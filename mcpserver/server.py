"""
TradeWave MCP server - thin wrapper over the v1 HTTP gateway.

Each tool calls the corresponding /v1 endpoint through a bounded asynchronous
httpx pool. Authentication is resolved PER CALL:

  1. A WorkOS OAuth JWT from a remote client is signature/issuer/audience/expiry
     checked, then delegated to the loopback gateway with the dedicated MCP
     service key plus its WorkOS subject. The gateway resolves the real user's tier.
  2. A remote `tw_` BYOK credential is validated at connect time and forwarded
     on each call. Sessions are bound to the validated credential's subject.
  3. Stdio uses TRADEWAVE_API_KEY because each local process belongs to one user.

No market-data or entitlement logic lives here; the gateway remains authoritative.

Transport:
  - stdio  (default, for Claude Desktop / local CLI)
  - streamable-http  (the only supported remote transport)

Run (stdio, key from env):
  TRADEWAVE_API_KEY=tw_... ./venv-api/bin/python -m mcpserver.server

Remote transports require the complete canonical WorkOS/resource/service-key
tuple, a loopback listener and gateway URL, and no shared TRADEWAVE_API_KEY.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import functools
import hashlib
import ipaddress
import json
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, Optional, TypedDict
from urllib.parse import urlsplit

import httpx
from pydantic import Field
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

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
# only when fully configured.  Non-stdio startup validates this tuple and fails closed; a partial
# tuple is permitted only for import-time tooling and local stdio use.
WORKOS_AUTHKIT_DOMAIN: str = (os.environ.get("WORKOS_AUTHKIT_DOMAIN", "") or "").rstrip("/")
MCP_PUBLIC_URL: str = (os.environ.get("TW2_MCP_PUBLIC_URL", "") or "").rstrip("/")  # canonical resource / token audience
MCP_GATEWAY_KEY: str = os.environ.get("MCP_GATEWAY_KEY", "")
OAUTH_ENABLED: bool = bool(WORKOS_AUTHKIT_DOMAIN and MCP_PUBLIC_URL and MCP_GATEWAY_KEY)

_SERVICE_KEY_RE = re.compile(r"^tw_svc_[A-Za-z0-9_-]{43}$")

_DEV_MCP_PUBLIC_URL = "https://mcp-dev.trxstat.com"
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalise_public_hostname(hostname: str, *, source: str) -> str:
    """Return a safe, canonical hostname for an MCP Host/Origin allowlist."""
    if not hostname or hostname != hostname.strip() or hostname.endswith("."):
        raise ValueError(f"{source} contains an invalid hostname")

    try:
        return ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        pass

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"{source} contains an invalid hostname") from exc
    if len(ascii_hostname) > 253 or any(
        not _DNS_LABEL_RE.fullmatch(label) for label in ascii_hostname.split(".")
    ):
        raise ValueError(f"{source} contains an invalid hostname")
    return ascii_hostname


def _parse_mcp_public_endpoint(
    value: str, *, source: str, allow_bare_authority: bool
) -> tuple[str, str]:
    """Validate config and return ``(Host authority, HTTPS origin)``.

    ``TW2_MCP_PUBLIC_HOST`` historically accepts ``host[:port]`` (and an HTTPS
    URL for compatibility).  ``TW2_MCP_PUBLIC_URL`` must be a canonical HTTPS
    origin.  Userinfo and ambiguous URL components are rejected so untrusted
    text can never widen the SDK's DNS-rebinding allowlists.
    """
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{source} is empty")

    has_scheme = "://" in candidate
    if not has_scheme and not allow_bare_authority:
        raise ValueError(f"{source} must be an HTTPS origin")

    try:
        parsed = urlsplit(candidate if has_scheme else f"//{candidate}")
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError(f"{source} is not a valid public endpoint: {exc}") from exc

    if (
        (has_scheme and parsed.scheme.lower() != "https")
        or (not has_scheme and parsed.scheme)
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port < 1)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{source} must identify one canonical HTTPS origin")

    hostname = _normalise_public_hostname(hostname, source=source)
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = f"{display_host}:{port}" if port is not None else display_host
    return authority, f"https://{authority}"


def _configured_mcp_public_endpoint() -> tuple[str, str]:
    """Resolve the public MCP authority without silently selecting the wrong env."""
    explicit_host = (os.environ.get("TW2_MCP_PUBLIC_HOST") or "").strip()
    if explicit_host:
        return _parse_mcp_public_endpoint(
            explicit_host, source="TW2_MCP_PUBLIC_HOST", allow_bare_authority=True
        )
    if MCP_PUBLIC_URL:
        return _parse_mcp_public_endpoint(
            MCP_PUBLIC_URL, source="TW2_MCP_PUBLIC_URL", allow_bare_authority=False
        )
    return _parse_mcp_public_endpoint(
        _DEV_MCP_PUBLIC_URL, source="development MCP fallback", allow_bare_authority=False
    )


def _mcp_transport_security(bind_host: str, bind_port: int):
    """Build the SDK DNS-rebinding allowlists from validated endpoint config."""
    from mcp.server.transport_security import TransportSecuritySettings

    public_host, public_origin = _configured_mcp_public_endpoint()
    allowed_hosts = list(dict.fromkeys([
        public_host,
        f"{bind_host}:{bind_port}",
        "127.0.0.1",
        f"127.0.0.1:{bind_port}",
        "localhost",
        f"localhost:{bind_port}",
    ]))
    return TransportSecuritySettings(
        allowed_hosts=allowed_hosts,
        allowed_origins=[public_origin, f"http://127.0.0.1:{bind_port}"],
    )


def _validate_remote_startup_configuration(bind_host: str, bind_port: int) -> None:
    """Fail closed before serving a shared remote transport.

    A partial OAuth tuple used to silently downgrade the process to an ungated
    BYOK-only server.  A baked-in customer key also let a headerless remote
    client inherit shared credentials.  Neither is safe for a multi-customer
    endpoint, so every non-stdio process requires the complete, canonical OAuth
    resource-server tuple and forbids ``TRADEWAVE_API_KEY``.  The listener and
    gateway must both stay on loopback so nginx is the only public ingress and
    bearer credentials cannot be forwarded to an arbitrary host.
    """
    required = {
        "WORKOS_AUTHKIT_DOMAIN": WORKOS_AUTHKIT_DOMAIN,
        "TW2_MCP_PUBLIC_URL": MCP_PUBLIC_URL,
        "MCP_GATEWAY_KEY": MCP_GATEWAY_KEY,
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise RuntimeError(
            "remote MCP startup requires OAuth configuration: missing "
            + ", ".join(missing)
        )
    if not OAUTH_ENABLED:
        raise RuntimeError(
            "remote MCP OAuth construction does not match its complete configuration"
        )

    for name, value in (
        ("WORKOS_AUTHKIT_DOMAIN", WORKOS_AUTHKIT_DOMAIN),
        ("TW2_MCP_PUBLIC_URL", MCP_PUBLIC_URL),
    ):
        try:
            _, canonical_origin = _parse_mcp_public_endpoint(
                value, source=name, allow_bare_authority=False
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if value != canonical_origin:
            raise RuntimeError(f"{name} must be one canonical HTTPS origin")

    if not _SERVICE_KEY_RE.fullmatch(MCP_GATEWAY_KEY):
        raise RuntimeError("MCP_GATEWAY_KEY must be a dedicated tw_svc_ service key")
    if TRADEWAVE_API_KEY:
        raise RuntimeError(
            "TRADEWAVE_API_KEY must be unset for a shared remote MCP transport"
        )

    try:
        bind_ip = ipaddress.ip_address(bind_host)
    except ValueError as exc:
        raise RuntimeError("remote MCP bind host must be a loopback IP address") from exc
    if not bind_ip.is_loopback or not 1 <= bind_port <= 65535:
        raise RuntimeError(
            "remote MCP bind host/port must be a valid loopback-only listener"
        )

    try:
        gateway = urlsplit(API_BASE_URL)
        gateway_port = gateway.port
        gateway_ip = ipaddress.ip_address(gateway.hostname or "")
    except ValueError as exc:
        raise RuntimeError(
            "API_BASE_URL must be one canonical loopback HTTP /v1 URL"
        ) from exc
    if (
        gateway.scheme != "http"
        or not gateway_ip.is_loopback
        or gateway_port is None
        or not 1 <= gateway_port <= 65535
        or gateway.username is not None
        or gateway.password is not None
        or gateway.path != "/v1"
        or gateway.query
        or gateway.fragment
    ):
        raise RuntimeError("API_BASE_URL must be one canonical loopback HTTP /v1 URL")
    gateway_host = (
        f"[{gateway_ip.compressed}]"
        if gateway_ip.version == 6
        else gateway_ip.compressed
    )
    if API_BASE_URL != f"http://{gateway_host}:{gateway_port}/v1":
        raise RuntimeError("API_BASE_URL must be one canonical loopback HTTP /v1 URL")

# ---------------------------------------------------------------------------
# Per-connection auth (BYOK)
# ---------------------------------------------------------------------------
#
# For the remote Streamable HTTP transport the SDK plumbs the incoming
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
_BYOK_INFLIGHT_MAX = 128                                 # disconnected unique-key tasks
_BYOK_ADMISSION_ID_RE = re.compile(r"^acct_[0-9a-f]{64}$")
_BYOK_SESSION_SUBJECT_RE = re.compile(
    r"^byok:(acct_[0-9a-f]{64}):([0-9a-f]{64})$"
)
_byok_cache: dict[str, tuple[float, str | None]] = {}
# sha256(key) -> (expires, opaque gateway account id or None for a cached rejection)
# Concurrent initializes from several chats commonly carry the same customer key.  Share
# that one validation round-trip instead of spending one gateway /me request (and one
# customer rate-limit unit) per chat.  Tasks are keyed by the key hash; raw keys live only
# inside the short-lived validation coroutine and are never retained in a cache key.
_byok_inflight: dict[str, asyncio.Task[str | None]] = {}

_OAUTH_HTTP_TIMEOUT = 3.0
_OAUTH_FETCH_DEADLINE = 5.0
_OAUTH_JWKS_RESPONSE_MAX_BYTES = 512 * 1024
_OAUTH_TOKEN_MAX_LENGTH = 16 * 1024
_OAUTH_KID_MAX_LENGTH = 256
_JWKS_CACHE_TTL = 15 * 60.0
_JWKS_UNKNOWN_KID_TTL = 30.0
_JWKS_UNKNOWN_REFRESH_INTERVAL = 30.0
_JWKS_UNKNOWN_CACHE_MAX = 1024


def _byok_session_subject(key: str, admission_id: str) -> str:
    """Bind an SDK session to one key while retaining its account identity."""
    if not _BYOK_ADMISSION_ID_RE.fullmatch(admission_id):
        raise ValueError("invalid BYOK admission identity")
    return "byok:" + admission_id + ":" + hashlib.sha256(key.encode()).hexdigest()


class _AsyncJwksResolver:
    """Resolve WorkOS signing keys without blocking network I/O on the event loop.

    PyJWT's built-in JWK client is synchronous and refreshes the remote JWKS when it sees
    an unknown ``kid``. Calling it from ``verify_token`` therefore let one unauthenticated
    request freeze every MCP session for up to 30 seconds. This resolver uses httpx's async
    client, single-flights refreshes, caches keys, and negatively caches unknown kids. A
    global refresh cooldown also prevents an attacker from bypassing the negative cache by
    sending a stream of different random kids.
    """

    def __init__(self, authkit_domain: str) -> None:
        self.issuer = authkit_domain
        self._jwks_uri = authkit_domain + "/oauth2/jwks"
        self._keys: dict[str, Any] = {}
        self._keys_expires_at = 0.0
        self._last_refresh_at = 0.0
        self._unknown_kids: dict[str, float] = {}
        self._lock = asyncio.Lock()
        # Kept injectable for bounded-stream tests; production always uses the
        # pinned httpx.AsyncClient constructor.
        self._client_factory = httpx.AsyncClient

    async def _fetch_json(self, url: str) -> Any:
        if url != self._jwks_uri:
            raise ValueError("refusing an unpinned OAuth JWKS URL")
        max_bytes = _OAUTH_JWKS_RESPONSE_MAX_BYTES

        timeout = httpx.Timeout(_OAUTH_HTTP_TIMEOUT, connect=2.0)
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)

        async def fetch() -> Any:
            async with self._client_factory(
                timeout=timeout, limits=limits, trust_env=False
            ) as client:
                request = client.build_request(
                    "GET",
                    url,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                )
                response = await client.send(request, stream=True)
                try:
                    response.raise_for_status()
                    content_encoding = response.headers.get(
                        "content-encoding", "identity"
                    )
                    if content_encoding.strip().lower() not in ("", "identity"):
                        raise ValueError("OAuth JWKS response is encoded")
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        if not content_length.isascii() or not content_length.isdigit():
                            raise ValueError(
                                "OAuth JWKS response has an invalid Content-Length"
                            )
                        if int(content_length, 10) > max_bytes:
                            raise ValueError("OAuth JWKS response is oversized")

                    body = bytearray()
                    if response.is_stream_consumed:
                        # Some in-process/custom transports return an already-buffered
                        # response. Production network transports take the raw streaming
                        # branch below, where the bound applies before allocation.
                        buffered = response.content
                        if len(buffered) > max_bytes:
                            raise ValueError("OAuth JWKS response is oversized")
                        body.extend(buffered)
                    else:
                        async for chunk in response.aiter_raw():
                            if len(body) + len(chunk) > max_bytes:
                                raise ValueError("OAuth JWKS response is oversized")
                            body.extend(chunk)
                finally:
                    await response.aclose()
            try:
                return json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("OAuth JWKS response is not valid JSON") from exc

        try:
            async with asyncio.timeout(_OAUTH_FETCH_DEADLINE):
                return await fetch()
        except TimeoutError as exc:
            # HTTPX's read timeout is per chunk. An absolute deadline also stops a
            # byte-at-a-time peer from holding the global JWKS single-flight forever.
            raise httpx.ReadTimeout("OAuth JWKS absolute deadline exceeded") from exc

    def _remember_unknown(self, kid: str, now: float) -> None:
        # Prune expired entries first; if randomized kids still fill the cache, evict the
        # one closest to expiry. Raw tokens are never retained.
        self._unknown_kids = {
            cached_kid: expires
            for cached_kid, expires in self._unknown_kids.items()
            if expires > now
        }
        if len(self._unknown_kids) >= _JWKS_UNKNOWN_CACHE_MAX:
            oldest = min(self._unknown_kids, key=self._unknown_kids.get)
            self._unknown_kids.pop(oldest, None)
        self._unknown_kids[kid] = now + _JWKS_UNKNOWN_KID_TTL

    async def _refresh(self, now: float) -> None:
        import jwt as _jwt

        payload = await self._fetch_json(self._jwks_uri)
        raw_keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(raw_keys, list):
            raise ValueError("JWKS response does not contain a keys array")

        parsed: dict[str, Any] = {}
        # A legitimate issuer has very few active keys. Bound parsing work in case the
        # upstream response is unexpectedly huge.
        for raw_key in raw_keys[:100]:
            if not isinstance(raw_key, dict):
                continue
            kid = raw_key.get("kid")
            if (
                not isinstance(kid, str)
                or not kid
                or len(kid) > _OAUTH_KID_MAX_LENGTH
                or raw_key.get("kty") != "RSA"
                or raw_key.get("alg") != "RS256"
                or raw_key.get("use") != "sig"
            ):
                continue
            if kid in parsed:
                raise ValueError("JWKS response contains a duplicate kid")
            try:
                parsed[kid] = _jwt.PyJWK.from_dict(raw_key, algorithm="RS256").key
            except Exception as exc:  # noqa: BLE001 - one malformed key must not poison the set
                kid_hash = hashlib.sha256(kid.encode()).hexdigest()[:12]
                log.warning(
                    "MCP OAuth: ignored malformed JWKS key hash %s... (%s)",
                    kid_hash,
                    type(exc).__name__,
                )

        self._keys = parsed
        self._keys_expires_at = now + _JWKS_CACHE_TTL
        self._last_refresh_at = now
        for known_kid in parsed:
            self._unknown_kids.pop(known_kid, None)

    async def signing_key(self, token: str) -> Any:
        import jwt as _jwt

        if not isinstance(token, str) or len(token) > _OAUTH_TOKEN_MAX_LENGTH:
            raise _jwt.InvalidTokenError("access token is too large")
        header = _jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise _jwt.InvalidAlgorithmError("only RS256 access tokens are accepted")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid or len(kid) > _OAUTH_KID_MAX_LENGTH:
            raise _jwt.InvalidTokenError("access token has an invalid kid")

        now = time.monotonic()
        unknown_until = self._unknown_kids.get(kid, 0.0)
        if unknown_until > now:
            raise _jwt.InvalidTokenError("unknown signing key")

        cached = self._keys.get(kid)
        if cached is not None and self._keys_expires_at > now:
            return cached

        async with self._lock:
            # Another verifier may have refreshed while this request waited.
            now = time.monotonic()
            unknown_until = self._unknown_kids.get(kid, 0.0)
            if unknown_until > now:
                raise _jwt.InvalidTokenError("unknown signing key")
            cached = self._keys.get(kid)
            if cached is not None and self._keys_expires_at > now:
                return cached

            missing_key = cached is None
            if (
                cached is not None
                and self._keys_expires_at <= now
                and self._last_refresh_at
                and now - self._last_refresh_at < _JWKS_UNKNOWN_REFRESH_INTERVAL
            ):
                # A previous refresh failed after this key's fixed cache TTL. Back off
                # network retries, but never turn that cooldown into renewed key validity.
                raise _jwt.InvalidTokenError(
                    "signing keys are temporarily unavailable"
                )
            may_refresh_unknown = (
                not self._last_refresh_at
                or now - self._last_refresh_at >= _JWKS_UNKNOWN_REFRESH_INTERVAL
            )
            if not missing_key or may_refresh_unknown:
                try:
                    await self._refresh(now)
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    # A failed issuer request must enter the same global cooldown as a
                    # successful refresh.  Otherwise random, never-before-seen kids can
                    # force one outbound request apiece throughout a WorkOS outage and
                    # keep every uncached legitimate verifier queued behind this lock.
                    self._last_refresh_at = now
                    # Unknown keys and expired known keys always fail closed. In
                    # particular, do not move _keys_expires_at forward here: doing so on
                    # every outage retry would make a revoked signing key valid forever.
                    if cached is not None:
                        log.warning(
                            "MCP OAuth: JWKS refresh failed; expired key rejected"
                        )
                        raise _jwt.InvalidTokenError(
                            "signing keys are temporarily unavailable"
                        ) from exc
                    self._remember_unknown(kid, now)
                    raise _jwt.InvalidTokenError(
                        "signing keys are temporarily unavailable"
                    ) from exc

            key = self._keys.get(kid)
            if key is None:
                self._remember_unknown(kid, now)
                raise _jwt.InvalidTokenError("unknown signing key")
            return key


async def _validate_byok_key(key: str, key_hash: str) -> str | None:
    """Return the gateway-issued account identity for one accepted BYOK key."""
    try:
        # Authentication has its own small, short-timeout pool.  It must never queue
        # behind the long-running research pool: a saturated batch of 110-second scans
        # must not prevent a new customer from establishing an MCP session.
        async with _auth_client_context() as client:
            async with _auth_request_slot() as admitted:
                if not admitted:
                    # An unverified cold key must not establish a retained MCP session.
                    # Existing positive verdicts use the short cache above; saturation
                    # therefore rejects only keys for which we have no current proof.
                    return None
                request = client.build_request(
                    "GET",
                    f"{API_BASE_URL}/me",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                )
                resp = await _bounded_gateway_response(
                    client,
                    request,
                    max_bytes=_AUTH_RESPONSE_MAX_BYTES,
                    deadline_seconds=_AUTH_RESPONSE_DEADLINE,
                )
    except (httpx.HTTPError, GatewayError):
        return None
    admission_id = None
    if resp.status_code == 200:
        try:
            payload = resp.json()
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            candidate = payload.get("mcp_admission_id")
            if isinstance(candidate, str) and _BYOK_ADMISSION_ID_RE.fullmatch(
                candidate
            ):
                admission_id = candidate
    if resp.status_code == 200 or resp.status_code in (401, 403):
        if len(_byok_cache) >= _BYOK_CACHE_MAX:
            _byok_cache.clear()
        _byok_cache[key_hash] = (
            time.monotonic() + _BYOK_CHECK_TTL,
            admission_id,
        )
    return admission_id


def _finish_byok_validation(
    key_hash: str, task: asyncio.Task[str | None]
) -> None:
    """Remove a completed single-flight even when every original waiter disconnected."""
    if _byok_inflight.get(key_hash) is task:
        _byok_inflight.pop(key_hash, None)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        # Avoid an un-retrieved-task warning without exposing the raw key.  Normal gateway
        # failures are converted to a fail-closed None inside _validate_byok_key.  An
        # unexpected exception's text is not a safe-log contract and could contain a
        # transport-supplied request fragment, so retain only its class.
        log.error("MCP BYOK validation task failed for key hash %s... (%s)",
                  key_hash[:12], type(exc).__name__)


async def _byok_key_identity(key: str) -> str | None:
    """Resolve a tw_ key to its single-flight, opaque gateway account identity.

    200 with an exact ``mcp_admission_id`` -> accepted; 200 without that trusted
    account binding and 401/403 -> rejected (cached for _BYOK_CHECK_TTL). Anything
    else (gateway down, admission saturation, 5xx, 429) FAILS CLOSED and remains uncached.
    An unseen key cannot retain a new session until the gateway can prove it valid;
    already registered requests remain subject to the same periodic revalidation."""
    h = hashlib.sha256(key.encode()).hexdigest()
    now = time.monotonic()
    cached = _byok_cache.get(h)
    if cached and cached[0] > now:
        return cached[1]

    task = _byok_inflight.get(h)
    if task is None:
        # A disconnected ASGI request can cancel its waiter while the shielded
        # validation continues for the benefit of other same-key sessions.  Without
        # a separate cardinality bound, a distributed stream of unique keys could
        # therefore leave more background tasks than Uvicorn's in-flight request
        # limit accounts for.  Existing same-key single-flights remain reusable at
        # the limit; an unproved new key fails closed immediately.
        if len(_byok_inflight) >= _BYOK_INFLIGHT_MAX:
            return None
        # No await occurs between the lookup and assignment, so this is atomic on the
        # event loop.  Shielding prevents one disconnected client from cancelling the
        # validation all other same-key clients are awaiting.
        task = asyncio.create_task(_validate_byok_key(key, h))
        _byok_inflight[h] = task
        task.add_done_callback(functools.partial(_finish_byok_validation, h))
    try:
        return await asyncio.shield(task)
    finally:
        if task.done() and _byok_inflight.get(h) is task:
            _byok_inflight.pop(h, None)


async def _byok_key_valid(key: str) -> bool:
    """Compatibility predicate for tests/callers that need only a verdict."""
    return await _byok_key_identity(key) is not None


if OAUTH_ENABLED:
    import jwt as _jwt
    from mcp.server.auth.provider import AccessToken, TokenVerifier

    class WorkOSTokenVerifier(TokenVerifier):
        """Resource-server token validation. Accepts BOTH a WorkOS OAuth JWT (consumer apps:
        verified against the AuthKit JWKS, audience-bound to our MCP URL, exp-checked) and a tw_
        API key (dev tools / BYOK: format-accepted here, the gateway is the source of truth and
        validates it on the actual call) - so the two coexist behind the SDK auth gate."""

        def __init__(self) -> None:
            # Construction is deliberately network-free. Discovery/JWKS loading happens
            # asynchronously on first use and is then cached by the resolver.
            self._jwks = _AsyncJwksResolver(WORKOS_AUTHKIT_DOMAIN)
            log.info("MCP OAuth ENABLED: issuer=%s audience=%s",
                     WORKOS_AUTHKIT_DOMAIN, MCP_PUBLIC_URL)

        async def verify_token(self, token: str):
            if not isinstance(token, str) or not token or len(token) > _OAUTH_TOKEN_MAX_LENGTH:
                return None
            if token.startswith("tw_"):          # BYOK / dev tools - validate at CONNECT (below)
                admission_id = await _byok_key_identity(token)
                if admission_id is None:
                    # A garbage tw_ key must fail the CONNECT, exactly like a bad OAuth
                    # login - not surface later as a confusing per-tool 401.
                    log.info("MCP BYOK: connect rejected, gateway did not accept key hash %s...",
                             hashlib.sha256(token.encode()).hexdigest()[:12])
                    return None
                return AccessToken(token=token, client_id="byok", scopes=[], expires_at=None,
                                   resource=MCP_PUBLIC_URL,
                                   subject=_byok_session_subject(token, admission_id),
                                   claims={
                                       "mode": "byok",
                                       "key": token,
                                       "admission_id": admission_id,
                                   })
            try:                                  # WorkOS OAuth JWT - verify sig + aud + exp strictly
                key = await self._jwks.signing_key(token)
                # Accept the audience with or without a trailing slash: the SDK advertises the
                # resource as "<url>/" while the WorkOS resource indicator is often registered as
                # "<url>" - tolerate both so a slash can't silently break the connect.
                aud = [MCP_PUBLIC_URL, MCP_PUBLIC_URL + "/"]
                claims = _jwt.decode(token, key, algorithms=["RS256"], audience=aud,
                                     issuer=self._jwks.issuer,
                                     options={"require": ["exp", "sub"]})
            except Exception as e:                # noqa: BLE001 - any failure => unauthenticated
                # Exception text from JWT/parsing libraries is not a stable safe-log
                # contract and can echo attacker-controlled token fragments.  Preserve
                # the diagnostic class without ever interpolating token-derived text.
                # Invalid public bearer tokens are expected hostile input. Keep details at
                # debug level so unauthenticated traffic cannot flood the service journal.
                log.debug("MCP OAuth: token verification failed (%s)", type(e).__name__)
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
                               claims={
                                   "mode": "oauth",
                                   "workos_sub": sub,
                                   # Retain the already-validated issuer so the SDK's
                                   # session owner and our fairness bucket use its full
                                   # (client_id, issuer, subject) identity.
                                   "iss": claims.get("iss"),
                               })


def _request_from_context(ctx: Optional[Context]) -> Any | None:
    """Return the SDK HTTP request, or ``None`` for stdio/direct invocation."""
    if ctx is None:
        return None
    try:
        return ctx.request_context.request
    except (LookupError, AttributeError, ValueError):
        # The SDK raises ValueError outside an active request.  Stdio also has no
        # Starlette request; both are the supported single-user env-key boundary.
        return None


def _bearer_from_request(ctx: Optional[Context]) -> Optional[str]:
    """Extract the Bearer token from the incoming MCP request, if any.

    Returns the raw key for Streamable HTTP where the
    SDK exposes the Starlette Request on the RequestContext. Returns None for
    stdio (no HTTP request) or when no usable Authorization header is present.
    """
    request = _request_from_context(ctx)
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
        if at is not None:
            claims = at.claims or {}
            if claims.get("mode") == "oauth" and claims.get("workos_sub"):
                _request_principal.set({"mode": "oauth", "sub": claims["workos_sub"]})
            elif claims.get("mode") == "byok" and claims.get("key"):
                _request_principal.set({"mode": "byok", "key": claims["key"]})
            else:
                # Never downgrade an HTTP/SDK token with malformed or unfamiliar
                # claims to a process-wide credential.
                _request_principal.set(None)
            return
        if _request_from_context(ctx) is None:
            # OAuth configuration is process-global, but stdio deliberately has
            # no SDK access-token context.  It remains a one-user process and must
            # retain the documented TRADEWAVE_API_KEY behavior.
            key = TRADEWAVE_API_KEY or None
            _request_principal.set({"mode": "byok", "key": key} if key else None)
        else:
            # An HTTP request without the SDK's verified token context must never
            # inherit the stdio key, even if one was accidentally present.
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
    # The gateway is loopback, so compression buys nothing.  More importantly, a decompressor
    # can allocate one enormous decoded chunk before our streaming byte counter gets control.
    # Identity-only responses make the cap in _bounded_gateway_response a true pre-parse
    # allocation bound, including when a broken gateway would otherwise emit a gzip bomb.
    h: dict[str, str] = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }
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
# httpx's read timeout is an inactivity timeout, not a wall-clock budget: a
# peer that sends one tiny chunk every few seconds can otherwise retain a
# research slot forever.  Keep a separate end-to-end deadline just below the
# gateway worker timeout so every one of the 32 slots has a finite lifetime.
_GATEWAY_RESPONSE_DEADLINE = 115.0
_GATEWAY_MAX_CONNECTIONS = 32
_GATEWAY_MAX_KEEPALIVE_CONNECTIONS = 16
_GATEWAY_ADMISSION_WAIT_TIMEOUT = 5.0
# A result-count cap alone does not bound memory when one malformed gateway
# object (or a compressed response) is enormous.  Bound decoded bytes before
# JSON parsing so 32 concurrent calls cannot expand without limit inside the
# MCP cgroup.  Normal cards, charts, and the 250-row track record are far below
# this ceiling.
_GATEWAY_RESPONSE_MAX_BYTES = 4 * 1024 * 1024
_GATEWAY_ERROR_MESSAGE_MAX_CHARS = 1024
# Reserve a separate, deliberately small pool for connect-time API-key validation.
# These requests are cheap and have a five-second deadline; isolating them keeps MCP
# admission responsive even when every research connection is occupied by a cold scan.
_AUTH_MAX_CONNECTIONS = 4
_AUTH_MAX_KEEPALIVE_CONNECTIONS = 2
_AUTH_ADMISSION_WAIT_TIMEOUT = 1.0
_AUTH_RESPONSE_MAX_BYTES = 64 * 1024
# Admission has the same trickle risk as research traffic, but uses a much
# shorter budget so four stalled /me checks cannot block all new sessions.
_AUTH_RESPONSE_DEADLINE = 6.0
# Uvicorn otherwise accepts an unbounded number of concurrent ASGI tasks.  Nginx's
# limits are deliberately per public IP, so they do not protect the process from a
# distributed flood (and systemd TasksMax does not count asyncio coroutines).  This
# budget leaves ample room for 20 chats and their MCP session traffic while failing
# excess work at admission instead of growing memory without bound.
_MCP_MAX_INBOUND_CONCURRENCY = 128
_MCP_SOCKET_BACKLOG = 128
# Retained stateful sessions need their own bound: Uvicorn's concurrency limit
# controls in-flight requests, not the SDK manager's persistent session map.
_MCP_MAX_ACTIVE_SESSIONS = 128
# A single verified credential must not be able to retain the entire global
# session pool.  Twenty concurrent ChatGPT conversations are an explicit release
# target; four additional slots leave reconnect headroom without allowing the
# shared public demo key (or any one customer key) to starve every other user.
_MCP_MAX_SESSIONS_PER_PRINCIPAL = 24
# Stateful Streamable HTTP is required for published clients, but the SDK's default
# idle timeout is None.  Reap clients that vanish without DELETE so their
# session transports and task-group work cannot accumulate for the process lifetime.
_MCP_SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60.0

_TIMEOUT_RESULT = (
    "This large scan is still computing on the gateway - retry in a moment; the result "
    "will be cached and come back quickly."
)
_UNREACHABLE_RESULT = "The TradeWave gateway is temporarily unreachable. Try again in a moment."
_INVALID_GATEWAY_RESULT = (
    "The TradeWave gateway returned an invalid response. Try again in a moment."
)
_OVERSIZED_GATEWAY_RESULT = (
    "The TradeWave gateway returned an unexpectedly large response. Narrow the request "
    "and try again."
)
_GATEWAY_BUSY_RESULT = (
    "TradeWave research capacity is busy. Retry in a few seconds; completed results "
    "are cached."
)


class GatewayError(Exception):
    """A user-presentable gateway failure. `message` is returned VERBATIM as the tool
    result (via _tool_errors) - never a raw httpx string, which would leak the internal
    gateway URL to the model."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _new_gateway_client() -> httpx.AsyncClient:
    """Build the bounded client shared for one FastMCP application lifespan."""
    timeout = httpx.Timeout(_GATEWAY_TIMEOUT, connect=5.0, write=15.0, pool=10.0)
    limits = httpx.Limits(
        max_connections=_GATEWAY_MAX_CONNECTIONS,
        max_keepalive_connections=_GATEWAY_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=30.0,
    )
    return httpx.AsyncClient(timeout=timeout, limits=limits, trust_env=False)


