import json
import time
import datetime

import jwt
import pytest
from flask import Flask

import chatbot
import tara_gateway


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("question", "matches", "expected_market"),
    [
        (
            "How did DJI index do during the 100 year pattern?",
            [
                {"resourceID": "2", "label": "S&P 500 STOCKS", "name": "DJI Holdings"},
                {"resourceID": "5", "label": "INDICES", "name": "Dow Jones Industrial Average"},
            ],
            "5",
        ),
        (
            "How did CL crude oil do during the 100 year pattern?",
            [
                {"resourceID": "2", "label": "US STOCKS", "name": "Colgate-Palmolive"},
                {"resourceID": "7", "label": "COMMODITY FUTURES", "name": "Crude Oil WTI"},
            ],
            "7",
        ),
    ],
)
def test_security_qualifier_resolves_cross_market_ticker(
    monkeypatch, question, matches, expected_market
):
    monkeypatch.setattr(
        tara_gateway,
        "_loopback_json",
        lambda *args, **kwargs: (200, {"symbol": "X", "matches": matches}),
    )

    symbol = "DJI" if "DJI" in question else "CL"
    result = tara_gateway._resolve_question_symbol(symbol, question, "token", {})

    assert result["status"] == "ok"
    assert result["market"] == expected_market


def test_unqualified_standard_ticker_prefers_us_stock_over_foreign_receipt(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_loopback_json",
        lambda *args, **kwargs: (200, {
            "symbol": "MSFT",
            "matches": [
                {
                    "resourceID": "2",
                    "label": "S&P 500 STOCKS",
                    "name": "Microsoft Corporation",
                },
                {
                    "resourceID": "12",
                    "label": "TORONTO STOCKS",
                    "name": "Microsoft CDR (CAD Hedged)",
                },
            ],
        }),
    )

    result = tara_gateway._resolve_question_symbol(
        "MSFT", "How did MSFT do during the 100 year pattern?", "token", {}
    )

    assert result["status"] == "ok"
    assert result["market"] == "2"


def test_unqualified_spx_prefers_canonical_index_over_foreign_stock(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_loopback_json",
        lambda *args, **kwargs: (200, {
            "symbol": "SPX",
            "matches": [
                {
                    "resourceID": "5",
                    "label": "INDICES COMMON",
                    "name": "S&P 500",
                },
                {
                    "resourceID": "14",
                    "label": "LONDON EXCHANGE",
                    "name": "Spirax Group plc",
                },
            ],
        }),
    )

    result = tara_gateway._resolve_question_symbol(
        "SPX", "When is SPX historically weak?", "token", {}
    )

    assert result["status"] == "ok"
    assert result["market"] == "5"


def test_hundred_year_dates_analyze_named_security_and_queue_exact_chart(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_resolve_question_symbol",
        lambda *args, **kwargs: {
            "status": "ok",
            "symbol": "MSFT",
            "market": "2",
            "label": "S&P 500 STOCKS",
            "name": "Microsoft Corp",
        },
    )
    monkeypatch.setattr(
        tara_gateway,
        "_symbol_metadata_dates",
        lambda *args, **kwargs: (
            datetime.date(1986, 3, 13),
            datetime.date(2026, 8, 19),
        ),
    )
    seen = {}

    def fake_chart(market, symbol, entry_date, days_out, years_value, token, *, direction):
        seen.update(
            market=market,
            symbol=symbol,
            entry_date=entry_date,
            days_out=days_out,
            years_value=years_value,
            direction=direction,
        )
        return 200, {
            "request": {
                "market": "2",
                "symbol": "MSFT",
                "entry_date": "2026-09-27",
                "days_out": 295,
                "years": 10,
                "pe_cycle": "pe2",
            },
            "stats": {
                "Num Winners": "8",
                "Num Losers": "2",
                "Avg Profit - All": "12%",
                "Median Profit": "10.5%",
                "Sharpe Ratio": "0.81",
            },
            "ChartData4": [
                {"year": 1986, "pct": "-11.2,5,-15", "price": "1,2"},
                {"year": 2022, "pct": "18.5,20,-3", "price": "1,2"},
                {"year": 2026, "pct": "0,0,0", "price": "0,0"},
            ],
        }

    monkeypatch.setattr(tara_gateway, "_chart_data4", fake_chart)

    command = tara_gateway.build_hundred_year_security_command(
        "How did MSFT do during the 100 year pattern?",
        {},
        "browser-token",
        today=datetime.date(2026, 8, 19),
    )

    assert command["spec"] == {
        "market": "2",
        "symbol": "MSFT",
        "entry_date": "2026-09-27",
        "days_out": 295,
        "years": 10,
        "pe_cycle": "pe2",
    }
    assert seen["years_value"] == "pe2-10"
    assert seen["direction"] == "long"
    assert "8 of 10 completed PE+2 observations" in command["reply"]
    assert "1986 at -11.2%" in command["reply"]
    assert "named 100-Year Pattern in the book is the SPX study" in command["reply"]


def test_best_time_to_buy_uses_recent_long_best_wave_and_exact_chart(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_resolve_question_symbol",
        lambda *args, **kwargs: {
            "status": "ok",
            "symbol": "SPY",
            "market": "11",
            "label": "ETFS",
            "name": "SPDR S&P 500 ETF Trust",
        },
    )
    monkeypatch.setattr(
        tara_gateway,
        "_best_waves_rows",
        lambda *args, **kwargs: (
            200,
            "ok",
            [
                ["2026-08-17", "SPY", 25, "Long", 1.52, 3.24, 2.8, 0, 0],
                ["2026-10-02", "SPY", 14, "Long", 1.80, 2.5, 2.1, 0, 0],
                ["2026-09-01", "SPY", 20, "Short", 2.0, 4.0, 3.0, 0, 0],
            ],
            20,
        ),
    )
    monkeypatch.setattr(
        tara_gateway,
        "_chart_data4",
        lambda *args, **kwargs: (200, {
            "request": {
                "market": "11",
                "symbol": "SPY",
                "entry_date": "2026-08-17",
                "days_out": 26,
                "years": 20,
                "pe_cycle": "cons",
            },
            "stats": {"Num Winners": "20", "Num Losers": "0"},
            "ChartData4": [{"year": 2025, "pct": "2,3,-1"}],
        }),
    )

    command = tara_gateway.build_best_waves_command(
        "When is the best time to buy SPY through the remainder of the year?",
        {"years": 20, "pe_cycle": "cons"},
        "browser-token",
        today=datetime.date(2026, 8, 19),
    )

    assert command["spec"] == {
        "market": "11",
        "symbol": "SPY",
        "entry_date": "2026-08-17",
        "days_out": 26,
        "years": 20,
        "pe_cycle": "cons",
    }
    assert "already started" in command["reply"]
    assert "Best Waves</b> dropdown above the bar chart" in command["reply"]
    assert "empty or hidden" in command["reply"]


