"""Affiliate program - Stripe glue, program v2 rules and commission engine.

Rules of record: docs/tasks/TW-TASK-0038.md (owner-approved 2026-11-24).

  1. Provisioning: one Stripe coupon (percent_off = the partner's customer
     discount, repeating 12 months) + one promotion code (the shareable
     string) per partner; reissue_coupon re-points the SAME code at a new
     coupon when the discount changes.

  2. Pure rule helpers (no DB / Stripe): preview_offer, preview_promo,
     preview_renewal, renewal_schedule, activity_status, classify_invoice.

  3. Commission engine: compute_month(session, year, month) reads the invoices
     PAID in the month and prices each one from its REFERRAL's checkout
     snapshot (terms version, offer type, discount) - first-year pool rule on
     the list price, promo rule on the paid amount, renewal rate within the
     renewal window while the partner is active. Refunds / disputes reverse at
     the original line's rate. upsert_month() persists insert-once ledger
     lines (affiliate_commission_lines) and rebuilds the monthly
     affiliate_payouts rows from them; a re-run never double-counts and never
     re-prices a line or overwrites a paid / locked payout row.

  4. Terms versions, self-serve partner discount, company-wide campaigns.

  5. Checkout offer resolution (resolve_checkout_offer) and the webhook
     writers that persist the referral snapshot and its commission clock.

On dev STRIPE_SECRET_KEY is a Stripe TEST-mode key, so provisioning creates
disposable test coupons.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import SimpleNamespace

import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import stripe  # noqa: E402
import config  # noqa: E402

log = logging.getLogger(__name__)

stripe.api_key = config.STRIPE_SECRET_KEY

# Canonical code charset (uppercase). normalize_code() uppercases first.
CODE_RE = re.compile(r"^[A-Z0-9_-]{2,64}$")
DISCOUNT_DURATION_MONTHS = 12  # "X% off the first year"
_CENTS = Decimal("0.01")


class AffiliateError(Exception):
    """Raised on bad input or any Stripe failure so callers can abort cleanly."""


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


# Named sub-link slug (?code=ANNE&sub=youtube; TW-TASK-0039 C). A reporting
# tag on a partner's own traffic: it is stored beside the click / signup /
# referral and is NEVER an input to who earns or how much.
SUB_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SUB_COOKIE = "tw_ref_sub"            # value "<CODE>:<sub>", set beside tw_ref


def normalize_sub(raw):
    """Canonical sub-link slug (lowercase) or None when absent / malformed."""
    v = (raw or "").strip().lower() if isinstance(raw, str) else ""
    return v if SUB_RE.match(v) else None


def sub_from_cookie(cookie_value, code):
    """The slug in a tw_ref_sub cookie ("<CODE>:<sub>") if it belongs to the
    partner `code`, else None - a sub tag never travels to another partner.
    A percent-encoded value ("ANNE%3Ayoutube", written by older page JS) is
    decoded first."""
    if not isinstance(cookie_value, str):
        return None
    if "%" in cookie_value:
        from urllib.parse import unquote
        cookie_value = unquote(cookie_value)
    owner, sep, slug = cookie_value.partition(":")
    if not sep or normalize_code(owner) != normalize_code(code or "") or not owner:
        return None
    return normalize_sub(slug)


def attribution_window_days() -> int:
    """How long a referral link is remembered (the tw_ref cookie lifetime),
    in days. One source for the cookie max-age and for partner-facing copy."""
    try:
        days = int(getattr(config, "AFFILIATE_ATTRIBUTION_WINDOW_DAYS", 60) or 60)
    except (TypeError, ValueError):
        days = 60
    return max(1, days)


def attribution_cookie_max_age() -> int:
    return attribution_window_days() * 24 * 60 * 60


def owner_email() -> str:
    """THE address for every partner-program notice to the owner (help
    escalations, applications, tax-form alerts, operations summary, digest):
    AFFILIATE_OWNER_EMAIL, else AFFILIATE_SUPPORT_EMAIL, else SUPPORT_EMAIL_TO."""
    for name in ("AFFILIATE_OWNER_EMAIL", "AFFILIATE_SUPPORT_EMAIL", "SUPPORT_EMAIL_TO"):
        v = (getattr(config, name, "") or "").strip()
        if v:
            return v
    return ""


def admin_url(path="") -> str:
    """Absolute link to an admin page, for owner emails."""
    base = (getattr(config, "tw2_public_url", None) or "https://tradewave.ai/").rstrip("/")
    return base + "/admin/" + path.lstrip("/")


def hash_ip(ip):
    """Salted hash of an IP (rate limits and fraud signals; the raw IP is
    never stored)."""
    if not ip:
        return None
    import hashlib
    salt = (getattr(config, "SUPPORT_IP_HASH_SALT", "") or
            getattr(config, "API_KEY_HMAC_SECRET", "") or "tw2-partner-apply")
    return hashlib.sha256(("%s|%s" % (ip, salt)).encode("utf-8")).hexdigest()


def validate_code(code: str) -> None:
    """Validate the CANONICAL (already-normalized) code. Callers normalize first."""
    if not CODE_RE.match(code or ""):
        raise AffiliateError(
            "code must be 2-64 chars of A-Z, 0-9, '_' or '-' "
            "(e.g. ANNE or COACH-BOB)"
        )


def _pct_to_float(pct) -> float:
    # numeric(5,2) -> Stripe percent_off float (Decimal('20.00') -> 20.0)
    return float(Decimal(str(pct)))


# ---------------------------------------------------------------------------
# Interval-split helpers (different terms for monthly vs annual plans)
# ---------------------------------------------------------------------------
# The form presents two pairs, Monthly + Annual. The flat discount_pct /
# commission_pct ARE the ANNUAL terms (the default, and what backs the manually-
# typed promo code); the *_monthly columns are the optional MONTHLY override
# (NULL => monthly is the same as annual). Stripe `recurring.interval` is
# "month"/"year"; checkout `period` is "monthly"/"yearly". Everything normalizes
# here, so "year" always resolves to the flat default.

def _norm_interval(x):
    """'month' | 'year' | None, from a Stripe interval OR a checkout period."""
    x = (x or "").strip().lower()
    if x in ("month", "monthly", "mo", "m"):
        return "month"
    if x in ("year", "yearly", "annual", "annually", "yr", "y"):
        return "year"
    return None


def is_interval_split(aff) -> bool:
    """True if the affiliate carries a monthly override (monthly terms differ from annual)."""
    return (getattr(aff, "discount_pct_monthly", None) is not None
            or getattr(aff, "commission_pct_monthly", None) is not None)


def effective_discount_pct(aff, interval):
    """Discount % for a billing interval: the monthly override on monthly plans,
    else the flat (annual) default."""
    if _norm_interval(interval) == "month" and getattr(aff, "discount_pct_monthly", None) is not None:
        return aff.discount_pct_monthly
    return aff.discount_pct


def effective_commission_pct(aff, interval):
    """Commission % for a billing interval: the monthly override on monthly plans,
    else the flat (annual) default."""
    if _norm_interval(interval) == "month" and getattr(aff, "commission_pct_monthly", None) is not None:
        return aff.commission_pct_monthly
    return aff.commission_pct


def effective_coupon_id(aff, interval):
    """Stripe coupon id for a billing interval: the monthly override coupon (if one
    was minted because monthly's discount differs), else the flat (annual) coupon."""
    if _norm_interval(interval) == "month" and getattr(aff, "stripe_coupon_id_monthly", None):
        return aff.stripe_coupon_id_monthly
    return aff.stripe_coupon_id


# ---------------------------------------------------------------------------
# 1) Provisioning
# ---------------------------------------------------------------------------

def provision_stripe_objects(aff) -> tuple[str, str]:
    """Create the Stripe coupon + promotion code for a freshly-added affiliate.

    Returns (coupon_id, promotion_code_id). Idempotent: if the affiliate already
    carries both ids they are returned unchanged. Raises AffiliateError on any
    Stripe failure so the caller can abort the DB insert (we never persist an
    affiliate without its Stripe objects). On promo-code failure the just-created
    coupon is best-effort deleted so we don't leak an orphan.
    """
    if aff.stripe_coupon_id and aff.stripe_promotion_code_id:
        return aff.stripe_coupon_id, aff.stripe_promotion_code_id

    code = normalize_code(aff.code)
    validate_code(code)
    percent_off = _pct_to_float(aff.discount_pct)
    if not (0 < percent_off <= 100):
        raise AffiliateError("discount_pct must be > 0 and <= 100")

    try:
        coupon = stripe.Coupon.create(
            percent_off=percent_off,
            duration="repeating",
            duration_in_months=DISCOUNT_DURATION_MONTHS,
            # Stripe caps coupon `name` at 40 chars; keep it short. The
            # discount lives in percent_off and the code in metadata + the
            # promotion code, so a truncated label here is purely cosmetic.
            name=f"Affiliate {code}"[:40],
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate"},
        )
    except Exception as e:
        raise AffiliateError(f"Stripe coupon create failed: {e}") from e

    try:
        # Stripe SDK 15.x: the coupon is nested under `promotion`, not a
        # top-level `coupon` param (older API). type must be "coupon".
        promo = stripe.PromotionCode.create(
            code=code,
            promotion={"type": "coupon", "coupon": coupon.id},
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate"},
        )
    except Exception as e:
        try:
            stripe.Coupon.delete(coupon.id)
        except Exception:
            log.warning("orphan coupon %s left after promo-code failure", coupon.id)
        raise AffiliateError(f"Stripe promotion code create failed: {e}") from e

    return coupon.id, promo.id


def provision_interval_overrides(aff) -> None:
    """Mint the MONTHLY override coupon when the affiliate's monthly discount
    differs from the annual (flat) discount, and store its id. No-op for a flat
    affiliate (no monthly override, or monthly == annual -> the flat coupon
    already serves monthly). Idempotent (skips if the coupon id is already set).
    The override coupon carries NO promotion code -- it's applied by id at
    checkout; the flat promo still covers manual entry at the annual rate. Repeats
    12 months ("first year"). Raises AffiliateError on a Stripe failure."""
    ov = getattr(aff, "discount_pct_monthly", None)
    if ov is None or getattr(aff, "stripe_coupon_id_monthly", None):
        return
    annual = _pct_to_float(aff.discount_pct)
    pct = _pct_to_float(ov)
    if not (0 < pct <= 100):
        raise AffiliateError("monthly discount must be > 0 and <= 100")
    if pct == annual:
        return  # same as annual -> the flat coupon already serves monthly
    code = normalize_code(aff.code)
    try:
        coupon = stripe.Coupon.create(
            percent_off=pct,
            duration="repeating",
            duration_in_months=DISCOUNT_DURATION_MONTHS,
            name=f"Affiliate {code} mo"[:40],
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate",
                      "tw2_interval": "month"},
        )
    except Exception as e:
        raise AffiliateError(f"Stripe monthly override coupon create failed: {e}") from e
    aff.stripe_coupon_id_monthly = coupon.id


def teardown_stripe_objects(aff) -> None:
    """Best-effort cleanup when an affiliate with NO referral/payout history is
    hard-deleted: deactivate the promotion code so it can't be redeemed, and
    delete the coupon so nothing dangles in Stripe. Promotion codes can't be
    deleted via the API (only deactivated); coupons can. An already-gone object
    counts as success; raises AffiliateError only on a real failure so the caller
    can warn (the row delete still proceeds)."""
    errs = []
    pid = getattr(aff, "stripe_promotion_code_id", None)
    if pid:
        try:
            stripe.PromotionCode.modify(pid, active=False)
        except Exception as e:
            if getattr(e, "code", "") != "resource_missing":
                errs.append(f"promo {pid}: {e}")
    for attr in ("stripe_coupon_id", "stripe_coupon_id_monthly"):
        cid = getattr(aff, attr, None)
        if cid:
            try:
                stripe.Coupon.delete(cid)
            except Exception as e:
                if getattr(e, "code", "") != "resource_missing":
                    errs.append(f"coupon {cid}: {e}")
    if errs:
        raise AffiliateError("; ".join(errs))


def reissue_coupon(aff, new_discount_pct) -> tuple[str, str]:
    """Mint a NEW coupon at new_discount_pct and re-point the affiliate's promo
    code (SAME code string) to it, so NEW referrals get the new discount while
    EXISTING customers keep theirs (their subscriptions still carry the OLD
    coupon, which we never touch/delete). Returns (new_coupon_id, new_promo_id).

    Safe against partial failure: if the new promo code can't be created, the old
    promo is re-activated and the just-minted coupon is deleted, so the affiliate
    is never left without a working code. The NEW promo is created active; the
    caller is responsible for its final active state (e.g. deactivate while the
    affiliate is paused pending re-signature)."""
    code = normalize_code(aff.code)
    pct = _pct_to_float(new_discount_pct)
    if not (0 < pct <= 100):
        raise AffiliateError("discount_pct must be > 0 and <= 100")
    old_pid = getattr(aff, "stripe_promotion_code_id", None)

    try:
        coupon = stripe.Coupon.create(
            percent_off=pct,
            duration="repeating",
            duration_in_months=DISCOUNT_DURATION_MONTHS,
            name=f"Affiliate {code}"[:40],
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate"},
        )
    except Exception as e:
        raise AffiliateError(f"Stripe coupon create failed: {e}") from e

    # Free up the code string: Stripe enforces uniqueness among ACTIVE promotion
    # codes, so the old one must be deactivated before we re-create with the same
    # code on the new coupon.
    if old_pid:
        try:
            stripe.PromotionCode.modify(old_pid, active=False)
        except Exception as e:
            try:
                stripe.Coupon.delete(coupon.id)
            except Exception:
                log.warning("orphan coupon %s after old-promo deactivate failed", coupon.id)
            raise AffiliateError(f"Could not deactivate the old promo code: {e}") from e
    else:
        # No tracked promo id: defensively deactivate any stray ACTIVE promo that
        # already holds this code string, so the create below doesn't hit Stripe's
        # active-code uniqueness rule.
        try:
            for pc in stripe.PromotionCode.list(code=code, active=True, limit=100).auto_paging_iter():
                try:
                    stripe.PromotionCode.modify(pc.id, active=False)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        promo = stripe.PromotionCode.create(
            code=code,
            promotion={"type": "coupon", "coupon": coupon.id},
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate"},
        )
    except Exception as e:
        # Roll back so the affiliate keeps a working code: re-activate the old
        # promo and remove the new coupon we just made.
        if old_pid:
            try:
                stripe.PromotionCode.modify(old_pid, active=True)
            except Exception:
                log.warning("could not re-activate old promo %s during rollback", old_pid)
        try:
            stripe.Coupon.delete(coupon.id)
        except Exception:
            log.warning("orphan coupon %s after new-promo create failed", coupon.id)
        raise AffiliateError(f"Stripe promotion code create failed: {e}") from e

    return coupon.id, promo.id


def revert_reissue(old_promo_id, new_coupon_id, new_promo_id) -> None:
    """Compensating undo for a reissue_coupon swap when the DB transaction that
    was supposed to record it fails: restore the affiliate's PRE-change code by
    re-activating the old promo, and remove the just-minted new coupon/promo so
    nothing dangles. Best-effort per step; raises AffiliateError if any step
    errors so the caller can surface ids for manual reconciliation."""
    errs = []
    if old_promo_id:
        try:
            stripe.PromotionCode.modify(old_promo_id, active=True)
        except Exception as e:
            errs.append(f"reactivate old promo {old_promo_id}: {e}")
    if new_promo_id:
        try:
            stripe.PromotionCode.modify(new_promo_id, active=False)
        except Exception as e:
            errs.append(f"deactivate new promo {new_promo_id}: {e}")
    if new_coupon_id:
        try:
            stripe.Coupon.delete(new_coupon_id)
        except Exception as e:
            errs.append(f"delete new coupon {new_coupon_id}: {e}")
    if errs:
        raise AffiliateError("; ".join(errs))


# ---------------------------------------------------------------------------
# 2) Program v2 rules - pure helpers (no DB, no Stripe)
# ---------------------------------------------------------------------------
# Owner-approved rules: docs/tasks/TW-TASK-0038.md. Three ways a paid invoice
# earns, decided from the REFERRAL's checkout snapshot (never the partner's
# current row):
#   first_year  regular offer, commission year 1: (pool - discount)% of the
#               LIST price (pre-discount subtotal, tax excluded)
#   promo       campaign offer, commission year 1: promo_commission_pct of
#               what the customer paid (tax excluded)
#   renewal     commission year 2 .. renewal_years: renewal_pct of what the
#               customer paid, only while the partner is ACTIVE (activity
#               rule); otherwise the line is recorded as 'lapsed' at $0.

DEFAULT_TERMS_VERSION = "v2-5y"
# Fallback when a referral/partner carries no terms row (duck-typed tests,
# pre-v2 rows). Mirrors the seeded v2-5y row in migration b4d7e1f2a3c5.
DEFAULT_TERMS = SimpleNamespace(
    id=None, version=DEFAULT_TERMS_VERSION,
    pool_pct=Decimal("50"), max_discount_pct=Decimal("25"),
    promo_commission_pct=Decimal("50"), renewal_pct=Decimal("25"),
    renewal_years=5, activity_rule_months=12)

