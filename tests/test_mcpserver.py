"""MCP server layer (mcpserver/server.py). Needs fastmcp, which lives in venv-api (not the
main pytest venv), so this module is SKIPPED under /home/flask/venv via importorskip and RUN
explicitly under venv-api:

    /home/flask/venv-api/bin/python -m pytest tests/test_mcpserver.py

Covers the thin-but-load-bearing MCP logic: presentation contracts, async tool execution,
per-call auth isolation, bounded aggregate fanout, async JWKS refresh behavior, published
schemas, and tool safety annotations. Gateway behavior uses either a mocked helper or an
in-process async httpx transport, so no external network/appserver is required.
"""
import asyncio
import base64
import gzip
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")              # skip cleanly when fastmcp is absent (the main venv)
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "mcpserver"))
import server                            # noqa: E402

assert Path(server.__file__).resolve() == (_REPO_ROOT / "mcpserver" / "server.py").resolve()

pytestmark = pytest.mark.unit

_TEST_MCP_ADMISSION_ID = "acct_" + "a" * 64
_OTHER_MCP_ADMISSION_ID = "acct_" + "b" * 64


def _admission_payload(admission_id=_TEST_MCP_ADMISSION_ID):
    return {"tier": "demo", "mcp_admission_id": admission_id}


@pytest.fixture
def anyio_backend():
    """The API venv includes anyio's pytest plugin; keep these tests on asyncio."""
    return "asyncio"


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

@pytest.mark.anyio
async def test_find_best_defaults_to_decision_view(captured):
    await server.find_best_opportunities(markets="2", ctx=None)
    assert captured["path"] == "/scan"
    assert captured["params"]["view"] == "decision"
    assert captured["params"]["limit"] == server._MCP_SCAN_DEFAULT_LIMIT == 10


@pytest.mark.anyio
async def test_whats_seasonal_now_defaults_to_decision(captured):
    await server.whats_seasonal_now(ctx=None)
    assert captured["params"]["view"] == "decision"
    assert captured["params"]["window"] == "now"


@pytest.mark.anyio
async def test_view_override_is_forwarded(captured):
    await server.find_best_opportunities(view="full", ctx=None)
    assert captured["params"]["view"] == "full"
    assert captured["params"]["limit"] == 10


@pytest.mark.anyio
async def test_mcp_result_limits_are_enforced_before_gateway(monkeypatch):
    calls = []

    async def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        return {"count": 0, "opportunities": []}

    monkeypatch.setattr(server, "_get", fake_get)

    await server.find_best_opportunities(limit=100, view="table", ctx=None)
    assert calls[-1][1]["limit"] == 100
    await server.find_best_opportunities(limit=25, view="full", ctx=None)
    assert calls[-1][1]["limit"] == 25
    await server.get_seasonal_opportunities(market="2", limit=100, ctx=None)
    assert calls[-1][1]["limit"] == 100

    call_count = len(calls)
    full_over_cap = await server.find_best_opportunities(
        limit=26, view="full", ctx=None
    )
    compact_over_cap = await server.find_best_opportunities(limit=101, ctx=None)
    primitive_over_cap = await server.get_seasonal_opportunities(
        market="2", limit=101, ctx=None
    )
    assert "between 1 and 25 for view='full'" in full_over_cap
    assert "between 1 and 100" in compact_over_cap
    assert "between 1 and 100" in primitive_over_cap
    assert len(calls) == call_count


@pytest.mark.anyio
async def test_raw_opportunity_default_is_bounded(captured):
    await server.get_seasonal_opportunities(market="2", ctx=None)
    assert captured["path"] == "/opportunities"
    assert captured["params"]["limit"] == server._MCP_OPPORTUNITIES_DEFAULT_LIMIT == 25


@pytest.mark.anyio
async def test_analyze_defaults_decision_and_include_chart(monkeypatch):
    box = {}
    async def fake_get(path, params=None):
        box.update(path=path, params=dict(params or {}))
        return {"card": {"bias": "bullish"}}
    monkeypatch.setattr(server, "_get", fake_get)
    await server.analyze_symbol(symbol="AAPL", include_chart=True, ctx=None)
    assert box["path"] == "/analyze/AAPL"
    assert box["params"]["view"] == "decision"
    assert box["params"]["include"] == "chart"


@pytest.mark.anyio
async def test_score_forwards_one_market_at_batch_level(monkeypatch):
    box = {}

    async def fake_post(path, body):
        box.update(path=path, body=body)
        return {"scores": [], "granted": 0, "ml_remaining_today": None}

    monkeypatch.setattr(server, "_post", fake_post)
    item = {"symbol": "GLD", "date": "2026-07-15", "days_out": 30,
            "direction": "long"}
    await server.score_opportunities([item], market="11", ctx=None)

    assert box["path"] == "/score"
    assert box["body"] == {"market": "11", "opportunities": [item]}
    assert "market" not in box["body"]["opportunities"][0]


@pytest.mark.anyio
async def test_list_symbols_pages_safely_by_default_and_forwards_filters(monkeypatch):
    calls = []

    async def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        return {"symbols": [], "count": 0, "matched": 0, "total": 0}

    monkeypatch.setattr(server, "_get", fake_get)
    await server.list_symbols(market="2", ctx=None)
    await server.list_symbols(market="2", prefix="AA", limit=25, ctx=None)

    assert calls == [
        ("/markets/2/symbols", {"limit": 100}),
        ("/markets/2/symbols", {"limit": 25, "prefix": "AA"}),
    ]


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
import jwt as pyjwt  # noqa: E402


class _AsyncChunks(httpx.AsyncByteStream):
    """Small controllable network-like response stream for allocation-bound tests."""

    def __init__(self, *chunks, pause_after_first=0.0):
        self.chunks = chunks
        self.pause_after_first = pause_after_first
        self.iterated = False
        self.closed = False

    async def __aiter__(self):
        self.iterated = True
        for index, chunk in enumerate(self.chunks):
            yield chunk
            if index == 0 and self.pause_after_first:
                await asyncio.sleep(self.pause_after_first)

    async def aclose(self):
        self.closed = True


class _TricklingChunks(httpx.AsyncByteStream):
    """Never-idle peer used to prove the wall-clock deadline, not read timeout."""

    def __init__(self, interval=0.005):
        self.interval = interval
        self.iterated = False
        self.closed = False

    async def __aiter__(self):
        self.iterated = True
        while True:
            await asyncio.sleep(self.interval)
            yield b" "

    async def aclose(self):
        self.closed = True


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


def test_friendly_http_error_rejects_unbounded_gateway_message():
    attacker_text = "x" * (server._GATEWAY_ERROR_MESSAGE_MAX_CHARS + 1)
    exc = _status_error(400, {"error": {"code": "invalid", "message": attacker_text}})
    msg = server._friendly_http_error(exc)
    assert msg == (
        "The TradeWave gateway returned an error (HTTP 400). Try again in a moment."
    )
    assert attacker_text not in msg


@pytest.mark.anyio
async def test_tool_returns_gateway_error_as_result(monkeypatch):
    async def boom(path, params=None):
        raise server.GatewayError("symbol 'GLD' not found in any of your in-scope markets")
    monkeypatch.setattr(server, "_get", boom)
    out = await server.analyze_symbol(symbol="GLD", ctx=None)
    assert out == "symbol 'GLD' not found in any of your in-scope markets"


