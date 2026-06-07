#!/usr/bin/env bash
# deploy.sh — promote current origin/main to one environment.
# Run from the DEV box (.176), after: commit + push  (and `npm run build` if web-react/ changed).
#
#   bash ops/deploy.sh staging     # then check https://tw2-stage.trxstat.com
#   bash ops/deploy.sh prod        # then check https://tw2-prod.trxstat.com
#
# Does, in order, and stops on any error:
#   1. pre-flight  — aborts if TW2_PUBLIC_HOST is unset (would break URLs)
#   2. app tier    — git pull + pip install -r requirements.txt + restart tradewave-appserver
#   2b.app tier    - sync venv-api + restart tradewave-apiserver + tradewave-mcpserver (if provisioned;
#                    guarded so a non-API box does not abort; /healthz gate on the gateway)
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
  staging) WEB=185.53.209.8;    APP=199.244.48.157;  HOST=tw2-stage.trxstat.com ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tw2-prod.trxstat.com ;;
  *) echo "usage: $0 {staging|prod}"; exit 2 ;;
esac
ENV="$1"; SSH="ssh -p 4369"; BUILD=/home/flask/web-react/build

[ -d "$BUILD/static" ] || { echo "ERROR: $BUILD missing — run 'npm run build' on dev first."; exit 1; }

echo "==> [$ENV] pre-flight: TW2_PUBLIC_HOST set on both boxes?"
for box in "$WEB" "$APP"; do
  $SSH "root@$box" "grep -q '^TW2_PUBLIC_HOST=' /etc/tradewave/secrets.env \
      || systemctl show tradewave-web tradewave-appserver -p Environment 2>/dev/null | grep -q TW2_PUBLIC_HOST" \
    || { echo "ABORT: TW2_PUBLIC_HOST not set on $box (expected $HOST). Set it in /etc/tradewave/secrets.env first, or the site falls back to tw2-dev."; exit 1; }
done

echo "==> [$ENV] app tier ($APP): pull + sync venv + restart appserver"
$SSH "root@$APP" 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo systemctl restart tradewave-appserver && sudo systemctl is-active tradewave-appserver'

# API gateway + MCP server are co-located on the app box. New services: guard each so a box
# not yet provisioned for the API (no venv-api / units) does NOT abort the deploy. Provision
# with ops/bootstrap_api_services.sh first; thereafter every deploy syncs + restarts them.
echo "==> [$ENV] app tier ($APP): API gateway + MCP server (if provisioned)"
$SSH "root@$APP" 'if [ -d /home/flask/venv-api ]; then sudo -u flask /home/flask/venv-api/bin/pip install -q -r /home/flask/requirements-api.txt; else echo "skip venv-api sync (not provisioned)"; fi; for u in tradewave-apiserver tradewave-mcpserver; do if systemctl cat "$u" >/dev/null 2>&1; then sudo systemctl restart "$u" && sudo systemctl is-active "$u"; else echo "skip $u (not installed on this box)"; fi; done; if systemctl cat tradewave-apiserver >/dev/null 2>&1; then curl -fsS http://127.0.0.1:8088/healthz >/dev/null && echo "apiserver /healthz OK" || { echo "ABORT: apiserver unhealthy after restart"; exit 1; }; fi'

echo "==> [$ENV] web tier ($WEB): pull + sync venv + DB migrate + restart web + SMN daemons"
# tradewave-web is on every web box; the SMN daemons are only on boxes provisioned
# for content generation (not prod web pre-cutover). Restart web always, SMN if present,
# so a missing optional unit doesn't abort the deploy before the React/nginx steps.
# DB migrate (alembic upgrade head) runs BEFORE the web restart and is fail-closed:
# a failed/needed migration aborts the deploy instead of starting the app against a
# schema it doesn't expect. Idempotent (only unapplied revisions run).
$SSH "root@$WEB" 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo -u flask bash /home/flask/ops/migrate.sh && sudo systemctl restart tradewave-web && for u in tradewave-blog-queue tradewave-article-processor; do if systemctl cat "$u" >/dev/null 2>&1; then sudo systemctl restart "$u"; else echo "skip $u (not installed on this box)"; fi; done && sudo systemctl is-active tradewave-web'

echo "==> [$ENV] web tier ($WEB): regenerate authored static pages (/affiliate, privacy, terms, ...)"
# generate_text_pages.py renders the authored pages (incl. /affiliate) into
# /var/www/tradewave. deploy doesn't otherwise emit static pages, so without this
# a copy change in the generator never reaches the served site (and /affiliate
# 404s on a fresh box). Guarded + fail-closed like the portal step.
$SSH "root@$WEB" 'if [ -f /home/flask/site/generate_text_pages.py ]; then sudo -u flask /home/flask/venv/bin/python /home/flask/site/generate_text_pages.py >/dev/null && echo "static pages regenerated" || { echo "ABORT: static page generation failed"; exit 1; }; else echo "skip static pages (generator not present)"; fi'

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
# It ships "dark" on PROD (the API/MCP product is not launched there), so DON'T build
# it on prod. On staging/dev it assembles as before (for testing). Guarded: skip if the
# box isn't provisioned for the portal.
if [ "$ENV" = "prod" ]; then
  echo "==> [$ENV] web tier ($WEB): SKIP developer portal (API/MCP dark on prod)"
else
  echo "==> [$ENV] web tier ($WEB): assemble developer portal (if provisioned)"
  $SSH "root@$WEB" 'if [ -x /home/flask/ops/assemble_developer_portal.sh ]; then sudo bash /home/flask/ops/assemble_developer_portal.sh || { echo "ABORT: developer portal assembly failed"; exit 1; }; else echo "skip developer portal (assemble script not present)"; fi'
fi

echo "==> [$ENV] DONE. Verify: https://$HOST"
