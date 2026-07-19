#!/usr/bin/env python3
"""Idempotently create the TradeWave API products + MONTHLY prices and
the dedicated API Billing Portal configuration in
Stripe (Dev/Pro/Business), with metadata product_line=api + tier so the
console's billing code (and the web app's webhook) can resolve them
deterministically.

API billing is MONTHLY ONLY (owner decision 2026-07-05, reaffirmed 2026-07-17;
rationale in apiserver/tiers.py). This script also SELF-HEALS an earlier annual
seed: it re-points the product's default_price to the monthly price first, then
archives any active annual price it finds.

  DO NOT RUN THIS DURING THE CONSOLE BUILD. The parent runs it ONCE at
  integration with a confirmed Stripe TEST key:

      cd /home/flask
      STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python web/api_portal/create_api_products.py

  LIVE cutover (guarded). To seed the SAME catalog into LIVE Stripe, pass the
  --live flag AND set TW2_CONFIRM_LIVE_SEED=1. Both are required; either one
  alone refuses. (If run on a TTY you will also be asked to type 'yes'.)

      cd /home/flask
      TW2_CONFIRM_LIVE_SEED=1 STRIPE_SECRET_KEY=sk_live_... \\
          ./venv/bin/python web/api_portal/create_api_products.py --live

Safety:
  - Default (no --live): refuses to run unless STRIPE_SECRET_KEY starts with
    'sk_test_'. A live key (sk_live_) aborts immediately.
  - With --live: permits an 'sk_live_' key ONLY if env TW2_CONFIRM_LIVE_SEED=1
    is also set (and, on a TTY, a typed 'yes'). A loud banner names exactly what
    will be created before proceeding.
  - Any key that is neither 'sk_test_' nor 'sk_live_' is always refused.
  - Idempotent: it looks up existing products by (product_line=api, tier)
    metadata, validates the exact amount/currency/interval, and reuses them.
    The dedicated portal configuration is found by purpose metadata or by
    TW2_API_BILLING_PORTAL_CONFIGURATION_ID. Re-running makes no duplicates.

Source of truth for the tiers/prices is apiserver.tiers.API_TIERS (the same
dict the console + gateway read). The free tier has no Stripe product.
"""
import os
import sys
from pathlib import Path

# Make the apiserver package + config importable from any CWD.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config
from apiserver import tiers as api_tiers

CURRENCY = "usd"
PRODUCT_LINE = "api"
# Tiers that get a Stripe product (free is not purchasable).
PAID_TIERS = ["dev", "pro", "business"]
PORTAL_CONFIGURATION_ENV = "TW2_API_BILLING_PORTAL_CONFIGURATION_ID"
PORTAL_PURPOSE = "api_subscription_management"
PORTAL_NAME = "TradeWave API subscriptions"
PORTAL_PRODUCTS_EXPANSION = "features.subscription_update.products"


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


def _live_banner():
    """Loud multi-line banner naming exactly what the LIVE seed will create.

    Pulls dollar amounts + Founder terms from API_TIERS / FOUNDER so the banner
    can never drift from the source of truth.
    """
    lines = [
        "",
        "!!! ====================================================================== !!!",
        "!!!  LIVE STRIPE SEED - this will create REAL, BILLABLE objects in LIVE     !!!",
        "!!!  Stripe. This is NOT test mode. Read carefully before confirming.       !!!",
        "!!! ====================================================================== !!!",
        "",
        "  Products + prices to ensure (idempotent - reused if already present):",
    ]
    for tier in PAID_TIERS:
        spec = api_tiers.API_TIERS[tier]
        lines.append(
            "    - TradeWave API - %-8s  $%d/mo (monthly only)"
            % (spec["name"], spec["price_monthly"])
        )
    f = api_tiers.FOUNDER
    lines += [
        "",
        "  Dedicated API Billing Portal configuration to ensure:",
        "    - Create or update the non-default API-only configuration",
        "    - Permit API tier/interval changes, promotion codes, cancellation,",
        "      payment-method updates, and invoice history",
        "    - Print the resulting %s value for operator persistence"
        % PORTAL_CONFIGURATION_ENV,
        "",
        "  Plus the FOUNDER discount on the Pro product:",
        "    - Coupon %s  (%d%% off Pro, repeating %dmo, max %d redemptions)"
        % (FOUNDER_COUPON_ID, f["percent_off"], f["duration_months"], f["max_redemptions"]),
        "    - Promotion code '%s'  (-> ~$%d/mo effective on Pro)"
        % (f["code"], f["effective_monthly"]),
        "",
        "!!! ====================================================================== !!!",
        "",
    ]
    return "\n".join(lines)


