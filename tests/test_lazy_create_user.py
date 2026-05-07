"""
Coverage for `lazy_create_user(workos_user)` in /home/flask/web/app.py.

This is the function that creates the Postgres mirror row on the first
sign-in via WorkOS. It has to be:

  * idempotent on repeated sign-ins
  * resilient to a two-tab signup race that hits the unique workos_user_id
    or email constraint at commit time (F2.4)
  * able to backfill workos_user_id onto an existing email-only row
  * able to detect a WorkOS-side email change and sync + audit it

Each of those branches is covered below. We patch `mailerlite_subscribe`
to a no-op so signup tests do not trigger an outbound HTTP call.
"""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.db


# ---------------------------------------------------------------------
# Fixtures specific to this module
# ---------------------------------------------------------------------

@pytest.fixture
def app_module(_models_module):
    """Import web.app with mailerlite stubbed to a no-op so create-user
    flows never touch the network."""
    mod = importlib.import_module("app")
    # Re-bind app.DBSession (and Session) to the test engine so that the
    # function-under-test, which calls `DBSession()` internally, hits
    # tradewave_test instead of tradewave.
    mod.DBSession = _models_module.Session
    return mod


@pytest.fixture(autouse=True)
def stub_mailerlite(app_module):
    """The signup happy path calls mailerlite_subscribe(); stub it so
    no test ever fires a real HTTP request to Mailerlite."""
    with patch.object(app_module, "mailerlite_subscribe", return_value=False) as m:
        yield m


@pytest.fixture
def stub_audit(app_module):
    """Capture write_audit() calls so tests can assert they happened
    without hitting the real audit log table."""
    with patch.object(app_module, "write_audit") as m:
        yield m


# ---------------------------------------------------------------------
# 1. Happy path — new user, never seen before
# ---------------------------------------------------------------------

class TestHappyPathCreate:
    def test_creates_explorer_user(self, app_module, db_session, mock_workos_user, stub_audit):
        wu = mock_workos_user(email="brandnew@example.com")
        u = app_module.lazy_create_user(wu)
        assert u is not None
        assert u.email == "brandnew@example.com"
        assert u.workos_user_id == wu.id
        assert u.tier == "explorer"
        assert u.email_verified is True
        assert "user" in (u.roles or [])
        # The schema_hardening trigger pins legacy_wp_level off tier:
        assert u.legacy_wp_level == "1"

        # Audit row written for the user_created event.
        stub_audit.assert_called()
        call_kw = stub_audit.call_args.kwargs
        assert call_kw["action"] == "user_created"

    def test_super_admin_role_for_afshin(self, app_module, mock_workos_user, stub_audit):
        wu = mock_workos_user(email="afshin@tradewave.ai")
        u = app_module.lazy_create_user(wu)
        assert "super_admin" in (u.roles or [])
        assert "user" in (u.roles or [])


# ---------------------------------------------------------------------
# 2. Idempotency — same workos_user_id called twice
# ---------------------------------------------------------------------

class TestIdempotent:
    def test_second_call_returns_same_row(self, app_module, db_session, _models_module,
                                           mock_workos_user, stub_audit):
        wu = mock_workos_user(email="repeat@example.com", id="user_repeat_42")
        u1 = app_module.lazy_create_user(wu)
        u2 = app_module.lazy_create_user(wu)
        assert str(u1.id) == str(u2.id)

        # Only ONE row in the DB for this workos_user_id.
        cnt = db_session.query(_models_module.User).filter_by(
            workos_user_id="user_repeat_42",
        ).count()
        assert cnt == 1


# ---------------------------------------------------------------------
# 3. Email-collision branch — pre-existing row by email gets backfilled
# ---------------------------------------------------------------------

class TestEmailCollisionBackfill:
    def test_existing_email_row_gets_workos_id_backfilled(
        self, app_module, db_session, _models_module, make_user, mock_workos_user, stub_audit,
    ):
        """A row with email=X but workos_user_id=NULL is exactly what an
        admin-created or migrated user looks like before they first sign
        in. lazy_create_user must reuse that row, NOT create a duplicate.
        """
        existing = make_user(email="legacy@example.com", workos_user_id=None, tier="analyst")
        existing_id = str(existing.id)

        wu = mock_workos_user(email="legacy@example.com", id="user_first_login_xyz")
        u = app_module.lazy_create_user(wu)

        # Same row, NOT a duplicate.
        assert str(u.id) == existing_id
        assert u.workos_user_id == "user_first_login_xyz"
        # Tier preserved (do NOT downgrade an analyst to explorer on first signin).
        assert u.tier == "analyst"

        cnt = db_session.query(_models_module.User).filter_by(email="legacy@example.com").count()
        assert cnt == 1


