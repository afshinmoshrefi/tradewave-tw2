"""Tara -> v1 API gateway client (Phase 1: read-client).

The in-product assistant ("Tara", chatbot.py) calls the SAME public v1 gateway the API +
MCP server use, so the numbers it narrates are the gateway's server-composed PatternCards -
one source of truth, derived-data only, same disclaimer. See docs/TARA_GATEWAY_INTEGRATION.md.

Auth (metering option A): Tara authenticates with the internal 'chatbot' service key
(config.TARA_GATEWAY_KEY) and passes the END USER's web id as X-TW-On-Behalf-Of, so the
gateway meters ML / rate / usage PER WEB USER against the chatbot tier's own quota (the
delegated principal is 'cb:'-namespaced server-side, separate from the API ML bucket).

Fail-soft: a gateway hiccup returns an {'error': ...} dict the model can narrate around -
it must never raise into the chat handler. When the gateway is not configured (no URL/key),
TARA_TOOLS_ENABLED is False and chatbot.py falls back to the plain no-tools chat.
"""
import datetime
import json
import logging
import re
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
            "month'. Returns ready PatternCards (entry/hold, win rate, Sharpe, avg return %)."
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
            "Deep-dive ONE symbol into a rich PatternCard (best setup + receipts + order "
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
            "Today's AI daily pick as a full PatternCard WITH its live forward-tested track "
            "record (made in advance, scored later - real out-of-sample proof, not a backtest). "
            "Use for 'today's pick', 'what is the AI recommending', 'does this actually work'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_view",
        "description": (
            "DRIVE THE WAVE-VIEWER: load a symbol/setup or change a knob so the user actually "
            "SEES it on screen, instead of telling them where to click. Call this when the user "
            "says show me / load / pull up / open / change the years / switch to the PE cycle. "
            "Pass concrete fields. To show a date-range PRESET (a month/quarter/season), FIRST "
            "call analyze_symbol with period= to get the resolved entry_date + days_out, THEN "
            "pass those here. Usually pair this with a read tool so you can also narrate the setup."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "resource id '0'..'16' of the security's market"},
                "symbol": {"type": "string"},
                "entry_date": {"type": "string", "description": "YYYY-MM-DD"},
                "days_out": {"type": "integer", "description": "1-366"},
                "years": {"type": "integer", "description": "lookback 1-99"},
                "pe_cycle": {"type": "string", "enum": ["consecutive", "pe0", "pe1", "pe2", "pe3"],
                             "description": "wave-viewer cycle selector; consecutive = normal years"},
            },
        },
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


# ---- update_view: validate the model's requested wave-viewer ViewSpec (Phase 2 actuation) ----
# Allowlist + range-check every field server-side before it can become a client action. The
# client re-validates too (defense in depth). Only these fields can ever drive the UI.
_VS_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")
_VS_MARKETS = {str(i) for i in range(17) if i not in (14, 15)}   # 14/15 (Korea) removed; never renumber
_VS_PE = {"consecutive": "cons", "cons": "cons", "pe0": "pe0", "pe1": "pe1", "pe2": "pe2", "pe3": "pe3"}


def _validate_view_spec(spec):
    """Return a cleaned ViewSpec containing ONLY valid, in-range fields (drops the rest).
    A field that fails validation is silently omitted so a partial/garbled spec still applies
    the good parts. Returns {} if nothing is valid (the loop then reports ok:false to the model)."""
    if not isinstance(spec, dict):
        return {}
    out = {}
    sym = spec.get("symbol")
    if isinstance(sym, str) and _VS_SYMBOL_RE.match(sym):
        out["symbol"] = sym.upper()
    mk = spec.get("market")
    if mk is not None and str(mk) in _VS_MARKETS:
        out["market"] = str(mk)
    ed = spec.get("entry_date")
    if isinstance(ed, str):
        try:
            datetime.datetime.strptime(ed, "%Y-%m-%d")
            out["entry_date"] = ed
        except ValueError:
            pass
    do = spec.get("days_out")
    if isinstance(do, int) and not isinstance(do, bool) and 1 <= do <= 366:
        out["days_out"] = do
    yr = spec.get("years")
    if isinstance(yr, int) and not isinstance(yr, bool) and 1 <= yr <= 99:
        out["years"] = yr
    pe = spec.get("pe_cycle")
    if isinstance(pe, str) and pe.lower() in _VS_PE:
        out["pe_cycle"] = _VS_PE[pe.lower()]
    return out


def _text_of(blocks):
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def run_chat_with_tools(messages, system, user_id, model, cache_ttl="5m"):
    """Run the Tara chat with gateway tool-use. `messages` ends with the user turn. Returns
    (final_text, actions): the assistant TEXT plus any UI actions the model requested (Phase 2,
    e.g. [{'type':'set_view','spec':{...}}]). Read tools (scan/analyze/...) are executed as
    `user_id` against the gateway; update_view is validated server-side and queued as an action
    for the client to apply. Capped at _MAX_TOOL_ROUNDS."""
    convo = list(messages)
    actions = []
    for _ in range(_MAX_TOOL_ROUNDS):
        resp = send_claude_messages(convo, model=model, system=system,
                                    cache_system=True, cache_ttl=cache_ttl,
                                    tools=TOOLS, return_raw=True)
        blocks = resp.get("content", []) or []
        if resp.get("stop_reason") != "tool_use":
            return _text_of(blocks), actions
        # echo the assistant's tool_use turn back verbatim, then answer each tool call
        convo.append({"role": "assistant", "content": blocks})
        results = []
        for b in blocks:
            if b.get("type") != "tool_use":
                continue
            name, inp = b.get("name"), (b.get("input") or {})
            if name == "update_view":                       # client-side UI action, not a gateway call
                cleaned = _validate_view_spec(inp)
                if cleaned:
                    actions.append({"type": "set_view", "spec": cleaned})
                    out = {"ok": True, "applied": cleaned}
                else:
                    out = {"ok": False, "error": "no valid view fields to apply"}
            else:
                out = run_tool(name, inp, user_id)
            results.append({
                "type": "tool_result",
                "tool_use_id": b.get("id"),
                "content": _bounded_json(out),
            })
        convo.append({"role": "user", "content": results})
    # Out of tool rounds - force a final text answer with no further tool calls.
    final = send_claude_messages(convo, model=model, system=system,
                                 cache_system=True, cache_ttl=cache_ttl)
    return final, actions
