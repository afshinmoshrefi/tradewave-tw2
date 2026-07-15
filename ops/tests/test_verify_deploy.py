"""Static trust-boundary tests for whole-site and paired post-deploy gates."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
WRAPPER = (ROOT / "ops" / "verify_deploy.sh").read_text(encoding="utf-8")
PAIRED = (ROOT / "ops" / "verify_paired_release.sh").read_text(encoding="utf-8")
ALL = WRAPPER + "\n" + PAIRED


def test_app_tier_has_one_exact_sha_transaction_and_no_manual_edge_restart():
    assert '[[ "$MCP_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]' in DEPLOY
    assert 'bash -s -- "$MCP_RELEASE_SHA"' in DEPLOY
    assert 'fetch --no-tags origin main' in DEPLOY
    assert 'merge-base --is-ancestor "$sha" origin/main' in DEPLOY
    assert 'merge-base --is-ancestor "$head" "$sha"' in DEPLOY
    assert 'merge --ff-only "$sha"' in DEPLOY
    assert '[ "$(sudo -u flask git -C "$checkout" rev-parse HEAD)" = "$sha" ]' in DEPLOY
    assert DEPLOY.count('"$launcher" "$sha"') == 2
    assert DEPLOY.count("systemctl restart tradewave-appserver.service") == 1
    for forbidden in (
        "systemctl restart tradewave-apiserver",
        "systemctl start tradewave-apiserver",
        "systemctl stop tradewave-apiserver",
        "systemctl restart tradewave-mcpserver",
        "systemctl start tradewave-mcpserver",
        "systemctl stop tradewave-mcpserver",
        "/home/flask/venv-api/bin/pip",
    ):
        assert forbidden not in DEPLOY


def test_first_migration_runs_launcher_before_checkout_moves_and_later_release_after_appserver():
    remote = DEPLOY.split("<<'REMOTE_APP_TIER'", 1)[1].split("REMOTE_APP_TIER", 1)[0]
    first_launcher = remote.index('if [ "$first" = 1 ]; then')
    merge = remote.index('merge --ff-only "$sha"')
    app_restart = remote.index("systemctl restart tradewave-appserver.service")
    later_launcher = remote.index('if [ "$first" = 0 ]; then')
    assert first_launcher < merge < app_restart < later_launcher
    assert 'if [ ! -e "$current" ] && [ ! -L "$current" ]; then' in remote


def test_cli_requires_exact_environment_sha_and_paired_helper():
    assert '[ "$#" -eq 2 ] || usage' in WRAPPER
    assert '[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || usage' in WRAPPER
    assert "staging)" in WRAPPER
    assert "prod)" in WRAPPER
    assert "*) usage ;;" in WRAPPER
    assert "PAIRED_VERIFIER=$SCRIPT_DIR/verify_paired_release.sh" in WRAPPER
    assert '[ -f "$PAIRED_VERIFIER" ] && [ ! -L "$PAIRED_VERIFIER" ]' in WRAPPER
    assert 'bash -s -- "$RELEASE_SHA" "$APIHOST" "$MCPHOST"' in WRAPPER
    assert '< "$PAIRED_VERIFIER"' in WRAPPER
    assert "TW_MCP_EXPECT_SHA" not in ALL


def test_original_whole_site_release_gates_are_retained():
    required = (
        "systemctl is-active nginx tradewave-web",
        "tradewave-appserver tradewave-apiserver tradewave-mcpserver nginx",
        "/home.html /scorecard.html /research.html /about.html",
        "/insights/ /learn/ /markets/sp500.html /affiliate.html",
        "wc_web /markets/",
        "wc_web /join/TESTCODE",
        'wc_app /healthz "$APIHOST"',
        'wc_app / "$DEVHOST"',
        'wc_app /docs/ "$DEVHOST"',
        "/var/www/tradewave/",
        "/var/www/developers/",
        "Public forward track record",
        'class="ledger-row ledger-grid"',
        "Open the Full Public Track Record",
        "Seasonal projection based on your chosen time frame",
        "Seasonal projection based on all available data",
        "Target Hit means the predicted return was reached",
        "Different Desks. One Standard of Proof.",
        "fund running thousands of backtests",
        "Trade<b>Wave</b>",
        "googletagmanager",
        "held.to.close|reached.target",
    )
    for marker in required:
        assert marker in WRAPPER


def test_current_and_seal_are_bound_to_the_requested_release():
    assert "BUNDLE=$RELEASE_ROOT/mcp-$sha" in PAIRED
    assert '[ "$(readlink "$CURRENT")" = "releases/mcp-$sha" ]' in PAIRED
    assert '[ "$(readlink -f "$CURRENT")" = "$BUNDLE" ]' in PAIRED
    assert 'values.get("release_sha") != expected_sha' in PAIRED
    assert 'TW_MCP_BUNDLE_CONTENT_V1\\0' in PAIRED
    assert 'values["bundle_content_sha256"]' in PAIRED
    assert '"venv", "gateway-venv", "provision-venv"' in PAIRED
    assert '"src/mcpserver/server.py"' in PAIRED
    assert '"src/apiserver/app.py"' in PAIRED


def test_interpreter_symlinks_use_target_and_owner_not_permission_bits():
    assert "if path not in expected_links" in PAIRED
    assert 'os.readlink(path) != "/usr/bin/python3.13"' in PAIRED
    assert 'os.path.realpath(path) != "/usr/bin/python3.13"' in PAIRED
    assert "metadata.st_uid != 0 or metadata.st_gid != 0" in PAIRED
    assert 'if kind != b"L":' in PAIRED
    mode_block = PAIRED.split('if kind != b"L":', 1)[1].split("entries.append", 1)[0]
    assert "stat.S_IMODE(metadata.st_mode)" in mode_block


def test_postcommit_has_no_reusable_bearer_or_authenticated_load_path():
    forbidden = (
        "--check-verifier",
        "exec-with-verifier",
        "verify_mcp_contract.py",
        "verify_mcp_load.py",
        "TW_MCP_VERIFY_TOKEN=",
        "Authorization",
        "tools/list",
        "tools/call",
        "whoami",
        "--clients",
        "source-value verification-token",
    )
    for token in forbidden:
        assert token not in ALL
    assert '[ ! -e /etc/tradewave/mcp-verifier.env ]' in PAIRED
    assert "require_empty_private_root /var/lib/tradewave/mcp-verifier-probes" in PAIRED
    assert "require_empty_private_root /run/tradewave-mcp-verifier" in PAIRED


def test_verifier_residue_checks_use_actual_unit_prefix_and_empty_uid():
    assert "tradewave-mcp-verify-*.service" in PAIRED
    assert "tradewave-mcp-release-verify-" not in PAIRED
    assert 'exact_uid_processes("tradewave-mcp-verify", set())' in PAIRED
    assert "/run/credentials" in PAIRED
    assert "/run/systemd/transient" in PAIRED


def test_postcommit_does_not_execute_mutable_checkout_or_candidate_helpers():
    for token in (
        "/home/flask/venv",
        "git -C",
        "sudo -u flask",
        "provision-mcp-key.py",
        "mcp-provision-bootstrap.py",
        "--check-service",
    ):
        assert token not in PAIRED
    assert "/usr/bin/python3.13 -I -B -S" in PAIRED


def test_rotation_uses_dedicated_api_hmac_and_broad_file_only_for_k0_absence():
    assert "API_ENV=/etc/tradewave/apiserver.env" in PAIRED
    assert "PLATFORM_ENV=/etc/tradewave/secrets.env" in PAIRED
    assert 'EnvironmentFiles \'/etc/tradewave/apiserver.env (ignore_errors=no)\'' in PAIRED
    assert 'gid=grp.getgrnam("flask").gr_gid, mode=0o640' in PAIRED
    assert 'platform_key = environment(platform_path, platform_raw, {"MCP_GATEWAY_KEY"})' in PAIRED
    assert 'hmac_secret = api_runtime["API_KEY_HMAC_SECRET"]' in PAIRED
    assert 'hmac.compare_digest(actual_hash, rotation["replacement_key_hash"])' in PAIRED


def test_journal_and_runtime_lock_evidence_are_release_blocking():
    assert 'flock --exclusive --nonblock 9' in PAIRED
    assert 'stat -c \'%s\' "$RELEASE_LOCK"' in PAIRED
    assert 'find "$TX_ROOT" -mindepth 1 -maxdepth 1 -print -quit' in PAIRED
    assert 'rotation.get("status") != "active"' in PAIRED
    assert "shared_lock(mcp_main, mcp_lock, \"MCP\")" in PAIRED
    assert "shared_lock(api_main, api_lock, \"API\")" in PAIRED
    assert 'fields[1:4] != ["FLOCK", "ADVISORY", "READ"]' in PAIRED


def test_exact_paired_systemd_process_and_listener_identity_is_checked():
    assert "tradewave-apiserver-immutable.service" in PAIRED
    assert "tradewave-mcpserver.service" in PAIRED
    assert "systemd-analyze verify tradewave-apiserver.service tradewave-mcpserver.service" in PAIRED
    assert 'if mcp_pids != {mcp_main}:' in PAIRED
    assert "if len(api_pids) != 5" in PAIRED
    assert 'f"{current}/venv/bin/python"' in PAIRED
    assert 'f"{current}/gateway-venv/bin/python"' in PAIRED
    assert '"--bind", "127.0.0.1:8088"' in PAIRED
    assert 'listener(8088, api_pids, "API")' in PAIRED
    assert 'listener(9090, mcp_pids, "MCP")' in PAIRED
    assert "nsenter --mount=\"/proc/$mcp_pid/ns/mnt\"" in PAIRED
    assert "nsenter --mount=\"/proc/$api_pid/ns/mnt\"" in PAIRED


def test_public_surface_is_unauthenticated_and_canonically_structured():
    assert 'expected_api + "/healthz"' in PAIRED
    assert '"http://127.0.0.1:8088/healthz"' in PAIRED
    assert 'discovery_url = expected_mcp + "/.well-known/oauth-protected-resource"' in PAIRED
    assert 'issuer + "/.well-known/oauth-authorization-server"' in PAIRED
    assert '"protocolVersion": "2025-11-25"' in PAIRED
    assert 'if status != 401:' in PAIRED
    assert 'r"^Bearer(?:\\s|$)"' in PAIRED
    assert '"Accept-Encoding": "identity"' in PAIRED
    assert 'discovery.get("bearer_methods_supported") != ["header"]' in PAIRED
    assert 'challenge_error != "invalid_token"' in PAIRED
    assert "if resource_metadata != discovery_url:" in PAIRED


def test_all_embedded_python_blocks_compile_on_windows():
    blocks = re.findall(r"<<'PY'\n(.*?)\nPY", PAIRED, flags=re.DOTALL)
    assert len(blocks) == 5
    for number, block in enumerate(blocks, 1):
        compile(block, f"verify_paired_release.sh::<python-{number}>", "exec")


def test_postdeploy_environment_allowlist_rejects_arbitrary_secret_names():
    checker = None
    for block in re.findall(r"<<'PY'\n(.*?)\nPY", PAIRED, flags=re.DOTALL):
        tree = ast.parse(block)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "exact_environment":
                namespace = {}
                isolated = ast.Module(body=[node], type_ignores=[])
                exec(compile(ast.fix_missing_locations(isolated), "<exact-environment>", "exec"), namespace)
                checker = namespace["exact_environment"]
                break
    assert checker is not None
    expected = {"API_BASE_URL": "http://127.0.0.1:8088/v1"}
    bookkeeping = {"HOME"}
    for injected in ("ANTHROPIC_API_KEY", "ARBITRARY_INJECTED_NAME"):
        actual = {
            "API_BASE_URL": [expected["API_BASE_URL"]],
            "HOME": ["/nonexistent"],
            injected: ["must-not-survive"],
        }
        with pytest.raises(SystemExit, match="non-allowlisted environment names"):
            checker("MCP", 123, actual, expected, bookkeeping)
