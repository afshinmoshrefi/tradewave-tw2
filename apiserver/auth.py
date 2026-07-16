"""Request auth + entitlement resolution + rate limiting + usage. Shared by the gateway
(Flask decorator) and the MCP server (resolve_customer directly).

Fail-fast: real errors propagate; only best-effort telemetry (usage counters) is guarded,
and even then it logs rather than silently swallowing.
"""
import hashlib
import hmac
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from functools import wraps

import redis
from flask import g, jsonify, request

from . import db, settings, tiers
from .gateway_redis import create_client
import reverse_trial  # shared reverse-trial cutoff math (also imported by web/app.py)
from reverse_trial import NAV_TEASER_SECONDS  # hoisted: web + gateway share the 7-day window

# A delegated principal id (the web user_id the in-product chatbot is acting for). Kept
# strict so it can only ever be a clean redis-key segment - never an injection vector.
_ON_BEHALF_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# A WorkOS user id (the OAuth token subject), e.g. "user_01H...". Strict so it can only ever be a
# clean DB lookup value, never an injection vector.
_WORKOS_SUB_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

log = logging.getLogger("apiserver.auth")
_redis = create_client()
_key_cache = OrderedDict()
_key_cache_lock = threading.Lock()


class AuthMisconfigured(Exception):
    """The HMAC secret is unset, so we cannot hash keys. Fail CLOSED (503) rather than
    authenticate against an empty-secret hash. Mirrors appserver.py login_api (503)."""


# Startup-time loud check: a box with no HMAC secret can never authenticate anyone, so
# surface it the moment the module imports rather than only on the first request.
if not settings.API_KEY_HMAC_SECRET:
    log.error("API_KEY_HMAC_SECRET (or APPSERVER_JWT_SECRET) is unset; the gateway will "
              "refuse all authenticated requests with 503 until it is configured.")


def hash_key(raw_key):
    secret = (settings.API_KEY_HMAC_SECRET or "").encode()
    return hmac.new(secret, raw_key.encode(), hashlib.sha256).hexdigest()


def _cached_key_row(key_hash):
    """Return a cached successful key lookup. Misses are deliberately not cached."""
    if settings.API_KEY_CACHE_TTL_SECONDS <= 0:
        return None
    now = time.monotonic()
    with _key_cache_lock:
        item = _key_cache.get(key_hash)
        if item is None:
            return None
        expires_at, row = item
        if expires_at <= now:
            _key_cache.pop(key_hash, None)
            return None
        _key_cache.move_to_end(key_hash)
        return dict(row)


def _cache_key_row(key_hash, row):
    if not row or settings.API_KEY_CACHE_TTL_SECONDS <= 0:
        return
    with _key_cache_lock:
        _key_cache[key_hash] = (
            time.monotonic() + settings.API_KEY_CACHE_TTL_SECONDS,
            dict(row),
        )
        _key_cache.move_to_end(key_hash)
        while len(_key_cache) > settings.API_KEY_CACHE_MAX_ENTRIES:
            _key_cache.popitem(last=False)


def resolve_customer(raw_key):
    """raw API key -> {user_id, email, tier(api), entitlements} or None.

    Fail CLOSED: if the HMAC secret is unset we raise AuthMisconfigured (translated to a
    503 by require_api_key) instead of hashing with an empty secret, which could otherwise
    match a row stored under an empty-secret hash."""
    if not raw_key:
        return None
    if raw_key == settings.DEMO_API_KEY:
        # public demo principal: no HMAC, no DB row. Shared metering bucket ("demo").
        return {"user_id": "demo", "email": "demo@tradewave.ai",
                "tier": "demo", "entitlements": tiers.tier_for("demo")}
    if not settings.API_KEY_HMAC_SECRET:
        raise AuthMisconfigured("API_KEY_HMAC_SECRET not configured")
    key_hash = hash_key(raw_key)
    row = _cached_key_row(key_hash)
    if row is None:
        row = db.get_user_by_key_hash(key_hash)
        _cache_key_row(key_hash, row)
    if not row:
        return None
    api_tier = _key_tier(row)
    return {
        "user_id": str(row["user_id"]),
        "email": row["email"],
        "tier": api_tier,
        "entitlements": tiers.tier_for(api_tier),
    }


