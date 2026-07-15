"""Adversarial tests for candidate-free, dedicated-only MCP key provisioning."""

from __future__ import annotations

from contextlib import nullcontext
import hashlib
import hmac
import importlib.util
import inspect
import json
import os
import stat
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_candidate_provision_mcp_key", ROOT / "apiserver" / "provision_mcp_key.py"
)
provisioner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(provisioner)

VALID_KEY = "tw_svc_" + "A" * 43
OLD_KEY = "tw_customer_legacy_mcp_service_key"
ACTIVE_KEY_ID = "11111111-1111-4111-8111-111111111111"
OLD_KEY_ID = "22222222-2222-4222-8222-222222222222"
REPLACEMENT_KEY_ID = "33333333-3333-4333-8333-333333333333"
SECOND_REPLACEMENT_KEY_ID = "44444444-4444-4444-8444-444444444444"
THIRD_REPLACEMENT_KEY_ID = "55555555-5555-4555-8555-555555555555"
VERIFIER_KEY = "tw_live_" + "a" * 32
VERIFIER_KEY_ID = "66666666-6666-4666-8666-666666666666"
VERIFIER_SECOND_KEY_ID = "77777777-7777-4777-8777-777777777777"
VERIFIER_USER_ID = "88888888-8888-4888-8888-888888888888"
VERIFIER_TX_ID = "99999999-9999-4999-8999-999999999999"


def _test_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _chmod(path: Path, mode: int) -> None:
    if os.name != "nt":
        path.chmod(mode)


class FakeServiceRows:
    def __init__(self, legacy: str | None) -> None:
        self.rows: dict[str, dict[str, str]] = {}
        self.inserted: list[tuple[str, str]] = []
        if legacy:
            self.rows[OLD_KEY_ID] = {"raw": legacy, "status": "active"}

    def active_for_raw(self, raw: str):
        for key_id, row in self.rows.items():
            if row["raw"] == raw and row["status"] == "active":
                return key_id
        return None

    def binding(self, raw: str):
        key_id = self.active_for_raw(raw)
        if key_id is None:
            raise provisioner.ProvisionError(
                "configured MCP key lacks exact reserved binding"
            )
        return "service-user", key_id

    def ensure(self, raw: str):
        return "service-user", self.active_for_raw(raw) if raw else None

    def insert(self, _user, raw: str, key_id: str):
        assert key_id not in self.rows
        self.rows[key_id] = {"raw": raw, "status": "active"}
        self.inserted.append((key_id, raw))
        return key_id

    def status(self, key_id: str, digest: str) -> str:
        row = self.rows.get(str(key_id))
        if row is None:
            return "missing"
        if _test_hash(row["raw"]) != digest:
            raise provisioner.ProvisionError("row hash mismatch")
        return row["status"]

    def revoke_bound(self, key_id: str, digest: str) -> None:
        status = self.status(str(key_id), digest)
        if status == "missing":
            raise provisioner.ProvisionError("missing state-bound row")
        self.rows[str(key_id)]["status"] = "revoked"

    def revoke_other(self, _user, keep_id: str) -> None:
        for key_id, row in self.rows.items():
            if key_id != str(keep_id) and row["status"] == "active":
                row["status"] = "revoked"

    def revoke_all(self, _user) -> None:
        for row in self.rows.values():
            row["status"] = "revoked"

    def assert_only_active(self, _user, keep_id: str) -> None:
        extras = [
            key_id
            for key_id, row in self.rows.items()
            if key_id != str(keep_id) and row["status"] == "active"
        ]
        if extras:
            raise provisioner.ProvisionError("unexpected extra active service key")


def _write_platform(path: Path, key: str | None) -> None:
    content = [
        "POSTGRES_DSN='postgresql://db.example/tradewave'\n",
        "API_KEY_HMAC_SECRET='unit-hmac-secret'\n",
        "UNRELATED_PLATFORM_SECRET='ignored-as-data'\n",
    ]
    if key is not None:
        content.append(f"MCP_GATEWAY_KEY={key}\n")
    path.write_text("".join(content), encoding="utf-8")
    _chmod(path, 0o640)


def _write_runtime(path: Path, key: str) -> None:
    path.write_text(
        f"API_BASE_URL=http://127.0.0.1:8088\nMCP_GATEWAY_KEY={key}\n",
        encoding="utf-8",
    )
    _chmod(path, 0o600)


def _configure(
    tmp_path: Path,
    monkeypatch,
    *,
    broad_key: str | None = OLD_KEY,
    runtime_key: str | None = OLD_KEY,
):
    broad = tmp_path / "secrets.env"
    runtime = tmp_path / "mcpserver.env"
    _write_platform(broad, broad_key)
    if runtime_key is not None:
        _write_runtime(runtime, runtime_key)
    monkeypatch.setattr(provisioner, "SECRETS_PATH", str(broad))
    monkeypatch.setattr(provisioner, "MCP_ENV_PATH", str(runtime))
    monkeypatch.setattr(
        provisioner, "ROTATION_STATE_PATH", str(tmp_path / "rotation.json")
    )
    monkeypatch.setattr(provisioner, "_exclusive_lock", nullcontext)
    monkeypatch.setattr(provisioner, "_release_not_active", nullcontext)
    monkeypatch.setattr(
        provisioner, "_verify_gateway_classification", lambda _raw: None
    )
    monkeypatch.setattr(provisioner, "_key_hash", _test_hash)
    identifiers = iter(
        (REPLACEMENT_KEY_ID, SECOND_REPLACEMENT_KEY_ID, THIRD_REPLACEMENT_KEY_ID)
    )
    monkeypatch.setattr(
        provisioner.uuid,
        "uuid4",
        lambda: provisioner.uuid.UUID(next(identifiers)),
    )
    rows = FakeServiceRows(broad_key)
    monkeypatch.setattr(
        provisioner, "_find_service_binding_for_provision", rows.binding
    )
    monkeypatch.setattr(provisioner, "_find_exact_service_binding", rows.binding)
    monkeypatch.setattr(provisioner, "_ensure_user_and_find_key", rows.ensure)
    monkeypatch.setattr(provisioner, "_insert_key", rows.insert)
    monkeypatch.setattr(provisioner, "_bound_key_status", rows.status)
    monkeypatch.setattr(provisioner, "_revoke_bound_key", rows.revoke_bound)
    monkeypatch.setattr(provisioner, "_revoke_other_keys", rows.revoke_other)
    monkeypatch.setattr(provisioner, "_revoke_all_service_keys", rows.revoke_all)
    monkeypatch.setattr(
        provisioner, "_assert_no_active_service_keys", lambda _user: None
    )
    monkeypatch.setattr(
        provisioner, "_assert_allowed_active_service_keys", lambda *_: None
    )
    monkeypatch.setattr(
        provisioner, "_assert_no_other_active_service_keys", rows.assert_only_active
    )
    return broad, runtime, rows


