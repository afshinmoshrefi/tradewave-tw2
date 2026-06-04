"""
TradeWave 2.0 - Web Tier
========================

Single Flask service handling:
  - Auth flow (signup / login / logout / callback) via WorkOS AuthKit
  - JSON API for current user (/api/me)
  - Account page (/account) - minimal landing post-signup
  - Pricing page (/pricing) - basic stub for Stripe Checkout (Phase 5)
  - Stripe Checkout + success/cancel (Phase 5)
  - Flask-Admin at /admin (Phase 6)
  - /app/ React shell with REAL auth globals injected (Phase 4)

Runs on 127.0.0.1:5500 behind nginx. Internal-only HTTP; nginx terminates
the public connection. WorkOS hosted UI is the user-facing auth surface.

Sessions: we use WorkOS' "sealed session" pattern - the entire session
is encrypted client-side as a single cookie value. No server-side session
store needed for auth state. Custom data (e.g. flash messages) go through
Flask's signed-cookie session.

Key design rule (from architecture decisions):
  - This service touches Postgres on /auth/callback (lazy-create user) and
    /webhooks/* (mutations). Never on the React app's data path.
  - All hot-path data still goes through the appserver (5000), which uses
    Redis for sub-ms session lookups via JWT.
"""
import os
import sys
import time
import json as _json
import socket
import decimal
import logging
from pathlib import Path
from functools import wraps
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlparse

import jwt
import requests
from flask import (
    Flask, request, redirect, url_for, jsonify,
    make_response, render_template, abort, session as flask_session, g,
)
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

# F2.5 - Defense in depth: cap any unbounded socket reads at 15s. Applies
# globally to every stdlib socket op including the requests/httpx layers used
# by Stripe + WorkOS SDKs. Per-call timeouts below add finer-grained limits.
socket.setdefaulttimeout(15)


def _json_safe(obj):
    """Convert Stripe response shapes (Decimal, nested dicts/lists) to JSON-safe
    primitives so they survive json.dumps into a JSONB column.

    F2.7 - Stripe occasionally returns Decimal in webhook payloads; the default
    json encoder raises TypeError on Decimal, which used to drop the entire
    StripeEvent insert and force a webhook 500 -> Stripe retry storm.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        try:
            return float(obj) if obj % 1 else int(obj)
        except Exception:
            return float(obj)
    return obj

# --- Project / internal ---
sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/web')
import config

# --- Sentry (no-op when SENTRY_DSN is empty/placeholder) ---
try:
    import sentry_sdk
    _dsn = getattr(config, 'SENTRY_DSN', '') or ''
    if _dsn and 'PLACEHOLDER' not in _dsn:
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
        )
except ImportError:
    pass

from models import (
    User, AuditLog, StripeEvent, CouponUsed, SupportTicket,
    SUPPORT_TICKET_TOPICS, db_session, write_audit, Session as DBSession,
)
from tier_compat import tier_to_wp_user_levels, tier_to_legacy_level
from email_utils import mailerlite_subscribe, sync_mailerlite_level_group

# --- WorkOS ---
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response
from workos._errors import BadRequestError as WorkOSBadRequestError

# --- Stripe ---
import stripe
stripe.api_key = config.STRIPE_SECRET_KEY
# F2.6 - Cap Stripe network timeouts and turn on built-in retries. Without
# these, a Stripe slow-response can wedge a worker for the OS socket default.
stripe.max_network_retries = 2
try:
    # Stripe 15.x exposes the requests-based client at stripe._http_client.
    # Setting default_http_client makes EVERY stripe.* call use this timeout.
    stripe.default_http_client = stripe._http_client.RequestsClient(timeout=10)
except Exception as _stripe_http_err:
    log_msg = "Stripe SDK http_client patch unavailable: %s" % (_stripe_http_err,)
    # Use print since logging not configured yet; will be captured by systemd
    print(log_msg, file=sys.stderr)

# --- Flask-Admin ---
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.actions import action
from flask import flash


# ============================================================
# App + logging setup
# ============================================================
app = Flask(__name__)
app.config["SECRET_KEY"] = config.WORKOS_COOKIE_PASSWORD  # for Flask's own session signing

# CSRF protection for all POST routes. Flask-Admin's form rendering picks
# this up automatically; webhooks (no browser session) and the SERVICE_API_KEY-
# authed /internal/* routes are exempted below at decorator level. SameSite=Lax
# alone is not enough for top-level cross-site POSTs.
from flask_wtf.csrf import CSRFProtect  # noqa: E402
csrf = CSRFProtect(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tw2.web")


# ============================================================
# WorkOS client + helpers
# ============================================================
workos_client = WorkOSClient(
    api_key=config.WORKOS_API_KEY,
    client_id=config.WORKOS_CLIENT_ID,
    # F2.5 - cap every WorkOS HTTP call at 10s. Default is 60s (or whatever
    # the WORKOS_REQUEST_TIMEOUT env says). 60s is too long to leave a Flask
    # worker blocked when a single request from a user is in flight.
    request_timeout=10,
)

# Internal: where users return to after WorkOS hosted UI
REDIRECT_URI = os.environ.get(
    "TW2_AUTH_CALLBACK_URL",
    f"http://{os.environ.get('TW2_PUBLIC_HOST', '192.168.1.176')}/auth/callback",
)

# Auth cookie name - the sealed session token
SESSION_COOKIE = "tw2_session"

# How long we trust a session before re-validating against WorkOS
SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _get_authorization_url(provider="authkit", state=None, screen_hint=None):
    """Build the URL that redirects the user to WorkOS hosted UI.
    screen_hint='sign-up' forces signup form; 'sign-in' forces login."""
    kwargs = dict(provider=provider, redirect_uri=REDIRECT_URI, state=state)
    if screen_hint:
        kwargs["screen_hint"] = screen_hint
    return workos_client.user_management.get_authorization_url(**kwargs)


# ============================================================
# Session helpers
# ============================================================

@app.after_request
def _persist_refreshed_session(response):
    """If _read_sealed_session refreshed the session, write the new sealed cookie."""
    pending = getattr(g, "_pending_session_cookie", None)
    if pending:
        response.set_cookie(
            SESSION_COOKIE,
            pending,
            max_age=SESSION_LIFETIME_SECONDS,
            httponly=True,
            secure=True,
            samesite="Lax",
            path="/",
        )
    return response


def _read_sealed_session():
    """Return (auth_result, sealed_token) if logged in, else (None, None).
    Validates by decrypting the sealed cookie with our cookie password.

    If the access token has expired, attempts sess.refresh() transparently. The
    refreshed sealed session is stashed on flask.g for an after_request hook to
    persist as a cookie on the response.
    """
    sealed = request.cookies.get(SESSION_COOKIE)
    if not sealed:
        return None, None
    try:
        sess = workos_client.user_management.load_sealed_session(
            session_data=sealed,
            cookie_password=config.WORKOS_COOKIE_PASSWORD,
        )
        result = sess.authenticate()
        if getattr(result, "authenticated", False):
            return result, sealed

        reason = getattr(result, "reason", None)
        log.info("Session authenticate=False reason=%s; attempting refresh", reason)
        try:
            refresh_result = sess.refresh()
            if getattr(refresh_result, "authenticated", False):
                new_sealed = getattr(refresh_result, "sealed_session", None)
                if new_sealed:
                    g._pending_session_cookie = new_sealed
                    log.info("Session refresh succeeded; new cookie staged")
                    return refresh_result, new_sealed
                log.warning("Session refresh authenticated but no sealed_session attr returned")
                return refresh_result, sealed
            log.info("Session refresh failed: reason=%s", getattr(refresh_result, "reason", None))
        except Exception as re:
            log.info("Session refresh raised: %s", re)
        return None, None
    except Exception as e:
        log.warning("Failed to load sealed session: %s", e)
        return None, None


def current_user_from_db(workos_user_id: str):
    """Return the Postgres User row for the given WorkOS user_id; None if not found."""
    s = DBSession()
    try:
        return s.query(User).filter_by(workos_user_id=workos_user_id).first()
    finally:
        s.close()


def lazy_create_user(workos_user) -> User:
    """Create a Postgres mirror row if it doesn't exist; return the User row.

    F2.4 - race-hardened: a duplicate signup hitting two workers simultaneously
    used to surface as an IntegrityError 500 from the unique workos_user_id /
    email constraints. Now we catch IntegrityError, rollback, and re-query.
    Also: if a user's WorkOS email has changed since we last saw them, sync it
    and audit the change.
    """
    s = DBSession()
    try:
        u = s.query(User).filter_by(workos_user_id=workos_user.id).first()
        if u is not None:
            # F2.4 - sync email if WorkOS shows it changed (e.g. user updated
            # their email in the WorkOS hosted UI).
            if workos_user.email and workos_user.email != u.email:
                old_email = u.email
                u.email = workos_user.email
                u.email_verified = bool(workos_user.email_verified)
                try:
                    s.commit()
                    write_audit(
                        actor_label="workos_signin",
                        action="email_changed",
                        target_user_id=u.id,
                        details={"from": old_email, "to": workos_user.email},
                    )
                except IntegrityError:
                    # Email collides with a different existing user - rare, but
                    # don't crash signup. Log and roll back the email update.
                    s.rollback()
                    log.warning(
                        "email_changed rollback: workos_user_id=%s wanted email=%s but it's taken",
                        workos_user.id, workos_user.email,
                    )
                    u = s.query(User).filter_by(workos_user_id=workos_user.id).first()
            return u

        # Race-safe: check by email too (in case workos_user_id wasn't backfilled)
        u = s.query(User).filter(func.lower(User.email) == (workos_user.email or "").lower()).first()
        if u is not None:
            u.workos_user_id = workos_user.id
            u.email_verified = bool(workos_user.email_verified)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                u = s.query(User).filter_by(workos_user_id=workos_user.id).first()
            return u

        # First sign-in: create row as Explorer; super_admin role only for
        # Afshin's verified email. Without email_verified, an attacker could
        # WorkOS-signup as afshin@tradewave.ai (before the real row exists)
        # and inherit super_admin. Verification is the gate.
        first_role = ["user"]
        if workos_user.email == "afshin@tradewave.ai" and bool(getattr(workos_user, "email_verified", False)):
            first_role = ["super_admin", "user"]
        u = User(
            workos_user_id=workos_user.id,
            email=workos_user.email,
            email_verified=bool(workos_user.email_verified),
            first_name=getattr(workos_user, "first_name", None),
            last_name=getattr(workos_user, "last_name", None),
            roles=first_role,
            tier="explorer",
            legacy_wp_level=tier_to_legacy_level("explorer"),
        )
        s.add(u)
        try:
            s.commit()
            s.refresh(u)
        except IntegrityError:
            # F2.4 - two-tab signup race: the sibling worker won. Roll back our
            # insert, re-query by workos_user_id, and return the row that won.
            s.rollback()
            log.info("lazy_create_user race: re-querying workos_user_id=%s", workos_user.id)
            u = s.query(User).filter_by(workos_user_id=workos_user.id).first()
            if u is None:
                # Extremely unlikely: race resolved against email constraint, not
                # workos_user_id. Try by email.
                u = s.query(User).filter(func.lower(User.email) == (workos_user.email or "").lower()).first()
            if u is None:
                # Should not happen. Re-raise so caller sees the 500.
                raise
            return u
        # Audit
        write_audit(
            actor_label="workos_signin",
            action="user_created",
            target_user_id=u.id,
            details={"email": workos_user.email, "workos_user_id": workos_user.id},
        )
        # F2.15 - Mailerlite list-add (best-effort; never blocks user creation).
        # Reduced timeout to 2s inside email_utils so a Mailerlite blip does not
        # add up to 5s of delay on the signup hot path. Returns False fast if
        # MAILERLITE_API_KEY is placeholder.
        try:
            display_name = " ".join(filter(None, [
                getattr(workos_user, "first_name", None),
                getattr(workos_user, "last_name", None),
            ])) or None
            mailerlite_subscribe(workos_user.email, name=display_name)
            # New accounts start as explorer -> add to the explorer LEVEL group
            # (TW1/UMP parity). new_user=True keeps this to a single fast call.
            sync_mailerlite_level_group(workos_user.email, "explorer", None, new_user=True)
        except Exception as e:
            log.warning("mailerlite_subscribe raised for %s: %s", workos_user.email, e)
        return u
    finally:
        s.close()


def _auth_user_id(auth_user):
    """auth.user can be either a User dataclass or a dict (depends on SDK code path)."""
    return auth_user["id"] if isinstance(auth_user, dict) else auth_user.id


def get_current_user():
    """Decorator-friendly: returns Postgres User row or None."""
    g_user = getattr(g, "_current_user", "unset")
    if g_user != "unset":
        return g_user
    auth, _ = _read_sealed_session()
    if not auth:
        g._current_user = None
        return None
    db_user = current_user_from_db(_auth_user_id(auth.user))
    g._current_user = db_user
    return db_user


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = get_current_user()
        if u is None:
            # Bounce to WorkOS hosted SIGNUP (default for protected pricing/checkout pages - 
            # most cold visitors hitting these are new users).
            full_path = request.full_path.rstrip("?")
            url = _get_authorization_url(state=full_path, screen_hint="sign-up")
            return redirect(url)
        return view(*args, **kwargs)
    return wrapped


def require_super_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = get_current_user()
        if u is None:
            return redirect(_get_authorization_url(state=request.path))
        if "super_admin" not in (u.roles or []):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# ============================================================
# Health
# ============================================================

@app.route("/healthz")
def healthz():
    """Cheap health probe - checks DB.
    F2.2 - generic error response; details only to log.
    """
    try:
        s = DBSession()
        s.execute(select(User).limit(1))
        s.close()
        return jsonify({"ok": True, "db": "ok", "ts": datetime.now(timezone.utc).isoformat()})
    except Exception:
        log.exception("/healthz DB probe failed")
        return jsonify({"ok": False, "error": "healthcheck_failed"}), 500


# ============================================================
# Auth routes
# ============================================================

@app.route("/signup")
def signup():
    """Send user to WorkOS AuthKit hosted SIGNUP screen."""
    state = request.args.get("next") or "/account"
    url = _get_authorization_url(state=state, screen_hint="sign-up")
    return redirect(url)


@app.route("/login")
def login():
    """Send user to WorkOS AuthKit hosted LOGIN screen."""
    state = request.args.get("next") or "/account"
    url = _get_authorization_url(state=state, screen_hint="sign-in")
    return redirect(url)


@app.route("/auth/callback")
def auth_callback():
    """User returns from WorkOS with ?code=... - exchange for token + create session.

    F2.1 - `state` is treated as a same-origin path. We reject protocol-relative
    redirects ("//evil.com/x") and backslash-prefixed forms.
    F2.2 - error responses no longer leak request.args or exception strings to
    the browser; details go to the server log only.
    F2.3 - when WorkOS bounces the user back with ?error=access_denied (clicked
    Cancel on the hosted UI), redirect home instead of showing a 400 JSON page.
    """
    # F2.3 - user clicked Cancel / declined consent on WorkOS hosted UI
    workos_error = request.args.get("error")
    if workos_error:
        log.info("auth_callback: WorkOS returned error=%s", workos_error)
        return redirect("/")

    code = request.args.get("code")
    state = request.args.get("state") or "/account"

    if not code:
        # F2.2 - don't echo request.args; log them server-side instead
        log.warning("auth_callback: missing code; args=%s", dict(request.args))
        return jsonify({"error": "missing_code"}), 400

    try:
        result = workos_client.user_management.authenticate_with_code(code=code)
    except WorkOSBadRequestError as e:
        # Invalid / expired / already-used auth code is a CLIENT error, not 500.
        log.warning("auth_callback: invalid grant: %s", e)
        return jsonify({"error": "invalid_grant"}), 400
    except Exception:
        # F2.2 - log the full traceback, return a generic message
        log.exception("auth_callback: authenticate_with_code failed")
        return jsonify({"error": "auth_failed"}), 500

    # WorkOS 6.x: build the sealed cookie ourselves from the auth response
    user_dict = result.user.to_dict() if hasattr(result.user, "to_dict") else dict(result.user)
    impersonator_dict = None
    if result.impersonator is not None:
        impersonator_dict = result.impersonator.to_dict() if hasattr(result.impersonator, "to_dict") else dict(result.impersonator)
    try:
        sealed_session = seal_session_from_auth_response(
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            user=user_dict,
            impersonator=impersonator_dict,
            cookie_password=config.WORKOS_COOKIE_PASSWORD,
        )
    except Exception:
        log.exception("auth_callback: seal_session_from_auth_response failed")
        return jsonify({"error": "session_seal_failed"}), 500

    db_user = lazy_create_user(result.user)

    # Update last_login_at
    s = DBSession()
    try:
        db_user_obj = s.query(User).filter_by(id=db_user.id).first()
        db_user_obj.last_login_at = datetime.now(timezone.utc)
        s.commit()
    finally:
        s.close()

    # F2.1 - Build redirect with strict same-origin path validation. Rejects:
    #   "//evil.com/x"   protocol-relative
    #   "/\\evil.com"    backslash bypass
    #   "https://..."    absolute URL (any scheme)
    # Anything else that doesn't begin with "/" falls back to /account.
    safe_next = "/account"
    if (
        state
        and state.startswith("/")
        and not state.startswith("//")
        and not state.startswith("/\\")
    ):
        safe_next = state
    resp = make_response(redirect(safe_next))
    resp.set_cookie(
        SESSION_COOKIE,
        sealed_session,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=True,   # tunnel is HTTPS
        samesite="Lax",
        path="/",
    )
    return resp


@app.route("/logout", methods=["POST"])
@csrf.exempt
def logout():
    """Log out: revoke the WorkOS session server-side, clear our cookie, and
    redirect SAME-ORIGIN.

    We deliberately do NOT redirect the browser to the WorkOS hosted-logout URL.
    That is a cross-origin redirect, and the form that posts here is constrained
    by the nginx `form-action` CSP directive ('self' + Stripe/WorkOS/AuthKit/
    Mailerlite). The hosted-logout redirect chain trips that directive, so the
    browser silently BLOCKED the first click while the cookie still got deleted -
    which is why a second, cookieless click appeared to "work" (it skips the
    WorkOS hop and does a plain same-origin redirect).

    F2.16 - revoke_session() still invalidates the access/refresh tokens at WorkOS
    server-side (no front-channel redirect needed), so a leaked sealed cookie
    cannot keep talking to WorkOS. The only thing we forgo by not hitting the
    hosted-logout URL is clearing AuthKit's own SSO cookie in the browser; the
    session itself is dead, so this is an acceptable trade for a logout that works
    on the first click. Relative "/" guarantees the redirect stays same-origin
    (tw2-dev/stage/prod) regardless of proxy/Host quirks, satisfying form-action.
    """
    sealed = request.cookies.get(SESSION_COOKIE)
    sid_for_revoke = None
    if sealed:
        try:
            sess = workos_client.user_management.load_sealed_session(
                session_data=sealed,
                cookie_password=config.WORKOS_COOKIE_PASSWORD,
            )
            # Pull the sid claim from the access token for the explicit revoke.
            try:
                auth_result = sess.authenticate()
                if getattr(auth_result, "authenticated", False):
                    sid_for_revoke = getattr(auth_result, "session_id", None)
            except Exception:
                # authenticate() can fail on an expired access token - fine, the
                # cookie delete below still logs the user out locally.
                pass
        except Exception as e:
            log.warning("logout: load_sealed_session failed: %s", e)

    # F2.16 - explicit server-side session revoke (best-effort)
    if sid_for_revoke:
        try:
            workos_client.user_management.revoke_session(session_id=sid_for_revoke)
        except Exception as e:
            log.warning("revoke_session(sid=%s) failed: %s", sid_for_revoke, e)

    resp = make_response(redirect("/"))
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# ============================================================
# JSON API for the React app to discover current user
# ============================================================

@app.route("/api/me")
def api_me():
    u = get_current_user()
    if u is None:
        resp = jsonify({"authenticated": False})
        resp.headers["Cache-Control"] = "private, no-store"
        return resp, 200
    resp = jsonify({
        "authenticated": True,
        "user": u.to_dict(),
        "wp_user_levels": tier_to_wp_user_levels(u.tier or "explorer"),
        "legacy_wp_level": tier_to_legacy_level(u.tier or "explorer"),
    })
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ============================================================
# /api/contact - Tier-1 support form
# ============================================================
# Replaces the legacy mailto-only form. Anonymous endpoint; abuse-gated by
# Cloudflare Turnstile + a hidden honeypot field. The DB row is canonical;
# the two emails (notification + visitor confirmation) are best-effort. See
# web/contact_form.py + email_utils.resend_send_email + migration
# 7a5c3b9d12ef for the rest of the stack.
_CONTACT_BODY_MAX = 8000      # 8KB - generous for "tell us what's on your mind"; bigger = abuse
_CONTACT_NAME_MAX = 200
_CONTACT_EMAIL_MAX = 320      # RFC 5321 max
_CONTACT_RATE_LIMIT_PER_IP = 5   # tickets per IP_hash per hour before we mark as spam


def _client_ip() -> str:
    """Honour the X-Forwarded-For chain set by nginx. nginx sets X-Real-IP to
    the immediate peer (the CF tunnel exit) which is the closest thing to a
    client IP we have; CF-Connecting-IP is what Cloudflare actually populates."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


