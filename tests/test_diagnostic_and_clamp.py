"""MSFT 20-years / PE+2 report, 2026-09-14.

Two defects in one turn pair:
  1. "Why did that change, and which years are actually included?" was classified as a
     VIEW command that must emit a chart action. It is analytical, the model emitted no
     action, and the protocol guard replaced the real answer with
     "I couldn't send the complete chart action".
  2. A KNOB-ONLY update_view carries no symbol, so the available-history clamp was
     skipped and the viewer was told to load 20 years of a cohort with only 9.
"""

import sys
from pathlib import Path

APPSERVER = Path(__file__).resolve().parents[1] / "appserver" / "appserver"
sys.path.insert(0, str(APPSERVER))

import tara_gateway  # noqa: E402


DIAGNOSTIC_TURNS = [
    "I requested 20 years, but the viewer now shows 9 years. Why did that change, "
    "and which years are actually included?",
    "why does it show 9 years?",
    "why did the chart change?",
    "how come the years switched?",
    "why didn't it load?",
    "which years are actually included?",
]

REAL_VIEW_COMMANDS = [
    "load AAPL",
    "change years to 20",
    "switch to PE+2",
    "pull up the first one",
    "show me today's pick",
]


def test_explanatory_questions_are_not_treated_as_view_commands():
    for turn in DIAGNOSTIC_TURNS:
        intent = tara_gateway.classify_view_intent(turn)
        assert intent == "forbid", (turn, intent)
        # "forbid" is satisfied by emitting NO action, so the protocol guard stays quiet.
        assert tara_gateway._actions_satisfy_view_intent([], intent), turn


def test_real_view_commands_still_require_an_action():
    for turn in REAL_VIEW_COMMANDS:
        intent = tara_gateway.classify_view_intent(turn)
        assert intent in {"chart", "view"}, (turn, intent)
        assert not tara_gateway._actions_satisfy_view_intent([], intent), turn


def test_knob_only_update_view_still_clamps_to_available_history(monkeypatch):
    """No symbol in the spec means "apply to whatever is loaded", so the loaded symbol
    must still drive the clamp."""
    monkeypatch.setattr(tara_gateway, "_symbol_max_available_years", lambda *a, **k: 9)

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 20, "pe_cycle": "pe2"},
        "user-42",
        actions,
        cards,
        card_list,
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
        named_symbol_override="MSFT",
        named_symbol_lookback=20,   # the "20 years" the user asked for
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs, "a knob change must still reach the viewer"
    assert specs[0].get("years") == 9, specs


def test_displayed_card_carries_its_historical_record():
    """TW-R14-03: the bundle's top level mirrors the DISPLAY horizon's score fields. Its
    selected_recurrence was the one sibling left behind, so the AI panel's exact-horizon
    card rendered "Historical Record: Not provided" with the record available."""
    from ml_checkpoint_context import assemble_minimum_horizon_bundle

    record = {
        "status": "qualified",
        "mode": "consecutive",
        "years": "10",
        "requested_observations": 10,
        "sample_size": 10,
        "positive_years": 7,
        "required_positive_years": 6,
    }
    bundle = assemble_minimum_horizon_bundle(
        {"symbol": "AAPL", "date": "2026-08-10", "daysOut": 5, "direction": "l"},
        {
            "status": "available",
            "ml_score": 72.0,
            "win_prob": 0.68,
            "pred_return": 2.4,
            "pred_mfe": 4.8,
            "selected_recurrence": record,
        },
    )
    # The record is normalized (extra optional stats are added), so assert the fields the
    # AI panel actually reads rather than exact equality.
    for carrier in (bundle, bundle["horizons"][0]):
        got = carrier.get("selected_recurrence")
        assert got, carrier.keys()
        assert got["sample_size"] == 10
        assert got["positive_years"] == 7
        assert got["required_positive_years"] == 6
        assert got["status"] == "qualified"


