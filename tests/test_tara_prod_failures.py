"""TW-TASK-0031: Tara failure classes found in real production conversations.

Each class is tested with the production phrasing (question text only, no customer
data) and with generalized variants, because the fixes target the class and not the
literal string. Engine and model seams are replaced with small stand-ins; no expected
statistic is computed here.
"""
import datetime
import re
import sys
import time
from pathlib import Path

import jwt
import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver/appserver"))

import chatbot  # noqa: E402
import tara_answer_planner as planner  # noqa: E402
import tara_gateway  # noqa: E402
import tara_prompt_context  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = datetime.date(2026, 11, 17)


def _plain(reply):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", reply or "")).strip()


def _words(reply):
    return len(_plain(reply).split())


def _loaded(symbol="ATO", direction="long", start="2026-11-17", days="24", returns=None,
            stats=None):
    returns = returns or [4.1, 2.2, 6.3, 1.8, 3.9, 5.2, 2.7, 8.4, 3.1, 4.6]
    first = 2026 - len(returns)
    return {
        "symbol": symbol, "market": "2", "direction": direction, "start_date": start,
        "days_out": days, "years": str(len(returns)), "selection_origin": "user_defined",
        "view_ready": True,
        "yearly_results": [
            {"year": first + i, "underlying_return_pct": value,
             "upside_excursion_pct": abs(value) + 2.0, "downside_excursion_pct": -1.5}
            for i, value in enumerate(returns)
        ],
        "stats": dict({"Sharpe Ratio": "1.87", "Sharpe Ratio2": "2.85"}, **(stats or {})),
    }


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(planner, "_today", lambda: TODAY)
    monkeypatch.setattr(tara_gateway, "_market_today", lambda: TODAY)


def _text_response(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _tool_response(tool_id, name, tool_input):
    return {"stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}


def _run(monkeypatch, responses, message, run_tool=None, current_view=None, **kwargs):
    calls = []

    def fake_send(*args, **send_kwargs):
        calls.append(send_kwargs)
        return responses.pop(0)

    monkeypatch.setattr(tara_gateway, "send_claude_messages", fake_send)
    monkeypatch.setattr(
        tara_gateway, "run_tool",
        run_tool or (lambda name, tool_input, user_id: pytest.fail("unexpected tool call")),
    )
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": message}], "system", "user-1", "model",
        current_view=current_view or {}, user_token="token", **kwargs,
    )
    return text, actions, calls


# ---------------------------------------------------------------------------
# Class 1: "show me ..." that is not a chart command
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "Show me my usage so far and which plan actually fits - including if free Explorer is enough.",
    "show my Z probability for next 3 months",
    "show me how the win rate is calculated",
    "Show me which plan I need for crypto",
    "open settings",
    "can I see the pricing",
    "display the filter options",
    "show me the difference between Sharpe and TWR",
    "SHOW ME MY USAGE",
])
def test_show_requests_about_ordinary_things_are_not_chart_commands(message):
    assert tara_gateway.classify_view_intent(message) is None


@pytest.mark.parametrize("message", [
    "show me AAPL", "show me aapl", "show nvda", "open TSLA", "load MSFT", "pull up roku",
    "can I see the SPY", "display QQQ", "show me ALL", "Show me Z",
])
def test_show_requests_naming_a_ticker_stay_chart_commands(message):
    assert tara_gateway.classify_view_intent(message) == "chart"


def test_clean_answer_to_a_show_question_is_not_replaced_by_a_chart_error(monkeypatch):
    # "dividends" is not in the common-word list, so this still classifies as a soft
    # chart intent. The model is nudged once and then its real answer is kept.
    answer = "TradeWave does not track dividend payments; its returns are price based."
    text, actions, calls = _run(
        monkeypatch,
        [_text_response(answer), _text_response(answer)],
        "show me dividends for this stock",
    )
    assert actions == []
    assert text == answer
    assert "couldn't send the complete chart action" not in text
    assert len(calls) == 2


def test_explicit_load_without_an_action_still_fails_closed(monkeypatch):
    answer = "TSLA has a solid seasonal record."
    text, actions, _ = _run(
        monkeypatch, [_text_response(answer) for _ in range(tara_gateway._MAX_TOOL_ROUNDS)],
        "load TSLA",
    )
    assert actions == []
    assert "haven't changed the chart" in text


def test_show_answer_that_claims_a_load_is_still_rejected(monkeypatch):
    claim = "AAPL is now loaded on the chart."
    text, actions, _ = _run(
        monkeypatch, [_text_response(claim) for _ in range(tara_gateway._MAX_TOOL_ROUNDS)],
        "show me aapl",
    )
    assert actions == []
    assert "loaded on the chart" not in text


# ---------------------------------------------------------------------------
# Class 2: AI-score ranking and filtering
# ---------------------------------------------------------------------------

def _scan_card(symbol, win_prob=None, ais=None, pred=None, avg=5.0, sharpe=2.0):
    card = {
        "symbol": symbol, "direction": "long",
        "headline": "%s long - enter ~Nov 17, hold 20d. Won 9/10 years, avg +%.1f%%, Sharpe %.1f."
                    % (symbol, avg, sharpe),
        "market": {"id": "2", "name": "S&P 500 STOCKS"},
        "setup": {"entry_date": "2026-11-17", "hold_days": 20},
        "stats": {"historical_win_rate": 0.9, "avg_return_pct": avg, "sharpe_ratio": sharpe,
                  "years": "10"},
        "wave_viewer": {"url": "https://example.invalid/" + "x" * 300},
        "tier_notes": "ML score shown." if win_prob is not None else
                      "ML score is currently unavailable for this setup.",
        "ml": None,
    }
    if win_prob is not None:
        card["ml"] = {"ml_score": ais, "ml_win_prob": win_prob, "pred_return_pct": pred,
                      "pred_mfe_pct": 9.0}
    return card


