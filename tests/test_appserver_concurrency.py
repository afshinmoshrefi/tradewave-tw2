"""Release contracts for bounded appserver concurrency and credential-safe logs."""

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "ops" / "systemd" / "tradewave-appserver.service"
API_UNIT = ROOT / "ops" / "systemd" / "tradewave-apiserver.service"


def test_pooled_http_preserves_requests_methods(monkeypatch):
    sys.path.insert(0, str(ROOT / "appserver" / "appserver"))
    import pooled_http

    calls = []
    monkeypatch.setattr(
        pooled_http.PooledHttp, "request",
        lambda self, method, url, **kwargs: calls.append((method, url)),
    )
    client = pooled_http.PooledHttp()
    client.get("https://example.test")
    client.post("https://example.test")
    client.put("https://example.test")
    client.delete("https://example.test")
    assert [method for method, _ in calls] == ["GET", "POST", "PUT", "DELETE"]
    assert client.RequestException is not None


def test_appserver_unit_defaults_to_four_by_four_gthread():
    unit = UNIT.read_text(encoding="utf-8")
    workers = int(re.search(r"^Environment=TW2_APPSERVER_WORKERS=(\d+)$", unit, re.M).group(1))
    threads = int(re.search(r"^Environment=TW2_APPSERVER_THREADS=(\d+)$", unit, re.M).group(1))
    assert (workers, threads) == (4, 4)
    assert "--worker-class gthread" in unit
    assert "--workers ${TW2_APPSERVER_WORKERS}" in unit
    assert "--threads ${TW2_APPSERVER_THREADS}" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit


def test_bootstrap_and_port_migration_install_the_tracked_unit():
    for relative in (
        "ops/staging/bootstrap_stage_app_services.sh",
        "ops/staging/migrate_app_port_to_80.sh",
    ):
        script = (ROOT / relative).read_text(encoding="utf-8")
        assert "ops/systemd/tradewave-appserver.service" in script
        assert "--worker-class sync" not in script
        assert "TW2_APPSERVER_WORKERS" in script
        assert "TW2_APPSERVER_THREADS" in script


def test_gunicorn_access_formats_drop_query_strings():
    for path in (
        UNIT,
        ROOT / "ops" / "systemd" / "tradewave-apiserver.service",
    ):
        text = path.read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if "--access-logformat" in line)
        assert "%(U)s" in line
        assert "%(q)s" not in line
        assert "%(f)s" not in line


def test_gateway_restart_tracks_appserver_and_proves_service_login():
    unit = API_UNIT.read_text(encoding="utf-8")

    assert "After=network.target redis-server.service tradewave-appserver.service" in unit
    assert "PartOf=tradewave-appserver.service" in unit
    assert "ExecStartPost=/home/flask/venv-api/bin/python -c" in unit
    assert "from apiserver.appserver_client import _get_token; assert _get_token()" in unit


def test_stage_web_bootstrap_keeps_credentials_out_of_access_logs():
    script = (
        ROOT / "ops" / "staging" / "bootstrap_stage_web_services.sh"
    ).read_text(encoding="utf-8")
    web_unit = (ROOT / "ops" / "systemd" / "tradewave-web.service").read_text(encoding="utf-8")
    line = next(line for line in web_unit.splitlines() if "--access-logformat" in line)
    assert "%(U)s" in line
    assert "%(q)s" not in line
    assert "%(f)s" not in line
    assert "--bind 127.0.0.1:5500" in web_unit
    assert "--bind __TW2_WEB_VLAN__:5500" in web_unit
    assert "ops/systemd/tradewave-web.service" in script
    assert "ops/nginx/conf.d/tradewave-log-format.conf" in script
    assert "tradewave.access.log tw_noargs" in script


def test_nginx_trade_wave_logs_use_no_args_format():
    fmt = (ROOT / "ops" / "nginx" / "conf.d" / "tradewave-log-format.conf").read_text()
    assert "$uri" in fmt
    assert "$args" not in fmt
    assert "$request " not in fmt
    assert "$http_referer" not in fmt
    portal = (ROOT / "ops" / "nginx" / "tradewave-developer-portal.conf").read_text()
    assert "tradewave-api.access.log tw_noargs" in portal
    assert "tradewave-mcp.access.log tw_noargs" in portal
    assert "listen __TW2_DEVELOPER_PORT__;" in portal
    assert "server_name __TW2_API_PUBLIC_HOST__;" in portal


def test_post_resize_staging_defaults_match_release_topology():
    target = (ROOT / "ops" / "staging" / "target.env").read_text(encoding="utf-8")
    assert 'TGT_APP_WORKERS="${TGT_APP_WORKERS:-4}"' in target
    assert 'TGT_APP_THREADS="${TGT_APP_THREADS:-4}"' in target


