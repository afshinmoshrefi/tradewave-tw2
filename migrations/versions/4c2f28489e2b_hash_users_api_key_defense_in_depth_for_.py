"""hash users.api_key (defense-in-depth for service account)

Adds users.api_key_hash (Text) and an index on it.

Strategy:
  - Add api_key_hash as a nullable Text column.
  - Backfill done by /home/flask/web/db_admin.py hash-api-keys (NOT in
    this migration — backfill is a Python step that needs the HMAC
    secret + bytes-equality care, which alembic SQL is awkward for).
  - The original api_key column is left intact so that the appserver
    continues to work during the transition. A follow-up migration
    will null out api_key once the appserver is fully on api_key_hash
    end-to-end and a soak period has confirmed no regressions.

Hashing:
  HMAC-SHA256(api_key, secret) where secret is API_KEY_HMAC_SECRET in
  the env (falls back to APPSERVER_JWT_SECRET as a transition default
  per F4 spec). See db_admin.py for the canonical implementation.

Revision ID: 4c2f28489e2b
Revises: 1940d1f63473
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c2f28489e2b'
down_revision = '1940d1f63473'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('api_key_hash', sa.Text(), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS users_api_key_hash_idx "
        "ON users (api_key_hash)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS users_api_key_hash_idx")
    op.drop_column('users', 'api_key_hash')