def _require_seed_key():
    """Gate the Stripe key based on --live.

    Returns the validated key, or sys.exit()s with a clear message.

      - WITHOUT --live: only an 'sk_test_' key is permitted (unchanged behavior).
      - WITH --live: only an 'sk_live_' key is permitted, AND only if
        TW2_CONFIRM_LIVE_SEED=1 is set (plus a typed 'yes' on a TTY). A loud
        banner is printed before proceeding.
      - Any key that is neither 'sk_test_' nor 'sk_live_' is always refused.
    """
    live = "--live" in sys.argv[1:]
    key = config.STRIPE_SECRET_KEY or ""

    # A bad/unknown key shape is always refused, in either mode.
    if not (key.startswith("sk_test_") or key.startswith("sk_live_")):
        sys.exit(
            "REFUSING TO RUN: STRIPE_SECRET_KEY is not a recognizable Stripe "
            "secret key (expected 'sk_test_...' or, with --live, 'sk_live_...').\n"
            "Re-run as: STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python "
            "web/api_portal/create_api_products.py"
        )

    if not live:
        # Default path: TEST only. A live key aborts immediately.
        if not key.startswith("sk_test_"):
            sys.exit(
                "REFUSING TO RUN: STRIPE_SECRET_KEY is a LIVE key but --live was "
                "not passed. This script defaults to Stripe TEST mode only.\n"
                "For a TEST seed: STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python "
                "web/api_portal/create_api_products.py\n"
                "For a LIVE seed (guarded): set TW2_CONFIRM_LIVE_SEED=1 and pass --live."
            )
        return key

    # --live path: LIVE only, double-gated.
    if not key.startswith("sk_live_"):
        sys.exit(
            "REFUSING TO RUN: --live was passed but STRIPE_SECRET_KEY is not a "
            "LIVE key (expected 'sk_live_...'). Drop --live for a TEST seed."
        )
    if os.environ.get("TW2_CONFIRM_LIVE_SEED") != "1":
        sys.exit(
            "REFUSING TO RUN: --live requires the environment variable "
            "TW2_CONFIRM_LIVE_SEED=1 to be set as an explicit confirmation.\n"
            "Re-run as: TW2_CONFIRM_LIVE_SEED=1 STRIPE_SECRET_KEY=sk_live_... "
            "./venv/bin/python web/api_portal/create_api_products.py --live"
        )

    print(_live_banner())
    # On an interactive terminal, additionally require a typed confirmation.
    if sys.stdin.isatty():
        try:
            answer = input("Type 'yes' to seed the above into LIVE Stripe: ").strip()
        except EOFError:
            answer = ""
        if answer != "yes":
            sys.exit("Aborted: live seed not confirmed ('yes' not typed).")
    return key


def _find_product(stripe, tier):
    """Find an existing product with metadata product_line=api + tier, or None.

    Stripe product search needs the 'metadata[...]' query. We page active
    products and match in Python to stay robust to search-index lag right
    after a create.
    """
    matches = []
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        md = _as_dict(getattr(prod, "metadata", None))
        if (md.get("product_line") or "").lower() == PRODUCT_LINE and (md.get("tier") or "").lower() == tier:
            matches.append(prod)
    if len(matches) > 1:
        raise RuntimeError(
            "REFUSING TO CONFIGURE: multiple active API products exist for "
            "tier %s" % tier
        )
    return matches[0] if matches else None


def _find_price_for_interval(stripe, product_id, interval):
    """Find the sole active recurring price for an interval, or None."""
    matches = []
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        rec = _as_dict(getattr(price, "recurring", None))
        if rec.get("interval") == interval:
            matches.append(price)
    if len(matches) > 1:
        raise RuntimeError(
            "REFUSING TO SEED: duplicate active %s prices for API product %s"
            % (interval, product_id)
        )
    return matches[0] if matches else None


