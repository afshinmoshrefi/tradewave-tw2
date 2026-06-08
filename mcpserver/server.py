"""
TradeWave MCP server - thin wrapper over the v1 HTTP gateway.

Each tool calls the corresponding /v1 endpoint via httpx. Authentication is
bring-your-own-key (BYOK) and resolved PER CALL:

  1. The API key from the INCOMING MCP request's `Authorization: Bearer <key>`
     header, if present (remote transports - sse, streamable-http). Each
     connection thus acts as its own customer; one remote server serves many.
  2. Otherwise the env var TRADEWAVE_API_KEY (stdio - each user runs their own
     local server with their own key).
  3. Otherwise no auth is sent (the gateway returns 401 - correct BYOK).

No data logic lives here; the gateway enforces all tier/signal rules.

Transport:
  - stdio  (default, for Claude Desktop / local CLI)
  - sse    (pass --transport sse --port <n> for remote use)
  - streamable-http  (pass --transport streamable-http)

Run (stdio, key from env):
  TRADEWAVE_API_KEY=tw_... ./venv-api/bin/python -m mcpserver.server

Run (SSE, remote, NO baked-in key - each client sends its own Bearer token):
  ./venv-api/bin/python -m mcpserver.server --transport sse --port 9090
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import Context, FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"

API_BASE_URL: str = os.environ.get("API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
TRADEWAVE_API_KEY: str = os.environ.get("TRADEWAVE_API_KEY", "")

import logging

log = logging.getLogger("mcpserver")

# --- WorkOS OAuth (consumer connect via ChatGPT/Claude) - docs/MCP_OAUTH_INTEGRATION.md ---
# This MCP server is an OAuth 2.1 RESOURCE server. WorkOS AuthKit (WORKOS_AUTHKIT_DOMAIN, already
# set per-env for the web tier) is the authorization server. We validate its JWTs and, for an OAuth
# principal, call the gateway AS that user (mcp service key + X-TW-Principal-WorkOS). OAuth turns ON
# only when fully configured; otherwise the server stays BYOK-only (dev/stdio/dev-tools).
WORKOS_AUTHKIT_DOMAIN: str = (os.environ.get("WORKOS_AUTHKIT_DOMAIN", "") or "").rstrip("/")
MCP_PUBLIC_URL: str = (os.environ.get("TW2_MCP_PUBLIC_URL", "") or "").rstrip("/")  # canonical resource / token audience
MCP_GATEWAY_KEY: str = os.environ.get("MCP_GATEWAY_KEY", "")
OAUTH_ENABLED: bool = bool(WORKOS_AUTHKIT_DOMAIN and MCP_PUBLIC_URL and MCP_GATEWAY_KEY)

# ---------------------------------------------------------------------------
# Per-connection auth (BYOK)
# ---------------------------------------------------------------------------
#
# For remote transports (sse, streamable-http) the SDK plumbs the incoming
# Starlette Request through to the tool's RequestContext (ctx.request_context.
# request). We extract that connection's `Authorization: Bearer <key>` and
# stash it in a ContextVar so the shared _get/_post helpers can forward it
# without threading the key through every signature. A ContextVar set in ASGI
# middleware would NOT survive the SSE anyio-stream task hop, so we resolve the
# key from the SDK-provided Request at tool-call time instead.
#
# For stdio there is no HTTP request (ctx.request_context.request is None), so
# we fall back to the env var TRADEWAVE_API_KEY.

from contextvars import ContextVar

# The resolved principal for this call: {"mode":"oauth","sub":<workos_sub>} (consumer apps via
# WorkOS), {"mode":"byok","key":<tw_ key>} (dev tools), or None.
_request_principal: ContextVar[Optional[dict]] = ContextVar("_request_principal", default=None)


if OAUTH_ENABLED:
    import jwt as _jwt
    from mcp.server.auth.provider import AccessToken, TokenVerifier

    class WorkOSTokenVerifier(TokenVerifier):
        """Resource-server token validation. Accepts BOTH a WorkOS OAuth JWT (consumer apps:
        verified against the AuthKit JWKS, audience-bound to our MCP URL, exp-checked) and a tw_
        API key (dev tools / BYOK: format-accepted here, the gateway is the source of truth and
        validates it on the actual call) - so the two coexist behind the SDK auth gate."""

        def __init__(self) -> None:
            # RFC 8414 discovery: prefer the AS metadata's real issuer + jwks_uri; fall back to the
            # documented WorkOS endpoints. Done once at startup.
            self._issuer = WORKOS_AUTHKIT_DOMAIN
            jwks_uri = WORKOS_AUTHKIT_DOMAIN + "/oauth2/jwks"
            try:
                meta = httpx.get(WORKOS_AUTHKIT_DOMAIN + "/.well-known/oauth-authorization-server",
                                 timeout=5).json()
                self._issuer = meta.get("issuer") or self._issuer
                jwks_uri = meta.get("jwks_uri") or jwks_uri
            except Exception as e:  # noqa: BLE001 - best-effort discovery
                log.warning("MCP OAuth: AS metadata discovery failed (%s); using defaults", e)
            self._jwks = _jwt.PyJWKClient(jwks_uri)
            log.info("MCP OAuth ENABLED: issuer=%s audience=%s", self._issuer, MCP_PUBLIC_URL)

        async def verify_token(self, token: str):
            if not token:
                return None
            if token.startswith("tw_"):          # BYOK / dev tools - gateway validates the key
                return AccessToken(token=token, client_id="byok", scopes=[], expires_at=None,
                                   resource=MCP_PUBLIC_URL, subject="byok",
                                   claims={"mode": "byok", "key": token})
            try:                                  # WorkOS OAuth JWT - verify sig + aud + exp strictly
                key = self._jwks.get_signing_key_from_jwt(token).key
                # Accept the audience with or without a trailing slash: the SDK advertises the
                # resource as "<url>/" while the WorkOS resource indicator is often registered as
                # "<url>" - tolerate both so a slash can't silently break the connect.
                aud = [MCP_PUBLIC_URL, MCP_PUBLIC_URL + "/"]
                claims = _jwt.decode(token, key, algorithms=["RS256"], audience=aud,
                                     issuer=self._issuer, options={"require": ["exp", "sub"]})
            except Exception as e:                # noqa: BLE001 - any failure => unauthenticated
                log.warning("MCP OAuth: token verification failed: %s", e)
                return None
            sub = claims.get("sub")
            if not sub:
                return None
            scope = claims.get("scope", "")
            exp = claims.get("exp")
            return AccessToken(token=token, client_id=claims.get("client_id", ""),
                               scopes=scope.split() if isinstance(scope, str) else [],
                               expires_at=int(exp) if exp is not None else None,
                               resource=MCP_PUBLIC_URL, subject=sub,
                               claims={"mode": "oauth", "workos_sub": sub})


def _bearer_from_request(ctx: Optional[Context]) -> Optional[str]:
    """Extract the Bearer token from the incoming MCP request, if any.

    Returns the raw key for remote transports (sse / streamable-http) where the
    SDK exposes the Starlette Request on the RequestContext. Returns None for
    stdio (no HTTP request) or when no usable Authorization header is present.
    """
    if ctx is None:
        return None
    try:
        request = ctx.request_context.request
    except (LookupError, AttributeError, ValueError):
        # No active request context (e.g. stdio, or a direct in-process call) - the SDK
        # raises ValueError("Context is not available outside of a request"); treat all of
        # these as "no HTTP request" and fall back to the env key.
        return None
    if request is None:
        return None
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def _bind_request_key(ctx: Optional[Context]) -> None:
    """Resolve this call's principal into the ContextVar. With OAuth ON, read the token the SDK
    already validated (get_access_token) and route by its mode; otherwise fall back to the BYOK
    header / env key. Each tool calls this once at entry."""
    if OAUTH_ENABLED:
        at = None
        try:
            from mcp.server.auth.middleware.auth_context import get_access_token
            at = get_access_token()
        except Exception:
            at = None
        claims = (at.claims if at is not None else None) or {}
        if claims.get("mode") == "oauth" and claims.get("workos_sub"):
            _request_principal.set({"mode": "oauth", "sub": claims["workos_sub"]})
        elif claims.get("mode") == "byok" and claims.get("key"):
            _request_principal.set({"mode": "byok", "key": claims["key"]})
        else:
            _request_principal.set(None)
        return
    key = _bearer_from_request(ctx) or (TRADEWAVE_API_KEY or None)
    _request_principal.set({"mode": "byok", "key": key} if key else None)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    """Auth headers for the gateway call. OAuth principal -> the mcp service key + the WorkOS
    subject (the gateway resolves it to the user's real tier); BYOK -> the user's own key."""
    h: dict[str, str] = {"Accept": "application/json"}
    p = _request_principal.get() or {}
    if p.get("mode") == "oauth" and p.get("sub"):
        h["Authorization"] = f"Bearer {MCP_GATEWAY_KEY}"
        h["X-TW-Principal-WorkOS"] = p["sub"]
    elif p.get("mode") == "byok" and p.get("key"):
        h["Authorization"] = f"Bearer {p['key']}"
    return h


def _seg(value: Any) -> str:
    """URL-encode a value used as a PATH segment (symbol/market), so a symbol with a '.', '/',
    space, or other special char can't corrupt the path or inject extra segments."""
    from urllib.parse import quote
    return quote(str(value), safe="")


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Synchronous GET against the gateway. Returns parsed JSON."""
    url = f"{API_BASE_URL}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, params={k: v for k, v in (params or {}).items() if v is not None}, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: Any) -> Any:
    """Synchronous POST against the gateway. Returns parsed JSON."""
    url = f"{API_BASE_URL}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=body, headers={**_headers(), "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


def _format_upgrade(data: dict[str, Any]) -> str:
    """Return a clear upgrade message from an UpgradeRequired or ml_daily_limit stub.

    Handles two stub shapes:
      {requires:"pro", ...}                     - feature requires Pro subscription
      {requires:"upgrade", reason:"ml_daily_limit", ...}  - daily ML allowance spent
    Both surface as a clear human message with an upgrade link, never as an error.
    ml_remaining_today is shown when present (None = unlimited, 0 = limit reached).
    """
    reason = data.get("reason", "")
    msg = data.get("message", "")
    url = data.get("upgrade_url", "https://tradewave.ai/upgrade")
    remaining = data.get("ml_remaining_today")

    if reason == "ml_daily_limit" or data.get("requires") == "upgrade":
        remaining_str = ""
        if remaining is not None:
            remaining_str = f" (ML calls remaining today: {remaining})"
        if not msg:
            msg = "You have reached your daily ML scoring limit. Upgrade for unlimited ML scoring."
        return f"Daily ML limit reached on your plan - {msg}{remaining_str}\nUpgrade at: {url}"

    if not msg:
        msg = "This feature requires a Pro subscription."
    return f"Upgrade required - {msg}\nUpgrade at: {url}"


def _is_upgrade_stub(data: Any) -> bool:
    return isinstance(data, dict) and (
        data.get("requires") == "pro"
        or data.get("requires") == "upgrade"
    )


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

_auth_kwargs: dict[str, Any] = {}
if OAUTH_ENABLED:
    from mcp.server.auth.settings import AuthSettings
    _auth_kwargs = {
        "token_verifier": WorkOSTokenVerifier(),
        "auth": AuthSettings(issuer_url=WORKOS_AUTHKIT_DOMAIN, resource_server_url=MCP_PUBLIC_URL),
    }

mcp = FastMCP(
    name="TradeWave",
    **_auth_kwargs,
    instructions=(
        "TradeWave is the user's seasonal-edge analyst. It finds, ranks, and explains "
        "derived seasonal trade setups (backed by ML win-probability scores) across 17 global "
        "markets. All returns are percentages - no raw prices are ever exposed.\n\n"
        "REACH FOR THE FLAGSHIP TOOLS FIRST - they return ready, evidence-backed answers as "
        "structured SignalCards (headline + verdict + receipts + a ready-to-place order ticket):\n"
        "  - find_best_opportunities: 'what should I trade', 'find me something', 'anything "
        "seasonal in gold/energy', a ranked scan across markets.\n"
        "  - whats_seasonal_now: 'what is entering its window this week', the weekly digest.\n"
        "  - analyze_symbol: a full deep-dive on ONE ticker in a single call.\n"
        "  - compare_opportunities: rank several tickers side-by-side.\n"
        "  - explain_pick: today's AI daily pick WITH its live forward-tested track record.\n\n"
        "The other tools are low-level primitives - prefer the flagships unless you need one "
        "exact slice (e.g. the raw normalized seasonal curve to chart). The gateway is the one "
        "source of truth: present its SignalCards, do not recompute or re-rank them.\n\n"
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "When the daily ML allowance is spent the gateway returns a graceful nudge "
        "(requires='upgrade', reason='ml_daily_limit') - surface this as "
        "'daily ML limit reached - upgrade for unlimited' and include ml_remaining_today if "
        "present. Never surface it as an error.\n\n"
        "RESEARCH METHOD - you are more than a TradeWave reader. TradeWave gives the SEASONAL + ML "
        "statistical edge; it is BLIND to fundamentals, news, macro, valuation, and upcoming "
        "earnings. The high-value workflow: (1) EDGE - get TradeWave's seasonal/ML read; (2) EXTEND "
        "- use YOUR OWN tools (web/news/fundamentals/macro) to check whether the current story "
        "SUPPORTS or THREATENS that seasonal thesis (search; never assume or fabricate a catalyst); "
        "(3) loop back to TradeWave for more when it changes the answer (detail receipts, peer "
        "comparison, the live track record); (4) SYNTHESIZE one view, keeping explicit which facts "
        "are TradeWave's data vs your own research. Three DISTINCT win rates appear and must NEVER "
        "be conflated: historical_win_rate (seasonal, in-sample), ml_win_prob (the ML model, "
        "per-instance), track_record.win_rate (LIVE, forward-tested). Call describe_tradewave for "
        "the full method + glossary."
    ),
)


def _extract_disclaimer(obj: Any) -> Optional[str]:
    """Recursively pop every identical 'disclaimer' field out of the payload and
    return the first one, so the MCP transport carries the regulator disclaimer
    ONCE in the envelope instead of repeating it verbatim on every card (a large
    token saving on multi-card scans). The gateway HTTP contract is unchanged - it
    still stamps each card (cards.DISCLAIMER); this de-dupe is MCP-transport only."""
    found = None
    if isinstance(obj, dict):
        d = obj.pop("disclaimer", None)
        if isinstance(d, str) and d:
            found = d
        for v in obj.values():
            r = _extract_disclaimer(v)   # ALWAYS recurse so every nested copy is popped
            if r is not None and found is None:
                found = r
    elif isinstance(obj, list):
        for v in obj:
            r = _extract_disclaimer(v)
            if r is not None and found is None:
                found = r
    return found


# Epistemic research hand-off, appended after CARD-BEARING responses only (never on
# primitives like whoami/list_markets). TradeWave's polished verdict otherwise reads as a
# "finished answer" = the strongest "stop here" signal; this converts it into "now go
# confirm this with your own tools," and blocks the two default failure modes - the model
# fabricating a catalyst, or laundering a NO_SIGNAL coin-flip into "mild support."
_HANDOFF = (
    "Research hand-off: this is a SEASONAL + ML statistical edge ONLY. TradeWave is BLIND to "
    "fundamentals, news, macro, valuation, and upcoming earnings/events. Before treating it as a "
    "complete view, use your OWN tools to check whether current news, macro, or recent price action "
    "SUPPORT or THREATEN this seasonal thesis - search for them; do NOT assume a catalyst exists and "
    "do NOT invent one. If TradeWave reports NO_SIGNAL / no edge, report that as a genuine 'no edge' "
    "finding (computed independently of any news), not as mild support. Then synthesize, keeping "
    "explicit which facts are TradeWave's data vs your own research; if you can't verify it, say so."
)


def _lead(text: str, data: Any, handoff: bool = False) -> str:
    """Prepend a one-line conversational lead to the gateway's structured JSON.

    The gateway's SignalCard JSON is the source of truth and is returned verbatim
    (json.dumps), except the repeated per-card 'disclaimer' is hoisted to a single
    envelope line (see _extract_disclaimer). The lead is a single human sentence
    for the model to open with; it never reshapes the structured payload.

    handoff=True (card-bearing flagships only) appends the epistemic research hand-off
    after the payload, so the model extends the research instead of stopping at the card.
    """
    disclaimer = _extract_disclaimer(data)
    out = f"{text}\n\n{json.dumps(data, separators=(',', ':'))}"
    if handoff:
        out += f"\n\n{_HANDOFF}"
    if disclaimer:
        out += f"\n\nDisclaimer: {disclaimer}"
    return out


def _present_cards(data: Any, empty_msg: str, found_msg) -> str:
    """Pass through a SignalCard list/payload, gracefully handling Pro stubs + empties.

    - UpgradeRequired stub -> clear Pro-required message + upgrade_url (never an error).
    - Otherwise prepend a one-line lead and forward the structured JSON unchanged.
    """
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    if isinstance(data, dict):
        count = data.get("count")
        if count == 0 or (count is None and not data.get("opportunities")):
            return _lead(empty_msg, data)
    return _lead(found_msg(data) if callable(found_msg) else found_msg, data, handoff=True)


# ===========================================================================
# FLAGSHIP TOOLS - reach for these first. Each forwards the gateway's
# SignalCards (the one source of truth) with a short conversational lead.
# ===========================================================================

# ---------------------------------------------------------------------------
# Flagship: find_best_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "THE flagship 'what should I trade right now' tool. Scan across markets, rank every "
        "seasonal setup by Sharpe ratio (mirroring TradeWave's own daily-pick selection: "
        "filter then rank by Sharpe), and return ready, evidence-backed SignalCards "
        "(headline + verdict + receipts + a copyable order ticket). "
        "REACH FOR THIS FIRST whenever the user asks 'find me a trade', 'what's good right now', "
        "'anything seasonal in gold / energy / tech', 'best setups this month', or wants a ranked "
        "shortlist - it replaces stitching list_markets + get_seasonal_opportunities yourself. "
        "Scans the caller's in-scope markets by default; narrow with `markets`. Honest by design: "
        "weak setups come back as NO_SIGNAL rather than a manufactured trade. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "Present the returned cards as-is; the gateway has already sorted them by rank. "
        "Progressive disclosure: each card defaults to the lean DECISION view (signal + verdict + "
        "timing + edge + the extend_research hand-off). Pass view='table' for a compact ranked "
        "list, or view='full' when you need the per-year receipts and detail stats."
    )
)
def find_best_opportunities(
    markets: Optional[str] = None,
    window: Optional[str] = None,
    direction: Optional[str] = None,
    min_win_rate: Optional[float] = None,
    min_years: Optional[int] = None,
    min_days: Optional[int] = None,
    max_days: Optional[int] = None,
    min_avg_return: Optional[float] = None,
    min_median_return: Optional[float] = None,
    min_sharpe: Optional[float] = None,
    pe_cycle: Optional[str] = None,
    years: Optional[int] = None,
    min_winning_years: Optional[int] = None,
    rank_by: Optional[str] = None,
    limit: Optional[int] = None,
    view: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        markets: CSV of market ids or names to scan, e.g. '2,11' or 'gold,energy'. Optional - omit to scan ALL in-scope markets.
        pe_cycle: Presidential election cycle mode for the opportunity table: 'consecutive' (default, consecutive years) or 'pe' (the current presidential-cycle position only). Optional.
        years: Lookback - how many years to scan for patterns (5-98, data-dependent; default 10). In PE mode this is the number of PE-position occurrences. Optional.
        min_winning_years: Of those `years`, the minimum that must be WINNERS - i.e. the win-rate floor (year2). DEFAULTS to ~90% of `years` (so a bare years=20 gives a valid 20-18; you rarely need to set it). It must stay inside the market's DETECTION BAND: TradeWave only detects patterns that won a market-specific share of years (about 75-90%+, e.g. S&P 500 ~85%, Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback). An out-of-band value like 20-9 is REJECTED with the valid range - never lower it below the floor. This is a multi-market scan, so if a value is out of band for some scanned markets the response includes a lookback_note naming them. Optional.
        window: Entry-date window: 'now' (default - setups entering in the next ~10 trading days), 'next_2_weeks', 'next_month', or a 'YYYY-MM-DD..YYYY-MM-DD' range.
        direction: 'long' or 'short'. Optional - omit for both.
        min_win_rate: Minimum historical_win_rate 0..1 (share of profitable years), e.g. 0.65. Optional.
        min_years: Trust filter - require at least N years of tested history. Optional.
        min_days: Minimum pattern length (holding period) in calendar days, e.g. 10. Optional.
        max_days: Maximum pattern length (holding period) in calendar days, e.g. 90. Optional. Use min_days+max_days for a day RANGE like 10-90.
        min_avg_return: Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%). Optional.
        min_median_return: Minimum median seasonal profit in PERCENT. Optional.
        min_sharpe: Minimum Sharpe ratio, e.g. 1.5. Optional.
        rank_by: Ranking method. Default 'sharpe' (mirrors TradeWave's daily-pick selection). Options: edge|win_rate|sharpe|ml|avg_return.
        limit: Max cards to return (tier-capped to the caller's opp_limit). Optional.
        view: Verbosity. 'decision' (default) = the lean read per card; 'table' = a compact ranked row per setup; 'full' = the complete card incl. per-year receipts and detail stats. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"view": view or "decision"}
    if markets is not None:
        params["markets"] = markets
    if window is not None:
        params["window"] = window
    if direction is not None:
        params["direction"] = direction
    if min_win_rate is not None:
        params["min_win_rate"] = min_win_rate
    if min_years is not None:
        params["min_years"] = min_years
    if min_days is not None:
        params["min_days"] = min_days
    if max_days is not None:
        params["max_days"] = max_days
    if min_avg_return is not None:
        params["min_avg_return"] = min_avg_return
    if min_median_return is not None:
        params["min_median_return"] = min_median_return
    if min_sharpe is not None:
        params["min_sharpe"] = min_sharpe
    if pe_cycle is not None:
        params["pe_cycle"] = pe_cycle
    if years is not None:
        params["years"] = years
    if min_winning_years is not None:
        params["min_winning_years"] = min_winning_years
    if rank_by is not None:
        params["rank_by"] = rank_by
    if limit is not None:
        params["limit"] = limit
    data = _get("/scan", params)

    def _found(d: Any) -> str:
        n = d.get("count") if isinstance(d, dict) else None
        win = d.get("window") if isinstance(d, dict) else None
        by = d.get("rank_by", "edge") if isinstance(d, dict) else "edge"
        where = f" entering its {win} window" if win == "now" else (f" for {win}" if win else "")
        return f"Found {n} ranked seasonal setup(s){where}, sorted by {by}. Top of the list first:"

    return _present_cards(
        data,
        empty_msg="No high-conviction seasonal setups matched those filters right now. "
                  "Try widening the markets, the window, or lowering min_win_rate.",
        found_msg=_found,
    )


# ---------------------------------------------------------------------------
# Flagship: analyze_symbol
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "The bundled deep-dive on ONE ticker - one call, the full evidence-backed answer. "
        "Returns a single rich SignalCard (best setup + verdict + receipts + order ticket) plus "
        "the symbol's other setups, fused server-side so the win rate is consistent everywhere. "
        "REACH FOR THIS whenever the user names a specific symbol - 'what about GLD', 'analyze "
        "AAPL's seasonality', 'is now a good time for SPY', 'does CL have an edge'. "
        "It replaces stitching get_symbol_patterns + get_seasonal_pattern + the chart. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro), "
        "on eligible markets (0-4, 11). "
        "If the symbol has no real seasonal edge it returns NO_SIGNAL with an honest verdict. "
        "The card carries an extend_research block telling you exactly how to extend it with your "
        "OWN news / fundamentals / earnings tools. Defaults to the lean DECISION view; pass "
        "view='full' for the per-year receipts, or include_chart=true to also get the Trend Chart "
        "curve + per-year bars inline (chart DATA you draw; never an image)."
    )
)
def analyze_symbol(
    symbol: str,
    market: Optional[str] = None,
    direction: Optional[str] = None,
    days_out: Optional[int] = None,
    entry_date: Optional[str] = None,
    pe_cycle: Optional[str] = None,
    years: Optional[int] = None,
    period: Optional[str] = None,
    reverse: Optional[bool] = None,
    view: Optional[str] = None,
    include_chart: Optional[bool] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        symbol: Ticker symbol, e.g. 'GLD', 'AAPL', 'CL'. Required.
        market: Market id ('0'..'16'). Optional - the gateway resolves it when the symbol is unique.
        direction: 'long' or 'short'. Optional - omit to let the best setup decide.
        days_out: Preferred holding period in calendar days. With entry_date, PINS the exact window;
            without it, biases setup selection. Optional.
        entry_date: 'YYYY-MM-DD'. PIN analysis to THIS exact opportunity (the "click this one /
            deep-dive THIS setup" flow) instead of auto-picking the best. Optional.
        pe_cycle: 'consecutive' (default) or 'pe' - score the setup over presidential-election-cycle
            years (same phase as the entry year) instead of consecutive years. Optional.
        years: Lookback length 1-99 (default 10) - how many years of history to score against. Optional.
        period: A wave-viewer date-range preset to pin the window: a month ('jan'..'dec'), quarter
            ('q1'..'q4'), season ('spring','summer','fall','winter'), or 'ytd'/'year_end'/'buy_hold'.
            Optional - overrides entry_date/days_out when set.
        reverse: Invert the period to "all of the year EXCEPT that window" (the reverse-date-range
            toggle). Optional.
        view: Verbosity. 'decision' (default) = the lean read; 'full' = the complete card incl. per-year receipts and detail stats; 'table' = a single compact row. Optional.
        include_chart: If true, attach the Trend Chart curve (0-100 seasonal index) + per-year bars (each year's return with its favorable/adverse excursion band) inline as chart DATA. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"view": view or "decision"}
    if include_chart:
        params["include"] = "chart"
    if market is not None:
        params["market"] = market
    if direction is not None:
        params["direction"] = direction
    if days_out is not None:
        params["days_out"] = days_out
    if entry_date is not None:
        params["entry_date"] = entry_date
    if pe_cycle is not None:
        params["pe_cycle"] = pe_cycle
    if years is not None:
        params["years"] = years
    if period is not None:
        params["period"] = period
    if reverse is not None:
        params["reverse"] = str(reverse).lower()
    data = _get(f"/analyze/{_seg(symbol)}", params)
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    sym = symbol.upper()
    card = data.get("card") if isinstance(data, dict) else None
    if isinstance(card, dict) and card.get("signal") == "NO_SIGNAL":
        return _lead(
            f"{sym} has no high-conviction seasonal edge right now - here is the honest read:",
            data,
            handoff=True,
        )
    return _lead(f"Here is the full seasonal deep-dive on {sym}:", data, handoff=True)


# ---------------------------------------------------------------------------
# Flagship: explain_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Today's AI daily pick presented as a full SignalCard WITH its live, forward-tested "
        "track record - the strongest proof TradeWave can offer (the pick is made in advance, "
        "then scored later, so the record is real out-of-sample performance, not a backtest). "
        "REACH FOR THIS when the user asks for 'today's pick', 'the trade of the day', 'what is "
        "the AI recommending', or wants to see proof the signals work before trusting them. "
        "Present the pick alongside its receipts (count of past picks, realized win rate, avg "
        "return) as forward-tested evidence. Two DISTINCT win rates appear: the card's "
        "historical_win_rate is the SEASONAL history (share of past years the window was "
        "profitable); track_record.win_rate is the LIVE, out-of-sample record of past daily "
        "picks. They are not the same number - don't conflate them."
    )
)
def explain_pick(ctx: Optional[Context] = None) -> str:
    _bind_request_key(ctx)
    data = _get("/daily-pick")
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    return _lead(
        "Here is today's TradeWave daily pick with its live forward-tested track record. "
        "Note the two distinct win rates: the card's historical_win_rate is the SEASONAL "
        "history (share of past years the window was profitable); track_record.win_rate is "
        "the LIVE, out-of-sample record of past daily picks. Don't conflate them.",
        data,
        handoff=True,
    )


# ---------------------------------------------------------------------------
# Flagship: whats_seasonal_now
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "The 'what is entering its seasonal window THIS WEEK' tool - the weekly digest. "
        "A focused scan of setups whose entry date falls within the next ~10 trading days, "
        "returned as ranked SignalCards. "
        "REACH FOR THIS on calendar-framed prompts: 'what's seasonal right now', 'anything "
        "opening this week', 'what should I be watching this week', the weekly digest. "
        "(It is a focused 'now'-window view of the scanner.) "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "Weak setups come back as NO_SIGNAL. Cards default to the lean DECISION view; pass "
        "view='table' for a compact ranked list or view='full' for receipts."
    )
)
def whats_seasonal_now(
    markets: Optional[str] = None,
    min_win_rate: Optional[float] = None,
    view: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        markets: CSV of market ids or names to scan, e.g. '2,11' or 'gold,energy'. Optional - omit to scan ALL in-scope markets.
        min_win_rate: Minimum historical_win_rate 0..1 (share of profitable years). Optional.
        view: Verbosity. 'decision' (default) = lean read; 'table' = compact ranked rows; 'full' = full cards. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"window": "now", "view": view or "decision"}
    if markets is not None:
        params["markets"] = markets
    if min_win_rate is not None:
        params["min_win_rate"] = min_win_rate
    data = _get("/scan", params)

    def _found(d: Any) -> str:
        n = d.get("count") if isinstance(d, dict) else None
        return f"{n} seasonal setup(s) are entering their window in the next ~2 weeks, ranked by edge:"

    return _present_cards(
        data,
        empty_msg="Nothing high-conviction is entering its seasonal window this week. "
                  "Try whats_seasonal_now with a wider market set, or find_best_opportunities "
                  "with a longer window.",
        found_msg=_found,
    )


# ---------------------------------------------------------------------------
# Flagship: compare_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Compare several tickers side-by-side as seasonal trades. Runs a full deep-dive on each "
        "symbol and returns their SignalCards together so they can be ranked head-to-head. "
        "REACH FOR THIS whenever the user names two or more symbols to weigh - 'GLD vs SLV', "
        "'compare AAPL, MSFT and NVDA seasonally', 'which of these has the better setup'. "
        "Each card carries its own edge score, win rate, and receipts; present them as a "
        "comparison and call out which has the strongest, most consistent edge. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro), "
        "on eligible markets."
    )
)
def compare_opportunities(
    symbols: list[str],
    market: Optional[str] = None,
    view: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        symbols: List of ticker symbols to compare, e.g. ['GLD', 'SLV', 'GDX']. Required, 2 or more.
        market: Market id ('0'..'16') applied to every symbol. Optional - omit to let the gateway resolve each.
        view: Verbosity per card. 'decision' (default) = lean read for an easy head-to-head; 'full' = full receipts on each. Optional.
    """
    _bind_request_key(ctx)
    results: list[dict[str, Any]] = []
    for sym in symbols:
        params: dict[str, Any] = {"view": view or "decision"}
        if market is not None:
            params["market"] = market
        try:
            data = _get(f"/analyze/{_seg(sym)}", params)
        except httpx.HTTPStatusError as exc:
            # Fail-soft per symbol: degrade that row, never break the comparison.
            results.append({"symbol": sym, "error": f"HTTP {exc.response.status_code}", "card": None})
            continue
        if _is_upgrade_stub(data):
            # A Pro-gated field surfaced as a stub - keep the comparison going, note it.
            results.append({"symbol": sym, "requires": "pro",
                            "message": data.get("message"), "upgrade_url": data.get("upgrade_url")})
            continue
        results.append({"symbol": sym, **(data if isinstance(data, dict) else {"data": data})})
    payload = {"count": len(results), "symbols": symbols, "comparison": results}
    return _lead(
        f"Side-by-side seasonal comparison of {len(symbols)} symbol(s) - compare edge score, "
        "win rate, and the receipts on each card:",
        payload,
        handoff=True,
    )


# ===========================================================================
# LOW-LEVEL PRIMITIVES - prefer the flagships above unless you need an exact slice.
# ===========================================================================

# ---------------------------------------------------------------------------
# Tool: list_markets
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer find_best_opportunities / analyze_symbol unless you need "
        "this exact slice (the market catalog itself). "
        "List all active TradeWave markets (15 markets - US stock universes, indices, futures, "
        "forex, bonds, ETFs, international and crypto - with ids spanning 0-16) and the caller's "
        "access scope. "
        "Use when the user asks which markets are available, what markets TradeWave covers, "
        "or which markets they have access to. Returns market ids (the stable keys used "
        "in all other tools), names, ML eligibility, and in-scope flag."
    )
)
def list_markets(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/markets")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: whoami
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Who am I / what can I do here. Returns the caller's plan tier, how many ML scorings "
        "they have left today (null = unlimited), the markets in their scope, and a few example "
        "prompts. REACH FOR THIS FIRST on 'what can you do', 'what plan am I on', 'how many ML "
        "calls do I have left', or to decide which markets are worth scanning before calling "
        "find_best_opportunities."
    )
)
def whoami(ctx: Optional[Context] = None) -> str:
    _bind_request_key(ctx)
    data = _get("/me")
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    tier = data.get("tier_name") or data.get("tier") or "your"
    rem = data.get("ml_remaining_today")
    ml_txt = "unlimited ML scorings/day" if rem is None else f"{rem} ML scoring(s) left today"
    in_scope = data.get("markets_in_scope") or []
    names = ", ".join(m.get("name", m.get("id")) for m in in_scope[:8])
    payload = dict(data)
    payload["example_prompts"] = [
        "Find me the best seasonal trades right now",
        "Analyze GLD's seasonality",
        "What's today's AI daily pick and its track record?",
    ]
    return _lead(
        f"You are on the {tier} plan with {ml_txt}. In-scope markets: {names}. "
        "Try one of the example prompts below:",
        payload,
    )


