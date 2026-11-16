"""Affiliate program - Stripe glue + commission engine (manual promo-code model).

Two jobs, both pure-Stripe (NO webhook / billing-path changes - this is a
downstream reader/writer of Stripe only):

  1. provision_stripe_objects(aff): create the affiliate's Stripe coupon
     (percent_off = discount_pct, repeating 12 months = "X% off the first year")
     plus a matching promotion code (the shareable string). One coupon + one
     code per affiliate (1:1:1) so every discounted sale maps to exactly one
     affiliate via the coupon id.

  2. compute_month(session, year, month): read Stripe for that calendar month,
     attribute each paid invoice to an affiliate by the coupon applied, and sum
     commission = (amount_paid - tax) * commission_pct, honoring the affiliate's
     commission_model and a self-referral guard. upsert_month() persists the
     result into the affiliate_payouts ledger, idempotent on
     (affiliate_id, period_start, currency) so a re-run never double-counts and
     never overwrites a row already marked paid.

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
# 2) Commission engine
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
    """All Stripe coupon ids applied to an invoice. Reads the `discounts` list
    (each a Discount object) plus the legacy single `discount`. NOTE: the coupon
    now lives at discount.source.coupon, NOT discount.coupon - the old path
    silently returned nothing and broke attribution. Unexpanded discount-id
    strings are skipped (compute_month expands data.discounts)."""
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


def _earliest_paid_invoice(customer_id: str, coupon_id: str | None = None,
                           subscription_id: str | None = None):
    """(datetime, invoice_id) of the customer's earliest paid (amount_paid>0)
    invoice, or (None, None). If subscription_id is given, only invoices for THAT
    subscription count (coupon-independent, so the anchor survives a later
    discount/coupon swap on the affiliate). Else if coupon_id is given, only
    invoices that carried THAT coupon count - so first_payment / duration_12mo
    anchor on the affiliate-attributed purchase, not on some unrelated earlier invoice.
    Returns the invoice id too so first_payment qualifies by IDENTITY (one
    invoice) rather than a time window - a window double-counts proration /
    true-up invoices Stripe mints minutes apart."""
    try:
        earliest_dt = None
        earliest_id = None
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
            d = dt.datetime.fromtimestamp(invd.get("created") or 0, tz=dt.timezone.utc)
            if earliest_dt is None or d < earliest_dt:
                earliest_dt = d
                earliest_id = invd.get("id")
        return earliest_dt, earliest_id
    except Exception as e:
        log.warning("earliest-paid-invoice lookup failed for %s: %s", customer_id, e)
        return None, None


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
    off the invoice line items (no extra Stripe call); used to pick the affiliate's
    per-interval commission rate."""
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


def compute_month(session, year: int, month: int) -> list[dict]:
    """Load active affiliates + persisted referrals, then compute per-affiliate
    commission for the month from Stripe. Does NOT write anything. See _compute()."""
    from models import Affiliate, AffiliateReferral
    # Pay ACTIVE affiliates only. 'paused' (incl. awaiting-signature) and
    # 'terminated' do not accrue commission - the activation gate covers accrual,
    # not just pre-application of the discount.
    affiliates = (session.query(Affiliate)
                  .filter(Affiliate.status == "active").all())
    referrals_by_sub = {r.stripe_subscription_id: str(r.affiliate_id)
                        for r in session.query(AffiliateReferral).all()}
    return _compute(affiliates, year, month, referrals_by_sub)


# Dispute statuses that do NOT take money back (won, or inquiries that never
# withdrew funds). Every other dispute status nets the commission at creation.
_DISPUTE_NO_CLAWBACK = {"won", "warning_needs_response", "warning_under_review",
                        "warning_closed"}


