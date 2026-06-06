"""affiliate_referrals: persisted customer/subscription -> affiliate attribution

Backs the durable referral record (web/models.py AffiliateReferral). Written from
the subscription webhook (affiliate id carried in Stripe subscription metadata,
stamped at checkout). Commission attribution joins to this table first; the coupon
becomes corroboration only, so a recurring affiliate keeps earning after the
12-month discount coupon leaves the invoice, and coupon expiry/deletion can't
orphan history. Additive only; no existing table/billing/webhook contract changed.

Revision ID: d5f8a2c1b6e4
Revises: c4e7a1b9f2d3
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd5f8a2c1b6e4'
down_revision = 'c4e7a1b9f2d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("affiliate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column("stripe_subscription_id", sa.Text(), nullable=False),
        sa.Column("referral_code", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'checkout'")),
        sa.Column("attributed_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_affiliate_referrals_subscription",
                                "affiliate_referrals", ["stripe_subscription_id"])
    op.create_index("ix_affiliate_referrals_customer", "affiliate_referrals",
                    ["stripe_customer_id"])
    op.create_index("ix_affiliate_referrals_affiliate", "affiliate_referrals",
                    ["affiliate_id"])


def downgrade() -> None:
    op.drop_table("affiliate_referrals")
