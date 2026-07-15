#!/usr/bin/env bash
# Deploy ONLY MCP as one immutable code+runtime bundle on the current app/dev box.
# Source is fetched from the fixed canonical HTTPS origin into disposable
# unprivileged builder cgroups. The mutable gateway checkout is never read.
#
# Internal immutable controller payload. Operators invoke only the fixed root
# launcher installed at /usr/local/sbin/tradewave-mcp-release:
#   sudo /usr/local/sbin/tradewave-mcp-release <exact-lowercase-40-sha>
#   sudo /usr/local/sbin/tradewave-mcp-release --rollback
#
# Layout:
#   /home/tradewave-mcp/releases/mcp-<sha>/src   self-contained commit export
#   /home/tradewave-mcp/releases/mcp-<sha>/venv  release-local Python runtime
#   /home/tradewave-mcp/current                  atomic bundle symlink
#   /home/tradewave-mcp/previous                 rollback bundle symlink
set +x  # Secrets are read later; never permit caller-supplied `bash -x` to expose them.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP

SOURCE_ORIGIN=https://github.com/afshinmoshrefi/tradewave-tw2.git
MCP_HOME=/home/tradewave-mcp
RELEASE_ROOT=$MCP_HOME/releases
CURRENT_LINK=$MCP_HOME/current
PREVIOUS_LINK=$MCP_HOME/previous
SECRETS=/etc/tradewave/secrets.env
MCP_ENV=/etc/tradewave/mcpserver.env
API_ENV=/etc/tradewave/apiserver.env
START_GUARD=/usr/local/libexec/tradewave-mcp-start-guard.py
CONTROL_ROOT=/usr/local/libexec/tradewave-mcp-release-control
CONTROL_SETS=$CONTROL_ROOT/sets
CONTROL_CURRENT=$CONTROL_ROOT/current
TRUSTED_ASSET_ROOT=$(dirname "$(realpath -e -- "${BASH_SOURCE[0]}")")
[[ "$TRUSTED_ASSET_ROOT" =~ ^${CONTROL_SETS}/[0-9a-f]{64}$ ]] \
  || { echo "FAIL: release controller is outside a content-addressed control-plane set" >&2; exit 1; }
CONTROL_MANIFEST=$TRUSTED_ASSET_ROOT/manifest.json
CONTROL_LAUNCHER=/usr/local/sbin/tradewave-mcp-release
TRUSTED_CONTROLLER=$TRUSTED_ASSET_ROOT/deploy-mcp-release.sh
TRUSTED_WHEEL_HELPER=$TRUSTED_ASSET_ROOT/mcp-offline-wheels.py
TRUSTED_ENV_HELPER=$TRUSTED_ASSET_ROOT/mcp-service-env.py
TRUSTED_START_GUARD=$TRUSTED_ASSET_ROOT/mcp-start-guard.py
TRUSTED_PROVISION_BOOTSTRAP=$TRUSTED_ASSET_ROOT/mcp-provision-bootstrap.py
TRUSTED_PROVISIONER=$TRUSTED_ASSET_ROOT/provision-mcp-key.py
TRUSTED_PROVISION_LOCK=$TRUSTED_ASSET_ROOT/requirements-mcp-provision.lock
TRUSTED_CONTRACT_VERIFIER=$TRUSTED_ASSET_ROOT/verify_mcp_contract.py
TRUSTED_LOAD_VERIFIER=$TRUSTED_ASSET_ROOT/verify_mcp_load.py
TRUSTED_UNIT_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-mcpserver.service
TRUSTED_DROPIN_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-mcpserver-release.conf
TRUSTED_FENCE_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-mcpserver-release-fence.conf
TRUSTED_LEGACY_UNIT=$TRUSTED_ASSET_ROOT/tradewave-mcpserver-legacy.service
TRUSTED_API_UNIT_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-apiserver-immutable.service
TRUSTED_API_FENCE_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-apiserver-release-fence.conf
TRUSTED_LEGACY_API_UNIT=$TRUSTED_ASSET_ROOT/tradewave-apiserver-legacy.service
TRUSTED_NGINX_TEMPLATE=$TRUSTED_ASSET_ROOT/tradewave-developer-portal.conf
BUILD_ROOT=/run/tradewave-mcp-deploy
LEGACY_ROLLBACK_SHA=0388847bd751db0d9e89108820f27a14e43f9151
LEGACY_VERIFIER_ENV=/etc/tradewave/mcp-verifier.env
VERIFIER_STATE_ROOT=/var/lib/tradewave/mcp-verifier-probes
VERIFIER_CREDENTIAL_ROOT=/run/tradewave-mcp-verifier
VERIFIER_STATE=""
VERIFIER_CREDENTIAL=""
VERIFIER_PROBE_ACTIVE=0
MCP_KEY_STATE=/var/lib/tradewave/mcp-key-rotation.json
BASE_PYTHON=/usr/bin/python3.13
REQUIRED_PYTHON_SERIES=3.13
UNIT=/etc/systemd/system/tradewave-mcpserver.service
DROPIN=/etc/systemd/system/tradewave-mcpserver.service.d/20-immutable-release.conf
FENCE_DROPIN=/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf
API_UNIT=/etc/systemd/system/tradewave-apiserver.service
API_FENCE_DROPIN=/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf
API_SERVICE_ENABLED=/etc/systemd/system/multi-user.target.wants/tradewave-apiserver.service
SERVICE_ENABLED=/etc/systemd/system/multi-user.target.wants/tradewave-mcpserver.service
NGINX_AVAILABLE=/etc/nginx/sites-available/tradewave-developer-portal.conf
NGINX_ENABLED=/etc/nginx/sites-enabled/tradewave-developer-portal
LOCK_DIR=/run/lock/tradewave
LOCK_FILE=$LOCK_DIR/mcp-release.lock
RUNTIME_LOCK_DIR=/var/lib/tradewave-mcp-runtime-lock
RUNTIME_LOCK=$RUNTIME_LOCK_DIR/runtime.lock
RUNTIME_LOCK_HELD=0
API_RUNTIME_LOCK_DIR=/var/lib/tradewave-api-runtime-lock
API_RUNTIME_LOCK=$API_RUNTIME_LOCK_DIR/runtime.lock
API_RUNTIME_LOCK_HELD=0
TX_ROOT=/var/lib/tradewave/mcp-release-transactions
TX_ACTIVE=$TX_ROOT/active
TX_ARMED=0
TX_BACKUP=""
TX_SCRATCH=""
SYNCFS_COUNT=0
MCP_SERVICE_USER=tradewave-mcp
MCP_SERVICE_GROUP=tradewave-mcp
MCP_SERVICE_HOME=/nonexistent
MCP_SERVICE_SHELL=/usr/sbin/nologin
MCP_VERIFIER_USER=tradewave-mcp-verify
MCP_VERIFIER_GROUP=tradewave-mcp-verify
MCP_BUILDER_USER=tradewave-mcp-build
MCP_BUILDER_GROUP=tradewave-mcp-build
MCP_DEPS_USER=tradewave-mcp-deps
MCP_DEPS_GROUP=tradewave-mcp-deps
MCP_TEST_USER=tradewave-mcp-test
MCP_TEST_GROUP=tradewave-mcp-test
API_SERVICE_USER=tradewave-api
API_SERVICE_GROUP=tradewave-api
DEPLOY_UNIT=${TW_MCP_DEPLOY_UNIT:-}
CANARY_UNIT=""
CANARY_PID=""
API_CANARY_UNIT=""
API_CANARY_PID=""
API_CANARY_PORT=8088
MCP_CANARY_PORT=9090
VERIFIER_RUN_COUNT=0
VERIFIER_UNIT=""
VERIFIER_RUNNER_PID=""

fail() { echo "FAIL: $*" >&2; exit 1; }
say() { echo "  $*"; }
trusted_python() {
  env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3.13 -I -B -S "$@"
}
crash_point() {  # test-only deterministic SIGKILL seam
  if [ "${TW_MCP_TEST_CRASH_AT:-}" = "$1" ]; then
    echo "TEST CRASH POINT: $1" >&2
    kill -KILL "$$"
  fi
}

[ "$(id -u)" -eq 0 ] || fail "run as root"
[ -x "$BASE_PYTHON" ] && [ ! -L "$BASE_PYTHON" ] || fail "$BASE_PYTHON is missing or unsafe"
command -v flock >/dev/null 2>&1 || fail "flock is missing"

require_trusted_controller_payload() {
  [ "${BASH_SOURCE[0]}" = "$TRUSTED_CONTROLLER" ] \
    || fail "release controller must execute from $TRUSTED_CONTROLLER"
  trusted_python - "$TRUSTED_ASSET_ROOT" "$CONTROL_MANIFEST" \
    "$TRUSTED_CONTROLLER:0555" "$TRUSTED_WHEEL_HELPER:0555" \
    "$TRUSTED_ENV_HELPER:0555" "$TRUSTED_START_GUARD:0555" \
    "$TRUSTED_PROVISION_BOOTSTRAP:0555" "$TRUSTED_PROVISIONER:0555" \
    "$TRUSTED_CONTRACT_VERIFIER:0555" "$TRUSTED_LOAD_VERIFIER:0555" \
    "$TRUSTED_PROVISION_LOCK:0444" "$TRUSTED_UNIT_TEMPLATE:0444" "$START_GUARD:0755" \
    "$CONTROL_LAUNCHER:0755" "$FENCE_DROPIN:0644" \
    "$TRUSTED_DROPIN_TEMPLATE:0444" "$TRUSTED_FENCE_TEMPLATE:0444" \
    "$TRUSTED_LEGACY_UNIT:0444" \
    "$TRUSTED_API_UNIT_TEMPLATE:0444" "$TRUSTED_API_FENCE_TEMPLATE:0444" \
    "$TRUSTED_LEGACY_API_UNIT:0444" "$API_FENCE_DROPIN:0644" \
    "$TRUSTED_NGINX_TEMPLATE:0444" <<'PY'
import hashlib
import json
import os
import stat
import sys

set_root, manifest_path = sys.argv[1:3]
items = sys.argv[3:]
set_metadata = os.lstat(set_root)
if (
    not stat.S_ISDIR(set_metadata.st_mode)
    or stat.S_ISLNK(set_metadata.st_mode)
    or set_metadata.st_uid != 0
    or set_metadata.st_gid != 0
    or stat.S_IMODE(set_metadata.st_mode) != 0o555
):
    raise SystemExit("trusted controller set directory is unsafe")
manifest_metadata = os.lstat(manifest_path)
if (
    not stat.S_ISREG(manifest_metadata.st_mode)
    or stat.S_ISLNK(manifest_metadata.st_mode)
    or manifest_metadata.st_uid != 0
    or manifest_metadata.st_gid != 0
    or stat.S_IMODE(manifest_metadata.st_mode) != 0o444
    or manifest_metadata.st_nlink != 1
):
    raise SystemExit("trusted controller manifest metadata is unsafe")
raw_manifest = open(manifest_path, "rb").read()
if hashlib.sha256(raw_manifest).hexdigest() != os.path.basename(set_root):
    raise SystemExit("trusted controller set name does not bind its manifest")
try:
    manifest = json.loads(raw_manifest.decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("trusted controller manifest is invalid JSON") from exc
if raw_manifest != (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode():
    raise SystemExit("trusted controller manifest is not canonical JSON")
if not isinstance(manifest, dict) or set(manifest) != {"bootstraps", "files", "schema", "source"}:
    raise SystemExit("trusted controller manifest schema is invalid")
if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), dict) \
        or not isinstance(manifest.get("bootstraps"), dict):
    raise SystemExit("trusted controller manifest fields are invalid")
source = manifest.get("source")
if (
    not isinstance(source, dict)
    or set(source) != {"commit_sha"}
    or not isinstance(source.get("commit_sha"), str)
    or __import__("re").fullmatch(r"[0-9a-f]{40}", source["commit_sha"]) is None
):
    raise SystemExit("trusted controller manifest source commit is invalid")
if set(os.listdir(set_root)) != set(manifest["files"]) | {"manifest.json"}:
    raise SystemExit("trusted controller set has unexpected children")

for item in items:
    raw, encoded_mode = item.rsplit(":", 1)
    expected_mode = int(encoded_mode, 8)
    if raw != os.path.abspath(raw) or os.path.realpath(raw) != raw:
        raise SystemExit(f"trusted controller payload path is not canonical: {raw}")
    metadata = os.lstat(raw)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != expected_mode
        or metadata.st_nlink != 1
    ):
        raise SystemExit(f"trusted controller payload metadata is unsafe: {raw}")
    current = "/"
    for component in raw.strip("/").split("/")[:-1]:
        current = os.path.join(current, component)
        parent = os.lstat(current)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_ISLNK(parent.st_mode)
            or parent.st_uid != 0
            or parent.st_gid != 0
            or stat.S_IMODE(parent.st_mode) & 0o022
        ):
            raise SystemExit(f"trusted controller payload ancestor is unsafe: {current}")
    payload = open(raw, "rb").read()
    key = os.path.basename(raw) if os.path.dirname(raw) == set_root else raw
    records = manifest["files"] if os.path.dirname(raw) == set_root else manifest["bootstraps"]
    record = records.get(key)
    if (
        not isinstance(record, dict)
        or set(record) != {"mode", "sha256"}
        or record.get("mode") != expected_mode
        or record.get("sha256") != hashlib.sha256(payload).hexdigest()
    ):
        raise SystemExit(f"trusted controller manifest does not bind payload: {raw}")
PY
}

require_transient_deploy_unit() {
  local main_pid fragment owner mode protect_system inaccessible read_write environment limit_core
  [[ "$DEPLOY_UNIT" =~ ^tradewave-mcp-deploy-[0-9a-f-]{36}\.service$ ]] \
    || fail "TW_MCP_DEPLOY_UNIT is not a canonical transient deploy unit"
  systemctl is-active --quiet "$DEPLOY_UNIT" \
    || fail "trusted transient deploy unit is not active: $DEPLOY_UNIT"
  main_pid=$(systemctl show "$DEPLOY_UNIT" --property=MainPID --value)
  [ "$main_pid" = "$$" ] \
    || fail "deploy shell PID $$ is not MainPID of $DEPLOY_UNIT (found $main_pid)"
  fragment=$(systemctl show "$DEPLOY_UNIT" --property=FragmentPath --value)
  [ "$fragment" = "/run/systemd/transient/$DEPLOY_UNIT" ] \
    || fail "deploy unit is not rooted in /run/systemd/transient"
  [ -f "$fragment" ] && [ ! -L "$fragment" ] || fail "transient deploy unit fragment is unsafe"
  owner=$(stat -c '%U:%G' "$fragment")
  mode=$(stat -c '%a' "$fragment")
  [ "$owner" = root:root ] && [ $((8#$mode & 0022)) -eq 0 ] \
    || fail "transient deploy unit fragment is not root-controlled"
  protect_system=$(systemctl show "$DEPLOY_UNIT" --property=ProtectSystem --value)
  [ "$protect_system" = strict ] \
    || fail "transient deploy unit does not enforce ProtectSystem=strict"
  inaccessible=$(systemctl show "$DEPLOY_UNIT" --property=InaccessiblePaths --value)
  read_write=$(systemctl show "$DEPLOY_UNIT" --property=ReadWritePaths --value)
  environment=$(systemctl show "$DEPLOY_UNIT" --property=Environment --value)
  limit_core=$(systemctl show "$DEPLOY_UNIT" --property=LimitCORE --value)
  [ "$limit_core" = 0 ] || fail "transient deploy unit does not disable core dumps"
  trusted_python - "$inaccessible" "$read_write" "$environment" <<'PY'
import shlex
import sys


def paths(value: str) -> set[str]:
    return {item.lstrip("-+") for item in shlex.split(value)}


inaccessible = paths(sys.argv[1])
if not {"/root", "/home/flask"}.issubset(inaccessible):
    raise SystemExit("transient deploy unit can access a forbidden home directory")
expected_writable = {
    "/home/tradewave-mcp",
    "/etc/systemd/system",
    "/etc/nginx",
    "/etc/tradewave",
    "/var/lib/tradewave",
    "/var/lib/tradewave-mcp-runtime-lock",
    "/var/lib/tradewave-api-runtime-lock",
    "/run/lock/tradewave",
    "/run/tradewave-mcp-deploy",
    "/run/tradewave-mcp-verifier",
}
if paths(sys.argv[2]) != expected_writable:
    raise SystemExit("transient deploy unit writable path set is not exact")
environment = set(shlex.split(sys.argv[3]))
if "HOME=/nonexistent" not in environment or any(item == "HOME=/root" for item in environment):
    raise SystemExit("transient deploy unit HOME is not isolated")
PY
}

require_trusted_controller_payload
require_transient_deploy_unit

ensure_root_path() {  # ensure_root_path <absolute-path> <create-mode> <exact|safe>
  trusted_python - "$1" "$2" "$3" <<'PY'
import os
import stat
import sys

path = os.path.abspath(sys.argv[1])
mode = int(sys.argv[2], 8)
policy = sys.argv[3]
if sys.argv[1] != path or path == "/" or policy not in {"exact", "safe"}:
    raise SystemExit("unsafe root-owned directory request")

current = "/"
for index, component in enumerate(path.strip("/").split("/")):
    current = os.path.join(current, component)
    final = index == len(path.strip("/").split("/")) - 1
    if os.path.lexists(current):
        metadata = os.lstat(current)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise SystemExit(f"unsafe root-owned directory component: {current}")
        if final and policy == "exact" and stat.S_IMODE(metadata.st_mode) != mode:
            raise SystemExit(f"wrong mode on {current}; want {mode:04o}")
        continue
    parent = os.path.dirname(current)
    os.mkdir(current, mode if final else 0o755)
    os.chown(current, 0, 0)
    os.chmod(current, mode if final else 0o755)
    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
PY
}

# Never let install(1) follow an attacker/accidental symlink at the release
# root. Components are lstat'd and creation is fsync'd one directory at a time.
ensure_root_path "$MCP_HOME" 0755 exact
ensure_root_path "$RELEASE_ROOT" 0755 exact
ensure_root_path "$(dirname "$TX_ROOT")" 0700 safe
[ ! -L "$LOCK_DIR" ] || fail "$LOCK_DIR must not be a symlink"
mkdir -m 0700 "$LOCK_DIR" 2>/dev/null || true
[ ! -L "$LOCK_DIR" ] && [ -d "$LOCK_DIR" ] \
  && [ "$(stat -c '%U:%G %a' "$LOCK_DIR")" = "root:root 700" ] \
  || fail "$LOCK_DIR must be a root:root mode 0700 directory"
if [ -e "$LOCK_FILE" ] || [ -L "$LOCK_FILE" ]; then
  [ -f "$LOCK_FILE" ] && [ ! -L "$LOCK_FILE" ] \
    || fail "$LOCK_FILE must be a non-symlink regular file"
  [ "$(stat -c '%U:%G %a' "$LOCK_FILE")" = "root:root 600" ] \
    || fail "$LOCK_FILE must be root:root mode 0600"
else
  install -o root -g root -m 0600 /dev/null "$LOCK_FILE"
fi
exec 9<>"$LOCK_FILE"
flock -n 9 || fail "another MCP release/rollback is already running"
# The launcher selected this immutable set before the lock. An installer may
# have won the lock and advanced CURRENT in between; never let a coherent but
# stale controller generation proceed against a newer guard/journal contract.
[ -L "$CONTROL_CURRENT" ] \
  && [ "$(stat -c '%U:%G %h' "$CONTROL_CURRENT")" = "root:root 1" ] \
  && [ "$(readlink "$CONTROL_CURRENT")" = "sets/${TRUSTED_ASSET_ROOT##*/}" ] \
  && [ "$(readlink -f "$CONTROL_CURRENT")" = "$TRUSTED_ASSET_ROOT" ] \
  || fail "atomic control-plane current changed before this controller acquired the release lock"
require_trusted_controller_payload

atomic_symlink() {  # atomic_symlink <stored-target> <link> [owner]
  local target="$1" link="$2" owner="${3:-root:root}" tmp="${2}.tmp.$$"
  rm -f "$tmp"
  ln -s "$target" "$tmp"
  chown -h "$owner" "$tmp"
  mv -Tf "$tmp" "$link"
}

bundle_for_sha() { printf '%s/mcp-%s' "$RELEASE_ROOT" "$1"; }

bundle_sha() {  # bundle_sha <bundle>
  seal_value release_sha "$1/.sealed"
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

require_release_python() {
  trusted_python - <<'PY' || fail "system Python trust boundary failed"
import os
import platform
import sys

if (
    platform.python_implementation() != "CPython"
    or sys.version_info[:2] != (3, 13)
    or platform.machine() != "x86_64"
    or platform.libc_ver() != ("glibc", "2.39")
    or sys.executable != "/usr/bin/python3.13"
    or os.path.realpath(sys.executable) != "/usr/bin/python3.13"
    or sys._base_executable != "/usr/bin/python3.13"
    or sys.prefix != "/usr"
    or sys.base_prefix != "/usr"
    or tuple(sys.path) != (
        "/usr/lib/python313.zip",
        "/usr/lib/python3.13",
        "/usr/lib/python3.13/lib-dynload",
    )
    or not sys.flags.isolated
    or not sys.flags.dont_write_bytecode
    or not sys.flags.no_site
    or not sys.flags.no_user_site
    or not sys.flags.ignore_environment
    or not sys.flags.safe_path
    or {"site", "sitecustomize", "usercustomize"}.intersection(sys.modules)
):
    raise SystemExit("not the exact isolated system CPython 3.13 runtime")
PY
}

ensure_exact_system_identity() {  # <user> <group>
  local account_name="$1" group_name="$2"
  [ -x "$MCP_SERVICE_SHELL" ] || fail "$MCP_SERVICE_SHELL is missing"
  command -v getent >/dev/null 2>&1 || fail "getent is missing"
  command -v groupadd >/dev/null 2>&1 || fail "groupadd is missing"
  command -v useradd >/dev/null 2>&1 || fail "useradd is missing"

  # Never modify or repurpose a pre-existing account. If either reserved name is
  # already present, the complete identity check below must accept it as-is.
  if getent passwd "$account_name" >/dev/null 2>&1 \
      && ! getent group "$group_name" >/dev/null 2>&1; then
    fail "$account_name exists without its reserved primary group"
  fi
  if ! getent group "$group_name" >/dev/null 2>&1; then
    groupadd --system "$group_name"
  fi
  if ! getent passwd "$account_name" >/dev/null 2>&1; then
    useradd --system --gid "$group_name" --no-user-group \
      --home-dir "$MCP_SERVICE_HOME" --no-create-home \
      --shell "$MCP_SERVICE_SHELL" --comment "" "$account_name"
  fi

  trusted_python - "$account_name" "$group_name" \
    "$MCP_SERVICE_HOME" "$MCP_SERVICE_SHELL" <<'PY'
import grp
import os
import pwd
import sys

name, group_name, home, shell = sys.argv[1:]
try:
    account = pwd.getpwnam(name)
    group = grp.getgrnam(group_name)
except KeyError as exc:
    raise SystemExit(f"dedicated MCP identity is incomplete: {exc}")
groups = os.getgrouplist(name, account.pw_gid)
if (
    account.pw_uid <= 0
    or account.pw_uid >= 1000
    or group.gr_gid <= 0
    or group.gr_gid >= 1000
    or account.pw_gid != group.gr_gid
    or account.pw_dir != home
    or account.pw_shell != shell
    or account.pw_gecos != ""
    or group.gr_mem != []
    or groups != [group.gr_gid]
):
    raise SystemExit(f"reserved {name} account/group does not match the exact service identity")
PY
}

ensure_mcp_service_identities() {
  ensure_exact_system_identity "$MCP_SERVICE_USER" "$MCP_SERVICE_GROUP"
  ensure_exact_system_identity "$MCP_VERIFIER_USER" "$MCP_VERIFIER_GROUP"
  ensure_exact_system_identity "$MCP_BUILDER_USER" "$MCP_BUILDER_GROUP"
  ensure_exact_system_identity "$MCP_DEPS_USER" "$MCP_DEPS_GROUP"
  ensure_exact_system_identity "$MCP_TEST_USER" "$MCP_TEST_GROUP"
  ensure_exact_system_identity "$API_SERVICE_USER" "$API_SERVICE_GROUP"
  trusted_python - \
    "$MCP_SERVICE_USER:$MCP_SERVICE_GROUP" \
    "$MCP_VERIFIER_USER:$MCP_VERIFIER_GROUP" \
    "$MCP_BUILDER_USER:$MCP_BUILDER_GROUP" \
    "$MCP_DEPS_USER:$MCP_DEPS_GROUP" \
    "$MCP_TEST_USER:$MCP_TEST_GROUP" \
    "$API_SERVICE_USER:$API_SERVICE_GROUP" <<'PY'
import grp
import pwd
import sys

pairs = [item.split(":", 1) for item in sys.argv[1:]]
accounts = {name: pwd.getpwnam(name) for name, _ in pairs}
groups = {name: grp.getgrnam(name) for _, name in pairs}
uids = {account.pw_uid for account in accounts.values()}
gids = {group.gr_gid for group in groups.values()}
if len(uids) != len(pairs) or len(gids) != len(pairs):
    raise SystemExit("reserved MCP identities must have pairwise-distinct UIDs and GIDs")
expected_uid_names = {account.pw_uid: name for name, account in accounts.items()}
expected_gid_names = {group.gr_gid: name for name, group in groups.items()}
expected_primary_ids = {
    (accounts[account_name].pw_uid, groups[group_name].gr_gid)
    for account_name, group_name in pairs
}
for account in pwd.getpwall():
    expected = expected_uid_names.get(account.pw_uid)
    if expected is not None and account.pw_name != expected:
        raise SystemExit(
            f"reserved MCP uid {account.pw_uid} is aliased by {account.pw_name!r}"
        )
    if (
        account.pw_gid in gids
        and (account.pw_uid, account.pw_gid) not in expected_primary_ids
    ):
        raise SystemExit(
            f"reserved MCP primary gid {account.pw_gid} is aliased by "
            f"{account.pw_name!r}"
        )
for group in grp.getgrall():
    expected = expected_gid_names.get(group.gr_gid)
    if expected is not None and group.gr_name != expected:
        raise SystemExit(
            f"reserved MCP gid {group.gr_gid} is aliased by {group.gr_name!r}"
        )
PY
}

ensure_one_runtime_lock_file() {  # <directory> <lock> <service-user> <service-group>
  local directory="$1" lock="$2" service_user="$3" service_group="$4"
  local service_uid service_gid
  service_uid=$(id -u "$service_user")
  service_gid=$(getent group "$service_group" | awk -F: '{print $3}')
  trusted_python - "$directory" "$lock" "$service_gid" <<'PY'
import os
import stat
import sys

directory, path, encoded_gid = sys.argv[1:]
gid = int(encoded_gid)
parent = os.path.dirname(directory)
current = "/"
for component in parent.strip("/").split("/"):
    if component:
        current = os.path.join(current, component)
    parent_metadata = os.lstat(current)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != 0
        or parent_metadata.st_gid != 0
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise SystemExit(f"runtime-lock ancestor is not root-controlled: {current}")
if not os.path.lexists(directory):
    os.mkdir(directory, 0o750)
    os.chown(directory, 0, gid)
    os.chmod(directory, 0o750)
    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
metadata = os.lstat(directory)
# The fixed launcher may have created this empty mount target before the
# service group existed so ProtectSystem=strict could bind it writable. Permit
# exactly that root:root bootstrap state to transition once, after identities
# have been created and verified.
if (
    stat.S_ISDIR(metadata.st_mode)
    and not stat.S_ISLNK(metadata.st_mode)
    and metadata.st_uid == 0
    and metadata.st_gid == 0
    and stat.S_IMODE(metadata.st_mode) == 0o750
    and not os.listdir(directory)
):
    os.chown(directory, 0, gid)
    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    metadata = os.lstat(directory)
if (
    not stat.S_ISDIR(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != gid
    or stat.S_IMODE(metadata.st_mode) != 0o750
):
    raise SystemExit("runtime-lock directory metadata is unsafe")
if not os.path.lexists(path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o640)
    try:
        os.fchown(fd, 0, gid)
        os.fchmod(fd, 0o640)
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != gid
    or stat.S_IMODE(metadata.st_mode) != 0o640
    or metadata.st_nlink != 1
    or metadata.st_size != 0
):
    raise SystemExit("runtime-lock file metadata is unsafe")
PY
  /usr/bin/setpriv --reuid="$service_uid" --regid="$service_gid" --clear-groups -- \
    /usr/bin/flock --shared --nonblock "$lock" /bin/true \
    || fail "$service_user cannot traverse and share-lock $lock"
}

ensure_runtime_lock_file() {
  ensure_one_runtime_lock_file \
    "$RUNTIME_LOCK_DIR" "$RUNTIME_LOCK" "$MCP_SERVICE_USER" "$MCP_SERVICE_GROUP"
  exec 8<>"$RUNTIME_LOCK"
}

ensure_api_runtime_lock_file() {
  ensure_one_runtime_lock_file \
    "$API_RUNTIME_LOCK_DIR" "$API_RUNTIME_LOCK" "$API_SERVICE_USER" "$API_SERVICE_GROUP"
  exec 7<>"$API_RUNTIME_LOCK"
}

acquire_runtime_lock_exclusive() {
  if [ "$RUNTIME_LOCK_HELD" = 1 ]; then
    return 0
  fi
  flock -n -x 8 \
    || fail "persistent MCP runtime lock is unexpectedly held after service stop"
  RUNTIME_LOCK_HELD=1
}

release_runtime_lock() {
  if [ "$RUNTIME_LOCK_HELD" = 1 ]; then
    flock -u 8 || fail "could not release persistent MCP runtime lock"
    RUNTIME_LOCK_HELD=0
  fi
}

acquire_api_runtime_lock_exclusive() {
  if [ "$API_RUNTIME_LOCK_HELD" = 1 ]; then
    return 0
  fi
  flock -n -x 7 \
    || fail "persistent API gateway runtime lock is unexpectedly held after service stop"
  API_RUNTIME_LOCK_HELD=1
}

release_api_runtime_lock() {
  if [ "$API_RUNTIME_LOCK_HELD" = 1 ]; then
    flock -u 7 || fail "could not release persistent API gateway runtime lock"
    API_RUNTIME_LOCK_HELD=0
  fi
}

seal_value() {  # seal_value <key> <seal-file>
  trusted_python - "$1" "$2" <<'PY'
import os
import re
import stat
import sys

key, path = sys.argv[1:]
if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
    raise SystemExit("invalid release seal key selector")
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o444
    or metadata.st_nlink != 1
):
    raise SystemExit("release seal metadata is unsafe")
with open(path, "r", encoding="ascii", newline="") as handle:
    lines = handle.read(64 * 1024 + 1)
if len(lines) > 64 * 1024:
    raise SystemExit("release seal is oversized")
values = {}
for number, line in enumerate(lines.splitlines(), 1):
    if not line or "=" not in line:
        raise SystemExit(f"malformed release seal line {number}")
    name, value = line.split("=", 1)
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
        or not value
        or any(character.isspace() for character in value)
        or name in values
    ):
        raise SystemExit(f"malformed release seal line {number}")
    values[name] = value
if key not in values:
    raise SystemExit(f"release seal is missing {key}")
print(values[key])
PY
}

json_inventory_value() {  # json_inventory_value <canonical-json-file> <key>
  trusted_python - "$1" "$2" <<'PY'
import json
import os
import stat
import sys

path, key = sys.argv[1:]
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o444
    or metadata.st_nlink != 1
    or metadata.st_size > 16 * 1024 * 1024
):
    raise SystemExit("dependency inventory metadata is unsafe")
raw = open(path, "rb", buffering=0).read()
try:
    value = json.loads(raw)
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("dependency inventory is not valid JSON") from exc
canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
if raw != canonical or not isinstance(value, dict):
    raise SystemExit("dependency inventory is not canonical JSON")
selected = value.get(key)
if not isinstance(selected, (str, int)) or isinstance(selected, bool):
    raise SystemExit(f"dependency inventory lacks scalar {key}")
print(selected)
PY
}

key_value_inventory_value() {  # key_value_inventory_value <file> <key>
  trusted_python - "$1" "$2" <<'PY'
import os
import re
import stat
import sys

path, selected = sys.argv[1:]
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o444
    or metadata.st_nlink != 1
    or metadata.st_size > 64 * 1024
):
    raise SystemExit("key/value inventory metadata is unsafe")
values = {}
for number, line in enumerate(open(path, "r", encoding="ascii"), 1):
    line = line.rstrip("\n")
    if "=" not in line:
        raise SystemExit(f"malformed inventory line {number}")
    key, value = line.split("=", 1)
    if not re.fullmatch(r"[a-z][a-z0-9_]+", key) or not re.fullmatch(r"[0-9a-f]{64}", value) or key in values:
        raise SystemExit(f"malformed inventory line {number}")
    values[key] = value
if selected not in values:
    raise SystemExit(f"inventory lacks {selected}")
print(values[selected])
PY
}

bundle_content_sha256() {  # bundle_content_sha256 <root-owned-bundle>
  # This implementation is embedded in the trusted root entrypoint. Never run a
  # candidate-supplied manifest helper before these bytes have been authenticated.
  trusted_python - "$1" <<'PY'
import hashlib
import os
import stat
import struct
import sys

root_text = os.path.abspath(sys.argv[1])
if root_text != sys.argv[1] or not os.path.lexists(root_text):
    raise SystemExit("bundle manifest root must be an existing canonical absolute path")
root = os.fsencode(root_text)
entries = []


def collect(relative: bytes) -> None:
    path = root if relative == b"." else os.path.join(root, relative)
    metadata = os.lstat(path)
    if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        kind = b"D"
    elif stat.S_ISREG(metadata.st_mode):
        kind = b"F"
    elif stat.S_ISLNK(metadata.st_mode):
        kind = b"L"
    else:
        raise SystemExit(f"unsupported bundle entry type: {os.fsdecode(relative)}")
    entries.append((relative, kind, metadata))
    if kind == b"D":
        names = sorted(entry.name for entry in os.scandir(path))
        for name in names:
            child = name if relative == b"." else os.path.join(relative, name)
            if child == b".sealed":
                continue
            collect(child)


collect(b".")
digest = hashlib.sha256(b"TW_MCP_BUNDLE_CONTENT_V1\0")
for relative, kind, captured in sorted(entries, key=lambda item: item[0]):
    path = root if relative == b"." else os.path.join(root, relative)
    digest.update(kind)
    digest.update(struct.pack(">I", stat.S_IMODE(captured.st_mode)))
    digest.update(struct.pack(">Q", len(relative)))
    digest.update(relative)
    if kind == b"F":
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            named = os.lstat(path)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or (opened.st_dev, opened.st_ino) != (captured.st_dev, captured.st_ino)
                or stat.S_IMODE(opened.st_mode) != stat.S_IMODE(captured.st_mode)
            ):
                raise SystemExit(f"bundle file changed during hashing: {os.fsdecode(relative)}")
            file_digest = hashlib.sha256()
            size = 0
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                file_digest.update(chunk)
            after = os.fstat(fd)
            if size != opened.st_size or (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                raise SystemExit(f"bundle file changed while hashing: {os.fsdecode(relative)}")
        finally:
            os.close(fd)
        digest.update(struct.pack(">Q", size))
        digest.update(file_digest.digest())
    elif kind == b"L":
        target = os.readlink(path)
        after = os.lstat(path)
        if (after.st_dev, after.st_ino) != (captured.st_dev, captured.st_ino):
            raise SystemExit(f"bundle symlink changed while hashing: {os.fsdecode(relative)}")
        digest.update(struct.pack(">Q", len(target)))
        digest.update(target)
print(digest.hexdigest())
PY
}

