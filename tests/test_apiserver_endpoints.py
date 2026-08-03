"""Gateway endpoint wiring (apiserver routes) - the integration layer over the unit-tested
functions. Auth + redis + the appserver are mocked, so these exercise ONLY the route plumbing:
the educational-only disclaimer on every pattern-bearing response, the per-market band 400, the
~90% default, and the view param. Runs under /home/flask/venv (has flask+pytest+apiserver).
"""
import copy

import pytest

from apiserver import tiers

pytestmark = pytest.mark.unit  # no real external state - auth, redis, and the appserver are all mocked

_ENT = tiers.tier_for("dev")
_CUSTOMER = {"user_id": "test-user", "email": "t@example.com", "tier": "dev", "entitlements": _ENT}


@pytest.fixture(autouse=True)
def _bypass_shared_scan_cache(monkeypatch):
    """Route tests stay hermetic; scan-cache coordination has dedicated tests."""
    from apiserver import scan_cache

    def bypass(_key, builder):
        built = builder()
        value = built.value if isinstance(built, scan_cache.BuildResult) else built
        return scan_cache.CacheResult(value, "BYPASS")

    monkeypatch.setattr(scan_cache, "get_or_build", bypass)


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


def test_daily_pick_source_failure_returns_503_json(client, monkeypatch):
    from apiserver import appserver_client

    def unavailable():
        raise appserver_client.FeaturedHistoryUnavailable("missing")

    monkeypatch.setattr(appserver_client, "daily_pick_raw", unavailable)
    response = client.get("/v1/daily-pick", headers=_hdr())
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "daily_pick_unavailable"


# --- auth ------------------------------------------------------------------------

def test_missing_key_is_401(app, monkeypatch):
    from apiserver import auth, scan_cache
    cache_calls = {"count": 0}

    def cache_spy(*_args, **_kwargs):
        cache_calls["count"] += 1
        raise AssertionError("unauthenticated request reached shared scan cache")

    monkeypatch.setattr(auth, "resolve_customer", lambda key: None)
    monkeypatch.setattr(scan_cache, "get_or_build", cache_spy)
    r = app.test_client().get("/v1/scan")
    assert r.status_code == 401
    assert cache_calls["count"] == 0


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
    assert r.get_json()["disclaimer"]             # pattern-bearing -> carries the disclaimer


def test_symbol_path_unsupported_market_is_400(client, monkeypatch):
    _patch_appsrv(monkeypatch)
    r = client.get("/v1/opportunities/AAPL?market=11", headers=_hdr())   # ETFs: no per-symbol grid
    assert r.status_code == 400
    assert "find_best_opportunities" in r.get_json()["error"]["message"]


# --- educational-only: the disclaimer on every pattern-bearing response ------------

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


def test_health_exposes_storm_breaker_canary(client, monkeypatch):
    monkeypatch.setattr("apiserver.app.storm_breaker_active", lambda: False)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["storm_breaker_active"] is False
    assert "Server-Timing" in response.headers


def test_health_fails_while_storm_breaker_is_active(client, monkeypatch):
    monkeypatch.setattr("apiserver.app.storm_breaker_active", lambda: True)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.get_json()["storm_breaker_active"] is True


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


# ============================ card-building endpoint tests ============================
# These mock the appserver card-build chain so a real PatternCard flows through the route.

_STATS = {"Percent Profitable": "90%", "Sharpe Ratio": "1.5", "Avg Profit - All": "5%",
          "Median Profit": "3%", "Std Dev": "3.40%", "Annualized Return": "4%",
          "Cumulative Return": "50%", "Sharpe Ratio2": "1.80"}
_ENTRIES = ([{"year": 2015 + i, "pct": "4.00,6.00,-1.00"} for i in range(9)]
            + [{"year": 2024, "pct": "-3.00,2.00,-5.00"}])


def _opp(win_rate=0.9, symbol="AAPL", market="2", direction="long", entry="2026-07-01"):
    return {"symbol": symbol, "market": market, "direction": direction, "entry_date": entry,
            "days_out": 21, "sharpe_ratio": 1.5, "avg_profit_pct": 5.0,
            "median_profit_pct": 3.0, "win_rate": win_rate, "years": "10"}


def _mock_card_chain(monkeypatch, multi=None, by_symbol=None, curve=None, entries=None):
    from apiserver import appserver_client as ac
    monkeypatch.setattr(ac, "market_name_map",
                        lambda: {"2": "S&P 500 STOCKS", "4": "WILSHIRE 5000", "0": "DOW 30 STOCKS",
                                 "7": "FUTURES & COMMODITIES", "11": "ETFs"})
    receipt_rows = _ENTRIES if entries is None else entries
    monkeypatch.setattr(ac, "chart_stats_and_years", lambda *a, **k: (dict(_STATS), list(receipt_rows)))
    monkeypatch.setattr(ac, "_seasonal_curve", lambda *a, **k: list(curve or []))
    monkeypatch.setattr(ac, "_win_rate_for_opp", lambda o: 0.9)
    if multi is not None:
        monkeypatch.setattr(ac, "opportunities_multi", lambda *a, **k: list(multi))
    if by_symbol is not None:
        monkeypatch.setattr(ac, "opportunities_by_symbol", lambda *a, **k: list(by_symbol))


_WIN = "window=2026-06-01..2026-12-31"   # an explicit range that contains the opp entry_date


