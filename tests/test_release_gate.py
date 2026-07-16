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


class _Response:
    def __init__(self, body, status=200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = headers or {"Content-Type": "application/json"}

    def json(self):
        return self._body


def test_mcp_oauth_gate_invokes_identity_and_downstream_data(monkeypatch):
    calls = []

    def fake_post(_url, **kwargs):
        payload = kwargs["json"]
        calls.append(payload)
        method = payload["method"]
        if method == "initialize":
            return _Response({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}},
                             headers={"Content-Type": "application/json", "Mcp-Session-Id": "s1"})
        if method == "tools/list":
            return _Response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [
                {"name": "whoami"}, {"name": "list_markets"}, {"name": "get_daily_pick"}
            ]}})
        return _Response({"jsonrpc": "2.0", "id": payload["id"], "result": {
            "content": [{"type": "text", "text": "ok"}], "isError": False
        }})

    monkeypatch.setattr(gate.requests, "post", fake_post)
    gate.require_mcp_auth("https://mcp.test/mcp", "oauth-token", "WorkOS OAuth", 5)

    tool_calls = [item["params"]["name"] for item in calls if item["method"] == "tools/call"]
    assert tool_calls == ["whoami", "list_markets", "get_daily_pick"]
    assert all(item.get("params", {}).get("arguments") == {} for item in calls
               if item["method"] == "tools/call")


def test_mcp_gate_rejects_data_tool_error(monkeypatch):
    responses = iter([
        _Response({"result": {"serverInfo": {}}}),
        _Response({"result": {"tools": [
            {"name": "whoami"}, {"name": "list_markets"}, {"name": "get_daily_pick"}
        ]}}),
        _Response({"result": {"content": [{"type": "text", "text": "ok"}]}}),
        _Response({"result": {"content": [{"type": "text", "text": "failed"}], "isError": True}}),
    ])
    monkeypatch.setattr(gate.requests, "post", lambda *_a, **_k: next(responses))
    with pytest.raises(RuntimeError, match="list_markets"):
        gate.require_mcp_auth("https://mcp.test/mcp", "oauth-token", "WorkOS OAuth", 5)


def test_health_gate_samples_multiple_connections(monkeypatch):
    calls = []

    def fake_get(*_args, **kwargs):
        calls.append(kwargs)
        return _Response({"storm_breaker_active": False})

    monkeypatch.setattr(gate.requests, "get", fake_get)
    gate.require_healthy("https://api.test/v1", 5, samples=4)
    assert len(calls) == 4
    assert all(call["headers"] == {"Connection": "close"} for call in calls)
