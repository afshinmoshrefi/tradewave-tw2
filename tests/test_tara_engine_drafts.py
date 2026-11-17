"""TW-TASK-0035: engine drafts rewritten inside the tool loop, lists rendered in code,
guard dead ends, refusal handling and the live-context additions.

The model is always a fake here. The tests pin the SAFETY properties of the rewrite: the
engine stays the only source of numbers, a plan boundary and the exact disclaimer are
never dropped, an engine action is never changed, and any failure sends the engine reply.
"""

import datetime
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver/appserver"))

import AI_tools_appserver  # noqa: E402
import chatbot  # noqa: E402
import config  # noqa: E402
import tara_answer_planner as planner  # noqa: E402
import tara_gateway as tg  # noqa: E402
import tara_research as research  # noqa: E402

DRAFT = (
    "<b>FICO</b> long, Nov 17 to Dec 5 (19 calendar days): profitable in 12 of 12 completed "
    "years, average +4.27%, Sharpe 1.46. ETFs is not included in your plan; see "
    "tradewave.ai/pricing. " + tg.DISCLAIMER_TEXT
)
SPEC = {"symbol": "FICO", "market": "2", "entry_date": "2026-11-17", "days_out": 19}


def _text(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _tool(name, tool_input, tool_id="t1"):
    return {"stop_reason": "tool_use", "content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}


def _rewrite(monkeypatch, responses, message="is FICO any good in late November?",
             draft=DRAFT, actions=None, tool_result=None, sources=()):
    calls = []

    def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(tg, "send_claude_messages", fake_send)
    monkeypatch.setattr(tg, "run_tool", lambda *a, **k: tool_result or {"error": "none"})
    trace = []
    text, out_actions = tg.run_chat_with_tools(
        [{"role": "user", "content": message}], "system", "user-1", "model",
        current_view={}, protocol_trace=trace, engine_draft=draft,
        draft_actions=actions or [], number_sources=list(sources))
    return text, out_actions, calls, trace


pytestmark = pytest.mark.tara_draft_rewrite


# ---------------------------------------------------------------------------
# Step 1: the verified draft inside the tool loop
# ---------------------------------------------------------------------------

def test_rewrite_is_sent_with_the_same_tools_and_the_draft_in_the_user_turn(monkeypatch):
    text, actions, calls, trace = _rewrite(monkeypatch, [_text(
        "Yes, historically: FICO was profitable in 12 of 12 completed years from Nov 17 "
        "to Dec 5, average +4.27%.")])
    args, kwargs = calls[0]
    assert kwargs["tools"] is tg.TOOLS and kwargs["system"] == "system"      # shared cache prefix
    assert "tool_choice" not in kwargs
    sent = args[0][-1]["content"]
    assert sent.startswith("is FICO any good in late November?")
    assert "[ENGINE DRAFT" in sent and "12 of 12 completed" in sent
    assert text.startswith("Yes, historically")
    assert any(item["event"] == "draft_rewrite" for item in trace)


def test_plan_boundary_and_exact_disclaimer_are_restored_word_for_word(monkeypatch):
    text, _actions, _calls, trace = _rewrite(monkeypatch, [_text(
        "FICO was profitable in 12 of 12 completed years, average +4.27%.")])
    assert "ETFs is not included in your plan; see tradewave.ai/pricing." in text
    assert tg.DISCLAIMER_TEXT in text
    assert [item["restored"] for item in trace if item["event"] == "draft_rewrite"] == [2]


@pytest.mark.parametrize("message,reply,reason", [
    ("how does FICO do in late November?",
     "FICO won 11 of 12 years, average +4.27%.", "number_guard"),          # a changed figure
    ("how does FICO do in late November?",
     "FICO averaged +4.27%, roughly 51% a year annualized.", "number_guard"),   # arithmetic
    ("how does FICO do in late November?",
     "The draft says FICO won 12 of 12 years.", "mentions_draft"),
    ("is FICO a good trade in late November?",
     "You should buy FICO now; it won 12 of 12 years.", "no_answer"),   # the loop failed closed
    ("how does FICO do in late November?", "", "provider_error"),
])
def test_a_rewrite_that_fails_a_guard_sends_the_engine_draft(monkeypatch, message, reply, reason):
    # The same reply on every round: an in-loop correction must not rescue it.
    text, actions, _calls, trace = _rewrite(
        monkeypatch, [_text(reply) for _ in range(tg._MAX_TOOL_ROUNDS + 1)], message=message)
    assert text == DRAFT and actions == []
    assert [item["reason"] for item in trace
            if item["event"] == "draft_rewrite_rejected"] == [reason]


def test_a_fail_closed_loop_result_never_replaces_the_engine_draft(monkeypatch):
    text, actions, _calls, trace = _rewrite(
        monkeypatch, [_text("You should buy FICO.") for _ in range(tg._MAX_TOOL_ROUNDS + 1)],
        message="should I buy FICO?")
    assert text == DRAFT and actions == []
    assert trace[-1]["event"] == "draft_rewrite_rejected"


def test_provider_failure_or_refusal_sends_the_engine_draft(monkeypatch):
    for failure in (RuntimeError("boom"), {"stop_reason": "refusal", "content": []}):
        text, actions, _calls, trace = _rewrite(monkeypatch, [failure], actions=[
            {"type": "set_view", "spec": dict(SPEC)}])
        assert text == DRAFT and actions == [{"type": "set_view", "spec": SPEC}]
        assert trace[-1] == {"event": "draft_rewrite_rejected", "reason": "provider_error"}


def test_missing_credential_is_never_masked_by_the_draft(monkeypatch):
    with pytest.raises(AI_tools_appserver.AnthropicConfigurationError):
        _rewrite(monkeypatch, [AI_tools_appserver.AnthropicConfigurationError("no key")])


def test_engine_action_is_kept_and_its_load_is_not_re_announced(monkeypatch):
    seed = [{"type": "set_view", "spec": dict(SPEC)}]
    text, actions, _calls, _trace = _rewrite(monkeypatch, [_text(
        "FICO was profitable in 12 of 12 completed years, average +4.27%, Sharpe 1.46.")],
        actions=seed)
    assert actions == seed
    assert "chart request" not in text and text.startswith("FICO was profitable")


def test_a_conflicting_model_action_sends_the_draft_and_the_engine_action(monkeypatch):
    seed = [{"type": "set_view", "spec": dict(SPEC)}]
    other = {"symbol": "TSLA", "market": "2", "entry_date": "2026-07-24", "days_out": 21}
    card = {"card": {"symbol": "TSLA", "market": {"id": "2"}, "direction": "long",
                     "headline": "TSLA long - Won 8/10 years, avg +4.2%",
                     "setup": {"entry_date": "2026-07-24", "hold_days": 21}}}
    text, actions, _calls, trace = _rewrite(monkeypatch, [
        _tool("analyze_symbol", {"symbol": "TSLA"}),
        _tool("update_view", other, "t2"),
        _text("TSLA won 8 of 10 years, average +4.2%."),
    ], actions=seed, tool_result=card)
    assert text == DRAFT and actions == seed
    assert trace[-1]["reason"] == "engine_action_changed"


def test_numbers_from_a_tool_result_and_the_live_context_are_allowed(monkeypatch):
    card = {"card": {"symbol": "IRM", "market": {"id": "2"}, "direction": "short",
                     "headline": "IRM short - Won 9/10 years, avg +3.2%",
                     "stats": {"historical_win_rate": 0.9, "sharpe_ratio": 0.78},
                     "setup": {"entry_date": "2026-12-11", "hold_days": 27}}}
    text, _actions, _calls, trace = _rewrite(monkeypatch, [
        _tool("analyze_symbol", {"symbol": "IRM"}),
        _text("I can't verify live volume. IRM's nearest seasonal window fell in 9 of 10 "
              "years (90%), average +3.2%, Sharpe 0.78; Trend Long is 87."),
    ], draft="I can't verify intraday volume from TradeWave's seasonal data.",
        message="today's volume on IRM?", tool_result=card, sources=["Trend Long: 87"])
    assert "9 of 10 years (90%)" in text
    assert trace[-1]["event"] == "draft_rewrite"


def test_compliance_only_and_row_load_replies_are_never_rewritten():
    assert not tg.draft_is_rewritable(
        "ETFs is not included in your plan. See tradewave.ai/pricing.")
    assert not tg.draft_is_rewritable(
        "<b>AI Scores are not available in this view.</b> They appear for eligible "
        "accounts on supported US stocks and ETFs.")
    assert not tg.draft_is_rewritable("Loading row 3.", [{"type": "load_opportunity"}])
    assert tg.draft_is_rewritable(DRAFT, [{"type": "set_view", "spec": SPEC}])


def test_number_guard_normalizes_spelling_but_not_values():
    sources = ["won 9/10, avg 4.30% over 1,234 days; rate 0.917"]
    assert tg.unsupported_numbers("9 of 10, +4.3%, 1234 days, 92% (91.7%)", sources) == []
    assert tg.unsupported_numbers("8 of 10 and 4.31%", sources) == ["4.31", "8"]
    assert tg.unsupported_numbers("top 3 rows, 2 lines", []) == []          # small ordinals


# ---------------------------------------------------------------------------
# Step 3: lists rendered in code
# ---------------------------------------------------------------------------

LIST_DRAFT = (
    '<div class="tara-analysis"><div><b>S&amp;P 500 bullish windows</b> Top 3 by Sharpe.</div>'
    '<div>1. <b>HLT</b> - starts Nov 18: profitable in 10 of 10 years, avg +13.1%<br>'
    '2. <b>CIEN</b> - starts Nov 17: profitable in 10 of 10 years, avg +16.7%<br>'
    '3. <b>YUM</b> - starts Nov 18: profitable in 9 of 10 years, avg +3.7%</div>'
    '<div>Scope: 418 patterns listed.</div></div>')


def test_draft_list_reaches_the_model_as_a_token_and_comes_back_verbatim(monkeypatch):
    text, _actions, calls, _trace = _rewrite(monkeypatch, [_text(
        "Two of these start on Nov 18.<br>[[TW_LIST_0]]<br>418 patterns were listed.")],
        draft=LIST_DRAFT, message="best S&P 500 setups now")
    sent = calls[0][0][0][-1]["content"]
    assert "[[TW_LIST_0]]" in sent and "The list has 3 rows" in sent
    rows = tg._draft_row_block(LIST_DRAFT)[1]
    assert len(rows) == 3 and "<br>".join(rows) in text


def test_a_row_selection_keeps_engine_rows_and_order(monkeypatch):
    text, _actions, _calls, _trace = _rewrite(monkeypatch, [_text(
        "The ones starting Nov 18:<br>[[TW_LIST_0 rows=3,1]]")],
        draft=LIST_DRAFT, message="which of the best S&P 500 setups start on the 18th")
    rows = tg._draft_row_block(LIST_DRAFT)[1]
    assert rows[0] + "<br>" + rows[2] in text and rows[1] not in text


def test_a_retyped_list_is_replaced_by_the_engine_rows_in_engine_order(monkeypatch):
    text, _actions, _calls, trace = _rewrite(monkeypatch, [_text(
        "Top picks:<br>1. <b>CIEN</b> - 10 of 10 years, avg +16.7%<br>"
        "2. <b>HLT</b> - 10 of 10 years, avg +13.1%<br>Research candidates only.")],
        draft=LIST_DRAFT, message="best S&P 500 setups now")
    rows = tg._draft_row_block(LIST_DRAFT)[1]
    assert text.startswith("Top picks:<br>" + rows[0] + "<br>" + rows[1] + "<br>Research")
    assert trace[-1]["event"] == "draft_rewrite"


def test_model_typed_scan_rows_are_replaced_by_the_rendered_rows():
    lists = [["1. <b>HLT</b> long - Nov 18 to Feb 15 (90 days); profitable in 10 of 10 years",
              "2. <b>CIEN</b> long - Nov 17 to Jan 13 (58 days); profitable in 10 of 10 years",
              "3. <b>YUM</b> long - Nov 18 to Dec 13 (26 days); profitable in 9 of 10 years"]]
    text = tg._enforce_rendered_rows(
        "Top 2:<br>\u2022 YUM long, hold 26d: won 9/10<br>\u2022 HLT long, hold 90d: won 10/10<br>"
        "Want one loaded?", lists)
    assert text == "Top 2:<br>" + lists[0][0] + "<br>" + lists[0][2] + "<br>Want one loaded?"
    prose = "HLT is the strongest of the three by Sharpe."
    assert tg._enforce_rendered_rows(prose, lists) == prose


def test_a_reply_that_drops_the_list_gets_the_engine_rows_back(monkeypatch):
    text, _actions, _calls, trace = _rewrite(monkeypatch, [_text(
        "Here are the strongest S&amp;P 500 windows.<br>Historical research candidates only.")],
        draft=LIST_DRAFT, message="best S&P 500 setups now")
    assert "<br>".join(tg._draft_row_block(LIST_DRAFT)[1]) in text
    assert any(item["event"] == "draft_list_restored" for item in trace)


def test_scan_result_carries_a_rendered_list_and_its_token_expands():
    out = {"cards": [
        {"symbol": "HLT", "direction": "long", "headline": "HLT long - Won 10/10 years, avg +13.1%",
         "stats": {"avg_return_pct": 13.1, "sharpe_ratio": 3.14},
         "setup": {"entry_date": "2026-11-18", "hold_days": 90}},
        {"symbol": "J", "direction": "short", "history": {"wins": 12, "years_tested": 12},
         "stats": {"avg_return_pct": 4.1, "sharpe_ratio": 1.0},
         "setup": {"entry_date": "2026-12-02", "hold_days": 18}},
    ]}
    lists = []
    tg._register_rendered_list(out, lists)
    rendered = out["rendered_list"]
    assert rendered["token"] == "[[TW_LIST_1]]" and rendered["rows_available"] == 2
    assert lists[0][0] == ("1. <b>HLT</b> long - Nov 18 to Feb 15 (90 days); profitable in "
                           "10 of 10 years; avg +13.1%; Sharpe 3.14")
    assert "fell in 12 of 12 years" in lists[0][1] and "Dec 2 to Dec 19 (18 days)" in lists[0][1]
    text = tg._expand_rendered_lists("Two setups:<br>[[TW_LIST_1:1]]<br>[[TW_LIST_7]]end", lists)
    assert lists[0][0] in text and lists[0][1] not in text and "TW_LIST" not in text


# ---------------------------------------------------------------------------
# Step 4: guard dead ends and refusals
# ---------------------------------------------------------------------------

def test_text_only_refusal_or_empty_answer_raises_for_the_fallback_provider(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    monkeypatch.setattr(AI_tools_appserver, "ANTHROPIC_API_KEY", "key")
    for data in ({"stop_reason": "refusal", "content": []},
                 {"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""}]}):
        monkeypatch.setattr(AI_tools_appserver.requests, "post",
                            lambda *a, _data=data, **k: Response(_data))
        with pytest.raises(AI_tools_appserver.AnthropicRefusal):
            AI_tools_appserver.send_claude_messages(
                [{"role": "user", "content": "hi"}], model="claude-haiku-5-5")
    assert issubclass(AI_tools_appserver.AnthropicRefusal, AI_tools_appserver.AnthropicAPIError)


def test_tool_choice_is_sent_only_when_given_and_never_forces_a_tool(monkeypatch):
    seen = []

    class Response:
        status_code = 200

        def json(self):
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(AI_tools_appserver, "ANTHROPIC_API_KEY", "key")
    monkeypatch.setattr(AI_tools_appserver.requests, "post",
                        lambda url, headers=None, json=None, timeout=None: seen.append(json) or Response())
    AI_tools_appserver.send_claude_messages([{"role": "user", "content": "hi"}],
                                            model="claude-haiku-5-5", tools=[{"name": "t"}])
    AI_tools_appserver.send_claude_messages([{"role": "user", "content": "hi"}],
                                            model="claude-haiku-5-5", tools=[{"name": "t"}],
                                            tool_choice={"type": "none"})
    assert "tool_choice" not in seen[0] and seen[1]["tool_choice"] == {"type": "none"}
    assert seen[1]["thinking"] == {"type": "adaptive"} and "temperature" not in seen[1]
    source = (ROOT / "appserver/appserver/tara_gateway.py").read_text(encoding="utf-8")
    assert '"type": "any"' not in source and '"type": "tool"' not in source


def test_a_queued_claim_without_an_action_is_removed():
    text, removed = tg.repair_view_contract(
        "GLD is the nearest AI-eligible symbol. I've queued GLD's same window on the chart.", [], {})
    assert removed == 1 and "queued" not in text and "GLD is the nearest" in text


# ---------------------------------------------------------------------------
# Step 5: live context
# ---------------------------------------------------------------------------

def test_plan_ladder_and_market_count_come_from_config():
    markets = [m for m in config.available_resources if m in tg._VS_MARKETS]
    lines = tg.plan_ladder_lines("2")
    assert "TradeWave has %d markets" % len(markets) in lines[0] and len(markets) == 15
    assert "- Navigator (this user's plan): 3 markets" in lines[2]
    assert "Crypto Currencies" in lines[4] and lines[4].startswith("- Strategist: 15 markets")
    knowledge = (ROOT / "appserver/appserver/chatbot_knowledge.txt").read_text(encoding="utf-8")
    assert "TradeWave has %d securities groups" % len(markets) in knowledge
    assert "all %d markets" % len(markets) in knowledge


def test_current_year_bar_state_is_explicit():
    start, end = datetime.date(2026, 11, 17), datetime.date(2026, 12, 5)
    state = chatbot._current_year_bar_state
    assert "ENTRY DAY" in state(2026, "active", start, end, start, 19)
    assert "do not call it live" in state(2026, "active", start, end, start, 19)
    assert "ACTIVE, day 11 of 19" in state(2026, "active", start, end, datetime.date(2026, 11, 27), 19)
    assert "UPCOMING" in state(2026, "upcoming", start, end, datetime.date(2026, 11, 1), 19)
    assert "COMPLETED" in state(2026, "completed", start, end, datetime.date(2026, 12, 9), 19)


def test_ai_reading_reaches_the_live_context_only_from_the_server_scorer():
    view = {"symbol": "MKC", "market": "2", "start_date": "2026-11-17", "days_out": 25,
            "years": 12, "direction": "long"}
    assert planner.ai_live_context_lines(view) == []                      # nothing attached
    view["ai_analysis"] = {
        "status": "available", "mode": "pattern", "full_pattern_calendar_days": 25,
        "horizons": [{"calendar_days": 25, "status": "available", "win_probability": 0.84,
                      "ai_score": 95, "predicted_return_pct": 4.4}]}
    text = "\n".join(planner.ai_live_context_lines(view))
    assert "25-day horizon (the loaded window): AI Win% 84%, AIS 95, PredR +4.4%" in text
    assert planner.wants_ai_live_context("what does the ai win% say", view, {})
    assert planner.wants_ai_live_context("explain this", view, {"active_bottom_slide": "ai_scores"})
    assert not planner.wants_ai_live_context("what is the average return", view, {})
    assert not planner.wants_ai_live_context("what does the ai win% say", {}, {})
    # The chat route asks the scorer only for an entitled plan (the tool-path gate).
    source = (ROOT / "appserver/appserver/chatbot.py").read_text(encoding="utf-8")
    assert "ai_scores_entitled()\n            and normalize_screen_context" in source
    assert 'wave_viewer.pop("ai_analysis", None)' in source               # never from the browser


def test_engine_average_wins_over_the_mean_of_rounded_rows():
    rows = [2.62, 2.69, 2.55, 1.18, 0.93, 0.94, 2.46, 2.44, 1.73, 1.26, 3.72, 0.7]
    view = {"symbol": "GWW", "market": "2", "start_date": "2026-11-17", "days_out": 8,
            "years": 12, "direction": "long",
            "stats": {"Avg Profit - All": "1.94%", "Num Winners": "12", "Num Losers": "0"},
            "yearly_results": [{"year": 2014 + i, "underlying_return_pct": value}
                               for i, value in enumerate(rows)]}
    facts = planner.canonical_pattern_facts(view, current_year=2026)
    assert facts["avg_trade_return_pct"] == 1.94


def test_daily_pick_live_track_record_is_passed_through_in_summary_form():
    out = tg._briefify({"card": {"symbol": "FICO", "headline": "h"}, "as_of": "2026-11-17",
                        "track_record": {"count": 40, "judged_count": 31, "win_count": 22,
                                         "win_rate": 0.71, "avg_return_pct": 1.8,
                                         "rows": [{"secret": 1}]}})
    assert out["live_track_record"] == {"count": 40, "judged_count": 31, "win_count": 22,
                                        "win_rate": 0.71, "avg_return_pct": 1.8}
    assert "track_record" not in out and "as_of" not in out
    assert "live_track_record" not in tg._briefify({"card": {}, "track_record": {"count": 0}})


# ---------------------------------------------------------------------------
# Step 6: injected lines, market switch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reply,language,note", [
    ("TSLA has a solid seasonal record.", "en", "I haven't changed the chart."),
    ("Ho caricato il future sull'oro sul grafico dei prezzi, non una previsione per il periodo.",
     "it", "Non ho modificato il grafico."),
    ("TSLA long, entrada 17 nov. Estos son datos históricos de estacionalidad.", "es",
     "No he cambiado el gráfico."),
    ("این الگو در دوازده سال سود داده است", None, ""),
])
def test_injected_no_change_note_follows_the_reply_language(reply, language, note):
    assert tg.reply_language(reply) == language
    assert tg._no_change_note(reply) == note


def test_announce_line_has_a_form_without_english_words():
    card = {"symbol": "GC", "direction": "long", "headline": "GC long - Won 10/10 years, avg +5.2%",
            "stats": {"sharpe_ratio": 1.9}, "setup": {"entry_date": "2026-12-13", "hold_days": 51}}
    line = tg._announce_line("GC", card, neutral=True)
    assert line == "<b>GC</b> long · Dec 13 to Feb 1 (51 days) · 10/10 · +5.2% · Sharpe 1.90."


def test_market_switch_is_queued_only_when_the_user_asks_for_the_table():
    actions = []
    tg._append_market_switch(actions, "1", "which tech stocks rise this time of year")
    assert actions == []
    tg._append_market_switch(actions, "1", "show the nasdaq 100 in the table")
    assert actions == [{"type": "set_view", "spec": {"market": "1"}}]


def test_no_retraction_and_language_rules_are_in_the_cached_prefix():
    blocks = chatbot.build_system_prompt({}, [])
    stable = blocks[0]["text"]
    assert blocks[0].get("cache_control") and "EARLIER TURNS STAND" in stable
    assert "reply entirely in the language of the user's latest message" in stable
    assert "[[TW_LIST_1]]" in stable and "never say the table switched" in stable
    # byte-stable: nothing request-specific may sit in the cached block
    assert chatbot.build_system_prompt(
        {"symbol": "AAPL", "start_date": "2026-11-17", "days_out": 45}, [{"symbol": "X"}],
        user_message="another question")[0]["text"] == stable
    assert len(stable) < 330000         # ~4 chars per token keeps the prefix far below 100K tokens


# ---------------------------------------------------------------------------
# Step 2: route templates
# ---------------------------------------------------------------------------

def test_january_first_keeps_the_end_date_and_says_so():
    start, days, note = research._january_first(datetime.date(2026, 1, 1), 90)
    assert (start, days) == (datetime.date(2026, 1, 2), 89) and "no January 1 entry" in note
    assert research._january_first(datetime.date(2026, 2, 1), 28) == (datetime.date(2026, 2, 1), 28, "")
    knowledge = (ROOT / "appserver/appserver/chatbot_knowledge.txt").read_text(encoding="utf-8")
    assert "a January 1 start is always studied from January 2" in knowledge
    engine = (ROOT / "appserver/appserver/appserver.py").read_text(encoding="utf-8")
    assert "if date.endswith('-01-01') and not exact_window:" in engine      # the engine rule itself


def test_ambiguous_bare_coin_code_resolves_to_the_listed_crypto_pair(monkeypatch):
    listings = {
        "BTC": [{"resourceID": "7", "label": "FUTURES & COMMODITIES", "name": "Bitcoin Futures CME"},
                {"resourceID": "12", "label": "LONDON EXCHANGE", "name": "Vinanz Limited"}],
        "BTC-USD": [{"resourceID": "16", "label": "CRYPTO CURRENCIES", "name": "Bitcoin"}],
        "ETH": [{"resourceID": "2", "label": "S&P 500 STOCKS", "name": "Ethan Allen Interiors"}],
        "ETH-USD": [{"resourceID": "16", "label": "CRYPTO CURRENCIES", "name": "Ethereum"}],
    }

    def loopback(path, token, **kwargs):
        symbol = path.rsplit("/", 1)[1]
        return 200, {"matches": listings.get(symbol, []), "symbol": symbol}

    monkeypatch.setattr(tg, "_loopback_json", loopback)
    assert tg._resolve_question_symbol("BTC", "btc seasonality", "t")["symbol"] == "BTC-USD"
    assert tg._resolve_question_symbol("BTC", "btc futures seasonality", "t")["market"] == "7"
    assert tg._resolve_question_symbol("ETH", "how does ETH do in Q1", "t")["market"] == "2"
    assert tg._resolve_question_symbol("ETH", "ethereum crypto in Q1", "t")["symbol"] == "ETH-USD"
    found = research._find_securities("btc vs eth seasonality next 2 months", "t")
    assert [(item["symbol"], item["market"]) for item in found] == [
        ("BTC-USD", "16"), ("ETH-USD", "16")]


def test_sector_screen_uses_a_stock_group_the_plan_includes(monkeypatch):
    asked = []

    def screen(message, token, **kwargs):
        asked.append(message)
        return {"reply": '<div class="tara-analysis">rows</div>', "actions": [], "trace": {}}

    monkeypatch.setattr(research, "build_screen_command", screen)
    monkeypatch.setattr(tg, "_verified_claims", lambda: {"user": "u", "user_level": "1"})
    command = tg.build_sector_screen_command("Which tech stocks tend to rise this time of year?", "t")
    assert asked == ["Which Dow 30 stocks tend to rise this time of year?"]
    assert "Screened on the Dow 30, the stock group your plan includes." in command["reply"]
    assert "tradewave.ai/pricing" in command["reply"]
    monkeypatch.setattr(tg, "_verified_claims", lambda: {"user": "u", "user_level": "6"})
    asked.clear()
    tg.build_sector_screen_command("Which tech stocks tend to rise this time of year?", "t")
    assert asked == ["Which NASDAQ 100 stocks tend to rise this time of year?"]
