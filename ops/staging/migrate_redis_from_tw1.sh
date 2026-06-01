#!/usr/bin/env bash
# migrate_redis_from_tw1.sh - Track B: migrate saved-data REDIS from TW1 prod
# appserver db2 into TW2 prod-app db2. Re-uses id_map.jsonl produced by
# migrate_users_from_tw1.sh (so run that with APPLY=1 first).
#
# Run on .176 via run.sh:
#   sudo         /home/flask/ops/staging/run.sh prod migrate_redis_from_tw1.sh   # DRY-RUN
#   sudo APPLY=1 /home/flask/ops/staging/run.sh prod migrate_redis_from_tw1.sh   # commit
#
# Bridge: .176 --ssh--> TW2 prod-app --(temp key, VLAN)--> TW1 prod appserver
# Reads TW1 redis db2 (SCAN/GET only, READ-ONLY on TW1); writes TW2 db2 on prod-app.
# Always passes --overwrite at the cutover - the pre-seed left existing keys
# behind that would otherwise stay stale (import_redis.py:102 SKIPs by default).

set -euo pipefail
hdr(){ printf '\n=== %s ===\n' "$*"; }

. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APPLY="${APPLY:-0}"
APP="$TGT_APP_PUB"; PORT="$TGT_SSH_PORT"
TW1="$TGT_TW1_APP_VLAN"
TW1_PY="${TGT_TW1_PY:-python3}"
REPO=/home/flask
EXPORT_PY="$REPO/ops/migrate/tw1_export.py"
LOCAL_KEY="/root/.ssh/id_rsa"
REMOTE_KEY="/root/.tw1_migration_key"
ID_MAP_LOCAL="/root/tw1_migration/id_map.jsonl"

[[ -r "$LOCAL_KEY" ]]    || { echo "No $LOCAL_KEY on .176." >&2; exit 1; }
[[ -r "$ID_MAP_LOCAL" ]] || { echo "No $ID_MAP_LOCAL on .176 - run migrate_users_from_tw1.sh with APPLY=1 first." >&2; exit 1; }

cleanup(){ ssh -p "$PORT" "root@${APP}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true; }
trap cleanup EXIT

hdr "0. refresh migrate code on TW2 prod-app"
ssh -p "$PORT" "root@${APP}" "sudo -u flask git -C $REPO pull --ff-only --quiet"

hdr "1. push temp key + exporter + id_map to prod-app"
scp -P "$PORT" "$LOCAL_KEY" "root@${APP}:${REMOTE_KEY}"
ssh -p "$PORT" "root@${APP}" "chmod 600 $REMOTE_KEY"
scp -P "$PORT" "$EXPORT_PY" "root@${APP}:/tmp/tw1_export.py"
scp -P "$PORT" "$ID_MAP_LOCAL" "root@${APP}:/tmp/id_map.jsonl"

hdr "2. export redis ON TW1 appserver (db2, READ-ONLY SCAN/GET); pull jsonl to prod-app"
ssh -p "$PORT" "root@${APP}" "bash -s" <<EOF
set -e
SSHK="ssh -n -i $REMOTE_KEY -p $PORT -o StrictHostKeyChecking=accept-new"
SCPK="scp -i $REMOTE_KEY -P $PORT -o StrictHostKeyChecking=accept-new"
mkdir -p /tmp/mig
chmod 777 /tmp/mig
mv /tmp/id_map.jsonl /tmp/mig/id_map.jsonl
\$SCPK /tmp/tw1_export.py root@${TW1}:/tmp/tw1_export.py
\$SSHK root@${TW1} '$TW1_PY /tmp/tw1_export.py redis --redis-db 2 --out-dir /tmp/mig'
\$SCPK root@${TW1}:/tmp/mig/tw1_redis.jsonl /tmp/mig/tw1_redis.jsonl
\$SSHK root@${TW1} 'rm -f /tmp/tw1_export.py /tmp/mig/tw1_redis.jsonl'
rm -f /tmp/tw1_export.py
echo "exported redis keys: \$(wc -l < /tmp/mig/tw1_redis.jsonl)"
EOF

hdr "3. import into TW2 prod-app redis db2 [APPLY=$APPLY] (--overwrite always)"
APPLY_FLAG=""; [[ "$APPLY" == "1" ]] && APPLY_FLAG="--apply"
ssh -p "$PORT" "root@${APP}" "
  sudo -u flask /home/flask/venv/bin/python $REPO/ops/migrate/import_redis.py \
    --redis-in /tmp/mig/tw1_redis.jsonl \
    --id-map /tmp/mig/id_map.jsonl \
    --redis-db 2 --overwrite $APPLY_FLAG
"

echo
if [[ "$APPLY" == "1" ]]; then
  echo "=== redis migration APPLIED with --overwrite. ==="
else
  echo "=== redis migration DRY-RUN (nothing written). Re-run with APPLY=1 to commit. ==="
fi
