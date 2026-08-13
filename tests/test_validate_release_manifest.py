"""Release-manifest schema and cross-field enforcement."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "validate_release_manifest.py"
SPEC = importlib.util.spec_from_file_location("validate_release_manifest", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
SCHEMA = json.loads((ROOT / "ops" / "release_manifest.schema.json").read_text())
SHA = "8" * 40
DIGEST = "a" * 64
NOW = "2026-08-13T12:00:00Z"


def _gate(required=False, ran=False, passed=None, evidence=None):
    return {
        "required": required,
        "ran": ran,
        "passed": passed,
        "evidence": evidence or [],
    }


def _environment():
    return {
        "state": "not_started",
        "release_sha": None,
        "runtime_paths": [],
        "effective_units": [],
        "checks": {
            name: _gate()
            for name in (
                "runtime_identity",
                "service_routes",
                "contract_check",
                "browser_check",
            )
        },
        "snapshots": [],
    }


def _approval(state="pending"):
    return {"state": state}


def _rollback():
    return {
        "state": "not_prepared",
        "previous_backend_ref": None,
        "previous_frontend_ref": None,
        "commands": [],
        "evidence": [],
    }


def manifest():
    return {
        "schema_version": 3,
        "release_id": "tw2-20260813-01",
        "release_kind": "baseline-reconciliation",
        "manager": {"agent": "Codex", "identity": "Codex", "session": None, "state": "active"},
        "baseline": {
            "state": "pending",
            "marker_path": "/var/lib/tradewave/release-state/baseline.json",
            "release_sha": None,
            "completed_at": None,
            "evidence": [],
        },
        "dev_coordination": {
            "state": "not_started",
            "lock_path": "/var/lib/tradewave/release-state/dev-activation.lock",
            "lock_owner": None,
            "release_sha": None,
            "announced_at": None,
            "released_at": None,
            "evidence": [],
        },
        "requested_target": "staging",
        "status": "inventory",
        "created_at": NOW,
        "updated_at": NOW,
        "git": {
            "base_sha": SHA,
            "release_sha": None,
            "release_branch": "codex/release",
            "remote_main_sha": SHA,
            "main_locked_sha": None,
            "handoff_shas": [],
        },
        "artifacts": {"manifest_sha256": None, "frontend": [], "backend_fingerprint": None},
        "environments": {name: _environment() for name in ("dev", "staging", "prod")},
        "approvals": {
            name: _approval()
            for name in ("dev", "staging", "production_snapshots", "production")
        },
        "out_of_band_changes": [],
        "known_risks": [],
        "rollback": {name: _rollback() for name in ("dev", "staging", "prod")},
        "events": [{
            "at": NOW,
            "authored_by": "Codex",
            "executed_by": None,
            "execution_mode": "repository-write",
            "action": "create release",
            "result": "created",
            "evidence": ["request recorded"],
        }],
    }


def assert_valid(value):
    assert validator.validate_manifest(value, SCHEMA) == []


def assert_invalid(value, fragment):
    assert any(fragment in error for error in validator.validate_manifest(value, SCHEMA))


def test_inventory_is_valid():
    assert_valid(manifest())


def test_required_gate_must_run():
    value = manifest()
    value["environments"]["dev"]["checks"]["browser_check"]["required"] = True
    assert_invalid(value, "schema violation")


def _approved_release():
    value = manifest()
    value["git"]["release_sha"] = SHA
    value["artifacts"]["backend_fingerprint"] = "backend"
    value["artifacts"]["frontend"] = [
        {"path": "main.js", "sha256": DIGEST, "source_sha": SHA}
    ]
    value["artifacts"]["manifest_sha256"] = validator.composite_release_hash(value)
    value["approvals"]["dev"] = {
        "state": "approved",
        "approved_by": "Afshin",
        "approved_at": NOW,
        "release_sha": SHA,
        "artifact_sha256": value["artifacts"]["manifest_sha256"],
    }
    return value


def test_composite_hash_is_recomputed():
    value = _approved_release()
    assert_valid(value)
    value["artifacts"]["backend_fingerprint"] = "different"
    assert_invalid(value, "canonical release identity")


@pytest.mark.parametrize("surface", ["main_locked_sha", "approval", "environment", "frontend"])
def test_release_sha_identity_is_enforced(surface):
    value = _approved_release()
    other = "9" * 40
    if surface == "main_locked_sha":
        value["git"]["main_locked_sha"] = other
    elif surface == "approval":
        value["approvals"]["dev"]["release_sha"] = other
    elif surface == "environment":
        value["environments"]["dev"]["release_sha"] = other
    else:
        value["artifacts"]["frontend"][0]["source_sha"] = other
    assert_invalid(value, "release_sha")


def test_staging_approval_requires_verified_staging():
    value = _approved_release()
    value["approvals"]["staging"] = deepcopy(value["approvals"]["dev"])
    assert_invalid(value, "verified staging")


def test_production_approval_requires_snapshots():
    value = _approved_release()
    value["approvals"]["staging"] = deepcopy(value["approvals"]["dev"])
    value["environments"]["staging"]["state"] = "verified"
    value["environments"]["staging"]["release_sha"] = SHA
    value["environments"]["staging"]["runtime_paths"] = ["/release"]
    value["environments"]["staging"]["effective_units"] = ["tradewave-web"]
    for gate in value["environments"]["staging"]["checks"].values():
        gate.update(required=True, ran=True, passed=True, evidence=["pass"])
    value["approvals"]["production"] = deepcopy(value["approvals"]["dev"])
    assert_invalid(value, "production snapshots")


def test_prod_deployed_requires_production_approval():
    value = _approved_release()
    value["status"] = "prod_deployed"
    value["git"]["main_locked_sha"] = SHA
    value["git"]["remote_main_sha"] = SHA
    assert_invalid(value, "production approval")


def test_awaiting_prod_approval_requires_verified_staging():
    value = _approved_release()
    value["status"] = "awaiting_prod_approval"
    value["git"]["main_locked_sha"] = SHA
    value["git"]["remote_main_sha"] = SHA
    assert_invalid(value, "verified staging")


def test_complete_dev_release_does_not_require_main_lock():
    value = _approved_release()
    value["requested_target"] = "dev"
    value["status"] = "complete"
    value["baseline"].update(
        state="complete", release_sha=SHA, completed_at=NOW, evidence=["baseline"]
    )
    value["dev_coordination"].update(
        state="locked",
        lock_owner="Codex",
        release_sha=SHA,
        announced_at=NOW,
        evidence=["lock"],
    )
    value["environments"]["dev"]["state"] = "verified"
    value["environments"]["dev"]["release_sha"] = SHA
    value["environments"]["dev"]["runtime_paths"] = ["/release"]
    value["environments"]["dev"]["effective_units"] = ["tradewave-web"]
    for gate in value["environments"]["dev"]["checks"].values():
        gate.update(required=True, ran=True, passed=True, evidence=["pass"])
    assert_valid(value)


def test_manager_live_write_requires_executor():
    value = manifest()
    value["events"].append({
        "at": NOW,
        "authored_by": "Codex",
        "executed_by": None,
        "execution_mode": "manager-live-write",
        "action": "deploy staging",
        "result": "started",
        "evidence": [],
    })
    assert_invalid(value, "schema violation")
