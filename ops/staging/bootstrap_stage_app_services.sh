#!/usr/bin/env bash
# TW2 staging APP-box systemd + nginx (HTTP only).
# Run after schema + data lift are done.
# Usage (env-driven runner prepends the target coordinates):
#   ops/staging/run.sh {staging|prod} bootstrap_stage_app_services.sh
#
# What this does:
#   1. Write 3 systemd unit files: appserver, blog-queue, article-processor.
#      Post-resize appserver defaults to the audited 4 workers x 4 threads.
#   2. Write nginx vhost for ${TGT_APP_HOST} → 127.0.0.1:5000 (port 80).
#      TLS deferred to bootstrap_stage_app_tls.sh.
#   3. systemctl daemon-reload, enable, start everything.
#   4. nginx -t, reload.
#   5. Quick smoke: curl localhost:5000/api/me, curl localhost/.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# PAYLOAD: run via ops/staging/run.sh {staging|prod}, which prepends the target
# coordinates (TGT_*). Fail clearly if invoked directly without them.
: "${TGT_APP_HOST:?run via ops/staging/run.sh - it prepends the target coordinates}"
[ -r /etc/tradewave/secrets.env ] || { echo "FAIL: secrets.env missing" >&2; exit 1; }
grep -q '^TW2_FEATURED_HISTORY_URL=http.*:5500/internal/featured-history$' /etc/tradewave/secrets.env || {
    echo "FAIL: TW2_FEATURED_HISTORY_URL must target the WEB VLAN :5500 private feed" >&2
    exit 1
}

hdr "1. write systemd units"

install -m 0644 /home/flask/ops/systemd/tradewave-appserver.service \
    /etc/systemd/system/tradewave-appserver.service
install -d -m 0750 /etc/tradewave
cat >/etc/tradewave/appserver.env <<ENV
TW2_APPSERVER_BIND=127.0.0.1:5000
TW2_APPSERVER_WORKERS=${TGT_APP_WORKERS}
TW2_APPSERVER_THREADS=${TGT_APP_THREADS}
ENV
chmod 0640 /etc/tradewave/appserver.env
chown root:flask /etc/tradewave/appserver.env

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

echo "  installed the appserver unit and wrote 2 queue unit files"

hdr "2. nginx vhost for ${TGT_APP_HOST} (HTTP only — TLS later)"

# Install the query-free named log format before nginx parses the vhost.
install -d -m 0755 /etc/nginx/conf.d
install -m 0644 /home/flask/ops/nginx/conf.d/tradewave-log-format.conf \
    /etc/nginx/conf.d/tradewave-log-format.conf

# Disable default vhost so our vhost wins for unknown server_name lookups.
rm -f /etc/nginx/sites-enabled/default

cat >"/etc/nginx/sites-available/$TGT_APP_NGINX_SITE" <<'NGINX'
upstream tw2_appserver {
    server 127.0.0.1:5000;
    keepalive 16;
}

# Reject any request that arrives on this box with a Host other than the
# expected one (Cloudflare scrapers, bare-IP probes, etc.). Fail closed.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}

server {
    listen 80;
    listen [::]:80;
    server_name __APP_HOST__;

    client_max_body_size 50M;

    # ACME challenge for Let's Encrypt (used by certbot --nginx). Allow even
    # if the rest is locked down, so cert renewal can complete.
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
        allow all;
    }

    # Health endpoint
    location = /healthz {
        return 200 "stage-app ok\n";
        add_header Content-Type text/plain;
    }

    # Everything else → gunicorn appserver
    location / {
        proxy_pass http://tw2_appserver;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_connect_timeout 10s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    access_log /var/log/nginx/tradewave-appserver.access.log tw_noargs;
    error_log  /var/log/nginx/tradewave-appserver.error.log;
}
NGINX

# Fill the placeholder the quoted NGINX heredoc could not expand.
sed -i "s|__APP_HOST__|$TGT_APP_HOST|g" "/etc/nginx/sites-available/$TGT_APP_NGINX_SITE"
ln -sf "/etc/nginx/sites-available/$TGT_APP_NGINX_SITE" "/etc/nginx/sites-enabled/$TGT_APP_NGINX_SITE"
install -d -o www-data -g www-data /var/www/html

hdr "3. daemon-reload + enable + start"
systemctl daemon-reload
systemctl enable --now tradewave-appserver
systemctl enable --now tradewave-blog-queue
systemctl enable --now tradewave-article-processor

# Give appserver a moment to bind
sleep 3

systemctl --no-pager status tradewave-appserver tradewave-blog-queue tradewave-article-processor | head -40

hdr "4. nginx -t + reload"
nginx -t
systemctl reload nginx || systemctl restart nginx
systemctl --no-pager status nginx | head -8

hdr "5. smoke"
echo "[gunicorn direct] $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/healthz 2>/dev/null || echo 'no /healthz route') (200 means appserver alive)"
echo "[gunicorn /api/me] $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/api/me)  (404 expected here — /api/me is web tier)"
echo "[nginx /healthz]   $(curl -sS -o /dev/null -w '%{http_code}' -H "Host: $TGT_APP_HOST" http://127.0.0.1/healthz)"
echo "[bare-IP scrape]   $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1/)  (444 expected — Host filter)"
echo "[blog-queue]       $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7171/  || true)"

ss -tlnp | grep -E ':5000|:7171|:80 ' || true

echo
echo "=== app-box services + http nginx complete ==="
echo "Next:"
echo "  - From your laptop:   curl -H 'Host: ${TGT_APP_HOST}' http://${TGT_APP_PUB}/healthz   (should return 'stage-app ok')"
echo "  - Once DNS for ${TGT_APP_HOST} points at ${TGT_APP_PUB}, set up TLS via certbot or cloudflared."
