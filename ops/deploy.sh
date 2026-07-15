#!/usr/bin/env bash
# deploy.sh — promote current origin/main to one environment.
# Run from the DEV box (.176), after: commit + push  (and `npm run build` if web-react/ changed).
#
#   bash ops/deploy.sh staging     # then check https://tw2-stage.trxstat.com
#   bash ops/deploy.sh prod        # then check https://tw2-prod.trxstat.com
#
# Does, in order, and stops on any error:
#   1. pre-flight  — aborts if TW2_PUBLIC_HOST is unset (would break URLs), or (staging) if
#                    TW2_API/DEVELOPERS/MCP_PUBLIC_HOST are missing or a dev host (portal leak)
#   2. app tier    — pin /home/flask to the requested commit + restart only tradewave-appserver
#   2b.paired edge — promote the immutable API gateway + MCP pair through its root launcher
#   3. web tier    — git pull + pip install + alembic upgrade head + restart tradewave-web + the 2 SMN daemons
#   3b.static pages— regenerate authored pages (/affiliate, privacy, terms, …) into /var/www/tradewave
#   4. React       — rsync to releases/build-<hash> + repoint the 'build' symlink (build-previous = instant rollback)
#   5. nginx       — refresh CSP snippet + reload (per-box site config managed on the box)
#   6. dev portal  — re-run the portal generators + rsync into /var/www/developers (if provisioned)
# Provision the API/MCP services + portal docroot ONCE per box with ops/bootstrap_api_services.sh
# (services) and the nginx/cloudflared additions; thereafter every deploy keeps them current.
# Full rationale: ops/OPERATIONS.md "Deploy a code change" + "API/MCP deploy + restart".
set -euo pipefail

case "${1:-}" in
  staging) WEB=185.53.209.8;    APP=199.244.48.157;  HOST=tw2-stage.trxstat.com
           APIHOST=api-stage.trxstat.com; DEVHOST=developers-stage.trxstat.com; MCPHOST=mcp-stage.trxstat.com ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tradewave.ai
           APIHOST=api.tradewave.ai;      DEVHOST=developers.tradewave.ai;      MCPHOST=mcp.tradewave.ai ;;
  *) echo "usage: $0 {staging|prod}"; exit 2 ;;
esac
ENV="$1"; SSH="ssh -p 4369"; BUILD=/home/flask/web-react/build

[ -d "$BUILD/static" ] || { echo "ERROR: $BUILD missing - run 'npm run build' on dev first."; exit 1; }

echo "==> [$ENV] pre-flight: TW2_PUBLIC_HOST == $HOST on BOTH boxes?"
# The WEB box bakes every public page, so it MUST equal the customer host ($HOST =
# the LIVE host: tradewave.ai on prod since the 2026-05-31 cutover - NOT the
# tw2-prod.trxstat.com tunnel placeholder, which is only the box's internal name).
# The APP box is strict everywhere since the 2026-07-04 API/MCP prod launch: the
# apiserver/mcpserver/portal bake TW2_PUBLIC_HOST into published responses.
# Catches stage2.trxstat.com-style drift before anything deploys.
check_host() {  # check_host <box> <strict>
  local box="$1" strict="$2" val
  val=$($SSH "root@$box" "grep -m1 '^TW2_PUBLIC_HOST=' /etc/tradewave/secrets.env 2>/dev/null | cut -d= -f2-")
  [ -n "$val" ] || { echo "ABORT: TW2_PUBLIC_HOST not set on $box. Set it in /etc/tradewave/secrets.env."; exit 1; }
  if [ "$strict" = 1 ] && [ "$val" != "$HOST" ]; then
    echo "ABORT: TW2_PUBLIC_HOST=$val on $box, but [$ENV] expects $HOST."
    echo "       Fix /etc/tradewave/secrets.env there (TW2_PUBLIC_HOST=$HOST + TW2_DOMAIN_ROOT=https://$HOST), then re-run."; exit 1
  fi
  echo "    $box -> TW2_PUBLIC_HOST=$val"
}
check_host "$WEB" 1
# App box is strict on EVERY env since the prod API/MCP launch (2026-07-04): the
# apiserver/mcpserver bake TW2_PUBLIC_HOST into published responses, so a placeholder
# host on the prod app box is no longer harmless.
check_host "$APP" 1
echo "    OK - web box resolves to $HOST"