def test_a_missing_historical_record_never_breaks_a_usable_score():
    """A legacy score may omit the record; that must not turn a good score into an error."""
    from ml_checkpoint_context import normalize_legacy_score_result

    out = normalize_legacy_score_result({
        "status": "available", "ml_score": 72.0, "win_prob": 0.68,
        "pred_return": 2.4, "pred_mfe": 4.8,
    })
    assert out["status"] == "available"
    assert "selected_recurrence" not in out

    # a malformed record is ignored, not fatal
    out = normalize_legacy_score_result({
        "status": "available", "ml_score": 72.0, "win_prob": 0.68,
        "pred_return": 2.4, "pred_mfe": 4.8,
        "selected_recurrence": {"sample_size": 99, "positive_years": 5,
                                "requested_observations": 10},
    })
    assert out["status"] == "available"


def _forced_viewer(direction, winners, losers):
    return {
        "symbol": "AAPL", "market": "2", "start_date": "2026-09-14",
        "days_out": "10", "years": "10", "direction": direction,
        "stats": {"Trade Dir": direction,
                  "Num Winners": str(winners), "Num Losers": str(losers)},
    }


def test_a_forced_direction_is_never_described_as_what_the_record_favors(monkeypatch):
    """Num Winners/Num Losers are direction-adjusted, and a DERIVED direction always ends
    up with winners >= losers (it picks the favoured side, ties going long). So
    winners < losers proves the direction was FORCED - by a pinned URL, say - and saying
    "TradeWave determined this" would be a false statement about the record."""
    monkeypatch.setattr(
        tara_gateway, "run_tool",
        lambda *a, **k: {"card": {"stats": {"historical_win_rate": 0.6,
                                            "avg_return_pct": 4.1,
                                            "sharpe_ratio": 0.8}}},
    )

    forced = tara_gateway.build_direction_flip_reply(
        _forced_viewer("long", 4, 6), "user-42", "2")
    assert "is pinned to LONG" in forced
    assert "not the side AAPL's record favors" in forced
    assert "TradeWave determined this pattern is LONG" not in forced
    assert "it would have called this one short" in forced

    derived = tara_gateway.build_direction_flip_reply(
        _forced_viewer("long", 10, 0), "user-42", "2")
    assert "TradeWave determined this pattern is LONG" in derived
    assert "pinned to" not in derived


def test_pe_phase_parses_only_real_cohorts():
    for value, expected in (
        ("pe0", 0), ("pe1", 1), ("pe2", 2), ("pe3", 3), ("PE2", 2),
        ("cons", None), ("consecutive", None), ("pe", None),
        ("", None), (None, None), ("pe4", None), ("pe22", None),
    ):
        assert tara_gateway._pe_phase(value) == expected, value


def _metadata_response(first_year, last_year):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"StockMetaData": ["%d-01-01" % first_year, "%d-12-31" % last_year]}

    return Response()


def test_available_years_is_counted_per_cohort_not_per_calendar_year(monkeypatch):
    """A PE cohort holds roughly a QUARTER of the calendar range. Returning the
    consecutive count let a 20-year PE+2 request through; React then stepped the control
    down to 9, the fetch had already gone out as pe2-20, and the transaction's request key
    never matched the response - the viewer sat on "loading" (2026-09-14 MSFT report)."""
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    consecutive = tara_gateway._symbol_max_available_years("2", "MSFT", "tok", "cons")
    assert consecutive == 40

    for cycle in ("pe0", "pe1", "pe2", "pe3"):
        cohort = tara_gateway._symbol_max_available_years("2", "MSFT", "tok", cycle)
        assert cohort == 10, (cycle, cohort)
        assert cohort < consecutive

    # No cohort given behaves exactly as before.
    assert tara_gateway._symbol_max_available_years("2", "MSFT", "tok") == 40


def test_knob_only_pe_switch_clamps_to_the_cohort_count(monkeypatch):
    """The reported turn: "use 20 years and switch to PE+2" on a consecutive MSFT view.
    The action must reach the viewer carrying the cohort's real maximum, so the control it
    sets and the chart request it triggers describe the same lookback."""
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 20, "pe_cycle": "pe2"},
        "user-42",
        actions,
        cards,
        card_list,
        user_token="tok",
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
        named_symbol_override="MSFT",
        named_symbol_lookback=20,
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs, "the knob change must still reach the viewer"
    assert specs[0].get("pe_cycle") == "pe2"
    assert specs[0].get("years") == 10, specs


