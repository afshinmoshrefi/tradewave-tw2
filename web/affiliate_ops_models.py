"""Affiliate operations + growth tables (TW-TASK-0039 package C, migration
c0a1b2d3e4f5_affiliate_ops_growth). Kept in their own module so the package
adds no churn to web/models.py; they share models.Base, so importing this
module registers them on the same metadata.

Every string in the tuples below is a STORAGE ID - never rename, only add.
"""
from sqlalchemy import (
    BigInteger, CheckConstraint, Column, Date, ForeignKey, Index, Integer, Text,
    TIMESTAMP, UniqueConstraint, text as sa_text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models import Base

TAX_FORM_TYPES = ("w9", "w8ben", "w8bene")
TAX_FORM_STATUSES = ("received", "accepted", "rejected", "replaced")
CREATIVE_KINDS = ("banner", "logo", "email", "social")
CREATIVE_STATUSES = ("active", "archived")

_BIGPK = BigInteger().with_variant(Integer, "sqlite")


class AffiliateTaxForm(Base):
    """One uploaded tax form (W-9 / W-8BEN / W-8BEN-E PDF). The file itself is
    Fernet-encrypted on disk OUTSIDE the web root (config.TAX_FORM_DIR); this
    row holds only its random storage name, size and SHA-256. received ->
    accepted | rejected by an admin; a newer upload or acceptance marks the
    older row 'replaced'. storage_name is cleared when the file is deleted
    (rejected / replaced forms are not kept)."""
    __tablename__ = "affiliate_tax_forms"
    id            = Column(_BIGPK, primary_key=True)
    affiliate_id  = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="RESTRICT"), nullable=False)
    form_type     = Column(Text, nullable=False)
    status        = Column(Text, nullable=False, server_default=sa_text("'received'"))
    reject_reason = Column(Text)                 # shown to the partner
    storage_name  = Column(Text)                 # random file name under TAX_FORM_DIR; NULL once deleted
    original_filename = Column(Text)
    size_bytes    = Column(Integer, nullable=False, server_default=sa_text("0"))   # plaintext size
    sha256        = Column(Text)                 # of the plaintext PDF
    uploaded_by_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at   = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at   = Column(TIMESTAMP(timezone=True))
    reviewed_by   = Column(Text)                 # 'admin:<email>'
    affiliate     = relationship("Affiliate")

    __table_args__ = (
        CheckConstraint("form_type IN ('w9','w8ben','w8bene')", name="affiliate_tax_forms_form_type_check"),
        CheckConstraint("status IN ('received','accepted','rejected','replaced')",
                        name="affiliate_tax_forms_status_check"),
        Index("ix_affiliate_tax_forms_affiliate", "affiliate_id", "uploaded_at"),
        Index("ix_affiliate_tax_forms_status", "status"),
    )


class AffiliateSublink(Base):
    """A partner-created named sub-link (?code=ANNE&sub=youtube). `sub` is the
    slug in the URL (storage id, immutable); `label` is the partner's free
    text. campaign_id optionally ties the link to a company promotion so the
    Links page can total clicks and signups per campaign. A sub-link never
    changes who earns: it is a reporting tag on the partner's own traffic."""
    __tablename__ = "affiliate_sublinks"
    id            = Column(_BIGPK, primary_key=True)
    affiliate_id  = Column(PG_UUID(as_uuid=True), ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False)
    sub           = Column(Text, nullable=False)
    label         = Column(Text)
    campaign_id   = Column(PG_UUID(as_uuid=True), ForeignKey("promo_campaigns.id", ondelete="SET NULL"))
    archived_at   = Column(TIMESTAMP(timezone=True))
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("affiliate_id", "sub", name="uq_affiliate_sublink_sub"),
        CheckConstraint(r"sub ~ '^[a-z0-9][a-z0-9_-]{0,39}$'", name="affiliate_sublinks_sub_charset_check"),
        CheckConstraint("label IS NULL OR char_length(label) <= 80", name="affiliate_sublinks_label_len_check"),
    )


class AffiliateSublinkClick(Base):
    """Per-(sub-link, UTC day) visit counter; the partner's total stays in
    affiliate_clicks (a sub-link visit counts in both)."""
    __tablename__ = "affiliate_sublink_clicks"
    sublink_id    = Column(BigInteger().with_variant(Integer, "sqlite"),
                           ForeignKey("affiliate_sublinks.id", ondelete="CASCADE"), primary_key=True)
    day           = Column(Date, primary_key=True)
    clicks        = Column(Integer, nullable=False, server_default=sa_text("0"))


class AffiliateCreative(Base):
    """Creative library item, uploaded by an admin. banner / logo carry an
    image file (config.AFFILIATE_CREATIVE_DIR, a public asset folder so a
    partner can embed it); email / social carry `body` copy with the
    placeholders {link} {join_link} {code} {discount} {name}. campaign_id
    NULL = evergreen; otherwise shown to partners only while that campaign is
    live."""
    __tablename__ = "affiliate_creatives"
    id            = Column(_BIGPK, primary_key=True)
    kind          = Column(Text, nullable=False)
    title         = Column(Text, nullable=False)
    body          = Column(Text)
    file_name     = Column(Text)                 # stored name under AFFILIATE_CREATIVE_DIR
    original_filename = Column(Text)
    mime_type     = Column(Text)
    width         = Column(Integer)
    height        = Column(Integer)
    size_bytes    = Column(Integer)
    campaign_id   = Column(PG_UUID(as_uuid=True), ForeignKey("promo_campaigns.id", ondelete="SET NULL"))
    status        = Column(Text, nullable=False, server_default=sa_text("'active'"))
    sort_order    = Column(Integer, nullable=False, server_default=sa_text("0"))
    created_by    = Column(Text)
    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    campaign      = relationship("PromoCampaign")

    __table_args__ = (
        CheckConstraint("kind IN ('banner','logo','email','social')", name="affiliate_creatives_kind_check"),
        CheckConstraint("status IN ('active','archived')", name="affiliate_creatives_status_check"),
        CheckConstraint("char_length(title) <= 120", name="affiliate_creatives_title_len_check"),
        Index("ix_affiliate_creatives_status", "status", "kind"),
    )