def _key_tier(row):
    """Resolve a DB-backed key without making internal tiers customer-settable.

    Sold/bundled tiers keep using ``api_tier_from_user`` and its MAX rule.  The
    two delegation principals (Tara and consumer MCP) are allowed to select an
    internal ``service: True`` tier only when the durable user row is explicitly
    marked ``service_account``.  A stray or forged internal label on an ordinary
    user therefore remains least-privilege and cannot unlock delegation.
    """
    explicit = str(row.get("api_tier") or "").strip().lower()
    internal = tiers.INTERNAL_TIERS.get(explicit) or {}
    roles = set(row.get("roles") or [])
    if internal.get("service"):
        if "service_account" in roles:
            return explicit
        log.error(
            "refusing internal api_tier=%r without service_account role user=%s",
            explicit,
            row.get("user_id"),
        )
    return tiers.api_tier_from_user(row)


def _extract_key():
    # HEADER ONLY: never accept the key via query string (?api_key=) - it would leak the
    # full tw_live_ key into nginx/gunicorn access logs, Referer headers, and browser history.
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    hdr = request.headers.get("X-API-Key")
    if hdr:
        return hdr
    # ONLY the public demo token may ride the query string (so the docs can use clickable
    # browser links). A real tw_live_ key here is ignored - it must stay in the header, or
    # it would leak into nginx/gunicorn access logs, Referer headers, and browser history.
    qk = request.args.get("api_key") or request.args.get("api_token")
    if qk and qk == settings.DEMO_API_KEY:
        return qk
    return None


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            cust = resolve_customer(_extract_key())
        except AuthMisconfigured:
            # Box is misconfigured (no HMAC secret). Fail closed: 503, never authenticate.
            return jsonify({"error": {"code": "service_misconfigured",
                                      "message": "service misconfigured"}}), 503
        if not cust:
            return jsonify({"error": {"code": "unauthorized",
                                      "message": "invalid or missing API key"}}), 401
        deleg_err = _apply_on_behalf(cust)
        if deleg_err is not None:
            return deleg_err
        # NOTE: record_usage runs only past this point, so 401/503/rate-limited calls are
        # not metered - only authenticated, non-rate-limited requests count.
        ok, headers = check_rate_limit(cust)
        if not ok:
            # 429 honesty: name WHICH window tripped (minute vs day) in both the headers
            # (X-RateLimit-Scope) and the error body, so an SDK auto-retry on a day-capped
            # key is never futile - Retry-After is already the real wait for that window.
            scope = headers.get("X-RateLimit-Scope", "minute")
            resp = jsonify({"error": {"code": "rate_limited",
                                      "message": "rate limit exceeded (%s window)" % scope,
                                      "scope": scope}})
            resp.headers.update(headers)
            return resp, 429
        g.customer = cust
        record_usage(cust, request.path)
        resp = fn(*args, **kwargs)
        # attach rate headers to successful responses too
        try:
            resp.headers.update(headers)
        except AttributeError:
            pass  # non-Response return (e.g. (dict, status)); blueprint normalizes it
        return resp
    return wrapper


def _apply_on_behalf(cust):
    """Privilege delegation, tightly scoped to `service: True` internal tiers. Returns None on
    success, or a Flask (json, status) response to ABORT (e.g. an MCP principal whose WorkOS user
    is unknown - we reject rather than fall back to the service tier). A normal customer key has no
    `service` flag, so both branches are a no-op for them - they can never spoof another user.

    (A) MCP OAuth (tier flag `workos_principal`): the MCP server has already validated a WorkOS JWT;
        it passes X-TW-Principal-WorkOS:<workos_sub>. We resolve that to the user's row and apply
        the MCP scope that MIRRORS their WEB subscription (see _resolve_mcp - NOT the API ladder),
        plus their real user_id (so a logged-in researcher gets exactly what they bought on the
        website, with per-user metering). Unknown sub -> 401.
    (B) Chatbot (Tara): X-TW-On-Behalf-Of:<web_user_id> swaps ONLY the metering principal to
        'cb:<id>' and KEEPS the chatbot tier (separate per-user ML bucket; never escalates scope)."""
    ent = cust.get("entitlements") or {}
    if not ent.get("service"):
        return None
    # (A) MCP OAuth principal -> the MCP scope mirroring the user's WEB sub.
    if ent.get("workos_principal"):
        sub = request.headers.get("X-TW-Principal-WorkOS", "").strip()
        # G17: FAIL CLOSED. A legitimate consumer-OAuth call ALWAYS carries the principal
        # header; without it we must NOT fall through and keep the mcp service tier's
        # ALL_MARKETS entitlement (that would expose all markets with no user identity).
        if not sub:
            return jsonify({"error": {"code": "unauthorized", "message": "missing principal"}}), 401
        if not _WORKOS_SUB_RE.match(sub):
            return jsonify({"error": {"code": "unauthorized", "message": "invalid principal"}}), 401
        row = db.get_user_by_workos_id(sub)
        if not row:
            return jsonify({"error": {"code": "unauthorized", "message": "unknown user"}}), 401
        cust["user_id"] = str(row["user_id"])
        cust["email"] = row["email"]
        cust["tier"], cust["entitlements"], cust["teaser_state"] = _resolve_mcp(row)
        return None
    # (B) Chatbot on-behalf (cb:-namespaced; keeps the chatbot tier).
    on_behalf = request.headers.get("X-TW-On-Behalf-Of", "").strip()
    if on_behalf and _ON_BEHALF_RE.match(on_behalf):
        cust["user_id"] = "cb:" + on_behalf
    return None


