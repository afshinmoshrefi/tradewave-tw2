"""drop users.api_key plaintext column

Closes the half-finished hash migration started in 4c2f28489e2b. The
appserver login_api route now exclusively reads api_key_hash, so the
plaintext column has no readers and must go.

Drops, in order:
  - the unique constraint users_api_key_key (auto-created by the
    column's UNIQUE attribute at baseline)
  - the explicit btree index idx_users_api_key (also baseline)
  - the column itself

The downgrade re-adds api_key as a nullable Text column WITHOUT the
UNIQUE constraint or btree index. Any data that was in the column at
upgrade time is gone (HMAC is one-way), and recreating UNIQUE on a
column we cannot repopulate would break legitimate inserts.

Revision ID: 5a3c1e2f4d6b
Revises: 4c2f28489e2b
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a3c1e2f4d6b'
down_revision = '4c2f28489e2b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the unique constraint first; on Postgres dropping the column
    # does this implicitly via CASCADE-style behaviour, but being
    # explicit makes the migration replay-safe on any backend.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_api_key_key")
    op.execute("DROP INDEX IF EXISTS idx_users_api_key")
    op.drop_column('users', 'api_key')


def downgrade() -> None:
    # Re-add the column nullable; data is NOT recoverable (HMAC is one-way).
    # We deliberately do NOT re-add the unique constraint or the index:
    # both would block re-deploy of the new code that no longer writes
    # this column.
    op.add_column(
        'users',
        sa.Column('api_key', sa.Text(), nullable=True),
    )