def _month_reversals(start, end):
    """Refunds + money-withdrawing disputes CREATED in [start, end), as plain
    dicts {kind, id, amount, charge, payment_intent, created}. Dated by when
    the money left, so a refund of an invoice paid in an earlier (possibly
    already-paid-out) month lands in THIS month as a negative line - the
    clawback. Credit notes that refund money create Refund objects, so they
    are covered here too (and are no longer netted on the invoice itself)."""
    window = {"gte": int(start.timestamp()), "lt": int(end.timestamp())}
    out = []
    for r in stripe.Refund.list(created=window, limit=100).auto_paging_iter():
        rd = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        if rd.get("status") not in ("succeeded", "pending"):
            continue
        out.append({"kind": "refund", "id": rd.get("id"), "amount": int(rd.get("amount") or 0),
                    "charge": rd.get("charge"), "payment_intent": rd.get("payment_intent"),
                    "created": rd.get("created")})
    for d in stripe.Dispute.list(created=window, limit=100).auto_paging_iter():
        dd = d.to_dict() if hasattr(d, "to_dict") else dict(d)
        if dd.get("status") in _DISPUTE_NO_CLAWBACK:
            continue
        out.append({"kind": "dispute", "id": dd.get("id"), "amount": int(dd.get("amount") or 0),
                    "charge": dd.get("charge"), "payment_intent": dd.get("payment_intent"),
                    "created": dd.get("created")})
    return out


def _id_of(v):
    if isinstance(v, dict):
        return v.get("id")
    return v if isinstance(v, str) else None


def _invoice_for_reversal(ev):
    """The paid invoice (dict, discounts expanded) a refund/dispute reverses,
    or None. API 2025+ links payments to invoices via InvoicePayment; older
    APIs carried charge.invoice. Never raises."""
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
        log.warning("reversal %s: invoice lookup failed: %s", ev.get("id"), e)
        return None


