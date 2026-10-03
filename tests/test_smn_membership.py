"""SMN identity/access and isolated payment invariants on real PostgreSQL."""
from datetime import timedelta
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

from flask import Flask
import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import models as m
import smn_membership as membership
import smn_billing as billing
import smn_reader_authorization as auth


def offer(**updates):
    values = dict(mode="paid", currency="usd", monthly_amount=1000, annual_mode="discount",
                  annual_discount_bps=5000, annual_amount=None, trial_days=28, intervals=["month", "year"])
    values.update(updates)
    return values


def provider_user(**updates):
    values = dict(id="user_" + uuid.uuid4().hex, email=uuid.uuid4().hex + "@example.test",
                  email_verified=True, first_name="Reader", last_name="Test")
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("changes", [dict(trial_days=-1), dict(trial_days=366), dict(trial_days=1.5),
    dict(monthly_amount=True), dict(monthly_amount=-1), dict(annual_discount_bps=10000),
    dict(intervals=[]), dict(intervals=["week"]), dict(currency="xxx"), dict(annual_amount=8000),
    dict(mode="free"), dict(annual_mode="explicit", annual_amount=8000)])
def test_invalid_offer_rejected(changes):
    with pytest.raises(membership.MembershipError):
        membership.validate_offer(offer(**changes))


def test_annual_rounding_and_explicit_amount():
    assert membership.validate_offer(offer())["annual_amount"] == 6000
    assert membership.validate_offer(offer(monthly_amount=1, annual_discount_bps=6250))["annual_amount"] == 5
    assert membership.validate_offer(offer(annual_mode="explicit", annual_amount=8000, annual_discount_bps=None))["annual_amount"] == 8000
    assert membership.validate_offer(dict(mode="free"))["trial_days"] == 0


