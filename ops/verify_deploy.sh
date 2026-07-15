#!/usr/bin/env bash
# Whole-site post-deploy gate plus exact paired immutable API/MCP attestation.
# Usage: verify_deploy.sh {staging|prod} <lowercase-40-character-release-sha>
set +x
set -uo pipefail

usage(){
  echo "usage: $0 {staging|prod} <lowercase-40-character-release-sha>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage
ENV=$1
RELEASE_SHA=$2
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || usage

case "$ENV" in
  staging) WEB=185.53.209.8;    APP=199.244.48.157; HOST=tw2-stage.trxstat.com; APIHOST=api-stage.trxstat.com; MCPHOST=mcp-stage.trxstat.com; DEVHOST=developers-stage.trxstat.com; PORTAL=1
           LEAKS='tw2-dev|developers-dev|api-dev|mcp-dev|stage2\.trxstat|192\.168\.|10\.0\.0\.|127\.0\.0\.1|smn-dev' ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tradewave.ai;        APIHOST=api.tradewave.ai;       MCPHOST=mcp.tradewave.ai;       DEVHOST=developers.tradewave.ai; PORTAL=1
           LEAKS='tw2-dev|tw2-stage|developers-dev|developers-stage|api-dev|api-stage|mcp-dev|mcp-stage|stage2\.trxstat|trxstat\.com|192\.168\.|10\.0\.0\.|127\.0\.0\.1|smn-dev|smn-stage' ;;
  *) usage ;;
esac

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 2
PAIRED_VERIFIER=$SCRIPT_DIR/verify_paired_release.sh
[ -f "$PAIRED_VERIFIER" ] && [ ! -L "$PAIRED_VERIFIER" ] \
  || { echo "FAIL: paired immutable verifier is absent: $PAIRED_VERIFIER" >&2; exit 2; }

SSH="ssh -p 4369 -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=2"
fails=0; warns=0
ok(){   echo "  PASS  $*"; }
bad(){  echo "  FAIL  $*"; fails=$((fails+1)); }
warn(){ echo "  WARN  $*"; warns=$((warns+1)); }
wc_web(){ $SSH "root@$WEB" "curl -s -o /dev/null -w '%{http_code}' -H 'Host: $HOST' http://127.0.0.1$1" 2>/dev/null; }
wc_app(){ $SSH "root@$APP" "curl -s -o /dev/null -w '%{http_code}' -H 'Host: $2' http://127.0.0.1:8080$1" 2>/dev/null; }
paired_release_gate(){
  $SSH "root@$APP" bash -s -- "$RELEASE_SHA" "$APIHOST" "$MCPHOST" \
    < "$PAIRED_VERIFIER"
}

echo "==================  verify_deploy [$ENV]  host=$HOST  sha=$RELEASE_SHA  =================="

echo "-- services --"
$SSH "root@$WEB" 'systemctl is-active nginx tradewave-web 2>/dev/null' | grep -qvx active \
  && bad "a WEB service is not active (nginx/tradewave-web)" || ok "WEB: nginx + tradewave-web active"
$SSH "root@$APP" 'systemctl is-active tradewave-appserver tradewave-apiserver tradewave-mcpserver nginx 2>/dev/null' | grep -qvx active \
  && bad "an APP service is not active (appserver/apiserver/mcp/nginx)" || ok "APP: appserver + apiserver + mcp + nginx active"

echo "-- paired immutable API + MCP release --"
if paired_release_gate; then
  ok "paired immutable API/MCP runtime exactly matches $RELEASE_SHA"
else
  bad "paired immutable API/MCP post-commit verification failed"
fi

echo "-- web routes (nginx-direct, Host: $HOST) --"
for r in / /home.html /scorecard.html /research.html /about.html /terms.html /privacy.html /disclaimer.html /methodology.html /insights/ /learn/ /markets/sp500.html /affiliate.html; do
  c=$(wc_web "$r"); [ "$c" = 200 ] && ok "$r -> 200" || bad "$r -> $c (want 200)"
