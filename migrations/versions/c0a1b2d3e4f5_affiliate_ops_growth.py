"""affiliate ops + growth: tax forms, sub-links, creative library

TW-TASK-0039 package C (affiliate_ops_growth). Additive only.

1. affiliate_tax_forms - one row per uploaded W-9 / W-8BEN / W-8BEN-E PDF.
   The file is Fernet-encrypted on disk outside the web root; the row holds
   the random storage name, size, SHA-256 and the review status.
2. affiliate_sublinks + affiliate_sublink_clicks - partner-created named
   sub-links (?code=X&sub=name) and their per-day visit counters.
3. users.referred_sub, affiliate_referrals.sub_link - the sub-link slug stored
   with the signup stamp and the referral. Reporting only: neither column is
   read by attribution or by the commission engine.
4. affiliate_creatives - admin-uploaded banners / logos / copy.

NOTE: packages A and B of the same task add migrations from the same parent
(b4d7e1f2a3c5); the integrator adds the merge revision.

Revision ID: c0a1b2d3e4f5
Revises: b4d7e1f2a3c5
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = 'c0a1b2d3e4f5'
down_revision = 'b4d7e1f2a3c5'
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade():
    op.create_table(
        "affiliate_tax_forms",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("form_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'received'")),
        sa.Column("reject_reason", sa.Text),
        sa.Column("storage_name", sa.Text),
        sa.Column("original_filename", sa.Text),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("sha256", sa.Text),
        sa.Column("uploaded_by_user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("reviewed_at", _TS),
        sa.Column("reviewed_by", sa.Text),
        sa.CheckConstraint("form_type IN ('w9','w8ben','w8bene')",
                           name="affiliate_tax_forms_form_type_check"),
        sa.CheckConstraint("status IN ('received','accepted','rejected','replaced')",
                           name="affiliate_tax_forms_status_check"),
    )
    op.create_index("ix_affiliate_tax_forms_affiliate", "affiliate_tax_forms",
                    ["affiliate_id", "uploaded_at"])
    op.create_index("ix_affiliate_tax_forms_status", "affiliate_tax_forms", ["status"])

    op.create_table(
        "affiliate_sublinks",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sub", sa.Text, nullable=False),
        sa.Column("label", sa.Text),
        sa.Column("campaign_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("promo_campaigns.id", ondelete="SET NULL")),
        sa.Column("archived_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.UniqueConstraint("affiliate_id", "sub", name="uq_affiliate_sublink_sub"),
        sa.CheckConstraint(r"sub ~ '^[a-z0-9][a-z0-9_-]{0,39}$'",
                           name="affiliate_sublinks_sub_charset_check"),
        sa.CheckConstraint("label IS NULL OR char_length(label) <= 80",
                           name="affiliate_sublinks_label_len_check"),
    )
    op.create_table(
        "affiliate_sublink_clicks",
        sa.Column("sublink_id", sa.BigInteger,
                  sa.ForeignKey("affiliate_sublinks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("clicks", sa.Integer, nullable=False, server_default=sa.text("0")),
    )

    op.add_column("users", sa.Column("referred_sub", sa.Text))
    op.add_column("affiliate_referrals", sa.Column("sub_link", sa.Text))
    op.create_index("ix_affiliate_referrals_sub", "affiliate_referrals", ["affiliate_id", "sub_link"])

    op.create_table(
        "affiliate_creatives",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("file_name", sa.Text),
        sa.Column("original_filename", sa.Text),
        sa.Column("mime_type", sa.Text),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("campaign_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("promo_campaigns.id", ondelete="SET NULL")),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'active'")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Text),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("kind IN ('banner','logo','email','social')",
                           name="affiliate_creatives_kind_check"),
        sa.CheckConstraint("status IN ('active','archived')",
                           name="affiliate_creatives_status_check"),
        sa.CheckConstraint("char_length(title) <= 120", name="affiliate_creatives_title_len_check"),
    )
    op.create_index("ix_affiliate_creatives_status", "affiliate_creatives", ["status", "kind"])


def downgrade():
    op.drop_index("ix_affiliate_creatives_status", table_name="affiliate_creatives")
    op.drop_table("affiliate_creatives")
    op.drop_index("ix_affiliate_referrals_sub", table_name="affiliate_referrals")
    op.drop_column("affiliate_referrals", "sub_link")
    op.drop_column("users", "referred_sub")
    op.drop_table("affiliate_sublink_clicks")
    op.drop_table("affiliate_sublinks")
    op.drop_index("ix_affiliate_tax_forms_status", table_name="affiliate_tax_forms")
    op.drop_index("ix_affiliate_tax_forms_affiliate", table_name="affiliate_tax_forms")
    op.drop_table("affiliate_tax_forms")
