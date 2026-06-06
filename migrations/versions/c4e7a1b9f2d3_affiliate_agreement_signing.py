"""affiliate_agreement_signing: clickwrap e-signature columns on affiliates

Backs the in-house affiliate agreement signing flow (web/affiliate_agreement.py
+ the public /affiliate/sign/<token> magic-link route + AffiliateAdmin). An
affiliate is created 'paused' and flips to 'active' only once the agreement is
signed, so the referral code can't be used before they've agreed.

Columns (all additive, all on the existing 'affiliates' table - no other table,
billing path, or webhook touched):
  - agreement_version           : version string of the terms presented
  - agreement_signed_name       : the typed legal name (the e-signature)
  - agreement_signed_at         : timestamp of acceptance
  - agreement_signed_ip         : client IP at acceptance (E-SIGN audit trail)
  - agreement_signed_user_agent : client UA at acceptance
  - agreement_snapshot          : immutable copy of the exact terms signed
  - agreement_token_version     : bumped to invalidate an issued signing link

Revision ID: c4e7a1b9f2d3
Revises: b2c0fee1d3a5
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e7a1b9f2d3'
down_revision = 'b2c0fee1d3a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("agreement_version", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_signed_name", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_signed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_signed_ip", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_signed_user_agent", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_snapshot", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("agreement_token_version", sa.Integer(),
                                          nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("affiliates", "agreement_token_version")
    op.drop_column("affiliates", "agreement_snapshot")
    op.drop_column("affiliates", "agreement_signed_user_agent")
    op.drop_column("affiliates", "agreement_signed_ip")
    op.drop_column("affiliates", "agreement_signed_at")
    op.drop_column("affiliates", "agreement_signed_name")
    op.drop_column("affiliates", "agreement_version")
