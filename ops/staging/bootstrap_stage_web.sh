#!/usr/bin/env bash
# TW2 staging WEB-box bootstrap (OS layer).
# Usage (env-driven runner prepends the target coordinates):
#   ops/staging/run.sh staging bootstrap_stage_web.sh
# For prod: run via  ops/staging/run.sh prod bootstrap_stage_web.sh
#
# What this does (system layer only — no app code, no secrets):
#   1. apt: nginx, redis-server, python3-venv, build deps, chrony, certbot, ufw
#      (no postgres on the web tier — that lives on the app box)
#   2. 1G swap (RAM is 961M)
#   3. flask system user (uid 1001 to match app + dev)
#   4. /etc/tradewave/, /var/log/tradewave/, /var/www/tradewave/, /home/flask/data/
#   5. chrony makestep 1 -1
#   6. Redis on 127.0.0.1 + $TGT_WEB_VLAN (so app box can write SMN db=3 cross-tier)
#   7. UFW: $TGT_SSH_PORT ssh + 80/443 public; 6379 from $TGT_APP_VLAN only (app → web Redis)
#   8. flask deploy SSH key, printed for you to add to GitHub

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# PAYLOAD: run via ops/staging/run.sh {staging|prod}, which prepends the target
# coordinates (TGT_*). Fail clearly if invoked directly without them.
: "${TGT_WEB_VLAN:?run via ops/staging/run.sh, which prepends the target coordinates}"

VLAN_APP="$TGT_APP_VLAN"
VLAN_WEB="$TGT_WEB_VLAN"
SSH_PORT="$TGT_SSH_PORT"

hdr "1. apt packages"
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y \
    redis-server \
    python3-venv python3-dev libpq-dev build-essential \
    nginx \
    chrony \
    certbot python3-certbot-nginx \
    ufw \
    curl jq rsync

hdr "2. swap (1G if absent)"
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "swap added"
else
    echo "swap already configured"
fi

hdr "3. flask user (uid 1001 to match app + dev)"
if ! id flask >/dev/null 2>&1; then
    groupadd -g 1001 flask
    useradd -m -d /home/flask -s /bin/bash -u 1001 -g 1001 flask
    echo "flask user created"
else
    echo "flask user already exists: $(id flask)"
fi

hdr "4. directories"
install -d -m 750 -o root  -g flask /etc/tradewave
install -d -m 755 -o flask -g flask /var/log/tradewave
install -d -m 755 -o flask -g flask /var/www/tradewave
install -d -m 755 -o flask -g flask /home/flask/data    # for the few _symbols.csv files report_renderer needs
ls -ld /etc/tradewave /var/log/tradewave /var/www/tradewave /home/flask/data

hdr "5. chrony makestep"
if ! grep -q '^makestep 1 -1' /etc/chrony/chrony.conf; then
    echo 'makestep 1 -1' >> /etc/chrony/chrony.conf
    systemctl restart chrony
    echo "makestep added"
else
    echo "makestep already set"
fi

hdr "6. redis"
REDIS_CONF=/etc/redis/redis.conf
sed -i "s/^bind .*/bind 127.0.0.1 ${VLAN_WEB}/" "$REDIS_CONF"
sed -i 's/^protected-mode .*/protected-mode yes/' "$REDIS_CONF"
systemctl enable --now redis-server
systemctl restart redis-server
echo "redis listening: $(ss -tln | grep ':6379' || echo NONE)"

hdr "7. ufw"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp comment 'ssh (non-standard)'
ufw allow 80/tcp           comment 'http (LE renewal or direct)'
ufw allow 443/tcp          comment 'https (if not behind cloudflared tunnel)'
ufw allow from ${VLAN_APP} to any port 6379 comment 'redis db=3 from app (SMN cross-tier)'
ufw --force enable
ufw status numbered

hdr "8. flask deploy key"
sudo -u flask install -d -m 700 /home/flask/.ssh
if [ ! -f /home/flask/.ssh/id_ed25519 ]; then
    sudo -u flask ssh-keygen -t ed25519 -N '' -C "flask@${TGT_WEB_HOST}" -f /home/flask/.ssh/id_ed25519
fi
sudo -u flask chmod 600 /home/flask/.ssh/id_ed25519
echo "PUBLIC KEY (add as deploy key at github.com/afshinmoshrefi/tradewave-tw2/settings/keys, title '${TGT_WEB_HOST}', read-only):"
cat /home/flask/.ssh/id_ed25519.pub

hdr "9. github known_hosts (pre-trust)"
sudo -u flask bash -c 'ssh-keyscan -t ed25519 github.com 2>/dev/null >> /home/flask/.ssh/known_hosts'
sudo -u flask sort -u /home/flask/.ssh/known_hosts -o /home/flask/.ssh/known_hosts

echo
echo "=== web-box bootstrap (OS layer) complete ==="
echo "Next: add the pubkey to GitHub as a deploy key, then run bootstrap_stage_web_code.sh"
