#!/usr/bin/env bash
# Install the appserver EOD data-refresh cron on whatever APP box this runs
# on. Idempotent (re-run converges, never duplicates). Box-agnostic: it
# reads /etc/tradewave/secrets.env on the box it runs on, so the same
# script is correct for prod-app and stage-app.
#
#   sudo bash /home/flask/ops/install_eod_cron.sh
#
# What it installs (TW1's canonical job, per the deployment runbook):
#   data_updater/update_client2.py pulls EOD deltas from config.update_server
#   (TW2_UPDATE_SERVER in secrets.env) into /home/flask/data/csv/. Runs as
#   flask (the data dir is flask-owned) with secrets sourced, 23:36 daily
#   (TW1 schedule, after the US market EOD). Logs to update_client.log.
#
# TW1 ran this from /etc/crontab as root; TW2 runs it on the flask crontab
# with secrets sourced so it picks up the per-env TW2_UPDATE_SERVER.
set -euo pipefail

LINE='36 23 * * * set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/data_updater && /home/flask/venv/bin/python update_client2.py >> /var/log/tradewave/update_client.log 2>&1'

# Sanity: every piece the cron needs must exist on THIS box.
[ -r /etc/tradewave/secrets.env ]                  || { echo "FAIL: /etc/tradewave/secrets.env not readable"; exit 1; }
[ -x /home/flask/venv/bin/python ]                 || { echo "FAIL: /home/flask/venv/bin/python missing"; exit 1; }
[ -f /home/flask/data_updater/update_client2.py ]  || { echo "FAIL: /home/flask/data_updater/update_client2.py missing"; exit 1; }
us=$(grep -E '^TW2_UPDATE_SERVER=' /etc/tradewave/secrets.env | cut -d= -f2- || true)
[ -n "$us" ] || { echo "FAIL: TW2_UPDATE_SERVER is empty/unset in secrets.env"; exit 1; }
echo "TW2_UPDATE_SERVER = $us"

cur=$(sudo -u flask crontab -l 2>/dev/null || true)
{ printf '%s\n' "$cur"; printf '%s\n' "$LINE"; } | grep -vE '^$' | sort -u | sudo -u flask crontab -

if sudo -u flask crontab -l | grep -qF 'update_client2.py'; then
  echo "OK: appserver EOD refresh cron installed (23:36 daily, flask, secrets-sourced)."
  echo "flask crontab now:"
  sudo -u flask crontab -l | grep -vE '^#|^$' | sort
else
  echo "FAIL: EOD line not present after install"; exit 1
fi
