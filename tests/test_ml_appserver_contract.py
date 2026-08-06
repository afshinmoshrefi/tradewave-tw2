"""Authenticated route contracts for bounded, single-flight ML scoring."""

from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time
from zoneinfo import ZoneInfo

import jwt


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))

import appserver as appserver_module  # noqa: E402


METADATA = {
    "model_release": "v3-route-test",
    "feature_schema_version": "v3-62",
    "feature_schema_hash": "features-route-test",
    "context_schema_version": "context-route-test",
    "pattern_profile_schema_version": "profile-route-test",
    "model_manifest_hash": "models-route-test",
    "data_as_of": "2026-08-05",
    "data_generation_hash": "generation-route-test",
    "data_source_manifest_hash": "sources-route-test",
    "context_data_complete": "True",
}


class _Pipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return queue

    def execute(self):
        results = []
        for name, args, kwargs in self.calls:
            results.append(getattr(self.redis, name)(*args, **kwargs))
        return results


class _Lock:
    def __init__(self, redis, key):
        self.redis = redis
        self.key = key
        self.owned = False

    def acquire(self, blocking=True):
        del blocking
        with self.redis.guard:
            if self.key in self.redis.locks:
                return False
            self.redis.locks.add(self.key)
            self.owned = True
            return True

    def release(self):
        with self.redis.guard:
            if not self.owned:
                raise RuntimeError("lock is not owned")
            self.redis.locks.remove(self.key)
            self.owned = False


class _Redis:
    def __init__(self):
        self.data = {}
        self.locks = set()
        self.guard = threading.Lock()

    def get(self, key):
        with self.guard:
            return self.data.get(key)

    def set(self, key, value, ex=None):
        del ex
        with self.guard:
            self.data[key] = value.encode() if isinstance(value, str) else value
        return True

    def pipeline(self, transaction=True):
        assert transaction is True
        return _Pipeline(self)

    def lock(self, key, timeout=None, blocking_timeout=None):
        del timeout, blocking_timeout
        return _Lock(self, key)


class _MetadataService:
    def scorer_metadata(self):
        return dict(METADATA)

    def cached_bundle(self, plan):
        del plan
        return None