def _configure_active(tmp_path: Path, monkeypatch):
    broad, runtime, rows = _configure(
        tmp_path,
        monkeypatch,
        broad_key=None,
        runtime_key=VALID_KEY,
    )
    rows.rows[ACTIVE_KEY_ID] = {"raw": VALID_KEY, "status": "active"}
    provisioner._write_rotation_state(
        {
            "version": 2,
            "status": "active",
            "replacement_key_id": ACTIVE_KEY_ID,
            "replacement_key_hash": _test_hash(VALID_KEY),
            "superseded_key_id": None,
            "superseded_key_hash": None,
            "source_key_hash": provisioner._ABSENT_SOURCE_HASH,
        }
    )
    return broad, runtime, rows


def _broad_has_key(path: Path) -> bool:
    return any(
        provisioner._ASSIGNMENT_RE.match(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def test_provisioner_has_no_candidate_source_import_boundary():
    source = Path(provisioner.__file__).read_text(encoding="utf-8")
    loader = inspect.getsource(provisioner._gateway_dependencies)
    assert "from apiserver" not in source
    assert "import apiserver" not in source
    assert "--source-root" not in source
    assert "apiserver.settings" not in source
    assert "apiserver.db" not in source
    assert "import psycopg2" in loader
    assert "candidate application modules" in loader


def test_gateway_dependencies_require_stdlib_first_and_sealed_site_last(
    tmp_path, monkeypatch
):
    site = tmp_path / "provision-venv" / "lib" / "python3.13" / "site-packages"
    package = site / "psycopg2"
    package.mkdir(parents=True)
    driver_file = package / "__init__.py"
    extras_file = package / "extras.py"
    driver_file.write_text("", encoding="utf-8")
    extras_file.write_text("", encoding="utf-8")

    driver = types.ModuleType("psycopg2")
    driver.__file__ = str(driver_file)
    driver.__path__ = [str(package)]
    driver.__version__ = "2.9.12 (dt dec pq3 ext lo64)"
    extras = types.ModuleType("psycopg2.extras")
    extras.__file__ = str(extras_file)
    extras.RealDictCursor = object
    driver.extras = extras
    monkeypatch.setitem(sys.modules, "psycopg2", driver)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)
    monkeypatch.setattr(
        provisioner.sys,
        "path",
        [*provisioner._SYSTEM_STDLIB_PATH, str(site)],
    )

    adapter = provisioner._gateway_dependencies()
    assert adapter._driver is driver
    assert adapter._extras is extras


@pytest.mark.parametrize(
    "path_factory",
    [
        lambda site: [str(site), *provisioner._SYSTEM_STDLIB_PATH],
        lambda site: [*provisioner._SYSTEM_STDLIB_PATH, str(site), str(site)],
        lambda site: [*provisioner._SYSTEM_STDLIB_PATH[:-1], str(site)],
        lambda site: [*provisioner._SYSTEM_STDLIB_PATH, str(site), "candidate-source"],
    ],
)
def test_gateway_dependencies_reject_any_other_import_path(
    tmp_path, monkeypatch, path_factory
):
    site = tmp_path / "provision-venv" / "lib" / "python3.13" / "site-packages"
    site.mkdir(parents=True)
    monkeypatch.setattr(provisioner.sys, "path", path_factory(site))
    with pytest.raises(provisioner.ProvisionError, match="system-stdlib-first"):
        provisioner._gateway_dependencies()


def test_key_hash_matches_gateway_hmac_and_fails_closed_without_secret(monkeypatch):
    raw = "tw_live_" + "c" * 32
    monkeypatch.setattr(provisioner.settings, "API_KEY_HMAC_SECRET", "hmac-secret")
    assert (
        provisioner._key_hash(raw)
        == hmac.new(b"hmac-secret", raw.encode(), hashlib.sha256).hexdigest()
    )
    monkeypatch.setattr(provisioner.settings, "API_KEY_HMAC_SECRET", None)
    with pytest.raises(provisioner.ProvisionError, match="unset"):
        provisioner._key_hash(raw)


def test_platform_parser_treats_shell_syntax_only_as_data(tmp_path, monkeypatch):
    broad, _runtime, _rows = _configure(tmp_path, monkeypatch)
    marker = tmp_path / "executed"
    broad.write_text(
        broad.read_text(encoding="utf-8")
        + f"IGNORED=$(touch {marker})\n"
        + "APPSERVER_URL=`false`\n",
        encoding="utf-8",
    )
    _chmod(broad, 0o640)
    assert provisioner._load_platform_settings() == OLD_KEY
    assert not marker.exists()


def test_platform_parser_rejects_conflicting_or_duplicate_security_values(
    tmp_path, monkeypatch
):
    broad, _runtime, _rows = _configure(tmp_path, monkeypatch)
    with broad.open("a", encoding="utf-8") as stream:
        stream.write("API_KEY_HMAC_SECRET=second\n")
    with pytest.raises(provisioner.ProvisionError, match="duplicate API_KEY"):
        provisioner._load_platform_settings()


def test_legacy_k0_rotates_to_dedicated_only_k1(tmp_path, monkeypatch):
    broad, runtime, rows = _configure(tmp_path, monkeypatch)
    result = provisioner.provision()
    k1 = provisioner._read_runtime_key(required=True)
    assert result["action"] == "rotated"
    assert k1.startswith("tw_svc_") and k1 != OLD_KEY
    assert not _broad_has_key(broad)
    assert "POSTGRES_DSN" in broad.read_text(encoding="utf-8")
    assert runtime.read_text(encoding="utf-8").count("MCP_GATEWAY_KEY=") == 1
    state = provisioner._read_rotation_state(required=True)
    assert state["status"] == "pending"
    assert state["superseded_key_id"] == OLD_KEY_ID
    assert rows.rows[OLD_KEY_ID]["status"] == "active"
    assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "active"


def test_all_duplicate_same_broad_assignments_are_removed(tmp_path, monkeypatch):
    broad, _runtime, _rows = _configure(tmp_path, monkeypatch)
    with broad.open("a", encoding="utf-8") as stream:
        stream.write(f"export MCP_GATEWAY_KEY='{OLD_KEY}'\n")
    provisioner.provision()
    assert not _broad_has_key(broad)


def test_initially_absent_runtime_is_created_root_only(tmp_path, monkeypatch):
    broad, runtime, _rows = _configure(tmp_path, monkeypatch, runtime_key=None)
    provisioner.provision()
    assert runtime.exists()
    assert provisioner._read_runtime_key(required=True).startswith("tw_svc_")
    assert not _broad_has_key(broad)
    if os.name != "nt":
        assert stat.S_IMODE(runtime.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("seam", "first_inserted", "expected_first_status"),
    [
        ("_after_service_plan_fsync", False, "planned"),
        ("_after_service_key_insert", True, "planned"),
        ("_before_service_pending_fsync", True, "planned"),
        ("_after_rotation_state_fsync", True, "pending"),
        ("_after_first_environment_fsync", True, "pending"),
        ("_after_broad_key_removal_fsync", True, "pending"),
    ],
)
def test_every_db_file_fsync_seam_recovers_idempotently(
    tmp_path, monkeypatch, seam, first_inserted, expected_first_status
):
    broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    calls = {"count": 0}

    def crash_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise SystemExit(f"crash at {seam}")

    monkeypatch.setattr(provisioner, seam, crash_once)
    with pytest.raises(SystemExit, match="crash at"):
        provisioner.provision()
    state = provisioner._read_rotation_state(required=True)
    assert state["status"] == expected_first_status
    assert (REPLACEMENT_KEY_ID in rows.rows) is first_inserted

    result = provisioner.provision()
    assert result["action"] in {"rotated", "reused"}
    assert not _broad_has_key(broad)
    assert provisioner._read_runtime_key(required=True).startswith("tw_svc_")
    assert provisioner._read_rotation_state(required=True)["status"] == "pending"
    if seam in {"_after_first_environment_fsync", "_after_broad_key_removal_fsync"}:
        assert len(rows.inserted) == 1
    elif first_inserted:
        assert len(rows.inserted) == 2
        assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "revoked"


def test_runtime_write_failure_keeps_k0_broad_and_pending_state(tmp_path, monkeypatch):
    broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(
        provisioner,
        "_write_runtime_key",
        lambda _raw: (_ for _ in ()).throw(provisioner.ProvisionError("write failed")),
    )
    with pytest.raises(provisioner.ProvisionError, match="write failed"):
        provisioner.provision()
    assert _broad_has_key(broad)
    assert provisioner._read_rotation_state(required=True)["status"] == "pending"
    assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "active"


def test_broad_removal_failure_resumes_without_minting_another_k1(
    tmp_path, monkeypatch
):
    broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    original = provisioner._remove_broad_service_assignments
    calls = {"count": 0}

    def fail_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise provisioner.ProvisionError("broad fsync failed")
        original()

    monkeypatch.setattr(provisioner, "_remove_broad_service_assignments", fail_once)
    with pytest.raises(provisioner.ProvisionError, match="broad fsync failed"):
        provisioner.provision()
    k1 = provisioner._read_runtime_key(required=True)
    assert _broad_has_key(broad)
    assert provisioner.provision()["action"] == "reused"
    assert provisioner._read_runtime_key(required=True) == k1
    assert len(rows.inserted) == 1
    assert not _broad_has_key(broad)


def test_active_dedicated_only_state_reuses_without_mutation(tmp_path, monkeypatch):
    broad, runtime, rows = _configure(
        tmp_path, monkeypatch, broad_key=None, runtime_key=VALID_KEY
    )
    rows.rows[ACTIVE_KEY_ID] = {"raw": VALID_KEY, "status": "active"}
    provisioner._write_rotation_state(
        {
            "version": 2,
            "status": "active",
            "replacement_key_id": ACTIVE_KEY_ID,
            "replacement_key_hash": _test_hash(VALID_KEY),
            "superseded_key_id": None,
            "superseded_key_hash": None,
            "source_key_hash": provisioner._ABSENT_SOURCE_HASH,
        }
    )
    assert provisioner.provision()["action"] == "reused"
    assert provisioner._read_runtime_key(required=True) == VALID_KEY
    assert not _broad_has_key(broad)
    assert rows.inserted == []


@pytest.mark.parametrize("release_mode", ["normal", "rollback"])
def test_post_journal_recovery_preserves_exact_steady_active_state(
    tmp_path, monkeypatch, release_mode
):
    broad, runtime, rows = _configure_active(tmp_path, monkeypatch)
    state_path = Path(provisioner.ROTATION_STATE_PATH)
    gateway_proofs = []
    monkeypatch.setattr(
        provisioner,
        "_verify_gateway_classification",
        lambda raw_key: gateway_proofs.append(raw_key),
    )

    if release_mode == "normal":
        assert provisioner.provision()["action"] == "reused"
    else:
        assert provisioner.check_service()["key_id"] == ACTIVE_KEY_ID

    journal_snapshots = {
        broad: (broad.read_bytes(), 0o640),
        runtime: (runtime.read_bytes(), 0o600),
        state_path: (state_path.read_bytes(), 0o600),
    }
    for path, (payload, mode) in journal_snapshots.items():
        path.write_bytes(payload)
        _chmod(path, mode)
    restored_files = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in journal_snapshots
    }
    restored_rows = {key_id: dict(row) for key_id, row in rows.rows.items()}

    expected = {
        "action": "nothing-to-abort",
        "legacy_preserved": False,
        "user_id": "service-user",
        "replacement_revoked": False,
    }
    assert provisioner.abort() == expected
    assert provisioner.abort() == expected
    assert rows.rows == restored_rows
    assert rows.inserted == []
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in journal_snapshots
    } == restored_files
    assert gateway_proofs == [VALID_KEY, VALID_KEY, VALID_KEY]


