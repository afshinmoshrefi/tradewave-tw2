"""Blueprint object + shared plumbing for the API customer console.

Auth: matches the existing web app's WorkOS sealed-session pattern. The parent
should inject its own `get_current_user` via `bp.set_user_loader(...)` so the
console reuses one auth path. If not injected, we read the same sealed cookie
ourselves (same SESSION_COOKIE name + config.WORKOS_COOKIE_PASSWORD).

Fail-fast: only best-effort telemetry (Redis usage reads) is guarded; auth,
DB, and Stripe errors propagate (Flask turns them into 500s) rather than being
silently swallowed.
"""
import sys
import logging
from functools import wraps

# The console runs under the WEB venv at integration. Make the apiserver
# package + the web tier importable regardless of CWD.
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

from flask import Blueprint, g, redirect, request, abort

import config
# Reuse the apiserver foundation (tier defs, api_keys table access, hash_key).
from apiserver import tiers as api_tiers  # noqa: F401  (re-exported for routes)
from apiserver.auth import hash_key  # noqa: F401  (re-exported for routes)

log = logging.getLogger("tw2.api_portal")

# Same sealed-session cookie the web app issues (web/app.py SESSION_COOKIE).
SESSION_COOKIE = "tw2_session"

bp = Blueprint(
    "api_portal",
    __name__,
    template_folder="templates",
    static_folder="static",
    # Relative to the blueprint's url_prefix (set by the parent to /account/api),
    # so blueprint static lands at /account/api/static and never collides with
    # the web app's /static.
    static_url_path="static",
)


# ------------------------------------------------------------------
# Current-user resolution (injected by parent, or self-contained fallback)
# ------------------------------------------------------------------
_USER_LOADER = None


def set_user_loader(fn):
    """Parent calls this to share its WorkOS session resolver (recommended).

    `fn` must be a zero-arg callable returning the Postgres User row (a
    models.User) for the logged-in request, or None when not authenticated -
    exactly the contract of web/app.py:get_current_user.
    """
    global _USER_LOADER
    _USER_LOADER = fn


# Lazily-built WorkOS client for the fallback path. We only construct it if the
# parent did NOT inject a loader, so a console that shares the app's resolver
# pays no WorkOS-client cost.
_workos_client = None


def _fallback_workos_client():
    global _workos_client
    if _workos_client is None:
        from workos import WorkOSClient
        _workos_client = WorkOSClient(
            api_key=config.WORKOS_API_KEY,
            client_id=config.WORKOS_CLIENT_ID,
            request_timeout=10,
        )
    return _workos_client


def _fallback_current_user():
    """Read the sealed cookie + resolve the Postgres User, mirroring web/app.py.

    This is only used when the parent did not inject a loader. It deliberately
    does NOT attempt the silent session-refresh dance that web/app.py does
    (that needs an after_request hook to persist the new cookie); a stale
    access token here just reads as "not logged in" and bounces to /login,
    which is the safe behavior for a self-serve console.
    """
    sealed = request.cookies.get(SESSION_COOKIE)
    if not sealed:
        return None
    client = _fallback_workos_client()
    try:
        sess = client.user_management.load_sealed_session(
            session_data=sealed,
            cookie_password=config.WORKOS_COOKIE_PASSWORD,
        )
        result = sess.authenticate()
    except Exception as e:
        # Bad/forged/expired cookie - treat as logged out, but log it.
        log.warning("api_portal fallback: load/authenticate sealed session failed: %s", e)
        return None
    if not getattr(result, "authenticated", False):
        return None
    workos_user = result.user
    workos_user_id = workos_user["id"] if isinstance(workos_user, dict) else workos_user.id

    from models import Session as DBSession, User
    s = DBSession()
    try:
        return s.query(User).filter_by(workos_user_id=workos_user_id).first()
    finally:
        s.close()


def get_current_user():
    """Return the logged-in Postgres User row, or None. Caches on flask.g."""
    cached = getattr(g, "_api_portal_user", "unset")
    if cached != "unset":
        return cached
    user = _USER_LOADER() if _USER_LOADER is not None else _fallback_current_user()
    g._api_portal_user = user
    return user


def require_login(view):
    """Console pages require a logged-in user. Bounce to the web app's WorkOS
    LOGIN screen (these are account-management pages, so the visitor already
    has an account - login, not signup), preserving where they were headed.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = get_current_user()
        if u is None:
            target = request.full_path.rstrip("?")
            return redirect("/login?next=%s" % target)
        return view(*args, **kwargs)
    return wrapped


# ------------------------------------------------------------------
# API-tier resolution (reuses apiserver.tiers; never contradicts models.py)
# ------------------------------------------------------------------
def api_tier_name_for(user):
    """The user's effective API tier name (key into API_TIERS).

    Unified-accounts rule lives in apiserver.tiers.api_tier_from_user: an
    explicit `api_tier` wins, else inherit from the web tier
    (explorer->free, navigator->internal navigator, analyst->dev,
    strategist->pro). The active users.api_tier column is null when the user
    has no standalone API subscription, so api_tier_from_user then falls back
    to the bundled web entitlement.
    """
    row = {"tier": getattr(user, "tier", None)}
    explicit = getattr(user, "api_tier", None)
    if explicit:
        row["api_tier"] = explicit
    return api_tiers.api_tier_from_user(row)


def api_entitlements_for(user):
    """Full entitlement dict (markets, ml, rate, max_keys, ...) for the user."""
    return api_tiers.tier_for(api_tier_name_for(user))


# Import the route modules so their @bp.route handlers attach to `bp`.
# (Done last to avoid circular imports - the routes import from this module.)
from . import routes_keys      # noqa: E402,F401
from . import routes_usage     # noqa: E402,F401
from . import routes_billing   # noqa: E402,F401
from . import routes_mcp       # noqa: E402,F401
