"""affiliates: co-branded landing page fields (display name + logo)

Optional, operator-entered. `page_display_name` is the name shown on the public
/join/<code> landing page (personal or business; falls back to `name`).
`page_logo` is the stored filename of an uploaded logo under
/var/www/tradewave/assets/affiliate-logos/. Both NULL for affiliates without a page.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("page_display_name", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("page_logo", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("affiliates", "page_logo")
    op.drop_column("affiliates", "page_display_name")
