"""
TW2 web tier - SQLAlchemy models.
Mirror of the schema defined in Postgres (see schema_version table).
"""
from datetime import datetime
from pathlib import Path
from sqlalchemy import (
    Column, Text, Boolean, TIMESTAMP, BigInteger, Integer, ForeignKey, Index,
    CheckConstraint, UniqueConstraint, Date, Numeric, create_engine, JSON,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.sql import func

import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
import config

Base = declarative_base()


# Canonical list of role strings that may appear in `users.roles`. The dict is
# the single source of truth: the Flask-Admin user form renders this as help
# text and rejects unknown role strings on save (web/app.py UserAdmin). When
# you add or rename a role, edit ONLY this dict — the admin UI updates
# automatically. The role names here must match the strings checked in code
# (e.g. ReportsDashboard.js `userRoles.includes('newsroom_author')`, app.py
# `'super_admin' in roles`).
ROLES = {
    "super_admin": "Full admin access — Flask-Admin tooling, user management, audit log.",
    "user":        "Standard authenticated user. Default role for every account.",
    "newsroom_author": "Can create, edit, and publish SMN articles from Portfolio Manager.",
    "service_account": "Non-human internal service account; not for interactive sign-in.",
}


class User(Base):
    __tablename__ = "users"
    id                          = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    workos_user_id              = Column(Text, unique=True)
    email                       = Column(Text, unique=True, nullable=False)
    email_verified              = Column(Boolean, default=False)
    first_name                  = Column(Text)
    last_name                   = Column(Text)
    legacy_phpass_hash          = Column(Text)
    roles                       = Column(JSONB, default=lambda: ["user"])
    tier                        = Column(Text, default="explorer")
    legacy_wp_level             = Column(Text)
    stripe_customer_id          = Column(Text, unique=True)
    stripe_subscription_id      = Column(Text)
    stripe_subscription_status  = Column(Text)
    # Explicit developer-API subscription tier (dev/pro/business), SEPARATE from the web
    # `tier`. NULL = inherit from the web tier (apiserver.tiers.api_tier_from_user:
    # explorer->free, analyst->dev, strategist->pro). Written ONLY by the product_line=api
    # Stripe path; never clobbers the web tier. DB column added additively by
    # apiserver/schema.sql (ADD COLUMN IF NOT EXISTS api_tier).
    api_tier                    = Column(Text)
    # The developer-API product line has its own Stripe subscription identity.
    # Keeping it separate is what makes out-of-order API cancellations safe:
    # an old API event can never clear a newer API plan or the web/EOD plan.
    api_stripe_subscription_id     = Column(Text)
    api_stripe_subscription_status = Column(Text)
    # api_key_hash: HMAC-SHA256(api_key, API_KEY_HMAC_SECRET). The ONLY
    # server-side material for service-account auth. The plaintext
    # api_key column was dropped in alembic 5a3c1e2f4d6b; if a caller
    # loses their key, issue a fresh one and overwrite this hash.
    api_key_hash                = Column(Text)
    trial_ends_at               = Column(TIMESTAMP(timezone=True))
    # reverse_trial_ends_at: end of the 7-day REVERSE TRIAL (full Strategist
    # experience for new free signups). DISTINCT from trial_ends_at above
    # (admin-granted paid trials, swept by web/expire_trials.py): the reverse
    # trial never mutates tier - the row stays 'explorer' and the elevation
    # happens at token-mint time (web/app.py effective_tier), so expiry is
    # implicit and needs no cron. Set on the lazy_create_user CREATE path
    # and by ops/grant_reverse_trial.py for existing explorers.
    reverse_trial_ends_at       = Column(TIMESTAMP(timezone=True))
    # navigator_mcp_first_connect_at: stamped ONCE (idempotently) by the gateway on a
    # Navigator's first MCP/OAuth connect (apiserver/db.py arm_navigator_teaser_if_null),
    # anchoring the one-time 7-day first-connect teaser (Analyst scope in chat). The web
    # tier only READS it (account() in-chat-access card; never arms it). Column already
    # exists in Postgres via apiserver/schema.sql - this is an additive mapping, NO migration.
    navigator_mcp_first_connect_at = Column(TIMESTAMP(timezone=True))
    # first_ai_score_viewed_at: stamped ONCE (idempotently), the first time a logged-in
    # user with AI-score access (Analyst+, config.ml_score_access_levels) actually renders
    # an AI score in the wave-viewer. Written by POST /api/activation/ai-score-viewed
    # (web/app.py) in the SAME handler that appends the onboarding_events row
    # (event_type='ai_score_viewed') and fires the GA4 ai_score_viewed event (web/ga4_mp.py).
    # GTM playbook CARD W1.4 / strategy §2 persistence rule: the day-2/day-7 trial-activation
    # emails read THIS column, never GA4. Migration b3f6a8c1d9e2.
    first_ai_score_viewed_at    = Column(TIMESTAMP(timezone=True))
    created_at                  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at                  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_login_at               = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        # Mirrors the DB-side constraint added in migration 1940d1f63473 and
        # widened to include 'navigator' in migration a1f4d2c9e7b3.
        # Keep this in sync with the migration's CHECK definition.
        CheckConstraint(
            "tier IN ('explorer','navigator','analyst','strategist','canceled')",
            name="users_tier_check",
        ),
    )

    def __str__(self):
        # Flask-Admin renders related objects via str() (AffiliateAdmin's
        # "Portal login" column + its ajax picker). Without this it shows the
        # raw object repr and blows up the list-table layout.
        return self.email or str(self.id)

    def to_dict(self):
        return {
            "id": str(self.id),
            "workos_user_id": self.workos_user_id,
            "email": self.email,
            "email_verified": self.email_verified,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "roles": self.roles or ["user"],
            "tier": self.tier,
            "api_tier": self.api_tier,
            "api_stripe_subscription_status": self.api_stripe_subscription_status,
            "stripe_subscription_status": self.stripe_subscription_status,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "reverse_trial_ends_at": self.reverse_trial_ends_at.isoformat() if self.reverse_trial_ends_at else None,
        }


