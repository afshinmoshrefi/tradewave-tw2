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
from markupsafe import Markup
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
import reverse_trial  # shared reverse-trial cutoff math (also imported by apiserver/auth.py)

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
    User, AuditLog, StripeEvent, CouponUsed, SupportTicket, OnboardingEvent,
    SUPPORT_TICKET_TOPICS, db_session, write_audit, Session as DBSession,
)
from tier_compat import tier_to_wp_user_levels, tier_to_legacy_level
from mailerlite_lifecycle import (
    EVENT_CLEAR_PAID,
    EVENT_RECONCILE,
    enqueue_mailerlite_reconcile,
    enqueue_signup_lifecycle,
)
from ga4_mp import parse_ga_client_id, send_event

# --- WorkOS ---
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response, unseal_data
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
from flask_admin.model.template import (BaseListRowAction, DeleteRowAction,
                                         EndpointLinkRowAction)
from flask_admin.form import FileUploadField

# Co-branded affiliate landing-page logo uploads (admin-only). Served as a static
# file from /assets/affiliate-logos/ under the marketing web root.
AFFILIATE_LOGO_DIR = os.path.join(config.web_root_dir.rstrip("/"), "assets", "affiliate-logos")
AFFILIATE_LOGO_URLPATH = "/assets/affiliate-logos"
try:  # ensure the upload target exists wherever the web tier runs (best-effort)
    os.makedirs(AFFILIATE_LOGO_DIR, exist_ok=True)
except OSError:
    pass


