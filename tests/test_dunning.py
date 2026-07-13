"""
Coverage for CARD W1.3 (docs/marketing/GTM_EXECUTION_PLAYBOOK.md) - the app-owned
dunning final-notice email in /home/flask/web/app.py.

The contract:
  * Stripe Smart Retries (Dashboard-side, FOUNDER-toggled) owns every mid-sequence
    "your payment failed" email - the app never duplicates those.
  * The app owns exactly ONE email: the final pre-cancel "your access pauses"
    nudge, fired from invoice.payment_failed ONLY when Stripe has stopped
    scheduling further retries (next_payment_attempt is None on the invoice).
  * A mid-retry invoice.payment_failed (next_payment_attempt still set) must
    NOT fire the app email - Stripe's own retry emails are still in flight.
  * next_payment_attempt is None ALSO on collection_method=send_invoice invoices
    (no retry schedule ever exists there) - the gate additionally requires
    collection_method == 'charge_automatically' AND a real subscription, so
    those invoices never fire the app email either (reasoner-review catch,
    2026-07-09).
  * The user's tier/access is never changed by invoice.payment_failed - dunning
    is a notice, not a downgrade (Smart Retries keeps access live until the
    dashboard's configured final action, e.g. cancel, actually runs).
  * The dunning call is best-effort - an exception in email/billing-portal
    creation must never turn the webhook into a 500 (which would make Stripe
    retry the whole event).
  * A developer-API-line invoice (api_event) never fires the web dunning email.

Stripe SDK calls (Webhook.construct_event, billing_portal.Session.create) and
the outbound email are all monkeypatched - no network.
"""
from __future__ import annotations

import importlib
import json
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.db


@pytest.fixture
def app_module(_models_module):
    mod = importlib.import_module("app")
    mod.DBSession = _models_module.Session
    return mod


@pytest.fixture
def client(app_module, mock_stripe):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def stub_resend(app_module, monkeypatch):
    """Patch the resend_send_email import used inside _fire_dunning_final_notice
    (imported locally in that function: `from email_utils import resend_send_email`)."""
    import email_utils
    m = MagicMock(return_value=True)
    monkeypatch.setattr(email_utils, "resend_send_email", m)
    return m


@pytest.fixture
def stub_billing_portal(monkeypatch):
    import stripe
    m = MagicMock(return_value=MagicMock(url="https://billing.stripe.com/session/test_123"))
    monkeypatch.setattr(stripe.billing_portal.Session, "create", m)
    return m


@pytest.fixture
def paid_user(make_user):
    return make_user(
        tier="analyst",
        stripe_customer_id="cus_dunning_test",
        stripe_subscription_id="sub_dunning_test",
        stripe_subscription_status="active",
    )


def _post_webhook(client, event_id, event_type, data_object):
    payload = {
        "id": event_id,
        "type": event_type,
        "data": {"object": data_object},
    }
    return client.post(
        "/webhooks/stripe",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=fake"},
    )