@pytest.mark.anyio
async def test_tool_wrapper_restores_principal_context_after_each_call(monkeypatch):
    outer = {"mode": "byok", "key": "outer-task-key"}
    reset_token = server._request_principal.set(outer)
    observed = None

    async def fake_get(_path, _params=None):
        nonlocal observed
        observed = server._request_principal.get()
        return {"card": {"bias": "bullish"}}

    monkeypatch.setattr(server, "OAUTH_ENABLED", False)
    monkeypatch.setattr(server, "TRADEWAVE_API_KEY", "inner-stdio-key")
    monkeypatch.setattr(server, "_get", fake_get)
    try:
        await server.analyze_symbol(symbol="GLD", ctx=None)
        assert observed == {"mode": "byok", "key": "inner-stdio-key"}
        assert server._request_principal.get() is outer
    finally:
        server._request_principal.reset(reset_token)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"<html>temporary proxy page</html>", "text/html"),
        (b'{"opportunities":[', "application/json"),
    ],
)
async def test_invalid_success_body_becomes_safe_gateway_error(
    monkeypatch, content, content_type
):
    async def handler(request):
        return httpx.Response(
            200,
            content=content,
            headers={"content-type": content_type},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", None)
    try:
        with pytest.raises(server.GatewayError) as raised:
            await server._get("/malformed")
    finally:
        await client.aclose()

    assert raised.value.message == server._INVALID_GATEWAY_RESULT
    assert "html" not in raised.value.message.lower()
    assert "json" not in raised.value.message.lower()


@pytest.mark.anyio
async def test_identity_gateway_response_bytes_are_bounded_before_json_parse(monkeypatch):
    oversized = b" " * (server._GATEWAY_RESPONSE_MAX_BYTES + 1)

    async def handler(request):
        return httpx.Response(
            200,
            content=oversized,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", None)
    try:
        with pytest.raises(server.GatewayError) as raised:
            await server._get("/oversized")
    finally:
        await client.aclose()

    assert raised.value.message == server._OVERSIZED_GATEWAY_RESULT
    assert "127.0.0.1" not in raised.value.message


@pytest.mark.anyio
async def test_gateway_requests_identity_and_rejects_encoded_body_before_read(monkeypatch):
    observed_accept_encoding = None
    compressed = gzip.compress(b"x" * (server._GATEWAY_RESPONSE_MAX_BYTES + 1))
    stream = _AsyncChunks(compressed)

    async def handler(request):
        nonlocal observed_accept_encoding
        observed_accept_encoding = request.headers.get("accept-encoding")
        return httpx.Response(
            200,
            stream=stream,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", None)
    try:
        with pytest.raises(server.GatewayError) as raised:
            await server._get("/encoded")
    finally:
        await client.aclose()

    assert observed_accept_encoding == "identity"
    assert raised.value.message == server._INVALID_GATEWAY_RESULT
    assert not stream.iterated
    assert stream.closed


@pytest.mark.anyio
async def test_trickling_research_response_hits_absolute_deadline_and_closes(monkeypatch):
    stream = _TricklingChunks()

    async def handler(request):
        return httpx.Response(
            200,
            stream=stream,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", None)
    monkeypatch.setattr(server, "_GATEWAY_RESPONSE_DEADLINE", 0.03)
    try:
        with pytest.raises(server.GatewayError) as raised:
            await asyncio.wait_for(server._get("/trickle"), timeout=1.0)
    finally:
        await client.aclose()

    assert raised.value.message == server._TIMEOUT_RESULT
    assert stream.iterated and stream.closed


@pytest.mark.anyio
async def test_trickling_auth_response_hits_short_absolute_deadline(monkeypatch):
    stream = _TricklingChunks()

    async def handler(request):
        return httpx.Response(
            200,
            stream=stream,
            headers={"content-type": "application/json"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    key = "tw_live_" + "e" * 32
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    server._byok_cache.clear()
    monkeypatch.setattr(server, "_auth_client", client)
    monkeypatch.setattr(server, "_auth_gate", None)
    monkeypatch.setattr(server, "_AUTH_RESPONSE_DEADLINE", 0.03)
    try:
        admitted = await asyncio.wait_for(
            server._validate_byok_key(key, key_hash), timeout=1.0
        )
    finally:
        await client.aclose()
        server._byok_cache.clear()

    assert admitted is None
    assert stream.iterated and stream.closed


@pytest.mark.anyio
async def test_saturated_research_pool_fails_fast_without_outbound_call(monkeypatch):
    outbound_calls = 0

    async def handler(request):
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(200, json={}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", asyncio.Semaphore(0))
    monkeypatch.setattr(server, "_GATEWAY_ADMISSION_WAIT_TIMEOUT", 0.01)
    try:
        with pytest.raises(server.GatewayError) as raised:
            await asyncio.wait_for(server._get("/busy"), timeout=1.0)
    finally:
        await client.aclose()

    assert raised.value.message == server._GATEWAY_BUSY_RESULT
    assert outbound_calls == 0


@pytest.mark.anyio
async def test_compare_degrades_row_with_gateway_message(monkeypatch):
    async def boom(path, params=None):
        raise server.GatewayError("rate limit exceeded - wait a few seconds and retry; results are cached.")
    monkeypatch.setattr(server, "_get", boom)
    out = await server.compare_opportunities(symbols=["GLD", "SLV"], ctx=None)
    assert "rate limit exceeded" in out and "127.0.0.1" not in out


def test_gateway_timeout_raised_to_110s():
    # The 30s timeout starved large cold scans mid-compute (prod 429 forensics).
    assert server._GATEWAY_TIMEOUT == 110


# --- markets accepts list[str] | str (models naturally send lists) -------------------

@pytest.mark.anyio
async def test_markets_list_is_csv_joined(captured):
    await server.find_best_opportunities(markets=["2", "11"], ctx=None)
    assert captured["params"]["markets"] == "2,11"
    await server.whats_seasonal_now(markets=["0"], ctx=None)
    assert captured["params"]["markets"] == "0"


@pytest.mark.anyio
async def test_markets_csv_string_passes_through(captured):
    await server.find_best_opportunities(markets="2,11", ctx=None)
    assert captured["params"]["markets"] == "2,11"


# --- whoami: tier-aware analyze example (free scope must not get an erroring example) -

def _me_payload(market_ids):
    return {"tier": "free", "tier_name": "Free", "ml_remaining_today": 5,
            "markets_in_scope": [{"id": m, "name": f"M{m}", "ml_eligible": True}
                                 for m in market_ids]}


@pytest.mark.anyio
async def test_whoami_example_matches_free_scope(monkeypatch):
    async def fake_get(path, params=None):
        return {
            **_me_payload(["2"]),
            "mcp_admission_id": _TEST_MCP_ADMISSION_ID,
        }
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.whoami(ctx=None)
    assert "Analyze AAPL's seasonality" in out
    assert "Analyze GLD" not in out
    assert "mcp_admission_id" not in out
    assert _TEST_MCP_ADMISSION_ID not in out


@pytest.mark.anyio
async def test_whoami_example_prefers_etfs_when_in_scope(monkeypatch):
    async def fake_get(path, params=None):
        return _me_payload(["2", "11"])
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.whoami(ctx=None)
    assert "Analyze GLD's seasonality" in out


# --- teaser_state: the structural in-chat disclosure rides /me into whoami ------------

def _me_with_teaser(teaser_state):
    """A minimal /me payload carrying a teaser_state contract (what the gateway emits)."""
    p = _me_payload(["2"])
    p["teaser_state"] = teaser_state
    return p


@pytest.mark.anyio
async def test_whoami_steady_payer_no_teaser_disclosure(monkeypatch):
    # A steady payer's /me carries the inactive teaser contract; whoami must NOT add the
    # teaser disclosure sentence.
    inactive = {"active": False, "kind": None, "ends_at": None, "post_teaser_scope": None}
    async def fake_get(path, params=None):
        return _me_with_teaser(inactive)
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.whoami(ctx=None)
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"] == inactive          # shape rides through verbatim
    assert "In-chat teaser active" not in out


@pytest.mark.anyio
async def test_whoami_explorer_trial_teaser_disclosed(monkeypatch):
    ts = {"active": True, "kind": "explorer_trial",
          "ends_at": "2026-07-05T00:00:00+00:00", "post_teaser_scope": "explorer"}
    async def fake_get(path, params=None):
        return _me_with_teaser(ts)
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.whoami(ctx=None)
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"]["kind"] == "explorer_trial"
    assert body["teaser_state"]["post_teaser_scope"] == "explorer"
    assert "In-chat teaser active until 2026-07-05T00:00:00+00:00" in out
    assert "reverts to explorer scope after" in out


@pytest.mark.anyio
async def test_whoami_navigator_firstconnect_teaser_disclosed(monkeypatch):
    ts = {"active": True, "kind": "navigator_firstconnect",
          "ends_at": "2026-07-05T00:00:00+00:00", "post_teaser_scope": "navigator"}
    async def fake_get(path, params=None):
        return _me_with_teaser(ts)
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.whoami(ctx=None)
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["teaser_state"]["kind"] == "navigator_firstconnect"
    assert "reverts to navigator scope after" in out


# --- morning_briefing: one-call composition ------------------------------------------

@pytest.mark.anyio
async def test_morning_briefing_composes_three_sections(monkeypatch):
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
    out = await server.morning_briefing(ctx=None)
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


@pytest.mark.anyio
async def test_morning_briefing_degrades_per_section(monkeypatch):
    async def fake_get(path, params=None):
        if path == "/scan":
            raise server.GatewayError("rate limit exceeded")
        if path == "/daily-pick":
            return {"card": {"symbol": "AAPL"}, "as_of": "2026-06-12"}
        return {"summary": {"count": 1}, "picks": []}
    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.morning_briefing(ctx=None)
    import json as _json
    body = _json.loads(out.split("\n\n")[1])
    assert body["this_week"] == {"unavailable": "rate limit exceeded"}
    assert body["todays_pick"]["symbol"] == "AAPL"


@pytest.mark.anyio
async def test_pick_track_record_bounds_rows_but_preserves_full_summary(monkeypatch):
    async def fake_get(_path, _params=None):
        return {
            "summary": {"count": 300, "win_rate": 0.6},
            "picks": [{"sequence": index} for index in range(300)],
        }

    monkeypatch.setattr(server, "_get", fake_get)
    output = await server.get_pick_track_record(ctx=None)
    payload = json.loads(output)

    assert payload["summary"]["count"] == 300
    assert len(payload["picks"]) == server._MCP_TRACK_RECORD_MAX_PICKS == 250
    assert payload["picks"][0]["sequence"] == 50
    assert payload["picks"][-1]["sequence"] == 299
    assert payload["returned_count"] == 250
    assert payload["truncated"] is True


# --- real async execution / shared-client lifecycle ---------------------------------

def _request_ctx(key):
    request = SimpleNamespace(headers={"authorization": f"Bearer {key}"})
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest.mark.anyio
async def test_concurrent_same_byok_key_validation_is_singleflight(monkeypatch):
    """Twenty cold connects with one key spend exactly one gateway /me request."""
    started = asyncio.Event()
    release = asyncio.Event()
    gateway_calls = 0

    async def handler(request):
        nonlocal gateway_calls
        gateway_calls += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json=_admission_payload(), request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_auth_client", client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(4))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    tasks = [asyncio.create_task(server._byok_key_valid("tw_same_customer"))
             for _ in range(20)]
    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
        # Let every waiter reach the shared task while its one gateway call is held.
        await asyncio.sleep(0)
        assert gateway_calls == 1
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await client.aclose()

    assert results == [True] * 20
    assert gateway_calls == 1
    assert len(server._byok_cache) == 1
    assert server._byok_inflight == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"mcp_admission_id": "raw-user-id"},
        {"mcp_admission_id": "acct_" + "A" * 64},
        {"mcp_admission_id": "acct_" + "a" * 63},
        ["acct_" + "a" * 64],
    ],
)
async def test_byok_validation_requires_exact_gateway_account_binding(
    monkeypatch, payload
):
    """A 200 without the trusted opaque account id cannot establish a session."""

    async def handler(request):
        return httpx.Response(200, json=payload, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_auth_client", client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(1))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    try:
        assert await server._byok_key_valid("tw_missing_account_binding") is False
    finally:
        await client.aclose()

    assert len(server._byok_cache) == 1
    assert next(iter(server._byok_cache.values()))[1] is None


@pytest.mark.anyio
async def test_byok_admission_response_is_identity_only_and_bounded(monkeypatch):
    compressed = gzip.compress(b"x" * (server._AUTH_RESPONSE_MAX_BYTES * 20))
    stream = _AsyncChunks(compressed)
    observed_accept_encoding = None

    async def handler(request):
        nonlocal observed_accept_encoding
        observed_accept_encoding = request.headers.get("accept-encoding")
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=stream,
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_auth_client", client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(1))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    try:
        assert await server._byok_key_valid("tw_encoded_admission") is False
    finally:
        await client.aclose()

    assert observed_accept_encoding == "identity"
    assert not stream.iterated
    assert stream.closed
    assert server._byok_cache == {}


@pytest.mark.anyio
async def test_cancelled_byok_waiter_does_not_cancel_or_leak_singleflight(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    gateway_calls = 0

    async def handler(request):
        nonlocal gateway_calls
        gateway_calls += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json=_admission_payload(), request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_auth_client", client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(4))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    waiter = asyncio.create_task(server._byok_key_valid("tw_disconnected"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert len(server._byok_inflight) == 1

        # The shielded shared validation finishes independently; its done callback must
        # remove the entry even though no request task remains to run a finally block.
        release.set()
        for _ in range(10):
            if not server._byok_inflight:
                break
            await asyncio.sleep(0)
    finally:
        release.set()
        await client.aclose()

    assert gateway_calls == 1
    assert len(server._byok_cache) == 1
    assert server._byok_inflight == {}


@pytest.mark.anyio
async def test_unique_byok_singleflights_fail_closed_at_cardinality_bound(monkeypatch):
    """Disconnected unique keys cannot outgrow the ASGI concurrency budget."""
    release = asyncio.Event()

    async def occupied_validation():
        await release.wait()
        return _TEST_MCP_ADMISSION_ID

    occupied = [asyncio.create_task(occupied_validation()) for _ in range(2)]
    monkeypatch.setattr(
        server,
        "_byok_inflight",
        {f"occupied-{index}": task for index, task in enumerate(occupied)},
    )
    monkeypatch.setattr(server, "_BYOK_INFLIGHT_MAX", 2)

    called = False

    async def must_not_start(_key, _key_hash):
        nonlocal called
        called = True
        return _TEST_MCP_ADMISSION_ID

    monkeypatch.setattr(server, "_validate_byok_key", must_not_start)
    try:
        assert await server._byok_key_valid("tw_unique_overload") is False
        assert called is False
        assert len(server._byok_inflight) == 2
    finally:
        release.set()
        await asyncio.gather(*occupied)


@pytest.mark.anyio
async def test_twenty_tool_calls_overlap_and_keep_auth_isolated(monkeypatch):
    """Exercise complete BYOK tool -> _get -> _request paths, independent of host secrets."""
    # tests/conftest.py intentionally mirrors the VM's secrets.env, which enables OAuth
    # in a real candidate test run. This test targets the separate BYOK/header branch;
    # pin that branch explicitly. Real OAuth context/session isolation is exercised by
    # the protocol-level ASGI tests below.
    monkeypatch.setattr(server, "OAUTH_ENABLED", False)
    monkeypatch.setattr(server, "TRADEWAVE_API_KEY", "")
    all_started = asyncio.Event()
    release = asyncio.Event()
    seen_headers = {}
    started = 0

    async def handler(request):
        nonlocal started
        symbol = request.url.path.rsplit("/", 1)[-1]
        seen_headers[symbol] = request.headers.get("authorization")
        started += 1
        if started == 20:
            all_started.set()
        await release.wait()
        return httpx.Response(200, json={"card": {"bias": "bullish"}}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", asyncio.Semaphore(32))
    try:
        tasks = [asyncio.create_task(server.analyze_symbol(
            symbol=f"S{i}", ctx=_request_ctx(f"tw_key_{i}"))) for i in range(20)]
        await asyncio.wait_for(all_started.wait(), timeout=1.0)
        # While all twenty network calls are suspended, the event loop remains responsive.
        ticked = asyncio.Event()
        asyncio.get_running_loop().call_soon(ticked.set)
        await asyncio.wait_for(ticked.wait(), timeout=0.1)
        assert not any(task.done() for task in tasks)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
    finally:
        release.set()
        await client.aclose()

    assert len(results) == 20
    assert started == 20
    assert seen_headers == {f"S{i}": f"Bearer tw_key_{i}" for i in range(20)}


@pytest.mark.anyio
async def test_mcp_lifespan_owns_and_closes_shared_client():
    assert server._gateway_client is None
    assert server._gateway_gate is None
    assert server._auth_client is None
    assert server._auth_gate is None
    assert server._gateway_pool_users == 0
    async with server._mcp_lifespan(server.mcp) as state:
        client = state["gateway_client"]
        auth_client = state["auth_client"]
        assert server._gateway_client is client
        assert server._auth_client is auth_client
        assert not client.is_closed
        assert not auth_client.is_closed
        assert server._gateway_gate is not None
        assert server._auth_gate is not None
        assert server._gateway_pool_users == 1
        async with server._mcp_lifespan(server.mcp) as nested_state:
            assert nested_state["gateway_client"] is client
            assert nested_state["auth_client"] is auth_client
            assert server._gateway_pool_users == 2
        assert server._gateway_pool_users == 1
        assert not client.is_closed
        assert not auth_client.is_closed
    assert client.is_closed
    assert auth_client.is_closed
    assert server._gateway_client is None
    assert server._gateway_gate is None
    assert server._auth_client is None
    assert server._auth_gate is None
    assert server._gateway_pool_users == 0


@pytest.mark.anyio
async def test_byok_admission_is_not_starved_by_saturated_research_pool(monkeypatch):
    """A full long-call pool cannot delay a new customer's short /me validation."""
    data_started = 0
    all_data_started = asyncio.Event()
    release_data = asyncio.Event()

    async def data_handler(request):
        nonlocal data_started
        data_started += 1
        if data_started == 3:
            all_data_started.set()
        await release_data.wait()
        return httpx.Response(200, json={"ok": True}, request=request)

    async def auth_handler(request):
        assert request.url.path.endswith("/me")
        return httpx.Response(200, json=_admission_payload(), request=request)

    data_client = httpx.AsyncClient(transport=httpx.MockTransport(data_handler))
    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    monkeypatch.setattr(server, "_gateway_client", data_client)
    monkeypatch.setattr(server, "_gateway_gate", asyncio.Semaphore(3))
    monkeypatch.setattr(server, "_auth_client", auth_client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(1))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})

    data_tasks = [asyncio.create_task(server._get(f"/slow/{i}")) for i in range(3)]
    try:
        await asyncio.wait_for(all_data_started.wait(), timeout=1.0)
        assert not any(task.done() for task in data_tasks)
        assert await asyncio.wait_for(
            server._byok_key_valid("tw_new_customer"), timeout=0.2
        ) is True
        assert not any(task.done() for task in data_tasks)
    finally:
        release_data.set()
        await asyncio.gather(*data_tasks)
        await data_client.aclose()
        await auth_client.aclose()


@pytest.mark.anyio
async def test_byok_admission_fails_closed_quickly_when_auth_pool_is_saturated(monkeypatch):
    """An unverified cold key cannot retain a session during an auth burst."""
    auth_calls = 0

    async def auth_handler(request):
        nonlocal auth_calls
        auth_calls += 1
        return httpx.Response(200, json=_admission_payload(), request=request)

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    held_gate = asyncio.Semaphore(0)
    monkeypatch.setattr(server, "_auth_client", auth_client)
    monkeypatch.setattr(server, "_auth_gate", held_gate)
    monkeypatch.setattr(server, "_AUTH_ADMISSION_WAIT_TIMEOUT", 0.01)
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    try:
        assert await asyncio.wait_for(
            server._byok_key_valid("tw_burst_customer"), timeout=1.0
        ) is False
    finally:
        await auth_client.aclose()

    assert auth_calls == 0
    assert server._byok_cache == {}


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_uncached_byok_gateway_errors_fail_closed_without_caching(
    monkeypatch, status_code
):
    async def auth_handler(request):
        return httpx.Response(status_code, request=request)

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    monkeypatch.setattr(server, "_auth_client", auth_client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(1))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    try:
        assert await server._byok_key_valid(f"tw_gateway_{status_code}") is False
    finally:
        await auth_client.aclose()

    assert server._byok_cache == {}


@pytest.mark.anyio
async def test_uncached_byok_network_failure_fails_closed_without_caching(monkeypatch):
    async def auth_handler(request):
        raise httpx.ConnectError("gateway unavailable", request=request)

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    monkeypatch.setattr(server, "_auth_client", auth_client)
    monkeypatch.setattr(server, "_auth_gate", asyncio.Semaphore(1))
    monkeypatch.setattr(server, "_byok_cache", {})
    monkeypatch.setattr(server, "_byok_inflight", {})
    try:
        assert await server._byok_key_valid("tw_gateway_unavailable") is False
    finally:
        await auth_client.aclose()

    assert server._byok_cache == {}


@pytest.mark.anyio
async def test_all_server_http_clients_ignore_inherited_proxy_environment(monkeypatch):
    """Bearer/JWKS traffic must never inherit a poisoned service-launch proxy."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("SSL_CERT_FILE", "/untrusted/cert.pem")

    gateway_client = server._new_gateway_client()
    auth_client = server._new_auth_client()
    assert gateway_client._trust_env is False
    assert auth_client._trust_env is False
    await gateway_client.aclose()
    await auth_client.aclose()

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def build_request(self, method, url, headers):
            captured["request_headers"] = headers
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, stream):
            assert stream is True
            return httpx.Response(
                200,
                json={},
                request=request,
            )

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)
    resolver = server._AsyncJwksResolver("https://auth.example")
    await resolver._fetch_json(resolver._jwks_uri)
    assert captured["trust_env"] is False
    assert captured["request_headers"]["Accept-Encoding"] == "identity"


def test_streamable_http_runner_has_global_admission_bounds(monkeypatch):
    import uvicorn

    captured = {}
    marker = object()

    def fake_run(app, **kwargs):
        captured.update(app=app, **kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(server.mcp.settings, "host", "127.0.0.1")
    monkeypatch.setattr(server.mcp.settings, "port", 9090)
    server._run_streamable_http_app(marker)

    assert captured["app"] is marker
    assert captured["limit_concurrency"] == server._MCP_MAX_INBOUND_CONCURRENCY == 128
    assert captured["backlog"] == server._MCP_SOCKET_BACKLOG == 128
    assert captured["limit_concurrency"] >= 20 * 4


def test_streamable_http_manager_has_finite_idle_timeout(monkeypatch):
    monkeypatch.setattr(server.mcp, "_session_manager", None)
    app = server._streamable_http_app_with_idle_timeout()
    manager = server.mcp.session_manager

    assert app is not None
    assert manager.stateless is False
    assert manager.session_idle_timeout == server._MCP_SESSION_IDLE_TIMEOUT_SECONDS == 1800.0
    assert server._MCP_MAX_ACTIVE_SESSIONS == 128
    assert server._MCP_MAX_SESSIONS_PER_PRINCIPAL == 24
    protected_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == server.mcp.settings.streamable_http_path
    )
    assert isinstance(protected_route.app, server._ActiveSessionAdmissionMiddleware)


def test_legacy_sse_transport_is_not_an_rc_runtime_option(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["server.py", "--transport", "sse"])
    with pytest.raises(SystemExit) as exc:
        server._parse_args()
    assert exc.value.code == 2


def _load_oauth_server(monkeypatch):
    """Load an isolated OAuth-enabled server module for real ASGI protocol tests."""
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://auth.example")
    monkeypatch.setenv("TW2_MCP_PUBLIC_URL", "https://mcp.example")
    monkeypatch.setenv("MCP_GATEWAY_KEY", "tw_svc_" + "A" * 43)
    module_name = f"_tradewave_mcp_oauth_test_{id(monkeypatch)}"
    spec = importlib.util.spec_from_file_location(module_name, server.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)

    async def valid_byok(_key):
        return "acct_" + hashlib.sha256(
            ("test-account:" + _key).encode()
        ).hexdigest()

    monkeypatch.setattr(module, "_byok_key_identity", valid_byok)
    module.mcp.settings.streamable_http_path = "/"
    from mcp.server.transport_security import TransportSecuritySettings
    module.mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    return module


def test_oauth_configured_stdio_still_uses_its_single_user_env_key(monkeypatch):
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "TRADEWAVE_API_KEY", "tw_stdio_customer")
    reset = oauth_server._request_principal.set(None)
    try:
        oauth_server._bind_request_key(None)
        assert oauth_server._request_principal.get() == {
            "mode": "byok",
            "key": "tw_stdio_customer",
        }
    finally:
        oauth_server._request_principal.reset(reset)


def test_oauth_http_without_verified_sdk_context_never_uses_stdio_key(monkeypatch):
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "TRADEWAVE_API_KEY", "tw_must_not_escape")
    context = SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(
                headers={"Authorization": "Bearer tw_unverified_http_value"}
            )
        )
    )
    reset = oauth_server._request_principal.set(
        {"mode": "byok", "key": "tw_stale_context"}
    )
    try:
        oauth_server._bind_request_key(context)
        assert oauth_server._request_principal.get() is None
    finally:
        oauth_server._request_principal.reset(reset)


@pytest.mark.anyio
async def test_oversized_byok_token_is_rejected_before_gateway_validation(monkeypatch):
    oauth_server = _load_oauth_server(monkeypatch)
    called = False

    async def should_not_validate(_key):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(oauth_server, "_byok_key_identity", should_not_validate)
    verifier = oauth_server.WorkOSTokenVerifier()
    token = "tw_" + ("A" * oauth_server._OAUTH_TOKEN_MAX_LENGTH)
    assert await verifier.verify_token(token) is None
    assert called is False


@pytest.mark.anyio
async def test_oauth_failure_log_never_interpolates_token_derived_exception_text(
    monkeypatch, caplog
):
    oauth_server = _load_oauth_server(monkeypatch)
    verifier = oauth_server.WorkOSTokenVerifier()
    sentinel = "SENSITIVE_TOKEN_FRAGMENT_MUST_NOT_BE_LOGGED"

    async def reject(_token):
        raise ValueError(sentinel)

    monkeypatch.setattr(verifier._jwks, "signing_key", reject)
    with caplog.at_level("DEBUG"):
        assert await verifier.verify_token("header.payload.signature") is None

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in rendered
    assert "ValueError" in rendered


@pytest.mark.anyio
async def test_byok_background_failure_log_never_interpolates_exception_text(caplog):
    sentinel = "SENSITIVE_BYOK_FRAGMENT_MUST_NOT_BE_LOGGED"

    async def fail():
        raise RuntimeError(sentinel)

    task = asyncio.create_task(fail())
    try:
        await task
    except RuntimeError:
        pass

    with caplog.at_level("ERROR"):
        server._finish_byok_validation("a" * 64, task)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in rendered
    assert "RuntimeError" in rendered


@pytest.mark.anyio
async def test_unverified_byok_cannot_create_or_retain_a_protocol_session(monkeypatch):
    """Auth failure occurs before the stateful session manager registers a transport."""
    oauth_server = _load_oauth_server(monkeypatch)

    async def unverified_byok(_key):
        return None

    monkeypatch.setattr(oauth_server, "_byok_key_identity", unverified_byok)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/",
                headers=_rpc_headers("tw_unverified_cold_key"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "negative-auth-test", "version": "1"},
                    },
                },
            )

    assert response.status_code == 401
    assert response.headers.get("Mcp-Session-Id") is None
    assert manager._server_instances == {}
    protected_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == oauth_server.mcp.settings.streamable_http_path
    )
    admission = protected_route.app
    assert isinstance(admission, oauth_server._ActiveSessionAdmissionMiddleware)
    assert admission._pending_initializations == 0
    assert admission._pending_by_owner == {}


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "DELETE", "HEAD", "PUT"])
async def test_authenticated_sessionless_nonpost_never_allocates_transport(
    monkeypatch, method
):
    """Reject the SDK's method-before-allocation edge at the protected route."""
    oauth_server = _load_oauth_server(monkeypatch)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            for _ in range(5):
                response = await client.request(
                    method,
                    "/",
                    headers=_rpc_headers("tw_method_bypass_probe"),
                    content=b"{}" if method == "PUT" else None,
                )
                assert response.status_code == 405
                assert response.headers["allow"] == "POST"
                if method != "HEAD":
                    assert response.json()["error"]["code"] == -32600
                assert manager._server_instances == {}
                assert manager._session_owners == {}


_CURRENT_PROTOCOL_VERSION = "2025-11-25"
_LEGACY_PROTOCOL_VERSION = "2025-06-18"
_EXPECTED_PUBLIC_TOOL_NAMES = {
    "analyze_symbol",
    "compare_opportunities",
    "describe_tradewave",
    "explain_pick",
    "find_best_opportunities",
    "get_daily_pick",
    "get_opportunity_chart",
    "get_pick_track_record",
    "get_seasonal_opportunities",
    "get_seasonal_pattern",
    "get_symbol_patterns",
    "list_markets",
    "list_symbols",
    "morning_briefing",
    "score_opportunities",
    "whats_seasonal_now",
    "whoami",
}


def _rpc_headers(key, session_id=None, protocol_version=_CURRENT_PROTOCOL_VERSION):
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol_version,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


def _rpc_response_message(response, request_id):
    """Decode either JSON or Streamable HTTP's SSE-framed JSON-RPC response."""
    if response.headers.get("content-type", "").split(";", 1)[0] == "application/json":
        messages = response.json()
        if isinstance(messages, dict):
            messages = [messages]
    else:
        messages = []
        data_lines = []
        for line in response.text.splitlines() + [""]:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif not line.strip() and data_lines:
                messages.append(json.loads("\n".join(data_lines)))
                data_lines = []
    return next(message for message in messages if message.get("id") == request_id)


async def _initialize_public_session(
    client, key, protocol_version=_CURRENT_PROTOCOL_VERSION
):
    response = await client.post(
        "/",
        headers=_rpc_headers(key, protocol_version=protocol_version),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "isolation-test", "version": "1"},
            },
        },
    )
    assert response.status_code == 200, response.text
    initialized_message = _rpc_response_message(response, 1)
    assert initialized_message["result"]["protocolVersion"] == protocol_version
    session_id = response.headers.get("Mcp-Session-Id")
    assert session_id
    initialized = await client.post(
        "/",
        headers=_rpc_headers(key, session_id, protocol_version),
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    )
    assert initialized.status_code in {200, 202}, initialized.text
    return session_id


def _oauth_token_factory(oauth_server):
    """Install one local signing key in the real async verifier and mint JWTs."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = oauth_server.mcp._token_verifier
    assert isinstance(verifier, oauth_server.WorkOSTokenVerifier)
    verifier._jwks._keys = {"protocol-test-kid": private_key.public_key()}
    verifier._jwks._keys_expires_at = time.monotonic() + 300
    verifier._jwks._last_refresh_at = time.monotonic()

    def mint(subject, client_id="chatgpt"):
        return pyjwt.encode(
            {
                "iss": "https://auth.example",
                "aud": "https://mcp.example",
                "sub": subject,
                "client_id": client_id,
                "exp": int(time.time()) + 300,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "protocol-test-kid"},
        )

    return mint


@pytest.mark.anyio
async def test_oauth_protocol_call_delegates_exact_subject_with_service_key(monkeypatch):
    """Lock the complete JWT -> SDK context -> loopback delegation boundary."""
    oauth_server = _load_oauth_server(monkeypatch)
    mint = _oauth_token_factory(oauth_server)
    subject = "user_protocol_delegation"
    observed = []

    async def gateway(request):
        observed.append(
            (
                request.url.path,
                request.headers.get("authorization"),
                request.headers.get("x-tw-principal-workos"),
            )
        )
        return httpx.Response(
            200,
            json={
                "tier": "analyst",
                "tier_name": "Analyst",
                "ml_remaining_today": 100,
                "markets_in_scope": [],
            },
        )

    monkeypatch.setattr(
        oauth_server,
        "_new_gateway_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(gateway)),
    )
    app = oauth_server._streamable_http_app_with_idle_timeout()
    transport = httpx.ASGITransport(app=app)
    token = mint(subject)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            session_id = await _initialize_public_session(client, token)
            assert oauth_server.mcp.session_manager._session_owners[session_id] == {
                "client_id": "chatgpt",
                "issuer": "https://auth.example",
                "subject": subject,
            }
            response = await client.post(
                "/",
                headers=_rpc_headers(token, session_id),
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "whoami", "arguments": {}},
                },
            )
            assert response.status_code == 200, response.text
            assert "result" in _rpc_response_message(response, 2)
            deleted = await client.delete(
                "/", headers=_rpc_headers(token, session_id)
            )
            assert deleted.status_code in {200, 204}

    assert observed == [
        ("/v1/me", f"Bearer {oauth_server.MCP_GATEWAY_KEY}", subject)
    ]


@pytest.mark.anyio
async def test_twenty_oauth_sessions_overlap_without_principal_cross_talk(monkeypatch):
    """Twenty concurrent SDK sessions retain distinct delegated WorkOS subjects."""
    oauth_server = _load_oauth_server(monkeypatch)
    mint = _oauth_token_factory(oauth_server)
    subjects = [f"user_parallel_{index:02d}" for index in range(20)]
    observed = []
    entered = 0
    all_entered = asyncio.Event()
    release = asyncio.Event()

    async def gateway(request):
        nonlocal entered
        observed.append(
            (
                request.headers.get("authorization"),
                request.headers.get("x-tw-principal-workos"),
            )
        )
        entered += 1
        if entered == 20:
            all_entered.set()
        await release.wait()
        return httpx.Response(
            200,
            json={
                "tier": "analyst",
                "tier_name": "Analyst",
                "ml_remaining_today": 100,
                "markets_in_scope": [],
            },
        )

    monkeypatch.setattr(
        oauth_server,
        "_new_gateway_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(gateway)),
    )
    app = oauth_server._streamable_http_app_with_idle_timeout()
    transport = httpx.ASGITransport(app=app)
    tokens = [mint(subject) for subject in subjects]

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            session_ids = await asyncio.wait_for(
                asyncio.gather(
                    *(_initialize_public_session(client, token) for token in tokens)
                ),
                timeout=5,
            )
            calls = [
                asyncio.create_task(
                    client.post(
                        "/",
                        headers=_rpc_headers(token, session_id),
                        json={
                            "jsonrpc": "2.0",
                            "id": index + 2,
                            "method": "tools/call",
                            "params": {"name": "whoami", "arguments": {}},
                        },
                    )
                )
                for index, (token, session_id) in enumerate(zip(tokens, session_ids))
            ]
            await asyncio.wait_for(all_entered.wait(), timeout=2)
            await asyncio.sleep(0)
            assert entered == 20
            assert not any(call.done() for call in calls)
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(*calls), timeout=2)
            for index, response in enumerate(responses):
                assert response.status_code == 200, response.text
                assert "result" in _rpc_response_message(response, index + 2)

            deletes = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        client.delete(
                            "/", headers=_rpc_headers(token, session_id)
                        )
                        for token, session_id in zip(tokens, session_ids)
                    )
                ),
                timeout=5,
            )
            assert all(response.status_code in {200, 204} for response in deletes)

    assert {subject for _authorization, subject in observed} == set(subjects)
    assert len(observed) == 20
    assert all(
        authorization == f"Bearer {oauth_server.MCP_GATEWAY_KEY}"
        for authorization, _subject in observed
    )


@pytest.mark.anyio
async def test_oauth_fairness_cannot_be_multiplied_by_dynamic_client_ids(monkeypatch):
    """One WorkOS subject shares one cap across public DCR client registrations."""
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_ACTIVE_SESSIONS", 8)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_SESSIONS_PER_PRINCIPAL", 2)
    mint = _oauth_token_factory(oauth_server)
    subject = "user_same_human"
    tokens = [mint(subject, f"dynamic-client-{index}") for index in range(3)]
    other_token = mint("user_other_human", "dynamic-client-other")
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            sessions = [
                await _initialize_public_session(client, token)
                for token in tokens[:2]
            ]
            assert {
                owner["client_id"] for owner in manager._session_owners.values()
            } == {"dynamic-client-0", "dynamic-client-1"}

            rejected = await client.post(
                "/",
                headers=_rpc_headers(tokens[2]),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "dcr-fairness", "version": "1"},
                    },
                },
            )
            assert rejected.status_code == 503

            other_session = await _initialize_public_session(client, other_token)
            for token, session_id in [
                *zip(tokens[:2], sessions),
                (other_token, other_session),
            ]:
                deleted = await client.delete(
                    "/", headers=_rpc_headers(token, session_id)
                )
                assert deleted.status_code in {200, 204}


@pytest.mark.anyio
async def test_current_and_legacy_protocol_revisions_publish_exact_catalog(monkeypatch):
    oauth_server = _load_oauth_server(monkeypatch)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for index, protocol_version in enumerate(
                (_CURRENT_PROTOCOL_VERSION, _LEGACY_PROTOCOL_VERSION)
            ):
                key = f"tw_protocol_{index}"
                session_id = await _initialize_public_session(
                    client, key, protocol_version
                )
                listed = await client.post(
                    "/",
                    headers=_rpc_headers(key, session_id, protocol_version),
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {},
                    },
                )
                assert listed.status_code == 200, listed.text
                payload = _rpc_response_message(listed, 2)
                assert payload["jsonrpc"] == "2.0"
                assert payload["id"] == 2
                tools = payload["result"]["tools"]
                names = [tool["name"] for tool in tools]
                assert len(names) == len(set(names))
                assert set(names) == _EXPECTED_PUBLIC_TOOL_NAMES
                deleted = await client.delete(
                    "/", headers=_rpc_headers(key, session_id, protocol_version)
                )
                assert deleted.status_code in {200, 204}


@pytest.mark.anyio
async def test_active_session_cap_rejects_then_recovers_after_delete(monkeypatch):
    """Retained sessions are bounded independently from in-flight HTTP requests."""
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_ACTIVE_SESSIONS", 1)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first_key = "tw_capacity_first"
            first_session = await _initialize_public_session(client, first_key)
            assert len(manager._server_instances) == 1

            wrong_owner_delete = await client.delete(
                "/",
                headers=_rpc_headers("tw_capacity_attacker", first_session),
            )
            assert wrong_owner_delete.status_code == 404
            assert first_session in manager._server_instances

            rejected = await client.post(
                "/",
                headers=_rpc_headers("tw_capacity_second"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "capacity-test", "version": "1"},
                    },
                },
            )
            assert rejected.status_code == 503, rejected.text
            assert rejected.headers["retry-after"] == "5"
            assert rejected.json()["error"]["code"] == -32000
            assert len(manager._server_instances) == 1

            deleted = await client.delete(
                "/", headers=_rpc_headers(first_key, first_session)
            )
            assert deleted.status_code in {200, 204}
            deadline = asyncio.get_running_loop().time() + 1.0
            while manager._server_instances and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.01)
            assert not manager._server_instances
            deadline = asyncio.get_running_loop().time() + 1.0
            while (
                oauth_server._gateway_pool_users != 1
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)
            assert oauth_server._gateway_pool_users == 1

            second_key = "tw_capacity_second"
            second_session = await _initialize_public_session(client, second_key)
            assert second_session in manager._server_instances
            second_deleted = await client.delete(
                "/", headers=_rpc_headers(second_key, second_session)
            )
            assert second_deleted.status_code in {200, 204}
            assert not manager._server_instances

            # Rapid clean churn must not leak the SDK's terminated transports into
            # the admission count (an upstream 1.28.1 manager edge case).
            for index in range(5):
                key = f"tw_capacity_churn_{index}"
                session_id = await _initialize_public_session(client, key)
                churn_deleted = await client.delete(
                    "/", headers=_rpc_headers(key, session_id)
                )
                assert churn_deleted.status_code in {200, 204}
                assert not manager._server_instances
                deadline = asyncio.get_running_loop().time() + 1.0
                while (
                    oauth_server._gateway_pool_users != 1
                    and asyncio.get_running_loop().time() < deadline
                ):
                    await asyncio.sleep(0.01)
                assert oauth_server._gateway_pool_users == 1


@pytest.mark.anyio
async def test_terminated_delete_is_evicted_even_when_response_send_fails():
    """A disconnected client cannot leak an already-terminated session slot."""
    transport = SimpleNamespace(is_terminated=True)
    manager = SimpleNamespace(
        _server_instances={"owned-session": transport},
        _session_owners={"owned-session": object()},
    )

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware = server._ActiveSessionAdmissionMiddleware(
        downstream,
        manager=manager,
        max_sessions=1,
        max_sessions_per_principal=1,
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def disconnected_send(_message):
        raise BrokenPipeError("client disconnected")

    scope = {
        "type": "http",
        "method": "DELETE",
        "path": "/",
        "headers": [(b"mcp-session-id", b"owned-session")],
    }
    with pytest.raises(BrokenPipeError):
        await middleware(scope, receive, disconnected_send)

    assert manager._server_instances == {}
    assert manager._session_owners == {}


@pytest.mark.anyio
async def test_pending_initializations_are_counted_atomically_at_session_cap():
    """Concurrent handshakes cannot all pass a stale len(registry) check."""
    manager = SimpleNamespace(_server_instances={}, _session_owners={})
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def downstream(_scope, _receive, send):
        first_started.set()
        await release_first.wait()
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = server._ActiveSessionAdmissionMiddleware(
        downstream,
        manager=manager,
        max_sessions=1,
        max_sessions_per_principal=1,
    )
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    access_token = AccessToken(
        token="not-retained-by-admission",
        client_id="byok",
        scopes=[],
        expires_at=None,
        resource="https://mcp.example",
        subject=server._byok_session_subject(
            "tw_unit_owner", _TEST_MCP_ADMISSION_ID
        ),
        claims={"mode": "byok", "admission_id": _TEST_MCP_ADMISSION_ID},
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "user": AuthenticatedUser(access_token),
    }

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    first_messages = []
    async def collect_first(message):
        first_messages.append(message)

    first = asyncio.create_task(
        middleware(scope, receive, collect_first)
    )
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    rejected_messages = []
    async def collect_rejected(message):
        rejected_messages.append(message)

    await middleware(scope, receive, collect_rejected)
    assert rejected_messages[0]["status"] == 503
    assert middleware._pending_initializations == 1

    release_first.set()
    await asyncio.wait_for(first, timeout=1.0)
    assert first_messages[0]["status"] == 401
    assert middleware._pending_initializations == 0
    assert middleware._pending_by_owner == {}


@pytest.mark.anyio
async def test_per_principal_cap_protects_other_users_and_recovers_after_delete(
    monkeypatch,
):
    """The public demo credential cannot monopolize the retained-session pool."""
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_ACTIVE_SESSIONS", 8)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_SESSIONS_PER_PRINCIPAL", 2)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)
    demo_key = "tw_demo_explore"
    other_key = "tw_customer_still_admitted"

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            demo_sessions = [
                await _initialize_public_session(client, demo_key) for _ in range(2)
            ]

            rejected = await client.post(
                "/",
                headers=_rpc_headers(demo_key),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "fairness-test", "version": "1"},
                    },
                },
            )
            assert rejected.status_code == 503
            assert len(manager._server_instances) == 2

            # Capacity held by one owner must not block a different verified owner.
            other_session = await _initialize_public_session(client, other_key)
            wrong_owner = await client.delete(
                "/", headers=_rpc_headers(other_key, demo_sessions[0])
            )
            assert wrong_owner.status_code == 404

            still_rejected = await client.post(
                "/",
                headers=_rpc_headers(demo_key),
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "fairness-test", "version": "1"},
                    },
                },
            )
            assert still_rejected.status_code == 503

            released = await client.delete(
                "/", headers=_rpc_headers(demo_key, demo_sessions.pop())
            )
            assert released.status_code in {200, 204}
            replacement = await _initialize_public_session(client, demo_key)

            for key, session_id in [
                (demo_key, *demo_sessions),
                (demo_key, replacement),
                (other_key, other_session),
            ]:
                deleted = await client.delete(
                    "/", headers=_rpc_headers(key, session_id)
                )
                assert deleted.status_code in {200, 204}


@pytest.mark.anyio
async def test_byok_fairness_groups_all_keys_for_one_gateway_account(monkeypatch):
    """Key rotation/max-key allowances cannot multiply an account's session cap."""
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_ACTIVE_SESSIONS", 8)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_SESSIONS_PER_PRINCIPAL", 2)
    same_account_keys = {"tw_account_key_a", "tw_account_key_b", "tw_account_key_c"}

    async def identity_for(key):
        return (
            _TEST_MCP_ADMISSION_ID
            if key in same_account_keys
            else _OTHER_MCP_ADMISSION_ID
        )

    monkeypatch.setattr(oauth_server, "_byok_key_identity", identity_for)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            sessions = [
                await _initialize_public_session(client, key)
                for key in ("tw_account_key_a", "tw_account_key_b")
            ]
            subjects = {
                owner["subject"] for owner in manager._session_owners.values()
            }
            assert len(subjects) == 2
            assert all(
                subject.startswith("byok:" + _TEST_MCP_ADMISSION_ID + ":")
                for subject in subjects
            )
            # Admission is account-level, but an individual SDK session remains
            # cryptographically/key-hash bound to the exact key that created it.
            wrong_key = await client.post(
                "/",
                headers=_rpc_headers("tw_account_key_b", sessions[0]),
                json={"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}},
            )
            assert wrong_key.status_code == 404
            right_key = await client.post(
                "/",
                headers=_rpc_headers("tw_account_key_a", sessions[0]),
                json={"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}},
            )
            assert right_key.status_code == 200

            rejected = await client.post(
                "/",
                headers=_rpc_headers("tw_account_key_c"),
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _CURRENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "multi-key-fairness", "version": "1"},
                    },
                },
            )
            assert rejected.status_code == 503

            other_key = "tw_different_account"
            other_session = await _initialize_public_session(client, other_key)
            for key, session_id in [
                ("tw_account_key_a", sessions[0]),
                ("tw_account_key_b", sessions[1]),
                (other_key, other_session),
            ]:
                deleted = await client.delete(
                    "/", headers=_rpc_headers(key, session_id)
                )
                assert deleted.status_code in {200, 204}


