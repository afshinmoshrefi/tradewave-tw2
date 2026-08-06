"""Resolve the additive service-only date override used by the EOD warmer.

Ordinary OppList4 callers continue to select a month/day in the current New
York calendar year.  The internal warmer may additionally name today's or
tomorrow's complete ISO date so a Dec 31 run can intentionally fetch Jan 1 of
the next year without changing the public route shape.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional
from zoneinfo import ZoneInfo


NY_TZ = ZoneInfo("America/New_York")


class OpportunityTableTargetError(ValueError):
    """A stable client-facing rejection for an invalid target-date override."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _new_york_now(now: Optional[dt.datetime]) -> dt.datetime:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=NY_TZ)
    return current.astimezone(NY_TZ)


def _route_month_day(month: str, day: str, year: int) -> dt.date:
    try:
        # Match OppList4's historical ``strptime('%B')`` month parsing so the
        # additive override does not narrow ordinary callers' accepted casing.
        month_number = dt.datetime.strptime(str(month), "%B").month
        day_number = int(str(day))
        return dt.date(year, month_number, day_number)
    except (ValueError, TypeError) as exc:
        raise OpportunityTableTargetError(
            "invalid_table_date",
            "The opportunity-table month and day are invalid.",
        ) from exc


def resolve_opportunity_table_date(
    *,
    month: str,
    day: str,
    requested_target_date: Optional[str],
    is_service_account: bool,
    now: Optional[dt.datetime] = None,
) -> dt.date:
    """Return the calendar date OppList4 should read.

    ``target_date`` is deliberately additive and tightly bounded.  It is only
    accepted from a JWT minted for a service account, only for New York today
    or tomorrow, and only when its month/day agrees with the route.  No trading
    calendar adjustment is made: TradeWave table dates are calendar dates.
    """

    local_today = _new_york_now(now).date()
    route_date = _route_month_day(month, day, local_today.year)
    requested = str(requested_target_date or "").strip()
    if not requested:
        return route_date

    if is_service_account is not True:
        raise OpportunityTableTargetError(
            "target_date_requires_service_account",
            "The target_date override is restricted to internal service accounts.",
            status_code=403,
        )
    try:
        target = dt.date.fromisoformat(requested)
    except ValueError as exc:
        raise OpportunityTableTargetError(
            "invalid_target_date",
            "target_date must use YYYY-MM-DD.",
        ) from exc
    if target not in {local_today, local_today + dt.timedelta(days=1)}:
        raise OpportunityTableTargetError(
            "target_date_out_of_range",
            "target_date must be today or tomorrow in New York.",
        )
    try:
        requested_route_date = _route_month_day(month, day, target.year)
    except OpportunityTableTargetError as exc:
        raise OpportunityTableTargetError(
            "target_date_route_mismatch",
            "The route month/day must match target_date.",
        ) from exc
    if requested_route_date != target:
        raise OpportunityTableTargetError(
            "target_date_route_mismatch",
            "The route month/day must match target_date.",
        )
    return target
