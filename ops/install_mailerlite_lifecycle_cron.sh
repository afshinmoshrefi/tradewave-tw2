#!/usr/bin/env bash
# Install the durable MailerLite lifecycle worker on a TW2 WEB box.
# Idempotent: any older line for this worker is removed before the canonical
# once-per-minute entry is added. The worker itself is fail-closed unless
# MAILERLITE_OUTBOUND_ENABLED=1 on prod and all lifecycle group IDs exist.
set -euo pipefail

LINE='* * * * * { test -r /etc/tradewave/secrets.env && set -a && . /etc/tradewave/secrets.env && set +a && cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --limit 15; } >> /var/log/tradewave/mailerlite_lifecycle.log 2>&1'

sudo -u flask test -r /etc/tradewave/secrets.env || {
  echo "FAIL: /etc/tradewave/secrets.env not readable by flask" >&2
  exit 1
}
[ -x /home/flask/venv/bin/python ] || {
  echo "FAIL: /home/flask/venv/bin/python missing" >&2
  exit 1
}
[ -f /home/flask/web/mailerlite_lifecycle.py ] || {
  echo "FAIL: /home/flask/web/mailerlite_lifecycle.py missing" >&2
  exit 1
}

install -d -o flask -g flask -m 0750 /var/log/tradewave
touch /var/log/tradewave/mailerlite_lifecycle.log
chown flask:flask /var/log/tradewave/mailerlite_lifecycle.log

current=$(sudo -u flask crontab -l 2>/dev/null || true)
cleaned=$(printf '%s\n' "$current" | grep -v 'mailerlite_lifecycle.py' || true)
{
  printf '%s\n' "$cleaned"
  printf '%s\n' "$LINE"
} | grep -vE '^$' | sudo -u flask crontab -

if sudo -u flask crontab -l | grep -qF '/web/mailerlite_lifecycle.py --limit 15'; then
  echo "OK: MailerLite lifecycle cron installed (once per minute, flask)."
else
  echo "FAIL: MailerLite lifecycle cron missing after install" >&2
  exit 1
fi

# Prove the exact cron user can load secrets, import the worker, and read the
# migrated outbox without claiming a row or contacting MailerLite.
sudo -u flask bash -c \
  'set -a && . /etc/tradewave/secrets.env && set +a && cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --dry-run --limit 1'