def _ensure_price(stripe, product, tier, interval, dollars):
    """Idempotently ensure an active <interval> price exists on the product."""
    unit = "/mo" if interval == "month" else "/yr"
    price = _find_price_for_interval(stripe, product.id, interval)
    expected_amount = int(dollars) * 100
    if price is None:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=expected_amount,
            currency=CURRENCY,
            recurring={"interval": interval},
            metadata={"product_line": PRODUCT_LINE, "tier": tier, "interval": interval},
        )
        print("    created price %s ($%d%s)" % (price.id, dollars, unit))
    else:
        recurring = _as_dict(getattr(price, "recurring", None))
        metadata = _as_dict(getattr(price, "metadata", None))
        if (
            getattr(price, "unit_amount", None) != expected_amount
            or str(getattr(price, "currency", "") or "").lower() != CURRENCY
            or recurring.get("interval") != interval
            or recurring.get("interval_count", 1) != 1
            or metadata.get("product_line") not in (None, "", PRODUCT_LINE)
            or metadata.get("tier") not in (None, "", tier)
            or metadata.get("interval") not in (None, "", interval)
        ):
            raise RuntimeError(
                "REFUSING TO SEED: active %s price for API tier %s does not "
                "match amount/currency/interval/metadata; reconcile it first"
                % (interval, tier)
            )
        print("    reused price  %s ($%d%s)" % (price.id, dollars, unit))
    return price


# Founder's plan = Pro at 50% off for 12 months, first 100 customers. A Stripe coupon
# (repeating 12 months, capped at 100 redemptions, restricted to the Pro product) plus a
# promotion code the customer types at checkout (allow_promotion_codes=True is already set).
FOUNDER_COUPON_ID = "founder_pro_50_12mo"


FOUNDER_COUPON_NAME = "TradeWave Founder (Pro 50% off 12mo)"


def _coupon_matches_founder(coupon, spec, pro_product_id):
    """True if an existing coupon carries EXACTLY the Founder terms + Pro restriction.
    NB: current Stripe API versions OMIT applies_to from the default representation -
    the caller must have retrieved with expand=["applies_to"] or this always fails."""
    applies = getattr(coupon, "applies_to", None)
    products = list(applies.products) if applies else []
    return (
        coupon.percent_off == spec["percent_off"]
        and coupon.duration == "repeating"
        and coupon.duration_in_months == spec["duration_months"]
        and coupon.max_redemptions == spec["max_redemptions"]
        and products == [pro_product_id]
    )


def _ensure_founder(stripe, pro_product_id):
    spec = api_tiers.FOUNDER

    def _create_coupon():
        return stripe.Coupon.create(
            id=FOUNDER_COUPON_ID,
            percent_off=spec["percent_off"],
            duration="repeating",
            duration_in_months=spec["duration_months"],
            max_redemptions=spec["max_redemptions"],
            applies_to={"products": [pro_product_id]},
            name=FOUNDER_COUPON_NAME,
            metadata={"product_line": PRODUCT_LINE, "plan": "founder"},
        )

    try:
        coupon = stripe.Coupon.retrieve(FOUNDER_COUPON_ID, expand=["applies_to"])
    except Exception:
        coupon = None

    if coupon is None:
        coupon = _create_coupon()
        print("  created coupon  %s (%d%% off Pro, %dmo, max %d)" % (
            coupon.id, spec["percent_off"], spec["duration_months"], spec["max_redemptions"]))
    elif _coupon_matches_founder(coupon, spec, pro_product_id):
        print("  reused coupon   %s (%d%% off Pro, %dmo)" % (coupon.id, spec["percent_off"], spec["duration_months"]))
    elif coupon.times_redeemed == 0:
        # Self-heal a drifted, never-redeemed coupon. Coupons are immutable past
        # name/metadata, so heal = delete + recreate (deleting auto-deactivates any
        # promo codes pointing at it; the promo ensure below recreates the code).
        stripe.Coupon.delete(FOUNDER_COUPON_ID)
        coupon = _create_coupon()
        print("  RECREATED coupon %s - existing one did not match the FOUNDER spec "
              "(0 redemptions, safe)" % coupon.id)
    else:
        print("  !! coupon %s does not match the FOUNDER spec but has %d redemption(s) - "
              "NOT touching it; reconcile in the Stripe dashboard." % (coupon.id, coupon.times_redeemed))

    # Name is the one mutable field - keep the dashboard/checkout label canonical.
    if getattr(coupon, "name", None) != FOUNDER_COUPON_NAME:
        stripe.Coupon.modify(FOUNDER_COUPON_ID, name=FOUNDER_COUPON_NAME)
        print("  renamed coupon  %s -> %r" % (coupon.id, FOUNDER_COUPON_NAME))

    # The customer-typed code. Reuse only an ACTIVE promo that points at OUR coupon
    # (a promo whose coupon was deleted goes inactive, so it must not count as "exists");
    # deactivate any active same-code stray pointing elsewhere before recreating.
    code = spec["code"]
    active = stripe.PromotionCode.list(code=code, active=True, limit=10).data
    ours = [p for p in active if getattr(p.promotion, "coupon", None) == FOUNDER_COUPON_ID]
    for stray in [p for p in active if p not in ours]:
        stripe.PromotionCode.modify(stray.id, active=False)
        print("  deactivated stray promo %s (code %s pointed at %r)" % (
            stray.id, code, getattr(stray.promotion, "coupon", None)))
    if ours:
        print("  reused promo    %s (code %s)" % (ours[0].id, code))
    else:
        # Stripe SDK 15.x: the coupon nests under `promotion`, not a top-level
        # `coupon` param (same shape as affiliate_service/promo_service).
        pc = stripe.PromotionCode.create(
            code=code, promotion={"type": "coupon", "coupon": FOUNDER_COUPON_ID},
            max_redemptions=spec["max_redemptions"],
            metadata={"product_line": PRODUCT_LINE, "plan": "founder"},
        )
        print("  created promo   %s (code %s -> ~$%d/mo Pro)" % (pc.id, code, spec["effective_monthly"]))


