"""schema_hardening: tier check, unique sub_id, coupon unique, tier-level trigger

Hardening pass on 2026-05-06 covering four DB-level invariants that
previously lived only in application code:

  1. CHECK on users.tier — restricts to {explorer, analyst, strategist,
     canceled}. Closes the gap where any text value could be written.
  2. UNIQUE index on users.stripe_subscription_id (partial: WHERE NOT
     NULL). Stripe's subscription IDs are globally unique; a duplicate
     row would mean a webhook handler bug or a bad migration.
  3. UNIQUE on (coupons_used.user_id, stripe_coupon_id). A given user
     can only have used a given Stripe coupon once.
  4. Trigger users_legacy_wp_level_sync — keeps legacy_wp_level in lock
     step with tier. Prevents another tier_compat-style inversion from
     ever drifting the column out of agreement with tier.

All four objects use IF NOT EXISTS / DROP-then-CREATE patterns so the
migration is safe to re-apply.

Revision ID: 1940d1f63473
Revises: 18eb4ac1baa0
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '1940d1f63473'
down_revision = '18eb4ac1baa0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. CHECK constraint on users.tier.
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_check"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_tier_check "
        "CHECK (tier IN ('explorer','analyst','strategist','canceled'))"
    )

    # 2. UNIQUE on stripe_subscription_id (partial — NULLs allowed).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_subscription_id_key "
        "ON users (stripe_subscription_id) "
        "WHERE stripe_subscription_id IS NOT NULL"
    )

    # 3. UNIQUE on (coupons_used.user_id, stripe_coupon_id).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS coupons_used_user_coupon_uniq "
        "ON coupons_used (user_id, stripe_coupon_id)"
    )

    # 4. Trigger function: keep legacy_wp_level synchronized with tier.
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
    op.execute(
        "DROP TRIGGER IF EXISTS users_legacy_wp_level_sync ON users"
    )
    op.execute(
        "CREATE TRIGGER users_legacy_wp_level_sync "
        "BEFORE INSERT OR UPDATE OF tier ON users "
        "FOR EACH ROW EXECUTE FUNCTION users_sync_legacy_wp_level()"
    )


def downgrade() -> None:
    # Reverse in opposite order — trigger first, then function, then
    # indexes, then check constraint.
    op.execute(
        "DROP TRIGGER IF EXISTS users_legacy_wp_level_sync ON users"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS users_sync_legacy_wp_level()"
    )
    op.execute(
        "DROP INDEX IF EXISTS coupons_used_user_coupon_uniq"
    )
    op.execute(
        "DROP INDEX IF EXISTS users_stripe_subscription_id_key"
    )
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_check"
    )
