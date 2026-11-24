"""affiliate_help_assistant: partner help chat, escalations, knowledge base

TW-TASK-0039 package A. Three new tables, nothing existing is touched.

Revision ID: a9c1e5f7b3d2
Revises: b4d7e1f2a3c5
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a9c1e5f7b3d2'
down_revision = 'b4d7e1f2a3c5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'affiliate_help_escalations',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('affiliate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('affiliates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('context', postgresql.JSONB()),
        sa.Column('reason', sa.Text()),
        sa.Column('status', sa.Text(), nullable=False, server_default='open'),
        sa.Column('answer', sa.Text()),
        sa.Column('answered_by', sa.Text()),
        sa.Column('answered_via', sa.Text()),
        sa.Column('answered_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('notified_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('open','answered','dismissed')",
                           name='ck_affiliate_help_escalations_status'),
    )
    op.create_index('ix_affiliate_help_escalations_affiliate', 'affiliate_help_escalations',
                    ['affiliate_id', 'created_at'])
    op.create_index('ix_affiliate_help_escalations_status', 'affiliate_help_escalations',
                    ['status', 'created_at'])

    op.create_table(
        'affiliate_help_messages',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('affiliate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('affiliates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Text()),
        sa.Column('escalation_id', sa.BigInteger(),
                  sa.ForeignKey('affiliate_help_escalations.id', ondelete='SET NULL')),
        sa.Column('read_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('partner','assistant','team')",
                           name='ck_affiliate_help_messages_role'),
    )
    op.create_index('ix_affiliate_help_messages_affiliate', 'affiliate_help_messages',
                    ['affiliate_id', 'created_at'])

    op.create_table(
        'affiliate_help_kb',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, server_default='manual'),
        sa.Column('scope', sa.Text(), nullable=False, server_default='general'),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('affiliate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('affiliates.id', ondelete='CASCADE')),
        sa.Column('escalation_id', sa.BigInteger(),
                  sa.ForeignKey('affiliate_help_escalations.id', ondelete='SET NULL')),
        sa.Column('proposed_question', sa.Text()),
        sa.Column('proposed_answer', sa.Text()),
        sa.Column('updated_by', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("scope IN ('general','partner')", name='ck_affiliate_help_kb_scope'),
        sa.CheckConstraint("status IN ('active','retired')", name='ck_affiliate_help_kb_status'),
        sa.CheckConstraint("source IN ('manual','escalation')", name='ck_affiliate_help_kb_source'),
        # a partner-specific entry must name its partner
        sa.CheckConstraint("scope = 'general' OR affiliate_id IS NOT NULL",
                           name='ck_affiliate_help_kb_partner_scope'),
    )
    op.create_index('ix_affiliate_help_kb_lookup', 'affiliate_help_kb',
                    ['status', 'scope', 'affiliate_id'])


def downgrade():
    op.drop_table('affiliate_help_kb')
    op.drop_table('affiliate_help_messages')
    op.drop_table('affiliate_help_escalations')
