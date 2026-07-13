"""affiliates: link to a users row (the affiliate dashboard login)

Adds affiliates.user_id (nullable, unique, FK users.id). NULL = not yet
linked; the portal auto-links on first visit by exact case-insensitive email
match (web/affiliate_portal/blueprint.py), operator can link manually in
AffiliateAdmin. Access to /account/affiliate is derived from this linkage -
no new role is added to models.ROLES (one source of truth: the FK).

Revision ID: e7a1b2c9d4f5
Revises: b8e3d1a6c4f2
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = 'e7a1b2c9d4f5'
down_revision = 'b8e3d1a6c4f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("user_id", PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_affiliates_user_id_users", "affiliates", "users",
        ["user_id"], ["id"], ondelete="SET NULL")
    # One dashboard login per affiliate row AND one affiliate row per login.
    op.create_unique_constraint("uq_affiliates_user_id", "affiliates", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_affiliates_user_id", "affiliates", type_="unique")
    op.drop_constraint("fk_affiliates_user_id_users", "affiliates", type_="foreignkey")
    op.drop_column("affiliates", "user_id")
