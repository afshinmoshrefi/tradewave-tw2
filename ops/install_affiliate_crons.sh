#!/usr/bin/env bash
# Install the affiliate / SMN-expert crons. Idempotent: older lines for each
# job are removed before the canonical entry is added.
#
#   web box (has /home/flask/web):
#     - expert_scorecard.py  daily 02:15 UTC - scores closed expert calls
#     - affiliate_ops_summary.py --email  06:30 UTC on the 3rd - one owner
#       email after month close: what is owed + things to check. Read-only on
#       the ledger; never marks anything paid (TW-TASK-0039 C).
#   SMN-serving box (has expert_sync.py; pass its path if not the default):
#     - expert_sync.py       every 2 min     - pulls published/retracted takes +
#                                              profiles, injects Expert Desk
#                                              blocks, rebuilds /experts/ hubs
#
# Usage: sudo bash ops/install_affiliate_crons.sh [web|smn|both] [EXPERT_SYNC_PATH]
# (the monthly affiliate_report.py --email cron is documented in that file
# and is left untouched here)
set -euo pipefail

ROLE="${1:-both}"
SYNC_PY="${2:-/home/flask/smn/expert_sync.py}"
PY=/home/flask/venv/bin/python

SCORE_LINE="15 2 * * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/expert_scorecard.lock $PY /home/flask/web/expert_scorecard.py >> /var/log/tradewave/expert_scorecard.log 2>&1"
SUMMARY_LINE="30 6 3 * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/affiliate_ops_summary.lock $PY /home/flask/web/affiliate_ops_summary.py --email >> /var/log/tradewave/affiliate_ops_summary.log 2>&1"
SYNC_LINE="*/2 * * * * set -a; . /etc/tradewave/secrets.env; set +a; flock -n /var/log/tradewave/expert_sync.lock $PY $SYNC_PY >> /var/log/tradewave/expert_sync.log 2>&1"

sudo -u flask test -r /etc/tradewave/secrets.env || { echo "FAIL: secrets.env not readable by flask" >&2; exit 1; }
[ -x "$PY" ] || { echo "FAIL: $PY missing" >&2; exit 1; }
install -d -o flask -g flask -m 0750 /var/log/tradewave

want=()
case "$ROLE" in
  web)  want=(score summary) ;;
  smn)  want=(sync) ;;
  both) want=(score summary sync) ;;
  *) echo "usage: $0 [web|smn|both] [EXPERT_SYNC_PATH]" >&2; exit 2 ;;
esac

current=$(sudo -u flask crontab -l 2>/dev/null || true)
lines=()
for w in "${want[@]}"; do
  if [ "$w" = score ]; then
    [ -f /home/flask/web/expert_scorecard.py ] || { echo "FAIL: expert_scorecard.py missing" >&2; exit 1; }
    current=$(printf '%s\n' "$current" | grep -v 'expert_scorecard.py' || true)
    touch /var/log/tradewave/expert_scorecard.log; chown flask:flask /var/log/tradewave/expert_scorecard.log
    lines+=("$SCORE_LINE")
  elif [ "$w" = summary ]; then
    [ -f /home/flask/web/affiliate_ops_summary.py ] || { echo "FAIL: affiliate_ops_summary.py missing" >&2; exit 1; }
    current=$(printf '%s\n' "$current" | grep -v 'affiliate_ops_summary.py' || true)
    touch /var/log/tradewave/affiliate_ops_summary.log; chown flask:flask /var/log/tradewave/affiliate_ops_summary.log
    lines+=("$SUMMARY_LINE")
  else
    [ -f "$SYNC_PY" ] || { echo "FAIL: $SYNC_PY missing (pass the SMN box's expert_sync.py path)" >&2; exit 1; }
    current=$(printf '%s\n' "$current" | grep -v 'expert_sync.py' || true)
    touch /var/log/tradewave/expert_sync.log; chown flask:flask /var/log/tradewave/expert_sync.log
    lines+=("$SYNC_LINE")
  fi
done

{ printf '%s\n' "$current"; printf '%s\n' "${lines[@]}"; } | grep -vE '^$' | sudo -u flask crontab -

for l in "${lines[@]}"; do
  if sudo -u flask crontab -l | grep -qF "$l"; then echo "OK: $l"; else echo "FAIL: missing after install: $l" >&2; exit 1; fi
done
