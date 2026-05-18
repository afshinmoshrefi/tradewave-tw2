#!/usr/bin/env bash
# Verify the TW2 Stripe webhook end-to-end with a REAL, correctly-signed
# event. Builds a benign invoice.payment_succeeded, HMAC-signs it with the
# box's actual STRIPE_WEBHOOK_SECRET (read from secrets.env, NEVER printed),
# and POSTs it to the live endpoint over the public tunnel — exactly the
# path Stripe uses. A valid signature must return 200. The fake customer
# matches no user, so the handler just records the stripe_events ledger
# row and returns; nothing is mutated, no email, no Stripe call-back.
#
# Run on the WEB box as root (needs to read /etc/tradewave/secrets.env):
#   /home/flask/ops/verify_stripe_webhook.sh                # -> tw2-prod.trxstat.com
#   /home/flask/ops/verify_stripe_webhook.sh tradewave.ai   # post-cutover
set -euo pipefail
HOST="${1:-tw2-prod.trxstat.com}"
SECRETS=/etc/tradewave/secrets.env
[ -r "$SECRETS" ] || { echo "FAIL: cannot read $SECRETS (run as root on the web box)"; exit 2; }
set -a; . "$SECRETS"; set +a
S="${STRIPE_WEBHOOK_SECRET:-}"
case "$S" in
  ""|*PLACEHOLDER*) echo "FAIL: STRIPE_WEBHOOK_SECRET unset or still PLACEHOLDER"; exit 2;;
esac
TS=$(date +%s)
BODY="{\"id\":\"evt_verify_${TS}\",\"object\":\"event\",\"type\":\"invoice.payment_succeeded\",\"data\":{\"object\":{\"id\":\"in_verify_${TS}\",\"object\":\"invoice\",\"customer\":\"cus_verify_nonexistent\",\"subscription\":\"sub_verify_nonexistent\"}}}"
SIG=$(printf '%s' "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$S" | sed 's/^.* //')
CODE=$(curl -sS -o /tmp/tw2_wh_verify.out -w '%{http_code}' -X POST \
  "https://${HOST}/webhooks/stripe" \
  -H "Stripe-Signature: t=${TS},v1=${SIG}" \
  -H 'Content-Type: application/json' \
  --data-binary "$BODY")
echo "POST https://${HOST}/webhooks/stripe  ->  HTTP ${CODE}"
echo "event id: evt_verify_${TS}  (find this row in the stripe_events ledger)"
if [ "$CODE" = "200" ]; then
  echo "PASS: valid signature accepted; handler processed and returned 200."
  exit 0
fi
echo "--- response body ---"; cat /tmp/tw2_wh_verify.out 2>/dev/null; echo
echo "FAIL: expected 200. 400 = secret in secrets.env != Stripe's signing secret; 5xx = handler error."
exit 1