def _portal_products(products, prices):
    return [
        {
            "product": products[tier].id,
            "prices": [prices[tier]["month"].id],
        }
        for tier in PAID_TIERS
    ]


def _portal_product_map(raw_products):
    result = {}
    for raw in raw_products or []:
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
            result[product] = frozenset(price_ids)
    return result


def _portal_features(expected_products):
    return {
        "payment_method_update": {"enabled": True},
        "invoice_history": {"enabled": True},
        "subscription_cancel": {
            "enabled": True,
            "mode": "at_period_end",
            "proration_behavior": "none",
        },
        "subscription_update": {
            "enabled": True,
            "default_allowed_updates": ["price", "promotion_code"],
            "proration_behavior": "create_prorations",
            "products": expected_products,
        },
    }


def _portal_configuration_matches(configuration, expected_products):
    configuration = _as_dict(configuration)
    if not configuration.get("active") or configuration.get("is_default"):
        return False
    metadata = _as_dict(configuration.get("metadata"))
    if metadata.get("tw2_purpose") != PORTAL_PURPOSE:
        return False
    features = _as_dict(configuration.get("features"))
    for feature_name in (
        "payment_method_update", "invoice_history", "subscription_cancel",
    ):
        if not _as_dict(features.get(feature_name)).get("enabled"):
            return False
    cancellation = _as_dict(features.get("subscription_cancel"))
    if (
        cancellation.get("mode") != "at_period_end"
        or cancellation.get("proration_behavior") != "none"
    ):
        return False
    subscription_update = _as_dict(features.get("subscription_update"))
    return bool(
        subscription_update.get("enabled")
        and set(subscription_update.get("default_allowed_updates") or [])
        == {"price", "promotion_code"}
        and subscription_update.get("proration_behavior")
        == "create_prorations"
        and _portal_product_map(subscription_update.get("products"))
        == _portal_product_map(expected_products)
    )


def _retrieve_api_portal_configuration(stripe, configuration_id):
    """Retrieve the complete portal catalog, including expandable products."""
    return stripe.billing_portal.Configuration.retrieve(
        configuration_id,
        expand=[PORTAL_PRODUCTS_EXPANSION],
    )


def _find_api_portal_configuration(stripe):
    configured_id = (os.environ.get(PORTAL_CONFIGURATION_ENV) or "").strip()
    if configured_id and "PLACEHOLDER" in configured_id.upper():
        # The staging secrets generator deliberately emits a fail-closed
        # placeholder. Treat it as "not seeded yet" so this operator command
        # can create the dedicated configuration whose real ID replaces it.
        configured_id = ""
    elif configured_id and not configured_id.startswith("bpc_"):
        raise RuntimeError(
            "REFUSING TO CONFIGURE: %s is not a Stripe Billing Portal "
            "configuration ID" % PORTAL_CONFIGURATION_ENV
        )
    if configured_id:
        configuration = _retrieve_api_portal_configuration(
            stripe, configured_id,
        )
        configuration_dict = _as_dict(configuration)
        if configuration_dict.get("is_default"):
            raise RuntimeError(
                "REFUSING TO CONFIGURE: %s points at Stripe's shared default "
                "portal; use a dedicated non-default configuration"
                % PORTAL_CONFIGURATION_ENV
            )
        metadata = _as_dict(configuration_dict.get("metadata"))
        if metadata.get("tw2_purpose") != PORTAL_PURPOSE:
            raise RuntimeError(
                "REFUSING TO CONFIGURE: %s points at a portal configuration "
                "without TradeWave API purpose metadata"
                % PORTAL_CONFIGURATION_ENV
            )
        return configuration

    matches = []
    for configuration in stripe.billing_portal.Configuration.list(
        active=True, limit=100,
    ).auto_paging_iter():
        metadata = _as_dict(getattr(configuration, "metadata", None))
        if metadata.get("tw2_purpose") == PORTAL_PURPOSE:
            matches.append(configuration)
    if len(matches) > 1:
        raise RuntimeError(
            "REFUSING TO CONFIGURE: multiple active TradeWave API portal "
            "configurations exist; set %s explicitly"
            % PORTAL_CONFIGURATION_ENV
        )
    if not matches:
        return None
    return _retrieve_api_portal_configuration(stripe, matches[0].id)


