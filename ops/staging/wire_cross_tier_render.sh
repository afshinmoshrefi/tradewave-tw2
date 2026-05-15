#!/usr/bin/env bash
# Wire stage-web's :5500 so stage-app's appserver can POST render requests
# to /internal/render_report. Pulls latest code on both boxes and restarts.
# Run on .176 as root.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

APP=199.244.48.157
WEB=185.53.209.8
SSH="-p 4369"

hdr "1. stage-web: rebind gunicorn web to also listen on 10.0.0.94:5500"
ssh $SSH "root@$WEB" 'bash -s' <<'REMOTE'
set -e
sed -i 's|--bind 127.0.0.1:5500|--bind 127.0.0.1:5500 --bind 10.0.0.94:5500|' /etc/systemd/system/tradewave-web.service
grep '\-\-bind' /etc/systemd/system/tradewave-web.service
ufw allow from 10.0.0.92 to any port 5500 comment 'render report from app box' || true
ufw status numbered | grep 5500 || true
REMOTE

hdr "2. stage-web: pull + restart web"
ssh $SSH "root@$WEB" 'sudo -u flask git -C /home/flask pull --ff-only origin main && systemctl daemon-reload && systemctl restart tradewave-web && sleep 2 && ss -tlnp | grep :5500'

hdr "3. stage-app: pull + restart appserver"
ssh $SSH "root@$APP" 'sudo -u flask git -C /home/flask pull --ff-only origin main && systemctl restart tradewave-appserver && sleep 2 && systemctl is-active tradewave-appserver'

hdr "4. smoke: appserver → web tier /internal/render_report"
ssh $SSH "root@$APP" '
  set -a; . /etc/tradewave/secrets.env; set +a
  curl -sS -o /dev/null -w "render endpoint reachable from app→web: %{http_code} (401 means unauth headers, 400 missing field, 200 queued)\n" \
    -X POST http://10.0.0.94:5500/internal/render_report
'

echo
echo "=== cross-tier render wired ==="
echo "Try saving a pattern to portfolio again — check /home/flask/appserver/appserver/add_to_blog_queue.log on stage-app for RENDER-* lines"
