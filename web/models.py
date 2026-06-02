"""
TW2 web tier - SQLAlchemy models.
Mirror of the schema defined in Postgres (see schema_version table).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Text, Boolean, TIMESTAMP, BigInteger, ForeignKey, Index,
    CheckConstraint, create_engine, JSON, text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.sql import func

import sys
sys.path.insert(0, '/home/flask')
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
    # api_key_hash: HMAC-SHA256(api_key, API_KEY_HMAC_SECRET). The ONLY
    # server-side material for service-account auth. The plaintext
    # api_key column was dropped in alembic 5a3c1e2f4d6b; if a caller
    # loses their key, issue a fresh one and overwrite this hash.
    api_key_hash                = Column(Text)
    trial_ends_at               = Column(TIMESTAMP(timezone=True))
    created_at                  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at                  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_login_at               = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        # Mirrors the DB-side constraint added in migration 1940d1f63473.
        # Keep this in sync with the migration's CHECK definition.
        CheckConstraint(
            "tier IN ('explorer','analyst','strategist','canceled')",
            name="users_tier_check",
        ),
    )

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
            "stripe_subscription_status": self.stripe_subscription_status,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
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
