"""first_ai_score_viewed_at: Postgres activation signal for the AI score

Adds users.first_ai_score_viewed_at (nullable TIMESTAMPTZ), stamped once,
idempotently, the first time a logged-in user with AI-score access (Analyst+)
actually renders an AI score in the wave-viewer. Written by the SAME web-tier
handler (POST /api/activation/ai-score-viewed) that appends the
onboarding_events row (event_type='ai_score_viewed') and fires the GA4
ai_score_viewed event (web/ga4_mp.py) - GTM playbook CARD W1.4, strategy §2
machine-part-1 persistence rule: the day-2/day-7 activation emails read THIS
column, never GA4. onboarding_events already exists (c2e5f8a1b3d4) and is
reused as-is for the per-view record; this migration only adds the
first-touch column on users.

Revision ID: b3f6a8c1d9e2
Revises: a9d3e4f1b6c7
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3f6a8c1d9e2'
down_revision = 'a9d3e4f1b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('first_ai_score_viewed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'first_ai_score_viewed_at')