@pytest.fixture
def store(test_engine):
    """Execute the actual migration in a disposable schema, preserving shared test DB."""
    connection = test_engine.connect()
    transaction = connection.begin()
    schema = "smn_test_" + uuid.uuid4().hex
    connection.execute(text("CREATE SCHEMA " + schema))
    connection.execute(text("SET LOCAL search_path TO " + schema + ", public"))
    for model in (m.User, m.AuditLog, m.StripeEvent, m.StripeCheckoutClaim):
        model.__table__.create(connection)
    filename = Path(__file__).resolve().parents[1] / "migrations/versions/fa8c2d601b93_smn_membership.py"
    spec = importlib.util.spec_from_file_location("smn_test_migration", filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = SimpleNamespace(execute=lambda sql: connection.execute(text(sql)))
    migration.upgrade()
    factory = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    yield factory
    transaction.rollback()
    connection.close()


@pytest.mark.db
def test_free_enrollment_has_no_tw_trial_and_is_once_only(store):
    p = provider_user()
    with store() as s:
        user, member = membership.enroll(s, p)
        s.commit()
        user2, member2 = membership.enroll(s, p)
        assert user2.id == user.id and member2.user_id == member.user_id
        assert user.reverse_trial_ends_at is None and user.trial_ends_at is None
        assert user.tier == "explorer" and user.roles == ["user"]
        assert user.stripe_subscription_id is None and user.api_stripe_subscription_id is None
        assert s.query(m.SmnGrant).count() == 1
        assert membership.entitlement(s, member)["reason"] == "free_launch"
        assert member.first_trial_started_at is None


@pytest.mark.db
def test_unverified_or_email_collision_never_merges(store):
    p = provider_user()
    with store() as s:
        with pytest.raises(membership.MembershipError):
            membership.enroll(s, provider_user(email_verified=False))
        user, _ = membership.enroll(s, p)
        s.commit()
        with pytest.raises(membership.MembershipError, match="identity_link_required"):
            membership.enroll(s, provider_user(email=p.email))
        assert s.query(m.User).count() == 1
        assert user.workos_user_id == p.id


@pytest.mark.db
def test_trial_exclusive_boundary_does_not_restart_or_change(store):
    start = membership.now_utc()
    with store() as s:
        o = m.SmnOffer(**membership.validate_offer(offer()), activated_at=start)
        s.add(o); s.flush()
        s.get(m.SmnSettings, 1).active_offer_id = o.id
        p = provider_user()
        user, member = membership.enroll(s, p, now=start)
        s.commit()
        end = member.first_trial_ends_at
        assert membership.entitlement(s, member, now=end - timedelta(microseconds=1))["can_read"]
        assert not membership.entitlement(s, member, now=end)["can_read"]
        membership.enroll(s, p, now=end + timedelta(days=10))
        assert member.first_trial_ends_at == end and s.query(m.SmnGrant).count() == 1
        member.suspended_at = start
        assert membership.entitlement(s, member, now=start)["reason"] == "membership_suspended"


@pytest.mark.db
def test_offer_activation_preserves_existing_free_members(store):
    with store() as s:
        user, member = membership.enroll(s, provider_user())
        draft = membership.save_draft(s, user, dict(expected_version=1, offer=dict(mode="free")))
        with pytest.raises(membership.MembershipError, match="version_conflict"):
            membership.save_draft(s, user, dict(expected_version=1, offer=dict(mode="free")))
        billing.activate_offer(s, user, dict(expected_version=2, draft_id=draft), "dev")
        assert membership.entitlement(s, member)["can_read"]
        assert s.query(m.SmnGrant).count() == 1
        assert s.get(m.SmnSettings, 1).version == 3


@pytest.mark.db
def test_reader_admin_service_and_csrf_separation(store, monkeypatch):
    workos = SimpleNamespace()
    provider = provider_user()
    monkeypatch.setattr(auth, "provider_identity", lambda *_: (provider, membership.now_utc() + timedelta(hours=12)))
    monkeypatch.setattr(auth, "verify_reader_token", lambda token: dict(sub=provider.id, sid="session_reader"))
    import smn_workos_authorization
    monkeypatch.setattr(smn_workos_authorization, "verify_access_token", lambda token: dict(sub=provider.id, sid="session_admin"))
    monkeypatch.setenv("TW2_SMN_READER_SERVICE_KEY", "r" * 48)
    monkeypatch.setenv("TW2_SMN_ADMIN_SERVICE_KEY", "a" * 48)
    app = Flask(__name__)
    app.register_blueprint(auth.create_blueprint(workos, "dev", session_factory=store))
    client = app.test_client()
    reader_headers = {"X-SMN-Reader-Key": "r" * 48, "Authorization": "Bearer workos"}
    result = client.post("/smn-reader/authorize", headers=reader_headers)
    assert result.status_code == 200
    reader_headers["Authorization"] = "Bearer " + result.json["reader_authority"]
    assert client.get("/smn-reader/entitlement", headers=reader_headers).json["can_read"]
    assert client.get("/smn-admin/settings", headers=reader_headers).status_code == 401
    admin_headers = {"X-SMN-Admin-Key": "a" * 48, "Authorization": "Bearer workos"}
    assert client.post("/smn-admin/authorize", headers=admin_headers).status_code == 403
    with store() as s:
        s.query(m.User).filter_by(workos_user_id=provider.id).one().roles = ["user", "super_admin"]
        s.commit()
    admin = client.post("/smn-admin/authorize", headers=admin_headers).json
    admin_headers["Authorization"] = "Bearer " + admin["admin_authority"]
    assert client.post("/smn-admin/settings", headers=admin_headers, json={}).status_code == 403
    admin_headers["X-SMN-CSRF"] = admin["csrf_token"]
    assert client.post("/smn-admin/settings", headers=admin_headers, json=dict(expected_version=1, offer=dict(mode="free"))).status_code == 200
    admin_headers["Authorization"] = reader_headers["Authorization"]
    assert client.get("/smn-admin/settings", headers=admin_headers).status_code == 401
    assert client.post("/smn-reader/logout", headers=reader_headers).status_code == 200
    assert client.get("/smn-reader/entitlement", headers=reader_headers).status_code == 401


def test_provider_revoked_session_and_outage_fail_closed():
    p = provider_user()
    session = SimpleNamespace(id="sid", user_id=p.id, status="ended", ended_at=membership.now_utc(),
                              impersonator=None, expires_at=membership.now_utc() + timedelta(days=1))
    workos = SimpleNamespace(user_management=SimpleNamespace(get_user=lambda _: p,
             list_sessions=lambda *a, **k: SimpleNamespace(auto_paging_iter=lambda: iter([session]))))
    with pytest.raises(membership.MembershipError, match="invalid_identity"):
        auth.provider_identity(workos, p.id, "sid")
    workos.user_management.get_user = lambda _: (_ for _ in ()).throw(RuntimeError("outage"))
    with pytest.raises(membership.MembershipError, match="identity_unavailable"):
        auth.provider_identity(workos, p.id, "sid")


def test_dev_live_key_and_disabled_billing_rejected(monkeypatch):
    monkeypatch.setenv("TW2_SMN_BILLING_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_testfixture")
    with pytest.raises(membership.MembershipError, match="billing_not_ready"):
        billing.client("dev")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fixture")
    assert billing.readiness("dev")["billing_enabled"]


@pytest.mark.db
def test_free_path_never_calls_stripe(store, monkeypatch):
    monkeypatch.setattr(billing, "client", lambda *_: pytest.fail("Stripe called for free membership"))
    with store() as s:
        user, _ = membership.enroll(s, provider_user())
        with pytest.raises(membership.MembershipError, match="free_membership_requires_no_checkout"):
            billing.create_checkout(s, user, {}, "dev", store)


def paid_member(s):
    o = m.SmnOffer(**membership.validate_offer(offer(trial_days=0)), activated_at=membership.now_utc(),
                  stripe_product_id="prod_smn", stripe_monthly_price_id="price_month", stripe_annual_price_id="price_year")
    s.add(o); s.flush()
    s.get(m.SmnSettings, 1).active_offer_id = o.id
    user, member = membership.enroll(s, provider_user())
    user.tier, user.api_tier = "strategist", "business"
    user.stripe_subscription_id, user.api_stripe_subscription_id = "sub_web", "sub_api"
    user.reverse_trial_ends_at = membership.now_utc() + timedelta(days=7)
    member.stripe_customer_id, member.stripe_subscription_id, member.subscription_offer_id = "cus_smn", "sub_smn", o.id
    s.commit()
    return user, member, o


def subscription(member, offer, **updates):
    price = dict(id="price_month", product="prod_smn", currency="usd", unit_amount=1000,
                 recurring=dict(interval="month", interval_count=1), active=True)
    values = dict(id="sub_smn", customer="cus_smn", status="active", cancel_at_period_end=False,
                  metadata=billing.metadata(offer, member.user_id),
                  items=dict(data=[dict(price=price, quantity=1)]), latest_invoice=None)
    values.update(updates)
    return values


def invoice(**updates):
    now = int(membership.now_utc().timestamp())
    values = dict(id="in_paid", customer="cus_smn", subscription="sub_smn", status="paid", paid=True,
                  amount_paid=1000, currency="usd", lines=dict(data=[dict(price=dict(id="price_month"),
                  amount=1000, period=dict(start=now, end=now + 30 * 86400))]))
    values.update(updates)
    return values


@pytest.mark.db
def test_paid_duplicate_out_of_order_failed_renewal_preserves_tw_and_paid_end(store):
    with store() as s:
        user, member, o = paid_member(s)
        reverse_end = user.reverse_trial_ends_at
        live = subscription(member, o, latest_invoice=invoice())
    provider = Mock()
    provider.v1.subscriptions.retrieve.return_value = live
    def event(eid, typ="invoice.payment_succeeded", **updates):
        data = dict(subscription="sub_smn", customer="cus_smn")
        data.update(updates)
        return dict(id=eid, type=typ, data=dict(object=data))
    assert billing.handle_event(event("evt_paid"), "dev", session_factory=store, provider=provider)["received"]
    assert billing.handle_event(event("evt_paid"), "dev", session_factory=store, provider=provider)["duplicate"]
    with store() as s:
        member = s.get(m.SmnMembership, user.id)
        paid_end = member.period_ends_at
        assert membership.entitlement(s, member)["can_read"]
        assert s.query(m.SmnGrant).count() == 1
    live["status"] = "past_due"
    live["latest_invoice"] = invoice(id="in_unpaid", status="open", paid=False, amount_paid=0)
    billing.handle_event(event("evt_failure", "invoice.payment_failed"), "dev", session_factory=store, provider=provider)
    billing.handle_event(event("evt_old_created", "customer.subscription.created", id="sub_smn"), "dev", session_factory=store, provider=provider)
    with store() as s:
        current = s.get(m.SmnMembership, user.id)
        assert current.period_ends_at == paid_end and s.query(m.SmnGrant).count() == 1
        assert membership.entitlement(s, current, now=paid_end)["can_read"] is False
        tw = s.get(m.User, user.id)
        assert (tw.tier, tw.api_tier, tw.stripe_subscription_id, tw.api_stripe_subscription_id) == ("strategist", "business", "sub_web", "sub_api")
        assert tw.reverse_trial_ends_at == reverse_end


@pytest.mark.db
@pytest.mark.parametrize("bad", [dict(customer="cus_other"), dict(metadata=dict(product_line="eod")),
     dict(items=dict(data=[dict(price=dict(id="price_wrong"), quantity=1)]))])
def test_wrong_customer_product_or_price_never_grants(store, bad):
    with store() as s:
        user, member, o = paid_member(s)
        live = subscription(member, o, latest_invoice=invoice(), **bad)
    provider = Mock()
    provider.v1.subscriptions.retrieve.return_value = live
    evt = dict(id="evt_bad", type="customer.subscription.updated", data=dict(object=dict(id="sub_smn", customer="cus_smn")))
    with pytest.raises(membership.MembershipError):
        billing.handle_event(evt, "dev", session_factory=store, provider=provider)
    with store() as s:
        assert s.query(m.SmnGrant).count() == 0
        assert s.get(m.User, user.id).stripe_subscription_id == "sub_web"


@pytest.mark.db
def test_old_subscription_cancellation_cannot_clear_new_subscription(store):
    with store() as s:
        user, member, o = paid_member(s)
        member.stripe_subscription_id = "sub_new"
        s.commit()
        live = subscription(member, o, id="sub_old", status="canceled")
    provider = Mock()
    provider.v1.subscriptions.retrieve.return_value = live
    evt = dict(id="evt_old_cancel", type="customer.subscription.deleted", data=dict(object=dict(id="sub_old", customer="cus_smn")))
    assert billing.handle_event(evt, "dev", session_factory=store, provider=provider)["ignored"] == "noncurrent_subscription"
    with store() as s:
        assert s.get(m.SmnMembership, user.id).stripe_subscription_id == "sub_new"


@pytest.mark.db
def test_refund_is_audited_without_changing_other_grants(store):
    with store() as s:
        user, member, o = paid_member(s)
        billing.apply_paid_invoice(s, member, o, "sub_smn", invoice())
        s.commit()
    evt = dict(id="evt_refund", type="charge.refunded", data=dict(object=dict(id="ch_smn", customer="cus_smn")))
    billing.handle_event(evt, "dev", session_factory=store)
    with store() as s:
        assert s.query(m.AuditLog).filter_by(action="smn_payment_review_required").count() == 1
        assert membership.entitlement(s, s.get(m.SmnMembership, user.id))["can_read"]


@pytest.mark.db
def test_checkout_replay_timeout_recovers_exact_payload_and_key(store, monkeypatch):
    with store() as s:
        user, member, o = paid_member(s)
        member.stripe_subscription_id = None
        member.subscription_offer_id = None
        s.commit()
        live = subscription(member, o)
    provider = Mock()
    provider.v1.prices.retrieve.side_effect = lambda pid: (live["items"]["data"][0]["price"] if pid == "price_month" else dict(id="price_year", product="prod_smn", currency="usd", unit_amount=6000, recurring=dict(interval="year"), active=True))
    provider.v1.customers.retrieve.return_value = dict(id="cus_smn", metadata=dict(product_line="smn", tw2_user_id=str(user.id)))
    provider.v1.checkout.sessions.create.side_effect = [RuntimeError("unknown outcome"), dict(id="cs_smn", url="https://checkout.stripe.com/test")]
    monkeypatch.setattr(billing, "client", lambda _: provider)
    monkeypatch.setenv("TW2_SMN_READER_ORIGIN", "https://smn.test")
    data = dict(interval="month", offer_version=o.id)
    with store() as s:
        with pytest.raises(membership.MembershipError, match="checkout_provider_unavailable"):
            billing.create_checkout(s, s.get(m.User, user.id), data, "dev", store)
    with store() as s:
        result = billing.create_checkout(s, s.get(m.User, user.id), data, "dev", store)
        assert result["session_id"] == "cs_smn"
    calls = provider.v1.checkout.sessions.create.call_args_list
    assert calls[0].kwargs == calls[1].kwargs
    with store() as s:
        assert billing.create_checkout(s, s.get(m.User, user.id), data, "dev", store)["reused"]
        assert provider.v1.checkout.sessions.create.call_count == 2
        with pytest.raises(membership.MembershipError, match="checkout_in_progress"):
            billing.create_checkout(s, s.get(m.User, user.id), dict(interval="year", offer_version=o.id), "dev", store)


@pytest.mark.db
def test_cancel_only_bound_smn_subscription_and_reactivation(store, monkeypatch):
    with store() as s:
        user, member, o = paid_member(s)
        live = subscription(member, o)
    provider = Mock()
    provider.v1.subscriptions.retrieve.return_value = live
    provider.v1.subscriptions.update.side_effect = lambda sid, params, options: {**live, **params}
    monkeypatch.setattr(billing, "client", lambda _: provider)
    with store() as s:
        assert billing.cancel_subscription(s, s.get(m.User, user.id), {}, "dev")["cancel_at_period_end"]
        assert not billing.cancel_subscription(s, s.get(m.User, user.id), dict(cancel_at_period_end=False), "dev")["cancel_at_period_end"]
        assert s.get(m.User, user.id).stripe_subscription_id == "sub_web"
    assert all(c.args[0] == "sub_smn" for c in provider.v1.subscriptions.update.call_args_list)
