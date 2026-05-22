#!/usr/bin/env bash
# Lift the US-only market data subset from .176 → staging-app.
# Run on .176 as root (needs to read flask-owned files and ssh as root to staging).
#
# What gets shipped (~11.9 GB total):
#   /home/flask/data/csv/US/        1.6G   raw historical CSVs (per-ticker)
#   /home/flask/data/dj30/          1.6G   precomputed opportunities
#   /home/flask/data/sp500/         6.1G
#   /home/flask/data/nasdaq100/     2.6G
#   /home/flask/data/dj30_symbols.csv
#   /home/flask/data/sp500_symbols.csv
#   /home/flask/data/nasdaq100_symbols.csv
#   /home/flask/data/INDX_USA_symbols.csv
#   /home/flask/data/INDX_COMMON_symbols.csv
#
# What gets skipped:
#   /home/flask/data/rus1000/ wilshire5000/ Sectors_ETF/ etc.  (size)
#   /home/flask/data/csv/{LSE,KO,KQ,TO,INDX,COMM,ETF,FOREX,CC,GBOND}/ (non-US)
#   *.bak/.work/.tmp (regenerable)
#
# rsync is resumable — if the link drops or you ^C, re-run and it picks up.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

STAGE_IP="$TGT_APP_PUB"
SSH_PORT="$TGT_SSH_PORT"
SSH_OPTS="-p ${SSH_PORT}"
SRC_BASE=/home/flask/data
DST_BASE=/home/flask/data

hdr "0. precheck dest dir on staging"
ssh ${SSH_OPTS} root@${STAGE_IP} \
  'install -d -o flask -g flask -m 755 /home/flask/data /home/flask/data/csv && df -h /home'

hdr "1. small files: symbol manifests"
rsync -avh --info=progress2 \
  -e "ssh ${SSH_OPTS}" \
  "${SRC_BASE}/dj30_symbols.csv" \
  "${SRC_BASE}/sp500_symbols.csv" \
  "${SRC_BASE}/nasdaq100_symbols.csv" \
  "${SRC_BASE}/INDX_USA_symbols.csv" \
  "${SRC_BASE}/INDX_COMMON_symbols.csv" \
  "root@${STAGE_IP}:${DST_BASE}/"

hdr "2. csv/US/ (raw historicals, 1.6G)"
rsync -avh --partial --info=progress2 \
  --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
  -e "ssh ${SSH_OPTS}" \
  "${SRC_BASE}/csv/US/" \
  "root@${STAGE_IP}:${DST_BASE}/csv/US/"

hdr "3. dj30/ (1.6G)"
rsync -avh --partial --info=progress2 \
  --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
  -e "ssh ${SSH_OPTS}" \
  "${SRC_BASE}/dj30/" \
  "root@${STAGE_IP}:${DST_BASE}/dj30/"

hdr "4. sp500/ (6.1G — biggest single dir)"
rsync -avh --partial --info=progress2 \
  --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
  -e "ssh ${SSH_OPTS}" \
  "${SRC_BASE}/sp500/" \
  "root@${STAGE_IP}:${DST_BASE}/sp500/"

hdr "5. nasdaq100/ (2.6G)"
rsync -avh --partial --info=progress2 \
  --exclude '*.bak' --exclude '*.work' --exclude '*.tmp' --exclude '*.orig' \
  -e "ssh ${SSH_OPTS}" \
  "${SRC_BASE}/nasdaq100/" \
  "root@${STAGE_IP}:${DST_BASE}/nasdaq100/"

hdr "6. chown to flask:flask + verify"
ssh ${SSH_OPTS} root@${STAGE_IP} '
  chown -R flask:flask /home/flask/data
  du -sh /home/flask/data /home/flask/data/csv/US /home/flask/data/dj30 /home/flask/data/sp500 /home/flask/data/nasdaq100 2>/dev/null
  df -h /home
'

echo
echo "=== US-only data lift complete ==="
echo "Next: systemd units for tradewave-appserver / blog-queue / article-processor."
