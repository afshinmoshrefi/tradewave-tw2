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
import os
import logging

import stripe

import config
from apiserver import tiers as api_tiers
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


def _subscription_has_api_line(subscription, stored_api_subscription_id=None):
    """Recognize an API-line subscription from its durable ID or metadata."""
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
    items = (_as_dict(sub.get("items")).get("data") or [])
    for raw_item in items:
        price = _as_dict(_as_dict(raw_item).get("price"))
        price_line = str(
            (_as_dict(price.get("metadata")).get("product_line") or "")
        ).strip().lower()
        product = _as_dict(price.get("product"))
        product_line = str(
            (_as_dict(product.get("metadata")).get("product_line") or "")
        ).strip().lower()
        if "api" in (price_line, product_line):
            return True
    return False


def _existing_api_subscription(customer_id, stored_api_subscription_id=None):
    """Return an existing live API subscription, or propagate lookup errors."""
    for status in ("active", "trialing", "past_due"):
        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            status=status,
            limit=100,
            expand=["data.items.data.price.product"],
        )
        for subscription in subscriptions.auto_paging_iter():
            if _subscription_has_api_line(
                subscription,
                stored_api_subscription_id=stored_api_subscription_id,
            ):
                sub = _as_dict(subscription)
                return sub.get("id"), sub.get("status") or status
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
        rec = p.recurring.to_dict() if getattr(p, "recurring", None) else {}
        interval = rec.get("interval") or "month"   # 'month' | 'year'
        key = (tier, interval)
        existing = _price_cache.get(key)
        if existing is not None and getattr(existing, "id", None) != getattr(p, "id", None):
            log.warning(
                "api price_cache: >1 active %s price for tier %s (%s, %s) - ambiguous; "
                "archive the extra in Stripe. Using last-seen.",
                interval, tier, getattr(existing, "id", "?"), getattr(p, "id", "?"),
            )
        _price_cache[key] = p


def _price_for_tier(tier_name, interval="month"):
    """Resolve the exact tier and billing interval requested.

    Never fall back from an annual request to a monthly price: charging a
    different cadence than the submitted form while labeling metadata as yearly
    would be a billing-integrity failure.
    """
    if not _price_cache:
        _refresh_price_cache()
    return _price_cache.get((tier_name, interval))


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
            "price_annual": t["price_annual"],
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
        # Pricing-visibility gate (apiserver.tiers.API_PRICING_LIVE): the owner has not
        # finalized paid-tier pricing, so the template hides dollar amounts / upgrade
        # cards for tiers the user is not already on. Display-only - entitlements,
        # checkout, and the billing portal are untouched.
        pricing_live=api_tiers.API_PRICING_LIVE,
    )


@bp.route("/billing/checkout", methods=["POST"])
@require_login
def billing_checkout():
    """Start Stripe Checkout for the requested API tier and billing interval.

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

    interval = (request.form.get("interval") or "month").strip().lower()
    if interval in ("annual", "yearly", "year"):
        interval = "year"
    elif interval in ("monthly", "month"):
        interval = "month"
    else:
        flash("Billing interval must be monthly or annual.", "error")
        return redirect(url_for("api_portal.billing_index")), 400

    price = _price_for_tier(tier, interval)
    if not price:
        flash(
            "No active %s price is configured for %s yet. Run "
            "web/api_portal/create_api_products.py (TEST mode) first."
            % (interval, tier),
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

    try:
        session_obj = stripe.checkout.Session.create(**kwargs)
    except stripe.error.StripeError as e:
        # A rejected FOUNDER discount at session-create time (rare - list()
        # above already active-filters, but Stripe is the final authority on
        # the 100-seat cap) falls back to a plain checkout rather than a dead
        # end for the exact seat-101 case R4 calls out.
        if applied_founder:
            log.warning("founder discount rejected at checkout create: %s; retrying plain", e)
            kwargs.pop("discounts", None)
            kwargs["allow_promotion_codes"] = True
            flash(
                "The Founder's plan code could not be applied (100 seats "
                "claimed) - continuing at the regular price. You can still "
                "enter any other promo code at checkout.", "warning",
            )
            session_obj = stripe.checkout.Session.create(**kwargs)
        else:
            raise
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

    public_host = _public_host()
    session_obj = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url="https://%s/account/api/billing" % public_host,
    )
    return redirect(session_obj.url, code=303)
