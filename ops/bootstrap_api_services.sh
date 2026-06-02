#!/usr/bin/env bash
# Stand up the TradeWave API gateway + MCP server ON THE BOX this runs on.
#
# The operator runs this AS root (it writes /etc/systemd, runs systemctl) on the
# target box (dev / staging / prod). It is env-agnostic: every per-env value comes
# from /etc/tradewave/secrets.env, so the SAME script works on every box.
#
# Idempotent: re-running is safe - it creates the venv only if missing, the schema
# is additive (CREATE TABLE IF NOT EXISTS ...), and systemd enable --now is a no-op
# when already running. It echoes every step.
#
# This script handles ONLY the two services (gateway :8088, mcp :9090). Their bind/host
# default to loopback (co-located on the app box) but read from secrets.env
# (TW2_APISERVER_BIND, TW2_MCP_HOST/PORT) - so the SAME units + this SAME script also stand
# the gateway up on its OWN dedicated box later. Runbook: ops/SPLIT_GATEWAY_TO_OWN_BOX.md.
# The public ingress is OUT OF SCOPE here and is reminded about at the end:
#   - nginx vhosts:  ops/nginx/tradewave-developer-portal.conf
#   - cloudflared:   add api-* / mcp-* / developers-* to /etc/cloudflared/config.yml
#
# Usage (on the target box):
#   sudo bash /home/flask/ops/bootstrap_api_services.sh

set -euo pipefail

hdr() { printf '\n=== %s ===\n' "$*"; }
say() { printf '  %s\n' "$*"; }

REPO=/home/flask
VENV=/home/flask/venv-api
REQ=/home/flask/requirements-api.txt
SECRETS=/etc/tradewave/secrets.env
SCHEMA=/home/flask/apiserver/schema.sql
LOGDIR=/var/log/tradewave
UNIT_SRC=/home/flask/ops/systemd
UNIT_DST=/etc/systemd/system

# --- preflight ---------------------------------------------------------------
hdr "0. preflight"
[ "$(id -u)" -eq 0 ]    || { echo "FAIL: run as root (writes /etc/systemd, runs systemctl)"; exit 1; }
[ -r "$SECRETS" ]       || { echo "FAIL: $SECRETS not readable"; exit 1; }
[ -r "$REQ" ]           || { echo "FAIL: $REQ not found"; exit 1; }
[ -r "$SCHEMA" ]        || { echo "FAIL: $SCHEMA not found"; exit 1; }
[ -r "$UNIT_SRC/tradewave-apiserver.service" ] || { echo "FAIL: $UNIT_SRC/tradewave-apiserver.service not found (pull the repo)"; exit 1; }
[ -r "$UNIT_SRC/tradewave-mcpserver.service" ] || { echo "FAIL: $UNIT_SRC/tradewave-mcpserver.service not found (pull the repo)"; exit 1; }
id -u flask >/dev/null 2>&1 || { echo "FAIL: 'flask' user does not exist"; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "FAIL: psql not on PATH (install postgresql-client)"; exit 1; }
say "preflight ok (root, secrets.env, requirements, schema, unit files, flask user, psql)"

# Load secrets for this step (POSTGRES_DSN below). Confined to this shell.
set -a; . "$SECRETS"; set +a
[ -n "${POSTGRES_DSN:-}" ] || { echo "FAIL: POSTGRES_DSN empty/unset in $SECRETS"; exit 1; }

# --- 1. venv-api + deps ------------------------------------------------------
hdr "1. python venv ($VENV) + API deps"
if [ -x "$VENV/bin/python" ]; then
    say "venv already exists - reusing $VENV"
else
    say "creating venv at $VENV"
    sudo -u flask python3 -m venv "$VENV"
fi
say "pip install -U pip  (as flask)"
sudo -u flask "$VENV/bin/pip" install -U pip
say "pip install -r $REQ  (as flask)"
sudo -u flask "$VENV/bin/pip" install -r "$REQ"

# --- 2. log dir --------------------------------------------------------------
hdr "2. log directory ($LOGDIR, owned by flask)"
if [ -d "$LOGDIR" ]; then
    say "$LOGDIR already exists"
else
    say "creating $LOGDIR"