_NO_TEASER = {"active": False, "kind": None, "ends_at": None, "post_teaser_scope": None}


def _resolve_mcp(row):
    """Consumer MCP (TradeWave inside ChatGPT/Claude via WorkOS): the scope MIRRORS the
    user's WEB subscription (tiers.WEB_TIER_TO_MCP), NOT the API developer ladder - what
    they bought on the website is what they get in the assistant. Two teasers only ever
    WIDEN it, never narrow it:
      (1) a trialing Explorer is elevated to full Strategist scope for the rest of the SAME
          7-day reverse-trial window (reverse_trial.effective_web_tier already maps
          explorer+trial -> 'strategist', mirroring web/app.py:effective_tier). Without this
          a trial user would get LESS in chat than on the website = a bait-and-switch.
      (2) a Navigator gets a one-time 7-day, first-MCP-connect taste of ANALYST scope (the
          AI layer Navigator lacks under Ladder A) - the in-chat pull from Navigator->Analyst.
    A user who ALSO holds an explicit standalone API subscription keeps the BETTER of
    (web-mirror, api) field-by-field, so a paying developer is never downgraded in chat.
    Also builds the STRUCTURAL teaser_state (the in-chat disclosure contract) so callers
    (whoami via /me) never have to re-derive it.
    Returns (tier_label, entitlements, teaser_state)."""
    raw_tier = row.get("tier")
    eff_web = reverse_trial.effective_web_tier(
        raw_tier, row.get("roles"), row.get("reverse_trial_ends_at"))
    # Build teaser_state alongside the scope, NEVER double-arming the navigator column:
    # _navigator_teaser_active arms + reads the stamped timestamp exactly once and returns
    # both the active flag and the stamp, so the ends_at below reuses that one read.
    teaser_state = dict(_NO_TEASER)
    # (1) Explorer reverse-trial -> strategist scope; surface as the explorer_trial teaser.
    if raw_tier == "explorer" and reverse_trial.in_reverse_trial(row.get("reverse_trial_ends_at")):
        rt = row.get("reverse_trial_ends_at")
        teaser_state = {"active": True, "kind": "explorer_trial",
                        "ends_at": rt.isoformat() if rt is not None else None,
                        "post_teaser_scope": "explorer"}
    # (2) Navigator one-time 7-day first-connect teaser -> Analyst scope (the AI taste).
    elif eff_web == "navigator":
        nav_active, nav_start = _navigator_teaser_active(row)
        if nav_active:
            eff_web = "analyst"
            _, nav_ends = reverse_trial.navigator_teaser_window(nav_start)
            teaser_state = {"active": True, "kind": "navigator_firstconnect",
                            "ends_at": nav_ends, "post_teaser_scope": "navigator"}
    ent = dict(tiers.mcp_tier_for(eff_web))
    # MAX(web-mirror, explicit standalone API sub) so a paying developer isn't downgraded.
    explicit = row.get("api_tier")
    if explicit:
        ent = tiers.merge_entitlements(ent, tiers.tier_for(explicit))
        # G12: markets/rate may widen from a standalone API key, but a separately-held key
        # must NOT raise in-chat AI for a tier where web AI is gated off (steady Explorer/
        # Navigator under Ladder A). Re-floor ml_daily_limit to the mirror after the merge.
        # eff_web here is post-teaser, so a trial Explorer (->strategist) / Navigator teaser
        # (->analyst) keep their intended AI; only the steady sub-Analyst tiers are floored.
        if eff_web in ("explorer", "navigator"):
            ent["ml_daily_limit"] = tiers.mcp_tier_for(eff_web)["ml_daily_limit"]
    return eff_web, ent, teaser_state


