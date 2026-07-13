"""Lifecycle-state truth table and durable enqueue semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def user(**overrides):
    values = {
        "tier": "explorer",
        "stripe_subscription_id": None,
        "stripe_subscription_status": None,
        "reverse_trial_ends_at": NOW + timedelta(days=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.unit
def test_first_time_trial_is_trial_started():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(user(), NOW) == "trial_started"


@pytest.mark.unit
def test_unpaid_trial_at_cutoff_is_trial_ended_explorer():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(reverse_trial_ends_at=NOW), NOW,
    ) == "trial_ended_explorer"


@pytest.mark.unit
def test_paid_tier_has_no_lifecycle_trigger():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(tier="analyst", stripe_subscription_id="sub_paid",
             stripe_subscription_status="active"), NOW,
    ) is None


@pytest.mark.unit
def test_active_subscription_race_clears_free_journeys():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(tier="explorer", stripe_subscription_id="sub_paid",
             stripe_subscription_status="trialing"), NOW,
    ) is None


@pytest.mark.unit
def test_former_payer_never_reenters_first_time_trial():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(stripe_subscription_id="sub_old",
             stripe_subscription_status="canceled",
             reverse_trial_ends_at=NOW + timedelta(days=3)), NOW,
    ) == "winback_explorer"


@pytest.mark.unit
def test_incomplete_checkout_does_not_become_winback():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(stripe_subscription_id="sub_incomplete",
             stripe_subscription_status="incomplete"), NOW,
    ) == "trial_started"


@pytest.mark.unit
def test_delayed_clear_paid_preserves_newer_free_journey():
    from mailerlite_lifecycle import (
        EVENT_CLEAR_PAID,
        _desired_for_event,
    )
    ended = user(reverse_trial_ends_at=NOW - timedelta(days=1))
    churned = user(
        stripe_subscription_id="sub_old",
        stripe_subscription_status="canceled",
    )
    assert _desired_for_event(EVENT_CLEAR_PAID, ended, False) == (
        "trial_ended_explorer"
    )
    assert _desired_for_event(EVENT_CLEAR_PAID, churned, False) == (
        "winback_explorer"
    )
    assert _desired_for_event(EVENT_CLEAR_PAID, user(), False) is None


@pytest.mark.unit
def test_stale_day0_uses_immutable_created_at_after_retry_reschedule():
    from mailerlite_lifecycle import (
        EVENT_RECONCILE,
        _desired_for_row,
    )
    row = SimpleNamespace(
        event_type=EVENT_RECONCILE,
        payload={"lifecycle_intent": "trial_started"},
        created_at=NOW - timedelta(hours=25),
        # A failed retry moves available_at forward; it must not reset the age.
        available_at=NOW + timedelta(hours=1),
    )
    desired, stale = _desired_for_row(row, user(), False, NOW)
    assert stale is True
    assert desired is None


@pytest.mark.unit
def test_preview_decision_for_delayed_clear_preserves_newer_state():
    from mailerlite_lifecycle import EVENT_CLEAR_PAID, _desired_for_row
    row = SimpleNamespace(
        event_type=EVENT_CLEAR_PAID,
        payload={},
        created_at=NOW - timedelta(days=2),
        available_at=NOW - timedelta(days=2),
    )
    ended = user(reverse_trial_ends_at=NOW - timedelta(days=1))
    desired, stale = _desired_for_row(row, ended, False, NOW)
    assert stale is False
    assert desired == "trial_ended_explorer"


@pytest.mark.unit
def test_plain_legacy_explorer_gets_no_automatic_backfill():
    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(
        user(reverse_trial_ends_at=None), NOW,
    ) is None


@pytest.mark.db
def test_signup_enqueue_is_idempotent_and_schedules_expiry(
    db_session, _models_module, make_user,
):
    from mailerlite_lifecycle import enqueue_signup_lifecycle

    cutoff = datetime.now(timezone.utc) + timedelta(days=7)
    created = make_user(
        email="lifecycle-enqueue@example.com",
        reverse_trial_ends_at=cutoff,
    )
    enqueue_signup_lifecycle(db_session, created, name="Lifecycle Test")
    enqueue_signup_lifecycle(db_session, created, name="Lifecycle Test")
    db_session.commit()

    rows = (
        db_session.query(_models_module.MailerLiteLifecycleEvent)
        .filter_by(user_id=created.id)
        .order_by(_models_module.MailerLiteLifecycleEvent.available_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].dedupe_key == f"signup:{created.id}"
    assert rows[0].payload["name"] == "Lifecycle Test"
    assert rows[1].available_at == cutoff


@pytest.mark.db
def test_local_unsubscribe_durably_queues_mailerlite_suppression(
    db_session, _models_module, make_user,
):
    import app as app_module

    app_module.DBSession = _models_module.Session
    created = make_user(email="durable-optout@example.com")

    app_module._suppress("  DURABLE-OPTOUT@example.com ", "link")
    # A duplicate Gmail one-click notification must not create another job.
    app_module._suppress("durable-optout@example.com", "one_click")

    db_session.expire_all()
    assert db_session.get(
        _models_module.EmailOptout, "durable-optout@example.com",
    ) is not None
    rows = (
        db_session.query(_models_module.MailerLiteLifecycleEvent)
        .filter_by(user_id=created.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].dedupe_key.startswith(f"email-optout:{created.id}:")
    assert rows[0].event_type == "reconcile"
    assert rows[0].status == "pending"
    assert rows[0].payload == {"remove_email": "durable-optout@example.com"}
