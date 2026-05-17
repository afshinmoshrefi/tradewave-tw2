#!/usr/bin/env bash
# run_prod.sh — run any ops/staging build script against PROD instead of staging.
#
#   sudo /home/flask/ops/staging/run_prod.sh bootstrap_stage_app.sh
#   sudo /home/flask/ops/staging/run_prod.sh make_bulletproof.sh
#
# How: copies the target script to a temp file, applies the fixed staging->prod
# coordinate substitution (derived from target.env vs prod_target.env), and
# executes that. The staging scripts on disk are NEVER modified — staging keeps
# working byte-identical, zero regression risk, and prod is a pure parameter
# flip (not a fork). Any extra args after the script name are passed through.
#
# This is the Phase-0 prod build mechanism. The tradewave.ai cutover is a
# SEPARATE session via ops/PROD_CUTOVER.md and is NOT run through here.

set -euo pipefail
DIR=/home/flask/ops/staging

[[ $# -ge 1 ]] || { echo "usage: run_prod.sh <script.sh> [args...]" >&2; exit 1; }
SCRIPT="$1"; shift
SRC="$DIR/$SCRIPT"
[[ -f "$SRC" ]] || { echo "no such script: $SRC" >&2; exit 1; }

case "$SCRIPT" in
  *cutover*|PROD_CUTOVER*)
    echo "REFUSING: $SCRIPT is cutover-only — run it from the dedicated cutover session per ops/PROD_CUTOVER.md, not via run_prod.sh." >&2
    exit 2;;
esac

# staging literal  ->  prod literal   (keep in sync with {,prod_}target.env)
declare -a MAP=(
  "199.244.48.157|138.128.240.115"      # app public
  "185.53.209.8|194.113.195.141"        # web public
  "10.0.0.92|10.0.0.96"                  # app VLAN
  "10.0.0.94|10.0.0.98"                  # web VLAN
  "stage2.trxstat.com|tw2-prod.trxstat.com"            # web host (placeholder)
  "tw2-stage-app.trxstat.com|tw2-prod-app.trxstat.com" # app host
  "smn-stage.trxstat.com|smn.trxstat.com"              # SMN host (CONFIRM)
  "tw2-stage-web|tw2-prod-web"           # web tunnel name
  "tw2-stage-app|tw2-prod-app"           # app tunnel name
)
# NOTE order matters: longer/host tokens before substrings. tw2-stage-app.trxstat.com
# is substituted before the bare tw2-stage-app tunnel token; sed runs the list in order.

TMP=$(mktemp /tmp/prod_"${SCRIPT%.sh}"_XXXX.sh)
trap 'rm -f "$TMP"' EXIT
cp "$SRC" "$TMP"

SED_ARGS=()
for pair in "${MAP[@]}"; do
  s="${pair%%|*}"; p="${pair##*|}"
  SED_ARGS+=(-e "s|${s}|${p}|g")
done
sed -i "${SED_ARGS[@]}" "$TMP"

echo "=== run_prod: $SCRIPT  (staging->prod coordinates applied) ==="
echo "    app  138.128.240.115 / vlan 10.0.0.96"
echo "    web  194.113.195.141 / vlan 10.0.0.98  (placeholder tw2-prod.trxstat.com)"
echo "    diff vs staging original:"
diff <(grep -nE '138\.128|194\.113|10\.0\.0\.9[68]|tw2-prod' "$TMP" || true) /dev/null | sed 's/^/      /' | head -20 || true
echo "=== executing ==="
chmod +x "$TMP"
exec bash "$TMP" "$@"