def test_best_waves_empty_result_is_an_answer_not_a_chart_failure(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_resolve_question_symbol",
        lambda *args, **kwargs: {
            "status": "ok", "symbol": "SPY", "market": "11", "label": "ETFS", "name": "SPY"
        },
    )
    monkeypatch.setattr(
        tara_gateway,
        "_best_waves_rows",
        lambda *args, **kwargs: (200, "ok", [], 10),
    )

    command = tara_gateway.build_best_waves_command(
        "When is the best time to buy SPY?",
        {"years": 10, "pe_cycle": "cons"},
        "browser-token",
        today=datetime.date(2026, 8, 19),
    )

    assert command["spec"] is None
    assert "No qualifying upcoming Long Best Wave" in command["reply"]
    assert "No pattern passed" in command["reply"]


def _text_response(text):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
    }


def _tool_response(tool_id, name, tool_input):
    return {
        "stop_reason": "tool_use",
        "content": [{
            "type": "tool_use",
            "id": tool_id,
            "name": name,
            "input": tool_input,
        }],
    }


def _grounded_card():
    return {
        "card": {
            "symbol": "TSLA",
            "market": {"id": "2", "name": "S&P 500 STOCKS"},
            "setup": {"entry_date": "2026-07-24", "hold_days": 21},
            "stats": {
                "historical_win_rate": 0.8,
                "avg_return_pct": 4.2,
                "years": 10,
            },
            "headline": "TSLA long - Won 8/10 years, avg +4.2%.",
        }
    }


def _run_sequence(
        monkeypatch, responses, message="load TSLA", current_view=None, tool_result=None):
    calls = []

    def fake_send(*args, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(tara_gateway, "send_claude_messages", fake_send)
    monkeypatch.setattr(
        tara_gateway,
        "run_tool",
        lambda name, tool_input, user_id: (
            _grounded_card() if tool_result is None else tool_result
        ),
    )
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": message}],
        "system",
        "user-1",
        "model",
        current_view=current_view or {},
    )
    return text, actions, calls


def test_new_symbol_action_must_match_read_result(monkeypatch):
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "TSLA"}),
        _tool_response("view-1", "update_view", spec),
        _text_response("TSLA won 8 of 10 years with an average +4.2% return."),
    ]

    text, actions, _ = _run_sequence(monkeypatch, responses)

    assert "TSLA" in text
    assert len(actions) == 1
    assert actions[0]["status"] == "validated"
    assert actions[0]["spec"] == spec


def test_fabricated_but_well_formed_setup_is_rejected(monkeypatch):
    fabricated = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-09-01",
        "days_out": 45,
    }
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "TSLA"}),
        _tool_response("view-1", "update_view", fabricated),
        _text_response("I could not resolve a setup."),
        _text_response("I could not resolve a setup."),
    ]

    text, actions, _ = _run_sequence(monkeypatch, responses)

    assert actions == []
    assert "haven't changed the chart" in text


def test_unconfirmed_same_symbol_cannot_bypass_setup_validation():
    assert tara_gateway._validate_view_spec(
        {"symbol": "TSLA"},
        current_view={"symbol": "TSLA", "view_ready": False},
    ) == {}
    assert tara_gateway._validate_view_spec(
        {"symbol": "TSLA"},
        current_view={
            "symbol": "TSLA",
            "market": "2",
            "entry_date": "2026-07-24",
            "days_out": 21,
            "view_ready": True,
        },
    ) == {"symbol": "TSLA"}
    assert tara_gateway._validate_view_spec(
        {"entry_date": "2026-09-01", "days_out": 45},
        current_view={"symbol": "TSLA", "view_ready": False},
    ) == {}


@pytest.mark.parametrize(
    "current_view",
    [
        {"symbol": "TSLA", "view_ready": True},
        {
            "symbol": "TSLA",
            "entry_date": "2026-07-24",
            "days_out": 21,
            "view_ready": True,
        },
        {
            "symbol": "TSLA",
            "market": "2",
            "entry_date": "2026-07-24",
            "view_ready": True,
        },
    ],
)
def test_partial_refresh_requires_complete_confirmed_view_identity(current_view):
    spec = {"symbol": "TSLA"}
    assert tara_gateway._validate_view_spec(spec, current_view=current_view) == {}
    assert tara_gateway._view_spec_is_grounded(
        spec, [], current_view=current_view
    ) is False


def test_flat_pattern_rows_with_days_out_are_valid_grounding():
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    cards = [{
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }]
    assert tara_gateway._view_spec_is_grounded(spec, cards, {}) is True


@pytest.mark.parametrize("bad_date", ["2026-7-04", "2026-07-4", "2026-02-30"])
def test_view_dates_are_strict_and_atomic(bad_date):
    assert tara_gateway._validate_view_spec({
        "symbol": "TSLA",
        "market": "2",
        "entry_date": bad_date,
        "days_out": 21,
    }) == {}


def test_printed_function_markup_never_reaches_client(monkeypatch):
    markup = _text_response(
        "<function_calls><invoke name='update_view'><parameter name='symbol'>TSLA</parameter>"
        "</invoke></function_calls>"
    )
    responses = [dict(markup) for _ in range(tara_gateway._MAX_TOOL_ROUNDS)]

    text, actions, calls = _run_sequence(monkeypatch, responses)

    assert len(calls) == tara_gateway._MAX_TOOL_ROUNDS
    assert actions == []
    assert "<function_calls" not in text
    assert "haven't changed the chart" in text


def test_completion_claim_is_rewritten_while_action_is_preserved(monkeypatch):
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "TSLA"}),
        _tool_response("view-1", "update_view", spec),
        _text_response("I've loaded TSLA on the chart."),
        _text_response("TSLA won 8 of 10 years with an average +4.2% return."),
    ]

    text, actions, _ = _run_sequence(monkeypatch, responses)

    assert len(actions) == 1
    assert "loaded" not in text.lower()
    assert "8 of 10" in text


def test_market_only_action_does_not_satisfy_symbol_load_intent():
    actions = [{
        "type": "set_view",
        "spec": {"market": "2"},
    }]
    assert tara_gateway._actions_satisfy_view_intent(actions, "chart") is False
    assert tara_gateway._actions_satisfy_view_intent(actions, "view") is True
    assert tara_gateway._actions_satisfy_view_intent(actions, "forbid") is False


