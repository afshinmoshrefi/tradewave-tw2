#!/usr/bin/env python3
"""Schedule only the post-trial reconciliation for already-active trials.

This intentionally does NOT enroll existing users midway through the day-0
trial-started automation and does NOT touch expired Explorer accounts. Run once
after the outbox migration, first without --apply.

  sudo -u flask /home/flask/venv/bin/python \
    /home/flask/ops/backfill_active_reverse_trial_lifecycle.py
  sudo -u flask /home/flask/venv/bin/python \
    /home/flask/ops/backfill_active_reverse_trial_lifecycle.py --apply
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "web"), "/home/flask", "/home/flask/web"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config  # noqa: E402
from mailerlite_lifecycle import (  # noqa: E402
    derive_lifecycle_state,
    enqueue_mailerlite_reconcile,
)
from models import MailerLiteLifecycleEvent, Session, User  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and config.MAILERLITE_OUTBOUND_ENABLED:
        print(
            "REFUSING --apply while MAILERLITE_OUTBOUND_ENABLED is true; "
            "set it to 0 and restart the web service before backfilling.",
            file=sys.stderr,
        )
        return 2
    now = datetime.now(timezone.utc)
    session = Session()
    try:
        candidates = (
            session.query(User)
            .filter(
                User.reverse_trial_ends_at > now,
            )
            .order_by(User.created_at, User.id)
            .all()
        )
        # Use the exact worker state machine so an abandoned/incomplete Checkout
        # does not omit a genuine first-time trial, while any payer or former
        # payer remains excluded.
        users = [
            user for user in candidates
            if derive_lifecycle_state(user, now) == "trial_started"
        ]
        new_count = 0
        existing_count = 0
        for user in users:
            cutoff = user.reverse_trial_ends_at
            key = f"reverse-trial-end:{user.id}:{cutoff.isoformat()}"
            exists = (
                session.query(MailerLiteLifecycleEvent)
                .filter_by(dedupe_key=key)
                .first()
                is not None
            )
            if exists:
                existing_count += 1
                continue
            new_count += 1
            if args.apply:
                enqueue_mailerlite_reconcile(
                    session,
                    user,
                    key,
                    available_at=cutoff,
                    payload={"level_tier": "explorer"},
                )
        if args.apply:
            session.commit()
        else:
            session.rollback()
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(
            f"mode={mode} active_trials={len(users)} "
            f"would_add={new_count} already_scheduled={existing_count}"
        )
        return 0
    finally:
        session.close()
        Session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
