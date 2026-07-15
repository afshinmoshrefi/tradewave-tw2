"""Static release invariants for the MCP edge/deploy layer."""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_nginx_budget_supports_twenty_parallel_chatgpt_conversations():
    config = _read("ops/nginx/tradewave-developer-portal.conf")
    rate = int(re.search(r"zone=tw2_mcp_per_ip:10m rate=(\d+)r/s", config).group(1))
    burst = int(re.search(r"tw2_mcp_per_ip burst=(\d+)", config).group(1))
    connections = int(re.search(r"tw2_mcp_conn_per_ip (\d+)", config).group(1))

    # Release gate: initialize + initialized + tools/list + first call + DELETE.
    # OpenAI egress can share an IP; keep headroom for the strict probe before it.
    assert rate >= 10
    assert burst >= (20 * 5) + 20
    assert connections >= 20 * 2


def test_mcp_proxy_preserves_public_https_and_real_client_ip():
    config = _read("ops/nginx/tradewave-developer-portal.conf")
    mcp_block = config.split("# 2) MCP server", 1)[1].split(
        "# 3) Developer portal", 1
    )[0]
    assert "proxy_set_header X-Forwarded-Proto https;" in mcp_block
    assert "proxy_set_header X-Forwarded-Proto $scheme;" not in mcp_block
    assert "real_ip_header CF-Connecting-IP;" in mcp_block
    assert "set_real_ip_from 127.0.0.1;" in mcp_block
    assert "listen 127.0.0.1:80;" in mcp_block
    assert "listen [::1]:80;" in mcp_block
    assert "listen 80;" not in mcp_block
    assert "listen [::]:80;" not in mcp_block


def test_mcp_runtime_versions_are_release_pinned():
    requirements = _read("requirements-api.txt")
    assert re.search(r"(?m)^mcp==1\.28\.1$", requirements)
    assert re.search(r"(?m)^httpx==0\.28\.1$", requirements)
    assert re.search(r"(?m)^PyJWT\[crypto\]==2\.13\.0$", requirements)

    lock = _read("requirements-mcp.lock")
    entries = []
    pending = ""
    for raw in lock.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        entries.append(shlex.split(pending))
        pending = ""
    assert not pending
    assert entries
    assert all(tokens[0].count("==") == 1 for tokens in entries)
    assert all(
        len(tokens) >= 2
        and all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", item) for item in tokens[1:])
        for tokens in entries
    )
    versions = {
        requirement.split("[", 1)[0]: version
        for requirement, version in (tokens[0].split("==", 1) for tokens in entries)
    }
    names = {name.lower() for name in versions}
    assert {"mcp", "httpx", "pyjwt", "cryptography", "starlette", "uvicorn"} <= names
    assert not {"flask", "gunicorn", "redis", "requests", "psycopg2-binary"} & names
    assert versions["cryptography"] == "48.0.1"
    assert versions["pydantic-settings"] == "2.14.2"
    assert versions["python-multipart"] == "0.0.31"
    assert versions["starlette"] == "1.3.1"


def test_immutable_release_is_outside_dirty_source_checkout():
    deploy = _read("ops/deploy_mcp_release.sh")
    unit = _read("ops/systemd/tradewave-mcpserver.service")
    drop_in = _read("ops/systemd/tradewave-mcpserver-release.conf")
    assert "/home/tradewave-mcp" in deploy
    assert "/home/flask/releases" not in deploy
    assert "/home/flask/mcp-current" not in deploy
    assert "WorkingDirectory=/" in unit
    assert (
        "ExecStart=/usr/bin/flock --shared --nonblock --no-fork "
        "/var/lib/tradewave-mcp-runtime-lock/runtime.lock "
        "/home/tradewave-mcp/current/venv/bin/python -I -B -u "
        "/home/tradewave-mcp/current/src/mcpserver/server.py"
    ) in unit
    assert "ExecStart=" not in drop_in
    assert "WorkingDirectory=" not in drop_in
    assert "/home/flask/venv-api/bin/pip" not in deploy
    assert "sudo -u flask" not in deploy
    assert "Environment=PYTHONPATH=" not in unit
    assert "--setenv=PYTHONPATH=" not in deploy
    assert "SOURCE_ORIGIN=https://github.com/afshinmoshrefi/tradewave-tw2.git" in deploy
    assert "NGINX_ENABLED=/etc/nginx/sites-enabled/tradewave-developer-portal\n" in deploy
    assert "runtime_manifest_sha256=" in deploy
    assert "runtime_wheel_manifest_sha256=" in deploy
    assert "artifacts/runtime.lock" in deploy
    assert "verify_bundle_tree_metadata" in deploy
    assert deploy.count("--require-hashes") >= 4
    assert deploy.count("--no-index --no-deps --no-compile") == 4


