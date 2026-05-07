"""
Coverage for the StripeEvent dedup path in /home/flask/web/app.py
`webhook_stripe()`.

The most-likely-to-silently-break invariant is "the same Stripe event
processed twice does not double-update the DB". These tests:

  1. Insert a StripeEvent row, attempt a duplicate insert by the same
     stripe_event_id, and confirm the unique constraint catches it.
  2. Confirm the `_json_safe` helper survives Decimals (the bug that
     used to drop entire StripeEvent rows and cause Stripe retry storms).
  3. Confirm the helper round-trips arbitrary nested dict/list shapes
     untouched.

We do not exercise the full Flask request/response path here — that
needs more mocking than is justified for a first pass. See README for
deferred coverage.
"""
from __future__ import annotations

import decimal
import json

import pytest
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.db


# ---------------------------------------------------------------------
# StripeEvent unique constraint
# ---------------------------------------------------------------------

class TestStripeEventUniqueness:
    def test_duplicate_stripe_event_id_blocked(self, db_session, _models_module):
        """The stripe_events.stripe_event_id UNIQUE constraint must reject
        a duplicate insert; this is the *primary* idempotency mechanism
        when SELECT-then-INSERT loses the race."""
        StripeEvent = _models_module.StripeEvent

        ev1 = StripeEvent(
            stripe_event_id="evt_dup_test_1",
            event_type="customer.subscription.updated",
            payload={"id": "evt_dup_test_1", "type": "customer.subscription.updated"},
        )
        db_session.add(ev1)
        db_session.commit()

        ev2 = StripeEvent(
            stripe_event_id="evt_dup_test_1",  # same id
            event_type="customer.subscription.updated",
            payload={"id": "evt_dup_test_1", "type": "customer.subscription.updated"},
        )
        db_session.add(ev2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

        # The first insert is still there, only one row total for this id.
        rows = db_session.query(StripeEvent).filter_by(stripe_event_id="evt_dup_test_1").all()
        assert len(rows) == 1

    def test_select_then_insert_idempotency_pattern(self, db_session, _models_module):
        """Mirror the exact pattern in webhook_stripe: SELECT first, only
        INSERT if not found. The 'duplicate' branch should short-circuit."""
        StripeEvent = _models_module.StripeEvent

        ev = StripeEvent(
            stripe_event_id="evt_idem_test_1",
            event_type="checkout.session.completed",
            payload={"id": "evt_idem_test_1"},
        )
        db_session.add(ev)
        db_session.commit()

        # Now simulate the second request seeing the same event id
        existing = db_session.query(StripeEvent).filter_by(
            stripe_event_id="evt_idem_test_1"
        ).first()
        assert existing is not None, "first row must be visible to duplicate request"
        # In the real handler this is the branch that returns
        # {"received": True, "duplicate": True} without touching the user row.

    def test_different_event_ids_coexist(self, db_session, _models_module):
        """Sanity: different event ids are fine."""
        StripeEvent = _models_module.StripeEvent
        for n in range(3):
            db_session.add(StripeEvent(
                stripe_event_id=f"evt_distinct_{n}",
                event_type="invoice.payment_succeeded",
                payload={"id": f"evt_distinct_{n}"},
            ))
        db_session.commit()
        cnt = db_session.query(StripeEvent).filter(
            StripeEvent.stripe_event_id.like("evt_distinct_%")
        ).count()
        assert cnt == 3


# ---------------------------------------------------------------------
# _json_safe — Decimal scrubbing
# ---------------------------------------------------------------------

class TestJsonSafe:
    """The webhook used to crash on Decimal-typed fields in Stripe payloads.
    `_json_safe` must coerce them to numerics that survive json.dumps."""

    @pytest.fixture(scope="class")
    def _json_safe(self):
        # Lazy import — avoid pulling Flask app side effects at collection.
        import importlib
        mod = importlib.import_module("app")
        return mod._json_safe

    def test_passes_through_primitives(self, _json_safe):
        assert _json_safe(1) == 1
        assert _json_safe("x") == "x"
        assert _json_safe(None) is None
        assert _json_safe(True) is True

    def test_decimal_integer_to_int(self, _json_safe):
        out = _json_safe(decimal.Decimal("100"))
        assert out == 100
        assert isinstance(out, int)

    def test_decimal_fractional_to_float(self, _json_safe):
        out = _json_safe(decimal.Decimal("19.99"))
        assert out == pytest.approx(19.99)
        assert isinstance(out, float)

    def test_nested_dict_recursion(self, _json_safe):
        payload = {
            "id": "evt_test",
            "data": {
                "object": {
                    "amount_total": decimal.Decimal("1999"),
                    "tax": decimal.Decimal("0.50"),
                    "items": [
                        {"qty": decimal.Decimal("3"), "price": decimal.Decimal("9.99")},
                    ],
                }
            },
        }
        cleaned = _json_safe(payload)
        # Survives json.dumps — that's the actual contract.
        json.dumps(cleaned)
        # Spot-check structure
        assert cleaned["data"]["object"]["amount_total"] == 1999
        assert cleaned["data"]["object"]["items"][0]["qty"] == 3
        assert cleaned["data"]["object"]["items"][0]["price"] == pytest.approx(9.99)

    def test_tuple_becomes_list(self, _json_safe):
        out = _json_safe(("a", "b", decimal.Decimal("1")))
        assert out == ["a", "b", 1]

    def test_idempotent(self, _json_safe):
        once = _json_safe({"x": decimal.Decimal("7.5")})
        twice = _json_safe(once)
        assert once == twice


# ---------------------------------------------------------------------
# StripeEvent insert with Decimal in payload (regression check)
# ---------------------------------------------------------------------

class TestStripeEventDecimalPayload:
    def test_stripe_event_with_decimal_after_json_safe(self, db_session, _models_module):
        """A payload that contained Decimal values must, after `_json_safe`,
        successfully insert into the JSONB column."""
        import importlib
        app_mod = importlib.import_module("app")
        _json_safe = app_mod._json_safe

        StripeEvent = _models_module.StripeEvent
        raw = {
            "id": "evt_decimal_payload",
            "type": "customer.subscription.updated",
            "data": {"object": {"amount": decimal.Decimal("1999"), "tax": decimal.Decimal("0.50")}},
        }
        cleaned = _json_safe(raw)

        ev = StripeEvent(
            stripe_event_id="evt_decimal_payload",
            event_type="customer.subscription.updated",
            payload=cleaned,
        )
        db_session.add(ev)
        db_session.commit()

        roundtrip = db_session.query(StripeEvent).filter_by(
            stripe_event_id="evt_decimal_payload"
        ).first()
        assert roundtrip is not None
        assert roundtrip.payload["data"]["object"]["amount"] == 1999