def _scan_tool(cards, seen):
    def run_tool(name, tool_input, user_id):
        seen.append((name, dict(tool_input)))
        return {"opportunities": [dict(card) for card in cards], "markets_scanned": ["2"]}
    return run_tool


@pytest.mark.parametrize("message, tool_input, expected_first", [
    ("best 10 opportunities for today based on AIS for highest probability",
     {"markets": "2", "limit": 10}, "CCC"),
    ("Give me ai ranked results", {"markets": "2"}, "CCC"),
    ("rank the S&P 500 by AI score", {"markets": "2", "rank_by": "ais"}, "BBB"),
    ("top setups by predicted return", {"markets": "2", "rank_by": "pred_return"}, "AAA"),
])
def test_scan_ranks_by_the_engines_ai_values(monkeypatch, message, tool_input, expected_first):
    cards = [
        _scan_card("AAA", win_prob=0.70, ais=80.0, pred=6.5),
        _scan_card("BBB", win_prob=0.80, ais=96.0, pred=3.0),
        _scan_card("CCC", win_prob=0.84, ais=95.0, pred=5.5),
        _scan_card("DDD"),                      # no AI score delivered for this row
    ]
    seen, notes = [], []
    monkeypatch.setattr(tara_gateway, "run_tool", _scan_tool(cards, seen))
    out = tara_gateway._execute_tara_tool(
        "find_best_opportunities", tool_input, "user-1", [], {}, [],
        latest_user_text=message, turn_notes=notes, user_token="token",
    )
    assert seen[0][1]["rank_by"] == "ml"         # asked the gateway for AI-scored rows
    rows = out["opportunities"]
    assert rows[0]["symbol"] == expected_first
    assert [row["symbol"] for row in rows].count("DDD") == 0
    assert out["ai_scores"]["delivered"] is True
    assert rows[0]["ai"]["ai_win_prob_pct"] in (70, 80, 84)
    assert all("wave_viewer" not in row for row in rows)
    assert notes == []


def test_predicted_return_floor_filters_on_predr_not_the_historical_average(monkeypatch):
    cards = [
        _scan_card("HIAVG", win_prob=0.80, ais=90.0, pred=2.0, avg=13.3),
        _scan_card("HIPRED", win_prob=0.75, ais=85.0, pred=6.1, avg=3.0),
    ]
    seen = []
    monkeypatch.setattr(tara_gateway, "run_tool", _scan_tool(cards, seen))
    out = tara_gateway._execute_tara_tool(
        "find_best_opportunities",
        {"markets": "2", "min_days": 40, "max_days": 100, "min_pred_return": 5},
        "user-1", [], {}, [],
        latest_user_text="best setup today with prdicted profit of minimum 5% and holding 40-100 ays",
        turn_notes=[], user_token="token",
    )
    assert [row["symbol"] for row in out["opportunities"]] == ["HIPRED"]
    assert "min_pred_return" not in seen[0][1] and "min_avg_return" not in seen[0][1]


def test_missing_ai_scores_are_stated_and_never_silently_replaced(monkeypatch):
    cards = [_scan_card("HLT", avg=13.3, sharpe=3.1), _scan_card("CIEN", avg=16.7, sharpe=2.7)]

    def run_tool(name, tool_input, user_id):
        return {"opportunities": [dict(card) for card in cards], "markets_scanned": ["2"]}

    text, actions, _ = _run(
        monkeypatch,
        [
            _tool_response("scan-1", "find_best_opportunities",
                           {"markets": "2", "min_avg_return": 5, "min_days": 40, "max_days": 100}),
            _text_response("<b>HLT long</b> - meets your minimum 5% filter, avg +13.3%."),
        ],
        "best setup today with predicted profit of minimum 5% and holding 40-100 days",
        run_tool=run_tool,
    )
    plain = _plain(text)
    assert plain.startswith("AI scores were not available for these setups")
    assert "historical, not predicted returns" in plain
    assert "HLT" in plain


def test_tool_result_trimming_keeps_ai_values_and_notices():
    rows = [dict(_scan_card("S%02d" % i, win_prob=0.8, ais=90.0, pred=4.0),
                 ai={"ais": 90.0, "ai_win_prob_pct": 80, "pred_return_pct": 4.0},
                 padding="y" * 2000) for i in range(12)]
    payload = tara_gateway._bounded_json({
        "opportunities": rows, "ai_scores": {"delivered": True, "ranked_by": "AIS"},
        "threshold_adjusted": {"used_min_winning_years": 6},
    })
    assert len(payload) <= tara_gateway._TOOL_RESULT_CAP
    assert '"ai_win_prob_pct": 80' in payload
    assert '"ranked_by": "AIS"' in payload and "threshold_adjusted" in payload


def test_scan_schema_exposes_ai_ranking_fields():
    schema = next(tool for tool in tara_gateway.TOOLS if tool["name"] == "find_best_opportunities")
    properties = schema["input_schema"]["properties"]
    assert set(properties["rank_by"]["enum"]) >= {"ai_win_prob", "ais", "pred_return"}
    assert "min_pred_return" in properties and "min_ai_win_prob" in properties
    assert "NEVER present the historical average return as a predicted return" in schema["description"]


# ---------------------------------------------------------------------------
# Class 3: "should I" and "recent" must not hijack ordinary questions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "can you explain me how to read the tradewave chart above on Win% and PredR ? what should i be looking?",
    "what should stocks should i look at for this week if im looking for bigger gains but don't have a huge amount of capital?",
    "tell me about the chart and the profitability of getting in this trade at $167, when and where should I get out",
    "how should I read Win%?",
    "should I use 10 or 20 years?",
    "when should I exit historically?",
    "what should I look at first on this screen?",
    "which lookback should we use for a short pattern?",
    "what do you recommend I read to learn seasonality?",
    "how should I trade a short pattern in general?",
    "when should I buy AAPL?",
])
def test_ordinary_questions_are_not_personal_advice_requests(message):
    wave = _loaded()
    assert planner.is_pattern_advice_question(message, wave) is False
    assert planner.build_advice_safe_reply(message, wave) is None


