"""Billing for the API product. MIRRORS web/app.py's Stripe wiring:

  - _stripe_configured(): refuse when keys are placeholders (503).
  - metadata-only price resolution: a price counts only if its product carries
    product_line=api + tier in {dev,pro,business} (matches the
    stripe_price_metadata in apiserver.tiers.API_TIERS).
  - POST /checkout -> stripe.checkout.Session.create (mode=subscription),
    client_reference_id = user UUID, subscription metadata product_line=api,tier.
  - GET  /manage  -> stripe.billing_portal.Session.create (upgrade / downgrade /
    cancel / card / invoices all happen IN the portal, same as the web tier).

NOTE: Stripe is only ever called at REQUEST time (a logged-in user clicking a
button). Importing this module performs NO Stripe calls. The webhook that flips
the API tier on payment is the web app's existing /webhooks/stripe; this console
does not add a second webhook. See README for the integration note on how the
webhook should map product_line=api events to the API tier.
"""
import os
import logging

import stripe

import config
from apiserver import tiers as api_tiers
from .blueprint import (
    bp, require_login, get_current_user, api_tier_name_for, api_entitlements_for,
)

from flask import render_template, request, redirect, jsonify, url_for

log = logging.getLogger("tw2.api_portal.billing")

# Configure the Stripe SDK exactly like web/app.py (idempotent if the parent
# already set these; importing stripe twice yields the same module object).
stripe.api_key = config.STRIPE_SECRET_KEY
stripe.max_network_retries = 2

# Tiers a customer can subscribe to / switch between (free is the default, not
# a purchasable product). Order = display order, cheapest first.
PURCHASABLE_TIERS = ["dev", "pro", "business"]

# Cache: api_tier_name -> Stripe price object, fetched once per process.
_price_cache = {}


def _stripe_configured():
    if "PLACEHOLDER" in (config.STRIPE_SECRET_KEY or ""):
        return False
    if "PLACEHOLDER" in (config.STRIPE_PUBLISHABLE_KEY or ""):
        return False
    return True


def _public_host():
    return os.environ.get("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")


def _refresh_price_cache():
    """Bucket active Stripe prices by API tier - metadata-only.

    A price is used ONLY if its product carries product_line=api and a tier in
    PURCHASABLE_TIERS. This is the same deterministic, metadata-only approach
    web/app.py uses for the EOD product line, so legacy UMP prices, the EOD
    product line, and placeholders are all ignored (no name collisions).
    """
    if not _stripe_configured():
        return
    valid = set(PURCHASABLE_TIERS)
    for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
        prod = p.product
        if not isinstance(prod, dict):
            prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
        md = prod.get("metadata") or {}
        if (md.get("product_line") or "").strip().lower() != "api":
            continue
        tier = (md.get("tier") or "").strip().lower()
        if tier not in valid:
            continue
        existing = _price_cache.get(tier)
        if existing is not None and getattr(existing, "id", None) != getattr(p, "id", None):
            log.warning(
                "api price_cache: >1 active price for tier %s (%s, %s) - ambiguous; "
                "archive the extra in Stripe. Using last-seen.",
                tier, getattr(existing, "id", "?"), getattr(p, "id", "?"),
            )
        _price_cache[tier] = p


def _price_for_tier(tier_name):
    if not _price_cache:
        _refresh_price_cache()
    return _price_cache.get(tier_name)


@bp.route("/billing")
@require_login
def billing_index():
    u = get_current_user()
    current_tier = api_tier_name_for(u)

    # Build display rows from the single source of truth (apiserver.tiers).
    plans = []
    for name in ["free"] + PURCHASABLE_TIERS:
        t = api_tiers.API_TIERS[name]
        plans.append({
            "name": name,
            "label": t["name"],
            "price_monthly": t["price_monthly"],
            "markets": "1 market" if len(t["markets"]) == 1 else "All %d markets" % len(t["markets"]),
            "ml_access": t["ml_access"],
            "history": t["history"],
            "opp_limit": t["opp_limit"],
            "rate": t["rate"],
            "max_keys": t["max_keys"],
            "is_current": name == current_tier,
            "purchasable": name in PURCHASABLE_TIERS,
        })

    return render_template(
        "api_billing.html",
        user=u,
        plans=plans,
        current_tier=current_tier,
        current_label=api_entitlements_for(u)["name"],
        has_customer=bool(getattr(u, "stripe_customer_id", None)),
        stripe_configured=_stripe_configured(),
    )


