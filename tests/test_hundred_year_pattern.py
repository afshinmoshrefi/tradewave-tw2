"""Contracts for the one-pattern public exhibit and Tara's deterministic command."""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver"
if str(APPSERVER) not in sys.path:
    sys.path.insert(0, str(APPSERVER))

from featured_patterns import (  # noqa: E402
    hundred_year_completed_count,
    hundred_year_completed_year_bounds,
    hundred_year_end_date,
    hundred_year_view_spec,
    hundred_year_years_value,
    is_hundred_year_chart_request,
    is_hundred_year_view_spec,
)
from tara_answer_planner import (  # noqa: E402
    build_hundred_year_pattern_command,
    is_hundred_year_pattern_question,
)


BEFORE_START = datetime.date(2026, 8, 2)


def test_signature_calendar_and_completed_cohort_are_exact():
    start = datetime.date(2026, 9, 27)

    assert hundred_year_end_date(start) == datetime.date(2027, 7, 18)
    assert hundred_year_completed_count(BEFORE_START) == 24
    assert hundred_year_completed_year_bounds(BEFORE_START) == (1930, 2022)
    assert hundred_year_years_value(BEFORE_START) == "pe2-24"
    assert hundred_year_view_spec(BEFORE_START) == {
        "market": "5",
        "symbol": "SPX",
        "entry_date": "2026-09-27",
        "days_out": 295,
        "years": 24,
        "pe_cycle": "pe2",
    }


def test_exact_chart_request_is_the_only_public_gate_bypass():
    exact = {
        "resource_id": "5",
        "date": "2026-09-27",
        "symbol": "SPX",
        "days_out": "294",
        "years": "pe2-24",
        "cut_off_year": 0,
    }
    assert is_hundred_year_chart_request(**exact, today=BEFORE_START)

    near_misses = (
        {"resource_id": "6"},
        {"date": "2026-09-28"},
        {"symbol": "SPY"},
        {"days_out": "295"},
        {"years": "pe2-23"},
        {"years": "24"},
        {"cut_off_year": 1930},
    )
    for changed in near_misses:
        request = {**exact, **changed}
        assert not is_hundred_year_chart_request(**request, today=BEFORE_START)


def test_browser_spec_requires_every_signature_field():
    exact = hundred_year_view_spec(BEFORE_START)
    assert is_hundred_year_view_spec(exact, today=BEFORE_START)

    for field, value in (
        ("market", "2"),
        ("symbol", "SPY"),
        ("entry_date", "2026-09-26"),
        ("days_out", 294),
        ("years", 23),
        ("pe_cycle", "cons"),
        ("trim_year", 1930),
    ):
        assert not is_hundred_year_view_spec(
            {**exact, field: value}, today=BEFORE_START
        )


@pytest.mark.parametrize(
    "message",
    (
        "show me the 100 year pattern",
        "Load The 100-Year Pattern",
        "what is the hundred-year pattern?",
        "the pattern from the book",
        "pattern in my book",
        "show me the pattern from your book",
        "open the book pattern",
        "explain Afshin's signature pattern",
    ),
)
def test_tara_recognizes_title_and_book_phrases(message):
    assert is_hundred_year_pattern_question(message)


@pytest.mark.parametrize(
    "message",
    (
        "show me a 100 day pattern",
        "what is a seasonal pattern?",
        "load SPX for September",
        "tell me about Afshin",
    ),
)
def test_tara_does_not_steal_nearby_questions(message):
    assert not is_hundred_year_pattern_question(message)


def test_tara_loads_and_explains_the_upcoming_2026_row():
    command = build_hundred_year_pattern_command(
        "show me the pattern from your book", today=BEFORE_START
    )

    assert command["spec"] == hundred_year_view_spec(BEFORE_START)
    reply = command["reply"]
    assert "Loaded The 100-Year Pattern" in reply
    assert "September 27 through July 18" in reply
    assert "295 calendar days, with the entry date counted as day 1" in reply
    assert "n=24 observations with entry years 1930-2022" in reply
    assert "23 of 24 PE+2 observations were profitable (96%)" in reply
    assert "averaging +18.8%" in reply
    assert "1930 was the one losing observation" in reply
    assert "2026 is upcoming" in reply
    assert "excluded from the completed n=24" in reply

    plain_reply = re.sub(r"<[^>]*>", "", reply)
    assert "Loaded The 100-Year Pattern SPX long" in plain_reply
    assert "What the bars show One bar" in plain_reply
    assert "Historical result 23 of 24" in plain_reply
    assert "Current row 2026 is upcoming" in plain_reply
    assert "Book This is the pattern" in plain_reply


def test_tara_labels_active_row_partial_and_keeps_completed_n_24():
    active = datetime.date(2026, 10, 1)
    command = build_hundred_year_pattern_command("the 100-year pattern", today=active)

    assert command["spec"]["years"] == 24
    assert "active on calendar day 5 of 295" in command["reply"]
    assert "partial row" in command["reply"]
    assert "excluded from the completed n=24" in command["reply"]


def test_completed_2026_occurrence_becomes_observation_25():
    after_end = datetime.date(2027, 7, 19)
    command = build_hundred_year_pattern_command("load the 100 year pattern", today=after_end)

    assert command["spec"]["entry_date"] == "2026-09-27"
    assert command["spec"]["years"] == 25
    assert hundred_year_years_value(after_end) == "pe2-25"
    assert "viewer now includes it in the completed n=25" in command["reply"]
    assert is_hundred_year_chart_request(
        "5", "2026-09-27", "SPX", "294", "pe2-25", today=after_end
    )


def test_advice_wording_adds_the_required_disclaimer_without_blocking_load():
    command = build_hundred_year_pattern_command(
        "should I trade the 100-year pattern?", today=BEFORE_START
    )

    assert command["spec"]["symbol"] == "SPX"
    assert "Past performance and model estimates do not guarantee future results" in command["reply"]
