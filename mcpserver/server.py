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

No data logic lives here; the gateway enforces all tier/access rules.

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
import asyncio
import copy
import datetime
import functools
import hashlib
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Optional

import httpx
from pydantic import Field
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import CallToolResult, ResourceLink, TextContent, ToolAnnotations

try:
    from mcpserver.chart_renderer import render_card_charts
except ImportError:  # direct ``python mcpserver/server.py`` / unit-test import path
    try:
        from chart_renderer import render_card_charts
    except ImportError:  # rolling deploy before Pillow lands: keep MCP data/link alive
        def render_card_charts(_card):
            return []

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

_main_public_host = (os.environ.get("TW2_PUBLIC_HOST", "") or "tw2-dev.trxstat.com").strip().rstrip("/")
MAIN_PUBLIC_URL: str = (
    _main_public_host
    if _main_public_host.startswith(("http://", "https://"))
    else f"https://{_main_public_host}"
)

LEGACY_PATTERN_WIDGET_URI = "ui://tradewave/pattern-evidence-v2.html"
PATTERN_WIDGET_URI = "ui://tradewave/pattern-evidence-v3.html"
SCAN_WIDGET_URI = "ui://tradewave/ranked-opportunities-v1.html"
PATTERN_WIDGET_HTML = (Path(__file__).with_name("pattern_widget.html")).read_text(
    encoding="utf-8"
)

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


# --- connect-time BYOK key validation (used by the auth gate below) -----------------
# Verdicts are cached briefly by key HASH (never the raw key) so the per-request auth
# gate stays cheap; the gateway remains the source of truth on every actual tool call.
_BYOK_CHECK_TTL = 60.0                                   # seconds
_BYOK_CACHE_MAX = 1024                                   # crude bound; cleared when exceeded
_byok_cache: dict[str, tuple[float, bool]] = {}          # sha256(key) -> (expires, valid)


async def _byok_key_valid(key: str) -> bool:
    """Cheap connect-time check of a tw_ key against the gateway's /me.

    200 -> valid, 401/403 -> invalid (both cached for _BYOK_CHECK_TTL). Anything else
    (gateway down, 5xx, 429) FAILS OPEN uncached: a gateway hiccup must not sever every
    existing connection, and the per-call gateway auth still rejects a bad key."""
    h = hashlib.sha256(key.encode()).hexdigest()
    now = time.monotonic()
    cached = _byok_cache.get(h)
    if cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{API_BASE_URL}/me",
                                    headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        return True
    if resp.status_code == 200 or resp.status_code in (401, 403):
        if len(_byok_cache) > _BYOK_CACHE_MAX:
            _byok_cache.clear()
        _byok_cache[h] = (now + _BYOK_CHECK_TTL, resp.status_code == 200)
    return resp.status_code not in (401, 403)


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
            if token.startswith("tw_"):          # BYOK / dev tools - validate at CONNECT (below)
                if not await _byok_key_valid(token):
                    # A garbage tw_ key must fail the CONNECT, exactly like a bad OAuth
                    # login - not surface later as a confusing per-tool 401.
                    log.info("MCP BYOK: connect rejected, gateway did not accept key hash %s...",
                             hashlib.sha256(token.encode()).hexdigest()[:12])
                    return None
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


# Large cold scans can legitimately run >60s (the gateway caches, so a retry returns fast);
# the old 30s starved them mid-compute and surfaced as a raw httpx exception.
_GATEWAY_TIMEOUT = 110
_GATEWAY_MAX_INFLIGHT = max(
    1, min(128, int(os.environ.get("TW2_MCP_GATEWAY_MAX_INFLIGHT", "32")))
)
_gateway_client: Optional[httpx.AsyncClient] = None
_gateway_slots: Optional[asyncio.Semaphore] = None

_TIMEOUT_RESULT = (
    "This large scan is still computing on the gateway - retry in a moment; the result "
    "will be cached and come back quickly."
)
_UNREACHABLE_RESULT = "The TradeWave gateway is temporarily unreachable. Try again in a moment."


class GatewayError(Exception):
    """A user-presentable gateway failure. `message` is returned VERBATIM as the tool
    result (via _tool_errors) - never a raw httpx string, which would leak the internal
    gateway URL to the model."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _friendly_http_error(exc: httpx.HTTPStatusError) -> str:
    """The gateway's own {error:{message}} text when present; a friendly generic line
    otherwise. Never the raw httpx repr (it embeds the internal gateway URL)."""
    code = None
    msg = None
    try:
        err = exc.response.json().get("error") or {}
        code = err.get("code")
        msg = err.get("message")
    except Exception:  # noqa: BLE001 - non-JSON body / unexpected shape
        pass
    if isinstance(msg, str) and msg.strip():
        msg = msg.strip()
        if code == "rate_limited":
            msg += " - wait a few seconds and retry; results are cached."
        return msg
    return (f"The TradeWave gateway returned an error (HTTP {exc.response.status_code}). "
            "Try again in a moment.")


def _new_gateway_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(_GATEWAY_TIMEOUT, connect=5.0),
        limits=httpx.Limits(
            max_connections=_GATEWAY_MAX_INFLIGHT,
            max_keepalive_connections=min(16, _GATEWAY_MAX_INFLIGHT),
            keepalive_expiry=30.0,
        ),
    )


@asynccontextmanager
async def _mcp_lifespan(_server: FastMCP):
    """Own one bounded reusable gateway pool for the MCP process lifetime."""
    global _gateway_client, _gateway_slots
    async with _new_gateway_client() as client:
        _gateway_client = client
        _gateway_slots = asyncio.Semaphore(_GATEWAY_MAX_INFLIGHT)
        try:
            yield {}
        finally:
            _gateway_client = None
            _gateway_slots = None


async def _request(method: str, path: str, *, params: dict[str, Any] | None = None,
                   body: Any = None) -> Any:
    """One gateway round-trip. Every failure mode becomes a GatewayError whose message is
    safe to hand to the model as the tool result (see _tool_errors)."""
    url = f"{API_BASE_URL}{path}"
    async def send(client: httpx.AsyncClient):
        slots = _gateway_slots
        if slots is None:
            if method == "GET":
                return await client.get(url, params=params, headers=_headers())
            return await client.post(
                url, json=body,
                headers={**_headers(), "Content-Type": "application/json"},
            )
        async with slots:
            if method == "GET":
                return await client.get(url, params=params, headers=_headers())
            return await client.post(
                url, json=body,
                headers={**_headers(), "Content-Type": "application/json"},
            )

    try:
        if _gateway_client is None:
            async with _new_gateway_client() as client:
                resp = await send(client)
        else:
            resp = await send(_gateway_client)
        resp.raise_for_status()
    except httpx.TimeoutException:
        raise GatewayError(_TIMEOUT_RESULT) from None
    except httpx.HTTPStatusError as exc:
        raise GatewayError(_friendly_http_error(exc)) from None
    except httpx.HTTPError:
        raise GatewayError(_UNREACHABLE_RESULT) from None
    return resp.json()


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Asynchronous GET against the gateway. Returns parsed JSON."""
    return await _request(
        "GET", path,
        params={k: v for k, v in (params or {}).items() if v is not None},
    )


async def _post(path: str, body: Any) -> Any:
    """Asynchronous POST against the gateway. Returns parsed JSON."""
    return await _request("POST", path, body=body)


def _tool_errors(fn):
    """Tool decorator (applied INSIDE @mcp.tool): converts a GatewayError into the tool
    RESULT text, so the model always sees the gateway's own friendly message instead of a
    raised exception. functools.wraps keeps the original signature visible to FastMCP's
    schema builder (inspect.signature follows __wrapped__)."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except GatewayError as e:
            return e.message
    return wrapper


def _widget_tool_errors(fn):
    """Widget-tool variant that keeps failures valid against the declared object schema."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except GatewayError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=e.message)],
                structuredContent={"error": {"message": e.message}},
                isError=True,
            )
    return wrapper


