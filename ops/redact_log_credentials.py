#!/usr/bin/env python3
"""Dry-run-first redaction of credential shapes in explicitly named log files."""

from __future__ import annotations

import argparse
import gzip
import os
import re
import stat
import tempfile
from pathlib import Path


PATTERNS = (
    (
        "query",
        re.compile(
            rb"(?i)(?P<name>(?:access_|refresh_)?token|api_?key|key)="
            rb"(?!\*{3}(?:[&\s'\"]|$))(?P<value>[^&\s'\"]+)"
        ),
        lambda match: match.group("name") + b"=***",
    ),
    (
        "legacy_login",
        re.compile(rb"(?i)(/login/api/)(?!\*{3}(?:[/?#\s'\"]|$))[^/?#\s'\"]+"),
        lambda match: match.group(1) + b"***",
    ),
    (
        "jwt",
        re.compile(rb"eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+\.?[A-Za-z0-9_=-]*"),
        lambda _match: b"eyJ***",
    ),
)


def redact_bytes(data: bytes) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    output = data
    for name, pattern, replacement in PATTERNS:
        output, counts[name] = pattern.subn(replacement, output)
    return output, counts


def _read(path: Path) -> bytes:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.read()
    return path.read_bytes()


def _write_atomic(path: Path, data: bytes) -> None:
    source_stat = path.stat()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as raw:
            if path.suffix.lower() == ".gz":
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                    zipped.write(data)
            else:
                raw.write(data)
            raw.flush()
            os.fsync(raw.fileno())
        os.chmod(temp, stat.S_IMODE(source_stat.st_mode))
        if hasattr(os, "chown"):
            try:
                os.chown(temp, source_stat.st_uid, source_stat.st_gid)
            except PermissionError:
                pass
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def process(path: Path, apply: bool) -> dict[str, int]:
    if path.is_symlink():
        raise ValueError(f"refusing symbolic link: {path}")
    if not path.is_file():
        raise ValueError(f"explicit regular-file path required: {path}")
    original = _read(path)
    redacted, counts = redact_bytes(original)
    if apply and redacted != original:
        _write_atomic(path, redacted)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="atomically replace named files; omission is a dry run",
    )
    parser.add_argument(
        "paths", nargs="+", type=Path,
        help="explicit plain or .gz log file paths (directories are refused)",
    )
    args = parser.parse_args(argv)

    seen: set[Path] = set()
    mode = "APPLY" if args.apply else "DRY-RUN"
    total = {name: 0 for name, _pattern, _replacement in PATTERNS}
    for path in args.paths:
        absolute = path.absolute()
        if absolute in seen:
            raise ValueError(f"duplicate path: {absolute}")
        seen.add(absolute)
        counts = process(absolute, args.apply)
        for name, count in counts.items():
            total[name] += count
        print(
            f"{mode} path={absolute} replacements={sum(counts.values())} "
            + " ".join(f"{name}={counts[name]}" for name in total)
        )
    print(
        f"{mode} total_replacements={sum(total.values())} "
        + " ".join(f"{name}={count}" for name, count in total.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