def _new_auth_client() -> httpx.AsyncClient:
    """Build the reserved short-timeout client used only for auth admission checks."""
    timeout = httpx.Timeout(5.0, connect=2.0, write=5.0, pool=1.0)
    limits = httpx.Limits(
        max_connections=_AUTH_MAX_CONNECTIONS,
        max_keepalive_connections=_AUTH_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=30.0,
    )
    return httpx.AsyncClient(timeout=timeout, limits=limits, trust_env=False)


_gateway_client: Optional[httpx.AsyncClient] = None
_gateway_gate: Optional[asyncio.Semaphore] = None
_auth_client: Optional[httpx.AsyncClient] = None
_auth_gate: Optional[asyncio.Semaphore] = None
_gateway_pool_users = 0
_gateway_pool_lock = asyncio.Lock()


@asynccontextmanager
async def _gateway_client_context():
    """Yield the lifespan client, with an isolated fallback for direct/test calls."""
    client = _gateway_client
    if client is not None and not client.is_closed:
        yield client
        return
    async with _new_gateway_client() as fallback:
        yield fallback


@asynccontextmanager
async def _gateway_request_slot():
    """Cap research calls and fail fast instead of forming a 110-second queue."""
    gate = _gateway_gate
    if gate is None:
        yield
        return
    try:
        await asyncio.wait_for(
            gate.acquire(), timeout=_GATEWAY_ADMISSION_WAIT_TIMEOUT
        )
    except TimeoutError:
        raise GatewayError(_GATEWAY_BUSY_RESULT) from None
    try:
        yield
    finally:
        gate.release()


