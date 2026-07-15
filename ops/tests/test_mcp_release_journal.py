"""Executable root/POSIX tests for the durable MCP release journal."""

from __future__ import annotations

import json
import grp
import hashlib
import hmac
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "ops" / "deploy_mcp_release.sh"
POSIX_ROOT = os.name == "posix" and os.geteuid() == 0
pytestmark = pytest.mark.skipif(not POSIX_ROOT, reason="journal evidence requires POSIX root metadata")
HMAC_SECRET = "journal-test-hmac-secret"
LEGACY_KEY = "tw_svc_" + "A" * 43
CANDIDATE_KEY = "tw_svc_" + "B" * 43


def _key_hash(raw_key: str) -> str:
    return hmac.new(
        HMAC_SECRET.encode(), raw_key.encode(), hashlib.sha256
    ).hexdigest()


def _journal_source() -> str:
    deploy = DEPLOY.read_text(encoding="utf-8")
    tail = deploy[deploy.index("journal_action()") :]
    match = re.search(r"<<'PY'\n(.*?)\nPY\n}", tail, re.DOTALL)
    assert match is not None
    return match.group(1)


def _mkdir(path: Path, mode: int = 0o755) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    os.chown(path, 0, 0)


def _write(path: Path, payload: bytes, mode: int, gid: int = 0) -> None:
    if not path.parent.exists():
        _mkdir(path.parent)
    path.write_bytes(payload)
    path.chmod(mode)
    os.chown(path, 0, gid)


