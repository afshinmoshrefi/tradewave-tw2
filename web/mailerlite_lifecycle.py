"""Durable MailerLite lifecycle routing for TradeWave.

Access LEVEL groups describe what a subscriber can use. LIFECYCLE groups are
mutually-exclusive automation triggers:

* trial_started
* trial_ended_explorer
* winback_explorer

HTTP writes never run in the signup or Stripe request transaction. Those paths
insert an outbox row in the same database transaction as the user change. This
worker claims due rows, derives the desired lifecycle state from the CURRENT
User row, reconciles MailerLite, verifies membership, and retries failures.

The storage IDs ``reconcile`` and ``clear_paid`` are permanent. Do not rename
them; add a new value and migration if the state machine grows.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_, text
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "web"), "/home/flask", "/home/flask/web"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config  # noqa: E402
from email_utils import (  # noqa: E402
    clear_mailerlite_level_groups,
    mailerlite_unsubscribe,
    sync_mailerlite_level_group,
    sync_mailerlite_lifecycle_groups,
)
from models import (  # noqa: E402
    EmailOptout,
    MailerLiteLifecycleEvent,
    User,
    engine,
)


log = logging.getLogger("tw2.web.mailerlite_lifecycle")

EVENT_RECONCILE = "reconcile"
EVENT_CLEAR_PAID = "clear_paid"
ACTIVE_PAID_STATUSES = {"active", "trialing", "past_due"}
CHURNED_SUBSCRIPTION_STATUSES = {"canceled", "unpaid"}
LIFECYCLE_STATES = {
    "trial_started",
    "trial_ended_explorer",
    "winback_explorer",
}
ADVISORY_LOCK_ID = 740_219_613
CLAIM_TIMEOUT = timedelta(minutes=10)
TRIAL_START_MAX_AGE = timedelta(hours=24)
RETRY_DELAYS_SECONDS = (60, 300, 1800, 7200, 43200)
# MailerLite's account-wide API ceiling is 120 requests/minute. A normal job
# needs roughly five or six verified reads/writes across lifecycle and access
# groups, so 15 leaves headroom for retries and other account integrations.
DEFAULT_BATCH_LIMIT = 15


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def enqueue_mailerlite_reconcile(session, user: User, source_key: str, *,
                                 event_type: str = EVENT_RECONCILE,
                                 available_at: datetime | None = None,
                                 payload: dict | None = None):
    """Insert one idempotent outbox row using the caller's transaction.

    Callers must already hold the User row lock for mutable billing paths. The
    globally unique dedupe key makes webhook retries and page refreshes harmless.
    """
    if event_type not in (EVENT_RECONCILE, EVENT_CLEAR_PAID):
        raise ValueError(f"unsupported MailerLite event type: {event_type}")
    existing = (
        session.query(MailerLiteLifecycleEvent)
        .filter_by(dedupe_key=source_key)
        .first()
    )
    if existing is not None:
        return existing
    row = MailerLiteLifecycleEvent(
        user_id=user.id,
        event_type=event_type,
        dedupe_key=source_key,
        available_at=_utc(available_at) or datetime.now(timezone.utc),
        payload=payload or {},
    )
    session.add(row)
    return row


def enqueue_signup_lifecycle(session, user: User, *, name: str | None = None):
    """Queue the immediate trial journey and its day-7 state reconciliation."""
    if user.id is None:
        session.flush()
    payload = {
        "lifecycle_intent": "trial_started",
        "level_tier": "explorer",
        "name": name or None,
    }
    immediate = enqueue_mailerlite_reconcile(
        session,
        user,
        f"signup:{user.id}",
        payload=payload,
    )
    expiry = None
    if user.reverse_trial_ends_at is not None:
        cutoff = _utc(user.reverse_trial_ends_at)
        expiry = enqueue_mailerlite_reconcile(
            session,
            user,
            f"reverse-trial-end:{user.id}:{cutoff.isoformat()}",
            available_at=cutoff,
            payload={"level_tier": "explorer"},
        )
    return immediate, expiry


def derive_lifecycle_state(user: User, now: datetime | None = None) -> str | None:
    """Derive the one valid lifecycle trigger from current durable user state."""
    now = _utc(now) or datetime.now(timezone.utc)
    tier = (user.tier or "explorer").strip().lower()
    sub_status = (user.stripe_subscription_status or "").strip().lower()

    # A paid tier, or a still-live subscription whose tier update is merely
    # crossing another worker, must receive no free/churn lifecycle email.
    if tier not in ("explorer", "canceled") or sub_status in ACTIVE_PAID_STATUSES:
        return None

    # Subscription identity is durable paid-history. It takes precedence over
    # reverse_trial_ends_at so a subscriber who pays and cancels during their
    # first seven days can never re-enter the first-time trial journey.
    if (
        sub_status in CHURNED_SUBSCRIPTION_STATUSES
        or (user.stripe_subscription_id and not sub_status)
    ):
        return "winback_explorer"

    trial_ends = _utc(user.reverse_trial_ends_at)
    if trial_ends is None:
        return None
    if trial_ends > now:
        return "trial_started"
    return "trial_ended_explorer"


def _successful(result: str) -> bool:
    return not (
        not result
        or result.startswith("error:")
        or result in {
            "skip:no-api-key",
            "skip:not-configured",
            "skip:writes-disabled",
            "skip:no-mappable-group",
        }
    )


def _latest_level_target(session, user: User):
    """Return the newest still-relevant level target recorded for this user."""
    tier = (user.tier or "explorer").strip().lower()
    if tier in ("explorer", "canceled"):
        return "explorer", None
    rows = (
        session.query(MailerLiteLifecycleEvent)
        .filter_by(user_id=user.id)
        .order_by(MailerLiteLifecycleEvent.id.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        payload = row.payload or {}
        if payload.get("level_tier") != tier:
            continue
        period = payload.get("level_period")
        if period in ("monthly", "yearly"):
            return tier, period
    return None, None


def _claim_next(session, now: datetime):
    stale_before = now - CLAIM_TIMEOUT
    row = (
        session.query(MailerLiteLifecycleEvent)
        .filter(
            or_(
                (
                    MailerLiteLifecycleEvent.status.in_(("pending", "failed"))
                    & (MailerLiteLifecycleEvent.available_at <= now)
                ),
                (
                    (MailerLiteLifecycleEvent.status == "processing")
                    & (MailerLiteLifecycleEvent.claimed_at < stale_before)
                ),
            )
        )
        .order_by(MailerLiteLifecycleEvent.available_at,
                  MailerLiteLifecycleEvent.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        return None
    row.status = "processing"
    row.claimed_at = now
    row.attempts = (row.attempts or 0) + 1
    row.last_error = None
    session.commit()
    return row.id


def _mark(session_factory, event_id: int, status: str, *, error: str = None):
    session = session_factory()
    try:
        row = session.query(MailerLiteLifecycleEvent).filter_by(id=event_id).first()
        if row is None:
            return
        now = datetime.now(timezone.utc)
        row.status = status
        row.last_error = (error or "")[:500] or None
        if status in ("completed", "suppressed"):
            row.processed_at = now
        elif status == "failed":
            delay_index = min(max((row.attempts or 1) - 1, 0),
                              len(RETRY_DELAYS_SECONDS) - 1)
            row.available_at = now + timedelta(
                seconds=RETRY_DELAYS_SECONDS[delay_index],
            )
        session.commit()
    finally:
        session.close()


def _is_locally_opted_out(session, email: str) -> bool:
    return (
        session.query(EmailOptout)
        .filter(EmailOptout.email == (email or "").strip().lower())
        .first()
        is not None
    )


def _desired_for_event(event_type: str, user: User,
                       opted_out: bool,
                       now: datetime | None = None) -> str | None:
    if opted_out:
        return None
    current = derive_lifecycle_state(user, now)
    # A verified Checkout clear may arrive before subscription.created and
    # therefore before the User row reflects paid state. It may suppress only
    # the still-current Day-0 trial journey. A delayed clear must never erase a
    # newer post-trial or winback state.
    if event_type == EVENT_CLEAR_PAID and current == "trial_started":
        return None
    return current


def _is_stale_trial_start(row: MailerLiteLifecycleEvent,
                          now: datetime | None = None) -> bool:
    """Use immutable creation time, not retry-mutated ``available_at``."""
    now = _utc(now) or datetime.now(timezone.utc)
    payload = row.payload or {}
    created_at = _utc(row.created_at) or _utc(row.available_at)
    return bool(
        payload.get("lifecycle_intent") == "trial_started"
        and created_at is not None
        and now - created_at > TRIAL_START_MAX_AGE
    )


def _desired_for_row(row: MailerLiteLifecycleEvent, user: User,
                     opted_out: bool,
                     now: datetime | None = None) -> tuple[str | None, bool]:
    """Return the runtime decision and whether the Day-0 age guard applied."""
    now = _utc(now) or datetime.now(timezone.utc)
    current = _desired_for_event(row.event_type, user, opted_out, now)
    stale_trial_start = _is_stale_trial_start(row, now)
    if stale_trial_start and current == "trial_started":
        current = None
    return current, stale_trial_start


def _suppress_mailerlite_address(email: str):
    """Remove all managed groups and force one address unsubscribed."""
    lifecycle = sync_mailerlite_lifecycle_groups(
        email, None, create_if_missing=False,
    )
    if not _successful(lifecycle):
        return False, f"lifecycle:{lifecycle}"
    level = clear_mailerlite_level_groups(email)
    if not _successful(level):
        return False, f"level:{level}"
    if not mailerlite_unsubscribe(email):
        return False, "unsubscribe:failed"
    return True, f"lifecycle={lifecycle} level={level}"


def _process_one(session_factory, event_id: int):
    session = session_factory()
    try:
        row = session.query(MailerLiteLifecycleEvent).filter_by(id=event_id).first()
        if row is None:
            return "suppressed", "missing-outbox-row"
        user = session.query(User).filter_by(id=row.user_id).first()
        if user is None:
            return "suppressed", "missing-user"

        payload = row.payload or {}
        event_type = row.event_type
        now = datetime.now(timezone.utc)
        stale_trial_start = _is_stale_trial_start(row, now)

        old_email = (payload.get("remove_email") or "").strip().lower()
        current_email = (user.email or "").strip().lower()
        if old_email and old_email != current_email:
            new_owner = (
                session.query(User)
                .filter(
                    User.id != user.id,
                    func.lower(User.email) == old_email,
                )
                .first()
            )
            if new_owner is None:
                cleaned, detail = _suppress_mailerlite_address(old_email)
                if not cleaned:
                    return "failed", f"old-email:{detail}"
            else:
                log.info(
                    "Skipping old MailerLite address cleanup because it now "
                    "belongs to user=%s email=%s",
                    new_owner.id, old_email,
                )

        opted_out = _is_locally_opted_out(session, user.email)
        if opted_out:
            cleaned, detail = _suppress_mailerlite_address(user.email)
            if not cleaned:
                return "failed", f"local-optout:{detail}"
            return "suppressed", f"local-optout {detail}"

        def desired_now(current_user, is_opted_out):
            current, _stale = _desired_for_row(
                row, current_user, is_opted_out,
            )
            return current

        desired = desired_now(user, opted_out)
        lifecycle_result = sync_mailerlite_lifecycle_groups(
            user.email,
            desired,
            name=payload.get("name"),
            create_if_missing=desired is not None,
        )
        if not _successful(lifecycle_result):
            return "failed", f"lifecycle:{lifecycle_result}"

        # Re-read suppression and billing state after the first external call.
        # Postgres READ COMMITTED plus the central email_utils check makes an
        # unsubscribe that raced this worker converge before completion.
        session.expire_all()
        user = session.query(User).filter_by(id=row.user_id).first()
        if user is None:
            return "suppressed", "missing-user-after-lifecycle"
        opted_out = _is_locally_opted_out(session, user.email)
        if opted_out:
            cleaned, detail = _suppress_mailerlite_address(user.email)
            if not cleaned:
                return "failed", f"post-lifecycle-optout:{detail}"
            return "suppressed", f"post-lifecycle-optout {detail}"

        current_desired = desired_now(user, opted_out)
        if current_desired != desired:
            raced_result = sync_mailerlite_lifecycle_groups(
                user.email,
                current_desired,
                create_if_missing=current_desired is not None,
            )
            if not _successful(raced_result):
                return "failed", f"post-lifecycle-state:{raced_result}"
            lifecycle_result = raced_result
            desired = current_desired

        # Access groups remain segmentation only. Reconcile them after the
        # lifecycle transition. A clear-only Checkout race must not write an
        # Explorer access group before the subscription event supplies a tier.
        level_result = "skip:not-needed"
        level_target = (None, None)
        if not (event_type == EVENT_CLEAR_PAID and desired is None):
            level_tier, level_period = _latest_level_target(session, user)
            level_target = (level_tier, level_period)
            if level_tier:
                level_result = sync_mailerlite_level_group(
                    user.email, level_tier, level_period, new_user=False,
                )
                if not _successful(level_result):
                    return "failed", f"level:{level_result}"

        # One final convergence pass covers a billing or opt-out commit that
        # raced the access-group HTTP call.
        session.expire_all()
        user = session.query(User).filter_by(id=row.user_id).first()
        if user is None:
            return "suppressed", "missing-user-after-level"
        opted_out = _is_locally_opted_out(session, user.email)
        if opted_out:
            cleaned, detail = _suppress_mailerlite_address(user.email)
            if not cleaned:
                return "failed", f"post-level-optout:{detail}"
            return "suppressed", f"post-level-optout {detail}"

        final_desired = desired_now(user, opted_out)
        if final_desired != desired:
            raced_result = sync_mailerlite_lifecycle_groups(
                user.email,
                final_desired,
                create_if_missing=final_desired is not None,
            )
            if not _successful(raced_result):
                return "failed", f"postcheck:{raced_result}"
            lifecycle_result = raced_result
            desired = final_desired

        if not (event_type == EVENT_CLEAR_PAID and desired is None):
            final_level_target = _latest_level_target(session, user)
            if final_level_target != level_target and final_level_target[0]:
                level_result = sync_mailerlite_level_group(
                    user.email, final_level_target[0], final_level_target[1],
                    new_user=False,
                )
                if not _successful(level_result):
                    return "failed", f"postcheck-level:{level_result}"

        final_status = (
            "suppressed"
            if stale_trial_start and desired is None else "completed"
        )
        return final_status, (
            f"state={desired or 'none'} lifecycle={lifecycle_result} "
            f"level={level_result}"
            f"{' stale-trial-start' if stale_trial_start else ''}"
        )
    finally:
        session.close()


def process_due_jobs(limit: int = DEFAULT_BATCH_LIMIT, *, session_factory=None) -> dict:
    """Process one bounded batch. Returns status counts for logs/tests."""
    if not getattr(config, 'MAILERLITE_OUTBOUND_ENABLED', False):
        log.info("MailerLite lifecycle worker disabled by configuration")
        return {"disabled": 1}
    groups = getattr(config, 'MAILERLITE_LIFECYCLE_GROUPS', {}) or {}
    if any(not groups.get(state) for state in LIFECYCLE_STATES):
        log.error("MailerLite lifecycle worker disabled: lifecycle group configuration incomplete")
        return {"misconfigured": 1}

    factory = session_factory or sessionmaker(
        bind=engine, expire_on_commit=False, future=True,
    )
    lock_session = factory()
    counts = {"completed": 0, "suppressed": 0, "failed": 0}
    try:
        got_lock = bool(lock_session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": ADVISORY_LOCK_ID},
        ).scalar())
        if not got_lock:
            return {"locked": 1}

        for _ in range(max(0, limit)):
            claim_session = factory()
            try:
                event_id = _claim_next(claim_session, datetime.now(timezone.utc))
            finally:
                claim_session.close()
            if event_id is None:
                break
            try:
                status, detail = _process_one(factory, event_id)
            except Exception as exc:  # worker boundary: preserve retryability
                log.exception("MailerLite lifecycle event %s crashed", event_id)
                status, detail = "failed", f"exception:{type(exc).__name__}"
            _mark(factory, event_id, status, error=None if status == "completed" else detail)
            counts[status] += 1
            log.info("MailerLite lifecycle event=%s status=%s %s",
                     event_id, status, detail)
        return counts
    finally:
        try:
            lock_session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": ADVISORY_LOCK_ID},
            )
        except Exception:
            log.warning("Could not explicitly release MailerLite advisory lock", exc_info=True)
        lock_session.close()


def preview_due_jobs(limit: int = DEFAULT_BATCH_LIMIT, *, session_factory=None) -> list[dict]:
    """Read-only preview that never claims jobs or contacts MailerLite."""
    factory = session_factory or sessionmaker(
        bind=engine, expire_on_commit=False, future=True,
    )
    session = factory()
    try:
        now = datetime.now(timezone.utc)
        rows = (
            session.query(MailerLiteLifecycleEvent)
            .filter(
                MailerLiteLifecycleEvent.status.in_(("pending", "failed")),
                MailerLiteLifecycleEvent.available_at <= now,
            )
            .order_by(MailerLiteLifecycleEvent.available_at,
                      MailerLiteLifecycleEvent.id)
            .limit(max(0, limit))
            .all()
        )
        result = []
        for row in rows:
            user = session.query(User).filter_by(id=row.user_id).first()
            opted_out = bool(
                user and _is_locally_opted_out(session, user.email)
            )
            if user:
                desired, stale_trial_start = _desired_for_row(
                    row, user, opted_out, now,
                )
            else:
                desired, stale_trial_start = "missing-user", False
            result.append({
                "id": row.id,
                "event_type": row.event_type,
                "attempts": row.attempts,
                "desired_state": desired or "none",
                "stale_trial_start": stale_trial_start,
                "locally_opted_out": opted_out,
            })
        return result
    finally:
        session.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.dry_run:
        rows = preview_due_jobs(args.limit)
        print(f"due={len(rows)}")
        for row in rows:
            print(
                f"id={row['id']} type={row['event_type']} "
                f"attempts={row['attempts']} desired={row['desired_state']} "
                f"stale_day0={int(row['stale_trial_start'])} "
                f"opted_out={int(row['locally_opted_out'])}"
            )
        return 0
    counts = process_due_jobs(args.limit)
    print(" ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
