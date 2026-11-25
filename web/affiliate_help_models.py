"""Tables of the partner help assistant (TW-TASK-0039 package A).

Kept out of models.py so the assistant stays one self-contained unit;
models.py imports this module at its end so the tables are on Base.metadata
wherever the models are loaded (app, Alembic, tests).
Migration: migrations/versions/a9c1e5f7b3d2_affiliate_help_assistant.py.
"""
from sqlalchemy import BigInteger, Column, ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.sql import func

from models import Base

HELP_ROLES = ("partner", "assistant", "team")
ESCALATION_STATUSES = ("open", "answered", "dismissed")
KB_SCOPES = ("general", "partner")
KB_STATUSES = ("active", "retired")
KB_SOURCES = ("manual", "escalation")


class AffiliateHelpEscalation(Base):
    """A partner question the assistant could not answer; the owner answers
    it on the admin page or by replying to the notification email."""
    __tablename__ = "affiliate_help_escalations"
    id           = Column(BigInteger, primary_key=True)
    affiliate_id = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False)
    question     = Column(Text, nullable=False)
    context      = Column(JSONB)            # [{"role","body","at"}] recent chat, this partner only
    reason       = Column(Text)             # why the assistant could not answer
    status       = Column(Text, nullable=False, server_default="open")
    answer       = Column(Text)
    answered_by  = Column(Text)             # "admin:<email>" | "email:<from address>"
    answered_via = Column(Text)             # 'admin' | 'email'
    answered_at  = Column(TIMESTAMP(timezone=True))
    notified_at  = Column(TIMESTAMP(timezone=True))   # owner email accepted by Resend
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        Index("ix_affiliate_help_escalations_affiliate", "affiliate_id", "created_at"),
        Index("ix_affiliate_help_escalations_status", "status", "created_at"),
    )


class AffiliateHelpMessage(Base):
    """The conversation log: one row per chat bubble. Scoped to one partner."""
    __tablename__ = "affiliate_help_messages"
    id            = Column(BigInteger, primary_key=True)
    affiliate_id  = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False)
    role          = Column(Text, nullable=False)       # HELP_ROLES
    body          = Column(Text, nullable=False)
    outcome       = Column(Text)                       # assistant rows: answered | needs_team | off_topic | error | limit
    escalation_id = Column(BigInteger, ForeignKey("affiliate_help_escalations.id", ondelete="SET NULL"))
    read_at       = Column(TIMESTAMP(timezone=True))   # team rows: when the partner saw it
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        Index("ix_affiliate_help_messages_affiliate", "affiliate_id", "created_at"),
    )


class AffiliateHelpKb(Base):
    """Admin-curated knowledge base. scope='partner' entries are used only
    for affiliate_id; scope='general' entries are used for every partner."""
    __tablename__ = "affiliate_help_kb"
    id                = Column(BigInteger, primary_key=True)
    question          = Column(Text, nullable=False)
    answer            = Column(Text, nullable=False)
    source            = Column(Text, nullable=False, server_default="manual")
    scope             = Column(Text, nullable=False, server_default="general")
    status            = Column(Text, nullable=False, server_default="active")
    affiliate_id      = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="CASCADE"))
    escalation_id     = Column(BigInteger, ForeignKey("affiliate_help_escalations.id", ondelete="SET NULL"))
    # model-proposed generalised version, waiting for one-click approval
    proposed_question = Column(Text)
    proposed_answer   = Column(Text)
    updated_by        = Column(Text)
    created_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        Index("ix_affiliate_help_kb_lookup", "status", "scope", "affiliate_id"),
    )
