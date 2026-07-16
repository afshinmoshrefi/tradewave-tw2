#!/usr/bin/env python3
"""Idempotently create the TradeWave **Navigator** web/EOD products + prices in
Stripe, matching the DEPLOYED metadata contract: ONE PRODUCT PER (tier, period)
with metadata product_line=eod + tier=navigator + period=monthly|yearly ON THE
PRODUCT - exactly how the hand-created Analyst/Strategist products look
("TradeWave Analyst Monthly" etc.). Both consumers read the PRODUCT metadata for
all three keys (web/app.py _refresh_price_cache; site/generate_home_page.py
_stripe_prices), so a single product carrying two periods can never match.

  LESSON (2026-07-04 prod seed): the first version of this script created one
  "TradeWave Navigator" product with period only on the PRICES - both matchers
  ignored it and the home generator fail-fasted on missing navigator slots.
  This version seeds per-period products and ARCHIVES any such periodless
  navigator product it finds, so re-running self-heals that state.

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
"""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config

CURRENCY = "usd"
PRODUCT_LINE = "eod"
TIER = "navigator"
# period -> (product name, recurring interval, dollars). One PRODUCT per period,
# mirroring the live Analyst/Strategist convention. Keep in sync with the
# home-page fallback.
PERIODS = {
    "monthly": ("TradeWave Navigator Monthly", "month", 19),
    "yearly":  ("TradeWave Navigator Yearly",  "year", 168),
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
    print("\n!!! LIVE STRIPE SEED - creates REAL, BILLABLE Navigator products "
          "($19/mo, $168/yr) in LIVE Stripe. !!!\n")
    if sys.stdin.isatty():
        try:
            answer = input("Type 'yes' to seed Navigator into LIVE Stripe: ").strip()
        except EOFError:
            answer = ""
        if answer != "yes":
            sys.exit("Aborted: live seed not confirmed ('yes' not typed).")
    return key


def _navigator_products(stripe):
    """All active products with metadata product_line=eod + tier=navigator,
    keyed by their period metadata ('' when absent - the broken shape)."""
    found = {}
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        md = prod.metadata.to_dict() if getattr(prod, "metadata", None) else {}
        if ((md.get("product_line") or "").lower() == PRODUCT_LINE
                and (md.get("tier") or "").lower() == TIER):
            found.setdefault((md.get("period") or "").lower(), []).append(prod)
    return found


def _archive_periodless(stripe, products):
    """Deactivate a periodless navigator product + its prices (the mis-seeded
    shape neither matcher can use) so re-runs self-heal."""
    for prod in products:
        for price in stripe.Price.list(product=prod.id, active=True, limit=100).auto_paging_iter():
            stripe.Price.modify(price.id, active=False)
            print("  archived price   %s (periodless product)" % price.id)
        stripe.Product.modify(prod.id, active=False)
        print("  archived product %s (%s - no period metadata)" % (prod.id, prod.name))


def _ensure_period_product(stripe, period, existing):
    name, interval, dollars = PERIODS[period]
    md = {"product_line": PRODUCT_LINE, "tier": TIER, "period": period}
    if existing:
        product = existing[0]
        cur = product.metadata.to_dict() if getattr(product, "metadata", None) else {}
        if any(cur.get(k) != v for k, v in md.items()):
            stripe.Product.modify(product.id, metadata=md)
        print("  reused product  %s (%s)" % (product.id, product.name))
    else:
        product = stripe.Product.create(name=name, metadata=md)
        print("  created product %s (%s)" % (product.id, name))

    for price in stripe.Price.list(product=product.id, active=True, limit=100).auto_paging_iter():
        rec = price.recurring.to_dict() if getattr(price, "recurring", None) else {}
        if rec.get("interval") == interval and price.unit_amount == int(dollars) * 100:
            print("    reused price  %s ($%d %s)" % (price.id, dollars, period))
            return
    price = stripe.Price.create(
        product=product.id,
        unit_amount=int(dollars) * 100,
        currency=CURRENCY,
        recurring={"interval": interval},
        metadata={"product_line": PRODUCT_LINE, "tier": TIER, "period": period},
    )
    print("    created price %s ($%d %s)" % (price.id, dollars, period))


def main():
    key = _require_seed_key()
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    print("Stripe %s mode confirmed. Ensuring Navigator products/prices exist...\n" % mode)

    by_period = _navigator_products(stripe)
    _archive_periodless(stripe, by_period.get("", []))
    for period in PERIODS:
        _ensure_period_product(stripe, period, by_period.get(period, []))

    print("\nDone. Both matchers resolve by PRODUCT metadata (product_line=eod, "
          "tier=navigator, period). RESTART the web unit to refresh _price_cache.")


if __name__ == "__main__":
    main()