def test_candidate_dependency_builds_are_python_313_and_wheel_only():
    deploy = _read("ops/deploy_mcp_release.sh")

    assert "REQUIRED_PYTHON_SERIES=3.13" in deploy
    assert "require_release_python()" in deploy
    assert 'BASE_PYTHON=/usr/bin/python3.13' in deploy
    assert 'sys.executable != "/usr/bin/python3.13"' in deploy
    assert 'sys.version_info[:2] != (3, 13)' in deploy
    assert 'platform.machine() != "x86_64"' in deploy
    assert 'platform.libc_ver() != ("glibc", "2.42")' in deploy
    assert "not sys.flags.isolated" in deploy
    assert "not sys.flags.no_site" in deploy
    assert deploy.index("recover_unfinished_transaction\nrequire_release_python") \
        > deploy.index("recover_unfinished_transaction()")

    assert deploy.count("/usr/bin/python3.13 -I -B -m pip install --no-index") == 4
    assert deploy.count("--require-hashes --only-binary=:all: --target") == 4
    assert deploy.count("PIP_CONFIG_FILE=/dev/null") >= 4
    assert deploy.count("--wheelhouse") >= 5
    venv_start = deploy.index("create_minimal_venv()")
    venv_helper = deploy[venv_start:deploy.index("\n}\n", venv_start)]
    for invariant in (
        "os.umask(0)",
        "os.mkdir(target, 0o555)",
        'os.mkdir(os.path.join(target, "lib"), 0o555)',
        "os.chmod(site, 0o700)",
        "os.fchmod(fd, 0o444)",
    ):
        assert invariant in venv_helper


def test_candidate_python_series_gate_fails_closed():
    deploy = _read("ops/deploy_mcp_release.sh")
    start = deploy.index("require_release_python()")
    end = deploy.index("\n}\n", start) + len("\n}\n")
    gate = deploy[start:end]
    for invariant in (
        'platform.python_implementation() != "CPython"',
        "sys.version_info[:2] != (3, 13)",
        'platform.machine() != "x86_64"',
        'platform.libc_ver() != ("glibc", "2.42")',
        'sys.executable != "/usr/bin/python3.13"',
        'os.path.realpath(sys.executable) != "/usr/bin/python3.13"',
        "not sys.flags.isolated",
        "not sys.flags.dont_write_bytecode",
        "not sys.flags.no_site",
        "not sys.flags.ignore_environment",
        'intersection(sys.modules)',
    ):
        assert invariant in gate
    assert 'fail "system Python trust boundary failed"' in gate


@pytest.mark.skipif(shutil.which("bash") is None or os.name != "posix",
                    reason="requires bash on a POSIX host")
def test_syncfs_failure_aborts_before_journal_publication(tmp_path):
    deploy = _read("ops/deploy_mcp_release.sh")
    start = deploy.index("flush_paths_durably()")
    end = deploy.index("\n}\n\nflush_candidate_bundle()", start) + len("\n}\n")
    function = deploy[start:end]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_sync = fake_bin / "sync"
    fake_sync.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    fake_sync.chmod(0o755)
    target = tmp_path / "candidate"
    target.write_text("candidate", encoding="utf-8")
    shell = "\n".join((
        "set -euo pipefail",
        'fail() { echo "FAIL: $*" >&2; exit 1; }',
        "SYNCFS_COUNT=0",
        'BASE_PYTHON="$(command -v python3)"',
        function,
        'flush_paths_durably "$1"',
    ))
    result = subprocess.run(
        ["bash", "-c", shell, "syncfs-test", str(target)],
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "sync -f failed" in result.stderr


def test_release_seal_binds_source_wheels_and_installed_bytes():
    deploy = _read("ops/deploy_mcp_release.sh")
    seal_check = deploy.split("verify_sealed_bundle()", 1)[1].split(
        "BUILD_WORKSPACES=", 1
    )[0]
    for field in (
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
    ):
        assert field in deploy
    assert 'verify_bundle_tree_metadata "$bundle"' in seal_check
    assert seal_check.count('"$TRUSTED_WHEEL_HELPER" verify-install') == 3
    assert '--wheelhouse "$bundle/wheelhouse/runtime"' in seal_check
    assert '--wheelhouse "$bundle/wheelhouse/provision"' in seal_check
    assert '--wheelhouse "$bundle/wheelhouse/gateway"' in seal_check
    assert "runtime installed inventory drift" in seal_check
    assert "provision installed inventory drift" in seal_check
    assert "gateway installed inventory drift" in seal_check


def test_production_port_canaries_are_mechanically_equivalent_to_stable_pair():
    deploy = _read("ops/deploy_mcp_release.sh")
    equivalence = deploy.split("verify_canary_policy_equivalence()", 1)[1].split(
        "start_api_candidate_canary()", 1
    )[0]
    for property_name in (
        "Type", "WorkingDirectory", "EnvironmentFiles", "Environment",
        "UnsetEnvironment", "StandardInput", "StandardOutput", "StandardError",
        "KillMode", "RestartUSec", "TimeoutStopUSec",
    ):
        assert property_name in equivalence
    assert 'stable[:len(wrapper)] != wrapper' in equivalence
    assert 'if candidate != stable:' in equivalence
    assert 'property=Restart --value)" = no' in equivalence
    assert 'property=Restart --value)" = on-failure' in equivalence
    assert '--property="WorkingDirectory=$CURRENT_LINK/src"' in deploy
    assert '--property="EnvironmentFile=$MCP_ENV"' in deploy
    assert '"$CURRENT_LINK/gateway-venv/bin/python" -I -B -m gunicorn' in deploy
    assert '"$CURRENT_LINK/venv/bin/python" -I -B -u "$CURRENT_LINK/src/mcpserver/server.py"' in deploy


def test_candidate_test_lock_carries_the_pinned_auditor_and_hashes():
    lock = _read("requirements-mcp-test.lock")
    assert re.search(r"(?m)^pip-audit==2\.10\.1 \\\s*$", lock)
    requirement_lines = [
        line for line in lock.splitlines()
        if line and not line[0].isspace() and not line.startswith("#")
    ]
    assert requirement_lines
    assert all(line.endswith("\\") for line in requirement_lines)


def test_release_verifier_never_places_bearer_tokens_in_process_arguments():
    deploy = _read("ops/deploy_mcp_release.sh")
    verifier_block = deploy.split("run_verifier()", 1)[1].split(
        "public_contract_check()", 1
    )[0]

    assert 'env "${verifier_env[@]}"' not in verifier_block
    assert 'token=$(' not in verifier_block
    assert 'TW_MCP_VERIFY_TOKEN=' not in verifier_block
    assert "LoadCredential=verify-env:$VERIFIER_CREDENTIAL" in verifier_block
    assert "verification-token" not in deploy
    assert '--setenv="TW_MCP_EXPECT_AUTHORIZATION_SERVER=$issuer"' in verifier_block
    assert "runtime_python=$BASE_PYTHON" in verifier_block
    assert '"$runtime_python" -I -B -S -u "$script" --url "$url" "$@"' in verifier_block
    assert '"$runtime_bundle/venv/bin/python"' not in verifier_block
    assert "-/home/tradewave-mcp" in verifier_block
    assert 'contract) script=$TRUSTED_CONTRACT_VERIFIER' in verifier_block
    assert 'load) script=$TRUSTED_LOAD_VERIFIER' in verifier_block


def test_release_verifiers_ignore_inherited_proxy_and_custom_ca_environment():
    helper = _read("ops/mcp_service_env.py")
    contract = _read("ops/verify_mcp_contract.py")
    load = _read("ops/verify_mcp_load.py")
    exec_block = helper.split("def exec_with_verifier", 1)[1].split(
        "def source_value", 1
    )[0]
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    ):
        assert name not in exec_block
    assert "ProxyHandler({})" in helper
    assert "ProxyHandler({})" in contract
    assert "urllib.request.ProxyHandler({})" in load
    assert "import httpx" not in load
    assert "ThreadPoolExecutor(" in load
    assert "max_workers=clients" in load


