"""MCP server layer (mcpserver/server.py). Needs fastmcp, which lives in venv-api (not the
main pytest venv), so this module is SKIPPED under /home/flask/venv via importorskip and RUN
explicitly under venv-api:

    /home/flask/venv-api/bin/python -m pytest tests/test_mcpserver.py

Covers the thin-but-load-bearing MCP logic: the evidence-first default, include=chart
plumbing, the disclaimer hoist/dedup, the research hand-off, and the upgrade-stub handling.
The gateway is mocked (server._get), so no network/appserver.
"""
import asyncio
import inspect
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")              # skip cleanly when fastmcp is absent (the main venv)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcpserver"))
import server                            # noqa: E402

pytestmark = pytest.mark.unit


def test_all_public_tools_have_async_boundaries():
    tool_names = (
        "find_best_opportunities", "analyze_symbol", "explain_pick", "morning_briefing",
        "whats_seasonal_now", "compare_opportunities", "list_markets", "whoami",
        "describe_tradewave", "list_symbols", "get_seasonal_opportunities",
        "get_symbol_patterns", "get_seasonal_pattern", "get_opportunity_chart",
        "score_opportunities", "get_daily_pick", "get_pick_track_record",
    )
    assert all(inspect.iscoroutinefunction(getattr(server, name)) for name in tool_names)


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def captured(monkeypatch):
    """Mock server._get and capture the (path, params) the tool sent to the gateway."""
    box = {}

    async def fake_get(path, params=None):
        box["path"] = path
        box["params"] = dict(params or {})
        return {"count": 0, "opportunities": []}        # empty -> tools take the 'empty' lead path

    monkeypatch.setattr(server, "_get", fake_get)
    return box


# --- progressive disclosure: the MCP layer defaults to the lean 'decision' view -----

def test_find_best_defaults_to_evidence_view_and_chart(captured):
    _run(server.find_best_opportunities(markets="2", ctx=None))
    assert captured["path"] == "/scan"
    assert captured["params"]["view"] == "evidence"
    assert captured["params"]["include"] == "chart"


def test_whats_seasonal_now_defaults_to_decision(captured):
    _run(server.whats_seasonal_now(ctx=None))
    assert captured["params"]["view"] == "decision"
    assert captured["params"]["window"] == "now"


def test_whats_seasonal_now_mixed_content_survives_fastmcp_serialization(monkeypatch):
    """Regression: a string return schema rejected text + ResourceLink in production."""
    async def fake_get(path, params=None):
        return {
            "count": 1,
            "opportunities": [{
                "symbol": "ALL",
                "wave_viewer": {
                    "label": "Open exact ALL pattern",
                    "url": "https://tradewave.example/app/?o=all",
                },
            }],
        }

    monkeypatch.setattr(server, "_get", fake_get)

    out = _run(server.mcp.call_tool("whats_seasonal_now", {}))

    assert out[0].type == "text"
    assert "1 seasonal setup(s)" in out[0].text
    assert out[1].type == "resource_link"
    assert str(out[1].uri) == "https://tradewave.example/app/?o=all"

    tool = next(
        tool for tool in _run(server.mcp.list_tools())
        if tool.name == "whats_seasonal_now"
    )
    assert tool.outputSchema is None


def test_remote_mcp_transport_is_stateless_across_workers_and_restarts():
    assert server.mcp.settings.stateless_http is True


def test_view_override_is_forwarded(captured):
    _run(server.find_best_opportunities(view="full", ctx=None))
    assert captured["params"]["view"] == "full"


def test_analyze_defaults_evidence_and_include_chart(monkeypatch):
    box = {}
    async def fake_get(path, params=None):
        box.update(path=path, params=dict(params or {}))
        return {"card": {"bias": "bullish"}}
    monkeypatch.setattr(server, "_get", fake_get)
    _run(server.analyze_symbol(symbol="AAPL", include_chart=True, ctx=None))
    assert box["path"] == "/analyze/AAPL"
    assert box["params"]["view"] == "evidence"
    assert box["params"]["include"] == "chart"


