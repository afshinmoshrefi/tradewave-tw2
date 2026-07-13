from types import SimpleNamespace
from unittest.mock import patch

import ops.audit_stripe_subscription_identity as audit
from ops.stripe_subscription_identity import UserIdentitySnapshot


class AutoPagedList:
    def __init__(self, items):
        self.items = items

    def auto_paging_iter(self):
        yield from self.items


def _item(item_id, line, tier):
    return {
        "id": item_id,
        "price": {
            "id": "price_" + item_id,
            "metadata": {},
            "recurring": {"interval": "month"},
            "product": {
                "id": "prod_" + item_id,
                "metadata": {"product_line": line, "tier": tier},
            },
        },
    }


def test_expanded_subscription_paginates_every_subscription_item():
    subscription = {
        "id": "sub_api",
        "customer": "cus_1",
        "status": "active",
        "items": {"data": [_item("first", "api", "dev")], "has_more": True},
    }
    all_items = [
        _item("first", "api", "dev"),
        _item("second", "api", "dev"),
    ]

    with patch.object(
        audit.stripe.Subscription, "retrieve", return_value=subscription,
    ), patch.object(
        audit.stripe.SubscriptionItem,
        "list",
        return_value=AutoPagedList(all_items),
    ) as item_list:
        expanded = audit._expanded_subscription("sub_api")

    assert expanded["items"]["has_more"] is False
    assert [item["id"] for item in expanded["items"]["data"]] == [
        "first", "second",
    ]
    item_list.assert_called_once_with(
        subscription="sub_api",
        limit=100,
        expand=["data.price.product"],
    )


def test_customer_subscription_scan_uses_auto_pagination():
    subscriptions = AutoPagedList([
        {"id": "sub_2"},
        {"id": "sub_1"},
        {"id": "sub_2"},
    ])

    with patch.object(
        audit.stripe.Subscription, "list", return_value=subscriptions,
    ) as subscription_list:
        found, errors = audit._customer_subscription_ids({"cus_1"})

    assert errors == {}
    assert found == {"cus_1": ("sub_1", "sub_2")}
    subscription_list.assert_called_once_with(
        customer="cus_1", status="all", limit=100,
    )


def test_partial_mapping_list_fails_closed_without_auto_pager():
    raw = {"data": [{"id": "sub_1"}], "has_more": True}

    with patch.object(audit.stripe.Subscription, "list", return_value=raw):
        found, errors = audit._customer_subscription_ids({"cus_1"})

    assert found == {}
    assert "has no auto_paging_iter" in errors["cus_1"]


def test_apply_requires_explicit_production_environment(monkeypatch):
    monkeypatch.setenv("TW2_ENV", "staging")
    monkeypatch.setattr(audit.config, "MAILERLITE_OUTBOUND_ENABLED", False)
    monkeypatch.setattr(audit.config, "STRIPE_SECRET_KEY", "sk_test_present")

    with patch.object(
        audit, "_snapshot_rows", side_effect=AssertionError("must stop before DB read"),
    ):
        result = audit.main(["--apply"])

    assert result == 2


def test_apply_refuses_while_mailerlite_outbound_is_enabled(monkeypatch):
    monkeypatch.setenv("TW2_ENV", "prod")
    monkeypatch.setattr(audit.config, "MAILERLITE_OUTBOUND_ENABLED", True)
    monkeypatch.setattr(audit.config, "STRIPE_SECRET_KEY", "sk_live_present")

    with patch.object(
        audit, "_snapshot_rows", side_effect=AssertionError("must stop before DB read"),
    ):
        result = audit.main(["--apply"])

    assert result == 2


def test_apply_snapshot_check_includes_entitlement_tiers():
    snapshot = UserIdentitySnapshot(
        user_id="user-1",
        email="user@example.com",
        customer_id="cus_1",
        web_subscription_id="sub_api",
        web_subscription_status="active",
        api_subscription_id=None,
        api_subscription_status=None,
        web_tier="strategist",
        api_tier="dev",
    )
    user = SimpleNamespace(
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_api",
        stripe_subscription_status="active",
        api_stripe_subscription_id=None,
        api_stripe_subscription_status=None,
        tier="strategist",
        api_tier="dev",
    )

    assert audit._same_snapshot(user, snapshot) is True
    user.tier = "explorer"
    assert audit._same_snapshot(user, snapshot) is False


def test_dry_run_is_allowed_outside_production(monkeypatch):
    monkeypatch.setenv("TW2_ENV", "staging")
    monkeypatch.setattr(audit.config, "STRIPE_SECRET_KEY", "sk_test_present")

    with patch.object(audit, "_snapshot_rows", return_value=[]):
        result = audit.main([])

    assert result == 0
