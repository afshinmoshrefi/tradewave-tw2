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
    """The b9c784d repair replaced the broken SDK `sess.refresh()` with a
    manual flow: unseal the cookie locally -> exchange the refresh token ->
    seal LOCALLY -> re-load + re-authenticate the new blob. These tests mock
    that flow (the old sess.refresh() is never called)."""

    def _wire_manual_refresh(self, app_module, patched_workos, monkeypatch,
                             stale_sess, new_blob="new_sealed_blob"):
        monkeypatch.setattr(app_module, "unseal_data",
                            lambda sealed, pw: {"refresh_token": "rt_old"})
        rt = MagicMock(name="rt", access_token="at_new",
                       refresh_token="rt_new", impersonator=None)
        rt.user.to_dict.return_value = {"id": "user_abc", "email": "a@b.com"}
        patched_workos.authenticate_with_refresh_token.return_value = rt
        monkeypatch.setattr(app_module, "seal_session_from_auth_response",
                            lambda **kw: new_blob)
        new_sess = MagicMock(name="new_sess")
        # First load -> the stale session; second load -> the re-sealed one.
        patched_workos.load_sealed_session.side_effect = [stale_sess, new_sess]
        return new_sess

    def test_refresh_stages_new_cookie(self, app_module, patched_workos, monkeypatch):
        sess = MagicMock(name="sess")
        # First authenticate: not authenticated -> triggers the manual refresh.
        sess.authenticate.return_value = MagicMock(
            authenticated=False, reason="access_token_expired",
        )
        new_sess = self._wire_manual_refresh(app_module, patched_workos,
                                             monkeypatch, sess)
        refreshed = MagicMock(authenticated=True)
        new_sess.authenticate.return_value = refreshed

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
        patched_workos.authenticate_with_refresh_token.assert_called_once_with(
            refresh_token="rt_old")
        # The broken SDK refresh must NOT be used.
        sess.refresh.assert_not_called()

    def test_refresh_reauth_fails_returns_none(self, app_module, patched_workos,
                                               monkeypatch):
        """Edge case: the re-sealed session does not re-authenticate. No
        cookie may be staged and the caller gets (None, None) (re-login)."""
        sess = MagicMock(name="sess")
        sess.authenticate.return_value = MagicMock(authenticated=False, reason="x")
        new_sess = self._wire_manual_refresh(app_module, patched_workos,
                                             monkeypatch, sess)
        new_sess.authenticate.return_value = MagicMock(
            authenticated=False, reason="still_bad")

        from flask import g
        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=stale",
        }):
            result = app_module._read_sealed_session()
            assert getattr(g, "_pending_session_cookie", None) is None
        assert result == (None, None)

    def test_refresh_without_refresh_token_returns_none(self, app_module,
                                                        patched_workos,
                                                        monkeypatch):
        """Edge case: the unsealed cookie carries no refresh_token - nothing
        to exchange, so the session ends (None, None)."""
        sess = MagicMock(name="sess")
        sess.authenticate.return_value = MagicMock(authenticated=False, reason="x")
        patched_workos.load_sealed_session.return_value = sess
        monkeypatch.setattr(app_module, "unseal_data", lambda sealed, pw: {})

        with app_module.app.test_request_context("/", headers={
            "Cookie": f"{app_module.SESSION_COOKIE}=stale",
        }):
            assert app_module._read_sealed_session() == (None, None)
        patched_workos.authenticate_with_refresh_token.assert_not_called()


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