@pytest.mark.parametrize("message", [
    "Should I trade this pattern?", "should i buy this", "so, should we take it?",
    "would you take this trade?", "do you recommend buying it?", "is this a good trade?",
    "This looks strong. Should I get in?", "should I just hold it", "how much should I invest in this?",
    "is it worth taking?",
])
def test_real_trade_decisions_get_evidence_then_one_short_boundary(message):
    reply = planner.build_advice_safe_reply(message, _loaded(), current_year=2026)
    assert reply is not None
    plain = _plain(reply)
    assert plain.startswith("Read: ATO long, Nov 17 to Dec 10")
    assert "profitable in 10 of 10 completed years" in plain
    assert plain.endswith("Whether to take the trade is your decision; I can't make it for you.")
    assert _words(reply) < 130
    assert "Cycle context" not in plain and "Payoff and path" not in plain


def test_exit_question_states_the_window_exit_date_plainly():
    reply = planner.build_deterministic_reply(
        "tell me about the chart and the profitability of getting in this trade at $167, "
        "when and where should I get out",
        _loaded(), {}, current_year=2026,
    )
    plain = _plain(reply)
    assert plain.startswith("The historical window exits on Dec 10, 2026.")
    assert "no price targets or stop levels" in plain
    assert "profitable in 10 of 10 completed years" in plain
    assert "do not depend on the price you enter at" in plain
    assert "can't decide" not in plain


@pytest.mark.parametrize("message", [
    "when does this pattern end?", "what is the exit date?", "when should I sell?",
    "is there a price target?", "where do I take profits?",
])
def test_exit_timing_variants_use_the_same_dated_answer(message):
    reply = planner.build_deterministic_reply(message, _loaded(), {}, current_year=2026)
    assert "The historical window exits on Dec 10, 2026." in _plain(reply)


@pytest.mark.parametrize("message", [
    "What about recent projections, for example where did you project NVDA price to be 30 days ago and how does that match where it is now ?",
    "any recent news on this?",
    "what was the most recent earnings date?",
    "show me the latest price target",
])
def test_recent_about_another_subject_is_not_a_record_recency_question(message):
    assert planner.is_pattern_recency_question(message, _loaded()) is False


@pytest.mark.parametrize("message", [
    "Has this weakened recently?", "how has it done lately?", "what about the last 5 years?",
    "are the recent years weaker?", "is it still working?", "show me the latest results",
])
def test_recency_of_the_record_is_still_recognized(message):
    assert planner.is_pattern_recency_question(message, _loaded()) is True


# ---------------------------------------------------------------------------
# Class 4: sector words
# ---------------------------------------------------------------------------

def _fake_screen(seen):
    def build_screen_command(text, token, today=None, table_market=None):
        seen.append(text)
        return {
            "reply": '<div class="tara-analysis"><div class="tara-analysis-section">LIST</div></div>',
            "actions": [{"type": "set_view", "spec": {"market": "1"}}],
            "trace": {"event": "research_screen"},
        }
    return build_screen_command


@pytest.mark.parametrize("message", [
    "Which tech stocks tend to rise this time of year?",
    "best technology stocks this month",
    "which semiconductor names are bearish this week?",
    "Which Tech companies are bullish now",
])
def test_tech_screen_uses_nasdaq_100_and_says_it_is_a_proxy(monkeypatch, message):
    import tara_research
    seen = []
    monkeypatch.setattr(tara_research, "build_screen_command", _fake_screen(seen))
    command = tara_gateway.build_sector_screen_command(
        message, "token", investor_intent="seasonal_stock", table_market="2")
    assert "NASDAQ 100 stocks" in seen[0] and not re.search(r"\btech", seen[0], re.I)
    plain = _plain(command["reply"])
    assert plain.startswith("Screened on the NASDAQ 100, a tech-heavy index.")
    assert "no sector tags" in plain and "LIST" in plain
    assert command["trace"]["event"] == "sector_proxy_screen"
    assert command["trace"]["universe"] == "NASDAQ 100"


@pytest.mark.parametrize("message, sector, etf", [
    ("which energy stocks are bearish this month?", "energy", "XLE"),
    ("best bank stocks this time of year", "financial", "XLF"),
    ("which healthcare names tend to rise now", "health care", "XLV"),
])
def test_other_sectors_say_the_list_is_not_sector_filtered(monkeypatch, message, sector, etf):
    import tara_research
    seen = []
    monkeypatch.setattr(tara_research, "build_screen_command", _fake_screen(seen))
    command = tara_gateway.build_sector_screen_command(message, "token", investor_intent=None)
    assert "S&P 500 stocks" in seen[0]
    plain = _plain(command["reply"])
    assert "no sector tags, so I cannot filter to %s stocks" % sector in plain
    assert 'analyze %s' % etf in plain


@pytest.mark.parametrize("message", [
    "Show me bullish S&P 500 stock patterns this time of year",
    "which NASDAQ tech stocks rise this month",
    "which stocks tend to rise this time of year?",
    "is XLK tech stocks seasonal now",
    "what is a tech stock",
])
def test_sector_route_leaves_other_questions_alone(monkeypatch, message):
    import tara_research
    monkeypatch.setattr(tara_research, "build_screen_command", lambda *a, **k: None)
    assert tara_gateway.build_sector_screen_command(message, "token") is None


# ---------------------------------------------------------------------------
# Class 5: named symbols (no detected pattern, aliases)
# ---------------------------------------------------------------------------

def _plain_window_card(symbol, market="2"):
    return {"card": {
        "symbol": symbol, "direction": "long", "market": {"id": market, "name": "M"},
        "setup": {"entry_date": TODAY.isoformat(), "hold_days": 30},
        "stats": {"historical_win_rate": 0.5, "avg_return_pct": -0.29, "years": "8"},
        "headline": "%s long - enter ~Nov 17, hold 30d. Won 4/8 years, avg -0.3%%, Sharpe -0.0." % symbol,
    }, "other_setups": [{"symbol": symbol}]}


