"""New York market-clock helpers shared by daily-pick result jobs."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
RESULT_FINALIZATION_TIME = dt.time(16, 20)


def new_york_now() -> dt.datetime:
    return dt.datetime.now(NEW_YORK)


def session_bar_is_final(
    session_date: str | dt.date,
    now: dt.datetime | None = None,
) -> bool:
    """Return whether a US-session daily bar is safe to treat as final."""
    if isinstance(session_date, str):
        session_date = dt.date.fromisoformat(session_date)
    now = now or new_york_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=NEW_YORK)
    local_now = now.astimezone(NEW_YORK)
    if session_date < local_now.date():
        return True
    return (
        session_date == local_now.date()
        and local_now.time().replace(tzinfo=None) >= RESULT_FINALIZATION_TIME
    )
