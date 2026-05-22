#!/usr/bin/env bash
# Move stage-app's gunicorn from port 5000 to port 80 (TW1 convention).
# Removes nginx from the app box. Updates stage-web nginx upstream to match.
# Run on .176 as root. Idempotent.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APP="$TGT_APP_PUB"
WEB="$TGT_WEB_PUB"
SSH="-p $TGT_SSH_PORT"

hdr "1. stage-app: rewrite unit to bind :80, grant CAP_NET_BIND_SERVICE, disable nginx"
ssh $SSH "root@$APP" "APP_VLAN='$TGT_APP_VLAN' bash -s" <<'REMOTE'
set -e

# UNIT delimiter is UNquoted so the remote shell substitutes $APP_VLAN at
# file-write time; the unit body has no other shell-expandable tokens.
cat >/etc/systemd/system/tradewave-appserver.service <<UNIT
[Unit]
Description=TradeWave 2.0 appserver (gunicorn on :80, TW1 convention)
After=network.target redis-server.service postgresql.service
Wants=redis-server.service postgresql.service

[Service]
Type=notify
User=flask
Group=flask
WorkingDirectory=/home/flask/appserver/appserver
EnvironmentFile=/etc/tradewave/secrets.env
Environment=PYTHONPATH=/home/flask:/home/flask/appserver/appserver
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ExecStart=/home/flask/venv/bin/gunicorn --workers 2 --worker-class sync --timeout 120 --bind 127.0.0.1:80 --bind ${APP_VLAN}:80 --access-logfile /var/log/tradewave/appserver.access.log --error-logfile /var/log/tradewave/appserver.error.log --capture-output appserver:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

# Drop any stale override files from the previous attempt
rm -f /etc/systemd/system/tradewave-appserver.service.d/lowport.conf
rmdir /etc/systemd/system/tradewave-appserver.service.d 2>/dev/null || true

systemctl disable --now nginx 2>/dev/null || true
systemctl daemon-reload
systemctl restart tradewave-appserver
sleep 3
ss -tlnp | grep -E ':80\b' || { echo "FAIL: gunicorn not on :80"; tail -30 /var/log/tradewave/appserver.error.log; exit 1; }
echo "stage-app gunicorn on :80"
REMOTE

hdr "2. stage-web: nginx upstream to ${TGT_APP_VLAN}:80"
ssh $SSH "root@$WEB" "APP_VLAN='$TGT_APP_VLAN' WEB_NGINX_SITE='$TGT_WEB_NGINX_SITE' bash -s" <<'REMOTE'
set -e
sed -i "s|server $APP_VLAN:5000|server $APP_VLAN:80|" "/etc/nginx/sites-available/$WEB_NGINX_SITE"
grep -q "server $APP_VLAN:80" "/etc/nginx/sites-available/$WEB_NGINX_SITE" || { echo "FAIL: upstream rewrite didn't take"; exit 1; }
nginx -t
systemctl reload nginx
echo "stage-web nginx reloaded"
REMOTE

hdr "3. smoke"
sleep 2
curl -sS -o /dev/null -w "external https://${TGT_APP_HOST}/: %{http_code}\n" "https://${TGT_APP_HOST}/"
curl -sS -o /dev/null -w 'web→app via VLAN /appserver/: %{http_code}\n' "https://${TGT_WEB_HOST}/appserver/"

echo
echo "=== port-80 migration complete ==="
