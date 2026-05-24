#!/usr/bin/env python3
"""
precreate_workos.py - item 1B of the TW1 -> TW2 cutover.

Run on a TW2 WEB box (it has WORKOS_* + POSTGRES_DSN). For every migrated user
that has no WorkOS identity yet, create one (email, marked verified, NO password)
and write its workos_user_id back onto the Postgres row - so first login matches
by id, and "set your password" / "forgot password" / Google all work.

Idempotent: a re-run only looks at rows still missing workos_user_id, and if the
email already exists in WorkOS it links instead of erroring. DRY-RUN by default -
makes NO WorkOS writes until --apply (it only does read-only list_users to
preview). Run ahead of cutover; links (the expiring part) are step 1C.

  sudo -u flask -E /home/flask/venv/bin/python precreate_workos.py             # dry-run
  sudo -u flask -E /home/flask/venv/bin/python precreate_workos.py --apply     # create + link
  ... --email someone@x.com    # just one (used by the one-user test)
  ... --limit 5                # first N candidates (small batch)
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
    ap.add_argument("--apply", action="store_true", help="create + link (default: dry-run)")
    ap.add_argument("--email", help="limit to one email")
    ap.add_argument("--limit", type=int, help="limit to the first N candidates")
    a = ap.parse_args()

    key = getattr(config, "WORKOS_API_KEY", "") or ""
    cid = getattr(config, "WORKOS_CLIENT_ID", "") or ""
    if not (key and cid):
        sys.exit("WORKOS_API_KEY / WORKOS_CLIENT_ID not set (run on a TW2 web box with secrets)")
    from workos import WorkOSClient
    wc = WorkOSClient(api_key=key, client_id=cid)

    from models import Session, User
    s = Session()
    q = s.query(User).filter(User.workos_user_id.is_(None),
                             User.email.isnot(None), User.email != "")
    rows = [u for u in q.all() if not (u.roles and "service_account" in u.roles)]
    if a.email:
        em = a.email.strip().lower()
        rows = [u for u in rows if (u.email or "").lower() == em]
    if a.limit:
        rows = rows[:a.limit]

    created = linked = errs = 0
    for i, u in enumerate(rows, 1):
        email = u.email
        try:
            existing = wc.user_management.list_users(email=email).data
            if existing:                              # already in WorkOS -> just link
                if a.apply:
                    u.workos_user_id = existing[0].id
                    s.commit()
                linked += 1
            else:                                     # absent -> create (apply only)
                if a.apply:
                    wu = wc.user_management.create_user(email=email, email_verified=True)
                    u.workos_user_id = wu.id
                    s.commit()
                created += 1
        except Exception as e:
            s.rollback()
            errs += 1
            print("  WARN %s: %s" % (email, str(e)[:140]), file=sys.stderr)
        if i % 50 == 0:
            print("  ...%d/%d" % (i, len(rows)), file=sys.stderr)

    verb = "APPLIED" if a.apply else "DRY-RUN (no WorkOS writes)"
    print("%s  candidates=%d  %s=%d  already-in-workos=%d  errors=%d"
          % (verb, len(rows), "created" if a.apply else "would-create", created, linked, errs))


if __name__ == "__main__":
    main()
