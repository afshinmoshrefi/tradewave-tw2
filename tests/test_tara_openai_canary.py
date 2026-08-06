"""Regression coverage for Tara's GPT-5.6 Luna primary and safe fallback."""

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
from tara_model_router import OPENAI_PROVIDER, select_tara_provider  # noqa: E402
from tara_runtime_policy import FALLBACK_MODEL, PRIMARY_MODEL, public_policy  # noqa: E402


def test_provider_selection_is_release_owned_and_has_no_user_bucket():
    assert select_tara_provider() == OPENAI_PROVIDER
    assert PRIMARY_MODEL == "gpt-5.6-luna"
    assert FALLBACK_MODEL == "claude-haiku-4-5-20251001"
    assert "canary" not in json.dumps(public_policy()).lower()


@pytest.mark.parametrize("environment", ["dev", "staging", "prod"])
def test_legacy_canary_setting_is_absent_in_every_environment(environment):
    env = os.environ.copy()
    env["TW2_ENV"] = environment
    env.pop("TARA_OPENAI_CANARY_PERCENT", None)
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import config; print(hasattr(config, 'TARA_OPENAI_CANARY_PERCENT'))",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert output.strip() == "False"


def test_legacy_canary_setting_is_absent_when_environment_is_not_explicit():
    env = os.environ.copy()
    env.pop("TW2_ENV", None)
    env.pop("TARA_OPENAI_CANARY_PERCENT", None)
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import config; print(hasattr(config, 'TARA_OPENAI_CANARY_PERCENT'))",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert output.strip() == "False"


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


def test_view_spec_keeps_the_inclusive_367_calendar_day_boundary():
    assert tara_gateway._validate_view_spec({"days_out": 367}) == {
        "days_out": 367
    }
    assert tara_gateway._validate_view_spec({"days_out": 368}) == {}
    update_view = next(
        tool for tool in tara_gateway.TOOLS if tool["name"] == "update_view"
    )
    assert update_view["input_schema"]["properties"]["days_out"][
        "description"
    ] == "1-367"


def test_view_spec_accepts_only_real_boolean_tooltip_control():
    assert tara_gateway._validate_view_spec({"show_tooltips": True}) == {
        "show_tooltips": True
    }
    assert tara_gateway._validate_view_spec({"show_tooltips": False}) == {
        "show_tooltips": False
    }
    assert tara_gateway._validate_view_spec({"show_tooltips": "false"}) == {}


def test_view_spec_accepts_only_named_lower_panels():
    assert tara_gateway._validate_view_spec({"bottom_slide": "wave_stats"}) == {
        "bottom_slide": "wave_stats"
    }
    assert tara_gateway._validate_view_spec({"bottom_slide": "ai_scores"}) == {
        "bottom_slide": "ai_scores"
    }
    assert tara_gateway._validate_view_spec({"bottom_slide": "settings"}) == {}
    assert tara_gateway._validate_view_spec({"bottom_slide": 2}) == {}


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


def test_named_symbol_action_uses_current_occurrence_year_and_drops_wrong_symbol():
    actions = [
        {
            "type": "set_view",
            "spec": {"symbol": "TDG", "entry_date": "2025-08-02", "days_out": 30},
        },
        {
            "type": "set_view",
            "spec": {
                "symbol": "ITW",
                "market": "2",
                "entry_date": "2025-08-02",
                "days_out": 208,
                "years": 16,
            },
        },
    ]

    tara_gateway._enforce_named_symbol_action(actions, {}, "ITW", 2026)

    assert actions == [
        {
            "type": "set_view",
            "spec": {
                "symbol": "ITW",
                "market": "2",
                "entry_date": "2026-08-02",
                "days_out": 208,
                "years": 16,
            },
        }
    ]


def test_named_symbol_read_is_forced_to_inherit_current_lookback(monkeypatch):
    captured = {}

    def fake_run_tool(name, tool_input, user_id):
        captured.update(name=name, tool_input=tool_input)
        return {"card": {"symbol": "ITW", "headline": "ITW - Won 15/16 years"}}

    monkeypatch.setattr(tara_gateway, "run_tool", fake_run_tool)
    monkeypatch.setattr(
        tara_gateway, "_symbol_max_available_years", lambda market, symbol, token: 16
    )

    tara_gateway._execute_tara_tool(
        "analyze_symbol",
        {"symbol": "ITW", "market": "2", "years": 10},
        "user-42",
        [],
        {},
        [],
        user_token="viewer-token",
        named_symbol_override="ITW",
        named_symbol_lookback=16,
    )

    assert captured["tool_input"]["years"] == 16