def _navigator_teaser_active(row):
    """Navigator's one-time 7-day first-MCP-connect teaser. Anchored in Postgres
    (users.navigator_mcp_first_connect_at via db.arm_navigator_teaser_if_null) so the window
    NEVER re-arms - it survives a Redis flush/eviction/policy change, and reconnecting after
    the 7 days lapse cannot restart it. Stamps the column on the first connect (idempotent),
    then the window is (now - first_connect) < 7d. Fails CLOSED (no teaser) on a DB error:
    the user keeps their full paid Navigator scope, just without the bonus.

    Returns (active: bool, first_connect_at: datetime|None) - the stamped timestamp is
    returned so the caller can build teaser_state.ends_at from the SAME read (the column is
    armed/read here exactly once; never call this twice for one request)."""
    try:
        start = row.get("navigator_mcp_first_connect_at")
        if start is None:
            start = db.arm_navigator_teaser_if_null(row["user_id"])   # first connect: arm + persist
        if start is None:
            return False, None
        active = (datetime.now(timezone.utc) - start).total_seconds() < NAV_TEASER_SECONDS
        return active, start
    except Exception as e:   # fail closed - never block paid scope on a teaser-state error
        log.warning("navigator MCP teaser check failed for %s: %s", row.get("user_id"), e)
        return False, None


def check_rate_limit(cust):
    """(allowed, headers). On a block the headers are scoped to the window that actually
    tripped: the DAY cap gets day-window Limit/Remaining/Reset + a Retry-After to the next
    UTC midnight (the day buckets are keyed on epoch days, i.e. UTC), the minute cap gets
    a Retry-After to the next minute boundary - plus X-RateLimit-Scope: minute|day so an
    SDK can tell a short wait from 'come back tomorrow'."""
    rate = cust["entitlements"]["rate"]
    now = int(time.time())
    min_key = f"rl:min:{cust['user_id']}:{now // 60}"
    day_key = f"rl:day:{cust['user_id']}:{now // 86400}"
    pipe = _redis.pipeline()
    pipe.incr(min_key); pipe.expire(min_key, 60)
    pipe.incr(day_key); pipe.expire(day_key, 86400)
    minute_count, _, day_count, _ = pipe.execute()
    minute_reset = (now // 60 + 1) * 60
    day_reset = (now // 86400 + 1) * 86400          # next UTC midnight
    headers = {
        "X-RateLimit-Limit": str(rate["per_minute"]),
        "X-RateLimit-Remaining": str(max(0, rate["per_minute"] - int(minute_count))),
        "X-RateLimit-Reset": str(minute_reset),
    }
    day_capped = int(day_count) > rate["per_day"]
    minute_capped = int(minute_count) > rate["per_minute"]
    if day_capped:
        # The DAY cap is the binding one (whether or not the minute also tripped): a
        # minute-window reset would invite a futile auto-retry, so the headers tell the
        # honest story - blocked until the day bucket rolls over at UTC midnight.
        headers.update({
            "X-RateLimit-Scope": "day",
            "X-RateLimit-Limit": str(rate["per_day"]),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(day_reset),
            "Retry-After": str(max(1, day_reset - now)),
        })
    elif minute_capped:
        headers.update({
            "X-RateLimit-Scope": "minute",
            "Retry-After": str(max(1, minute_reset - now)),
        })
    return not (minute_capped or day_capped), headers


def record_usage(cust, endpoint):
    """Best-effort daily usage counter in Redis; rolled up to api_usage_daily by a cron.
    Never blocks the request, but logs failures (no silent swallow)."""
    try:
        day = time.strftime("%Y-%m-%d")
        key = f"usage:{cust['user_id']}:{day}"
        _redis.hincrby(key, endpoint, 1)
        _redis.expire(key, 60 * 60 * 24 * 40)
    except redis.RedisError as e:
        log.warning("usage metering failed for %s: %s", cust["user_id"], e)
