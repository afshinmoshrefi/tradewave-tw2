from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "ops" / "mcp_start_guard.py"
POSIX_ROOT = os.name == "posix" and os.geteuid() == 0
pytestmark = pytest.mark.skipif(
    not POSIX_ROOT, reason="guard validates POSIX root ownership and flock"
)

FILE_PATHS = {
    "unit": "/etc/systemd/system/tradewave-mcpserver.service",
    "api_unit": "/etc/systemd/system/tradewave-apiserver.service",
    "dropin": "/etc/systemd/system/tradewave-mcpserver.service.d/20-immutable-release.conf",
    "nginx": "/etc/nginx/sites-available/tradewave-developer-portal.conf",
    "mcp_env": "/etc/tradewave/mcpserver.env",
    "api_env": "/etc/tradewave/apiserver.env",
    "secrets": "/etc/tradewave/secrets.env",
}
POINTER_PATHS = {
    "current": "/home/tradewave-mcp/current",
    "previous": "/home/tradewave-mcp/previous",
    "nginx_enabled": "/etc/nginx/sites-enabled/tradewave-developer-portal",
    "service_enabled": "/etc/systemd/system/multi-user.target.wants/tradewave-mcpserver.service",
    "api_service_enabled": "/etc/systemd/system/multi-user.target.wants/tradewave-apiserver.service",
}
VERIFIER = {
    "state_root_absent_or_exact_empty": True,
    "credential_root_absent_or_exact_empty": True,
    "transaction_artifacts_absent": True,
    "legacy_env_absent": True,
}
HMAC_SECRET = "unit-test-hmac-secret"
SERVICE_KEY = "tw_svc_" + "A" * 43
BROAD_KEY = "tw_svc_" + "B" * 43


@dataclass
class Layout:
    module: ModuleType
    active: Path
    lock: Path
    state: Path
    bundle: Path
    files: dict[str, Path]
    pointers: dict[str, Path]
    rotation: Path
    verifier_state_root: Path
    verifier_credential_root: Path
    legacy_verifier_env: Path
    manifest: dict[str, object]
    intent: dict[str, object] | None
    marker: dict[str, object]


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _mkdir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    os.chown(path, 0, 0)


