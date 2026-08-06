"""appserver_client robustness (2026-06-12 prod-429 review): bounded 429 retries that
honor Retry-After, the storm breaker (fail-fast after an exhausted retry burst), the
failure-vs-data-gap distinction in chart_stats_and_years, timeout bounds under gunicorn's
120s, and credential scrubbing (the service JWT / api key must never reach a log line or
exception message). Hermetic - requests and time.sleep are mocked.
"""
import pytest
import requests

from apiserver import appserver_client as ac

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                "%d Error for url: http://x/ChartData4/2?token=eyJaaa.bbbb.cccc" % self.status_code,
                response=self)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _fast_and_clean(monkeypatch):
    """No real sleeping; storm breaker reset between tests."""
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)
    monkeypatch.setattr(ac, "_rl_state", {"until": 0.0})


# --- 429 retry: retryable rate-limit pressure, DISTINCT from a data gap ------------

def test_429_then_success_is_retried(monkeypatch):
    seq = [_Resp(429, headers={"Retry-After": "1"}), _Resp(200, {"ok": True})]
    calls = []
    monkeypatch.setattr(ac._http, "request",
                        lambda m, u, **k: (calls.append(u) or seq.pop(0)))
    assert ac._request("GET", "http://x/path") == {"ok": True}
    assert len(calls) == 2


def test_429_exhausted_raises_with_scrubbed_message(monkeypatch):
    monkeypatch.setattr(ac._http, "request", lambda m, u, **k: _Resp(429))
    with pytest.raises(requests.HTTPError) as ei:
        ac._request("GET", "http://x/path?token=eyJaaa.bbbb.cccc")
    msg = str(ei.value)
    assert "token=***" in msg
    assert ".bbbb.cccc" not in msg          # never the full JWT, prefix only
    assert ei.value.request is None
    assert ei.value.response is None


def test_non_429_errors_fail_fast_no_retry(monkeypatch):
    calls = {"n": 0}

    def _one(m, u, **k):
        calls["n"] += 1
        return _Resp(500)

    monkeypatch.setattr(ac._http, "request", _one)
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/path")
    assert calls["n"] == 1


def test_retry_after_is_honored_and_bounded(monkeypatch):
    slept = []
    monkeypatch.setattr(ac.time, "sleep", lambda s: slept.append(s))
    seq = [_Resp(429, headers={"Retry-After": "2"}),
           _Resp(429, headers={"Retry-After": "3600"}),   # bounded, never an hour
           _Resp(200, {"ok": 1})]
    monkeypatch.setattr(ac._http, "request", lambda m, u, **k: seq.pop(0))
    assert ac._request("GET", "http://x/p") == {"ok": 1}
    assert slept[0] == 2.0
    assert slept[1] == ac._RETRY_MAX_SLEEP


def test_storm_breaker_suppresses_retries_then_recovers(monkeypatch):
    calls = {"n": 0}

    def _always_429(m, u, **k):
        calls["n"] += 1
        return _Resp(429)

    monkeypatch.setattr(ac._http, "request", _always_429)
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/a")        # exhausts retries, trips the breaker
    burst = calls["n"]
    assert burst == ac._RETRY_ATTEMPTS
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/b")        # breaker active -> single attempt
    assert calls["n"] == burst + 1
    # a healthy response resets the breaker
    monkeypatch.setattr(ac, "_rl_state", {"until": 0.0})
    monkeypatch.setattr(ac._http, "request", lambda m, u, **k: _Resp(200, {"ok": 1}))
    assert ac._request("GET", "http://x/c") == {"ok": 1}
    assert ac._rl_state["until"] == 0.0


def test_timeouts_stay_under_gunicorn_120s():
    assert ac.GET_TIMEOUT < 120 and ac.POST_TIMEOUT < 120


# --- failure vs data gap in chart_stats_and_years ----------------------------------

def test_chart_stats_fetch_failure_returns_none_pair(monkeypatch):
    def _boom(*a, **k):
        raise requests.ConnectTimeout("timed out")
    monkeypatch.setattr(ac, "_chart_data", _boom)
    assert ac.chart_stats_and_years("2", "AAPL", "2026-07-01", 21, "10") == (None, None)


def test_chart_stats_genuine_gap_stays_empty_pair(monkeypatch):
    # a 200 'Not Enough Data' maps to ([], {}) inside _chart_data - real absence,
    # NOT the (None, None) failure sentinel.
    monkeypatch.setattr(ac, "_chart_data", lambda *a, **k: ([], {}))
    assert ac.chart_stats_and_years("2", "AAPL", "2026-07-01", 21, "10") == ({}, [])


