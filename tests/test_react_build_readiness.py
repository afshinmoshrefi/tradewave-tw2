"""Regression coverage for backend activation followed by a cold web restart."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from react_build import ReactBuildError, react_build_dir, validate_react_build


def make_build(root, name="main.test.js"):
    root.mkdir(parents=True)
    (root / "static/js").mkdir(parents=True)
    (root / "static/js" / name).write_text("/* tested build */")
    (root / "static/js/lazy.chunk.js").write_text("/* lazy */")
    (root / "index.html").write_text(
        f'<div id="root"></div><script src="/app/static/js/{name}"></script>'
    )
    (root / "asset-manifest.json").write_text(json.dumps({
        "files": {"main.js": f"/app/static/js/{name}", "lazy.js": "/app/static/js/lazy.chunk.js",
                  "index.html": "/app/index.html"},
        "entrypoints": [f"static/js/{name}"],
    }))
    return root


def test_backend_checkout_without_build_uses_stable_frontend(tmp_path, monkeypatch):
    build = make_build(tmp_path / "artifact")
    pointer = tmp_path / "build"
    pointer.symlink_to(build, target_is_directory=True)
    monkeypatch.setenv("TW2_REACT_BUILD_DIR", str(pointer))
    for checkout in (tmp_path / "old-backend", tmp_path / "new-backend"):
        assert not (checkout / "web-react/build/index.html").exists()
        selected = react_build_dir(checkout)
        assert selected == pointer
        validate_react_build(selected)


def test_running_process_follows_frontend_swap(tmp_path, monkeypatch):
    old = make_build(tmp_path / "old")
    new = make_build(tmp_path / "new", "main.new.js")
    pointer = tmp_path / "build"
    pointer.symlink_to(old, target_is_directory=True)
    monkeypatch.setenv("TW2_REACT_BUILD_DIR", str(pointer))
    selected = react_build_dir(tmp_path)
    next_pointer = tmp_path / "build.next"
    next_pointer.symlink_to(new, target_is_directory=True)
    next_pointer.replace(pointer)
    assert "main.new.js" in (selected / "index.html").read_text()
    validate_react_build(selected)


def test_unconfigured_checkout_retains_local_build(tmp_path, monkeypatch):
    monkeypatch.delenv("TW2_REACT_BUILD_DIR", raising=False)
    assert react_build_dir(tmp_path) == tmp_path / "web-react/build"


def test_relative_configuration_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("TW2_REACT_BUILD_DIR", "web-react/build")
    with pytest.raises(ReactBuildError):
        react_build_dir(tmp_path)


@pytest.mark.parametrize("missing", ["index.html", "asset-manifest.json", "static/js/main.test.js", "static/js/lazy.chunk.js"])
def test_missing_artifact_fails_readiness(tmp_path, missing):
    build = make_build(tmp_path / "build")
    (build / missing).unlink()
    with pytest.raises(ReactBuildError):
        validate_react_build(build)


def test_unreadable_bundle_fails_readiness(tmp_path, monkeypatch):
    build = make_build(tmp_path / "build")
    original = Path.open
    def denied(path, *args, **kwargs):
        if path.name == "main.test.js":
            raise PermissionError("denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(ReactBuildError):
        validate_react_build(build)


@pytest.mark.parametrize("damage", ["empty", "manifest", "shell", "wrong_bundle", "outside"])
def test_incomplete_or_mismatched_artifact_fails(tmp_path, damage):
    build = make_build(tmp_path / "build")
    if damage == "empty":
        (build / "static/js/main.test.js").write_text("")
    elif damage == "manifest":
        (build / "asset-manifest.json").write_text("{}")
    elif damage == "shell":
        (build / "index.html").write_text("<html>not a React application</html>")
    elif damage == "wrong_bundle":
        (build / "index.html").write_text('<div id="root"></div><script src="/app/static/js/stale.js"></script>')
    else:
        outside = tmp_path / "outside.js"
        outside.write_text("/* outside */")
        (build / "static/js/main.test.js").unlink()
        (build / "static/js/main.test.js").symlink_to(outside)
    with pytest.raises(ReactBuildError):
        validate_react_build(build)


def test_startup_command_refuses_missing_build(tmp_path):
    build = make_build(tmp_path / "build")
    env = dict(os.environ, TW2_REACT_BUILD_DIR=str(build))
    command = [sys.executable, "-m", "web.react_build"]
    good = subprocess.run(command, env=env, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    (build / "index.html").unlink()
    bad = subprocess.run(command, env=env, capture_output=True, text=True)
    assert bad.returncode == 1


def test_health_checks_frontend_even_when_database_is_healthy(tmp_path, monkeypatch):
    mod = importlib.import_module("app")
    build = make_build(tmp_path / "build")
    monkeypatch.setattr(mod, "REACT_BUILD_INDEX", build / "index.html")
    monkeypatch.setattr(mod, "DBSession", MagicMock())
    client = mod.app.test_client()
    good = client.get("/healthz")
    assert good.status_code == 200
    assert good.json["frontend"] == "ok"
    (build / "static/js/lazy.chunk.js").unlink()
    bad = client.get("/healthz")
    assert bad.status_code == 503
    assert bad.json == {"ok": False, "db": "ok", "frontend": "unavailable", "error": "healthcheck_failed"}
    assert str(tmp_path) not in bad.get_data(as_text=True)


def test_unavailable_shell_does_not_expose_server_path(tmp_path, monkeypatch):
    mod = importlib.import_module("app")
    monkeypatch.setattr(mod, "REACT_BUILD_INDEX", tmp_path / "absent/index.html")
    with mod.app.test_request_context("/app/"):
        response, status = mod._render_app_shell(None)
    assert status == 503
    assert response.json == {"error": "Wave Viewer is temporarily unavailable"}