@asynccontextmanager
async def _auth_client_context():
    """Yield the reserved auth client, with an isolated fallback for direct/test calls."""
    client = _auth_client
    if client is not None and not client.is_closed:
        yield client
        return
    async with _new_auth_client() as fallback:
        yield fallback


@asynccontextmanager
async def _auth_request_slot():
    """Bound admission checks independently from long-running gateway research calls."""
    gate = _auth_gate
    if gate is None:
        yield True
        return
    try:
        await asyncio.wait_for(gate.acquire(), timeout=_AUTH_ADMISSION_WAIT_TIMEOUT)
    except TimeoutError:
        yield False
        return
    try:
        yield True
    finally:
        gate.release()


@asynccontextmanager
async def _shared_gateway_pool():
    """Reference-count one bounded outbound pool across every MCP session.

    The pinned SDK invokes the low-level server lifespan once *per stateful
    session*, not once per ASGI process.  Without this shared owner, 20 chats
    would silently create 20 independent 32-connection pools and defeat the
    global bound.  The Streamable HTTP app also holds one process-lifespan
    reference so connect-time auth checks have the reserved pool before the
    first session exists.
    """
    global _gateway_client, _gateway_gate, _auth_client, _auth_gate
    global _gateway_pool_users

    async with _gateway_pool_lock:
        if _gateway_pool_users == 0:
            client = _new_gateway_client()
            try:
                auth_client = _new_auth_client()
            except BaseException:
                await client.aclose()
                raise
            _gateway_client = client
            _gateway_gate = asyncio.Semaphore(_GATEWAY_MAX_CONNECTIONS)
            _auth_client = auth_client
            _auth_gate = asyncio.Semaphore(_AUTH_MAX_CONNECTIONS)
        else:
            client = _gateway_client
            auth_client = _auth_client
            if (
                client is None
                or auth_client is None
                or client.is_closed
                or auth_client.is_closed
            ):
                raise RuntimeError("shared MCP gateway pool is inconsistent")
        _gateway_pool_users += 1

    try:
        yield {"gateway_client": client, "auth_client": auth_client}
    finally:
        close_client = None
        close_auth_client = None
        async with _gateway_pool_lock:
            _gateway_pool_users -= 1
            if _gateway_pool_users < 0:
                raise RuntimeError("shared MCP gateway pool reference underflow")
            if _gateway_pool_users == 0:
                close_client = _gateway_client
                close_auth_client = _auth_client
                _gateway_client = None
                _gateway_gate = None
                _auth_client = None
                _auth_gate = None
        if close_client is not None and close_auth_client is not None:
            await asyncio.gather(close_client.aclose(), close_auth_client.aclose())