@pytest.mark.parametrize(
    "near_match", ["broad-present", "runtime-missing", "runtime-different"]
)
def test_active_abort_rejects_environment_near_matches(
    tmp_path, monkeypatch, near_match
):
    broad, runtime, rows = _configure_active(tmp_path, monkeypatch)
    if near_match == "broad-present":
        _write_platform(broad, OLD_KEY)
    elif near_match == "runtime-missing":
        runtime.unlink()
    else:
        different = "tw_svc_" + "B" * 43
        _write_runtime(runtime, different)
        rows.rows[SECOND_REPLACEMENT_KEY_ID] = {
            "raw": different,
            "status": "active",
        }

    with pytest.raises(provisioner.ProvisionError):
        provisioner.abort()
    assert rows.rows[ACTIVE_KEY_ID]["status"] == "active"


@pytest.mark.parametrize("near_match", ["state-hash", "state-id"])
def test_active_abort_rejects_state_near_matches(tmp_path, monkeypatch, near_match):
    _broad, _runtime, rows = _configure_active(tmp_path, monkeypatch)
    state = provisioner._read_rotation_state(required=True)
    if near_match == "state-hash":
        state["replacement_key_hash"] = "0" * 64
    else:
        state["replacement_key_id"] = SECOND_REPLACEMENT_KEY_ID
    provisioner._write_rotation_state(state)

    with pytest.raises(provisioner.ProvisionError, match="root-owned rotation state"):
        provisioner.abort()
    assert rows.rows[ACTIVE_KEY_ID]["status"] == "active"


