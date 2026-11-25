"""Partner help assistant - portal endpoints (TW-TASK-0039 package A).

JSON endpoints behind the same @require_affiliate gate as every portal page:
only a logged-in user with a linked, non-terminated affiliate row reaches
them, and the affiliate ALWAYS comes from the session, never from the
request. The chat panel itself is templates/aff_help_widget.html, included
by aff_base.html on every partner page. Logic: web/affiliate_help.py.
"""
import logging
from decimal import Decimal
from functools import wraps

from flask import jsonify, request

from .blueprint import bp, get_current_affiliate, get_current_user
from . import dashboard as dash

log = logging.getLogger("tw2.affiliate_portal")


def _json_affiliate(view):
    """require_affiliate for fetch() callers: 401/403 JSON instead of an
    HTML redirect or the invite-only page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return jsonify(ok=False, error="Please sign in again."), 401
        if get_current_affiliate() is None:
            return jsonify(ok=False, error="Not available."), 403
        return view(*args, **kwargs)
    return wrapped


def _money_map(d):
    return {cur: str(Decimal(str(amt)).quantize(Decimal("0.01"))) for cur, amt in (d or {}).items()}


def _tax_form_numbers(s, aff) -> dict:
    """The partner's tax-form state for the assistant: status, form name and
    (when rejected) the owner's reason. No file, no tax detail.
    status: none | received (waiting for review) | accepted | rejected."""
    try:
        import affiliate_ops as ops
        v = ops.tax_form_view(s, aff)
        latest = v.get("latest")
        if latest is not None and latest["status"] in ("received", "rejected"):
            return {"status": latest["status"], "form": latest["form_label"],
                    "reason": latest["reason"] if latest["status"] == "rejected" else None,
                    "form_on_file": v["on_file_label"]}
        if v["on_file"]:
            return {"status": "accepted", "form": v["on_file_label"], "reason": None,
                    "form_on_file": v["on_file_label"]}
        return {"status": "none", "form": None, "reason": None, "form_on_file": None}
    except Exception as e:   # noqa: BLE001
        log.warning("help: tax form state unavailable for %s: %s", aff.code, type(e).__name__)
        return {"status": "unknown", "form": None, "reason": None, "form_on_file": None}


def partner_numbers(aff, s):
    """This partner's own numbers for the assistant: COUNTS AND TOTALS ONLY.
    Built from the same dashboard functions the pages use, so the assistant
    can never say a number the dashboard does not show. No customer row,
    name, email or Stripe id is included."""
    from . import routes
    try:
        d = routes._page_data(aff, s)
        live, terms, catalog = d["live"], d["terms"], d["catalog"]
        pending, paid = dash.payout_totals(s, live)
        custs = dash.customers(s, live, catalog, terms, d["lines"], d["activity"]["status"])
        totals = dash.ledger_totals(d["lines"])
        usd = totals.get("usd") or {}
        held_cents = int(Decimal(str(usd.get("held") or 0)) * 100)
        check = dash.payout_checklist(live, pending, held_cents)
        funnels = {}
        for key in ("30d", "all"):
            f = dash.funnel(s, live, d["lines"], key)
            funnels[f["range_label"]] = {"link_clicks": f["clicks"], "signups": f["signups"],
                                         "paying_customers": f["paid"], "in_trial_now": f["in_trial"]}
        act = d["activity"]
        return {
            "tax_form": _tax_form_numbers(s, live),
            "program_status": live.status,
            "agreement_signed": live.agreement_signed_at is not None,
            "customers": {
                "total": len(custs),
                "paying": sum(1 for c in custs if c["status"] == "paying"),
                "in_trial": sum(1 for c in custs if c["status"] == "trial"),
                "ended": sum(1 for c in custs if c["status"] == "ended"),
            },
            "funnel": funnels,
            "commission_by_currency": {
                cur: {"estimated_this_month_not_final": str(t.get("estimated", 0)),
                      "approved_waiting_for_payout": str(t.get("pending", 0)),
                      "paid": str(t.get("paid", 0)), "held": str(t.get("held", 0))}
                for cur, t in totals.items()},
            "estimate_available": d["est"]["rows"] is not None,
            "payout_ledger": {"pending": _money_map(pending), "paid_lifetime": _money_map(paid)},
            "payout_checklist": [{"item": i["label"], "done": bool(i["ok"]), "note": i["help"]}
                                 for i in check["items"]],
            "payout_ready": bool(check["ready"]),
            "next_statement_date": check["next_date"],
            "payouts_sent_by": check["send_by"],
            "payout_rule": check["send_rule"],
            "activity_rule": {"rule": act.get("rule"), "status": act.get("title"),
                              "detail": act.get("text"), "days_left": act.get("days_left")},
        }
    except Exception as e:   # noqa: BLE001 - the assistant degrades to "numbers unavailable"
        log.warning("help: numbers unavailable for %s: %s", aff.code, type(e).__name__)
        return {"unavailable": True}


@bp.route("/help/messages")
@_json_affiliate
def help_messages():
    """Chat history. ?peek=1 returns only the unread count (the badge on
    every page); a full load marks the team's answers as read."""
    import affiliate_help as ah
    from . import routes
    aff = get_current_affiliate()
    s = routes._db()
    try:
        if request.args.get("peek"):
            return jsonify(ok=True, unread=ah.unread_count(s, aff))
        msgs = ah.history(s, aff)
        ah.mark_read(s, aff)
        return jsonify(ok=True, messages=msgs, unread=0, support_email=ah.support_email())
    finally:
        s.close()