def test_analyze_chart_is_mandatory_even_for_legacy_false(monkeypatch):
    box = {}
    async def fake_get(path, params=None):
        box.update(path=path, params=dict(params or {}))
        return {"card": {"bias": "bullish"}}
    monkeypatch.setattr(server, "_get", fake_get)
    _run(server.analyze_symbol(symbol="AAPL", include_chart=False, ctx=None))
    assert box["params"]["include"] == "chart"


def test_scan_carries_focused_followup_contract(monkeypatch):
    async def fake_get(path, params=None):
        return {"count": 1, "opportunities": [{"symbol": "TJX"}]}
    monkeypatch.setattr(server, "_get", fake_get)

    out = _run(server.find_best_opportunities(ctx=None))

    assert isinstance(out, server.CallToolResult)
    rule = out.structuredContent["focused_followup"]
    assert rule["required_tool"] == "analyze_symbol"
    assert "never require the user to ask for a chart" in rule["instruction"]


def test_analyze_returns_mcp_app_result_with_structured_evidence(monkeypatch):
    url = "https://tradewave.example/app/?o=all&view=evidence"
    async def fake_get(path, params=None):
        return {"card": {
            "symbol": "ALL",
            "bias": "bullish",
            "setup": {"entry_date": "2026-07-19", "exit_date": "2026-09-12",
                      "hold_days": 55},
            "stats": {"historical_win_rate": .9, "years": "10"},
            "chart": {
                "trend_chart": [{"date": "2026-07-19", "index": 100}],
                "per_year_bars": [{"year": "2025", "mae_pct": -1, "mfe_pct": 5,
                                    "net_pct": 4}],
            },
            "wave_viewer": {"label": "Open exact ALL pattern", "url": url},
        }}
    monkeypatch.setattr(server, "_get", fake_get)

    out = _run(server.analyze_symbol(symbol="ALL", market="2", ctx=None))

    assert isinstance(out, server.CallToolResult)
    assert out.structuredContent["card"]["chart"]["per_year_bars"][0]["year"] == "2025"
    assert out.structuredContent["primary_action"]["url"] == url
    assert url in out.content[0].text
    assert out.content[1].type == "resource_link"


def test_analyze_tool_and_resource_advertise_mcp_app_contract():
    tools = _run(server.mcp.list_tools())
    analyze = next(tool for tool in tools if tool.name == "analyze_symbol")
    scan = next(tool for tool in tools if tool.name == "find_best_opportunities")
    assert analyze.meta["ui"]["resourceUri"] == server.PATTERN_WIDGET_URI
    assert analyze.meta["openai/outputTemplate"] == server.PATTERN_WIDGET_URI
    assert analyze.annotations.readOnlyHint is True
    assert analyze.outputSchema["type"] == "object"
    assert scan.meta["ui"]["resourceUri"] == server.PATTERN_WIDGET_URI
    assert scan.annotations.readOnlyHint is True
    assert scan.outputSchema["type"] == "object"

    resources = _run(server.mcp.list_resources())
    widget = next(resource for resource in resources if str(resource.uri) == server.PATTERN_WIDGET_URI)
    assert widget.mimeType == "text/html;profile=mcp-app"
    assert widget.meta["ui"]["prefersBorder"] is True
    assert "domain" not in widget.meta["ui"]
    assert widget.meta["openai/widgetCSP"]["redirect_domains"] == [server.MAIN_PUBLIC_URL]
    assert "mcp-dev.trxstat.com" not in repr(widget.meta)
    assert server.PATTERN_WIDGET_URI.endswith("pattern-evidence-v3.html")
    assert 'request("ui/initialize"' in server.PATTERN_WIDGET_HTML
    assert 'notify("ui/notifications/initialized")' in server.PATTERN_WIDGET_HTML
    assert 'notify("ui/notifications/size-changed"' in server.PATTERN_WIDGET_HTML
    assert "ui/notifications/tool-result" in server.PATTERN_WIDGET_HTML
    assert "All ${opportunities.length} ranked patterns" in server.PATTERN_WIDGET_HTML
    assert "rankedShortlist(data?.opportunities" in server.PATTERN_WIDGET_HTML


