"""Release contracts for bounded appserver concurrency and credential-safe logs."""

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "ops" / "systemd" / "tradewave-appserver.service"


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


def test_stage_web_bootstrap_keeps_credentials_out_of_access_logs():
    script = (
        ROOT / "ops" / "staging" / "bootstrap_stage_web_services.sh"
    ).read_text(encoding="utf-8")
    line = next(line for line in script.splitlines() if "--access-logformat" in line)
    assert "%(U)s" in line
    assert "%(q)s" not in line
    assert "%(f)s" not in line
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


def test_split_daily_pick_uses_reachable_web_nginx():
    secrets = (ROOT / "ops" / "staging" / "make_staging_secrets.sh").read_text()
    assert "TW2_FEATURED_HISTORY_URL=http://${TGT_WEB_VLAN}/internal/featured-history" in secrets
    assert "TGT_WEB_VLAN}:5500/internal/featured-history" not in secrets
