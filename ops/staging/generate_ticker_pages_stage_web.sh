#!/usr/bin/env bash
# Generate the per-ticker SEO pages on stage-web (the "Tickers" menu item).
# TW2 regenerates them with its own templates/branding rather than rsyncing
# TW1's WordPress-styled HTML — no URL rewrite needed, correct TW2 chrome.
#
# Runs the generator on stage-web; it pulls live data from stage-app
# (config.appserver_url) + central services and writes
# /var/www/tradewave/patterns/{SYMBOL}.html + patterns_index + sitemap.
#
# Run on .176 as root.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

WEB="$TGT_WEB_PUB"
SSH="-p $TGT_SSH_PORT"

hdr "1. confirm ticker list + appserver reachability"
ssh $SSH "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  /home/flask/venv/bin/python -c "import json; print(\"tickers:\", len(json.load(open(\"/home/flask/site/ticker_pages/data/ticker_list_phase1.json\"))))"
  curl -sS -o /dev/null -w "appserver via VLAN: %{http_code}\n" http://${TGT_APP_VLAN}:80/ || true
'

hdr "2. generate"
ssh $SSH "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  cd /home/flask/site/ticker_pages
  sudo -u flask -E /home/flask/venv/bin/python generate_ticker_pages.py 2>&1 | tail -20
'

hdr "3. verify output + perms"
ssh $SSH "root@$WEB" '
  chown -R flask:flask /var/www/tradewave/patterns 2>/dev/null || true
  find /var/www/tradewave/patterns -name "*.html" | wc -l
  ls /var/www/tradewave/patterns/ | head -8
'

echo
echo "=== ticker pages generated ==="
echo "Verify: https://${TGT_WEB_HOST}/patterns/AAPL.html"
echo "Index:  https://${TGT_WEB_HOST}/patterns/"
echo "For prod: run via  ops/staging/run.sh prod generate_ticker_pages_stage_web.sh"
