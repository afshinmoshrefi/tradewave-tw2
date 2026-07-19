#!/usr/bin/env bash
# deploy.sh — promote current origin/main to one environment.
# Run from the DEV box (.176), after: commit + push  (and `npm run build` if web-react/ changed).
#
#   bash ops/deploy.sh staging     # then check https://tw2-stage.trxstat.com
#   bash ops/deploy.sh prod        # then check https://tradewave.ai
#
# Does, in order, and stops on any error:
#   1. pre-flight  — aborts if TW2_PUBLIC_HOST is unset (would break URLs), or (staging) if
#                    TW2_API/DEVELOPERS/MCP_PUBLIC_HOST are missing or a dev host (portal leak)
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
  staging) WEB=185.53.209.8;    APP=199.244.48.157;  HOST=tw2-stage.trxstat.com
           WEB_VLAN=10.0.0.94; WEB_NGINX_SITE=tw2-stage-web; APP_NGINX_SITE=tw2-stage-app
           APIHOST=api-stage.trxstat.com; DEVHOST=developers-stage.trxstat.com; MCPHOST=mcp-stage.trxstat.com ;;
  prod)    WEB=194.113.195.141; APP=138.128.240.115; HOST=tradewave.ai
           WEB_VLAN=10.0.0.98; WEB_NGINX_SITE=tw2-prod-web; APP_NGINX_SITE=tw2-prod-app
           APIHOST=api.tradewave.ai;      DEVHOST=developers.tradewave.ai;      MCPHOST=mcp.tradewave.ai ;;
  *) echo "usage: $0 {staging|prod}"; exit 2 ;;
esac
ENV="$1"; SSH="ssh -p 4369"
# The live dev checkout can contain unrelated in-progress work.  Permit release
# orchestration from a separate clean worktree while keeping /home/flask as the
# normal default for operators and automation.
DEPLOY_REPO="${TW2_DEPLOY_REPO:-/home/flask}"
BUILD="$DEPLOY_REPO/web-react/build"

# Pin the deployment to one reviewed commit. A local-only commit, a later main
# update, a dirty target, or a React bundle built from another SHA all fail before
# any remote state is changed.
EXPECTED_SHA="${TW2_DEPLOY_SHA:-$(git -C "$DEPLOY_REPO" rev-parse HEAD)}"
case "$EXPECTED_SHA" in *[!0-9a-f]*|'') echo "ABORT: TW2_DEPLOY_SHA must be a full lowercase commit SHA"; exit 1 ;; esac
[ "${#EXPECTED_SHA}" -eq 40 ] || { echo "ABORT: expected a full 40-character deploy SHA"; exit 1; }
[ -z "$(git -C "$DEPLOY_REPO" status --porcelain --untracked-files=normal)" ] || {
  echo "ABORT: local release worktree is dirty; commit or remove release artifacts first."; exit 1;
}
REMOTE_MAIN="$(git -C "$DEPLOY_REPO" ls-remote origin refs/heads/main | awk '{print $1}')"
[ "$REMOTE_MAIN" = "$EXPECTED_SHA" ] || {
  echo "ABORT: intended SHA is not the current origin/main; push/merge the reviewed release first."; exit 1;
}
[ -d "$BUILD/static" ] || { echo "ERROR: $BUILD missing - run 'bash ops/build_react_release.sh' first."; exit 1; }
[ -r "$BUILD/.tradewave-source-sha" ] || {
  echo "ABORT: React build has no provenance marker; run bash ops/build_react_release.sh."; exit 1;
}
[ "$(tr -d '[:space:]' <"$BUILD/.tradewave-source-sha")" = "$EXPECTED_SHA" ] || {
  echo "ABORT: React build provenance does not match the intended release SHA."; exit 1;
}
REL="${EXPECTED_SHA:0:12}"

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

echo "==> [$ENV] pre-flight: TW2_ENV is explicit in secrets.env on both boxes?"
check_tw2_env() {
  local box="$1" val
  val=$($SSH "root@$box" "grep -m1 '^TW2_ENV=' /etc/tradewave/secrets.env 2>/dev/null | cut -d= -f2-")
  [ "$val" = "$ENV" ] || {
    echo "ABORT: TW2_ENV=${val:-<unset>} on $box; expected TW2_ENV=$ENV."
    echo "       Put TW2_ENV=$ENV in /etc/tradewave/secrets.env (cron does not inherit systemd overrides)."
    exit 1
  }
  echo "    $box -> TW2_ENV=$val"
}
check_tw2_env "$WEB"
check_tw2_env "$APP"