def test_scan_card_carries_extend_research_and_timing(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp()])
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    assert r.status_code == 200
    card = r.get_json()["opportunities"][0]
    assert "extend_research" in card and card["setup"]["timing"] is not None
    assert card["bias"] == "bullish"
    assert r.headers["X-TW-Scan-Cache"] == "BYPASS"
    assert "scan-cache" in r.headers["Server-Timing"]


def test_scan_evidence_view_enriches_only_winner_with_chart(client, monkeypatch):
    curve = [
        {"date": "2026-07-01", "index": 40.0},
        {"date": "2026-07-02", "index": 41.0},
    ]
    _mock_card_chain(
        monkeypatch,
        multi=[_opp(symbol="WIN"), _opp(symbol="RUN", win_rate=0.8)],
        curve=curve,
    )
    r = client.get(
        f"/v1/scan?{_WIN}&markets=2&limit=2&view=evidence&include=chart",
        headers=_hdr(),
    )
    assert r.status_code == 200
    cards = r.get_json()["opportunities"]
    assert "chart" in cards[0]
    assert cards[0]["chart"]["trend_chart"] == curve
    assert "per_year" in cards[0]["receipts"]
    assert "chart" not in cards[1]
    assert "per_year" not in cards[1]["receipts"]
    assert cards[0]["wave_viewer"]["pattern"]["symbol"] == "WIN"


def test_default_scan_enriches_only_requested_rows(client, monkeypatch):
    from apiserver import appserver_client as ac
    rows = [_opp(symbol=f"SYM{i}") for i in range(10)]
    chart_calls = {"count": 0}
    _mock_card_chain(monkeypatch, multi=rows)

    def receipts(*_args, **_kwargs):
        chart_calls["count"] += 1
        return dict(_STATS), list(_ENTRIES)

    monkeypatch.setattr(ac, "chart_stats_and_years", receipts)
    response = client.get(
        f"/v1/scan?{_WIN}&markets=2&limit=5&view=decision", headers=_hdr()
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 5
    assert chart_calls["count"] == 5


def test_shared_core_reused_across_users_but_ml_is_metered_per_request(app, monkeypatch):
    from apiserver import appserver_client as ac, auth, ml_quota, scan_cache
    rows = [_opp(symbol=f"SYM{i}") for i in range(5)]
    counts = {"opp": 0, "chart": 0}
    metered_users = []
    stored = {}

    monkeypatch.setattr(auth, "resolve_customer", lambda key: {
        **_CUSTOMER, "user_id": key,
    })
    monkeypatch.setattr(auth, "check_rate_limit", lambda cust: (True, {}))
    monkeypatch.setattr(auth, "record_usage", lambda *a, **k: None)
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: None)
    monkeypatch.setattr(ml_quota, "refund", lambda cust, n=1: None)

    def consume(customer, n=1):
        metered_users.append(customer["user_id"])
        return n

    monkeypatch.setattr(ml_quota, "consume", consume)

    def opportunities(*_args, **_kwargs):
        counts["opp"] += 1
        return list(rows)

    def receipts(*_args, **_kwargs):
        counts["chart"] += 1
        return dict(_STATS), list(_ENTRIES)

    def memory_cache(key, builder):
        if key not in stored:
            built = builder()
            stored[key] = copy.deepcopy(built.value)
            status = "MISS"
        else:
            status = "HIT"
        return scan_cache.CacheResult(copy.deepcopy(stored[key]), status)

    monkeypatch.setattr(ac, "market_name_map", lambda: {"2": "S&P 500 STOCKS"})
    monkeypatch.setattr(ac, "opportunities_multi", opportunities)
    monkeypatch.setattr(ac, "chart_stats_and_years", receipts)
    monkeypatch.setattr(ac, "_seasonal_curve", lambda *_a, **_k: [])
    monkeypatch.setattr(ac, "ml_scores", lambda _market, items: [
        {"ml_score": 80, "win_prob": 0.8, "pred_return": 5.0, "pred_mfe": 7.0}
        for _ in items
    ])
    monkeypatch.setattr(scan_cache, "get_or_build", memory_cache)

    test_client = app.test_client()
    one = test_client.get(
        f"/v1/scan?{_WIN}&markets=2&limit=5",
        headers={"Authorization": "Bearer user-one"},
    )
    two = test_client.get(
        f"/v1/scan?{_WIN}&markets=2&limit=5",
        headers={"Authorization": "Bearer user-two"},
    )
    assert (one.status_code, two.status_code) == (200, 200)
    assert (one.headers["X-TW-Scan-Cache"], two.headers["X-TW-Scan-Cache"]) == (
        "MISS", "HIT"
    )
    assert counts == {"opp": 1, "chart": 5}
    assert metered_users == ["user-one", "user-two"]


def test_scan_cache_boundary_drops_prices_private_fields_and_ml(client, monkeypatch):
    from apiserver import appserver_client as ac, scan_cache
    unsafe = _opp()
    unsafe.update(price=123.45, _private="internal", ml={"win_prob": 0.99})
    captured = {}

    monkeypatch.setattr(ac, "market_name_map", lambda: {"2": "S&P 500 STOCKS"})
    monkeypatch.setattr(ac, "opportunities_multi", lambda *_a, **_k: [unsafe])
    monkeypatch.setattr(ac, "chart_stats_and_years", lambda *_a, **_k: (
        {**_STATS, "52W High": 999.0},
        [{"year": 2025, "pct": "5.0,6.0,-1.0", "price": 456.78}],
    ))
    monkeypatch.setattr(ac, "_seasonal_curve", lambda *_a, **_k: [])

    def inspect(_key, builder):
        built = builder()
        captured.update(copy.deepcopy(built.value))
        return scan_cache.CacheResult(built.value, "MISS")

    monkeypatch.setattr(scan_cache, "get_or_build", inspect)
    response = client.get(
        f"/v1/scan?{_WIN}&markets=2&limit=1", headers=_hdr()
    )
    assert response.status_code == 200
    record = captured["candidates"][0]
    assert "price" not in record["opp"] and "_private" not in record["opp"]
    assert record["opp"]["ml"] is None
    assert "52W High" not in record["stats"]
    assert set(record["chart_entries"][0]) == {"year", "pct"}


