"""Monthly affiliate commission sweep - upserts the payout ledger.

Computes per-affiliate commission for a calendar month (default: the previous
month) from Stripe and inserts pending rows into affiliate_payouts, idempotent
on (affiliate_id, period_start, currency). PURE downstream reader of Stripe -
touches no billing path or webhook. Review + the manual PayPal/Wise payout
happen in Flask-Admin (Affiliates -> Payout Ledger): mark each row paid and add
the txn id.

Cron (web box), 03:30 on the 2nd of each month (lets the prior month settle):
  30 3 2 * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/web/affiliate_report.py >> /var/log/tradewave/affiliate_report.log 2>&1

Usage: affiliate_report.py [--month YYYY-MM] [--dry-run]
Idempotent - safe to re-run.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="YYYY-MM (default: previous month)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + log only; do not write the ledger")
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
            return 0
        afs.upsert_month(s, y, m)
        log.info("ledger upserted (idempotent) for %04d-%02d", y, m)
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