class AuditLog(Base):
    __tablename__ = "audit_log"
    id              = Column(BigInteger, primary_key=True)
    actor_user_id   = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    actor_label     = Column(Text)
    action          = Column(Text, nullable=False)
    target_user_id  = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    details         = Column(JSONB)
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now())


class StripeEvent(Base):
    __tablename__ = "stripe_events"
    id                 = Column(BigInteger, primary_key=True)
    stripe_event_id    = Column(Text, unique=True, nullable=False)
    event_type         = Column(Text, nullable=False)
    user_id            = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    payload            = Column(JSONB)
    received_at        = Column(TIMESTAMP(timezone=True), server_default=func.now())
    processed_at       = Column(TIMESTAMP(timezone=True))
    processing_error   = Column(Text)


class StripeCheckoutClaim(Base):
    """Durable single-flight state for subscription Checkout creation.

    One row per user and product line serializes browser replays and concurrent
    Gunicorn workers.  ``request_payload`` is the exact, JSON-safe kwargs sent
    to Stripe; persisting it with the idempotency key lets a later request retry
    an unknown network outcome without changing parameters or minting a second
    subscription.
    """
    __tablename__ = "stripe_checkout_claims"
    user_id             = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_line        = Column(Text, primary_key=True)
    request_fingerprint = Column(Text, nullable=False)
    request_payload     = Column(JSONB, nullable=False)
    idempotency_key     = Column(Text, nullable=False, unique=True)
    lease_token         = Column(PG_UUID(as_uuid=True))
    lease_expires_at    = Column(TIMESTAMP(timezone=True))
    stripe_session_id   = Column(Text, unique=True)
    stripe_session_url  = Column(Text)
    expires_at          = Column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at         = Column(TIMESTAMP(timezone=True))
    created_at          = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at          = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "product_line IN ('eod','api')",
            name="stripe_checkout_claims_product_line_check",
        ),
        CheckConstraint(
            "(stripe_session_id IS NULL) = (stripe_session_url IS NULL)",
            name="stripe_checkout_claims_session_pair_check",
        ),
    )


