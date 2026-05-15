#!/usr/bin/env bash
# Migrate scorecard data (featured_history.json) from TW1 prod to TW2 stage-web,
# then regenerate /var/www/tradewave/scorecard.html with current live prices.
#
# Run on .176 as root. Idempotent.
#
# Approach: same as migrate_smn_content_from_tw1 — copy .176's existing
# /root/.ssh/id_rsa to stage-web briefly, run rsync over the Kamatera VLAN
# (stage-web ↔ TW1 prod at 10.0.0.40), wipe the temp key on exit.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

TW1_VLAN_IP="10.0.0.40"
TW1_USER="root"
TW1_PORT="4369"
TW1_SRC="/home/flask/blog/featured_history.json"

WEB_HOST="185.53.209.8"
WEB_SSH_PORT="4369"
WEB_DST="/home/flask/site/data/featured_history.json"

LOCAL_KEY="/root/.ssh/id_rsa"
REMOTE_KEY="/root/.tw1_migration_key"

[[ -r "$LOCAL_KEY" ]] || { echo "No $LOCAL_KEY on .176." >&2; exit 1; }

cleanup() {
    ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true
}
# SIGKILL bypasses traps, but INT/TERM/HUP we can catch.
trap cleanup EXIT INT TERM HUP

hdr "1. push key to stage-web (temp)"
scp -P "$WEB_SSH_PORT" "$LOCAL_KEY" "root@${WEB_HOST}:${REMOTE_KEY}"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "chmod 600 $REMOTE_KEY"

hdr "2. rsync featured_history.json from TW1 prod"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "
  install -d -o flask -g flask -m 755 /home/flask/site/data
  rsync -avh \
    -e 'ssh -i $REMOTE_KEY -p $TW1_PORT -o StrictHostKeyChecking=accept-new' \
    ${TW1_USER}@${TW1_VLAN_IP}:${TW1_SRC} \
    ${WEB_DST}
  chown flask:flask ${WEB_DST}
  chmod 644 ${WEB_DST}
  ls -la ${WEB_DST}
  /home/flask/venv/bin/python -c \"import json; print('entries:', len(json.load(open('${WEB_DST}'))))\"
"

hdr "3. regenerate scorecard.html on stage-web"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "
  set -a; . /etc/tradewave/secrets.env; set +a
  cd /home/flask/site && sudo -u flask -E /home/flask/venv/bin/python generate_scorecard.py 2>&1 | tail -10
  ls -la /var/www/tradewave/scorecard.html
"

echo
echo "=== scorecard migration complete ==="
echo "Verify: https://stage2.trxstat.com/scorecard.html"
echo "For prod cutover: change WEB_HOST/WEB_SSH_PORT to prod-web and re-run."
