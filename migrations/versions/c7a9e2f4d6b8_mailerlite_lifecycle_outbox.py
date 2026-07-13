"""Add the durable MailerLite lifecycle outbox.

Lifecycle group writes used to happen after the user/Stripe transaction and
could be lost forever on a transient API failure. This additive table records
the intent in the same transaction, supports retries, and lets the worker
reconcile from current user state.

Revision ID: c7a9e2f4d6b8
Revises: b3f6a8c1d9e2
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c7a9e2f4d6b8'
down_revision = 'b3f6a8c1d9e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mailerlite_lifecycle_events',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column(
            'user_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('dedupe_key', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('attempts', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('available_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('claimed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('processed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.CheckConstraint(
            "event_type IN ('reconcile','clear_paid')",
            name='mailerlite_lifecycle_events_type_check',
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','suppressed','failed')",
            name='mailerlite_lifecycle_events_status_check',
        ),
        sa.UniqueConstraint('dedupe_key', name='uq_mailerlite_lifecycle_dedupe_key'),
    )
    op.create_index(
        'ix_mailerlite_lifecycle_user_status',
        'mailerlite_lifecycle_events', ['user_id', 'status'], unique=False,
    )
    op.create_index(
        'ix_mailerlite_lifecycle_due',
        'mailerlite_lifecycle_events', ['available_at', 'id'], unique=False,
        postgresql_where=sa.text("status IN ('pending','failed')"),
    )


def downgrade() -> None:
    op.drop_index('ix_mailerlite_lifecycle_due',
                  table_name='mailerlite_lifecycle_events')
    op.drop_index('ix_mailerlite_lifecycle_user_status',
                  table_name='mailerlite_lifecycle_events')
    op.drop_table('mailerlite_lifecycle_events')
