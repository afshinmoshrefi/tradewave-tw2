#!/usr/bin/env bash
# Install the canonical daily AI pick X publisher on a TW2 WEB box.
# Idempotent: every older line for this job is removed before the canonical
# weekday entry is added. The Python job remains fail-closed outside production
# and unless TW2_X_POSTING_ENABLED=1.
set -euo pipefail

LINE='10 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py --send >> /var/log/tradewave/m_daily_ai_pick_social.log 2>&1'

sudo -u flask test -r /etc/tradewave/secrets.env || {
  echo "FAIL: /etc/tradewave/secrets.env not readable by flask" >&2
  exit 1
}
[ -x /home/flask/venv/bin/python ] || {
  echo "FAIL: /home/flask/venv/bin/python missing" >&2
  exit 1
}
[ -f /home/flask/site/m_daily_ai_pick_social.py ] || {
  echo "FAIL: daily AI pick X publisher missing" >&2
  exit 1
}

install -d -o flask -g flask -m 0750 /var/log/tradewave
touch /var/log/tradewave/m_daily_ai_pick_social.log
chown flask:flask /var/log/tradewave/m_daily_ai_pick_social.log

current=$(sudo -u flask crontab -l 2>/dev/null || true)
cleaned=$(printf '%s\n' "$current" | grep -v 'm_daily_ai_pick_social.py' || true)
{
  printf '%s\n' "$cleaned"
  printf '%s\n' "$LINE"
} | grep -vE '^$' | sudo -u flask crontab -

if sudo -u flask crontab -l | grep -qF '10 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py --send'; then
  echo "OK: daily AI pick X cron installed (07:10 weekdays, flask)."
else
  echo "FAIL: daily AI pick X cron missing after install" >&2
  exit 1
fi
