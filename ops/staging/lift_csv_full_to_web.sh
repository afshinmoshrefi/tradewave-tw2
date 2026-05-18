#!/usr/bin/env bash
# Lift the FULL per-ticker csv tree + all *_symbols.csv from the APP box to
# the WEB box over the Kamatera VLAN. Prod analog of lift_csv_us_to_web.sh
# (which is US-only) — prod-web's ticker/scorecard/home-opps generators read
# /home/flask/data/csv/<market>/<sym>.csv locally for ALL markets.
#
# Does NOT copy the app-side precompute (opportunities/ opp_by_symbol/) —
# that stays app-only, served via the appserver API.
#
# Staging defaults; run via run_prod.sh for prod (coordinates swapped).
# Run on .176 as root: temp-copies .176 /root/.ssh/id_rsa to the web box,
# web box rsyncs from the app box over VLAN, key trap-wiped.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

APP_VLAN=10.0.0.92          # app box VLAN IP (run_prod -> 10.0.0.96)
WEB_HOST=185.53.209.8       # web box public  (run_prod -> 194.113.195.141)
SSH_PORT=4369
LOCAL_KEY=/root/.ssh/id_rsa
REMOTE_KEY=/root/.csvsync_key

[[ -r "$LOCAL_KEY" ]] || { echo "No $LOCAL_KEY on .176" >&2; exit 1; }
cleanup() { ssh -p "$SSH_PORT" "root@${WEB_HOST}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true; }
trap cleanup EXIT INT TERM HUP

hdr "1. temp key onto web box"
scp -P "$SSH_PORT" "$LOCAL_KEY" "root@${WEB_HOST}:${REMOTE_KEY}"
ssh -p "$SSH_PORT" "root@${WEB_HOST}" "chmod 600 $REMOTE_KEY"

hdr "2. web box rsyncs full csv/ + *_symbols.csv from app over VLAN"
ssh -p "$SSH_PORT" "root@${WEB_HOST}" "
  install -d -o flask -g flask -m 755 /home/flask/data /home/flask/data/csv
  rsync -a --partial --info=progress2 \
    -e 'ssh -i $REMOTE_KEY -p $SSH_PORT -o StrictHostKeyChecking=accept-new' \
    root@${APP_VLAN}:/home/flask/data/csv/ /home/flask/data/csv/
  rsync -a --info=progress2 \
    -e 'ssh -i $REMOTE_KEY -p $SSH_PORT -o StrictHostKeyChecking=accept-new' \
    root@${APP_VLAN}:/home/flask/data/ --include='*_symbols.csv' --exclude='*/' --exclude='*' \
    /home/flask/data/ 2>/dev/null || \
  rsync -a -e \"ssh -i $REMOTE_KEY -p $SSH_PORT -o StrictHostKeyChecking=accept-new\" \
    root@${APP_VLAN}:'/home/flask/data/*_symbols.csv' /home/flask/data/
  chown -R flask:flask /home/flask/data
  echo '--- result ---'
  du -sh /home/flask/data/csv
  ls /home/flask/data/*_symbols.csv 2>/dev/null | wc -l
  df -h / | tail -1
"

hdr "done"
echo "Full csv + symbol manifests on web box. Precompute stays app-side."