NO_SETUP = {
    "error": "gateway 404", "code": "not_found",
    "message": "no seasonal setup for 'ROKU' in market '2' enters today. To study any window "
               "for this symbol, pass entry_date with days_out, or a period preset.",
}


@pytest.mark.parametrize("symbol", ["ROKU", "ABNB", "COIN"])
def test_symbol_without_a_detected_pattern_gets_a_labelled_plain_window(monkeypatch, symbol):
    seen = []

    def run_tool(name, tool_input, user_id):
        seen.append(dict(tool_input))
        return dict(NO_SETUP) if "entry_date" not in tool_input else _plain_window_card(symbol)

    monkeypatch.setattr(tara_gateway, "run_tool", run_tool)
    notes = []
    out, used = tara_gateway._analyze_with_recoveries({"symbol": symbol}, "user-1", "token", notes)
    assert seen[1]["entry_date"] == TODAY.isoformat() and seen[1]["days_out"] == 30
    assert out["card"]["symbol"] == symbol
    assert "no qualifying seasonal pattern for %s" % symbol in out["detector_note"]
    assert "not a detected pattern" in out["detector_note"]
    assert out["other_setups"] == []
    assert notes and notes[0]["key"] == "no_detected_pattern"


def test_no_detected_pattern_notice_reaches_the_user_even_if_the_model_omits_it(monkeypatch):
    def run_tool(name, tool_input, user_id):
        return dict(NO_SETUP) if "entry_date" not in tool_input else _plain_window_card("ROKU")

    spec = {"symbol": "ROKU", "market": "2", "entry_date": TODAY.isoformat(), "days_out": 30}
    text, actions, _ = _run(
        monkeypatch,
        [
            _tool_response("read-1", "analyze_symbol", {"symbol": "ROKU"}),
            _tool_response("view-1", "update_view", spec),
            _text_response("ROKU long - won 4/8 years, avg -0.3%."),
        ],
        "is roku a good buiyng opportunity right now",
        run_tool=run_tool,
    )
    plain = _plain(text)
    assert "detector lists no qualifying seasonal pattern for ROKU" in plain
    assert "could not retrieve" not in plain.lower()
    assert actions and actions[0]["spec"]["symbol"] == "ROKU"


def test_pinned_window_or_outage_is_not_replaced_by_a_plain_window(monkeypatch):
    seen = []

    def run_tool(name, tool_input, user_id):
        seen.append(dict(tool_input))
        return {"error": "gateway unreachable"}

    monkeypatch.setattr(tara_gateway, "run_tool", run_tool)
    monkeypatch.setattr(tara_gateway, "_usd_pair_alias", lambda symbol, token: None)
    out, _ = tara_gateway._analyze_with_recoveries({"symbol": "ROKU"}, "user-1", "token", [])
    assert out == {"error": "gateway unreachable"} and len(seen) == 1


def _resolver(listings):
    def loopback(path, token, **kwargs):
        symbol = path.rsplit("/", 1)[-1]
        return 200, {"symbol": symbol, "matches": listings.get(symbol, [])}
    return loopback


METALS = {
    "XAUUSD": [{"resourceID": "8", "label": "FOREX ALL", "name": "Gold Spot US Dollar"}],
    "XAGUSD": [{"resourceID": "8", "label": "FOREX ALL", "name": "Silver Spot US Dollar"}],
    "XAU": [{"resourceID": "5", "label": "INDICES COMMON", "name": "Philadelphia Gold/Silver"},
            {"resourceID": "13", "label": "TORONTO STOCKS", "name": "GoldMoney Inc"}],
}


@pytest.mark.parametrize("tool_input, expected_symbol", [
    ({"symbol": "XAU"}, "XAUUSD"),
    ({"symbol": "xau", "market": "8"}, "XAUUSD"),
    ({"symbol": "XAG"}, "XAGUSD"),
    ({"symbol": "XAU", "market": "7"}, "XAUUSD"),     # commodities guess: XAU is not listed there
])
def test_bare_metal_code_is_read_as_its_listed_spot_pair(monkeypatch, tool_input, expected_symbol):
    seen = []
    monkeypatch.setattr(tara_gateway, "_loopback_json", _resolver(METALS))

    def run_tool(name, tool_input, user_id):
        seen.append(dict(tool_input))
        return _plain_window_card(tool_input["symbol"], market="8")

    monkeypatch.setattr(tara_gateway, "run_tool", run_tool)
    notes = []
    out, used = tara_gateway._analyze_with_recoveries(tool_input, "user-1", "token", notes)
    assert seen[0]["symbol"] == expected_symbol and seen[0]["market"] == "8"
    assert expected_symbol in out["symbol_note"] and "spot" in out["symbol_note"]
    assert notes[0]["key"] == "symbol_alias"


def test_explicit_index_market_keeps_the_xau_index(monkeypatch):
    seen = []
    monkeypatch.setattr(tara_gateway, "_loopback_json", _resolver(METALS))
    monkeypatch.setattr(tara_gateway, "run_tool",
                        lambda name, tool_input, user_id: seen.append(dict(tool_input))
                        or _plain_window_card("XAU", market="5"))
    out, _ = tara_gateway._analyze_with_recoveries(
        {"symbol": "XAU", "market": "5"}, "user-1", "token", [])
    assert seen[0] == {"symbol": "XAU", "market": "5"} and "symbol_note" not in out


def test_question_symbol_resolution_uses_the_spot_gold_alias(monkeypatch):
    monkeypatch.setattr(tara_gateway, "_loopback_json", _resolver(METALS))
    resolution = tara_gateway._resolve_question_symbol(
        "XAU", "when is XAU historically weak?", "token")
    assert resolution["status"] == "ok"
    assert (resolution["symbol"], resolution["market"]) == ("XAUUSD", "8")


