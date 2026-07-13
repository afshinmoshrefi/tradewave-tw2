"""Track developer-API Stripe subscription identity separately.

The web/EOD and developer-API products share a Stripe customer. Separate
subscription IDs let the webhook reject stale API cancellation events without
ever touching the web subscription fields.

Revision ID: d8c4e6a2f9b1
Revises: c7a9e2f4d6b8
Create Date: 2026-07-13
"""
from alembic import op


revision = 'd8c4e6a2f9b1'
down_revision = 'c7a9e2f4d6b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # apiserver/schema.sql is intentionally idempotent and may have run first
    # on an API box, so the Alembic side must be idempotent as well.
    op.execute(
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS '
        'api_stripe_subscription_id text'
    )
    op.execute(
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS '
        'api_stripe_subscription_status text'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS '
        'users_api_stripe_subscription_id_key '
        'ON users (api_stripe_subscription_id) '
        'WHERE api_stripe_subscription_id IS NOT NULL'
    )


def downgrade() -> None:
    op.drop_index(
        'users_api_stripe_subscription_id_key', table_name='users',
    )
    op.drop_column('users', 'api_stripe_subscription_status')
    op.drop_column('users', 'api_stripe_subscription_id')