def test_negated_and_diagnostic_load_phrases_forbid_actions():
    for text in (
        "I don't want you to load TSLA",
        "never load TSLA",
        "please avoid loading TSLA",
        "don't display TSLA",
        "stop loading TSLA",
        "why didn't it load?",
        "how did the chart fail to load?",
        "Can you explain why it didn't load TSLA?",
    ):
        assert tara_gateway._latest_user_view_intent(
            [{"role": "user", "content": text}]
        ) == "forbid"


def test_later_positive_view_correction_wins_over_earlier_negation():
    assert tara_gateway.classify_view_intent(
        "Don't load TSLA; load AAPL instead"
    ) == "chart"
    assert tara_gateway.classify_view_intent(
        "don't display TSLA, but pull AAPL up"
    ) == "chart"


def test_negated_load_cannot_queue_an_action(monkeypatch):
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "TSLA"}),
        _tool_response("view-1", "update_view", spec),
        _text_response("I did not change the chart."),
    ]
    _, actions, _ = _run_sequence(
        monkeypatch,
        responses,
        message="I don't want you to load TSLA",
    )
    assert actions == []


@pytest.mark.parametrize(
    "text",
    [
        "what's today's pick?",
        "is AAPL a good trade?",
        "should I buy TSLA?",
        "what about AAPL?",
        "analyze AAPL",
        "does AAPL make money?",
        "show me the best one",
        "can I see AAPL?",
        "pull AAPL up",
        "display AAPL",
        "take me to AAPL",
        "Load AAPL and show me its current seasonal pattern.",
    ],
)
def test_single_pick_requests_require_a_chart_action(text):
    assert tara_gateway._latest_user_view_intent(
        [{"role": "user", "content": text}]
    ) == "chart"


@pytest.mark.parametrize("text", [
    "what should I trade?",
    "give me a trade",
    "recommend me a trade",
    "I have $2,000 and want to invest. What should I buy?",
    "I want to invest in the market. How do I figure out what to invest in?",
])
def test_broad_investment_requests_never_auto_load_a_winner(text):
    assert tara_gateway._latest_user_view_intent(
        [{"role": "user", "content": text}]
    ) is None


@pytest.mark.parametrize(
    "text",
    [
        "show me the best trade setups",
        "what are your best trade ideas?",
        "give me the top trade picks",
        "show me top trades",
        "show me high win-rate trades",
        "show me only the best ones",
        "show me the top 5",
        "list the top 10 seasonal picks",
        "which are the strongest setups?",
        "find me the highest win rate trades",
    ],
)
def test_plural_trade_list_requests_do_not_require_a_chart_action(text):
    assert tara_gateway._latest_user_view_intent(
        [{"role": "user", "content": text}]
    ) is None


def test_investor_funnel_classifies_horizon_universe_and_weak_periods():
    assert tara_gateway.classify_investor_intent(
        "I have 2000 dollars - I want to invest - what should I buy?"
    ) == "start"
    assert tara_gateway.classify_investor_intent(
        "Find ETFs in bullish patterns this time of the year"
    ) == "seasonal_etf"
    assert tara_gateway.classify_investor_intent(
        "Find S&P 500 stocks with bullish seasonal opportunities now"
    ) == "seasonal_stock"
    assert tara_gateway.classify_investor_intent(
        "Find the historically weak time for AAPL"
    ) == "weak_symbol"
    assert tara_gateway.classify_investor_intent(
        "Show me the Buy & Hold workflow for long-term investors"
    ) == "buy_hold_study"
    assert tara_gateway.classify_investor_intent(
        "What can I research with Tara right now?"
    ) == "capabilities"
    assert tara_gateway.classify_investor_intent(
        "Load AAPL and show me its current seasonal pattern."
    ) is None
    assert tara_gateway.classify_investor_intent([
        {"role": "user", "content": "I want to invest. What should I buy?"},
        {"role": "assistant", "content": "Long term or seasonal?"},
        {"role": "user", "content": "long term"},
    ]) == "long_term"
    assert tara_gateway.classify_investor_intent([
        {"role": "user", "content": "I want to invest. What should I buy?"},
        {"role": "assistant", "content": "Long term or seasonal?"},
        {"role": "user", "content": "long"},
    ]) == "long_term"
    assert tara_gateway.classify_investor_intent("long") is None
    assert tara_gateway.classify_investor_intent([
        {"role": "user", "content": "Is this pattern long or short?"},
        {"role": "assistant", "content": "It is a historical Long pattern."},
        {"role": "user", "content": "long"},
    ]) is None
    assert tara_gateway.classify_investor_intent([
        {"role": "user", "content": "What should I trade?"},
        {"role": "assistant", "content": "Stocks or ETFs?"},
        {"role": "user", "content": "ETFs"},
    ]) == "seasonal_etf"


def test_loaded_personal_direction_question_uses_historical_boundary():
    current_view = {
        "symbol": "AVGO",
        "market": "2",
        "direction": "long",
        "entry_date": "2026-07-23",
        "days_out": 21,
        "view_ready": True,
        "stats": {
            "Num Winners": "8",
            "Num Losers": "2",
            "Avg Profit - All": "+4.2%",
            "Sharpe Ratio": "1.4",
        },
    }

    assert tara_gateway.classify_investor_intent(
        "do i long or short?"
    ) == "trade_suitability"
    text = tara_gateway.loaded_pattern_suitability_response(
        "do i long or short?", current_view
    )

    assert "cannot tell you whether to go long or short" in text
    assert "historical <b>Long</b> pattern" in text
    assert "won 8 of 10 completed years" in text
    assert "average pattern result of +4.2%" in text
    assert "Sharpe ratio of 1.4" in text
    assert "not today's market direction or a forecast" in text
    assert "Past performance does not guarantee future results" in text


def test_personal_direction_boundary_does_not_replace_factual_direction_question():
    assert tara_gateway.loaded_pattern_suitability_response(
        "is this pattern long or short?",
        {"symbol": "AVGO", "direction": "long", "view_ready": True},
    ) is None


def test_personal_direction_question_never_reaches_tool_model_loop(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("personal direction question reached model"),
    )
    protocol_trace = []
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": "do i long or short?"}],
        "system",
        "user-1",
        "model",
        current_view={
            "symbol": "AVGO",
            "market": "2",
            "direction": "long",
            "entry_date": "2026-07-23",
            "days_out": 21,
            "view_ready": True,
            "stats": {"Num Winners": 8, "Num Losers": 2},
        },
        protocol_trace=protocol_trace,
    )

    assert actions == []
    assert "cannot tell you whether to go long or short" in text
    assert protocol_trace == [{
        "event": "loaded_pattern_suitability_boundary",
        "symbol": "AVGO",
    }]


