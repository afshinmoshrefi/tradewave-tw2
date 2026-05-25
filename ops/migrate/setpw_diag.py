#!/usr/bin/env python3
"""
setpw_diag.py - set a WorkOS user's password directly + verify it authenticates.

A diagnostic/test helper for the migrated-user login. It BYPASSES WorkOS's hosted
set-password page entirely:
  1) sets the user's password via user_management.update_user, then
  2) calls authenticate_with_password to prove email/password auth works in THIS env.

This answers, definitively, "does email/password login work in prod?" without any
hosted page or redirect involved. On any failure it prints the exact WorkOS error.

  sudo -u flask -E /home/flask/venv/bin/python ops/migrate/setpw_diag.py --email someone@x.com
  ... --password 'Custom-Pw-Here'     # override the default test password
"""
import argparse
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")
try:  # pick up /etc/tradewave/secrets.env for ad-hoc `sudo python` runs
    from db_admin import _maybe_load_secrets_env
    _maybe_load_secrets_env()
except Exception:
    pass

import config  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", default="Migrate-TW2-2026!")
    a = ap.parse_args()

    key = getattr(config, "WORKOS_API_KEY", "") or ""
    cid = getattr(config, "WORKOS_CLIENT_ID", "") or ""
    if not (key and cid):
        sys.exit("WORKOS_API_KEY / WORKOS_CLIENT_ID not set (run on a TW2 web box)")

    from sqlalchemy import func
    from workos import WorkOSClient
    from workos.user_management._resource import PasswordPlaintext
    from models import Session, User

    wc = WorkOSClient(api_key=key, client_id=cid)
    s = Session()
    em = a.email.strip().lower()
    u = s.query(User).filter(func.lower(User.email) == em).first()
    if not u:
        sys.exit("no Postgres user for %s" % a.email)
    if not u.workos_user_id:
        sys.exit("%s has no workos_user_id - run precreate_workos.py first" % a.email)
    print("user: uuid=%s  workos_user_id=%s  tier=%s" % (u.id, u.workos_user_id, u.tier))

    # 1) set the password directly - no hosted page, no redirect
    try:
        wc.user_management.update_user(
            id=u.workos_user_id,
            password=PasswordPlaintext(password=a.password),
        )
        print("PASSWORD SET ok  (password = %s)" % a.password)
    except Exception as e:
        print("PASSWORD SET FAILED -> %s: %s" % (type(e).__name__, str(e)[:400]))
        sys.exit(1)

    # 2) prove email/password auth works in this environment
    try:
        wc.user_management.authenticate_with_password(email=a.email, password=a.password)
        print("AUTH OK - email/password authentication WORKS in this WorkOS env")
    except Exception as e:
        print("AUTH FAILED -> %s: %s" % (type(e).__name__, str(e)[:400]))
        print("  ^ THIS is the real blocker (e.g. email/password auth not enabled in the env)")
        sys.exit(2)


if __name__ == "__main__":
    main()