class CouponUsed(Base):
    __tablename__ = "coupons_used"
    id                = Column(BigInteger, primary_key=True)
    user_id           = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_coupon_id  = Column(Text, nullable=False)
    redeemed_at       = Column(TIMESTAMP(timezone=True), server_default=func.now())
    metadata_         = Column("metadata", JSONB)


# Allowed values are mirrored in the DB as CHECK constraints (see migration
# 7a5c3b9d12ef). The strings here ARE storage IDs - never rename, only add.
# UI labels live in the form template; values stored never change.
SUPPORT_TICKET_TOPICS = (
    "bug", "feature", "billing", "account",
    "data", "institutional", "press", "other",
)
SUPPORT_TICKET_STATUSES = ("open", "pending_customer", "resolved", "spam")


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id              = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # Monotonic sequence-backed counter; the human-facing public_id is derived
    # from this + year. Sequence lives in Postgres (support_tickets_number_seq).
    ticket_number   = Column(BigInteger, nullable=False, unique=True,
                             server_default=sa_text("nextval('support_tickets_number_seq')"))
    # public_id is set by a BEFORE-INSERT trigger from ticket_number + the
    # year of created_at, format TW-YYYY-NNNNN. Year reflects when the ticket
    # was opened; numbers are globally monotonic, not per-year. The trigger
    # (not a GENERATED column) because to_char(timestamptz, ...) is STABLE
    # not IMMUTABLE in PG and so isn't legal in a generated expression.
    # Trigger source lives in migration 7a5c3b9d12ef.
    public_id       = Column(Text, unique=True, nullable=False)
    user_id         = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email           = Column(Text, nullable=False)
    name            = Column(Text, nullable=False)
    topic           = Column(Text, nullable=False)
    body            = Column(Text, nullable=False)
    status          = Column(Text, nullable=False, server_default=sa_text("'open'"))
    # Snapshot of customer context (tier, stripe state, last_login) captured at
    # submit time so the notification email - and any future audit - reflects
    # what was true when the user wrote in, not what's true now.
    enrichment      = Column(JSONB)
    user_agent      = Column(Text)
    ip_hash         = Column(Text)  # sha256(ip + per-env salt); NEVER store raw IP
    created_at      = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    resolved_at     = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "topic IN ('bug','feature','billing','account','data','institutional','press','other')",
            name="support_tickets_topic_check",
        ),
        CheckConstraint(
            "status IN ('open','pending_customer','resolved','spam')",
            name="support_tickets_status_check",
        ),
        Index("ix_support_tickets_created_at", "created_at"),
        Index("ix_support_tickets_status", "status"),
        Index("ix_support_tickets_email", "email"),
    )


class EmailLead(Base):
    """Top-of-funnel email capture - the free personalized seasonal report
    (web/seasonal_report.py + the /api/lead-report route). The DB row is the
    canonical record (CAN-SPAM consent proof); the emailed report is best-effort
    and built/sent in a background thread. NO public_id / sequence / trigger -
    this is a lightweight lead, not a ticketed support case.
    """
    __tablename__ = "email_leads"
    id          = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # NULL for anonymous (funnel) captures; set for logged-in users so their quota is
    # counted by account (IP-proof) and scales with tier. SET NULL keeps leads on delete.
    user_id     = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email       = Column(Text, nullable=False)
    # uppercased symbols the visitor asked about (stable storage = a JSON list, mirrors enrichment).
    tickers     = Column(JSONB)
    source      = Column(Text)   # stable storage-ID string, e.g. 'home_free_report'
    # DOUBLE OPT-IN lifecycle: pending_confirm = confirm email sent, awaiting the click;
    # sent = report emailed after confirm; failed = build/send error; spam = rate-limited;
    # expired = confirm link aged out (7d) unclicked.
    status        = Column(Text, nullable=False, server_default=sa_text("'pending_confirm'"))
    confirm_token = Column(Text, unique=True)        # opaque URL-safe token in the confirm link
    confirmed_at  = Column(TIMESTAMP(timezone=True))  # set when the user clicks the confirm link
    # snapshot captured at send: {covered:[...], not_covered:[...], as_of:'YYYY-MM-DD'}.
    detail      = Column(JSONB)
    user_agent  = Column(Text)
    ip_hash     = Column(Text)   # sha256(ip + per-env salt); NEVER store raw IP
    created_at  = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    sent_at     = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_confirm','sent','failed','spam','expired')",
            name="email_leads_status_check",
        ),
        Index("ix_email_leads_created_at", "created_at"),
        Index("ix_email_leads_email", "email"),
        Index("ix_email_leads_user_id", "user_id"),
    )


