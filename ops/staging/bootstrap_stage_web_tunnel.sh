#!/usr/bin/env bash
# TW2 staging WEB-box cloudflared tunnel for stage2.trxstat.com.
# Run on .176 as root. Reuses Afshin's Cloudflare account cert.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

STAGE_IP=185.53.209.8
SSH_PORT=4369
CERT_SRC=/home/afshin/.cloudflared/cert.pem

[[ -r "$CERT_SRC" ]] || { echo "Cannot read $CERT_SRC" >&2; exit 1; }

hdr "1. scp cert.pem to stage-web"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'install -d -m 700 /root/.cloudflared'
scp -P "$SSH_PORT" "$CERT_SRC" "root@${STAGE_IP}:/root/.cloudflared/cert.pem"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'chmod 600 /root/.cloudflared/cert.pem'

hdr "2. remote setup"
ssh -p "$SSH_PORT" "root@${STAGE_IP}" 'bash -s' <<'REMOTE'
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
if cloudflared tunnel list 2>/dev/null | grep -q 'tw2-stage-web'; then
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk '$2=="tw2-stage-web" {print $1}')
    echo "tunnel tw2-stage-web already exists: $TUNNEL_ID"
else
    cloudflared tunnel create tw2-stage-web
    TUNNEL_ID=$(cloudflared tunnel list | awk '$2=="tw2-stage-web" {print $1}')
fi
echo "TUNNEL_ID=$TUNNEL_ID"
[[ -f "/root/.cloudflared/${TUNNEL_ID}.json" ]] || { echo "credentials file missing" >&2; exit 1; }

hdr "c. route DNS (overwrite any existing record)"
cloudflared tunnel route dns --overwrite-dns tw2-stage-web stage2.trxstat.com

hdr "d. write /etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cat >/etc/cloudflared/config.yml <<CFG
tunnel: tw2-stage-web
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: stage2.trxstat.com
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
    -H 'Host: stage2.trxstat.com' http://127.0.0.1/healthz
REMOTE

hdr "3. external smoke from .176"
sleep 5
for path in /healthz / /api/me; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' "https://stage2.trxstat.com${path}" || echo "ERR")
    echo "external https://stage2.trxstat.com${path}: $code"
done

echo
echo "=== stage2.trxstat.com tunnel up ==="
