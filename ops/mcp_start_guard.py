#!/usr/bin/env python3
"""Refuse persistent MCP start while release state is not start-authoritative.

An active transaction always blocks persistent systemd activation. Precommit
gates use a separate transient canary bound to the transient deploy unit, so no
lock-sampling race exists between ExecCondition and ExecStart.
"""

from __future__ import annotations

import hashlib
import grp
import hmac
import json
import os
import platform
import re
import shlex
import stat
import struct
import sys
import uuid


_JOURNAL_VERSION = 4
_FILE_LABELS = {"unit", "api_unit", "dropin", "nginx", "mcp_env", "api_env", "secrets"}
_POINTER_LABELS = {
    "current",
    "previous",
    "nginx_enabled",
    "service_enabled",
    "api_service_enabled",
}
_MARKER_NAMES = {"commit-intent.json", "finalized.json", "recovery.json"}
_DISCARDABLE = _FILE_LABELS | _MARKER_NAMES | {"manifest.json"}
_STATE = re.compile(r"(?:\.new|committed|recovered|gc)-([0-9a-f-]{36})")
_EXPECTED_ACTIVE = "/var/lib/tradewave/mcp-release-transactions/active"
_EXPECTED_LOCK = "/run/lock/tradewave/mcp-release.lock"
_EXPECTED_SELF = "/usr/local/libexec/tradewave-mcp-start-guard.py"
_VERSIONED_SELF = re.compile(
    r"/usr/local/libexec/tradewave-mcp-release-control/sets/[0-9a-f]{64}/mcp-start-guard\.py"
)
_RELEASE_ROOT = "/home/tradewave-mcp/releases"
_BASE_INTERPRETER = "/usr/bin/python3.13"
_EXPECTED_FILES = {
    "unit": "/etc/systemd/system/tradewave-mcpserver.service",
    "api_unit": "/etc/systemd/system/tradewave-apiserver.service",
    "dropin": "/etc/systemd/system/tradewave-mcpserver.service.d/20-immutable-release.conf",
    "nginx": "/etc/nginx/sites-available/tradewave-developer-portal.conf",
    "mcp_env": "/etc/tradewave/mcpserver.env",
    "api_env": "/etc/tradewave/apiserver.env",
    "secrets": "/etc/tradewave/secrets.env",
}
_EXPECTED_POINTERS = {
    "current": "/home/tradewave-mcp/current",
    "previous": "/home/tradewave-mcp/previous",
    "nginx_enabled": "/etc/nginx/sites-enabled/tradewave-developer-portal",
    "service_enabled": "/etc/systemd/system/multi-user.target.wants/tradewave-mcpserver.service",
    "api_service_enabled": "/etc/systemd/system/multi-user.target.wants/tradewave-apiserver.service",
}
_EXPECTED_COMMITTED_FILE_METADATA = {
    "unit": (0o644, 0, 0),
    "api_unit": (0o644, 0, 0),
    "dropin": (0o644, 0, 0),
    "nginx": (0o644, 0, 0),
    "mcp_env": (0o600, 0, 0),
    "api_env": (0o600, 0, 0),
}
_ROTATION_STATE_PATH = "/var/lib/tradewave/mcp-key-rotation.json"
_VERIFIER_STATE_ROOT = "/var/lib/tradewave/mcp-verifier-probes"
_VERIFIER_CREDENTIAL_ROOT = "/run/tradewave-mcp-verifier"
_LEGACY_VERIFIER_ENV = "/etc/tradewave/mcp-verifier.env"
_SEAL_FIELDS = {
    "release_sha",
    "bundle_content_sha256",
    "runtime_lock_sha256",
    "runtime_wheel_manifest_sha256",
    "runtime_manifest_sha256",
    "runtime_tree_sha256",
    "gateway_lock_sha256",
    "gateway_wheel_manifest_sha256",
    "gateway_manifest_sha256",
    "gateway_tree_sha256",
    "provision_lock_sha256",
    "provision_wheel_manifest_sha256",
    "provision_manifest_sha256",
    "provision_tree_sha256",
}
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_SERVICE_KEY_RE = re.compile(r"tw_svc_[A-Za-z0-9_-]{43}")
_SERVICE_KEY_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?MCP_GATEWAY_KEY\s*=(.*)$")
_PLATFORM_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)
_API_ENV_KEYS = {
    "POSTGRES_DSN", "API_KEY_HMAC_SECRET", "TW2_APPSERVER_URL",
    "SERVICE_API_KEY", "TW2_DEMO_API_KEY", "REDIS_HOST", "REDIS_PORT",
    "API_REDIS_DB", "TW2_PUBLIC_HOST", "TW2_ENV", "API_CORS_ORIGINS",
    "TW2_API_PRICING_LIVE",
}
_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_MAX_BUNDLE_ENTRIES = 250_000
_SYSTEM_STDLIB_PATH = (
    "/usr/lib/python313.zip",
    "/usr/lib/python3.13",
    "/usr/lib/python3.13/lib-dynload",
)


def _expected_committed_metadata(label: str) -> tuple[int, int, int]:
    if label != "secrets":
        return _EXPECTED_COMMITTED_FILE_METADATA[label]
    try:
        gid = grp.getgrnam("flask").gr_gid
    except KeyError as exc:
        raise RuntimeError("required flask secrets group is missing") from exc
    return 0o640, 0, gid


def _refuse(message: str) -> int:
    print(f"MCP start refused: {message}", file=sys.stderr)
    return 1


