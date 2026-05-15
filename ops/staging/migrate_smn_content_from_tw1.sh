#!/usr/bin/env bash
# Migrate SMN article content from TW1 prod web (10.0.0.40 on Kamatera VLAN)
# to TW2 stage-web (10.0.0.94 on the same VLAN). Uses .176's existing
# /root/.ssh/id_rsa (already authorized on TW1 prod) by copying it briefly
# to stage-web, running the rsync, then wiping it.
#
# rsync runs ON stage-web pulling from TW1 prod over the internal Kamatera VLAN.
#
# Run on .176 as root.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# ---------------------------- config ---------------------------------
TW1_VLAN_IP="10.0.0.40"
TW1_USER="root"
TW1_PORT="4369"
TW1_SMN_DIR="/var/www/smn/"

WEB_HOST="185.53.209.8"
WEB_SSH_PORT="4369"
WEB_SMN_DIR="/var/www/smn/"

LOCAL_KEY="/root/.ssh/id_rsa"
REMOTE_KEY="/root/.tw1_migration_key"   # tempfile on stage-web; wiped at end
# ---------------------------------------------------------------------

[[ -r "$LOCAL_KEY" ]] || { echo "No $LOCAL_KEY on .176 (need the shared TW1-auth key)." >&2; exit 1; }

cleanup() {
    ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true
}
# SIGKILL bypasses traps, but INT/TERM/HUP we can catch — at least don't
# leak the key on Ctrl+C or session disconnect.
trap cleanup EXIT INT TERM HUP

hdr "1. push key to stage-web (temp)"
scp -P "$WEB_SSH_PORT" "$LOCAL_KEY" "root@${WEB_HOST}:${REMOTE_KEY}"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "chmod 600 $REMOTE_KEY"

hdr "2. test stage-web → TW1 prod over VLAN"
TEST=$(ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" \
    "ssh -n -i $REMOTE_KEY -o StrictHostKeyChecking=accept-new -o BatchMode=yes -p $TW1_PORT ${TW1_USER}@${TW1_VLAN_IP} 'echo OK'")
[[ "$TEST" == "OK" ]] || { echo "FAIL: stage-web → TW1 prod ssh failed"; exit 1; }
echo "stage-web → TW1 prod ssh: OK"

hdr "3. dry-run rsync"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "
  rsync -avh --dry-run --partial \
    --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
    -e 'ssh -i $REMOTE_KEY -p $TW1_PORT -o StrictHostKeyChecking=accept-new' \
    ${TW1_USER}@${TW1_VLAN_IP}:${TW1_SMN_DIR} \
    ${WEB_SMN_DIR}
" | tail -25

read -r -p "Proceed with the real copy? [y/N] " yn
[[ "$yn" =~ ^[Yy]$ ]] || { echo "aborted"; exit 0; }

hdr "4. real rsync"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "
  rsync -avh --partial --info=progress2 \
    --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
    -e 'ssh -i $REMOTE_KEY -p $TW1_PORT -o StrictHostKeyChecking=accept-new' \
    ${TW1_USER}@${TW1_VLAN_IP}:${TW1_SMN_DIR} \
    ${WEB_SMN_DIR}
"

hdr "5. chown + chmod"
ssh -p "$WEB_SSH_PORT" "root@${WEB_HOST}" "
  chown -R flask:flask ${WEB_SMN_DIR}
  find ${WEB_SMN_DIR} -type d -exec chmod 755 {} +
  find ${WEB_SMN_DIR} -type f -exec chmod 644 {} +
  du -sh ${WEB_SMN_DIR}
"

echo
echo "=== SMN content migration complete ==="
echo "Verify:  curl -sS https://smn-stage.trxstat.com/ | head"
echo "Key wiped from stage-web (trap on EXIT)."