def test_widget_result_has_ranked_text_fallback_for_non_rendering_hosts(monkeypatch):
    async def fake_get(path, params=None):
        return {
            "count": 2,
            "opportunities": [
                {
                    "rank": 1,
                    "symbol": "TJX",
                    "direction": "long",
                    "setup": {
                        "entry_date": "2026-07-19",
                        "exit_date": "2026-09-16",
                        "hold_days": 59,
                    },
                    "stats": {
                        "historical_win_rate": .95,
                        "years": "20",
                        "avg_return_pct": 6.0,
                        "median_return_pct": 5.36,
                        "sharpe_ratio": 1.8,
                    },
                    "ml": {"ml_win_prob": .865},
                    "chart": {
                        "per_year_bars": [
                            {"year": "2025", "mae_pct": -1, "mfe_pct": 12,
                             "net_pct": 10}
                        ]
                    },
                },
                {"rank": 2, "symbol": "ALL", "direction": "long"},
            ],
        }

    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.find_best_opportunities(ctx=None))
    text = out.content[0].text

    assert "Required ranked shortlist: present EVERY returned row" in text
    assert "show all 2 returned patterns in a ranked table" in text
    assert "1. TJX LONG" in text
    assert "win rate 95% over 20 years" in text
    assert "ML win probability 86.50%" in text
    assert "2. ALL LONG" in text
    assert "2025: final +10.00% (path -1.00% to +12.00%)" in text
    contract = out.structuredContent["ranked_list_presentation"]
    assert contract["required"] is True
    assert contract["result_count"] == 2
    assert "Present every returned opportunity" in contract["instruction"]


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


def test_rich_lead_returns_native_image_blocks(monkeypatch):
    monkeypatch.setattr(
        server,
        "render_card_charts",
        lambda card: [("TradeWave evidence", b"\x89PNG\r\n\x1a\nsynthetic")],
    )
    data = {"card": {
        "symbol": "AAPL",
        "chart": {"trend_chart": [{"index": 1}]},
        "wave_viewer": {
            "label": "Open exact AAPL pattern",
            "url": "https://tradewave.example/app/?o=abc&view=evidence",
        },
    }}
    out = server._rich_lead("Evidence:", data)
    assert isinstance(out, list)
    assert "[Open exact AAPL pattern](https://tradewave.example/app/?o=abc&view=evidence)" in out[0]
    assert '"primary_action"' in out[0]
    assert out[1].type == "resource_link"
    assert str(out[1].uri) == "https://tradewave.example/app/?o=abc&view=evidence"
    assert out[2] == "TradeWave evidence"
    assert out[3].to_image_content().mimeType == "image/png"


def test_rich_lead_returns_clickable_resource_even_without_chart():
    data = {"card": {
        "symbol": "ALL",
        "wave_viewer": {
            "label": "Open exact ALL pattern",
            "url": "https://tradewave.example/app/?o=all&view=evidence",
        },
    }}
    out = server._rich_lead("Evidence:", data)
    assert isinstance(out, list) and len(out) == 2
    assert out[1].type == "resource_link"


# --- upgrade-stub handling (graceful, never an error) -------------------------------

def test_is_upgrade_stub():
    # The gateway's ONLY upgrade stub is the ML daily-limit one (requires="upgrade",
    # reason="ml_daily_limit"). There is no requires="pro" shape - ML is metered on every
    # tier, not Pro-gated - so that must NOT be treated as a stub.
    assert server._is_upgrade_stub({"requires": "upgrade", "reason": "ml_daily_limit"})
    assert not server._is_upgrade_stub({"requires": "pro"})
    assert not server._is_upgrade_stub({"count": 0})


def test_format_upgrade_messages():
    ml = server._format_upgrade({"requires": "upgrade", "reason": "ml_daily_limit",
                                 "ml_remaining_today": 0})
    assert "Daily ML limit reached" in ml