# ---------------------------------------------------------------------------
# Tool: describe_tradewave (the self-describing / how-to-research guide)
# ---------------------------------------------------------------------------

_TRADEWAVE_GUIDE = (
    "HOW TRADEWAVE WORKS + HOW TO RESEARCH WITH IT\n\n"
    "What it is: TradeWave finds recurring SEASONAL price patterns (calendar windows that have paid "
    "off across many years) and scores each with a 62-feature ML model. Every result is a SignalCard: "
    "a headline + verdict, the entry/hold window, win rates, an ML probability, an edge_score, and "
    "year-by-year receipts. The daily AI pick also carries a LIVE forward-tested track record. "
    "Signals-only: TradeWave never returns raw prices - moves are percentages and the seasonal curve "
    "(its user-facing name is 'The Trend Chart') is a 0-100 normalized index.\n\n"
    "What it does NOT see: fundamentals, valuation, news, catalysts, macro/rates, analyst views, "
    "upcoming earnings, or the live price. Treat a card as a statistical PRIOR, not a complete view.\n\n"
    "HOW TO RESEARCH WITH IT (the method): (1) EDGE - get the seasonal/ML read from TradeWave; "
    "(2) EXTEND - use your OWN tools to check whether news / fundamentals / macro SUPPORT or THREATEN "
    "that thesis (search for them; do not assume or invent a catalyst); (3) ASK TRADEWAVE FOR MORE "
    "when it would change the answer (detail receipts + the Trend Chart, compare peers, the live "
    "track record); (4) SYNTHESIZE one view and keep explicit which facts are TradeWave's data vs "
    "your own research.\n\n"
    "The THREE win rates (NEVER conflate them):\n"
    "  - historical_win_rate: share of past YEARS the seasonal window was profitable (in-sample seasonal history).\n"
    "  - ml_win_prob: the 62-feature ML model's probability THIS instance works (per-instance, not history).\n"
    "  - track_record.win_rate: the LIVE, forward-tested record of past daily picks (out-of-sample - the real proof).\n\n"
    "edge_score (0-100): a blend of historical_win_rate, Sharpe, years of history, and the ML score - one number to rank by.\n\n"
    "How to act on a card: respect the entry WINDOW (entering late or after it closes loses the edge). "
    "NO_SIGNAL means TradeWave found NO statistical edge - a genuine 'no edge' finding, not weak support. "
    "Nothing here is personalized investment advice."
)