bundle_tree_policy() {  # bundle_tree_policy <freeze|verify> <bundle>
  trusted_python - "$1" "$2" <<'PY'
import os
import stat
import sys

action, root = sys.argv[1:]
root = os.path.abspath(root)
if action not in {"freeze", "verify"} or sys.argv[2] != root:
    raise SystemExit("invalid bundle tree policy request")
expected_links = {
    os.path.join(root, "venv", "bin", "python"),
    os.path.join(root, "gateway-venv", "bin", "python"),
    os.path.join(root, "provision-venv", "bin", "python"),
}
seen_links = set()
nodes = []

def visit(path: str, relative: str) -> None:
    metadata = os.lstat(path)
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        raise SystemExit(f"bundle entry is not root-owned: {relative}")
    if stat.S_ISLNK(metadata.st_mode):
        if path not in expected_links or os.readlink(path) != "/usr/bin/python3.13":
            raise SystemExit(f"bundle has an unexpected symlink: {relative}")
        if os.path.realpath(path) != "/usr/bin/python3.13":
            raise SystemExit(f"bundle interpreter link is unsafe: {relative}")
        seen_links.add(path)
    elif stat.S_ISREG(metadata.st_mode):
        if metadata.st_nlink != 1:
            raise SystemExit(f"bundle has a hard-linked file: {relative}")
    elif not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit(f"bundle has a special file: {relative}")
    nodes.append((path, relative, metadata))
    if stat.S_ISDIR(metadata.st_mode):
        with os.scandir(path) as iterator:
            children = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
        for child in children:
            child_relative = child.name if relative == "." else f"{relative}/{child.name}"
            if child.name == ".git":
                raise SystemExit(f"bundle contains forbidden Git metadata: {child_relative}")
            visit(os.path.join(path, child.name), child_relative)

visit(root, ".")
if seen_links != expected_links:
    raise SystemExit("bundle does not contain the three exact interpreter links")
for path, relative, metadata in reversed(nodes):
    if stat.S_ISLNK(metadata.st_mode):
        continue
    expected_mode = 0o555 if stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o111 else 0o444
    if relative == ".sealed":
        expected_mode = 0o444
    if action == "freeze":
        if relative == ".sealed":
            raise SystemExit("cannot freeze a bundle that is already sealed")
        os.chmod(path, expected_mode)
    elif stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise SystemExit(
            f"bundle entry mode mismatch: {relative} is {stat.S_IMODE(metadata.st_mode):04o}, want {expected_mode:04o}"
        )
PY
}

freeze_bundle_tree() { bundle_tree_policy freeze "$1"; }
verify_bundle_tree_metadata() { bundle_tree_policy verify "$1"; }

verify_minimal_venv() {  # verify_minimal_venv <venv>
  trusted_python - "$1" <<'PY'
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
expected = {
    ".": {"bin", "lib", "pyvenv.cfg"},
    "bin": {"python"},
    "lib": {"python3.13"},
    "lib/python3.13": {"site-packages"},
}
for relative, names in expected.items():
    path = root if relative == "." else os.path.join(root, relative)
    metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o555:
        raise SystemExit(f"minimal venv directory is not exact: {relative}")
    if set(os.listdir(path)) != names:
        raise SystemExit(f"minimal venv skeleton has unexpected entries: {relative}")
link = os.path.join(root, "bin", "python")
if os.readlink(link) != "/usr/bin/python3.13" or os.path.realpath(link) != "/usr/bin/python3.13":
    raise SystemExit("minimal venv interpreter link is not exact")
configuration = open(os.path.join(root, "pyvenv.cfg"), "r", encoding="ascii", newline="").read()
if configuration != (
    "home = /usr/bin\n"
    "include-system-site-packages = false\n"
    "version = 3.13\n"
    "executable = /usr/bin/python3.13\n"
):
    raise SystemExit("minimal venv configuration is not exact")
PY
}

verify_release_seal_schema() {  # <seal>
  trusted_python - "$1" <<'PY'
import os
import re
import stat
import sys

path = sys.argv[1]
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o444
    or metadata.st_nlink != 1
):
    raise SystemExit("release seal metadata is unsafe")
values = {}
for number, line in enumerate(open(path, "r", encoding="ascii"), 1):
    line = line.rstrip("\n")
    if "=" not in line:
        raise SystemExit(f"malformed release seal line {number}")
    key, value = line.split("=", 1)
    if key in values or not value:
        raise SystemExit(f"malformed release seal line {number}")
    values[key] = value
expected = {
    "release_sha",
    "bundle_content_sha256",
    "runtime_lock_sha256",
    "runtime_wheel_manifest_sha256",
    "runtime_manifest_sha256",
    "runtime_tree_sha256",
    "gateway_lock_sha256",
    "gateway_wheel_manifest_sha256",
    "gateway_manifest_sha256",
    "gateway_tree_sha256",
    "provision_lock_sha256",
    "provision_wheel_manifest_sha256",
    "provision_manifest_sha256",
    "provision_tree_sha256",
}
if set(values) != expected:
    raise SystemExit("release seal schema is not exact")
if not re.fullmatch(r"[0-9a-f]{40}", values["release_sha"]):
    raise SystemExit("release seal SHA is invalid")
for key in expected - {"release_sha"}:
    if not re.fullmatch(r"[0-9a-f]{64}", values[key]):
        raise SystemExit(f"release seal {key} is invalid")
PY
}

verify_sealed_bundle() {  # verify_sealed_bundle <bundle> <sha>
  local bundle="$1" sha="$2" seal runtime_lock gateway_lock provision_lock expected actual
  local runtime_inventory gateway_inventory provision_inventory provision_bootstrap
  seal="$bundle/.sealed"
  runtime_lock="$bundle/artifacts/runtime.lock"
  gateway_lock="$bundle/artifacts/gateway.lock"
  provision_lock="$bundle/artifacts/provision.lock"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "invalid requested bundle SHA"
  [ "$bundle" = "$(bundle_for_sha "$sha")" ] \
    || fail "bundle path is not canonical for SHA $sha"
  [ -d "$bundle" ] && [ ! -L "$bundle" ] || fail "$bundle is not a real directory"
  verify_bundle_tree_metadata "$bundle"
  verify_release_seal_schema "$seal"
  [ "$(seal_value release_sha "$seal")" = "$sha" ] || fail "$bundle seal SHA mismatch"
  expected=$(seal_value bundle_content_sha256 "$seal")
  actual=$(bundle_content_sha256 "$bundle")
  [ "$actual" = "$expected" ] || fail "$bundle content digest drift"

  for artifact in runtime.lock gateway.lock provision.lock test.lock mcp-provision-bootstrap.py \
    provision-mcp-key.py runtime-wheels.json provision-wheels.json \
    gateway-wheels.json runtime-installed.json gateway-installed.json \
    provision-installed.json provision-bootstrap.txt; do
    [ -r "$bundle/artifacts/$artifact" ] || fail "$bundle artifact is missing: $artifact"
  done
  cmp -s "$bundle/artifacts/mcp-provision-bootstrap.py" "$TRUSTED_PROVISION_BOOTSTRAP" \
    || fail "$bundle provision bootstrap differs from the fixed controller asset"
  cmp -s "$bundle/artifacts/provision-mcp-key.py" "$TRUSTED_PROVISIONER" \
    || fail "$bundle provisioner differs from the fixed controller asset"
  cmp -s "$provision_lock" "$TRUSTED_PROVISION_LOCK" \
    || fail "$bundle provision lock differs from the fixed controller asset"
  verify_minimal_venv "$bundle/venv"
  verify_minimal_venv "$bundle/gateway-venv"
  verify_minimal_venv "$bundle/provision-venv"

  [ "$(sha256_file "$runtime_lock")" = "$(seal_value runtime_lock_sha256 "$seal")" ] \
    || fail "$bundle runtime lock digest drift"
  [ "$(sha256_file "$provision_lock")" = "$(seal_value provision_lock_sha256 "$seal")" ] \
    || fail "$bundle provision lock digest drift"
  [ "$(sha256_file "$gateway_lock")" = "$(seal_value gateway_lock_sha256 "$seal")" ] \
    || fail "$bundle gateway lock digest drift"
  [ "$(json_inventory_value "$bundle/artifacts/runtime-wheels.json" wheel_manifest_sha256)" = \
      "$(seal_value runtime_wheel_manifest_sha256 "$seal")" ] \
    || fail "$bundle runtime wheel inventory drift"
  [ "$(json_inventory_value "$bundle/artifacts/provision-wheels.json" wheel_manifest_sha256)" = \
      "$(seal_value provision_wheel_manifest_sha256 "$seal")" ] \
    || fail "$bundle provision wheel inventory drift"
  [ "$(json_inventory_value "$bundle/artifacts/gateway-wheels.json" wheel_manifest_sha256)" = \
      "$(seal_value gateway_wheel_manifest_sha256 "$seal")" ] \
    || fail "$bundle gateway wheel inventory drift"

  runtime_inventory=$(trusted_python "$TRUSTED_WHEEL_HELPER" verify-install \
    --lock "$runtime_lock" --wheelhouse "$bundle/wheelhouse/runtime" \
    --site-packages "$bundle/venv/lib/python3.13/site-packages") \
    || fail "$bundle runtime installed tree failed fixed inventory verification"
  [ "$runtime_inventory" = "$(cat "$bundle/artifacts/runtime-installed.json")" ] \
    || fail "$bundle runtime installed inventory drift"
  [ "$(json_inventory_value "$bundle/artifacts/runtime-installed.json" installed_manifest_sha256)" = \
      "$(seal_value runtime_manifest_sha256 "$seal")" ] \
    || fail "$bundle runtime manifest seal drift"
  [ "$(json_inventory_value "$bundle/artifacts/runtime-installed.json" installed_tree_sha256)" = \
      "$(seal_value runtime_tree_sha256 "$seal")" ] \
    || fail "$bundle runtime tree seal drift"

  gateway_inventory=$(trusted_python "$TRUSTED_WHEEL_HELPER" verify-install \
    --lock "$gateway_lock" --wheelhouse "$bundle/wheelhouse/gateway" \
    --site-packages "$bundle/gateway-venv/lib/python3.13/site-packages") \
    || fail "$bundle gateway installed tree failed fixed inventory verification"
  [ "$gateway_inventory" = "$(cat "$bundle/artifacts/gateway-installed.json")" ] \
    || fail "$bundle gateway installed inventory drift"
  [ "$(json_inventory_value "$bundle/artifacts/gateway-installed.json" installed_manifest_sha256)" = \
      "$(seal_value gateway_manifest_sha256 "$seal")" ] \
    || fail "$bundle gateway manifest seal drift"
  [ "$(json_inventory_value "$bundle/artifacts/gateway-installed.json" installed_tree_sha256)" = \
      "$(seal_value gateway_tree_sha256 "$seal")" ] \
    || fail "$bundle gateway tree seal drift"

  provision_inventory=$(trusted_python "$TRUSTED_WHEEL_HELPER" verify-install \
    --lock "$provision_lock" --wheelhouse "$bundle/wheelhouse/provision" \
    --site-packages "$bundle/provision-venv/lib/python3.13/site-packages") \
    || fail "$bundle provision installed tree failed fixed inventory verification"
  [ "$provision_inventory" = "$(cat "$bundle/artifacts/provision-installed.json")" ] \
    || fail "$bundle provision installed inventory drift"
  provision_bootstrap=$(trusted_python "$bundle/artifacts/mcp-provision-bootstrap.py" verify \
    --bundle "$bundle" --lock "$provision_lock") \
    || fail "$bundle provision bootstrap seal verification failed"
  [ "$provision_bootstrap" = "$(cat "$bundle/artifacts/provision-bootstrap.txt")" ] \
    || fail "$bundle provision bootstrap inventory drift"
  [ "$(key_value_inventory_value "$bundle/artifacts/provision-bootstrap.txt" provision_manifest_sha256)" = \
      "$(seal_value provision_manifest_sha256 "$seal")" ] \
    || fail "$bundle provision manifest seal drift"
  [ "$(key_value_inventory_value "$bundle/artifacts/provision-bootstrap.txt" provision_tree_sha256)" = \
      "$(seal_value provision_tree_sha256 "$seal")" ] \
    || fail "$bundle provision tree seal drift"
}

