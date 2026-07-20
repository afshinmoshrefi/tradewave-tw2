#!/usr/bin/env python3
"""Read-only launch audit for the API Stripe catalog and Billing Portal.

This script deliberately reuses the console's fail-closed runtime validators.
It lists Stripe prices and retrieves one Billing Portal configuration; it never
creates, modifies, archives, or deletes a Stripe object.
"""

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
for candidate in (str(REPO_ROOT), str(WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

def _stripe_mode(config):
    secret = (config.STRIPE_SECRET_KEY or "").strip()
    publishable = (config.STRIPE_PUBLISHABLE_KEY or "").strip()
    secret_mode = "test" if secret.startswith("sk_test_") else "live" if secret.startswith("sk_live_") else None
    publishable_mode = "test" if publishable.startswith("pk_test_") else "live" if publishable.startswith("pk_live_") else None
    if not secret_mode or secret_mode != publishable_mode:
        raise RuntimeError("Stripe secret and publishable keys are missing, invalid, or use different modes")
    return secret_mode


def audit(expect_mode, expect_pricing):
    # Delay application imports until after argument parsing so --help remains
    # usable on an operator workstation without server-only configuration.
    import config
    from apiserver import tiers as api_tiers
    from api_portal import routes_billing as billing

    mode = _stripe_mode(config)
    if mode != expect_mode:
        raise RuntimeError("Stripe mode does not match --expect-mode")

    pricing = "on" if api_tiers.API_PRICING_LIVE else "off"
    if pricing != expect_pricing:
        raise RuntimeError("pricing visibility does not match --expect-pricing")

    billing._price_cache.clear()
    billing._refresh_price_cache()
    billing._validated_portal_configuration_id()

    prices = ", ".join(
        "%s $%d/mo" % (
            api_tiers.API_TIERS[tier]["name"],
            api_tiers.API_TIERS[tier]["price_monthly"],
        )
        for tier in billing.PURCHASABLE_TIERS
    )
    return mode, pricing, prices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-mode", required=True, choices=("test", "live"))
    parser.add_argument("--expect-pricing", required=True, choices=("off", "on"))
    args = parser.parse_args()

    try:
        mode, pricing, prices = audit(args.expect_mode, args.expect_pricing)
    except RuntimeError as exc:
        raise SystemExit("FAIL: %s" % exc) from None
    except Exception as exc:
        # Avoid dumping remote object payloads, request headers, or credentials.
        raise SystemExit("FAIL: Stripe read failed (%s)" % type(exc).__name__) from None

    print("PASS: Stripe %s mode; pricing %s" % (mode.upper(), pricing))
    print("PASS: exact monthly API catalog: %s" % prices)
    print("PASS: dedicated API Billing Portal configuration is exact")


if __name__ == "__main__":
    main()