class EmailOptout(Base):
    """Suppression list - the SINGLE source of truth for unsubscribes across BOTH
    Resend (the report sends) and MailerLite. Any send to a suppressed email is
    skipped. Populated by the /unsubscribe endpoint (the in-email link + the Gmail
    one-click POST) and by the MailerLite unsubscribe webhook, so an opt-out from
    either system stops both."""
    __tablename__ = "email_optouts"
    email           = Column(Text, primary_key=True)   # lowercased
    unsubscribed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    source          = Column(Text)   # 'link' | 'one_click' | 'mailerlite_webhook'


# ---------------------------------------------------------------------------
# Affiliate program (manual promo-code model). See web/affiliate_service.py and
# the AffiliateAdmin / AffiliatePayoutAdmin Flask-Admin views in web/app.py.
# The CHECK values below are STORAGE IDs, mirrored in migration af1c0de2b3a4 -
# never rename, only add.
# ---------------------------------------------------------------------------
COMMISSION_MODELS = ("recurring", "first_payment", "duration_12mo")
AFFILIATE_STATUSES = ("active", "paused", "terminated")
PAYOUT_STATUSES = ("pending", "paid", "void")


class Affiliate(Base):
    __tablename__ = "affiliates"
    id            = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # code: the Stripe promotion-code string the affiliate shares (uppercase
    # canonical). IMMUTABLE once stripe_coupon_id is set - Stripe coupons can't
    # be edited; the AffiliateAdmin enforces this.
    code          = Column(Text, nullable=False, unique=True)
    name          = Column(Text, nullable=False)
    email         = Column(Text, nullable=False)  # required - also the self-referral guard
    payout_method = Column(Text)  # 'paypal' | 'wise'
    payout_email  = Column(Text)
    discount_pct  = Column(Numeric(5, 2), nullable=False)   # audience discount, 20.00 = 20% (DEFAULT/fallback)
    commission_pct = Column(Numeric(5, 2), nullable=False)  # affiliate keeps, 30.00 = 30% (DEFAULT/fallback)
    # --- interval-split: the form presents two pairs, Monthly + Annual. The flat
    # discount_pct/commission_pct above ARE the ANNUAL terms (the default, and
    # what backs the promo code); the *_monthly columns are the optional MONTHLY
    # override (NULL => monthly is the same as annual). A "split" affiliate just
    # carries a monthly override + its own coupon. Discounts are immutable
    # post-create (coupon-tied); commissions are editable. See affiliate_service
    # .effective_discount_pct / effective_commission_pct / effective_coupon_id /
    # provision_interval_overrides.
    discount_pct_monthly     = Column(Numeric(5, 2))   # monthly discount override (NULL = same as annual)
    commission_pct_monthly   = Column(Numeric(5, 2))   # monthly commission override (NULL = same as annual)
    stripe_coupon_id_monthly = Column(Text)            # monthly override coupon, applied by id at checkout
    # --- co-branded landing page (/join/<code>): operator-entered, all optional.
    page_display_name = Column(Text)   # name shown on the page (personal or business); falls back to `name`
    page_logo         = Column(Text)   # stored filename under /assets/affiliate-logos/ (brand mark; rounded chip)
    page_photo        = Column(Text)   # stored filename under /assets/affiliate-logos/ (headshot; circular avatar)
    page_note         = Column(Text)   # short first-person note to their audience (<=280, plain text)
    page_signoff      = Column(Text)   # attribution line under the note, e.g. "Sarah, your options coach" (<=60)
    commission_model = Column(Text, nullable=False, server_default=sa_text("'recurring'"))
    stripe_coupon_id = Column(Text, unique=True)
    stripe_promotion_code_id = Column(Text)
    # Default 'paused' (not 'active'): an affiliate is active only once signed
    # (the activation gate). AffiliateAdmin forces paused on create; signing flips
    # paused->active. A non-admin/raw insert therefore can't be active-and-unsigned.
    status        = Column(Text, nullable=False, server_default=sa_text("'paused'"))
    notes         = Column(Text)
    # --- affiliate agreement e-signature (in-house clickwrap; see
    # web/affiliate_agreement.py + the /affiliate/sign/<token> route). An
    # affiliate is created 'paused' and only flips to 'active' once signed, so
    # the referral code can't be used before they've agreed (_resolve_affiliate_promo
    # requires status == 'active'). agreement_token_version is bumped to
    # invalidate an already-issued signing link ("regenerate" admin action).
    agreement_version           = Column(Text)
    agreement_signed_name       = Column(Text)
    agreement_signed_at         = Column(TIMESTAMP(timezone=True))
    agreement_signed_ip         = Column(Text)
    agreement_signed_user_agent = Column(Text)
    agreement_snapshot          = Column(Text)   # immutable copy of the exact terms signed
    # Per-affiliate rider rendered as "Exhibit B - Additional Terms" (operator-
    # authored markdown). The shared body (Sections 1-15) is identical for every
    # affiliate; ONLY this varies. Frozen into agreement_snapshot on signing.
    agreement_addendum          = Column(Text)
    agreement_token_version     = Column(Integer, nullable=False, server_default=sa_text("0"))
    # user_id: the affiliate's DASHBOARD LOGIN (users row), migration e7a1b2c9d4f5.
    # NULL = not yet linked. The portal (/account/affiliate) auto-links on first
    # visit by exact case-insensitive email match; operator can set it manually
    # in AffiliateAdmin. Access is derived from this FK - deliberately NOT a
    # models.ROLES role (one source of truth). UNIQUE both ways (1:1).
    user_id       = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(r"code ~ '^[A-Z0-9_-]{2,64}$'", name="affiliates_code_charset_check"),
        CheckConstraint(
            "commission_model IN ('recurring','first_payment','duration_12mo')",
            name="affiliates_commission_model_check"),
        CheckConstraint("status IN ('active','paused','terminated')", name="affiliates_status_check"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="affiliates_discount_pct_check"),
        CheckConstraint("commission_pct >= 0 AND commission_pct <= 100", name="affiliates_commission_pct_check"),
        CheckConstraint("discount_pct_monthly IS NULL OR (discount_pct_monthly >= 0 AND discount_pct_monthly <= 100)", name="affiliates_discount_pct_monthly_check"),
        CheckConstraint("commission_pct_monthly IS NULL OR (commission_pct_monthly >= 0 AND commission_pct_monthly <= 100)", name="affiliates_commission_pct_monthly_check"),
        CheckConstraint("page_note IS NULL OR char_length(page_note) <= 280", name="affiliates_page_note_len_check"),
        CheckConstraint("page_signoff IS NULL OR char_length(page_signoff) <= 60", name="affiliates_page_signoff_len_check"),
        CheckConstraint("agreement_addendum IS NULL OR char_length(agreement_addendum) <= 20000", name="affiliates_agreement_addendum_len_check"),
    )

    def __str__(self):
        return f"{self.code} ({self.name})"


