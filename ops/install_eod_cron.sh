#!/usr/bin/env bash
# Install the appserver EOD data-refresh cron on whatever APP box this runs
# on. Idempotent (re-run converges, never duplicates). Box-agnostic: it
# reads /etc/tradewave/secrets.env on the box it runs on, so the same
# script is correct for prod-app and stage-app.
#
#   sudo bash /home/flask/ops/install_eod_cron.sh
#
# What it installs (TW1's canonical job, per the deployment runbook):
#   The immutable /home/flask/.tw2-app-current release pointer owns the job code.
#   data_updater/update_client2.py pulls EOD deltas from config.update_server
#   (TW2_UPDATE_SERVER in secrets.env) into /home/flask/data/csv/. Runs as
#   flask (the data dir is flask-owned) with secrets sourced. The production
#   keyprovider starts its EODHD load at 20:03 New York time and currently
#   takes about 92 minutes. Appservers therefore poll at 03:05-05:05 UTC
#   Tuesday-Saturday; update_client2 exits immediately after a successful
#   same-market-date completion marker. After authoritative success (including
#   marker no-ops), update_client2 runs the bounded, idempotent ML score warmer.
#   Logs to update_client.log.
#
# TW1 ran this from /etc/crontab as root; TW2 runs it on the flask crontab
# with secrets sourced so it picks up the per-env TW2_UPDATE_SERVER.
set -euo pipefail

RELEASE_ROOT='/home/flask/.tw2-app-current'
LINE='5 3-5 * * 2-6 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/.tw2-app-current/data_updater && flock -n /var/lib/tradewave/eod/update.lock /home/flask/venv/bin/python update_client2.py >> /var/log/tradewave/update_client.log 2>&1'

# Sanity: every piece the cron needs must exist on THIS box.
[ -r /etc/tradewave/secrets.env ]                  || { echo "FAIL: /etc/tradewave/secrets.env not readable"; exit 1; }
[ -x /home/flask/venv/bin/python ]                 || { echo "FAIL: /home/flask/venv/bin/python missing"; exit 1; }
[ -d "$RELEASE_ROOT/data_updater" ]                 || { echo "FAIL: $RELEASE_ROOT/data_updater missing"; exit 1; }
[ -f "$RELEASE_ROOT/data_updater/update_client2.py" ] || { echo "FAIL: release update_client2.py missing"; exit 1; }
[ -f "$RELEASE_ROOT/data_updater/prefetch_ml_scores.py" ] || { echo "FAIL: release prefetch_ml_scores.py missing"; exit 1; }
us=$(grep -E '^TW2_UPDATE_SERVER=' /etc/tradewave/secrets.env | cut -d= -f2- || true)
[ -n "$us" ] || { echo "FAIL: TW2_UPDATE_SERVER is empty/unset in secrets.env"; exit 1; }
echo "TW2_UPDATE_SERVER = $us"

install -d -o flask -g flask -m 0750 /var/log/tradewave /var/lib/tradewave/eod
touch /var/log/tradewave/update_client.log
chown flask:flask /var/log/tradewave/update_client.log

# Remove the legacy system-crontab copy. In production it was missing the
# mandatory username field, so cron interpreted `set` as a user and never ran.
if grep -q 'update_client2.py' /etc/crontab; then
  cp -a /etc/crontab "/etc/crontab.pre-tw2-eod.$(date -u +%Y%m%d%H%M%S)"
  awk '!/update_client2[.]py/' /etc/crontab > /etc/crontab.tw2-eod.tmp
  install -m 0644 /etc/crontab.tw2-eod.tmp /etc/crontab
  rm -f /etc/crontab.tw2-eod.tmp
fi

cur=$(sudo -u flask crontab -l 2>/dev/null || true)
cleaned=$(printf '%s\n' "$cur" | grep -v 'update_client2.py' || true)
{ printf '%s\n' "$cleaned"; printf '%s\n' "$LINE"; } | grep -vE '^$' | sudo -u flask crontab -

if sudo -u flask crontab -l | grep -qF "$LINE"; then
  echo "OK: appserver EOD refresh cron installed (03:05-05:05 UTC Tue-Sat, marker-gated)."
  echo "flask crontab now:"
  sudo -u flask crontab -l | grep -vE '^#|^$' | sort
else
  echo "FAIL: EOD line not present after install"; exit 1
fi