@app.route("/api/contact", methods=["POST"])
@csrf.exempt  # anonymous endpoint; abuse gate is Turnstile + honeypot, not CSRF
def api_contact():
    from contact_form import (
        verify_turnstile, hash_ip, enrich_user_context,
        format_notification_email, format_confirmation_email,
    )
    from email_utils import resend_send_email

    data = request.get_json(silent=True) or {}

    # Honeypot - a hidden field named "company" that humans never fill in. If
    # set, silently return success so bots think they got through.
    if (data.get("company") or "").strip():
        log.info("api_contact honeypot tripped ip=%s", _client_ip())
        return jsonify({"ok": True, "public_id": None, "note": "thanks"}), 200

    name    = (data.get("name") or "").strip()
    email   = (data.get("email") or "").strip().lower()
    topic   = (data.get("topic") or "other").strip().lower()
    body    = (data.get("message") or "").strip()
    token   = (data.get("turnstile_token") or "").strip()

    # Field validation - fail-fast on missing/oversize; specific 400 codes for
    # the JS so it can show inline messages.
    if not name or len(name) > _CONTACT_NAME_MAX:
        return jsonify({"ok": False, "error": "name_invalid"}), 400
    if not email or "@" not in email or len(email) > _CONTACT_EMAIL_MAX:
        return jsonify({"ok": False, "error": "email_invalid"}), 400
    if topic not in SUPPORT_TICKET_TOPICS:
        return jsonify({"ok": False, "error": "topic_invalid"}), 400
    if not body or len(body) > _CONTACT_BODY_MAX:
        return jsonify({"ok": False, "error": "message_invalid"}), 400

    ip = _client_ip()
    if not verify_turnstile(token, remote_ip=ip):
        return jsonify({"ok": False, "error": "captcha_failed"}), 400

    ip_hashed = hash_ip(ip)
    user = get_current_user()
    enrichment = enrich_user_context(user)

    # Per-IP soft rate limit: if this IP_hash has 5+ open tickets in the last
    # hour, accept the row but mark it spam (still useful as a signal in the
    # admin) and skip the email blast. Anonymous = abuse, so we throttle.
    initial_status = "open"
    if ip_hashed:
        s = DBSession()
        try:
            recent = s.execute(
                select(func.count(SupportTicket.id))
                .where(SupportTicket.ip_hash == ip_hashed)
                .where(SupportTicket.created_at > func.now() - timedelta(hours=1))
            ).scalar() or 0
            if recent >= _CONTACT_RATE_LIMIT_PER_IP:
                initial_status = "spam"
                log.warning("api_contact rate-limit tripped ip_hash=%s recent=%s email=%s",
                            ip_hashed[:12], recent, email)
        finally:
            s.close()

    s = DBSession()
    try:
        ticket = SupportTicket(
            user_id=user.id if user is not None else None,
            email=email,
            name=name,
            topic=topic,
            body=body,
            status=initial_status,
            enrichment=enrichment or None,
            user_agent=(request.headers.get("User-Agent") or "")[:500],
            ip_hash=ip_hashed,
        )
        s.add(ticket)
        s.commit()
        s.refresh(ticket)  # pick up server-default ticket_number + computed public_id
        ticket_public_id = ticket.public_id

        if initial_status == "spam":
            # Don't email anyone for spam. Visitor still gets a 200 so we don't
            # signal the rate-limit to the bot.
            return jsonify({"ok": True, "public_id": ticket_public_id}), 200

        # Notification to support (Reply-To = customer so hitting Reply in
        # the inbox responds directly to them).
        n_subject, n_body = format_notification_email(ticket)
        resend_send_email(
            to=config.SUPPORT_EMAIL_TO,
            subject=n_subject,
            body_text=n_body,
            reply_to=email,
        )

        # Confirmation to visitor.
        c_subject, c_body = format_confirmation_email(ticket)
        resend_send_email(
            to=email,
            subject=c_subject,
            body_text=c_body,
            reply_to=config.SUPPORT_EMAIL_TO,
        )

        return jsonify({"ok": True, "public_id": ticket_public_id}), 200
    except Exception as e:
        s.rollback()
        log.exception("api_contact insert failed: %s", e)
        return jsonify({"ok": False, "error": "server_error"}), 500
    finally:
        s.close()