def test_admission_identity_is_mode_aware_for_cross_mode_collision():
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    byok = AccessToken(
        token="not-retained-by-admission",
        client_id="byok",
        scopes=[],
        expires_at=None,
        resource="https://mcp.example",
        subject=server._byok_session_subject(
            "tw_collision_key", _TEST_MCP_ADMISSION_ID
        ),
        claims={"mode": "byok", "admission_id": _TEST_MCP_ADMISSION_ID},
    )
    oauth = AccessToken(
        token="not-retained-by-admission",
        client_id="dynamic-client",
        scopes=[],
        expires_at=None,
        resource="https://mcp.example",
        subject=_TEST_MCP_ADMISSION_ID,
        claims={
            "mode": "oauth",
            "workos_sub": _TEST_MCP_ADMISSION_ID,
            "iss": "https://auth.example",
        },
    )

    assert server._ActiveSessionAdmissionMiddleware._verified_owner(
        {"user": AuthenticatedUser(byok)}
    ) == ("byok", _TEST_MCP_ADMISSION_ID)
    assert server._ActiveSessionAdmissionMiddleware._verified_owner(
        {"user": AuthenticatedUser(oauth)}
    ) == ("oauth", _TEST_MCP_ADMISSION_ID)


@pytest.mark.anyio
async def test_per_principal_pending_handshakes_are_atomic_and_fair():
    """Same-owner races stop at the cap while another owner can enter."""
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    manager = SimpleNamespace(_server_instances={}, _session_owners={})
    entered = []
    two_entered = asyncio.Event()
    release = asyncio.Event()

    def scope_for(admission_id, key):
        token = AccessToken(
            token="not-retained-by-admission",
            client_id="byok",
            scopes=[],
            expires_at=None,
            resource="https://mcp.example",
            subject=server._byok_session_subject(key, admission_id),
            claims={"mode": "byok", "admission_id": admission_id},
        )
        return {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "user": AuthenticatedUser(token),
        }

    async def downstream(scope, _receive, send):
        entered.append(scope["user"].access_token.subject)
        if len(entered) == 2:
            two_entered.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = server._ActiveSessionAdmissionMiddleware(
        downstream,
        manager=manager,
        max_sessions=4,
        max_sessions_per_principal=1,
    )

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def call(scope):
        messages = []

        async def collect(message):
            messages.append(message)

        await middleware(scope, receive, collect)
        return messages

    owner_a = scope_for(_TEST_MCP_ADMISSION_ID, "tw_owner_a")
    owner_b = scope_for(_OTHER_MCP_ADMISSION_ID, "tw_owner_b")
    first_a = asyncio.create_task(call(owner_a))
    while not entered:
        await asyncio.sleep(0)

    second_a = await call(owner_a)
    assert second_a[0]["status"] == 503

    first_b = asyncio.create_task(call(owner_b))
    await asyncio.wait_for(two_entered.wait(), timeout=1.0)
    assert middleware._pending_initializations == 2
    assert sorted(middleware._pending_by_owner.values()) == [1, 1]

    release.set()
    first_a_messages, first_b_messages = await asyncio.gather(first_a, first_b)
    assert first_a_messages[0]["status"] == 401
    assert first_b_messages[0]["status"] == 401
    assert middleware._pending_initializations == 0
    assert middleware._pending_by_owner == {}


