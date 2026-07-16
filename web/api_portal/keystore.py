"""API-key data access for the console.

Reuses apiserver.db.cursor (same POSTGRES_DSN connection helper the gateway
uses) and apiserver.auth.hash_key (HMAC-SHA256) so keys hash + verify
identically to the gateway. The api_keys table is defined in
apiserver/schema.sql; this module only reads/writes it (additive).

Key format: tw_live_<32 hex chars>. We store ONLY the HMAC hash + a short
non-secret display prefix (e.g. 'tw_live_9f3a2b71'); the raw key is shown to
the user exactly once at creation and is never recoverable afterwards.
"""
import secrets

from apiserver import db
from apiserver.auth import hash_key

KEY_PREFIX = "tw_live_"
# Length (chars) of the random hex body. 16 bytes -> 32 hex chars -> 128 bits.
_RANDOM_BYTES = 16
# How many chars of the random body to keep as the human-visible prefix label.
_PREFIX_DISPLAY_CHARS = 8


class KeyStoreError(RuntimeError):
    pass


class KeyLimitReached(KeyStoreError):
    pass


class KeyNotFound(KeyStoreError):
    pass


class KeyAlreadyRevoked(KeyStoreError):
    pass


def _lock_owner(cur, user_id):
    """Serialize all key-count mutations for one account."""
    cur.execute(
        "SELECT id FROM users WHERE id = %s FOR UPDATE",
        (str(user_id),),
    )
    if cur.fetchone() is None:
        raise KeyNotFound("API-key owner no longer exists")


def _insert_key(cur, user_id, name, raw, display_prefix):
    cur.execute(
        """
        INSERT INTO api_keys (user_id, name, key_hash, prefix)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, prefix, created_at, last_used_at, revoked_at
        """,
        (str(user_id), name, hash_key(raw), display_prefix),
    )
    return cur.fetchone()


def generate_raw_key():
    """Return (raw_key, display_prefix).

    raw_key:        tw_live_<32 hex>           - shown to the user ONCE.
    display_prefix: tw_live_<first 8 hex>      - safe to store + display.
    """
    body = secrets.token_hex(_RANDOM_BYTES)
    raw = KEY_PREFIX + body
    display_prefix = KEY_PREFIX + body[:_PREFIX_DISPLAY_CHARS]
    return raw, display_prefix


def list_keys(user_id):
    """All keys for a user, newest first (includes revoked ones, marked)."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, prefix, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (str(user_id),),
        )
        return cur.fetchall()


def count_active_keys(user_id):
    """Number of live (non-revoked) keys - used to enforce tier max_keys."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM api_keys WHERE user_id = %s AND revoked_at IS NULL",
            (str(user_id),),
        )
        return int(cur.fetchone()["n"])


def create_key(user_id, name, *, max_keys=None):
    """Insert a new key for the user. Returns (raw_key, row_dict).

    The HMAC of the raw key is stored; the raw key is returned to the caller to
    show once and then forget. The UNIQUE constraint on key_hash makes a hash
    collision (astronomically unlikely) fail loudly rather than silently alias.
    """
    raw, display_prefix = generate_raw_key()
    with db.cursor(commit=True) as cur:
        _lock_owner(cur, user_id)
        if max_keys is not None:
            max_keys = int(max_keys)
            cur.execute(
                "SELECT count(*) AS n FROM api_keys "
                "WHERE user_id = %s AND revoked_at IS NULL",
                (str(user_id),),
            )
            if int(cur.fetchone()["n"]) >= max_keys:
                raise KeyLimitReached("active API-key limit reached")
        row = _insert_key(cur, user_id, name, raw, display_prefix)
    return raw, row


def rotate_key(user_id, key_id):
    """Create the replacement and revoke the old key in one transaction."""
    raw, display_prefix = generate_raw_key()
    with db.cursor(commit=True) as cur:
        _lock_owner(cur, user_id)
        cur.execute(
            """
            SELECT id, name, prefix, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE id = %s AND user_id = %s
            FOR UPDATE
            """,
            (str(key_id), str(user_id)),
        )
        old = cur.fetchone()
        if old is None:
            raise KeyNotFound("API key not found")
        if old["revoked_at"] is not None:
            raise KeyAlreadyRevoked("API key is already revoked")
        row = _insert_key(cur, user_id, old["name"], raw, display_prefix)
        cur.execute(
            """
            UPDATE api_keys
            SET revoked_at = now()
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            """,
            (str(key_id), str(user_id)),
        )
        if cur.rowcount != 1:
            raise KeyStoreError("API key changed during rotation")
    return raw, row


def revoke_key(user_id, key_id):
    """Revoke one key the user owns. Returns True if a live key was revoked.

    Scoped by user_id so a customer can never revoke another account's key.
    No-ops (returns False) if the key is missing, not theirs, or already
    revoked.
    """
    with db.cursor(commit=True) as cur:
        _lock_owner(cur, user_id)
        cur.execute(
            """
            UPDATE api_keys
            SET revoked_at = now()
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            """,
            (str(key_id), str(user_id)),
        )
        return cur.rowcount > 0


def get_key(user_id, key_id):
    """Fetch one key row the user owns, or None."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, prefix, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE id = %s AND user_id = %s
            """,
            (str(key_id), str(user_id)),
        )
        return cur.fetchone()
