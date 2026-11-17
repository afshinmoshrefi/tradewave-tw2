"""TW-TASK-0035: engine replies with a validated model lead, lists rendered in code,
guard dead ends, refusal handling and the live-context additions.

Phase B contract (after the independent review of 8ff5a607): an engine route's reply is
sent WORD FOR WORD and its chart actions are never touched. The model may only add a
short lead above it, and tara_draft_lead.validate_lead refuses any lead that says
something the engine reply does not. Every probe from the review (f1.py to f8.py) is a
regression test here; the recorded replies are in
tests/fixtures/tara_review_probes_20261117.json.
"""

import datetime
import json
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
import tara_draft_lead as lead_rules  # noqa: E402
import tara_gateway as tg  # noqa: E402
import tara_research as research  # noqa: E402

PROBES = json.loads((ROOT / "tests/fixtures/tara_review_probes_20261117.json").read_text())
LIST_DRAFT = PROBES["drafts"]["LIST"]
STUDY_DRAFT = PROBES["drafts"]["STUDY"]
SPEC = {"symbol": "CL", "market": "7", "entry_date": "2026-06-01", "days_out": 92,
        "years": 20, "pe_cycle": "cons"}
DRAFT = (
    "<b>FICO</b> long, Nov 17 to Dec 5 (19 calendar days): profitable in 12 of 12 completed "
    "years, average +4.27%, Sharpe 1.46. ETFs is not included in your plan; see "
    "tradewave.ai/pricing. " + tg.DISCLAIMER_TEXT
)

pytestmark = pytest.mark.tara_draft_rewrite


def _with_lead(monkeypatch, lead, draft=STUDY_DRAFT, actions=None,
               message="what happens to oil in the summer", history=None):
    """Run the lead path with a model that answers ``lead`` (or raises it)."""

    calls = []

    def request(provider, convo, system, model, user_id=None, cache_ttl="5m"):
        calls.append({"provider": provider, "convo": convo, "system": system})
        if isinstance(lead, Exception):
            raise lead
        return lead

    monkeypatch.setattr(tg, "_request_lead", request)
    trace = []
    messages = list(history or []) + [{"role": "user", "content": message}]
    reply = tg.engine_reply_with_lead(
        "anthropic", messages, "system", "model", draft, actions or [], protocol_trace=trace)
    return reply, calls, trace


# ---------------------------------------------------------------------------
# The lead contract
# ---------------------------------------------------------------------------

def test_an_allowed_lead_goes_above_the_engine_reply_which_stays_word_for_word(monkeypatch):
    lead = "CL fell in 11 of 21 completed years (52%) from Jun 1 to Aug 31."
    actions = [{"type": "set_view", "spec": dict(SPEC)}]
    reply, calls, trace = _with_lead(monkeypatch, lead, actions=actions)
    assert reply == lead + "<br><br>" + STUDY_DRAFT
    assert trace == [{"event": "draft_lead", "outcome": "added"}]
    sent = calls[0]["convo"][-1]["content"]
    assert sent.startswith("what happens to oil in the summer")
    assert "[ENGINE REPLY" in sent and "CL fell in 11 of 21 completed consecutive years" in sent
    assert calls[0]["system"] == "system"                    # the cached prefix is untouched
    assert actions == [{"type": "set_view", "spec": SPEC}]   # engine actions never change


def test_the_lead_request_shares_the_chat_prefix_and_cannot_call_tools(monkeypatch):
    seen = []

    def send(convo, **kwargs):
        seen.append(kwargs)
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "NONE"}]}

    monkeypatch.setattr(tg, "send_claude_messages", send)
    reply = tg.engine_reply_with_lead(
        "anthropic", [{"role": "user", "content": "oil in summer?"}], "system", "model",
        STUDY_DRAFT, [])
    assert reply == STUDY_DRAFT
    assert seen[0]["tools"] is tg.TOOLS and seen[0]["tool_choice"] == {"type": "none"}
    assert seen[0]["system"] == "system" and seen[0]["cache_system"] is True