def test_general_investing_question_gets_horizon_first_without_model(monkeypatch):
    text, actions, calls = _run_sequence(
        monkeypatch,
        [],
        message="I have $2,000 and want to invest. What should I buy?",
    )

    assert calls == []
    assert actions == []
    assert "cannot decide what is suitable" in text
    assert "long-term investing" in text
    assert "days or weeks" in text
    assert "losing evidence" in text


def test_capability_guide_is_deterministic_and_outcome_oriented(monkeypatch):
    text, actions, calls = _run_sequence(
        monkeypatch,
        [],
        message="What can I ask Tara?",
    )

    assert calls == []
    assert actions == []
    assert "Find opportunities" in text
    assert "Research a ticker" in text
    assert "Study downside" in text
    assert "Research long-term investing" in text
    assert "compare symbols" in text
    assert "guided questions below" in text


def test_long_term_followup_teaches_buy_hold_comparison_and_access_without_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    text, actions = tara_gateway.run_chat_with_tools(
        [
            {"role": "user", "content": "I want to invest. What should I buy?"},
            {"role": "assistant", "content": "Long term or seasonal?"},
            {"role": "user", "content": "long"},
        ],
        "system",
        "user-1",
        "model",
    )

    assert calls == []
    assert actions == []
    assert text.index("Start with Buy &amp; Hold") < text.index("Compare investments")
    assert text.index("Compare investments") < text.index("Advanced: test weak dates")
    assert "enter a ticker such as MSFT" in text
    assert "Analysis &rarr; Buy &amp; Hold" in text
    assert "green and red yearly bars" in text
    assert "Trend Chart" in text
    assert "Cumulative Return" in text
    assert "Analysis &rarr; Compare Symbols&hellip;" in text
    assert "WMT and AVGO" in text
    assert "same full-year dates" in text
    assert "Analysis &rarr; Exclude Current Range" in text
    assert "View Exclusion Report" in text
    assert text.count("<br>") >= 8
    assert len(text) < 1800


def test_buy_hold_workflow_is_deterministic_and_uses_comparable_years(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": (
            "Show me the Buy & Hold workflow for long-term investors"
        )}],
        "system",
        "user-1",
        "model",
    )

    assert calls == []
    assert actions == []
    assert "Jan 1-to-Jan 1" in text
    assert "Read historical growth" in text
    assert "each year's gain or loss" in text
    assert "Analysis &rarr; Compare Symbols&hellip;" in text
    assert "MSFT first and enter WMT and AVGO" in text
    assert "common historical years" in text
    assert "Analysis &rarr; Exclude Current Range" in text
    assert "View Exclusion Report" in text
    assert "same completed years" in text
    assert "not a promise that timing will outperform" in text
    assert text.count("<br>") >= 10
    assert len(text) < 1800


def test_guided_questions_follow_the_investor_research_stage():
    start = tara_gateway.guided_next_questions(
        "I have $2,000 and want to invest. What should I buy?"
    )
    assert [item["label"] for item in start] == [
        "Plan for years", "Find seasonal ETFs", "Find seasonal stocks",
    ]
    assert start[0]["prompt"] == "long term"

    long_term = tara_gateway.guided_next_questions(
        "Show me the Buy & Hold workflow for long-term investors",
        current_view={"view_ready": True, "symbol": "SPY"},
    )
    assert long_term[0]["prompt"] == "Show me the Buy & Hold workflow for SPY"
    assert long_term[1]["prompt"] == "When is SPY historically weak?"
    assert "Buy & Hold" in long_term[2]["prompt"]


def test_guided_candidate_questions_are_grounded_in_returned_symbols():
    questions = tara_gateway.guided_next_questions(
        "Show me bullish ETF patterns this time of year",
        reply=(
            "Candidates:<br><b>SPY</b> - evidence.<br>"
            "<b>VTI</b> - evidence.<br><b>not a ticker</b>"
        ),
        actions=[{"type": "set_view", "spec": {"market": "11"}}],
    )

    assert questions == [
        {"label": "Inspect SPY", "prompt": "Analyze SPY's full seasonal evidence"},
        {
            "label": "Compare two candidates",
            "prompt": "Compare SPY and VTI using their historical seasonal evidence",
        },
        {"label": "Study the downside", "prompt": "When is SPY historically weak?"},
    ]


def test_guided_report_questions_follow_the_validated_report_type():
    questions = tara_gateway.guided_next_questions(
        "Explain this report",
        analysis_report={"report_type": "range_comparison"},
    )

    assert [item["label"] for item in questions] == [
        "Judge the result", "Inspect the downside", "Check limitations",
    ]
    assert "Buy & Hold" in questions[0]["prompt"]


def test_etf_investor_screen_filters_complex_products_and_never_loads_winner(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("deterministic investor screen reached model"),
    )
    rows = [
        {"date": "2026-08-20", "symbol": "TQQQ", "days_out": 20,
         "direction": "L", "avg_profit": 9.0, "sharpe_ratio": 2.5},
        {"date": "2026-08-21", "symbol": "SPY", "days_out": 30,
         "direction": "L", "avg_profit": 3.4, "sharpe_ratio": 1.4},
        {"date": "2026-08-22", "symbol": "VTI", "days_out": 25,
         "direction": "L", "avg_profit": 2.8, "sharpe_ratio": 1.2},
    ]
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": (
            "I have $2,000. Show bullish ETF patterns this time of the year."
        )}],
        "system",
        "user-1",
        "model",
        opp_table=rows,
        opp_table_market="11",
    )

    assert actions == []
    assert "SPY" in text and "VTI" in text
    assert "TQQQ" not in text
    assert "not personal recommendations" in text
    assert "dollar amount was not used" in text
    assert "leveraged, inverse, and single-stock" in text


def test_stock_investor_screen_switches_market_only(monkeypatch):
    monkeypatch.setattr(
        tara_gateway,
        "_opplist4_rows",
        lambda *args, **kwargs: [
            {"date": "2026-08-20", "symbol": "AAPL", "days_out": 21,
             "direction": "L", "avg_profit": 4.0, "sharpe_ratio": 1.6},
            {"date": "2026-08-22", "symbol": "MSFT", "days_out": 28,
             "direction": "L", "avg_profit": 3.1, "sharpe_ratio": 1.3},
        ],
    )
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("deterministic investor screen reached model"),
    )
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": "Find bullish seasonal stock opportunities now"}],
        "system",
        "user-1",
        "model",
        opp_table_market="0",
        user_token="token",
    )

    assert "AAPL" in text and "MSFT" in text
    assert len(actions) == 1
    assert actions[0]["type"] == "set_view"
    assert actions[0]["spec"] == {"market": "2"}
    assert all(not action["spec"].get("symbol") for action in actions)