def test_deploy_pins_source_build_and_one_time_login_cutover():
    deploy = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
    assert "TW2_DEPLOY_SHA" in deploy
    assert 'DEPLOY_REPO="${TW2_DEPLOY_REPO:-/home/flask}"' in deploy
    assert 'BUILD="$DEPLOY_REPO/web-react/build"' in deploy
    assert 'git -C "$DEPLOY_REPO" status' in deploy
    assert '"$DEPLOY_REPO/ops/verify_deploy.sh"' in deploy
    assert ".tradewave-source-sha" in deploy
    assert "chmod -R a+rX releases/build-$REL" in deploy
    assert "git -C \"$repo\" merge --ff-only \"$EXPECTED_SHA\"" in deploy
    assert "TW2_SERVICE_LOGIN_CUTOVER" in deploy
    assert "service-login-header-v1" in deploy
    assert "service login header canary OK" in deploy
    assert "from apiserver.appserver_client import _get_token" in deploy
    assert "SELECT roles FROM users WHERE api_key_hash = %s" in deploy
    assert "len(rows) != 1" in deploy
    assert 'hmac.compare_digest(role, "service_account")' in deploy
    assert "MCP_SERVICE_ACCOUNT_PREFLIGHT" in deploy
    assert "MCP_GATEWAY_KEY" in deploy
    assert "FROM api_keys k JOIN users u ON u.id = k.user_id" in deploy
    assert 'hmac.compare_digest(str(api_tier or ""), "mcp")' in deploy
    assert deploy.index("service-account identity OK") < deploy.index(
        "both target worktrees are clean"
    )
    assert deploy.index("service-account identity OK") < deploy.index(
        "REMOTE_WEB_QUIESCE"
    )
    assert deploy.index("service login header canary OK") < deploy.index(
        "touch '$SERVICE_LOGIN_STAMP'"
    )
    assert deploy.index("WEB_QUIESCED=1") > deploy.index("REMOTE_WEB_QUIESCE")
    assert deploy.index("APP_SWITCH_STARTED=1") > deploy.index("WEB_QUIESCED=1")
    recovery = deploy[deploy.index("recover_service_login_cutover"):deploy.index(
        "trap recover_service_login_cutover"
    )]
    assert "systemctl restart tradewave-appserver" not in recovery
    assert "callers remain stopped (fail-closed)" in recovery


def test_react_release_permissions_and_assets_are_release_gates():
    builder = (ROOT / "ops" / "build_react_release.sh").read_text(encoding="utf-8")
    verifier = (ROOT / "ops" / "verify_deploy.sh").read_text(encoding="utf-8")

    assert 'chmod -R a+rX "$REPO/web-react/build"' in builder
    assert "find -L /home/flask/web-react/build/static/js" in verifier
    assert 'wc_web "/app/static/js/$react_js"' in verifier
    assert "React main bundle -> 200" in verifier
    assert "wc_web /app/manifest.json" in verifier
    assert "React manifest -> 200" in verifier


def test_deploy_requires_exact_environment_portal_hosts():
    deploy = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
    portal_check = deploy[
        deploy.index("check_portal_host()") : deploy.index(
            'echo "==> [$ENV] pre-flight: split-tier runtime files'
        )
    ]
    assert 'if [ "$val" != "$want" ]; then' in portal_check
    assert "Cross-environment API/MCP/developer hosts" in portal_check
    for key in (
        "TW2_API_PUBLIC_HOST",
        "TW2_DEVELOPERS_PUBLIC_HOST",
        "TW2_MCP_PUBLIC_HOST",
    ):
        assert f'check_portal_host "$box" {key}' in deploy
    assert 'for box in "$WEB" "$APP"; do' in deploy


def test_split_daily_pick_uses_reachable_web_nginx():
    secrets = (ROOT / "ops" / "staging" / "make_staging_secrets.sh").read_text()
    assert "TW2_FEATURED_HISTORY_URL=http://${TGT_WEB_VLAN}:5500/internal/featured-history" in secrets
    assert "TW2_API_PUBLIC_HOST=${TGT_API_HOST}" in secrets
    assert "TW2_MCP_PUBLIC_HOST=${TGT_MCP_HOST}" in secrets
    assert "TW2_DEVELOPERS_PUBLIC_HOST=${TGT_DEVELOPERS_HOST}" in secrets
    assert "TW2_MCP_LIVE=1" in secrets
    assert "TW2_API_CONSOLE_ENABLED=1" in secrets
    assert "TW2_API_PRICING_LIVE=0" in secrets
    assert "https://${TGT_WEB_HOST}/webhooks/stripe" in secrets
    assert "TW2_FEATURED_HISTORY_URL=http://${TGT_WEB_VLAN}/internal/featured-history" not in secrets


def test_app_tunnel_preserves_appserver_80_and_routes_public_api_surface_to_8080():
    tunnel = (ROOT / "ops/staging/bootstrap_stage_app_tunnel.sh").read_text(
        encoding="utf-8"
    )
    assert "service: http://localhost:80" in tunnel
    assert tunnel.count("service: http://localhost:8080") == 3
    for variable in ("TGT_API_HOST", "TGT_MCP_HOST", "TGT_DEVELOPERS_HOST"):
        assert variable in tunnel