def _csv(value: list[str] | str | None) -> Optional[str]:
    """Accept a list OR a CSV string for multi-value params (models naturally send lists);
    the gateway speaks CSV."""
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return value


def _format_upgrade(data: dict[str, Any]) -> str:
    """Return a clear upgrade message from the gateway's ML daily-limit stub.

    The gateway emits ONE upgrade-stub shape (POST /v1/score, when the daily ML allowance
    is spent): {requires:"upgrade", reason:"ml_daily_limit", message, upgrade_url,
    ml_remaining_today:0}. ML is offered on EVERY tier, metered per day - there is no
    feature that "requires Pro". The stub surfaces as a clear human message with an
    upgrade link, never as an error. ml_remaining_today is shown when present
    (None = unlimited, 0 = limit reached).
    """
    msg = data.get("message", "")
    url = data.get("upgrade_url", "https://tradewave.ai/upgrade")
    remaining = data.get("ml_remaining_today")

    remaining_str = ""
    if remaining is not None:
        remaining_str = f" (ML calls remaining today: {remaining})"
    if not msg:
        msg = "You have reached your daily ML scoring limit. Upgrade for unlimited ML scoring."
    return f"Daily ML limit reached on your plan - {msg}{remaining_str}\nUpgrade at: {url}"


def _is_upgrade_stub(data: Any) -> bool:
    # The only upgrade stub the gateway returns is the ML daily-limit one (requires:"upgrade",
    # reason:"ml_daily_limit"); there is no requires:"pro" shape - ML is metered, not gated.
    return isinstance(data, dict) and data.get("requires") == "upgrade"


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
    lifespan=_mcp_lifespan,
    # Every remote request is independently authenticated and all business state
    # lives in the gateway.  Keeping transport sessions in this process makes a
    # valid Claude/ChatGPT connector fail after a deploy (or when a load balancer
    # sends its next request to another worker).  Stateless Streamable HTTP accepts
    # the client's prior session header without depending on in-memory session state.
    stateless_http=True,
    **_auth_kwargs,
    instructions=(
        "TradeWave is the user's seasonal-edge analyst. It finds, ranks, and explains "
        "detected seasonal patterns (backed by ML win-probability scores) across TradeWave's "
        "15 active markets. All returns are percentages - no raw prices are ever exposed.\n\n"
        "REACH FOR THE FLAGSHIP TOOLS FIRST - they return ready, evidence-backed answers as "
        "structured Pattern Cards (headline + verdict + receipts + a ready-to-place order ticket):\n"
        "  - find_best_opportunities: 'what should I trade', 'find me something', 'anything "
        "seasonal in gold/energy', a ranked scan across markets.\n"
        "  - whats_seasonal_now: 'what is entering its window this week', the weekly digest.\n"
        "  - analyze_symbol: a full deep-dive on ONE ticker in a single call.\n"
        "  - compare_opportunities: rank several tickers side-by-side.\n"
        "  - explain_pick: today's AI daily pick WITH its live forward-tested track record.\n\n"
        "The other tools are low-level primitives - prefer the flagships unless you need one "
        "exact slice (e.g. the raw normalized seasonal curve to chart). The gateway is the one "
        "source of truth: present its Pattern Cards, do not recompute or re-rank them.\n\n"
        "FOCUSED FOLLOW-UPS MUST CALL analyze_symbol AGAIN. On every user turn that asks about, "
        "assesses, explains, revisits, or opens one named symbol or one exact pattern, call "
        "analyze_symbol on that turn even when an earlier scan already contains enough numbers "
        "to write a text answer. Never answer a focused follow-up solely from cached conversation "
        "or a prior shortlist. The fresh call is required to mount TradeWave's evidence widget "
        "automatically; do not wait for the user to say 'chart' or 'TradeWave chart'.\n\n"
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "When the daily ML allowance is spent the gateway returns a graceful nudge "
        "(requires='upgrade', reason='ml_daily_limit') - surface this as "
        "'daily ML limit reached - upgrade for unlimited' and include ml_remaining_today if "
        "present. Never surface it as an error.\n\n"
        "PRESENTATION - TradeWave is the primary answer, not a footnote. Lead with its verdict, "
        "statistics, year-by-year evidence, path risk, and seasonal trend. When a tool has a "
        "TradeWave evidence widget, let that widget render the charts and include the exact Wave "
        "Viewer link. Do not replace "
        "this evidence with generic prose or outside research. When the user asks how to view, "
        "open, or inspect a setup in TradeWave, repeat the exact supplied Wave Viewer URL. Never "
        "replace an available deep link with manual navigation instructions.\n\n"
        "RESEARCH METHOD - TradeWave gives the SEASONAL + ML "
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


@mcp.resource(
    PATTERN_WIDGET_URI,
    name="tradewave-pattern-evidence",
    title="TradeWave Pattern Evidence",
    description=(
        "Complete ranked seasonal shortlist plus interactive evidence for the top pattern."
    ),
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": True,
            # Deliberately omit ui.domain. MCP hosts assign their own isolated widget
            # origin (Claude uses <hash>.claudemcpcontent.com); advertising the MCP
            # server host here makes Claude reject the app before it can list tools.
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
            },
        },
        "openai/widgetDescription": (
            "Shows the complete ranked TradeWave shortlist, normalized seasonal trend, yearly "
            "MFE/MAE ranges, final returns, key statistics, and exact Wave Viewer links."
        ),
        "openai/widgetCSP": {
            "redirect_domains": [MAIN_PUBLIC_URL],
        },
    },
)
def pattern_evidence_widget() -> str:
    """MCP App template. All evidence arrives in the tool's structuredContent."""
    return PATTERN_WIDGET_HTML


# MCP hosts can cache a tool's outputTemplate URI for an existing connector. Keep
# the previous URI resolvable so a deploy cannot break an already-connected client.
@mcp.resource(
    LEGACY_PATTERN_WIDGET_URI,
    name="tradewave-pattern-evidence-v2",
    title="TradeWave Pattern Evidence",
    description=(
        "Complete ranked seasonal shortlist plus interactive evidence for the top pattern."
    ),
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": True,
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
            },
        },
        "openai/widgetDescription": (
            "Shows the complete ranked TradeWave shortlist, normalized seasonal trend, yearly "
            "MFE/MAE ranges, final returns, key statistics, and exact Wave Viewer links."
        ),
        "openai/widgetCSP": {
            "redirect_domains": [MAIN_PUBLIC_URL],
        },
    },
)
def pattern_evidence_widget_v2() -> str:
    """Compatibility alias for hosts that cached the previous outputTemplate URI."""
    return PATTERN_WIDGET_HTML


@mcp.resource(
    SCAN_WIDGET_URI,
    name="tradewave-ranked-opportunities",
    title="TradeWave Ranked Opportunities",
    description="Complete ranked seasonal shortlist with exact Wave Viewer links.",
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": True,
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
            },
        },
        "openai/widgetDescription": (
            "Shows every returned TradeWave opportunity in rank order. Detailed charts appear "
            "only after the user selects a pattern for analysis."
        ),
        "openai/widgetCSP": {
            "redirect_domains": [MAIN_PUBLIC_URL],
        },
    },
)
def ranked_opportunities_widget() -> str:
    """Fresh result-level template that overrides stale single-pattern scan metadata."""
    return PATTERN_WIDGET_HTML


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
# fabricating a catalyst, or laundering a neutral coin-flip into "mild support."
_HANDOFF = (
    "Research hand-off: optional current-context check. First present the complete TradeWave evidence above, including "
    "its charts, risk statistics, failed years, and Wave Viewer link. Then, only when relevant to "
    "the user's question, note that this is a SEASONAL + ML statistical edge and TradeWave is blind to "
    "fundamentals, news, macro, valuation, and upcoming earnings/events. Before treating it as a "
    "complete current-market view, you may use your own tools to check whether current news, macro, or recent price action "
    "SUPPORT or THREATEN this seasonal thesis - search for them; do NOT assume a catalyst exists and "
    "do NOT invent one. If TradeWave reports neutral / no edge, report that as a genuine 'no edge' "
    "finding (computed independently of any news), not as mild support. Then synthesize, keeping "
    "explicit which facts are TradeWave's data vs your own research; if you can't verify it, say so."
)


