"""Request auth + entitlement resolution + rate limiting + usage. Shared by the gateway
(Flask decorator) and the MCP server (resolve_customer directly).

Fail-fast: real errors propagate; only best-effort telemetry (usage counters) is guarded,
and even then it logs rather than silently swallowing.
"""
import hashlib
import hmac
import logging
import re
import time
from functools import wraps

import redis
from flask import g, jsonify, request

from . import db, settings, tiers

# A delegated principal id (the web user_id the in-product chatbot is acting for). Kept
# strict so it can only ever be a clean redis-key segment - never an injection vector.
_ON_BEHALF_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# A WorkOS user id (the OAuth token subject), e.g. "user_01H...". Strict so it can only ever be a
# clean DB lookup value, never an injection vector.
_WORKOS_SUB_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

log = logging.getLogger("apiserver.auth")
_redis = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)


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
    row = db.get_user_by_key_hash(hash_key(raw_key))
    if not row:
        return None
    api_tier = tiers.api_tier_from_user(row)
    return {
        "user_id": str(row["user_id"]),
        "email": row["email"],
        "tier": api_tier,
        "entitlements": tiers.tier_for(api_tier),
    }


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
        their REAL api tier + real user_id (so a logged-in researcher gets exactly their own
        free/dev/pro entitlements + per-user metering). Unknown sub -> 401.
    (B) Chatbot (Tara): X-TW-On-Behalf-Of:<web_user_id> swaps ONLY the metering principal to
        'cb:<id>' and KEEPS the chatbot tier (separate per-user ML bucket; never escalates scope)."""
    ent = cust.get("entitlements") or {}
    if not ent.get("service"):
        return None
    # (A) MCP OAuth principal -> the user's REAL tier.
    if ent.get("workos_principal"):
        sub = request.headers.get("X-TW-Principal-WorkOS", "").strip()
        if sub:
            if not _WORKOS_SUB_RE.match(sub):
                return jsonify({"error": {"code": "unauthorized", "message": "invalid principal"}}), 401
            row = db.get_user_by_workos_id(sub)
            if not row:
                return jsonify({"error": {"code": "unauthorized", "message": "unknown user"}}), 401
            api_tier = tiers.api_tier_from_user(row)
            cust["user_id"] = str(row["user_id"])
            cust["email"] = row["email"]
            cust["tier"] = api_tier
            cust["entitlements"] = tiers.tier_for(api_tier)   # the researcher's REAL tier
            return None
    # (B) Chatbot on-behalf (cb:-namespaced; keeps the chatbot tier).
    on_behalf = request.headers.get("X-TW-On-Behalf-Of", "").strip()
    if on_behalf and _ON_BEHALF_RE.match(on_behalf):
        cust["user_id"] = "cb:" + on_behalf
    return None


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
