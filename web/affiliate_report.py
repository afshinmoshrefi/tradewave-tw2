"""Monthly affiliate commission sweep - upserts the payout ledger.

Computes per-affiliate commission for a calendar month (default: the previous
month) from Stripe and inserts pending rows into affiliate_payouts, idempotent
on (affiliate_id, period_start, currency). PURE downstream reader of Stripe -
touches no billing path or webhook. Review + the manual PayPal/Wise payout
happen in Flask-Admin (Affiliates -> Payout Ledger): mark each row paid and add
the txn id.

Cron (web box), 03:30 on the 2nd of each month (lets the prior month settle).
Pass --email so each affiliate also gets their anonymized monthly statement
(the cron is the ONLY place --email is set; manual re-runs without it stay
side-effect-free / ledger-only, so affiliates don't get duplicate statements):
  30 3 2 * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/web/affiliate_report.py --email >> /var/log/tradewave/affiliate_report.log 2>&1

Usage: affiliate_report.py [--month YYYY-MM] [--dry-run] [--email]
The ledger upsert is idempotent - safe to re-run. The --email send is NOT
idempotent, hence it's opt-in (cron-only); --dry-run --email just logs who'd be emailed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

import config  # noqa: E402  (loads per-env Stripe key / DSN from env)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s affiliate_report: %(message)s",
)
log = logging.getLogger(__name__)


def _prev_month(today: dt.date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def _fmt_money(amount, currency: str) -> str:
    c = (currency or "usd").lower()
    return ("$%0.2f USD" % float(amount)) if c == "usd" else ("%0.2f %s" % (float(amount), c.upper()))


def _customer_count(detail) -> int:
    """Distinct paying customers this month (anonymized count, never identities)."""
    cs = {ln.get("customer") for ln in (detail or []) if ln.get("customer")}
    return len(cs) if cs else len(detail or [])


def send_monthly_statements(rows, year: int, month: int, dry_run: bool = False) -> int:
    """Email each earning affiliate an ANONYMIZED monthly statement (totals + a
    customer count only - never any customer identity). Groups a multi-currency
    affiliate into one email. Best-effort: a failed/blank-email affiliate is
    logged and skipped, never aborts the run. Returns the number sent (or, in
    dry-run, that would be sent)."""
    from collections import defaultdict
    month_label = dt.date(year, month, 1).strftime("%B %Y")
    by_aff: dict = defaultdict(list)
    for r in rows:
        by_aff[r["affiliate_id"]].append(r)

    try:
        from email_utils import resend_send_email
    except Exception as e:
        log.warning("email_utils unavailable (%s); skipping statements", e)
        return 0

    sent = 0
    for entries in by_aff.values():
        e0 = entries[0]
        lines = []
        for e in entries:
            if float(e["commission_amount"]) <= 0:
                continue
            n = _customer_count(e.get("detail"))
            lines.append("  Commission earned: %s  (from %d customer%s)"
                         % (_fmt_money(e["commission_amount"], e["currency"]),
                            n, "" if n == 1 else "s"))
        if not lines:
            continue  # nothing earned this month
        to = e0.get("email")
        if not to:
            log.info("statement: %s earned but has no contact email; skipped", e0.get("code"))
            continue
        name = e0.get("name") or "there"
        payout = "%s (%s)" % (
            ((e0.get("payout_method") or "").upper() or "your payout method"),
            (e0.get("payout_email") or "the address on file"))
        body = (
            "Hi %s,\n\n"
            "Here is your TradeWave affiliate summary for %s:\n\n"
            "%s\n\n"
            "We'll send your payout to %s on the usual monthly schedule. "
            "Questions? Just reply to this email.\n\n"
            "Thanks for partnering with TradeWave.\n"
            % (name, month_label, "\n".join(lines), payout))

        if dry_run:
            log.info("statement (dry-run) -> %s [%s]: %s",
                     to, e0.get("code"), " | ".join(s.strip() for s in lines))
            sent += 1
            continue
        try:
            if resend_send_email(
                    to=to,
                    subject="Your TradeWave affiliate earnings - %s" % month_label,
                    body_text=body):
                sent += 1
                log.info("statement emailed -> %s [%s]", to, e0.get("code"))
        except Exception as ex:
            log.warning("statement email to %s [%s] failed: %s", to, e0.get("code"), ex)
    return sent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="YYYY-MM (default: previous month)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + log only; do not write the ledger or send email")
    ap.add_argument("--email", action="store_true",
                    help="email each affiliate their anonymized monthly statement "
                         "(off by default so manual re-runs stay side-effect-free; "
                         "the monthly cron passes --email). With --dry-run, only logs "
                         "who would be emailed.")
    args = ap.parse_args()

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
        y, m = _prev_month(dt.date.today())

    import affiliate_service as afs
    from models import Session

    s = Session()
    try:
        from collections import defaultdict
        from decimal import Decimal
        rows = afs.compute_month(s, y, m)
        totals = defaultdict(lambda: Decimal("0"))
        for r in rows:
            totals[r["currency"]] += r["commission_amount"]
            log.info("  %s (%s): revenue=%s commission=%s %s",
                     r["code"], r["name"], r["gross_revenue"],
                     r["commission_amount"], r["currency"].upper())
        # Never sum across currencies - one total per currency.
        totals_str = ", ".join(f"{amt} {ccy.upper()}" for ccy, amt in sorted(totals.items())) or "0"
        log.info("%d affiliate(s) owed for %04d-%02d, total=%s",
                 len(rows), y, m, totals_str)
        if args.dry_run:
            log.info("dry-run: ledger NOT written")
        else:
            afs.upsert_month(s, y, m)
            log.info("ledger upserted (idempotent) for %04d-%02d", y, m)
        if args.email:
            n = send_monthly_statements(rows, y, m, dry_run=args.dry_run)
            log.info("%smonthly statement emails: %d", "(dry-run) " if args.dry_run else "", n)
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
