"""API keys: list, create, rotate, revoke. Enforces the tier's max_keys.

State changes are POST-only. The parent app has a global Flask-WTF CSRFProtect;
our forms carry {{ csrf_token() }} so they validate just like the Flask-Admin
forms do. We do NOT csrf-exempt these (unlike the app's webhooks) because they
are browser-session, same-origin form posts.
"""
import logging
import os

from flask import (
    render_template, request, redirect, url_for, flash,
    session as flask_session, make_response,
)

import config
from apiserver import settings as api_settings
from .blueprint import (
    bp, require_login, get_current_user, api_entitlements_for, api_tier_name_for,
    entitlement_context,
)
from . import keystore

# Public hosts for the quickstart/docs links: explicit env var wins, else derive
# from the box's env (same pattern as routes_mcp._mcp_host). NEVER hardcode the
# prod hosts in templates - the dev/staging consoles must show their own hosts.
_API_HOST_BY_ENV = {
    "dev": "api-dev.trxstat.com",
    "staging": "api-stage.trxstat.com",
    "prod": "api.tradewave.ai",
}
_DEVELOPERS_HOST_BY_ENV = {
    "dev": "developers-dev.trxstat.com",
    "staging": "developers-stage.trxstat.com",
    "prod": "developers.tradewave.ai",
}


def _public_host(env_var, by_env):
    explicit = (os.environ.get(env_var) or "").strip().rstrip("/")
    if explicit:
        return explicit.replace("https://", "").replace("http://", "")
    return by_env.get(getattr(config, "tw2_env", "dev"), by_env["dev"])

log = logging.getLogger("tw2.api_portal.keys")

# Flask-session key used to hand the freshly-created RAW key to the redirected
# page exactly once. Popped on render so a refresh never re-reveals it.
_ONCE_KEY_SESSION = "_api_portal_new_raw_key"
_MAX_KEY_NAME_LEN = 100


def _clean_name(raw_name):
    """Trim + bound the user-supplied key name; default if empty."""
    name = (raw_name or "").strip()
    if not name:
        name = "API key"
    return name[:_MAX_KEY_NAME_LEN]


def _private_no_store(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.route("/keys")
@require_login
def keys_index():
    u = get_current_user()
    ent = api_entitlements_for(u)
    keys = keystore.list_keys(u.id)
    active_count = sum(1 for k in keys if k["revoked_at"] is None)

    # One-time reveal of a just-created raw key (set by create/rotate, popped here).
    new_raw_key = flask_session.pop(_ONCE_KEY_SESSION, None)

    response = make_response(render_template(
        "api_keys.html",
        user=u,
        keys=keys,
        active_count=active_count,
        max_keys=ent["max_keys"],
        at_limit=active_count >= ent["max_keys"],
        tier_name=api_tier_name_for(u),
        tier_label=ent["name"],
        new_raw_key=new_raw_key,
        api_host=_public_host("TW2_API_PUBLIC_HOST", _API_HOST_BY_ENV),
        developers_host=_public_host("TW2_DEVELOPERS_PUBLIC_HOST", _DEVELOPERS_HOST_BY_ENV),
        revocation_delay_seconds=api_settings.API_KEY_CACHE_TTL_SECONDS,
        # C1 (bundling banner, always) + C4 (active reverse-trial note) context -
        # same computation routes_billing.py uses, so the two tabs never disagree.
        ctx=entitlement_context(u),
    ))
    # The page can contain the one-time raw credential.  It must never be
    # retained by a browser cache, shared proxy, or back/forward cache.
    return _private_no_store(response)


@bp.route("/keys/create", methods=["POST"])
@require_login
def keys_create():
    u = get_current_user()
    ent = api_entitlements_for(u)

    name = _clean_name(request.form.get("name"))
    try:
        raw, row = keystore.create_key(
            u.id, name, max_keys=ent["max_keys"],
        )
    except keystore.KeyLimitReached:
        flash(
            "You have reached your plan's limit of %d active key(s). "
            "Revoke one or upgrade your plan to create more." % ent["max_keys"],
            "error",
        )
        return redirect(url_for("api_portal.keys_index"))
    log.info("api key created user=%s key_id=%s prefix=%s", u.id, row["id"], row["prefix"])

    # Hand the raw key to the redirect target for a one-time reveal.
    flask_session[_ONCE_KEY_SESSION] = raw
    flash("API key created. Copy it now - it will not be shown again.", "success")
    return _private_no_store(redirect(url_for("api_portal.keys_index")))


@bp.route("/keys/<key_id>/rotate", methods=["POST"])
@require_login
def keys_rotate(key_id):
    """Rotate in one DB transaction; net active-key count is unchanged."""
    u = get_current_user()
    try:
        raw, row = keystore.rotate_key(u.id, key_id)
    except keystore.KeyNotFound:
        flash("That key was not found on your account.", "error")
        return redirect(url_for("api_portal.keys_index"))
    except keystore.KeyAlreadyRevoked:
        flash("That key is already revoked; create a new one instead.", "error")
        return redirect(url_for("api_portal.keys_index"))
    log.info("api key rotated user=%s old=%s new=%s", u.id, key_id, row["id"])

    flask_session[_ONCE_KEY_SESSION] = raw
    flash("Key rotated. Copy the new key now - the old one is revoked.", "success")
    return _private_no_store(redirect(url_for("api_portal.keys_index")))


@bp.route("/keys/<key_id>/revoke", methods=["POST"])
@require_login
def keys_revoke(key_id):
    u = get_current_user()
    revoked = keystore.revoke_key(u.id, key_id)
    if revoked:
        log.info("api key revoked user=%s key_id=%s", u.id, key_id)
        delay = api_settings.API_KEY_CACHE_TTL_SECONDS
        flash(
            "Key revoked. Cached authorization may take up to %d seconds "
            "to expire." % delay if delay else "Key revoked.",
            "success",
        )
    else:
        flash("That key was not found or is already revoked.", "error")
    return redirect(url_for("api_portal.keys_index"))
