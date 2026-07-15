#!/usr/bin/env python3
"""Build and verify the MCP service's least-privilege runtime environment.

The platform secrets file is an input to deployment only.  The internet-facing
MCP process receives the small, explicit allowlist emitted by this program.
Secret values are never printed.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import shlex
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


RUNTIME_KEYS = (
    "API_BASE_URL",
    "TW2_MCP_HOST",
    "TW2_MCP_PORT",
    "TW2_MCP_TRANSPORT",
    "WORKOS_AUTHKIT_DOMAIN",
    "TW2_MCP_PUBLIC_URL",
    "TW2_MCP_PUBLIC_HOST",
    "MCP_GATEWAY_KEY",
)
API_RUNTIME_KEYS = (
    "POSTGRES_DSN",
    "API_KEY_HMAC_SECRET",
    "TW2_APPSERVER_URL",
    "SERVICE_API_KEY",
    "TW2_DEMO_API_KEY",
    "REDIS_HOST",
    "REDIS_PORT",
    "API_REDIS_DB",
    "TW2_PUBLIC_HOST",
    "TW2_ENV",
    "API_CORS_ORIGINS",
    "TW2_API_PRICING_LIVE",
)
API_SOURCE_KEYS = frozenset(API_RUNTIME_KEYS) | {
    "APPSERVER_JWT_SECRET",
    "APPSERVER_URL",
}
SOURCE_KEYS = frozenset((
    "API_BASE_URL", "TW2_MCP_HOST", "TW2_MCP_PORT", "TW2_MCP_TRANSPORT",
    "WORKOS_AUTHKIT_DOMAIN", "TW2_MCP_PUBLIC_URL", "TW2_MCP_PUBLIC_HOST",
    "TW_MCP_SMOKE_WORKOS_SUB", "TW_MCP_SMOKE_EXPECT_TIER",
    "TW2_PUBLIC_HOST", "TW2_API_PUBLIC_HOST", "TW2_DEVELOPERS_PUBLIC_HOST",
))
REQUIRED_SOURCE_KEYS = frozenset(
    ("WORKOS_AUTHKIT_DOMAIN", "TW2_MCP_PUBLIC_URL")
)
REQUIRED_RUNTIME_KEYS = REQUIRED_SOURCE_KEYS | {"MCP_GATEWAY_KEY"}
DEFAULTS = {
    "API_BASE_URL": "http://127.0.0.1:8088/v1",
    "TW2_MCP_HOST": "127.0.0.1",
    "TW2_MCP_PORT": "9090",
    "TW2_MCP_TRANSPORT": "streamable-http",
}
_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$"
)
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SERVICE_KEY_RE = re.compile(r"^tw_svc_[A-Za-z0-9_-]{43}$")
_VERIFIER_KEY_RE = re.compile(r"^tw_live_[0-9a-f]{32}$")
_VERIFIER_ASSIGNMENT_RE = re.compile(r"^\s*TW_MCP_VERIFY_TOKEN\s*=(.*)$")
_WORKOS_SUB_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@+\[\]-]+$")
VERIFIER_TIER = "pro"
VERIFIER_TIER_NAME = "Pro"
VERIFIER_MIN_PER_MINUTE = 120
VERIFIER_MIN_PER_DAY = 5_000


class ConfigError(ValueError):
    pass


def _decode_value(raw: str, *, path: Path, line_number: int) -> str:
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        values = list(lexer)
    except ValueError as exc:
        raise ConfigError(f"{path}:{line_number}: malformed assignment") from exc
    if len(values) != 1:
        raise ConfigError(f"{path}:{line_number}: assignment must contain one value")
    value = values[0]
    if any(character in value for character in ("\x00", "\r", "\n", "`", "$")):
        raise ConfigError(f"{path}:{line_number}: unsafe assignment value")
    return value


def read_env(path: str | Path, *, allowed: frozenset[str]) -> dict[str, str]:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"cannot read {source}") from exc
    found: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT_RE.match(line)
        if not match:
            if allowed == frozenset(RUNTIME_KEYS):
                raise ConfigError(f"{source}:{number}: invalid environment line")
            continue
        key, raw = match.groups()
        if allowed == SOURCE_KEYS and key == "TW_MCP_VERIFY_TOKEN":
            raise ConfigError(
                "TW_MCP_VERIFY_TOKEN must not be stored in the platform secrets file"
            )
        if key not in allowed:
            if allowed == frozenset(RUNTIME_KEYS):
                raise ConfigError(f"{source}:{number}: runtime key {key!r} is not allowed")
            continue
        if key in found:
            raise ConfigError(f"{source}: duplicate assignment for {key}")
        found[key] = _decode_value(raw, path=source, line_number=number)
    return found


def read_platform_assignments(
    path: str | Path, *, allowed: frozenset[str] | None = None
) -> dict[str, str]:
    """Parse relevant platform assignments as data, without eval or expansion."""
    source = Path(path)
    try:
        raw_source = source.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read {source}") from exc
    if len(raw_source) > 2 * 1024 * 1024:
        raise ConfigError(f"{source} is oversized")
    try:
        lines = raw_source.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{source} is not valid UTF-8") from exc
    found: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT_RE.fullmatch(line)
        if match is None:
            if allowed is None:
                raise ConfigError(f"{source}:{number}: malformed API environment line")
            continue
        key, raw = match.groups()
        if allowed is not None and key not in allowed:
            continue
        if key in found:
            raise ConfigError(f"{source}: duplicate assignment for {key}")
        found[key] = _decode_value(raw, path=source, line_number=number)
        if len(found[key].encode("utf-8")) > 128 * 1024:
            raise ConfigError(f"{source}:{number}: assignment value is oversized")
    return found


def _normalise_api_runtime(values: dict[str, str], *, source: bool) -> dict[str, str]:
    if source:
        hmac_secret = values.get("API_KEY_HMAC_SECRET") or values.get(
            "APPSERVER_JWT_SECRET", ""
        )
        appserver_url = (
            values.get("TW2_APPSERVER_URL")
            or values.get("APPSERVER_URL")
            or "http://127.0.0.1:5000"
        )
        environment = values.get("TW2_ENV") or "dev"
        if environment not in {"dev", "staging", "prod"}:
            raise ConfigError("TW2_ENV must be dev, staging, or prod")
        public_host = values.get("TW2_PUBLIC_HOST", "")
        if not public_host and environment != "dev":
            raise ConfigError("TW2_PUBLIC_HOST is required outside dev")
        pricing = values.get("TW2_API_PRICING_LIVE", "").strip().lower()
        if pricing in {"1", "true", "yes"}:
            pricing = "true"
        elif pricing in {"", "0", "false", "no"}:
            pricing = "false"
        else:
            raise ConfigError("TW2_API_PRICING_LIVE must be a canonical boolean")
        resolved = {
            "POSTGRES_DSN": values.get("POSTGRES_DSN", ""),
            "API_KEY_HMAC_SECRET": hmac_secret,
            "TW2_APPSERVER_URL": appserver_url,
            "SERVICE_API_KEY": values.get("SERVICE_API_KEY", ""),
            "TW2_DEMO_API_KEY": values.get("TW2_DEMO_API_KEY") or "tw_demo_explore",
            "REDIS_HOST": values.get("REDIS_HOST") or "127.0.0.1",
            "REDIS_PORT": values.get("REDIS_PORT") or "6379",
            "API_REDIS_DB": values.get("API_REDIS_DB") or "4",
            "TW2_PUBLIC_HOST": public_host or "tw2-dev.trxstat.com",
            "TW2_ENV": environment,
            "API_CORS_ORIGINS": values.get("API_CORS_ORIGINS", ""),
            "TW2_API_PRICING_LIVE": pricing,
        }
    else:
        if set(values) != set(API_RUNTIME_KEYS):
            missing = sorted(set(API_RUNTIME_KEYS) - set(values))
            extra = sorted(set(values) - set(API_RUNTIME_KEYS))
            raise ConfigError(
                f"API runtime key set is not exact; missing={missing}, extra={extra}"
            )
        resolved = dict(values)
        if resolved["TW2_ENV"] not in {"dev", "staging", "prod"}:
            raise ConfigError("TW2_ENV must be dev, staging, or prod")
        if resolved["TW2_API_PRICING_LIVE"] not in {"true", "false"}:
            raise ConfigError("TW2_API_PRICING_LIVE must be true or false")
    for key in ("POSTGRES_DSN", "API_KEY_HMAC_SECRET", "SERVICE_API_KEY"):
        if not resolved[key]:
            raise ConfigError(f"{key} is required for the API gateway runtime")
    try:
        parsed_appserver = urlsplit(resolved["TW2_APPSERVER_URL"])
    except ValueError as exc:
        raise ConfigError("TW2_APPSERVER_URL is invalid") from exc
    if (
        parsed_appserver.scheme not in {"http", "https"}
        or not parsed_appserver.hostname
        or parsed_appserver.username is not None
        or parsed_appserver.password is not None
        or parsed_appserver.query
        or parsed_appserver.fragment
    ):
        raise ConfigError("TW2_APPSERVER_URL must be an absolute credential-free HTTP(S) URL")
    for key, minimum, maximum in (("REDIS_PORT", 1, 65535), ("API_REDIS_DB", 0, 1024)):
        try:
            number = int(resolved[key], 10)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer") from exc
        if not minimum <= number <= maximum:
            raise ConfigError(f"{key} is outside its permitted range")
        resolved[key] = str(number)
    if any(character in resolved["REDIS_HOST"] for character in "\x00\r\n/\\"):
        raise ConfigError("REDIS_HOST is invalid")
    resolved["TW2_PUBLIC_HOST"] = _dns_host(
        resolved["TW2_PUBLIC_HOST"], name="TW2_PUBLIC_HOST"
    )
    return {key: resolved[key] for key in API_RUNTIME_KEYS}


def _api_runtime_payload(values: dict[str, str]) -> bytes:
    lines = [
        "# Generated by TradeWave paired release tooling; exact gateway allowlist."
    ]
    lines.extend(f"{key}={shlex.quote(values[key])}" for key in API_RUNTIME_KEYS)
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_api(source: str, output: str) -> None:
    values = read_platform_assignments(source, allowed=API_SOURCE_KEYS)
    runtime = _normalise_api_runtime(values, source=True)
    target = os.path.abspath(output)
    if output != target or target != "/etc/tradewave/apiserver.env":
        raise ConfigError("API runtime output path is not the fixed dedicated path")

    _publish_api_runtime(runtime, target)


def _publish_api_runtime(runtime: dict[str, str], target: str) -> None:
    """Atomically publish an already-normalized API allowlist.

    ``render_api`` owns the fixed-path authority check. Keeping the filesystem
    transaction separate makes every write/fsync/replace seam executable in
    isolation without tests ever touching the host's real /etc/tradewave.
    """
    parent, basename = os.path.split(target)
    directory_fd = os.open(
        parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = f".{basename}.tmp-{secrets.token_hex(16)}"
    try:
        parent_metadata = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_uid != 0
            or parent_metadata.st_mode & 0o022
        ):
            raise ConfigError("API runtime environment parent is not root-controlled")
        try:
            metadata = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_gid != 0
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                raise ConfigError("existing API runtime environment metadata is unsafe")
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            os.fchown(fd, 0, 0)
            os.fchmod(fd, 0o600)
            payload = memoryview(_api_runtime_payload(runtime))
            while payload:
                written = os.write(fd, payload)
                if written <= 0:
                    raise OSError("short API runtime environment write")
                payload = payload[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, basename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except OSError as exc:
        raise ConfigError("could not atomically publish API runtime environment") from exc
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def validate_api(path: str) -> dict[str, str]:
    target = Path(path)
    metadata = target.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise ConfigError("API runtime environment must be root:root mode 0600")
    values = read_platform_assignments(path)
    return _normalise_api_runtime(values, source=False)


def reject_broad_service_key(path: str | Path) -> None:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"cannot read {source}") from exc
    for number, line in enumerate(lines, 1):
        match = _ASSIGNMENT_RE.match(line)
        if match and match.group(1) == "MCP_GATEWAY_KEY":
            raise ConfigError(
                f"{source}:{number}: MCP_GATEWAY_KEY is forbidden in the platform secrets file"
            )


def read_dedicated_runtime(path: str | Path) -> dict[str, str]:
    source = Path(path)
    if not source.is_absolute():
        raise ConfigError("dedicated MCP environment path must be absolute")
    directory, basename = os.path.split(str(source))
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_fd = os.open(directory, directory_flags)
    except OSError as exc:
        raise ConfigError("cannot open dedicated MCP environment parent") from exc
    try:
        parent = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != 0
            or parent.st_mode & 0o022
        ):
            raise ConfigError("dedicated MCP environment parent is not root-controlled")
        descriptor = os.open(
            basename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_gid != 0
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or metadata.st_size > 64 * 1024
            ):
                raise ConfigError(
                    "dedicated MCP environment must be single-link root:root mode 0600"
                )
            raw = b""
            while len(raw) <= 64 * 1024:
                chunk = os.read(descriptor, 64 * 1024 + 1 - len(raw))
                if not chunk:
                    break
                raw += chunk
            if len(raw) > 64 * 1024:
                raise ConfigError("dedicated MCP environment is too large")
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ConfigError("cannot read dedicated MCP environment") from exc
    finally:
        os.close(directory_fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("dedicated MCP environment is not valid UTF-8") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT_RE.fullmatch(line)
        if not match or match.group(1) not in RUNTIME_KEYS:
            raise ConfigError(
                f"{source}:{number}: dedicated MCP environment has a forbidden line"
            )
        key, encoded = match.groups()
        if key in values:
            raise ConfigError(f"{source}: duplicate assignment for {key}")
        values[key] = _decode_value(encoded, path=source, line_number=number)
    key = values.get("MCP_GATEWAY_KEY", "")
    if not _SERVICE_KEY_RE.fullmatch(key):
        raise ConfigError("dedicated MCP environment lacks one valid MCP_GATEWAY_KEY")
    return values


def _parse_verifier_env(raw: bytes, source: Path) -> str:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigError("dedicated verifier environment is not valid UTF-8") from exc
    values: list[str] = []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _VERIFIER_ASSIGNMENT_RE.fullmatch(line)
        if not match:
            raise ConfigError(
                "dedicated verifier environment may contain only TW_MCP_VERIFY_TOKEN"
            )
        values.append(_decode_value(match.group(1), path=source, line_number=number))
    if len(values) != 1:
        raise ConfigError(
            "dedicated verifier environment must contain exactly one TW_MCP_VERIFY_TOKEN"
        )
    if not _VERIFIER_KEY_RE.fullmatch(values[0]):
        raise ConfigError("dedicated verifier token is not a regular tw_live_ API key")
    return values[0]


def read_verifier_env(path: str | Path) -> str:
    """Read the one root-only release credential with no broad-env fallback."""
    source = Path(path)
    if not source.is_absolute():
        raise ConfigError("verifier environment path must be absolute")
    directory, basename = os.path.split(str(source))
    if not basename:
        raise ConfigError("verifier environment path has no filename")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_descriptor = os.open(directory, directory_flags)
    except OSError as exc:
        raise ConfigError("cannot open dedicated verifier environment parent") from exc
    try:
        directory_metadata = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_metadata.st_mode):
            raise ConfigError("dedicated verifier environment parent is not a directory")
        if directory_metadata.st_uid != 0 or directory_metadata.st_mode & 0o022:
            raise ConfigError(
                "dedicated verifier environment parent must be root-controlled"
            )
    except BaseException:
        os.close(directory_descriptor)
        raise
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(basename, flags, dir_fd=directory_descriptor)
    except FileNotFoundError as exc:
        os.close(directory_descriptor)
        raise ConfigError("dedicated verifier environment is missing") from exc
    except OSError as exc:
        os.close(directory_descriptor)
        raise ConfigError("cannot open dedicated verifier environment") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ConfigError("dedicated verifier environment must be a regular file")
        if metadata.st_uid != 0 or metadata.st_gid != 0:
            raise ConfigError("dedicated verifier environment must be owned by root:root")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ConfigError("dedicated verifier environment must have mode 0600")
        raw = b""
        while len(raw) <= 8192:
            chunk = os.read(descriptor, 8193 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > 8192:
            raise ConfigError("dedicated verifier environment is too large")
    finally:
        os.close(descriptor)
        os.close(directory_descriptor)
    return _parse_verifier_env(raw, source)


def _dns_host(value: str, *, name: str) -> str:
    if not value or value != value.strip() or value.endswith("."):
        raise ConfigError(f"{name} must be a bare canonical DNS hostname")
    try:
        host = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ConfigError(f"{name} is not a valid DNS hostname") from exc
    if len(host) > 253 or any(not _DNS_LABEL_RE.fullmatch(part) for part in host.split(".")):
        raise ConfigError(f"{name} is not a valid DNS hostname")
    return host


def _https_origin(value: str, *, name: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ConfigError(f"{name} is invalid") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(f"{name} must be a canonical HTTPS origin")
    host = _dns_host(parsed.hostname, name=name)
    return f"https://{host}", host


def _api_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        address = ipaddress.ip_address(parsed.hostname or "")
    except (ValueError, TypeError) as exc:
        raise ConfigError("API_BASE_URL must be a loopback HTTP /v1 URL") from exc
    if (
        parsed.scheme.lower() != "http"
        or not address.is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or not (1 <= port <= 65535)
        or parsed.path.rstrip("/") != "/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError("API_BASE_URL must be a loopback HTTP /v1 URL")
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"http://{host}:{port}/v1"


def normalise_runtime(values: dict[str, str], *, resolved_public_host: str | None) -> dict[str, str]:
    missing = sorted(REQUIRED_RUNTIME_KEYS - values.keys())
    if missing:
        raise ConfigError(f"source configuration is missing required keys: {', '.join(missing)}")

    result = {key: values.get(key, default) for key, default in DEFAULTS.items()}
    workos_origin, _ = _https_origin(
        values["WORKOS_AUTHKIT_DOMAIN"], name="WORKOS_AUTHKIT_DOMAIN"
    )
    public_origin, public_host = _https_origin(
        values["TW2_MCP_PUBLIC_URL"], name="TW2_MCP_PUBLIC_URL"
    )
    resolved = _dns_host(resolved_public_host or values.get("TW2_MCP_PUBLIC_HOST", ""),
                         name="TW2_MCP_PUBLIC_HOST")
    explicit = values.get("TW2_MCP_PUBLIC_HOST")
    if explicit and _dns_host(explicit, name="TW2_MCP_PUBLIC_HOST") != resolved:
        raise ConfigError("configured and resolved TW2_MCP_PUBLIC_HOST values disagree")
    if public_host != resolved:
        raise ConfigError("TW2_MCP_PUBLIC_URL and TW2_MCP_PUBLIC_HOST values disagree")

    result.update(
        WORKOS_AUTHKIT_DOMAIN=workos_origin,
        TW2_MCP_PUBLIC_URL=public_origin,
        TW2_MCP_PUBLIC_HOST=resolved,
        MCP_GATEWAY_KEY=values["MCP_GATEWAY_KEY"],
    )
    result["API_BASE_URL"] = _api_base_url(result["API_BASE_URL"])
    try:
        bind_address = ipaddress.ip_address(result["TW2_MCP_HOST"])
    except ValueError as exc:
        raise ConfigError("TW2_MCP_HOST must be a loopback IP address") from exc
    if not bind_address.is_loopback:
        raise ConfigError("TW2_MCP_HOST must be a loopback IP address")
    result["TW2_MCP_HOST"] = bind_address.compressed
    try:
        port = int(result["TW2_MCP_PORT"], 10)
    except ValueError as exc:
        raise ConfigError("TW2_MCP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("TW2_MCP_PORT must be between 1 and 65535")
    result["TW2_MCP_PORT"] = str(port)
    if result["TW2_MCP_TRANSPORT"] != "streamable-http":
        raise ConfigError("TW2_MCP_TRANSPORT must be streamable-http")
    if not _SERVICE_KEY_RE.fullmatch(result["MCP_GATEWAY_KEY"]):
        raise ConfigError("MCP_GATEWAY_KEY is absent or is not a service-key token")
    for key, value in result.items():
        if not value or not _SAFE_VALUE_RE.fullmatch(value):
            raise ConfigError(f"{key} cannot be represented safely in EnvironmentFile syntax")
    return {key: result[key] for key in RUNTIME_KEYS}


def render(source: str, dedicated: str, output: str, resolved_public_host: str) -> None:
    reject_broad_service_key(source)
    values = read_env(source, allowed=SOURCE_KEYS)
    dedicated_values = read_dedicated_runtime(dedicated)
    values["MCP_GATEWAY_KEY"] = dedicated_values["MCP_GATEWAY_KEY"]
    runtime = normalise_runtime(values, resolved_public_host=resolved_public_host)
    target = Path(output)
    if target.exists():
        raise ConfigError(f"refusing to replace existing render target: {target}")
    old_umask = os.umask(0o177)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("# Generated by TradeWave MCP release tooling; do not add platform secrets.\n")
            for key in RUNTIME_KEYS:
                handle.write(f"{key}={runtime[key]}\n")
    finally:
        os.umask(old_umask)


def validate(path: str) -> dict[str, str]:
    values = read_env(path, allowed=frozenset(RUNTIME_KEYS))
    missing = sorted(set(RUNTIME_KEYS) - values.keys())
    if missing:
        raise ConfigError(f"runtime environment is missing keys: {', '.join(missing)}")
    return normalise_runtime(values, resolved_public_host=values["TW2_MCP_PUBLIC_HOST"])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _gateway_get(url: str, key: str, principal: str | None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if principal is not None:
        headers["X-TW-Principal-WorkOS"] = principal
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            status = response.status
            raw = response.read(1_048_577)
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read(1_048_577)
    except OSError as exc:
        raise ConfigError("local gateway key preflight could not connect") from exc
    if len(raw) > 1_048_576:
        raise ConfigError("local gateway key preflight returned an oversized body")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError("local gateway key preflight returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise ConfigError("local gateway key preflight returned an invalid payload")
    return status, body


def _require_error(result: tuple[int, dict], message: str) -> None:
    status, body = result
    error = body.get("error") if isinstance(body, dict) else None
    if not (
        status == 401
        and isinstance(error, dict)
        and error.get("code") == "unauthorized"
        and error.get("message") == message
    ):
        raise ConfigError(f"MCP gateway service-key classification failed ({message})")


def check_gateway_key(runtime_path: str, source_path: str | None) -> bool:
    runtime = validate(runtime_path)
    url = runtime["API_BASE_URL"].rstrip("/") + "/me"
    key = runtime["MCP_GATEWAY_KEY"]
    _require_error(_gateway_get(url, key, None), "missing principal")
    fake_subject = "mcp_release_probe_" + secrets.token_hex(16)
    _require_error(_gateway_get(url, key, fake_subject), "unknown user")

    if not source_path:
        raise ConfigError("known-principal MCP gateway smoke configuration is required")
    source = read_env(source_path, allowed=SOURCE_KEYS)
    subject = source.get("TW_MCP_SMOKE_WORKOS_SUB", "")
    expected_tier = source.get("TW_MCP_SMOKE_EXPECT_TIER", "")
    if not subject or not expected_tier:
        raise ConfigError(
            "TW_MCP_SMOKE_WORKOS_SUB and TW_MCP_SMOKE_EXPECT_TIER are release-required"
        )
    if not _WORKOS_SUB_RE.fullmatch(subject):
        raise ConfigError("TW_MCP_SMOKE_WORKOS_SUB is invalid")
    if expected_tier not in {"explorer", "navigator", "analyst", "strategist"}:
        raise ConfigError("TW_MCP_SMOKE_EXPECT_TIER is invalid")
    status, body = _gateway_get(url, key, subject)
    if status != 200 or body.get("tier") != expected_tier:
        raise ConfigError("known-principal MCP gateway smoke failed")
    return True


def check_verifier_key(runtime_path: str, verifier_source: str) -> bool:
    runtime = validate(runtime_path)
    key = read_verifier_env(verifier_source)
    status, body = _gateway_get(
        runtime["API_BASE_URL"].rstrip("/") + "/me", key, None
    )
    rate = body.get("rate") if isinstance(body, dict) else None
    per_minute = rate.get("per_minute") if isinstance(rate, dict) else None
    per_day = rate.get("per_day") if isinstance(rate, dict) else None
    if not (
        status == 200
        and isinstance(body, dict)
        and body.get("tier") == VERIFIER_TIER
        and body.get("tier_name") == VERIFIER_TIER_NAME
        and isinstance(per_minute, int)
        and not isinstance(per_minute, bool)
        and per_minute >= VERIFIER_MIN_PER_MINUTE
        and isinstance(per_day, int)
        and not isinstance(per_day, bool)
        and per_day >= VERIFIER_MIN_PER_DAY
    ):
        raise ConfigError(
            "release verifier must be the dedicated ordinary Pro key with gate capacity"
        )
    return True


def exec_with_verifier(verifier_source: str, command: list[str]) -> None:
    """Replace this helper with a verifier child; the raw token is env-only."""
    if command and command[0] == "--":
        command = command[1:]
    if not command or not command[0] or not os.path.isabs(command[0]):
        raise ConfigError("exec-with-verifier requires an absolute executable path")
    allowed_environment = {
        "HOME", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED", "TW_MCP_EXPECT_AUTHORIZATION_SERVER",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in allowed_environment and value
    }
    environment["TW_MCP_VERIFY_TOKEN"] = read_verifier_env(verifier_source)
    try:
        os.execvpe(command[0], command, environment)
    except OSError as exc:
        raise ConfigError("cannot execute verifier command") from exc


def source_value(source_path: str, name: str) -> str:
    if name == "public-url":
        source = read_env(source_path, allowed=SOURCE_KEYS)
        value = source.get("TW2_MCP_PUBLIC_URL", "")
        return _https_origin(value, name="TW2_MCP_PUBLIC_URL")[0]
    if name == "authorization-server":
        source = read_env(source_path, allowed=SOURCE_KEYS)
        value = source.get("WORKOS_AUTHKIT_DOMAIN", "")
        return _https_origin(value, name="WORKOS_AUTHKIT_DOMAIN")[0]
    raise ConfigError("unsupported source-value selector")


def resolve_portal_hosts(source_path: str) -> tuple[str, str, str]:
    source = read_env(source_path, allowed=SOURCE_KEYS)
    main = source.get("TW2_PUBLIC_HOST", "").strip()
    is_dev = not main or "-dev." in main or main.startswith("tw2-dev")

    def selected(name: str, dev_default: str) -> str:
        value = source.get(name, "").strip()
        if not value:
            if not is_dev:
                raise ConfigError(f"{name} is required for a non-dev public host")
            value = dev_default
        return _dns_host(value, name=name)

    return (
        selected("TW2_API_PUBLIC_HOST", "api-dev.trxstat.com"),
        selected("TW2_MCP_PUBLIC_HOST", "mcp-dev.trxstat.com"),
        selected("TW2_DEVELOPERS_PUBLIC_HOST", "developers-dev.trxstat.com"),
    )


def check_process_env(runtime_path: str, pid: int) -> None:
    expected = validate(runtime_path)
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError as exc:
        raise ConfigError("cannot inspect the running MCP process environment") from exc
    actual: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            key, value = entry.decode("utf-8").split("=", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConfigError("running MCP process has a malformed environment") from exc
        if key in actual:
            raise ConfigError(f"running MCP process has duplicate environment key {key}")
        actual[key] = value
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ConfigError(f"running MCP process does not match {key} from mcpserver.env")
    permitted = set(RUNTIME_KEYS) | {
        "HOME", "INVOCATION_ID", "JOURNAL_STREAM", "LANG", "LOGNAME",
        "MEMORY_PRESSURE_WATCH", "MEMORY_PRESSURE_WRITE", "NOTIFY_SOCKET", "PATH",
        "SHELL",
        "SYSTEMD_EXEC_PID", "USER",
    }
    unexpected = sorted(set(actual) - permitted)
    if unexpected:
        raise ConfigError(
            "running MCP process inherited non-allowlisted environment keys: "
            + ", ".join(unexpected)
        )


def check_api_process_env(runtime_path: str, pid: int, featured_path: str) -> None:
    expected = validate_api(runtime_path)
    expected["TW2_FEATURED_HISTORY_FILE"] = featured_path
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError as exc:
        raise ConfigError("cannot inspect the running API gateway environment") from exc
    actual: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            key, value = entry.decode("utf-8").split("=", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConfigError("running API gateway has a malformed environment") from exc
        if key in actual:
            raise ConfigError(f"running API gateway has duplicate environment key {key}")
        actual[key] = value
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ConfigError(f"running API gateway does not match {key} from apiserver.env")
    permitted = set(expected) | {
        "HOME", "INVOCATION_ID", "JOURNAL_STREAM", "LANG", "LC_ALL", "LOGNAME",
        "MEMORY_PRESSURE_WATCH", "MEMORY_PRESSURE_WRITE", "NOTIFY_SOCKET", "PATH",
        "PYTHONDONTWRITEBYTECODE", "SHELL", "SYSTEMD_EXEC_PID", "USER",
    }
    unexpected = sorted(set(actual) - permitted)
    if unexpected:
        raise ConfigError(
            "running API gateway inherited non-allowlisted environment keys: "
            + ", ".join(unexpected)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--source", required=True)
    render_parser.add_argument("--dedicated", required=True)
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--resolved-public-host", required=True)
    api_render_parser = subparsers.add_parser("render-api")
    api_render_parser.add_argument("--source", required=True)
    api_render_parser.add_argument("--output", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--path", required=True)
    api_validate_parser = subparsers.add_parser("validate-api")
    api_validate_parser.add_argument("--path", required=True)
    gateway_parser = subparsers.add_parser("check-gateway-key")
    gateway_parser.add_argument("--path", required=True)
    gateway_parser.add_argument("--source")
    verifier_parser = subparsers.add_parser("check-verifier-key")
    verifier_parser.add_argument("--path", required=True)
    verifier_parser.add_argument("--source", required=True)
    exec_parser = subparsers.add_parser("exec-with-verifier")
    exec_parser.add_argument("--source", required=True)
    exec_parser.add_argument("argv", nargs=argparse.REMAINDER)
    process_parser = subparsers.add_parser("check-process-env")
    process_parser.add_argument("--path", required=True)
    process_parser.add_argument("--pid", required=True, type=int)
    api_process_parser = subparsers.add_parser("check-api-process-env")
    api_process_parser.add_argument("--path", required=True)
    api_process_parser.add_argument("--pid", required=True, type=int)
    api_process_parser.add_argument("--featured-path", required=True)
    value_parser = subparsers.add_parser("source-value")
    value_parser.add_argument("--source", required=True)
    value_parser.add_argument(
        "--name", required=True,
        choices=("public-url", "authorization-server"),
    )
    portal_parser = subparsers.add_parser("resolve-portal-hosts")
    portal_parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            render(args.source, args.dedicated, args.output, args.resolved_public_host)
        elif args.command == "render-api":
            render_api(args.source, args.output)
        elif args.command == "validate":
            validate(args.path)
        elif args.command == "validate-api":
            validate_api(args.path)
        elif args.command == "check-gateway-key":
            known = check_gateway_key(args.path, args.source)
            print(
                "PASS: MCP service key rejected missing and unknown principals; "
                + ("known-principal smoke passed" if known else "known-principal smoke not configured")
            )
        elif args.command == "check-verifier-key":
            check_verifier_key(args.path, args.source)
            print("PASS: dedicated ordinary Pro release-verifier key and capacity verified")
        elif args.command == "exec-with-verifier":
            exec_with_verifier(args.source, args.argv)
        elif args.command == "check-process-env":
            check_process_env(args.path, args.pid)
            print("PASS: running MCP process has only the least-privilege environment allowlist")
        elif args.command == "check-api-process-env":
            check_api_process_env(args.path, args.pid, args.featured_path)
            print("PASS: running API gateway has only the least-privilege environment allowlist")
        elif args.command == "source-value":
            print(source_value(args.source, args.name), end="")
        else:
            print("\n".join(resolve_portal_hosts(args.source)))
    except ConfigError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
