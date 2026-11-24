"""Monthly affiliate operations summary for the owner (TW-TASK-0039 C5).

Runs AFTER month close (the ledger sweep affiliate_report.py commits the
month on the 2nd; this runs on the 3rd) and emails the owner ONE summary:

  - what is owed: payable now vs not payable yet, per currency;
  - things to check: large refunds / chargebacks, held commission, missing
    tax forms (and forms waiting for review), balances carried under the
    minimum, missing payout details, partners close to (or just past) the
    activity deadline;
  - links to the admin screens that act on each of them.

READ-ONLY on the program: it reads the payout ledger and the commission
lines, never calls Stripe, never computes or commits a month, and NEVER marks
anything paid. Its only write is one audit_log row per month sent, which is
what makes the email idempotent (a re-run for the same month sends nothing
unless --force).

The checks are plain rules (no LLM): every number in the email is read from
the ledger.

Cron (web box), 06:30 UTC on the 3rd (installed by ops/install_affiliate_crons.sh):
  30 6 3 * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/web/affiliate_ops_summary.py --email >> /var/log/tradewave/affiliate_ops_summary.log 2>&1

Usage: affiliate_ops_summary.py [--month YYYY-MM] [--email] [--force]
Without --email the summary is printed and nothing is sent or recorded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as _html
import logging
import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config  # noqa: E402

log = logging.getLogger("affiliate_ops_summary")

UTC = dt.timezone.utc
SENT_ACTION = "affiliate_ops_summary_sent"
ADMIN_LINKS = (
    ("bulk", "Bulk payouts (export and mark paid)", "/admin/affiliate_bulk_payouts/"),
    ("ledger", "Payout ledger", "/admin/affiliatepayout/?flt1_status_equals=pending"),
    ("tax", "Tax forms", "/admin/affiliate_tax_forms/"),
    ("held", "Held commission lines", "/admin/affiliatecommissionline/?flt1_state_equals=held"),
    ("compute", "Compute / What I owe", "/admin/affiliate_compute/"),
    ("affiliates", "Affiliates", "/admin/affiliate/"),
)


def prev_month(today: dt.date) -> tuple[int, int]:
    return (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)


def _base() -> str:
    return (getattr(config, "tw2_public_url", None) or "https://tradewave.ai/").rstrip("/")


def _money(amount, currency="usd") -> str:
    amount = Decimal(str(amount or 0))
    sign = "-" if amount < 0 else ""
    text = "{:,.2f}".format(abs(amount))
    c = (currency or "usd").lower()
    return "%s$%s" % (sign, text) if c == "usd" else "%s%s %s" % (sign, text, c.upper())


def _d(v) -> str:
    return v.strftime("%d %b %Y").lstrip("0") if v else ""


def build_summary(session, year: int, month: int, now=None) -> dict:
    """Everything the email says, as plain data (see module docstring).
    Read-only."""
    from sqlalchemy import func
    import affiliate_admin as afa
    import affiliate_ops as ops
    import affiliate_ops_models as om
    import affiliate_service as afs
    from models import Affiliate, AffiliateCommissionLine as L, AffiliatePayout, AffiliateReferral

    now = afs._utc(now) or dt.datetime.now(UTC)
    period = dt.date(year, month, 1)
    minimum = afs.payout_minimum()

    rows = ops.pending_payout_rows(session)
    payable = [r for r in rows if r["payable"]]
    blocked = [r for r in rows if not r["payable"]]

    def totals(items):
        out = {}
        for r in items:
            out[r["currency"]] = out.get(r["currency"], Decimal("0")) + r["amount"]
        return sorted(out.items())

    month_rows = (session.query(AffiliatePayout).filter(AffiliatePayout.period_start == period).all())
    month_lines = (session.query(func.count(L.id)).filter(L.period_month == period).scalar() or 0)
    month_commission = {}
    for p in month_rows:
        if p.status != "void":
            month_commission[p.currency] = (month_commission.get(p.currency, Decimal("0"))
                                            + Decimal(str(p.commission_amount or 0)))

    # --- anomalies ---------------------------------------------------------
    big = int(getattr(config, "AFFILIATE_OPS_LARGE_REFUND_CENTS", 20000))
    codes = dict(session.query(Affiliate.id, Affiliate.code).all())
    refund_lines = (session.query(L).filter(L.period_month == period,
                                            L.kind.in_(("refund", "dispute"))).all())
    large_refunds = [{"code": codes.get(ln.affiliate_id, "?"), "kind": ln.kind,
                      "customer_amount": Decimal(abs(ln.net_paid_cents or 0)) / 100,
                      "commission": Decimal(str(ln.amount or 0)).quantize(Decimal("0.01")),
                      "currency": ln.currency, "source": ln.source_id, "date": _d(ln.event_at)}
                     for ln in refund_lines
                     if abs(ln.net_paid_cents or 0) >= big or ln.kind == "dispute"]
    large_refunds.sort(key=lambda r: r["customer_amount"], reverse=True)
    per_partner = {}
    for ln in refund_lines:
        per_partner[ln.affiliate_id] = per_partner.get(ln.affiliate_id, 0) + 1
    repeat_refunds = sorted((codes.get(a, "?"), n) for a, n in per_partner.items() if n >= 3)

    held = afa.held_summary(session)

    no_tax = [r for r in blocked if r["short_reason"] == "No tax form on file"]
    forms_waiting = (session.query(func.count(om.AffiliateTaxForm.id))
                     .filter(om.AffiliateTaxForm.status == "received").scalar() or 0)
    held_no_tax = sorted({h["code"] for h in held} & {
        a.code for a in session.query(Affiliate).filter(Affiliate.tax_form_received_at.is_(None)).all()})

    carries = [r for r in blocked if r["short_reason"] in ("Below minimum, carried", "Negative, carried")]
    no_details = [r for r in blocked if r["short_reason"] in ("No payout method", "No payout email")]

    warn_days = int(getattr(config, "AFFILIATE_OPS_ACTIVITY_WARN_DAYS", 30))
    activity = []
    with_customers = {r[0] for r in session.query(AffiliateReferral.affiliate_id)
                      .filter(AffiliateReferral.first_paid_at.isnot(None)).distinct().all()}
    for aff in (session.query(Affiliate).filter(Affiliate.status.in_(("active", "paused")))
                .order_by(Affiliate.code).all()):
        if aff.id not in with_customers:
            continue
        st = afs.activity_status(aff, now, session=session, terms=afs.terms_for(session, aff))
        if st["active_until"] is not None:
            left = (st["active_until"] - now.date()).days
            if left <= warn_days:
                activity.append({"code": aff.code, "name": aff.name, "state": "closing",
                                 "date": _d(st["active_until"]), "days": left})
        elif st["lapsed_since"] is not None and (now.date() - st["lapsed_since"]).days <= 31:
            activity.append({"code": aff.code, "name": aff.name, "state": "lapsed",
                             "date": _d(st["lapsed_since"]), "days": 0})

    flags = (len(large_refunds) + len(repeat_refunds) + len(held) + len(no_tax) + len(carries)
             + len(no_details) + len(activity) + (1 if forms_waiting else 0))
    return {
        "period": period, "period_label": period.strftime("%B %Y"), "generated_at": now,
        "committed": bool(month_rows) or bool(month_lines),
        "month_commission": sorted(month_commission.items()),
        "payable": payable, "blocked": blocked,
        "payable_totals": totals(payable), "blocked_totals": totals(blocked),
        "minimum": minimum,
        "large_refunds": large_refunds, "repeat_refunds": repeat_refunds, "large_refund_floor": Decimal(big) / 100,
        "held": held, "no_tax": no_tax, "forms_waiting": int(forms_waiting), "held_no_tax": held_no_tax,
        "carries": carries, "no_details": no_details, "activity": activity, "warn_days": warn_days,
        "flags": flags,
        "links": [(key, label, _base() + path) for key, label, path in ADMIN_LINKS],
    }


def subject_for(summary) -> str:
    owed = ", ".join(_money(a, c) for c, a in summary["payable_totals"]) or "$0.00"
    n = len({r["code"] for r in summary["payable"]})
    k = summary["flags"]
    return "Affiliate operations %s - %s payable to %d partner%s, %d thing%s to check" % (
        summary["period"].strftime("%b %Y"), owed, n, "" if n == 1 else "s", k, "" if k == 1 else "s")


def sections(summary) -> list:
    """[(heading, [line, ...], link key or None)] - one source for the text
    and the HTML email."""
    s = summary
    out = []
    lines = []
    if not s["committed"]:
        lines.append("%s is not in the ledger yet (no payout rows or commission lines for the month). "
                     "Open Compute / What I owe, preview the month and commit it." % s["period_label"])
    elif s["month_commission"]:
        lines.append("Commission booked for %s: %s." % (
            s["period_label"], ", ".join(_money(a, c) for c, a in s["month_commission"])))
    if s["payable"]:
        lines.append("Payable now: %s across %d row%s." % (
            ", ".join(_money(a, c) for c, a in s["payable_totals"]), len(s["payable"]),
            "" if len(s["payable"]) == 1 else "s"))
        for r in s["payable"]:
            lines.append("  %s %s - %s - %s via %s (%s)" % (
                r["code"], r["name"], r["period"], _money(r["amount"], r["currency"]),
                (r["method"] or "?").capitalize(), r["ref"]))
    else:
        lines.append("Nothing is payable right now.")
    if s["blocked"]:
        lines.append("Not payable yet: %s across %d row%s (reasons below)." % (
            ", ".join(_money(a, c) for c, a in s["blocked_totals"]), len(s["blocked"]),
            "" if len(s["blocked"]) == 1 else "s"))
    lines.append("Nothing has been paid or marked paid by this report. Export and mark paid on Bulk payouts.")
    out.append(("What is owed", lines, "bulk"))

    if s["large_refunds"] or s["repeat_refunds"]:
        lines = ["%s %s of %s on %s - commission taken back %s (%s)" % (
            r["code"], "chargeback" if r["kind"] == "dispute" else "refund",
            _money(r["customer_amount"], r["currency"]), r["date"],
            _money(abs(r["commission"]), r["currency"]), r["source"]) for r in s["large_refunds"]]
        lines += ["%s had %d refunds or chargebacks in the month" % cn for cn in s["repeat_refunds"]]
        out.append(("Large refunds and chargebacks (refunds of %s or more, every chargeback)"
                    % _money(s["large_refund_floor"]), lines, "ledger"))
    if s["held"]:
        out.append(("Held commission", [
            "%s %s (%s) - %s in %d line%s - %s" % (
                h["code"], h["name"], h["status"], _money(h["amount"], h["currency"]), h["count"],
                "" if h["count"] == 1 else "s", h["reason"]) for h in s["held"]], "held"))
    if s["no_tax"] or s["forms_waiting"] or s["held_no_tax"]:
        lines = ["%s %s - %s waiting (%s)" % (r["code"], r["name"], _money(r["amount"], r["currency"]),
                                              r["period"]) for r in s["no_tax"]]
        if s["held_no_tax"]:
            lines.append("Held commission and no tax form: %s" % ", ".join(s["held_no_tax"]))
        if s["forms_waiting"]:
            lines.append("%d uploaded form%s waiting for your review." % (
                s["forms_waiting"], "" if s["forms_waiting"] == 1 else "s"))
        out.append(("Missing tax forms", lines, "tax"))
    if s["no_details"]:
        out.append(("Missing payout details", [
            "%s %s - %s - %s" % (r["code"], r["name"], _money(r["amount"], r["currency"]),
                                 r["short_reason"]) for r in s["no_details"]], "affiliates"))
    if s["carries"]:
        out.append(("Carried to next month (under the %s minimum, or negative)" % _money(s["minimum"]), [
            "%s %s - %s - %s" % (r["code"], r["period"], _money(r["amount"], r["currency"]),
                                 r["short_reason"]) for r in s["carries"]], "ledger"))
    if s["activity"]:
        lines = []
        for a in s["activity"]:
            if a["state"] == "closing":
                lines.append("%s %s - renewal commissions stop after %s (%d day%s) unless they bring "
                             "a new paying customer" % (a["code"], a["name"], a["date"], a["days"],
                                                        "" if a["days"] == 1 else "s"))
            else:
                lines.append("%s %s - renewal commissions lapsed on %s" % (a["code"], a["name"], a["date"]))
        out.append(("Activity deadline (next %d days)" % s["warn_days"], lines, "affiliates"))
    if not s["flags"]:
        out.append(("Things to check", ["Nothing flagged this month."], None))
    return out


def render_text(summary) -> str:
    links = {k: url for k, _label, url in summary["links"]}
    parts = ["TradeWave affiliate operations summary - %s" % summary["period_label"], ""]
    for heading, lines, key in sections(summary):
        parts.append(heading.upper())
        parts.extend(lines)
        if key:
            parts.append("Open: %s" % links[key])
        parts.append("")
    parts.append("ADMIN LINKS")
    parts.extend("%s: %s" % (label, url) for _k, label, url in summary["links"])
    parts += ["", "This report only reads the ledger. It never pays anyone and never marks a row paid."]
    return "\n".join(parts)


def render_html(summary) -> str:
    e = _html.escape
    links = {k: url for k, _label, url in summary["links"]}
    out = ['<div style="font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2a44;max-width:680px">',
           '<h2 style="font-size:19px;margin:0 0 12px">Affiliate operations summary - %s</h2>'
           % e(summary["period_label"])]
    for heading, lines, key in sections(summary):
        out.append('<h3 style="font-size:15px;margin:18px 0 4px;color:#3a32a8">%s</h3>' % e(heading))
        out.append('<ul style="margin:0 0 6px 18px;padding:0">%s</ul>'
                   % "".join("<li>%s</li>" % e(ln.strip()) for ln in lines))
        if key:
            out.append('<p style="margin:0"><a href="%s">Open in admin</a></p>' % e(links[key]))
    out.append('<h3 style="font-size:15px;margin:18px 0 4px;color:#3a32a8">Admin links</h3><ul style="margin:0 0 6px 18px;padding:0">')
    out.extend('<li><a href="%s">%s</a></li>' % (e(url), e(label)) for _k, label, url in summary["links"])
    out.append('</ul><p style="color:#666;font-size:13px">This report only reads the ledger. '
               'It never pays anyone and never marks a row paid.</p></div>')
    return "".join(out)


def already_sent(session, period: dt.date) -> bool:
    from models import AuditLog
    key = period.strftime("%Y-%m")
    for (details,) in session.query(AuditLog.details).filter(AuditLog.action == SENT_ACTION).all():
        if isinstance(details, dict) and details.get("period") == key:
            return True
    return False


def send_summary(session, year: int, month: int, *, force=False, now=None) -> str:
    """Build and email the summary once per month. Returns 'sent',
    'already_sent' or 'not_sent' (email not configured / refused)."""
    from email_utils import resend_send_email
    from models import AuditLog
    period = dt.date(year, month, 1)
    if not force and already_sent(session, period):
        log.info("summary for %s already sent; nothing to do (use --force to resend)", period.strftime("%Y-%m"))
        return "already_sent"
    summary = build_summary(session, year, month, now=now)
    to = getattr(config, "AFFILIATE_OPS_EMAIL", "") or config.SUPPORT_EMAIL_TO
    ok = resend_send_email(to=to, subject=subject_for(summary), body_text=render_text(summary),
                           html=render_html(summary))
    if not ok:
        log.warning("summary email was not sent (Resend not configured or refused)")
        return "not_sent"
    session.add(AuditLog(actor_label="affiliate_ops_summary", action=SENT_ACTION,
                         details={"period": period.strftime("%Y-%m"), "to": to,
                                  "flags": summary["flags"],
                                  "payable_rows": len(summary["payable"])}))
    session.commit()
    log.info("summary for %s emailed to %s (%d flag(s))", period.strftime("%Y-%m"), to, summary["flags"])
    return "sent"


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s affiliate_ops_summary: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", help="YYYY-MM (default: previous month)")
    ap.add_argument("--email", action="store_true", help="email the owner (once per month)")
    ap.add_argument("--force", action="store_true", help="send even if this month was already sent")
    args = ap.parse_args(argv)
    if not config.POSTGRES_DSN:
        log.error("POSTGRES_DSN not set")
        return 1
    if args.month:
        try:
            y, m = (int(x) for x in args.month.split("-"))
            dt.date(y, m, 1)
        except (ValueError, TypeError):
            log.error("bad --month %r (want YYYY-MM)", args.month)
            return 2
    else:
        y, m = prev_month(dt.date.today())
    from models import Session
    s = Session()
    try:
        if args.email:
            return 0 if send_summary(s, y, m, force=args.force) in ("sent", "already_sent") else 3
        print(render_text(build_summary(s, y, m)))
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
