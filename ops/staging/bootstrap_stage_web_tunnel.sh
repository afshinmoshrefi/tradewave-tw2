#!/usr/bin/env bash
# TW2 WEB-box cloudflared tunnel for ${TGT_WEB_HOST}.
# Run on .176 as root via ops/staging/run.sh {staging|prod}. Reuses Afshin's Cloudflare account cert.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

STAGE_IP="$TGT_WEB_PUB"
SSH_PORT="$TGT_SSH_PORT"
CERT_SRC=/home/afshin/.cloudflared/cert.pem

[[ -r "$CERT_SRC" ]] || { echo "Cannot read $CERT_SRC" >&2; exit 1; }

hdr "1. scp cert.pem to web box"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'install -d -m 700 /root/.cloudflared'
scp -P "$SSH_PORT" "$CERT_SRC" "root@${STAGE_IP}:/root/.cloudflared/cert.pem"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'chmod 600 /root/.cloudflared/cert.pem'

hdr "2. remote setup"
# WEB_HOST + TUNNEL are expanded LOCALLY into the remote env; the REMOTE heredoc
# stays single-quoted so remote-only $vars ($TUNNEL_ID, awk fields, $VERSION_CODENAME)
# are NOT expanded here.
ssh -p "$SSH_PORT" "root@${STAGE_IP}" "WEB_HOST='$TGT_WEB_HOST' TUNNEL='$TGT_TUNNEL_WEB' bash -s" <<'REMOTE'
set -euo pipefail
hdr() { printf '\n--- %s ---\n' "$*"; }

hdr "a. install cloudflared"
if ! command -v cloudflared >/dev/null 2>&1; then
    mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(. /etc/os-release && echo $VERSION_CODENAME) main" \
        | tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared
fi
cloudflared --version

hdr "b. create tunnel"
if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL"; then
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL" '$2==t {print $1}')
    echo "tunnel $TUNNEL already exists: $TUNNEL_ID"
else
    cloudflared tunnel create "$TUNNEL"
    TUNNEL_ID=$(cloudflared tunnel list | awk -v t="$TUNNEL" '$2==t {print $1}')
fi
echo "TUNNEL_ID=$TUNNEL_ID"
[[ -f "/root/.cloudflared/${TUNNEL_ID}.json" ]] || { echo "credentials file missing" >&2; exit 1; }

hdr "c. route DNS (overwrite any existing record)"
cloudflared tunnel route dns --overwrite-dns "$TUNNEL" "$WEB_HOST"

hdr "d. write /etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cat >/etc/cloudflared/config.yml <<CFG
tunnel: $TUNNEL
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: $WEB_HOST
    service: http://localhost:80
  - service: http_status:404
CFG

hdr "e. systemd"
if [[ ! -f /etc/systemd/system/cloudflared.service ]]; then
    cloudflared service install
fi
systemctl daemon-reload
systemctl enable cloudflared
systemctl restart cloudflared
sleep 2
systemctl --no-pager status cloudflared | head -8

hdr "f. local smoke"
sleep 3
curl -sS -o /dev/null -w "local nginx /healthz via Host header: %{http_code}\n" \
    -H "Host: $WEB_HOST" http://127.0.0.1/healthz
REMOTE

hdr "3. external smoke from .176"
sleep 5
for path in /healthz / /api/me; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' "https://${TGT_WEB_HOST}${path}" || echo "ERR")
    echo "external https://${TGT_WEB_HOST}${path}: $code"
done

echo
echo "=== ${TGT_WEB_HOST} tunnel up ==="
