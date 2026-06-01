#!/usr/bin/env python3
"""
freshuser_diag.py - create a BRAND-NEW disposable WorkOS user with a known password,
to test the hosted AuthKit login independent of any migrated user (Codex's test #1).

Logic: if this fresh user CAN sign in on the hosted page but a migrated user can't, the
migrated user's WorkOS object/credential is the problem (recreate just that user). If the
fresh user ALSO can't sign in, the environment/application itself is bad (recreate the env).

It sets the password the same way we set the migrated user's (create_user + update_user),
so it's an apples-to-apples test.

  sudo -u flask /home/flask/venv/bin/python ops/migrate/freshuser_diag.py               # create + show creds
  ... --email someone+x@gmail.com --password 'Strong-Pass-1!'   # override defaults
  ... --delete                                                  # remove the test user afterward
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
    ap.add_argument("--email", default="afshinmoshrefi+tw2freshtest@gmail.com")
    ap.add_argument("--password", default="Cobalt-River-Salmon-88!")
    ap.add_argument("--delete", action="store_true", help="delete the test user instead of creating")
    ap.add_argument("--reset-link", action="store_true",
                    help="print a hosted password-reset URL for --email (set the pw via AuthKit's own page)")
    a = ap.parse_args()

    from workos import WorkOSClient
    from workos.user_management._resource import PasswordPlaintext
    wc = WorkOSClient(api_key=config.WORKOS_API_KEY, client_id=config.WORKOS_CLIENT_ID)
    um = wc.user_management

    if a.reset_link:
        pr = um.reset_password(email=a.email)
        print("HOSTED RESET URL for %s" % a.email)
        print("Open this in a browser and set a NEW password ON THAT PAGE (it may 404 on the")
        print("redirect afterward - ignore that; the password is set before the redirect):")
        print("  %s" % pr.password_reset_url)
        print("  (expires %s)" % pr.expires_at)
        return

    existing = um.list_users(email=a.email).data

    if a.delete:
        for u in existing:
            um.delete_user(u.id)
            print("deleted %s" % u.id)
        if not existing:
            print("no such user to delete")
        return

    if existing:
        u = existing[0]
        print("already exists: %s" % u.id)
    else:
        u = um.create_user(email=a.email, email_verified=True)
        print("created fresh user: %s" % u.id)

    um.update_user(id=u.id, password=PasswordPlaintext(password=a.password), email_verified=True)
    print("password set + email_verified=True")

    um.authenticate_with_password(email=a.email, password=a.password)
    print("API AUTH OK (password valid server-side)")

    print()
    print(">>> NOW TEST THE HOSTED LOGIN at https://tw2-prod.trxstat.com  with:")
    print("      email:    %s" % a.email)
    print("      password: %s" % a.password)
    print(">>> If this fresh user logs in but hotmail doesn't -> hotmail's WorkOS user is bad.")
    print(">>> If this fresh user ALSO fails -> the environment/app is bad (recreate env).")
    print("    (clean up after with:  ... freshuser_diag.py --delete )")


if __name__ == "__main__":
    main()