def _compute(affiliates, year: int, month: int, referrals_by_sub=None) -> list[dict]:
    """Pure core (testable): given a list of affiliate objects, read Stripe paid
    invoices for the month and return per-(affiliate, currency) totals.

    referrals_by_sub: optional {stripe_subscription_id: affiliate_id} map (the
    PERSISTED attribution). When a referral matches it takes precedence over the
    coupon, so commission keeps flowing after the 12-month discount coupon leaves
    the invoice. The coupon is the fallback / corroborating signal.

    Two passes:
      1. every invoice PAID in the month -> a positive line
         (basis = amount_paid - tax);
      2. every refund / money-withdrawing dispute CREATED in the month whose
         invoice earned commission -> a NEGATIVE line at the same rate (the
         clawback; can make a month's total negative, which upsert_month
         carries forward into the next payable month).

    Each result dict: affiliate_id, code, name, payout_email, currency,
    gross_revenue (Decimal), commission_amount (Decimal), period_start/end
    (date), detail (list of per-invoice lines). Sorted by commission desc.
    """
    start, end, period_start, period_end = _month_window(year, month)

    referrals_by_sub = referrals_by_sub or {}
    by_id = {str(a.id): a for a in affiliates}
    by_coupon = {a.stripe_coupon_id: a for a in affiliates if a.stripe_coupon_id}
    if not by_id:
        return []

    acc: dict = {}
    first_paid_cache: dict = {}
    unattributed: list = []

    def attribute(invd):
        """1) persisted referral (subscription -> affiliate) wins; 2) else the
        affiliate coupon on the invoice (fallback / corroboration)."""
        sub_id = _invoice_subscription_id(invd)
        if sub_id and sub_id in referrals_by_sub:
            hit = by_id.get(referrals_by_sub[sub_id])
            if hit is not None:
                return hit
        matches = [by_coupon[cid] for cid in _invoice_coupon_ids(invd) if cid in by_coupon]
        if matches:
            if len({m.stripe_coupon_id for m in matches}) > 1:
                log.warning("invoice %s carries %d affiliate coupons; attributing "
                            "to the first (%s) - needs review", invd.get("id"),
                            len(matches), matches[0].code)
            return matches[0]
        return None

    def is_self_referral(aff, invd):
        cust_email = (invd.get("customer_email") or "").strip().lower()
        aff_email = (getattr(aff, "email", None) or "").strip().lower()
        return bool(aff_email and cust_email and cust_email == aff_email)

    def earns(aff, invd):
        """Does this invoice earn commission under the affiliate's model?"""
        model = getattr(aff, "commission_model", None) or "recurring"
        if model not in ("first_payment", "duration_12mo"):
            return True
        sub_id = _invoice_subscription_id(invd)
        cust = invd.get("customer")
        # Anchor the window on the SUBSCRIPTION's first paid invoice whenever
        # the sub id is known (coupon-independent, so it survives a later
        # discount/coupon swap via Change-terms). Fall back to the coupon anchor
        # only when the subscription id is unknown.
        if sub_id:
            akey = ("sub", sub_id)
            if cust and akey not in first_paid_cache:
                first_paid_cache[akey] = _earliest_paid_invoice(cust, subscription_id=sub_id)
        else:
            akey = ("coupon", cust, aff.stripe_coupon_id)
            if cust and akey not in first_paid_cache:
                first_paid_cache[akey] = _earliest_paid_invoice(cust, coupon_id=aff.stripe_coupon_id)
        first_dt, first_id = first_paid_cache.get(akey, (None, None))
        if model == "first_payment":
            # Qualify by invoice IDENTITY, not a time window: only the single
            # earliest attributed invoice earns, so proration/true-up invoices
            # minted minutes apart don't double-pay the commission.
            return bool(first_id) and invd.get("id") == first_id
        inv_dt = dt.datetime.fromtimestamp(invd.get("created") or 0, tz=dt.timezone.utc)
        return first_dt is None or inv_dt <= first_dt + dt.timedelta(days=365)

    def add_line(aff, invd, basis, kind, extra):
        currency = (invd.get("currency") or "usd").lower()
        # Interval-split affiliates earn a different rate on monthly vs annual
        # invoices; flat affiliates fall back to commission_pct for both.
        interval = _invoice_interval(invd)
        comm_pct = effective_commission_pct(aff, interval)
        rate = Decimal(str(comm_pct)) / Decimal(100)
        commission_raw = basis * rate          # unrounded; the per-(affiliate,
        commission = commission_raw.quantize(_CENTS, rounding=ROUND_HALF_UP)  # currency)
        #                                        TOTAL is rounded once at the end.
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
                "currency": currency,
                "gross_revenue": Decimal("0.00"),
                "commission_amount": Decimal("0.00"),
                "period_start": period_start,
                "period_end": period_end,
                "detail": [],
            }
            acc[key] = entry
        entry["gross_revenue"] += basis
        entry["commission_amount"] += commission_raw
        line = {
            "kind": kind,
            "invoice": invd.get("id"),
            "customer": invd.get("customer"),
            "basis": str(basis),
            "interval": interval,
            "rate_pct": str(comm_pct),
            "commission": str(commission),
        }
        line.update(extra)
        entry["detail"].append(line)

    # --- pass 1: payments ---------------------------------------------------
    listing = stripe.Invoice.list(
        status="paid",
        created={"gte": int(start.timestamp()), "lt": int(end.timestamp())},
        limit=100,
        expand=["data.discounts"],
    )
    for inv in listing.auto_paging_iter():
        invd = inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)
        aff = attribute(invd)
        if aff is None:
            # A discounted invoice we can't attribute to a known ACTIVE affiliate
            # -> surface it rather than silently dropping money.
            if _invoice_coupon_ids(invd):
                unattributed.append(invd.get("id"))
            continue
        if is_self_referral(aff, invd):
            log.info("affiliate %s: skipping self-referral invoice %s",
                     aff.code, invd.get("id"))
            continue
        amount_paid = int(invd.get("amount_paid") or 0)
        tax_cents = _invoice_tax_cents(invd)
        # Commission basis = what Company kept: paid less tax. Refunds and
        # disputes are netted in pass 2, dated when the money actually left.
        basis_cents = max(0, amount_paid - tax_cents)
        if basis_cents <= 0 or not earns(aff, invd):
            continue
        add_line(aff, invd, Decimal(basis_cents) / Decimal(100), "payment", {
            "amount_paid_cents": amount_paid,
            "tax_cents": tax_cents,
            "created": invd.get("created"),
        })

    # --- pass 2: refunds + disputes (clawback) ------------------------------
    # Deliberately NOT caught: if Stripe can't list refunds/disputes, the
    # compute fails rather than over-paying with the clawback silently skipped.
    reversals = _month_reversals(start, end)
    for ev in reversals:
        invd = _invoice_for_reversal(ev)
        if not invd:
            continue
        aff = attribute(invd)
        if aff is None or is_self_referral(aff, invd) or not earns(aff, invd):
            continue
        amount_paid = int(invd.get("amount_paid") or 0)
        if amount_paid <= 0:
            continue
        tax_cents = _invoice_tax_cents(invd)
        # Strip the tax share out of the reversed amount (pro rata) and never
        # claw back more than the invoice's own basis.
        inv_basis = max(0, amount_paid - tax_cents)
        rev_cents = min(ev["amount"], amount_paid)
        rev_basis = (Decimal(rev_cents) * Decimal(inv_basis) / Decimal(amount_paid))
        rev_basis = min(rev_basis, Decimal(inv_basis)).quantize(_CENTS) / Decimal(100)
        if rev_basis <= 0:
            continue
        add_line(aff, invd, -rev_basis, ev["kind"], {
            ev["kind"]: ev["id"],
            "reversed_cents": rev_cents,
            "created": ev.get("created"),
        })

    if unattributed:
        log.warning("compute %04d-%02d: %d discounted invoice(s) with NO active-affiliate "
                    "attribution (neither referral nor coupon) - unpaid, needs review: %s",
                    year, month, len(unattributed), unattributed[:25])

    out = []
    for entry in acc.values():
        # Quantize the TOTALS once (avoids per-invoice rounding drift).
        entry["gross_revenue"] = entry["gross_revenue"].quantize(_CENTS)
        entry["commission_amount"] = entry["commission_amount"].quantize(_CENTS, rounding=ROUND_HALF_UP)
        out.append(entry)
    out.sort(key=lambda e: e["commission_amount"], reverse=True)
    return out


