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
