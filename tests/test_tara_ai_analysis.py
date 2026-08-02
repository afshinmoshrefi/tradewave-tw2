"""Regression coverage for Tara's bounded current-condition AI context."""

import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))

from tara_ai_analysis import (  # noqa: E402
    build_analysis_score_plan,
    finalize_analysis_score_context,
)


def _wave(days="17", start="2026-08-03", direction="long"):
    return {
        "symbol": "ROST",
        "start_date": start,
        "days_out": days,
        "direction": direction,
    }


def test_like_for_like_plan_converts_calendar_label_to_engine_days_out():
    plan = build_analysis_score_plan(
        _wave(days="17"), today=datetime.date(2026, 8, 1)
    )

    assert plan["status"] == "ready"
    assert plan["mode"] == "pattern"
    assert plan["full_pattern_calendar_days"] == 17
    assert plan["opportunities"] == [
        {
            "symbol": "ROST",
            "date": "2026-08-03",
            "daysOut": 16,
            "direction": "l",
            "calendar_days": 17,
            "score_key": "ROST|16|l",
        }
    ]


def test_long_pattern_uses_30_60_90_calendar_day_checkpoints_only():
    plan = build_analysis_score_plan(
        _wave(days="180", direction="short"), today=datetime.date(2026, 8, 1)
    )

    assert plan["mode"] == "checkpoints"
    assert [item["calendar_days"] for item in plan["opportunities"]] == [30, 60, 90]
    assert [item["daysOut"] for item in plan["opportunities"]] == [29, 59, 89]
    assert {item["direction"] for item in plan["opportunities"]} == {"s"}
    assert all(item["daysOut"] != 90 for item in plan["opportunities"])


def test_ai_plan_waits_until_five_days_before_entry_and_never_backfills_after_entry():
    early = build_analysis_score_plan(
        _wave(start="2026-08-07"), today=datetime.date(2026, 8, 1)
    )
    started = build_analysis_score_plan(
        _wave(start="2026-07-31"), today=datetime.date(2026, 8, 1)
    )

    assert early == {
        "mode": "pattern",
        "full_pattern_calendar_days": 17,
        "entry_date": "2026-08-07",
        "status": "too_early",
        "days_to_entry": 6,
    }
    assert started["status"] == "after_entry"
    assert "opportunities" not in started


def test_final_context_keeps_zero_scores_and_drops_invalid_provider_values():
    plan = build_analysis_score_plan(
        _wave(days="17"), today=datetime.date(2026, 8, 1)
    )
    context = finalize_analysis_score_context(
        plan,
        {
            "ROST|16|l": {
                "ml_score": 0,
                "win_prob": 0.64,
                "pred_return": 2.15,
                "pred_mfe": float("nan"),
            }
        },
    )

    assert context == {
        "status": "available",
        "mode": "pattern",
        "full_pattern_calendar_days": 17,
        "horizons": [
            {
                "calendar_days": 17,
                "ai_score": 0.0,
                "win_probability": 0.64,
                "predicted_return_pct": 2.15,
            }
        ],
    }


def test_ready_plan_without_a_provider_result_is_unavailable_not_zero():
    plan = build_analysis_score_plan(
        _wave(days="180"), today=datetime.date(2026, 8, 1)
    )

    assert finalize_analysis_score_context(plan, {}) == {
        "status": "unavailable",
        "mode": "checkpoints",
        "full_pattern_calendar_days": 180,
    }
