"""Stripe deletion ordering and lifecycle-outbox regression coverage."""
from __future__ import annotations

import importlib
import json
from contextlib import nullcontext
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.db


@pytest.fixture
def app_module(_models_module, test_engine, monkeypatch):
    _models_module.StripeCheckoutClaim.__table__.create(
        bind=test_engine, checkfirst=True,
    )
    module = importlib.import_module("app")
    module.DBSession = _models_module.Session
    monkeypatch.setattr(module.config, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    return module


def deleted_event(event_id, customer_id, subscription_id, price_id="price_web"):
    return {
        "id": event_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": subscription_id,
                "customer": customer_id,
                "status": "canceled",
                "items": {"data": [{"price": {"id": price_id}}]},
                "metadata": {},
            },
        },
    }


def updated_event(
    event_id, customer_id, subscription_id, status, price_id="price_web",
):
    event = deleted_event(event_id, customer_id, subscription_id, price_id)
    event["type"] = "customer.subscription.updated"
    event["data"]["object"]["status"] = status
    return event


def checkout_event(
    event_id, customer_id, subscription_id, *, product_line, tier,
):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{event_id}",
                "customer": customer_id,
                "subscription": subscription_id,
                "metadata": {
                    "product_line": product_line,
                    "tier": tier,
                },
            },
        },
    }


def invoice_event(
    event_id, customer_id, subscription_id, event_type,
):
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": f"in_{event_id}",
                "customer": customer_id,
                "subscription": subscription_id,
                "collection_method": "charge_automatically",
                "next_payment_attempt": None,
            },
        },
    }


def post_event(app_module, event, *, current_subscription=None):
    event_type = event.get("type")
    if current_subscription is None and event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        current_subscription = event["data"]["object"]
    retrieve_patch = (
        patch.object(
            app_module.stripe.Subscription,
            "retrieve",
            return_value=current_subscription,
        )
        if current_subscription is not None else nullcontext()
    )
    with retrieve_patch, app_module.app.test_client() as client:
        return client.post(
            "/webhooks/stripe",
            data=json.dumps(event),
            content_type="application/json",
            headers={"Stripe-Signature": "test"},
        )


class _CheckoutSession:
    """Small StripeObject stand-in for route-level success tests."""

    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def success_session(
    user, subscription_id, *, product_line="eod", tier="analyst",
    customer_id="cus_success", payment_status="paid",
):
    return {
        "id": f"cs_{subscription_id}",
        "client_reference_id": str(user.id),
        "status": "complete",
        "payment_status": payment_status,
        "customer": customer_id,
        "subscription": subscription_id,
        "metadata": {
            "product_line": product_line,
            "tier": tier,
        },
    }


def retrieved_subscription(
    subscription_id, *, status="active", price_id="price_web",
):
    return {
        "id": subscription_id,
        "status": status,
        "items": {"data": [{"price": {"id": price_id}}]},
    }


def get_success(app_module, user, session_id="cs_route"):
    with patch.object(app_module, "get_current_user", return_value=user):
        with app_module.app.test_client() as client:
            return client.get(f"/stripe/success?session_id={session_id}")


def test_success_rejects_api_checkout_without_touching_web_identity(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="success-api-checkout@example.com",
        tier="strategist",
        legacy_wp_level="6",
        stripe_customer_id="cus_web_existing",
        stripe_subscription_id="sub_web_existing",
        stripe_subscription_status="active",
        api_tier="pro",
        api_stripe_subscription_id="sub_api_existing",
        api_stripe_subscription_status="active",
    )
    payload = success_session(
        user,
        "sub_api_new",
        product_line="api",
        tier="business",
        customer_id="cus_web_existing",
    )
    with patch.object(
        app_module.stripe.checkout.Session,
        "retrieve",
        return_value=_CheckoutSession(payload),
    ), patch.object(
        app_module.stripe.Subscription,
        "retrieve",
        side_effect=AssertionError("API success must be rejected before lookup"),
    ):
        response = get_success(app_module, user, "cs_api_route")

    assert response.status_code == 400
    assert response.get_json()["error"] == "not_web_checkout"
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.tier == "strategist"
    assert fresh.legacy_wp_level == "6"
    assert fresh.stripe_customer_id == "cus_web_existing"
    assert fresh.stripe_subscription_id == "sub_web_existing"
    assert fresh.stripe_subscription_status == "active"
    assert fresh.api_tier == "pro"
    assert fresh.api_stripe_subscription_id == "sub_api_existing"
    assert fresh.api_stripe_subscription_status == "active"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