done
c=$(wc_web /markets/);        case "$c" in 200|301|302) ok "/markets/ -> $c" ;; *) bad "/markets/ -> $c (raw 403 = no section index)";; esac
c=$(wc_web /join/TESTCODE);   [ "$c" = 404 ] && bad "/join/TESTCODE -> 404 (nginx 'location /join/' proxy rule missing)" || ok "/join/TESTCODE -> $c (route reaches the app)"
c=$(wc_web /healthz);         [ "$c" = 200 ] && ok "/healthz -> 200" || warn "/healthz -> $c"

echo "-- api + developer portal (app box :8080) --"
c=$(wc_app /healthz "$APIHOST"); [ "$c" = 200 ] && ok "api /healthz -> 200" || bad "api /healthz -> $c"
c=$(wc_app / "$DEVHOST");        [ "$c" = 200 ] && ok "portal / -> 200"     || bad "portal / -> $c"
c=$(wc_app /docs/ "$DEVHOST");   [ "$c" = 200 ] && ok "portal /docs/ -> 200" || bad "portal /docs/ -> $c (403 = no docs index)"

echo "-- host-leak grep (baked HTML/XML must carry only the $ENV host) --"
n=$($SSH "root@$WEB" "grep -rlE '$LEAKS' --include='*.html' --include='*.xml' /var/www/tradewave/ 2>/dev/null | wc -l")
if [ "$n" = 0 ]; then ok "site: 0 files leak a non-$ENV host"; else bad "site: $n file(s) leak a non-$ENV host:"; $SSH "root@$WEB" "grep -rlE '$LEAKS' --include='*.html' --include='*.xml' /var/www/tradewave/ 2>/dev/null | sed 's/^/        /' | head"; fi
n=$($SSH "root@$APP" "grep -rlE '$LEAKS' --include='*.html' --include='*.json' /var/www/developers/ 2>/dev/null | wc -l")
[ "$n" = 0 ] && ok "portal: 0 files leak a non-$ENV host" || { bad "portal: $n file(s) leak a non-$ENV host:"; $SSH "root@$APP" "grep -rlE '$LEAKS' --include='*.html' --include='*.json' /var/www/developers/ 2>/dev/null | sed 's/^/        /' | head"; }

echo "-- design + feature markers --"
# Read generated files from disk: nginx open_file_cache can briefly serve the
# prior page immediately after regeneration and produce false release failures.
home=$($SSH "root@$WEB" "cat /var/www/tradewave/home.html 2>/dev/null")
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
echo "$home" | grep -c  'Trade<b>Wave</b>'                  >/dev/null && ok "home: 2-color logo"           || warn "home: 2-color logo markup not found"
echo "$home" | grep -ciE '>Wave Viewer<|>Start Free Trial<' >/dev/null && ok "home: unified nav"            || warn "home: nav markers not found"
if echo "$home" | grep -cE 'gtag\(|googletagmanager|G-[A-Z0-9]{6,}' >/dev/null; then ok "home: GA4 loader present"; else
  [ "$ENV" = prod ] && bad "home: GA4 loader MISSING (analytics dead on prod)" || warn "home: no GA4 loader (may be prod-gated; confirm it lights on prod)"; fi
if $SSH "root@$WEB" "grep -qiE 'held.to.close|reached.target' /var/www/tradewave/scorecard.html 2>/dev/null"; then
  ok "scorecard: two-metric present"
else
  bad "scorecard: two-metric MISSING (still the old blended metric)"
fi

echo "======  verify_deploy [$ENV]:  $fails FAIL, $warns WARN  ======"
[ "$fails" = 0 ] && echo "RESULT: CLEAN" || echo "RESULT: $fails BLOCKER(S) - do not ship"
exit "$fails"
