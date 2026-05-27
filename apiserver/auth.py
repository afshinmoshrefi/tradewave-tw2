"""Request auth + entitlement resolution + rate limiting + usage. Shared by the gateway
(Flask decorator) and the MCP server (resolve_customer directly).

Fail-fast: real errors propagate; only best-effort telemetry (usage counters) is guarded,
and even then it logs rather than silently swallowing.
"""
import hashlib
import hmac
import logging
import time
from functools import wraps

import redis
from flask import g, jsonify, request

from . import db, settings, tiers

log = logging.getLogger("apiserver.auth")
_redis = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)


def hash_key(raw_key):
    secret = (settings.API_KEY_HMAC_SECRET or "").encode()
    return hmac.new(secret, raw_key.encode(), hashlib.sha256).hexdigest()


def resolve_customer(raw_key):
    """raw API key -> {user_id, email, tier(api), entitlements} or None."""
    if not raw_key:
        return None
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
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-API-Key") or request.args.get("api_key")


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cust = resolve_customer(_extract_key())
        if not cust:
            return jsonify({"error": {"code": "unauthorized",
                                      "message": "invalid or missing API key"}}), 401
        ok, headers = check_rate_limit(cust)
        if not ok:
            resp = jsonify({"error": {"code": "rate_limited", "message": "rate limit exceeded"}})
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


def check_rate_limit(cust):
    rate = cust["entitlements"]["rate"]
    now = int(time.time())
    min_key = f"rl:min:{cust['user_id']}:{now // 60}"
    day_key = f"rl:day:{cust['user_id']}:{now // 86400}"
    pipe = _redis.pipeline()
    pipe.incr(min_key); pipe.expire(min_key, 60)
    pipe.incr(day_key); pipe.expire(day_key, 86400)
    minute_count, _, day_count, _ = pipe.execute()
    headers = {
        "X-RateLimit-Limit": str(rate["per_minute"]),
        "X-RateLimit-Remaining": str(max(0, rate["per_minute"] - int(minute_count))),
        "X-RateLimit-Reset": str((now // 60 + 1) * 60),
    }
    allowed = int(minute_count) <= rate["per_minute"] and int(day_count) <= rate["per_day"]
    return allowed, headers


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
