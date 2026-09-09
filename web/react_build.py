"""Shared frontend selection and readiness checks for the web tier.

Keep the configured symlink unresolved between requests: nginx follows that same
pointer, independently of the backend release's working directory.
"""
from __future__ import annotations

import json
import os
from html.parser import HTMLParser
from pathlib import Path


class ReactBuildError(RuntimeError):
    """A missing, unreadable, or incomplete viewer artifact."""


def react_build_dir(repo_root: Path) -> Path:
    configured = os.environ.get("TW2_REACT_BUILD_DIR", "").strip()
    if not configured:
        return repo_root / "web-react" / "build"
    path = Path(configured)
    if not path.is_absolute():
        raise ReactBuildError("TW2_REACT_BUILD_DIR must be absolute")
    return path


class _ShellAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.has_root = False
        self.scripts = set()
        self.styles = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.has_root |= attrs.get("id") == "root"
        if tag == "script" and attrs.get("src"):
            self.scripts.add(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.styles.add(attrs.get("href", ""))


def validate_react_build(build_dir: Path) -> None:
    """Check the shell and every manifest asset, including lazy-loaded chunks.

    This is a filesystem readiness gate, not a replacement for a browser smoke
    through nginx. Resolve once per check to inspect one artifact generation.
    """
    try:
        root = build_dir.resolve(strict=True)
        parser = _ShellAssets()
        parser.feed((root / "index.html").read_text(encoding="utf-8"))
        manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
        files = manifest["files"]
        entrypoints = manifest["entrypoints"]
        if not isinstance(files, dict) or not files or not isinstance(entrypoints, list) or not entrypoints:
            raise ValueError("invalid manifest")
        urls = set(files.values())
        if not parser.has_root or not parser.scripts:
            raise ValueError("invalid React shell")
        if not (parser.scripts | parser.styles).issubset(urls):
            raise ValueError("shell and manifest disagree")
        if any(not isinstance(item, str) or "/app/" + item not in urls for item in entrypoints):
            raise ValueError("entrypoints and manifest disagree")
        for url in urls:
            if not isinstance(url, str) or not url.startswith("/app/"):
                raise ValueError("asset outside /app/")
            asset = (root / url[5:]).resolve(strict=True)
            if not asset.is_relative_to(root):
                raise ValueError("asset outside build directory")
            with asset.open("rb") as stream:
                if not stream.read(1):
                    raise ValueError("empty asset")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        raise ReactBuildError("React build is missing, unreadable, or incomplete") from exc


def main() -> int:
    try:
        validate_react_build(react_build_dir(Path(__file__).resolve().parents[1]))
    except ReactBuildError as exc:
        print(str(exc))
        return 1
    print("React shell and manifest assets ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