@pytest.mark.parametrize("near_match", ["db-missing", "db-revoked", "wrong-profile"])
def test_active_abort_rejects_database_identity_near_matches(
    tmp_path, monkeypatch, near_match
):
    _broad, _runtime, rows = _configure_active(tmp_path, monkeypatch)
    if near_match == "db-missing":
        del rows.rows[ACTIVE_KEY_ID]
    elif near_match == "db-revoked":
        rows.rows[ACTIVE_KEY_ID]["status"] = "revoked"
    else:
        monkeypatch.setattr(
            provisioner,
            "_find_exact_service_binding",
            lambda _raw: (_ for _ in ()).throw(
                provisioner.ProvisionError(
                    "API-key row lacks the exact reserved service identity/name"
                )
            ),
        )

    with pytest.raises(provisioner.ProvisionError):
        provisioner.abort()


def test_active_abort_rejects_sibling_or_failed_live_classification(
    tmp_path, monkeypatch
):
    _broad, _runtime, rows = _configure_active(tmp_path, monkeypatch)
    rows.rows[SECOND_REPLACEMENT_KEY_ID] = {
        "raw": "tw_svc_" + "C" * 43,
        "status": "active",
    }
    with pytest.raises(provisioner.ProvisionError, match="extra active service key"):
        provisioner.abort()

    rows.rows[SECOND_REPLACEMENT_KEY_ID]["status"] = "revoked"
    monkeypatch.setattr(
        provisioner,
        "_verify_gateway_classification",
        lambda _raw: (_ for _ in ()).throw(
            provisioner.ProvisionError("live gateway classification failed")
        ),
    )
    with pytest.raises(provisioner.ProvisionError, match="classification failed"):
        provisioner.abort()


def test_check_service_reads_dedicated_only_and_rejects_broad_assignment(
    tmp_path, monkeypatch
):
    broad, _runtime, _rows = _configure(tmp_path, monkeypatch)
    provisioner.provision()
    provisioner.check_service()
    with broad.open("a", encoding="utf-8") as stream:
        stream.write(f"MCP_GATEWAY_KEY={OLD_KEY}\n")
    with pytest.raises(provisioner.ProvisionError, match="must be absent"):
        provisioner.check_service()


def test_finalize_proves_pid_k1_then_revokes_k0_and_every_sibling(
    tmp_path, monkeypatch
):
    _broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    provisioner.provision()
    k1 = provisioner._read_runtime_key(required=True)
    rows.rows[THIRD_REPLACEMENT_KEY_ID] = {
        "raw": "tw_svc_" + "Z" * 43,
        "status": "active",
    }
    monkeypatch.setattr(provisioner, "_process_key", lambda _pid: k1)
    result = provisioner.finalize(1234)
    assert result["exact_superseded_key_finalized"] is True
    assert rows.rows[OLD_KEY_ID]["status"] == "revoked"
    assert rows.rows[THIRD_REPLACEMENT_KEY_ID]["status"] == "revoked"
    assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "active"
    assert provisioner._read_rotation_state(required=True)["status"] == "active"


