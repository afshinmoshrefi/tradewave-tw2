"""email_optouts: unsubscribe suppression list (shared by Resend + MailerLite)

The single source of truth for unsubscribes. Any send to a suppressed email is
skipped. Populated by /unsubscribe (in-email link + Gmail one-click POST) and the
MailerLite unsubscribe webhook, so an opt-out from either system stops both.

Chained off b8e3d1a6c4f2 (the current head) to keep a linear history.

Revision ID: f6a7b8c9d0e1
Revises: b8e3d1a6c4f2
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'b8e3d1a6c4f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_optouts",
        sa.Column("email", sa.Text(), primary_key=True),
        sa.Column("unsubscribed_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("source", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("email_optouts")
