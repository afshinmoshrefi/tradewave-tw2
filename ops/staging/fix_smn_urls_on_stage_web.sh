#!/usr/bin/env bash
# Rewrite TW1 SMN URLs in /var/www/smn/ on stage-web to point at
# https://${TGT_SMN_HOST} instead. Uses fix_staging_urls.py
# (lifted from TW1 .151). Dry-runs first, prompts before applying.
#
# Run on .176 as root.
# For prod: run via  ops/staging/run.sh prod fix_smn_urls_on_stage_web.sh

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

WEB="$TGT_WEB_PUB"
SSH="-p $TGT_SSH_PORT"

hdr "1. ensure stage-web TW2_NEWS_WEBSITE_URL points at smn host"
ssh $SSH "root@$WEB" "
  set -e
  if grep -q \"^TW2_NEWS_WEBSITE_URL=https://${TGT_SMN_HOST}\" /etc/tradewave/secrets.env; then
      echo \"already set\"
  else
      sed -i \"s|^TW2_NEWS_WEBSITE_URL=.*|TW2_NEWS_WEBSITE_URL=https://${TGT_SMN_HOST}|\" /etc/tradewave/secrets.env
      echo \"updated\"
  fi
  grep ^TW2_NEWS_WEBSITE_URL /etc/tradewave/secrets.env
"

hdr "2. pull latest code on stage-web (has fix_staging_urls.py)"
ssh $SSH "root@$WEB" "sudo -u flask git -C /home/flask pull --ff-only origin main" | tail -5

hdr "3. dry-run fix_staging_urls.py on stage-web"
ssh $SSH "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  cd /home/flask/smn && /home/flask/venv/bin/python fix_staging_urls.py
' | tail -40

read -r -p "Apply the rewrites for real? [y/N] " yn
[[ "$yn" =~ ^[Yy]$ ]] || { echo "aborted"; exit 0; }

hdr "4. apply"
ssh $SSH "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  cd /home/flask/smn && /home/flask/venv/bin/python fix_staging_urls.py --confirm
'

hdr "5. restart SMN services to pick up new env"
ssh $SSH "root@$WEB" 'systemctl restart tradewave-blog-queue tradewave-article-processor && echo restarted'

echo
echo "=== SMN URL rewrite complete ==="
echo "Verify in browser: click an article on https://${TGT_SMN_HOST}/"