def test_weak_symbol_study_uses_short_direction_without_recommending_short(monkeypatch):
    seen = []
    weak_result = {
        "card": {
            "symbol": "AAPL",
            "market": {"id": "2"},
            "direction": "short",
            "setup": {"entry_date": "2026-09-10", "hold_days": 24},
            "stats": {
                "historical_win_rate": 0.7,
                "avg_return_pct": 3.2,
                "sharpe_ratio": 1.1,
                "years": 10,
            },
            "receipts": {
                "years_tested": 10,
                "wins": 7,
                "losses": 3,
                "worst_year": {"year": "2021", "return_pct": -5.0},
            },
            "headline": "AAPL short - Won 7/10 years, avg +3.2%, Sharpe 1.1.",
        },
    }

    def fake_tool(name, tool_input, user_id):
        seen.append((name, tool_input, user_id))
        return weak_result

    monkeypatch.setattr(tara_gateway, "run_tool", fake_tool)
    monkeypatch.setattr(
        tara_gateway,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("deterministic weak study reached model"),
    )
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": "Find the weakest time for AAPL"}],
        "system",
        "user-1",
        "model",
    )

    assert seen == [("analyze_symbol", {"symbol": "AAPL", "direction": "short"}, "user-1")]
    assert "underlying fell in 7 of 10 years" in text
    assert "not a sell or short recommendation" in text
    assert len(actions) == 1
    assert actions[0]["spec"] == {
        "symbol": "AAPL",
        "market": "2",
        "entry_date": "2026-09-10",
        "days_out": 24,
    }


def test_named_buy_question_retries_personalized_directive(monkeypatch):
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "TSLA"}),
        _tool_response("view-1", "update_view", spec),
        _text_response("You should buy TSLA."),
        _text_response(
            "TradeWave cannot determine whether TSLA is suitable for you. "
            "Historically, this setup won 8 of 10 years with an average +4.2% return."
        ),
    ]

    text, actions, calls = _run_sequence(
        monkeypatch,
        responses,
        message="Should I buy TSLA?",
    )

    assert len(calls) == 4
    assert len(actions) == 1
    assert "cannot determine whether TSLA is suitable" in text
    assert "You should buy" not in text


def test_investor_response_contract_blocks_allocations_and_forecasts():
    assert tara_gateway.response_violates_investor_contract(
        "You should put $2,000 in SPY.", "named_security"
    ) is True
    assert tara_gateway.response_violates_investor_contract(
        "TSLA will rise this year.", "named_security"
    ) is True
    assert tara_gateway.response_violates_investor_contract(
        "TradeWave cannot determine whether TSLA is suitable for you. "
        "Historically, the setup won 8 of 10 years.",
        "named_security",
    ) is False


def test_brief_card_preserves_compact_gain_loss_evidence():
    brief = tara_gateway._brief_card({
        "symbol": "SPY",
        "stats": {"historical_win_rate": 0.8, "avg_return_pct": 3.0, "years": 10},
        "receipts": {
            "years_tested": 10,
            "wins": 8,
            "losses": 2,
            "best_year": {"year": "2020", "return_pct": 9.0},
            "worst_year": {"year": "2022", "return_pct": -6.0},
            "per_year": [{"year": "2022", "return_pct": -6.0}],
        },
    })

    assert "receipts" not in brief
    assert brief["history"] == {
        "years_tested": 10,
        "wins": 8,
        "losses": 2,
        "best_year": {"year": "2020", "return_pct": 9.0},
        "worst_year": {"year": "2022", "return_pct": -6.0},
    }


def test_exclusion_question_refuses_unmatched_tool_synthesis(monkeypatch):
    text, actions, calls = _run_sequence(
        monkeypatch,
        [],
        message="What if I exclude the current date range?",
    )

    assert calls == []
    assert actions == []
    assert "validated Date Range Exclusion Report" in text
    assert "won't compare unmatched windows" in text


@pytest.mark.parametrize(
    "claim",
    [
        "The chart has been updated with AAPL.",
        "I've put AAPL on the chart.",
        "You're now viewing AAPL.",
        "The viewer is ready.",
        "AAPL is now displayed on your chart.",
        "AAPL is showing on the chart now.",
        "The chart now contains AAPL.",
        "I switched to AAPL.",
        "AAPL loaded successfully.",
        "The chart is showing AAPL now.",
        "I've brought up AAPL.",
        "The view has refreshed with AAPL.",
        "Loading AAPL now.",
    ],
)
def test_unconfirmed_completion_claim_variants_are_blocked(claim):
    assert tara_gateway.response_violates_view_contract(
        claim,
        actions=[],
        current_view={},
    ) is True


def test_negated_status_and_capability_description_are_not_completion_claims():
    assert tara_gateway.response_violates_view_contract(
        "Chart controls are temporarily unavailable, so I haven't changed the chart.",
        actions=[],
        current_view={},
    ) is False
    assert tara_gateway.response_violates_view_contract(
        "I can load supported public symbols when you ask.",
        actions=[],
        current_view={},
    ) is False


@pytest.mark.parametrize(
    "text",
    [
        "whats the best high volume stock for today?",
        "you tell me should i do a long or short depending on todays trend and market",
    ],
)
def test_unsupported_live_data_intent_is_deterministic_without_model_or_action(
        monkeypatch, text):
    assert tara_gateway.classify_view_intent(text) == "unsupported_live"

    reply, actions, calls = _run_sequence(monkeypatch, [], message=text)

    assert calls == []
    assert actions == []
    assert "can't verify intraday volume or the broad market's live trend" in reply
    assert "seasonal-pattern scan" in reply


def test_failed_requested_symbol_read_allows_truthful_no_action_answer(monkeypatch):
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "SPACEX"}),
        _text_response(
            "SpaceX is private and has no publicly traded TradeWave symbol, "
            "so I can't load it."
        ),
    ]

    text, actions, calls = _run_sequence(
        monkeypatch,
        responses,
        message="load me the spacex latest",
        tool_result={"error": {"code": "not_found", "message": "symbol not found"}},
    )

    assert len(calls) == 2
    assert actions == []
    assert "SpaceX is private" in text
    assert "can't load it" in text


