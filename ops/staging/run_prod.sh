#!/usr/bin/env bash
# run_prod.sh — run an ops/staging build script against PROD instead of staging.
#
#   sudo /home/flask/ops/staging/run_prod.sh inventory.sh app
#   sudo /home/flask/ops/staging/run_prod.sh bootstrap_stage_app.sh
#   sudo /home/flask/ops/staging/run_prod.sh bootstrap_stage_app_code.sh app
#   sudo /home/flask/ops/staging/run_prod.sh make_bulletproof.sh
#
# Copies the script to a temp file, applies the fixed staging->prod coordinate
# substitution, then runs it the SAME WAY the staging build runs it:
#
#   * PAYLOAD scripts (apt/useradd/ufw etc. that must execute ON the target
#     box — staging piped them via `ssh root@box 'bash -s' < script`):
#     run_prod.sh pipes the substituted copy to the correct prod box over ssh.
#     Running these locally would wreck the .176 dev box — that is the bug
#     this version fixes.
#   * ORCHESTRATOR scripts (already ssh/scp/rsync OUT to the targets
#     themselves using the now-prod coordinates): executed locally on .176.
#
# inventory.sh and bootstrap_stage_app_code.sh are tier-neutral payloads —
# pass a 2nd arg `app` or `web` to pick the box.
#
# Staging scripts on disk are never modified. Cutover-* scripts are refused
# (separate session, ops/PROD_CUTOVER.md).

set -euo pipefail
DIR=/home/flask/ops/staging
. "$DIR/prod_target.env"   # TGT_APP_PUB / TGT_WEB_PUB / TGT_SSH_PORT (prod)

[[ $# -ge 1 ]] || { echo "usage: run_prod.sh <script.sh> [app|web]" >&2; exit 1; }
SCRIPT="$1"; TIER="${2:-}"
SRC="$DIR/$SCRIPT"
[[ -f "$SRC" ]] || { echo "no such script: $SRC" >&2; exit 1; }
case "$SCRIPT" in
  *cutover*|PROD_CUTOVER*) echo "REFUSING: $SCRIPT is cutover-only (separate session, ops/PROD_CUTOVER.md)." >&2; exit 2;;
esac

# script -> routing
case "$SCRIPT" in
  bootstrap_stage_app.sh|bootstrap_stage_app_services.sh)        MODE=payload; BOX="$TGT_APP_PUB" ;;
  bootstrap_stage_web.sh|bootstrap_stage_web_services.sh)        MODE=payload; BOX="$TGT_WEB_PUB" ;;
  inventory.sh|bootstrap_stage_app_code.sh)
      case "$TIER" in
        app) MODE=payload; BOX="$TGT_APP_PUB" ;;
        web) MODE=payload; BOX="$TGT_WEB_PUB" ;;
        *) echo "ERROR: $SCRIPT is tier-neutral — pass 'app' or 'web' as 2nd arg." >&2; exit 1 ;;
      esac ;;
  *)  MODE=orchestrator ;;
esac

declare -a MAP=(
  "199.244.48.157|138.128.240.115"
  "185.53.209.8|194.113.195.141"
  "10.0.0.92|10.0.0.96"
  "10.0.0.94|10.0.0.98"
  "tw2-stage-app.trxstat.com|tw2-prod-app.trxstat.com"
  "smn-stage.trxstat.com|smn.trxstat.com"
  "stage2.trxstat.com|tw2-prod.trxstat.com"
  "tw2-stage-web|tw2-prod-web"
  "tw2-stage-app|tw2-prod-app"
)
TMP=$(mktemp /tmp/prod_"${SCRIPT%.sh}"_XXXX.sh)
trap 'rm -f "$TMP"' EXIT
cp "$SRC" "$TMP"
SED=(); for p in "${MAP[@]}"; do SED+=(-e "s|${p%%|*}|${p##*|}|g"); done
sed -i "${SED[@]}" "$TMP"

if [[ "$MODE" == payload ]]; then
  echo "=== run_prod[payload]: $SCRIPT -> ssh root@${BOX} -p ${TGT_SSH_PORT} ==="
  exec ssh -p "$TGT_SSH_PORT" -o StrictHostKeyChecking=accept-new "root@${BOX}" 'bash -s' < "$TMP"
else
  echo "=== run_prod[orchestrator]: $SCRIPT (local on .176, ssh/scp/rsync out to prod) ==="
  chmod +x "$TMP"; exec bash "$TMP"
fi
