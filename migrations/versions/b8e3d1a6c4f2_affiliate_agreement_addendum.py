"""affiliates: per-affiliate agreement addendum (Exhibit B - Additional Terms)

Optional, operator-authored rider attached to a SINGLE affiliate's agreement.
The standard body (Sections 1-15 from docs/AFFILIATE_AGREEMENT.md) stays identical
for every affiliate; only this per-affiliate addendum varies. When present it is
rendered (markdown) as "Exhibit B - Additional Terms", appended after Exhibit A on
the signing page AND frozen into the immutable agreement_snapshot when the
affiliate signs. Adding a rider for one affiliate therefore never alters anyone
else's contract and does not bump the global AGREEMENT_VERSION.

Nullable; blank => the agreement renders exactly as before. A generous length
CHECK backstops the wtforms validator.

Revision ID: b8e3d1a6c4f2
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8e3d1a6c4f2'
down_revision = 'c2e5f8a1b3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("agreement_addendum", sa.Text(), nullable=True))
    op.create_check_constraint(
        "affiliates_agreement_addendum_len_check", "affiliates",
        "agreement_addendum IS NULL OR char_length(agreement_addendum) <= 20000")


def downgrade() -> None:
    op.drop_constraint("affiliates_agreement_addendum_len_check", "affiliates", type_="check")
    op.drop_column("affiliates", "agreement_addendum")
