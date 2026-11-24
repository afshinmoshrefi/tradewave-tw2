"""Partner portal: Messages inbox + email preferences (TW-TASK-0039 package B).

Routes on the affiliate_portal blueprint, every query scoped to the SESSION
affiliate (never a request parameter). Logic: web/affiliate_comms.py.

Also registers a blueprint context processor so aff_base.html can show the
unread badge and aff_settings.html the preferences card without the page
routes having to pass anything.
"""
import logging

from flask import abort, flash, g, redirect, render_template, request, url_for

from .blueprint import bp, get_current_affiliate, require_affiliate
from . import routes as _routes

log = logging.getLogger("tw2.affiliate_portal")


def _unread():
    """Unread inbox count for the session affiliate (0 on any problem: the
    badge must never break a page)."""
    cached = getattr(g, "_aff_unread", None)
    if cached is not None:
        return cached
    n = 0
    aff = get_current_affiliate()
    if aff is not None:
        s = _routes._db()
        try:
            import affiliate_comms as comms
            n = comms.unread_count(s, aff.id)
        except Exception:   # noqa: BLE001
            s.rollback()
            n = 0
        finally:
            s.close()
    g._aff_unread = n
    return n


def _prefs():
    aff = get_current_affiliate()
    if aff is None:
        return None
    s = _routes._db()
    try:
        import affiliate_comms as comms
        return {"rows": comms.pref_rows(s, aff.id), "required": comms.REQUIRED_NOTICES}
    except Exception:   # noqa: BLE001
        s.rollback()
        return None
    finally:
        s.close()


@bp.context_processor
def _comms_context():
    return {"aff_unread_count": _unread, "aff_email_prefs": _prefs}


def _when(value):
    return value.strftime("%d %b %Y").lstrip("0") if value else ""


@bp.route("/messages")
@require_affiliate
def messages():
    import affiliate_comms as comms
    aff = get_current_affiliate()
    s = _routes._db()
    try:
        rows = [{"id": n.id, "subject": n.subject, "date": _when(n.created_at),
                 "unread": n.read_at is None,
                 "kind": comms.EVENT_LABEL.get(n.event_type, "Message"),
                 "preview": " ".join((n.body or "").split())[:140]}
                for n in comms.inbox(s, aff.id)]
    finally:
        s.close()
    return render_template("aff_messages.html", **_routes._ctx(
        aff, "messages", rows=rows, unread=sum(1 for r in rows if r["unread"])))


@bp.route("/messages/<int:nid>")
@require_affiliate
def message(nid):
    import affiliate_comms as comms
    from models import AffiliateNotification
    aff = get_current_affiliate()
    s = _routes._db()
    try:
        n = (s.query(AffiliateNotification)
             .filter(AffiliateNotification.id == nid,
                     AffiliateNotification.affiliate_id == aff.id).first())
        if n is None:
            abort(404)
        if n.read_at is None:
            comms.mark_read(s, aff.id, n.id)
            g._aff_unread = None
        msg = {"subject": n.subject, "date": _when(n.created_at),
               "kind": comms.EVENT_LABEL.get(n.event_type, "Message"),
               "paragraphs": [p.split("\n") for p in (n.body or "").split("\n\n") if p.strip()],
               "link_label": n.link_label, "link_url": n.link_url,
               "emailed": n.email_status == "sent", "to_email": n.to_email}
    finally:
        s.close()
    return render_template("aff_message.html", **_routes._ctx(aff, "messages", msg=msg))


@bp.route("/messages/read-all", methods=["POST"])
@require_affiliate
def messages_read_all():
    import affiliate_comms as comms
    aff = get_current_affiliate()
    s = _routes._db()
    try:
        comms.mark_read(s, aff.id)
    finally:
        s.close()
    return redirect(url_for("affiliate_portal.messages"))


@bp.route("/settings/email", methods=["POST"])
@require_affiliate
def settings_email():
    """Save which optional emails the partner wants."""
    import affiliate_comms as comms
    aff = get_current_affiliate()
    on = set(request.form.getlist("on"))
    s = _routes._db()
    try:
        comms.set_disabled_prefs(s, aff.id, [p for p in comms.PREF_IDS if p not in on])
        flash("Saved. Your email preferences are updated.", "success")
    except Exception:   # noqa: BLE001
        s.rollback()
        log.exception("saving email preferences failed")
        flash("We could not save your email preferences. Please try again.", "error")
    finally:
        s.close()
    return redirect(url_for("affiliate_portal.settings") + "#email")
