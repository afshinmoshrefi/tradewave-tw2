"""affiliates: monthly override for interval-split (monthly vs annual terms)

The flat discount_pct / commission_pct ARE the annual terms (default + promo-code
backing). These optional columns are the MONTHLY override (NULL => monthly is the
same as annual), plus the monthly override coupon applied by id at checkout.
Backward compatible: existing affiliates have NULL monthly = flat for both plans.
See web/affiliate_service.effective_* / provision_interval_overrides.

Revision ID: a1b2c3d4e5f6
Revises: f2c3d4e5a6b7
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f2c3d4e5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("discount_pct_monthly", sa.Numeric(5, 2), nullable=True))
    op.add_column("affiliates", sa.Column("commission_pct_monthly", sa.Numeric(5, 2), nullable=True))
    op.add_column("affiliates", sa.Column("stripe_coupon_id_monthly", sa.Text(), nullable=True))
    op.create_check_constraint(
        "affiliates_discount_pct_monthly_check", "affiliates",
        "discount_pct_monthly IS NULL OR (discount_pct_monthly >= 0 AND discount_pct_monthly <= 100)")
    op.create_check_constraint(
        "affiliates_commission_pct_monthly_check", "affiliates",
        "commission_pct_monthly IS NULL OR (commission_pct_monthly >= 0 AND commission_pct_monthly <= 100)")


def downgrade() -> None:
    op.drop_constraint("affiliates_commission_pct_monthly_check", "affiliates", type_="check")
    op.drop_constraint("affiliates_discount_pct_monthly_check", "affiliates", type_="check")
    op.drop_column("affiliates", "stripe_coupon_id_monthly")
    op.drop_column("affiliates", "commission_pct_monthly")
    op.drop_column("affiliates", "discount_pct_monthly")
