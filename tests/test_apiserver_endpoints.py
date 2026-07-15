"""Gateway endpoint wiring (apiserver routes) - the integration layer over the unit-tested
functions. Auth + redis + the appserver are mocked, so these exercise ONLY the route plumbing:
the educational-only disclaimer on every pattern-bearing response, the per-market band 400, the
~90% default, and the view param. Runs under /home/flask/venv (has flask+pytest+apiserver).
"""
from datetime import datetime, timedelta, timezone
import re

import pytest

from apiserver import tiers

pytestmark = pytest.mark.unit  # no real external state - auth, redis, and the appserver are all mocked

_ENT = tiers.tier_for("dev")
_CUSTOMER = {"user_id": "test-user", "email": "t@example.com", "tier": "dev", "entitlements": _ENT}


@pytest.fixture(autouse=True)
def _stable_gateway_hmac_secret(monkeypatch):
    """Gateway identity tests must never depend on a workstation/VM secret file."""
    from apiserver import settings

    monkeypatch.setattr(settings, "API_KEY_HMAC_SECRET", "unit-test-hmac-secret")


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


def _mcp_service_customer():
    return {
        "user_id": "mcp-service-user",
        "email": "mcp-service@internal.tradewave",
        "tier": "mcp",
        "entitlements": tiers.tier_for("mcp"),
    }


@pytest.mark.parametrize(
    ("principal", "message"),
    [
        (None, "missing principal"),
        ("contains spaces", "invalid principal"),
        ("user_" + "x" * 124, "invalid principal"),
    ],
)
def test_mcp_service_delegation_fails_closed_without_valid_principal(
    app, monkeypatch, principal, message
):
    from apiserver import auth

    monkeypatch.setattr(
        auth.db,
        "get_user_by_workos_id",
        lambda _sub: pytest.fail("invalid principals must not reach the database"),
    )
    headers = {} if principal is None else {"X-TW-Principal-WorkOS": principal}
    with app.test_request_context("/v1/me", headers=headers):
        response, status = auth._apply_on_behalf(_mcp_service_customer())
    assert status == 401
    assert response.get_json()["error"]["message"] == message


def test_mcp_service_delegation_rejects_unknown_workos_user(app, monkeypatch):
    from apiserver import auth

    monkeypatch.setattr(auth.db, "get_user_by_workos_id", lambda _sub: None)
    with app.test_request_context(
        "/v1/me", headers={"X-TW-Principal-WorkOS": "user_01KNOWN_SHAPE"}
    ):
        response, status = auth._apply_on_behalf(_mcp_service_customer())
    assert status == 401
    assert response.get_json()["error"]["message"] == "unknown user"


def test_normal_customer_cannot_activate_workos_delegation(app, monkeypatch):
    from apiserver import auth

    monkeypatch.setattr(
        auth.db,
        "get_user_by_workos_id",
        lambda _sub: pytest.fail("a normal customer header must be ignored"),
    )
    customer = dict(_CUSTOMER)
    with app.test_request_context(
        "/v1/me", headers={"X-TW-Principal-WorkOS": "user_attacker"}
    ):
        assert auth._apply_on_behalf(customer) is None
    assert customer == _CUSTOMER


