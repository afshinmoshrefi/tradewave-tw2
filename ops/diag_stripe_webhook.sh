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

sign_and_post () {  # $1=secret  $2=label
  local sec="$1" label="$2" t b sig code body
  [ -z "$sec" ] && { echo "[$label] skipped (empty secret)"; return; }
  t=$(date +%s)
  b='{"id":"evt_diag_'"$t"'","type":"invoice.payment_succeeded","data":{"object":{}}}'
  sig=$(printf '%s' "$t.$b" | openssl dgst -sha256 -hmac "$sec" | awk '{print $NF}')
  body=$(curl -s -m 15 -w $'\n%{http_code}' -X POST "https://$HOST/webhooks/stripe" \
        -H "Stripe-Signature: t=$t,v1=$sig" -H 'Content-Type: application/json' \
        --data-binary "$b")
  code=$(printf '%s' "$body" | tail -1)
  echo "[$label] HTTP $code  body=$(printf '%s' "$body" | head -1)"
}

hr "test A: sign with the secret the RUNNING APP uses (decisive)"
sign_and_post "$PSEC" "proc-secret"
hr "test B: sign with the secret in secrets.env"
sign_and_post "$FSEC" "file-secret"

hr "VERDICT"
if [ "$SAME" = yes ]; then
  echo "Secret is consistent (file == running process)."
  echo "If test A/B = 200 -> webhook is GOOD."
  echo "If test A/B = 400 -> secret is right but SIGNING FORMAT is wrong (code-side); send me this output."
else
  echo "MISMATCH: the running service is NOT using the secrets.env value."
  echo "If test A (proc-secret) = 200 but test B (file-secret) = 400:"
  echo "  -> signing math is fine; the live service is running a STALE/OTHER secret."
  echo "  -> Real Stripe events (signed with the dashboard whsec you put in secrets.env)"
  echo "     will FAIL until the service is restarted so it loads /etc/tradewave/secrets.env."
  echo "  Likely cause: the $UNIT systemd unit doesn't load that file, OR it wasn't"
  echo "  truly restarted. Next: check 'systemctl cat $UNIT' for EnvironmentFile=."
fi
