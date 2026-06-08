"""Gateway endpoint wiring (apiserver routes) - the integration layer over the unit-tested
functions. Auth + redis + the appserver are mocked, so these exercise ONLY the route plumbing:
the educational-only disclaimer on every signal-bearing response, the per-market band 400, the
~90% default, and the view param. Runs under /home/flask/venv (has flask+pytest+apiserver).
"""
import pytest

from apiserver import tiers

pytestmark = pytest.mark.unit  # no real external state - auth, redis, and the appserver are all mocked

_ENT = tiers.tier_for("dev")
_CUSTOMER = {"user_id": "test-user", "email": "t@example.com", "tier": "dev", "entitlements": _ENT}


@pytest.fixture
def app():
    from apiserver import app as appmod
    a = appmod.app if hasattr(appmod, "app") else appmod.create_app()
    a.config.update(TESTING=True)
    return a


@pytest.fixture
def client(app, monkeypatch):
    """Authenticated test client: auth + rate-limit + usage + ml metering mocked away."""
    from apiserver import auth, ml_quota
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(_CUSTOMER))
    monkeypatch.setattr(auth, "check_rate_limit", lambda cust: (True, {}))
    monkeypatch.setattr(auth, "record_usage", lambda *a, **k: None)
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: None)
    monkeypatch.setattr(ml_quota, "consume", lambda cust, n=1: 0)
    monkeypatch.setattr(ml_quota, "refund", lambda cust, n=1: None)
    return app.test_client()


def _patch_appsrv(monkeypatch, **fns):
    from apiserver import appserver_client
    monkeypatch.setattr(appserver_client, "market_name_map",
                        lambda: {"2": "S&P 500 STOCKS", "4": "WILSHIRE 5000", "11": "ETFs"})
    for name, fn in fns.items():
        monkeypatch.setattr(appserver_client, name, fn)


def _hdr():
    return {"Authorization": "Bearer tw_live_test"}


# --- auth ------------------------------------------------------------------------

def test_missing_key_is_401(app, monkeypatch):
    from apiserver import auth
    monkeypatch.setattr(auth, "resolve_customer", lambda key: None)
    r = app.test_client().get("/v1/scan")
    assert r.status_code == 401


# --- the band, at the HTTP layer -------------------------------------------------

def test_out_of_band_combo_is_400_with_valid_range(client, monkeypatch):
    _patch_appsrv(monkeypatch)
    r = client.get("/v1/opportunities?market=2&years=20&min_winning_years=9", headers=_hdr())
    assert r.status_code == 400
    body = r.get_json()
    msg = body["error"]["message"]
    assert "17" in msg and "20" in msg            # the valid range for S&P @20y


def test_default_min_winning_years_scales_and_passes(client, monkeypatch):
    # bare years=20 (no min_winning_years) must NOT 400 - it defaults to ~90% (20-18, in band).
    _patch_appsrv(monkeypatch, opportunities=lambda *a, **k: [])
    r = client.get("/v1/opportunities?market=2&years=20", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["disclaimer"]             # signal-bearing -> carries the disclaimer


def test_symbol_path_unsupported_market_is_400(client, monkeypatch):
    _patch_appsrv(monkeypatch)
    r = client.get("/v1/opportunities/AAPL?market=11", headers=_hdr())   # ETFs: no per-symbol grid
    assert r.status_code == 400
    assert "find_best_opportunities" in r.get_json()["error"]["message"]


# --- educational-only: the disclaimer on every signal-bearing response ------------

def test_scan_carries_disclaimer_and_echoes_view(client, monkeypatch):
    _patch_appsrv(monkeypatch, opportunities_multi=lambda *a, **k: [])
    r = client.get("/v1/scan?view=table", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["disclaimer"]
    assert body["view"] == "table"                # the view param plumbs through


def test_opportunities_carries_disclaimer(client, monkeypatch):
    _patch_appsrv(monkeypatch, opportunities=lambda *a, **k: [])
    r = client.get("/v1/opportunities?market=2", headers=_hdr())
    assert r.get_json()["disclaimer"]


def test_patterns_carries_disclaimer(client, monkeypatch):
    _patch_appsrv(monkeypatch,
                  pattern_stats=lambda *a, **k: {"symbol": "AAPL", "market": "2",
                                                 "win_rate": 0.8, "stats": {}})
    r = client.get("/v1/patterns/2/AAPL", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["disclaimer"]


def test_seasonal_chart_carries_disclaimer(client, monkeypatch):
    _patch_appsrv(monkeypatch,
                  seasonal_chart=lambda *a, **k: {"symbol": "AAPL", "market": "2",
                                                  "seasonal_curve": [], "per_year_bars": [], "stats": {}})
    r = client.get("/v1/seasonal-chart?market=2&symbol=AAPL", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["disclaimer"]


def test_track_record_carries_disclaimer(client, monkeypatch):
    _patch_appsrv(monkeypatch, track_record=lambda *a, **k: {"summary": {"count": 5}, "picks": []})
    r = client.get("/v1/daily-pick/track-record", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["disclaimer"]


def test_markets_has_no_disclaimer_but_has_pattern_detection(client, monkeypatch):
    _patch_appsrv(monkeypatch,
                  list_markets=lambda: [{"id": "2", "name": "S&P 500 STOCKS"},
                                        {"id": "4", "name": "WILSHIRE 5000"}])
    r = client.get("/v1/markets", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert "disclaimer" not in body               # catalog endpoint - no signal, no disclaimer
    m2 = next(m for m in body["markets"] if m["id"] == "2")
    assert m2["pattern_detection"]["by_symbol_detection"] is True
