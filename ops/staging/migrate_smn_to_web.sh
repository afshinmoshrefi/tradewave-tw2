#!/usr/bin/env bash
# Move SMN article pipeline from stage-app to stage-web (matching TW1).
# Run on .176 as root. Idempotent.
#
# Steps:
#   1. stage-app: stop+disable+remove blog-queue and article-processor units
#   2. stage-web: create /var/www/smn/, install blog-queue + article-processor
#      units, start them
#   3. stage-web: nginx vhost for ${TGT_SMN_HOST} → /var/www/smn/
#   4. stage-web: add ${TGT_SMN_HOST} to existing ${TGT_TUNNEL_WEB} tunnel
#      ingress + DNS CNAME

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APP="$TGT_APP_PUB"
WEB="$TGT_WEB_PUB"
SSH="-p $TGT_SSH_PORT"

hdr "1. stage-app: stop and remove SMN pipeline services"
ssh $SSH "root@$APP" 'bash -s' <<'REMOTE'
set -e
systemctl disable --now tradewave-blog-queue tradewave-article-processor 2>/dev/null || true
rm -f /etc/systemd/system/tradewave-blog-queue.service /etc/systemd/system/tradewave-article-processor.service
systemctl daemon-reload
echo "stage-app SMN services removed"
REMOTE

hdr "2. stage-web: install SMN services + content dir"
ssh $SSH "root@$WEB" 'bash -s' <<'REMOTE'
set -e
install -d -o flask -g flask -m 755 /var/www/smn

cat >/etc/systemd/system/tradewave-blog-queue.service <<'UNIT'
[Unit]
Description=TradeWave SMN blog queue gateway (Flask, port 7171)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=flask
Group=flask
WorkingDirectory=/home/flask/smn
EnvironmentFile=/etc/tradewave/secrets.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/flask/venv/bin/python /home/flask/smn/blog_queue.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/tradewave/blog-queue.log
StandardError=append:/var/log/tradewave/blog-queue.log

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/tradewave-article-processor.service <<'UNIT'
[Unit]
Description=TradeWave SMN article processor (Redis news article queue worker)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=flask
Group=flask
WorkingDirectory=/home/flask/smn
EnvironmentFile=/etc/tradewave/secrets.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/flask/venv/bin/python /home/flask/smn/article_processor.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/tradewave/article-processor.log
StandardError=append:/var/log/tradewave/article-processor.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now tradewave-blog-queue tradewave-article-processor
sleep 2
systemctl --no-pager status tradewave-blog-queue tradewave-article-processor | head -20
echo "stage-web SMN services running"
REMOTE

hdr "3. stage-web: nginx vhost for ${TGT_SMN_HOST}"
ssh $SSH "root@$WEB" "SMN_HOST='$TGT_SMN_HOST' bash -s" <<'REMOTE'
set -e
cat >/etc/nginx/sites-available/smn-stage <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name __SMN_HOST__;

    include /etc/nginx/snippets/security_headers.conf;
    include /etc/nginx/snippets/dotfile_deny.conf;

    root /var/www/smn;
    index index.html;

    client_max_body_size 50M;

    # ACME challenge fallback
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
        allow all;
    }

    # blog-queue (for any local HTTP integrations)
    location /blog-queue/ {
        proxy_pass http://127.0.0.1:7171/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }

    error_page 404 /404.html;
    location = /404.html { root /var/www/smn; internal; }

    location / { try_files $uri $uri/ $uri.html =404; }

    access_log /var/log/nginx/smn-stage.access.log;
    error_log  /var/log/nginx/smn-stage.error.log;
}
NGINX
sed -i "s|__SMN_HOST__|$SMN_HOST|g" /etc/nginx/sites-available/smn-stage

ln -sf /etc/nginx/sites-available/smn-stage /etc/nginx/sites-enabled/smn-stage
nginx -t
systemctl reload nginx
echo "stage-web nginx vhost added"
REMOTE

hdr "4. stage-web: add ${TGT_SMN_HOST} to ${TGT_TUNNEL_WEB} tunnel"
ssh $SSH "root@$WEB" "TUNNEL_WEB='$TGT_TUNNEL_WEB' WEB_HOST='$TGT_WEB_HOST' SMN_HOST='$TGT_SMN_HOST' bash -s" <<'REMOTE'
set -e
# Add DNS CNAME via the existing tunnel
cloudflared tunnel route dns --overwrite-dns "$TUNNEL_WEB" "$SMN_HOST"

# Extend config.yml ingress to include smn-stage hostname (idempotent rewrite)
TUNNEL_ID=$(cloudflared tunnel list | awk -v t="$TUNNEL_WEB" '$2==t {print $1}')
cat >/etc/cloudflared/config.yml <<CFG
tunnel: $TUNNEL_WEB
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: $WEB_HOST
    service: http://localhost:80
  - hostname: $SMN_HOST
    service: http://localhost:80
  - service: http_status:404
CFG
systemctl restart cloudflared
sleep 3
echo "cloudflared updated with smn-stage ingress"
REMOTE

hdr "5. smoke"
sleep 3
curl -sS -o /dev/null -w "external https://${TGT_SMN_HOST}/: %{http_code}\n" "https://${TGT_SMN_HOST}/"
echo "(404 is fine — /var/www/smn/ is empty; pipeline will populate it)"

echo
echo "=== SMN migration complete ==="
echo "Pipeline now runs on stage-web. /var/www/smn/ is empty until the article processor publishes."
