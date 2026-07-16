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

hdr "1. app box: install tracked unit, bind :80, disable nginx"
ssh $SSH "root@$APP" "APP_VLAN='$TGT_APP_VLAN' APP_WORKERS='$TGT_APP_WORKERS' APP_THREADS='$TGT_APP_THREADS' APP_NGINX_SITE='$TGT_APP_NGINX_SITE' bash -s" <<'REMOTE'
set -e

install -m 0644 /home/flask/ops/systemd/tradewave-appserver.service \
    /etc/systemd/system/tradewave-appserver.service
install -d -m 0750 /etc/tradewave
cat >/etc/tradewave/appserver.env <<ENV
TW2_APPSERVER_BIND=0.0.0.0:80
TW2_APPSERVER_WORKERS=${APP_WORKERS}
TW2_APPSERVER_THREADS=${APP_THREADS}
ENV
chmod 0640 /etc/tradewave/appserver.env
chown root:flask /etc/tradewave/appserver.env

# Drop any stale override files from the previous attempt
rm -f /etc/systemd/system/tradewave-appserver.service.d/lowport.conf
rmdir /etc/systemd/system/tradewave-appserver.service.d 2>/dev/null || true

rm -f "/etc/nginx/sites-enabled/$APP_NGINX_SITE"
systemctl disable --now nginx 2>/dev/null || true
systemctl daemon-reload
systemctl restart tradewave-appserver
sleep 3
ss -tlnp | grep -E ':80\b' || { echo "FAIL: gunicorn not on :80"; tail -30 /var/log/tradewave/appserver.error.log; exit 1; }
echo "appserver gunicorn on :80 with ${APP_WORKERS}x${APP_THREADS} gthread capacity"
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
