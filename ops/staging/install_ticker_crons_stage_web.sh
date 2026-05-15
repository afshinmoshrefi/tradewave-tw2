#!/usr/bin/env bash
# Install the two web-tier crons on stage-web so ticker pages update daily
# like TW1:
#   1. update_client2.py  — pulls daily EOD deltas from config.update_server
#      (TW2_UPDATE_SERVER = central 104.238.214.253:7775) into
#      /home/flask/data/csv/. TW1 ran this from /etc/crontab as root at 23:36;
#      TW2 runs it as flask (the data dir is flask-owned) with secrets sourced.
#   2. generate_ticker_pages.py — regenerates /var/www/tradewave/patterns/
#      at 02:00 and hourly 09-16 (DEPLOY_STAGING §17.2). Runs AFTER the
#      23:36 EOD refresh so it renders off fresh data.
#
# Idempotent — re-running de-dupes via sort -u.
#
# NOTE: if the central update_server 403s the staging IP (same allowlist
# issue seen with stockta:7771), the EOD cron will no-op and ticker pages
# regenerate off frozen data. Allowlisting the staging public IP on
# 104.238.214.253 is a separate task on the central box.
#
# Run on .176 as root.

set -euo pipefail
WEB=185.53.209.8
SSH="-p 4369"

ssh $SSH "root@$WEB" 'bash -s' <<'REMOTE'
set -e
EOD_LINE='36 23 * * * set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/data_updater && /home/flask/venv/bin/python update_client2.py >> /var/log/tradewave/eod_update.log 2>&1'
TICK_LINE='0 2,9-16 * * * set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/site/ticker_pages && /home/flask/venv/bin/python generate_ticker_pages.py >> /var/log/tradewave/ticker_pages.log 2>&1'

current=$(sudo -u flask crontab -l 2>/dev/null || true)
{
  printf '%s\n' "$current"
  printf '%s\n' "$EOD_LINE"
  printf '%s\n' "$TICK_LINE"
} | grep -v '^$' | sort -u | sudo -u flask crontab -

echo "flask crontab on stage-web now:"
sudo -u flask crontab -l | grep -E 'update_client2|generate_ticker_pages'
REMOTE

echo
echo "=== ticker crons installed on stage-web ==="
echo "EOD refresh: 23:36 daily.  Ticker regen: 02:00 + hourly 09-16."
echo "First natural run tonight; to test now:"
echo "  ssh root@${WEB} -p 4369 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/data_updater && sudo -u flask -E /home/flask/venv/bin/python update_client2.py 2>&1 | tail -20'"
