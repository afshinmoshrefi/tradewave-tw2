#!/usr/bin/env bash
# Phase-2 box-side re-point for the prod domain cutover (see ops/PROD_CUTOVER.md).
# Does ONLY the reversible box-side mechanics. Does NOT touch DNS, Cloudflare
# cache, WorkOS, or Stripe — those are the deliberate manual irreversible
# actions you do with the runbook open.
#
# Fill in the three vars, then run from a host with SSH to prod-web.
# Idempotent.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# ----------------------------- EDIT THESE -----------------------------
NEW_HOST="${NEW_HOST:-tradewave.ai}"
PROD_WEB="${PROD_WEB:-CHANGE_ME}"          # prod-web public IP
SSH_PORT="${SSH_PORT:-4369}"
# ----------------------------------------------------------------------

[[ "$PROD_WEB" == "CHANGE_ME" ]] && { echo "Set PROD_WEB (prod-web IP) at top of script or via env." >&2; exit 1; }

NEW_ROOT="https://${NEW_HOST}"
NEW_CB="https://${NEW_HOST}/auth/callback"

ssh -p "$SSH_PORT" "root@${PROD_WEB}" "NEW_HOST='${NEW_HOST}' NEW_ROOT='${NEW_ROOT}' NEW_CB='${NEW_CB}' bash -s" <<'REMOTE'
set -euo pipefail
hdr() { printf '\n--- %s ---\n' "$*"; }
S=/etc/tradewave/secrets.env

hdr "1. re-point secrets.env (TW2_DOMAIN_ROOT / TW2_PUBLIC_HOST / TW2_AUTH_CALLBACK_URL)"
cp -a "$S" "${S}.precutover.$(date -u +%Y%m%d%H%M)"
sed -i "s|^TW2_DOMAIN_ROOT=.*|TW2_DOMAIN_ROOT=${NEW_ROOT}|" "$S"
sed -i "s|^TW2_PUBLIC_HOST=.*|TW2_PUBLIC_HOST=${NEW_HOST}|" "$S"
if grep -q '^TW2_AUTH_CALLBACK_URL=' "$S"; then
  sed -i "s|^TW2_AUTH_CALLBACK_URL=.*|TW2_AUTH_CALLBACK_URL=${NEW_CB}|" "$S"
else
  echo "TW2_AUTH_CALLBACK_URL=${NEW_CB}" >> "$S"
fi
grep -E '^TW2_(DOMAIN_ROOT|PUBLIC_HOST|AUTH_CALLBACK_URL)=' "$S"

hdr "2. nginx server_name"
VHOST=$(grep -rl 'server_name ' /etc/nginx/sites-available/ | xargs grep -l 'tw2_web\|/var/www/tradewave' | head -1)
cp -a "$VHOST" "${VHOST}.precutover"
# Replace the marketing vhost server_name (the one with the web upstream),
# leave the 444 default_server block alone.
sed -i "s|server_name [a-z0-9.-]*;|server_name ${NEW_HOST};|" "$VHOST"
grep -n 'server_name' "$VHOST"
nginx -t

hdr "3. cloudflared ingress hostname"
CFG=/etc/cloudflared/config.yml
cp -a "$CFG" "${CFG}.precutover"
# Replace the primary web hostname line; keep smn-* and the 404 catch-all.
python3 - "$CFG" "$NEW_HOST" <<'PY'
import sys,re
p,newh=sys.argv[1],sys.argv[2]
s=open(p).read()
# first ingress hostname that is NOT an smn- host becomes the new web host
lines=s.splitlines()
done=False
for i,l in enumerate(lines):
    m=re.match(r'(\s*-\s*hostname:\s*)(\S+)',l)
    if m and not done and 'smn' not in m.group(2):
        lines[i]=m.group(1)+newh; done=True
open(p,'w').write("\n".join(lines)+"\n")
print("rewrote web ingress hostname ->", newh, "(changed)" if done else "(NO MATCH - check config.yml)")
PY
grep -n 'hostname:' "$CFG"

hdr "4. restart web + reload nginx + cloudflared"
systemctl restart tradewave-web
nginx -t && systemctl reload nginx
systemctl restart cloudflared
sleep 3
systemctl is-active tradewave-web nginx cloudflared

hdr "5. regenerate static content (canonical/og:url/sitemaps -> new host)"
set -a; . "$S"; set +a
sudo -u flask -E /home/flask/venv/bin/python /home/flask/site/generate_home_page.py        >> /var/log/tradewave/home_page.log 2>&1 || echo "home_page gen WARN"
sudo -u flask -E /home/flask/venv/bin/python /home/flask/site/generate_scorecard.py         >> /var/log/tradewave/scorecard.log 2>&1 || echo "scorecard gen WARN"
sudo -u flask -E /home/flask/venv/bin/python /home/flask/site/generate_insights.py          >> /var/log/tradewave/insights.log 2>&1 || echo "insights gen WARN"
( cd /home/flask/site/ticker_pages && sudo -u flask -E /home/flask/venv/bin/python generate_ticker_pages.py >> /var/log/tradewave/ticker_pages.log 2>&1 ) || echo "ticker gen WARN"
echo "content regenerated (warnings non-fatal; crons will also refresh)"

hdr "6. local smoke (Host header = new host)"
for path in / /healthz /api/me; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ${NEW_HOST}" "http://127.0.0.1${path}" || echo ERR)
  echo "  ${path} -> ${code}"
done
REMOTE

hdr "DONE — box side re-pointed"
cat <<EOF

Box side complete. The IRREVERSIBLE manual actions are NOT done by this
script — do them now, in order, with ops/PROD_CUTOVER.md open:

  [ ] Flip the tradewave.ai DNS record -> TW2 tunnel CNAME (Phase 2.2)
  [ ] Purge Cloudflare cache for the zone (Phase 2.3)
  [ ] Confirm WorkOS prod redirect URI https://${NEW_HOST}/auth/callback is active
  [ ] Confirm Stripe prod webhook endpoint is receiving

Then smoke https://${NEW_HOST} per Phase 2.6. Rollback = Phase 3
(restore saved DNS record + purge cache). TW1 stays up untouched.
EOF
