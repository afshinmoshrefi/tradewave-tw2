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

import sys
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

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
    cid = getattr(aff, "stripe_coupon_id", None)
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


def _invoice_refunded_cents(invd) -> int:
    """Post-payment refunds on the invoice, issued as credit notes after it was
    paid (Stripe's recommended way to refund an invoiced subscription charge).
    Subtracted from the commission basis. NOTE: direct charge refunds / disputes
    NOT issued as a credit note are not reflected here and still need manual
    netting at payout review."""
    v = invd.get("post_payment_credit_notes_amount")
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


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


def _compute(affiliates, year: int, month: int, referrals_by_sub=None) -> list[dict]:
    """Pure core (testable): given a list of affiliate objects, read Stripe paid
    invoices for the month and return per-(affiliate, currency) totals.

    referrals_by_sub: optional {stripe_subscription_id: affiliate_id} map (the
    PERSISTED attribution). When a referral matches it takes precedence over the
    coupon, so commission keeps flowing after the 12-month discount coupon leaves
    the invoice. The coupon is the fallback / corroborating signal.

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

    listing = stripe.Invoice.list(
        status="paid",
        created={"gte": int(start.timestamp()), "lt": int(end.timestamp())},
        limit=100,
        expand=["data.discounts"],
    )
    for inv in listing.auto_paging_iter():
        invd = inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)

        # Attribution: 1) persisted referral (subscription -> affiliate) wins;
        # 2) else the affiliate coupon on the invoice (fallback / corroboration).
        aff = None
        sub_id = _invoice_subscription_id(invd)
        if sub_id and sub_id in referrals_by_sub:
            aff = by_id.get(referrals_by_sub[sub_id])
        if aff is None:
            matches = [by_coupon[cid] for cid in _invoice_coupon_ids(invd) if cid in by_coupon]
            if matches:
                aff = matches[0]
                if len({m.stripe_coupon_id for m in matches}) > 1:
                    log.warning("invoice %s carries %d affiliate coupons; attributing "
                                "to the first (%s) - needs review", invd.get("id"),
                                len(matches), aff.code)
        if aff is None:
            # A discounted invoice we can't attribute to a known ACTIVE affiliate
            # -> surface it rather than silently dropping money.
            if _invoice_coupon_ids(invd):
                unattributed.append(invd.get("id"))
            continue

        # self-referral guard: an affiliate can't earn commission on themselves.
        cust_email = (invd.get("customer_email") or "").strip().lower()
        aff_email = (getattr(aff, "email", None) or "").strip().lower()
        if aff_email and cust_email and cust_email == aff_email:
            log.info("affiliate %s: skipping self-referral invoice %s",
                     aff.code, invd.get("id"))
            continue

        amount_paid = int(invd.get("amount_paid") or 0)
        tax_cents = _invoice_tax_cents(invd)
        refunded_cents = _invoice_refunded_cents(invd)
        # Commission basis = what Company actually kept: paid, less tax, less
        # post-payment refunds (credit notes). Matches the agreement's Net Revenue.
        basis_cents = max(0, amount_paid - tax_cents - refunded_cents)
        if basis_cents <= 0:
            continue

        model = getattr(aff, "commission_model", None) or "recurring"
        if model in ("first_payment", "duration_12mo"):
            cust = invd.get("customer")
            # Anchor the window on the SUBSCRIPTION's first paid invoice whenever
            # the sub id is known (coupon-independent, so it survives a later
            # discount/coupon swap via Change-terms - whether the hit is a
            # persisted referral or a coupon-only match). Fall back to the coupon
            # anchor only when the subscription id is unknown.
            if sub_id:
                akey = ("sub", sub_id)
                if cust and akey not in first_paid_cache:
                    first_paid_cache[akey] = _earliest_paid_invoice(cust, subscription_id=sub_id)
                first_dt, first_id = first_paid_cache.get(akey, (None, None))
            else:
                ckey = ("coupon", cust, aff.stripe_coupon_id)
                if cust and ckey not in first_paid_cache:
                    first_paid_cache[ckey] = _earliest_paid_invoice(cust, coupon_id=aff.stripe_coupon_id)
                first_dt, first_id = first_paid_cache.get(ckey, (None, None))
            if model == "first_payment":
                # Qualify by invoice IDENTITY, not a time window: only the single
                # earliest coupon-attributed invoice earns, so proration/true-up
                # invoices minted minutes apart don't double-pay the commission.
                if not first_id or invd.get("id") != first_id:
                    continue
            elif model == "duration_12mo":
                inv_dt = dt.datetime.fromtimestamp(invd.get("created") or 0,
                                                   tz=dt.timezone.utc)
                if first_dt is not None and inv_dt > first_dt + dt.timedelta(days=365):
                    continue

        currency = (invd.get("currency") or "usd").lower()
        rate = Decimal(str(aff.commission_pct)) / Decimal(100)
        basis = (Decimal(basis_cents) / Decimal(100))
        commission_raw = basis * rate                        # unrounded; the per-(affiliate,
        commission = commission_raw.quantize(_CENTS, rounding=ROUND_HALF_UP)  # currency) TOTAL is
        #                                                      rounded once at the end (no per-line drift).

        key = (str(aff.id), currency)
        entry = acc.get(key)
        if entry is None:
            entry = {
                "affiliate_id": str(aff.id),
                "code": aff.code,
                "name": aff.name,
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
        entry["commission_amount"] += commission_raw   # accumulate UNROUNDED; quantized once below
        entry["detail"].append({
            "invoice": invd.get("id"),
            "customer": invd.get("customer"),
            "amount_paid_cents": amount_paid,
            "tax_cents": tax_cents,
            "refunded_cents": refunded_cents,
            "basis": str(basis),
            "rate_pct": str(aff.commission_pct),
            "commission": str(commission),
            "created": invd.get("created"),
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


def upsert_month(session, year: int, month: int) -> list:
    """Compute the month and INSERT pending ledger rows, idempotent on the
    (affiliate_id, period_start, currency) unique key. A still-PENDING, UNLOCKED
    row is refreshed with the latest numbers (so a re-run picks up late-settling
    invoices); rows that are paid, void, or LOCKED (hand-adjusted, e.g. a netted
    refund) are frozen. Returns the AffiliatePayout rows for the period."""
    from models import AffiliatePayout
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    rows = compute_month(session, year, month)
    tbl = AffiliatePayout.__table__
    now = dt.datetime.now(dt.timezone.utc)
    for r in rows:
        stmt = pg_insert(tbl).values(
            affiliate_id=r["affiliate_id"],
            period_start=r["period_start"],
            period_end=r["period_end"],
            currency=r["currency"],
            gross_revenue=r["gross_revenue"],
            commission_amount=r["commission_amount"],
            status="pending",
            detail={"lines": r["detail"]},
        ).on_conflict_do_update(
            # Refresh a still-PENDING, UNLOCKED row with the latest numbers so a
            # re-run picks up late-settling invoices instead of keeping the first
            # (under-counted) result. Rows marked paid/void, OR locked (the
            # operator hand-adjusted them, e.g. netted a refund), are FROZEN -
            # the WHERE guard leaves them untouched.
            constraint="uq_affiliate_payout_period",
            set_={
                "gross_revenue": r["gross_revenue"],
                "commission_amount": r["commission_amount"],
                "detail": {"lines": r["detail"]},
                "computed_at": now,
            },
            where=((tbl.c.status == "pending") & (tbl.c.locked.is_(False))),
        )
        session.execute(stmt)
    session.commit()

    period_start = dt.date(year, month, 1)
    return (session.query(AffiliatePayout)
            .filter(AffiliatePayout.period_start == period_start)
            .order_by(AffiliatePayout.commission_amount.desc())
            .all())