def _ensure_api_portal_configuration(stripe, products, prices):
    """Create/update the dedicated API portal and return its configuration."""
    expected_products = _portal_products(products, prices)
    features = _portal_features(expected_products)
    configuration = _find_api_portal_configuration(stripe)
    if configuration is None:
        configuration = stripe.billing_portal.Configuration.create(
            name=PORTAL_NAME,
            features=features,
            metadata={
                "product_line": PRODUCT_LINE,
                "tw2_purpose": PORTAL_PURPOSE,
            },
        )
        print("  created API Billing Portal configuration %s" % configuration.id)
        configuration = _retrieve_api_portal_configuration(
            stripe, configuration.id,
        )
    elif _portal_configuration_matches(configuration, expected_products):
        print("  reused API Billing Portal configuration  %s" % configuration.id)
    else:
        configuration = stripe.billing_portal.Configuration.modify(
            configuration.id,
            active=True,
            name=PORTAL_NAME,
            features=features,
            metadata={
                "product_line": PRODUCT_LINE,
                "tw2_purpose": PORTAL_PURPOSE,
            },
        )
        print("  updated API Billing Portal configuration %s" % configuration.id)
        configuration = _retrieve_api_portal_configuration(
            stripe, configuration.id,
        )

    if not _portal_configuration_matches(configuration, expected_products):
        raise RuntimeError(
            "API Billing Portal configuration did not verify after create/update"
        )
    print(
        "  persist on the WEB host: %s=%s"
        % (PORTAL_CONFIGURATION_ENV, configuration.id)
    )
    return configuration


def main():
    key = _require_seed_key()
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY

    print("Stripe %s mode confirmed. Ensuring API products/prices exist...\n" % mode)
    products = {}
    prices = {}
    for tier in PAID_TIERS:
        spec = api_tiers.API_TIERS[tier]
        label = "TradeWave API - %s" % spec["name"]

        product = _find_product(stripe, tier)
        if product is None:
            product = stripe.Product.create(
                name=label,
                metadata={"product_line": PRODUCT_LINE, "tier": tier},
            )
            print("  created product %s (%s)" % (product.id, label))
        else:
            print("  reused product  %s (%s)" % (product.id, label))
        products[tier] = product
        prices[tier] = {}

        # Monthly price ONLY (annual dropped 2026-07-05, reaffirmed 2026-07-17 -
        # rationale in apiserver/tiers.py).
        month_price = _ensure_price(stripe, product, tier, "month", spec["price_monthly"])
        prices[tier]["month"] = month_price

        # Self-heal an earlier annual seed: default_price must point at monthly
        # BEFORE archiving (Stripe refuses to archive a product's default price),
        # then archive every active annual price so the console/portal can never
        # resolve one.
        if getattr(product, "default_price", None) != month_price.id:
            stripe.Product.modify(product.id, default_price=month_price.id)
            print("    default_price -> %s (monthly)" % month_price.id)
        for price in stripe.Price.list(product=product.id, active=True, limit=100).auto_paging_iter():
            rec = _as_dict(getattr(price, "recurring", None))
            if rec.get("interval") == "year":
                stripe.Price.modify(price.id, active=False)
                print("    archived stale annual price %s" % price.id)

    print()
    _ensure_api_portal_configuration(stripe, products, prices)
    print()
    _ensure_founder(stripe, products["pro"].id)

    for tier in PAID_TIERS:
        spec = api_tiers.API_TIERS[tier]
        print("  %-8s $%d/mo (monthly only)" % (spec["name"], spec["price_monthly"]))

    print("\nDone. The console resolves prices live by (metadata product_line=api, tier), monthly "
          "only; the API console uses its dedicated Billing Portal configuration; Founder is the "
          "promo code customers type at checkout. Nothing hardcoded.")


if __name__ == "__main__":
    main()