echo "==> [$ENV] pre-flight: developer-portal hosts are config-driven (no dev-host leak)?"
# The portal bakes TW2_API/DEVELOPERS/MCP_PUBLIC_HOST into PUBLISHED artifacts (openapi.json
# `servers`, docs back-links, MCP setup). portal_urls now REFUSES to fall back to a dev host,
# so catch a missing/dev value HERE - before any tier deploys - and say exactly what to set.
check_portal_host() {  # check_portal_host <box> <key> <required-value-for-this-env>
  local box="$1" key="$2" want="$3" val
  val=$($SSH "root@$box" "grep -m1 '^$key=' /etc/tradewave/secrets.env 2>/dev/null | cut -d= -f2-")
  if [ -z "$val" ]; then
    echo "ABORT: $key is not set on $box."
    echo "       Footer/portal generation would fail (portal_urls refuses a dev fallback)."
    echo "       Add to /etc/tradewave/secrets.env on $box:   $key=$want"
    exit 1
  fi
  case "$val" in
    *-dev.*|*tw2-dev*|*127.0.0.1*|*10.0.0.*|*192.168.*)
      echo "ABORT: $key=$val on $box is a DEV/internal host."
      echo "       It would leak into the published portal (openapi.json, docs, MCP manifest)."
      echo "       Set the [$ENV] host in /etc/tradewave/secrets.env on $box:   $key=$want"
      exit 1 ;;
  esac
  if [ "$val" != "$want" ]; then
    echo "ABORT: $key=$val on $box, but [$ENV] requires $want."
    echo "       Cross-environment API/MCP/developer hosts can misroute OAuth and customer traffic."
    echo "       Set exactly:   $key=$want"
    exit 1
  fi
  echo "    $box -> $key=$val"
}
# Both tiers import portal_urls: WEB bakes the main-site footer and APP bakes
# docs/OpenAPI/MCP discovery.  Validate the same exact matrix before either
# tier is changed. Prod included since the API/MCP launch.
for box in "$WEB" "$APP"; do
  check_portal_host "$box" TW2_API_PUBLIC_HOST         "$APIHOST"
  check_portal_host "$box" TW2_DEVELOPERS_PUBLIC_HOST  "$DEVHOST"
  check_portal_host "$box" TW2_MCP_PUBLIC_HOST         "$MCPHOST"
done

echo "==> [$ENV] pre-flight: MCP launch state is live on both publishing tiers?"
# WEB uses this flag for the main-site MCP claims; APP uses it while rendering the
# developer setup guide. A split value published a live connector page alongside a
# contradictory "has not launched" banner in production, so require the launched
# state on both boxes before changing either worktree.
for box in "$WEB" "$APP"; do
  $SSH "root@$box" "grep -Eiq '^TW2_MCP_LIVE=(1|true|yes)$' /etc/tradewave/secrets.env" || {
    echo "ABORT: TW2_MCP_LIVE is not enabled on $box."
    echo "       MCP is launched in [$ENV]; set TW2_MCP_LIVE=1 in /etc/tradewave/secrets.env on both tiers."
    exit 1
  }
  echo "    $box -> TW2_MCP_LIVE=1"
done

echo "==> [$ENV] pre-flight: WorkOS MCP issuer matches the web client and supports registration?"
workos_issuer=""
for box in "$WEB" "$APP"; do
  issuer=$($SSH "root@$box" "grep -m1 '^WORKOS_AUTHKIT_DOMAIN=' /etc/tradewave/secrets.env 2>/dev/null | cut -d= -f2-")
  [ -n "$issuer" ] || { echo "ABORT: WORKOS_AUTHKIT_DOMAIN is missing on $box."; exit 1; }
  case "$issuer" in http://*|https://*) ;; *) issuer="https://$issuer" ;; esac
  issuer="${issuer%/}"
  if [ -n "$workos_issuer" ] && [ "$issuer" != "$workos_issuer" ]; then
    echo "ABORT: production tiers disagree on WORKOS_AUTHKIT_DOMAIN ($workos_issuer vs $issuer)."
    exit 1
  fi
  workos_issuer="$issuer"
  echo "    $box -> WORKOS_AUTHKIT_DOMAIN=$issuer"
