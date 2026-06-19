#!/usr/bin/env bash
# verify_deploy.sh {staging|prod} - post-deploy smoke test. Fails LOUD when the
# deployed site is incomplete, mis-hosted, or a feature did not land. Run from the
# DEV/deploy box after deploy.sh + regen_site. Exit 0 = clean; nonzero = #failures.
#
# This is the gate that turns "messy deploy" into "boring": it catches broken routes
# (/markets 403, /join 404), wrong-host leaks (tw2-dev/stage2/api-dev baked into pages),
# and undeployed features (dead GA4, old scorecard metric) at deploy time instead of in
# production. WARN = look at it; FAIL = do not ship.
#
# PORTAL=1 (staging): the developer API/MCP/portal are live - verify them.
# PORTAL=0 (prod):    API/MCP ship DARK (deploy.sh skips them) - skip those checks.
set -uo pipefail

ENV="${1:-}"
case "$ENV" in
  staging) WEB=185.53.209.8;    APP=199.244.48.157; HOST=tw2-stage.trxstat.com; APIHOST=api-stage.trxstat.com; DEVHOST=developers-stage.trxstat.com; PORTAL=1
           LEAKS='tw2-dev|developers-dev|api-dev|mcp-dev|stage2\.trxstat|192\.168\.|10\.0\.0\.|127\.0\.0\.1|smn-dev' ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tradewave.ai;        APIHOST=api.tradewave.ai;       DEVHOST=developers.tradewave.ai; PORTAL=0
           LEAKS='tw2-dev|tw2-stage|developers-dev|developers-stage|api-dev|api-stage|mcp-dev|mcp-stage|stage2\.trxstat|trxstat\.com|192\.168\.|10\.0\.0\.|127\.0\.0\.1|smn-dev|smn-stage' ;;
  *) echo "usage: $0 {staging|prod}"; exit 2 ;;
esac
SSH="ssh -p 4369 -o BatchMode=yes -o ConnectTimeout=10"
fails=0; warns=0
ok(){   echo "  PASS  $*"; }
bad(){  echo "  FAIL  $*"; fails=$((fails+1)); }
warn(){ echo "  WARN  $*"; warns=$((warns+1)); }
wc_web(){ $SSH "root@$WEB" "curl -s -o /dev/null -w '%{http_code}' -H 'Host: $HOST' http://127.0.0.1$1" 2>/dev/null; }
wc_app(){ $SSH "root@$APP" "curl -s -o /dev/null -w '%{http_code}' -H 'Host: $2' http://127.0.0.1:8080$1" 2>/dev/null; }

echo "==================  verify_deploy [$ENV]  host=$HOST  portal=$PORTAL  =================="

echo "-- services --"
$SSH "root@$WEB" 'systemctl is-active nginx tradewave-web 2>/dev/null' | grep -qvx active \
  && bad "a WEB service is not active (nginx/tradewave-web)" || ok "WEB: nginx + tradewave-web active"
if [ "$PORTAL" = 1 ]; then
  $SSH "root@$APP" 'systemctl is-active tradewave-appserver tradewave-apiserver tradewave-mcpserver nginx 2>/dev/null' | grep -qvx active \
    && bad "an APP service is not active (appserver/apiserver/mcp/nginx)" || ok "APP: appserver + apiserver + mcp + nginx active"
else
  $SSH "root@$APP" 'systemctl is-active tradewave-appserver 2>/dev/null' | grep -qvx active \
    && bad "APP appserver not active" || ok "APP: appserver active (api/mcp dark on prod - not checked)"
fi

echo "-- web routes (nginx-direct, Host: $HOST) --"
for r in / /home.html /scorecard.html /research.html /about.html /terms.html /privacy.html /disclaimer.html /methodology.html /insights/ /learn/ /markets/sp500.html /affiliate.html; do
  c=$(wc_web "$r"); [ "$c" = 200 ] && ok "$r -> 200" || bad "$r -> $c (want 200)"
