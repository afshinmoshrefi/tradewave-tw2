#!/usr/bin/env bash
set -Eeuo pipefail
SHA=d6e2b6fd59b15e2a601248df00073c078db24df4
RELEASE=/opt/smn-subscription/releases/$SHA
PY=/home/flask/venv/bin/python
TODAY=$(date -u +%F)

die() { echo "BLOCKED: $*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
root_host() {
  [[ $(id -u) == 0 ]] || die 'run as root on SMN production'
  [[ " $(hostname -I) " == *' 209.182.216.112 '* ]] || die 'wrong host'
}
assert_dirty_source() {
  local p expected
  while read -r p expected; do
    [[ -f /home/flask/blog/$p ]] || die "missing production source: $p"
    [[ $(sha /home/flask/blog/$p) == "$expected" ]] || die "production source drift: $p"
  done <<'HASHES'
article_hero_image.py 9d81a388d55b134246e805badef0353e1df76165e9d37bf0e4dd7c7f62676b61
thumbnail_tools.py 6155004a63163e1d542e4dc36cc67a2be1687a5ab4f424e11012505e2bb51a89
article_prompt.py a5cdb2ec53e001d8d530730815de8ea03b5c0a36d8fb43acb1e0476cd4a4c348
article_workflow.py 817e63fcd7425ea9a9bad2aafc725f2ed95782b5278d55b5e7b5aad2b2f56a2e
blog_queue.py 24027ce5ac00a198b99a6090982f6cc1bda2f9f089387c66976cc765ae2007f9
article_sources.py 7a84fa0f5a47d92e10326634e2ffb2e964b483db1914dd038f6b2af2fc55828f
HASHES
  [[ $(sudo -u flask git -c safe.directory=/home/flask -C /home/flask rev-parse HEAD) == 2ea0e4e2897c39bbef01e908cd193b72545712e7 ]] || die 'production Git HEAD drift'
}
assert_release() {
  [[ -e $RELEASE/.git && -f $RELEASE/blog/install_smn_dashboard.py ]] || die 'exact release checkout missing'
  [[ $(sudo -u flask git -C "$RELEASE" rev-parse HEAD) == "$SHA" ]] || die 'release SHA changed'
  [[ -z $(sudo -u flask git -C "$RELEASE" status --porcelain) ]] || die 'release checkout dirty'
}
assert_sso() {
  local code
  code=$(curl --max-time 10 -sS -o /dev/null -w '%{http_code}' https://tradewave.ai/smn-dashboard/login) || die 'TradeWave production SSO route unreachable'
  [[ $code == 200 || $code == 302 || $code == 303 ]] || die "TradeWave production SSO route not released (HTTP $code)"
  [[ -f /etc/SMN/dashboard.env ]] || die 'private dashboard.env missing'
  [[ -f /etc/SMN/secrets.env ]] || die 'private dashboard secrets.env missing'
  [[ -f /etc/tradewave/secrets.env ]] || die 'private TradeWave secrets.env missing'
  PYTHONPATH="$RELEASE/blog" "$PY" - <<'PY'
from pathlib import Path
from install_smn_dashboard import auth_config, private_path
env=Path('/etc/SMN/dashboard.env')
private_path(env,0o027)
key=auth_config(env.read_text())
private_path(key,0o022)
PY
}
verify_evidence() {
  local snapshots=$1 proof=$2
  [[ -f $snapshots && -f $proof ]] || die 'snapshot metadata and Dev proof required'
  "$PY" - "$snapshots" "$proof" "$SHA" "$TODAY" <<'PY'
import json,sys
from pathlib import Path
snap=Path(sys.argv[1]).resolve();proof=Path(sys.argv[2]).resolve();commit,today=sys.argv[3:]
def fail(reason): raise SystemExit('BLOCKED: '+reason)
if any(p.is_symlink() or not p.is_file() for p in (snap,proof)): fail('evidence must be regular files')
data=json.loads(snap.read_text());dev=json.loads(proof.read_text())
if dev.get('source_commit')!=commit or dev.get('status')!='dev_qualified' or not dev.get('live_verification_sha256'): fail('wrong Dev qualification')
if data.get('source_commit')!=commit or data.get('date')!=today or not data.get('approved_by'): fail('current-day snapshots and human approval required')
for key in ('production_web_snapshot','production_app_snapshot'):
    ref=data.get(key)
    if not isinstance(ref,str) or len(ref)<8 or ref.lower() in ('pending','placeholder','none'): fail('confirmed server snapshot reference missing: '+key)
PY
}
