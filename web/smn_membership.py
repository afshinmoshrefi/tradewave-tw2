"""SMN enrollment and grants; deliberately never mutate TradeWave access."""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import or_, func
from models import User, SmnMembership, SmnGrant, SmnOffer, SmnSettings, AuditLog


class MembershipError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def now_utc():
    return datetime.now(timezone.utc)


def integer(value, name, minimum=0, maximum=2_000_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise MembershipError("invalid_" + name)
    return value


def validate_offer(data):
    if not isinstance(data, dict):
        raise MembershipError("invalid_offer")
    mode = data.get("mode")
    currency = data.get("currency", "usd")
    if mode not in ("free", "paid") or currency not in ("usd", "eur", "gbp", "cad", "aud", "jpy"):
        raise MembershipError("invalid_mode_or_currency")
    monthly = integer(data.get("monthly_amount", 0), "monthly_amount")
    trial = integer(data.get("trial_days", 0), "trial_days", maximum=365)
    annual_mode = data.get("annual_mode", "explicit")
    intervals = data.get("intervals", [])
    if not isinstance(intervals, list) or len(set(intervals)) != len(intervals) or any(x not in ("month", "year") for x in intervals):
        raise MembershipError("invalid_intervals")
    if annual_mode not in ("explicit", "discount"):
        raise MembershipError("invalid_annual_mode")
    bps = data.get("annual_discount_bps")
    if mode == "free":
        if monthly or data.get("annual_amount", 0) not in (0, None) or bps not in (0, None) or intervals or trial:
            raise MembershipError("free_offer_must_have_no_price_or_trial")
        annual, bps, annual_mode = 0, None, "explicit"
    elif annual_mode == "discount":
        bps = integer(bps, "annual_discount_bps", maximum=9999)
        annual = (monthly * 12 * (10000 - bps) + 5000) // 10000
        if data.get("annual_amount") not in (None, annual):
            raise MembershipError("conflicting_annual_amount")
    else:
        if bps is not None:
            raise MembershipError("conflicting_annual_discount")
        annual = integer(data.get("annual_amount"), "annual_amount")
    if mode == "paid" and (not intervals or monthly <= 0 or ("year" in intervals and annual <= 0)):
        raise MembershipError("paid_offer_requires_positive_enabled_prices")
    return dict(mode=mode, currency=currency, monthly_amount=monthly, annual_mode=annual_mode,
                annual_amount=annual, annual_discount_bps=bps, trial_days=trial, intervals=intervals)


def offer_dict(o):
    return dict(version=o.id, draft_id=o.id, mode=o.mode, currency=o.currency,
                monthly_amount=o.monthly_amount, annual_mode=o.annual_mode,
                annual_amount=o.annual_amount, annual_discount_bps=o.annual_discount_bps,
                annual_saving_amount=(o.monthly_amount * 12 - o.annual_amount) if o.mode == "paid" else None,
                trial_days=o.trial_days, intervals=o.intervals,
                activated_at=o.activated_at.isoformat() if o.activated_at else None)


def active_offer(s):
    setting = s.query(SmnSettings).filter_by(id=1).one()
    return s.get(SmnOffer, setting.active_offer_id)


def enroll(s, provider_user, *, now=None):
    """Subject lock serializes membership and once-only initial grant issuance."""
    now = now or now_utc()
    subject = provider_user.id
    if not subject or provider_user.email_verified is not True:
        raise MembershipError("verified_email_required", 403)
    # PostgreSQL advisory lock protects the first user insert, before a row exists.
    if s.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 5819))"), {"subject": subject})
    user = s.query(User).filter_by(workos_user_id=subject).with_for_update().one_or_none()
    if user is None:
        if s.query(User.id).filter(func.lower(User.email) == provider_user.email.lower()).first():
            raise MembershipError("identity_link_required", 409)
        user = User(id=uuid.uuid4(), workos_user_id=subject, email=provider_user.email,
                    email_verified=True, first_name=provider_user.first_name, last_name=provider_user.last_name,
                    roles=["user"], tier="explorer")
        s.add(user)
        s.flush()
    membership = s.get(SmnMembership, user.id)
    if membership is None:
        offer = active_offer(s)
        membership = SmnMembership(user_id=user.id, enrollment_offer_id=offer.id,
                                   verified_at=now, cancel_at_period_end=False)
        s.add(membership)
        s.flush()
        source = "free_launch" if offer.mode == "free" else "trial"
        if offer.mode == "free" or offer.trial_days:
            end = None if offer.mode == "free" else now + timedelta(days=offer.trial_days)
            s.add(SmnGrant(id=uuid.uuid4(), user_id=user.id, source=source,
                           source_key=f"initial:{user.id}", offer_id=offer.id, starts_at=now, ends_at=end))
            if source == "trial":
                membership.first_trial_started_at, membership.first_trial_ends_at = now, end
    return user, membership


def entitlement(s, membership, *, now=None):
    now = now or now_utc()
    offer = active_offer(s)
    result = dict(can_read=False, reason="membership_required", grant_id=None, access_ends_at=None,
                  mode=offer.mode, offer_version=offer.id, trial_days=offer.trial_days)
    if membership.suspended_at:
        result["reason"] = "membership_suspended"
        return result
    grants = s.query(SmnGrant).filter(SmnGrant.user_id == membership.user_id,
                SmnGrant.revoked_at.is_(None), SmnGrant.starts_at <= now,
                or_(SmnGrant.ends_at.is_(None), SmnGrant.ends_at > now)).all()
    if grants:
        grant = max(grants, key=lambda g: (g.ends_at is None, g.ends_at or now, str(g.id)))
        result.update(can_read=True, reason=grant.source, grant_id=str(grant.id),
                      access_ends_at=grant.ends_at.isoformat() if grant.ends_at else None)
    elif membership.first_trial_ends_at:
        result["reason"] = "trial_expired"
    return result


def settings_snapshot(s, readiness):
    setting = s.query(SmnSettings).filter_by(id=1).one()
    counts = dict(total=s.query(SmnMembership).count(),
                  suspended=s.query(SmnMembership).filter(SmnMembership.suspended_at.is_not(None)).count())
    now = now_utc()
    for source in ("free_launch", "trial", "paid"):
        counts[source] = s.query(SmnGrant.user_id).filter(SmnGrant.source == source,
                SmnGrant.revoked_at.is_(None), SmnGrant.starts_at <= now,
                or_(SmnGrant.ends_at.is_(None), SmnGrant.ends_at > now)).distinct().count()
    return dict(settings_version=setting.version, active_offer=offer_dict(s.get(SmnOffer, setting.active_offer_id)),
                draft_offers=[offer_dict(o) for o in s.query(SmnOffer).filter(SmnOffer.activated_at.is_(None)).order_by(SmnOffer.id.desc()).limit(20)],
                readiness=readiness, member_counts=counts,
                existing_free_members="Existing free launch grants remain valid; offer activation affects new enrollments.")


def save_draft(s, actor, data):
    setting = s.query(SmnSettings).filter_by(id=1).with_for_update().one()
    if data.get("expected_version") != setting.version:
        raise MembershipError("settings_version_conflict", 409)
    values = validate_offer(data.get("offer"))
    offer = SmnOffer(**values, created_by=actor.id)
    s.add(offer)
    s.flush()
    setting.version += 1
    s.add(AuditLog(actor_user_id=actor.id, action="smn_offer_draft", details={"offer_id": offer.id, "offer": values}))
    return offer.id
