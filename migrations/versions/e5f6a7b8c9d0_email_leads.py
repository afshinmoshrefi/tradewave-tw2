"""email_leads: free personalized seasonal report lead capture

Top-of-funnel email capture for the free seasonal report (web/seasonal_report.py
+ the /api/lead-report route). DOUBLE OPT-IN: the row is written as pending_confirm
with a confirm_token; the heavy report is built/sent only after the user clicks the
emailed confirm link (api_lead_report_confirm). The DB row is the canonical record
(CAN-SPAM consent proof). Lightweight lead - no public_id / sequence / trigger,
unlike support_tickets (7a5c3b9d12ef).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("tickers", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending_confirm'")),
        sa.Column("confirm_token", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending_confirm','sent','failed','spam','expired')",
                           name="email_leads_status_check"),
        sa.UniqueConstraint("confirm_token", name="uq_email_leads_confirm_token"),
    )
    op.create_index("ix_email_leads_created_at", "email_leads", ["created_at"])
    op.create_index("ix_email_leads_email", "email_leads", ["email"])
    op.create_index("ix_email_leads_user_id", "email_leads", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_leads_user_id", table_name="email_leads")
    op.drop_index("ix_email_leads_email", table_name="email_leads")
    op.drop_index("ix_email_leads_created_at", table_name="email_leads")
    op.drop_table("email_leads")