@bp.route("/help/ask", methods=["POST"])
@_json_affiliate
def help_ask():
    import affiliate_help as ah
    from . import routes
    aff = get_current_affiliate()
    question = ((request.get_json(silent=True) or {}).get("question") or "")
    s = routes._db()
    try:
        try:
            ah.check_rate(s, aff)          # before the (Stripe-backed) numbers are built
            live = routes._fresh_affiliate(s)
            msgs = ah.ask(s, live, question, partner_numbers(aff, s))
        except ah.HelpError as e:
            s.rollback()
            return jsonify(ok=False, error=str(e)), 429 if str(e) == ah.MSG_RATE_LIMIT else 400
        return jsonify(ok=True, messages=msgs)
    finally:
        s.close()


@bp.route("/help/ask-team", methods=["POST"])
@_json_affiliate
def help_ask_team():
    """Send a question to a person. Three callers, all in the chat panel:
      {message_id}       'Ask the TradeWave team' under an assistant answer
      {question}         'Send this to the team instead' while the assistant is slow
      {about, question}  'Ask about this' on a Messages entry (about = its id;
                         the entry must belong to the session partner)"""
    import affiliate_help as ah
    from . import routes
    data = request.get_json(silent=True) or {}
    mid, about = data.get("message_id"), data.get("about")
    question = data.get("question")
    s = routes._db()
    try:
        try:
            live = routes._fresh_affiliate(s)
            if str(about or "").isdigit():
                from models import AffiliateNotification as N
                note = (s.query(N).filter(N.id == int(about), N.affiliate_id == live.id).first())
                if note is None:
                    return jsonify(ok=False, error="That message was not found."), 404
                msgs = ah.ask_about(s, live, question, note.subject, note.body)
            elif question is not None:
                msgs = ah.ask_team(s, live, question=str(question))
            else:
                msgs = ah.ask_team(s, live, int(mid) if str(mid or "").isdigit() else None)
        except ah.HelpError as e:
            s.rollback()
            return jsonify(ok=False, error=str(e)), 429 if str(e) == ah.MSG_RATE_LIMIT else 400
        return jsonify(ok=True, messages=msgs)
    finally:
        s.close()