@pytest.mark.anyio
async def test_byok_session_owner_rejects_a_different_valid_key(monkeypatch):
    """A leaked session id cannot cross from valid BYOK credential A to B."""
    oauth_server = _load_oauth_server(monkeypatch)
    key_a = "tw_customer_a"
    key_b = "tw_customer_b"
    subject_a = oauth_server._byok_session_subject(key_a, _TEST_MCP_ADMISSION_ID)
    subject_b = oauth_server._byok_session_subject(key_b, _TEST_MCP_ADMISSION_ID)
    assert subject_a != subject_b
    assert key_a not in subject_a and key_b not in subject_b

    app = oauth_server._streamable_http_app_with_idle_timeout()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            session_id = await _initialize_public_session(client, key_a)
            request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

            wrong_owner = await client.post(
                "/", headers=_rpc_headers(key_b, session_id), json=request)
            assert wrong_owner.status_code == 404, wrong_owner.text

            right_owner = await client.post(
                "/", headers=_rpc_headers(key_a, session_id), json=request)
            assert right_owner.status_code == 200, right_owner.text
            await client.delete("/", headers=_rpc_headers(key_a, session_id))


@pytest.mark.anyio
async def test_streamable_process_uses_one_pool_across_multiple_sessions(monkeypatch):
    """Stateful SDK lifespans are per-session; the outbound budget stays process-global."""
    oauth_server = _load_oauth_server(monkeypatch)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        process_client = oauth_server._gateway_client
        process_auth_client = oauth_server._auth_client
        assert process_client is not None and process_auth_client is not None
        assert oauth_server._gateway_pool_users == 1

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            session_a = await _initialize_public_session(client, "tw_pool_a")
            session_b = await _initialize_public_session(client, "tw_pool_b")
            assert oauth_server._gateway_client is process_client
            assert oauth_server._auth_client is process_auth_client
            assert oauth_server._gateway_pool_users == 3

            deleted = await client.delete(
                "/", headers=_rpc_headers("tw_pool_a", session_a)
            )
            assert deleted.status_code in {200, 204}
            for _ in range(20):
                if oauth_server._gateway_pool_users == 2:
                    break
                await asyncio.sleep(0)
            assert oauth_server._gateway_pool_users == 2
            assert not process_client.is_closed
            assert not process_auth_client.is_closed

            still_live = await client.post(
                "/",
                headers=_rpc_headers("tw_pool_b", session_b),
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            assert still_live.status_code == 200, still_live.text
            await client.delete("/", headers=_rpc_headers("tw_pool_b", session_b))

    assert process_client.is_closed
    assert process_auth_client.is_closed
    assert oauth_server._gateway_client is None
    assert oauth_server._auth_client is None
    assert oauth_server._gateway_pool_users == 0


@pytest.mark.anyio
async def test_idle_session_is_reaped_without_client_delete(monkeypatch):
    """Pinned MCP manager removes a vanished stateful session at the configured deadline."""
    oauth_server = _load_oauth_server(monkeypatch)
    monkeypatch.setattr(oauth_server, "_MCP_MAX_SESSIONS_PER_PRINCIPAL", 1)
    app = oauth_server._streamable_http_app_with_idle_timeout()
    manager = oauth_server.mcp.session_manager
    # The deadline starts before the initialize response is written. Keep enough
    # headroom for a loaded CI/VM so this tests idle cleanup rather than racing the
    # session handshake itself.
    manager.session_idle_timeout = 0.25
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            key = "tw_idle_customer"
            session_id = await _initialize_public_session(client, key)
            assert session_id in manager._server_instances
            deadline = asyncio.get_running_loop().time() + 3.0
            while (
                session_id in manager._server_instances
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.02)
            assert session_id not in manager._server_instances
            assert session_id not in manager._session_owners

            expired = await client.post(
                "/",
                headers=_rpc_headers(key, session_id),
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            assert expired.status_code == 404, expired.text

            # Admission derives active ownership from the SDK registry, so idle
            # eviction must restore this same principal's only slot.
            replacement = await _initialize_public_session(client, key)
            deleted = await client.delete(
                "/", headers=_rpc_headers(key, replacement)
            )
            assert deleted.status_code in {200, 204}


# --- streamable HTTP DNS-rebinding allowlists --------------------------------------


def _set_valid_remote_startup_config(monkeypatch):
    monkeypatch.setattr(server, "WORKOS_AUTHKIT_DOMAIN", "https://auth.example.com")
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", "https://mcp.example.com")
    monkeypatch.setattr(server, "MCP_GATEWAY_KEY", "tw_svc_" + "A" * 43)
    monkeypatch.setattr(server, "TRADEWAVE_API_KEY", "")
    monkeypatch.setattr(server, "API_BASE_URL", "http://127.0.0.1:8088/v1")
    monkeypatch.setattr(server, "OAUTH_ENABLED", True)


def test_remote_startup_accepts_only_complete_canonical_oauth_config(monkeypatch):
    _set_valid_remote_startup_config(monkeypatch)
    server._validate_remote_startup_configuration("127.0.0.1", 9090)


@pytest.mark.parametrize(
    ("attribute", "expected_name"),
    [
        ("WORKOS_AUTHKIT_DOMAIN", "WORKOS_AUTHKIT_DOMAIN"),
        ("MCP_PUBLIC_URL", "TW2_MCP_PUBLIC_URL"),
        ("MCP_GATEWAY_KEY", "MCP_GATEWAY_KEY"),
    ],
)
def test_remote_startup_rejects_every_partial_oauth_tuple(
    monkeypatch, attribute, expected_name
):
    _set_valid_remote_startup_config(monkeypatch)
    monkeypatch.setattr(server, attribute, "")

    with pytest.raises(RuntimeError, match=expected_name):
        server._validate_remote_startup_configuration("127.0.0.1", 9090)


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("WORKOS_AUTHKIT_DOMAIN", "http://auth.example.com", "canonical HTTPS origin"),
        ("MCP_PUBLIC_URL", "https://mcp.example.com/path", "canonical HTTPS origin"),
        ("MCP_GATEWAY_KEY", "tw_live_" + "A" * 32, "dedicated tw_svc_ service key"),
    ],
)
def test_remote_startup_rejects_invalid_oauth_values(
    monkeypatch, attribute, value, message
):
    _set_valid_remote_startup_config(monkeypatch)
    monkeypatch.setattr(server, attribute, value)

    with pytest.raises(RuntimeError, match=message):
        server._validate_remote_startup_configuration("127.0.0.1", 9090)


