#!/usr/bin/env bash
# Wire the web box's :5500 so the app box's appserver can POST render requests
# to /internal/render_report. Pulls latest code on both boxes and restarts.
# Run on .176 as root via ops/staging/run.sh {staging|prod}.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APP="$TGT_APP_PUB"
WEB="$TGT_WEB_PUB"
SSH="-p $TGT_SSH_PORT"

hdr "1. web box: install the tracked loopback + VLAN gunicorn unit"
# Render from the repository source rather than mutating an installed unit in place.
ssh $SSH "root@$WEB" "WEB_VLAN='$TGT_WEB_VLAN' APP_VLAN='$TGT_APP_VLAN' bash -s" <<'REMOTE'
set -euo pipefail
src=/home/flask/ops/systemd/tradewave-web.service
[ -r "$src" ] || { echo "FAIL: missing $src (sync the release first)" >&2; exit 1; }
sed "s|__TW2_WEB_VLAN__|$WEB_VLAN|g" "$src" >/etc/systemd/system/tradewave-web.service
grep -q -- "--bind 127.0.0.1:5500" /etc/systemd/system/tradewave-web.service
grep -q -- "--bind $WEB_VLAN:5500" /etc/systemd/system/tradewave-web.service
ufw allow from $APP_VLAN to any port 5500 comment 'render report from app box' || true
ufw status numbered | grep 5500 || true
REMOTE

hdr "2. web box: pull + restart web"
ssh $SSH "root@$WEB" 'sudo -u flask git -C /home/flask pull --ff-only origin main && systemctl daemon-reload && systemctl restart tradewave-web && sleep 2 && ss -tlnp | grep :5500'

hdr "3. app box: pull + restart appserver"
ssh $SSH "root@$APP" 'sudo -u flask git -C /home/flask pull --ff-only origin main && systemctl restart tradewave-appserver && sleep 2 && systemctl is-active tradewave-appserver'

hdr "4. smoke: appserver → web tier /internal/render_report"
ssh $SSH "root@$APP" "WEB_VLAN='$TGT_WEB_VLAN' bash -s" <<'REMOTE'
set -a; . /etc/tradewave/secrets.env; set +a
curl -sS -o /dev/null -w "render endpoint reachable from app->web: %{http_code} (401 means unauth headers, 400 missing field, 200 queued)\n" \
  -X POST "http://$WEB_VLAN:5500/internal/render_report"
REMOTE

echo
echo "=== cross-tier render wired ==="
echo "Try saving a pattern to portfolio again — check /home/flask/appserver/appserver/add_to_blog_queue.log on the app box for RENDER-* lines"
