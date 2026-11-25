"""affiliate review fixes + owner-side gap closure (TW-TASK-0039, fix-0039)

Additive except for one foreign key that is recreated with a new delete rule.

1. affiliate_payouts.exported_at / exported_amount / paid_amount - the amount
   written into the last PayPal / Wise export file, so a bulk import can
   refuse a row whose ledger amount changed after the file was made, and the
   "Payout sent" email can state what was actually sent.
2. affiliate_jobs - durable queue for slow work that must not run inside a web
   request (group message sends, knowledge-base generalisation).
3. affiliate_program_settings - owner-editable program settings (key -> JSON);
   first key: 'auto_approve'.
4. users.referred_ip_hash - salted hash of the IP of a REFERRED signup, for
   the fraud signals on the payout screens (never the raw IP).
5. affiliate_tax_forms.affiliate_id: ON DELETE RESTRICT -> CASCADE, so a test
   partner with an uploaded form can be hard-deleted (the admin delete also
   removes the encrypted files first). Partners with customers or payouts are
   still protected by affiliate_referrals / affiliate_payouts RESTRICT.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")
_TAX_FK = "affiliate_tax_forms_affiliate_id_fkey"


def _tax_fk(ondelete):
    op.drop_constraint(_TAX_FK, "affiliate_tax_forms", type_="foreignkey")
    op.create_foreign_key(_TAX_FK, "affiliate_tax_forms", "affiliates",
                          ["affiliate_id"], ["id"], ondelete=ondelete)


def upgrade():
    op.add_column("affiliate_payouts", sa.Column("exported_at", _TS))
    op.add_column("affiliate_payouts", sa.Column("exported_amount", sa.Numeric(12, 2)))
    op.add_column("affiliate_payouts", sa.Column("paid_amount", sa.Numeric(12, 2)))

    op.create_table(
        "affiliate_jobs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("result", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_by", sa.Text),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("started_at", _TS),
        sa.Column("finished_at", _TS),
        sa.CheckConstraint("status IN ('queued','running','done','failed')",
                           name="affiliate_jobs_status_check"),
    )
    op.create_index("ix_affiliate_jobs_status", "affiliate_jobs", ["status", "created_at"])

    op.create_table(
        "affiliate_program_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_by", sa.Text),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    )

    op.add_column("users", sa.Column("referred_ip_hash", sa.Text))
    op.create_index("ix_users_referred_ip_hash", "users", ["referred_ip_hash"],
                    postgresql_where=sa.text("referred_ip_hash IS NOT NULL"))

    _tax_fk("CASCADE")


def downgrade():
    _tax_fk("RESTRICT")
    op.drop_index("ix_users_referred_ip_hash", table_name="users")
    op.drop_column("users", "referred_ip_hash")
    op.drop_table("affiliate_program_settings")
    op.drop_index("ix_affiliate_jobs_status", table_name="affiliate_jobs")
    op.drop_table("affiliate_jobs")
    op.drop_column("affiliate_payouts", "paid_amount")
    op.drop_column("affiliate_payouts", "exported_amount")
    op.drop_column("affiliate_payouts", "exported_at")
