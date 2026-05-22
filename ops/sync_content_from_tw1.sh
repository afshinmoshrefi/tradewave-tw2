#!/usr/bin/env bash
# sync_content_from_tw1.sh - refresh the four TW1-lineage content sets on a TW2 web box.
#
# Standalone / on-demand. Run it against STAGING first to test, then against PROD
# right before cutover to populate fresh content:
#     bash ops/sync_content_from_tw1.sh staging    # test
#     bash ops/sync_content_from_tw1.sh prod       # at cutover
#
# Of the four, only the SCORECARD pulls from TW1: featured_history.json is an
# accumulated state file that cannot be recomputed. Tickers, home-opportunities,
# and daily-AI-pick are GENERATED in TW2 from the appserver (the market data they
# need already syncs); TW2 uses its own templates/branding, not TW1's WP HTML.
# This script ONLY produces content - it does NOT send emails or post to social.
#
# PREREQUISITE (verified on staging 2026-05-22): scorecard + tickers work as-is.
# home_opportunities + daily_ai_pick need the target APPSERVER to accept the
# generators' service login: home_opportunities uses SERVICE_API_KEY -> /login/api,
# which requires the service-account row on the appserver DB. Create it per env on
# the app box: sudo -u flask /home/flask/venv/bin/python web/db_admin.py ensure-service-account
# (idempotent; hashes SERVICE_API_KEY with API_KEY_HMAC_SECRET or APPSERVER_JWT_SECRET).
# daily_ai_pick uses the legacy keyprovider login. Until that auth is set up on the
# target, those two log "invalid api_key" / login errors (the script continues; the
# other generators still run).
#
# Run on .176 as root. It borrows .176's TW1-authorized /root/.ssh/id_rsa, pushes
# it to the target web box only for the rsync, then shreds it (same pattern as the
# migrate_*_from_tw1.sh scripts). Idempotent.
set -euo pipefail
hdr(){ printf '\n=== %s ===\n' "$*"; }

case "${1:-}" in
  staging) WEB=185.53.209.8;    HOST=tw2-stage.trxstat.com ;;
  prod)    WEB=194.113.195.141; HOST=tw2-prod.trxstat.com ;;
  *) echo "usage: $0 {staging|prod}"; exit 2 ;;
esac
ENV="$1"; SSHP=4369
TW1_IP=10.0.0.40; TW1_USER=root; TW1_PORT=4369
TW1_FEATURED=/home/flask/blog/featured_history.json
DST_FEATURED=/home/flask/site/data/featured_history.json
LOCAL_KEY=/root/.ssh/id_rsa
REMOTE_KEY=/root/.tw1_sync_key

[[ -r "$LOCAL_KEY" ]] || { echo "ERROR: no $LOCAL_KEY on .176 (the TW1-authorized key)."; exit 1; }
cleanup(){ ssh -p $SSHP "root@$WEB" "shred -u $REMOTE_KEY 2>/dev/null || rm -f $REMOTE_KEY" 2>/dev/null || true; }
trap cleanup EXIT INT TERM HUP

hdr "[$ENV] 1/3  sync scorecard state (featured_history.json) from TW1 prod ($TW1_IP)"
scp -P $SSHP "$LOCAL_KEY" "root@$WEB:$REMOTE_KEY"
ssh -p $SSHP "root@$WEB" "chmod 600 $REMOTE_KEY && install -d -o flask -g flask -m 755 /home/flask/site/data && \
  rsync -avh -e 'ssh -i $REMOTE_KEY -p $TW1_PORT -o StrictHostKeyChecking=accept-new' \
    ${TW1_USER}@${TW1_IP}:${TW1_FEATURED} ${DST_FEATURED} && \
  chown flask:flask ${DST_FEATURED} && chmod 644 ${DST_FEATURED} && \
  /home/flask/venv/bin/python -c \"import json;print('featured_history entries:',len(json.load(open('${DST_FEATURED}'))))\""

hdr "[$ENV] 2/3  generate the 4 content sets on $WEB (from the appserver / synced market data)"
ssh -p $SSHP "root@$WEB" '
  set -a; . /etc/tradewave/secrets.env; set +a
  run(){ echo "--- $2 ---"; ( cd "/home/flask/$1" && sudo -u flask -E /home/flask/venv/bin/python "$2" ) 2>&1 | tail -4 || true; }
  run site generate_scorecard.py
  run site home_opportunities.py
  run site generate_daily_ai_pick.py
  run site/ticker_pages generate_ticker_pages.py
'

hdr "[$ENV] 3/3  verify outputs"
ssh -p $SSHP "root@$WEB" '
  chown -R flask:flask /var/www/tradewave/patterns 2>/dev/null || true
  for f in /var/www/tradewave/scorecard.html /var/www/tradewave/daily-ai-pick.html /home/flask/site/data/home_opportunities.csv; do
    if [ -f "$f" ]; then echo "OK   $f ($(stat -c%s "$f") bytes, mtime $(date -r "$f" +%H:%M))"; else echo "MISS $f"; fi
  done
  echo "ticker pages: $(find /var/www/tradewave/patterns -name "*.html" 2>/dev/null | wc -l)"
'
echo; echo "=== [$ENV] content sync done. Verify on https://$HOST : /scorecard.html, /daily-ai-pick.html, /patterns/, and the home-page opp list ==="
