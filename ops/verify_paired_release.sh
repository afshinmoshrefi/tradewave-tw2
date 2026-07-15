#!/usr/bin/env bash
# Target-side, post-commit verifier for one exact immutable API + MCP release.
# Arguments: <lowercase-40-sha> <canonical-api-host> <canonical-mcp-host>.
# This file is streamed to the app host by verify_deploy.sh; it never retains or
# exercises a verifier/customer bearer after the rollback-capable transaction.
set +x
set -Eeuo pipefail
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP

sha=$1
api_host=$2
mcp_host=$3
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "FAIL: invalid remote release SHA" >&2; exit 1; }

MCP_HOME=/home/tradewave-mcp
RELEASE_ROOT=$MCP_HOME/releases
CURRENT=$MCP_HOME/current
BUNDLE=$RELEASE_ROOT/mcp-$sha
MCP_ENV=/etc/tradewave/mcpserver.env
API_ENV=/etc/tradewave/apiserver.env
PLATFORM_ENV=/etc/tradewave/secrets.env
ROTATION=/var/lib/tradewave/mcp-key-rotation.json
TX_ROOT=/var/lib/tradewave/mcp-release-transactions
RELEASE_LOCK=/run/lock/tradewave/mcp-release.lock
MCP_RUNTIME_LOCK=/var/lib/tradewave-mcp-runtime-lock/runtime.lock
API_RUNTIME_LOCK=/var/lib/tradewave-api-runtime-lock/runtime.lock
MCP_UNIT=/etc/systemd/system/tradewave-mcpserver.service
MCP_FENCE=/etc/systemd/system/tradewave-mcpserver.service.d/10-release-fence.conf
MCP_MARKER=/etc/systemd/system/tradewave-mcpserver.service.d/20-immutable-release.conf
API_UNIT=/etc/systemd/system/tradewave-apiserver.service
API_FENCE=/etc/systemd/system/tradewave-apiserver.service.d/10-mcp-release-fence.conf

die() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "  PASS  $*"; }
clean_python() {
  env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 /usr/bin/python3.13 -I -B -S "$@"
}
expect_property() {
  local unit=$1 name=$2 expected=$3 actual
  actual=$(systemctl show "$unit" --property="$name" --value)
  [ "$actual" = "$expected" ] \
    || die "$unit $name is '$actual', want '$expected'"
}
require_file_metadata() {
  local path=$1 wanted=$2
  [ -f "$path" ] && [ ! -L "$path" ] || die "$path is not a regular file"
  [ "$(stat -c '%U:%G %a %h' "$path")" = "$wanted" ] \
    || die "$path metadata is not $wanted"
}
require_empty_private_root() {
  local root=$1
  [ ! -e "$root" ] && return 0
  [ -d "$root" ] && [ ! -L "$root" ] || die "$root is not a real directory"
  [ "$(stat -c '%U:%G %a' "$root")" = "root:root 700" ] \
    || die "$root is not root:root mode 0700"
  [ -z "$(find "$root" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || die "$root retains a release-verifier artifact"
}

# Hold the controller lock for the entire observation so the evidence cannot be
# mixed with a new transaction. The journal must already have been durably GC'd.
require_file_metadata "$RELEASE_LOCK" "root:root 600 1"
[ "$(stat -c '%s' "$RELEASE_LOCK")" = 0 ] || die "release lock file is not empty"
exec 9<>"$RELEASE_LOCK"
flock --exclusive --nonblock 9 || die "a release transaction is still running"
[ -d "$TX_ROOT" ] && [ ! -L "$TX_ROOT" ] \
  || die "the durable release-journal root is absent or unsafe"
[ "$(stat -c '%U:%G %a' "$TX_ROOT")" = "root:root 700" ] \
  || die "the durable release-journal root is not root:root mode 0700"
[ -z "$(find "$TX_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ] \
  || die "the durable release journal is not empty"
pass "release lock is quiescent and the authoritative journal is empty"

[ -L "$CURRENT" ] || die "$CURRENT is not a symlink"
[ "$(stat -c '%U:%G %h' "$CURRENT")" = "root:root 1" ] \
  || die "$CURRENT symlink metadata is unsafe"
[ "$(readlink "$CURRENT")" = "releases/mcp-$sha" ] \
  || die "$CURRENT does not store the exact release-relative target"
[ "$(readlink -f "$CURRENT")" = "$BUNDLE" ] \
  || die "$CURRENT does not resolve to $BUNDLE"
[ -d "$BUNDLE" ] && [ ! -L "$BUNDLE" ] || die "$BUNDLE is not a real directory"

# Authenticate the complete frozen tree using only isolated system Python. The
# candidate supplies no helper code before its bytes and metadata are verified.
clean_python - "$BUNDLE" "$sha" <<'PY'
import hashlib
import os
import re
import stat
import struct
import sys

root, expected_sha = sys.argv[1:]
if os.path.abspath(root) != root or os.path.basename(root) != f"mcp-{expected_sha}":
    raise SystemExit("release bundle path is not canonical")
seal_path = os.path.join(root, ".sealed")
seal_stat = os.lstat(seal_path)
if (
    not stat.S_ISREG(seal_stat.st_mode)
    or stat.S_ISLNK(seal_stat.st_mode)
    or seal_stat.st_uid != 0
    or seal_stat.st_gid != 0
    or stat.S_IMODE(seal_stat.st_mode) != 0o444
    or seal_stat.st_nlink != 1
    or seal_stat.st_size > 64 * 1024
):
    raise SystemExit("release seal metadata is unsafe")
raw_seal = open(seal_path, "rb", buffering=0).read()
try:
    seal_text = raw_seal.decode("ascii")
except UnicodeDecodeError as exc:
    raise SystemExit("release seal is not ASCII") from exc
if not seal_text.endswith("\n") or "\r" in seal_text:
    raise SystemExit("release seal encoding is not canonical")
values = {}
for number, line in enumerate(seal_text.splitlines(), 1):
    if line.count("=") != 1:
        raise SystemExit(f"malformed release seal line {number}")
    key, value = line.split("=", 1)
    if key in values or not value:
        raise SystemExit(f"duplicate/empty release seal line {number}")
    values[key] = value
expected_fields = {
    "release_sha", "bundle_content_sha256",
    "runtime_lock_sha256", "runtime_wheel_manifest_sha256",
    "runtime_manifest_sha256", "runtime_tree_sha256",
    "gateway_lock_sha256", "gateway_wheel_manifest_sha256",
    "gateway_manifest_sha256", "gateway_tree_sha256",
    "provision_lock_sha256", "provision_wheel_manifest_sha256",
    "provision_manifest_sha256", "provision_tree_sha256",
}
if set(values) != expected_fields or values.get("release_sha") != expected_sha:
    raise SystemExit("release seal schema/SHA is not exact")
if not re.fullmatch(r"[0-9a-f]{40}", values["release_sha"]):
    raise SystemExit("release seal SHA is invalid")
for key in expected_fields - {"release_sha"}:
    if not re.fullmatch(r"[0-9a-f]{64}", values[key]):
        raise SystemExit(f"release seal digest is invalid: {key}")

expected_links = {
    os.path.join(root, name, "bin", "python")
    for name in ("venv", "gateway-venv", "provision-venv")
}
seen_links = set()
entries = []

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
        kind = b"L"
    elif stat.S_ISREG(metadata.st_mode):
        if metadata.st_nlink != 1:
            raise SystemExit(f"bundle has a hard-linked file: {relative}")
        kind = b"F"
    elif stat.S_ISDIR(metadata.st_mode):
        kind = b"D"
    else:
        raise SystemExit(f"bundle has a special file: {relative}")
    # Linux symlink mode bits are not a permission policy (lstat reports 0777).
    # Their security boundary is instead the exact allowlisted path, exact
    # absolute interpreter target, resolved target, and root lchown above.
    if kind != b"L":
        expected_mode = 0o555 if kind == b"D" or metadata.st_mode & 0o111 else 0o444
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise SystemExit(f"bundle entry mode drift: {relative}")
    entries.append((os.fsencode(relative), kind, metadata))
    if kind == b"D":
        with os.scandir(path) as iterator:
            children = sorted(iterator, key=lambda item: os.fsencode(item.name))
        for child in children:
            if child.name == ".git":
                raise SystemExit("bundle contains forbidden Git metadata")
            child_relative = child.name if relative == "." else f"{relative}/{child.name}"
            visit(os.path.join(path, child.name), child_relative)

visit(root, ".")
if seen_links != expected_links:
    raise SystemExit("bundle lacks the three exact interpreter links")
for relative in (
    "src/mcpserver/server.py",
    "src/apiserver/app.py",
    "src/ops/systemd/tradewave-mcpserver.service",
    "src/ops/systemd/tradewave-apiserver-immutable.service",
):
    metadata = os.lstat(os.path.join(root, relative))
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SystemExit(f"required sealed source is not exact: {relative}")

# Reproduce the controller's TW_MCP_BUNDLE_CONTENT_V1 digest, excluding only
# the root .sealed file that contains the digest itself.
content_entries = []
def collect(relative: bytes) -> None:
    path = os.fsencode(root) if relative == b"." else os.path.join(os.fsencode(root), relative)
    metadata = os.lstat(path)
    if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        kind = b"D"
    elif stat.S_ISREG(metadata.st_mode):
        kind = b"F"
    elif stat.S_ISLNK(metadata.st_mode):
        kind = b"L"
    else:
        raise SystemExit(f"unsupported bundle entry type: {os.fsdecode(relative)}")
    content_entries.append((relative, kind, metadata))
    if kind == b"D":
        for entry in sorted(os.scandir(path), key=lambda item: item.name):
            child = entry.name if relative == b"." else os.path.join(relative, entry.name)
            if child == b".sealed":
                continue
            collect(child)

collect(b".")
digest = hashlib.sha256(b"TW_MCP_BUNDLE_CONTENT_V1\0")
for relative, kind, captured in sorted(content_entries, key=lambda item: item[0]):
    path = os.fsencode(root) if relative == b"." else os.path.join(os.fsencode(root), relative)
    digest.update(kind)
    digest.update(struct.pack(">I", stat.S_IMODE(captured.st_mode)))
    digest.update(struct.pack(">Q", len(relative)))
    digest.update(relative)
    if kind == b"F":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
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
            raise SystemExit(f"bundle symlink changed during hashing: {os.fsdecode(relative)}")
        digest.update(struct.pack(">Q", len(target)))
        digest.update(target)
if digest.hexdigest() != values["bundle_content_sha256"]:
    raise SystemExit("sealed bundle content digest drifted")
PY
pass "current resolves to the exact fully sealed bundle $sha"

# Installed units and every allowed drop-in must be byte-for-byte members of
# the authenticated bundle. Extra drop-ins or alternate reboot links fail.
cmp -s "$MCP_UNIT" "$BUNDLE/src/ops/systemd/tradewave-mcpserver.service" \
  || die "installed MCP unit differs from sealed policy"
cmp -s "$MCP_FENCE" "$BUNDLE/src/ops/systemd/tradewave-mcpserver-release-fence.conf" \
  || die "installed MCP start fence differs from sealed policy"
cmp -s "$MCP_MARKER" "$BUNDLE/src/ops/systemd/tradewave-mcpserver-release.conf" \
  || die "installed MCP marker differs from sealed policy"
cmp -s "$API_UNIT" "$BUNDLE/src/ops/systemd/tradewave-apiserver-immutable.service" \
  || die "installed API unit differs from sealed policy"
cmp -s "$API_FENCE" "$BUNDLE/src/ops/systemd/tradewave-apiserver-release-fence.conf" \
  || die "installed API start fence differs from sealed policy"
for path in "$MCP_UNIT" "$MCP_FENCE" "$MCP_MARKER" "$API_UNIT" "$API_FENCE"; do
  require_file_metadata "$path" "root:root 644 1"
done
mapfile -t mcp_dropins < <(find "$(dirname "$MCP_FENCE")" -mindepth 1 -maxdepth 1 -type f -printf '%p\n' | sort)
[ "${mcp_dropins[*]}" = "$MCP_FENCE $MCP_MARKER" ] \
  || die "MCP has an unexpected or missing drop-in"
mapfile -t api_dropins < <(find "$(dirname "$API_FENCE")" -mindepth 1 -maxdepth 1 -type f -printf '%p\n' | sort)
[ "${#api_dropins[@]}" -eq 1 ] && [ "${api_dropins[0]}" = "$API_FENCE" ] \
  || die "API has an unexpected or missing drop-in"
[ -L /etc/systemd/system/multi-user.target.wants/tradewave-mcpserver.service ] \
  && [ "$(readlink /etc/systemd/system/multi-user.target.wants/tradewave-mcpserver.service)" = ../tradewave-mcpserver.service ] \
  || die "MCP reboot activation link is not exact"
[ -L /etc/systemd/system/multi-user.target.wants/tradewave-apiserver.service ] \
  && [ "$(readlink /etc/systemd/system/multi-user.target.wants/tradewave-apiserver.service)" = ../tradewave-apiserver.service ] \
  || die "API reboot activation link is not exact"
[ "$(systemctl is-enabled tradewave-mcpserver.service)" = enabled ] \
  && [ "$(systemctl is-enabled tradewave-apiserver.service)" = enabled ] \
  || die "paired services are not enabled"

expect_property tradewave-mcpserver.service FragmentPath "$MCP_UNIT"
expect_property tradewave-mcpserver.service User tradewave-mcp
expect_property tradewave-mcpserver.service Group tradewave-mcp
expect_property tradewave-mcpserver.service Type exec
expect_property tradewave-mcpserver.service WorkingDirectory /
expect_property tradewave-mcpserver.service ProtectSystem strict
expect_property tradewave-mcpserver.service NoNewPrivileges yes
expect_property tradewave-mcpserver.service InaccessiblePaths '-/etc/tradewave -/home/flask'
expect_property tradewave-mcpserver.service EnvironmentFiles '/etc/tradewave/mcpserver.env (ignore_errors=no)'
expect_property tradewave-apiserver.service FragmentPath "$API_UNIT"
expect_property tradewave-apiserver.service DropInPaths "$API_FENCE"
expect_property tradewave-apiserver.service User tradewave-api
expect_property tradewave-apiserver.service Group tradewave-api
expect_property tradewave-apiserver.service Type notify
expect_property tradewave-apiserver.service WorkingDirectory "$CURRENT/src"
expect_property tradewave-apiserver.service ProtectSystem strict
expect_property tradewave-apiserver.service NoNewPrivileges yes
expect_property tradewave-apiserver.service InaccessiblePaths '-/etc/tradewave /home/flask'
expect_property tradewave-apiserver.service EnvironmentFiles '/etc/tradewave/apiserver.env (ignore_errors=no)'
clean_python - "$(systemctl show tradewave-mcpserver.service --property=DropInPaths --value)" \
  "$MCP_FENCE" "$MCP_MARKER" <<'PY'
import shlex
import sys
actual = shlex.split(sys.argv[1])
expected = sys.argv[2:]
if len(actual) != 2 or set(actual) != set(expected):
    raise SystemExit("effective MCP drop-in set is not exact")
PY
exact_condition='ExecCondition=+/usr/bin/python3.13 -I -B -S /usr/local/libexec/tradewave-mcp-start-guard.py /var/lib/tradewave/mcp-release-transactions/active /run/lock/tradewave/mcp-release.lock'
for unit in tradewave-mcpserver.service tradewave-apiserver.service; do
  mapfile -t conditions < <(systemctl cat "$unit" --no-pager | sed -n -E 's/^[[:space:]]*(ExecCondition=.*)$/\1/p')
  [ "${#conditions[@]}" -eq 1 ] && [ "${conditions[0]}" = "$exact_condition" ] \
    || die "$unit does not have exactly one fixed journal start fence"
  mapfile -t privileged < <(systemctl cat "$unit" --no-pager | sed -n -E 's/^[[:space:]]*(Exec[A-Za-z]*=\+.*)$/\1/p')
  [ "${#privileged[@]}" -eq 1 ] && [ "${privileged[0]}" = "$exact_condition" ] \
    || die "$unit has an unexpected privileged command"
  for hook in ExecStartPre ExecStartPost ExecReload ExecStop ExecStopPost; do
    [ -z "$(systemctl show "$unit" --property="$hook" --value)" ] \
      || die "$unit has forbidden $hook"
  done
done
systemd-analyze verify tradewave-apiserver.service tradewave-mcpserver.service >/dev/null
systemctl is-active --quiet tradewave-apiserver.service \
  && systemctl is-active --quiet tradewave-mcpserver.service \
  || die "paired services are not active"
expect_property tradewave-apiserver.service ActiveState active
expect_property tradewave-apiserver.service SubState running
expect_property tradewave-mcpserver.service ActiveState active
expect_property tradewave-mcpserver.service SubState running
pass "installed and effective API/MCP systemd policies are exact"

# Prove the finalized dedicated K1 without invoking candidate code or making an
# authenticated request. The raw key is compared only through the platform's
# keyed HMAC and is never emitted.
clean_python - "$MCP_ENV" "$API_ENV" "$PLATFORM_ENV" "$ROTATION" "$mcp_host" <<'PY'
import hashlib
import hmac
import json
import os
import re
import shlex
import stat
import sys
from urllib.parse import urlsplit

runtime_path, api_runtime_path, platform_path, rotation_path, expected_host = sys.argv[1:]

def private_file(path: str, maximum: int, *, gid: int = 0, mode: int = 0o600) -> bytes:
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0 or metadata.st_gid != gid
        or stat.S_IMODE(metadata.st_mode) != mode or metadata.st_nlink != 1
        or metadata.st_size > maximum
    ):
        raise SystemExit(f"private release evidence metadata is unsafe: {path}")
    return open(path, "rb", buffering=0).read()