def test_finalize_wrong_pid_never_revokes_k0(tmp_path, monkeypatch):
    _broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    provisioner.provision()
    monkeypatch.setattr(provisioner, "_process_key", lambda _pid: OLD_KEY)
    with pytest.raises(provisioner.ProvisionError, match="does not use dedicated K1"):
        provisioner.finalize(1234)
    assert rows.rows[OLD_KEY_ID]["status"] == "active"


@pytest.mark.parametrize(
    ("broad_key", "runtime_key", "legacy_preserved"),
    [(OLD_KEY, OLD_KEY, True), (None, None, False)],
    ids=["restored-k0", "originally-absent"],
)
def test_abort_before_provision_is_an_authenticated_noop(
    tmp_path, monkeypatch, broad_key, runtime_key, legacy_preserved
):
    _configure(
        tmp_path,
        monkeypatch,
        broad_key=broad_key,
        runtime_key=runtime_key,
    )
    result = provisioner.abort()
    assert result == {
        "action": "nothing-to-abort",
        "legacy_preserved": legacy_preserved,
        "user_id": "service-user" if legacy_preserved else None,
        "replacement_revoked": False,
    }


@pytest.mark.parametrize(
    "runtime_restored", [True, False], ids=["restored-k0", "originally-absent"]
)
def test_abort_after_snapshot_restore_revokes_only_k1_and_clears_state(
    tmp_path, monkeypatch, runtime_restored
):
    broad, runtime, rows = _configure(
        tmp_path, monkeypatch, runtime_key=OLD_KEY if runtime_restored else None
    )
    provisioner.provision()
    _write_platform(broad, OLD_KEY)
    if runtime_restored:
        _write_runtime(runtime, OLD_KEY)
    else:
        runtime.unlink()
    result = provisioner.abort()
    assert result["legacy_preserved"] is True
    assert rows.rows[OLD_KEY_ID]["status"] == "active"
    assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "revoked"
    assert not Path(provisioner.ROTATION_STATE_PATH).exists()
    assert provisioner._read_key(str(broad), required=True) == OLD_KEY
    replay = provisioner.abort()
    assert replay["action"] == "nothing-to-abort"
    assert replay["replacement_revoked"] is False


def test_abort_rejects_when_controller_has_not_restored_dedicated_snapshot(
    tmp_path, monkeypatch
):
    broad, _runtime, rows = _configure(tmp_path, monkeypatch)
    provisioner.provision()
    _write_platform(broad, OLD_KEY)
    with pytest.raises(provisioner.ProvisionError, match="restore dedicated K0"):
        provisioner.abort()
    assert rows.rows[REPLACEMENT_KEY_ID]["status"] == "active"


def test_abort_planned_state_with_missing_k1_row_is_idempotent(tmp_path, monkeypatch):
    broad, runtime, rows = _configure(tmp_path, monkeypatch)
    provisioner._write_rotation_state(
        {
            "version": 2,
            "status": "planned",
            "replacement_key_id": REPLACEMENT_KEY_ID,
            "replacement_key_hash": _test_hash(VALID_KEY),
            "superseded_key_id": OLD_KEY_ID,
            "superseded_key_hash": _test_hash(OLD_KEY),
            "source_key_hash": _test_hash(OLD_KEY),
        }
    )
    provisioner.abort()
    assert rows.rows[OLD_KEY_ID]["status"] == "active"
    assert _broad_has_key(broad)
    assert provisioner._read_runtime_key(required=True) == OLD_KEY
    assert not Path(provisioner.ROTATION_STATE_PATH).exists()


def test_dedicated_mode_and_symlink_tamper_fail_closed(tmp_path, monkeypatch):
    _broad, runtime, _rows = _configure(tmp_path, monkeypatch)
    if os.name != "nt":
        runtime.chmod(0o644)
        with pytest.raises(provisioner.ProvisionError, match="0600"):
            provisioner._read_runtime_key(required=True)
        runtime.chmod(0o600)
    target = tmp_path / "target.env"
    _write_runtime(target, OLD_KEY)
    runtime.unlink()
    try:
        runtime.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(provisioner.ProvisionError, match="single-link regular"):
        provisioner._read_runtime_key(required=True)


def test_broad_mode_and_symlink_tamper_fail_closed(tmp_path, monkeypatch):
    broad, _runtime, _rows = _configure(tmp_path, monkeypatch)
    if os.name != "nt":
        broad.chmod(0o666)
        with pytest.raises(provisioner.ProvisionError, match="permissions"):
            provisioner._load_platform_settings()
        broad.chmod(0o640)
    target = tmp_path / "platform-target.env"
    _write_platform(target, OLD_KEY)
    broad.unlink()
    try:
        broad.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(provisioner.ProvisionError, match="single-link regular"):
        provisioner._load_platform_settings()


