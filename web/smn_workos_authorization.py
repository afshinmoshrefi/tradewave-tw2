"""Validate the dedicated SMN AuthKit application before central role lookup."""
import os
import time
import uuid
from functools import lru_cache
from pathlib import Path

import jwt


class Unavailable(Exception):
    pass


@lru_cache(maxsize=4)
def _keys(client_id):
    return jwt.PyJWKClient("https://api.workos.com/sso/jwks/" + client_id, timeout=5)


def verify_access_token(token):
    client_id = os.environ.get("TW2_SMN_WORKOS_CLIENT_ID", "").strip()
    issuer = os.environ.get("TW2_SMN_WORKOS_ISSUER", "").strip()
    if not client_id or not issuer:
        raise Unavailable()
    if not token or len(token) > 16384:
        raise jwt.InvalidTokenError()
    key = _keys(client_id).get_signing_key_from_jwt(token).key
    # AuthKit access tokens do not necessarily have aud. The issuer and explicit
    # application client_id pin this endpoint to the SMN app in this environment.
    claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
        options={"verify_aud": False, "require": ["iss", "sub", "sid", "exp", "iat", "client_id"]})
    if claims["client_id"] != client_id or any(
            not isinstance(claims[k], str) or not claims[k] for k in ("sub", "sid")):
        raise jwt.InvalidTokenError()
    if claims.get("act") or claims.get("impersonator"):
        raise jwt.InvalidTokenError()
    return claims


def admin_ticket(user, claims, environment):
    path = os.environ.get("TW2_SMN_DASHBOARD_SSO_KEY", "").strip()
    if not path or environment not in ("dev", "prod"):
        raise Unavailable()
    try:
        private_key = Path(path).read_bytes()
    except OSError:
        raise Unavailable() from None
    now = int(time.time())
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or user.email
    return jwt.encode({
        "iss": "tw2-web", "aud": "smn-dashboard", "sub": str(user.id),
        "name": name, "email": user.email, "env": environment,
        "is_admin": True, "iat": now, "exp": now + 60, "jti": uuid.uuid4().hex,
        "workos_user_id": claims["sub"], "workos_session_id": claims["sid"],
    }, private_key, algorithm="EdDSA")
