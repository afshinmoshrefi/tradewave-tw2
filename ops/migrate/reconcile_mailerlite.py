#!/usr/bin/env python3
"""
reconcile_mailerlite.py - one-time (re-runnable) reconcile of TW2 Postgres users
into their correct Mailerlite LEVEL group, replicating the TW1/UMP "level -> group"
behavior. Source of truth = Postgres (tier) + the live Stripe subscription (period).

Run on a TW2 WEB box (needs POSTGRES_DSN + STRIPE_SECRET_KEY + MAILERLITE_API_KEY).
DRY-RUN by default - prints the planned change per user and makes NO Mailerlite
writes. Add --apply to execute. Idempotent: re-running converges.

  sudo -u flask /home/flask/venv/bin/python reconcile_mailerlite.py            # dry-run
  sudo -u flask /home/flask/venv/bin/python reconcile_mailerlite.py --apply    # execute
  ... --email someone@x.com    # just one (test)
  ... --limit 10               # first N

Rules (enforced by email_utils.sync_mailerlite_level_group):
  - each account in EXACTLY its current level group, removed from the other 4;
  - only the 5 LEVEL groups are touched (SMN / newsletter / webinar untouched);
  - unsubscribed/bounced subscribers are never added (only removed from wrong groups);
  - a paid user whose period can't be derived (legacy/unmappable price, or a manual
    comp with no Stripe sub) is SKIPPED + logged for manual placement.
"""
import argparse
import sys
import time

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")
try:
    from db_admin import _maybe_load_secrets_env
    _maybe_load_secrets_env()
except Exception:
    pass

import config  # noqa: E402
from email_utils import sync_mailerlite_level_group  # noqa: E402


def _period_from_stripe(stripe, sub_id):
    """Return 'monthly'/'yearly' for a subscription's price (via product metadata),
    or None if missing / unmappable / on error."""
    if not sub_id:
        return None
    try:
        sub = stripe.Subscription.retrieve(sub_id, expand=["items.data.price.product"])
        items = sub.get("items", {}).get("data", []) if isinstance(sub, dict) else sub["items"]["data"]
        if not items:
            return None
        price = items[0]["price"]
        prod = price.get("product") if isinstance(price, dict) else price["product"]
        md = (prod.get("metadata") or {}) if isinstance(prod, dict) else {}
        line = (md.get("product_line") or "").strip().lower()
        tier = (md.get("tier") or "").strip().lower()
        period = (md.get("period") or "").strip().lower()
        if line == "eod" and tier in ("analyst", "strategist") and period in ("monthly", "yearly"):
            return period
        return None
    except Exception as e:
        print("  WARN stripe retrieve %s: %s" % (sub_id, str(e)[:120]), file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--email", help="limit to one email")
    ap.add_argument("--limit", type=int, help="limit to the first N")
    ap.add_argument("--sleep", type=float, default=1.2,
                    help="seconds between users (rate-limit throttle; default 1.2)")
    a = ap.parse_args()

    if config._is_placeholder(config.MAILERLITE_API_KEY) if hasattr(config, "_is_placeholder") \
            else (not config.MAILERLITE_API_KEY or "PLACEHOLDER" in config.MAILERLITE_API_KEY):
        sys.exit("MAILERLITE_API_KEY not set (run on a TW2 web box with secrets)")

    import stripe
    stripe.api_key = getattr(config, "STRIPE_SECRET_KEY", "") or ""

    from models import Session, User
    s = Session()
    q = s.query(User).filter(User.email.isnot(None), User.email != "")
    rows = [u for u in q.all() if not (u.roles and "service_account" in u.roles)]
    if a.email:
        em = a.email.strip().lower()
        rows = [u for u in rows if (u.email or "").lower() == em]
    if a.limit:
        rows = rows[:a.limit]

    mode = "APPLY" if a.apply else "DRY-RUN"
    print("=== reconcile_mailerlite %s  candidates=%d ===" % (mode, len(rows)))
    counts = {}
    for i, u in enumerate(rows, 1):
        tier = (u.tier or "explorer").strip().lower()
        active = (u.stripe_subscription_status or "") in ("active", "trialing", "past_due")
        if tier in ("explorer", "canceled") or not active:
            tier_for_group, period = "explorer", None
        else:
            period = _period_from_stripe(stripe, u.stripe_subscription_id)
            tier_for_group = tier  # Postgres tier is operational truth; Stripe gives period
        result = sync_mailerlite_level_group(u.email, tier_for_group, period,
                                             new_user=False, dry_run=not a.apply)
        bucket = result.split(":")[0].split("(")[0]
        counts[bucket] = counts.get(bucket, 0) + 1
        print("  %-40s tier=%-10s period=%-7s -> %s"
              % (u.email, tier_for_group, period or "-", result))
        if i % 25 == 0:
            print("  ...%d/%d" % (i, len(rows)), file=sys.stderr)
        time.sleep(a.sleep)

    print("=== %s done. summary: %s ===" % (mode, counts))
    if not a.apply:
        print("Re-run with --apply to execute these changes.")


if __name__ == "__main__":
    main()