BUILD_WORKSPACES=()
PREPARED_SOURCE_WORKSPACE=""
PREPARED_RUNTIME_DOWNLOAD=""
PREPARED_GATEWAY_DOWNLOAD=""
PREPARED_PROVISION_DOWNLOAD=""
PREPARED_TEST_DOWNLOAD=""
PREPARED_RUNTIME_LOCK_SOURCE=""
PREPARED_GATEWAY_LOCK_SOURCE=""
PREPARED_TEST_LOCK_SOURCE=""
cleanup_build_workspaces() {
  local workspace parent base
  set +e
  for workspace in "${BUILD_WORKSPACES[@]}"; do
    parent=$(dirname -- "$workspace")
    base=$(basename -- "$workspace")
    if [ "$parent" = "$BUILD_ROOT" ] \
        && [[ "$base" =~ ^(source|dependencies)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
      :
    elif [ "$parent" = "$RELEASE_ROOT" ] \
        && [[ "$base" =~ ^\.build-mcp-[0-9a-f]{40}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
      :
    else
      echo "REFUSING unsafe build-workspace cleanup path: $workspace" >&2
      continue
    fi
    [ "$workspace" = "$(realpath -m -- "$workspace")" ] \
      || { echo "REFUSING noncanonical build-workspace cleanup path: $workspace" >&2; continue; }
    if [ -e "$workspace" ]; then
      [ -d "$workspace" ] && [ ! -L "$workspace" ] \
        && rm -rf --one-file-system -- "$workspace"
    fi
  done
  set -e
}
early_exit() {
  local rc=$?
  trap - EXIT
  cleanup_build_workspaces
  exit "$rc"
}
trap early_exit EXIT

prepare_bundle() {  # prepare_bundle <sha> [sealed compatibility-runtime bundle]
  local sha="$1" compatibility_bundle="${2:-}" final workspace deps_workspace staging uuid repository fetched
  local runtime_lock_source gateway_lock_source provision_lock_source test_lock_source
  final=$(bundle_for_sha "$sha")
  if [ -e "$final" ]; then
    verify_sealed_bundle "$final" "$sha"
    PREPARED_BUNDLE=$final
    PREPARED_NEW=0
    say "reusing verified sealed bundle $final"
    return
  fi
  uuid=$(trusted_python -c 'import uuid; print(uuid.uuid4())')
  workspace="$BUILD_ROOT/source-$uuid"
  deps_workspace="$BUILD_ROOT/dependencies-$uuid"
  staging="$RELEASE_ROOT/.build-mcp-$sha-$uuid"
  [ ! -e "$workspace" ] && [ ! -e "$deps_workspace" ] && [ ! -e "$staging" ] \
    || fail "temporary build path already exists"
  install -d -o "$MCP_BUILDER_USER" -g "$MCP_BUILDER_GROUP" -m 0700 \
    "$workspace" "$workspace/repository" "$workspace/export"
  install -d -o root -g root -m 0755 "$deps_workspace" "$deps_workspace/locks"
  install -d -o "$MCP_DEPS_USER" -g "$MCP_DEPS_GROUP" -m 0700 \
    "$deps_workspace/runtime-download" "$deps_workspace/gateway-download" \
    "$deps_workspace/provision-download" \
    "$deps_workspace/test-download"
  install -d -o root -g root -m 0755 "$staging"
  BUILD_WORKSPACES+=("$workspace" "$deps_workspace" "$staging")
  repository=$workspace/repository
  run_isolated_actor "$MCP_BUILDER_USER" "$MCP_BUILDER_GROUP" \
    "$workspace" "$workspace" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
      GIT_NO_REPLACE_OBJECTS=1 \
      /usr/bin/git -C "$repository" init -q \
    || fail "could not initialize isolated canonical source repository"
  run_isolated_actor "$MCP_BUILDER_USER" "$MCP_BUILDER_GROUP" \
    "$workspace" "$workspace" 0 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
      GIT_NO_REPLACE_OBJECTS=1 \
      /usr/bin/git -c protocol.file.allow=never -C "$repository" fetch -q \
        --depth=1 --no-tags "$SOURCE_ORIGIN" "$sha" \
    || fail "canonical origin did not provide exact candidate SHA $sha"
  fetched=$(run_isolated_actor "$MCP_BUILDER_USER" "$MCP_BUILDER_GROUP" \
    "$workspace" "$workspace" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
      GIT_NO_REPLACE_OBJECTS=1 \
      /usr/bin/git -C "$repository" rev-parse --verify FETCH_HEAD^{commit}) \
    || fail "could not attest fetched canonical source"
  [ "$fetched" = "$sha" ] || fail "canonical source resolved $fetched, want $sha"
  # Export raw commit-tree blobs with a fixed stdlib program.  This avoids
  # archive parsers, worktree filters, hooks and candidate-controlled modes
  # other than the one executable bit.  The builder is unprivileged and has no
  # network while parsing paths and object bytes.  Root only sees the result
  # through freeze_canonical_source's ownership/type/size checks below.
  run_isolated_actor "$MCP_BUILDER_USER" "$MCP_BUILDER_GROUP" \
    "$workspace" "$workspace/export" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
      GIT_NO_REPLACE_OBJECTS=1 \
      /usr/bin/python3.13 -I -B -S - "$repository" "$workspace/export" "$sha" <<'PY' \
    || fail "could not export exact canonical source SHA as raw Git blobs"
import os
import re
import stat
import subprocess
import sys

repository = os.path.abspath(sys.argv[1])
destination = os.path.abspath(sys.argv[2])
release_sha = sys.argv[3]
if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
    raise SystemExit("release SHA is not exact lowercase SHA-1")
if os.environ.get("GIT_NO_REPLACE_OBJECTS") != "1":
    raise SystemExit("Git replacement-object protection is absent")
root_metadata = os.lstat(destination)
if (
    not stat.S_ISDIR(root_metadata.st_mode)
    or stat.S_ISLNK(root_metadata.st_mode)
    or root_metadata.st_uid != os.getuid()
    or root_metadata.st_gid != os.getgid()
    or os.listdir(destination)
):
    raise SystemExit("raw export destination is not a fresh owned directory")

git = ["/usr/bin/git", "-C", repository]
tree = subprocess.Popen(
    git + ["ls-tree", "-r", "-z", "--full-tree", release_sha],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    env=os.environ,
)
assert tree.stdout is not None
entries = []
seen = set()
pending = b""
listing_bytes = 0

def accept_record(record: bytes) -> None:
    if not record:
        raise SystemExit("empty record in canonical Git tree")
    metadata, separator, path = record.partition(b"\t")
    fields = metadata.split()
    if not separator or len(fields) != 3:
        raise SystemExit("malformed canonical Git tree record")
    mode, object_type, object_id = fields
    if mode not in (b"100644", b"100755") or object_type != b"blob":
        raise SystemExit("canonical Git tree contains a symlink, submodule, or special mode")
    if not re.fullmatch(rb"[0-9a-f]{40}", object_id):
        raise SystemExit("canonical Git tree contains a non-SHA-1 object id")
    if len(path) > 4096 or path.startswith(b"/"):
        raise SystemExit("canonical Git tree path is unsafe or too long")
    components = path.split(b"/")
    if (
        not components
        or any(
            component in (b"", b".", b"..", b".git") or len(component) > 255
            for component in components
        )
    ):
        raise SystemExit("canonical Git tree path has a forbidden component")
    if path in seen:
        raise SystemExit("canonical Git tree contains a duplicate path")
    seen.add(path)
    entries.append((path, object_id, mode))
    if len(entries) > 200_000:
        raise SystemExit("canonical Git tree has too many files")

while True:
    chunk = tree.stdout.read(1024 * 1024)
    if not chunk:
        break
    listing_bytes += len(chunk)
    if listing_bytes > 64 * 1024 * 1024:
        raise SystemExit("canonical Git tree listing is oversized")
    pending += chunk
    records = pending.split(b"\0")
    pending = records.pop()
    for record in records:
        accept_record(record)
tree.stdout.close()
if pending:
    raise SystemExit("canonical Git tree listing is not NUL terminated")
if tree.wait() != 0:
    raise SystemExit("could not enumerate the canonical Git tree")

objects = subprocess.Popen(
    git + ["cat-file", "--batch"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    env=os.environ,
)
assert objects.stdin is not None and objects.stdout is not None
total_size = 0
for raw_path, requested_id, mode in entries:
    objects.stdin.write(requested_id + b"\n")
    objects.stdin.flush()
    header = objects.stdout.readline(256)
    if not header.endswith(b"\n") or len(header) >= 256:
        raise SystemExit("malformed Git blob batch header")
    fields = header.rstrip(b"\n").split()
    if (
        len(fields) != 3
        or fields[0] != requested_id
        or fields[1] != b"blob"
        or not fields[2].isdigit()
    ):
        raise SystemExit("Git returned an unexpected raw object")
    size = int(fields[2])
    total_size += size
    if size > 1024 * 1024 * 1024 or total_size > 4 * 1024 * 1024 * 1024:
        raise SystemExit("canonical Git tree blob content is oversized")

    relative = os.fsdecode(raw_path)
    output_path = os.path.join(destination, relative)
    parent = os.path.dirname(output_path)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    current = destination
    for component in os.fsdecode(raw_path).split("/")[:-1]:
        current = os.path.join(current, component)
        metadata = os.lstat(current)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
        ):
            raise SystemExit("raw export parent directory became unsafe")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(output_path, flags, 0o700 if mode == b"100755" else 0o600)
    try:
        remaining = size
        while remaining:
            chunk = objects.stdout.read(min(1024 * 1024, remaining))
            if not chunk:
                raise SystemExit("short read from raw Git blob stream")
            view = memoryview(chunk)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise SystemExit("short write during raw Git export")
                view = view[written:]
            remaining -= len(chunk)
        if objects.stdout.read(1) != b"\n":
            raise SystemExit("raw Git blob stream lacks its record terminator")
        os.fsync(fd)
    finally:
        os.close(fd)
objects.stdin.close()
objects.stdout.close()
if objects.wait() != 0:
    raise SystemExit("raw Git object exporter did not exit cleanly")
PY
  assert_exact_uid_processes "$MCP_BUILDER_USER" \
    || fail "source builder retained a process after canonical export"
  freeze_canonical_source "$workspace/export" "$staging/src"

  runtime_lock_source=$deps_workspace/locks/runtime.lock
  gateway_lock_source=$deps_workspace/locks/gateway.lock
  provision_lock_source=$deps_workspace/locks/provision.lock
  test_lock_source=$deps_workspace/locks/test.lock
  if [ -n "$compatibility_bundle" ]; then
    [[ "$compatibility_bundle" =~ ^${RELEASE_ROOT}/mcp-[0-9a-f]{40}$ ]] \
      || fail "compatibility runtime source is not an exact release bundle"
    verify_sealed_bundle "$compatibility_bundle" "${compatibility_bundle##*/mcp-}"
    install -o root -g root -m 0444 "$compatibility_bundle/artifacts/runtime.lock" \
      "$runtime_lock_source"
    install -o root -g root -m 0444 "$compatibility_bundle/artifacts/gateway.lock" \
      "$gateway_lock_source"
    install -o root -g root -m 0444 "$compatibility_bundle/artifacts/test.lock" \
      "$test_lock_source"
  else
    [ -r "$staging/src/requirements-mcp.lock" ] \
      && [ -r "$staging/src/requirements-gateway.lock" ] \
      && [ -r "$staging/src/requirements-mcp-test.lock" ] \
      || fail "canonical candidate lacks the three hashed release dependency locks"
    install -o root -g root -m 0444 "$staging/src/requirements-mcp.lock" \
      "$runtime_lock_source"
    install -o root -g root -m 0444 "$staging/src/requirements-mcp-test.lock" \
      "$test_lock_source"
    install -o root -g root -m 0444 "$staging/src/requirements-gateway.lock" \
      "$gateway_lock_source"
  fi
  install -o root -g root -m 0444 "$TRUSTED_PROVISION_LOCK" "$provision_lock_source"
  chmod 0555 "$deps_workspace/locks"

  # The fixed stdlib-only grammar gate examines root-owned handoff bytes before
  # the first network-capable dependency actor receives any execution time.
  trusted_python "$TRUSTED_WHEEL_HELPER" validate-lock --lock "$runtime_lock_source" >/dev/null \
    || fail "candidate runtime dependency lock failed fixed grammar validation"
  trusted_python "$TRUSTED_WHEEL_HELPER" validate-lock --lock "$provision_lock_source" >/dev/null \
    || fail "fixed provision dependency lock failed fixed grammar validation"
  trusted_python "$TRUSTED_WHEEL_HELPER" validate-lock --lock "$gateway_lock_source" >/dev/null \
    || fail "candidate gateway dependency lock failed fixed grammar validation"
  trusted_python "$TRUSTED_WHEEL_HELPER" validate-lock --lock "$test_lock_source" >/dev/null \
    || fail "candidate test dependency lock failed fixed grammar validation"

  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" \
    / "$deps_workspace/runtime-download" 0 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip download --no-deps --require-hashes \
        --only-binary=:all: --dest "$deps_workspace/runtime-download" \
        -r "$runtime_lock_source" \
    || fail "could not download the exact runtime wheel set"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" \
    / "$deps_workspace/gateway-download" 0 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip download --no-deps --require-hashes \
        --only-binary=:all: --dest "$deps_workspace/gateway-download" \
        -r "$gateway_lock_source" \
    || fail "could not download the exact gateway wheel set"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" \
    / "$deps_workspace/provision-download" 0 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip download --no-deps --require-hashes \
        --only-binary=:all: --dest "$deps_workspace/provision-download" \
        -r "$provision_lock_source" \
    || fail "could not download the fixed provision wheel set"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" \
    / "$deps_workspace/test-download" 0 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip download --no-deps --require-hashes \
        --only-binary=:all: --dest "$deps_workspace/test-download" \
        -r "$test_lock_source" \
    || fail "could not download the exact test wheel set"
  assert_exact_uid_processes "$MCP_DEPS_USER" \
    || fail "dependency downloader retained a process after wheel fetch"

  PREPARED_SOURCE_WORKSPACE=$workspace
  PREPARED_RUNTIME_DOWNLOAD=$deps_workspace/runtime-download
  PREPARED_GATEWAY_DOWNLOAD=$deps_workspace/gateway-download
  PREPARED_PROVISION_DOWNLOAD=$deps_workspace/provision-download
  PREPARED_TEST_DOWNLOAD=$deps_workspace/test-download
  PREPARED_RUNTIME_LOCK_SOURCE=$runtime_lock_source
  PREPARED_GATEWAY_LOCK_SOURCE=$gateway_lock_source
  PREPARED_TEST_LOCK_SOURCE=$test_lock_source
  PREPARED_BUNDLE=$staging
  PREPARED_NEW=1
}

publish_prepared_bundle() {  # publish_prepared_bundle <sha>
  local sha="$1" final staging content_sha
  local runtime_lock_sha runtime_wheel_sha runtime_manifest_sha runtime_tree_sha
  local gateway_lock_sha gateway_wheel_sha gateway_manifest_sha gateway_tree_sha
  local provision_lock_sha provision_wheel_sha provision_manifest_sha provision_tree_sha
  if [ "$PREPARED_NEW" = 0 ]; then return; fi
  staging=$PREPARED_BUNDLE
  final=$(bundle_for_sha "$sha")
  [ ! -e "$final" ] || fail "refusing to replace existing bundle: $final"
  freeze_bundle_tree "$staging"
  runtime_lock_sha=$(sha256_file "$staging/artifacts/runtime.lock")
  runtime_wheel_sha=$(json_inventory_value "$staging/artifacts/runtime-wheels.json" wheel_manifest_sha256)
  runtime_manifest_sha=$(json_inventory_value "$staging/artifacts/runtime-installed.json" installed_manifest_sha256)
  runtime_tree_sha=$(json_inventory_value "$staging/artifacts/runtime-installed.json" installed_tree_sha256)
  gateway_lock_sha=$(sha256_file "$staging/artifacts/gateway.lock")
  gateway_wheel_sha=$(json_inventory_value "$staging/artifacts/gateway-wheels.json" wheel_manifest_sha256)
  gateway_manifest_sha=$(json_inventory_value "$staging/artifacts/gateway-installed.json" installed_manifest_sha256)
  gateway_tree_sha=$(json_inventory_value "$staging/artifacts/gateway-installed.json" installed_tree_sha256)
  provision_lock_sha=$(sha256_file "$staging/artifacts/provision.lock")
  provision_wheel_sha=$(json_inventory_value "$staging/artifacts/provision-wheels.json" wheel_manifest_sha256)
  provision_manifest_sha=$(key_value_inventory_value "$staging/artifacts/provision-bootstrap.txt" provision_manifest_sha256)
  provision_tree_sha=$(key_value_inventory_value "$staging/artifacts/provision-bootstrap.txt" provision_tree_sha256)
  content_sha=$(bundle_content_sha256 "$staging")
  printf 'release_sha=%s\nbundle_content_sha256=%s\nruntime_lock_sha256=%s\nruntime_wheel_manifest_sha256=%s\nruntime_manifest_sha256=%s\nruntime_tree_sha256=%s\ngateway_lock_sha256=%s\ngateway_wheel_manifest_sha256=%s\ngateway_manifest_sha256=%s\ngateway_tree_sha256=%s\nprovision_lock_sha256=%s\nprovision_wheel_manifest_sha256=%s\nprovision_manifest_sha256=%s\nprovision_tree_sha256=%s\n' \
    "$sha" "$content_sha" "$runtime_lock_sha" "$runtime_wheel_sha" \
    "$runtime_manifest_sha" "$runtime_tree_sha" "$gateway_lock_sha" \
    "$gateway_wheel_sha" "$gateway_manifest_sha" "$gateway_tree_sha" "$provision_lock_sha" \
    "$provision_wheel_sha" "$provision_manifest_sha" "$provision_tree_sha" \
    > "$staging/.sealed"
  chown root:root "$staging/.sealed"
  chmod 0444 "$staging/.sealed"
  mv "$staging" "$final"
  PREPARED_BUNDLE=$final
  PREPARED_NEW=0
  if ! (verify_sealed_bundle "$final" "$sha"); then
    echo "FAIL: discarding bundle that failed its post-move seal verification" >&2
    case "$final" in "$RELEASE_ROOT"/mcp-*) rm -rf -- "$final" ;; esac
    fail "published bundle did not verify: $final"
  fi
  BUILD_WORKSPACES=()
}

stage_bundle_artifacts() {  # <prepared-bundle> [candidate|legacy]
  local bundle="$1" suite_kind="${2:-candidate}" runtime_site gateway_site provision_site test_site
  local runtime_lock gateway_lock provision_lock test_lock test_venv test_wheels
  [ "$PREPARED_NEW" = 1 ] || return 0
  [ "$bundle" = "$PREPARED_BUNDLE" ] || fail "artifact staging bundle mismatch"
  [ "$suite_kind" = candidate ] || [ "$suite_kind" = legacy ] \
    || fail "invalid release test-suite kind"
  install -d -o root -g root -m 0755 "$bundle/artifacts" "$bundle/wheelhouse"
  install -o root -g root -m 0444 "$PREPARED_RUNTIME_LOCK_SOURCE" \
    "$bundle/artifacts/runtime.lock"
  install -o root -g root -m 0444 "$PREPARED_GATEWAY_LOCK_SOURCE" \
    "$bundle/artifacts/gateway.lock"
  install -o root -g root -m 0444 "$TRUSTED_PROVISION_LOCK" \
    "$bundle/artifacts/provision.lock"
  install -o root -g root -m 0444 "$PREPARED_TEST_LOCK_SOURCE" \
    "$bundle/artifacts/test.lock"
  install -o root -g root -m 0555 "$TRUSTED_PROVISION_BOOTSTRAP" \
    "$bundle/artifacts/mcp-provision-bootstrap.py"
  install -o root -g root -m 0555 "$TRUSTED_PROVISIONER" \
    "$bundle/artifacts/provision-mcp-key.py"
  runtime_lock=$bundle/artifacts/runtime.lock
  gateway_lock=$bundle/artifacts/gateway.lock
  provision_lock=$bundle/artifacts/provision.lock
  test_lock=$bundle/artifacts/test.lock

  trusted_python "$TRUSTED_WHEEL_HELPER" stage --lock "$runtime_lock" \
    --source "$PREPARED_RUNTIME_DOWNLOAD" --destination "$bundle/wheelhouse/runtime" \
    --python-version 3.13 --architecture x86_64 --glibc 2.39 \
    > "$bundle/artifacts/runtime-wheels.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" stage --lock "$provision_lock" \
    --source "$PREPARED_PROVISION_DOWNLOAD" --destination "$bundle/wheelhouse/provision" \
    --python-version 3.13 --architecture x86_64 --glibc 2.39 \
    > "$bundle/artifacts/provision-wheels.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" stage --lock "$gateway_lock" \
    --source "$PREPARED_GATEWAY_DOWNLOAD" --destination "$bundle/wheelhouse/gateway" \
    --python-version 3.13 --architecture x86_64 --glibc 2.39 \
    > "$bundle/artifacts/gateway-wheels.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" stage --lock "$test_lock" \
    --source "$PREPARED_TEST_DOWNLOAD" --destination "$bundle/wheelhouse/test" \
    --python-version 3.13 --architecture x86_64 --glibc 2.39 \
    > "$bundle/artifacts/test-wheels.json"
  chmod 0444 "$bundle/artifacts/"*-wheels.json

  create_minimal_venv "$bundle/venv" "$MCP_DEPS_USER"
  create_minimal_venv "$bundle/gateway-venv" "$MCP_DEPS_USER"
  create_minimal_venv "$bundle/provision-venv" "$MCP_DEPS_USER"
  create_minimal_venv "$bundle/test-venv" "$MCP_DEPS_USER"
  runtime_site=$bundle/venv/lib/python3.13/site-packages
  gateway_site=$bundle/gateway-venv/lib/python3.13/site-packages
  provision_site=$bundle/provision-venv/lib/python3.13/site-packages
  test_site=$bundle/test-venv/lib/python3.13/site-packages

  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" / "$runtime_site" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip install --no-index --no-deps --no-compile \
        --require-hashes --only-binary=:all: --target "$runtime_site" \
        --find-links "$bundle/wheelhouse/runtime" -r "$runtime_lock" \
    || fail "offline runtime dependency installation failed"
  freeze_dependency_target "$runtime_site" "$MCP_DEPS_USER"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" / "$gateway_site" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip install --no-index --no-deps --no-compile \
        --require-hashes --only-binary=:all: --target "$gateway_site" \
        --find-links "$bundle/wheelhouse/gateway" -r "$gateway_lock" \
    || fail "offline gateway dependency installation failed"
  freeze_dependency_target "$gateway_site" "$MCP_DEPS_USER"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" / "$provision_site" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip install --no-index --no-deps --no-compile \
        --require-hashes --only-binary=:all: --target "$provision_site" \
        --find-links "$bundle/wheelhouse/provision" -r "$provision_lock" \
    || fail "offline provision dependency installation failed"
  freeze_dependency_target "$provision_site" "$MCP_DEPS_USER"
  run_isolated_actor "$MCP_DEPS_USER" "$MCP_DEPS_GROUP" / "$test_site" 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
      /usr/bin/python3.13 -I -B -m pip install --no-index --no-deps --no-compile \
        --require-hashes --only-binary=:all: --target "$test_site" \
        --find-links "$bundle/wheelhouse/test" -r "$test_lock" \
    || fail "offline test dependency installation failed"
  freeze_dependency_target "$test_site" "$MCP_DEPS_USER"
  assert_exact_uid_processes "$MCP_DEPS_USER" \
    || fail "dependency installer retained a process after offline installs"

  trusted_python "$TRUSTED_WHEEL_HELPER" verify-install --lock "$runtime_lock" \
    --wheelhouse "$bundle/wheelhouse/runtime" --site-packages "$runtime_site" \
    > "$bundle/artifacts/runtime-installed.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" verify-install --lock "$provision_lock" \
    --wheelhouse "$bundle/wheelhouse/provision" --site-packages "$provision_site" \
    > "$bundle/artifacts/provision-installed.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" verify-install --lock "$gateway_lock" \
    --wheelhouse "$bundle/wheelhouse/gateway" --site-packages "$gateway_site" \
    > "$bundle/artifacts/gateway-installed.json"
  trusted_python "$TRUSTED_WHEEL_HELPER" verify-install --lock "$test_lock" \
    --wheelhouse "$bundle/wheelhouse/test" --site-packages "$test_site" \
    > "$bundle/artifacts/test-installed.json"
  chmod 0444 "$bundle/artifacts/"*-installed.json

  if [ "$suite_kind" = candidate ]; then
    echo "==> run candidate MCP tests as the dedicated network-isolated test identity"
    run_isolated_actor "$MCP_TEST_USER" "$MCP_TEST_GROUP" / /tmp 1 -- \
      /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        "$bundle/test-venv/bin/python" -I -B -c \
        'import runpy,sys; source=sys.argv.pop(1); sys.path.insert(0,source); sys.argv[0]="pytest"; runpy.run_module("pytest",run_name="__main__")' \
        "$bundle/src" -q -p no:cacheprovider --import-mode=importlib \
        "$bundle/src/tests/test_mcpserver.py" \
        "$bundle/src/tests/test_mcp_discovery_contract.py" \
        "$bundle/src/tests/test_provision_mcp_key.py" \
        "$bundle/src/tests/test_consistency.py" \
        "$bundle/src/ops/tests/test_mcp_contract_runtime.py" \
        "$bundle/src/ops/tests/test_mcp_service_env.py" \
        "$bundle/src/ops/tests/test_verify_mcp_discovery.py" \
        "$bundle/src/ops/tests/test_verify_mcp_protocol.py" \
        "$bundle/src/ops/tests/test_verify_mcp_load.py" \
      || fail "network-isolated candidate MCP test suite failed"
    echo "==> run candidate gateway tests from exact sealed gateway + test dependencies"
    run_isolated_actor "$MCP_TEST_USER" "$MCP_TEST_GROUP" / /tmp 1 -- \
      /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
        /usr/bin/python3.13 -I -B -c \
        'import importlib,os,runpy,sys; gateway,test,source=sys.argv[1:4]; sys.path[:0]=[gateway,test,source];
for name,root in [("flask",gateway),("psycopg2",gateway),("redis",gateway),("requests",gateway),("gunicorn",gateway),("pytest",test)]:
 module=importlib.import_module(name); path=os.path.realpath(module.__file__); expected=os.path.realpath(root); assert os.path.commonpath([path,expected])==expected,(name,path,expected)
sys.argv=["pytest",*sys.argv[4:]]; runpy.run_module("pytest",run_name="__main__")' \
        "$gateway_site" "$test_site" "$bundle/src" \
        -q -p no:cacheprovider --import-mode=importlib \
        "$bundle/src/tests/test_apiserver_endpoints.py" \
        "$bundle/src/tests/test_cards.py" \
        "$bundle/src/tests/test_ml_quota.py" \
        "$bundle/src/tests/test_consistency.py" \
        "$bundle/src/tests/test_mcp_discovery_contract.py" \
      || fail "network-isolated sealed gateway test suite failed"
  else
    say "legacy rollback source uses the reviewed fixed SHA; applying only the absolute-entrypoint runtime smoke"
  fi
  run_isolated_actor "$MCP_TEST_USER" "$MCP_TEST_GROUP" / /tmp 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      "$bundle/venv/bin/python" -I -B -u "$bundle/src/mcpserver/server.py" --help \
    || fail "candidate runtime cannot execute the absolute MCP server entrypoint"
  run_isolated_actor "$MCP_TEST_USER" "$MCP_TEST_GROUP" / /tmp 1 -- \
    /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      "$bundle/gateway-venv/bin/python" -I -B -m gunicorn --version \
    || fail "candidate gateway runtime cannot execute its sealed Gunicorn entrypoint"
  assert_exact_uid_processes "$MCP_TEST_USER" \
    || fail "candidate test identity retained a process"

  test_venv=$bundle/test-venv
  test_wheels=$bundle/wheelhouse/test
  [ ! -L "$test_venv" ] && [ ! -L "$test_wheels" ] \
    || fail "refusing to remove a symlinked test dependency tree"
  rm -rf --one-file-system -- "$test_venv" "$test_wheels"
  rm -f -- "$bundle/artifacts/test-wheels.json" "$bundle/artifacts/test-installed.json"
  trusted_python "$bundle/artifacts/mcp-provision-bootstrap.py" inventory \
    --bundle "$bundle" --lock "$provision_lock" \
    > "$bundle/artifacts/provision-bootstrap.txt"
  chmod 0444 "$bundle/artifacts/provision-bootstrap.txt"
}

public_url() {
  trusted_python "$TRUSTED_ENV_HELPER" source-value \
    --source "$SECRETS" --name public-url
}

public_url_host() {  # public_url_host <canonical-public-url>
  trusted_python - "$1" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
try:
    parsed = urlsplit(value)
    port = parsed.port
except ValueError as exc:
    raise SystemExit(f"invalid TW2_MCP_PUBLIC_URL: {exc}")
if (
    parsed.scheme.lower() != "https"
    or not parsed.hostname
    or parsed.username is not None
    or parsed.password is not None
    or port not in (None, 443)
    or parsed.path not in ("", "/")
    or parsed.query
    or parsed.fragment
):
    raise SystemExit("TW2_MCP_PUBLIC_URL must be a canonical HTTPS origin")
print(parsed.hostname.encode("idna").decode("ascii").lower())
PY
}

resolved_portal_hosts() {  # emits API_HOST, MCP_HOST, DEV_HOST on separate lines
  trusted_python "$TRUSTED_ENV_HELPER" resolve-portal-hosts --source "$SECRETS"
}

authorization_server() {
  trusted_python "$TRUSTED_ENV_HELPER" source-value \
    --source "$SECRETS" --name authorization-server
}

install_mcp_runtime_env() {  # install_mcp_runtime_env <resolved-public-host>
  local public_host="$1" rendered staged metadata
  rendered="$TX_SCRATCH/mcpserver.env-candidate"
  staged="${MCP_ENV}.tmp.$$"
  rm -f "$rendered" "$staged"
  trusted_python "$TRUSTED_ENV_HELPER" render \
    --source "$SECRETS" --dedicated "$MCP_ENV" --output "$rendered" \
    --resolved-public-host "$public_host"
  trusted_python "$TRUSTED_ENV_HELPER" validate --path "$rendered"
  install -d -o root -g root -m 0755 "$(dirname "$MCP_ENV")"
  # PID 1 reads EnvironmentFile before dropping privileges; the MCP account
  # never needs filesystem access to this credential-bearing file.
  install -o root -g root -m 0600 "$rendered" "$staged"
  mv -fT "$staged" "$MCP_ENV"
  metadata=$(stat -c '%U:%G %a' "$MCP_ENV")
  [ "$metadata" = "root:root 600" ] \
    || fail "$MCP_ENV ownership/mode is $metadata, want root:root 600"
  trusted_python "$TRUSTED_ENV_HELPER" validate --path "$MCP_ENV"
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?TRADEWAVE_API_KEY[[:space:]]*=' "$MCP_ENV"; then
    fail "$MCP_ENV must never contain TRADEWAVE_API_KEY"
  fi
}

prepare_mcp_canary_env() {
  # Production-port canaries consume the byte-identical persistent environment.
  # This removes an entire class of precommit-vs-stable configuration drift.
  MCP_CANARY_ENV=$MCP_ENV
  trusted_python "$TRUSTED_ENV_HELPER" validate --path "$MCP_CANARY_ENV"
  [ "$(runtime_env_value API_BASE_URL)" = "http://127.0.0.1:$API_CANARY_PORT/v1" ] \
    && [ "$(runtime_env_value TW2_MCP_HOST)" = 127.0.0.1 ] \
    && [ "$(runtime_env_value TW2_MCP_PORT)" = "$MCP_CANARY_PORT" ] \
    && [ "$(runtime_env_value TW2_MCP_TRANSPORT)" = streamable-http ] \
    || fail "persistent MCP environment is not production-canary equivalent"
}

check_mcp_gateway_key() {
  trusted_python "$TRUSTED_ENV_HELPER" check-gateway-key \
    --path "$MCP_ENV" --source "$SECRETS"
}

check_release_service_key() {
  run_release_provisioner "$CANDIDATE_BUNDLE" --check-service
}

run_release_provisioner() {  # <sealed-bundle> [fixed provisioner action]
  local bundle="$1"
  shift
  verify_sealed_bundle "$bundle" "${bundle##*/mcp-}"
  env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TW_MCP_RELEASE_LOCK_FD=9 \
    /usr/bin/python3.13 -I -B -S \
    "$bundle/artifacts/mcp-provision-bootstrap.py" run \
    --bundle "$bundle" --lock "$bundle/artifacts/provision.lock" \
    --provisioner "$bundle/artifacts/provision-mcp-key.py" -- "$@"
}

provision_release_credentials() {
  run_release_provisioner "$CANDIDATE_BUNDLE" --check-runtime-dependencies
  run_release_provisioner "$CANDIDATE_BUNDLE"
  check_release_service_key
}

purge_stale_verifier_probes() {  # [sealed bundle]
  run_release_provisioner "${1:-$CANDIDATE_BUNDLE}" --purge-stale-verifier-probes
}

mint_verifier_probe() {
  [ -n "$TXID" ] && [ -r "$TX_ACTIVE/manifest.json" ] \
    || fail "verifier probe requires the durable active journal"
  VERIFIER_STATE="$VERIFIER_STATE_ROOT/$TXID.json"
  VERIFIER_CREDENTIAL="$VERIFIER_CREDENTIAL_ROOT/$TXID/verify-env"
  run_release_provisioner "$CANDIDATE_BUNDLE" --mint-verifier-probe \
    --transaction-id "$TXID" --journal-manifest "$TX_ACTIVE/manifest.json" \
    --state-path "$VERIFIER_STATE" --credential-path "$VERIFIER_CREDENTIAL"
  [ -f "$VERIFIER_STATE" ] && [ ! -L "$VERIFIER_STATE" ] \
    && [ "$(stat -c '%U:%G %a %h' "$VERIFIER_STATE")" = "root:root 600 1" ] \
    && [ -f "$VERIFIER_CREDENTIAL" ] && [ ! -L "$VERIFIER_CREDENTIAL" ] \
    && [ "$(stat -c '%U:%G %a %h' "$VERIFIER_CREDENTIAL")" = "root:root 600 1" ] \
    || fail "sacrificial verifier probe files are not exact"
  VERIFIER_PROBE_ACTIVE=1
}

unlink_materialized_verifier_source() {
  trusted_python - "$VERIFIER_CREDENTIAL" "$VERIFIER_CREDENTIAL_ROOT" "$TXID" <<'PY'
import os
import stat
import sys

path, root, txid = sys.argv[1:]
expected = os.path.join(root, txid, "verify-env")
if path != expected:
    raise SystemExit("verifier credential source path is not transaction-bound")
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0 or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1
):
    raise SystemExit("verifier credential source metadata is unsafe")
os.unlink(path)
directory = os.path.dirname(path)
fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
if os.listdir(directory):
    raise SystemExit("verifier credential transaction directory is not empty")
os.rmdir(directory)
fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

revoke_verifier_probe() {
  [ "$VERIFIER_PROBE_ACTIVE" = 1 ] || return 0
  run_release_provisioner "$CANDIDATE_BUNDLE" --revoke-verifier-probe \
    --transaction-id "$TXID" --state-path "$VERIFIER_STATE" \
    --credential-path "$VERIFIER_CREDENTIAL"
  VERIFIER_PROBE_ACTIVE=0
  VERIFIER_STATE=""
  VERIFIER_CREDENTIAL=""
}

revoke_verifier_probe_best_effort() {
  if [ "$VERIFIER_PROBE_ACTIVE" = 1 ]; then
    revoke_verifier_probe >/dev/null 2>&1 || true
  fi
}

finalize_mcp_key_rotation() {  # [activated-pid]
  local pid="${1:-}"
  if [ -z "$pid" ]; then
    pid=$(systemctl show tradewave-mcpserver --property=MainPID --value)
  fi
  if [ -z "$pid" ] || [ "$pid" -lt 2 ]; then
    fail "cannot identify activated MCP PID for service-key finalization"
  fi
  run_release_provisioner "$CANDIDATE_BUNDLE" --finalize --pid "$pid"
}

abort_mcp_key_rotation() {  # [sealed candidate bundle]
  run_release_provisioner "${1:-$CANDIDATE_BUNDLE}" --abort
}

stop_transient_verifier_best_effort() {
  if [ -n "$VERIFIER_UNIT" ]; then
    systemctl stop "$VERIFIER_UNIT" >/dev/null 2>&1 || true
    systemctl reset-failed "$VERIFIER_UNIT" >/dev/null 2>&1 || true
  fi
  if [ -n "$VERIFIER_RUNNER_PID" ]; then
    wait "$VERIFIER_RUNNER_PID" >/dev/null 2>&1 || true
  fi
  VERIFIER_UNIT=""
  VERIFIER_RUNNER_PID=""
}

assert_exact_uid_processes() {  # <account> [expected-pid]
  local uid expected="${2:-}"
  uid=$(id -u "$1") || return 1
  trusted_python - "$uid" "$expected" <<'PY'
import pathlib
import sys

uid = int(sys.argv[1])
expected = {int(sys.argv[2])} if sys.argv[2] else set()
actual = set()
for status in pathlib.Path("/proc").glob("[0-9]*/status"):
    try:
        lines = status.read_text(encoding="ascii").splitlines()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        continue
    for line in lines:
        if line.startswith("Uid:"):
            values = {int(value) for value in line.split()[1:]}
            if uid in values:
                actual.add(int(status.parent.name))
            break
if actual != expected:
    raise SystemExit(f"uid {uid} process set mismatch: expected={sorted(expected)} actual={sorted(actual)}")
PY
}

assert_no_uid_environment_name() {  # <account> <environment-name>
  local uid
  uid=$(id -u "$1") || return 1
  trusted_python - "$uid" "$2" <<'PY'
import os
import pathlib
import re
import sys

uid = int(sys.argv[1])
name = sys.argv[2]
if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
    raise SystemExit("invalid environment-name assertion")
holders = []
for process in pathlib.Path("/proc").glob("[0-9]*"):
    try:
        status = (process / "status").read_text(encoding="ascii").splitlines()
        uid_line = next(line for line in status if line.startswith("Uid:"))
        process_uids = {int(value) for value in uid_line.split()[1:]}
        if uid not in process_uids:
            continue
        environment = (process / "environ").read_bytes().split(b"\0")
    except (FileNotFoundError, ProcessLookupError):
        continue
    except PermissionError as exc:
        raise SystemExit(f"cannot inspect uid {uid} process environment: {process.name}") from exc
    prefix = name.encode("ascii") + b"="
    if any(entry.startswith(prefix) for entry in environment):
        holders.append(int(process.name))
if holders:
    raise SystemExit(
        f"uid {uid} still has {name} in process environments: {sorted(holders)}"
    )
PY
}

scrub_legacy_flask_mcp_secret() {
  # The old broad EnvironmentFile was inherited by every flask-owned service,
  # even though only legacy MCP used K0. Restart the three fixed platform units
  # after the assignment is removed, then prove no flask process retains it.
  systemctl stop tradewave-apiserver.service
  systemctl restart tradewave-appserver.service tradewave-web.service
  ! systemctl is-active --quiet tradewave-apiserver.service \
    && systemctl is-active --quiet tradewave-appserver.service \
    && systemctl is-active --quiet tradewave-web.service \
    || fail "legacy gateway/app platform processes did not establish the K0-free boundary"
  assert_no_uid_environment_name flask MCP_GATEWAY_KEY \
    || fail "a flask-owned process retained the removed broad MCP_GATEWAY_KEY"
  say "legacy API gateway was stopped and remaining flask processes restarted without K0"
}

assert_flask_platform_services_active() {
  systemctl is-active --quiet tradewave-apiserver.service \
    && systemctl is-active --quiet tradewave-appserver.service \
    && systemctl is-active --quiet tradewave-web.service
}

restore_legacy_flask_support_services() {
  # A failed first migration may have restarted only a subset of the flask
  # services after removing K0 from the broad file. The journal has restored
  # the exact broad bytes at this point, so restart only the unfenced support
  # services. The API gateway remains stopped until recovery.json is durable;
  # the stable start guard correctly refuses it while the journal is active.
  systemctl restart tradewave-appserver.service tradewave-web.service
  ! systemctl is-active --quiet tradewave-apiserver.service \
    && systemctl is-active --quiet tradewave-appserver.service \
    && systemctl is-active --quiet tradewave-web.service \
    || { echo "legacy flask support services did not recover behind the active fence" >&2; return 1; }
}

run_isolated_actor() {  # <user> <group> <workdir> <rw-path> <private-network:0|1> -- <argv...>
  local account="$1" group="$2" workdir="$3" writable="$4" private_network="$5"
  local unit rc
  shift 5
  [ "${1:-}" = -- ] || fail "internal isolated actor call is malformed"
  shift
  [ "$#" -gt 0 ] || fail "isolated actor command is empty"
  assert_exact_uid_processes "$account" \
    || fail "$account already has a live process before isolated work"
  unit="tradewave-mcp-work-$(trusted_python -c 'import uuid; print(uuid.uuid4())').service"
  local -a network_property=(--property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6")
  if [ "$private_network" = 1 ]; then
    network_property=(--property=PrivateNetwork=yes --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6")
  elif [ "$private_network" != 0 ]; then
    fail "invalid isolated actor network policy"
  fi
  set +e
  /usr/bin/systemd-run --quiet --wait --pipe --collect --service-type=exec \
    --unit="$unit" --description="TradeWave MCP isolated release worker" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$DEPLOY_UNIT" --property="User=$account" \
    --property="Group=$group" --property="SupplementaryGroups=" \
    --property="WorkingDirectory=$workdir" --property="ReadWritePaths=$writable" \
    --property="InaccessiblePaths=-/etc/tradewave -/home/flask" \
    --setenv=PATH=/usr/bin:/bin --setenv=HOME=/nonexistent \
    --setenv=LANG=C.UTF-8 --setenv=LC_ALL=C.UTF-8 \
    --property="UnsetEnvironment=BASH_ENV ENV CDPATH GLOBIGNORE HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK PYTHONUNBUFFERED PYTHONDONTWRITEBYTECODE GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG_COUNT GIT_SSH GIT_SSH_COMMAND GIT_ASKPASS SSH_ASKPASS" \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
    --property=ProtectHome=read-only --property=PrivateTmp=yes \
    --property=PrivateDevices=yes --property=ProtectHostname=yes \
    --property=ProtectClock=yes --property=ProtectKernelTunables=yes \
    --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
    --property=ProtectKernelLogs=yes --property=ProtectProc=invisible \
    --property=ProcSubset=pid --property=RestrictSUIDSGID=yes \
    --property=RestrictNamespaces=yes --property=LockPersonality=yes \
    --property=SystemCallArchitectures=native \
    "${network_property[@]}" \
    --property=CapabilityBoundingSet= --property=AmbientCapabilities= \
    --property=UMask=0077 --property=LimitCORE=0 --property=TasksMax=512 \
    --property=MemoryHigh=2G --property=MemoryMax=3G \
    --property=Restart=no --property=KillMode=control-group \
    --property=RuntimeMaxSec=15min --property=TimeoutStopSec=15s "$@"
  rc=$?
  set -e
  assert_exact_uid_processes "$account" \
    || fail "$account retained a process after isolated unit collection"
  [ "$rc" -eq 0 ] || return "$rc"
}

freeze_canonical_source() {  # <builder-export> <root-destination>
  local builder_uid builder_gid
  builder_uid=$(id -u "$MCP_BUILDER_USER")
  builder_gid=$(getent group "$MCP_BUILDER_GROUP" | awk -F: '{print $3}')
  trusted_python - "$1" "$2" "$builder_uid" "$builder_gid" <<'PY'
import hashlib
import os
import stat
import sys

source = os.path.abspath(sys.argv[1])
destination = os.path.abspath(sys.argv[2])
builder_uid = int(sys.argv[3])
builder_gid = int(sys.argv[4])
if source == destination or os.path.lexists(destination):
    raise SystemExit("unsafe canonical source freeze destination")
parent = os.path.dirname(destination)
parent_metadata = os.lstat(parent)
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or stat.S_ISLNK(parent_metadata.st_mode)
    or parent_metadata.st_uid != 0
    or parent_metadata.st_gid != 0
    or stat.S_IMODE(parent_metadata.st_mode) & 0o022
):
    raise SystemExit("canonical source destination parent is unsafe")

entries = 0
total_size = 0

def copy_directory(src: str, dst: str, relative: str) -> None:
    global entries, total_size
    metadata = os.lstat(src)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != builder_uid
        or metadata.st_gid != builder_gid
    ):
        raise SystemExit(f"unsafe builder source directory: {relative or '.'}")
    os.mkdir(dst, 0o755)
    os.chown(dst, 0, 0)
    with os.scandir(src) as iterator:
        children = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
    for child in children:
        if child.name == ".git" or "/.git/" in f"/{relative}/{child.name}/":
            raise SystemExit("canonical source export contains forbidden Git metadata")
        entries += 1
        if entries > 200_000:
            raise SystemExit("canonical source export has too many entries")
        child_relative = child.name if not relative else f"{relative}/{child.name}"
        child_src = os.path.join(src, child.name)
        child_dst = os.path.join(dst, child.name)
        child_metadata = os.lstat(child_src)
        if child_metadata.st_uid != builder_uid or child_metadata.st_gid != builder_gid:
            raise SystemExit(f"builder source ownership mismatch: {child_relative}")
        if stat.S_ISDIR(child_metadata.st_mode) and not stat.S_ISLNK(child_metadata.st_mode):
            copy_directory(child_src, child_dst, child_relative)
            continue
        if not stat.S_ISREG(child_metadata.st_mode) or child_metadata.st_nlink != 1:
            raise SystemExit(f"builder source contains symlink/special/hardlink: {child_relative}")
        total_size += child_metadata.st_size
        if total_size > 4 * 1024 * 1024 * 1024:
            raise SystemExit("canonical source export is oversized")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        source_fd = os.open(child_src, flags)
        destination_fd = os.open(
            child_dst,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (child_metadata.st_dev, child_metadata.st_ino)
            ):
                raise SystemExit(f"builder source changed during freeze: {child_relative}")
            remaining = opened.st_size
            while remaining:
                chunk = os.read(source_fd, min(1024 * 1024, remaining))
                if not chunk:
                    raise SystemExit(f"short builder source read: {child_relative}")
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    view = view[written:]
                remaining -= len(chunk)
            if os.read(source_fd, 1):
                raise SystemExit(f"builder source grew during freeze: {child_relative}")
            mode = 0o555 if stat.S_IMODE(opened.st_mode) & 0o111 else 0o444
            os.fchmod(destination_fd, mode)
            os.fchown(destination_fd, 0, 0)
            os.fsync(destination_fd)
        finally:
            os.close(source_fd)
            os.close(destination_fd)
    os.chmod(dst, 0o555)
    directory_fd = os.open(dst, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

copy_directory(source, destination, "")
parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(parent_fd)
finally:
    os.close(parent_fd)
PY
}

freeze_dependency_target() {  # <target-root> <dependency-user>
  local uid gid
  uid=$(id -u "$2")
  gid=$(id -g "$2")
  trusted_python - "$1" "$uid" "$gid" <<'PY'
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
uid = int(sys.argv[2])
gid = int(sys.argv[3])
entries = []
for current, directories, files in os.walk(root, topdown=True, followlinks=False):
    directories.sort(key=os.fsencode)
    files.sort(key=os.fsencode)
    for name in directories + files:
        path = os.path.join(current, name)
        relative = os.path.relpath(path, root)
        metadata = os.lstat(path)
        if metadata.st_uid != uid or metadata.st_gid != gid:
            raise SystemExit(f"dependency target ownership mismatch: {relative}")
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(f"dependency target contains a symlink: {relative}")
        if stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise SystemExit(f"dependency target contains a hardlink: {relative}")
        elif not stat.S_ISDIR(metadata.st_mode):
            raise SystemExit(f"dependency target contains a special file: {relative}")
        entries.append((path, metadata))
        if len(entries) > 250_000:
            raise SystemExit("dependency target has too many entries")
root_metadata = os.lstat(root)
if (
    not stat.S_ISDIR(root_metadata.st_mode)
    or stat.S_ISLNK(root_metadata.st_mode)
    or root_metadata.st_uid != uid
    or root_metadata.st_gid != gid
):
    raise SystemExit("dependency target root ownership/type mismatch")
for path, metadata in reversed(entries):
    if stat.S_ISDIR(metadata.st_mode):
        os.chown(path, 0, 0)
        os.chmod(path, 0o555)
    else:
        os.chown(path, 0, 0)
        mode = 0o555 if stat.S_IMODE(metadata.st_mode) & 0o111 else 0o444
        os.chmod(path, mode)
os.chown(root, 0, 0)
os.chmod(root, 0o555)
PY
}

create_minimal_venv() {  # <target-root> <site-owner-user>
  local target="$1" owner="$2" uid gid
  uid=$(id -u "$owner")
  gid=$(id -g "$owner")
  trusted_python - "$target" "$uid" "$gid" <<'PY'
import os
import stat
import sys

target = os.path.abspath(sys.argv[1])
uid, gid = int(sys.argv[2]), int(sys.argv[3])
if os.path.lexists(target):
    raise SystemExit("minimal venv target already exists")
parent = os.path.dirname(target)
metadata = os.lstat(parent)
if (
    not stat.S_ISDIR(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0
    or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) & 0o022
):
    raise SystemExit("minimal venv parent is unsafe")
os.mkdir(target, 0o555)
os.mkdir(os.path.join(target, "bin"), 0o555)
os.mkdir(os.path.join(target, "lib"), 0o555)
os.mkdir(os.path.join(target, "lib", "python3.13"), 0o555)
site = os.path.join(target, "lib", "python3.13", "site-packages")
os.mkdir(site, 0o700)
os.chown(site, uid, gid)
os.symlink("/usr/bin/python3.13", os.path.join(target, "bin", "python"))
os.lchown(os.path.join(target, "bin", "python"), 0, 0)
configuration = (
    "home = /usr/bin\n"
    "include-system-site-packages = false\n"
    "version = 3.13\n"
    "executable = /usr/bin/python3.13\n"
)
path = os.path.join(target, "pyvenv.cfg")
fd = os.open(
    path,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
    0o444,
)
try:
    view = memoryview(configuration.encode("ascii"))
    while view:
        view = view[os.write(fd, view):]
    os.fchown(fd, 0, 0)
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

verify_transient_verifier_environment() {  # <pid> <unit> <expected-issuer>
  env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3.13 -I -B -S - "$1" "$2" "$3" <<'PY'
import os
import sys

pid, unit, issuer = sys.argv[1:]
payload = open(f"/proc/{pid}/environ", "rb", buffering=0).read()
entries = payload.split(b"\0")
allowed = {
    "CREDENTIALS_DIRECTORY", "HOME", "USER", "LOGNAME", "SHELL", "PATH",
    "INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID",
    "MEMORY_PRESSURE_WATCH", "MEMORY_PRESSURE_WRITE",
    "LANG", "LC_ALL", "TERM", "COLORTERM", "NO_COLOR", "SYSTEMD_COLORS",
    "TW_MCP_EXPECT_AUTHORIZATION_SERVER",
}
values = {}
for raw in entries:
    if not raw:
        continue
    name_raw, separator, value_raw = raw.partition(b"=")
    if not separator:
        raise SystemExit("verifier process has malformed environment")
    try:
        name = name_raw.decode("ascii")
        value = value_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit("verifier process has a non-text environment entry") from exc
    if name not in allowed or name in values:
        raise SystemExit(f"verifier process has unexpected environment name: {name}")
    values[name] = value
required = {
    "CREDENTIALS_DIRECTORY": f"/run/credentials/{unit}",
    "TW_MCP_EXPECT_AUTHORIZATION_SERVER": issuer,
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "USER": "tradewave-mcp-verify",
    "LOGNAME": "tradewave-mcp-verify",
    "SHELL": "/usr/sbin/nologin",
}
for name, expected in required.items():
    if values.get(name) != expected:
        raise SystemExit(f"verifier process has wrong {name}")
if "TW_MCP_VERIFY_TOKEN" in values:
    raise SystemExit("verifier token leaked into process environment")
PY
}

verify_exact_verifier_cmdline() {  # <pid> <fixed-script> <url> [verifier args...]
  trusted_python - "$@" <<'PY'
import pathlib
import sys

pid, script, url, *extra = sys.argv[1:]
raw = pathlib.Path(f"/proc/{int(pid)}/cmdline").read_bytes()
actual = [item.decode("utf-8") for item in raw.split(b"\0") if item]
expected = [
    "/usr/bin/python3.13", "-I", "-B", "-S", "-u", script, "--url", url, *extra,
]
if actual != expected:
    raise SystemExit(f"fixed verifier command mismatch: expected={expected!r} actual={actual!r}")
PY
}

run_verifier() {  # run_verifier <target-bundle-to-attest> <contract|load> <url> [extra args...]
  local runtime_bundle="$1" verifier_kind="$2" url="$3" issuer runtime_python script
  local pid="" credential_property binds part_of runner_rc attempt
  shift 3
  mint_verifier_probe
  [ -f "$VERIFIER_CREDENTIAL" ] && [ ! -L "$VERIFIER_CREDENTIAL" ] \
    && [ "$(stat -c '%U:%G %a' "$VERIFIER_CREDENTIAL")" = "root:root 600" ] \
    || fail "verifier credential source must be root:root mode 0600"
  [[ "$runtime_bundle" =~ ^${RELEASE_ROOT}/mcp-[0-9a-f]{40}$ ]] \
    || fail "verifier runtime bundle is not an exact immutable release path"
  case "$verifier_kind" in
    contract) script=$TRUSTED_CONTRACT_VERIFIER ;;
    load) script=$TRUSTED_LOAD_VERIFIER ;;
    *) fail "unsupported fixed verifier kind: $verifier_kind" ;;
  esac
  verify_sealed_bundle "$runtime_bundle" "${runtime_bundle##*/mcp-}"
  [ -f "$script" ] && [ ! -L "$script" ] || fail "verifier script is not a regular file"
  [ "$(stat -c '%U:%G %a %h' "$script")" = "root:root 555 1" ] \
    || fail "verifier script is not exact immutable fixed content"
  # The permanent Pro verifier credential must never meet candidate-controlled
  # Python or packages. Both fixed verifiers are stdlib-only and execute under
  # the exact isolated system interpreter from the installed control plane.
  runtime_python=$BASE_PYTHON
  issuer=$(runtime_env_value WORKOS_AUTHKIT_DOMAIN)
  assert_exact_uid_processes "$MCP_VERIFIER_USER" \
    || fail "verifier identity already has a live process"
  VERIFIER_RUN_COUNT=$((VERIFIER_RUN_COUNT + 1))
  VERIFIER_UNIT="tradewave-mcp-verify-${TXID:-recovery-$$}-$VERIFIER_RUN_COUNT.service"
  systemctl reset-failed "$VERIFIER_UNIT" >/dev/null 2>&1 || true
  set +e
  /usr/bin/systemd-run --quiet --wait --pipe --collect --service-type=exec \
    --unit="$VERIFIER_UNIT" --description="TradeWave MCP release verifier" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$DEPLOY_UNIT" --property="User=$MCP_VERIFIER_USER" \
    --property="Group=$MCP_VERIFIER_GROUP" --property="SupplementaryGroups=" \
    --property=WorkingDirectory=/ \
    --property="LoadCredential=verify-env:$VERIFIER_CREDENTIAL" \
    --property="UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK TERM COLORTERM NO_COLOR SYSTEMD_COLORS" \
    --setenv=PATH=/usr/bin:/bin --setenv=HOME=/nonexistent \
    --setenv=LANG=C.UTF-8 --setenv=LC_ALL=C.UTF-8 \
    --setenv="USER=$MCP_VERIFIER_USER" --setenv="LOGNAME=$MCP_VERIFIER_USER" \
    --setenv="SHELL=$MCP_SERVICE_SHELL" \
    --setenv="TW_MCP_EXPECT_AUTHORIZATION_SERVER=$issuer" \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
    --property=ProtectHome=read-only --property=PrivateTmp=yes \
    --property=PrivateDevices=yes --property=ProtectHostname=yes \
    --property=ProtectClock=yes --property=ProtectKernelTunables=yes \
    --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
    --property=ProtectKernelLogs=yes --property=ProtectProc=invisible \
    --property=ProcSubset=pid --property=RestrictSUIDSGID=yes \
    --property=RestrictNamespaces=yes --property=LockPersonality=yes \
    --property=SystemCallArchitectures=native \
    --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
    --property=CapabilityBoundingSet= --property=AmbientCapabilities= \
    --property=UMask=0077 --property=LimitCORE=0 \
    --property=LimitNOFILE=65536 --property=TasksMax=128 \
    --property=MemoryHigh=512M --property=MemoryMax=768M \
    --property="InaccessiblePaths=-/etc/tradewave -/home/flask -/home/tradewave-mcp" \
    --property=Restart=no --property=KillMode=control-group \
    --property=TimeoutStartSec=15s --property=TimeoutStopSec=10s \
    --property=RuntimeMaxSec=90s \
    "$runtime_python" -I -B -S -u "$script" --url "$url" "$@" &
  VERIFIER_RUNNER_PID=$!
  set -e

  for attempt in $(seq 1 100); do
    pid=$(systemctl show "$VERIFIER_UNIT" --property=MainPID --value 2>/dev/null || true)
    if [ -n "$pid" ] && [ "$pid" -ge 2 ] && [ -e "/proc/$pid" ]; then break; fi
    kill -0 "$VERIFIER_RUNNER_PID" 2>/dev/null || break
    sleep 0.02
  done
  if [ -z "$pid" ] || [ "$pid" -lt 2 ] || [ ! -e "/proc/$pid" ]; then
    set +e; wait "$VERIFIER_RUNNER_PID"; runner_rc=$?; set -e
    VERIFIER_UNIT=""; VERIFIER_RUNNER_PID=""
    fail "transient verifier exited before its identity boundary could be attested (status $runner_rc)"
  fi
  unlink_materialized_verifier_source \
    || { stop_transient_verifier_best_effort; fail "verifier raw credential source was not destroyed after materialization"; }
  [ "$(systemctl show "$VERIFIER_UNIT" --property=User --value)" = "$MCP_VERIFIER_USER" ] \
    || { stop_transient_verifier_best_effort; fail "transient verifier has wrong User"; }
  [ "$(systemctl show "$VERIFIER_UNIT" --property=Group --value)" = "$MCP_VERIFIER_GROUP" ] \
    || { stop_transient_verifier_best_effort; fail "transient verifier has wrong Group"; }
  credential_property=$(systemctl show "$VERIFIER_UNIT" --property=LoadCredential --value)
  [[ "$credential_property" = *"verify-env"* ]] \
    || { stop_transient_verifier_best_effort; fail "transient verifier has no verify-env credential"; }
  binds=$(systemctl show "$VERIFIER_UNIT" --property=BindsTo --value)
  part_of=$(systemctl show "$VERIFIER_UNIT" --property=PartOf --value)
  [[ " $binds " = *" $DEPLOY_UNIT "* ]] \
    || { stop_transient_verifier_best_effort; fail "transient verifier is not bound to deploy unit"; }
  [[ " $part_of " = *" $DEPLOY_UNIT "* ]] \
    || { stop_transient_verifier_best_effort; fail "transient verifier is not PartOf deploy unit"; }
  verify_mcp_process_identity_and_isolation "$pid" "$MCP_VERIFIER_USER" "$MCP_VERIFIER_GROUP" \
    || { stop_transient_verifier_best_effort; fail "transient verifier identity/isolation failed"; }
  assert_exact_uid_processes "$MCP_VERIFIER_USER" "$pid" \
    || { stop_transient_verifier_best_effort; fail "transient verifier spawned an unexpected process"; }
  verify_exact_verifier_cmdline "$pid" "$script" "$url" "$@" \
    || { stop_transient_verifier_best_effort; fail "transient verifier runtime/argv mismatch"; }
  verify_transient_verifier_environment "$pid" "$VERIFIER_UNIT" "$issuer" \
    || { stop_transient_verifier_best_effort; fail "transient verifier environment boundary failed"; }

  set +e
  wait "$VERIFIER_RUNNER_PID"
  runner_rc=$?
  set -e
  systemctl reset-failed "$VERIFIER_UNIT" >/dev/null 2>&1 || true
  VERIFIER_UNIT=""
  VERIFIER_RUNNER_PID=""
  assert_exact_uid_processes "$MCP_VERIFIER_USER" \
    || fail "verifier identity retained a process after transient collection"
  [ "$runner_rc" -eq 0 ] || fail "transient MCP verifier failed (status $runner_rc)"
  revoke_verifier_probe
}

public_contract_check() {  # public_contract_check <bundle>
  local bundle="$1" url
  url=$(public_url)
  if [ -z "$url" ]; then
    echo "FAIL: TW2_MCP_PUBLIC_URL is missing from $SECRETS" >&2
    return 1
  fi
  run_verifier "$bundle" contract "$url"
}

public_load_check() {  # public_load_check <runtime-bundle> <validator-bundle>
  local runtime_bundle="$1" validator_bundle="$2" url
  local -a compatibility_args=()
  : "$validator_bundle"  # Compatibility argument; validators are fixed controller assets.
  url=$(public_url)
  if [ -z "$url" ]; then
    echo "FAIL: TW2_MCP_PUBLIC_URL is missing from $SECRETS" >&2
    return 1
  fi
  if [ "${runtime_bundle##*/mcp-}" = "$LEGACY_ROLLBACK_SHA" ]; then
    compatibility_args+=(--legacy-smoke)
  fi
  run_verifier "$runtime_bundle" load "$url" \
    --clients 20 --timeout 20 \
    --phase-max-seconds 5 \
    --whoami-p95-max-seconds 2 --whoami-max-seconds 3 \
    --session-p95-max-seconds 12 --session-max-seconds 15 \
    "${compatibility_args[@]}"
}

candidate_contract_check() {  # <runtime-bundle>
  local bundle="$1" url
  local -a compatibility_args=()
  url=$(public_url)
  [ -n "$url" ] || fail "TW2_MCP_PUBLIC_URL is missing during candidate contract gate"
  if [ "${bundle##*/mcp-}" = "$LEGACY_ROLLBACK_SHA" ]; then
    compatibility_args+=(--legacy-smoke)
  fi
  run_verifier "$bundle" contract "$url" "${compatibility_args[@]}"
}

candidate_load_check() {  # <runtime-bundle>
  local bundle="$1" url
  local -a compatibility_args=()
  url=$(public_url)
  [ -n "$url" ] || fail "TW2_MCP_PUBLIC_URL is missing during candidate load gate"
  if [ "${bundle##*/mcp-}" = "$LEGACY_ROLLBACK_SHA" ]; then
    compatibility_args+=(--legacy-smoke)
  fi
  run_verifier "$bundle" load "$url" \
    --clients 20 --timeout 20 --phase-max-seconds 5 \
    --whoami-p95-max-seconds 2 --whoami-max-seconds 3 \
    --session-p95-max-seconds 12 --session-max-seconds 15 \
    "${compatibility_args[@]}"
}

public_no_bearer_gates() {
  local url issuer
  url=$(public_url)
  [ -n "$url" ] || fail "public MCP URL is absent during postcommit gates"
  issuer=$(authorization_server)
  [ -n "$issuer" ] || fail "WorkOS authorization server is absent during postcommit gates"
  env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TW_MCP_EXPECT_AUTHORIZATION_SERVER="$issuer" \
    "$BASE_PYTHON" -I -B -S "$TRUSTED_CONTRACT_VERIFIER" \
      --url "$url" --timeout 10 --unauthenticated-only \
    || fail "public OAuth discovery/exact no-bearer challenge gate failed"
}

rollback_contract_check() {  # rollback_contract_check <target-bundle> <validator-bundle>
  local target="$1" validator_bundle="$2" url
  : "$validator_bundle"  # Compatibility argument; validators are fixed controller assets.
  url=$(public_url)
  if [ -z "$url" ]; then
    echo "FAIL: TW2_MCP_PUBLIC_URL is missing from $SECRETS" >&2
    return 1
  fi
  if [ "${target##*/mcp-}" = "$LEGACY_ROLLBACK_SHA" ]; then
    run_verifier "$target" contract "$url" --legacy-smoke
  else
    run_verifier "$target" contract "$url"
  fi
}

verify_mcp_process_identity_and_isolation() {  # <pid> <user> <group>
  local pid="$1" account_name="$2" group_name="$3" uid gid
  local uid_label ruid euid suid fsuid gid_label rgid egid sgid fsgid
  local groups_label groups
  uid=$(id -u "$account_name") || return 1
  gid=$(getent group "$group_name" | awk -F: '{print $3}')
  [ -n "$uid" ] && [ -n "$gid" ] || return 1
  read -r uid_label ruid euid suid fsuid < <(grep '^Uid:' "/proc/$pid/status") || return 1
  read -r gid_label rgid egid sgid fsgid < <(grep '^Gid:' "/proc/$pid/status") || return 1
  read -r groups_label groups < <(grep '^Groups:' "/proc/$pid/status") || return 1
  [ "$ruid:$euid:$suid:$fsuid" = "$uid:$uid:$uid:$uid" ] \
    || { echo "FAIL: MCP PID $pid does not run wholly as uid $uid" >&2; return 1; }
  [ "$rgid:$egid:$sgid:$fsgid" = "$gid:$gid:$gid:$gid" ] \
    || { echo "FAIL: MCP PID $pid does not run wholly as gid $gid" >&2; return 1; }
  [ "$groups" = "$gid" ] \
    || { echo "FAIL: MCP PID $pid has supplementary groups: $groups" >&2; return 1; }

  # Enter the service's own mount namespace and drop to its exact uid/gid. This
  # proves systemd's filesystem boundary, not merely host DAC permissions.
  nsenter --mount="/proc/$pid/ns/mnt" -- \
    setpriv --reuid="$uid" --regid="$gid" --clear-groups -- \
    /bin/sh -c '
      ! test -r /etc/tradewave/secrets.env &&
      ! test -x /etc/tradewave &&
      ! test -r /home/flask &&
      ! test -x /home/flask
    ' || {
      echo "FAIL: MCP namespace can read platform secrets or the mutable gateway checkout" >&2
      return 1
    }
}

verify_mcp_service_identity_and_isolation() {  # <pid>
  local pid="$1" configured_user configured_group
  configured_user=$(systemctl show tradewave-mcpserver --property=User --value)
  configured_group=$(systemctl show tradewave-mcpserver --property=Group --value)
  [ "$configured_user" = "$MCP_SERVICE_USER" ] \
    || { echo "FAIL: MCP unit User is $configured_user, want $MCP_SERVICE_USER" >&2; return 1; }
  [ "$configured_group" = "$MCP_SERVICE_GROUP" ] \
    || { echo "FAIL: MCP unit Group is $configured_group, want $MCP_SERVICE_GROUP" >&2; return 1; }
  verify_mcp_process_identity_and_isolation "$pid" "$MCP_SERVICE_USER" "$MCP_SERVICE_GROUP"
  assert_exact_uid_processes "$MCP_SERVICE_USER" "$pid" \
    || { echo "FAIL: MCP service identity has a stale or extra process" >&2; return 1; }
}

verify_installed_service_policy() {  # [fenced|sealed-unfenced]
  local policy="${1:-fenced}" exact fragment dropins value name expected exec_start
  local -a conditions privileged dropin_files
  [ "$policy" = fenced ] || [ "$policy" = sealed-unfenced ] \
    || fail "unknown MCP service runtime policy: $policy"
  exact='ExecCondition=+/usr/bin/python3.13 -I -B -S /usr/local/libexec/tradewave-mcp-start-guard.py /var/lib/tradewave/mcp-release-transactions/active /run/lock/tradewave/mcp-release.lock'
  if [ "$policy" = fenced ]; then
    cmp -s "$TRUSTED_UNIT_TEMPLATE" "$UNIT" \
      || fail "installed MCP unit differs from the fixed fenced controller template"
  else
    # One migration-only predecessor is recognized semantically: the complete
    # current template, in the same directive order, with only ExecStart changed
    # from the lifetime flock wrapper to the former direct immutable Python
    # command. Comments/blank lines do not affect systemd and are ignored.
    trusted_python - "$TRUSTED_UNIT_TEMPLATE" "$UNIT" "$RUNTIME_LOCK" "$CURRENT_LINK" <<'PY'
import pathlib
import sys

template_path, installed_path, runtime_lock, current = sys.argv[1:]
fenced = (
    f"ExecStart=/usr/bin/flock --shared --nonblock --no-fork {runtime_lock} "
    f"{current}/venv/bin/python -I -B -u {current}/src/mcpserver/server.py "
    "--transport ${TW2_MCP_TRANSPORT} --host ${TW2_MCP_HOST} --port ${TW2_MCP_PORT}"
)
unfenced = (
    f"ExecStart={current}/venv/bin/python -I -B -u {current}/src/mcpserver/server.py "
    "--transport ${TW2_MCP_TRANSPORT} --host ${TW2_MCP_HOST} --port ${TW2_MCP_PORT}"
)

def directives(path: str) -> list[str]:
    result = []
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            result.append(line)
    return result

expected = directives(template_path)
if expected.count(fenced) != 1:
    raise SystemExit("fixed template does not contain its one exact fenced ExecStart")
expected[expected.index(fenced)] = unfenced
actual = directives(installed_path)
# The immediately preceding sealed controller carried the same fixed condition
# inline. The new stable fence duplicates it during this one migration only.
condition = (
    "ExecCondition=+/usr/bin/python3.13 -I -B -S "
    "/usr/local/libexec/tradewave-mcp-start-guard.py "
    "/var/lib/tradewave/mcp-release-transactions/active "
    "/run/lock/tradewave/mcp-release.lock"
)
if actual.count(condition) != 1:
    raise SystemExit("known sealed-unfenced predecessor lacks its exact inline condition")
actual.remove(condition)
if actual != expected:
    raise SystemExit("installed unit is not the exact known sealed-unfenced predecessor policy")
PY
  fi
  cmp -s "$TRUSTED_DROPIN_TEMPLATE" "$DROPIN" \
    || fail "installed MCP drop-in differs from the fixed controller template"
  cmp -s "$TRUSTED_FENCE_TEMPLATE" "$FENCE_DROPIN" \
    || fail "installed MCP release fence differs from the fixed stable template"
  [ "$(stat -c '%U:%G %a' "$UNIT")" = "root:root 644" ] \
    && [ "$(stat -c '%U:%G %a' "$DROPIN")" = "root:root 644" ] \
    && [ "$(stat -c '%U:%G %a' "$FENCE_DROPIN")" = "root:root 644" ] \
    || fail "installed MCP unit/drop-in/fence metadata is unsafe"
  [ "$(stat -c '%U:%G %a' "$RUNTIME_LOCK_DIR")" = "root:$MCP_SERVICE_GROUP 750" ] \
    && [ "$(stat -c '%U:%G %a %h %s' "$RUNTIME_LOCK")" = "root:$MCP_SERVICE_GROUP 640 1 0" ] \
    || fail "persistent MCP runtime-lock metadata is unsafe"
  fragment=$(systemctl show tradewave-mcpserver --property=FragmentPath --value)
  dropins=$(systemctl show tradewave-mcpserver --property=DropInPaths --value)
  [ "$fragment" = "$UNIT" ] || fail "effective MCP unit loads an unexpected fragment"
  trusted_python - "$dropins" "$FENCE_DROPIN" "$DROPIN" <<'PY'
import shlex
import sys

if set(shlex.split(sys.argv[1])) != set(sys.argv[2:]) or len(shlex.split(sys.argv[1])) != 2:
    raise SystemExit("effective MCP unit loads an unexpected drop-in set")
PY
  mapfile -t dropin_files < <(find "$(dirname "$DROPIN")" -mindepth 1 -maxdepth 1 -printf '%p\n' | sort)
  [ "${#dropin_files[@]}" -eq 2 ] \
    && [ "${dropin_files[0]}" = "$FENCE_DROPIN" ] \
    && [ "${dropin_files[1]}" = "$DROPIN" ] \
    || fail "MCP unit has an unexpected drop-in"
  mapfile -t conditions < <(
    systemctl cat tradewave-mcpserver.service --no-pager \
      | sed -n -E 's/^[[:space:]]*(ExecCondition=.*)$/\1/p'
  )
  if [ "$policy" = sealed-unfenced ]; then
    [ "${#conditions[@]}" -eq 2 ] \
      && [ "${conditions[0]}" = "$exact" ] && [ "${conditions[1]}" = "$exact" ] \
      || fail "known predecessor does not have its exact inline plus stable start guards"
  else
    [ "${#conditions[@]}" -eq 1 ] && [ "${conditions[0]}" = "$exact" ] \
      || fail "installed MCP unit does not have the one exact isolated fixed start guard"
  fi
  mapfile -t privileged < <(
    systemctl cat tradewave-mcpserver.service --no-pager \
      | sed -n -E 's/^[[:space:]]*(Exec[A-Za-z]*=\+.*)$/\1/p'
  )
  if [ "$policy" = sealed-unfenced ]; then
    [ "${#privileged[@]}" -eq 2 ] \
      && [ "${privileged[0]}" = "$exact" ] && [ "${privileged[1]}" = "$exact" ] \
      || fail "known predecessor has an unexpected privileged command"
  else
    [ "${#privileged[@]}" -eq 1 ] && [ "${privileged[0]}" = "$exact" ] \
      || fail "installed MCP unit has an unexpected privileged command"
  fi

  while IFS='|' read -r name expected; do
    value=$(systemctl show tradewave-mcpserver --property="$name" --value)
    [ "$value" = "$expected" ] \
      || fail "effective MCP $name is '$value', want '$expected'"
  done <<EOF
User|$MCP_SERVICE_USER
Group|$MCP_SERVICE_GROUP
SupplementaryGroups|
Type|exec
NoNewPrivileges|yes
ProtectSystem|strict
ProtectHome|read-only
WorkingDirectory|/
PrivateTmp|yes
PrivateDevices|yes
ProtectHostname|yes
ProtectClock|yes
ProtectKernelTunables|yes
ProtectKernelModules|yes
ProtectControlGroups|yes
ProtectKernelLogs|yes
ProtectProc|invisible
ProcSubset|pid
RestrictSUIDSGID|yes
RestrictNamespaces|yes
LockPersonality|yes
SystemCallArchitectures|native
RestrictAddressFamilies|AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet|
AmbientCapabilities|
UMask|0077
LimitCORE|0
LimitNOFILE|65536
TasksMax|256
MemoryHigh|805306368
MemoryMax|1073741824
KillMode|control-group
Restart|on-failure
RestartUSec|3s
TimeoutStopUSec|30s
StandardInput|null
StandardOutput|journal
StandardError|journal
InaccessiblePaths|-/etc/tradewave -/home/flask
EnvironmentFiles|/etc/tradewave/mcpserver.env (ignore_errors=no)
UnsetEnvironment|HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK PYTHONUNBUFFERED PYTHONDONTWRITEBYTECODE BASH_ENV ENV
RuntimeDirectory|
StateDirectory|
CacheDirectory|
LogsDirectory|
ConfigurationDirectory|
RootDirectory|
RootImage|
BindPaths|
TemporaryFileSystem|
LoadCredential|
SetCredential|
OpenFile|
EOF
  exec_start=$(systemctl show tradewave-mcpserver --property=ExecStart --value)
  [ "$(grep -o 'path=' <<<"$exec_start" | wc -l)" -eq 1 ] \
    || fail "effective MCP service does not have exactly one ExecStart"
  if [ "$policy" = fenced ]; then
    [[ "$exec_start" = *"path=/usr/bin/flock"* ]] \
      && [[ "$exec_start" = *"argv[]=/usr/bin/flock --shared --nonblock --no-fork $RUNTIME_LOCK $CURRENT_LINK/venv/bin/python -I -B -u $CURRENT_LINK/src/mcpserver/server.py"* ]] \
      || fail "effective MCP service lacks the exact fenced ExecStart"
  else
    [[ "$exec_start" = *"path=$CURRENT_LINK/venv/bin/python"* ]] \
      && [[ "$exec_start" = *"argv[]=$CURRENT_LINK/venv/bin/python -I -B -u $CURRENT_LINK/src/mcpserver/server.py"* ]] \
      && [[ "$exec_start" != *"/usr/bin/flock"* ]] \
      || fail "effective MCP service lacks the exact known sealed-unfenced ExecStart"
  fi
  for name in ExecStartPre ExecStartPost ExecReload ExecStop ExecStopPost; do
    [ -z "$(systemctl show tradewave-mcpserver --property="$name" --value)" ] \
      || fail "effective MCP service has forbidden $name commands"
  done
}

verify_service_enabled() {
  [ -L "$SERVICE_ENABLED" ] \
    && [ "$(stat -c '%U:%G %h' "$SERVICE_ENABLED")" = "root:root 1" ] \
    && [ "$(readlink "$SERVICE_ENABLED")" = "../tradewave-mcpserver.service" ] \
    || fail "MCP reboot activation symlink is absent or unsafe"
  [ "$(systemctl is-enabled tradewave-mcpserver.service)" = enabled ] \
    || fail "tradewave-mcpserver.service is not enabled for reboot activation"
}

verify_exact_mcp_cmdline() {  # <pid> <python> <server-script> <transport> <host> <port>
  trusted_python - "$@" <<'PY'
import pathlib
import sys

pid, python, script, transport, host, port = sys.argv[1:]
raw = pathlib.Path(f"/proc/{int(pid)}/cmdline").read_bytes()
argv = [entry.decode("utf-8") for entry in raw.split(b"\0") if entry]
expected = [
    python, "-I", "-B", "-u", script,
    "--transport", transport, "--host", host, "--port", port,
]
if argv != expected:
    raise SystemExit(f"MCP command line mismatch: expected={expected!r} actual={argv!r}")
PY
}

verify_runtime_shared_lock() {  # <persistent-main-pid> <exact-lock-path> <service-label>
  trusted_python - "$1" "$2" "$3" <<'PY'
import os
import pathlib
import sys

pid = int(sys.argv[1])
path = sys.argv[2]
label = sys.argv[3]
target = os.stat(path)
has_descriptor = False
for entry in pathlib.Path(f"/proc/{pid}/fd").iterdir():
    try:
        metadata = os.stat(entry)
    except FileNotFoundError:
        continue
    if (metadata.st_dev, metadata.st_ino) == (target.st_dev, target.st_ino):
        has_descriptor = True
        break
if not has_descriptor:
    raise SystemExit(f"persistent {label} PID did not inherit the runtime-lock descriptor")
device = f"{os.major(target.st_dev):02x}:{os.minor(target.st_dev):02x}"
matched = False
for line in pathlib.Path("/proc/locks").read_text(encoding="ascii").splitlines():
    fields = line.split()
    if len(fields) < 8 or fields[1:4] != ["FLOCK", "ADVISORY", "READ"]:
        continue
    if int(fields[4]) != pid:
        continue
    encoded_device, encoded_inode = fields[5].rsplit(":", 1)
    if encoded_device == device and int(encoded_inode) == target.st_ino:
        matched = True
        break
if not matched:
    raise SystemExit(f"persistent {label} PID does not hold the exact shared runtime lock")
PY
}

verify_running_bundle() {  # verify_running_bundle <bundle> <sha> [fenced|sealed-unfenced]
  local bundle="$1" sha="$2" policy="${3:-fenced}" linked pid cwd command
  if ! systemctl is-active --quiet tradewave-mcpserver; then
    echo "FAIL: tradewave-mcpserver is not active" >&2
    return 1
  fi
  linked=$(readlink -f "$CURRENT_LINK")
  if [ "$linked" != "$bundle" ] || [ "$(bundle_sha "$linked")" != "$sha" ]; then
    echo "FAIL: current bundle/SHA does not match $bundle @ $sha" >&2
    return 1
  fi
  verify_installed_service_policy "$policy" || return 1
  pid=$(systemctl show tradewave-mcpserver --property=MainPID --value)
  if [ "$policy" = fenced ]; then
    verify_runtime_shared_lock "$pid" "$RUNTIME_LOCK" MCP || return 1
  elif [ "$policy" != sealed-unfenced ]; then
    echo "FAIL: unknown running-bundle runtime policy: $policy" >&2
    return 1
  fi
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
  command=$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | head -1 || true)
  if [ "$cwd" != "/" ]; then
    echo "FAIL: MCP PID $pid cwd is $cwd, want /" >&2
    return 1
  fi
  if [ "$command" != "$CURRENT_LINK/venv/bin/python" ]; then
    echo "FAIL: MCP PID $pid runtime is $command, want $CURRENT_LINK/venv/bin/python" >&2
    return 1
  fi
  verify_exact_mcp_cmdline "$pid" "$CURRENT_LINK/venv/bin/python" \
    "$CURRENT_LINK/src/mcpserver/server.py" \
    "$(runtime_env_value TW2_MCP_TRANSPORT)" "$(runtime_env_value TW2_MCP_HOST)" \
    "$(runtime_env_value TW2_MCP_PORT)" || return 1
  verify_mcp_service_identity_and_isolation "$pid" || return 1
  trusted_python "$TRUSTED_ENV_HELPER" check-process-env \
    --path "$MCP_ENV" --pid "$pid" || return 1
  verify_loopback_listener_owners "$(runtime_env_value TW2_MCP_PORT)" "$pid" \
    || return 1
  say "running PID $pid from bundle $sha (code + venv; policy=$policy)"
}