def _affiliate_logo_namegen(obj, file_data):
    """Unique, collision-free filename for an uploaded logo (avoids depending on
    the not-yet-normalized code during form population)."""
    import uuid
    ext = os.path.splitext(file_data.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    return "%s%s" % (uuid.uuid4().hex, ext)
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
from wtforms import validators as wtf_validators  # noqa: E402
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

# --- Single-flight refresh memo (WorkOS refresh tokens are SINGLE-USE) -------
# A page load fires several parallel requests carrying the SAME stale cookie.
# Without coordination each one consumes the rotation chain independently and
# the browser keeps whichever Set-Cookie lands last - frequently one whose
# refresh token a sibling already burned -> the next request fails again ->
# visible login bouncing. The memo collapses all holders of one stale cookie
# onto ONE WorkOS rotation: first request refreshes and publishes the new
# sealed cookie under sha256(old cookie) for 90s; the rest reuse it. Redis on
# localhost (web box), db 5, fail-OPEN everywhere: any redis problem simply
# reverts to the uncoordinated behavior.
_SESS_MEMO_DB = 5
_SESS_MEMO_TTL = 90
_sess_memo_redis = None


def _sess_memo():
    global _sess_memo_redis
    if _sess_memo_redis is None:
        import redis as _redis
        _sess_memo_redis = _redis.Redis(
            host="127.0.0.1", port=6379, db=_SESS_MEMO_DB,
            socket_timeout=0.25, socket_connect_timeout=0.25,
            decode_responses=True)
    return _sess_memo_redis


def _sess_memo_key(sealed: str) -> str:
    import hashlib
    return "tw2:sess_refresh:" + hashlib.sha256(sealed.encode()).hexdigest()


def _sess_memo_get(sealed: str):
    try:
        return _sess_memo().get(_sess_memo_key(sealed))
    except Exception:
        return None


def _sess_memo_put(sealed: str, new_sealed: str) -> None:
    try:
        _sess_memo().set(_sess_memo_key(sealed), new_sealed, ex=_SESS_MEMO_TTL)
    except Exception:
        pass


def _sess_memo_lock(sealed: str) -> bool:
    """True if WE should perform the refresh (lock acquired or redis down)."""
    try:
        return bool(_sess_memo().set(_sess_memo_key(sealed) + ":lock", "1",
                                     nx=True, ex=10))
    except Exception:
        return True


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
        # The WorkOS SDK 6.2.0 `sess.refresh()` is broken for our setup: it asks the
        # API to seal the new session (session.seal_session=True) and then reads
        # auth_response["sealed_session"], which is absent in the response -> it
        # always fails with reason="'sealed_session'" (a swallowed KeyError). So we
        # refresh the way LOGIN works (which seals LOCALLY): exchange the refresh
        # token for fresh tokens, then seal with seal_session_from_auth_response
        # (mirrors auth_callback). Any failure falls back to None,None (re-login) -
        # i.e. never worse than the old behavior; the win is sessions now persist.
        # Single-flight: a sibling request may already have rotated this exact
        # stale cookie - reuse its published successor instead of burning the
        # (single-use) refresh token chain again.
        def _try_memoized():
            memo = _sess_memo_get(sealed)
            if not memo:
                return None
            try:
                m_sess = workos_client.user_management.load_sealed_session(
                    session_data=memo, cookie_password=config.WORKOS_COOKIE_PASSWORD)
                m_result = m_sess.authenticate()
                if getattr(m_result, "authenticated", False):
                    g._pending_session_cookie = memo
                    log.info("Session refresh reused memoized cookie (single-flight)")
                    return m_result, memo
            except Exception:
                pass
            return None

        hit = _try_memoized()
        if hit:
            return hit
        if not _sess_memo_lock(sealed):
            # Another request holds the refresh lock - give it a moment, then
            # reuse its result; fall through to our own refresh as last resort.
            import time as _t
            for _ in range(3):
                _t.sleep(0.15)
                hit = _try_memoized()
                if hit:
                    return hit

        try:
            sdata = unseal_data(sealed, config.WORKOS_COOKIE_PASSWORD)
            refresh_token = sdata.get("refresh_token")
            if refresh_token:
                rt = workos_client.user_management.authenticate_with_refresh_token(
                    refresh_token=refresh_token)
                user_dict = rt.user.to_dict() if hasattr(rt.user, "to_dict") else dict(rt.user)
                imp_dict = None
                if getattr(rt, "impersonator", None) is not None:
                    imp_dict = (rt.impersonator.to_dict() if hasattr(rt.impersonator, "to_dict")
                                else dict(rt.impersonator))
                new_sealed = seal_session_from_auth_response(
                    access_token=rt.access_token,
                    refresh_token=rt.refresh_token,
                    user=user_dict,
                    impersonator=imp_dict,
                    cookie_password=config.WORKOS_COOKIE_PASSWORD,
                )
                # Re-load + authenticate the freshly sealed session so callers get
                # the same result type as the normal path, and we only persist a
                # cookie that actually authenticates.
                new_sess = workos_client.user_management.load_sealed_session(
                    session_data=new_sealed, cookie_password=config.WORKOS_COOKIE_PASSWORD)
                result2 = new_sess.authenticate()
                if getattr(result2, "authenticated", False):
                    g._pending_session_cookie = new_sealed
                    _sess_memo_put(sealed, new_sealed)  # publish for parallel holders
                    log.info("Session refresh (manual local-seal) succeeded; new cookie staged")
                    return result2, new_sealed
                log.info("Session refresh re-auth not authenticated: reason=%s",
                         getattr(result2, "reason", None))
        except WorkOSBadRequestError as e:
            # Invalid grant: EITHER a genuine session end OR a sibling request
            # consumed this rotation a moment ago - check the memo once more
            # before declaring the session dead.
            hit = _try_memoized()
            if hit:
                return hit
            log.info("Session refresh invalid grant (re-login needed): %s", e)
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
                    import hashlib as _hashlib
                    change_fingerprint = _hashlib.sha256(
                        (
                            f"{(old_email or '').strip().lower()}\0"
                            f"{(workos_user.email or '').strip().lower()}"
                        ).encode("utf-8")
                    ).hexdigest()[:20]
                    enqueue_mailerlite_reconcile(
                        s,
                        u,
                        f"email-change:{u.id}:{change_fingerprint}",
                        payload={
                            "remove_email": old_email,
                            "level_tier": u.tier,
                        },
                    )
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
            # REVERSE TRIAL: every brand-new signup gets the full Strategist
            # experience for 7 days. tier stays 'explorer' - the elevation
            # happens at token-mint time via effective_tier(), so expiry is
            # implicit (no cron, no tier mutation). CREATE path only; the
            # match/update paths above never touch this.
            reverse_trial_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        display_name = " ".join(filter(None, [
            getattr(workos_user, "first_name", None),
            getattr(workos_user, "last_name", None),
        ])) or None
        s.add(u)
        try:
            # Durable lifecycle routing is committed atomically with the User.
            # The worker sends no HTTP request on this signup hot path.
            s.flush()
            enqueue_signup_lifecycle(s, u, name=display_name)
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
        # GA4: mark this row as a genuinely brand-new signup (transient,
        # non-persisted attribute - NOT a mapped column) so auth_callback can
        # fire a GA4 sign_up event ONLY here, never on every login. Plain
        # attribute assignment survives commit/refresh: expire-on-commit only
        # expires SQLAlchemy-mapped columns, not arbitrary python attributes.
        # Deliberately NOT set on the IntegrityError re-query path above (the
        # sibling worker that actually won the race already gets this flag on
        # its own return u; marking it here too would double-fire sign_up
        # for a two-tab signup race).
        u._tw_new_signup = True
        # Audit
        write_audit(
            actor_label="workos_signin",
            action="user_created",
            target_user_id=u.id,
            details={"email": workos_user.email, "workos_user_id": workos_user.id},
        )
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

    # GA4 sign_up (Measurement Protocol) - ONLY on the path where
    # lazy_create_user just inserted a brand-new row, never on a plain login.
    # client_id comes from the browser's own _ga cookie on this request (the
    # WorkOS-hosted-UI redirect back to us); send_event no-ops safely if it's
    # absent or GA isn't configured (dev/staging).
    if getattr(db_user, "_tw_new_signup", False):
        send_event(parse_ga_client_id(request), "sign_up", {"method": "workos"},
                   user_id=str(db_user.id))

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
    # Access fields derive from the EFFECTIVE tier (reverse-trial elevation);
    # user.tier inside to_dict() stays the raw billing tier. trial_ends_at =
    # ISO end of an ACTIVE reverse trial, else None (additive; distinct from
    # user.trial_ends_at, the admin-granted paid trial).
    eff_tier = effective_tier(u)
    resp = jsonify({
        "authenticated": True,
        "user": u.to_dict(),
        "effective_tier": eff_tier,
        "trial_ends_at": reverse_trial_ends_at_iso(u) or None,
        "wp_user_levels": tier_to_wp_user_levels(eff_tier),
        "legacy_wp_level": tier_to_legacy_level(eff_tier),
    })
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ============================================================
# Onboarding usage telemetry -> the end-of-trial TRUST SIGNAL
# ============================================================
# Append-only log of what a trial user actually did (markets/symbols/horizon) so
# the end-of-trial card can recommend the MINIMUM tier that covers their real
# usage ("you don't need Strategist"). Low-sensitivity, same-origin, authed.
_ONBOARDING_EVENT_TYPES = {
    "market_opened", "symbol_scored", "wave_viewer_opened", "pattern_saved",
    "reverse_date_range", "pe_toggle", "report_view", "persona",
}


def _min_tier_for_markets(used_ids):
    """Smallest tier whose resources_allowed superset-covers the used market ids.
    Returns 'explorer' when Dow-30-only (the free floor genuinely covers them) -
    the strongest trust signal. config.TIER_FEATURES is the source of truth.
    Returns None when nothing was logged (caller must hedge the copy)."""
    used = set()
    for m in used_ids:
        try:
            used.add(int(m))
        except (TypeError, ValueError):
            pass
    if not used:
        return None
    for t in ("explorer", "navigator", "analyst", "strategist"):
        allowed = (config.TIER_FEATURES.get(t) or {}).get("resources_allowed")
        if allowed == "all":
            return t
        if allowed and used.issubset(set(allowed)):
            return t
    return "strategist"


@app.route("/api/onboarding/event", methods=["POST"])
@csrf.exempt  # same-origin authed fetch; append-only low-sensitivity telemetry, no mutation
@require_login
def onboarding_event():
    u = get_current_user()
    if u is None:
        return jsonify({"ok": False}), 401
    data = request.get_json(silent=True) or {}
    etype = (data.get("type") or "").strip().lower()
    if etype not in _ONBOARDING_EVENT_TYPES:
        return jsonify({"ok": False, "error": "bad_type"}), 400
    detail = data.get("detail")
    if not isinstance(detail, dict):
        detail = {}
    else:
        try:
            import json as _json
            if len(_json.dumps(detail)) > 2000:
                detail = {"_truncated": True}
        except Exception:
            detail = {}
    s = DBSession()
    try:
        s.add(OnboardingEvent(user_id=u.id, event_type=etype, detail=detail))
        s.commit()
    except Exception:
        s.rollback()
        log.exception("onboarding_event insert failed uid=%s", u.id)
        return jsonify({"ok": False}), 500
    finally:
        s.close()
    return jsonify({"ok": True})


@app.route("/api/onboarding/usage-summary")
@require_login
def onboarding_usage_summary():
    """Aggregate the user's logged trial usage and compute the MINIMUM tier that
    covers it (the trust signal). `measured` is False when there are no events yet -
    the caller must then HEDGE the copy ("you spent most of your week on ...")
    rather than claim a measured number it cannot produce."""
    u = get_current_user()
    if u is None:
        return jsonify({"authenticated": False}), 401
    s = DBSession()
    try:
        rows = s.query(OnboardingEvent).filter(OnboardingEvent.user_id == u.id).all()
    finally:
        s.close()
    market_ids, short_ct, long_ct, patterns_saved, max_years = set(), 0, 0, 0, 0
    for r in rows:
        d = r.detail or {}
        if r.event_type == "market_opened" and d.get("market_id") is not None:
            market_ids.add(str(d.get("market_id")))
        elif r.event_type == "pattern_saved":
            patterns_saved += 1
        elif r.event_type == "reverse_date_range":
            long_ct += 1
        elif r.event_type == "persona":
            if d.get("persona") == "long":
                long_ct += 1
            elif d.get("persona") == "short":
                short_ct += 1
        elif r.event_type in ("symbol_scored", "wave_viewer_opened", "report_view"):
            # ONLY setup-viewing events legitimately carry a horizon (days) / lookback
            # (years). Parsing them for every row double-counted reverse_date_range and
            # let stray numbers in unrelated payloads skew persona/max_years.
            try:
                days = int(d.get("days"))
                if 0 < days <= 120:
                    short_ct += 1
                elif days >= 150:
                    long_ct += 1
            except (TypeError, ValueError):
                pass
            try:
                max_years = max(max_years, int(d.get("years") or 0))
            except (TypeError, ValueError):
                pass
    ordered = sorted(market_ids, key=lambda x: int(x) if str(x).isdigit() else 999)
    persona = "long" if long_ct > short_ct else ("short" if short_ct > 0 else "both")
    resp = jsonify({
        "measured": len(rows) > 0,
        "event_count": len(rows),
        "markets_used": ordered,
        "market_names": [config.available_resources.get(str(m), str(m)) for m in ordered],
        "persona": persona,
        "patterns_saved": patterns_saved,
        "max_years": max_years,
        "recommended_tier": _min_tier_for_markets(market_ids),
    })
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ============================================================
# /api/activation/ai-score-viewed - Postgres activation signal
# ============================================================
# GTM playbook CARD W1.4 (docs/marketing/GTM_EXECUTION_PLAYBOOK.md). Fired
# once by the React wave-viewer the first time a logged-in, AI-eligible user
# (Analyst+, config.ml_score_access_levels) actually renders an AI score.
# Strategy §2 persistence rule (BINDING): the day-2/day-7 trial-activation
# emails read users.first_ai_score_viewed_at, NEVER GA4 - GA4 is analytics
# only. This handler is the SINGLE place both are written, in order:
#   1. append an onboarding_events row (event_type='ai_score_viewed') -
#      reuses the existing append-only table (models.py:560), no new table.
#   2. idempotent first-touch UPDATE of users.first_ai_score_viewed_at.
#   3. fire the GA4 ai_score_viewed Measurement Protocol event (fail-open -
#      ga4_mp.send_event never raises; a GA outage must never fail this
#      request, and the Postgres write above happens even when GA4 is
#      unconfigured, e.g. dev/staging).
@app.route("/api/activation/ai-score-viewed", methods=["POST"])
@csrf.exempt  # same-origin authed fetch; append-only + idempotent first-touch, no destructive mutation
@require_login
def api_activation_ai_score_viewed():
    u = get_current_user()
    if u is None:
        return jsonify({"ok": False}), 401

    data = request.get_json(silent=True) or {}
    detail = data.get("detail")
    if not isinstance(detail, dict):
        detail = {}
    else:
        # Storage-key discipline (tw-coding-standards): market is a stable resource
        # key ('0'..'16'), never free text - coerce to str, drop anything else oversized.
        if "market" in detail and detail["market"] is not None:
            detail["market"] = str(detail["market"])
        try:
            if len(_json.dumps(detail)) > 2000:
                detail = {"_truncated": True}
        except Exception:
            detail = {}

    s = DBSession()
    try:
        # 1. Append-only per-view telemetry row (reuses onboarding_events).
        s.add(OnboardingEvent(user_id=u.id, event_type="ai_score_viewed", detail=detail))

        # 2. Idempotent first-touch stamp - only the FIRST view sets it, ever.
        first_touch = False
        db_user = s.query(User).filter_by(id=u.id).with_for_update().first()
        if db_user is not None and db_user.first_ai_score_viewed_at is None:
            db_user.first_ai_score_viewed_at = func.now()
            first_touch = True

        s.commit()
    except Exception:
        s.rollback()
        log.exception("api_activation_ai_score_viewed failed uid=%s", u.id)
        return jsonify({"ok": False}), 500
    finally:
        s.close()

    # 3. GA4 server-side event - fail-open, fired AFTER the Postgres commit so a GA
    # outage/misconfiguration (the normal dev/staging state) never affects the write above.
    try:
        client_id = parse_ga_client_id(request)
        send_event(
            client_id,
            "ai_score_viewed",
            {"market": detail.get("market"), "symbol": detail.get("symbol"), "horizon": detail.get("horizon")},
            user_id=str(u.id),
        )
    except Exception:
        log.warning("ga4_mp send_event raised unexpectedly for ai_score_viewed uid=%s", u.id)

    return jsonify({"ok": True, "first_touch": first_touch})


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


# ------------------------------------------------------------
# /api/lead-report - free personalized seasonal report (lead magnet)
# Mirrors the /api/contact stack (honeypot + per-IP rate limit + DB-canonical +
# best-effort email) but the report is BUILT + SENT in a background thread so
# the worker returns immediately. Historical record only - no forward claims.
# ------------------------------------------------------------
# Free seasonal-report quota by tier: (day, week). 'anon' = the top-of-funnel cap for
# not-logged-in visitors; logged-in subscribers get the same feature with more room (an
# upgrade lever). Anonymous is counted by ip_hash; logged-in by user_id (IP-proof).
# Keyed by effective_tier(); tune freely.
LEAD_REPORT_QUOTAS = {
    "anon":       {"day": 2,  "week": 5},
    "explorer":   {"day": 5,  "week": 15},
    "navigator":  {"day": 10, "week": 30},
    "analyst":    {"day": 20, "week": 60},
    "strategist": {"day": 50, "week": 150},
}


# --- unsubscribe: signed token + the shared suppression list (Resend + MailerLite) ---
def _unsub_secret():
    # no source-visible fallback: an empty key would let anyone forge unsub tokens.
    sec = getattr(config, "API_KEY_HMAC_SECRET", "") or ""
    if not sec:
        raise RuntimeError("API_KEY_HMAC_SECRET is empty; refusing to mint/verify unsub tokens")
    return sec.encode("utf-8")


def make_unsub_token(email):
    import hmac, hashlib, base64
    e = (email or "").strip().lower()
    sig = hmac.new(_unsub_secret(), e.encode("utf-8"), hashlib.sha256).digest()[:18]
    b = lambda raw: base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return b(e.encode("utf-8")) + "." + b(sig)


def verify_unsub_token(token):
    import hmac, hashlib, base64
    try:
        e_b64, sig_b64 = (token or "").split(".", 1)
        pad = lambda s: s + "=" * (-len(s) % 4)
        email = base64.urlsafe_b64decode(pad(e_b64)).decode("utf-8").strip().lower()
        sig = base64.urlsafe_b64decode(pad(sig_b64))
        expected = hmac.new(_unsub_secret(), email.encode("utf-8"), hashlib.sha256).digest()[:18]
        if hmac.compare_digest(sig, expected):
            return email
    except Exception:
        pass
    return None


def _unsub_url(email):
    base = (getattr(config, "tw2_public_url", "") or "").rstrip("/")
    return "%s/unsubscribe?token=%s" % (base, make_unsub_token(email))


def _is_suppressed(email):
    from models import EmailOptout
    s = DBSession()
    try:
        return s.get(EmailOptout, (email or "").strip().lower()) is not None
    except Exception as e:
        # fail CLOSED: on a DB error treat as suppressed. A missed marketing email is
        # harmless; mailing a real opt-out is a CAN-SPAM violation. (Only the report
        # worker calls this, so a transient blip just defers that one send.)
        log.warning("suppression check failed for %s (failing closed): %s", email, e)
        return True
    finally:
        s.close()


def _suppress(email, source):
    from models import EmailOptout
    from sqlalchemy.dialects.postgresql import insert as _pg_insert
    import hashlib as _hashlib
    e = (email or "").strip().lower()
    if not e:
        return
    s = DBSession()
    try:
        # race-free idempotent upsert (concurrent link GET + Gmail POST + dup webhooks)
        s.execute(_pg_insert(EmailOptout).values(email=e, source=source)
                  .on_conflict_do_nothing(index_elements=["email"]))
        # A direct MailerLite unsubscribe below is deliberately best-effort so
        # the public one-click endpoint can ACK quickly. For account holders,
        # persist the same suppression in the lifecycle outbox transaction so
        # a process crash or transient MailerLite outage cannot leave them in
        # an already-running automation. Include the address in the payload so
        # the worker still cleans it if WorkOS changes the user's email before
        # this row is processed.
        user = (
            s.query(User)
            .filter(func.lower(User.email) == e)
            .with_for_update()
            .first()
        )
        if user is not None:
            email_fingerprint = _hashlib.sha256(e.encode("utf-8")).hexdigest()[:20]
            enqueue_mailerlite_reconcile(
                s,
                user,
                f"email-optout:{user.id}:{email_fingerprint}",
                payload={"remove_email": e},
            )
        s.commit()
    except Exception as ex:
        s.rollback(); log.warning("suppress failed for %s: %s", e, ex)
    finally:
        s.close()


def leads_tickers_for_email(email, max_tickers=15):
    """Union of tickers this email has asked about across ALL its (non-spam) report
    requests, newest-first + deduped. The activation bridge calls this at signup to
    pre-load 'their stocks' as a starter watchlist - richer than the last report's
    tickers alone (someone who ran the report 3 times gets all of them)."""
    from models import EmailLead
    e = (email or "").strip().lower()
    if not e:
        return []
    s = DBSession()
    try:
        rows = s.execute(
            select(EmailLead.tickers).where(EmailLead.email == e)
            # status != 'spam' intentionally INCLUDES pending_confirm/expired - we want ALL of
            # this person's stocks; safe because callers run it only for the signed-in/verified email.
            .where(EmailLead.status != "spam")
            .order_by(EmailLead.created_at.desc())
        ).all()
    except Exception as ex:
        log.warning("leads_tickers_for_email failed for %s: %s", e, ex)
        return []
    finally:
        s.close()
    seen, out = set(), []
    for (tk,) in rows:
        for t in (tk or []):
            u = (t or "").strip().upper()
            if u and u not in seen:
                seen.add(u); out.append(u)
                if len(out) >= max_tickers:
                    return out
    return out


def account_cta_mode(email):
    """Report-email CTA mode for the recipient, looked up by email (privacy-safe - their own
    address). 'signup' = no account; 'open_app' = existing user WITH score access (paid tier or
    an active reverse-trial, per effective_tier); 'upgrade' = free Explorer (no AI score yet).
    So a paying subscriber isn't pitched a trial, and a trial-used free user gets an upgrade,
    not a 'start free' they can't take."""
    from models import User
    e = (email or "").strip().lower()
    if not e:
        return "signup"
    s = DBSession()
    try:
        u = s.execute(select(User).where(func.lower(User.email) == e)).scalar_one_or_none()
        if u is None:
            return "signup"
        try:
            tier = effective_tier(u)
        except Exception:
            tier = (getattr(u, "tier", None) or "explorer")
        # open_app ONLY for tiers that actually have the AI-score view right now (effective_tier
        # elevates an active reverse-trial to 'strategist'). Everything else - explorer (past or
        # without the 7-day trial), 'canceled' (lapsed), unknown - gets 'upgrade', so we never
        # imply access a free/lapsed account does not have, and never re-pitch a used-up trial.
        return "open_app" if tier in ("analyst", "strategist") else "upgrade"
    except Exception as ex:
        log.warning("account_cta_mode failed for %s: %s", e, ex)
        return "signup"
    finally:
        s.close()


def _update_lead(lead_id, status, detail=None, sent=False):
    """Best-effort status/detail update on an EmailLead row (called from the
    background worker thread)."""
    import uuid as _uuid
    from models import EmailLead
    s = DBSession()
    try:
        lead = s.get(EmailLead, _uuid.UUID(str(lead_id)))
        if not lead:
            return
        lead.status = status
        if detail is not None:
            lead.detail = detail
        if sent:
            lead.sent_at = func.now()
        s.commit()
    except Exception as e:
        s.rollback()
        log.warning("update_lead failed lead=%s: %s", lead_id, e)
    finally:
        s.close()


@app.route("/api/lead-report", methods=["POST"])
@csrf.exempt  # anonymous lead capture; abuse gate is honeypot + per-IP rate limit, not CSRF
def api_lead_report():
    import re as _re
    import threading
    from contact_form import hash_ip
    from models import EmailLead

    data = request.get_json(silent=True) or {}

    # Honeypot: hidden 'company' field humans never fill in -> fake-200 for bots.
    if (data.get("company") or "").strip():
        log.info("api_lead_report honeypot tripped ip=%s", _client_ip())
        return jsonify({"ok": True}), 200

    email  = (data.get("email") or "").strip().lower()
    raw    = data.get("tickers") or []
    if isinstance(raw, str):
        raw = [raw]
    source = (data.get("source") or "home_free_report").strip()[:60]

    # Normalize: uppercase, ticker-safe chars only, dedupe, cap at 3.
    seen, tickers = set(), []
    for t in raw:
        sym = _re.sub(r"[^A-Z0-9.\-]", "", (t or "").strip().upper())
        if sym and sym not in seen:
            seen.add(sym); tickers.append(sym)
        if len(tickers) == 3:
            break

    if not email or "@" not in email or len(email) > 320:
        return jsonify({"ok": False, "error": "email_invalid"}), 400
    if not tickers:
        return jsonify({"ok": False, "error": "tickers_invalid"}), 400

    ip        = _client_ip()
    ip_hashed = hash_ip(ip)
    ua        = (request.headers.get("User-Agent") or "")[:500]
    user      = get_current_user()
    tier      = effective_tier(user) if user is not None else "anon"
    quota     = LEAD_REPORT_QUOTAS.get(tier, LEAD_REPORT_QUOTAS["anon"])

    # Tiered day + week quota -> over EITHER window = store as spam (still a signal),
    # no email. Logged-in users are counted by user_id (IP-proof, scales with tier);
    # anonymous by ip_hash. 'spam' rows do not count toward the quota.
    status = "requested"
    s = DBSession()
    try:
        base = select(func.count(EmailLead.id)).where(EmailLead.status != "spam")
        if user is not None:
            base = base.where(EmailLead.user_id == user.id)
        elif ip_hashed:
            base = base.where(EmailLead.ip_hash == ip_hashed)
        else:
            base = None
        if base is not None:
            day_n  = s.execute(base.where(EmailLead.created_at > func.now() - timedelta(days=1))).scalar() or 0
            week_n = s.execute(base.where(EmailLead.created_at > func.now() - timedelta(days=7))).scalar() or 0
            if day_n >= quota["day"] or week_n >= quota["week"]:
                status = "spam"
                log.warning("api_lead_report quota hit tier=%s id=%s day=%s/%s week=%s/%s",
                            tier, (str(user.id) if user is not None else (ip_hashed or "")[:12]),
                            day_n, quota["day"], week_n, quota["week"])
    finally:
        s.close()

    # Spam path: store the row (still a useful signal) and return 200 so the
    # rate limit stays invisible to the bot. No coverage call, no email.
    if status == "spam":
        s = DBSession()
        try:
            s.add(EmailLead(email=email, tickers=tickers, source=source,
                            status="spam", user_agent=ua, ip_hash=ip_hashed,
                            user_id=(user.id if user is not None else None)))
            s.commit()
        except Exception as e:
            s.rollback(); log.warning("api_lead_report spam insert failed: %s", e)
        finally:
            s.close()
        return jsonify({"ok": True}), 200

    # Resolve coverage synchronously (cheap) so we never promise an email we
    # cannot build. All-uncovered -> 400 the modal surfaces inline.
    import seasonal_report
    try:
        cov = seasonal_report.resolve_coverage(tickers)
    except Exception as e:
        log.exception("api_lead_report coverage resolve failed: %s", e)
        return jsonify({"ok": False, "error": "server_error"}), 500
    if not cov["covered"]:
        return jsonify({"ok": False, "error": "no_coverage",
                        "not_covered": cov["not_covered"]}), 400

    # DOUBLE OPT-IN: store pending_confirm + a one-time token and email a LIGHTWEIGHT
    # confirmation link. The heavy per-ticker report is built + sent ONLY after the user
    # clicks that link (api_lead_report_confirm). This neutralizes email-bombing - an
    # unrequested address just receives one ignorable confirm email, never a report.
    import secrets as _secrets
    confirm_token = _secrets.token_urlsafe(32)
    s = DBSession()
    try:
        lead = EmailLead(email=email, tickers=tickers, source=source,
                         status="pending_confirm", confirm_token=confirm_token,
                         user_agent=ua, ip_hash=ip_hashed,
                         user_id=(user.id if user is not None else None))
        s.add(lead); s.commit()
    except Exception as e:
        s.rollback()
        log.exception("api_lead_report insert failed: %s", e)
        return jsonify({"ok": False, "error": "server_error"}), 500
    finally:
        s.close()

    sender = getattr(config, "LEAD_EMAIL_FROM", "") or getattr(config, "SUPPORT_EMAIL_FROM", "")
    base = (getattr(config, "tw2_public_url", "") or "").rstrip("/")
    confirm_url = "%s/api/lead-report/confirm?token=%s" % (base, confirm_token)

    def _send_confirm(email, confirm_url, tickers, sender):
        try:
            from email_utils import resend_send_email
            if not sender:
                log.error("api_lead_report: no sender configured for the confirmation email")
                return
            subj, text, html = seasonal_report.render_confirm_email(confirm_url, tickers)
            resend_send_email(to=email, subject=subj, body_text=text, html=html,
                              from_addr=sender, reply_to="hello@tradewave.ai")
        except Exception as e:
            log.exception("api_lead_report confirm-email send failed: %s", e)

    threading.Thread(target=_send_confirm, args=(email, confirm_url, tickers, sender),
                     daemon=True).start()
    return jsonify({"ok": True}), 200


@app.route("/api/lead-report/confirm", methods=["GET"])
@csrf.exempt  # clicked from an email; idempotent read of a one-time token, not a form post
def api_lead_report_confirm():
    import threading
    from datetime import datetime, timezone, timedelta as _td
    from models import EmailLead
    import seasonal_report

    token = (request.args.get("token") or "").strip()
    if not token:
        return seasonal_report.render_confirm_landing("invalid"), 400

    s = DBSession()
    lead_id = email = None
    tickers = []
    try:
        lead = s.execute(
            select(EmailLead).where(EmailLead.confirm_token == token)
        ).scalar_one_or_none()
        if lead is None:
            return seasonal_report.render_confirm_landing("invalid"), 404
        if lead.confirmed_at is not None or lead.status == "sent":
            return seasonal_report.render_confirm_landing("used"), 200
        if lead.created_at and (datetime.now(timezone.utc) - lead.created_at) > _td(days=7):
            lead.status = "expired"; s.commit()
            return seasonal_report.render_confirm_landing("expired"), 200
        lead.confirmed_at = func.now()
        s.commit()
        lead_id = str(lead.id); email = lead.email; tickers = list(lead.tickers or [])
    except Exception as e:
        s.rollback()
        log.exception("api_lead_report_confirm failed: %s", e)
        return seasonal_report.render_confirm_landing("invalid"), 500
    finally:
        s.close()

    sender = getattr(config, "LEAD_EMAIL_FROM", "") or getattr(config, "SUPPORT_EMAIL_FROM", "")

    # Now (and only now) build + send the full report, off the request path.
    def _worker(lead_id, tickers, email):
        try:
            from email_utils import resend_send_email, mailerlite_subscribe
            if _is_suppressed(email):
                _update_lead(lead_id, "failed", {"error": "suppressed"})
                return
            rep = seasonal_report.build_report_data(tickers)
            if not rep["tickers"]:
                _update_lead(lead_id, "failed", {"not_covered": rep["not_covered"]})
                return
            if not sender:
                log.error("api_lead_report_confirm: no sender configured")
                _update_lead(lead_id, "failed", {"error": "no_sender"})
                return
            unsub = _unsub_url(email)
            cta_mode = account_cta_mode(email)   # adapt the CTA if they already have an account
            html = seasonal_report.render_email_html(rep, unsubscribe_url=unsub, cta_mode=cta_mode)
            text = seasonal_report.render_email_text(rep, unsubscribe_url=unsub, cta_mode=cta_mode)
            subj = "Your Seasonal Report: " + ", ".join(t["symbol"] for t in rep["tickers"])
            ok = resend_send_email(to=email, subject=subj, body_text=text, html=html,
                                   from_addr=sender, reply_to="hello@tradewave.ai",
                                   headers={"List-Unsubscribe": "<%s>" % unsub,
                                            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
            if not _is_suppressed(email):   # never re-activate a MailerLite unsubscribe
                try:
                    mailerlite_subscribe(email)
                except Exception:
                    pass
            _update_lead(lead_id, "sent" if ok else "failed",
                         {"covered": [t["symbol"] for t in rep["tickers"]],
                          "not_covered": rep["not_covered"], "as_of": rep["as_of"].isoformat()},
                         sent=ok)
        except Exception as e:
            log.exception("api_lead_report_confirm worker failed lead=%s: %s", lead_id, e)
            _update_lead(lead_id, "failed", {"error": str(e)[:200]})

    threading.Thread(target=_worker, args=(lead_id, tickers, email), daemon=True).start()
    return seasonal_report.render_confirm_landing("ok"), 200


@app.route("/unsubscribe", methods=["GET", "POST"])
@csrf.exempt  # clicked from an email + the Gmail one-click POST; the signed token IS the auth
def unsubscribe():
    import seasonal_report
    token = (request.args.get("token") or request.form.get("token") or "").strip()
    email = verify_unsub_token(token) if token else None
    if not email:
        if request.method == "POST":
            return ("", 400)
        return seasonal_report.render_unsub_landing("invalid"), 400
    _suppress(email, "one_click" if request.method == "POST" else "link")

    def _propagate(em):
        try:
            from email_utils import mailerlite_unsubscribe
            mailerlite_unsubscribe(em)   # propagate the opt-out to MailerLite too
        except Exception as e:
            log.warning("mailerlite_unsubscribe call failed for %s: %s", em, e)

    if request.method == "POST":
        # Gmail one-click prober has a short timeout: suppress locally, ACK fast, sync async.
        import threading
        threading.Thread(target=_propagate, args=(email,), daemon=True).start()
        return ("", 200)
    _propagate(email)
    return seasonal_report.render_unsub_landing("ok"), 200


@app.route("/webhooks/mailerlite", methods=["POST"])
@csrf.exempt  # external webhook; authenticated by a shared secret, fail-closed off dev
def mailerlite_webhook():
    import hmac as _hmac
    # AuthN: require MAILERLITE_WEBHOOK_SECRET, sent as the X-Webhook-Secret header (preferred,
    # stays out of access logs) or a ?secret= query param, constant-time compared. If it is
    # UNSET, fail CLOSED on any non-dev env (open only on dev). TODO(hardening): switch to
    # MailerLite's documented request signature over the raw body once confirmed (O2).
    want = getattr(config, "MAILERLITE_WEBHOOK_SECRET", "") or ""
    env = (getattr(config, "tw2_env", "") or "dev")
    got = request.headers.get("X-Webhook-Secret") or request.args.get("secret") or ""
    if want:
        if not _hmac.compare_digest(got, want):
            return ("", 403)
    elif env != "dev":
        log.error("mailerlite_webhook: MAILERLITE_WEBHOOK_SECRET unset on %s; rejecting", env)
        return ("", 403)
    # cap the body so a public endpoint can't be used for a memory / DB-write DoS
    if (request.content_length or 0) > 256 * 1024:
        return ("", 413)
    data = request.get_json(silent=True) or {}
    events = data.get("events")
    if not isinstance(events, list):
        events = [data]
    n = 0
    for ev in events[:1000]:
        if not isinstance(ev, dict):
            continue
        etype = (ev.get("type") or ev.get("event") or "")
        # suppress on unsubscribe, spam complaint, OR hard bounce so Resend stops mailing too
        # (a MailerLite complaint that doesn't reach the Resend side risks the Gmail/Yahoo
        # <0.3% complaint threshold). MailerLite's connect-API event is subscriber.spam_reported
        # (confirmed against the live webhook API 2026-07-07); .spam_complaint kept defensively.
        if etype.endswith((".unsubscribe", ".unsubscribed", ".spam_complaint", ".spam_reported", ".bounced")):
            sub = ev.get("subscriber") or ev.get("data") or {}
            em = (sub.get("email") if isinstance(sub, dict) else None) or ev.get("email")
            if em and "@" in em and len(em) <= 320:
                _suppress(em, "mailerlite_webhook"); n += 1
    if n:
        log.info("mailerlite_webhook: suppressed %d email(s)", n)
    return jsonify({"ok": True}), 200


# ============================================================
# /app/ - React shell with REAL session globals injected
# (replaces the milestone-1 nginx sub_filter stub)
# ============================================================

REACT_BUILD_INDEX = Path("/home/flask/web-react/build/index.html")
TW_HEADER_TEMPLATE = Path("/home/flask/site/templates/_tw_header.html")


def effective_tier(user) -> str:
    """Tier used for ACCESS decisions (LTK claims, /app/ window globals,
    /api/me) - NOT for billing.

    REVERSE TRIAL: an 'explorer' whose reverse_trial_ends_at is in the future
    is elevated to 'strategist' here, at token-mint time. users.tier is never
    mutated, so expiry is implicit (the next mint after the deadline falls
    back to explorer - no cron; web/expire_trials.py sweeps only the separate
    admin-granted trial_ends_at column). Paid/billing paths (Stripe webhook,
    /stripe/success, admin) must keep reading user.tier raw.
    """
    # Delegates to the shared cutoff math so the gateway (apiserver/auth.py, which
    # mirrors this into the MCP/consumer-OAuth scope) cannot drift from the website.
    # ROLE BYPASS: admins/service principals (config.ROLE_BYPASSES_TIER, passed in so
    # config stays authoritative here) always get the full platform view - the founder
    # must never hit his own paywall. Access-only; billing reads user.tier raw.
    return reverse_trial.effective_web_tier(
        user.tier, user.roles, user.reverse_trial_ends_at, config.ROLE_BYPASSES_TIER
    )


def reverse_trial_ends_at_iso(user) -> str:
    """ISO-8601 end of the user's ACTIVE reverse trial, or '' when no
    trial elevation is in effect (no trial, expired, or a paid tier). Non-empty
    means the front end can show a countdown off it.

    Must key on the TRIAL specifically, not on effective_tier() != raw tier:
    the role bypass (super_admin etc.) also elevates the effective tier, and an
    admin explorer row with reverse_trial_ends_at=NULL used to 500 /app/ and
    /api/me here (None.isoformat())."""
    if (user.tier or "explorer") == "explorer" and reverse_trial.in_reverse_trial(user.reverse_trial_ends_at):
        return user.reverse_trial_ends_at.isoformat()
    return ""


def generate_ltk(user) -> str:
    """Sign a short-lived JWT containing the user's identity claims.
    The appserver verifies this with config.APPSERVER_JWT_SECRET when
    useUMP=False, and uses its claims for is_admin and tier resolution.

    F2.13 - adds aud/iss claims so the appserver can defend against tokens
    minted by other services that might share the same secret. Appserver
    enforces `audience="tw2-appserver"` and `issuer="tw2-web"` at all 16
    jwt.decode() call sites in appserver.py (F3 closed).

    tier/legacy_level come from effective_tier(): an explorer in their 7-day
    reverse trial mints Strategist claims; the 8h LTK lifetime bounds how
    long after expiry an already-minted token keeps the elevated access.
    """
    eff_tier = effective_tier(user)
    return jwt.encode(
        {
            "user_id": str(user.id),
            "workos_user_id": user.workos_user_id,
            "email": user.email,
            "tier": eff_tier,
            "legacy_level": tier_to_legacy_level(eff_tier),
            # Per-tier historical-years cap (10 Explorer / 15 Navigator; "" = uncapped).
            # Informational/defensive - the appserver re-derives + enforces it from config.
            "max_years": config.num_years_allowed_by_level.get(tier_to_legacy_level(eff_tier), ""),
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

    return _render_app_shell(u)


# ============================================================
# Dev-only screenshot-harness entry point
# ============================================================
#
# /internal/capture/app renders the SAME authenticated app shell as /app/,
# but for a fixed internal "capture-bot" service account instead of a real
# WorkOS session - so an automated screenshot pipeline can fetch the
# wave-viewer HTML without driving a real OAuth login.
#
# TWO independent gates keep this from being an auth bypass in staging/prod:
#   1. ENV GATE: hard 404 unless config.tw2_env == "dev" (checked first,
#      before any DB query - fails closed on every other env).
#   2. NETWORK GATE: this app is served by gunicorn bound to 127.0.0.1:5500
#      (see the tradewave-web unit) with no nginx `location` exposing it
#      externally, so the route is unreachable from outside the box even on
#      dev. Belt-and-suspenders with gate 1, not a substitute for it - the
#      env check is what actually stops this from working if the bind or
#      proxy config ever changes.
#
# The capture-bot user (email capture-bot@tradewave.local) is a
# roles=["user"] / tier="strategist" row with no real WorkOS identity
# (workos_user_id="capture-bot-dev", not a live WorkOS subject) - it can
# never sign in through the normal /login flow, only be looked up here.
@app.route("/internal/capture/app")
def capture_app():
    """Dev-only: render the wave-viewer app shell authenticated as the
    screenshot-bot service account. See the module comment above for the
    two gates (env + localhost-only bind) that keep this dev-only.
    """
    if config.tw2_env != "dev":
        abort(404)
    s = DBSession()
    try:
        u = s.query(User).filter_by(email="capture-bot@tradewave.local").first()
    finally:
        s.close()
    if u is None:
        return jsonify({"error": "capture bot user missing"}), 500
    return _render_app_shell(u)


def _render_app_shell(u):
    """Build the React wave-viewer shell (build/index.html) with REAL window
    globals injected for user `u`, and the shared header swapped in.

    Extracted out of app_index() so the same authenticated shell can be
    rendered for a caller that has already resolved its user by some means
    other than the WorkOS session cookie (see capture_app() above - the
    dev-only screenshot-bot route). Pure extraction: no behavior change vs.
    the original inline body of app_index().
    """
    if not REACT_BUILD_INDEX.exists():
        return jsonify({"error": "React build/index.html not found", "path": str(REACT_BUILD_INDEX)}), 500

    html = REACT_BUILD_INDEX.read_text()
    ltk = generate_ltk(u)
    user_id = str(u.id)
    # Access globals reflect the EFFECTIVE tier (reverse-trial elevation);
    # billing/admin code keeps reading users.tier raw.
    eff_tier = effective_tier(u)
    user_level = tier_to_legacy_level(eff_tier)
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
        # Date-only ISO string (e.g. "2026-06-30") of account creation. Feeds the React
        # onboarding gate (onboarding.js getAccountAgeDays/isAutoArcEligible): a genuinely
        # new user (<=7 days old) auto-enrolls into the 7-day LessonBox arc, an existing
        # user does not. '' when unavailable so the client fails safe (never auto-enrolls
        # on missing data) - created_at has a server_default so this should always be set.
        f'window.current_user_created_at={_js_safe(u.created_at.date().isoformat() if getattr(u, "created_at", None) else "")};'
        f'window.current_user_level={_js_safe(user_level)};'
        f'window.ltk={_js_safe(ltk)};'
        f'window.tw2_user_email={_js_safe(u.email)};'
        f'window.tw2_user_tier={_js_safe(eff_tier)};'
        # Per-tier historical-years cap: 10 (Explorer) / 15 (Navigator) / '' = uncapped
        # (Analyst/Strategist). React grays out year/lookback options above this as an
        # upgrade nudge; '' (falsy) means no cap. Enforced server-side regardless.
        f'window.tw2_max_years={_js_safe(config.num_years_allowed_by_level.get(user_level, ""))};'
        f'window.tw2_is_admin={"true" if is_admin_bool else "false"};'
        f'window.tw2_user_roles={_js_safe(u.roles or ["user"])};'
        f'window.tw2_env={_js_safe(config.tw2_env)};'
        # ISO end of an ACTIVE reverse trial, '' otherwise (additive global).
        f'window.tw2_trial_ends_at={_js_safe(reverse_trial_ends_at_iso(u))};'
        # '1' iff the user has EVER had a reverse trial (future, past, or expired) - lets the
        # React onboarding tell a lapsed-trial Explorer from a never-trialed one (the
        # end-of-trial card must NOT tell a never-trialed user "your access wrapped up").
        f'window.tw2_trial_ever={_js_safe("1" if getattr(u, "reverse_trial_ends_at", None) is not None else "")};'
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

    is_affiliate = False
    if u is not None:
        s = DBSession()
        try:
            from models import Affiliate as _Aff
            is_affiliate = (s.query(_Aff)
                            .filter(_Aff.user_id == u.id,
                                    _Aff.status != "terminated").first() is not None)
        finally:
            s.close()

    return render_template(
        "account.html",
        user=u,
        billing_interval=billing_interval,
        next_renewal_date=next_renewal_date,
        started_date=started_date,
        mcp_teaser=_account_mcp_teaser(u),
        is_affiliate=is_affiliate,
    )


def _account_mcp_teaser(user):
    """READ-ONLY in-chat (MCP) teaser_state for the account card. Mirrors the gateway
    contract (apiserver/auth.py:_resolve_mcp) using the shared reverse_trial helpers so
    the web view never drifts from what the user actually gets in ChatGPT/Claude:
      - explorer + active reverse trial -> explorer_trial (reverts to explorer)
      - navigator + active first-connect window -> navigator_firstconnect (reverts to navigator)
    NEVER arms the navigator column (that is the gateway's job on first connect); this only
    reads navigator_mcp_first_connect_at. GATED behind TW2_MCP_LIVE (the same flag the home
    pill uses) so the card stays hidden until consumer MCP launches - active is forced False
    when the flag is off, even if a teaser window would otherwise be live."""
    state = {"active": False, "kind": None, "ends_at": None, "post_teaser_scope": None}
    if user is None:
        return state
    mcp_live = os.environ.get("TW2_MCP_LIVE", "").strip().lower() in ("1", "true", "yes")
    if not mcp_live:
        return state
    raw_tier = user.tier or "explorer"
    # Mirror the gateway (apiserver/auth.py): the navigator check uses the EFFECTIVE web tier
    # so an admin/service-bypass navigator (eff_web -> strategist) shows no teaser, exactly
    # like the gateway. Explorer-trial stays on the RAW tier (effective_web_tier maps
    # explorer+trial -> strategist, so the raw check is the correct one there).
    eff_web = reverse_trial.effective_web_tier(
        user.tier, user.roles, user.reverse_trial_ends_at, config.ROLE_BYPASSES_TIER)
    if raw_tier == "explorer" and reverse_trial.in_reverse_trial(user.reverse_trial_ends_at):
        rt = user.reverse_trial_ends_at
        return {"active": True, "kind": "explorer_trial",
                "ends_at": rt.isoformat() if rt is not None else None,
                "post_teaser_scope": "explorer"}
    if eff_web == "navigator":
        nav_active, nav_ends = reverse_trial.navigator_teaser_window(
            getattr(user, "navigator_mcp_first_connect_at", None))
        if nav_active:
            return {"active": True, "kind": "navigator_firstconnect",
                    "ends_at": nav_ends, "post_teaser_scope": "navigator"}
    return state


# ============================================================
# Pricing page - simple fallback so /pricing isn't a 404
# (Phase 5 will turn into a real Stripe Checkout flow)
# ============================================================

@app.route("/pricing")
def pricing():
    # Send users to the rich pricing section on the home page (single source
    # of truth). An affiliate referral code on the link (?code=ANNE / ?via=ANNE)
    # must survive the hop: validate it like /join/<code> does, set the same
    # first-touch tw_ref cookie, and carry the code through the redirect so the
    # home-page JS sees it too. Unknown / inactive codes redirect as before.
    raw = request.args.get("code") or request.args.get("via")
    if raw:
        import affiliate_service as afs
        norm = afs.normalize_code(raw)
        if afs.CODE_RE.match(norm):
            s = DBSession()
            try:
                from models import Affiliate
                aff = (s.query(Affiliate)
                       .filter(Affiliate.code == norm, Affiliate.status == "active")
                       .first())
                if aff:
                    resp = make_response(redirect("/?code=%s#pricing" % aff.code, code=302))
                    # First-touch attribution cookie (60 days), same key the
                    # /join/<code> landing page + checkout use.
                    resp.set_cookie("tw_ref", aff.code, max_age=60 * 60 * 24 * 60,
                                    samesite="Lax", secure=request.is_secure, path="/")
                    return resp
            finally:
                s.close()
    return redirect("/#pricing", code=302)


# ============================================================
# Stripe Checkout (Phase 5)
# ============================================================

# Map (tier, period) → Stripe Product name (case-insensitive match)
TIER_PRODUCT_NAMES = {
    ("navigator",  "monthly"): ("navigator",  "month"),
    ("navigator",  "yearly"):  ("navigator",  "year"),
    ("analyst",    "monthly"): ("analyst",    "month"),
    ("analyst",    "yearly"):  ("analyst",    "year"),
    ("strategist", "monthly"): ("strategist", "month"),
    ("strategist", "yearly"):  ("strategist", "year"),
}

# Cache: (tier, period) → price object, fetched once
_price_cache = {}
_price_product_metadata_cache = {}


def _price_product_metadata(price):
    """Return normalized product metadata from an expanded Stripe Price."""
    price_d = (
        price if isinstance(price, dict)
        else (price.to_dict() if hasattr(price, "to_dict") else dict(price))
    )
    product = price_d.get("product")
    if not isinstance(product, dict):
        product = (
            product.to_dict()
            if hasattr(product, "to_dict") else {}
        )
    metadata = product.get("metadata") or {}
    return {
        str(key): str(value)
        for key, value in metadata.items()
        if value is not None
    }


def _metadata_for_price_id(price_id):
    """Resolve even archived prices; transient Stripe failures stay retryable."""
    if price_id in _price_product_metadata_cache:
        return _price_product_metadata_cache[price_id]
    price = stripe.Price.retrieve(price_id, expand=["product"])
    metadata = _price_product_metadata(price)
    _price_product_metadata_cache[price_id] = metadata
    return metadata


def _web_period(value):
    value = str(value or "").strip().lower()
    return {
        "month": "monthly",
        "monthly": "monthly",
        "year": "yearly",
        "annual": "yearly",
        "yearly": "yearly",
    }.get(value)


def _stripe_configured():
    if 'PLACEHOLDER' in (config.STRIPE_SECRET_KEY or ''):
        return False
    if 'PLACEHOLDER' in (config.STRIPE_PUBLISHABLE_KEY or ''):
        return False
    return True


def _refresh_price_cache():
    """Bucket active Stripe prices into (tier, period) slots — metadata-only.

    A price is used ONLY if its product carries all three metadata keys:
      product_line == "eod", tier in {navigator,analyst,strategist}, period in {monthly,yearly}.

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
    valid_tiers = {"navigator", "analyst", "strategist"}
    valid_periods = {"monthly", "yearly"}
    try:
        for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
            prod = p.product
            if not isinstance(prod, dict):
                prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
            metadata = prod.get("metadata") or {}
            _price_product_metadata_cache[p.id] = {
                str(key): str(value)
                for key, value in metadata.items()
                if value is not None
            }
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
    metadata = _metadata_for_price_id(price_id)
    line = str(metadata.get("product_line") or "").strip().lower()
    tier = str(metadata.get("tier") or "").strip().lower()
    period = _web_period(metadata.get("period") or metadata.get("interval"))
    if (
        line == "eod"
        and tier in {"navigator", "analyst", "strategist"}
        and period in {"monthly", "yearly"}
    ):
        return tier, period
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
            _price_product_metadata_cache[p.id] = {
                str(key): str(value)
                for key, value in md.items()
                if value is not None
            }
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
    cached = _api_price_tier.get(price_id)
    if cached:
        return cached
    metadata = _metadata_for_price_id(price_id)
    line = str(metadata.get("product_line") or "").strip().lower()
    tier = str(metadata.get("tier") or "").strip().lower()
    if line == "api" and tier in {"dev", "pro", "business"}:
        return tier
    return None


def _subscription_product_target(price_id, metadata):
    """Return ``(product_line, tier, period)`` for a subscription event.

    The event's current price is canonical because Billing Portal plan changes
    update the item price without rewriting subscription metadata. Exact-price
    lookup also works for archived prices. Subscription metadata is used only
    for a legacy event that has no price ID; lookup failures propagate so
    Stripe retries instead of applying a possibly stale tier.
    """
    metadata = metadata or {}
    line = str(metadata.get("product_line") or "").strip().lower()
    tier = str(
        metadata.get("tier")
        or metadata.get("tw2_tier_target")
        or ""
    ).strip().lower()
    period = _web_period(
        metadata.get("period") or metadata.get("interval")
    )
    metadata_target = (None, None, None)
    if line == "api" and tier in {"dev", "pro", "business"}:
        metadata_target = ("api", tier, None)
    elif (
        line == "eod"
        and tier in {"navigator", "analyst", "strategist"}
        and period in {"monthly", "yearly"}
    ):
        metadata_target = ("eod", tier, period)
    if not price_id:
        return metadata_target

    api_tier = _api_tier_for_price(price_id)
    if api_tier:
        price_target = ("api", api_tier, None)
    else:
        web_tier, web_period = _tier_period_for_price(price_id)
        price_target = (
            ("eod", web_tier, web_period)
            if web_tier else (None, None, None)
        )
    if (
        price_target[0]
        and metadata_target[0]
        and price_target != metadata_target
    ):
        log.warning(
            "stripe subscription metadata is stale for price %s: "
            "metadata=%s price=%s; using price",
            price_id, metadata_target, price_target,
        )
    return price_target


def _current_subscription_snapshot(subscription_id, expected_customer_id):
    """Fetch and validate current Stripe truth for an update/create event."""
    current = stripe.Subscription.retrieve(
        subscription_id,
        expand=["items.data.price.product"],
    )
    current_d = (
        current if isinstance(current, dict)
        else current.to_dict()
    )
    if str(current_d.get("id") or "") != str(subscription_id or ""):
        raise ValueError("Stripe returned a different subscription ID")
    actual_customer = current_d.get("customer")
    if isinstance(actual_customer, dict):
        actual_customer = actual_customer.get("id")
    elif hasattr(actual_customer, "id"):
        actual_customer = actual_customer.id
    if (
        expected_customer_id
        and str(actual_customer or "") != str(expected_customer_id)
    ):
        raise ValueError("Stripe subscription customer does not match event")
    return current_d


def _live_api_subscription_for_customer(customer_id, *, exclude_id=None):
    """Find a current API subscription for one legacy/untracked customer.

    This is used only while adopting the new separate API subscription ID. A
    Stripe lookup failure is intentionally not swallowed so the webhook returns
    500 and retries instead of clearing access from incomplete evidence.
    """
    if not customer_id:
        return None
    for status in ("active", "trialing", "past_due"):
        subscriptions = stripe.Subscription.list(
            customer=customer_id, status=status, limit=100,
        )
        for subscription in subscriptions.auto_paging_iter():
            sub_d = (
                subscription if isinstance(subscription, dict)
                else subscription.to_dict()
            )
            if sub_d.get("id") == exclude_id:
                continue
            items = (sub_d.get("items") or {}).get("data") or []
            price_id = None
            if items:
                price_id = ((items[0] or {}).get("price") or {}).get("id")
            line, tier, _period = _subscription_product_target(
                price_id, sub_d.get("metadata") or {},
            )
            if line == "api" and tier:
                return {
                    "id": sub_d.get("id"),
                    "status": sub_d.get("status") or status,
                    "tier": tier,
                }
    return None


def _created_subscription_can_replace(event_type, current_id,
                                      replacement_id, candidate):
    """Order a freshly hydrated differing ``subscription.created`` event."""
    if event_type != "customer.subscription.created" or not current_id:
        return False
    if str((candidate or {}).get("status") or "").lower() not in {
        "active", "trialing", "past_due",
    }:
        return False
    if not (candidate or {}).get("id"):
        return False
    if replacement_id == current_id:
        return True
    candidate_created = candidate.get("created") if candidate else None
    if not isinstance(candidate_created, (int, float)):
        return False
    current = stripe.Subscription.retrieve(current_id)
    current_d = (
        current if isinstance(current, dict)
        else current.to_dict()
    )
    current_created = current_d.get("created")
    return bool(
        isinstance(current_created, (int, float))
        and candidate_created > current_created
    )


def _resolve_affiliate_promo(raw, period=None):
    """Resolve an affiliate referral code (?code=ANNE / ?via=ANNE / tw_ref cookie)
    to (discount_spec, affiliate_id, code) for an ACTIVE affiliate, or
    (None, None, None). `discount_spec` is the dict to pass in Stripe Checkout's
    `discounts=[...]`: a flat affiliate yields {"promotion_code": <id>}; an
    interval-split affiliate on an interval that carries an override coupon yields
    {"coupon": <override_coupon_id>} (chosen by `period`), otherwise the flat
    promo. Unknown / paused / terminated / malformed codes return the empty tuple
    so checkout proceeds normally (manual promo entry)."""
    if not raw:
        return None, None, None
    import affiliate_service as afs
    code = afs.normalize_code(raw)
    if not afs.CODE_RE.match(code):
        return None, None, None
    s = DBSession()
    try:
        from models import Affiliate
        aff = (s.query(Affiliate)
               .filter(Affiliate.code == code, Affiliate.status == "active")
               .first())
        if not aff:
            return None, None, None
        # Monthly plans use the monthly override coupon when one exists; annual
        # (and everything else) uses the flat promo code (the annual/default rate).
        override = (aff.stripe_coupon_id_monthly
                    if afs._norm_interval(period) == "month" else None)
        if override:
            spec = {"coupon": override}
        elif aff.stripe_promotion_code_id:
            spec = {"promotion_code": aff.stripe_promotion_code_id}
        else:
            spec = None
        return spec, str(aff.id), aff.code
    finally:
        s.close()


def _record_affiliate_referral(session, sub_id, customer_id, metadata):
    """Persist the customer/subscription -> affiliate link from subscription
    metadata (stamped onto subscription_data at checkout). Idempotent (ON CONFLICT
    DO NOTHING on the subscription id). No-op unless metadata carries a valid
    tw2_affiliate_id. Never raises - a referral-write failure must not break the
    webhook (the discount/commission still works off the coupon as a fallback)."""
    aff_id = (metadata or {}).get("tw2_affiliate_id")
    if not (sub_id and aff_id):
        return
    import uuid as _uuid
    try:
        _uuid.UUID(str(aff_id))
    except (ValueError, TypeError):
        return
    try:
        from models import AffiliateReferral
        from sqlalchemy.dialects.postgresql import insert as _pg_insert
        stmt = _pg_insert(AffiliateReferral.__table__).values(
            affiliate_id=aff_id,
            stripe_customer_id=customer_id,
            stripe_subscription_id=sub_id,
            referral_code=(metadata or {}).get("tw2_affiliate_code"),
            source="checkout",
        ).on_conflict_do_nothing(index_elements=["stripe_subscription_id"])
        session.execute(stmt)
    except Exception:
        log.exception("failed to record affiliate referral for subscription %s", sub_id)


def _existing_eod_subscription(customer_id, stored_web_subscription_id=None):
    """Return (subscription_id, item_id, status) for the customer's first
    active-or-trialing EOD-line Stripe subscription (an item whose price
    resolves through the eod price cache), or (None, None, None). A listed
    subscription matching the user's stored web subscription ID also counts;
    this preserves the guard for legacy web prices without modern metadata.

    Lookup failures intentionally propagate. This helper is only called for a
    known Stripe customer; failing closed prevents a transient Stripe error
    from minting that customer a second subscription and another trial."""
    # past_due included: the webhook keeps the paid tier through dunning, so
    # route those customers to the portal (fix the card) instead of a 2nd sub.
    for sub_status in ("active", "trialing", "past_due"):
        for sub in stripe.Subscription.list(
                customer=customer_id, status=sub_status, limit=100).auto_paging_iter():
            sub_d = sub.to_dict() if hasattr(sub, "to_dict") else dict(sub)
            items_d = sub_d.get("items") or {}
            items_list = items_d.get("data", []) if isinstance(items_d, dict) else []
            if (
                stored_web_subscription_id
                and sub_d.get("id") == stored_web_subscription_id
            ):
                first_item = items_list[0] if items_list else {}
                first_item_d = first_item if isinstance(first_item, dict) else (
                    first_item.to_dict() if hasattr(first_item, "to_dict")
                    else dict(first_item))
                return (
                    sub_d.get("id"),
                    first_item_d.get("id"),
                    sub_d.get("status"),
                )
            for item in items_list:
                item_d = item if isinstance(item, dict) else (
                    item.to_dict() if hasattr(item, "to_dict") else dict(item))
                price_d = item_d.get("price") or {}
                price_id = price_d.get("id") if isinstance(price_d, dict) else None
                if price_id and _tier_period_for_price(price_id)[0]:
                    return sub_d.get("id"), item_d.get("id"), sub_d.get("status")
    return None, None, None


def _fire_dunning_final_notice(db_user, event_id):
    """GTM playbook CARD W1.3 - the ONE app-owned dunning email: the final
    pre-cancel "your access pauses" nudge, fired from the invoice.payment_failed
    branch of the Stripe webhook once Stripe has stopped scheduling further Smart
    Retries. Every earlier "your payment failed, please update your card" email in
    the sequence is Stripe's own (Dashboard-side "Email customers about failed
    payments") - this function does not duplicate those.

    Best-effort / fail-open by design (matches email_utils.resend_send_email's own
    contract): never raises past the caller's try/except, and a billing-portal
    session failure degrades to a plain /account link rather than skipping the
    email entirely.
    """
    if not db_user.email:
        return
    public_host = os.environ.get("TW2_PUBLIC_HOST", "tw2.trxstat.com")
    portal_url = f"https://{public_host}/account"
    try:
        if db_user.stripe_customer_id:
            session_obj = stripe.billing_portal.Session.create(
                customer=db_user.stripe_customer_id,
                return_url=f"https://{public_host}/account",
            )
            portal_url = session_obj.url
    except Exception:
        log.warning("dunning: billing-portal session create failed for user %s (event %s); "
                    "falling back to /account link", db_user.id, event_id)

    tier_label = (db_user.tier or "explorer").capitalize()
    subject = "Your TradeWave Access Pauses Soon - Quick Card Update"
    body = (
        f"Your last payment did not go through and our retries have run out.\n\n"
        f"Update your card to keep your {tier_label} access: {portal_url}\n\n"
        f"Nothing else changes if you update your card."
    )
    from email_utils import resend_send_email
    sent = resend_send_email(db_user.email, subject, body)
    # No PII in logs: identify by user id, not email address.
    log.info("dunning final-notice email user=%s sent=%s event=%s", db_user.id, sent, event_id)


# State-changing endpoint: POST only. The pricing template uses
# <form method="post"> hidden-input forms to hit this route.
@app.route("/api/stripe/create-checkout", methods=["GET", "POST"])
@csrf.exempt
@require_login
def stripe_create_checkout():
    """Initiate Stripe Checkout for the requested tier+period.
    Params: tier=navigator|analyst|strategist, period=monthly|yearly (+ optional code=).

    Accepts GET as well as POST: a logged-OUT visitor who clicks Subscribe is
    bounced through WorkOS sign-up by require_login, which preserves only the
    request URL (state=full_path) - not a POST body. So the pricing CTAs submit
    as GET (params in the query string), and after sign-up auth_callback
    redirects (GET) back here with tier/period/code intact, instead of 405-ing
    on a POST-only route. Creating a Checkout Session is non-destructive (no
    charge until the user pays on Stripe's page), so GET is safe here.
    """
    if not _stripe_configured():
        return jsonify({
            "error": "stripe_not_configured",
            "message": "Stripe keys / price IDs are placeholders. Edit /home/flask/config.py and restart the web tier.",
        }), 503

    # Pull tier/period from query OR form (request.values covers both).
    tier   = (request.values.get("tier")   or "").lower()
    period = (request.values.get("period") or "").lower()
    price_id = _price_id_for(tier, period)
    if not price_id:
        return jsonify({
            "error": "price_not_found",
            "message": f"No active Stripe price for tier={tier!r} period={period!r}. "
                       f"Prices resolve by PRODUCT METADATA, not name: the Stripe product "
                       f"needs product_line=eod, tier={tier!r}, period={period!r}. "
                       f"(Conventionally named like "
                       f"{TIER_PRODUCT_NAMES.get((tier,period), ('?','?'))[0]!r}/"
                       f"{TIER_PRODUCT_NAMES.get((tier,period), ('?','?'))[1]!r}, "
                       f"but the name is NOT used for matching.)",
        }), 400

    u = get_current_user()
    public_host = os.environ.get("TW2_PUBLIC_HOST", "tw2.trxstat.com")
    success_url = f"https://{public_host}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url  = f"https://{public_host}/pricing?cancelled=1"

    # GA4: client id off the browser's own _ga cookie. Stashed onto the
    # Checkout Session's own metadata below (distinct from subscription_data's
    # metadata) so the /webhooks/stripe checkout.session.completed handler can
    # attribute the eventual purchase event back to this same GA4 client.
    ga_client_id = parse_ga_client_id(request)

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
                row.api_stripe_subscription_id = None
                row.api_stripe_subscription_status = None
                row.api_tier = None
                s.commit()
            finally:
                s.close()
            # Keep the detached request snapshot aligned with the committed
            # cleanup so replacement metadata cannot reference a dead ID.
            u.stripe_customer_id = None
            u.stripe_subscription_id = None
            u.stripe_subscription_status = None
            u.api_stripe_subscription_id = None
            u.api_stripe_subscription_status = None
            u.api_tier = None

    # An already-subscribed user must NOT get a second subscription (Stripe
    # happily creates one per Checkout session, each with its own 7-day
    # trial). If this customer already carries an active or trialing EOD-line
    # subscription, send them to the Billing Portal to change plan instead -
    # ideally straight into the update-confirm flow for the requested price,
    # else the plain portal /account/manage-subscription opens.
    if valid_customer_id:
        try:
            existing_sub_id, existing_item_id, existing_sub_status = \
                _existing_eod_subscription(
                    valid_customer_id,
                    stored_web_subscription_id=(
                        u.stripe_subscription_id
                        if u.tier in ("navigator", "analyst", "strategist")
                        else None
                    ),
                )
        except Exception:
            log.exception(
                "create-checkout: existing-subscription lookup failed for user %s",
                u.id,
            )
            return jsonify({
                "error": "subscription_lookup_failed",
                "message": "We could not verify your current subscription. "
                           "Please retry in a moment.",
            }), 503
        if existing_sub_id:
            log.info(
                "create-checkout: user %s already has %s eod subscription %s; "
                "redirecting to billing portal instead of a second checkout",
                u.id, existing_sub_status, existing_sub_id,
            )
            try:
                session_obj = stripe.billing_portal.Session.create(
                    customer=valid_customer_id,
                    return_url=f"https://{public_host}/account",
                    flow_data={
                        "type": "subscription_update_confirm",
                        "subscription_update_confirm": {
                            "subscription": existing_sub_id,
                            "items": [{"id": existing_item_id,
                                       "price": price_id, "quantity": 1}],
                        },
                    },
                )
                return redirect(session_obj.url, code=303)
            except Exception:
                # The update-confirm flow needs the portal configuration to
                # allow switching to this price (and rejects a no-op switch to
                # the current price). Fall back to the plain portal session,
                # same as /account/manage-subscription.
                log.warning("create-checkout: portal update-confirm flow failed for "
                            "user %s; falling back to plain portal", u.id, exc_info=True)
                return manage_subscription()

    # Affiliate referral code: from a direct link (?code=ANNE / ?via=ANNE), a
    # hidden checkout-form field, or the first-party `tw_ref` cookie set on the
    # affiliate's landing page (so attribution survives navigation + the signup
    # round-trip). If it resolves to an active affiliate we PRE-APPLY their
    # Stripe promotion code, so the discount shows already applied AND the sale
    # is attributed. Pre-applying via `discounts` is mutually exclusive with
    # allow_promotion_codes.
    discount_spec, affiliate_id, affiliate_code = _resolve_affiliate_promo(
        request.values.get("code") or request.values.get("via")
        or request.cookies.get("tw_ref"), period)

    # Stamp the affiliate onto the subscription metadata: this is the DURABLE
    # attribution carrier - it rides on the Stripe subscription for its whole
    # life, surviving the 12-month discount coupon. The subscription webhook
    # reads it to write the affiliate_referrals row.
    sub_metadata = {
        "tw2_user_id": str(u.id),
        "tw2_tier_target": tier,
        "product_line": "eod",
        "tier": tier,
        "period": period,
    }
    if u.stripe_subscription_id:
        sub_metadata["replaces_subscription_id"] = u.stripe_subscription_id
    if affiliate_id:
        sub_metadata["tw2_affiliate_id"] = affiliate_id
        sub_metadata["tw2_affiliate_code"] = affiliate_code
    # GA4: also on the SUBSCRIPTION metadata (not just the session's) so a
    # future invoice.paid handler can attribute real post-trial revenue to the
    # originating GA4 client - checkout completes at $0 under the 7-day trial,
    # so the session-completed purchase event carries no dollars.
    if ga_client_id:
        sub_metadata["ga_client_id"] = ga_client_id

    try:
        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(u.id),
            subscription_data={
                "trial_period_days": 7,
                "metadata": sub_metadata,
            },
            # Session-level metadata (separate object from subscription_data's
            # metadata above) - this is what the checkout.session.completed
            # webhook event actually carries, which is why ga_client_id + tier
            # are duplicated here rather than relying on the subscription's.
            # No pre-existing top-level session metadata to clobber.
            metadata={
                "ga_client_id": ga_client_id or "",
                "product_line": "eod",
                "tier": tier,
                "period": period,
                "replaces_subscription_id": u.stripe_subscription_id or "",
            },
        )
        if discount_spec:
            kwargs["discounts"] = [discount_spec]
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
            if discount_spec:
                log.warning("checkout: pre-applied affiliate discount %r rejected; "
                            "retrying with manual entry", discount_spec)
                kwargs.pop("discounts", None)
                kwargs["allow_promotion_codes"] = True
                session_obj = stripe.checkout.Session.create(**kwargs)
            else:
                raise

        # GA4 begin_checkout (Measurement Protocol). price_obj is already
        # cache-resident from _price_id_for(tier, period) above - no extra
        # Stripe call - so unit_amount/currency are cheap to include. Wrapped
        # in its own try/except (belt-and-suspenders on top of send_event's
        # internal fail-open): this code sits inside the SAME try/except that
        # wraps the Stripe checkout Session.create call above, so an uncaught
        # exception here would misreport an already-successful checkout as
        # "stripe_error" / 500 to the browser. Must never happen for analytics.
        try:
            begin_checkout_params = {"currency": "usd", "tier": tier}
            price_obj = _price_for(tier, period)
            if price_obj is not None:
                if getattr(price_obj, "currency", None):
                    begin_checkout_params["currency"] = price_obj.currency
                if getattr(price_obj, "unit_amount", None) is not None:
                    begin_checkout_params["value"] = price_obj.unit_amount / 100.0
            send_event(ga_client_id, "begin_checkout", begin_checkout_params, user_id=str(u.id))
        except Exception:
            log.warning("begin_checkout GA4 tracking failed (checkout unaffected)", exc_info=True)

        return redirect(session_obj.url, code=303)
    except Exception:
        # F2.2 - log the full traceback, return generic message
        log.exception("stripe checkout creation failed")
        return jsonify({"error": "stripe_error"}), 500


def _trial_session_subscription_ok(sess_d):
    """A 7-day-trial Checkout session completes with payment_status ==
    'no_payment_required' (nothing is due until the trial ends), so 'paid'
    never arrives on that path. Before accepting one, verify SERVER-SIDE with
    Stripe that the session's subscription really exists and is 'trialing'
    (or already 'active') - the redirect alone proves nothing (the SEC-C1
    unpaid-session reasoning is unchanged)."""
    sub_raw = sess_d.get("subscription")
    sub_id = (sub_raw.get("id") if isinstance(sub_raw, dict)
              else (sub_raw if isinstance(sub_raw, str) else None))
    if not sub_id:
        return False
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception:
        log.exception("stripe_success: Subscription.retrieve failed for %s", sub_id)
        return False
    status = sub.get("status") if isinstance(sub, dict) else getattr(sub, "status", None)
    return status in ("trialing", "active")


@app.route("/stripe/success")
@require_login
def stripe_success():
    """Stripe redirects here after successful checkout. Poll the session,
    update our user row, then send them to /app/.

    Refreshes are idempotent: user writes are assignments and the durable
    MailerLite outbox dedupes on the Checkout Session id. We deliberately do
    not compare a cs_ session id to StripeEvent.stripe_event_id (which stores
    evt_ webhook ids); that old comparison could never match.
    F2.10 - User row read happens with SELECT ... FOR UPDATE so concurrent
    /stripe/success and /webhooks/stripe handlers don't race on tier writes.
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return redirect("/pricing")

    u = get_current_user()

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

    session_metadata = sess_d.get("metadata") or {}
    session_product_line = str(
        session_metadata.get("product_line") or ""
    ).strip().lower()
    if session_product_line and session_product_line != "eod":
        log.warning(
            "stripe_success: refusing non-web session user_id=%s session=%s line=%s",
            expected_user_id, session_id, session_product_line,
        )
        return jsonify({"error": "not_web_checkout"}), 400
    if sess_d.get("status") not in (None, "complete"):
        log.warning(
            "stripe_success: refusing incomplete session user_id=%s session=%s status=%s",
            expected_user_id, session_id, sess_d.get("status"),
        )
        return redirect("/pricing?payment_pending=1")

    # SEC-C1 - never write an upgrade for an unpaid session. Stripe checkout
    # sessions can be retrieved before payment lands (e.g. user closes the tab
    # mid-flow); writing the tier change off an unpaid session would let any
    # user upgrade for free by hitting /stripe/success with their own
    # half-completed session_id. The ONE acceptable non-'paid' state is a
    # 7-day-trial session ('no_payment_required'), and only after the
    # subscription's trialing/active status is verified server-side.
    payment_status = sess_d.get("payment_status")
    is_trial = (payment_status == "no_payment_required"
                and _trial_session_subscription_ok(sess_d))
    if payment_status != "paid" and not is_trial:
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
    price_id = None
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

    # The expanded subscription is normally present. Fail closed and retrieve
    # it explicitly if Stripe returned only an ID, then require a currently
    # live subscription. This prevents replaying an old paid Checkout session
    # after its subscription was canceled.
    if sub_id and (not sub_status or not price_id):
        try:
            sub_obj = stripe.Subscription.retrieve(
                sub_id, expand=["items.data.price"],
            )
            sub_d = (
                sub_obj if isinstance(sub_obj, dict)
                else sub_obj.to_dict()
            )
            sub_status = sub_d.get("status")
            items = (sub_d.get("items") or {}).get("data") or []
            if items:
                price_id = ((items[0] or {}).get("price") or {}).get("id")
                new_tier, ml_period = _tier_period_for_price(price_id)
        except Exception:
            log.exception(
                "stripe_success: live subscription validation failed sub=%s",
                sub_id,
            )
            return jsonify({"error": "subscription_lookup_failed"}), 503

    metadata_tier = str(session_metadata.get("tier") or "").strip().lower()
    if (
        not sub_id
        or sub_status not in {"active", "trialing", "past_due"}
        or new_tier not in {"navigator", "analyst", "strategist"}
        or ml_period not in {"monthly", "yearly"}
        or (metadata_tier and metadata_tier != new_tier)
    ):
        log.warning(
            "stripe_success: refusing unverified web subscription user=%s session=%s "
            "sub=%s status=%s tier=%s period=%s metadata_tier=%s",
            expected_user_id, session_id, sub_id, sub_status, new_tier,
            ml_period, metadata_tier,
        )
        return jsonify({"error": "unverified_web_subscription"}), 409

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
        if db_user is None:
            return jsonify({"error": "user_not_found"}), 404
        if (
            db_user.stripe_subscription_id
            and db_user.stripe_subscription_id != sub_id
        ):
            # Never let a replayed Checkout replace a different subscription.
            # A genuine replacement is provisioned by its signed subscription
            # webhook, which has explicit replacement metadata and ordering
            # checks; this redirect simply avoids racing that source of truth.
            log.warning(
                "stripe_success: differing current subscription user=%s "
                "session_sub=%s current_sub=%s; deferring to webhook",
                db_user.id, sub_id, db_user.stripe_subscription_id,
            )
            return redirect("/app/?upgrade_pending=1")
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
        # Commit the paid-state lifecycle cleanup with the billing mutation.
        ml_payload = {
            "paid_subscription_id": sub_id,
            "level_tier": new_tier,
            "level_period": ml_period,
        }
        enqueue_mailerlite_reconcile(
            s,
            db_user,
            f"stripe-success:{session_id}",
            event_type=EVENT_RECONCILE,
            payload=ml_payload,
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

    return redirect("/app/?welcome=trial" if is_trial else "/app/?upgraded=1")


@app.route("/stripe/cancel")
def stripe_cancel():
    return redirect("/pricing?cancelled=1")


# ============================================================
# Affiliate co-branded landing page: /join/<code> (public, noindex)
# A ready-made page the affiliate sends their audience to: a short TradeWave
# pitch + their specific discount + a Subscribe CTA that sets the tw_ref cookie
# (so the discount applies + the sale is credited to them). Active affiliates
# only; anything else falls through to the homepage.
# ============================================================
@app.route("/join/<code>")
def affiliate_join(code):
    import affiliate_service as afs
    import affiliate_agreement as agr
    from decimal import Decimal
    norm = afs.normalize_code(code)
    if not afs.CODE_RE.match(norm):
        return redirect("/", code=302)
    s = DBSession()
    try:
        from models import Affiliate
        aff = (s.query(Affiliate)
               .filter(Affiliate.code == norm, Affiliate.status == "active")
               .first())
        if not aff:
            return redirect("/", code=302)
        m_disc = afs.effective_discount_pct(aff, "month")
        a_disc = aff.discount_pct
        try:
            two_tier = Decimal(str(m_disc)) != Decimal(str(a_disc))
        except Exception:
            two_tier = m_disc != a_disc
        ctx = dict(
            code=aff.code,
            display_name=(aff.page_display_name or aff.name or "a TradeWave partner").strip(),
            logo_url=(AFFILIATE_LOGO_URLPATH + "/" + aff.page_logo) if aff.page_logo else None,
            photo_url=(AFFILIATE_LOGO_URLPATH + "/" + aff.page_photo) if aff.page_photo else None,
            page_note=(aff.page_note or "").strip() or None,
            page_signoff=(aff.page_signoff or "").strip() or None,
            two_tier=two_tier,
            monthly_discount=agr._fmt_pct(m_disc),
            annual_discount=agr._fmt_pct(a_disc),
            discount=agr._fmt_pct(a_disc),   # single-offer case: monthly == annual
            cta_url="/pricing?code=%s" % aff.code,
        )
    finally:
        s.close()
    resp = make_response(render_template("affiliate_landing.html", **ctx))
    # First-touch attribution cookie (60 days), same key the homepage + checkout use.
    resp.set_cookie("tw_ref", ctx["code"], max_age=60 * 60 * 24 * 60,
                    samesite="Lax", secure=request.is_secure, path="/")
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


# ============================================================
# Affiliate agreement e-signature (public, login-free magic link)
# The <token> identifies the affiliate (itsdangerous-signed); CSRF still
# protects the POST. Signing flips a 'paused' affiliate to 'active'. See
# web/affiliate_agreement.py.
# ============================================================
_SIGN_INVALID_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="robots" content="noindex"><title>Link not valid</title></head>
<body style="font-family:system-ui;max-width:560px;margin:80px auto;padding:0 20px;color:#1f2a44">
<h1 style="font-size:22px">This signing link isn't valid</h1>
<p style="color:#555">It may have expired or been replaced with a newer one.
Please contact <a href="mailto:help@tradewave.ai">help@tradewave.ai</a> for a fresh link.</p>
</body></html>"""


@app.route("/affiliate/sign/<token>", methods=["GET", "POST"])
def affiliate_sign(token):
    from flask import render_template_string
    import affiliate_agreement as agr
    from models import Affiliate, Session as _S

    data = agr.verify_sign_token(token)
    if not data:
        return render_template_string(_SIGN_INVALID_HTML), 410

    s = _S()
    error = None
    try:
        aff = s.query(Affiliate).filter(Affiliate.id == data["aid"]).first()
        if aff is None or int(data["tv"]) != int(aff.agreement_token_version or 0):
            return render_template_string(_SIGN_INVALID_HTML), 410

        already = aff.agreement_signed_at is not None
        if request.method == "POST" and not already:
            if request.form.get("agree") != "yes":
                error = "Please tick the box to confirm you agree before signing."
            else:
                try:
                    agr.record_signature(
                        aff, request.form.get("signed_name"),
                        _client_ip(), request.headers.get("User-Agent"))
                    s.commit()
                    already = True
                    write_audit(actor_label="affiliate",
                                action="affiliate_agreement_signed",
                                details={"code": aff.code,
                                         "name": aff.agreement_signed_name,
                                         "version": aff.agreement_version,
                                         "consent": "electronic-records-accepted",
                                         "ip": aff.agreement_signed_ip})
                    # Signing flipped paused->active: make the promo code
                    # redeemable now (it was deactivated while paused).
                    try:
                        import promo_service as ps
                        ps.set_promo_active(aff, True)
                    except Exception:
                        log.warning("could not reactivate promo for %s after signing", aff.code)
                    agr.email_signed_copy(aff)
                except agr.AlreadySigned:
                    s.rollback()
                    already = True
                except agr.AgreementError as e:
                    s.rollback()
                    error = str(e)

        ex = agr.exhibit(aff)
        ex["name_signed"] = aff.agreement_signed_name or ex["name"]
        signed_at_display = (aff.agreement_signed_at.strftime("%B %d, %Y").replace(" 0", " ")
                             if aff.agreement_signed_at else "")
        return render_template(
            "affiliate_sign.html",
            # Once signed, show the FROZEN snapshot (the exact terms as signed),
            # not a live re-render of the current .md.
            agreement_html=(aff.agreement_snapshot if (already and aff.agreement_snapshot)
                            else agr.agreement_body_html()),
            # Live-rendered Exhibit B for the UNSIGNED view; once signed the frozen
            # snapshot above already contains it, so the template ignores this.
            addendum_html=agr.addendum_html(aff),
            ex=ex, signed=already, error=error,
            signed_at_display=signed_at_display,
            version=aff.agreement_version or agr.AGREEMENT_VERSION,
            action_url=request.path,
            year=datetime.now(timezone.utc).year,
        )
    finally:
        s.close()


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
            row.api_stripe_subscription_id = None
            row.api_stripe_subscription_status = None
            row.api_tier = None
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
        existing = (
            s.query(StripeEvent)
            .filter_by(stripe_event_id=event_id)
            .with_for_update()
            .first()
        )
        if existing and (existing.processed_at or existing.processing_error):
            return jsonify({"received": True, "duplicate": True}), 200

        # F2.7 - event was already normalized to a plain dict above; now
        # additionally scrub Decimal types so the JSONB insert doesn't blow up
        # when Stripe returns numeric fields as Decimal.
        payload_dict = _json_safe(event)
        if existing:
            # A prior attempt inserted the receipt row but failed before the
            # processed marker. Stripe retries must resume it, not short-circuit
            # forever on the bare event id.
            evrow = existing
        else:
            evrow = StripeEvent(
                stripe_event_id=event_id,
                event_type=event_type,
                payload=payload_dict,
            )
            s.add(evrow)
            try:
                s.commit()
            except IntegrityError:
                # Race: a sibling inserted the receipt. Do not ACK blindly. Lock
                # and inspect the winning row so this request can resume it if
                # the winner died after its insert commit.
                s.rollback()
                log.info(
                    "Concurrent Stripe receipt insert for %s; relocking",
                    event_id,
                )
            # Hold the receipt row through the rest of processing. A retry that
            # arrives concurrently waits, then sees the completed marker.
            evrow = (
                s.query(StripeEvent)
                .filter_by(stripe_event_id=event_id)
                .with_for_update()
                .one()
            )
            # A sibling may have processed the row between our insert commit
            # and this relock. Recheck the terminal markers after waiting on
            # the lock so analytics or dunning side effects cannot run twice.
            if evrow.processed_at or evrow.processing_error:
                return jsonify({
                    "received": True,
                    "duplicate": True,
                    "processed_during_relock": True,
                }), 200

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

        # Stripe webhook deliveries are not ordered. Hydrate every created or
        # updated subscription from Stripe before using its status, item price,
        # or metadata. This prevents an older active/plan-change snapshot from
        # re-granting a subscription that is now canceled or reverting a newer
        # Billing Portal plan switch.
        if event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            data_obj = _current_subscription_snapshot(sub_id, customer_id)
            sub_status = data_obj.get("status")
            items = (data_obj.get("items") or {}).get("data") or []
            price_id = None
            if items:
                price_obj = (items[0] or {}).get("price") or {}
                price_id = price_obj.get("id")
            sub_metadata = data_obj.get("metadata") or {}
            if event_type == "customer.subscription.created":
                # Persist durable attribution from the current subscription,
                # rather than from a possibly stale event snapshot.
                _record_affiliate_referral(
                    s, sub_id, customer_id, sub_metadata,
                )

        # Resolve the product line positively. TW2's web/EOD and developer API
        # subscriptions share one Stripe customer. An event that is not proven
        # to be web/EOD must never mutate users.stripe_subscription_*.
        live_statuses = {"active", "trialing", "past_due"}
        terminal_statuses = {"canceled", "unpaid"}
        subscription_events = {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }
        new_tier = None
        new_api_tier = None
        web_event = False
        api_event = False
        unmappable_price = False
        subscription_ignore_reason = None
        ml_target_period = "__skip__"
        current_web_sub_id = db_user.stripe_subscription_id
        current_api_sub_id = db_user.api_stripe_subscription_id
        current_web_match = bool(
            sub_id and current_web_sub_id and sub_id == current_web_sub_id
        )
        current_api_match = bool(
            sub_id and current_api_sub_id and sub_id == current_api_sub_id
        )

        if event_type == "checkout.session.completed":
            checkout_metadata = data_obj.get("metadata") or {}
            checkout_product_line = str(
                checkout_metadata.get("product_line") or ""
            ).strip().lower()
            checkout_target_tier = str(
                checkout_metadata.get("tier") or ""
            ).strip().lower()
            if (
                checkout_target_tier
                in ("navigator", "analyst", "strategist")
                and checkout_product_line in ("", "eod")
            ):
                web_event = True

        elif event_type in subscription_events:
            product_line, mapped_tier, mapped_period = (
                _subscription_product_target(price_id, sub_metadata)
            )
            # created/updated events were hydrated from current Stripe truth
            # above. A delayed created receipt that now resolves as terminal
            # must revoke access just like an updated/deleted receipt.
            terminal_event = sub_status in terminal_statuses
            replacement_id = str(
                (sub_metadata or {}).get("replaces_subscription_id") or ""
            )

            if product_line == "api":
                api_event = True
                allowed_replacement = bool(
                    current_api_sub_id
                    and not current_api_match
                    and _created_subscription_can_replace(
                        event_type,
                        current_api_sub_id,
                        replacement_id,
                        data_obj,
                    )
                )
                if (
                    current_api_sub_id
                    and not current_api_match
                    and not allowed_replacement
                ):
                    subscription_ignore_reason = "stale_api_subscription"
                elif terminal_event and current_api_match:
                    new_api_tier = "__free__"
                elif sub_status in live_statuses:
                    new_api_tier = mapped_tier
                elif terminal_event:
                    # Adopt the identity of any newer live API subscription
                    # before deciding whether this legacy/untracked terminal
                    # event can clear access.
                    live_api = _live_api_subscription_for_customer(
                        customer_id, exclude_id=sub_id,
                    )
                    if live_api:
                        db_user.api_stripe_subscription_id = live_api["id"]
                        db_user.api_stripe_subscription_status = live_api["status"]
                        db_user.api_tier = live_api["tier"]
                        subscription_ignore_reason = "stale_api_subscription"
                    else:
                        new_api_tier = "__free__"
            elif product_line == "eod" or current_web_match:
                web_event = True
                allowed_replacement = bool(
                    current_web_sub_id
                    and not current_web_match
                    and _created_subscription_can_replace(
                        event_type,
                        current_web_sub_id,
                        replacement_id,
                        data_obj,
                    )
                )
                if (
                    current_web_sub_id
                    and not current_web_match
                    and not allowed_replacement
                ):
                    subscription_ignore_reason = "stale_subscription"
                elif terminal_event:
                    new_tier = "explorer"
                    ml_target_period = None
                elif sub_status in live_statuses:
                    if product_line == "eod" and mapped_tier:
                        new_tier = mapped_tier
                        ml_target_period = mapped_period
                    else:
                        # A current legacy subscription may keep its existing
                        # tier/status, but its unknown price is surfaced loudly.
                        unmappable_price = True
            else:
                subscription_ignore_reason = "unclassified_subscription"

        elif event_type in (
            "invoice.payment_failed",
            "invoice.payment_succeeded",
        ):
            # Invoice payloads do not reliably carry product-line price
            # metadata. Only the exact stored web subscription is allowed to
            # update status or trigger web dunning.
            if (
                current_web_match
                and str(db_user.stripe_subscription_status or "").lower()
                in terminal_statuses
            ):
                subscription_ignore_reason = "terminal_subscription_invoice"
            else:
                web_event = current_web_match

        if subscription_ignore_reason:
            evrow.processed_at = datetime.now(timezone.utc)
            s.commit()
            if subscription_ignore_reason == "stale_subscription":
                action = (
                    "stale_subscription_deleted_ignored"
                    if event_type == "customer.subscription.deleted"
                    else "stale_subscription_event_ignored"
                )
            elif subscription_ignore_reason == "unclassified_subscription":
                action = (
                    "unclassified_subscription_deleted_ignored"
                    if event_type == "customer.subscription.deleted"
                    else "unclassified_subscription_event_ignored"
                )
            else:
                action = (
                    f"{subscription_ignore_reason}_deleted_ignored"
                    if event_type == "customer.subscription.deleted"
                    else f"{subscription_ignore_reason}_event_ignored"
                )
            write_audit(
                actor_label=f"stripe_webhook:{event_type}",
                action=action,
                target_user_id=db_user.id,
                details={
                    "stripe_event_id": event_id,
                    "event_subscription_id": sub_id,
                    "current_subscription_id": db_user.stripe_subscription_id,
                    "current_api_subscription_id": (
                        db_user.api_stripe_subscription_id
                    ),
                    "price_present": bool(price_id),
                },
            )
            log.warning(
                "stripe_webhook ignored %s event=%s user=%s sub=%s current_sub=%s",
                subscription_ignore_reason, event_type, db_user.id, sub_id,
                db_user.stripe_subscription_id,
            )
            response = {
                "received": True,
                "ignored_subscription": subscription_ignore_reason,
            }
            if event_type == "customer.subscription.deleted":
                response["ignored_delete"] = subscription_ignore_reason
            return jsonify(response), 200

        old_tier = db_user.tier
        # Only positively classified web/EOD subscription events own the
        # shared stripe_subscription_id. Matching web invoices may update
        # status, but Checkout and every non-web event leave both fields alone.
        if sub_id and web_event and event_type in subscription_events:
            db_user.stripe_subscription_id = sub_id
        if sub_status and web_event and (
            event_type in subscription_events
            or event_type == "invoice.payment_failed"
        ):
            db_user.stripe_subscription_status = sub_status
        if sub_id and api_event and event_type in subscription_events:
            db_user.api_stripe_subscription_id = sub_id
        if sub_status and api_event and event_type in subscription_events:
            db_user.api_stripe_subscription_status = sub_status
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

        # Durable MailerLite routing is part of this transaction. The worker
        # performs and verifies HTTP writes later, then retries failures.
        if (
            event_type == "checkout.session.completed"
            and web_event
            and checkout_target_tier
            in ("navigator", "analyst", "strategist")
        ):
            # checkout.completed can beat subscription.created. Clear any
            # immediate trial trigger now; the positively classified
            # subscription event follows with the full access-group target.
            enqueue_mailerlite_reconcile(
                s,
                db_user,
                f"stripe:{event_id}:clear-paid",
                event_type=EVENT_CLEAR_PAID,
                payload={"paid_subscription_id": sub_id},
            )
        elif (
            web_event
            and event_type in (
                "customer.subscription.created",
                "customer.subscription.updated",
            )
            and sub_status in live_statuses
            and ml_target_period != "__skip__"
        ):
            enqueue_mailerlite_reconcile(
                s,
                db_user,
                f"stripe:{event_id}:reconcile",
                payload={
                    "level_tier": final_tier,
                    "level_period": ml_target_period,
                },
            )
        elif (
            web_event
            and event_type in (
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
            )
            and new_tier == "explorer"
        ):
            enqueue_mailerlite_reconcile(
                s,
                db_user,
                f"stripe:{event_id}:reconcile",
                payload={"level_tier": "explorer"},
            )
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

        # GA4 purchase (Measurement Protocol) - best-effort, post-commit, same
        # region as the Mailerlite syncs above. Fired HERE rather than from
        # /stripe/success: checkout.session.completed is the more reliable
        # "checkout really completed" signal (Stripe-initiated, signature-
        # verified, and this whole handler already dedupes by event_id at the
        # top) - and it does NOT drive any tier write itself (only the
        # customer.subscription.* events above do), so this is purely
        # additive. The session's own top-level metadata (stashed at checkout
        # creation in stripe_create_checkout - a SEPARATE object from
        # subscription_data's metadata) carries ga_client_id + tier.
        # Wrapped in its own try/except (belt-and-suspenders on top of
        # send_event's internal fail-open): this whole function shares one
        # broad outer except that returns 500 on any exception, and a 500
        # here would make Stripe retry the event - a retry that would then
        # short-circuit on the event_id dedup check above WITHOUT re-running
        # anything. Never worth that risk for an analytics call.
        if event_type == "checkout.session.completed":
            try:
                checkout_metadata = data_obj.get("metadata") or {}
                purchase_params = {
                    "currency": data_obj.get("currency") or "usd",
                    "transaction_id": data_obj.get("id"),
                }
                amount_total = data_obj.get("amount_total")
                if amount_total is not None:
                    purchase_params["value"] = amount_total / 100.0
                if checkout_metadata.get("tier"):
                    purchase_params["tier"] = checkout_metadata["tier"]
                send_event(checkout_metadata.get("ga_client_id") or None,
                           "purchase", purchase_params, user_id=str(db_user.id))
            except Exception:
                log.warning("purchase GA4 tracking failed for event %s (webhook unaffected)",
                            event_id, exc_info=True)

        # Dunning (GTM playbook CARD W1.3, retention floor) - best-effort, post-commit,
        # same region/pattern as the GA4/Mailerlite calls above. Stripe Smart Retries
        # (Dashboard-side, FOUNDER-toggled) owns EVERY mid-sequence "your payment failed,
        # please update your card" email - we do not duplicate those. The app owns exactly
        # ONE email: the FINAL pre-cancel "your access pauses" nudge, fired only on the
        # invoice.payment_failed event where Stripe has stopped scheduling further retries
        # (data_obj.next_payment_attempt is None - the standard Stripe signal that this was
        # the last attempt before the subscription's configured final action fires). This
        # keeps the tier UNCHANGED (the webhook's tier-mapping block above intentionally
        # never touches new_tier for invoice.* events, so access stays live through the
        # whole retry sequence) - only the copy warns it is about to end.
        #
        # Reasoner-review catch (2026-07-09): next_payment_attempt is ALSO null on
        # collection_method=send_invoice invoices (there is never a retry schedule to
        # begin with) and on the very FIRST failure of a subscription whose retries are
        # disabled - neither is "retries exhausted", so the bare null check alone would
        # fire the final notice one failure too early in those cases. Require
        # charge_automatically (the only collection method Smart Retries applies to) AND
        # a real subscription invoice, so the gate only ever fires on a genuine
        # exhausted-retry event.
        if (event_type == "invoice.payment_failed" and web_event
                and data_obj.get("collection_method") == "charge_automatically"
                and data_obj.get("subscription")
                and data_obj.get("next_payment_attempt") is None):
            try:
                _fire_dunning_final_notice(db_user, event_id)
            except Exception:
                log.warning("dunning final-notice email failed for event %s (webhook unaffected)",
                            event_id, exc_info=True)

        # On recovery (a successful invoice after a prior past_due), nothing to suppress
        # server-side: the final notice above only ever fires once retries are already
        # exhausted, at which point Stripe's own configured final action (cancel / mark
        # unpaid) is about to run - there is no pending scheduled app email to cancel.

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
    """Mixin: only super_admin role can see Flask-Admin views.

    Also shims a flask-admin 2.1.0 bug: in contrib.sqla update_model/
    create_model/delete_model, `session` is assigned AFTER on_model_change /
    on_model_delete runs, so the library's own documented pattern (raising
    wtforms ValidationError from those hooks) crashes the except-path
    `session.rollback()` with UnboundLocalError -> 500. handle_view_exception
    has already flashed the validation message by then; we finish the intended
    path: rollback on our session and return False so the form re-renders."""

    def _shim_rollback_return_false(self):
        try:
            self.session.rollback()
        except Exception:
            log.exception("admin shim rollback failed")
        return False

    def update_model(self, form, model):
        try:
            return super().update_model(form, model)
        except UnboundLocalError:
            return self._shim_rollback_return_false()

    def create_model(self, form):
        try:
            return super().create_model(form)
        except UnboundLocalError:
            return self._shim_rollback_return_false()

    def delete_model(self, model):
        try:
            return super().delete_model(model)
        except UnboundLocalError:
            return self._shim_rollback_return_false()

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
        # Queue the same durable current-state reconciliation used by signup and
        # Stripe. In particular, a manual paid grant must remove a reverse-trial
        # user from lifecycle email groups without making MailerLite HTTP calls
        # in the admin request. Period isn't known for a manual paid grant, so
        # access-level placement remains unchanged unless an earlier Stripe
        # event recorded a matching monthly/yearly period.
        lifecycle_session = DBSession()
        try:
            user = (
                lifecycle_session.query(User)
                .filter_by(id=model.id)
                .with_for_update()
                .first()
            )
            if user is not None and user.email:
                enqueue_mailerlite_reconcile(
                    lifecycle_session,
                    user,
                    f"admin-user-edit:{user.id}:{time.time_ns()}",
                    payload={"level_tier": user.tier or "explorer"},
                )
                lifecycle_session.commit()
        except Exception as e:
            lifecycle_session.rollback()
            log.warning(
                "admin after_model_change MailerLite enqueue failed for %s: %s",
                getattr(model, "email", "?"), e,
            )
        finally:
            lifecycle_session.close()

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
                # Cancel both independent product-line subscriptions before
                # removing the identity. Never orphan a billable API
                # subscription just because the web subscription is absent.
                cancel_failed = False
                subscription_ids = {
                    subscription_id
                    for subscription_id in (
                        u.stripe_subscription_id,
                        u.api_stripe_subscription_id,
                    )
                    if subscription_id
                }
                for subscription_id in subscription_ids:
                    try:
                        stripe.Subscription.delete(subscription_id)
                    except Exception as e:
                        errors.append(
                            f"{u.email}: Stripe cancellation failed for "
                            f"{subscription_id}: {e}"
                        )
                        cancel_failed = True
                if cancel_failed:
                    # Retain WorkOS and Postgres identity so an operator can
                    # retry after resolving Stripe; deleting it would lose the
                    # ownership trail for a subscription that may still bill.
                    continue
                # Delete from WorkOS
                if u.workos_user_id:
                    try:
                        workos_client.user_management.delete_user(user_id=u.workos_user_id)
                    except Exception as e:
                        errors.append(f"{u.email}: WorkOS delete failed: {e}")
                        continue
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

class _AffiliateJoinPageRowAction(BaseListRowAction):
    """Per-row icon opening the affiliate's public co-branded landing page
    (/join/<CODE>) in a new tab. Rendered only for ACTIVE affiliates: the
    public route redirects paused/terminated codes to the homepage, so the
    icon would be a dead link for them."""

    def __init__(self):
        super().__init__(title="Open landing page")
        self.icon_class = "fa fa-external-link glyphicon glyphicon-new-window"

    def render(self, context, row_id, row):
        if getattr(row, "status", None) != "active" or not row.code:
            return ""
        # code charset is DB-CHECKed to ^[A-Z0-9_-]{2,64}$ — URL/HTML safe.
        return Markup(
            '<a class="icon" href="/join/%s" target="_blank" rel="noopener" '
            'title="Open landing page /join/%s"><span class="%s"></span></a>'
            % (row.code, row.code, self.icon_class))


class AffiliateAdmin(_AdminAuth, ModelView):
    column_list = ("name", "code", "discount_pct", "commission_pct",
                   "commission_model", "status", "agreement_signed_at",
                   "user", "stripe_coupon_id", "created_at")
    column_searchable_list = ("code", "name", "email", "payout_email")
    column_filters = ("status", "commission_model")
    column_labels = {
        "agreement_signed_at": "Agreement",
        "discount_pct": "Annual discount %",
        "commission_pct": "Annual commission %",
        "discount_pct_monthly": "Monthly discount %",
        "commission_pct_monthly": "Monthly commission %",
        "stripe_coupon_id_monthly": "Monthly coupon",
        "page_display_name": "Page name",
        "page_logo": "Page logo",
        "page_photo": "Page headshot",
        "page_note": "Page note",
        "page_signoff": "Page sign-off",
        "agreement_addendum": "Addendum (Exhibit B)",
        "user": "Portal login",
    }
    # Manual-link fallback for the affiliate dashboard (spec 4.1): the portal
    # auto-links by e-mail on first visit; this field covers mismatches. Ajax
    # so the form never loads the whole users table.
    form_ajax_refs = {"user": {"fields": ["email"], "page_size": 10}}
    column_formatters = {
        "user": lambda v, c, m, n: (m.user.email if m.user is not None else "-"),
        "agreement_signed_at": lambda v, c, m, n: (
            Markup('<a href="%s">✓ Signed %s</a>' % (
                url_for("affiliate_signed.index", id=str(m.id)),
                m.agreement_signed_at.strftime("%Y-%m-%d")))
            if m.agreement_signed_at else "Awaiting signature"),
    }
    # 4th per-row icon (next to view/edit/delete): opens the affiliate's signing
    # link when unsigned, or the stored signed agreement once signed.
    column_extra_row_actions = [
        EndpointLinkRowAction(
            "fa fa-file-text glyphicon glyphicon-file",
            "affiliate_signed.index",
            title="Signing link / signed agreement",
            id_arg="id",
        ),
        EndpointLinkRowAction(
            "fa fa-exchange glyphicon glyphicon-refresh",
            "affiliate_change_terms.index",
            title="Change terms (new coupon + re-sign)",
            id_arg="id",
        ),
        _AffiliateJoinPageRowAction(),
    ]
    can_view_details = True
    column_details_list = ("code", "name", "email", "status",
                           "discount_pct", "commission_pct",
                           "discount_pct_monthly", "commission_pct_monthly",
                           "commission_model",
                           "payout_method", "payout_email", "stripe_coupon_id",
                           "stripe_coupon_id_monthly",
                           "page_display_name", "page_logo", "page_photo",
                           "page_note", "page_signoff",
                           "agreement_addendum",
                           "agreement_version", "agreement_signed_name",
                           "agreement_signed_at", "agreement_signed_ip",
                           "notes", "created_at")
    # Two pairs: Annual (discount_pct/commission_pct = the default + promo backing)
    # and the optional Monthly override. Leave Monthly blank for one flat rate.
    form_columns = ("name", "email", "code",
                    "discount_pct", "commission_pct",
                    "discount_pct_monthly", "commission_pct_monthly",
                    "commission_model", "payout_method", "payout_email",
                    "agreement_addendum",
                    "page_display_name", "page_logo", "page_photo",
                    "page_note", "page_signoff",
                    "user",
                    "status", "notes")
    form_extra_fields = {
        "page_logo": FileUploadField(
            "Page logo (optional)",
            base_path=AFFILIATE_LOGO_DIR,
            allowed_extensions=("png", "jpg", "jpeg", "webp"),
            namegen=_affiliate_logo_namegen,
            description="Optional BRAND logo for the /join/<code> page (shown as a rounded chip). "
                        "PNG/JPG/WEBP. Leave empty to keep the current one.",
        ),
        "page_photo": FileUploadField(
            "Page headshot (optional)",
            base_path=AFFILIATE_LOGO_DIR,
            allowed_extensions=("png", "jpg", "jpeg", "webp"),
            namegen=_affiliate_logo_namegen,
            description="Optional HEADSHOT of the affiliate for the /join/<code> page (shown as a "
                        "circular avatar). A square image looks best. PNG/JPG/WEBP. Leave empty to keep the current one.",
        ),
    }
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
        "discount_pct": {"description": "Annual-plan audience discount, e.g. 20 = 20% off. Also applies to "
                                        "monthly plans unless you set a Monthly discount below, and backs the "
                                        "manually-typed promo code. IMMUTABLE after creation."},
        "commission_pct": {"description": "Annual-plan commission the affiliate keeps, e.g. 30 = 30%. Also applies "
                                          "to monthly plans unless overridden below. Editable later."},
        "discount_pct_monthly": {"description": "OPTIONAL - monthly-plan discount, only if it differs from annual "
                                                "(e.g. 15). Leave blank to match the annual rate. IMMUTABLE after creation."},
        "commission_pct_monthly": {"description": "OPTIONAL - monthly-plan commission, only if it differs from annual "
                                                  "(e.g. 35). Leave blank to match the annual rate. Editable later."},
        "page_display_name": {"description": "OPTIONAL - the name shown on their co-branded landing page "
                                             "(tradewave.ai/join/<code>): their personal OR business name. "
                                             "Leave blank to use the affiliate's name."},
        "page_note": {"description": "OPTIONAL - a short personal note (max 280 chars) from the affiliate to "
                                     "THEIR audience, shown in their voice on tradewave.ai/join/<code>. PLAIN TEXT, "
                                     "public - you (operator) read + approve it before saving. Educational only: "
                                     "NO performance promises, guarantees, return/price/win-rate claims, or links."},
        "page_signoff": {"description": "OPTIONAL - the attribution under the note, e.g. 'Sarah, your options coach' "
                                        "(max 60 chars). The affiliate's OWN name/title only. Blank falls back to the Page name."},
        "agreement_addendum": {"description": "OPTIONAL per-affiliate rider for THIS affiliate only, appended to their "
                                              "agreement as 'Exhibit B - Additional Terms'. The standard Sections 1-15 stay "
                                              "identical for everyone. Markdown allowed (## headings, **bold**, lists, tables). "
                                              "For an UNSIGNED affiliate it appears on their signing page and is frozen into "
                                              "their signed copy when they sign. For an ALREADY-SIGNED affiliate, editing this "
                                              "does NOT change their binding signed copy - use 'Change terms' to require a "
                                              "re-sign so the new Exhibit B takes legal effect. Max 20,000 chars."},
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
        import affiliate_agreement as agr

        # normalize + validate the code
        model.code = afs.normalize_code(model.code)
        try:
            afs.validate_code(model.code)
        except afs.AffiliateError as e:
            raise ValidationError(str(e))

        if not model.commission_model:
            model.commission_model = "recurring"
        if not model.status:
            model.status = "paused"

        # Landing-page note / sign-off: public, affiliate-authored PLAIN TEXT.
        # Strip; treat blank/whitespace as NULL; reject markup + links (defense in
        # depth on top of Jinja autoescape); cap length (DB CHECK backstops it).
        for field, cap in (("page_note", 280), ("page_signoff", 60)):
            val = getattr(model, field, None)
            if val is None:
                continue
            val = " ".join(val.split())  # collapse whitespace/newlines
            if not val:
                setattr(model, field, None)
                continue
            if len(val) > cap:
                raise ValidationError("%s must be %d characters or fewer." % (field, cap))
            low = val.lower()
            if "<" in val or ">" in val or "http://" in low or "https://" in low or "www." in low:
                raise ValidationError(
                    "%s must be plain text - no HTML tags (< >) or links allowed." % field)
            setattr(model, field, val)

        # Agreement addendum (Exhibit B): operator-authored markdown rider. Strip;
        # blank => NULL. Unlike page_note this is admin-authored legal text rendered
        # into the signed document, so markup/links are permitted (markdown). Length
        # is capped (DB CHECK backstops). Warn - don't block - if it changes after the
        # affiliate already signed: the FROZEN snapshot is binding and is unaffected;
        # a 'Change terms' re-sign is needed for the new Exhibit B to take effect.
        addv = getattr(model, "agreement_addendum", None)
        if addv is not None:
            addv = addv.strip()
            if not addv:
                model.agreement_addendum = None
            elif len(addv) > 20000:
                raise ValidationError("Addendum (Exhibit B) must be 20,000 characters or fewer.")
            else:
                model.agreement_addendum = addv
        if not is_created:
            from flask import flash
            addh = sa_inspect(model).attrs.agreement_addendum.history
            if addh.has_changes() and getattr(model, "agreement_signed_at", None):
                flash("Note: %s has already signed. The addendum is saved but does NOT "
                      "change their binding signed agreement - use 'Change terms' to "
                      "require a re-sign so the new Exhibit B takes effect." % model.code,
                      "warning")

        # Activation gate (active <=> signed), enforced on EDITS - but only on
        # the TRANSITION into 'active' (2026-07-07 fix: a legacy row that is
        # already active-without-signature must stay editable; the old check
        # blocked even a name edit). Creation forces 'paused' below regardless;
        # the signing route flips paused->active programmatically once signed.
        if (not is_created and model.status == "active"
                and not getattr(model, "agreement_signed_at", None)):
            _sh = sa_inspect(model).attrs.status.history
            _old_status = _sh.deleted[0] if _sh.deleted else model.status
            if _old_status != "active":
                raise ValidationError(
                    "Can't set an affiliate to 'active' before they've signed the "
                    "agreement. Send them the signing link - status flips to active "
                    "automatically on signing.")
            from flask import flash as _flash
            _flash("Heads-up: %s is active but has no signed agreement on record "
                   "(legacy row). Consider sending the signing link." % model.code,
                   "warning")

        # Terminating an affiliate invalidates their signing magic link (bump the
        # token version so any link already issued now 410s) - a stale link must
        # not let a terminated partner execute a binding signature.
        if not is_created:
            sh = sa_inspect(model).attrs.status.history
            if (model.status == "terminated" and sh.has_changes() and sh.deleted
                    and sh.deleted[0] != "terminated"):
                model.agreement_token_version = (model.agreement_token_version or 0) + 1

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
            # Interval-split: mint an override coupon for any interval whose
            # discount differs from the default (applied by id at checkout; the
            # flat promo above still backs manual entry at the default rate).
            try:
                afs.provision_interval_overrides(model)
            except afs.AffiliateError as e:
                raise ValidationError(str(e))
            # Gate: created paused (awaiting signature). The code stays inert
            # (_resolve_affiliate_promo requires status=='active') until the
            # affiliate signs the agreement, which flips them to 'active'.
            model.status = "paused"
            model.agreement_version = agr.AGREEMENT_VERSION
            model.agreement_token_version = 0
            write_audit(actor_label="admin", action="affiliate_created",
                        details={"code": model.code, "coupon": coupon_id,
                                 "discount_pct": str(model.discount_pct),
                                 "commission_pct": str(model.commission_pct)})
        else:
            # code + every discount % are immutable once their Stripe coupon
            # exists (Stripe coupons can't be edited). Commission %s stay editable.
            st = sa_inspect(model)
            for field in ("code", "discount_pct", "discount_pct_monthly"):
                hist = getattr(st.attrs, field).history
                if hist.has_changes() and hist.deleted:
                    raise ValidationError(
                        f"{field} can't be changed after the Stripe coupon is created. "
                        f"Use 'Change terms' (new coupon + re-sign), or terminate and "
                        f"create a new affiliate.")

    def after_model_change(self, form, model, is_created):
        # Keep the Stripe promotion code's redeemability in lockstep with status:
        # redeemable ONLY while active (i.e. signed). paused/terminated ->
        # deactivate the promo code (existing referred customers keep their
        # discount; only NEW redemptions stop - the coupon is never deleted).
        # This also gates a freshly-created (paused) affiliate's code until they
        # sign; the signing route reactivates it.
        import promo_service as ps
        try:
            ps.set_promo_active(model, model.status == "active")
        except Exception as e:
            flash("Saved, but syncing the Stripe promo code state failed: %s" % e, "warning")
        # Copy-link default: surface the signing link right after creation so
        # the operator can paste it into their welcome note to the affiliate.
        if is_created:
            import affiliate_agreement as agr
            flash('Affiliate "%s" created and PAUSED until signed. Copy this '
                  "signing link and send it to them: %s"
                  % (model.code, agr.signing_url(model)), "success")

    @action("show_signing_link", "Show signing link",
            "Show the agreement signing link for the selected affiliate(s)?")
    def action_show_signing_link(self, ids):
        import affiliate_agreement as agr
        for a in self.session.query(self.model).filter(self.model.id.in_(ids)).all():
            state = ("already signed %s" % a.agreement_signed_at.strftime("%Y-%m-%d")
                     if a.agreement_signed_at else "awaiting signature")
            flash("%s (%s): %s" % (a.code, state, agr.signing_url(a)), "info")

    @action("regenerate_signing_link", "Regenerate signing link (invalidate old)",
            "Regenerate the signing link for the selected affiliate(s)? Any link "
            "you already sent will stop working.")
    def action_regenerate_signing_link(self, ids):
        import affiliate_agreement as agr
        affs = self.session.query(self.model).filter(self.model.id.in_(ids)).all()
        for a in affs:
            a.agreement_token_version = (a.agreement_token_version or 0) + 1
        self.session.commit()
        for a in affs:
            flash("%s: new signing link %s" % (a.code, agr.signing_url(a)), "info")

    @action("email_signing_link", "Email signing link to affiliate",
            "Email the agreement signing link to the selected affiliate(s)?")
    def action_email_signing_link(self, ids):
        import affiliate_agreement as agr
        skipped = 0
        for a in self.session.query(self.model).filter(self.model.id.in_(ids)).all():
            if a.agreement_signed_at is not None or not a.email:
                skipped += 1
                continue
            if agr.email_signing_link(a):
                flash("Signing link emailed to %s (%s)." % (a.email, a.code), "success")
            else:
                flash("Could not email %s (%s) - copy the link and send it manually."
                      % (a.code, a.email), "warning")
        if skipped:
            flash("%d affiliate(s) skipped (already signed or no email on file)."
                  % skipped, "info")

    def get_list_row_actions(self):
        # Keep Delete as the LAST row icon, after our custom signing-link /
        # signed-agreement icon. Flask-Admin appends column_extra_row_actions
        # after Delete by default; move Delete back to the end.
        actions = super().get_list_row_actions()
        dels = [a for a in actions if isinstance(a, DeleteRowAction)]
        rest = [a for a in actions if not isinstance(a, DeleteRowAction)]
        return rest + dels

    def on_model_delete(self, model):
        # Hard delete is allowed ONLY for affiliates with no customers (no
        # referral/payout history) - for clearing test rows or a mistaken entry
        # before they've gone live. If they have history, block it (the DB FK
        # also RESTRICTs this) and steer to Terminated, which keeps the record.
        # The history check runs BEFORE any Stripe call, so a blocked delete
        # never half-tears-down Stripe.
        from models import AffiliateReferral, AffiliatePayout
        has_customers = (
            self.session.query(AffiliateReferral)
                .filter(AffiliateReferral.affiliate_id == model.id).first() is not None
            or self.session.query(AffiliatePayout)
                .filter(AffiliatePayout.affiliate_id == model.id).first() is not None)
        if has_customers:
            raise Exception(
                "%s has referred customers / payout history - delete is blocked to "
                "preserve records. Set status to 'Terminated' instead (it disables "
                "their code and keeps the record)." % model.code)
        # No customers: deactivate the promo + delete the coupon so we never leave
        # a live, unattributable discount code behind in Stripe.
        import affiliate_service as afs
        try:
            afs.teardown_stripe_objects(model)
        except Exception as e:
            flash("Removed %s, but Stripe cleanup had an issue (%s) - check the "
                  "coupon/promo in the Stripe dashboard." % (model.code, e), "warning")


class AffiliatePayoutAdmin(_AdminAuth, ModelView):
    # Rows are created by the compute step, not by hand. You edit only the
    # amount (e.g. to net a refund), the status, the paid date, and the txn id.
    can_create = False
    can_delete = False
    can_edit = True
    column_list = ("affiliate", "period_start", "period_end", "currency",
                   "gross_revenue", "commission_amount", "status", "locked",
                   "paid_at", "external_ref")
    column_default_sort = ("period_start", True)
    column_filters = ("status", "currency", "period_start", "locked")
    form_columns = ("commission_amount", "status", "paid_at", "external_ref")
    form_choices = {"status": [("pending", "Pending"), ("paid", "Paid"),
                               ("void", "Void")]}
    can_view_details = True
    column_details_list = ("affiliate", "period_start", "period_end", "currency",
                           "gross_revenue", "commission_amount", "status", "locked",
                           "computed_at", "paid_at", "external_ref", "detail")
    page_size = 100

    def on_model_change(self, form, model, is_created):
        from sqlalchemy import inspect as sa_inspect
        # auto-stamp paid_at when flipped to paid without an explicit date
        if model.status == "paid" and not model.paid_at:
            from datetime import datetime, timezone
            model.paid_at = datetime.now(timezone.utc)
        # Lock a hand-edited commission so a later compute/upsert re-run can't
        # clobber the adjustment (e.g. a netted refund); upsert_month refreshes
        # only pending rows that are NOT locked.
        if sa_inspect(model).attrs.commission_amount.history.has_changes() \
                and sa_inspect(model).attrs.commission_amount.history.deleted:
            model.locked = True


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
 <tr><th>Code</th><th>Affiliate</th><th>Cur</th><th class="num">Revenue</th><th class="num">Commission owed</th><th>Via</th><th>Pay to</th></tr>
 {% for r in preview %}
 <tr><td><b>{{ r.code }}</b></td><td>{{ r.name }}</td><td>{{ r.currency|upper }}</td>
     <td class="num">{{ '%.2f'|format(r.gross_revenue) }}</td>
     <td class="num"><b>{{ '%.2f'|format(r.commission_amount) }}</b></td>
     <td>{{ (r.payout_method or '?')|upper }}</td>
     <td>{{ r.payout_email or '(no payout email set)' }}{% if r.notes %} <span style="color:#888;font-size:12px">- {{ r.notes }}</span>{% endif %}</td></tr>
 {% endfor %}
 {% for ccy, amt in totals %}
 <tr><th colspan="4" class="num">Total ({{ ccy|upper }})</th><th class="num">{{ '%.2f'|format(amt) }}</th><th></th><th></th></tr>
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
<p>An in-house affiliate program built on Stripe's own coupons. <b>Each affiliate gets one Stripe coupon + one promo code, created automatically</b> when you add them here - no Stripe dashboard, no Rewardful. Every new affiliate starts <b>paused</b>, and their code stays inert until they <b>e-sign the affiliate agreement</b> (step 2).</p>
<p>Current mode: {% if livemode %}<span class="pill mode-live">LIVE - real money</span>{% else %}<span class="pill mode-test">TEST / sandbox - safe to experiment</span>{% endif %}</p>

<h2>1. Add the affiliate</h2>
<div class="step"><b>Affiliates &rarr; Create.</b> Fill in:
  <ul>
    <li><b>name</b> and <b>email</b> - email is required; the signed agreement copy is emailed there.</li>
    <li><b>code</b> - the promo code they share (A-Z, 0-9, _ or -). <b>Immutable</b> after creation.</li>
    <li><b>Annual discount %</b> (default 20) &amp; <b>Annual commission %</b> (default 30) - the standard rate: what an annual-plan customer saves and what the affiliate keeps. This rate also applies to <b>monthly</b> plans unless you set a Monthly override below. Discount is <b>immutable</b> after creation; commission is editable.</li>
    <li><b>Monthly discount %</b> &amp; <b>Monthly commission %</b> (optional) - <b>only</b> fill these if monthly plans get <b>different</b> terms than annual; leave blank to match the annual rate. See <b>section 1a</b> below.</li>
    <li><b>commission model</b> - Recurring (lifetime), First 12 months, or First payment only (how long they earn).</li>
    <li><b>payout method</b> (PayPal / Wise) + <b>payout email</b>, and optional <b>notes</b>.</li>
  </ul>
  On <b>Save</b> we create their Stripe coupon (annual % off) and a promotion code equal to <code>code</code> - plus a separate <b>monthly coupon</b> if you set a different Monthly discount. The affiliate is created <b>PAUSED and the promo code is inactive</b>. A green banner shows their <b>signing link</b>; copy it for step 2. (The <code>status</code> field is ignored on create - everyone starts paused until signed.)
</div>

<h2>1a. Optional: different terms for monthly vs annual <span style="font-weight:normal">(interval-split)</span></h2>
<div class="step">
  <b>What it is.</b> Normally an affiliate has one discount and one commission. You can instead give them <b>different terms depending on whether the customer buys a MONTHLY or an ANNUAL plan</b> - for example a bigger commission on monthly and a bigger discount on annual. It is per-affiliate and optional.
  <ul>
    <li><b>How to set it.</b> The <b>Annual discount %</b>/<b>Annual commission %</b> are the standard rate. To make monthly different, also fill <b>Monthly discount %</b>/<b>Monthly commission %</b>. Leave the Monthly fields <b>blank</b> for one flat rate (monthly then matches annual).</li>
    <li><b>Worked example - Anne-Marie.</b> Annual <b>20% off / 30% commission</b> + Monthly <b>15% off / 35% commission</b>. Result: a <b>monthly</b> subscriber gets 15% off and Anne-Marie earns 35%; an <b>annual</b> subscriber gets 20% off and she earns 30%.</li>
    <li><b>How it behaves.</b> The right discount is applied automatically when the customer arrives through the affiliate's <b>referral link</b> (<code>/?code=THEIRCODE</code>); a manually typed code gives the annual rate. Each month, commission is computed per invoice at that plan's rate.</li>
    <li><b>What's editable.</b> The <b>commissions</b> (annual + monthly) are editable later; the <b>discounts</b> are <b>immutable</b> (each is tied to a Stripe coupon). To change a split affiliate's monthly discount, <b>terminate &amp; recreate</b> (Change terms only updates the annual coupon for now).</li>
  </ul>
</div>

<h2>2. Get them to sign the agreement</h2>
<div class="step">The code does <b>not</b> work until the affiliate signs. To send the link:
  <ol>
    <li>Click the <b>signing icon</b> on the affiliate's row (the document icon; hover shows "Signing link / signed agreement"). For an unsigned affiliate it opens their link with a <b>Copy link</b> button and a one-click <b>Email link to &lt;their address&gt;</b> button that sends it straight to them. (The green banner right after Save shows the same link, and <b>With selected &rarr; Show signing link</b> / <b>Email signing link to affiliate</b> handle several at once.)</li>
    <li>The affiliate opens it - a <b>magic link</b>, no login required. It shows the agreement plus an <b>Exhibit A</b> with their exact terms (code, referral link, discount, commission, payout).</li>
    <li>They type their full legal name, tick the agree box, and click <b>Sign &amp; Accept</b>.</li>
  </ol>
  On signing, the affiliate flips to <b>active</b>, their promo code is <b>activated</b>, and two emails go out: the signed copy to the affiliate, and a notification to <code>help@tradewave.ai</code>. To read the signed contract any time, click the <b>&check; Signed</b> link in the <b>Agreement</b> column (or the same signing icon on the row, which shows the signed agreement once signed).
</div>
<div class="note"><b>About the link:</b> it <b>expires after 30 days</b>. Need a fresh one? <b>With selected &rarr; Regenerate signing link</b> - but that <b>invalidates</b> any link you already sent. You can't flip an affiliate to <b>active</b> by hand before they've signed; send the link and it happens automatically. To change an already-signed affiliate's terms and have them re-sign, use <b>Change terms</b> (step 4) - not terminate.</div>

<h2>3. What the affiliate shares (both ways credit them)</h2>
<div class="step">
  <b>Their code</b> - the audience types <code>THEIRCODE</code> at checkout to get the discount, and
  <b>a direct link</b> - <code>https://{{ public_host }}/?code=THEIRCODE</code>. Clicking it pre-applies the discount at checkout (no typing needed), so it works even when the code is just spoken on a podcast. (<code>?via=THEIRCODE</code> also works.) Both only apply once the affiliate is <b>active</b> (signed).
</div>

<h2>4. What you can and can't change later</h2>
<div class="step">
  <b>Editable</b> anytime via <b>Edit</b>: the <b>Annual</b> and <b>Monthly commission %</b>, payout method/email, and notes. <b>Status</b>: you can pause or terminate at will, but you <b>can't set active by hand</b> without a signature - it flips automatically on signing.<br>
  <b>The discount %s are immutable</b> (each is tied to a Stripe coupon) - neither the <b>Annual</b> nor the <b>Monthly discount %</b> can be edited after creation.<br>
  <b>The <code>code</code> is immutable</b> (it is the Stripe promotion code) - to change the code, terminate and create a new affiliate.<br>
  <b>To change the discount % or renegotiate (e.g. 20/30 &rarr; 15/35):</b> use the <b>Change terms</b> icon on the row - <b>do not terminate</b> (that would cut off their commission on existing customers). It mints a <b>new coupon</b> at the new discount for <b>new</b> referrals, updates commission, and sends the affiliate back to <b>paused</b> to <b>re-sign</b> the new terms (send them the fresh signing link; their code and commission resume on re-signature). <b>Existing customers keep the discount they signed up with</b> - it lives on their Stripe subscription and is never touched. A commission-only change skips the re-sign. <i>(Note: for an <b>interval-split</b> affiliate, Change terms currently reissues only the annual coupon, not the monthly override coupon - to change a split affiliate's monthly discount, terminate and recreate for now.)</i>
</div>

<h2>5. Statuses</h2>
<ol>
  <li><b>paused</b> - the starting state for every new affiliate (<i>awaiting signature</i>), and also what you set to wind someone down. Their code does not apply for new visitors; you still get paid on their existing referrals.</li>
  <li><b>active</b> - signed; earns commission and their link/code pre-applies the discount. Reached only by signing.</li>
  <li><b>terminated</b> - excluded from future payouts, code no longer applies, and their signing link is invalidated. Use this to wind down or end an affiliate with history (the record is kept).</li>
</ol>
<div class="note"><b>Deleting:</b> the trash icon hard-deletes an affiliate <b>only when they have no customers</b> (no referrals or payouts) - handy for clearing a test row or a mistaken entry, and it also removes their Stripe coupon/code. Once they have customers, delete is blocked - <b>terminate</b> instead, which keeps the record.</div>

<h2>6. Paying affiliates each month</h2>
<ol>
  <li><b>Affiliates &rarr; Compute / what I owe.</b> Pick the month and hit <b>Preview</b> - it reads Stripe live and shows revenue + commission owed per affiliate.</li>
  <li>Hit <b>Commit to ledger</b> to save those numbers.</li>
  <li><b>Affiliates &rarr; Payout Ledger.</b> For each row: pay the person by PayPal/Wise, then set <b>status = Paid</b> and paste the transaction id into <b>external_ref</b>.</li>
</ol>
<div class="step"><b>How the payout itself works:</b> TradeWave does not move money - it tells you <i>who</i> to pay and <i>how much</i>. The affiliate gives you their PayPal or Wise email when they apply, and you set <b>payout method</b> + <b>payout email</b> on their record. Each month you send the owed amount yourself in PayPal or Wise, then mark the row paid. The "What I owe" table shows the method + email per affiliate so you know which app to open. Use <b>PayPal</b> for US / simple payees and <b>Wise</b> for international ones (better exchange rates); an email works for both - to pay a Wise recipient straight to their bank, put the bank details in that affiliate's <b>Notes</b>.</div>
<div class="note"><b>Good to know:</b> commission is computed on revenue <i>after</i> the discount and <i>after</i> tax. Re-running a month <b>refreshes still-pending rows</b> with the latest numbers (good for late-settling payments); rows you've marked <b>Paid</b> or <b>Void</b> are frozen. <b>Refunds are not auto-deducted</b> - if a referral refunds, edit that pending row's commission amount down before you mark it paid.</div>

<h2>7. Test vs live</h2>
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


_SIGNED_VIEW_TMPL = """
<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>Signed agreement{% if aff %} - {{ aff.code }}{% endif %}</title>
<style>
 body{font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2a44;background:#f4f5f9;margin:0;}
 .wrap{max-width:820px;margin:0 auto;padding:24px 20px 60px;}
 .bar{background:#fff;border:1px solid #e3e6ee;border-radius:10px;padding:14px 18px;margin-bottom:16px;
      display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;}
 .bar .meta{font-size:13px;color:#555;}
 .bar button, .doc button{font-size:13px;font-weight:600;border:1px solid #4338ca;background:#4f46e5;color:#fff;border-radius:7px;padding:8px 16px;cursor:pointer;box-shadow:0 1px 2px rgba(31,42,68,0.15);}
 .bar button:hover, .doc button:hover{background:#4338ca;}
 .bar button:active, .doc button:active{transform:translateY(1px);}
 .doc{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:32px 36px;}
 .doc table{border-collapse:collapse;margin:10px 0;} .doc th,.doc td{border:1px solid #e3e6ee;padding:6px 10px;text-align:left;}
 .none{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:32px;color:#555;}
 .flash{border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:13px;border:1px solid #e3e6ee;}
 .flash-success{background:#e7f6ec;color:#0a7d28;border-color:#bfe6cb;}
 .flash-warning{background:#fffbe6;color:#8a6d00;border-color:#f0e6b0;}
 .flash-error,.flash-danger{background:#fdeaea;color:#b00020;border-color:#f3c6c6;}
 .flash-info{background:#eef2ff;color:#3a32a8;border-color:#cfd6f5;}
 @media print{body{background:#fff;}.bar{display:none;}.doc{border:0;padding:0;}}
</style></head><body><div class="wrap">
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}{% for cat, m in msgs %}<div class="flash flash-{{ cat }}">{{ m }}</div>{% endfor %}{% endif %}
{% endwith %}
{% if not found %}
  <div class="none">Affiliate not found.</div>
{% elif not signed %}
  <div class="bar">
    <div class="meta"><strong>{{ aff.code }}</strong> &middot; awaiting signature
      &middot; status {{ aff.status }}</div>
  </div>
  <div class="doc">
    <h2 style="margin-top:0;">Signing link</h2>
    <p>Send this private link to the affiliate to review and sign the agreement.
       No login is needed, and it expires 30 days after it was issued.</p>
    {% if signing_url %}
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <input id="signlink" type="text" readonly value="{{ signing_url }}" onclick="this.select()"
             style="flex:1;min-width:280px;padding:8px 10px;border:1px solid #cfd3e0;border-radius:7px;font-size:13px;color:#1f2a44;">
      <button onclick="copySignLink(this)">Copy link</button>
    </div>
    <div style="margin-top:14px;">
      {% if aff.email %}
      <form method="post" action="{{ url_for('affiliate_signed.send') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="id" value="{{ aff.id }}">
        <textarea name="note" rows="3" maxlength="2000"
                  placeholder="Optional personal note shown at the top of the email - e.g. 'Hi {{ (aff.name or '').split(' ')[0] }}, here is the updated agreement for your review.'"
                  style="width:100%;max-width:640px;display:block;padding:8px 10px;border:1px solid #cfd3e0;border-radius:7px;font-size:13px;color:#1f2a44;margin-bottom:8px;"></textarea>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <button type="submit">Email link to {{ aff.email }}</button>
          <a href="{{ signing_url }}" target="_blank" rel="noopener">Open the signing page &rarr;</a>
        </div>
      </form>
      {% else %}
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <span style="color:#b00020;font-size:13px;">No contact email on file - add one on the affiliate record to enable emailing.</span>
        <a href="{{ signing_url }}" target="_blank" rel="noopener">Open the signing page &rarr;</a>
      </div>
      {% endif %}
    </div>
    {% else %}
    <p style="color:#b00020;">Could not generate a signing link (the signing secret is unset).</p>
    {% endif %}
  </div>
  <script>
    function copySignLink(btn){
      var i=document.getElementById('signlink'); if(!i){return;}
      i.select(); i.setSelectionRange(0, 99999);
      var done=function(){var t=btn.textContent; btn.textContent='Copied'; setTimeout(function(){btn.textContent=t;}, 1200);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(i.value).then(done, function(){try{document.execCommand('copy'); done();}catch(e){}});
      }else{try{document.execCommand('copy'); done();}catch(e){}}
    }
  </script>
{% elif not snapshot %}
  <div class="none"><strong>{{ aff.code }}</strong> signed on {{ aff.agreement_signed_at }},
  but no snapshot is on file (signed before snapshots were recorded).</div>
{% else %}
  <div class="bar">
    <div class="meta"><strong>{{ aff.code }}</strong> &middot; signed by
      {{ aff.agreement_signed_name }} on {{ aff.agreement_signed_at }} &middot;
      IP {{ aff.agreement_signed_ip }} &middot; version {{ aff.agreement_version }}</div>
    <button onclick="window.print()">Print / save PDF</button>
  </div>
  <div class="doc">{{ snapshot|safe }}</div>
{% endif %}
</div></body></html>
"""


class AffiliateSignedView(_AdminAuth, BaseView):
    """Super-admin view of the immutable signed-agreement snapshot for one
    affiliate (the exact terms + Exhibit A + signature captured at signing).
    Reached via the per-row link in the Affiliates list, not the nav."""

    def is_visible(self):
        return False  # hidden from the nav; opened via the Affiliates "✓ Signed" link

    @expose("/")
    def index(self):
        from flask import render_template_string, request as _rq
        import uuid as _uuid
        from models import Session as _S, Affiliate as _Aff
        import affiliate_agreement as _agr
        aid = _rq.args.get("id", "")
        try:
            _uuid.UUID(aid)
        except (ValueError, TypeError, AttributeError):
            return render_template_string(_SIGNED_VIEW_TMPL, found=False, aff=None,
                                          signed=False, snapshot="", signing_url="")
        s = _S()
        try:
            aff = s.query(_Aff).filter(_Aff.id == aid).first()
            signed = bool(aff and aff.agreement_signed_at)
            # Unsigned: surface the signing link so the operator can copy/send it
            # (fails closed to "" if the signing secret is unset).
            signing_url = ""
            if aff is not None and not signed:
                try:
                    signing_url = _agr.signing_url(aff)
                except Exception:
                    signing_url = ""
            return render_template_string(
                _SIGNED_VIEW_TMPL, found=aff is not None, aff=aff, signed=signed,
                snapshot=(aff.agreement_snapshot if aff else "") or "",
                signing_url=signing_url)
        finally:
            s.close()

    @expose("/send", methods=["POST"])
    def send(self):
        """Email the signing link to the affiliate (button on the unsigned page /
        the list bulk action both route here in spirit). Sends nothing if already
        signed or no email on file. Best-effort via Resend."""
        from flask import request as _rq, redirect, url_for as _url_for, flash
        import uuid as _uuid
        from models import Session as _S, Affiliate as _Aff
        import affiliate_agreement as _agr
        aid = _rq.form.get("id", "")
        try:
            _uuid.UUID(aid)
        except (ValueError, TypeError, AttributeError):
            flash("Invalid affiliate id.", "error")
            return redirect(_url_for("affiliate_signed.index", id=aid))
        s = _S()
        try:
            aff = s.query(_Aff).filter(_Aff.id == aid).first()
            if aff is None:
                flash("Affiliate not found.", "error")
            elif aff.agreement_signed_at is not None:
                flash("%s has already signed; no link sent." % aff.code, "warning")
            elif not aff.email:
                flash("%s has no contact email on file; can't email the link."
                      % aff.code, "error")
            elif _agr.email_signing_link(
                    aff, note=(_rq.form.get("note") or "").strip()[:2000] or None):
                flash("Signing link emailed to %s." % aff.email, "success")
            else:
                flash("Could not send the email (check RESEND_API_KEY). Copy the "
                      "link and send it manually.", "warning")
            return redirect(_url_for("affiliate_signed.index", id=aid))
        finally:
            s.close()


_CHANGE_TERMS_TMPL = """
<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>Change terms{% if aff %} - {{ aff.code }}{% endif %}</title>
<style>
 body{font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2a44;background:#f4f5f9;margin:0;}
 .wrap{max-width:640px;margin:0 auto;padding:24px 20px 60px;}
 .doc{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:28px 32px;}
 .doc h2{margin-top:0;}
 .none{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:32px;color:#555;}
 .flash{border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:13px;border:1px solid #e3e6ee;}
 .flash-success{background:#e7f6ec;color:#0a7d28;border-color:#bfe6cb;}
 .flash-warning{background:#fffbe6;color:#8a6d00;border-color:#f0e6b0;}
 .flash-error,.flash-danger{background:#fdeaea;color:#b00020;border-color:#f3c6c6;}
 .flash-info{background:#eef2ff;color:#3a32a8;border-color:#cfd6f5;}
 label{display:block;margin:14px 0 0;font-size:13px;font-weight:600;color:#3a3a55;}
 input[type=number]{width:140px;margin-top:4px;padding:8px 10px;border:1px solid #cfd3e0;border-radius:7px;font-size:14px;}
 .note{font-size:13px;color:#555;background:#f7f7fb;border:1px solid #e6e6ef;border-radius:8px;padding:12px 14px;margin:14px 0;}
 button{margin-top:20px;font-size:14px;font-weight:600;border:1px solid #4338ca;background:#4f46e5;color:#fff;border-radius:7px;padding:10px 18px;cursor:pointer;box-shadow:0 1px 2px rgba(31,42,68,.15);}
 button:hover{background:#4338ca;}
 a{color:#5b4bdb;}
</style></head><body><div class="wrap">
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}{% for cat, m in msgs %}<div class="flash flash-{{ cat }}">{{ m }}</div>{% endfor %}{% endif %}
{% endwith %}
{% if not found %}
  <div class="none">Affiliate not found.</div>
{% elif not eligible %}
  <div class="none"><strong>{{ aff.code }}</strong> ({{ aff.status }}) - changing terms applies to a
  signed, <strong>active</strong> affiliate.{% if not aff.agreement_signed_at %} This affiliate hasn't signed yet,
  so just edit them directly, or delete + recreate with the right terms.{% else %} Reactivate them first if you want to change terms.{% endif %}
  <p><a href="{{ url_for('affiliate.index_view') }}">&larr; Back to affiliates</a></p></div>
{% else %}
  <div class="doc">
    <h2>Change terms - {{ aff.code }}</h2>
    <p>Current: <strong>{{ cur_discount }}% discount</strong> / <strong>{{ cur_commission }}% commission</strong>
       &middot; {{ ref_count }} existing referred customer(s).</p>
    <div class="note">This mints a <strong>new coupon</strong> for <strong>new</strong> referrals at the new
      discount and re-points their code to it. <strong>Existing customers keep their current discount</strong>
      (it lives on their Stripe subscription) and you keep owing the affiliate commission on them. The
      affiliate must <strong>re-sign</strong> the new terms, so they go to <em>paused</em> until they do
      (their code and commission resume on re-signature). The new commission rate applies to all of their
      referrals going forward.</div>
    <form method="post" action="{{ url_for('affiliate_change_terms.apply') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="id" value="{{ aff.id }}">
      <label>New discount % (audience)
        <input type="number" step="0.01" min="1" max="100" name="discount_pct" value="{{ cur_discount }}" required></label>
      <label>New commission % (affiliate keeps)
        <input type="number" step="0.01" min="0" max="100" name="commission_pct" value="{{ cur_commission }}" required></label>
      <button type="submit">Apply new terms &amp; require re-sign</button>
    </form>
  </div>
{% endif %}
</div></body></html>
"""


class AffiliateChangeTermsView(_AdminAuth, BaseView):
    """Change an established (signed) affiliate's terms without breaking their
    existing customers: mint a new coupon for new referrals at the new discount,
    update commission, and require the affiliate to re-sign the new Exhibit A.
    Reached via the per-row 'change terms' icon, not the nav."""

    def is_visible(self):
        return False

    @expose("/")
    def index(self):
        from flask import render_template_string, request as _rq
        import uuid as _uuid
        from models import Session as _S, Affiliate as _Aff, AffiliateReferral as _Ref
        import affiliate_agreement as _agr
        aid = _rq.args.get("id", "")
        try:
            _uuid.UUID(aid)
        except (ValueError, TypeError, AttributeError):
            return render_template_string(_CHANGE_TERMS_TMPL, found=False, aff=None, eligible=False)
        s = _S()
        try:
            aff = s.query(_Aff).filter(_Aff.id == aid).first()
            if aff is None:
                return render_template_string(_CHANGE_TERMS_TMPL, found=False, aff=None, eligible=False)
            eligible = aff.agreement_signed_at is not None and aff.status == "active"
            ref_count = s.query(_Ref).filter(_Ref.affiliate_id == aff.id).count()
            return render_template_string(
                _CHANGE_TERMS_TMPL, found=True, aff=aff, eligible=eligible,
                cur_discount=_agr._fmt_pct(aff.discount_pct),
                cur_commission=_agr._fmt_pct(aff.commission_pct), ref_count=ref_count)
        finally:
            s.close()

    @expose("/apply", methods=["POST"])
    def apply(self):
        from flask import request as _rq, redirect, url_for as _url_for, flash
        import uuid as _uuid
        from decimal import Decimal, InvalidOperation
        from models import Session as _S, Affiliate as _Aff
        import affiliate_service as _afs
        import affiliate_agreement as _agr
        import promo_service as _ps
        aid = _rq.form.get("id", "")
        try:
            _uuid.UUID(aid)
        except (ValueError, TypeError, AttributeError):
            flash("Invalid affiliate id.", "error")
            return redirect(_url_for("affiliate.index_view"))
        try:
            new_d = Decimal((_rq.form.get("discount_pct") or "").strip())
            new_c = Decimal((_rq.form.get("commission_pct") or "").strip())
        except (InvalidOperation, ValueError):
            flash("Enter valid numbers for discount and commission.", "error")
            return redirect(_url_for("affiliate_change_terms.index", id=aid))
        if not (0 < new_d <= 100) or not (0 <= new_c <= 100):
            flash("Discount must be 1-100 and commission 0-100.", "error")
            return redirect(_url_for("affiliate_change_terms.index", id=aid))
        s = _S()
        # Stripe state captured so a DB failure AFTER the swap can be compensated.
        new_coupon = new_promo = old_pid = None
        reissued = False
        try:
            # Row lock serialises concurrent / double submits (idempotency).
            aff = s.query(_Aff).filter(_Aff.id == aid).with_for_update().first()
            if aff is None:
                flash("Affiliate not found.", "error")
                return redirect(_url_for("affiliate.index_view"))
            # Only START a change from a live, signed, ACTIVE affiliate. A paused
            # (incl. mid-re-sign) one is ineligible -> blocks re-processing.
            if aff.agreement_signed_at is None or aff.status != "active":
                flash("Terms can only be changed for a signed, ACTIVE affiliate "
                      "(this one is %s). Reactivate them first if needed." % aff.status, "error")
                return redirect(_url_for("affiliate_change_terms.index", id=aid))

            code = aff.code
            discount_changed = Decimal(str(aff.discount_pct)) != new_d
            commission_changed = Decimal(str(aff.commission_pct)) != new_c

            # ---- Commission-only change: light path, no coupon swap / re-sign ----
            # (mirrors the Edit form, which lets commission_pct change in place.)
            if not discount_changed:
                if not commission_changed:
                    flash("No change - discount and commission are unchanged.", "info")
                    return redirect(_url_for("affiliate_change_terms.index", id=aid))
                aff.commission_pct = new_c
                s.commit()
                write_audit(actor_label="admin", action="affiliate_commission_changed",
                            details={"code": code, "commission_pct": str(new_c)})
                flash("Commission for %s updated to %s%% (no re-signature needed; "
                      "applies to the next month you compute)."
                      % (code, _agr._fmt_pct(new_c)), "success")
                return redirect(_url_for("affiliate_change_terms.index", id=aid))

            # ---- Discount change: new coupon + re-sign ----
            old_pid = aff.stripe_promotion_code_id
            # reissue_coupon is the irreversible coupon/promo swap; it rolls back
            # its OWN partial failures (AffiliateError below). After it succeeds,
            # any later failure - the set_promo_active Stripe call OR the DB
            # commit - triggers revert_reissue in the except path to restore the
            # old code, so the affiliate is never left holding a dead one.
            new_coupon, new_promo = _afs.reissue_coupon(aff, new_d)
            reissued = True
            aff.discount_pct = new_d
            aff.stripe_coupon_id = new_coupon
            aff.stripe_promotion_code_id = new_promo
            aff.commission_pct = new_c
            # Require re-signature of the new Exhibit A.
            aff.agreement_signed_name = None
            aff.agreement_signed_at = None
            aff.agreement_signed_ip = None
            aff.agreement_signed_user_agent = None
            aff.agreement_snapshot = None
            aff.agreement_version = _agr.AGREEMENT_VERSION
            aff.agreement_token_version = (aff.agreement_token_version or 0) + 1
            aff.status = "paused"
            # Paused pending re-sign -> the NEW promo must be inert. A failure here
            # raises PromoError -> caught below -> full DB + Stripe rollback (so we
            # never commit a paused row whose code is still redeemable).
            _ps.set_promo_active(aff, False)
            s.commit()
            # Audit AFTER commit (write_audit uses the same scoped_session and
            # closes it; calling it earlier would tear down the live transaction).
            write_audit(actor_label="admin", action="affiliate_terms_changed",
                        details={"code": code, "discount_pct": str(new_d),
                                 "commission_pct": str(new_c)})
            flash('Terms updated for %s to %s%% / %s%%. The affiliate is now PAUSED '
                  "pending re-signature - send them the new signing link below."
                  % (code, _agr._fmt_pct(new_d), _agr._fmt_pct(new_c)), "success")
            return redirect(_url_for("affiliate_signed.index", id=aid))
        except _afs.AffiliateError as e:
            # reissue_coupon failed atomically (its own rollback already ran).
            s.rollback()
            flash("Could not re-issue the discount coupon: %s" % e, "error")
            return redirect(_url_for("affiliate_change_terms.index", id=aid))
        except Exception as e:
            s.rollback()
            if reissued:
                # DB step failed AFTER Stripe was swapped: restore the old code so
                # the affiliate isn't left with a dead one, and remove the new objects.
                try:
                    _afs.revert_reissue(old_pid, new_coupon, new_promo)
                    flash("Failed to change terms (%s); restored the previous "
                          "coupon/code." % e, "error")
                except Exception as e2:
                    flash("Failed to change terms (%s) AND the Stripe rollback hit an "
                          "issue (%s). Reconcile in Stripe: promo %s should be ACTIVE; "
                          "coupon %s / promo %s should be removed."
                          % (e, e2, old_pid, new_coupon, new_promo), "error")
            else:
                flash("Failed to change terms: %s" % e, "error")
            return redirect(_url_for("affiliate_change_terms.index", id=aid))
        finally:
            s.close()


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


@app.route("/internal/featured-history", methods=["GET"])
@csrf.exempt
def internal_featured_history():
    """Private split-topology feed for the gateway on the app box."""
    if not _check_service_key():
        return jsonify({"error": "unauthorized"}), 401
    path = os.environ.get(
        "TW2_FEATURED_HISTORY_FILE", "/home/flask/site/data/featured_history.json"
    )
    try:
        with open(path, encoding="utf-8") as f:
            entries = _json.load(f)
    except FileNotFoundError:
        return jsonify({"error": "daily-pick data unavailable"}), 503
    except (OSError, _json.JSONDecodeError):
        log.exception("internal_featured_history: canonical file unreadable")
        return jsonify({"error": "daily-pick data unavailable"}), 503
    if not isinstance(entries, list):
        return jsonify({"error": "daily-pick data invalid"}), 503
    response = jsonify(entries)
    response.headers["Cache-Control"] = "no-store"
    return response


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
        try:
            if "/home/flask/web" not in sys.path:
                sys.path.insert(0, "/home/flask/web")
            import report_renderer
            report_renderer.rebuild_report_sitemap()
        except Exception:
            log.exception("internal_delete_report: sitemap rebuild failed slug=%s", slug)
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
admin.add_view(AffiliateSignedView(name="Signed agreement", endpoint="affiliate_signed", category="Affiliates"))
admin.add_view(AffiliateChangeTermsView(name="Change terms", endpoint="affiliate_change_terms", category="Affiliates"))

# --- SMN expert module: participation (invites) + take review queue ---
from models import AffiliateSmnProfile, ExpertTake


class AffiliateSmnProfileAdmin(_AdminAuth, ModelView):
    """Operator INVITES an affiliate to the SMN expert program by creating a
    row here (status starts 'invited'). 'active' is reached ONLY through the
    affiliate's own click-accept of the contributor terms in the portal - the
    admin can pause/re-invite but never activate on their behalf."""
    column_list = ("affiliate", "status", "slug", "terms_accepted_at",
                   "scorecard_enabled", "published_at", "updated_at")
    column_filters = ("status",)
    form_columns = ("affiliate", "status", "slug", "scorecard_enabled")
    form_ajax_refs = {"affiliate": {"fields": ["code", "name", "email"], "page_size": 10}}

    def on_model_change(self, form, model, is_created):
        if model.status == "active" and model.terms_accepted_at is None:
            raise wtf_validators.ValidationError(
                "'active' requires the affiliate's own terms acceptance in the "
                "portal - invite them (status 'invited') and let them accept.")
        if (not is_created and model.published_at is not None
                and form.slug.data != model.slug):
            raise wtf_validators.ValidationError(
                "slug is locked once the expert page is published (stable id).")
        super().on_model_change(form, model, is_created)


class ExpertTakeAdmin(_AdminAuth, ModelView):
    """Review queue (spec B4: operator review is MANDATORY before publish).
    Approve/Reject via row actions; the only editable field is review_note
    (write it BEFORE running Reject so the affiliate sees why). All state
    changes go through expert_takes_service - never edit status directly."""
    can_create = False
    can_delete = False
    can_edit = True
    can_view_details = True
    form_columns = ("review_note",)
    column_list = ("updated_at", "affiliate", "article_slug", "title",
                   "status", "published_at")
    column_filters = ("status", "article_slug")
    column_default_sort = ("updated_at", True)

    @action("approve_publish", "Approve + publish",
            "Publish the selected takes to SMN?")
    def action_approve(self, ids):
        import expert_takes_service as _ets
        u = get_current_user()
        done = 0
        for tid in ids:
            take = self.session.get(ExpertTake, tid)
            if take is None:
                continue
            try:
                _ets.approve_and_publish(self.session, take, u)
                done += 1
            except _ets.TakeError as te:
                flash(f"{take.article_slug}: {te}", "error")
        self.session.commit()
        if done:
            flash(f"Published {done} take(s). The SMN box picks them up within a minute.", "success")

    @action("reject", "Reject (uses the row's review note)",
            "Reject the selected takes?")
    def action_reject(self, ids):
        import expert_takes_service as _ets
        u = get_current_user()
        for tid in ids:
            take = self.session.get(ExpertTake, tid)
            if take is None:
                continue
            try:
                _ets.reject_take(self.session, take, u, take.review_note)
            except _ets.TakeError as te:
                flash(f"{take.article_slug}: {te}", "error")
        self.session.commit()
        flash("Rejected.", "success")

    @action("retract", "Retract published take(s)",
            "Retract from SMN? The block disappears on the next sync.")
    def action_retract(self, ids):
        import expert_takes_service as _ets
        u = get_current_user()
        for tid in ids:
            take = self.session.get(ExpertTake, tid)
            if take is None:
                continue
            try:
                _ets.operator_retract(self.session, take, u)
            except _ets.TakeError as te:
                flash(f"{take.article_slug}: {te}", "error")
        self.session.commit()
        flash("Retracted.", "success")


admin.add_view(AffiliateSmnProfileAdmin(
    AffiliateSmnProfile, ModelsSession, name="SMN Experts", category="Affiliates"))
admin.add_view(ExpertTakeAdmin(
    ExpertTake, ModelsSession, name="Expert Takes", category="Affiliates"))

# --- Standalone promo coupons (no affiliate / commission) ---
from models import PromoCoupon
admin.add_view(PromoCouponAdmin(PromoCoupon, ModelsSession, name="Coupons", category=None))

# --- API customer console: self-serve keys / usage / billing / MCP connect (additive) ---
# Gated so the API/MCP product ships DARK on prod: the console registers only when
# TW2_API_CONSOLE_ENABLED is set (dev/staging). Unset (prod default) => /account/api
# is not exposed. The API gateway + MCP server are separate, unprovisioned on prod.
if config.API_CONSOLE_ENABLED:
    import api_portal  # web/api_portal/ blueprint
    from api_portal.blueprint import set_user_loader as _console_set_user_loader
    _console_set_user_loader(get_current_user)  # reuse the web app's WorkOS session resolver
    app.register_blueprint(api_portal.bp, url_prefix="/account/api")
    log.info("API console enabled at /account/api")
else:
    log.info("API console disabled (set TW2_API_CONSOLE_ENABLED to enable /account/api)")


# --- Affiliate dashboard: partner self-serve (always on; access is derived
# from the affiliates.user_id linkage, so non-affiliates just see the
# invite-only page). Spec: docs/AFFILIATE_DASHBOARD_SPEC.md ---
import affiliate_portal  # web/affiliate_portal/ blueprint
from affiliate_portal.blueprint import set_user_loader as _aff_set_user_loader
_aff_set_user_loader(get_current_user)  # share the web app's WorkOS session resolver
app.register_blueprint(affiliate_portal.bp, url_prefix="/account/affiliate")
log.info("Affiliate dashboard enabled at /account/affiliate")


# --- SMN expert-content pull feed (X-Service-Key, same auth as
# /internal/render_report). The SMN box PULLS (outbound-only) on a cron and
# injects/removes Expert Desk blocks - see smn/expert_sync.py. ---
def _parse_since():
    raw = request.args.get("since", "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        abort(400)


@app.route("/internal/expert_takes")
def internal_expert_takes():
    if not _check_service_key():
        abort(403)
    import expert_takes_service as _ets
    since = _parse_since()
    s = DBSession()
    try:
        takes = _ets.takes_since(s, since)
    finally:
        s.close()
    cursor = takes[-1]["updated_at"] if takes else (request.args.get("since") or None)
    return jsonify({"takes": takes, "cursor": cursor})


@app.route("/internal/expert_profiles")
def internal_expert_profiles():
    if not _check_service_key():
        abort(403)
    import expert_takes_service as _ets
    since = _parse_since()
    s = DBSession()
    try:
        profiles = _ets.profiles_since(s, since)
    finally:
        s.close()
    cursor = profiles[-1]["updated_at"] if profiles else (request.args.get("since") or None)
    return jsonify({"profiles": profiles, "cursor": cursor})


# ============================================================
# Boot
# ============================================================
if __name__ == "__main__":
    # Convenience: bare-Flask dev runner
    app.run(host="127.0.0.1", port=5500, debug=False)
