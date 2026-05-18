#!/usr/bin/env bash
# DECISIVE Stripe-webhook diagnostic. Run on the WEB box as root:
#   sudo bash /home/flask/ops/diag_stripe_webhook.sh
#
# It answers exactly one question: is the 400 because the running service
# uses a different secret than /etc/tradewave/secrets.env, or because the
# signature computation is wrong? Secrets are NEVER printed — only sha256
# hashes (classification-only) and the standard error body.
set -uo pipefail
hr(){ printf -- '---- %s\n' "$*"; }

UNIT=tradewave-web
HOST="${1:-tw2-prod.trxstat.com}"

P=$(systemctl show -p MainPID --value "$UNIT" 2>/dev/null || echo 0)
hr "service"
echo "unit=$UNIT MainPID=$P state=$(systemctl is-active "$UNIT" 2>/dev/null)"

# Secret the RUNNING process actually has (what config.py / stripe verify with)
PSEC=""
if [ "$P" != "0" ] && [ -r "/proc/$P/environ" ]; then
  PSEC=$(tr '\0' '\n' < "/proc/$P/environ" | sed -n 's/^STRIPE_WEBHOOK_SECRET=//p')
fi
# Secret in the file you edited
FSEC=""
if [ -r /etc/tradewave/secrets.env ]; then
  set -a; . /etc/tradewave/secrets.env; set +a
  FSEC="${STRIPE_WEBHOOK_SECRET:-}"
fi

ph=$(printf %s "$PSEC" | sha256sum | awk '{print $1}')
fh=$(printf %s "$FSEC" | sha256sum | awk '{print $1}')
hr "secret identity (hashes only)"
echo "proc_env_sha256=$ph  (len=${#PSEC})"
echo "file_env_sha256=$fh  (len=${#FSEC})"
if [ -z "$PSEC" ]; then echo "NOTE: running process has NO STRIPE_WEBHOOK_SECRET in its env"; fi
if [ "$ph" = "$fh" ] && [ -n "$PSEC" ]; then SAME=yes; else SAME=no; fi
echo "same_secret=$SAME"

sign_and_post () {  # $1=secret  $2=url  $3=label
  local sec="$1" url="$2" label="$3" t b sig code body
  [ -z "$sec" ] && { echo "[$label] skipped (empty secret)"; return; }
  t=$(date +%s)
  b='{"id":"evt_diag_'"$t"'","type":"invoice.payment_succeeded","data":{"object":{}}}'
  sig=$(printf '%s' "$t.$b" | openssl dgst -sha256 -hmac "$sec" | awk '{print $NF}')
  body=$(curl -s -k -m 15 -w $'\n%{http_code}' -X POST "$url" \
        -H "Host: $HOST" -H "Stripe-Signature: t=$t,v1=$sig" \
        -H 'Content-Type: application/json' --data-binary "$b")
  code=$(printf '%s' "$body" | tail -1)
  echo "[$label] HTTP $code  body=$(printf '%s' "$body" | head -1)"
}

hr "layer isolation - all signed with the secret the RUNNING APP uses"
GUNI_PORT=$(ss -ltnp 2>/dev/null | grep -oE '127.0.0.1:(5500|8000|5000)' | head -1 | cut -d: -f2)
GUNI_PORT="${GUNI_PORT:-5500}"
echo "(detected gunicorn loopback port: $GUNI_PORT)"
sign_and_post "$PSEC" "http://127.0.0.1:${GUNI_PORT}/webhooks/stripe" "A1 gunicorn-direct (no nginx/no CF)"
sign_and_post "$PSEC" "http://127.0.0.1:80/webhooks/stripe"            "A2 local-nginx (no CF)"
sign_and_post "$PSEC" "https://$HOST/webhooks/stripe"                  "A3 via Cloudflare tunnel"
hr "control - secrets.env value over the tunnel"
sign_and_post "$FSEC" "https://$HOST/webhooks/stripe"                  "B  file-secret via tunnel"

hr "VERDICT (read against the A1/A2/A3 codes above)"
echo "Secret is consistent (file == running process), same box => not secret, not clock."
echo "  A1 gunicorn-direct = 200  -> signing+secret+app are CORRECT. The breakage is an"
echo "     edge layer: if A2 also 400 it's nginx; if only A3 400 it's Cloudflare/tunnel"
echo "     mangling the body or the Stripe-Signature header."
echo "  A1 gunicorn-direct = 400  -> the app rejects a byte-perfect, correctly-signed"
echo "     request with its own secret => something consumes/changes request.data before"
echo "     the handler (a body-reading WSGI/before_request middleware), or stripe-lib"
echo "     version scheme. That's a code-side fix; send me this whole output."
