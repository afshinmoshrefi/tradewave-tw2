#!/usr/bin/env bash
# Close public 80/443 on both boxes — cloudflared tunnels carry traffic
# OUTBOUND from each box, so no inbound 80/443 is needed for the public
# hostnames. Leaving them open lets bare-IP scanners reach the boxes
# directly, bypassing Cloudflare's WAF/bot-detection.
#
# Uses `ufw delete allow <spec>` (deterministic; removes the v4 AND v6
# "Anywhere" rule regardless of numbering/comments) — the old numbered-
# rule loop silently no-op'd against real ufw output.
#
# HAZARD handled: after migrate_app_port_to_80, the WEB box reaches the
# APP box's gunicorn over the VLAN on :80. That path was only permitted
# by the public `80/tcp Anywhere` rule, so we add an explicit
# `allow from <web-vlan> to any port 80` on the app box BEFORE dropping
# public 80, or cross-tier /appserver breaks.
#
# For prod: run via  ops/staging/run.sh prod lockdown_public_ports.sh
set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APP="$TGT_APP_PUB"
WEB="$TGT_WEB_PUB"
WEB_VLAN="$TGT_WEB_VLAN"
SSH_PORT="$TGT_SSH_PORT"

hdr "app box: preserve VLAN web->app:80, drop public 80/443"
ssh -p "$SSH_PORT" "root@${APP}" "
  ufw allow from ${WEB_VLAN} to any port 80 proto tcp comment 'web->app gunicorn :80 (post port-80 migration)' >/dev/null
  ufw delete allow 80/tcp  >/dev/null 2>&1 || true
  ufw delete allow 443/tcp >/dev/null 2>&1 || true
  ufw reload >/dev/null
  echo 'app ufw:'; ufw status | grep -E '80|443|4369|5432|6379' | grep -v '^\$' || true
"

hdr "web box: drop public 80/443 (cloudflared is outbound; nginx is localhost)"
ssh -p "$SSH_PORT" "root@${WEB}" "
  ufw delete allow 80/tcp  >/dev/null 2>&1 || true
  ufw delete allow 443/tcp >/dev/null 2>&1 || true
  ufw reload >/dev/null
  echo 'web ufw:'; ufw status | grep -E '80|443|4369|5500|6379' | grep -v '^\$' || true
"

hdr "verify ingress still works via tunnels"
sleep 2
curl -sS -o /dev/null -w 'app-tunnel /healthz: %{http_code}\n' "https://${TGT_APP_HOST}/healthz" || true
curl -sS -o /dev/null -w 'web-tunnel /: %{http_code}\n'        "https://${TGT_WEB_HOST}/" || true
curl -sS -o /dev/null -w 'cross-tier /appserver/: %{http_code}\n' "https://${TGT_WEB_HOST}/appserver/" || true
echo "(all should be 200/30x; bare-IP :443 now refused)"
