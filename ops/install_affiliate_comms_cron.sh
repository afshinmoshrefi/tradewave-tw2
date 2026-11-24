#!/usr/bin/env bash
# Install the partner lifecycle-email cron (TW-TASK-0039 package B). Idempotent:
# any older line for the job is removed before the canonical entry is added.
#
#   web box (has /home/flask/web):
#     - affiliate_comms.py  daily 14:10 UTC - welcome, first click, new paying
#       customer, statement ready, payout sent, activity warnings (60/30/7
#       days), renewals stopped / resumed, new company sale, discount change.
#       One send per event per partner (affiliate_notifications is the log).
#
# Usage: sudo bash ops/install_affiliate_comms_cron.sh
# Called by ops/install_affiliate_crons.sh for the web role.
# Preview without sending:  python /home/flask/web/affiliate_comms.py --dry-run
set -euo pipefail

PY=/home/flask/venv/bin/python
JOB=/home/flask/web/affiliate_comms.py
LOG=/var/log/tradewave/affiliate_comms.log
LINE="10 14 * * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/affiliate_comms.lock $PY $JOB >> $LOG 2>&1"

sudo -u flask test -r /etc/tradewave/secrets.env || { echo "FAIL: secrets.env not readable by flask" >&2; exit 1; }
[ -x "$PY" ] || { echo "FAIL: $PY missing" >&2; exit 1; }
[ -f "$JOB" ] || { echo "FAIL: $JOB missing" >&2; exit 1; }
install -d -o flask -g flask -m 0750 /var/log/tradewave
touch "$LOG"; chown flask:flask "$LOG"

current=$(sudo -u flask crontab -l 2>/dev/null || true)
current=$(printf '%s\n' "$current" | grep -v 'affiliate_comms.py' || true)
{ printf '%s\n' "$current"; printf '%s\n' "$LINE"; } | grep -vE '^$' | sudo -u flask crontab -

if sudo -u flask crontab -l | grep -qF "$LINE"; then echo "OK: $LINE"; else echo "FAIL: missing after install: $LINE" >&2; exit 1; fi