RETURN_WINDOW_MONTHS = 12          # cancel-and-return: same partner keeps credit
DISCOUNT_CHANGE_COOLDOWN = dt.timedelta(hours=24)
# Detail-line kinds that are SALES (legacy 'payment' = pre-v2 statement rows).
PAYMENT_KINDS = ("payment", "first_year", "promo", "renewal")
REVERSAL_KINDS = ("refund", "dispute")
# A period start this close before an anniversary still counts as that month
# (guards clock jitter between the anchor and Stripe's period boundaries).
_ANCHOR_TOLERANCE = dt.timedelta(days=2)
_HUNDRED = Decimal(100)


def is_payment_line(line) -> bool:
    """True for a sale line in a statement/estimate detail list (v2 kinds and
    the legacy 'payment'). Reversals and lapsed lines are not payments."""
    return ((line or {}).get("kind") or "payment") in PAYMENT_KINDS


def _dec(v, default="0") -> Decimal:
    if v is None or v == "":
        return Decimal(default)
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _utc(v):
    """Aware UTC datetime from a datetime (naive = UTC), an epoch, or None."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.replace(tzinfo=dt.timezone.utc) if v.tzinfo is None else v.astimezone(dt.timezone.utc)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)
    try:
        return dt.datetime.fromtimestamp(int(float(v)), tz=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _add_months(d: dt.datetime, months: int) -> dt.datetime:
    """Calendar-month arithmetic from the ORIGINAL day (Jan 31 + 1 = Feb 28/29,
    + 2 = Mar 31), the same way Stripe walks a billing-cycle anchor."""
    idx = d.year * 12 + (d.month - 1) + months
    year, month = divmod(idx, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return d.replace(year=year, month=month + 1, day=day)


def months_since_anchor(anchor, at) -> int:
    """Whole service months from the year-1 anchor to `at` (0 = month 1)."""
    anchor, at = _utc(anchor), _utc(at)
    probe = at + _ANCHOR_TOLERANCE
    if probe < anchor:
        return 0
    k = (probe.year - anchor.year) * 12 + (probe.month - anchor.month)
    while k > 0 and _add_months(anchor, k) > probe:
        k -= 1
    return max(k, 0)


def year_number(anchor, at) -> int:
    """Commission year (1-based) of a service period that starts at `at`."""
    return months_since_anchor(anchor, at) // 12 + 1


def _terms_of(terms):
    return terms if terms is not None else DEFAULT_TERMS


def _cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def clamp_discount(discount_pct, terms=None) -> Decimal:
    """Clamp a partner discount into [0, terms.max_discount_pct]."""
    t = _terms_of(terms)
    return max(Decimal("0"), min(_dec(discount_pct), _dec(t.max_discount_pct)))


def preview_offer(list_price_cents, discount_pct, terms=None) -> dict:
    """Pool rule, in cents: what the customer pays, what the partner earns and
    what TradeWave retains for a regular referred sale at `discount_pct`.
    Raises AffiliateError when the discount is outside 0..max_discount_pct."""
    t = _terms_of(terms)
    d = _dec(discount_pct)
    if d < 0 or d > _dec(t.max_discount_pct):
        raise AffiliateError("discount must be between 0%% and %s%%"
                             % _dec(t.max_discount_pct).normalize())
    lp = int(list_price_cents)
    customer = _cents(Decimal(lp) * (_HUNDRED - d) / _HUNDRED)
    rate = max(Decimal("0"), _dec(t.pool_pct) - d)
    partner = _cents(Decimal(lp) * rate / _HUNDRED)
    return {"list_price_cents": lp, "discount_pct": d, "commission_rate_pct": rate,
            "customer_pays_cents": customer, "partner_earns_cents": partner,
            "retained_cents": customer - partner}


def preview_promo(promo_price_cents, list_price_cents=None, terms=None) -> dict:
    """Promo rule, in cents: a referred campaign sale pays the partner
    promo_commission_pct of what the customer actually paid (pre-tax)."""
    t = _terms_of(terms)
    paid = int(promo_price_cents)
    rate = _dec(t.promo_commission_pct)
    partner = _cents(Decimal(paid) * rate / _HUNDRED)
    lp = int(list_price_cents) if list_price_cents is not None else None
    return {"list_price_cents": lp, "commission_rate_pct": rate,
            "customer_pays_cents": paid, "partner_earns_cents": partner,
            "retained_cents": paid - partner,
            "savings_cents": (lp - paid) if lp is not None else None}


def preview_renewal(paid_cents, terms=None) -> dict:
    """Renewal rule, in cents: renewal_pct of what the customer pays."""
    t = _terms_of(terms)
    paid = int(paid_cents)
    partner = _cents(Decimal(paid) * _dec(t.renewal_pct) / _HUNDRED)
    return {"commission_rate_pct": _dec(t.renewal_pct), "customer_pays_cents": paid,
            "partner_earns_cents": partner, "retained_cents": paid - partner}


def renewal_schedule(terms=None) -> dict:
    """The renewal window of a terms version, for display. renewal_years is
    the LAST commission year (5 = years 2-5); None = lifetime."""
    t = _terms_of(terms)
    last = t.renewal_years
    lifetime = last is None
    return {
        "renewal_pct": _dec(t.renewal_pct),
        "lifetime": lifetime,
        "first_year": 2,
        "last_year": last,
        "annual_renewals_paid": None if lifetime else max(0, int(last) - 1),
        "monthly_first_month": 13,
        "monthly_last_month": None if lifetime else int(last) * 12,
        "activity_rule_months": int(t.activity_rule_months or 0),
        "label": ("Lifetime renewals" if lifetime
                  else "Renewals in years 2-%d" % int(last)),
    }


# Owner decision 2026-11-24: a 30-day grace on top of the activity window, so a
# partner whose only customer of the year renews 12 months later is still paid
# on that renewal ("at least 1 new customer per year").
ACTIVITY_GRACE_DAYS = 30


def _is_active_at(first_paid_dates, at, months) -> bool:
    """Activity rule: at least one NEW paying customer in the trailing
    `months` (+ ACTIVITY_GRACE_DAYS) before `at` (window is
    (at - months - grace, at]; 0 disables the rule)."""
    months = int(months or 0)
    if months <= 0:
        return True
    at = _utc(at)
    floor = _add_months(at, -months) - dt.timedelta(days=ACTIVITY_GRACE_DAYS)
    return any(floor < d <= at for d in (_utc(x) for x in first_paid_dates) if d is not None)


def activity_status(affiliate, now=None, *, first_paid_dates=None, session=None, terms=None) -> dict:
    """Where the partner stands on the activity rule right now.

    Returns {active, last_new_customer_at, active_until (date) | None,
    lapsed_since (date) | None, activity_rule_months}. `first_paid_dates`
    (first successful payment of each NEW referred customer) is read from the
    affiliate's referrals when not supplied (pass `session`, or the affiliate's
    own ORM session is used)."""
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    t = terms if terms is not None else (getattr(affiliate, "terms", None) or DEFAULT_TERMS)
    months = int(t.activity_rule_months or 0)
    if first_paid_dates is None:
        from sqlalchemy.orm import object_session
        from models import AffiliateReferral
        session = session or object_session(affiliate)
        first_paid_dates = [r[0] for r in (
            session.query(AffiliateReferral.first_paid_at)
            .filter(AffiliateReferral.affiliate_id == affiliate.id,
                    AffiliateReferral.first_paid_at.isnot(None),
                    AffiliateReferral.source != "return").all())]
    dates = sorted(d for d in (_utc(x) for x in first_paid_dates) if d is not None and d <= now)
    last = dates[-1] if dates else None
    out = {"active": True, "last_new_customer_at": last, "active_until": None,
           "lapsed_since": None, "activity_rule_months": months}
    if months <= 0:
        return out
    if last is None:
        out["active"] = False
        return out
    until = _add_months(last, months) + dt.timedelta(days=ACTIVITY_GRACE_DAYS)
    if now < until:
        out["active_until"] = until.date()
    else:
        out["active"] = False
        out["lapsed_since"] = until.date()
    return out


# ---------------------------------------------------------------------------
# 3) Commission engine
# ---------------------------------------------------------------------------

def _month_window(year: int, month: int):
    """Return (start_dt, end_dt, period_start_date, period_end_date) for a UTC
    calendar month, half-open [start, end)."""
    start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    if month == 12:
        end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
    else:
        end = dt.datetime(year, month + 1, 1, tzinfo=dt.timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    return start, end, dt.date(year, month, 1), dt.date(year, month, last_day)


def _coupon_id_from_discount(d) -> str | None:
    """Pull the coupon id out of a Stripe Discount object, across API shapes:
      - current (SDK 15.x / API 2025+): d['source'] = {'type':'coupon','coupon': <id>}
      - older:                          d['coupon'] = {'id': <id>}  or a bare id string
    """
    if not isinstance(d, dict):
        return None
    src = d.get("source")
    if isinstance(src, dict) and src.get("type") == "coupon":
        c = src.get("coupon")
        return c.get("id") if isinstance(c, dict) else c
    c = d.get("coupon")
    if isinstance(c, dict):
        return c.get("id")
    return c if isinstance(c, str) else None


def _invoice_coupon_ids(inv: dict) -> list[str]:
    """All Stripe coupon ids applied to an invoice (or subscription). Reads the
    `discounts` list (each a Discount object) plus the legacy single
    `discount`. NOTE: the coupon now lives at discount.source.coupon, NOT
    discount.coupon - the old path silently returned nothing and broke
    attribution. Unexpanded discount-id strings are skipped (compute_month
    expands data.discounts)."""
    ids: list[str] = []
    single = _coupon_id_from_discount(inv.get("discount"))
    if single:
        ids.append(single)
    for d in (inv.get("discounts") or []):
        cid = _coupon_id_from_discount(d)
        if cid:
            ids.append(cid)
    return ids


def _invoice_tax_cents(inv: dict) -> int:
    """Total tax on the invoice, in cents. Stripe SDK 15.x / API 2025-03-31+
    carries tax in `total_taxes` (list of {amount}); older APIs used the
    top-level `tax` or `total_tax_amounts`. Check all three so we work across
    versions (the live SDK only emits total_taxes - missing it silently
    zeroed tax and overpaid commission on every taxed sale)."""
    tax = inv.get("tax")
    if tax is None:
        items = (inv.get("total_taxes")
                 or inv.get("total_tax_amounts")
                 or [])
        tax = sum((t.get("amount") or 0) for t in items)
    return int(tax or 0)


def _invoice_list_cents(invd: dict) -> int:
    """The invoice's LIST amount in cents: the pre-discount subtotal with tax
    excluded (the pool-rule basis). Falls back to paid-less-tax plus the
    discount amounts when the subtotal fields are absent."""
    for key in ("subtotal_excluding_tax", "subtotal"):
        v = invd.get(key)
        if v is not None:
            return max(0, int(v))
    net = max(0, int(invd.get("amount_paid") or 0) - _invoice_tax_cents(invd))
    disc = sum(int(d.get("amount") or 0) for d in (invd.get("total_discount_amounts") or []))
    return net + disc


def _invoice_paid_at(invd: dict):
    """When the invoice was PAID (status_transitions.paid_at), else created."""
    st = invd.get("status_transitions") or {}
    return _utc(st.get("paid_at")) or _utc(invd.get("created"))


def _line_is_proration(ln: dict) -> bool:
    if ln.get("proration"):
        return True
    parent = ln.get("parent") or {}
    for key in ("subscription_item_details", "invoice_item_details"):
        if (parent.get(key) or {}).get("proration"):
            return True
    return False


def _invoice_service_start(invd: dict):
    """Start of the SERVICE PERIOD the invoice pays for: line.period.start of
    its subscription line (not invoice.created - a late-paid or back-dated
    invoice still belongs to the period it covers). Falls back to the paid
    date when the invoice carries no line periods."""
    lines = (invd.get("lines") or {}).get("data") or []
    best = None
    for ln in lines:
        start = (ln.get("period") or {}).get("start")
        if start is None:
            continue
        cand = (0 if _line_is_proration(ln) else 1, int(start))
        if best is None or cand > best:
            best = cand
    if best is not None:
        return _utc(best[1])
    return _invoice_paid_at(invd)


def _invoice_subscription_id(invd):
    """The subscription id an invoice belongs to, across SDK shapes."""
    sub = invd.get("subscription")
    if isinstance(sub, str):
        return sub
    if isinstance(sub, dict):
        return sub.get("id")
    parent = invd.get("parent") or {}
    sd = parent.get("subscription_details") or invd.get("subscription_details") or {}
    val = sd.get("subscription")
    if isinstance(val, dict):
        return val.get("id")
    return val or None


def _invoice_interval(invd):
    """'month' | 'year' | None for the invoice's recurring line. Read straight
    off the invoice line items (no extra Stripe call)."""
    lines = (invd.get("lines") or {}).get("data") or []
    for ln in lines:
        price = ln.get("price") or {}
        rec = price.get("recurring") or {}
        iv = _norm_interval(rec.get("interval"))
        if iv:
            return iv
        plan = ln.get("plan") or {}            # older SDK shape
        iv = _norm_interval(plan.get("interval"))
        if iv:
            return iv
    return None


def _first_paid_invoice(customer_id: str, subscription_id: str | None = None,
                        coupon_id: str | None = None):
    """The earliest PAID invoice with amount_paid > 0 for a subscription (or,
    when the subscription id is unknown, the earliest carrying `coupon_id`), as
    {"paid_at", "service_start", "invoice"} - or None when Stripe ANSWERED and
    there is none. $0 trial invoices and failed payments never qualify, so
    they never start the commission clock.

    A Stripe failure raises StripeLookupError. It is never turned into "no
    invoice": the caller would then anchor the commission clock on the wrong
    invoice, or declare an active partner lapsed, and persist that forever."""
    if not customer_id:
        return None
    try:
        best = None
        listing = stripe.Invoice.list(customer=customer_id, status="paid",
                                      limit=100, expand=["data.discounts"])
        for inv in listing.auto_paging_iter():
            invd = inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)
            if (invd.get("amount_paid") or 0) <= 0:
                continue
            if subscription_id:
                if _invoice_subscription_id(invd) != subscription_id:
                    continue
            elif coupon_id and coupon_id not in _invoice_coupon_ids(invd):
                continue
            paid_at = _invoice_paid_at(invd)
            if paid_at is not None and (best is None or paid_at < best["paid_at"]):
                best = {"paid_at": paid_at, "service_start": _invoice_service_start(invd),
                        "invoice": invd.get("id")}
        return best
    except Exception as e:
        raise StripeLookupError("first-paid-invoice lookup failed for %s: %s"
                                % (customer_id, e)) from e


class StripeLookupError(AffiliateError):
    """Stripe could not be asked something the engine needs to price a line
    (a transient error). The invoice / reversal is SKIPPED for this run - not
    booked, not persisted - and picked up by the next run."""


def _resolve_terms(ref, aff, terms_by_id):
    """Terms for a line: the REFERRAL's snapshot first, then the partner's
    current terms (pre-v2 / coupon-only rows), then the program default."""
    terms_by_id = terms_by_id or {}
    for owner in (ref, aff):
        if owner is None:
            continue
        t = getattr(owner, "terms", None)
        if t is not None:
            return t
        tid = getattr(owner, "terms_id", None)
        if tid is not None and tid in terms_by_id:
            return terms_by_id[tid]
    return DEFAULT_TERMS


def classify_invoice(invd: dict, ref, terms, anchor, is_active) -> dict | None:
    """Price ONE paid invoice under the program rules. Pure.

    ref: the referral snapshot (offer_type, discount_pct; may be None for a
    coupon-only attribution). anchor: service start of commission year 1.
    is_active(paid_at, months) -> bool: the partner's activity rule.
    Returns the line fields (kind, year_number, basis_cents, net_paid_cents,
    rate_pct, amount as an UNROUNDED Decimal in dollars, ...) or None when the
    invoice earns nothing and leaves no line ($0 paid, or past the renewal
    window)."""
    t = _terms_of(terms)
    amount_paid = int(invd.get("amount_paid") or 0)
    tax_cents = _invoice_tax_cents(invd)
    net = max(0, amount_paid - tax_cents)
    if amount_paid <= 0 or net <= 0:
        return None
    service_start = _invoice_service_start(invd)
    paid_at = _invoice_paid_at(invd)
    year = year_number(anchor or service_start, service_start)
    offer = (getattr(ref, "offer_type", None) or "regular")
    line = {
        "year_number": year,
        "service_period_start": service_start,
        "paid_at": paid_at,
        "net_paid_cents": net,
        "amount_paid_cents": amount_paid,
        "tax_cents": tax_cents,
        "offer_type": offer,
    }
    if year <= 1 and offer == "promo":
        rate = _dec(t.promo_commission_pct)
        line.update(kind="promo", basis_cents=net, rate_pct=rate,
                    amount=Decimal(net) * rate / _HUNDRED / _HUNDRED)
        return line
    if year <= 1:
        list_cents = _invoice_list_cents(invd) or net
        stamped = getattr(ref, "discount_pct", None)
        if stamped is None:
            # Coupon-only / pre-v2 row: use the discount actually on the invoice.
            actual = (Decimal(list_cents - net) * _HUNDRED / Decimal(list_cents)
                      if list_cents > net else Decimal("0"))
            discount = min(max(actual, Decimal("0")), _dec(t.pool_pct)).quantize(Decimal("0.01"))
        else:
            discount = _dec(stamped)
        rate = max(Decimal("0"), _dec(t.pool_pct) - discount)
        amount = Decimal(list_cents) * rate / _HUNDRED / _HUNDRED
        expected_net = Decimal(list_cents) * (_HUNDRED - discount) / _HUNDRED
        line.update(kind="first_year", basis_cents=list_cents, rate_pct=rate,
                    discount_pct=discount, list_cents=list_cents)
        if Decimal(net) < expected_net - 1:
            # The customer paid LESS than the stamped offer (an extra coupon or
            # credit got onto the invoice). Never stack: fall back to the promo
            # rule on what was actually paid, capped at the pool amount.
            promo_amount = Decimal(net) * _dec(t.promo_commission_pct) / _HUNDRED / _HUNDRED
            if promo_amount < amount:
                amount = promo_amount
                line.update(basis_cents=net, rate_pct=_dec(t.promo_commission_pct),
                            guard="extra_discount")
        line["amount"] = amount
        return line
    last_year = t.renewal_years
    if last_year is not None and year > int(last_year):
        return None                                   # past the renewal window: $0, no line
    rate = _dec(t.renewal_pct)
    if is_active(paid_at, t.activity_rule_months):
        line.update(kind="renewal", basis_cents=net, rate_pct=rate,
                    amount=Decimal(net) * rate / _HUNDRED / _HUNDRED)
    else:
        # Forfeited, never paid later - recorded so the partner can see it.
        line.update(kind="lapsed", basis_cents=net, rate_pct=rate, amount=Decimal("0"),
                    forfeited=str((Decimal(net) * rate / _HUNDRED / _HUNDRED).quantize(_CENTS, rounding=ROUND_HALF_UP)))
    return line


class LedgerView:
    """What the engine needs to know about ALREADY-PERSISTED ledger lines:
    the original sale line of an invoice (so a refund reverses at the original
    rate and formula) and how much of it earlier reversals already took back.
    Backed by plain dicts so the pure core stays testable; compute_month
    fills it from affiliate_commission_lines."""

    def __init__(self, lines=()):
        self._sales = {}       # (affiliate_id, invoice_id) -> line dict
        self._reversed = {}    # (affiliate_id, invoice_id) -> Decimal (positive)
        self._sources = {}     # (affiliate_id, source_id) -> line dict
        for ln in lines:
            self.add(ln)

    def add(self, ln: dict) -> None:
        aid = str(ln["affiliate_id"])
        self._sources[(aid, ln["source_id"])] = ln
        inv = ln.get("invoice")
        if ln.get("kind") in REVERSAL_KINDS:
            self._reversed[(aid, inv)] = self._reversed.get((aid, inv), Decimal("0")) - _dec(ln.get("amount"))
        elif inv:
            self._sales[(aid, inv)] = ln

    def sale(self, affiliate_id, invoice_id):
        return self._sales.get((str(affiliate_id), invoice_id))

    def reversed_amount(self, affiliate_id, invoice_id) -> Decimal:
        return self._reversed.get((str(affiliate_id), invoice_id), Decimal("0"))

    def line(self, affiliate_id, source_id):
        """The persisted line for a Stripe source object (invoice, refund or
        dispute id), or None."""
        return self._sources.get((str(affiliate_id), source_id))


def _line_dict_from_row(row) -> dict:
    """An affiliate_commission_lines ORM row as an engine/detail line dict."""
    d = dict(row.detail or {})
    amount = _dec(row.amount)
    d.update({
        "affiliate_id": str(row.affiliate_id),
        "kind": row.kind, "state": row.state, "hold_reason": row.hold_reason,
        "source_id": row.source_id, "invoice": row.stripe_invoice_id,
        "customer": row.stripe_customer_id, "subscription": row.stripe_subscription_id,
        "referral_id": str(row.referral_id) if row.referral_id else None,
        "currency": row.currency, "interval": row.billing_interval,
        "service_period_start": _iso(row.service_period_start),
        "event_at": _iso(row.event_at),
        "year_number": row.year_number,
        "net_paid_cents": int(row.net_paid_cents or 0),
        "basis_cents": int(row.basis_cents or 0),
        "basis": str((Decimal(int(row.basis_cents or 0)) / _HUNDRED).quantize(_CENTS)),
        "rate_pct": str(_dec(row.rate_pct)),
        "amount": str(amount),
        "commission": str(amount.quantize(_CENTS, rounding=ROUND_HALF_UP)),
        "period_month": row.period_month.isoformat() if row.period_month else None,
        "persisted": True,
    })
    if row.stripe_reversal_id:
        d[row.kind] = row.stripe_reversal_id
    return d


def _iso(v):
    v = _utc(v)
    return v.isoformat() if v is not None else None


def _from_iso(v):
    """Inverse of _iso for values read back from a persisted line dict."""
    if isinstance(v, str):
        return _utc(dt.datetime.fromisoformat(v))
    return v


def _state_for(aff) -> tuple[str, str | None]:
    """(state, hold_reason) of a freshly computed line for this partner:
    active -> estimated (payable); paused -> HELD (payable once unpaused);
    terminated WITHOUT cause -> estimated (agreement 5.3 / 11.3: commission on
    payments already made stays payable and the final balance is paid);
    terminated FOR CAUSE -> void (the only forfeiture)."""
    status = getattr(aff, "status", None) or "active"
    if status == "active":
        return "estimated", None
    if status == "paused":
        return "held", "paused"
    if getattr(aff, "terminated_for_cause", False):
        return "void", "terminated_for_cause"
    return "estimated", None


def compute_month(session, year: int, month: int, discovered=None, skipped=None) -> list[dict]:
    """Compute every partner's commission lines for the month from Stripe and
    the persisted referrals. Does NOT write anything. See _compute().

    ALL partners are computed, not only active ones: a paused partner's lines
    come back HELD (they become payable when unpaused) and only a partner
    terminated for cause forfeits (void)."""
    from models import Affiliate, AffiliateReferral, AffiliateTerms
    affiliates = session.query(Affiliate).all()
    referrals = session.query(AffiliateReferral).all()
    terms_by_id = {t.id: t for t in session.query(AffiliateTerms).all()}
    return _compute(affiliates, year, month,
                    {r.stripe_subscription_id: r for r in referrals},
                    terms_by_id=terms_by_id, ledger=_ledger_loader(session),
                    discovered=discovered, skipped=skipped)


def _ledger_loader(session):
    """LedgerView factory for _compute: given the invoice ids in play, load the
    persisted lines that reference them."""
    def load(invoice_ids):
        from models import AffiliateCommissionLine
        ids = [i for i in set(invoice_ids) if i]
        view = LedgerView()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for row in (session.query(AffiliateCommissionLine)
                        .filter(AffiliateCommissionLine.stripe_invoice_id.in_(chunk)).all()):
                view.add(_line_dict_from_row(row))
        return view
    return load


# Dispute statuses that do NOT take money back (won, or inquiries that never
# withdrew funds). Every other dispute status nets the commission.
_DISPUTE_NO_CLAWBACK = {"won", "warning_needs_response", "warning_under_review",
                        "warning_closed"}
# Refund statuses that mean the money did NOT (or will not) leave.
_REFUND_UNDONE = {"failed", "canceled"}


def _reversal_lookback_days() -> int:
    return max(0, int(getattr(config, "AFFILIATE_REVERSAL_LOOKBACK_DAYS", 180) or 0))


def _month_reversals(start, end):
    """Refunds and disputes the month's reversal pass has to look at, as plain
    dicts {kind, id, amount, charge, payment_intent, created, status, undo}.

    * CREATED in [start, end): refunds that took (or are taking) money back
      and disputes that withdrew funds. Dated by when the money left, so a
      refund of an invoice paid in an earlier (possibly already-paid-out)
      month lands in THIS month as a negative line - the clawback. Credit
      notes that refund money create Refund objects, so they are covered here
      too (and are no longer netted on the invoice itself).
    * Created up to AFFILIATE_REVERSAL_LOOKBACK_DAYS BEFORE the month, to
      catch a status that changed after the event's own month was computed:
      a dispute that was WON (the commission comes back), an inquiry that
      ESCALATED into a real dispute (clawed back now), and a pending refund
      that FAILED or was canceled (the clawback is undone).

    `undo` is True when the event's current status means the money came back:
    the reversal pass then books an offsetting line, but only against a
    clawback that is already in the ledger."""
    lo = int((start - dt.timedelta(days=_reversal_lookback_days())).timestamp())
    month_lo = int(start.timestamp())
    window = {"gte": lo, "lt": int(end.timestamp())}
    out = []
    for r in stripe.Refund.list(created=window, limit=100).auto_paging_iter():
        rd = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        status = rd.get("status")
        undo = status in _REFUND_UNDONE
        in_month = int(rd.get("created") or 0) >= month_lo
        if not undo and (status not in ("succeeded", "pending") or not in_month):
            continue                  # an earlier month's refund was booked in its own month
        out.append({"kind": "refund", "id": rd.get("id"), "amount": int(rd.get("amount") or 0),
                    "charge": rd.get("charge"), "payment_intent": rd.get("payment_intent"),
                    "created": rd.get("created"), "status": status, "undo": undo})
    for d in stripe.Dispute.list(created=window, limit=100).auto_paging_iter():
        dd = d.to_dict() if hasattr(d, "to_dict") else dict(d)
        status = dd.get("status")
        if status in _DISPUTE_NO_CLAWBACK and status != "won":
            continue                  # an inquiry: no money has moved (yet)
        out.append({"kind": "dispute", "id": dd.get("id"), "amount": int(dd.get("amount") or 0),
                    "charge": dd.get("charge"), "payment_intent": dd.get("payment_intent"),
                    "created": dd.get("created"), "status": status, "undo": status == "won"})
    out.sort(key=lambda e: (int(e.get("created") or 0), e.get("id") or ""))
    return out


def undo_source_id(ev) -> str:
    """source_id of the line that gives a clawback back: '<dispute id>:won' or
    '<refund id>:failed'. Stable, so the give-back is booked exactly once."""
    return "%s:%s" % (ev["id"], "won" if ev["kind"] == "dispute" else "failed")


def _id_of(v):
    if isinstance(v, dict):
        return v.get("id")
    return v if isinstance(v, str) else None


def _invoice_for_reversal(ev):
    """The paid invoice (dict, discounts expanded) a refund/dispute reverses,
    or None when the payment belongs to no invoice. API 2025+ links payments
    to invoices via InvoicePayment; older APIs carried charge.invoice. A
    Stripe failure raises StripeLookupError (the reversal is retried on the
    next run instead of being dropped)."""
    inv_id = None
    pi = _id_of(ev.get("payment_intent"))
    try:
        if pi:
            ips = stripe.InvoicePayment.list(
                payment={"type": "payment_intent", "payment_intent": pi}, limit=1)
            for ip in ips.auto_paging_iter():
                ipd = ip.to_dict() if hasattr(ip, "to_dict") else dict(ip)
                inv_id = _id_of(ipd.get("invoice"))
                break
        if not inv_id and _id_of(ev.get("charge")):
            ch = stripe.Charge.retrieve(_id_of(ev.get("charge")))
            chd = ch.to_dict() if hasattr(ch, "to_dict") else dict(ch)
            inv_id = _id_of(chd.get("invoice"))
        if not inv_id:
            return None
        inv = stripe.Invoice.retrieve(inv_id, expand=["discounts"])
        return inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)
    except Exception as e:   # noqa: BLE001
        raise StripeLookupError("reversal %s: invoice lookup failed: %s" % (ev.get("id"), e)) from e


def _paid_invoices_in(start, end):
    """Invoices PAID in [start, end), oldest payment first. Stripe can only
    filter the listing by `created`, so list a window that reaches back
    AFFILIATE_PAID_LOOKBACK_DAYS before the month and keep the invoices whose
    status_transitions.paid_at falls inside it. An invoice created in March
    and paid late in May is therefore counted in MAY - and only there."""
    lookback = int(getattr(config, "AFFILIATE_PAID_LOOKBACK_DAYS", 120) or 0)
    listing = stripe.Invoice.list(
        status="paid",
        created={"gte": int((start - dt.timedelta(days=lookback)).timestamp()),
                 "lt": int(end.timestamp())},
        limit=100,
        expand=["data.discounts"],
    )
    out = []
    for inv in listing.auto_paging_iter():
        invd = inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)
        if (invd.get("status") or "paid") != "paid":
            continue                                   # failed / open payments never count
        paid_at = _invoice_paid_at(invd)
        if paid_at is None or not (start <= paid_at < end):
            continue
        out.append(invd)
    out.sort(key=lambda i: (_invoice_paid_at(i), i.get("id") or ""))
    return out


def _ref_view(value):
    """Normalize a referrals_by_sub value: an AffiliateReferral row (or any
    duck-typed object) is used as-is; a bare affiliate id (legacy callers)
    becomes a snapshot-less view."""
    if value is None or hasattr(value, "affiliate_id"):
        return value
    return SimpleNamespace(affiliate_id=value)


def _compute(affiliates, year: int, month: int, referrals_by_sub=None, *,
             terms_by_id=None, ledger=None, discovered=None, skipped=None) -> list[dict]:
    """Pure core (testable): given duck-typed partner objects, read Stripe for
    the month and return per-(partner, currency) totals plus every line.

    referrals_by_sub: {stripe_subscription_id: referral} - the PERSISTED
    attribution and checkout snapshot (terms_id / terms, offer_type,
    discount_pct, first_paid_at, year_anchor_at, source). A referral wins over
    the coupon; the coupon is the fallback for a sale with no referral row.
    A bare affiliate id is accepted in place of a referral object.

    terms_by_id: {terms_id: terms}. ledger: a LedgerView, or a callable
    (invoice_ids) -> LedgerView, of already-persisted lines. discovered: an
    optional dict the engine fills with {subscription_id: {"first_paid_at",
    "year_anchor_at"}} for referrals whose clock it had to derive from Stripe
    (upsert_month persists those). Only clocks READ from Stripe are reported;
    a clock the engine had to guess from the invoice in hand is used for this
    run but never persisted. skipped: an optional list the engine appends
    {"source", "id", "error"} to for every invoice / reversal it could not
    price because a Stripe lookup FAILED (StripeLookupError). A skipped source
    gets no line at all - never a wrong one - and is picked up by the next
    run.

    Two passes:
      1. every invoice PAID in the month -> a sale line (first_year / promo /
         renewal / lapsed), priced by classify_invoice from the referral
         snapshot;
      2. every refund / money-withdrawing dispute CREATED in the month -> a
         NEGATIVE line at the ORIGINAL sale line's rate and formula, pro-rated
         by the share of the payment that was reversed and capped at the
         original commission (can make a month negative; upsert_month carries
         that forward). The pass also follows STATUS CHANGES of earlier
         events (see _month_reversals): a dispute that is later won, or a
         pending refund that later fails, gets a POSITIVE line equal to the
         booked clawback (source_id '<id>:won' / '<id>:failed', same kind,
         detail outcome 'won' / 'failed'); an inquiry that later escalates is
         clawed back when it is first seen as a real dispute.

    Each result dict: affiliate_id, code, name, email, payout_email,
    payout_method, notes, currency, gross_revenue (paid less tax, payable
    lines), commission_amount (payable lines only), held_amount (lines held
    for a paused partner), lapsed_count, period_start/end, detail (ALL lines,
    each with kind + state). Sorted by commission desc.
    """
    start, end, period_start, period_end = _month_window(year, month)

    by_id = {str(a.id): a for a in affiliates}
    if not by_id:
        return []
    by_coupon = {}
    for a in affiliates:
        for attr in ("stripe_coupon_id", "stripe_coupon_id_monthly"):
            cid = getattr(a, attr, None)
            if cid:
                by_coupon[cid] = a
    refs = {sub: _ref_view(v) for sub, v in (referrals_by_sub or {}).items()}

    acc: dict = {}
    unattributed: list = []
    clock_cache: dict = {}      # subscription/customer key -> {"first_paid_at", "year_anchor_at"}
    # Activity rule input: first successful payment of every NEW customer.
    first_paid: dict = {}
    unresolved: dict = {}
    for sub, r in refs.items():
        aid = str(getattr(r, "affiliate_id", ""))
        fp = _utc(getattr(r, "first_paid_at", None))
        if getattr(r, "source", None) == "return":
            continue                                  # a returning customer is not a NEW one
        if fp is not None:
            first_paid.setdefault(aid, []).append(fp)
        else:
            unresolved.setdefault(aid, []).append((sub, r))

    def attribute(invd):
        """(partner, referral|None): the persisted referral wins; else the
        partner coupon on the invoice (fallback / corroboration)."""
        sub_id = _invoice_subscription_id(invd)
        if sub_id and sub_id in refs:
            ref = refs[sub_id]
            hit = by_id.get(str(ref.affiliate_id))
            if hit is not None:
                return hit, ref
        matches = [by_coupon[cid] for cid in _invoice_coupon_ids(invd) if cid in by_coupon]
        if matches:
            if len({str(m.id) for m in matches}) > 1:
                log.warning("invoice %s carries %d affiliate coupons; attributing "
                            "to the first (%s) - needs review", invd.get("id"),
                            len(matches), matches[0].code)
            return matches[0], None
        return None, None

    def is_self_referral(aff, invd):
        cust_email = (invd.get("customer_email") or "").strip().lower()
        aff_email = (getattr(aff, "email", None) or "").strip().lower()
        return bool(aff_email and cust_email and cust_email == aff_email)

    def clock(aff, ref, invd):
        """The referral's commission clock: when the customer first paid and
        where commission year 1 starts. Read from the referral row; derived
        from Stripe (earliest paid invoice > $0 of the subscription) when the
        row has not been stamped yet, else from this very invoice."""
        sub_id = _invoice_subscription_id(invd)
        key = sub_id or ("cust", invd.get("customer"), str(aff.id))
        if key in clock_cache:
            return clock_cache[key]
        fp = _utc(getattr(ref, "first_paid_at", None))
        anchor = _utc(getattr(ref, "year_anchor_at", None))
        if fp is None or anchor is None:
            # A Stripe failure raises StripeLookupError: the caller skips the
            # invoice. It must never fall through to the guess below.
            found = _first_paid_invoice(invd.get("customer"), subscription_id=sub_id,
                                        coupon_id=None if sub_id else aff.stripe_coupon_id)
            guessed = found is None
            if guessed:
                # Stripe answered "no earlier paid invoice": this invoice is
                # the first. Good enough to price it now, not to persist.
                found = {"paid_at": _invoice_paid_at(invd),
                         "service_start": _invoice_service_start(invd)}
            derived_fp = fp is None
            fp = fp or found["paid_at"]
            anchor = anchor or found["service_start"] or fp
            if derived_fp and getattr(ref, "source", None) != "return":
                first_paid.setdefault(str(aff.id), []).append(fp)
                unresolved[str(aff.id)] = [x for x in unresolved.get(str(aff.id), [])
                                           if x[0] != sub_id]
            if discovered is not None and sub_id and ref is not None and not guessed:
                discovered[sub_id] = {"first_paid_at": fp, "year_anchor_at": anchor}
        clock_cache[key] = {"first_paid_at": fp, "year_anchor_at": anchor}
        return clock_cache[key]

    def activity_fn(aff):
        aid = str(aff.id)

        def is_active(at, months):
            if _is_active_at(first_paid.get(aid, ()), at, months):
                return True
            # Referrals whose first payment was never stamped (missed webhook):
            # look them up once before declaring the partner lapsed. A Stripe
            # failure raises StripeLookupError with the referral left
            # unresolved: "could not ask" is never booked as "lapsed".
            pending = unresolved.get(aid, [])
            if not pending:
                return False
            while pending:
                sub, r = pending[0]
                found = _first_paid_invoice(getattr(r, "stripe_customer_id", None),
                                            subscription_id=sub)
                pending.pop(0)
                if found:
                    first_paid.setdefault(aid, []).append(found["paid_at"])
                    if discovered is not None and sub not in discovered:
                        discovered[sub] = {"first_paid_at": found["paid_at"],
                                           "year_anchor_at": (_utc(getattr(r, "year_anchor_at", None))
                                                              or found["service_start"])}
            return _is_active_at(first_paid.get(aid, ()), at, months)
        return is_active

    def price(aff, ref, invd):
        c = clock(aff, ref, invd)
        return classify_invoice(invd, ref, _resolve_terms(ref, aff, terms_by_id),
                                c["year_anchor_at"], activity_fn(aff))

    def entry_for(aff, currency):
        key = (str(aff.id), currency)
        entry = acc.get(key)
        if entry is None:
            entry = {
                "affiliate_id": str(aff.id),
                "code": aff.code,
                "name": aff.name,
                "email": getattr(aff, "email", None),
                "payout_email": getattr(aff, "payout_email", None),
                "payout_method": getattr(aff, "payout_method", None),
                "notes": getattr(aff, "notes", None),
                "status": getattr(aff, "status", None),
                "currency": currency,
                "gross_revenue": Decimal("0.00"),
                "commission_amount": Decimal("0.00"),
                "held_amount": Decimal("0.00"),
                "lapsed_count": 0,
                "period_start": period_start,
                "period_end": period_end,
                "detail": [],
            }
            acc[key] = entry
        return entry

    def add_line(aff, ref, invd, fields, extra):
        currency = (invd.get("currency") or "usd").lower()
        entry = entry_for(aff, currency)
        amount = _dec(fields["amount"])
        state, hold = _state_for(aff)
        if fields["kind"] == "lapsed":
            state, hold = "lapsed", None
        ref_terms = _resolve_terms(ref, aff, terms_by_id)
        line = {
            "affiliate_id": str(aff.id),
            "kind": fields["kind"],
            "state": state,
            "hold_reason": hold,
            "source_id": extra.get("source_id") or invd.get("id"),
            "invoice": invd.get("id"),
            "customer": invd.get("customer"),
            "subscription": _invoice_subscription_id(invd),
            "referral_id": (str(ref.id) if getattr(ref, "id", None) else None),
            "terms_id": getattr(ref_terms, "id", None),
            "terms_version": getattr(ref_terms, "version", None),
            "offer_type": fields.get("offer_type"),
            "currency": currency,
            "interval": _invoice_interval(invd) or getattr(ref, "billing_interval", None),
            "service_period_start": _iso(fields.get("service_period_start")),
            "event_at": _iso(extra.get("event_at") or fields.get("paid_at")),
            "year_number": fields.get("year_number"),
            "net_paid_cents": int(fields["net_paid_cents"]),
            "basis_cents": int(fields["basis_cents"]),
            "basis": str((Decimal(int(fields["basis_cents"])) / _HUNDRED).quantize(_CENTS)),
            "rate_pct": str(_dec(fields["rate_pct"])),
            "amount": str(amount),
            "commission": str(amount.quantize(_CENTS, rounding=ROUND_HALF_UP)),
            "period_month": period_start.isoformat(),
        }
        for k in ("discount_pct", "list_cents", "guard", "forfeited",
                  "amount_paid_cents", "tax_cents"):
            if fields.get(k) is not None:
                line[k] = str(fields[k]) if isinstance(fields[k], Decimal) else fields[k]
        line.update({k: v for k, v in extra.items() if k not in ("source_id", "event_at")})
        if state == "estimated":
            entry["gross_revenue"] += Decimal(int(fields["net_paid_cents"])) / _HUNDRED
            entry["commission_amount"] += amount     # unrounded; total rounded once
        elif state == "held":
            entry["held_amount"] += amount
        elif state == "lapsed":
            entry["lapsed_count"] += 1
        entry["detail"].append(line)
        return line

    def skip(source, sid, err):
        """A Stripe lookup failed: leave the source out of this run entirely."""
        log.warning("compute %04d-%02d: %s %s SKIPPED for this run (not booked, retried on "
                    "the next run): %s", year, month, source, sid, err)
        if skipped is not None:
            skipped.append({"source": source, "id": sid, "error": str(err)})

    # --- pass 1: payments ---------------------------------------------------
    invoices = _paid_invoices_in(start, end)
    # Deliberately NOT caught: if Stripe can't list refunds/disputes, the
    # compute fails rather than over-paying with the clawback silently skipped.
    reversal_events = []
    for ev in _month_reversals(start, end):
        try:
            invd = _invoice_for_reversal(ev)
        except StripeLookupError as e:
            skip(ev["kind"], ev["id"], e)
            continue
        if invd:
            reversal_events.append((ev, invd))
    book = ledger
    if callable(ledger):
        book = ledger([i.get("id") for i in invoices] + [i.get("id") for _, i in reversal_events])
    book = book or LedgerView()

    attributed = []
    for invd in invoices:
        aff, ref = attribute(invd)
        if aff is None:
            # A discounted invoice we can't attribute to any partner -> surface
            # it rather than silently dropping money.
            if _invoice_coupon_ids(invd):
                unattributed.append(invd.get("id"))
            continue
        if is_self_referral(aff, invd):
            log.info("affiliate %s: skipping self-referral invoice %s",
                     aff.code, invd.get("id"))
            continue
        if int(invd.get("amount_paid") or 0) <= 0:
            continue                                  # trial / $0 invoice: never starts the clock
        attributed.append((aff, ref, invd))
    # Start every clock BEFORE pricing, so a first payment earlier in the month
    # counts toward the activity rule of a renewal paid later in it.
    priceable = []
    for aff, ref, invd in attributed:
        try:
            clock(aff, ref, invd)
        except StripeLookupError as e:
            skip("invoice", invd.get("id"), e)
            continue
        priceable.append((aff, ref, invd))
    attributed = priceable

    def show_persisted(aff, persisted):
        """A line already in the ledger is never re-priced. Show it in the
        month it was booked in, and only there (a source is counted once)."""
        if persisted.get("period_month") != period_start.isoformat():
            return
        entry = entry_for(aff, persisted.get("currency") or "usd")
        amt = _dec(persisted.get("amount"))
        if persisted.get("state") in ("pending", "paid"):
            entry["gross_revenue"] += Decimal(int(persisted.get("net_paid_cents") or 0)) / _HUNDRED
            entry["commission_amount"] += amt
        elif persisted.get("state") == "held":
            entry["held_amount"] += amt
        elif persisted.get("state") == "lapsed":
            entry["lapsed_count"] += 1
        entry["detail"].append(persisted)

    this_run = {}       # (affiliate_id, invoice_id) -> line (sale lines of this run)
    for aff, ref, invd in attributed:
        persisted = book.sale(aff.id, invd.get("id"))
        if persisted is not None:
            show_persisted(aff, persisted)
            continue
        try:
            fields = price(aff, ref, invd)
        except StripeLookupError as e:
            skip("invoice", invd.get("id"), e)
            continue
        if fields is None:
            continue
        this_run[(str(aff.id), invd.get("id"))] = add_line(aff, ref, invd, fields, {
            "created": invd.get("created"),
        })

    # --- pass 2: refunds + disputes (clawback) ------------------------------
    reversed_now: dict = {}
    for ev, invd in reversal_events:
        aff, ref = attribute(invd)
        if aff is None or is_self_referral(aff, invd):
            continue
        booked = book.line(aff.id, ev["id"])
        if ev.get("undo"):
            # Dispute WON / refund FAILED: the money came back, so give the
            # booked clawback back - once (keyed on '<id>:won' / ':failed').
            # Nothing was booked -> nothing to give back.
            if booked is not None:
                show_persisted(aff, booked)
            undo_id = undo_source_id(ev)
            given_back = book.line(aff.id, undo_id)
            if given_back is not None:
                show_persisted(aff, given_back)
                continue
            claw = _dec(booked.get("amount")) if booked is not None else Decimal("0")
            if claw >= 0 or booked.get("state") == "void":
                continue
            add_line(aff, ref, invd, {
                "kind": ev["kind"],
                "amount": -claw,
                "basis_cents": -int(booked.get("basis_cents") or 0),
                "net_paid_cents": -int(booked.get("net_paid_cents") or 0),
                "rate_pct": booked.get("rate_pct"),
                "year_number": booked.get("year_number"),
                "offer_type": booked.get("offer_type"),
                "service_period_start": _from_iso(booked.get("service_period_start")),
            }, {
                "source_id": undo_id,
                ev["kind"]: ev["id"],
                "outcome": "won" if ev["kind"] == "dispute" else "failed",
                "restores": ev["id"],
                "reverses_kind": booked.get("reverses_kind"),
                "created": ev.get("created"),
                "event_at": min(end - dt.timedelta(seconds=1),
                                max(start, dt.datetime.now(dt.timezone.utc))),
            })
            continue
        if booked is not None:
            show_persisted(aff, booked)               # this reversal is already booked
            continue
        amount_paid = int(invd.get("amount_paid") or 0)
        if amount_paid <= 0:
            continue
        # The ORIGINAL line: the persisted one, else this run's, else priced
        # now from the same immutable referral snapshot.
        orig = book.sale(aff.id, invd.get("id")) or this_run.get((str(aff.id), invd.get("id")))
        if orig is None:
            try:
                fields = price(aff, ref, invd)
            except StripeLookupError as e:
                skip(ev["kind"], ev["id"], e)
                continue
            if fields is None:
                continue
            orig = {"kind": fields["kind"], "amount": fields["amount"],
                    "basis_cents": fields["basis_cents"], "net_paid_cents": fields["net_paid_cents"],
                    "rate_pct": fields["rate_pct"], "year_number": fields.get("year_number"),
                    "offer_type": fields.get("offer_type"), "state": None,
                    "service_period_start": fields.get("service_period_start")}
        orig_amount = _dec(orig.get("amount"))
        if orig_amount <= 0 or orig.get("state") in ("void", "lapsed"):
            continue                                  # nothing was earned -> nothing to take back
        rev_cents = min(int(ev["amount"]), amount_paid)
        share = Decimal(rev_cents) / Decimal(amount_paid)
        key = (str(aff.id), invd.get("id"))
        already = book.reversed_amount(aff.id, invd.get("id")) + reversed_now.get(key, Decimal("0"))
        take = min(orig_amount * share, max(Decimal("0"), orig_amount - already))
        if take <= 0:
            continue
        reversed_now[key] = reversed_now.get(key, Decimal("0")) + take
        fraction = take / orig_amount
        add_line(aff, ref, invd, {
            "kind": ev["kind"],
            "amount": -take,
            "basis_cents": -_cents(Decimal(int(orig.get("basis_cents") or 0)) * fraction),
            "net_paid_cents": -_cents(Decimal(int(orig.get("net_paid_cents") or 0)) * fraction),
            "rate_pct": orig.get("rate_pct"),
            "year_number": orig.get("year_number"),
            "offer_type": orig.get("offer_type"),
            "service_period_start": orig.get("service_period_start"),
        }, {
            "source_id": ev["id"],
            ev["kind"]: ev["id"],
            "reverses_kind": orig.get("kind"),
            "reversed_cents": rev_cents,
            "created": ev.get("created"),
            # A dispute first seen after its own month (an escalated inquiry)
            # is dated into THIS month, where it is booked.
            "event_at": max(start, _utc(ev.get("created")) or start),
        })

    if unattributed:
        log.warning("compute %04d-%02d: %d discounted invoice(s) with NO partner "
                    "attribution (neither referral nor coupon) - unpaid, needs review: %s",
                    year, month, len(unattributed), unattributed[:25])

    out = []
    for entry in acc.values():
        # Quantize the TOTALS once (avoids per-invoice rounding drift).
        entry["gross_revenue"] = entry["gross_revenue"].quantize(_CENTS)
        entry["commission_amount"] = entry["commission_amount"].quantize(_CENTS, rounding=ROUND_HALF_UP)
        entry["held_amount"] = entry["held_amount"].quantize(_CENTS, rounding=ROUND_HALF_UP)
        out.append(entry)
    out.sort(key=lambda e: e["commission_amount"], reverse=True)
    return out


# Hold reasons the engine releases on its own (see _release_lines). 'terminated'
# is the pre-fix reason for a partner terminated WITHOUT cause.
AUTO_RELEASE_HOLD_REASONS = ("paused", "terminated")

# external_ref of a payout row voided by a termination for cause.
FORFEIT_REF = "forfeited:terminated_for_cause"


def final_balance_due(affiliate) -> bool:
    """True for a partner terminated WITHOUT cause: their final balance is
    paid regardless of the payout minimum (agreement 5.3 / 11.3)."""
    return (getattr(affiliate, "status", None) == "terminated"
            and not getattr(affiliate, "terminated_for_cause", False))


def carry_ref(period_start) -> str:
    """external_ref stamped on a negative row that was folded into a later
    month's payout (clawback carry-forward)."""
    return "carried:%s" % period_start.strftime("%Y-%m")


