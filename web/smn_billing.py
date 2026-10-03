"""Isolated SMN Checkout and paid-period authority using an instance Stripe client."""
from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

import stripe
from sqlalchemy.exc import IntegrityError
from models import (Session, SmnSettings, SmnOffer, SmnMembership, SmnGrant,
                    StripeEvent, StripeCheckoutClaim, AuditLog)
from checkout_claims import (reserve_checkout, complete_checkout, release_checkout,
                             consume_checkout, CheckoutClaimError)
from smn_membership import MembershipError, now_utc, active_offer, integer

API_VERSION = "2026-08-26.dahlia"
INTEGRATION_IDENTIFIER = "tw2_smn_reader_qhdkmzpa"


def readiness(environment):
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    mode = "test" if key.startswith(("sk_test_", "rk_test_")) else "live" if key.startswith(("sk_live_", "rk_live_")) else "unconfigured"
    enabled = os.environ.get("TW2_SMN_BILLING_ENABLED", "").lower() in ("1", "true", "yes")
    return dict(billing_enabled=enabled and (mode == "test" if environment == "dev" else mode == "live"),
                stripe_mode=mode, api_version=API_VERSION,
                refund_dispute_policy="Recorded for administrator review; no automatic SMN revocation. Live billing requires a reviewed policy.")


def client(environment):
    if not readiness(environment)["billing_enabled"]:
        raise MembershipError("billing_not_ready", 503)
    return stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"], stripe_version=API_VERSION,
                max_network_retries=2, http_client=stripe._http_client.RequestsClient(timeout=10))


def plain(obj):
    return obj.to_dict_recursive() if hasattr(obj, "to_dict_recursive") else obj


def obj_id(value):
    return value.get("id") if isinstance(value, dict) else value


def timestamp(value):
    if type(value) is not int or value <= 0:
        raise MembershipError("invalid_provider_period", 409)
    return datetime.fromtimestamp(value, timezone.utc)


def metadata(offer, user_id):
    return dict(product_line="smn", tw2_user_id=str(user_id), smn_offer_id=str(offer.id))


def verify_price(price, offer, interval):
    expected = offer.monthly_amount if interval == "month" else offer.annual_amount
    if not price.get("active") or obj_id(price.get("product")) != offer.stripe_product_id or price.get("currency") != offer.currency or price.get("unit_amount") != expected or (price.get("recurring") or {}).get("interval") != interval or (price.get("recurring") or {}).get("interval_count", 1) != 1:
        raise MembershipError("provider_price_binding_mismatch", 409)


def provision_offer(o, provider):
    product = plain(provider.v1.products.create(params={"name": "Seasonal Market News membership", "metadata": {"product_line": "smn", "smn_offer_id": str(o.id)}}, options={"idempotency_key": f"smn-offer-{o.id}-product"}))
    o.stripe_product_id = product["id"]
    for interval in o.intervals:
        price = plain(provider.v1.prices.create(params={"product": o.stripe_product_id, "currency": o.currency,
            "unit_amount": o.monthly_amount if interval == "month" else o.annual_amount,
            "recurring": {"interval": interval}, "metadata": {"product_line": "smn", "smn_offer_id": str(o.id)}},
            options={"idempotency_key": f"smn-offer-{o.id}-{interval}"}))
        verify_price(price, o, interval)
        setattr(o, "stripe_monthly_price_id" if interval == "month" else "stripe_annual_price_id", price["id"])


def activate_offer(s, actor, data, environment):
    setting = s.query(SmnSettings).filter_by(id=1).with_for_update().one()
    if data.get("expected_version") != setting.version:
        raise MembershipError("settings_version_conflict", 409)
    draft_id = integer(data.get("draft_id"), "draft_id", minimum=1)
    offer = s.get(SmnOffer, draft_id)
    if not offer or offer.activated_at:
        raise MembershipError("offer_is_not_draft", 409)
    if offer.mode == "paid":
        provider = client(environment)
        provision_offer(offer, provider)
    before = setting.active_offer_id
    offer.activated_at = now_utc()
    setting.active_offer_id, setting.version = offer.id, setting.version + 1
    s.add(AuditLog(actor_user_id=actor.id, action="smn_offer_activated", details={"before": before, "after": offer.id, "existing_grants_unchanged": True}))