def test_metal_alias_also_applies_to_the_pattern_list_tool(monkeypatch):
    seen = []
    monkeypatch.setattr(tara_gateway, "_loopback_json", _resolver(METALS))
    monkeypatch.setattr(tara_gateway, "run_tool",
                        lambda name, tool_input, user_id: seen.append(dict(tool_input))
                        or {"opportunities": []})
    notes = []
    out = tara_gateway._execute_tara_tool(
        "get_symbol_patterns", {"symbol": "XAG", "market": "9"}, "user-1", [], {}, [],
        turn_notes=notes, user_token="token", latest_user_text="best patterns for xag")
    assert seen[0]["symbol"] == "XAGUSD" and seen[0]["market"] == "8"
    assert "XAGUSD" in out["symbol_note"]


def test_pattern_list_outside_the_symbol_grid_falls_back_to_the_current_setup(monkeypatch):
    monkeypatch.setattr(tara_gateway, "_loopback_json", _resolver(METALS))

    def run_tool(name, tool_input, user_id):
        if name == "get_symbol_patterns":
            return {"error": "gateway 400", "code": "invalid_request",
                    "message": "Per-symbol seasonal pattern detection is not available for FOREX ALL."}
        return _plain_window_card(tool_input["symbol"], market="8")

    monkeypatch.setattr(tara_gateway, "run_tool", run_tool)
    cards, card_list = {}, []
    out = tara_gateway._execute_tara_tool(
        "get_symbol_patterns", {"symbol": "XAU", "market": "8"}, "user-1", [], cards, card_list,
        turn_notes=[], user_token="token", latest_user_text="patrones del xau")
    assert out["card"]["symbol"] == "XAUUSD"
    assert "no full pattern list" in out["pattern_list_note"]
    assert card_list and card_list[0]["symbol"] == "XAUUSD"


def test_win_record_uses_the_engines_completed_year_counts():
    card = {"symbol": "ROKU", "headline": "ROKU long - no high-conviction edge.",
            "stats": {"historical_win_rate": 0.5, "years": "10", "avg_return_pct": -0.29},
            "history": {"wins": 4, "years_tested": 8}}
    assert tara_gateway._card_headline_stats(card) == (4, 8, -0.29)
    assert "won 4 of the last 8 years" in tara_gateway._announce_line("ROKU", card)


def test_gateway_error_detail_is_preserved(monkeypatch):
    class Response:
        status_code = 404

        @staticmethod
        def json():
            return {"error": {"code": "not_found", "message": "no seasonal setup for 'ROKU'"}}

    monkeypatch.setattr(tara_gateway, "TARA_TOOLS_ENABLED", True)
    monkeypatch.setattr(tara_gateway.requests, "get", lambda *args, **kwargs: Response())
    out = tara_gateway._get("/analyze/ROKU", {}, "user-1")
    assert out == {"error": "gateway 404", "code": "not_found",
                   "message": "no seasonal setup for 'ROKU'"}
    assert tara_gateway._is_no_detected_setup(out)


# ---------------------------------------------------------------------------
# Class 6: common English words are not tickers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "show me 100 year pattern", "SHOW ME 100 YEAR PATTERN", "show me the 100 year pattern",
    "please show me my 100-year pattern", "show 100 year pattern", "100 year pattern",
    "show us the hundred year pattern",
])
def test_hundred_year_pattern_never_reads_a_common_word_as_a_ticker(message):
    assert tara_gateway._question_symbol(message) is None
    resolved = []
    command = tara_gateway.build_hundred_year_security_command(message, {}, "token")
    assert command is None and resolved == []


@pytest.mark.parametrize("message, symbol", [
    ("How did DJI do during the 100 year pattern?", "DJI"),
    ("show me aapl during the 100 year pattern", "AAPL"),
    ("when is nvda historically weak?", "NVDA"),
    ("how did ALL do during the 100 year pattern", "ALL"),
    ("best time to buy the qqq", "QQQ"),
])
def test_real_tickers_are_still_extracted(message, symbol):
    assert tara_gateway._question_symbol(message) == symbol


@pytest.mark.parametrize("token, text, expected", [
    ("me", "show me 100 year pattern", False),
    ("ME", "SHOW ME 100 YEAR PATTERN", False),
    ("ALL", "show me ALL", True),
    ("all", "show me all", False),
    ("Z", "show my Z probability", True),
    ("roku", "pull up roku", True),
    ("I", "can I see it", False),
])
def test_ticker_plausibility_rule(token, text, expected):
    assert tara_gateway._plausible_ticker_token(token, text) is expected


# ---------------------------------------------------------------------------
# Class 7: UI how-to routing
# ---------------------------------------------------------------------------

SECTIONS = tara_prompt_context.parse_knowledge_sections(
    (ROOT / "appserver/appserver/chatbot_knowledge.txt").read_text(encoding="utf-8"))


@pytest.mark.parametrize("message, heading", [
    ("create a watch list", "Watchlist"),
    ("how do I ad to a watch list", "Watchlist"),
    ("make a watch-list", "Watchlist"),
    ("why did my chart change", "Common Navigation Playbooks"),
    ("my chart changed when I clicked something", "Common Navigation Playbooks"),
    ("how do I cancel my subscription", "Account & Profile"),
    ("where can I download my invoice", "Account & Profile"),
    ("what is median gain?", "Lower Panel Views (below the Gain-Loss Bar Chart)"),
])
def test_how_to_questions_select_the_documenting_kb_section(message, heading):
    assert heading in SECTIONS
    selection = tara_prompt_context.select_topic_knowledge(message, SECTIONS)
    assert heading in selection.headings


