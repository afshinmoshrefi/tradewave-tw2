"""tier_compat: analyst=4, strategist=6 (was inverted)

This revision captures the data-side correction made on 2026-05-06 to
/home/flask/web/tier_compat.py.

Background:
  TW1 (legacy WP UMP) level IDs:
    1 = free / Ripple
    4 = Pro yearly      (entry paid)
    5 = Pro monthly     (entry paid, same access as 4)
    6 = Inst. yearly    (top paid)
    7 = Inst. monthly   (top paid, same access as 6)

  Earlier in TW2's life the mapping had been written inverted (analyst→6,
  strategist→4). The React app gates on numeric levels via
  window.current_user_level → wpUserLevels, so the inversion gave Analyst
  users top-tier access and Strategist users entry-paid access.

  Today's tier_compat.py fix codified the correct mapping:
    explorer   → '1'
    analyst    → '4'   (entry paid)
    strategist → '6'   (top paid)

This is NOT a schema change — it is a one-time data sweep that re-derives
users.legacy_wp_level from users.tier under the corrected mapping.
The UPDATEs are idempotent: re-running them on already-correct rows is a
no-op.

Revision ID: 18eb4ac1baa0
Revises: c0d92cd5de83
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '18eb4ac1baa0'
down_revision = 'c0d92cd5de83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Strategist: should be '6'. If we previously wrote '4' or '5' (the
    # inverted entry-paid IDs), correct to '6'.
    op.execute(
        "UPDATE users "
        "SET legacy_wp_level = '6' "
        "WHERE tier = 'strategist' AND legacy_wp_level IN ('4', '5')"
    )
    # Analyst: should be '4' (yearly default). If previously '6' or '7'
    # (the inverted top-paid IDs), correct to '4'.
    op.execute(
        "UPDATE users "
        "SET legacy_wp_level = '4' "
        "WHERE tier = 'analyst' AND legacy_wp_level IN ('6', '7')"
    )
    # Explorer: should be '1'. Anything else is wrong; force '1'.
    op.execute(
        "UPDATE users "
        "SET legacy_wp_level = '1' "
        "WHERE tier = 'explorer' AND legacy_wp_level <> '1'"
    )


def downgrade() -> None:
    # Reverting a corruption fix would re-corrupt the data. Refuse.
    pass