class AffiliatePayout(Base):
    __tablename__ = "affiliate_payouts"
    id            = Column(BigInteger, primary_key=True)
    affiliate_id  = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False)
    period_start  = Column(Date, nullable=False)
    period_end    = Column(Date, nullable=False)
    currency      = Column(Text, nullable=False, server_default=sa_text("'usd'"))
    gross_revenue = Column(Numeric(12, 2), nullable=False, server_default=sa_text("0"))
    commission_amount = Column(Numeric(12, 2), nullable=False, server_default=sa_text("0"))
    status        = Column(Text, nullable=False, server_default=sa_text("'pending'"))
    # locked: set true when an operator hand-edits a pending row's commission
    # (e.g. nets a refund). upsert_month skips locked rows so re-compute can't
    # clobber the adjustment.
    locked        = Column(Boolean, nullable=False, server_default=sa_text("false"))
    computed_at   = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    paid_at       = Column(TIMESTAMP(timezone=True))
    external_ref  = Column(Text)  # PayPal/Wise transaction id once paid
    detail        = Column(JSONB)  # {"lines": [...per-invoice...]}
    affiliate     = relationship("Affiliate")

    __table_args__ = (
        CheckConstraint("status IN ('pending','paid','void')", name="affiliate_payouts_status_check"),
        UniqueConstraint("affiliate_id", "period_start", "currency", name="uq_affiliate_payout_period"),
        Index("ix_affiliate_payouts_status", "status"),
    )

    def __str__(self):
        return f"{self.affiliate_id} {self.period_start} {self.commission_amount} {self.currency}"


