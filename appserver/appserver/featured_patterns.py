"""Canonical definitions for narrowly public TradeWave signature patterns.

The 100-Year Pattern is intentionally a single public exhibit, not an indices-market
entitlement. Keep its identity checks exact: changing any defining field produces a
different pattern and must fall back to the caller's normal subscription rules.
"""

from __future__ import annotations

import datetime as _datetime
from typing import Any, Mapping, Optional


HUNDRED_YEAR_PATTERN_ID = "hundred_year_pattern"
HUNDRED_YEAR_MARKET = "5"
HUNDRED_YEAR_SYMBOL = "SPX"
HUNDRED_YEAR_PE_CYCLE = "pe2"
HUNDRED_YEAR_START_MONTH = 9
HUNDRED_YEAR_START_DAY = 27
HUNDRED_YEAR_DISPLAY_DAYS = 295
HUNDRED_YEAR_ENGINE_DAYS = HUNDRED_YEAR_DISPLAY_DAYS - 1
HUNDRED_YEAR_FIRST_COMPLETED_YEAR = 1930


def _as_date(value: Optional[_datetime.date] = None) -> _datetime.date:
    if isinstance(value, _datetime.datetime):
        return value.date()
    return value if isinstance(value, _datetime.date) else _datetime.date.today()


def hundred_year_end_date(start: _datetime.date) -> _datetime.date:
    """Return the inclusive end date; entry day is calendar day 1."""

    return start + _datetime.timedelta(days=HUNDRED_YEAR_DISPLAY_DAYS - 1)


def hundred_year_occurrence_start(
    today: Optional[_datetime.date] = None,
) -> _datetime.date:
    """Return the current/latest PE+2 occurrence used by the signature view.

    In a PE+2 calendar year the September occurrence is used before it starts and
    while it is active. In intervening years the most recently started occurrence
    remains the book record until the next PE+2 calendar year arrives.
    """

    current = _as_date(today)
    year = current.year - ((current.year - 2) % 4)
    return _datetime.date(year, HUNDRED_YEAR_START_MONTH, HUNDRED_YEAR_START_DAY)


def hundred_year_occurrence_status(
    today: Optional[_datetime.date] = None,
) -> str:
    current = _as_date(today)
    start = hundred_year_occurrence_start(current)
    end = hundred_year_end_date(start)
    if current < start:
        return "upcoming"
    if current <= end:
        return "active"
    return "completed"


def hundred_year_completed_count(
    today: Optional[_datetime.date] = None,
) -> int:
    """Count completed PE+2 observations beginning with the 1930 entry year."""

    current = _as_date(today)
    candidate = current.year - ((current.year - 2) % 4)
    while hundred_year_end_date(
        _datetime.date(candidate, HUNDRED_YEAR_START_MONTH, HUNDRED_YEAR_START_DAY)
    ) >= current:
        candidate -= 4
    if candidate < HUNDRED_YEAR_FIRST_COMPLETED_YEAR:
        return 0
    return ((candidate - HUNDRED_YEAR_FIRST_COMPLETED_YEAR) // 4) + 1


def hundred_year_completed_year_bounds(
    today: Optional[_datetime.date] = None,
) -> tuple[Optional[int], Optional[int]]:
    count = hundred_year_completed_count(today)
    if count <= 0:
        return None, None
    last = HUNDRED_YEAR_FIRST_COMPLETED_YEAR + 4 * (count - 1)
    return HUNDRED_YEAR_FIRST_COMPLETED_YEAR, last


def hundred_year_years_value(today: Optional[_datetime.date] = None) -> str:
    """Canonical ChartData4 ``years`` string. Never coerce this transport to int."""

    return f"{HUNDRED_YEAR_PE_CYCLE}-{hundred_year_completed_count(today)}"


def hundred_year_view_spec(today: Optional[_datetime.date] = None) -> dict[str, Any]:
    """Return the browser-facing ViewSpec using inclusive display-day semantics."""

    current = _as_date(today)
    return {
        "market": HUNDRED_YEAR_MARKET,
        "symbol": HUNDRED_YEAR_SYMBOL,
        "entry_date": hundred_year_occurrence_start(current).isoformat(),
        "days_out": HUNDRED_YEAR_DISPLAY_DAYS,
        "years": hundred_year_completed_count(current),
        "pe_cycle": HUNDRED_YEAR_PE_CYCLE,
    }


def is_hundred_year_view_spec(
    spec: Any,
    *,
    today: Optional[_datetime.date] = None,
) -> bool:
    """Whether a browser-facing spec is exactly the public signature view."""

    if not isinstance(spec, Mapping):
        return False
    expected = hundred_year_view_spec(today)
    try:
        days = int(spec.get("days_out"))
        years = int(spec.get("years"))
        trim_year = int(spec.get("trim_year", 0) or 0)
    except (TypeError, ValueError):
        return False
    return (
        str(spec.get("market") or "") == expected["market"]
        and str(spec.get("symbol") or "").strip().upper() == expected["symbol"]
        and str(spec.get("entry_date") or "") == expected["entry_date"]
        and days == expected["days_out"]
        and years == expected["years"]
        and str(spec.get("pe_cycle") or "").strip().lower()
        == expected["pe_cycle"]
        and trim_year == 0
    )


def is_hundred_year_chart_request(
    resource_id: Any,
    date: Any,
    symbol: Any,
    days_out: Any,
    years: Any,
    cut_off_year: Any = 0,
    *,
    today: Optional[_datetime.date] = None,
) -> bool:
    """Whether a ChartData4 request may bypass only the normal market/year gate."""

    expected = hundred_year_view_spec(today)
    try:
        engine_days = int(str(days_out))
        trim_year = int(str(cut_off_year))
    except (TypeError, ValueError):
        return False
    return (
        str(resource_id) == expected["market"]
        and str(symbol or "").strip().upper() == expected["symbol"]
        and str(date or "") == expected["entry_date"]
        and engine_days == HUNDRED_YEAR_ENGINE_DAYS
        and str(years or "").strip().lower() == hundred_year_years_value(today)
        and trim_year == 0
    )