def _primary_card(data: Any) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    card = data.get("card")
    if isinstance(card, dict):
        return card
    opportunities = data.get("opportunities")
    if isinstance(opportunities, list) and opportunities and isinstance(opportunities[0], dict):
        return opportunities[0]
    return None


def _rich_lead(text: str, data: Any, handoff: bool = False):
    """Return text plus native MCP image blocks for the winner's evidence charts.

    Rendering is fail-soft: response data and the Wave Viewer link still ship if the
    optional image renderer is unavailable on a node.
    """
    card = _primary_card(data)
    viewer = card.get("wave_viewer") if isinstance(card, dict) else None
    viewer_url = viewer.get("url") if isinstance(viewer, dict) else None
    viewer_label = (
        (viewer.get("label") or "Open this exact pattern in TradeWave")
        if isinstance(viewer, dict) else "Open this exact pattern in TradeWave"
    )
    if viewer_url:
        # Put the action before the JSON and duplicate it at the envelope top. This is
        # intentionally redundant: it prevents the model from overlooking a late nested
        # field and inventing manual navigation steps for an exact pattern we can link.
        text += (
            "\n\nOpen this exact pattern in TradeWave: "
            "[%s](%s)\nUse this exact URL; do not reconstruct the setup manually."
            % (viewer_label, viewer_url)
        )
        if isinstance(data, dict):
            data = {
                "primary_action": {
                    "type": "open_exact_pattern",
                    "label": viewer_label,
                    "url": viewer_url,
                    "instruction": ("Show this clickable action in the answer. If asked how to "
                                    "view the setup, repeat this URL instead of navigation steps."),
                },
                **data,
            }
    rendered = []
    if card and card.get("chart"):
        try:
            rendered = render_card_charts(card)
        except Exception as exc:  # noqa: BLE001 - visualization must never fail the tool
            log.warning("MCP chart rendering failed for %s: %s", card.get("symbol"), exc)
    out = _lead(text, data, handoff=handoff)
    if not rendered and not viewer_url:
        return out
    content: list[Any] = [out]
    if viewer_url:
        content.append(ResourceLink(
            type="resource_link",
            name="tradewave_exact_pattern",
            title=viewer_label,
            uri=viewer_url,
            description=("Open the exact market, symbol, entry date, holding period, and "
                         "lookback returned by this TradeWave analysis."),
            mimeType="text/html",
        ))
    for label, png in rendered:
        content.extend([label, Image(data=png, format="png")])
    return content


def _widget_text_fallback(data: dict[str, Any]) -> str:
    """Compact evidence that remains useful when a host cannot render MCP Apps.

    MCP App ``structuredContent`` is intended for the embedded view and is not
    guaranteed to enter the model's context.  Keep the ranked rows and the top
    setup's yearly path evidence in ordinary text as a portable fallback.
    """
    cards: list[dict[str, Any]] = []
    if isinstance(data.get("card"), dict):
        cards = [data["card"]]
    elif isinstance(data.get("opportunities"), list):
        cards = [card for card in data["opportunities"] if isinstance(card, dict)]
    if not cards:
        return ""

    def _number(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _pct(value: Any, *, probability: bool = False) -> Optional[str]:
        number = _number(value)
        if number is None:
            return None
        if probability and abs(number) <= 1:
            number *= 100
        return f"{number:+.2f}%"

    lines = [f"Ranked shortlist ({len(cards)} returned patterns, in rank order):"]
    for index, card in enumerate(cards, start=1):
        setup = card.get("setup") if isinstance(card.get("setup"), dict) else card
        stats = card.get("stats") if isinstance(card.get("stats"), dict) else card
        ml = card.get("ml") if isinstance(card.get("ml"), dict) else card
        rank = card.get("rank") or index
        symbol = card.get("symbol") or "Pattern"
        direction = (card.get("direction") or card.get("bias") or "").upper()
        entry = setup.get("entry_date") or card.get("entry_date")
        exit_date = setup.get("exit_date") or card.get("exit_date")
        hold_days = setup.get("hold_days") or card.get("hold_days")
        win_rate = _number(stats.get("historical_win_rate"))
        if win_rate is not None and abs(win_rate) <= 1:
            win_rate *= 100

        pieces = [f"{rank}. {symbol}{f' {direction}' if direction else ''}"]
        if entry or exit_date or hold_days:
            window = f"{entry or '?'} to {exit_date or '?'}"
            if hold_days is not None:
                window += f" ({hold_days} days)"
            pieces.append(window)
        if win_rate is not None:
            years = stats.get("years") or card.get("years")
            pieces.append(f"win rate {win_rate:.0f}%{f' over {years} years' if years else ''}")
        avg = _pct(stats.get("avg_return_pct"))
        median = _pct(stats.get("median_return_pct"))
        sharpe = _number(stats.get("sharpe_ratio"))
        ml_prob = _pct(ml.get("ml_win_prob"), probability=True)
        if avg:
            pieces.append(f"average {avg}")
        if median:
            pieces.append(f"median {median}")
        if sharpe is not None:
            pieces.append(f"Sharpe {sharpe:.2f}")
        if ml_prob:
            pieces.append(f"ML win probability {ml_prob.lstrip('+')}")
        lines.append(" | ".join(pieces))

    chart = cards[0].get("chart") if isinstance(cards[0].get("chart"), dict) else {}
    bars = chart.get("per_year_bars") if isinstance(chart, dict) else None
    if isinstance(bars, list) and bars:
        yearly = []
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            final = _pct(bar.get("net_pct"))
            worst = _pct(bar.get("mae_pct"))
            best = _pct(bar.get("mfe_pct"))
            detail = f"{bar.get('year', '?')}: final {final or 'n/a'}"
            if worst and best:
                detail += f" (path {worst} to {best})"
            yearly.append(detail)
        if yearly:
            lines.append("Top setup year-by-year evidence: " + "; ".join(yearly))
    return "\n".join(lines)


def _widget_lead(text: str, data: dict[str, Any], handoff: bool = False) -> CallToolResult:
    """Return a proper MCP App result for ChatGPT while keeping the exact link portable.

    ``structuredContent`` is shared by the model and the widget. The widget renders
    directly from the gateway's chart arrays, so chart visibility no longer depends on
    whether a host chooses to display ordinary MCP ``image`` content blocks.
    """
    payload = copy.deepcopy(data)
    card = _primary_card(payload)
    viewer = card.get("wave_viewer") if isinstance(card, dict) else None
    viewer_url = viewer.get("url") if isinstance(viewer, dict) else None
    viewer_label = (
        (viewer.get("label") or "Open this exact pattern in TradeWave")
        if isinstance(viewer, dict) else "Open this exact pattern in TradeWave"
    )
    if viewer_url:
        payload = {
            "primary_action": {
                "type": "open_exact_pattern",
                "label": viewer_label,
                "url": viewer_url,
                "instruction": (
                    "Show this clickable action in the answer. If asked how to view the setup, "
                    "repeat this URL instead of navigation steps."
                ),
            },
            **payload,
        }
        text += (
            "\n\nOpen this exact pattern in TradeWave: "
            "[%s](%s)\nUse this exact URL; do not reconstruct the setup manually."
            % (viewer_label, viewer_url)
        )

    disclaimer = _extract_disclaimer(payload)
    if disclaimer:
        payload["disclaimer"] = disclaimer
    fallback = _widget_text_fallback(payload)
    if fallback:
        text += f"\n\n{fallback}"
    if handoff:
        text += f"\n\n{_HANDOFF}"
    if disclaimer:
        text += f"\n\nDisclaimer: {disclaimer}"

    # Widget-bearing tools already expose the exact URL in ordinary Markdown,
    # structuredContent, and the embedded app. Some MCP hosts do not support a
    # ResourceLink content block and inject a noisy warning into the model context.
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=payload,
    )


