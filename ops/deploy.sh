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
#   3. web tier    — git pull + pip install -r requirements.txt + restart tradewave-web + the 2 SMN daemons
#   4. React       — rsync to releases/build-<hash> + repoint the 'build' symlink (build-previous = instant rollback)
#   5. nginx       — refresh CSP snippet + reload
# Full rationale: ops/OPERATIONS.md "Deploy a code change".
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

echo "==> [$ENV] web tier ($WEB): pull + sync venv + restart web + SMN daemons"
$SSH "root@$WEB" 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo systemctl restart tradewave-web tradewave-blog-queue tradewave-article-processor && sudo systemctl is-active tradewave-web tradewave-blog-queue tradewave-article-processor'

# React deploy = ship a release dir named by source commit, then repoint the `build` SYMLINK.
# `build` is a symlink to releases/build-<hash>; build-previous holds the prior target for instant rollback.
# (One-time per box, already done on stage+prod: mkdir -p releases && mv build releases/build-prev && ln -s releases/build-prev build)
REL=$(git -C /home/flask rev-parse --short HEAD)
echo "==> [$ENV] React bundle -> $WEB (release build-$REL; repoint build symlink; build-previous = rollback)"
rsync -az -e "$SSH" "$BUILD/" "root@$WEB:/home/flask/web-react/releases/build-$REL/"
$SSH "root@$WEB" "cd /home/flask/web-react && chown -R flask:flask releases/build-$REL && ln -sfn \"\$(readlink build)\" build-previous && ln -sfn releases/build-$REL build && chown -h flask:flask build build-previous"

echo "==> [$ENV] nginx CSP snippet + reload"
$SSH "root@$WEB" 'sudo cp /home/flask/ops/nginx/snippets/security_headers.conf /etc/nginx/snippets/security_headers.conf && sudo nginx -t && sudo systemctl reload nginx'

echo "==> [$ENV] DONE. Verify: https://$HOST"