# ============================================================
# /app/ - React shell with REAL session globals injected
# (replaces the milestone-1 nginx sub_filter stub)
# ============================================================

REACT_BUILD_INDEX = Path("/home/flask/web-react/build/index.html")
TW_HEADER_TEMPLATE = Path("/home/flask/site/templates/_tw_header.html")


def generate_ltk(user) -> str:
    """Sign a short-lived JWT containing the user's identity claims.
    The appserver verifies this with config.APPSERVER_JWT_SECRET when
    useUMP=False, and uses its claims for is_admin and tier resolution.

    F2.13 - adds aud/iss claims so the appserver can defend against tokens
    minted by other services that might share the same secret. Appserver
    enforces `audience="tw2-appserver"` and `issuer="tw2-web"` at all 16
    jwt.decode() call sites in appserver.py (F3 closed).
    """
    return jwt.encode(
        {
            "user_id": str(user.id),
            "workos_user_id": user.workos_user_id,
            "email": user.email,
            "tier": user.tier or "explorer",
            "legacy_level": tier_to_legacy_level(user.tier or "explorer"),
            "roles": user.roles or ["user"],
            "is_admin": "super_admin" in (user.roles or []),
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 8,  # 8-hour LTK
        },
        config.APPSERVER_JWT_SECRET,
        algorithm="HS256",
    )


@app.route("/app", endpoint="app_index_no_slash")
@app.route("/app/", endpoint="app_index")
def app_index():
    """Serve React build/index.html with REAL window globals injected.
    Unauthenticated users are redirected to /login with a return-to /app/.
    """
    u = get_current_user()
    if u is None:
        # Preserve the full path (incl. ?o=BASE64 pattern param from static reports)
        # so that after auth the user lands back on the wave viewer with their pattern
        # intact. screen_hint="sign-up" prompts cold visitors to create a free account.
        return_to = request.full_path.rstrip("?")
        return redirect(_get_authorization_url(state=return_to, screen_hint="sign-up"))

    if not REACT_BUILD_INDEX.exists():
        return jsonify({"error": "React build/index.html not found", "path": str(REACT_BUILD_INDEX)}), 500

    html = REACT_BUILD_INDEX.read_text()
    ltk = generate_ltk(u)
    user_id = str(u.id)
    user_level = tier_to_legacy_level(u.tier or "explorer")
    # F2.14 - JSON-escape every value that is interpolated into the inline
    # <script>. The previous f-string approach would break if u.email or
    # any other field contained a `"`, `</script>`, line terminator, or null
    # byte - all valid in DB strings, none safe in a raw-quoted JS literal.
    #
    # json.dumps quotes the string and escapes inner quotes / control chars,
    # but does NOT escape `</script>` - which would still close the script
    # tag in HTML parsing. We do the standard `</` -> `<\/` rewrite to fully
    # neutralize that vector. The result is still valid JSON and parses to
    # the original string at JS-runtime.
    def _js_safe(v):
        return _json.dumps(v).replace("</", "<\\/")
    is_admin_bool = "super_admin" in (u.roles or [])
    inject = (
        '<script>'
        f'window.current_user_id={_js_safe(user_id)};'
        f'window.current_user_level={_js_safe(user_level)};'
        f'window.ltk={_js_safe(ltk)};'
        f'window.tw2_user_email={_js_safe(u.email)};'
        f'window.tw2_user_tier={_js_safe(u.tier or "explorer")};'
        f'window.tw2_is_admin={"true" if is_admin_bool else "false"};'
        f'window.tw2_user_roles={_js_safe(u.roles or ["user"])};'
        f'window.tw2_env={_js_safe(config.tw2_env)};'
        '</script>'
    )
    # Inject right before </head> (same hook the milestone-1 nginx sub_filter used)
    html = html.replace("</head>", inject + "</head>", 1)

    # Replace the empty #main-header stub with the shared TW2 header template.
    # The template's #main-header id is what App.js / MobileLayout*.js read for
    # clientHeight, so the React resize calc gets the real header height.
    if TW_HEADER_TEMPLATE.exists():
        header_html = TW_HEADER_TEMPLATE.read_text()
        html = html.replace(
            '<header id="main-header" style="display:none"></header>',
            header_html,
            1,
        )
        # body.page-template hides the header on mobile so React's mobile layout owns the screen
        html = html.replace("<body>", '<body class="page-template">', 1)

    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ============================================================
# Account page (minimal - phase 4 will fancy this up)
# ============================================================

