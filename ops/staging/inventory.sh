#!/usr/bin/env bash
# TW2 staging VM read-only inventory.
# Usage from your laptop / dev box:
#   ssh root@185.53.209.8   -p 4369 'bash -s' < inventory.sh > inv_web.txt
#   ssh root@199.244.48.157 -p 4369 'bash -s' < inventory.sh > inv_app.txt
#
# Read-only. No installs, no mutations.

set -u
hdr() { printf '\n=== %s ===\n' "$*"; }

hdr "HOST"
hostname -f 2>/dev/null || hostname
cat /etc/hostname 2>/dev/null

hdr "OS"
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
uname -a

hdr "RESOURCES"
echo "CPUs: $(nproc)"
free -h
df -h / /var /home 2>/dev/null | grep -v tmpfs

hdr "NETWORK"
ip -4 -br a 2>/dev/null
ss -tlnp 2>/dev/null | awk 'NR==1 || $1=="LISTEN"' | head -25

hdr "USERS"
id flask 2>&1
id afshin 2>&1
getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 {print $1, $3, $7}'

hdr "TIME"
timedatectl 2>/dev/null | head -8

hdr "PYTHON / NODE"
python3 --version 2>&1
which python3
python3 -m venv --help >/dev/null 2>&1 && echo "venv: ok" || echo "venv: MISSING (apt install python3-venv)"
which pip3 2>&1
node --version 2>&1
npm --version 2>&1

hdr "POSTGRES"
which psql 2>&1
psql --version 2>&1
systemctl is-active postgresql 2>&1
systemctl is-enabled postgresql 2>&1

hdr "REDIS"
which redis-cli 2>&1
redis-cli --version 2>&1
systemctl is-active redis-server 2>&1
systemctl is-active redis 2>&1

hdr "NGINX"
nginx -v 2>&1
systemctl is-active nginx 2>&1

hdr "CLOUDFLARED"
which cloudflared 2>&1
cloudflared --version 2>&1

hdr "GIT"
git --version 2>&1

hdr "RELEVANT PACKAGES (installed)"
dpkg -l 2>/dev/null | awk '/^ii / && $2 ~ /^(chrony|nginx|postgresql|redis|python3|nodejs|npm|cloudflared|git|jq|certbot|build-essential|libpq-dev|ufw|fail2ban)/ {printf "%-35s %s\n",$2,$3}'

hdr "FIREWALL"
ufw status 2>&1 | head -10
iptables -L INPUT -n 2>&1 | head -20

hdr "FILESYSTEM ROOTS"
ls -la /home 2>&1
ls -la /var/www 2>&1 || echo "/var/www absent"
ls -la /var/log/tradewave 2>&1 || echo "/var/log/tradewave absent"
ls -la /etc/tradewave 2>&1 || echo "/etc/tradewave absent"
ls /home/flask 2>/dev/null && echo "(/home/flask non-empty)" || echo "/home/flask absent or empty"

hdr "ROOT CRON"
crontab -l 2>&1 || echo "no root crontab"

hdr "CLOUD-INIT / IMAGE MARKERS"
ls /var/log/cloud-init* 2>/dev/null | head -3
cat /etc/issue 2>&1
ls /etc/cloud 2>/dev/null | head

hdr "SSH CONFIG (root + flask only)"
grep -E '^(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|AllowUsers)' /etc/ssh/sshd_config 2>&1 | head -10

echo
echo "=== inventory complete ==="
