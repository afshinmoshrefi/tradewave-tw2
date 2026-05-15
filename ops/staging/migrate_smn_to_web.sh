#!/usr/bin/env bash
# Move SMN article pipeline from stage-app to stage-web (matching TW1).
# Run on .176 as root. Idempotent.
#
# Steps:
#   1. stage-app: stop+disable+remove blog-queue and article-processor units
#   2. stage-web: create /var/www/smn/, install blog-queue + article-processor
#      units, start them
#   3. stage-web: nginx vhost for smn-stage.trxstat.com → /var/www/smn/
#   4. stage-web: add smn-stage.trxstat.com to existing tw2-stage-web tunnel
#      ingress + DNS CNAME

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

APP=199.244.48.157
WEB=185.53.209.8
SSH="-p 4369"

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

hdr "3. stage-web: nginx vhost for smn-stage.trxstat.com"
ssh $SSH "root@$WEB" 'bash -s' <<'REMOTE'
set -e
cat >/etc/nginx/sites-available/smn-stage <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name smn-stage.trxstat.com;

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

ln -sf /etc/nginx/sites-available/smn-stage /etc/nginx/sites-enabled/smn-stage
nginx -t
systemctl reload nginx
echo "stage-web nginx vhost added"
REMOTE

hdr "4. stage-web: add smn-stage.trxstat.com to tw2-stage-web tunnel"
ssh $SSH "root@$WEB" 'bash -s' <<'REMOTE'
set -e
# Add DNS CNAME via the existing tunnel
cloudflared tunnel route dns --overwrite-dns tw2-stage-web smn-stage.trxstat.com

# Extend config.yml ingress to include smn-stage hostname (idempotent rewrite)
TUNNEL_ID=$(cloudflared tunnel list | awk '$2=="tw2-stage-web" {print $1}')
cat >/etc/cloudflared/config.yml <<CFG
tunnel: tw2-stage-web
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: stage2.trxstat.com
    service: http://localhost:80
  - hostname: smn-stage.trxstat.com
    service: http://localhost:80
  - service: http_status:404
CFG
systemctl restart cloudflared
sleep 3
echo "cloudflared updated with smn-stage ingress"
REMOTE

hdr "5. smoke"
sleep 3
curl -sS -o /dev/null -w 'external https://smn-stage.trxstat.com/: %{http_code}\n' https://smn-stage.trxstat.com/
echo "(404 is fine — /var/www/smn/ is empty; pipeline will populate it)"

echo
echo "=== SMN migration complete ==="
echo "Pipeline now runs on stage-web. /var/www/smn/ is empty until the article processor publishes."