def account_origin():
    origin = os.environ.get("TW2_SMN_READER_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise MembershipError("reader_origin_not_configured", 503)
    return origin


def create_checkout(s, user, data, environment, session_factory=Session):
    member = s.query(SmnMembership).filter_by(user_id=user.id).with_for_update().one()
    offer = active_offer(s)
    if offer.mode == "free":
        raise MembershipError("free_membership_requires_no_checkout", 409)
    if type(data.get("offer_version")) is not int or data["offer_version"] != offer.id:
        raise MembershipError("offer_version_conflict", 409)
    interval = data.get("interval")
    if interval not in offer.intervals:
        raise MembershipError("interval_not_enabled", 409)
    if member.suspended_at:
        raise MembershipError("membership_suspended", 403)
    provider = client(environment)
    if member.stripe_subscription_id:
        current = plain(provider.v1.subscriptions.retrieve(member.stripe_subscription_id))
        validate_subscription(current, member, s.get(SmnOffer, member.subscription_offer_id))
        if current.get("status") not in ("canceled", "incomplete_expired"):
            raise MembershipError("subscription_already_exists", 409)
        member.stripe_subscription_id = None
        member.subscription_offer_id = None
    subscription_data = {"metadata": metadata(offer, user.id)}
    if member.first_trial_ends_at and member.first_trial_ends_at > now_utc():
        remaining = (member.first_trial_ends_at - now_utc()).total_seconds()
        # Stripe Checkout trial_end needs at least 48 hours, and a maximum 730d.
        # Include one minute margin; never move the recorded grant boundary.
        if remaining < 48 * 3600 + 60:
            raise MembershipError("checkout_deferred_until_trial_end", 409)
        subscription_data["trial_end"] = int(member.first_trial_ends_at.timestamp())
    price_id = offer.stripe_monthly_price_id if interval == "month" else offer.stripe_annual_price_id
    verify_price(plain(provider.v1.prices.retrieve(price_id)), offer, interval)
    if not member.stripe_customer_id:
        customer = plain(provider.v1.customers.create(params={"email": user.email, "metadata": {"product_line": "smn", "tw2_user_id": str(user.id)}},
                    options={"idempotency_key": f"smn-customer-{user.id}"}))
        member.stripe_customer_id = customer["id"]
    customer = plain(provider.v1.customers.retrieve(member.stripe_customer_id))
    if customer.get("deleted") or customer.get("metadata", {}).get("tw2_user_id") != str(user.id) or customer.get("metadata", {}).get("product_line") != "smn":
        raise MembershipError("provider_customer_binding_mismatch", 409)
    origin = account_origin()
    payload = dict(mode="subscription", customer=member.stripe_customer_id,
        client_reference_id=str(user.id), line_items=[dict(price=price_id, quantity=1)],
        metadata=metadata(offer, user.id), subscription_data=subscription_data,
        success_url=origin + "/member/account?checkout=returned", cancel_url=origin + "/member/account",
        integration_identifier=INTEGRATION_IDENTIFIER, expires_at=int(now_utc().timestamp()) + 3600)
    # Commit customer identity before the reusable claim opens its own transaction.
    s.commit()
    try:
        reservation = reserve_checkout(user.id, "smn", payload, session_factory=session_factory)
    except CheckoutClaimError:
        raise MembershipError("checkout_in_progress", 409) from None
    if reservation.session_id:
        return dict(url=reservation.session_url, session_id=reservation.session_id, reused=True)
    try:
        checkout = plain(provider.v1.checkout.sessions.create(params=reservation.payload,
                              options={"idempotency_key": reservation.idempotency_key}))
        complete_checkout(reservation, checkout["id"], checkout["url"], session_factory=session_factory)
    except Exception:
        release_checkout(reservation, session_factory=session_factory)
        raise MembershipError("checkout_provider_unavailable", 503) from None
    return dict(url=checkout["url"], session_id=checkout["id"], reused=False)


def validate_subscription(sub, member, offer):
    meta = sub.get("metadata") or {}
    items = (sub.get("items") or {}).get("data") or []
    if not offer or obj_id(sub.get("customer")) != member.stripe_customer_id or meta != {**meta, **metadata(offer, member.user_id)} or len(items) != 1:
        raise MembershipError("provider_subscription_binding_mismatch", 409)
    item = items[0]
    price = item.get("price") or {}
    price_id = obj_id(price)
    interval = "month" if price_id == offer.stripe_monthly_price_id else "year" if price_id == offer.stripe_annual_price_id else None
    if interval is None or interval not in offer.intervals or item.get("quantity", 1) != 1:
        raise MembershipError("provider_subscription_binding_mismatch", 409)
    # A canceled subscription may refer to a price archived for new enrollment.
    verify_price({**price, "active": True}, offer, interval)
    return interval


def cancel_subscription(s, user, data, environment):
    requested = data.get("cancel_at_period_end", True)
    if type(requested) is not bool:
        raise MembershipError("invalid_cancel_at_period_end")
    member = s.query(SmnMembership).filter_by(user_id=user.id).with_for_update().one()
    if not member.stripe_subscription_id:
        raise MembershipError("smn_subscription_not_found", 404)
    provider = client(environment)
    current = plain(provider.v1.subscriptions.retrieve(member.stripe_subscription_id))
    validate_subscription(current, member, s.get(SmnOffer, member.subscription_offer_id))
    if current.get("status") in ("canceled", "incomplete_expired"):
        raise MembershipError("subscription_is_closed", 409)
    updated = plain(provider.v1.subscriptions.update(member.stripe_subscription_id,
        params={"cancel_at_period_end": requested},
        options={"idempotency_key": f"smn-cancel-{uuid.uuid4().hex}"}))
    validate_subscription(updated, member, s.get(SmnOffer, member.subscription_offer_id))
    member.cancel_at_period_end = bool(updated.get("cancel_at_period_end"))
    s.add(AuditLog(actor_user_id=user.id, action="smn_subscription_cancel_setting", details={"subscription_id": member.stripe_subscription_id, "cancel_at_period_end": requested}))
    return dict(cancel_at_period_end=member.cancel_at_period_end)


def subscription_id(obj):
    return obj_id(obj.get("subscription")) or obj_id(((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))


def handle_event(event, environment, *, session_factory=Session, provider=None):
    """Return None for another product. Verified signatures are the caller's job.

    Current provider subscription/invoice state makes replay order irrelevant;
    only confirmed invoice line service periods create paid grants.
    """
    typ = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    sid = obj.get("id") if typ.startswith("customer.subscription.") else subscription_id(obj)
    with session_factory() as s:
        known = s.query(SmnMembership).filter_by(stripe_subscription_id=sid).one_or_none() if sid else None
        customer = obj_id(obj.get("customer"))
        customer_known = s.query(SmnMembership).filter_by(stripe_customer_id=customer).one_or_none() if customer else None
        if meta.get("product_line") != "smn" and known is None and customer_known is None:
            return None
        if not event.get("id"):
            raise MembershipError("invalid_provider_event", 400)
        receipt = s.query(StripeEvent).filter_by(stripe_event_id=event["id"]).with_for_update().one_or_none()
        if receipt and receipt.processed_at:
            return dict(received=True, duplicate=True, product_line="smn")
        if receipt is None:
            s.add(StripeEvent(stripe_event_id=event["id"], event_type=typ, payload=event))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
            receipt = s.query(StripeEvent).filter_by(stripe_event_id=event["id"]).with_for_update().one()
            if receipt.processed_at:
                return dict(received=True, duplicate=True, product_line="smn")
        if typ.startswith(("charge.refunded", "charge.dispute.")):
            receipt.user_id = customer_known.user_id if customer_known else None
            s.add(AuditLog(actor_label="stripe_smn", action="smn_payment_review_required", target_user_id=receipt.user_id, details={"event_id": event["id"], "event_type": typ}))
        elif sid:
            provider = provider or client(environment)
            live = plain(provider.v1.subscriptions.retrieve(sid, params={"expand": ["latest_invoice"]}))
            live_meta = live.get("metadata") or {}
            try:
                uid = uuid.UUID(live_meta.get("tw2_user_id", ""))
                oid = int(live_meta.get("smn_offer_id", ""))
            except (ValueError, TypeError):
                raise MembershipError("provider_subscription_binding_mismatch", 409) from None
            member = s.query(SmnMembership).filter_by(user_id=uid).with_for_update().one_or_none()
            offer = s.get(SmnOffer, oid)
            if member is None:
                raise MembershipError("provider_membership_binding_mismatch", 409)
            validate_subscription(live, member, offer)
            receipt.user_id = uid
            if member.stripe_subscription_id != sid:
                # A late old cancellation cannot overwrite the current membership.
                if member.stripe_subscription_id or live.get("status") in ("canceled", "incomplete_expired"):
                    receipt.processed_at = now_utc()
                    s.commit()
                    return dict(received=True, ignored="noncurrent_subscription", product_line="smn")
                claim = s.query(StripeCheckoutClaim).filter_by(user_id=uid, product_line="smn").one_or_none()
                if not claim or claim.request_payload.get("metadata") != metadata(offer, uid) or claim.request_payload.get("customer") != member.stripe_customer_id:
                    raise MembershipError("provider_checkout_binding_mismatch", 409)
                member.stripe_subscription_id, member.subscription_offer_id = sid, offer.id
            if typ.startswith("checkout.session."):
                claim = s.query(StripeCheckoutClaim).filter_by(user_id=uid, product_line="smn").with_for_update().one_or_none()
                if not claim or claim.stripe_session_id != obj.get("id") or obj.get("client_reference_id") != str(uid) or obj_id(obj.get("customer")) != member.stripe_customer_id:
                    raise MembershipError("provider_checkout_binding_mismatch", 409)
                consume_checkout(s, uid, "smn", obj["id"])
            member.stripe_subscription_status = live.get("status")
            member.cancel_at_period_end = bool(live.get("cancel_at_period_end"))
            invoice = live.get("latest_invoice")
            if isinstance(invoice, str):
                invoice = plain(provider.v1.invoices.retrieve(invoice))
            if isinstance(invoice, dict):
                apply_paid_invoice(s, member, offer, sid, invoice)
        receipt.processed_at = now_utc()
        s.commit()
        return dict(received=True, product_line="smn")


def apply_paid_invoice(s, member, offer, sid, invoice):
    if invoice.get("status") != "paid" or invoice.get("paid") is False:
        return
    if obj_id(invoice.get("customer")) != member.stripe_customer_id or subscription_id(invoice) != sid:
        raise MembershipError("provider_invoice_binding_mismatch", 409)
    # Zero-value provider trial invoices are not paid-service evidence.
    if not invoice.get("amount_paid") or invoice.get("currency") != offer.currency:
        return
    lines = (invoice.get("lines") or {}).get("data") or []
    valid = []
    for line in lines:
        pid = obj_id(line.get("price")) or obj_id(((line.get("pricing") or {}).get("price_details") or {}).get("price"))
        if pid in (offer.stripe_monthly_price_id, offer.stripe_annual_price_id) and line.get("amount", 0) > 0:
            period = line.get("period") or {}
            valid.append((timestamp(period.get("start")), timestamp(period.get("end"))))
    if len(valid) != 1 or valid[0][1] <= valid[0][0]:
        raise MembershipError("provider_invoice_period_mismatch", 409)
    start, end = valid[0]
    key = "invoice:" + invoice["id"]
    grant = s.query(SmnGrant).filter_by(source_key=key).one_or_none()
    if grant is None:
        s.add(SmnGrant(id=uuid.uuid4(), user_id=member.user_id, source="paid", source_key=key,
                      offer_id=offer.id, starts_at=start, ends_at=end))
    elif grant.user_id != member.user_id or grant.starts_at != start or grant.ends_at != end:
        raise MembershipError("provider_invoice_grant_conflict", 409)
    if member.period_ends_at is None or end > member.period_ends_at:
        member.period_ends_at = end
