from datetime import datetime

import pytest

from webinar_schedule import EASTERN, get_upcoming_webinars, parse_webinar_datetime, public_sessions


pytestmark = pytest.mark.unit


def _row(date, time="2:00 PM", webinar_id="wb001"):
    return {
        "Webinar ID": webinar_id,
        "Date": date,
        "Time": time,
        "Title": "TradeWave Live",
        "Description": "A live walkthrough.",
        "Webinar Link": "https://zoom.example/private",
    }


def test_parse_sheet_datetime_is_eastern_and_portable():
    parsed = parse_webinar_datetime("2026-07-22T00:00:00.000Z", "1899-12-30T18:30:00.000Z")
    assert parsed == datetime(2026, 7, 22, 18, 30, tzinfo=EASTERN)


def test_upcoming_filter_sorts_and_excludes_past_or_other_ids():
    now = datetime(2026, 7, 19, 12, 0, tzinfo=EASTERN)
    sessions = get_upcoming_webinars([
        _row("2026-07-25", "3:00 PM"),
        _row("2026-07-18", "3:00 PM"),
        _row("2026-07-22", "2:00 PM"),
        _row("2026-07-23", "2:00 PM", webinar_id="wb999"),
    ], now=now)
    assert [session["date_short"] for session in sessions] == ["2026-07-22", "2026-07-25"]
    assert sessions[0]["formatted_date"] == "July 22, 2026"
    assert sessions[0]["formatted_time"] == "2:00 PM"
    assert sessions[0]["group_name"] == "wb001_2026-07-22_0200PM"
    assert sessions[0]["datetime"].tzinfo == EASTERN


@pytest.mark.parametrize("link_field", ["Webinar Link", "zoom url"])
def test_public_feed_never_exposes_meeting_url_or_datetime_object(link_field):
    row = _row("2026-07-22")
    row[link_field] = row.pop("Webinar Link")
    sessions = get_upcoming_webinars(
        [row],
        now=datetime(2026, 7, 19, 12, 0, tzinfo=EASTERN),
    )
    public = public_sessions(sessions)
    assert "webinar_url" not in public[0]
    assert "datetime" not in public[0]


@pytest.mark.parametrize("link_fields,expected", [
    ({"zoom url": "https://zoom.example/published"}, "https://zoom.example/published"),
    ({"Webinar Link": "https://zoom.example/legacy", "zoom url": "https://zoom.example/published"}, "https://zoom.example/legacy"),
    ({"Webinar Link": "", "zoom url": "https://zoom.example/published"}, "https://zoom.example/published"),
    ({}, ""),
])
def test_published_sheet_meeting_link_mapping(link_fields, expected):
    row = _row("2026-10-09T04:00:00.000Z", "1:00 PM EST")
    row.pop("Webinar Link")
    row.update(link_fields)
    session, = get_upcoming_webinars(
        [row], now=datetime(2026, 10, 8, 9, 0, tzinfo=EASTERN),
    )
    assert session["webinar_url"] == expected
    assert session["start_iso"] == "2026-10-09T13:00:00-04:00"