done
c=$(wc_web /markets/);        case "$c" in 200|301|302) ok "/markets/ -> $c" ;; *) bad "/markets/ -> $c (raw 403 = no section index)";; esac
c=$(wc_web /join/TESTCODE);   [ "$c" = 404 ] && bad "/join/TESTCODE -> 404 (nginx 'location /join/' proxy rule missing)" || ok "/join/TESTCODE -> $c (route reaches the app)"
c=$(wc_web /healthz);         [ "$c" = 200 ] && ok "/healthz -> 200" || warn "/healthz -> $c"

if [ "$PORTAL" = 1 ]; then
  echo "-- api + developer portal (app box :8080) --"
  c=$(wc_app /healthz "$APIHOST"); [ "$c" = 200 ] && ok "api /healthz -> 200" || bad "api /healthz -> $c"
  c=$(wc_app / "$DEVHOST");        [ "$c" = 200 ] && ok "portal / -> 200"     || bad "portal / -> $c"
  c=$(wc_app /docs/ "$DEVHOST");   [ "$c" = 200 ] && ok "portal /docs/ -> 200" || bad "portal /docs/ -> $c (403 = no docs index)"
else
  echo "-- api + developer portal: SKIP (API/MCP dark on $ENV) --"
fi

echo "-- host-leak grep (baked HTML/XML must carry only the $ENV host) --"
n=$($SSH "root@$WEB" "grep -rlE '$LEAKS' --include='*.html' --include='*.xml' /var/www/tradewave/ 2>/dev/null | wc -l")
if [ "$n" = 0 ]; then ok "site: 0 files leak a non-$ENV host"; else bad "site: $n file(s) leak a non-$ENV host:"; $SSH "root@$WEB" "grep -rlE '$LEAKS' --include='*.html' --include='*.xml' /var/www/tradewave/ 2>/dev/null | sed 's/^/        /' | head"; fi
if [ "$PORTAL" = 1 ]; then
  n=$($SSH "root@$APP" "grep -rlE '$LEAKS' --include='*.html' --include='*.json' /var/www/developers/ 2>/dev/null | wc -l")
  [ "$n" = 0 ] && ok "portal: 0 files leak a non-$ENV host" || { bad "portal: $n file(s) leak a non-$ENV host:"; $SSH "root@$APP" "grep -rlE '$LEAKS' --include='*.html' --include='*.json' /var/www/developers/ 2>/dev/null | sed 's/^/        /' | head"; }
fi

echo "-- design + feature markers --"
home=$($SSH "root@$WEB" "curl -s -H 'Host: $HOST' http://127.0.0.1/" 2>/dev/null)
echo "$home" | grep -qiE 'whoever|the receipts|tuesday'      && ok "home: Ledger design present" || bad "home: Ledger markers missing"
echo "$home" | grep -q  'Trade<b>Wave</b>'                   && ok "home: 2-color logo"           || warn "home: 2-color logo markup not found"
echo "$home" | grep -qiE '>Wave Viewer<|>Start Free Trial<'  && ok "home: unified nav"            || warn "home: nav markers not found"
if echo "$home" | grep -qE 'gtag\(|googletagmanager|G-[A-Z0-9]{6,}'; then ok "home: GA4 loader present"; else
  [ "$ENV" = prod ] && bad "home: GA4 loader MISSING (analytics dead on prod)" || warn "home: no GA4 loader (may be prod-gated; confirm it lights on prod)"; fi
# Read the generated file on disk, NOT via nginx: open_file_cache can briefly serve the
# pre-regen scorecard right after a deploy, false-flagging an otherwise-correct page. This
# check is about generated CONTENT (did the two-metric render), so the file is the source of truth.
if $SSH "root@$WEB" "grep -qiE 'held.to.close|reached.target' /var/www/tradewave/scorecard.html 2>/dev/null"; then
  ok "scorecard: two-metric present"
else
  bad "scorecard: two-metric MISSING (still the old blended metric)"
fi

echo "======  verify_deploy [$ENV]:  $fails FAIL, $warns WARN  ======"
[ "$fails" = 0 ] && echo "RESULT: CLEAN" || echo "RESULT: $fails BLOCKER(S) - do not ship"
exit "$fails"