def _as_uuid(v):
    import uuid as _uuid
    return v if isinstance(v, _uuid.UUID) else _uuid.UUID(str(v))


def payout_minimum() -> Decimal:
    """The payout minimum (small-balance hold) in currency units, from
    config.AFFILIATE_PAYOUT_MINIMUM_CENTS (default 5000 = $50.00)."""
    cents = int(getattr(config, "AFFILIATE_PAYOUT_MINIMUM_CENTS", 5000) or 0)
    return (Decimal(max(cents, 0)) / _HUNDRED).quantize(_CENTS)


def _apply_carry(session, rows, period_start):
    """Carry-forward of balances that cannot be paid on their own.

    Clawback: a month whose refunds/disputes outweigh its sales ends NEGATIVE;
    that debt is folded into the affiliate's next month with activity in the
    same currency (so we never pay out while they owe us). Payout minimum: a
    month whose total is BELOW payout_minimum() is not paid either; it rolls
    into the next month with activity the same way.

    For each computed (affiliate, currency) row, collect EARLIER rows below
    the minimum that are still pending (or already carried into THIS period by
    a previous run - keeps re-runs idempotent), add them to this row's
    commission, record them in detail["carry_in"], and mark them void with
    external_ref carried:<this period>. Their ledger lines are paid together
    with the row they were carried into (sync_line_states). Mutates `rows`;
    returns the carried row objects."""
    from models import AffiliatePayout
    ref = carry_ref(period_start)
    floor = payout_minimum()
    carried = []
    for r in rows:
        prior = (session.query(AffiliatePayout)
                 .filter(AffiliatePayout.affiliate_id == _as_uuid(r["affiliate_id"]),
                         AffiliatePayout.currency == r["currency"],
                         AffiliatePayout.period_start < period_start,
                         AffiliatePayout.commission_amount < floor,
                         ((AffiliatePayout.status == "pending")
                          | ((AffiliatePayout.status == "void")
                             & (AffiliatePayout.external_ref == ref))))
                 .order_by(AffiliatePayout.period_start).all())
        if not prior:
            continue
        carry = sum((_dec(p.commission_amount) for p in prior), Decimal("0.00"))
        r["commission_amount"] = (r["commission_amount"] + carry).quantize(_CENTS)
        r["carry_in"] = [{"period": p.period_start.isoformat(),
                          "amount": str(_dec(p.commission_amount).quantize(_CENTS))} for p in prior]
        for p in prior:
            p.status = "void"
            p.external_ref = ref
            carried.append(p)
    return carried


