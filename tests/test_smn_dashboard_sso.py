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
    monkeypatch.setattr(app_module, "_get_authorization_url", lambda **kw: "https://login.test/")
    r = app_module.app.test_client().get("/smn-dashboard/login")
    assert (r.status_code, r.headers["Location"]) == (302, "https://login.test/")


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
