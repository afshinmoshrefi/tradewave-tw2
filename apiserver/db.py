"""DB access for the gateway: the api_keys + api_usage tables and read-only user
lookups. Same Postgres as the appserver/web (POSTGRES_DSN). Tables created by schema.sql
at the integration step (additive; CREATE TABLE IF NOT EXISTS)."""
import contextlib
import threading
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from . import settings


_pool = None
_pool_lock = threading.Lock()


def _connection_pool():
    """Lazily create one thread-safe pool per gunicorn worker process."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    settings.DB_POOL_MIN,
                    settings.DB_POOL_MAX,
                    dsn=settings.POSTGRES_DSN,
                )
    return _pool


@contextlib.contextmanager
def cursor(commit=False):
    pool = _connection_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn, close=bool(conn.closed))


def get_user_by_workos_id(workos_user_id):
    """Return {user_id, email, tier, api_tier, roles, reverse_trial_ends_at,
    navigator_mcp_first_connect_at} for a user by their WorkOS id, else None. Used by the MCP OAuth
    flow: a WorkOS-authenticated researcher maps to their existing TradeWave user via
    users.workos_user_id; the gateway then MIRRORS their WEB sub into the MCP scope
    (auth._resolve_mcp). reverse_trial_ends_at drives the Explorer in-chat teaser (a trialing
    Explorer gets full Strategist scope for the rest of the same window);
    navigator_mcp_first_connect_at anchors the one-time 7-day Navigator first-connect teaser."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT id AS user_id, email, tier, api_tier, roles, reverse_trial_ends_at,
                   navigator_mcp_first_connect_at
            FROM users WHERE workos_user_id = %s
            """,
            (workos_user_id,),
        )
        return cur.fetchone()


def arm_navigator_teaser_if_null(user_id):
    """Idempotently stamp users.navigator_mcp_first_connect_at on a Navigator's FIRST
    consumer-MCP connect, and return the canonical timestamp (the one we just set if we won
    the race, else the pre-existing one). Anchors the one-time 7-day Navigator teaser in
    Postgres - NOT Redis - so it NEVER re-arms (survives a Redis flush/eviction/policy change).
    Race-safe via the WHERE ... IS NULL guard; the loser of a concurrent first-connect reads
    back the winner's timestamp."""
    with cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE users SET navigator_mcp_first_connect_at = now()
            WHERE id = %s AND navigator_mcp_first_connect_at IS NULL
            RETURNING navigator_mcp_first_connect_at
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return row["navigator_mcp_first_connect_at"]   # we just armed it (first connect)
        cur.execute("SELECT navigator_mcp_first_connect_at FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row["navigator_mcp_first_connect_at"] if row else None


def get_user_by_key_hash(key_hash):
    """Return {user_id, email, tier, api_tier, roles, reverse_trial_ends_at} for a live (non-revoked)
    key, else None. Also bumps last_used_at. api_tier is the explicit API subscription (null when the
    user inherits from the web tier); tiers.api_tier_from_user() prefers it over the web tier.
    reverse_trial_ends_at is selected for parity with the WorkOS lookup (so any future API-key path
    can honor the trial too); requires the users.api_tier column (schema.sql ADD COLUMN IF NOT EXISTS)."""
    with cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, u.email, u.tier, u.api_tier, u.roles,
                   u.reverse_trial_ends_at, k.id AS key_id
            FROM api_keys k JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = %s AND k.revoked_at IS NULL
            """,
            (key_hash,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE api_keys SET last_used_at = now()
                WHERE id = %s
                  AND (last_used_at IS NULL OR last_used_at < now() - interval '60 seconds')
                """,
                (row["key_id"],),
            )
        return row


# --- affiliate self-service (read-only; GET /v1/affiliate/me, see affiliate_view.py) --------

_AFFILIATE_COLS = """a.id, a.code, a.name, a.status, a.commission_model, a.discount_pct,
       a.commission_pct, a.discount_pct_monthly, a.commission_pct_monthly, a.payout_method,
       a.payout_email, a.tax_form_type, a.tax_form_received_at"""