@asynccontextmanager
async def _mcp_lifespan(_server: FastMCP):
    """Give each SDK session a reference to the process-wide bounded pools."""
    async with _shared_gateway_pool() as state:
        yield state


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
    if (
        isinstance(msg, str)
        and msg.strip()
        and len(msg.strip()) <= _GATEWAY_ERROR_MESSAGE_MAX_CHARS
    ):
        msg = msg.strip()
        if code == "rate_limited":
            msg += " - wait a few seconds and retry; results are cached."
        return msg
    return (f"The TradeWave gateway returned an error (HTTP {exc.response.status_code}). "
            "Try again in a moment.")


async def _bounded_gateway_response(
    client: httpx.AsyncClient,
    request: httpx.Request,
    *,
    max_bytes: int = _GATEWAY_RESPONSE_MAX_BYTES,
    deadline_seconds: float | None = None,
) -> httpx.Response:
    """Read one identity response with hard byte and wall-clock caps.

    ``AsyncClient.get`` buffers the entire decoded body before returning.  Using
    the streaming API plus an identity-only request lets us reject an oversized
    body before it becomes an unbounded per-request allocation.  Reject an
    encoded response before iterating it: httpx's decoder may otherwise allocate
    one giant decoded chunk before yielding control to this counter.  The returned
    response is a small, fully buffered copy so existing status/error handling
    never depends on a closed network stream.  The explicit asyncio deadline is
    intentionally distinct from httpx's per-chunk inactivity timeout: even a
    peer that continuously trickles bytes must release its bounded pool slot.
    """
    if deadline_seconds is None:
        deadline_seconds = _GATEWAY_RESPONSE_DEADLINE
    response: httpx.Response | None = None
    try:
        async with asyncio.timeout(deadline_seconds):
            response = await client.send(request, stream=True)
            content_encoding = response.headers.get("content-encoding", "identity")
            if content_encoding.strip().lower() not in ("", "identity"):
                raise GatewayError(_INVALID_GATEWAY_RESULT)
            content_length = response.headers.get("content-length")
            if content_length is not None:
                if not content_length.isascii() or not content_length.isdigit():
                    raise GatewayError(_INVALID_GATEWAY_RESULT)
                if int(content_length, 10) > max_bytes:
                    raise GatewayError(_OVERSIZED_GATEWAY_RESULT)
            body = bytearray()
            if response.is_stream_consumed:
                buffered = response.content
                if len(buffered) > max_bytes:
                    raise GatewayError(_OVERSIZED_GATEWAY_RESULT)
                body.extend(buffered)
            else:
                async for chunk in response.aiter_raw():
                    if len(body) + len(chunk) > max_bytes:
                        raise GatewayError(_OVERSIZED_GATEWAY_RESULT)
                    body.extend(chunk)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )
    except TimeoutError:
        raise GatewayError(_TIMEOUT_RESULT) from None
    finally:
        if response is not None:
            await response.aclose()


