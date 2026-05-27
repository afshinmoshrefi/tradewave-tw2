"""API keys: list, create, rotate, revoke. Enforces the tier's max_keys.

State changes are POST-only. The parent app has a global Flask-WTF CSRFProtect;
our forms carry {{ csrf_token() }} so they validate just like the Flask-Admin
forms do. We do NOT csrf-exempt these (unlike the app's webhooks) because they
are browser-session, same-origin form posts.
"""
import logging

from flask import (
    render_template, request, redirect, url_for, flash,
    session as flask_session,
)

from .blueprint import bp, require_login, get_current_user, api_entitlements_for, api_tier_name_for
from . import keystore

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


@bp.route("/keys")
@require_login
def keys_index():
    u = get_current_user()
    ent = api_entitlements_for(u)
    keys = keystore.list_keys(u.id)
    active_count = sum(1 for k in keys if k["revoked_at"] is None)

    # One-time reveal of a just-created raw key (set by create/rotate, popped here).
    new_raw_key = flask_session.pop(_ONCE_KEY_SESSION, None)

    return render_template(
        "api_keys.html",
        user=u,
        keys=keys,
        active_count=active_count,
        max_keys=ent["max_keys"],
        at_limit=active_count >= ent["max_keys"],
        tier_name=api_tier_name_for(u),
        tier_label=ent["name"],
        new_raw_key=new_raw_key,
    )


@bp.route("/keys/create", methods=["POST"])
@require_login
def keys_create():
    u = get_current_user()
    ent = api_entitlements_for(u)

    # Enforce the tier's max_keys against LIVE keys only.
    if keystore.count_active_keys(u.id) >= ent["max_keys"]:
        flash(
            "You have reached your plan's limit of %d active key(s). "
            "Revoke one or upgrade your plan to create more." % ent["max_keys"],
            "error",
        )
        return redirect(url_for("api_portal.keys_index"))

    name = _clean_name(request.form.get("name"))
    raw, row = keystore.create_key(u.id, name)
    log.info("api key created user=%s key_id=%s prefix=%s", u.id, row["id"], row["prefix"])

    # Hand the raw key to the redirect target for a one-time reveal.
    flask_session[_ONCE_KEY_SESSION] = raw
    flash("API key created. Copy it now - it will not be shown again.", "success")
    return redirect(url_for("api_portal.keys_index"))


@bp.route("/keys/<key_id>/rotate", methods=["POST"])
@require_login
def keys_rotate(key_id):
    """Rotate: mint a NEW key (same name) and revoke the old one atomically
    enough for self-serve (create then revoke). Net key count is unchanged, so
    this is always allowed even at the tier limit.
    """
    u = get_current_user()
    old = keystore.get_key(u.id, key_id)
    if old is None:
        flash("That key was not found on your account.", "error")
        return redirect(url_for("api_portal.keys_index"))
    if old["revoked_at"] is not None:
        flash("That key is already revoked; create a new one instead.", "error")
        return redirect(url_for("api_portal.keys_index"))

    raw, row = keystore.create_key(u.id, old["name"])
    keystore.revoke_key(u.id, key_id)
    log.info("api key rotated user=%s old=%s new=%s", u.id, key_id, row["id"])

    flask_session[_ONCE_KEY_SESSION] = raw
    flash("Key rotated. Copy the new key now - the old one is revoked.", "success")
    return redirect(url_for("api_portal.keys_index"))


@bp.route("/keys/<key_id>/revoke", methods=["POST"])
@require_login
def keys_revoke(key_id):
    u = get_current_user()
    revoked = keystore.revoke_key(u.id, key_id)
    if revoked:
        log.info("api key revoked user=%s key_id=%s", u.id, key_id)
        flash("Key revoked.", "success")
    else:
        flash("That key was not found or is already revoked.", "error")
    return redirect(url_for("api_portal.keys_index"))