def _scan_widget_lead(text: str, data: dict[str, Any], handoff: bool = False) -> CallToolResult:
    """Return the ranked-list component explicitly at result level.

    ChatGPT can retain an older tool descriptor after a connector update. The result-level
    resource URI is authoritative for this call and prevents that stale descriptor from
    mounting the single-pattern chart component for a plural scan.
    """
    result = _widget_lead(text, data, handoff=handoff)
    result.meta = {
        "ui": {"resourceUri": SCAN_WIDGET_URI},
        "openai/outputTemplate": SCAN_WIDGET_URI,
    }
    return result


def _lead(text: str, data: Any, handoff: bool = False) -> str:
    """Prepend a one-line conversational lead to the gateway's structured JSON.

    The gateway's Pattern Card JSON is the source of truth and is returned verbatim
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


def _present_cards(data: Any, empty_msg: str, found_msg, *, widget: bool = False):
    """Pass through a Pattern Card list/payload, gracefully handling Pro stubs + empties.

    - UpgradeRequired stub -> clear Pro-required message + upgrade_url (never an error).
    - Otherwise prepend a one-line lead and forward the structured JSON unchanged.
    """
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    if isinstance(data, dict):
        count = data.get("count")
        if count == 0 or (count is None and not data.get("opportunities")):
            return _widget_lead(empty_msg, data) if widget else _lead(empty_msg, data)
    lead = found_msg(data) if callable(found_msg) else found_msg
    return (_widget_lead(lead, data, handoff=True) if widget
            else _rich_lead(lead, data, handoff=True))


# ===========================================================================
# FLAGSHIP TOOLS - reach for these first. Each forwards the gateway's
# Pattern Cards (the one source of truth) with a short conversational lead.
# ===========================================================================

# ---------------------------------------------------------------------------
# Flagship: find_best_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "THE flagship 'what should I trade right now' tool. Scan across markets, rank every "
        "seasonal setup by Sharpe ratio (mirroring TradeWave's own daily-pick selection: "
        "filter then rank by Sharpe), and return ready, evidence-backed Pattern Cards with "
        "an extend_research hand-off (headline + verdict + receipts + a copyable order ticket). "
        "REACH FOR THIS FIRST whenever the user asks 'find me a trade', 'what's good right now', "
        "'anything seasonal in gold / energy / tech', 'best setups this month', or wants a ranked "
        "shortlist - it replaces stitching list_markets + get_seasonal_opportunities yourself. "
        "Scans the caller's in-scope markets by default; narrow with `markets`. Honest by design: "
        "weak setups come back as neutral rather than a manufactured trade. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "Present the complete returned shortlist in rank order; the gateway has already sorted it. "
        "This scan is intentionally LIST-FIRST and never mounts the single-pattern evidence "
        "widget; its ranked-list component keeps every returned pattern visible with its "
        "extend_research hand-off. When the user "
        "focuses on one pattern, call analyze_symbol to open its detailed card, exact Wave Viewer "
        "link, and charts. Pass view='table' only when the user explicitly wants a compact list."
    ),
    annotations=ToolAnnotations(
        title="Find the best TradeWave opportunities",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
@_widget_tool_errors
async def find_best_opportunities(
    markets: Annotated[Optional[list[str] | str], Field(description=(
        "Market ids, list_markets names, or common aliases ('sp500','crypto','europe') to "
        "scan - a list (['2','11']) or CSV ('2,11' / 'S&P 500 STOCKS,ETFs'). Omit to scan a "
        "LIQUID EQUITIES CORE (DOW 30, NASDAQ 100, S&P 500, ETFs) intersected with your "
        "scope, NOT every in-scope market - pass markets explicitly to scan others."))] = None,
    window: Annotated[Optional[str], Field(description=(
        "Entry-date window: 'now' (default), 'next_2_weeks', 'next_month', or a "
        "'YYYY-MM-DD..YYYY-MM-DD' range. The scan evaluates opportunities AS OF the window's "
        "START date (the underlying primitive is keyed to one entry date) and keeps only "
        "setups whose entry_date falls inside the window - it does not re-scan every date in "
        "the range. 'now' starts today (~10 trading days wide)."))] = None,
    direction: Annotated[Optional[str], Field(description=(
        "'long' or 'short'. Omit for both."))] = None,
    min_win_rate: Annotated[Optional[float], Field(description=(
        "Minimum historical_win_rate 0..1 (share of profitable years), e.g. 0.65."))] = None,
    min_years: Annotated[Optional[int], Field(description=(
        "Trust filter - require at least N years of tested history."))] = None,
    min_days: Annotated[Optional[int], Field(description=(
        "Minimum pattern length (holding period) in calendar days, e.g. 10."))] = None,
    max_days: Annotated[Optional[int], Field(description=(
        "Maximum pattern length (holding period) in calendar days, e.g. 90. Use "
        "min_days+max_days for a day RANGE like 10-90."))] = None,
    min_avg_return: Annotated[Optional[float], Field(description=(
        "Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%)."))] = None,
    min_median_return: Annotated[Optional[float], Field(description=(
        "Minimum median seasonal profit in PERCENT."))] = None,
    min_sharpe: Annotated[Optional[float], Field(description=(
        "Minimum Sharpe ratio, e.g. 1.5."))] = None,
    pe_cycle: Annotated[Optional[str], Field(description=(
        "Presidential election cycle mode: 'consecutive' (default, consecutive years) or "
        "'pe' (the current presidential-cycle position only)."))] = None,
    years: Annotated[Optional[int], Field(description=(
        "Lookback - how many years to scan for patterns (5-98, data-dependent; default 10). "
        "In PE mode this is the number of PE-position occurrences."))] = None,
    min_winning_years: Annotated[Optional[int], Field(description=(
        "Of those `years`, the minimum that must be WINNERS - i.e. the win-rate floor "
        "(year2). DEFAULTS to ~90% of `years` (so a bare years=20 gives a valid 20-18; you "
        "rarely need to set it). It must stay inside the market's DETECTION BAND: TradeWave "
        "only detects patterns that won a market-specific share of years (about 75-90%+, "
        "e.g. S&P 500 ~85%, Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback). An "
        "out-of-band value like 20-9 is REJECTED with the valid range - never lower it "
        "below the floor. This is a multi-market scan, so if a value is out of band for "
        "some scanned markets the response includes a lookback_note naming them."))] = None,
    rank_by: Annotated[Optional[str], Field(description=(
        "Ranking method. Default 'sharpe' (mirrors TradeWave's daily-pick selection). "
        "Options: edge|win_rate|sharpe|ml|avg_return."))] = None,
    limit: Annotated[Optional[int], Field(description=(
        "Max cards to return (tier-capped to the caller's opp_limit)."))] = None,
    view: Annotated[Optional[str], Field(description=(
        "Verbosity. 'decision' (default) = the complete ranked shortlist with a lean read per "
        "pattern; 'table' = compact ranked rows; 'full' = complete cards for every result."))] = None,
    include_chart: Annotated[Optional[bool], Field(description=(
        "Compatibility parameter. Ranked scans remain list-first; use analyze_symbol on a "
        "selected result to render its TradeWave charts."))] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    _bind_request_key(ctx)
    params: dict[str, Any] = {"view": view or "decision"}
    if markets is not None:
        params["markets"] = _csv(markets)
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
    data = await _get("/scan", params)
    if isinstance(data, dict) and data.get("opportunities"):
        # This rides inside every live scan response, so hosts see the rule even when their
        # versioned tool-description snapshot is stale. A model can often answer a focused
        # follow-up from lean shortlist data, but doing so suppresses the per-symbol MCP App:
        # only a fresh analyze_symbol result can mount the exact pattern's widget.
        data = {
            "focused_followup": {
                "required_tool": "analyze_symbol",
                "when": (
                    "The user focuses on, asks how good, requests details for, revisits, or "
                    "asks to open any one symbol/pattern from this result."
                ),
                "instruction": (
                    "Call analyze_symbol on that turn even if this shortlist contains enough "
                    "statistics for a text answer. The fresh call automatically renders the "
                    "TradeWave evidence widget; never require the user to ask for a chart."
                ),
            },
            **data,
        }

    def _found(d: Any) -> str:
        n = d.get("count") if isinstance(d, dict) else None
        win = d.get("window") if isinstance(d, dict) else None
        by = d.get("rank_by", "edge") if isinstance(d, dict) else "edge"
        where = f" entering its {win} window" if win == "now" else (f" for {win}" if win else "")
        return f"Found {n} ranked seasonal setup(s){where}, sorted by {by}. Top of the list first:"

    if _is_upgrade_stub(data):
        return _scan_widget_lead(_format_upgrade(data), data)
    if isinstance(data, dict):
        count = data.get("count")
        if count == 0 or (count is None and not data.get("opportunities")):
            return _scan_widget_lead(
                "No high-conviction seasonal setups matched those filters right now. "
                "Try widening the markets, the window, or lowering min_win_rate.",
                data,
            )
    return _scan_widget_lead(_found(data), data, handoff=True)


# ---------------------------------------------------------------------------
# Flagship: analyze_symbol
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "The bundled deep-dive on ONE ticker - one call, the full evidence-backed answer. "
        "Returns a single rich Pattern Card (best setup + verdict + receipts + order ticket) plus "
        "the symbol's other setups, fused server-side so the win rate is consistent everywhere. "
        "REACH FOR THIS whenever the user names a specific symbol - 'what about GLD', 'analyze "
        "AAPL's seasonality', 'is now a good time for SPY', 'does CL have an edge'. "
        "This is mandatory on EVERY focused-symbol turn, including follow-ups after a prior "
        "shortlist; never reuse the old shortlist as the complete answer and never wait for an "
        "explicit chart request. Calling this tool is what mounts the TradeWave chart widget. "
        "It replaces stitching get_symbol_patterns + get_seasonal_pattern + the chart. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro), "
        "on eligible markets (0-4, 11). "
        "If the symbol has no real seasonal edge it returns neutral with an honest verdict. "
        "The default EVIDENCE view returns the complete TradeWave record, two native chart images "
        "(year-by-year MFE/MAE evidence and normalized seasonal trend), chart data/specifications, "
        "and an exact link that opens this pattern in Wave Viewer. Lead with this TradeWave evidence; "
        "outside news/fundamentals are optional current-context checks, never a substitute for it."
    ),
    annotations=ToolAnnotations(
        title="Analyze a TradeWave seasonal pattern",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta={
        "ui": {"resourceUri": PATTERN_WIDGET_URI},
        "openai/outputTemplate": PATTERN_WIDGET_URI,
        "openai/toolInvocation/invoking": "Building TradeWave evidence charts…",
        "openai/toolInvocation/invoked": "TradeWave evidence charts ready",
    },
    structured_output=True,
)
@_widget_tool_errors
async def analyze_symbol(
    symbol: Annotated[str, Field(description=(
        "Ticker symbol, e.g. 'GLD', 'AAPL', 'CL'. Required."))],
    market: Annotated[Optional[str], Field(description=(
        "Market id ('0'..'16'). Optional - the gateway resolves it when the symbol is "
        "unique."))] = None,
    direction: Annotated[Optional[str], Field(description=(
        "'long' or 'short'. Omit to let the best setup decide."))] = None,
    days_out: Annotated[Optional[int], Field(description=(
        "Preferred inclusive holding period in CALENDAR days: entry date is day 1 and "
        "the end date is entry_date + (days_out - 1). With entry_date, PINS the exact "
        "window; without it, biases setup selection."))] = None,
    entry_date: Annotated[Optional[str], Field(description=(
        "'YYYY-MM-DD'. PIN analysis to THIS exact opportunity (the 'click this one / "
        "deep-dive THIS setup' flow) instead of auto-picking the best."))] = None,
    pe_cycle: Annotated[Optional[str], Field(description=(
        "'consecutive' (default) or 'pe' - score the setup over presidential-election-"
        "cycle years (same phase as the entry year) instead of consecutive years."))] = None,
    years: Annotated[Optional[int], Field(description=(
        "Lookback length 1-99 (default 10) - how many years of history to score "
        "against."))] = None,
    period: Annotated[Optional[str], Field(description=(
        "A wave-viewer date-range preset to pin the window: a month ('jan'..'dec'), "
        "quarter ('q1'..'q4'), season ('spring','summer','fall','winter'), or "
        "'ytd'/'year_end'/'buy_hold'. Overrides entry_date/days_out when set."))] = None,
    reverse: Annotated[Optional[bool], Field(description=(
        "Invert the period to 'all of the year EXCEPT that window' (the reverse-date-"
        "range toggle)."))] = None,
    view: Annotated[Optional[str], Field(description=(
        "Verbosity. 'evidence' (default) or 'full' = the complete evidence card; "
        "'decision' = lean; 'table' = a compact row."))] = None,
    include_chart: Annotated[Optional[bool], Field(description=(
        "Compatibility parameter; the focused analysis always includes TradeWave chart data "
        "and its evidence widget. This value is ignored so users never have to request charts."))] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    _bind_request_key(ctx)
    params: dict[str, Any] = {"view": view or "evidence"}
    # A focused pattern analysis is the premium evidence experience, not a text-only endpoint.
    # Always request chart evidence—even if an older client explicitly sends false—so the user
    # never needs to know the magic phrase "show me a TradeWave chart".
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
    data = await _get(f"/analyze/{_seg(symbol)}", params)
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    sym = symbol.upper()
    card = data.get("card") if isinstance(data, dict) else None
    if isinstance(card, dict) and card.get("bias") == "neutral":
        return _widget_lead(
            f"{sym} has no high-conviction seasonal edge right now - here is the honest read:",
            data,
            handoff=True,
        )
    return _widget_lead(f"Here is the full seasonal deep-dive on {sym}:", data, handoff=True)


# ---------------------------------------------------------------------------
# Flagship: explain_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Today's AI daily pick presented as a full Pattern Card WITH its live, forward-tested "
        "track record - the strongest proof TradeWave can offer (the pick is made in advance, "
        "then scored later, so the record is real out-of-sample performance, not a backtest). "
        "REACH FOR THIS when the user asks for 'today's pick', 'the trade of the day', 'what is "
        "the AI recommending', or wants to see proof the seasonal patterns work before trusting them. "
        "Present the pick alongside its receipts (count of past picks, realized win rate, avg "
        "return) as forward-tested evidence. Two DISTINCT win rates appear: the card's "
        "historical_win_rate is the SEASONAL history (share of past years the window was "
        "profitable); track_record.win_rate is the LIVE, out-of-sample record of past daily "
        "picks. They are not the same number - don't conflate them."
    )
)
@_tool_errors
async def explain_pick(ctx: Optional[Context] = None) -> str:
    _bind_request_key(ctx)
    data = await _get("/daily-pick")
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
# Flagship: morning_briefing
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "The one-call MORNING BRIEFING. REACH FOR THIS on 'my briefing', 'good morning', "
        "'what's happening today', 'daily update', or any open-ended start-of-day prompt. "
        "Returns one compact payload: todays_pick (today's AI daily pick as a Pattern Card with "
        "its live forward-tested track record), track_record_summary (counts + the last 5 pick "
        "outcomes, losses included - the honest record), this_week (the top 5 distinct-symbol "
        "setups entering their seasonal window now, as compact ranked rows), and as_of. "
        "Composed server-side from the same gateway endpoints as explain_pick + "
        "whats_seasonal_now, so it is always consistent with them. Present the pick first, "
        "then the record, then what's opening this week."
    )
)
@_tool_errors
async def morning_briefing(ctx: Optional[Context] = None) -> str:
    _bind_request_key(ctx)
    calls = {
        "pick": ("/daily-pick", {"view": "decision"}),
        "record": ("/daily-pick/track-record", None),
        "scan": ("/scan", {"window": "now", "view": "table", "limit": 10}),
    }
    async def fetch(path, params):
        try:
            return await _get(path, params)
        except GatewayError as e:
            return {"unavailable": e.message}

    names = list(calls)
    fetched = await asyncio.gather(
        *(fetch(*calls[name]) for name in names)
    )
    results = dict(zip(names, fetched))

    pick = results["pick"]
    todays_pick = pick.get("card", pick) if isinstance(pick, dict) else pick

    record = results["record"]
    if isinstance(record, dict) and isinstance(record.get("summary"), dict):
        picks = record.get("picks") or []
        # last 5 outcomes, chronological, losses included - never curate the record.
        track_record_summary = {**record["summary"], "last_5": picks[-5:]}
    else:
        track_record_summary = record   # upgrade stub / unavailable note, passed through honestly

    scan = results["scan"]
    if isinstance(scan, dict) and isinstance(scan.get("opportunities"), list):
        rows, seen = [], set()
        for row in scan["opportunities"]:
            sym = row.get("symbol") if isinstance(row, dict) else None
            if sym in seen:
                continue
            seen.add(sym)
            rows.append(row)
            if len(rows) == 5:
                break
        this_week = rows
    else:
        this_week = scan

    payload = {
        "todays_pick": todays_pick,
        "track_record_summary": track_record_summary,
        "this_week": this_week,
        "as_of": (pick.get("as_of") if isinstance(pick, dict) else None)
                 or datetime.date.today().isoformat(),
    }
    return _lead(
        "Your TradeWave morning briefing - today's AI pick (with its live track record), "
        "the recent pick outcomes, and what's entering its seasonal window this week:",
        payload,
        handoff=True,
    )


# ---------------------------------------------------------------------------
# Flagship: whats_seasonal_now
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "The 'what is entering its seasonal window THIS WEEK' tool - the weekly digest. "
        "A focused scan of setups whose entry date falls within the next ~10 trading days, "
        "returned as ranked Pattern Cards. "
        "REACH FOR THIS on calendar-framed prompts: 'what's seasonal right now', 'anything "
        "opening this week', 'what should I be watching this week', the weekly digest. "
        "(It is a focused 'now'-window view of the scanner.) "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "Weak setups come back as neutral. Cards default to the lean DECISION view; pass "
        "view='table' for a compact ranked list or view='full' for receipts."
    )
)
@_tool_errors
async def whats_seasonal_now(
    markets: Annotated[Optional[list[str] | str], Field(description=(
        "Market ids, list_markets names, or common aliases ('sp500','crypto','europe') to "
        "scan - a list (['2','11']) or CSV ('2,11' / 'S&P 500 STOCKS,ETFs'). Omit to scan a "
        "liquid equities core (DOW 30, NASDAQ 100, S&P 500, ETFs) intersected with your "
        "scope, NOT every in-scope market - pass markets explicitly to scan others."))] = None,
    min_win_rate: Annotated[Optional[float], Field(description=(
        "Minimum historical_win_rate 0..1 (share of profitable years)."))] = None,
    view: Annotated[Optional[str], Field(description=(
        "Verbosity. 'decision' (default) = lean read; 'table' = compact ranked rows; "
        "'full' = full cards."))] = None,
    ctx: Optional[Context] = None,
) -> Any:
    # This tool can return FastMCP's unstructured mixed-content sequence (text,
    # ResourceLink, and optional Image blocks).  Do not annotate it as ``str``:
    # FastMCP would publish a string-only output schema and reject the valid
    # sequence during protocol serialization before the client receives it.
    _bind_request_key(ctx)
    params: dict[str, Any] = {"window": "now", "view": view or "decision"}
    if markets is not None:
        params["markets"] = _csv(markets)
    if min_win_rate is not None:
        params["min_win_rate"] = min_win_rate
    data = await _get("/scan", params)

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
        "symbol and returns their Pattern Cards together so they can be ranked head-to-head. "
        "REACH FOR THIS whenever the user names two or more symbols to weigh - 'GLD vs SLV', "
        "'compare AAPL, MSFT and NVDA seasonally', 'which of these has the better setup'. "
        "Each card carries its own edge score, win rate, and receipts; present them as a "
        "comparison and call out which has the strongest, most consistent edge. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro), "
        "on eligible markets."
    )
)
@_tool_errors
async def compare_opportunities(
    symbols: Annotated[list[str], Field(description=(
        "List of ticker symbols to compare, e.g. ['GLD', 'SLV', 'GDX']. Required, 2 or "
        "more."))],
    market: Annotated[Optional[str], Field(description=(
        "Market id ('0'..'16') applied to every symbol. Omit to let the gateway resolve "
        "each."))] = None,
    view: Annotated[Optional[str], Field(description=(
        "Verbosity per card. 'decision' (default) = lean read for an easy head-to-head; "
        "'full' = full receipts on each."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    async def analyze_one(sym):
        params: dict[str, Any] = {"view": view or "decision"}
        if market is not None:
            params["market"] = market
        try:
            data = await _get(f"/analyze/{_seg(sym)}", params)
        except GatewayError as e:
            return {"symbol": sym, "error": e.message, "card": None}
        if _is_upgrade_stub(data):
            return {"symbol": sym, "requires": "upgrade", "reason": data.get("reason"),
                    "message": data.get("message"), "upgrade_url": data.get("upgrade_url")}
        return {"symbol": sym, **(data if isinstance(data, dict) else {"data": data})}

    results = await asyncio.gather(*(analyze_one(sym) for sym in symbols))
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
        "in all other tools), names, ML eligibility, in-scope flag, and each market's "
        "pattern_detection coverage (scan vs per-symbol) with an example win-rate band - so you can "
        "answer 'which markets support per-symbol patterns?' or 'what lookback/min_winning_years is "
        "valid for this market?' from data."
    )
)
@_tool_errors
async def list_markets(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = await _get("/markets")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: whoami
# ---------------------------------------------------------------------------


# Tier-aware analyze example for whoami: (market_id, symbol) in preference order
# (ML-eligible markets first so the example shows ML). Every symbol is verified to exist
# in that market's roster, so the example NEVER errors for the caller's scope.
_ANALYZE_EXAMPLES: list[tuple[str, str]] = [
    ("11", "GLD"), ("2", "AAPL"), ("0", "AAPL"), ("1", "AAPL"), ("3", "AAPL"),
    ("4", "AAPL"), ("7", "BZ"), ("9", "EURUSD"), ("8", "EURUSD"), ("5", "SPX"),
    ("6", "SPX"), ("10", "US10Y"), ("16", "BTC-USD"),
]


@mcp.tool(
    description=(
        "Who am I / what can I do here. Returns the caller's plan tier, how many ML scorings "
        "they have left today (null = unlimited), the markets in their scope, and a few example "
        "prompts. REACH FOR THIS FIRST on 'what can you do', 'what plan am I on', 'how many ML "
        "calls do I have left', or to decide which markets are worth scanning before calling "
        "find_best_opportunities."
    )
)
@_tool_errors
async def whoami(ctx: Optional[Context] = None) -> str:
    _bind_request_key(ctx)
    data = await _get("/me")
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    tier = data.get("tier_name") or data.get("tier") or "your"
    rem = data.get("ml_remaining_today")
    ml_txt = "unlimited ML scorings/day" if rem is None else f"{rem} ML scoring(s) left today"
    in_scope = data.get("markets_in_scope") or []
    names = ", ".join(m.get("name", m.get("id")) for m in in_scope[:8])
    payload = dict(data)
    # Build the analyze example from the caller's OWN scope - a free user must get an
    # example that works on their plan, not one that errors (e.g. GLD on an S&P-only scope).
    scope_ids = {str(m.get("id")) for m in in_scope}
    analyze_example = next(
        (f"Analyze {sym}'s seasonality" for mid, sym in _ANALYZE_EXAMPLES if mid in scope_ids),
        None,
    )
    payload["example_prompts"] = [p for p in (
        "Find me the best seasonal trades right now",
        analyze_example,
        "What's today's AI daily pick and its track record?",
        "Give me my morning briefing",
    ) if p]
    # Structural in-chat teaser disclosure: teaser_state rides /me verbatim; when it is
    # active, add a belt-and-suspenders sentence to the human lead so the model always
    # discloses that the elevated in-chat scope is temporary and what it reverts to.
    teaser_line = ""
    ts = data.get("teaser_state") if isinstance(data, dict) else None
    if isinstance(ts, dict) and ts.get("active"):
        ends = ts.get("ends_at") or "the end of the window"
        scope = ts.get("post_teaser_scope") or "your"
        teaser_line = (" In-chat teaser active until %s; reverts to %s scope after."
                       % (ends, scope))
    return _lead(
        f"You are on the {tier} plan with {ml_txt}. In-scope markets: {names}.{teaser_line} "
        "Try one of the example prompts below:",
        payload,
    )


# ---------------------------------------------------------------------------
# Tool: describe_tradewave (the self-describing / how-to-research guide)
# ---------------------------------------------------------------------------

_TRADEWAVE_GUIDE = (
    "HOW TRADEWAVE WORKS + HOW TO RESEARCH WITH IT\n\n"
    "What it is: TradeWave finds recurring SEASONAL price patterns (calendar windows that have paid "
    "off across many years) and scores each with a 62-feature ML model. Every result is a Pattern Card: "
    "a headline + verdict, the entry/hold window, win rates, an ML probability, an edge_score, and "
    "year-by-year receipts. The daily AI pick also carries a LIVE forward-tested track record. "
    "Seasonal patterns only: TradeWave never returns raw prices - moves are percentages and the seasonal curve "
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
    "neutral means TradeWave found NO statistical edge - a genuine 'no edge' finding, not weak support.\n\n"
    "THE SEASONAL ANALYSIS KNOBS (what they mean + how to choose them):\n"
    "  - Two modes: DETECTION (find patterns: find_best_opportunities / get_seasonal_opportunities / "
    "get_symbol_patterns) vs ANALYSIS (score one setup: analyze_symbol / get_opportunity_chart). The "
    "`years` knob is constrained on DETECTION (see below) and free (1-99, scored on the fly) on ANALYSIS.\n"
    "  - years (lookback) + min_winning_years (of those years, the minimum that won) = the WIN-RATE "
    "FLOOR (year2/year1). Patterns only exist INSIDE a per-market band, so min_winning_years is not "
    "free: e.g. at a 20-year lookback S&P 500 allows 17-20 (~85%+), Wilshire 18-20 (~90%), FOREX "
    "Liquid 14-20 (~70%). A combo below the floor (e.g. 20-9 = 45%) is impossible and is rejected with "
    "the valid range. You rarely set it: omit it and it DEFAULTS to ~90% of years (years=20 -> 20-18).\n"
    "  - min_days / max_days = the pattern's HOLDING-PERIOD length in days (use both for a range, e.g. "
    "10-90). pe_cycle = consecutive (default) vs presidential-cycle. direction = long|short.\n"
    "  - Coverage: 15 active markets; per-SYMBOL patterns (get_symbol_patterns) exist for DOW 30, "
    "NASDAQ 100, S&P 500, Futures & Commodities, FOREX Liquid only - for other markets use "
    "find_best_opportunities. ML scores cover US stocks + ETFs (ids 0-4, 11). Call list_markets for "
    "each market's scope and pattern coverage.\n\n"
    "Nothing here is personalized investment advice."
)


@mcp.tool(
    description=(
        "How TradeWave works + how to research with it, AND what its seasonal analysis variables mean. "
        "REACH FOR THIS on 'what is this / how do I read these cards / how do the win rates differ / "
        "what does min_winning_years (or years / lookback / the win-rate band) mean / how do I pick a "
        "lookback / which markets have what', or before relying on a card. Returns the research method "
        "(edge -> extend with your own tools -> synthesize), the glossary (the three distinct win "
        "rates, edge_score, the Trend Chart), the SEASONAL KNOBS (lookback years + min_winning_years "
        "and the per-market win-rate band, day-range, market coverage), what TradeWave can and cannot "
        "tell you, and how to act on a Pattern Card."
    )
)
async def describe_tradewave(ctx: Optional[Context] = None) -> str:
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
@_tool_errors
async def list_symbols(
    market: Annotated[str, Field(description=(
        "Market id, e.g. '0', '2', '11'. Use list_markets to find valid ids."))],
    ctx: Context,
) -> str:
    _bind_request_key(ctx)
    data = await _get(f"/markets/{_seg(market)}/symbols")
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_seasonal_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer find_best_opportunities (which scans across markets, "
        "scores by edge, and returns ready Pattern Cards) unless you need this exact slice: the "
        "raw single-market opportunity list for ONE entry date. "
        "Find seasonal trade setups for ONE market at a single entry_date, ranked by historical "
        "edge. This primitive is single-date - it does NOT widen across a date window (use "
        "find_best_opportunities for windows). Filters by direction (long/short) and minimum win rate. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro)."
    )
)
@_tool_errors
async def get_seasonal_opportunities(
    market: Annotated[str, Field(description=(
        "Market id (permanent key '0'..'16'). Required."))],
    from_date: Annotated[Optional[str], Field(description=(
        "The single entry_date to evaluate, ISO 8601 (YYYY-MM-DD). Defaults to today."))] = None,
    to_date: Annotated[Optional[str], Field(description=(
        "Accepted but IGNORED - this primitive does not widen across a date window "
        "(window_supported is false). Use find_best_opportunities for a date window."))] = None,
    direction: Annotated[Optional[str], Field(description=(
        "'long' or 'short'. Omit for both."))] = None,
    min_win_rate: Annotated[Optional[float], Field(description=(
        "Minimum historical win rate 0..1, e.g. 0.65."))] = None,
    min_days: Annotated[Optional[int], Field(description=(
        "Minimum pattern length (holding period) in calendar days, e.g. 10."))] = None,
    max_days: Annotated[Optional[int], Field(description=(
        "Maximum pattern length (holding period) in calendar days, e.g. 90. Use "
        "min_days+max_days for a day RANGE like 10-90."))] = None,
    min_avg_return: Annotated[Optional[float], Field(description=(
        "Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%)."))] = None,
    min_median_return: Annotated[Optional[float], Field(description=(
        "Minimum median seasonal profit in PERCENT."))] = None,
    min_sharpe: Annotated[Optional[float], Field(description=(
        "Minimum Sharpe ratio, e.g. 1.5."))] = None,
    pe_cycle: Annotated[Optional[str], Field(description=(
        "Presidential election cycle mode: 'consecutive' (default) or 'pe' (the current "
        "cycle position)."))] = None,
    years: Annotated[Optional[int], Field(description=(
        "Lookback - years to scan for patterns (5-98, default 10; PE-position occurrences "
        "in pe mode)."))] = None,
    min_winning_years: Annotated[Optional[int], Field(description=(
        "Of those years, the minimum that must be WINNERS - the win-rate floor (year2). "
        "DEFAULTS to ~90% of years (so years=20 gives a valid 20-18). This is a SINGLE-"
        "market call, so it is validated against that market's DETECTION BAND (about "
        "75-90%+, market-specific); an out-of-band value (e.g. 20-9) returns a clear error "
        "with the valid range."))] = None,
    limit: Annotated[Optional[int], Field(description=(
        "Max results to return (tier-capped: free=3, dev=100, pro=1000, business=5000)."))] = None,
    ctx: Optional[Context] = None,
) -> str:
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
    data = await _get("/opportunities", params)
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
@_tool_errors
async def get_symbol_patterns(
    symbol: Annotated[str, Field(description=(
        "Ticker symbol, e.g. 'DOV', 'GLD'."))],
    market: Annotated[str, Field(description=(
        "Market id containing the symbol. Per-symbol patterns exist for ids 0,1,2,7,9 "
        "only (other markets return a clear error)."))],
    pe_cycle: Annotated[Optional[str], Field(description=(
        "'consecutive' (default) or 'pe' (current presidential-cycle position)."))] = None,
    years: Annotated[Optional[int], Field(description=(
        "Lookback years for pattern detection (default 10)."))] = None,
    min_winning_years: Annotated[Optional[int], Field(description=(
        "Of those years, the minimum WINNERS - the win-rate floor (year2). Defaults to "
        "~90% of years; must stay within this market's detection band (an out-of-band "
        "value returns a clear error with the valid range)."))] = None,
    min_days: Annotated[Optional[int], Field(description=(
        "Minimum pattern length in days."))] = None,
    max_days: Annotated[Optional[int], Field(description=(
        "Maximum pattern length in days (use with min_days for a range)."))] = None,
    min_avg_return: Annotated[Optional[float], Field(description=(
        "Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%)."))] = None,
    min_sharpe: Annotated[Optional[float], Field(description=(
        "Minimum Sharpe ratio."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    params: dict[str, Any] = {"market": market}
    for _k, _v in (("pe_cycle", pe_cycle), ("years", years), ("min_winning_years", min_winning_years),
                   ("min_days", min_days), ("max_days", max_days),
                   ("min_avg_return", min_avg_return), ("min_sharpe", min_sharpe)):
        if _v is not None:
            params[_k] = _v
    data = await _get(f"/securities/{_seg(symbol)}/patterns", params=params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_seasonal_pattern
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer analyze_symbol (it already bundles these stats with the "
        "setup, receipts, and ML into one Pattern Card) unless you need this exact slice: the bare "
        "aggregate stats with nothing else. "
        "Get aggregate seasonal pattern statistics for a symbol - Sharpe ratio, win rate, "
        "average and median return, and other summary stats. "
        "Returns stats only - no raw price series."
    )
)
@_tool_errors
async def get_seasonal_pattern(
    market: Annotated[str, Field(description=(
        "Market id containing the symbol."))],
    symbol: Annotated[str, Field(description=(
        "Ticker symbol."))],
    pe_cycle: Annotated[Optional[str], Field(description=(
        "Presidential cycle filter: 'consecutive' (default), 'pe' (current cycle "
        "position), or a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'."))] = None,
    years: Annotated[Optional[int], Field(description=(
        "Lookback count (number of years, or number of cycle occurrences when pe_cycle "
        "is set)."))] = None,
    period: Annotated[Optional[str], Field(description=(
        "Date-range PRESET: month 'jan'..'dec', quarter 'q1'..'q4', season "
        "'spring'|'summer'|'fall'|'winter', 'ytd', 'year_end', or 'buy_hold'."))] = None,
    reverse: Annotated[Optional[bool], Field(description=(
        "If true, use the COMPLEMENT of the window (e.g. period='mar' + reverse=true = "
        "all year except March). A full-year (buy_hold) range cannot be reversed."))] = None,
    ctx: Optional[Context] = None,
) -> str:
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
    data = await _get(f"/patterns/{_seg(market)}/{_seg(symbol)}", params=params or None)
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
@_tool_errors
async def get_opportunity_chart(
    market: Annotated[str, Field(description=(
        "Market id."))],
    symbol: Annotated[str, Field(description=(
        "Ticker symbol."))],
    entry_date: Annotated[Optional[str], Field(description=(
        "Entry date for the setup, ISO 8601 (YYYY-MM-DD)."))] = None,
    days_out: Annotated[Optional[int], Field(description=(
        "Inclusive holding period in CALENDAR days: entry date is day 1 and the end "
        "date is entry_date + (days_out - 1)."))] = None,
    direction: Annotated[Optional[str], Field(description=(
        "'long' or 'short'."))] = None,
    years: Annotated[Optional[str], Field(description=(
        "Lookback window label (stays a string, e.g. '10', '20')."))] = None,
    pe_cycle: Annotated[Optional[str], Field(description=(
        "Presidential cycle filter for the curve: 'consecutive' (default), 'pe' (current "
        "cycle position), or a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'."))] = None,
    period: Annotated[Optional[str], Field(description=(
        "Date-range PRESET (overrides entry_date/days_out): a month 'jan'..'dec', a "
        "quarter 'q1'..'q4', a season 'spring'|'summer'|'fall'|'winter', 'ytd' (year to "
        "date), 'year_end' (today to year end), or 'buy_hold' (Jan 1 to Jan 1, full "
        "year)."))] = None,
    reverse: Annotated[Optional[bool], Field(description=(
        "If true, use the COMPLEMENT of the window - everything except it (e.g. "
        "period='mar' + reverse=true = all year except March). A full-year (buy_hold) "
        "range cannot be reversed."))] = None,
    ctx: Optional[Context] = None,
) -> str:
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
    data = await _get("/seasonal-chart", params)
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
        "Input: a list of {symbol, date, days_out, direction} dicts. days_out is the "
        "inclusive CALENDAR-day count: date is day 1. "
        "Output: ml_score (0-100), win_prob (0-1), pred_return %, pred_mfe %."
    )
)
@_tool_errors
async def score_opportunities(
    opportunities: Annotated[list[dict[str, Any]], Field(description=(
        "List of opportunity dicts, each with keys: symbol (str, ticker symbol), date "
        "(str, entry date YYYY-MM-DD), days_out (int, inclusive CALENDAR-day count; "
        "entry date is day 1), direction "
        "(str, 'long' or 'short')."))],
    ctx: Context,
) -> str:
    _bind_request_key(ctx)
    data = await _post("/score", {"opportunities": opportunities})
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_daily_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Low-level primitive. Prefer explain_pick (it returns the same pick as a full Pattern Card "
        "WITH its live forward-tested track record - the strongest proof) unless you need this "
        "exact slice: the bare daily-pick payload with no receipts. "
        "Get today's AI-selected daily pick - the single ML-ranked seasonal opportunity "
        "TradeWave highlights each day. "
        "Includes symbol, direction, holding period, pattern summary, and ML scores."
    )
)
@_tool_errors
async def get_daily_pick(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = await _get("/daily-pick")
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
        "historical accuracy before trusting the seasonal patterns. Returns the full history with "
        "per-pick return %, result (win/loss/open), and summary stats (count, win rate, "
        "avg return). This is the verifiable performance record - free-tier accessible."
    )
)
@_tool_errors
async def get_pick_track_record(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = await _get("/daily-pick/track-record")
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

        class _McpPathAlias:
            """ASGI wrapper: serve the legacy /mcp path identically to the root endpoint,
            FOREVER - published setup instructions point clients at POST /mcp and must
            keep working. Rewrites only the exact /mcp (and /mcp/) path; everything else
            (root, /.well-known/oauth-*) passes through untouched."""

            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope.get("type") == "http" and scope.get("path") in ("/mcp", "/mcp/"):
                    scope = dict(scope)
                    scope["path"] = "/"
                    scope["raw_path"] = b"/"
                await self.app(scope, receive, send)

        # Mirrors FastMCP.run_streamable_http_async, with the alias wrapper in front
        # (the SDK offers no hook to mount the same session app at a second path).
        import uvicorn
        uvicorn.run(_McpPathAlias(mcp.streamable_http_app()),
                    host=mcp.settings.host, port=mcp.settings.port,
                    log_level=mcp.settings.log_level.lower())
    else:
        mcp.run(transport=args.transport)
