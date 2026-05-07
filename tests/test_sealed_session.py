"""
Coverage for `_read_sealed_session()` in /home/flask/web/app.py.

This is the function that bit us today during the redirect-loop incident
and on a previous deploy. It is the entry point for every authenticated
request.

We patch `workos_client.user_management.load_sealed_session` to return
controllable mocks and exercise the five real branches of the function:

  1. No cookie present                         → (None, None)
  2. Cookie present but load_sealed raises     → (None, None), warning
  3. Authenticated session                      → (auth_result, sealed)
  4. authenticate=False but refresh succeeds    → (refresh_result, new_sealed),
                                                   g._pending_session_cookie set
  5. authenticate=False and refresh fails       → (None, None)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

@pytest.fixture
def app_module():
    """Import web.app once. Subsequent tests reuse the same module."""
    import importlib
    return importlib.import_module("app")


@pytest.fixture
def request_ctx(app_module):
    """Push a Flask test-request context so request.cookies / flask.g work."""
    with app_module.app.test_request_context("/"):
        yield


@pytest.fixture
def patched_workos(app_module, monkeypatch):
    """Replace app.workos_client.user_management with a MagicMock for the
    duration of one test. Returns the mock so the test can program return
    values."""
    fake_um = MagicMock(name="user_management")
    monkeypatch.setattr(app_module.workos_client, "user_management", fake_um)
    return fake_um


# ---------------------------------------------------------------------
# 1. No cookie present
# ---------------------------------------------------------------------

class TestNoCookie:
    def test_returns_none_pair(self, app_module, patched_workos):
        with app_module.app.test_request_context("/"):
            assert app_module._read_sealed_session() == (None, None)
        # If there's no cookie we should never even call load_sealed_session.
        patched_workos.load_sealed_session.assert_not_called()


# ---------------------------------------------------------------------
# 2. Cookie present but load_sealed_session raises
# ---------------------------------------------------------------------

class TestInvalidCookie:
    def test_load_sealed_raises(self, app_module, patched_workos, caplog):
        patched_workos.load_sealed_session.side_effect = ValueError("malformed cookie")
        cookies = {app_module.SESSION_COOKIE: "garbage"}
        with caplog.at_level("WARNING"):
            with app_module.app.test_request_context("/", headers={
                "Cookie": f"{app_module.SESSION_COOKIE}=garbage",
            }):
                result = app_module._read_sealed_session()
        assert result == (None, None)
        # Warning must mention the failure (so ops can grep logs).
        assert any("Failed to load sealed session" in r.message for r in caplog.records)


# ---------------------------------------------------------------------
# 3. Valid sealed session — authenticate succeeds
# ---------------------------------------------------------------------

class TestAuthenticatedHappyPath:
    def test_returns_auth_result_and_sealed(self, app_module, patched_workos):
        sess = MagicMock(name="sess")
        auth_result = MagicMock(authenticated=True, user=MagicMock(id="user_abc", email="a@b.com"))
        sess.authenticate.return_value = auth_result
        patched_workos.load_sealed_session.return_value = sess

        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=valid_sealed_token",
        }):
            r, sealed = app_module._read_sealed_session()

        assert r is auth_result
        assert sealed == "valid_sealed_token"
        patched_workos.load_sealed_session.assert_called_once()
        sess.authenticate.assert_called_once()
        # Refresh must NOT be called on the happy path.
        sess.refresh.assert_not_called()


# ---------------------------------------------------------------------
# 4. Authenticate fails, refresh succeeds → new cookie staged
# ---------------------------------------------------------------------

class TestRefreshSuccess:
    def test_refresh_stages_new_cookie(self, app_module, patched_workos):
        sess = MagicMock(name="sess")
        # First call: not authenticated
        sess.authenticate.return_value = MagicMock(
            authenticated=False, reason="access_token_expired",
        )
        # Refresh: authenticated, with a new sealed_session blob
        refreshed = MagicMock(authenticated=True, sealed_session="new_sealed_blob")
        sess.refresh.return_value = refreshed
        patched_workos.load_sealed_session.return_value = sess

        from flask import g
        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=stale_sealed_token",
        }):
            r, sealed = app_module._read_sealed_session()
            # The function stages the new cookie on flask.g for the
            # after_request hook.
            assert getattr(g, "_pending_session_cookie", None) == "new_sealed_blob"

        assert r is refreshed
        assert sealed == "new_sealed_blob"
        sess.refresh.assert_called_once()

    def test_refresh_authenticated_but_no_sealed(self, app_module, patched_workos):
        """Edge case: refresh says authenticated but didn't return a new
        sealed_session blob. We still return the refreshed result, but
        keep using the original cookie."""
        sess = MagicMock(name="sess")
        sess.authenticate.return_value = MagicMock(authenticated=False, reason="x")
        refreshed = MagicMock(authenticated=True, sealed_session=None)
        sess.refresh.return_value = refreshed
        patched_workos.load_sealed_session.return_value = sess

        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=stale",
        }):
            r, sealed = app_module._read_sealed_session()
        assert r is refreshed
        assert sealed == "stale"


# ---------------------------------------------------------------------
# 5. Authenticate fails, refresh fails → (None, None)
# ---------------------------------------------------------------------

class TestRefreshFailure:
    def test_refresh_authenticated_false(self, app_module, patched_workos):
        sess = MagicMock(name="sess")
        sess.authenticate.return_value = MagicMock(authenticated=False, reason="x")
        sess.refresh.return_value = MagicMock(authenticated=False, reason="refresh_token_expired")
        patched_workos.load_sealed_session.return_value = sess

        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=really_stale",
        }):
            assert app_module._read_sealed_session() == (None, None)

    def test_refresh_raises(self, app_module, patched_workos):
        """If refresh() raises (e.g. WorkOS network blip), function must
        return (None, None) instead of letting the exception bubble up."""
        sess = MagicMock(name="sess")
        sess.authenticate.return_value = MagicMock(authenticated=False, reason="x")
        sess.refresh.side_effect = RuntimeError("workos 503")
        patched_workos.load_sealed_session.return_value = sess

        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=stale",
        }):
            result = app_module._read_sealed_session()

        assert result == (None, None)
