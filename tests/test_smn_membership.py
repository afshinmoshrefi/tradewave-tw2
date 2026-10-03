"""SMN identity/access and isolated payment invariants on real PostgreSQL."""
from datetime import timedelta
import importlib.util
from pathlib import Path
from types import SimpleNamespace
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