def _dialect_insert(session, table):
    """INSERT construct with ON CONFLICT support for the session's dialect
    (Postgres in every environment; SQLite in the hermetic ledger tests)."""
    if session.get_bind().dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:
        from sqlalchemy.dialects.postgresql import insert as _insert
    return _insert(table)


def sync_line_states(session) -> int:
    """Move ledger lines to 'paid' once the payout row that aggregated them is
    marked paid - including the lines of earlier rows that were CARRIED into
    that paid row (negative months and months below the payout minimum, see
    _apply_carry). Called by upsert_month; call it after marking a payout paid
    too. Returns the number of lines moved. Does not commit."""
    from models import AffiliateCommissionLine, AffiliatePayout
    paid = (session.query(AffiliatePayout.id, AffiliatePayout.affiliate_id,
                          AffiliatePayout.currency, AffiliatePayout.period_start)
            .filter(AffiliatePayout.status == "paid").all())
    if not paid:
        return 0
    carried: dict = {}
    for c in (session.query(AffiliatePayout.id, AffiliatePayout.affiliate_id,
                            AffiliatePayout.currency, AffiliatePayout.period_start,
                            AffiliatePayout.external_ref)
              .filter(AffiliatePayout.status == "void",
                      AffiliatePayout.external_ref.like("carried:%")).all()):
        carried.setdefault((str(c.affiliate_id), c.currency, c.external_ref), []).append(c)
    ids = {p.id for p in paid}
    frontier = list(paid)
    while frontier:                                 # a carried row may itself carry earlier ones
        nxt = []
        for p in frontier:
            for c in carried.get((str(p.affiliate_id), p.currency, carry_ref(p.period_start)), ()):
                if c.id not in ids:
                    ids.add(c.id)
                    nxt.append(c)
        frontier = nxt
    return (session.query(AffiliateCommissionLine)
            .filter(AffiliateCommissionLine.payout_id.in_(ids),
                    AffiliateCommissionLine.state == "pending")
            .update({"state": "paid"}, synchronize_session=False))


