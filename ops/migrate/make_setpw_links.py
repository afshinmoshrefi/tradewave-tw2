#!/usr/bin/env python3
"""
make_setpw_links.py - item 1C of the TW1 -> TW2 cutover.

Run on a TW2 WEB box AT cutover/send-time (the links EXPIRE). For each migrated
user that has a WorkOS identity (i.e. precreate_workos.py already ran), mint a
one-time set-password link and write {email, tier, set_password_url, expires_at}
to setpw_links.jsonl - the feed for the MailerLite "set your password" email.

  sudo -u flask /home/flask/venv/bin/python make_setpw_links.py --out-dir /tmp/mig
  ... --email someone@x.com    # just one (the one-user test)
  ... --limit 5

SENSITIVE OUTPUT: setpw_links.jsonl contains live one-time set-password URLs -
anyone with the file can set those users' passwords. Keep it flask-owned in /tmp,
upload to MailerLite, then SHRED it. The script prints only counts, never links.
Re-run anytime to regenerate fresh links (each call issues a new one-time token).
"""
import argparse
import json
import os
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
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--email", help="limit to one email")
    ap.add_argument("--limit", type=int, help="limit to the first N")
    a = ap.parse_args()

    key = getattr(config, "WORKOS_API_KEY", "") or ""
    cid = getattr(config, "WORKOS_CLIENT_ID", "") or ""
    if not (key and cid):
        sys.exit("WORKOS_API_KEY / WORKOS_CLIENT_ID not set (run on a TW2 web box with secrets)")
    from workos import WorkOSClient
    wc = WorkOSClient(api_key=key, client_id=cid)

    from models import Session, User
    s = Session()
    # Only users WITH a WorkOS identity (precreate ran) - reset_password needs the user to exist.
    q = s.query(User).filter(User.workos_user_id.isnot(None),
                             User.email.isnot(None), User.email != "")
    rows = [u for u in q.all() if not (u.roles and "service_account" in u.roles)]
    if a.email:
        em = a.email.strip().lower()
        rows = [u for u in rows if (u.email or "").lower() == em]
    if a.limit:
        rows = rows[:a.limit]

    os.makedirs(a.out_dir, exist_ok=True)
    out_path = os.path.join(a.out_dir, "setpw_links.jsonl")
    n = err = 0
    soonest = None
    with open(out_path, "w") as out:
        for i, u in enumerate(rows, 1):
            try:
                pr = wc.user_management.reset_password(email=u.email)
                out.write(json.dumps({
                    "email": u.email,
                    "tier": u.tier,
                    "set_password_url": pr.password_reset_url,
                    "expires_at": str(pr.expires_at),
                }) + "\n")
                n += 1
                if soonest is None or str(pr.expires_at) < soonest:
                    soonest = str(pr.expires_at)
            except Exception as e:
                err += 1
                print("  WARN %s: %s" % (u.email, str(e)[:140]), file=sys.stderr)
            if i % 50 == 0:
                print("  ...%d/%d" % (i, len(rows)), file=sys.stderr)

    print("links generated: %d  errors: %d  -> %s  (earliest expiry: %s)"
          % (n, err, out_path, soonest))
    print("SENSITIVE: that file holds live set-password URLs - upload to MailerLite then shred it.")


if __name__ == "__main__":
    main()
