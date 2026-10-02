#!/usr/bin/env bash
# Stage exact committed source only. Existing production source and runtime stay untouched.
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
[[ $# == 2 ]] || die 'usage: 01-stage-release.sh SNAPSHOTS_JSON DEV_PROOF_JSON'
root_host
verify_evidence "$1" "$2"
assert_dirty_source
if [[ -d /opt/smn-subscription/releases ]]; then
  [[ $(stat -c %U /opt/smn-subscription/releases) == flask ]] || die 'existing release directory ownership requires inspection'
else
  install -d -o flask -g flask -m 0755 /opt/smn-subscription/releases
fi
[[ ! -e $RELEASE ]] || die 'release checkout already exists; inspect it instead of replacing'
REMOTE=$(sudo -u flask git -c safe.directory=/home/flask -C /home/flask remote get-url origin)
sudo -u flask git clone --no-checkout "$REMOTE" "$RELEASE"
sudo -u flask git -C "$RELEASE" fetch origin main
sudo -u flask git -C "$RELEASE" checkout --detach "$SHA"
assert_release
echo "Staged clean $SHA at $RELEASE. No production runtime or publication changed."