class _ComparisonService(_MetadataService):
    def score_bundles(self, plans, max_request_items):
        assert max_request_items >= sum(len(plan["requests"]) for plan in plans)
        return {
            plan["ui_key"]: {
                "status": "available",
                "basis": "recalculated_checkpoints",
                "horizons": [
                    {
                        "status": "available",
                        "calendar_days": item["calendar_days"],
                        "daysOut": item["calendar_days"] - 1,
                        "ml_score": float(item["calendar_days"]),
                        "win_prob": 0.6,
                        "pred_return": 2.0,
                        "pred_mfe": 4.0,
                    }
                    for item in plan["requests"]
                ],
                "scorer": METADATA,
            }
            for plan in plans
        }


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _token():
    return jwt.encode(
        {
            "user": "route-test-user",
            "user_level": "4",
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
        },
        appserver_module.app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def _market_date():
    return dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _opportunity(symbol="AAPL", days_out=29):
    return {
        "symbol": symbol,
        "date": _market_date(),
        "daysOut": days_out,
        "direction": "l",
        "years": "20",
        "partial": {"min_winning_years": "17", "mode": "consecutive"},
    }


def _configure(monkeypatch, redis=None):
    redis = redis or _Redis()
    monkeypatch.setattr(appserver_module, "redis_client", redis)
    monkeypatch.setattr(
        appserver_module, "_ml_checkpoint_service", lambda: _MetadataService()
    )
    monkeypatch.setattr(appserver_module, "_ml_record_table_usage", lambda *a, **k: None)
    monkeypatch.setattr(appserver_module, "_ml_ttl_seconds", lambda: 300)
    return redis


def _post(path, payload):
    with appserver_module.app.test_client() as client:
        return client.post(f"{path}?token={_token()}", json=payload)


def test_request_shape_and_hard_row_ceiling_are_bounded(monkeypatch):
    _configure(monkeypatch)
    limit = appserver_module.ML_SCORE_MAX_REQUEST_ROWS

    wrong = _post("/MLScoreBatch/2", {"opportunities": {}})
    over = _post(
        "/MLScoreBatch/2",
        {"opportunities": [{}] * (limit + 1)},
    )

    assert wrong.status_code == 400
    assert wrong.get_json()["error"] == "opportunities_must_be_object_list"
    assert over.status_code == 400
    assert over.get_json() == {
        "error": "opportunities_too_large",
        "max_rows": limit,
    }
    assert appserver_module._ml_valid_request_items([{}] * limit, "pending")[1] is None


def test_500_row_collapsed_table_is_accepted(monkeypatch):
    _configure(monkeypatch)
    opportunities = [
        _opportunity(f"T{index}", 29) for index in range(500)
    ]

    response = _post("/MLScoreBatch/2", {"opportunities": opportunities})

    assert response.status_code == 200
    assert len(response.get_json()["pending"]) == 500


def test_duration_boundaries_and_malformed_rows_are_explicit(monkeypatch):
    _configure(monkeypatch)
    opportunities = [
        _opportunity("RAW8", 8),
        _opportunity("RAW9", 9),
        _opportunity("RAW89", 89),
        _opportunity("RAW90", 90),
        _opportunity("RAW366", 366),
        _opportunity("RAW367", 367),
        {"symbol": "BAD", "date": "not-a-date", "daysOut": 29, "direction": "l"},
    ]

    body = _post("/MLScoreBatch/2", {"opportunities": opportunities}).get_json()

    assert {item["symbol"] for item in body["pending"]} == {
        "RAW9", "RAW89", "RAW90", "RAW366"
    }
    assert body["scores"][f"RAW8|8|l"]["error"]["code"] == "unsupported_duration"
    assert body["scores"][
        f"RAW367|{_market_date()}|367|l"
    ]["horizons"][0]["error"]["code"] == "unsupported_duration"
    assert body["validation_errors"] == [{
        "index": 6,
        "code": "invalid_date",
        "message": "Entry date must use YYYY-MM-DD.",
    }]


def test_85_day_row_keeps_current_score_and_adds_only_30_60_comparisons(monkeypatch):
    redis = _configure(monkeypatch)
    service = _ComparisonService()
    monkeypatch.setattr(appserver_module, "_ml_checkpoint_service", lambda: service)
    opportunity = _opportunity("AAPL", 84)

    initial = _post(
        "/MLScoreBatch/2", {"opportunities": [opportunity]}
    ).get_json()
    key = f"AAPL|{_market_date()}|84|l"
    assert [item["calendar_days"] for item in initial["scores"][key]["horizons"]] == [30, 60, 85]
    assert initial["scores"][key]["display_horizon_days"] == 85
    assert initial["scores"][key]["display_status"] == "loading"
    assert len(initial["pending"]) == 1
    assert initial["pending"][0]["symbol"] == "AAPL"
    assert initial["pending"][0]["mode"] == "consecutive"

    def exact_provider(url, json, timeout):
        assert url.endswith("/score")
        assert json["tier"] == "61_90"
        assert timeout == 30
        item = json["opportunities"][0]
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 74,
                "win_prob": 0.68,
                "pred_return": 2.4,
                "pred_mfe": 5.2,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", exact_provider)
    final = _post(
        "/MLScorePending/2", {"pending": initial["pending"]}
    ).get_json()
    bundle = final["scores"][key]

    assert final["still_pending"] == []
    assert bundle["basis"] == "duration_comparison"
    assert bundle["display_horizon_days"] == 85
    assert bundle["ml_score"] == 74.0
    assert [item["calendar_days"] for item in bundle["horizons"]] == [30, 60, 85]
    assert bundle["horizons"][-1]["is_current"] is True
    assert f"AAPL|84|l" in final["scores"]
    assert redis.locks == set()


def test_pending_matches_reordered_results_and_requeues_missing_identity(monkeypatch):
    _configure(monkeypatch)
    opportunities = [_opportunity("AAPL"), _opportunity("MSFT")]

    def reordered(url, json, timeout):
        del url, timeout
        return _Response({
            "metadata": METADATA,
            "results": [
                {
                    **item,
                    "ml_score": 70,
                    "win_prob": 0.7,
                    "pred_return": 2,
                    "pred_mfe": 4,
                }
                for item in reversed(json["opportunities"])
            ],
        })

    monkeypatch.setattr(appserver_module.requests, "post", reordered)
    body = _post("/MLScorePending/2", {"pending": opportunities}).get_json()
    assert body["still_pending"] == []
    assert body["scores"][f"AAPL|{_market_date()}|29|l"]["ml_score"] == 70.0
    assert body["scores"][f"MSFT|{_market_date()}|29|l"]["ml_score"] == 70.0

    _configure(monkeypatch)

    def missing(url, json, timeout):
        del url, timeout
        item = json["opportunities"][0]
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 70,
                "win_prob": 0.7,
                "pred_return": 2,
                "pred_mfe": 4,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", missing)
    body = _post("/MLScorePending/2", {"pending": opportunities}).get_json()
    assert [item["symbol"] for item in body["still_pending"]] == ["MSFT"]


def test_exact_score_cold_miss_is_single_flight_between_workers(monkeypatch):
    redis = _configure(monkeypatch)
    opportunity = _opportunity("AAPL")
    provider_calls = 0
    provider_guard = threading.Lock()

    def delayed_provider(url, json, timeout):
        nonlocal provider_calls
        del url, timeout
        with provider_guard:
            provider_calls += 1
        time.sleep(0.2)
        item = json["opportunities"][0]
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 71,
                "win_prob": 0.71,
                "pred_return": 2.1,
                "pred_mfe": 4.2,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", delayed_provider)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(
            lambda _: _post("/MLScorePending/2", {"pending": [opportunity]}),
            range(2),
        ))

    assert redis.locks == set()
    assert provider_calls == 1
    assert all(response.status_code == 200 for response in responses)
    assert all(response.get_json()["still_pending"] == [] for response in responses)


def test_tara_and_table_share_the_same_exact_score_single_flight(monkeypatch):
    redis = _configure(monkeypatch)
    opportunity = _opportunity("AAPL")
    wave = {
        "market": "2",
        "symbol": "AAPL",
        "start_date": opportunity["date"],
        "days_out": "30",
        "direction": "long",
    }
    provider_calls = 0
    provider_guard = threading.Lock()

    def delayed_provider(url, json, timeout):
        nonlocal provider_calls
        del url, timeout
        with provider_guard:
            provider_calls += 1
        time.sleep(0.2)
        item = json["opportunities"][0]
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 72,
                "win_prob": 0.72,
                "pred_return": 2.2,
                "pred_mfe": 4.3,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", delayed_provider)
    with ThreadPoolExecutor(max_workers=2) as executor:
        table_future = executor.submit(
            _post, "/MLScorePending/2", {"pending": [opportunity]}
        )
        tara_future = executor.submit(
            appserver_module._tara_ai_analysis_context,
            wave,
            _token(),
        )
        table_response = table_future.result()
        tara_context = tara_future.result()

    assert redis.locks == set()
    assert provider_calls == 1
    assert table_response.get_json()["still_pending"] == []
    assert tara_context["status"] == "available"
    assert tara_context["horizons"][0]["ai_score"] == 72.0
