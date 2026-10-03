"""Dedicated reader/admin service authorities backed by current WorkOS identity."""
from datetime import timedelta
from functools import lru_cache, wraps
import hashlib
import hmac
import os
import secrets

import jwt
from flask import Blueprint, request, jsonify
from models import Session, SmnAuthority, SmnMembership, User, SmnOffer
from smn_membership import (MembershipError, now_utc, enroll, entitlement, active_offer,
                            offer_dict, settings_snapshot, save_draft)


@lru_cache(maxsize=4)
def _keys(client_id):
    return jwt.PyJWKClient("https://api.workos.com/sso/jwks/" + client_id, timeout=5)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_reader_token(token):
    client_id = os.environ.get("TW2_SMN_READER_WORKOS_CLIENT_ID", "").strip()
    issuer = os.environ.get("TW2_SMN_READER_WORKOS_ISSUER", "").strip()
    if not client_id or not issuer:
        raise MembershipError("reader_identity_not_configured", 503)
    if not token or len(token) > 16384:
        raise jwt.InvalidTokenError()
    key = _keys(client_id).get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
        options={"verify_aud": False, "require": ["iss", "sub", "sid", "exp", "iat", "client_id"]})
    if claims["client_id"] != client_id or any(not isinstance(claims[k], str) or not claims[k] for k in ("sub", "sid")) or claims.get("act") or claims.get("impersonator"):
        raise jwt.InvalidTokenError()
    return claims


def provider_identity(workos, subject, session_id):
    """No cached positive identity: revoked sessions and verification fail closed."""
    try:
        user = workos.user_management.get_user(subject)
        if user.id != subject or user.email_verified is not True:
            raise MembershipError("verified_email_required", 403)
        sessions = workos.user_management.list_sessions(subject, limit=100)
        for item in sessions.auto_paging_iter():
            if item.id == session_id:
                status = getattr(item.status, "value", item.status)
                if item.user_id == subject and status == "active" and not item.ended_at and not item.impersonator and item.expires_at > now_utc():
                    return user, item.expires_at
                break
        raise MembershipError("invalid_identity", 401)
    except MembershipError:
        raise
    except Exception:
        raise MembershipError("identity_unavailable", 503) from None


def identity_fields(authority):
    return dict(user_id=str(authority.user_id), workos_user_id=authority.workos_user_id,
                workos_session_id=authority.workos_session_id, env=authority.environment,
                expires_at=authority.expires_at.isoformat())


