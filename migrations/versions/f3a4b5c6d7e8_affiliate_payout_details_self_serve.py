"""affiliate self-serve payout details

Additive. Two columns on affiliates for the partner's own "Payout details"
form on the dashboard Payouts page:

1. payout_account_name - the account holder name the payout is sent to. Wise
   needs the recipient's name; the Wise export file uses it (else `name`).
2. payout_details_changed_at - when the PARTNER last changed a payout method
   or payout email that was already on file. Payouts to that partner are held
   for 24 hours after it (affiliate_service.payout_details_hold_until, the
   same gate as the tax form: affiliate_admin.payout_block_reason). NULL = no
   hold. An admin edit in Flask-Admin does not set it.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("affiliates", sa.Column("payout_account_name", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("payout_details_changed_at",
                                          sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade():
    op.drop_column("affiliates", "payout_details_changed_at")
    op.drop_column("affiliates", "payout_account_name")
