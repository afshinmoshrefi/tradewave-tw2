"""support_tickets: table + sequence for /api/contact form

Adds the support_tickets table backing the Tier-1 contact form (replaces
the legacy mailto-only flow). Schema design notes:

  - id           : uuid PK
  - ticket_number: BigInteger from a dedicated sequence
                   (support_tickets_number_seq). Globally monotonic.
  - public_id    : populated by a BEFORE-INSERT trigger from ticket_number
                   + year(created_at), format TW-YYYY-NNNNN. Year is
                   informational (not a yearly reset). A trigger (not a
                   GENERATED column) because to_char(timestamptz, ...) is
                   STABLE not IMMUTABLE and so isn't legal in a GENERATED
                   expression.
  - topic/status : CHECK constraints mirror the SUPPORT_TICKET_TOPICS
                   and SUPPORT_TICKET_STATUSES tuples in web/models.py.
                   These values are STORAGE IDs; never rename.
  - enrichment   : jsonb snapshot of user context (tier, stripe, last
                   login) at submit time so the notification email and
                   any future audit reflect what was true when the
                   customer wrote in.
  - ip_hash      : sha256(ip + per-env salt). NEVER store raw IP - it's
                   PII drift we don't need.

Indexes: created_at (recent first), status (open queue), email (cust
lookup).

Revision ID: 7a5c3b9d12ef
Revises: 5a3c1e2f4d6b
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '7a5c3b9d12ef'
down_revision = '5a3c1e2f4d6b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sequence first - the table's server_default references it.
    op.execute("CREATE SEQUENCE IF NOT EXISTS support_tickets_number_seq")

    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False,
                  server_default=sa.text("nextval('support_tickets_number_seq')")),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("enrichment", postgresql.JSONB()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("ip_hash", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "topic IN ('bug','feature','billing','account','data','institutional','press','other')",
            name="support_tickets_topic_check",
        ),
        sa.CheckConstraint(
            "status IN ('open','pending_customer','resolved','spam')",
            name="support_tickets_status_check",
        ),
        sa.UniqueConstraint("ticket_number", name="support_tickets_ticket_number_key"),
        sa.UniqueConstraint("public_id", name="support_tickets_public_id_key"),
    )

    # Sequence becomes owned by the column - so dropping the table also
    # drops the sequence, no orphan left behind on downgrade.
    op.execute("ALTER SEQUENCE support_tickets_number_seq OWNED BY support_tickets.ticket_number")

    # BEFORE-INSERT trigger that auto-populates public_id from ticket_number
    # + year(created_at). App code MAY also set public_id directly (e.g. for
    # backfills); the trigger respects that and only fills NULLs.
    op.execute("""
        CREATE OR REPLACE FUNCTION support_tickets_set_public_id() RETURNS trigger AS $$
        BEGIN
            IF NEW.public_id IS NULL THEN
                NEW.public_id := 'TW-' || to_char(NEW.created_at, 'YYYY')
                              || '-' || lpad(NEW.ticket_number::text, 5, '0');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER support_tickets_set_public_id_trg
        BEFORE INSERT ON support_tickets
        FOR EACH ROW
        EXECUTE FUNCTION support_tickets_set_public_id();
    """)

    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_email", "support_tickets", ["email"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_email", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_created_at", table_name="support_tickets")
    # Trigger goes with the table, but be explicit so downgrade is replay-safe.
    op.execute("DROP TRIGGER IF EXISTS support_tickets_set_public_id_trg ON support_tickets")
    op.drop_table("support_tickets")
    op.execute("DROP FUNCTION IF EXISTS support_tickets_set_public_id()")
    # Sequence is owned by the column, so the DROP TABLE above drops it
    # too; the IF EXISTS guard is just paranoia for partial rollbacks.
    op.execute("DROP SEQUENCE IF EXISTS support_tickets_number_seq")
