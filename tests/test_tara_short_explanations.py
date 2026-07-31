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


def _short_wave(*, legacy_rows=False):
    return_key = "return_pct" if legacy_rows else "raw_return_pct"
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


def test_inclusive_calendar_window_ends_on_august_6():
    assert chatbot.calculate_end_date("2026-07-31", "7") == "2026-08-06"


def test_loaded_short_overview_is_inclusive_and_direction_aware():
    reply = chatbot._loaded_pattern_overview("what am I looking at?", _short_wave())

    assert "Jul 31 to Aug 6" in reply
    assert "exactly 7 calendar days" in reply
    assert "counts Jul 31 as day 1" in reply
    assert "price fell in 14 of 17 completed years" in reply
    assert "red/down bars are profitable short years" in reply
    assert "green/up bars are losing short years" in reply
    assert "82% profitable" in reply
    assert "6-day" not in reply
    assert "most bars are green" not in reply.lower()


def test_prompt_exposes_raw_bars_and_direction_adjusted_short_results():
    prompt = chatbot.build_system_prompt(_short_wave(), [])

    assert "EXACTLY 7 calendar days" in prompt
    assert "entry date is day 1" in prompt
    assert "14 profitable and 3 losing years" in prompt
    assert "3 green/up and 14 red/down completed bars" in prompt
    assert "RED/DOWN bars are profitable short years" in prompt
    assert "2000: raw price -1.00% (RED/DOWN); short trade +1.00% [PROFIT]" in prompt
    assert "2014: raw price +1.00% (GREEN/UP); short trade -1.00% [LOSS]" in prompt


def test_prompt_accepts_legacy_return_pct_as_raw_during_rolling_deploy():
    prompt = chatbot.build_system_prompt(_short_wave(legacy_rows=True), [])

    assert "2000: raw price -1.00% (RED/DOWN); short trade +1.00% [PROFIT]" in prompt
    assert "2014: raw price +1.00% (GREEN/UP); short trade -1.00% [LOSS]" in prompt


def test_bad_short_color_or_day_reply_is_replaced_with_loaded_truth():
    bad_reply = (
        "PEG short from Jul 31 to Aug 6 is a 6-day bearish seasonal window. "
        "Most bars are green, which is unusual for a short pattern."
    )

    guarded = chatbot._guard_loaded_pattern_reply("tell me about it", _short_wave(), bad_reply)

    assert "exactly 7 calendar days" in guarded
    assert "price fell in 14 of 17 completed years" in guarded
    assert "6-day" not in guarded
    assert "most bars are green" not in guarded.lower()


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

    completed = chatbot._completed_year_rows(wave, today=date(2026, 7, 31))

    assert len(completed) == 17
    assert all(row["year"] != 2026 for row in completed)


def test_react_payload_names_the_value_as_raw_price_return():
    source = (ROOT / "web-react" / "src" / "components" / "Chatbot.js").read_text()

    assert "raw_return_pct: parseFloat(plist[0])" in source
    assert "\n          return_pct: parseFloat(plist[0])" not in source
