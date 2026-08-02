#!/usr/bin/env python3
"""Publish the static 100-Year Pattern evidence page and download assets.

The page is intentionally framework-free. This generator performs only
environment-aware metadata substitution and atomic file copies; it does not
call the appserver, Stripe, or any market-data service.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


SITE_DIR = Path(__file__).resolve().parent
SOURCE_HTML = SITE_DIR / "100-year-pattern" / "100-year-pattern.html"
SOURCE_ASSETS = SITE_DIR / "static" / "100-year-pattern"
OUTPUT_FILENAME = "100-year-pattern.html"


def _runtime_config():
    repository_root = str(SITE_DIR.parent)
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    import config  # pylint: disable=import-outside-toplevel

    return config


def _default_output_root() -> Path:
    return Path(_runtime_config().web_root_dir)


def _public_root() -> str:
    return str(_runtime_config().tw2_public_url).strip().rstrip("/")


def _write_atomic(path: Path, content: str) -> None:
    temp = path.with_name(".%s.tmp" % path.name)
    temp.write_text(content, encoding="utf-8")
    temp.chmod(0o644)
    os.replace(temp, path)


def _copy_atomic(source: Path, destination: Path) -> None:
    temp = destination.with_name(".%s.tmp" % destination.name)
    shutil.copy2(source, temp)
    os.replace(temp, destination)


def publish(output_root: Path) -> tuple[Path, list[Path]]:
    if not SOURCE_HTML.is_file():
        raise FileNotFoundError("Missing page source: %s" % SOURCE_HTML)
    if not SOURCE_ASSETS.is_dir():
        raise FileNotFoundError("Missing page assets: %s" % SOURCE_ASSETS)

    public_root = _public_root()
    canonical_url = "%s/%s" % (public_root, OUTPUT_FILENAME)
    is_production = os.environ.get("TW2_ENV", "").strip().lower() == "prod"
    robots = "index,follow" if is_production else "noindex,nofollow"
    favicon = str(_runtime_config().tw_favicon).strip()

    html = SOURCE_HTML.read_text(encoding="utf-8")
    replacements = {
        "__ROBOTS__": robots,
        "__CANONICAL_URL__": canonical_url,
        "__FAVICON_URL__": favicon,
        "__OG_IMAGE_URL__": (
            "%s/_static/100-year-pattern/100-year-pattern-book.webp"
            % public_root
        ),
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    unresolved = [token for token in replacements if token in html]
    if unresolved:
        raise RuntimeError("Unresolved page metadata tokens: %s" % unresolved)

    output_root.mkdir(parents=True, exist_ok=True)
    output_html = output_root / OUTPUT_FILENAME
    _write_atomic(output_html, html)

    output_assets = output_root / "_static" / "100-year-pattern"
    output_assets.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in sorted(SOURCE_ASSETS.iterdir()):
        if not source.is_file():
            continue
        destination = output_assets / source.name
        _copy_atomic(source, destination)
        copied.append(destination)

    return output_html, copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        help="Override the generated site root (used by local validation).",
    )
    args = parser.parse_args()
    output_root = Path(args.output_dir).resolve() if args.output_dir else _default_output_root()
    output_html, copied = publish(output_root)
    print("Generated: %s" % output_html)
    for path in copied:
        print("Copied: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
