import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import smn_workos_authorization as auth
from tests.test_smn_dashboard_sso import app_module, keys, _user


@pytest.fixture
def signer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("TW2_SMN_WORKOS_CLIENT_ID", "client_smn_dev")
    monkeypatch.setenv("TW2_SMN_WORKOS_ISSUER", "https://api.workos.com/user_management/client_tw_dev")
    monkeypatch.setattr(auth, "_keys", lambda _: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    def sign(**updates):
        now = int(time.time())
        claims = dict(iss="https://api.workos.com/user_management/client_tw_dev",
                      sub="user_admin", sid="session_smn", client_id="client_smn_dev", iat=now, exp=now+300)
        claims.update(updates)
        return jwt.encode({k:v for k,v in claims.items() if v is not None}, key, algorithm="RS256")
    return sign


def test_valid_token_is_bound_to_smn_app(signer):
    assert auth.verify_access_token(signer())["sub"] == "user_admin"


@pytest.mark.parametrize("updates", [
    {"client_id":"client_tw_dev"}, {"client_id":None}, {"iss":"https://other.test"},
    {"exp":1}, {"exp":None}, {"iat":None}, {"iat":9999999999},
    {"sub":""}, {"sid":None}, {"sid":123}, {"act":{"sub":"another-user"}},
])
def test_invalid_claims_rejected(signer, updates):
    with pytest.raises(jwt.InvalidTokenError):
        auth.verify_access_token(signer(**updates))


def test_foreign_signature_rejected(signer):
    token = jwt.encode(dict(sub="user_admin"), rsa.generate_private_key(public_exponent=65537,key_size=2048),algorithm="RS256")
    with pytest.raises(jwt.InvalidTokenError): auth.verify_access_token(token)


def test_authorize_uses_verified_subject_and_current_role(app_module, keys, signer, monkeypatch):
    lookup = Mock(return_value=_user(["super_admin"]))
    monkeypatch.setattr(app_module,"current_user_from_db",lookup)
    monkeypatch.setattr(app_module,"get_current_user",lambda: _user(["super_admin"]))
    client=app_module.app.test_client()
    # Existing browser cookies/headers cannot substitute for WorkOS proof.
    assert client.post("/smn-dashboard/authorize",json={"is_admin":True}).status_code == 401
    response=client.post("/smn-dashboard/authorize",headers={"Authorization":"Bearer "+signer()})
    assert response.status_code == 200
    lookup.assert_called_once_with("user_admin")
    claims=jwt.decode(response.json["ticket"],keys,algorithms=["EdDSA"],audience="smn-dashboard",issuer="tw2-web")
    assert claims["workos_user_id"] == "user_admin"
    assert claims["workos_session_id"] == "session_smn"
    assert claims["env"] == app_module.config.tw2_env
    assert response.headers["Cache-Control"] == "no-store"
    lookup.return_value=_user(["user"])
    assert client.post("/smn-dashboard/authorize",headers={"Authorization":"Bearer "+signer()}).status_code == 403
    lookup.return_value=None
    assert client.post("/smn-dashboard/authorize",headers={"Authorization":"Bearer "+signer()}).status_code == 403


def test_bad_token_never_queries_user(app_module, signer, monkeypatch):
    lookup=Mock()
    monkeypatch.setattr(app_module,"current_user_from_db",lookup)
    response=app_module.app.test_client().post("/smn-dashboard/authorize",headers={"Authorization":"Bearer "+signer(client_id="client_other")})
    assert response.status_code == 401
    lookup.assert_not_called()


def test_missing_config_fails_closed(app_module, monkeypatch):
    monkeypatch.delenv("TW2_SMN_WORKOS_CLIENT_ID", raising=False)
    assert app_module.app.test_client().post("/smn-dashboard/authorize",headers={"Authorization":"Bearer token"}).status_code == 503