async def _request(method: str, path: str, *, params: dict[str, Any] | None = None,
                   body: Any = None) -> Any:
    """One gateway round-trip. Every failure mode becomes a GatewayError whose message is
    safe to hand to the model as the tool result (see _tool_errors)."""
    url = f"{API_BASE_URL}{path}"
    try:
        async with _gateway_client_context() as client:
            async with _gateway_request_slot():
                if method == "GET":
                    request = client.build_request(
                        "GET", url, params=params, headers=_headers()
                    )
                else:
                    request = client.build_request(
                        "POST",
                        url,
                        json=body,
                        headers={**_headers(), "Content-Type": "application/json"},
                    )
                resp = await _bounded_gateway_response(client, request)
        resp.raise_for_status()
    except httpx.TimeoutException:
        raise GatewayError(_TIMEOUT_RESULT) from None
    except httpx.HTTPStatusError as exc:
        raise GatewayError(_friendly_http_error(exc)) from None
    except httpx.HTTPError:
        raise GatewayError(_UNREACHABLE_RESULT) from None
    try:
        return resp.json()
    except ValueError:
        # A proxy error page or truncated 2xx JSON must never escape as a raw decoder
        # exception (which can expose internals and bypass the friendly tool envelope).
        raise GatewayError(_INVALID_GATEWAY_RESULT) from None


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Asynchronous GET against the gateway. Returns parsed JSON."""
    return await _request(
        "GET",
        path,
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
        # Start every tool invocation from a clean principal and restore the caller's
        # context afterward. ASGI tasks are already isolated, but this also prevents a
        # reused/direct task from retaining one call's credential after completion.
        principal_token = _request_principal.set(None)
        try:
            try:
                return await fn(*args, **kwargs)
            except GatewayError as e:
                return e.message
        finally:
            _request_principal.reset(principal_token)
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

_READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_METERED_TOOL = ToolAnnotations(
    # These tools do not mutate market data, but can consume the caller's finite ML
    # allowance. MCP's read-only contract includes externally visible quota state.
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# Public input schemas should reject pathological payloads before they consume proxy,
# framework, or gateway resources. These limits are intentionally above normal usage and
# mirror the gateway's existing score cap / the 15-market catalog.
_BoundedText = Annotated[str, Field(min_length=1, max_length=128)]
_SymbolText = Annotated[str, Field(min_length=1, max_length=64)]
_SymbolPrefix = Annotated[str, Field(min_length=1, max_length=15)]
_MarketToken = Annotated[str, Field(min_length=1, max_length=64)]
_MarketList = Annotated[list[_MarketToken], Field(min_length=1, max_length=15)]
_MarketsInput = _MarketList | Annotated[str, Field(min_length=1, max_length=512)]
_Direction = Annotated[Literal["long", "short"], Field(max_length=5)]
_View = Annotated[Literal["decision", "table", "full"], Field(max_length=8)]
_RankBy = Annotated[
    Literal["edge", "win_rate", "sharpe", "ml", "avg_return"],
    Field(max_length=10),
]
_ListPeCycle = Annotated[Literal["consecutive", "pe"], Field(max_length=11)]
_ChartPeCycle = Annotated[
    Literal["consecutive", "pe", "pe0", "pe1", "pe2", "pe3"],
    Field(max_length=11),
]
_Period = Annotated[
    Literal[
        "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
        "nov", "dec", "q1", "q2", "q3", "q4", "spring", "summer", "fall",
        "winter", "ytd", "year_end", "buy_hold",
    ],
    Field(max_length=8),
]
_MlMarketToken = Annotated[
    Literal["0", "1", "2", "3", "4", "11"],
    Field(max_length=2),
]
_ChartYears = Annotated[
    str,
    Field(min_length=1, max_length=2, pattern=r"^(?:[1-9]|[1-9]\d)$"),
]

# LLM-facing tools need materially smaller result budgets than the bulk REST API.
# These are enforced both in the published schemas and immediately before the
# gateway call, including when a Python caller bypasses FastMCP validation.
_MCP_COMPACT_RESULT_MAX = 100
_MCP_FULL_RESULT_MAX = 25
_MCP_SCAN_DEFAULT_LIMIT = 10
_MCP_OPPORTUNITIES_DEFAULT_LIMIT = 25
_MCP_TRACK_RECORD_MAX_PICKS = 250


def _bounded_mcp_result_limit(
    limit: int | None,
    *,
    view: str | None = None,
    default: int,
) -> int:
    maximum = _MCP_FULL_RESULT_MAX if view == "full" else _MCP_COMPACT_RESULT_MAX
    value = default if limit is None else limit
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        qualifier = " for view='full'" if view == "full" else ""
        raise GatewayError(
            f"limit must be between 1 and {maximum}{qualifier} on the MCP interface."
        )
    return value


class _ScoreOpportunity(TypedDict):
    symbol: _SymbolText
    date: Annotated[str, Field(min_length=1, max_length=32)]
    days_out: Annotated[int, Field(ge=1, le=366)]
    direction: _Direction


_ScoreBatch = Annotated[list[_ScoreOpportunity], Field(min_length=1, max_length=100)]

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
# fabricating a catalyst, or laundering a neutral coin-flip into "mild support."
_HANDOFF = (
    "Research hand-off: this is a SEASONAL + ML statistical edge ONLY. TradeWave is BLIND to "
    "fundamentals, news, macro, valuation, and upcoming earnings/events. Before treating it as a "
    "complete view, use your OWN tools to check whether current news, macro, or recent price action "
    "SUPPORT or THREATEN this seasonal thesis - search for them; do NOT assume a catalyst exists and "
    "do NOT invent one. If TradeWave reports neutral / no edge, report that as a genuine 'no edge' "
    "finding (computed independently of any news), not as mild support. Then synthesize, keeping "
    "explicit which facts are TradeWave's data vs your own research; if you can't verify it, say so."
)


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


def _present_cards(data: Any, empty_msg: str, found_msg) -> str:
    """Pass through a Pattern Card list/payload, gracefully handling Pro stubs + empties.

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
# Pattern Cards (the one source of truth) with a short conversational lead.
# ===========================================================================

# ---------------------------------------------------------------------------
# Flagship: find_best_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=_METERED_TOOL,
    description=(
        "THE flagship 'what should I trade right now' tool. Scan across markets, rank every "
        "seasonal setup by Sharpe ratio (mirroring TradeWave's own daily-pick selection: "
        "filter then rank by Sharpe), and return ready, evidence-backed Pattern Cards "
        "(headline + verdict + receipts + a copyable order ticket). "
        "REACH FOR THIS FIRST whenever the user asks 'find me a trade', 'what's good right now', "
        "'anything seasonal in gold / energy / tech', 'best setups this month', or wants a ranked "
        "shortlist - it replaces stitching list_markets + get_seasonal_opportunities yourself. "
        "Scans a liquid-equities core within the caller's scope by default; pass `markets` to "
        "scan other in-scope markets. Honest by design: "
        "weak setups come back as neutral rather than a manufactured trade. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "Present the returned cards as-is; the gateway has already sorted them by rank. "
        "Progressive disclosure: each card defaults to the lean DECISION view (verdict + "
        "timing + edge + the extend_research hand-off). Pass view='table' for a compact ranked "
        "list, or view='full' when you need the per-year receipts and detail stats."
    )
)
@_tool_errors
async def find_best_opportunities(
    markets: Annotated[Optional[_MarketsInput], Field(description=(
        "Market ids, list_markets names, or common aliases ('sp500','crypto','europe') to "
        "scan - a list (['2','11']) or CSV ('2,11' / 'S&P 500 STOCKS,ETFs'). Omit to scan a "
        "LIQUID EQUITIES CORE (DOW 30, NASDAQ 100, S&P 500, ETFs) intersected with your "
        "scope, NOT every in-scope market - pass markets explicitly to scan others."))] = None,
    window: Annotated[Optional[_BoundedText], Field(description=(
        "Entry-date window: 'now' (default), 'next_2_weeks', 'next_month', or a "
        "'YYYY-MM-DD..YYYY-MM-DD' range. The scan evaluates opportunities AS OF the window's "
        "START date (the underlying primitive is keyed to one entry date) and keeps only "
        "setups whose entry_date falls inside the window - it does not re-scan every date in "
        "the range. 'now' starts today (~10 trading days wide)."))] = None,
    direction: Annotated[Optional[_Direction], Field(description=(
        "'long' or 'short'. Omit for both."))] = None,
    min_win_rate: Annotated[Optional[float], Field(ge=0, le=1, description=(
        "Minimum historical_win_rate 0..1 (share of profitable years), e.g. 0.65."))] = None,
    min_years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Trust filter - require at least N years of tested history."))] = None,
    min_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Minimum pattern length (holding period) in calendar days, e.g. 10."))] = None,
    max_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Maximum pattern length (holding period) in calendar days, e.g. 90. Use "
        "min_days+max_days for a day RANGE like 10-90."))] = None,
    min_avg_return: Annotated[Optional[float], Field(description=(
        "Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%)."))] = None,
    min_median_return: Annotated[Optional[float], Field(description=(
        "Minimum median seasonal profit in PERCENT."))] = None,
    min_sharpe: Annotated[Optional[float], Field(description=(
        "Minimum Sharpe ratio, e.g. 1.5."))] = None,
    pe_cycle: Annotated[Optional[_ListPeCycle], Field(description=(
        "Presidential election cycle mode: 'consecutive' (default, consecutive years) or "
        "'pe' (the current presidential-cycle position only)."))] = None,
    years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Lookback - how many years to scan for patterns (5-98, data-dependent; default 10). "
        "In PE mode this is the number of PE-position occurrences."))] = None,
    min_winning_years: Annotated[Optional[int], Field(ge=0, le=99, description=(
        "Of those `years`, the minimum that must be WINNERS - i.e. the win-rate floor "
        "(year2). DEFAULTS to ~90% of `years` (so a bare years=20 gives a valid 20-18; you "
        "rarely need to set it). It must stay inside the market's DETECTION BAND: TradeWave "
        "only detects patterns that won a market-specific share of years (about 75-90%+, "
        "e.g. S&P 500 ~85%, Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback). An "
        "out-of-band value like 20-9 is REJECTED with the valid range - never lower it "
        "below the floor. This is a multi-market scan, so if a value is out of band for "
        "some scanned markets the response includes a lookback_note naming them."))] = None,
    rank_by: Annotated[Optional[_RankBy], Field(description=(
        "Ranking method. Default 'sharpe' (mirrors TradeWave's daily-pick selection). "
        "Options: edge|win_rate|sharpe|ml|avg_return."))] = None,
    limit: Annotated[Optional[int], Field(ge=1, le=100, description=(
        "Max cards to return on the MCP interface (maximum 100; full view maximum 25). "
        "Defaults to 10 and remains tier-capped by the caller's plan."))] = None,
    view: Annotated[Optional[_View], Field(description=(
        "Verbosity. 'decision' (default) = the lean read per card; 'table' = a compact "
        "ranked row per setup; 'full' = the complete card incl. per-year receipts and "
        "detail stats."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    effective_view = view or "decision"
    params: dict[str, Any] = {
        "view": effective_view,
        "limit": _bounded_mcp_result_limit(
            limit,
            view=effective_view,
            default=_MCP_SCAN_DEFAULT_LIMIT,
        ),
    }
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
    data = await _get("/scan", params)

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
    annotations=_METERED_TOOL,
    description=(
        "The bundled deep-dive on ONE ticker - one call, the full evidence-backed answer. "
        "Returns a single rich Pattern Card (best setup + verdict + receipts + order ticket) plus "
        "the symbol's other setups, fused server-side so the win rate is consistent everywhere. "
        "REACH FOR THIS whenever the user names a specific symbol - 'what about GLD', 'analyze "
        "AAPL's seasonality', 'is now a good time for SPY', 'does CL have an edge'. "
        "It replaces stitching get_symbol_patterns + get_seasonal_pattern + the chart. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro), "
        "on eligible markets (0-4, 11). "
        "If the symbol has no real seasonal edge it returns neutral with an honest verdict. "
        "The card carries an extend_research block telling you exactly how to extend it with your "
        "OWN news / fundamentals / earnings tools. Defaults to the lean DECISION view; pass "
        "view='full' for the per-year receipts, or include_chart=true to also get the Trend Chart "
        "curve + per-year bars inline (chart DATA you draw; never an image)."
    )
)
@_tool_errors
async def analyze_symbol(
    symbol: Annotated[_SymbolText, Field(description=(
        "Ticker symbol, e.g. 'GLD', 'AAPL', 'CL'. Required."))],
    market: Annotated[Optional[_MarketToken], Field(description=(
        "Market id ('0'..'16'). Optional - the gateway resolves it when the symbol is "
        "unique."))] = None,
    direction: Annotated[Optional[_Direction], Field(description=(
        "'long' or 'short'. Omit to let the best setup decide."))] = None,
    days_out: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Preferred holding period in calendar days. With entry_date, PINS the exact "
        "window; without it, biases setup selection."))] = None,
    entry_date: Annotated[Optional[_BoundedText], Field(description=(
        "'YYYY-MM-DD'. PIN analysis to THIS exact opportunity (the 'click this one / "
        "deep-dive THIS setup' flow) instead of auto-picking the best."))] = None,
    pe_cycle: Annotated[Optional[_ListPeCycle], Field(description=(
        "'consecutive' (default) or 'pe' - score the setup over presidential-election-"
        "cycle years (same phase as the entry year) instead of consecutive years."))] = None,
    years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Lookback length 1-99 (default 10) - how many years of history to score "
        "against."))] = None,
    period: Annotated[Optional[_Period], Field(description=(
        "A wave-viewer date-range preset to pin the window: a month ('jan'..'dec'), "
        "quarter ('q1'..'q4'), season ('spring','summer','fall','winter'), or "
        "'ytd'/'year_end'/'buy_hold'. Overrides entry_date/days_out when set."))] = None,
    reverse: Annotated[Optional[bool], Field(description=(
        "Invert the period to 'all of the year EXCEPT that window' (the reverse-date-"
        "range toggle)."))] = None,
    view: Annotated[Optional[_View], Field(description=(
        "Verbosity. 'decision' (default) = the lean read; 'full' = the complete card "
        "incl. per-year receipts and detail stats; 'table' = a single compact row."))] = None,
    include_chart: Annotated[Optional[bool], Field(description=(
        "If true, attach the Trend Chart curve (0-100 seasonal index) + per-year bars "
        "(each year's return with its favorable/adverse excursion band) inline as chart "
        "DATA."))] = None,
    ctx: Optional[Context] = None,
) -> str:
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
    data = await _get(f"/analyze/{_seg(symbol)}", params)
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    sym = symbol.upper()
    card = data.get("card") if isinstance(data, dict) else None
    if isinstance(card, dict) and card.get("bias") == "neutral":
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
    annotations=_READ_ONLY_TOOL,
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
    annotations=_METERED_TOOL,
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
    async def _briefing_call(path: str, params: Optional[dict[str, Any]]) -> Any:
        try:
            return await _get(path, params)
        except GatewayError as exc:
            # Fail-soft per section: a degraded briefing beats no briefing.
            return {"unavailable": exc.message}

    # These calls are independent. asyncio tasks inherit the current ContextVar context,
    # so every request keeps this MCP call's principal without blocking unrelated sessions.
    values = await asyncio.gather(*(
        _briefing_call(path, params) for path, params in calls.values()
    ))
    results = dict(zip(calls, values))

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
    annotations=_METERED_TOOL,
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
    markets: Annotated[Optional[_MarketsInput], Field(description=(
        "Market ids, list_markets names, or common aliases ('sp500','crypto','europe') to "
        "scan - a list (['2','11']) or CSV ('2,11' / 'S&P 500 STOCKS,ETFs'). Omit to scan a "
        "liquid equities core (DOW 30, NASDAQ 100, S&P 500, ETFs) intersected with your "
        "scope, NOT every in-scope market - pass markets explicitly to scan others."))] = None,
    min_win_rate: Annotated[Optional[float], Field(ge=0, le=1, description=(
        "Minimum historical_win_rate 0..1 (share of profitable years)."))] = None,
    view: Annotated[Optional[_View], Field(description=(
        "Verbosity. 'decision' (default) = lean read; 'table' = compact ranked rows; "
        "'full' = full cards."))] = None,
    ctx: Optional[Context] = None,
) -> str:
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


