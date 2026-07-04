#!/usr/bin/env python3
"""Idempotently create the TradeWave **Navigator** web/EOD product + monthly/yearly
prices in Stripe, with metadata product_line=eod + tier=navigator + period so the
web app's price cache (web/app.py _refresh_price_cache) and the home-page pricing
(site/generate_home_page.py _stripe_prices) resolve them deterministically.

  WHY a script: the existing eod tiers (analyst/strategist) were created by hand in
  the Stripe dashboard; Navigator is new. This mirrors web/api_portal/
  create_api_products.py's safety gates so the operator can seed it the same way.

  DEV NOTE: the dev box has NO Stripe key (STRIPE_SECRET_KEY empty), so checkout is
  503 on dev regardless. Run this against the shared account with a confirmed key:

      cd /home/flask
      STRIPE_SECRET_KEY=sk_test_...  ./venv/bin/python web/create_eod_navigator_product.py
      # LIVE (double-gated):
      TW2_CONFIRM_LIVE_SEED=1 STRIPE_SECRET_KEY=sk_live_... \\
          ./venv/bin/python web/create_eod_navigator_product.py --live

After seeding: restart the web unit so _price_cache picks up the new prices.

Prices (match site/generate_home_page.py fallback + project_tw2_current_prices):
  Navigator  $19/mo   $168/yr  (= $14/mo-equiv, ~26% off monthly)
Metadata on EACH price's product: product_line=eod, tier=navigator, period=monthly|yearly.
"""
import os
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

import config

CURRENCY = "usd"
PRODUCT_LINE = "eod"
TIER = "navigator"
PRODUCT_NAME = "TradeWave Navigator"
# (period -> (recurring interval, dollars)). Keep in sync with the home-page fallback.
PRICES = {
    "monthly": ("month", 19),
    "yearly":  ("year", 168),
}


def _require_seed_key():
    """TEST-only by default; LIVE permitted only with --live AND TW2_CONFIRM_LIVE_SEED=1
    (plus a typed 'yes' on a TTY). Any non-sk_test_/sk_live_ key is refused."""
    live = "--live" in sys.argv[1:]
    key = config.STRIPE_SECRET_KEY or ""
    if not (key.startswith("sk_test_") or key.startswith("sk_live_")):
        sys.exit(
            "REFUSING TO RUN: STRIPE_SECRET_KEY is not a recognizable Stripe secret key "
            "(expected 'sk_test_...' or, with --live, 'sk_live_...').\n"
            "Re-run as: STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python "
            "web/create_eod_navigator_product.py"
        )
    if not live:
        if not key.startswith("sk_test_"):
            sys.exit(
                "REFUSING TO RUN: STRIPE_SECRET_KEY is a LIVE key but --live was not passed. "
                "This script defaults to Stripe TEST mode only.\n"
                "For a LIVE seed (guarded): set TW2_CONFIRM_LIVE_SEED=1 and pass --live."
            )
        return key
    if not key.startswith("sk_live_"):
        sys.exit("REFUSING TO RUN: --live was passed but STRIPE_SECRET_KEY is not a LIVE key.")
    if os.environ.get("TW2_CONFIRM_LIVE_SEED") != "1":
        sys.exit(
            "REFUSING TO RUN: --live requires env TW2_CONFIRM_LIVE_SEED=1 as an explicit confirmation."
        )
    print("\n!!! LIVE STRIPE SEED - creates a REAL, BILLABLE Navigator product "
          "($19/mo, $168/yr) in LIVE Stripe. !!!\n")
    if sys.stdin.isatty():
        try:
            answer = input("Type 'yes' to seed Navigator into LIVE Stripe: ").strip()
        except EOFError:
            answer = ""
        if answer != "yes":
            sys.exit("Aborted: live seed not confirmed ('yes' not typed).")
    return key


def _find_product(stripe):
    """Find an existing product with metadata product_line=eod + tier=navigator, or None."""
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        md = prod.metadata.to_dict() if getattr(prod, "metadata", None) else {}
        if (md.get("product_line") or "").lower() == PRODUCT_LINE and (md.get("tier") or "").lower() == TIER:
            return prod
    return None


def _find_price(stripe, product_id, interval):
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        rec = price.recurring.to_dict() if getattr(price, "recurring", None) else {}
        if rec.get("interval") == interval:
            return price
    return None


def _ensure_price(stripe, product, period, interval, dollars):
    price = _find_price(stripe, product.id, interval)
    if price is None:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=int(dollars) * 100,
            currency=CURRENCY,
            recurring={"interval": interval},
            # product_line/tier live on the PRODUCT metadata (that's what the web app
            # reads via expand=data.product); period is the per-price discriminator.
            metadata={"product_line": PRODUCT_LINE, "tier": TIER, "period": period},
        )
        print("    created price %s ($%d %s)" % (price.id, dollars, period))
    else:
        print("    reused price  %s ($%d %s)" % (price.id, dollars, period))
    return price


def main():
    key = _require_seed_key()
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    print("Stripe %s mode confirmed. Ensuring Navigator product/prices exist...\n" % mode)

    product = _find_product(stripe)
    if product is None:
        product = stripe.Product.create(
            name=PRODUCT_NAME,
            metadata={"product_line": PRODUCT_LINE, "tier": TIER},
        )
        print("  created product %s (%s)" % (product.id, PRODUCT_NAME))
    else:
        # Ensure the metadata is present even if the product pre-existed.
        if (product.metadata.get("product_line") != PRODUCT_LINE
                or product.metadata.get("tier") != TIER):
            stripe.Product.modify(product.id, metadata={"product_line": PRODUCT_LINE, "tier": TIER})
        print("  reused product  %s (%s)" % (product.id, PRODUCT_NAME))

    for period, (interval, dollars) in PRICES.items():
        _ensure_price(stripe, product, period, interval, dollars)

    print("\nDone. The web app resolves prices live by (product metadata product_line=eod, "
          "tier=navigator) + period. RESTART the web unit to refresh _price_cache.")


if __name__ == "__main__":
    main()
