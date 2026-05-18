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
  b='{"id":"evt_diag_'"$t"'","object":"event","api_version":"2026-04-22.dahlia","type":"invoice.payment_succeeded","data":{"object":{"id":"in_diag_'"$t"'","object":"invoice","customer":"cus_diag_none","subscription":"sub_diag_none"}}}'
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

hr "test C: in-process construct_event (prod venv + its config + its stripe lib, NO http)"
VPY=/home/flask/venv/bin/python
[ -x "$VPY" ] || VPY=$(command -v python3)
TMPC=$(mktemp /tmp/whprobe.XXXX.py)
cat > "$TMPC" <<'PY'
import sys, time, hmac, hashlib
sys.path[:0] = ['/home/flask/web', '/home/flask']
try:
    import config
    print("config.__file__ =", getattr(config, "__file__", "?"))
except Exception as e:
    print("IMPORT config FAILED:", type(e).__name__, "-", e); raise SystemExit(0)
try:
    import stripe
    print("stripe version =", getattr(stripe, "VERSION", getattr(stripe, "_version", "?")))
except Exception as e:
    print("IMPORT stripe FAILED:", type(e).__name__, "-", e); raise SystemExit(0)
sec = getattr(config, "STRIPE_WEBHOOK_SECRET", "") or ""
print("config secret sha256 =", hashlib.sha256(sec.encode()).hexdigest(), "len =", len(sec))
# Mirror the running app: it sets stripe.api_key at startup; Event.construct_from
# needs it. Without it, construct_event can AttributeError after a VALID signature.
try:
    stripe.api_key = getattr(config, "STRIPE_SECRET_KEY", "") or getattr(config, "STRIPE_API_KEY", "") or stripe.api_key
    print("stripe.api_key set =", bool(stripe.api_key))
except Exception as _e:
    print("api_key set skipped:", _e)
body = '{"id":"evt_probe","object":"event","api_version":"2026-04-22.dahlia","type":"invoice.payment_succeeded","data":{"object":{"id":"in_probe","object":"invoice","customer":"cus_probe_none","subscription":"sub_probe_none"}}}'
t = int(time.time())
mac = hmac.new(sec.encode("utf-8"), ("%d.%s" % (t, body)).encode("utf-8"), hashlib.sha256).hexdigest()
hdr = "t=%d,v1=%s" % (t, mac)
try:
    ev = stripe.Webhook.construct_event(body, hdr, sec)
    et = ev.get("type") if isinstance(ev, dict) else getattr(ev, "type", None)
    print("CONSTRUCT_EVENT: PASS  type=", et)
except Exception as e:
    print("CONSTRUCT_EVENT: FAIL ", type(e).__name__, "-", e)
PY
"$VPY" "$TMPC" 2>&1
rm -f "$TMPC"

hr "VERDICT (read against the A1/A2/A3 codes above)"
echo "test C is the bisector:"
echo "  C config secret sha256 must equal 7b66...cfcb (the proc/file hash). If it"
echo "    DIFFERS -> config.py transforms the secret; that's the bug."
echo "  C CONSTRUCT_EVENT PASS but A1 http=400 -> secret+lib+scheme are fine; the"
echo "    bytes reaching the handler != what was sent (request.data not raw / proxy)."
echo "  C CONSTRUCT_EVENT FAIL -> the printed exception IS the answer (stripe-lib"
echo "    version scheme, header parse, or secret). Send me this whole output."
echo "Secret is consistent (file == running process), same box => not secret, not clock."
echo "  A1 gunicorn-direct = 200  -> signing+secret+app are CORRECT. The breakage is an"
echo "     edge layer: if A2 also 400 it's nginx; if only A3 400 it's Cloudflare/tunnel"
echo "     mangling the body or the Stripe-Signature header."
echo "  A1 gunicorn-direct = 400  -> the app rejects a byte-perfect, correctly-signed"
echo "     request with its own secret => something consumes/changes request.data before"
echo "     the handler (a body-reading WSGI/before_request middleware), or stripe-lib"
echo "     version scheme. That's a code-side fix; send me this whole output."
