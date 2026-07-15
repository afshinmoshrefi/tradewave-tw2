"""Safely provision MCP's internal keys without exposing raw credentials.

An already-configured, active MCP service key is reused. Rotation creates and
authenticates the replacement first, writes it only to the dedicated root-owned
MCP environment, and removes every broad-environment assignment. Older keys
remain live until ``--finalize --pid`` proves the new key is in the activated MCP
process; only then are they revoked. The raw key is never printed.

Release verification uses a fresh, sacrificial ordinary ``pro`` API key.  It is
minted only after the controller's durable transaction journal exists, bound to
that journal by transaction ID and digest, and revoked on every exit path.  The
raw key exists only in a short-lived root-controlled systemd credential source;
durable probe state contains identifiers and a keyed hash, never the credential.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets as _secrets
import shlex
import stat
import tempfile
import urllib.error
import urllib.request
import uuid
import sys
from contextlib import contextmanager
from pathlib import Path

try:  # Importable on Windows for pure unit tests; production requires Linux.
    import fcntl
except ModuleNotFoundError:  # pragma: no cover - exercised by Windows collection
    fcntl = None  # type: ignore[assignment]


SERVICE_EMAIL = "mcp-service@internal.tradewave"
KEY_NAME = "mcp-oauth-service"
VERIFIER_EMAIL = "mcp-release-verifier@internal.tradewave"
VERIFIER_KEY_NAME_PREFIX = "mcp-release-probe:"
_LEGACY_VERIFIER_KEY_NAME = "mcp-release-verifier"
VERIFIER_TIER = "pro"
VERIFIER_TIER_NAME = "Pro"
VERIFIER_MIN_PER_MINUTE = 120
VERIFIER_MIN_PER_DAY = 5_000
SECRETS_PATH = os.environ.get("TW_MCP_SECRETS", "/etc/tradewave/secrets.env")
MCP_ENV_PATH = os.environ.get("TW_MCP_RUNTIME_ENV", "/etc/tradewave/mcpserver.env")
VERIFIER_STATE_ROOT = "/var/lib/tradewave/mcp-verifier-probes"
VERIFIER_CREDENTIAL_ROOT = "/run/tradewave-mcp-verifier"
RELEASE_JOURNAL_ROOT = "/var/lib/tradewave/mcp-release-transactions"
LEGACY_VERIFIER_ENV_PATH = "/etc/tradewave/mcp-verifier.env"
LOCK_DIR = "/run/lock/tradewave"
LOCK_PATH = "/run/lock/tradewave/mcp-key.lock"
RELEASE_LOCK_PATH = "/run/lock/tradewave/mcp-release.lock"
ROTATION_STATE_PATH = os.environ.get(
    "TW_MCP_KEY_PENDING_STATE", "/var/lib/tradewave/mcp-key-rotation.json"
)
GATEWAY_ME_URL = "http://127.0.0.1:8088/v1/me"
_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?MCP_GATEWAY_KEY\s*=(.*)$")
_VERIFIER_ASSIGNMENT_RE = re.compile(r"^\s*TW_MCP_VERIFY_TOKEN\s*=(.*)$")
_ANY_VERIFIER_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?TW_MCP_VERIFY_TOKEN\s*=")
_SERVICE_KEY_RE = re.compile(r"^tw_svc_[A-Za-z0-9_-]{43}$")
_VERIFIER_KEY_RE = re.compile(r"^tw_live_[0-9a-f]{32}$")
_KEY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_VERIFIER_PROBE_NAME_RE = re.compile(
    r"^mcp-release-probe:([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
_VERIFIER_STATE_FIELDS = {
    "version",
    "transaction_id",
    "journal_sha256",
    "user_id",
    "key_id",
    "key_hash",
    "key_name",
}
_ROTATION_STATE_V1_FIELDS = {
    "version",
    "status",
    "replacement_key_id",
    "replacement_key_hash",
    "superseded_key_id",
    "superseded_key_hash",
}
_ROTATION_STATE_V2_FIELDS = _ROTATION_STATE_V1_FIELDS | {"source_key_hash"}
_PLATFORM_VALUE_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)
_PLATFORM_KEYS = {
    "POSTGRES_DSN",
    "API_KEY_HMAC_SECRET",
    "APPSERVER_JWT_SECRET",
    "MCP_GATEWAY_KEY",
}
_ABSENT_SOURCE_HASH = hashlib.sha256(b"TW_MCP_NO_SOURCE_KEY_V1").hexdigest()
_SYSTEM_STDLIB_PATH = (
    "/usr/lib/python313.zip",
    "/usr/lib/python3.13",
    "/usr/lib/python3.13/lib-dynload",
)


class _LocalSettings:
    """Compatibility-shaped, candidate-free settings owned by this artifact."""

    POSTGRES_DSN: str | None = None
    API_KEY_HMAC_SECRET: str | None = None


settings = _LocalSettings()


class ProvisionError(RuntimeError):
    pass


def _effective_ids() -> tuple[int, int]:
    if os.name == "nt":
        return 0, 0
    return os.geteuid(), os.getegid()


def _decode_environment_value(raw: str, *, label: str, path: str) -> str:
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        values = list(lexer)
    except ValueError as exc:
        raise ProvisionError(f"malformed {label} assignment in {path}") from exc
    if len(values) != 1 or any(
        character in values[0] for character in ("\x00", "\r", "\n")
    ):
        raise ProvisionError(f"invalid {label} assignment in {path}")
    return values[0]


def _read_bounded_regular(
    path: str, *, label: str, limit: int = 2 * 1024 * 1024
) -> tuple[bytes, os.stat_result]:
    if not os.path.isabs(path):
        raise ProvisionError(f"{label} path must be absolute")
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise ProvisionError(f"cannot inspect {label}: {path}") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ProvisionError(f"{label} must be a single-link regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProvisionError(f"cannot open {label}: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino, metadata.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            raise ProvisionError(f"{label} changed while opening")
        if metadata.st_size > limit:
            raise ProvisionError(f"{label} is too large")
        raw = b""
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > limit:
            raise ProvisionError(f"{label} is too large")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ):
            raise ProvisionError(f"{label} changed while reading")
        return raw, metadata
    finally:
        os.close(descriptor)


def _production_owner(metadata: os.stat_result, *, dedicated: bool, label: str) -> None:
    if os.name == "nt":
        return
    effective_uid, effective_gid = _effective_ids()
    expected_uid = 0 if effective_uid == 0 else effective_uid
    expected_gid = 0 if effective_uid == 0 else effective_gid
    if metadata.st_uid != expected_uid:
        raise ProvisionError(f"{label} has an unexpected owner")
    mode = stat.S_IMODE(metadata.st_mode)
    if dedicated:
        if metadata.st_gid != expected_gid or mode != 0o600:
            raise ProvisionError(f"{label} must be root:root mode 0600")
    elif mode & 0o027:
        raise ProvisionError(f"{label} has unsafe group/world permissions")


def _platform_values(path: str) -> dict[str, list[str]]:
    raw, metadata = _read_bounded_regular(path, label="platform secrets")
    _production_owner(metadata, dedicated=False, label="platform secrets")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ProvisionError("platform secrets is not valid UTF-8") from exc
    values = {name: [] for name in _PLATFORM_KEYS}
    for line in lines:
        match = _PLATFORM_VALUE_RE.fullmatch(line)
        if match is None or match.group(1) not in values:
            continue
        name = match.group(1)
        values[name].append(
            _decode_environment_value(match.group(2), label=name, path=path)
        )
    for name, assignments in values.items():
        if name == "MCP_GATEWAY_KEY":
            if len(set(assignments)) > 1:
                raise ProvisionError(
                    "broad secrets contains conflicting MCP_GATEWAY_KEY assignments"
                )
        elif len(assignments) > 1:
            raise ProvisionError(
                f"platform secrets contains duplicate {name} assignments"
            )
    return values


def _load_platform_settings() -> str:
    values = _platform_values(SECRETS_PATH)
    dsn = values["POSTGRES_DSN"]
    hmac_values = values["API_KEY_HMAC_SECRET"]
    jwt_values = values["APPSERVER_JWT_SECRET"]
    if not dsn or not dsn[0]:
        raise ProvisionError("POSTGRES_DSN is unset")
    secret = hmac_values[0] if hmac_values else jwt_values[0] if jwt_values else ""
    if not secret:
        raise ProvisionError("API_KEY_HMAC_SECRET/APPSERVER_JWT_SECRET is unset")
    settings.POSTGRES_DSN = dsn[0]
    settings.API_KEY_HMAC_SECRET = secret
    legacy = values["MCP_GATEWAY_KEY"]
    return legacy[0] if legacy else ""


class _DatabaseAdapter:
    def __init__(self, driver, extras) -> None:
        self._driver = driver
        self._extras = extras

    @contextmanager
    def cursor(self, commit: bool = False):
        if not settings.POSTGRES_DSN:
            raise ProvisionError("POSTGRES_DSN is unset")
        connection = self._driver.connect(settings.POSTGRES_DSN)
        try:
            with connection.cursor(
                cursor_factory=self._extras.RealDictCursor
            ) as cursor:
                yield cursor
            if commit:
                connection.commit()
        except BaseException:
            try:
                connection.rollback()
            except BaseException:
                pass
            raise
        finally:
            connection.close()


def _gateway_dependencies():
    """Import psycopg2 only from the verified provision site-packages."""
    forbidden = sorted(
        name
        for name in sys.modules
        if name == "apiserver" or name.startswith("apiserver.")
    )
    if forbidden:
        raise ProvisionError(
            "candidate application modules are loaded in the provisioner"
        )
    if len(sys.path) != len(_SYSTEM_STDLIB_PATH) + 1 or tuple(
        sys.path[:-1]
    ) != _SYSTEM_STDLIB_PATH:
        raise ProvisionError(
            "provisioner requires the exact system-stdlib-first import path"
        )
    provision_site = Path(sys.path[-1])
    try:
        provision_site = provision_site.resolve(strict=True)
    except OSError as exc:
        raise ProvisionError("cannot resolve verified provision site-packages") from exc
    if (
        provision_site.name != "site-packages"
        or provision_site.parent.name != "python3.13"
    ):
        raise ProvisionError("verified provision site-packages has an unexpected path")
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise ProvisionError(
            "sealed psycopg2 provisioning driver is unavailable"
        ) from exc
    try:
        driver_path = Path(psycopg2.__file__).resolve(strict=True)
        driver_path.relative_to(provision_site)
    except (OSError, ValueError, TypeError) as exc:
        raise ProvisionError(
            "psycopg2 escaped verified provision site-packages"
        ) from exc
    version = getattr(psycopg2, "__version__", None)
    if not isinstance(version, str) or not version.startswith("2.9.12"):
        raise ProvisionError("unexpected psycopg2 provisioning driver")
    return _DatabaseAdapter(psycopg2, psycopg2.extras)


def _key_hash(raw_key: str) -> str:
    secret = settings.API_KEY_HMAC_SECRET
    if not isinstance(secret, str) or not secret:
        raise ProvisionError("API_KEY_HMAC_SECRET is unset")
    if not isinstance(raw_key, str):
        raise ProvisionError("API key must be text")
    value = hmac.new(
        secret.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not isinstance(value, str) or not _KEY_HASH_RE.fullmatch(value):
        raise ProvisionError("gateway returned an invalid API-key hash")
    return value


def check_runtime_dependencies() -> dict[str, str]:
    """Import the exact DB adapter without opening a connection.

    The release bootstrap uses this preflight to prove that isolated system
    Python can import psycopg2 only after the sealed provision site-packages is
    inserted.  It intentionally performs no database or network I/O.
    """
    _gateway_dependencies()
    driver = sys.modules.get("psycopg2")
    version = getattr(driver, "__version__", None)
    if not isinstance(version, str) or not version.startswith("2.9.12"):
        raise ProvisionError("unexpected psycopg2 provisioning driver")
    driver_file = str(Path(getattr(driver, "__file__", "")).resolve(strict=True))
    return {
        "db_adapter": "local-minimal-cursor",
        "driver_file": driver_file,
        "psycopg2_version": version,
    }


def _is_exact_internal_profile(
    row: object, *, email: str, first_name: str, api_tier: str, roles: list[str]
) -> bool:
    """Reject every mutable users field except created/updated timestamps."""
    if not isinstance(row, dict):
        return False
    return (
        row.get("email") == email
        and row.get("first_name") == first_name
        and row.get("last_name") is None
        and row.get("tier") == "explorer"
        and row.get("legacy_wp_level") == "1"
        and row.get("api_tier") == api_tier
        and row.get("roles") == roles
        and row.get("email_verified") is False
        and row.get("workos_user_id") is None
        and row.get("legacy_phpass_hash") is None
        and row.get("api_key_hash") is None
        and row.get("stripe_customer_id") is None
        and row.get("stripe_subscription_id") is None
        and row.get("stripe_subscription_status") is None
        and row.get("trial_ends_at") is None
        and row.get("reverse_trial_ends_at") is None
        and row.get("navigator_mcp_first_connect_at") is None
        and row.get("first_ai_score_viewed_at") is None
        and row.get("last_login_at") is None
    )


_INTERNAL_PROFILE_SELECT = (
    "u.email, u.first_name, u.last_name, u.tier, u.legacy_wp_level, "
    "u.api_tier, u.roles, u.email_verified, u.workos_user_id, "
    "u.legacy_phpass_hash, u.api_key_hash, u.stripe_customer_id, "
    "u.stripe_subscription_id, u.stripe_subscription_status, u.trial_ends_at, "
    "u.reverse_trial_ends_at, u.navigator_mcp_first_connect_at, "
    "u.first_ai_score_viewed_at, u.last_login_at"
)


def _decode_value(raw: str, path: str) -> str:
    return _decode_environment_value(raw, label="MCP_GATEWAY_KEY", path=path)


def _read_key(path: str, *, required: bool) -> str:
    if not os.path.lexists(path):
        if required:
            raise ProvisionError(f"required environment file is missing: {path}")
        return ""
    try:
        raw, _metadata = _read_bounded_regular(path, label="environment file")
        lines = raw.decode("utf-8").splitlines()
    except FileNotFoundError:
        if required:
            raise ProvisionError(f"required environment file is missing: {path}")
        return ""
    except UnicodeDecodeError as exc:
        raise ProvisionError(f"{path} is not valid UTF-8") from exc
    except OSError as exc:
        raise ProvisionError(f"cannot read {path}") from exc
    values = []
    for line in lines:
        match = _ASSIGNMENT_RE.match(line)
        if match:
            values.append(_decode_value(match.group(1), path))
    if len(values) > 1:
        raise ProvisionError(f"duplicate MCP_GATEWAY_KEY assignments in {path}")
    if not values:
        return ""
    return values[0]


def _read_runtime_key(*, required: bool) -> str:
    if not os.path.lexists(MCP_ENV_PATH):
        if required:
            raise ProvisionError(
                "required dedicated MCP runtime environment is missing"
            )
        return ""
    raw, metadata = _read_bounded_regular(
        MCP_ENV_PATH, label="dedicated MCP runtime environment"
    )
    _production_owner(
        metadata, dedicated=True, label="dedicated MCP runtime environment"
    )
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ProvisionError(
            "dedicated MCP runtime environment is not valid UTF-8"
        ) from exc
    values = [
        _decode_value(match.group(1), MCP_ENV_PATH)
        for line in lines
        if (match := _ASSIGNMENT_RE.match(line)) is not None
    ]
    if len(values) > 1:
        raise ProvisionError(
            "dedicated MCP runtime environment has duplicate MCP_GATEWAY_KEY assignments"
        )
    if not values:
        if required:
            raise ProvisionError(
                "dedicated MCP runtime environment lacks MCP_GATEWAY_KEY"
            )
        return ""
    return values[0]


def _parse_verifier_key(raw: bytes, path: str) -> str:
    """Parse the one literal assignment accepted as a systemd credential."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProvisionError("verifier credential source is not valid ASCII") from exc
    match = re.fullmatch(r"TW_MCP_VERIFY_TOKEN=(tw_live_[0-9a-f]{32})\n", text)
    if match is None:
        raise ProvisionError(
            f"verifier credential source must contain one literal assignment: {path}"
        )
    return match.group(1)