def test_partial_receipt_failure_is_never_published(client, monkeypatch):
    from apiserver import appserver_client as ac, scan_cache
    _mock_card_chain(monkeypatch, multi=[_opp()])
    monkeypatch.setattr(ac, "chart_stats_and_years", lambda *_a, **_k: (None, None))
    captured = {}

    def inspect(_key, builder):
        built = builder()
        captured["cacheable"] = built.cacheable
        return scan_cache.CacheResult(built.value, "BYPASS")

    monkeypatch.setattr(scan_cache, "get_or_build", inspect)
    response = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    assert response.status_code == 200
    assert captured["cacheable"] is False


def test_partial_market_failure_is_explicit_and_never_published(client, monkeypatch):
    from apiserver import appserver_client as ac, scan_cache
    _mock_card_chain(monkeypatch)
    monkeypatch.setattr(
        ac, "opportunities_multi", lambda *_a, **_k: ([_opp()], ["4"])
    )
    captured = {}

    def inspect(_key, builder):
        built = builder()
        captured["cacheable"] = built.cacheable
        return scan_cache.CacheResult(built.value, "BYPASS")

    monkeypatch.setattr(scan_cache, "get_or_build", inspect)
    response = client.get(f"/v1/scan?{_WIN}&markets=2,4", headers=_hdr())
    assert response.status_code == 200
    body = response.get_json()
    assert body["market_failures"] == ["4"]
    assert "omitted" in body["summary"].lower()
    assert captured["cacheable"] is False


def test_scan_busy_is_retryable_json_503(client, monkeypatch):
    from apiserver import appserver_client as ac, scan_cache
    monkeypatch.setattr(ac, "market_name_map", lambda: {"2": "S&P 500 STOCKS"})
    monkeypatch.setattr(
        scan_cache, "get_or_build",
        lambda *_a, **_k: (_ for _ in ()).throw(scan_cache.ScanBuildBusy()),
    )
    response = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "scan_busy"
    assert response.headers["Retry-After"] == "1"


def test_scan_no_signal_card_omits_order_ticket(client, monkeypatch):
    weak = ([{"year": 2015 + i, "pct": "4.00,6.00,-1.00"} for i in range(3)]
            + [{"year": 2018 + i, "pct": "-3.00,2.00,-5.00"} for i in range(7)])
    _mock_card_chain(monkeypatch, multi=[_opp(win_rate=0.30)], entries=weak)
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    card = r.get_json()["opportunities"][0]
    assert card["bias"] == "neutral"
    assert "order_ticket" not in card["next_step"]


def test_scan_lookback_note_for_out_of_band_markets(client, monkeypatch):
    # years=20, min_winning_years=16: out of band for S&P(floor 17) AND Wilshire(floor 18).
    _mock_card_chain(monkeypatch, multi=[])
    r = client.get(f"/v1/scan?markets=2,4&years=20&min_winning_years=16&{_WIN}", headers=_hdr())
    assert r.status_code == 200
    note = r.get_json().get("lookback_note")
    assert note and "S&P 500 STOCKS" in note and "WILSHIRE 5000" in note


def test_scan_pe_position_mode_rejected(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[])
    r = client.get("/v1/scan?pe_cycle=pe2", headers=_hdr())
    assert r.status_code == 400