fi
install -d -o flask -g flask "$LOGDIR"
say "ensured ownership flask:flask on $LOGDIR"

# --- 3. DB schema (idempotent, additive) -------------------------------------
hdr "3. apply API schema ($SCHEMA)"
say "checking the venv can import psycopg2"
"$VENV/bin/python" -c 'import psycopg2' \
    || { echo "FAIL: psycopg2 not importable in $VENV - step 1 install must have failed"; exit 1; }
# The schema is additive (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), so
# re-applying is a no-op. We still guard so a clean re-run says so instead of churning.
if psql "$POSTGRES_DSN" -tAc "SELECT to_regclass('public.api_keys')" 2>/dev/null | grep -q '^api_keys$'; then
    say "api_keys table already present - schema looks applied; re-applying anyway (idempotent)"
else
    say "api_keys table absent - applying schema for the first time"
fi
psql "$POSTGRES_DSN" -v ON_ERROR_STOP=1 -f "$SCHEMA"
say "schema applied"

# --- 4. systemd units + enable + health --------------------------------------
hdr "4. install systemd units, enable --now, health-check"
install -m 0644 "$UNIT_SRC/tradewave-apiserver.service" "$UNIT_DST/tradewave-apiserver.service"
install -m 0644 "$UNIT_SRC/tradewave-mcpserver.service" "$UNIT_DST/tradewave-mcpserver.service"
say "copied tradewave-apiserver.service + tradewave-mcpserver.service to $UNIT_DST"
systemctl daemon-reload
say "daemon-reload done"
systemctl enable --now tradewave-apiserver
systemctl enable --now tradewave-mcpserver
say "enabled + started both units"

# Give them a moment to bind their loopback ports before probing.
sleep 3
systemctl --no-pager status tradewave-apiserver tradewave-mcpserver | head -30 || true

hdr "4a. health checks"
say "gateway: curl http://127.0.0.1:8088/healthz"
curl -fsS http://127.0.0.1:8088/healthz && echo \
    || { echo "FAIL: gateway /healthz did not return 200 - 'journalctl -u tradewave-apiserver -n 50'"; exit 1; }
say "mcp: ss -ltnp | grep 9090 (expect the python process LISTENing on 127.0.0.1:9090)"
ss -ltnp | grep -q ':9090 ' \
    || { echo "FAIL: nothing listening on :9090 - 'journalctl -u tradewave-mcpserver -n 50'"; exit 1; }
ss -ltnp | grep ':9090 ' || true
say "both services healthy (gateway :8088 answering /healthz, mcp :9090 listening)"

# --- 5. reminder: ingress is a SEPARATE step ---------------------------------
hdr "5. REMINDER - public ingress is NOT done by this script"
cat <<'REMIND'
  The gateway (:8088) and MCP (:9090) bind LOOPBACK only. They are not reachable
  from the internet until nginx + the cloudflared tunnel front them. Still TODO,
  per env, BY YOU (the operator):

  1) nginx vhosts - install the developer-portal vhost and set its server_name
     for THIS env (dev=*-dev.trxstat.com, staging=*-stage.trxstat.com,
     prod=api/mcp/developers.tradewave.ai):
         /home/flask/ops/nginx/tradewave-developer-portal.conf
     Copy it into /etc/nginx/sites-available/, symlink into sites-enabled/, then:
         nginx -t && systemctl reload nginx

  2) cloudflared ingress - add the three hostnames for THIS env to
     /etc/cloudflared/config.yml ABOVE the final '- service: http_status:404'
     catch-all, each -> http://localhost:80 :
         api-<env>.trxstat.com   mcp-<env>.trxstat.com   developers-<env>.trxstat.com
         (prod: api.tradewave.ai  mcp.tradewave.ai  developers.tradewave.ai)
     then: systemctl reload cloudflared   (or restart, per your cloudflared unit)

  3) developer-portal docroot - generate /var/www/developers from the repo:
     see the portal generators under site/api_marketing, site/api_docs,
     site/api_learn, site/api_playground (run with /home/flask/venv/bin/python).
REMIND

echo
echo "=== API + MCP services bootstrap complete on $(hostname) ==="
echo "Loopback services are UP. Finish the ingress steps above to expose them."
