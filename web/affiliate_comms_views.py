"""Public partner pages (TW-TASK-0039 package B): no login needed.

  /partners/apply                          the partner application form
  /partners/email-preferences/<token>      a partner's email preferences
  /partners/unsubscribe/<token>/<pref>     one-click unsubscribe (RFC 8058 POST)

The <token> is signed (affiliate_comms.make_pref_token) and IS the auth for
the two preference routes, like the agreement signing link. web/app.py
registers the blueprint and CSRF-exempts only the one-click POST.
Logic lives in web/affiliate_comms.py.
"""
import logging
import uuid

from flask import Blueprint, render_template, request

import affiliate_comms as comms
import affiliate_service as afs

log = logging.getLogger("tw2.affiliate_comms")

bp = Blueprint("partner_public", __name__)

_CLIENT_IP = None


def set_client_ip(fn):
    """Parent injects web/app.py:_client_ip (proxy-aware)."""
    global _CLIENT_IP
    _CLIENT_IP = fn


def _ip():
    try:
        return _CLIENT_IP() if _CLIENT_IP is not None else request.remote_addr
    except Exception:   # noqa: BLE001
        return request.remote_addr


def _db():
    import models
    return models.Session()


def _program_facts():
    """Headline numbers for the apply page, from the default terms."""
    t = afs.DEFAULT_TERMS
    s = _db()
    try:
        t = afs.get_terms(s) or t
    except Exception:   # noqa: BLE001  (the page must render without the DB)
        s.rollback()
    finally:
        s.close()
    return {"pool": comms._pct(t.pool_pct), "max_discount": comms._pct(t.max_discount_pct),
            "renewal": comms._pct(t.renewal_pct),
            "last_year": int(t.renewal_years) if t.renewal_years else None}


def _no_store(resp, status=200):
    from flask import make_response
    resp = make_response(resp, status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/partners/apply", methods=["GET", "POST"])
def apply():
    ctx = {"sizes": comms.AUDIENCE_SIZES, "f": {}, "errors": None, "done": False,
           "limited": False, "t": _program_facts()}
    if request.method == "GET":
        return render_template("partner_apply.html", **ctx)
    s = _db()
    try:
        try:
            outcome, _row = comms.submit_application(
                s, request.form, ip=_ip(), user_agent=request.headers.get("User-Agent"))
        except comms.CommsError as e:
            s.rollback()
            ctx.update(errors=e.errors, f=request.form)
            return _no_store(render_template("partner_apply.html", **ctx), 400)
        except Exception:   # noqa: BLE001
            s.rollback()
            log.exception("partner application failed")
            ctx.update(errors=["Something went wrong on our side. Please try again in a "
                               "minute, or email help@tradewave.ai."], f=request.form)
            return _no_store(render_template("partner_apply.html", **ctx), 500)
    finally:
        s.close()
    if outcome == "rate_limited":
        ctx["limited"] = True
        return _no_store(render_template("partner_apply.html", **ctx), 429)
    # 'ok', 'duplicate' and 'honeypot' all look the same from outside
    ctx["done"] = True
    return _no_store(render_template("partner_apply.html", **ctx))


def _affiliate_for(s, token):
    from models import Affiliate
    aid = comms.verify_pref_token(token)
    if not aid:
        return None
    try:
        return s.get(Affiliate, uuid.UUID(aid))
    except (ValueError, TypeError):
        return None


@bp.route("/partners/email-preferences/<token>", methods=["GET", "POST"])
def email_preferences(token):
    s = _db()
    try:
        aff = _affiliate_for(s, token)
        if aff is None:
            return _no_store(render_template("partner_email_prefs.html", invalid=True), 404)
        saved = None
        highlight = None
        if request.method == "POST":
            if request.form.get("all_off") == "yes":
                comms.set_disabled_prefs(s, aff.id, comms.PREF_IDS)
                saved = "Done. All optional partner emails are off. Required notices still reach you."
            else:
                on = set(request.form.getlist("on"))
                comms.set_disabled_prefs(s, aff.id, [p for p in comms.PREF_IDS if p not in on])
                saved = "Saved. Your email preferences are updated."
        else:
            off = request.args.get("off") or ""
            if off in comms.PREF_IDS and off not in comms.disabled_prefs(s, aff.id):
                highlight = off
        resp = render_template(
            "partner_email_prefs.html", invalid=False, code=aff.code, saved=saved,
            highlight=highlight, prefs=comms.pref_rows(s, aff.id),
            required=comms.REQUIRED_NOTICES, action=request.path)
        return _no_store(resp)
    finally:
        s.close()


@bp.route("/partners/unsubscribe/<token>/<pref>", methods=["POST"])
def one_click_unsubscribe(token, pref):
    """Mail clients POST here from the List-Unsubscribe header. The signed
    token is the auth; it turns off exactly one kind of optional email."""
    s = _db()
    try:
        aff = _affiliate_for(s, token)
        if aff is None or pref not in comms.PREF_IDS:
            return "invalid link", 404
        comms.turn_off_pref(s, aff.id, pref)
        return "ok", 200
    finally:
        s.close()
