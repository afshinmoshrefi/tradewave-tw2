#!/usr/bin/env bash
# Production root operator only. No model or subscriber send is used for smoke.
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
[[ $# == 3 ]] || die 'usage: 02-cutover.sh SNAPSHOTS_JSON DEV_PROOF_JSON VERIFIED_TW2_SSO_JSON'
SNAPSHOTS=$(realpath "$1"); PROOF=$(realpath "$2"); SSO_PROOF=$(realpath "$3")
root_host
assert_release
assert_dirty_source
verify_evidence "$SNAPSHOTS" "$PROOF"
[[ -f $SSO_PROOF && ! -L $SSO_PROOF ]] || die 'verified TradeWave production SSO evidence missing'
"$PY" - "$SSO_PROOF" <<'PY'
import json,sys
data=json.load(open(sys.argv[1]))
if (data.get('status')!='production_verified' or
    data.get('dashboard_login_url')!='https://tradewave.ai/smn-dashboard/login' or
    not data.get('release_sha') or not data.get('verified_by') or
    data.get('source_route_verified') is not True):
    raise SystemExit('BLOCKED: separately verified TradeWave production SSO release required')
PY
assert_sso
[[ -x /opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex ]] || die 'qualified production Codex CLI missing'
[[ -x /root/.local/bin/claude ]] || die 'production Claude CLI missing'
[[ -f /root/.codex/auth.json ]] || die 'private root Codex subscription login missing'
[[ -d /opt/smn-playwright/node_modules/playwright ]] || die 'production Playwright missing'
[[ $(systemctl is-active blog_queue.service) == active ]] || die 'blog_queue service not active before cutover'
[[ $(systemctl is-active article_processor.service) == active ]] || die 'article_processor service not active before cutover'
[[ $(systemctl is-active smn-shadow.service || true) != active ]] || die 'shadow job still running'
[[ ! -e /etc/SMN/subscription-primary.json && ! -e /etc/SMN/dashboard-production.json ]] || die 'existing activation requires separate inspected upgrade'
[[ ! -e /var/lib/tradewave/smn-daily/subscription-primary/$TODAY/chatgpt/production-publication-receipt.json ]] || die 'current-day reader receipt exists; newsletter might send'
[[ ! -e /opt/smn-subscription/bin/git ]] || die 'release Git wrapper already exists'
for unit in pub_dashboard.service smn-subscription.service smn-weekday-newsletter.service; do
  [[ ! -e /etc/systemd/system/$unit.d/10-release-git.conf ]] || die "existing Git unit drop-in requires inspection: $unit"
done
PYTHONPATH="$RELEASE/blog" "$PY" - <<'PY'
from datetime import datetime,timezone
import operational_schedule,operational_settings
now=datetime.now(timezone.utc)
settings=operational_settings.for_instant(now)
if operational_schedule.due(now,'production',settings):
    raise SystemExit('BLOCKED: scheduler phase is due now; cut over outside the scheduled minute')
PY
OUT=$(dirname "$SNAPSHOTS")
[[ $(stat -c %u "$OUT") == 0 ]] || die 'handoff directory must be root-owned'
[[ ! -e $OUT/handoff-queue.active && ! -e $OUT/blog_queue.before.py ]] || die 'queue cutover state already exists'
[[ $(sha "$RELEASE/blog/blog_queue.py") == 715e1876d5e9d047b13abf0b732f604055373e5b5f8d3b1dd18a7939b6ccdcfe ]] || die 'qualified queue integration hash changed'
cp -a /home/flask/blog/blog_queue.py "$OUT/blog_queue.before.py"
[[ $(sha "$OUT/blog_queue.before.py") == 24027ce5ac00a198b99a6090982f6cc1bda2f9f089387c66976cc765ae2007f9 ]] || die 'queue backup mismatch'
printf '%s\n%s\n' "$SHA" "$TODAY" > "$OUT/handoff-queue.active"
chmod 0600 "$OUT/handoff-queue.active"
rollback_on_exit() {
  local code=$?
  trap - EXIT
  [[ $code != 0 ]] || code=1
  echo "Cutover failed (exit $code); attempting reverse-order rollback" >&2
  bash "$(dirname "$0")/03-rollback.sh" "$SNAPSHOTS" || echo 'Automatic rollback needs operator inspection; stop all further writes' >&2
  exit "$code"
}
trap rollback_on_exit EXIT
systemctl stop blog_queue.service
cp -a "$RELEASE/blog/blog_queue.py" /home/flask/blog/blog_queue.py.smn-new
mv /home/flask/blog/blog_queue.py.smn-new /home/flask/blog/blog_queue.py
systemctl start blog_queue.service
systemctl is-active --quiet blog_queue.service
curl --max-time 10 -fsS http://127.0.0.1:7171/ >/dev/null
install -d -m 0755 /opt/smn-subscription/bin
printf '#!/bin/sh\nexec /usr/bin/sudo -u flask /usr/bin/git "$@"\n' > /opt/smn-subscription/bin/git
chmod 0755 /opt/smn-subscription/bin/git
export PATH="/opt/smn-subscription/bin:$PATH"
"$PY" "$RELEASE/blog/install_smn_dashboard.py" activate --dev-proof "$PROOF" --snapshots "$SNAPSHOTS"
for unit in pub_dashboard.service smn-subscription.service smn-weekday-newsletter.service; do
  dropin="/etc/systemd/system/$unit.d/10-release-git.conf"
  install -d -m 0755 "$(dirname "$dropin")"
  printf '[Service]\nEnvironment=PATH=/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' > "$dropin"
done
systemctl daemon-reload
systemctl restart pub_dashboard.service
systemctl is-active --quiet pub_dashboard.service
"$PY" "$RELEASE/blog/install_smn_subscription.py" activate --dev-proof "$PROOF" --snapshots "$SNAPSHOTS" --codex /opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex --claude /root/.local/bin/claude
if PYTHONPATH="$RELEASE/blog" "$PY" -c 'from install_smn_operational_alerts import _secret_ready; raise SystemExit(0 if _secret_ready() else 1)'; then
  "$PY" "$RELEASE/blog/install_smn_operational_alerts.py" activate --repo "$RELEASE" --target production --dev-proof "$PROOF" --snapshots "$SNAPSHOTS"
  systemctl is-active --quiet smn-operational-alerts.timer
else
  echo 'Alert monitor pending: private RESEND_API_KEY is not provisioned; no alert delivery claim.' >&2
fi
systemctl is-active --quiet pub_dashboard.service
systemctl is-active --quiet smn-subscription.timer
systemctl is-active --quiet smn-weekday-newsletter.timer
[[ $(curl --max-time 10 -sS -o /dev/null -w '%{http_code}' https://seasonalmarketnews.com/smn-dashboard/api/articles) == 401 ]] || die 'public dashboard auth smoke failed'
trap - EXIT
echo "Active release $SHA. Preserve $OUT; inspect installer records for rollback. No generation or subscriber send was invoked."