@bp.route("/billing/checkout", methods=["POST"])
@require_login
def billing_checkout():
    """Start Stripe Checkout for the requested API tier (monthly).

    Mirrors web/app.py:stripe_create_checkout - validates a stored customer id,
    sets client_reference_id + subscription metadata (product_line=api, tier)
    so the webhook can map the resulting subscription back to this user + the
    API product line.
    """
    if not _stripe_configured():
        return jsonify({
            "error": "stripe_not_configured",
            "message": "Stripe keys are placeholders. Configure them in /etc/tradewave/secrets.env and restart the web tier.",
        }), 503

    tier = (request.form.get("tier") or "").strip().lower()
    if tier not in PURCHASABLE_TIERS:
        return jsonify({"error": "bad_tier", "message": "tier must be one of %s" % PURCHASABLE_TIERS}), 400

    price = _price_for_tier(tier)
    if not price:
        return jsonify({
            "error": "price_not_found",
            "message": "No active Stripe price with metadata product_line=api, tier=%s. "
                       "Run web/api_portal/create_api_products.py (TEST mode) first." % tier,
        }), 400

    u = get_current_user()
    public_host = _public_host()
    success_url = "https://%s/account/api/billing/success?session_id={CHECKOUT_SESSION_ID}" % public_host
    cancel_url = "https://%s/account/api/billing?cancelled=1" % public_host

    # Validate / clear a stale stored customer id, same as web/app.py.
    valid_customer_id = None
    customer_id = getattr(u, "stripe_customer_id", None)
    if customer_id:
        cust = stripe.Customer.retrieve(customer_id)
        if getattr(cust, "deleted", False):
            log.info("api billing: stale stripe_customer_id for user %s; not reusing", u.id)
        else:
            valid_customer_id = customer_id

    kwargs = dict(
        mode="subscription",
        line_items=[{"price": price.id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
        client_reference_id=str(u.id),
        subscription_data={
            "metadata": {
                "tw2_user_id": str(u.id),
                "product_line": "api",
                "tier": tier,
            },
        },
    )
    if valid_customer_id:
        kwargs["customer"] = valid_customer_id
    else:
        kwargs["customer_email"] = u.email

    session_obj = stripe.checkout.Session.create(**kwargs)
    return redirect(session_obj.url, code=303)


@bp.route("/billing/success")
@require_login
def billing_success():
    """Stripe redirects here after API checkout. We do NOT mutate the tier here
    (that is the web app's webhook's job, keyed on product_line=api metadata);
    we just confirm + send the user back to billing. Avoids a second, divergent
    tier-write path racing the webhook.
    """
    return redirect(url_for("api_portal.billing_index", subscribed=1))


@bp.route("/billing/manage")
@require_login
def billing_manage():
    """Stripe Billing Portal: change plan (upgrade/downgrade), update card,
    cancel, view invoices. Mirrors web/app.py:manage_subscription.
    """
    u = get_current_user()
    customer_id = getattr(u, "stripe_customer_id", None)
    if not customer_id:
        return redirect(url_for("api_portal.billing_index", no_subscription=1))
    if not _stripe_configured():
        return jsonify({"error": "stripe_not_configured"}), 503

    cust = stripe.Customer.retrieve(customer_id)
    if getattr(cust, "deleted", False):
        log.info("api billing manage: stale stripe_customer_id for user %s", u.id)
        return redirect(url_for("api_portal.billing_index", no_subscription=1))

    public_host = _public_host()
    session_obj = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url="https://%s/account/api/billing" % public_host,
    )
    return redirect(session_obj.url, code=303)
