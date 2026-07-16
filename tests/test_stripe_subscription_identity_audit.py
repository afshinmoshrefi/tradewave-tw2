from dataclasses import replace

from ops.stripe_subscription_identity import (
    UserIdentitySnapshot,
    classify_subscription_payload,
    plan_identity_reconciliation,
)


def subscription_payload(
    subscription_id="sub_1",
    *,
    product_line=None,
    product_tier=None,
    subscription_line=None,
    subscription_tier=None,
    status="active",
    customer="cus_1",
    livemode=True,
):
    product_metadata = {}
    if product_line is not None:
        product_metadata["product_line"] = product_line
    if product_tier is not None:
        product_metadata["tier"] = product_tier
    subscription_metadata = {}
    if subscription_line is not None:
        subscription_metadata["product_line"] = subscription_line
    if subscription_tier is not None:
        subscription_metadata["tier"] = subscription_tier
    return {
        "id": subscription_id,
        "status": status,
        "customer": customer,
        "livemode": livemode,
        "metadata": subscription_metadata,
        "items": {
            "data": [{
                "price": {
                    "id": "price_1",
                    "recurring": {"interval": "month"},
                    "product": {
                        "id": "prod_1",
                        "metadata": product_metadata,
                    },
                },
            }],
        },
    }


def snapshot(**overrides):
    base = UserIdentitySnapshot(
        user_id="user-1",
        email="user@example.com",
        customer_id="cus_1",
        web_subscription_id="sub_api",
        web_subscription_status="active",
        api_subscription_id=None,
        api_subscription_status=None,
        web_tier="explorer",
        api_tier="dev",
    )
    return replace(base, **overrides)


def test_classifies_api_from_expanded_product_metadata():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
        subscription_line="api", subscription_tier="dev",
    ))

    assert evidence.line == "api"
    assert evidence.tier == "dev"
    assert evidence.status == "active"
    assert evidence.customer_id == "cus_1"


def test_classifies_valid_web_without_risking_it():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_web", product_line="eod", product_tier="analyst",
        subscription_line="eod", subscription_tier="analyst",
    ))

    assert evidence.line == "eod"
    assert evidence.tier == "analyst"
    assert evidence.period == "monthly"


def test_subscription_metadata_is_a_safe_fallback_for_unlabelled_price():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", subscription_line="api", subscription_tier="pro",
    ))

    assert evidence.line == "api"
    assert evidence.tier == "pro"
    assert evidence.reason == "classified-from-subscription"


def test_classifies_from_current_price_metadata_when_product_is_unlabelled():
    payload = subscription_payload("sub_api")
    payload["items"]["data"][0]["price"]["metadata"] = {
        "product_line": "api",
        "tier": "business",
    }

    evidence = classify_subscription_payload(payload)

    assert evidence.line == "api"
    assert evidence.tier == "business"
    assert evidence.reason == "classified-from-price/product"


def test_conflicting_price_and_product_metadata_blocks_classification():
    payload = subscription_payload(
        "sub_conflict", product_line="eod", product_tier="analyst",
    )
    payload["items"]["data"][0]["price"]["metadata"] = {
        "product_line": "api",
        "tier": "dev",
    }

    evidence = classify_subscription_payload(payload)

    assert evidence.line == "conflict"
    assert evidence.reason == "price-product-line-conflict:api,eod"


def test_legacy_unlabelled_subscription_remains_unknown():
    evidence = classify_subscription_payload(subscription_payload("sub_legacy"))

    assert evidence.line == "unknown"
    assert evidence.reason == "no-product-line-metadata"


def test_conflicting_subscription_and_product_lines_block_classification():
    evidence = classify_subscription_payload(subscription_payload(
        product_line="eod", product_tier="analyst",
        subscription_line="api", subscription_tier="dev",
    ))

    assert evidence.line == "conflict"
    assert "line-conflict" in evidence.reason


def test_mixed_product_lines_block_classification():
    payload = subscription_payload(product_line="api", product_tier="dev")
    payload["items"]["data"].append({
        "price": {
            "id": "price_2",
            "product": {
                "id": "prod_2",
                "metadata": {"product_line": "eod", "tier": "analyst"},
            },
        },
    })

    evidence = classify_subscription_payload(payload)

    assert evidence.line == "conflict"
    assert evidence.reason == "mixed-product-lines:api,eod"


def test_partially_labelled_items_block_even_with_subscription_metadata():
    payload = subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
        subscription_line="api", subscription_tier="dev",
    )
    payload["items"]["data"].append({
        "price": {
            "id": "price_unlabelled",
            "recurring": {"interval": "month"},
            "product": {"id": "prod_unlabelled", "metadata": {}},
        },
    })

    evidence = classify_subscription_payload(payload)

    assert evidence.line == "conflict"
    assert evidence.reason == "partially-labelled-multi-item-subscription"