def test_remote_startup_rejects_shared_customer_fallback_key(monkeypatch):
    _set_valid_remote_startup_config(monkeypatch)
    monkeypatch.setattr(server, "TRADEWAVE_API_KEY", "tw_live_" + "B" * 32)

    with pytest.raises(RuntimeError, match="must be unset"):
        server._validate_remote_startup_configuration("127.0.0.1", 9090)


def test_remote_startup_rejects_oauth_construction_drift(monkeypatch):
    _set_valid_remote_startup_config(monkeypatch)
    monkeypatch.setattr(server, "OAUTH_ENABLED", False)

    with pytest.raises(RuntimeError, match="construction does not match"):
        server._validate_remote_startup_configuration("127.0.0.1", 9090)


@pytest.mark.parametrize("bind_host", ["0.0.0.0", "192.168.1.176", "localhost"])
def test_remote_startup_rejects_non_loopback_or_ambiguous_bind(monkeypatch, bind_host):
    _set_valid_remote_startup_config(monkeypatch)

    with pytest.raises(RuntimeError, match="loopback"):
        server._validate_remote_startup_configuration(bind_host, 9090)


@pytest.mark.parametrize(
    "gateway_url",
    [
        "https://api.example.com/v1",
        "http://192.168.1.176:8088/v1",
        "http://127.0.0.1:8088/v1?leak=1",
        "http://user:pass@127.0.0.1:8088/v1",
        "http://localhost:8088/v1",
    ],
)
def test_remote_startup_rejects_noncanonical_or_nonloopback_gateway(
    monkeypatch, gateway_url
):
    _set_valid_remote_startup_config(monkeypatch)
    monkeypatch.setattr(server, "API_BASE_URL", gateway_url)

    with pytest.raises(RuntimeError, match="canonical loopback"):
        server._validate_remote_startup_configuration("127.0.0.1", 9090)

