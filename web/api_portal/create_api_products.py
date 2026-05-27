#!/usr/bin/env python3
"""Idempotently create the 4 TradeWave API products + monthly prices in Stripe
TEST mode, with metadata product_line=api + tier so the console's billing code
(and the web app's webhook) can resolve them deterministically.

  DO NOT RUN THIS DURING THE CONSOLE BUILD. The parent runs it ONCE at
  integration with a confirmed Stripe TEST key:

      cd /home/flask
      STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python web/api_portal/create_api_products.py

Safety:
  - Refuses to run unless STRIPE_SECRET_KEY starts with 'sk_test_'. A live key
    (sk_live_) aborts immediately - this script must never touch live Stripe.
  - Idempotent: it looks up existing products by (product_line=api, tier)
    metadata and reuses them; it looks up an existing active monthly price on
    that product and reuses it. Re-running makes no duplicates.

Source of truth for the tiers/prices is apiserver.tiers.API_TIERS (the same
dict the console + gateway read). The free tier has no Stripe product.
"""
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


def _require_test_key():
    key = config.STRIPE_SECRET_KEY or ""
    if not key.startswith("sk_test_"):
        sys.exit(
            "REFUSING TO RUN: STRIPE_SECRET_KEY is not a TEST key (expected "
            "'sk_test_...'). This script must only run against Stripe TEST mode.\n"
            "Re-run as: STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python "
            "web/api_portal/create_api_products.py"
        )
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


def _find_monthly_price(stripe, product_id):
    """Find an existing active recurring-monthly price on the product, or None."""
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        rec = price.recurring.to_dict() if getattr(price, "recurring", None) else {}
        if rec.get("interval") == "month":
            return price
    return None


def main():
    _require_test_key()
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY

    print("Stripe TEST mode confirmed. Ensuring API products/prices exist...\n")
    for tier in PAID_TIERS:
        spec = api_tiers.API_TIERS[tier]
        label = "TradeWave API - %s" % spec["name"]
        amount_cents = int(spec["price_monthly"]) * 100

        product = _find_product(stripe, tier)
        if product is None:
            product = stripe.Product.create(
                name=label,
                metadata={"product_line": PRODUCT_LINE, "tier": tier},
            )
            print("  created product %s (%s)" % (product.id, label))
        else:
            print("  reused product  %s (%s)" % (product.id, label))

        price = _find_monthly_price(stripe, product.id)
        if price is None:
            price = stripe.Price.create(
                product=product.id,
                unit_amount=amount_cents,
                currency=CURRENCY,
                recurring={"interval": "month"},
                metadata={"product_line": PRODUCT_LINE, "tier": tier},
            )
            print("    created price %s ($%d/mo)" % (price.id, spec["price_monthly"]))
        else:
            print("    reused price  %s ($%d/mo)" % (price.id, spec["price_monthly"]))

    print("\nDone. The console resolves these live by metadata; nothing to hardcode.")


if __name__ == "__main__":
    main()