def _format_unix_date(ts):
    """Convert a Unix timestamp (int|None) to YYYY-MM-DD UTC, or None."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return None


def _stripe_subscription_summary(sub_id):
    """Pull billing interval + period dates from a Stripe subscription.
    Returns (interval, current_period_end_str, start_date_str) - any/all may be None.
    Never raises; logs and returns Nones on Stripe errors."""
    if not sub_id or not _stripe_configured():
        return (None, None, None)
    try:
        sub = stripe.Subscription.retrieve(sub_id, expand=["items.data.price"])
    except Exception as e:
        log.warning("stripe.Subscription.retrieve failed for %s: %s", sub_id, e)
        return (None, None, None)

    try:
        sub_d = sub.to_dict() if hasattr(sub, "to_dict") else dict(sub)
    except Exception:
        sub_d = {}

    interval = None
    items_d = (sub_d.get("items") or {}).get("data") or []
    if items_d:
        price_d = items_d[0].get("price") or {}
        recurring = price_d.get("recurring") or {}
        if isinstance(recurring, dict):
            interval = recurring.get("interval")

    cpe = sub_d.get("current_period_end")
    if cpe is None:
        # Newer Stripe API surfaces period end on the item, not the sub
        if items_d:
            cpe = items_d[0].get("current_period_end")
    next_renewal_str = _format_unix_date(cpe)

    started_str = _format_unix_date(sub_d.get("start_date"))

    return (interval, next_renewal_str, started_str)


@app.route("/account")
@require_login
def account():
    u = get_current_user()

    billing_interval = None
    next_renewal_date = None
    started_date = None
    if u and u.stripe_subscription_id:
        billing_interval, next_renewal_date, started_date = _stripe_subscription_summary(
            u.stripe_subscription_id
        )

    return render_template(
        "account.html",
        user=u,
        billing_interval=billing_interval,
        next_renewal_date=next_renewal_date,
        started_date=started_date,
    )


# ============================================================
# Pricing page - simple fallback so /pricing isn't a 404
# (Phase 5 will turn into a real Stripe Checkout flow)
# ============================================================

@app.route("/pricing")
def pricing():
    # Send users to the rich pricing section on the home page (single source of truth)
    return redirect("/#pricing", code=302)


# ============================================================
# Stripe Checkout (Phase 5)
# ============================================================

# Map (tier, period) → Stripe Product name (case-insensitive match)
TIER_PRODUCT_NAMES = {
    ("analyst",    "monthly"): ("analyst",    "month"),
    ("analyst",    "yearly"):  ("analyst",    "year"),
    ("strategist", "monthly"): ("strategist", "month"),
    ("strategist", "yearly"):  ("strategist", "year"),
}

# Cache: (tier, period) → price object, fetched once
_price_cache = {}


def _stripe_configured():
    if 'PLACEHOLDER' in (config.STRIPE_SECRET_KEY or ''):
        return False
    if 'PLACEHOLDER' in (config.STRIPE_PUBLISHABLE_KEY or ''):
        return False
    return True


def _refresh_price_cache():
    """Bucket active Stripe prices into (tier, period) slots — metadata-only.

    A price is used ONLY if its product carries all three metadata keys:
      product_line == "eod", tier in {analyst,strategist}, period in {monthly,yearly}.

    The legacy product-name-substring fallback was REMOVED (2026-05-19). The
    shared Stripe account holds ~14 active legacy UMP per-member prices (no
    metadata) that name-collided nondeterministically, plus the placeholder
    test prices, and a separate "TradeWave RT" product line is coming.
    Requiring explicit product_line=eod metadata makes resolution deterministic
    and immune to legacy / RT / placeholder prices — they have no (or non-eod)
    metadata and are simply ignored. Set tier/period/product_line on each EOD
    product in the Stripe dashboard; nothing else is discoverable.

    Paginates so >100 active prices don't get silently truncated.
    """
    if not _stripe_configured():
        return
    valid_tiers = {"analyst", "strategist"}
    valid_periods = {"monthly", "yearly"}
    try:
        for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
            prod = p.product
            if not isinstance(prod, dict):
                prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
            metadata = prod.get("metadata") or {}
            md_line = (metadata.get("product_line") or "").strip().lower()
            md_tier = (metadata.get("tier") or "").strip().lower()
            md_period = (metadata.get("period") or "").strip().lower()
            if md_line != "eod" or md_tier not in valid_tiers or md_period not in valid_periods:
                continue  # legacy / RT / placeholder / unscoped price — ignore
            slot = (md_tier, md_period)
            existing = _price_cache.get(slot)
            if existing is not None and getattr(existing, "id", None) != getattr(p, "id", None):
                log.warning(
                    "price_cache: >1 active EOD price for slot %s (%s, %s) — ambiguous; "
                    "archive the extra in Stripe. Using last-seen.",
                    slot, getattr(existing, "id", "?"), getattr(p, "id", "?"),
                )
            _price_cache[slot] = p
    except Exception:
        log.exception("Failed to refresh Stripe price cache")


def _price_for(tier, period):
    if not _price_cache:
        _refresh_price_cache()
    return _price_cache.get((tier, period))


def _price_id_for(tier, period):
    p = _price_for(tier, period)
    return p.id if p else None


def _tier_period_for_price(price_id):
    if not _price_cache:
        _refresh_price_cache()
    for key, p in _price_cache.items():
        if p.id == price_id:
            return key
    return (None, None)


# --- Developer API product line (product_line == "api") -> users.api_tier -----------------
# A SEPARATE Stripe subscription line from the web/EOD line: its prices carry product
# metadata product_line=api + tier in {dev,pro,business} (see web/api_portal/
# create_api_products.py). The webhook routes by the price's product_line and writes
# users.api_tier (NEVER users.tier), so the two lines never clobber each other. Period is
# irrelevant to the api tier (unlike eod, which needs it for the Mailerlite group sync), so
# we key price id -> tier only.
_api_price_tier = {}  # stripe price id -> api tier ('dev'|'pro'|'business')


def _refresh_api_price_cache():
    if not _stripe_configured():
        return
    valid = {"dev", "pro", "business"}
    try:
        for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
            prod = p.product
            if not isinstance(prod, dict):
                prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
            md = prod.get("metadata") or {}
            if (md.get("product_line") or "").strip().lower() != "api":
                continue
            tier = (md.get("tier") or "").strip().lower()
            if tier in valid:
                _api_price_tier[p.id] = tier
    except Exception:
        log.exception("Failed to refresh Stripe API price cache")


def _api_tier_for_price(price_id):
    """Return the API tier ('dev'|'pro'|'business') for a Stripe price id, or None if it is
    not an API-line price."""
    if not _api_price_tier:
        _refresh_api_price_cache()
    return _api_price_tier.get(price_id)


def _resolve_affiliate_promo(raw):
    """Resolve an affiliate referral code (e.g. from ?code=ANNE / ?via=ANNE, or
    a hidden checkout-form field) to an ACTIVE affiliate's Stripe promotion-code
    id, or None. Unknown / paused / terminated / malformed codes return None so
    checkout proceeds normally (manual promo entry). No cookie - the code must
    be present on the checkout request itself."""
    if not raw:
        return None
    import affiliate_service as afs
    code = afs.normalize_code(raw)
    if not afs.CODE_RE.match(code):
        return None
    s = DBSession()
    try:
        from models import Affiliate
        aff = (s.query(Affiliate)
               .filter(Affiliate.code == code, Affiliate.status == "active")
               .first())
        return aff.stripe_promotion_code_id if aff else None
    finally:
        s.close()


# State-changing endpoint: POST only. The pricing template uses
# <form method="post"> hidden-input forms to hit this route.
@app.route("/api/stripe/create-checkout", methods=["POST"])
@csrf.exempt
@require_login
def stripe_create_checkout():
    """Initiate Stripe Checkout for the requested tier+period.
    Required params: tier=analyst|strategist, period=monthly|yearly
    Accepted via form data (POST).
    """
    if not _stripe_configured():
        return jsonify({
            "error": "stripe_not_configured",
            "message": "Stripe keys / price IDs are placeholders. Edit /home/flask/config.py and restart the web tier.",
        }), 503

    # Pull tier/period from form (POST).
    tier   = (request.form.get("tier")   or "").lower()
    period = (request.form.get("period") or "").lower()
    price_id = _price_id_for(tier, period)
    if not price_id:
        return jsonify({
            "error": "price_not_found",
            "message": f"No Stripe price found for tier={tier!r} period={period!r}. "
                       f"Expected a product whose name contains {TIER_PRODUCT_NAMES.get((tier,period), ('?','?'))[0]!r} "
                       f"with a recurring interval of {TIER_PRODUCT_NAMES.get((tier,period), ('?','?'))[1]!r}.",
        }), 400

    u = get_current_user()
    public_host = os.environ.get("TW2_PUBLIC_HOST", "tw2.trxstat.com")
    success_url = f"https://{public_host}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url  = f"https://{public_host}/pricing?cancelled=1"

    # Validate stored stripe_customer_id still exists AND isn't soft-deleted; clear stale ones
    valid_customer_id = None
    if u.stripe_customer_id:
        try:
            cust = stripe.Customer.retrieve(u.stripe_customer_id)
            if getattr(cust, "deleted", False):
                raise stripe.error.InvalidRequestError("customer soft-deleted", None)
            valid_customer_id = u.stripe_customer_id
        except stripe.error.InvalidRequestError:
            log.info("Stale stripe_customer_id for user %s; clearing", u.id)
            s = DBSession()
            try:
                row = s.query(User).filter_by(id=u.id).first()
                row.stripe_customer_id = None
                row.stripe_subscription_id = None
                row.stripe_subscription_status = None
                s.commit()
            finally:
                s.close()

    # Affiliate referral code: from a direct link (?code=ANNE / ?via=ANNE), a
    # hidden checkout-form field, or the first-party `tw_ref` cookie set on the
    # affiliate's landing page (so attribution survives navigation + the signup
    # round-trip). If it resolves to an active affiliate we PRE-APPLY their
    # Stripe promotion code, so the discount shows already applied AND the sale
    # is attributed. Pre-applying via `discounts` is mutually exclusive with
    # allow_promotion_codes.
    promo_code_id = _resolve_affiliate_promo(
        request.values.get("code") or request.values.get("via")
        or request.cookies.get("tw_ref"))

    try:
        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(u.id),
            subscription_data={
                "trial_period_days": 7,
                "metadata": {"tw2_user_id": str(u.id), "tw2_tier_target": tier},
            },
        )
        if promo_code_id:
            kwargs["discounts"] = [{"promotion_code": promo_code_id}]
        else:
            kwargs["allow_promotion_codes"] = True
        if valid_customer_id:
            kwargs["customer"] = valid_customer_id
        else:
            kwargs["customer_email"] = u.email
        try:
            session_obj = stripe.checkout.Session.create(**kwargs)
        except Exception:
            # A pre-applied promo code Stripe rejects (expired / inactive /
            # min-amount / already-redeemed) must NOT break checkout: retry
            # once, letting the customer enter a code manually instead.
            if promo_code_id:
                log.warning("checkout: pre-applied promo %s rejected; retrying "
                            "with manual entry", promo_code_id)
                kwargs.pop("discounts", None)
                kwargs["allow_promotion_codes"] = True
                session_obj = stripe.checkout.Session.create(**kwargs)
            else:
                raise
        return redirect(session_obj.url, code=303)
    except Exception:
        # F2.2 - log the full traceback, return generic message
        log.exception("stripe checkout creation failed")
        return jsonify({"error": "stripe_error"}), 500


@app.route("/stripe/success")
@require_login
def stripe_success():
    """Stripe redirects here after successful checkout. Poll the session,
    update our user row, then send them to /app/.

    F2.11 - idempotent: if we've already processed this checkout session
    (StripeEvent row with stripe_event_id=session_id exists), short-circuit
    and redirect to /app/?upgraded=1 without re-running mutations.
    F2.10 - User row read happens with SELECT ... FOR UPDATE so concurrent
    /stripe/success and /webhooks/stripe handlers don't race on tier writes.
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return redirect("/pricing")

    u = get_current_user()

    # F2.11 - idempotency: if the matching StripeEvent already exists, skip
    # the work and just redirect. Either /webhooks/stripe handled it, or a
    # previous visit to this URL did. This stops user-driven page refreshes
    # from racing against the webhook handler.
    s_idem = DBSession()
    try:
        existing = s_idem.query(StripeEvent).filter_by(
            stripe_event_id=session_id,
            event_type="checkout.session.completed",
        ).first()
        if existing:
            log.info("/stripe/success: session_id=%s already processed; redirecting", session_id)
            return redirect("/app/?upgraded=1")
    finally:
        s_idem.close()

    try:
        sess = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "subscription.items.data.price"])
    except Exception:
        # F2.2 - log full traceback, generic response
        log.exception("stripe.session.retrieve failed for session_id=%s", session_id)
        return jsonify({"error": "stripe_lookup_failed"}), 500

    # StripeObject is NOT a dict subclass and has no .get(). .to_dict() yields a
    # fully-recursive plain dict - the only safe way to traverse the tree.
    sess_d = sess.to_dict() if hasattr(sess, "to_dict") else dict(sess)

    # SEC-C1 - bind the Stripe session to the authenticated user. Without this,
    # any logged-in user can visit /stripe/success?session_id=<someone_elses_id>
    # and have that other user's paid tier flipped onto their own row. Stripe
    # populates client_reference_id from the value we set in stripe_create_checkout
    # (str(u.id)); the subscription metadata carries the same id as a fallback.
    expected_user_id = str(u.id)
    client_ref = sess_d.get("client_reference_id")
    sub_meta_user = None
    sub_raw_for_id = sess_d.get("subscription")
    if isinstance(sub_raw_for_id, dict):
        sub_meta = sub_raw_for_id.get("metadata") or {}
        if isinstance(sub_meta, dict):
            sub_meta_user = sub_meta.get("tw2_user_id")

    bound_user_id = client_ref or sub_meta_user
    if bound_user_id != expected_user_id:
        log.warning(
            "stripe_success: client_reference mismatch user_id=%s session=%s "
            "client_ref=%s sub_meta_user=%s ip=%s ua=%s",
            expected_user_id, session_id, client_ref, sub_meta_user,
            request.headers.get("X-Forwarded-For", request.remote_addr),
            request.headers.get("User-Agent", "-"),
        )
        try:
            write_audit(
                actor_label="stripe_success",
                action="stripe_session_user_mismatch",
                target_user_id=u.id,
                details={
                    "stripe_session_id": session_id,
                    "expected_user_id": expected_user_id,
                    "client_reference_id": str(client_ref) if client_ref is not None else None,
                    "subscription_metadata_user_id": str(sub_meta_user) if sub_meta_user is not None else None,
                },
            )
        except Exception:
            log.exception("stripe_success: write_audit failed for mismatch event")
        return jsonify({"error": "session_user_mismatch"}), 403

    # SEC-C1 - never write an upgrade for an unpaid session. Stripe checkout
    # sessions can be retrieved before payment lands (e.g. user closes the tab
    # mid-flow); writing the tier change off an unpaid session would let any
    # user upgrade for free by hitting /stripe/success with their own
    # half-completed session_id.
    payment_status = sess_d.get("payment_status")
    if payment_status != "paid":
        log.warning(
            "stripe_success: refusing unpaid session user_id=%s session=%s status=%s",
            expected_user_id, session_id, payment_status,
        )
        return redirect("/pricing?payment_pending=1")

    # Resolve tier from price_id
    new_tier = None
    ml_period = None  # billing period for the Mailerlite level-group sync
    sub_raw = sess_d.get("subscription")
    sub_d = sub_raw if isinstance(sub_raw, dict) else {}
    sub_id = sub_d.get("id") if sub_d else (sub_raw if isinstance(sub_raw, str) else None)
    sub_status = sub_d.get("status") if sub_d else None
    if sub_d:
        items_d = sub_d.get("items") or {}
        items_list = items_d.get("data", []) if isinstance(items_d, dict) else []
        if items_list:
            price_d = (items_list[0] or {}).get("price") or {}
            price_id = price_d.get("id") if isinstance(price_d, dict) else None
            if price_id:
                tier, period = _tier_period_for_price(price_id)
                if tier:
                    new_tier = tier
                    ml_period = period

    customer_id = sess_d.get("customer")
    if customer_id and not isinstance(customer_id, str):
        # If customer was expanded into a nested object, pull its id
        customer_id = customer_id.get("id") if isinstance(customer_id, dict) else None

    # F2.10 - Update Postgres with row-level locking.
    audit_payload = None
    rebind_conflict_payload = None
    s = DBSession()
    try:
        db_user = s.query(User).filter_by(id=u.id).with_for_update().first()
        # F2.9 - only assign stripe_customer_id if no OTHER user already owns it.
        # Otherwise we'd silently steal a customer record from a different account
        # row, which is data corruption that's hard to unwind.
        if customer_id and not db_user.stripe_customer_id:
            existing_owner = s.query(User).filter_by(stripe_customer_id=customer_id).filter(User.id != db_user.id).first()
            if existing_owner:
                log.error(
                    "stripe customer_id=%s already on user %s; refusing to rebind to %s",
                    customer_id, existing_owner.id, db_user.id,
                )
                rebind_conflict_payload = dict(
                    actor_label="stripe_success",
                    action="stripe_customer_rebind_conflict",
                    target_user_id=db_user.id,
                    details={"stripe_customer_id": customer_id, "existing_owner_user_id": str(existing_owner.id), "stripe_session_id": session_id},
                )
            else:
                db_user.stripe_customer_id = customer_id
        if sub_id:
            db_user.stripe_subscription_id = sub_id
        if sub_status:
            db_user.stripe_subscription_status = sub_status
        if new_tier and new_tier != db_user.tier:
            old_tier = db_user.tier
            db_user.tier = new_tier
            db_user.legacy_wp_level = tier_to_legacy_level(new_tier)
            # Defer write_audit to after this session commits - write_audit
            # reuses the same scoped_session and closing it would expunge
            # our pending db_user mutations.
            audit_payload = dict(
                actor_label="stripe_success",
                action="tier_changed",
                target_user_id=db_user.id,
                details={"from": old_tier, "to": new_tier, "stripe_session_id": session_id, "stripe_sub_id": sub_id},
            )
        try:
            s.commit()
        except IntegrityError as ie:
            # Race: webhook+success path both committed stripe_customer_id
            # simultaneously, or the unique constraint on stripe_subscription_id
            # rejected. Roll back; the webhook side will replay via Stripe retry
            # and will see the now-set value on its next pass.
            s.rollback()
            log.warning("stripe_success commit IntegrityError uid=%s session=%s err=%s",
                        db_user.id if db_user else None, session_id, ie)
            return jsonify({"error": "race_with_webhook_retry_shortly"}), 503
    finally:
        s.close()

    if audit_payload:
        write_audit(**audit_payload)
    if rebind_conflict_payload:
        write_audit(**rebind_conflict_payload)

    # Mailerlite level-group sync (TW1/UMP parity) - best-effort, post-commit.
    if new_tier:
        sync_mailerlite_level_group(u.email, new_tier, ml_period, new_user=False)

    return redirect("/app/?upgraded=1")