done

# The web login's WorkOS redirect is authoritative for the environment assigned to
# WORKOS_CLIENT_ID. Comparing it catches a plausible-looking but wrong AuthKit domain,
# which otherwise leaves Claude with no DCR endpoint before login even begins.
web_login_location=$($SSH "root@$WEB" "curl -sSI -H 'Host: $HOST' http://127.0.0.1/login | tr -d '\r' | grep -i '^Location:' | head -1 | cut -d' ' -f2-")
[ -n "$web_login_location" ] || { echo "ABORT: could not resolve the WEB WorkOS login redirect."; exit 1; }
authkit_location=$(curl -sSI --max-time 15 "$web_login_location" | tr -d '\r' | grep -i '^Location:' | head -1 | cut -d' ' -f2-)
actual_workos_issuer=$(printf '%s' "$authkit_location" | sed -E 's#^(https://[^/]+).*#\1#')
[ "$actual_workos_issuer" = "$workos_issuer" ] || {
  echo "ABORT: WORKOS_AUTHKIT_DOMAIN=$workos_issuer, but the [$ENV] web client belongs to $actual_workos_issuer."
  echo "       Correct WORKOS_AUTHKIT_DOMAIN on both tiers before publishing MCP OAuth metadata."
  exit 1
}
workos_metadata=$(curl -fsS --max-time 15 "$workos_issuer/.well-known/oauth-authorization-server") || {
  echo "ABORT: cannot read WorkOS OAuth metadata from $workos_issuer."; exit 1;
}
printf '%s' "$workos_metadata" | grep -q '"registration_endpoint"' || {
  echo "ABORT: WorkOS Dynamic Client Registration is not published for $workos_issuer."; exit 1;
}
printf '%s' "$workos_metadata" | grep -Eq '"client_id_metadata_document_supported"[[:space:]]*:[[:space:]]*true' || {
  echo "ABORT: WorkOS Client ID Metadata Document support is not published for $workos_issuer."; exit 1;
}
echo "    OK - issuer matches the web client; DCR + CIMD are published"

echo "==> [$ENV] pre-flight: split-tier runtime files and API console are complete?"
$SSH "root@$APP" "sudo -u flask test -r /etc/tradewave/appserver.env && grep -Fqx 'TW2_FEATURED_HISTORY_URL=http://$WEB_VLAN:5500/internal/featured-history' /etc/tradewave/secrets.env && grep -q '^TW2_DEVELOPER_PORT=8080$' /etc/tradewave/secrets.env" || {
  echo "ABORT: APP needs readable appserver.env, WEB-VLAN :5500 featured URL, and developer port 8080."; exit 1;
}
$SSH "root@$APP" "test -x /home/flask/venv-api/bin/python" || {
  echo "ABORT: APP venv-api is not provisioned; run the API/MCP bootstrap before this release."; exit 1;
}
$SSH "root@$WEB" "grep -Eq '^TW2_API_CONSOLE_ENABLED=(1|true|yes)$' /etc/tradewave/secrets.env" || {
  echo "ABORT: TW2_API_CONSOLE_ENABLED is not enabled on WEB."; exit 1;
}
$SSH "root@$WEB" "grep -Eq '^TW2_API_BILLING_PORTAL_CONFIGURATION_ID=bpc_[A-Za-z0-9_]+$' /etc/tradewave/secrets.env && ! grep -Eiq '^TW2_API_BILLING_PORTAL_CONFIGURATION_ID=.*PLACEHOLDER' /etc/tradewave/secrets.env" || {
  echo "ABORT: dedicated API Billing Portal configuration is missing or still a placeholder on WEB."; exit 1;
}