def test_named_symbol_inherited_lookback_steps_down_to_target_metadata(monkeypatch):
    captured = {}

    def fake_run_tool(name, tool_input, user_id):
        captured.update(tool_input=tool_input)
        return {"card": {"symbol": "NEW", "headline": "NEW - Won 8/12 years"}}

    monkeypatch.setattr(tara_gateway, "run_tool", fake_run_tool)
    monkeypatch.setattr(
        tara_gateway, "_symbol_max_available_years", lambda market, symbol, token: 12
    )

    tara_gateway._execute_tara_tool(
        "analyze_symbol",
        {"symbol": "NEW", "market": "2", "years": 10},
        "user-42",
        [],
        {},
        [],
        user_token="viewer-token",
        named_symbol_override="NEW",
        named_symbol_lookback=16,
    )

    assert captured["tool_input"]["years"] == 12


def test_tara_brief_card_keeps_twr_without_restoring_heavy_receipts():
    brief = tara_gateway._briefify(
        {
            "card": {
                "symbol": "ITW",
                "headline": "ITW long - Won 15/16 years",
                "stats": {
                    "historical_win_rate": 0.9375,
                    "sharpe_ratio": 1.64,
                    "sharpe_ratio_mfe": 2.18,
                    "avg_return_pct": 12.87,
                    "years": "16",
                    "std_dev_pct": 7.0,
                },
                "receipts": {"per_year": [{"year": "2021", "return_pct": -2.09}]},
            }
        }
    )

    assert brief["card"]["stats"]["sharpe_ratio_mfe"] == 2.18
    assert "std_dev_pct" not in brief["card"]["stats"]
    assert "receipts" not in brief["card"]


def test_openai_http_failure_is_classified_and_does_not_expose_body(monkeypatch, caplog):
    class Response:
        status_code = 429
        text = "provider-private-detail"

    monkeypatch.setattr(openai_tools, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_tools.requests, "post", lambda *args, **kwargs: Response())

    with pytest.raises(openai_tools.OpenAIAPIError, match="rate_limit"):
        openai_tools.send_openai_response([{"role": "user", "content": "hello"}])
    assert "provider-private-detail" not in caplog.text


def test_missing_openai_credential_is_configuration_failure_not_api_fallback(monkeypatch):
    monkeypatch.setattr(openai_tools, "OPENAI_API_KEY", "")
    with pytest.raises(openai_tools.OpenAIConfigurationError):
        openai_tools.send_openai_response([{"role": "user", "content": "hello"}])