def test_transport_security_derives_host_and_optional_port_from_public_url(monkeypatch):
    monkeypatch.delenv("TW2_MCP_PUBLIC_HOST", raising=False)
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", "https://MCP.Example.com:8443/")

    settings = server._mcp_transport_security("127.0.0.1", 9090)

    assert settings.allowed_hosts[0] == "mcp.example.com:8443"
    assert settings.allowed_origins[0] == "https://mcp.example.com:8443"


def test_transport_security_explicit_host_override_wins(monkeypatch):
    monkeypatch.setenv("TW2_MCP_PUBLIC_HOST", "override.example.com:9443")
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", "https://canonical.example.com")

    settings = server._mcp_transport_security("127.0.0.1", 9090)

    assert settings.allowed_hosts[0] == "override.example.com:9443"
    assert settings.allowed_origins[0] == "https://override.example.com:9443"
    assert "canonical.example.com" not in settings.allowed_hosts


def test_transport_security_uses_dev_fallback_only_without_public_config(monkeypatch):
    monkeypatch.delenv("TW2_MCP_PUBLIC_HOST", raising=False)
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", "")

    settings = server._mcp_transport_security("127.0.0.1", 9090)

    assert settings.allowed_hosts[0] == "mcp-dev.trxstat.com"
    assert settings.allowed_origins[0] == "https://mcp-dev.trxstat.com"