@app.route("/stripe/cancel")
def stripe_cancel():
    return redirect("/pricing?cancelled=1")


@app.route("/account/manage-subscription")
@require_login
def manage_subscription():
    """Redirect logged-in user to Stripe Customer Portal where they can
    cancel, swap card, change plan, view invoices, download receipts."""
    u = get_current_user()
    if not u.stripe_customer_id:
        return redirect("/pricing?no_subscription=1")
    if not _stripe_configured():
        return jsonify({"error": "stripe_not_configured"}), 503

    # Validate customer isn't stale/soft-deleted
    try:
        cust = stripe.Customer.retrieve(u.stripe_customer_id)
        if getattr(cust, "deleted", False):
            raise stripe.error.InvalidRequestError("customer soft-deleted", None)
    except stripe.error.InvalidRequestError:
        log.info("Stale stripe_customer_id on manage_subscription for user %s; clearing", u.id)
        s = DBSession()
        try:
            row = s.query(User).filter_by(id=u.id).first()
            row.stripe_customer_id = None
            row.stripe_subscription_id = None
            row.stripe_subscription_status = None
            s.commit()
        finally:
            s.close()
        return redirect("/pricing?no_subscription=1")

    try:
        public_host = os.environ.get("TW2_PUBLIC_HOST", "tw2.trxstat.com")
        session_obj = stripe.billing_portal.Session.create(
            customer=u.stripe_customer_id,
            return_url=f"https://{public_host}/account",
        )
        return redirect(session_obj.url, code=303)
    except Exception:
        # F2.2 - log full traceback, generic response
        log.exception("portal session creation failed")
        return jsonify({"error": "portal_session_failed"}), 500


# ============================================================
# Webhook receivers
# ============================================================

@app.route("/webhooks/workos", methods=["POST"])
@csrf.exempt
def webhook_workos():
    """Receive WorkOS events (user.created/updated/deleted). Lazy-sync on login
    handles most cases; this is just a stub until cloudflared+webhook is wired."""
    return jsonify({"received": True, "note": "stubbed"}), 200