def test_rotation_state_schema_and_mode_tamper_fail_closed(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    state_path = Path(provisioner.ROTATION_STATE_PATH)
    state_path.write_text(json.dumps({"status": "pending"}), encoding="utf-8")
    _chmod(state_path, 0o600)
    with pytest.raises(provisioner.ProvisionError, match="invalid schema"):
        provisioner._read_rotation_state(required=True)
    if os.name != "nt":
        state_path.chmod(0o644)
        with pytest.raises(provisioner.ProvisionError, match="0600"):
            provisioner._read_rotation_state(required=True)


class FakeVerifierRows:
    def __init__(self) -> None:
        self.ids = iter((VERIFIER_KEY_ID, VERIFIER_SECOND_KEY_ID))
        self.rows: dict[str, dict[str, object]] = {}
        self.insert_count = 0
        self.revoke_count = 0

    def find_user(self, *, create: bool):
        return VERIFIER_USER_ID if create or self.rows else None

    def insert(self, user_id, key_name: str, raw_key: str):
        assert user_id == VERIFIER_USER_ID
        key_id = next(self.ids)
        self.rows[key_id] = {
            "id": key_id,
            "name": key_name,
            "key_hash": _test_hash(raw_key),
            "revoked_at": None,
        }
        self.insert_count += 1
        return key_id

    def verify(self, state, *, require_active: bool):
        row = self.rows.get(str(state["key_id"]))
        if not row or not (
            row["name"] == state["key_name"]
            and row["key_hash"] == state["key_hash"]
        ):
            raise provisioner.ProvisionError("fake exact verifier binding failed")
        status = "revoked" if row["revoked_at"] else "active"
        if require_active and status != "active":
            raise provisioner.ProvisionError("fake verifier row is revoked")
        return status

    def revoke(self, state):
        row = self.rows.get(str(state["key_id"]))
        if row is None:
            return False
        if not (
            row["name"] == state["key_name"]
            and row["key_hash"] == state["key_hash"]
        ):
            raise provisioner.ProvisionError("fake revoke escaped exact binding")
        if row["revoked_at"]:
            return False
        row["revoked_at"] = "revoked"
        self.revoke_count += 1
        return True

    def active(self, user_id):
        assert user_id == VERIFIER_USER_ID
        return [dict(row) for row in self.rows.values() if not row["revoked_at"]]


def _write_release_journal(tmp_path: Path, transaction_id: str) -> Path:
    root = tmp_path / "journal"
    active = root / "active"
    active.mkdir(parents=True)
    _chmod(root, 0o700)
    _chmod(active, 0o700)
    manifest = active / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 4,
                "txid": transaction_id,
                "candidate": {"bundle": "/sealed/candidate", "sha": "a" * 40},
                "entry": {
                    "kind": "sealed",
                    "policy": "fenced",
                    "bundle": "/sealed/candidate",
                    "sha": "a" * 40,
                    "cwd": "/sealed/candidate/src",
                    "command": "/sealed/candidate/venv/bin/python",
                    "argv_sha256": "b" * 64,
                    "active": True,
                },
                "gateway_entry": {
                    "kind": "sealed",
                    "policy": "fenced",
                    "bundle": "/sealed/candidate",
                    "sha": "a" * 40,
                    "cwd": "/sealed/candidate/src",
                    "command": "/sealed/candidate/gateway-venv/bin/gunicorn",
                    "argv_sha256": "c" * 64,
                    "active": True,
                },
                "files": {},
                "pointers": {},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    _chmod(manifest, 0o600)
    return manifest


def _configure_verifier_probe(tmp_path: Path, monkeypatch):
    _configure(tmp_path, monkeypatch, broad_key=None, runtime_key=None)
    state_root = tmp_path / "verifier-state"
    credential_root = tmp_path / "verifier-run"
    legacy = tmp_path / "legacy-verifier.env"
    monkeypatch.setattr(provisioner, "VERIFIER_STATE_ROOT", str(state_root))
    monkeypatch.setattr(provisioner, "VERIFIER_CREDENTIAL_ROOT", str(credential_root))
    monkeypatch.setattr(provisioner, "RELEASE_JOURNAL_ROOT", str(tmp_path / "journal"))
    monkeypatch.setattr(provisioner, "LEGACY_VERIFIER_ENV_PATH", str(legacy))
    monkeypatch.setattr(provisioner, "_verify_release_verifier_key", lambda _raw: None)

    def prepare_test_tree(path: str, *, label: str):
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        _chmod(directory, 0o700)
        return str(directory)

    # pytest's Linux tmp root is intentionally 01777; production path-walk
    # rejection is tested separately while lifecycle tests use private leaves.
    monkeypatch.setattr(provisioner, "_prepare_private_tree", prepare_test_tree)
    tokens = iter(("a" * 32, "b" * 32, "c" * 32))
    monkeypatch.setattr(provisioner._secrets, "token_hex", lambda _size: next(tokens))
    rows = FakeVerifierRows()
    monkeypatch.setattr(provisioner, "_find_or_create_verifier_user", rows.find_user)
    monkeypatch.setattr(provisioner, "_insert_verifier_probe", rows.insert)
    monkeypatch.setattr(provisioner, "_verify_verifier_probe_binding", rows.verify)
    monkeypatch.setattr(provisioner, "_revoke_verifier_probe_binding", rows.revoke)
    monkeypatch.setattr(provisioner, "_active_verifier_rows", rows.active)
    manifest = _write_release_journal(tmp_path, VERIFIER_TX_ID)
    state_path = state_root / f"{VERIFIER_TX_ID}.json"
    credential_path = credential_root / VERIFIER_TX_ID / "verify-env"
    return rows, manifest, state_path, credential_path


def test_verifier_mint_is_journal_first_state_before_secret_and_no_secret_output(
    tmp_path, monkeypatch, capsys
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    events = []
    verify_journal = provisioner._verify_durable_release_journal
    find_user = rows.find_user

    def ordered_journal(*args):
        events.append("journal")
        return verify_journal(*args)

    def ordered_user(*, create):
        events.append("db")
        return find_user(create=create)

    def after_state():
        events.append("state")
        assert state_path.exists()
        assert not credential_path.exists()

    monkeypatch.setattr(provisioner, "_verify_durable_release_journal", ordered_journal)
    monkeypatch.setattr(provisioner, "_find_or_create_verifier_user", ordered_user)
    monkeypatch.setattr(provisioner, "_after_verifier_state_fsync", after_state)
    result = provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    assert result["action"] == "minted"
    assert events.index("journal") < events.index("db") < events.index("state")
    raw = "tw_live_" + "a" * 32
    assert credential_path.read_bytes() == f"TW_MCP_VERIFY_TOKEN={raw}\n".encode()
    state_bytes = state_path.read_bytes()
    assert raw.encode() not in state_bytes
    assert b"tw_live_" not in state_bytes
    assert set(json.loads(state_bytes)) == provisioner._VERIFIER_STATE_FIELDS
    assert raw not in capsys.readouterr().out
    assert rows.insert_count == 1


def test_verifier_mint_retry_reuses_exact_transaction_without_new_key(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    first = provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    second = provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    assert first["key_id"] == second["key_id"] == VERIFIER_KEY_ID
    assert second["action"] == "reused"
    assert rows.insert_count == 1
    assert rows.revoke_count == 0


def test_verifier_retry_after_state_only_crash_revokes_then_remints(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )

    def crash_after_state():
        raise RuntimeError("simulated power loss")

    monkeypatch.setattr(provisioner, "_after_verifier_state_fsync", crash_after_state)
    with pytest.raises(RuntimeError, match="power loss"):
        provisioner.mint_verifier_probe(
            VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
        )
    assert state_path.exists()
    assert not credential_path.exists()
    monkeypatch.setattr(provisioner, "_after_verifier_state_fsync", lambda: None)
    result = provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    assert result["key_id"] == VERIFIER_SECOND_KEY_ID
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert rows.insert_count == 2


def test_verifier_revoke_is_exact_idempotent_and_removes_raw_first(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    observed = []
    revoke = rows.revoke

    def assert_unlinked_before_db(state):
        observed.append(not credential_path.exists())
        return revoke(state)

    monkeypatch.setattr(
        provisioner, "_revoke_verifier_probe_binding", assert_unlinked_before_db
    )
    first = provisioner.revoke_verifier_probe(
        VERIFIER_TX_ID, str(state_path), str(credential_path)
    )
    second = provisioner.revoke_verifier_probe(
        VERIFIER_TX_ID, str(state_path), str(credential_path)
    )
    assert observed == [True]
    assert first["rows_revoked"] == 1
    assert second["rows_revoked"] == 0
    assert not state_path.exists()
    assert not credential_path.exists()


def test_verifier_startup_purge_removes_state_marker_and_raw_temporary(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    temporary = credential_path.parent / ".mcp-probe-crashwindow"
    temporary.write_text("TW_MCP_VERIFY_TOKEN=tw_live_" + "f" * 32 + "\n")
    _chmod(temporary, 0o600)
    result = provisioner.purge_stale_verifier_probes()
    assert result == {
        "credential_files_removed": 1,
        "state_files_removed": 1,
        "rows_revoked": 1,
    }
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert not credential_path.parent.exists()
    assert not state_path.exists()


def test_verifier_platform_secret_leak_cannot_block_startup_revocation(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    broad = Path(provisioner.SECRETS_PATH)
    broad.write_text(
        broad.read_text(encoding="utf-8")
        + "TW_MCP_VERIFY_TOKEN=tw_live_"
        + "a" * 32
        + "\n",
        encoding="utf-8",
    )
    _chmod(broad, 0o640)

    with pytest.raises(
        provisioner.ProvisionError,
        match="TW_MCP_VERIFY_TOKEN must be removed",
    ):
        provisioner.purge_stale_verifier_probes()

    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert not credential_path.parent.exists()
    assert not state_path.exists()


def test_verifier_journal_mismatch_blocks_before_any_db_or_secret_mutation(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    value = json.loads(manifest.read_text())
    value["txid"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    manifest.write_text(json.dumps(value) + "\n")
    _chmod(manifest, 0o600)
    with pytest.raises(provisioner.ProvisionError, match="does not bind"):
        provisioner.mint_verifier_probe(
            VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
        )
    assert rows.insert_count == 0
    assert not state_path.exists()
    assert not credential_path.exists()


def test_verifier_journal_requires_exact_v4_gateway_bound_schema(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    valid = json.loads(manifest.read_text(encoding="utf-8"))
    assert valid["version"] == 4
    assert set(valid["gateway_entry"]) == {
        "kind",
        "policy",
        "bundle",
        "sha",
        "cwd",
        "command",
        "argv_sha256",
        "active",
    }

    near_misses = []
    value = json.loads(json.dumps(valid))
    value["version"] = 3
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["unexpected"] = True
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    del value["gateway_entry"]
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["candidate"]["unexpected"] = "field"
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["gateway_entry"]["unexpected"] = "field"
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["gateway_entry"]["active"] = False
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["entry"]["kind"] = "unknown"
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["entry"]["argv_sha256"] = "not-a-digest"
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["gateway_entry"]["cwd"] = 7
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["files"] = []
    near_misses.append(value)
    value = json.loads(json.dumps(valid))
    value["pointers"] = []
    near_misses.append(value)

    for value in near_misses:
        manifest.write_text(json.dumps(value) + "\n", encoding="utf-8")
        _chmod(manifest, 0o600)
        with pytest.raises(provisioner.ProvisionError, match="release journal"):
            provisioner.mint_verifier_probe(
                VERIFIER_TX_ID,
                str(manifest),
                str(state_path),
                str(credential_path),
            )

    assert rows.insert_count == 0
    assert not state_path.exists()
    assert not credential_path.exists()


def test_verifier_gateway_failure_revokes_row_and_removes_all_artifacts(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        provisioner,
        "_verify_release_verifier_key",
        lambda _raw: (_ for _ in ()).throw(
            provisioner.ProvisionError("live Pro classification failed")
        ),
    )
    with pytest.raises(provisioner.ProvisionError, match="classification failed"):
        provisioner.mint_verifier_probe(
            VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
        )
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert not state_path.exists()
    assert not credential_path.exists()


def test_verifier_startup_purge_catches_insert_before_state_crash(
    tmp_path, monkeypatch
):
    rows, _manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    raw = "tw_live_" + "a" * 32
    rows.insert(
        VERIFIER_USER_ID,
        provisioner._verifier_probe_name(VERIFIER_TX_ID),
        raw,
    )
    result = provisioner.purge_stale_verifier_probes()
    assert result["rows_revoked"] == 1
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert not state_path.exists()
    assert not credential_path.exists()


def test_verifier_corrupt_state_cannot_block_exact_marker_revocation(
    tmp_path, monkeypatch
):
    rows, manifest, state_path, credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    provisioner.mint_verifier_probe(
        VERIFIER_TX_ID, str(manifest), str(state_path), str(credential_path)
    )
    state_path.write_text('{"version":1,"unexpected":"tamper"}\n')
    _chmod(state_path, 0o600)
    with pytest.raises(provisioner.ProvisionError, match="invalid schema"):
        provisioner.revoke_verifier_probe(
            VERIFIER_TX_ID, str(state_path), str(credential_path)
        )
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert not credential_path.exists()
    assert state_path.exists()  # retained as integrity-failure evidence


def test_verifier_unknown_account_key_cannot_block_recognized_probe_revoke(
    tmp_path, monkeypatch
):
    rows, _manifest, _state_path, _credential_path = _configure_verifier_probe(
        tmp_path, monkeypatch
    )
    rows.insert(
        VERIFIER_USER_ID,
        provisioner._verifier_probe_name(VERIFIER_TX_ID),
        "tw_live_" + "a" * 32,
    )
    unknown_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    rows.rows[unknown_id] = {
        "id": unknown_id,
        "name": "unrecognized-key",
        "key_hash": "f" * 64,
        "revoked_at": None,
    }
    with pytest.raises(provisioner.ProvisionError, match="integrity errors"):
        provisioner.purge_stale_verifier_probes()
    assert rows.rows[VERIFIER_KEY_ID]["revoked_at"] == "revoked"
    assert rows.rows[unknown_id]["revoked_at"] is None


def test_verifier_live_classification_requires_real_pro_capacity(monkeypatch):
    monkeypatch.setattr(
        provisioner,
        "_gateway_get",
        lambda _raw, _principal: (
            200,
            {
                "tier": "pro",
                "tier_name": "Pro",
                "mcp_admission_id": "acct_" + "1" * 64,
                "rate": {"per_minute": 120, "per_day": 5_000},
            },
        ),
    )
    provisioner._verify_release_verifier_key(VERIFIER_KEY)
    monkeypatch.setattr(
        provisioner,
        "_gateway_get",
        lambda _raw, _principal: (
            200,
            {
                "tier": "pro",
                "tier_name": "Pro",
                "rate": {"per_minute": 120, "per_day": 5_000},
            },
        ),
    )
    with pytest.raises(provisioner.ProvisionError, match="Pro release-verifier"):
        provisioner._verify_release_verifier_key(VERIFIER_KEY)
    monkeypatch.setattr(
        provisioner,
        "_gateway_get",
        lambda _raw, _principal: (
            200,
            {
                "tier": "explorer",
                "tier_name": "Explorer",
                "mcp_admission_id": "acct_" + "2" * 64,
                "rate": {"per_minute": 10_000, "per_day": 10_000},
            },
        ),
    )
    with pytest.raises(provisioner.ProvisionError, match="Pro release-verifier"):
        provisioner._verify_release_verifier_key(VERIFIER_KEY)


def test_verifier_cli_contract_never_prints_raw_or_key_hash(monkeypatch, capsys):
    raw = "tw_live_" + "f" * 32
    digest = _test_hash(raw)
    monkeypatch.setattr(
        provisioner,
        "mint_verifier_probe",
        lambda *_args: {
            "action": "minted",
            "transaction_id": VERIFIER_TX_ID,
            "user_id": VERIFIER_USER_ID,
            "key_id": VERIFIER_KEY_ID,
            "journal_sha256": "e" * 64,
        },
    )
    provisioner.main(
        [
            "--mint-verifier-probe",
            "--transaction-id",
            VERIFIER_TX_ID,
            "--journal-manifest",
            "/var/lib/tradewave/mcp-release-transactions/active/manifest.json",
            "--state-path",
            f"/var/lib/tradewave/mcp-verifier-probes/{VERIFIER_TX_ID}.json",
            "--credential-path",
            f"/run/tradewave-mcp-verifier/{VERIFIER_TX_ID}/verify-env",
        ]
    )
    output = capsys.readouterr().out
    assert raw not in output
    assert digest not in output
    assert "tw_live_" not in output
    source = Path(provisioner.__file__).read_text(encoding="utf-8")
    assert "--provision-verifier" not in source
    assert "--check-verifier" not in source


def test_cli_output_never_contains_raw_credentials_or_hashes(monkeypatch, capsys):
    monkeypatch.setattr(
        provisioner,
        "provision",
        lambda: {
            "action": "rotated",
            "user_id": "service-user",
            "key_id": REPLACEMENT_KEY_ID,
            "dedicated_env_synchronized": True,
            "cleanup_pending": True,
            "superseded_key_captured": True,
        },
    )
    provisioner.main([])
    output = capsys.readouterr().out
    assert "tw_svc_" not in output
    assert OLD_KEY not in output
    assert _test_hash(VALID_KEY) not in output


def test_abort_cli_is_explicit_and_pid_is_finalize_only(monkeypatch, capsys):
    monkeypatch.setattr(
        provisioner,
        "abort",
        lambda: {"legacy_preserved": True, "user_id": "u", "replacement_revoked": True},
    )
    provisioner.main(["--abort"])
    assert "reconciled" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="--pid is valid only"):
        provisioner.main(["--abort", "--pid", "2"])
