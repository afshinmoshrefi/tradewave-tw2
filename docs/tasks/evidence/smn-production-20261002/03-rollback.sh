#!/usr/bin/env bash
# Reverse only this handoff. Stops email before legacy cron restoration.
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
[[ $# == 1 ]] || die 'usage: 03-rollback.sh SNAPSHOTS_JSON'
root_host
SNAPSHOTS=$(realpath "$1"); OUT=$(dirname "$SNAPSHOTS")
[[ -f $OUT/handoff-queue.active && $(head -1 "$OUT/handoff-queue.active") == "$SHA" ]] || die 'this handoff has no active queue record'
ACTDATE=$(sed -n '2p' "$OUT/handoff-queue.active")
[[ $ACTDATE =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die 'handoff activation date invalid'
[[ -f $OUT/blog_queue.before.py && $(sha "$OUT/blog_queue.before.py") == 24027ce5ac00a198b99a6090982f6cc1bda2f9f089387c66976cc765ae2007f9 ]] || die 'queue rollback backup missing or changed'
[[ $(systemctl is-active smn-subscription.service || true) != active ]] || die 'reader controller still running; let it finish before rollback'
record_status() { "$PY" - "$1" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);print(json.loads(p.read_text()).get('status','') if p.is_file() else '')
PY
}
ALERT=/var/lib/tradewave/release-state/smn-operational-alerts-activation.json
SCHED=/var/lib/tradewave/release-state/smn-subscription-${SHA:0:12}-$ACTDATE/receipt.json
DASH=/var/lib/tradewave/release-state/smn-dashboard-${SHA:0:12}-$ACTDATE/receipt.json
if [[ $(record_status "$ALERT") == active ]]; then
  "$PY" "$RELEASE/blog/install_smn_operational_alerts.py" rollback --receipt "$ALERT"
fi
if [[ $(record_status "$SCHED") == active ]]; then
  "$PY" "$RELEASE/blog/install_smn_subscription.py" rollback "$(dirname "$SCHED")"
fi
if [[ $(record_status "$DASH") == active ]]; then
  "$PY" "$RELEASE/blog/install_smn_dashboard.py" rollback "$(dirname "$DASH")"
fi
CURRENT=$(sha /home/flask/blog/blog_queue.py)
queue_dropin=/etc/systemd/system/blog_queue.service.d/20-dashboard-loopback.conf
if [[ -e $queue_dropin ]]; then
  expected=$(queue_loopback_config | sha256sum | cut -d' ' -f1)
  [[ $(sha "$queue_dropin") == "$expected" ]] || die 'queue loopback binding changed; preserve it'
  rm "$queue_dropin"
  rmdir "$(dirname "$queue_dropin")" 2>/dev/null || true
  systemctl daemon-reload
fi
if [[ $CURRENT == 9245384c43ef256a4d51934bac7acb0720b64c05bbe42ac4c911d248aeda37ff ]]; then
  systemctl stop blog_queue.service
  cp -a "$OUT/blog_queue.before.py" /home/flask/blog/blog_queue.py.smn-restore
  mv /home/flask/blog/blog_queue.py.smn-restore /home/flask/blog/blog_queue.py
  systemctl start blog_queue.service
elif [[ $CURRENT != 24027ce5ac00a198b99a6090982f6cc1bda2f9f089387c66976cc765ae2007f9 ]]; then
  die 'queue file changed after cutover; preserve peer edit'
fi
systemctl is-active --quiet blog_queue.service
[[ $(sha /home/flask/blog/blog_queue.py) == 24027ce5ac00a198b99a6090982f6cc1bda2f9f089387c66976cc765ae2007f9 ]] || die 'queue rollback verification failed'
for unit in pub_dashboard.service smn-subscription.service smn-weekday-newsletter.service; do
  dropin="/etc/systemd/system/$unit.d/10-release-git.conf"
  if [[ -e $dropin ]]; then
    expected=$(printf '[Service]\nEnvironment=PATH=/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' | sha256sum | cut -d' ' -f1)
    [[ $(sha "$dropin") == "$expected" ]] || die "Git unit drop-in changed; preserve it: $unit"
    rm "$dropin"
    rmdir "$(dirname "$dropin")" 2>/dev/null || true
  fi
done
start_guard=/etc/systemd/system/smn-subscription.service.d/20-cutover-start.conf
if [[ -e $start_guard ]]; then
  [[ -f $OUT/cutover-start.sha256 && $(sha "$start_guard") == $(cat "$OUT/cutover-start.sha256") ]] || die 'cutover start guard changed; preserve it'
  rm "$start_guard"
  rmdir "$(dirname "$start_guard")" 2>/dev/null || true
fi
systemctl daemon-reload
if [[ -e /opt/smn-subscription/bin/git ]]; then
  expected=$(printf '#!/bin/sh\nexec /usr/bin/sudo -u flask /usr/bin/git "$@"\n' | sha256sum | cut -d' ' -f1)
  [[ $(sha /opt/smn-subscription/bin/git) == "$expected" ]] || die 'release Git wrapper changed; preserve it'
  rm /opt/smn-subscription/bin/git
  rmdir /opt/smn-subscription/bin 2>/dev/null || true
fi
mv "$OUT/handoff-queue.active" "$OUT/handoff-queue.rolled-back"
echo 'Rolled back this handoff; snapshots and dashboard state remain preserved.'