def test_success_rejects_paid_session_when_fresh_subscription_is_canceled(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="success-canceled-sub@example.com",
        tier="explorer",
        legacy_wp_level="1",
    )
    payload = success_session(user, "sub_fresh_canceled")
    with patch.object(
        app_module.stripe.checkout.Session,
        "retrieve",
        return_value=_CheckoutSession(payload),
    ), patch.object(
        app_module.stripe.Subscription,
        "retrieve",
        return_value=retrieved_subscription(
            "sub_fresh_canceled", status="canceled",
        ),
    ) as retrieve_sub, patch.object(
        app_module, "_tier_period_for_price",
        return_value=("analyst", "monthly"),
    ):
        response = get_success(app_module, user, "cs_canceled_route")

    assert response.status_code == 409
    assert response.get_json()["error"] == "unverified_web_subscription"
    retrieve_sub.assert_called_once_with(
        "sub_fresh_canceled", expand=["items.data.price"],
    )
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.tier == "explorer"
    assert fresh.legacy_wp_level == "1"
    assert fresh.stripe_customer_id is None
    assert fresh.stripe_subscription_id is None
    assert fresh.stripe_subscription_status is None
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


def test_success_accepts_paid_live_eod_and_queues_reconcile(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="success-live-eod@example.com",
        tier="explorer",
        legacy_wp_level="1",
    )
    payload = success_session(
        user, "sub_live_eod", customer_id="cus_live_eod",
    )
    with patch.object(
        app_module.stripe.checkout.Session,
        "retrieve",
        return_value=_CheckoutSession(payload),
    ), patch.object(
        app_module.stripe.Subscription,
        "retrieve",
        return_value=retrieved_subscription("sub_live_eod", status="active"),
    ) as retrieve_sub, patch.object(
        app_module, "_tier_period_for_price",
        return_value=("analyst", "monthly"),
    ), patch.object(app_module, "write_audit"):
        response = get_success(app_module, user, "cs_live_route")

    assert response.status_code == 302
    assert response.headers["Location"] == "/app/?upgraded=1"
    retrieve_sub.assert_called_once_with(
        "sub_live_eod", expand=["items.data.price"],
    )
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.tier == "analyst"
    assert fresh.legacy_wp_level == "4"
    assert fresh.stripe_customer_id == "cus_live_eod"
    assert fresh.stripe_subscription_id == "sub_live_eod"
    assert fresh.stripe_subscription_status == "active"
    rows = db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].event_type == "reconcile"
    assert rows[0].dedupe_key == "stripe-success:cs_live_route"
    assert rows[0].payload == {
        "paid_subscription_id": "sub_live_eod",
        "level_tier": "analyst",
        "level_period": "monthly",
    }


def test_success_defers_when_live_session_differs_from_current_subscription(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="success-different-sub@example.com",
        tier="strategist",
        legacy_wp_level="6",
        stripe_customer_id="cus_current",
        stripe_subscription_id="sub_current",
        stripe_subscription_status="active",
    )
    payload = success_session(
        user, "sub_other_live", tier="analyst", customer_id="cus_other",
    )
    with patch.object(
        app_module.stripe.checkout.Session,
        "retrieve",
        return_value=_CheckoutSession(payload),
    ), patch.object(
        app_module.stripe.Subscription,
        "retrieve",
        return_value=retrieved_subscription("sub_other_live", status="active"),
    ), patch.object(
        app_module, "_tier_period_for_price",
        return_value=("analyst", "monthly"),
    ), patch.object(app_module, "write_audit") as audit:
        response = get_success(app_module, user, "cs_different_route")

    assert response.status_code == 302
    assert response.headers["Location"] == "/app/?upgrade_pending=1"
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.tier == "strategist"
    assert fresh.legacy_wp_level == "6"
    assert fresh.stripe_customer_id == "cus_current"
    assert fresh.stripe_subscription_id == "sub_current"
    assert fresh.stripe_subscription_status == "active"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0
    audit.assert_not_called()


