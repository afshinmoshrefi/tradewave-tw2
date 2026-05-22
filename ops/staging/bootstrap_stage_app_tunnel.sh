#!/usr/bin/env bash
# TW2 APP-box cloudflared tunnel setup (target = ${TGT_APP_HOST}).
# Run on .176 as root via ops/staging/run.sh {staging|prod}. Reuses Afshin's Cloudflare account creds.
#
# What this does:
#   1. SCP /home/afshin/.cloudflared/cert.pem to the app box:/root/.cloudflared/
#   2. SSH to the app box and:
#      a. Add Cloudflare's apt repo + install cloudflared
#      b. cloudflared tunnel create ${TGT_TUNNEL_APP}
#      c. cloudflared tunnel route dns ${TGT_TUNNEL_APP} ${TGT_APP_HOST}
#         (rewrites the DNS proxied record to a CNAME at <UUID>.cfargotunnel.com)
#      d. Write /etc/cloudflared/config.yml with ingress ${TGT_APP_HOST} → http://localhost:80
#      e. Install cloudflared as a systemd service, enable, start
#      f. Curl https://${TGT_APP_HOST}/healthz from outside

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

STAGE_IP="$TGT_APP_PUB"
SSH_PORT="$TGT_SSH_PORT"
CERT_SRC=/home/afshin/.cloudflared/cert.pem

[[ -r "$CERT_SRC" ]] || { echo "Cannot read $CERT_SRC" >&2; exit 1; }

hdr "1. scp cert.pem to app box"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'install -d -m 700 /root/.cloudflared'
scp -P "$SSH_PORT" "$CERT_SRC" "root@${STAGE_IP}:/root/.cloudflared/cert.pem"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'chmod 600 /root/.cloudflared/cert.pem'

hdr "2. remote setup"
# APP_HOST + TUNNEL are expanded LOCALLY into the remote env; the REMOTE heredoc
# stays single-quoted so remote-only $vars are NOT expanded here.
ssh -p "$SSH_PORT" "root@${STAGE_IP}" "APP_HOST='$TGT_APP_HOST' TUNNEL='$TGT_TUNNEL_APP' bash -s" <<'REMOTE'
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
if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL"; then
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL" '$2==t {print $1}')
    echo "tunnel $TUNNEL already exists: $TUNNEL_ID"
else
    cloudflared tunnel create "$TUNNEL"
    TUNNEL_ID=$(cloudflared tunnel list | awk -v t="$TUNNEL" '$2==t {print $1}')
fi
echo "TUNNEL_ID=$TUNNEL_ID"
[[ -f "/root/.cloudflared/${TUNNEL_ID}.json" ]] || { echo "credentials file missing for $TUNNEL_ID" >&2; exit 1; }

hdr "c. route DNS"
# Routes the proxied DNS record at $APP_HOST to the tunnel's CNAME. Replaces any A record.
cloudflared tunnel route dns "$TUNNEL" "$APP_HOST" || \
    echo "(DNS route may already exist — non-fatal)"

hdr "d. write /etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cat >/etc/cloudflared/config.yml <<CFG
tunnel: $TUNNEL
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: $APP_HOST
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
    -H "Host: $APP_HOST" http://127.0.0.1/healthz
REMOTE

hdr "3. external smoke from .176"
sleep 5
curl -sS -o /dev/null -w "external https://${TGT_APP_HOST}/healthz: %{http_code}\n" \
    "https://${TGT_APP_HOST}/healthz"
echo "If 200, end-to-end TLS via Cloudflare tunnel is up."

echo
echo "=== cloudflared tunnel setup complete (${TGT_APP_HOST}) ==="