def test_analyze_carries_disclaimer_and_extend_research(client, monkeypatch):
    _mock_card_chain(monkeypatch, by_symbol=[_opp()])
    r = client.get("/v1/analyze/AAPL?market=2", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["disclaimer"] and body["view"] == "full"
    assert "extend_research" in body["card"]


def test_analyze_custom_lookback_uses_matching_symbol_detection_band(client, monkeypatch):
    from apiserver import appserver_client as ac

    seen = {}
    _mock_card_chain(monkeypatch, by_symbol=[_opp()])

    def by_symbol(market, symbol, **kwargs):
        seen.update(market=market, symbol=symbol, **kwargs)
        return [_opp()]

    monkeypatch.setattr(ac, "opportunities_by_symbol", by_symbol)

    response = client.get("/v1/analyze/AAPL?market=2&years=16", headers=_hdr())

    assert response.status_code == 200
    assert seen["year1"] == "16"
    assert seen["year2"] == "14"
    assert response.get_json()["card"]["stats"]["years"] == "16"


def test_analyze_include_chart_attaches_inline(client, monkeypatch):
    _mock_card_chain(monkeypatch, by_symbol=[_opp()],
                     curve=[{"date": "2026-07-01", "index": 40.0}, {"date": "2026-07-02", "index": 41.0}])
    r = client.get("/v1/analyze/AAPL?market=2&include=chart", headers=_hdr())
    card = r.get_json()["card"]
    assert "chart" in card
    assert card["chart"]["trend_chart"] and card["chart"]["per_year_bars"]


def test_analyze_bare_ticker_resolves_to_primary_listing(client, monkeypatch):
    from apiserver import appserver_client as ac
    _mock_card_chain(monkeypatch, by_symbol=[_opp(symbol="IBM")])
    monkeypatch.setattr(ac, "resolve_market_for_symbol", lambda sym, scope: ["0", "2"])
    r = client.get("/v1/analyze/IBM", headers=_hdr())          # no ?market
    assert r.status_code == 200
    note = r.get_json()["card"]["note"]
    assert "also trades in" in note and "DOW 30" in note


def test_analyze_strict_ambiguous_is_400(client, monkeypatch):
    from apiserver import appserver_client as ac
    _mock_card_chain(monkeypatch)
    monkeypatch.setattr(ac, "resolve_market_for_symbol", lambda sym, scope: ["0", "2"])
    r = client.get("/v1/analyze/IBM?strict=1", headers=_hdr())
    assert r.status_code == 400


def test_score_requires_json_body(client):
    r = client.post("/v1/score", headers=_hdr())
    assert r.status_code == 400


def test_score_rejects_non_ml_market(client, monkeypatch):
    _mock_card_chain(monkeypatch)
    r = client.post("/v1/score", json={"market": "7",
                    "opportunities": [{"symbol": "CL", "date": "2026-07-01", "days_out": 21, "direction": "long"}]},
                    headers=_hdr())
    assert r.status_code == 403


def test_score_success_carries_disclaimer(client, monkeypatch):
    from apiserver import appserver_client as ac, ml_quota
    monkeypatch.setattr(ml_quota, "consume", lambda cust, n=1: n)     # grant the batch
    monkeypatch.setattr(ac, "ml_scores",
                        lambda market, items: [{"ml_score": 80, "win_prob": 0.8,
                                                "pred_return": 5.0, "pred_mfe": 7.0} for _ in items])
    r = client.post("/v1/score", json={"market": "2",
                    "opportunities": [{"symbol": "AAPL", "date": "2026-07-01", "days_out": 21, "direction": "long"}]},
                    headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["disclaimer"] and body["granted"] == 1


def test_daily_pick_carries_disclaimer(client, monkeypatch):
    from apiserver import appserver_client as ac
    _mock_card_chain(monkeypatch)
    monkeypatch.setattr(ac, "daily_pick_raw",
                        lambda: {"opp": _opp(), "featured_date": "2026-06-08"})
    monkeypatch.setattr(ac, "track_record",
                        lambda: {"summary": {"count": 10, "win_count": 7, "win_rate": 0.7, "avg_return_pct": 3.0}})
    r = client.get("/v1/daily-pick", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["disclaimer"] and body["card"]["extend_research"]


# ==================== honesty + robustness (2026-06-12 prod-429 review) ====================

import requests as _requests


def _http_error(status):
    resp = _requests.Response()
    resp.status_code = status
    return _requests.HTTPError("%d error" % status, response=resp)


# --- receipts_unavailable flows through the scan route -----------------------------

def test_scan_failed_receipts_never_render_false_no_signal(client, monkeypatch):
    from apiserver import appserver_client as ac
    _mock_card_chain(monkeypatch, multi=[_opp()])
    monkeypatch.setattr(ac, "chart_stats_and_years", lambda *a, **k: (None, None))  # fetch FAILED
    r = client.get(f"/v1/scan?{_WIN}&markets=2&view=full", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    card = body["opportunities"][0]
    assert card["receipts"]["receipts_unavailable"] is True
    assert card["bias"] == "bullish"                  # the OppList-stats signal is KEPT
    assert "unavailable" in card["verdict"].lower()
    assert "unavailable" in body["summary"].lower() # degraded enrichment named in the lead


# --- structured 503 on the chart endpoints ------------------------------------------

def test_patterns_upstream_429_is_structured_503(client, monkeypatch):
    def _boom(*a, **k):
        raise _http_error(429)
    _patch_appsrv(monkeypatch, pattern_stats=_boom)
    r = client.get("/v1/patterns/2/AAPL", headers=_hdr())
    assert r.status_code == 503
    msg = r.get_json()["error"]["message"]
    assert "chart data temporarily unavailable - retry shortly" in msg


def test_seasonal_chart_upstream_timeout_is_structured_503(client, monkeypatch):
    def _boom(*a, **k):
        raise _requests.ConnectTimeout("timed out")
    _patch_appsrv(monkeypatch, seasonal_chart=_boom)
    r = client.get("/v1/seasonal-chart?market=2&symbol=AAPL", headers=_hdr())
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "upstream_unavailable"


# --- market forgiveness + unknown-vs-out-of-scope distinction -----------------------

def test_opportunities_accepts_exact_name_case_insensitive(client, monkeypatch):
    _patch_appsrv(monkeypatch, opportunities=lambda *a, **k: [])
    r = client.get("/v1/opportunities?market=s%26p+500+stocks", headers=_hdr())
    assert r.status_code == 200


def test_analyze_market_alias_resolves(client, monkeypatch):
    _mock_card_chain(monkeypatch, by_symbol=[_opp()])
    r = client.get("/v1/analyze/AAPL?market=sp500", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["card"]["market"]["id"] == "2"


def test_analyze_unknown_market_is_400_not_upsell(client, monkeypatch):
    _mock_card_chain(monkeypatch)
    r = client.get("/v1/analyze/AAPL?market=narnia", headers=_hdr())
    assert r.status_code == 400
    msg = r.get_json()["error"]["message"]
    assert "unknown market" in msg and "upgrade" not in msg.lower()


def test_scan_unknown_market_is_400_not_upsell(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[])
    r = client.get("/v1/scan?markets=atlantis", headers=_hdr())
    assert r.status_code == 400
    msg = r.get_json()["error"]["message"]
    assert "unknown market" in msg and "upgrade" not in msg.lower()


def test_scan_out_of_scope_catalog_market_is_honest_403(client, monkeypatch):
    from apiserver import auth
    free = dict(_CUSTOMER, tier="free", entitlements=tiers.tier_for("free"))
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(free))
    _mock_card_chain(monkeypatch, multi=[])
    r = client.get("/v1/scan?markets=ETFs", headers=_hdr())   # real market, free scope is ['2']
    assert r.status_code == 403
    body = r.get_json()["error"]
    assert "scope" in body["message"] and body["upgrade_url"]


# --- scan honesty trio ---------------------------------------------------------------

def test_scan_min_win_rate_percent_autonormalizes_with_note(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp()])
    r = client.get(f"/v1/scan?{_WIN}&markets=2&min_win_rate=90", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["count"] == 1                       # 0.9 passes the normalized 0.90
    assert "normalized" in body["min_win_rate_note"]
    assert "normalized" in body["summary"]


def test_scan_min_win_rate_over_100_is_400_with_guidance(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[])
    r = client.get("/v1/scan?min_win_rate=150", headers=_hdr())
    assert r.status_code == 400
    assert "0.9" in r.get_json()["error"]["message"]


def test_scan_all_no_signal_lead_is_honest(client, monkeypatch):
    weak = ([{"year": 2015 + i, "pct": "4.00,6.00,-1.00"} for i in range(3)]
            + [{"year": 2018 + i, "pct": "-3.00,2.00,-5.00"} for i in range(7)])
    _mock_card_chain(monkeypatch, multi=[_opp(win_rate=0.30)], entries=weak)
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    body = r.get_json()
    assert body["summary"].startswith("Evaluated 1 candidate - 0 have a high-conviction edge")
    assert "Found" not in body["summary"]


# --- scan dedupe ----------------------------------------------------------------------

def test_scan_dedupes_cross_market_duplicates(client, monkeypatch):
    # the same (symbol, direction, entry_date, hold_days) listed by 3 markets (the live
    # MSFT x3 case) must collapse to ONE ranked row, preferring the primary listing.
    rows = [_opp(market="0"), _opp(market="1"), _opp(market="2")]
    _mock_card_chain(monkeypatch, multi=rows)
    r = client.get(f"/v1/scan?{_WIN}&markets=0,1,2", headers=_hdr())
    body = r.get_json()
    assert body["evaluated_count"] == 1 and body["count"] == 1
    assert body["opportunities"][0]["market"]["id"] == "2"


def test_scan_keeps_distinct_setups(client, monkeypatch):
    rows = [_opp(market="2"), _opp(market="2", direction="short")]
    _mock_card_chain(monkeypatch, multi=rows)
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    assert r.get_json()["evaluated_count"] == 2


# --- free-tier wall visible ------------------------------------------------------------

def test_scan_plan_cap_is_visible_with_upgrade_url(client, monkeypatch):
    from apiserver import auth
    free = dict(_CUSTOMER, tier="free", entitlements=tiers.tier_for("free"))
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(free))
    rows = [_opp(symbol="S%02d" % i) for i in range(6)]
    _mock_card_chain(monkeypatch, multi=rows)
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    body = r.get_json()
    assert body["capped_by_plan"] is True
    assert body["shown_of_evaluated"] == "3 of 6"   # free opp_limit = 3
    assert body["upgrade_url"]
    assert "capped by your plan" in body["summary"]


def test_scan_uncapped_envelope_is_clean(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp()])
    body = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr()).get_json()
    assert body["capped_by_plan"] is False
    assert "upgrade_url" not in body


def test_me_carries_upgrade_url(client, monkeypatch):
    _patch_appsrv(monkeypatch, list_markets=lambda: [])
    r = client.get("/v1/me", headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["upgrade_url"]


# --- token-bomb trim ---------------------------------------------------------------------

def test_decision_view_omits_extend_research(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp()])
    r = client.get(f"/v1/scan?{_WIN}&markets=2&view=decision", headers=_hdr())
    card = r.get_json()["opportunities"][0]
    assert "extend_research" not in card
    assert card["verdict"] and card["bias"] == "bullish"


def test_full_view_keeps_extend_research(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp()])
    r = client.get(f"/v1/scan?{_WIN}&markets=2&view=full", headers=_hdr())
    assert "extend_research" in r.get_json()["opportunities"][0]


