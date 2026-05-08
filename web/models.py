"""
TW2 web tier - SQLAlchemy models.
Mirror of the schema defined in Postgres (see schema_version table).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Text, Boolean, TIMESTAMP, BigInteger, ForeignKey, Index,
    CheckConstraint, create_engine, JSON,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.sql import func

import sys
sys.path.insert(0, '/home/flask')
import config

Base = declarative_base()


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
    # api_key: legacy plaintext column. Kept populated during the
    # transition window so the appserver can fall back while it is
    # being switched over to api_key_hash. Will be NULLed out in a
    # follow-up migration once the appserver is fully on api_key_hash.
    api_key                     = Column(Text, unique=True)
    # api_key_hash: HMAC-SHA256(api_key, API_KEY_HMAC_SECRET). New
    # canonical lookup column (see migration 4c2f28489e2b and
    # /home/flask/web/db_admin.py).
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