def get_affiliate_for_user(user_id, email=None):
    """The caller's non-terminated affiliate row: linked by affiliates.user_id, else (not yet
    linked) the same exact case-insensitive email match the web portal auto-links on. The
    email fallback never matches a row already linked to a different user."""
    with cursor() as cur:
        cur.execute("SELECT " + _AFFILIATE_COLS + " FROM affiliates a "
                    "WHERE a.user_id = %s AND a.status <> 'terminated'", (user_id,))
        row = cur.fetchone()
        if row or not email:
            return row
        cur.execute("SELECT " + _AFFILIATE_COLS + " FROM affiliates a "
                    "WHERE a.user_id IS NULL AND a.status <> 'terminated' "
                    "AND lower(a.email) = lower(%s)", (email,))
        rows = cur.fetchall()
        return rows[0] if len(rows) == 1 else None


def affiliate_funnel(affiliate_id, days=30):
    """Anonymized counts only (mirrors web affiliate_service.funnel_for_affiliate)."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT coalesce(sum(clicks), 0) FROM affiliate_clicks
                 WHERE affiliate_id = %(a)s AND day >= (now() at time zone 'utc')::date - %(d)s) AS clicks_recent,
              (SELECT coalesce(sum(clicks), 0) FROM affiliate_clicks WHERE affiliate_id = %(a)s) AS clicks_total,
              (SELECT count(*) FROM users WHERE referred_by_affiliate_id = %(a)s
                 AND referred_at >= now() - make_interval(days => %(d)s)) AS signups_recent,
              (SELECT count(*) FROM users WHERE referred_by_affiliate_id = %(a)s) AS signups_total,
              (SELECT count(*) FROM users WHERE referred_by_affiliate_id = %(a)s
                 AND reverse_trial_ends_at > now()) AS in_trial,
              (SELECT count(*) FROM affiliate_referrals WHERE affiliate_id = %(a)s) AS paying_total
            """,
            {"a": affiliate_id, "d": int(days)},
        )
        r = cur.fetchone() or {}
        out = {"days": int(days)}
        for k in ("clicks_recent", "clicks_total", "signups_recent", "signups_total",
                  "in_trial", "paying_total"):
            out[k] = int(r.get(k) or 0)
        return out


def affiliate_program_v2(affiliate_id):
    """Program v2 facts for ONE affiliate: the terms version that applies to their next
    referral (their assigned row, else the seeded default v2-5y), the last self-serve
    discount change, and the first-payment date of their most recent NEW paying customer
    (the activity rule's input; returning customers do not count). None if unknown."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT t.version AS terms_version, t.pool_pct, t.max_discount_pct,
                   t.promo_commission_pct, t.renewal_pct, t.renewal_years,
                   t.activity_rule_months, a.discount_changed_at,
                   (SELECT max(r.first_paid_at) FROM affiliate_referrals r
                     WHERE r.affiliate_id = a.id AND r.first_paid_at IS NOT NULL
                       AND r.source <> 'return') AS last_new_customer_at
            FROM affiliates a
            LEFT JOIN affiliate_terms t ON t.id = coalesce(
                a.terms_id, (SELECT id FROM affiliate_terms WHERE version = 'v2-5y'))
            WHERE a.id = %s
            """,
            (affiliate_id,),
        )
        return cur.fetchone()


def active_promotions():
    """Company-wide campaigns that are live right now (not partner-specific)."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT code, name, tiers, billing_intervals, offer_type, intro_prices, percent_off,
                   intro_months, stripe_coupon_ids, starts_at, ends_at
            FROM promo_campaigns
            WHERE status = 'active' AND starts_at <= now() AND ends_at > now()
            ORDER BY ends_at
            """
        )
        return cur.fetchall()


def affiliate_payout_rows(affiliate_id, limit=36):
    """Statement rows, newest first (totals only - the per-invoice detail is not selected)."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT period_start, currency, commission_amount, status, external_ref, paid_at
            FROM affiliate_payouts WHERE affiliate_id = %s
            ORDER BY period_start DESC, currency LIMIT %s
            """,
            (affiliate_id, int(limit)),
        )
        return cur.fetchall()