@mcp.tool(
    description=(
        "How TradeWave works + how to research with it. REACH FOR THIS on 'what is this / how do I "
        "read these cards / how do the win rates differ / how should I use TradeWave', or before "
        "relying on a card. Returns the research method (edge -> extend with your own tools -> "
        "synthesize), the glossary (the three distinct win rates, edge_score, the Trend Chart), what "
        "TradeWave can and cannot tell you, and how to act on a SignalCard."
    )
)
def describe_tradewave(ctx: Optional[Context] = None) -> str:
    return _TRADEWAVE_GUIDE


# ---------------------------------------------------------------------------
# Tool: list_symbols
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer find_best_opportunities / analyze_symbol unless you need "
        "this exact slice (the symbol roster of one market). "
        "List the tradeable symbols in a specific market. "
        "Use when the user asks what stocks, futures, or ETFs are in a market, "
        "or to discover valid symbols. "
        "Pass the market id from list_markets (e.g. '2' for S&P 500 stocks)."
    )
)
def list_symbols(market: str, ctx: Context) -> str:
    """
    Args:
        market: Market id, e.g. '0', '2', '11'. Use list_markets to find valid ids.
    """
    _bind_request_key(ctx)
    data = _get(f"/markets/{_seg(market)}/symbols")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_seasonal_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer find_best_opportunities (which scans across markets, "
        "scores by edge, and returns ready SignalCards) unless you need this exact slice: the "
        "raw single-market opportunity list for one date window. "
        "Find seasonal trade setups for ONE market and date window, ranked by historical edge. "
        "Filters by direction (long/short), minimum win rate, and date range. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro)."
    )
)
def get_seasonal_opportunities(
    market: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    direction: Optional[str] = None,
    min_win_rate: Optional[float] = None,
    min_days: Optional[int] = None,
    max_days: Optional[int] = None,
    min_avg_return: Optional[float] = None,
    min_median_return: Optional[float] = None,
    min_sharpe: Optional[float] = None,
    pe_cycle: Optional[str] = None,
    years: Optional[int] = None,
    min_winning_years: Optional[int] = None,
    limit: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        market: Market id (permanent key '0'..'16'). Required.
        pe_cycle: Presidential election cycle mode: 'consecutive' (default) or 'pe' (the current cycle position). Optional.
        years: Lookback - years to scan for patterns (5-98, default 10; PE-position occurrences in pe mode). Optional.
        min_winning_years: Of those years, the minimum that must be WINNERS - the win-rate floor (year2). DEFAULTS to ~90% of years (so years=20 gives a valid 20-18). This is a SINGLE-market call, so it is validated against that market's DETECTION BAND (about 75-90%+, market-specific); an out-of-band value (e.g. 20-9) returns a clear error with the valid range. Optional.
        from_date: Start of entry-date window, ISO 8601 (YYYY-MM-DD). Optional.
        to_date: End of entry-date window, ISO 8601 (YYYY-MM-DD). Optional.
        direction: 'long' or 'short'. Optional - omit for both.
        min_win_rate: Minimum historical win rate 0..1, e.g. 0.65. Optional.
        min_days: Minimum pattern length (holding period) in calendar days, e.g. 10. Optional.
        max_days: Maximum pattern length (holding period) in calendar days, e.g. 90. Optional. Use min_days+max_days for a day RANGE like 10-90.
        min_avg_return: Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%). Optional.
        min_median_return: Minimum median seasonal profit in PERCENT. Optional.
        min_sharpe: Minimum Sharpe ratio, e.g. 1.5. Optional.
        limit: Max results to return (tier-capped: free=3, dev=25, pro up to 5000). Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"market": market}
    if from_date is not None:
        params["from"] = from_date
    if to_date is not None:
        params["to"] = to_date
    if direction is not None:
        params["direction"] = direction
    if min_win_rate is not None:
        params["min_win_rate"] = min_win_rate
    if min_days is not None:
        params["min_days"] = min_days
    if max_days is not None:
        params["max_days"] = max_days
    if min_avg_return is not None:
        params["min_avg_return"] = min_avg_return
    if min_median_return is not None:
        params["min_median_return"] = min_median_return
    if min_sharpe is not None:
        params["min_sharpe"] = min_sharpe
    if pe_cycle is not None:
        params["pe_cycle"] = pe_cycle
    if years is not None:
        params["years"] = years
    if min_winning_years is not None:
        params["min_winning_years"] = min_winning_years
    if limit is not None:
        params["limit"] = limit
    data = _get("/opportunities", params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_symbol_patterns (the wave-viewer pattern-dropdown list, named clearly)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "A security's TOP SEASONAL PATTERNS throughout the year, ranked by Sharpe ratio - the list "
        "the wave viewer shows in its pattern dropdown. Reach for this when the user asks 'what are "
        "the best seasonal patterns for SYMBOL' or 'show me SYMBOL's patterns'. Each pattern is an "
        "entry window with direction, hold length (days), Sharpe, avg/median seasonal return %, and "
        "historical win rate. Filters: pattern length (min_days/max_days, e.g. 10-90), avg profit "
        "(min_avg_return, percent), Sharpe floor (min_sharpe), and pe_cycle ('consecutive' default, "
        "or 'pe' for the current presidential-cycle position). "
        "COVERAGE: the per-symbol pattern grid exists for DOW 30, NASDAQ 100, S&P 500, Futures & "
        "Commodities, and FOREX Liquid only (market ids 0,1,2,7,9); for any other market this returns "
        "a clear error - use find_best_opportunities to scan those markets instead. The lookback knobs "
        "years / min_winning_years follow the same per-market detection band as find_best_opportunities "
        "(min_winning_years defaults to ~90% of years and must stay within the band)."
    )
)
def get_symbol_patterns(symbol: str, market: str, pe_cycle: Optional[str] = None,
                        years: Optional[int] = None, min_winning_years: Optional[int] = None,
                        min_days: Optional[int] = None, max_days: Optional[int] = None,
                        min_avg_return: Optional[float] = None, min_sharpe: Optional[float] = None,
                        ctx: Optional[Context] = None) -> str:
    """
    Args:
        symbol: Ticker symbol, e.g. 'DOV', 'GLD'.
        market: Market id containing the symbol. Per-symbol patterns exist for ids 0,1,2,7,9 only (other markets return a clear error).
        pe_cycle: 'consecutive' (default) or 'pe' (current presidential-cycle position). Optional.
        years: Lookback years for pattern detection (default 10). Optional.
        min_winning_years: Of those years, the minimum WINNERS - the win-rate floor (year2). Defaults to ~90% of years; must stay within this market's detection band (an out-of-band value returns a clear error with the valid range). Optional.
        min_days: Minimum pattern length in days. Optional.
        max_days: Maximum pattern length in days (use with min_days for a range). Optional.
        min_avg_return: Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%). Optional.
        min_sharpe: Minimum Sharpe ratio. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"market": market}
    for _k, _v in (("pe_cycle", pe_cycle), ("years", years), ("min_winning_years", min_winning_years),
                   ("min_days", min_days), ("max_days", max_days),
                   ("min_avg_return", min_avg_return), ("min_sharpe", min_sharpe)):
        if _v is not None:
            params[_k] = _v
    data = _get(f"/securities/{_seg(symbol)}/patterns", params=params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_seasonal_pattern
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer analyze_symbol (it already bundles these stats with the "
        "setup, receipts, and ML into one SignalCard) unless you need this exact slice: the bare "
        "aggregate stats with nothing else. "
        "Get aggregate seasonal pattern statistics for a symbol - Sharpe ratio, win rate, "
        "average and median return, and other summary stats. "
        "Returns stats only - no raw price series."
    )
)
def get_seasonal_pattern(market: str, symbol: str, pe_cycle: Optional[str] = None,
                         years: Optional[int] = None, period: Optional[str] = None,
                         reverse: Optional[bool] = None, ctx: Optional[Context] = None) -> str:
    """
    Args:
        market: Market id containing the symbol.
        symbol: Ticker symbol.
        pe_cycle: Presidential cycle filter: 'consecutive' (default), 'pe' (current cycle position), or
            a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'. Optional.
        years: Lookback count (number of years, or number of cycle occurrences when pe_cycle is set). Optional.
        period: Date-range PRESET: month 'jan'..'dec', quarter 'q1'..'q4', season 'spring'|'summer'|'fall'|
            'winter', 'ytd', 'year_end', or 'buy_hold'. Optional.
        reverse: If true, use the COMPLEMENT of the window (e.g. period='mar' + reverse=true = all year
            except March). A full-year (buy_hold) range cannot be reversed. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {}
    if pe_cycle is not None:
        params["pe_cycle"] = pe_cycle
    if years is not None:
        params["years"] = years
    if period is not None:
        params["period"] = period
    if reverse:
        params["reverse"] = "true"
    data = _get(f"/patterns/{_seg(market)}/{_seg(symbol)}", params=params or None)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_opportunity_chart
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer find_best_opportunities / analyze_symbol unless you need "
        "this exact slice: the raw seasonal curve to chart or to reason over its shape. "
        "Get the Trend Chart DATA for a symbol as numbers (not an image), in ONE call: a SINGLE "
        "year-averaged, normalized 0-100 seasonal index curve (`seasonal_curve`) showing the "
        "typical within-year shape - it is NOT per-year cumulative paths - PLUS `per_year_bars` "
        "(each completed year's trade return with its favorable (mfe) / adverse (mae) excursion "
        "band, direction-aware, all percentages). Together they are everything needed to draw the "
        "Trend Chart and the per-year bar panel client-side. "
        "Use when the user wants to see or reason over the shape of the seasonal pattern "
        "(where it rises, peaks, and fades through the year). "
        "The index is a normalized relative shape, never a price. "
        "The response may include receipts.curve_summary which describes the TREND OF THE "
        "HOLD SECTION (entry to exit), NOT the full year. Fields: shape, trend "
        "(rising|falling|flat), change_pts, peak_day, trough_day - where peak_day and "
        "trough_day are days INTO THE HOLD (0 = entry day). Do not interpret these as "
        "full-year peaks or troughs."
    )
)
def get_opportunity_chart(
    market: str,
    symbol: str,
    entry_date: Optional[str] = None,
    days_out: Optional[int] = None,
    direction: Optional[str] = None,
    years: Optional[str] = None,
    pe_cycle: Optional[str] = None,
    period: Optional[str] = None,
    reverse: Optional[bool] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        market: Market id.
        symbol: Ticker symbol.
        entry_date: Entry date for the setup, ISO 8601 (YYYY-MM-DD). Optional.
        days_out: Holding period in calendar days. Optional.
        direction: 'long' or 'short'. Optional.
        years: Lookback window label (stays a string, e.g. '10', '20'). Optional.
        pe_cycle: Presidential cycle filter for the curve: 'consecutive' (default), 'pe' (current cycle
            position), or a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'. Optional.
        period: Date-range PRESET (overrides entry_date/days_out): a month 'jan'..'dec', a quarter
            'q1'..'q4', a season 'spring'|'summer'|'fall'|'winter', 'ytd' (year to date), 'year_end'
            (today to year end), or 'buy_hold' (Jan 1 to Jan 1, full year). Optional.
        reverse: If true, use the COMPLEMENT of the window - everything except it (e.g. period='mar' +
            reverse=true = all year except March). A full-year (buy_hold) range cannot be reversed. Optional.
    """
    _bind_request_key(ctx)
    params: dict[str, Any] = {"market": market, "symbol": symbol}
    if entry_date is not None:
        params["entry_date"] = entry_date
    if days_out is not None:
        params["days_out"] = days_out
    if direction is not None:
        params["direction"] = direction
    if years is not None:
        params["years"] = years
    if pe_cycle is not None:
        params["pe_cycle"] = pe_cycle
    if period is not None:
        params["period"] = period
    if reverse:
        params["reverse"] = "true"
    data = _get("/seasonal-chart", params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: score_opportunities (metered, all tiers)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer analyze_symbol / find_best_opportunities (they attach ML "
        "inline on eligible markets, metered per tier) unless you need this exact slice: ML scoring "
        "of an explicit hand-built list of setups. "
        "Score a list of seasonal opportunities with ML win-probability and predicted return. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "When the daily ML allowance is spent the gateway returns a graceful nudge (never an error): "
        "a 200 body with requires='upgrade', reason='ml_daily_limit', and ml_remaining_today. "
        "ML scoring is available for markets 0-4 and 11 only. "
        "Input: a list of {symbol, date, days_out, direction} dicts. "
        "Output: ml_score (0-100), win_prob (0-1), pred_return %, pred_mfe %."
    )
)
def score_opportunities(
    opportunities: list[dict[str, Any]],
    ctx: Context,
) -> str:
    """
    Args:
        opportunities: List of opportunity dicts, each with keys:
            - symbol (str): ticker symbol
            - date (str): entry date YYYY-MM-DD
            - days_out (int): holding period in days
            - direction (str): 'long' or 'short'
    """
    _bind_request_key(ctx)
    data = _post("/score", {"opportunities": opportunities})
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_daily_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer explain_pick (it returns the same pick as a full SignalCard "
        "WITH its live forward-tested track record - the strongest proof) unless you need this "
        "exact slice: the bare daily-pick payload with no receipts. "
        "Get today's AI-selected daily pick - the single ML-ranked seasonal opportunity "
        "TradeWave highlights each day. "
        "Includes symbol, direction, holding period, pattern summary, and ML scores."
    )
)
def get_daily_pick(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/daily-pick")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_pick_track_record
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer explain_pick (it bundles today's pick WITH this record) "
        "unless you need this exact slice: the standalone full history of past picks. "
        "Get the realized win/loss track record of all past TradeWave daily picks. "
        "Use when the user wants the full per-pick performance history, or to verify the "
        "historical accuracy before trusting the signals. Returns the full history with "
        "per-pick return %, result (win/loss/open), and summary stats (count, win rate, "
        "avg return). This is the verifiable performance record - free-tier accessible."
    )
)
def get_pick_track_record(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/daily-pick/track-record")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradeWave MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE / streamable-http transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="Port for SSE / streamable-http transports (default: 9090)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.transport == "stdio":
        # stdio = one local server per user; the key MUST come from the env.
        if not TRADEWAVE_API_KEY:
            print(
                "WARNING: TRADEWAVE_API_KEY is not set. stdio gateway calls will be "
                "unauthenticated (gateway will 401).",
                file=sys.stderr,
            )
    else:
        # Remote (sse / streamable-http) = BYOK per connection: each client sends
        # its own `Authorization: Bearer <key>`, used for that connection's calls.
        # Run with NO baked-in key. If TRADEWAVE_API_KEY happens to be set it acts
        # only as a last-resort fallback for a connection that sends no header, so
        # a shared key is best left unset on a multi-customer remote endpoint.
        if TRADEWAVE_API_KEY:
            print(
                "NOTE: TRADEWAVE_API_KEY is set on a remote transport. The "
                "per-connection Authorization header takes precedence per call; "
                "the env key is only a fallback for headerless connections. Unset "
                "it for a true multi-customer BYOK endpoint.",
                file=sys.stderr,
            )

    if args.transport != "stdio":
        # Inject host/port before running non-stdio transports.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # The SDK's DNS-rebinding protection allowlists only localhost by default,
        # so a proxied public Host (e.g. mcp-dev.trxstat.com) gets a 421. Allow the
        # configured public host (env TW2_MCP_PUBLIC_HOST) plus the local bind.
        from mcp.server.transport_security import TransportSecuritySettings
        _pub = (os.environ.get("TW2_MCP_PUBLIC_HOST") or "mcp-dev.trxstat.com").replace(
            "https://", "").replace("http://", "").rstrip("/")
        mcp.settings.transport_security = TransportSecuritySettings(
            allowed_hosts=[_pub, f"{args.host}:{args.port}", "127.0.0.1",
                           f"127.0.0.1:{args.port}", "localhost", f"localhost:{args.port}"],
            allowed_origins=[f"https://{_pub}", f"http://127.0.0.1:{args.port}"],
        )

    if args.transport == "streamable-http":
        # Serve the MCP endpoint at the ROOT so the bare connector URL works (ChatGPT/Claude POST to
        # whatever URL the user enters; entering the host with no path means they POST "/"). The
        # /.well-known/oauth-* discovery routes are more specific and still resolve.
        mcp.settings.streamable_http_path = "/"

    mcp.run(transport=args.transport)