echo "==> [$ENV] pre-flight: developer-portal hosts are config-driven (no dev-host leak)?"
# The portal bakes TW2_API/DEVELOPERS/MCP_PUBLIC_HOST into PUBLISHED artifacts (openapi.json
# `servers`, docs back-links, MCP setup). portal_urls now REFUSES to fall back to a dev host,
# so catch a missing/dev value HERE - before any tier deploys - and say exactly what to set.
check_portal_host() {  # check_portal_host <key> <recommended-value-for-this-env>
  local key="$1" want="$2" val
  val=$($SSH "root@$APP" "grep -m1 '^$key=' /etc/tradewave/secrets.env 2>/dev/null | cut -d= -f2-")
  if [ -z "$val" ]; then
    echo "ABORT: $key is not set on the APP box ($APP)."
    echo "       The developer portal would fail to assemble (portal_urls refuses a dev fallback)."
    echo "       Add to /etc/tradewave/secrets.env on $APP:   $key=$want"
    exit 1
  fi
  case "$val" in
    *-dev.*|*tw2-dev*|*127.0.0.1*|*10.0.0.*|*192.168.*)
      echo "ABORT: $key=$val on the APP box ($APP) is a DEV/internal host."
      echo "       It would leak into the published portal (openapi.json, docs, MCP manifest)."
      echo "       Set the [$ENV] host in /etc/tradewave/secrets.env on $APP:   $key=$want"
      exit 1 ;;
  esac
  echo "    $APP -> $key=$val"
}
# Prod included since the API/MCP prod launch (2026-07-04) - the dark-ship skip is retired.
check_portal_host TW2_API_PUBLIC_HOST        "$APIHOST"
check_portal_host TW2_DEVELOPERS_PUBLIC_HOST "$DEVHOST"
check_portal_host TW2_MCP_PUBLIC_HOST        "$MCPHOST"

