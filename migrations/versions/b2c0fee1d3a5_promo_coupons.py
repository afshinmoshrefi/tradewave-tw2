"""promo_coupons: standalone marketing discount codes (no affiliate/commission)

Backs the Flask-Admin "Coupons" tab (web/app.py PromoCouponAdmin) + the
provisioning helper (web/promo_service.py). These are plain discount codes NOT
tied to any affiliate - launch promos, sales, comps/free access, unpaid
partners. Each row == one Stripe coupon + one promotion code (1:1), created
automatically on save. Distinct from the affiliate program (affiliates table),
which adds commission tracking + payouts on top of the same Stripe primitives.

Supported shapes (all four): percent off, fixed-amount off (needs currency),
free/100% (percent_off=100), and time-limited (expires_at + max_redemptions on
the promotion code). code + discount are immutable once the Stripe coupon
exists (Stripe coupons can't be edited).

Additive only; no existing table/billing/webhook touched.

Revision ID: b2c0fee1d3a5
Revises: af1c0de2b3a4
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b2c0fee1d3a5'
down_revision = 'af1c0de2b3a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),          # internal label
        sa.Column("discount_type", sa.Text(), nullable=False),  # 'percent' | 'amount'
        sa.Column("percent_off", sa.Numeric(5, 2), nullable=True),
        sa.Column("amount_off_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),        # required for amount
        sa.Column("duration", sa.Text(), nullable=False, server_default=sa.text("'once'")),
        sa.Column("duration_in_months", sa.Integer(), nullable=True),  # for repeating
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("stripe_coupon_id", sa.Text(), nullable=True),
        sa.Column("stripe_promotion_code_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(r"code ~ '^[A-Z0-9_-]{2,64}$'",
                           name="promo_coupons_code_charset_check"),
        sa.CheckConstraint("discount_type IN ('percent','amount')",
                           name="promo_coupons_discount_type_check"),
        sa.CheckConstraint("duration IN ('once','repeating','forever')",
                           name="promo_coupons_duration_check"),
        sa.CheckConstraint("status IN ('active','archived')",
                           name="promo_coupons_status_check"),
        # repeating needs a month count
        sa.CheckConstraint("duration <> 'repeating' OR duration_in_months IS NOT NULL",
                           name="promo_coupons_repeating_months_check"),
        sa.CheckConstraint("percent_off IS NULL OR (percent_off > 0 AND percent_off <= 100)",
                           name="promo_coupons_percent_range_check"),
        sa.CheckConstraint("amount_off_cents IS NULL OR amount_off_cents > 0",
                           name="promo_coupons_amount_positive_check"),
        sa.CheckConstraint("max_redemptions IS NULL OR max_redemptions > 0",
                           name="promo_coupons_max_redemptions_check"),
        # discount shape: percent needs percent_off; amount needs amount_off_cents + currency
        sa.CheckConstraint(
            "(discount_type = 'percent' AND percent_off IS NOT NULL AND amount_off_cents IS NULL) "
            "OR (discount_type = 'amount' AND amount_off_cents IS NOT NULL AND currency IS NOT NULL AND percent_off IS NULL)",
            name="promo_coupons_discount_shape_check"),
    )
    op.create_unique_constraint("uq_promo_coupons_code", "promo_coupons", ["code"])
    op.create_unique_constraint("uq_promo_coupons_stripe_coupon_id", "promo_coupons",
                                ["stripe_coupon_id"])
    op.create_index("ix_promo_coupons_status", "promo_coupons", ["status"])


def downgrade() -> None:
    op.drop_table("promo_coupons")
