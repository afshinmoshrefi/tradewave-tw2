"""Per-customer DAILY ML-scoring allowance.

TradeWave gives ML scores to EVERY tier, but metered per day: free Explorer gets a
small taste (5/day), Dev more, Pro/Business unlimited. The limit lives in
tiers.API_TIERS[tier]['ml_daily_limit'] (None = unlimited). This module is the one place
that counts + consumes the daily allowance, in Redis db4 (the gateway's own db, same as
the win_rate cache / usage counters - never the appserver's db0/2/3).

A "use" = one opportunity scored by the ML model. consume(cust, n) atomically grants up
to the remaining allowance and returns how many were granted (so a request scores only
what it is allowed and the rest degrade to a graceful upgrade nudge, never an error).

Best-effort: a Redis outage FAILS OPEN (grants the request) and logs - ML metering is a
product lever, not a security control, so a counter outage must not block paying behavior.
"""
import logging
import time

import redis

from . import settings
from .gateway_redis import create_client

log = logging.getLogger("apiserver.ml_quota")
_redis = create_client()
_TTL = 60 * 60 * 40  # ~40h, comfortably past a calendar day

# Redis executes each script atomically. Client-side GET + INCRBY/SET would allow
# concurrent API/MCP requests to overspend or erase one another's reservations.
_CONSUME_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
local requested = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if used == nil or limit == nil or requested == nil or ttl == nil or requested <= 0 then
  return redis.error_reply('invalid ML quota state')
end
local remaining = limit - used
if remaining <= 0 then return 0 end
local granted = math.min(requested, remaining)
redis.call('SET', KEYS[1], used + granted, 'EX', ttl)
return granted
"""

_REFUND_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if used == nil or amount == nil or ttl == nil or amount <= 0 then
  return redis.error_reply('invalid ML quota state')
end
local revised = math.max(0, used - amount)
if revised == 0 then
  redis.call('DEL', KEYS[1])
else
  redis.call('SET', KEYS[1], revised, 'EX', ttl)
end
return revised
"""


def _key(user_id):
    return "mlq:%s:%s" % (user_id, time.strftime("%Y-%m-%d"))


def _limit(cust):
    """The tier's daily ML limit; None = unlimited."""
    return (cust.get("entitlements") or {}).get("ml_daily_limit")


def remaining(cust):
    """ML scorings still allowed today; None = unlimited."""
    lim = _limit(cust)
    if lim is None:
        return None
    if lim == 0:
        return 0  # G11: a 0-limit tier (e.g. MCP explorer/navigator) has NO AI - decide it
                  # BEFORE the fail-open path so a Redis outage can never grant it scores.
    try:
        used = int(_redis.get(_key(cust["user_id"])) or 0)
    except redis.RedisError as e:
        log.warning("ml_quota remaining read failed for %s: %s", cust.get("user_id"), e)
        return lim  # fail open
    return max(0, lim - used)


def consume(cust, n):
    """Grant up to `n` ML scorings against today's allowance; returns the number granted.
    Unlimited tiers grant all n. Increments the daily counter by the granted amount."""
    if n <= 0:
        return 0
    lim = _limit(cust)
    if lim is None:
        return n  # unlimited
    if lim == 0:
        return 0  # G11: a 0-limit tier gets NO AI - decide BEFORE the fail-open path below,
                  # so a Redis outage can never flip no-AI (explorer/navigator) into granted.
    k = _key(cust["user_id"])
    try:
        return int(_redis.eval(_CONSUME_LUA, 1, k, lim, n, _TTL))
    except redis.RedisError as e:
        log.warning("ml_quota consume failed for %s: %s", cust.get("user_id"), e)
        return n  # fail open - never block on a counter outage


def refund(cust, n):
    """Give back `n` previously-consumed ML scorings (floor 0). Used when allowance was
    RESERVED for a row up front but the model returned no score for it (e.g. a hold longer
    than the model covers), so a metered customer is only ever charged for ML scores
    actually delivered. No-op for unlimited tiers or n <= 0; fails open on a Redis outage."""
    if n <= 0 or _limit(cust) is None:
        return
    k = _key(cust["user_id"])
    try:
        _redis.eval(_REFUND_LUA, 1, k, n, _TTL)
    except redis.RedisError as e:
        log.warning("ml_quota refund failed for %s: %s", cust.get("user_id"), e)
