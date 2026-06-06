"""status default -> paused, backfill, and affiliate_payouts.locked

Two review fixes:
  1. affiliates.status server_default 'active' -> 'paused'. The app convention is
     active <=> signed (the activation gate), but the DB default was 'active', so a
     row created outside AffiliateAdmin (or before the signing migration) could be
     active-and-unsigned and get paid. Also backfill any existing active+unsigned
     affiliate to paused.
  2. affiliate_payouts.locked (bool, default false). upsert_month refreshes still-
     pending rows on every re-run, which clobbered an operator's hand-netted
     commission_amount. A hand-edit now sets locked=true and upsert_month skips
     locked rows, so manual adjustments survive re-compute.

Additive / safe; no billing/webhook contract changed.

Revision ID: e1b2c3d4f5a6
Revises: d5f8a2c1b6e4
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'e1b2c3d4f5a6'
down_revision = 'd5f8a2c1b6e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. status default -> paused (active <=> signed) + backfill active-but-unsigned.
    op.alter_column("affiliates", "status", server_default=sa.text("'paused'"))
    op.execute("UPDATE affiliates SET status='paused' "
               "WHERE status='active' AND agreement_signed_at IS NULL")
    # 2. payout lock so a hand-adjusted pending row isn't clobbered by re-compute.
    op.add_column("affiliate_payouts",
                  sa.Column("locked", sa.Boolean(), nullable=False,
                            server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("affiliate_payouts", "locked")
    op.alter_column("affiliates", "status", server_default=sa.text("'active'"))
