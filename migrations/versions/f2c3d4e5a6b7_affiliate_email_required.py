"""affiliates.email NOT NULL (required)

The self-referral guard compares the affiliate's email to the buyer's; a NULL
email made it a no-op (an emailless affiliate could self-refer). Email is now
required - the AffiliateAdmin form requires it (model nullable=False) and the DB
enforces it. Fail-closed: if a legacy NULL email exists this migration aborts the
deploy so the operator fills it in rather than silently shipping a broken guard.

Revision ID: f2c3d4e5a6b7
Revises: e1b2c3d4f5a6
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'f2c3d4e5a6b7'
down_revision = 'e1b2c3d4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("affiliates", "email", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.alter_column("affiliates", "email", existing_type=sa.Text(), nullable=True)