def test_symbols_prefix_and_limit_paging(client, monkeypatch):
    _patch_appsrv(monkeypatch,
                  list_symbols=lambda m: [{"symbol": s, "name": s}
                                          for s in ("AAPL", "AAL", "MSFT")])
    r = client.get("/v1/markets/2/symbols?prefix=aa&limit=1", headers=_hdr())
    body = r.get_json()
    assert body["total"] == 3 and body["matched"] == 2 and body["count"] == 1
    assert body["symbols"][0]["symbol"] == "AAPL"
    assert "note" in body                            # truncation is explicit


# --- daily-pick staleness guard -----------------------------------------------------------

def _mock_daily_pick(monkeypatch, featured_date):
    from apiserver import appserver_client as ac
    _mock_card_chain(monkeypatch)
    monkeypatch.setattr(ac, "daily_pick_raw",
                        lambda: {"opp": _opp(), "featured_date": featured_date})
    monkeypatch.setattr(ac, "track_record", lambda: {"summary": {"count": 1}})


def test_daily_pick_stale_note_when_old(client, monkeypatch):
    _mock_daily_pick(monkeypatch, "2026-01-05")
    body = client.get("/v1/daily-pick", headers=_hdr()).get_json()
    assert "2026-01-05" in body["stale_note"]
    assert body["as_of"]


