#!/usr/bin/env bash
# TW2 staging APP-box bootstrap (OS layer).
# Idempotent — safe to re-run. Stops on first error.
# Usage (env-driven runner prepends the target coordinates):
#   ops/staging/run.sh staging bootstrap_stage_app.sh
# For prod: run via  ops/staging/run.sh prod bootstrap_stage_app.sh
#
# What this does (system layer only — no app code, no secrets):
#   1. apt: postgres, redis, python3-venv, nginx, chrony, certbot, ufw, etc.
#   2. 1G swap (RAM is 961M)
#   3. flask system user (uid 1001 to match dev .176)
#   4. /etc/tradewave/, /var/log/tradewave/, /var/backups/tradewave/
#   5. chrony makestep 1 -1 (snapshot-revert safety, per dev)
#   6. Postgres role+db `tradewave`, listening on 127.0.0.1 + $TGT_APP_VLAN
#   7. Redis on 127.0.0.1 + $TGT_APP_VLAN, protected-mode on
#   8. UFW: $TGT_SSH_PORT ssh + 80/443 public; 5000/5432/6379 from $TGT_WEB_VLAN only
#   9. flask deploy SSH key, printed at the end for GitHub
#
# Code + secrets + alembic + services are a SEPARATE second script.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# PAYLOAD: run via ops/staging/run.sh {staging|prod}, which prepends the target
# coordinates (TGT_*). Fail clearly if invoked directly without them.
: "${TGT_APP_VLAN:?run via ops/staging/run.sh, which prepends the target coordinates}"

VLAN_APP="$TGT_APP_VLAN"
VLAN_WEB="$TGT_WEB_VLAN"
SSH_PORT="$TGT_SSH_PORT"

hdr "1. apt packages"
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y \
    postgresql postgresql-contrib \
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

hdr "3. flask user (uid 1001)"
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
install -d -m 750 -o flask -g flask /var/backups/tradewave  # flask-owned: backup_db.sh runs as flask
install -d -m 755 -o flask -g flask /home/flask/data            # for the US-only data subset
ls -ld /etc/tradewave /var/log/tradewave /var/backups/tradewave /home/flask/data

hdr "5. chrony makestep"
if ! grep -q '^makestep 1 -1' /etc/chrony/chrony.conf; then
    echo 'makestep 1 -1' >> /etc/chrony/chrony.conf
    systemctl restart chrony
    echo "makestep added"
else
    echo "makestep already set"
fi

hdr "6. postgres"
# Make Postgres listen on localhost + VLAN
PG_CONF="$(ls /etc/postgresql/*/main/postgresql.conf | head -1)"
PG_HBA="$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)"
sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost,${VLAN_APP}'/" "$PG_CONF"
sed -i "s/^listen_addresses.*/listen_addresses = 'localhost,${VLAN_APP}'/" "$PG_CONF"
# Allow tradewave from the web box's VLAN IP only
if ! grep -q "host  *tradewave  *tradewave  *${VLAN_WEB}/32" "$PG_HBA"; then
    echo "host    tradewave       tradewave       ${VLAN_WEB}/32         scram-sha-256" >> "$PG_HBA"
fi
systemctl enable --now postgresql
systemctl restart postgresql
# Create role + db (idempotent)
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='tradewave'" | grep -q 1 || \
    sudo -u postgres createuser tradewave
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='tradewave'" | grep -q 1 || \
    sudo -u postgres createdb -O tradewave tradewave
echo "postgres ready: $(sudo -u postgres psql -c '\l' | grep tradewave | head -1)"
echo "NOTE: tradewave role has no password yet. Bootstrap-2 will set it via ALTER ROLE from secrets.env."

hdr "7. redis"
# Bind localhost + VLAN, keep protected-mode on (we'll set requirepass in bootstrap-2 from secrets)
REDIS_CONF=/etc/redis/redis.conf
sed -i "s/^bind .*/bind 127.0.0.1 ${VLAN_APP}/" "$REDIS_CONF"
sed -i 's/^protected-mode .*/protected-mode yes/' "$REDIS_CONF"
systemctl enable --now redis-server
systemctl restart redis-server
echo "redis listening: $(ss -tln | grep ':6379' || echo NONE)"

hdr "8. ufw"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp comment 'ssh (non-standard)'
ufw allow 80/tcp           comment 'http (LE renewal)'
ufw allow 443/tcp          comment 'https (appserver public TLS)'
ufw allow from ${VLAN_WEB} to any port 5000 comment 'gunicorn from web'
ufw allow from ${VLAN_WEB} to any port 5432 comment 'postgres from web'
ufw allow from ${VLAN_WEB} to any port 6379 comment 'redis from web'
ufw --force enable
ufw status numbered

hdr "9. flask deploy key"
sudo -u flask install -d -m 700 /home/flask/.ssh
if [ ! -f /home/flask/.ssh/id_ed25519 ]; then
    sudo -u flask ssh-keygen -t ed25519 -N '' -C "flask@${TGT_APP_HOST}" -f /home/flask/.ssh/id_ed25519
fi
sudo -u flask chmod 600 /home/flask/.ssh/id_ed25519
echo "PUBLIC KEY (add to github.com/afshinmoshrefi/tradewave-tw2 → Settings → Deploy keys → Add deploy key, label '${TGT_APP_HOST}', allow write access NO):"
cat /home/flask/.ssh/id_ed25519.pub

hdr "10. github known_hosts (pre-trust)"
# Redirect must happen inside the flask shell, otherwise the file is root-owned.
sudo -u flask bash -c 'ssh-keyscan -t ed25519 github.com 2>/dev/null >> /home/flask/.ssh/known_hosts'
sudo -u flask sort -u /home/flask/.ssh/known_hosts -o /home/flask/.ssh/known_hosts

echo
echo "=== app-box bootstrap (OS layer) complete ==="
echo "Next: add the pubkey above to GitHub as a deploy key, then run bootstrap_stage_app_code.sh"
