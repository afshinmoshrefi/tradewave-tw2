"""affiliate_lifecycle_comms: applications, messages, notifications, email prefs

TW-TASK-0039 package B (partner lifecycle + communication). Four new tables,
no change to an existing one:

1. affiliate_applications - public /partners/apply submissions.
2. affiliate_messages - admin-composed messages (send-log header).
3. affiliate_notifications - one row per (partner, event): portal inbox,
   email send log and the idempotency claim. UNIQUE (affiliate_id, event_key).
4. affiliate_email_prefs - optional emails a partner turned off.

NOTE for the integrator: two other TW-TASK-0039 packages add migrations from
the same parent (b4d7e1f2a3c5). This one is independent of them (no shared
table); join the heads with an Alembic merge revision.

Revision ID: c5e8f1a2b3d6
Revises: b4d7e1f2a3c5
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = 'c5e8f1a2b3d6'
down_revision = 'b4d7e1f2a3c5'
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "affiliate_applications",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("channels", sa.Text(), nullable=True),
        sa.Column("audience_size", sa.Text(), nullable=True),
        sa.Column("promo_plan", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("agreed_policies_at", _TS, nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('new','approved','rejected','spam')",
                           name="affiliate_applications_status_check"),
    )
    op.create_index("ix_affiliate_applications_email", "affiliate_applications", ["email"])
    op.create_index("ix_affiliate_applications_status", "affiliate_applications",
                    ["status", "created_at"])
    op.create_index("ix_affiliate_applications_ip", "affiliate_applications",
                    ["ip_hash", "created_at"])

    op.create_table(
        "affiliate_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("audience_param", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sent_by", sa.Text(), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "affiliate_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.BigInteger(),
                  sa.ForeignKey("affiliate_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_label", sa.Text(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("email_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("email_reason", sa.Text(), nullable=True),
        sa.Column("to_email", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("emailed_at", _TS, nullable=True),
        sa.Column("read_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("affiliate_id", "event_key", name="uq_affiliate_notification_event"),
        sa.CheckConstraint("email_status IN ('pending','sent','skipped','failed')",
                           name="affiliate_notifications_email_status_check"),
    )
    op.create_index("ix_affiliate_notifications_inbox", "affiliate_notifications",
                    ["affiliate_id", "created_at"])
    op.create_index("ix_affiliate_notifications_message", "affiliate_notifications", ["message_id"])

    op.create_table(
        "affiliate_email_prefs",
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("disabled", JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("affiliate_email_prefs")
    op.drop_index("ix_affiliate_notifications_message", table_name="affiliate_notifications")
    op.drop_index("ix_affiliate_notifications_inbox", table_name="affiliate_notifications")
    op.drop_table("affiliate_notifications")
    op.drop_table("affiliate_messages")
    op.drop_index("ix_affiliate_applications_ip", table_name="affiliate_applications")
    op.drop_index("ix_affiliate_applications_status", table_name="affiliate_applications")
    op.drop_index("ix_affiliate_applications_email", table_name="affiliate_applications")
    op.drop_table("affiliate_applications")