def test_no_action_explanation_requires_a_matching_failed_read(monkeypatch):
    explanation = _text_response(
        "SpaceX is private and has no publicly traded TradeWave symbol, so I can't load it."
    )
    responses = [dict(explanation) for _ in range(tara_gateway._MAX_TOOL_ROUNDS)]

    text, actions, calls = _run_sequence(
        monkeypatch,
        responses,
        message="load me the spacex latest",
    )

    assert len(calls) == tara_gateway._MAX_TOOL_ROUNDS
    assert actions == []
    assert "SpaceX is private" not in text
    assert "haven't changed the chart" in text


def test_failed_symbol_read_does_not_allow_a_future_load_promise(monkeypatch):
    responses = [
        _tool_response("read-1", "analyze_symbol", {"symbol": "SPACEX"}),
        _text_response("I'll load SpaceX as soon as it is available."),
        _text_response(
            "SpaceX is private and has no publicly traded TradeWave symbol, "
            "so I can't load it."
        ),
    ]

    text, actions, calls = _run_sequence(
        monkeypatch,
        responses,
        message="load me the spacex latest",
        tool_result={"error": "gateway 404"},
    )

    assert len(calls) == 3
    assert actions == []
    assert "as soon as" not in text
    assert "SpaceX is private" in text


def test_evidence_guard_matches_market_date_and_duration():
    action = {
        "type": "set_view",
        "spec": {
            "symbol": "TSLA",
            "market": "2",
            "entry_date": "2026-07-24",
            "days_out": 21,
        },
    }
    correct = {
        "symbol": "TSLA",
        "market": "2",
        "setup": {"entry_date": "2026-07-24", "hold_days": 21},
        "headline": "TSLA long - Won 8/10 years, avg +4.2%.",
    }
    other_duration = {
        "symbol": "TSLA",
        "market": "2",
        "setup": {"entry_date": "2026-07-24", "hold_days": 45},
        "headline": "TSLA long - Won 4/10 years, avg +1.0%.",
    }
    fixed = tara_gateway._ensure_load_named(
        "TSLA won 4 of 10 years.",
        [action],
        {"TSLA": other_duration},
        [correct, other_duration],
    )
    assert "8 of the last 10" in fixed
    assert "4 of 10" not in fixed


def test_correct_win_count_does_not_mask_wrong_average_or_sharpe():
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    action = {"type": "set_view", "spec": spec}
    exact = {
        "symbol": "TSLA",
        "market": "2",
        "direction": "long",
        "setup": {"entry_date": "2026-07-24", "hold_days": 21},
        "stats": {
            "historical_win_rate": 0.8,
            "avg_return_pct": 4.2,
            "sharpe_ratio": 1.1,
            "years": 10,
        },
        "headline": "TSLA long - Won 8/10 years, avg +4.2%, Sharpe 1.1.",
    }

    fixed = tara_gateway._ensure_load_named(
        "TSLA won 8 of 10 years, avg +12%, Sharpe 9.9.",
        [action],
        {"TSLA": exact},
        [exact],
    )

    assert "8 of the last 10" in fixed
    assert "avg +4.2%" in fixed
    assert "Sharpe 1.10" in fixed
    assert "+12%" not in fixed
    assert "9.9" not in fixed

    correct = "TSLA won 8 of 10 years, avg +4.2%, Sharpe 1.1."
    assert tara_gateway._ensure_load_named(
        correct,
        [action],
        {"TSLA": exact},
        [exact],
    ) == correct


def test_partial_refresh_never_uses_unrelated_same_symbol_card():
    action = {"type": "set_view", "spec": {"symbol": "TSLA"}}
    current_view = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
        "view_ready": True,
        "yearly_results": [
            {"year": 2017 + index, "return_pct": value}
            for index, value in enumerate([4, 3, 2, 1, 5, 6, 7, 8, -1, -2])
        ],
    }
    unrelated = {
        "symbol": "TSLA",
        "market": "2",
        "setup": {"entry_date": "2026-09-01", "hold_days": 45},
        "headline": "TSLA long - Won 4/10 years, avg +1.0%.",
    }

    fixed = tara_gateway._ensure_load_named(
        "TSLA won 4 of 10 years.",
        [action],
        {"TSLA": unrelated},
        [unrelated],
        current_view=current_view,
    )

    assert "8 of the last 10" in fixed
    assert "4 of 10" not in fixed


def test_partial_refresh_without_exact_current_evidence_uses_neutral_text():
    action = {"type": "set_view", "spec": {"symbol": "TSLA"}}
    current_view = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
        "view_ready": True,
    }
    unrelated = {
        "symbol": "TSLA",
        "market": "2",
        "setup": {"entry_date": "2026-09-01", "hold_days": 45},
        "headline": "TSLA long - Won 4/10 years, avg +1.0%.",
    }

    fixed = tara_gateway._ensure_load_named(
        "TSLA won 4 of 10 years.",
        [action],
        {"TSLA": unrelated},
        [unrelated],
        current_view=current_view,
    )

    assert fixed == "<b>TSLA</b> chart request."


def test_valid_same_view_refresh_is_preserved(monkeypatch):
    current_view = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
        "view_ready": True,
        "yearly_results": [
            {"year": 2017 + index, "return_pct": value}
            for index, value in enumerate([4, 3, 2, 1, 5, 6, 7, 8, -1, -2])
        ],
    }
    responses = [
        _tool_response("view-1", "update_view", {"symbol": "TSLA"}),
        _text_response("TSLA won 8 of 10 years."),
    ]

    text, actions, _ = _run_sequence(
        monkeypatch,
        responses,
        message="reload TSLA",
        current_view=current_view,
    )

    assert [action["spec"] for action in actions] == [{"symbol": "TSLA"}]
    assert "8 of 10" in text


def test_malformed_native_tool_input_fails_without_crashing(monkeypatch):
    responses = [
        _tool_response("bad-1", "analyze_symbol", ["not", "an", "object"]),
        _text_response("Here is a safe answer."),
    ]
    text, actions, _ = _run_sequence(
        monkeypatch,
        responses,
        message="hello",
    )
    assert actions == []
    assert text == "Here is a safe answer."


def test_max_rounds_never_make_an_extra_toolless_model_call(monkeypatch):
    responses = [
        _tool_response("read-%d" % i, "analyze_symbol", {"symbol": "TSLA"})
        for i in range(tara_gateway._MAX_TOOL_ROUNDS)
    ]
    text, actions, calls = _run_sequence(
        monkeypatch,
        responses,
        message="analyze TSLA",
    )
    assert len(calls) == tara_gateway._MAX_TOOL_ROUNDS
    assert actions == []
    assert "haven't changed the chart" in text


