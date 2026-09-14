"""Analysis-menu requests Tara cannot perform (owner decision, 2026-09-14).

Tara's ViewSpec vocabulary has no action that opens a dialog, so "Open Compare Symbols."
classified as a view command she could not satisfy and the protocol guard replaced her
answer with "I couldn't send the complete chart action". She now points at the menu, the
same way a documented UI gap is already handled for the lower-panel slides.

The hard constraint: comparing symbols is a WORKING capability with its own contract, so
the pointer must never swallow a real comparison question.
"""

import sys
from pathlib import Path

APPSERVER = Path(__file__).resolve().parents[1] / "appserver" / "appserver"
sys.path.insert(0, str(APPSERVER))

from tara_answer_planner import build_analysis_menu_reply  # noqa: E402


MENU_REQUESTS = [
    "Open Compare Symbols.",
    "open the compare symbols dialog",
    "where is compare symbols",
    "how do I find compare symbols",
    "launch compare date ranges",
    "where do i find exclude current range",
    "open the exclusion report",
    "What can I do in the Analysis menu?",
]

COMPARISON_QUESTIONS = [
    "compare AAPL and MSFT",
    "which is better, AAPL or MSFT?",
    "compare AAPL vs MSFT",
    "compare this to the S&P",
    "compare NVDA, AMD and INTC over 20 years",
    "compare symbols AAPL MSFT",
    "analyze this pattern",
    "load AAPL",
    "what is MFE?",
    "show me the short side",
]


def test_menu_requests_get_a_pointer_instead_of_an_error():
    missed = [q for q in MENU_REQUESTS if not build_analysis_menu_reply(q)]
    assert not missed, missed


def test_comparison_questions_are_never_redirected():
    """Redirecting these would break a working feature, which is worse than the bug."""
    wrong = [q for q in COMPARISON_QUESTIONS if build_analysis_menu_reply(q)]
    assert not wrong, wrong


def test_the_pointer_names_the_menu_and_admits_the_limit():
    reply = build_analysis_menu_reply("Open Compare Symbols.")
    assert "Analysis menu" in reply
    assert "cannot open" in reply
    # It must still offer what Tara CAN do, so the user is not simply turned away.
    assert "compare two or three symbols right here in chat" in reply


def test_the_menu_overview_lists_every_action():
    reply = build_analysis_menu_reply("What can I do in the Analysis menu?")
    for label in ("Compare Symbols", "Compare Date Ranges", "Buy &amp; Hold",
                  "Exclude Current Range"):
        assert label in reply, label


def test_exclude_current_range_is_explained_not_deflected():
    """The earlier answer asked the user to run a report instead of explaining the control."""
    reply = build_analysis_menu_reply("where do i find exclude current range")
    assert "OUTSIDE your selected range" in reply
    # Invariant: the excluded dates are never described as a short trade.
    assert "not a short trade" in reply.lower()