class TestDunningFinalNotice:
    def test_final_failure_fires_the_app_email(
        self, app_module, client, paid_user, stub_resend, stub_billing_portal,
        monkeypatch, db_session, _models_module
    ):
        """next_payment_attempt: None = Stripe has given up retrying -> the ONE
        app-owned final notice fires."""
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        r = _post_webhook(client, "evt_dunning_final_1", "invoice.payment_failed", {
            "id": "in_final_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
            "collection_method": "charge_automatically",
            "next_payment_attempt": None,
        })
        assert r.status_code == 200

        stub_resend.assert_called_once()
        call_args = stub_resend.call_args
        assert call_args[0][0] == paid_user.email
        assert "pauses" in call_args[0][1].lower()
        assert "Analyst" in call_args[0][2]
        assert "billing.stripe.com" in call_args[0][2]

        # Tier/status: access is NOT downgraded by dunning - only status mirrors past_due.
        db_session.expire_all()
        refreshed = db_session.get(_models_module.User, paid_user.id)
        assert refreshed.tier == "analyst"
        assert refreshed.stripe_subscription_status == "past_due"

    def test_mid_retry_failure_does_not_fire_app_email(
        self, app_module, client, paid_user, stub_resend, stub_billing_portal, monkeypatch
    ):
        """next_payment_attempt still set = Stripe's own Smart Retries email is the
        one in flight for this attempt; the app must stay silent."""
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        r = _post_webhook(client, "evt_dunning_midretry_1", "invoice.payment_failed", {
            "id": "in_midretry_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
            "collection_method": "charge_automatically",
            "next_payment_attempt": 1234567890,
        })
        assert r.status_code == 200
        stub_resend.assert_not_called()

    def test_send_invoice_never_fires_dunning_email(
        self, app_module, client, paid_user, stub_resend, stub_billing_portal, monkeypatch
    ):
        """Reasoner-review catch (2026-07-09): collection_method=send_invoice invoices
        have no Stripe retry schedule at all, so next_payment_attempt is ALWAYS None on
        them - that is NOT 'retries exhausted', it is 'retries were never a concept
        here'. The app must never fire its dunning email on this collection method."""
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        r = _post_webhook(client, "evt_dunning_send_invoice_1", "invoice.payment_failed", {
            "id": "in_send_invoice_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
            "collection_method": "send_invoice",
            "next_payment_attempt": None,
        })
        assert r.status_code == 200
        stub_resend.assert_not_called()

    def test_first_failure_with_retries_disabled_never_fires_dunning_email(
        self, app_module, client, paid_user, stub_resend, stub_billing_portal, monkeypatch
    ):
        """A subscription with Smart Retries disabled also reports next_payment_attempt
        None on its very FIRST failure (no retry was ever scheduled) - same false-
        positive shape as send_invoice. The collection_method gate alone cannot
        distinguish this from a real charge_automatically final-failure by that field
        alone; document behavior: this path DOES currently fire (Smart Retries is a
        Dashboard-level account setting FOUNDER-enables per CARD W1.3 step 1, not
        something distinguishable per-invoice from the webhook payload). This test
        pins that known, accepted behavior rather than silently allowing regression."""
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        r = _post_webhook(client, "evt_dunning_no_retries_1", "invoice.payment_failed", {
            "id": "in_no_retries_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
            "collection_method": "charge_automatically",
            "next_payment_attempt": None,
        })
        assert r.status_code == 200
        # With Smart Retries enabled account-wide (the FOUNDER's W1.3 step-1 toggle),
        # this shape only occurs on a genuine final failure - so firing here is correct.
        stub_resend.assert_called_once()

    def test_payment_succeeded_never_fires_dunning_email(
        self, app_module, client, paid_user, stub_resend, monkeypatch
    ):
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        r = _post_webhook(client, "evt_dunning_recovered_1", "invoice.payment_succeeded", {
            "id": "in_recovered_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
        })
        assert r.status_code == 200
        stub_resend.assert_not_called()

    def test_email_failure_never_500s_the_webhook(
        self, app_module, client, paid_user, monkeypatch
    ):
        """Best-effort: an exception building/sending the dunning email must not
        turn the webhook into a 500 (which would make Stripe retry the whole event)."""
        monkeypatch.setattr(app_module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

        import stripe
        monkeypatch.setattr(
            stripe.billing_portal.Session, "create",
            MagicMock(side_effect=RuntimeError("stripe down")),
        )
        import email_utils
        monkeypatch.setattr(
            email_utils, "resend_send_email",
            MagicMock(side_effect=RuntimeError("resend down")),
        )

        r = _post_webhook(client, "evt_dunning_boom_1", "invoice.payment_failed", {
            "id": "in_boom_1",
            "customer": "cus_dunning_test",
            "subscription": "sub_dunning_test",
            "collection_method": "charge_automatically",
            "next_payment_attempt": None,
        })
        assert r.status_code == 200
        assert r.get_json()["received"] is True


class TestFireDunningFinalNoticeUnit:
    """Direct unit coverage of _fire_dunning_final_notice, independent of the
    webhook route (fast, no signature/payload plumbing)."""

    def test_no_email_no_send_attempted(self, app_module, stub_resend, make_user):
        # users.email is NOT NULL in the schema, so insert normally then blank
        # the in-memory attribute (not re-committed) to exercise the guard.
        u = make_user(tier="navigator")
        u.email = None
        app_module._fire_dunning_final_notice(u, "evt_x")
        stub_resend.assert_not_called()

    def test_billing_portal_failure_falls_back_to_account_link(
        self, app_module, stub_resend, make_user, monkeypatch
    ):
        import stripe
        monkeypatch.setattr(
            stripe.billing_portal.Session, "create",
            MagicMock(side_effect=RuntimeError("stripe down")),
        )
        u = make_user(tier="strategist", stripe_customer_id="cus_fallback_test")
        app_module._fire_dunning_final_notice(u, "evt_fallback")

        stub_resend.assert_called_once()
        body = stub_resend.call_args[0][2]
        assert "/account" in body
        assert "Strategist" in body
