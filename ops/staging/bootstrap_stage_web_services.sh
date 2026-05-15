#!/usr/bin/env bash
# TW2 staging WEB-box systemd + nginx (HTTP only).
# Run after code + secrets + content lift are done.
# Usage:
#   ssh root@185.53.209.8 -p 4369 'bash -s' < bootstrap_stage_web_services.sh
#
# What this does:
#   1. systemd unit for tradewave-web (gunicorn :5500, 2 workers — RAM constraint)
#   2. 3 nginx snippets (security_headers, dotfile_deny, tw2-proxy-headers)
#   3. nginx vhost for stage2.trxstat.com:
#        - Marketing site (static from /var/www/tradewave/)
#        - /app/, /app/index.html → web tier (index injection); /app/static/* → React build
#        - /api/, /auth/, /webhooks/, /admin/, /signup, /login, /logout, /account, /pricing,
#          /stripe/, /healthz → web tier on 127.0.0.1:5500
#        - /appserver/ → stage-app over VLAN (http://10.0.0.92:5000/), faster than going through
#          stage-app's cloudflared tunnel
#        - default vhost returns 444 for bare-IP / wrong-Host probes
#   4. Start tradewave-web, reload nginx, smoke

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

hdr "1. systemd unit"
cat >/etc/systemd/system/tradewave-web.service <<'UNIT'
[Unit]
Description=TradeWave 2.0 web tier (auth + admin + Stripe)
After=network.target

[Service]
Type=simple
User=flask
Group=flask
WorkingDirectory=/home/flask/web
EnvironmentFile=/etc/tradewave/secrets.env
Environment=PYTHONPATH=/home/flask:/home/flask/web
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/log/tradewave /var/www/tradewave /var/www/smn /home/flask/web /home/flask/site/data
ProtectHome=read-only
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ExecStart=/home/flask/venv/bin/gunicorn \
    --workers 2 \
    --worker-class sync \
    --timeout 60 \
    --bind 127.0.0.1:5500 \
    --access-logfile /var/log/tradewave/web.access.log \
    --error-logfile /var/log/tradewave/web.error.log \
    --capture-output \
    app:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

hdr "2. nginx snippets"
install -d -m 755 /etc/nginx/snippets

cat >/etc/nginx/snippets/security_headers.conf <<'SNIP'
# TW2 staging shared HTTP security headers.
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "interest-cohort=(), camera=(), microphone=(), geolocation=(), payment=(self \"https://checkout.stripe.com\")" always;
# CSP allow-list:
#   - Cloudflare Insights beacon (auto-injected by CF on proxied responses)
#   - Mailerlite signup forms (assets.mailerlite.com + form action posts)
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://js.stripe.com https://static.cloudflareinsights.com https://assets.mailerlite.com; style-src 'self' 'unsafe-inline' https://assets.mailerlite.com; img-src 'self' data: blob: https:; font-src 'self' data: https:; connect-src 'self' https://api.stripe.com https://api.workos.com https://*.authkit.app https://cloudflareinsights.com https://static.cloudflareinsights.com https://assets.mailerlite.com; frame-src 'self' https://js.stripe.com https://checkout.stripe.com https://*.authkit.app; frame-ancestors 'self'; base-uri 'self'; form-action 'self' https://checkout.stripe.com https://api.workos.com https://*.authkit.app https://assets.mailerlite.com; object-src 'none'; upgrade-insecure-requests" always;
SNIP

cat >/etc/nginx/snippets/dotfile_deny.conf <<'SNIP'
location ~ /\.(?!well-known) {
    deny all;
    access_log off;
    log_not_found off;
    return 404;
}
SNIP

cat >/etc/nginx/snippets/tw2-proxy-headers.conf <<'SNIP'
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_read_timeout 60s;
proxy_connect_timeout 5s;
SNIP

hdr "3. nginx vhost stage2.trxstat.com"
rm -f /etc/nginx/sites-enabled/default

cat >/etc/nginx/sites-available/tw2-stage-web <<'NGINX'
upstream tw2_web {
    server 127.0.0.1:5500;
    keepalive 16;
}

# Cross-tier appserver upstream lives on the app box over VLAN.
upstream tw2_appserver {
    server 10.0.0.92:5000;
    keepalive 16;
}

# Default vhost: bare-IP/wrong-Host probes get hung up.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}

server {
    listen 80;
    listen [::]:80;
    server_name stage2.trxstat.com;

    include /etc/nginx/snippets/security_headers.conf;
    include /etc/nginx/snippets/dotfile_deny.conf;

    root /var/www/tradewave;
    index home.html index.html;

    client_max_body_size 50M;

    # ACME challenge (kept open for future certbot or LE renewal)
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
        allow all;
    }

    # ============================================================
    # Marketing site (static)
    # ============================================================
    location = / {
        try_files /home.html =404;
    }
    location /_static/   { try_files $uri =404; expires 1d; }
    location /_partials/ { try_files $uri =404; }

    # ============================================================
    # Web tier
    # ============================================================
    location = /signup    { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /login     { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /logout    { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /account   { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /account/    { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /pricing   { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /healthz   { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }

    location /auth/       { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /api/        { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /webhooks/   { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /admin       { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /admin/      { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /stripe/     { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }

    # ============================================================
    # /app — React; index goes through web tier for auth injection
    # ============================================================
    location = /app             { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /app/            { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location = /app/index.html  { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }
    location /app/              { alias /home/flask/web-react/build/; }

    # ============================================================
    # /appserver — proxy to stage-app over VLAN
    # ============================================================
    location /appserver/ {
        proxy_pass http://tw2_appserver/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    # Block source maps
    location ~ \.map$ { return 404; }

    error_page 404 /404.html;
    location = /404.html { root /var/www/tradewave; internal; }

    location / { try_files $uri $uri/ $uri.html =404; }

    access_log /var/log/nginx/tradewave.access.log;
    error_log  /var/log/nginx/tradewave.error.log;
}
NGINX

ln -sf /etc/nginx/sites-available/tw2-stage-web /etc/nginx/sites-enabled/tw2-stage-web
install -d -o www-data -g www-data /var/www/html

hdr "4. daemon-reload + start"
systemctl daemon-reload
systemctl enable --now tradewave-web
sleep 2
systemctl --no-pager status tradewave-web | head -12

hdr "5. nginx -t + reload"
nginx -t
systemctl reload nginx || systemctl restart nginx
systemctl --no-pager status nginx | head -6

hdr "6. smoke"
echo "[gunicorn direct]      $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:5500/api/me)  (200/401 means web tier alive)"
echo "[nginx marketing]      $(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: stage2.trxstat.com' http://127.0.0.1/)"
echo "[nginx /api/me]        $(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: stage2.trxstat.com' http://127.0.0.1/api/me)"
echo "[nginx /app/static/*]  $(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: stage2.trxstat.com' 'http://127.0.0.1/app/static/css/main.css' 2>/dev/null || echo n/a)"
echo "[nginx /appserver via VLAN] $(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: stage2.trxstat.com' http://127.0.0.1/appserver/healthz 2>/dev/null || echo n/a)"
echo "[bare-IP]              $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1/)  (444 expected)"

ss -tlnp | grep -E ':5500|:80 ' || true

echo
echo "=== stage-web services + http nginx complete ==="
echo "Next: bootstrap_stage_web_tunnel.sh — cloudflared tunnel for stage2.trxstat.com"
