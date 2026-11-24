"""ops/warm_after_restart.py: fail-soft, bounded, never primes the API scan cache."""
import datetime as dt
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "warm_after_restart.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_after_restart", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _install_fakes(monkeypatch, client):
    pkg = types.ModuleType("apiserver")
    se = types.ModuleType("apiserver.seasonal_evidence")
    se.market_today = lambda: dt.date(2026, 11, 24)
    pkg.appserver_client = client
    pkg.seasonal_evidence = se
    monkeypatch.setitem(sys.modules, "apiserver", pkg)
    monkeypatch.setitem(sys.modules, "apiserver.appserver_client", client)
    monkeypatch.setitem(sys.modules, "apiserver.seasonal_evidence", se)


def test_warms_every_market_with_copies(monkeypatch, capsys):
    calls = []
    client = types.ModuleType("apiserver.appserver_client")
    client.list_markets = lambda: [{"id": "0", "name": "DJ30"}, {"id": "2", "name": "S&P 500"}]

    def opportunities(market, entry):
        calls.append(("opp", market, entry))
        return [{"symbol": "AAA", "entry_date": entry, "days_out": 20}]

    def chart(market, symbol, entry, days, years):
        calls.append(("chart", market, symbol))
        return {}, []
    client.opportunities = opportunities
    client.chart_stats_and_years = chart
    _install_fakes(monkeypatch, client)
    monkeypatch.setattr(sys, "argv", ["warm", "--copies", "3", "--deadline", "10"])
    assert _load().main() == 0
    opp = [c for c in calls if c[0] == "opp"]
    assert len(opp) == 6 and {c[1] for c in opp} == {"0", "2"}
    assert all(c[2] == "2026-11-24" for c in opp)
    assert "WARMUP DONE: 6 ok, 0 failed" in capsys.readouterr().out


def test_failures_are_soft(monkeypatch, capsys):
    client = types.ModuleType("apiserver.appserver_client")
    client.list_markets = lambda: [{"id": "0", "name": "DJ30"}]

    def boom(*a, **k):
        raise RuntimeError("secret-ish detail must not print")
    client.opportunities = boom
    client.chart_stats_and_years = boom
    _install_fakes(monkeypatch, client)
    monkeypatch.setattr(sys, "argv", ["warm", "--copies", "2", "--deadline", "5"])
    assert _load().main() == 0
    out = capsys.readouterr().out
    assert "RuntimeError" in out and "secret-ish" not in out
    assert "0 ok, 2 failed" in out


def test_market_listing_failure_skips(monkeypatch, capsys):
    client = types.ModuleType("apiserver.appserver_client")

    def boom():
        raise ConnectionError("down")
    client.list_markets = boom
    _install_fakes(monkeypatch, client)
    monkeypatch.setattr(sys, "argv", ["warm"])
    assert _load().main() == 0
    assert "WARMUP SKIPPED" in capsys.readouterr().out


def test_never_primes_scan_cache_or_calls_scan():
    src = SCRIPT.read_text()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    body = code.split('"""', 2)[2]  # skip the module docstring
    assert "scan_cache" not in body and "/v1/scan" not in body


def test_deploy_runs_warmup_fail_soft_after_runtime_proof():
    deploy = (REPO / "ops" / "deploy.sh").read_text()
    proof = deploy.index('assert_live_runtime "$WEB" tradewave-web /home/flask/web')
    warm = deploy.index("ops/warm_after_restart.py")
    regen = deploy.index("regenerate ALL static pages")
    assert proof < warm < regen
    line = deploy[warm:deploy.index("\n", warm)]
    assert "|| echo" in line