def test_mcp_delegation_precedes_per_user_rate_limit_and_metering(
    app, monkeypatch
):
    from apiserver import appserver_client, auth

    service = _mcp_service_customer()
    resolved = {
        "user_id": "real-user-42",
        "email": "researcher@example.com",
        "tier": "analyst",
        "api_tier": None,
        "roles": [],
        "reverse_trial_ends_at": None,
        "navigator_mcp_first_connect_at": None,
    }
    delegated_entitlements = dict(tiers.mcp_tier_for("analyst"))
    observed = {}
    monkeypatch.setattr(auth, "resolve_customer", lambda _key: dict(service))
    monkeypatch.setattr(auth.db, "get_user_by_workos_id", lambda _sub: dict(resolved))

    def check_rate_limit(customer):
        observed["rate"] = dict(customer)
        return True, {}

    def record_usage(customer, path):
        observed["usage"] = (dict(customer), path)

    monkeypatch.setattr(auth, "check_rate_limit", check_rate_limit)
    monkeypatch.setattr(auth, "record_usage", record_usage)
    monkeypatch.setattr(appserver_client, "list_markets", lambda: [])
    response = app.test_client().get(
        "/v1/markets",
        headers={
            "Authorization": "Bearer tw_svc_test",
            "X-TW-Principal-WorkOS": "user_01REAL",
        },
    )
    assert response.status_code == 200
    assert observed["rate"]["user_id"] == "real-user-42"
    assert observed["rate"]["email"] == "researcher@example.com"
    assert observed["rate"]["tier"] == "analyst"
    assert observed["rate"]["entitlements"] == delegated_entitlements
    assert observed["usage"][0]["user_id"] == "real-user-42"
    assert observed["usage"][1] == "/v1/markets"


@pytest.mark.parametrize(
    (
        "raw_tier",
        "reverse_days",
        "navigator_days",
        "roles",
        "api_tier",
        "expected_tier",
        "expected_markets",
        "expected_ml",
        "expected_rate",
        "expected_opp_limit",
        "expected_teaser",
    ),
    [
        ("explorer", None, None, [], None, "explorer", ("0",), 0, (20, 400), 10, None),
        ("explorer", 1, None, [], None, "strategist", tuple(tiers.ALL_MARKETS), None, (120, 20000), 500, "explorer_trial"),
        ("explorer", -1, None, [], None, "explorer", ("0",), 0, (20, 400), 10, None),
        ("navigator", None, -1, [], None, "analyst", ("0", "1", "2", "3", "4", "11"), 100, (60, 5000), 100, "navigator_firstconnect"),
        ("navigator", None, -8, [], None, "navigator", ("0", "1", "2"), 0, (30, 1000), 25, None),
        ("analyst", None, None, [], None, "analyst", ("0", "1", "2", "3", "4", "11"), 100, (60, 5000), 100, None),
        ("strategist", None, None, [], None, "strategist", tuple(tiers.ALL_MARKETS), None, (120, 20000), 500, None),
        ("explorer", None, None, ["staff_admin"], None, "strategist", tuple(tiers.ALL_MARKETS), None, (120, 20000), 500, None),
        # Explicit API subscriptions may widen markets/rate/volume, but steady
        # sub-Analyst web plans remain at zero in-chat ML by policy.
        ("explorer", None, None, [], "business", "explorer", tuple(tiers.ALL_MARKETS), 0, (300, 250000), 5000, None),
        ("navigator", None, -8, [], "pro", "navigator", tuple(tiers.ALL_MARKETS), 0, (120, 50000), 1000, None),
        ("analyst", None, None, [], "business", "analyst", tuple(tiers.ALL_MARKETS), None, (300, 250000), 5000, None),
    ],
    ids=[
        "steady-explorer",
        "active-explorer-reverse-trial",
        "expired-explorer-reverse-trial",
        "active-navigator-first-connect",
        "expired-navigator-first-connect",
        "steady-analyst",
        "steady-strategist",
        "role-bypass",
        "explorer-business-refloor",
        "navigator-pro-refloor",
        "analyst-business-merge",
    ],
)
def test_real_mcp_tier_resolution_matrix(
    monkeypatch,
    raw_tier,
    reverse_days,
    navigator_days,
    roles,
    api_tier,
    expected_tier,
    expected_markets,
    expected_ml,
    expected_rate,
    expected_opp_limit,
    expected_teaser,
):
    from apiserver import auth

    now = datetime.now(timezone.utc)
    reverse_end = None if reverse_days is None else now + timedelta(days=reverse_days)
    navigator_start = (
        None if navigator_days is None else now + timedelta(days=navigator_days)
    )
    # None on a non-Navigator must never arm; the matrix's Navigator cases use
    # persisted timestamps so active and expired windows are deterministic.
    monkeypatch.setattr(
        auth.db,
        "arm_navigator_teaser_if_null",
        lambda _user_id: pytest.fail("this matrix should not arm a new teaser"),
    )
    row = {
        "user_id": "tier-matrix-user",
        "email": "tier-matrix@example.com",
        "tier": raw_tier,
        "api_tier": api_tier,
        "roles": roles,
        "reverse_trial_ends_at": reverse_end,
        "navigator_mcp_first_connect_at": navigator_start,
    }

    tier_label, entitlements, teaser = auth._resolve_mcp(row)

    assert tier_label == expected_tier
    assert tuple(entitlements["markets"]) == expected_markets
    assert entitlements["ml_daily_limit"] == expected_ml
    assert (
        entitlements["rate"]["per_minute"],
        entitlements["rate"]["per_day"],
    ) == expected_rate
    assert entitlements["opp_limit"] == expected_opp_limit
    if expected_teaser is None:
        assert teaser == {
            "active": False,
            "kind": None,
            "ends_at": None,
            "post_teaser_scope": None,
        }
    else:
        assert teaser["active"] is True
        assert teaser["kind"] == expected_teaser
        assert teaser["ends_at"]
        assert teaser["post_teaser_scope"] in {"explorer", "navigator"}


