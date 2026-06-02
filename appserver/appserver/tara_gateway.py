"""Tara -> v1 API gateway client (Phase 1: read-client).

The in-product assistant ("Tara", chatbot.py) calls the SAME public v1 gateway the API +
MCP server use, so the numbers it narrates are the gateway's server-composed SignalCards -
one source of truth, signals-only, same disclaimer. See docs/TARA_GATEWAY_INTEGRATION.md.

Auth (metering option A): Tara authenticates with the internal 'chatbot' service key
(config.TARA_GATEWAY_KEY) and passes the END USER's web id as X-TW-On-Behalf-Of, so the
gateway meters ML / rate / usage PER WEB USER against the chatbot tier's own quota (the
delegated principal is 'cb:'-namespaced server-side, separate from the API ML bucket).

Fail-soft: a gateway hiccup returns an {'error': ...} dict the model can narrate around -
it must never raise into the chat handler. When the gateway is not configured (no URL/key),
TARA_TOOLS_ENABLED is False and chatbot.py falls back to the plain no-tools chat.
"""
import json
import logging
import sys
from urllib.parse import quote

import requests

sys.path.insert(0, '/home/flask')
import config

from AI_tools_appserver import send_claude_messages

log = logging.getLogger("tara_gateway")

GATEWAY_URL = (config.TARA_GATEWAY_URL or "").rstrip("/")
SERVICE_KEY = config.TARA_GATEWAY_KEY or ""
TARA_TOOLS_ENABLED = bool(GATEWAY_URL and SERVICE_KEY)

