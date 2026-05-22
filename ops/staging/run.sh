#!/usr/bin/env bash
# run.sh - run an ops/staging build script against a target environment.
#
#   sudo /home/flask/ops/staging/run.sh staging bootstrap_stage_app.sh
#   sudo /home/flask/ops/staging/run.sh prod    bootstrap_stage_app.sh
#   sudo /home/flask/ops/staging/run.sh prod    inventory.sh app
#   sudo /home/flask/ops/staging/run.sh staging make_staging_secrets.sh
#
# ONE runner for BOTH envs. It picks the per-env coordinate file
#   staging -> target.env        prod -> prod_target.env
# then runs the script the right way for its type:
#
#   * PAYLOAD scripts (apt/useradd/ufw/systemd - must execute ON the target box;
#     staging piped them via `ssh root@box 'bash -s' < script`): the env file is
#     PREPENDED to the script and the combined stream is piped over ssh, so the
#     remote bash defines the TGT_* coordinates first, then runs the script.
#   * ORCHESTRATOR scripts (already ssh/scp/rsync OUT to the targets themselves):
#     run locally on .176 with TGT_ENV_FILE exported; the script sources it.
#
# Scripts reference $TGT_* coordinates ONLY - no hardcoded hostnames/IPs. The two
# env files are the single source of per-env coordinates. This replaces the old
# run_prod.sh sed-rewrite (run_prod.sh is now a thin forwarder to `run.sh prod`).
#
# Cutover-* scripts are refused (separate session, ops/PROD_CUTOVER.md).

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[[ $# -ge 2 ]] || { echo "usage: run.sh {staging|prod} <script.sh> [app|web]" >&2; exit 1; }
ENV="$1"; SCRIPT="$2"; TIER="${3:-}"

case "$ENV" in
  staging) ENVFILE="$DIR/target.env" ;;
  prod)    ENVFILE="$DIR/prod_target.env" ;;
  *) echo "ERROR: env must be 'staging' or 'prod' (got '$ENV')." >&2; exit 1 ;;
esac
SRC="$DIR/$SCRIPT"
[[ -f "$SRC" ]]     || { echo "no such script: $SRC" >&2; exit 1; }
[[ -f "$ENVFILE" ]] || { echo "no such env file: $ENVFILE" >&2; exit 1; }
case "$SCRIPT" in
  *cutover*|PROD_CUTOVER*) echo "REFUSING: $SCRIPT is cutover-only (separate session, ops/PROD_CUTOVER.md)." >&2; exit 2;;
  run.sh|run_prod.sh)      echo "REFUSING: cannot run the runner itself." >&2; exit 2;;
esac

# Load the target coordinates locally so we know which box to ssh to (routing).
# shellcheck source=/dev/null
. "$ENVFILE"

# script -> type/routing
case "$SCRIPT" in
  bootstrap_stage_app.sh|bootstrap_stage_app_services.sh|bootstrap_stage_app_db.sh)  MODE=payload; BOX="$TGT_APP_PUB" ;;
  bootstrap_stage_web.sh|bootstrap_stage_web_services.sh)                            MODE=payload; BOX="$TGT_WEB_PUB" ;;
  inventory.sh|bootstrap_stage_app_code.sh)
      case "$TIER" in
        app) MODE=payload; BOX="$TGT_APP_PUB" ;;
        web) MODE=payload; BOX="$TGT_WEB_PUB" ;;
        *) echo "ERROR: $SCRIPT is tier-neutral - pass 'app' or 'web' as 3rd arg." >&2; exit 1 ;;
      esac ;;
  *)  MODE=orchestrator ;;
esac

if [[ "$MODE" == payload ]]; then
  echo "=== run[$ENV/payload]: $SCRIPT -> ssh root@${BOX} -p ${TGT_SSH_PORT} (coordinates prepended) ==="
  # Remote bash reads: env file (defines TGT_*) then the script body.
  cat "$ENVFILE" "$SRC" | ssh -p "$TGT_SSH_PORT" -o StrictHostKeyChecking=accept-new "root@${BOX}" 'bash -s'
else
  echo "=== run[$ENV/orchestrator]: $SCRIPT (local on .176, ssh/scp/rsync out to $ENV) ==="
  TGT_ENV_FILE="$ENVFILE" bash "$SRC"
fi