def carry_ref(period_start) -> str:
    """external_ref stamped on a negative row that was folded into a later
    month's payout (clawback carry-forward)."""
    return "carried:%s" % period_start.strftime("%Y-%m")


def _apply_carry(session, rows, period_start):
    """Clawback carry-forward. A month whose refunds/disputes outweigh its
    sales ends NEGATIVE; that debt is folded into the affiliate's next month
    with activity in the same currency (so we never pay out while they owe us).

    For each computed (affiliate, currency) row, collect EARLIER negative rows
    that are still pending (or already carried into THIS period by a previous
    run - keeps re-runs idempotent), add them to this row's commission, record
    them in detail["carry_in"], and mark them void with external_ref
    carried:<this period>. Mutates `rows`; returns the carried row objects."""
    from models import AffiliatePayout
    ref = carry_ref(period_start)
    carried = []
    for r in rows:
        prior = (session.query(AffiliatePayout)
                 .filter(AffiliatePayout.affiliate_id == r["affiliate_id"],
                         AffiliatePayout.currency == r["currency"],
                         AffiliatePayout.period_start < period_start,
                         AffiliatePayout.commission_amount < 0,
                         ((AffiliatePayout.status == "pending")
                          | ((AffiliatePayout.status == "void")
                             & (AffiliatePayout.external_ref == ref))))
                 .order_by(AffiliatePayout.period_start).all())
        if not prior:
            continue
        carry = sum((p.commission_amount for p in prior), Decimal("0.00"))
        r["commission_amount"] = (r["commission_amount"] + carry).quantize(_CENTS)
        r["carry_in"] = [{"period": p.period_start.isoformat(),
                          "amount": str(p.commission_amount)} for p in prior]
        for p in prior:
            p.status = "void"
            p.external_ref = ref
            carried.append(p)
    return carried


