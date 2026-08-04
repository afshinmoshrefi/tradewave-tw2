"""Small OpenAI Responses API adapter for Tara's GPT-5.6 Luna primary.

Tara intentionally keeps its provider integration local instead of requiring the
OpenAI SDK in the appserver environment.  The adapter accepts the same segmented
system prompt and tool schemas as the established Anthropic path, then translates
them to Responses API input items and function tools.
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

from pooled_http import http as requests


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config
from tara_runtime_policy import PRIMARY_MODEL


log = logging.getLogger("openai_tools_appserver")

OPENAI_API_KEY = config.OPENAI_KEY
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GPT_56_LUNA = PRIMARY_MODEL

_CACHE_KEY_VERSION = "tara-luna-v1"
_CACHE_SHARDS = 4


class OpenAIAPIError(Exception):
    """A runtime provider/API/adapter failure eligible for the safe fallback."""

    def __init__(self, category):
        super().__init__(category)
        self.category = str(category or "adapter_error")


class OpenAIConfigurationError(RuntimeError):
    """A deployment/configuration failure that must never select a fallback."""


def failure_category(exc):
    """Return a bounded nonsecret category for operational fallback telemetry."""

    if isinstance(exc, OpenAIAPIError):
        allowed = {
            "timeout",
            "connection",
            "authentication",
            "rate_limit",
            "provider_server",
            "provider_http",
            "invalid_response",
            "adapter_error",
        }
        return exc.category if exc.category in allowed else "adapter_error"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connection" in name:
        return "connection"
    return "adapter_error"


def prompt_cache_key(user_id):
    """Share Tara's stable prefix while spreading traffic across bounded cache shards."""

    digest = hashlib.sha256(str(user_id or "unknown").encode("utf-8")).digest()
    shard = int.from_bytes(digest[:4], "big") % _CACHE_SHARDS
    return f"{_CACHE_KEY_VERSION}-{shard:02d}"


def _system_blocks(system):
    if not system:
        return []
    if isinstance(system, str):
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    if not isinstance(system, (list, tuple)):
        raise TypeError("system must be a string or an ordered list of text blocks")
    blocks = []
    for item in system:
        block = {"type": "text", "text": item} if isinstance(item, str) else dict(item)
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise TypeError("system blocks must contain type=text and string text")
        blocks.append(block)
    return blocks


def build_responses_input(messages, system=None):
    """Translate Tara's ordered system blocks and string history to Responses input.

    Anthropic's ``cache_control`` marker is provider-local.  For OpenAI it becomes
    one explicit prompt-cache breakpoint on the same stable block; topic-selected
    knowledge and live screen facts remain after that breakpoint.
    """

    input_items = []
    blocks = _system_blocks(system)
    if blocks:
        content = []
        breakpoint_added = False
        for block in blocks:
            item = {"type": "input_text", "text": block["text"]}
            if block.get("cache_control") and not breakpoint_added:
                item["prompt_cache_breakpoint"] = {"mode": "explicit"}
                breakpoint_added = True
            content.append(item)
        if not breakpoint_added:
            content[-1]["prompt_cache_breakpoint"] = {"mode": "explicit"}
        input_items.append({"role": "developer", "content": content})

    for message in messages or []:
        if not isinstance(message, dict):
            raise TypeError("messages must be dictionaries")
        role = "assistant" if message.get("role") == "assistant" else "user"
        content = message.get("content", "")
        if not isinstance(content, str):
            raise TypeError("OpenAI canary conversation history must contain string content")
        input_items.append({"role": role, "content": content})
    return input_items


def to_openai_tools(tools):
    """Translate Anthropic ``input_schema`` function tools to Responses API tools."""

    converted = []
    for tool in tools or []:
        if not isinstance(tool, dict) or not tool.get("name"):
            raise TypeError("tools must contain named function schemas")
        parameters = tool.get("parameters") or tool.get("input_schema")
        if not isinstance(parameters, dict):
            raise TypeError("tool parameters must be an object schema")
        converted.append(
            {
                "type": "function",
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": parameters,
                # The existing schemas are intentionally permissive and do not all
                # declare additionalProperties:false, so strict mode is not valid here.
                "strict": False,
            }
        )
    return converted


def response_text(response):
    """Collect all assistant output text from a Responses API response."""

    chunks = []
    for item in (response or {}).get("output", []) or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks).strip()


def function_calls(response):
    """Return Responses API function-call output items in provider order."""

    return [
        item
        for item in (response or {}).get("output", []) or []
        if isinstance(item, dict) and item.get("type") == "function_call"
    ]


def decode_function_arguments(call):
    """Decode a function call's JSON arguments; reject non-object argument values."""

    raw = (call or {}).get("arguments") or "{}"
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise OpenAIAPIError("invalid_response") from exc
    if not isinstance(decoded, dict):
        raise OpenAIAPIError("invalid_response")
    return decoded


def _log_usage(model, response):
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    log.info(
        "OpenAI usage model=%s input=%s cache_write=%s cache_read=%s output=%s reasoning=%s",
        model,
        usage.get("input_tokens", 0),
        input_details.get("cache_write_tokens", input_details.get("cache_write_input_tokens", 0)),
        input_details.get("cached_tokens", input_details.get("cache_read_tokens", 0)),
        usage.get("output_tokens", 0),
        output_details.get("reasoning_tokens", 0),
    )


def send_openai_response(input_items, model=GPT_56_LUNA, tools=None,
                         cache_key=None, max_output_tokens=2048,
                         timeout=(15, 100)):
    """Send one stateless Responses API request and return its full JSON body."""

    if not OPENAI_API_KEY:
        raise OpenAIConfigurationError("OpenAI primary credential is not configured")
    payload = {
        "model": model,
        "input": input_items,
        "max_output_tokens": max_output_tokens,
        "reasoning": {"effort": "low"},
        "text": {"verbosity": "low"},
        "store": False,
        "prompt_cache_options": {"mode": "explicit"},
    }
    if cache_key:
        payload["prompt_cache_key"] = cache_key
    if tools:
        payload["tools"] = to_openai_tools(tools)

    headers = {
        "Authorization": "Bearer " + OPENAI_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:
        raise OpenAIAPIError(failure_category(exc)) from exc
    if response.status_code != 200:
        status = int(response.status_code)
        if status in {401, 403}:
            category = "authentication"
        elif status == 429:
            category = "rate_limit"
        elif status >= 500:
            category = "provider_server"
        else:
            category = "provider_http"
        # Never log the provider body: it can echo request or customer content.
        log.warning("OpenAI API failure status=%s category=%s", status, category)
        raise OpenAIAPIError(category)
    try:
        data = response.json()
    except ValueError as exc:
        raise OpenAIAPIError("invalid_response") from exc
    _log_usage(model, data)
    return data


def send_openai_messages(messages, system=None, user_id=None, model=GPT_56_LUNA,
                         max_output_tokens=2048):
    """Provider-compatible convenience path for Tara when gateway tools are disabled."""

    response = send_openai_response(
        build_responses_input(messages, system=system),
        model=model,
        cache_key=prompt_cache_key(user_id),
        max_output_tokens=max_output_tokens,
    )
    text = response_text(response)
    if not text:
        raise OpenAIAPIError("invalid_response")
    return text