# --- error wrapper: gateway failures become friendly tool RESULTS, never httpx leaks ---

import httpx  # noqa: E402


def _status_error(status, body=None, text=None):
    req = httpx.Request("GET", "http://127.0.0.1:8088/v1/x")
    if body is not None:
        resp = httpx.Response(status, json=body, request=req)
    else:
        resp = httpx.Response(status, text=text or "", request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


def test_friendly_http_error_uses_gateway_message():
    exc = _status_error(404, {"error": {"code": "not_found",
                                        "message": "symbol 'GLD' not found in any of your in-scope markets"}})
    msg = server._friendly_http_error(exc)
    assert "GLD" in msg and "127.0.0.1" not in msg


def test_friendly_http_error_rate_limited_adds_retry_hint():
    exc = _status_error(429, {"error": {"code": "rate_limited", "message": "rate limit exceeded"}})
    msg = server._friendly_http_error(exc)
    assert msg.startswith("rate limit exceeded") and "retry" in msg


def test_friendly_http_error_non_json_is_generic():
    exc = _status_error(502, text="<html>Bad Gateway</html>")
    msg = server._friendly_http_error(exc)
    assert "HTTP 502" in msg and "127.0.0.1" not in msg and "<html>" not in msg


def test_tool_returns_gateway_error_as_result(monkeypatch):
    async def boom(path, params=None):
        raise server.GatewayError("symbol 'GLD' not found in any of your in-scope markets")
    monkeypatch.setattr(server, "_get", boom)
    out = _run(server.analyze_symbol(symbol="GLD", ctx=None))
    assert isinstance(out, server.CallToolResult)
    assert out.isError is True
    assert out.structuredContent["error"]["message"] == (
        "symbol 'GLD' not found in any of your in-scope markets"
    )


def test_compare_degrades_row_with_gateway_message(monkeypatch):
    async def boom(path, params=None):
        raise server.GatewayError("rate limit exceeded - wait a few seconds and retry; results are cached.")
    monkeypatch.setattr(server, "_get", boom)
    out = _run(server.compare_opportunities(symbols=["GLD", "SLV"], ctx=None))
    assert "rate limit exceeded" in out and "127.0.0.1" not in out


def test_gateway_timeout_raised_to_110s():
    # The 30s timeout starved large cold scans mid-compute (prod 429 forensics).
    assert server._GATEWAY_TIMEOUT == 110


# --- markets accepts list[str] | str (models naturally send lists) -------------------

def test_markets_list_is_csv_joined(captured):
    _run(server.find_best_opportunities(markets=["2", "11"], ctx=None))
    assert captured["params"]["markets"] == "2,11"
    _run(server.whats_seasonal_now(markets=["0"], ctx=None))
    assert captured["params"]["markets"] == "0"


def test_markets_csv_string_passes_through(captured):
    _run(server.find_best_opportunities(markets="2,11", ctx=None))
    assert captured["params"]["markets"] == "2,11"


# --- whoami: tier-aware analyze example (free scope must not get an erroring example) -

def _me_payload(market_ids):
    return {"tier": "free", "tier_name": "Free", "ml_remaining_today": 5,
            "markets_in_scope": [{"id": m, "name": f"M{m}", "ml_eligible": True}
                                 for m in market_ids]}


def test_whoami_example_matches_free_scope(monkeypatch):
    async def fake_get(path, params=None):
        return _me_payload(["2"])
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.whoami(ctx=None))
    assert "Analyze AAPL's seasonality" in out
    assert "Analyze GLD" not in out


def test_whoami_example_prefers_etfs_when_in_scope(monkeypatch):
    async def fake_get(path, params=None):
        return _me_payload(["2", "11"])
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.whoami(ctx=None))
    assert "Analyze GLD's seasonality" in out


# --- teaser_state: the structural in-chat disclosure rides /me into whoami ------------

