#!/usr/bin/env python3
"""
grant_reverse_trial.py - one-off grant of the 7-day REVERSE TRIAL to EXISTING
free users ("we unlocked everything for you for 7 days" founder-email moment).

Sets users.reverse_trial_ends_at = now + N days for every user with
tier='explorer' and NO ACTIVE reverse trial (column NULL or already lapsed).
The tier column is NEVER touched: the elevation to the full Strategist
experience happens at token-mint time (web/app.py effective_tier), so expiry
is implicit at the next mint after the deadline - NO cron is needed.
web/expire_trials.py is unrelated and unaffected: it sweeps the SEPARATE
admin-granted trial_ends_at column and only touches tier IN ('analyst',
'strategist'), so it can never see (or revert) a reverse-trial explorer.

New signups get the grant automatically in lazy_create_user; this script is
only for the back-catalog of explorers created before the feature shipped.

Run on a TW2 box with secrets (needs POSTGRES_DSN). DRY-RUN by default -
prints the planned grant per user and writes NOTHING. Add --apply to execute.

  sudo -u flask /home/flask/venv/bin/python /home/flask/ops/grant_reverse_trial.py            # dry-run
  sudo -u flask /home/flask/venv/bin/python /home/flask/ops/grant_reverse_trial.py --apply    # execute
  ... --days 14                # longer grant (default 7)
  ... --email someone@x.com    # just one (test)
"""
import argparse
import datetime as dt
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")
from db_admin import _maybe_load_secrets_env  # noqa: E402
_maybe_load_secrets_env()

from sqlalchemy import or_  # noqa: E402
from models import Session, User, write_audit  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--days", type=int, default=7, help="trial length in days (default 7)")
    ap.add_argument("--email", help="limit to one email (test)")
    ap.add_argument("--regrant", action="store_true",
                    help="also re-grant users whose previous reverse trial already "
                         "lapsed (default: only users never granted one)")
    a = ap.parse_args()

    if a.days <= 0:
        sys.exit("--days must be positive")

    now = dt.datetime.now(dt.timezone.utc)
    ends_at = now + dt.timedelta(days=a.days)

    s = Session()
    try:
        q = (
            s.query(User)
            .filter(User.tier == "explorer")
            .filter(or_(User.reverse_trial_ends_at.is_(None),
                        User.reverse_trial_ends_at <= now)
                    if a.regrant else User.reverse_trial_ends_at.is_(None))
            # Non-human rows (tara-service@, mcp-service@, ...) sit at tier
            # 'explorer' but must never carry a trial. The elevation only
            # happens at web token mint, which requires a WorkOS sign-in -
            # so a row with no workos_user_id can never use the grant; service
            # principals have none. api_key_hash (service-account-only auth
            # material, models.py) is excluded as belt-and-suspenders.
            .filter(User.workos_user_id.isnot(None))
            .filter(User.api_key_hash.is_(None))
            .order_by(User.created_at)
        )
        if a.email:
            q = q.filter(User.email == a.email.strip().lower())
        users = [u for u in q.all() if "service_account" not in (u.roles or [])]

        granted = 0
        for u in users:
            prev = u.reverse_trial_ends_at.isoformat() if u.reverse_trial_ends_at else None
            print("%s %-40s prev=%s -> ends_at=%s"
                  % ("GRANT" if a.apply else "would-grant", u.email, prev, ends_at.isoformat()))
            if a.apply:
                u.reverse_trial_ends_at = ends_at
                granted += 1
        if a.apply:
            s.commit()
            for u in users:
                write_audit(
                    actor_label="ops:grant_reverse_trial",
                    action="reverse_trial_granted",
                    target_user_id=u.id,
                    details={"days": a.days, "ends_at": ends_at.isoformat()},
                )
            print("granted %d user(s) a %d-day reverse trial (ends %s)"
                  % (granted, a.days, ends_at.isoformat()))
        else:
            print("dry-run: %d user(s) would be granted a %d-day reverse trial "
                  "(add --apply to execute)" % (len(users), a.days))
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