def test_public_release_gates_have_no_bypass_and_provision_inside_transaction():
    deploy = _read("ops/deploy_mcp_release.sh")
    assert "skip-public-verify" not in deploy
    assert "SKIP_PUBLIC_VERIFY" not in deploy
    main = deploy.split("TX_ARMED=1", 1)[1]
    assert main.index("trap on_exit EXIT") < main.index("provision_release_credentials")
    assert deploy.index("journal_action prepare") < deploy.rindex("provision_release_credentials")
    assert "--mint-verifier-probe" in deploy
    assert "--revoke-verifier-probe" in deploy
    assert "--purge-stale-verifier-probes" in deploy
    assert "provision-mcp-key.py" in deploy
    assert '"$bundle/artifacts/provision-mcp-key.py"' in deploy
    assert '"$bundle/artifacts/mcp-provision-bootstrap.py"' in deploy
    assert '"$CANDIDATE_SRC/apiserver/provision_mcp_key.py"' not in deploy
    assert 'abort_mcp_key_rotation "$candidate_bundle"' in deploy


def test_release_lock_and_xtrace_are_hardened():
    deploy = _read("ops/deploy_mcp_release.sh")
    assert deploy.index("set +x") < deploy.index("SECRETS=")
    assert "LOCK_DIR=/run/lock/tradewave" in deploy
    assert 'mkdir -m 0700 "$LOCK_DIR"' in deploy
    assert '[ ! -L "$LOCK_DIR" ]' in deploy
    assert 'root:root 700' in deploy
    assert '[ ! -L "$LOCK_FILE" ]' in deploy
    assert 'root:root 600' in deploy
    assert 'exec 9<>"$LOCK_FILE"' in deploy
    assert "TW_MCP_RELEASE_LOCK_FD=9" in deploy
    assert ">/run/lock/tradewave-mcp-release.lock" not in deploy


def test_persistent_runtime_lock_fences_every_live_mutation():
    deploy = _read("ops/deploy_mcp_release.sh")
    unit = _read("ops/systemd/tradewave-mcpserver.service")
    main = deploy.split("TX_ARMED=1", 1)[1]
    assert (
        "/usr/bin/flock --shared --nonblock --no-fork "
        "/var/lib/tradewave-mcp-runtime-lock/runtime.lock"
    ) in unit
    assert main.index("systemctl stop tradewave-mcpserver") < main.index(
        "acquire_runtime_lock_exclusive"
    )
    assert main.index("acquire_runtime_lock_exclusive") < main.index(
        "provision_release_credentials"
    )
    finalization = main.rindex('finalize_mcp_key_rotation "$CANARY_PID"')
    unlock = main.rindex("release_runtime_lock")
    persistent_start = main.rindex("systemctl start tradewave-mcpserver")
    assert finalization < unlock < persistent_start
    assert "verify_runtime_shared_lock" in deploy
    assert 'fields[1:4] != ["FLOCK", "ADVISORY", "READ"]' in deploy