def create_blueprint(workos, environment, *, session_factory=Session):
    bp = Blueprint("smn_membership", __name__)

    @bp.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @bp.errorhandler(MembershipError)
    def error(exc):
        return jsonify(error=exc.code), exc.status

    def service(kind):
        configured = os.environ.get("TW2_SMN_" + ("READER" if kind == "reader" else "ADMIN") + "_SERVICE_KEY", "")
        supplied = request.headers.get("X-SMN-Reader-Key" if kind == "reader" else "X-SMN-Admin-Key", "")
        if len(configured) < 32:
            raise MembershipError("service_not_configured", 503)
        if not hmac.compare_digest(configured, supplied):
            raise MembershipError("service_authentication_required", 401)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) > 16400:
            raise MembershipError("authentication_required", 401)
        return header[7:]

    def authorized(kind):
        def decorate(fn):
            @wraps(fn)
            def invoke(*args, **kwargs):
                token = service(kind)
                with session_factory() as s:
                    authority = s.get(SmnAuthority, digest(token))
                    if authority is None or authority.kind != kind or authority.environment != environment or authority.revoked_at or authority.expires_at <= now_utc():
                        raise MembershipError("invalid_authority", 401)
                    user = s.get(User, authority.user_id)
                    if user is None or user.workos_user_id != authority.workos_user_id:
                        raise MembershipError("invalid_identity", 401)
                    provider_identity(workos, authority.workos_user_id, authority.workos_session_id)
                    if kind == "admin":
                        if "super_admin" not in (user.roles or []):
                            raise MembershipError("administrator_required", 403)
                        if request.method != "GET" and not hmac.compare_digest(authority.csrf_hash or "", digest(request.headers.get("X-SMN-CSRF", ""))):
                            raise MembershipError("csrf_required", 403)
                    result = fn(s, authority, user, *args, **kwargs)
                    s.commit()
                    return result
            return invoke
        return decorate

    def authorize(kind):
        token = service(kind)
        try:
            if kind == "reader":
                claims = verify_reader_token(token)
            else:
                from smn_workos_authorization import verify_access_token, Unavailable
                try:
                    claims = verify_access_token(token)
                except Unavailable:
                    raise MembershipError("admin_identity_not_configured", 503)
            provider_user, provider_expiry = provider_identity(workos, claims["sub"], claims["sid"])
        except jwt.InvalidTokenError:
            raise MembershipError("invalid_identity", 401) from None
        except jwt.PyJWKClientError:
            raise MembershipError("identity_unavailable", 503) from None
        raw, csrf_token = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with session_factory() as s:
            if kind == "reader":
                user, _ = enroll(s, provider_user)
            else:
                user = s.query(User).filter_by(workos_user_id=claims["sub"]).one_or_none()
                if user is None or "super_admin" not in (user.roles or []):
                    raise MembershipError("administrator_required", 403)
            authority = SmnAuthority(token_hash=digest(raw), kind=kind, csrf_hash=digest(csrf_token) if kind == "admin" else None,
                user_id=user.id, workos_user_id=claims["sub"], workos_session_id=claims["sid"],
                environment=environment, expires_at=min(now_utc() + timedelta(hours=8), provider_expiry))
            s.add(authority)
            s.commit()
            result = identity_fields(authority)
            result[kind + "_authority"] = raw
            if kind == "admin":
                result["csrf_token"] = csrf_token
            return jsonify(result)

    bp.add_url_rule("/smn-reader/authorize", "reader_authorize", lambda: authorize("reader"), methods=["POST"])
    bp.add_url_rule("/smn-admin/authorize", "admin_authorize", lambda: authorize("admin"), methods=["POST"])

    @bp.get("/smn-reader/entitlement")
    @authorized("reader")
    def reader_entitlement(s, authority, user):
        result = entitlement(s, s.get(SmnMembership, user.id))
        result.update(identity_fields(authority))
        return jsonify(result)

    @bp.get("/smn-reader/account")
    @authorized("reader")
    def account(s, authority, user):
        member = s.get(SmnMembership, user.id)
        access = entitlement(s, member)
        access.update(identity_fields(authority))
        return jsonify(identity=dict(user_id=str(user.id), email=user.email,
                       name=" ".join(x for x in (user.first_name, user.last_name) if x)),
                       entitlement=access, offer=offer_dict(active_offer(s)),
                       subscription=dict(status=member.stripe_subscription_status,
                           cancel_at_period_end=member.cancel_at_period_end,
                           period_ends_at=member.period_ends_at.isoformat() if member.period_ends_at else None))

    @bp.post("/smn-reader/logout")
    @authorized("reader")
    def logout(s, authority, user):
        authority.revoked_at = now_utc()
        return jsonify(logged_out=True)

    @bp.post("/smn-reader/checkout")
    @authorized("reader")
    def checkout(s, authority, user):
        from smn_billing import create_checkout
        return jsonify(create_checkout(s, user, request.get_json(silent=True) or {}, environment, session_factory))

    @bp.post("/smn-reader/cancel")
    @authorized("reader")
    def cancel(s, authority, user):
        from smn_billing import cancel_subscription
        return jsonify(cancel_subscription(s, user, request.get_json(silent=True) or {}, environment))

    @bp.get("/smn-admin/settings")
    @authorized("admin")
    def settings(s, authority, user):
        from smn_billing import readiness
        return jsonify(settings_snapshot(s, readiness(environment)))

    @bp.post("/smn-admin/settings")
    @authorized("admin")
    def save(s, authority, user):
        from smn_billing import readiness
        draft_id = save_draft(s, user, request.get_json(silent=True) or {})
        result = settings_snapshot(s, readiness(environment))
        result["draft_id"] = draft_id
        return jsonify(result)

    @bp.post("/smn-admin/activate")
    @authorized("admin")
    def activate(s, authority, user):
        from smn_billing import readiness, activate_offer
        activate_offer(s, user, request.get_json(silent=True) or {}, environment)
        return jsonify(settings_snapshot(s, readiness(environment)))

    return bp
