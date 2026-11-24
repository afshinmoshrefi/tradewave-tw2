"""Blueprint object + shared plumbing for the affiliate dashboard.

Mirrors web/api_portal/blueprint.py: the parent injects its WorkOS session
resolver via set_user_loader() so both consoles share ONE auth path. Every
portal query is scoped by the affiliate row derived from the SESSION user -
never from a request parameter (spec C2).
"""
import sys
import logging
from functools import wraps
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from flask import Blueprint, g, redirect, render_template, request

log = logging.getLogger("tw2.affiliate_portal")

bp = Blueprint(
    "affiliate_portal",
    __name__,
    template_folder="templates",
)

_USER_LOADER = None


def set_user_loader(fn):
    """Parent injects web/app.py:get_current_user (zero-arg -> User|None)."""
    global _USER_LOADER
    _USER_LOADER = fn


_CATALOG_LOADER = None


def set_catalog_loader(fn):
    """Optional: parent injects its Stripe price catalog (zero-arg ->
    {(tier, 'month'|'year'): {"list_price_cents": ...}}; web/app.py:
    _campaign_catalog). Without it the routes look the function up on the
    module that created the Flask app."""
    global _CATALOG_LOADER
    _CATALOG_LOADER = fn


def get_catalog_loader():
    return _CATALOG_LOADER


def get_current_user():
    cached = getattr(g, "_aff_portal_user", "unset")
    if cached != "unset":
        return cached
    user = _USER_LOADER() if _USER_LOADER is not None else None
    g._aff_portal_user = user
    return user


def get_current_affiliate():
    """The linked, non-terminated Affiliate row for the session user, or None.

    First visit AUTO-LINKS by exact case-insensitive email match against
    unlinked rows (spec 4.1): WorkOS verifies the email and affiliate emails
    are operator-entered for hand-picked partners; the admin user_id field is
    the manual fallback for mismatches.
    """
    cached = getattr(g, "_aff_portal_affiliate", "unset")
    if cached != "unset":
        return cached
    user = get_current_user()
    aff = None
    if user is not None:
        import affiliate_service as asvc
        from models import Session as DBSession
        s = DBSession()
        try:
            aff = asvc.find_or_link_affiliate(s, user)
            if aff is not None:
                # Detach a fully-loaded copy so routes can read attrs after close.
                s.refresh(aff)
                s.expunge(aff)
        finally:
            s.close()
    g._aff_portal_affiliate = aff
    return aff


def require_affiliate(view):
    """Logged-out -> /login (account-management page). Logged-in non-affiliate
    -> the clean invite-only page (200, no probing signal about who is one)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            target = request.full_path.rstrip("?")
            return redirect("/login?next=%s" % target)
        if get_current_affiliate() is None:
            return render_template("aff_not_affiliate.html"), 200
        return view(*args, **kwargs)
    return wrapped


from . import routes  # noqa: E402,F401  (attach @bp.route handlers)
