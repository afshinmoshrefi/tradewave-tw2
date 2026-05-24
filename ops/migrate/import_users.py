#!/usr/bin/env python3
"""
TW1 -> TW2 migration, step 2: IMPORT users into TW2 Postgres (+ link Stripe).

Run this ON A TW2 WEB BOX (staging first, then prod): it needs POSTGRES_DSN and
STRIPE_SECRET_KEY, which the web box already has in /etc/tradewave/secrets.env.
Reuses this repo's own models + tier_compat so the result matches the live app.
Nothing is hardcoded per-env.

  reads  : tw1_users.jsonl   (from tw1_export.py users)
  writes : the TW2 'users' table (idempotent upsert by lower(email))
  emits  : id_map.jsonl      (wp_user_id -> tw2 uuid; feeds the redis step)
           payer_report.txt  (every paid / flagged user, for human review)

DRY-RUN BY DEFAULT - prints what it would do, writes nothing. Add --apply to
commit. Never downgrades an existing row; never clobbers roles or
workos_user_id. Safe to re-run.

Tier source of truth, in order:
  1. an ACTIVE Stripe subscription matched by email -> tier from the price
     (price/product metadata product_line=eod + tier; else --legacy-price-map);
  2. else the WP UMP level via tier_compat;
  3. else explorer.
Disagreements and unmappable paid prices are FLAGGED, never silently resolved.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

try:  # reuse db_admin's secrets.env loader so `sudo python ...` sees the env
    from db_admin import _maybe_load_secrets_env
    _maybe_load_secrets_env()
except Exception:
    pass

import config as tw2_config  # noqa: E402
from sqlalchemy import func  # noqa: E402
from tier_compat import legacy_levels_to_tier, tier_to_legacy_level  # noqa: E402

TIER_RANK = {"explorer": 0, "analyst": 1, "strategist": 2}


def _higher(a, b):
    return a if TIER_RANK.get(a, 0) >= TIER_RANK.get(b, 0) else b


def _md(obj):
    """A Stripe object's metadata as a plain dict (the SDK object's .get is
    unreliable across versions; convert and use a real dict)."""
    try:
        return dict(obj["metadata"])
    except Exception:
        return {}


def _stripe_tier_for_price(stripe, price_id, legacy_map):
    if price_id in legacy_map:
        return legacy_map[price_id], "legacy-pin"
    price = stripe.Price.retrieve(price_id, expand=["product"])
    prod = price["product"]
    md = {} if isinstance(prod, str) else _md(prod)
    pm = _md(price)
    line = (md.get("product_line") or pm.get("product_line") or "").strip().lower()
    tier = (md.get("tier") or pm.get("tier") or "").strip().lower()
    if line == "eod" and tier in ("analyst", "strategist"):
        return tier, "metadata"
    return None, "unmappable"


def _stripe_lookup(stripe, email, legacy_map):
    out = {"customer_id": None, "subscription_id": None, "status": None,
           "tier": None, "reason": "no-customer", "flags": []}
    customers = stripe.Customer.list(email=email, limit=10)["data"]
    if not customers:
        return out
    cands = []
    for c in customers:
        for s in stripe.Subscription.list(customer=c["id"], status="all", limit=20)["data"]:
            if s["status"] in ("active", "trialing", "past_due"):
                pid = s["items"]["data"][0]["price"]["id"]
                tier, _ = _stripe_tier_for_price(stripe, pid, legacy_map)
                cands.append((c["id"], s, tier, pid))
    if len(customers) > 1:
        out["flags"].append("multiple-stripe-customers")
    if not cands:
        out["customer_id"] = customers[0]["id"]
        out["reason"] = "customer-no-active-sub"
        return out
    cands.sort(key=lambda t: TIER_RANK.get(t[2] or "", -1), reverse=True)
    cust_id, sub, tier, pid = cands[0]
    out.update(customer_id=cust_id, subscription_id=sub["id"], status=sub["status"],
               tier=tier, reason="active-sub")
    if tier is None:
        out["flags"].append("unmappable-price:%s" % pid)
    if len({t[2] for t in cands if t[2]}) > 1:
        out["flags"].append("multiple-active-tiers")
    return out


def _persist(s, u, is_new):
    """Flush one row in a savepoint; on a unique collision (most likely the
    stripe_customer_id), retry once without the customer link so the user row
    still lands. Returns an error string or None."""
    try:
        with s.begin_nested():
            s.flush()
        return None
    except Exception as e1:
        if u.stripe_customer_id:
            u.stripe_customer_id = None
            try:
                with s.begin_nested():
                    s.flush()
                return "stripe_customer_id-collision (cleared): %s" % str(e1)[:120]
            except Exception as e2:
                if is_new:
                    s.expunge(u)
                return "persist-failed: %s" % str(e2)[:160]
        if is_new:
            s.expunge(u)
        return "persist-failed: %s" % str(e1)[:160]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="infile", default="tw1_users.jsonl")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--legacy-price-map",
                    help="JSON {price_id: tier} for legacy no-metadata prices")
    ap.add_argument("--skip-stripe", action="store_true",
                    help="skip Stripe linkage (mechanics-only run)")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    a = ap.parse_args()

    legacy_map = {}
    if a.legacy_price_map:
        with open(a.legacy_price_map) as f:
            legacy_map = {str(k): str(v) for k, v in json.load(f).items()}

    stripe = None
    if not a.skip_stripe:
        import stripe as stripe_mod
        key = getattr(tw2_config, "STRIPE_SECRET_KEY", "") or os.environ.get("STRIPE_SECRET_KEY", "")
        if not key:
            sys.exit("STRIPE_SECRET_KEY not set; use --skip-stripe for a mechanics-only run")
        stripe_mod.api_key = key
        stripe = stripe_mod

    from models import Session, User  # lazy import (matches db_admin pattern)
    s = Session()
    created = updated = skipped = errors = 0
    id_map, report = [], []
    try:
        with open(a.infile) as f:
            rows = [json.loads(l) for l in f if l.strip()]

        for row in rows:
            email = (row.get("email") or "").strip().lower()
            wp_id = row.get("wp_user_id")
            if not email:
                report.append("SKIP wp_user_id=%s : no email" % wp_id)
                skipped += 1
                continue

            level_ids = [str(x) for x in (row.get("active_level_ids") or [])]
            wp_tier = legacy_levels_to_tier(level_ids) if level_ids else "explorer"
            sl = ({"customer_id": None, "subscription_id": None, "status": None,
                   "tier": None, "reason": "skipped", "flags": []}
                  if stripe is None else _stripe_lookup(stripe, email, legacy_map))

            stripe_tier = sl["tier"]
            final_tier = stripe_tier or wp_tier
            flags = list(sl["flags"])
            if stripe_tier and wp_tier != "explorer" and stripe_tier != wp_tier:
                flags.append("tier-mismatch wp=%s stripe=%s" % (wp_tier, stripe_tier))
            if wp_tier != "explorer" and sl["reason"] in ("no-customer", "customer-no-active-sub"):
                flags.append("wp-paid-but-no-active-stripe-sub")

            u = s.query(User).filter(func.lower(User.email) == email).first()
            is_new = u is None
            if is_new:
                u = User(email=email, roles=["user"])
                s.add(u)
            new_tier = final_tier if is_new else _higher(final_tier, u.tier or "explorer")
            u.tier = new_tier
            u.legacy_wp_level = tier_to_legacy_level(new_tier)
            u.email_verified = True
            if sl["customer_id"] and not u.stripe_customer_id:
                u.stripe_customer_id = sl["customer_id"]
            if sl["subscription_id"]:
                u.stripe_subscription_id = sl["subscription_id"]
                u.stripe_subscription_status = sl["status"]
            # roles + workos_user_id intentionally left untouched on existing rows

            uid = None
            if a.apply:
                err = _persist(s, u, is_new)
                if err:
                    flags.append(err)
                    errors += 1
                    if "persist-failed" in err:
                        report.append("ERROR %-30s wp_id=%s : %s" % (email, wp_id, err))
                        continue
                uid = str(u.id) if u.id else None

            id_map.append({"wp_user_id": wp_id, "email": email, "uuid": uid, "tier": new_tier})
            created += int(is_new)
            updated += int(not is_new)
            if new_tier != "explorer" or flags or sl["customer_id"]:
                report.append(
                    "%-32s wp_id=%-6s tier=%-10s (wp=%-10s stripe=%s) cust=%s%s"
                    % (email, wp_id, new_tier, wp_tier, stripe_tier, sl["customer_id"],
                       ("  FLAGS: " + "; ".join(flags)) if flags else ""))

        s.commit() if a.apply else s.rollback()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "id_map.jsonl"), "w") as f:
        for m in id_map:
            f.write(json.dumps(m) + "\n")
    with open(os.path.join(a.out_dir, "payer_report.txt"), "w") as f:
        f.write("\n".join(report) + ("\n" if report else ""))

    print("%s  created=%d updated=%d skipped=%d errors=%d  flagged/paid lines=%d"
          % ("APPLIED" if a.apply else "DRY-RUN (nothing written)",
             created, updated, skipped, errors, len(report)))
    print("  id_map -> %s/id_map.jsonl   payer_report -> %s/payer_report.txt"
          % (a.out_dir, a.out_dir))
    if not a.apply:
        print("  NOTE: dry-run assigns no uuids. Review payer_report.txt, then re-run "
              "with --apply to populate id_map for the redis step.")


if __name__ == "__main__":
    main()