def _persist_lines(session, rows, period_start, frozen) -> int:
    """INSERT the month's computed lines into the ledger, insert-once on
    (affiliate_id, source_id): a rerun, a webhook retry or a second operator
    click can never double count, and an existing line is never re-priced.
    A payable line of a FROZEN (paid / void / locked) payout month gets no
    payable_month yet - the next open month picks it up."""
    from models import AffiliateCommissionLine
    tbl = AffiliateCommissionLine.__table__
    inserted = 0
    for r in rows:
        for ln in r["detail"]:
            if ln.get("persisted"):
                continue
            state = "pending" if ln["state"] == "estimated" else ln["state"]
            payable = (period_start if state == "pending"
                       and (r["affiliate_id"], r["currency"]) not in frozen else None)
            core = {"affiliate_id", "kind", "state", "hold_reason", "source_id", "invoice",
                    "customer", "subscription", "referral_id", "currency", "interval",
                    "service_period_start", "event_at", "year_number", "net_paid_cents",
                    "basis_cents", "basis", "rate_pct", "amount", "commission", "period_month"}
            stmt = _dialect_insert(session, tbl).values(
                affiliate_id=_as_uuid(ln["affiliate_id"]),
                referral_id=_as_uuid(ln["referral_id"]) if ln.get("referral_id") else None,
                kind=ln["kind"],
                source_id=ln["source_id"],
                stripe_invoice_id=ln.get("invoice"),
                stripe_reversal_id=((ln.get(ln["kind"]) or ln["source_id"])
                                    if ln["kind"] in REVERSAL_KINDS else None),
                stripe_customer_id=ln.get("customer"),
                stripe_subscription_id=ln.get("subscription"),
                currency=ln["currency"],
                billing_interval=ln.get("interval"),
                service_period_start=_utc(dt.datetime.fromisoformat(ln["service_period_start"]))
                if ln.get("service_period_start") else None,
                event_at=_utc(dt.datetime.fromisoformat(ln["event_at"])) if ln.get("event_at") else None,
                year_number=ln.get("year_number"),
                net_paid_cents=ln["net_paid_cents"],
                basis_cents=ln["basis_cents"],
                rate_pct=_dec(ln["rate_pct"]),
                amount=_dec(ln["amount"]),
                state=state,
                hold_reason=ln.get("hold_reason"),
                period_month=period_start,
                payable_month=payable,
                detail={k: v for k, v in ln.items() if k not in core},
            ).on_conflict_do_nothing(index_elements=["affiliate_id", "source_id"])
            inserted += session.execute(stmt).rowcount or 0
    return inserted


def _release_lines(session, period_start, frozen) -> None:
    """Held -> payable. A line held while its partner was PAUSED becomes
    pending once the partner is active again OR is terminated without cause
    (agreement 5.3 / 11.3: that commission stays payable); lines of a partner
    terminated for cause are forfeited (void). A line held for any OTHER
    reason (an explicit operator hold) is only released by
    release_held_lines. Any pending line without a payout month
    (just released, or found after its own month was frozen) is assigned to
    this month unless this month's payout row is frozen too."""
    from models import Affiliate, AffiliateCommissionLine as L
    active = [a.id for a in session.query(Affiliate.id)
              .filter((Affiliate.status == "active")
                      | ((Affiliate.status == "terminated")
                         & Affiliate.terminated_for_cause.isnot(True))).all()]
    forfeited = [a.id for a in session.query(Affiliate.id)
                 .filter(Affiliate.terminated_for_cause.is_(True)).all()]
    if forfeited:
        (session.query(L).filter(L.affiliate_id.in_(forfeited), L.state.in_(("held", "pending")),
                                 L.payout_id.is_(None))
         .update({"state": "void", "hold_reason": "terminated_for_cause", "payable_month": None},
                 synchronize_session=False))
    if active:
        (session.query(L).filter(L.affiliate_id.in_(active), L.state == "held",
                                 L.hold_reason.in_(AUTO_RELEASE_HOLD_REASONS))
         .update({"state": "pending", "hold_reason": None}, synchronize_session=False))
    session.flush()
    for ln in (session.query(L).filter(L.state == "pending", L.payable_month.is_(None),
                                       L.period_month <= period_start).all()):
        if (str(ln.affiliate_id), ln.currency) not in frozen:
            ln.payable_month = period_start
    session.flush()


def upsert_month(session, year: int, month: int) -> list:
    """Compute the month, persist its ledger lines and (re)build the pending
    affiliate_payouts rows from the ledger.

    Lines are INSERT-ONCE on (affiliate_id, source_id) - see _persist_lines -
    so a re-run only ADDS what is new (late-settling invoices, new refunds)
    and never re-prices an existing line. The payout row of each
    (affiliate, currency) is the sum of the ledger lines whose payable_month
    is this month, idempotent on (affiliate_id, period_start, currency). A
    still-PENDING, UNLOCKED row is refreshed; rows that are paid, void, or
    LOCKED (hand-adjusted) are frozen. Earlier negative (clawback) months are
    carried into this month - see _apply_carry. Returns the AffiliatePayout
    rows for the period."""
    from models import (Affiliate, AffiliateCommissionLine, AffiliatePayout,
                        AffiliateReferral)

    discovered: dict = {}
    skipped: list = []
    rows = compute_month(session, year, month, discovered=discovered, skipped=skipped)
    if skipped:
        log.warning("upsert %04d-%02d: %d source(s) skipped after a Stripe lookup failure - "
                    "nothing was booked for them; commit the month again: %s",
                    year, month, len(skipped), [x["id"] for x in skipped][:25])
    _, _, period_start, period_end = _month_window(year, month)

    # Persist the commission clocks the engine had to derive from Stripe.
    for sub_id, found in discovered.items():
        ref = (session.query(AffiliateReferral)
               .filter(AffiliateReferral.stripe_subscription_id == sub_id).first())
        if ref is None:
            continue
        if ref.first_paid_at is None:
            ref.first_paid_at = found["first_paid_at"]
        if ref.year_anchor_at is None:
            ref.year_anchor_at = found["year_anchor_at"]

    sync_line_states(session)
    # Only (re)write rows we are allowed to: a frozen (paid/void/locked) row
    # for this period keeps its numbers, so new lines and carried debt wait
    # for the next open month instead.
    frozen = {(str(p.affiliate_id), p.currency) for p in
              session.query(AffiliatePayout)
              .filter(AffiliatePayout.period_start == period_start,
                      (AffiliatePayout.status != "pending") | AffiliatePayout.locked.is_(True))}
    _persist_lines(session, rows, period_start, frozen)
    _release_lines(session, period_start, frozen)

    L = AffiliateCommissionLine
    groups: dict = {}
    for ln in (session.query(L).filter(L.payable_month == period_start,
                                       L.state.in_(("pending", "paid")))
               .order_by(L.event_at, L.id).all()):
        groups.setdefault((str(ln.affiliate_id), ln.currency), []).append(ln)
    info: dict = {}
    for ln in (session.query(L).filter(L.period_month == period_start,
                                       L.state.in_(("held", "lapsed", "void"))).all()):
        info.setdefault((str(ln.affiliate_id), ln.currency), []).append(ln)

    agg = []
    for (aid, currency), lines in groups.items():
        if (aid, currency) in frozen:
            continue
        agg.append({
            "affiliate_id": aid, "currency": currency,
            "gross_revenue": (sum((Decimal(int(l.net_paid_cents or 0)) for l in lines), Decimal("0"))
                              / _HUNDRED).quantize(_CENTS),
            "commission_amount": sum((_dec(l.amount) for l in lines), Decimal("0"))
            .quantize(_CENTS, rounding=ROUND_HALF_UP),
            "lines": lines,
        })
    _apply_carry(session, agg, period_start)

    tbl = AffiliatePayout.__table__
    now = dt.datetime.now(dt.timezone.utc)
    for r in agg:
        detail = {"lines": [_line_dict_from_row(l) for l in r["lines"]]}
        other = info.get((r["affiliate_id"], r["currency"]))
        if other:
            detail["not_payable"] = [_line_dict_from_row(l) for l in other]
        if r.get("carry_in"):
            detail["carry_in"] = r["carry_in"]
        stmt = _dialect_insert(session, tbl).values(
            affiliate_id=_as_uuid(r["affiliate_id"]),
            period_start=period_start,
            period_end=period_end,
            currency=r["currency"],
            gross_revenue=r["gross_revenue"],
            commission_amount=r["commission_amount"],
            status="pending",
            detail=detail,
        ).on_conflict_do_update(
            # Refresh a still-PENDING, UNLOCKED row so a re-run picks up
            # late-settling lines. Rows marked paid/void, OR locked (the
            # operator hand-adjusted them), are FROZEN - the WHERE guard
            # leaves them untouched.
            index_elements=["affiliate_id", "period_start", "currency"],
            set_={
                "gross_revenue": r["gross_revenue"],
                "commission_amount": r["commission_amount"],
                "detail": detail,
                "computed_at": now,
            },
            where=((tbl.c.status == "pending") & (tbl.c.locked.is_(False))),
        )
        session.execute(stmt)
        payout = (session.query(AffiliatePayout)
                  .filter(AffiliatePayout.affiliate_id == _as_uuid(r["affiliate_id"]),
                          AffiliatePayout.period_start == period_start,
                          AffiliatePayout.currency == r["currency"]).first())
        if payout is not None:
            for l in r["lines"]:
                l.payout_id = payout.id
    session.commit()

    return (session.query(AffiliatePayout)
            .filter(AffiliatePayout.period_start == period_start)
            .order_by(AffiliatePayout.commission_amount.desc())
            .all())


def active_affiliate_by_code(session, raw):
    """The ACTIVE Affiliate for a referral code (any case), or None."""
    from models import Affiliate
    code = normalize_code(raw or "")
    if not CODE_RE.match(code):
        return None
    return (session.query(Affiliate)
            .filter(Affiliate.code == code, Affiliate.status == "active").first())


def record_click(session, affiliate_id, day=None) -> None:
    """Atomically +1 the affiliate's visit counter for `day` (UTC today).
    Commits. Callers treat failures as non-fatal (a count must never break a
    landing page)."""
    from models import AffiliateClick
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    day = day or dt.datetime.now(dt.timezone.utc).date()
    tbl = AffiliateClick.__table__
    stmt = pg_insert(tbl).values(affiliate_id=affiliate_id, day=day, clicks=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=["affiliate_id", "day"],
        set_={"clicks": tbl.c.clicks + 1})
    session.execute(stmt)
    session.commit()


def record_signup_referral(session, user, raw_code, sub_cookie=None, ip=None) -> bool:
    """First-touch: stamp a brand-new user with the affiliate whose tw_ref
    code they arrived with. Never overwrites an existing stamp, skips
    self-referral and inactive codes. Commits; returns True if stamped.
    `sub_cookie` (tw_ref_sub) adds the partner's sub-link tag to the stamp
    when it belongs to that same partner; it never affects who is credited."""
    if user is None or getattr(user, "referred_by_affiliate_id", None):
        return False
    aff = active_affiliate_by_code(session, raw_code)
    if aff is None:
        return False
    if (aff.email or "").strip().lower() == (user.email or "").strip().lower():
        return False
    user.referred_by_affiliate_id = aff.id
    user.referred_at = dt.datetime.now(dt.timezone.utc)
    user.referred_sub = sub_from_cookie(sub_cookie, aff.code)
    user.referred_ip_hash = hash_ip(ip)     # fraud signals only; never the raw IP
    session.commit()
    return True


def funnel_for_affiliate(session, affiliate_id, days: int = 30) -> dict:
    """Anonymized top-of-funnel counts for the partner dashboard (no customer
    identities): link visits and signups in the last `days` days and all-time,
    users currently in their free trial, and paying subscriptions credited
    (affiliate_referrals)."""
    from sqlalchemy import func as safunc
    from models import AffiliateClick, AffiliateReferral, User
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=days)
    clicks_recent = (session.query(safunc.coalesce(safunc.sum(AffiliateClick.clicks), 0))
                     .filter(AffiliateClick.affiliate_id == affiliate_id,
                             AffiliateClick.day >= since.date()).scalar())
    clicks_total = (session.query(safunc.coalesce(safunc.sum(AffiliateClick.clicks), 0))
                    .filter(AffiliateClick.affiliate_id == affiliate_id).scalar())
    signups_q = session.query(User).filter(User.referred_by_affiliate_id == affiliate_id)
    signups_total = signups_q.count()
    signups_recent = signups_q.filter(User.referred_at >= since).count()
    in_trial = signups_q.filter(User.reverse_trial_ends_at > now).count()
    paying = (session.query(AffiliateReferral)
              .filter(AffiliateReferral.affiliate_id == affiliate_id).count())
    return {"days": days,
            "clicks_recent": int(clicks_recent or 0), "clicks_total": int(clicks_total or 0),
            "signups_recent": signups_recent, "signups_total": signups_total,
            "in_trial": in_trial, "paying_total": paying}


def find_or_link_affiliate(session, user):
    """The linked, non-terminated Affiliate row for `user`, or None.

    If the user has no linked row yet, AUTO-LINK by exact case-insensitive email
    match against an unlinked, non-terminated affiliate (dashboard spec 4.1:
    WorkOS verifies the email; affiliate emails are operator-entered). Commits
    the link + an `affiliate_linked` audit row. Shared by the portal and the
    /account page so the dashboard card shows on the FIRST account visit
    (before this lived only in the portal, so an affiliate who never typed
    /account/affiliate never got linked and never saw the card)."""
    if user is None:
        return None
    from sqlalchemy import func as safunc
    from models import Affiliate, AuditLog
    aff = (session.query(Affiliate)
           .filter(Affiliate.user_id == user.id,
                   Affiliate.status != "terminated").first())
    if aff is not None or not getattr(user, "email", None):
        return aff
    candidate = (session.query(Affiliate)
                 .filter(safunc.lower(Affiliate.email) == user.email.strip().lower(),
                         Affiliate.user_id.is_(None),
                         Affiliate.status != "terminated").first())
    if candidate is None:
        return None
    candidate.user_id = user.id
    session.add(AuditLog(actor_user_id=user.id, action="affiliate_linked",
                         details={"affiliate_id": str(candidate.id),
                                  "code": candidate.code, "via": "email_match"}))
    session.commit()
    log.info("affiliate auto-linked: %s -> user %s", candidate.code, user.id)
    return candidate