def _write_root(path: Path, payload: bytes, mode: int, gid: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chown(path.parent, 0, 0)
    path.write_bytes(payload)
    path.chmod(mode)
    os.chown(path, 0, gid)


def _write_json(path: Path, value: object) -> None:
    _write_root(path, _canonical(value), 0o600)


def _symlink(target: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chown(path.parent, 0, 0)
    os.symlink(target, path)
    os.lchown(path, 0, 0)


def _run(active: Path, lock: Path) -> subprocess.CompletedProcess[str]:
    loader = (
        "import importlib.util,sys;"
        "spec=importlib.util.spec_from_file_location('guard_under_test',sys.argv[1]);"
        "guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);"
        "guard._EXPECTED_ACTIVE=sys.argv[2];guard._EXPECTED_LOCK=sys.argv[3];"
        "guard._verify_runtime_boundary=lambda:None;"
        "raise SystemExit(guard.check(sys.argv[2],sys.argv[3]))"
    )
    return subprocess.run(
        [sys.executable, "-I", "-B", "-S", "-c", loader, str(GUARD), str(active), str(lock)],
        capture_output=True,
        text=True,
        check=False,
    )


def _load_guard(
    *,
    active: Path,
    lock: Path,
    release_root: Path,
    files: dict[str, Path],
    pointers: dict[str, Path],
    rotation: Path,
    verifier_state_root: Path,
    verifier_credential_root: Path,
    legacy_verifier_env: Path,
) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"guard_{uuid.uuid4().hex}", GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._EXPECTED_ACTIVE = str(active)
    module._EXPECTED_LOCK = str(lock)
    module._RELEASE_ROOT = str(release_root)
    module._EXPECTED_FILES = {name: str(path) for name, path in files.items()}
    module._EXPECTED_POINTERS = {name: str(path) for name, path in pointers.items()}
    module._ROTATION_STATE_PATH = str(rotation)
    module._VERIFIER_STATE_ROOT = str(verifier_state_root)
    module._VERIFIER_CREDENTIAL_ROOT = str(verifier_credential_root)
    module._LEGACY_VERIFIER_ENV = str(legacy_verifier_env)
    module._BASE_INTERPRETER = os.path.realpath(sys.executable)
    module._verify_runtime_boundary = lambda: None
    module._expected_committed_metadata = lambda label: (
        0o600 if label in {"mcp_env", "api_env"} else 0o640 if label == "secrets" else 0o644,
        0,
        0,
    )
    return module


def _absent_entry(*, gateway: bool) -> dict[str, object]:
    return {
        "kind": "absent",
        "policy": "absent",
        "bundle": "",
        "sha": "",
        "cwd": "/",
        "command": "/nonexistent",
        "argv_sha256": "0" * 64,
        "active": False,
    }


def _legacy_entry(*, gateway: bool) -> dict[str, object]:
    return {
        "kind": "legacy",
        "policy": "legacy",
        "bundle": "",
        "sha": "",
        "cwd": "/home/flask",
        "command": (
            "/home/flask/venv-api/bin/python3"
            if gateway
            else "/home/flask/venv-api/bin/python"
        ),
        "argv_sha256": ("f" if gateway else "e") * 64,
        "active": True,
    }


def _sealed_entry(
    bundle: Path, sha: str, current: Path, *, gateway: bool
) -> dict[str, object]:
    return {
        "kind": "sealed",
        "policy": "fenced",
        "bundle": str(bundle),
        "sha": sha,
        "cwd": str(bundle / "src") if gateway else "/",
        "command": str(current / ("gateway-venv" if gateway else "venv") / "bin" / "python"),
        "argv_sha256": ("d" if gateway else "c") * 64,
        "active": True,
    }


def _make_bundle(module: ModuleType, release_root: Path) -> tuple[Path, str]:
    sha = "a" * 40
    bundle = release_root / f"mcp-{sha}"
    directories = [
        bundle,
        bundle / "src",
        bundle / "venv",
        bundle / "venv" / "bin",
        bundle / "gateway-venv",
        bundle / "gateway-venv" / "bin",
        bundle / "provision-venv",
        bundle / "provision-venv" / "bin",
    ]
    for directory in directories:
        _mkdir(directory, 0o755)
    _write_root(bundle / "src" / "server.py", b"SERVER = 'sealed'\n", 0o444)
    for venv in ("venv", "gateway-venv", "provision-venv"):
        _symlink(module._BASE_INTERPRETER, bundle / venv / "bin" / "python")
    for directory in reversed(directories):
        directory.chmod(0o555)
    digest = module._bundle_content_sha256(str(bundle))
    values = {name: hashlib.sha256(name.encode("ascii")).hexdigest() for name in module._SEAL_FIELDS}
    values["release_sha"] = sha
    values["bundle_content_sha256"] = digest
    seal = "".join(f"{name}={values[name]}\n" for name in sorted(values)).encode("ascii")
    _write_root(bundle / ".sealed", seal, 0o444)
    return bundle, sha


def _rotation_state(key_id: str, key_hash: str, *, status: str = "active") -> dict[str, object]:
    return {
        "version": 2,
        "status": status,
        "replacement_key_id": key_id,
        "replacement_key_hash": key_hash,
        "superseded_key_id": None,
        "superseded_key_hash": None,
        "source_key_hash": "9" * 64,
    }


def _snapshot_file(path: Path, state: Path, label: str) -> dict[str, object]:
    if not os.path.lexists(path):
        return {
            "path": str(path),
            "exists": False,
            "backup": None,
            "sha256": None,
            "mode": None,
            "uid": None,
            "gid": None,
            "parent_exists": os.path.lexists(path.parent),
        }
    payload = path.read_bytes()
    metadata = os.lstat(path)
    _write_root(state / label, payload, 0o600)
    return {
        "path": str(path),
        "exists": True,
        "backup": label,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "mode": metadata.st_mode & 0o7777,
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "parent_exists": True,
    }


def _snapshot_pointer(path: Path) -> dict[str, object]:
    if not os.path.lexists(path):
        return {"path": str(path), "exists": False, "target": None, "uid": None, "gid": None}
    metadata = os.lstat(path)
    return {
        "path": str(path),
        "exists": True,
        "target": os.readlink(path),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }


def _release_layout(tmp_path: Path, *, state_kind: str = "committed") -> Layout:
    assert state_kind in {"committed", "recovered-sealed", "recovered-legacy", "recovered-absent"}
    home = tmp_path / "home"
    release_home = home / "tradewave-mcp"
    release_root = release_home / "releases"
    for directory in (home, release_home, release_root):
        _mkdir(directory, 0o755)
    tx_root = tmp_path / "transactions"
    _mkdir(tx_root)
    active = tx_root / "active"
    lock = tmp_path / "run" / "lock" / "tradewave" / "mcp-release.lock"
    files = {
        "unit": tmp_path / "etc" / "systemd" / "system" / "tradewave-mcpserver.service",
        "api_unit": tmp_path / "etc" / "systemd" / "system" / "tradewave-apiserver.service",
        "dropin": tmp_path / "etc" / "systemd" / "system" / "mcp-dropin.conf",
        "nginx": tmp_path / "etc" / "nginx" / "available.conf",
        "mcp_env": tmp_path / "etc" / "tradewave" / "mcpserver.env",
        "api_env": tmp_path / "etc" / "tradewave" / "apiserver.env",
        "secrets": tmp_path / "etc" / "tradewave" / "secrets.env",
    }
    pointers = {
        "current": release_home / "current",
        "previous": release_home / "previous",
        "nginx_enabled": tmp_path / "etc" / "nginx" / "enabled.conf",
        "service_enabled": tmp_path / "etc" / "systemd" / "wants" / "tradewave-mcpserver.service",
        "api_service_enabled": tmp_path / "etc" / "systemd" / "wants" / "tradewave-apiserver.service",
    }
    rotation = tmp_path / "var" / "lib" / "tradewave" / "mcp-key-rotation.json"
    verifier_state_root = tmp_path / "var" / "lib" / "tradewave" / "mcp-verifier-probes"
    verifier_credential_root = tmp_path / "run" / "tradewave-mcp-verifier"
    legacy_verifier_env = tmp_path / "etc" / "tradewave" / "mcp-verifier.env"
    module = _load_guard(
        active=active,
        lock=lock,
        release_root=release_root,
        files=files,
        pointers=pointers,
        rotation=rotation,
        verifier_state_root=verifier_state_root,
        verifier_credential_root=verifier_credential_root,
        legacy_verifier_env=legacy_verifier_env,
    )
    bundle, sha = _make_bundle(module, release_root)

    key_id = str(uuid.uuid4())
    key = SERVICE_KEY if state_kind in {"committed", "recovered-sealed"} else BROAD_KEY
    key_hash = hmac.new(HMAC_SECRET.encode(), key.encode(), hashlib.sha256).hexdigest()
    payloads = {
        "unit": b"[Unit]\nDescription=MCP\n",
        "api_unit": b"[Unit]\nDescription=API gateway\n",
        "dropin": b"[Service]\nReadOnlyPaths=/home/tradewave-mcp\n",
        "nginx": b"server { listen 443 ssl; }\n",
        "mcp_env": (
            f"MCP_GATEWAY_KEY={key}\n".encode()
            if state_kind != "recovered-absent"
            else b"MCP_THREADS=8\n"
        ),
        "api_env": (
            b"POSTGRES_DSN=postgresql://gateway\n"
            b"API_KEY_HMAC_SECRET=unit-test-hmac-secret\n"
            b"TW2_APPSERVER_URL=http://127.0.0.1:5000\n"
            b"SERVICE_API_KEY=service-api-key\n"
            b"TW2_DEMO_API_KEY=tw_demo_explore\n"
            b"REDIS_HOST=127.0.0.1\n"
            b"REDIS_PORT=6379\n"
            b"API_REDIS_DB=4\n"
            b"TW2_PUBLIC_HOST=tw2-dev.trxstat.com\n"
            b"TW2_ENV=dev\n"
            b"API_CORS_ORIGINS=''\n"
            b"TW2_API_PRICING_LIVE=false\n"
        ),
        "secrets": (
            f"API_KEY_HMAC_SECRET={HMAC_SECRET}\n".encode()
            + (f"MCP_GATEWAY_KEY={BROAD_KEY}\n".encode() if state_kind == "recovered-legacy" else b"")
        ),
    }
    modes = {
        "unit": 0o644,
        "api_unit": 0o644,
        "dropin": 0o644,
        "nginx": 0o644,
        "mcp_env": 0o600,
        "api_env": 0o600,
        "secrets": 0o640,
    }
    for label, path in files.items():
        if state_kind == "recovered-absent" and label in {"unit", "api_unit"}:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chown(path.parent, 0, 0)
            continue
        _write_root(path, payloads[label], modes[label])

    if state_kind in {"committed", "recovered-sealed"}:
        _symlink(f"releases/mcp-{sha}", pointers["current"])
        _symlink(f"releases/mcp-{sha}", pointers["previous"])
    _symlink(str(files["nginx"]), pointers["nginx_enabled"])
    if state_kind != "recovered-absent":
        _symlink("../tradewave-mcpserver.service", pointers["service_enabled"])
        _symlink("../tradewave-apiserver.service", pointers["api_service_enabled"])
    if state_kind in {"committed", "recovered-sealed"}:
        rotation_value = _rotation_state(key_id, key_hash)
        _write_root(rotation, _canonical(rotation_value), 0o600)
        rotation_digest: str | None = hashlib.sha256(_canonical(rotation_value)).hexdigest()
        credential = {
            "state_kind": "active",
            "replacement_key_id": key_id,
            "replacement_key_hash": key_hash,
            "rotation_state_sha256": rotation_digest,
        }
    elif state_kind == "recovered-legacy":
        credential = {
            "state_kind": "legacy-broad",
            "replacement_key_id": None,
            "replacement_key_hash": key_hash,
            "rotation_state_sha256": None,
        }
    else:
        credential = {
            "state_kind": "source-absent",
            "replacement_key_id": None,
            "replacement_key_hash": None,
            "rotation_state_sha256": None,
        }

    txid = str(uuid.uuid4())
    state_prefix = "committed" if state_kind == "committed" else "recovered"
    state = tx_root / f"{state_prefix}-{txid}"
    _mkdir(state)
    candidate = {"bundle": str(bundle), "sha": sha}
    if state_kind == "committed":
        manifest_files = {
            label: {
                "path": str(path),
                "exists": False,
                "backup": None,
                "sha256": None,
                "mode": None,
                "uid": None,
                "gid": None,
                "parent_exists": True,
            }
            for label, path in files.items()
        }
        manifest_pointers = {
            label: {"path": str(path), "exists": False, "target": None, "uid": None, "gid": None}
            for label, path in pointers.items()
        }
        entry = _absent_entry(gateway=False)
        gateway_entry = _absent_entry(gateway=True)
    else:
        manifest_files = {
            label: _snapshot_file(path, state, label) for label, path in files.items()
        }
        manifest_pointers = {
            label: _snapshot_pointer(path) for label, path in pointers.items()
        }
        if state_kind == "recovered-sealed":
            entry = _sealed_entry(bundle, sha, pointers["current"], gateway=False)
            gateway_entry = _sealed_entry(bundle, sha, pointers["current"], gateway=True)
        elif state_kind == "recovered-legacy":
            entry = _legacy_entry(gateway=False)
            gateway_entry = _legacy_entry(gateway=True)
        else:
            entry = _absent_entry(gateway=False)
            gateway_entry = _absent_entry(gateway=True)
    manifest = {
        "version": 4,
        "txid": txid,
        "candidate": candidate,
        "entry": entry,
        "gateway_entry": gateway_entry,
        "files": manifest_files,
        "pointers": manifest_pointers,
    }
    _write_json(state / "manifest.json", manifest)

    intent: dict[str, object] | None = None
    if state_kind == "committed":
        intent = {
            "version": 4,
            "txid": txid,
            "candidate": candidate,
            "files": {
                label: {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "mode": modes[label],
                    "uid": 0,
                    "gid": 0,
                }
                for label, path in files.items()
            },
            "pointers": {
                label: {
                    "path": str(path),
                    "exists": True,
                    "target": os.readlink(path),
                    "uid": 0,
                    "gid": 0,
                }
                for label, path in pointers.items()
            },
            "credentials": {
                "replacement_key_id": key_id,
                "replacement_key_hash": key_hash,
            },
        }
        _write_json(state / "commit-intent.json", intent)
        marker_name = "finalized.json"
    else:
        marker_name = "recovery.json"
    marker = {
        "version": 4,
        "txid": txid,
        "candidate": candidate,
        "credentials": credential,
        "verifier": dict(VERIFIER),
    }
    _write_json(state / marker_name, marker)
    return Layout(
        module=module,
        active=active,
        lock=lock,
        state=state,
        bundle=bundle,
        files=files,
        pointers=pointers,
        rotation=rotation,
        verifier_state_root=verifier_state_root,
        verifier_credential_root=verifier_credential_root,
        legacy_verifier_env=legacy_verifier_env,
        manifest=manifest,
        intent=intent,
        marker=marker,
    )


def _production_active_manifest(active: Path, *, version: int = 4) -> dict[str, object]:
    txid = str(uuid.uuid4())
    manifest = {
        "version": version,
        "txid": txid,
        "candidate": {
            "bundle": "/home/tradewave-mcp/releases/mcp-" + "a" * 40,
            "sha": "a" * 40,
        },
        "entry": _absent_entry(gateway=False),
        "gateway_entry": _absent_entry(gateway=True),
        "files": {
            label: {
                "path": path,
                "exists": False,
                "backup": None,
                "sha256": None,
                "mode": None,
                "uid": None,
                "gid": None,
                "parent_exists": False,
            }
            for label, path in FILE_PATHS.items()
        },
        "pointers": {
            label: {"path": path, "exists": False, "target": None, "uid": None, "gid": None}
            for label, path in POINTER_PATHS.items()
        },
    }
    _write_json(active / "manifest.json", manifest)
    return manifest


def _refresh_intent_file(layout: Layout, label: str) -> None:
    assert layout.intent is not None
    layout.intent["files"][label]["sha256"] = hashlib.sha256(
        layout.files[label].read_bytes()
    ).hexdigest()
    _write_json(layout.state / "commit-intent.json", layout.intent)


def test_no_transaction_allows_normal_start_without_runtime_lock(tmp_path: Path) -> None:
    active = tmp_path / "transactions" / "active"
    lock = tmp_path / "run" / "lock" / "tradewave" / "mcp-release.lock"
    result = _run(active, lock)
    assert result.returncode == 0, result.stderr


def test_cli_refuses_alternate_paths(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-S", str(GUARD), str(tmp_path / "active"), str(tmp_path / "lock")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "fixed production paths" in result.stderr


def test_active_v4_transaction_refuses_start_after_reboot_without_lock(tmp_path: Path) -> None:
    tx_root = tmp_path / "transactions"
    active = tx_root / "active"
    _mkdir(tx_root)
    _mkdir(active)
    _production_active_manifest(active)
    result = _run(active, tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "active release transaction blocks" in result.stderr


def test_active_transaction_rejects_v1_to_v3_and_old_commit_marker(tmp_path: Path) -> None:
    for version in (1, 2, 3):
        tx_root = tmp_path / f"v{version}" / "transactions"
        active = tx_root / "active"
        _mkdir(tx_root)
        _mkdir(active)
        _production_active_manifest(active, version=version)
        result = _run(active, tmp_path / "missing-lock")
        assert result.returncode != 0
        assert "schema/version" in result.stderr

    tx_root = tmp_path / "old-marker" / "transactions"
    active = tx_root / "active"
    _mkdir(tx_root)
    _mkdir(active)
    _production_active_manifest(active)
    _write_root(active / "commit.json", b"{}\n", 0o600)
    result = _run(active, tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "unexpected or missing evidence" in result.stderr


@pytest.mark.parametrize(
    ("section", "label", "field"),
    [
        ("files", "api_unit", "parent_exists"),
        ("files", "unit", "exists"),
        ("pointers", "api_service_enabled", "exists"),
    ],
)
def test_manifest_boolean_fields_reject_integer_lookalikes(
    tmp_path: Path, section: str, label: str, field: str
) -> None:
    tx_root = tmp_path / "transactions"
    active = tx_root / "active"
    _mkdir(tx_root)
    _mkdir(active)
    manifest = _production_active_manifest(active)
    manifest[section][label][field] = 0
    _write_json(active / "manifest.json", manifest)
    result = _run(active, tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "invalid durable journal" in result.stderr


def test_incomplete_mixed_and_corrupt_states_are_refused(tmp_path: Path) -> None:
    incomplete_root = tmp_path / "incomplete" / "transactions"
    _mkdir(incomplete_root)
    _mkdir(incomplete_root / f".new-{uuid.uuid4()}")
    result = _run(incomplete_root / "active", tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "requires reconciliation" in result.stderr

    mixed_root = tmp_path / "mixed" / "transactions"
    _mkdir(mixed_root)
    _mkdir(mixed_root / "active")
    _production_active_manifest(mixed_root / "active")
    _mkdir(mixed_root / f"gc-{uuid.uuid4()}")
    result = _run(mixed_root / "active", tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "mixed durable journal states" in result.stderr

    corrupt_root = tmp_path / "corrupt" / "transactions"
    _mkdir(corrupt_root)
    _mkdir(corrupt_root / "active")
    _write_root(corrupt_root / "active" / "manifest.json", b"not-json", 0o600)
    result = _run(corrupt_root / "active", tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "invalid JSON" in result.stderr


def test_partial_v4_gc_allows_start_but_old_or_extra_names_refuse(tmp_path: Path) -> None:
    tx_root = tmp_path / "safe" / "transactions"
    _mkdir(tx_root)
    gc = tx_root / f"gc-{uuid.uuid4()}"
    _mkdir(gc)
    _write_root(gc / "api_unit", b"partial", 0o600)
    _write_root(gc / "finalized.json", b"partial", 0o600)
    assert _run(tx_root / "active", tmp_path / "missing-lock").returncode == 0

    bad_root = tmp_path / "bad" / "transactions"
    _mkdir(bad_root)
    bad_gc = bad_root / f"gc-{uuid.uuid4()}"
    _mkdir(bad_gc)
    _write_root(bad_gc / "commit.json", b"old", 0o600)
    result = _run(bad_root / "active", tmp_path / "missing-lock")
    assert result.returncode != 0
    assert "unexpected child" in result.stderr


@pytest.mark.parametrize(
    "state_kind", ["committed", "recovered-sealed", "recovered-legacy", "recovered-absent"]
)
def test_exact_v4_authority_states_allow_start(tmp_path: Path, state_kind: str) -> None:
    layout = _release_layout(tmp_path, state_kind=state_kind)
    assert layout.module.check(str(layout.active), str(layout.lock)) == 0


def test_absent_or_exact_empty_verifier_roots_are_equivalent(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    _mkdir(layout.verifier_state_root)
    _mkdir(layout.verifier_credential_root)
    assert layout.module.check(str(layout.active), str(layout.lock)) == 0


@pytest.mark.parametrize("label", sorted(FILE_PATHS))
def test_committed_refuses_every_live_file_tamper(tmp_path: Path, label: str) -> None:
    layout = _release_layout(tmp_path)
    with layout.files[label].open("ab") as handle:
        handle.write(b"tamper")
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("label", sorted(POINTER_PATHS))
def test_committed_refuses_every_live_pointer_tamper(tmp_path: Path, label: str) -> None:
    layout = _release_layout(tmp_path)
    layout.pointers[label].unlink()
    _symlink("releases/mcp-" + "f" * 40, layout.pointers[label])
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize(
    "mutation", ["bytes", "writable", "hardlink", "runtime_link", "gateway_link", "provision_link"]
)
def test_committed_refuses_candidate_tree_tamper(tmp_path: Path, mutation: str) -> None:
    layout = _release_layout(tmp_path)
    source = layout.bundle / "src" / "server.py"
    if mutation == "bytes":
        source.write_bytes(b"poison\n")
        source.chmod(0o444)
    elif mutation == "writable":
        source.chmod(0o644)
    elif mutation == "hardlink":
        os.link(source, layout.bundle / "src" / "hardlink.py")
    else:
        venv = mutation.removesuffix("_link") + "-venv" if mutation != "runtime_link" else "venv"
        if mutation == "gateway_link":
            venv = "gateway-venv"
        elif mutation == "provision_link":
            venv = "provision-venv"
        link = layout.bundle / venv / "bin" / "python"
        link.unlink()
        _symlink("/bin/sh", link)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("mutation", ["missing_gateway_field", "extra_field", "bad_gateway_hash"])
def test_gateway_seal_schema_is_exact(tmp_path: Path, mutation: str) -> None:
    layout = _release_layout(tmp_path)
    seal_path = layout.bundle / ".sealed"
    values = dict(line.split("=", 1) for line in seal_path.read_text(encoding="ascii").splitlines())
    if mutation == "missing_gateway_field":
        values.pop("gateway_tree_sha256")
    elif mutation == "extra_field":
        values["gateway_extra_sha256"] = "a" * 64
    else:
        values["gateway_manifest_sha256"] = "not-a-hash"
    payload = "".join(f"{name}={values[name]}\n" for name in sorted(values)).encode("ascii")
    _write_root(seal_path, payload, 0o444)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("field", ["command", "cwd", "active", "policy", "extra"])
def test_recovered_gateway_entry_identity_is_exact(tmp_path: Path, field: str) -> None:
    layout = _release_layout(tmp_path, state_kind="recovered-sealed")
    entry = layout.manifest["gateway_entry"]
    if field == "command":
        entry[field] = str(layout.pointers["current"] / "venv" / "bin" / "python")
    elif field == "cwd":
        entry[field] = "/"
    elif field == "active":
        entry[field] = False
    elif field == "policy":
        entry[field] = "sealed-unfenced"
    else:
        entry[field] = "unexpected"
    _write_json(layout.state / "manifest.json", layout.manifest)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_recovered_gateway_absence_cannot_hide_installed_enabled_api(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path, state_kind="recovered-sealed")
    layout.manifest["gateway_entry"] = _absent_entry(gateway=True)
    _write_json(layout.state / "manifest.json", layout.manifest)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("name", ["commit.json", "unexpected", "recovery.json"])
def test_committed_rejects_old_mixed_or_extra_evidence(tmp_path: Path, name: str) -> None:
    layout = _release_layout(tmp_path)
    _write_root(layout.state / name, b"{}\n", 0o600)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("missing", ["commit-intent.json", "finalized.json"])
def test_committed_requires_intent_and_finalized_markers(tmp_path: Path, missing: str) -> None:
    layout = _release_layout(tmp_path)
    (layout.state / missing).unlink()
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_manifest_and_markers_require_canonical_json(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    _write_root(
        layout.state / "manifest.json",
        json.dumps(layout.manifest, indent=2).encode("utf-8"),
        0o600,
    )
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_committed_rejects_broad_key_after_dedicated_activation(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    _write_root(
        layout.files["secrets"],
        layout.files["secrets"].read_bytes() + f"MCP_GATEWAY_KEY={BROAD_KEY}\n".encode(),
        0o640,
    )
    _refresh_intent_file(layout, "secrets")
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_committed_rejects_runtime_key_rotation_mismatch(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    other = "tw_svc_" + "Z" * 43
    _write_root(layout.files["mcp_env"], f"MCP_GATEWAY_KEY={other}\n".encode(), 0o600)
    _refresh_intent_file(layout, "mcp_env")
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_committed_rejects_pending_or_drifted_rotation_state(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    state = json.loads(layout.rotation.read_text(encoding="utf-8"))
    state["status"] = "pending"
    _write_root(layout.rotation, _canonical(state), 0o600)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_finalized_credential_binding_cannot_drift_from_intent(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path)
    layout.marker["credentials"]["replacement_key_hash"] = "0" * 64
    _write_json(layout.state / "finalized.json", layout.marker)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


@pytest.mark.parametrize("artifact", ["legacy", "state", "credential"])
def test_verifier_credentials_or_sidecars_block_start(tmp_path: Path, artifact: str) -> None:
    layout = _release_layout(tmp_path)
    txid = layout.manifest["txid"]
    if artifact == "legacy":
        _write_root(layout.legacy_verifier_env, b"MCP_GATEWAY_KEY=poison\n", 0o600)
    elif artifact == "state":
        _mkdir(layout.verifier_state_root)
        _write_root(layout.verifier_state_root / f"{txid}.json", b"{}\n", 0o600)
    else:
        credential = layout.verifier_credential_root / str(txid) / "verify-env"
        _write_root(credential, b"MCP_GATEWAY_KEY=poison\n", 0o600)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_recovered_legacy_refuses_retained_rotation_state(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path, state_kind="recovered-legacy")
    state = _rotation_state(str(uuid.uuid4()), "1" * 64)
    _write_root(layout.rotation, _canonical(state), 0o600)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0


def test_recovered_refuses_api_unit_or_enabled_pointer_tamper(tmp_path: Path) -> None:
    unit_layout = _release_layout(tmp_path / "unit", state_kind="recovered-sealed")
    with unit_layout.files["api_unit"].open("ab") as handle:
        handle.write(b"tamper")
    assert unit_layout.module.check(str(unit_layout.active), str(unit_layout.lock)) != 0

    pointer_layout = _release_layout(tmp_path / "pointer", state_kind="recovered-sealed")
    pointer_layout.pointers["api_service_enabled"].unlink()
    _symlink("../tradewave-mcpserver.service", pointer_layout.pointers["api_service_enabled"])
    assert pointer_layout.module.check(str(pointer_layout.active), str(pointer_layout.lock)) != 0


def test_recovered_gateway_bundle_must_match_current_selection(tmp_path: Path) -> None:
    layout = _release_layout(tmp_path, state_kind="recovered-sealed")
    other_sha = "b" * 40
    layout.manifest["gateway_entry"]["sha"] = other_sha
    layout.manifest["gateway_entry"]["bundle"] = str(
        layout.bundle.parent / f"mcp-{other_sha}"
    )
    layout.manifest["gateway_entry"]["cwd"] = str(
        layout.bundle.parent / f"mcp-{other_sha}" / "src"
    )
    _write_json(layout.state / "manifest.json", layout.manifest)
    assert layout.module.check(str(layout.active), str(layout.lock)) != 0
