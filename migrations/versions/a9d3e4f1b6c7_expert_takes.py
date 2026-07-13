"""expert_takes: affiliate/expert commentary on SMN articles

One row per take. Lifecycle (STORAGE IDs - never rename, only add):
  draft -> submitted -> approved -> published, plus rejected and retracted.
Operator review is MANDATORY before publish (ExpertTakeAdmin). rendered_html
is stamped at approval time by web/expert_takes_service.py (markdown ->
bleach-sanitized HTML; the single sanitation authority) and is what the SMN
box pulls via /internal/expert_takes (X-Service-Key) and injects into the
static article. declared_call (JSONB, optional) is the scored directional
thesis: {"symbol","direction","entry_date","exit_date"} - Layer 1 of the
two-layer scorecard. execution_note/execution_result are the expert-reported
Layer 2 (labeled, never part of the verified record).

Revision ID: a9d3e4f1b6c7
Revises: f8c2d3e0a5b6
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = 'a9d3e4f1b6c7'
down_revision = 'f8c2d3e0a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expert_takes",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("article_slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("declared_call", JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rendered_html", sa.Text(), nullable=True),
        sa.Column("execution_note", sa.Text(), nullable=True),
        sa.Column("execution_result", sa.Text(), nullable=True),
        sa.Column("execution_result_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retracted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','published','rejected','retracted')",
            name="expert_takes_status_check"),
        sa.CheckConstraint(r"article_slug ~ '^[a-zA-Z0-9_-]{1,200}$'",
                           name="expert_takes_article_slug_charset_check"),
        sa.CheckConstraint("title IS NULL OR char_length(title) <= 120",
                           name="expert_takes_title_len_check"),
        sa.CheckConstraint("char_length(body_md) <= 8000",
                           name="expert_takes_body_len_check"),
        sa.CheckConstraint("execution_note IS NULL OR char_length(execution_note) <= 500",
                           name="expert_takes_execution_note_len_check"),
        sa.CheckConstraint("execution_result IS NULL OR char_length(execution_result) <= 300",
                           name="expert_takes_execution_result_len_check"),
    )
    op.create_index("ix_expert_takes_affiliate", "expert_takes", ["affiliate_id"])
    op.create_index("ix_expert_takes_status", "expert_takes", ["status"])
    op.create_index("ix_expert_takes_article", "expert_takes", ["article_slug"])
    # Cursor for the SMN box's since-pull (/internal/expert_takes?since=...).
    op.create_index("ix_expert_takes_updated", "expert_takes", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_expert_takes_updated", table_name="expert_takes")
    op.drop_index("ix_expert_takes_article", table_name="expert_takes")
    op.drop_index("ix_expert_takes_status", table_name="expert_takes")
    op.drop_index("ix_expert_takes_affiliate", table_name="expert_takes")
    op.drop_table("expert_takes")
