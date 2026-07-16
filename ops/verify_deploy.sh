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
# PORTAL=1 on BOTH envs since the prod API/MCP launch (2026-07-04): the developer
# API/MCP/portal stack is verified everywhere. (It was 0 on prod during dark-ship.)
set -uo pipefail

ENV="${1:-}"
case "$ENV" in
  staging) WEB=185.53.209.8;    APP=199.244.48.157; HOST=tw2-stage.trxstat.com; APIHOST=api-stage.trxstat.com; DEVHOST=developers-stage.trxstat.com; MCPHOST=mcp-stage.trxstat.com; PORTAL=1
           LEAKS='tw2-dev|developers-dev|api-dev|mcp-dev|stage2\.trxstat|192\.168\.|10\.0\.0\.|127\.0\.0\.1|smn-dev' ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tradewave.ai;        APIHOST=api.tradewave.ai;       DEVHOST=developers.tradewave.ai; MCPHOST=mcp.tradewave.ai; PORTAL=1
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
  c=$(wc_app /learn/ "$DEVHOST");  [ "$c" = 200 ] && ok "portal /learn/ -> 200" || bad "portal /learn/ -> $c"
  c=$(wc_app /playground/ "$DEVHOST"); [ "$c" = 200 ] && ok "portal /playground/ -> 200" || bad "portal /playground/ -> $c"
  c=$(wc_app /mcp "$DEVHOST");     [ "$c" = 200 ] && ok "portal /mcp -> 200" || bad "portal /mcp -> $c"
  c=$(wc_app / "$MCPHOST")
  case "$c" in
    200|400|401|405|406) ok "mcp protocol host is routed -> $c" ;;
    *) bad "mcp protocol host is not routed correctly -> $c" ;;
  esac
  mcp_redirect_code=$($SSH "root@$APP" "curl -sS -o /dev/null -w '%{http_code}' -H 'Host: $DEVHOST' http://127.0.0.1:8080/mcp/" 2>/dev/null)
  mcp_redirect_location=$($SSH "root@$APP" "curl -sSI -H 'Host: $DEVHOST' http://127.0.0.1:8080/mcp/ | tr -d '\\r' | grep -i '^Location:' | head -1" 2>/dev/null)
  [ "$mcp_redirect_code" = 308 ] && [ "$mcp_redirect_location" = "Location: /mcp" ] \
    && ok "portal /mcp/ -> relative /mcp redirect" \
    || bad "portal /mcp/ redirect is not exactly 308 Location: /mcp"
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
# Read home.html from DISK, not via nginx: open_file_cache can briefly serve the
# pre-regen page right after a deploy and false-WARN the design markers (bit us
# on the 2026-07-04 staging deploy) - same reasoning as the scorecard check below.
home=$($SSH "root@$WEB" "cat /var/www/tradewave/home.html 2>/dev/null")
# NOTE: grep -c (not -q) - under `set -o pipefail`, grep -q exits on first match,
# SIGPIPEs the echo, and the pipeline reports failure EXACTLY when the marker IS
# present. -c consumes the whole input; exit status still reflects any-match.
echo "$home" | grep -ciE 'different desks|the receipts|tuesday' >/dev/null && ok "home: evidence design present" || bad "home: evidence markers missing"
echo "$home" | grep -c  'Public forward track record'       >/dev/null && ok "home: live track-record preview present" || bad "home: live track-record preview MISSING"
ledger_rows=$(printf '%s\n' "$home" | grep -o 'class="ledger-row ledger-grid"' | wc -l)
[ "$ledger_rows" = 8 ] && ok "home: live ledger preview has 8 rows" || bad "home: live ledger preview has $ledger_rows rows (want 8)"
echo "$home" | grep -c  'Open the Full Public Track Record' >/dev/null && ok "home: full track-record CTA present" || bad "home: full track-record CTA MISSING"
echo "$home" | grep -c  'Seasonal projection based on your chosen time frame' >/dev/null && ok "home: chosen-time-frame projection label" || bad "home: chosen-time-frame projection label MISSING"
echo "$home" | grep -c  'Seasonal projection based on all available data' >/dev/null && ok "home: all-data projection label" || bad "home: all-data projection label MISSING"
echo "$home" | grep -c  'Target Hit means the predicted return was reached and the trade was exited for a win.' >/dev/null && ok "home: Target Hit definition" || bad "home: Target Hit definition MISSING"
echo "$home" | grep -c  'Different Desks. One Standard of Proof.' >/dev/null && ok "home: audience heading" || bad "home: audience heading MISSING"
echo "$home" | grep -c  'fund running thousands of backtests' >/dev/null && ok "home: audience scale copy" || bad "home: audience scale copy MISSING"
echo "$home" | grep -c  'Is TradeWave a signal service? Does it tell me what to buy?' >/dev/null && ok "home: updated FAQ question" || bad "home: updated FAQ question MISSING"
echo "$home" | grep -c  'TradeWave is a research tool, not a signal service.' >/dev/null && ok "home: updated FAQ answer" || bad "home: updated FAQ answer MISSING"
echo "$home" | grep -c  'Trade<b>Wave</b>'                  >/dev/null && ok "home: 2-color logo"           || warn "home: 2-color logo markup not found"
echo "$home" | grep -ciE '>Wave Viewer<|>Start Free Trial<' >/dev/null && ok "home: unified nav"            || warn "home: nav markers not found"
for href in \
  "https://$DEVHOST" \
  "https://$DEVHOST/docs/quickstart.html" \
  "https://$DEVHOST/mcp"
do
  echo "$home" | grep -F "href=\"$href\"" >/dev/null \
    && ok "home footer: $href" \
    || bad "home footer: missing $href"
done
echo "$home" | grep -F 'href="/insights/"' >/dev/null \
  && ok "home footer: Insights" \
  || bad "home footer: Insights link missing"
if echo "$home" | grep -cE 'gtag\(|googletagmanager|G-[A-Z0-9]{6,}' >/dev/null; then ok "home: GA4 loader present"; else
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
