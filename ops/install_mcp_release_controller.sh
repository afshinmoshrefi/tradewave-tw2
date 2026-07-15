#!/usr/bin/bash -p
# Publish one coherent, immutable MCP release control-plane generation.
set +x
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP

fail() { echo "FAIL: $*" >&2; exit 1; }
crash_point() {
  if [ "${TW_MCP_INSTALL_TEST_CRASH_AT:-}" = "$1" ]; then
    echo "TEST CRASH POINT: $1" >&2
    kill -KILL "$$"
  fi
}

[ "$EUID" -eq 0 ] || fail "run as root"
[ "$#" -eq 1 ] || fail "usage: $0 <reviewed-lowercase-40-sha>"
REVIEWED_SHA=$1
SOURCE_ORIGIN=https://github.com/afshinmoshrefi/tradewave-tw2.git
[[ "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || fail "reviewed control-plane source must be an exact lowercase 40-character commit SHA"

# Test-only prefix is deliberately narrow. It permits destructive crash/retry
# tests without touching the host control plane. Production uses an empty prefix.
PREFIX=${TW_MCP_INSTALL_TEST_ROOT:-}
if [ -n "$PREFIX" ]; then
  [[ "$PREFIX" =~ ^/tmp/tradewave-mcp-install-test-[0-9a-f-]{36}$ ]] \
    || fail "invalid installer test root"
  [ -d "$PREFIX" ] && [ ! -L "$PREFIX" ] \
    && [ "$(stat -c '%U:%G %a' "$PREFIX")" = "root:root 700" ] \
    || fail "installer test root must be root:root mode 0700"
else
  INSTALLER_SELF=/usr/local/sbin/tradewave-mcp-control-install
  [ "${BASH_SOURCE[0]}" = "$INSTALLER_SELF" ] \
    && [ "$(realpath -e -- "${BASH_SOURCE[0]}")" = "$INSTALLER_SELF" ] \
    || fail "copy the reviewed installer to $INSTALLER_SELF before invoking it"
  [ -f "$INSTALLER_SELF" ] && [ ! -L "$INSTALLER_SELF" ] \
    && [ "$(stat -c '%U:%G %a %h' "$INSTALLER_SELF")" = "root:root 555 1" ] \
    || fail "installed control-plane installer must be root:root mode 0555 single-link"
  [[ "${TW_MCP_INSTALLER_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] \
    || fail "TW_MCP_INSTALLER_SHA256 must carry the out-of-band reviewed installer digest"
  [ "$(sha256sum "$INSTALLER_SELF" | awk '{print $1}')" = "$TW_MCP_INSTALLER_SHA256" ] \
    || fail "installed control-plane installer differs from its reviewed digest"
  /usr/bin/python3.13 -I -B -S - "$INSTALLER_SELF" <<'PY'
import os
import stat
import sys

current = "/"
for component in sys.argv[1].strip("/").split("/")[:-1]:
    current = os.path.join(current, component)
    metadata = os.lstat(current)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise SystemExit(f"unsafe installed installer ancestor: {current}")
PY
fi

CONTROL_ROOT=$PREFIX/usr/local/libexec/tradewave-mcp-release-control
SETS_ROOT=$CONTROL_ROOT/sets
CURRENT=$CONTROL_ROOT/current
PREVIOUS=$CONTROL_ROOT/previous
LAUNCHER=$PREFIX/usr/local/sbin/tradewave-mcp-release
PRODUCTION_GUARD=$PREFIX/usr/local/libexec/tradewave-mcp-start-guard.py
PRODUCTION_FENCE=$PREFIX/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf
PRODUCTION_API_FENCE=$PREFIX/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf
TX_ROOT=$PREFIX/var/lib/tradewave/mcp-release-transactions
LOCK_DIR=$PREFIX/run/lock/tradewave
LOCK_FILE=$LOCK_DIR/mcp-release.lock
TMPFILES_CONFIG=$PREFIX/etc/tmpfiles.d/tradewave-mcp-release.conf

/usr/bin/install -d -o root -g root -m 0700 "$LOCK_DIR"
if [ ! -e "$LOCK_FILE" ]; then
  (umask 077; : > "$LOCK_FILE")
fi
[ -f "$LOCK_FILE" ] && [ ! -L "$LOCK_FILE" ] \
  && [ "$(stat -c '%U:%G %a %h' "$LOCK_FILE")" = "root:root 600 1" ] \
  || fail "$LOCK_FILE is not the exact root-only single-link release lock"
exec 9<>"$LOCK_FILE"
/usr/bin/flock -n 9 || fail "an MCP release controller is already active"

if [ -e "$TX_ROOT" ] || [ -L "$TX_ROOT" ]; then
  [ -d "$TX_ROOT" ] && [ ! -L "$TX_ROOT" ] \
    && [ "$(stat -c '%U:%G %a' "$TX_ROOT")" = "root:root 700" ] \
    || fail "$TX_ROOT is not the exact root-only journal directory"
  [ -z "$(find "$TX_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || fail "refusing control-plane upgrade while any durable transaction exists"
fi

# Account-database mutation cannot run inside the immutable launcher's
# ProtectSystem=strict namespace. The out-of-band reviewed installer creates
# each fixed least-privilege identity; the controller independently rechecks
# the complete set before any release work.
ensure_exact_release_identity() {  # <account> <group>
  local account_name="$1" group_name="$2"
  [ -x /usr/sbin/nologin ] || fail "/usr/sbin/nologin is missing"
  [ -x /usr/bin/getent ] || fail "/usr/bin/getent is missing"
  [ -x /usr/sbin/groupadd ] || fail "/usr/sbin/groupadd is missing"
  [ -x /usr/sbin/useradd ] || fail "/usr/sbin/useradd is missing"

  if /usr/bin/getent passwd "$account_name" >/dev/null 2>&1 \
      && ! /usr/bin/getent group "$group_name" >/dev/null 2>&1; then
    fail "$account_name exists without its reserved primary group"
  fi
  if ! /usr/bin/getent group "$group_name" >/dev/null 2>&1; then
    /usr/sbin/groupadd --system "$group_name"
  fi
  if ! /usr/bin/getent passwd "$account_name" >/dev/null 2>&1; then
    /usr/sbin/useradd --system --gid "$group_name" --no-user-group \
      --home-dir /nonexistent --no-create-home \
      --shell /usr/sbin/nologin --comment "" "$account_name"
  fi

  /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3.13 -I -B -S - "$account_name" "$group_name" <<'PY'
import grp
import os
import pwd
import sys

name, group_name = sys.argv[1:]
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
    or account.pw_dir != "/nonexistent"
    or account.pw_shell != "/usr/sbin/nologin"
    or account.pw_gecos != ""
    or group.gr_mem != []
    or groups != [group.gr_gid]
):
    raise SystemExit(f"reserved {name} account/group does not match the exact service identity")
PY
}

ensure_release_identities() {
  ensure_exact_release_identity tradewave-mcp tradewave-mcp
  ensure_exact_release_identity tradewave-mcp-verify tradewave-mcp-verify
  ensure_exact_release_identity tradewave-mcp-build tradewave-mcp-build
  ensure_exact_release_identity tradewave-mcp-deps tradewave-mcp-deps
  ensure_exact_release_identity tradewave-mcp-test tradewave-mcp-test
  ensure_exact_release_identity tradewave-api tradewave-api
  /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3.13 -I -B -S - \
      tradewave-mcp:tradewave-mcp \
      tradewave-mcp-verify:tradewave-mcp-verify \
      tradewave-mcp-build:tradewave-mcp-build \
      tradewave-mcp-deps:tradewave-mcp-deps \
      tradewave-mcp-test:tradewave-mcp-test \
      tradewave-api:tradewave-api <<'PY'
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

if [ -z "$PREFIX" ]; then
  ensure_release_identities
fi
crash_point after_service_identity_bootstrap

# The stable launcher is deliberately immutable once CURRENT exists. Publish
# every strict-namespace writable mount target here instead, and persist the
# three /run roots through reboot with one immutable tmpfiles definition.
ensure_runtime_mount_bootstrap() {
  /usr/bin/python3.13 -I -B -S - "$PREFIX" "$TMPFILES_CONFIG" <<'PY'
import grp
import os
import secrets
import stat
import sys

prefix, config_path = sys.argv[1:]
os.umask(0)


def fsync_directory(path: str) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


base = prefix or "/"
base_metadata = os.lstat(base)
if (
    not stat.S_ISDIR(base_metadata.st_mode)
    or stat.S_ISLNK(base_metadata.st_mode)
    or base_metadata.st_uid != 0
    or base_metadata.st_gid != 0
    or stat.S_IMODE(base_metadata.st_mode) & 0o022
):
    raise SystemExit(f"unsafe runtime-mount bootstrap root: {base}")


def ensure_directory(path: str, mode: int, group_name: str | None = None) -> None:
    if not path.startswith("/") or path == "/":
        raise SystemExit("runtime-mount bootstrap path is invalid")
    current = base
    components = path.strip("/").split("/")
    service_gid = None
    if group_name is not None:
        try:
            service_gid = grp.getgrnam(group_name).gr_gid
        except KeyError:
            pass
    for index, component in enumerate(components):
        parent = current
        current = os.path.join(current, component)
        is_target = index == len(components) - 1
        create_mode = mode if is_target else 0o755
        # The installer always publishes the empty root:root transitional
        # directory. Only the controller may assign a service group.
        create_gid = 0
        if not os.path.lexists(current):
            os.mkdir(current, create_mode)
            os.chown(current, 0, create_gid)
            os.chmod(current, create_mode)
            fsync_directory(parent)
        metadata = os.lstat(current)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
        ):
            raise SystemExit(f"unsafe runtime-mount bootstrap directory: {current}")
        if not is_target:
            if metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                raise SystemExit(f"unsafe runtime-mount bootstrap ancestor: {current}")
            continue
        transitional_empty = (
            group_name is not None
            and metadata.st_gid == 0
            and stat.S_IMODE(metadata.st_mode) == 0o750
            and not os.listdir(current)
        )
        settled_gid = metadata.st_gid == (service_gid if service_gid is not None else 0)
        if group_name is not None and service_gid is None:
            settled_gid = False
        if (
            stat.S_IMODE(metadata.st_mode) != mode
            or (not settled_gid and not transitional_empty)
        ):
            raise SystemExit(f"unsafe runtime-mount bootstrap target: {current}")


for record in (
    ("/home/tradewave-mcp", 0o755, None),
    ("/var/lib/tradewave", 0o755, None),
    ("/var/lib/tradewave-mcp-runtime-lock", 0o750, "tradewave-mcp"),
    ("/var/lib/tradewave-api-runtime-lock", 0o750, "tradewave-api"),
    ("/run/tradewave-mcp-deploy", 0o755, None),
    ("/run/tradewave-mcp-verifier", 0o700, None),
    ("/etc/tmpfiles.d", 0o755, None),
):
    ensure_directory(*record)

payload = (
    b"d /run/lock/tradewave 0700 root root -\n"
    b"d /run/tradewave-mcp-deploy 0755 root root -\n"
    b"d /run/tradewave-mcp-verifier 0700 root root -\n"
)
config_parent = os.path.dirname(config_path)
config_name = os.path.basename(config_path)
parent_fd = os.open(
    config_parent,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
)
try:
    if not os.path.lexists(config_path):
        temporary = f".{config_name}.install-{os.getpid()}-{secrets.token_hex(8)}"
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(descriptor, view):]
                os.fchown(descriptor, 0, 0)
                os.fchmod(descriptor, 0o644)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(
                temporary,
                config_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
    metadata = os.lstat(config_path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o644
        or metadata.st_nlink != 1
    ):
        raise SystemExit("unsafe runtime-mount tmpfiles bootstrap")
    descriptor = os.open(config_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        content = bytearray()
        while len(content) <= len(payload):
            chunk = os.read(descriptor, min(4096, len(payload) + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if bytes(content) != payload:
            raise SystemExit("runtime-mount tmpfiles bootstrap differs from reviewed bytes")
    finally:
        os.close(descriptor)
finally:
    os.close(parent_fd)
PY
}

ensure_runtime_mount_bootstrap
if [ -z "$PREFIX" ]; then
  /usr/bin/systemd-tmpfiles --create "$TMPFILES_CONFIG" \
    || fail "could not materialize persistent MCP release runtime directories"
fi
ensure_runtime_mount_bootstrap
crash_point after_runtime_mount_bootstrap

/usr/bin/install -d -o root -g root -m 0755 \
  "$PREFIX/usr/local/libexec" "$PREFIX/usr/local/sbin" "$CONTROL_ROOT" "$SETS_ROOT"
for directory in "$CONTROL_ROOT" "$SETS_ROOT"; do
  [ -d "$directory" ] && [ ! -L "$directory" ] \
    && [ "$(stat -c '%U:%G %a' "$directory")" = "root:root 755" ] \
    || fail "unsafe control-plane directory: $directory"
done

# Fetch the reviewed commit from the one fixed canonical origin inside an
# ephemeral DynamicUser service. Root never parses a mutable/local Git object
# database and no replace refs, alternates, worktree attributes, or hooks exist.
FETCH_UUID=$(/usr/bin/python3.13 -I -B -S -c 'import uuid; print(uuid.uuid4())')
FETCH_NAME=tradewave-mcp-control-fetch-$FETCH_UUID
FETCH_RUNTIME=/run/$FETCH_NAME
FETCH_ROOT=/run/private/$FETCH_NAME
FETCH_UNIT=$FETCH_NAME.service
FETCH_SCRIPT='set -euo pipefail
root=$1
sha=$2
origin=$3
repo=$root/repository
export_root=$root/export
umask 077
/usr/bin/mkdir "$repo" "$export_root"
/usr/bin/git -C "$repo" init -q
/usr/bin/git -c protocol.file.allow=never -C "$repo" fetch -q --depth=1 --no-tags "$origin" "$sha"
fetched=$(/usr/bin/git -C "$repo" rev-parse --verify FETCH_HEAD^{commit})
[ "$fetched" = "$sha" ]
for path in \
  ops/launch_mcp_release.sh ops/mcp_start_guard_launcher.py \
  ops/deploy_mcp_release.sh ops/mcp_offline_wheels.py \
  ops/mcp_provision_bootstrap.py ops/mcp_service_env.py ops/mcp_start_guard.py \
  apiserver/provision_mcp_key.py requirements-mcp-provision.lock \
  ops/nginx/tradewave-developer-portal.conf \
  ops/systemd/tradewave-mcpserver-release.conf \
  ops/systemd/tradewave-mcpserver-release-fence.conf \
  ops/systemd/tradewave-mcpserver-legacy.service \
  ops/systemd/tradewave-mcpserver.service \
  ops/systemd/tradewave-apiserver-immutable.service \
  ops/systemd/tradewave-apiserver-release-fence.conf \
  ops/systemd/tradewave-apiserver-legacy.service \
  ops/verify_mcp_contract.py ops/verify_mcp_load.py
do
  [ "$(/usr/bin/git -C "$repo" cat-file -t "$sha:$path")" = blob ]
  /usr/bin/mkdir -p "$export_root/$(/usr/bin/dirname "$path")"
  /usr/bin/git -C "$repo" cat-file blob "$sha:$path" > "$export_root/$path"
done
'
/usr/bin/systemd-run --quiet --wait --pipe --collect --service-type=exec \
  --unit="$FETCH_UNIT" --description="Fetch reviewed TradeWave MCP control plane" \
  --property=DynamicUser=yes --property="RuntimeDirectory=$FETCH_NAME" \
  --property=RuntimeDirectoryMode=0700 --property=RuntimeDirectoryPreserve=yes \
  --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
  --property=ProtectHome=yes --property=PrivateTmp=yes --property=PrivateDevices=yes \
  --property=ProtectHostname=yes --property=ProtectClock=yes \
  --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
  --property=ProtectControlGroups=yes --property=ProtectKernelLogs=yes \
  --property=RestrictSUIDSGID=yes --property=RestrictNamespaces=yes \
  --property=LockPersonality=yes --property=SystemCallArchitectures=native \
  --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
  --property=CapabilityBoundingSet= --property=AmbientCapabilities= \
  --property=UMask=0077 --property=LimitCORE=0 --property=TasksMax=128 \
  --property=MemoryMax=512M --property="ReadWritePaths=$FETCH_RUNTIME" \
  --property="InaccessiblePaths=-/root -/home/flask" \
  /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
    GIT_NO_REPLACE_OBJECTS=1 \
    /usr/bin/bash --noprofile --norc -p -c "$FETCH_SCRIPT" fetch \
      "$FETCH_RUNTIME" "$REVIEWED_SHA" "$SOURCE_ORIGIN" \
  || fail "canonical origin did not provide the exact reviewed control-plane blobs"

# DynamicUser exposes RuntimeDirectory through a root-owned public symlink to
# /run/private and maps the backing directory to nobody:nogroup on the host.
# Validate that exact PID1-created topology, remove the public name, and only
# then take ownership of the private top directory.  /run/private is root-only,
# so no unprivileged identity can race this handoff after the unit exits.
[ -L "$FETCH_RUNTIME" ] \
  && [ "$(stat -c '%U:%G %h' "$FETCH_RUNTIME")" = "root:root 1" ] \
  && [ "$(readlink "$FETCH_RUNTIME")" = "private/$FETCH_NAME" ] \
  && [ "$(realpath -e -- "$FETCH_RUNTIME")" = "$FETCH_ROOT" ] \
  || fail "isolated reviewed-source RuntimeDirectory link is unsafe"
[ -d "$FETCH_ROOT" ] && [ ! -L "$FETCH_ROOT" ] \
  && [ "$(stat -c '%u:%g %a' "$FETCH_ROOT")" = "65534:65534 700" ] \
  || fail "isolated reviewed-source private RuntimeDirectory is unsafe"
rm -- "$FETCH_RUNTIME"
chown root:root "$FETCH_ROOT"
chmod 0700 "$FETCH_ROOT"
REVIEW_ROOT=$FETCH_ROOT/export
[ -d "$REVIEW_ROOT" ] && [ ! -L "$REVIEW_ROOT" ] \
  || fail "isolated reviewed-source export is unsafe"

# Read reviewed sources as bounded bytes, build a canonical manifest binding
# every asset and both stable bootstrap digests, fsync the complete generation,
# then publish its content-addressed directory with one rename. It is not live
# until CURRENT is switched later.
SET_DIGEST=$(/usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 /usr/bin/python3.13 -I -B -S - \
  "$SETS_ROOT" "$REVIEWED_SHA" \
  "$REVIEW_ROOT/ops/launch_mcp_release.sh:/usr/local/sbin/tradewave-mcp-release:0755" \
  "$REVIEW_ROOT/ops/mcp_start_guard_launcher.py:/usr/local/libexec/tradewave-mcp-start-guard.py:0755" \
  "$REVIEW_ROOT/ops/systemd/tradewave-mcpserver-release-fence.conf:/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf:0644" \
  "$REVIEW_ROOT/ops/systemd/tradewave-apiserver-release-fence.conf:/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf:0644" \
  "$REVIEW_ROOT/ops/launch_mcp_release.sh:release-launcher-bootstrap.sh:0444" \
  "$REVIEW_ROOT/ops/mcp_start_guard_launcher.py:start-guard-bootstrap.py:0444" \
  "$REVIEW_ROOT/ops/deploy_mcp_release.sh:deploy-mcp-release.sh:0555" \
  "$REVIEW_ROOT/ops/mcp_offline_wheels.py:mcp-offline-wheels.py:0555" \
  "$REVIEW_ROOT/ops/mcp_provision_bootstrap.py:mcp-provision-bootstrap.py:0555" \
  "$REVIEW_ROOT/ops/mcp_service_env.py:mcp-service-env.py:0555" \
  "$REVIEW_ROOT/ops/mcp_start_guard.py:mcp-start-guard.py:0555" \
  "$REVIEW_ROOT/apiserver/provision_mcp_key.py:provision-mcp-key.py:0555" \
  "$REVIEW_ROOT/requirements-mcp-provision.lock:requirements-mcp-provision.lock:0444" \
  "$REVIEW_ROOT/ops/nginx/tradewave-developer-portal.conf:tradewave-developer-portal.conf:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-mcpserver-release.conf:tradewave-mcpserver-release.conf:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-mcpserver-release-fence.conf:tradewave-mcpserver-release-fence.conf:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-mcpserver-legacy.service:tradewave-mcpserver-legacy.service:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-mcpserver.service:tradewave-mcpserver.service:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-apiserver-immutable.service:tradewave-apiserver-immutable.service:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-apiserver-release-fence.conf:tradewave-apiserver-release-fence.conf:0444" \
  "$REVIEW_ROOT/ops/systemd/tradewave-apiserver-legacy.service:tradewave-apiserver-legacy.service:0444" \
  "$REVIEW_ROOT/ops/verify_mcp_contract.py:verify_mcp_contract.py:0555" \
  "$REVIEW_ROOT/ops/verify_mcp_load.py:verify_mcp_load.py:0555" <<'PY'
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import uuid

sets_root = os.path.abspath(sys.argv[1])
source_sha = sys.argv[2]
bootstrap_specs = sys.argv[3:7]
asset_specs = sys.argv[7:]
max_bytes = 16 * 1024 * 1024
temp_re = re.compile(r"\.new-([0-9a-f-]{36})")
expected_names = {
    "deploy-mcp-release.sh", "mcp-offline-wheels.py", "mcp-provision-bootstrap.py",
    "mcp-service-env.py", "mcp-start-guard.py", "provision-mcp-key.py",
    "release-launcher-bootstrap.sh", "start-guard-bootstrap.py",
    "requirements-mcp-provision.lock", "tradewave-developer-portal.conf",
    "tradewave-mcpserver-release.conf", "tradewave-mcpserver-release-fence.conf",
    "tradewave-mcpserver-legacy.service",
    "tradewave-mcpserver.service",
    "tradewave-apiserver-immutable.service",
    "tradewave-apiserver-release-fence.conf",
    "tradewave-apiserver-legacy.service",
    "verify_mcp_contract.py", "verify_mcp_load.py",
}


def die(message):
    raise SystemExit(f"control-plane set publication: {message}")


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_source(path):
    if path != os.path.abspath(path):
        die(f"source is not absolute: {path}")
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1 or before.st_size > max_bytes
    ):
        die(f"source is not a bounded single-link regular file: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            die(f"source changed before read: {path}")
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                die(f"source is oversized: {path}")
        after = os.fstat(fd)
        named = os.lstat(path)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_size, value.st_ctime_ns, value.st_mtime_ns
        )
        if identity(opened) != identity(after) or identity(opened) != identity(named):
            die(f"source changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def parse(encoded, *, asset):
    source, name, mode_text = encoded.rsplit(":", 2)
    mode = int(mode_text, 8)
    if asset:
        if name not in expected_names or "/" in name or mode not in {0o444, 0o555}:
            die(f"invalid fixed asset specification: {name}")
    else:
        expected_bootstraps = {
            "/usr/local/sbin/tradewave-mcp-release",
            "/usr/local/libexec/tradewave-mcp-start-guard.py",
            "/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf",
            "/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf",
        }
        expected_mode = 0o644 if name.endswith(".conf") else 0o755
        if name not in expected_bootstraps or mode != expected_mode:
            die(f"invalid fixed bootstrap specification: {name}")
    return source, name, mode, read_source(source)


def verify_final(path, manifest_bytes, assets):
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0 or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o555
    ):
        die("existing content-addressed set directory is unsafe")
    if set(os.listdir(path)) != expected_names | {"manifest.json"}:
        die("existing content-addressed set has unexpected children")
    expected = {name: (mode, payload) for _, name, mode, payload in assets}
    expected["manifest.json"] = (0o444, manifest_bytes)
    for name, (mode, payload) in expected.items():
        child = os.path.join(path, name)
        child_meta = os.lstat(child)
        if (
            not stat.S_ISREG(child_meta.st_mode) or stat.S_ISLNK(child_meta.st_mode)
            or child_meta.st_uid != 0 or child_meta.st_gid != 0
            or stat.S_IMODE(child_meta.st_mode) != mode or child_meta.st_nlink != 1
        ):
            die(f"existing set asset metadata is unsafe: {name}")
        with open(child, "rb", buffering=0) as handle:
            actual = handle.read(max_bytes + 1)
        if actual != payload:
            die(f"existing content-addressed set bytes differ: {name}")


sets_meta = os.lstat(sets_root)
if (
    not stat.S_ISDIR(sets_meta.st_mode) or stat.S_ISLNK(sets_meta.st_mode)
    or sets_meta.st_uid != 0 or sets_meta.st_gid != 0
    or stat.S_IMODE(sets_meta.st_mode) != 0o755
):
    die("sets root is unsafe")

# Crash leftovers were never selected. Remove only exact root-owned temporary
# generation directories and refuse any surprising object.
for name in os.listdir(sets_root):
    if not name.startswith(".new-"):
        continue
    match = temp_re.fullmatch(name)
    if match is None or str(uuid.UUID(match.group(1))) != match.group(1):
        die("malformed temporary generation name")
    path = os.path.join(sets_root, name)
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0 or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) not in {0o700, 0o555}
    ):
        die("unsafe temporary generation directory")
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        for child in files:
            child_path = os.path.join(root, child)
            child_meta = os.lstat(child_path)
            if not stat.S_ISREG(child_meta.st_mode) or stat.S_ISLNK(child_meta.st_mode) or child_meta.st_uid != 0:
                die("unsafe temporary generation child")
            os.unlink(child_path)
        for child in directories:
            child_path = os.path.join(root, child)
            child_meta = os.lstat(child_path)
            if not stat.S_ISDIR(child_meta.st_mode) or stat.S_ISLNK(child_meta.st_mode) or child_meta.st_uid != 0:
                die("unsafe temporary generation subtree")
            os.chmod(child_path, 0o700)
            os.rmdir(child_path)
    os.chmod(path, 0o700)
    os.rmdir(path)
    fsync_dir(sets_root)

bootstraps = [parse(item, asset=False) for item in bootstrap_specs]
assets = [parse(item, asset=True) for item in asset_specs]
if {item[1] for item in assets} != expected_names:
    die("fixed asset specification is incomplete")
manifest = {
    "schema": 1,
    "source": {"commit_sha": source_sha},
    "bootstraps": {
        name: {"mode": mode, "sha256": hashlib.sha256(payload).hexdigest()}
        for _, name, mode, payload in bootstraps
    },
    "files": {
        name: {"mode": mode, "sha256": hashlib.sha256(payload).hexdigest()}
        for _, name, mode, payload in assets
    },
}
manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
digest = hashlib.sha256(manifest_bytes).hexdigest()
final = os.path.join(sets_root, digest)
if os.path.lexists(final):
    verify_final(final, manifest_bytes, assets)
    print(digest)
    raise SystemExit(0)

temporary = os.path.join(sets_root, f".new-{uuid.uuid4()}")
os.mkdir(temporary, 0o700)
os.chown(temporary, 0, 0)
os.chmod(temporary, 0o700)
try:
    for _, name, mode, payload in [*assets, ("", "manifest.json", 0o444, manifest_bytes)]:
        path = os.path.join(temporary, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view):]
            os.fchown(fd, 0, 0)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
    fsync_dir(temporary)
    os.chmod(temporary, 0o555)
    fsync_dir(temporary)
    os.rename(temporary, final)
    fsync_dir(sets_root)
except BaseException:
    # Leave a bounded .new UUID for a deterministic, validated retry cleanup.
    raise
verify_final(final, manifest_bytes, assets)
print(digest)
PY
) || fail "could not publish a sealed MCP control-plane generation"
[[ "$SET_DIGEST" =~ ^[0-9a-f]{64}$ ]] || fail "control-plane publisher returned an invalid digest"
SET_TARGET=sets/$SET_DIGEST
SEALED_SET=$SETS_ROOT/$SET_DIGEST
[ -d "$SEALED_SET" ] && [ ! -L "$SEALED_SET" ] \
  || fail "published control-plane set is missing"
[[ "$FETCH_ROOT" =~ ^/run/private/tradewave-mcp-control-fetch-[0-9a-f-]{36}$ ]] \
  && [ -d "$FETCH_ROOT" ] && [ ! -L "$FETCH_ROOT" ] \
  || fail "refusing unsafe reviewed-source workspace cleanup"
rm -rf --one-file-system -- "$FETCH_ROOT"
crash_point after_set_publish

install_bootstrap() {  # <source> <destination> <mode>
  /usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 /usr/bin/python3.13 -I -B -S - \
    "$1" "$2" "$CURRENT" "$3" <<'PY'
import hashlib
import os
import secrets
import stat
import sys

source, destination, current, mode_text = sys.argv[1:]
expected_mode = int(mode_text, 8)
if expected_mode not in {0o644, 0o755}:
    raise SystemExit("invalid stable bootstrap mode")
limit = 16 * 1024 * 1024


def read(path, *, installed=False):
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1 or before.st_size > limit
        or (installed and (before.st_uid != 0 or before.st_gid != 0 or stat.S_IMODE(before.st_mode) != expected_mode))
    ):
        raise SystemExit(f"unsafe bootstrap file: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        payload = b""
        while len(payload) <= limit:
            chunk = os.read(fd, limit + 1 - len(payload))
            if not chunk:
                break
            payload += chunk
        after = os.fstat(fd)
        named = os.lstat(path)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_size, value.st_ctime_ns, value.st_mtime_ns
        )
        if len(payload) > limit or identity(opened) != identity(after) or identity(opened) != identity(named):
            raise SystemExit(f"bootstrap changed while read: {path}")
        return payload
    finally:
        os.close(fd)


payload = read(source)
parent = os.path.dirname(destination)
parent_meta = os.lstat(parent)
if (
    not stat.S_ISDIR(parent_meta.st_mode) or stat.S_ISLNK(parent_meta.st_mode)
    or parent_meta.st_uid != 0 or parent_meta.st_gid != 0
    or stat.S_IMODE(parent_meta.st_mode) & 0o022
):
    raise SystemExit("bootstrap destination parent is unsafe")
if os.path.lexists(destination):
    try:
        existing = read(destination, installed=True)
    except (OSError, SystemExit):
        if os.path.lexists(current):
            raise
        existing = None
    if existing == payload:
        raise SystemExit(0)
    if os.path.lexists(current):
        raise SystemExit("stable bootstrap changes are forbidden after atomic control-plane activation")
temporary = f".{os.path.basename(destination)}.install-{os.getpid()}-{secrets.token_hex(8)}"
parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
try:
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view):]
        os.fchown(fd, 0, 0)
        os.fchmod(fd, expected_mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, os.path.basename(destination), src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    os.fsync(parent_fd)
finally:
    try:
        os.unlink(temporary, dir_fd=parent_fd)
    except FileNotFoundError:
        pass
    os.close(parent_fd)
if read(destination, installed=True) != payload:
    raise SystemExit("installed bootstrap bytes differ")
PY
}

# First migration replaces the legacy launcher before the guard. With no atomic
# CURRENT yet the new launcher fails closed; the already-running service retains
# its old guard until the second replacement. Once CURRENT exists, bootstrap
# bytes are immutable and only set-pointer publication is permitted.
install_bootstrap "$SEALED_SET/release-launcher-bootstrap.sh" "$LAUNCHER" 0755 \
  || fail "could not install stable MCP release launcher"
crash_point after_launcher_bootstrap
install_bootstrap "$SEALED_SET/start-guard-bootstrap.py" "$PRODUCTION_GUARD" 0755 \
  || fail "could not install stable MCP start-guard launcher"
crash_point after_guard_bootstrap
install -d -o root -g root -m 0755 "$(dirname "$PRODUCTION_FENCE")"
install_bootstrap "$SEALED_SET/tradewave-mcpserver-release-fence.conf" \
  "$PRODUCTION_FENCE" 0644 \
  || fail "could not install stable MCP release fence"
crash_point after_release_fence
install -d -o root -g root -m 0755 "$(dirname "$PRODUCTION_API_FENCE")"
install_bootstrap "$SEALED_SET/tradewave-apiserver-release-fence.conf" \
  "$PRODUCTION_API_FENCE" 0644 \
  || fail "could not install stable API release fence"
crash_point after_api_release_fence
if [ -z "$PREFIX" ]; then
  systemctl daemon-reload || fail "could not load the stable MCP release fence"
  if systemctl cat tradewave-mcpserver.service --no-pager >/dev/null 2>&1; then
    [ "$(systemctl show tradewave-mcpserver.service --property=ExecCondition --value | \
      grep -o 'path=/usr/bin/python3.13' | wc -l)" -eq 1 ] \
      || fail "effective MCP service did not load the one stable release fence"
  fi
  if systemctl cat tradewave-apiserver.service --no-pager >/dev/null 2>&1; then
    [ "$(systemctl show tradewave-apiserver.service --property=ExecCondition --value | \
      grep -o 'path=/usr/bin/python3.13' | wc -l)" -eq 1 ] \
      || fail "effective API service did not load the one stable release fence"
  fi
fi
crash_point after_release_fence_reload

atomic_pointer() {  # <target> <path>
  /usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3.13 -I -B -S - "$1" "$2" <<'PY'
import os
import re
import secrets
import stat
import sys

target, path = sys.argv[1:]
if re.fullmatch(r"sets/[0-9a-f]{64}", target) is None:
    raise SystemExit("invalid atomic control-plane pointer target")
parent = os.path.dirname(path)
metadata = os.lstat(parent)
if (
    not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o755
):
    raise SystemExit("unsafe atomic control-plane pointer parent")
temporary = os.path.join(parent, f".{os.path.basename(path)}.install-{os.getpid()}-{secrets.token_hex(8)}")
if os.path.lexists(path):
    old = os.lstat(path)
    if not stat.S_ISLNK(old.st_mode) or old.st_uid != 0 or old.st_gid != 0 or old.st_nlink != 1:
        raise SystemExit("unsafe existing atomic control-plane pointer")
try:
    os.symlink(target, temporary)
    os.lchown(temporary, 0, 0)
    os.replace(temporary, path)
    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
}

OLD_TARGET=""
if [ -e "$CURRENT" ] && [ ! -L "$CURRENT" ]; then
  fail "$CURRENT is not an atomic control-plane symlink"
fi
if [ -L "$CURRENT" ]; then
  [ "$(stat -c '%U:%G' "$CURRENT")" = root:root ] \
    || fail "$CURRENT is not root-owned"
  OLD_TARGET=$(readlink "$CURRENT")
  [[ "$OLD_TARGET" =~ ^sets/[0-9a-f]{64}$ ]] \
    || fail "$CURRENT has an invalid stored target"
fi
if [ -n "$OLD_TARGET" ] && [ "$OLD_TARGET" != "$SET_TARGET" ]; then
  atomic_pointer "$OLD_TARGET" "$PREVIOUS" \
    || fail "could not retain previous MCP control-plane generation"
  crash_point after_previous_pointer
fi
atomic_pointer "$SET_TARGET" "$CURRENT" \
  || fail "could not atomically select the MCP control-plane generation"
crash_point after_current_pointer

if [ -z "$PREFIX" ]; then
  "$LAUNCHER" --verify-control-plane \
    || fail "installed atomic MCP control plane failed its bootstrap verification"
fi

echo "PASS: atomic MCP release control plane $SET_DIGEST installed; invoke /usr/local/sbin/tradewave-mcp-release <lowercase-40-SHA>"
