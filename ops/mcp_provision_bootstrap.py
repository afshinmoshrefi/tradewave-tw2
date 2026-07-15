#!/usr/bin/env python3
"""Verify and enter the sealed MCP credential-provisioning environment.

This helper is intentionally standard-library-only. Production must execute a
root-owned copy with the root-owned system CPython using -I -B -S. It never
executes the provision virtual environment's interpreter: it verifies an exact,
sealed site-packages inventory and adds only that directory to the isolated
system interpreter before loading the canonical provisioner artifact.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import platform
import re
import runpy
import stat
import struct
import sys
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


EXPECTED_REQUIREMENTS = {
    "pip": "26.1.2",
    "psycopg2-binary": "2.9.12",
}
SEAL_KEYS = (
    "provision_lock_sha256",
    "provision_manifest_sha256",
    "provision_tree_sha256",
)
BUNDLE_CONTENT_SEAL_KEY = "bundle_content_sha256"
BUNDLE_CONTENT_DOMAIN = b"TW_MCP_BUNDLE_CONTENT_V1\0"
SYSTEM_PYTHON = Path("/usr/bin/python3.13")
SYSTEM_PREFIX = "/usr"
SYSTEM_STDLIB_PATH = (
    "/usr/lib/python313.zip",
    "/usr/lib/python3.13",
    "/usr/lib/python3.13/lib-dynload",
)
ROOT_UID = 0
ROOT_GID = 0
_REQUIREMENT_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+!-]*)(?:\s+\\)?"
)
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?:\s+\\)?")
_HEX_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class BootstrapError(RuntimeError):
    """A fail-closed provisioning bootstrap validation error."""


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display(path: Path) -> str:
    return os.fspath(path)


def _lstat(path: Path, label: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise BootstrapError(f"cannot inspect {label}: {_display(path)}") from exc


def _assert_secure_node(
    path: Path,
    label: str,
    *,
    kind: str | None = None,
    allow_symlink: bool = False,
) -> os.stat_result:
    metadata = _lstat(path, label)
    is_link = stat.S_ISLNK(metadata.st_mode)
    if is_link and not allow_symlink:
        raise BootstrapError(f"{label} must not be a symlink: {_display(path)}")
    if os.name != "nt":
        if metadata.st_uid != ROOT_UID or metadata.st_gid != ROOT_GID:
            raise BootstrapError(f"{label} is not root:root: {_display(path)}")
        if not is_link and stat.S_IMODE(metadata.st_mode) & 0o022:
            raise BootstrapError(f"{label} is group/other writable: {_display(path)}")
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
        raise BootstrapError(f"{label} has an unsafe hard link: {_display(path)}")
    if kind == "file" and not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError(f"{label} is not a regular file: {_display(path)}")
    if kind == "dir" and not stat.S_ISDIR(metadata.st_mode):
        raise BootstrapError(f"{label} is not a directory: {_display(path)}")
    return metadata


def _canonical_absolute(path: str | os.PathLike[str], label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or "\x00" in os.fspath(candidate):
        raise BootstrapError(f"{label} must be an absolute canonical path")
    _assert_secure_node(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError(f"cannot resolve {label}: {_display(candidate)}") from exc
    if candidate != resolved:
        raise BootstrapError(f"{label} is not canonical: {_display(candidate)}")
    return resolved


def _assert_exact_path(actual: Path, expected: Path, label: str) -> None:
    try:
        actual_resolved = actual.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError(f"cannot resolve {label}") from exc
    if actual != actual_resolved or actual_resolved != expected_resolved:
        raise BootstrapError(f"{label} is not the canonical sealed artifact")


def _assert_secure_ancestors(path: Path) -> None:
    current = path.parent
    while True:
        _assert_secure_node(current, "bundle ancestor", kind="dir")
        if current.parent == current:
            return
        current = current.parent


def _iter_tree(root: Path):
    """Yield a deterministic, non-following recursive inventory."""
    root_metadata = _assert_secure_node(root, "tree root", kind="dir")
    yield ".", root, root_metadata

    def visit(directory: Path, relative: PurePosixPath):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise BootstrapError(
                f"cannot list sealed tree: {_display(directory)}"
            ) from exc
        for entry in entries:
            child = directory / entry.name
            child_relative = relative / entry.name
            metadata = _assert_secure_node(
                child, "sealed tree entry", allow_symlink=True
            )
            yield child_relative.as_posix(), child, metadata
            if stat.S_ISDIR(metadata.st_mode):
                yield from visit(child, child_relative)
            elif not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
                raise BootstrapError(
                    f"sealed tree contains a special file: {_display(child)}"
                )

    yield from visit(root, PurePosixPath())


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, path, metadata in _iter_tree(root):
        record: dict[str, object] = {
            "path": relative,
            "mode": stat.S_IMODE(metadata.st_mode),
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
        }
        if stat.S_ISDIR(metadata.st_mode):
            record["type"] = "directory"
        elif stat.S_ISLNK(metadata.st_mode):
            record["type"] = "symlink"
            try:
                record["target"] = os.readlink(path)
            except OSError as exc:
                raise BootstrapError(
                    f"cannot read sealed symlink: {_display(path)}"
                ) from exc
        else:
            record["type"] = "file"
            record["size"] = metadata.st_size
            record["sha256"] = _sha256_file(path)
        digest.update(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _bundle_content_sha256(bundle: Path) -> str:
    """Hash the complete lstat-only bundle, excluding only its root .sealed.

    This independently duplicates the release builder's content-manifest
    format.  Keeping this implementation local prevents a trusted verifier
    call followed by a different root Python import boundary.
    """
    entries: list[tuple[bytes, Path, os.stat_result]] = []
    root_metadata = _assert_secure_node(bundle, "bundle manifest root", kind="dir")
    entries.append((b".", bundle, root_metadata))

    def collect(directory: Path, prefix: bytes) -> None:
        try:
            children = list(os.scandir(directory))
        except OSError as exc:
            raise BootstrapError(
                f"cannot list bundle manifest directory: {_display(directory)}"
            ) from exc
        for child in children:
            raw_name = os.fsencode(child.name)
            relative = raw_name if not prefix else prefix + b"/" + raw_name
            if relative == b".sealed":
                continue
            path = directory / child.name
            metadata = _assert_secure_node(
                path, "bundle manifest entry", allow_symlink=True
            )
            entries.append((relative, path, metadata))
            if stat.S_ISDIR(metadata.st_mode):
                collect(path, relative)
            elif not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
                raise BootstrapError(
                    f"bundle contains a special file: {_display(path)}"
                )

    collect(bundle, b"")
    digest = hashlib.sha256()
    digest.update(BUNDLE_CONTENT_DOMAIN)
    for relative, path, metadata in sorted(entries, key=lambda value: value[0]):
        if stat.S_ISDIR(metadata.st_mode):
            kind = b"D"
        elif stat.S_ISREG(metadata.st_mode):
            kind = b"F"
        elif stat.S_ISLNK(metadata.st_mode):
            kind = b"L"
        else:  # Defensive: collect rejects this before the stream is built.
            raise BootstrapError(f"unsupported bundle entry: {_display(path)}")
        digest.update(kind)
        digest.update(struct.pack(">I", stat.S_IMODE(metadata.st_mode)))
        digest.update(struct.pack(">Q", len(relative)))
        digest.update(relative)
        if kind == b"F":
            digest.update(struct.pack(">Q", metadata.st_size))
            digest.update(bytes.fromhex(_sha256_file(path)))
        elif kind == b"L":
            try:
                target = os.readlink(os.fsencode(path))
            except OSError as exc:
                raise BootstrapError(
                    f"cannot read bundle symlink: {_display(path)}"
                ) from exc
            if not isinstance(target, bytes):
                target = os.fsencode(target)
            digest.update(struct.pack(">Q", len(target)))
            digest.update(target)
    return digest.hexdigest()


def _parse_lock(lock: Path) -> tuple[dict[str, str], dict[str, tuple[str, ...]], bytes]:
    try:
        raw = lock.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BootstrapError("provision lock is not readable UTF-8") from exc
    if "\x00" in text:
        raise BootstrapError("provision lock contains a NUL byte")

    versions: dict[str, str] = {}
    hashes: dict[str, set[str]] = {}
    current: str | None = None
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = _REQUIREMENT_RE.fullmatch(line)
        if requirement:
            name = _normalize_distribution(requirement.group(1))
            if name in versions:
                raise BootstrapError(
                    f"duplicate provision requirement on line {number}"
                )
            versions[name] = requirement.group(2)
            hashes[name] = set()
            current = name
            continue
        lock_hash = _HASH_RE.fullmatch(line)
        if lock_hash and current is not None:
            if lock_hash.group(1) in hashes[current]:
                raise BootstrapError(f"duplicate provision hash on line {number}")
            hashes[current].add(lock_hash.group(1))
            continue
        raise BootstrapError(f"unsupported provision lock syntax on line {number}")

    if versions != EXPECTED_REQUIREMENTS:
        raise BootstrapError(
            "provision lock must contain exactly pip==26.1.2 and "
            "psycopg2-binary==2.9.12"
        )
    if any(not values for values in hashes.values()):
        raise BootstrapError("every provision requirement must have hashes")
    return (
        versions,
        {name: tuple(sorted(values)) for name, values in hashes.items()},
        raw,
    )


def _metadata_identity(dist_info: Path) -> tuple[str, str]:
    metadata_path = dist_info / "METADATA"
    _assert_secure_node(metadata_path, "distribution METADATA", kind="file")
    try:
        message = BytesParser().parsebytes(metadata_path.read_bytes())
    except OSError as exc:
        raise BootstrapError(
            f"cannot read distribution metadata: {_display(metadata_path)}"
        ) from exc
    names = message.get_all("Name", [])
    versions = message.get_all("Version", [])
    if len(names) != 1 or len(versions) != 1:
        raise BootstrapError(f"invalid distribution METADATA: {_display(dist_info)}")
    return _normalize_distribution(names[0]), versions[0]


def _record_target(
    raw_name: str, *, site_packages: Path, venv: Path
) -> tuple[Path, str]:
    if (
        not raw_name
        or "\x00" in raw_name
        or "\\" in raw_name
        or PurePosixPath(raw_name).is_absolute()
    ):
        raise BootstrapError(f"unsafe RECORD path: {raw_name!r}")
    pure = PurePosixPath(raw_name)
    candidate = site_packages.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(venv)
    except (OSError, ValueError) as exc:
        raise BootstrapError(
            f"RECORD path escapes the provision venv: {raw_name!r}"
        ) from exc

    current = venv
    for component in relative.parts:
        current = current / component
        metadata = _assert_secure_node(current, "RECORD target")
        if stat.S_ISLNK(metadata.st_mode):
            raise BootstrapError(f"RECORD target traverses a symlink: {raw_name!r}")
    metadata = _assert_secure_node(resolved, "RECORD target", kind="file")
    if not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError(f"RECORD target is not a regular file: {raw_name!r}")
    return resolved, relative.as_posix()


def _decode_record_hash(value: str) -> bytes:
    if not value.startswith("sha256="):
        raise BootstrapError("RECORD uses a non-sha256 digest")
    encoded = value.removeprefix("sha256=")
    if not encoded or re.fullmatch(r"[A-Za-z0-9_-]+", encoded) is None:
        raise BootstrapError("RECORD has an invalid sha256 digest")
    try:
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise BootstrapError("RECORD has an invalid sha256 digest") from exc
    if len(decoded) != hashlib.sha256().digest_size:
        raise BootstrapError("RECORD has an invalid sha256 digest length")
    return decoded


def _site_packages_files(site_packages: Path) -> set[str]:
    files: set[str] = set()
    for relative, path, metadata in _iter_tree(site_packages):
        if relative == ".":
            continue
        parts = PurePosixPath(relative).parts
        lowered = {part.lower() for part in parts}
        if any(part.lower().endswith(".pth") for part in parts) or lowered & {
            "sitecustomize",
            "sitecustomize.py",
            "usercustomize",
            "usercustomize.py",
        }:
            raise BootstrapError(
                f"site-packages contains startup customization: {relative}"
            )
        if stat.S_ISLNK(metadata.st_mode):
            raise BootstrapError(f"site-packages contains a symlink: {relative}")
        if stat.S_ISREG(metadata.st_mode):
            files.add(path.resolve(strict=True).as_posix())
    return files


def _manifest_sha256(
    *,
    versions: dict[str, str],
    lock_hashes: dict[str, tuple[str, ...]],
    file_entries: list[dict[str, object]],
) -> str:
    records: list[str] = []
    for name in sorted(versions):
        records.append(
            json.dumps(
                {
                    "type": "requirement",
                    "name": name,
                    "version": versions[name],
                    "lock_hashes": list(lock_hashes[name]),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    records.extend(
        sorted(
            json.dumps(entry, sort_keys=True, separators=(",", ":"))
            for entry in file_entries
        )
    )
    return _sha256_bytes(("\n".join(records) + "\n").encode("utf-8"))


def _validate_site_packages(
    *,
    site_packages: Path,
    venv: Path,
    versions: dict[str, str],
    lock_hashes: dict[str, tuple[str, ...]],
) -> str:
    _assert_secure_node(site_packages, "provision site-packages", kind="dir")
    actual_site_files = _site_packages_files(site_packages)

    try:
        top_level = list(site_packages.iterdir())
    except OSError as exc:
        raise BootstrapError("cannot list provision site-packages") from exc
    for child in top_level:
        lowered = child.name.lower()
        if lowered.endswith((".egg-info", ".egg-link")):
            raise BootstrapError(f"legacy package metadata is forbidden: {child.name}")

    dist_infos = sorted(
        (child for child in top_level if child.name.lower().endswith(".dist-info")),
        key=lambda child: child.name,
    )
    if len(dist_infos) != len(versions):
        raise BootstrapError("unexpected distribution count in provision site-packages")

    identities: dict[str, tuple[str, Path]] = {}
    for dist_info in dist_infos:
        _assert_secure_node(dist_info, "dist-info directory", kind="dir")
        name, version = _metadata_identity(dist_info)
        if name in identities:
            raise BootstrapError(f"duplicate installed distribution: {name}")
        identities[name] = (version, dist_info)
    if {name: value[0] for name, value in identities.items()} != versions:
        raise BootstrapError("installed provision distributions do not match the lock")

    recorded_targets: dict[str, str] = {}
    recorded_site_files: set[str] = set()
    file_entries: list[dict[str, object]] = []
    for name in sorted(identities):
        version, dist_info = identities[name]
        record_path = dist_info / "RECORD"
        _assert_secure_node(record_path, "distribution RECORD", kind="file")
        try:
            record_text = record_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise BootstrapError(f"cannot read RECORD for {name}") from exc
        rows = csv.reader(io.StringIO(record_text, newline=""))
        row_count = 0
        saw_own_record = False
        for row_number, row in enumerate(rows, 1):
            if len(row) != 3:
                raise BootstrapError(f"{name} RECORD row {row_number} is malformed")
            raw_name, recorded_hash, recorded_size = row
            target, relative = _record_target(
                raw_name, site_packages=site_packages, venv=venv
            )
            canonical = target.as_posix()
            if canonical in recorded_targets:
                raise BootstrapError(
                    f"duplicate RECORD target shared by {recorded_targets[canonical]} and {name}"
                )
            recorded_targets[canonical] = name
            if target == record_path.resolve(strict=True):
                saw_own_record = True
            if target.is_relative_to(site_packages):
                recorded_site_files.add(canonical)

            metadata = target.stat()
            actual_digest = bytes.fromhex(_sha256_file(target))
            if bool(recorded_hash) != bool(recorded_size):
                raise BootstrapError(f"{name} RECORD hash/size pair is incomplete")
            if recorded_hash:
                expected_digest = _decode_record_hash(recorded_hash)
                if not hmac.compare_digest(actual_digest, expected_digest):
                    raise BootstrapError(f"{name} RECORD hash mismatch: {relative}")
                if (
                    not recorded_size.isdecimal()
                    or str(int(recorded_size)) != recorded_size
                ):
                    raise BootstrapError(f"{name} RECORD size is invalid: {relative}")
                if int(recorded_size) != metadata.st_size:
                    raise BootstrapError(f"{name} RECORD size mismatch: {relative}")
            elif target != record_path.resolve(strict=True) and target.suffix != ".pyc":
                raise BootstrapError(
                    f"{name} RECORD omits integrity metadata for {relative}"
                )
            file_entries.append(
                {
                    "type": "installed-file",
                    "distribution": name,
                    "version": version,
                    "path": relative,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "size": metadata.st_size,
                    "sha256": actual_digest.hex(),
                    "record_hash_present": bool(recorded_hash),
                }
            )
            row_count += 1
        if row_count == 0 or not saw_own_record:
            raise BootstrapError(f"{name} RECORD is empty or does not own itself")

    if actual_site_files != recorded_site_files:
        extra = sorted(actual_site_files - recorded_site_files)
        missing = sorted(recorded_site_files - actual_site_files)
        details = []
        if extra:
            details.append(f"unrecorded={len(extra)}")
        if missing:
            details.append(f"missing={len(missing)}")
        raise BootstrapError(
            "site-packages is not the exact RECORD allowlist"
            + (f" ({', '.join(details)})" if details else "")
        )
    return _manifest_sha256(
        versions=versions, lock_hashes=lock_hashes, file_entries=file_entries
    )


def _inventory(bundle: Path, lock: Path) -> tuple[dict[str, str], Path]:
    versions, lock_hashes, raw_lock = _parse_lock(lock)
    venv = bundle / "provision-venv"
    _assert_secure_node(venv, "provision venv", kind="dir")
    site_packages = venv / "lib" / "python3.13" / "site-packages"
    manifest = _validate_site_packages(
        site_packages=site_packages,
        venv=venv,
        versions=versions,
        lock_hashes=lock_hashes,
    )
    values = {
        "provision_lock_sha256": _sha256_bytes(raw_lock),
        "provision_manifest_sha256": manifest,
        "provision_tree_sha256": _tree_sha256(venv),
    }
    return values, site_packages


def _read_seal(seal: Path) -> dict[str, str]:
    _assert_secure_node(seal, "release seal", kind="file")
    try:
        text = seal.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise BootstrapError("release seal is not readable ASCII") from exc
    values: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise BootstrapError(f"malformed release seal line {number}")
        key, value = line.split("=", 1)
        if key in values:
            raise BootstrapError(f"duplicate release seal key: {key}")
        if not key or not value or key.strip() != key or value.strip() != value:
            raise BootstrapError(f"malformed release seal line {number}")
        values[key] = value
    return values


def _verify_seal(seal: Path, inventory: dict[str, str], *, bundle: Path) -> None:
    values = _read_seal(seal)
    for key in SEAL_KEYS:
        expected = values.get(key)
        if expected is None or _HEX_SHA256_RE.fullmatch(expected) is None:
            raise BootstrapError(f"release seal lacks a valid {key}")
        if not hmac.compare_digest(expected, inventory[key]):
            raise BootstrapError(
                f"sealed {key} does not match the provision environment"
            )
    expected_content = values.get(BUNDLE_CONTENT_SEAL_KEY)
    if expected_content is None or _HEX_SHA256_RE.fullmatch(expected_content) is None:
        raise BootstrapError(f"release seal lacks a valid {BUNDLE_CONTENT_SEAL_KEY}")
    actual_content = _bundle_content_sha256(bundle)
    if not hmac.compare_digest(expected_content, actual_content):
        raise BootstrapError(
            "sealed bundle content does not match the root import boundary"
        )


def _require_hardened_runtime() -> None:
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 13):
        raise BootstrapError("provision bootstrap requires system CPython 3.13")
    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.no_user_site
        or not sys.flags.ignore_environment
        or not sys.flags.safe_path
        or not sys.dont_write_bytecode
    ):
        raise BootstrapError("provision bootstrap requires Python -I -B -S")
    get_euid = getattr(os, "geteuid", None)
    if get_euid is None or get_euid() != 0:
        raise BootstrapError("provision bootstrap must run as root")
    executable = Path(sys.executable)
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("cannot resolve the system Python executable") from exc
    if (
        executable != SYSTEM_PYTHON
        or resolved != SYSTEM_PYTHON
        or Path(sys._base_executable) != SYSTEM_PYTHON
        or sys.prefix != SYSTEM_PREFIX
        or sys.base_prefix != SYSTEM_PREFIX
        or tuple(sys.path) != SYSTEM_STDLIB_PATH
    ):
        raise BootstrapError(
            "provision bootstrap requires the exact /usr/bin/python3.13 system runtime"
        )
    _assert_secure_node(resolved, "system Python executable", kind="file")
    _assert_secure_ancestors(resolved)
    forbidden_startup_modules = {"site", "sitecustomize", "usercustomize"}
    if forbidden_startup_modules.intersection(sys.modules):
        raise BootstrapError(
            "Python startup customization loaded before provision verification"
        )


def _prepare(
    *, bundle_arg: str, lock_arg: str, require_seal: bool
) -> tuple[Path, Path, dict[str, str], Path]:
    bundle = _canonical_absolute(bundle_arg, "bundle")
    _assert_secure_node(bundle, "bundle", kind="dir")
    _assert_secure_ancestors(bundle)
    lock = _canonical_absolute(lock_arg, "provision lock")
    _assert_exact_path(lock, bundle / "artifacts" / "provision.lock", "provision lock")
    _assert_secure_node(lock, "provision lock", kind="file")

    helper = Path(__file__)
    _assert_secure_node(helper, "provision bootstrap", kind="file")
    _assert_exact_path(
        helper,
        bundle / "artifacts" / "mcp-provision-bootstrap.py",
        "provision bootstrap",
    )
    inventory, site_packages = _inventory(bundle, lock)
    if require_seal:
        _verify_seal(bundle / ".sealed", inventory, bundle=bundle)
    return bundle, lock, inventory, site_packages


def _emit_inventory(inventory: dict[str, str]) -> None:
    for key in SEAL_KEYS:
        print(f"{key}={inventory[key]}")


def _command_inventory(arguments: argparse.Namespace) -> int:
    _bundle, _lock, inventory, _site_packages = _prepare(
        bundle_arg=arguments.bundle,
        lock_arg=arguments.lock,
        require_seal=False,
    )
    _emit_inventory(inventory)
    return 0


def _command_verify(arguments: argparse.Namespace) -> int:
    _bundle, _lock, inventory, _site_packages = _prepare(
        bundle_arg=arguments.bundle,
        lock_arg=arguments.lock,
        require_seal=True,
    )
    _emit_inventory(inventory)
    return 0


def _command_run(arguments: argparse.Namespace) -> int:
    bundle, _lock, _inventory_values, site_packages = _prepare(
        bundle_arg=arguments.bundle,
        lock_arg=arguments.lock,
        require_seal=True,
    )
    provisioner = _canonical_absolute(arguments.provisioner, "provisioner")
    _assert_exact_path(
        provisioner,
        bundle / "artifacts" / "provision-mcp-key.py",
        "provisioner",
    )
    _assert_secure_node(provisioner, "provisioner", kind="file")

    forwarded = list(arguments.provisioner_arguments)
    if forwarded and forwarded[0] == "--":
        forwarded.pop(0)
    if os.fspath(site_packages) in sys.path:
        raise BootstrapError("provision site-packages was loaded before verification")
    if any(
        name == "apiserver" or name.startswith("apiserver.") for name in sys.modules
    ):
        raise BootstrapError(
            "candidate application modules were loaded before provisioning"
        )

    # Keep the root-owned system standard library ahead of the sealed third-party
    # dependency directory.  The provision site is deliberately last: even if a
    # future dependency-validation bug missed a stdlib-shadowing name, that file
    # must not become the implementation imported by this root process.
    sys.path[:] = [*SYSTEM_STDLIB_PATH, os.fspath(site_packages)]
    sys.argv = [os.fspath(provisioner), *forwarded]
    runpy.run_path(os.fspath(provisioner), run_name="__main__")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the sealed MCP provisioning dependency boundary"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("inventory", _command_inventory),
        ("verify", _command_verify),
    ):
        command = commands.add_parser(name)
        command.add_argument("--bundle", required=True)
        command.add_argument("--lock", required=True)
        command.set_defaults(handler=handler)
    run = commands.add_parser("run")
    run.add_argument("--bundle", required=True)
    run.add_argument("--lock", required=True)
    run.add_argument("--provisioner", required=True)
    run.add_argument("provisioner_arguments", nargs=argparse.REMAINDER)
    run.set_defaults(handler=_command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        _require_hardened_runtime()
        arguments = _parser().parse_args(argv)
        return arguments.handler(arguments)
    except BootstrapError as exc:
        print(f"MCP provision bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