echo "==> [$ENV] pre-flight: configured service key maps to exactly one service-account row?"
# This check runs before either worktree is changed or any caller is quiesced. It
# intentionally prints neither the configured key nor its derived HMAC. A fresh
# staging/prod schema does not seed this row; provision it explicitly with
# `web/db_admin.py ensure-service-account` on APP before attempting the cutover.
$SSH "root@$APP" 'set -a; . /etc/tradewave/secrets.env; . /etc/tradewave/appserver.env; set +a; exec /home/flask/venv-api/bin/python -' <<'SERVICE_ACCOUNT_PREFLIGHT'
import hashlib
import hmac
import os
import sys

import psycopg2

service_key = os.environ.get("SERVICE_API_KEY", "")
hmac_secret = (
    os.environ.get("API_KEY_HMAC_SECRET", "")
    or os.environ.get("APPSERVER_JWT_SECRET", "")
)
dsn = os.environ.get("POSTGRES_DSN", "")
if len(service_key) < 16 or not hmac_secret or not dsn:
    sys.stderr.write("ABORT: service-account preflight configuration is incomplete.\n")
    raise SystemExit(1)

key_hash = hmac.new(
    hmac_secret.encode("utf-8"),
    service_key.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
conn = None
try:
    conn = psycopg2.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT roles FROM users WHERE api_key_hash = %s", (key_hash,))
        rows = cur.fetchall()
except Exception:
    # Do not echo exception text: connection failures may serialize a credentialed DSN.
    sys.stderr.write("ABORT: service-account preflight could not query the database.\n")
    raise SystemExit(1)
finally:
    if conn is not None:
        conn.close()

if len(rows) != 1:
    sys.stderr.write(
        "ABORT: configured service key must match exactly one database row; "
        "run ensure-service-account on APP.\n"
    )
    raise SystemExit(1)
roles = rows[0][0]
if not isinstance(roles, list) or not any(
    isinstance(role, str) and hmac.compare_digest(role, "service_account")
    for role in roles
):
    sys.stderr.write(
        "ABORT: configured service key row lacks the service_account role; "
        "run ensure-service-account on APP.\n"
    )
    raise SystemExit(1)
print("    service-account identity OK")
SERVICE_ACCOUNT_PREFLIGHT

# The consumer MCP key is a separate delegation principal from SERVICE_API_KEY.
# Validate its durable identity too: if the key exists but loses service_account,
# OAuth still succeeds while every request silently resolves as Explorer/free.
$SSH "root@$APP" 'set -a; . /etc/tradewave/secrets.env; set +a; exec /home/flask/venv-api/bin/python -' <<'MCP_SERVICE_ACCOUNT_PREFLIGHT'
import hashlib
import hmac
import os
import sys

import psycopg2

mcp_key = os.environ.get("MCP_GATEWAY_KEY", "")
hmac_secret = (
    os.environ.get("API_KEY_HMAC_SECRET", "")
    or os.environ.get("APPSERVER_JWT_SECRET", "")
)
dsn = os.environ.get("POSTGRES_DSN", "")
if len(mcp_key) < 16 or not hmac_secret or not dsn:
    sys.stderr.write("ABORT: MCP service-account preflight configuration is incomplete.\n")
    raise SystemExit(1)

key_hash = hmac.new(
    hmac_secret.encode("utf-8"),
    mcp_key.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
conn = None
try:
    conn = psycopg2.connect(dsn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.api_tier, u.roles "
            "FROM api_keys k JOIN users u ON u.id = k.user_id "
            "WHERE k.key_hash = %s AND k.revoked_at IS NULL",
            (key_hash,),
        )
        rows = cur.fetchall()
except Exception:
    # Do not echo exception text: connection failures may serialize a credentialed DSN.
    sys.stderr.write("ABORT: MCP service-account preflight could not query the database.\n")
    raise SystemExit(1)
finally:
    if conn is not None:
        conn.close()

if len(rows) != 1:
    sys.stderr.write(
        "ABORT: configured MCP gateway key must match exactly one active API-key row; "
        "run apiserver.provision_mcp_key on APP.\n"
    )
    raise SystemExit(1)
api_tier, roles = rows[0]
has_service_role = isinstance(roles, list) and any(
    isinstance(role, str) and hmac.compare_digest(role, "service_account")
    for role in roles
)
if not hmac.compare_digest(str(api_tier or ""), "mcp") or not has_service_role:
    sys.stderr.write(
        "ABORT: configured MCP gateway key lacks the mcp tier or service_account role; "
        "run apiserver.provision_mcp_key on APP.\n"
    )
    raise SystemExit(1)
print("    MCP service-account identity OK")
MCP_SERVICE_ACCOUNT_PREFLIGHT

echo "==> [$ENV] pre-flight: both target worktrees are clean and see the intended origin/main?"
for box in "$APP" "$WEB"; do
  $SSH "root@$box" "EXPECTED_SHA='$EXPECTED_SHA' bash -s" <<'REMOTE_PREFLIGHT'
set -euo pipefail
repo=/home/flask
[ -d "$repo/.git" ] || { echo "ABORT: /home/flask is not a Git worktree"; exit 1; }
[ "$(sudo -u flask git -C "$repo" branch --show-current)" = main ] || { echo "ABORT: target worktree is not on main"; exit 1; }
[ -z "$(sudo -u flask git -C "$repo" status --porcelain --untracked-files=normal)" ] || { echo "ABORT: target worktree is dirty"; exit 1; }
remote_main="$(sudo -u flask git -C "$repo" ls-remote origin refs/heads/main | awk '{print $1}')"
[ "$remote_main" = "$EXPECTED_SHA" ] || { echo "ABORT: target origin/main differs from intended SHA"; exit 1; }
REMOTE_PREFLIGHT
done

echo "==> [$ENV] pre-flight: APP was resized and both boxes have disk headroom?"
$SSH "root@$APP" 'cpu=$(nproc); mem_kb=$(awk "/^MemTotal:/{print \$2}" /proc/meminfo); [ "$cpu" -ge 4 ] && [ "$mem_kb" -ge 7000000 ]' || {
  echo "ABORT: APP needs the planned >=4 CPU / ~8 GB resize before deployment."; exit 1;
}
for box in "$APP" "$WEB"; do
  $SSH "root@$box" 'root_blocks=$(df -Pk / | awk "NR==2{print \$2}"); root_free=$(df -Pk / | awk "NR==2{print \$4}"); [ "$root_free" -ge 2097152 ] && [ $((root_free * 100 / root_blocks)) -ge 10 ]' || {
    echo "ABORT: $box needs >=2 GB and >=10% free root disk before deployment."; exit 1;
  }
done

SERVICE_LOGIN_STAMP=/var/lib/tradewave/release-gates/service-login-header-v1
if $SSH "root@$APP" "test -f $SERVICE_LOGIN_STAMP"; then
  SERVICE_LOGIN_CUTOVER=0
else
  SERVICE_LOGIN_CUTOVER=1
  [ "${TW2_SERVICE_LOGIN_CUTOVER:-}" = 1 ] || {
    echo "ABORT: this target still needs the one-time pathless service-login cutover."
    echo "       Review ops/SERVICE_LOGIN_CUTOVER.md, then rerun with TW2_SERVICE_LOGIN_CUTOVER=1."
    exit 1
  }
fi

echo "==> [$ENV] sync the exact release to APP without restarting callers"
$SSH "root@$APP" "EXPECTED_SHA='$EXPECTED_SHA' APP_NGINX_SITE='$APP_NGINX_SITE' WEB_VLAN='$WEB_VLAN' bash -s" <<'REMOTE_APP_SYNC'
set -euo pipefail
repo=/home/flask
[ -z "$(sudo -u flask git -C "$repo" status --porcelain --untracked-files=normal)" ] || { echo "ABORT: APP worktree is dirty"; exit 1; }
sudo -u flask git -C "$repo" fetch origin main
[ "$(sudo -u flask git -C "$repo" rev-parse origin/main)" = "$EXPECTED_SHA" ] || { echo "ABORT: APP origin/main differs from intended SHA"; exit 1; }
sudo -u flask git -C "$repo" merge --ff-only "$EXPECTED_SHA"
[ "$(sudo -u flask git -C "$repo" rev-parse HEAD)" = "$EXPECTED_SHA" ] || { echo "ABORT: APP did not reach intended SHA"; exit 1; }
[ -z "$(sudo -u flask git -C "$repo" status --porcelain --untracked-files=normal)" ] || { echo "ABORT: APP worktree became dirty"; exit 1; }
test -r /etc/tradewave/appserver.env || { echo "ABORT: /etc/tradewave/appserver.env missing"; exit 1; }
grep -Fqx "TW2_FEATURED_HISTORY_URL=http://$WEB_VLAN:5500/internal/featured-history" /etc/tradewave/secrets.env || { echo "ABORT: APP featured-history URL is not the expected WEB VLAN :5500 feed"; exit 1; }
sudo -u flask "$repo/venv/bin/pip" install -q -r "$repo/requirements.txt"
install -m 0644 "$repo/ops/systemd/tradewave-appserver.service" /etc/systemd/system/tradewave-appserver.service
if [ -d "$repo/venv-api" ]; then
  sudo -u flask "$repo/venv-api/bin/pip" install -q -r "$repo/requirements-api.txt"
  set -a; . /etc/tradewave/secrets.env; set +a
  psql "$POSTGRES_DSN" -v ON_ERROR_STOP=1 -f "$repo/apiserver/schema.sql"
  for u in tradewave-apiserver tradewave-mcpserver; do install -m 0644 "$repo/ops/systemd/$u.service" "/etc/systemd/system/$u.service"; done
fi
systemctl daemon-reload
bash "$repo/ops/install_developer_portal_nginx.sh"
if [ -f "/etc/nginx/sites-available/$APP_NGINX_SITE" ]; then
  bash "$repo/ops/install_safe_nginx_logging.sh" "/etc/nginx/sites-available/$APP_NGINX_SITE"
fi
REMOTE_APP_SYNC

echo "==> [$ENV] sync the same release to WEB without restarting callers"
$SSH "root@$WEB" "EXPECTED_SHA='$EXPECTED_SHA' WEB_VLAN='$WEB_VLAN' bash -s" <<'REMOTE_WEB_SYNC'
set -euo pipefail
repo=/home/flask
[ -z "$(sudo -u flask git -C "$repo" status --porcelain --untracked-files=normal)" ] || { echo "ABORT: WEB worktree is dirty"; exit 1; }
sudo -u flask git -C "$repo" fetch origin main
[ "$(sudo -u flask git -C "$repo" rev-parse origin/main)" = "$EXPECTED_SHA" ] || { echo "ABORT: WEB origin/main differs from intended SHA"; exit 1; }
sudo -u flask git -C "$repo" merge --ff-only "$EXPECTED_SHA"
[ "$(sudo -u flask git -C "$repo" rev-parse HEAD)" = "$EXPECTED_SHA" ] || { echo "ABORT: WEB did not reach intended SHA"; exit 1; }
[ -z "$(sudo -u flask git -C "$repo" status --porcelain --untracked-files=normal)" ] || { echo "ABORT: WEB worktree became dirty"; exit 1; }
sudo -u flask "$repo/venv/bin/pip" install -q -r "$repo/requirements.txt"
sudo -u flask bash "$repo/ops/migrate.sh"
bash "$repo/ops/install_mailerlite_lifecycle_cron.sh"
bash "$repo/ops/install_webinar_cron.sh"
sed "s|__TW2_WEB_VLAN__|$WEB_VLAN|g" "$repo/ops/systemd/tradewave-web.service" >/etc/systemd/system/tradewave-web.service
grep -q -- "--bind 127.0.0.1:5500" /etc/systemd/system/tradewave-web.service
grep -q -- "--bind $WEB_VLAN:5500" /etc/systemd/system/tradewave-web.service
systemctl daemon-reload
REMOTE_WEB_SYNC

if [ "$SERVICE_LOGIN_CUTOVER" -eq 1 ]; then
  echo "==> [$ENV] one-time bounded pathless service-login cutover"
  WEB_QUIESCED=0
  APP_SWITCH_STARTED=0
  recover_service_login_cutover() {
    rc=$?
    trap - ERR INT TERM
    safe_to_resume=1
    if [ "$APP_SWITCH_STARTED" -eq 1 ]; then
      # Once APP switching was attempted, resume callers only if the NEW header
      # handshake can be proven. A broken new appserver stays fail-closed.
      set +e
      $SSH "root@$APP" 'systemctl is-active --quiet tradewave-appserver && . /etc/tradewave/appserver.env && app_port="${TW2_APPSERVER_BIND##*:}" && curl -fsS "http://127.0.0.1:$app_port/healthz" >/dev/null && sudo -u flask bash -c '\''set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask; /home/flask/venv-api/bin/python -c "from apiserver.appserver_client import _get_token; assert _get_token()"'\''' >/dev/null 2>&1
      [ "$?" -eq 0 ] || safe_to_resume=0
      set -e
    fi
    if [ "$safe_to_resume" -eq 1 ]; then
      echo "!!! cutover failed; safely resuming services recorded as previously active"
      set +e
      $SSH "root@$APP" 'for u in tradewave-apiserver tradewave-mcpserver tradewave-blog-queue tradewave-article-processor; do if [ -f "/run/tradewave-cutover/$u" ]; then systemctl start "$u"; fi; done; rm -rf /run/tradewave-cutover'
      $SSH "root@$WEB" 'for u in tradewave-web tradewave-blog-queue tradewave-article-processor; do if [ -f "/run/tradewave-cutover/$u" ]; then systemctl start "$u"; fi; done; if [ -f /run/tradewave-cutover/cron ]; then systemctl start cron; fi; rm -rf /run/tradewave-cutover'
      set -e
    else
      echo "!!! new appserver/header canary is unhealthy; callers remain stopped (fail-closed)."
      set +e
      $SSH "root@$APP" 'systemctl stop tradewave-apiserver tradewave-mcpserver tradewave-blog-queue tradewave-article-processor'
      $SSH "root@$WEB" 'systemctl stop tradewave-web tradewave-blog-queue tradewave-article-processor cron'
      set -e
    fi
    exit "$rc"
  }
  trap recover_service_login_cutover ERR INT TERM
  # Stop scheduled/manual caller processes before the old route disappears. No old
  # long-lived WEB/API process can issue /login/api/<key> during the transition.
  $SSH "root@$WEB" 'bash -s' <<'REMOTE_WEB_QUIESCE'
set -euo pipefail
install -d -m 0755 /run/tradewave-cutover
if systemctl is-active --quiet cron; then touch /run/tradewave-cutover/cron; systemctl stop cron; fi
for u in tradewave-web tradewave-blog-queue tradewave-article-processor; do
  if systemctl is-active --quiet "$u"; then touch "/run/tradewave-cutover/$u"; systemctl stop "$u"; fi
done
deadline=$((SECONDS + 60))
while pgrep -f '/home/flask/(ops/regen_site\.sh|site/[^ ]*(generate_|home_opportunities))' >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "ABORT: a site generator did not quiesce within 60s"; exit 1; }
  sleep 1
done
REMOTE_WEB_QUIESCE
  WEB_QUIESCED=1
  APP_SWITCH_STARTED=1
  $SSH "root@$APP" 'bash -s' <<'REMOTE_APP_QUIESCE'
set -euo pipefail
install -d -m 0755 /run/tradewave-cutover
for u in tradewave-apiserver tradewave-mcpserver tradewave-blog-queue tradewave-article-processor; do
  if systemctl is-active --quiet "$u"; then touch "/run/tradewave-cutover/$u"; systemctl stop "$u"; fi
done
systemctl restart tradewave-appserver
systemctl is-active --quiet tradewave-appserver
. /etc/tradewave/appserver.env
app_port="${TW2_APPSERVER_BIND##*:}"
curl -fsS "http://127.0.0.1:$app_port/healthz" >/dev/null
sudo -u flask bash -c 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask; /home/flask/venv-api/bin/python -c "from apiserver.appserver_client import _get_token; assert _get_token(); print(\"service login header canary OK\")"'
for u in tradewave-apiserver tradewave-mcpserver; do
  systemctl start "$u"; systemctl is-active --quiet "$u"
done
for u in tradewave-blog-queue tradewave-article-processor; do
  if [ -f "/run/tradewave-cutover/$u" ]; then systemctl start "$u"; systemctl is-active --quiet "$u"; fi
done
if systemctl is-active --quiet tradewave-apiserver; then curl -fsS http://127.0.0.1:8088/healthz >/dev/null; fi
REMOTE_APP_QUIESCE
  $SSH "root@$WEB" 'bash -s' <<'REMOTE_WEB_RESUME'
set -euo pipefail
for u in tradewave-web tradewave-blog-queue tradewave-article-processor; do
  if [ -f "/run/tradewave-cutover/$u" ]; then systemctl start "$u"; systemctl is-active --quiet "$u"; fi
done
if [ -f /run/tradewave-cutover/cron ]; then systemctl start cron; fi
rm -rf /run/tradewave-cutover
REMOTE_WEB_RESUME
  $SSH "root@$APP" "install -d -m 0755 '$(dirname "$SERVICE_LOGIN_STAMP")' && touch '$SERVICE_LOGIN_STAMP' && rm -rf /run/tradewave-cutover"
  WEB_QUIESCED=0
  APP_SWITCH_STARTED=0
  trap - ERR INT TERM
else
  echo "==> [$ENV] restart APP/API/MCP and WEB from the pinned release"
  $SSH "root@$APP" 'systemctl restart tradewave-appserver && systemctl is-active tradewave-appserver && . /etc/tradewave/appserver.env && app_port="${TW2_APPSERVER_BIND##*:}" && curl -fsS "http://127.0.0.1:$app_port/healthz" >/dev/null && for u in tradewave-apiserver tradewave-mcpserver; do if systemctl cat "$u" >/dev/null 2>&1; then systemctl restart "$u" && systemctl is-active "$u"; fi; done && if systemctl is-active --quiet tradewave-apiserver; then curl -fsS http://127.0.0.1:8088/healthz >/dev/null; fi'
  $SSH "root@$WEB" 'systemctl restart tradewave-web && systemctl is-active tradewave-web && for u in tradewave-blog-queue tradewave-article-processor; do if systemctl cat "$u" >/dev/null 2>&1; then systemctl restart "$u"; fi; done'
fi

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
echo "==> [$ENV] React bundle -> $WEB (release build-$REL; repoint build symlink; build-previous = rollback)"
rsync -az -e "$SSH" "$BUILD/" "root@$WEB:/home/flask/web-react/releases/build-$REL/"
$SSH "root@$WEB" "cd /home/flask/web-react && test \"\$(tr -d '[:space:]' < releases/build-$REL/.tradewave-source-sha)\" = '$EXPECTED_SHA' && chown -R flask:flask releases/build-$REL && ln -sfn \"\$(readlink build)\" build-previous && ln -sfn releases/build-$REL build && chown -h flask:flask build build-previous"

echo "==> [$ENV] nginx CSP snippet + reload"
# The per-box site config (/etc/nginx/sites-enabled/tw2-<env>-web) is managed ON
# the box (server_name, etc.) and is NOT shipped from the repo: copying the repo's
# 'tradewave' config alongside it duplicates 'upstream tw2_web' and breaks nginx.
# Route rules like /affiliate/sign/ are added to that per-box file ONCE (see
# PROD_CUTOVER affiliate checklist). Deploy only refreshes the shared CSP snippet;
# nginx -t gates the reload (fail-closed).
$SSH "root@$WEB" "sudo cp /home/flask/ops/nginx/snippets/security_headers.conf /etc/nginx/snippets/security_headers.conf && sudo bash /home/flask/ops/install_safe_nginx_logging.sh '/etc/nginx/sites-available/$WEB_NGINX_SITE'"

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
if [ -x "$DEPLOY_REPO/ops/verify_deploy.sh" ]; then
  if bash "$DEPLOY_REPO/ops/verify_deploy.sh" "$ENV"; then
    echo "==> [$ENV] DONE + VERIFIED CLEAN. Live: https://$HOST"
  else
    echo "!!! [$ENV] DEPLOYED, but verify_deploy reported BLOCKER(S) above."
    echo "!!! The site is live but NOT clean - review, fix, re-run 'bash ops/regen_site.sh' on the box, then 'bash ops/verify_deploy.sh $ENV'."
    exit 1
  fi
else
  echo "==> [$ENV] DONE. (verify_deploy.sh missing - skipped verification.) Live: https://$HOST"
fi
