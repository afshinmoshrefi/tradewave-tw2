#!/usr/bin/env bash
# Install the partner-program crons of the web box (TW-TASK-0039 package B +
# fix-0039). Idempotent: any older line for a job is removed before the
# canonical entry is added.
#
#   web box (has /home/flask/web):
#     - affiliate_comms.py  daily 14:10 UTC - welcome, first click, new paying
#       customer, statement ready, payout sent, activity warnings (60/30/7
#       days), renewals stopped / resumed, new company sale, discount change,
#       signing reminders (3 and 10 days), tax-form results; plus the owner
#       digest (only when something has waited more than 48 hours), retries of
#       failed notices and the help-chat retention purge.
#       One send per event per partner (affiliate_notifications is the log).
#     - affiliate_jobs.py   every 2 minutes - the background job queue
#       (affiliate_jobs table): group message sends and suggested general
#       knowledge-base answers. These used to run inside the web request.
#
# ONE STATEMENT EMAIL, NOT TWO: affiliate_comms.py is the only sender of the
# monthly statement email. This script therefore strips "--email" from an
# existing affiliate_report.py cron line (the ledger sweep stays; only the
# older second statement email goes). affiliate_report.py also ignores the
# flag, so a line installed by hand later is harmless.
#
# Usage: sudo bash ops/install_affiliate_comms_cron.sh
# Called by ops/install_affiliate_crons.sh for the web role.
# Preview without sending:  python /home/flask/web/affiliate_comms.py --dry-run
set -euo pipefail

PY=/home/flask/venv/bin/python
JOB=/home/flask/web/affiliate_comms.py
JOBS=/home/flask/web/affiliate_jobs.py
LOG=/var/log/tradewave/affiliate_comms.log
JOBS_LOG=/var/log/tradewave/affiliate_jobs.log
LINE="10 14 * * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/affiliate_comms.lock $PY $JOB >> $LOG 2>&1"
JOBS_LINE="*/2 * * * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/affiliate_jobs.lock $PY $JOBS >> $JOBS_LOG 2>&1"

# Remove the --email flag from affiliate_report.py cron lines (stdin -> stdout).
# Only lines that run affiliate_report.py are touched; --email-anything-else
# (a longer flag) is left alone.
strip_report_email() {
  sed -E '/affiliate_report\.py/ s/[[:space:]]+--email([[:space:]]|$)/\1/g'
}

if [ "${1:-}" = "--print-strip" ]; then    # used by the tests: filter stdin, change nothing
  strip_report_email
  exit 0
fi

sudo -u flask test -r /etc/tradewave/secrets.env || { echo "FAIL: secrets.env not readable by flask" >&2; exit 1; }
[ -x "$PY" ] || { echo "FAIL: $PY missing" >&2; exit 1; }
[ -f "$JOB" ] || { echo "FAIL: $JOB missing" >&2; exit 1; }
[ -f "$JOBS" ] || { echo "FAIL: $JOBS missing" >&2; exit 1; }
install -d -o flask -g flask -m 0750 /var/log/tradewave
touch "$LOG" "$JOBS_LOG"; chown flask:flask "$LOG" "$JOBS_LOG"

current=$(sudo -u flask crontab -l 2>/dev/null || true)
if printf '%s\n' "$current" | grep -E 'affiliate_report\.py' | grep -qE -- '[[:space:]]--email([[:space:]]|$)'; then
  echo "NOTE: removing --email from the affiliate_report.py cron line (affiliate_comms.py sends the statement email)"
fi
current=$(printf '%s\n' "$current" | strip_report_email)
current=$(printf '%s\n' "$current" | grep -v 'affiliate_comms.py' | grep -v 'affiliate_jobs.py' || true)
{ printf '%s\n' "$current"; printf '%s\n' "$LINE"; printf '%s\n' "$JOBS_LINE"; } | grep -vE '^$' | sudo -u flask crontab -

for l in "$LINE" "$JOBS_LINE"; do
  if sudo -u flask crontab -l | grep -qF "$l"; then echo "OK: $l"; else echo "FAIL: missing after install: $l" >&2; exit 1; fi
done
if sudo -u flask crontab -l | grep -E 'affiliate_report\.py' | grep -qE -- '[[:space:]]--email([[:space:]]|$)'; then
  echo "FAIL: affiliate_report.py cron line still carries --email" >&2; exit 1
fi
echo "OK: no affiliate_report.py cron line sends statement emails"
