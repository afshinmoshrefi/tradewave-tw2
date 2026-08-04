#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ABORT: activate_tara_release.sh must run as root" >&2
  exit 1
fi
if [[ $# -ne 2 ]]; then
  echo "usage: $0 RELEASE_DIR EXPECTED_BACKEND_FINGERPRINT" >&2
  exit 1
fi

wait_service_active() {
  local unit=$1
  for _ in {1..45}; do
    if systemctl is-active --quiet "$unit"; then
      return 0
    fi
    sleep 1
  done
  systemctl status "$unit" --no-pager -l >&2 || true
  return 1
}

release_dir=$(readlink -f "$1")
expected_fingerprint=$2
case "$release_dir" in
  /home/flask/.tw2-releases/*) ;;
  *) echo "ABORT: release directory is outside /home/flask/.tw2-releases" >&2; exit 1 ;;
esac
[[ -d "$release_dir/.git" || -f "$release_dir/.git" ]] || {
  echo "ABORT: release directory is not a Git worktree" >&2
  exit 1
}

release_sha=$(sudo -u flask git -C "$release_dir" rev-parse HEAD)
[[ -z $(sudo -u flask git -C "$release_dir" status --porcelain) ]] || {
  echo "ABORT: release worktree is dirty" >&2
  exit 1
}

set -a
# shellcheck source=/dev/null
. /etc/tradewave/secrets.env
# shellcheck source=/dev/null
. /etc/tradewave/appserver.env
set +a
tw2_env=${TW2_ENV:-unknown}
if [[ "$tw2_env" != dev ]]; then
  target_status=$(
    sudo -u flask git -C /home/flask status --porcelain --untracked-files=all -- \
      . ':(exclude).tw2-releases' ':(exclude).tw2-app-current'
  )
  [[ -z "$target_status" ]] || {
    echo "ABORT: /home/flask target worktree is dirty" >&2
    exit 1
  }
fi
PYTHONPATH="$release_dir:$release_dir/appserver/appserver" \
  /home/flask/venv/bin/python "$release_dir/ops/verify_tara_release.py" \
  --check-credentials >/dev/null

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot_dir="/root/tradewave-snapshots/tara-parity-${tw2_env}-${timestamp}"
install -d -m 0700 "$snapshot_dir" "$snapshot_dir/prior-source"
printf '%s\n' "$release_sha" >"$snapshot_dir/release-sha"
printf '%s\n' "$release_dir" >"$snapshot_dir/release-dir"
printf '%s\n' "$(sudo -u flask git -C /home/flask rev-parse HEAD)" >"$snapshot_dir/prior-git-sha"
if [[ -L /home/flask/.tw2-app-current ]]; then
  readlink -f /home/flask/.tw2-app-current >"$snapshot_dir/prior-app-target"
else
  printf '%s\n' /home/flask >"$snapshot_dir/prior-app-target"
fi

cp -a /etc/tradewave/appserver.env "$snapshot_dir/appserver.env.before"
stat -c '%n %U:%G %a %s' /etc/tradewave/appserver.env /etc/tradewave/secrets.env \
  >"$snapshot_dir/runtime-files.stat"
sha256sum /etc/tradewave/appserver.env /etc/tradewave/secrets.env \
  >"$snapshot_dir/runtime-files.sha256"

for unit in tradewave-appserver tradewave-apiserver; do
  dropin="/etc/systemd/system/${unit}.service.d/20-release-pointer.conf"
  if [[ -f "$dropin" ]]; then
    cp -a "$dropin" "$snapshot_dir/${unit}.dropin.before"
  else
    : >"$snapshot_dir/${unit}.dropin.before.missing"
  fi
  systemctl cat "$unit" >"$snapshot_dir/${unit}.unit.before"
done

for relative in \
  config.py \
  appserver/appserver/chatbot.py \
  appserver/appserver/chatbot_knowledge.txt \
  appserver/appserver/openai_tools_appserver.py \
  appserver/appserver/tara_answer_planner.py \
  appserver/appserver/tara_gateway.py \
  appserver/appserver/tara_model_router.py \
  appserver/appserver/tara_prompt_context.py; do
  prior="$(cat "$snapshot_dir/prior-app-target")/$relative"
  if [[ -f "$prior" ]]; then
    install -D -m 0600 "$prior" "$snapshot_dir/prior-source/$relative"
  fi
done
find "$snapshot_dir/prior-source" -type f -print0 | sort -z | xargs -0 -r sha256sum \
  >"$snapshot_dir/prior-source.sha256"

install -d -m 0755 /etc/systemd/system/tradewave-appserver.service.d
install -d -m 0755 /etc/systemd/system/tradewave-apiserver.service.d
printf '%s\n' \
  '[Service]' \
  'WorkingDirectory=/home/flask/.tw2-app-current/appserver/appserver' \
  'Environment=PYTHONPATH=/home/flask/.tw2-app-current:/home/flask/.tw2-app-current/appserver/appserver' \
  >"$snapshot_dir/tradewave-appserver.dropin.after"
printf '%s\n' \
  '[Service]' \
  'WorkingDirectory=/home/flask/.tw2-app-current' \
  'Environment=PYTHONPATH=/home/flask/.tw2-app-current' \
  >"$snapshot_dir/tradewave-apiserver.dropin.after"
install -o root -g root -m 0644 "$snapshot_dir/tradewave-appserver.dropin.after" \
  /etc/systemd/system/tradewave-appserver.service.d/20-release-pointer.conf
install -o root -g root -m 0644 "$snapshot_dir/tradewave-apiserver.dropin.after" \
  /etc/systemd/system/tradewave-apiserver.service.d/20-release-pointer.conf

awk '!/^[[:space:]]*TARA_OPENAI_CANARY_PERCENT[[:space:]]*=/' \
  /etc/tradewave/appserver.env >"$snapshot_dir/appserver.env.after"
install -o root -g root -m 0600 "$snapshot_dir/appserver.env.after" \
  /etc/tradewave/appserver.env

ln -sfn "$release_dir" /home/flask/.tw2-app-current
chown -h flask:flask /home/flask/.tw2-app-current

cat >"$snapshot_dir/rollback.sh" <<ROLLBACK
#!/usr/bin/env bash
set -euo pipefail
ln -sfn "$(cat "$snapshot_dir/prior-app-target")" /home/flask/.tw2-app-current
chown -h flask:flask /home/flask/.tw2-app-current
cp -a "$snapshot_dir/appserver.env.before" /etc/tradewave/appserver.env
if [[ -f "$snapshot_dir/tradewave-appserver.dropin.before.missing" ]]; then
  rm -f /etc/systemd/system/tradewave-appserver.service.d/20-release-pointer.conf
else
  cp -a "$snapshot_dir/tradewave-appserver.dropin.before" /etc/systemd/system/tradewave-appserver.service.d/20-release-pointer.conf
fi
if [[ -f "$snapshot_dir/tradewave-apiserver.dropin.before.missing" ]]; then
  rm -f /etc/systemd/system/tradewave-apiserver.service.d/20-release-pointer.conf
else
  cp -a "$snapshot_dir/tradewave-apiserver.dropin.before" /etc/systemd/system/tradewave-apiserver.service.d/20-release-pointer.conf
fi
systemctl daemon-reload
systemctl restart tradewave-appserver
for unit in tradewave-appserver tradewave-apiserver; do
  for _ in {1..45}; do
    systemctl is-active --quiet "\$unit" && break
    sleep 1
  done
  systemctl is-active --quiet "\$unit"
done
echo "restored Tara runtime: $(cat "$snapshot_dir/prior-app-target")"
ROLLBACK
chmod 0700 "$snapshot_dir/rollback.sh"

cat >"$snapshot_dir/rollforward.sh" <<ROLLFORWARD
#!/usr/bin/env bash
set -euo pipefail
ln -sfn "$release_dir" /home/flask/.tw2-app-current
chown -h flask:flask /home/flask/.tw2-app-current
cp -a "$snapshot_dir/appserver.env.after" /etc/tradewave/appserver.env
cp -a "$snapshot_dir/tradewave-appserver.dropin.after" /etc/systemd/system/tradewave-appserver.service.d/20-release-pointer.conf
cp -a "$snapshot_dir/tradewave-apiserver.dropin.after" /etc/systemd/system/tradewave-apiserver.service.d/20-release-pointer.conf
systemctl daemon-reload
systemctl restart tradewave-appserver
for unit in tradewave-appserver tradewave-apiserver; do
  for _ in {1..45}; do
    systemctl is-active --quiet "\$unit" && break
    sleep 1
  done
  systemctl is-active --quiet "\$unit"
done
echo "activated Tara runtime: $release_dir"
ROLLFORWARD
chmod 0700 "$snapshot_dir/rollforward.sh"

activated=1
on_error() {
  status=$?
  trap - ERR
  if [[ ${activated:-0} -eq 1 ]]; then
    echo "Activation failed; restoring the snapshot" >&2
    "$snapshot_dir/rollback.sh" >&2 || true
  fi
  exit "$status"
}
trap on_error ERR

systemctl daemon-reload
systemctl restart tradewave-appserver
wait_service_active tradewave-appserver
wait_service_active tradewave-apiserver

unset TARA_OPENAI_CANARY_PERCENT
set -a
# shellcheck source=/dev/null
. /etc/tradewave/secrets.env
# shellcheck source=/dev/null
. /etc/tradewave/appserver.env
set +a
PYTHONPATH="$release_dir:$release_dir/appserver/appserver" \
  /home/flask/venv/bin/python "$release_dir/ops/verify_tara_release.py" \
  --check-credentials --require-no-legacy-canary \
  --expected-fingerprint "$expected_fingerprint" >/dev/null

app_bind=$(
  systemctl show tradewave-appserver --property=Environment --value \
    | tr ' ' '\n' \
    | sed -n 's/^TW2_APPSERVER_BIND=//p' \
    | tail -1
)
export TW2_APPSERVER_BIND="$app_bind"
app_port=${app_bind##*:}
case "$app_port" in
  ''|*[!0-9]*) echo "ABORT: invalid active TW2_APPSERVER_BIND" >&2; false ;;
esac
health_json=$(curl -fsS "http://127.0.0.1:${app_port}/chatbot/runtime-fingerprint")
HEALTH_JSON="$health_json" EXPECTED_FINGERPRINT="$expected_fingerprint" \
  /home/flask/venv/bin/python -c \
  'import json, os; actual=json.loads(os.environ["HEALTH_JSON"]); assert actual["fingerprint"] == os.environ["EXPECTED_FINGERPRINT"]'

model_log=/var/log/tradewave/appserver.log
before_lines=$(wc -l <"$model_log" 2>/dev/null || printf 0)
PYTHONPATH="$release_dir:$release_dir/appserver/appserver" \
  /home/flask/venv/bin/python "$release_dir/ops/smoke_tara_deterministic.py"
PYTHONPATH="$release_dir:$release_dir/appserver/appserver" \
  /home/flask/venv/bin/python "$release_dir/ops/smoke_tara_model_bound.py"
new_log="$snapshot_dir/appserver-smoke.log"
tail -n "+$((before_lines + 1))" "$model_log" >"$new_log"
grep -Fq 'Tara model turn phase=complete provider=openai model=gpt-5.6-luna status=success' "$new_log"
if grep -Fq 'Tara model fallback' "$new_log"; then
  echo "ABORT: fallback occurred during the live Luna gate" >&2
  false
fi

PYTHONPATH="$release_dir:$release_dir/appserver/appserver" \
  /home/flask/venv/bin/python "$release_dir/ops/verify_tara_release.py" \
  >"$snapshot_dir/backend-fingerprint.json"
stat -c '%n %U:%G %a %s' \
  /etc/systemd/system/tradewave-appserver.service.d/20-release-pointer.conf \
  /etc/systemd/system/tradewave-apiserver.service.d/20-release-pointer.conf \
  >"$snapshot_dir/activated-files.stat"

trap - ERR
echo "Tara release activated"
echo "environment=$tw2_env"
echo "release_sha=$release_sha"
echo "snapshot=$snapshot_dir"
echo "rollback=$snapshot_dir/rollback.sh"
echo "rollforward=$snapshot_dir/rollforward.sh"
