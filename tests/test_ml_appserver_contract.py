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

V2_METADATA = {
    "scorer_mode": "v2",
    "model_release": "v2-legacy-59",
    "feature_schema_version": "v2-59",
    "feature_schema_hash": "v2-features-route-test",
    "context_schema_version": "not-supported",
    "pattern_profile_schema_version": "not-reported",
    "model_manifest_hash": "v2-model-route-test",
    "data_as_of": "2026-08-05",
    "data_generation_hash": "v2-generation-route-test",
    "data_source_manifest_hash": "v2-sources-route-test",
    "context_data_complete": "False",
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


class _V2MetadataService:
    def legacy_scorer_metadata(self):
        return dict(V2_METADATA)


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


def test_wave_viewer_batch_skips_only_table_popularity_telemetry(monkeypatch):
    _configure(monkeypatch)
    recorded = []
    monkeypatch.setattr(
        appserver_module,
        "_ml_record_table_usage",
        lambda resource, body: recorded.append((resource, body)),
    )

    viewer_body = {
        "request_origin": "wave_viewer",
        "opportunities": [_opportunity("VIEWER", 149)],
    }
    table_body = {"opportunities": [_opportunity("TABLE", 29)]}

    assert _post("/MLScoreBatch/2", viewer_body).status_code == 200
    assert recorded == []
    assert _post("/MLScoreBatch/2", table_body).status_code == 200
    assert recorded == [("2", table_body)]


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
        _opportunity("RAW0", 0),
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
        "RAW0", "RAW8", "RAW9", "RAW89", "RAW90", "RAW366"
    }
    assert body["scores"][
        f"RAW367|{_market_date()}|367|l"
    ]["horizons"][0]["error"]["code"] == "unsupported_duration"
    assert body["validation_errors"] == [{
        "index": 7,
        "code": "invalid_date",
        "message": "Entry date must use YYYY-MM-DD.",
    }]


def test_duration_parser_rejects_boolean_fractional_and_nonfinite_offsets():
    valid = {
        "symbol": "AAPL",
        "date": _market_date(),
        "direction": "l",
    }

    for raw in (False, True, 0.5, "0.5", float("nan"), float("inf")):
        normalized, code, _message = appserver_module._ml_normalize_opportunity(
            {**valid, "daysOut": raw}
        )
        assert normalized is None
        assert code == "invalid_duration"

    for raw in (0, 8, 9, 366):
        normalized, code, message = appserver_module._ml_normalize_opportunity(
            {**valid, "daysOut": raw}
        )
        assert normalized["daysOut"] == raw
        assert code is None
        assert message is None

    for raw in (-1, 367):
        normalized, code, _message = appserver_module._ml_normalize_opportunity(
            {**valid, "daysOut": raw}
        )
        assert normalized["daysOut"] == raw
        assert code == "unsupported_duration"


def test_short_sources_share_one_ten_day_provider_score_and_keep_source_keys(monkeypatch):
    redis = _configure(monkeypatch)
    opportunities = [
        _opportunity("AAPL", 0),
        _opportunity("AAPL", 8),
        _opportunity("AAPL", 9),
    ]
    provider_requests = []

    def provider(url, json, timeout):
        assert url.endswith("/score")
        assert json["tier"] == "10_30"
        assert timeout == 30
        provider_requests.extend(json["opportunities"])
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 73,
                "win_prob": 0.69,
                "pred_return": 2.5,
                "pred_mfe": 4.9,
            } for item in json["opportunities"]],
        })

    monkeypatch.setattr(appserver_module.requests, "post", provider)
    body = _post("/MLScorePending/2", {"pending": opportunities}).get_json()

    assert provider_requests == [{
        "symbol": "AAPL",
        "date": _market_date(),
        "daysOut": 9,
        "direction": "l",
    }]
    assert body["still_pending"] == []
    for raw_days, full_days in ((0, 1), (8, 9)):
        bundle = body["scores"][
            f"AAPL|{_market_date()}|{raw_days}|l"
        ]
        assert bundle["basis"] == "minimum_horizon"
        assert bundle["full_pattern_calendar_days"] == full_days
        assert bundle["display_horizon_days"] == 10
        assert bundle["horizons"][0]["daysOut"] == 9
        assert bundle["ml_score"] == 73.0
    assert body["scores"][f"AAPL|{_market_date()}|9|l"] == {
        "status": "available",
        "ml_score": 73.0,
        "win_prob": 0.69,
        "pred_return": 2.5,
        "pred_mfe": 4.9,
    }
    assert redis.locks == set()