@pytest.mark.parametrize("message", [
    "create a watch list", "how do I create a watch list?", "how do I ad to a watch list",
    "make me a watchlist", "how can I add symbols to my watchlist",
])
def test_watchlist_how_to_gives_the_steps_and_opens_the_guide(message):
    reply = planner.build_deterministic_reply(message, {}, {})
    plain = _plain(reply)
    assert plain.startswith("I can't create or edit a watchlist for you")
    for step in ("1) Click the Watchlist icon", "2) Type a name", "3) Type each symbol",
                 "4) Select the watchlist"):
        assert step in plain
    assert 'data-action="open-watchlist-popup"' in reply


def test_watchlist_research_requests_are_not_answered_with_setup_steps():
    for message in ("Scan my Tech watchlist and tell me which tickers are entering a seasonal buy zone",
                    "what is a watchlist limit on Navigator"):
        assert planner.build_watchlist_howto_reply(message) is None


@pytest.mark.parametrize("message", [
    "what is median gain?", "what does median mean here", "explain the median return",
    "define median profit",
])
def test_median_is_defined_over_all_completed_years(message):
    plain = _plain(planner.build_deterministic_reply(message, {}, {}))
    assert "every completed year's return" in plain
    assert "winning and losing years together" in plain
    assert "not limited to the profitable years" in plain


def test_median_definition_cites_the_loaded_patterns_engine_values():
    plain = _plain(planner.build_median_definition_reply(
        "what is median gain?", _loaded(), current_year=2026))
    assert "For the loaded ATO window the median is +4.00% and the average +4.23%." in plain


def test_prompt_no_longer_denies_the_lower_viewer_action():
    source = (ROOT / "appserver/appserver/chatbot.py").read_text(encoding="utf-8")
    assert "documented UI gaps - slide/tab switch" not in source
    assert "Switching the lower viewer is NOT a gap" in source
    assert "opening the guide alone is not an answer" in source


def test_calendar_boundary_points_to_the_remind_me_button():
    reply = tara_prompt_context.research_capability_reply(
        "Add the top AAPL seasonal setup for next week to my calendar with entry and exit reminders.")
    assert "click Remind me in the Gain-Loss Bar Chart toolbar" in reply
    assert "notification icon" not in reply


# ---------------------------------------------------------------------------
# Class 8: deterministic screen boilerplate and win counts
# ---------------------------------------------------------------------------

def test_investor_screen_has_win_counts_and_one_short_closing_line(monkeypatch):
    rows = [
        {"date": "2026-11-17", "symbol": "GWW", "days_out": 8, "direction": "L",
         "avg_profit": 1.9, "sharpe_ratio": 1.98},
        {"date": "2026-11-17", "symbol": "ZBRA", "days_out": 12, "direction": "L",
         "avg_profit": 5.8, "sharpe_ratio": 1.75},
    ]
    chart_calls = []

    def chart(market, symbol, entry_date, days_out, years_value, token, *, direction="long"):
        chart_calls.append((market, symbol, entry_date, days_out, years_value, direction))
        return 200, {"stats": {"Num Winners": "10" if symbol == "GWW" else "9",
                               "Num Losers": "0" if symbol == "GWW" else "1"}}

    monkeypatch.setattr(tara_gateway, "_chart_data4", chart)
    monkeypatch.setattr(tara_gateway, "send_claude_messages",
                        lambda *a, **k: pytest.fail("deterministic screen reached the model"))
    text, actions = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": "Show me bullish stock patterns this time of year"}],
        "system", "user-1", "model", opp_table=rows, opp_table_market="2",
        user_token="token", opp_table_years=10,
    )
    plain = _plain(text)
    assert "GWW — window near Nov 17; 8-day study; profitable in 10 of 10 years" in plain
    assert "ZBRA — window near Nov 17; 12-day study; profitable in 9 of 10 years" in plain
    assert ("2", "GWW", "2026-11-17", 8, "10", "long") in chart_calls
    closing = plain.split("Sharpe 1.75.")[-1]
    assert len(closing.split()) <= 15
    for old in ("does not check company fundamentals", "The research advantage is",
                "This screening feed has average return and Sharpe"):
        assert old not in plain


def test_screen_still_answers_when_the_win_record_cannot_be_read(monkeypatch):
    rows = [{"date": "2026-11-17", "symbol": "GWW", "days_out": 8, "direction": "L",
             "avg_profit": 1.9, "sharpe_ratio": 1.98}]
    monkeypatch.setattr(tara_gateway, "_chart_data4", lambda *a, **k: (None, None))
    text, _ = tara_gateway.run_chat_with_tools(
        [{"role": "user", "content": "Show me bullish stock patterns this time of year"}],
        "system", "user-1", "model", opp_table=rows, opp_table_market="2", user_token="token",
    )
    assert "GWW" in text and "profitable in" not in text


# ---------------------------------------------------------------------------
# Class 9: "N of Y winning years" below the detection band
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("asked, years, market, floor", [
    (5, 7, "4", 6),
    (6, 10, "4", 9),
    (4, 7, "2", 6),
])
def test_out_of_band_threshold_runs_the_nearest_supported_screen(monkeypatch, asked, years,
                                                                market, floor):
    import tara_research
    assert tara_research._band_floor(market, years) == floor
    seen = []

    def run_tool(name, tool_input, user_id):
        seen.append(dict(tool_input))
        if tool_input["min_winning_years"] < floor:
            return {"opportunities": [], "lookback_note": "min_winning_years=%d is outside the "
                    "detection band" % asked}
        return {"opportunities": [_scan_card("TOL")]}

    monkeypatch.setattr(tara_gateway, "run_tool", run_tool)
    notes, actions = [], []
    out = tara_gateway._execute_tara_tool(
        "find_best_opportunities",
        {"markets": market, "years": years, "min_winning_years": asked, "pe_cycle": "pe"},
        "user-1", actions, {}, [], latest_user_text="min %d of %d years" % (asked, years),
        turn_notes=notes, user_token="token",
    )
    assert [call["min_winning_years"] for call in seen] == [asked, floor]
    assert out["opportunities"][0]["symbol"] == "TOL"
    assert out["threshold_adjusted"]["used_min_winning_years"] == floor
    assert "lookback_note" not in out
    note = notes[0]["text"]
    assert "won at least %d of the last %d years" % (floor, years) in note
    assert "%d-of-%d screen does not exist" % (asked, years) in note
    assert "detection band" not in note and "min_winning_years" not in note


