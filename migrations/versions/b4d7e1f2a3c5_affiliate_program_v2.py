"""affiliate program v2: terms versions, campaigns, commission ledger

TW-TASK-0038. One migration for the whole v2 data model:

1. affiliate_terms - versioned, immutable commission terms. Seeds three
   versions: v2-5y (default: renewals in years 2-5), v2-10y, v2-lifetime.
2. affiliates - terms_id, discount_changed_at, terminated_for_cause /
   terminated_at / termination_cause. Existing rows move to v2-5y with the
   customer discount clamped to 25, and every ACTIVE partner is PAUSED pending
   re-signature of agreement v2 (owner rule 12). The old signature evidence is
   archived to audit_log (action affiliate_v2_resign_required) before the
   signature columns are cleared, exactly as the Change-terms flow clears them.
   The Stripe side (deactivate the paused promo codes, re-issue coupons that
   were above 25%) is NOT reachable from a migration: run
   affiliate_service.reconcile_v2_stripe(session) once after upgrading.
3. affiliate_discount_changes - history of self-serve discount changes.
4. promo_campaigns - company-wide intro offers (claim window, per plan).
5. affiliate_referrals - the checkout snapshot (terms, offer type, campaign,
   tier, interval, list price, discount) plus first_paid_at / year_anchor_at /
   ended_at / prior_referral_id, and a CHECK on source.
6. affiliate_commission_lines - the insert-once per-invoice ledger that
   affiliate_payouts aggregates. UNIQUE (affiliate_id, source_id).

Column is named billing_interval (not interval): INTERVAL is an SQL type name.

Revision ID: b4d7e1f2a3c5
Revises: a7f3c2e9b1d4
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


revision = 'b4d7e1f2a3c5'
down_revision = 'a7f3c2e9b1d4'
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # --- 1. terms ----------------------------------------------------------
    terms = op.create_table(
        "affiliate_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("pool_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("50")),
        sa.Column("max_discount_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("25")),
        sa.Column("promo_commission_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("50")),
        sa.Column("renewal_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("25")),
        sa.Column("renewal_years", sa.Integer(), nullable=True),
        sa.Column("activity_rule_months", sa.Integer(), nullable=False, server_default=sa.text("12")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("version", name="affiliate_terms_version_key"),
        sa.CheckConstraint("pool_pct >= 0 AND pool_pct <= 100", name="affiliate_terms_pool_pct_check"),
        sa.CheckConstraint("max_discount_pct >= 0 AND max_discount_pct <= pool_pct",
                           name="affiliate_terms_max_discount_pct_check"),
        sa.CheckConstraint("promo_commission_pct >= 0 AND promo_commission_pct <= 100",
                           name="affiliate_terms_promo_commission_pct_check"),
        sa.CheckConstraint("renewal_pct >= 0 AND renewal_pct <= 100",
                           name="affiliate_terms_renewal_pct_check"),
        sa.CheckConstraint("renewal_years IS NULL OR renewal_years >= 1",
                           name="affiliate_terms_renewal_years_check"),
        sa.CheckConstraint("activity_rule_months >= 0",
                           name="affiliate_terms_activity_rule_months_check"),
    )
    op.bulk_insert(terms, [
        {"version": "v2-5y", "renewal_years": 5,
         "notes": "Program v2 default: 50% pool, discount 0-25%, promo 50% of paid, "
                  "renewals 25% of paid in years 2-5, 12-month activity rule."},
        {"version": "v2-10y", "renewal_years": 10,
         "notes": "Program v2 with renewals in years 2-10."},
        {"version": "v2-lifetime", "renewal_years": None,
         "notes": "Program v2 with lifetime renewals."},
    ])

    # --- 2. affiliates -----------------------------------------------------
    op.add_column("affiliates", sa.Column("terms_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_affiliates_terms", "affiliates", "affiliate_terms",
                          ["terms_id"], ["id"], ondelete="RESTRICT")
    op.add_column("affiliates", sa.Column("discount_changed_at", _TS, nullable=True))
    op.add_column("affiliates", sa.Column("terminated_for_cause", sa.Boolean(), nullable=False,
                                          server_default=sa.text("false")))
    op.add_column("affiliates", sa.Column("terminated_at", _TS, nullable=True))
    op.add_column("affiliates", sa.Column("termination_cause", sa.Text(), nullable=True))

    op.execute("UPDATE affiliates SET terms_id = (SELECT id FROM affiliate_terms WHERE version = 'v2-5y')")
    op.execute("UPDATE affiliates SET discount_pct = 25 WHERE discount_pct > 25")
    op.execute("UPDATE affiliates SET discount_pct_monthly = 25 WHERE discount_pct_monthly > 25")
    # Archive the v1 signature evidence, then require re-signature of v2.
    op.execute("""
        INSERT INTO audit_log (actor_label, action, details)
        SELECT 'migration:b4d7e1f2a3c5', 'affiliate_v2_resign_required',
               jsonb_build_object(
                   'affiliate_id', id::text, 'code', code,
                   'agreement_version', agreement_version,
                   'signed_name', agreement_signed_name,
                   'signed_at', agreement_signed_at,
                   'signed_ip', agreement_signed_ip,
                   'signed_user_agent', agreement_signed_user_agent,
                   'snapshot', agreement_snapshot,
                   'commission_pct', commission_pct,
                   'commission_model', commission_model)
        FROM affiliates
        WHERE status = 'active' OR agreement_signed_at IS NOT NULL
    """)
    op.execute("""
        UPDATE affiliates
        SET status = CASE WHEN status = 'active' THEN 'paused' ELSE status END,
            agreement_signed_name = NULL, agreement_signed_at = NULL,
            agreement_signed_ip = NULL, agreement_signed_user_agent = NULL,
            agreement_snapshot = NULL,
            agreement_token_version = agreement_token_version + 1
        WHERE status <> 'terminated'
          AND (status = 'active' OR agreement_signed_at IS NOT NULL)
    """)

    # --- 3. discount history -------------------------------------------------
    op.create_table(
        "affiliate_discount_changes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("billing_interval", sa.Text(), nullable=False),
        sa.Column("old_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("new_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("old_coupon_id", sa.Text(), nullable=True),
        sa.Column("new_coupon_id", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("changed_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("billing_interval IN ('month','year')",
                           name="affiliate_discount_changes_billing_interval_check"),
    )
    op.create_index("ix_affiliate_discount_changes_affiliate", "affiliate_discount_changes",
                    ["affiliate_id", "changed_at"])

    # --- 4. campaigns ----------------------------------------------------------
    op.create_table(
        "promo_campaigns",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tiers", JSONB(), nullable=False),
        sa.Column("billing_intervals", JSONB(), nullable=False),
        sa.Column("new_customers_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("starts_at", _TS, nullable=False),
        sa.Column("ends_at", _TS, nullable=False),
        sa.Column("offer_type", sa.Text(), nullable=False),
        sa.Column("intro_prices", JSONB(), nullable=True),
        sa.Column("percent_off", sa.Numeric(5, 2), nullable=True),
        sa.Column("intro_months", sa.Integer(), nullable=False, server_default=sa.text("12")),
        sa.Column("stripe_coupon_ids", JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="promo_campaigns_code_key"),
        sa.CheckConstraint(r"code ~ '^[A-Z0-9_-]{2,64}$'", name="promo_campaigns_code_charset_check"),
        sa.CheckConstraint("offer_type IN ('price','percent')", name="promo_campaigns_offer_type_check"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="promo_campaigns_status_check"),
        sa.CheckConstraint("ends_at > starts_at", name="promo_campaigns_window_check"),
        sa.CheckConstraint("percent_off IS NULL OR (percent_off > 0 AND percent_off <= 100)",
                           name="promo_campaigns_percent_off_check"),
    )
    op.create_index("ix_promo_campaigns_window", "promo_campaigns", ["status", "starts_at", "ends_at"])

    # --- 5. referrals ----------------------------------------------------------
    op.add_column("affiliate_referrals", sa.Column("terms_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_affiliate_referrals_terms", "affiliate_referrals", "affiliate_terms",
                          ["terms_id"], ["id"], ondelete="RESTRICT")
    op.add_column("affiliate_referrals", sa.Column("offer_type", sa.Text(), nullable=True))
    op.add_column("affiliate_referrals", sa.Column("campaign_id", PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_affiliate_referrals_campaign", "affiliate_referrals", "promo_campaigns",
                          ["campaign_id"], ["id"], ondelete="RESTRICT")
    op.add_column("affiliate_referrals", sa.Column("tier", sa.Text(), nullable=True))
    op.add_column("affiliate_referrals", sa.Column("billing_interval", sa.Text(), nullable=True))
    op.add_column("affiliate_referrals", sa.Column("list_price_cents", sa.Integer(), nullable=True))
    op.add_column("affiliate_referrals", sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("affiliate_referrals", sa.Column("first_paid_at", _TS, nullable=True))
    op.add_column("affiliate_referrals", sa.Column("year_anchor_at", _TS, nullable=True))
    op.add_column("affiliate_referrals", sa.Column("ended_at", _TS, nullable=True))
    op.add_column("affiliate_referrals", sa.Column("prior_referral_id", PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_affiliate_referrals_prior", "affiliate_referrals", "affiliate_referrals",
                          ["prior_referral_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("affiliate_referrals_offer_type_check", "affiliate_referrals",
                               "offer_type IS NULL OR offer_type IN ('regular','promo')")
    op.create_check_constraint("affiliate_referrals_billing_interval_check", "affiliate_referrals",
                               "billing_interval IS NULL OR billing_interval IN ('month','year')")
    op.create_check_constraint("affiliate_referrals_source_check", "affiliate_referrals",
                               "source IN ('checkout','promo_code','signup','return')")

    # --- 6. commission ledger ----------------------------------------------------
    op.create_table(
        "affiliate_commission_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("affiliate_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("referral_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("affiliate_referrals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("stripe_invoice_id", sa.Text(), nullable=True),
        sa.Column("stripe_reversal_id", sa.Text(), nullable=True),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column("stripe_subscription_id", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'usd'")),
        sa.Column("billing_interval", sa.Text(), nullable=True),
        sa.Column("service_period_start", _TS, nullable=True),
        sa.Column("event_at", _TS, nullable=True),
        sa.Column("year_number", sa.Integer(), nullable=True),
        sa.Column("net_paid_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("basis_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rate_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("amount", sa.Numeric(14, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("payable_month", sa.Date(), nullable=True),
        sa.Column("payout_id", sa.BigInteger(),
                  sa.ForeignKey("affiliate_payouts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("affiliate_id", "source_id", name="uq_affiliate_commission_line_source"),
        sa.CheckConstraint("kind IN ('first_year','promo','renewal','lapsed','refund','dispute')",
                           name="affiliate_commission_lines_kind_check"),
        sa.CheckConstraint("state IN ('pending','paid','held','lapsed','void')",
                           name="affiliate_commission_lines_state_check"),
    )
    op.create_index("ix_affiliate_commission_lines_payable", "affiliate_commission_lines",
                    ["affiliate_id", "payable_month", "currency"])
    op.create_index("ix_affiliate_commission_lines_period", "affiliate_commission_lines",
                    ["affiliate_id", "period_month"])
    op.create_index("ix_affiliate_commission_lines_invoice", "affiliate_commission_lines",
                    ["stripe_invoice_id"])


def downgrade() -> None:
    # Schema only: the v1 signatures archived in audit_log are not restored and
    # partners paused for re-signature stay paused.
    op.drop_table("affiliate_commission_lines")
    for name in ("affiliate_referrals_source_check", "affiliate_referrals_billing_interval_check",
                 "affiliate_referrals_offer_type_check"):
        op.drop_constraint(name, "affiliate_referrals", type_="check")
    for name in ("fk_affiliate_referrals_prior", "fk_affiliate_referrals_campaign",
                 "fk_affiliate_referrals_terms"):
        op.drop_constraint(name, "affiliate_referrals", type_="foreignkey")
    for col in ("prior_referral_id", "ended_at", "year_anchor_at", "first_paid_at", "discount_pct",
                "list_price_cents", "billing_interval", "tier", "campaign_id", "offer_type", "terms_id"):
        op.drop_column("affiliate_referrals", col)
    op.drop_table("promo_campaigns")
    op.drop_table("affiliate_discount_changes")
    op.drop_constraint("fk_affiliates_terms", "affiliates", type_="foreignkey")
    for col in ("termination_cause", "terminated_at", "terminated_for_cause",
                "discount_changed_at", "terms_id"):
        op.drop_column("affiliates", col)
    op.drop_table("affiliate_terms")