class AffiliateReferral(Base):
    """Persisted customer/subscription -> affiliate attribution, written from the
    subscription webhook when a referred checkout completes (the affiliate id is
    carried in the Stripe subscription metadata, stamped at checkout). Commission
    attribution joins to THIS table first - the coupon is only corroboration - so
    a recurring affiliate keeps earning after the 12-month discount coupon falls
    off the invoice, and coupon expiry/deletion can't orphan referral history."""
    __tablename__ = "affiliate_referrals"
    id            = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    affiliate_id  = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False)
    stripe_customer_id     = Column(Text)
    stripe_subscription_id = Column(Text, nullable=False, unique=True)  # one referral per subscription
    referral_code = Column(Text)   # snapshot of the code used at checkout
    source        = Column(Text, nullable=False, server_default=sa_text("'checkout'"))
    attributed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    affiliate     = relationship("Affiliate")

    __table_args__ = (
        Index("ix_affiliate_referrals_customer", "stripe_customer_id"),
        Index("ix_affiliate_referrals_affiliate", "affiliate_id"),
    )

    def __str__(self):
        return f"{self.stripe_subscription_id} -> {self.affiliate_id}"


# ---------------------------------------------------------------------------
# SMN expert module (optional, operator-invited; docs/AFFILIATE_DASHBOARD_SPEC.md
# section 4.3). Status strings are STORAGE IDs - never rename, only add. CHECK
# values mirror migrations f8c2d3e0a5b6 / a9d3e4f1b6c7.
# ---------------------------------------------------------------------------
SMN_PROFILE_STATUSES = ("invited", "active", "paused")
EXPERT_TAKE_STATUSES = ("draft", "submitted", "approved", "published", "rejected", "retracted")


class AffiliateSmnProfile(Base):
    """1:1 opt-in row: exists only once the operator invites the affiliate to
    the SMN expert program. invited -> active happens ONLY via the portal's
    click-accept of docs/SMN_CONTRIBUTOR_TERMS.md (audited: version/ts/ip/ua +
    immutable snapshot, mirroring the main agreement). slug is the expert's
    public id on SMN (hub page) - IMMUTABLE once published_at is set."""
    __tablename__ = "affiliate_smn_profiles"
    affiliate_id  = Column(PG_UUID(as_uuid=True),
                           ForeignKey("affiliates.id", ondelete="CASCADE"), primary_key=True)
    status        = Column(Text, nullable=False, server_default=sa_text("'invited'"))
    slug          = Column(Text, unique=True)
    bio_md        = Column(Text)
    credentials   = Column(Text)
    links         = Column(JSONB)   # [{"label": ..., "url": "https://..."}] - validated in the portal
    disclosure_md = Column(Text)
    terms_version             = Column(Text)
    terms_accepted_at         = Column(TIMESTAMP(timezone=True))
    terms_accepted_ip         = Column(Text)
    terms_accepted_user_agent = Column(Text)
    terms_snapshot            = Column(Text)   # immutable copy of the exact terms accepted
    scorecard_enabled = Column(Boolean, nullable=False, server_default=sa_text("true"))
    published_at  = Column(TIMESTAMP(timezone=True))
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    affiliate     = relationship("Affiliate")

    __table_args__ = (
        CheckConstraint("status IN ('invited','active','paused')",
                        name="affiliate_smn_profiles_status_check"),
        CheckConstraint(r"slug IS NULL OR slug ~ '^[a-z0-9-]{2,64}$'",
                        name="affiliate_smn_profiles_slug_charset_check"),
        CheckConstraint("bio_md IS NULL OR char_length(bio_md) <= 4000",
                        name="affiliate_smn_profiles_bio_len_check"),
        CheckConstraint("credentials IS NULL OR char_length(credentials) <= 200",
                        name="affiliate_smn_profiles_credentials_len_check"),
        CheckConstraint("disclosure_md IS NULL OR char_length(disclosure_md) <= 500",
                        name="affiliate_smn_profiles_disclosure_len_check"),
        Index("ix_affiliate_smn_profiles_status", "status"),
        Index("ix_affiliate_smn_profiles_updated", "updated_at"),
    )

    def __str__(self):
        return f"smn:{self.slug or self.affiliate_id} ({self.status})"