def test_threshold_notice_is_added_when_the_model_does_not_mention_it(monkeypatch):
    def run_tool(name, tool_input, user_id):
        if tool_input["min_winning_years"] < 6:
            return {"opportunities": []}
        return {"opportunities": [_scan_card("TOL")]}

    text, _, _ = _run(
        monkeypatch,
        [
            _tool_response("scan-1", "find_best_opportunities",
                           {"markets": "4", "years": 7, "min_winning_years": 5}),
            _text_response("TOL - won 7/7 years, avg +5.6%."),
        ],
        "Find me the 5 best opportunities in Wilshire 5000, min 5 out of 7 years",
        run_tool=run_tool,
    )
    plain = _plain(text)
    assert plain.startswith("TradeWave's detector only lists Wilshire 5000 patterns that won at "
                            "least 6 of the last 7 years")
    assert "nearest supported threshold" in plain and "TOL" in plain


def test_in_band_empty_result_is_left_alone(monkeypatch):
    seen = []
    monkeypatch.setattr(tara_gateway, "run_tool",
                        lambda name, tool_input, user_id: seen.append(1) or {"opportunities": []})
    out = tara_gateway._execute_tara_tool(
        "find_best_opportunities", {"markets": "4", "years": 7, "min_winning_years": 7},
        "user-1", [], {}, [], turn_notes=[], user_token="token",
    )
    assert len(seen) == 1 and "threshold_adjusted" not in out


# ---------------------------------------------------------------------------
# Class 10: next checks Tara can run; consistent earnings statements
# ---------------------------------------------------------------------------

def _next_check_cases():
    weak_recent = [5, 6, 4, 7, 5, -2, -3, 1, -1, -2]
    return [
        ("recent weaker", _loaded(returns=weak_recent), {}),
        ("earnings in window", _loaded(stats={"next_earnings_est": "2026-11-24"}), {}),
        ("small sample", _loaded(returns=[3.0, 2.0, 4.0, 1.0, 2.5]), {}),
        ("scanner", dict(_loaded(), selection_origin="scanner"), {}),
        ("scanner short", dict(_loaded(direction="short", returns=[-4, -2, -6, -1, -3, -5, -2, -8, -3, -4]),
                               selection_origin="scanner"), {}),
        ("worst path", _loaded(), {}),
        ("outlier", _loaded(returns=[-1, -1, -1, -1, -1, -1, -1, -1, -1, 30]), {}),
        ("curves disagree", _loaded(), {"selected_window_path": "supports",
                                         "full_history_window_path": "against"}),
    ]


