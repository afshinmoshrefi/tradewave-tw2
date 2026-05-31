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
    """Return {user_id, email, tier, api_tier, roles} for a live (non-revoked) key, else None.
    Also bumps last_used_at. api_tier is the explicit API subscription (null when the user
    inherits from the web tier); tiers.api_tier_from_user() prefers it over the web tier.
    Requires the users.api_tier column (schema.sql ADD COLUMN IF NOT EXISTS)."""
    with cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, u.email, u.tier, u.api_tier, u.roles, k.id AS key_id
            FROM api_keys k JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = %s AND k.revoked_at IS NULL
            """,
            (key_hash,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["key_id"],))
        return row
