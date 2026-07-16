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
# Dependency-free, repo-root module shared with web/app.py + apiserver/auth.py
# (see reverse_trial.py docstring). sys.path already carries /home/flask above.
import reverse_trial  # noqa: F401  (re-exported for routes)

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


# ------------------------------------------------------------------
# §7.3 shared context: explicit/bundled/effective split + C1/C4/C5 copy
# plumbing, used by BOTH routes_keys.py (Keys tab: C1 + C4) and
# routes_billing.py (Billing tab: C1 + C4 + C5 + per-card state). Lives here
# (not duplicated in each route module) so the two tabs can never drift on
# what "effective" or "redundant sub" means - one computation, two renders.
# ------------------------------------------------------------------

# WebTier display label (Title Case, matches copy blocks C1/C4/C5 "{WebTier}").
_WEB_TIER_LABEL = {
    "explorer": "Explorer", "navigator": "Navigator",
    "analyst": "Analyst", "strategist": "Strategist",
}


def _rankable_explicit(user):
    """The user's explicit api_tier IF it is a ranked/sellable name, else None.
    Mirrors apiserver.tiers.api_tier_from_user's own defensive treatment of an
    unrankable explicit value (a service/internal name like 'mcp' leaking in) -
    such a value must never be treated as "holds an explicit API sub" here
    either, for the same reason it must never win the MAX in tiers.py."""
    explicit = getattr(user, "api_tier", None)
    if explicit and explicit in api_tiers.API_TIER_RANK:
        return explicit
    return None


def _scope_summary(tier_name):
    """Human scope summary for a bundled/API tier, e.g. 'Dow, NASDAQ, S&P +
    5 ML/day'. Reads names/limits from config.available_resources +
    apiserver.tiers so numbers are never hand-duplicated (C1's "don't hardcode
    numbers tiers.py already owns")."""
    t = api_tiers.tier_for(tier_name)
    names = []
    for mid in t["markets"]:
        raw = config.available_resources.get(mid, "market %s" % mid)
        # Title-case + drop the noisy "STOCKS"/"ALL" suffixes for a short banner
        # phrase (e.g. "DOW 30 STOCKS" -> "Dow 30", "S&P 500 STOCKS" -> "S&P 500").
        label = raw.title().replace(" Stocks", "").replace(" All", "")
        names.append(label)
    if len(names) > 4:
        market_part = "%d markets" % len(names)
    else:
        market_part = ", ".join(names)
    if t.get("ml_access"):
        ml_part = "unlimited ML/day" if t.get("ml_daily_limit") is None else "%d ML/day" % t["ml_daily_limit"]
    else:
        ml_part = "no ML"
    return "%s, %s" % (market_part, ml_part)


def entitlement_context(user):
    """The full §7.3 explicit/bundled/effective picture for `user`, plus the
    C1/C4/C5 copy-block context. One dict, reused verbatim by both the Keys
    and Billing templates so banner copy can never disagree between tabs.

    Keys:
      explicit          - explicit api_tier name if rankable, else None
      bundled           - WEB_TIER_TO_API[web tier] (always present)
      effective         - api_tiers.api_tier_from_user(...) (MAX by rank)
      effective_source  - "explicit" | "bundled" (which side of the MAX won;
                           ties (equal rank) count as "bundled" - a same-rank
                           explicit sub is redundant, not a distinct source)
      web_tier / web_tier_label
      bundled_label / effective_label - API_TIERS/INTERNAL_TIERS "name" fields
      c1_scope_summary  - scope summary for the BUNDLED tier (C1 always
                           describes what the plan itself grants)
      in_trial          - reverse_trial.in_reverse_trial() AND web tier explorer
                           (C4 gate - computed the same way as the account-hub
                           MCP teaser: web_tier == 'explorer' AND the raw
                           reverse_trial_ends_at is active. Deliberately NOT
                           inferred from "effective != raw tier" - that pattern
                           breaks for a role-bypass user, e.g. an admin whose
                           effective access is elevated by config.ROLE_BYPASSES_
                           TIER rather than by an actual trial, which would
                           incorrectly show the trial note; see web/app.py's
                           _account_mcp_teaser for the same distinction.)
      redundant         - True iff explicit is rankable and its rank <= bundled's
                           rank (R7 - explicit sub adds nothing, advise cancel)
    """
    web_tier = (getattr(user, "tier", None) or "explorer")
    explicit = _rankable_explicit(user)
    bundled = api_tiers.WEB_TIER_TO_API.get(web_tier, api_tiers.DEFAULT_TIER)
    effective = api_tier_name_for(user)
    if explicit is not None and api_tiers.API_TIER_RANK[explicit] > api_tiers.API_TIER_RANK.get(bundled, 0):
        effective_source = "explicit"
    else:
        effective_source = "bundled"
    redundant = explicit is not None and api_tiers.API_TIER_RANK[explicit] <= api_tiers.API_TIER_RANK.get(bundled, 0)
    in_trial = (
        web_tier == "explorer"
        and reverse_trial.in_reverse_trial(getattr(user, "reverse_trial_ends_at", None))
    )
    return {
        "explicit": explicit,
        "bundled": bundled,
        "effective": effective,
        "effective_source": effective_source,
        "web_tier": web_tier,
        "web_tier_label": _WEB_TIER_LABEL.get(web_tier, web_tier.capitalize() if web_tier else web_tier),
        "explicit_label": api_tiers.tier_for(explicit)["name"] if explicit else None,
        "bundled_label": api_tiers.tier_for(bundled)["name"],
        "effective_label": api_tiers.tier_for(effective)["name"],
        "c1_scope_summary": _scope_summary(bundled),
        "in_trial": in_trial,
        "redundant": redundant,
    }


# Import the route modules so their @bp.route handlers attach to `bp`.
# (Done last to avoid circular imports - the routes import from this module.)
from . import routes_keys      # noqa: E402,F401
from . import routes_usage     # noqa: E402,F401
from . import routes_billing   # noqa: E402,F401
from . import routes_mcp       # noqa: E402,F401
