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
    monkeypatch.setattr(ac.requests, "request",
                        lambda m, u, **k: (calls.append(u) or seq.pop(0)))
    assert ac._request("GET", "http://x/path") == {"ok": True}
    assert len(calls) == 2


def test_429_exhausted_raises_with_scrubbed_message(monkeypatch):
    monkeypatch.setattr(ac.requests, "request", lambda m, u, **k: _Resp(429))
    with pytest.raises(requests.HTTPError) as ei:
        ac._request("GET", "http://x/path?token=eyJaaa.bbbb.cccc")
    msg = str(ei.value)
    assert "token=***" in msg
    assert ".bbbb.cccc" not in msg          # never the full JWT, prefix only


def test_non_429_errors_fail_fast_no_retry(monkeypatch):
    calls = {"n": 0}

    def _one(m, u, **k):
        calls["n"] += 1
        return _Resp(500)

    monkeypatch.setattr(ac.requests, "request", _one)
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/path")
    assert calls["n"] == 1


def test_retry_after_is_honored_and_bounded(monkeypatch):
    slept = []
    monkeypatch.setattr(ac.time, "sleep", lambda s: slept.append(s))
    seq = [_Resp(429, headers={"Retry-After": "2"}),
           _Resp(429, headers={"Retry-After": "3600"}),   # bounded, never an hour
           _Resp(200, {"ok": 1})]
    monkeypatch.setattr(ac.requests, "request", lambda m, u, **k: seq.pop(0))
    assert ac._request("GET", "http://x/p") == {"ok": 1}
    assert slept[0] == 2.0
    assert slept[1] == ac._RETRY_MAX_SLEEP


def test_storm_breaker_suppresses_retries_then_recovers(monkeypatch):
    calls = {"n": 0}

    def _always_429(m, u, **k):
        calls["n"] += 1
        return _Resp(429)

    monkeypatch.setattr(ac.requests, "request", _always_429)
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/a")        # exhausts retries, trips the breaker
    burst = calls["n"]
    assert burst == ac._RETRY_ATTEMPTS
    with pytest.raises(requests.HTTPError):
        ac._request("GET", "http://x/b")        # breaker active -> single attempt
    assert calls["n"] == burst + 1
    # a healthy response resets the breaker
    monkeypatch.setattr(ac, "_rl_state", {"until": 0.0})
    monkeypatch.setattr(ac.requests, "request", lambda m, u, **k: _Resp(200, {"ok": 1}))
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


# --- log scrub ---------------------------------------------------------------------

def test_scrub_hides_jwt_token_param_and_service_key(monkeypatch):
    monkeypatch.setattr(ac.settings, "SERVICE_API_KEY", "sk_supersecret_key")
    s = ac._scrub("GET http://x/login/api/sk_supersecret_key?token=eyJabc.defg.hijk failed")
    assert "sk_supersecret_key" not in s
    assert ".defg.hijk" not in s
    assert "token=***" in s
