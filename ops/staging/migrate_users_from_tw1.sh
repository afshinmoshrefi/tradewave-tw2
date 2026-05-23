#!/usr/bin/env bash
# migrate_users_from_tw1.sh - Track A: migrate USERS (customers) from TW1 prod
# into the TW2 Postgres `users` table.
#
# Run on .176 via the standard runner (NOT directly):
#   sudo         /home/flask/ops/staging/run.sh prod migrate_users_from_tw1.sh   # DRY-RUN
#   sudo APPLY=1 /home/flask/ops/staging/run.sh prod migrate_users_from_tw1.sh   # commit
#
# DRY-RUN writes NOTHING to TW2 (import rolls back Postgres; Stripe calls are
# read-only) and pulls payer_report.txt + id_map.jsonl back to .176 for review.
# APPLY=1 commits the idempotent, never-downgrade upsert. Safe to re-run - re-run
# as a delta right before the cutover.
#
# .176 cannot reach TW1 directly; only the TW2 boxes can over the Kamatera VLAN.
# So this uses the same temp-key bridge as migrate_scorecard_from_tw1.sh:
#   .176 --ssh--> TW2 prod-web --(temp key, VLAN)--> TW1 prod web
# Roster (MySQL) + levels (UMP api-gate) are read ON TW1 web; the import
# (Postgres + LIVE Stripe) runs ON TW2 prod-web.
#
# Needs these TW1 coordinates set in the env file (CONFIRM the placeholders):
#   TGT_TW1_PROD_VLAN  TGT_TW1_KEYSTORE_URL  TGT_TW1_WP_HOST
#   TGT_TW1_WP_URL  TGT_TW1_WP_CONFIG  TGT_TW1_PY  [TGT_TW1_LEGACY_PRICE_MAP]

set -euo pipefail
hdr(){ printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (run.sh sets TGT_ENV_FILE; defaults to staging's target.env).
# shellcheck source=/dev/null
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APPLY="${APPLY:-0}"
WEB="$TGT_WEB_PUB"; PORT="$TGT_SSH_PORT"
TW1="$TGT_TW1_PROD_VLAN"                                  # TW1 prod WEB (WordPress/MySQL)
KEYSTORE="${TGT_TW1_KEYSTORE_URL:?set TGT_TW1_KEYSTORE_URL in the env file}"
WPHOST="${TGT_TW1_WP_HOST:?set TGT_TW1_WP_HOST (TW1 WP server_name) in the env file}"
WPURL="${TGT_TW1_WP_URL:-http://localhost/}"
WPCONF="${TGT_TW1_WP_CONFIG:-/var/www/html/wordpress/wp-config.php}"
TW1_PY="${TGT_TW1_PY:-python3}"
PRICE_MAP="${TGT_TW1_LEGACY_PRICE_MAP:-}"

REPO=/home/flask
EXPORT_PY="$REPO/ops/migrate/tw1_export.py"
LOCAL_KEY="/root/.ssh/id_rsa"
REMOTE_KEY="/root/.tw1_migration_key"
OUT_LOCAL="${OUT_LOCAL:-/root/tw1_migration}"

[[ -r "$LOCAL_KEY" ]] || { echo "No $LOCAL_KEY on .176." >&2; exit 1; }
[[ -r "$EXPORT_PY" ]] || { echo "missing $EXPORT_PY (git pull on .176?)" >&2; exit 1; }

cleanup(){ ssh -p "$PORT" "root@${WEB}" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" || true; }
trap cleanup EXIT INT TERM HUP

hdr "0. refresh migrate code on TW2 prod-web"
ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "root@${WEB}" "sudo -u flask git -C $REPO pull --ff-only"

hdr "1. push temp key + the exporter to prod-web"
scp -P "$PORT" "$LOCAL_KEY" "root@${WEB}:${REMOTE_KEY}"
scp -P "$PORT" "$EXPORT_PY" "root@${WEB}:/tmp/tw1_export.py"
ssh -p "$PORT" "root@${WEB}" "chmod 600 $REMOTE_KEY"

hdr "2. export users ON TW1 web (roster=MySQL, levels=UMP api-gate); pull jsonl to prod-web"
# heredoc runs on prod-web; .176 expands the TGT_* coordinates into it first.
# shellcheck disable=SC2087  # intentional: expand TGT_* on .176; prod-web-side vars are escaped \$
ssh -p "$PORT" "root@${WEB}" "bash -s" <<EOF
set -e
SSHK="ssh -i $REMOTE_KEY -p $PORT -o StrictHostKeyChecking=accept-new"
SCPK="scp -i $REMOTE_KEY -P $PORT -o StrictHostKeyChecking=accept-new"
mkdir -p /tmp/mig
\$SCPK /tmp/tw1_export.py root@${TW1}:/tmp/tw1_export.py
\$SSHK root@${TW1} '$TW1_PY /tmp/tw1_export.py users --wp-config "$WPCONF" --keystore-url "$KEYSTORE" --wordpress-url "$WPURL" --host-header "$WPHOST" --out-dir /tmp/mig'
\$SCPK root@${TW1}:/tmp/mig/tw1_users.jsonl /tmp/mig/tw1_users.jsonl
\$SSHK root@${TW1} 'rm -f /tmp/tw1_export.py /tmp/mig/tw1_users.jsonl'
rm -f /tmp/tw1_export.py
echo "exported rows: \$(wc -l < /tmp/mig/tw1_users.jsonl)"
EOF

hdr "3. import into TW2 Postgres on prod-web (LIVE Stripe) [APPLY=$APPLY]"
APPLY_FLAG=""; [[ "$APPLY" == "1" ]] && APPLY_FLAG="--apply"
MAP_FLAG="";   [[ -n "$PRICE_MAP" ]] && MAP_FLAG="--legacy-price-map $PRICE_MAP"
ssh -p "$PORT" "root@${WEB}" "
  set -a; . /etc/tradewave/secrets.env; set +a
  sudo -u flask -E /home/flask/venv/bin/python $REPO/ops/migrate/import_users.py \
    --in /tmp/mig/tw1_users.jsonl --out-dir /tmp/mig $APPLY_FLAG $MAP_FLAG
"

hdr "4. pull payer_report + id_map back to .176 for review"
mkdir -p "$OUT_LOCAL"
scp -P "$PORT" "root@${WEB}:/tmp/mig/payer_report.txt" "$OUT_LOCAL/" 2>/dev/null || true
scp -P "$PORT" "root@${WEB}:/tmp/mig/id_map.jsonl"     "$OUT_LOCAL/" 2>/dev/null || true

echo
if [[ "$APPLY" == "1" ]]; then
  echo "=== users migration APPLIED. id_map -> $OUT_LOCAL/id_map.jsonl (feeds migrate_redis_from_tw1.sh). ==="
else
  echo "=== users migration DRY-RUN (nothing written). Review $OUT_LOCAL/payer_report.txt, then: sudo APPLY=1 run.sh prod migrate_users_from_tw1.sh ==="
fi