@pytest.mark.parametrize("case", PROBES["lead_cases"], ids=lambda case: case["name"])
def test_review_probe_f1_leads(case, monkeypatch):
    """f1.py: 22 hand-written rewrites; only the two faithful ones may be added."""

    draft = PROBES["drafts"][case["draft"]]
    allowed, reason = lead_rules.validate_lead(case["lead"], draft)
    assert allowed is case["allowed"], reason
    reply, _calls, _trace = _with_lead(monkeypatch, case["lead"], draft=draft)
    if case["allowed"]:
        assert reply == case["lead"] + "<br><br>" + draft
    else:
        assert reply == draft


@pytest.mark.parametrize("lead,reason", [
    # a figure moved to another symbol, a flipped sign, a flipped direction, a changed n
    ("MMM fell in 9 of 10 years.", "unsupported:MMM"),
    ("CRM's average move was +2.9%.", "unsupported:CRM"),
    ("IBM rose in 7 of 10 years.", "unsupported:IBM"),
    ("MMM fell in 8 of 20 years.", "unsupported:MMM"),
    # a date and a window length that belong to another row
    ("MMM starts Fri Nov 20.", "unsupported:MMM"),
    ("CRM has a 24-day window.", "unsupported:CRM"),
    # a count, a totality claim, a superlative and a sector the engine never stated
    ("Two Dow 30 names start bearish windows this week.", "count"),
    ("This is the full Dow 30 screen.", "unsupported:-"),
    ("IBM is the strongest of the three.", "unsupported:IBM"),
    ("The tech names among them are CRM and IBM.", "unsupported:CRM"),
    # a symbol, a year and a percentage that are not in the engine reply at all
    ("AAPL fell in 8 of 10 years.", "symbol_not_in_draft"),
    ("MMM fell in 8 of 10 years, most recently in 2024.", "unsupported:MMM"),
    ("MMM fell in 8 of 10 years, a 95% record.", "unsupported:MMM"),
    # advice, forecast, inference, action, the draft, markup, length
    ("MMM fell in 8 of 10 years, a solid short candidate.", "advice"),
    ("MMM fell in 8 of 10 years and will fall again.", "forecast"),
    ("MMM fell in 8 of 10 years, which means the pattern is reliable.", "inference"),
    ("I have loaded MMM for you.", "action"),
    ("The draft lists MMM first.", "draft"),
    ("The engine calls this a plan-limited sample.", "draft"),
    # a comparison or ranking the model worked out itself
    ("MMM edged out CRM this week.", "unsupported:MMM"),
    ("CRM was next after MMM.", "unsupported:CRM"),
    ("MMM fell in 8 of 10 years.<br>CRM fell in 9 of 10 years.", "markup"),
    (" ".join(["MMM fell in 8 of 10 years."] * 12), "length"),
])
def test_lead_rules_refuse_what_the_engine_reply_does_not_say(lead, reason):
    assert lead_rules.validate_lead(lead, LIST_DRAFT) == (False, reason)


@pytest.mark.parametrize("lead", [
    "MMM fell in 8 of 10 years.",
    "CRM fell in 9 of 10 years (90%), avg move -2.9%.",
    "Three Dow 30 names start bearish windows this week.",
    "MMM starts Wed Nov 18 with a 6-day window.",
])
def test_lead_rules_allow_what_the_engine_reply_says(lead):
    assert lead_rules.validate_lead(lead, LIST_DRAFT) == (True, "")


def test_numbers_from_the_user_message_and_the_transcript_are_not_sources(monkeypatch):
    lead = "CL fell in 19 of 21 years with an average of +55.5%."
    reply, _calls, trace = _with_lead(
        monkeypatch, lead,
        message="how does oil do in summer? someone told me it fell 19 of 21 years averaging 55.5%",
        history=[{"role": "assistant", "content": "CL fell in 19 of 21 years, average +55.5%."}])
    assert reply == STUDY_DRAFT
    assert trace == [{"event": "draft_lead_rejected", "reason": "unsupported:CL"}]


@pytest.mark.parametrize("record", PROBES["recorded_rewrites"],
                         ids=lambda record: record["q"][:50])