@pytest.mark.skipif(
    shutil.which("flock") is None or os.name != "posix",
    reason="requires util-linux flock on a POSIX host",
)
def test_runtime_lock_race_and_crash_release_are_fail_closed(tmp_path):
    lock = tmp_path / "runtime.lock"
    lock.touch(mode=0o640)
    sleeper = [
        shutil.which("python3") or "python3",
        "-c",
        "import time; print('ready', flush=True); time.sleep(30)",
    ]

    shared = subprocess.Popen(
        ["flock", "--shared", "--no-fork", str(lock), *sleeper],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert shared.stdout is not None and shared.stdout.readline().strip() == "ready"
        assert subprocess.run(
            ["flock", "--exclusive", "--nonblock", str(lock), "true"],
            check=False,
        ).returncode != 0
    finally:
        shared.terminate()
        shared.wait(timeout=5)

    exclusive = subprocess.Popen(
        ["flock", "--exclusive", "--no-fork", str(lock), *sleeper],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert exclusive.stdout is not None and exclusive.stdout.readline().strip() == "ready"
    assert subprocess.run(
        ["flock", "--shared", "--nonblock", str(lock), "true"],
        check=False,
    ).returncode != 0
    exclusive.kill()
    exclusive.wait(timeout=5)
    assert subprocess.run(
        ["flock", "--shared", "--nonblock", str(lock), "true"],
        check=False,
    ).returncode == 0


def test_mcp_service_logs_only_to_journald_without_root_opening_mutable_paths():
    unit = _read("ops/systemd/tradewave-mcpserver.service")
    assert "StandardOutput=journal" in unit
    assert "StandardError=journal" in unit
    assert "append:" not in unit
    assert "/var/log/tradewave" not in unit


def test_target_side_postdeploy_retains_no_verifier_or_authenticated_probe():
    verifier = _read("ops/verify_deploy.sh") + _read("ops/verify_paired_release.sh")
    assert "--check-verifier" not in verifier
    assert "exec-with-verifier" not in verifier
    assert "verify_mcp_contract.py" not in verifier
    assert "verify_mcp_load.py" not in verifier
    assert "TW_MCP_VERIFY_TOKEN=" not in verifier
    assert "Authorization" not in verifier
    assert "tools/list" not in verifier
    assert "whoami" not in verifier
    assert "--clients" not in verifier
    assert "[ ! -e /etc/tradewave/mcp-verifier.env ]" in verifier
    assert "tradewave-mcp-verify-*.service" in verifier
    assert 'if status != 401:' in verifier
    assert 'challenge_error != "invalid_token"' in verifier


@pytest.mark.skipif(shutil.which("bash") is None or getattr(os, "geteuid", lambda: 1)() != 0,
                    reason="requires root on a POSIX host")
def test_exec_with_verifier_does_not_leak_under_bash_x(tmp_path):
    sentinel = "tw_live_" + "d" * 32
    verifier_env = tmp_path / "mcp-verifier.env"
    verifier_env.write_text(f"TW_MCP_VERIFY_TOKEN={sentinel}\n", encoding="utf-8")
    verifier_env.chmod(0o600)
    child = tmp_path / "child.py"
    child.write_text(
        "import os\nassert os.environ['TW_MCP_VERIFY_TOKEN'].startswith('tw_live_')\n",
        encoding="utf-8",
    )
    helper = ROOT / "ops" / "mcp_service_env.py"
    command = (
        'set +x; "$PYTHON" "$HELPER" exec-with-verifier --source "$VERIFIER" -- '
        '"$PYTHON" "$CHILD"'
    )
    result = subprocess.run(
        ["bash", "-x", "-c", command],
        env={
            **os.environ,
            "HELPER": str(helper),
            "VERIFIER": str(verifier_env),
            "CHILD": str(child),
            "PYTHON": shutil.which("python3") or "",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert sentinel not in result.stdout + result.stderr


def test_seal_treats_symlinks_safely_and_rejects_untrusted_targets():
    deploy = _read("ops/deploy_mcp_release.sh")
    tree_policy = deploy.split("bundle_tree_policy()", 1)[1].split(
        "verify_minimal_venv()", 1
    )[0]
    assert 'os.path.join(root, "venv", "bin", "python")' in tree_policy
    assert 'os.path.join(root, "provision-venv", "bin", "python")' in tree_policy
    assert 'os.readlink(path) != "/usr/bin/python3.13"' in tree_policy
    assert "bundle has an unexpected symlink" in tree_policy
    assert "bundle has a hard-linked file" in tree_policy
    assert "bundle has a special file" in tree_policy
    assert "bundle contains forbidden Git metadata" in tree_policy
    assert "bundle does not contain the three exact interpreter links" in tree_policy


def test_rollback_uses_fixed_config_and_legacy_smoke_is_explicit():
    deploy = _read("ops/deploy_mcp_release.sh")
    assert '"$TRUSTED_UNIT_TEMPLATE" "$UNIT"' in deploy
    assert '"$TRUSTED_DROPIN_TEMPLATE" "$DROPIN"' in deploy
    assert '"$TRUSTED_NGINX_TEMPLATE" > "$EDGE_TMP"' in deploy
    assert '"$CANDIDATE_BUNDLE/artifacts/mcpserver.service"' not in deploy
    assert '"$url" --legacy-smoke' in deploy
    assert "rollback_contract_check" in deploy
    assert "recover_unfinished_transaction" in deploy
    assert 'finalizer_src="$VALIDATOR_BUNDLE/src"' not in deploy
    assert "old unsafe provisioner" not in deploy
    assert "PAIRED RECOVERY FAILED after deploy exit" in deploy
    assert "RECOVERY PASS: pre-intent API gateway + MCP entry pair restored" in deploy
    assert 'journal_action restore' in deploy
    assert 'journal_action mark-recovered' in deploy
    assert 'journal_action cleanup-recovered' in deploy
    assert "verify_restored" in deploy
    assert "TX_ARMED=1" in deploy


def test_existing_current_is_trusted_only_after_entry_seal_and_process_preflight():
    deploy = _read("ops/deploy_mcp_release.sh")
    normal_path = deploy.split('if [ "${1:-}" = --rollback ]; then', 1)[1]
    normal_path = normal_path.split('echo "==> snapshot live unit', 1)[0]

    assert 'resolved=$(readlink -f -- "$CURRENT_LINK")' in deploy
    assert "current release resolves outside $RELEASE_ROOT" in deploy
    assert 'expected=$(bundle_for_sha "$sha")' in deploy
    assert 'verify_sealed_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"' in deploy
    assert 'verify_running_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"' in deploy
    assert normal_path.count("preflight_entry_bundle") >= 2
    assert normal_path.index("preflight_entry_bundle") < normal_path.index(
        'echo "==> prepare immutable MCP candidate'
    )
    assert deploy.count('verify_sealed_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"') >= 1
    assert deploy.count('verify_running_bundle "$ENTRY_BUNDLE" "$ENTRY_BUNDLE_SHA"') >= 1
    assert 'sha=$(bundle_sha "$linked"' not in deploy
    assert '"$CANDIDATE_BUNDLE" = "$(bundle_for_sha "$RELEASE_SHA")"' in deploy


def test_release_entrypoints_accept_only_exact_lowercase_commit_sha():
    deploy = _read("ops/deploy_mcp_release.sh")
    launcher = _read("ops/launch_mcp_release.sh")
    orchestrator = _read("ops/deploy.sh")
    assert '[[ "$requested" =~ ^[0-9a-f]{40}$ ]]' in deploy
    assert '[[ ! "$1" =~ ^[0-9a-f]{40}$ ]]' in launcher
    assert '[[ "$MCP_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]' in orchestrator
    assert "TW_MCP_RELEASE_SHA" in orchestrator
    assert "TW_MCP_RELEASE_REF" not in orchestrator
    assert "launcher=/usr/local/sbin/tradewave-mcp-release" in orchestrator
    assert '"$launcher" "$sha"' in orchestrator
    assert "/home/flask/ops/deploy_mcp_release.sh" not in orchestrator
    assert "check-ref-format" not in deploy
    assert "ls-remote" not in deploy
    assert "git-branch" not in launcher
    assert '--depth=1 --no-tags "$SOURCE_ORIGIN" "$sha"' in deploy


def test_public_host_and_twenty_session_gate_are_release_blocking():
    deploy = _read("ops/deploy_mcp_release.sh")
    load_gate = _read("ops/verify_mcp_load.py")
    assert "public_url_host" in deploy
    assert "resolved_portal_hosts" in deploy
    assert 'trusted_python "$TRUSTED_ENV_HELPER" resolve-portal-hosts' in deploy
    assert "disagrees with TW2_MCP_PUBLIC_URL" in deploy
    assert "public_load_check" in deploy
    assert "--clients 20 --timeout 20" in deploy
    assert "--phase-max-seconds 5" in deploy
    assert "--whoami-p95-max-seconds 2 --whoami-max-seconds 3" in deploy
    assert "--session-p95-max-seconds 12 --session-max-seconds 15" in deploy
    assert "latency SLO failed" in load_gate
    assert "concurrent sessions may be serializing" in load_gate
    assert '"tools/list"' in load_gate
    assert 'phases["whoami"] = await _phase(' in load_gate
    assert 'phases["delete"] = await _phase(' in load_gate


def test_first_dev_install_resolves_missing_per_service_hosts(monkeypatch):
    for name in (
        "TW2_API_PUBLIC_HOST",
        "TW2_MCP_PUBLIC_HOST",
        "TW2_DEVELOPERS_PUBLIC_HOST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")
    original_exists = os.path.exists
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda path: False
        if path == "/etc/tradewave/secrets.env"
        else original_exists(path),
    )
    path = ROOT / "site/lib/portal_urls.py"
    spec = importlib.util.spec_from_file_location("portal_urls_dev_first_install", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.API_HOST == "api-dev.trxstat.com"
    assert module.MCP_HOST == "mcp-dev.trxstat.com"
    assert module.DEV_HOST == "developers-dev.trxstat.com"


def test_systemd_baseline_is_explicit():
    unit = _read("ops/systemd/tradewave-mcpserver.service")
    release = _read("ops/systemd/tradewave-mcpserver-release.conf")
    fence = _read("ops/systemd/tradewave-mcpserver-release-fence.conf")
    bootstrap = _read("ops/bootstrap_api_services.sh")
    for directive in (
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectHome=read-only",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "UMask=0077",
        "MemoryHigh=768M",
        "MemoryMax=1G",
        "ProtectProc=invisible",
        "ProcSubset=pid",
        "User=tradewave-mcp",
        "Group=tradewave-mcp",
        "InaccessiblePaths=-/etc/tradewave",
        "WorkingDirectory=/",
        "LimitCORE=0",
        "KillMode=control-group",
    ):
        assert directive in unit
    assert (
        "ExecCondition=+/usr/bin/python3.13 -I -B -S "
        "/usr/local/libexec/tradewave-mcp-start-guard.py"
    ) in fence
    assert "EnvironmentFile=/etc/tradewave/mcpserver.env" in unit
    assert "EnvironmentFile=/etc/tradewave/secrets.env" not in unit
    assert "PYTHONDONTWRITEBYTECODE" in unit.split("UnsetEnvironment=", 1)[1]
    assert "ExecStart=" not in release
    assert "systemctl enable --now tradewave-mcpserver" not in bootstrap
    assert "/usr/local/sbin/tradewave-mcp-release <lowercase-40-char-sha>" in bootstrap


def test_durable_journal_has_crash_recovery_and_reboot_start_guards():
    deploy = _read("ops/deploy_mcp_release.sh")
    unit = _read("ops/systemd/tradewave-mcpserver.service")
    fence = _read("ops/systemd/tradewave-mcpserver-release-fence.conf")
    guard = _read("ops/mcp_start_guard.py")

    for point in (
        "after_journal_publish",
        "after_previous_pointer",
        "after_current_pointer",
        "after_unit_file",
        "after_dropin_file",
        "after_mcp_environment",
        "after_nginx_file",
        "after_nginx_pointer",
        "after_service_restart",
        "after_public_gates",
        "after_key_finalize",
        "before_commit_intent",
        "after_journal_commit",
        "after_journal_cleanup",
    ):
        assert f"crash_point {point}" in deploy
    assert 'journal_action reconcile' in deploy
    assert 'journal_action verify-committed-live "$state_path"' in deploy
    assert "TW_MCP_TEST_FAIL_JOURNAL_FSYNC_AT" in deploy
    assert "TW_MCP_TEST_FAIL_JOURNAL_WRITE_AT" in deploy
    assert "TW_MCP_TEST_FAIL_SYNCFS_AT" in deploy
    assert "commit-intent.json" in deploy
    assert "finalized.json" in deploy
    assert 'state_re = re.compile(r"(?:\\.new|committed|recovered|gc)-' in deploy
    assert "mcp-start-guard.py" in fence
    assert "active release transaction blocks persistent MCP start" in guard
    assert "BindsTo=$DEPLOY_UNIT" in deploy
    assert "PartOf=$DEPLOY_UNIT" in deploy


def test_mcp_opportunity_response_budget_is_frozen_at_one_hundred():
    server = _read("mcpserver/server.py")
    verifier = _read("ops/verify_mcp_contract.py")
    tests = _read("tests/test_mcpserver.py")

    assert "_MCP_COMPACT_RESULT_MAX = 100" in server
    assert "_MCP_FULL_RESULT_MAX = 25" in server
    assert "_MCP_SCAN_DEFAULT_LIMIT = 10" in server
    assert "_MCP_OPPORTUNITIES_DEFAULT_LIMIT = 25" in server
    assert 'maximum = 1000 if name == "list_symbols" else 100' in verifier
    assert "limit=100, view=\"table\"" in tests
    assert "limit=25, view=\"full\"" in tests
    assert "limit=101" in tests


def test_deploy_transactions_and_verifies_the_mcp_only_environment():
    deploy = _read("ops/deploy_mcp_release.sh")
    assert "MCP_ENV=/etc/tradewave/mcpserver.env" in deploy
    assert "SECRETS=/etc/tradewave/secrets.env" in deploy
    assert '"mcp_env": os.path.abspath(sys.argv[12])' in deploy
    assert '"api_env": os.path.abspath(sys.argv[13])' in deploy
    assert '"secrets": os.path.abspath(sys.argv[14])' in deploy
    assert 'files = {label: snapshot_file(path, txdir, label)' in deploy
    assert 'restore_file(record, active_path, manifest["txid"])' in deploy
    assert "install_mcp_runtime_env" in deploy
    assert 'want root:root 600' in deploy
    assert "check_mcp_gateway_key" in deploy
    assert "check-process-env" in deploy
    assert "broad or verifier secrets file" in deploy
    assert "MCP_KEY_STATE=/var/lib/tradewave/mcp-key-rotation.json" in deploy
    assert "TW_MCP_KEY_PENDING_STATE" not in deploy


def test_root_launcher_and_controller_transient_are_fail_closed():
    launcher = _read("ops/launch_mcp_release.sh")
    deploy = _read("ops/deploy_mcp_release.sh")
    installer = _read("ops/install_mcp_release_controller.sh")

    identity_start = deploy.index("ensure_mcp_service_identities()")
    identity_end = deploy.index("ensure_one_runtime_lock_file()", identity_start)
    identity_helper = deploy[identity_start:identity_end]
    for guard in (
        "expected_primary_ids = {",
        "account.pw_gid in gids",
        "(account.pw_uid, account.pw_gid) not in expected_primary_ids",
        "reserved MCP primary gid",
    ):
        assert guard in identity_helper

    assert '[[ ! "$1" =~ ^[0-9a-f]{40}$ ]]' in launcher
    assert "ProtectSystem=strict" in launcher
    import hashlib

    assert hashlib.sha256(
        (ROOT / "ops/launch_mcp_release.sh").read_bytes()
    ).hexdigest() == "54749d8ba854345abe96a6797fff50e7f9ee1fdc98d92a55cec2e852f06f3efc"
    assert "controller bootstrap mount target" not in launcher

    identity_bootstrap_start = installer.index(
        "# Account-database mutation cannot run inside the immutable launcher's"
    )
    identity_bootstrap = installer[
        identity_bootstrap_start:installer.index(
            "# The stable launcher is deliberately immutable once CURRENT exists",
            identity_bootstrap_start,
        )
    ]
    for invocation in (
        "ensure_exact_release_identity tradewave-mcp tradewave-mcp",
        "ensure_exact_release_identity tradewave-mcp-verify tradewave-mcp-verify",
        "ensure_exact_release_identity tradewave-mcp-build tradewave-mcp-build",
        "ensure_exact_release_identity tradewave-mcp-deps tradewave-mcp-deps",
        "ensure_exact_release_identity tradewave-mcp-test tradewave-mcp-test",
        "ensure_exact_release_identity tradewave-api tradewave-api",
    ):
        assert invocation in identity_bootstrap
    for guard in (
        '/usr/sbin/groupadd --system "$group_name"',
        '/usr/sbin/useradd --system --gid "$group_name" --no-user-group',
        'account.pw_dir != "/nonexistent"',
        'account.pw_shell != "/usr/sbin/nologin"',
        "reserved MCP identities must have pairwise-distinct UIDs and GIDs",
        "reserved MCP primary gid",
        'if [ -z "$PREFIX" ]; then\n  ensure_release_identities\nfi',
        "crash_point after_service_identity_bootstrap",
    ):
        assert guard in identity_bootstrap

    bootstrap_start = installer.index(
        "# The stable launcher is deliberately immutable once CURRENT exists"
    )
    bootstrap = installer[
        bootstrap_start:installer.index(
            '/usr/bin/install -d -o root -g root -m 0755 \\\n', bootstrap_start
        )
    ]
    for record in (
        '("/home/tradewave-mcp", 0o755, None)',
        '("/var/lib/tradewave", 0o755, None)',
        '("/var/lib/tradewave-mcp-runtime-lock", 0o750, "tradewave-mcp")',
        '("/var/lib/tradewave-api-runtime-lock", 0o750, "tradewave-api")',
        '("/run/tradewave-mcp-deploy", 0o755, None)',
        '("/run/tradewave-mcp-verifier", 0o700, None)',
    ):
        assert record in bootstrap
    for guard in (
        "os.umask(0)",
        "unsafe runtime-mount bootstrap ancestor",
        "unsafe runtime-mount bootstrap target",
        "os.path.lexists(current)",
        "os.lstat(current)",
        "group_name is not None",
        "create_gid = 0",
        "metadata.st_gid == 0",
        "not os.listdir(current)",
        "not settled_gid and not transitional_empty",
        'b"d /run/lock/tradewave 0700 root root -\\n"',
        'b"d /run/tradewave-mcp-deploy 0755 root root -\\n"',
        'b"d /run/tradewave-mcp-verifier 0700 root root -\\n"',
        "/usr/bin/systemd-tmpfiles --create",
    ):
        assert guard in bootstrap
    assert (
        bootstrap.index('if [ -z "$PREFIX" ]; then')
        < bootstrap.index("/usr/bin/systemd-tmpfiles --create")
        < bootstrap.index("crash_point after_runtime_mount_bootstrap")
    )
    assert installer.index("crash_point after_runtime_mount_bootstrap") < installer.index(
        "FETCH_UUID="
    )
    assert installer.index(
        "refusing control-plane upgrade while any durable transaction exists"
    ) < identity_bootstrap_start < bootstrap_start < installer.index(
        'install_bootstrap "$SEALED_SET/release-launcher-bootstrap.sh"'
    )
    assert installer.count("/usr/bin/systemd-tmpfiles --create") == 1

    helper_start = deploy.index("ensure_one_runtime_lock_file()")
    runtime_helper = deploy[
        helper_start:deploy.index("\nensure_runtime_lock_file()", helper_start)
    ]
    for guard in (
        "metadata.st_uid == 0",
        "metadata.st_gid == 0",
        "stat.S_IMODE(metadata.st_mode) == 0o750",
        "not os.listdir(directory)",
        "os.chown(directory, 0, gid)",
    ):
        assert guard in runtime_helper
    assert runtime_helper.count("metadata = os.lstat(directory)") >= 2
    stateful = deploy[deploy.index("# This is intentionally the first stateful action"):]
    assert (
        stateful.index("ensure_mcp_service_identities")
        < stateful.index("ensure_runtime_lock_file")
        < stateful.index("ensure_api_runtime_lock_file")
    )
    assert 'InaccessiblePaths=-/root -/home/flask' in launcher
    assert "--setenv=HOME=/nonexistent" in launcher
    assert "--property=LimitCORE=0" in launcher
    assert "ProtectSystem=full" not in launcher
    assert 'protect_system=$(systemctl show "$DEPLOY_UNIT" --property=ProtectSystem --value)' in deploy
    assert '"/root", "/home/flask"' in deploy
    assert '"HOME=/nonexistent"' in deploy
    assert 'limit_core=$(systemctl show "$DEPLOY_UNIT" --property=LimitCORE --value)' in deploy
    assert "refusing control-plane upgrade while any durable transaction exists" in installer
    assert "/usr/bin/python3.13 -I -B -S" in installer
    # systemctl's ExecCondition record contains the interpreter once in `path=`
    # and again in `argv[]=`. Count the path field, not the raw substring.
    assert installer.count("grep -o 'path=/usr/bin/python3.13'") == 2
    assert "grep -o '/usr/bin/python3.13'" not in installer
    assert "O_NOFOLLOW" in installer


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 1)() != 0,
    reason="requires root on a POSIX host",
)
def test_installer_mount_bootstrap_is_crash_retry_safe_and_fail_closed():
    import grp
    import signal
    import stat
    import uuid

    prefix = Path("/tmp") / f"tradewave-mcp-install-test-{uuid.uuid4()}"
    prefix.mkdir(mode=0o700)
    os.chown(prefix, 0, 0)
    os.chmod(prefix, 0o700)
    installer = ROOT / "ops/install_mcp_release_controller.sh"
    environment = {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TW_MCP_INSTALL_TEST_ROOT": str(prefix),
        "TW_MCP_INSTALL_TEST_CRASH_AT": "after_runtime_mount_bootstrap",
    }

    def run_installer():
        return subprocess.run(
            [
                "/usr/bin/bash",
                "--noprofile",
                "--norc",
                "-p",
                str(installer),
                "0" * 40,
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    expected_directories = {
        "home/tradewave-mcp": 0o755,
        "var/lib/tradewave": 0o755,
        "var/lib/tradewave-mcp-runtime-lock": 0o750,
        "var/lib/tradewave-api-runtime-lock": 0o750,
        "run/lock/tradewave": 0o700,
        "run/tradewave-mcp-deploy": 0o755,
        "run/tradewave-mcp-verifier": 0o700,
    }
    expected_tmpfiles = (
        b"d /run/lock/tradewave 0700 root root -\n"
        b"d /run/tradewave-mcp-deploy 0755 root root -\n"
        b"d /run/tradewave-mcp-verifier 0700 root root -\n"
    )

    def assert_killed_at_bootstrap(result):
        assert result.returncode in {-signal.SIGKILL, 128 + signal.SIGKILL}
        assert "TEST CRASH POINT: after_runtime_mount_bootstrap" in result.stderr

    def snapshot():
        values = {}
        for relative, mode in expected_directories.items():
            path = prefix / relative
            metadata = os.lstat(path)
            assert stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)
            assert (metadata.st_uid, metadata.st_gid) == (0, 0)
            assert stat.S_IMODE(metadata.st_mode) == mode
            values[relative] = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
            )
        for relative in (
            "var/lib/tradewave-mcp-runtime-lock",
            "var/lib/tradewave-api-runtime-lock",
        ):
            assert not any((prefix / relative).iterdir())
        lock = os.lstat(prefix / "run/lock/tradewave/mcp-release.lock")
        assert stat.S_ISREG(lock.st_mode) and not stat.S_ISLNK(lock.st_mode)
        assert (lock.st_uid, lock.st_gid, stat.S_IMODE(lock.st_mode), lock.st_nlink) == (
            0,
            0,
            0o600,
            1,
        )
        config = prefix / "etc/tmpfiles.d/tradewave-mcp-release.conf"
        config_metadata = os.lstat(config)
        assert stat.S_ISREG(config_metadata.st_mode)
        assert not stat.S_ISLNK(config_metadata.st_mode)
        assert (
            config_metadata.st_uid,
            config_metadata.st_gid,
            stat.S_IMODE(config_metadata.st_mode),
            config_metadata.st_nlink,
        ) == (0, 0, 0o644, 1)
        assert config.read_bytes() == expected_tmpfiles
        return values, (config_metadata.st_dev, config_metadata.st_ino, config.read_bytes())

    try:
        first = run_installer()
        assert_killed_at_bootstrap(first)
        before = snapshot()
        second = run_installer()
        assert_killed_at_bootstrap(second)
        assert snapshot() == before

        group_paths = (
            ("tradewave-mcp", prefix / "var/lib/tradewave-mcp-runtime-lock"),
            ("tradewave-api", prefix / "var/lib/tradewave-api-runtime-lock"),
        )
        try:
            settled_groups = [(grp.getgrnam(name), path) for name, path in group_paths]
        except KeyError:
            settled_groups = []
        if settled_groups:
            for group, directory in settled_groups:
                os.chown(directory, 0, group.gr_gid)
                lock_path = directory / "runtime.lock"
                descriptor = os.open(
                    lock_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o640,
                )
                try:
                    os.fchown(descriptor, 0, group.gr_gid)
                    os.fchmod(descriptor, 0o640)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            settled = run_installer()
            assert_killed_at_bootstrap(settled)
            evidence_path = settled_groups[0][1] / "runtime.lock"
            os.chown(settled_groups[0][1], 0, 0)
        else:
            evidence_path = prefix / "var/lib/tradewave-mcp-runtime-lock/unexpected"
            evidence_path.write_text("occupied", encoding="utf-8")
        rejected = run_installer()
        assert rejected.returncode not in {-signal.SIGKILL, 128 + signal.SIGKILL, 0}
        assert "unsafe runtime-mount bootstrap target" in rejected.stderr
        assert evidence_path.exists()
    finally:
        shutil.rmtree(prefix)


def test_release_verifier_freezes_seventeen_tools_and_rejects_ghost():
    verifier_path = ROOT / "ops/verify_mcp_contract.py"
    spec = importlib.util.spec_from_file_location("verify_mcp_contract", verifier_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert len(module.EXPECTED_SCHEMAS) == 17
    assert "get_opportunity_for_symbol" not in module.EXPECTED_SCHEMAS
    assert module.GHOST_TOOLS == {"get_opportunity_for_symbol"}
