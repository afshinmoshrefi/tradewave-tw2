"""Daily report-expiry sweep.

Deletes rendered static reports (index.html + PNGs) under /var/www/tradewave/r/
once the pattern's END date is more than 30 days in the past. This only cleans
up the WEB TIER's static files - it does NOT touch the Redis user_reports_*
portfolio records, so a user's saved pattern survives; if they come back to it,
the React Refresh button re-fires dr_report_publish, which (see appserver.py's
idempotent-refresh path) detects the existing record and re-renders instead of
rejecting as a duplicate.

Cron entry (web box):
  15 4 * * * cd /home/flask/web && /home/flask/venv/bin/python report_expiry.py >> /var/log/tradewave/report_expiry.log 2>&1

Idempotent - safe to run as often as you like. --dry-run previews with zero
side effects (no deletions, no sitemap rebuild).
"""
from __future__ import annotations

import argparse
import datetime
import logging
import re
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import report_renderer  # noqa: E402

REPORT_ROOT = Path(report_renderer.REPORT_OUTPUT_ROOT)  # /var/www/tradewave/r
EXPIRY_DAYS = 30

# Dir name must END with -YYYY-MM-DD-to-YYYY-MM-DD ; group(2) is the end date.
# Anything that doesn't match this suffix (a stray file, sitemap.xml, a
# differently-named dir) is left alone - never touched.
_END_DATE_RE = re.compile(r'-(\d{4}-\d{2}-\d{2})-to-(\d{4}-\d{2}-\d{2})$')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s report_expiry: %(message)s",
)
log = logging.getLogger(__name__)


def _parse_end_date(dirname):
    """Return the pattern's end date (datetime.date), or None if dirname doesn't match."""
    m = _END_DATE_RE.search(dirname)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(2), '%Y-%m-%d').date()
    except ValueError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true', help='print what would be deleted, delete nothing')
    args = ap.parse_args(argv)

    if not REPORT_ROOT.is_dir():
        log.error("refusing to run - report root does not exist: %s", REPORT_ROOT)
        return 1

    root_real = REPORT_ROOT.resolve()
    today = datetime.date.today()
    cutoff = datetime.timedelta(days=EXPIRY_DAYS)

    scanned = 0
    expired = []
    for entry in sorted(REPORT_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        scanned += 1
        end_date = _parse_end_date(entry.name)
        if end_date is None:
            log.debug("skip (no date-range suffix match): %s", entry.name)
            continue
        if end_date + cutoff < today:
            expired.append((entry, end_date))

    deleted = 0
    for entry, end_date in expired:
        # Safety: only ever delete a direct child of REPORT_ROOT, re-verified via
        # realpath right before the rmtree - never trust the iterdir() listing alone.
        real_entry = entry.resolve()
        if real_entry.parent != root_real:
            log.warning("skip (not a direct child of %s after realpath): %s", root_real, real_entry)
            continue
        days_past = (today - end_date).days - EXPIRY_DAYS
        if args.dry_run:
            log.info("[DRY-RUN] would delete %s (end_date=%s, %d days past the %d-day expiry)",
                      entry.name, end_date.isoformat(), days_past, EXPIRY_DAYS)
            continue
        try:
            shutil.rmtree(real_entry)
            deleted += 1
            log.info("deleted %s (end_date=%s, %d days past the %d-day expiry)",
                      entry.name, end_date.isoformat(), days_past, EXPIRY_DAYS)
        except OSError:
            log.exception("failed to delete %s", real_entry)

    if deleted > 0:
        try:
            sitemap_path = report_renderer.rebuild_report_sitemap()
            log.info("sitemap rebuilt: %s", sitemap_path)
        except Exception:
            log.exception("sitemap rebuild failed after expiry sweep")

    summary = "scanned=%d expired=%d deleted=%d dry_run=%s" % (scanned, len(expired), deleted, args.dry_run)
    print(summary)
    log.info(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