# ---------------------------------------------------------------------
# 4. Race condition — IntegrityError on commit, re-query wins
# ---------------------------------------------------------------------

class TestSignupRace:
    def test_integrity_error_triggers_requery(
        self, app_module, db_session, _models_module, mock_workos_user, stub_audit,
    ):
        """Simulate two-tab signup: by the time we commit our INSERT, a
        sibling worker already inserted the same workos_user_id. The
        commit raises IntegrityError; the function must rollback and
        re-query, returning the row the sibling won with."""
        from models import User

        # Pre-insert the "sibling worker's" row directly so the lookup
        # finds it after the simulated IntegrityError.
        winner = User(
            workos_user_id="user_race_winner",
            email="race@example.com",
            email_verified=True,
            tier="explorer",
            roles=["user"],
        )
        db_session.add(winner)
        db_session.commit()
        winner_id = str(winner.id)

        wu = mock_workos_user(id="user_race_winner", email="race@example.com")

        # Patch the module's DBSession factory so that the FIRST call to
        # commit() raises IntegrityError but the re-query succeeds.
        # We do this by intercepting the Session() constructor to wrap
        # the returned session: first .commit() raises once, then works.
        original_session_factory = app_module.DBSession

        def make_flaky_session():
            s = original_session_factory()
            real_commit = s.commit
            calls = {"n": 0}

            def flaky_commit():
                calls["n"] += 1
                # Skip the FIRST commit (the INSERT path); rollback so
                # state is consistent, then raise to mimic Postgres
                # rejecting the duplicate.
                if calls["n"] == 1:
                    s.rollback()
                    raise IntegrityError("race", {}, Exception("duplicate key"))
                return real_commit()

            s.commit = flaky_commit
            return s

        with patch.object(app_module, "DBSession", side_effect=make_flaky_session):
            u = app_module.lazy_create_user(wu)

        assert u is not None
        assert str(u.id) == winner_id, (
            "After IntegrityError the function must re-query and return "
            "the row inserted by the racing worker, not raise."
        )

        # Still exactly one row.
        cnt = db_session.query(User).filter_by(workos_user_id="user_race_winner").count()
        assert cnt == 1


# ---------------------------------------------------------------------
# 5. Email-change sync — WorkOS email differs from DB email
# ---------------------------------------------------------------------

class TestEmailChangeSync:
    def test_email_change_updates_db_and_audits(
        self, app_module, db_session, _models_module, make_user, mock_workos_user, stub_audit,
    ):
        # Pre-insert the user with an OLD email
        u_initial = make_user(
            workos_user_id="user_email_changer",
            email="old@example.com",
            email_verified=True,
        )

        # WorkOS now reports a different email for the same user_id
        wu = mock_workos_user(id="user_email_changer", email="new@example.com")

        u = app_module.lazy_create_user(wu)

        # Refresh + assert
        db_session.expire_all()
        from models import User
        fresh = db_session.query(User).filter_by(workos_user_id="user_email_changer").first()
        assert fresh.email == "new@example.com"
        assert str(fresh.id) == str(u_initial.id)

        # Audit should have an "email_changed" entry.
        actions = [c.kwargs.get("action") for c in stub_audit.call_args_list]
        assert "email_changed" in actions

    def test_no_email_change_no_audit(
        self, app_module, db_session, make_user, mock_workos_user, stub_audit,
    ):
        """If WorkOS email matches DB email, no email_changed audit fires."""
        make_user(workos_user_id="user_stable", email="stable@example.com")

        wu = mock_workos_user(id="user_stable", email="stable@example.com")
        app_module.lazy_create_user(wu)

        actions = [c.kwargs.get("action") for c in stub_audit.call_args_list]
        assert "email_changed" not in actions
