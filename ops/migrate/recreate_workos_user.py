#!/usr/bin/env python3
"""
recreate_workos_user.py - give a migrated user a FRESH WorkOS user object.

Use when a migrated user's existing WorkOS user is in a bad state (e.g. churned during
setup) and the hosted login rejects it even after a hosted password reset, while a
brand-new user works. Deletes the old WorkOS user, creates a clean one, relinks the
Postgres row, and prints a hosted reset URL to set the password.

  sudo -u flask -E /home/flask/venv/bin/python ops/migrate/recreate_workos_user.py --email afshinmoshrefi@hotmail.com
"""
import argparse
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")
try:
    from db_admin import _maybe_load_secrets_env
    _maybe_load_secrets_env()
except Exception:
    pass

import config  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    a = ap.parse_args()

    from sqlalchemy import func
    from workos import WorkOSClient
    from models import Session, User
    wc = WorkOSClient(api_key=config.WORKOS_API_KEY, client_id=config.WORKOS_CLIENT_ID)
    um = wc.user_management
    em = a.email.strip().lower()

    # 1) delete the existing (suspect) WorkOS user(s) for this email
    for u in um.list_users(email=em).data:
        um.delete_user(user_id=u.id)
        print("deleted old WorkOS user %s" % u.id)

    # 2) create a fresh, clean WorkOS user
    nu = um.create_user(email=em, email_verified=True)
    print("created fresh WorkOS user %s" % nu.id)

    # 3) relink the Postgres row to the new WorkOS id
    s = Session()
    pu = s.query(User).filter(func.lower(User.email) == em).first()
    if pu:
        pu.workos_user_id = nu.id
        s.commit()
        print("relinked Postgres user %s (tier=%s) -> %s" % (pu.id, pu.tier, nu.id))
    else:
        print("WARNING: no Postgres user row for %s (WorkOS user created anyway)" % em)

    # 4) hosted reset URL to set the password via WorkOS's own flow
    pr = um.reset_password(email=em)
    print()
    print("Open this hosted reset URL and set a NEW password ON THAT PAGE")
    print("(ignore any tradewave.ai 404 after submitting - the password is set first):")
    print("  %s" % pr.password_reset_url)
    print()
    print("Then do a FRESH login at https://tw2-prod.trxstat.com (start there, incognito)")
    print("with  %s  + that new password." % em)


if __name__ == "__main__":
    main()
