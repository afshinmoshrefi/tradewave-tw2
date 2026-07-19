"""Shared Google-Sheet schedule loader for TradeWave webinars.

The public page generator and the registration endpoint both use this module,
so the page and the server validate against the same future-session rules.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


DATA_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxU-EX_Wpi7Gf4kJzl2zcG62ECEpdC--raZZINnTCDCCPN-"
    "a6H2dMCIMh_6rCb8NtIWSg/exec"
)
CACHE_FILE = Path("/home/flask/site/data/webinar_data.json")
WEBINAR_ID = "wb001"
MAX_UPCOMING = 5
EASTERN = ZoneInfo("America/New_York")
_TIME_ZONE_SUFFIX = re.compile(r"\s+(?:EST|EDT|ET)$", re.IGNORECASE)


def parse_webinar_datetime(date_string: str, time_string: str) -> datetime:
    """Return a timezone-aware Eastern datetime from the Sheet display values."""
    date_part = str(date_string or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part):
        raise ValueError("invalid webinar date")

    raw_time = str(time_string or "").strip()
    if raw_time.startswith("1899-12-30T"):
        clock = raw_time.split("T", 1)[1].rstrip("Z")
        parsed_time = datetime.strptime(clock.split(".", 1)[0], "%H:%M:%S")
    else:
        clean_time = _TIME_ZONE_SUFFIX.sub("", raw_time).strip()
        parsed_time = datetime.strptime(clean_time, "%I:%M %p")

    parsed_date = datetime.strptime(date_part, "%Y-%m-%d")
    return datetime(
        parsed_date.year,
        parsed_date.month,
        parsed_date.day,
        parsed_time.hour,
        parsed_time.minute,
        tzinfo=EASTERN,
    )


def group_name_for(start: datetime, webinar_id: str = WEBINAR_ID) -> str:
    return "%s_%s_%s" % (
        webinar_id.lower(),
        start.strftime("%Y-%m-%d"),
        start.strftime("%I%M%p").upper(),
    )


def get_upcoming_webinars(data, *, now: datetime | None = None, limit: int = MAX_UPCOMING):
    """Filter the Sheet payload to future WEBINAR_ID sessions, sorted soonest first."""
    now = now or datetime.now(EASTERN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=EASTERN)
    upcoming = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("Webinar ID", "")).strip().lower() != WEBINAR_ID:
            continue
        try:
            start = parse_webinar_datetime(item.get("Date"), item.get("Time"))
        except (TypeError, ValueError):
            continue
        if start <= now:
            continue
        upcoming.append({
            "datetime": start,
            "group_name": group_name_for(start),
            "date_short": start.strftime("%Y-%m-%d"),
            "formatted_date": f"{start.strftime('%B')} {start.day}, {start.year}",
            "formatted_time": f"{int(start.strftime('%I'))}:{start.strftime('%M')} {start.strftime('%p')}",
            "start_iso": start.isoformat(),
            "title": str(item.get("Title") or item.get("Webinar Title") or "TradeWave Webinar").strip(),
            "description": str(item.get("Description") or item.get("Webinar Description") or "").strip(),
            "webinar_url": str(item.get("Webinar Link") or "").strip(),
        })
    upcoming.sort(key=lambda session: session["start_iso"])
    return upcoming[:limit]


def _read_cache():
    try:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if isinstance(cached, dict):
        cached = cached.get("data", [])
    return cached if isinstance(cached, list) else []


def _write_cache(data):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_FILE.parent / ("." + CACHE_FILE.name + ".tmp")
    temporary.write_text(
        json.dumps({"fetched_at": datetime.now(EASTERN).isoformat(), "data": data}),
        encoding="utf-8",
    )
    os.replace(temporary, CACHE_FILE)


def fetch_webinar_data(*, force_refresh: bool = False, cache_hours: int = 2):
    """Fetch the published Google Apps Script feed with a bounded cache fallback."""
    if not force_refresh and CACHE_FILE.is_file():
        age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
        if age < timedelta(hours=cache_hours).total_seconds():
            cached = _read_cache()
            if cached:
                return cached

    try:
        response = requests.get(DATA_URL, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("webinar feed must return a list")
        _write_cache(data)
        return data
    except (requests.RequestException, ValueError, TypeError):
        return _read_cache()


def public_sessions(sessions):
    """Remove private meeting URLs before writing the browser-facing JSON feed."""
    public_keys = (
        "group_name", "date_short", "formatted_date", "formatted_time",
        "start_iso", "title", "description",
    )
    return [{key: session.get(key, "") for key in public_keys} for session in sessions]