class ExpertTake(Base):
    """One expert commentary on one SMN article. Lifecycle: draft -> submitted
    -> approved -> published (+ rejected, retracted). Operator review is
    MANDATORY before publish (ExpertTakeAdmin). rendered_html is stamped at
    approval by web/expert_takes_service.py (markdown -> bleach; the single
    sanitation authority) and is what /internal/expert_takes serves to the SMN
    box. declared_call = the house-scored directional thesis (Layer 1);
    execution_note/result = expert-reported options detail (Layer 2, labeled,
    never in the verified record)."""
    __tablename__ = "expert_takes"
    id            = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    affiliate_id  = Column(PG_UUID(as_uuid=True),
                           ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False)
    article_slug  = Column(Text, nullable=False)
    title         = Column(Text)
    body_md       = Column(Text, nullable=False)
    declared_call = Column(JSONB)   # {"symbol","direction","entry_date","exit_date"} or NULL
    status        = Column(Text, nullable=False, server_default=sa_text("'draft'"))
    review_note   = Column(Text)
    reviewed_by   = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    rendered_html = Column(Text)
    execution_note      = Column(Text)
    execution_result    = Column(Text)
    execution_result_at = Column(TIMESTAMP(timezone=True))
    published_at  = Column(TIMESTAMP(timezone=True))
    retracted_at  = Column(TIMESTAMP(timezone=True))
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    affiliate     = relationship("Affiliate")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','submitted','approved','published','rejected','retracted')",
            name="expert_takes_status_check"),
        CheckConstraint(r"article_slug ~ '^[a-zA-Z0-9_-]{1,200}$'",
                        name="expert_takes_article_slug_charset_check"),
        CheckConstraint("title IS NULL OR char_length(title) <= 120",
                        name="expert_takes_title_len_check"),
        CheckConstraint("char_length(body_md) <= 8000",
                        name="expert_takes_body_len_check"),
        CheckConstraint("execution_note IS NULL OR char_length(execution_note) <= 500",
                        name="expert_takes_execution_note_len_check"),
        CheckConstraint("execution_result IS NULL OR char_length(execution_result) <= 300",
                        name="expert_takes_execution_result_len_check"),
        Index("ix_expert_takes_affiliate", "affiliate_id"),
        Index("ix_expert_takes_status", "status"),
        Index("ix_expert_takes_article", "article_slug"),
        Index("ix_expert_takes_updated", "updated_at"),
    )

    def __str__(self):
        return f"{self.article_slug} by {self.affiliate_id} ({self.status})"


# ---------------------------------------------------------------------------
# Standalone promo coupons (marketing discount codes, NO affiliate/commission).
# See web/promo_service.py + the PromoCouponAdmin Flask-Admin view. CHECK values
# mirror migration b2c0fee1d3a5 - never rename, only add.
# ---------------------------------------------------------------------------
PROMO_DISCOUNT_TYPES = ("percent", "amount")
PROMO_DURATIONS = ("once", "repeating", "forever")
PROMO_STATUSES = ("active", "archived")