@pytest.mark.parametrize("bad_url", [
    "http://mcp.example.com",
    "https://user@mcp.example.com",
    "https://mcp.example.com/path",
    "https://mcp.example.com?other-host=evil.example",
    "https://bad_host.example",
    "https://mcp.example.com:0",
    "https://mcp.example.com:70000",
    "mcp.example.com",
])
def test_public_url_rejects_unsafe_or_noncanonical_values(monkeypatch, bad_url):
    monkeypatch.delenv("TW2_MCP_PUBLIC_HOST", raising=False)
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", bad_url)

    with pytest.raises(ValueError, match="TW2_MCP_PUBLIC_URL"):
        server._configured_mcp_public_endpoint()


@pytest.mark.parametrize("bad_host", [
    "http://mcp.example.com",
    "https://user@mcp.example.com",
    "mcp.example.com/path",
    "bad_host.example",
    "mcp.example.com:invalid",
])
def test_explicit_public_host_rejects_unsafe_values(monkeypatch, bad_host):
    monkeypatch.setenv("TW2_MCP_PUBLIC_HOST", bad_host)
    monkeypatch.setattr(server, "MCP_PUBLIC_URL", "https://canonical.example.com")

    with pytest.raises(ValueError, match="TW2_MCP_PUBLIC_HOST"):
        server._configured_mcp_public_endpoint()


# --- compare fanout: validation, dedupe, ordering, local + aggregate bounds ----------

@pytest.mark.anyio
async def test_compare_deduplicates_stably_and_caps_local_concurrency(monkeypatch):
    active = 0
    max_active = 0

    async def fake_get(path, params=None):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        symbol = path.rsplit("/", 1)[-1]
        # Deliberately finish out of order; gather must still preserve requested order.
        await asyncio.sleep({"gld": 0.04, "SLV": 0.03, "GDX": 0.02,
                             "AAPL": 0.01, "MSFT": 0.0}[symbol])
        active -= 1
        return {"card": {"bias": "bullish"}, "marker": symbol}

    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.compare_opportunities(
        symbols=[" gld ", "SLV", "GLD", "GDX", "slv", "AAPL", "MSFT"], ctx=None)
    payload = json.loads(out.split("\n\n", 2)[1])
    assert payload["symbols"] == ["gld", "SLV", "GDX", "AAPL", "MSFT"]
    assert [row["marker"] for row in payload["comparison"]] == payload["symbols"]
    assert payload["count"] == 5
    assert 1 < max_active <= server._COMPARE_MAX_CONCURRENCY


@pytest.mark.anyio
async def test_compare_rejects_over_cap_before_gateway(monkeypatch):
    called = False

    async def fake_get(path, params=None):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(server, "_get", fake_get)
    out = await server.compare_opportunities(
        symbols=[f"S{i}" for i in range(server._COMPARE_MAX_SYMBOLS + 1)], ctx=None)
    assert "between 2 and 10" in out
    assert not called


@pytest.mark.anyio
async def test_global_gateway_gate_bounds_aggregate_compare_fanout(monkeypatch):
    active = 0
    max_active = 0

    async def handler(request):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"card": {"bias": "bullish"}}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_gateway_client", client)
    monkeypatch.setattr(server, "_gateway_gate", asyncio.Semaphore(3))
    try:
        outputs = await asyncio.gather(*(server.compare_opportunities(
            symbols=[f"B{batch}_{i}" for i in range(5)],
            ctx=_request_ctx(f"tw_batch_{batch}"),
        ) for batch in range(4)))
    finally:
        await client.aclose()

    assert len(outputs) == 4
    assert max_active == 3


# --- OAuth/JWKS: async, single-flight, and resistant to random-kid refresh floods -----

def _unsigned_rs256_token(kid):
    raw_header = json.dumps({"alg": "RS256", "kid": kid}, separators=(",", ":")).encode()
    header = base64.urlsafe_b64encode(raw_header).rstrip(b"=").decode()
    # All three JWT segments must be valid base64url even though signing_key only reads
    # the unverified header. "e30" is {}, "c2ln" is "sig".
    return f"{header}.e30.c2ln"


@pytest.mark.anyio
async def test_jwks_resolver_loads_and_caches_a_valid_rsa_key(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "active-key", "alg": "RS256", "use": "sig"})
    token = pyjwt.encode({"sub": "user_1"}, private_key, algorithm="RS256",
                         headers={"kid": "active-key"})
    resolver = server._AsyncJwksResolver("https://auth.example")
    jwks_fetches = 0

    async def fake_fetch(url):
        nonlocal jwks_fetches
        jwks_fetches += 1
        return {"keys": [jwk]}

    monkeypatch.setattr(resolver, "_fetch_json", fake_fetch)
    key = await resolver.signing_key(token)
    assert pyjwt.decode(token, key, algorithms=["RS256"])["sub"] == "user_1"
    assert resolver.issuer == "https://auth.example"
    assert await resolver.signing_key(token) is key
    assert jwks_fetches == 1


@pytest.mark.anyio
async def test_oauth_resolver_refuses_any_unpinned_jwks_origin():
    resolver = server._AsyncJwksResolver("https://auth.example")
    assert resolver.issuer == "https://auth.example"
    assert resolver._jwks_uri == "https://auth.example/oauth2/jwks"
    with pytest.raises(ValueError, match="unpinned"):
        await resolver._fetch_json("https://127.0.0.1/private-jwks")


def _mock_oauth_client(resolver, handler):
    transport = httpx.MockTransport(handler)
    resolver._client_factory = lambda **kwargs: httpx.AsyncClient(
        transport=transport, **kwargs
    )


@pytest.mark.anyio
async def test_oauth_fetch_rejects_declared_and_chunked_oversize():
    resolver = server._AsyncJwksResolver("https://auth.example")
    limit = server._OAUTH_JWKS_RESPONSE_MAX_BYTES
    declared_stream = _AsyncChunks(b"{}")

    async def declared_handler(request):
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-length": str(limit + 1),
            },
            stream=declared_stream,
            request=request,
        )

    _mock_oauth_client(resolver, declared_handler)
    with pytest.raises(ValueError, match="oversized"):
        await resolver._fetch_json(resolver._jwks_uri)
    assert not declared_stream.iterated
    assert declared_stream.closed

    chunked_stream = _AsyncChunks(b"x" * limit, b"x")

    async def chunked_handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=chunked_stream,
            request=request,
        )

    _mock_oauth_client(resolver, chunked_handler)
    with pytest.raises(ValueError, match="oversized"):
        await resolver._fetch_json(resolver._jwks_uri)
    assert chunked_stream.iterated
    assert chunked_stream.closed


@pytest.mark.anyio
async def test_oauth_fetch_identity_rejects_gzip_bomb_before_decompression():
    resolver = server._AsyncJwksResolver("https://auth.example")
    compressed = gzip.compress(b"x" * (server._OAUTH_JWKS_RESPONSE_MAX_BYTES * 3))
    stream = _AsyncChunks(compressed)
    observed_accept_encoding = None

    async def handler(request):
        nonlocal observed_accept_encoding
        observed_accept_encoding = request.headers.get("accept-encoding")
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
            },
            stream=stream,
            request=request,
        )

    _mock_oauth_client(resolver, handler)
    with pytest.raises(ValueError, match="encoded"):
        await resolver._fetch_json(resolver._jwks_uri)
    assert observed_accept_encoding == "identity"
    assert not stream.iterated
    assert stream.closed


@pytest.mark.anyio
async def test_oauth_fetch_absolute_deadline_stops_slow_drip(monkeypatch):
    resolver = server._AsyncJwksResolver("https://auth.example")
    stream = _AsyncChunks(b"{", b"}", pause_after_first=0.1)

    async def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=stream,
            request=request,
        )

    _mock_oauth_client(resolver, handler)
    monkeypatch.setattr(server, "_OAUTH_FETCH_DEADLINE", 0.02)
    with pytest.raises(httpx.ReadTimeout, match="absolute deadline"):
        await resolver._fetch_json(resolver._jwks_uri)
    assert stream.iterated
    assert stream.closed