def _me_with_teaser(teaser_state):
    """A minimal /me payload carrying a teaser_state contract (what the gateway emits)."""
    p = _me_payload(["2"])
    p["teaser_state"] = teaser_state
    return p


def test_whoami_steady_payer_no_teaser_disclosure(monkeypatch):
    # A steady payer's /me carries the inactive teaser contract; whoami must NOT add the
    # teaser disclosure sentence.
    inactive = {"active": False, "kind": None, "ends_at": None, "post_teaser_scope": None}
    async def fake_get(path, params=None):
        return _me_with_teaser(inactive)
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.whoami(ctx=None))
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"] == inactive          # shape rides through verbatim
    assert "In-chat teaser active" not in out


def test_whoami_explorer_trial_teaser_disclosed(monkeypatch):
    ts = {"active": True, "kind": "explorer_trial",
          "ends_at": "2026-07-05T00:00:00+00:00", "post_teaser_scope": "explorer"}
    async def fake_get(path, params=None):
        return _me_with_teaser(ts)
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.whoami(ctx=None))
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"]["kind"] == "explorer_trial"
    assert body["teaser_state"]["post_teaser_scope"] == "explorer"
    assert "In-chat teaser active until 2026-07-05T00:00:00+00:00" in out
    assert "reverts to explorer scope after" in out


def test_whoami_navigator_firstconnect_teaser_disclosed(monkeypatch):
    ts = {"active": True, "kind": "navigator_firstconnect",
          "ends_at": "2026-07-05T00:00:00+00:00", "post_teaser_scope": "navigator"}
    async def fake_get(path, params=None):
        return _me_with_teaser(ts)
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.whoami(ctx=None))
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"]["kind"] == "navigator_firstconnect"
    assert "reverts to navigator scope after" in out


# --- morning_briefing: one-call composition ------------------------------------------

def test_morning_briefing_composes_three_sections(monkeypatch):
    async def fake_get(path, params=None):
        if path == "/daily-pick":
            return {"card": {"symbol": "AAPL", "bias": "bullish", "disclaimer": "D"},
                    "as_of": "2026-06-12", "disclaimer": "D"}
        if path == "/daily-pick/track-record":
            return {"summary": {"count": 40, "win_count": 28, "win_rate": 0.7,
                                "avg_return_pct": 2.1},
                    "picks": [{"symbol": f"S{i}", "result": "loss" if i % 3 else "win",
                               "return_pct": -1.0 if i % 3 else 2.0} for i in range(8)],
                    "disclaimer": "D"}
        if path == "/scan":
            assert params["window"] == "now" and params["view"] == "table"
            return {"count": 7, "opportunities": [
                {"symbol": s, "rank": i} for i, s in
                enumerate(["AAPL", "AAPL", "MSFT", "NVDA", "KO", "XOM", "JPM"])]}
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.morning_briefing(ctx=None))
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["todays_pick"]["symbol"] == "AAPL"
    assert body["track_record_summary"]["count"] == 40
    assert len(body["track_record_summary"]["last_5"]) == 5      # losses included
    assert any(p["result"] == "loss" for p in body["track_record_summary"]["last_5"])
    syms = [r["symbol"] for r in body["this_week"]]
    assert len(syms) == 5 and len(set(syms)) == 5                # top 5 DISTINCT symbols
    assert body["as_of"] == "2026-06-12"
    assert out.count("Disclaimer: D") == 1                       # hoisted once


def test_morning_briefing_degrades_per_section(monkeypatch):
    async def fake_get(path, params=None):
        if path == "/scan":
            raise server.GatewayError("rate limit exceeded")
        if path == "/daily-pick":
            return {"card": {"symbol": "AAPL"}, "as_of": "2026-06-12"}
        return {"summary": {"count": 1}, "picks": []}
    monkeypatch.setattr(server, "_get", fake_get)
    out = _run(server.morning_briefing(ctx=None))
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["this_week"] == {"unavailable": "rate limit exceeded"}
    assert body["todays_pick"]["symbol"] == "AAPL"
