"""Standalone promo coupons - Stripe glue (NO affiliate / commission / payout).

Create a plain marketing discount code: percent off, fixed-amount off,
free/100%, with optional expiry + max-redemptions. One Stripe coupon + one
promotion code per row (1:1). Pure Stripe writes - no billing/webhook changes.
Reuses the affiliate code-string rules (normalize/validate). On dev
STRIPE_SECRET_KEY is a test key, so these are disposable test objects.
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from pathlib import Path

import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import stripe  # noqa: E402
import config  # noqa: E402
from affiliate_service import normalize_code, validate_code, AffiliateError  # noqa: E402

log = logging.getLogger(__name__)
stripe.api_key = config.STRIPE_SECRET_KEY


class PromoError(Exception):
    """Bad input or Stripe failure creating a standalone promo coupon."""


def validate_promo(promo) -> None:
    """Validate a promo row's discount shape before we touch Stripe."""
    try:
        validate_code(normalize_code(promo.code))
    except AffiliateError as e:
        raise PromoError(str(e)) from e

    dtype = promo.discount_type
    if dtype not in ("percent", "amount"):
        raise PromoError("discount_type must be 'percent' or 'amount'")

    if dtype == "percent":
        if promo.percent_off is None:
            raise PromoError("percent_off is required for a percent coupon")
        p = float(Decimal(str(promo.percent_off)))
        if not (0 < p <= 100):
            raise PromoError("percent_off must be > 0 and <= 100 (use 100 for free/comp)")
        if promo.amount_off_cents:
            raise PromoError("leave amount_off_cents blank for a percent coupon")
    else:  # amount
        if not promo.amount_off_cents or int(promo.amount_off_cents) <= 0:
            raise PromoError("amount_off_cents must be a positive integer (cents) for an amount coupon")
        if not promo.currency:
            raise PromoError("currency is required for an amount coupon (e.g. usd)")
        if promo.percent_off is not None:
            raise PromoError("leave percent_off blank for an amount coupon")

    if promo.duration not in ("once", "repeating", "forever"):
        raise PromoError("duration must be once / repeating / forever")
    if promo.duration == "repeating" and not promo.duration_in_months:
        raise PromoError("duration_in_months is required when duration is 'repeating'")
    if promo.max_redemptions is not None and int(promo.max_redemptions) <= 0:
        raise PromoError("max_redemptions must be a positive integer")
    if promo.expires_at is not None:
        exp = promo.expires_at
        if exp.tzinfo is None:           # admin form yields naive -> treat as UTC
            exp = exp.replace(tzinfo=dt.timezone.utc)
        if exp <= dt.datetime.now(dt.timezone.utc):
            raise PromoError("expires_at must be in the future")


def provision_promo_coupon(promo) -> tuple[str, str]:
    """Create the Stripe coupon + promotion code for a promo row. Idempotent if
    both ids are already present. Raises PromoError on bad input / Stripe
    failure; best-effort deletes an orphan coupon if promo-code creation fails."""
    if promo.stripe_coupon_id and promo.stripe_promotion_code_id:
        return promo.stripe_coupon_id, promo.stripe_promotion_code_id

    validate_promo(promo)
    code = normalize_code(promo.code)

    coupon_kwargs = dict(
        duration=promo.duration,
        name=f"Promo {code}"[:40],
        metadata={"tw2_promo_code": code, "tw2_purpose": "promo"},
    )
    if promo.duration == "repeating":
        coupon_kwargs["duration_in_months"] = int(promo.duration_in_months)
    if promo.discount_type == "percent":
        coupon_kwargs["percent_off"] = float(Decimal(str(promo.percent_off)))
    else:
        coupon_kwargs["amount_off"] = int(promo.amount_off_cents)
        coupon_kwargs["currency"] = (promo.currency or "usd").lower()

    try:
        coupon = stripe.Coupon.create(**coupon_kwargs)
    except Exception as e:
        raise PromoError(f"Stripe coupon create failed: {e}") from e

    # SDK 15.x: coupon nests under `promotion`, not a top-level `coupon` param.
    promo_kwargs = dict(
        code=code,
        promotion={"type": "coupon", "coupon": coupon.id},
        metadata={"tw2_promo_code": code, "tw2_purpose": "promo"},
    )
    if promo.max_redemptions:
        promo_kwargs["max_redemptions"] = int(promo.max_redemptions)
    if promo.expires_at:
        exp = promo.expires_at
        if exp.tzinfo is None:           # naive admin-form value -> treat as UTC
            exp = exp.replace(tzinfo=dt.timezone.utc)
        promo_kwargs["expires_at"] = int(exp.timestamp())

    try:
        pc = stripe.PromotionCode.create(**promo_kwargs)
    except Exception as e:
        try:
            stripe.Coupon.delete(coupon.id)
        except Exception:
            log.warning("orphan promo coupon %s after promo-code failure", coupon.id)
        raise PromoError(f"Stripe promotion code create failed: {e}") from e

    return coupon.id, pc.id


def set_promo_active(promo, active: bool) -> None:
    """Activate / archive: flip the Stripe promotion code's `active` flag so an
    archived coupon stops being redeemable (the coupon itself is left intact)."""
    if not promo.stripe_promotion_code_id:
        return
    try:
        stripe.PromotionCode.modify(promo.stripe_promotion_code_id, active=bool(active))
    except Exception as e:
        raise PromoError(f"Stripe promotion code update failed: {e}") from e