def test_chat_route_retries_haiku_when_luna_fails(monkeypatch, caplog):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(chatbot_module, "build_deterministic_reply", lambda *args, **kwargs: None)
    monkeypatch.setattr(chatbot_module, "build_system_prompt", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: OPENAI_PROVIDER,
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
    assert "primary_provider=openai" in caplog.text
    assert "primary_model=gpt-5.6-luna" in caplog.text
    assert "fallback_model=claude-haiku-4-5-20251001" in caplog.text
    assert "category=adapter_error" in caplog.text
    assert "simulated provider failure" not in caplog.text


def test_chat_route_does_not_fallback_for_missing_primary_configuration(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    monkeypatch.setattr(chatbot_module, "build_deterministic_reply", lambda *args, **kwargs: None)
    monkeypatch.setattr(chatbot_module, "build_system_prompt", lambda *args, **kwargs: [])
    monkeypatch.setattr(chatbot_module, "select_tara_provider", lambda: OPENAI_PROVIDER)
    monkeypatch.setattr(chatbot_module, "TARA_TOOLS_ENABLED", True)
    monkeypatch.setattr(
        chatbot_module,
        "run_chat_with_openai_tools",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            openai_tools.OpenAIConfigurationError("missing primary")
        ),
    )
    monkeypatch.setattr(
        chatbot_module,
        "run_chat_with_tools",
        lambda *args, **kwargs: pytest.fail("configuration failures must not use Haiku"),
    )
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    body = {
        "message": "What can you do?",
        "history": [{"role": "user", "content": "What can you do?"}],
        "wave_viewer": {},
        "screen_context": {},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "configuration-test"
        response = chatbot_module.chat.__wrapped__()

    assert response.get_json()["reply"].startswith("Sorry")


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


def test_chat_route_uses_current_visible_googl_row_not_stale_history(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("current-table selection must bypass providers"),
    )
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    message = "show me something good from the table"
    body = {
        "message": message,
        "history": [
            {
                "role": "assistant",
                "content": "Earlier we discussed an expired GOOGL window from July.",
            },
            {"role": "user", "content": message},
        ],
        "wave_viewer": {"symbol": "MSFT"},
        "screen_context": {"opportunity_rows": 2},
        "opp_table_market": "2",
        "opp_table_pe_cycle": "cons",
        "opportunities": [
            {
                "date": "2026-08-07",
                "symbol": "GOOGL",
                "days_out": 21,
                "direction": "Long",
                "avg_profit": 4.2,
                "sharpe_ratio": 1.91,
            },
            {
                "date": "2026-08-08",
                "symbol": "AAPL",
                "days_out": 12,
                "direction": "Short",
                "sharpe_ratio": 1.44,
            },
        ],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "current-table-googl-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == [
        {
            "type": "load_opportunity",
            "rank": 1,
            "spec": {
                "symbol": "GOOGL",
                "market": "2",
                "entry_date": "2026-08-07",
                "days_out": 21,
                "pe_cycle": "cons",
            },
        }
    ]
    assert "highest-ranked visible row (#1): GOOGL long" in payload["reply"]
    assert "July" not in payload["reply"]


@pytest.mark.parametrize(
    "message, expected_slide, expected_reply",
    [
        ("show me the trend chart", "trend_chart", "Trend Chart"),
        ("show me the stats", "wave_stats", "Wave Stats"),
        ("show me AI Scores", "ai_scores", "AI Scores"),
        ("open the price chart", "price_chart", "Price Chart"),
    ],
)
def test_chat_route_moves_lower_panel_without_calling_a_provider(
    monkeypatch, message, expected_slide, expected_reply
):
    from flask import Flask, g
    import chatbot as chatbot_module

    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("lower-panel commands must bypass providers"),
    )
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    body = {
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {"symbol": "ADI", "years": "16", "pe_cycle": "cons"},
        "screen_context": {"ai_scores_available": expected_slide == "ai_scores"},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "panel-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == [
        {"type": "set_view", "spec": {"bottom_slide": expected_slide}}
    ]
    assert expected_reply in payload["reply"]


def test_chat_route_explains_when_ai_scores_panel_is_not_available(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    body = {
        "message": "show me AI Scores",
        "history": [],
        "wave_viewer": {"symbol": "BTCUSD", "market": "16"},
        "screen_context": {"ai_scores_available": False},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "panel-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == []
    assert "not available for this market" in payload["reply"]
    assert "supported US stocks and ETFs" in payload["reply"]


def test_system_prompt_forces_named_symbol_over_loaded_symbol():
    import chatbot as chatbot_module

    blocks = chatbot_module.build_system_prompt(
        {
            "symbol": "TDG",
            "start_date": "2026-08-02",
            "days_out": "30",
            "years": "16",
            "pe_cycle": "cons",
            "direction": "long",
            "stats": {},
            "yearly_results": [],
        },
        [],
        screen_context={},
        user_message="What does TWR reveal about this ITW pattern that Sharpe misses?",
    )
    prompt = "\n".join(block["text"] for block in blocks)

    assert "EXPLICIT NAMED-SYMBOL OVERRIDE" in prompt
    assert "the user named ITW, while TDG is currently loaded" in prompt
    assert "Do not answer with or relabel TDG's statistics" in prompt
    assert "Analyze and load ITW at 16 years, not the default 10" in prompt


@pytest.mark.parametrize(
    "message, expected",
    [
        ("I don't like all the tooltips", False),
        ("I don't understand all these controls", True),
    ],
)
def test_chat_route_changes_tooltips_without_calling_a_provider(
    monkeypatch, message, expected
):
    from flask import Flask, g
    import chatbot as chatbot_module

    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("tooltip commands must bypass providers"),
    )
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    body = {
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {},
        "screen_context": {},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "tooltip-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == [
        {"type": "set_view", "spec": {"show_tooltips": expected}}
    ]
    assert "upper-left toolbar" in payload["reply"]


def test_chat_route_explains_trend_arrow_without_calling_a_provider(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("trend-arrow questions must bypass providers"),
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
        "message": "what is the red arrow next to trend long?",
        "history": [
            {"role": "user", "content": "what is the red arrow next to trend long?"}
        ],
        "wave_viewer": {
            "symbol": "MET",
            "direction": "long",
            "stats": {
                "Trade Dir": "long",
                "Trend Long": "69",
                "Trend Long1": "74",
            },
        },
        "screen_context": {},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "trend-arrow-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert payload["actions"] == []
    assert "moved from 74 to 69" in payload["reply"]
    assert "69/100 score is still <b>Aligned</b>" in payload["reply"]
    assert "arrow only shows how that score changed" in payload["reply"]
    assert seen["provider"] == "deterministic"


def test_chat_route_passes_loaded_lookback_to_a_different_named_symbol(monkeypatch):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(chatbot_module, "build_deterministic_reply", lambda *args, **kwargs: None)
    monkeypatch.setattr(chatbot_module, "build_system_prompt", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: OPENAI_PROVIDER,
    )
    monkeypatch.setattr(chatbot_module, "TARA_TOOLS_ENABLED", True)

    def fake_openai(*args, **kwargs):
        seen.update(kwargs)
        return "ITW result", []

    monkeypatch.setattr(chatbot_module, "run_chat_with_openai_tools", fake_openai)
    monkeypatch.setattr(chatbot_module, "log_question", lambda *args, **kwargs: None)

    app = Flask(__name__)
    message = "how does ITW do?"
    body = {
        "message": message,
        "history": [{"role": "user", "content": message}],
        "wave_viewer": {
            "symbol": "ADI",
            "years": "16",
            "pe_cycle": "cons",
            "start_date": "2026-08-02",
            "days_out": "30",
        },
        "screen_context": {},
        "opportunities": [],
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "lookback-test"
        response = chatbot_module.chat.__wrapped__()

    assert response.get_json()["reply"] == "ITW result"
    assert seen["named_symbol_override"] == "ITW"
    assert seen["named_symbol_lookback"] == 16


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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Convince me I should use seasonality", "Why seasonality matters"),
        ("Help me come up with a winning strategy", "Build around measurable odds"),
        ("Why does AI only do the first 90 days?", "Why TradeWave uses 90-day AI horizons"),
    ],
)
def test_signature_product_questions_bypass_models_and_live_ai_scorer(
    monkeypatch, message, expected
):
    from flask import Flask, g
    import chatbot as chatbot_module

    seen = {}
    monkeypatch.setattr(
        chatbot_module,
        "select_tara_provider",
        lambda *args, **kwargs: pytest.fail("signature product answers must bypass providers"),
    )
    monkeypatch.setattr(
        chatbot_module,
        "log_question",
        lambda user_id, question, response, wave_viewer, provider="unknown": seen.update(
            provider=provider, response=response
        ),
    )

    rows = [
        {
            "year": year,
            "underlying_return_pct": float(index + 1),
            "upside_excursion_pct": float(index + 3),
            "downside_excursion_pct": -1.0,
        }
        for index, year in enumerate(range(2016, 2026))
    ]
    rows.append(
        {
            "year": 2026,
            "underlying_return_pct": 0.0,
            "upside_excursion_pct": 0.0,
            "downside_excursion_pct": 0.0,
        }
    )
    app = Flask(__name__)
    app.extensions["tara_ai_analysis_context"] = lambda *args, **kwargs: pytest.fail(
        "signature product answers must not wait for live AI scoring"
    )
    body = {
        "message": message,
        "history": [{"role": "user", "content": message}],
        "token": "browser-token",
        "wave_viewer": {
            "symbol": "AVGO",
            "market": "2",
            "start_date": "2026-08-02",
            "days_out": "133",
            "years": "10",
            "direction": "long",
            "selection_origin": "scanner",
            "stats": {"Sharpe Ratio": "1.78"},
            "yearly_results": rows,
        },
        "screen_context": {"selected_lookback": "10", "full_history_years": "17"},
        "opportunities": [],
        "opp_table_market": "2",
    }
    with app.test_request_context("/chatbot/chat", method="POST", json=body):
        g.chatbot_user_id = "signature-product-test"
        response = chatbot_module.chat.__wrapped__()

    payload = response.get_json()
    assert expected in payload["reply"]
    assert 'class="tara-analysis"' in payload["reply"]
    assert payload["actions"] == []
    assert seen["provider"] == "deterministic"