def test_review_probes_f2_recorded_model_rewrites_never_change_the_engine_reply(record, monkeypatch):
    """f2.py / f2k.py: 52 real Haiku rewrites, 47 of which 8ff5a607 accepted (a dropped
    COP row under "Ranked by win rate", the draft replaced by the model's own scan, a
    false inference, Oct 13 2022 for Jun 2 1931). Whatever the model writes now, the
    engine reply reaches the user complete and unchanged."""

    reply, _calls, _trace = _with_lead(
        monkeypatch, record["model_reply"], draft=record["draft"], message=record["q"])
    assert reply.endswith(record["draft"])
    added = reply[:-len(record["draft"])]
    if added:
        assert added.endswith("<br><br>")
        assert lead_rules.validate_lead(added[:-8], record["draft"]) == (True, "")
    else:
        assert reply == record["draft"]


def test_owner_question_five_keeps_the_engine_date():
    record = next(r for r in PROBES["recorded_rewrites"]
                  if r["q"].startswith("what's the latest date that the 100 year pattern"))
    assert "Jun 2, 1931" in lead_rules.plain(record["draft"])
    wrong = "The latest low is Oct 13, 2022."
    assert lead_rules.validate_lead(wrong, record["draft"])[0] is False
    right = "The latest the pattern has bottomed is Jun 2, 1931."
    assert lead_rules.validate_lead(right, record["draft"]) == (True, "")


@pytest.mark.parametrize("answer,outcome", [
    ("NONE", {"event": "draft_lead", "outcome": "none"}),
    ("", {"event": "draft_lead", "outcome": "none"}),
    (RuntimeError("boom"), {"event": "draft_lead_rejected", "reason": "provider_error"}),
])
def test_no_lead_and_provider_failure_send_the_engine_reply(monkeypatch, answer, outcome):
    reply, _calls, trace = _with_lead(monkeypatch, answer)
    assert reply == STUDY_DRAFT and trace == [outcome]


def test_a_refusal_sends_the_engine_reply(monkeypatch):
    monkeypatch.setattr(tg, "send_claude_messages",
                        lambda *a, **k: {"stop_reason": "refusal", "content": []})
    assert tg.engine_reply_with_lead(
        "anthropic", [{"role": "user", "content": "oil in summer?"}], "system", "model",
        STUDY_DRAFT, []) == STUDY_DRAFT


def test_missing_credential_is_never_masked(monkeypatch):
    with pytest.raises(AI_tools_appserver.AnthropicConfigurationError):
        _with_lead(monkeypatch, AI_tools_appserver.AnthropicConfigurationError("no key"))


def test_plan_notices_and_the_disclaimer_cannot_be_dropped_or_duplicated(monkeypatch):
    """S4: the locked paragraph used to be appended a second time. The engine reply is now
    the reply, so every plan and limit notice is there exactly once."""

    reply, _calls, _trace = _with_lead(
        monkeypatch, "MMM fell in 8 of 10 years.", draft=LIST_DRAFT,
        message="which dow stocks are bearish this week")
    text = lead_rules.plain(reply)
    assert text.count("Your plan shows only the top 5 patterns per day") == 1
    reply, _calls, _trace = _with_lead(
        monkeypatch, "FICO was profitable in 12 of 12 completed years.", draft=DRAFT,
        message="how does FICO do in late November?")
    assert reply.count("ETFs is not included in your plan") == 1
    assert reply.count(tg.DISCLAIMER_TEXT) == 1 and reply.endswith(tg.DISCLAIMER_TEXT)


def test_compliance_only_and_row_load_replies_never_get_a_lead(monkeypatch):
    monkeypatch.setattr(tg, "_request_lead", lambda *a, **k: pytest.fail("model was called"))
    for draft, actions in (
        ("ETFs is not included in your plan. See tradewave.ai/pricing.", []),
        ("<b>AI Scores are not available in this view.</b> They appear for eligible "
         "accounts on supported US stocks and ETFs.", []),
        ("Loading row 3.", [{"type": "load_opportunity"}]),
    ):
        assert not tg.draft_is_rewritable(draft, actions)
        assert tg.engine_reply_with_lead(
            "anthropic", [{"role": "user", "content": "q"}], "s", "m", draft, actions) == draft
    assert tg.draft_is_rewritable(DRAFT, [{"type": "set_view", "spec": SPEC}])