def test_stale_old_subscription_delete_preserves_current_payer(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="stale-delete@example.com",
        tier="strategist",
        stripe_customer_id="cus_stale",
        stripe_subscription_id="sub_current",
        stripe_subscription_status="active",
    )
    event = deleted_event("evt_stale_delete", "cus_stale", "sub_old")
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(app_module, "_tier_period_for_price", return_value=("strategist", "monthly")), \
         patch.object(app_module, "write_audit") as audit:
        response = post_event(app_module, event)

    assert response.status_code == 200
    assert response.get_json()["ignored_delete"] == "stale_subscription"
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_current"
    assert fresh.stripe_subscription_status == "active"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0
    assert any(
        call.kwargs.get("action") == "stale_subscription_deleted_ignored"
        for call in audit.call_args_list
    )


def test_matching_delete_downgrades_and_queues_winback_reconcile(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="matching-delete@example.com",
        tier="analyst",
        stripe_customer_id="cus_match",
        stripe_subscription_id="sub_match",
        stripe_subscription_status="active",
    )
    event = deleted_event("evt_matching_delete", "cus_match", "sub_match")
    with patch.object(
        app_module,
        "_subscription_product_target",
        side_effect=AssertionError("matching delete must not query Stripe pricing"),
    ) as classify, patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    classify.assert_not_called()
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "explorer"
    assert fresh.stripe_subscription_id == "sub_match"
    assert fresh.stripe_subscription_status == "canceled"
    rows = db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].dedupe_key == "stripe:evt_matching_delete:reconcile"

    from mailerlite_lifecycle import derive_lifecycle_state
    assert derive_lifecycle_state(fresh) == "winback_explorer"


def test_api_subscription_delete_never_touches_web_tier(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="api-delete@example.com",
        tier="strategist",
        api_tier="pro",
        api_stripe_subscription_id="sub_api",
        api_stripe_subscription_status="active",
        stripe_customer_id="cus_api",
        stripe_subscription_id="sub_web",
        stripe_subscription_status="active",
    )
    event = deleted_event(
        "evt_api_delete", "cus_api", "sub_api", price_id="price_api",
    )
    with patch.object(
        app_module,
        "_subscription_product_target",
        side_effect=AssertionError("matching API delete must not query Stripe pricing"),
    ) as classify, patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    classify.assert_not_called()
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_web"
    assert fresh.stripe_subscription_status == "active"
    assert fresh.api_tier is None
    assert fresh.api_stripe_subscription_id == "sub_api"
    assert fresh.api_stripe_subscription_status == "canceled"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


def test_api_checkout_never_overwrites_web_subscription(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="api-checkout@example.com",
        tier="strategist",
        api_tier=None,
        stripe_customer_id="cus_api_checkout",
        stripe_subscription_id="sub_web",
        stripe_subscription_status="active",
    )
    event = checkout_event(
        "evt_api_checkout",
        "cus_api_checkout",
        "sub_api",
        product_line="api",
        tier="pro",
    )
    with patch.object(app_module, "write_audit"), \
         patch.object(app_module, "send_event"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_web"
    assert fresh.stripe_subscription_status == "active"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


@pytest.mark.parametrize(
    "event_type",
    ["invoice.payment_failed", "invoice.payment_succeeded"],
)
def test_api_invoice_never_overwrites_web_subscription_or_duns(
    app_module, db_session, _models_module, make_user, mock_stripe,
    event_type,
):
    user = make_user(
        email=f"{event_type.replace('.', '-')}@example.com",
        tier="analyst",
        stripe_customer_id="cus_api_invoice",
        stripe_subscription_id="sub_web",
        stripe_subscription_status="active",
    )
    event = invoice_event(
        f"evt_{event_type.replace('.', '_')}",
        "cus_api_invoice",
        "sub_api",
        event_type,
    )
    with patch.object(app_module, "write_audit"), \
         patch.object(app_module, "_fire_dunning_final_notice") as dunning:
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "analyst"
    assert fresh.stripe_subscription_id == "sub_web"
    assert fresh.stripe_subscription_status == "active"
    dunning.assert_not_called()


def test_current_web_failed_invoice_updates_status_and_duns(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="web-invoice@example.com",
        tier="analyst",
        stripe_customer_id="cus_web_invoice",
        stripe_subscription_id="sub_web_invoice",
        stripe_subscription_status="active",
    )
    event = invoice_event(
        "evt_web_invoice_failed",
        "cus_web_invoice",
        "sub_web_invoice",
        "invoice.payment_failed",
    )
    with patch.object(app_module, "write_audit"), \
         patch.object(app_module, "_fire_dunning_final_notice") as dunning:
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.stripe_subscription_status == "past_due"
    dunning.assert_called_once()


@pytest.mark.parametrize("terminal_status", ["canceled", "unpaid"])
def test_terminal_web_update_downgrades_and_queues_winback(
    app_module, db_session, _models_module, make_user, mock_stripe,
    terminal_status,
):
    user = make_user(
        email=f"terminal-{terminal_status}@example.com",
        tier="analyst",
        stripe_customer_id=f"cus_{terminal_status}",
        stripe_subscription_id=f"sub_{terminal_status}",
        stripe_subscription_status="active",
    )
    event = updated_event(
        f"evt_terminal_{terminal_status}",
        f"cus_{terminal_status}",
        f"sub_{terminal_status}",
        terminal_status,
    )
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module, "_tier_period_for_price",
             return_value=("analyst", "monthly"),
         ), \
         patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "explorer"
    assert fresh.stripe_subscription_status == terminal_status
    rows = db_session.query(
        _models_module.MailerLiteLifecycleEvent
    ).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].payload["level_tier"] == "explorer"