# The app checkout and the sealed pair must name one exact pushed commit. Validate
# this before the first remote mutation; a branch name or abbreviated SHA is not
# release authority.
MCP_RELEASE_SHA=${TW_MCP_RELEASE_SHA:-}
[[ "$MCP_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || { echo "ABORT: set TW_MCP_RELEASE_SHA to the exact lowercase 40-character commit SHA"; exit 1; }

echo "==> [$ENV] app tier ($APP): exact appserver + immutable paired edge $MCP_RELEASE_SHA"
# One remote transaction owns the ordering. On the first migration the launcher
# must snapshot and qualify the live legacy API/MCP bytes before /home/flask moves.
# On later releases appserver moves first so the paired canaries qualify the exact
# gateway/MCP candidate against the newly deployed dependency. No command outside
# the immutable launcher starts, stops, or restarts either edge service.
$SSH "root@$APP" bash -s -- "$MCP_RELEASE_SHA" <<'REMOTE_APP_TIER'
set -euo pipefail
sha=$1
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] \
  || { echo "ABORT: app-tier release target is not an exact lowercase commit SHA" >&2; exit 2; }
checkout=/home/flask
current=/home/tradewave-mcp/current
launcher=/usr/local/sbin/tradewave-mcp-release

[ -x "$launcher" ] && [ ! -L "$launcher" ] \
  || { echo "ABORT: immutable paired release launcher is not installed" >&2; exit 1; }
[ -d "$checkout/.git" ] && [ ! -L "$checkout" ] \
  || { echo "ABORT: /home/flask is not the expected checkout" >&2; exit 1; }
sudo -u flask git -C "$checkout" diff --quiet --
sudo -u flask git -C "$checkout" diff --cached --quiet --
sudo -u flask git -C "$checkout" fetch --no-tags origin main
sudo -u flask git -C "$checkout" cat-file -e "$sha^{commit}"
sudo -u flask git -C "$checkout" merge-base --is-ancestor "$sha" origin/main \
  || { echo "ABORT: requested commit is not reachable from origin/main" >&2; exit 1; }
head=$(sudo -u flask git -C "$checkout" rev-parse HEAD)
sudo -u flask git -C "$checkout" merge-base --is-ancestor "$head" "$sha" \
  || { echo "ABORT: /home/flask cannot fast-forward exactly to requested commit" >&2; exit 1; }

first=0
if [ ! -e "$current" ] && [ ! -L "$current" ]; then
  first=1
elif [ ! -L "$current" ]; then
  echo "ABORT: immutable current release path exists but is not a symlink" >&2
  exit 1
fi

if [ "$first" = 1 ]; then
  "$launcher" "$sha"
fi

sudo -u flask git -C "$checkout" merge --ff-only "$sha"
[ "$(sudo -u flask git -C "$checkout" rev-parse HEAD)" = "$sha" ] \
  || { echo "ABORT: /home/flask did not land on the requested commit" >&2; exit 1; }
sudo -u flask "$checkout/venv/bin/pip" install -q -r "$checkout/requirements.txt"
systemctl restart tradewave-appserver.service
systemctl is-active --quiet tradewave-appserver.service

if [ "$first" = 0 ]; then
  "$launcher" "$sha"
fi
REMOTE_APP_TIER

echo "==> [$ENV] web tier ($WEB): pull + sync venv + DB migrate + restart web + SMN daemons"
# tradewave-web is on every web box; the SMN daemons are only on boxes provisioned
# for content generation (not prod web pre-cutover). Restart web always, SMN if present,
# so a missing optional unit doesn't abort the deploy before the React/nginx steps.
# DB migrate (alembic upgrade head) runs BEFORE the web restart and is fail-closed:
# a failed/needed migration aborts the deploy instead of starting the app against a
# schema it doesn't expect. Idempotent (only unapplied revisions run).
$SSH "root@$WEB" 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo -u flask bash /home/flask/ops/migrate.sh && sudo systemctl restart tradewave-web && for u in tradewave-blog-queue tradewave-article-processor; do if systemctl cat "$u" >/dev/null 2>&1; then sudo systemctl restart "$u"; else echo "skip $u (not installed on this box)"; fi; done && sudo systemctl is-active tradewave-web'

echo "==> [$ENV] web tier ($WEB): regenerate ALL static pages (home, scorecard, insights, learn, research, about, daily-pick, ticker, text, markets)"
# regen_site.sh runs EVERY main-site generator with secrets.env sourced, so each page
# bakes the correct per-env host (never the tw2-dev fallback). This closes the historical
# deploy gap: stock deploy only ran generate_text_pages and home/scorecard/insights/etc.
# waited for the next cron tick, so a code/content change never reached the served site on
# deploy (this is why "the home page looked the same" after a deploy). Runs as flask (output
# stays flask-owned, mirroring the cron pattern: set -a; . secrets.env; set +a; python ...).
# Fail-closed: any generator failure aborts the deploy.
$SSH "root@$WEB" 'if [ -x /home/flask/ops/regen_site.sh ]; then sudo -u flask bash /home/flask/ops/regen_site.sh || { echo "ABORT: site regeneration failed (see /tmp/regen_*.log on the web box)"; exit 1; }; else echo "ABORT: /home/flask/ops/regen_site.sh missing on the web box"; exit 1; fi'

# React deploy = ship a release dir named by source commit, then repoint the `build` SYMLINK.
# `build` is a symlink to releases/build-<hash>; build-previous holds the prior target for instant rollback.
# (One-time per box, already done on stage+prod: mkdir -p releases && mv build releases/build-prev && ln -s releases/build-prev build)
REL=$(git -C /home/flask rev-parse --short HEAD)
echo "==> [$ENV] React bundle -> $WEB (release build-$REL; repoint build symlink; build-previous = rollback)"
rsync -az -e "$SSH" "$BUILD/" "root@$WEB:/home/flask/web-react/releases/build-$REL/"
$SSH "root@$WEB" "cd /home/flask/web-react && chown -R flask:flask releases/build-$REL && ln -sfn \"\$(readlink build)\" build-previous && ln -sfn releases/build-$REL build && chown -h flask:flask build build-previous"

echo "==> [$ENV] nginx CSP snippet + reload"
# The per-box site config (/etc/nginx/sites-enabled/tw2-<env>-web) is managed ON
# the box (server_name, etc.) and is NOT shipped from the repo: copying the repo's
# 'tradewave' config alongside it duplicates 'upstream tw2_web' and breaks nginx.
# Route rules like /affiliate/sign/ are added to that per-box file ONCE (see
# PROD_CUTOVER affiliate checklist). Deploy only refreshes the shared CSP snippet;
# nginx -t gates the reload (fail-closed).
$SSH "root@$WEB" 'sudo cp /home/flask/ops/nginx/snippets/security_headers.conf /etc/nginx/snippets/security_headers.conf && sudo nginx -t && sudo systemctl reload nginx'

# Public developer portal (developers.*) is the API product's marketing/docs site.
# Assembled on EVERY env since the prod API/MCP launch (2026-07-04) - the dark-ship
# skip is retired. Still guarded: skips cleanly if the box isn't provisioned yet.
echo "==> [$ENV] app tier ($APP): assemble developer portal (portal vhost + /var/www/developers live on the APP box, not WEB)"
$SSH "root@$APP" 'if [ -x /home/flask/ops/assemble_developer_portal.sh ]; then sudo bash /home/flask/ops/assemble_developer_portal.sh || { echo "ABORT: developer portal assembly failed"; exit 1; }; else echo "skip developer portal (assemble script not present)"; fi'

echo "==> [$ENV] code+pages deployed. Running post-deploy verification..."
# verify_deploy.sh runs FROM this (dev) box, SSHing to WEB/APP. It fails LOUD on broken
# routes, wrong-host leaks, and undeployed features - turning a silent-bad deploy into a
# visible one. Non-fatal-but-loud: the deploy already applied; a nonzero verify means the
# site is live-but-not-clean, so fix + re-run regen before announcing.
[ -x /home/flask/ops/verify_deploy.sh ] \
  || { echo "ABORT: mandatory /home/flask/ops/verify_deploy.sh is missing"; exit 1; }
if bash /home/flask/ops/verify_deploy.sh "$ENV" "$MCP_RELEASE_SHA"; then
  echo "==> [$ENV] DONE + VERIFIED CLEAN. Live: https://$HOST"
else
  echo "!!! [$ENV] DEPLOYED, but mandatory verification reported BLOCKER(S) above."
  exit 1
fi
