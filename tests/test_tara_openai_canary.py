"""Regression coverage for Tara's GPT-5.6 Luna canary and Responses adapter."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver"
sys.path.insert(0, str(APPSERVER))

import openai_tools_appserver as openai_tools  # noqa: E402
import tara_gateway  # noqa: E402
from tara_model_router import (  # noqa: E402
    ANTHROPIC_PROVIDER,
    OPENAI_PROVIDER,
    canary_bucket,
    select_tara_provider,
)


def test_provider_selection_is_sticky_bounded_and_requires_a_key():
    bucket = canary_bucket("user-42")

    assert canary_bucket("user-42") == bucket
    assert select_tara_provider("user-42", 0, True)[0] == ANTHROPIC_PROVIDER
    assert select_tara_provider("user-42", 100, False)[0] == ANTHROPIC_PROVIDER
    assert select_tara_provider("user-42", bucket, True)[0] == ANTHROPIC_PROVIDER
    assert select_tara_provider("user-42", bucket + 1, True)[0] == OPENAI_PROVIDER


@pytest.mark.parametrize("environment, expected", [("dev", "10"), ("staging", "0"), ("prod", "0")])
def test_canary_defaults_to_ten_percent_on_dev_and_zero_elsewhere(environment, expected):
    env = os.environ.copy()
    env["TW2_ENV"] = environment
    env.pop("TARA_OPENAI_CANARY_PERCENT", None)
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import config; print(config.TARA_OPENAI_CANARY_PERCENT)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert output.strip() == expected


def test_canary_fails_closed_when_environment_is_not_explicit():
    env = os.environ.copy()
    env.pop("TW2_ENV", None)
    env.pop("TARA_OPENAI_CANARY_PERCENT", None)
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import config; print(config.TARA_OPENAI_CANARY_PERCENT)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert output.strip() == "0"


def test_segmented_prompt_maps_only_stable_prefix_to_explicit_cache_breakpoint():
    source = [
        {"type": "text", "text": "stable rules", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "selected topic"},
        {"type": "text", "text": "live screen"},
    ]
    original = copy.deepcopy(source)

    items = openai_tools.build_responses_input(
        [{"role": "user", "content": "What am I looking at?"}],
        system=source,
    )

    assert items[0]["role"] == "developer"
    content = items[0]["content"]
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert "prompt_cache_breakpoint" not in content[1]
    assert "prompt_cache_breakpoint" not in content[2]
    assert "cache_control" not in content[0]
    assert items[-1] == {"role": "user", "content": "What am I looking at?"}
    assert source == original


def test_responses_request_uses_luna_low_reasoning_low_verbosity_and_no_storage(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 0},
                    "output_tokens": 5,
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
            }

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(openai_tools, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_tools.requests, "post", fake_post)
    response = openai_tools.send_openai_response(
        [{"role": "user", "content": "hello"}],
        tools=[
            {
                "name": "update_view",
                "description": "change the view",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        cache_key="tara-luna-v1-00",
    )

    payload = captured["payload"]
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["text"] == {"verbosity": "low"}
    assert payload["store"] is False
    assert payload["prompt_cache_options"] == {"mode": "explicit"}
    assert payload["prompt_cache_key"] == "tara-luna-v1-00"
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["parameters"]["type"] == "object"
    assert payload["tools"][0]["strict"] is False
    assert openai_tools.response_text(response) == "ok"


def test_openai_tool_loop_reuses_the_validated_view_action_path(monkeypatch):
    seen_inputs = []

    def fake_send(input_items, model, tools=None, cache_key=None, **kwargs):
        seen_inputs.append(copy.deepcopy(input_items))
        if len(seen_inputs) == 1:
            return {
                "output": [
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "update_view",
                        "arguments": json.dumps(
                            {
                                "market": "3",
                                "symbol": "peg",
                                "entry_date": "2026-07-31",
                                "days_out": 6,
                                "show_mfe": True,
                                "show_mae": False,
                            }
                        ),
                    }
                ]
            }
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "PEG short loaded; its completed sample is 14 profitable years out of n=17.",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(tara_gateway, "send_openai_response", fake_send)
    reply, actions = tara_gateway.run_chat_with_openai_tools(
        [{"role": "user", "content": "Load PEG"}],
        [{"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}}],
        "user-42",
        "gpt-5.6-luna",
    )

    assert reply.startswith("PEG short loaded")
    assert actions == [
        {
            "type": "set_view",
            "spec": {
                "symbol": "PEG",
                "market": "3",
                "entry_date": "2026-07-31",
                "days_out": 6,
                "show_mfe": True,
                "show_mae": False,
            },
        }
    ]
    function_outputs = [
        item for item in seen_inputs[1] if item.get("type") == "function_call_output"
    ]
    assert len(function_outputs) == 1
    assert json.loads(function_outputs[0]["output"])["ok"] is True


def test_view_spec_accepts_only_real_boolean_excursion_controls():
    cleaned = tara_gateway._validate_view_spec(
        {
            "show_mfe": True,
            "show_mae": False,
            "ignored": True,
        }
    )

    assert cleaned == {"show_mfe": True, "show_mae": False}
    assert tara_gateway._validate_view_spec({"show_mfe": "true", "show_mae": 0}) == {}


def test_full_history_command_overrides_model_sentinel_and_pins_loaded_window(monkeypatch):
    captured = {}

    def fake_run_tool(name, tool_input, user_id):
        captured.update(name=name, tool_input=tool_input, user_id=user_id)
        return {"card": {"symbol": "ROST", "headline": "ROST full-history result"}}

    monkeypatch.setattr(tara_gateway, "run_tool", fake_run_tool)
    request_spec = {
        "years": 40,
        "symbol": "ROST",
        "market": "2",
        "entry_date": "2026-08-03",
        "days_out": 17,
        "direction": "long",
        "pe_cycle": "consecutive",
    }
    actions = []
    cards = {}
    card_list = []

    tara_gateway._execute_tara_tool(
        "analyze_symbol",
        {"symbol": "ROST", "years": 99, "entry_date": "2026-08-04", "days_out": 99},
        "user-42",
        actions,
        cards,
        card_list,
        full_history_request=request_spec,
    )
    tara_gateway._execute_tara_tool(
        "update_view",
        {"symbol": "AAPL", "entry_date": "2026-01-01", "days_out": 99, "years": 99},
        "user-42",
        actions,
        cards,
        card_list,
        full_history_request=request_spec,
    )

    assert captured["tool_input"] == request_spec
    assert actions == [{"type": "set_view", "spec": {"years": 40}}]


def test_full_history_action_is_added_when_provider_omits_update_view():
    actions = []

    tara_gateway._enforce_full_history_action(actions, {"years": 40})

    assert actions == [{"type": "set_view", "spec": {"years": 40}}]


def test_full_history_action_cannot_switch_the_loaded_setup():
    actions = [{
        "type": "set_view",
        "spec": {"symbol": "AAPL", "entry_date": "2026-01-01", "years": 99},
    }]

    tara_gateway._enforce_full_history_action(actions, {"years": 40})

    assert actions == [{"type": "set_view", "spec": {"years": 40}}]


def test_openai_http_failure_is_generic_and_does_not_expose_body(monkeypatch):
    class Response:
        status_code = 429
        text = "provider-private-detail"

    monkeypatch.setattr(openai_tools, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_tools.requests, "post", lambda *args, **kwargs: Response())

    with pytest.raises(openai_tools.OpenAIAPIError, match="HTTP 429"):
        openai_tools.send_openai_response([{"role": "user", "content": "hello"}])


def test_chat_route_retries_haiku_when_luna_fails(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(chatbot_module, "build_deterministic_reply", lambda *args, **kwargs: None)
    monkeypatch.setattr(chatbot_module, "build_system_prompt", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: (OPENAI_PROVIDER, 3),
    )
    monkeypatch.setattr(chatbot_module, "TARA_TOOLS_ENABLED", True)

    def fail_openai(*args, **kwargs):
        raise openai_tools.OpenAIAPIError("simulated provider failure")

    monkeypatch.setattr(chatbot_module, "run_chat_with_openai_tools", fail_openai)
    monkeypatch.setattr(
        chatbot_module,
        "run_chat_with_tools",
        lambda *args, **kwargs: ("Haiku recovered the turn.", []),
    )
    monkeypatch.setattr(
        chatbot_module,
        "log_question",
        lambda user_id, question, response, wave_viewer, provider="unknown": seen.update(
            provider=provider, response=response
        ),
    )

    app = Flask(__name__)
    body = {
        "message": "What can you do?",
        "history": [{"role": "user", "content": "What can you do?"}],
        "wave_viewer": {},
        "screen_context": {},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "fallback-test"
        response = chatbot_module.chat.__wrapped__()

    assert response.get_json() == {"reply": "Haiku recovered the turn.", "actions": []}
    assert seen == {"provider": "anthropic_fallback", "response": "Haiku recovered the turn."}


def test_chat_route_loads_visible_ordinal_row_without_calling_a_provider(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("ordinal table commands must bypass providers"),
    )
    monkeypatch.setattr(
        chatbot_module,
        "log_question",
        lambda user_id, question, response, wave_viewer, provider="unknown": seen.update(
            provider=provider, response=response
        ),
    )

    app = Flask(__name__)
    body = {
        "message": "load the 3rd one on the list",
        "history": [{"role": "user", "content": "load the 3rd one on the list"}],
        "wave_viewer": {"symbol": "PCAR"},
        "screen_context": {"opportunity_rows": 3},
        "opp_table_market": "2",
        "opp_table_pe_cycle": "cons",
        "opportunities": [
            {"date": "2026-08-03", "symbol": "ROST", "days_out": 17, "direction": "Long"},
            {"date": "2026-08-02", "symbol": "PCAR", "days_out": 177, "direction": "Long"},
            {
                "date": "2026-08-06",
                "symbol": "PEG",
                "days_out": 6,
                "direction": "Short",
                "avg_profit": 1.8,
                "sharpe_ratio": 0.82,
            },
        ],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "ordinal-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == [
        {
            "type": "load_opportunity",
            "rank": 3,
            "spec": {
                "symbol": "PEG",
                "market": "2",
                "entry_date": "2026-08-06",
                "days_out": 6,
                "pe_cycle": "cons",
            },
        }
    ]
    assert "Loaded row #3: PEG short" in payload["reply"]
    assert seen["provider"] == "deterministic"


@pytest.mark.parametrize("analysis_message", ["Analyze", "Analyze this", "Analyze this pattern"])
def test_chat_route_replaces_client_ai_values_with_server_analysis_context(
    monkeypatch, analysis_message
):
    from flask import Flask, g
    import chatbot as chatbot_module

    captured = {}

    def deterministic(_message, wave_viewer, _screen, **_kwargs):
        captured["wave"] = wave_viewer
        return "verified analysis"

    monkeypatch.setattr(chatbot_module, "build_deterministic_reply", deterministic)
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("verified pattern analysis must bypass providers"),
    )

    app = Flask(__name__)
    app.extensions["tara_ai_analysis_context"] = lambda wave, token, market: {
        "status": "available",
        "mode": "pattern",
        "full_pattern_calendar_days": 17,
        "horizons": [
            {
                "calendar_days": 17,
                "ai_score": 72,
                "win_probability": 0.64,
                "predicted_return_pct": 2.1,
            }
        ],
    }
    body = {
        "message": analysis_message,
        "history": [{"role": "user", "content": analysis_message}],
        "token": "browser-token",
        "wave_viewer": {
            "symbol": "ROST",
            "start_date": "2026-08-03",
            "days_out": "17",
            "direction": "long",
            "ai_analysis": {"status": "available", "horizons": [{"ai_score": 100}]},
        },
        "screen_context": {},
        "opportunities": [],
        "opp_table_market": "2",
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "ai-context-test"
        response = chatbot_module.chat.__wrapped__()

    assert response.get_json() == {"reply": "verified analysis", "actions": []}
    assert captured["wave"]["ai_analysis"]["horizons"][0]["ai_score"] == 72