class Layout:
    def __init__(
        self, root: Path, *, dropin_exists: bool = False, mcp_env_exists: bool = True,
        api_env_exists: bool = True,
    ) -> None:
        self.root = root
        self.sha = "a" * 40
        self.entry_sha = "b" * 40
        self.previous_sha = "c" * 40
        self.mcp_home = root / "home" / "tradewave-mcp"
        self.release_root = self.mcp_home / "releases"
        self.candidate = self.release_root / f"mcp-{self.sha}"
        self.entry = self.release_root / f"mcp-{self.entry_sha}"
        self.current = self.mcp_home / "current"
        self.previous = self.mcp_home / "previous"
        self.unit = root / "etc" / "systemd" / "system" / "tradewave-mcpserver.service"
        self.api_unit = root / "etc" / "systemd" / "system" / "tradewave-apiserver.service"
        self.dropin = root / "etc" / "systemd" / "system" / "tradewave-mcpserver.service.d" / "20-immutable-release.conf"
        self.service_enabled = root / "etc" / "systemd" / "system" / "multi-user.target.wants" / "tradewave-mcpserver.service"
        self.api_service_enabled = root / "etc" / "systemd" / "system" / "multi-user.target.wants" / "tradewave-apiserver.service"
        self.nginx = root / "etc" / "nginx" / "sites-available" / "tradewave.conf"
        self.nginx_enabled = root / "etc" / "nginx" / "sites-enabled" / "tradewave.conf"
        self.mcp_env = root / "etc" / "tradewave" / "mcpserver.env"
        self.api_env = root / "etc" / "tradewave" / "apiserver.env"
        self.secrets = root / "etc" / "tradewave" / "secrets.env"
        self.flask_gid = grp.getgrnam("flask").gr_gid
        self.tx_parent = root / "var" / "lib" / "tradewave"
        self.tx_root = self.tx_parent / "transactions"
        self.rotation_state = self.tx_parent / "mcp-service-key-rotation.json"
        self.verifier_state_root = self.tx_parent / "mcp-verifier-probes"
        self.verifier_credential_root = root / "run" / "tradewave-mcp-verifier"
        self.legacy_verifier_env = root / "etc" / "tradewave" / "mcp-verifier.env"

        for directory in (
            self.mcp_home,
            self.release_root,
            self.candidate,
            self.entry,
            self.entry / "src",
            self.nginx_enabled.parent,
            self.service_enabled.parent,
            self.tx_parent,
        ):
            _mkdir(directory, 0o700 if directory == self.tx_parent else 0o755)
        _write(self.unit, b"old-unit\n", 0o644)
        _write(self.api_unit, b"old-api-unit\n", 0o644)
        _write(self.nginx, b"old-nginx\n", 0o644)
        if mcp_env_exists:
            _write(self.mcp_env, b"TW2_MCP_PORT=9090\n", 0o600)
        if api_env_exists:
            _write(self.api_env, b"TW2_ENV=dev\n", 0o600)
        _write(
            self.secrets,
            (
                "POSTGRES_DSN=postgresql://old\n"
                f"API_KEY_HMAC_SECRET={HMAC_SECRET}\n"
                f"MCP_GATEWAY_KEY={LEGACY_KEY}\n"
            ).encode(),
            0o640,
            self.flask_gid,
        )
        if dropin_exists:
            _write(self.dropin, b"old-dropin\n", 0o644)
        self.nginx_enabled.symlink_to(self.nginx)
        self.service_enabled.symlink_to("../tradewave-mcpserver.service")
        self.api_service_enabled.symlink_to("../tradewave-apiserver.service")

    @property
    def argv_prefix(self) -> list[str]:
        return [
            str(self.tx_root),
            str(self.current),
            str(self.previous),
            str(self.nginx_enabled),
            str(self.service_enabled),
            str(self.api_service_enabled),
            str(self.unit),
            str(self.api_unit),
            str(self.dropin),
            str(self.nginx),
            str(self.mcp_env),
            str(self.api_env),
            str(self.secrets),
            str(self.release_root),
            str(self.rotation_state),
            str(self.verifier_state_root),
            str(self.verifier_credential_root),
            str(self.legacy_verifier_env),
        ]

    def run(self, operation: str, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        clean_env = os.environ.copy()
        clean_env.pop("TW_MCP_TEST_FAIL_JOURNAL_FSYNC_AT", None)
        clean_env.pop("TW_MCP_TEST_FAIL_JOURNAL_WRITE_AT", None)
        if env:
            clean_env.update(env)
        return subprocess.run(
            [sys.executable, "-", operation, *self.argv_prefix, *extra],
            input=_journal_source(),
            capture_output=True,
            text=True,
            check=False,
            env=clean_env,
        )

    def prepare_legacy(self, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run(
            "prepare",
            str(uuid.uuid4()),
            str(self.candidate),
            self.sha,
            "legacy",
            "legacy",
            "",
            "",
            "/home/flask",
            "/home/flask/venv-api/bin/python",
            "1" * 64,
            "legacy",
            "legacy",
            "",
            "",
            "/home/flask",
            "/home/flask/venv-api/bin/python3",
            "2" * 64,
            env=env,
        )

    def prepare_sealed(self) -> subprocess.CompletedProcess[str]:
        self.current.symlink_to(f"releases/mcp-{self.entry_sha}")
        self.previous.symlink_to(f"releases/mcp-{self.previous_sha}")
        return self.run(
            "prepare",
            str(uuid.uuid4()),
            str(self.candidate),
            self.sha,
            "sealed",
            "fenced",
            str(self.entry),
            self.entry_sha,
            "/",
            str(self.mcp_home / "current" / "venv" / "bin" / "python"),
            "3" * 64,
            "sealed",
            "fenced",
            str(self.entry),
            self.entry_sha,
            str(self.entry / "src"),
            str(self.mcp_home / "current" / "gateway-venv" / "bin" / "python"),
            "4" * 64,
        )

    def publish_candidate_state(self) -> None:
        for pointer in (
            self.current,
            self.previous,
            self.nginx_enabled,
            self.service_enabled,
            self.api_service_enabled,
        ):
            pointer.unlink(missing_ok=True)
        self.current.symlink_to(f"releases/mcp-{self.sha}")
        self.previous.symlink_to(f"releases/mcp-{self.entry_sha}")
        self.nginx_enabled.symlink_to(self.nginx)
        self.service_enabled.symlink_to("../tradewave-mcpserver.service")
        self.api_service_enabled.symlink_to("../tradewave-apiserver.service")
        _write(self.unit, b"candidate-unit\n", 0o644)
        _write(self.api_unit, b"candidate-api-unit\n", 0o644)
        _write(self.dropin, b"candidate-dropin\n", 0o644)
        _write(self.nginx, b"candidate-nginx\n", 0o644)
        _write(
            self.mcp_env,
            f"TW2_MCP_PORT=9091\nMCP_GATEWAY_KEY={CANDIDATE_KEY}\n".encode(),
            0o600,
        )
        _write(self.api_env, b"TW2_ENV=staging\n", 0o600)
        _write(
            self.secrets,
            (
                "POSTGRES_DSN=postgresql://candidate\n"
                f"API_KEY_HMAC_SECRET={HMAC_SECRET}\n"
            ).encode(),
            0o640,
            self.flask_gid,
        )

    def publish_active_rotation(self, raw_key: str = CANDIDATE_KEY) -> None:
        state = {
            "version": 2,
            "status": "active",
            "replacement_key_id": str(uuid.uuid4()),
            "replacement_key_hash": _key_hash(raw_key),
            "superseded_key_id": None,
            "superseded_key_hash": None,
            "source_key_hash": _key_hash(LEGACY_KEY),
        }
        _write(
            self.rotation_state,
            (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            0o600,
        )

    def publish_pending_rotation(self) -> None:
        state = {
            "version": 2,
            "status": "pending",
            "replacement_key_id": str(uuid.uuid4()),
            "replacement_key_hash": _key_hash(CANDIDATE_KEY),
            "superseded_key_id": str(uuid.uuid4()),
            "superseded_key_hash": _key_hash(LEGACY_KEY),
            "source_key_hash": _key_hash(LEGACY_KEY),
        }
        _write(
            self.rotation_state,
            (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            0o600,
        )

    def finish_committed(self) -> subprocess.CompletedProcess[str]:
        self.publish_active_rotation()
        intent = self.run("prepare-commit", str(self.candidate), self.sha)
        if intent.returncode != 0:
            return intent
        finalized = self.run("mark-finalized")
        if finalized.returncode != 0:
            return finalized
        return self.run("commit", str(self.candidate), self.sha)

    def finish_recovered(self) -> subprocess.CompletedProcess[str]:
        marked = self.run("mark-recovered")
        if marked.returncode != 0:
            return marked
        return self.run("cleanup-recovered", marked.stdout.strip())


def test_first_migration_restore_removes_new_dropin_parent(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    prepared = layout.prepare_legacy()
    assert prepared.returncode == 0, prepared.stderr
    assert not layout.dropin.parent.exists()

    layout.publish_candidate_state()
    inspected = layout.run("inspect")
    assert inspected.returncode == 0, inspected.stderr
    assert inspected.stdout.splitlines()[0] == "active"
    restored = layout.run("restore")
    assert restored.returncode == 0, restored.stderr

    assert not layout.current.exists() and not layout.current.is_symlink()
    assert not layout.previous.exists() and not layout.previous.is_symlink()
    assert not layout.dropin.parent.exists()
    assert layout.unit.read_bytes() == b"old-unit\n"
    assert layout.api_unit.read_bytes() == b"old-api-unit\n"
    assert layout.nginx.read_bytes() == b"old-nginx\n"
    assert layout.mcp_env.read_bytes() == b"TW2_MCP_PORT=9090\n"
    assert layout.api_env.read_bytes() == b"TW2_ENV=dev\n"
    assert f"MCP_GATEWAY_KEY={LEGACY_KEY}".encode() in layout.secrets.read_bytes()
    closed = layout.finish_recovered()
    assert closed.returncode == 0, closed.stderr
    assert list(layout.tx_root.iterdir()) == []


def test_restore_removes_dedicated_environment_that_was_initially_absent(tmp_path: Path) -> None:
    layout = Layout(tmp_path, mcp_env_exists=False)
    prepared = layout.prepare_legacy()
    assert prepared.returncode == 0, prepared.stderr
    layout.publish_candidate_state()
    assert layout.mcp_env.exists()
    restored = layout.run("restore")
    assert restored.returncode == 0, restored.stderr
    assert not layout.mcp_env.exists()
    assert f"MCP_GATEWAY_KEY={LEGACY_KEY}".encode() in layout.secrets.read_bytes()


def test_restore_removes_api_environment_that_was_initially_absent(tmp_path: Path) -> None:
    layout = Layout(tmp_path, api_env_exists=False)
    prepared = layout.prepare_legacy()
    assert prepared.returncode == 0, prepared.stderr
    layout.publish_candidate_state()
    assert layout.api_env.exists()
    restored = layout.run("restore")
    assert restored.returncode == 0, restored.stderr
    assert not layout.api_env.exists()
    assert layout.api_unit.read_bytes() == b"old-api-unit\n"


def test_legacy_recovery_binds_the_restored_keyed_hmac(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    assert layout.prepare_legacy().returncode == 0
    layout.publish_candidate_state()
    layout.publish_pending_rotation()
    assert layout.run("restore").returncode == 0
    # This is the provisioner's durable result after it verifies restored K0,
    # revokes K1, and discards pending rotation state.
    layout.rotation_state.unlink()
    marked = layout.run("mark-recovered")
    assert marked.returncode == 0, marked.stderr
    marker = json.loads((Path(marked.stdout.strip()) / "recovery.json").read_text())
    assert marker["credentials"] == {
        "state_kind": "legacy-broad",
        "replacement_key_id": None,
        "replacement_key_hash": _key_hash(LEGACY_KEY),
        "rotation_state_sha256": None,
    }
    assert layout.run("cleanup-recovered", marked.stdout.strip()).returncode == 0


def test_active_evidence_rejects_plain_sha_instead_of_gateway_hmac(tmp_path: Path) -> None:
    layout = Layout(tmp_path, dropin_exists=True)
    assert layout.prepare_sealed().returncode == 0
    layout.publish_candidate_state()
    layout.publish_active_rotation()
    state = json.loads(layout.rotation_state.read_text())
    state["replacement_key_hash"] = hashlib.sha256(CANDIDATE_KEY.encode()).hexdigest()
    _write(
        layout.rotation_state,
        (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        0o600,
    )
    assert layout.run("prepare-commit", str(layout.candidate), layout.sha).returncode == 0
    rejected = layout.run("mark-finalized")
    assert rejected.returncode != 0
    assert "does not match active rotation state" in rejected.stderr


def test_recovery_key_hash_uses_supported_jwt_fallback(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    _write(
        layout.secrets,
        (
            "POSTGRES_DSN=postgresql://old\n"
            f"APPSERVER_JWT_SECRET={HMAC_SECRET}\n"
            f"MCP_GATEWAY_KEY={LEGACY_KEY}\n"
        ).encode(),
        0o640,
        layout.flask_gid,
    )
    assert layout.prepare_legacy().returncode == 0
    marked = layout.run("mark-recovered")
    assert marked.returncode == 0, marked.stderr
    marker = json.loads((Path(marked.stdout.strip()) / "recovery.json").read_text())
    assert marker["credentials"]["replacement_key_hash"] == _key_hash(LEGACY_KEY)


@pytest.mark.parametrize("kind", ["write", "fsync", "rename"])
def test_first_migration_recovery_marker_survives_crash_and_run_reboot(
    tmp_path: Path, kind: str
) -> None:
    killed = 0
    for index in range(1, 25):
        layout = Layout(tmp_path / f"{kind}-{index}")
        assert layout.prepare_legacy().returncode == 0
        layout.publish_candidate_state()
        layout.publish_pending_rotation()
        assert layout.run("restore").returncode == 0
        layout.rotation_state.unlink()  # successful idempotent provisioner abort
        _mkdir(layout.verifier_state_root, 0o700)
        _mkdir(layout.verifier_credential_root, 0o700)
        marked = layout.run(
            "mark-recovered",
            env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"},
        )
        if marked.returncode == 0:
            recovered_path = marked.stdout.strip()
        else:
            assert marked.returncode == -9
            killed += 1
            assert layout.run("reconcile").returncode == 0
            inspected = layout.run("inspect")
            assert inspected.returncode == 0, inspected.stderr
            fields = inspected.stdout.splitlines()
            if fields[0] in {"active", "recovering"}:
                retried = layout.run("mark-recovered")
                assert retried.returncode == 0, retried.stderr
                recovered_path = retried.stdout.strip()
            else:
                assert fields[0] == "recovered"
                recovered_path = fields[1]
        # /run is volatile. Evidence deliberately binds the semantic invariant,
        # so exact empty roots at finalization may disappear across reboot.
        layout.verifier_state_root.rmdir()
        layout.verifier_credential_root.rmdir()
        inspected = layout.run("inspect")
        assert inspected.returncode == 0, inspected.stderr
        assert inspected.stdout.splitlines()[:2] == ["recovered", recovered_path]
        assert layout.run("cleanup-recovered", recovered_path).returncode == 0
        if marked.returncode == 0:
            break
    else:
        pytest.fail(f"never exhausted recovery-marker {kind} events")
    assert killed >= 1


def test_committed_evidence_binds_every_live_file_and_pointer(tmp_path: Path) -> None:
    layout = Layout(tmp_path, dropin_exists=True)
    prepared = layout.prepare_sealed()
    assert prepared.returncode == 0, prepared.stderr
    layout.publish_candidate_state()
    committed = layout.finish_committed()
    assert committed.returncode == 0, committed.stderr
    committed_path = committed.stdout.strip()

    inspected = layout.run("inspect")
    assert inspected.returncode == 0, inspected.stderr
    assert inspected.stdout.splitlines()[0] == "committed"
    verified = layout.run("verify-committed-live", committed_path)
    assert verified.returncode == 0, verified.stderr

    layout.nginx.write_bytes(b"tampered\n")
    rejected = layout.run("verify-committed-live", committed_path)
    assert rejected.returncode != 0
    assert "live file changed: nginx" in rejected.stderr
    layout.nginx.write_bytes(b"candidate-nginx\n")
    cleaned = layout.run("cleanup", committed_path)
    assert cleaned.returncode == 0, cleaned.stderr
    assert list(layout.tx_root.iterdir()) == []


@pytest.mark.parametrize("state", [".new", "gc"])
@pytest.mark.parametrize("removed", range(8))
def test_partial_discard_is_resumable_after_each_unlink(tmp_path: Path, state: str, removed: int) -> None:
    layout = Layout(tmp_path)
    _mkdir(layout.tx_root, 0o700)
    txid = str(uuid.uuid4())
    directory = layout.tx_root / f"{state}-{txid}"
    _mkdir(directory, 0o700)
    evidence = sorted(
        ("manifest.json", "unit", "api_unit", "dropin", "nginx", "mcp_env", "api_env", "secrets")
    )
    for name in evidence[removed:]:
        _write(directory / name, b"partial", 0o600)
    result = layout.run("reconcile")
    assert result.returncode == 0, result.stderr
    assert list(layout.tx_root.iterdir()) == []


@pytest.mark.parametrize(
    "seam",
    ["TW_MCP_TEST_FAIL_JOURNAL_FSYNC_AT", "TW_MCP_TEST_FAIL_JOURNAL_WRITE_AT"],
)
def test_prepare_io_failure_is_fail_closed_and_reconcilable(tmp_path: Path, seam: str) -> None:
    layout = Layout(tmp_path)
    failed = layout.prepare_legacy(env={seam: "1"})
    assert failed.returncode != 0
    reconciled = layout.run("reconcile")
    assert reconciled.returncode == 0, reconciled.stderr
    retried = layout.prepare_legacy()
    assert retried.returncode == 0, retried.stderr


def test_mixed_durable_states_fail_closed(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    assert layout.prepare_legacy().returncode == 0
    extra = layout.tx_root / f"gc-{uuid.uuid4()}"
    _mkdir(extra, 0o700)
    for operation in ("inspect", "reconcile"):
        result = layout.run(operation)
        assert result.returncode != 0
        assert "multiple/coexisting" in result.stderr


def test_boolean_metadata_and_wrong_owner_are_rejected(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    assert layout.prepare_legacy().returncode == 0
    manifest_path = layout.tx_root / "active" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["unit"]["uid"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)
    rejected_bool = layout.run("inspect")
    assert rejected_bool.returncode != 0
    assert "backup uid" in rejected_bool.stderr

    os.chown(manifest_path, 1, 1)
    rejected_owner = layout.run("inspect")
    assert rejected_owner.returncode != 0
    assert "not root:root mode 0600" in rejected_owner.stderr


def test_journal_root_symlink_is_rejected(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    target = tmp_path / "attacker-journal"
    _mkdir(target, 0o700)
    layout.tx_root.symlink_to(target, target_is_directory=True)
    result = layout.run("inspect")
    assert result.returncode != 0
    assert "not a real directory" in result.stderr


def _assert_legacy_entry(layout: Layout) -> None:
    assert not layout.current.exists() and not layout.current.is_symlink()
    assert not layout.previous.exists() and not layout.previous.is_symlink()
    assert not layout.dropin.parent.exists()
    assert layout.unit.read_bytes() == b"old-unit\n"
    assert layout.nginx.read_bytes() == b"old-nginx\n"
    assert layout.mcp_env.read_bytes() == b"TW2_MCP_PORT=9090\n"
    assert layout.api_env.read_bytes() == b"TW2_ENV=dev\n"
    assert (layout.unit.stat().st_uid, layout.unit.stat().st_gid, layout.unit.stat().st_mode & 0o777) == (0, 0, 0o644)
    assert (layout.api_unit.stat().st_uid, layout.api_unit.stat().st_gid, layout.api_unit.stat().st_mode & 0o777) == (0, 0, 0o644)
    assert (layout.mcp_env.stat().st_uid, layout.mcp_env.stat().st_gid, layout.mcp_env.stat().st_mode & 0o777) == (0, 0, 0o600)
    assert (layout.api_env.stat().st_uid, layout.api_env.stat().st_gid, layout.api_env.stat().st_mode & 0o777) == (0, 0, 0o600)
    assert f"MCP_GATEWAY_KEY={LEGACY_KEY}".encode() in layout.secrets.read_bytes()
    assert (layout.secrets.stat().st_uid, layout.secrets.stat().st_gid, layout.secrets.stat().st_mode & 0o777) == (0, layout.flask_gid, 0o640)


def _settle_active(layout: Layout) -> None:
    reconciled = layout.run("reconcile")
    assert reconciled.returncode == 0, reconciled.stderr
    inspected = layout.run("inspect")
    assert inspected.returncode == 0, inspected.stderr
    mode = inspected.stdout.splitlines()[0]
    if mode == "active":
        restored = layout.run("restore")
        assert restored.returncode == 0, restored.stderr
        _assert_legacy_entry(layout)
        closed = layout.finish_recovered()
        assert closed.returncode == 0, closed.stderr
    else:
        assert mode == "none"


@pytest.mark.parametrize("kind", ["write", "fsync", "rename"])
def test_sigkill_at_each_prepare_durable_event_is_recoverable(tmp_path: Path, kind: str) -> None:
    killed = 0
    for index in range(1, 40):
        layout = Layout(tmp_path / f"{kind}-{index}")
        result = layout.prepare_legacy(env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"})
        if result.returncode == 0:
            _settle_active(layout)
            break
        assert result.returncode == -9
        killed += 1
        _settle_active(layout)
    else:
        pytest.fail(f"never exhausted {kind} events")
    assert killed >= 1


@pytest.mark.parametrize("kind", ["replace", "unlink", "rmdir", "fsync"])
def test_sigkill_at_each_restore_mutation_is_idempotent(tmp_path: Path, kind: str) -> None:
    killed = 0
    for index in range(1, 50):
        layout = Layout(tmp_path / f"{kind}-{index}")
        assert layout.prepare_legacy().returncode == 0
        layout.publish_candidate_state()
        result = layout.run("restore", env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"})
        if result.returncode == 0:
            _assert_legacy_entry(layout)
            assert layout.finish_recovered().returncode == 0
            break
        assert result.returncode == -9
        killed += 1
        inspected = layout.run("inspect")
        assert inspected.returncode == 0, inspected.stderr
        assert inspected.stdout.splitlines()[0] == "active"
        retried = layout.run("restore")
        assert retried.returncode == 0, retried.stderr
        _assert_legacy_entry(layout)
        assert layout.finish_recovered().returncode == 0
    else:
        pytest.fail(f"never exhausted restore {kind} events")
    assert killed >= 1


@pytest.mark.parametrize("kind", ["fsync", "rename"])
def test_sigkill_during_commit_preserves_finalizing_or_committed_authority(tmp_path: Path, kind: str) -> None:
    killed = 0
    for index in range(1, 30):
        layout = Layout(tmp_path / f"{kind}-{index}", dropin_exists=True)
        assert layout.prepare_sealed().returncode == 0
        layout.publish_candidate_state()
        layout.publish_active_rotation()
        assert layout.run("prepare-commit", str(layout.candidate), layout.sha).returncode == 0
        assert layout.run("mark-finalized").returncode == 0
        result = layout.run(
            "commit",
            str(layout.candidate),
            layout.sha,
            env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"},
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            assert layout.run("verify-committed-live", path).returncode == 0
            assert layout.run("cleanup", path).returncode == 0
            break
        assert result.returncode == -9
        killed += 1
        assert layout.run("reconcile").returncode == 0
        inspected = layout.run("inspect")
        assert inspected.returncode == 0, inspected.stderr
        fields = inspected.stdout.splitlines()
        if fields[0] == "finalizing":
            committed = layout.run("commit", str(layout.candidate), layout.sha)
            assert committed.returncode == 0, committed.stderr
            fields = ["committed", committed.stdout.strip(), *fields[2:]]
        assert fields[0] == "committed"
        assert layout.run("verify-committed-live", fields[1]).returncode == 0
        assert layout.run("cleanup", fields[1]).returncode == 0
    else:
        pytest.fail(f"never exhausted commit {kind} events")
    assert killed >= 1


@pytest.mark.parametrize("operation", ["prepare-commit", "mark-finalized"])
@pytest.mark.parametrize("kind", ["write", "fsync", "replace"])
def test_sigkill_during_authority_marker_publish_is_reconcilable(
    tmp_path: Path, operation: str, kind: str
) -> None:
    killed = 0
    for index in range(1, 20):
        layout = Layout(tmp_path / f"{operation}-{kind}-{index}", dropin_exists=True)
        assert layout.prepare_sealed().returncode == 0
        layout.publish_candidate_state()
        layout.publish_active_rotation()
        if operation == "mark-finalized":
            assert layout.run("prepare-commit", str(layout.candidate), layout.sha).returncode == 0
            extra = ()
        else:
            extra = (str(layout.candidate), layout.sha)
        result = layout.run(
            operation,
            *extra,
            env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"},
        )
        if result.returncode != 0:
            assert result.returncode == -9
            killed += 1
            assert layout.run("reconcile").returncode == 0
        inspected = layout.run("inspect")
        assert inspected.returncode == 0, inspected.stderr
        mode = inspected.stdout.splitlines()[0]
        if mode == "active":
            assert operation == "prepare-commit"
            assert layout.run("prepare-commit", str(layout.candidate), layout.sha).returncode == 0
        else:
            assert mode == "finalizing"
        assert layout.run("mark-finalized").returncode == 0
        committed = layout.run("commit", str(layout.candidate), layout.sha)
        assert committed.returncode == 0, committed.stderr
        assert layout.run("verify-committed-live", committed.stdout.strip()).returncode == 0
        assert layout.run("cleanup", committed.stdout.strip()).returncode == 0
        if result.returncode == 0:
            break
    else:
        pytest.fail(f"never exhausted {operation} {kind} events")
    assert killed >= 1


@pytest.mark.parametrize("kind", ["unlink", "rmdir", "fsync"])
def test_sigkill_at_each_gc_event_is_resumed_by_reconcile(tmp_path: Path, kind: str) -> None:
    killed = 0
    for index in range(1, 30):
        layout = Layout(tmp_path / f"{kind}-{index}", dropin_exists=True)
        assert layout.prepare_sealed().returncode == 0
        layout.publish_candidate_state()
        committed = layout.finish_committed()
        assert committed.returncode == 0, committed.stderr
        result = layout.run(
            "cleanup",
            committed.stdout.strip(),
            env={"TW_MCP_TEST_KILL_JOURNAL_AT": f"{kind}:{index}"},
        )
        if result.returncode == 0:
            break
        assert result.returncode == -9
        killed += 1
        reconciled = layout.run("reconcile")
        assert reconciled.returncode == 0, reconciled.stderr
        inspected = layout.run("inspect")
        assert inspected.returncode == 0, inspected.stderr
        assert inspected.stdout.strip() == "none"
    else:
        pytest.fail(f"never exhausted GC {kind} events")
    assert killed >= 1