_MAX_TOOL_ROUNDS = 4          # cap the agentic loop (each round = one gateway fan-out)
_TOOL_RESULT_CAP = 6000       # chars per tool result fed back to the model


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool-use). A lean, opinionated set of the flagships so
# Haiku routes cleanly; descriptions tell it to ground every claim in a tool result.
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "find_best_opportunities",
        "description": (
            "Scan the markets for the best seasonal setups right now, ranked by Sharpe. Use "
            "this for 'what should I trade', 'anything good in <market>', 'best setups this "
            "month'. Returns ready SignalCards (entry/hold, win rate, Sharpe, avg return %)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "markets": {"type": "string", "description": "comma list of market names or ids '0'..'16'; omit for all in scope"},
                "window": {"type": "string", "description": "'now' | 'next_2_weeks' | 'next_month' | 'YYYY-MM-DD..YYYY-MM-DD'"},
                "direction": {"type": "string", "enum": ["long", "short"]},
                "min_win_rate": {"type": "number", "description": "0..1"},
                "min_days": {"type": "integer"}, "max_days": {"type": "integer"},
                "min_avg_return": {"type": "number", "description": "percent, e.g. 5 = 5%"},
                "min_sharpe": {"type": "number"},
                "pe_cycle": {"type": "string", "enum": ["consecutive", "pe"]},
                "years": {"type": "integer", "description": "lookback 1-99 (default 10)"},
                "min_winning_years": {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "analyze_symbol",
        "description": (
            "Deep-dive ONE symbol into a rich SignalCard (best setup + receipts + order "
            "ticket) plus its other setups. Pin a specific setup with entry_date (+days_out) "
            "or a period preset; pe_cycle/years are the lookback knobs. Use for 'analyze GLD', "
            "'is AAPL seasonal now', 'explain this pattern over 20 years'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "market": {"type": "string", "description": "market id '0'..'16'; optional if the symbol is unique"},
                "direction": {"type": "string", "enum": ["long", "short"]},
                "days_out": {"type": "integer"},
                "entry_date": {"type": "string", "description": "YYYY-MM-DD - pin THIS exact setup"},
                "pe_cycle": {"type": "string", "enum": ["consecutive", "pe"]},
                "years": {"type": "integer"},
                "period": {"type": "string", "description": "jan..dec | q1..q4 | spring|summer|fall|winter | ytd|year_end|buy_hold"},
                "reverse": {"type": "boolean"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_symbol_patterns",
        "description": (
            "A security's TOP seasonal patterns across the whole year, ranked by Sharpe (the "
            "wave-viewer pattern dropdown). Use for 'what are GLD's best windows', 'show me all "
            "of AAPL's seasonal patterns'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "market": {"type": "string"},
                "pe_cycle": {"type": "string", "enum": ["consecutive", "pe"]},
                "years": {"type": "integer"},
                "min_days": {"type": "integer"}, "max_days": {"type": "integer"},
                "min_sharpe": {"type": "number"},
            },
            "required": ["symbol", "market"],
        },
    },
    {
        "name": "explain_pick",
        "description": (
            "Today's AI daily pick as a full SignalCard WITH its live forward-tested track "
            "record (made in advance, scored later - real out-of-sample proof, not a backtest). "
            "Use for 'today's pick', 'what is the AI recommending', 'does this actually work'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

# tool name -> (gateway path template, allowed query params). {symbol} is URL-encoded.
_ALLOWED = {
    "find_best_opportunities": ("/scan", [
        "markets", "window", "direction", "min_win_rate", "min_days", "max_days",
        "min_avg_return", "min_sharpe", "pe_cycle", "years", "min_winning_years", "limit"]),
    "analyze_symbol": ("/analyze/{symbol}", [
        "market", "direction", "days_out", "entry_date", "pe_cycle", "years", "period", "reverse"]),
    "get_symbol_patterns": ("/securities/{symbol}/patterns", [
        "market", "pe_cycle", "years", "min_days", "max_days", "min_sharpe"]),
    "explain_pick": ("/daily-pick", []),
}


def _get(path, params, user_id):
    """GET the gateway as the chatbot principal, acting for `user_id`. Returns parsed JSON
    or a narration-safe {'error': ...} dict - never raises."""
    if not TARA_TOOLS_ENABLED:
        return {"error": "gateway not configured"}
    headers = {"Authorization": "Bearer " + SERVICE_KEY}
    if user_id:
        headers["X-TW-On-Behalf-Of"] = str(user_id)
    clean = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    try:
        # Short read timeout: a slow gateway must fail fast so the tool loop narrates around
        # it rather than stacking latency behind the Anthropic call (each round can repeat).
        r = requests.get(GATEWAY_URL + path, params=clean, headers=headers, timeout=(5, 20))
    except requests.RequestException as e:
        log.warning("tara gateway GET %s failed: %s", path, e)
        return {"error": "gateway unreachable"}
    if r.status_code != 200:
        return {"error": "gateway %s" % r.status_code}
    try:
        return r.json()
    except ValueError:
        return {"error": "gateway returned non-JSON"}


def run_tool(name, tool_input, user_id):
    """Dispatch one tool_use to the gateway. Allowlisted path + params only."""
    spec = _ALLOWED.get(name)
    if not spec:
        return {"error": "unknown tool: %s" % name}
    path_tpl, allowed = spec
    tool_input = tool_input or {}
    path = path_tpl
    if "{symbol}" in path_tpl:
        sym = tool_input.get("symbol")
        if not sym:
            return {"error": "symbol is required"}
        path = path_tpl.replace("{symbol}", quote(str(sym), safe=""))
    params = {k: tool_input.get(k) for k in allowed if k in tool_input}
    return _get(path, params, user_id)


# Trimming a too-large tool result. We must NEVER raw-slice json.dumps(...) - that emits
# malformed JSON to the model. Instead cap list fields + drop the heaviest nested card fields,
# always re-serializing to VALID JSON (last resort = a valid 'too large' stub).
_LIST_KEYS = ("cards", "opportunities", "patterns", "other_setups", "results")
_HEAVY_CARD_KEYS = ("receipts", "next_step", "edge_basis", "disclaimer")
_LIST_CAP = 8


def _slim(item):
    if not isinstance(item, dict):
        return item
    return {k: v for k, v in item.items() if k not in _HEAVY_CARD_KEYS}


def _bounded_json(out):
    """Serialize a tool result to VALID JSON within _TOOL_RESULT_CAP."""
    s = json.dumps(out)
    if len(s) <= _TOOL_RESULT_CAP:
        return s
    if isinstance(out, dict):
        t = dict(out)
        for k in _LIST_KEYS:                       # cap long lists, note what was dropped
            v = t.get(k)
            if isinstance(v, list) and len(v) > _LIST_CAP:
                t[k] = v[:_LIST_CAP]
                t["_truncated"] = "showing first %d of %d %s" % (_LIST_CAP, len(v), k)
        for k in _LIST_KEYS:                        # drop heavy nested fields from list items
            if isinstance(t.get(k), list):
                t[k] = [_slim(it) for it in t[k]]
        if isinstance(t.get("card"), dict):         # and from a single deep-dive card
            t["card"] = _slim(t["card"])
        s = json.dumps(t)
        if len(s) <= _TOOL_RESULT_CAP:
            return s
    return json.dumps({"error": "result too large to include in full",
                       "note": "narrow the request (fewer markets, a specific symbol, or a tighter filter)"})


def _text_of(blocks):
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def run_chat_with_tools(messages, system, user_id, model, cache_ttl="5m"):
    """Run the Tara chat with gateway tool-use. `messages` ends with the user turn. Returns
    the final assistant TEXT. The model may call gateway tools; we execute them as `user_id`
    and feed results back until it answers (capped at _MAX_TOOL_ROUNDS)."""
    convo = list(messages)
    for _ in range(_MAX_TOOL_ROUNDS):
        resp = send_claude_messages(convo, model=model, system=system,
                                    cache_system=True, cache_ttl=cache_ttl,
                                    tools=TOOLS, return_raw=True)
        blocks = resp.get("content", []) or []
        if resp.get("stop_reason") != "tool_use":
            return _text_of(blocks)
        # echo the assistant's tool_use turn back verbatim, then answer each tool call
        convo.append({"role": "assistant", "content": blocks})
        results = []
        for b in blocks:
            if b.get("type") == "tool_use":
                out = run_tool(b.get("name"), b.get("input"), user_id)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": b.get("id"),
                    "content": _bounded_json(out),
                })
        convo.append({"role": "user", "content": results})
    # Out of tool rounds - force a final text answer with no further tool calls.
    return send_claude_messages(convo, model=model, system=system,
                                cache_system=True, cache_ttl=cache_ttl)
