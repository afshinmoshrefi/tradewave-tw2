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

WEB=185.53.209.8
SSH="-p 4369"

hdr "1. confirm ticker list + appserver reachability"
ssh $SSH "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  /home/flask/venv/bin/python -c "import json; print(\"tickers:\", len(json.load(open(\"/home/flask/site/ticker_pages/data/ticker_list_phase1.json\"))))"
  curl -sS -o /dev/null -w "appserver via VLAN: %{http_code}\n" http://10.0.0.92:80/ || true
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
echo "Verify: https://stage2.trxstat.com/patterns/AAPL.html"
echo "Index:  https://stage2.trxstat.com/patterns/"
echo "For prod: re-run with WEB= pointed at prod-web."
