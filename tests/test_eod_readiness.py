"""Deterministic EOD session, population coverage, and marker contracts."""

from __future__ import annotations

import copy
import datetime as dt

from data_updater.eod_readiness import (
    NY_TZ,
    build_status_marker,
    evaluate_eod_readiness,
    latest_completed_us_equity_session,
    target_table_date,
    terminal_row_fingerprint,
    validate_success_marker,
)


SMALL_POLICY = {
    "US": {
        "minimum_recent_coverage_ratio": 0.50,
        "minimum_completion_ratio": 0.98,
        "minimum_complete_count": 1,
    },
    "ETF": {
        "minimum_recent_coverage_ratio": 0.50,
        "minimum_completion_ratio": 0.98,
        "minimum_complete_count": 1,
    },
}


def _observation(key: str, date: str, state: str = "verified"):
    return {
        "state": state,
        "terminal_date": date,
        "terminal_row_fingerprint": terminal_row_fingerprint([key, date, 1.0]),
    }


def test_terminal_row_fingerprint_is_stable_across_csv_numeric_inference():
    assert terminal_row_fingerprint(["2026-08-05", 10, 12.5, 1000]) == (
        terminal_row_fingerprint(["2026-08-05", 10.0, "12.500", "1000.0"])
    )


def test_latest_completed_session_handles_after_midnight_and_weekday_holiday():
    # The final hourly retry can run after NY midnight; Thursday's close is
    # still the latest completed session early Friday morning.
    friday_early = NY_TZ.localize(dt.datetime(2026, 8, 7, 1, 5))
    assert latest_completed_us_equity_session(friday_early) == dt.date(2026, 8, 6)

    thursday_late = NY_TZ.localize(dt.datetime(2026, 8, 6, 23, 5))
    assert target_table_date(thursday_late) == dt.date(2026, 8, 7)
    assert target_table_date(friday_early) == dt.date(2026, 8, 7)

    # Thanksgiving is a weekday market holiday, so Wednesday remains the
    # completed session both Thursday night and early Friday.
    thanksgiving_night = NY_TZ.localize(dt.datetime(2026, 11, 26, 23, 5))
    friday_after_holiday = NY_TZ.localize(dt.datetime(2026, 11, 27, 1, 5))
    assert latest_completed_us_equity_session(thanksgiving_night) == dt.date(
        2026, 11, 25
    )
    assert latest_completed_us_equity_session(friday_after_holiday) == dt.date(
        2026, 11, 25
    )

    # Independence Day is observed Friday in 2026.
    observed_holiday = NY_TZ.localize(dt.datetime(2026, 7, 3, 23, 5))
    assert latest_completed_us_equity_session(observed_holiday) == dt.date(
        2026, 7, 2
    )


def test_partial_upstream_generation_and_single_fresh_file_fail_closed():
    targets = {
        "US": ["A", "B", "C", "D"],
        "ETF": ["SPY", "QQQ"],
    }
    observations = {
        "US:A": _observation("US:A", "2026-08-05"),
        "US:B": _observation("US:B", "2026-08-04"),
        "US:C": _observation("US:C", "2026-08-04"),
        "US:D": _observation("US:D", "2026-08-04"),
        "ETF:SPY": _observation("ETF:SPY", "2026-08-04"),
        "ETF:QQQ": _observation("ETF:QQQ", "2026-08-04"),
    }
    result = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations=observations,
        completed_session=dt.date(2026, 8, 5),
        resource_ids=["0", "1", "2", "3", "4", "11"],
        policy=SMALL_POLICY,
    )

    assert result["ready"] is False
    assert result["coverage"]["exchanges"]["US"]["complete_count"] == 1
    assert result["coverage"]["exchanges"]["US"]["recent_count"] == 4
    assert result["coverage"]["exchanges"]["US"]["completion_ratio"] == 0.25

    # Even without prior-session rows, one fresh file cannot establish broad
    # target-population coverage.
    single = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations={"US:A": observations["US:A"]},
        completed_session=dt.date(2026, 8, 5),
        resource_ids=["0", "1", "2", "3", "4", "11"],
        policy=SMALL_POLICY,
    )
    assert single["ready"] is False
    assert (
        single["coverage"]["exchanges"]["US"]["recent_coverage_ratio"]
        == 0.25
    )


def test_consistent_prior_session_generation_passes_on_weekday_holiday():
    targets = {"US": ["A", "B"], "ETF": ["SPY", "QQQ"]}
    observations = {
        f"{exchange}:{symbol}": _observation(
            f"{exchange}:{symbol}", "2026-11-25"
        )
        for exchange, symbols in targets.items()
        for symbol in symbols
    }
    result = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations=observations,
        completed_session=dt.date(2026, 11, 25),
        resource_ids=["0", "1", "2", "3", "4", "11"],
        policy=SMALL_POLICY,
    )

    assert result["ready"] is True
    assert result["coverage"]["exchanges"]["US"]["completion_ratio"] == 1.0
    assert result["coverage"]["exchanges"]["ETF"]["completion_ratio"] == 1.0


def test_success_marker_binds_generation_and_completeness_fingerprints():
    targets = {
        "US": [f"S{index:03d}" for index in range(100)],
        "ETF": [f"E{index:03d}" for index in range(25)],
    }
    observations = {
        f"{exchange}:{symbol}": _observation(
            f"{exchange}:{symbol}", "2026-08-05"
        )
        for exchange, symbols in targets.items()
        for symbol in symbols
    }
    readiness = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations=observations,
        completed_session=dt.date(2026, 8, 5),
        resource_ids=["0", "1", "2", "3", "4", "11"],
    )
    marker = build_status_marker(
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

    assert marker["ok"] is True
    assert validate_success_marker(
        marker,
        expected_market_date="2026-08-05",
        expected_target_table_date="2026-08-06",
        expected_completed_session="2026-08-05",
    )
    # At 00:05 New York the invocation date has rolled to August 6, but the
    # prior 23:05 marker remains authoritative for the same target/session.
    assert validate_success_marker(
        marker,
        expected_target_table_date="2026-08-06",
        expected_completed_session="2026-08-05",
    )

    changed_generation = copy.deepcopy(marker)
    changed_generation["generation_fingerprint"] = "0" * 64
    assert validate_success_marker(changed_generation) is False

    changed_coverage = copy.deepcopy(marker)
    changed_coverage["coverage"]["exchanges"]["US"]["complete_count"] = 99
    assert validate_success_marker(changed_coverage) is False
