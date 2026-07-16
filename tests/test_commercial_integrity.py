"""Focused regression tests for commercial concurrency and billing integrity.

Stripe is always mocked.  DB-marked tests use only ``tradewave_test`` through
the shared conftest safety guard.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import importlib
import threading

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_SQL = _REPO_ROOT / "apiserver" / "schema.sql"


class _StripeList:
    def __init__(self, items):
        self._items = list(items)

    def auto_paging_iter(self):
        return iter(self._items)


@pytest.fixture(scope="module")
def commercial_schema(test_engine, _models_module):
    """Apply only additive/idempotent shared schema to the test database."""
    with test_engine.begin() as connection:
        connection.exec_driver_sql(_SCHEMA_SQL.read_text())
    _models_module.StripeCheckoutClaim.__table__.create(
        bind=test_engine, checkfirst=True,
    )


def _checkout_payload(*, price="price_dev_month", expires_offset=3600):
    return {
        "mode": "subscription",
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": "https://example.test/success",
        "cancel_url": "https://example.test/cancel",
        "client_reference_id": "user-test",
        "metadata": {"product_line": "api", "tier": "dev"},
        "subscription_data": {
            "metadata": {"product_line": "api", "tier": "dev"},
        },
        "allow_promotion_codes": True,
        "customer_email": "buyer@example.test",
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + expires_offset,
    }


@pytest.mark.unit
def test_checkout_ttl_leaves_stripe_minimum_after_lease_recovery():
    from checkout_claims import (
        CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS,
        CHECKOUT_SESSION_TTL_SECONDS,
        LEASE_SECONDS,
        STRIPE_MIN_CHECKOUT_REMAINING_SECONDS,
    )

    # Preserve at least a minute beyond Stripe's documented 30-minute minimum
    # after the original creator's lease and normal scheduling delay elapse.
    assert (
        CHECKOUT_SESSION_TTL_SECONDS
        - LEASE_SECONDS
        - CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS
        >= STRIPE_MIN_CHECKOUT_REMAINING_SECONDS
    )


@pytest.mark.unit
def test_deploy_requires_real_dedicated_portal_id_before_restart():
    generator = (
        _REPO_ROOT / "ops" / "staging" / "make_staging_secrets.sh"
    ).read_text()
    deploy = (_REPO_ROOT / "ops" / "deploy.sh").read_text()

    assert (
        "TW2_API_BILLING_PORTAL_CONFIGURATION_ID="
        "PLACEHOLDER_RUN_API_STRIPE_SEED_AND_PERSIST_BPC_ID"
    ) in generator
    check = (
        "^TW2_API_BILLING_PORTAL_CONFIGURATION_ID="
        "bpc_[A-Za-z0-9_]+$"
    )
    assert check in deploy
    assert "API_BILLING_PORTAL_CONFIGURATION_ID=.*PLACEHOLDER" in deploy
    assert deploy.index(check) < deploy.index("sync the same release to WEB")


@pytest.mark.db
def test_checkout_claim_replay_unknown_outcome_and_consumption(
    make_user, _models_module, commercial_schema,
):
    from checkout_claims import (
        CheckoutClaimBusy,
        CheckoutClaimConflict,
        complete_checkout,
        consume_checkout,
        reserve_checkout,
    )

    user = make_user()
    user_id = user.id
    first = reserve_checkout(
        user_id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    assert not first.reused

    with pytest.raises(CheckoutClaimBusy):
        reserve_checkout(
            user_id, "api", _checkout_payload(),
            session_factory=_models_module.Session,
        )

    # Simulate a worker dying after the reservation commit.  The takeover must
    # reuse the exact stored payload and idempotency key, never mint a new key.
    session = _models_module.Session.session_factory()
    try:
        row = session.get(
            _models_module.StripeCheckoutClaim,
            (user_id, "api"),
        )
        row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
    takeover = reserve_checkout(
        user_id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    assert takeover.idempotency_key == first.idempotency_key
    assert takeover.payload == first.payload

    complete_checkout(
        takeover,
        "cs_test_single_flight",
        "https://checkout.stripe.test/single-flight",
        session_factory=_models_module.Session,
    )
    replay = reserve_checkout(
        user_id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    assert replay.reused
    assert replay.session_id == "cs_test_single_flight"
    assert replay.idempotency_key == first.idempotency_key

    with pytest.raises(CheckoutClaimConflict):
        reserve_checkout(
            user_id,
            "api",
            _checkout_payload(price="price_pro_month"),
            session_factory=_models_module.Session,
        )

    session = _models_module.Session.session_factory()
    try:
        assert consume_checkout(
            session, user_id, "api", "cs_test_single_flight",
        )
        session.commit()
    finally:
        session.close()
    # A consumed but unexpired claim is still authoritative.  A stale route
    # request may have loaded its user before the webhook committed; it must
    # not mint a second Checkout session in that window.
    after_consumption = reserve_checkout(
        user_id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    assert after_consumption.reused
    assert after_consumption.idempotency_key == first.idempotency_key
    assert after_consumption.session_id == "cs_test_single_flight"
    with pytest.raises(CheckoutClaimConflict):
        reserve_checkout(
            user_id, "api", _checkout_payload(price="price_pro_month"),
            session_factory=_models_module.Session,
        )


@pytest.mark.db
def test_stale_route_snapshot_cannot_replace_consumed_unexpired_checkout(
    make_user, _models_module, commercial_schema,
):
    """Reproduce the route-precheck/webhook-commit ordering explicitly."""
    from checkout_claims import complete_checkout, consume_checkout, reserve_checkout

    user = make_user()
    reservation = reserve_checkout(
        user.id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    complete_checkout(
        reservation,
        "cs_test_stale_route",
        "https://checkout.stripe.test/stale-route",
        session_factory=_models_module.Session,
    )

    # The route loaded the user before the webhook transaction completed.
    stale_route_session = _models_module.Session.session_factory()
    webhook_session = _models_module.Session.session_factory()
    try:
        stale_user = stale_route_session.get(_models_module.User, user.id)
        assert stale_user is not None
        assert consume_checkout(
            webhook_session, user.id, "api", "cs_test_stale_route",
        )
        webhook_session.commit()

        replay = reserve_checkout(
            stale_user.id, "api", _checkout_payload(),
            session_factory=_models_module.Session,
        )
    finally:
        webhook_session.close()
        stale_route_session.close()

    assert replay.reused
    assert replay.idempotency_key == reservation.idempotency_key
    assert replay.session_id == "cs_test_stale_route"


@pytest.mark.db
def test_checkout_claim_allows_one_concurrent_creator(
    make_user, _models_module, commercial_schema,
):
    from checkout_claims import CheckoutClaimBusy, reserve_checkout

    user = make_user()
    user_id = user.id
    barrier = threading.Barrier(2)
    acquired = []
    busy = []
    failures = []

    def worker():
        try:
            barrier.wait(timeout=5)
            acquired.append(reserve_checkout(
                user_id, "eod", _checkout_payload(price="price_eod"),
                session_factory=_models_module.Session,
            ))
        except CheckoutClaimBusy as exc:
            busy.append(exc)
        except Exception as exc:  # surfaced below with the original repr
            failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert failures == []
    assert len(acquired) == 1
    assert len(busy) == 1


@pytest.mark.db
def test_unknown_checkout_outcome_near_expiry_is_not_reissued(
    make_user, _models_module, commercial_schema,
):
    from checkout_claims import (
        CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS,
        STRIPE_MIN_CHECKOUT_REMAINING_SECONDS,
        CheckoutClaimBusy,
        CheckoutClaimDeferred,
        reserve_checkout,
    )

    user = make_user()
    reservation = reserve_checkout(
        user.id, "api", _checkout_payload(),
        session_factory=_models_module.Session,
    )
    session = _models_module.Session.session_factory()
    try:
        row = session.get(
            _models_module.StripeCheckoutClaim,
            (user.id, "api"),
        )
        near_expiry = datetime.now(timezone.utc) + timedelta(
            seconds=(
                STRIPE_MIN_CHECKOUT_REMAINING_SECONDS
                + CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS
                - 5
            ),
        )
        stored_payload = dict(row.request_payload)
        stored_payload["expires_at"] = int(near_expiry.timestamp())
        row.request_payload = stored_payload
        row.expires_at = near_expiry
        row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    with pytest.raises(CheckoutClaimDeferred, match="unresolved"):
        reserve_checkout(
            user.id, "api", _checkout_payload(),
            session_factory=_models_module.Session,
        )

    session = _models_module.Session.session_factory()
    try:
        row = session.get(
            _models_module.StripeCheckoutClaim,
            (user.id, "api"),
        )
        assert row.idempotency_key == reservation.idempotency_key
        assert row.stripe_session_id is None
    finally:
        session.close()


@pytest.mark.db
def test_promotion_fallback_replay_recovers_completed_plain_session(
    make_user, _models_module, commercial_schema,
):
    from checkout_claims import (
        complete_checkout,
        replace_checkout_payload,
        reserve_checkout,
    )

    user = make_user()
    promotional_payload = _checkout_payload()
    promotional_payload["discounts"] = [{"promotion_code": "promo_founder"}]
    reservation = reserve_checkout(
        user.id, "api", promotional_payload,
        session_factory=_models_module.Session,
    )
    plain_payload = dict(promotional_payload)
    plain_payload.pop("discounts")
    fallback = replace_checkout_payload(
        reservation, plain_payload,
        session_factory=_models_module.Session,
    )
    assert fallback.idempotency_key != reservation.idempotency_key
    assert fallback.request_fingerprint == reservation.request_fingerprint
    assert fallback.payload == plain_payload

    complete_checkout(
        fallback,
        "cs_test_plain_fallback",
        "https://checkout.stripe.test/plain-fallback",
        session_factory=_models_module.Session,
    )

    # Simulate the 303 response being lost and the browser posting the original
    # promotion-bearing form again.
    replay = reserve_checkout(
        user.id, "api", promotional_payload,
        session_factory=_models_module.Session,
    )
    assert replay.reused
    assert replay.idempotency_key == fallback.idempotency_key
    assert replay.payload == plain_payload
    assert replay.session_id == "cs_test_plain_fallback"


@pytest.mark.db
def test_api_key_cap_is_atomic_under_concurrency(
    make_user, commercial_schema,
):
    from api_portal import keystore

    user = make_user()
    barrier = threading.Barrier(2)
    created = []
    limited = []
    failures = []

    def worker(index):
        try:
            barrier.wait(timeout=5)
            created.append(keystore.create_key(
                user.id, f"key-{index}", max_keys=1,
            ))
        except keystore.KeyLimitReached as exc:
            limited.append(exc)
        except Exception as exc:
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert failures == []
    assert len(created) == 1
    assert len(limited) == 1
    assert keystore.count_active_keys(user.id) == 1


@pytest.mark.db
def test_api_key_rotation_rolls_back_insert_if_revoke_path_fails(
    make_user, commercial_schema, monkeypatch,
):
    from api_portal import keystore

    user = make_user()
    _raw, old = keystore.create_key(user.id, "old", max_keys=1)
    original_insert = keystore._insert_key

    def insert_then_fail(*args, **kwargs):
        original_insert(*args, **kwargs)
        raise RuntimeError("forced failure after replacement insert")

    monkeypatch.setattr(keystore, "_insert_key", insert_then_fail)
    with pytest.raises(RuntimeError, match="forced failure"):
        keystore.rotate_key(user.id, old["id"])

    assert keystore.count_active_keys(user.id) == 1
    fresh = keystore.get_key(user.id, old["id"])
    assert fresh["revoked_at"] is None


def _api_prices():
    from apiserver import tiers

    prices = []
    for tier in ("dev", "pro", "business"):
        for interval, amount_key in (
            ("month", "price_monthly"),
            ("year", "price_annual"),
        ):
            prices.append(SimpleNamespace(
                id=f"price_{tier}_{interval}",
                product={
                    "id": f"prod_{tier}",
                    "metadata": {"product_line": "api", "tier": tier},
                },
                recurring={"interval": interval, "interval_count": 1},
                currency="usd",
                unit_amount=tiers.API_TIERS[tier][amount_key] * 100,
                metadata={
                    "product_line": "api", "tier": tier,
                    "interval": interval,
                },
            ))
    return prices


@pytest.mark.unit
def test_api_price_catalog_accepts_only_exact_complete_catalog(monkeypatch):
    billing = importlib.import_module("api_portal.routes_billing")
    prices = _api_prices()
    monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
    monkeypatch.setattr(
        billing.stripe.Price,
        "list",
        staticmethod(lambda **_kwargs: _StripeList(prices)),
    )
    billing._price_cache.clear()

    billing._refresh_price_cache()

    assert len(billing._price_cache) == 6


@pytest.mark.unit
@pytest.mark.parametrize(
    "secret,publishable,expected",
    [
        ("", "", False),
        ("PLACEHOLDER", "pk_test_value", False),
        ("sk_test_value", "PLACEHOLDER", False),
        ("sk_test_value", "pk_live_value", False),
        ("sk_live_value", "pk_test_value", False),
        ("sk_test_value", "pk_test_value", True),
        ("sk_live_value", "pk_live_value", True),
    ],
)
def test_stripe_configuration_requires_complete_mode_matched_keys(
    monkeypatch, secret, publishable, expected,
):
    app_module = importlib.import_module("app")
    billing = importlib.import_module("api_portal.routes_billing")
    monkeypatch.setattr(app_module.config, "STRIPE_SECRET_KEY", secret)
    monkeypatch.setattr(app_module.config, "STRIPE_PUBLISHABLE_KEY", publishable)

    assert app_module._stripe_configured() is expected
    assert billing._stripe_configured() is expected


@pytest.mark.unit
def test_eod_checkout_refuses_subscription_without_customer_identity(monkeypatch):
    app_module = importlib.import_module("app")
    user = SimpleNamespace(
        id="web-user",
        tier="explorer",
        stripe_customer_id=None,
        stripe_subscription_id="sub_web_orphaned",
    )
    checkout_calls = []
    monkeypatch.setattr(app_module, "_stripe_configured", lambda: True)
    monkeypatch.setattr(app_module, "_price_id_for", lambda *_args: "price_eod")
    monkeypatch.setattr(app_module, "get_current_user", lambda: user)
    monkeypatch.setattr(app_module, "parse_ga_client_id", lambda _request: None)
    monkeypatch.setattr(
        app_module.stripe.checkout.Session,
        "create",
        staticmethod(lambda **kwargs: checkout_calls.append(kwargs)),
    )

    with app_module.app.test_request_context(
        "/api/stripe/create-checkout?tier=navigator&period=monthly",
    ):
        response, status = app_module.stripe_create_checkout.__wrapped__()

    assert status == 503
    assert response.get_json()["error"] == "subscription_identity_incomplete"
    assert checkout_calls == []


@pytest.mark.unit
@pytest.mark.parametrize("defect", ["duplicate", "amount", "currency", "interval", "metadata"])
def test_api_price_catalog_fails_closed_on_drift(monkeypatch, defect):
    billing = importlib.import_module("api_portal.routes_billing")
    prices = _api_prices()
    if defect == "duplicate":
        duplicate = SimpleNamespace(**vars(prices[0]))
        duplicate.id = "price_duplicate"
        prices.append(duplicate)
    elif defect == "amount":
        prices[0].unit_amount += 1
    elif defect == "currency":
        prices[0].currency = "eur"
    elif defect == "interval":
        prices[0].recurring = {"interval": "week", "interval_count": 1}
    elif defect == "metadata":
        prices[0].metadata = {
            "product_line": "api", "tier": "pro", "interval": "month",
        }
    monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
    monkeypatch.setattr(
        billing.stripe.Price,
        "list",
        staticmethod(lambda **_kwargs: _StripeList(prices)),
    )
    billing._price_cache.clear()

    with pytest.raises(billing.PriceCatalogError):
        billing._refresh_price_cache()

    assert billing._price_cache == {}


@pytest.mark.unit
def test_unrelated_newer_subscription_cannot_replace_tracked_identity():
    app_module = importlib.import_module("app")
    candidate = {
        "id": "sub_unrelated_newer",
        "status": "active",
        "created": 999999,
    }

    assert not app_module._created_subscription_can_replace(
        "customer.subscription.created",
        "sub_current",
        "",
        candidate,
    )
    assert app_module._created_subscription_can_replace(
        "customer.subscription.created",
        "sub_current",
        "sub_current",
        candidate,
    )


class _Object(dict):
    __getattr__ = dict.__getitem__

    def to_dict(self):
        return dict(self)

    def to_dict_recursive(self):
        return dict(self)


def _portal_config(config_id, products, *, is_default=False, purpose=True):
    return _Object({
        "id": config_id,
        "active": True,
        "is_default": is_default,
        "livemode": False,
        "metadata": {
            "product_line": "api",
            "tw2_purpose": "api_subscription_management" if purpose else "other",
        },
        "features": {
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
            "subscription_cancel": {
                "enabled": True,
                "mode": "at_period_end",
                "proration_behavior": "none",
            },
            "subscription_update": {
                "enabled": True,
                "default_allowed_updates": ["price", "promotion_code"],
                "proration_behavior": "create_prorations",
                "products": products,
            },
        },
    })


@pytest.mark.unit
def test_runtime_validates_dedicated_portal_contains_exact_api_catalog(monkeypatch):
    billing = importlib.import_module("api_portal.routes_billing")
    prices = _api_prices()
    billing._price_cache.clear()
    for price in prices:
        interval = price.recurring["interval"]
        tier = price.product["metadata"]["tier"]
        billing._price_cache[(tier, interval)] = price
    portal_products = [
        {
            "product": f"prod_{tier}",
            "prices": [f"price_{tier}_month", f"price_{tier}_year"],
        }
        for tier in ("dev", "pro", "business")
    ]
    monkeypatch.setattr(
        billing.config,
        "API_BILLING_PORTAL_CONFIGURATION_ID",
        "bpc_api_test",
    )
    monkeypatch.setattr(billing.config, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        billing.stripe.billing_portal.Configuration,
        "retrieve",
        staticmethod(lambda _configuration_id: _portal_config(
            "bpc_api_test", portal_products,
        )),
    )

    assert billing._validated_portal_configuration_id() == "bpc_api_test"

    portal_products[0] = {
        "product": "prod_dev",
        "prices": ["price_dev_month"],
    }
    with pytest.raises(billing.PortalConfigurationError):
        billing._validated_portal_configuration_id()


@pytest.mark.unit
@pytest.mark.parametrize(
    "feature,path,value",
    [
        ("subscription_update", "proration_behavior", "none"),
        ("subscription_cancel", "mode", "immediately"),
        ("subscription_cancel", "proration_behavior", "create_prorations"),
    ],
)
def test_runtime_rejects_portal_billing_semantic_drift(
    monkeypatch, feature, path, value,
):
    billing = importlib.import_module("api_portal.routes_billing")
    prices = _api_prices()
    billing._price_cache.clear()
    for price in prices:
        billing._price_cache[
            (price.product["metadata"]["tier"], price.recurring["interval"])
        ] = price
    portal_products = [
        {
            "product": f"prod_{tier}",
            "prices": [f"price_{tier}_month", f"price_{tier}_year"],
        }
        for tier in ("dev", "pro", "business")
    ]
    portal = _portal_config("bpc_api_test", portal_products)
    portal["features"][feature][path] = value
    monkeypatch.setattr(
        billing.config, "API_BILLING_PORTAL_CONFIGURATION_ID", "bpc_api_test",
    )
    monkeypatch.setattr(billing.config, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        billing.stripe.billing_portal.Configuration,
        "retrieve",
        staticmethod(lambda _configuration_id: portal),
    )

    with pytest.raises(billing.PortalConfigurationError):
        billing._validated_portal_configuration_id()


@pytest.mark.unit
def test_portal_seeder_matcher_rejects_cancellation_proration_drift():
    seeder = importlib.import_module("api_portal.create_api_products")
    products = [{"product": "prod_dev", "prices": ["price_dev_month"]}]
    portal = _portal_config("bpc_api_test", products)
    assert seeder._portal_configuration_matches(portal, products)

    portal["features"]["subscription_cancel"]["proration_behavior"] = (
        "create_prorations"
    )
    assert not seeder._portal_configuration_matches(portal, products)


@pytest.mark.unit
def test_portal_seeder_is_idempotent_and_dedicated(monkeypatch):
    seeder = importlib.import_module("api_portal.create_api_products")
    monkeypatch.setenv(
        seeder.PORTAL_CONFIGURATION_ENV,
        "PLACEHOLDER_RUN_API_STRIPE_SEED_AND_PERSIST_BPC_ID",
    )
    products = {
        tier: SimpleNamespace(id=f"prod_{tier}")
        for tier in seeder.PAID_TIERS
    }
    prices = {
        tier: {
            "month": SimpleNamespace(id=f"price_{tier}_month"),
            "year": SimpleNamespace(id=f"price_{tier}_year"),
        }
        for tier in seeder.PAID_TIERS
    }
    state = {"configuration": None, "creates": 0, "modifies": 0}

    def list_configurations(**_kwargs):
        items = [state["configuration"]] if state["configuration"] else []
        return _StripeList(items)

    def create_configuration(**kwargs):
        state["creates"] += 1
        state["configuration"] = _portal_config(
            "bpc_api_dedicated",
            kwargs["features"]["subscription_update"]["products"],
        )
        return state["configuration"]

    def modify_configuration(configuration_id, **kwargs):
        state["modifies"] += 1
        state["configuration"] = _portal_config(
            configuration_id,
            kwargs["features"]["subscription_update"]["products"],
        )
        return state["configuration"]

    configuration_api = SimpleNamespace(
        list=list_configurations,
        create=create_configuration,
        modify=modify_configuration,
        retrieve=lambda _configuration_id: state["configuration"],
    )
    fake_stripe = SimpleNamespace(
        billing_portal=SimpleNamespace(Configuration=configuration_api),
    )

    first = seeder._ensure_api_portal_configuration(
        fake_stripe, products, prices,
    )
    second = seeder._ensure_api_portal_configuration(
        fake_stripe, products, prices,
    )

    assert first.id == second.id == "bpc_api_dedicated"
    assert not first["is_default"]
    assert state == {
        "configuration": state["configuration"],
        "creates": 1,
        "modifies": 0,
    }


@pytest.mark.unit
def test_portal_seeder_refuses_shared_default(monkeypatch):
    seeder = importlib.import_module("api_portal.create_api_products")
    monkeypatch.setenv(
        seeder.PORTAL_CONFIGURATION_ENV,
        "bpc_shared_default",
    )
    shared = _portal_config(
        "bpc_shared_default", [], is_default=True,
    )
    fake_stripe = SimpleNamespace(
        billing_portal=SimpleNamespace(
            Configuration=SimpleNamespace(retrieve=lambda _id: shared),
        ),
    )

    with pytest.raises(RuntimeError, match="shared default"):
        seeder._find_api_portal_configuration(fake_stripe)


@pytest.mark.unit
def test_portal_seeder_refuses_duplicate_active_tier_products():
    seeder = importlib.import_module("api_portal.create_api_products")
    products = [
        SimpleNamespace(
            id=f"prod_dev_{index}",
            metadata=_Object({"product_line": "api", "tier": "dev"}),
        )
        for index in range(2)
    ]
    fake_stripe = SimpleNamespace(
        Product=SimpleNamespace(
            list=lambda **_kwargs: _StripeList(products),
        ),
    )

    with pytest.raises(RuntimeError, match="multiple active API products"):
        seeder._find_product(fake_stripe, "dev")


@pytest.mark.unit
def test_live_seed_banner_discloses_portal_mutation():
    seeder = importlib.import_module("api_portal.create_api_products")

    banner = seeder._live_banner()

    assert "Dedicated API Billing Portal configuration" in banner
    assert "Create or update" in banner
    assert seeder.PORTAL_CONFIGURATION_ENV in banner


@pytest.mark.unit
@pytest.mark.parametrize(
    "configuration_id",
    ["", "PLACEHOLDER_RUN_API_SEED", "bpc_PLACEHOLDER_NOT_READY"],
)
def test_missing_api_portal_config_fails_manage_only(
    monkeypatch, configuration_id,
):
    app_module = importlib.import_module("app")
    billing = importlib.import_module("api_portal.routes_billing")
    user = SimpleNamespace(id="api-user", stripe_customer_id="cus_api")
    portal_calls = []
    monkeypatch.setattr(billing, "get_current_user", lambda: user)
    monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
    monkeypatch.setattr(
        billing.config, "API_BILLING_PORTAL_CONFIGURATION_ID", configuration_id,
    )
    monkeypatch.setattr(
        billing.stripe.Customer,
        "retrieve",
        staticmethod(lambda _customer_id: SimpleNamespace(deleted=False)),
    )
    monkeypatch.setattr(
        billing.stripe.billing_portal.Session,
        "create",
        staticmethod(lambda **kwargs: portal_calls.append(kwargs)),
    )

    with app_module.app.test_request_context("/account/api/billing/manage"):
        response, status = billing.billing_manage.__wrapped__()

    assert status == 503
    assert response.get_json()["error"] == "billing_portal_misconfigured"
    assert portal_calls == []


@pytest.mark.unit
def test_missing_api_portal_config_does_not_block_eod_portal(monkeypatch):
    app_module = importlib.import_module("app")
    user = SimpleNamespace(id="web-user", stripe_customer_id="cus_web")
    portal_calls = []
    monkeypatch.setenv("TW2_PUBLIC_HOST", "tw2.trxstat.com")
    monkeypatch.setattr(app_module, "get_current_user", lambda: user)
    monkeypatch.setattr(app_module, "_stripe_configured", lambda: True)
    monkeypatch.setattr(
        app_module.config, "API_BILLING_PORTAL_CONFIGURATION_ID", "",
    )
    monkeypatch.setattr(
        app_module.stripe.Customer,
        "retrieve",
        staticmethod(lambda _customer_id: SimpleNamespace(deleted=False)),
    )

    def create_portal(**kwargs):
        portal_calls.append(kwargs)
        return SimpleNamespace(url="https://billing.stripe.test/eod")

    monkeypatch.setattr(
        app_module.stripe.billing_portal.Session,
        "create",
        staticmethod(create_portal),
    )

    with app_module.app.test_request_context("/account/manage-subscription"):
        response = app_module.manage_subscription.__wrapped__()

    assert response.status_code == 303
    assert response.location == "https://billing.stripe.test/eod"
    assert portal_calls == [{
        "customer": "cus_web",
        "return_url": "https://tw2.trxstat.com/account",
    }]


@pytest.mark.unit
def test_live_catalog_seed_keeps_double_gate(monkeypatch):
    seeder = importlib.import_module("api_portal.create_api_products")
    monkeypatch.setattr(seeder.config, "STRIPE_SECRET_KEY", "sk_live_fake")
    monkeypatch.setattr(seeder.sys, "argv", ["create_api_products.py", "--live"])
    monkeypatch.delenv("TW2_CONFIRM_LIVE_SEED", raising=False)
    with pytest.raises(SystemExit, match="TW2_CONFIRM_LIVE_SEED=1"):
        seeder._require_seed_key()

    monkeypatch.setenv("TW2_CONFIRM_LIVE_SEED", "1")
    monkeypatch.setattr(seeder.sys.stdin, "isatty", lambda: False)
    assert seeder._require_seed_key() == "sk_live_fake"
