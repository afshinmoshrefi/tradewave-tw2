"""baseline schema

Captures the schema that was hand-rolled into the tradewave database on
2026-05-03 (per the schema_version row 1: "initial TW2 schema: users,
audit_log, stripe_events, coupons_used"). This revision is a NO-OP at the
DDL level — it only documents the tables already present so future
revisions can build on a known starting point.

Tables present at baseline:
  - users (PK uuid, indexes on email/tier/api_key/stripe_customer/workos_id)
  - audit_log (PK bigserial, FKs to users on actor + target with ON DELETE
    SET NULL)
  - stripe_events (PK bigserial, unique stripe_event_id, FK to users)
  - coupons_used (PK bigserial, FK to users with ON DELETE CASCADE)
  - schema_version (legacy bookkeeping; superseded by alembic_version)

Trigger: users_updated_at BEFORE UPDATE ON users FOR EACH ROW
EXECUTE FUNCTION set_updated_at().

Apply method: this revision is stamped, NOT upgraded. The DB already has
the objects; running upgrade()/downgrade() here would either no-op or
destroy data.

Revision ID: c0d92cd5de83
Revises:
Create Date: 2026-05-06
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = 'c0d92cd5de83'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Baseline: schema already exists. This is a stamp-only revision."""
    pass


def downgrade() -> None:
    """Refuse to drop the entire baseline schema. One-way revision."""
    raise RuntimeError(
        "downgrade of baseline is not supported — would drop all TW2 tables"
    )
