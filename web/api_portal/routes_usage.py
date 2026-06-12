"""Usage vs quota.

Hot path: the gateway writes per-day Redis counters in db4 (see
apiserver/auth.py):
  - usage:{user_id}:{YYYY-MM-DD}   HASH  endpoint -> count   (per-endpoint calls)
  - rl:day:{user_id}:{epoch_day}   STR   total calls today   (rate-limit counter)
We read those for "today". For history we read the api_usage_daily rollup table
(populated by the gateway's cron). Redis is best-effort: a Redis outage degrades
to "today unavailable" rather than 500ing the page.
"""
import time
import logging
from datetime import date, timedelta

import redis

from flask import render_template

from apiserver import settings, db
from .blueprint import bp, require_login, get_current_user, api_entitlements_for, api_tier_name_for

log = logging.getLogger("tw2.api_portal.usage")

# Same Redis db the gateway meters into (db4 by default; read from settings).
_redis = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    socket_timeout=2,
    socket_connect_timeout=2,
)

_HISTORY_DAYS = 14


def _today_counts(user_id):
    """Return (total_today, {endpoint: count}). Best-effort; ({},0) on Redis error."""
    today = time.strftime("%Y-%m-%d")
    epoch_day = int(time.time()) // 86400
    try:
        per_endpoint_raw = _redis.hgetall("usage:%s:%s" % (user_id, today))
        day_total_raw = _redis.get("rl:day:%s:%s" % (user_id, epoch_day))
    except redis.RedisError as e:
        log.warning("usage read failed for %s: %s", user_id, e)
        return None, None

    per_endpoint = {}
    for k, v in (per_endpoint_raw or {}).items():
        endpoint = k.decode() if isinstance(k, (bytes, bytearray)) else k
        try:
            per_endpoint[endpoint] = int(v)
        except (TypeError, ValueError):
            continue

    if day_total_raw is not None:
        try:
            total = int(day_total_raw)
        except (TypeError, ValueError):
            total = sum(per_endpoint.values())
    else:
        # No rate-limit counter (e.g. only metered usage exists) - sum endpoints.
        total = sum(per_endpoint.values())
    return total, per_endpoint


def _history_rows(user_id):
    """Daily totals for the last _HISTORY_DAYS from api_usage_daily (rollup)."""
    since = date.today() - timedelta(days=_HISTORY_DAYS - 1)
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT day, sum(count) AS total
            FROM api_usage_daily
            WHERE user_id = %s AND day >= %s
            GROUP BY day
            ORDER BY day DESC
            """,
            (str(user_id), since),
        )
        return cur.fetchall()


@bp.route("/usage")
@require_login
def usage_index():
    u = get_current_user()
    ent = api_entitlements_for(u)
    rate = ent["rate"]

    total_today, per_endpoint = _today_counts(u.id)
    redis_ok = total_today is not None
    if not redis_ok:
        total_today, per_endpoint = 0, {}

    day_quota = rate["per_day"]
    pct_day = min(100, round(100 * total_today / day_quota)) if day_quota else 0

    # Sort endpoints by call count desc for the breakdown table.
    endpoint_rows = sorted(per_endpoint.items(), key=lambda kv: kv[1], reverse=True)

    history = _history_rows(u.id)

    return render_template(
        "api_usage.html",
        user=u,
        tier_name=api_tier_name_for(u),
        tier_label=ent["name"],
        per_minute_limit=rate["per_minute"],
        per_day_limit=day_quota,
        opp_limit=ent["opp_limit"],
        total_today=total_today,
        pct_day=pct_day,
        endpoint_rows=endpoint_rows,
        history=history,
        redis_ok=redis_ok,
    )