def test_stale_terminal_update_preserves_newer_web_subscription(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="stale-terminal-update@example.com",
        tier="strategist",
        stripe_customer_id="cus_stale_update",
        stripe_subscription_id="sub_current",
        stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_stale_terminal_update",
        "cus_stale_update",
        "sub_old",
        "unpaid",
    )
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module, "_tier_period_for_price",
             return_value=("strategist", "monthly"),
         ), \
         patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    assert response.get_json()["ignored_subscription"] == "stale_subscription"
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_current"
    assert fresh.stripe_subscription_status == "active"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


def test_stale_created_event_cannot_replace_newer_web_subscription(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="stale-created@example.com",
        tier="strategist",
        stripe_customer_id="cus_stale_created",
        stripe_subscription_id="sub_newer",
        stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_stale_created",
        "cus_stale_created",
        "sub_older",
        "active",
    )
    event["type"] = "customer.subscription.created"
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module, "_tier_period_for_price",
             return_value=("analyst", "monthly"),
         ), \
         patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    assert response.get_json()["ignored_subscription"] == "stale_subscription"
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_newer"


def test_signed_api_metadata_provisions_without_price_cache(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="api-metadata@example.com",
        stripe_customer_id="cus_api_metadata",
    )
    event = updated_event(
        "evt_api_metadata",
        "cus_api_metadata",
        "sub_api_metadata",
        "active",
        price_id="price_archived_api",
    )
    event["type"] = "customer.subscription.created"
    event["data"]["object"]["metadata"] = {
        "product_line": "api",
        "tier": "business",
        "tw2_user_id": str(user.id),
    }
    event["data"]["object"]["items"] = {"data": []}
    with patch.object(
        app_module, "_api_tier_for_price",
        side_effect=AssertionError("metadata path must not consult cache"),
    ), patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.api_tier == "business"
    assert fresh.api_stripe_subscription_id == "sub_api_metadata"
    assert fresh.api_stripe_subscription_status == "active"


def test_web_portal_price_change_overrides_stale_subscription_metadata(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="web-portal-switch@example.com",
        tier="navigator",
        stripe_customer_id="cus_web_portal_switch",
        stripe_subscription_id="sub_web_portal_switch",
        stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_web_portal_switch",
        "cus_web_portal_switch",
        "sub_web_portal_switch",
        "active",
        price_id="price_strategist_yearly",
    )
    event["data"]["object"]["metadata"] = {
        "product_line": "eod",
        "tier": "navigator",
        "period": "monthly",
    }
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module,
             "_tier_period_for_price",
             return_value=("strategist", "yearly"),
         ), patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    row = db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).one()
    assert row.payload["level_tier"] == "strategist"
    assert row.payload["level_period"] == "yearly"


