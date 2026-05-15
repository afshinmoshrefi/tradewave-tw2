#!/usr/bin/env bash
# TW2 staging APP-box cloudflared tunnel setup.
# Run on .176 as root. Reuses Afshin's existing Cloudflare account creds.
#
# What this does:
#   1. SCP /home/afshin/.cloudflared/cert.pem to staging-app:/root/.cloudflared/
#   2. SSH to staging-app and:
#      a. Add Cloudflare's apt repo + install cloudflared
#      b. cloudflared tunnel create tw2-stage-app
#      c. cloudflared tunnel route dns tw2-stage-app tw2-stage-app.trxstat.com
#         (rewrites the DNS proxied record to a CNAME at <UUID>.cfargotunnel.com)
#      d. Write /etc/cloudflared/config.yml with ingress tw2-stage-app.trxstat.com → http://localhost:80
#      e. Install cloudflared as a systemd service, enable, start
#      f. Curl https://tw2-stage-app.trxstat.com/healthz from outside

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

STAGE_IP=199.244.48.157
SSH_PORT=4369
CERT_SRC=/home/afshin/.cloudflared/cert.pem

[[ -r "$CERT_SRC" ]] || { echo "Cannot read $CERT_SRC" >&2; exit 1; }

hdr "1. scp cert.pem to staging-app"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'install -d -m 700 /root/.cloudflared'
scp -P "$SSH_PORT" "$CERT_SRC" "root@${STAGE_IP}:/root/.cloudflared/cert.pem"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'chmod 600 /root/.cloudflared/cert.pem'

hdr "2. remote setup"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'bash -s' <<'REMOTE'
set -euo pipefail
hdr() { printf '\n--- %s ---\n' "$*"; }

hdr "a. install cloudflared from Cloudflare apt repo"
if ! command -v cloudflared >/dev/null 2>&1; then
    mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(. /etc/os-release && echo $VERSION_CODENAME) main" \
        | tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared
fi
cloudflared --version

hdr "b. create tunnel (idempotent — reuse if name already exists)"
if cloudflared tunnel list 2>/dev/null | grep -q 'tw2-stage-app'; then
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk '$2=="tw2-stage-app" {print $1}')
    echo "tunnel tw2-stage-app already exists: $TUNNEL_ID"
else
    cloudflared tunnel create tw2-stage-app
    TUNNEL_ID=$(cloudflared tunnel list | awk '$2=="tw2-stage-app" {print $1}')
fi
echo "TUNNEL_ID=$TUNNEL_ID"
[[ -f "/root/.cloudflared/${TUNNEL_ID}.json" ]] || { echo "credentials file missing for $TUNNEL_ID" >&2; exit 1; }

hdr "c. route DNS"
# Routes the proxied DNS record at tw2-stage-app.trxstat.com to the tunnel's
# CNAME. Replaces whatever A record was there.
cloudflared tunnel route dns tw2-stage-app tw2-stage-app.trxstat.com || \
    echo "(DNS route may already exist — non-fatal)"

hdr "d. write /etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cat >/etc/cloudflared/config.yml <<CFG
tunnel: tw2-stage-app
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: tw2-stage-app.trxstat.com
    service: http://localhost:80
  - service: http_status:404
CFG
echo "wrote /etc/cloudflared/config.yml"

hdr "e. systemd"
# `cloudflared service install` creates a unit. If it already exists, just
# refresh the config and restart.
if [[ ! -f /etc/systemd/system/cloudflared.service ]]; then
    cloudflared service install
fi
systemctl daemon-reload
systemctl enable cloudflared
systemctl restart cloudflared
sleep 2
systemctl --no-pager status cloudflared | head -10

hdr "f. local smoke"
sleep 3
curl -sS -o /dev/null -w "local nginx /healthz via Host header: %{http_code}\n" \
    -H 'Host: tw2-stage-app.trxstat.com' http://127.0.0.1/healthz
REMOTE

hdr "3. external smoke from .176"
sleep 5
curl -sS -o /dev/null -w "external https://tw2-stage-app.trxstat.com/healthz: %{http_code}\n" \
    https://tw2-stage-app.trxstat.com/healthz
echo "If 200, end-to-end TLS via Cloudflare tunnel is up."

echo
echo "=== cloudflared tunnel setup complete ==="