def test_daily_pick_fresh_has_no_stale_note(client, monkeypatch):
    from apiserver import routes
    _mock_daily_pick(monkeypatch, routes._last_trading_day().isoformat())
    body = client.get("/v1/daily-pick", headers=_hdr()).get_json()
    assert "stale_note" not in body


# ==================== gateway contract fixes (2026-06-12 verified review) ====================

# --- 429 honesty: Retry-After + the minute|day window discriminator -----------------

class _FakeRatePipe:
    """Stands in for the redis pipeline in check_rate_limit: returns fixed counters."""
    def __init__(self, minute, day):
        self._res = [minute, True, day, True]

    def incr(self, *a):
        return self

    def expire(self, *a):
        return self

    def execute(self):
        return self._res


class _FakeRateRedis:
    def __init__(self, minute, day):
        self.minute, self.day = minute, day

    def pipeline(self):
        return _FakeRatePipe(self.minute, self.day)


def _rate_limited_client(app, monkeypatch, minute, day):
    """Authenticated client whose redis rate counters read (minute, day) - the REAL
    check_rate_limit runs (unlike the main fixture, which mocks it away)."""
    from apiserver import auth, ml_quota
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(_CUSTOMER))
    monkeypatch.setattr(auth, "record_usage", lambda *a, **k: None)
    monkeypatch.setattr(auth, "_redis", _FakeRateRedis(minute, day))
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: None)
    return app.test_client()


def test_429_minute_cap_has_retry_after_and_minute_scope(app, monkeypatch):
    rate = _ENT["rate"]                                   # dev: 60/min, 5000/day
    c = _rate_limited_client(app, monkeypatch, minute=rate["per_minute"] + 1, day=10)
    r = c.get("/v1/me", headers=_hdr())
    assert r.status_code == 429
    assert r.headers["X-RateLimit-Scope"] == "minute"
    assert 1 <= int(r.headers["Retry-After"]) <= 60       # seconds to the minute boundary
    body = r.get_json()["error"]
    assert body["code"] == "rate_limited" and body["scope"] == "minute"


def test_429_day_cap_has_day_scope_and_day_window_headers(app, monkeypatch):
    rate = _ENT["rate"]
    c = _rate_limited_client(app, monkeypatch, minute=1, day=rate["per_day"] + 1)
    r = c.get("/v1/me", headers=_hdr())
    assert r.status_code == 429
    assert r.headers["X-RateLimit-Scope"] == "day"
    assert 1 <= int(r.headers["Retry-After"]) <= 86400    # seconds to the next UTC midnight
    # the headers describe the DAY window (never the futile-auto-retry minute window)
    assert int(r.headers["X-RateLimit-Limit"]) == rate["per_day"]
    assert r.headers["X-RateLimit-Remaining"] == "0"
    import time as _time
    assert int(r.headers["X-RateLimit-Reset"]) == (int(_time.time()) // 86400 + 1) * 86400
    assert r.get_json()["error"]["scope"] == "day"


def test_within_limits_has_no_retry_after(app, monkeypatch):
    c = _rate_limited_client(app, monkeypatch, minute=1, day=1)
    from apiserver import appserver_client as ac
    monkeypatch.setattr(ac, "list_markets", lambda: [])
    r = c.get("/v1/me", headers=_hdr())
    assert r.status_code == 200
    assert "Retry-After" not in r.headers and "X-RateLimit-Scope" not in r.headers
    assert r.headers["X-RateLimit-Limit"] == str(_ENT["rate"]["per_minute"])


def test_public_demo_gets_stable_per_client_metering_buckets(app, monkeypatch):
    from apiserver import appserver_client as ac, auth, ml_quota, tiers

    demo = {"user_id": "demo", "email": "demo@tradewave.ai", "tier": "demo",
            "entitlements": tiers.tier_for("demo")}
    observed = []
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(demo))
    monkeypatch.setattr(
        auth, "check_rate_limit",
        lambda cust: (observed.append(dict(cust)) or True, {}),
    )
    monkeypatch.setattr(auth, "record_usage", lambda *a, **k: None)
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: 25)
    monkeypatch.setattr(ac, "list_markets", lambda: [])
    client = app.test_client()

    for address in ("203.0.113.10", "203.0.113.10", "203.0.113.11"):
        response = client.get(
            "/v1/me", headers={**_hdr(), "CF-Connecting-IP": address},
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        assert response.status_code == 200

    meter_ids = [cust["metering_id"] for cust in observed]
    assert meter_ids[0] == meter_ids[1]
    assert meter_ids[0] != meter_ids[2]
    assert all(value.startswith("demo:") for value in meter_ids)
    assert all("203.0.113." not in value for value in meter_ids)
    assert all(cust["user_id"] == "demo" for cust in observed)


def test_public_demo_ignores_forwarded_ip_from_non_loopback_peer(app):
    from apiserver import auth

    with app.test_request_context(
        "/", headers={"CF-Connecting-IP": "203.0.113.99"},
        environ_base={"REMOTE_ADDR": "198.51.100.7"},
    ):
        spoofed = auth._public_demo_metering_id()
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "198.51.100.7"},
    ):
        direct = auth._public_demo_metering_id()
    assert spoofed == direct


