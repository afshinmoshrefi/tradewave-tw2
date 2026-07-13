"""
Coverage for the 2026-06-10 web-funnel fixes in /home/flask/web/app.py:

  1. /stripe/success now accepts payment_status == 'no_payment_required'
     for 7-day-trial Checkout sessions, but ONLY after the session's
     subscription is verified server-side as trialing/active
     (`_trial_session_subscription_ok`).
  2. /api/stripe/create-checkout refuses to mint a second subscription for
     a customer who already has an active/trialing EOD-line subscription
     (`_existing_eod_subscription` feeds the Billing-Portal redirect).
  3. /pricing carries an affiliate ?code= / ?via= through the /#pricing
     redirect and sets the tw_ref attribution cookie for active affiliates.

Stripe is monkeypatched throughout - no network. The /pricing tests use
the Flask test client against the tradewave_test DB (db-marked).
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
import stripe


class _FakeList:
    """Mirror of the stripe list-object stub used in test_affiliate.py."""

    def __init__(self, items):
        self._items = items

    def auto_paging_iter(self):
        return iter(self._items)


@pytest.fixture
def app_module():
    """Lazy import - avoid pulling Flask app side effects at collection."""
    return importlib.import_module("app")


@pytest.fixture
def api_billing_module(app_module):
    """The parent app registers and imports the API billing blueprint."""
    return importlib.import_module("api_portal.routes_billing")


# ---------------------------------------------------------------------
# 1. Trial sessions: _trial_session_subscription_ok + the success gate
# ---------------------------------------------------------------------

@pytest.mark.unit
class TestTrialSessionVerification:
    def _patch_retrieve(self, monkeypatch, status=None, raises=False):
        def _retrieve(sub_id):
            if raises:
                raise stripe.error.InvalidRequestError("no such subscription", None)
            return SimpleNamespace(id=sub_id, status=status)
        monkeypatch.setattr(stripe.Subscription, "retrieve", staticmethod(_retrieve))

    def test_trialing_subscription_accepted(self, app_module, monkeypatch):
        self._patch_retrieve(monkeypatch, status="trialing")
        sess_d = {"subscription": {"id": "sub_1", "status": "trialing"}}
        assert app_module._trial_session_subscription_ok(sess_d) is True

    def test_active_subscription_accepted(self, app_module, monkeypatch):
        self._patch_retrieve(monkeypatch, status="active")
        sess_d = {"subscription": "sub_1"}  # unexpanded string id shape
        assert app_module._trial_session_subscription_ok(sess_d) is True

    def test_other_statuses_rejected(self, app_module, monkeypatch):
        for bad in ("incomplete", "incomplete_expired", "canceled",
                    "past_due", "unpaid", None):
            self._patch_retrieve(monkeypatch, status=bad)
            sess_d = {"subscription": {"id": "sub_1"}}
            assert app_module._trial_session_subscription_ok(sess_d) is False, \
                f"subscription status {bad!r} must NOT be accepted"

    def test_session_without_subscription_rejected(self, app_module, monkeypatch):
        # No Stripe call should even be attempted; patch to raise to prove it.
        self._patch_retrieve(monkeypatch, raises=True)
        assert app_module._trial_session_subscription_ok({}) is False
        assert app_module._trial_session_subscription_ok({"subscription": None}) is False

    def test_retrieve_failure_rejected(self, app_module, monkeypatch):
        """Server-side verification is mandatory: if Stripe can't confirm the
        subscription, the session is NOT accepted (fail closed)."""
        self._patch_retrieve(monkeypatch, raises=True)
        sess_d = {"subscription": {"id": "sub_gone", "status": "trialing"}}
        assert app_module._trial_session_subscription_ok(sess_d) is False

    def test_lying_session_status_ignored(self, app_module, monkeypatch):
        """The expanded session payload claiming 'trialing' is irrelevant -
        only the fresh Subscription.retrieve answer counts."""
        self._patch_retrieve(monkeypatch, status="incomplete")
        sess_d = {"subscription": {"id": "sub_1", "status": "trialing"}}
        assert app_module._trial_session_subscription_ok(sess_d) is False


@pytest.mark.unit
class TestStripeSuccessPaymentGate:
    """Mirror the gate in stripe_success():
    refuse unless payment_status == 'paid' OR (== 'no_payment_required'
    AND the subscription verifies trialing/active)."""

    def _gate_allows(self, payment_status, trial_ok):
        is_trial = payment_status == "no_payment_required" and trial_ok
        return not (payment_status != "paid" and not is_trial)

    def test_paid_always_allowed(self):
        assert self._gate_allows("paid", trial_ok=False)

    def test_trial_allowed_only_with_verified_subscription(self):
        assert self._gate_allows("no_payment_required", trial_ok=True)
        assert not self._gate_allows("no_payment_required", trial_ok=False)

    def test_other_statuses_always_blocked(self):
        for bad in ("unpaid", "open", None):
            assert not self._gate_allows(bad, trial_ok=True)
            assert not self._gate_allows(bad, trial_ok=False)


# ---------------------------------------------------------------------
# 2. Double-subscription guard: _existing_eod_subscription
# ---------------------------------------------------------------------

@pytest.mark.unit
class TestExistingEodSubscription:
    EOD_PRICE = "price_eod_analyst_month"

    @pytest.fixture(autouse=True)
    def _eod_price_cache(self, app_module, monkeypatch):
        """Pre-fill the price cache so _tier_period_for_price resolves the
        EOD price offline (an empty cache would trigger a live refresh)."""
        monkeypatch.setitem(
            app_module._price_cache, ("analyst", "monthly"),
            SimpleNamespace(id=self.EOD_PRICE),
        )
        monkeypatch.setitem(
            app_module._price_product_metadata_cache,
            "price_api_dev",
            {"product_line": "api", "tier": "dev"},
        )

    def _sub(self, sub_id="sub_eod_1", price_id=None, status="active",
             item_id="si_1"):
        return {
            "id": sub_id,
            "status": status,
            "items": {"data": [{"id": item_id,
                                "price": {"id": price_id or self.EOD_PRICE}}]},
        }

    def _patch_list(self, monkeypatch, by_status):
        """by_status: dict status -> list of subscription dicts."""
        def _list(**kw):
            return _FakeList(by_status.get(kw.get("status"), []))
        monkeypatch.setattr(stripe.Subscription, "list", staticmethod(_list))

    def test_active_eod_subscription_found(self, app_module, monkeypatch):
        self._patch_list(monkeypatch, {"active": [self._sub()]})
        sub_id, item_id, status = app_module._existing_eod_subscription("cus_1")
        assert (sub_id, item_id, status) == ("sub_eod_1", "si_1", "active")

    def test_trialing_eod_subscription_found(self, app_module, monkeypatch):
        self._patch_list(monkeypatch, {
            "trialing": [self._sub(sub_id="sub_trial", status="trialing")],
        })
        sub_id, item_id, status = app_module._existing_eod_subscription("cus_1")
        assert (sub_id, item_id, status) == ("sub_trial", "si_1", "trialing")

    def test_no_subscriptions_returns_empty(self, app_module, monkeypatch):
        self._patch_list(monkeypatch, {})
        assert app_module._existing_eod_subscription("cus_1") == (None, None, None)

    def test_foreign_line_subscription_ignored(self, app_module, monkeypatch):
        """A non-EOD subscription (TW1 legacy / API line) must NOT trip the
        guard - those customers may still buy an EOD plan."""
        self._patch_list(monkeypatch, {
            "active": [self._sub(sub_id="sub_api", price_id="price_api_dev")],
        })
        assert app_module._existing_eod_subscription("cus_1") == (None, None, None)

    def test_stored_legacy_web_subscription_found_without_price_metadata(
        self, app_module, monkeypatch,
    ):
        self._patch_list(monkeypatch, {
            "active": [self._sub(
                sub_id="sub_legacy_web",
                price_id="price_legacy_without_metadata",
                item_id="si_legacy",
            )],
        })
        found = app_module._existing_eod_subscription(
            "cus_1", stored_web_subscription_id="sub_legacy_web",
        )
        assert found == ("sub_legacy_web", "si_legacy", "active")

    def test_eod_found_among_mixed_subscriptions(self, app_module, monkeypatch):
        self._patch_list(monkeypatch, {
            "active": [
                self._sub(sub_id="sub_api", price_id="price_api_dev", item_id="si_a"),
                self._sub(sub_id="sub_eod_2", item_id="si_b"),
            ],
        })
        sub_id, item_id, status = app_module._existing_eod_subscription("cus_1")
        assert (sub_id, item_id) == ("sub_eod_2", "si_b")

    def test_stripe_error_fails_closed(self, app_module, monkeypatch):
        """A Stripe hiccup must not be mistaken for no current subscription."""
        def _boom(**kw):
            raise stripe.error.APIConnectionError("stripe down")
        monkeypatch.setattr(stripe.Subscription, "list", staticmethod(_boom))
        with pytest.raises(stripe.error.APIConnectionError):
            app_module._existing_eod_subscription("cus_1")


@pytest.mark.unit
class TestExistingApiSubscription:
    @staticmethod
    def _sub(sub_id="sub_api_1", status="active", line="api"):
        return {
            "id": sub_id,
            "status": status,
            "metadata": {},
            "items": {"data": [{
                "id": "si_api_1",
                "price": {
                    "id": "price_api_1",
                    "product": {"metadata": {"product_line": line}},
                },
            }]},
        }

    @staticmethod
    def _patch_list(monkeypatch, by_status):
        def _list(**kwargs):
            return _FakeList(by_status.get(kwargs.get("status"), []))
        monkeypatch.setattr(stripe.Subscription, "list", staticmethod(_list))

    def test_active_api_subscription_found(
        self, api_billing_module, monkeypatch,
    ):
        self._patch_list(monkeypatch, {"active": [self._sub()]})
        assert api_billing_module._existing_api_subscription("cus_1") == (
            "sub_api_1", "active",
        )

    def test_eod_subscription_ignored(
        self, api_billing_module, monkeypatch,
    ):
        self._patch_list(monkeypatch, {
            "active": [self._sub(sub_id="sub_eod", line="eod")],
        })
        assert api_billing_module._existing_api_subscription("cus_1") == (
            None, None,
        )

    def test_stored_legacy_api_subscription_found_without_metadata(
        self, api_billing_module, monkeypatch,
    ):
        legacy = self._sub(
            sub_id="sub_api_legacy", status="past_due", line="",
        )
        self._patch_list(monkeypatch, {"past_due": [legacy]})
        found = api_billing_module._existing_api_subscription(
            "cus_1", stored_api_subscription_id="sub_api_legacy",
        )
        assert found == ("sub_api_legacy", "past_due")

    def test_stripe_error_fails_closed(
        self, api_billing_module, monkeypatch,
    ):
        def _boom(**kwargs):
            raise stripe.error.APIConnectionError("stripe down")
        monkeypatch.setattr(stripe.Subscription, "list", staticmethod(_boom))
        with pytest.raises(stripe.error.APIConnectionError):
            api_billing_module._existing_api_subscription("cus_1")


@pytest.mark.unit
class TestSubscriptionProductTarget:
    def test_price_wins_over_stale_subscription_metadata(
        self, app_module, monkeypatch,
    ):
        monkeypatch.setattr(
            app_module, "_api_tier_for_price", lambda _price_id: None,
        )
        monkeypatch.setattr(
            app_module,
            "_tier_period_for_price",
            lambda _price_id: ("strategist", "yearly"),
        )
        assert app_module._subscription_product_target(
            "price_current",
            {
                "product_line": "eod",
                "tier": "navigator",
                "period": "monthly",
            },
        ) == ("eod", "strategist", "yearly")

    def test_exact_price_lookup_failure_remains_retryable(
        self, app_module, monkeypatch,
    ):
        def _fail(_price_id):
            raise stripe.error.APIConnectionError("stripe unavailable")

        monkeypatch.setattr(app_module, "_api_tier_for_price", _fail)
        with pytest.raises(stripe.error.APIConnectionError):
            app_module._subscription_product_target(
                "price_unavailable",
                {
                    "product_line": "api",
                    "tier": "business",
                },
            )

    def test_metadata_is_fallback_only_without_price_id(self, app_module):
        assert app_module._subscription_product_target(
            None,
            {
                "product_line": "api",
                "tier": "business",
            },
        ) == ("api", "business", None)

# ---------------------------------------------------------------------
# 3. /pricing affiliate param carry-through (Flask test client + test DB)
# ---------------------------------------------------------------------

@pytest.mark.db
class TestPricingAffiliateRedirect:
    @pytest.fixture(autouse=True)
    def _ensure_affiliates_table(self, test_engine, _models_module):
        """The operator-loaded tradewave_test snapshot can predate the
        affiliate feature; create the table from the model if missing
        (idempotent, test DB only)."""
        _models_module.Affiliate.__table__.create(bind=test_engine, checkfirst=True)

    @pytest.fixture
    def client(self, app_module, _models_module):
        app_module.DBSession = _models_module.Session
        app_module.app.config["TESTING"] = True
        return app_module.app.test_client()

    @pytest.fixture
    def active_affiliate(self, db_session, _models_module):
        aff = _models_module.Affiliate(
            code="ANNE", name="Anne", email="anne@example.com",
            discount_pct=20, commission_pct=30, status="active",
        )
        db_session.add(aff)
        db_session.commit()
        yield aff
        db_session.delete(aff)
        db_session.commit()

    def test_plain_pricing_redirects_unchanged(self, client):
        r = client.get("/pricing")
        assert r.status_code == 302
        assert r.headers["Location"] == "/#pricing"
        assert "tw_ref" not in (r.headers.get("Set-Cookie") or "")

    def test_active_code_carried_and_cookie_set(self, client, active_affiliate):
        r = client.get("/pricing?code=anne")  # lowercase: normalized like /join
        assert r.status_code == 302
        assert r.headers["Location"] == "/?code=ANNE#pricing"
        cookie = r.headers.get("Set-Cookie") or ""
        assert "tw_ref=ANNE" in cookie
        assert "SameSite=Lax" in cookie

    def test_via_param_also_accepted(self, client, active_affiliate):
        r = client.get("/pricing?via=ANNE")
        assert r.status_code == 302
        assert r.headers["Location"] == "/?code=ANNE#pricing"

    def test_unknown_code_redirects_plain(self, client):
        r = client.get("/pricing?code=NOSUCH")
        assert r.status_code == 302
        assert r.headers["Location"] == "/#pricing"
        assert "tw_ref" not in (r.headers.get("Set-Cookie") or "")

    def test_inactive_affiliate_redirects_plain(self, client, db_session,
                                                _models_module):
        aff = _models_module.Affiliate(
            code="PAUSED1", name="P", email="p@example.com",
            discount_pct=10, commission_pct=20, status="paused",
        )
        db_session.add(aff)
        db_session.commit()
        try:
            r = client.get("/pricing?code=PAUSED1")
            assert r.status_code == 302
            assert r.headers["Location"] == "/#pricing"
            assert "tw_ref" not in (r.headers.get("Set-Cookie") or "")
        finally:
            db_session.delete(aff)
            db_session.commit()

    def test_malformed_code_redirects_plain(self, client):
        r = client.get("/pricing?code=%2Fetc%2Fpasswd")
        assert r.status_code == 302
        assert r.headers["Location"] == "/#pricing"
