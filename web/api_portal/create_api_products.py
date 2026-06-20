#!/usr/bin/env python3
"""Idempotently create the TradeWave API products + monthly/annual prices in
Stripe (Dev/Pro/Business), with metadata product_line=api + tier so the
console's billing code (and the web app's webhook) can resolve them
deterministically.

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
    metadata and reuses them; it looks up an existing active monthly price on
    that product and reuses it. Re-running makes no duplicates.

Source of truth for the tiers/prices is apiserver.tiers.API_TIERS (the same
dict the console + gateway read). The free tier has no Stripe product.
"""
import os
import sys

# Make the apiserver package + config importable from any CWD.
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

import config
from apiserver import tiers as api_tiers

CURRENCY = "usd"
PRODUCT_LINE = "api"
# Tiers that get a Stripe product (free is not purchasable).
PAID_TIERS = ["dev", "pro", "business"]


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
            "    - TradeWave API - %-8s  $%d/mo  +  $%d/yr"
            % (spec["name"], spec["price_monthly"], spec["price_annual"])
        )
    f = api_tiers.FOUNDER
    lines += [
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
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        md = prod.metadata.to_dict() if getattr(prod, "metadata", None) else {}
        if (md.get("product_line") or "").lower() == PRODUCT_LINE and (md.get("tier") or "").lower() == tier:
            return prod
    return None


def _find_price_for_interval(stripe, product_id, interval):
    """Find an existing active recurring price with the given interval, or None."""
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        rec = price.recurring.to_dict() if getattr(price, "recurring", None) else {}
        if rec.get("interval") == interval:
            return price
    return None


def _ensure_price(stripe, product, tier, interval, dollars):
    """Idempotently ensure an active <interval> price exists on the product."""
    unit = "/mo" if interval == "month" else "/yr"
    price = _find_price_for_interval(stripe, product.id, interval)
    if price is None:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=int(dollars) * 100,
            currency=CURRENCY,
            recurring={"interval": interval},
            metadata={"product_line": PRODUCT_LINE, "tier": tier, "interval": interval},
        )
        print("    created price %s ($%d%s)" % (price.id, dollars, unit))
    else:
        print("    reused price  %s ($%d%s)" % (price.id, dollars, unit))
    return price


# Founder's plan = Pro at 50% off for 12 months, first 100 customers. A Stripe coupon
# (repeating 12 months, capped at 100 redemptions, restricted to the Pro product) plus a
# promotion code the customer types at checkout (allow_promotion_codes=True is already set).
FOUNDER_COUPON_ID = "founder_pro_50_12mo"


def _ensure_founder(stripe, pro_product_id):
    spec = api_tiers.FOUNDER
    try:
        coupon = stripe.Coupon.retrieve(FOUNDER_COUPON_ID)
        print("  reused coupon   %s (%d%% off, %dmo)" % (coupon.id, spec["percent_off"], spec["duration_months"]))
    except Exception:
        coupon = stripe.Coupon.create(
            id=FOUNDER_COUPON_ID,
            percent_off=spec["percent_off"],
            duration="repeating",
            duration_in_months=spec["duration_months"],
            max_redemptions=spec["max_redemptions"],
            applies_to={"products": [pro_product_id]},
            name="TradeWave Founder (Pro 50%% off 12mo)",
            metadata={"product_line": PRODUCT_LINE, "plan": "founder"},
        )
        print("  created coupon  %s (%d%% off Pro, %dmo, max %d)" % (
            coupon.id, spec["percent_off"], spec["duration_months"], spec["max_redemptions"]))

    # The customer-typed code. Reuse if a promo code with this code already exists.
    code = spec["code"]
    existing = stripe.PromotionCode.list(code=code, limit=1).data
    if existing:
        print("  reused promo    %s (code %s)" % (existing[0].id, code))
    else:
        pc = stripe.PromotionCode.create(
            coupon=coupon.id, code=code, max_redemptions=spec["max_redemptions"],
            metadata={"product_line": PRODUCT_LINE, "plan": "founder"},
        )
        print("  created promo   %s (code %s -> ~$%d/mo Pro)" % (pc.id, code, spec["effective_monthly"]))


def main():
    key = _require_seed_key()
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY

    print("Stripe %s mode confirmed. Ensuring API products/prices exist...\n" % mode)
    products = {}
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

        # Monthly + annual price (annual = price_annual, i.e. 10x monthly = 2 months free).
        _ensure_price(stripe, product, tier, "month", spec["price_monthly"])
        _ensure_price(stripe, product, tier, "year", spec["price_annual"])

    print()
    _ensure_founder(stripe, products["pro"].id)

    print("\nDone. The console resolves prices live by (metadata product_line=api, tier) + interval; "
          "Founder is the promo code customers type at checkout. Nothing hardcoded.")


if __name__ == "__main__":
    main()