verify_api_service_enabled() {
  [ -L "$API_SERVICE_ENABLED" ] \
    && [ "$(stat -c '%U:%G %h' "$API_SERVICE_ENABLED")" = "root:root 1" ] \
    && [ "$(readlink "$API_SERVICE_ENABLED")" = "../tradewave-apiserver.service" ] \
    || fail "API gateway reboot activation symlink is absent or unsafe"
  [ "$(systemctl is-enabled tradewave-apiserver.service)" = enabled ] \
    || fail "tradewave-apiserver.service is not enabled for reboot activation"
}

verify_installed_api_service_policy() {
  local exact fragment dropins exec_start environment inaccessible binds value name expected
  local -a conditions dropin_files
  exact='ExecCondition=+/usr/bin/python3.13 -I -B -S /usr/local/libexec/tradewave-mcp-start-guard.py /var/lib/tradewave/mcp-release-transactions/active /run/lock/tradewave/mcp-release.lock'
  cmp -s "$TRUSTED_API_UNIT_TEMPLATE" "$API_UNIT" \
    || fail "installed API gateway unit differs from the fixed controller template"
  cmp -s "$TRUSTED_API_FENCE_TEMPLATE" "$API_FENCE_DROPIN" \
    || fail "installed API gateway release fence differs from the fixed stable template"
  [ "$(stat -c '%U:%G %a' "$API_UNIT")" = "root:root 644" ] \
    && [ "$(stat -c '%U:%G %a' "$API_FENCE_DROPIN")" = "root:root 644" ] \
    || fail "installed API gateway unit/fence metadata is unsafe"
  [ -f "$API_ENV" ] && [ ! -L "$API_ENV" ] \
    && [ "$(stat -c '%U:%G %a %h' "$API_ENV")" = "root:root 600 1" ] \
    || fail "dedicated API gateway environment metadata is unsafe"
  trusted_python "$TRUSTED_ENV_HELPER" validate-api --path "$API_ENV" \
    || fail "dedicated API gateway environment allowlist is invalid"
  [ "$(stat -c '%U:%G %a' "$API_RUNTIME_LOCK_DIR")" = "root:$API_SERVICE_GROUP 750" ] \
    && [ "$(stat -c '%U:%G %a %h %s' "$API_RUNTIME_LOCK")" = "root:$API_SERVICE_GROUP 640 1 0" ] \
    || fail "API gateway runtime-lock metadata is unsafe"
  fragment=$(systemctl show tradewave-apiserver --property=FragmentPath --value)
  dropins=$(systemctl show tradewave-apiserver --property=DropInPaths --value)
  [ "$fragment" = "$API_UNIT" ] || fail "effective API gateway loads an unexpected fragment"
  [ "$dropins" = "$API_FENCE_DROPIN" ] \
    || fail "effective API gateway loads an unexpected drop-in set"
  mapfile -t dropin_files < <(find "$(dirname "$API_FENCE_DROPIN")" -mindepth 1 -maxdepth 1 -printf '%p\n' | sort)
  [ "${#dropin_files[@]}" -eq 1 ] && [ "${dropin_files[0]}" = "$API_FENCE_DROPIN" ] \
    || fail "API gateway unit has an unexpected drop-in"
  mapfile -t conditions < <(
    systemctl cat tradewave-apiserver.service --no-pager \
      | sed -n -E 's/^[[:space:]]*(ExecCondition=.*)$/\1/p'
  )
  [ "${#conditions[@]}" -eq 1 ] && [ "${conditions[0]}" = "$exact" ] \
    || fail "installed API gateway does not have the one exact fixed start guard"
  [[ "$(systemctl show tradewave-apiserver --property=ExecCondition --value)" = \
      *"path=/usr/bin/python3.13"*"argv[]=/usr/bin/python3.13 -I -B -S $START_GUARD $TX_ACTIVE $LOCK_FILE"* ]] \
    || fail "effective API gateway ExecCondition is not the exact fixed start guard"

  while IFS='|' read -r name expected; do
    value=$(systemctl show tradewave-apiserver --property="$name" --value)
    [ "$value" = "$expected" ] \
      || fail "effective API gateway $name is '$value', want '$expected'"
  done <<EOF
User|$API_SERVICE_USER
Group|$API_SERVICE_GROUP
SupplementaryGroups|
Type|notify
NoNewPrivileges|yes
ProtectSystem|strict
ProtectHome|read-only
WorkingDirectory|$CURRENT_LINK/src
PrivateTmp|yes
PrivateDevices|yes
ProtectHostname|yes
ProtectClock|yes
ProtectKernelTunables|yes
ProtectKernelModules|yes
ProtectControlGroups|yes
ProtectKernelLogs|yes
ProtectProc|invisible
ProcSubset|pid
RestrictSUIDSGID|yes
RestrictNamespaces|yes
LockPersonality|yes
SystemCallArchitectures|native
RestrictAddressFamilies|AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet|
AmbientCapabilities|
UMask|0077
LimitCORE|0
LimitNOFILE|65536
TasksMax|256
MemoryHigh|1073741824
MemoryMax|1610612736
Restart|on-failure
RestartUSec|3s
StandardOutput|journal
StandardError|journal
EnvironmentFiles|/etc/tradewave/apiserver.env (ignore_errors=no)
UnsetEnvironment|HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK PYTHONUNBUFFERED PYTHONHASHSEED BASH_ENV ENV GUNICORN_CMD_ARGS WEB_CONCURRENCY
EOF
  inaccessible=$(systemctl show tradewave-apiserver --property=InaccessiblePaths --value)
  [ "$inaccessible" = "-/etc/tradewave /home/flask" ] \
    || fail "effective API gateway does not hide /etc/tradewave and /home/flask exactly"
  binds=$(systemctl show tradewave-apiserver --property=BindReadOnlyPaths --value)
  [[ "$binds" = *"/home/flask/site/data/featured_history.json:/run/tradewave-gateway/featured_history.json"* ]] \
    || fail "effective API gateway lacks the one featured-history read-only bind"
  environment=$(systemctl show tradewave-apiserver --property=Environment --value)
  [[ " $environment " = *" TW2_FEATURED_HISTORY_FILE=/run/tradewave-gateway/featured_history.json "* ]] \
    && [[ " $environment " != *" PYTHONPATH="* ]] \
    && [[ " $environment " != *" MCP_GATEWAY_KEY="* ]] \
    || fail "effective API gateway environment policy drifted"
  exec_start=$(systemctl show tradewave-apiserver --property=ExecStart --value)
  [ "$(grep -o 'path=' <<<"$exec_start" | wc -l)" -eq 1 ] \
    && [[ "$exec_start" = *"path=/usr/bin/flock"* ]] \
    && [[ "$exec_start" = *"argv[]=/usr/bin/flock --shared --nonblock --no-fork $API_RUNTIME_LOCK $CURRENT_LINK/gateway-venv/bin/python -I -B -m gunicorn --chdir $CURRENT_LINK/src --workers 4 --worker-class gthread --threads 12 --timeout 120 --keep-alive 75 --bind 127.0.0.1:8088 --access-logfile - --error-logfile - --capture-output apiserver.app:app"* ]] \
    || fail "effective API gateway ExecStart is not exact"
  for name in ExecStartPre ExecStartPost ExecReload ExecStop ExecStopPost; do
    [ -z "$(systemctl show tradewave-apiserver --property="$name" --value)" ] \
      || fail "effective API gateway has forbidden $name commands"
  done
}