def test_knob_change_on_the_loaded_symbol_is_clamped_without_a_named_override(monkeypatch):
    """Codex retest 2026-09-14, the turn that still failed.

    "Use 20 years and switch to PE+2 midterm years. Keep MSFT..." names the symbol that is
    ALREADY loaded, so chatbot.py sets named_symbol_override=None by design, and the
    named-symbol clamp never runs. The spec reached the viewer carrying years=20 while the
    viewer's own control stepped down to the cohort maximum, and tara_actions.log recorded
    status=failed reason=view_superseded expected years 20 / observed years 9 with the
    chart blank. The clamp must therefore not depend on a named-symbol override.
    """
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 20, "pe_cycle": "pe2"},
        "user-42",
        actions,
        cards,
        card_list,
        user_token="tok",
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
        # exactly as the live turn arrives: no override, no inherited lookback
        named_symbol_override=None,
        named_symbol_lookback=None,
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs, "the knob change must still reach the viewer"
    assert specs[0].get("pe_cycle") == "pe2"
    assert specs[0].get("years") == 10, specs


def test_a_lookback_within_the_cohort_is_left_alone(monkeypatch):
    """The clamp is a ceiling, never a rewrite: an in-range request must pass through."""
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 6, "pe_cycle": "pe2"},
        "user-42",
        actions, cards, card_list,
        user_token="tok",
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs[0].get("years") == 6, specs


def test_a_consecutive_lookback_is_not_clamped_to_a_cohort_count(monkeypatch):
    """Switching years with NO pe_cycle must use the consecutive span, not a quarter of it."""
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 20},
        "user-42",
        actions, cards, card_list,
        user_token="tok",
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs[0].get("years") == 20, specs


def test_the_clamp_never_blocks_the_action_when_metadata_is_unavailable(monkeypatch):
    """A failed lookup must leave the request untouched, not drop the action."""
    def boom(*a, **k):
        raise tara_gateway.requests.RequestException("metadata down")

    monkeypatch.setattr(tara_gateway.requests, "get", boom)
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")

    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view",
        {"years": 20, "pe_cycle": "pe2"},
        "user-42",
        actions, cards, card_list,
        user_token="tok",
        current_view={"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
                      "days_out": 45, "years": 10, "pe_cycle": "cons"},
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs, "a metadata outage must not swallow the user's action"
    assert specs[0].get("years") == 20, specs


def _clamped_years(inp, view, user_years_cap=None, first=1986, last=2026):
    actions, cards, card_list = [], {}, []
    tara_gateway._execute_tara_tool(
        "update_view", inp, "user-42", actions, cards, card_list,
        user_token="tok", user_years_cap=user_years_cap, current_view=view,
    )
    specs = [a.get("spec", {}) for a in actions if a.get("type") == "set_view"]
    assert specs, "the action must still reach the viewer"
    return specs[0].get("years")


def test_the_plan_years_cap_is_applied_too(monkeypatch):
    """The viewer caps the years control by PLAN (Explorer 10, Navigator 15) and steps a
    larger value down to it, so an uncapped spec desynchronises the pending action exactly
    as the cohort case did. Analyst+ has no cap and must be unaffected."""
    monkeypatch.setattr(
        tara_gateway.requests, "get", lambda *a, **k: _metadata_response(1986, 2026)
    )
    monkeypatch.setattr(tara_gateway.config, "appserver_url", "http://appserver.test")
    view = {"symbol": "MSFT", "market": "2", "entry_date": "2026-09-14",
            "days_out": 45, "years": 10, "pe_cycle": "cons"}

    # Explorer: 40 consecutive years exist, but the plan allows 10.
    assert _clamped_years({"years": 30}, view, user_years_cap=10) == 10
    # Navigator: 15.
    assert _clamped_years({"years": 30}, view, user_years_cap=15) == 15
    # Analyst+ (no cap): limited only by the data.
    assert _clamped_years({"years": 30}, view, user_years_cap=None) == 30
    # Whichever limit is TIGHTER wins: a PE+2 cohort has ~10, below Navigator's 15.
    assert _clamped_years({"years": 30, "pe_cycle": "pe2"}, view, user_years_cap=15) == 10
    # ...and the plan wins when IT is tighter than the cohort.
    assert _clamped_years({"years": 30, "pe_cycle": "pe2"}, view, user_years_cap=4) == 4
    # An in-range request is never rewritten.
    assert _clamped_years({"years": 8}, view, user_years_cap=10) == 8