@pytest.mark.parametrize("label, wave, screen", _next_check_cases(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_suggested_next_check_is_something_tara_can_run(label, wave, screen):
    facts = planner.canonical_pattern_facts(wave, current_year=2026)
    check = planner._runnable_next_check(facts, screen)
    assert check, label
    ask = re.search(r'ask "([^"]+)"', check)
    assert ask, check
    question = ask.group(1)
    symbol = wave["symbol"]
    handled = (
        planner.is_specific_year_question(question, wave)
        or planner.build_bottom_slide_command(question) is not None
        or bool(planner._FULL_HISTORY_COMMAND_PATTERN.search(question))
        or (bool(tara_gateway._BEST_TIME_BUY_RE.search(question)
                 or tara_gateway._HISTORICAL_WEAK_SYMBOL_RE.search(question))
            and tara_gateway._question_symbol(question, wave) == symbol)
    )
    assert handled, question
    for dead_end in ("with and without earnings", "nearby start dates", "projection"):
        assert dead_end not in check


def test_analysis_never_suggests_an_earnings_cohort_split():
    wave = _loaded(stats={"next_earnings_est": "2026-11-24"})
    for message in ("analyze this pattern", "what is the downside risk of this pattern?", "Should I trade this pattern?"):
        reply = planner.build_deterministic_reply(message, wave, {}, current_year=2026)
        assert reply
        assert "with and without earnings" not in reply
        assert "with and without an earnings" not in reply


@pytest.mark.parametrize("message", [
    "ok do with and without earnings", "compare the years with earnings vs without",
    "exclude earnings years", "what is the earnings effect on this window?",
])
def test_earnings_split_request_is_answered_consistently(message):
    wave = _loaded(stats={"next_earnings_est": "2026-11-24"})
    plain = _plain(planner.build_deterministic_reply(message, wave, {}, current_year=2026))
    assert plain.startswith("TradeWave cannot split ATO's history into with-earnings and "
                            "without-earnings years.")
    assert "The estimated next earnings date, Nov 24, 2026, falls inside this window." in plain
    assert "Price Chart marks each past earnings date (E)" in plain
    assert "does not provide earnings" not in plain
    assert 'Ask "open the price chart"' in plain
    assert planner.build_bottom_slide_command("open the price chart") is not None


# ---------------------------------------------------------------------------
# Class 11: weak-period ask after the 100-Year Pattern
# ---------------------------------------------------------------------------

def _best_waves(by_setting, seen):
    def rows(market, symbol, years, pe_cycle, token):
        seen.append((years, pe_cycle))
        status, found = by_setting.get((years, pe_cycle), ("feature_not_available", []))
        return 200, status, found, years
    return rows


SPX_VIEW = {"symbol": "SPX", "market": "5", "years": "24", "pe_cycle": "pe2",
            "start_date": "2026-09-27", "days_out": "295"}
SPX_OK = {"status": "ok", "symbol": "SPX", "market": "5", "label": "INDICES", "name": "S&P 500"}
SHORT_ROW = ["2026-02-15", "SPX", 6, "Short", 1.77, 2.32, 1.9]


@pytest.mark.parametrize("by_setting, used_years, small_sample", [
    ({(10, "cons"): ("ok", [SHORT_ROW])}, 10, False),
    ({(10, "cons"): ("ok", []), (5, "cons"): ("ok", [SHORT_ROW])}, 5, True),
])
def test_weak_question_falls_back_from_the_loaded_view_lookback(monkeypatch, by_setting,
                                                                used_years, small_sample):
    seen = []
    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol", lambda *a, **k: dict(SPX_OK))
    monkeypatch.setattr(tara_gateway, "_best_waves_rows", _best_waves(by_setting, seen))
    monkeypatch.setattr(tara_gateway, "_chart_data4", lambda *a, **k: (200, {"request": {
        "market": "5", "symbol": "SPX", "entry_date": "2026-02-15", "days_out": 7,
        "years": used_years, "pe_cycle": "cons"}}))
    command = tara_gateway.build_best_waves_command(
        "When is SPX historically weak?", SPX_VIEW, "token", today=TODAY)
    assert seen[0] == (24, "pe2") and seen[-1] == (used_years, "cons")
    plain = _plain(command["reply"])
    assert "Strongest qualifying weak window for SPX" in plain
    assert "Feb 15, 2026 through Feb 21, 2026" in plain
    assert "I used %d consecutive years because no qualifying wave is listed at 24 PE+2 samples" % used_years in plain
    assert ("sample is small" in plain) is small_sample
    assert "hidden or empty" not in plain and "empty or hidden" not in plain
    assert command["spec"]["years"] == used_years and command["spec"]["pe_cycle"] == "cons"
    assert command["fallback_used"] is True


def test_weak_question_with_no_wave_anywhere_gives_a_plain_finding(monkeypatch):
    seen = []
    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol", lambda *a, **k: dict(SPX_OK))
    monkeypatch.setattr(tara_gateway, "_best_waves_rows", _best_waves({}, seen))
    command = tara_gateway.build_best_waves_command(
        "When is SPX historically weak?", SPX_VIEW, "token", today=TODAY)
    plain = _plain(command["reply"])
    assert seen == [(24, "pe2"), (10, "cons"), (5, "cons")]
    assert plain.startswith("No qualifying weak (Short) Best Wave for SPX at 24 PE+2 samples or "
                            "10 consecutive years or 5 consecutive years")
    assert "dropdown" not in plain and command["spec"] is None


def test_requested_lookback_is_used_without_a_fallback_label_when_it_has_waves(monkeypatch):
    seen = []
    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol", lambda *a, **k: dict(SPX_OK))
    monkeypatch.setattr(tara_gateway, "_best_waves_rows",
                        _best_waves({(20, "cons"): ("ok", [SHORT_ROW])}, seen))
    monkeypatch.setattr(tara_gateway, "_chart_data4", lambda *a, **k: (None, None))
    command = tara_gateway.build_best_waves_command(
        "When is SPX historically weak?", {"years": "20", "pe_cycle": "cons"}, "token", today=TODAY)
    assert seen == [(20, "cons")]
    assert "I used" not in command["reply"] and command["fallback_used"] is False


# ---------------------------------------------------------------------------
# End to end through /chatbot/chat for the deterministic classes
# ---------------------------------------------------------------------------

@pytest.fixture
def chat_app(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "tara-test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    app.register_blueprint(chatbot.chatbot_bp, url_prefix="/chatbot")
    monkeypatch.setattr(chatbot, "ACTION_AUDIT_LOG", str(tmp_path / "tara-actions.jsonl"))
    monkeypatch.setattr(chatbot, "QUESTION_LOG", str(tmp_path / "tara-questions.jsonl"))
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", True)
    for name in ("run_chat_with_tools", "run_chat_with_openai_tools"):
        if hasattr(chatbot, name):
            monkeypatch.setattr(
                chatbot, name,
                lambda *args, **kwargs: pytest.fail("deterministic class reached the model loop"))
    monkeypatch.setattr(tara_gateway, "_loopback_json", lambda *a, **k: (None, None))
    return app


def _ask(app, message, wave=None):
    token = jwt.encode(
        {"user": "tw-task-0031-test", "user_level": "6", "aud": "tw2-appserver",
         "iss": "tw2-web", "exp": int(time.time()) + 300},
        app.config["SECRET_KEY"], algorithm="HS256")
    response = app.test_client().post("/chatbot/chat", json={
        "token": token, "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": wave or {}, "opportunities": [], "screen_context": {},
    })
    assert response.status_code == 200
    return response.get_json()


@pytest.mark.parametrize("message, wave, expected", [
    ("show me 100 year pattern", None, "The 100-Year Pattern"),
    ("create a watch list", None, "1) Click the Watchlist icon"),
    ("what is median gain?", None, "winning and losing years together"),
    ("ok do with and without earnings", "ATO", "cannot split ATO's history"),
    ("tell me about the chart and the profitability of getting in this trade at $167, "
     "when and where should I get out", "ATO", "The historical window exits on Dec 10, 2026."),
    ("would you take this trade?", "ATO", "Whether to take the trade is your decision"),
])
def test_chat_route_answers_deterministic_classes(chat_app, message, wave, expected):
    body = _ask(chat_app, message, _loaded() if wave else None)
    plain = _plain(body["reply"])
    assert expected in plain
    assert "I could not find ME" not in plain
    assert "can't decide whether you should take the trade" not in plain


def test_chat_route_sends_tech_question_to_the_sector_screen(chat_app, monkeypatch):
    import tara_research
    seen = []
    monkeypatch.setattr(tara_research, "build_screen_command", _fake_screen(seen))
    monkeypatch.setattr(chatbot, "build_research_command", lambda *a, **k: None)
    body = _ask(chat_app, "Which tech stocks tend to rise this time of year?")
    plain = _plain(body["reply"])
    assert plain.startswith("Screened on the NASDAQ 100, a tech-heavy index.")
    assert body["actions"] and body["actions"][0]["spec"] == {"market": "1"}