def test_opportunity_days_are_exposed_as_inclusive_calendar_days():
    row = ["2026-08-03", "ROST", 16, "Long", 2.48, 5.2, 4.1, None, None]

    opportunity = ac._opp_row_to_obj(row, "2", "10")

    assert opportunity["days_out"] == 17


def test_chart_data_converts_display_days_to_engine_offset(monkeypatch):
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        return {"ChartData4": [], "stats": {}}

    monkeypatch.setattr(ac, "get", fake_get)

    ac._chart_data("2", "ROST", "2026-08-03", 17, "40")

    assert captured["path"] == "/ChartData4/2/2026-08-03/ROST/16/40"


def test_ml_scoring_converts_display_days_to_engine_offset(monkeypatch):
    captured = {}

    def fake_post(path, body, params=None):
        captured.update(path=path, body=body)
        return {
            "scores": {
                "ROST|16|l": {
                    "ml_score": 70,
                    "win_prob": 0.7,
                    "pred_return": 2.0,
                    "pred_mfe": 4.0,
                }
            },
            "pending": [],
        }

    monkeypatch.setattr(ac, "post", fake_post)

    result = ac.ml_scores(
        "2",
        [{"symbol": "ROST", "date": "2026-08-03", "days_out": 17, "direction": "long"}],
    )

    assert captured["body"]["opportunities"][0]["daysOut"] == 16
    assert result[0]["ml_score"] == 70


def test_ml_scoring_prefers_date_qualified_keys_for_same_duration_rows(monkeypatch):
    """A legacy alias collision must not give both entry dates the same score."""

    def fake_post(path, body, params=None):
        assert path == "/MLScoreBatch/2"
        return {
            "scores": {
                "ROST|2026-08-03|16|l": {
                    "ml_score": 71,
                    "win_prob": 0.71,
                    "pred_return": 2.1,
                    "pred_mfe": 4.1,
                },
                "ROST|2026-09-03|16|l": {
                    "ml_score": 83,
                    "win_prob": 0.83,
                    "pred_return": 3.3,
                    "pred_mfe": 5.3,
                },
                # Both dates necessarily share this rolling-deploy alias. If the
                # client reads it first, the collision recreates the old bug.
                "ROST|16|l": {
                    "ml_score": 99,
                    "win_prob": 0.99,
                    "pred_return": 9.9,
                    "pred_mfe": 9.9,
                },
            },
            "pending": [],
        }

    monkeypatch.setattr(ac, "post", fake_post)

    result = ac.ml_scores(
        "2",
        [
            {
                "symbol": "ROST",
                "date": "2026-08-03",
                "days_out": 17,
                "direction": "long",
            },
            {
                "symbol": "ROST",
                "date": "2026-09-03",
                "days_out": 17,
                "direction": "long",
            },
        ],
    )

    assert [item["ml_score"] for item in result] == [71, 83]


