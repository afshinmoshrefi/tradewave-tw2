"""Daily trial-expiry sweep.

Finds users whose admin-granted trial has lapsed and reverts them to
`explorer`. Only touches users WITHOUT a Stripe subscription — Stripe's
own webhooks (`customer.subscription.deleted` etc.) handle paid
subscribers, and we must not race with them.

Cron entry (web box):
  15 4 * * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/web/expire_trials.py >> /var/log/tradewave/expire_trials.log 2>&1

Idempotent — safe to run as often as you like.
"""
from __future__ import annotations

import logging
import sys
import datetime as dt

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

import config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from email_utils import sync_mailerlite_level_group  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s expire_trials: %(message)s",
)
log = logging.getLogger(__name__)


def main() -> int:
    dsn = config.POSTGRES_DSN
    if not dsn:
        log.error("POSTGRES_DSN not set")
        return 1

    engine = create_engine(dsn, future=True)
    now_utc = dt.datetime.now(dt.timezone.utc)

    expired = 0
    expired_emails = []  # synced to the explorer Mailerlite group after commit

    # One transaction per row keeps the lock window small and prevents a
    # single slow audit-log insert from holding rows for the whole batch.
    # FOR UPDATE inside the transaction gives us serial access against
    # the Stripe webhook path — re-check the IS NULL guard after the lock
    # so a webhook that wrote stripe_subscription_id mid-flight aborts us.
    with engine.connect() as conn:
        ids = conn.execute(
            text(
                """
                SELECT id FROM users
                WHERE trial_ends_at IS NOT NULL
                  AND trial_ends_at < :now
                  AND tier IN ('analyst', 'strategist')
                  AND stripe_subscription_id IS NULL
                """
            ),
            {"now": now_utc},
        ).scalars().all()

    if not ids:
        log.info("nothing to expire (checked at %s)", now_utc.isoformat())
        return 0

    for uid in ids:
        with engine.begin() as txn:
            row = txn.execute(
                text(
                    """
                    SELECT id, email, tier, trial_ends_at, stripe_subscription_id
                    FROM users
                    WHERE id = :id
                    FOR UPDATE
                    """
                ),
                {"id": uid},
            ).first()
            if row is None:
                continue
            # Re-check the guards under the lock — a webhook may have
            # written stripe_subscription_id between the SELECT above
            # and this transaction.
            if (
                row.stripe_subscription_id is not None
                or row.tier not in ("analyst", "strategist")
                or row.trial_ends_at is None
                or row.trial_ends_at >= now_utc
            ):
                log.info("skip user_id=%s — guard re-check failed (raced with webhook?)", uid)
                continue
            log.info(
                "expiring user_id=%s email=%s tier=%s trial_ended=%s",
                row.id, row.email, row.tier, row.trial_ends_at.isoformat(),
            )
            txn.execute(
                text(
                    """
                    UPDATE users
                    SET tier = 'explorer',
                        trial_ends_at = NULL,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": row.id},
            )
            import json as _json
            txn.execute(
                text(
                    """
                    INSERT INTO audit_log (actor_user_id, actor_label, action, target_user_id, details)
                    VALUES (NULL, 'system:expire_trials', :action, :target, CAST(:details AS jsonb))
                    """
                ),
                {
                    "action": "trial_expired_revert_to_explorer",
                    "target": row.id,
                    "details": _json.dumps({
                        "from_tier": row.tier,
                        "ended_at": row.trial_ends_at.isoformat(),
                    }),
                },
            )
            expired += 1
            expired_emails.append(row.email)

    # Mailerlite level-group sync (TW1/UMP parity) - move reverted users to the
    # explorer group. After commit, best-effort; never raises.
    for em in expired_emails:
        sync_mailerlite_level_group(em, "explorer", None, new_user=False)

    log.info("expired %d user(s)", expired)
    return 0


if __name__ == "__main__":
    sys.exit(main())
