"""Regression coverage for inclusive day counts and bearish bar interpretation."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver"
if str(APPSERVER) not in sys.path:
    sys.path.insert(0, str(APPSERVER))

import chatbot  # noqa: E402
import tara_answer_planner as planner  # noqa: E402


def _short_wave(*, return_key="underlying_return_pct"):
    rows = []
    for year in range(2000, 2014):
        rows.append({
            "year": year,
            return_key: -1.0,
            "mfe_pct": 2.0,
            "mae_pct": -3.0,
        })
    for year in range(2014, 2017):
        rows.append({
            "year": year,
            return_key: 1.0,
            "mfe_pct": 3.0,
            "mae_pct": -2.0,
        })
    return {
        "symbol": "PEG",
        "company": "Public Service Enterprise Group",
        "start_date": "2026-07-31",
        "days_out": "7",
        "years": "17",
        "pe_cycle": "cons",
        "direction": "short",
        "selection_origin": "scanner",
        "mfe_enabled": True,
        "mae_enabled": False,
        "stats": {
            "Num Winners": "14",
            "Num Losers": "3",
            "Percent Profitable": "82%",
            "Avg Profit": "2.51%",
            "Avg Loss": "-1.44%",
            "Sharpe Ratio": "0.82",
            "Cumulative Return": "35%",
        },
        "yearly_results": rows,
    }


def _screen(slide="price_chart"):
    return {
        "active_bottom_slide": slide,
        "price_chart_mode": "current",
        "selected_projection_visible": True,
        "full_history_projection_visible": True,
        "opportunity_table_visible": True,
        "selected_lookback": "17",
        "full_history_years": "25",
        "projection_period": "90",
        "opportunity_rows": 12,
        "selected_window_path": "supports",
        "full_history_window_path": "supports",
    }


def test_inclusive_calendar_window_ends_on_august_6():
    assert chatbot.calculate_end_date("2026-07-31", "7") == "2026-08-06"


def test_loaded_short_overview_is_inclusive_and_direction_aware():
    reply = planner.build_deterministic_reply(
        "what am I looking at?", _short_wave(), _screen(), current_year=2026
    )

    assert "Jul 31 to Aug 6" in reply
    assert "7 calendar days, with the entry date counted as day 1" in reply
    assert "14 of 17 completed years (82%)" in reply
    assert "red/down years are profitable short trades" in reply
    assert "green/up years are losing short trades" in reply
    assert "Bottom Price Chart" in reply
    assert "showing current price action" in reply
    assert "gold dashed line uses the selected 17-year seasonal history" in reply
    assert "purple dashed line uses the full 25-year history" in reply
    assert "historical seasonal guides, not guaranteed forecasts" in reply
    assert "6-day" not in reply
    assert "most bars are green" not in reply.lower()


def test_prompt_exposes_raw_bars_and_direction_adjusted_short_results():
    blocks = chatbot.build_system_prompt(
        _short_wave(), [], screen_context=_screen(), user_message="show me 2000 and 2014"
    )
    prompt = "\n".join(block["text"] for block in blocks)

    assert "Jul 31 to Aug 6 (7 calendar days)" in prompt
    assert "entry date counted as day 1" in prompt
    assert "14 profitable, 3 losing, 0 flat, n=17 years" in prompt
    assert "negative returns/red bars are PROFITABLE SHORT trades" in prompt
    assert "2000: underlying -1.00% [RED/DOWN BAR]; short trade +1.00% [PROFIT]" in prompt
    assert "2014: underlying +1.00% [GREEN/UP BAR]; short trade -1.00% [LOSS]" in prompt


def test_stable_prompt_uses_semantic_lower_viewer_positions():
    blocks = chatbot.build_system_prompt(
        _short_wave(), [], screen_context=_screen(), user_message="Where is the Price Chart?"
    )
    prompt = "\n".join(block["text"] for block in blocks)

    assert "Price Chart is the final lower-viewer dot" in prompt
    assert "Wave Stats is the second lower-viewer dot" in prompt
    assert "Price Chart is slide 3" not in prompt
    assert "3-slide menu" not in prompt


def test_prompt_accepts_legacy_return_pct_as_raw_during_rolling_deploy():
    for return_key in ("raw_return_pct", "return_pct"):
        blocks = chatbot.build_system_prompt(
            _short_wave(return_key=return_key),
            [],
            screen_context=_screen(),
            user_message="show me 2000 and 2014",
        )
        prompt = "\n".join(block["text"] for block in blocks)
        assert "2000: underlying -1.00% [RED/DOWN BAR]; short trade +1.00% [PROFIT]" in prompt
        assert "2014: underlying +1.00% [GREEN/UP BAR]; short trade -1.00% [LOSS]" in prompt


def test_bad_short_color_or_day_reply_is_replaced_with_loaded_truth():
    bad_reply = (
        "PEG short from Jul 31 to Aug 6 is a 6-day bearish seasonal window. "
        "Most bars are green, which is unusual for a short pattern."
    )

    guarded = planner.build_deterministic_reply(
        "what am I looking at?", _short_wave(), _screen(), current_year=2026
    )

    assert "7 calendar days, with the entry date counted as day 1" in guarded
    assert "14 of 17 completed years (82%)" in guarded
    assert "6-day" not in guarded
    assert "most bars are green" not in guarded.lower()


def test_loaded_overview_explains_the_visible_trend_slide_instead():
    reply = planner.build_deterministic_reply(
        "what am I looking at?", _short_wave(), _screen("trend_chart"), current_year=2026
    )

    assert "Bottom Trend Chart" in reply
    assert "historical seasonal path" in reply
    assert "Jul 31 to Aug 6" in reply
    assert "Bottom Price Chart" not in reply


def test_loaded_overview_explains_the_visible_ai_scores_slide():
    reply = planner.build_deterministic_reply(
        "what am I looking at?", _short_wave(), _screen("ai_scores"), current_year=2026
    )

    assert "Bottom AI Scores" in reply
    assert "estimated chance of profit" in reply
    assert "0-100 return rank" in reply


def test_strength_floor_uses_direction_adjusted_stats_and_sample_size():
    reply = chatbot._ensure_strength_answered(
        "how strong is this?", _short_wave(), "Loaded on the chart."
    )

    assert "82% profitable (won 14 of 17 years)" in reply
    assert "won 3 of 17" not in reply


def test_current_year_zero_stub_is_not_part_of_completed_record():
    wave = _short_wave()
    wave["start_date"] = "2026-07-31"
    wave["yearly_results"].append({
        "year": 2026,
        "raw_return_pct": 0,
        "mfe_pct": 0,
        "mae_pct": 0,
    })

    completed = planner.canonical_pattern_facts(wave, current_year=2026)

    assert completed["sample_size"] == 17
    assert 2026 not in completed["completed_years"]


def test_react_payload_names_underlying_price_move_and_screen_snapshot():
    source = (ROOT / "web-react" / "src" / "components" / "Chatbot.js").read_text()
    app_source = (ROOT / "web-react" / "src" / "components" / "App.js").read_text()
    price_source = (ROOT / "web-react" / "src" / "components" / "StockLineChart.js").read_text()

    assert "underlying_return_pct: parseOptionalNumber(plist[0])" in source
    assert "\n          return_pct:" not in source
    assert "screen_context: buildChatbotScreenContext(props)" in source
    assert "visibleOpportunities" in source
    assert "const [priceChartContext, SetPriceChartContext]" in app_source
    assert "selected_projection_visible" in price_source
    assert "full_history_projection_visible" in price_source
