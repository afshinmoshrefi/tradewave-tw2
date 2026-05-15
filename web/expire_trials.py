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

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, email, tier, trial_ends_at
                FROM users
                WHERE trial_ends_at IS NOT NULL
                  AND trial_ends_at < :now
                  AND tier IN ('analyst', 'strategist')
                  AND stripe_subscription_id IS NULL
                """
            ),
            {"now": now_utc},
        ).all()

        if not rows:
            log.info("nothing to expire (checked at %s)", now_utc.isoformat())
            return 0

        for r in rows:
            log.info(
                "expiring user_id=%s email=%s tier=%s trial_ended=%s",
                r.id, r.email, r.tier, r.trial_ends_at.isoformat(),
            )
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET tier = 'explorer',
                        trial_ends_at = NULL,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": r.id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log (actor_user_id, actor_label, action, target_user_id, details)
                    VALUES (NULL, 'system:expire_trials', :action, :target, :details)
                    """
                ),
                {
                    "action": "trial_expired_revert_to_explorer",
                    "target": r.id,
                    "details": '{"from_tier":"' + r.tier + '","ended_at":"' + r.trial_ends_at.isoformat() + '"}',
                },
            )

    log.info("expired %d user(s)", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