class PromoCoupon(Base):
    __tablename__ = "promo_coupons"
    id            = Column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    code          = Column(Text, nullable=False, unique=True)   # the promo code string (uppercase); immutable once created
    name          = Column(Text)                                # internal label
    discount_type = Column(Text, nullable=False)                # 'percent' | 'amount'
    percent_off   = Column(Numeric(5, 2))                       # for percent (100 = free/comp)
    amount_off_cents = Column(Integer)                          # for amount
    currency      = Column(Text)                                # required for amount
    duration      = Column(Text, nullable=False, server_default=sa_text("'once'"))  # once|repeating|forever
    duration_in_months = Column(Integer)                        # for repeating
    max_redemptions = Column(Integer)                           # optional total cap (on the promo code)
    expires_at    = Column(TIMESTAMP(timezone=True))            # optional expiry (on the promo code)
    stripe_coupon_id = Column(Text, unique=True)
    stripe_promotion_code_id = Column(Text)
    status        = Column(Text, nullable=False, server_default=sa_text("'active'"))  # active|archived
    notes         = Column(Text)
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(r"code ~ '^[A-Z0-9_-]{2,64}$'", name="promo_coupons_code_charset_check"),
        CheckConstraint("discount_type IN ('percent','amount')", name="promo_coupons_discount_type_check"),
        CheckConstraint("duration IN ('once','repeating','forever')", name="promo_coupons_duration_check"),
        CheckConstraint("status IN ('active','archived')", name="promo_coupons_status_check"),
    )

    def __str__(self):
        if self.discount_type == "amount":
            disc = f"{(self.amount_off_cents or 0)/100:.2f} {(self.currency or '').upper()} off"
        else:
            disc = f"{self.percent_off}% off"
        return f"{self.code} ({disc})"


class MailerLiteLifecycleEvent(Base):
    """Durable outbox for MailerLite access/lifecycle reconciliation.

    Event-type and status strings are persistent storage IDs. Never rename an
    existing value; add a new value plus a migration if the state machine grows.
    The worker always derives the desired lifecycle group from the CURRENT User
    row, so delayed or out-of-order Stripe events converge instead of replaying
    stale group assignments.
    """
    __tablename__ = "mailerlite_lifecycle_events"
    id           = Column(BigInteger, primary_key=True)
    user_id      = Column(PG_UUID(as_uuid=True),
                          ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type   = Column(Text, nullable=False)  # reconcile | clear_paid
    dedupe_key   = Column(Text, nullable=False, unique=True)
    status       = Column(Text, nullable=False, server_default=sa_text("'pending'"))
    attempts     = Column(Integer, nullable=False, server_default=sa_text("0"))
    available_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    claimed_at   = Column(TIMESTAMP(timezone=True))
    processed_at = Column(TIMESTAMP(timezone=True))
    payload      = Column(JSONB)
    last_error   = Column(Text)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False,
                          server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('reconcile','clear_paid')",
            name="mailerlite_lifecycle_events_type_check",
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','suppressed','failed')",
            name="mailerlite_lifecycle_events_status_check",
        ),
        Index("ix_mailerlite_lifecycle_user_status", "user_id", "status"),
        Index(
            "ix_mailerlite_lifecycle_due", "available_at", "id",
            postgresql_where=sa_text("status IN ('pending','failed')"),
        ),
    )


class OnboardingEvent(Base):
    """Append-only trial-usage telemetry that powers the end-of-trial TRUST SIGNAL
    (recommend the MINIMUM tier that covers what the user actually did, so we can
    honestly say "you don't need Strategist"). Low-sensitivity: the market / symbol
    / horizon a trial user touched - never an order or PII. Written by
    POST /api/onboarding/event; aggregated by GET /api/onboarding/usage-summary."""
    __tablename__ = "onboarding_events"
    id          = Column(BigInteger, primary_key=True)
    user_id     = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type  = Column(Text, nullable=False)
    detail      = Column(JSONB)
    created_at  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_onboarding_events_user_id", "user_id"),
    )


# Engine + session factory - used app-wide
engine = create_engine(
    config.POSTGRES_DSN,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)
Session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False, future=True))


def db_session():
    return Session()


def write_audit(actor_user_id=None, actor_label=None, action=None, target_user_id=None, details=None):
    """Convenience helper for writing audit log entries."""
    s = Session()
    try:
        s.add(AuditLog(
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            action=action,
            target_user_id=target_user_id,
            details=details,
        ))
        s.commit()
    finally:
        s.close()