def test_partial_subscription_item_page_blocks_classification():
    payload = subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    )
    payload["items"]["has_more"] = True

    evidence = classify_subscription_payload(payload)

    assert evidence.line == "conflict"
    assert evidence.reason == "subscription-items-not-fully-loaded"


def test_moves_confirmed_api_identity_out_of_web_columns():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))

    plan = plan_identity_reconciliation(
        snapshot(), evidence, None,
        customer_subscriptions=(evidence,),
        customer_scan_complete=True,
    )

    assert plan.action == "move-api-from-web"
    assert plan.applyable is True
    assert plan.blocking is False
    assert plan.web_subscription_id is None
    assert plan.web_subscription_status is None
    assert plan.api_subscription_id == "sub_api"
    assert plan.api_subscription_status == "active"


def test_clears_web_duplicate_when_same_api_id_is_already_adopted():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))
    user = snapshot(
        api_subscription_id="sub_api",
        api_subscription_status="past_due",
    )

    plan = plan_identity_reconciliation(
        user, evidence, evidence,
        customer_subscriptions=(evidence,),
        customer_scan_complete=True,
    )

    assert plan.action == "clear-duplicate-api-from-web"
    assert plan.applyable is True
    assert plan.api_subscription_status == "active"
    assert plan.web_subscription_id is None


def test_preserves_confirmed_web_identity_byte_for_byte():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_web", product_line="eod", product_tier="strategist",
    ))
    user = snapshot(
        web_subscription_id="sub_web",
        web_subscription_status="past_due",
    )

    plan = plan_identity_reconciliation(user, evidence, None)

    assert plan.action == "preserve-valid-web"
    assert plan.applyable is False
    assert plan.blocking is False
    assert plan.web_subscription_id == "sub_web"
    assert plan.web_subscription_status == "past_due"


def test_preserves_unlabelled_legacy_web_identity():
    evidence = classify_subscription_payload(subscription_payload("sub_legacy"))
    user = snapshot(web_subscription_id="sub_legacy")

    plan = plan_identity_reconciliation(user, evidence, None)

    assert plan.action == "preserve-legacy-web"
    assert plan.applyable is False
    assert plan.blocking is False


def test_different_existing_api_identity_blocks_all_changes():
    web_evidence = classify_subscription_payload(subscription_payload(
        "sub_api_old", product_line="api", product_tier="dev",
    ))
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_api_new", product_line="api", product_tier="pro",
    ))
    user = snapshot(
        web_subscription_id="sub_api_old",
        api_subscription_id="sub_api_new",
        api_subscription_status="active",
        api_tier="pro",
    )

    plan = plan_identity_reconciliation(user, web_evidence, api_evidence)

    assert plan.action == "blocked-two-api-subscriptions"
    assert plan.applyable is False
    assert plan.blocking is True
    assert plan.web_subscription_id == "sub_api_old"
    assert plan.api_subscription_id == "sub_api_new"


def test_customer_mismatch_blocks_move():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
        customer="cus_other",
    ))

    plan = plan_identity_reconciliation(snapshot(), evidence, None)

    assert plan.action == "blocked-web-customer-mismatch"
    assert plan.blocking is True
    assert plan.applyable is False


def test_rebinds_stale_foreign_web_id_to_only_matching_customer_plan():
    stale = classify_subscription_payload(subscription_payload(
        "sub_foreign", product_line="eod", product_tier="analyst",
        subscription_tier="strategist", customer="cus_other",
        livemode=False,
    ))
    canonical = classify_subscription_payload(subscription_payload(
        "sub_owned", product_line="eod", product_tier="strategist",
        subscription_line="eod", subscription_tier="strategist",
        customer="cus_1", livemode=False,
    ))
    user = snapshot(
        web_subscription_id="sub_foreign",
        web_tier="strategist",
        api_tier=None,
    )

    plan = plan_identity_reconciliation(
        user, stale, None,
        customer_subscriptions=(canonical,),
        customer_scan_complete=True,
        expected_livemode=False,
    )

    assert stale.line == "conflict"
    assert plan.action == "rebind-web-to-customer-subscription"
    assert plan.applyable is True
    assert plan.blocking is False
    assert plan.web_subscription_id == "sub_owned"
    assert plan.web_subscription_status == "active"
    assert plan.api_subscription_id is None


