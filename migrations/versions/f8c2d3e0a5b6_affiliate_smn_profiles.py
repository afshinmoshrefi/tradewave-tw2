"""affiliate_smn_profiles: opt-in SMN expert module (1:1 with affiliates)

Row exists only once the operator INVITES the affiliate to the SMN expert
program (AffiliateSmnProfileAdmin). status: invited -> active (click-accept
of the SMN contributor terms in the portal) -> paused. slug is the expert's
public id on SMN (hub page /experts/<slug>.html) - a STORAGE ID: immutable
once published_at is set (tw-coding-standards #2; the portal + admin enforce).
Terms acceptance carries the same audit discipline as the main agreement
(version, timestamp, ip, user-agent, immutable snapshot).

Revision ID: f8c2d3e0a5b6
Revises: e7a1b2c9d4f5
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = 'f8c2d3e0a5b6'
down_revision = 'e7a1b2c9d4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_smn_profiles",
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'invited'")),
        sa.Column("slug", sa.Text(), nullable=True, unique=True),
        sa.Column("bio_md", sa.Text(), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("links", JSONB(), nullable=True),  # [{"label": ..., "url": "https://..."}]
        sa.Column("disclosure_md", sa.Text(), nullable=True),
        sa.Column("terms_version", sa.Text(), nullable=True),
        sa.Column("terms_accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("terms_accepted_ip", sa.Text(), nullable=True),
        sa.Column("terms_accepted_user_agent", sa.Text(), nullable=True),
        sa.Column("terms_snapshot", sa.Text(), nullable=True),
        sa.Column("scorecard_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('invited','active','paused')",
                           name="affiliate_smn_profiles_status_check"),
        sa.CheckConstraint(r"slug IS NULL OR slug ~ '^[a-z0-9-]{2,64}$'",
                           name="affiliate_smn_profiles_slug_charset_check"),
        sa.CheckConstraint("bio_md IS NULL OR char_length(bio_md) <= 4000",
                           name="affiliate_smn_profiles_bio_len_check"),
        sa.CheckConstraint("credentials IS NULL OR char_length(credentials) <= 200",
                           name="affiliate_smn_profiles_credentials_len_check"),
        sa.CheckConstraint("disclosure_md IS NULL OR char_length(disclosure_md) <= 500",
                           name="affiliate_smn_profiles_disclosure_len_check"),
    )
    op.create_index("ix_affiliate_smn_profiles_status", "affiliate_smn_profiles", ["status"])
    op.create_index("ix_affiliate_smn_profiles_updated", "affiliate_smn_profiles", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_affiliate_smn_profiles_updated", table_name="affiliate_smn_profiles")
    op.drop_index("ix_affiliate_smn_profiles_status", table_name="affiliate_smn_profiles")
    op.drop_table("affiliate_smn_profiles")
