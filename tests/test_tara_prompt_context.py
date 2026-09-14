"""Regression coverage for Tara's prompt segmentation and context minimization."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver"
sys.path.insert(0, str(APPSERVER))

from tara_prompt_context import (  # noqa: E402
    MAX_TOPIC_KNOWLEDGE_CHARS,
    allowlisted_prompt_stats,
    needs_opportunity_rows,
    needs_yearly_results,
    parse_knowledge_sections,
    prompt_segment_sizes,
    segmented_system_blocks,
    select_topic_knowledge,
)


def _sections():
    knowledge = (APPSERVER / "chatbot_knowledge.txt").read_text(encoding="utf-8")
    return knowledge, parse_knowledge_sections(knowledge)


def test_topic_router_loads_only_relevant_complete_kb_sections():
    full_knowledge, sections = _sections()
    selection = select_topic_knowledge("How does the Sharpe ratio work?", sections)

    assert "What Makes a Strong Pattern" in selection.headings
    assert "Key Concepts and Definitions" in selection.headings
    assert "## What Makes a Strong Pattern" in selection.text
    assert "## Subscription Tiers" not in selection.text
    assert "## Seasonal Projection on Price Chart" not in selection.text
    assert "mostly red/down for short setups" in selection.text
    assert "Bars are mostly green with" not in selection.text
    assert "0.5 to 1.0 = moderate" in selection.text
    assert "risk-free rate prorated" in selection.text
    assert len(selection.text) <= MAX_TOPIC_KNOWLEDGE_CHARS + 200
    assert len(selection.text) < len(full_knowledge) * 0.1


def test_projection_and_pricing_questions_do_not_load_each_others_knowledge():
    _, sections = _sections()
    projection = select_topic_knowledge("What is the purple dashed projection?", sections)
    pricing = select_topic_knowledge("Is TradeWave free?", sections)

    assert projection.headings[0] == "Seasonal Projection on Price Chart"
    assert "Subscription Tiers" not in projection.headings
    assert pricing.headings == ("Subscription Tiers",)
    assert "Seasonal Projection on Price Chart" not in pricing.headings


def test_core_seasonality_definition_routes_to_general_facts_not_named_pattern():
    _, sections = _sections()
    selection = select_topic_knowledge("What is a seasonal pattern?", sections)

    assert selection.headings == ("What is TradeWave", "Key Concepts and Definitions")
    assert "The 100-Year Pattern" not in selection.headings


def test_mcp_questions_load_only_the_new_connected_ai_knowledge():
    _, sections = _sections()

    definition = select_topic_knowledge("What is TradeWave MCP?", sections)
    comparison = select_topic_knowledge(
        "Do I need seasonality now that I have ChatGPT and Claude?", sections
    )

    assert definition.headings == ("TradeWave in ChatGPT and Claude (MCP)",)
    assert comparison.headings[0] == "TradeWave in ChatGPT and Claude (MCP)"
    assert "MCP is a secure connection" in comparison.text
    assert "An AI assistant without a TradeWave connection" in comparison.text
    assert "## Subscription Tiers" not in comparison.text
    assert select_topic_knowledge("Is Tara using Claude?", sections).headings == ()


def test_tooltip_questions_load_the_small_guidance_section():
    _, sections = _sections()

    selection = select_topic_knowledge("Where is the tooltip toggle?", sections)

    assert selection.headings == ("Guidance Tooltips",)
    assert "upper-left toolbar" in selection.text
    assert "show_tooltips=true" in selection.text
    assert "## TradeWave UI Map" not in selection.text


def test_ai_scores_ui_knowledge_describes_conditional_fourth_window_and_long_horizons():
    _, sections = _sections()

    selection = select_topic_knowledge("What is the fourth window?", sections)

    assert selection.headings[0] == "AI Scores (AIS, Win%, PredR, PMFE)"
    assert "a fourth window appears between Wave Stats and Price Chart" in selection.text
    assert "AI Scores window and dot do not appear at all" in selection.text
    assert "source longer than 90 calendar days" in selection.text
    assert "30-, 60-, and 90-day model readings" in selection.text
    assert "Opportunity Table uses 90 days" in selection.text
    assert "original pattern's Wave Stats" in selection.text
    assert "complete source pattern" in selection.text
    assert "historical record recalculated for that checkpoint" in selection.text


def test_ai_columns_start_hidden_and_can_be_enabled_in_settings():
    _, sections = _sections()

    selection = select_topic_knowledge(
        "How do I add the AI score columns in Settings?", sections
    )

    assert selection.headings == (
        "AI Scores (AIS, Win%, PredR, PMFE)",
        "Settings Window",
    )
    assert "The Opportunity Table's four AI columns start hidden" in selection.text
    assert 'Settings under "AI Scores in Opportunity Table"' in selection.text
    assert "Hiding those columns does not hide the AI Scores window" in selection.text
    assert "AIS, Win%, PredR, and PMFE" in selection.text


def test_sort_by_can_use_an_available_hidden_column_without_showing_it():
    _, sections = _sections()

    selection = select_topic_knowledge(
        "Can I sort by AI Win% while that column is hidden?", sections
    )

    assert "The Opportunity Table (Left Panel)" in selection.headings
    assert "visible Sort by control is independent of column visibility" in selection.text
    assert "sorted by AI Win% while all AI columns remain hidden" in selection.text
    assert "without showing that column or widening the table" in selection.text


def test_left_panel_collapse_knowledge_explains_restore_controls():
    _, sections = _sections()

    selection = select_topic_knowledge(
        "How do I collapse and reopen the left side?", sections
    )

    assert selection.headings == ("Desktop Left Panel Collapse",)
    assert "hides that entire side panel" in selection.text
    assert "right-chevron reopens the Opportunity Table and Tara" in selection.text
    assert "Tara button reopens the side panel and opens Tara" in selection.text
    assert "remembers the collapsed or open choice" in selection.text
    assert "different from the Opportunity Table's Expand control" in selection.text


def test_left_panel_restore_wording_routes_to_collapse_knowledge():
    _, sections = _sections()

    for message in (
        "How do I open the left side?",
        "How do I bring back the left panel?",
        "Where did the Opportunity Table go?",
    ):
        selection = select_topic_knowledge(message, sections)
        assert "Desktop Left Panel Collapse" in selection.headings


def test_plain_ai_window_wording_routes_to_ai_knowledge():
    _, sections = _sections()

    for message in (
        "Where is the AI window?",
        "Why is the AI panel missing?",
        "Why is there no AI window for forex?",
    ):
        selection = select_topic_knowledge(message, sections)
        assert "AI Scores (AIS, Win%, PredR, PMFE)" in selection.headings
        assert "supported US stock or ETF" in selection.text


def test_ai_market_scope_routes_generic_scoring_question_to_exact_eligibility():
    _, sections = _sections()

    selection = select_topic_knowledge(
        "Does TradeWave score futures, commodities, forex, or crypto?", sections
    )

    assert selection.headings == (
        "AI Scores (AIS, Win%, PredR, PMFE)",
        "Securities Groups (Markets) Explained",
    )
    assert "AI scores are available for supported US stocks and ETFs only" in selection.text
    assert "futures and commodities, forex, crypto" in selection.text
    assert "AI Scores target supported US stocks and ETFs only" in selection.text
    assert "do not get an AI Scores window, AI navigation dot, or AI scoring columns" in selection.text


def test_trend_arrow_question_loads_the_change_and_alignment_contract():
    _, sections = _sections()

    selection = select_topic_knowledge(
        "What is the red arrow next to Trend Long?", sections
    )

    assert "Trend Long / Trend Short Scores (TL / TS columns in Opportunity Table)" in selection.headings
    assert "Trend Alignment (Wave Info Panel)" in selection.headings
    assert "Red down arrow" in selection.text
    assert "score level determines alignment" in selection.text
    assert "red down arrow can therefore sit beside an Aligned score" in selection.text


def test_large_row_context_is_loaded_only_when_the_question_needs_it():
    _, sections = _sections()
    assert not needs_yearly_results("Explain Sharpe ratio")
    assert needs_yearly_results("How did this pattern do in 2022?")
    assert needs_yearly_results("What was its worst year?")
    assert not needs_yearly_results("What is standard deviation?")
    assert not needs_yearly_results("Explain MAE")
    assert needs_yearly_results("What was this pattern's MAE?")
    assert needs_yearly_results("what about max and min for each year")
    assert needs_yearly_results("show the highs and lows year by year")
    assert not needs_yearly_results("what are the maximum hold days and minimum win rate?")
    assert select_topic_knowledge("How did this pattern do in 2022?", sections).headings == ()
    assert not needs_opportunity_rows("Analyze this loaded pattern")
    assert not needs_opportunity_rows("What is the opportunity table?")
    assert needs_opportunity_rows("What are the top opportunities in my table?")
    assert needs_opportunity_rows("Why is PEG ranked here?")
    assert needs_opportunity_rows("load the 3rd one on the list")


def test_prompt_stats_exclude_raw_prices_volumes_and_large_nested_data():
    stats = {
        "Percent Profitable": "82%",
        "Avg Profit - All": "2%",
        "Sharpe Ratio": "0.82",
        "Trend Score Available": False,
        "52W High": 99.25,
        "52W Low": 42.10,
        "SMA 50": 75.4,
        "Avg Volume 20d": 123456,
        "last_trade_date": "2026-07-31",
        "earnings_filings": [{"date": "2026-07-20", "form": "10-Q"}],
        "next_earnings_est": "2026-10-20",
    }
    selected = dict(allowlisted_prompt_stats(stats))

    assert selected["Percent Profitable"] == "82%"
    assert selected["Sharpe Ratio"] == "0.82"
    assert selected["Trend Score Available"] == "False"
    assert selected["next_earnings_est"] == "2026-10-20"
    assert "52W High" not in selected
    assert "SMA 50" not in selected
    assert "Avg Volume 20d" not in selected
    assert "earnings_filings" not in selected


def test_only_stable_prefix_has_a_cache_breakpoint():
    blocks = segmented_system_blocks("stable rules", "topic facts", "live pattern")

    assert prompt_segment_sizes(blocks) == (12, 11, 12)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in blocks[1]
    assert "cache_control" not in blocks[2]


# ---------------------------------------------------------------------------
# Direction-flip detection (release defect TW-R14-01).
#
# Direction is DETERMINED from the win/loss split and the viewer has no long/short
# control, so these turns get a deterministic what-if answer. People phrase the ask many
# ways, so this suite is the coverage contract: a first regex matched only 9 of 31
# realistic phrasings. Add a phrasing here before widening the pattern.
# ---------------------------------------------------------------------------

DIRECTION_FLIP_PHRASINGS = [
    "Switch this exact pattern from long to short. Keep all other settings",
    "flip it to short",
    "change the direction",
    "reverse the direction",
    "swap the direction please",
    "show me the short side",
    "what does this look like on the short side?",
    "can you analyze this as a short",
    "could we look at it as a short?",
    "turn this into a long",
    "what if I shorted this instead?",
    "shorting this",
    "I shorted it",
    "how would this do if I sold it short?",
    "can I trade this the other way?",
    "show me the opposite direction",
    "what about going the other way?",
    "how about the other direction",
    "go the other way on this one",
    "I want to short this",
    "short it instead",
    "short this pattern instead",
    "this but short",
    "what if I go short here",
    "what if I bet against it?",
    "can you show the bearish version?",
    "make it bearish",
    "show this bearish",
    "run this as a short trade",
    "what would shorting this have returned?",
    "is there a short version of this pattern?",
    "invert this pattern",
    "opposite side please",
    "flip the trade",
    "reverse it",
    "what if the trade was reversed?",
    "what happens if I sell this instead of buying?",
    "what if I bought it instead of selling?",
]

NOT_DIRECTION_FLIP_PHRASINGS = [
    # screening for setups that ALREADY determine that way is an ordinary scan
    "find me short setups in energy",
    "what are the best short patterns",
    "which stocks have short opportunities",
    # definitions and "why is it labelled that" are answered elsewhere
    "what is a short trade",
    "what does short mean?",
    "why is this pattern short?",
    # DURATION, not direction. "shorten/shortened/shorter" are different words from
    # "short/shorted", and word boundaries keep them apart - but they read alike to a
    # human, so the whole family is pinned here.
    "show me a shorter duration",
    "can you make the window shorter?",
    "what if I shortened this instead?",
    "can you shorten this?",
    "make it shorter",
    "shorten the window",
    "shortened the pattern",
    "I want a shorter hold",
    "can we shorten the date range?",
    "make this a shorter trade",
    "shorten it to 10 days",
    "what if the window were shortened?",
    # TradeWave's Reverse Date Range is a different feature
    "reverse the date range",
    "use the reverse date range",
    "change the dates",
    # ordinary view commands
    "analyze this pattern",
    "change years to 20",
    "load AAPL",
    "switch to PE+2",
    "change the market to NASDAQ",
    "flip to the price chart tab",
    "switch to the trend chart",
    "show me the wave stats",
    "what is MFE?",
    "how did it do in 2019?",
]


def test_direction_flip_detector_covers_natural_phrasings():
    from tara_prompt_context import is_direction_flip_request

    missed = [t for t in DIRECTION_FLIP_PHRASINGS if not is_direction_flip_request(t)]
    assert not missed, "direction-flip phrasings not detected: %r" % missed


def test_direction_flip_detector_ignores_scans_definitions_and_view_commands():
    from tara_prompt_context import is_direction_flip_request

    wrong = [t for t in NOT_DIRECTION_FLIP_PHRASINGS if is_direction_flip_request(t)]
    assert not wrong, "wrongly treated as a direction flip: %r" % wrong


def test_exclude_current_range_menu_label_selects_its_knowledge_section():
    """The Analysis menu says "Exclude Current Range"; "Reverse Date Range" is only the
    legacy internal name (kept as the ViewSpec value in Common.js:559 and as the KB
    heading). Users type what the menu shows, so the router must accept both or the
    section silently never loads."""
    import tara_prompt_context as tpc

    for question in (
        "what does exclude current range do?",
        "how do I exclude the current range",
        "exclude this date range",
        "show me the exclusion report",
        "reverse date range",
    ):
        hits = [h for rx, h in tpc._TOPIC_ROUTES if rx.search(question)]
        assert any("Reverse Date Range" in h for h in hits), question


# Every label a user can actually SEE and click must resolve to a knowledge section.
# An unrouted label is a silent failure: nothing errors, Tara just answers from general
# reasoning with none of the product facts. Found 2026-09-14 - the whole Analysis menu
# was unrouted, and "what is Buy and Hold?" fell through to the lexical fallback, which
# selected the unrelated MCP section and then short-circuited every other section.
VISIBLE_UI_LABELS = {
    "Compare Symbols": "Interactive Analysis Reports",
    "Compare Date Ranges": "Interactive Analysis Reports",
    "Buy & Hold": "Interactive Analysis Reports",
    "Exclude Current Range": "Reverse Date Range",
    "Year to Date": "Months & Qtrs (Time Grouping)",
    "Today to Year End": "Months & Qtrs (Time Grouping)",
    "Months & Qtrs": "Months & Qtrs (Time Grouping)",
    "Best Waves": "Best Waves Selector (Desktop Only)",
    "Portfolio Manager": "Portfolio Manager (Popup Window)",
}


def test_every_visible_ui_label_loads_its_knowledge_section():
    import tara_prompt_context as tpc

    sections = tpc.parse_knowledge_sections(
        (APPSERVER / "chatbot_knowledge.txt").read_text(encoding="utf-8")
    )

    broken = {}
    for label, expected in VISIBLE_UI_LABELS.items():
        headings = tpc.select_topic_knowledge(
            "what does %s do?" % label, sections
        ).headings
        if expected not in headings:
            broken[label] = headings
    assert not broken, "UI labels that do not load their section: %r" % broken


def test_buy_and_hold_never_falls_through_to_the_mcp_section():
    """The MCP section short-circuits selection, so a wrong match there starves the turn."""
    import tara_prompt_context as tpc

    sections = tpc.parse_knowledge_sections(
        (APPSERVER / "chatbot_knowledge.txt").read_text(encoding="utf-8")
    )

    for question in ("what is Buy and Hold?", "what is buy & hold", "explain buy-and-hold"):
        headings = tpc.select_topic_knowledge(question, sections).headings
        assert "TradeWave in ChatGPT and Claude (MCP)" not in headings, question