def test_rate_limit_uses_demo_metering_id_instead_of_shared_user_id(monkeypatch):
    from apiserver import auth, tiers

    keys = []

    class CapturingPipe(_FakeRatePipe):
        def incr(self, key):
            keys.append(key)
            return self

    class CapturingRedis:
        def pipeline(self):
            return CapturingPipe(1, 1)

    monkeypatch.setattr(auth, "_redis", CapturingRedis())
    customer = {
        "user_id": "demo", "metering_id": "demo:visitor-a",
        "entitlements": tiers.tier_for("demo"),
    }
    allowed, _headers = auth.check_rate_limit(customer)

    assert allowed
    assert len(keys) == 2
    assert all(":demo:visitor-a:" in key for key in keys)
    assert all(":demo:" not in key.replace(":demo:visitor-a:", ":") for key in keys)


# --- direction validation: a 400 naming the valid values, never a silent empty 200 --

@pytest.mark.parametrize("path", [
    "/v1/scan?direction=sideways",
    "/v1/opportunities?market=2&direction=sideways",
    "/v1/analyze/AAPL?market=2&direction=sideways",
    "/v1/seasonal-chart?market=2&symbol=AAPL&direction=sideways",
])
def test_invalid_direction_is_400_naming_valid_values(client, monkeypatch, path):
    _mock_card_chain(monkeypatch, multi=[], by_symbol=[_opp()])
    r = client.get(path, headers=_hdr())
    assert r.status_code == 400
    msg = r.get_json()["error"]["message"]
    assert "long" in msg and "short" in msg and "sideways" in msg


def test_direction_short_codes_and_case_accepted(client, monkeypatch):
    _patch_appsrv(monkeypatch, opportunities=lambda *a, **k: [])
    for d in ("S", "l", "LONG", "Short"):
        r = client.get("/v1/opportunities?market=2&direction=%s" % d, headers=_hdr())
        assert r.status_code == 200, d


def test_score_item_invalid_direction_is_400(client, monkeypatch):
    _mock_card_chain(monkeypatch)
    r = client.post("/v1/score", json={"market": "2", "opportunities": [
        {"symbol": "AAPL", "date": "2026-07-01", "days_out": 21, "direction": "sideways"}]},
        headers=_hdr())
    assert r.status_code == 400
    msg = r.get_json()["error"]["message"]
    assert "long" in msg and "short" in msg


def test_score_normalizes_l_s_directions(client, monkeypatch):
    from apiserver import appserver_client as ac, ml_quota
    monkeypatch.setattr(ml_quota, "consume", lambda cust, n=1: n)
    monkeypatch.setattr(ac, "ml_scores",
                        lambda market, items: [{"ml_score": 80, "win_prob": 0.8,
                                                "pred_return": 5.0, "pred_mfe": 7.0} for _ in items])
    _mock_card_chain(monkeypatch)
    r = client.post("/v1/score", json={"market": "2", "opportunities": [
        {"symbol": "AAPL", "date": "2026-07-01", "days_out": 21, "direction": "S"}]},
        headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["scores"][0]["direction"] == "short"


# --- uniform JSON error envelope on framework errors (405 etc.) ---------------------

def test_post_to_get_route_is_json_405_with_allow(client):
    r = client.post("/v1/scan", headers=_hdr())
    assert r.status_code == 405
    body = r.get_json()
    assert body["error"]["code"] == "method_not_allowed" and body["error"]["message"]
    assert "GET" in r.headers["Allow"]


def test_get_on_score_is_json_405(client):
    r = client.get("/v1/score", headers=_hdr())
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == "method_not_allowed"
    assert "POST" in r.headers["Allow"]


def test_404_envelope_unchanged(client):
    r = client.get("/v1/no-such-endpoint", headers=_hdr())
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"


# --- /score batch cap ----------------------------------------------------------------

def test_score_batch_over_cap_is_400_naming_cap(client, monkeypatch):
    from apiserver import routes
    items = [{"symbol": "AAPL", "date": "2026-07-01", "days_out": 21, "direction": "long"}
             for _ in range(routes._SCORE_BATCH_CAP + 1)]
    r = client.post("/v1/score", json={"market": "2", "opportunities": items}, headers=_hdr())
    assert r.status_code == 400
    msg = r.get_json()["error"]["message"]
    assert str(routes._SCORE_BATCH_CAP) in msg and str(len(items)) in msg


def test_score_batch_at_cap_passes(client, monkeypatch):
    from apiserver import appserver_client as ac, ml_quota
    monkeypatch.setattr(ml_quota, "consume", lambda cust, n=1: n)
    monkeypatch.setattr(ac, "ml_scores",
                        lambda market, items: [{"ml_score": 80, "win_prob": 0.8,
                                                "pred_return": 5.0, "pred_mfe": 7.0} for _ in items])
    _mock_card_chain(monkeypatch)
    from apiserver import routes
    items = [{"symbol": "AAPL", "date": "2026-07-01", "days_out": 21, "direction": "long"}
             for _ in range(routes._SCORE_BATCH_CAP)]
    r = client.post("/v1/score", json={"market": "2", "opportunities": items}, headers=_hdr())
    assert r.status_code == 200
    assert r.get_json()["granted"] == routes._SCORE_BATCH_CAP


# --- demo token: /v1/scan and /v1/opportunities scoped to the allowlist -------------------

def _demo_client(app, monkeypatch):
    from apiserver import auth
    demo = {"user_id": "demo", "email": "demo@tradewave.ai", "tier": "demo",
            "entitlements": tiers.tier_for("demo")}
    monkeypatch.setattr(auth, "resolve_customer", lambda key: dict(demo))
    monkeypatch.setattr(auth, "check_rate_limit", lambda cust: (True, {}))
    monkeypatch.setattr(auth, "record_usage", lambda *a, **k: None)
    from apiserver import ml_quota
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: None)
    monkeypatch.setattr(ml_quota, "consume", lambda cust, n=1: 0)
    monkeypatch.setattr(ml_quota, "refund", lambda cust, n=1: None)
    return app.test_client()