def test_foreign_web_id_rebind_refuses_multiple_customer_subscriptions():
    stale = classify_subscription_payload(subscription_payload(
        "sub_foreign", product_line="eod", product_tier="analyst",
        subscription_tier="strategist", customer="cus_other",
    ))
    canonical = classify_subscription_payload(subscription_payload(
        "sub_owned", product_line="eod", product_tier="strategist",
    ))
    historical = classify_subscription_payload(subscription_payload(
        "sub_old", product_line="eod", product_tier="strategist",
        status="canceled",
    ))

    plan = plan_identity_reconciliation(
        snapshot(web_subscription_id="sub_foreign", web_tier="strategist"),
        stale,
        None,
        customer_subscriptions=(canonical, historical),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-web-classification"
    assert plan.blocking is True


def test_shared_subscription_id_blocks_move():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))

    plan = plan_identity_reconciliation(
        snapshot(), evidence, None,
        shared_subscription_ids=("sub_api",),
    )

    assert plan.action == "blocked-shared-web-id"
    assert plan.blocking is True


def test_incomplete_customer_scan_blocks_move():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))

    plan = plan_identity_reconciliation(snapshot(), evidence, None)

    assert plan.action == "blocked-incomplete-customer-subscription-scan"
    assert plan.blocking is True


def test_production_plan_blocks_test_mode_stripe_evidence():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev", livemode=False,
    ))

    plan = plan_identity_reconciliation(
        snapshot(), evidence, None,
        customer_subscriptions=(evidence,),
        customer_scan_complete=True,
        expected_livemode=True,
    )

    assert plan.action == "blocked-web-stripe-mode"
    assert plan.blocking is True


def test_complete_customer_scan_must_include_stored_subscription():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))

    plan = plan_identity_reconciliation(
        snapshot(), evidence, None,
        customer_subscriptions=(),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-stored-id-missing-from-customer-scan"
    assert plan.blocking is True


def test_paid_web_tier_never_clears_without_verified_eod_identity():
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))
    user = snapshot(web_tier="strategist")

    plan = plan_identity_reconciliation(
        user, api_evidence, None,
        customer_subscriptions=(api_evidence,),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-paid-web-tier-without-eod-identity"
    assert plan.blocking is True
    assert plan.web_subscription_id == "sub_api"


def test_restores_one_verified_live_eod_identity_for_paid_web_tier():
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))
    eod_evidence = classify_subscription_payload(subscription_payload(
        "sub_eod", product_line="eod", product_tier="strategist",
    ))
    user = snapshot(web_tier="strategist")

    plan = plan_identity_reconciliation(
        user, api_evidence, None,
        customer_subscriptions=(api_evidence, eod_evidence),
        customer_scan_complete=True,
    )

    assert plan.action == "restore-web-and-move-api"
    assert plan.applyable is True
    assert plan.web_subscription_id == "sub_eod"
    assert plan.web_subscription_status == "active"
    assert plan.api_subscription_id == "sub_api"


def test_live_eod_with_explorer_tier_blocks_instead_of_partial_repair():
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))
    eod_evidence = classify_subscription_payload(subscription_payload(
        "sub_eod", product_line="eod", product_tier="analyst",
    ))

    plan = plan_identity_reconciliation(
        snapshot(), api_evidence, None,
        customer_subscriptions=(api_evidence, eod_evidence),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-live-web-tier-mismatch"
    assert plan.blocking is True


def test_api_tier_mismatch_blocks_identity_move():
    evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="business",
    ))

    plan = plan_identity_reconciliation(
        snapshot(api_tier="dev"), evidence, None,
        customer_subscriptions=(evidence,),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-api-entitlement-state"
    assert plan.blocking is True


def test_another_customer_api_subscription_blocks_canonical_identity_guess():
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_api", product_line="api", product_tier="dev",
    ))
    other_api = classify_subscription_payload(subscription_payload(
        "sub_api_other", product_line="api", product_tier="dev",
    ))

    plan = plan_identity_reconciliation(
        snapshot(), api_evidence, None,
        customer_subscriptions=(api_evidence, other_api),
        customer_scan_complete=True,
    )

    assert plan.action == "blocked-additional-api-subscriptions"
    assert plan.blocking is True


def test_non_api_object_in_api_column_blocks_apply():
    api_evidence = classify_subscription_payload(subscription_payload(
        "sub_web", product_line="eod", product_tier="analyst",
    ))
    user = snapshot(
        web_subscription_id=None,
        web_subscription_status=None,
        api_subscription_id="sub_web",
        api_subscription_status="active",
    )

    plan = plan_identity_reconciliation(user, None, api_evidence)

    assert plan.action == "blocked-api-column-classification"
    assert plan.blocking is True