def compute_for_affiliate(session, affiliate, year: int, month: int) -> list[dict]:
    """Scoped variant of compute_month for ONE affiliate - the portal's live
    current-month ESTIMATE (labeled as such in the UI; the monthly statement
    stays the number of record). Reads Stripe, writes nothing. EXACTLY the
    same engine as compute_month (same referral snapshots, terms, ledger and
    activity rule); referrals are pre-filtered to this affiliate so a
    coupon-only match for a DIFFERENT affiliate can never leak in.

    Each returned row carries its lines in row["detail"] (alias row["lines"]):
    kind, state (estimated | pending | paid | held | lapsed | void),
    year_number, basis, rate_pct, commission, ...

    NOTE: this walks the month's paid invoices like compute_month does - the
    portal caches the result (~1h) per (affiliate, month); do not call it per
    page element."""
    from models import AffiliateReferral, AffiliateTerms
    referrals_by_sub = {
        r.stripe_subscription_id: r
        for r in (session.query(AffiliateReferral)
                  .filter(AffiliateReferral.affiliate_id == affiliate.id).all())
    }
    terms_by_id = {t.id: t for t in session.query(AffiliateTerms).all()}
    rows = _compute([affiliate], year, month, referrals_by_sub,
                    terms_by_id=terms_by_id, ledger=_ledger_loader(session))
    for r in rows:
        r["lines"] = r["detail"]
    return rows


# ---------------------------------------------------------------------------
# 4) Terms versions (create a new version; assign prospectively)
# ---------------------------------------------------------------------------

def list_terms(session) -> list:
    """All terms versions, oldest first."""
    from models import AffiliateTerms
    return session.query(AffiliateTerms).order_by(AffiliateTerms.id).all()


def get_terms(session, terms_id=None):
    """A terms version by id; with no id, the program default (v2-5y). None
    if it does not exist (callers fall back to DEFAULT_TERMS)."""
    from models import AffiliateTerms
    q = session.query(AffiliateTerms)
    if terms_id is not None:
        return q.filter(AffiliateTerms.id == int(terms_id)).first()
    return q.filter(AffiliateTerms.version == DEFAULT_TERMS_VERSION).first()


def terms_for(session, affiliate):
    """The terms that apply to this partner's NEXT referral: their assigned
    version, else the program default row, else DEFAULT_TERMS."""
    t = getattr(affiliate, "terms", None)
    if t is None and getattr(affiliate, "terms_id", None) is not None:
        t = get_terms(session, affiliate.terms_id)
    return t or get_terms(session) or DEFAULT_TERMS


def create_terms(session, version, *, pool_pct=50, max_discount_pct=25,
                 promo_commission_pct=50, renewal_pct=25, renewal_years=5,
                 activity_rule_months=12, notes=None):
    """Create a NEW immutable terms version (there is deliberately no update:
    referrals already stamped with a version must stay reproducible).
    renewal_years is the LAST commission year (5 = years 2-5, 10 = years
    2-10); None = lifetime. Commits; returns the AffiliateTerms row."""
    from models import AffiliateTerms
    label = (version or "").strip()
    if not re.match(r"^[A-Za-z0-9._-]{2,40}$", label):
        raise AffiliateError("version must be 2-40 chars of letters, digits, '.', '_' or '-'")
    pool, max_d = _dec(pool_pct), _dec(max_discount_pct)
    promo, renewal = _dec(promo_commission_pct), _dec(renewal_pct)
    for name, v in (("pool_pct", pool), ("promo_commission_pct", promo), ("renewal_pct", renewal)):
        if not (0 <= v <= 100):
            raise AffiliateError("%s must be between 0 and 100" % name)
    if not (0 <= max_d <= pool):
        raise AffiliateError("max_discount_pct must be between 0 and pool_pct")
    if renewal_years is not None and int(renewal_years) < 1:
        raise AffiliateError("renewal_years must be 1 or more (or None for lifetime)")
    if int(activity_rule_months) < 0:
        raise AffiliateError("activity_rule_months must be 0 or more")
    if session.query(AffiliateTerms).filter(AffiliateTerms.version == label).first():
        raise AffiliateError("terms version %r already exists" % label)
    row = AffiliateTerms(
        version=label, pool_pct=pool, max_discount_pct=max_d,
        promo_commission_pct=promo, renewal_pct=renewal,
        renewal_years=int(renewal_years) if renewal_years is not None else None,
        activity_rule_months=int(activity_rule_months), notes=notes)
    session.add(row)
    session.commit()
    return row


def assign_terms(session, affiliate, terms_id, actor=None):
    """Assign a terms version to a partner PROSPECTIVELY: only referrals whose
    checkout starts after this are stamped with it. Existing referrals and
    ledger lines keep the version they were stamped with. A discount above the
    new version's cap is refused (change the discount first). Commits."""
    from models import AuditLog
    terms = get_terms(session, terms_id)
    if terms is None:
        raise AffiliateError("unknown terms version")
    cap = _dec(terms.max_discount_pct)
    for pct in (affiliate.discount_pct, getattr(affiliate, "discount_pct_monthly", None)):
        if pct is not None and _dec(pct) > cap:
            raise AffiliateError("this partner's discount (%s%%) is above the %s%% cap of "
                                 "terms %s - lower the discount first"
                                 % (_dec(pct).normalize(), cap.normalize(), terms.version))
    old = affiliate.terms_id
    affiliate.terms_id = terms.id
    session.add(AuditLog(actor_label=actor or "admin", action="affiliate_terms_assigned",
                         details={"affiliate_id": str(affiliate.id), "code": affiliate.code,
                                  "from_terms_id": old, "to_terms_id": terms.id,
                                  "version": terms.version}))
    session.commit()
    return terms


# ---------------------------------------------------------------------------
# 5) Self-serve partner discount (0..max, once per 24h, no pause, no re-sign)
# ---------------------------------------------------------------------------

def next_discount_change_at(affiliate, now=None):
    """When the partner may change the discount again, or None if they may
    change it now (limit: one change per 24 hours)."""
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    last = _utc(getattr(affiliate, "discount_changed_at", None))
    if last is None or now >= last + DISCOUNT_CHANGE_COOLDOWN:
        return None
    return last + DISCOUNT_CHANGE_COOLDOWN


def set_partner_discount(session, affiliate, new_pct, *, interval="year", actor=None,
                         now=None, enforce_cooldown=True):
    """Change the customer discount a partner offers (self-serve).

    interval 'year' sets discount_pct - the annual / default discount and the
    one behind the partner's typed promotion code. interval 'month' sets the
    monthly override (discount_pct_monthly). Allowed range 0..max_discount_pct
    of the partner's terms. One change per 24h (pass enforce_cooldown=False
    for an admin override).

    A change applies only to customers whose checkout starts AFTER it:
    existing subscribers keep the coupon already on their subscription and
    their referral keeps its stamped discount. The partner is NOT paused and
    does NOT re-sign. A new Stripe coupon is minted (the SAME code string is
    re-pointed via reissue_coupon); 0% removes the coupon and deactivates the
    typed code. Records an affiliate_discount_changes row. Commits; returns
    that row. Raises AffiliateError on bad input, cooldown or Stripe failure
    (Stripe is rolled back if the DB write fails)."""
    from models import AffiliateDiscountChange
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    iv = _norm_interval(interval)
    if iv is None:
        raise AffiliateError("interval must be 'year' or 'month'")
    terms = terms_for(session, affiliate)
    cap = _dec(terms.max_discount_pct)
    try:
        new = _dec(new_pct).quantize(Decimal("0.01"))
    except Exception as e:
        raise AffiliateError("discount must be a number") from e
    if new < 0 or new > cap:
        raise AffiliateError("discount must be between 0%% and %s%%" % cap.normalize())
    if getattr(affiliate, "status", None) == "terminated":
        raise AffiliateError("a terminated partner cannot change the discount")
    if enforce_cooldown:
        wait_until = next_discount_change_at(affiliate, now)
        if wait_until is not None:
            raise AffiliateError("You can change your discount once every 24 hours. "
                                 "Next change available %s UTC."
                                 % wait_until.strftime("%Y-%m-%d %H:%M"))

    code = normalize_code(affiliate.code)
    is_active = getattr(affiliate, "status", None) == "active"
    if iv == "year":
        old = affiliate.discount_pct
        old_coupon = affiliate.stripe_coupon_id
    else:
        old = effective_discount_pct(affiliate, "month")
        old_coupon = affiliate.stripe_coupon_id_monthly
    if old is not None and _dec(old) == new:
        raise AffiliateError("No change - the discount is already %s%%." % new.normalize())

    old_pid = affiliate.stripe_promotion_code_id
    new_coupon = new_promo = None
    undo = None                                    # Stripe compensation if the DB write fails
    if iv == "year":
        if new > 0:
            new_coupon, new_promo = reissue_coupon(affiliate, new)
            undo = lambda: revert_reissue(old_pid, new_coupon, new_promo)   # noqa: E731
            if not is_active:
                # Not active (paused / awaiting signature): the code stays inert.
                try:
                    stripe.PromotionCode.modify(new_promo, active=False)
                except Exception as e:
                    _safe(undo)
                    raise AffiliateError("Could not keep the paused partner's code inactive: %s" % e) from e
        elif old_pid:
            try:
                stripe.PromotionCode.modify(old_pid, active=False)
            except Exception as e:
                if getattr(e, "code", "") != "resource_missing":
                    raise AffiliateError("Could not deactivate the promo code: %s" % e) from e
            if is_active:
                undo = lambda: stripe.PromotionCode.modify(old_pid, active=True)   # noqa: E731
    elif new > 0 and new != _dec(affiliate.discount_pct):
        new_coupon = _mint_monthly_coupon(affiliate, new)
        undo = lambda: stripe.Coupon.delete(new_coupon)   # noqa: E731

    try:
        if iv == "year":
            affiliate.discount_pct = new
            affiliate.stripe_coupon_id = new_coupon
            affiliate.stripe_promotion_code_id = new_promo
        else:
            # Equal to the annual discount -> no override (monthly follows annual).
            affiliate.discount_pct_monthly = None if new == _dec(affiliate.discount_pct) else new
            affiliate.stripe_coupon_id_monthly = new_coupon
        affiliate.discount_changed_at = now
        change = AffiliateDiscountChange(
            affiliate_id=affiliate.id, billing_interval=iv,
            old_pct=_dec(old) if old is not None else None, new_pct=new,
            old_coupon_id=old_coupon, new_coupon_id=new_coupon,
            actor=actor, changed_at=now)
        session.add(change)
        session.commit()
    except Exception:
        session.rollback()
        if undo is not None:
            _safe(undo)
        raise
    log.info("affiliate %s discount (%s) %s -> %s by %s", code, iv, old, new, actor)
    return change


def _safe(fn):
    try:
        fn()
    except Exception as e:   # noqa: BLE001
        log.warning("affiliate Stripe compensation failed: %s", e)


def discount_history(session, affiliate, limit=50) -> list:
    """The partner's discount changes, newest first."""
    from models import AffiliateDiscountChange as C
    return (session.query(C).filter(C.affiliate_id == affiliate.id)
            .order_by(C.changed_at.desc(), C.id.desc()).limit(limit).all())


def forfeit_unpaid(session, affiliate) -> dict:
    """Forfeit everything not yet paid to a partner terminated for cause, at
    once: pending payout rows become void (external_ref FORFEIT_REF) and every
    held or payable ledger line - including lines already sitting on an
    UNPAID payout row - becomes void with hold_reason 'terminated_for_cause'.
    Paid rows and paid lines are never touched; amounts are not changed (lines
    are never re-priced). Does not commit."""
    from models import AffiliateCommissionLine as L, AffiliatePayout as P
    rows = (session.query(P).filter(P.affiliate_id == affiliate.id, P.status == "pending").all())
    for row in rows:
        row.status = "void"
        row.external_ref = FORFEIT_REF
    lines = (session.query(L)
             .filter(L.affiliate_id == affiliate.id, L.state.in_(("held", "pending")))
             .update({"state": "void", "hold_reason": "terminated_for_cause",
                      "payable_month": None}, synchronize_session=False))
    return {"payout_rows": len(rows), "lines": int(lines or 0)}


def terminate_for_cause(session, affiliate, cause, actor=None, now=None):
    """Terminate a partner FOR CAUSE: the only action that forfeits commission.
    Everything not yet paid is forfeited in the same transaction
    (forfeit_unpaid): pending payout rows and held / payable ledger lines,
    including lines already on an unpaid payout row. Paid rows and lines are
    untouched. The cause is required and recorded. Deactivates the typed code.
    Commits."""
    from models import AuditLog
    cause = (cause or "").strip()
    if not cause:
        raise AffiliateError("a cause is required to terminate for cause")
    affiliate.status = "terminated"
    affiliate.terminated_for_cause = True
    affiliate.terminated_at = _utc(now) or dt.datetime.now(dt.timezone.utc)
    affiliate.termination_cause = cause
    forfeited = forfeit_unpaid(session, affiliate)
    session.add(AuditLog(actor_label=actor or "admin", action="affiliate_terminated_for_cause",
                         details={"affiliate_id": str(affiliate.id), "code": affiliate.code,
                                  "cause": cause, "forfeited": forfeited}))
    session.commit()
    if affiliate.stripe_promotion_code_id:
        _safe(lambda: stripe.PromotionCode.modify(affiliate.stripe_promotion_code_id, active=False))
    return affiliate


def release_held_lines(session, affiliate, actor=None) -> int:
    """Operator action "Release held lines": move every HELD ledger line of
    the partner to pending (payable), whatever the hold reason. The lines join
    the next month that is committed (upsert_month gives them a payout month).
    Refused for a partner terminated for cause - that commission is forfeited.
    Returns the number of lines released. Commits."""
    from models import AffiliateCommissionLine as L, AuditLog
    if getattr(affiliate, "terminated_for_cause", False):
        raise AffiliateError("%s was terminated for cause: the commission is forfeited "
                             "and cannot be released." % affiliate.code)
    moved = (session.query(L).filter(L.affiliate_id == affiliate.id, L.state == "held")
             .update({"state": "pending", "hold_reason": None, "payable_month": None},
                     synchronize_session=False))
    moved = int(moved or 0)
    if moved:
        session.add(AuditLog(actor_label=actor or "admin", action="affiliate_held_lines_released",
                             details={"affiliate_id": str(affiliate.id), "code": affiliate.code,
                                      "lines": moved}))
    session.commit()
    return moved


def _mint_monthly_coupon(aff, pct) -> str:
    """Create the partner's MONTHLY override coupon at `pct` and return its id."""
    code = normalize_code(aff.code)
    try:
        coupon = stripe.Coupon.create(
            percent_off=_pct_to_float(pct), duration="repeating",
            duration_in_months=DISCOUNT_DURATION_MONTHS,
            name=f"Affiliate {code} mo"[:40],
            metadata={"tw2_affiliate_code": code, "tw2_purpose": "affiliate",
                      "tw2_interval": "month"})
    except Exception as e:
        raise AffiliateError("Stripe monthly coupon create failed: %s" % e) from e
    return coupon.id


# Stripe coupon id -> percent_off. A coupon's percent_off can never be edited
# in Stripe, so a successful lookup is cached for the life of the process.
_coupon_pct_cache: dict = {}


def coupon_percent_off(coupon_id):
    """percent_off of a Stripe coupon as a Decimal; Decimal('0') for an
    amount-off coupon; None when Stripe could not be asked (not cached, so
    the next call asks again). Never raises."""
    if not coupon_id:
        return None
    if coupon_id in _coupon_pct_cache:
        return _coupon_pct_cache[coupon_id]
    try:
        coupon = stripe.Coupon.retrieve(coupon_id)
        pct = coupon.get("percent_off") if isinstance(coupon, dict) else getattr(coupon, "percent_off", None)
    except Exception as e:   # noqa: BLE001
        log.warning("coupon %s: percent_off lookup failed: %s", coupon_id, e)
        return None
    value = _dec(pct) if pct is not None else Decimal("0")
    _coupon_pct_cache[coupon_id] = value
    return value


def _coupon_matches(coupon_id, discount) -> bool:
    """True unless Stripe says the coupon's percent_off DIFFERS from the
    discount we are about to stamp. A coupon that could not be checked
    (Stripe lookup failed) is not treated as a mismatch: the commission engine
    still protects the payout (classify_invoice 'extra_discount' guard)."""
    pct = coupon_percent_off(coupon_id)
    if pct is None:
        return True
    if pct != _dec(discount):
        log.warning("coupon %s is %s%% off but the partner discount is %s%% - not applied "
                    "(run reconcile_v2_stripe)", coupon_id, pct, _dec(discount))
        return False
    return True


