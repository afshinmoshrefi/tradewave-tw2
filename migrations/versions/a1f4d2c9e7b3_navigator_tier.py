"""navigator_tier: widen users.tier CHECK + legacy_wp_level trigger for 'navigator'

Adds the new entry-paid tier 'navigator' (Dow + NASDAQ + S&P 500, legacy WP
level '2', between Explorer '1' and Analyst '4') to the two DB-level invariants
that pin the tier set:

  1. CHECK users_tier_check — widen {explorer,analyst,strategist,canceled} to
     also allow 'navigator'. Without this the customer.subscription webhook
     would 500 while Stripe charges (silent revenue break) the moment a
     navigator subscription resolves.
  2. Trigger function users_sync_legacy_wp_level() — add WHEN 'navigator'
     THEN '2' so legacy_wp_level can never drift from tier for navigator rows
     (mirrors tier_compat.TIER_TO_LEGACY_LEVEL['navigator'] = '2').

Keep in sync with web/models.py users_tier_check and web/tier_compat.py.
Re-apply-safe (DROP-then-ADD / CREATE OR REPLACE).

NOTE: downgrade() narrows the CHECK back to the 4-tier set; it will FAIL if any
users.tier = 'navigator' rows still exist — migrate them off first.

Revision ID: a1f4d2c9e7b3
Revises: f6a7b8c9d0e1
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = 'a1f4d2c9e7b3'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Widen the tier CHECK to include 'navigator'.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_tier_check "
        "CHECK (tier IN ('explorer','navigator','analyst','strategist','canceled'))"
    )

    # 2. Teach the legacy_wp_level sync trigger about navigator ('2').
    op.execute("""
        CREATE OR REPLACE FUNCTION users_sync_legacy_wp_level()
        RETURNS trigger AS $$
        BEGIN
            NEW.legacy_wp_level := CASE NEW.tier
                WHEN 'explorer'   THEN '1'
                WHEN 'navigator'  THEN '2'
                WHEN 'analyst'    THEN '4'
                WHEN 'strategist' THEN '6'
                ELSE NEW.legacy_wp_level
            END;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Revert the trigger to the 4-tier mapping first, then narrow the CHECK.
    op.execute("""
        CREATE OR REPLACE FUNCTION users_sync_legacy_wp_level()
        RETURNS trigger AS $$
        BEGIN
            NEW.legacy_wp_level := CASE NEW.tier
                WHEN 'explorer'   THEN '1'
                WHEN 'analyst'    THEN '4'
                WHEN 'strategist' THEN '6'
                ELSE NEW.legacy_wp_level
            END;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_tier_check "
        "CHECK (tier IN ('explorer','analyst','strategist','canceled'))"
    )