def test_demo_scan_returns_only_allowlist_symbols(app, monkeypatch):
    # a mix of allowlisted (AAPL) and non-allowlisted (GOOG) rows on market 2 (demo's only
    # in-scope market) - the demo response must contain ONLY the allowlist symbol, and
    # evaluated_count must honestly reflect the filtered (not full-market) universe.
    rows = [_opp(symbol="AAPL"), _opp(symbol="GOOG"), _opp(symbol="TSLA", entry="2026-07-02")]
    _mock_card_chain(monkeypatch, multi=rows)
    demo_client = _demo_client(app, monkeypatch)
    r = demo_client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    symbols_seen = {o["symbol"] for o in body["opportunities"]}
    assert symbols_seen <= {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}
    assert "GOOG" not in symbols_seen
    assert body["evaluated_count"] == 2                    # AAPL + TSLA only, not GOOG


def test_demo_scan_all_non_allowlist_is_honestly_empty(app, monkeypatch):
    rows = [_opp(symbol="GOOG"), _opp(symbol="META", entry="2026-07-02")]
    _mock_card_chain(monkeypatch, multi=rows)
    demo_client = _demo_client(app, monkeypatch)
    r = demo_client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    body = r.get_json()
    assert body["evaluated_count"] == 0
    assert body["opportunities"] == []


def test_real_key_scan_unaffected_by_demo_scoping(client, monkeypatch):
    # a paying key (the default `client` fixture, tier=dev) must see every row - the demo
    # allowlist filter must be a true no-op for a non-demo entitlement.
    rows = [_opp(symbol="AAPL"), _opp(symbol="GOOG"), _opp(symbol="META", entry="2026-07-02")]
    _mock_card_chain(monkeypatch, multi=rows)
    r = client.get(f"/v1/scan?{_WIN}&markets=2", headers=_hdr())
    body = r.get_json()
    symbols_seen = {o["symbol"] for o in body["opportunities"]}
    assert symbols_seen == {"AAPL", "GOOG", "META"}
    assert body["evaluated_count"] == 3


def test_demo_opportunities_scoped_to_allowlist(app, monkeypatch):
    # /v1/opportunities is a single-market enumeration route with the same bulk-exposure
    # shape as /v1/scan (audit 2026-07-10 sweep finding) - it must get the same scoping.
    from apiserver import appserver_client as ac
    rows = [_opp(symbol="AAPL"), _opp(symbol="GOOG")]
    monkeypatch.setattr(ac, "market_name_map", lambda: {"2": "S&P 500 STOCKS"})
    monkeypatch.setattr(ac, "opportunities", lambda *a, **k: list(rows))
    monkeypatch.setattr(ac, "_win_rate_for_opp", lambda o: 0.9)
    demo_client = _demo_client(app, monkeypatch)
    r = demo_client.get("/v1/opportunities?market=2", headers=_hdr())
    assert r.status_code == 200
    body = r.get_json()
    symbols_seen = {o["symbol"] for o in body["opportunities"]}
    assert symbols_seen == {"AAPL"}
    assert body["evaluated_count"] == 1


def test_real_key_opportunities_unaffected_by_demo_scoping(client, monkeypatch):
    from apiserver import appserver_client as ac
    rows = [_opp(symbol="AAPL"), _opp(symbol="GOOG")]
    monkeypatch.setattr(ac, "market_name_map", lambda: {"2": "S&P 500 STOCKS"})
    monkeypatch.setattr(ac, "opportunities", lambda *a, **k: list(rows))
    monkeypatch.setattr(ac, "_win_rate_for_opp", lambda o: 0.9)
    r = client.get("/v1/opportunities?market=2", headers=_hdr())
    body = r.get_json()
    symbols_seen = {o["symbol"] for o in body["opportunities"]}
    assert symbols_seen == {"AAPL", "GOOG"}


# --- tier rank MAX(explicit, bundled) at the resolution layer -----------------------------

def test_strategist_with_explicit_dev_sub_resolves_pro():
    # the exact defect the spec fixes: bundled-pro must not be demoted by a lower explicit sub.
    assert tiers.api_tier_from_user({"tier": "strategist", "api_tier": "dev"}) == "pro"


def test_explorer_with_explicit_dev_sub_resolves_dev():
    assert tiers.api_tier_from_user({"tier": "explorer", "api_tier": "dev"}) == "dev"