def _secure_directory(path: str, mode: int) -> os.stat_result:
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise RuntimeError(f"{path} is not root:root mode {mode:04o}")
    return metadata


def _read_fd_bounded(fd: int, path: str, limit: int = _MAX_EVIDENCE_BYTES) -> bytes:
    payload = bytearray()
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
        if len(payload) > limit:
            raise RuntimeError(f"oversized file: {path}")


def _secure_file(path: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or opened.st_uid != 0
            or opened.st_gid != 0
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
        ):
            raise RuntimeError(f"unsafe journal evidence: {path}")
        payload = _read_fd_bounded(fd, path)
        after = os.fstat(fd)
        renamed = os.lstat(path)
        if (
            _metadata_identity(after) != _metadata_identity(opened)
            or (renamed.st_dev, renamed.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise RuntimeError(f"journal evidence changed while being read: {path}")
        return payload
    finally:
        os.close(fd)


def _canonical_json_file(path: str, label: str) -> dict[str, object]:
    raw = _secure_file(path)
    if len(raw) > 65536:
        raise RuntimeError(f"{label} is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} is not a JSON object")
    canonical = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    if raw != canonical:
        raise RuntimeError(f"{label} is not canonical JSON")
    return value


def _canonical_uuid(value: object) -> str:
    try:
        parsed = str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("invalid journal transaction id") from exc
    if parsed != value:
        raise RuntimeError("noncanonical journal transaction id")
    return parsed


def _nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _canonical_release_bundle(bundle: object, sha: object) -> tuple[str, str]:
    if (
        not isinstance(bundle, str)
        or bundle != os.path.abspath(bundle)
        or os.path.dirname(bundle) != _RELEASE_ROOT
        or not isinstance(sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or os.path.basename(bundle) != f"mcp-{sha}"
    ):
        raise RuntimeError("invalid sealed release bundle identity")
    return bundle, sha


def _validate_candidate(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"bundle", "sha"}:
        raise RuntimeError("invalid durable journal candidate identity")
    _canonical_release_bundle(value.get("bundle"), value.get("sha"))
    return value


def _validate_entry(value: object, *, gateway: bool) -> dict[str, object]:
    label = "gateway entry" if gateway else "MCP entry"
    fields = {"kind", "policy", "bundle", "sha", "cwd", "command", "argv_sha256", "active"}
    if not isinstance(value, dict) or set(value) != fields:
        raise RuntimeError(f"invalid durable journal {label} identity")
    kind = value.get("kind")
    if kind not in {"sealed", "legacy", "absent"}:
        raise RuntimeError(f"invalid durable journal {label} kind")
    if type(value.get("active")) is not bool:
        raise RuntimeError(f"invalid durable journal {label} active state")
    if _HASH_RE.fullmatch(str(value.get("argv_sha256", ""))) is None:
        raise RuntimeError(f"invalid durable journal {label} argv digest")
    cwd = value.get("cwd")
    command = value.get("command")
    if (
        not isinstance(cwd, str)
        or cwd != os.path.abspath(cwd)
        or not isinstance(command, str)
        or command != os.path.abspath(command)
        or "\x00" in cwd
        or "\x00" in command
    ):
        raise RuntimeError(f"invalid durable journal {label} process identity")
    if kind == "sealed":
        allowed_policies = {"fenced"} if gateway else {"fenced", "sealed-unfenced"}
        bundle, _ = _canonical_release_bundle(value.get("bundle"), value.get("sha"))
        expected_cwd = os.path.join(bundle, "src") if gateway else "/"
        runtime = "gateway-venv" if gateway else "venv"
        expected_command = os.path.join(_EXPECTED_POINTERS["current"], runtime, "bin", "python")
        if (
            value.get("policy") not in allowed_policies
            or value["active"] is not True
            or cwd != expected_cwd
            or command != expected_command
        ):
            raise RuntimeError(f"invalid sealed {label} runtime identity")
    elif kind == "legacy":
        expected_command = (
            "/home/flask/venv-api/bin/python3" if gateway else "/home/flask/venv-api/bin/python"
        )
        if (
            value.get("policy") != "legacy"
            or value.get("bundle") != ""
            or value.get("sha") != ""
            or cwd != "/home/flask"
            or command != expected_command
            or value["active"] is not True
        ):
            raise RuntimeError(f"invalid legacy {label} identity")
    elif (
        value.get("policy") != "absent"
        or value.get("bundle") != ""
        or value.get("sha") != ""
        or cwd != "/"
        or command != "/nonexistent"
        or value.get("argv_sha256") != "0" * 64
        or value["active"] is not False
    ):
        raise RuntimeError(f"invalid absent {label} identity")
    return value


def _valid_pointer_target(label: str, target: object) -> bool:
    if not isinstance(target, str) or not target or "\x00" in target:
        return False
    if label in {"current", "previous"}:
        return re.fullmatch(r"releases/mcp-[0-9a-f]{40}", target) is not None
    if label == "nginx_enabled":
        return target == _EXPECTED_FILES["nginx"]
    if label == "service_enabled":
        return target in {
            "../tradewave-mcpserver.service",
            "/etc/systemd/system/tradewave-mcpserver.service",
        }
    if label == "api_service_enabled":
        return target in {
            "../tradewave-apiserver.service",
            "/etc/systemd/system/tradewave-apiserver.service",
        }
    return False


def _validate_pointer_record(label: str, record: object) -> dict[str, object]:
    if (
        not isinstance(record, dict)
        or set(record) != {"path", "exists", "target", "uid", "gid"}
        or record.get("path") != _EXPECTED_POINTERS[label]
        or type(record.get("exists")) is not bool
    ):
        raise RuntimeError(f"invalid durable journal pointer record: {label}")
    if record["exists"]:
        if (
            not _valid_pointer_target(label, record.get("target"))
            or not _nonnegative_int(record.get("uid"))
            or not _nonnegative_int(record.get("gid"))
            or record["uid"] != 0
            or record["gid"] != 0
        ):
            raise RuntimeError(f"invalid durable journal pointer metadata: {label}")
    elif any(record.get(key) is not None for key in ("target", "uid", "gid")):
        raise RuntimeError(f"absent durable journal pointer carries metadata: {label}")
    return record


def _validate_manifest(
    txdir: str, *, required_markers: set[str] | None = None
) -> dict[str, object]:
    _secure_directory(txdir, 0o700)
    manifest = _canonical_json_file(os.path.join(txdir, "manifest.json"), "durable journal manifest")
    if (
        set(manifest) != {
            "version", "txid", "candidate", "entry", "gateway_entry", "files", "pointers"
        }
        or type(manifest.get("version")) is not int
        or manifest["version"] != _JOURNAL_VERSION
    ):
        raise RuntimeError("invalid durable journal manifest schema/version")
    manifest["txid"] = _canonical_uuid(manifest.get("txid"))
    _validate_candidate(manifest.get("candidate"))
    _validate_entry(manifest.get("entry"), gateway=False)
    _validate_entry(manifest.get("gateway_entry"), gateway=True)
    files = manifest.get("files")
    pointers = manifest.get("pointers")
    if not isinstance(files, dict) or set(files) != _FILE_LABELS:
        raise RuntimeError("invalid durable journal file set")
    if not isinstance(pointers, dict) or set(pointers) != _POINTER_LABELS:
        raise RuntimeError("invalid durable journal pointer set")

    expected = {"manifest.json"}
    fields = {"path", "exists", "backup", "sha256", "mode", "uid", "gid", "parent_exists"}
    for label, record in files.items():
        if (
            not isinstance(record, dict)
            or set(record) != fields
            or record.get("path") != _EXPECTED_FILES[label]
            or type(record.get("exists")) is not bool
            or type(record.get("parent_exists")) is not bool
        ):
            raise RuntimeError(f"invalid durable journal file record: {label}")
        if record["exists"]:
            if (
                record["parent_exists"] is not True
                or record.get("backup") != label
                or _HASH_RE.fullmatch(str(record.get("sha256", ""))) is None
                or not _nonnegative_int(record.get("mode"))
                or record["mode"] > 0o7777
                or not _nonnegative_int(record.get("uid"))
                or not _nonnegative_int(record.get("gid"))
            ):
                raise RuntimeError(f"invalid durable journal backup binding: {label}")
            payload = _secure_file(os.path.join(txdir, label))
            if hashlib.sha256(payload).hexdigest() != record["sha256"]:
                raise RuntimeError(f"durable journal backup digest mismatch: {label}")
            expected.add(label)
        elif any(record.get(key) is not None for key in ("backup", "sha256", "mode", "uid", "gid")):
            raise RuntimeError(f"absent durable journal file carries metadata: {label}")
    for label, record in pointers.items():
        _validate_pointer_record(label, record)

    children = set(os.listdir(txdir))
    marker_set = children - expected
    allowed_marker_sets = (
        set(),
        {"commit-intent.json"},
        {"commit-intent.json", "finalized.json"},
        {"recovery.json"},
    )
    if not expected.issubset(children) or marker_set not in allowed_marker_sets:
        raise RuntimeError("durable journal has unexpected or missing evidence")
    if required_markers is not None and marker_set != required_markers:
        raise RuntimeError("durable journal authority markers are incomplete or mixed")
    for name in marker_set:
        _secure_file(os.path.join(txdir, name))
    return manifest


def _validate_live_file_record(label: str, record: object) -> dict[str, object]:
    expected_mode, expected_uid, expected_gid = _expected_committed_metadata(label)
    if (
        not isinstance(record, dict)
        or set(record) != {"path", "sha256", "mode", "uid", "gid"}
        or record.get("path") != _EXPECTED_FILES[label]
        or _HASH_RE.fullmatch(str(record.get("sha256", ""))) is None
        or any(not _nonnegative_int(record.get(key)) for key in ("mode", "uid", "gid"))
        or (record["mode"], record["uid"], record["gid"])
        != (expected_mode, expected_uid, expected_gid)
    ):
        raise RuntimeError(f"invalid committed live file record: {label}")
    return record


def _load_intent(txdir: str, manifest: dict[str, object]) -> dict[str, object]:
    intent = _canonical_json_file(os.path.join(txdir, "commit-intent.json"), "commit intent")
    if (
        set(intent) != {"version", "txid", "candidate", "files", "pointers", "credentials"}
        or type(intent.get("version")) is not int
        or intent["version"] != _JOURNAL_VERSION
        or _canonical_uuid(intent.get("txid")) != manifest["txid"]
        or intent.get("candidate") != manifest["candidate"]
    ):
        raise RuntimeError("invalid commit intent schema/binding")
    files = intent.get("files")
    pointers = intent.get("pointers")
    if not isinstance(files, dict) or set(files) != _FILE_LABELS:
        raise RuntimeError("invalid commit intent file set")
    if not isinstance(pointers, dict) or set(pointers) != _POINTER_LABELS:
        raise RuntimeError("invalid commit intent pointer set")
    for label, record in files.items():
        _validate_live_file_record(label, record)
    for label, record in pointers.items():
        validated = _validate_pointer_record(label, record)
        if validated["exists"] is not True:
            raise RuntimeError(f"committed candidate pointer is absent: {label}")
    credentials = intent.get("credentials")
    if (
        not isinstance(credentials, dict)
        or set(credentials) != {"replacement_key_id", "replacement_key_hash"}
        or _HASH_RE.fullmatch(str(credentials.get("replacement_key_hash", ""))) is None
    ):
        raise RuntimeError("invalid commit intent credential binding")
    _canonical_uuid(credentials.get("replacement_key_id"))
    return intent


def _read_live_regular(path: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise RuntimeError(f"unsafe live committed file: {path}")
        return _read_fd_bounded(fd, path), opened
    finally:
        os.close(fd)


def _verify_files_and_pointers(
    files: dict[str, object], pointers: dict[str, object], *, restored: bool
) -> None:
    for label, record in files.items():
        path = record.get("path") if isinstance(record, dict) else None
        if not isinstance(path, str) or not os.path.isabs(path):
            raise RuntimeError(f"invalid live path for {label}")
        existed = record.get("exists") if restored else True
        if not existed:
            if os.path.lexists(path):
                raise RuntimeError(f"restored absent file exists: {label}")
            if not record.get("parent_exists") and os.path.lexists(os.path.dirname(path)):
                raise RuntimeError(f"restored absent parent exists: {label}")
            continue
        payload, metadata = _read_live_regular(path)
        if (
            hashlib.sha256(payload).hexdigest() != record.get("sha256")
            or stat.S_IMODE(metadata.st_mode) != record.get("mode")
            or metadata.st_uid != record.get("uid")
            or metadata.st_gid != record.get("gid")
        ):
            raise RuntimeError(f"live file does not match durable evidence: {label}")
    for label, record in pointers.items():
        path = record.get("path") if isinstance(record, dict) else None
        if not isinstance(path, str) or not os.path.isabs(path):
            raise RuntimeError(f"invalid live pointer path for {label}")
        existed = record.get("exists") if restored else True
        if not existed:
            if os.path.lexists(path):
                raise RuntimeError(f"restored absent pointer exists: {label}")
            continue
        metadata = os.lstat(path)
        if (
            not stat.S_ISLNK(metadata.st_mode)
            or os.readlink(path) != record.get("target")
            or metadata.st_uid != record.get("uid")
            or metadata.st_gid != record.get("gid")
        ):
            raise RuntimeError(f"live pointer does not match durable evidence: {label}")


def _verify_recovered_live(manifest: dict[str, object]) -> None:
    _verify_files_and_pointers(manifest["files"], manifest["pointers"], restored=True)
    components = (
        ("MCP", manifest["entry"], "unit", "service_enabled"),
        ("gateway", manifest["gateway_entry"], "api_unit", "api_service_enabled"),
    )
    for label, entry, unit_label, enabled_label in components:
        expected = entry["kind"] != "absent"
        if (
            manifest["files"][unit_label]["exists"] is not expected
            or manifest["pointers"][enabled_label]["exists"] is not expected
        ):
            raise RuntimeError(f"recovered {label} install/enabled state contradicts its entry")

    current = manifest["pointers"]["current"]
    sealed = [(label, entry) for label, entry, _, _ in components if entry["kind"] == "sealed"]
    if not sealed:
        if current["exists"]:
            raise RuntimeError("unsealed recovered entries unexpectedly retain a current release")
        return
    if not current["exists"]:
        raise RuntimeError("sealed recovered entry has no current release")
    resolved = os.path.realpath(os.path.join(os.path.dirname(current["path"]), current["target"]))
    verified: set[tuple[str, str]] = set()
    for label, entry in sealed:
        bundle, sha = _canonical_release_bundle(entry.get("bundle"), entry.get("sha"))
        if resolved != bundle:
            raise RuntimeError(f"recovered current pointer does not select sealed {label} entry")
        if (bundle, sha) not in verified:
            _verify_bundle_content(bundle, sha)
            verified.add((bundle, sha))
    if manifest["gateway_entry"]["kind"] == "sealed":
        _validate_api_environment()


def _verify_committed_live(manifest: dict[str, object], intent: dict[str, object]) -> None:
    files = intent["files"]
    pointers = intent["pointers"]
    _verify_files_and_pointers(files, pointers, restored=False)
    candidate = _validate_candidate(manifest.get("candidate"))
    bundle, sha = _canonical_release_bundle(candidate.get("bundle"), candidate.get("sha"))
    current = pointers["current"]
    resolved = os.path.realpath(os.path.join(os.path.dirname(current["path"]), current["target"]))
    if resolved != bundle:
        raise RuntimeError("committed current pointer does not select candidate")
    _verify_bundle_content(bundle, sha)
    _validate_api_environment()


def _decode_assignment(raw_value: str, label: str) -> str:
    lexer = shlex.shlex(raw_value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        decoded = list(lexer)
    except ValueError as exc:
        raise RuntimeError(f"{label} has a malformed assignment") from exc
    if len(decoded) != 1 or any(character in decoded[0] for character in ("\x00", "\r", "\n")):
        raise RuntimeError(f"{label} has an invalid assignment")
    return decoded[0]


def _validate_api_environment() -> None:
    raw, metadata = _read_live_regular(_EXPECTED_FILES["api_env"])
    if (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or len(raw) > 2 * 1024 * 1024
    ):
        raise RuntimeError("dedicated API environment metadata is unsafe")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("dedicated API environment is not valid UTF-8") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _PLATFORM_ASSIGNMENT_RE.fullmatch(line)
        if match is None:
            raise RuntimeError(f"dedicated API environment line {number} is malformed")
        name, encoded = match.groups()
        if name not in _API_ENV_KEYS:
            raise RuntimeError(f"dedicated API environment contains forbidden key {name!r}")
        if name in values:
            raise RuntimeError(f"dedicated API environment duplicates key {name!r}")
        values[name] = _decode_assignment(encoded, f"dedicated API environment {name}")
    if set(values) != _API_ENV_KEYS:
        raise RuntimeError("dedicated API environment key set is not exact")
    for name in ("POSTGRES_DSN", "API_KEY_HMAC_SECRET", "TW2_APPSERVER_URL", "SERVICE_API_KEY"):
        if not values[name]:
            raise RuntimeError(f"dedicated API environment required key is empty: {name}")
    if values["TW2_ENV"] not in {"dev", "staging", "prod"}:
        raise RuntimeError("dedicated API environment TW2_ENV is invalid")
    if values["TW2_API_PRICING_LIVE"] not in {"true", "false"}:
        raise RuntimeError("dedicated API environment pricing flag is not canonical")
    if not hmac.compare_digest(values["API_KEY_HMAC_SECRET"], _load_platform_hmac_secret()):
        raise RuntimeError("dedicated API HMAC authority differs from canonical platform source")


def _load_environment_service_key(path: str, label: str) -> str | None:
    if not os.path.lexists(path):
        return None
    raw, _ = _read_live_regular(path)
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError(f"{label} is too large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} is not valid UTF-8") from exc
    values: list[str] = []
    for line in lines:
        match = _SERVICE_KEY_ASSIGNMENT_RE.fullmatch(line)
        if match is None:
            continue
        value = _decode_assignment(match.group(1), f"{label} MCP_GATEWAY_KEY")
        if _SERVICE_KEY_RE.fullmatch(value) is None:
            raise RuntimeError(f"{label} has an invalid MCP_GATEWAY_KEY assignment")
        values.append(value)
    if len(values) > 1:
        raise RuntimeError(f"{label} has duplicate MCP_GATEWAY_KEY assignments")
    return values[0] if values else None


def _load_platform_hmac_secret() -> str:
    raw, _ = _read_live_regular(_EXPECTED_FILES["secrets"])
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError("platform secrets is too large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("platform secrets is not valid UTF-8") from exc
    values: dict[str, list[str]] = {"API_KEY_HMAC_SECRET": [], "APPSERVER_JWT_SECRET": []}
    for line in lines:
        match = _PLATFORM_ASSIGNMENT_RE.fullmatch(line)
        if match is None or match.group(1) not in values:
            continue
        values[match.group(1)].append(
            _decode_assignment(match.group(2), f"platform secrets {match.group(1)}")
        )
    for name, assignments in values.items():
        if len(assignments) > 1:
            raise RuntimeError(f"platform secrets has duplicate {name} assignments")
    secret = (
        values["API_KEY_HMAC_SECRET"][0]
        if values["API_KEY_HMAC_SECRET"]
        else values["APPSERVER_JWT_SECRET"][0]
        if values["APPSERVER_JWT_SECRET"]
        else ""
    )
    if not secret:
        raise RuntimeError("platform secrets lacks API_KEY_HMAC_SECRET/APPSERVER_JWT_SECRET")
    return secret


def _service_key_hash(raw_key: str) -> str:
    return hmac.new(
        _load_platform_hmac_secret().encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _load_rotation_state(
    *, allow_absent: bool = False
) -> tuple[dict[str, object] | None, str | None]:
    if not os.path.lexists(_ROTATION_STATE_PATH):
        if allow_absent:
            return None, None
        raise RuntimeError("required service-key rotation state is absent")
    raw, metadata = _read_live_regular(_ROTATION_STATE_PATH)
    if (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or len(raw) > 8192
    ):
        raise RuntimeError("service-key rotation state metadata is unsafe")
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("service-key rotation state is invalid JSON") from exc
    fields = {
        "version", "status", "replacement_key_id", "replacement_key_hash",
        "superseded_key_id", "superseded_key_hash", "source_key_hash",
    }
    if (
        not isinstance(state, dict)
        or set(state) != fields
        or type(state.get("version")) is not int
        or state["version"] != 2
        or state.get("status") not in {"pending", "active"}
    ):
        raise RuntimeError("service-key rotation state schema/status is invalid")
    _canonical_uuid(state.get("replacement_key_id"))
    if (
        _HASH_RE.fullmatch(str(state.get("replacement_key_hash", ""))) is None
        or _HASH_RE.fullmatch(str(state.get("source_key_hash", ""))) is None
    ):
        raise RuntimeError("service-key rotation state digest is invalid")
    if (state.get("superseded_key_id") is None) != (state.get("superseded_key_hash") is None):
        raise RuntimeError("service-key rotation superseded binding is incomplete")
    if state.get("superseded_key_id") is not None:
        _canonical_uuid(state["superseded_key_id"])
        if _HASH_RE.fullmatch(str(state.get("superseded_key_hash", ""))) is None:
            raise RuntimeError("service-key rotation superseded hash is invalid")
    if state["status"] == "active" and state.get("superseded_key_id") is not None:
        raise RuntimeError("active service-key rotation retains a superseded binding")
    canonical = (
        json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    if raw != canonical:
        raise RuntimeError("service-key rotation state is not canonical JSON")
    return state, hashlib.sha256(raw).hexdigest()


def _active_credential_record() -> dict[str, object]:
    state, state_digest = _load_rotation_state()
    assert state is not None and state_digest is not None
    if state["status"] != "active":
        raise RuntimeError("dedicated service-key state is not active")
    broad_key = _load_environment_service_key(_EXPECTED_FILES["secrets"], "platform secrets")
    if broad_key is not None:
        raise RuntimeError("active dedicated service key still exists in broad platform secrets")
    runtime_key = _load_environment_service_key(
        _EXPECTED_FILES["mcp_env"], "dedicated MCP environment"
    )
    if runtime_key is None:
        raise RuntimeError("active service-key state lacks its dedicated runtime credential")
    if _service_key_hash(runtime_key) != state["replacement_key_hash"]:
        raise RuntimeError("dedicated runtime credential does not match active rotation state")
    return {
        "state_kind": "active",
        "replacement_key_id": state["replacement_key_id"],
        "replacement_key_hash": state["replacement_key_hash"],
        "rotation_state_sha256": state_digest,
    }


def _recovered_credential_record(manifest: dict[str, object]) -> dict[str, object]:
    entry_kind = manifest["entry"]["kind"]
    if entry_kind == "sealed":
        return _active_credential_record()
    if _load_rotation_state(allow_absent=True) != (None, None):
        raise RuntimeError("legacy/absent recovery retained service-key rotation state")
    broad_key = _load_environment_service_key(_EXPECTED_FILES["secrets"], "platform secrets")
    runtime_key = _load_environment_service_key(
        _EXPECTED_FILES["mcp_env"], "dedicated MCP environment"
    )
    if runtime_key is not None and runtime_key != broad_key:
        raise RuntimeError("restored dedicated and broad legacy credentials conflict")
    if broad_key is not None:
        return {
            "state_kind": "legacy-broad",
            "replacement_key_id": None,
            "replacement_key_hash": _service_key_hash(broad_key),
            "rotation_state_sha256": None,
        }
    if runtime_key is not None:
        raise RuntimeError("restored dedicated credential has no rotation state or broad source")
    if entry_kind == "legacy":
        raise RuntimeError("restored legacy MCP entry lacks its broad service credential")
    return {
        "state_kind": "source-absent",
        "replacement_key_id": None,
        "replacement_key_hash": None,
        "rotation_state_sha256": None,
    }


def _verifier_root_safe(path: str, label: str) -> None:
    if not os.path.lexists(path):
        return
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or os.listdir(path)
    ):
        raise RuntimeError(f"{label} must be absent or an exact empty root:root mode 0700 directory")


def _verifier_absence_record(txid: str) -> dict[str, object]:
    if os.path.lexists(_LEGACY_VERIFIER_ENV):
        raise RuntimeError("legacy permanent verifier credential still exists")
    state_path = os.path.join(_VERIFIER_STATE_ROOT, f"{txid}.json")
    credential_path = os.path.join(_VERIFIER_CREDENTIAL_ROOT, txid, "verify-env")
    if os.path.lexists(state_path) or os.path.lexists(credential_path):
        raise RuntimeError("transaction verifier sidecar or credential source still exists")
    _verifier_root_safe(_VERIFIER_STATE_ROOT, "verifier state root")
    _verifier_root_safe(_VERIFIER_CREDENTIAL_ROOT, "verifier credential root")
    return {
        "state_root_absent_or_exact_empty": True,
        "credential_root_absent_or_exact_empty": True,
        "transaction_artifacts_absent": True,
        "legacy_env_absent": True,
    }


def _load_authority_marker(
    txdir: str,
    manifest: dict[str, object],
    intent: dict[str, object] | None,
    name: str,
) -> dict[str, object]:
    marker = _canonical_json_file(os.path.join(txdir, name), name)
    if (
        set(marker) != {"version", "txid", "candidate", "credentials", "verifier"}
        or type(marker.get("version")) is not int
        or marker["version"] != _JOURNAL_VERSION
        or _canonical_uuid(marker.get("txid")) != manifest["txid"]
        or marker.get("candidate") != manifest["candidate"]
    ):
        raise RuntimeError(f"{name} schema/transaction binding is invalid")
    credentials = marker.get("credentials")
    if not isinstance(credentials, dict) or set(credentials) != {
        "state_kind", "replacement_key_id", "replacement_key_hash", "rotation_state_sha256"
    }:
        raise RuntimeError(f"{name} credential evidence is invalid")
    expected_credentials = (
        _active_credential_record() if intent is not None else _recovered_credential_record(manifest)
    )
    if credentials != expected_credentials:
        raise RuntimeError(f"{name} service-key evidence drifted")
    if intent is not None and {
        "replacement_key_id": credentials["replacement_key_id"],
        "replacement_key_hash": credentials["replacement_key_hash"],
    } != intent["credentials"]:
        raise RuntimeError(f"{name} differs from commit-intent credential binding")
    verifier = marker.get("verifier")
    if (
        not isinstance(verifier, dict)
        or set(verifier) != {
            "state_root_absent_or_exact_empty",
            "credential_root_absent_or_exact_empty",
            "transaction_artifacts_absent",
            "legacy_env_absent",
        }
        or any(value is not True for value in verifier.values())
        or verifier != _verifier_absence_record(manifest["txid"])
    ):
        raise RuntimeError(f"{name} verifier-absence evidence drifted")
    return marker


def _metadata_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
    )


def _require_immutable_bundle_node(
    path: bytes, relative: bytes, kind: bytes, metadata: os.stat_result, root: bytes
) -> bytes | None:
    display = os.fsdecode(path)
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        raise RuntimeError(f"candidate bundle node is not root-owned: {display}")
    mode = stat.S_IMODE(metadata.st_mode)
    if kind == b"D":
        if mode != 0o555:
            raise RuntimeError(f"candidate bundle directory mode is not exact: {display}")
        return None
    if kind == b"F":
        expected_mode = 0o555 if mode & 0o111 else 0o444
        if mode != expected_mode or metadata.st_nlink != 1:
            raise RuntimeError(f"candidate bundle regular-file policy is not exact: {display}")
        return None

    expected_links = {
        b"venv/bin/python",
        b"gateway-venv/bin/python",
        b"provision-venv/bin/python",
    }
    target = os.readlink(path)
    if (
        relative not in expected_links
        or target != os.fsencode(_BASE_INTERPRETER)
        or os.path.realpath(path) != os.fsencode(_BASE_INTERPRETER)
    ):
        raise RuntimeError(f"candidate bundle has an unexpected interpreter symlink: {display}")
    return target


def _hash_bundle_regular(path: bytes, captured: os.stat_result) -> tuple[int, bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _metadata_identity(opened) != _metadata_identity(captured):
            raise RuntimeError(f"candidate file changed before hashing: {os.fsdecode(path)}")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        current = os.lstat(path)
        if _metadata_identity(current) != _metadata_identity(captured) or size != captured.st_size:
            raise RuntimeError(f"candidate file changed while hashing: {os.fsdecode(path)}")
        return size, digest.digest()
    finally:
        os.close(fd)


def _bundle_content_sha256(bundle: str) -> str:
    root = os.fsencode(bundle)
    entries: list[tuple[bytes, bytes, os.stat_result, bytes | None]] = []

    def collect(relative: bytes) -> None:
        if len(entries) >= _MAX_BUNDLE_ENTRIES:
            raise RuntimeError("candidate bundle has too many filesystem entries")
        path = root if relative == b"." else os.path.join(root, relative)
        metadata = os.lstat(path)
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            kind = b"D"
        elif stat.S_ISREG(metadata.st_mode):
            kind = b"F"
        elif stat.S_ISLNK(metadata.st_mode):
            kind = b"L"
        else:
            raise RuntimeError("unsupported candidate bundle entry")
        target = _require_immutable_bundle_node(path, relative, kind, metadata, root)
        entries.append((relative, kind, metadata, target))
        if kind == b"D":
            with os.scandir(path) as directory:
                names = sorted(entry.name for entry in directory)
            for name in names:
                child = name if relative == b"." else os.path.join(relative, name)
                if child != b".sealed":
                    collect(child)

    collect(b".")
    actual_links = {relative for relative, kind, _, _ in entries if kind == b"L"}
    if actual_links != {
        b"venv/bin/python",
        b"gateway-venv/bin/python",
        b"provision-venv/bin/python",
    }:
        raise RuntimeError("candidate bundle lacks the three exact interpreter links")
    digest = hashlib.sha256(b"TW_MCP_BUNDLE_CONTENT_V1\0")
    for relative, kind, captured, captured_target in sorted(entries, key=lambda item: item[0]):
        path = root if relative == b"." else os.path.join(root, relative)
        digest.update(kind)
        digest.update(struct.pack(">I", stat.S_IMODE(captured.st_mode)))
        digest.update(struct.pack(">Q", len(relative)))
        digest.update(relative)
        if kind == b"F":
            size, file_digest = _hash_bundle_regular(path, captured)
            digest.update(struct.pack(">Q", size))
            digest.update(file_digest)
        elif kind == b"L":
            target = os.readlink(path)
            current = os.lstat(path)
            if _metadata_identity(current) != _metadata_identity(captured) or target != captured_target:
                raise RuntimeError("candidate symlink changed while hashing")
            digest.update(struct.pack(">Q", len(target)))
            digest.update(target)
    return digest.hexdigest()


def _verify_bundle_content(bundle: str, sha: str) -> None:
    bundle, sha = _canonical_release_bundle(bundle, sha)
    if os.path.realpath(bundle) != bundle:
        raise RuntimeError("candidate bundle path traverses a symlink")
    release_home = os.path.dirname(_RELEASE_ROOT)
    for parent in (os.path.dirname(release_home), release_home, _RELEASE_ROOT):
        metadata = os.lstat(parent)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise RuntimeError(f"candidate release parent is unsafe: {parent}")
    seal_path = os.path.join(bundle, ".sealed")
    payload, metadata = _read_live_regular(seal_path)
    if (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o444
        or metadata.st_nlink != 1
        or len(payload) > 65536
    ):
        raise RuntimeError("candidate seal is not immutable root-owned evidence")
    values: dict[str, str] = {}
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError("candidate seal is not ASCII") from exc
    if not text.endswith("\n") or "\r" in text:
        raise RuntimeError("candidate seal has noncanonical line endings")
    for line in text.splitlines():
        if line.count("=") != 1:
            raise RuntimeError("candidate seal line is malformed")
        key, value = line.split("=", 1)
        if not key or key in values or any(character in value for character in "\x00\r\n"):
            raise RuntimeError("candidate seal has duplicate/unsafe data")
        values[key] = value
    if set(values) != _SEAL_FIELDS:
        raise RuntimeError("candidate seal schema is not exact")
    expected = values["bundle_content_sha256"]
    if values["release_sha"] != sha:
        raise RuntimeError("candidate seal identity/content digest is invalid")
    for key in _SEAL_FIELDS - {"release_sha"}:
        if _HASH_RE.fullmatch(values[key]) is None:
            raise RuntimeError(f"candidate seal has no valid {key}")
    if _bundle_content_sha256(bundle) != expected:
        raise RuntimeError("candidate bundle content does not match seal")


def _validate_discardable(path: str) -> None:
    _secure_directory(path, 0o700)
    for name in os.listdir(path):
        if name not in _DISCARDABLE:
            raise RuntimeError("discardable journal has an unexpected child")
        _secure_file(os.path.join(path, name))


def _verify_runtime_boundary() -> None:
    self_path = os.path.abspath(os.fsdecode(__file__))
    real_self = os.path.realpath(__file__)
    stable = self_path == _EXPECTED_SELF and real_self == _EXPECTED_SELF
    versioned = self_path == real_self and _VERSIONED_SELF.fullmatch(self_path) is not None
    if not stable and not versioned:
        raise RuntimeError("start guard is not executing from a fixed or sealed versioned path")
    self_metadata = os.lstat(__file__)
    expected_mode = 0o755 if stable else 0o555
    if (
        not stat.S_ISREG(self_metadata.st_mode)
        or self_metadata.st_uid != 0
        or self_metadata.st_gid != 0
        or stat.S_IMODE(self_metadata.st_mode) != expected_mode
        or self_metadata.st_nlink != 1
    ):
        raise RuntimeError("start guard is not a root-owned single-link file with its exact mode")
    for protected in (self_path, _BASE_INTERPRETER):
        current = "/"
        components = protected.strip("/").split("/")
        for component in components[:-1]:
            current = os.path.join(current, component)
            metadata = os.lstat(current)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_gid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RuntimeError(f"trusted helper ancestor is unsafe: {current}")
    interpreter_metadata = os.lstat(_BASE_INTERPRETER)
    if (
        not stat.S_ISREG(interpreter_metadata.st_mode)
        or interpreter_metadata.st_uid != 0
        or interpreter_metadata.st_gid != 0
        or stat.S_IMODE(interpreter_metadata.st_mode) & 0o022
    ):
        raise RuntimeError("system Python interpreter is not a trusted root-owned file")
    flags = sys.flags
    if (
        platform.python_implementation() != "CPython"
        or sys.version_info[:2] != (3, 13)
        or sys.executable != _BASE_INTERPRETER
        or os.path.realpath(sys.executable) != _BASE_INTERPRETER
        or sys._base_executable != _BASE_INTERPRETER
        or sys.prefix != "/usr"
        or sys.base_prefix != "/usr"
        or tuple(sys.path) != _SYSTEM_STDLIB_PATH
        or not flags.isolated
        or not flags.dont_write_bytecode
        or not flags.no_site
        or not flags.no_user_site
        or not flags.ignore_environment
        or not flags.safe_path
        or {"site", "sitecustomize", "usercustomize"}.intersection(sys.modules)
    ):
        raise RuntimeError("start guard requires exact isolated /usr/bin/python3.13 -I -B -S")


def check(active_path: str, lock_path: str) -> int:
    if active_path != _EXPECTED_ACTIVE or lock_path != _EXPECTED_LOCK:
        return _refuse("journal and lock paths must be the fixed production paths")
    try:
        _verify_runtime_boundary()
        txroot = os.path.dirname(active_path)
        if os.path.basename(active_path) != "active":
            raise RuntimeError("active journal path has an invalid basename")
        if not os.path.lexists(txroot):
            return 0
        _secure_directory(txroot, 0o700)
        names = os.listdir(txroot)
        if not names:
            return 0
        if len(names) != 1:
            raise RuntimeError("mixed durable journal states exist")
        state = names[0]
        state_path = os.path.join(txroot, state)
        if state == "active":
            _validate_manifest(state_path)
            raise RuntimeError("active release transaction blocks persistent MCP start")
        else:
            match = _STATE.fullmatch(state)
            if match is None:
                raise RuntimeError("unknown durable journal state")
            _canonical_uuid(match.group(1))
            if state.startswith(".new-"):
                raise RuntimeError("incomplete journal publication requires reconciliation")
            if state.startswith("committed-"):
                manifest = _validate_manifest(
                    state_path, required_markers={"commit-intent.json", "finalized.json"}
                )
                if manifest["txid"] != match.group(1):
                    raise RuntimeError("committed journal directory/manifest transaction mismatch")
                intent = _load_intent(state_path, manifest)
                _verify_committed_live(manifest, intent)
                _load_authority_marker(state_path, manifest, intent, "finalized.json")
                return 0
            if state.startswith("recovered-"):
                manifest = _validate_manifest(state_path, required_markers={"recovery.json"})
                if manifest["txid"] != match.group(1):
                    raise RuntimeError("recovered journal directory/manifest transaction mismatch")
                _verify_recovered_live(manifest)
                _load_authority_marker(state_path, manifest, None, "recovery.json")
                return 0
            # gc is explicitly non-authoritative and may be partly unlinked
            # after a kill; its fixed safe subset can be discarded.
            _validate_discardable(state_path)
            return 0
    except (OSError, RuntimeError) as exc:
        return _refuse(str(exc))


def main() -> int:
    if len(sys.argv) != 3:
        return _refuse("usage: mcp_start_guard.py ACTIVE_JOURNAL LOCK_FILE")
    return check(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