def test_switch_is_off_by_default_and_off_means_no_model_call(monkeypatch):
    source = (ROOT / "appserver/appserver/tara_gateway.py").read_text(encoding="utf-8")
    assert "\nDRAFT_REWRITE_ENABLED = False\n" in source
    monkeypatch.setattr(tg, "DRAFT_REWRITE_ENABLED", False)
    monkeypatch.setattr(tg, "_request_lead", lambda *a, **k: pytest.fail("model was called"))
    assert tg.engine_reply_with_lead(
        "anthropic", [{"role": "user", "content": "q"}], "s", "m", STUDY_DRAFT, []) == STUDY_DRAFT


def test_the_first_rewrite_design_is_gone():
    source = (ROOT / "appserver/appserver/tara_gateway.py").read_text(encoding="utf-8")
    for name in ("unsupported_numbers", "_accept_draft_rewrite", "_restore_locked_sentences",
                 "engine_draft", "number_sources"):
        assert name not in source


# ---------------------------------------------------------------------------
# Review probes f5 (advice floor), f7 (AI gate by plan), f8 (routes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question", PROBES["advice_questions"])
def test_review_probe_f5_every_advice_question_ends_with_the_exact_disclaimer(question):
    assert planner.is_advice_shaped_question(question)
    reply = tg.disclaimer_last(planner.ensure_required_disclaimer(
        question, "TradeWave can't identify that. It measures a fixed calendar window."))
    assert lead_rules.plain(reply).endswith(tg.DISCLAIMER_TEXT)


def test_review_probe_f7_ai_reading_is_asked_for_only_on_an_entitled_plan(monkeypatch):
    view = {"symbol": "AAPL", "market": "2", "start_date": "2026-11-17", "days_out": 45}
    screen = {"ai_scores_available": True, "active_bottom_slide": "ai_scores"}
    assert planner.wants_ai_live_context("what is the AI win probability?", view, screen)
    for level, entitled in (("1", False), ("2", False), ("4", True), ("6", True)):
        monkeypatch.setattr(
            tg, "_verified_claims", lambda level=level: {"user": "u", "user_level": level})
        assert tg.ai_scores_entitled() is entitled
    source = (ROOT / "appserver/appserver/chatbot.py").read_text(encoding="utf-8")
    assert "ai_scores_entitled()\n            and normalize_screen_context" in source
    assert 'wave_viewer.pop("ai_analysis", None)' in source      # never taken from the browser


@pytest.mark.parametrize("text,expected", [
    ("which russell 1000 stocks have bearish 10 to 20 day holds starting next week?", (10, 20)),
    ("best nasdaq setups with 5-10 day windows", (5, 10)),
    ("top dow stocks, 20-day holds", (20, 20)),
    ("hold for at least 10 days", (10, 367)),
])
def test_review_probe_f8_hold_range_is_a_range(text, expected):
    assert research._hold_filter(text) == expected


# ---------------------------------------------------------------------------
# Polish after phase A went live
# ---------------------------------------------------------------------------

def test_no_change_note_goes_before_the_disclaimer_and_only_after_a_claim():
    answer = ("TradeWave can't identify a best exit price. I've loaded today's pick on the "
              "chart. " + tg.DISCLAIMER_TEXT)
    repaired, dropped = tg.repair_view_contract(answer, [], {})
    assert dropped == 1 and repaired.endswith(tg.DISCLAIMER_TEXT)
    assert repaired.index("I haven't changed the chart.") < repaired.index(tg.DISCLAIMER_TEXT)
    # a removed description of the screen claimed no action: no note at all
    described = ("TradeWave can't identify a best exit price. The chart shows each year's "
                 "MFE and MAE. " + tg.DISCLAIMER_TEXT)
    repaired, dropped = tg.repair_view_contract(described, [], {})
    assert dropped == 1 and "haven't changed" not in repaired
    assert repaired.endswith(tg.DISCLAIMER_TEXT)


def test_a_sentence_that_pointed_at_a_removed_sentence_is_removed_with_it():
    answer = ("TradeWave can't identify a best exit price. It doesn't set targets or exits. "
              "The chart shows each year's MFE and MAE. That's path context, not an exit "
              "instruction. Want me to load today's AI pick?")
    repaired, dropped = tg.repair_view_contract(answer, [], {})
    assert dropped == 2 and "That's path context" not in repaired
    assert repaired.startswith("TradeWave can't identify a best exit price. It doesn't set")
    assert "Want me to load today's AI pick?" in repaired


