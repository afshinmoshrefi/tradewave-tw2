#!/usr/bin/bash -p
# Stable root bootstrap for one atomically selected, sealed MCP control-plane set.
set +x
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP

SELF=/usr/local/sbin/tradewave-mcp-release
PRODUCTION_GUARD=/usr/local/libexec/tradewave-mcp-start-guard.py
PRODUCTION_FENCE=/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf
PRODUCTION_API_FENCE=/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf
CONTROL_ROOT=/usr/local/libexec/tradewave-mcp-release-control
CONTROL_CURRENT=$CONTROL_ROOT/current
CONTROL_SETS=$CONTROL_ROOT/sets

[ "$EUID" -eq 0 ] || { echo "FAIL: run as root" >&2; exit 1; }
[ "$0" = "$SELF" ] || { echo "FAIL: use the fixed installed MCP release launcher" >&2; exit 1; }
VERIFY_ONLY=0
[ "$#" -eq 1 ] || { echo "usage: $SELF <lowercase-40-sha|--rollback>" >&2; exit 2; }
if [ "$1" = --verify-control-plane ]; then
  VERIFY_ONLY=1
elif [ "$1" != --rollback ] && [[ ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL: release target must be an exact lowercase 40-character commit SHA or --rollback" >&2
  exit 2
fi

# Resolve and validate one complete immutable generation before asking PID1 to
# execute anything. The selected real directory remains coherent even if a
# later installer atomically advances the current pointer.
ASSET_ROOT=$(/usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 /usr/bin/python3.13 -I -B -S - \
  "$SELF" "$PRODUCTION_GUARD" "$PRODUCTION_FENCE" "$PRODUCTION_API_FENCE" \
  "$CONTROL_ROOT" "$CONTROL_CURRENT" "$CONTROL_SETS" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys

self_path, guard_path, fence_path, api_fence_path, control_root, current, sets_root = sys.argv[1:]
max_bytes = 16 * 1024 * 1024
hash_re = re.compile(r"[0-9a-f]{64}")
target_re = re.compile(r"sets/([0-9a-f]{64})")
expected_files = {
    "deploy-mcp-release.sh": 0o555,
    "mcp-offline-wheels.py": 0o555,
    "mcp-provision-bootstrap.py": 0o555,
    "mcp-service-env.py": 0o555,
    "mcp-start-guard.py": 0o555,
    "release-launcher-bootstrap.sh": 0o444,
    "start-guard-bootstrap.py": 0o444,
    "provision-mcp-key.py": 0o555,
    "requirements-mcp-provision.lock": 0o444,
    "tradewave-developer-portal.conf": 0o444,
    "tradewave-mcpserver-release.conf": 0o444,
    "tradewave-mcpserver-release-fence.conf": 0o444,
    "tradewave-mcpserver-legacy.service": 0o444,
    "tradewave-mcpserver.service": 0o444,
    "tradewave-apiserver-immutable.service": 0o444,
    "tradewave-apiserver-release-fence.conf": 0o444,
    "tradewave-apiserver-legacy.service": 0o444,
    "verify_mcp_contract.py": 0o555,
    "verify_mcp_load.py": 0o555,
}
expected_bootstraps = {
    self_path: 0o755,
    guard_path: 0o755,
    fence_path: 0o644,
    api_fence_path: 0o644,
}


def die(message):
    raise SystemExit(f"MCP control-plane launcher: {message}")


def secure_ancestors(path):
    current_path = "/"
    for component in os.path.dirname(path).strip("/").split("/"):
        if component:
            current_path = os.path.join(current_path, component)
        metadata = os.lstat(current_path)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            die(f"unsafe trusted ancestor: {current_path}")


def directory(path, mode):
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        die(f"unsafe trusted directory: {path}")


def regular(path, mode):
    secure_ancestors(path)
    before = os.lstat(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_uid != 0
            or opened.st_gid != 0
            or stat.S_IMODE(opened.st_mode) != mode
            or opened.st_nlink != 1
            or opened.st_size > max_bytes
        ):
            die(f"unsafe trusted regular file: {path}")
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                die(f"oversized trusted regular file: {path}")
        after = os.fstat(fd)
        named = os.lstat(path)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_size, value.st_ctime_ns, value.st_mtime_ns
        )
        if identity(opened) != identity(after) or identity(opened) != identity(named):
            die(f"trusted regular file changed while read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def record(value, mode, label):
    if not isinstance(value, dict) or set(value) != {"mode", "sha256"}:
        die(f"invalid manifest record: {label}")
    if type(value.get("mode")) is not int or value["mode"] != mode:
        die(f"invalid manifest mode: {label}")
    digest = value.get("sha256")
    if not isinstance(digest, str) or hash_re.fullmatch(digest) is None:
        die(f"invalid manifest digest: {label}")
    return digest


if sys.executable != "/usr/bin/python3.13" or os.path.realpath(sys.executable) != "/usr/bin/python3.13":
    die("unexpected control-plane verifier interpreter")
directory(control_root, 0o755)
directory(sets_root, 0o755)
pointer = os.lstat(current)
target = os.readlink(current)
match = target_re.fullmatch(target)
if (
    not stat.S_ISLNK(pointer.st_mode)
    or pointer.st_uid != 0
    or pointer.st_gid != 0
    or pointer.st_nlink != 1
    or match is None
):
    die("atomic current pointer is unsafe")
manifest_digest = match.group(1)
selected = os.path.join(control_root, target)
expected_selected = os.path.join(sets_root, manifest_digest)
if selected != expected_selected or os.path.realpath(selected) != expected_selected:
    die("atomic current pointer escapes the sealed set root")
directory(selected, 0o555)
raw = regular(os.path.join(selected, "manifest.json"), 0o444)
if hashlib.sha256(raw).hexdigest() != manifest_digest:
    die("manifest digest does not bind its selected set")
try:
    manifest = json.loads(raw.decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError):
    die("manifest is invalid JSON")
if raw != (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode():
    die("manifest is not canonical JSON")
if not isinstance(manifest, dict) or set(manifest) != {"bootstraps", "files", "schema", "source"}:
    die("manifest schema is invalid")
if type(manifest.get("schema")) is not int or manifest["schema"] != 1:
    die("manifest version is unsupported")
files = manifest.get("files")
bootstraps = manifest.get("bootstraps")
source = manifest.get("source")
if (
    not isinstance(source, dict)
    or set(source) != {"commit_sha"}
    or not isinstance(source.get("commit_sha"), str)
    or re.fullmatch(r"[0-9a-f]{40}", source["commit_sha"]) is None
):
    die("manifest source commit is invalid")
if not isinstance(files, dict) or set(files) != set(expected_files):
    die("manifest asset set is invalid")
if not isinstance(bootstraps, dict) or set(bootstraps) != set(expected_bootstraps):
    die("manifest bootstrap set is invalid")
if set(os.listdir(selected)) != set(expected_files) | {"manifest.json"}:
    die("selected set has unexpected children")
for name, mode in expected_files.items():
    payload = regular(os.path.join(selected, name), mode)
    if hashlib.sha256(payload).hexdigest() != record(files[name], mode, name):
        die(f"asset digest mismatch: {name}")
for path, mode in expected_bootstraps.items():
    payload = regular(path, mode)
    if hashlib.sha256(payload).hexdigest() != record(bootstraps[path], mode, path):
        die(f"bootstrap digest mismatch: {path}")
print(selected)
PY
) || { echo "FAIL: trusted MCP control-plane set verification failed" >&2; exit 1; }

case "$ASSET_ROOT" in
  "$CONTROL_SETS"/[0-9a-f][0-9a-f]*) ;;
  *) echo "FAIL: trusted MCP control-plane resolver returned an invalid path" >&2; exit 1 ;;
esac
CONTROLLER=$ASSET_ROOT/deploy-mcp-release.sh
if [ "$VERIFY_ONLY" = 1 ]; then
  echo "PASS: coherent sealed MCP control-plane set ${ASSET_ROOT##*/}"
  exit 0
fi

unit_uuid=$(/usr/bin/env -i HOME=/nonexistent PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  /usr/bin/python3.13 -I -B -S -c 'import uuid; print(uuid.uuid4())')
unit="tradewave-mcp-deploy-$unit_uuid.service"

exec /usr/bin/systemd-run --quiet --wait --pipe --collect --service-type=exec \
  --unit="$unit" --description="Trusted TradeWave MCP release controller" \
  --setenv="TW_MCP_DEPLOY_UNIT=$unit" \
  --setenv=PATH=/usr/sbin:/usr/bin:/sbin:/bin --setenv=HOME=/nonexistent \
  --setenv=LANG=C.UTF-8 --setenv=LC_ALL=C.UTF-8 \
  --property="UnsetEnvironment=BASH_ENV ENV CDPATH GLOBIGNORE HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONWARNINGS TW_MCP_RELEASE_HOME TW_MCP_SECRETS TW_MCP_RUNTIME_ENV TW_MCP_START_GUARD TW_MCP_VERIFIER_ENV TW_MCP_KEY_PENDING_STATE TW_MCP_TX_ROOT TW_MCP_RELEASE_LOCK_FD TW_MCP_VERIFY_TOKEN TW_MCP_EXPECT_AUTHORIZATION_SERVER TW_MCP_TEST_CRASH_AT TW_MCP_TEST_FAIL_JOURNAL_FSYNC_AT TW_MCP_TEST_FAIL_JOURNAL_WRITE_AT TW_MCP_TEST_FAIL_SYNCFS_AT TW_MCP_TEST_KILL_JOURNAL_AT GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM GIT_CONFIG_COUNT GIT_SSH GIT_SSH_COMMAND GIT_ASKPASS SSH_ASKPASS GIT_TERMINAL_PROMPT GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM GIT_NAMESPACE GIT_REPLACE_REF_BASE" \
  --property=NoNewPrivileges=yes --property=ProtectSystem=strict \
  --property=ProtectHome=read-only \
  --property="ReadWritePaths=-/home/tradewave-mcp -/etc/systemd/system -/etc/nginx -/etc/tradewave -/var/lib/tradewave -/var/lib/tradewave-mcp-runtime-lock -/var/lib/tradewave-api-runtime-lock -/run/lock/tradewave -/run/tradewave-mcp-deploy -/run/tradewave-mcp-verifier" \
  --property="InaccessiblePaths=-/root -/home/flask" \
  --property=PrivateTmp=yes --property=PrivateDevices=yes \
  --property=ProtectHostname=yes --property=ProtectClock=yes \
  --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
  --property=ProtectControlGroups=yes --property=ProtectKernelLogs=yes \
  --property=RestrictSUIDSGID=yes --property=RestrictNamespaces=yes \
  --property=LockPersonality=yes --property=SystemCallArchitectures=native \
  --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK" \
  --property=UMask=0077 --property=KillMode=control-group \
  --property=LimitCORE=0 \
  --property=TimeoutStopSec=30s --property=StandardOutput=journal+console \
  --property=StandardError=journal+console \
  /usr/bin/bash --noprofile --norc -p "$CONTROLLER" "$1"