def test_v2_metadata_free_score_response_resolves_without_context_calls(monkeypatch):
    redis = _configure(monkeypatch)
    monkeypatch.setattr(
        appserver_module, "_ml_checkpoint_service", lambda: _V2MetadataService()
    )
    opportunity = _opportunity("AAPL", 44)

    initial = _post(
        "/MLScoreBatch/2", {"opportunities": [opportunity]}
    ).get_json()
    assert initial["scores"] == {}
    assert initial["pending"] == [{
        "symbol": "AAPL",
        "date": _market_date(),
        "daysOut": 44,
        "direction": "l",
    }]

    def provider(url, json, timeout):
        assert url.endswith("/score")
        assert json["tier"] == "31_60"
        assert timeout == 30
        return _Response({
            "results": [{
                **json["opportunities"][0],
                "ml_score": 81,
                "win_prob": 0.77,
                "pred_return": 3.1,
                "pred_mfe": 5.4,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", provider)
    final = _post(
        "/MLScorePending/2", {"pending": initial["pending"]}
    ).get_json()

    key = f"AAPL|{_market_date()}|44|l"
    assert final["still_pending"] == []
    assert final["scores"][key] == {
        "status": "available",
        "ml_score": 81.0,
        "win_prob": 0.77,
        "pred_return": 3.1,
        "pred_mfe": 5.4,
    }
    assert redis.locks == set()


def test_v2_long_pattern_returns_30_60_90_checkpoint_scores(monkeypatch):
    redis = _configure(monkeypatch)
    monkeypatch.setattr(
        appserver_module, "_ml_checkpoint_service", lambda: _V2MetadataService()
    )
    opportunity = _opportunity("AAPL", 180)

    initial = _post(
        "/MLScoreBatch/2", {"opportunities": [opportunity]}
    ).get_json()
    assert initial["scores"] == {}
    assert initial["pending"] == [opportunity]

    requested_days = []

    def provider(url, json, timeout):
        assert url.endswith("/score")
        assert timeout == 30
        item = json["opportunities"][0]
        requested_days.append(item["daysOut"])
        return _Response({
            "results": [{
                **item,
                "ml_score": 60 + item["daysOut"] / 10,
                "win_prob": 0.60 + item["daysOut"] / 1000,
                "pred_return": 1 + item["daysOut"] / 100,
                "pred_mfe": 2 + item["daysOut"] / 100,
            }],
        })

    monkeypatch.setattr(appserver_module.requests, "post", provider)
    final = _post(
        "/MLScorePending/2", {"pending": initial["pending"]}
    ).get_json()

    key = f"AAPL|{_market_date()}|180|l"
    bundle = final["scores"][key]
    assert final["still_pending"] == []
    assert sorted(requested_days) == [29, 59, 89]
    assert bundle["basis"] == "duration_comparison"
    assert bundle["full_pattern_calendar_days"] == 181
    assert bundle["display_horizon_days"] == 90
    assert [item["calendar_days"] for item in bundle["horizons"]] == [30, 60, 90]
    assert [item["status"] for item in bundle["horizons"]] == [
        "available", "available", "available"
    ]
    assert bundle["ml_score"] == 68.9
    assert redis.locks == set()


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


def test_pending_cache_recheck_failure_requeues_row_and_releases_lock(monkeypatch):
    class FailSecondGetRedis(_Redis):
        def __init__(self):
            super().__init__()
            self.get_calls = 0

        def get(self, key):
            self.get_calls += 1
            if self.get_calls == 2:
                raise RuntimeError("simulated cache recheck failure")
            return super().get(key)

    redis = _configure(monkeypatch, FailSecondGetRedis())
    opportunity = _opportunity("AAPL", 8)

    body = _post(
        "/MLScorePending/2", {"pending": [opportunity]}
    ).get_json()

    assert body["scores"] == {}
    assert body["still_pending"] == [opportunity]
    assert redis.locks == set()


def test_pending_lock_setup_failure_does_not_drop_current_or_later_rows(monkeypatch):
    class FailSecondLockRedis(_Redis):
        def __init__(self):
            super().__init__()
            self.lock_calls = 0

        def lock(self, key, timeout=None, blocking_timeout=None):
            self.lock_calls += 1
            if self.lock_calls == 2:
                raise RuntimeError("simulated second lock failure")
            return super().lock(key, timeout=timeout, blocking_timeout=blocking_timeout)

    redis = _configure(monkeypatch, FailSecondLockRedis())
    opportunities = [_opportunity("AAPL", 8), _opportunity("MSFT", 8)]

    body = _post(
        "/MLScorePending/2", {"pending": opportunities}
    ).get_json()

    assert body["scores"] == {}
    assert {item["symbol"] for item in body["still_pending"]} == {"AAPL", "MSFT"}
    assert redis.locks == set()


def test_pending_partial_cache_write_never_scores_and_requeues_same_identity(monkeypatch):
    redis = _configure(monkeypatch)
    opportunities = [_opportunity("AAPL", 29), _opportunity("MSFT", 29)]

    def provider(url, json, timeout):
        del url, timeout
        return _Response({
            "metadata": METADATA,
            "results": [{
                **item,
                "ml_score": 70,
                "win_prob": 0.7,
                "pred_return": 2,
                "pred_mfe": 4,
            } for item in json["opportunities"]],
        })

    original_write = appserver_module.write_cached_legacy_score

    def selective_write(redis_client, symbol, *args, **kwargs):
        if symbol == "MSFT":
            raise RuntimeError("simulated second cache write failure")
        return original_write(redis_client, symbol, *args, **kwargs)

    monkeypatch.setattr(appserver_module.requests, "post", provider)
    monkeypatch.setattr(appserver_module, "write_cached_legacy_score", selective_write)
    body = _post(
        "/MLScorePending/2", {"pending": opportunities}
    ).get_json()

    assert body["scores"][f"AAPL|{_market_date()}|29|l"]["ml_score"] == 70.0
    assert f"MSFT|{_market_date()}|29|l" not in body["scores"]
    assert [item["symbol"] for item in body["still_pending"]] == ["MSFT"]
    assert redis.locks == set()


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


def test_tara_cache_recheck_failure_releases_exact_score_lock(monkeypatch):
    class FailSecondGetRedis(_Redis):
        def __init__(self):
            super().__init__()
            self.get_calls = 0

        def get(self, key):
            self.get_calls += 1
            if self.get_calls == 2:
                raise RuntimeError("simulated Tara cache recheck failure")
            return super().get(key)

    redis = _configure(monkeypatch, FailSecondGetRedis())
    opportunity = _opportunity("AAPL", 29)
    wave = {
        "market": "2",
        "symbol": "AAPL",
        "start_date": opportunity["date"],
        "days_out": "30",
        "direction": "long",
    }

    context = appserver_module._tara_ai_analysis_context(
        wave, _token()
    )

    assert context["status"] == "unavailable"
    assert redis.locks == set()