def _read_verifier_key(path: str, *, required: bool) -> str:
    """Read an ephemeral credential source after strict path/metadata checks."""
    if not os.path.isabs(path):
        raise ProvisionError("verifier credential source path must be absolute")
    if os.name == "nt":  # Production is Linux; preserve pure Windows unit tests.
        if not os.path.lexists(path):
            if required:
                raise ProvisionError(
                    f"required verifier credential source is missing: {path}"
                )
            return ""
        raw, _metadata = _read_bounded_regular(
            path, label="verifier credential source", limit=8192
        )
        return _parse_verifier_key(raw, path)
    directory, basename = os.path.split(path)
    if not basename:
        raise ProvisionError("verifier credential source path has no filename")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_descriptor = os.open(directory, directory_flags)
    except OSError as exc:
        raise ProvisionError("cannot open verifier credential source parent") from exc
    try:
        directory_metadata = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_metadata.st_mode):
            raise ProvisionError("verifier credential source parent is not a directory")
        if directory_metadata.st_uid != 0 or directory_metadata.st_mode & 0o022:
            raise ProvisionError("verifier credential source parent must be root-controlled")
    except BaseException:
        os.close(directory_descriptor)
        raise
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(basename, flags, dir_fd=directory_descriptor)
    except FileNotFoundError:
        os.close(directory_descriptor)
        if required:
            raise ProvisionError(
                f"required verifier credential source is missing: {path}"
            )
        return ""
    except OSError as exc:
        os.close(directory_descriptor)
        raise ProvisionError(f"cannot open verifier credential source: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisionError("verifier credential source must be a regular file")
        if metadata.st_nlink != 1:
            raise ProvisionError("verifier credential source must have one link")
        if metadata.st_uid != 0 or metadata.st_gid != 0:
            raise ProvisionError("verifier credential source must be owned by root:root")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ProvisionError("verifier credential source must have mode 0600")
        raw = b""
        while len(raw) <= 8192:
            chunk = os.read(descriptor, 8193 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > 8192:
            raise ProvisionError("verifier credential source is too large")
    finally:
        os.close(descriptor)
        os.close(directory_descriptor)
    return _parse_verifier_key(raw, path)


def _reject_verifier_in_platform_secrets(path: str) -> None:
    """The broad root:flask file is inherited by peers and must never hold this key."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ProvisionError(f"cannot inspect platform secrets file: {path}") from exc
    if any(_ANY_VERIFIER_ASSIGNMENT_RE.match(line) for line in lines):
        raise ProvisionError(
            "TW_MCP_VERIFY_TOKEN must be removed from the platform secrets file"
        )


def _snapshot(path: str) -> tuple[bytes, os.stat_result]:
    return _read_bounded_regular(path, label="snapshot target")


def _write_atomic(path: str, content: bytes, metadata: os.stat_result) -> None:
    directory = os.path.dirname(path)
    temporary = ""
    try:
        fd, temporary = tempfile.mkstemp(prefix=".mcp-key-", dir=directory)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "chown"):
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.chmod(temporary, stat.S_IMODE(metadata.st_mode))
        os.replace(temporary, path)
        temporary = ""
        _fsync_directory(directory)
    except OSError as exc:
        raise ProvisionError(f"atomic environment update failed for {path}") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _require_root_for_verifier_lifecycle() -> None:
    if os.name != "nt" and _effective_ids() != (0, 0):
        raise ProvisionError("verifier-probe lifecycle must run as root:root")


def _inspect_controlled_directory(
    path: str, *, private: bool, label: str
) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ProvisionError(f"cannot inspect {label}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ProvisionError(f"{label} must be a real directory")
    if os.name != "nt":
        if metadata.st_uid != 0 or metadata.st_gid != 0:
            raise ProvisionError(f"{label} must be owned by root:root")
        mode = stat.S_IMODE(metadata.st_mode)
        if private and mode != 0o700:
            raise ProvisionError(f"{label} must have mode 0700")
        if not private and mode & 0o022:
            raise ProvisionError(f"{label} is writable outside root")
    return metadata


def _prepare_private_tree(path: str, *, label: str) -> str:
    """Create only missing root-owned directories; never follow a symlink."""
    _require_root_for_verifier_lifecycle()
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ProvisionError(f"{label} path must be canonical and absolute")
    if os.name == "nt":  # Production is Linux; preserve pure Windows unit tests.
        Path(path).mkdir(parents=True, mode=0o700, exist_ok=True)
        _inspect_controlled_directory(path, private=False, label=label)
        return path
    current = os.path.sep
    parts = [part for part in Path(path).parts if part != os.path.sep]
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        final = index == len(parts) - 1
        if not os.path.lexists(current):
            try:
                os.mkdir(current, 0o700)
                os.chown(current, 0, 0)
                os.chmod(current, 0o700)
                _fsync_directory(os.path.dirname(current) or os.path.sep)
            except OSError as exc:
                raise ProvisionError(f"cannot create {label}") from exc
        _inspect_controlled_directory(
            current, private=final, label=label if final else "path ancestor"
        )
    return path


def _write_private_file(path: str, payload: bytes, *, label: str) -> None:
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ProvisionError(f"{label} path must be canonical and absolute")
    directory = os.path.dirname(path)
    _inspect_controlled_directory(directory, private=True, label=f"{label} parent")
    if os.path.lexists(path):
        raise ProvisionError(f"refusing to replace existing {label}")
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".mcp-probe-", dir=directory)
        with os.fdopen(descriptor, "wb") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            if hasattr(os, "fchown"):
                os.fchown(handle.fileno(), 0, 0)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = ""
        _fsync_directory(directory)
    except OSError as exc:
        raise ProvisionError(f"cannot publish {label}") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _unlink_private_file(path: str, *, label: str, missing_ok: bool = True) -> bool:
    if not os.path.lexists(path):
        if missing_ok:
            return False
        raise ProvisionError(f"required {label} is missing")
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ProvisionError(f"cannot inspect {label}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise ProvisionError(f"{label} must be a single-link regular file")
    if os.name != "nt" and (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ProvisionError(f"{label} must be root:root mode 0600")
    try:
        os.unlink(path)
        _fsync_directory(os.path.dirname(path))
    except OSError as exc:
        raise ProvisionError(f"cannot remove {label}") from exc
    return True


def _write_verifier_key(path: str, raw_key: str) -> None:
    """Publish the ephemeral source later copied by systemd LoadCredential."""
    if not _VERIFIER_KEY_RE.fullmatch(raw_key):
        raise ProvisionError("refusing to write an invalid verifier key")
    payload = f"TW_MCP_VERIFY_TOKEN={raw_key}\n".encode("ascii")
    _write_private_file(path, payload, label="verifier credential source")
    if not hmac.compare_digest(_read_verifier_key(path, required=True), raw_key):
        raise ProvisionError("verifier credential source read-back failed")


def _replace_key(path: str, raw_key: str, *, append_if_missing: bool) -> None:
    content, metadata = _snapshot(path)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProvisionError(f"{path} is not valid UTF-8") from exc
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if _ASSIGNMENT_RE.match(line)]
    if len(matches) > 1:
        raise ProvisionError(f"duplicate MCP_GATEWAY_KEY assignments in {path}")
    replacement = f"MCP_GATEWAY_KEY={raw_key}\n"
    if matches:
        lines[matches[0]] = replacement
    elif append_if_missing:
        if text and not text.endswith(("\n", "\r")):
            lines.append("\n")
        lines.extend(("# MCP -> v1 gateway OAuth delegation key\n", replacement))
    else:
        raise ProvisionError(f"MCP_GATEWAY_KEY is missing from {path}")
    _write_atomic(path, "".join(lines).encode("utf-8"), metadata)


def _prepare_runtime_parent() -> str:
    if not os.path.isabs(MCP_ENV_PATH):
        raise ProvisionError("dedicated MCP runtime environment path must be absolute")
    directory = os.path.dirname(MCP_ENV_PATH)
    try:
        Path(directory).mkdir(parents=True, mode=0o755, exist_ok=True)
        metadata = os.stat(directory, follow_symlinks=False)
    except OSError as exc:
        raise ProvisionError(
            "cannot prepare dedicated MCP runtime environment parent"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ProvisionError(
            "dedicated MCP runtime environment parent is not a real directory"
        )
    if os.name != "nt":
        effective_uid, _effective_gid = _effective_ids()
        expected_uid = 0 if effective_uid == 0 else effective_uid
        if metadata.st_uid != expected_uid or metadata.st_mode & 0o022:
            raise ProvisionError(
                "dedicated MCP runtime environment parent is not root-controlled"
            )
    return directory


def _write_runtime_key(raw_key: str) -> None:
    if not _SERVICE_KEY_RE.fullmatch(raw_key):
        raise ProvisionError(
            "refusing to write a non-service key to dedicated MCP environment"
        )
    directory = _prepare_runtime_parent()
    if os.path.lexists(MCP_ENV_PATH):
        _read_runtime_key(required=False)
        content, _metadata = _snapshot(MCP_ENV_PATH)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProvisionError(
                "dedicated MCP runtime environment is not valid UTF-8"
            ) from exc
        lines = text.splitlines(keepends=True)
        matches = [
            index for index, line in enumerate(lines) if _ASSIGNMENT_RE.match(line)
        ]
        if len(matches) > 1:
            raise ProvisionError(
                "dedicated MCP runtime environment has duplicate MCP_GATEWAY_KEY assignments"
            )
        if matches:
            lines[matches[0]] = f"MCP_GATEWAY_KEY={raw_key}\n"
        else:
            if text and not text.endswith(("\n", "\r")):
                lines.append("\n")
            lines.extend(
                (
                    "# MCP OAuth delegation key; root-only.\n",
                    f"MCP_GATEWAY_KEY={raw_key}\n",
                )
            )
        payload = "".join(lines).encode("utf-8")
    else:
        payload = (
            "# MCP OAuth delegation key; root-only.\n" f"MCP_GATEWAY_KEY={raw_key}\n"
        ).encode("utf-8")
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".mcp-runtime-", dir=directory)
        with os.fdopen(descriptor, "wb") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            if hasattr(os, "fchown"):
                effective_uid, effective_gid = _effective_ids()
                owner = 0 if effective_uid == 0 else effective_uid
                group = 0 if effective_uid == 0 else effective_gid
                os.fchown(handle.fileno(), owner, group)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, MCP_ENV_PATH)
        temporary = ""
        _fsync_directory(directory)
    except OSError as exc:
        raise ProvisionError(
            "atomic dedicated MCP runtime environment update failed"
        ) from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    if _read_runtime_key(required=True) != raw_key:
        raise ProvisionError("dedicated MCP runtime environment read-back failed")


def _remove_broad_service_assignments() -> None:
    content, metadata = _snapshot(SECRETS_PATH)
    _production_owner(metadata, dedicated=False, label="platform secrets")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProvisionError("platform secrets is not valid UTF-8") from exc
    lines = text.splitlines(keepends=True)
    retained = [line for line in lines if _ASSIGNMENT_RE.match(line) is None]
    _write_atomic(SECRETS_PATH, "".join(retained).encode("utf-8"), metadata)
    if _platform_values(SECRETS_PATH)["MCP_GATEWAY_KEY"]:
        raise ProvisionError("broad MCP_GATEWAY_KEY removal read-back failed")


def _restore(path: str, snapshot: tuple[bytes, os.stat_result]) -> None:
    _write_atomic(path, snapshot[0], snapshot[1])


def _optional_snapshot(path: str) -> tuple[bytes, os.stat_result] | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProvisionError(f"cannot inspect {path}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ProvisionError(f"refusing non-regular snapshot path: {path}")
    return _snapshot(path)


def _fsync_directory(path: str) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _normalise_key_id(value: object, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProvisionError(f"rotation state has an invalid {label}") from exc


def _canonical_uuid(value: object, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProvisionError(f"invalid {label}") from exc
    canonical = str(parsed)
    if canonical != value or parsed.version not in {1, 2, 3, 4, 5}:
        raise ProvisionError(f"invalid {label}")
    return canonical


def _verifier_probe_name(transaction_id: str) -> str:
    transaction_id = _canonical_uuid(transaction_id, "verifier transaction id")
    return VERIFIER_KEY_NAME_PREFIX + transaction_id


def _expected_verifier_state_path(transaction_id: str) -> str:
    return os.path.join(VERIFIER_STATE_ROOT, f"{transaction_id}.json")


def _expected_verifier_credential_path(transaction_id: str) -> str:
    return os.path.join(
        VERIFIER_CREDENTIAL_ROOT, transaction_id, "verify-env"
    )


def _validate_verifier_paths(
    transaction_id: str, state_path: str, credential_path: str
) -> tuple[str, str, str]:
    transaction_id = _canonical_uuid(transaction_id, "verifier transaction id")
    expected_state = _expected_verifier_state_path(transaction_id)
    expected_credential = _expected_verifier_credential_path(transaction_id)
    if state_path != expected_state:
        raise ProvisionError("verifier state path does not match its transaction")
    if credential_path != expected_credential:
        raise ProvisionError("verifier credential path does not match its transaction")
    return transaction_id, expected_state, expected_credential


def _validate_verifier_state(
    value: object, *, expected_transaction_id: str | None = None
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _VERIFIER_STATE_FIELDS:
        raise ProvisionError("verifier probe state has an invalid schema")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ProvisionError("verifier probe state has an unsupported version")
    transaction_id = _canonical_uuid(
        value.get("transaction_id"), "verifier state transaction id"
    )
    if expected_transaction_id is not None and transaction_id != expected_transaction_id:
        raise ProvisionError("verifier probe state belongs to another transaction")
    journal_sha256 = value.get("journal_sha256")
    key_hash = value.get("key_hash")
    if not isinstance(journal_sha256, str) or not _KEY_HASH_RE.fullmatch(
        journal_sha256
    ):
        raise ProvisionError("verifier probe state has an invalid journal digest")
    if not isinstance(key_hash, str) or not _KEY_HASH_RE.fullmatch(key_hash):
        raise ProvisionError("verifier probe state has an invalid key hash")
    user_id = _canonical_uuid(value.get("user_id"), "verifier state user id")
    key_id = _canonical_uuid(value.get("key_id"), "verifier state key id")
    key_name = value.get("key_name")
    if key_name != _verifier_probe_name(transaction_id):
        raise ProvisionError("verifier probe state has an invalid key marker")
    return {
        "version": 1,
        "transaction_id": transaction_id,
        "journal_sha256": journal_sha256,
        "user_id": user_id,
        "key_id": key_id,
        "key_hash": key_hash,
        "key_name": key_name,
    }


def _read_verifier_state(
    state_path: str,
    *,
    transaction_id: str,
    required: bool,
) -> dict[str, object] | None:
    expected = _expected_verifier_state_path(transaction_id)
    if state_path != expected:
        raise ProvisionError("verifier state path does not match its transaction")
    if not os.path.lexists(state_path):
        if required:
            raise ProvisionError("required verifier probe state is missing")
        return None
    raw, metadata = _read_bounded_regular(
        state_path, label="verifier probe state", limit=8192
    )
    _production_owner(metadata, dedicated=True, label="verifier probe state")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("verifier probe state is invalid JSON") from exc
    return _validate_verifier_state(
        value, expected_transaction_id=transaction_id
    )


def _write_verifier_state(state_path: str, value: dict[str, object]) -> None:
    state = _validate_verifier_state(value)
    if state_path != _expected_verifier_state_path(str(state["transaction_id"])):
        raise ProvisionError("verifier state path does not match its transaction")
    payload = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    _write_private_file(state_path, payload, label="verifier probe state")


def _verify_durable_release_journal(
    transaction_id: str, journal_manifest: str
) -> str:
    """Verify and fsync the controller journal before any probe DB mutation."""
    transaction_id = _canonical_uuid(transaction_id, "verifier transaction id")
    if (
        not os.path.isabs(journal_manifest)
        or os.path.normpath(journal_manifest) != journal_manifest
        or os.path.basename(journal_manifest) != "manifest.json"
        or os.path.basename(os.path.dirname(journal_manifest)) != "active"
    ):
        raise ProvisionError("verifier requires the active release journal manifest")
    parent = os.path.dirname(journal_manifest)
    root = os.path.dirname(parent)
    if root != RELEASE_JOURNAL_ROOT:
        raise ProvisionError("verifier journal is outside the fixed release journal root")
    _inspect_controlled_directory(root, private=True, label="release journal root")
    _inspect_controlled_directory(parent, private=True, label="active release journal")
    raw, metadata = _read_bounded_regular(
        journal_manifest, label="active release journal manifest", limit=65536
    )
    _production_owner(
        metadata, dedicated=True, label="active release journal manifest"
    )
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("active release journal manifest is invalid JSON") from exc
    expected_fields = {
        "version",
        "txid",
        "candidate",
        "entry",
        "gateway_entry",
        "files",
        "pointers",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != expected_fields
        or type(manifest.get("version")) is not int
        or manifest.get("version") != 4
        or manifest.get("txid") != transaction_id
    ):
        raise ProvisionError("active release journal manifest does not bind transaction")
    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"bundle", "sha"}:
        raise ProvisionError("active release journal candidate has an invalid schema")
    candidate_bundle = candidate.get("bundle")
    candidate_sha = candidate.get("sha")
    if (
        not isinstance(candidate_bundle, str)
        or not candidate_bundle
        or "\x00" in candidate_bundle
        or not os.path.isabs(candidate_bundle)
        or os.path.normpath(candidate_bundle) != candidate_bundle
        or not isinstance(candidate_sha, str)
        or not _RELEASE_SHA_RE.fullmatch(candidate_sha)
    ):
        raise ProvisionError("active release journal candidate identity is invalid")

    entry_fields = {
        "kind",
        "policy",
        "bundle",
        "sha",
        "cwd",
        "command",
        "argv_sha256",
        "active",
    }

    def validate_entry(value: object, *, label: str) -> None:
        if not isinstance(value, dict) or set(value) != entry_fields:
            raise ProvisionError(f"active release journal {label} has an invalid schema")
        kind = value.get("kind")
        active = value.get("active")
        if kind not in {"sealed", "legacy", "absent"} or type(active) is not bool:
            raise ProvisionError(f"active release journal {label} identity is invalid")
        if active is not (kind != "absent"):
            raise ProvisionError(f"active release journal {label} state is inconsistent")
        policy = value.get("policy")
        bundle = value.get("bundle")
        entry_sha = value.get("sha")
        cwd = value.get("cwd")
        command = value.get("command")
        argv_sha256 = value.get("argv_sha256")
        if (
            not isinstance(policy, str)
            or not policy
            or "\x00" in policy
            or not isinstance(bundle, str)
            or "\x00" in bundle
            or not isinstance(entry_sha, str)
            or not isinstance(cwd, str)
            or not cwd
            or "\x00" in cwd
            or not os.path.isabs(cwd)
            or os.path.normpath(cwd) != cwd
            or not isinstance(command, str)
            or not command
            or "\x00" in command
            or not os.path.isabs(command)
            or os.path.normpath(command) != command
            or not isinstance(argv_sha256, str)
            or not _KEY_HASH_RE.fullmatch(argv_sha256)
        ):
            raise ProvisionError(f"active release journal {label} identity is invalid")
        if kind == "sealed":
            if (
                not bundle
                or not os.path.isabs(bundle)
                or os.path.normpath(bundle) != bundle
                or not _RELEASE_SHA_RE.fullmatch(entry_sha)
            ):
                raise ProvisionError(
                    f"active release journal sealed {label} identity is invalid"
                )
        elif bundle or entry_sha:
            raise ProvisionError(
                f"active release journal non-sealed {label} identity is invalid"
            )

    validate_entry(manifest.get("entry"), label="MCP entry")
    validate_entry(manifest.get("gateway_entry"), label="gateway entry")
    if not isinstance(manifest.get("files"), dict) or not isinstance(
        manifest.get("pointers"), dict
    ):
        raise ProvisionError("active release journal snapshots have an invalid schema")
    descriptor = os.open(
        journal_manifest,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        if os.name != "nt":
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(parent)
    _fsync_directory(root)
    return hashlib.sha256(raw).hexdigest()


def _validate_rotation_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProvisionError("rotation state has an invalid schema")
    version = value.get("version")
    expected_fields = (
        _ROTATION_STATE_V1_FIELDS if version == 1 else _ROTATION_STATE_V2_FIELDS
    )
    allowed_statuses = (
        {"pending", "active"}
        if version == 1
        else {
            "planned",
            "pending",
            "active",
        }
    )
    if set(value) != expected_fields:
        raise ProvisionError("rotation state has an invalid schema")
    if version not in {1, 2} or value.get("status") not in allowed_statuses:
        raise ProvisionError("rotation state has an unsupported version or status")
    replacement_id = _normalise_key_id(
        value.get("replacement_key_id"), "replacement key id"
    )
    replacement_hash = value.get("replacement_key_hash")
    if not isinstance(replacement_hash, str) or not _KEY_HASH_RE.fullmatch(
        replacement_hash
    ):
        raise ProvisionError("rotation state has an invalid replacement key hash")
    superseded_id_raw = value.get("superseded_key_id")
    superseded_hash = value.get("superseded_key_hash")
    if (superseded_id_raw is None) != (superseded_hash is None):
        raise ProvisionError("rotation state has an incomplete superseded-key binding")
    superseded_id = None
    if superseded_id_raw is not None:
        superseded_id = _normalise_key_id(superseded_id_raw, "superseded key id")
        if not isinstance(superseded_hash, str) or not _KEY_HASH_RE.fullmatch(
            superseded_hash
        ):
            raise ProvisionError("rotation state has an invalid superseded key hash")
        if superseded_id == replacement_id or superseded_hash == replacement_hash:
            raise ProvisionError(
                "rotation state aliases replacement and superseded keys"
            )
    if value["status"] == "active" and superseded_id is not None:
        raise ProvisionError(
            "active rotation state must not retain superseded-key data"
        )
    source_hash = None
    if version == 2:
        source_hash = value.get("source_key_hash")
        if not isinstance(source_hash, str) or not _KEY_HASH_RE.fullmatch(source_hash):
            raise ProvisionError("rotation state has an invalid source key hash")
        if value["status"] == "planned":
            if source_hash == replacement_hash:
                raise ProvisionError(
                    "planned replacement aliases the pre-operation source"
                )
            if superseded_hash is not None and source_hash != superseded_hash:
                raise ProvisionError(
                    "planned superseded row does not bind the source key"
                )
    state = {
        "version": version,
        "status": value["status"],
        "replacement_key_id": replacement_id,
        "replacement_key_hash": replacement_hash,
        "superseded_key_id": superseded_id,
        "superseded_key_hash": superseded_hash,
    }
    if version == 2:
        state["source_key_hash"] = source_hash
    return state


def _read_rotation_state(*, required: bool) -> dict[str, object] | None:
    if not os.path.isabs(ROTATION_STATE_PATH):
        raise ProvisionError("MCP key rotation state path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(ROTATION_STATE_PATH, flags)
    except FileNotFoundError:
        if required:
            raise ProvisionError("MCP key rotation state is missing")
        return None
    except OSError as exc:
        raise ProvisionError("cannot open MCP key rotation state") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisionError("MCP key rotation state is not a regular file")
        if os.name != "nt":
            effective_uid, _effective_gid = _effective_ids()
            if (
                metadata.st_uid != effective_uid
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ProvisionError(
                    "MCP key rotation state must be owner-only mode 0600"
                )
        raw = b""
        while len(raw) <= 8192:
            chunk = os.read(descriptor, 8193 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > 8192:
            raise ProvisionError("MCP key rotation state is too large")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("MCP key rotation state is invalid JSON") from exc
    return _validate_rotation_state(value)


def _write_rotation_state(value: dict[str, object]) -> None:
    state = _validate_rotation_state(value)
    if not os.path.isabs(ROTATION_STATE_PATH):
        raise ProvisionError("MCP key rotation state path must be absolute")
    directory = os.path.dirname(ROTATION_STATE_PATH)
    try:
        Path(directory).mkdir(parents=True, mode=0o700, exist_ok=True)
        directory_metadata = os.stat(directory, follow_symlinks=False)
        if not stat.S_ISDIR(directory_metadata.st_mode):
            raise ProvisionError("MCP key rotation state parent is not a directory")
        if os.name != "nt":
            effective_uid, _effective_gid = _effective_ids()
            if (
                directory_metadata.st_uid != effective_uid
                or directory_metadata.st_mode & 0o022
            ):
                raise ProvisionError(
                    "MCP key rotation state parent is not owner-controlled"
                )
    except OSError as exc:
        raise ProvisionError("cannot prepare MCP key rotation state directory") from exc
    temporary = ""
    payload = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".mcp-rotation-", dir=directory)
        with os.fdopen(descriptor, "wb") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, ROTATION_STATE_PATH)
        temporary = ""
        _fsync_directory(directory)
    except OSError as exc:
        raise ProvisionError("atomic MCP key rotation state update failed") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _restore_rotation_state(snapshot: tuple[bytes, os.stat_result] | None) -> None:
    if snapshot is not None:
        _write_atomic(ROTATION_STATE_PATH, snapshot[0], snapshot[1])
        return
    try:
        os.unlink(ROTATION_STATE_PATH)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ProvisionError("cannot remove new MCP key rotation state") from exc
    _fsync_directory(os.path.dirname(ROTATION_STATE_PATH))


def _after_rotation_state_fsync() -> None:
    """Fault-injection seam: a real process may die after state fsync and before env writes."""


def _after_service_plan_fsync() -> None:
    """Fault-injection seam after durable intent and before replacement INSERT."""


def _after_service_key_insert() -> None:
    """Fault-injection seam after INSERT commits while durable state remains planned."""


def _before_service_pending_fsync() -> None:
    """Fault-injection seam after live validation while durable state is still planned."""


def _after_first_environment_fsync() -> None:
    """Fault-injection seam after dedicated K1 is durable."""


def _after_broad_key_removal_fsync() -> None:
    """Fault-injection seam after broad MCP key assignments are durably absent."""


def _after_verifier_key_insert() -> None:
    """Fault-injection seam after the marked DB row commits."""


def _after_verifier_state_fsync() -> None:
    """Fault-injection seam after non-secret state, before raw credential publication."""


def _after_verifier_credential_fsync() -> None:
    """Fault-injection seam after the ephemeral credential source is durable."""


def _open_verified_lock(path: str) -> int:
    try:
        Path(LOCK_DIR).mkdir(mode=0o700, exist_ok=True)
        directory_metadata = os.stat(LOCK_DIR, follow_symlinks=False)
    except OSError as exc:
        raise ProvisionError("cannot prepare MCP provisioning lock directory") from exc
    if not stat.S_ISDIR(directory_metadata.st_mode):
        raise ProvisionError("MCP provisioning lock parent is not a directory")
    if (
        directory_metadata.st_uid != 0
        or directory_metadata.st_gid != 0
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
    ):
        raise ProvisionError("MCP provisioning lock parent must be root:root mode 0700")
    flags = (
        os.O_CREAT
        | os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ProvisionError("cannot open MCP provisioning lock") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisionError("MCP provisioning lock is not a regular file")
        if (
            metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ProvisionError("MCP provisioning lock must be root:root mode 0600")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _exclusive_lock():
    descriptor = _open_verified_lock(LOCK_PATH)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


@contextmanager
def _release_not_active():
    """Coordinate provisioning with deploy without involving deploy-time finalization."""
    inherited = os.environ.get("TW_MCP_RELEASE_LOCK_FD", "")
    if inherited:
        if not inherited.isdigit() or int(inherited) < 3:
            raise ProvisionError("inherited MCP release lock descriptor is invalid")
        descriptor = int(inherited)
        try:
            metadata = os.fstat(descriptor)
            path_metadata = os.stat(RELEASE_LOCK_PATH, follow_symlinks=False)
        except OSError as exc:
            raise ProvisionError("cannot verify inherited MCP release lock") from exc
        if not (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and metadata.st_gid == 0
            and stat.S_IMODE(metadata.st_mode) == 0o600
            and stat.S_ISREG(path_metadata.st_mode)
            and metadata.st_dev == path_metadata.st_dev
            and metadata.st_ino == path_metadata.st_ino
        ):
            raise ProvisionError(
                "inherited MCP release lock does not match the safe lock file"
            )
        try:
            # The deploy child inherits the same locked open-file description,
            # so this is idempotent. A separately opened descriptor cannot pass.
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProvisionError(
                "inherited MCP release lock is not the held deploy lock"
            ) from exc
        yield
        return
    descriptor = _open_verified_lock(RELEASE_LOCK_PATH)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProvisionError(
                "an MCP release/rollback is active; provisioning is not allowed concurrently"
            ) from exc
        yield
    finally:
        os.close(descriptor)


def _ensure_user_and_find_key(existing_key: str) -> tuple[object, object | None]:
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "SELECT u.id, " + _INTERNAL_PROFILE_SELECT + " "
            "FROM users AS u WHERE u.email = %s FOR UPDATE",
            (SERVICE_EMAIL,),
        )
        row = cur.fetchone()
        if row:
            if not _is_exact_internal_profile(
                row,
                email=SERVICE_EMAIL,
                first_name="MCP Service",
                api_tier="mcp",
                roles=["user"],
            ):
                raise ProvisionError(
                    "reserved MCP service identity collides with a non-exact account"
                )
            user_id = row["id"]
        else:
            cur.execute(
                "INSERT INTO users "
                "(email, first_name, last_name, tier, legacy_wp_level, api_tier, roles, "
                "email_verified, workos_user_id, legacy_phpass_hash, api_key_hash, "
                "stripe_customer_id, stripe_subscription_id, stripe_subscription_status, "
                "trial_ends_at, reverse_trial_ends_at, navigator_mcp_first_connect_at, "
                "first_ai_score_viewed_at, last_login_at) "
                "VALUES (%s, %s, NULL, 'explorer', '1', 'mcp', %s::jsonb, false, "
                "NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL) "
                "RETURNING id",
                (SERVICE_EMAIL, "MCP Service", json.dumps(["user"])),
            )
            user_id = cur.fetchone()["id"]
        key_id = None
        if existing_key and _SERVICE_KEY_RE.fullmatch(existing_key):
            cur.execute(
                "SELECT k.id FROM api_keys AS k JOIN users AS u ON u.id = k.user_id "
                "WHERE k.user_id = %s AND u.email = %s AND u.tier = 'explorer' "
                "AND u.api_tier = 'mcp' AND u.roles = %s::jsonb "
                "AND u.email_verified = false AND u.workos_user_id IS NULL "
                "AND u.stripe_customer_id IS NULL AND u.stripe_subscription_id IS NULL "
                "AND u.stripe_subscription_status IS NULL AND k.name = %s "
                "AND k.key_hash = %s AND k.revoked_at IS NULL",
                (
                    user_id,
                    SERVICE_EMAIL,
                    json.dumps(["user"]),
                    KEY_NAME,
                    _key_hash(existing_key),
                ),
            )
            key_row = cur.fetchone()
            key_id = key_row["id"] if key_row else None
        return user_id, key_id


def _find_active_key_id(key_hash: str) -> object | None:
    if not key_hash:
        return None
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
            (key_hash,),
        )
        row = cur.fetchone()
        return row["id"] if row else None


def _find_service_binding_for_provision(raw_key: str) -> tuple[object, object]:
    """Accept a legacy token only when its live row is the exact reserved service binding.

    Replacement and steady-state keys remain ``tw_svc_`` tokens.  This lookup is
    deliberately provision-only so an existing legacy service credential can be
    captured as K0 and rotated without accepting a customer-owned key.
    """
    if not raw_key:
        raise ProvisionError("configured MCP gateway key is empty")
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT u.id AS user_id, k.id AS key_id, k.name, "
            + _INTERNAL_PROFILE_SELECT
            + " FROM users AS u "
            "JOIN api_keys AS k ON k.user_id = u.id "
            "WHERE u.email = %s AND k.key_hash = %s AND k.revoked_at IS NULL",
            (SERVICE_EMAIL, _key_hash(raw_key)),
        )
        row = cur.fetchone()
        if not (
            row is not None
            and row.get("name") == KEY_NAME
            and _is_exact_internal_profile(
                row,
                email=SERVICE_EMAIL,
                first_name="MCP Service",
                api_tier="mcp",
                roles=["user"],
            )
        ):
            raise ProvisionError(
                "configured MCP key lacks the exact reserved service DB binding"
            )
        return row["user_id"], row["key_id"]


def _insert_key(user_id: object, raw_key: str, key_id: object) -> object:
    explicit_id = _normalise_key_id(key_id, "planned replacement key id")
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO api_keys (id, user_id, name, key_hash, prefix) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (explicit_id, user_id, KEY_NAME, _key_hash(raw_key), raw_key[:12]),
        )
        inserted_id = _normalise_key_id(
            cur.fetchone()["id"], "inserted replacement key id"
        )
        if inserted_id != explicit_id:
            raise ProvisionError("database returned a different replacement key id")
        return inserted_id


def _revoke_key(key_id: object) -> None:
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (key_id,),
        )


def _revoke_other_keys(user_id: object, keep_id: object) -> None:
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE user_id = %s "
            "AND id <> %s AND revoked_at IS NULL",
            (user_id, keep_id),
        )


def _revoke_all_service_keys(user_id: object) -> None:
    """Revoke rows only when source, runtime, and state prove none is referenced."""
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )


def _assert_no_other_active_service_keys(user_id: object, keep_id: object) -> None:
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM api_keys WHERE user_id = %s AND id <> %s "
            "AND revoked_at IS NULL LIMIT 1",
            (user_id, keep_id),
        )
        if cur.fetchone() is not None:
            raise ProvisionError(
                "reserved MCP service identity has another active API key"
            )


def _assert_allowed_active_service_keys(
    user_id: object,
    keep_id: object,
    rotation_state: dict[str, object] | None,
) -> None:
    """Allow only K1, plus the exact state-bound K0 while rotation is pending."""
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, key_hash FROM api_keys WHERE user_id = %s "
            "AND id <> %s AND revoked_at IS NULL",
            (user_id, keep_id),
        )
        rows = cur.fetchall()
    if not rows:
        return
    if not (
        rotation_state is not None
        and rotation_state["status"] == "pending"
        and rotation_state["superseded_key_id"] is not None
        and rotation_state["superseded_key_hash"] is not None
        and len(rows) == 1
    ):
        raise ProvisionError(
            "reserved MCP service identity has an unauthorized active sibling"
        )
    keep = _normalise_key_id(keep_id, "configured service key id")
    if keep == rotation_state["replacement_key_id"]:
        expected_id = rotation_state["superseded_key_id"]
        expected_hash = rotation_state["superseded_key_hash"]
    elif keep == rotation_state["superseded_key_id"]:
        expected_id = rotation_state["replacement_key_id"]
        expected_hash = rotation_state["replacement_key_hash"]
    else:
        raise ProvisionError(
            "configured service key is not one of the pending state rows"
        )
    row = rows[0]
    if not (
        _normalise_key_id(row["id"], "active sibling key id") == expected_id
        and row["name"] == KEY_NAME
        and row["key_hash"] == expected_hash
    ):
        raise ProvisionError(
            "active MCP service sibling is not the exact pending superseded key"
        )


def _assert_no_active_service_keys(user_id: object) -> None:
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM api_keys WHERE user_id = %s AND revoked_at IS NULL LIMIT 1",
            (user_id,),
        )
        if cur.fetchone() is not None:
            raise ProvisionError(
                "reserved MCP service identity has an unbound active API key"
            )


def _find_or_create_verifier_user(*, create: bool) -> object | None:
    """Return only the exact reserved Pro probe identity; near matches fail."""
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "SELECT u.id, " + _INTERNAL_PROFILE_SELECT + " "
            "FROM users AS u WHERE u.email = %s FOR UPDATE",
            (VERIFIER_EMAIL,),
        )
        row = cur.fetchone()
        if row:
            if not _is_exact_internal_profile(
                row,
                email=VERIFIER_EMAIL,
                first_name="MCP Release Verifier",
                api_tier=VERIFIER_TIER,
                roles=["service_account"],
            ):
                raise ProvisionError(
                    "reserved verifier identity collides with a non-exact service account"
                )
            return row["id"]
        if not create:
            return None
        cur.execute(
            "INSERT INTO users "
            "(email, first_name, last_name, tier, legacy_wp_level, api_tier, roles, "
            "email_verified, workos_user_id, legacy_phpass_hash, api_key_hash, "
            "stripe_customer_id, stripe_subscription_id, stripe_subscription_status, "
            "trial_ends_at, reverse_trial_ends_at, navigator_mcp_first_connect_at, "
            "first_ai_score_viewed_at, last_login_at) "
            "VALUES (%s, %s, NULL, 'explorer', '1', %s, %s::jsonb, false, NULL, "
            "NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL) "
            "RETURNING id",
            (
                VERIFIER_EMAIL,
                "MCP Release Verifier",
                VERIFIER_TIER,
                json.dumps(["service_account"]),
            ),
        )
        return cur.fetchone()["id"]


def _insert_verifier_probe(user_id: object, key_name: str, raw_key: str) -> object:
    if _VERIFIER_PROBE_NAME_RE.fullmatch(key_name) is None:
        raise ProvisionError("refusing an invalid verifier probe marker")
    if not _VERIFIER_KEY_RE.fullmatch(raw_key):
        raise ProvisionError("refusing an invalid verifier probe key")
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO api_keys (user_id, name, key_hash, prefix) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, key_name, _key_hash(raw_key), raw_key[:16]),
        )
        return cur.fetchone()["id"]


def _verify_verifier_probe_binding(
    state: dict[str, object], *, require_active: bool
) -> str:
    state = _validate_verifier_state(state)
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT k.id, k.name, k.key_hash, k.revoked_at, "
            + _INTERNAL_PROFILE_SELECT
            + " FROM api_keys AS k "
            "JOIN users AS u ON u.id = k.user_id "
            "WHERE k.id = %s AND k.user_id = %s AND u.email = %s "
            "AND k.name = %s AND k.key_hash = %s",
            (
                state["key_id"],
                state["user_id"],
                VERIFIER_EMAIL,
                state["key_name"],
                state["key_hash"],
            ),
        )
        row = cur.fetchone()
    if not (
        row is not None
        and _normalise_key_id(row.get("id"), "verifier probe key id")
        == state["key_id"]
        and row.get("name") == state["key_name"]
        and row.get("key_hash") == state["key_hash"]
        and _is_exact_internal_profile(
            row,
            email=VERIFIER_EMAIL,
            first_name="MCP Release Verifier",
            api_tier=VERIFIER_TIER,
            roles=["service_account"],
        )
    ):
        raise ProvisionError(
            "verifier probe lacks the exact DB owner/name/hash binding"
        )
    status = "revoked" if row["revoked_at"] is not None else "active"
    if require_active and status != "active":
        raise ProvisionError("state-bound verifier probe is not active")
    return status


def _revoke_verifier_probe_binding(state: dict[str, object]) -> bool:
    """Idempotently revoke only the exact state-bound row."""
    state = _validate_verifier_state(state)
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "SELECT k.id, k.name, k.key_hash, k.revoked_at, "
            + _INTERNAL_PROFILE_SELECT
            + " FROM api_keys AS k JOIN users AS u ON u.id = k.user_id "
            "WHERE k.id = %s AND k.user_id = %s FOR UPDATE",
            (state["key_id"], state["user_id"]),
        )
        row = cur.fetchone()
        if row is None:
            return False
        if not (
            _normalise_key_id(row.get("id"), "verifier probe key id")
            == state["key_id"]
            and row.get("name") == state["key_name"]
            and row.get("key_hash") == state["key_hash"]
            and _is_exact_internal_profile(
                row,
                email=VERIFIER_EMAIL,
                first_name="MCP Release Verifier",
                api_tier=VERIFIER_TIER,
                roles=["service_account"],
            )
        ):
            raise ProvisionError(
                "state-bound verifier row lacks the exact reserved binding"
            )
        if row["revoked_at"] is not None:
            return False
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND user_id = %s "
            "AND name = %s AND key_hash = %s AND revoked_at IS NULL",
            (
                state["key_id"],
                state["user_id"],
                state["key_name"],
                state["key_hash"],
            ),
        )
        return True


def _active_verifier_rows(user_id: object) -> list[dict[str, object]]:
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, key_hash, revoked_at FROM api_keys "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )
        return list(cur.fetchall())


def _state_for_verifier_row(
    *,
    transaction_id: str,
    journal_sha256: str,
    user_id: object,
    key_id: object,
    key_hash: str,
    key_name: str,
) -> dict[str, object]:
    return _validate_verifier_state(
        {
            "version": 1,
            "transaction_id": transaction_id,
            "journal_sha256": journal_sha256,
            "user_id": _normalise_key_id(user_id, "verifier user id"),
            "key_id": _normalise_key_id(key_id, "verifier key id"),
            "key_hash": key_hash,
            "key_name": key_name,
        }
    )


def _revoke_legacy_verifier_row(user_id: object, row: dict[str, object]) -> bool:
    """Remove only the exact key name used by the superseded permanent design."""
    key_id = _normalise_key_id(row.get("id"), "legacy verifier key id")
    digest = row.get("key_hash")
    if not isinstance(digest, str) or not _KEY_HASH_RE.fullmatch(digest):
        raise ProvisionError("legacy verifier row has an invalid key hash")
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND user_id = %s "
            "AND name = %s AND key_hash = %s AND revoked_at IS NULL",
            (key_id, user_id, _LEGACY_VERIFIER_KEY_NAME, digest),
        )
    return True


def _purge_recognized_verifier_rows() -> int:
    """Purge exact marked rows; never issue an owner-wide UPDATE."""
    user_id = _find_or_create_verifier_user(create=False)
    if user_id is None:
        return 0
    rows = _active_verifier_rows(user_id)
    probes: list[dict[str, object]] = []
    legacy: list[dict[str, object]] = []
    unexpected_active_key = False
    for row in rows:
        name = row.get("name")
        digest = row.get("key_hash")
        if name == _LEGACY_VERIFIER_KEY_NAME:
            legacy.append(row)
            continue
        match = (
            _VERIFIER_PROBE_NAME_RE.fullmatch(name)
            if isinstance(name, str)
            else None
        )
        if match is None:
            unexpected_active_key = True
            continue
        if not isinstance(digest, str) or not _KEY_HASH_RE.fullmatch(digest):
            raise ProvisionError("marked verifier row has an invalid key hash")
        transaction_id = _canonical_uuid(
            match.group(1), "marked verifier transaction id"
        )
        probes.append(
            _state_for_verifier_row(
                transaction_id=transaction_id,
                journal_sha256="0" * 64,
                user_id=user_id,
                key_id=row.get("id"),
                key_hash=digest,
                key_name=name,
            )
        )
    for state in probes:
        _revoke_verifier_probe_binding(state)
    for row in legacy:
        _revoke_legacy_verifier_row(user_id, row)
    if unexpected_active_key:
        raise ProvisionError(
            "reserved verifier identity has an unrecognized active key"
        )
    return len(probes) + len(legacy)


def _validate_partial_service_rotation(
    source_key: str,
    runtime_key: str,
    state: dict[str, object] | None,
) -> None:
    """Accept only the write-order-safe K1(source)/K0(runtime) crash arrangement."""
    if not (
        state is not None
        and state["status"] == "pending"
        and state["superseded_key_id"] is not None
        and state["superseded_key_hash"] is not None
        and _SERVICE_KEY_RE.fullmatch(source_key)
        and _key_hash(source_key) == state["replacement_key_hash"]
        and _key_hash(runtime_key) == state["superseded_key_hash"]
    ):
        raise ProvisionError(
            "source and dedicated MCP environments disagree outside a safe pending rotation"
        )
    replacement_status = _bound_key_status(
        state["replacement_key_id"], state["replacement_key_hash"]
    )
    superseded_status = _bound_key_status(
        state["superseded_key_id"], state["superseded_key_hash"]
    )
    if replacement_status != "active" or superseded_status != "active":
        raise ProvisionError(
            "partial MCP rotation rows are not both active and state-bound"
        )


def _bound_key_status(key_id: object, key_hash: str) -> str:
    """Return state-row status only for the exact reserved service owner/name."""
    db = _gateway_dependencies()
    with db.cursor() as cur:
        cur.execute(
            "SELECT k.key_hash, k.revoked_at, k.name, " + _INTERNAL_PROFILE_SELECT + " "
            "FROM api_keys AS k "
            "JOIN users AS u ON u.id = k.user_id "
            "WHERE k.id = %s",
            (key_id,),
        )
        row = cur.fetchone()
        if row is None:
            return "missing"
        if not (
            row.get("name") == KEY_NAME
            and _is_exact_internal_profile(
                row,
                email=SERVICE_EMAIL,
                first_name="MCP Service",
                api_tier="mcp",
                roles=["user"],
            )
        ):
            raise ProvisionError(
                "state-bound API-key row lacks the exact reserved service binding"
            )
        if row["key_hash"] != key_hash:
            raise ProvisionError(
                "API-key row no longer matches root-owned rotation state"
            )
        return "revoked" if row["revoked_at"] is not None else "active"


def _revoke_bound_key(key_id: object, key_hash: str) -> None:
    """Idempotently revoke one state-bound row, never a caller-selected bare ID."""
    db = _gateway_dependencies()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "SELECT k.key_hash, k.revoked_at, k.name, " + _INTERNAL_PROFILE_SELECT + " "
            "FROM api_keys AS k "
            "JOIN users AS u ON u.id = k.user_id "
            "WHERE k.id = %s FOR UPDATE",
            (key_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ProvisionError(
                "state-bound API-key row lacks the exact reserved service binding"
            )
        if not (
            row.get("name") == KEY_NAME
            and _is_exact_internal_profile(
                row,
                email=SERVICE_EMAIL,
                first_name="MCP Service",
                api_tier="mcp",
                roles=["user"],
            )
        ):
            raise ProvisionError(
                "state-bound API-key row lacks the exact reserved service binding"
            )
        if row["key_hash"] != key_hash:
            raise ProvisionError(
                "API-key row no longer matches root-owned rotation state"
            )
        if row["revoked_at"] is None:
            cur.execute(
                "UPDATE api_keys SET revoked_at = now() "
                "WHERE id = %s AND key_hash = %s AND revoked_at IS NULL",
                (key_id, key_hash),
            )


def _revoke_exact_superseded_key(
    key_id: object, key_hash: str, replacement_key_id: object
) -> None:
    """Idempotently revoke only the old row cryptographically bound in state."""
    if str(key_id) == str(replacement_key_id):
        raise ProvisionError("rotation state aliases replacement and superseded rows")
    _revoke_bound_key(key_id, key_hash)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _gateway_get(raw_key: str, principal: str | None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {raw_key}", "Accept": "application/json"}
    if principal:
        headers["X-TW-Principal-WorkOS"] = principal
    request = urllib.request.Request(GATEWAY_ME_URL, headers=headers, method="GET")
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect
        ).open(request, timeout=10) as response:
            status, raw = response.status, response.read(1_048_577)
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read(1_048_577)
    except OSError as exc:
        raise ProvisionError(
            "local gateway service-key verification could not connect"
        ) from exc
    if len(raw) > 1_048_576:
        raise ProvisionError(
            "local gateway service-key verification returned too much data"
        )
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError(
            "local gateway service-key verification returned invalid JSON"
        ) from exc
    return status, body


def _verify_gateway_classification(raw_key: str) -> None:
    probes = (
        (None, "missing principal"),
        ("mcp_provision_probe_" + _secrets.token_hex(16), "unknown user"),
    )
    for principal, expected_message in probes:
        status, body = _gateway_get(raw_key, principal)
        error = body.get("error") if isinstance(body, dict) else None
        if not (
            status == 401
            and isinstance(error, dict)
            and error.get("code") == "unauthorized"
            and error.get("message") == expected_message
        ):
            raise ProvisionError(
                f"gateway rejected MCP service-key classification ({expected_message})"
            )


def _verify_release_verifier_key(raw_key: str) -> None:
    """Require the live gateway to classify the key as ordinary Pro capacity."""
    status, body = _gateway_get(raw_key, None)
    rate = body.get("rate") if isinstance(body, dict) else None
    per_minute = rate.get("per_minute") if isinstance(rate, dict) else None
    per_day = rate.get("per_day") if isinstance(rate, dict) else None
    admission_id = body.get("mcp_admission_id") if isinstance(body, dict) else None
    valid_numbers = (
        isinstance(per_minute, int)
        and not isinstance(per_minute, bool)
        and isinstance(per_day, int)
        and not isinstance(per_day, bool)
    )
    if not (
        status == 200
        and isinstance(body, dict)
        and body.get("tier") == VERIFIER_TIER
        and body.get("tier_name") == VERIFIER_TIER_NAME
        and isinstance(admission_id, str)
        and re.fullmatch(r"acct_[0-9a-f]{64}", admission_id) is not None
        and valid_numbers
        and per_minute >= VERIFIER_MIN_PER_MINUTE
        and per_day >= VERIFIER_MIN_PER_DAY
    ):
        raise ProvisionError(
            "gateway rejected the dedicated Pro release-verifier classification/capacity"
        )


def _assert_only_active_verifier_probe(state: dict[str, object]) -> None:
    rows = _active_verifier_rows(state["user_id"])
    if len(rows) != 1:
        raise ProvisionError(
            "reserved verifier identity does not have exactly one active probe"
        )
    row = rows[0]
    if not (
        _normalise_key_id(row.get("id"), "active verifier key id")
        == state["key_id"]
        and row.get("name") == state["key_name"]
        and row.get("key_hash") == state["key_hash"]
    ):
        raise ProvisionError("active verifier probe does not match durable state")


def _remove_probe_temporaries(directory: str) -> int:
    if not os.path.lexists(directory):
        return 0
    _inspect_controlled_directory(
        directory, private=True, label="verifier probe private directory"
    )
    removed = 0
    for name in sorted(os.listdir(directory)):
        if re.fullmatch(r"\.mcp-probe-[A-Za-z0-9_-]+", name) is None:
            continue
        removed += int(
            _unlink_private_file(
                os.path.join(directory, name),
                label="incomplete verifier probe temporary",
                missing_ok=False,
            )
        )
    return removed


def _remove_verifier_credential_source(
    transaction_id: str, credential_path: str
) -> bool:
    removed = _unlink_private_file(
        credential_path, label="verifier credential source", missing_ok=True
    )
    transaction_directory = os.path.dirname(credential_path)
    if os.path.lexists(transaction_directory):
        _inspect_controlled_directory(
            transaction_directory,
            private=True,
            label="verifier credential transaction directory",
        )
        _remove_probe_temporaries(transaction_directory)
        if os.listdir(transaction_directory):
            raise ProvisionError(
                "verifier credential transaction directory is not empty"
            )
        try:
            os.rmdir(transaction_directory)
            _fsync_directory(VERIFIER_CREDENTIAL_ROOT)
        except OSError as exc:
            raise ProvisionError(
                "cannot remove verifier credential transaction directory"
            ) from exc
    return removed


def _remove_verifier_state(state_path: str) -> bool:
    return _unlink_private_file(
        state_path, label="verifier probe state", missing_ok=True
    )


def _remove_legacy_verifier_file() -> bool:
    return _unlink_private_file(
        LEGACY_VERIFIER_ENV_PATH,
        label="superseded verifier credential file",
        missing_ok=True,
    )


def _revoke_transaction_verifier_rows(transaction_id: str) -> int:
    user_id = _find_or_create_verifier_user(create=False)
    if user_id is None:
        return 0
    key_name = _verifier_probe_name(transaction_id)
    count = 0
    for row in _active_verifier_rows(user_id):
        if row.get("name") != key_name:
            continue
        digest = row.get("key_hash")
        if not isinstance(digest, str) or not _KEY_HASH_RE.fullmatch(digest):
            raise ProvisionError("transaction verifier row has an invalid key hash")
        state = _state_for_verifier_row(
            transaction_id=transaction_id,
            journal_sha256="0" * 64,
            user_id=user_id,
            key_id=row.get("id"),
            key_hash=digest,
            key_name=key_name,
        )
        _revoke_verifier_probe_binding(state)
        count += 1
    return count


def _prepare_verifier_transaction_paths(
    transaction_id: str, state_path: str, credential_path: str
) -> None:
    _validate_verifier_paths(transaction_id, state_path, credential_path)
    _prepare_private_tree(VERIFIER_STATE_ROOT, label="verifier state root")
    _prepare_private_tree(
        VERIFIER_CREDENTIAL_ROOT, label="verifier credential root"
    )
    _prepare_private_tree(
        os.path.dirname(credential_path),
        label="verifier credential transaction directory",
    )
    _remove_probe_temporaries(VERIFIER_STATE_ROOT)
    _remove_probe_temporaries(os.path.dirname(credential_path))


def mint_verifier_probe(
    transaction_id: str,
    journal_manifest: str,
    state_path: str,
    credential_path: str,
) -> dict[str, object]:
    """Mint or safely resume one journal-bound sacrificial verifier probe."""
    _load_platform_settings()
    with _exclusive_lock(), _release_not_active():
        _require_root_for_verifier_lifecycle()
        transaction_id, state_path, credential_path = _validate_verifier_paths(
            transaction_id, state_path, credential_path
        )
        _reject_verifier_in_platform_secrets(SECRETS_PATH)
        # This check and fsync must precede every DB/filesystem probe mutation.
        journal_sha256 = _verify_durable_release_journal(
            transaction_id, journal_manifest
        )
        _prepare_verifier_transaction_paths(
            transaction_id, state_path, credential_path
        )
        _remove_legacy_verifier_file()

        state = _read_verifier_state(
            state_path, transaction_id=transaction_id, required=False
        )
        if state is not None:
            if state["journal_sha256"] != journal_sha256:
                raise ProvisionError(
                    "verifier probe state journal digest does not match"
                )
            if os.path.lexists(credential_path):
                raw_key = _read_verifier_key(credential_path, required=True)
                if not hmac.compare_digest(_key_hash(raw_key), str(state["key_hash"])):
                    raise ProvisionError(
                        "verifier credential source does not match durable state"
                    )
                status = _verify_verifier_probe_binding(
                    state, require_active=False
                )
                if status == "active":
                    _assert_only_active_verifier_probe(state)
                    _verify_release_verifier_key(raw_key)
                    return {
                        "action": "reused",
                        "transaction_id": transaction_id,
                        "user_id": state["user_id"],
                        "key_id": state["key_id"],
                        "journal_sha256": journal_sha256,
                    }
            _remove_verifier_credential_source(transaction_id, credential_path)
            _revoke_verifier_probe_binding(state)
            _remove_verifier_state(state_path)
        elif os.path.lexists(credential_path):
            # State is durably published before raw material by construction.
            # A source without state is unusable and must be destroyed.
            _remove_verifier_credential_source(transaction_id, credential_path)

        _purge_recognized_verifier_rows()
        user_id = _find_or_create_verifier_user(create=True)
        if user_id is None:  # pragma: no cover - defensive type narrowing
            raise ProvisionError("cannot create verifier probe identity")
        raw_key = "tw_live_" + _secrets.token_hex(16)
        key_name = _verifier_probe_name(transaction_id)
        key_id = _insert_verifier_probe(user_id, key_name, raw_key)
        state = _state_for_verifier_row(
            transaction_id=transaction_id,
            journal_sha256=journal_sha256,
            user_id=user_id,
            key_id=key_id,
            key_hash=_key_hash(raw_key),
            key_name=key_name,
        )
        # A hard crash here leaves a recognizable DB marker for startup purge.
        _after_verifier_key_insert()
        try:
            _write_verifier_state(state_path, state)
        except BaseException:
            _revoke_verifier_probe_binding(state)
            raise
        # A hard crash here leaves exact non-secret recovery state and no raw file.
        _after_verifier_state_fsync()
        try:
            _verify_verifier_probe_binding(state, require_active=True)
            _assert_only_active_verifier_probe(state)
            _verify_release_verifier_key(raw_key)
            _prepare_private_tree(
                os.path.dirname(credential_path),
                label="verifier credential transaction directory",
            )
            _write_verifier_key(credential_path, raw_key)
        except BaseException:
            _remove_verifier_credential_source(transaction_id, credential_path)
            _revoke_verifier_probe_binding(state)
            _remove_verifier_state(state_path)
            raise
        # A hard crash here is recovered by exact state-bound revoke/startup purge.
        _after_verifier_credential_fsync()
        return {
            "action": "minted",
            "transaction_id": transaction_id,
            "user_id": state["user_id"],
            "key_id": state["key_id"],
            "journal_sha256": journal_sha256,
        }


def revoke_verifier_probe(
    transaction_id: str, state_path: str, credential_path: str
) -> dict[str, object]:
    """Idempotently destroy raw material and revoke only its transaction rows."""
    _load_platform_settings()
    with _exclusive_lock(), _release_not_active():
        _require_root_for_verifier_lifecycle()
        transaction_id, state_path, credential_path = _validate_verifier_paths(
            transaction_id, state_path, credential_path
        )
        credential_removed = _remove_verifier_credential_source(
            transaction_id, credential_path
        )
        rows_revoked = 0
        try:
            state = _read_verifier_state(
                state_path, transaction_id=transaction_id, required=False
            )
        except ProvisionError:
            # Corrupt/tampered state remains as evidence, but the exact
            # transaction marker is independently sufficient to make the key
            # harmless before reporting the integrity failure.
            _revoke_transaction_verifier_rows(transaction_id)
            raise
        if state is not None:
            rows_revoked += int(_revoke_verifier_probe_binding(state))
            _remove_verifier_state(state_path)
        rows_revoked += _revoke_transaction_verifier_rows(transaction_id)
        return {
            "transaction_id": transaction_id,
            "credential_removed": credential_removed,
            "rows_revoked": rows_revoked,
        }


def _purge_credential_tree() -> int:
    if not os.path.lexists(VERIFIER_CREDENTIAL_ROOT):
        return 0
    _inspect_controlled_directory(
        VERIFIER_CREDENTIAL_ROOT, private=True, label="verifier credential root"
    )
    transaction_ids: list[str] = []
    for name in sorted(os.listdir(VERIFIER_CREDENTIAL_ROOT)):
        transaction_id = _canonical_uuid(name, "credential transaction directory")
        directory = os.path.join(VERIFIER_CREDENTIAL_ROOT, name)
        _inspect_controlled_directory(
            directory, private=True, label="verifier credential transaction directory"
        )
        unexpected = {
            entry
            for entry in os.listdir(directory)
            if entry != "verify-env"
            and re.fullmatch(r"\.mcp-probe-[A-Za-z0-9_-]+", entry) is None
        }
        if unexpected:
            raise ProvisionError("verifier credential directory has unexpected entries")
        transaction_ids.append(transaction_id)
    removed = 0
    for transaction_id in transaction_ids:
        removed += int(
            _remove_verifier_credential_source(
                transaction_id,
                _expected_verifier_credential_path(transaction_id),
            )
        )
    return removed


def _load_all_verifier_states() -> list[tuple[str, str, dict[str, object]]]:
    if not os.path.lexists(VERIFIER_STATE_ROOT):
        return []
    _inspect_controlled_directory(
        VERIFIER_STATE_ROOT, private=True, label="verifier state root"
    )
    _remove_probe_temporaries(VERIFIER_STATE_ROOT)
    states: list[tuple[str, str, dict[str, object]]] = []
    for name in sorted(os.listdir(VERIFIER_STATE_ROOT)):
        match = re.fullmatch(r"([0-9a-f-]{36})\.json", name)
        if match is None:
            raise ProvisionError("verifier state root has an unexpected entry")
        transaction_id = _canonical_uuid(match.group(1), "state filename transaction id")
        path = os.path.join(VERIFIER_STATE_ROOT, name)
        state = _read_verifier_state(
            path, transaction_id=transaction_id, required=True
        )
        if state is None:  # pragma: no cover - required=True
            raise ProvisionError("required verifier probe state is missing")
        states.append((transaction_id, path, state))
    return states


def purge_stale_verifier_probes() -> dict[str, object]:
    """Controller-start recovery for every recognizable stale probe artifact."""
    _load_platform_settings()
    with _exclusive_lock(), _release_not_active():
        _require_root_for_verifier_lifecycle()
        recovery_errors: list[str] = []
        try:
            credential_files_removed = _purge_credential_tree()
        except ProvisionError as exc:
            credential_files_removed = 0
            recovery_errors.append(str(exc))
        try:
            _remove_legacy_verifier_file()
        except ProvisionError as exc:
            recovery_errors.append(str(exc))
        # Marker metadata is independently sufficient for safe exact revoke.
        # Do this before parsing sidecars so a corrupt state file cannot keep a
        # raw-less but still active probe credential alive.
        try:
            rows_revoked = _purge_recognized_verifier_rows()
        except ProvisionError as exc:
            rows_revoked = 0
            recovery_errors.append(str(exc))
        try:
            states = _load_all_verifier_states()
        except ProvisionError as exc:
            states = []
            recovery_errors.append(str(exc))
        for _transaction_id, _path, state in states:
            try:
                rows_revoked += int(_revoke_verifier_probe_binding(state))
            except ProvisionError as exc:
                recovery_errors.append(str(exc))
        for _transaction_id, path, _state in states:
            try:
                _remove_verifier_state(path)
            except ProvisionError as exc:
                recovery_errors.append(str(exc))
        # A verifier token in the broad platform environment is an integrity
        # failure, but it must not become a kill switch for recovery.  Destroy
        # credential sources and revoke every recognizable marker/state-bound
        # row first, then report the leak fail-closed.  Mint still rejects the
        # same condition before making any mutation.
        try:
            _reject_verifier_in_platform_secrets(SECRETS_PATH)
        except ProvisionError as exc:
            recovery_errors.append(str(exc))
        if recovery_errors:
            raise ProvisionError(
                "stale verifier probe purge found integrity errors: "
                + "; ".join(recovery_errors)
            )
        return {
            "credential_files_removed": credential_files_removed,
            "state_files_removed": len(states),
            "rows_revoked": rows_revoked,
        }


def _find_exact_service_binding(raw_key: str) -> tuple[object, object]:
    if not _SERVICE_KEY_RE.fullmatch(raw_key):
        raise ProvisionError("configured MCP gateway key is not a service-key token")
    return _find_service_binding_for_provision(raw_key)


def _process_key(pid: int) -> str:
    try:
        entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError as exc:
        raise ProvisionError("cannot inspect the activated MCP process") from exc
    values = []
    for entry in entries:
        if entry.startswith(b"MCP_GATEWAY_KEY="):
            try:
                values.append(entry.split(b"=", 1)[1].decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise ProvisionError(
                    "activated MCP process has an invalid service key"
                ) from exc
    if len(values) != 1:
        raise ProvisionError(
            "activated MCP process must have exactly one MCP_GATEWAY_KEY"
        )
    return values[0]


# Dedicated-only release-candidate service credential flow.  These definitions
# intentionally replace the pre-RC dual-environment implementation above; no
# reachable command writes a newly minted key to the broad platform file.
def _exact_state_runtime_binding(
    state: dict[str, object], raw_key: str
) -> tuple[object, object]:
    if not _SERVICE_KEY_RE.fullmatch(raw_key):
        raise ProvisionError("dedicated MCP key is not a service-key token")
    user_id, key_id = _find_exact_service_binding(raw_key)
    if not (
        state["replacement_key_id"]
        == _normalise_key_id(key_id, "dedicated service key id")
        and state["replacement_key_hash"] == _key_hash(raw_key)
    ):
        raise ProvisionError(
            "dedicated MCP key does not match root-owned rotation state"
        )
    return user_id, key_id


def _legacy_binding(raw_key: str) -> tuple[object, str, str]:
    user_id, key_id = _find_service_binding_for_provision(raw_key)
    return (
        user_id,
        _normalise_key_id(key_id, "legacy service key id"),
        _key_hash(raw_key),
    )


def _state_binds_source(
    state: dict[str, object], legacy_key: str
) -> tuple[object | None, str | None, str]:
    if legacy_key:
        user_id, key_id, key_hash = _legacy_binding(legacy_key)
        if not (
            state.get("source_key_hash") == key_hash
            and state["superseded_key_id"] == key_id
            and state["superseded_key_hash"] == key_hash
        ):
            raise ProvisionError(
                "rotation state does not bind the restored legacy service key"
            )
        return user_id, key_id, key_hash
    if not (
        state.get("source_key_hash") == _ABSENT_SOURCE_HASH
        and state["superseded_key_id"] is None
        and state["superseded_key_hash"] is None
    ):
        raise ProvisionError("rotation state requires a missing legacy credential")
    return None, None, _ABSENT_SOURCE_HASH


def _discard_unreferenced_replacement(state: dict[str, object]) -> None:
    status = _bound_key_status(
        state["replacement_key_id"], state["replacement_key_hash"]
    )
    if status == "active":
        _revoke_bound_key(state["replacement_key_id"], state["replacement_key_hash"])
    _restore_rotation_state(None)


def check_service() -> dict[str, object]:
    """Check K1 using only dedicated storage; broad must contain no assignment."""
    broad_key = _load_platform_settings()
    if broad_key:
        raise ProvisionError(
            "MCP_GATEWAY_KEY must be absent from broad platform secrets"
        )
    with _exclusive_lock():
        raw_key = _read_runtime_key(required=True)
        state = _read_rotation_state(required=True)
        assert state is not None
        if state["status"] not in {"pending", "active"}:
            raise ProvisionError("dedicated MCP key is not in pending/active state")
        user_id, key_id = _exact_state_runtime_binding(state, raw_key)
        _assert_allowed_active_service_keys(user_id, key_id, state)
        _verify_gateway_classification(raw_key)
        return {"user_id": user_id, "key_id": key_id}


def provision() -> dict[str, object]:
    """Create or resume K1, persist it dedicated-only, then scrub broad K0."""
    broad_key = _load_platform_settings()
    with _exclusive_lock(), _release_not_active():
        runtime_key = _read_runtime_key(required=False)
        state = _read_rotation_state(required=False)

        if state is not None and state["status"] == "active" and not broad_key:
            user_id, key_id = _exact_state_runtime_binding(state, runtime_key)
            _assert_no_other_active_service_keys(user_id, key_id)
            _verify_gateway_classification(runtime_key)
            return {
                "action": "reused",
                "user_id": user_id,
                "key_id": key_id,
                "dedicated_env_synchronized": True,
                "cleanup_pending": False,
                "superseded_key_captured": False,
            }

        if state is not None and state["status"] == "pending" and runtime_key:
            runtime_hash = _key_hash(runtime_key)
            if runtime_hash == state["replacement_key_hash"]:
                user_id, key_id = _exact_state_runtime_binding(state, runtime_key)
                if broad_key:
                    legacy_user, legacy_id, legacy_hash = _legacy_binding(broad_key)
                    if not (
                        str(legacy_user) == str(user_id)
                        and state["superseded_key_id"] == legacy_id
                        and state["superseded_key_hash"] == legacy_hash
                        and state.get("source_key_hash") == legacy_hash
                    ):
                        raise ProvisionError("pending K1 does not bind broad legacy K0")
                _assert_allowed_active_service_keys(user_id, key_id, state)
                _verify_gateway_classification(runtime_key)
                if broad_key:
                    _remove_broad_service_assignments()
                    _after_broad_key_removal_fsync()
                return {
                    "action": "reused",
                    "user_id": user_id,
                    "key_id": key_id,
                    "dedicated_env_synchronized": True,
                    "cleanup_pending": True,
                    "superseded_key_captured": state["superseded_key_id"] is not None,
                }

        if state is not None and state["status"] in {"planned", "pending"}:
            _state_binds_source(state, broad_key)
            if runtime_key and runtime_key != broad_key:
                raise ProvisionError(
                    "lost-credential recovery found an unbound dedicated key"
                )
            _discard_unreferenced_replacement(state)
            state = None

        if state is not None and state["status"] == "active":
            if not broad_key:
                raise ProvisionError("active state requires its exact dedicated K1")
            legacy_user, legacy_id, legacy_hash = _legacy_binding(broad_key)
            if not (
                state["replacement_key_id"] == legacy_id
                and state["replacement_key_hash"] == legacy_hash
                and (not runtime_key or runtime_key == broad_key)
            ):
                raise ProvisionError(
                    "active state does not bind the configured legacy key"
                )
            user_id = legacy_user
        elif broad_key:
            user_id, legacy_id, legacy_hash = _legacy_binding(broad_key)
            if runtime_key and runtime_key != broad_key:
                raise ProvisionError("broad and dedicated legacy credentials disagree")
        else:
            if runtime_key:
                raise ProvisionError(
                    "dedicated MCP key exists without root-owned rotation state"
                )
            user_id, unexpected = _ensure_user_and_find_key("")
            if unexpected is not None:
                raise ProvisionError(
                    "unreferenced service key unexpectedly matched an empty credential"
                )
            _revoke_all_service_keys(user_id)
            _assert_no_active_service_keys(user_id)
            legacy_id = None
            legacy_hash = None

        raw_key = "tw_svc_" + _secrets.token_urlsafe(32)
        replacement_id = str(uuid.uuid4())
        replacement_hash = _key_hash(raw_key)
        source_hash = legacy_hash if broad_key else _ABSENT_SOURCE_HASH
        planned = {
            "version": 2,
            "status": "planned",
            "replacement_key_id": replacement_id,
            "replacement_key_hash": replacement_hash,
            "superseded_key_id": legacy_id if broad_key else None,
            "superseded_key_hash": legacy_hash if broad_key else None,
            "source_key_hash": source_hash,
        }
        _write_rotation_state(planned)
        _after_service_plan_fsync()
        _insert_key(user_id, raw_key, replacement_id)
        _after_service_key_insert()
        _verify_gateway_classification(raw_key)
        _before_service_pending_fsync()
        pending = dict(planned)
        pending["status"] = "pending"
        _write_rotation_state(pending)
        _after_rotation_state_fsync()
        _write_runtime_key(raw_key)
        _after_first_environment_fsync()
        if broad_key:
            _remove_broad_service_assignments()
        _after_broad_key_removal_fsync()
        return {
            "action": "rotated",
            "user_id": user_id,
            "key_id": replacement_id,
            "dedicated_env_synchronized": True,
            "cleanup_pending": True,
            "superseded_key_captured": legacy_id is not None,
        }


def abort() -> dict[str, object]:
    """Reconcile rollback after the controller restores pre-provision snapshots."""
    broad_key = _load_platform_settings()
    with _exclusive_lock(), _release_not_active():
        runtime_key = _read_runtime_key(required=False)
        state = _read_rotation_state(required=False)
        if state is not None and state["status"] == "active":
            if broad_key:
                raise ProvisionError(
                    "active MCP state requires an absent broad service credential"
                )
            if not runtime_key:
                raise ProvisionError(
                    "active MCP state requires its dedicated service credential"
                )
            user_id, key_id = _exact_state_runtime_binding(state, runtime_key)
            _assert_no_other_active_service_keys(user_id, key_id)
            _verify_gateway_classification(runtime_key)
            return {
                "action": "nothing-to-abort",
                "legacy_preserved": False,
                "user_id": user_id,
                "replacement_revoked": False,
            }
        if runtime_key and runtime_key != broad_key:
            raise ProvisionError("controller must restore dedicated K0 before abort")
        if state is None:
            user_id = None
            legacy_id = None
            if broad_key:
                user_id, legacy_id, _legacy_hash = _legacy_binding(broad_key)
            return {
                "action": "nothing-to-abort",
                "legacy_preserved": legacy_id is not None,
                "user_id": user_id,
                "replacement_revoked": False,
            }
        if state["status"] not in {"planned", "pending"}:
            raise ProvisionError("only planned/pending rotation state can be aborted")
        user_id, legacy_id, _legacy_hash = _state_binds_source(state, broad_key)
        _discard_unreferenced_replacement(state)
        return {
            "action": "aborted",
            "legacy_preserved": legacy_id is not None,
            "user_id": user_id,
            "replacement_revoked": True,
        }


def finalize(pid: int) -> dict[str, object]:
    """Prove the activated PID uses dedicated K1, then revoke K0 and siblings."""
    broad_key = _load_platform_settings()
    if broad_key:
        raise ProvisionError(
            "MCP_GATEWAY_KEY must be absent from broad platform secrets"
        )
    with _exclusive_lock():
        state = _read_rotation_state(required=True)
        assert state is not None
        if state["status"] not in {"pending", "active"}:
            raise ProvisionError("activated MCP key is not in pending/active state")
        raw_key = _read_runtime_key(required=True)
        if _process_key(pid) != raw_key:
            raise ProvisionError("activated MCP process does not use dedicated K1")
        user_id, key_id = _exact_state_runtime_binding(state, raw_key)
        _verify_gateway_classification(raw_key)
        replacement_id = _normalise_key_id(key_id, "activated replacement key id")
        finalized = (
            state["status"] == "pending" and state["superseded_key_id"] is not None
        )
        if finalized:
            _revoke_exact_superseded_key(
                state["superseded_key_id"],
                state["superseded_key_hash"],
                replacement_id,
            )
        _revoke_other_keys(user_id, key_id)
        _assert_no_other_active_service_keys(user_id, key_id)
        active = {
            "version": 2,
            "status": "active",
            "replacement_key_id": replacement_id,
            "replacement_key_hash": _key_hash(raw_key),
            "superseded_key_id": None,
            "superseded_key_hash": None,
            "source_key_hash": state.get("source_key_hash", _ABSENT_SOURCE_HASH),
        }
        _write_rotation_state(active)
        _after_rotation_state_fsync()
        return {
            "user_id": user_id,
            "key_id": key_id,
            "exact_superseded_key_finalized": finalized,
        }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--finalize", action="store_true")
    action.add_argument("--abort", action="store_true")
    action.add_argument("--mint-verifier-probe", action="store_true")
    action.add_argument("--revoke-verifier-probe", action="store_true")
    action.add_argument("--purge-stale-verifier-probes", action="store_true")
    action.add_argument("--check-service", action="store_true")
    action.add_argument("--check-runtime-dependencies", action="store_true")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--transaction-id")
    parser.add_argument("--journal-manifest")
    parser.add_argument("--state-path")
    parser.add_argument("--credential-path")
    args = parser.parse_args(argv)
    try:
        probe_values = (
            args.transaction_id,
            args.journal_manifest,
            args.state_path,
            args.credential_path,
        )
        if args.finalize:
            if not args.pid or args.pid < 2:
                raise ProvisionError("--finalize requires the activated MCP --pid")
            if any(probe_values):
                raise ProvisionError("verifier arguments require a verifier action")
            result = finalize(args.pid)
        elif args.abort:
            if args.pid is not None:
                raise ProvisionError("--pid is valid only with --finalize")
            if any(probe_values):
                raise ProvisionError("unexpected arguments for --abort")
            result = abort()
        elif args.mint_verifier_probe:
            if args.pid is not None:
                raise ProvisionError("--pid is valid only with --finalize")
            if not all(probe_values):
                raise ProvisionError(
                    "--mint-verifier-probe requires transaction, journal, state, and credential paths"
                )
            result = mint_verifier_probe(
                args.transaction_id,
                args.journal_manifest,
                args.state_path,
                args.credential_path,
            )
        elif args.revoke_verifier_probe:
            if args.pid is not None:
                raise ProvisionError("--pid is valid only with --finalize")
            if not (
                args.transaction_id
                and args.state_path
                and args.credential_path
                and args.journal_manifest is None
            ):
                raise ProvisionError(
                    "--revoke-verifier-probe requires transaction, state, and credential paths only"
                )
            result = revoke_verifier_probe(
                args.transaction_id, args.state_path, args.credential_path
            )
        elif args.purge_stale_verifier_probes:
            if args.pid is not None or any(probe_values):
                raise ProvisionError(
                    "--purge-stale-verifier-probes takes no transaction arguments"
                )
            result = purge_stale_verifier_probes()
        elif args.check_service:
            if args.pid is not None or any(probe_values):
                raise ProvisionError("unexpected arguments for --check-service")
            result = check_service()
        elif args.check_runtime_dependencies:
            if args.pid is not None or any(probe_values):
                raise ProvisionError(
                    "unexpected arguments for --check-runtime-dependencies"
                )
            result = check_runtime_dependencies()
        else:
            if args.pid is not None or any(probe_values):
                raise ProvisionError("unexpected arguments for MCP key provision")
            result = provision()
    except ProvisionError as exc:
        raise SystemExit(f"MCP key provisioning failed: {exc}") from exc
    if args.finalize:
        print("PASS: activated MCP service key verified; superseded key rows revoked")
        return
    if args.abort:
        print("PASS: pending MCP service-key rotation reconciled for rollback")
        return
    if args.mint_verifier_probe:
        print("PASS: transaction-scoped Pro MCP verifier probe is ready")
        print("  action                  : %s" % result["action"])
        print("  transaction_id          : %s" % result["transaction_id"])
        print("  verifier user_id        : %s" % result["user_id"])
        print("  api_key id              : %s" % result["key_id"])
        return
    if args.revoke_verifier_probe:
        print("PASS: transaction-scoped MCP verifier probe revoked")
        print("  transaction_id          : %s" % result["transaction_id"])
        print("  rows revoked            : %s" % result["rows_revoked"])
        return
    if args.purge_stale_verifier_probes:
        print("PASS: stale MCP verifier probes purged")
        print("  rows revoked            : %s" % result["rows_revoked"])
        print("  state files removed     : %s" % result["state_files_removed"])
        print(
            "  credential files removed: %s"
            % result["credential_files_removed"]
        )
        return
    if args.check_service:
        print(
            "PASS: MCP service file, exact DB/state binding, and live classification verified"
        )
        print("  service user_id         : %s" % result["user_id"])
        print("  api_key id              : %s" % result["key_id"])
        return
    if args.check_runtime_dependencies:
        print("PASS: sealed MCP provision runtime dependencies imported without I/O")
        print("  db adapter              : %s" % result["db_adapter"])
        print("  driver file             : %s" % result["driver_file"])
        print("  psycopg2                : %s" % result["psycopg2_version"])
        return
    print("MCP service key provisioned safely")
    print("  action                  : %s" % result["action"])
    print("  service user_id         : %s" % result["user_id"])
    print("  api_key id              : %s" % result["key_id"])
    print(
        "  dedicated env synchronized: %s"
        % (
            "yes"
            if result["dedicated_env_synchronized"]
            else "not present (deploy will create it)"
        )
    )
    print("  old-key cleanup         : deferred until successful MCP activation")
    print("NEXT: run the immutable MCP deploy; it verifies activation before cleanup.")


if __name__ == "__main__":
    main()