def test_public_scoring_keeps_long_checkpoint_contract_unsupported_and_refundable(monkeypatch):
    calls = []
    monkeypatch.setattr(ac, "post", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = ac.ml_scores(
        "2",
        [{"symbol": "AAPL", "date": "2026-08-05", "days_out": 150, "direction": "long"}],
    )

    assert result == [None]
    assert calls == []


def test_structured_unavailable_score_is_not_counted_as_api_delivery(monkeypatch):
    monkeypatch.setattr(
        ac,
        "post",
        lambda *_args, **_kwargs: {
            "scores": {
                "AAPL|2026-08-05|29|l": {
                    "status": "unavailable",
                    "ml_score": None,
                    "win_prob": None,
                    "pred_return": None,
                    "pred_mfe": None,
                    "error": {"code": "vix_blocked", "retryable": False},
                }
            },
            "pending": [],
        },
    )

    assert ac.ml_scores(
        "2",
        [{"symbol": "AAPL", "date": "2026-08-05", "days_out": 30, "direction": "long"}],
    ) == [None]


def test_stored_daily_pick_offset_is_exposed_as_inclusive_days(monkeypatch):
    stored = {
        "symbol": "ROST",
        "resource_id": 2,
        "date": "2026-08-03",
        "featured_date": "2026-08-01",
        "direction": "l",
        "daysOut": 16,
        "years": "10",
    }
    monkeypatch.setattr(ac, "_load_featured_history", lambda: [stored])

    assert ac.daily_pick()["days_out"] == 17
    assert ac.daily_pick_raw()["opp"]["days_out"] == 17


def test_seasonal_curve_gateway_cache_avoids_second_http_call(monkeypatch):
    class MemoryCache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def setex(self, key, _ttl, value):
            self.values[key] = value

    cache = MemoryCache()
    calls = {"count": 0}

    def fake_get(*_args, **_kwargs):
        calls["count"] += 1
        return {"cons_seas_chart": [["07-01", 41.5], ["07-02", 43.0]]}

    monkeypatch.setattr(ac, "_curve_cache", cache)
    monkeypatch.setattr(ac, "get", fake_get)
    first = ac._seasonal_curve("2", "AAPL", "2026-07-01", "10")
    second = ac._seasonal_curve("2", "AAPL", "2026-07-01", "10")
    assert first == second
    assert calls["count"] == 1


def test_opportunities_multi_reports_partial_failures_when_requested(monkeypatch):
    def one_market(market, *_args, **_kwargs):
        if market == "4":
            raise requests.ConnectTimeout("market unavailable")
        return [{"market": market, "symbol": "AAPL"}]

    monkeypatch.setattr(ac, "appserver_opportunities_safe", one_market)
    rows, failures = ac.opportunities_multi(
        ["2", "4"], "2026-07-01", return_failures=True
    )
    assert rows == [{"market": "2", "symbol": "AAPL"}]
    assert failures == ["4"]


def test_opportunities_multi_keeps_historical_list_contract(monkeypatch):
    monkeypatch.setattr(
        ac, "appserver_opportunities_safe",
        lambda market, *_args, **_kwargs: [{"market": market}],
    )
    assert ac.opportunities_multi(["2"], "2026-07-01") == [{"market": "2"}]


# --- log scrub ---------------------------------------------------------------------

def test_scrub_hides_jwt_token_param_and_service_key(monkeypatch):
    monkeypatch.setattr(ac.settings, "SERVICE_API_KEY", "sk_supersecret_key")
    s = ac._scrub("GET http://x/login/api/sk_supersecret_key?token=eyJabc.defg.hijk failed")
    assert "sk_supersecret_key" not in s
    assert ".defg.hijk" not in s
    assert "token=***" in s


def test_scrub_hides_unknown_legacy_login_path_and_api_key_query():
    s = ac._scrub("GET http://x/login/api/unknown-secret?api_key=also-secret failed")
    assert s == "GET http://x/login/api/***?api_key=*** failed"


def test_get_token_uses_header_not_request_target(monkeypatch):
    monkeypatch.setattr(ac.settings, "APPSERVER_URL", "http://app")
    monkeypatch.setattr(ac.settings, "SERVICE_API_KEY", "service-key")
    monkeypatch.setattr(ac, "_token", {"value": None, "exp": 0.0})
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, kwargs=kwargs)
        return {"token": "session-token"}

    monkeypatch.setattr(ac, "_request", fake_request)
    assert ac._get_token() == "session-token"
    assert captured["method"] == "POST"
    assert captured["url"] == "http://app/login/api"
    assert captured["kwargs"]["headers"] == {"X-Service-Key": "service-key"}
    assert "service-key" not in captured["url"]


def test_featured_history_missing_is_an_honest_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "FEATURED_HISTORY_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(ac.settings, "FEATURED_HISTORY_URL", "")
    with pytest.raises(ac.FeaturedHistoryUnavailable):
        ac._load_featured_history()


def test_featured_history_uses_private_remote_feed_on_split_topology(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "FEATURED_HISTORY_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(ac.settings, "FEATURED_HISTORY_URL", "http://web/internal/featured-history")
    monkeypatch.setattr(ac.settings, "SERVICE_API_KEY", "service-key")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, kwargs=kwargs)
        return [{"symbol": "AAPL"}]

    monkeypatch.setattr(ac, "_request", fake_request)
    assert ac._load_featured_history() == [{"symbol": "AAPL"}]
    assert captured["kwargs"]["headers"] == {"X-Service-Key": "service-key"}


def test_featured_history_configured_remote_precedes_existing_local(monkeypatch, tmp_path):
    local = tmp_path / "featured.json"
    local.write_text('[{"symbol":"STALE"}]', encoding="utf-8")
    monkeypatch.setattr(ac, "FEATURED_HISTORY_FILE", str(local))
    monkeypatch.setattr(ac.settings, "FEATURED_HISTORY_URL", "http://web/internal/featured-history")
    monkeypatch.setattr(ac.settings, "SERVICE_API_KEY", "service-key")
    monkeypatch.setattr(ac, "_request", lambda *_a, **_k: [{"symbol": "REMOTE"}])

    assert ac._load_featured_history() == [{"symbol": "REMOTE"}]
