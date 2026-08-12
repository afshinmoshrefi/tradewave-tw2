import json
import time

import jwt
import pytest
from flask import Flask

import chatbot
import tara_gateway


pytestmark = pytest.mark.unit


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
        "what should I trade?",
        "what's today's pick?",
        "is AAPL a good trade?",
        "should I buy TSLA?",
        "what about AAPL?",
        "analyze AAPL",
        "does AAPL make money?",
        "give me a trade",
        "recommend me a trade",
        "show me the best one",
        "can I see AAPL?",
        "pull AAPL up",
        "display AAPL",
        "take me to AAPL",
    ],
)
def test_single_pick_requests_require_a_chart_action(text):
    assert tara_gateway._latest_user_view_intent(
        [{"role": "user", "content": text}]
    ) == "chart"


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
    row = json.loads(open(chatbot.QUESTION_LOG, encoding="utf-8").readline())
    assert row["turn_id"] == body["turn_id"]
    assert row["protocol_trace"] == [{"event": "blank_message"}]


def test_prompt_does_not_substitute_seasonal_rank_for_live_market_data():
    prompt = chatbot.build_system_prompt({}, [])

    assert "do NOT provide intraday trading volume" in prompt
    assert "cannot verify that live criterion" in prompt
    assert "never the overall market trend" in prompt
    assert "Private companies" in prompt


@pytest.mark.parametrize("message", [
    "what should I trade?",
    "what about AAPL?",
    "does AAPL make money?",
    "recommend me a trade",
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


def test_backend_turn_exception_is_written_to_question_audit(
    audit_app, monkeypatch
):
    monkeypatch.setattr(chatbot, "TARA_TOOLS_ENABLED", True)
    monkeypatch.setattr(
        chatbot,
        "run_chat_with_tools",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
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