def upsert_month(session, year: int, month: int) -> list:
    """Compute the month and INSERT pending ledger rows, idempotent on the
    (affiliate_id, period_start, currency) unique key. A still-PENDING, UNLOCKED
    row is refreshed with the latest numbers (so a re-run picks up late-settling
    invoices); rows that are paid, void, or LOCKED (hand-adjusted) are frozen.
    Earlier negative (clawback) months are carried into this month - see
    _apply_carry. Returns the AffiliatePayout rows for the period."""
    from models import AffiliatePayout
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    rows = compute_month(session, year, month)
    period_start = dt.date(year, month, 1)
    # Only carry into rows we are actually allowed to (re)write: a frozen
    # (paid/void/locked) row for this period keeps its numbers, so its debt
    # stays pending for the next month instead.
    frozen = {(str(p.affiliate_id), p.currency) for p in
              session.query(AffiliatePayout)
              .filter(AffiliatePayout.period_start == period_start,
                      (AffiliatePayout.status != "pending") | AffiliatePayout.locked.is_(True))}
    _apply_carry(session, [r for r in rows
                           if (r["affiliate_id"], r["currency"]) not in frozen],
                 period_start)
    tbl = AffiliatePayout.__table__
    now = dt.datetime.now(dt.timezone.utc)
    for r in rows:
        detail = {"lines": r["detail"]}
        if r.get("carry_in"):
            detail["carry_in"] = r["carry_in"]
        stmt = pg_insert(tbl).values(
            affiliate_id=r["affiliate_id"],
            period_start=r["period_start"],
            period_end=r["period_end"],
            currency=r["currency"],
            gross_revenue=r["gross_revenue"],
            commission_amount=r["commission_amount"],
            status="pending",
            detail=detail,
        ).on_conflict_do_update(
            # Refresh a still-PENDING, UNLOCKED row with the latest numbers so a
            # re-run picks up late-settling invoices instead of keeping the first
            # (under-counted) result. Rows marked paid/void, OR locked (the
            # operator hand-adjusted them), are FROZEN - the WHERE guard leaves
            # them untouched.
            constraint="uq_affiliate_payout_period",
            set_={
                "gross_revenue": r["gross_revenue"],
                "commission_amount": r["commission_amount"],
                "detail": detail,
                "computed_at": now,
            },
            where=((tbl.c.status == "pending") & (tbl.c.locked.is_(False))),
        )
        session.execute(stmt)
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


def record_signup_referral(session, user, raw_code) -> bool:
    """First-touch: stamp a brand-new user with the affiliate whose tw_ref
    code they arrived with. Never overwrites an existing stamp, skips
    self-referral and inactive codes. Commits; returns True if stamped."""
    if user is None or getattr(user, "referred_by_affiliate_id", None):
        return False
    aff = active_affiliate_by_code(session, raw_code)
    if aff is None:
        return False
    if (aff.email or "").strip().lower() == (user.email or "").strip().lower():
        return False
    user.referred_by_affiliate_id = aff.id
    user.referred_at = dt.datetime.now(dt.timezone.utc)
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
    stays the number of record). Reads Stripe, writes nothing. Same attribution
    rules as compute_month; referrals are pre-filtered to this affiliate so a
    coupon-only match for a DIFFERENT affiliate can never leak in.

    NOTE: this walks the month's paid invoices like compute_month does - the
    portal caches the result (~1h) per (affiliate, month); do not call it per
    page element."""
    from models import AffiliateReferral
    referrals_by_sub = {
        r.stripe_subscription_id: str(r.affiliate_id)
        for r in (session.query(AffiliateReferral)
                  .filter(AffiliateReferral.affiliate_id == affiliate.id).all())
    }
    return _compute([affiliate], year, month, referrals_by_sub)
