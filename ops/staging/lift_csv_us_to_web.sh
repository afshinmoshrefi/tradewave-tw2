#!/usr/bin/env bash
# Lift per-ticker US CSVs to stage-web so the ticker-page / scorecard /
# home-opportunities generators (web-tier functions in TW1) can read them
# locally — matching TW1 where the web box has the market data.
#
# Source: stage-app /home/flask/data/csv/US/ (lifted there earlier).
# Dest:   stage-web /home/flask/data/csv/US/
# ~1.6 GB; fits stage-web's 20 GB disk. rsync over the Kamatera VLAN.
#
# Run on .176 as root. Uses .176's id_rsa temp-copied to stage-web
# (same trap-wiped pattern as the TW1 migration scripts), because the
# rsync runs ON stage-web pulling from stage-app over VLAN.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

APP_VLAN=10.0.0.92
WEB_HOST=185.53.209.8
SSH_PORT=4369
LOCAL_KEY=/root/.ssh/id_rsa
REMOTE_KEY=/root/.stagesync_key

[[ -r "$LOCAL_KEY" ]] || { echo "No $LOCAL_KEY on .176" >&2; exit 1; }

cleanup() {
    ssh -p "$SSH_PORT" "root@${WEB_HOST}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true
}
trap cleanup EXIT INT TERM HUP

hdr "1. temp key onto stage-web"
scp -P "$SSH_PORT" "$LOCAL_KEY" "root@${WEB_HOST}:${REMOTE_KEY}"
ssh -p "$SSH_PORT" "root@${WEB_HOST}" "chmod 600 $REMOTE_KEY"

hdr "2. rsync csv/US from stage-app → stage-web over VLAN"
ssh -p "$SSH_PORT" "root@${WEB_HOST}" "
  install -d -o flask -g flask -m 755 /home/flask/data /home/flask/data/csv
  rsync -avh --partial --info=progress2 \
    -e 'ssh -i $REMOTE_KEY -p $SSH_PORT -o StrictHostKeyChecking=accept-new' \
    root@${APP_VLAN}:/home/flask/data/csv/US/ \
    /home/flask/data/csv/US/
  chown -R flask:flask /home/flask/data/csv
  du -sh /home/flask/data/csv/US
  df -h /
"

hdr "3. regenerate ticker pages"
ssh -p "$SSH_PORT" "root@${WEB_HOST}" '
  set -a; . /etc/tradewave/secrets.env; set +a
  cd /home/flask/site/ticker_pages
  sudo -u flask -E /home/flask/venv/bin/python generate_ticker_pages.py 2>&1 | tail -15
  echo "--- rendered html count ---"
  ls /var/www/tradewave/patterns/*.html | wc -l
'

echo
echo "=== csv/US lifted + ticker pages regenerated ==="
echo "Verify: https://stage2.trxstat.com/patterns/"
echo "Note: ETF/INDX tickers (SPY/QQQ/GLD/XLF...) still skip — no csv/ETF on staging."
echo "Note: central stockta 403 (104.238.214.253:7771) means no trend score on"
echo "      staging until those IPs are allowlisted there — non-blocking for render."
