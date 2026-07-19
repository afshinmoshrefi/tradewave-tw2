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

Card-state + entitlement rules below implement docs/API_CONSOLE_USER_FLOWS.md
§7.3 (R3-R7). KNOWN DEFECT FIXED HERE: this module used to derive every
non-current card's state from `has_customer = bool(u.stripe_customer_id)` -
that flag survives a CANCELLED subscription (Stripe never deletes the
customer object) and says nothing about whether the plan is bundled or
explicit, so a churned subscriber saw "Switch in portal" instead of
Subscribe, and a bundled-pro Strategist saw a live paid Dev card. The
reliable "holds an ACTIVE explicit API sub" signal is `users.api_tier` being
present and rankable - the webhook NULLs it on cancel (see apiserver.tiers
docstring), so its presence/absence is authoritative. `stripe_customer_id`
is used ONLY to gate the "manage" links to the Stripe-hosted portal, never to
choose a card's purchase state.
"""
from copy import deepcopy
import os
import logging
import time

import stripe

import config
from apiserver import tiers as api_tiers
from checkout_claims import (
    CHECKOUT_SESSION_TTL_SECONDS,
    CheckoutClaimBusy,
    CheckoutClaimConflict,
    CheckoutClaimDeferred,
    complete_checkout,
    release_checkout,
    replace_checkout_payload,
    reserve_checkout,
)
from .blueprint import (
    bp, require_login, get_current_user, api_tier_name_for, api_entitlements_for,
    entitlement_context,
)

from flask import render_template, request, redirect, jsonify, url_for, flash

log = logging.getLogger("tw2.api_portal.billing")

# Configure the Stripe SDK exactly like web/app.py (idempotent if the parent
# already set these; importing stripe twice yields the same module object).
stripe.api_key = config.STRIPE_SECRET_KEY
stripe.max_network_retries = 2

# Tiers a customer can subscribe to / switch between (free is the default, not
# a purchasable product). Order = display order, cheapest first.
PURCHASABLE_TIERS = ["dev", "pro", "business"]

# The FOUNDER promo (R4) only ever applies to Pro (apiserver.tiers.FOUNDER).
FOUNDER_TIER = api_tiers.FOUNDER["applies_to_tier"]

# Cache: api_tier_name -> Stripe price object, fetched once per process.
_price_cache = {}


class PriceCatalogError(RuntimeError):
    """The API Stripe catalog is ambiguous or differs from the sellable spec."""


class PortalConfigurationError(RuntimeError):
    """The dedicated API Billing Portal configuration is missing or drifted."""


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    for method_name in ("to_dict_recursive", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, dict):
                return converted
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _subscription_has_api_line(
    subscription, stored_api_subscription_id=None, product_cache=None,
):
    """Recognize an API-line subscription from durable identity or metadata.

    Stripe limits expansion paths to four levels, so ``Subscription.list``
    cannot expand ``data.items.data.price.product``.  Current TradeWave
    subscriptions carry ``product_line=api`` on the subscription itself.  For
    a legacy subscription without that metadata (and without a stored local
    ID), resolve the item's Product separately and inspect its canonical
    metadata.  Lookup failures intentionally propagate so checkout fails
    closed instead of creating a duplicate subscription.
    """
    sub = _as_dict(subscription)
    if (
        stored_api_subscription_id
        and sub.get("id") == stored_api_subscription_id
    ):
        return True
    sub_line = str(
        (_as_dict(sub.get("metadata")).get("product_line") or "")
    ).strip().lower()
    if sub_line == "api":
        return True
    product_cache = product_cache if product_cache is not None else {}
    items = (_as_dict(sub.get("items")).get("data") or [])
    for raw_item in items:
        price = _as_dict(_as_dict(raw_item).get("price"))
        price_line = str(
            (_as_dict(price.get("metadata")).get("product_line") or "")
        ).strip().lower()
        product_ref = price.get("product")
        if isinstance(product_ref, str) and product_ref:
            if product_ref not in product_cache:
                product_cache[product_ref] = stripe.Product.retrieve(
                    product_ref,
                )
            product_ref = product_cache[product_ref]
        product = _as_dict(product_ref)
        product_line = str(
            (_as_dict(product.get("metadata")).get("product_line") or "")
        ).strip().lower()
        if "api" in (price_line, product_line):
            return True
    return False


def _existing_api_subscription(customer_id, stored_api_subscription_id=None):
    """Return any non-terminal API subscription, or propagate lookup errors.

    ``incomplete``, ``unpaid``, and ``paused`` subscriptions can still produce
    billing/customer consequences and must be reconciled rather than bypassed
    with another Checkout. Only Stripe's terminal ``canceled`` and
    ``incomplete_expired`` states are safe to ignore.
    """
    product_cache = {}
    subscriptions = stripe.Subscription.list(
        customer=customer_id,
        status="all",
        limit=100,
    )
    for subscription in subscriptions.auto_paging_iter():
        sub = _as_dict(subscription)
        status = str(sub.get("status") or "").strip().lower()
        if status in {"canceled", "incomplete_expired"}:
            continue
        if _subscription_has_api_line(
            subscription,
            stored_api_subscription_id=stored_api_subscription_id,
            product_cache=product_cache,
        ):
            return sub.get("id"), sub.get("status") or "unknown"
    return None, None


def _clear_stale_customer_identity(user_id):
    """Clear both Stripe product-line identities for a missing customer."""
    from models import Session as DBSession, User

    session = DBSession()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is None:
            return
        user.stripe_customer_id = None
        user.stripe_subscription_id = None
        user.stripe_subscription_status = None
        user.api_stripe_subscription_id = None
        user.api_stripe_subscription_status = None
        user.api_tier = None
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        DBSession.remove()


def _stripe_configured():
    secret = (config.STRIPE_SECRET_KEY or "").strip()
    publishable = (config.STRIPE_PUBLISHABLE_KEY or "").strip()
    if "PLACEHOLDER" in secret.upper() or "PLACEHOLDER" in publishable.upper():
        return False
    secret_mode = (
        "test" if secret.startswith("sk_test_")
        else "live" if secret.startswith("sk_live_")
        else None
    )
    publishable_mode = (
        "test" if publishable.startswith("pk_test_")
        else "live" if publishable.startswith("pk_live_")
        else None
    )
    return bool(secret_mode and secret_mode == publishable_mode)


def _public_host():
    return os.environ.get("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")


def _refresh_price_cache():
    """Bucket active Stripe prices by API tier - metadata-only, MONTHLY ONLY.

    A price is used ONLY if its product carries product_line=api, a tier in
    PURCHASABLE_TIERS, AND a monthly recurring interval. This is the same
    deterministic, metadata-only approach web/app.py uses for the EOD product
    line, so legacy UMP prices, the EOD product line, and placeholders are all
    ignored (no name collisions).

    Billing is MONTHLY ONLY (owner decision 2026-07-05, reaffirmed 2026-07-17;
    rationale in apiserver/tiers.py). A stale annual price left over in Stripe
    from before that decision is tolerated: it is simply skipped here rather
    than matched or required, so it can never resolve at checkout.
    """
    if not _stripe_configured():
        return
    valid = set(PURCHASABLE_TIERS)
    next_cache = {}
    errors = []
    for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
        prod = p.product
        if not isinstance(prod, dict):
            prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
        md = prod.get("metadata") or {}
        if (md.get("product_line") or "").strip().lower() != "api":
            continue
        tier = (md.get("tier") or "").strip().lower()
        if tier not in valid:
            errors.append("API product has an unknown tier")
            continue
        rec = _as_dict(getattr(p, "recurring", None))
        interval = str(rec.get("interval") or "").strip().lower()
        interval_count = rec.get("interval_count", 1)
        if interval != "month":
            # A stale annual price (or anything else non-monthly) - never
            # matched, not an error. This is the tolerance for an earlier
            # annual seed that create_api_products.py self-heals separately.
            continue
        if interval_count != 1:
            errors.append("API price has an unsupported recurring interval")
            continue
        expected_amount = int(api_tiers.API_TIERS[tier]["price_monthly"] * 100)
        currency = str(getattr(p, "currency", "") or "").strip().lower()
        if currency != "usd":
            errors.append("API price currency does not match the USD catalog")
            continue
        if getattr(p, "unit_amount", None) != expected_amount:
            errors.append("API price amount does not match the published catalog")
            continue
        # Product metadata is canonical.  Legacy Price objects may have no
        # metadata, but any metadata that is present must agree with the
        # product and recurring interval.
        price_md = _as_dict(getattr(p, "metadata", None))
        if price_md.get("product_line") not in (None, "", "api"):
            errors.append("API price metadata has the wrong product line")
            continue
        if price_md.get("tier") not in (None, "", tier):
            errors.append("API price metadata has the wrong tier")
            continue
        if price_md.get("interval") not in (None, "", interval):
            errors.append("API price metadata has the wrong interval")
            continue
        existing = next_cache.get(tier)
        if existing is not None and getattr(existing, "id", None) != getattr(p, "id", None):
            errors.append("API catalog has duplicate active monthly prices for one tier")
            continue
        next_cache[tier] = p

    required = set(PURCHASABLE_TIERS)
    if set(next_cache) != required:
        errors.append("API catalog is missing one or more required monthly tier prices")
    if errors:
        _price_cache.clear()
        # Do not include remote object IDs or full Stripe payloads in the log.
        summary = "; ".join(sorted(set(errors)))
        log.error("API Stripe price catalog rejected: %s", summary)
        raise PriceCatalogError(summary)
    _price_cache.clear()
    _price_cache.update(next_cache)


def _price_for_tier(tier_name):
    """Resolve the (only) monthly price for this tier. Billing is MONTHLY ONLY
    (owner decision 2026-07-05, reaffirmed 2026-07-17); there is no interval
    parameter to accept, so a caller can never resolve anything else."""
    if not _price_cache:
        _refresh_price_cache()
    return _price_cache.get(tier_name)


def _price_product_id(price):
    product = getattr(price, "product", None)
    if isinstance(product, str):
        return product
    product = _as_dict(product)
    return product.get("id")


def _portal_product_map(products):
    normalized = {}
    for raw in products or []:
        item = _as_dict(raw)
        product = item.get("product")
        if not isinstance(product, str):
            product = _as_dict(product).get("id")
        price_ids = []
        for raw_price in item.get("prices") or []:
            if isinstance(raw_price, str):
                price_ids.append(raw_price)
            else:
                price_id = _as_dict(raw_price).get("id")
                if price_id:
                    price_ids.append(price_id)
        if product:
            normalized[product] = frozenset(price_ids)
    return normalized


def _validated_portal_configuration_id():
    """Validate the dedicated API portal against the exact API price catalog."""
    configuration_id = getattr(
        config, "API_BILLING_PORTAL_CONFIGURATION_ID", "",
    )
    if (
        not configuration_id
        or not configuration_id.startswith("bpc_")
        or "PLACEHOLDER" in configuration_id.upper()
    ):
        raise PortalConfigurationError(
            "TW2_API_BILLING_PORTAL_CONFIGURATION_ID is missing or a placeholder"
        )
    if not _price_cache:
        _refresh_price_cache()
    expected_products = {}
    for price in _price_cache.values():
        product_id = _price_product_id(price)
        if not product_id:
            raise PortalConfigurationError("API price lacks an expanded product ID")
        expected_products.setdefault(product_id, set()).add(price.id)
    expected_products = {
        product_id: frozenset(price_ids)
        for product_id, price_ids in expected_products.items()
    }

    portal = _as_dict(
        stripe.billing_portal.Configuration.retrieve(
            configuration_id,
            expand=["features.subscription_update.products"],
        )
    )
    if not portal.get("active") or portal.get("is_default"):
        raise PortalConfigurationError(
            "API Billing Portal configuration must be active and non-default"
        )
    expected_livemode = (config.STRIPE_SECRET_KEY or "").startswith("sk_live_")
    if bool(portal.get("livemode")) != expected_livemode:
        raise PortalConfigurationError(
            "API Billing Portal configuration belongs to the wrong Stripe mode"
        )
    metadata = _as_dict(portal.get("metadata"))
    if metadata.get("tw2_purpose") != "api_subscription_management":
        raise PortalConfigurationError(
            "API Billing Portal configuration has the wrong purpose metadata"
        )
    features = _as_dict(portal.get("features"))
    subscription_update = _as_dict(features.get("subscription_update"))
    if (
        not subscription_update.get("enabled")
        or set(subscription_update.get("default_allowed_updates") or [])
        != {"price", "promotion_code"}
        or subscription_update.get("proration_behavior") != "create_prorations"
        or _portal_product_map(subscription_update.get("products"))
        != expected_products
    ):
        raise PortalConfigurationError(
            "API Billing Portal configuration does not contain the exact API catalog"
        )
    for feature_name in (
        "invoice_history", "payment_method_update", "subscription_cancel",
    ):
        if not _as_dict(features.get(feature_name)).get("enabled"):
            raise PortalConfigurationError(
                "API Billing Portal configuration is missing account-management features"
            )
    subscription_cancel = _as_dict(features.get("subscription_cancel"))
    if (
        subscription_cancel.get("mode") != "at_period_end"
        or subscription_cancel.get("proration_behavior") != "none"
    ):
        raise PortalConfigurationError(
            "API Billing Portal cancellation semantics have drifted"
        )
    return configuration_id


def _founder_promotion_code_id():
    """Look up the ACTIVE Stripe promotion code for FOUNDER (id, not the typed
    code string) - required by checkout.Session.create(discounts=[{"promotion_
    code": id}]). Returns None on ANY lookup miss/Stripe error so the caller can
    fall back to plain allow_promotion_codes (R4) rather than erroring the
    checkout. NOT cached (spec: "do not cache the promo id") - redemption count
    changes as seats fill, and a cached id could keep offering an exhausted/
    deactivated code long after Stripe would have rejected it anyway."""
    try:
        matches = stripe.PromotionCode.list(
            code=api_tiers.FOUNDER["code"], active=True, limit=10,
        ).data
    except Exception as e:
        log.warning("founder promo lookup failed: %s", e)
        return None
    for pc in matches:
        coupon = getattr(pc.promotion, "coupon", None) if hasattr(pc, "promotion") else None
        if coupon and getattr(coupon, "percent_off", None) == api_tiers.FOUNDER["percent_off"]:
            return pc.id
    # Fall back to any active code matching the string if the coupon shape
    # couldn't be introspected (still real Stripe data, just less strict).
    return matches[0].id if matches else None


def _card_state(card_rank, ctx):
    """R5, pure function of (card rank, entitlement ctx). Returns one of:
      'current_explicit'  - T == C, explicit source -> Current plan + manage
      'current_bundled'    - T == C, bundled source -> disabled "Included..."
      'included_below'     - T < C, bundled source  -> disabled C2
      'downgrade'           - T < C, explicit source -> Downgrade in portal
      'upgrade_explicit'    - T > C, holds a lower explicit sub -> Upgrade in portal
      'subscribe'           - T > C, no explicit sub (or explicit == bundled) -> Subscribe
    """
    eff_rank = api_tiers.API_TIER_RANK[ctx["effective"]]
    if card_rank == eff_rank:
        return "current_explicit" if ctx["effective_source"] == "explicit" else "current_bundled"
    if card_rank < eff_rank:
        return "downgrade" if ctx["effective_source"] == "explicit" else "included_below"
    # card_rank > eff_rank: strictly-above card. eff_rank is always >= the
    # explicit rank (it's a MAX), so any card here is also above the explicit
    # sub if one exists. If it does, R5 routes through "upgrade in portal"
    # (switch the existing sub) rather than Subscribe, so a second Stripe API
    # subscription is never created.
    if ctx["explicit"] is not None:
        return "upgrade_explicit"
    return "subscribe"


@bp.route("")
@bp.route("/")
def index():
    """Console landing. /account/api (no tab) is the exact URL the gateway
    publishes as upgrade_url in every quota/scope nudge (apiserver/routes.py
    _UPGRADE_URL), so it must always resolve. Land it on the billing tab -
    the plans + upgrade page is what every published nudge is selling.
    No require_login here: billing_index already bounces anonymous visitors
    to /login, and a bare redirect leaks nothing.
    """
    return redirect(url_for("api_portal.billing_index"))


@bp.route("/billing")
@require_login
def billing_index():
    u = get_current_user()
    ctx = entitlement_context(u)
    current_tier = ctx["effective"]

    # R3: ?subscribe=<tier> highlights a card, never auto-charges. Validate
    # against the purchasable set; anything else (unknown tier, or a tier
    # already covered - rank <= effective) degrades to no-highlight rather
    # than erroring. Pricing-flag-off also degrades (R3 "or the flag is off").
    requested = (request.args.get("subscribe") or "").strip().lower()
    highlight_tier = None
    if (
        api_tiers.API_PRICING_LIVE
        and requested in PURCHASABLE_TIERS
        and api_tiers.API_TIER_RANK[requested] > api_tiers.API_TIER_RANK[current_tier]
    ):
        highlight_tier = requested

    # Build display rows from the single source of truth (apiserver.tiers).
    plans = []
    for name in ["free"] + PURCHASABLE_TIERS:
        t = api_tiers.API_TIERS[name]
        rank = api_tiers.API_TIER_RANK[name]
        state = _card_state(rank, ctx)
        plans.append({
            "name": name,
            "label": t["name"],
            "price_monthly": t["price_monthly"],
            "markets": "1 market" if len(t["markets"]) == 1 else "All %d markets" % len(t["markets"]),
            "ml_access": t["ml_access"],
            "ml_daily_limit": t.get("ml_daily_limit"),  # None = unlimited
            "history": t["history"],
            "opp_limit": t["opp_limit"],
            "rate": t["rate"],
            "max_keys": t["max_keys"],
            "is_current": name == current_tier,
            "purchasable": name in PURCHASABLE_TIERS,
            "state": state,
            "highlight": name == highlight_tier,
            # Pro-only note C3, shown to prospects with no web sub at all
            # (WEB_TIER_TO_API bundles nothing worth mentioning at 'explorer').
            "show_c3": name == "pro" and ctx["web_tier"] == "explorer",
        })

    return render_template(
        "api_billing.html",
        user=u,
        plans=plans,
        current_tier=current_tier,
        current_label=ctx["effective_label"],
        ctx=ctx,
        highlight_tier=highlight_tier,
        # "Manage in billing portal" is offered only when Stripe actually has a
        # live customer record; kept SEPARATE from card-state logic (see
        # module docstring) - it only gates whether the "Open billing portal"
        # link/button appears, never which state a card is in.
        has_customer=bool(getattr(u, "stripe_customer_id", None)),
        stripe_configured=_stripe_configured(),
        founder=api_tiers.FOUNDER,
        # Owner-controlled pricing/acquisition gate: the template hides paid
        # offers and the POST route independently rejects new subscriptions.
        # Existing entitlements and Billing Portal management/cancellation stay
        # available while the gate is off.
        pricing_live=api_tiers.API_PRICING_LIVE,
    )


@bp.route("/billing/checkout", methods=["POST"])
@require_login
def billing_checkout():
    """Start Stripe Checkout for the requested API tier (monthly).

    Mirrors web/app.py:stripe_create_checkout - validates a stored customer id,
    sets client_reference_id + subscription metadata (product_line=api, tier)
    so the webhook can map the resulting subscription back to this user + the
    API product line.

    Server-side re-check (R5/R3): a tier whose rank <= the caller's CURRENT
    effective rank is rejected here regardless of what the UI showed - the UI
    state is a rendering of this same rule, but a stale page, a replayed form,
    or a hand-crafted POST must never be able to buy something already held.
    4xx-with-flash, not 500: this is a caller mistake / stale link, not a
    server fault.
    """
    if not _stripe_configured():
        flash("Billing is not yet configured in this environment. Try again later.", "error")
        return redirect(url_for("api_portal.billing_index")), 503
    if not api_tiers.API_PRICING_LIVE:
        # Owner-controlled acquisition gate.  Management/cancellation remains
        # available through /billing/manage for existing subscribers.
        flash("New API subscriptions are not available yet.", "warning")
        return redirect(url_for("api_portal.billing_index")), 403

    u = get_current_user()
    tier = (request.form.get("tier") or "").strip().lower()
    if tier not in PURCHASABLE_TIERS:
        flash("Unknown plan requested.", "error")
        return redirect(url_for("api_portal.billing_index")), 400

    ctx = entitlement_context(u)
    if api_tiers.API_TIER_RANK[tier] <= api_tiers.API_TIER_RANK[ctx["effective"]]:
        flash(
            "You already have %s access or better (via your %s plan). "
            "No purchase needed." % (api_tiers.tier_for(tier)["name"], ctx["web_tier_label"]),
            "warning",
        )
        return redirect(url_for("api_portal.billing_index")), 400

    # MONTHLY ONLY (owner decision 2026-07-05, reaffirmed 2026-07-17). Reject an
    # explicit annual ask loudly rather than silently resolving a different
    # interval than the caller requested.
    interval = (request.form.get("interval") or "month").strip().lower()
    if interval not in ("monthly", "month"):
        flash("API plans are billed monthly only; annual billing is not offered.", "error")
        return redirect(url_for("api_portal.billing_index")), 400
    interval = "month"

    try:
        price = _price_for_tier(tier)
    except PriceCatalogError:
        flash(
            "Billing is temporarily unavailable because the price catalog "
            "needs operator review.",
            "error",
        )
        return redirect(url_for("api_portal.billing_index")), 503
    if not price:
        flash(
            "No active monthly price is configured for %s yet. Run "
            "web/api_portal/create_api_products.py (TEST mode) first." % tier,
            "error",
        )
        return redirect(url_for("api_portal.billing_index")), 400

    # If the caller ALREADY holds a lower explicit API sub, R5 says the UI
    # offers "Upgrade in billing portal" instead of Subscribe - a second
    # Stripe subscription must never be created. Re-check server-side too.
    if ctx["explicit"] is not None:
        flash(
            "You already have an active %s API subscription. Switch plans in "
            "the billing portal instead." % ctx["explicit_label"],
            "warning",
        )
        return redirect(url_for("api_portal.billing_manage")), 400

    public_host = _public_host()
    success_url = "https://%s/account/api/billing/success?session_id={CHECKOUT_SESSION_ID}" % public_host
    cancel_url = "https://%s/account/api/billing?cancelled=1" % public_host

    # Validate / clear a stale stored customer id, same as web/app.py.
    valid_customer_id = None
    customer_id = getattr(u, "stripe_customer_id", None)
    if not customer_id and getattr(u, "api_stripe_subscription_id", None):
        log.error(
            "api billing: user %s has an API subscription but no Stripe customer",
            u.id,
        )
        return jsonify({
            "error": "subscription_identity_incomplete",
            "message": "Billing needs account reconciliation before another "
                       "subscription can be started.",
        }), 503
    if customer_id:
        try:
            cust = stripe.Customer.retrieve(customer_id)
            if getattr(cust, "deleted", False):
                raise stripe.error.InvalidRequestError(
                    "customer soft-deleted", None,
                )
        except stripe.error.InvalidRequestError:
            log.info("api billing: stale stripe_customer_id for user %s; not reusing", u.id)
            _clear_stale_customer_identity(u.id)
            u.stripe_customer_id = None
            u.stripe_subscription_id = None
            u.stripe_subscription_status = None
            u.api_stripe_subscription_id = None
            u.api_stripe_subscription_status = None
            u.api_tier = None
        else:
            valid_customer_id = customer_id

    if valid_customer_id:
        try:
            existing_api_id, existing_api_status = _existing_api_subscription(
                valid_customer_id,
                stored_api_subscription_id=getattr(
                    u, "api_stripe_subscription_id", None,
                ),
            )
        except Exception:
            log.exception(
                "api billing: existing-subscription lookup failed for user %s",
                u.id,
            )
            return jsonify({
                "error": "subscription_lookup_failed",
                "message": "We could not verify your current API subscription. "
                           "Please retry in a moment.",
            }), 503
        if existing_api_id:
            log.info(
                "api billing: user %s already has %s API subscription %s; "
                "redirecting to billing portal",
                u.id, existing_api_status, existing_api_id,
            )
            return redirect(url_for("api_portal.billing_manage"), code=303)

    kwargs = dict(
        mode="subscription",
        line_items=[{"price": price.id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(u.id),
        # Checkout-session metadata is what checkout.session.completed carries.
        # Keep product-line identity here as well as on the Subscription so the
        # shared webhook can never mistake an API checkout for a web plan.
        metadata={
            "product_line": "api",
            "tier": tier,
            "interval": interval,
            "replaces_subscription_id": (
                getattr(u, "api_stripe_subscription_id", None) or ""
            ),
        },
        subscription_data={
            "metadata": {
                "tw2_user_id": str(u.id),
                "product_line": "api",
                "tier": tier,
                "interval": interval,
                "replaces_subscription_id": (
                    getattr(u, "api_stripe_subscription_id", None) or ""
                ),
            },
        },
        # Stripe permits a 30-minute to 24-hour lifetime.  Bounding it also
        # bounds how long the durable checkout claim blocks a different target.
        expires_at=int(time.time()) + CHECKOUT_SESSION_TTL_SECONDS,
    )
    if valid_customer_id:
        kwargs["customer"] = valid_customer_id
    else:
        kwargs["customer_email"] = u.email

    # R4: promo=FOUNDER pre-applies the FOUNDER promotion code (Stripe enforces
    # the 100-seat cap) ONLY for the tier it applies to (Pro). Any Stripe
    # rejection (exhausted/expired/not found) falls back to plain checkout
    # with allow_promotion_codes=True plus a flash note - no dead end.
    promo_requested = (request.args.get("promo") or request.form.get("promo") or "").strip().upper()
    applied_founder = False
    if promo_requested == api_tiers.FOUNDER["code"] and tier == FOUNDER_TIER:
        promo_id = _founder_promotion_code_id()
        if promo_id:
            kwargs["discounts"] = [{"promotion_code": promo_id}]
            applied_founder = True
        else:
            flash(
                "The Founder's plan code is no longer available (100 seats "
                "claimed, or it has expired) - you can still enter any other "
                "promo code at checkout.", "warning",
            )
    if not applied_founder:
        kwargs["allow_promotion_codes"] = True

    from models import Session as DBSession

    try:
        reservation = reserve_checkout(
            u.id, "api", kwargs, session_factory=DBSession,
        )
    except CheckoutClaimDeferred:
        flash(
            "A previous API checkout outcome is still being reconciled. Wait "
            "for that session to expire before starting another.",
            "warning",
        )
        response = redirect(url_for("api_portal.billing_index"))
        response.status_code = 409
        return response
    except CheckoutClaimConflict:
        flash(
            "A different API subscription checkout is already pending. Finish "
            "it or wait for it to expire.",
            "warning",
        )
        response = redirect(url_for("api_portal.billing_index"))
        response.status_code = 409
        return response
    except CheckoutClaimBusy:
        flash(
            "API checkout creation is already in progress. Retry in a few "
            "seconds.",
            "warning",
        )
        response = redirect(url_for("api_portal.billing_index"))
        response.status_code = 409
        response.headers["Retry-After"] = "2"
        return response

    if reservation.reused:
        return redirect(reservation.session_url, code=303)

    try:
        session_obj = stripe.checkout.Session.create(
            idempotency_key=reservation.idempotency_key,
            **reservation.payload,
        )
    except stripe.error.InvalidRequestError as e:
        # A rejected FOUNDER discount at session-create time (rare - list()
        # above already active-filters, but Stripe is the final authority on
        # the 100-seat cap) falls back to a plain checkout rather than a dead
        # end for the exact seat-101 case R4 calls out.
        if applied_founder and "discounts" in reservation.payload:
            log.warning("founder discount rejected at checkout create: %s; retrying plain", e)
            kwargs = deepcopy(reservation.payload)
            kwargs.pop("discounts", None)
            kwargs["allow_promotion_codes"] = True
            flash(
                "The Founder's plan code could not be applied (100 seats "
                "claimed) - continuing at the regular price. You can still "
                "enter any other promo code at checkout.", "warning",
            )
            try:
                reservation = replace_checkout_payload(
                    reservation, kwargs, session_factory=DBSession,
                )
                session_obj = stripe.checkout.Session.create(
                    idempotency_key=reservation.idempotency_key,
                    **reservation.payload,
                )
            except Exception:
                try:
                    release_checkout(reservation, session_factory=DBSession)
                except Exception:
                    log.exception(
                        "api billing: failed to release fallback Checkout claim"
                    )
                raise
        else:
            release_checkout(reservation, session_factory=DBSession)
            raise
    except Exception:
        try:
            release_checkout(reservation, session_factory=DBSession)
        except Exception:
            log.exception("api billing: failed to release Checkout claim")
        raise

    session_data = _as_dict(session_obj)
    try:
        complete_checkout(
            reservation,
            session_data.get("id"),
            session_data.get("url"),
            session_factory=DBSession,
        )
    except Exception:
        try:
            release_checkout(reservation, session_factory=DBSession)
        except Exception:
            log.exception("api billing: failed to release incomplete Checkout claim")
        raise
    return redirect(session_data["url"], code=303)


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

    try:
        cust = stripe.Customer.retrieve(customer_id)
        if getattr(cust, "deleted", False):
            raise stripe.error.InvalidRequestError(
                "customer soft-deleted", None,
            )
    except stripe.error.InvalidRequestError:
        log.info("api billing manage: stale stripe_customer_id for user %s", u.id)
        _clear_stale_customer_identity(u.id)
        return redirect(url_for("api_portal.billing_index", no_subscription=1))

    try:
        portal_configuration_id = _validated_portal_configuration_id()
    except (PriceCatalogError, PortalConfigurationError):
        log.exception(
            "api billing manage: dedicated portal configuration validation failed"
        )
        return jsonify({
            "error": "billing_portal_misconfigured",
            "message": "Subscription management is temporarily unavailable. "
                       "Please contact support if you need to cancel now.",
        }), 503

    public_host = _public_host()
    session_obj = stripe.billing_portal.Session.create(
        customer=customer_id,
        configuration=portal_configuration_id,
        return_url="https://%s/account/api/billing" % public_host,
    )
    return redirect(session_obj.url, code=303)
