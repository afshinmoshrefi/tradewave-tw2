"""onboarding_events: trial-usage telemetry for the end-of-trial trust-signal

Append-only table logging which markets / symbols / horizons a trial user touched,
so the end-of-trial conversion can recommend the MINIMUM tier that covers their
actual usage (POST /api/onboarding/event -> GET /api/onboarding/usage-summary).
Low-sensitivity (no orders, no PII). FK to users with ON DELETE CASCADE.

Revision ID: c2e5f8a1b3d4
Revises: a1f4d2c9e7b3
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'c2e5f8a1b3d4'
down_revision = 'a1f4d2c9e7b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'onboarding_events',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_onboarding_events_user_id', 'onboarding_events', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_onboarding_events_user_id', table_name='onboarding_events')
    op.drop_table('onboarding_events')
