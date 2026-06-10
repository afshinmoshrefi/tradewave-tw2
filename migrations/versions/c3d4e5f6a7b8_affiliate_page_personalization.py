"""affiliates: landing-page personalization (headshot photo + personal note + sign-off)

Optional, operator-entered fields for the /join/<code> co-branded page:
  page_photo    - stored filename of an uploaded headshot (circular avatar)
  page_note     - short first-person note to the affiliate's audience (<=280 chars, plain text)
  page_signoff  - attribution line shown under the note (<=60 chars)
All nullable; blank => the page renders as before. Length CHECKs backstop the
wtforms validators so a raw insert can't blow out the hero. Mirrors the
page_display_name/page_logo additive pattern.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliates", sa.Column("page_photo", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("page_note", sa.Text(), nullable=True))
    op.add_column("affiliates", sa.Column("page_signoff", sa.Text(), nullable=True))
    op.create_check_constraint(
        "affiliates_page_note_len_check", "affiliates",
        "page_note IS NULL OR char_length(page_note) <= 280")
    op.create_check_constraint(
        "affiliates_page_signoff_len_check", "affiliates",
        "page_signoff IS NULL OR char_length(page_signoff) <= 60")


def downgrade() -> None:
    op.drop_constraint("affiliates_page_signoff_len_check", "affiliates", type_="check")
    op.drop_constraint("affiliates_page_note_len_check", "affiliates", type_="check")
    op.drop_column("affiliates", "page_signoff")
    op.drop_column("affiliates", "page_note")
    op.drop_column("affiliates", "page_photo")