def test_api_portal_price_change_overrides_stale_subscription_metadata(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="api-portal-switch@example.com",
        tier="analyst",
        api_tier="dev",
        stripe_customer_id="cus_api_portal_switch",
        api_stripe_subscription_id="sub_api_portal_switch",
        api_stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_api_portal_switch",
        "cus_api_portal_switch",
        "sub_api_portal_switch",
        "active",
        price_id="price_api_business",
    )
    event["data"]["object"]["metadata"] = {
        "product_line": "api",
        "tier": "dev",
    }
    with patch.object(
        app_module, "_api_tier_for_price", return_value="business",
    ), patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.api_tier == "business"
    assert fresh.tier == "analyst"


@pytest.mark.parametrize(
    "event_type", [
        "customer.subscription.created",
        "customer.subscription.updated",
    ],
)
def test_delayed_live_event_cannot_regrant_same_canceled_web_subscription(
    app_module, db_session, _models_module, make_user, mock_stripe,
    event_type,
):
    user = make_user(
        email=f"same-id-{event_type.rsplit('.', 1)[-1]}@example.com",
        tier="explorer",
        stripe_customer_id="cus_same_id_terminal",
        stripe_subscription_id="sub_same_id_terminal",
        stripe_subscription_status="canceled",
    )
    event = updated_event(
        f"evt_same_id_{event_type.rsplit('.', 1)[-1]}",
        "cus_same_id_terminal",
        "sub_same_id_terminal",
        "active",
    )
    event["type"] = event_type
    event["data"]["object"]["metadata"] = {
        "product_line": "eod",
        "tier": "analyst",
        "period": "monthly",
    }
    current = dict(event["data"]["object"])
    current["status"] = "canceled"
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module,
             "_tier_period_for_price",
             return_value=("analyst", "monthly"),
         ), patch.object(app_module, "write_audit"):
        response = post_event(
            app_module, event, current_subscription=current,
        )

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "explorer"
    assert fresh.stripe_subscription_status == "canceled"


def test_deleted_replacement_cannot_be_adopted_by_delayed_created_event(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="deleted-replacement@example.com",
        tier="strategist",
        stripe_customer_id="cus_deleted_replacement",
        stripe_subscription_id="sub_predecessor",
        stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_deleted_replacement_created",
        "cus_deleted_replacement",
        "sub_deleted_replacement",
        "active",
    )
    event["type"] = "customer.subscription.created"
    event["data"]["object"]["metadata"] = {
        "product_line": "eod",
        "tier": "analyst",
        "period": "monthly",
        "replaces_subscription_id": "sub_predecessor",
    }
    current = dict(event["data"]["object"])
    current["status"] = "canceled"
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module,
             "_tier_period_for_price",
             return_value=("analyst", "monthly"),
         ), patch.object(app_module, "write_audit"):
        response = post_event(
            app_module, event, current_subscription=current,
        )

    assert response.status_code == 200
    assert response.get_json()["ignored_subscription"] == (
        "stale_subscription"
    )
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_predecessor"


def test_delayed_created_hydrated_terminal_revokes_current_web_access(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="terminal-created-web@example.com",
        tier="analyst",
        stripe_customer_id="cus_terminal_created_web",
        stripe_subscription_id="sub_terminal_created_web",
        stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_terminal_created_web",
        "cus_terminal_created_web",
        "sub_terminal_created_web",
        "active",
    )
    event["type"] = "customer.subscription.created"
    event["data"]["object"]["metadata"] = {
        "product_line": "eod",
        "tier": "analyst",
        "period": "monthly",
    }
    current = dict(event["data"]["object"])
    current["status"] = "canceled"
    with patch.object(app_module, "_api_tier_for_price", return_value=None), \
         patch.object(
             app_module,
             "_tier_period_for_price",
             return_value=("analyst", "monthly"),
         ), patch.object(app_module, "write_audit"):
        response = post_event(
            app_module, event, current_subscription=current,
        )

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.tier == "explorer"
    assert fresh.stripe_subscription_status == "canceled"
    row = db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).one()
    assert row.payload["level_tier"] == "explorer"


