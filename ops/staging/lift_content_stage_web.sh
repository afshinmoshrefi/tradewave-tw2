#!/usr/bin/env bash
# Lift stage-web's static content from .176.
# Run on .176 as root.
#
# Three sets:
#   1. /home/flask/web-react/build/      — compiled React /app/ (1.8M)
#   2. /var/www/tradewave/               — generated marketing pages (~210M)
#   3. /home/flask/data/*_symbols.csv    — US-only manifests for report_renderer

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

STAGE_IP=185.53.209.8
SSH_PORT=4369
SSH_OPTS="-p ${SSH_PORT}"

hdr "0. precheck dest dirs on stage-web"
ssh ${SSH_OPTS} root@${STAGE_IP} '
  install -d -o flask -g flask -m 755 /home/flask/web-react /home/flask/web-react/build
  install -d -o flask -g flask -m 755 /var/www/tradewave
  install -d -o flask -g flask -m 755 /home/flask/data
  df -h /
'

hdr "1. React build/ (1.8M)"
rsync -avh --info=progress2 --delete \
  -e "ssh ${SSH_OPTS}" \
  /home/flask/web-react/build/ \
  root@${STAGE_IP}:/home/flask/web-react/build/

hdr "2. /var/www/tradewave/ (~210M generated marketing)"
rsync -avh --partial --info=progress2 \
  --exclude '*.bak' --exclude '*.work' --exclude '*.orig' \
  -e "ssh ${SSH_OPTS}" \
  /var/www/tradewave/ \
  root@${STAGE_IP}:/var/www/tradewave/

hdr "3. _symbols.csv files (US-relevant only)"
rsync -avh --info=progress2 \
  -e "ssh ${SSH_OPTS}" \
  /home/flask/data/dj30_symbols.csv \
  /home/flask/data/sp500_symbols.csv \
  /home/flask/data/nasdaq100_symbols.csv \
  /home/flask/data/INDX_USA_symbols.csv \
  /home/flask/data/INDX_COMMON_symbols.csv \
  root@${STAGE_IP}:/home/flask/data/

hdr "4. chown + verify"
ssh ${SSH_OPTS} root@${STAGE_IP} '
  chown -R flask:flask /home/flask/web-react /home/flask/data
  chown -R flask:flask /var/www/tradewave
  du -sh /home/flask/web-react/build /var/www/tradewave /home/flask/data
  df -h /
'

echo
echo "=== stage-web content lift complete ==="
echo "Next: bootstrap_stage_web_services.sh (systemd tradewave-web + nginx)."