def environment(path: str, raw: bytes, selected=None) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise SystemExit(f"environment is not UTF-8: {path}") from exc
    values = {}
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)", line)
        if match is None:
            raise SystemExit(f"malformed environment assignment: {path}:{number}")
        name, encoded = match.groups()
        if selected is not None and name not in selected:
            continue
        lexer = shlex.shlex(encoded, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            decoded = list(lexer)
        except ValueError as exc:
            raise SystemExit(f"malformed environment value: {path}:{number}") from exc
        if len(decoded) != 1 or name in values or any(c in decoded[0] for c in "\0\r\n"):
            raise SystemExit(f"ambiguous environment assignment: {path}:{number}")
        values[name] = decoded[0]
    return values

runtime_raw = private_file(runtime_path, 64 * 1024)
runtime = environment(runtime_path, runtime_raw)
required_runtime = {
    "API_BASE_URL", "TW2_MCP_HOST", "TW2_MCP_PORT", "TW2_MCP_TRANSPORT",
    "WORKOS_AUTHKIT_DOMAIN", "TW2_MCP_PUBLIC_URL", "TW2_MCP_PUBLIC_HOST",
    "MCP_GATEWAY_KEY",
}
if set(runtime) != required_runtime:
    raise SystemExit("dedicated MCP environment schema is not exact")
expected_runtime = {
    "API_BASE_URL": "http://127.0.0.1:8088/v1",
    "TW2_MCP_HOST": "127.0.0.1",
    "TW2_MCP_PORT": "9090",
    "TW2_MCP_TRANSPORT": "streamable-http",
    "TW2_MCP_PUBLIC_URL": f"https://{expected_host}",
    "TW2_MCP_PUBLIC_HOST": expected_host,
}
for name, expected in expected_runtime.items():
    if runtime.get(name) != expected:
        raise SystemExit(f"dedicated MCP environment drifted: {name}")
if not re.fullmatch(r"tw_svc_[A-Za-z0-9_-]{43}", runtime["MCP_GATEWAY_KEY"]):
    raise SystemExit("dedicated MCP credential is not a service key")
issuer = urlsplit(runtime["WORKOS_AUTHKIT_DOMAIN"])
if (
    issuer.scheme != "https" or not issuer.hostname or issuer.port not in (None, 443)
    or issuer.username is not None or issuer.password is not None
    or issuer.path not in ("", "/") or issuer.query or issuer.fragment
):
    raise SystemExit("configured authorization server is not a canonical HTTPS origin")

api_runtime_raw = private_file(api_runtime_path, 64 * 1024)
api_runtime = environment(api_runtime_path, api_runtime_raw)
api_runtime_fields = {
    "POSTGRES_DSN", "API_KEY_HMAC_SECRET", "TW2_APPSERVER_URL", "SERVICE_API_KEY",
    "TW2_DEMO_API_KEY", "REDIS_HOST", "REDIS_PORT", "API_REDIS_DB",
    "TW2_PUBLIC_HOST", "TW2_ENV", "API_CORS_ORIGINS", "TW2_API_PRICING_LIVE",
}
if set(api_runtime) != api_runtime_fields or not api_runtime.get("API_KEY_HMAC_SECRET"):
    raise SystemExit("dedicated API environment schema/HMAC authority is not exact")

# The broad source has legacy root:flask 0640 metadata. It is read only to prove
# that K0 is absent; no active secret authority is derived from this mutable file.
import grp
platform_raw = private_file(
    platform_path, 2 * 1024 * 1024, gid=grp.getgrnam("flask").gr_gid, mode=0o640
)
platform_key = environment(platform_path, platform_raw, {"MCP_GATEWAY_KEY"})
if "MCP_GATEWAY_KEY" in platform_key:
    raise SystemExit("broad platform secrets still contain MCP_GATEWAY_KEY")
hmac_secret = api_runtime["API_KEY_HMAC_SECRET"]

rotation_raw = private_file(rotation_path, 8192)
try:
    rotation = json.loads(rotation_raw)
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("service-key rotation evidence is invalid JSON") from exc
fields = {
    "version", "status", "replacement_key_id", "replacement_key_hash",
    "superseded_key_id", "superseded_key_hash", "source_key_hash",
}
if set(rotation) != fields or type(rotation.get("version")) is not int or rotation.get("version") != 2:
    raise SystemExit("service-key rotation schema/version is not exact")
if rotation.get("status") != "active":
    raise SystemExit("service-key rotation is not active")
if rotation.get("superseded_key_id") is not None or rotation.get("superseded_key_hash") is not None:
    raise SystemExit("active service-key rotation retained superseded authority")
if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", str(rotation.get("replacement_key_id", ""))):
    raise SystemExit("replacement service-key identity is not a canonical UUIDv4")
for name in ("replacement_key_hash", "source_key_hash"):
    if not re.fullmatch(r"[0-9a-f]{64}", str(rotation.get(name, ""))):
        raise SystemExit(f"rotation evidence has invalid {name}")
canonical = (json.dumps(rotation, sort_keys=True, separators=(",", ":")) + "\n").encode()
if rotation_raw != canonical:
    raise SystemExit("service-key rotation evidence is not canonical JSON")
actual_hash = hmac.new(
    hmac_secret.encode("utf-8"), runtime["MCP_GATEWAY_KEY"].encode("utf-8"), hashlib.sha256
).hexdigest()
if not hmac.compare_digest(actual_hash, rotation["replacement_key_hash"]):
    raise SystemExit("dedicated K1 does not match active keyed rotation evidence")
PY
pass "dedicated K1 matches active rotation evidence; broad K0 is absent"

# Sacrificial verifier state may leave its empty, root-private roots behind, but
# no reusable credential, state record, materialized credential, or unit may remain.
[ ! -e /etc/tradewave/mcp-verifier.env ] \
  || die "legacy permanent verifier environment still exists"
require_empty_private_root /var/lib/tradewave/mcp-verifier-probes
require_empty_private_root /run/tradewave-mcp-verifier
if [ -d /run/credentials ]; then
  [ -z "$(find /run/credentials -mindepth 1 -maxdepth 2 -name 'tradewave-mcp-verify-*' -print -quit)" ] \
    || die "a materialized verifier credential directory remains"
fi
if [ -d /run/systemd/transient ]; then
  [ -z "$(find /run/systemd/transient -mindepth 1 -maxdepth 1 -name 'tradewave-mcp-verify-*.service' -print -quit)" ] \
    || die "a transient release-verifier unit file remains"
fi
if systemctl list-units --all --plain --no-legend | awk '$1 ~ /^tradewave-mcp-verify-/ {found=1} END {exit found ? 0 : 1}'; then
  die "a transient release-verifier unit remains"
fi
if systemctl list-unit-files --no-legend | awk '$1 ~ /^tradewave-mcp-verify-/ {found=1} END {exit found ? 0 : 1}'; then
  die "a release-verifier unit file remains"
fi
pass "sacrificial verifier credentials, state, and transient units are absent"

require_file_metadata "$MCP_RUNTIME_LOCK" "root:tradewave-mcp 640 1"
require_file_metadata "$API_RUNTIME_LOCK" "root:tradewave-api 640 1"
[ "$(stat -c '%s' "$MCP_RUNTIME_LOCK")" = 0 ] \
  && [ "$(stat -c '%s' "$API_RUNTIME_LOCK")" = 0 ] \
  || die "a runtime lock file contains unexpected data"
mcp_pid=$(systemctl show tradewave-mcpserver.service --property=MainPID --value)
api_pid=$(systemctl show tradewave-apiserver.service --property=MainPID --value)
[[ "$mcp_pid" =~ ^[1-9][0-9]*$ ]] && [ "$mcp_pid" -ge 2 ] || die "MCP MainPID is invalid"
[[ "$api_pid" =~ ^[1-9][0-9]*$ ]] && [ "$api_pid" -ge 2 ] || die "API MainPID is invalid"
mcp_cgroup=$(systemctl show tradewave-mcpserver.service --property=ControlGroup --value)
api_cgroup=$(systemctl show tradewave-apiserver.service --property=ControlGroup --value)
[[ "$mcp_cgroup" = /* ]] && [ -r "/sys/fs/cgroup$mcp_cgroup/cgroup.procs" ] \
  || die "MCP cgroup process ledger is unavailable"
[[ "$api_cgroup" = /* ]] && [ -r "/sys/fs/cgroup$api_cgroup/cgroup.procs" ] \
  || die "API cgroup process ledger is unavailable"
mcp_pids=$(sort -n -u "/sys/fs/cgroup$mcp_cgroup/cgroup.procs" | paste -sd, -)
api_pids=$(sort -n -u "/sys/fs/cgroup$api_cgroup/cgroup.procs" | paste -sd, -)

clean_python - "$BUNDLE" "$CURRENT" "$MCP_ENV" "$API_ENV" "$mcp_pid" "$mcp_pids" \
  "$api_pid" "$api_pids" "$MCP_RUNTIME_LOCK" "$API_RUNTIME_LOCK" <<'PY'
import os
import pathlib
import pwd
import grp
import socket
import stat
import sys

bundle, current, runtime_env, api_runtime_env, mcp_main, raw_mcp, api_main, raw_api, mcp_lock, api_lock = sys.argv[1:]
mcp_main = int(mcp_main)
api_main = int(api_main)
mcp_pids = {int(value) for value in raw_mcp.split(",") if value}
api_pids = {int(value) for value in raw_api.split(",") if value}
if mcp_pids != {mcp_main}:
    raise SystemExit(f"MCP cgroup is not exactly its MainPID: {sorted(mcp_pids)}")
if len(api_pids) != 5 or api_main not in api_pids:
    raise SystemExit(f"API cgroup is not one Gunicorn master plus four workers: {sorted(api_pids)}")

def identity(account: str, group: str, pid: int) -> None:
    uid = pwd.getpwnam(account).pw_uid
    gid = grp.getgrnam(group).gr_gid
    lines = pathlib.Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines()
    uids = next(line for line in lines if line.startswith("Uid:")).split()[1:]
    gids = next(line for line in lines if line.startswith("Gid:")).split()[1:]
    groups = next(line for line in lines if line.startswith("Groups:")).split()[1:]
    if uids != [str(uid)] * 4 or gids != [str(gid)] * 4 or groups != [str(gid)]:
        raise SystemExit(f"PID {pid} identity/group set drifted")

def argv(pid: int) -> list[str]:
    return [value.decode("utf-8") for value in pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if value]

def environ(pid: int) -> dict[str, list[str]]:
    result = {}
    for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if not item:
            continue
        if b"=" not in item:
            raise SystemExit(f"PID {pid} has a malformed environment entry")
        try:
            name, value = item.split(b"=", 1)
            decoded_name, decoded_value = name.decode("ascii"), value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"PID {pid} has a non-text environment entry") from exc
        result.setdefault(decoded_name, []).append(decoded_value)
    return result

def exact_environment(
    label: str,
    pid: int,
    actual: dict[str, list[str]],
    expected: dict[str, str],
    bookkeeping: set[str],
) -> None:
    for name, value in expected.items():
        if actual.get(name) != [value]:
            raise SystemExit(f"{label} PID {pid} environment drifted: {name}")
    duplicates = sorted(name for name, values in actual.items() if len(values) != 1)
    if duplicates:
        raise SystemExit(f"{label} PID {pid} has duplicate environment names: {duplicates}")
    unexpected = sorted(set(actual) - set(expected) - bookkeeping)
    if unexpected:
        raise SystemExit(
            f"{label} PID {pid} inherited non-allowlisted environment names: {unexpected}"
        )

import shlex
def environment(path: str) -> dict[str, str]:
    values = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, encoded = line.split("=", 1)
        lexer = shlex.shlex(encoded, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        decoded = list(lexer)
        if len(decoded) != 1 or name in values:
            raise SystemExit(f"ambiguous dedicated environment: {path}")
        values[name] = decoded[0]
    return values

runtime_values = environment(runtime_env)
api_runtime_values = environment(api_runtime_env)
mcp_bookkeeping = {
    "HOME", "INVOCATION_ID", "JOURNAL_STREAM", "LANG", "LOGNAME",
    "MEMORY_PRESSURE_WATCH", "MEMORY_PRESSURE_WRITE", "NOTIFY_SOCKET", "PATH",
    "SHELL", "SYSTEMD_EXEC_PID", "USER",
}
api_bookkeeping = {
    "HOME", "INVOCATION_ID", "JOURNAL_STREAM", "LANG", "LC_ALL", "LOGNAME",
    "MEMORY_PRESSURE_WATCH", "MEMORY_PRESSURE_WRITE", "NOTIFY_SOCKET", "PATH",
    "PYTHONDONTWRITEBYTECODE", "SHELL", "SYSTEMD_EXEC_PID", "USER",
}
mcp_expected = [
    f"{current}/venv/bin/python", "-I", "-B", "-u",
    f"{current}/src/mcpserver/server.py", "--transport", "streamable-http",
    "--host", "127.0.0.1", "--port", "9090",
]
api_expected = [
    f"{current}/gateway-venv/bin/python", "-I", "-B", "-m", "gunicorn",
    "--chdir", f"{current}/src", "--workers", "4", "--worker-class", "gthread",
    "--threads", "12", "--timeout", "120", "--keep-alive", "75",
    "--bind", "127.0.0.1:8088", "--access-logfile", "-", "--error-logfile", "-",
    "--capture-output", "apiserver.app:app",
]
for pid in mcp_pids:
    identity("tradewave-mcp", "tradewave-mcp", pid)
    if argv(pid) != mcp_expected or os.path.realpath(f"/proc/{pid}/cwd") != "/":
        raise SystemExit(f"MCP PID {pid} command/cwd is not exact")
    if os.path.realpath(f"/proc/{pid}/exe") != "/usr/bin/python3.13":
        raise SystemExit(f"MCP PID {pid} executable escaped the fixed interpreter")
    process_env = environ(pid)
    exact_environment("MCP", pid, process_env, runtime_values, mcp_bookkeeping)
for pid in api_pids:
    identity("tradewave-api", "tradewave-api", pid)
    if argv(pid) != api_expected or os.path.realpath(f"/proc/{pid}/cwd") != f"{bundle}/src":
        raise SystemExit(f"API PID {pid} command/cwd is not exact")
    if os.path.realpath(f"/proc/{pid}/exe") != "/usr/bin/python3.13":
        raise SystemExit(f"API PID {pid} executable escaped the fixed interpreter")
    process_env = environ(pid)
    api_expected_environment = dict(api_runtime_values)
    api_expected_environment["TW2_FEATURED_HISTORY_FILE"] = "/run/tradewave-gateway/featured_history.json"
    exact_environment("API", pid, process_env, api_expected_environment, api_bookkeeping)

def exact_uid_processes(account: str, expected: set[int]) -> None:
    uid = pwd.getpwnam(account).pw_uid
    actual = set()
    for process in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            lines = (process / "status").read_text(encoding="ascii").splitlines()
            uids = {int(value) for value in next(line for line in lines if line.startswith("Uid:")).split()[1:]}
        except (FileNotFoundError, ProcessLookupError, StopIteration):
            continue
        if uid in uids:
            actual.add(int(process.name))
    if actual != expected:
        raise SystemExit(f"{account} has processes outside its service cgroup: {sorted(actual - expected)}")

exact_uid_processes("tradewave-mcp", mcp_pids)
exact_uid_processes("tradewave-api", api_pids)
exact_uid_processes("tradewave-mcp-verify", set())

def shared_lock(pid: int, path: str, label: str) -> None:
    target = os.stat(path)
    descriptors = []
    for entry in pathlib.Path(f"/proc/{pid}/fd").iterdir():
        try:
            metadata = os.stat(entry)
        except FileNotFoundError:
            continue
        if (metadata.st_dev, metadata.st_ino) == (target.st_dev, target.st_ino):
            descriptors.append(entry)
    if not descriptors:
        raise SystemExit(f"{label} MainPID did not inherit its runtime-lock descriptor")
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
        raise SystemExit(f"{label} MainPID does not hold its exact lifetime shared lock")

shared_lock(mcp_main, mcp_lock, "MCP")
shared_lock(api_main, api_lock, "API")

def listener(port: int, expected_pids: set[int], label: str) -> None:
    encoded = f"{port:04X}"
    listeners = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in pathlib.Path(table).read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 10 and fields[1].rsplit(":", 1)[-1] == encoded and fields[3] == "0A":
                listeners.append((table, fields[1], fields[9]))
    expected_address = f"0100007F:{encoded}"
    if len(listeners) != 1 or listeners[0][:2] != ("/proc/net/tcp", expected_address):
        raise SystemExit(f"{label} listener is not exactly IPv4 loopback-only: {listeners!r}")
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
    if not owners or not owners.issubset(expected_pids):
        raise SystemExit(f"{label} listener ownership escaped its cgroup: {sorted(owners)}")

listener(8088, api_pids, "API")
listener(9090, mcp_pids, "MCP")
PY

nsenter --mount="/proc/$mcp_pid/ns/mnt" -- \
  setpriv --reuid="$(id -u tradewave-mcp)" --regid="$(id -g tradewave-mcp)" --clear-groups -- \
  /bin/sh -c '! test -r /etc/tradewave/secrets.env && ! test -x /etc/tradewave && ! test -r /home/flask && ! test -x /home/flask' \
  || die "MCP process namespace can browse platform secrets or mutable source"
nsenter --mount="/proc/$api_pid/ns/mnt" -- \
  setpriv --reuid="$(id -u tradewave-api)" --regid="$(id -g tradewave-api)" --clear-groups -- \
  /bin/sh -c 'test -s /run/tradewave-gateway/featured_history.json && test -r /run/tradewave-gateway/featured_history.json && ! test -w /run/tradewave-gateway/featured_history.json && ! test -r /etc/tradewave/secrets.env && ! test -x /etc/tradewave && ! test -r /home/flask && ! test -x /home/flask' \
  || die "API process namespace isolation or read-only featured ledger failed"
pass "exact API/MCP processes, loopback listeners, namespaces, and lifetime locks are live"

# Public post-commit checks are deliberately unauthenticated. Validate the
# configured identity, protected-resource and authorization-server metadata,
# API health, and a real initialize request that must return exactly 401.
clean_python - "$MCP_ENV" "https://$api_host" "https://$mcp_host" <<'PY'
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

runtime_path, api_origin, mcp_origin = sys.argv[1:]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    NoRedirect(),
)

def request(url, *, method="GET", headers=None, payload=None):
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request_headers = {
        "Accept-Encoding": "identity",
        "User-Agent": "TradeWave-Postdeploy-No-Bearer/1.0",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with opener.open(req, timeout=8) as response:
            content = response.read(4 * 1024 * 1024 + 1)
            if len(content) > 4 * 1024 * 1024:
                raise SystemExit(f"public response exceeded safety bound: {url}")
            if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise SystemExit(f"public response ignored identity encoding: {url}")
            return response.status, response.headers, content
    except urllib.error.HTTPError as exc:
        content = exc.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise SystemExit(f"public error response exceeded safety bound: {url}")
        if exc.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise SystemExit(f"public error response ignored identity encoding: {url}")
        return exc.code, exc.headers, content

def canonical_origin(value: str, label: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SystemExit(f"{label} is invalid") from exc
    if (
        parsed.scheme != "https" or not parsed.hostname or port not in (None, 443)
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
    ):
        raise SystemExit(f"{label} is not a canonical HTTPS origin")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    return f"https://{host}"

runtime = {}
for line in open(runtime_path, "r", encoding="utf-8"):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    name, separator, value = stripped.partition("=")
    if not separator or name in runtime:
        raise SystemExit("runtime identity environment is ambiguous")
    runtime[name] = value
expected_mcp = canonical_origin(mcp_origin, "expected MCP identity")
expected_api = canonical_origin(api_origin, "expected API identity")
if canonical_origin(runtime.get("TW2_MCP_PUBLIC_URL", ""), "runtime MCP identity") != expected_mcp:
    raise SystemExit("runtime and requested MCP public identities disagree")
expected_issuer = canonical_origin(runtime.get("WORKOS_AUTHKIT_DOMAIN", ""), "configured issuer")

for health_url, label in (
    ("http://127.0.0.1:8088/healthz", "local API"),
    (expected_api + "/healthz", "public API"),
):
    status, _, body = request(health_url)
    if status != 200:
        raise SystemExit(f"{label} health returned {status}")
    try:
        health = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} health is not JSON") from exc
    if health != {"ok": True, "service": "tradewave-apiserver"}:
        raise SystemExit(f"{label} health identity drifted")

discovery_url = expected_mcp + "/.well-known/oauth-protected-resource"
status, _, body = request(discovery_url, headers={"Accept": "application/json"})
if status != 200:
    raise SystemExit(f"protected-resource discovery returned {status}")
try:
    discovery = json.loads(body)
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("protected-resource discovery is not JSON") from exc
if not isinstance(discovery, dict) or set(discovery) != {
    "resource", "authorization_servers", "bearer_methods_supported"
}:
    raise SystemExit("protected-resource discovery schema is not exact")
if canonical_origin(discovery.get("resource", ""), "discovery resource") != expected_mcp:
    raise SystemExit("protected-resource discovery advertises the wrong resource")
if discovery.get("bearer_methods_supported") != ["header"]:
    raise SystemExit("protected-resource discovery bearer method is not header-only")
servers = discovery.get("authorization_servers")
if not isinstance(servers, list) or len(servers) != 1:
    raise SystemExit("protected-resource discovery must advertise exactly one issuer")
issuer = canonical_origin(servers[0], "discovery issuer")
if issuer != expected_issuer:
    raise SystemExit("protected-resource discovery issuer disagrees with runtime policy")

status, _, metadata_body = request(issuer + "/.well-known/oauth-authorization-server")
if status != 200:
    raise SystemExit(f"authorization-server metadata returned {status}")
try:
    metadata = json.loads(metadata_body)
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("authorization-server metadata is not JSON") from exc
if not isinstance(metadata, dict) or canonical_origin(metadata.get("issuer", ""), "metadata issuer") != issuer:
    raise SystemExit("authorization-server metadata issuer drifted")
for field, suffix in {
    "authorization_endpoint": "/oauth2/authorize",
    "token_endpoint": "/oauth2/token",
}.items():
    if metadata.get(field) != issuer + suffix:
        raise SystemExit(f"authorization-server metadata {field} drifted")
registration = metadata.get("registration_endpoint")
if registration is not None:
    if registration != issuer + "/oauth2/register":
        raise SystemExit("authorization-server registration endpoint drifted")
elif metadata.get("client_id_metadata_document_supported") is not True:
    raise SystemExit("authorization server supports neither DCR nor CIMD")
required = {
    "scopes_supported": {"offline_access"},
    "grant_types_supported": {"authorization_code", "refresh_token"},
    "response_types_supported": {"code"},
    "code_challenge_methods_supported": {"S256"},
    "token_endpoint_auth_methods_supported": {"none"},
}
for field, wanted in required.items():
    actual = metadata.get(field)
    if not isinstance(actual, list) or any(not isinstance(item, str) for item in actual) or not wanted.issubset(actual):
        raise SystemExit(f"authorization-server metadata {field} is incomplete")

initialize = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "tradewave-postdeploy-no-bearer", "version": "1"},
    },
}
status, headers, _ = request(
    expected_mcp + "/",
    method="POST",
    headers={
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
        "User-Agent": "TradeWave-Postdeploy-No-Bearer/1.0",
    },
    payload=initialize,
)
if status != 401:
    raise SystemExit(f"unauthenticated initialize returned {status}, want exactly 401")
challenge = headers.get("WWW-Authenticate", "")
if not re.match(r"^Bearer(?:\s|$)", challenge, flags=re.IGNORECASE):
    raise SystemExit("401 lacks a Bearer WWW-Authenticate challenge")
error_match = re.search(
    r"(?:^|,)\s*error\s*=\s*(?:\"([^\"]+)\"|([^,\s]+))",
    challenge[len("Bearer"):],
    flags=re.IGNORECASE,
)
challenge_error = (error_match.group(1) or error_match.group(2)) if error_match else ""
if challenge_error != "invalid_token":
    raise SystemExit("401 Bearer challenge is not exact invalid_token")
match = re.search(
    r"resource_metadata\s*=\s*(?:\"([^\"]+)\"|([^,\s]+))",
    challenge,
    flags=re.IGNORECASE,
)
resource_metadata = (match.group(1) or match.group(2)) if match else ""
if resource_metadata != discovery_url:
    raise SystemExit("401 challenge does not name the canonical resource metadata URL")
PY
pass "public API health, OAuth discovery/issuer metadata, and exact unauthenticated 401 passed"

echo "RESULT: exact paired release $sha is post-commit clean"
