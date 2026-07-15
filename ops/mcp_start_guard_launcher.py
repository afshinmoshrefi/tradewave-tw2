#!/usr/bin/python3.13
"""Immutable production bootstrap for the versioned MCP start guard.

The service invokes this stable file.  It validates one complete control-plane
generation selected by the atomic ``current`` pointer, then execs that set's
guard with an isolated system interpreter.  No file from two generations can
be combined.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


CONTROL_ROOT = "/usr/local/libexec/tradewave-mcp-release-control"
CURRENT = f"{CONTROL_ROOT}/current"
SETS_ROOT = f"{CONTROL_ROOT}/sets"
SELF = "/usr/local/libexec/tradewave-mcp-start-guard.py"
LAUNCHER = "/usr/local/sbin/tradewave-mcp-release"
FENCE = "/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf"
API_FENCE = "/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf"
PYTHON = "/usr/bin/python3.13"
MAX_FILE_BYTES = 16 * 1024 * 1024
HASH_RE = re.compile(r"[0-9a-f]{64}")
SET_TARGET_RE = re.compile(r"sets/([0-9a-f]{64})")
EXPECTED_FILES = {
    "deploy-mcp-release.sh": 0o555,
    "mcp-offline-wheels.py": 0o555,
    "mcp-provision-bootstrap.py": 0o555,
    "mcp-service-env.py": 0o555,
    "mcp-start-guard.py": 0o555,
    "release-launcher-bootstrap.sh": 0o444,
    "start-guard-bootstrap.py": 0o444,
    "provision-mcp-key.py": 0o555,
    "requirements-mcp-provision.lock": 0o444,
    "tradewave-developer-portal.conf": 0o444,
    "tradewave-mcpserver-release.conf": 0o444,
    "tradewave-mcpserver-release-fence.conf": 0o444,
    "tradewave-mcpserver-legacy.service": 0o444,
    "tradewave-mcpserver.service": 0o444,
    "tradewave-apiserver-immutable.service": 0o444,
    "tradewave-apiserver-release-fence.conf": 0o444,
    "tradewave-apiserver-legacy.service": 0o444,
    "verify_mcp_contract.py": 0o555,
    "verify_mcp_load.py": 0o555,
}
EXPECTED_BOOTSTRAPS = {
    SELF: 0o755,
    LAUNCHER: 0o755,
    FENCE: 0o644,
    API_FENCE: 0o644,
}


class ControlPlaneError(RuntimeError):
    """The selected trusted control-plane generation is unsafe."""


def _fail(message: str) -> "NoReturn":
    print(f"MCP control-plane guard: {message}", file=sys.stderr)
    raise SystemExit(1)


def _secure_ancestors(path: str) -> None:
    current = "/"
    for component in os.path.dirname(path).strip("/").split("/"):
        if component:
            current = os.path.join(current, component)
        metadata = os.lstat(current)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ControlPlaneError(f"unsafe trusted ancestor: {current}")


def _regular_bytes(path: str, mode: int) -> bytes:
    _secure_ancestors(path)
    try:
        before = os.lstat(path)
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ControlPlaneError(f"cannot open trusted regular file {path}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_uid != 0
            or opened.st_gid != 0
            or stat.S_IMODE(opened.st_mode) != mode
            or opened.st_nlink != 1
            or opened.st_size > MAX_FILE_BYTES
        ):
            raise ControlPlaneError(f"unsafe trusted regular file metadata: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ControlPlaneError(f"oversized trusted regular file: {path}")
        after = os.fstat(descriptor)
        named = os.lstat(path)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_ctime_ns,
            value.st_mtime_ns,
        )
        if identity(opened) != identity(after) or identity(opened) != identity(named):
            raise ControlPlaneError(f"trusted regular file changed while read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _secure_directory(path: str, mode: int) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ControlPlaneError(f"cannot inspect trusted directory {path}: {exc}") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise ControlPlaneError(f"unsafe trusted directory metadata: {path}")


def _validate_record(record: object, expected_mode: int, label: str) -> str:
    if not isinstance(record, dict) or set(record) != {"mode", "sha256"}:
        raise ControlPlaneError(f"invalid manifest record: {label}")
    if type(record.get("mode")) is not int or record["mode"] != expected_mode:
        raise ControlPlaneError(f"invalid manifest mode: {label}")
    digest = record.get("sha256")
    if not isinstance(digest, str) or HASH_RE.fullmatch(digest) is None:
        raise ControlPlaneError(f"invalid manifest digest: {label}")
    return digest


def selected_set() -> str:
    _secure_directory(CONTROL_ROOT, 0o755)
    _secure_directory(SETS_ROOT, 0o755)
    try:
        pointer = os.lstat(CURRENT)
        target = os.readlink(CURRENT)
    except OSError as exc:
        raise ControlPlaneError(f"cannot inspect atomic control-plane pointer: {exc}") from exc
    match = SET_TARGET_RE.fullmatch(target)
    if (
        not stat.S_ISLNK(pointer.st_mode)
        or pointer.st_uid != 0
        or pointer.st_gid != 0
        or pointer.st_nlink != 1
        or match is None
    ):
        raise ControlPlaneError("atomic control-plane pointer is unsafe")
    manifest_digest = match.group(1)
    selected = os.path.join(CONTROL_ROOT, target)
    expected = os.path.join(SETS_ROOT, manifest_digest)
    if selected != expected or os.path.realpath(selected) != expected:
        raise ControlPlaneError("atomic control-plane pointer escapes the sealed set root")
    _secure_directory(selected, 0o555)

    manifest_path = os.path.join(selected, "manifest.json")
    raw_manifest = _regular_bytes(manifest_path, 0o444)
    if hashlib.sha256(raw_manifest).hexdigest() != manifest_digest:
        raise ControlPlaneError("control-plane manifest digest does not match its set name")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlPlaneError("control-plane manifest is invalid JSON") from exc
    canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if raw_manifest != canonical:
        raise ControlPlaneError("control-plane manifest is not canonical JSON")
    if not isinstance(manifest, dict) or set(manifest) != {"bootstraps", "files", "schema", "source"}:
        raise ControlPlaneError("control-plane manifest schema is invalid")
    if type(manifest.get("schema")) is not int or manifest["schema"] != 1:
        raise ControlPlaneError("control-plane manifest version is unsupported")
    files = manifest.get("files")
    bootstraps = manifest.get("bootstraps")
    source = manifest.get("source")
    if (
        not isinstance(source, dict)
        or set(source) != {"commit_sha"}
        or not isinstance(source.get("commit_sha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", source["commit_sha"]) is None
    ):
        raise ControlPlaneError("control-plane source commit is invalid")
    if not isinstance(files, dict) or set(files) != set(EXPECTED_FILES):
        raise ControlPlaneError("control-plane manifest has an unexpected asset set")
    if not isinstance(bootstraps, dict) or set(bootstraps) != set(EXPECTED_BOOTSTRAPS):
        raise ControlPlaneError("control-plane manifest has an unexpected bootstrap set")
    if set(os.listdir(selected)) != set(EXPECTED_FILES) | {"manifest.json"}:
        raise ControlPlaneError("sealed control-plane directory has unexpected children")
    for name, mode in EXPECTED_FILES.items():
        expected_digest = _validate_record(files[name], mode, name)
        payload = _regular_bytes(os.path.join(selected, name), mode)
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise ControlPlaneError(f"control-plane asset digest mismatch: {name}")
    for path, mode in EXPECTED_BOOTSTRAPS.items():
        expected_digest = _validate_record(bootstraps[path], mode, path)
        payload = _regular_bytes(path, mode)
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise ControlPlaneError(f"control-plane bootstrap digest mismatch: {path}")
    return selected


def main() -> int:
    if (
        sys.executable != PYTHON
        or os.path.realpath(sys.executable) != PYTHON
        or sys.version_info[:2] != (3, 13)
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.ignore_environment
    ):
        _fail("bootstrap requires isolated /usr/bin/python3.13 -I -B -S")
    try:
        selected = selected_set()
    except ControlPlaneError as exc:
        _fail(str(exc))
    guard = os.path.join(selected, "mcp-start-guard.py")
    argv = [PYTHON, "-I", "-B", "-S", guard, *sys.argv[1:]]
    environment = {
        "HOME": "/nonexistent",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    os.execve(PYTHON, argv, environment)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