@pytest.mark.anyio
async def test_expired_known_jwks_key_never_regains_validity_during_outage(monkeypatch):
    resolver = server._AsyncJwksResolver("https://auth.example")
    sentinel_key = object()
    resolver._keys = {"formerly-valid": sentinel_key}
    resolver._keys_expires_at = 100.0
    resolver._last_refresh_at = 0.0
    now = 101.0
    fetches = 0

    async def failed_fetch(url):
        nonlocal fetches
        fetches += 1
        raise httpx.ConnectError("issuer unavailable", request=httpx.Request("GET", url))

    monkeypatch.setattr(resolver, "_fetch_json", failed_fetch)
    monkeypatch.setattr(server.time, "monotonic", lambda: now)
    token = _unsigned_rs256_token("formerly-valid")

    with pytest.raises(pyjwt.InvalidTokenError, match="temporarily unavailable"):
        await resolver.signing_key(token)
    assert resolver._keys_expires_at == 100.0
    assert fetches == 1

    # The network retry cooldown cannot extend key validity.
    now = 110.0
    with pytest.raises(pyjwt.InvalidTokenError, match="temporarily unavailable"):
        await resolver.signing_key(token)
    assert resolver._keys_expires_at == 100.0
    assert fetches == 1

    # Even much later, another failed refresh still cannot resurrect the old key.
    now = 100_000.0
    with pytest.raises(pyjwt.InvalidTokenError, match="temporarily unavailable"):
        await resolver.signing_key(token)
    assert resolver._keys_expires_at == 100.0
    assert fetches == 2


@pytest.mark.anyio
async def test_unknown_jwks_kids_singleflight_and_refresh_cooldown(monkeypatch):
    resolver = server._AsyncJwksResolver("https://auth.example")
    jwks_fetches = 0

    async def fake_fetch(url):
        nonlocal jwks_fetches
        await asyncio.sleep(0)
        jwks_fetches += 1
        return {"keys": []}

    monkeypatch.setattr(resolver, "_fetch_json", fake_fetch)
    attempts = await asyncio.gather(*(
        resolver.signing_key(_unsigned_rs256_token("unknown")) for _ in range(20)
    ), return_exceptions=True)
    assert all(isinstance(exc, pyjwt.InvalidTokenError) for exc in attempts)
    assert jwks_fetches == 1

    # A different randomized kid cannot force another upstream fetch during the global
    # refresh cooldown (negative caching alone would not stop this attack pattern).
    with pytest.raises(pyjwt.InvalidTokenError):
        await resolver.signing_key(_unsigned_rs256_token("another-random-kid"))
    assert jwks_fetches == 1

    # Oversized attacker-controlled identifiers/tokens are rejected before any cache or
    # network work, keeping the negative cache's memory use bounded.
    with pytest.raises(pyjwt.InvalidTokenError):
        await resolver.signing_key(_unsigned_rs256_token(
            "x" * (server._OAUTH_KID_MAX_LENGTH + 1)))
    with pytest.raises(pyjwt.InvalidTokenError):
        await resolver.signing_key("x" * (server._OAUTH_TOKEN_MAX_LENGTH + 1))
    assert jwks_fetches == 1
    assert server._OAUTH_HTTP_TIMEOUT <= 3.0


@pytest.mark.anyio
async def test_failed_jwks_refresh_cools_down_random_unknown_kids(monkeypatch):
    """An issuer outage cannot turn randomized kids into one network call each."""
    resolver = server._AsyncJwksResolver("https://auth.example")
    jwks_fetches = 0

    async def failed_fetch(url):
        nonlocal jwks_fetches
        jwks_fetches += 1
        await asyncio.sleep(0)
        request = httpx.Request("GET", url)
        raise httpx.ConnectError("issuer unavailable", request=request)

    monkeypatch.setattr(resolver, "_fetch_json", failed_fetch)
    attempts = await asyncio.gather(*(
        resolver.signing_key(_unsigned_rs256_token(f"random-kid-{i}"))
        for i in range(20)
    ), return_exceptions=True)

    assert all(isinstance(exc, pyjwt.InvalidTokenError) for exc in attempts)
    assert jwks_fetches == 1
    assert resolver._last_refresh_at > 0
    assert len(resolver._unknown_kids) == 20


@pytest.mark.anyio
async def test_jwks_fetch_wait_does_not_block_event_loop(monkeypatch):
    resolver = server._AsyncJwksResolver("https://auth.example")
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch(url):
        started.set()
        await release.wait()
        return {"keys": []}

    monkeypatch.setattr(resolver, "_fetch_json", fake_fetch)
    verification = asyncio.create_task(
        resolver.signing_key(_unsigned_rs256_token("unknown")))
    await asyncio.wait_for(started.wait(), timeout=0.1)
    ticked = asyncio.Event()
    asyncio.get_running_loop().call_soon(ticked.set)
    await asyncio.wait_for(ticked.wait(), timeout=0.1)
    release.set()
    with pytest.raises(pyjwt.InvalidTokenError):
        await verification


# --- published MCP contract: annotations + bounded collection/string schemas ---------

def test_all_tools_are_async_and_publish_safety_annotations():
    read_only = {
        "explain_pick", "list_markets", "whoami", "describe_tradewave", "list_symbols",
        "get_symbol_patterns", "get_seasonal_pattern", "get_opportunity_chart",
        "get_daily_pick", "get_pick_track_record",
    }
    metered = {
        "find_best_opportunities", "analyze_symbol", "morning_briefing",
        "whats_seasonal_now", "compare_opportunities", "get_seasonal_opportunities",
        "score_opportunities",
    }
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    assert set(tools) == read_only | metered
    for name, tool in tools.items():
        assert tool.is_async, name
        annotations = tool.annotations
        assert annotations is not None
        assert annotations.readOnlyHint is (name in read_only)
        assert annotations.destructiveHint is False
        assert annotations.openWorldHint is False
        assert annotations.idempotentHint is (name in read_only)


def _walk_schema(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_schema(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_schema(value)


def test_all_public_string_and_array_inputs_are_bounded():
    tools = server.mcp._tool_manager.list_tools()
    for tool in tools:
        for node in _walk_schema(tool.parameters):
            if node.get("type") == "string":
                assert "maxLength" in node, f"{tool.name}: unbounded string schema {node}"
            if node.get("type") == "array":
                assert "maxItems" in node, f"{tool.name}: unbounded array schema {node}"

    compare = server.mcp._tool_manager.get_tool("compare_opportunities").parameters
    compare_symbols = compare["properties"]["symbols"]
    assert compare_symbols["minItems"] == 2
    assert compare_symbols["maxItems"] == 10
    assert compare_symbols["items"]["maxLength"] == 64

    score = server.mcp._tool_manager.get_tool("score_opportunities").parameters
    score_items = score["properties"]["opportunities"]
    assert score_items["minItems"] == 1
    assert score_items["maxItems"] == 100


def _resolved_schema(root, node):
    while isinstance(node, dict) and "$ref" in node:
        target = root
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        node = target
    if isinstance(node, dict) and "anyOf" in node:
        variants = [item for item in node["anyOf"] if item.get("type") != "null"]
        assert len(variants) == 1
        return _resolved_schema(root, variants[0])
    return node


def test_public_enums_are_canonical_and_ml_market_is_not_aliasable():
    expected = {
        "find_best_opportunities": {
            "direction": ["long", "short"],
            "pe_cycle": ["consecutive", "pe"],
            "rank_by": ["edge", "win_rate", "sharpe", "ml", "avg_return"],
            "view": ["decision", "table", "full"],
        },
        "analyze_symbol": {
            "direction": ["long", "short"],
            "pe_cycle": ["consecutive", "pe"],
            "period": [
                "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                "oct", "nov", "dec", "q1", "q2", "q3", "q4", "spring", "summer",
                "fall", "winter", "ytd", "year_end", "buy_hold",
            ],
            "view": ["decision", "table", "full"],
        },
        "whats_seasonal_now": {"view": ["decision", "table", "full"]},
        "compare_opportunities": {"view": ["decision", "table", "full"]},
        "get_seasonal_opportunities": {
            "direction": ["long", "short"], "pe_cycle": ["consecutive", "pe"],
        },
        "get_symbol_patterns": {"pe_cycle": ["consecutive", "pe"]},
        "get_seasonal_pattern": {
            "pe_cycle": ["consecutive", "pe", "pe0", "pe1", "pe2", "pe3"],
        },
        "get_opportunity_chart": {
            "direction": ["long", "short"],
            "pe_cycle": ["consecutive", "pe", "pe0", "pe1", "pe2", "pe3"],
        },
        "score_opportunities": {"market": ["0", "1", "2", "3", "4", "11"]},
    }
    period = expected["analyze_symbol"]["period"]
    expected["get_seasonal_pattern"]["period"] = period
    expected["get_opportunity_chart"]["period"] = period

    for tool_name, fields in expected.items():
        root = server.mcp._tool_manager.get_tool(tool_name).parameters
        for field, enum in fields.items():
            schema = _resolved_schema(root, root["properties"][field])
            assert schema["enum"] == enum, f"{tool_name}.{field}"

    score = server.mcp._tool_manager.get_tool("score_opportunities").parameters
    item = _resolved_schema(score, score["properties"]["opportunities"])["items"]
    item = _resolved_schema(score, item)
    direction = _resolved_schema(score, item["properties"]["direction"])
    assert direction["enum"] == ["long", "short"]


def test_public_numeric_ranges_and_safe_symbol_page_are_frozen():
    expected = {
        "find_best_opportunities": {
            "min_win_rate": (0, 1), "min_years": (1, 99),
            "min_days": (1, 366), "max_days": (1, 366), "years": (1, 99),
            "min_winning_years": (0, 99), "limit": (1, 100),
        },
        "analyze_symbol": {"days_out": (1, 366), "years": (1, 99)},
        "whats_seasonal_now": {"min_win_rate": (0, 1)},
        "list_symbols": {"limit": (1, 1000)},
        "get_seasonal_opportunities": {
            "min_win_rate": (0, 1), "min_days": (1, 366), "max_days": (1, 366),
            "years": (1, 99), "min_winning_years": (0, 99), "limit": (1, 100),
        },
        "get_symbol_patterns": {
            "years": (1, 99), "min_winning_years": (0, 99),
            "min_days": (1, 366), "max_days": (1, 366),
        },
        "get_seasonal_pattern": {"years": (1, 99)},
        "get_opportunity_chart": {"days_out": (1, 366)},
    }
    for tool_name, fields in expected.items():
        root = server.mcp._tool_manager.get_tool(tool_name).parameters
        for field, bounds in fields.items():
            schema = _resolved_schema(root, root["properties"][field])
            assert (schema["minimum"], schema["maximum"]) == bounds, f"{tool_name}.{field}"

    symbols = server.mcp._tool_manager.get_tool("list_symbols").parameters
    assert _resolved_schema(symbols, symbols["properties"]["prefix"])["maxLength"] == 15
    chart = server.mcp._tool_manager.get_tool("get_opportunity_chart").parameters
    years = _resolved_schema(chart, chart["properties"]["years"])
    assert years["pattern"] == r"^(?:[1-9]|[1-9]\d)$"
