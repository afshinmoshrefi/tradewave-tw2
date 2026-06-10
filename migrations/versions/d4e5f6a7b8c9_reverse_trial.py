"""users: reverse_trial_ends_at (7-day full-access reverse trial for new signups)

New free signups get the FULL Strategist experience for 7 days, then fall back
to a genuinely limited Explorer (DJ30 only - see config.level_access_hierarchy).
NO tier mutation: users.tier stays 'explorer'; the elevation happens at
token-mint time (web/app.py effective_tier), so expiry is implicit and needs
no cron (web/expire_trials.py sweeps the SEPARATE admin-granted trial_ends_at
column and does not touch this one). Additive + nullable; NULL = no reverse
trial (pre-existing users until ops/grant_reverse_trial.py grants one).
Decided by owner 2026-06-10 (supersedes the launch open-paywall decision).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reverse_trial_ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "reverse_trial_ends_at")