def test_disclaimer_is_always_the_last_sentence():
    moved = tg.disclaimer_last(
        "Evidence line. " + tg.DISCLAIMER_TEXT + "<br><br>I haven't changed the chart.")
    assert moved == "Evidence line.<br><br>I haven't changed the chart.<br><br>" + tg.DISCLAIMER_TEXT
    ended = "Evidence line.<br><br>" + tg.DISCLAIMER_TEXT
    assert tg.disclaimer_last(ended) == ended
    assert tg.disclaimer_last("No disclaimer here.") == "No disclaimer here."


# ---------------------------------------------------------------------------
# Lists rendered in code (model path)
# ---------------------------------------------------------------------------

def _text(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def test_model_typed_scan_rows_are_replaced_by_the_rendered_rows():
    lists = [["1. <b>HLT</b> long - Nov 18 to Feb 15 (90 days); profitable in 10 of 10 years",
              "2. <b>CIEN</b> long - Nov 17 to Jan 13 (58 days); profitable in 10 of 10 years",
              "3. <b>YUM</b> long - Nov 18 to Dec 13 (26 days); profitable in 9 of 10 years"]]
    text = tg._enforce_rendered_rows(
        "Top 2:<br>• YUM long, hold 26d: won 9/10<br>• HLT long, hold 90d: won 10/10<br>"
        "Want one loaded?", lists)
    assert text == "Top 2:<br>" + lists[0][0] + "<br>" + lists[0][2] + "<br>Want one loaded?"
    prose = "HLT is the strongest of the three by Sharpe."
    assert tg._enforce_rendered_rows(prose, lists) == prose


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
                           "10 of 10 years; avg return +13.1%; Sharpe 3.14")
    assert "fell in 12 of 12 years" in lists[0][1] and "Dec 2 to Dec 19 (18 days)" in lists[0][1]
    assert "avg short-side return +4.1%" in lists[0][1]          # same wording as the research route
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


def test_a_progressive_load_claim_without_an_action_is_removed():
    text, removed = tg.repair_view_contract(
        "Silver won 6 of 10 years, average +1.6%. I'm putting the SI setup on the chart.", [], {})
    assert removed == 1 and "putting" not in text and "Silver won 6 of 10" in text
    queued = [{"type": "set_view", "spec": {"symbol": "SI", "market": "7"}}]
    assert tg._claims_unqueued_view_change("I'm putting the SI setup on the chart.", queued) is False


def test_one_setup_per_turn_is_enforced_at_the_tool():
    actions = [{"type": "set_view", "spec": dict(SPEC)}]
    card = {"symbol": "TSLA", "market": {"id": "2"},
            "setup": {"entry_date": "2026-07-24", "hold_days": 21}}
    out = tg._execute_tara_tool(
        "update_view", {"symbol": "TSLA", "market": "2", "entry_date": "2026-07-24", "days_out": 21},
        "u", actions, {"TSLA": card}, [card], current_view={})
    assert out["ok"] is False and "already queued" in out["error"]
    assert actions == [{"type": "set_view", "spec": SPEC}]


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


# ---------------------------------------------------------------------------
# Review of 8ff5a607 (phase A): rendered values are the engine's values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,direction,wins,years,avg,sharpe,headline_sharpe", [
    ("FICO", "long", 10, 10, 4.4, 1.43, "1.4"),
    ("MAR", "long", 10, 10, 12.2, 1.84, "1.8"),
    ("GOOGL", "long", 9, 10, 9.5, 1.48, "1.5"),
    ("AMCR", "short", 8, 10, 2.1, 0.06, "0.1"),
])
def test_rendered_row_fields_equal_the_engine_values(symbol, direction, wins, years, avg, sharpe,
                                                    headline_sharpe):
    card = {
        "symbol": symbol, "direction": direction,
        "headline": "%s %s - Won %d/%d years, avg %+.1f%%, Sharpe %s." % (
            symbol, direction, wins, years, avg, headline_sharpe),
        "stats": {"avg_return_pct": avg, "sharpe_ratio": sharpe,
                  "historical_win_rate": wins / years, "years": str(years)},
        "setup": {"entry_date": "2026-11-17", "hold_days": 19},
    }
    line = re.sub(r"<[^>]+>", "", tg._scan_row_line(1, card))
    assert line.startswith("1. %s %s - Nov 17 to Dec 5 (19 days); " % (symbol, direction))
    assert "%s in %d of %d years" % ("fell" if direction == "short" else "profitable", wins, years) in line
    assert ("avg short-side return %+.1f%%" if direction == "short" else "avg return %+.1f%%") % avg in line
    # The engine's Sharpe at the engine's precision - never the headline's one-decimal copy.
    assert line.endswith("Sharpe %.2f" % sharpe)
    assert "Sharpe %s0" % headline_sharpe not in line or "%.2f" % sharpe == headline_sharpe + "0"


