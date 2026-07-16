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