def test_navigator_first_connect_is_armed_once_and_uses_returned_timestamp(monkeypatch):
    from apiserver import auth

    stamped = datetime.now(timezone.utc) - timedelta(hours=1)
    calls = []

    def arm(user_id):
        calls.append(user_id)
        return stamped

    monkeypatch.setattr(auth.db, "arm_navigator_teaser_if_null", arm)
    row = {
        "user_id": "new-navigator",
        "email": "navigator@example.com",
        "tier": "navigator",
        "api_tier": None,
        "roles": [],
        "reverse_trial_ends_at": None,
        "navigator_mcp_first_connect_at": None,
    }

    tier_label, entitlements, teaser = auth._resolve_mcp(row)

    assert calls == ["new-navigator"]
    assert tier_label == "analyst"
    assert entitlements == tiers.mcp_tier_for("analyst")
    assert teaser == {
        "active": True,
        "kind": "navigator_firstconnect",
        "ends_at": (stamped + timedelta(days=7)).isoformat(),
        "post_teaser_scope": "navigator",
    }


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


def _receipt_entries(win_rate, n_entries=10):
    wins = round(win_rate * n_entries)
    return [
        {
            "year": 2015 + i,
            "pct": "4.00,6.00,-1.00" if i < wins else "-3.00,2.00,-5.00",
        }
        for i in range(n_entries)
    ]


def _opp(win_rate=0.9, symbol="AAPL", market="2", direction="long", entry="2026-07-01"):
    return {"symbol": symbol, "market": market, "direction": direction, "entry_date": entry,
            "days_out": 21, "sharpe_ratio": 1.5, "avg_profit_pct": 5.0,
            "median_profit_pct": 3.0, "win_rate": win_rate, "years": "10"}


def _mock_card_chain(monkeypatch, multi=None, by_symbol=None, curve=None, entries=None):
    from apiserver import appserver_client as ac
    monkeypatch.setattr(ac, "market_name_map",
                        lambda: {"2": "S&P 500 STOCKS", "4": "WILSHIRE 5000", "0": "DOW 30 STOCKS",
                                 "7": "FUTURES & COMMODITIES", "11": "ETFs"})
    receipt_rows = list(_ENTRIES if entries is None else entries)
    monkeypatch.setattr(ac, "chart_stats_and_years",
                        lambda *a, **k: (dict(_STATS), list(receipt_rows)))
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


