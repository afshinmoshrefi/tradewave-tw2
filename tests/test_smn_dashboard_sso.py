"""
/smn-dashboard/login: admin-only handoff to the SMN publishing dashboard.

The route signs a 60-second, one-time ticket with an Ed25519 private key.
The SMN dashboard verifies it with the matching public key
(SMN repo: blog/dashboard_auth.py, tests/test_dashboard_auth.py).
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@pytest.fixture
def app_module():
    return importlib.import_module("app")


@pytest.fixture
def keys(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    path = tmp_path / "sso.pem"
    path.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    monkeypatch.setenv("TW2_SMN_DASHBOARD_SSO_KEY", str(path))
    monkeypatch.setenv("TW2_SMN_DASHBOARD_URL", "https://smn.test/dashboard/")
    return private.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)


def _user(roles):
    return SimpleNamespace(id="7f0c1c1e-0000-4000-8000-000000000001", email="a@t.test",
                           first_name="Afshin", last_name="M", roles=roles)


def test_logged_out_goes_to_tradewave_login(app_module, keys, monkeypatch):
    monkeypatch.setattr(app_module, "get_current_user", lambda: None)
    authorize = MagicMock(return_value="https://login.test/")
    monkeypatch.setattr(app_module, "_get_authorization_url", authorize)
    r = app_module.app.test_client().get("/smn-dashboard/login")
    assert (r.status_code, r.headers["Location"]) == (302, "https://login.test/")
    authorize.assert_called_once_with(state="/smn-dashboard/login")


@pytest.mark.parametrize("roles, expected", [(["super_admin"], 302), (["user"], 403)])
def test_logged_out_callback_returns_to_dashboard_and_rechecks_role(
        app_module, keys, monkeypatch, roles, expected):
    identity = None
    monkeypatch.setattr(app_module, "get_current_user", lambda: identity)
    authorize = MagicMock(return_value="https://login.test/")
    monkeypatch.setattr(app_module, "_get_authorization_url", authorize)
    client = app_module.app.test_client()
    assert client.get("/smn-dashboard/login").status_code == 302
    state = authorize.call_args.kwargs["state"]

    # Exercise the actual callback's redirect validation without external auth/DB writes.
    result = SimpleNamespace(
        user=SimpleNamespace(to_dict=lambda: {"id": "unit-user"}, email_verified=False),
        impersonator=None, access_token="unit-access", refresh_token="unit-refresh")
    workos = MagicMock()
    workos.user_management.authenticate_with_code.return_value = result
    monkeypatch.setattr(app_module, "workos_client", workos)
    monkeypatch.setattr(app_module, "seal_session_from_auth_response", lambda **kw: "unit-cookie")
    identity = _user(roles)
    monkeypatch.setattr(app_module, "lazy_create_user", lambda user: identity)
    monkeypatch.setattr(app_module, "DBSession", MagicMock())
    callback = client.get("/auth/callback", query_string={"code": "unit-code", "state": state})
    assert (callback.status_code, callback.headers["Location"]) == (302, "/smn-dashboard/login")
    workos.user_management.authenticate_with_code.assert_called_once_with(code="unit-code")
    handoff = client.get(callback.headers["Location"])
    assert handoff.status_code == expected
    if expected == 302:
        ticket = parse_qs(urlparse(handoff.headers["Location"]).query)["ticket"][0]
        claims = jwt.decode(ticket, keys, algorithms=["EdDSA"], audience="smn-dashboard", issuer="tw2-web")
        assert claims["is_admin"] is True
    else:
        assert "Location" not in handoff.headers


def test_non_admin_is_refused(app_module, keys, monkeypatch):
    monkeypatch.setattr(app_module, "get_current_user", lambda: _user(["user"]))
    assert app_module.app.test_client().get("/smn-dashboard/login").status_code == 403


def test_not_configured_is_503(app_module, monkeypatch):
    monkeypatch.delenv("TW2_SMN_DASHBOARD_SSO_KEY", raising=False)
    monkeypatch.setattr(app_module, "get_current_user", lambda: _user(["super_admin"]))
    assert app_module.app.test_client().get("/smn-dashboard/login").status_code == 503


def test_admin_gets_a_signed_short_ticket(app_module, keys, monkeypatch):
    monkeypatch.setattr(app_module, "get_current_user", lambda: _user(["user", "super_admin"]))
    r = app_module.app.test_client().get("/smn-dashboard/login")
    assert r.status_code == 302
    assert r.headers["Cache-Control"] == "no-store"
    url = urlparse(r.headers["Location"])
    assert (url.scheme, url.netloc, url.path) == ("https", "smn.test", "/dashboard/auth")
    ticket = parse_qs(url.query)["ticket"][0]
    claims = jwt.decode(ticket, keys, algorithms=["EdDSA"], audience="smn-dashboard",
                        issuer="tw2-web")
    assert claims["is_admin"] is True
    assert claims["env"] == app_module.config.tw2_env
    assert claims["sub"] == "7f0c1c1e-0000-4000-8000-000000000001"
    assert claims["name"] == "Afshin M"
    assert claims["exp"] - claims["iat"] == 60
    assert len(claims["jti"]) == 32
