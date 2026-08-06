"""Contracts for recalculated V3 checkpoints, cache identity, and usage ranking."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys

import pytest


APPSERVER_DIR = Path(__file__).resolve().parents[1] / "appserver" / "appserver"
if str(APPSERVER_DIR) not in sys.path:
    sys.path.insert(0, str(APPSERVER_DIR))

from ml_checkpoint_context import (  # noqa: E402
    CheckpointContextError,
    CheckpointProviderError,
    CheckpointScoringService,
    assemble_duration_comparison_bundle,
    build_checkpoint_plan,
    build_usage_context,
    checkpoint_pending_opportunity,
    checkpoint_pointer_key,
    checkpoint_value_key,
    legacy_score_keys,
    legacy_pointer_key,
    legacy_value_key,
    normalize_checkpoint_response,
    normalize_legacy_score_result,
    read_cached_legacy_score,
    ranked_usage_contexts,
    read_cached_checkpoint,
    record_usage_context,
    write_cached_checkpoint,
    write_cached_legacy_score,
)
from tara_ai_analysis import (  # noqa: E402
    build_analysis_score_plan,
    finalize_analysis_checkpoint_bundle,
)
from tara_answer_planner import _analysis_ai_context_line  # noqa: E402


METADATA = {
    "model_release": "v3-test",
    "feature_schema_version": "v3-62",
    "feature_schema_hash": "features123",
    "context_schema_version": "context-v1",
    "pattern_profile_schema_version": "profile-v1",
    "model_manifest_hash": "abc123",
    "data_as_of": "2026-08-05",
    "data_generation_hash": "data-generation-123",
    "data_source_manifest_hash": "data-sources-123",
    "context_data_complete": "True",
}


SELECTED_RECURRENCE = {
    "status": "qualified",
    "mode": "consecutive",
    "years": "20",
    "requested_observations": 20,
    "sample_size": 20,
    "positive_years": 17,
    "required_positive_years": 17,
    "win_rate": 0.85,
    "average_return_pct": 2.1,
    "median_return_pct": 1.8,
    "average_favorable_excursion_pct": 4.2,
    "complete": True,
}


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def __getattr__(self, name):
        def queued(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return queued

    def execute(self):
        for name, args, kwargs in self.calls:
            getattr(self.redis, name)(*args, **kwargs)
        return [True] * len(self.calls)


class FakeLock:
    def __init__(self, redis, key):
        self.redis = redis
        self.key = key
        self.owned = False

    def acquire(self, blocking=True):
        del blocking
        if self.key in self.redis.locks:
            return False
        self.redis.locks.add(self.key)
        self.owned = True
        return True

    def release(self):
        if not self.owned:
            raise RuntimeError("not owned")
        self.redis.locks.remove(self.key)
        self.owned = False


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.zsets = {}
        self.locks = set()

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        del ex
        self.data[key] = value.encode() if isinstance(value, str) else value
        return True

    def expire(self, key, seconds):
        del key, seconds
        return True

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)

    def lock(self, key, timeout=None, blocking_timeout=None):
        del timeout, blocking_timeout
        return FakeLock(self, key)

    def zincrby(self, key, amount, member):
        zset = self.zsets.setdefault(key, {})
        zset[member] = zset.get(member, 0.0) + float(amount)
        return zset[member]

    def zrevrange(self, key, start, end, withscores=False):
        items = sorted(
            self.zsets.get(key, {}).items(),
            key=lambda item: (-item[1], item[0]),
        )
        sliced = items[start : end + 1]
        if withscores:
            return [(member.encode(), score) for member, score in sliced]
        return [member.encode() for member, _score in sliced]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeScorerHTTP:
    def __init__(self):
        self.posts = []
        self.gets = 0

    def get(self, url, timeout):
        assert url.endswith("/health")
        assert timeout == 3
        self.gets += 1
        return FakeResponse(METADATA)

    def post(self, url, json, timeout):
        assert url.endswith("/score/context")
        assert timeout == 35
        self.posts.append(json)
        items = json["opportunities"]
        return FakeResponse(
            {
                "metadata": METADATA,
                "results": [
                    {
                        **item,
                        "daysOut": item["calendar_days"] - 1,
                        "tier": (
                            "10_30"
                            if item["calendar_days"] == 30
                            else "31_60"
                            if item["calendar_days"] == 60
                            else "61_90"
                        ),
                        "ml_score": item["calendar_days"] / 3,
                        "win_prob": 0.5 + item["calendar_days"] / 1000,
                        "pred_return": item["calendar_days"] / 10,
                        "pred_mfe": item["calendar_days"] / 8,
                        "pattern_recalculated": True,
                        "selected_recurrence": SELECTED_RECURRENCE,
                        "pattern_profile": {
                            "source": "dynamic_recalculation",
                            "qualifying_combo_count": 7,
                            "profile_hash": f"{item['calendar_days']:064x}",
                        },
                        "context_hash": f"{item['calendar_days'] + 1:064x}",
                        "feature_vector_hash": f"{item['calendar_days'] + 2:064x}",
                    }
                    for item in items
                ],
            }
        )


def long_opp(symbol="AAPL", date="2026-08-10", days_out=149):
    return {
        "symbol": symbol,
        "date": date,
        "daysOut": days_out,
        "direction": "l",
        "years": "20",
        "partial": {"min_winning_years": "17", "mode": "consecutive"},
    }


def test_legacy_score_keys_add_date_without_breaking_the_old_alias():
    first = legacy_score_keys("aapl", "2026-08-10", 29, "long")
    second = legacy_score_keys("AAPL", "2026-09-10", 29, "l")

    assert first == ("AAPL|2026-08-10|29|l", "AAPL|29|l")
    assert second == ("AAPL|2026-09-10|29|l", "AAPL|29|l")
    assert first[0] != second[0]
    assert first[1] == second[1]


def test_legacy_cache_is_exact_and_invalidates_with_scorer_generation():
    redis_client = FakeRedis()
    score = {
        "ml_score": 71,
        "win_prob": 0.7,
        "pred_return": 2.1,
        "pred_mfe": 4.2,
    }
    write_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-10",
        29,
        "l",
        score,
        metadata=METADATA,
        ttl_seconds=300,
    )

    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-10",
        29,
        "l",
        expected_metadata=METADATA,
    )["ml_score"] == 71
    changed = {**METADATA, "data_generation_hash": "next-generation"}
    assert read_cached_legacy_score(
        redis_client,
        "AAPL",
        "2026-08-10",
        29,
        "l",
        expected_metadata=changed,
    ) is None
    assert legacy_pointer_key("AAPL", "2026-08-10", 29, "l").startswith(
        "ml6:legacy:index:"
    )
    assert legacy_value_key("AAPL", "2026-08-10", 29, "l", METADATA) != legacy_value_key(
        "AAPL", "2026-08-10", 29, "l", changed
    )


def test_legacy_unavailable_codes_are_closed_and_vix_is_explicit():
    generic = normalize_legacy_score_result(
        {
            "status": "unavailable",
            "error": {"code": "internal_detail", "message": "do not expose"},
        }
    )
    vix = normalize_legacy_score_result(
        {"status": "unavailable", "error": "VIX detail", "vix_blocked": True}
    )

    assert generic["error"] == {
        "code": "provider_unavailable",
        "message": "Current-condition scoring is temporarily unavailable.",
        "retryable": True,
    }
    assert vix["error"] == {
        "code": "vix_blocked",
        "message": "Volatility safety gate is active.",
        "retryable": False,
    }

    target_entry = normalize_legacy_score_result(
        {
            "status": "unavailable",
            "error": {
                "code": "target_entry_unavailable",
                "message": "private provider detail must not escape",
                "retryable": False,
            },
        }
    )
    assert target_entry["error"] == {
        "code": "target_entry_unavailable",
        "message": "A valid price entry could not be established for this date.",
        "retryable": False,
    }


def test_raw_90_is_a_long_pattern_and_requests_exact_inclusive_checkpoints():
    plan = build_checkpoint_plan("2", long_opp(days_out=90))

    assert plan["ui_key"] == "AAPL|2026-08-10|90|l"
    assert plan["source"]["calendar_days"] == 91
    assert [item["calendar_days"] for item in plan["requests"]] == [30, 60, 90]
    assert all("daysOut" not in item and "entry_date" not in item for item in plan["requests"])
    assert [item["calendar_days"] - 1 for item in plan["requests"]] == [29, 59, 89]
    assert {item["resource_id"] for item in plan["requests"]} == {"2"}


def test_85_day_pattern_requests_only_30_and_60_and_keeps_85_current():
    opportunity = long_opp(days_out=84)
    plan = build_checkpoint_plan("2", opportunity)

    assert plan["source"]["calendar_days"] == 85
    assert plan["display_horizon_days"] == 85
    assert plan["includes_current_score"] is True
    assert [item["calendar_days"] for item in plan["requests"]] == [30, 60]

    checkpoints = [
        {
            "calendar_days": day,
            "status": "available",
            "ml_score": day,
            "win_prob": 0.6,
            "pred_return": 2.0,
            "pred_mfe": 4.0,
        }
        for day in (30, 60)
    ]
    comparison = assemble_duration_comparison_bundle(
        plan,
        {"horizons": checkpoints},
        current_score={
            "ml_score": 74,
            "win_prob": 0.68,
            "pred_return": 2.4,
            "pred_mfe": 5.2,
        },
    )

    assert comparison["basis"] == "duration_comparison"
    assert comparison["display_horizon_days"] == 85
    assert comparison["ml_score"] == 74.0
    assert [item["calendar_days"] for item in comparison["horizons"]] == [30, 60, 85]
    assert comparison["horizons"][-1]["is_current"] is True


def test_duration_comparison_starts_strictly_after_30_calendar_days():
    with pytest.raises(CheckpointContextError):
        build_checkpoint_plan("2", long_opp(days_out=29))
    plan = build_checkpoint_plan("2", long_opp(days_out=30))
    assert [item["calendar_days"] for item in plan["requests"]] == [30]


def test_source_duration_is_explanation_only_and_dedupes_checkpoint_requests():
    pattern_150 = build_checkpoint_plan("2", long_opp(days_out=149))
    pattern_180 = build_checkpoint_plan("2", long_opp(days_out=179))

    assert pattern_150["source"]["calendar_days"] == 150
    assert pattern_180["source"]["calendar_days"] == 180
    assert pattern_150["requests"] == pattern_180["requests"]
    assert [checkpoint_pointer_key(item) for item in pattern_150["requests"]] == [
        checkpoint_pointer_key(item) for item in pattern_180["requests"]
    ]
    assert "source_pattern_calendar_days" not in pattern_150["requests"][0]["partial"]


def test_pe_mode_preserves_string_identity_and_rejects_non_us_or_numeric_years():
    opportunity = long_opp()
    opportunity.update({"years": "10", "mode": "pe2", "direction": "short"})
    plan = build_checkpoint_plan("11", opportunity)

    assert {item["years"] for item in plan["requests"]} == {"pe2-10"}
    assert {item["direction"] for item in plan["requests"]} == {"s"}
    assert plan["source"]["partial"]["requested_years"] == "10"

    with pytest.raises(CheckpointContextError, match="US stocks and ETFs"):
        build_checkpoint_plan("7", opportunity)
    with pytest.raises(CheckpointContextError, match="years must be a string"):
        build_checkpoint_plan("2", {**opportunity, "years": 10})


def test_pending_round_trip_preserves_pe_and_table_level_fallback_identity():
    browser_row = {
        "symbol": "AAPL",
        "date": "2026-08-10",
        "daysOut": 149,
        "direction": "l",
    }
    initial = build_checkpoint_plan(
        "2",
        browser_row,
        fallback_years="10",
        fallback_partial={"min_winning_years": "6", "mode": "pe"},
        fallback_mode="pe",
        selection_origin="opportunity_table",
    )
    pending = checkpoint_pending_opportunity(browser_row, initial)
    rebuilt = build_checkpoint_plan("2", pending)

    assert pending == {
        **browser_row,
        "years": "10",
        "partial": {"min_winning_years": "6", "mode": "pe"},
        "mode": "pe",
        "selection_origin": "opportunity_table",
    }
    assert rebuilt["requests"] == initial["requests"]
    assert rebuilt["source"] == initial["source"]


def test_selection_origin_is_source_metadata_not_scorer_or_cache_identity():
    scanner = build_checkpoint_plan(
        "2",
        {
            **long_opp(),
            "partial": {
                "min_winning_years": "17",
                "mode": "consecutive",
                "selection_origin": "scanner",
            },
            "selection_origin": "scanner",
        },
    )
    table = build_checkpoint_plan(
        "2",
        {
            **long_opp(),
            "selection_origin": "opportunity_table",
        },
    )
    tara = build_checkpoint_plan(
        "2",
        {
            **long_opp(),
            "selection_origin": "tara",
        },
    )

    assert scanner["requests"] == table["requests"] == tara["requests"]
    assert "selection_origin" not in scanner["requests"][0]["partial"]
    assert "selection_origin" not in scanner["requests"][0]["partial"]["selection"]
    assert checkpoint_pointer_key(scanner["requests"][0]) == checkpoint_pointer_key(
        table["requests"][0]
    )
    assert scanner["source"]["selection_origin"] == "scanner"
    assert table["source"]["selection_origin"] == "opportunity_table"
    assert tara["source"]["selection_origin"] == "tara"


@pytest.mark.parametrize(
    ("table_mode", "tara_mode", "partial", "expected_years"),
    [
        (
            "consecutive",
            "consecutive",
            {"min_winning_years": "9", "mode": "consecutive"},
            "10",
        ),
        ("pe", "pe2", {"min_winning_years": "6", "mode": "pe"}, "pe2-10"),
    ],
)
def test_table_and_tara_recurrence_contexts_share_checkpoint_identity(
    table_mode, tara_mode, partial, expected_years
):
    base = {
        "symbol": "AAPL",
        "date": "2026-08-10",
        "daysOut": 149,
        "direction": "l",
        "years": "10",
        "partial": partial,
    }
    table = build_checkpoint_plan(
        "2", {**base, "mode": table_mode, "selection_origin": "opportunity_table"}
    )
    tara = build_checkpoint_plan(
        "2", {**base, "mode": tara_mode, "selection_origin": "scanner"}
    )

    assert {item["years"] for item in table["requests"]} == {expected_years}
    assert table["requests"] == tara["requests"]
    assert [checkpoint_pointer_key(item) for item in table["requests"]] == [
        checkpoint_pointer_key(item) for item in tara["requests"]
    ]


def test_provider_identity_and_all_four_scores_are_validated():
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    result = {
        **request_item,
        "tier": "10_30",
        "pattern_recalculated": True,
        "selected_recurrence": SELECTED_RECURRENCE,
        "ml_score": 0,
        "win_prob": 0,
        "pred_return": -2.5,
        "pred_mfe": 0,
        "pattern_profile": {
            "source": "dynamic_recalculation",
            "qualifying_combo_count": 3,
            "profile_hash": "a" * 64,
        },
        "context_hash": "b" * 64,
        "feature_vector_hash": "c" * 64,
    }
    checkpoint = normalize_checkpoint_response(
        request_item,
        {"metadata": METADATA, "results": [result]},
    )

    assert checkpoint["status"] == "available"
    assert checkpoint["pattern_recalculated"] is True
    assert [
        checkpoint[field]
        for field in ("ml_score", "win_prob", "pred_return", "pred_mfe")
    ] == [0.0, 0.0, -2.5, 0.0]
    assert checkpoint["scorer"] == METADATA


def test_below_threshold_checkpoint_keeps_evidence_without_fake_metrics():
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    below = {
        **request_item,
        "tier": "10_30",
        "status": "below_threshold",
        "pattern_recalculated": True,
        "selected_recurrence": {
            **SELECTED_RECURRENCE,
            "status": "below_threshold",
            "positive_years": 6,
        },
        "context_hash": "b" * 64,
    }

    checkpoint = normalize_checkpoint_response(
        request_item,
        {"metadata": METADATA, "results": [below]},
    )

    assert checkpoint["status"] == "below_threshold"
    assert checkpoint["ml_score"] is None
    assert checkpoint["selected_recurrence"] == {
        **SELECTED_RECURRENCE,
        "status": "below_threshold",
        "positive_years": 6,
    }


def test_available_checkpoint_rejects_unverified_tier_profile_and_hashes():
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    valid_result = {
        **request_item,
        "tier": "10_30",
        "pattern_recalculated": True,
        "selected_recurrence": SELECTED_RECURRENCE,
        "ml_score": 75,
        "win_prob": 0.7,
        "pred_return": 2.5,
        "pred_mfe": 4.0,
        "pattern_profile": {
            "source": "dynamic_recalculation",
            "qualifying_combo_count": 3,
            "profile_hash": "a" * 64,
        },
        "context_hash": "b" * 64,
        "feature_vector_hash": "c" * 64,
    }
    invalid_results = []
    for field, value in (
        ("tier", "31_60"),
        ("context_hash", ""),
        ("feature_vector_hash", "not-a-sha256"),
    ):
        candidate = {**valid_result, field: value}
        invalid_results.append(candidate)
    for profile_update in (
        {"qualifying_combo_count": 0},
        {"profile_hash": ""},
    ):
        candidate = {
            **valid_result,
            "pattern_profile": {
                **valid_result["pattern_profile"],
                **profile_update,
            },
        }
        invalid_results.append(candidate)

    for result in invalid_results:
        with pytest.raises(CheckpointProviderError):
            normalize_checkpoint_response(
                request_item,
                {"metadata": METADATA, "results": [result]},
            )


def test_checkpoint_rejects_a_complete_but_different_scorer_identity():
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    result = {
        **request_item,
        "tier": "10_30",
        "pattern_recalculated": True,
        "selected_recurrence": SELECTED_RECURRENCE,
        "ml_score": 75,
        "win_prob": 0.7,
        "pred_return": 2.5,
        "pred_mfe": 4.0,
        "pattern_profile": {
            "qualifying_combo_count": 3,
            "profile_hash": "a" * 64,
        },
        "context_hash": "b" * 64,
        "feature_vector_hash": "c" * 64,
    }
    changed = {**METADATA, "data_generation_hash": "other-complete-generation"}

    with pytest.raises(CheckpointProviderError):
        normalize_checkpoint_response(
            request_item,
            {"metadata": changed, "results": [result]},
            expected_metadata=METADATA,
        )


def test_structured_vix_unavailable_is_preserved_not_coerced_to_pending_or_zero():
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    checkpoint = normalize_checkpoint_response(
        request_item,
        {
            "metadata": METADATA,
            "results": [
                {
                    **request_item,
                    "tier": "10_30",
                    "status": "unavailable",
                    "error": {
                        "code": "vix_blocked",
                        "message": "Volatility gate is active.",
                        "retryable": False,
                    },
                    "vix_blocked": True,
                }
            ],
        },
    )

    assert checkpoint["status"] == "unavailable"
    assert checkpoint["error"] == {
        "code": "vix_blocked",
        "message": "Volatility gate is active.",
        "retryable": False,
    }
    assert checkpoint["pattern_recalculated"] is False


def test_exact_cache_identity_includes_provenance_and_scorer_versions():
    redis_client = FakeRedis()
    request_item = build_checkpoint_plan("2", long_opp())["requests"][0]
    checkpoint = {
        "status": "available",
        "calendar_days": 30,
        "ml_score": 80,
        "win_prob": 0.8,
        "pred_return": 4,
        "pred_mfe": 6,
        "scorer": METADATA,
    }
    write_cached_checkpoint(
        redis_client,
        request_item,
        checkpoint,
        ttl_seconds=300,
    )

    assert read_cached_checkpoint(
        redis_client, request_item, expected_metadata=METADATA
    ) == checkpoint
    changed_partial = {
        **request_item,
        "partial": {**request_item["partial"], "selection": {"min_winning_years": "18"}},
    }
    assert checkpoint_pointer_key(changed_partial) != checkpoint_pointer_key(request_item)
    assert read_cached_checkpoint(redis_client, changed_partial) is None
    changed_metadata = {**METADATA, "model_release": "v3-next"}
    assert read_cached_checkpoint(
        redis_client, request_item, expected_metadata=changed_metadata
    ) is None
    assert checkpoint_value_key(request_item, METADATA) != checkpoint_value_key(
        request_item, changed_metadata
    )


def test_cold_multiple_rows_use_one_bounded_context_post_then_hit_cache():
    redis_client = FakeRedis()
    http = FakeScorerHTTP()
    service = CheckpointScoringService(
        redis_client=redis_client,
        scorer_url="http://scorer",
        http_client=http,
        ttl_seconds=300,
    )
    plans = [
        build_checkpoint_plan("2", long_opp("AAPL")),
        build_checkpoint_plan("2", long_opp("MSFT")),
    ]
    first = service.score_bundles(plans, max_request_items=6)

    assert len(http.posts) == 1
    assert len(http.posts[0]["opportunities"]) == 6
    assert all(bundle["status"] == "available" for bundle in first.values())
    assert all(len(bundle["horizons"]) == 3 for bundle in first.values())
    assert first[plans[0]["ui_key"]]["display_horizon_days"] == 90
    assert first[plans[0]["ui_key"]]["ml_score"] == 30.0

    second = service.score_bundles(plans, max_request_items=6)
    assert len(http.posts) == 1
    assert second == first


def test_usage_registry_is_full_identity_default_first_then_view_count():
    redis_client = FakeRedis()
    default_body = {
        "table_context": {
            "years": "10",
            "partial": {"min_winning_years": "9", "mode": "consecutive"},
            "mode": "consecutive",
            "date": "2026-08-05",
        },
        "opportunities": [long_opp()],
    }
    other_body = {
        "table_context": {
            "years": "20",
            "partial": {"min_winning_years": "17", "mode": "consecutive"},
            "mode": "consecutive",
            "date": "2026-08-05",
        },
        "opportunities": [long_opp("MSFT")],
    }
    default = build_usage_context("2", default_body)
    other = build_usage_context("2", other_body)
    assert default["is_default"] is True
    assert other["is_default"] is False
    record_usage_context(
        redis_client, default, market_date="2026-08-05"
    )
    for _ in range(5):
        record_usage_context(
            redis_client, other, market_date="2026-08-05"
        )

    ranked = ranked_usage_contexts(
        redis_client,
        days=1,
        limit=10,
        today=dt.date(2026, 8, 5),
    )
    assert [item["context_hash"] for item in ranked] == [
        default["context_hash"],
        other["context_hash"],
    ]
    assert ranked[1]["views"] == 5
    assert ranked[0]["opportunity_set_hash"] != ranked[1]["opportunity_set_hash"]


def test_usage_and_scorer_provenance_strip_identity_and_unknown_partial_fields():
    sentinel = "secret-user@example.test"
    body = {
        "table_context": {
            "years": "20",
            "partial": {
                "min_winning_years": "17",
                "mode": "consecutive",
                "email": sentinel,
                "selection_origin": "private-route",
                "nested": {"token": sentinel},
            },
            "mode": "consecutive",
            "date": "2026-08-05",
            "day_range": "10-367",
            "is_default": False,
            "user_id": sentinel,
            "token": sentinel,
        },
        "opportunities": [
            {
                **long_opp(),
                "partial": {
                    "min_winning_years": "17",
                    "mode": "consecutive",
                    "email": sentinel,
                    "selection_origin": "opportunity_table",
                },
                "selection_origin": "opportunity_table",
                "user_id": sentinel,
            }
        ],
    }

    detail = build_usage_context("2", body)
    serialized = json.dumps(detail, sort_keys=True)
    assert sentinel not in serialized
    assert "selection_origin" not in serialized
    assert detail["table_context"] == {
        "years": "20",
        "partial": {
            "min_winning_years": "17",
            "mode": "consecutive",
        },
        "mode": "consecutive",
        "date": "2026-08-05",
        "day_range": "10-367",
        "is_default": False,
    }
    assert detail["is_default"] is False

    plan = build_checkpoint_plan("2", body["opportunities"][0])
    scorer_request = json.dumps(plan["requests"], sort_keys=True)
    assert sentinel not in scorer_request
    assert "selection_origin" not in scorer_request
    assert plan["requests"][0]["partial"]["selection"] == {
        "min_winning_years": "17",
        "mode": "consecutive",
    }


def test_ranged_usage_records_only_rows_visible_in_the_displayed_calendar_range():
    detail = build_usage_context(
        "2",
        {
            "table_context": {
                "years": "20",
                "partial": "17",
                "mode": "consecutive",
                "date": "2026-08-05",
                "day_range": "91-150",
                "is_default": False,
            },
            # The request deliberately includes the stable baseline row as
            # well as the current ranged row. raw 90 displays as day 91.
            "opportunities": [
                long_opp("BASE", days_out=45),
                long_opp("EDGE", days_out=90),
                long_opp("TOP", days_out=149),
                long_opp("PAST", days_out=150),
            ],
        },
    )

    assert [item["symbol"] for item in detail["opportunities"]] == ["EDGE", "TOP"]


def test_tara_bundle_keeps_per_horizon_unavailable_reason():
    plan = build_analysis_score_plan(
        {
            "symbol": "AAPL",
            "start_date": "2026-08-10",
            "days_out": "150",
            "direction": "long",
        },
        today=dt.date(2026, 8, 5),
    )
    context = finalize_analysis_checkpoint_bundle(
        plan,
        {
            "status": "partial",
            "horizons": [
                {
                    "status": "available",
                    "calendar_days": 30,
                    "ml_score": 70,
                    "win_prob": 0.7,
                    "pred_return": 3,
                    "pred_mfe": 5,
                },
                {
                    "status": "unavailable",
                    "calendar_days": 60,
                    "error": {
                        "code": "vix_blocked",
                        "message": "Volatility safety gate is active.",
                    },
                },
                {
                    "status": "available",
                    "calendar_days": 90,
                    "ml_score": 75,
                    "win_prob": 0.72,
                    "pred_return": 5,
                    "pred_mfe": 8,
                },
            ],
        },
    )

    assert context["status"] == "available"
    assert context["basis"] == "duration_comparison"
    assert context["checkpoint_status"] == "partial"
    assert context["horizons"][1] == {
        "calendar_days": 60,
        "status": "unavailable",
        "error_code": "vix_blocked",
        "unavailable_reason": "Volatility safety gate is active.",
    }

    line = _analysis_ai_context_line({}, {"ai_analysis": context})
    assert "60 days" in line
    assert "volatility safety gate" in line
    assert "missing values as zero" not in line