@pytest.fixture
def audit_app(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "tara-test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    app.register_blueprint(chatbot.chatbot_bp, url_prefix="/chatbot")
    monkeypatch.setattr(chatbot, "ACTION_AUDIT_LOG", str(tmp_path / "tara-actions.jsonl"))
    monkeypatch.setattr(chatbot, "QUESTION_LOG", str(tmp_path / "tara-questions.jsonl"))
    return app


def _token(app):
    return jwt.encode(
        {
            "user": "audit-user",
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "exp": int(time.time()) + 300,
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def _proof(app, spec):
    turn_id = "a" * 32
    action_id = "b" * 32
    expires_at = int(time.time()) + 300
    manifest = chatbot._action_manifest([{
        "action_id": action_id,
        "spec": spec,
    }])
    with app.app_context():
        receipt = chatbot._action_receipt(
            "audit-user", turn_id, action_id, spec, expires_at, manifest
        )
    return turn_id, {
        "action_id": action_id,
        "receipt": receipt,
        "manifest": manifest,
        "spec": spec,
        "expires_at": expires_at,
    }


def test_action_audit_rejects_zero_point_chart_success(audit_app, monkeypatch):
    monkeypatch.setattr(chatbot, "_claim_action_result", lambda *args: (True, "memory"))
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    turn_id, proof = _proof(audit_app, spec)
    response = audit_app.test_client().post("/chatbot/action_result", json={
        "token": _token(audit_app),
        "turn_id": turn_id,
        "actions": [proof],
        "status": "succeeded",
        "reason": "",
        "observed_view": spec,
        "data_points": 0,
        "displayed_response": "TSLA loaded on the chart.",
    })
    assert response.status_code == 409


def test_action_audit_records_displayed_response_and_is_idempotent(
    audit_app, monkeypatch
):
    seen = set()

    def claim(key, expires_at):
        if key in seen:
            return False, "memory"
        seen.add(key)
        return True, "memory"

    monkeypatch.setattr(chatbot, "_claim_action_result", claim)
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    turn_id, proof = _proof(audit_app, spec)
    payload = {
        "token": _token(audit_app),
        "turn_id": turn_id,
        "actions": [proof],
        "status": "succeeded",
        "reason": "",
        "observed_view": spec,
        "data_points": 10,
        "displayed_response": "TSLA evidence. TSLA loaded on the chart.",
    }
    client = audit_app.test_client()
    assert client.post("/chatbot/action_result", json=payload).status_code == 200
    duplicate = client.post("/chatbot/action_result", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.get_json()["duplicate"] is True

    rows = [
        json.loads(line)
        for line in open(chatbot.ACTION_AUDIT_LOG, encoding="utf-8")
    ]
    assert len(rows) == 1
    assert rows[0]["displayed_response"] == payload["displayed_response"]
    assert rows[0]["expected_spec"] == spec


def test_action_audit_rejects_an_incomplete_manifest(audit_app):
    turn_id = "a" * 32
    expires_at = int(time.time()) + 300
    rows = [
        {"action_id": "b" * 32, "spec": {"market": "2"}},
        {"action_id": "c" * 32, "spec": {"years": 20}},
    ]
    manifest = chatbot._action_manifest(rows)
    proofs = []
    with audit_app.app_context():
        for row in rows:
            proofs.append({
                "action_id": row["action_id"],
                "receipt": chatbot._action_receipt(
                    "audit-user",
                    turn_id,
                    row["action_id"],
                    row["spec"],
                    expires_at,
                    manifest,
                ),
                "manifest": manifest,
                "spec": row["spec"],
                "expires_at": expires_at,
            })
    response = audit_app.test_client().post("/chatbot/action_result", json={
        "token": _token(audit_app),
        "turn_id": turn_id,
        "actions": proofs[:1],
        "status": "failed",
        "reason": "client_validation_failed",
        "observed_view": {},
        "data_points": 0,
        "displayed_response": "The request was rejected.",
    })
    assert response.status_code == 400


def test_action_audit_rejects_non_object_json(audit_app):
    response = audit_app.test_client().post(
        "/chatbot/action_result?token=" + _token(audit_app),
        json=["not", "an", "object"],
    )
    assert response.status_code == 400


def test_chat_rejects_non_object_and_untyped_message_without_calling_model(audit_app):
    client = audit_app.test_client()
    token = _token(audit_app)
    non_object = client.post(
        "/chatbot/chat?token=" + token,
        json=["not", "an", "object"],
    )
    assert non_object.status_code == 400

    untyped = client.post("/chatbot/chat", json={
        "token": token,
        "message": {"unexpected": "object"},
        "history": [],
        "wave_viewer": {},
        "opportunities": [],
    })
    assert untyped.status_code == 400

    oversized = client.post("/chatbot/chat", json={
        "token": token,
        "message": "x" * 2001,
        "history": [],
        "wave_viewer": {},
        "opportunities": [],
    })
    assert oversized.status_code == 400

    malformed_context = client.post("/chatbot/chat", json={
        "token": token,
        "message": "load TSLA",
        "history": {"not": "a list"},
        "wave_viewer": {},
        "opportunities": [],
    })
    assert malformed_context.status_code == 400

    responses = [non_object, untyped, oversized, malformed_context]
    rows = [
        json.loads(line)
        for line in open(chatbot.QUESTION_LOG, encoding="utf-8")
    ]
    assert len(rows) == len(responses)
    assert [row["turn_id"] for row in rows] == [
        response.get_json()["turn_id"] for response in responses
    ]
    assert rows[0]["question"] == "[invalid request body]"
    assert rows[1]["question"] == "[invalid message type: dict]"
    assert rows[2]["question"] == "x" * 2000
    assert rows[3]["question"] == "load TSLA"
    assert all(
        row["protocol_trace"][0]["event"] == "validation_failure"
        for row in rows
    )


def test_blank_chat_turn_is_correlated_and_audited(audit_app):
    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": "   ",
        "history": [],
        "wave_viewer": {},
        "opportunities": [],
    })

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["turn_id"]) == 32
    assert len(body["suggestions"]) == 3
    assert body["suggestions"][2]["prompt"] == (
        "Show me the Buy & Hold workflow for long-term investors"
    )
    row = json.loads(open(chatbot.QUESTION_LOG, encoding="utf-8").readline())
    assert row["turn_id"] == body["turn_id"]
    assert row["protocol_trace"] == [{"event": "blank_message"}]


def test_prompt_does_not_substitute_seasonal_rank_for_live_market_data():
    prompt = chatbot.build_system_prompt({}, [])
    prompt = "\n".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in prompt
    ) if isinstance(prompt, list) else prompt

    assert "do NOT provide intraday trading volume" in prompt
    assert "cannot verify that live criterion" in prompt
    assert "never the overall market trend" in prompt
    assert "Private companies" in prompt