_COMPARE_MAX_SYMBOLS = 10
_COMPARE_MAX_CONCURRENCY = 4
_CompareSymbol = Annotated[str, Field(min_length=1, max_length=64)]


def _validated_compare_symbols(symbols: list[str]) -> list[str]:
    """Validate and case-insensitively de-duplicate while preserving first-seen order."""
    if not isinstance(symbols, list):
        raise GatewayError("symbols must be a list of 2 to 10 ticker symbols.")
    if len(symbols) < 2 or len(symbols) > _COMPARE_MAX_SYMBOLS:
        raise GatewayError("Compare between 2 and 10 ticker symbols at a time.")

    unique: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if not isinstance(symbol, str):
            raise GatewayError("Every comparison symbol must be a ticker string.")
        cleaned = symbol.strip()
        if not cleaned or len(cleaned) > 64:
            raise GatewayError("Every comparison symbol must contain 1 to 64 characters.")
        identity = cleaned.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(cleaned)
    if len(unique) < 2:
        raise GatewayError("Provide at least 2 distinct ticker symbols to compare.")
    return unique


@mcp.tool(
    annotations=_METERED_TOOL,
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
    symbols: Annotated[list[_CompareSymbol], Field(
        min_length=2,
        max_length=_COMPARE_MAX_SYMBOLS,
        description=(
        "List of ticker symbols to compare, e.g. ['GLD', 'SLV', 'GDX']. Required, 2 or "
        "more; maximum 10. Duplicates are removed case-insensitively."))],
    market: Annotated[Optional[_MarketToken], Field(description=(
        "Market id ('0'..'16') applied to every symbol. Omit to let the gateway resolve "
        "each."))] = None,
    view: Annotated[Optional[_View], Field(description=(
        "Verbosity per card. 'decision' (default) = lean read for an easy head-to-head; "
        "'full' = full receipts on each."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    unique_symbols = _validated_compare_symbols(symbols)
    semaphore = asyncio.Semaphore(_COMPARE_MAX_CONCURRENCY)

    async def _analyze_one(sym: str) -> dict[str, Any]:
        params: dict[str, Any] = {"view": view or "decision"}
        if market is not None:
            params["market"] = market
        async with semaphore:
            try:
                data = await _get(f"/analyze/{_seg(sym)}", params)
            except GatewayError as exc:
                # Fail-soft per symbol: degrade that row, never break the comparison.
                return {"symbol": sym, "error": exc.message, "card": None}
        if _is_upgrade_stub(data):
            # The ML daily-limit stub surfaced - keep the comparison going, note it.
            return {"symbol": sym, "requires": "upgrade", "reason": data.get("reason"),
                    "message": data.get("message"), "upgrade_url": data.get("upgrade_url")}
        return {"symbol": sym, **(data if isinstance(data, dict) else {"data": data})}

    # gather preserves input order while the semaphore prevents comparison calls from
    # monopolizing the shared gateway pool.
    results = await asyncio.gather(*(_analyze_one(sym) for sym in unique_symbols))
    payload = {"count": len(results), "symbols": unique_symbols, "comparison": results}
    return _lead(
        f"Side-by-side seasonal comparison of {len(unique_symbols)} symbol(s) - compare edge score, "
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
    annotations=_READ_ONLY_TOOL,
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
    annotations=_READ_ONLY_TOOL,
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
    # Internal account-equality material is required at bearer admission but is not
    # useful model context and must not become a user-facing identifier.
    payload.pop("mcp_admission_id", None)
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
    annotations=_READ_ONLY_TOOL,
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
    annotations=_READ_ONLY_TOOL,
    description=(
        "Low-level primitive. Prefer find_best_opportunities / analyze_symbol unless you need "
        "this exact slice (the symbol roster of one market). "
        "List a safe page of tradeable symbols in a specific market. The default page is 100 "
        "symbols; use `prefix` to narrow and `limit` (maximum 1000) to control the page. "
        "Use when the user asks what stocks, futures, or ETFs are in a market, "
        "or to discover valid symbols. "
        "Pass the market id from list_markets (e.g. '2' for S&P 500 stocks)."
    )
)
@_tool_errors
async def list_symbols(
    market: Annotated[_MarketToken, Field(description=(
        "Market id, e.g. '0', '2', '11'. Use list_markets to find valid ids."))],
    prefix: Annotated[Optional[_SymbolPrefix], Field(description=(
        "Optional case-insensitive ticker prefix, e.g. 'AA' matches AAPL and AAL."))] = None,
    limit: Annotated[Optional[int], Field(ge=1, le=1000, description=(
        "Maximum symbols returned. Defaults to 100; maximum 1000."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    params: dict[str, Any] = {"limit": limit or 100}
    if prefix is not None:
        params["prefix"] = prefix
    data = await _get(f"/markets/{_seg(market)}/symbols", params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_seasonal_opportunities
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=_METERED_TOOL,
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
    market: Annotated[_MarketToken, Field(description=(
        "Market id (permanent key '0'..'16'). Required."))],
    from_date: Annotated[Optional[_BoundedText], Field(description=(
        "The single entry_date to evaluate, ISO 8601 (YYYY-MM-DD). Defaults to today."))] = None,
    direction: Annotated[Optional[_Direction], Field(description=(
        "'long' or 'short'. Omit for both."))] = None,
    min_win_rate: Annotated[Optional[float], Field(ge=0, le=1, description=(
        "Minimum historical win rate 0..1, e.g. 0.65."))] = None,
    min_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Minimum pattern length (holding period) in calendar days, e.g. 10."))] = None,
    max_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Maximum pattern length (holding period) in calendar days, e.g. 90. Use "
        "min_days+max_days for a day RANGE like 10-90."))] = None,
    min_avg_return: Annotated[Optional[float], Field(description=(
        "Minimum average seasonal profit in PERCENT (e.g. 5 means >= 5%)."))] = None,
    min_median_return: Annotated[Optional[float], Field(description=(
        "Minimum median seasonal profit in PERCENT."))] = None,
    min_sharpe: Annotated[Optional[float], Field(description=(
        "Minimum Sharpe ratio, e.g. 1.5."))] = None,
    pe_cycle: Annotated[Optional[_ListPeCycle], Field(description=(
        "Presidential election cycle mode: 'consecutive' (default) or 'pe' (the current "
        "cycle position)."))] = None,
    years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Lookback - years to scan for patterns (5-98, default 10; PE-position occurrences "
        "in pe mode)."))] = None,
    min_winning_years: Annotated[Optional[int], Field(ge=0, le=99, description=(
        "Of those years, the minimum that must be WINNERS - the win-rate floor (year2). "
        "DEFAULTS to ~90% of years (so years=20 gives a valid 20-18). This is a SINGLE-"
        "market call, so it is validated against that market's DETECTION BAND (about "
        "75-90%+, market-specific); an out-of-band value (e.g. 20-9) returns a clear error "
        "with the valid range."))] = None,
    limit: Annotated[Optional[int], Field(ge=1, le=100, description=(
        "Max results to return on the MCP interface (default 25, maximum 100, and still "
        "tier-capped by the caller's plan)."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    params: dict[str, Any] = {
        "market": market,
        "limit": _bounded_mcp_result_limit(
            limit,
            default=_MCP_OPPORTUNITIES_DEFAULT_LIMIT,
        ),
    }
    if from_date is not None:
        params["from"] = from_date
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
    data = await _get("/opportunities", params)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_symbol_patterns (the wave-viewer pattern-dropdown list, named clearly)
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=_READ_ONLY_TOOL,
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
    symbol: Annotated[_SymbolText, Field(description=(
        "Ticker symbol, e.g. 'DOV', 'GLD'."))],
    market: Annotated[_MarketToken, Field(description=(
        "Market id containing the symbol. Per-symbol patterns exist for ids 0,1,2,7,9 "
        "only (other markets return a clear error)."))],
    pe_cycle: Annotated[Optional[_ListPeCycle], Field(description=(
        "'consecutive' (default) or 'pe' (current presidential-cycle position)."))] = None,
    years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Lookback years for pattern detection (default 10)."))] = None,
    min_winning_years: Annotated[Optional[int], Field(ge=0, le=99, description=(
        "Of those years, the minimum WINNERS - the win-rate floor (year2). Defaults to "
        "~90% of years; must stay within this market's detection band (an out-of-band "
        "value returns a clear error with the valid range)."))] = None,
    min_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Minimum pattern length in days."))] = None,
    max_days: Annotated[Optional[int], Field(ge=1, le=366, description=(
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
    annotations=_READ_ONLY_TOOL,
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
    market: Annotated[_MarketToken, Field(description=(
        "Market id containing the symbol."))],
    symbol: Annotated[_SymbolText, Field(description=(
        "Ticker symbol."))],
    pe_cycle: Annotated[Optional[_ChartPeCycle], Field(description=(
        "Presidential cycle filter: 'consecutive' (default), 'pe' (current cycle "
        "position), or a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'."))] = None,
    years: Annotated[Optional[int], Field(ge=1, le=99, description=(
        "Lookback count (number of years, or number of cycle occurrences when pe_cycle "
        "is set)."))] = None,
    period: Annotated[Optional[_Period], Field(description=(
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
    annotations=_READ_ONLY_TOOL,
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
    market: Annotated[_MarketToken, Field(description=(
        "Market id."))],
    symbol: Annotated[_SymbolText, Field(description=(
        "Ticker symbol."))],
    entry_date: Annotated[Optional[_BoundedText], Field(description=(
        "Entry date for the setup, ISO 8601 (YYYY-MM-DD)."))] = None,
    days_out: Annotated[Optional[int], Field(ge=1, le=366, description=(
        "Holding period in calendar days."))] = None,
    direction: Annotated[Optional[_Direction], Field(description=(
        "'long' or 'short'."))] = None,
    years: Annotated[Optional[_ChartYears], Field(description=(
        "Lookback window label (stays a string, e.g. '10', '20')."))] = None,
    pe_cycle: Annotated[Optional[_ChartPeCycle], Field(description=(
        "Presidential cycle filter for the curve: 'consecutive' (default), 'pe' (current "
        "cycle position), or a specific position 'pe0' | 'pe1' | 'pe2' | 'pe3'."))] = None,
    period: Annotated[Optional[_Period], Field(description=(
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
    annotations=_METERED_TOOL,
    description=(
        "Low-level primitive. Prefer analyze_symbol / find_best_opportunities (they attach ML "
        "inline on eligible markets, metered per tier) unless you need this exact slice: ML scoring "
        "of an explicit hand-built list of setups. "
        "Score a list of seasonal opportunities with ML win-probability and predicted return. "
        "ML scores are available on every plan, metered daily (free 5/day, unlimited on Pro). "
        "When the daily ML allowance is spent the gateway returns a graceful nudge (never an error): "
        "a 200 body with requires='upgrade', reason='ml_daily_limit', and ml_remaining_today. "
        "ML scoring is available for markets 0-4 and 11 only. Score exactly ONE market per "
        "call with the top-level `market` parameter (defaults to '2', S&P 500 stocks); never "
        "put market inside an opportunity item because the gateway contract is batch-level. "
        "Input: a list of {symbol, date, days_out, direction} dicts. "
        "Output: ml_score (0-100), win_prob (0-1), pred_return %, pred_mfe %."
    )
)
@_tool_errors
async def score_opportunities(
    opportunities: Annotated[_ScoreBatch, Field(description=(
        "List of opportunity dicts, each with keys: symbol (str, ticker symbol), date "
        "(str, entry date YYYY-MM-DD), days_out (int, holding period in days), direction "
        "(str, 'long' or 'short'). Maximum 100 opportunities per request."))],
    market: Annotated[Optional[_MlMarketToken], Field(description=(
        "One ML-eligible market id for the entire batch (0,1,2,3,4,11). Defaults to '2' "
        "(S&P 500 stocks). Every opportunity in this call must belong to this market."))] = None,
    ctx: Optional[Context] = None,
) -> str:
    _bind_request_key(ctx)
    body: dict[str, Any] = {"opportunities": opportunities}
    if market is not None:
        body["market"] = market
    data = await _post("/score", body)
    if _is_upgrade_stub(data):
        return _format_upgrade(data)
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Tool: get_daily_pick
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=_READ_ONLY_TOOL,
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
    annotations=_READ_ONLY_TOOL,
    description=(
        "Low-level primitive. Prefer explain_pick (it bundles today's pick WITH this record) "
        "unless you need this exact slice: the standalone full history of past picks. "
        "Get the realized win/loss track record of recent TradeWave daily picks. "
        "Use when the user wants detailed per-pick performance, or to verify the "
        "historical accuracy before trusting the seasonal patterns. Returns recent rows with "
        "per-pick return %, result (win/loss/open), and summary stats (count, win rate, "
        "avg return). The aggregate summary covers the complete record; the per-pick list is "
        "bounded to the latest 250 rows for safe model context. This is the verifiable "
        "performance record - free-tier accessible."
    )
)
@_tool_errors
async def get_pick_track_record(ctx: Context) -> str:
    _bind_request_key(ctx)
    data = await _get("/daily-pick/track-record")
    if isinstance(data, dict) and isinstance(data.get("picks"), list):
        picks = data["picks"]
        if len(picks) > _MCP_TRACK_RECORD_MAX_PICKS:
            data = {
                **data,
                "picks": picks[-_MCP_TRACK_RECORD_MAX_PICKS:],
                "returned_count": _MCP_TRACK_RECORD_MAX_PICKS,
                "truncated": True,
                "truncation_note": (
                    "Per-pick rows are limited to the latest 250 on MCP; summary "
                    "statistics still describe the complete record."
                ),
            }
    return json.dumps(data, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run_streamable_http_app(app: Any) -> None:
    """Run the public ASGI app with explicit global admission bounds."""
    import uvicorn

    uvicorn.run(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
        limit_concurrency=_MCP_MAX_INBOUND_CONCURRENCY,
        backlog=_MCP_SOCKET_BACKLOG,
    )


class _ActiveSessionAdmissionMiddleware:
    """Atomically cap retained sessions globally and per verified principal."""

    def __init__(
        self,
        app: Any,
        *,
        manager: Any,
        max_sessions: int,
        max_sessions_per_principal: int,
        session_path: str = "/",
    ) -> None:
        self.app = app
        self.manager = manager
        self.max_sessions = max_sessions
        self.max_sessions_per_principal = max_sessions_per_principal
        self.session_path = session_path
        self._pending_initializations = 0
        self._pending_by_owner: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _sdk_owner_key(
        owner: Any,
    ) -> tuple[str, str | None, str | None] | None:
        """Canonicalize the SDK's non-secret AuthorizationContext."""
        if not isinstance(owner, dict):
            return None
        client_id = owner.get("client_id")
        issuer = owner.get("issuer")
        subject = owner.get("subject")
        if (
            not isinstance(client_id, str)
            or (issuer is not None and not isinstance(issuer, str))
            or (subject is not None and not isinstance(subject, str))
        ):
            return None
        return client_id, issuer, subject

    @classmethod
    def _admission_key_from_sdk_owner(
        cls, owner: Any
    ) -> tuple[str, str] | None:
        """Collapse SDK ownership to one quota bucket per human/account.

        SDK session isolation intentionally includes OAuth ``client_id``.  Admission
        must not: dynamic client registration would otherwise let one WorkOS subject
        obtain a fresh quota for every registered client.  BYOK SDK subjects contain
        both the gateway-issued opaque account id and the key hash: ownership uses
        the whole subject, while admission uses only the account component.
        """
        canonical = cls._sdk_owner_key(owner)
        if canonical is None:
            return None
        client_id, issuer, subject = canonical
        if not subject:
            return None
        if client_id == "byok" and issuer is None:
            match = _BYOK_SESSION_SUBJECT_RE.fullmatch(subject)
            return ("byok", match.group(1)) if match is not None else None
        return "oauth", subject

    @classmethod
    def _verified_owner(
        cls, scope: dict[str, Any]
    ) -> tuple[str, str] | None:
        """Return one server-issued, mode-aware admission identity.

        This middleware is installed inside AuthenticationMiddleware and
        AuthContextMiddleware.  Requiring their AuthenticatedUser type prevents an
        unverified Authorization header from selecting an admission bucket.  OAuth
        client_id is deliberately excluded so public dynamic registration cannot
        multiply one WorkOS user's allowance.
        """
        from mcp.server.auth.middleware.bearer_auth import (
            AuthenticatedUser,
            authorization_context,
        )

        user = scope.get("user")
        if not isinstance(user, AuthenticatedUser):
            return None
        token = user.access_token
        claims = token.claims or {}
        mode = claims.get("mode")
        subject = token.subject
        if mode == "oauth" and isinstance(subject, str) and subject:
            if claims.get("workos_sub") != subject:
                return "invalid", "verifier-contract"
            return "oauth", subject
        if mode == "byok" and isinstance(subject, str):
            admission_id = claims.get("admission_id")
            match = _BYOK_SESSION_SUBJECT_RE.fullmatch(subject)
            if (
                isinstance(admission_id, str)
                and _BYOK_ADMISSION_ID_RE.fullmatch(admission_id)
                and match is not None
                and match.group(1) == admission_id
            ):
                return "byok", admission_id
            return "invalid", "verifier-contract"
        # This should be unreachable with WorkOSTokenVerifier, but deriving via the
        # SDK context preserves a bounded bucket if a future verifier drops mode.
        fallback = cls._admission_key_from_sdk_owner(authorization_context(user))
        return fallback or ("invalid", "verifier-contract")

    def _is_session_root_request(self, scope: dict[str, Any]) -> bool:
        return scope.get("type") == "http" and scope.get("path") == self.session_path

    def _is_new_session_request(self, scope: dict[str, Any]) -> bool:
        if (
            not self._is_session_root_request(scope)
            or scope.get("method") != "POST"
        ):
            return False
        headers = scope.get("headers") or []
        return not any(name.lower() == b"mcp-session-id" for name, _ in headers)

    @staticmethod
    def _session_id(scope: dict[str, Any]) -> str | None:
        for name, value in scope.get("headers") or []:
            if name.lower() == b"mcp-session-id":
                try:
                    return value.decode("ascii")
                except UnicodeDecodeError:
                    return None
        return None

    @staticmethod
    async def _reject_capacity(receive: Any, send: Any) -> None:
        # Drain the small, edge-limited request body so a keep-alive connection can
        # safely carry a later retry without leaving unread HTTP/1.1 bytes behind.
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            more_body = bool(message.get("more_body", False))
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": "MCP session capacity temporarily reached; retry shortly",
                },
            },
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"retry-after", b"5"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _reject_sessionless_method(
        scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        """Stop SDK 1.28.1 from allocating a transport for a non-POST request.

        The pinned stateful manager creates a session before it validates the HTTP
        method whenever no Mcp-Session-Id is present.  Only POST can initialize a
        session; allowing any other authenticated method through would bypass both
        retained-session limits.
        """
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            more_body = bool(message.get("more_body", False))
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": (
                        "A new MCP session must be initialized with an HTTP POST request"
                    ),
                },
            },
            separators=(",", ":"),
        ).encode()
        response_body = b"" if scope.get("method") == "HEAD" else body
        await send(
            {
                "type": "http.response.start",
                "status": 405,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_body)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"allow", b"POST"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": response_body})

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        owner_key = self._verified_owner(scope)
        session_id = self._session_id(scope)

        # MCP 1.28.1 registers a stateful transport for every authenticated,
        # sessionless request before method validation.  Refuse all non-POST methods
        # at this authenticated boundary so they cannot create uncounted sessions.
        if (
            self._is_session_root_request(scope)
            and session_id is None
            and owner_key is not None
            and scope.get("method") != "POST"
        ):
            await self._reject_sessionless_method(scope, receive, send)
            return

        # MCP 1.28.1 terminates a transport on successful DELETE but leaves the
        # terminated object in the manager registry. Evict it after the response;
        # otherwise a clean disconnect permanently consumes admission capacity.
        if (
            self._is_session_root_request(scope)
            and scope.get("method") == "DELETE"
            and session_id is not None
        ):
            response_status = None

            async def capture_status(message: dict[str, Any]) -> None:
                nonlocal response_status
                if message.get("type") == "http.response.start":
                    response_status = message.get("status")
                await send(message)

            registered_transport = self.manager._server_instances.get(session_id)
            try:
                await self.app(scope, receive, capture_status)
            finally:
                # A client can disconnect while the successful response is being sent.
                # Cleanup must still run, but a wrong-owner 404 must never evict the
                # legitimate owner's live transport.
                current_transport = self.manager._server_instances.get(session_id)
                successful = (
                    isinstance(response_status, int)
                    and 200 <= response_status < 300
                )
                terminated = (
                    registered_transport is not None
                    and current_transport is registered_transport
                    and bool(getattr(registered_transport, "is_terminated", False))
                )
                if successful or terminated:
                    if current_transport is registered_transport:
                        self.manager._server_instances.pop(session_id, None)
                    owners = getattr(self.manager, "_session_owners", None)
                    if isinstance(owners, dict):
                        owners.pop(session_id, None)
            return

        if not self._is_new_session_request(scope):
            await self.app(scope, receive, send)
            return

        if owner_key is None:
            # Preserve the SDK's exact OAuth challenge.  An unverified request cannot
            # reach the session manager and therefore cannot retain a session slot.
            await self.app(scope, receive, send)
            return

        rejected = False
        async with self._lock:
            instances = getattr(self.manager, "_server_instances", None)
            owners = getattr(self.manager, "_session_owners", None)
            if not isinstance(instances, dict) or not isinstance(owners, dict):
                raise RuntimeError("MCP SDK session registries are unavailable")
            active_for_owner = sum(
                self._admission_key_from_sdk_owner(owner) == owner_key
                for owner in owners.values()
            )
            pending_for_owner = self._pending_by_owner.get(owner_key, 0)
            if (
                len(instances) + self._pending_initializations >= self.max_sessions
                or active_for_owner + pending_for_owner
                >= self.max_sessions_per_principal
            ):
                rejected = True
            else:
                self._pending_initializations += 1
                self._pending_by_owner[owner_key] = pending_for_owner + 1
        if rejected:
            await self._reject_capacity(receive, send)
            return

        try:
            await self.app(scope, receive, send)
        finally:
            async with self._lock:
                pending_for_owner = self._pending_by_owner.get(owner_key, 0)
                if self._pending_initializations <= 0 or pending_for_owner <= 0:
                    raise RuntimeError("MCP pending-session admission counter underflow")
                self._pending_initializations -= 1
                if pending_for_owner == 1:
                    self._pending_by_owner.pop(owner_key, None)
                else:
                    self._pending_by_owner[owner_key] = pending_for_owner - 1


def _streamable_http_app_with_idle_timeout() -> Any:
    """Create the stateful app with process-wide pools and finite session lifetime."""
    app = mcp.streamable_http_app()
    manager = mcp.session_manager
    if manager.stateless:
        raise RuntimeError("TradeWave MCP requires stateful Streamable HTTP sessions")
    manager.session_idle_timeout = _MCP_SESSION_IDLE_TIMEOUT_SECONDS
    # Install admission on the protected MCP route, not as outer Starlette
    # middleware.  The route runs after the SDK has authenticated the bearer and
    # populated scope['user'], but before RequireAuth and the session manager.
    mcp_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == mcp.settings.streamable_http_path
    ]
    if len(mcp_routes) != 1 or getattr(mcp_routes[0], "app", None) is None:
        raise RuntimeError("MCP protected Streamable HTTP route is unavailable")
    mcp_routes[0].app = _ActiveSessionAdmissionMiddleware(
        mcp_routes[0].app,
        manager=manager,
        max_sessions=_MCP_MAX_ACTIVE_SESSIONS,
        max_sessions_per_principal=_MCP_MAX_SESSIONS_PER_PRINCIPAL,
        session_path=mcp.settings.streamable_http_path,
    )
    manager_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def process_lifespan(starlette_app: Any):
        # Hold one reference for the whole ASGI process. The low-level FastMCP
        # lifespan runs per session and takes additional references, but no
        # session can multiply the connection budget or close another's pool.
        async with _shared_gateway_pool():
            async with manager_lifespan(starlette_app):
                yield

    app.router.lifespan_context = process_lifespan
    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradeWave MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for the Streamable HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="Port for the Streamable HTTP transport (default: 9090)",
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
        # Remote Streamable HTTP is always a shared, authenticated resource
        # server. Refuse partial OAuth configuration and shared customer credentials
        # before binding a socket; this prevents config drift from downgrading auth.
        try:
            _validate_remote_startup_configuration(args.host, args.port)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(2) from None

    if args.transport != "stdio":
        # Inject host/port before running non-stdio transports.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # The SDK's DNS-rebinding protection allowlists only localhost by default,
        # so a proxied public Host gets a 421. Prefer the explicit compatibility
        # override, then derive the authority from the canonical OAuth resource
        # URL, and only use the development fallback when neither is configured.
        mcp.settings.transport_security = _mcp_transport_security(args.host, args.port)

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
        _run_streamable_http_app(_McpPathAlias(_streamable_http_app_with_idle_timeout()))
    else:
        # The parser admits only stdio here. Legacy SSE transport is deliberately
        # unsupported: it lacks the Streamable HTTP runner's process-wide pool,
        # inbound/session admission, idle reaping, and socket backlog bounds.
        mcp.run(transport="stdio")
