"""Pure contracts for the read-only release-gate helper."""

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "verify_mvp_release.py"
SPEC = importlib.util.spec_from_file_location("verify_mvp_release", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def test_percentile_is_deterministic():
    assert gate.percentile([5, 1, 4, 2, 3], 0.95) == 4


def test_success_message_claims_only_executed_auth_gates():
    skipped = gate.success_message(oauth_verified=False)
    verified = gate.success_message(oauth_verified=True)
    assert "MCP BYOK" in skipped
    assert "OAuth" not in skipped
    assert "OAuth" in verified


def test_load_gate_rejects_error_budget(monkeypatch):
    samples = iter([
        gate.Sample(0.1, 200, True),
        gate.Sample(0.1, 503, False),
    ])
    monkeypatch.setattr(gate, "one_sample", lambda *_: next(samples))
    with pytest.raises(RuntimeError, match="error rate"):
        gate.load_gate("https://example.test", "secret", 1, 2, 1, 1, 0.01)


def test_load_gate_rejects_p95(monkeypatch):
    monkeypatch.setattr(
        gate, "one_sample", lambda *_: gate.Sample(2.0, 200, True)
    )
    with pytest.raises(RuntimeError, match="p95"):
        gate.load_gate("https://example.test", "secret", 1, 2, 1, 1, 0.01)