@pytest.mark.parametrize("message", [
    "what about AAPL?",
    "does AAPL make money?",
])
def test_tools_disabled_fails_closed_for_implicit_chart_requests(
    audit_app, monkeypatch, message
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", False)
    monkeypatch.setattr(
        chatbot,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("no-tools chart request reached the model"),
    )

    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {},
        "opportunities": [],
    })

    assert response.status_code == 200
    assert response.get_json()["actions"] == []
    assert "controls are temporarily unavailable" in response.get_json()["reply"]


@pytest.mark.parametrize("message", [
    "what should I trade?",
    "recommend me a trade",
])
def test_tools_disabled_keeps_broad_trade_request_in_discovery_funnel(
    audit_app, monkeypatch, message
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", False)
    monkeypatch.setattr(
        chatbot,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("no-tools discovery request reached the model"),
    )

    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {},
        "opportunities": [],
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["actions"] == []
    assert "curated ETF screen or S&P 500 stock candidates" in body["reply"]
    assert [item["label"] for item in body["suggestions"]] == [
        "Find ETF candidates", "Find stock candidates", "Study weak periods",
    ]


def test_tools_disabled_preserves_live_data_capability_boundary(
    audit_app, monkeypatch
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", False)
    monkeypatch.setattr(
        chatbot,
        "send_claude_messages",
        lambda *args, **kwargs: pytest.fail("unsupported live-data request reached the model"),
    )

    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": "What is the best high-volume stock today?",
        "history": [{
            "role": "user",
            "content": "What is the best high-volume stock today?",
        }],
        "wave_viewer": {},
        "opportunities": [],
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["actions"] == []
    assert "can't verify intraday volume" in body["reply"]
    assert "seasonal-pattern scan" in body["reply"]


def test_chat_route_closes_production_long_or_short_followup(
    audit_app, monkeypatch
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", True)
    monkeypatch.setattr(
        chatbot,
        "run_chat_with_tools",
        lambda *args, **kwargs: pytest.fail("safe loaded-pattern reply reached gateway model loop"),
    )
    message = "do i long or short?"
    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {
            "symbol": "AVGO",
            "market": "2",
            "direction": "long",
            "entry_date": "2026-07-23",
            "days_out": 21,
            "view_ready": True,
            "stats": {
                "Num Winners": "8",
                "Num Losers": "2",
                "Avg Profit - All": "+4.2%",
                "Sharpe Ratio": "1.4",
            },
        },
        "opportunities": [],
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["actions"] == []
    assert "historical <b>Long</b> pattern" in body["reply"]
    assert "not today's market direction or a forecast" in body["reply"]
    audit_row = json.loads(open(chatbot.QUESTION_LOG, encoding="utf-8").readline())
    assert audit_row["protocol_trace"] == [{
        "event": "loaded_pattern_suitability_boundary",
        "symbol": "AVGO",
    }]


def test_backend_turn_exception_is_written_to_question_audit(
    audit_app, monkeypatch
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", True)
    def fail_provider(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(chatbot, "run_chat_with_openai_tools", fail_provider)
    monkeypatch.setattr(chatbot, "run_chat_with_tools", fail_provider)
    response = audit_app.test_client().post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": "load TSLA",
        "history": [{"role": "user", "content": "load TSLA"}],
        "wave_viewer": {},
        "opportunities": [],
    })
    assert response.status_code == 200
    assert response.get_json()["actions"] == []
    rows = [
        json.loads(line)
        for line in open(chatbot.QUESTION_LOG, encoding="utf-8")
    ]
    assert len(rows) == 1
    assert rows[0]["question"] == "load TSLA"
    assert rows[0]["response"] == "Sorry, something went wrong on my end. Please try again."
    assert any(
        event.get("event") == "backend_exception"
        for event in rows[0]["protocol_trace"]
    )


def test_chat_action_receipt_round_trip_writes_joined_audits(
    audit_app, monkeypatch
):
    spec = {
        "symbol": "TSLA",
        "market": "2",
        "entry_date": "2026-07-24",
        "days_out": 21,
    }
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", True)
    monkeypatch.setattr(
        chatbot,
        "run_chat_with_tools",
        lambda *args, **kwargs: (
            "TSLA won 8 of 10 years with an average +4.2% return.",
            [{
                "action_id": "b" * 32,
                "type": "set_view",
                "status": "validated",
                "spec": spec,
            }],
        ),
    )
    monkeypatch.setattr(
        chatbot,
        "run_chat_with_openai_tools",
        lambda *args, **kwargs: (
            "TSLA won 8 of 10 years with an average +4.2% return.",
            [{
                "action_id": "b" * 32,
                "type": "set_view",
                "status": "validated",
                "spec": spec,
            }],
        ),
    )
    monkeypatch.setattr(
        chatbot,
        "_claim_action_result",
        lambda *args: (True, "memory"),
    )
    client = audit_app.test_client()
    chat_response = client.post("/chatbot/chat", json={
        "token": _token(audit_app),
        "message": "load TSLA",
        "history": [{"role": "user", "content": "load TSLA"}],
        "wave_viewer": {},
        "opportunities": [],
    })
    assert chat_response.status_code == 200
    body = chat_response.get_json()
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert len(action["action_manifest"]) == 64
    assert len(action["receipt"]) == 64

    terminal = client.post("/chatbot/action_result", json={
        "token": _token(audit_app),
        "turn_id": body["turn_id"],
        "actions": [{
            "action_id": action["action_id"],
            "receipt": action["receipt"],
            "manifest": action["action_manifest"],
            "spec": action["spec"],
            "expires_at": action["receipt_expires_at"],
        }],
        "status": "succeeded",
        "reason": "",
        "observed_view": spec,
        "data_points": 375,
        "displayed_response": (
            "TSLA won 8 of 10 years. "
            "TSLA pattern and seasonal graph loaded in the Wave Viewer."
        ),
    })
    assert terminal.status_code == 200

    question_row = json.loads(
        open(chatbot.QUESTION_LOG, encoding="utf-8").readline()
    )
    action_row = json.loads(
        open(chatbot.ACTION_AUDIT_LOG, encoding="utf-8").readline()
    )
    assert question_row["turn_id"] == action_row["turn_id"] == body["turn_id"]
    assert (
        question_row["actions"][0]["action_manifest"]
        == action_row["action_manifest"]
        == action["action_manifest"]
    )
