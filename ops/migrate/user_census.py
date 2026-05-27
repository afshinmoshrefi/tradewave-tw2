#!/usr/bin/env python3
"""
user_census.py - read-only breakdown of the TW2 `users` table.

Answers "why are there N users?" by classifying every row: tier split,
Stripe-subscription status, paying vs free, WorkOS-linked, migrated-from-TW1
vs native signup, the privileged/service rows, and a per-day created_at
histogram (so a migration seed spike vs later organic signups is obvious).

Makes ZERO writes. Safe to run anytime. Run on a TW2 WEB box (needs
POSTGRES_DSN from /etc/tradewave/secrets.env):

  sudo -u flask /home/flask/venv/bin/python /home/flask/ops/migrate/user_census.py

Or pipe it in from a dev checkout without deploying first:

  ssh -p 4369 root@<prod-web> 'sudo -u flask /home/flask/venv/bin/python -' < ops/migrate/user_census.py
"""
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")
try:
    from db_admin import _maybe_load_secrets_env
    _maybe_load_secrets_env()
except Exception:
    pass

from sqlalchemy import text  # noqa: E402
from models import Session  # noqa: E402


def main() -> int:
    s = Session()

    def rows(sql):
        return s.execute(text(sql)).fetchall()

    def scalar(sql):
        return s.execute(text(sql)).scalar()

    total = scalar("select count(*) from users")

    def section(title, pairs):
        print(f"\n{title}")
        for k, v in pairs:
            print(f"  {str(k):<28} {v}")

    print(f"TOTAL users: {total}")

    section("by tier", rows(
        "select tier, count(*) from users group by tier order by 2 desc"))

    section("by stripe_subscription_status", rows(
        "select coalesce(stripe_subscription_status, '(none)'), count(*) "
        "from users group by 1 order by 2 desc"))

    section("billing / identity", [
        ("has stripe_subscription_id", scalar(
            "select count(*) from users where stripe_subscription_id is not null")),
        ("has stripe_customer_id", scalar(
            "select count(*) from users where stripe_customer_id is not null")),
        ("workos-linked", scalar(
            "select count(*) from users where workos_user_id is not null")),
        ("email_verified", scalar(
            "select count(*) from users where email_verified")),
    ])

    section("origin", [
        ("migrated (legacy_wp_level set)", scalar(
            "select count(*) from users where legacy_wp_level is not null")),
        ("native (no legacy_wp_level)", scalar(
            "select count(*) from users where legacy_wp_level is null")),
        ("service_account role", scalar(
            "select count(*) from users where roles @> '[\"service_account\"]'::jsonb")),
        ("super_admin role", scalar(
            "select count(*) from users where roles @> '[\"super_admin\"]'::jsonb")),
    ])

    section("created_at by day (seed spike vs organic signups)", rows(
        "select created_at::date, count(*) from users group by 1 order by 1"))

    # Headline interpretation: paying = an active/trialing Stripe sub; everyone
    # else is effectively free (the migration imported the whole TW1 base, which
    # is overwhelmingly free Explorer accounts).
    paying = scalar(
        "select count(*) from users where stripe_subscription_status "
        "in ('active', 'trialing')")
    print(f"\nHEADLINE: {paying} paying (active/trialing Stripe), "
          f"{total - paying} free/other of {total} total.")

    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
