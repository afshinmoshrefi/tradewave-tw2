#!/usr/bin/python3
"""Trusted, stdlib-only inventory for an offline MCP Python dependency bundle.

This program is intended to be copied into the root-controlled transient deploy
payload and invoked with ``/usr/bin/python3.13 -I -B -S``.  It never imports or
executes code from a wheel or from the target environment.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import email.parser
import email.policy
import hashlib
import io
import itertools
import json
import os
import re
import secrets
import shlex
import stat
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, Iterable


SCHEMA_VERSION = 1
MAX_LOCK_BYTES = 2 * 1024 * 1024
MAX_PACKAGES = 256
MAX_WHEEL_BYTES = 256 * 1024 * 1024
MAX_TOTAL_WHEEL_BYTES = 2 * 1024 * 1024 * 1024
MAX_WHEEL_MEMBERS = 20_000
MAX_TOTAL_MEMBERS = 250_000
MAX_INSTALLED_NODES = 250_000
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_WHEEL_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_PATH_LENGTH = 4096
COPY_CHUNK = 1024 * 1024
INSTALL_PYTHON_VERSION = "3.13"
INSTALL_ARCHITECTURE = "x86_64"
INSTALL_GLIBC = "2.39"
INSTALL_SCRIPT_PYTHON = "/usr/bin/python3.13"
TRUSTED_WHEELHOUSE_UID = 0
TRUSTED_WHEELHOUSE_GID = 0
_SAFE_WHEEL_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+!-]{0,250}\.whl\Z")
_PROJECT_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?\Z")
_SAFE_SCRIPT_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}\Z")
_ENTRY_POINT_VALUE = re.compile(
    r"\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r"\s*:\s*([A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?:\[[A-Za-z0-9_,. -]+\])?\s*\Z"
)
_HASH_OPTION = re.compile(r"--hash=sha256:([0-9a-f]{64})\Z")
_RECORD_HASH = re.compile(r"sha256=([A-Za-z0-9_-]{43})\Z")


class BundleError(RuntimeError):
    """A deterministic, user-presentable validation failure."""


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    normalized_name: str
    version: str
    hashes: frozenset[str]


@dataclass(frozen=True)
class Target:
    python_major: int
    python_minor: int
    architecture: str
    glibc_major: int
    glibc_minor: int


@dataclass(frozen=True)
class WheelFilename:
    distribution: str
    version: str
    build: str | None
    tags: frozenset[str]


@dataclass(frozen=True)
class WheelInventory:
    filename: str
    name: str
    normalized_name: str
    version: str
    sha256: str
    size: int
    tags: tuple[str, ...]
    root_is_purelib: bool
    record_sha256: str
    member_count: int
    uncompressed_size: int


@dataclass
class ResourceBudget:
    compressed: int = 0
    uncompressed: int = 0
    members: int = 0


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonicalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _read_regular_file(path: str, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    # The Windows CRT otherwise translates CRLF and treats 0x1a as EOF even
    # when using os.read().  That would make a digest describe bytes other
    # than the bytes on disk.
    flags |= getattr(os, "O_BINARY", 0)
    # Opening a FIFO read-only can otherwise block before fstat() has a chance
    # to reject it.  O_NONBLOCK has no effect on a genuine regular file.
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise BundleError(f"cannot safely inspect regular file: {path}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
    ):
        raise BundleError(f"file is not a single-link regular file: {path}")
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BundleError(f"cannot safely open regular file: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BundleError(f"file is not a single-link regular file: {path}")
        if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise BundleError(f"file changed while it was opened: {path}")
        if metadata.st_size > limit:
            raise BundleError(f"file exceeds its size limit: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(COPY_CHUNK, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise BundleError(f"file exceeds its size limit: {path}")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_ctime_ns,
            after.st_mtime_ns,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_ctime_ns,
            metadata.st_mtime_ns,
        ):
            raise BundleError(f"file changed while it was read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def parse_lock(path: str) -> tuple[dict[str, LockedRequirement], str]:
    raw = _read_regular_file(path, MAX_LOCK_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError("lock file is not UTF-8") from exc

    logical: list[tuple[int, str]] = []
    pending = ""
    pending_line = 0
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not pending:
            pending_line = line_number
        pending = f"{pending} {line}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical.append((pending_line, pending))
        pending = ""
    if pending:
        raise BundleError(f"{path}:{pending_line}: unterminated continuation")

    requirements: dict[str, LockedRequirement] = {}
    for line_number, line in logical:
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError as exc:
            raise BundleError(f"{path}:{line_number}: malformed lock entry") from exc
        if len(tokens) < 2:
            raise BundleError(f"{path}:{line_number}: requirement has no hashes")
        requirement, *options = tokens
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[A-Za-z0-9,._-]+\])?==([^\s;@]+)",
            requirement,
        )
        if match is None:
            raise BundleError(f"{path}:{line_number}: requirement is not an exact pin")
        name, version = match.groups()
        if not _PROJECT_NAME.fullmatch(name) or not version:
            raise BundleError(f"{path}:{line_number}: invalid requirement identity")
        hashes: set[str] = set()
        for option in options:
            hash_match = _HASH_OPTION.fullmatch(option)
            if hash_match is None:
                raise BundleError(f"{path}:{line_number}: unsupported lock option")
            if hash_match.group(1) in hashes:
                raise BundleError(f"{path}:{line_number}: duplicate lock hash")
            hashes.add(hash_match.group(1))
        normalized = canonicalize_name(name)
        if normalized in requirements:
            raise BundleError(
                f"{path}:{line_number}: duplicate locked project {normalized}"
            )
        requirements[normalized] = LockedRequirement(
            name=name,
            normalized_name=normalized,
            version=version,
            hashes=frozenset(hashes),
        )
        if len(requirements) > MAX_PACKAGES:
            raise BundleError("lock contains too many packages")
    if not requirements:
        raise BundleError("lock contains no requirements")
    return requirements, _sha256_bytes(raw)


def validate_lock(*, lock: str) -> dict[str, object]:
    requirements, lock_sha256 = parse_lock(lock)
    return {
        "kind": "dependency-lock",
        "lock_sha256": lock_sha256,
        "package_count": len(requirements),
        "schema": SCHEMA_VERSION,
    }


def _expand_tag(value: str) -> frozenset[str]:
    fields = value.split("-")
    if len(fields) != 3 or any(not field for field in fields):
        raise BundleError(f"invalid wheel tag: {value}")
    pieces = [field.split(".") for field in fields]
    valid = re.compile(r"[A-Za-z0-9_]+\Z")
    if any(not valid.fullmatch(piece) for group in pieces for piece in group):
        raise BundleError(f"invalid wheel tag: {value}")
    return frozenset("-".join(item) for item in itertools.product(*pieces))


def parse_wheel_filename(filename: str) -> WheelFilename:
    if not _SAFE_WHEEL_FILENAME.fullmatch(filename):
        raise BundleError(f"unsafe wheel filename: {filename!r}")
    components = filename[:-4].split("-")
    if len(components) not in (5, 6):
        raise BundleError(f"invalid wheel filename: {filename}")
    distribution, version = components[0], components[1]
    build = components[2] if len(components) == 6 else None
    if build is not None and re.fullmatch(r"[0-9][A-Za-z0-9_]*", build) is None:
        raise BundleError(f"invalid wheel build tag: {filename}")
    tag_text = "-".join(components[-3:])
    return WheelFilename(distribution, version, build, _expand_tag(tag_text))


def _parse_target(python_version: str, architecture: str, glibc: str) -> Target:
    python_match = re.fullmatch(r"(\d+)\.(\d+)", python_version)
    glibc_match = re.fullmatch(r"(\d+)\.(\d+)", glibc)
    if python_match is None or glibc_match is None:
        raise BundleError("Python and glibc versions must have major.minor form")
    if architecture not in {"x86_64", "aarch64"}:
        raise BundleError("unsupported target architecture")
    return Target(
        int(python_match.group(1)),
        int(python_match.group(2)),
        architecture,
        int(glibc_match.group(1)),
        int(glibc_match.group(2)),
    )


def _platform_compatible(value: str, target: Target) -> bool:
    if value == "any":
        return True
    if value == f"linux_{target.architecture}":
        return True
    legacy = {
        f"manylinux1_{target.architecture}": (2, 5),
        f"manylinux2010_{target.architecture}": (2, 12),
        f"manylinux2014_{target.architecture}": (2, 17),
    }
    required = legacy.get(value)
    if required is None:
        match = re.fullmatch(r"manylinux_(\d+)_(\d+)_(x86_64|aarch64)", value)
        if match is None or match.group(3) != target.architecture:
            return False
        required = (int(match.group(1)), int(match.group(2)))
    return required <= (target.glibc_major, target.glibc_minor)


def _tag_compatible(value: str, target: Target) -> bool:
    interpreter, abi, platform_tag = value.split("-")
    if not _platform_compatible(platform_tag, target):
        return False
    current = f"{target.python_major}{target.python_minor}"
    if interpreter == f"py{target.python_major}" or interpreter == f"py{current}":
        return abi == "none"
    if interpreter == f"cp{current}":
        return abi in {f"cp{current}", "abi3", "none"}
    match = re.fullmatch(r"cp(\d)(\d+)", interpreter)
    if match and int(match.group(1)) == target.python_major:
        return abi == "abi3" and int(match.group(2)) <= target.python_minor
    return False


def _safe_archive_name(value: str) -> str:
    if (
        not value
        or len(value.encode("utf-8", "strict")) > MAX_ARCHIVE_PATH_LENGTH
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or unicodedata.normalize("NFC", value) != value
    ):
        raise BundleError(f"unsafe wheel member path: {value!r}")
    is_directory = value.endswith("/")
    core = value[:-1] if is_directory else value
    parts = core.split("/")
    if not core or any(part in {"", ".", ".."} for part in parts):
        raise BundleError(f"unsafe wheel member path: {value!r}")
    if re.match(r"[A-Za-z]:", parts[0]):
        raise BundleError(f"unsafe wheel member path: {value!r}")
    return core + ("/" if is_directory else "")


def _member_kind(info: zipfile.ZipInfo) -> str:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(unix_mode) if unix_mode else 0
    if info.is_dir():
        if kind not in (0, stat.S_IFDIR):
            raise BundleError(
                f"wheel directory has an invalid file type: {info.filename}"
            )
        if info.file_size or info.compress_size:
            raise BundleError(f"wheel directory has content: {info.filename}")
        return "directory"
    if kind not in (0, stat.S_IFREG):
        raise BundleError(f"wheel contains a non-regular member: {info.filename}")
    return "file"


def _bounded_member_bytes(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int
) -> bytes:
    if info.file_size > limit:
        raise BundleError(f"wheel metadata exceeds its limit: {info.filename}")
    with archive.open(info, "r") as handle:
        data = handle.read(limit + 1)
        if len(data) > limit or handle.read(1):
            raise BundleError(f"wheel metadata exceeds its limit: {info.filename}")
    if len(data) != info.file_size:
        raise BundleError(f"wheel member size changed while reading: {info.filename}")
    return data


def _metadata_headers(raw: bytes, label: str) -> email.message.Message:
    if b"\x00" in raw:
        raise BundleError(f"{label} contains NUL")
    try:
        return email.parser.BytesParser(policy=email.policy.compat32).parsebytes(raw)
    except Exception as exc:
        raise BundleError(f"cannot parse {label}") from exc


def _decode_record_hash(value: str) -> bytes:
    match = _RECORD_HASH.fullmatch(value)
    if match is None:
        raise BundleError("RECORD contains a missing or non-SHA-256 hash")
    return base64.urlsafe_b64decode(match.group(1) + "=")


def _validate_record(
    archive: zipfile.ZipFile,
    files: dict[str, zipfile.ZipInfo],
    record_name: str,
) -> str:
    record_raw = _bounded_member_bytes(archive, files[record_name], MAX_RECORD_BYTES)
    try:
        record_text = record_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError("wheel RECORD is not UTF-8") from exc
    rows: dict[str, tuple[str, str]] = {}
    canonical_rows: set[str] = set()
    try:
        reader = csv.reader(io.StringIO(record_text, newline=""))
        for row in reader:
            if len(row) != 3:
                raise BundleError("wheel RECORD row does not have three fields")
            path = _safe_archive_name(row[0])
            if path.endswith("/") or path in rows:
                raise BundleError("wheel RECORD has a duplicate or directory row")
            collision = path.casefold()
            if collision in canonical_rows:
                raise BundleError("wheel RECORD has a case-colliding row")
            canonical_rows.add(collision)
            rows[path] = (row[1], row[2])
    except csv.Error as exc:
        raise BundleError("wheel RECORD is malformed") from exc
    if set(rows) != set(files):
        missing = sorted(set(files) - set(rows))[:3]
        extra = sorted(set(rows) - set(files))[:3]
        raise BundleError(
            f"wheel RECORD allowlist mismatch; missing={missing}, extra={extra}"
        )

    for name, info in files.items():
        hash_text, size_text = rows[name]
        if name == record_name:
            if hash_text or size_text:
                raise BundleError("wheel RECORD must leave its own hash and size empty")
            continue
        expected_hash = _decode_record_hash(hash_text)
        if (
            not size_text.isascii()
            or not size_text.isdigit()
            or int(size_text) != info.file_size
        ):
            raise BundleError(f"wheel RECORD size mismatch: {name}")
        digest = hashlib.sha256()
        total = 0
        with archive.open(info, "r") as handle:
            while True:
                chunk = handle.read(COPY_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
                if total > info.file_size:
                    raise BundleError(f"wheel member exceeds declared size: {name}")
        if total != info.file_size or digest.digest() != expected_hash:
            raise BundleError(f"wheel RECORD hash/size mismatch: {name}")
    return _sha256_bytes(record_raw)


def inspect_wheel(
    handle: BinaryIO,
    *,
    filename: str,
    archive_sha256: str,
    archive_size: int,
    requirement: LockedRequirement,
    target: Target,
    budget: ResourceBudget,
) -> WheelInventory:
    parsed_filename = parse_wheel_filename(filename)
    if canonicalize_name(parsed_filename.distribution) != requirement.normalized_name:
        raise BundleError(f"wheel filename project does not match lock: {filename}")
    normalized_version = re.sub(r"[^A-Za-z0-9.]+", "_", requirement.version)
    if parsed_filename.version not in {requirement.version, normalized_version}:
        raise BundleError(f"wheel filename version does not match lock: {filename}")
    if not any(_tag_compatible(tag, target) for tag in parsed_filename.tags):
        raise BundleError(f"wheel is incompatible with the declared target: {filename}")

    try:
        archive = zipfile.ZipFile(handle, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundleError(f"wheel is not a valid ZIP archive: {filename}") from exc
    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_WHEEL_MEMBERS:
            raise BundleError(f"wheel member-count limit exceeded: {filename}")
        budget.members += len(infos)
        if budget.members > MAX_TOTAL_MEMBERS:
            raise BundleError("wheel-set member-count limit exceeded")
        names: set[str] = set()
        canonical_names: set[str] = set()
        files: dict[str, zipfile.ZipInfo] = {}
        uncompressed = 0
        for info in infos:
            name = _safe_archive_name(info.filename)
            if name in names or name.casefold() in canonical_names:
                raise BundleError(
                    f"wheel has duplicate/colliding member names: {filename}"
                )
            names.add(name)
            canonical_names.add(name.casefold())
            if info.flag_bits & 0x1:
                raise BundleError(f"wheel contains an encrypted member: {filename}")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise BundleError(
                    f"wheel uses an unsupported compression method: {filename}"
                )
            kind = _member_kind(info)
            if info.file_size > MAX_MEMBER_BYTES:
                raise BundleError(f"wheel member exceeds its size limit: {filename}")
            if info.file_size and (
                info.compress_size == 0
                or info.file_size > info.compress_size * MAX_COMPRESSION_RATIO
            ):
                raise BundleError(
                    f"wheel member exceeds compression-ratio limit: {filename}"
                )
            uncompressed += info.file_size
            if uncompressed > MAX_WHEEL_UNCOMPRESSED:
                raise BundleError(f"wheel uncompressed-size limit exceeded: {filename}")
            if kind == "file":
                files[name] = info
        budget.compressed += archive_size
        budget.uncompressed += uncompressed
        if (
            budget.compressed > MAX_TOTAL_WHEEL_BYTES
            or budget.uncompressed > MAX_TOTAL_UNCOMPRESSED
        ):
            raise BundleError("wheel-set resource limit exceeded")

        dist_info_roots = {
            name.split("/", 1)[0]
            for name in names
            if "/" in name and name.split("/", 1)[0].endswith(".dist-info")
        }
        if len(dist_info_roots) != 1:
            raise BundleError(
                f"wheel must contain exactly one dist-info directory: {filename}"
            )
        dist_info = next(iter(dist_info_roots))
        metadata_name = f"{dist_info}/METADATA"
        wheel_name = f"{dist_info}/WHEEL"
        record_name = f"{dist_info}/RECORD"
        if any(
            required not in files
            for required in (metadata_name, wheel_name, record_name)
        ):
            raise BundleError(
                f"wheel is missing METADATA, WHEEL, or RECORD: {filename}"
            )

        metadata = _metadata_headers(
            _bounded_member_bytes(archive, files[metadata_name], MAX_METADATA_BYTES),
            "METADATA",
        )
        name = metadata.get("Name")
        version = metadata.get("Version")
        if (
            not isinstance(name, str)
            or not _PROJECT_NAME.fullmatch(name)
            or canonicalize_name(name) != requirement.normalized_name
            or version != requirement.version
        ):
            raise BundleError(
                f"wheel METADATA identity does not match lock: {filename}"
            )

        wheel_metadata = _metadata_headers(
            _bounded_member_bytes(archive, files[wheel_name], MAX_METADATA_BYTES),
            "WHEEL",
        )
        wheel_version = wheel_metadata.get("Wheel-Version")
        purelib = wheel_metadata.get("Root-Is-Purelib")
        tag_values = wheel_metadata.get_all("Tag") or []
        if not isinstance(wheel_version, str) or not wheel_version.startswith("1."):
            raise BundleError(f"unsupported Wheel-Version: {filename}")
        if purelib not in {"true", "false"}:
            raise BundleError(f"invalid Root-Is-Purelib: {filename}")
        metadata_tags: set[str] = set()
        for tag in tag_values:
            metadata_tags.update(_expand_tag(str(tag)))
        if not metadata_tags or not metadata_tags.issubset(parsed_filename.tags):
            raise BundleError(f"WHEEL tags do not match its filename: {filename}")
        if not any(_tag_compatible(tag, target) for tag in metadata_tags):
            raise BundleError(f"WHEEL metadata is incompatible with target: {filename}")
        record_sha = _validate_record(archive, files, record_name)

    return WheelInventory(
        filename=filename,
        name=name,
        normalized_name=requirement.normalized_name,
        version=version,
        sha256=archive_sha256,
        size=archive_size,
        tags=tuple(sorted(parsed_filename.tags)),
        root_is_purelib=purelib == "true",
        record_sha256=record_sha,
        member_count=len(infos),
        uncompressed_size=uncompressed,
    )


def _open_directory(path: str) -> int:
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise BundleError(f"directory path must be canonical and absolute: {path}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BundleError(f"cannot safely open directory: {path}") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise BundleError(f"path is not a directory: {path}")
    return descriptor


def _copy_and_hash(source_fd: int, destination_fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = os.read(source_fd, COPY_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_WHEEL_BYTES:
            raise BundleError("wheel exceeds its archive-size limit")
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            if written <= 0:
                raise BundleError("short write while preserving wheel")
            view = view[written:]
    return digest.hexdigest(), total


def _wheelhouse_manifest(
    *,
    inventories: dict[str, WheelInventory],
    lock_sha256: str,
    target: Target,
) -> dict[str, object]:
    wheels = [
        {
            "filename": item.filename,
            "member_count": item.member_count,
            "name": item.name,
            "normalized_name": item.normalized_name,
            "record_sha256": item.record_sha256,
            "root_is_purelib": item.root_is_purelib,
            "sha256": item.sha256,
            "size": item.size,
            "tags": list(item.tags),
            "uncompressed_size": item.uncompressed_size,
            "version": item.version,
        }
        for item in sorted(
            inventories.values(), key=lambda value: value.normalized_name
        )
    ]
    result: dict[str, object] = {
        "architecture": target.architecture,
        "glibc": f"{target.glibc_major}.{target.glibc_minor}",
        "kind": "wheelhouse",
        "lock_sha256": lock_sha256,
        "python_version": f"{target.python_major}.{target.python_minor}",
        "schema": SCHEMA_VERSION,
        "wheel_count": len(wheels),
        "wheels": wheels,
    }
    result["wheel_manifest_sha256"] = _sha256_bytes(_canonical_json(result))
    return result


def _path_must_not_exist(path: str) -> None:
    if os.path.lexists(path):
        raise BundleError("wheelhouse destination must not preexist")


def _cleanup_path_staging(temporary_path: str, filenames: Iterable[str]) -> None:
    for filename in filenames:
        path = os.path.join(temporary_path, filename)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    try:
        os.chmod(temporary_path, 0o700)
    except OSError:
        pass
    try:
        os.rmdir(temporary_path)
    except FileNotFoundError:
        pass


def _stage_wheels_by_path(
    *,
    requirements: dict[str, LockedRequirement],
    lock_sha256: str,
    source: str,
    destination: str,
    target: Target,
) -> dict[str, object]:
    """Portable fallback for platforms without POSIX dir-fd operations.

    The production path is the dir-fd implementation below.  This fallback is
    deliberately limited to platforms (currently Windows) where Python cannot
    open directories or use the required *at operations.  It retains the same
    validation and no-replacement semantics for development and CI.
    """

    if not os.path.isabs(source) or os.path.normpath(source) != source:
        raise BundleError("wheel source path must be canonical and absolute")
    source_stat = os.lstat(source)
    if not stat.S_ISDIR(source_stat.st_mode) or stat.S_ISLNK(source_stat.st_mode):
        raise BundleError("wheel source is not a real directory")
    destination = os.path.abspath(destination)
    parent_path, destination_name = os.path.split(destination)
    if not destination_name or os.path.normpath(destination) != destination:
        raise BundleError("destination must be a canonical absolute path")
    parent_stat = os.lstat(parent_path)
    if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
        raise BundleError("wheelhouse parent is not a real directory")
    _path_must_not_exist(destination)

    temporary = f".{destination_name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    temporary_path = os.path.join(parent_path, temporary)
    copied_names: list[str] = []
    try:
        try:
            os.mkdir(temporary_path, 0o700)
        except OSError as exc:
            raise BundleError(
                "cannot create protected wheel staging directory"
            ) from exc
        names = sorted(os.listdir(source))
        if len(names) != len(requirements) or len(names) > MAX_PACKAGES:
            raise BundleError(
                "wheel directory must contain exactly one file per locked package"
            )

        inventories: dict[str, WheelInventory] = {}
        budget = ResourceBudget()
        binary = getattr(os, "O_BINARY", 0)
        for filename in names:
            parsed = parse_wheel_filename(filename)
            normalized = canonicalize_name(parsed.distribution)
            requirement = requirements.get(normalized)
            if requirement is None:
                raise BundleError(f"wheel is not present in the lock: {filename}")
            if normalized in inventories:
                raise BundleError(
                    f"multiple wheels selected for locked project: {normalized}"
                )

            source_path = os.path.join(source, filename)
            before = os.lstat(source_path)
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > MAX_WHEEL_BYTES
            ):
                raise BundleError(
                    f"wheel is not a bounded single-link regular file: {filename}"
                )
            source_flags = os.O_RDONLY | binary | getattr(os, "O_CLOEXEC", 0)
            source_flags |= getattr(os, "O_NONBLOCK", 0)
            try:
                source_fd = os.open(source_path, source_flags)
            except OSError as exc:
                raise BundleError(
                    f"wheel is not a safe regular file: {filename}"
                ) from exc
            destination_path = os.path.join(temporary_path, filename)
            destination_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | binary
            destination_flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                opened = os.fstat(source_fd)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino, opened.st_size)
                    != (before.st_dev, before.st_ino, before.st_size)
                ):
                    raise BundleError(f"wheel changed while opening: {filename}")
                destination_fd = os.open(destination_path, destination_flags, 0o600)
                copied_names.append(filename)
                try:
                    archive_sha256, archive_size = _copy_and_hash(
                        source_fd, destination_fd
                    )
                    if archive_sha256 not in requirement.hashes:
                        raise BundleError(
                            f"wheel SHA-256 is not authorized by lock: {filename}"
                        )
                    if archive_size != before.st_size:
                        raise BundleError(
                            f"wheel size changed while copying: {filename}"
                        )
                    os.fsync(destination_fd)
                    os.lseek(destination_fd, 0, os.SEEK_SET)
                    with os.fdopen(
                        os.dup(destination_fd), "rb", closefd=True
                    ) as handle:
                        inventory = inspect_wheel(
                            handle,
                            filename=filename,
                            archive_sha256=archive_sha256,
                            archive_size=archive_size,
                            requirement=requirement,
                            target=target,
                            budget=budget,
                        )
                    os.chmod(destination_path, 0o444)
                finally:
                    os.close(destination_fd)
                inventories[normalized] = inventory
            finally:
                os.close(source_fd)

        if set(inventories) != set(requirements):
            missing = sorted(set(requirements) - set(inventories))
            raise BundleError(f"wheel set is incomplete: {missing}")
        os.chmod(temporary_path, 0o555)
        # Recheck immediately before publication.  The parent is controlled by
        # the caller; this also guarantees that an existing empty directory is
        # never silently replaced by rename() on POSIX-like filesystems.
        _path_must_not_exist(destination)
        try:
            os.rename(temporary_path, destination)
        except OSError as exc:
            raise BundleError("cannot atomically publish protected wheelhouse") from exc
        return _wheelhouse_manifest(
            inventories=inventories, lock_sha256=lock_sha256, target=target
        )
    except Exception:
        _cleanup_path_staging(temporary_path, copied_names)
        raise


def _cleanup_staging(parent_fd: int, temporary: str, filenames: Iterable[str]) -> None:
    try:
        temporary_fd = os.open(
            temporary,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError:
        return
    try:
        try:
            os.fchmod(temporary_fd, 0o700)
        except OSError:
            pass
        for filename in filenames:
            try:
                os.unlink(filename, dir_fd=temporary_fd)
            except FileNotFoundError:
                pass
    finally:
        os.close(temporary_fd)
    try:
        os.rmdir(temporary, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def stage_wheels(
    *,
    lock: str,
    source: str,
    destination: str,
    python_version: str,
    architecture: str,
    glibc: str,
    expected_owner_uid: int = 0,
) -> dict[str, object]:
    requirements, lock_sha256 = parse_lock(lock)
    target = _parse_target(python_version, architecture, glibc)
    if os.name == "nt":
        return _stage_wheels_by_path(
            requirements=requirements,
            lock_sha256=lock_sha256,
            source=source,
            destination=destination,
            target=target,
        )
    source_fd = _open_directory(source)
    destination = os.path.abspath(destination)
    parent_path, destination_name = os.path.split(destination)
    if not destination_name or os.path.normpath(destination) != destination:
        os.close(source_fd)
        raise BundleError("destination must be a canonical absolute path")
    parent_fd = _open_directory(parent_path)
    parent_stat = os.fstat(parent_fd)
    if parent_stat.st_uid != expected_owner_uid or parent_stat.st_mode & 0o022:
        os.close(source_fd)
        os.close(parent_fd)
        raise BundleError(
            "destination parent is not owned and protected by the trusted UID"
        )
    try:
        os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        os.close(source_fd)
        os.close(parent_fd)
        raise BundleError("cannot validate wheelhouse destination") from exc
    else:
        os.close(source_fd)
        os.close(parent_fd)
        raise BundleError("wheelhouse destination must not preexist")
    temporary = f".{destination_name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    copied_names: list[str] = []
    temporary_fd = -1
    try:
        try:
            os.mkdir(temporary, 0o700, dir_fd=parent_fd)
            temporary_fd = os.open(
                temporary,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise BundleError(
                "cannot create protected wheel staging directory"
            ) from exc

        try:
            names = sorted(os.listdir(source_fd))
        except OSError as exc:
            raise BundleError("cannot inventory wheel source directory") from exc
        if len(names) != len(requirements) or len(names) > MAX_PACKAGES:
            raise BundleError(
                "wheel directory must contain exactly one file per locked package"
            )

        inventories: dict[str, WheelInventory] = {}
        budget = ResourceBudget()
        for filename in names:
            parsed = parse_wheel_filename(filename)
            normalized = canonicalize_name(parsed.distribution)
            requirement = requirements.get(normalized)
            if requirement is None:
                raise BundleError(f"wheel is not present in the lock: {filename}")
            if normalized in inventories:
                raise BundleError(
                    f"multiple wheels selected for locked project: {normalized}"
                )
            source_flags = (
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            source_flags |= getattr(os, "O_BINARY", 0)
            source_flags |= getattr(os, "O_NONBLOCK", 0)
            try:
                wheel_source_fd = os.open(filename, source_flags, dir_fd=source_fd)
            except OSError as exc:
                raise BundleError(
                    f"wheel is not a safe regular file: {filename}"
                ) from exc
            try:
                source_stat = os.fstat(wheel_source_fd)
                if (
                    not stat.S_ISREG(source_stat.st_mode)
                    or source_stat.st_nlink != 1
                    or source_stat.st_size > MAX_WHEEL_BYTES
                ):
                    raise BundleError(
                        f"wheel is not a bounded single-link regular file: {filename}"
                    )
                destination_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
                destination_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(
                    os, "O_NOFOLLOW", 0
                )
                destination_flags |= getattr(os, "O_BINARY", 0)
                wheel_destination_fd = os.open(
                    filename, destination_flags, 0o600, dir_fd=temporary_fd
                )
                copied_names.append(filename)
                try:
                    archive_sha256, archive_size = _copy_and_hash(
                        wheel_source_fd, wheel_destination_fd
                    )
                    if archive_sha256 not in requirement.hashes:
                        raise BundleError(
                            f"wheel SHA-256 is not authorized by lock: {filename}"
                        )
                    if archive_size != source_stat.st_size:
                        raise BundleError(
                            f"wheel size changed while copying: {filename}"
                        )
                    os.fsync(wheel_destination_fd)
                    os.lseek(wheel_destination_fd, 0, os.SEEK_SET)
                    with os.fdopen(
                        os.dup(wheel_destination_fd), "rb", closefd=True
                    ) as handle:
                        inventory = inspect_wheel(
                            handle,
                            filename=filename,
                            archive_sha256=archive_sha256,
                            archive_size=archive_size,
                            requirement=requirement,
                            target=target,
                            budget=budget,
                        )
                    os.fchmod(wheel_destination_fd, 0o444)
                finally:
                    os.close(wheel_destination_fd)
                inventories[normalized] = inventory
            finally:
                os.close(wheel_source_fd)

        if set(inventories) != set(requirements):
            missing = sorted(set(requirements) - set(inventories))
            raise BundleError(f"wheel set is incomplete: {missing}")
        os.fsync(temporary_fd)
        os.fchmod(temporary_fd, 0o555)
        os.close(temporary_fd)
        temporary_fd = -1
        try:
            os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise BundleError("cannot validate wheelhouse destination") from exc
        else:
            raise BundleError("wheelhouse destination must not preexist")
        try:
            os.rename(
                temporary, destination_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd
            )
        except OSError as exc:
            raise BundleError("cannot atomically publish protected wheelhouse") from exc
        os.fsync(parent_fd)

        return _wheelhouse_manifest(
            inventories=inventories, lock_sha256=lock_sha256, target=target
        )
    except Exception:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        _cleanup_staging(parent_fd, temporary, copied_names)
        raise
    finally:
        os.close(source_fd)
        os.close(parent_fd)


def _claim_expected_file(
    expected: dict[str, tuple[str | None, int | None, str]],
    canonical: dict[str, str],
    *,
    path: str,
    sha256: str | None,
    size: int | None,
    owner: str,
) -> None:
    collision = path.casefold()
    if path in expected or collision in canonical:
        raise BundleError(f"wheel members collide after installation: {path}")
    canonical[collision] = path
    expected[path] = (sha256, size, owner)


def _zip_member_hash(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(COPY_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > info.file_size or total > MAX_MEMBER_BYTES:
                raise BundleError(
                    f"wheel member exceeds declared size: {info.filename}"
                )
            digest.update(chunk)
    if total != info.file_size:
        raise BundleError(f"wheel member size changed while reading: {info.filename}")
    return digest.hexdigest(), total


def _entry_point_scripts(raw: bytes, *, owner: str) -> dict[str, tuple[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError(f"entry_points.txt is not UTF-8: {owner}") from exc
    parser = configparser.RawConfigParser(
        interpolation=None,
        strict=True,
        delimiters=("=",),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
    )
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise BundleError(f"entry_points.txt is malformed: {owner}") from exc
    if parser.defaults():
        raise BundleError(f"entry_points.txt uses unsupported defaults: {owner}")
    scripts: dict[str, tuple[str, str]] = {}
    canonical: set[str] = set()
    for group in ("console_scripts", "gui_scripts"):
        if not parser.has_section(group):
            continue
        for name, value in parser.items(group, raw=True):
            if not _SAFE_SCRIPT_BASENAME.fullmatch(name):
                raise BundleError(f"unsafe generated console-script name: {name!r}")
            match = _ENTRY_POINT_VALUE.fullmatch(value)
            if match is None:
                raise BundleError(
                    f"unsupported generated console-script entry point: {name!r}"
                )
            collision = name.casefold()
            if name in scripts or collision in canonical:
                raise BundleError(f"duplicate generated console-script name: {name}")
            canonical.add(collision)
            scripts[name] = (match.group(1), match.group(2))
    if owner == "pip" and "pip" in scripts:
        if "pip3" not in scripts or scripts["pip3"] != scripts["pip"]:
            raise BundleError("pip wheel lacks its exact pip/pip3 console-script pair")
        versioned = "pip" + INSTALL_PYTHON_VERSION
        if versioned in scripts or versioned.casefold() in canonical:
            raise BundleError("pip wheel predeclares its generated versioned script")
        scripts[versioned] = scripts["pip"]
    return scripts


def _console_script_bytes(module: str, callable_name: str) -> bytes:
    return (
        f"#!{INSTALL_SCRIPT_PYTHON}\n"
        "# -*- coding: utf-8 -*-\n"
        "import re\n"
        "import sys\n"
        f"from {module} import {callable_name}\n"
        "if __name__ == '__main__':\n"
        "    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
        f"    sys.exit({callable_name}())\n"
    ).encode("utf-8")


def _assert_no_stdlib_shadow(
    expected: dict[str, tuple[str | None, int | None, str]]
) -> None:
    stdlib = getattr(sys, "stdlib_module_names", None)
    if not isinstance(stdlib, frozenset) or not stdlib:
        raise BundleError("trusted Python stdlib module inventory is unavailable")
    forbidden = {name.casefold(): name for name in stdlib}
    forbidden.update(
        {"sitecustomize": "sitecustomize", "usercustomize": "usercustomize"}
    )
    top_level: dict[str, str] = {}
    for path in expected:
        parts = PurePosixPath(path).parts
        top = parts[0]
        folded = top.casefold()
        if (
            top == "bin"
            or folded.endswith(".dist-info")
            or folded.endswith(".data")
            or folded.endswith(".libs")
        ):
            continue
        candidate = ""
        if len(parts) > 1:
            candidate = top
        elif folded.endswith(".py"):
            candidate = top[:-3]
        elif folded.endswith((".so", ".pyd", ".dll")):
            candidate = top.split(".", 1)[0]
        if not candidate:
            continue
        collision = candidate.casefold()
        if collision in forbidden:
            raise BundleError(
                f"wheel installs a top-level Python stdlib shadow: {candidate}"
            )
        prior = top_level.get(collision)
        if prior is not None and prior != candidate:
            raise BundleError(
                f"wheel set has colliding top-level import names: {prior}, {candidate}"
            )
        top_level[collision] = candidate


def _wheel_install_expectations(
    raw_wheel: bytes,
    *,
    inventory: WheelInventory,
    expected: dict[str, tuple[str | None, int | None, str]],
    canonical: dict[str, str],
) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_wheel), "r")
    except zipfile.BadZipFile as exc:  # inspect_wheel already checked this boundary.
        raise BundleError(
            f"wheel changed during install inventory: {inventory.filename}"
        ) from exc
    with archive:
        files: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            name = _safe_archive_name(info.filename)
            if info.is_dir():
                continue
            if name.split("/", 1)[0].endswith(".data"):
                raise BundleError(
                    f"wheel uses an unsupported .data installation scheme: {inventory.filename}"
                )
            files[name] = info
        dist_infos = {
            name.split("/", 1)[0]
            for name in files
            if "/" in name and name.split("/", 1)[0].endswith(".dist-info")
        }
        if len(dist_infos) != 1:
            raise BundleError(
                f"wheel must contain one installable dist-info: {inventory.filename}"
            )
        dist_info = next(iter(dist_infos))
        record_path = f"{dist_info}/RECORD"
        reserved = {
            f"{dist_info}/INSTALLER",
            f"{dist_info}/REQUESTED",
            f"{dist_info}/direct_url.json",
        }
        occupied = reserved.intersection(files)
        if occupied:
            raise BundleError(
                f"wheel predeclares pip-reserved generated files: {sorted(occupied)}"
            )

        for path, info in files.items():
            if path == record_path:
                _claim_expected_file(
                    expected,
                    canonical,
                    path=path,
                    sha256=None,
                    size=None,
                    owner=inventory.normalized_name,
                )
                continue
            digest, size = _zip_member_hash(archive, info)
            _claim_expected_file(
                expected,
                canonical,
                path=path,
                sha256=digest,
                size=size,
                owner=inventory.normalized_name,
            )

        for filename, payload in (("INSTALLER", b"pip\n"), ("REQUESTED", b"")):
            _claim_expected_file(
                expected,
                canonical,
                path=f"{dist_info}/{filename}",
                sha256=_sha256_bytes(payload),
                size=len(payload),
                owner=inventory.normalized_name,
            )

        entry_points_path = f"{dist_info}/entry_points.txt"
        scripts: dict[str, tuple[str, str]] = {}
        if entry_points_path in files:
            scripts = _entry_point_scripts(
                _bounded_member_bytes(
                    archive, files[entry_points_path], MAX_METADATA_BYTES
                ),
                owner=inventory.normalized_name,
            )
        for name, (module, callable_name) in scripts.items():
            payload = _console_script_bytes(module, callable_name)
            _claim_expected_file(
                expected,
                canonical,
                path=f"bin/{name}",
                sha256=_sha256_bytes(payload),
                size=len(payload),
                owner=inventory.normalized_name,
            )
        return dist_info


def _expected_install_from_wheelhouse(
    *,
    requirements: dict[str, LockedRequirement],
    wheelhouse: str,
) -> tuple[
    dict[str, tuple[str | None, int | None, str]],
    dict[str, str],
]:
    if not os.path.isabs(wheelhouse) or os.path.normpath(wheelhouse) != wheelhouse:
        raise BundleError("wheelhouse path must be canonical and absolute")
    metadata = os.lstat(wheelhouse)
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise BundleError("wheelhouse is not a real directory")
    if os.name != "nt" and (
        metadata.st_uid != TRUSTED_WHEELHOUSE_UID
        or metadata.st_gid != TRUSTED_WHEELHOUSE_GID
        or stat.S_IMODE(metadata.st_mode) != 0o555
    ):
        raise BundleError("wheelhouse must be root:root mode 0555")
    names = sorted(os.listdir(wheelhouse))
    if len(names) != len(requirements) or len(names) > MAX_PACKAGES:
        raise BundleError("wheelhouse must contain exactly one wheel per lock entry")

    target = _parse_target(INSTALL_PYTHON_VERSION, INSTALL_ARCHITECTURE, INSTALL_GLIBC)
    budget = ResourceBudget()
    inventories: dict[str, WheelInventory] = {}
    expected: dict[str, tuple[str | None, int | None, str]] = {}
    canonical: dict[str, str] = {}
    dist_infos: dict[str, str] = {}
    canonical_filenames: set[str] = set()
    for filename in names:
        if not _SAFE_WHEEL_FILENAME.fullmatch(filename):
            raise BundleError(f"wheelhouse contains an unsafe filename: {filename}")
        collision = filename.casefold()
        if collision in canonical_filenames:
            raise BundleError(f"wheelhouse contains colliding filenames: {filename}")
        canonical_filenames.add(collision)
        parsed = parse_wheel_filename(filename)
        normalized = canonicalize_name(parsed.distribution)
        requirement = requirements.get(normalized)
        if requirement is None or normalized in inventories:
            raise BundleError(f"wheelhouse wheel is not uniquely locked: {filename}")
        path = os.path.join(wheelhouse, filename)
        wheel_metadata = os.lstat(path)
        if (
            not stat.S_ISREG(wheel_metadata.st_mode)
            or stat.S_ISLNK(wheel_metadata.st_mode)
            or wheel_metadata.st_nlink != 1
            or wheel_metadata.st_size > MAX_WHEEL_BYTES
        ):
            raise BundleError(
                f"wheelhouse wheel is not a safe regular file: {filename}"
            )
        if os.name != "nt" and (
            wheel_metadata.st_uid != TRUSTED_WHEELHOUSE_UID
            or wheel_metadata.st_gid != TRUSTED_WHEELHOUSE_GID
            or stat.S_IMODE(wheel_metadata.st_mode) != 0o444
        ):
            raise BundleError(
                f"wheelhouse wheel must be root:root mode 0444: {filename}"
            )
        raw_wheel = _read_regular_file(path, MAX_WHEEL_BYTES)
        archive_sha256 = _sha256_bytes(raw_wheel)
        if archive_sha256 not in requirement.hashes:
            raise BundleError(f"wheelhouse wheel SHA-256 is not authorized: {filename}")
        inventory = inspect_wheel(
            io.BytesIO(raw_wheel),
            filename=filename,
            archive_sha256=archive_sha256,
            archive_size=len(raw_wheel),
            requirement=requirement,
            target=target,
            budget=budget,
        )
        dist_info = _wheel_install_expectations(
            raw_wheel,
            inventory=inventory,
            expected=expected,
            canonical=canonical,
        )
        inventories[normalized] = inventory
        dist_infos[normalized] = dist_info
    if set(inventories) != set(requirements):
        raise BundleError("wheelhouse distribution set does not exactly match lock")
    _assert_no_stdlib_shadow(expected)
    return expected, dist_infos


def _installed_record_path(root: str, value: str) -> str:
    if (
        not value
        or len(value.encode("utf-8", "strict")) > MAX_ARCHIVE_PATH_LENGTH
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or unicodedata.normalize("NFC", value) != value
    ):
        raise BundleError(f"unsafe installed RECORD path: {value!r}")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", "."} for part in path.parts):
        raise BundleError(f"unsafe installed RECORD path: {value!r}")
    if (
        len(path.parts) == 4
        and path.parts[:3] == ("..", "..", "bin")
        and _SAFE_SCRIPT_BASENAME.fullmatch(path.parts[3])
    ):
        # pip --target records generated console scripts using its exact
        # two-parent scripts-scheme path, while placing them in <target>/bin.
        # This is the only outside-root RECORD spelling accepted, and it maps
        # back into the tree that is scanned and cryptographically allowlisted.
        return f"bin/{path.parts[3]}"
    if any(part == ".." for part in path.parts):
        raise BundleError(f"unsafe installed RECORD path: {value!r}")
    if re.match(r"[A-Za-z]:", path.parts[0]):
        raise BundleError(f"unsafe installed RECORD path: {value!r}")
    candidate = os.path.abspath(os.path.join(root, *path.parts))
    root_prefix = root + os.sep
    if candidate == root or not candidate.startswith(root_prefix):
        raise BundleError(f"unsafe installed RECORD path: {value!r}")
    return os.path.relpath(candidate, root).replace(os.sep, "/")


def _scan_installed_tree(root: str) -> tuple[dict[str, tuple[str, int]], set[str]]:
    if not os.path.isabs(root) or os.path.normpath(root) != root:
        raise BundleError("site-packages path must be canonical and absolute")
    root_stat = os.lstat(root)
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise BundleError("site-packages is not a real directory")
    files: dict[str, tuple[str, int]] = {}
    directories: set[str] = set()
    canonical_nodes: dict[str, str] = {}
    node_count = 0
    total_bytes = 0
    for current, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        node_count += len(directory_names) + len(file_names)
        if node_count > MAX_INSTALLED_NODES:
            raise BundleError("installed tree node-count limit exceeded")
        for directory_name in list(directory_names):
            path = os.path.join(current, directory_name)
            metadata = os.lstat(path)
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise BundleError(
                    f"installed tree contains a non-directory node: {path}"
                )
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if (
                len(relative.encode("utf-8", "strict")) > MAX_ARCHIVE_PATH_LENGTH
                or unicodedata.normalize("NFC", relative) != relative
            ):
                raise BundleError(
                    f"installed tree contains an unsafe directory path: {relative}"
                )
            collision = relative.casefold()
            if collision in canonical_nodes:
                raise BundleError(
                    f"installed tree contains duplicate/colliding paths: {relative}"
                )
            canonical_nodes[collision] = relative
            if "/" not in relative and directory_name.casefold() in {
                "sitecustomize",
                "usercustomize",
            }:
                raise BundleError(
                    f"installed tree contains a forbidden startup/cache directory: {relative}"
                )
            directories.add(relative)
        for file_name in file_names:
            path = os.path.join(current, file_name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if (
                len(relative.encode("utf-8", "strict")) > MAX_ARCHIVE_PATH_LENGTH
                or unicodedata.normalize("NFC", relative) != relative
            ):
                raise BundleError(
                    f"installed tree contains an unsafe file path: {relative}"
                )
            collision = relative.casefold()
            if collision in canonical_nodes:
                raise BundleError(
                    f"installed tree contains duplicate/colliding paths: {relative}"
                )
            canonical_nodes[collision] = relative
            lower_name = file_name.casefold()
            if (
                lower_name.endswith(".pyc")
                or lower_name.endswith(".pth")
                or lower_name in {"sitecustomize.py", "usercustomize.py"}
                or "__pycache__"
                in {part.casefold() for part in PurePosixPath(relative).parts}
            ):
                raise BundleError(
                    f"installed tree contains a forbidden startup/cache file: {relative}"
                )
            metadata = os.lstat(path)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise BundleError(
                    f"installed tree contains a non-regular/multi-link file: {relative}"
                )
            total_bytes += metadata.st_size
            if total_bytes > MAX_TOTAL_UNCOMPRESSED:
                raise BundleError("installed tree byte-size limit exceeded")
            data = _read_regular_file(path, MAX_MEMBER_BYTES)
            files[relative] = (_sha256_bytes(data), len(data))
    return files, directories


def verify_install(
    *, lock: str, site_packages: str, wheelhouse: str
) -> dict[str, object]:
    requirements, lock_sha256 = parse_lock(lock)
    expected, expected_dist_infos = _expected_install_from_wheelhouse(
        requirements=requirements,
        wheelhouse=wheelhouse,
    )
    root = os.path.abspath(site_packages)
    files, directories = _scan_installed_tree(root)
    dist_info_dirs = sorted(
        directory
        for directory in directories
        if "/" not in directory and directory.endswith(".dist-info")
    )
    if set(dist_info_dirs) != set(expected_dist_infos.values()):
        raise BundleError(
            "installed dist-info set does not match the locked wheelhouse"
        )

    seen_projects: dict[str, tuple[str, str]] = {}
    declared_allowlist: dict[str, tuple[str | None, int | None, str]] = {}
    declared_manifest: list[dict[str, object]] = []
    for dist_info in dist_info_dirs:
        metadata_relative = f"{dist_info}/METADATA"
        record_relative = f"{dist_info}/RECORD"
        if metadata_relative not in files or record_relative not in files:
            raise BundleError(
                f"installed distribution is missing METADATA/RECORD: {dist_info}"
            )
        metadata_raw = _read_regular_file(
            os.path.join(root, *metadata_relative.split("/")), MAX_METADATA_BYTES
        )
        metadata = _metadata_headers(metadata_raw, "installed METADATA")
        name = metadata.get("Name")
        version = metadata.get("Version")
        if (
            not isinstance(name, str)
            or not _PROJECT_NAME.fullmatch(name)
            or not isinstance(version, str)
        ):
            raise BundleError(f"installed METADATA has invalid identity: {dist_info}")
        normalized = canonicalize_name(name)
        requirement = requirements.get(normalized)
        if (
            requirement is None
            or version != requirement.version
            or normalized in seen_projects
            or expected_dist_infos.get(normalized) != dist_info
        ):
            raise BundleError(
                f"installed distribution does not exactly match lock: {name}=={version}"
            )
        seen_projects[normalized] = (name, version)

        record_raw = _read_regular_file(
            os.path.join(root, *record_relative.split("/")), MAX_RECORD_BYTES
        )
        try:
            rows = list(csv.reader(io.StringIO(record_raw.decode("utf-8"), newline="")))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise BundleError(f"installed RECORD is malformed: {dist_info}") from exc
        record_entries: list[dict[str, object]] = []
        row_paths: set[str] = set()
        for row in rows:
            if len(row) != 3:
                raise BundleError(f"installed RECORD row is malformed: {dist_info}")
            inside = _installed_record_path(root, row[0])
            if inside in row_paths:
                raise BundleError(f"installed RECORD contains duplicate path: {inside}")
            row_paths.add(inside)
            hash_text, size_text = row[1], row[2]
            if inside == record_relative:
                if hash_text or size_text:
                    raise BundleError(
                        "installed RECORD must leave its own hash and size empty"
                    )
                expected_hash: str | None = None
                expected_size: int | None = None
            else:
                expected_hash = _decode_record_hash(hash_text).hex()
                if not size_text.isascii() or not size_text.isdigit():
                    raise BundleError(f"installed RECORD has invalid size: {inside}")
                expected_size = int(size_text)
            if inside in declared_allowlist:
                raise BundleError(
                    f"multiple distributions claim installed file: {inside}"
                )
            declared_allowlist[inside] = (expected_hash, expected_size, normalized)
            record_entries.append(
                {"path": inside, "sha256": expected_hash, "size": expected_size}
            )
        declared_manifest.append(
            {
                "name": name,
                "normalized_name": normalized,
                "record_entries": sorted(
                    record_entries, key=lambda value: str(value["path"])
                ),
                "version": version,
            }
        )

    if set(seen_projects) != set(requirements):
        raise BundleError("installed distribution set does not exactly match lock")
    if set(declared_allowlist) != set(expected):
        missing = sorted(set(expected) - set(declared_allowlist))[:3]
        extra = sorted(set(declared_allowlist) - set(expected))[:3]
        raise BundleError(
            "installed RECORD does not match the locked wheelhouse; "
            f"missing={missing}, extra={extra}"
        )
    for path in sorted(expected):
        if declared_allowlist[path] != expected[path]:
            raise BundleError(
                f"installed RECORD claim differs from the locked wheelhouse: {path}"
            )
    if set(files) != set(expected):
        missing = sorted(set(expected) - set(files))[:3]
        extra = sorted(set(files) - set(expected))[:3]
        raise BundleError(
            f"installed wheelhouse allowlist mismatch; missing={missing}, extra={extra}"
        )
    tree_entries: list[dict[str, object]] = []
    for path in sorted(files):
        actual_hash, actual_size = files[path]
        expected_hash, expected_size, _owner = expected[path]
        if expected_hash is not None and (
            actual_hash != expected_hash or actual_size != expected_size
        ):
            raise BundleError(
                f"installed file differs from the locked wheelhouse: {path}"
            )
        tree_entries.append({"path": path, "sha256": actual_hash, "size": actual_size})

    installed_manifest_sha256 = _sha256_bytes(
        _canonical_json(
            sorted(declared_manifest, key=lambda value: str(value["normalized_name"]))
        )
    )
    installed_tree_sha256 = _sha256_bytes(_canonical_json(tree_entries))
    result: dict[str, object] = {
        "distribution_count": len(seen_projects),
        "distributions": [
            {
                "name": seen_projects[key][0],
                "normalized_name": key,
                "version": seen_projects[key][1],
            }
            for key in sorted(seen_projects)
        ],
        "file_count": len(files),
        "installed_manifest_sha256": installed_manifest_sha256,
        "installed_tree_sha256": installed_tree_sha256,
        "kind": "installed-tree",
        "lock_sha256": lock_sha256,
        "schema": SCHEMA_VERSION,
    }
    result["inventory_sha256"] = _sha256_bytes(_canonical_json(result))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser(
        "stage", help="verify and preserve one locked wheel per package"
    )
    stage.add_argument("--lock", required=True)
    stage.add_argument("--source", required=True)
    stage.add_argument("--destination", required=True)
    stage.add_argument("--python-version", required=True)
    stage.add_argument("--architecture", required=True, choices=("x86_64", "aarch64"))
    stage.add_argument("--glibc", required=True)
    lock = subparsers.add_parser(
        "validate-lock",
        help="validate an exact, SHA-256-hashed dependency lock",
    )
    lock.add_argument("--lock", required=True)
    installed = subparsers.add_parser(
        "verify-install",
        help="inventory an installed dependency-only site-packages tree",
    )
    installed.add_argument("--lock", required=True)
    installed.add_argument("--site-packages", required=True)
    installed.add_argument("--wheelhouse", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "stage":
            result = stage_wheels(
                lock=os.path.abspath(arguments.lock),
                source=os.path.abspath(arguments.source),
                destination=os.path.abspath(arguments.destination),
                python_version=arguments.python_version,
                architecture=arguments.architecture,
                glibc=arguments.glibc,
            )
        elif arguments.command == "validate-lock":
            result = validate_lock(lock=os.path.abspath(arguments.lock))
        else:
            result = verify_install(
                lock=os.path.abspath(arguments.lock),
                site_packages=os.path.abspath(arguments.site_packages),
                wheelhouse=os.path.abspath(arguments.wheelhouse),
            )
    except BundleError as exc:
        print(f"mcp_offline_wheels: {exc}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