def test_headline_only_sharpe_is_not_padded_to_two_decimals():
    card = {"symbol": "XYZ", "direction": "long", "headline": "XYZ long - Won 9/10 years, avg +3.0%, Sharpe 1.4.",
            "stats": {"avg_return_pct": 3.0}, "setup": {"entry_date": "2026-11-17", "hold_days": 19}}
    assert tg._scan_row_line(1, card).endswith("Sharpe 1.4")


@pytest.mark.parametrize("question", [
    "what exit price gives the best result",
    "which stop level works best here",
    "what is the best entry price for this",
])
def test_price_level_asks_get_the_exact_disclaimer_with_or_without_a_pattern(question):
    assert planner.is_advice_shaped_question(question)
    reply = planner.ensure_required_disclaimer(
        question, "TradeWave measures a fixed calendar window, so the exit is a date, not a price.")
    assert reply.endswith(planner.DISCLAIMER_TEXT) or tg.DISCLAIMER_TEXT in reply
    assert not planner.is_advice_shaped_question("what does exit price mean")


def test_empty_symbol_read_is_explained_as_what_happened(monkeypatch):
    empty = {"card": {"symbol": "ZZZ", "direction": "long",
                      "headline": "ZZZ long - no high-conviction seasonal edge right now.",
                      "stats": {"avg_return_pct": None, "historical_win_rate": None,
                                "sharpe_ratio": None, "years": "10"},
                      "setup": {"entry_date": "2026-10-01", "hold_days": 92}}}
    coin = {"card": {"symbol": "BTC-USD", "direction": "long",
                     "headline": "BTC-USD long - Won 5/10 years, avg +46.5%",
                     "stats": {"avg_return_pct": 46.5, "sharpe_ratio": 0.5, "years": "10"},
                     "setup": {"entry_date": "2026-10-01", "hold_days": 92}}}
    calls = []

    def run_tool(name, inp, user_id):
        calls.append(dict(inp))
        return coin if inp.get("symbol") == "BTC-USD" else empty

    monkeypatch.setattr(tg, "run_tool", run_tool)
    monkeypatch.setattr(tg, "_metal_spot_alias", lambda inp, token: None)
    monkeypatch.setattr(tg, "_crypto_pair_alias", lambda symbol, token: (
        {"symbol": "BTC-USD", "market": "16", "label": "CRYPTO CURRENCIES", "name": "Bitcoin"}
        if symbol == "BTC" else None))
    notes = []
    out, used = tg._analyze_with_recoveries({"symbol": "BTC", "period": "Q4"}, "u", "t", notes)
    assert used["symbol"] == "BTC-USD" and used["market"] == "16"
    assert out["card"]["symbol"] == "BTC-USD" and "read as BTC-USD" in out["symbol_note"]
    out, _used = tg._analyze_with_recoveries({"symbol": "ZZZ", "period": "Q4"}, "u", "t", [])
    assert "returned no statistics for ZZZ" in out["read_note"]
    assert "do not say it has no completed years" in out["read_note"]
    assert "read_note" in tg._RESULT_NOTICE_KEYS


def test_coin_names_resolve_to_the_listed_pair():
    named = {symbol: market for _pattern, symbol, market in research._NAMED_SECURITIES}
    assert named["BTC-USD"] == "16" and named["ETH-USD"] == "16"
