"""affiliate program: affiliates + affiliate_payouts (manual promo-code model)

Backs the Flask-Admin Affiliates tab (web/app.py AffiliateAdmin /
AffiliatePayoutAdmin / AffiliatePayoutComputeView) and the commission engine
(web/affiliate_service.py). This is the in-house, $0/mo affiliate program for the
first ~10 hand-picked partners WITHOUT a paid SaaS (Rewardful/Tolt). Each
affiliate == one Stripe coupon + one promotion code (1:1:1) so every discounted
sale traces to exactly one partner.

  affiliates       : the partner registry.
                     - code: the Stripe promotion-code string customers type.
                       Charset A-Z/0-9/_/- (uppercase canonical). IMMUTABLE once
                       the Stripe coupon exists (Stripe coupons can't be edited).
                     - discount_pct / commission_pct: percentages (20.00 = 20%).
                     - commission_model: mirrors COMMISSION_MODELS in
                       web/models.py (CHECK). Default 'recurring' (lifetime).
  affiliate_payouts: monthly commission ledger. UNIQUE(affiliate_id,
                     period_start, currency) = idempotency key so re-running a
                     month never double-counts. status mirrors PAYOUT_STATUSES.

Additive only: touches no existing table, billing path, or webhook. Safe to
apply during stabilization (isolated new tables).

Revision ID: af1c0de2b3a4
Revises: 7a5c3b9d12ef
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'af1c0de2b3a4'
down_revision = '7a5c3b9d12ef'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliates",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("payout_method", sa.Text(), nullable=True),
        sa.Column("payout_email", sa.Text(), nullable=True),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_model", sa.Text(), nullable=False,
                  server_default=sa.text("'recurring'")),
        sa.Column("stripe_coupon_id", sa.Text(), nullable=True),
        sa.Column("stripe_promotion_code_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(r"code ~ '^[A-Z0-9_-]{2,64}$'",
                           name="affiliates_code_charset_check"),
        sa.CheckConstraint(
            "commission_model IN ('recurring','first_payment','duration_12mo')",
            name="affiliates_commission_model_check"),
        sa.CheckConstraint("status IN ('active','paused','terminated')",
                           name="affiliates_status_check"),
        sa.CheckConstraint("discount_pct >= 0 AND discount_pct <= 100",
                           name="affiliates_discount_pct_check"),
        sa.CheckConstraint("commission_pct >= 0 AND commission_pct <= 100",
                           name="affiliates_commission_pct_check"),
    )
    op.create_unique_constraint("uq_affiliates_code", "affiliates", ["code"])
    op.create_unique_constraint("uq_affiliates_stripe_coupon_id", "affiliates",
                                ["stripe_coupon_id"])
    op.create_index("ix_affiliates_status", "affiliates", ["status"])

    op.create_table(
        "affiliate_payouts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("affiliate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False,
                  server_default=sa.text("'usd'")),
        sa.Column("gross_revenue", sa.Numeric(12, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("status", sa.Text(), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("status IN ('pending','paid','void')",
                           name="affiliate_payouts_status_check"),
        sa.UniqueConstraint("affiliate_id", "period_start", "currency",
                            name="uq_affiliate_payout_period"),
    )
    op.create_index("ix_affiliate_payouts_status", "affiliate_payouts", ["status"])
    op.create_index("ix_affiliate_payouts_affiliate", "affiliate_payouts",
                    ["affiliate_id"])


def downgrade() -> None:
    op.drop_table("affiliate_payouts")
    op.drop_table("affiliates")
