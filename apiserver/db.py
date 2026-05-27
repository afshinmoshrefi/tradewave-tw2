"""DB access for the gateway: the api_keys + api_usage tables and read-only user
lookups. Same Postgres as the appserver/web (POSTGRES_DSN). Tables created by schema.sql
at the integration step (additive; CREATE TABLE IF NOT EXISTS)."""
import contextlib
import psycopg2
import psycopg2.extras

from . import settings


@contextlib.contextmanager
def cursor(commit=False):
    conn = psycopg2.connect(settings.POSTGRES_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def get_user_by_key_hash(key_hash):
    """Return {user_id, email, tier, roles} for a live (non-revoked) key, else None.
    Also bumps last_used_at. NOTE: selects only columns that exist in the current
    users schema (tier, roles); api_tier inheritance is computed in tiers.py."""
    with cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, u.email, u.tier, u.roles, k.id AS key_id
            FROM api_keys k JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = %s AND k.revoked_at IS NULL
            """,
            (key_hash,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["key_id"],))
        return row