@app.route("/webhooks/stripe", methods=["POST"])
@csrf.exempt
def webhook_stripe():
    """Stripe webhook handler with signature verification. Reacts to:
      - checkout.session.completed       → confirm new subscription
      - customer.subscription.created    → create/refresh subscription
      - customer.subscription.updated    → tier change, trial end, status change
      - customer.subscription.deleted    → cancellation/downgrade
      - invoice.payment_failed           → flag the user, optionally notify
      - invoice.payment_succeeded        → confirm renewal (low priority)
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    # SEC-H4 - fail closed when the webhook secret is missing or still a
    # placeholder. The previous fail-open path let a forged checkout.session.completed
    # event flip a user to Strategist for free if ops forgot to rotate the
    # placeholder at staging/prod cutover. Refuse to process the webhook
    # rather than parse unsigned JSON; ops must explicitly set the real
    # secret in /etc/tradewave/secrets.env (STRIPE_WEBHOOK_SECRET) before
    # this route can accept events.
    secret = getattr(config, "STRIPE_WEBHOOK_SECRET", "") or ""
    if not secret or "PLACEHOLDER" in secret:
        log.error(
            "webhook_stripe: STRIPE_WEBHOOK_SECRET missing or placeholder; "
            "refusing webhook ip=%s ua=%s",
            request.headers.get("X-Forwarded-For", request.remote_addr),
            request.headers.get("User-Agent", "-"),
        )
        return jsonify({"error": "webhook_secret_not_configured"}), 503
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:
        log.warning("Stripe webhook signature verification failed: %s", e)
        return jsonify({"error": "invalid_signature"}), 400

    # Normalize: convert Stripe Event object → plain nested dict so .get() is safe.
    if not isinstance(event, dict):
        try:
            event = event.to_dict()
        except Exception:
            # Last-ditch: pull fields manually
            event = {"id": event["id"], "type": event["type"], "data": {"object": event["data"]["object"]}}
    event_id   = event.get("id")
    event_type = event.get("type")
    data_raw   = (event.get("data") or {}).get("object") or {}
    # data_raw can still be a StripeObject if event came in as a dict wrapping a StripeObject;
    # be defensive and convert if needed.
    if not isinstance(data_raw, dict):
        data_obj = data_raw.to_dict() if hasattr(data_raw, "to_dict") else dict(data_raw)
    else:
        data_obj = data_raw

    s = DBSession()
    try:
        # Idempotency - if we already saw this event_id, skip.
        # SELECT-then-INSERT can lose the race to a sibling worker; the
        # IntegrityError below is the second line of defence.
        existing = s.query(StripeEvent).filter_by(stripe_event_id=event_id).first()
        if existing:
            return jsonify({"received": True, "duplicate": True}), 200

        # F2.7 - event was already normalized to a plain dict above; now
        # additionally scrub Decimal types so the JSONB insert doesn't blow up
        # when Stripe returns numeric fields as Decimal.
        payload_dict = _json_safe(event)
        evrow = StripeEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=payload_dict,
        )
        s.add(evrow)
        try:
            s.commit()
        except IntegrityError:
            # Race: a sibling worker inserted the same event_id concurrently.
            # That worker will process it; we ack 200 so Stripe stops retrying.
            s.rollback()
            log.info("Concurrent duplicate Stripe webhook %s - returning 200", event_id)
            return jsonify({"received": True, "duplicate": True, "race": True}), 200

        # Determine which user this event affects
        customer_id = None
        sub_id = None
        sub_status = None
        price_id = None
        client_ref = None  # our user UUID, passed in checkout.create as client_reference_id
        sub_metadata = None
        cust_email = None

        if event_type == "checkout.session.completed":
            customer_id = data_obj.get("customer")
            sub_id = data_obj.get("subscription")
            client_ref = data_obj.get("client_reference_id")
            cust_email = data_obj.get("customer_email") or (data_obj.get("customer_details") or {}).get("email")

        elif event_type in ("customer.subscription.created",
                            "customer.subscription.updated",
                            "customer.subscription.deleted"):
            customer_id = data_obj.get("customer")
            sub_id = data_obj.get("id")
            sub_status = data_obj.get("status") or ("canceled" if event_type.endswith("deleted") else None)
            items = (data_obj.get("items") or {}).get("data") or []
            if items:
                price_obj = items[0].get("price") or {}
                price_id = price_obj.get("id")
            sub_metadata = data_obj.get("metadata") or {}
            client_ref = sub_metadata.get("tw2_user_id")

        elif event_type == "invoice.payment_failed":
            customer_id = data_obj.get("customer")
            sub_id = data_obj.get("subscription")
            sub_status = "past_due"

        elif event_type == "invoice.payment_succeeded":
            customer_id = data_obj.get("customer")
            sub_id = data_obj.get("subscription")
            # No tier change; just record the event

        # Look up our user - try in order: stripe_customer_id, client_reference_id (our UUID),
        # email lookup against Stripe customer record. Whichever finds the row wins.
        # F2.10 - every successful lookup is locked with SELECT ... FOR UPDATE so
        # a concurrent /stripe/success or sibling webhook serializes on tier writes.
        db_user = None
        if customer_id:
            db_user = s.query(User).filter_by(stripe_customer_id=customer_id).with_for_update().first()
        if not db_user and client_ref:
            try:
                import uuid as _uuid
                db_user = s.query(User).filter_by(id=_uuid.UUID(client_ref)).with_for_update().first()
            except Exception:
                pass
        if not db_user and customer_id and not cust_email:
            try:
                cust = stripe.Customer.retrieve(customer_id)
                cust_email = getattr(cust, "email", None)
            except Exception:
                pass
        if not db_user and cust_email:
            db_user = s.query(User).filter_by(email=cust_email).with_for_update().first()

        if not db_user:
            # TW2 shares its Stripe account with TW1, so every TW1 customer's
            # billing event is ALSO delivered to this endpoint and will never
            # map to a TW2 user. The old behavior (return 5xx so Stripe retries
            # for ~3 days to cover a new-signup race) turned that into a
            # permanent retry storm and risked Stripe auto-disabling the
            # endpoint. Instead: record the row with processing_error set and
            # processed_at left NULL so it stays visible and replayable from
            # /admin, then ACK 200 so Stripe stops retrying. Genuine new-
            # subscriber races are covered by the idempotent /stripe/success
            # reconcile and by later recurring subscription events.
            err_detail = (
                f"No user found for stripe_customer_id={customer_id}, "
                f"client_ref={client_ref}, email={cust_email}"
            )
            evrow.processing_error = err_detail
            s.commit()
            try:
                write_audit(
                    actor_label=f"stripe_webhook:{event_type}",
                    action="stripe_webhook_user_not_found",
                    target_user_id=None,
                    details={
                        "stripe_event_id": event_id,
                        "stripe_customer_id": customer_id,
                        "client_reference_id": client_ref,
                        "email": cust_email,
                    },
                )
            except Exception:
                log.exception("write_audit for user_not_found failed")
            return jsonify({"received": True, "user_not_found": True}), 200

        # F2.9 - Backfill stripe_customer_id if it was missing - but refuse
        # to rebind a customer_id that already belongs to a different user row.
        # This prevents a malicious or duplicate-account event from silently
        # stealing another user's Stripe identity.
        if customer_id and not db_user.stripe_customer_id:
            existing_owner = s.query(User).filter_by(stripe_customer_id=customer_id).filter(User.id != db_user.id).first()
            if existing_owner:
                log.error(
                    "stripe customer_id=%s already on user %s; refusing to rebind to %s (event %s)",
                    customer_id, existing_owner.id, db_user.id, event_id,
                )
                try:
                    write_audit(
                        actor_label=f"stripe_webhook:{event_type}",
                        action="stripe_customer_rebind_conflict",
                        target_user_id=db_user.id,
                        details={
                            "stripe_customer_id": customer_id,
                            "existing_owner_user_id": str(existing_owner.id),
                            "stripe_event_id": event_id,
                        },
                    )
                except Exception:
                    log.exception("write_audit for rebind_conflict failed")
            else:
                db_user.stripe_customer_id = customer_id

        evrow.user_id = db_user.id

        # Resolve new tier (None = no change). TW2 runs TWO subscription product lines on the
        # SAME (TW1-shared) Stripe account: the web/EOD line (product_line=eod -> users.tier)
        # and the developer API line (product_line=api -> users.api_tier). Each subscription
        # event carries ONE price, so we route by that price's product_line and only ever
        # touch the matching column: cancelling the API sub must never downgrade the web tier,
        # and vice versa.
        new_tier = None            # web/EOD tier change (None = no change)
        new_api_tier = None        # API-line tier change ("__free__" = revert to inherited)
        api_event = False          # this event belongs to the developer-API product line
        unmappable_price = False
        # Mailerlite level-group sync target: "__skip__" means don't sync this event;
        # otherwise it's the billing period (monthly/yearly, or None for explorer) to
        # pair with the final tier. We sync on EVERY mappable subscription event - not
        # only on a tier change - so a same-tier monthly<->yearly switch still moves groups.
        # API-line events never touch the web level groups (left as "__skip__").
        ml_target_period = "__skip__"
        if event_type in ("customer.subscription.created", "customer.subscription.updated") and price_id:
            api_tier_for_price = _api_tier_for_price(price_id)
            if api_tier_for_price is not None:
                api_event = True
                if sub_status in ("active", "trialing", "past_due"):
                    new_api_tier = api_tier_for_price
            else:
                tier, period = _tier_period_for_price(price_id)
                if sub_status in ("active", "trialing", "past_due"):
                    if tier:
                        new_tier = tier
                        ml_target_period = period
                    else:
                        # Legacy / no-metadata price on a LIVE subscription. We can't map it
                        # to a tier, so we deliberately do NOT touch the tier (never wrongly
                        # downgrade a grandfathered payer) - but we must NOT silently no-op
                        # either: a plan change between two legacy prices would otherwise
                        # leave the user stuck at the old tier with no signal. Alert below.
                        unmappable_price = True
        if event_type == "customer.subscription.deleted":
            # Route the cancellation to the right line by the deleted sub's price.
            if price_id is not None and _api_tier_for_price(price_id) is not None:
                api_event = True
                new_api_tier = "__free__"   # cancelled API sub -> inherit from the web tier
            else:
                new_tier = "explorer"
                ml_target_period = None

        old_tier = db_user.tier
        # Only the web/EOD line owns the shared stripe_subscription_id / _status fields; an
        # API-line event must not clobber the web subscription's id (a user may hold both).
        if sub_id and not api_event:
            db_user.stripe_subscription_id = sub_id
        if sub_status and not api_event:
            db_user.stripe_subscription_status = sub_status
        tier_changed_to = None
        if new_tier and new_tier != db_user.tier:
            db_user.tier = new_tier
            db_user.legacy_wp_level = tier_to_legacy_level(new_tier)
            tier_changed_to = new_tier
        # API-line tier write (separate column; never clobbers the web tier).
        old_api_tier = db_user.api_tier
        api_tier_changed_to = None
        if new_api_tier == "__free__":
            if db_user.api_tier is not None:
                db_user.api_tier = None     # cancelled -> inherit from the web tier again
                api_tier_changed_to = "free"
        elif new_api_tier and new_api_tier != db_user.api_tier:
            db_user.api_tier = new_api_tier
            api_tier_changed_to = new_api_tier

        # Commit our row mutations BEFORE calling write_audit. write_audit uses
        # the same scoped_session and closes its inner session, which expunges
        # objects from the outer session - silently dropping later updates
        # (this is why processed_at was missing from subscription.* events).
        evrow.processed_at = datetime.now(timezone.utc)
        final_tier = db_user.tier
        final_api_tier = db_user.api_tier
        s.commit()

        if tier_changed_to:
            write_audit(
                actor_label=f"stripe_webhook:{event_type}",
                action="tier_changed",
                target_user_id=db_user.id,
                details={"from": old_tier, "to": tier_changed_to, "stripe_event_id": event_id, "stripe_sub_id": sub_id},
            )

        if api_tier_changed_to:
            write_audit(
                actor_label=f"stripe_webhook:{event_type}",
                action="api_tier_changed",
                target_user_id=db_user.id,
                details={"from": old_api_tier, "to": api_tier_changed_to,
                         "stripe_event_id": event_id, "stripe_sub_id": sub_id},
            )

        if unmappable_price:
            # A live subscription carries a price we can't map to a tier (legacy / no
            # product metadata). Tier was intentionally left unchanged; surface it loudly
            # so a stuck-high tier on a legacy plan-change can't slip by unnoticed. Fix =
            # add product_line=eod/tier/period metadata to the Stripe product, or a
            # legacy_price_map entry. Stripe still gets a 200 (no retry storm).
            log.error(
                "stripe_webhook: UNMAPPABLE active price - user=%s price=%s sub=%s status=%s "
                "tier-left-as=%s. Add Stripe product metadata (product_line=eod,tier,period) "
                "or a legacy_price_map entry; tier was NOT changed.",
                db_user.id, price_id, sub_id, sub_status, final_tier,
            )
            write_audit(
                actor_label=f"stripe_webhook:{event_type}",
                action="unmappable_price",
                target_user_id=db_user.id,
                details={"price_id": price_id, "stripe_sub_id": sub_id, "status": sub_status,
                         "tier_unchanged": final_tier, "stripe_event_id": event_id},
            )

        # Mailerlite level-group sync (TW1/UMP parity) - best-effort, post-commit.
        # Fires on every mappable subscription event (and on delete -> explorer), so a
        # same-tier monthly<->yearly switch still moves the user's group. Idempotent.
        if ml_target_period != "__skip__":
            sync_mailerlite_level_group(db_user.email, final_tier, ml_target_period, new_user=False)

        return jsonify({"received": True, "tier": final_tier, "api_tier": final_api_tier,
                        "status": sub_status}), 200

    except Exception:
        # F2.2 - log full traceback, generic response. Stripe will retry on 500.
        log.exception("Stripe webhook processing failed (event_id=%s type=%s)", event_id, event_type)
        s.rollback()
        return jsonify({"error": "processing_failed"}), 500
    finally:
        s.close()


# ============================================================
# Flask-Admin (Phase 6)
# ============================================================

class _AdminAuth:
    """Mixin: only super_admin role can see Flask-Admin views."""
    def is_accessible(self):
        u = get_current_user()
        return u is not None and "super_admin" in (u.roles or [])

    def inaccessible_callback(self, name, **kwargs):
        u = get_current_user()
        if u is None:
            return redirect(_get_authorization_url(state=request.url))
        return abort(403)


class TW2AdminIndex(_AdminAuth, AdminIndexView):
    @expose("/")
    def index(self):
        u = get_current_user()
        s = DBSession()
        try:
            user_count = s.query(User).count()
            recent_audit = s.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(10).all()
            recent_stripe = s.query(StripeEvent).order_by(StripeEvent.received_at.desc()).limit(10).all()
            tier_counts = {}
            for t in ("explorer", "analyst", "strategist"):
                tier_counts[t] = s.query(User).filter_by(tier=t).count()
        finally:
            s.close()
        return self.render(
            "admin/index.html",
            current_admin=u,
            user_count=user_count,
            tier_counts=tier_counts,
            recent_audit=recent_audit,
            recent_stripe=recent_stripe,
        )


def _roles_help_html():
    """Render the canonical ROLES dict as help text shown under the roles
    field in the user-edit form. Kept in a helper so it stays in sync with
    models.ROLES — edit ROLES, not this function."""
    from models import ROLES
    from markupsafe import Markup, escape
    rows = "".join(
        f"<li><code>{escape(name)}</code> — {escape(desc)}</li>"
        for name, desc in ROLES.items()
    )
    return Markup(
        f"Valid role strings (JSON array, e.g. <code>[\"user\", \"newsroom_author\"]</code>):"
        f"<ul style='margin:4px 0 0 18px;padding:0;'>{rows}</ul>"
    )


class UserAdmin(_AdminAuth, ModelView):
    column_list = ("email", "tier", "roles", "stripe_subscription_status", "email_verified", "last_login_at", "created_at")
    column_searchable_list = ("email", "workos_user_id", "stripe_customer_id")
    column_filters = ("tier", "email_verified", "stripe_subscription_status")
    form_columns = ("email", "first_name", "last_name", "tier", "roles", "email_verified", "stripe_customer_id", "stripe_subscription_id", "stripe_subscription_status", "trial_ends_at")
    column_default_sort = ("created_at", True)
    page_size = 50

    # NOTE: use form_args, NOT form_widget_args. form_widget_args kwargs are
    # emitted as raw HTML attributes on the input (description="<ul>...">),
    # which breaks out of the attribute and renders garbage. form_args sets the
    # field's real `description`, which the form template renders as help text.
    form_args = {
        "roles": {"description": _roles_help_html()},
    }

    def on_model_change(self, form, model, is_created):
        from tier_compat import tier_to_legacy_level
        from models import ROLES
        from wtforms.validators import ValidationError
        if model.tier:
            model.legacy_wp_level = tier_to_legacy_level(model.tier)

        # Validate roles against the canonical list. Reject unknown strings so
        # a typo ("newsroomauthor") fails loudly instead of silently granting
        # nothing. Accepts a JSON array; converts None/empty to default ["user"].
        roles = model.roles
        if roles is None or roles == []:
            model.roles = ["user"]
            roles = model.roles
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise ValidationError("roles must be a JSON array of strings, e.g. [\"user\"]")
        unknown = [r for r in roles if r not in ROLES]
        if unknown:
            valid = ", ".join(sorted(ROLES.keys()))
            raise ValidationError(
                f"Unknown role(s): {unknown}. Valid roles are: {valid}."
            )

    def after_model_change(self, form, model, is_created):
        # Mailerlite level-group sync (TW1/UMP parity) for manual admin tier edits.
        # Period isn't known for a manual grant: explorer syncs to the explorer group;
        # a manual analyst/strategist has no monthly/yearly, so the helper skips + logs
        # it for manual placement (the reconcile picks up anyone with a real Stripe sub).
        try:
            if getattr(model, "email", None) and getattr(model, "tier", None):
                sync_mailerlite_level_group(model.email, model.tier, None, new_user=False)
        except Exception as e:
            log.warning("admin after_model_change mailerlite sync failed for %s: %s",
                        getattr(model, "email", "?"), e)

    @action(
        "purge",
        "Hard delete (purge from WorkOS + Postgres)",
        "PERMANENTLY delete selected user(s) from BOTH WorkOS and Postgres. Frees the email for re-signup. NO UNDO. Continue?",
    )
    def action_purge(self, ids):
        s = DBSession()
        try:
            users = s.query(User).filter(User.id.in_(ids)).all()
            purged = 0
            errors = []
            for u in users:
                # Cancel any active Stripe subscription first
                if u.stripe_subscription_id:
                    try:
                        stripe.Subscription.delete(u.stripe_subscription_id)
                    except Exception as e:
                        errors.append(f"{u.email}: stripe cancel failed: {e}")
                # Delete from WorkOS
                if u.workos_user_id:
                    try:
                        workos_client.user_management.delete_user(user_id=u.workos_user_id)
                    except Exception as e:
                        errors.append(f"{u.email}: WorkOS delete failed: {e}")
                # Audit before deleting from Postgres
                write_audit(
                    actor_label="admin_purge",
                    action="user_purged",
                    target_user_id=u.id,
                    details={"email": u.email, "workos_user_id": u.workos_user_id, "tier": u.tier},
                )
                s.delete(u)
                purged += 1
            s.commit()
            if errors:
                flash(f"Purged {purged} but with errors: " + "; ".join(errors), "warning")
            else:
                flash(f"Purged {purged} user(s) from WorkOS + Postgres.", "success")
        except Exception as e:
            s.rollback()
            flash(f"Purge failed: {e}", "error")
        finally:
            s.close()


class AuditLogAdmin(_AdminAuth, ModelView):
    can_create = False
    can_edit = False
    can_delete = False
    column_list = ("created_at", "actor_label", "action", "target_user_id", "details")
    column_default_sort = ("created_at", True)
    page_size = 100


class StripeEventAdmin(_AdminAuth, ModelView):
    can_create = False
    can_edit = False
    can_delete = False
    column_list = ("received_at", "event_type", "stripe_event_id", "user_id", "processed_at", "processing_error")
    column_default_sort = ("received_at", True)
    page_size = 100


class SupportTicketAdmin(_AdminAuth, ModelView):
    # Tier-1 view: read + status edits only. Body/email/etc are immutable from
    # the admin - the customer wrote them and the source of truth is the email
    # thread. If/when we promote DB to source-of-truth (Tier 2), this view
    # gains a reply form.
    can_create = False
    can_delete = False
    can_edit = True
    column_list = ("created_at", "public_id", "topic", "status", "name", "email")
    column_default_sort = ("created_at", True)
    column_searchable_list = ("public_id", "email", "name")
    column_filters = ("status", "topic", "created_at")
    # Edit form: status is the only field worth flipping (open -> resolved /
    # spam). Everything else is read-only context.
    form_columns = ("status", "resolved_at")
    column_details_list = (
        "public_id", "created_at", "topic", "status", "name", "email",
        "body", "enrichment", "user_id", "ip_hash", "user_agent",
        "resolved_at", "updated_at",
    )
    can_view_details = True
    page_size = 100


# ============================================================
# Affiliate program admin (Affiliates tab)
# In-house, manual promo-code model: one Stripe coupon + one promotion code per
# affiliate; commission is computed downstream from Stripe (no webhook/billing
# changes). See web/affiliate_service.py + migration af1c0de2b3a4.
# ============================================================

class AffiliateAdmin(_AdminAuth, ModelView):
    column_list = ("code", "name", "discount_pct", "commission_pct",
                   "commission_model", "status", "stripe_coupon_id", "created_at")
    column_searchable_list = ("code", "name", "email", "payout_email")
    column_filters = ("status", "commission_model")
    form_columns = ("name", "email", "code", "discount_pct", "commission_pct",
                    "commission_model", "payout_method", "payout_email",
                    "status", "notes")
    column_default_sort = ("created_at", True)
    page_size = 50
    form_choices = {
        "commission_model": [
            ("recurring", "Recurring (lifetime)"),
            ("duration_12mo", "First 12 months"),
            ("first_payment", "First payment only"),
        ],
        "payout_method": [("paypal", "PayPal"), ("wise", "Wise")],
        "status": [("active", "Active"), ("paused", "Paused"),
                   ("terminated", "Terminated")],
    }
    form_args = {
        "code": {"description": "The promo code the affiliate shares (A-Z, 0-9, _ or -). "
                                "Becomes the Stripe promotion code. IMMUTABLE after creation."},
        "discount_pct": {"description": "Audience discount, e.g. 20 = 20% off the first 12 months. "
                                        "IMMUTABLE after creation (Stripe coupons can't be edited)."},
        "commission_pct": {"description": "What the affiliate keeps, e.g. 30 = 30%. Editable later."},
    }

    def create_form(self, obj=None):
        form = super().create_form(obj)
        if form.discount_pct.data is None:
            form.discount_pct.data = config.AFFILIATE_DEFAULT_DISCOUNT_PCT
        if form.commission_pct.data is None:
            form.commission_pct.data = config.AFFILIATE_DEFAULT_COMMISSION_PCT
        if not form.commission_model.data:
            form.commission_model.data = "recurring"
        return form

    def on_model_change(self, form, model, is_created):
        from wtforms.validators import ValidationError
        from sqlalchemy import inspect as sa_inspect
        import affiliate_service as afs

        # normalize + validate the code
        model.code = afs.normalize_code(model.code)
        try:
            afs.validate_code(model.code)
        except afs.AffiliateError as e:
            raise ValidationError(str(e))

        if not model.commission_model:
            model.commission_model = "recurring"
        if not model.status:
            model.status = "active"

        if is_created:
            from sqlalchemy.exc import IntegrityError
            # Claim the code via the real UNIQUE constraint by flushing the row
            # (coupon id still NULL) BEFORE creating any Stripe objects: a
            # duplicate/raced code fails here and aborts, so we never leave an
            # orphan Stripe coupon for a row we can't save.
            #
            # Do NOT pre-SELECT for the duplicate: Flask-Admin has already added
            # `model` to the session, so any query autoflushes it and the SELECT
            # "finds itself" -> every create would falsely report "already
            # exists". The flush + IntegrityError below is the correct guard.
            try:
                self.session.flush()
            except IntegrityError:
                self.session.rollback()
                raise ValidationError(f"An affiliate with code {model.code} already exists.")
            # create the Stripe coupon + promo code; abort the insert on failure
            try:
                coupon_id, promo_id = afs.provision_stripe_objects(model)
            except afs.AffiliateError as e:
                raise ValidationError(str(e))
            model.stripe_coupon_id = coupon_id
            model.stripe_promotion_code_id = promo_id
            write_audit(actor_label="admin", action="affiliate_created",
                        details={"code": model.code, "coupon": coupon_id,
                                 "discount_pct": str(model.discount_pct),
                                 "commission_pct": str(model.commission_pct)})
        else:
            # code + discount_pct are immutable once the Stripe coupon exists
            st = sa_inspect(model)
            for field in ("code", "discount_pct"):
                hist = getattr(st.attrs, field).history
                if hist.has_changes() and hist.deleted:
                    raise ValidationError(
                        f"{field} can't be changed after the Stripe coupon is created. "
                        f"Terminate this affiliate and create a new one instead.")


class AffiliatePayoutAdmin(_AdminAuth, ModelView):
    # Rows are created by the compute step, not by hand. You edit only the
    # amount (e.g. to net a refund), the status, the paid date, and the txn id.
    can_create = False
    can_delete = False
    can_edit = True
    column_list = ("affiliate", "period_start", "period_end", "currency",
                   "gross_revenue", "commission_amount", "status", "paid_at",
                   "external_ref")
    column_default_sort = ("period_start", True)
    column_filters = ("status", "currency", "period_start")
    form_columns = ("commission_amount", "status", "paid_at", "external_ref")
    form_choices = {"status": [("pending", "Pending"), ("paid", "Paid"),
                               ("void", "Void")]}
    can_view_details = True
    column_details_list = ("affiliate", "period_start", "period_end", "currency",
                           "gross_revenue", "commission_amount", "status",
                           "computed_at", "paid_at", "external_ref", "detail")
    page_size = 100

    def on_model_change(self, form, model, is_created):
        # auto-stamp paid_at when flipped to paid without an explicit date
        if model.status == "paid" and not model.paid_at:
            from datetime import datetime, timezone
            model.paid_at = datetime.now(timezone.utc)


_AFFILIATE_COMPUTE_TMPL = """
<!doctype html><html><head><meta charset="utf-8"><title>Affiliate payouts</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;max-width:920px;margin:32px auto;padding:0 16px;color:#111}
 h1{font-size:22px} table{border-collapse:collapse;width:100%;margin-top:16px}
 th,td{border:1px solid #ddd;padding:8px 10px;text-align:left;font-size:14px}
 th{background:#f5f5f7} td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
 .bar{margin:16px 0;padding:12px;border-radius:8px}
 .ok{background:#e7f6ec;color:#0a7d28} .err{background:#fdeaea;color:#b00020}
 input[type=number]{width:80px;padding:4px}
 .btn{background:#6366f1;color:#fff;border:0;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600}
 .muted{color:#666;font-size:13px} a{color:#5b4bdb}
</style></head><body>
<p><a href="/admin">&larr; Admin</a> &middot; <a href="/admin/affiliatepayout/">Payout ledger</a></p>
<h1>Affiliate commission - what I owe</h1>
{% if committed %}<div class="bar ok">Committed {{ '%04d-%02d'|format(y, m) }} to the payout ledger (idempotent - existing rows untouched).</div>{% endif %}
{% if error %}<div class="bar err">Error: {{ error }}</div>{% endif %}
<form method="get">
  <label>Year <input type="number" name="year" value="{{ y }}"></label>
  <label>Month <input type="number" name="month" value="{{ m }}" min="1" max="12"></label>
  <button class="btn" type="submit">Preview</button>
</form>
<p class="muted">Reads Stripe live for the month and attributes each discounted sale to its affiliate by the coupon used. Commission = (amount paid &minus; tax) &times; the affiliate's rate. Refunds are not auto-deducted - adjust the amount in the ledger before marking it paid.</p>
{% if preview %}
<table>
 <tr><th>Code</th><th>Affiliate</th><th>Cur</th><th class="num">Revenue</th><th class="num">Commission owed</th><th>Pay to</th></tr>
 {% for r in preview %}
 <tr><td><b>{{ r.code }}</b></td><td>{{ r.name }}</td><td>{{ r.currency|upper }}</td>
     <td class="num">{{ '%.2f'|format(r.gross_revenue) }}</td>
     <td class="num"><b>{{ '%.2f'|format(r.commission_amount) }}</b></td>
     <td>{{ r.payout_email or '' }}</td></tr>
 {% endfor %}
 {% for ccy, amt in totals %}
 <tr><th colspan="4" class="num">Total ({{ ccy|upper }})</th><th class="num">{{ '%.2f'|format(amt) }}</th><th></th></tr>
 {% endfor %}
</table>
<form method="post" style="margin-top:16px">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input type="hidden" name="year" value="{{ y }}"><input type="hidden" name="month" value="{{ m }}">
  <input type="hidden" name="action" value="commit">
  <button class="btn" type="submit">Commit {{ '%04d-%02d'|format(y, m) }} to ledger &rarr;</button>
</form>
{% else %}
<p class="muted">No affiliate sales found for {{ '%04d-%02d'|format(y, m) }}.</p>
{% endif %}
</body></html>
"""


class AffiliatePayoutComputeView(_AdminAuth, BaseView):
    """Month picker: previews 'what I owe' live from Stripe, with a button to
    commit the numbers into the payout ledger (idempotent)."""

    @expose("/", methods=["GET", "POST"])
    def index(self):
        from flask import render_template_string, request as _rq
        from datetime import date
        from decimal import Decimal as _D
        import affiliate_service as afs
        from models import Session as _S

        today = date.today()
        dflt_y, dflt_m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        try:
            y = int(_rq.values.get("year", dflt_y))
            m = int(_rq.values.get("month", dflt_m))
            date(y, m, 1)
        except (ValueError, TypeError):
            y, m = dflt_y, dflt_m

        committed = False
        error = None
        preview = []
        s = _S()
        try:
            if _rq.method == "POST" and _rq.form.get("action") == "commit":
                afs.upsert_month(s, y, m)
                committed = True
            preview = afs.compute_month(s, y, m)
        except Exception as e:
            error = str(e)
            log.exception("affiliate compute failed for %04d-%02d", y, m)
        finally:
            s.close()

        # Never sum across currencies - one total per currency.
        totals = {}
        for r in preview:
            totals[r["currency"]] = totals.get(r["currency"], _D("0")) + r["commission_amount"]
        return render_template_string(
            _AFFILIATE_COMPUTE_TMPL, y=y, m=m, preview=preview,
            committed=committed, error=error, totals=sorted(totals.items()))


_AFFILIATE_GUIDE_TMPL = """
<!doctype html><html><head><meta charset="utf-8"><title>Affiliates - how it works</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#111;line-height:1.6}
 h1{font-size:24px;margin-bottom:4px} h2{font-size:17px;margin:26px 0 6px;color:#3a32a8}
 a{color:#5b4bdb} code{background:#f0f0f4;padding:1px 6px;border-radius:4px;font-size:13px}
 .step{background:#f7f7fb;border:1px solid #e6e6ef;border-radius:10px;padding:14px 18px;margin:10px 0}
 .step b{color:#000} ol{padding-left:20px} li{margin:5px 0}
 .pill{display:inline-block;font-size:12px;font-weight:700;padding:2px 8px;border-radius:20px;margin-right:6px}
 .mode-test{background:#e7f6ec;color:#0a7d28} .mode-live{background:#fdeaea;color:#b00020}
 .note{font-size:13px;color:#555;background:#fffbe6;border:1px solid #f0e6b0;border-radius:8px;padding:10px 14px;margin:14px 0}
 nav a{margin-right:14px}
</style></head><body>
<nav><a href="/admin">&larr; Admin</a><a href="/admin/affiliate/">Affiliates</a><a href="/admin/affiliatepayout/">Payout ledger</a><a href="/admin/affiliate_compute/">Compute / what I owe</a></nav>
<h1>Affiliate program - how it works</h1>
<p>An in-house affiliate program built on Stripe's own coupons. <b>Each affiliate gets one Stripe coupon + one promo code, created automatically</b> when you add them here - no Stripe dashboard, no Rewardful.</p>
<p>Current mode: {% if livemode %}<span class="pill mode-live">LIVE - real money</span>{% else %}<span class="pill mode-test">TEST / sandbox - safe to experiment</span>{% endif %}</p>

<h2>1. Add an affiliate</h2>
<div class="step"><b>Affiliates &rarr; Create.</b> Fill in name, payout email, the audience <b>discount %</b> (default 20), the affiliate's <b>commission %</b> (default 30, what they keep), and the <b>commission model</b>. On Save, we create their Stripe coupon (X% off, repeating 12 months = "first year") and a promotion code equal to the <code>code</code> you chose. That code is what they share.</div>

<h2>2. What the affiliate shares (both ways credit them)</h2>
<div class="step">
  <b>Their code</b> - the audience types <code>THEIRCODE</code> at checkout to get the discount, and
  <b>A direct link</b> - <code>https://{{ public_host }}/?code=THEIRCODE</code>. Clicking it pre-applies the discount at checkout (no typing needed), so it works even when the code is just spoken on a podcast. (<code>?via=THEIRCODE</code> also works.)
</div>

<h2>3. What you can and can't change later</h2>
<div class="step">
  <b>Immutable</b> after creation: the <code>code</code> and the <b>discount %</b> (Stripe coupons can't be edited). To change either, set the affiliate to <b>terminated</b> and create a new one.<br>
  <b>Editable</b> anytime: commission %, payout method/email, notes, and status.
</div>

<h2>4. Statuses</h2>
<ol>
  <li><b>active</b> - earns commission; their link pre-applies the discount.</li>
  <li><b>paused</b> - you still get paid on their existing referrals, but their link stops auto-applying for new visitors. Use to wind someone down gently.</li>
  <li><b>terminated</b> - excluded from future payouts and their link no longer applies. Use instead of deleting (history is preserved).</li>
</ol>

<h2>5. Paying affiliates each month</h2>
<ol>
  <li><b>Affiliates &rarr; Compute / what I owe.</b> Pick the month and hit <b>Preview</b> - it reads Stripe live and shows revenue + commission owed per affiliate.</li>
  <li>Hit <b>Commit to ledger</b> to save those numbers.</li>
  <li><b>Affiliates &rarr; Payout Ledger.</b> For each row: pay the person by PayPal/Wise, then set <b>status = Paid</b> and paste the transaction id into <b>external_ref</b>.</li>
</ol>
<div class="note"><b>Good to know:</b> commission is computed on revenue <i>after</i> the discount and <i>after</i> tax. Re-running a month <b>refreshes still-pending rows</b> with the latest numbers (good for late-settling payments); rows you've marked <b>Paid</b> or <b>Void</b> are frozen. <b>Refunds are not auto-deducted</b> - if a referral refunds, edit that pending row's commission amount down before you mark it paid.</div>

<h2>6. Test vs live</h2>
<div class="step">On the dev box this is Stripe <b>test mode</b> - create affiliates, generate codes, and run payouts freely; nothing is real. On production the same actions create <b>real</b> coupons and apply <b>real</b> discounts.</div>
</body></html>
"""


class AffiliateGuideView(_AdminAuth, BaseView):
    """Static 'how to use the affiliate program' page for the admin."""

    @expose("/")
    def index(self):
        from flask import render_template_string
        import os as _os
        public_host = _os.environ.get("TW2_PUBLIC_HOST", request.host)
        livemode = "live" in (config.STRIPE_SECRET_KEY or "").split("_")[1:2]
        return render_template_string(
            _AFFILIATE_GUIDE_TMPL, public_host=public_host, livemode=livemode)


# ============================================================
# Standalone promo coupons (Coupons tab) - plain discount codes, NO affiliate /
# commission / payout. Each row = one Stripe coupon + one promotion code,
# created on save. See web/promo_service.py + migration b2c0fee1d3a5.
# ============================================================

class PromoCouponAdmin(_AdminAuth, ModelView):
    column_list = ("code", "discount_type", "percent_off", "amount_off_cents",
                   "currency", "duration", "status", "expires_at",
                   "max_redemptions", "created_at")
    column_searchable_list = ("code", "name", "notes")
    column_filters = ("status", "discount_type", "duration")
    form_columns = ("code", "name", "discount_type", "percent_off",
                    "amount_off_cents", "currency", "duration",
                    "duration_in_months", "max_redemptions", "expires_at",
                    "status", "notes")
    column_default_sort = ("created_at", True)
    page_size = 50
    form_choices = {
        "discount_type": [("percent", "Percent off (e.g. 20 = 20%)"),
                          ("amount", "Fixed amount off (needs currency)")],
        "duration": [("once", "Once (first invoice only)"),
                     ("repeating", "Repeating (N months)"),
                     ("forever", "Forever (every invoice)")],
        "status": [("active", "Active"), ("archived", "Archived (code disabled)")],
    }
    form_args = {
        "code": {"description": "The code customers type / you share (A-Z, 0-9, _ or -). IMMUTABLE after creation."},
        "percent_off": {"description": "PERCENT coupons: 1-100. Use 100 for a free/comp code. Leave blank for amount coupons."},
        "amount_off_cents": {"description": "AMOUNT coupons: discount in CENTS (1000 = $10). Leave blank for percent coupons."},
        "currency": {"description": "Required for amount coupons, e.g. usd."},
        "duration_in_months": {"description": "Required when duration = repeating."},
        "max_redemptions": {"description": "Optional: total times the code can be redeemed (e.g. 50)."},
        "expires_at": {"description": "Optional: when the code stops working. Must be in the future."},
    }

    def on_model_change(self, form, model, is_created):
        from wtforms.validators import ValidationError
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.exc import IntegrityError
        import datetime as _dt
        import promo_service as ps

        model.code = ps.normalize_code(model.code)
        if not model.status:
            model.status = "active"
        if model.currency:
            model.currency = model.currency.strip().lower()
        # The admin form yields a NAIVE datetime; store it UTC-aware so the
        # Stripe expiry timestamp is correct and edit-time comparisons are sane.
        if model.expires_at is not None and model.expires_at.tzinfo is None:
            model.expires_at = model.expires_at.replace(tzinfo=_dt.timezone.utc)

        if is_created:
            try:
                ps.validate_promo(model)
            except ps.PromoError as e:
                raise ValidationError(str(e))
            # claim the code via the unique constraint BEFORE creating Stripe
            # objects (do NOT pre-SELECT: the row is already in the session and
            # a query would autoflush + find itself).
            try:
                self.session.flush()
            except IntegrityError as e:
                self.session.rollback()
                orig = str(getattr(e, "orig", e))
                if "promo_coupons_code" in orig:   # the unique-code constraint
                    raise ValidationError(f"A coupon with code {model.code} already exists.")
                raise ValidationError(f"Could not save coupon: {orig}")
            try:
                coupon_id, promo_id = ps.provision_promo_coupon(model)
            except ps.PromoError as e:
                raise ValidationError(str(e))
            model.stripe_coupon_id = coupon_id
            model.stripe_promotion_code_id = promo_id
            model._tw_sync_stripe_active = False
            write_audit(actor_label="admin", action="promo_coupon_created",
                        details={"code": model.code, "coupon": coupon_id,
                                 "discount_type": model.discount_type})
        else:
            # Only name / notes / status are editable. Compare INSTANTS (not raw
            # values) so a tz-aware<->naive datetime at the same moment isn't
            # seen as a change; restore the persisted value when unchanged so
            # populate_obj can't drift it on the UPDATE.
            st = sa_inspect(model)

            def _norm(v):
                if isinstance(v, _dt.datetime) and v.tzinfo is None:
                    return v.replace(tzinfo=_dt.timezone.utc)
                return v

            for field in ("code", "discount_type", "percent_off", "amount_off_cents",
                          "currency", "duration", "duration_in_months",
                          "max_redemptions", "expires_at"):
                h = getattr(st.attrs, field).history
                if not h.has_changes():
                    continue
                old = h.deleted[0] if h.deleted else None
                new = h.added[0] if h.added else None
                if _norm(old) != _norm(new):
                    raise ValidationError(
                        f"{field} can't be changed after creation (Stripe coupons are fixed). "
                        f"Archive this coupon and create a new one instead.")
                if h.deleted:   # same instant/value: keep persisted, don't drift
                    setattr(model, field, old)
            # The Stripe active<->archived flip happens in after_model_change
            # (post-commit), so a commit failure can't disable the Stripe code
            # while the DB still shows it active.
            model._tw_sync_stripe_active = st.attrs.status.history.has_changes()

    def after_model_change(self, form, model, is_created):
        # Reflect a committed status change onto the Stripe promotion code AFTER
        # the DB commit (DB is the source of truth). Best-effort: log on failure.
        if is_created or not getattr(model, "_tw_sync_stripe_active", False):
            return
        import promo_service as ps
        try:
            ps.set_promo_active(model, model.status == "active")
        except Exception as e:
            log.warning("promo coupon %s: Stripe active-flag sync failed (%s); "
                        "DB says %s", getattr(model, "code", "?"), e, model.status)


# ============================================================
# Internal cross-tier endpoint: render a date-range report.
# Called by appserver's /dr_report_publish so the static HTML
# is written on the web tier (where /var/www/tradewave/ lives)
# regardless of whether dev (single box) or split web/app.
# ============================================================
import threading as _threading  # noqa: E402

# Bound concurrent /internal/render_report threads so a burst can't OOM
# the 1-CPU/961M staging box. matplotlib in report_renderer.render()
# spikes to ~200M per thread.
_RENDER_SEM = _threading.Semaphore(4)


def _check_service_key():
    """Constant-time compare so a timing oracle can't leak the key."""
    import hmac
    provided = request.headers.get("X-Service-Key", "")
    expected = config.SERVICE_API_KEY or ""
    return bool(expected) and hmac.compare_digest(provided, expected)


def _slug_safe(slug: str) -> bool:
    """ASCII-only [a-zA-Z0-9_-]+ allowlist.

    str.isalnum() is Unicode-aware (٠ café Ⅰ all pass), so we explicitly
    constrain to ASCII alphanumerics + '-' and '_'. Refuses NUL, '/',
    '..', control chars, and anything not in the allowlist.
    """
    import re
    return bool(slug) and bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", slug))


@app.route("/internal/render_report", methods=["POST"])
@csrf.exempt
def internal_render_report():
    if not _check_service_key():
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(force=True, silent=True) or {}
    try:
        report_dict = payload["report_dict"]
        appserver_token = payload["token"]
        post_title = payload["title"]
        post_slug = payload["slug"]
    except KeyError as e:
        return jsonify({"error": f"missing field {e}"}), 400
    if not _slug_safe(post_slug):
        return jsonify({"error": "invalid slug"}), 400

    import threading, sys
    # Bounded concurrency so a flood of /dr_report_publish calls can't fork
    # unbounded matplotlib threads on the 1-CPU staging box (RAM is 961M).
    # Returns 503 if all slots are busy — caller sees fast-fail.
    if not _RENDER_SEM.acquire(blocking=False):
        return jsonify({"status": "busy"}), 503
    def _render():
        try:
            if "/home/flask/web" not in sys.path:
                sys.path.insert(0, "/home/flask/web")
            import report_renderer
            report_renderer.render(report_dict, appserver_token, post_title, post_slug)
        except Exception as exc:
            log.exception("internal_render_report: render failed slug=%s err=%s", post_slug, exc)
        finally:
            _RENDER_SEM.release()

    threading.Thread(target=_render, daemon=True).start()
    return jsonify({"status": "queued", "slug": post_slug})


@app.route("/internal/delete_report", methods=["POST"])
@csrf.exempt
def internal_delete_report():
    if not _check_service_key():
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(force=True, silent=True) or {}
    slug = payload.get("slug", "")
    if not _slug_safe(slug):
        return jsonify({"error": "invalid slug"}), 400
    import shutil
    from pathlib import Path
    target = Path("/var/www/tradewave/r") / slug
    if target.is_dir() and target.resolve().is_relative_to("/var/www/tradewave/r"):
        shutil.rmtree(target, ignore_errors=True)
        return jsonify({"status": "deleted", "slug": slug})
    return jsonify({"status": "absent", "slug": slug})


# Register Flask-Admin on the existing app
admin = Admin(
    app,
    name="TradeWave Admin",
    index_view=TW2AdminIndex(name="Dashboard", url="/admin"),
)

# Need a DB session bound to Flask-Admin's expectations
from models import Session as ModelsSession
admin.add_view(UserAdmin(User, ModelsSession, name="Users", category=None))
admin.add_view(AuditLogAdmin(AuditLog, ModelsSession, name="Audit Log", category="System"))
admin.add_view(StripeEventAdmin(StripeEvent, ModelsSession, name="Stripe Events", category="System"))
admin.add_view(SupportTicketAdmin(SupportTicket, ModelsSession, name="Support Tickets", category=None))

# --- Affiliate program (manual promo-code model) ---
from models import Affiliate, AffiliatePayout
admin.add_view(AffiliateGuideView(name="How it works", endpoint="affiliate_guide", category="Affiliates"))
admin.add_view(AffiliateAdmin(Affiliate, ModelsSession, name="Affiliates", category="Affiliates"))
admin.add_view(AffiliatePayoutAdmin(AffiliatePayout, ModelsSession, name="Payout Ledger", category="Affiliates"))
admin.add_view(AffiliatePayoutComputeView(name="Compute / What I owe", endpoint="affiliate_compute", category="Affiliates"))

# --- Standalone promo coupons (no affiliate / commission) ---
from models import PromoCoupon
admin.add_view(PromoCouponAdmin(PromoCoupon, ModelsSession, name="Coupons", category=None))

# --- API customer console: self-serve keys / usage / billing / MCP connect (additive) ---
import api_portal  # web/api_portal/ blueprint
from api_portal.blueprint import set_user_loader as _console_set_user_loader
_console_set_user_loader(get_current_user)  # reuse the web app's WorkOS session resolver
app.register_blueprint(api_portal.bp, url_prefix="/account/api")


# ============================================================
# Boot
# ============================================================
if __name__ == "__main__":
    # Convenience: bare-Flask dev runner
    app.run(host="127.0.0.1", port=5500, debug=False)