def test_delayed_created_hydrated_terminal_revokes_only_current_api_access(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="terminal-created-api@example.com",
        tier="analyst",
        api_tier="business",
        stripe_customer_id="cus_terminal_created_api",
        stripe_subscription_id="sub_web_stays",
        stripe_subscription_status="active",
        api_stripe_subscription_id="sub_terminal_created_api",
        api_stripe_subscription_status="active",
    )
    event = updated_event(
        "evt_terminal_created_api",
        "cus_terminal_created_api",
        "sub_terminal_created_api",
        "active",
        price_id="price_api_business",
    )
    event["type"] = "customer.subscription.created"
    event["data"]["object"]["metadata"] = {
        "product_line": "api",
        "tier": "business",
    }
    current = dict(event["data"]["object"])
    current["status"] = "canceled"
    with patch.object(
        app_module, "_api_tier_for_price", return_value="business",
    ), patch.object(app_module, "write_audit"):
        response = post_event(
            app_module, event, current_subscription=current,
        )

    assert response.status_code == 200
    db_session.expire_all()
    fresh = db_session.get(_models_module.User, user.id)
    assert fresh.api_tier is None
    assert fresh.api_stripe_subscription_status == "canceled"
    assert fresh.tier == "analyst"
    assert fresh.stripe_subscription_id == "sub_web_stays"
    assert db_session.query(_models_module.MailerLiteLifecycleEvent).filter_by(
        user_id=user.id,
    ).count() == 0


def test_stale_api_cancellation_preserves_newer_api_plan(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="stale-api-delete@example.com",
        tier="analyst",
        api_tier="business",
        api_stripe_subscription_id="sub_api_new",
        api_stripe_subscription_status="active",
        stripe_customer_id="cus_stale_api",
        stripe_subscription_id="sub_web",
        stripe_subscription_status="active",
    )
    event = deleted_event(
        "evt_stale_api_delete",
        "cus_stale_api",
        "sub_api_old",
        price_id="price_api_old",
    )
    event["data"]["object"]["metadata"] = {
        "product_line": "api",
        "tier": "pro",
    }
    with patch.object(
        app_module,
        "_subscription_product_target",
        side_effect=AssertionError("stale API delete must not query Stripe pricing"),
    ) as classify, patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    classify.assert_not_called()
    assert response.get_json()["ignored_subscription"] == (
        "stale_api_subscription"
    )
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.api_tier == "business"
    assert fresh.api_stripe_subscription_id == "sub_api_new"
    assert fresh.tier == "analyst"
    assert fresh.stripe_subscription_id == "sub_web"


def test_unclassified_delete_lookup_failure_preserves_current_plan(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="unclassified-delete@example.com",
        tier="strategist",
        stripe_customer_id="cus_unclassified_delete",
        stripe_subscription_id="sub_web_current",
        stripe_subscription_status="active",
    )
    event = deleted_event(
        "evt_unclassified_delete",
        "cus_unclassified_delete",
        "sub_unknown_old",
        price_id="price_archived_unavailable",
    )
    with patch.object(
        app_module,
        "_subscription_product_target",
        side_effect=RuntimeError("Stripe price lookup unavailable"),
    ), patch.object(app_module, "write_audit"):
        response = post_event(app_module, event)

    assert response.status_code == 200
    assert response.get_json()["ignored_delete"] == "unclassified_subscription"
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.tier == "strategist"
    assert fresh.stripe_subscription_id == "sub_web_current"
    assert fresh.stripe_subscription_status == "active"


def test_late_failed_invoice_cannot_undo_terminal_web_state(
    app_module, db_session, _models_module, make_user, mock_stripe,
):
    user = make_user(
        email="late-invoice@example.com",
        tier="explorer",
        stripe_customer_id="cus_late_invoice",
        stripe_subscription_id="sub_terminal",
        stripe_subscription_status="canceled",
    )
    event = invoice_event(
        "evt_late_invoice",
        "cus_late_invoice",
        "sub_terminal",
        "invoice.payment_failed",
    )
    with patch.object(app_module, "write_audit"), \
         patch.object(app_module, "_fire_dunning_final_notice") as dunning:
        response = post_event(app_module, event)

    assert response.status_code == 200
    assert response.get_json()["ignored_subscription"] == (
        "terminal_subscription_invoice"
    )
    db_session.expire_all()
    fresh = db_session.query(_models_module.User).filter_by(id=user.id).one()
    assert fresh.stripe_subscription_status == "canceled"
    dunning.assert_not_called()