def reconcile_v2_stripe(session) -> list[dict]:
    """One-off Stripe reconcile after migration b4d7e1f2a3c5 (a migration
    cannot call Stripe). For every non-terminated partner: a partner that is
    not ACTIVE gets its promotion code deactivated (v1 partners were paused
    pending re-signature of agreement v2), and a coupon whose percent no
    longer matches the (clamped to 25%) discount is re-issued - the annual /
    typed-code coupon AND the monthly override coupon. A monthly coupon that
    is no longer needed (monthly now equals annual, or 0%) is dropped from the
    partner row; the Stripe coupon itself is left alone because existing
    subscriptions still carry it. Idempotent. Returns one {"code", "action"}
    dict per change. Commits."""
    from models import Affiliate
    out = []
    for aff in session.query(Affiliate).filter(Affiliate.status != "terminated").all():
        try:
            if aff.stripe_coupon_id and _dec(aff.discount_pct) > 0:
                coupon = stripe.Coupon.retrieve(aff.stripe_coupon_id)
                pct = coupon.get("percent_off") if isinstance(coupon, dict) else getattr(coupon, "percent_off", None)
                if pct is not None and _dec(pct) != _dec(aff.discount_pct):
                    old = aff.stripe_coupon_id
                    aff.stripe_coupon_id, aff.stripe_promotion_code_id = reissue_coupon(aff, aff.discount_pct)
                    session.commit()
                    out.append({"code": aff.code, "action": "coupon_reissued",
                                "old_coupon": old, "new_coupon": aff.stripe_coupon_id})
            if aff.stripe_coupon_id_monthly:
                old = aff.stripe_coupon_id_monthly
                monthly = aff.discount_pct_monthly
                if monthly is None or _dec(monthly) <= 0 or _dec(monthly) == _dec(aff.discount_pct):
                    # No separate monthly discount any more: monthly follows annual.
                    aff.stripe_coupon_id_monthly = None
                    if monthly is not None and _dec(monthly) == _dec(aff.discount_pct):
                        aff.discount_pct_monthly = None
                    session.commit()
                    out.append({"code": aff.code, "action": "monthly_coupon_dropped",
                                "old_coupon": old})
                else:
                    coupon = stripe.Coupon.retrieve(old)
                    pct = coupon.get("percent_off") if isinstance(coupon, dict) else getattr(coupon, "percent_off", None)
                    if pct is None or _dec(pct) != _dec(monthly):
                        aff.stripe_coupon_id_monthly = _mint_monthly_coupon(aff, monthly)
                        try:
                            session.commit()
                        except Exception:
                            _safe(lambda cid=aff.stripe_coupon_id_monthly: stripe.Coupon.delete(cid))
                            raise
                        out.append({"code": aff.code, "action": "monthly_coupon_reissued",
                                    "old_coupon": old, "new_coupon": aff.stripe_coupon_id_monthly})
            if aff.status != "active" and aff.stripe_promotion_code_id:
                stripe.PromotionCode.modify(aff.stripe_promotion_code_id, active=False)
                out.append({"code": aff.code, "action": "promo_deactivated"})
        except Exception as e:   # noqa: BLE001
            session.rollback()
            out.append({"code": aff.code, "action": "error", "error": str(e)})
    return out


# ---------------------------------------------------------------------------
# 6) Company-wide promotions (campaigns)
# ---------------------------------------------------------------------------
# A campaign is an intro offer for NEW customers during a claim window. Each
# eligible (tier, interval) gets its own Stripe coupon restricted to that
# plan's product (applies_to) and unredeemable after the window (redeem_by).
# Annual: the coupon applies once (one billing period). Monthly: it repeats
# for intro_months (12). The renewal is at the regular price.

CAMPAIGN_TIERS = ("navigator", "analyst", "strategist")
CAMPAIGN_INTERVALS = ("month", "year")


def offer_key(tier, interval) -> str:
    """Storage key of a plan inside promo_campaigns.intro_prices /
    stripe_coupon_ids: '<tier>:<month|year>'."""
    return "%s:%s" % ((tier or "").strip().lower(), _norm_interval(interval))


def campaign_first_period_cents(campaign, tier, interval, list_price_cents):
    """What a customer pays for the FIRST billing period of this plan under
    the campaign (pre-tax), or None when the plan is not part of it."""
    iv = _norm_interval(interval)
    tier = (tier or "").strip().lower()
    if iv is None or tier not in (campaign.tiers or []) or iv not in (campaign.billing_intervals or []):
        return None
    lp = int(list_price_cents)
    if campaign.offer_type == "price":
        price = (campaign.intro_prices or {}).get(offer_key(tier, iv))
        if price is None:
            return None
        return min(int(price), lp)
    if campaign.percent_off is None:
        return None
    return _cents(Decimal(lp) * (_HUNDRED - _dec(campaign.percent_off)) / _HUNDRED)


def campaign_is_live(campaign, now=None) -> bool:
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    return (campaign.status == "active"
            and _utc(campaign.starts_at) <= now < _utc(campaign.ends_at))


def active_campaign_for(session, tier, interval, list_price_cents, now=None):
    """(campaign, first_period_cents) of the best live campaign for a plan -
    the lowest first-period price when several overlap - or (None, None).
    Only campaigns whose Stripe coupon for the plan is provisioned qualify."""
    from models import PromoCampaign
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    best = (None, None)
    for c in (session.query(PromoCampaign)
              .filter(PromoCampaign.status == "active",
                      PromoCampaign.starts_at <= now, PromoCampaign.ends_at > now).all()):
        if not campaign_is_live(c, now):
            continue
        price = campaign_first_period_cents(c, tier, interval, list_price_cents)
        if price is None or not (c.stripe_coupon_ids or {}).get(offer_key(tier, interval)):
            continue
        if best[1] is None or price < best[1]:
            best = (c, price)
    return best


def _validate_campaign(c, catalog) -> None:
    tiers = list(c.tiers or [])
    ivs = list(c.billing_intervals or [])
    if not (c.name or "").strip():
        raise AffiliateError("campaign name is required")
    if not tiers or any(t not in CAMPAIGN_TIERS for t in tiers):
        raise AffiliateError("tiers must be a non-empty list of: %s" % ", ".join(CAMPAIGN_TIERS))
    if not ivs or any(i not in CAMPAIGN_INTERVALS for i in ivs):
        raise AffiliateError("intervals must be a non-empty list of: month, year")
    if not c.new_customers_only:
        raise AffiliateError("campaigns are for new customers only")
    starts, ends = _utc(c.starts_at), _utc(c.ends_at)
    if starts is None or ends is None or ends <= starts:
        raise AffiliateError("the claim window needs a start and a later end (UTC)")
    if c.offer_type not in ("price", "percent"):
        raise AffiliateError("offer_type must be 'price' or 'percent'")
    if int(c.intro_months or 0) < 1:
        raise AffiliateError("intro_months must be 1 or more")
    if c.offer_type == "percent":
        if c.percent_off is None or not (0 < _dec(c.percent_off) <= 100):
            raise AffiliateError("percent_off must be more than 0 and at most 100")
    for tier in tiers:
        for iv in ivs:
            plan = (catalog or {}).get((tier, iv))
            if not plan or not plan.get("product_id") or not plan.get("list_price_cents"):
                raise AffiliateError("no Stripe price is configured for %s (%s)" % (tier, iv))
            if c.offer_type == "price":
                price = (c.intro_prices or {}).get(offer_key(tier, iv))
                if price is None or int(price) < 0 or int(price) >= int(plan["list_price_cents"]):
                    raise AffiliateError("intro price for %s (%s) must be at least 0 and below "
                                         "the list price" % (tier, iv))


def provision_campaign_coupons(campaign, catalog) -> dict:
    """Create one Stripe coupon per eligible (tier, interval) of the campaign
    and return {offer_key: coupon_id}. catalog: {(tier, interval):
    {"product_id", "list_price_cents"}} (app.py: _campaign_catalog()). On any
    failure the coupons created so far are deleted and AffiliateError raised."""
    ends = _utc(campaign.ends_at)
    if ends <= dt.datetime.now(dt.timezone.utc):
        raise AffiliateError("the claim window has already ended")
    made = {}
    try:
        for tier in campaign.tiers:
            for iv in campaign.billing_intervals:
                plan = catalog[(tier, iv)]
                kwargs = dict(
                    name=("%s %s %s" % (campaign.code, tier, iv))[:40],
                    applies_to={"products": [plan["product_id"]]},
                    redeem_by=int(ends.timestamp()),
                    metadata={"tw2_purpose": "campaign", "tw2_campaign_code": campaign.code,
                              "tw2_campaign_id": str(campaign.id or ""),
                              "tw2_tier": tier, "tw2_interval": iv},
                )
                if iv == "year":
                    kwargs["duration"] = "once"
                else:
                    kwargs["duration"] = "repeating"
                    kwargs["duration_in_months"] = int(campaign.intro_months or 12)
                if campaign.offer_type == "price":
                    kwargs["amount_off"] = (int(plan["list_price_cents"])
                                            - int(campaign.intro_prices[offer_key(tier, iv)]))
                    kwargs["currency"] = "usd"
                else:
                    kwargs["percent_off"] = _pct_to_float(campaign.percent_off)
                made[offer_key(tier, iv)] = stripe.Coupon.create(**kwargs).id
    except Exception as e:
        for cid in made.values():
            _safe(lambda cid=cid: stripe.Coupon.delete(cid))
        raise AffiliateError("Stripe campaign coupon create failed: %s" % e) from e
    return made


def _campaign_code(session, name) -> str:
    """Generate the campaign's storage code from its name (a slug WE control,
    never raw free text), made unique with a numeric suffix."""
    from models import PromoCampaign
    slug = re.sub(r"[^A-Z0-9]+", "-", (name or "").upper()).strip("-")[:48] or "CAMPAIGN"
    if len(slug) < 2:
        slug = "CAMPAIGN-" + slug
    code, n = slug, 1
    while session.query(PromoCampaign).filter(PromoCampaign.code == code).first() is not None:
        n += 1
        code = "%s-%d" % (slug, n)
    return code


def create_campaign(session, *, name, tiers, intervals, starts_at, ends_at, offer_type,
                    catalog, intro_prices=None, percent_off=None, intro_months=12,
                    new_customers_only=True, status="active", notes=None, code=None):
    """Create a company-wide promotion and provision its Stripe coupons.

    tiers: list of navigator|analyst|strategist. intervals: list of
    month|year (monthly|yearly accepted). starts_at / ends_at: the claim
    window, UTC. offer_type 'price' needs intro_prices
    {"<tier>:<month|year>": cents} for every eligible plan (annual: the price
    of the first year; monthly: the price of each of the first intro_months
    months); 'percent' needs percent_off. catalog: {(tier, interval):
    {"product_id", "list_price_cents"}} from app.py _campaign_catalog().
    status 'draft' skips Stripe (provision later via update_campaign).
    Commits; returns the PromoCampaign row."""
    import uuid as _uuid
    from models import PromoCampaign
    ivs = []
    for i in (intervals or []):
        n = _norm_interval(i)
        if n is None:
            raise AffiliateError("intervals must be a non-empty list of: month, year")
        if n not in ivs:
            ivs.append(n)
    if status not in ("draft", "active"):
        raise AffiliateError("status must be 'draft' or 'active'")
    if code:
        code = normalize_code(code)
        validate_code(code)
        if session.query(PromoCampaign).filter(PromoCampaign.code == code).first() is not None:
            raise AffiliateError("campaign code %s already exists" % code)
    c = PromoCampaign(
        id=_uuid.uuid4(), code=code or _campaign_code(session, name), name=(name or "").strip(),
        tiers=[(t or "").strip().lower() for t in (tiers or [])], billing_intervals=ivs,
        new_customers_only=bool(new_customers_only),
        starts_at=_utc(starts_at), ends_at=_utc(ends_at), offer_type=offer_type,
        intro_prices=({str(k): int(v) for k, v in (intro_prices or {}).items()}
                      if offer_type == "price" else None),
        percent_off=_dec(percent_off) if (offer_type == "percent" and percent_off is not None) else None,
        intro_months=int(intro_months or 12), status=status, notes=notes)
    _validate_campaign(c, catalog)
    if status == "active":
        c.stripe_coupon_ids = provision_campaign_coupons(c, catalog)
    try:
        session.add(c)
        session.commit()
    except Exception:
        session.rollback()
        for cid in (c.stripe_coupon_ids or {}).values():
            _safe(lambda cid=cid: stripe.Coupon.delete(cid))
        raise
    return c


_CAMPAIGN_OFFER_FIELDS = ("tiers", "intervals", "starts_at", "ends_at", "offer_type",
                          "intro_prices", "percent_off", "intro_months")


def update_campaign(session, campaign, *, catalog=None, **changes):
    """Update a campaign. name / notes / status change in place. Changing the
    OFFER (tiers, intervals, window, offer_type, intro_prices, percent_off,
    intro_months) - or activating a draft - provisions FRESH Stripe coupons
    (needs catalog); the old coupons are left alone because subscriptions that
    already claimed them keep their intro price. status 'archived' stops new
    claims at once. Commits; returns the campaign."""
    unknown = set(changes) - set(_CAMPAIGN_OFFER_FIELDS) - {"name", "notes", "status", "new_customers_only"}
    if unknown:
        raise AffiliateError("unknown campaign field(s): %s" % ", ".join(sorted(unknown)))
    offer_changed = False
    for field in _CAMPAIGN_OFFER_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if field == "intervals":
            value = [_norm_interval(i) for i in (value or [])]
            attr = "billing_intervals"
        else:
            attr = field
        if field in ("starts_at", "ends_at"):
            value = _utc(value)
        if field == "tiers":
            value = [(t or "").strip().lower() for t in (value or [])]
        if field == "intro_prices" and value is not None:
            value = {str(k): int(v) for k, v in value.items()}
        if field == "percent_off" and value is not None:
            value = _dec(value)
        old = getattr(campaign, attr)
        if field in ("starts_at", "ends_at"):
            old = _utc(old)
        if old != value:
            setattr(campaign, attr, value)
            offer_changed = True
    for field in ("name", "notes", "new_customers_only"):
        if field in changes:
            setattr(campaign, field, changes[field])
    new_status = changes.get("status", campaign.status)
    if new_status not in ("draft", "active", "archived"):
        raise AffiliateError("status must be draft, active or archived")
    activating = new_status == "active" and (campaign.status != "active"
                                             or not campaign.stripe_coupon_ids)
    campaign.status = new_status
    minted = None
    if new_status == "active" and (offer_changed or activating):
        if catalog is None:
            raise AffiliateError("catalog is required to provision campaign coupons")
        _validate_campaign(campaign, catalog)
        minted = provision_campaign_coupons(campaign, catalog)
        campaign.stripe_coupon_ids = minted
    elif offer_changed:
        campaign.stripe_coupon_ids = None          # stale: re-provisioned on activation
    try:
        session.commit()
    except Exception:
        session.rollback()
        for cid in (minted or {}).values():
            _safe(lambda cid=cid: stripe.Coupon.delete(cid))
        raise
    return campaign


def list_campaigns(session, include_archived=True) -> list:
    from models import PromoCampaign
    q = session.query(PromoCampaign)
    if not include_archived:
        q = q.filter(PromoCampaign.status != "archived")
    return q.order_by(PromoCampaign.starts_at.desc()).all()


# ---------------------------------------------------------------------------
# 7) Checkout: resolve the partner and the ONE offer for a purchase
# ---------------------------------------------------------------------------

def _partner_spec(aff, interval, discount):
    """The Stripe `discounts=[...]` entry that applies the partner's discount
    for a billing interval, or None (0% discount, or nothing provisioned).

    A coupon is only ever applied when its Stripe percent_off EQUALS
    `discount` (the value stamped on the referral): a monthly coupon that is
    out of step (for example a legacy 40% coupon after the cap was lowered to
    25%) is skipped in favour of the annual / flat coupon when THAT one
    matches, else no coupon at all. The caller then stamps 0%."""
    if discount <= 0:
        return None
    monthly = _norm_interval(interval) == "month"
    override = getattr(aff, "stripe_coupon_id_monthly", None) if monthly else None
    flat = getattr(aff, "stripe_coupon_id", None)

    def flat_spec():
        if getattr(aff, "stripe_promotion_code_id", None):
            return {"promotion_code": aff.stripe_promotion_code_id}
        return {"coupon": flat} if flat else None

    if override:
        if _coupon_matches(override, discount):
            return {"coupon": override}
        # Out-of-step monthly coupon: the flat coupon may stand in, but only
        # when Stripe CONFIRMS it carries exactly this discount.
        if flat and coupon_percent_off(flat) == _dec(discount):
            return flat_spec()
        return None
    if monthly and getattr(aff, "discount_pct_monthly", None) is not None \
            and _dec(aff.discount_pct_monthly) != _dec(aff.discount_pct):
        return None                                # monthly override without its own coupon
    if flat and not _coupon_matches(flat, discount):
        return None
    return flat_spec()