service_cgroup_pids() {  # <systemd-unit>
  local cgroup
  cgroup=$(systemctl show "$1" --property=ControlGroup --value)
  [[ "$cgroup" = /* ]] && [ -r "/sys/fs/cgroup$cgroup/cgroup.procs" ] \
    || fail "$1 has no readable service cgroup"
  sort -n -u "/sys/fs/cgroup$cgroup/cgroup.procs" | tr '\n' ' '
}

verify_exact_api_processes() {  # <unit> <python> <source> <port> <featured-path>
  local unit="$1" python="$2" source="$3" port="$4" featured="$5" raw_pids main_pid
  raw_pids=$(service_cgroup_pids "$unit")
  read -r -a api_pids <<< "$raw_pids"
  [ "${#api_pids[@]}" -eq 5 ] || fail "$unit does not have one Gunicorn master plus four workers"
  main_pid=$(systemctl show "$unit" --property=MainPID --value)
  [[ " ${api_pids[*]} " = *" $main_pid "* ]] || fail "$unit MainPID is outside its cgroup"
  trusted_python - "$API_SERVICE_USER" "$API_SERVICE_GROUP" "$python" "$source" \
    "$port" "$featured" "$main_pid" "${api_pids[@]}" <<'PY'
import os
import pathlib
import pwd
import grp
import sys

account, group, python, source, port, featured, main, *raw_pids = sys.argv[1:]
source_real = os.path.realpath(source)
pids = {int(value) for value in raw_pids}
uid = pwd.getpwnam(account).pw_uid
gid = grp.getgrnam(group).gr_gid
expected = [
    python, "-I", "-B", "-m", "gunicorn", "--chdir", source,
    "--workers", "4", "--worker-class", "gthread", "--threads", "12",
    "--timeout", "120", "--keep-alive", "75", "--bind", f"127.0.0.1:{port}",
    "--access-logfile", "-", "--error-logfile", "-", "--capture-output",
    "apiserver.app:app",
]
for pid in pids:
    process = pathlib.Path(f"/proc/{pid}")
    status = (process / "status").read_text(encoding="ascii").splitlines()
    uids = next(line for line in status if line.startswith("Uid:")).split()[1:]
    gids = next(line for line in status if line.startswith("Gid:")).split()[1:]
    groups = next(line for line in status if line.startswith("Groups:")).split()[1:]
    if uids != [str(uid)] * 4 or gids != [str(gid)] * 4 or groups != [str(gid)]:
        raise SystemExit(f"API PID {pid} identity/group set drifted")
    argv = [value.decode() for value in (process / "cmdline").read_bytes().split(b"\0") if value]
    if argv != expected:
        raise SystemExit(f"API PID {pid} argv drifted: {argv!r}")
    if os.path.realpath(process / "cwd") != source_real:
        raise SystemExit(f"API PID {pid} cwd escaped sealed source")
    environment = {}
    for item in (process / "environ").read_bytes().split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment.setdefault(key.decode(), []).append(value.decode())
    if "MCP_GATEWAY_KEY" in environment:
        raise SystemExit(f"API PID {pid} retained broad MCP_GATEWAY_KEY")
    if environment.get("TW2_FEATURED_HISTORY_FILE") != [featured]:
        raise SystemExit(f"API PID {pid} featured-history path drifted")

holders = set()
for process in pathlib.Path("/proc").glob("[0-9]*"):
    try:
        status = (process / "status").read_text(encoding="ascii").splitlines()
        uids = {int(value) for value in next(line for line in status if line.startswith("Uid:")).split()[1:]}
    except (FileNotFoundError, ProcessLookupError, StopIteration):
        continue
    if uid in uids:
        holders.add(int(process.name))
if holders != pids:
    raise SystemExit(f"API identity has processes outside its service cgroup: {sorted(holders - pids)}")
if int(main) not in pids:
    raise SystemExit("API MainPID is outside expected process set")
PY
  local api_pid
  for api_pid in "${api_pids[@]}"; do
    trusted_python "$TRUSTED_ENV_HELPER" check-api-process-env \
      --path "$API_ENV" --pid "$api_pid" --featured-path "$featured" \
      || fail "$unit API PID $api_pid inherited a non-allowlisted environment"
  done
  nsenter --mount="/proc/$main_pid/ns/mnt" -- \
    setpriv --reuid="$(id -u "$API_SERVICE_USER")" \
      --regid="$(id -g "$API_SERVICE_USER")" --clear-groups -- \
      /bin/sh -c 'test -s "$1" && test -r "$1" && ! test -w "$1" && ! test -r /etc/tradewave/secrets.env && ! test -x /etc/tradewave && ! test -r /home/flask && ! test -x /home/flask' \
      sh "$featured" \
    || fail "$unit mount namespace isolation or featured ledger bind failed"
  trusted_python - "$port" "${api_pids[@]}" <<'PY'
import os
import pathlib
import socket
import sys

port = int(sys.argv[1])
pids = {int(value) for value in sys.argv[2:]}
encoded = f"{port:04X}"
listeners = []
for table in ("/proc/net/tcp", "/proc/net/tcp6"):
    for line in pathlib.Path(table).read_text(encoding="ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 10 and fields[1].rsplit(":", 1)[-1] == encoded and fields[3] == "0A":
            listeners.append((table, fields[1], fields[9]))
expected_address = f"0100007F:{encoded}"
if len(listeners) != 1 or listeners[0][0] != "/proc/net/tcp" or listeners[0][1] != expected_address:
    raise SystemExit(f"API listener is not exactly IPv4 loopback-only: {listeners!r}")
inode = listeners[0][2]
owners = set()
for process in pathlib.Path("/proc").glob("[0-9]*"):
    try:
        descriptors = list((process / "fd").iterdir())
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    for descriptor in descriptors:
        try:
            target = os.readlink(descriptor)
        except (FileNotFoundError, OSError):
            continue
        if target == f"socket:[{inode}]":
            owners.add(int(process.name))
if not owners or not owners.issubset(pids):
    raise SystemExit(f"API listener has owners outside its service cgroup: {sorted(owners - pids)}")
PY
}

verify_running_api_bundle() {  # <bundle> <sha> [unit] [port] [featured-path]
  local bundle="$1" sha="$2" unit="${3:-tradewave-apiserver.service}"
  local port="${4:-8088}" featured="${5:-/run/tradewave-gateway/featured_history.json}" main python source
  systemctl is-active --quiet "$unit" || fail "$unit is not active"
  [ "$(systemctl show "$unit" --property=ActiveState --value)" = active ] \
    && [ "$(systemctl show "$unit" --property=SubState --value)" = running ] \
    && [ "$(systemctl show "$unit" --property=Type --value)" = notify ] \
    || fail "$unit did not reach Type=notify active/running readiness"
  [ "$(readlink -f "$CURRENT_LINK")" = "$bundle" ] \
    && [ "$(bundle_sha "$bundle")" = "$sha" ] \
    || fail "$unit does not run the current sealed bundle identity"
  if [ "$unit" = tradewave-apiserver.service ]; then
    verify_installed_api_service_policy
    verify_api_service_enabled
  fi
  # Both stable and canary use the literal current-link argv/cwd. The realpath
  # binding above proves that link resolves to this exact sealed candidate.
  python=$CURRENT_LINK/gateway-venv/bin/python
  source=$CURRENT_LINK/src
  verify_exact_api_processes "$unit" "$python" "$source" "$port" "$featured"
  curl --noproxy '*' --fail --silent --show-error --connect-timeout 1 --max-time 3 \
    "http://127.0.0.1:$port/healthz" >/dev/null \
    || fail "$unit did not pass its local health gate"
  main=$(systemctl show "$unit" --property=MainPID --value)
  if [ "$unit" = tradewave-apiserver.service ]; then
    verify_runtime_shared_lock "$main" "$API_RUNTIME_LOCK" "API gateway"
  fi
  say "API gateway PID $main with four workers serves sealed bundle $sha on $port"
}

runtime_env_value() {  # <exact-name>
  local name="$1" value count
  count=$(awk -F= -v key="$name" '$1 == key {count++} END {print count+0}' "$MCP_ENV")
  [ "$count" = 1 ] || fail "$MCP_ENV does not contain exactly one $name assignment"
  value=$(awk -F= -v key="$name" '$1 == key {print substr($0, index($0, "=") + 1)}' "$MCP_ENV")
  [[ "$value" =~ ^[A-Za-z0-9_.:/@+-]+$ ]] || fail "$MCP_ENV has an unsafe $name value"
  printf '%s' "$value"
}

verify_canary_policy_equivalence() {  # <canary-unit> <stable-unit> <api|mcp>
  local canary="$1" stable="$2" kind="$3" property candidate_value stable_value
  local candidate_exec stable_exec expected_lock
  local -a properties=(
    User Group SupplementaryGroups Type WorkingDirectory EnvironmentFiles Environment
    UnsetEnvironment NoNewPrivileges ProtectSystem ProtectHome PrivateTmp PrivateDevices
    ProtectHostname ProtectClock ProtectKernelTunables ProtectKernelModules
    ProtectControlGroups ProtectKernelLogs ProtectProc ProcSubset RestrictSUIDSGID
    RestrictNamespaces LockPersonality SystemCallArchitectures RestrictAddressFamilies
    CapabilityBoundingSet AmbientCapabilities UMask LimitCORE LimitNOFILE TasksMax
    MemoryHigh MemoryMax InaccessiblePaths StandardInput StandardOutput StandardError
    KillMode RestartUSec TimeoutStopUSec
  )
  if [ "$kind" = api ]; then
    properties+=(RuntimeDirectory RuntimeDirectoryMode BindReadOnlyPaths)
    expected_lock=$API_RUNTIME_LOCK
  elif [ "$kind" != mcp ]; then
    fail "unknown canary equivalence kind: $kind"
  else
    expected_lock=$RUNTIME_LOCK
  fi
  for property in "${properties[@]}"; do
    candidate_value=$(systemctl show "$canary" --property="$property" --value)
    stable_value=$(systemctl show "$stable" --property="$property" --value)
    [ "$candidate_value" = "$stable_value" ] \
      || fail "$kind canary $property differs from stable unit: '$candidate_value' != '$stable_value'"
  done
  [ "$(systemctl show "$canary" --property=Restart --value)" = no ] \
    && [ "$(systemctl show "$stable" --property=Restart --value)" = on-failure ] \
    || fail "$kind canary/stable restart semantics are not exact"
  candidate_exec=$(systemctl show "$canary" --property=ExecStart --value)
  stable_exec=$(systemctl show "$stable" --property=ExecStart --value)
  trusted_python - "$kind" "$CURRENT_LINK" "$expected_lock" \
    "$candidate_exec" "$stable_exec" <<'PY'
import shlex
import sys

kind, current, expected_lock, candidate_raw, stable_raw = sys.argv[1:]

def command(raw: str) -> list[str]:
    marker = "argv[]="
    start = raw.find(marker)
    end = raw.find(" ; ignore_errors=", start)
    if start < 0 or end < 0:
        raise SystemExit("effective ExecStart has an unexpected systemd representation")
    return shlex.split(raw[start + len(marker):end])

candidate = command(candidate_raw)
stable = command(stable_raw)
wrapper = ["/usr/bin/flock", "--shared", "--nonblock", "--no-fork", expected_lock]
if stable[:len(wrapper)] != wrapper:
    raise SystemExit(f"{kind} stable ExecStart lacks its exact lifetime-lock wrapper")
stable = stable[len(wrapper):]
if kind == "mcp":
    substitutions = {
        "${TW2_MCP_TRANSPORT}": "streamable-http",
        "${TW2_MCP_HOST}": "127.0.0.1",
        "${TW2_MCP_PORT}": "9090",
    }
    stable = [substitutions.get(value, value) for value in stable]
if candidate != stable:
    raise SystemExit(
        f"{kind} canary command is not stable ExecStart after removing only "
        "the persistent lifetime-lock wrapper"
    )
PY
  say "$kind canary policy/argv is mechanically equivalent to $stable; only Restart=no is transient"
}

start_api_candidate_canary() {  # <bundle> <sha>
  local bundle="$1" sha="$2" runtime_dir featured binds part_of
  command -v systemd-run >/dev/null 2>&1 || fail "systemd-run is missing"
  runtime_dir="tradewave-gateway"
  featured="/run/$runtime_dir/featured_history.json"
  API_CANARY_UNIT="tradewave-api-canary-$TXID.service"
  systemctl reset-failed "$API_CANARY_UNIT" >/dev/null 2>&1 || true
  /usr/bin/systemd-run --quiet --collect --service-type=notify --unit="$API_CANARY_UNIT" \
    --description="TradeWave API gateway precommit canary $sha" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$DEPLOY_UNIT" --property="User=$API_SERVICE_USER" \
    --property="Group=$API_SERVICE_GROUP" --property="SupplementaryGroups=" \
    --property="WorkingDirectory=$CURRENT_LINK/src" \
    --property="EnvironmentFile=$API_ENV" \
    --property=Environment=HOME=/nonexistent \
    --property=Environment=PATH=/usr/bin:/bin \
    --property=Environment=LANG=C.UTF-8 \
    --property=Environment=LC_ALL=C.UTF-8 \
    --property=Environment=PYTHONDONTWRITEBYTECODE=1 \
    --property="Environment=TW2_FEATURED_HISTORY_FILE=$featured" \
    --property="UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK PYTHONUNBUFFERED PYTHONHASHSEED BASH_ENV ENV GUNICORN_CMD_ARGS WEB_CONCURRENCY" \
    --property="RuntimeDirectory=$runtime_dir" --property=RuntimeDirectoryMode=0700 \
    --property="BindReadOnlyPaths=/home/flask/site/data/featured_history.json:$featured" \
    --property="InaccessiblePaths=-/etc/tradewave /home/flask" \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
    --property=ProtectHome=read-only --property=PrivateTmp=yes \
    --property=PrivateDevices=yes --property=ProtectHostname=yes \
    --property=ProtectClock=yes --property=ProtectKernelTunables=yes \
    --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
    --property=ProtectKernelLogs=yes --property=ProtectProc=invisible \
    --property=ProcSubset=pid --property=RestrictSUIDSGID=yes \
    --property=RestrictNamespaces=yes --property=LockPersonality=yes \
    --property=SystemCallArchitectures=native \
    --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
    --property=CapabilityBoundingSet= --property=AmbientCapabilities= \
    --property=UMask=0077 --property=LimitCORE=0 \
    --property=LimitNOFILE=65536 --property=TasksMax=256 \
    --property=MemoryHigh=1G --property=MemoryMax=1536M \
    --property=Restart=no --property=RestartSec=3s --property=KillMode=control-group \
    --property=TimeoutStopSec=90s \
    "$CURRENT_LINK/gateway-venv/bin/python" -I -B -m gunicorn \
      --chdir "$CURRENT_LINK/src" --workers 4 --worker-class gthread --threads 12 \
      --timeout 120 --keep-alive 75 --bind "127.0.0.1:$API_CANARY_PORT" \
      --access-logfile - --error-logfile - --capture-output apiserver.app:app
  systemctl is-active --quiet "$API_CANARY_UNIT" || fail "API gateway canary did not become active"
  API_CANARY_PID=$(systemctl show "$API_CANARY_UNIT" --property=MainPID --value)
  [ -n "$API_CANARY_PID" ] && [ "$API_CANARY_PID" -ge 2 ] \
    || fail "API gateway canary has no MainPID"
  binds=$(systemctl show "$API_CANARY_UNIT" --property=BindsTo --value)
  part_of=$(systemctl show "$API_CANARY_UNIT" --property=PartOf --value)
  [[ " $binds " = *" $DEPLOY_UNIT "* ]] || fail "API gateway canary is not bound to deploy unit"
  [[ " $part_of " = *" $DEPLOY_UNIT "* ]] || fail "API gateway canary is not PartOf deploy unit"
  verify_canary_policy_equivalence "$API_CANARY_UNIT" tradewave-apiserver.service api
  verify_running_api_bundle "$bundle" "$sha" "$API_CANARY_UNIT" \
    "$API_CANARY_PORT" "$featured"
}

start_candidate_canary() {  # <bundle> <sha>
  local bundle="$1" sha="$2" binds part_of
  command -v systemd-run >/dev/null 2>&1 || fail "systemd-run is missing"
  [ "${MCP_CANARY_ENV:-}" = "$MCP_ENV" ] && [ -r "$MCP_ENV" ] \
    || fail "MCP canary environment was not prepared from the stable exact file"
  CANARY_UNIT="tradewave-mcp-canary-$TXID.service"
  systemctl reset-failed "$CANARY_UNIT" >/dev/null 2>&1 || true
  /usr/bin/systemd-run --quiet --collect --service-type=exec --unit="$CANARY_UNIT" \
    --description="TradeWave MCP precommit canary $sha" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$DEPLOY_UNIT" --property="User=$MCP_SERVICE_USER" \
    --property="Group=$MCP_SERVICE_GROUP" --property="SupplementaryGroups=" \
    --property=WorkingDirectory=/ --property="EnvironmentFile=$MCP_ENV" \
    --property=Environment=API_BASE_URL=http://127.0.0.1:8088/v1 \
    --property=Environment=TW2_MCP_HOST=127.0.0.1 \
    --property=Environment=TW2_MCP_PORT=9090 \
    --property=Environment=TW2_MCP_TRANSPORT=streamable-http \
    --property="UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS PYTHONBREAKPOINT PYTHONPLATLIBDIR PYTHONCASEOK PYTHONUNBUFFERED PYTHONDONTWRITEBYTECODE BASH_ENV ENV" \
    --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
    --property=ProtectHome=read-only --property=PrivateTmp=yes \
    --property=PrivateDevices=yes --property=ProtectHostname=yes \
    --property=ProtectClock=yes --property=ProtectKernelTunables=yes \
    --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
    --property=ProtectKernelLogs=yes --property=ProtectProc=invisible \
    --property=ProcSubset=pid --property=RestrictSUIDSGID=yes \
    --property=RestrictNamespaces=yes --property=LockPersonality=yes \
    --property=SystemCallArchitectures=native \
    --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
    --property=CapabilityBoundingSet= --property=AmbientCapabilities= \
    --property=UMask=0077 --property=LimitCORE=0 \
    --property=LimitNOFILE=65536 --property=TasksMax=256 \
    --property=MemoryHigh=768M --property=MemoryMax=1G \
    --property="InaccessiblePaths=-/etc/tradewave -/home/flask" \
    --property=Restart=no --property=RestartSec=3s --property=KillMode=control-group \
    --property=TimeoutStopSec=30s \
    "$CURRENT_LINK/venv/bin/python" -I -B -u "$CURRENT_LINK/src/mcpserver/server.py" \
      --transport streamable-http --host 127.0.0.1 --port "$MCP_CANARY_PORT"
  systemctl is-active --quiet "$CANARY_UNIT" || fail "MCP canary did not become active"
  CANARY_PID=$(systemctl show "$CANARY_UNIT" --property=MainPID --value)
  [ -n "$CANARY_PID" ] && [ "$CANARY_PID" -ge 2 ] || fail "MCP canary has no MainPID"
  binds=$(systemctl show "$CANARY_UNIT" --property=BindsTo --value)
  part_of=$(systemctl show "$CANARY_UNIT" --property=PartOf --value)
  [[ " $binds " = *" $DEPLOY_UNIT "* ]] || fail "MCP canary is not bound to deploy unit"
  [[ " $part_of " = *" $DEPLOY_UNIT "* ]] || fail "MCP canary is not PartOf deploy unit"
  verify_canary_policy_equivalence "$CANARY_UNIT" tradewave-mcpserver.service mcp
}

verify_candidate_canary() {  # <bundle> <sha>
  local bundle="$1" sha="$2" linked cwd command attempt
  systemctl is-active --quiet "$CANARY_UNIT" || fail "MCP canary is not active"
  linked=$(readlink -f "$CURRENT_LINK")
  [ "$linked" = "$bundle" ] && [ "$(bundle_sha "$linked")" = "$sha" ] \
    || fail "canary current bundle/SHA mismatch"
  cwd=$(readlink -f "/proc/$CANARY_PID/cwd" 2>/dev/null || true)
  command=$(tr '\0' '\n' < "/proc/$CANARY_PID/cmdline" 2>/dev/null | head -1 || true)
  [ "$cwd" = "/" ] || fail "MCP canary cwd mismatch: $cwd"
  [ "$command" = "$CURRENT_LINK/venv/bin/python" ] || fail "MCP canary runtime mismatch: $command"
  verify_exact_mcp_cmdline "$CANARY_PID" "$CURRENT_LINK/venv/bin/python" \
    "$CURRENT_LINK/src/mcpserver/server.py" \
    streamable-http 127.0.0.1 "$MCP_CANARY_PORT"
  [ "$(systemctl show "$CANARY_UNIT" --property=User --value)" = "$MCP_SERVICE_USER" ] \
    || fail "MCP canary unit has wrong User"
  [ "$(systemctl show "$CANARY_UNIT" --property=Group --value)" = "$MCP_SERVICE_GROUP" ] \
    || fail "MCP canary unit has wrong Group"
  verify_mcp_process_identity_and_isolation "$CANARY_PID" "$MCP_SERVICE_USER" "$MCP_SERVICE_GROUP"
  assert_exact_uid_processes "$MCP_SERVICE_USER" "$CANARY_PID" \
    || fail "MCP canary identity has a stale or extra process"
  trusted_python "$TRUSTED_ENV_HELPER" check-process-env \
    --path "$MCP_ENV" --pid "$CANARY_PID"
  for attempt in $(seq 1 50); do
    if curl --noproxy '*' --connect-timeout 0.2 --max-time 1 -sS -o /dev/null \
        "http://127.0.0.1:$MCP_CANARY_PORT/"; then
      verify_loopback_listener_owners "$MCP_CANARY_PORT" "$CANARY_PID" \
        || fail "MCP canary listener ownership/address policy failed"
      say "precommit canary PID $CANARY_PID is serving sealed bundle $sha"
      return 0
    fi
    systemctl is-active --quiet "$CANARY_UNIT" || fail "MCP canary exited during readiness"
    sleep 0.2
  done
  fail "MCP canary did not bind its loopback port"
}

tcp_listen_port_present() {  # <decimal-port>; success means LISTEN exists
  trusted_python - "$1" <<'PY'
import pathlib
import sys

port = int(sys.argv[1])
if not 1 <= port <= 65535:
    raise SystemExit("invalid TCP port")
encoded = f"{port:04X}"
for table in (pathlib.Path("/proc/net/tcp"), pathlib.Path("/proc/net/tcp6")):
    try:
        lines = table.read_text(encoding="ascii").splitlines()[1:]
    except FileNotFoundError:
        continue
    for line in lines:
        fields = line.split()
        if len(fields) >= 4 and fields[1].rsplit(":", 1)[-1] == encoded and fields[3] == "0A":
            raise SystemExit(0)
raise SystemExit(1)
PY
}

assert_paired_ports_free() {
  ! tcp_listen_port_present "$API_CANARY_PORT" \
    || fail "API gateway production loopback port $API_CANARY_PORT is still occupied"
  ! tcp_listen_port_present "$MCP_CANARY_PORT" \
    || fail "MCP production loopback port $MCP_CANARY_PORT is still occupied"
}

verify_loopback_listener_owners() {  # <port> <allowed-pid>...
  trusted_python - "$@" <<'PY'
import os
import pathlib
import sys

port = int(sys.argv[1])
allowed = {int(value) for value in sys.argv[2:]}
if not allowed:
    raise SystemExit("listener owner allowlist is empty")
encoded = f"{port:04X}"
expected = f"0100007F:{encoded}"
listeners = []
for table in (pathlib.Path("/proc/net/tcp"), pathlib.Path("/proc/net/tcp6")):
    for line in table.read_text(encoding="ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 10 and fields[1].rsplit(":", 1)[-1] == encoded and fields[3] == "0A":
            listeners.append((str(table), fields[1], fields[9]))
if len(listeners) != 1 or listeners[0][0] != "/proc/net/tcp" or listeners[0][1] != expected:
    raise SystemExit(f"listener is not exact IPv4 loopback: {listeners!r}")
inode = listeners[0][2]
owners = set()
for process in pathlib.Path("/proc").glob("[0-9]*"):
    try:
        descriptors = list((process / "fd").iterdir())
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    for descriptor in descriptors:
        try:
            target = os.readlink(descriptor)
        except (FileNotFoundError, OSError):
            continue
        if target == f"socket:[{inode}]":
            owners.add(int(process.name))
if not owners or not owners.issubset(allowed):
    raise SystemExit(f"listener ownership escaped service cgroup: {sorted(owners - allowed)}")
PY
}

stop_candidate_canary_best_effort() {
  if [ -n "$CANARY_UNIT" ]; then
    systemctl stop "$CANARY_UNIT" >/dev/null 2>&1 || true
    systemctl reset-failed "$CANARY_UNIT" >/dev/null 2>&1 || true
    CANARY_UNIT=""
    CANARY_PID=""
  fi
}

stop_api_candidate_canary_best_effort() {
  if [ -n "$API_CANARY_UNIT" ]; then
    systemctl stop "$API_CANARY_UNIT" >/dev/null 2>&1 || true
    systemctl reset-failed "$API_CANARY_UNIT" >/dev/null 2>&1 || true
    API_CANARY_UNIT=""
    API_CANARY_PID=""
  fi
}

stop_api_candidate_canary_strict() {
  local unit="$API_CANARY_UNIT" pid="$API_CANARY_PID" attempt
  [ -n "$unit" ] && [ -n "$pid" ] && [ "$pid" -ge 2 ] \
    || fail "API gateway canary identity was lost before strict shutdown"
  systemctl is-active --quiet "$unit" \
    || fail "API gateway canary is not active immediately before strict shutdown"
  systemctl stop "$unit" || fail "could not stop API gateway canary $unit"
  for attempt in $(seq 1 50); do
    if ! systemctl is-active --quiet "$unit" \
        && [ ! -e "/proc/$pid" ] \
        && ! tcp_listen_port_present "$API_CANARY_PORT"; then
      systemctl reset-failed "$unit" >/dev/null 2>&1 || true
      assert_exact_uid_processes "$API_SERVICE_USER" \
        || fail "API service identity retained a process after canary shutdown"
      API_CANARY_UNIT=""
      API_CANARY_PID=""
      say "API gateway canary is inactive and port $API_CANARY_PORT is released"
      return 0
    fi
    sleep 0.1
  done
  fail "API gateway canary shutdown was not complete"
}

stop_candidate_canary_strict() {
  local unit="$CANARY_UNIT" pid="$CANARY_PID" port attempt
  [ -n "$unit" ] && [ -n "$pid" ] && [ "$pid" -ge 2 ] \
    || fail "MCP canary identity was lost before strict shutdown"
  systemctl is-active --quiet "$unit" \
    || fail "MCP canary is not active immediately before strict shutdown"
  port=$MCP_CANARY_PORT
  systemctl stop "$unit" || fail "could not stop MCP canary $unit"
  for attempt in $(seq 1 50); do
    if ! systemctl is-active --quiet "$unit" \
        && [ ! -e "/proc/$pid" ] \
        && ! tcp_listen_port_present "$port"; then
      systemctl reset-failed "$unit" >/dev/null 2>&1 || true
      assert_exact_uid_processes "$MCP_SERVICE_USER" \
        || fail "MCP service identity retained a process after canary shutdown"
      CANARY_UNIT=""
      CANARY_PID=""
      say "precommit canary is inactive, its PID is gone, and port $port is released"
      return 0
    fi
    sleep 0.1
  done
  fail "MCP canary shutdown was not complete; refusing durable commit"
}

# The journal implementation is deliberately embedded in this script. Recovery
# must work on the first immutable migration, before any candidate checkout or
# previously installed helper can be trusted. JSON is parsed as data and is
# never sourced/eval'd by the shell.
journal_action() {  # journal_action <operation> [operation arguments...]
  local operation="$1"
  shift
  trusted_python - "$operation" "$TX_ROOT" "$CURRENT_LINK" "$PREVIOUS_LINK" \
    "$NGINX_ENABLED" "$SERVICE_ENABLED" "$API_SERVICE_ENABLED" \
    "$UNIT" "$API_UNIT" "$DROPIN" "$NGINX_AVAILABLE" "$MCP_ENV" "$API_ENV" \
    "$SECRETS" "$RELEASE_ROOT" "$MCP_KEY_STATE" "$VERIFIER_STATE_ROOT" \
    "$VERIFIER_CREDENTIAL_ROOT" "$LEGACY_VERIFIER_ENV" "$@" <<'PY'
from __future__ import annotations

import hashlib
import hmac
import grp
import json
import os
import re
import shlex
import shutil
import signal
import stat
import sys
import uuid


operation = sys.argv[1]
root = os.path.abspath(sys.argv[2])
pointer_paths = {
    "current": os.path.abspath(sys.argv[3]),
    "previous": os.path.abspath(sys.argv[4]),
    "nginx_enabled": os.path.abspath(sys.argv[5]),
    "service_enabled": os.path.abspath(sys.argv[6]),
    "api_service_enabled": os.path.abspath(sys.argv[7]),
}
file_paths = {
    "unit": os.path.abspath(sys.argv[8]),
    "api_unit": os.path.abspath(sys.argv[9]),
    "dropin": os.path.abspath(sys.argv[10]),
    "nginx": os.path.abspath(sys.argv[11]),
    "mcp_env": os.path.abspath(sys.argv[12]),
    "api_env": os.path.abspath(sys.argv[13]),
    "secrets": os.path.abspath(sys.argv[14]),
}
release_root = os.path.abspath(sys.argv[15])
rotation_state_path = os.path.abspath(sys.argv[16])
verifier_state_root = os.path.abspath(sys.argv[17])
verifier_credential_root = os.path.abspath(sys.argv[18])
legacy_verifier_env = os.path.abspath(sys.argv[19])
extra = sys.argv[20:]
active_path = os.path.join(root, "active")
allowed_backups = set(file_paths)
allowed_evidence = {
    "manifest.json", "commit-intent.json", "finalized.json", "recovery.json"
} | allowed_backups
sha_re = re.compile(r"[0-9a-f]{40}")
hash_re = re.compile(r"[0-9a-f]{64}")
service_key_re = re.compile(r"tw_svc_[A-Za-z0-9_-]{43}")
service_key_assignment_re = re.compile(
    r"^\s*(?:export\s+)?MCP_GATEWAY_KEY\s*=(.*)$"
)
platform_assignment_re = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)
state_re = re.compile(r"(?:\.new|committed|recovered|gc)-([0-9a-f-]{36})")
fsync_count = 0
write_count = 0
kill_event_counts: dict[str, int] = {}


def die(message: str) -> None:
    raise SystemExit(f"release journal: {message}")


def journal_kill_event(kind: str) -> None:
    count = kill_event_counts.get(kind, 0) + 1
    kill_event_counts[kind] = count
    requested = os.environ.get("TW_MCP_TEST_KILL_JOURNAL_AT", "")
    if requested == f"{kind}:{count}":
        os.kill(os.getpid(), signal.SIGKILL)


def durable_fsync(fd: int) -> None:
    global fsync_count
    fsync_count += 1
    requested = os.environ.get("TW_MCP_TEST_FAIL_JOURNAL_FSYNC_AT", "")
    if requested:
        try:
            fail_at = int(requested)
        except ValueError:
            die("invalid journal fsync failure seam")
        if fail_at <= 0:
            die("invalid journal fsync failure seam")
        if fsync_count == fail_at:
            raise OSError("injected durable journal fsync failure")
    os.fsync(fd)
    journal_kill_event("fsync")


def durable_write(fd: int, payload: memoryview) -> int:
    global write_count
    write_count += 1
    requested = os.environ.get("TW_MCP_TEST_FAIL_JOURNAL_WRITE_AT", "")
    if requested:
        try:
            fail_at = int(requested)
        except ValueError:
            die("invalid journal write failure seam")
        if fail_at <= 0:
            die("invalid journal write failure seam")
        if write_count == fail_at:
            raise OSError("injected durable journal write failure")
    written = os.write(fd, payload)
    journal_kill_event("write")
    return written


def journal_rename(source: str, destination: str) -> None:
    os.rename(source, destination)
    journal_kill_event("rename")


def journal_replace(source: str, destination: str) -> None:
    os.replace(source, destination)
    journal_kill_event("replace")


def journal_unlink(path: str) -> None:
    os.unlink(path)
    journal_kill_event("unlink")


def journal_rmdir(path: str) -> None:
    os.rmdir(path)
    journal_kill_event("rmdir")


def fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        durable_fsync(fd)
    finally:
        os.close(fd)


def safe_text(value: object, label: str, *, absolute: bool = False) -> str:
    if not isinstance(value, str) or any(c in value for c in "\x00\r\n\t"):
        die(f"invalid {label}")
    if absolute and (not value or not os.path.isabs(value) or os.path.normpath(value) != value):
        die(f"invalid absolute {label}")
    return value


def safe_uuid(value: object, label: str = "transaction id") -> str:
    try:
        parsed = str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        die(f"invalid {label}")
    if parsed != value:
        die(f"noncanonical {label}")
    return parsed


def nonnegative_int(value: object, label: str) -> int:
    # bool is an int subclass in Python; accepting True as uid/gid/mode would
    # weaken the exact journal schema and make JSON type confusion possible.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        die(f"invalid {label}")
    return value


def inspect_directory(path: str, mode: int, label: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        die(f"cannot inspect {label}: {exc}")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        die(f"{label} is not a real directory")
    if metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != mode:
        die(f"{label} must be root:root mode {mode:04o}")
    return metadata


def ensure_root(create: bool) -> bool:
    if os.path.lexists(root):
        inspect_directory(root, 0o700, "journal root")
        return True
    if not create:
        return False
    parent = os.path.dirname(root)
    try:
        parent_meta = os.lstat(parent)
    except OSError as exc:
        die(f"cannot inspect journal parent: {exc}")
    if (
        not stat.S_ISDIR(parent_meta.st_mode)
        or stat.S_ISLNK(parent_meta.st_mode)
        or parent_meta.st_uid != 0
        or parent_meta.st_mode & 0o022
    ):
        die("journal parent is not root-controlled")
    try:
        os.mkdir(root, 0o700)
        os.chown(root, 0, 0)
        os.chmod(root, 0o700)
        fsync_dir(parent)
    except OSError as exc:
        die(f"cannot create journal root: {exc}")
    inspect_directory(root, 0o700, "journal root")
    return True


def read_fd_all(fd: int, limit: int = 64 * 1024 * 1024) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, limit + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            die("journal input is too large")
    return b"".join(chunks)


def read_regular(path: str, *, require_root_copy: bool = False) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        die(f"cannot open regular file {path}: {exc}")
    try:
        opened = os.fstat(fd)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            die(f"unsafe regular file {path}")
        if require_root_copy and (
            opened.st_uid != 0
            or opened.st_gid != 0
            or stat.S_IMODE(opened.st_mode) != 0o600
        ):
            die(f"journal file is not root:root mode 0600: {path}")
        return read_fd_all(fd), opened
    finally:
        os.close(fd)


def write_root_file(path: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.fchown(fd, 0, 0)
            view = memoryview(payload)
            while view:
                written = durable_write(fd, view)
                view = view[written:]
            durable_fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        die(f"cannot write durable journal file {path}: {exc}")


def write_atomic_root_file(txdir: str, name: str, payload: bytes, txid: str) -> None:
    """Publish an authority-changing marker with no partial final name."""
    if name not in {"commit-intent.json", "finalized.json", "recovery.json"}:
        die("invalid atomic journal marker name")
    final = os.path.join(txdir, name)
    temporary = os.path.join(txdir, f".{name}.tmp-{txid}")
    if os.path.lexists(final) or os.path.lexists(temporary):
        die(f"journal marker already exists: {name}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(temporary, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.fchown(fd, 0, 0)
            view = memoryview(payload)
            while view:
                written = durable_write(fd, view)
                view = view[written:]
            durable_fsync(fd)
        finally:
            os.close(fd)
        journal_replace(temporary, final)
        fsync_dir(txdir)
    except BaseException:
        # A kill leaves only the recognizable temporary. Reconcile removes it
        # before interpreting authority on the next controller invocation.
        raise


def snapshot_file(path: str, txdir: str, label: str) -> dict[str, object]:
    record: dict[str, object] = {"path": path, "exists": False, "backup": None,
                                "sha256": None, "mode": None, "uid": None, "gid": None,
                                "parent_exists": os.path.lexists(os.path.dirname(path))}
    if record["parent_exists"]:
        ensure_parent(path)
    if not os.path.lexists(path):
        return record
    try:
        named = os.lstat(path)
    except OSError as exc:
        die(f"cannot inspect live file {path}: {exc}")
    if not stat.S_ISREG(named.st_mode) or stat.S_ISLNK(named.st_mode):
        die(f"refusing non-regular live file {path}")
    payload, opened = read_regular(path)
    backup = label
    write_root_file(os.path.join(txdir, backup), payload)
    record.update(
        exists=True,
        backup=backup,
        sha256=hashlib.sha256(payload).hexdigest(),
        mode=stat.S_IMODE(opened.st_mode),
        uid=opened.st_uid,
        gid=opened.st_gid,
    )
    return record


def snapshot_pointer(path: str) -> dict[str, object]:
    record: dict[str, object] = {"path": path, "exists": False, "target": None,
                                "uid": None, "gid": None}
    if not os.path.lexists(path):
        return record
    metadata = os.lstat(path)
    if not stat.S_ISLNK(metadata.st_mode):
        die(f"journal pointer is not a symlink: {path}")
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        die(f"journal pointer must be root:root: {path}")
    target = safe_text(os.readlink(path), f"pointer target for {path}")
    after = os.lstat(path)
    if (metadata.st_dev, metadata.st_ino) != (after.st_dev, after.st_ino):
        die(f"journal pointer changed while being captured: {path}")
    if not target:
        die(f"empty pointer target for {path}")
    record.update(exists=True, target=target, uid=metadata.st_uid, gid=metadata.st_gid)
    return record


def validate_file_record(label: str, record: object, txdir: str) -> dict[str, object]:
    fields = {"path", "exists", "backup", "sha256", "mode", "uid", "gid", "parent_exists"}
    if not isinstance(record, dict) or set(record) != fields or record.get("path") != file_paths[label]:
        die(f"invalid file record {label}")
    existed = record.get("exists")
    if not isinstance(existed, bool):
        die(f"invalid exists flag for {label}")
    if not isinstance(record.get("parent_exists"), bool):
        die(f"invalid parent-exists flag for {label}")
    if existed and not record["parent_exists"]:
        die(f"existing file has an absent parent: {label}")
    backup_path = os.path.join(txdir, label)
    if not existed:
        if any(record.get(key) is not None for key in ("backup", "sha256", "mode", "uid", "gid")):
            die(f"absent file record carries metadata: {label}")
        if os.path.lexists(backup_path):
            die(f"absent file record has a backup: {label}")
        return record
    if record.get("backup") != label or not hash_re.fullmatch(str(record.get("sha256", ""))):
        die(f"invalid backup binding for {label}")
    for key in ("mode", "uid", "gid"):
        nonnegative_int(record.get(key), f"backup {key} for {label}")
    if record["mode"] & ~0o7777:
        die(f"invalid backup mode for {label}")
    payload, _ = read_regular(backup_path, require_root_copy=True)
    if hashlib.sha256(payload).hexdigest() != record["sha256"]:
        die(f"backup digest mismatch for {label}")
    return record


def validate_pointer_record(label: str, record: object) -> dict[str, object]:
    fields = {"path", "exists", "target", "uid", "gid"}
    if not isinstance(record, dict) or set(record) != fields or record.get("path") != pointer_paths[label]:
        die(f"invalid pointer record {label}")
    existed = record.get("exists")
    if not isinstance(existed, bool):
        die(f"invalid pointer exists flag for {label}")
    if not existed:
        if any(record.get(key) is not None for key in ("target", "uid", "gid")):
            die(f"absent pointer record carries metadata: {label}")
        return record
    safe_text(record.get("target"), f"pointer target {label}")
    if not record["target"]:
        die(f"invalid pointer metadata for {label}")
    for key in ("uid", "gid"):
        nonnegative_int(record.get(key), f"pointer {key} for {label}")
    if record["uid"] != 0 or record["gid"] != 0:
        die(f"journal pointer must be root:root: {label}")
    if label in {"current", "previous"}:
        if not re.fullmatch(r"releases/mcp-[0-9a-f]{40}", record["target"]):
            die(f"release pointer target is not canonical: {label}")
    elif label == "nginx_enabled" and record["target"] != file_paths["nginx"]:
        die("nginx enabled pointer does not store the canonical available path")
    elif label == "service_enabled" and record["target"] not in {
        "../tradewave-mcpserver.service",
        "/etc/systemd/system/tradewave-mcpserver.service",
    }:
        die("service enabled pointer does not store the canonical unit target")
    elif label == "api_service_enabled" and record["target"] not in {
        "../tradewave-apiserver.service",
        "/etc/systemd/system/tradewave-apiserver.service",
    }:
        die("API enabled pointer does not store the canonical unit target")
    return record


def capture_live_file(label: str) -> dict[str, object]:
    path = file_paths[label]
    payload, metadata = read_regular(path)
    expected_mode = 0o600 if label in {"mcp_env", "api_env"} else (0o640 if label == "secrets" else 0o644)
    expected_gid = grp.getgrnam("flask").gr_gid if label == "secrets" else 0
    if (
        metadata.st_uid != 0
        or metadata.st_gid != expected_gid
        or stat.S_IMODE(metadata.st_mode) != expected_mode
    ):
        die(f"candidate live file metadata is invalid: {label}")
    return {
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "mode": expected_mode,
        "uid": 0,
        "gid": expected_gid,
    }


def validate_live_file_record(label: str, record: object) -> dict[str, object]:
    fields = {"path", "sha256", "mode", "uid", "gid"}
    if not isinstance(record, dict) or set(record) != fields or record.get("path") != file_paths[label]:
        die(f"invalid candidate live file record: {label}")
    if not hash_re.fullmatch(str(record.get("sha256", ""))):
        die(f"invalid candidate live file digest: {label}")
    for key in ("mode", "uid", "gid"):
        nonnegative_int(record.get(key), f"candidate live {key} for {label}")
    expected_mode = 0o600 if label in {"mcp_env", "api_env"} else (0o640 if label == "secrets" else 0o644)
    expected_gid = grp.getgrnam("flask").gr_gid if label == "secrets" else 0
    if record["mode"] != expected_mode or record["uid"] != 0 or record["gid"] != expected_gid:
        die(f"invalid candidate live file metadata: {label}")
    return record


def capture_live_pointer(label: str) -> dict[str, object]:
    record = snapshot_pointer(pointer_paths[label])
    if not record["exists"]:
        die(f"candidate live pointer is absent: {label}")
    validate_pointer_record(label, record)
    return record


def verify_live_file(label: str, record: dict[str, object]) -> None:
    payload, metadata = read_regular(file_paths[label])
    if (
        hashlib.sha256(payload).hexdigest() != record["sha256"]
        or stat.S_IMODE(metadata.st_mode) != record["mode"]
        or metadata.st_uid != record["uid"]
        or metadata.st_gid != record["gid"]
    ):
        die(f"committed candidate live file changed: {label}")


def verify_live_pointer(label: str, record: dict[str, object]) -> None:
    current = snapshot_pointer(pointer_paths[label])
    validate_pointer_record(label, current)
    if current != record:
        die(f"committed candidate live pointer changed: {label}")


def load_manifest(txdir: str) -> dict[str, object]:
    inspect_directory(txdir, 0o700, "transaction directory")
    manifest_path = os.path.join(txdir, "manifest.json")
    raw, _ = read_regular(manifest_path, require_root_copy=True)
    if len(raw) > 65536:
        die("manifest is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("manifest is invalid JSON")
    if not isinstance(value, dict) or set(value) != {
        "version", "txid", "candidate", "entry", "gateway_entry", "files", "pointers"
    }:
        die("manifest schema is invalid")
    if type(value.get("version")) is not int or value.get("version") != 4:
        die("manifest version is unsupported")
    txid = safe_uuid(value.get("txid"))
    candidate = value.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"bundle", "sha"}:
        die("candidate manifest is invalid")
    candidate_sha = safe_text(candidate.get("sha"), "candidate sha")
    if not sha_re.fullmatch(candidate_sha):
        die("candidate sha is invalid")
    candidate_bundle = safe_text(candidate.get("bundle"), "candidate bundle", absolute=True)
    if candidate_bundle != os.path.join(release_root, f"mcp-{candidate_sha}"):
        die("candidate bundle does not match its sha")
    def validate_entry(entry: object, *, gateway: bool) -> dict[str, object]:
        label = "gateway entry" if gateway else "MCP entry"
        if not isinstance(entry, dict) or set(entry) != {
            "kind", "policy", "bundle", "sha", "cwd", "command", "argv_sha256", "active"
        }:
            die(f"{label} manifest is invalid")
        kind = entry.get("kind")
        if kind not in {"sealed", "legacy", "absent"}:
            die(f"{label} kind is invalid")
        if not isinstance(entry.get("active"), bool):
            die(f"{label} active state is invalid")
        policy = entry.get("policy")
        cwd = safe_text(entry.get("cwd"), f"{label} cwd", absolute=True)
        command = safe_text(entry.get("command"), f"{label} command", absolute=True)
        if not hash_re.fullmatch(str(entry.get("argv_sha256", ""))):
            die(f"{label} argv digest is invalid")
        if kind == "sealed":
            allowed = {"fenced"} if gateway else {"fenced", "sealed-unfenced"}
            if policy not in allowed or entry["active"] is not True:
                die(f"sealed {label} runtime policy/state is invalid")
            entry_sha = safe_text(entry.get("sha"), f"{label} sha")
            if not sha_re.fullmatch(entry_sha):
                die(f"{label} sha is invalid")
            entry_bundle = safe_text(entry.get("bundle"), f"{label} bundle", absolute=True)
            if entry_bundle != os.path.join(release_root, f"mcp-{entry_sha}"):
                die(f"{label} bundle does not match its sha")
            expected_cwd = os.path.join(entry_bundle, "src") if gateway else "/"
            expected_command = os.path.join(
                pointer_paths["current"],
                "gateway-venv" if gateway else "venv",
                "bin",
                "python",
            )
            if cwd != expected_cwd or command != expected_command:
                die(f"sealed {label} process identity is not exact")
        elif kind == "absent":
            if (
                policy != "absent"
                or entry.get("bundle") != ""
                or entry.get("sha") != ""
                or cwd != "/"
                or command != "/nonexistent"
                or entry.get("argv_sha256") != "0" * 64
                or entry["active"] is not False
            ):
                die(f"absent {label} identity is invalid")
        else:
            expected_command = (
                "/home/flask/venv-api/bin/python3"
                if gateway else "/home/flask/venv-api/bin/python"
            )
            if (
                policy != "legacy"
                or entry.get("bundle") != ""
                or entry.get("sha") != ""
                or cwd != "/home/flask"
                or command != expected_command
                or entry["active"] is not True
            ):
                die(f"legacy {label} identity is invalid")
        return entry

    value["entry"] = validate_entry(value.get("entry"), gateway=False)
    value["gateway_entry"] = validate_entry(value.get("gateway_entry"), gateway=True)
    files = value.get("files")
    pointers = value.get("pointers")
    if not isinstance(files, dict) or set(files) != set(file_paths):
        die("manifest file set is invalid")
    if not isinstance(pointers, dict) or set(pointers) != set(pointer_paths):
        die("manifest pointer set is invalid")
    for label in file_paths:
        validate_file_record(label, files[label], txdir)
    for label in pointer_paths:
        validate_pointer_record(label, pointers[label])
    expected_children = {"manifest.json"} | {
        label for label, record in files.items() if record["exists"]
    }
    actual_children = set(os.listdir(txdir))
    marker_sets = (
        set(),
        {"commit-intent.json"},
        {"commit-intent.json", "finalized.json"},
        {"recovery.json"},
    )
    if not expected_children.issubset(actual_children) or actual_children - expected_children not in marker_sets:
        die("transaction directory has unexpected or missing evidence")
    for name in actual_children - expected_children:
        metadata = os.lstat(os.path.join(txdir, name))
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            die(f"journal marker is unsafe: {name}")
    value["txid"] = txid
    return value


def load_rotation_state(
    *, allow_absent: bool = False
) -> tuple[dict[str, object] | None, str | None]:
    if not os.path.lexists(rotation_state_path):
        if allow_absent:
            return None, None
        die("required service-key rotation state is absent")
    raw, metadata = read_regular(rotation_state_path)
    if (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or len(raw) > 8192
    ):
        die("service-key rotation state metadata is unsafe")
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("service-key rotation state is invalid JSON")
    fields = {
        "version", "status", "replacement_key_id", "replacement_key_hash",
        "superseded_key_id", "superseded_key_hash", "source_key_hash",
    }
    if (
        not isinstance(state, dict)
        or set(state) != fields
        or type(state.get("version")) is not int
        or state.get("version") != 2
        or state.get("status") not in {"pending", "active"}
    ):
        die("service-key rotation state schema/status is invalid")
    safe_uuid(state.get("replacement_key_id"), "replacement key id")
    if not hash_re.fullmatch(str(state.get("replacement_key_hash", ""))):
        die("service-key rotation replacement hash is invalid")
    if not hash_re.fullmatch(str(state.get("source_key_hash", ""))):
        die("service-key rotation source hash is invalid")
    if (state.get("superseded_key_id") is None) != (state.get("superseded_key_hash") is None):
        die("service-key rotation superseded binding is incomplete")
    if state.get("superseded_key_id") is not None:
        safe_uuid(state["superseded_key_id"], "superseded key id")
        if not hash_re.fullmatch(str(state.get("superseded_key_hash", ""))):
            die("service-key rotation superseded hash is invalid")
    if state["status"] == "active" and state.get("superseded_key_id") is not None:
        die("active service-key rotation state retains a superseded binding")
    canonical = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if raw != canonical:
        die("service-key rotation state is not canonical JSON")
    return state, hashlib.sha256(raw).hexdigest()


def load_environment_service_key(path: str, label: str) -> str | None:
    """Read the one service-key assignment using the provisioner's syntax.

    Recovery evidence never stores the raw key.  It does, however, prove that
    the restored runtime source has exactly the credential whose digest is
    recorded in the marker.  This prevents an absent rotation-state file from
    being mistaken for a safe legacy rollback when the restored K0 is missing
    or conflicts with a dedicated environment.
    """
    if not os.path.lexists(path):
        return None
    raw, _metadata = read_regular(path)
    if len(raw) > 2 * 1024 * 1024:
        die(f"{label} is too large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        die(f"{label} is not valid UTF-8")
    values: list[str] = []
    for line in lines:
        match = service_key_assignment_re.fullmatch(line)
        if match is None:
            continue
        lexer = shlex.shlex(match.group(1), posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            decoded = list(lexer)
        except ValueError:
            die(f"{label} has a malformed MCP_GATEWAY_KEY assignment")
        if (
            len(decoded) != 1
            or any(character in decoded[0] for character in ("\x00", "\r", "\n"))
            or not service_key_re.fullmatch(decoded[0])
        ):
            die(f"{label} has an invalid MCP_GATEWAY_KEY assignment")
        values.append(decoded[0])
    if len(values) > 1:
        die(f"{label} has duplicate MCP_GATEWAY_KEY assignments")
    return values[0] if values else None


def load_platform_hmac_secret() -> str:
    raw, _metadata = read_regular(file_paths["secrets"])
    if len(raw) > 2 * 1024 * 1024:
        die("platform secrets is too large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        die("platform secrets is not valid UTF-8")
    values = {"API_KEY_HMAC_SECRET": [], "APPSERVER_JWT_SECRET": []}
    for line in lines:
        match = platform_assignment_re.fullmatch(line)
        if match is None or match.group(1) not in values:
            continue
        lexer = shlex.shlex(match.group(2), posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            decoded = list(lexer)
        except ValueError:
            die(f"platform secrets has a malformed {match.group(1)} assignment")
        if len(decoded) != 1 or any(
            character in decoded[0] for character in ("\x00", "\r", "\n")
        ):
            die(f"platform secrets has an invalid {match.group(1)} assignment")
        values[match.group(1)].append(decoded[0])
    for name, assignments in values.items():
        if len(assignments) > 1:
            die(f"platform secrets has duplicate {name} assignments")
    secret = (
        values["API_KEY_HMAC_SECRET"][0]
        if values["API_KEY_HMAC_SECRET"]
        else values["APPSERVER_JWT_SECRET"][0]
        if values["APPSERVER_JWT_SECRET"]
        else ""
    )
    if not secret:
        die("platform secrets lacks API_KEY_HMAC_SECRET/APPSERVER_JWT_SECRET")
    return secret


def service_key_hash(raw_key: str) -> str:
    return hmac.new(
        load_platform_hmac_secret().encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def active_credential_record() -> dict[str, object]:
    state, state_digest = load_rotation_state()
    assert state is not None and state_digest is not None
    if state["status"] != "active":
        die("dedicated service-key state is not active")
    broad_key = load_environment_service_key(file_paths["secrets"], "platform secrets")
    if broad_key is not None:
        die("active dedicated service key still exists in broad platform secrets")
    runtime_key = load_environment_service_key(
        file_paths["mcp_env"], "dedicated MCP environment"
    )
    if runtime_key is None:
        die("active service-key state lacks its dedicated runtime credential")
    if service_key_hash(runtime_key) != state["replacement_key_hash"]:
        die("dedicated runtime credential does not match active rotation state")
    return {
        "state_kind": "active",
        "replacement_key_id": state["replacement_key_id"],
        "replacement_key_hash": state["replacement_key_hash"],
        "rotation_state_sha256": state_digest,
    }


def recovered_credential_record(manifest: dict[str, object]) -> dict[str, object]:
    entry_kind = manifest["entry"]["kind"]
    if entry_kind == "sealed":
        return active_credential_record()
    if entry_kind not in {"legacy", "absent"}:
        die("recovery has an unknown MCP entry credential policy")
    if load_rotation_state(allow_absent=True) != (None, None):
        die("legacy/absent recovery retained service-key rotation state")
    broad_key = load_environment_service_key(file_paths["secrets"], "platform secrets")
    runtime_key = load_environment_service_key(
        file_paths["mcp_env"], "dedicated MCP environment"
    )
    if runtime_key is not None and runtime_key != broad_key:
        die("restored dedicated and broad legacy credentials conflict")
    if broad_key is not None:
        return {
            "state_kind": "legacy-broad",
            "replacement_key_id": None,
            "replacement_key_hash": service_key_hash(broad_key),
            "rotation_state_sha256": None,
        }
    if runtime_key is not None:
        die("restored dedicated credential has no rotation state or broad source")
    if entry_kind == "legacy":
        die("restored legacy MCP entry lacks its broad service credential")
    return {
        "state_kind": "source-absent",
        "replacement_key_id": None,
        "replacement_key_hash": None,
        "rotation_state_sha256": None,
    }


def verifier_root_safe(path: str, label: str) -> None:
    if not os.path.lexists(path):
        return
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or os.listdir(path)
    ):
        die(f"{label} must be absent or an exact empty root:root mode 0700 directory")
    return


def verifier_absence_record(txid: str) -> dict[str, object]:
    if os.path.lexists(legacy_verifier_env):
        die("legacy permanent verifier credential still exists")
    state_path = os.path.join(verifier_state_root, f"{txid}.json")
    credential_path = os.path.join(verifier_credential_root, txid, "verify-env")
    if os.path.lexists(state_path) or os.path.lexists(credential_path):
        die("transaction verifier sidecar or credential source still exists")
    verifier_root_safe(verifier_state_root, "verifier state root")
    verifier_root_safe(verifier_credential_root, "verifier credential root")
    return {
        "state_root_absent_or_exact_empty": True,
        "credential_root_absent_or_exact_empty": True,
        "transaction_artifacts_absent": True,
        "legacy_env_absent": True,
    }


def load_intent(txdir: str, manifest: dict[str, object]) -> dict[str, object]:
    path = os.path.join(txdir, "commit-intent.json")
    raw, _ = read_regular(path, require_root_copy=True)
    if len(raw) > 65536:
        die("commit intent is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("commit intent is invalid JSON")
    fields = {"version", "txid", "candidate", "files", "pointers", "credentials"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or type(value.get("version")) is not int
        or value.get("version") != 4
    ):
        die("commit intent schema is invalid")
    if safe_uuid(value.get("txid")) != manifest["txid"]:
        die("commit intent transaction id does not match manifest")
    if value.get("candidate") != manifest["candidate"]:
        die("commit intent candidate does not match manifest")
    files = value.get("files")
    pointers = value.get("pointers")
    if not isinstance(files, dict) or set(files) != set(file_paths):
        die("commit evidence file set is invalid")
    if not isinstance(pointers, dict) or set(pointers) != set(pointer_paths):
        die("commit evidence pointer set is invalid")
    for label in file_paths:
        validate_live_file_record(label, files[label])
    for label in pointer_paths:
        record = validate_pointer_record(label, pointers[label])
        if not record["exists"]:
            die(f"committed candidate pointer is absent: {label}")
    credentials = value.get("credentials")
    if not isinstance(credentials, dict) or set(credentials) != {
        "replacement_key_id", "replacement_key_hash"
    }:
        die("commit intent credential binding is invalid")
    safe_uuid(credentials.get("replacement_key_id"), "intent replacement key id")
    if not hash_re.fullmatch(str(credentials.get("replacement_key_hash", ""))):
        die("commit intent replacement key hash is invalid")
    return value


def load_authority_marker(
    txdir: str, manifest: dict[str, object], intent: dict[str, object] | None, name: str
) -> dict[str, object]:
    path = os.path.join(txdir, name)
    raw, _ = read_regular(path, require_root_copy=True)
    if len(raw) > 65536:
        die(f"{name} is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die(f"{name} is invalid JSON")
    if not isinstance(value, dict) or set(value) != {
        "version", "txid", "candidate", "credentials", "verifier"
    } or type(value.get("version")) is not int or value.get("version") != 4:
        die(f"{name} schema is invalid")
    if safe_uuid(value.get("txid")) != manifest["txid"] or value.get("candidate") != manifest["candidate"]:
        die(f"{name} transaction/candidate binding is invalid")
    credentials = value.get("credentials")
    if not isinstance(credentials, dict) or set(credentials) != {
        "state_kind", "replacement_key_id", "replacement_key_hash", "rotation_state_sha256"
    }:
        die(f"{name} credential evidence is invalid")
    expected_credentials = (
        active_credential_record()
        if intent is not None
        else recovered_credential_record(manifest)
    )
    if credentials != expected_credentials:
        die(f"{name} service-key evidence drifted")
    if intent is not None and {
        "replacement_key_id": credentials["replacement_key_id"],
        "replacement_key_hash": credentials["replacement_key_hash"],
    } != intent["credentials"]:
        die(f"{name} differs from commit-intent credential binding")
    verifier = value.get("verifier")
    current_absence = verifier_absence_record(manifest["txid"])
    if verifier != current_absence:
        die(f"{name} verifier-absence evidence drifted")
    canonical = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if raw != canonical:
        die(f"{name} is not canonical JSON")
    return value


def verify_committed_live(intent: dict[str, object]) -> None:
    for label, record in intent["files"].items():
        verify_live_file(label, record)
    for label, record in intent["pointers"].items():
        verify_live_pointer(label, record)


def discard_subset_tree(path: str, label: str) -> None:
    """Idempotently discard an already non-authoritative journal directory.

    The directory must first be in .new/recovered/gc state. Its children may be
    any subset of the fixed evidence names because SIGKILL can land after any
    unlink. Each unlink is itself made durable before the next one.
    """
    inspect_directory(path, 0o700, label)
    for name in os.listdir(path):
        if name not in allowed_evidence:
            die(f"{label} has an unexpected child")
        metadata = os.lstat(os.path.join(path, name))
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            die(f"{label} child is unsafe")
    for name in sorted(os.listdir(path)):
        journal_unlink(os.path.join(path, name))
        fsync_dir(path)
    journal_rmdir(path)
    fsync_dir(root)


def ensure_parent(path: str) -> str:
    parent = os.path.dirname(path)
    metadata = os.lstat(parent)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
    ):
        die(f"live parent is not root-controlled: {parent}")
    return parent


def cleanup_restore_temporary(
    parent: str,
    name: str,
    *,
    symlink: bool,
    allowed_gids: frozenset[int] = frozenset({0}),
) -> None:
    path = os.path.join(parent, name)
    if os.path.lexists(path):
        metadata = os.lstat(path)
        expected_type = stat.S_ISLNK(metadata.st_mode) if symlink else stat.S_ISREG(metadata.st_mode)
        if (
            not expected_type
            or metadata.st_uid != 0
            or metadata.st_gid not in allowed_gids
            or metadata.st_nlink != 1
        ):
            die(f"unsafe restore temporary: {path}")
        journal_unlink(path)
        fsync_dir(parent)


def restore_file(record: dict[str, object], txdir: str, txid: str) -> None:
    path = record["path"]
    parent = os.path.dirname(path)
    # Two managed files share /etc/tradewave. Bind the temporary name to the
    # destination basename so a crash after fchown of secrets.env cannot be
    # mistaken for the root:root mcpserver.env temporary on retry.
    temporary_name = f".{os.path.basename(path)}.mcp-journal-restore-{txid}"
    if not record["exists"]:
        if not os.path.lexists(parent):
            if record["parent_exists"]:
                die(f"live parent disappeared during restore: {parent}")
            return
        ensure_parent(path)
        cleanup_restore_temporary(parent, temporary_name, symlink=False)
        if os.path.lexists(path):
            metadata = os.lstat(path)
            if stat.S_ISDIR(metadata.st_mode):
                die(f"refusing to remove directory at live file path: {path}")
            journal_unlink(path)
            fsync_dir(parent)
        if not record["parent_exists"]:
            if os.listdir(parent):
                die(f"new live parent is not empty during restore: {parent}")
            grandparent = os.path.dirname(parent)
            ensure_parent(parent)
            journal_rmdir(parent)
            fsync_dir(grandparent)
        return
    parent = ensure_parent(path)
    cleanup_restore_temporary(
        parent,
        temporary_name,
        symlink=False,
        allowed_gids=frozenset({0, record["gid"]}),
    )
    payload, _ = read_regular(os.path.join(txdir, record["backup"]), require_root_copy=True)
    temporary = os.path.join(parent, temporary_name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = durable_write(fd, view)
            view = view[written:]
        os.fchmod(fd, record["mode"])
        os.fchown(fd, record["uid"], record["gid"])
        durable_fsync(fd)
    except BaseException:
        os.close(fd)
        if os.path.lexists(temporary):
            journal_unlink(temporary)
            fsync_dir(parent)
        raise
    else:
        os.close(fd)
    journal_replace(temporary, path)
    fsync_dir(parent)


def restore_pointer(record: dict[str, object], txid: str) -> None:
    path = record["path"]
    parent = ensure_parent(path)
    temporary_name = f".mcp-journal-link-{txid}"
    cleanup_restore_temporary(parent, temporary_name, symlink=True)
    if not record["exists"]:
        if os.path.lexists(path):
            metadata = os.lstat(path)
            if stat.S_ISDIR(metadata.st_mode):
                die(f"refusing to remove directory at pointer path: {path}")
            journal_unlink(path)
            fsync_dir(parent)
        return
    temporary = os.path.join(parent, temporary_name)
    os.symlink(record["target"], temporary)
    os.lchown(temporary, record["uid"], record["gid"])
    journal_replace(temporary, path)
    fsync_dir(parent)


def verify_restored(manifest: dict[str, object], txdir: str) -> None:
    for label, record in manifest["files"].items():
        path = record["path"]
        if not record["exists"]:
            if os.path.lexists(path):
                die(f"absent file was not restored: {label}")
            if not record["parent_exists"] and os.path.lexists(os.path.dirname(path)):
                die(f"absent parent was not restored: {label}")
            continue
        payload, metadata = read_regular(path)
        if (
            hashlib.sha256(payload).hexdigest() != record["sha256"]
            or stat.S_IMODE(metadata.st_mode) != record["mode"]
            or metadata.st_uid != record["uid"]
            or metadata.st_gid != record["gid"]
        ):
            die(f"restored file verification failed: {label}")
    for label, record in manifest["pointers"].items():
        path = record["path"]
        if not record["exists"]:
            if os.path.lexists(path):
                die(f"absent pointer was not restored: {label}")
            continue
        metadata = os.lstat(path)
        if (
            not stat.S_ISLNK(metadata.st_mode)
            or os.readlink(path) != record["target"]
            or metadata.st_uid != record["uid"]
            or metadata.st_gid != record["gid"]
        ):
            die(f"restored pointer verification failed: {label}")


def print_manifest_mode(mode: str, txdir: str, manifest: dict[str, object]) -> None:
    entry = manifest["entry"]
    gateway_entry = manifest["gateway_entry"]
    candidate = manifest["candidate"]
    for item in (
        mode,
        txdir,
        candidate["bundle"],
        candidate["sha"],
        entry["kind"],
        entry["policy"],
        entry["bundle"],
        entry["sha"],
        entry["cwd"],
        entry["command"],
        entry["argv_sha256"],
        gateway_entry["kind"],
        gateway_entry["policy"],
        gateway_entry["bundle"],
        gateway_entry["sha"],
        gateway_entry["cwd"],
        gateway_entry["command"],
        gateway_entry["argv_sha256"],
    ):
        print(item)


if operation == "prepare":
    if len(extra) != 17:
        die("prepare argument count is invalid")
    txid = safe_uuid(extra[0])
    candidate_bundle = safe_text(extra[1], "candidate bundle", absolute=True)
    candidate_sha = safe_text(extra[2], "candidate sha")
    entry_kind = extra[3]
    entry_policy = extra[4]
    entry_bundle = safe_text(extra[5], "entry bundle")
    entry_sha = safe_text(extra[6], "entry sha")
    entry_cwd = safe_text(extra[7], "entry cwd", absolute=True)
    entry_command = safe_text(extra[8], "entry command", absolute=True)
    entry_argv_sha256 = safe_text(extra[9], "entry argv sha256")
    gateway_kind = extra[10]
    gateway_policy = extra[11]
    gateway_bundle = safe_text(extra[12], "gateway entry bundle")
    gateway_sha = safe_text(extra[13], "gateway entry sha")
    gateway_cwd = safe_text(extra[14], "gateway entry cwd", absolute=True)
    gateway_command = safe_text(extra[15], "gateway entry command", absolute=True)
    gateway_argv_sha256 = safe_text(extra[16], "gateway entry argv sha256")
    if not hash_re.fullmatch(entry_argv_sha256):
        die("prepare entry argv digest is invalid")
    if not sha_re.fullmatch(candidate_sha) or candidate_bundle != os.path.join(release_root, f"mcp-{candidate_sha}"):
        die("prepare candidate identity is invalid")
    if entry_kind == "sealed":
        if entry_policy not in {"fenced", "sealed-unfenced"}:
            die("prepare sealed entry runtime policy is invalid")
        safe_text(entry_bundle, "entry bundle", absolute=True)
        if (
            not sha_re.fullmatch(entry_sha)
            or entry_bundle != os.path.join(release_root, f"mcp-{entry_sha}")
            or entry_cwd != "/"
            or entry_command != os.path.join(pointer_paths["current"], "venv", "bin", "python")
        ):
            die("prepare sealed entry identity is invalid")
    elif entry_kind == "legacy":
        if entry_policy != "legacy":
            die("prepare legacy entry runtime policy is invalid")
        if entry_bundle or entry_sha:
            die("prepare legacy entry identity is invalid")
        if entry_cwd != "/home/flask" or entry_command != "/home/flask/venv-api/bin/python":
            die("prepare legacy process identity is not the supported baseline")
    elif entry_kind == "absent":
        if (
            entry_policy != "absent"
            or entry_bundle
            or entry_sha
            or entry_cwd != "/"
            or entry_command != "/nonexistent"
            or entry_argv_sha256 != "0" * 64
        ):
            die("prepare absent entry identity is invalid")
    else:
        die("prepare entry kind is invalid")
    if not hash_re.fullmatch(gateway_argv_sha256):
        die("prepare gateway entry argv digest is invalid")
    if gateway_kind == "sealed":
        if gateway_policy != "fenced":
            die("prepare sealed gateway policy is invalid")
        safe_text(gateway_bundle, "gateway entry bundle", absolute=True)
        if (
            not sha_re.fullmatch(gateway_sha)
            or gateway_bundle != os.path.join(release_root, f"mcp-{gateway_sha}")
            or gateway_cwd != os.path.join(gateway_bundle, "src")
            or gateway_command != os.path.join(
                pointer_paths["current"], "gateway-venv", "bin", "python"
            )
        ):
            die("prepare sealed gateway identity is invalid")
    elif gateway_kind == "legacy":
        if (
            gateway_policy != "legacy"
            or gateway_bundle
            or gateway_sha
            or gateway_cwd != "/home/flask"
            or gateway_command != "/home/flask/venv-api/bin/python3"
        ):
            die("prepare legacy gateway identity is invalid")
    elif gateway_kind == "absent":
        if (
            gateway_policy != "absent"
            or gateway_bundle
            or gateway_sha
            or gateway_cwd != "/"
            or gateway_command != "/nonexistent"
            or gateway_argv_sha256 != "0" * 64
        ):
            die("prepare absent gateway identity is invalid")
    else:
        die("prepare gateway entry kind is invalid")
    ensure_root(True)
    if os.listdir(root):
        die("journal root is not empty before prepare")
    txdir = os.path.join(root, f".new-{txid}")
    os.mkdir(txdir, 0o700)
    os.chown(txdir, 0, 0)
    os.chmod(txdir, 0o700)
    files = {label: snapshot_file(path, txdir, label) for label, path in file_paths.items()}
    pointers = {label: snapshot_pointer(path) for label, path in pointer_paths.items()}
    manifest = {
        "version": 4,
        "txid": txid,
        "candidate": {"bundle": candidate_bundle, "sha": candidate_sha},
        "entry": {
            "kind": entry_kind,
            "policy": entry_policy,
            "bundle": entry_bundle,
            "sha": entry_sha,
            "cwd": entry_cwd,
            "command": entry_command,
            "argv_sha256": entry_argv_sha256,
            "active": entry_kind != "absent",
        },
        "gateway_entry": {
            "kind": gateway_kind,
            "policy": gateway_policy,
            "bundle": gateway_bundle,
            "sha": gateway_sha,
            "cwd": gateway_cwd,
            "command": gateway_command,
            "argv_sha256": gateway_argv_sha256,
            "active": gateway_kind != "absent",
        },
        "files": files,
        "pointers": pointers,
    }
    payload = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    write_root_file(os.path.join(txdir, "manifest.json"), payload)
    fsync_dir(txdir)
    if os.path.lexists(active_path):
        die("active journal appeared during prepare")
    journal_rename(txdir, active_path)
    fsync_dir(root)
    print(active_path)
elif operation in {"inspect", "reconcile"}:
    if extra:
        die(f"{operation} takes no extra arguments")
    if not ensure_root(False):
        print("none")
        raise SystemExit(0)
    names = os.listdir(root)
    for name in names:
        if name == "active":
            continue
        match = state_re.fullmatch(name)
        if match is None:
            die(f"unexpected journal-root entry: {name}")
        safe_uuid(match.group(1), "journal directory transaction id")
    new_names = [name for name in names if name.startswith(".new-")]
    recovered_names = [name for name in names if name.startswith("recovered-")]
    gc_names = [name for name in names if name.startswith("gc-")]
    committed_names = [name for name in names if name.startswith("committed-")]
    active_names = [name for name in names if name == "active"]
    # active does not carry its UUID in the name; the validated manifest binds it.
    if "active" in names:
        active_names = ["active"]
    if len(names) > 1:
        die("multiple/coexisting durable journal states exist")
    if new_names or gc_names:
        name = (new_names or gc_names)[0]
        if operation == "reconcile":
            discard_subset_tree(os.path.join(root, name), "discardable transaction")
            print("none")
        else:
            die("discardable journal state requires reconciliation")
    elif recovered_names:
        path = os.path.join(root, recovered_names[0])
        manifest = load_manifest(path)
        if recovered_names[0] != f"recovered-{manifest['txid']}":
            die("recovered journal name does not match manifest")
        print_manifest_mode("recovered", path, manifest)
    elif committed_names:
        path = os.path.join(root, committed_names[0])
        manifest = load_manifest(path)
        if committed_names[0] != f"committed-{manifest['txid']}":
            die("committed journal name does not match manifest")
        intent = load_intent(path, manifest)
        load_authority_marker(path, manifest, intent, "finalized.json")
        verify_committed_live(intent)
        print_manifest_mode("committed", path, manifest)
    elif active_names:
        if operation == "reconcile":
            for name in sorted(os.listdir(active_path)):
                match = re.fullmatch(
                    r"\.(?:commit-intent|finalized|recovery)\.json\.tmp-([0-9a-f-]{36})",
                    name,
                )
                if match is None:
                    continue
                safe_uuid(match.group(1), "journal marker temporary transaction id")
                temporary = os.path.join(active_path, name)
                metadata = os.lstat(temporary)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid != 0
                    or metadata.st_gid != 0
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_nlink != 1
                ):
                    die("unsafe journal marker temporary")
                journal_unlink(temporary)
                fsync_dir(active_path)
        manifest = load_manifest(active_path)
        children = set(os.listdir(active_path))
        if "commit-intent.json" in children:
            intent = load_intent(active_path, manifest)
            verify_committed_live(intent)
            if "finalized.json" in children:
                load_authority_marker(
                    active_path, manifest, intent, "finalized.json"
                )
            print_manifest_mode("finalizing", active_path, manifest)
        elif "recovery.json" in children:
            load_authority_marker(
                active_path, manifest, None, "recovery.json"
            )
            print_manifest_mode("recovering", active_path, manifest)
        else:
            print_manifest_mode("active", active_path, manifest)
    elif not new_names and not recovered_names and not gc_names:
        print("none")
elif operation == "restore":
    if extra:
        die("restore takes no arguments")
    ensure_root(False) or die("journal root is missing during restore")
    manifest = load_manifest(active_path)
    if set(os.listdir(active_path)) & {
        "commit-intent.json", "finalized.json", "recovery.json"
    }:
        die("authority-changing journal cannot enter rollback restore")
    # load_manifest validates the complete manifest and every backup before the
    # first live mutation. The shell stops MCP before invoking this operation.
    for record in manifest["pointers"].values():
        restore_pointer(record, manifest["txid"])
    # The stable installer-owned fence remains active throughout. Restore every
    # environment/edge/drop-in file before the replaceable base unit as a second
    # defense against reboot or manual-start observation of a partial rollback.
    for label, record in manifest["files"].items():
        if label not in {"unit", "api_unit"}:
            restore_file(record, active_path, manifest["txid"])
    restore_file(manifest["files"]["api_unit"], active_path, manifest["txid"])
    restore_file(manifest["files"]["unit"], active_path, manifest["txid"])
    verify_restored(manifest, active_path)
    print_manifest_mode("active", active_path, manifest)
elif operation == "prepare-commit":
    if len(extra) != 2:
        die("prepare-commit argument count is invalid")
    ensure_root(False) or die("journal root is missing at commit intent")
    manifest = load_manifest(active_path)
    if manifest["candidate"] != {"bundle": extra[0], "sha": extra[1]}:
        die("commit-intent candidate does not match active journal")
    if set(os.listdir(active_path)) & {
        "commit-intent.json", "finalized.json", "recovery.json"
    }:
        die("commit-intent marker already exists or conflicts")
    current = capture_live_pointer("current")
    if current["target"] != f"releases/mcp-{manifest['candidate']['sha']}":
        die("current pointer does not select the committed candidate")
    rotation, _rotation_digest = load_rotation_state()
    intent = {
        "version": 4,
        "txid": manifest["txid"],
        "candidate": manifest["candidate"],
        "files": {label: capture_live_file(label) for label in file_paths},
        "pointers": {
            label: current if label == "current" else capture_live_pointer(label)
            for label in pointer_paths
        },
        "credentials": {
            "replacement_key_id": rotation["replacement_key_id"],
            "replacement_key_hash": rotation["replacement_key_hash"],
        },
    }
    payload = (json.dumps(intent, sort_keys=True, separators=(",", ":")) + "\n").encode()
    write_atomic_root_file(
        active_path, "commit-intent.json", payload, manifest["txid"]
    )
    load_intent(active_path, manifest)
    print(active_path)
elif operation == "mark-finalized":
    if extra:
        die("mark-finalized takes no arguments")
    ensure_root(False) or die("journal root is missing at finalization")
    manifest = load_manifest(active_path)
    intent = load_intent(active_path, manifest)
    if os.path.lexists(os.path.join(active_path, "finalized.json")):
        load_authority_marker(
            active_path, manifest, intent, "finalized.json"
        )
        print(active_path)
        raise SystemExit(0)
    credentials = active_credential_record()
    if {
        "replacement_key_id": credentials["replacement_key_id"],
        "replacement_key_hash": credentials["replacement_key_hash"],
    } != intent["credentials"]:
        die("service-key finalization does not match commit intent")
    marker = {
        "version": 4,
        "txid": manifest["txid"],
        "candidate": manifest["candidate"],
        "credentials": credentials,
        "verifier": verifier_absence_record(manifest["txid"]),
    }
    payload = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    write_atomic_root_file(active_path, "finalized.json", payload, manifest["txid"])
    load_authority_marker(active_path, manifest, intent, "finalized.json")
    print(active_path)
elif operation == "commit":
    if len(extra) != 2:
        die("commit argument count is invalid")
    ensure_root(False) or die("journal root is missing at commit")
    manifest = load_manifest(active_path)
    if manifest["candidate"] != {"bundle": extra[0], "sha": extra[1]}:
        die("commit candidate does not match active journal")
    intent = load_intent(active_path, manifest)
    load_authority_marker(active_path, manifest, intent, "finalized.json")
    verify_committed_live(intent)
    destination = os.path.join(root, f"committed-{manifest['txid']}")
    if os.path.lexists(destination):
        die("committed journal destination already exists")
    journal_rename(active_path, destination)
    fsync_dir(root)
    print(destination)
elif operation == "mark-recovered":
    if extra:
        die("mark-recovered takes no arguments")
    ensure_root(False) or die("journal root is missing during recovery close")
    manifest = load_manifest(active_path)
    if set(os.listdir(active_path)) & {"commit-intent.json", "finalized.json"}:
        die("roll-forward journal cannot be marked recovered")
    verify_restored(manifest, active_path)
    marker_path = os.path.join(active_path, "recovery.json")
    if not os.path.lexists(marker_path):
        credentials = recovered_credential_record(manifest)
        marker = {
            "version": 4,
            "txid": manifest["txid"],
            "candidate": manifest["candidate"],
            "credentials": credentials,
            "verifier": verifier_absence_record(manifest["txid"]),
        }
        payload = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
        write_atomic_root_file(
            active_path, "recovery.json", payload, manifest["txid"]
        )
    load_authority_marker(active_path, manifest, None, "recovery.json")
    destination = os.path.join(root, f"recovered-{manifest['txid']}")
    if os.path.lexists(destination):
        die("recovered journal destination already exists")
    journal_rename(active_path, destination)
    fsync_dir(root)
    print(destination)
elif operation == "cleanup-recovered":
    if len(extra) != 1:
        die("cleanup-recovered argument count is invalid")
    ensure_root(False) or die("journal root is missing during recovered cleanup")
    path = os.path.abspath(extra[0])
    if os.path.dirname(path) != root or not os.path.basename(path).startswith("recovered-"):
        die("refusing unexpected recovered cleanup path")
    manifest = load_manifest(path)
    if os.path.basename(path) != f"recovered-{manifest['txid']}":
        die("recovered cleanup path does not match manifest")
    load_authority_marker(path, manifest, None, "recovery.json")
    verify_restored(manifest, path)
    destination = os.path.join(root, f"gc-{manifest['txid']}")
    if os.path.lexists(destination):
        die("recovered journal GC destination already exists")
    journal_rename(path, destination)
    fsync_dir(root)
    discard_subset_tree(destination, "recovered transaction GC")
elif operation == "verify-committed-live":
    if len(extra) != 1:
        die("verify-committed-live argument count is invalid")
    ensure_root(False) or die("journal root is missing during committed verification")
    path = os.path.abspath(extra[0])
    if os.path.dirname(path) != root or not os.path.basename(path).startswith("committed-"):
        die("refusing unexpected committed verification path")
    manifest = load_manifest(path)
    if os.path.basename(path) != f"committed-{manifest['txid']}":
        die("committed verification path does not match manifest")
    intent = load_intent(path, manifest)
    load_authority_marker(path, manifest, intent, "finalized.json")
    verify_committed_live(intent)
elif operation == "cleanup":
    if len(extra) != 1:
        die("cleanup argument count is invalid")
    ensure_root(False) or die("journal root is missing during cleanup")
    path = os.path.abspath(extra[0])
    if os.path.dirname(path) != root or not os.path.basename(path).startswith("committed-"):
        die("refusing unexpected committed cleanup path")
    manifest = load_manifest(path)
    if os.path.basename(path) != f"committed-{manifest['txid']}":
        die("committed cleanup path does not match manifest")
    intent = load_intent(path, manifest)
    load_authority_marker(path, manifest, intent, "finalized.json")
    verify_committed_live(intent)
    destination = os.path.join(root, f"gc-{manifest['txid']}")
    if os.path.lexists(destination):
        die("committed journal GC destination already exists")
    journal_rename(path, destination)
    fsync_dir(root)
    discard_subset_tree(destination, "committed transaction GC")
else:
    die("unknown journal operation")
PY
}

process_argv_sha256() {  # <pid>
  trusted_python - "$1" <<'PY'
import hashlib
import pathlib
import sys

raw = pathlib.Path(f"/proc/{int(sys.argv[1])}/cmdline").read_bytes()
if not raw or not raw.endswith(b"\0"):
    raise SystemExit("process command line is empty or malformed")
print(hashlib.sha256(raw).hexdigest())
PY
}

verify_exact_legacy_cmdline() {  # <pid>
  trusted_python - "$1" <<'PY'
import pathlib
import sys

raw = pathlib.Path(f"/proc/{int(sys.argv[1])}/cmdline").read_bytes()
argv = [part.decode("utf-8") for part in raw.split(b"\0") if part]
expected = [
    "/home/flask/venv-api/bin/python", "-m", "mcpserver.server",
    "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "9090",
]
if argv != expected:
    raise SystemExit(f"legacy MCP argv differs from reviewed predecessor: {argv!r}")
PY
}

verify_legacy_service_policy() {
  local fragment dropins exec_start
  cmp -s "$TRUSTED_LEGACY_UNIT" "$UNIT" \
    || fail "legacy MCP unit bytes differ from the exact reviewed VM predecessor"
  cmp -s "$TRUSTED_FENCE_TEMPLATE" "$FENCE_DROPIN" \
    || fail "legacy MCP unit lacks the exact stable release fence"
  [ "$(stat -c '%U:%G %a' "$UNIT")" = "root:root 644" ] \
    && [ "$(stat -c '%U:%G %a' "$FENCE_DROPIN")" = "root:root 644" ] \
    || fail "legacy MCP unit/fence metadata is unsafe"
  fragment=$(systemctl show tradewave-mcpserver.service --property=FragmentPath --value)
  dropins=$(systemctl show tradewave-mcpserver.service --property=DropInPaths --value)
  [ "$fragment" = "$UNIT" ] && [ "$dropins" = "$FENCE_DROPIN" ] \
    || fail "legacy MCP effective fragment/drop-in set is not exact"
  while IFS='|' read -r name expected; do
    [ "$(systemctl show tradewave-mcpserver.service --property="$name" --value)" = "$expected" ] \
      || fail "legacy MCP effective $name differs from the reviewed predecessor"
  done <<'EOF'
User|flask
Group|flask
Type|simple
WorkingDirectory|/home/flask
NoNewPrivileges|yes
ProtectSystem|full
EnvironmentFiles|/etc/tradewave/secrets.env (ignore_errors=no)
Restart|on-failure
RestartUSec|3s
StandardOutput|append
StandardError|append
EOF
  exec_start=$(systemctl show tradewave-mcpserver.service --property=ExecStart --value)
  [[ "$exec_start" = *"path=/home/flask/venv-api/bin/python"* ]] \
    && [[ "$exec_start" = *'argv[]=/home/flask/venv-api/bin/python -m mcpserver.server --transport ${TW2_MCP_TRANSPORT} --host ${TW2_MCP_HOST} --port ${TW2_MCP_PORT}'* ]] \
    || fail "legacy MCP effective ExecStart differs from the reviewed predecessor"
  [ "$(systemctl is-enabled tradewave-mcpserver.service)" = enabled ] \
    && [ -L "$SERVICE_ENABLED" ] \
    && [ "$(readlink "$SERVICE_ENABLED")" = "/etc/systemd/system/tradewave-mcpserver.service" ] \
    || fail "legacy MCP reboot activation differs from the reviewed VM predecessor"
}

verify_legacy_process_identity() {  # <cwd> <command> <argv-sha256>
  local expected_cwd="$1" expected_command="$2" expected_argv_sha="$3" pid cwd command
  systemctl is-active --quiet tradewave-mcpserver || return 1
  verify_legacy_service_policy || return 1
  pid=$(systemctl show tradewave-mcpserver --property=MainPID --value)
  [ -n "$pid" ] && [ "$pid" -ge 2 ] || return 1
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
  command=$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null | head -1 || true)
  [ "$cwd" = "$expected_cwd" ] && [ "$command" = "$expected_command" ] \
    && verify_exact_legacy_cmdline "$pid" \
    && [ "$(process_argv_sha256 "$pid")" = "$expected_argv_sha" ]
}

verify_legacy_api_service_policy() {
  local exec_start fragment dropins name
  local -a dropin_files conditions privileged
  cmp -s "$TRUSTED_LEGACY_API_UNIT" "$API_UNIT" \
    || fail "legacy API gateway unit differs from the reviewed predecessor"
  cmp -s "$TRUSTED_API_FENCE_TEMPLATE" "$API_FENCE_DROPIN" \
    || fail "legacy API gateway lacks the stable release fence"
  [ "$(stat -c '%U:%G %a' "$API_UNIT")" = "root:root 644" ] \
    && [ "$(stat -c '%U:%G %a' "$API_FENCE_DROPIN")" = "root:root 644" ] \
    || fail "legacy API gateway unit/fence metadata is unsafe"
  fragment=$(systemctl show tradewave-apiserver --property=FragmentPath --value)
  dropins=$(systemctl show tradewave-apiserver --property=DropInPaths --value)
  [ "$fragment" = "$API_UNIT" ] && [ "$dropins" = "$API_FENCE_DROPIN" ] \
    || fail "legacy API gateway effective fragment/drop-in set is not exact"
  mapfile -t dropin_files < <(find "$(dirname "$API_FENCE_DROPIN")" -mindepth 1 -maxdepth 1 -printf '%p\n' | sort)
  [ "${#dropin_files[@]}" -eq 1 ] && [ "${dropin_files[0]}" = "$API_FENCE_DROPIN" ] \
    || fail "legacy API gateway has an unexpected drop-in"
  mapfile -t conditions < <(
    systemctl cat tradewave-apiserver.service --no-pager \
      | sed -n -E 's/^[[:space:]]*(ExecCondition=.*)$/\1/p'
  )
  [ "${#conditions[@]}" -eq 1 ] \
    && [ "${conditions[0]}" = 'ExecCondition=+/usr/bin/python3.13 -I -B -S /usr/local/libexec/tradewave-mcp-start-guard.py /var/lib/tradewave/mcp-release-transactions/active /run/lock/tradewave/mcp-release.lock' ] \
    || fail "legacy API gateway does not have the one exact stable start fence"
  mapfile -t privileged < <(
    systemctl cat tradewave-apiserver.service --no-pager \
      | sed -n -E 's/^[[:space:]]*(Exec[A-Za-z]*=\+.*)$/\1/p'
  )
  [ "${#privileged[@]}" -eq 1 ] && [ "${privileged[0]}" = "${conditions[0]}" ] \
    || fail "legacy API gateway has an unexpected privileged command"
  while IFS='|' read -r name expected; do
    [ "$(systemctl show tradewave-apiserver --property="$name" --value)" = "$expected" ] \
      || fail "legacy API gateway effective $name differs from reviewed predecessor"
  done <<EOF
User|flask
Group|flask
Type|notify
WorkingDirectory|/home/flask
EnvironmentFiles|/etc/tradewave/secrets.env (ignore_errors=no)
NoNewPrivileges|yes
ProtectSystem|full
Restart|on-failure
RestartUSec|3s
EOF
  exec_start=$(systemctl show tradewave-apiserver --property=ExecStart --value)
  [[ "$exec_start" = *"path=/home/flask/venv-api/bin/gunicorn"* ]] \
    && [[ "$exec_start" = *'argv[]=/home/flask/venv-api/bin/gunicorn --workers 4 --worker-class gthread --threads 12 --timeout 120 --keep-alive 75 --bind ${TW2_APISERVER_BIND} --access-logfile /var/log/tradewave/apiserver.access.log --error-logfile /var/log/tradewave/apiserver.error.log --capture-output apiserver.app:app'* ]] \
    || fail "legacy API gateway effective ExecStart differs from reviewed predecessor"
  for name in ExecStartPre ExecStartPost ExecReload ExecStop ExecStopPost; do
    [ -z "$(systemctl show tradewave-apiserver --property="$name" --value)" ] \
      || fail "legacy API gateway has forbidden $name commands"
  done
  [ "$(systemctl is-enabled tradewave-apiserver.service)" = enabled ] \
    && [ -L "$API_SERVICE_ENABLED" ] \
    && [ "$(stat -c '%U:%G %h' "$API_SERVICE_ENABLED")" = "root:root 1" ] \
    && { [ "$(readlink "$API_SERVICE_ENABLED")" = "../tradewave-apiserver.service" ] \
      || [ "$(readlink "$API_SERVICE_ENABLED")" = "/etc/systemd/system/tradewave-apiserver.service" ]; } \
    || fail "legacy API gateway reboot activation differs from reviewed predecessor"
}

verify_legacy_api_process_identity() {  # <cwd> <command> <argv-sha256>
  local expected_cwd="$1" expected_command="$2" expected_argv_sha="$3" raw_pids main
  systemctl is-active --quiet tradewave-apiserver || return 1
  verify_legacy_api_service_policy || return 1
  main=$(systemctl show tradewave-apiserver --property=MainPID --value)
  [ -n "$main" ] && [ "$main" -ge 2 ] || return 1
  raw_pids=$(service_cgroup_pids tradewave-apiserver.service)
  read -r -a legacy_api_pids <<< "$raw_pids"
  [ "${#legacy_api_pids[@]}" -eq 5 ] || return 1
  trusted_python - "$expected_cwd" "$expected_command" "$expected_argv_sha" \
    "$main" "${legacy_api_pids[@]}" <<'PY'
import os
import pathlib
import sys

cwd, command, argv_sha, main, *raw_pids = sys.argv[1:]
pids = {int(value) for value in raw_pids}
if int(main) not in pids:
    raise SystemExit("legacy API MainPID is outside service cgroup")
expected = [
    "/home/flask/venv-api/bin/python3",
    "/home/flask/venv-api/bin/gunicorn",
    "--workers", "4", "--worker-class", "gthread", "--threads", "12",
    "--timeout", "120", "--keep-alive", "75", "--bind", "127.0.0.1:8088",
    "--access-logfile", "/var/log/tradewave/apiserver.access.log",
    "--error-logfile", "/var/log/tradewave/apiserver.error.log",
    "--capture-output", "apiserver.app:app",
]
for pid in pids:
    process = pathlib.Path(f"/proc/{pid}")
    raw = (process / "cmdline").read_bytes()
    argv = [value.decode() for value in raw.split(b"\0") if value]
    if os.path.realpath(process / "cwd") != cwd or argv[0] != command:
        raise SystemExit("legacy API process cwd/command drifted")
    if argv != expected:
        raise SystemExit(f"legacy API process argv is not the reviewed loopback predecessor: {argv!r}")
    if __import__("hashlib").sha256(raw).hexdigest() != argv_sha:
        raise SystemExit("legacy API process argv drifted")
PY
}

start_legacy_recovery_canaries() {  # <entry-argv-sha> <gateway-argv-sha>
  local entry_argv_sha="$1" gateway_argv_sha="$2" raw_pids attempt url
  API_CANARY_UNIT="tradewave-api-legacy-recovery-$TXID.service"
  CANARY_UNIT="tradewave-mcp-legacy-recovery-$TXID.service"
  assert_paired_ports_free
  /usr/bin/systemd-run --quiet --collect --service-type=notify --unit="$API_CANARY_UNIT" \
    --description="TradeWave reviewed legacy API recovery canary" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$DEPLOY_UNIT" --property=User=flask --property=Group=flask \
    --property=SupplementaryGroups= --property=WorkingDirectory=/home/flask \
    --property=Environment=TW2_APISERVER_BIND=127.0.0.1:8088 \
    --property="EnvironmentFile=$SECRETS" --property=Environment=PYTHONPATH=/home/flask \
    --property=NoNewPrivileges=yes --property=ProtectSystem=full \
    --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
    --property=ProtectControlGroups=yes --property=RestrictSUIDSGID=yes \
    --property=LockPersonality=yes --property=Restart=no \
    --property=KillMode=control-group --property=TimeoutStopSec=10s \
    /home/flask/venv-api/bin/gunicorn --workers 4 --worker-class gthread \
      --threads 12 --timeout 120 --keep-alive 75 --bind 127.0.0.1:8088 \
      --access-logfile /var/log/tradewave/apiserver.access.log \
      --error-logfile /var/log/tradewave/apiserver.error.log \
      --capture-output apiserver.app:app
  for attempt in $(seq 1 50); do
    raw_pids=$(service_cgroup_pids "$API_CANARY_UNIT")
    read -r -a legacy_api_canary_pids <<< "$raw_pids"
    [ "${#legacy_api_canary_pids[@]}" -eq 5 ] && break
    sleep 0.1
  done
  [ "${#legacy_api_canary_pids[@]}" -eq 5 ] \
    || fail "reviewed legacy API canary did not create one master/four workers"
  API_CANARY_PID=$(systemctl show "$API_CANARY_UNIT" --property=MainPID --value)
  [ "$(systemctl show "$API_CANARY_UNIT" --property=User --value)" = flask ] \
    && [ "$(systemctl show "$API_CANARY_UNIT" --property=Group --value)" = flask ] \
    && [ "$(systemctl show "$API_CANARY_UNIT" --property=WorkingDirectory --value)" = /home/flask ] \
    && [ "$(systemctl show "$API_CANARY_UNIT" --property=NoNewPrivileges --value)" = yes ] \
    && [ "$(systemctl show "$API_CANARY_UNIT" --property=ProtectSystem --value)" = full ] \
    || fail "reviewed legacy API canary policy differs from fixed predecessor"
  trusted_python - "$gateway_argv_sha" "${legacy_api_canary_pids[@]}" <<'PY'
import hashlib
import os
import pathlib
import sys

expected_hash, *raw_pids = sys.argv[1:]
expected = [
    "/home/flask/venv-api/bin/python3", "/home/flask/venv-api/bin/gunicorn",
    "--workers", "4", "--worker-class", "gthread", "--threads", "12",
    "--timeout", "120", "--keep-alive", "75", "--bind", "127.0.0.1:8088",
    "--access-logfile", "/var/log/tradewave/apiserver.access.log",
    "--error-logfile", "/var/log/tradewave/apiserver.error.log",
    "--capture-output", "apiserver.app:app",
]
for raw_pid in raw_pids:
    pid = int(raw_pid)
    process = pathlib.Path(f"/proc/{pid}")
    raw = (process / "cmdline").read_bytes()
    argv = [item.decode() for item in raw.split(b"\0") if item]
    if argv != expected or os.path.realpath(process / "cwd") != "/home/flask":
        raise SystemExit(f"legacy API canary identity drifted: {argv!r}")
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise SystemExit("legacy API canary argv differs from journal entry")
PY
  verify_loopback_listener_owners 8088 "${legacy_api_canary_pids[@]}"
  curl --noproxy '*' --fail --silent --show-error --connect-timeout 1 --max-time 3 \
    http://127.0.0.1:8088/healthz >/dev/null \
    || fail "reviewed legacy API recovery canary health gate failed"

  /usr/bin/systemd-run --quiet --collect --service-type=exec --unit="$CANARY_UNIT" \
    --description="TradeWave reviewed legacy MCP recovery canary" \
    --property="BindsTo=$DEPLOY_UNIT" --property="PartOf=$DEPLOY_UNIT" \
    --property="After=$API_CANARY_UNIT" --property=User=flask --property=Group=flask \
    --property=SupplementaryGroups= --property=WorkingDirectory=/home/flask \
    --property=Environment=API_BASE_URL=http://127.0.0.1:8088/v1 \
    --property=Environment=TW2_MCP_HOST=127.0.0.1 \
    --property=Environment=TW2_MCP_PORT=9090 \
    --property=Environment=TW2_MCP_TRANSPORT=streamable-http \
    --property="EnvironmentFile=$SECRETS" --property=Environment=PYTHONPATH=/home/flask \
    --property=NoNewPrivileges=yes --property=ProtectSystem=full \
    --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
    --property=ProtectControlGroups=yes --property=RestrictSUIDSGID=yes \
    --property=LockPersonality=yes --property=Restart=no \
    --property=KillMode=control-group --property=TimeoutStopSec=10s \
    /home/flask/venv-api/bin/python -m mcpserver.server \
      --transport streamable-http --host 127.0.0.1 --port 9090
  CANARY_PID=$(systemctl show "$CANARY_UNIT" --property=MainPID --value)
  [ -n "$CANARY_PID" ] && [ "$CANARY_PID" -ge 2 ] \
    || fail "reviewed legacy MCP recovery canary has no MainPID"
  [ "$(systemctl show "$CANARY_UNIT" --property=User --value)" = flask ] \
    && [ "$(systemctl show "$CANARY_UNIT" --property=Group --value)" = flask ] \
    && [ "$(systemctl show "$CANARY_UNIT" --property=WorkingDirectory --value)" = /home/flask ] \
    && [ "$(systemctl show "$CANARY_UNIT" --property=NoNewPrivileges --value)" = yes ] \
    && [ "$(systemctl show "$CANARY_UNIT" --property=ProtectSystem --value)" = full ] \
    && verify_exact_legacy_cmdline "$CANARY_PID" \
    && [ "$(process_argv_sha256 "$CANARY_PID")" = "$entry_argv_sha" ] \
    || fail "reviewed legacy MCP canary identity/policy differs from journal entry"
  for attempt in $(seq 1 50); do
    if verify_loopback_listener_owners 9090 "$CANARY_PID" 2>/dev/null; then break; fi
    systemctl is-active --quiet "$CANARY_UNIT" \
      || fail "reviewed legacy MCP recovery canary exited during readiness"
    sleep 0.1
  done
  verify_loopback_listener_owners 9090 "$CANARY_PID" \
    || fail "reviewed legacy MCP recovery canary did not bind loopback port 9090"

  url=$(public_url)
  run_verifier "$CANDIDATE_BUNDLE" contract "$url" --legacy-smoke
  run_verifier "$CANDIDATE_BUNDLE" load "$url" \
    --clients 20 --timeout 20 --phase-max-seconds 5 \
    --whoami-p95-max-seconds 2 --whoami-max-seconds 3 \
    --session-p95-max-seconds 12 --session-max-seconds 15 --legacy-smoke
}

stop_legacy_recovery_canaries_strict() {
  local unit
  for unit in "$CANARY_UNIT" "$API_CANARY_UNIT"; do
    [ -n "$unit" ] || fail "legacy recovery canary unit identity was lost"
    systemctl stop "$unit" || fail "could not stop legacy recovery canary $unit"
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  done
  CANARY_UNIT=""; CANARY_PID=""; API_CANARY_UNIT=""; API_CANARY_PID=""
  assert_paired_ports_free
}

journal_state_txid() {  # <validated-journal-directory>
  trusted_python - "$1/manifest.json" <<'PY'
import json
import os
import re
import stat
import sys

path = os.path.abspath(sys.argv[1])
metadata = os.lstat(path)
if (
    not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0 or metadata.st_gid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1
):
    raise SystemExit("journal manifest metadata is unsafe")
raw = open(path, "rb").read(1024 * 1024 + 1)
if len(raw) > 1024 * 1024:
    raise SystemExit("journal manifest is oversized")
value = json.loads(raw.decode("utf-8"))
txid = value.get("txid") if isinstance(value, dict) else None
if not isinstance(txid, str) or re.fullmatch(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", txid
) is None:
    raise SystemExit("journal transaction id is not a canonical UUIDv4")
print(txid)
PY
}

stop_persistent_pair_for_recovery() {  # <gateway-entry-kind>
  local gateway_kind="$1"
  # Dependency direction is gateway -> MCP, so shutdown is the reverse:
  # stop MCP first, then the gateway, before taking both exclusive fences.
  systemctl stop tradewave-mcpserver.service 2>/dev/null \
    || ! systemctl is-active --quiet tradewave-mcpserver.service \
    || fail "could not stop persistent MCP during paired recovery"
  systemctl stop tradewave-apiserver.service 2>/dev/null \
    || ! systemctl is-active --quiet tradewave-apiserver.service \
    || fail "could not stop persistent API gateway during paired recovery"
  ! systemctl is-active --quiet tradewave-mcpserver.service \
    && ! systemctl is-active --quiet tradewave-apiserver.service \
    || fail "persistent API/MCP pair remained active during recovery stop"
  assert_exact_uid_processes "$MCP_SERVICE_USER" \
    || fail "paired recovery stop left an MCP service-identity process"
  if [ "$gateway_kind" = sealed ]; then
    assert_exact_uid_processes "$API_SERVICE_USER" \
      || fail "paired recovery stop left an API service-identity process"
  fi
  acquire_runtime_lock_exclusive
  acquire_api_runtime_lock_exclusive
  assert_paired_ports_free
}

verify_restored_pair_policy() {  # <MCP kind> <MCP policy> <gateway kind>
  local entry_kind="$1" entry_policy="$2" gateway_kind="$3"
  case "$entry_kind" in
    sealed)
      verify_installed_service_policy "$entry_policy"
      verify_service_enabled
      ;;
    legacy)
      verify_legacy_service_policy
      ;;
    absent)
      [ ! -e "$UNIT" ] && [ ! -L "$UNIT" ] \
        && [ ! -e "$SERVICE_ENABLED" ] && [ ! -L "$SERVICE_ENABLED" ] \
        && ! systemctl is-active --quiet tradewave-mcpserver.service \
        || fail "restored absent MCP component is not exact"
      ;;
    *) fail "restored pair has an unknown MCP entry kind" ;;
  esac
  case "$gateway_kind" in
    sealed)
      verify_installed_api_service_policy
      verify_api_service_enabled
      ;;
    legacy)
      verify_legacy_api_service_policy
      ;;
    absent)
      [ ! -e "$API_UNIT" ] && [ ! -L "$API_UNIT" ] \
        && [ ! -e "$API_SERVICE_ENABLED" ] && [ ! -L "$API_SERVICE_ENABLED" ] \
        && ! systemctl is-active --quiet tradewave-apiserver.service \
        || fail "restored absent API gateway component is not exact"
      ;;
    *) fail "restored pair has an unknown API gateway entry kind" ;;
  esac
}

start_and_verify_recovered_pair() {  # 14 entry/gateway identity arguments
  local entry_kind="$1" entry_policy="$2" entry_bundle="$3" entry_sha="$4"
  local entry_cwd="$5" entry_command="$6" entry_argv_sha="$7"
  local gateway_kind="$8" gateway_policy="$9" gateway_bundle="${10}" gateway_sha="${11}"
  local gateway_cwd="${12}" gateway_command="${13}" gateway_argv_sha="${14}" pid
  : "$gateway_policy"

  # Startup follows the dependency direction: exact gateway first, MCP second.
  release_api_runtime_lock
  case "$gateway_kind" in
    sealed)
      systemctl start tradewave-apiserver.service
      verify_sealed_bundle "$gateway_bundle" "$gateway_sha"
      verify_running_api_bundle "$gateway_bundle" "$gateway_sha"
      pid=$(systemctl show tradewave-apiserver.service --property=MainPID --value)
      [ "$(process_argv_sha256 "$pid")" = "$gateway_argv_sha" ] \
        || fail "recovered sealed API gateway argv differs from journal entry"
      ;;
    legacy)
      systemctl start tradewave-apiserver.service
      verify_legacy_api_process_identity \
        "$gateway_cwd" "$gateway_command" "$gateway_argv_sha" \
        || fail "recovered legacy API gateway identity differs from journal entry"
      ;;
    absent)
      ! systemctl is-active --quiet tradewave-apiserver.service \
        || fail "absent recovered API gateway unexpectedly started"
      ;;
  esac

  release_runtime_lock
  case "$entry_kind" in
    sealed)
      systemctl start tradewave-mcpserver.service
      verify_sealed_bundle "$entry_bundle" "$entry_sha"
      verify_running_bundle "$entry_bundle" "$entry_sha" "$entry_policy"
      pid=$(systemctl show tradewave-mcpserver.service --property=MainPID --value)
      [ "$(process_argv_sha256 "$pid")" = "$entry_argv_sha" ] \
        || fail "recovered sealed MCP argv differs from journal entry"
      ;;
    legacy)
      systemctl start tradewave-mcpserver.service
      verify_legacy_process_identity "$entry_cwd" "$entry_command" "$entry_argv_sha" \
        || fail "recovered legacy MCP identity differs from journal entry"
      ;;
    absent)
      ! systemctl is-active --quiet tradewave-mcpserver.service \
        || fail "absent recovered MCP unexpectedly started"
      ;;
  esac
  if [ "$entry_kind" != absent ]; then
    public_no_bearer_gates
  fi
}

recover_unfinished_transaction() {
  local output mode state_path candidate_bundle candidate_sha entry_kind
  local entry_policy entry_bundle entry_sha entry_cwd entry_command entry_argv_sha
  local gateway_kind gateway_policy gateway_bundle gateway_sha gateway_cwd
  local gateway_command gateway_argv_sha committed_path pid

  # Reconciliation removes only never-authoritative temporary/GC states. Every
  # authoritative state is then completed in its one permitted direction.
  journal_action reconcile >/dev/null \
    || fail "durable paired transaction garbage-collection recovery failed"
  output=$(journal_action inspect) \
    || fail "durable paired transaction inspection failed"
  mapfile -t journal_fields <<< "$output"
  mode=${journal_fields[0]:-}
  [ "$mode" != none ] || return 0
  [ "${#journal_fields[@]}" -eq 18 ] \
    || fail "paired journal recovery returned invalid data"

  ensure_runtime_lock_file
  ensure_api_runtime_lock_file
  state_path=${journal_fields[1]}
  candidate_bundle=${journal_fields[2]}
  candidate_sha=${journal_fields[3]}
  entry_kind=${journal_fields[4]}
  entry_policy=${journal_fields[5]}
  entry_bundle=${journal_fields[6]}
  entry_sha=${journal_fields[7]}
  entry_cwd=${journal_fields[8]}
  entry_command=${journal_fields[9]}
  entry_argv_sha=${journal_fields[10]}
  gateway_kind=${journal_fields[11]}
  gateway_policy=${journal_fields[12]}
  gateway_bundle=${journal_fields[13]}
  gateway_sha=${journal_fields[14]}
  gateway_cwd=${journal_fields[15]}
  gateway_command=${journal_fields[16]}
  gateway_argv_sha=${journal_fields[17]}
  CANDIDATE_BUNDLE=$candidate_bundle
  CANDIDATE_SRC=$candidate_bundle/src
  TXID=$(journal_state_txid "$state_path")

  if [ "$mode" = active ] || [ "$mode" = recovering ]; then
    echo "RECOVERY: restoring the pre-intent API gateway + MCP entry pair" >&2
    if [ "$entry_kind" = sealed ]; then
      verify_sealed_bundle "$entry_bundle" "$entry_sha"
    fi
    if [ "$gateway_kind" = sealed ]; then
      verify_sealed_bundle "$gateway_bundle" "$gateway_sha"
    fi
    stop_persistent_pair_for_recovery "$gateway_kind"
    if [ "$mode" = active ]; then
      crash_point recovery_after_pair_stop
      journal_action restore >/dev/null \
        || fail "durable paired transaction restore failed"
      crash_point recovery_after_restore
      # A crash may leave a sacrificial verifier row/source. Destroy it before
      # recovery evidence is created. For a sealed entry K1 was already active
      # on entry and must be preserved; only first-migration pending K1 is aborted.
      purge_stale_verifier_probes "$candidate_bundle"
      if [ "$entry_kind" = sealed ]; then
        check_release_service_key
      else
        abort_mcp_key_rotation "$candidate_bundle"
      fi
      crash_point recovery_after_key_reconcile
    fi
    if [ "$entry_kind" = legacy ] || [ "$gateway_kind" = legacy ]; then
      restore_legacy_flask_support_services \
        || fail "legacy support-service recovery failed"
    fi
    systemctl daemon-reload
    verify_restored_pair_policy "$entry_kind" "$entry_policy" "$gateway_kind"
    nginx -t
    systemctl reload nginx
    crash_point recovery_after_restored_pair_policy
    if [ "$entry_kind" = sealed ] && [ "$gateway_kind" = sealed ]; then
      # The restored sealed pair is re-qualified while the active journal still
      # blocks every persistent start. Sacrificial bearer evidence is destroyed
      # before recovery.json is created; nothing authenticated runs post-marker.
      TX_SCRATCH=$(mktemp -d /tmp/tradewave-mcp-recovery.XXXXXX)
      prepare_mcp_canary_env
      assert_paired_ports_free
      start_api_candidate_canary "$gateway_bundle" "$gateway_sha"
      crash_point recovery_rollback_after_api_canary
      start_candidate_canary "$entry_bundle" "$entry_sha"
      verify_candidate_canary "$entry_bundle" "$entry_sha"
      candidate_contract_check "$entry_bundle"
      candidate_load_check "$entry_bundle"
      crash_point recovery_rollback_after_authenticated_gates
      stop_candidate_canary_strict
      stop_api_candidate_canary_strict
      assert_paired_ports_free
      purge_stale_verifier_probes "$candidate_bundle"
      rm -f "$TX_SCRATCH/mcpserver-canary.env"
      rmdir "$TX_SCRATCH" 2>/dev/null || true
      TX_SCRATCH=""
    elif [ "$entry_kind" = legacy ] && [ "$gateway_kind" = legacy ]; then
      start_legacy_recovery_canaries "$entry_argv_sha" "$gateway_argv_sha"
      crash_point recovery_legacy_after_authenticated_gates
      stop_legacy_recovery_canaries_strict
      purge_stale_verifier_probes "$candidate_bundle"
    elif [ "$entry_kind" != absent ]; then
      fail "recovery refuses an authenticated-untested mixed legacy/sealed pair"
    fi
    state_path=$(journal_action mark-recovered) \
      || fail "safe restored pair could not be durably marked recovered"
    crash_point recovery_after_mark_recovered
    start_and_verify_recovered_pair \
      "$entry_kind" "$entry_policy" "$entry_bundle" "$entry_sha" \
      "$entry_cwd" "$entry_command" "$entry_argv_sha" \
      "$gateway_kind" "$gateway_policy" "$gateway_bundle" "$gateway_sha" \
      "$gateway_cwd" "$gateway_command" "$gateway_argv_sha"
    crash_point recovery_after_pair_restart
    journal_action cleanup-recovered "$state_path" >/dev/null \
      || fail "verified recovered pair could not be durably cleaned"
    crash_point recovery_after_close
    echo "RECOVERY PASS: pre-intent API gateway + MCP entry pair restored" >&2
    return 0
  fi

  if [ "$mode" = finalizing ]; then
    echo "RECOVERY: irrevocable paired commit intent detected; rolling forward" >&2
    verify_sealed_bundle "$candidate_bundle" "$candidate_sha"
    [ "$(readlink -f "$CURRENT_LINK")" = "$candidate_bundle" ] \
      || fail "finalizing candidate is not the current paired release"
    stop_persistent_pair_for_recovery sealed
    require_trusted_controller_payload
    systemctl daemon-reload
    verify_installed_api_service_policy
    verify_api_service_enabled
    verify_installed_service_policy
    verify_service_enabled
    nginx -t
    systemctl reload nginx
    TX_SCRATCH=$(mktemp -d /tmp/tradewave-mcp-recovery.XXXXXX)
    prepare_mcp_canary_env
    purge_stale_verifier_probes "$candidate_bundle"
    assert_paired_ports_free
    start_api_candidate_canary "$candidate_bundle" "$candidate_sha"
    crash_point recovery_finalizing_after_api_canary
    start_candidate_canary "$candidate_bundle" "$candidate_sha"
    verify_candidate_canary "$candidate_bundle" "$candidate_sha"
    crash_point recovery_finalizing_after_mcp_canary
    candidate_contract_check "$candidate_bundle"
    candidate_load_check "$candidate_bundle"
    crash_point recovery_finalizing_after_authenticated_gates
    check_release_service_key
    finalize_mcp_key_rotation "$CANARY_PID"
    purge_stale_verifier_probes "$candidate_bundle"
    journal_action mark-finalized >/dev/null \
      || fail "finalizing recovery could not publish finalization evidence"
    crash_point recovery_finalizing_after_marker
    committed_path=$(journal_action commit "$candidate_bundle" "$candidate_sha") \
      || fail "finalizing recovery could not commit paired journal"
    crash_point recovery_finalizing_after_commit
    stop_candidate_canary_strict
    stop_api_candidate_canary_strict
    assert_paired_ports_free
    release_api_runtime_lock
    systemctl start tradewave-apiserver.service
    verify_running_api_bundle "$candidate_bundle" "$candidate_sha"
    crash_point recovery_finalizing_after_api_start
    release_runtime_lock
    systemctl start tradewave-mcpserver.service
    verify_running_bundle "$candidate_bundle" "$candidate_sha"
    public_no_bearer_gates
    crash_point recovery_finalizing_after_pair_start
    journal_action cleanup "$committed_path" >/dev/null \
      || fail "roll-forward paired transaction could not be cleaned"
    rm -f "$TX_SCRATCH/mcpserver-canary.env"
    rmdir "$TX_SCRATCH" 2>/dev/null || true
    TX_SCRATCH=""
    echo "RECOVERY PASS: finalizing API gateway + MCP release rolled forward" >&2
    return 0
  fi

  [ "$mode" = committed ] || fail "unknown durable paired transaction mode: $mode"
  echo "RECOVERY: committed paired release detected; starting exact persistent pair" >&2
  [ "$(readlink -f "$CURRENT_LINK")" = "$candidate_bundle" ] \
    || fail "committed candidate is not the current paired release"
  verify_sealed_bundle "$candidate_bundle" "$candidate_sha"
  journal_action verify-committed-live "$state_path" >/dev/null \
    || fail "committed paired live state differs from durable evidence"
  stop_persistent_pair_for_recovery sealed
  require_trusted_controller_payload
  systemctl daemon-reload
  verify_installed_api_service_policy
  verify_api_service_enabled
  verify_installed_service_policy
  verify_service_enabled
  nginx -t
  systemctl reload nginx
  release_api_runtime_lock
  systemctl start tradewave-apiserver.service
  verify_running_api_bundle "$candidate_bundle" "$candidate_sha"
  crash_point recovery_committed_after_api_start
  release_runtime_lock
  systemctl start tradewave-mcpserver.service
  verify_running_bundle "$candidate_bundle" "$candidate_sha"
  public_no_bearer_gates
  crash_point recovery_committed_after_pair_start
  journal_action cleanup "$state_path" >/dev/null \
    || fail "committed paired transaction could not be cleaned"
  crash_point recovery_after_committed_cleanup
  echo "RECOVERY PASS: committed API gateway + MCP pair verified and journal cleaned" >&2
}

flush_paths_durably() {  # flush_paths_durably <path>...
  local path
  for path in "$@"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
      # sync -f flushes the complete backing filesystem; the Python pass below
      # additionally fsyncs each live file and containing directory explicitly.
      SYNCFS_COUNT=$((SYNCFS_COUNT + 1))
      if [ "${TW_MCP_TEST_FAIL_SYNCFS_AT:-}" = "$SYNCFS_COUNT" ]; then
        echo "injected syncfs failure at call $SYNCFS_COUNT" >&2
        return 70
      fi
      sync -f "$path" || fail "sync -f failed for $path"
    fi
  done
  trusted_python - "$@" <<'PY'
import os
import stat
import sys

directories = set()
for raw in sys.argv[1:]:
    path = os.path.abspath(raw)
    if os.path.lexists(path):
        metadata = os.lstat(path)
        if stat.S_ISREG(metadata.st_mode):
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        elif stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            directories.add(path)
    directories.add(os.path.dirname(path))
for directory in sorted(directories):
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
PY
}

flush_candidate_bundle() {
  flush_paths_durably "$CANDIDATE_BUNDLE" "$CANDIDATE_BUNDLE/.sealed" \
    "$CANDIDATE_BUNDLE/artifacts" "$RELEASE_ROOT"
}

flush_live_candidate_state() {
  flush_paths_durably "$CANDIDATE_BUNDLE" "$CANDIDATE_BUNDLE/.sealed" \
    "$CURRENT_LINK" "$PREVIOUS_LINK" "$UNIT" "$API_UNIT" "$DROPIN" "$NGINX_AVAILABLE" \
    "$NGINX_ENABLED" "$SERVICE_ENABLED" "$API_SERVICE_ENABLED" \
    "$MCP_ENV" "$API_ENV" "$SECRETS" "$MCP_KEY_STATE" \
    "$START_GUARD" "$(dirname "$UNIT")" "$(dirname "$DROPIN")" \
    "$(dirname "$NGINX_AVAILABLE")" "$(dirname "$SERVICE_ENABLED")" \
    "$(dirname "$MCP_ENV")" "$MCP_HOME"
}

ENTRY_BUNDLE=""
ENTRY_BUNDLE_SHA=""
ENTRY_RUNTIME_POLICY=""
preflight_entry_bundle() {
  local resolved sha expected policy
  if [ -e "$CURRENT_LINK" ] && [ ! -L "$CURRENT_LINK" ]; then
    fail "$CURRENT_LINK exists but is not a symlink"
  fi
  if [ ! -L "$CURRENT_LINK" ]; then
    return 0
  fi
  resolved=$(readlink -f -- "$CURRENT_LINK") \
    || fail "$CURRENT_LINK is broken or cannot be resolved"
  case "$resolved" in
    "$RELEASE_ROOT"/mcp-*) ;;
    *) fail "current release resolves outside $RELEASE_ROOT: $resolved" ;;
  esac
  [ -r "$resolved/.sealed" ] || fail "current release is not sealed: $resolved"
  sha=$(seal_value release_sha "$resolved/.sealed")
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "current release seal has an invalid SHA"
  expected=$(bundle_for_sha "$sha")
  [ "$resolved" = "$expected" ] \
    || fail "current release path does not match its sealed SHA: $resolved"
  ENTRY_BUNDLE=$resolved
  ENTRY_BUNDLE_SHA=$sha
  verify_sealed_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"
  if cmp -s "$TRUSTED_UNIT_TEMPLATE" "$UNIT"; then
    policy=fenced
  else
    policy=sealed-unfenced
  fi
  verify_running_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA" "$policy"
  ENTRY_RUNTIME_POLICY=$policy
  say "pre-deploy current release is sealed, in-root, and running: $ENTRY_BUNDLE_SHA ($policy)"
}

accept_release_sha() {  # sets RELEASE_SHA
  local requested="$1"
  [[ "$requested" =~ ^[0-9a-f]{40}$ ]] \
    || fail "release target must be an exact lowercase 40-character commit SHA"
  RELEASE_SHA=$requested
}

# This is intentionally the first stateful action after acquiring the release
# lock. It precedes service-active, current-bundle, source checkout, secrets,
# and candidate preflights so a reboot/SIGKILL hybrid can always be reconciled.
recover_unfinished_transaction
require_release_python
command -v nsenter >/dev/null 2>&1 || fail "nsenter is missing"
command -v setpriv >/dev/null 2>&1 || fail "setpriv is missing"
ensure_mcp_service_identities
ensure_runtime_lock_file
ensure_api_runtime_lock_file
ensure_root_path "$BUILD_ROOT" 0755 exact
[ -f "$SECRETS" ] && [ ! -L "$SECRETS" ] \
  && [ "$(stat -c '%U:%G %a %h' "$SECRETS")" = "root:flask 640 1" ] \
  || fail "$SECRETS must be a single-link root:flask mode 0640 regular file"
if [ -e "$MCP_ENV" ] || [ -L "$MCP_ENV" ]; then
  [ -f "$MCP_ENV" ] && [ ! -L "$MCP_ENV" ] \
    && [ "$(stat -c '%U:%G %a %h' "$MCP_ENV")" = "root:root 600 1" ] \
    || fail "$MCP_ENV must be absent or a single-link root:root mode 0600 regular file"
fi
ENTRY_INSTALL_STATE=present
if [ -f "$UNIT" ] && [ ! -L "$UNIT" ]; then
  systemctl is-active --quiet tradewave-mcpserver \
    || fail "pre-deploy MCP service is not active"
else
  [ ! -e "$UNIT" ] && [ ! -L "$UNIT" ] \
    || fail "pre-deploy MCP unit path is unsafe"
  [ ! -L "$CURRENT_LINK" ] \
    || fail "sealed current release exists without its base MCP unit"
  ! systemctl is-active --quiet tradewave-mcpserver \
    || fail "MCP service is active without a base unit"
  cmp -s "$TRUSTED_FENCE_TEMPLATE" "$FENCE_DROPIN" \
    || fail "absent first activation lacks the stable release fence"
  ENTRY_INSTALL_STATE=absent
fi
if [ ! -L "$CURRENT_LINK" ] && [ "$ENTRY_INSTALL_STATE" = present ]; then
  LEGACY_PREFLIGHT_PID=$(systemctl show tradewave-mcpserver --property=MainPID --value)
  [ -n "$LEGACY_PREFLIGHT_PID" ] && [ "$LEGACY_PREFLIGHT_PID" -ge 2 ] \
    || fail "legacy first migration has no live MainPID"
  verify_legacy_service_policy
  verify_exact_legacy_cmdline "$LEGACY_PREFLIGHT_PID"
  [ "$(readlink -f "/proc/$LEGACY_PREFLIGHT_PID/cwd")" = /home/flask ] \
    || fail "legacy first-migration PID cwd differs from the reviewed predecessor"
fi

API_ENTRY_INSTALL_STATE=present
API_ENTRY_KIND=""
if [ -f "$API_UNIT" ] && [ ! -L "$API_UNIT" ]; then
  systemctl is-active --quiet tradewave-apiserver.service \
    || fail "pre-deploy API gateway service is not active"
  if cmp -s "$TRUSTED_API_UNIT_TEMPLATE" "$API_UNIT"; then
    [ -L "$CURRENT_LINK" ] \
      || fail "immutable API gateway unit has no sealed current release"
    API_ENTRY_KIND=sealed
  elif cmp -s "$TRUSTED_LEGACY_API_UNIT" "$API_UNIT"; then
    API_ENTRY_KIND=legacy
  else
    fail "pre-deploy API gateway unit is neither immutable nor the reviewed legacy predecessor"
  fi
else
  [ ! -e "$API_UNIT" ] && [ ! -L "$API_UNIT" ] \
    || fail "pre-deploy API gateway unit path is unsafe"
  ! systemctl is-active --quiet tradewave-apiserver.service \
    || fail "API gateway is active without a base unit"
  API_ENTRY_INSTALL_STATE=absent
  API_ENTRY_KIND=absent
fi

ROLLBACK_MODE=0
VALIDATOR_BUNDLE=""
SEED_PREVIOUS_TARGET=""

if [ "${1:-}" = --rollback ]; then
  [ "$#" -eq 1 ] || fail "usage: $0 --rollback"
  [ -L "$CURRENT_LINK" ] || fail "$CURRENT_LINK is not a symlink"
  [ -L "$PREVIOUS_LINK" ] || fail "$PREVIOUS_LINK is not available"
  ROLLBACK_MODE=1
  preflight_entry_bundle
  VALIDATOR_BUNDLE=$ENTRY_BUNDLE
  CANDIDATE_BUNDLE=$(readlink -f "$PREVIOUS_LINK")
  case "$CANDIDATE_BUNDLE" in
    "$RELEASE_ROOT"/mcp-*) ;;
    *) fail "invalid rollback bundle: $CANDIDATE_BUNDLE" ;;
  esac
  RELEASE_SHA=$(bundle_sha "$CANDIDATE_BUNDLE")
  [ "$CANDIDATE_BUNDLE" = "$(bundle_for_sha "$RELEASE_SHA")" ] \
    || fail "rollback bundle path does not match its sealed SHA: $CANDIDATE_BUNDLE"
  verify_sealed_bundle "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
  CANDIDATE_SRC=$CANDIDATE_BUNDLE/src
  say "rollback target is sealed bundle $RELEASE_SHA"
else
  [ "$#" -eq 1 ] || fail "usage: $0 <lowercase-40-sha>"
  REQUESTED_SHA=$1
  accept_release_sha "$REQUESTED_SHA"

  # Refuse to build or preserve a rollback target until the release active on
  # entry has independently proved its path, seal, runtime, PID, and environment.
  # A missing current link is the one supported legacy-first-install case.
  preflight_entry_bundle

  echo "==> prepare immutable MCP candidate at exact SHA: $RELEASE_SHA"
  prepare_bundle "$RELEASE_SHA"
  CANDIDATE_BUNDLE=$PREPARED_BUNDLE
  CANDIDATE_SRC=$CANDIDATE_BUNDLE/src

  for required in \
    mcpserver/server.py \
    apiserver/app.py \
    apiserver/auth.py \
    requirements-mcp.lock \
    requirements-gateway.lock \
    requirements-mcp-test.lock \
    tests/test_mcpserver.py \
    tests/test_apiserver_endpoints.py \
    tests/test_cards.py \
    tests/test_ml_quota.py \
    tests/test_mcp_discovery_contract.py \
    tests/test_provision_mcp_key.py \
    tests/test_consistency.py \
    ops/tests/test_mcp_contract_runtime.py \
    ops/tests/test_mcp_service_env.py \
    ops/tests/test_verify_mcp_discovery.py \
    ops/tests/test_verify_mcp_protocol.py \
    ops/tests/test_verify_mcp_load.py; do
    [ -r "$CANDIDATE_SRC/$required" ] || fail "candidate is missing $required"
  done
  stage_bundle_artifacts "$CANDIDATE_BUNDLE" candidate
  publish_prepared_bundle "$RELEASE_SHA"
  CANDIDATE_BUNDLE=$PREPARED_BUNDLE
  CANDIDATE_SRC=$CANDIDATE_BUNDLE/src

  # The first migration uses one explicitly reviewed canonical SHA. The mutable
  # /home/flask checkout is neither read nor trusted. The sealed compatibility
  # bundle reuses the candidate's already verified dependency locks.
  if [ ! -L "$CURRENT_LINK" ]; then
    prepare_bundle "$LEGACY_ROLLBACK_SHA" "$CANDIDATE_BUNDLE"
    stage_bundle_artifacts "$PREPARED_BUNDLE" legacy
    publish_prepared_bundle "$LEGACY_ROLLBACK_SHA"
    SEED_PREVIOUS_TARGET="releases/mcp-$LEGACY_ROLLBACK_SHA"
    say "seeded first rollback bundle from reviewed canonical SHA $LEGACY_ROLLBACK_SHA"
  fi
fi

echo "==> capture entry identity before publishing the durable transaction journal"
if [ "$API_ENTRY_KIND" = sealed ]; then
  [ -n "$ENTRY_BUNDLE" ] && [ -n "$ENTRY_BUNDLE_SHA" ] \
    || fail "sealed API gateway entry has no preflighted current bundle"
  verify_running_api_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"
elif [ "$API_ENTRY_KIND" = legacy ]; then
  verify_legacy_api_service_policy
fi
if [ "$ENTRY_INSTALL_STATE" = absent ]; then
  ENTRY_SERVICE_PID=""
  ENTRY_SERVICE_CWD=/
  ENTRY_SERVICE_COMMAND=/nonexistent
  ENTRY_SERVICE_ARGV_SHA=$(printf '%064d' 0)
else
  ENTRY_SERVICE_PID=$(systemctl show tradewave-mcpserver --property=MainPID --value)
  if [ -z "$ENTRY_SERVICE_PID" ] || [ "$ENTRY_SERVICE_PID" -lt 2 ]; then
    fail "cannot snapshot pre-deploy MCP MainPID"
  fi
  ENTRY_SERVICE_CWD=$(readlink -f "/proc/$ENTRY_SERVICE_PID/cwd")
  ENTRY_SERVICE_COMMAND=$(tr '\0' '\n' < "/proc/$ENTRY_SERVICE_PID/cmdline" | head -1)
  ENTRY_SERVICE_ARGV_SHA=$(process_argv_sha256 "$ENTRY_SERVICE_PID")
  if [ -z "$ENTRY_SERVICE_CWD" ] || [ -z "$ENTRY_SERVICE_COMMAND" ]; then
    fail "cannot snapshot pre-deploy MCP process identity"
  fi
fi
if [ "$API_ENTRY_INSTALL_STATE" = absent ]; then
  GATEWAY_ENTRY_PID=""
  GATEWAY_ENTRY_CWD=/
  GATEWAY_ENTRY_COMMAND=/nonexistent
  GATEWAY_ENTRY_ARGV_SHA=$(printf '%064d' 0)
else
  GATEWAY_ENTRY_PID=$(systemctl show tradewave-apiserver --property=MainPID --value)
  if [ -z "$GATEWAY_ENTRY_PID" ] || [ "$GATEWAY_ENTRY_PID" -lt 2 ]; then
    fail "cannot snapshot pre-deploy API gateway MainPID"
  fi
  GATEWAY_ENTRY_CWD=$(readlink -f "/proc/$GATEWAY_ENTRY_PID/cwd")
  GATEWAY_ENTRY_COMMAND=$(tr '\0' '\n' < "/proc/$GATEWAY_ENTRY_PID/cmdline" | head -1)
  GATEWAY_ENTRY_ARGV_SHA=$(process_argv_sha256 "$GATEWAY_ENTRY_PID")
  if [ -z "$GATEWAY_ENTRY_CWD" ] || [ -z "$GATEWAY_ENTRY_COMMAND" ]; then
    fail "cannot snapshot pre-deploy API gateway process identity"
  fi
  if [ "$API_ENTRY_KIND" = sealed ]; then
    [ "$GATEWAY_ENTRY_CWD" = "$ENTRY_BUNDLE/src" ] \
      && [ "$GATEWAY_ENTRY_COMMAND" = "$CURRENT_LINK/gateway-venv/bin/python" ] \
      || fail "sealed pre-deploy API gateway process escaped current bundle"
  elif [ "$API_ENTRY_KIND" = legacy ]; then
    verify_legacy_api_process_identity \
      "$GATEWAY_ENTRY_CWD" "$GATEWAY_ENTRY_COMMAND" "$GATEWAY_ENTRY_ARGV_SHA" \
      || fail "legacy pre-deploy API gateway process identity is not exact"
  fi
fi

CURRENT_WAS_LINK=0; CURRENT_OLD_TARGET=""
PREVIOUS_WAS_LINK=0; PREVIOUS_OLD_TARGET=""
NGINX_LINK_WAS_LINK=0; NGINX_LINK_OLD_TARGET=""
if [ -e "$CURRENT_LINK" ] && [ ! -L "$CURRENT_LINK" ]; then fail "$CURRENT_LINK is not a symlink"; fi
if [ -L "$CURRENT_LINK" ]; then
  CURRENT_WAS_LINK=1
  [ "$(stat -c '%u:%g' "$CURRENT_LINK")" = "0:0" ] \
    || fail "$CURRENT_LINK symlink must be root:root"
  [ "$(readlink -f -- "$CURRENT_LINK")" = "$ENTRY_BUNDLE" ] \
    || fail "current release changed after its entry preflight"
  [ -n "$ENTRY_BUNDLE_SHA" ] || fail "current release entry SHA was not captured"
  CURRENT_OLD_TARGET=$(readlink "$CURRENT_LINK")
  [[ "$CURRENT_OLD_TARGET" =~ ^releases/mcp-[0-9a-f]{40}$ ]] \
    || fail "$CURRENT_LINK does not store a canonical release target"
fi
if [ -e "$PREVIOUS_LINK" ] && [ ! -L "$PREVIOUS_LINK" ]; then fail "$PREVIOUS_LINK is not a symlink"; fi
if [ -L "$PREVIOUS_LINK" ]; then
  PREVIOUS_WAS_LINK=1
  [ "$(stat -c '%u:%g' "$PREVIOUS_LINK")" = "0:0" ] \
    || fail "$PREVIOUS_LINK symlink must be root:root"
  PREVIOUS_OLD_TARGET=$(readlink "$PREVIOUS_LINK")
  [[ "$PREVIOUS_OLD_TARGET" =~ ^releases/mcp-[0-9a-f]{40}$ ]] \
    || fail "$PREVIOUS_LINK does not store a canonical release target"
fi
if [ -e "$NGINX_ENABLED" ] && [ ! -L "$NGINX_ENABLED" ]; then fail "$NGINX_ENABLED is not a symlink"; fi
if [ -L "$NGINX_ENABLED" ]; then
  NGINX_LINK_WAS_LINK=1
  [ "$(stat -c '%u:%g' "$NGINX_ENABLED")" = "0:0" ] \
    || fail "$NGINX_ENABLED symlink must be root:root"
  NGINX_LINK_OLD_TARGET=$(readlink "$NGINX_ENABLED")
  [ "$NGINX_LINK_OLD_TARGET" = "$NGINX_AVAILABLE" ] \
    || fail "$NGINX_ENABLED must store exactly $NGINX_AVAILABLE"
fi

ENTRY_KIND=legacy
ENTRY_JOURNAL_POLICY=legacy
ENTRY_JOURNAL_BUNDLE=""
ENTRY_JOURNAL_SHA=""
GATEWAY_ENTRY_KIND=$API_ENTRY_KIND
GATEWAY_ENTRY_JOURNAL_POLICY=$API_ENTRY_KIND
GATEWAY_ENTRY_JOURNAL_BUNDLE=""
GATEWAY_ENTRY_JOURNAL_SHA=""
if [ "$CURRENT_WAS_LINK" = 1 ]; then
  ENTRY_KIND=sealed
  ENTRY_JOURNAL_POLICY=$ENTRY_RUNTIME_POLICY
  [ "$ENTRY_JOURNAL_POLICY" = fenced ] || [ "$ENTRY_JOURNAL_POLICY" = sealed-unfenced ] \
    || fail "sealed entry runtime policy was not classified"
  ENTRY_JOURNAL_BUNDLE=$ENTRY_BUNDLE
  ENTRY_JOURNAL_SHA=$ENTRY_BUNDLE_SHA
else
  if [ "$ENTRY_INSTALL_STATE" = absent ]; then
    ENTRY_KIND=absent
    ENTRY_JOURNAL_POLICY=absent
  fi
  assert_flask_platform_services_active \
    || fail "first MCP activation requires all fixed flask platform services active"
fi
if [ "$GATEWAY_ENTRY_KIND" = sealed ]; then
  GATEWAY_ENTRY_JOURNAL_POLICY=fenced
  GATEWAY_ENTRY_JOURNAL_BUNDLE=$ENTRY_BUNDLE
  GATEWAY_ENTRY_JOURNAL_SHA=$ENTRY_BUNDLE_SHA
elif [ "$GATEWAY_ENTRY_KIND" = legacy ]; then
  GATEWAY_ENTRY_JOURNAL_POLICY=legacy
elif [ "$GATEWAY_ENTRY_KIND" = absent ]; then
  GATEWAY_ENTRY_JOURNAL_POLICY=absent
else
  fail "API gateway entry kind was not independently classified"
fi
# No pointer may reference a bundle whose seal/runtime/artifacts have not crossed
# a filesystem durability barrier.
flush_candidate_bundle
TXID=$(trusted_python -c 'import uuid; print(uuid.uuid4())')
TX_BACKUP=$(journal_action prepare "$TXID" "$CANDIDATE_BUNDLE" "$RELEASE_SHA" \
  "$ENTRY_KIND" "$ENTRY_JOURNAL_POLICY" "$ENTRY_JOURNAL_BUNDLE" "$ENTRY_JOURNAL_SHA" \
  "$ENTRY_SERVICE_CWD" "$ENTRY_SERVICE_COMMAND" "$ENTRY_SERVICE_ARGV_SHA" \
  "$GATEWAY_ENTRY_KIND" "$GATEWAY_ENTRY_JOURNAL_POLICY" \
  "$GATEWAY_ENTRY_JOURNAL_BUNDLE" "$GATEWAY_ENTRY_JOURNAL_SHA" \
  "$GATEWAY_ENTRY_CWD" "$GATEWAY_ENTRY_COMMAND" "$GATEWAY_ENTRY_ARGV_SHA") \
  || fail "could not publish durable MCP transaction journal"
[ "$TX_BACKUP" = "$TX_ACTIVE" ] || fail "journal prepare returned an unexpected path"
TX_SCRATCH=$(mktemp -d /tmp/tradewave-mcp-release.XXXXXX)
TX_ARMED=1
crash_point after_journal_publish

on_exit() {
  local rc=$? recovery_failed=0
  trap - EXIT
  stop_transient_verifier_best_effort
  revoke_verifier_probe_best_effort
  stop_candidate_canary_best_effort
  stop_api_candidate_canary_best_effort
  if [ "$TX_ARMED" = 1 ] && [ "$rc" -eq 0 ]; then
    echo "FAIL: controller attempted a successful exit while paired journal remained armed" >&2
    rc=70
  fi
  if [ "$rc" -ne 0 ] || [ "$TX_ARMED" = 1 ]; then
    # The durable journal chooses the only legal direction: active/recovering
    # restores the entry pair; finalizing/committed rolls the candidate pair
    # forward. Both paths stop MCP then gateway and restart gateway then MCP.
    ( recover_unfinished_transaction ) || recovery_failed=1
  fi
  if [ -n "$TX_SCRATCH" ]; then
    rm -f "$TX_SCRATCH/nginx-candidate" "$TX_SCRATCH/mcpserver.env-candidate" \
      "$TX_SCRATCH/mcpserver-canary.env"
    rmdir "$TX_SCRATCH" 2>/dev/null || true
  fi
  if [ "$recovery_failed" != 0 ]; then
    echo "PAIRED RECOVERY FAILED after deploy exit $rc; original failure preserved; journal=$TX_ACTIVE" >&2
  fi
  exit "$rc"
}
trap on_exit EXIT

echo "==> generate the exact dedicated API gateway environment"
trusted_python "$TRUSTED_ENV_HELPER" render-api --source "$SECRETS" --output "$API_ENV"
trusted_python "$TRUSTED_ENV_HELPER" validate-api --path "$API_ENV"
crash_point after_api_environment

echo "==> stop persistent MCP and fence its activation before any live mutation"
systemctl stop tradewave-mcpserver
assert_exact_uid_processes "$MCP_SERVICE_USER" \
  || fail "MCP service identity retained a process after persistent stop"
acquire_runtime_lock_exclusive
crash_point after_entry_service_stop

# Credential mutation begins only after the durable journal has captured both
# secret files and the persistent service has released its lifetime shared
# runtime lock. The controller now holds that lock exclusively through commit.
if [ "$ROLLBACK_MODE" = 0 ]; then
  echo "==> provision K1 inside the durable release transaction"
  provision_release_credentials
  crash_point after_key_provision
else
  echo "==> verify dedicated release credentials inside the rollback transaction"
  check_release_service_key
fi

if [ "$API_ENTRY_KIND" = legacy ] || [ "$API_ENTRY_KIND" = absent ]; then
  scrub_legacy_flask_mcp_secret
else
  if [ "$API_ENTRY_KIND" = sealed ]; then
    systemctl stop tradewave-apiserver.service
    assert_exact_uid_processes "$API_SERVICE_USER" \
      || fail "API service identity retained a process after persistent stop"
  fi
  assert_no_uid_environment_name flask MCP_GATEWAY_KEY \
    || fail "a flask-owned process unexpectedly retained legacy K0"
fi
! systemctl is-active --quiet tradewave-apiserver.service \
  || fail "API gateway remained active after the paired release stop boundary"
acquire_api_runtime_lock_exclusive
assert_paired_ports_free
crash_point after_api_entry_service_stop

echo "==> stage target bundle pointers inside the rollback transaction"
if [ "$CURRENT_WAS_LINK" = 1 ]; then
  prior_dir=$(readlink -f "$CURRENT_LINK")
  if [ "$prior_dir" != "$CANDIDATE_BUNDLE" ]; then
    atomic_symlink "$CURRENT_OLD_TARGET" "$PREVIOUS_LINK"
    say "retained release active on entry as previous: $prior_dir"
  fi
else
  [ -n "$SEED_PREVIOUS_TARGET" ] \
    || fail "first immutable activation has no seeded rollback bundle"
  atomic_symlink "$SEED_PREVIOUS_TARGET" "$PREVIOUS_LINK"
fi
crash_point after_previous_pointer
atomic_symlink "releases/mcp-$RELEASE_SHA" "$CURRENT_LINK"
crash_point after_current_pointer

echo "==> install target bundle's versioned unit/drop-in and reviewed edge"
require_trusted_controller_payload
install -o root -g root -m 0644 "$TRUSTED_API_UNIT_TEMPLATE" "$API_UNIT"
crash_point after_api_unit_file
install -o root -g root -m 0644 "$TRUSTED_UNIT_TEMPLATE" "$UNIT"
crash_point after_unit_file
install -d -m 0755 "$(dirname "$DROPIN")"
install -o root -g root -m 0644 "$TRUSTED_DROPIN_TEMPLATE" "$DROPIN"
crash_point after_dropin_file
install -d -o root -g root -m 0755 "$(dirname "$SERVICE_ENABLED")"
atomic_symlink "../tradewave-mcpserver.service" "$SERVICE_ENABLED" root:root
crash_point after_service_enabled_pointer
atomic_symlink "../tradewave-apiserver.service" "$API_SERVICE_ENABLED" root:root
crash_point after_api_service_enabled_pointer

HOST_OUTPUT=$(resolved_portal_hosts) \
  || fail "fixed environment helper rejected the per-environment public hosts"
mapfile -t RESOLVED_HOSTS <<< "$HOST_OUTPUT"
[ "${#RESOLVED_HOSTS[@]}" -eq 3 ] || fail "portal host resolver returned an invalid result"
API_HOST=${RESOLVED_HOSTS[0]}
MCP_HOST=${RESOLVED_HOSTS[1]}
DEVELOPERS_HOST=${RESOLVED_HOSTS[2]}
MCP_PUBLIC_URL=$(public_url)
[ -n "$MCP_PUBLIC_URL" ] || fail "TW2_MCP_PUBLIC_URL is missing"
MCP_URL_HOST=$(public_url_host "$MCP_PUBLIC_URL") \
  || fail "TW2_MCP_PUBLIC_URL is not a canonical HTTPS MCP origin"
if [ "${MCP_HOST,,}" != "$MCP_URL_HOST" ]; then
  fail "TW2_MCP_PUBLIC_HOST ($MCP_HOST) disagrees with TW2_MCP_PUBLIC_URL ($MCP_PUBLIC_URL)"
fi
say "resolved edge hosts via fixed environment helper: API=$API_HOST MCP=$MCP_HOST Developers=$DEVELOPERS_HOST"
for host in "$API_HOST" "$MCP_HOST" "$DEVELOPERS_HOST"; do
  [[ "$host" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] \
    || fail "public hosts must be bare DNS hostnames: $host"
done
echo "==> install and authenticate the least-privilege MCP runtime environment"
install_mcp_runtime_env "$MCP_HOST"
crash_point after_mcp_environment
check_mcp_gateway_key
prepare_mcp_canary_env

EDGE_TMP=$TX_SCRATCH/nginx-candidate
sed -e "s/api-dev\.trxstat\.com/$API_HOST/g" \
    -e "s/mcp-dev\.trxstat\.com/$MCP_HOST/g" \
    -e "s/developers-dev\.trxstat\.com/$DEVELOPERS_HOST/g" \
    "$TRUSTED_NGINX_TEMPLATE" > "$EDGE_TMP"
install -m 0644 "$EDGE_TMP" "$NGINX_AVAILABLE"
crash_point after_nginx_file
atomic_symlink "$NGINX_AVAILABLE" "$NGINX_ENABLED" root:root
crash_point after_nginx_pointer
systemctl daemon-reload
verify_installed_service_policy
verify_service_enabled
verify_installed_api_service_policy
verify_api_service_enabled
if systemctl cat tradewave-mcpserver.service --no-pager \
    | grep -Eq '^[[:space:]]*EnvironmentFile=.*(secrets|mcp-verifier)\.env'; then
  fail "tradewave-mcpserver references a broad or verifier secrets file"
fi
systemd-analyze verify tradewave-apiserver.service tradewave-mcpserver.service
nginx -t

systemctl reload nginx
assert_paired_ports_free
start_api_candidate_canary "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
crash_point after_api_canary_start
start_candidate_canary "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
crash_point after_canary_start
verify_candidate_canary "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
crash_point after_running_bundle_gate
candidate_contract_check "$CANDIDATE_BUNDLE"
candidate_load_check "$CANDIDATE_BUNDLE"
crash_point after_public_gates

echo "==> flush live candidate state and durably commit the release transaction"
flush_live_candidate_state
crash_point before_commit_intent
INTENT_JOURNAL=$(journal_action prepare-commit "$CANDIDATE_BUNDLE" "$RELEASE_SHA") \
  || fail "could not durably publish paired release commit intent"
[ "$INTENT_JOURNAL" = "$TX_ACTIVE" ] || fail "commit intent returned an unexpected journal path"
crash_point after_commit_intent
echo "==> finalize candidate service credential while both canaries are live"
check_release_service_key
finalize_mcp_key_rotation "$CANARY_PID"
crash_point after_key_finalize
revoke_verifier_probe
FINALIZED_JOURNAL=$(journal_action mark-finalized) \
  || fail "could not durably publish paired release finalization evidence"
[ "$FINALIZED_JOURNAL" = "$TX_ACTIVE" ] || fail "finalization returned an unexpected journal path"
crash_point after_finalized_marker
COMMITTED_JOURNAL=$(journal_action commit "$CANDIDATE_BUNDLE" "$RELEASE_SHA") \
  || fail "could not durably commit paired API+MCP release journal"
crash_point after_journal_commit
  stop_candidate_canary_strict
stop_api_candidate_canary_strict
assert_paired_ports_free
# Persistent systemd activation is authorized only after the journal is durable
# committed. Release the controller's exclusive runtime fence immediately before
# PID1 starts the fixed flock wrapper, which takes the lifetime shared side.
systemctl daemon-reload
release_api_runtime_lock
systemctl start tradewave-apiserver
crash_point after_api_service_restart
verify_running_api_bundle "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
release_runtime_lock
systemctl start tradewave-mcpserver
crash_point after_service_restart
verify_running_bundle "$CANDIDATE_BUNDLE" "$RELEASE_SHA"
public_no_bearer_gates
crash_point after_persistent_public_gates
# If cleanup is interrupted, the committed journal remains authoritative and
# the next invocation validates/rolls forward; it is never treated as rollback.
journal_action cleanup "$COMMITTED_JOURNAL" >/dev/null \
  || fail "committed MCP release journal cleanup failed"
crash_point after_journal_cleanup
TX_ARMED=0

echo "==> systemd security exposure summary"
systemd-analyze security tradewave-mcpserver.service --no-pager || true
say "mutable /home/flask gateway checkout was neither read nor modified"

if [ "$ROLLBACK_MODE" = 1 ]; then
  echo "PASS: rolled MCP back to sealed bundle $RELEASE_SHA; prior release is now at $PREVIOUS_LINK"
else
  echo "PASS: MCP bundle $RELEASE_SHA active; rollback ready at $PREVIOUS_LINK"
fi
