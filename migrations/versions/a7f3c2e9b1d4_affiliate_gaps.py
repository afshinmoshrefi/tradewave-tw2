"""affiliate gaps: tax forms, referred signups, click counts

1. affiliates.tax_form_type ('w9' | 'w8ben' | 'w8bene') + tax_form_received_at.
   The agreement (s.6.2) makes a valid tax form a condition of payment; the
   payout ledger now refuses 'paid' until one is on file.
2. users.referred_by_affiliate_id + referred_at: first-touch tw_ref captured
   at SIGNUP (not only at checkout), so the dashboard can show signups/trials.
3. affiliate_clicks: per-(affiliate, UTC day) visit counter for referral-link
   and /join landings.

Additive only; no billing/webhook path changed.

Revision ID: a7f3c2e9b1d4
Revises: fa8c2d601b93
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = 'a7f3c2e9b1d4'
down_revision = 'fa8c2d601b93'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("tax_form_type", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("tax_form_received_at",
                                          sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_check_constraint(
        "affiliates_tax_form_type_check", "affiliates",
        "tax_form_type IS NULL OR tax_form_type IN ('w9','w8ben','w8bene')")

    op.add_column("users", sa.Column("referred_by_affiliate_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("referred_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_users_referred_by_affiliate", "users", "affiliates",
        ["referred_by_affiliate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_referred_by_affiliate", "users", ["referred_by_affiliate_id"])

    op.create_table(
        "affiliate_clicks",
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("affiliate_id", "day", name="pk_affiliate_clicks"),
    )


def downgrade() -> None:
    op.drop_table("affiliate_clicks")
    op.drop_index("ix_users_referred_by_affiliate", table_name="users")
    op.drop_constraint("fk_users_referred_by_affiliate", "users", type_="foreignkey")
    op.drop_column("users", "referred_at")
    op.drop_column("users", "referred_by_affiliate_id")
    op.drop_constraint("affiliates_tax_form_type_check", "affiliates", type_="check")
    op.drop_column("affiliates", "tax_form_received_at")
    op.drop_column("affiliates", "tax_form_type")
