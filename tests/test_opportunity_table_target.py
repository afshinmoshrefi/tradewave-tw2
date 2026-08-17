"""Service-only OppList4 target-date override contract."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "appserver" / "appserver" / "opportunity_table_target.py"
SPEC = importlib.util.spec_from_file_location("opportunity_table_target_test", HELPER_PATH)
target_helper = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(target_helper)


def _ny(year, month, day, hour=12):
    return dt.datetime(
        year,
        month,
        day,
        hour,
        tzinfo=target_helper.NY_TZ,
    )


def test_normal_browser_call_keeps_current_year_without_override():
    assert target_helper.resolve_opportunity_table_date(
        month="august",
        day="6",
        requested_target_date=None,
        is_service_account=False,
        now=_ny(2026, 8, 6),
    ) == dt.date(2026, 8, 6)


def test_service_override_supports_december_to_january_year_rollover():
    result = target_helper.resolve_opportunity_table_date(
        month="January",
        day="1",
        requested_target_date="2027-01-01",
        is_service_account=True,
        now=_ny(2026, 12, 31, 23),
    )

    assert result == dt.date(2027, 1, 1)
    assert result.year % 4 == 3


def test_weekend_or_holiday_target_remains_a_literal_calendar_date():
    # Thanksgiving is not shifted to Friday. TradeWave table dates are calendar
    # dates even though the table engine may consolidate adjacent rows.
    assert target_helper.resolve_opportunity_table_date(
        month="November",
        day="26",
        requested_target_date="2026-11-26",
        is_service_account=True,
        now=_ny(2026, 11, 25, 23),
    ) == dt.date(2026, 11, 26)


@pytest.mark.parametrize(
    ("requested", "is_service", "month", "day", "expected_code", "status"),
    [
        (
            "2026-08-07",
            False,
            "August",
            "7",
            "target_date_requires_service_account",
            403,
        ),
        (
            "2026-08-08",
            True,
            "August",
            "8",
            "target_date_out_of_range",
            400,
        ),
        (
            "2026-08-07",
            True,
            "August",
            "6",
            "target_date_route_mismatch",
            400,
        ),
        (
            "08/07/2026",
            True,
            "August",
            "7",
            "invalid_target_date",
            400,
        ),
    ],
)
def test_target_override_rejects_unauthorized_or_ambiguous_requests(
    requested, is_service, month, day, expected_code, status
):
    with pytest.raises(target_helper.OpportunityTableTargetError) as error:
        target_helper.resolve_opportunity_table_date(
            month=month,
            day=day,
            requested_target_date=requested,
            is_service_account=is_service,
            now=_ny(2026, 8, 6, 12),
        )

    assert error.value.code == expected_code
    assert error.value.status_code == status


def test_opplist_route_uses_resolved_year_phase_and_isolated_override_cache():
    source = (ROOT / "appserver" / "appserver" / "appserver.py").read_text(
        encoding="utf-8"
    )

    assert "requested_target_date = request.args.get(\"target_date\")" in source
    assert "is_service_account=data.get('is_service_account') is True" in source
    assert "current_year = table_date.year" in source
    assert "pe_phase = current_year % 4" in source
    assert 'redis_suffix += f"_TARGET{current_year}"' in source
