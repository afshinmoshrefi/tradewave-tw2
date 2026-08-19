"""EOD ML warmer contracts: default seeds, marker gate, and atomic publication."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from data_updater import prefetch_ml_scores as prefetch
from data_updater.eod_readiness import (
    NY_TZ,
    build_status_marker,
    evaluate_eod_readiness,
    terminal_row_fingerprint,
)
from tests.test_ml_checkpoint_context import (
    FakeRedis,
    FakeResponse,
    METADATA,
    SELECTED_RECURRENCE,
)
from ml_checkpoint_context import (
    read_cached_checkpoint,
    read_cached_legacy_score,
    write_cached_checkpoint,
    write_cached_legacy_score,
)


FIXED_NOW = NY_TZ.localize(dt.datetime(2026, 8, 5, 23, 5))


@pytest.fixture(autouse=True)
def _stable_final_live_scorer(monkeypatch):
    monkeypatch.setattr(
        prefetch,
        "_live_scorer_metadata",
        lambda **_kwargs: METADATA,
    )


def _valid_status_marker():
    targets = {
        "US": [f"S{index:03d}" for index in range(100)],
        "ETF": [f"E{index:03d}" for index in range(25)],
    }
    observations = {
        f"{exchange}:{symbol}": {
            "state": "verified",
            "terminal_date": "2026-08-05",
            "terminal_row_fingerprint": terminal_row_fingerprint(
                [exchange, symbol, "2026-08-05"]
            ),
        }
        for exchange, symbols in targets.items()
        for symbol in symbols
    }
    readiness = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations=observations,
        completed_session=dt.date(2026, 8, 5),
        resource_ids=sorted(prefetch.ALLOWED_RESOURCE_IDS, key=int),
    )
    return build_status_marker(
        base={
            "started_at": "2026-08-06T03:05:00+00:00",
            "completed_at": "2026-08-06T03:06:00+00:00",
            "market_date": "2026-08-05",
            "target_table_date": "2026-08-06",
            "latest_us_date": "2026-08-05",
            "total": 125,
            "updated": 125,
            "skipped": 0,
            "missing": 0,
            "failed": 0,
            "source": "http://update-server/",
        },
        readiness=readiness,
    )


def _write_valid_status(path):
    marker = _valid_status_marker()
    path.write_text(json.dumps(marker), encoding="utf-8")
    return marker


class DefaultOppHTTP:
    def get(self, url, params, timeout):
        assert "/August/6/" in url
        assert "/-/0/0" in url
        assert params["mode"] == "consecutive"
        assert params["token"] == "test-token"
        assert params["target_date"] == "2026-08-06"
        assert timeout == 90
        return FakeResponse(
            {
                "OppList": [
                    [
                        "2026-08-06",
                        "AAPL",
                        149,
                        "Long",
                        1.2,
                        4.5,
                        4.0,
                        6.0,
                        1.1,
                    ]
                ]
            }
        )


class StrictSetRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.set_calls = []

    def set(self, key, value, *, ex=None):
        self.set_calls.append((key, value, ex))
        return super().set(key, value, ex=ex)


class RejectFinalPublicationRedis(FakeRedis):
    def pipeline(self, transaction=True):
        base = super().pipeline(transaction=transaction)
        original_execute = base.execute

        def execute():
            if any(
                name == "set" and args and args[0] == prefetch.ACTIVE_GENERATION_KEY
                for name, args, _kwargs in base.calls
            ):
                raise RuntimeError("simulated pre-EXEC failure")
            return original_execute()

        base.execute = execute
        return base


def test_staged_pipeline_accounts_for_mixed_score_and_metadata_writes():
    redis_client = FakeRedis()
    publication = prefetch._StagedCachePublication(redis_client, "mixed")
    score_key = f"{prefetch.CACHE_SCHEMA_VERSION}:legacy:value:mixed"
    metadata_key = f"{prefetch.CACHE_SCHEMA_VERSION}:scorer:metadata:mixed"
    pipeline = publication.pipeline(transaction=True)
    pipeline.set(score_key, "{}", ex=300)
    pipeline.set(metadata_key, "{}", ex=60)

    assert pipeline.execute() == [True, True]
    assert publication.staged_count == 1
    assert redis_client.get(score_key) is None
    assert publication.get(score_key) == b"{}"
    assert redis_client.get(metadata_key) == b"{}"


class LegacyScoreHTTP:
    def __init__(self):
        self.posts = []

    def post(self, url, json, timeout):
        assert url == "http://scorer/score"
        assert json["tier"] == "10_30"
        assert timeout == 60
        self.posts.append(json)
        return FakeResponse(
            {
                "metadata": METADATA,
                "results": [
                    {
                        **requested,
                        "ml_score": 81,
                        "win_prob": 0.78,
                        "pred_return": 4.2,
                        "pred_mfe": 6.7,
                    }
                    for requested in json["opportunities"]
                ]
            }
        )


class RetryableLegacyHTTP:
    def post(self, url, json, timeout):
        del url, timeout
        requested = json["opportunities"][0]
        return FakeResponse(
            {
                "metadata": METADATA,
                "results": [
                    {
                        **requested,
                        "status": "unavailable",
                        "error": {
                            "code": "provider_unavailable",
                            "message": "try again",
                            "retryable": True,
                        },
                    }
                ]
            }
        )


class FailSecondLegacyHTTP:
    def __init__(self):
        self.posts = 0

    def post(self, url, json, timeout):
        assert url == "http://scorer/score"
        assert timeout == 60
        self.posts += 1
        if self.posts == 2:
            return FakeResponse({}, status_code=503)
        requested = json["opportunities"][0]
        return FakeResponse(
            {
                "metadata": METADATA,
                "results": [
                    {
                        **requested,
                        "ml_score": 91,
                        "win_prob": 0.81,
                        "pred_return": 5.1,
                        "pred_mfe": 7.2,
                    }
                ],
            }
        )


class MissingMetadataLegacyHTTP:
    def post(self, url, json, timeout):
        del url, timeout
        requested = json["opportunities"][0]
        return FakeResponse(
            {
                "results": [
                    {
                        **requested,
                        "ml_score": 81,
                        "win_prob": 0.78,
                        "pred_return": 4.2,
                        "pred_mfe": 6.7,
                    }
                ]
            }
        )


class FailSecondCheckpointHTTP:
    def __init__(self):
        self.posts = 0

    def post(self, url, json, timeout):
        assert url == "http://scorer/score/context"
        assert timeout == 60
        self.posts += 1
        if self.posts == 2:
            return FakeResponse({}, status_code=503)
        return FakeResponse(
            {
                "metadata": METADATA,
                "results": [
                    {
                        **item,
                        "tier": (
                            "10_30"
                            if item["calendar_days"] == 30
                            else "31_60"
                            if item["calendar_days"] == 60
                            else "61_90"
                        ),
                        "ml_score": 91,
                        "win_prob": 0.81,
                        "pred_return": 5.1,
                        "pred_mfe": 7.2,
                        "pattern_recalculated": True,
                        "selected_recurrence": SELECTED_RECURRENCE,
                        "pattern_profile": {
                            "source": "dynamic_recalculation",
                            "qualifying_combo_count": 7,
                            "profile_hash": "a" * 64,
                        },
                        "context_hash": "b" * 64,
                        "feature_vector_hash": "c" * 64,
                    }
                    for item in json["opportunities"]
                ],
            }
        )


def _empty_defaults():
    defaults = []
    for resource_id in sorted(prefetch.ALLOWED_RESOURCE_IDS, key=int):
        years, partial = prefetch.DEFAULT_CONSECUTIVE_CONTEXTS[resource_id]
        defaults.append(
            prefetch._empty_seed_context(
                resource_id,
                {
                    "years": years,
                    "partial": {
                        "min_winning_years": partial,
                        "mode": "consecutive",
                    },
                    "mode": "consecutive",
                    "date": "2026-08-06",
                    "day_range": "-",
                    "is_default": True,
                },
            )
        )
    return defaults


def test_no_authoritative_marker_defers_without_publishing(tmp_path):
    redis_client = FakeRedis()
    result = prefetch.run_prefetch(
        status_file=str(tmp_path / "missing.json"),
        redis_client=redis_client,
        http_client=object(),
    )

    assert result == 0
    assert redis_client.get(prefetch.ACTIVE_GENERATION_KEY) is None


def test_default_us_stock_etf_contexts_are_seeded_before_usage(monkeypatch):
    monkeypatch.setattr(prefetch, "_prefetch_token", lambda: "test-token")
    contexts, failures = prefetch.fetch_default_contexts(
        status={
            "market_date": "2026-08-05",
            "target_table_date": "2026-08-06",
            "latest_us_date": "2026-08-05",
        },
        http_client=DefaultOppHTTP(),
        appserver_url="http://127.0.0.1:5000",
    )

    assert failures == []
    assert {item["resource_id"] for item in contexts} == {
        "0",
        "1",
        "2",
        "3",
        "4",
        "11",
    }
    assert all(item["is_default"] is True for item in contexts)
    assert all(item["seeded"] is True for item in contexts)
    assert all(item["opportunities"][0]["daysOut"] == 149 for item in contexts)


def test_popular_views_are_retargeted_refetched_and_aggregated(monkeypatch):
    monkeypatch.setattr(prefetch, "_prefetch_token", lambda: "test-token")
    target = dt.date(2026, 8, 6)
    saved = [
        {
            "resource_id": "2",
            "views": views,
            "table_context": {
                "years": "20",
                "partial": {"min_winning_years": "17", "mode": "consecutive"},
                "mode": "consecutive",
                "date": old_date,
                "day_range": "10-367",
                "is_default": False,
            },
            # These snapshots are deliberately stale and must never be scored.
            "opportunities": [
                {
                    "symbol": "STALE",
                    "date": old_date,
                    "daysOut": 149,
                    "direction": "l",
                }
            ],
        }
        for old_date, views in (("2026-08-01", 3), ("2026-08-02", 4))
    ]
    logical = prefetch._dedupe_logical_contexts(
        [], saved, target=target, popular_limit=1
    )

    assert len(logical) == 1
    assert logical[0]["views"] == 7
    assert logical[0]["table_context"]["date"] == "2026-08-06"
    assert "opportunities" not in logical[0]

    class TargetHTTP:
        def __init__(self):
            self.calls = []

        def get(self, url, params, timeout):
            self.calls.append((url, params, timeout))
            return FakeResponse(
                {
                    "OppList": [
                        ["2026-08-05", "PAST", 149, "Long"],
                        ["2026-08-06", "FRESH", 149, "Long"],
                    ]
                }
            )

    http = TargetHTTP()
    contexts, failures = prefetch.fetch_target_contexts(
        logical_contexts=logical,
        target=target,
        http_client=http,
        appserver_url="http://127.0.0.1:5000",
    )

    assert failures == []
    assert len(http.calls) == 1
    url, params, timeout = http.calls[0]
    assert "/OppList4/2/August/6/20/17/9-366/0/0" in url
    assert params == {
        "mode": "consecutive",
        "token": "test-token",
        "target_date": "2026-08-06",
    }
    assert timeout == 90
    assert [row["symbol"] for row in contexts[0]["opportunities"]] == ["FRESH"]


def test_popular_one_to_nine_day_view_refetches_engine_zero_to_eight(monkeypatch):
    monkeypatch.setattr(prefetch, "_prefetch_token", lambda: "test-token")
    target = dt.date(2026, 8, 6)
    logical = [{
        "resource_id": "2",
        "views": 5,
        "table_context": {
            "years": "20",
            "partial": {"min_winning_years": "17", "mode": "consecutive"},
            "mode": "consecutive",
            "date": "2026-08-06",
            "day_range": "1-9",
            "is_default": False,
        },
    }]

    class ShortHTTP:
        def __init__(self):
            self.url = ""

        def get(self, url, params, timeout):
            self.url = url
            assert params["target_date"] == "2026-08-06"
            assert timeout == 90
            return FakeResponse({
                "OppList": [
                    ["2026-08-06", "FIRST", 0, "Long"],
                    ["2026-08-06", "SHORT", 8, "Long"],
                ]
            })

    http = ShortHTTP()
    contexts, failures = prefetch.fetch_target_contexts(
        logical_contexts=logical,
        target=target,
        http_client=http,
        appserver_url="http://127.0.0.1:5000",
    )

    assert failures == []
    assert "/OppList4/2/August/6/20/17/0-8/0/0" in http.url
    assert [row["daysOut"] for row in contexts[0]["opportunities"]] == [0, 8]


def test_authoritative_default_refetch_is_not_cut_to_telemetry_row_limit(monkeypatch):
    monkeypatch.setattr(prefetch, "_prefetch_token", lambda: "test-token")
    target = dt.date(2026, 8, 6)
    logical = prefetch._default_logical_contexts(target)[:1]

    class LargeDefaultHTTP:
        def get(self, url, params, timeout):
            del url, params, timeout
            return FakeResponse(
                {
                    "OppList": [
                        ["2026-08-06", f"A{index:03d}", 149, "Long"]
                        for index in range(125)
                    ]
                }
            )

    contexts, failures = prefetch.fetch_target_contexts(
        logical_contexts=logical,
        target=target,
        http_client=LargeDefaultHTTP(),
        appserver_url="http://127.0.0.1:5000",
    )

    assert failures == []
    assert len(contexts[0]["opportunities"]) == 125


def test_authoritative_marker_must_match_current_target_and_session(tmp_path):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)

    # The same marker remains valid across New York midnight: both the late
    # run and its early retry target Aug 6 and use Aug 5's completed session.
    after_midnight = NY_TZ.localize(dt.datetime(2026, 8, 6, 1, 5))
    assert prefetch._read_authoritative_status(
        str(status_path), now=FIXED_NOW
    ) is not None
    assert prefetch._read_authoritative_status(
        str(status_path), now=after_midnight
    ) is not None

    # Once the next session has closed, that marker is stale and fails closed.
    next_close = NY_TZ.localize(dt.datetime(2026, 8, 6, 17, 5))
    assert prefetch._read_authoritative_status(
        str(status_path), now=next_close
    ) is None


def test_legacy_warm_writes_versioned_value_and_pointer_with_atomic_expiry():
    redis_client = StrictSetRedis()
    row = {
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 29,
        "direction": "l",
    }
    completed, failures = prefetch.warm_legacy_rows(
        [row],
        redis_client=redis_client,
        http_client=LegacyScoreHTTP(),
        scorer_url="http://scorer",
        expected_metadata=METADATA,
        ttl_seconds=321,
        request_batch_size=25,
    )

    assert completed == 1
    assert failures == []
    assert len(redis_client.set_calls) == 2
    assert {key.split(":", 3)[2] for key, _value, _ttl in redis_client.set_calls} == {
        "index",
        "value",
    }
    assert all(ttl == 321 for _key, _value, ttl in redis_client.set_calls)
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        29,
        "l",
        expected_metadata=METADATA,
    ) == {
        "status": "available",
        "ml_score": 81.0,
        "win_prob": 0.78,
        "pred_return": 4.2,
        "pred_mfe": 6.7,
    }


def test_legacy_warm_fans_short_sources_into_one_ten_day_cache_identity():
    redis_client = StrictSetRedis()
    http_client = LegacyScoreHTTP()
    rows = [
        {
            "symbol": "AAPL",
            "date": "2026-08-06",
            "daysOut": days_out,
            "direction": "l",
        }
        for days_out in (0, 5, 8, 9)
    ]
    completed, failures = prefetch.warm_legacy_rows(
        rows,
        redis_client=redis_client,
        http_client=http_client,
        scorer_url="http://scorer",
        expected_metadata=METADATA,
        ttl_seconds=321,
        request_batch_size=25,
    )

    assert completed == 4
    assert failures == []
    assert len(http_client.posts) == 1
    assert http_client.posts[0]["opportunities"] == [{
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 9,
        "direction": "l",
    }]
    assert len(redis_client.set_calls) == 2
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        9,
        "l",
        expected_metadata=METADATA,
    )["ml_score"] == 81.0
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        8,
        "l",
        expected_metadata=METADATA,
    ) is None


def test_short_warm_does_not_share_across_date_or_direction():
    redis_client = StrictSetRedis()
    http_client = LegacyScoreHTTP()
    rows = [
        {"symbol": "AAPL", "date": "2026-08-06", "daysOut": 0, "direction": "l"},
        {"symbol": "AAPL", "date": "2026-08-06", "daysOut": 8, "direction": "s"},
        {"symbol": "AAPL", "date": "2026-08-07", "daysOut": 5, "direction": "l"},
    ]

    completed, failures = prefetch.warm_legacy_rows(
        rows,
        redis_client=redis_client,
        http_client=http_client,
        scorer_url="http://scorer",
        expected_metadata=METADATA,
        ttl_seconds=321,
        request_batch_size=25,
    )

    assert completed == 3
    assert failures == []
    assert len(http_client.posts) == 1
    assert http_client.posts[0]["opportunities"] == [
        {"symbol": "AAPL", "date": "2026-08-06", "daysOut": 9, "direction": "l"},
        {"symbol": "AAPL", "date": "2026-08-06", "daysOut": 9, "direction": "s"},
        {"symbol": "AAPL", "date": "2026-08-07", "daysOut": 9, "direction": "l"},
    ]


def test_legacy_unavailable_reason_is_vix_only_when_scorer_says_vix():
    generic = prefetch._terminal_legacy_score(
        {"status": "unavailable", "error": "profile missing"}
    )
    vix = prefetch._terminal_legacy_score(
        {"status": "unavailable", "vix_blocked": True}
    )

    assert generic["error"]["code"] == "provider_unavailable"
    assert vix["error"]["code"] == "vix_blocked"


def test_legacy_warm_rejects_results_without_matching_top_level_metadata():
    redis_client = StrictSetRedis()
    row = {
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 29,
        "direction": "l",
    }

    completed, failures = prefetch.warm_legacy_rows(
        [row],
        redis_client=redis_client,
        http_client=MissingMetadataLegacyHTTP(),
        scorer_url="http://scorer",
        expected_metadata=METADATA,
        ttl_seconds=321,
        request_batch_size=25,
    )

    assert completed == 0
    assert failures == ["legacy 10_30: scorer metadata mismatch"]
    assert redis_client.set_calls == []


def test_retryable_provider_states_cannot_publish_as_warm():
    redis_client = StrictSetRedis()
    row = {
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 29,
        "direction": "l",
    }
    completed, failures = prefetch.warm_legacy_rows(
        [row],
        redis_client=redis_client,
        http_client=RetryableLegacyHTTP(),
        scorer_url="http://scorer",
        expected_metadata=METADATA,
        ttl_seconds=321,
        request_batch_size=25,
    )
    assert completed == 0
    assert failures and "retryable provider state" in failures[0]
    assert redis_client.set_calls == []

    class RetryableCheckpointService:
        def score_bundles(self, plans, max_request_items):
            assert max_request_items == 3
            return {
                plans[0]["ui_key"]: {
                    "horizons": [
                        {
                            "calendar_days": 30,
                            "status": "unavailable",
                            "error": {"retryable": True},
                        }
                    ]
                }
            }

    checkpoint_completed, checkpoint_failures = prefetch.warm_checkpoint_rows(
        [("2", {**row, "daysOut": 149, "years": "20", "partial": "17"})],
        service=RetryableCheckpointService(),
        row_batch_size=1,
    )
    assert checkpoint_completed == 0
    assert checkpoint_failures and "retryable provider state" in checkpoint_failures[0]


def test_warm_selection_accepts_displayed_1_through_367_calendar_days():
    context = {
        "resource_id": "2",
        "context_hash": "bounded-days",
        "opportunities": [
            {
                "symbol": symbol,
                "date": "2026-08-06",
                "daysOut": days_out,
                "direction": "l",
                "years": "20",
                "partial": "17",
            }
            for symbol, days_out in (
                ("FIRST", 0),
                ("SHORT", 8),
                ("LOW", 9),
                ("HIGH", 366),
                ("TOOHIGH", 367),
            )
        ],
    }

    selected = prefetch._selected_opportunities(
        [context],
        rows_per_context=10,
        max_total_rows=10,
    )

    assert [(row["symbol"], row["daysOut"]) for _resource, row in selected] == [
        ("FIRST", 0),
        ("SHORT", 8),
        ("LOW", 9),
        ("HIGH", 366),
    ]
    assert prefetch._opplist_engine_day_range("1-9") == "0-8"
    assert prefetch._legacy_tier(-1) is None
    assert prefetch._legacy_tier(0) == "10_30"
    assert prefetch._legacy_tier(8) == "10_30"
    assert prefetch._legacy_tier(9) == "10_30"
    assert prefetch._legacy_tier(89) == "61_90"
    assert prefetch._legacy_tier(90) is None
    assert prefetch._legacy_tier(367) is None

    past_context = {
        **context,
        "opportunities": [
            {
                "symbol": "PAST",
                "date": "2026-08-05",
                "daysOut": 29,
                "direction": "l",
                "years": "20",
                "partial": "17",
            },
            {
                "symbol": "TARGET",
                "date": "2026-08-06",
                "daysOut": 29,
                "direction": "l",
                "years": "20",
                "partial": "17",
            },
        ],
    }
    current = prefetch._selected_opportunities(
        [past_context],
        rows_per_context=10,
        max_total_rows=10,
        minimum_entry_date=dt.date(2026, 8, 6),
    )
    assert [row["symbol"] for _resource, row in current] == ["TARGET"]


def test_default_rows_are_uncapped_per_context_before_bounded_popular_rows():
    def rows(prefix, count):
        return [
            {
                "symbol": f"{prefix}{index}",
                "date": "2026-08-06",
                "daysOut": 149,
                "direction": "l",
                "years": "20",
                "partial": "17",
            }
            for index in range(count)
        ]

    contexts = [
        {
            "resource_id": "2",
            "is_default": True,
            "opportunities": rows("D", 25),
        },
        {
            "resource_id": "2",
            "is_default": False,
            "opportunities": rows("P", 20),
        },
        {
            "resource_id": "2",
            "is_default": False,
            "opportunities": rows("Q", 20),
        },
    ]

    selected, coverage = prefetch._select_opportunities_with_coverage(
        contexts,
        popular_rows_per_context=10,
        popular_max_rows=15,
        max_total_rows=2500,
        minimum_entry_date=dt.date(2026, 8, 6),
    )

    assert len(selected) == 40
    assert coverage["eligible_rows"] == 65
    assert coverage["selected_rows"] == 40
    assert coverage["truncated_rows"] == 25
    assert coverage["truncated"] is True
    assert coverage["default"] == {
        "eligible_rows": 25,
        "selected_rows": 25,
        "truncated_rows": 0,
        "truncated": False,
    }
    assert coverage["popular"] == {
        "eligible_rows": 40,
        "selected_rows": 15,
        "truncated_rows": 25,
        "truncated": True,
    }
    assert [row["symbol"] for _resource, row in selected[:25]] == [
        f"D{index}" for index in range(25)
    ]

    globally_bounded, bounded_coverage = prefetch._select_opportunities_with_coverage(
        contexts,
        popular_rows_per_context=10,
        popular_max_rows=15,
        max_total_rows=30,
        minimum_entry_date=dt.date(2026, 8, 6),
    )
    assert len(globally_bounded) == 30
    assert bounded_coverage["default"]["selected_rows"] == 25
    assert bounded_coverage["popular"]["selected_rows"] == 5
    assert bounded_coverage["truncated_rows"] == 35


def test_selected_popular_context_keeps_a_typical_table_whole_when_budget_allows():
    context = {
        "resource_id": "2",
        "is_default": False,
        "opportunities": [
            {
                "symbol": f"S{index}",
                "date": "2026-08-06",
                "daysOut": 94,
                "direction": "l",
                "years": "10",
                "partial": "9",
            }
            for index in range(39)
        ],
    }

    selected, coverage = prefetch._select_opportunities_with_coverage(
        [context],
        popular_rows_per_context=100,
        popular_max_rows=180,
        max_total_rows=2500,
        minimum_entry_date=dt.date(2026, 8, 6),
    )

    assert len(selected) == 39
    assert coverage["popular"] == {
        "eligible_rows": 39,
        "selected_rows": 39,
        "truncated_rows": 0,
        "truncated": False,
    }


@pytest.mark.parametrize("missing_field", prefetch._REQUIRED_SCORER_IDENTITY_FIELDS)
def test_prefetch_metadata_fails_closed_for_every_missing_identity_field(
    missing_field,
):
    metadata = {**METADATA}
    metadata.pop(missing_field)

    assert prefetch._valid_prefetch_metadata(metadata) is False


@pytest.mark.parametrize(
    "metadata",
    [
        {**METADATA, "model_release": "v2-legacy"},
        {**METADATA, "feature_schema_version": "v3-59"},
        {**METADATA, "context_data_complete": "False"},
        {**METADATA, "data_generation_hash": "unknown"},
    ],
)
def test_prefetch_metadata_requires_complete_v3_62_identity(metadata):
    assert prefetch._valid_prefetch_metadata(metadata) is False


def test_prefetch_metadata_accepts_complete_v3_62_identity():
    assert prefetch._valid_prefetch_metadata(METADATA) is True


def test_prefetch_defers_cleanly_for_v2(tmp_path, monkeypatch):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: None,
    )
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "legacy_scorer_metadata",
        lambda _self: {
            "scorer_mode": "v2",
            "model_release": "v2-legacy-59",
            "feature_schema_version": "v2-59",
        },
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    assert prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=FakeRedis(),
        http_client=object(),
        now=FIXED_NOW,
    ) == 0


@pytest.mark.parametrize("data_as_of", ["2026-08-04", "2026-08-06"])
def test_prefetch_rejects_scorer_data_not_aligned_to_eod_session(
    tmp_path, monkeypatch, data_as_of
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    redis_client = FakeRedis()
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: {**METADATA, "data_as_of": data_as_of},
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    assert prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=object(),
        now=FIXED_NOW,
    ) == 1
    assert redis_client.get(prefetch.ACTIVE_GENERATION_KEY) is None


def test_complete_generation_and_active_pointer_publish_atomically(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    redis_client = FakeRedis()
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: (_empty_defaults(), []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=object(),
        now=FIXED_NOW,
    )

    assert result == 0
    active = json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY))
    manifest = json.loads(redis_client.get(active["manifest_key"]))
    assert manifest["status"] == "complete"
    assert manifest["default_contexts"] == 6
    assert manifest["selected_rows"] == 0
    assert manifest["eligible_rows"] == 0
    assert manifest["warmed_rows"] == 0
    assert manifest["staged_terminal_rows"] == 0
    assert manifest["legacy_source_rows"] == 0
    assert manifest["legacy_unique_requests"] == 0
    assert manifest["legacy_deduplicated_rows"] == 0
    assert manifest["short_source_rows"] == 0
    assert manifest["short_unique_requests"] == 0
    assert manifest["short_deduplicated_rows"] == 0
    assert manifest["truncated_rows"] == 0
    assert manifest["selection_truncated"] is False
    assert manifest["selection_coverage"]["limits"] == {
        "global_max_rows": 2500,
        "popular_rows_per_context": 100,
        "popular_max_rows": 180,
    }
    assert manifest["selection_coverage"]["default"]["warmed_rows"] == 0
    assert manifest["selection_coverage"]["popular"]["warmed_rows"] == 0
    assert manifest["target_table_date"] == "2026-08-06"
    assert manifest["data_alignment"] == {
        "aligned": True,
        "scorer_data_as_of": "2026-08-05",
        "eod_completed_session": "2026-08-05",
        "latest_us_date": "2026-08-05",
    }
    assert manifest["final_scorer_verification"] == {
        "verified": True,
        "scorer_fingerprint": prefetch.metadata_fingerprint(METADATA),
        "data_as_of": "2026-08-05",
    }
    assert active["target_table_date"] == "2026-08-06"
    assert active["scorer_data_as_of"] == "2026-08-05"
    assert active["contract_version"] == prefetch.CONTEXT_CONTRACT_VERSION

    monkeypatch.setenv("TW2_ML_PREFETCH_MAX_ROWS", "181")
    assert prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=object(),
        now=FIXED_NOW,
    ) == 0
    next_active = json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY))
    assert next_active["generation_id"] != active["generation_id"]
    assert next_active["policy_fingerprint"] != active["policy_fingerprint"]


def test_complete_manifest_reports_warmed_default_scope(tmp_path, monkeypatch):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    context = {
        "resource_id": "2",
        "context_hash": "one-default-row",
        "is_default": True,
        "opportunities": [
            {
                "symbol": "AAPL",
                "date": "2026-08-06",
                "daysOut": 29,
                "direction": "l",
                "years": "20",
                "partial": "17",
            }
        ],
    }
    redis_client = FakeRedis()
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: ([context], []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    assert prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=LegacyScoreHTTP(),
        now=FIXED_NOW,
    ) == 0

    active = json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY))
    manifest = json.loads(redis_client.get(active["manifest_key"]))
    assert manifest["eligible_rows"] == 1
    assert manifest["selected_rows"] == 1
    assert manifest["staged_terminal_rows"] == 1
    assert manifest["legacy_source_rows"] == 1
    assert manifest["legacy_unique_requests"] == 1
    assert manifest["legacy_deduplicated_rows"] == 0
    assert manifest["warmed_rows"] == 1
    assert manifest["selection_coverage"]["default"]["warmed_rows"] == 1
    assert manifest["selection_coverage"]["popular"]["warmed_rows"] == 0


def test_scorer_restart_before_publish_keeps_generation_invisible(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    row = {
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 29,
        "direction": "l",
        "years": "20",
        "partial": "17",
    }
    context = {
        "resource_id": "2",
        "context_hash": "one-legacy-row",
        "opportunities": [row],
    }
    redis_client = FakeRedis()
    redis_client.set(prefetch.ACTIVE_GENERATION_KEY, '{"generation_id":"prior"}')
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: ([context], []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(
        prefetch,
        "_live_scorer_metadata",
        lambda **_kwargs: {**METADATA, "model_release": "v3-restarted"},
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=LegacyScoreHTTP(),
        now=FIXED_NOW,
    )

    assert result == 1
    assert json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY)) == {
        "generation_id": "prior"
    }
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        29,
        "l",
        expected_metadata=METADATA,
    ) is None
    manifests = [
        json.loads(value)
        for key, value in redis_client.data.items()
        if key.startswith(f"{prefetch.CACHE_SCHEMA_VERSION}:prefetch:generation:")
    ]
    assert len(manifests) == 1
    assert manifests[0]["status"] == "failed"
    assert manifests[0]["staged_terminal_rows"] == 1
    assert manifests[0]["warmed_rows"] == 0
    assert manifests[0]["selection_coverage"]["popular"]["warmed_rows"] == 0
    assert manifests[0]["final_scorer_verification"]["verified"] is False
    assert manifests[0]["final_scorer_verification"]["reason"] == "identity_changed"
    assert "scorer identity changed before atomic publication" in manifests[0][
        "failures"
    ]


def test_failed_generation_never_replaces_active_pointer(tmp_path, monkeypatch):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    redis_client = FakeRedis()
    redis_client.set(prefetch.ACTIVE_GENERATION_KEY, '{"generation_id":"prior"}')
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: (_empty_defaults(), ["seed failed"]),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=object(),
        now=FIXED_NOW,
    )

    assert result == 1
    assert json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY)) == {
        "generation_id": "prior"
    }


def test_failed_midrun_legacy_generation_exposes_no_staged_values(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    rows = [
        {
            "symbol": symbol,
            "date": "2026-08-06",
            "daysOut": 29,
            "direction": "l",
            "years": "20",
            "partial": "17",
        }
        for symbol in ("AAPL", "MSFT")
    ]
    context = {
        "resource_id": "2",
        "context_hash": "two-legacy-rows",
        "opportunities": rows,
    }
    redis_client = FakeRedis()
    redis_client.set(prefetch.ACTIVE_GENERATION_KEY, '{"generation_id":"prior"}')
    old_metadata = {**METADATA, "model_release": "v3-old"}
    old_score = {
        "ml_score": 12,
        "win_prob": 0.52,
        "pred_return": 1.2,
        "pred_mfe": 2.1,
    }
    write_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        29,
        "l",
        old_score,
        metadata=old_metadata,
        ttl_seconds=300,
    )
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: ([context], []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")
    monkeypatch.setenv("TW2_ML_PREFETCH_LEGACY_BATCH_SIZE", "1")
    http = FailSecondLegacyHTTP()

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=http,
        now=FIXED_NOW,
    )

    assert result == 1
    assert http.posts == 2
    assert json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY)) == {
        "generation_id": "prior"
    }
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        29,
        "l",
        expected_metadata=old_metadata,
    )["ml_score"] == 12
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-06",
        29,
        "l",
        expected_metadata=METADATA,
    ) is None
    assert read_cached_legacy_score(
        redis_client,
        "MSFT",
        "2026-08-06",
        29,
        "l",
        expected_metadata=METADATA,
    ) is None
    assert any(
        key.startswith(f"{prefetch.CACHE_SCHEMA_VERSION}:prefetch:staged:")
        for key in redis_client.data
    )


def test_failed_midrun_checkpoint_generation_exposes_no_staged_values(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    rows = [
        {
            "symbol": symbol,
            "date": "2026-08-06",
            "daysOut": 149,
            "direction": "l",
            "years": "20",
            "partial": {
                "min_winning_years": "17",
                "mode": "consecutive",
            },
        }
        for symbol in ("AAPL", "MSFT")
    ]
    context = {
        "resource_id": "2",
        "context_hash": "two-long-rows",
        "opportunities": rows,
    }
    redis_client = FakeRedis()
    redis_client.set(prefetch.ACTIVE_GENERATION_KEY, '{"generation_id":"prior"}')

    first_plan = prefetch.build_checkpoint_plan("2", rows[0])
    second_plan = prefetch.build_checkpoint_plan("2", rows[1])
    old_metadata = {**METADATA, "model_release": "v3-old"}
    old_checkpoints = []
    for request_item in first_plan["requests"]:
        checkpoint = {
            "status": "available",
            "calendar_days": request_item["calendar_days"],
            "ml_score": 12,
            "win_prob": 0.52,
            "pred_return": 1.2,
            "pred_mfe": 2.1,
            "scorer": old_metadata,
        }
        old_checkpoints.append(checkpoint)
        write_cached_checkpoint(
            redis_client,
            request_item,
            checkpoint,
            ttl_seconds=300,
        )

    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: ([context], []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")
    monkeypatch.setenv("TW2_ML_PREFETCH_CHECKPOINT_ROW_BATCH", "1")
    http = FailSecondCheckpointHTTP()

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=http,
        now=FIXED_NOW,
    )

    assert result == 1
    assert http.posts == 2
    assert json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY)) == {
        "generation_id": "prior"
    }
    assert [
        read_cached_checkpoint(redis_client, item)
        for item in first_plan["requests"]
    ] == old_checkpoints
    assert all(
        read_cached_checkpoint(redis_client, item) is None
        for item in second_plan["requests"]
    )
    assert any(
        key.startswith(f"{prefetch.CACHE_SCHEMA_VERSION}:prefetch:staged:")
        for key in redis_client.data
    )


def test_failed_atomic_publish_keeps_staged_checkpoint_out_of_read_path(
    tmp_path, monkeypatch
):
    status_path = tmp_path / "status.json"
    _write_valid_status(status_path)
    row = {
        "symbol": "AAPL",
        "date": "2026-08-06",
        "daysOut": 149,
        "direction": "l",
        "years": "20",
        "partial": {"min_winning_years": "17", "mode": "consecutive"},
    }
    context = {
        "resource_id": "2",
        "context_hash": "one-long-row",
        "opportunities": [row],
    }
    redis_client = RejectFinalPublicationRedis()
    redis_client.set(prefetch.ACTIVE_GENERATION_KEY, '{"generation_id":"prior"}')
    monkeypatch.setattr(
        prefetch,
        "fetch_target_contexts",
        lambda **_kwargs: ([context], []),
    )
    monkeypatch.setattr(prefetch, "ranked_usage_contexts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        prefetch.CheckpointScoringService,
        "scorer_metadata",
        lambda _self: METADATA,
    )
    monkeypatch.setattr(prefetch.config, "ml_scorer_url", "http://scorer")

    result = prefetch.run_prefetch(
        status_file=str(status_path),
        redis_client=redis_client,
        http_client=FailSecondCheckpointHTTP(),
        now=FIXED_NOW,
    )

    assert result == 1
    assert json.loads(redis_client.get(prefetch.ACTIVE_GENERATION_KEY)) == {
        "generation_id": "prior"
    }
    plan = prefetch.build_checkpoint_plan("2", row)
    assert all(
        read_cached_checkpoint(redis_client, item) is None
        for item in plan["requests"]
    )
    manifests = [
        json.loads(value)
        for key, value in redis_client.data.items()
        if key.startswith(f"{prefetch.CACHE_SCHEMA_VERSION}:prefetch:generation:")
    ]
    assert len(manifests) == 1
    assert manifests[0]["status"] == "failed"


def test_eod_cron_and_imports_follow_the_environment_runtime_model():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "ops" / "install_eod_cron.sh").read_text(
        encoding="utf-8"
    )
    updater = (repo_root / "data_updater" / "update_client2.py").read_text(
        encoding="utf-8"
    )

    assert "dev)" in installer
    assert "RELEASE_ROOT='/home/flask/.tw2-app-current'" in installer
    assert "staging|prod)" in installer
    assert "RELEASE_ROOT='/home/flask'" in installer
    assert "cd $RELEASE_ROOT/data_updater" in installer
    assert "TW2_ENV must be dev, staging, or prod" in installer
    assert "REPO_ROOT = os.path.dirname" in updater
    forbidden_live_import = "sys.path.insert(0, " + repr("/home/flask") + ")"
    assert forbidden_live_import not in updater
