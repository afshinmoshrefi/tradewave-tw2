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

_request_api_key: ContextVar[Optional[str]] = ContextVar("_request_api_key", default=None)


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
    except (LookupError, AttributeError):
        # No active request context (e.g. stdio) - nothing to extract.
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
    """Resolve and bind this call's API key into the ContextVar.

    Each tool calls this once at entry. Resolution order:
      per-connection Bearer header (remote) -> env TRADEWAVE_API_KEY (stdio)
      -> None (no auth; gateway 401, correct BYOK behavior).
    """
    _request_api_key.set(_bearer_from_request(ctx) or (TRADEWAVE_API_KEY or None))


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    key = _request_api_key.get()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


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
    """Return a clear Pro-required message from an UpgradeRequired stub."""
    msg = data.get("message", "This feature requires a Pro subscription.")
    url = data.get("upgrade_url", "https://tradewave.ai/upgrade")
    return f"Pro subscription required - {msg}\nUpgrade at: {url}"


def _is_upgrade_stub(data: Any) -> bool:
    return isinstance(data, dict) and data.get("requires") == "pro"


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="TradeWave",
    instructions=(
        "TradeWave provides derived seasonal trading signals and ML win-probability scores "
        "for 17 global markets. Use these tools to find seasonal trade setups, get ML scoring "
        "on opportunities, and check the AI daily pick and its track record. "
        "All returns are percentages - no raw prices are ever exposed. "
        "Pro-tier tools degrade gracefully with an upgrade message for non-Pro callers."
    ),
)

# ---------------------------------------------------------------------------
# Tool: list_markets
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "List all 17 TradeWave markets and the caller's access scope. "
        "Use when the user asks which markets are available, what markets TradeWave covers, "
        "or which markets they have access to. Returns market ids (the stable keys used "
        "in all other tools), names, ML eligibility, and in-scope flag."
    )
)
def list_markets(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/markets")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: list_symbols
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "List the tradeable symbols in a specific market. "
        "Use when the user asks what stocks, futures, or ETFs are in a market, "
        "or before calling get_seasonal_opportunities to discover valid symbols. "
        "Pass the market id from list_markets (e.g. '2' for S&P 500 stocks)."
    )
)
def list_symbols(market: str, ctx: Context) -> str:
    """
    Args:
        market: Market id, e.g. '0', '2', '11'. Use list_markets to find valid ids.
    """
    _bind_request_key(ctx)
    data = _get(f"/markets/{market}/symbols")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_seasonal_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Find the best seasonal trade setups for a market and date window, ranked by "
        "historical edge. Use when the user asks what to trade, when to enter, which "
        "symbols have a strong seasonal tendency, or wants a ranked list of opportunities. "
        "Filters by direction (long/short), minimum win rate, and date range. "
        "Pro callers get ML scores inline; free-tier results are still ranked by Sharpe ratio."
    )
)
def get_seasonal_opportunities(
    market: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    direction: Optional[str] = None,
    min_win_rate: Optional[float] = None,
    limit: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Args:
        market: Market id (permanent key '0'..'16'). Required.
        from_date: Start of entry-date window, ISO 8601 (YYYY-MM-DD). Optional.
        to_date: End of entry-date window, ISO 8601 (YYYY-MM-DD). Optional.
        direction: 'long' or 'short'. Optional - omit for both.
        min_win_rate: Minimum historical win rate 0..1, e.g. 0.65. Optional.
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
    if limit is not None:
        params["limit"] = limit
    data = _get("/opportunities", params)
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_opportunity_for_symbol
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get all seasonal trade setups for a single symbol in a market. "
        "Use when the user asks about a specific ticker - e.g. 'what is AAPL's seasonal pattern', "
        "'show me GLD setups', or 'does this symbol have any strong seasonal trades'. "
        "Returns ranked setups (entry date, direction, hold period, win rate, avg return)."
    )
)
def get_opportunity_for_symbol(symbol: str, market: str, ctx: Context) -> str:
    """
    Args:
        symbol: Ticker symbol, e.g. 'AAPL', 'GC', 'SPY'. Case-sensitive as in the market.
        market: Market id containing the symbol (use list_markets or list_symbols to find it).
    """
    _bind_request_key(ctx)
    data = _get(f"/opportunities/{symbol}", params={"market": market})
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_seasonal_pattern
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get aggregate seasonal pattern statistics for a symbol - Sharpe ratio, win rate, "
        "average and median return, and other summary stats. "
        "Use when the user wants to understand the strength and reliability of a seasonal "
        "pattern for a specific symbol, or to compare the historical edge across names. "
        "Returns stats only - no raw price series."
    )
)
def get_seasonal_pattern(market: str, symbol: str, ctx: Context) -> str:
    """
    Args:
        market: Market id containing the symbol.
        symbol: Ticker symbol.
    """
    _bind_request_key(ctx)
    data = _get(f"/patterns/{market}/{symbol}")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_opportunity_chart
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get seasonal trend-chart DATA for a trade setup - the per-year cumulative % paths "
        "and the average seasonal line, as numbers (not an image). "
        "Use when the user wants to see how a seasonal setup has played out year-by-year, "
        "understand the consistency of the pattern, or reason over its shape. "
        "Returns average path, per-year paths with win/loss labels, and summary stats. "
        "All values are percentages from entry - no raw prices."
    )
)
def get_opportunity_chart(
    market: str,
    symbol: str,
    entry_date: Optional[str] = None,
    days_out: Optional[int] = None,
    direction: Optional[str] = None,
    years: Optional[str] = None,
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
    data = _get("/seasonal-chart", params)
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: score_opportunities (Pro)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Score a list of seasonal opportunities with ML win-probability and predicted return. "
        "Pro tier only - non-Pro callers receive a clear upgrade message, not an error. "
        "Use when the user wants to rank setups by ML confidence, get a win probability, "
        "or filter a shortlist by predicted return / max favorable excursion. "
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
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_daily_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get today's AI-selected daily pick - the single ML-ranked seasonal opportunity "
        "TradeWave highlights each day. "
        "Use when the user asks for today's trade idea, what the AI picked today, "
        "or wants a ready-to-act setup without scanning the full opportunity list. "
        "Includes symbol, direction, holding period, pattern summary, and ML scores."
    )
)
def get_daily_pick(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/daily-pick")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_pick_track_record
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get the realized win/loss track record of all past TradeWave daily picks. "
        "Use when the user asks how the AI picks have performed, wants to verify the "
        "historical accuracy before trusting the signals, or is evaluating TradeWave's "
        "edge. Returns the full history with per-pick return %, result (win/loss/open), "
        "and summary stats (count, win rate, avg return). "
        "This is the verifiable performance record - free-tier accessible."
    )
)
def get_pick_track_record(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = _get("/daily-pick/track-record")
    return json.dumps(data, indent=2)


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

    mcp.run(transport=args.transport)
