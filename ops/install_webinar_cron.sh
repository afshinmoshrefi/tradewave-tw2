#!/usr/bin/env bash
# Install the Google-Sheet webinar page refresh for the web tier.
# Idempotent: replaces any older limited-hours entry with one hourly refresh.
set -euo pipefail

CRON_USER=flask
MARKER='/home/flask/site/generate_webinar_page.py'
ENTRY='0 * * * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_webinar_page.py --force >> /var/log/tradewave/webinar_page.log 2>&1'

install -d -m 0755 -o flask -g flask /var/log/tradewave
current="$(mktemp)"
updated="$(mktemp)"
trap 'rm -f "$current" "$updated"' EXIT

crontab -u "$CRON_USER" -l >"$current" 2>/dev/null || true
grep -Fv "$MARKER" "$current" >"$updated" || true
printf '%s\n' "$ENTRY" >>"$updated"
crontab -u "$CRON_USER" "$updated"

crontab -u "$CRON_USER" -l | grep -Fq "$MARKER"
echo "webinar cron installed for $CRON_USER: hourly"