def find_returning_referral(session, customer_id, now=None):
    """Cancel-and-return (rule 8): the customer's most recent referral if their
    previous subscription ended within the last 12 months, else None. The
    end time comes from the referral row (stamped by the webhook), falling
    back to Stripe when it was never stamped. Never raises."""
    if not customer_id:
        return None
    from models import AffiliateReferral as R
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    try:
        prev = (session.query(R).filter(R.stripe_customer_id == customer_id)
                .order_by(R.attributed_at.desc()).first())
        if prev is None:
            return None
        ended = _utc(prev.ended_at)
        if ended is None:
            sub = stripe.Subscription.retrieve(prev.stripe_subscription_id)
            subd = sub if isinstance(sub, dict) else sub.to_dict()
            if (subd.get("status") or "") not in ("canceled", "incomplete_expired", "unpaid"):
                return None
            ended = _utc(subd.get("ended_at") or subd.get("canceled_at"))
        if ended is None or now >= _add_months(ended, RETURN_WINDOW_MONTHS):
            return None
        return prev
    except Exception as e:   # noqa: BLE001
        log.warning("returning-referral lookup failed for %s: %s", customer_id, e)
        return None


def resolve_checkout_offer(session, *, user, raw_code, tier, period, list_price_cents,
                           customer_id=None, is_new_customer=True, now=None) -> dict:
    """Decide WHO gets credit and WHICH single offer a checkout carries.

    Partner (first hit wins): a returning customer's previous partner (same
    Stripe customer, previous subscription ended < 12 months ago), then
    `raw_code` (URL / form code or the tw_ref cookie - the caller passes the
    first non-empty), then the signup stamp users.referred_by_affiliate_id.
    Codes and stamps need an ACTIVE partner; a self-referral (partner email ==
    buyer email) is never attributed.

    Offer: the live campaign for (tier, period) if the customer is new, versus
    the partner's discount. Whichever FIRST-PERIOD price is lower wins (a tie
    goes to the partner offer); exactly one discount is pre-applied, never
    both. Campaign wins -> offer_type 'promo'; partner wins -> 'regular'.

    Returns a dict:
      affiliate_id, affiliate_code, source ('checkout'|'signup'|'return'|None)
      offer_type ('regular'|'promo'|None)   None = direct sale at list price
      campaign_id, campaign_code
      discount_spec     entry for Stripe Checkout discounts=[...] or None
      discount_pct      partner discount stamped on a regular offer
      list_price_cents, first_period_cents
      partner_price_cents, campaign_price_cents   (what each offer would cost)
      metadata          the tw2_* subscription metadata to stamp
    """
    from models import Affiliate
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    iv = _norm_interval(period)
    lp = int(list_price_cents or 0)
    out = {"affiliate_id": None, "affiliate_code": None, "source": None, "offer_type": None,
           "campaign_id": None, "campaign_code": None, "discount_spec": None,
           "discount_pct": None, "list_price_cents": lp, "first_period_cents": lp,
           "partner_price_cents": None, "campaign_price_cents": None, "metadata": {}}
    buyer_email = (getattr(user, "email", None) or "").strip().lower()

    def usable(aff, need_active=True):
        if aff is None or aff.status == "terminated" or (need_active and aff.status != "active"):
            return False
        return not (buyer_email and (aff.email or "").strip().lower() == buyer_email)

    aff = None
    prior = find_returning_referral(session, customer_id, now) if customer_id else None
    if prior is not None:
        cand = session.query(Affiliate).filter(Affiliate.id == prior.affiliate_id).first()
        if usable(cand, need_active=False):
            aff, out["source"] = cand, "return"
        else:
            prior = None
    if aff is None and raw_code:
        cand = active_affiliate_by_code(session, raw_code)
        if usable(cand):
            aff, out["source"] = cand, "checkout"
    if aff is None and getattr(user, "referred_by_affiliate_id", None):
        cand = (session.query(Affiliate)
                .filter(Affiliate.id == user.referred_by_affiliate_id).first())
        if usable(cand):
            aff, out["source"] = cand, "signup"

    terms = terms_for(session, aff) if aff is not None else None
    # A returning customer keeps the ORIGINAL year-1 anchor: no new first year.
    anchor = _utc(getattr(prior, "year_anchor_at", None)) if prior is not None else None
    past_year_one = anchor is not None and year_number(anchor, now) > 1

    partner_price = partner_spec = None
    partner_discount = Decimal("0")
    if aff is not None:
        if aff.status == "active" and not past_year_one:
            partner_discount = clamp_discount(effective_discount_pct(aff, iv), terms)
            partner_spec = _partner_spec(aff, iv, partner_discount)
            if partner_spec is None:
                partner_discount = Decimal("0")
        partner_price = _cents(Decimal(lp) * (_HUNDRED - partner_discount) / _HUNDRED)
        out["partner_price_cents"] = partner_price

    campaign = campaign_price = None
    if is_new_customer and prior is None and lp > 0:
        campaign, campaign_price = active_campaign_for(session, tier, iv, lp, now)
        out["campaign_price_cents"] = campaign_price

    campaign_wins = campaign is not None and (partner_price is None or campaign_price < partner_price)
    if campaign_wins:
        out.update(offer_type="promo", campaign_id=str(campaign.id), campaign_code=campaign.code,
                   discount_spec={"coupon": campaign.stripe_coupon_ids[offer_key(tier, iv)]},
                   first_period_cents=campaign_price)
    elif aff is not None:
        out.update(offer_type="regular", discount_spec=partner_spec,
                   discount_pct=partner_discount, first_period_cents=partner_price)

    md = {}
    if aff is not None:
        out["affiliate_id"], out["affiliate_code"] = str(aff.id), aff.code
        md.update({
            "tw2_affiliate_id": str(aff.id),
            "tw2_affiliate_code": aff.code,
            "tw2_affiliate_source": out["source"],
            "tw2_terms_id": str(getattr(terms, "id", "") or ""),
            "tw2_offer_type": out["offer_type"],
            "tw2_list_price_cents": str(lp),
            "tw2_discount_pct": str((partner_discount if out["offer_type"] == "regular"
                                     else Decimal("0")).quantize(Decimal("0.01"))),
        })
        if prior is not None:
            md["tw2_prior_referral_id"] = str(prior.id)
            if anchor is not None:
                md["tw2_year_anchor_at"] = str(int(anchor.timestamp()))
    if campaign_wins:
        md["tw2_campaign_id"] = str(campaign.id)
        md["tw2_campaign_code"] = campaign.code
        md.setdefault("tw2_offer_type", "promo")
        md.setdefault("tw2_list_price_cents", str(lp))
    out["metadata"] = md
    return out


def display_offers(session, affiliate, catalog, now=None, is_new_customer=True) -> dict:
    """The effective customer offer per plan, for /join/<code> and pricing.

    catalog: {(tier, interval): {"list_price_cents", ...}}. Returns
    {"<tier>:<month|year>": {tier, interval, list_price_cents, price_cents,
    offer ('campaign'|'partner'|None), discount_pct, savings_cents,
    intro_months, campaign: {code, name, ends_at} | None,
    partner_price_cents, campaign_price_cents}}. Same price choice as
    resolve_checkout_offer (lower first-period price wins; tie -> partner)."""
    now = _utc(now) or dt.datetime.now(dt.timezone.utc)
    terms = terms_for(session, affiliate) if affiliate is not None else None
    out = {}
    for (tier, interval), plan in sorted((catalog or {}).items()):
        iv = _norm_interval(interval)
        lp = int(plan.get("list_price_cents") or 0)
        if iv is None or lp <= 0:
            continue
        partner_price = None
        discount = Decimal("0")
        if affiliate is not None and affiliate.status == "active":
            discount = clamp_discount(effective_discount_pct(affiliate, iv), terms)
            if _partner_spec(affiliate, iv, discount) is None:
                discount = Decimal("0")
            partner_price = _cents(Decimal(lp) * (_HUNDRED - discount) / _HUNDRED)
        campaign, campaign_price = (active_campaign_for(session, tier, iv, lp, now)
                                    if is_new_customer else (None, None))
        row = {"tier": tier, "interval": iv, "list_price_cents": lp, "price_cents": lp,
               "offer": None, "discount_pct": None, "savings_cents": 0, "intro_months": None,
               "campaign": None, "partner_price_cents": partner_price,
               "campaign_price_cents": campaign_price}
        if campaign is not None and (partner_price is None or campaign_price < partner_price):
            row.update(offer="campaign", price_cents=campaign_price,
                       intro_months=(int(campaign.intro_months or 12) if iv == "month" else None),
                       campaign={"code": campaign.code, "name": campaign.name,
                                 "ends_at": _iso(campaign.ends_at)})
        elif partner_price is not None and discount > 0:
            row.update(offer="partner", price_cents=partner_price, discount_pct=str(discount),
                       intro_months=DISCOUNT_DURATION_MONTHS if iv == "month" else None)
        row["savings_cents"] = lp - row["price_cents"]
        out[offer_key(tier, iv)] = row
    return out


# ---------------------------------------------------------------------------
# 8) Webhook writers (called from web/app.py inside the webhook transaction)
# ---------------------------------------------------------------------------

def affiliate_for_coupon(session, coupon_id):
    """(affiliate, discount_pct) for a partner coupon id - the partner's
    current annual or monthly coupon, or an OLDER one found in the discount
    history - else (None, None)."""
    if not coupon_id:
        return None, None
    from models import Affiliate, AffiliateDiscountChange as C
    aff = session.query(Affiliate).filter(Affiliate.stripe_coupon_id == coupon_id).first()
    if aff is not None:
        return aff, _dec(aff.discount_pct)
    aff = session.query(Affiliate).filter(Affiliate.stripe_coupon_id_monthly == coupon_id).first()
    if aff is not None:
        return aff, _dec(effective_discount_pct(aff, "month"))
    change = (session.query(C).filter((C.new_coupon_id == coupon_id) | (C.old_coupon_id == coupon_id))
              .order_by(C.changed_at.desc()).first())
    if change is not None:
        aff = session.query(Affiliate).filter(Affiliate.id == change.affiliate_id).first()
        pct = change.new_pct if change.new_coupon_id == coupon_id else change.old_pct
        if aff is not None:
            return aff, (_dec(pct) if pct is not None else None)
    return None, None


def _subscription_plan(sub: dict) -> dict:
    """tier / interval / list price read off a subscription's first item."""
    items = ((sub.get("items") or {}).get("data") or [])
    price = (items[0].get("price") or {}) if items else {}
    md = sub.get("metadata") or {}
    return {"interval": (_norm_interval((price.get("recurring") or {}).get("interval"))
                         or _norm_interval(md.get("period"))),
            "list_price_cents": price.get("unit_amount"),
            "tier": (md.get("tier") or md.get("tw2_tier_target") or None)}


def record_referral_from_subscription(session, sub: dict, customer_id=None) -> bool:
    """Write the affiliate_referrals row for a NEW subscription. Idempotent
    (one referral per subscription id); returns True if a row was inserted.

    1. Checkout stamped the partner in the subscription metadata
       (tw2_affiliate_id): the row carries the full checkout snapshot - terms,
       offer type, campaign, tier, interval, list price, discount - and, for a
       returning customer, the carried year-1 anchor.
    2. No metadata, but the subscription's discount is a partner coupon (the
       customer TYPED the partner's promotion code into Stripe's box): map
       the coupon to its partner and write the row with source 'promo_code',
       so renewals keep paying after the 12-month coupon falls off.

    Runs inside a SAVEPOINT and never raises - a referral-write failure must
    not break the webhook."""
    import uuid as _uuid
    from models import Affiliate, AffiliateReferral
    sub = sub or {}
    sub_id = sub.get("id")
    if not sub_id:
        return False
    md = sub.get("metadata") or {}
    customer_id = customer_id or _id_of(sub.get("customer"))
    try:
        with session.begin_nested():
            if (session.query(AffiliateReferral.id)
                    .filter(AffiliateReferral.stripe_subscription_id == sub_id).first()):
                return False
            plan = _subscription_plan(sub)
            values = None
            aff_id = md.get("tw2_affiliate_id")
            if aff_id:
                try:
                    aff_uuid = _uuid.UUID(str(aff_id))
                except (ValueError, TypeError):
                    return False
                aff = session.query(Affiliate).filter(Affiliate.id == aff_uuid).first()
                if aff is None:
                    return False

                def _int(key):
                    try:
                        return int(md.get(key)) if md.get(key) not in (None, "") else None
                    except (TypeError, ValueError):
                        return None

                def _uuid_or_none(key):
                    try:
                        return _uuid.UUID(str(md.get(key))) if md.get(key) else None
                    except (ValueError, TypeError):
                        return None
                offer = md.get("tw2_offer_type") if md.get("tw2_offer_type") in ("regular", "promo") else None
                source = md.get("tw2_affiliate_source")
                try:
                    discount = _dec(md.get("tw2_discount_pct")) if md.get("tw2_discount_pct") not in (None, "") else None
                except Exception:
                    discount = None
                values = dict(
                    affiliate_id=aff.id, referral_code=md.get("tw2_affiliate_code") or aff.code,
                    source=source if source in ("checkout", "signup", "return") else "checkout",
                    terms_id=_int("tw2_terms_id") or aff.terms_id,
                    offer_type=offer, campaign_id=_uuid_or_none("tw2_campaign_id"),
                    tier=plan["tier"], billing_interval=plan["interval"],
                    list_price_cents=_int("tw2_list_price_cents") or plan["list_price_cents"],
                    discount_pct=discount,
                    year_anchor_at=_utc(_int("tw2_year_anchor_at")),
                    prior_referral_id=_uuid_or_none("tw2_prior_referral_id"),
                    sub_link=normalize_sub(md.get("tw2_affiliate_sub")))
            else:
                coupon_ids = _invoice_coupon_ids(sub)
                if not coupon_ids and (sub.get("discounts") or sub.get("discount")):
                    # Discounts arrive as bare ids unless expanded.
                    full = stripe.Subscription.retrieve(sub_id, expand=["discounts"])
                    coupon_ids = _invoice_coupon_ids(full if isinstance(full, dict) else full.to_dict())
                for cid in coupon_ids:
                    aff, pct = affiliate_for_coupon(session, cid)
                    if aff is None or aff.status == "terminated":
                        continue
                    values = dict(
                        affiliate_id=aff.id, referral_code=aff.code, source="promo_code",
                        terms_id=aff.terms_id, offer_type="regular", tier=plan["tier"],
                        billing_interval=plan["interval"],
                        list_price_cents=plan["list_price_cents"], discount_pct=pct)
                    break
            if values is None:
                return False
            session.add(AffiliateReferral(
                id=_uuid.uuid4(), stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id, **values))
            session.flush()
            return True
    except Exception:
        log.exception("failed to record affiliate referral for subscription %s", sub_id)
        return False


def record_first_payment(session, invoice: dict) -> bool:
    """Stamp a referral's commission clock from a SUCCEEDED invoice: the first
    payment with amount_paid > 0 sets first_paid_at (the activity rule's "new
    paying customer") and year_anchor_at (service start of year 1, unless a
    returning customer carried one over). $0 trial invoices never start the
    clock. Idempotent; SAVEPOINT; never raises."""
    from models import AffiliateReferral
    invoice = invoice or {}
    sub_id = _invoice_subscription_id(invoice)
    if not sub_id or int(invoice.get("amount_paid") or 0) <= 0:
        return False
    try:
        with session.begin_nested():
            ref = (session.query(AffiliateReferral)
                   .filter(AffiliateReferral.stripe_subscription_id == sub_id).first())
            if ref is None or ref.first_paid_at is not None:
                return False
            ref.first_paid_at = _invoice_paid_at(invoice) or dt.datetime.now(dt.timezone.utc)
            if ref.year_anchor_at is None:
                ref.year_anchor_at = _invoice_service_start(invoice) or ref.first_paid_at
            session.flush()
            return True
    except Exception:
        log.exception("failed to stamp first payment for subscription %s", sub_id)
        return False


def record_subscription_ended(session, sub: dict) -> bool:
    """Stamp affiliate_referrals.ended_at when a referred subscription ends
    (opens the 12-month cancel-and-return window). SAVEPOINT; never raises."""
    from models import AffiliateReferral
    sub = sub or {}
    sub_id = sub.get("id")
    if not sub_id:
        return False
    try:
        with session.begin_nested():
            ref = (session.query(AffiliateReferral)
                   .filter(AffiliateReferral.stripe_subscription_id == sub_id).first())
            if ref is None or ref.ended_at is not None:
                return False
            ref.ended_at = (_utc(sub.get("ended_at") or sub.get("canceled_at"))
                            or dt.datetime.now(dt.timezone.utc))
            session.flush()
            return True
    except Exception:
        log.exception("failed to stamp subscription end for %s", sub_id)
        return False


def is_founder_price(price, product_metadata=None) -> bool:
    """A legacy FOUNDER price (rule 10): its id is listed in
    config.FOUNDER_PRICE_IDS, or the price / its product carries metadata
    tw2_founder=true."""
    price = price or {}
    if not isinstance(price, dict):
        price = price.to_dict() if hasattr(price, "to_dict") else {}
    if price.get("id") and price.get("id") in set(getattr(config, "FOUNDER_PRICE_IDS", ()) or ()):
        return True

    def flagged(md):
        return str((md or {}).get("tw2_founder") or "").strip().lower() in ("true", "1", "yes")
    if flagged(price.get("metadata")) or flagged(product_metadata):
        return True
    product = price.get("product")
    return isinstance(product, dict) and flagged(product.get("metadata"))