def test_scan_no_signal_card_omits_order_ticket(client, monkeypatch):
    _mock_card_chain(monkeypatch, multi=[_opp(win_rate=0.30)],
                     entries=_receipt_entries(0.30))
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
    _mock_card_chain(monkeypatch, multi=[_opp(win_rate=0.30)],
                     entries=_receipt_entries(0.30))
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
    admission_id = r.get_json()["mcp_admission_id"]
    assert re.fullmatch(r"acct_[0-9a-f]{64}", admission_id)
    assert _CUSTOMER["user_id"] not in admission_id


def test_mcp_admission_id_is_stable_per_account_and_not_per_key(monkeypatch):
    from apiserver import auth

    first = auth.mcp_admission_id({"user_id": "account-42", "email": "a@example.com"})
    same = auth.mcp_admission_id({"user_id": "account-42", "email": "changed@example.com"})
    other = auth.mcp_admission_id({"user_id": "account-43", "email": "a@example.com"})
    assert first == same
    assert first != other
    assert re.fullmatch(r"acct_[0-9a-f]{64}", first)
    assert "account-42" not in first

    # The public demo has no database/HMAC key but still receives one fixed bucket.
    monkeypatch.setattr(auth.settings, "API_KEY_HMAC_SECRET", None)
    assert re.fullmatch(
        r"acct_[0-9a-f]{64}", auth.mcp_admission_id({"user_id": "demo"})
    )
    with pytest.raises(auth.AuthMisconfigured):
        auth.mcp_admission_id({"user_id": "account-42"})


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


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"symbol": 7}, "symbol must be a string"),
        ({"symbol": "   "}, "between 1 and 64"),
        ({"symbol": "A" * 65}, "between 1 and 64"),
        ({"date": 20260701}, "valid YYYY-MM-DD"),
        ({"date": "20260701"}, "valid YYYY-MM-DD"),
        ({"date": "2026-02-30"}, "valid YYYY-MM-DD"),
        ({"days_out": "21"}, "integer between 1 and 366"),
        ({"days_out": True}, "integer between 1 and 366"),
        ({"days_out": 0}, "integer between 1 and 366"),
        ({"days_out": 367}, "integer between 1 and 366"),
        ({"market": "11"}, "market must be supplied once at the top level"),
    ],
)
def test_score_enforces_frozen_item_schema_before_quota(
    client, monkeypatch, override, message
):
    from apiserver import ml_quota

    monkeypatch.setattr(
        ml_quota,
        "consume",
        lambda *_args, **_kwargs: pytest.fail("invalid score item consumed quota"),
    )
    item = {
        "symbol": "AAPL",
        "date": "2026-07-01",
        "days_out": 21,
        "direction": "long",
    }
    item.update(override)
    r = client.post(
        "/v1/score",
        json={"market": "2", "opportunities": [item]},
        headers=_hdr(),
    )
    assert r.status_code == 400
    assert message in r.get_json()["error"]["message"]


def test_score_strips_symbol_and_accepts_days_out_boundaries(client, monkeypatch):
    from apiserver import appserver_client as ac, ml_quota

    observed = []
    monkeypatch.setattr(ml_quota, "consume", lambda _customer, n=1: n)
    monkeypatch.setattr(ml_quota, "refund", lambda *_args, **_kwargs: None)

    def score_rows(_market, items):
        observed.extend(items)
        return [
            {
                "ml_score": 80,
                "win_prob": 0.8,
                "pred_return": 5.0,
                "pred_mfe": 7.0,
            }
            for _ in items
        ]

    monkeypatch.setattr(ac, "ml_scores", score_rows)
    items = [
        {"symbol": " AAPL ", "date": "2026-07-01", "days_out": days,
         "direction": "long"}
        for days in (1, 366)
    ]
    r = client.post(
        "/v1/score",
        json={"market": "2", "opportunities": items},
        headers=_hdr(),
    )
    assert r.status_code == 200
    assert [row["symbol"] for row in observed] == ["AAPL", "AAPL"]
    assert [row["days_out"] for row in observed] == [1, 366]


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
