"""MCP server layer (mcpserver/server.py). Needs fastmcp, which lives in venv-api (not the
main pytest venv), so this module is SKIPPED under /home/flask/venv via importorskip and RUN
explicitly under venv-api:

    /home/flask/venv-api/bin/python -m pytest tests/test_mcpserver.py

Covers the thin-but-load-bearing MCP logic: the lean view=decision default, include=chart
plumbing, the disclaimer hoist/dedup, the research hand-off, and the upgrade-stub handling.
The gateway is mocked (server._get), so no network/appserver.
"""
import sys

import pytest

pytest.importorskip("mcp")              # skip cleanly when fastmcp is absent (the main venv)
sys.path.insert(0, "/home/flask/mcpserver")
import server                            # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def captured(monkeypatch):
    """Mock server._get and capture the (path, params) the tool sent to the gateway."""
    box = {}

    def fake_get(path, params=None):
        box["path"] = path
        box["params"] = dict(params or {})
        return {"count": 0, "opportunities": []}        # empty -> tools take the 'empty' lead path

    monkeypatch.setattr(server, "_get", fake_get)
    return box


# --- progressive disclosure: the MCP layer defaults to the lean 'decision' view -----

def test_find_best_defaults_to_decision_view(captured):
    server.find_best_opportunities(markets="2", ctx=None)
    assert captured["path"] == "/scan"
    assert captured["params"]["view"] == "decision"


def test_whats_seasonal_now_defaults_to_decision(captured):
    server.whats_seasonal_now(ctx=None)
    assert captured["params"]["view"] == "decision"
    assert captured["params"]["window"] == "now"


def test_view_override_is_forwarded(captured):
    server.find_best_opportunities(view="full", ctx=None)
    assert captured["params"]["view"] == "full"


def test_analyze_defaults_decision_and_include_chart(monkeypatch):
    box = {}
    monkeypatch.setattr(server, "_get", lambda path, params=None: box.update(
        path=path, params=dict(params or {})) or {"card": {"signal": "BUY"}})
    server.analyze_symbol(symbol="AAPL", include_chart=True, ctx=None)
    assert box["path"] == "/analyze/AAPL"
    assert box["params"]["view"] == "decision"
    assert box["params"]["include"] == "chart"


# --- disclaimer hoist / dedup (token-saving envelope handling) ----------------------

def test_extract_disclaimer_pops_every_copy_and_returns_one():
    payload = {"opportunities": [{"symbol": "A", "disclaimer": "D"},
                                 {"symbol": "B", "disclaimer": "D"}],
               "disclaimer": "D"}
    got = server._extract_disclaimer(payload)
    assert got == "D"
    # every nested copy is popped so the transport carries it once.
    assert "disclaimer" not in payload
    assert all("disclaimer" not in c for c in payload["opportunities"])


def test_lead_appends_handoff_and_hoists_disclaimer():
    out = server._lead("Found 1 setup:", {"opportunities": [{"symbol": "A", "disclaimer": "D"}]},
                       handoff=True)
    assert "Research hand-off:" in out                 # the _HANDOFF text
    assert out.count("Disclaimer: D") == 1             # exactly once, at the envelope
    assert '"disclaimer"' not in out                   # not repeated inside the JSON


def test_lead_without_handoff_omits_it():
    out = server._lead("Markets:", {"markets": []}, handoff=False)
    assert "Research hand-off:" not in out


# --- upgrade-stub handling (graceful, never an error) -------------------------------

def test_is_upgrade_stub():
    assert server._is_upgrade_stub({"requires": "pro"})
    assert server._is_upgrade_stub({"requires": "upgrade", "reason": "ml_daily_limit"})
    assert not server._is_upgrade_stub({"count": 0})


def test_format_upgrade_messages():
    pro = server._format_upgrade({"requires": "pro", "upgrade_url": "https://x/up"})
    assert "Upgrade required" in pro and "https://x/up" in pro
    ml = server._format_upgrade({"requires": "upgrade", "reason": "ml_daily_limit",
                                 "ml_remaining_today": 0})
    assert "Daily ML limit reached" in ml
