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
import uuid
from pathlib import Path
from urllib.parse import quote

from pooled_http import http as requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

from AI_tools_appserver import send_claude_messages
from openai_tools_appserver import (
    OpenAIAPIError,
    build_responses_input,
    decode_function_arguments,
    function_calls,
    prompt_cache_key,
    response_text,
    send_openai_response,
)

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
                "markets": {"type": "string", "description": "for a 'which <group> stocks' screen pass the SINGLE market id of that group (tech=1, dow=0, ...); comma list of names/ids '0'..'16' for a multi-market scan; omit for all in scope"},
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
            "For any new or different symbol/setup, FIRST use a read tool and copy its exact "
            "symbol + market id + entry_date + hold_days/days_out here; invented or partial "
            "setups are rejected. For a date-range preset (month/quarter/season), call "
            "analyze_symbol with period= first. A knob-only change or exact confirmed-view refresh "
            "may omit the setup fields."
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
                "show_mfe": {"type": "boolean", "description": "show/hide the best-move MFE overlay"},
                "show_mae": {"type": "boolean", "description": "show/hide the worst-move MAE overlay"},
                "show_tooltips": {
                    "type": "boolean",
                    "description": "show/hide TradeWave guidance tooltips across the UI",
                },
                "bottom_slide": {
                    "type": "string",
                    "enum": ["trend_chart", "wave_stats", "price_chart"],
                    "description": "lower carousel panel to display",
                },
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


def _mini(item):
    """Tiniest usable shape of a card/row - enough to NAME and rank a result. Used as the
    last-resort trim so the model ALWAYS gets real named entries to answer with, never a
    content-free 'too large' (which makes it bail to manual click-instructions). Handles both
    a flat table-row and a nested card (stats/setup may be top-level or nested)."""
    if not isinstance(item, dict):
        return item
    st = item.get("stats") if isinstance(item.get("stats"), dict) else item
    setup = item.get("setup") if isinstance(item.get("setup"), dict) else item
    out = {}
    for k in ("rank", "symbol", "market", "direction", "bias", "headline"):
        if item.get(k) is not None:
            out[k] = item[k]
    for k in (
        "historical_win_rate",
        "sharpe_ratio",
        "sharpe_ratio_mfe",
        "avg_return_pct",
        "years",
    ):
        if st.get(k) is not None:
            out[k] = st[k]
    for k in ("entry_date", "hold_days", "days_out"):
        if setup.get(k) is not None:
            out[k] = setup[k]
    return out


# Tara (the in-app BRIEF assistant) receives the SAME gateway PatternCards as the public
# API/MCP research consumers, but she must narrate a one-line headline, not the research
# scaffolding (extend_research / suggested_checks / receipts / ml / alignment / median+stddev).
# Strip those heavy fields from every read-tool result she gets so the model surfaces the
# pre-composed `headline` + symbol instead of reciting checklists. (Tara-peak loop 2026-06-21)
_BRIEF_DROP = ("extend_research", "receipts", "next_step", "edge_basis", "edge_score",
               "alignment", "verdict", "ml", "tier_notes", "rank", "disclaimer", "bias",
               "blind_to", "suggested_checks", "synthesis_rule", "loop_back")
_BRIEF_STATS = (
    "historical_win_rate",
    "sharpe_ratio",
    "sharpe_ratio_mfe",
    "avg_return_pct",
    "years",
)
_BRIEF_SETUP = ("entry_date", "exit_date", "hold_days", "entry_window")


def _brief_card(c):
    if not isinstance(c, dict):
        return c
    out = {k: v for k, v in c.items() if k not in _BRIEF_DROP}
    if isinstance(out.get("stats"), dict):
        out["stats"] = {k: v for k, v in out["stats"].items() if k in _BRIEF_STATS}
    if isinstance(out.get("setup"), dict):
        out["setup"] = {k: v for k, v in out["setup"].items() if k in _BRIEF_SETUP}
    return out


def _briefify(out):
    """Reduce a gateway read-tool result to the BRIEF shape Tara should narrate: keep
    symbol + headline + slim setup + key stats; drop the research-agent scaffolding and the
    bulky forward-record/view blobs. Tara is the brief in-app assistant, NOT the research API."""
    if not isinstance(out, dict):
        return out
    t = {k: v for k, v in out.items() if k not in ("track_record", "view", "as_of", "featured_date")}
    if isinstance(t.get("card"), dict):
        t["card"] = _brief_card(t["card"])
    if "symbol" in t and "headline" in t:          # the result itself IS a card
        t = _brief_card(t)
    for k in _LIST_KEYS:                            # list of cards/rows (scan / patterns / other_setups)
        if isinstance(t.get(k), list):
            t[k] = [_brief_card(it) for it in t[k]]
    return t


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
        # STILL too large: keep the TOP entries in a MINIMAL shape so the model can always
        # NAME and rank real results and tell the user "more are in the table", instead of a
        # content-free 'too large' that makes it fall back to manual click-instructions.
        for k in _LIST_KEYS:
            v = out.get(k)
            if isinstance(v, list) and v:
                for n in (_LIST_CAP, 5, 3):
                    mini = {k: [_mini(it) for it in v[:n]],
                            "_truncated": ("showing the top %d of %d - more are in the "
                                           "opportunity table" % (min(n, len(v)), len(v)))}
                    s = json.dumps(mini)
                    if len(s) <= _TOOL_RESULT_CAP:
                        return s
    return json.dumps({"error": "result too large to include in full",
                       "note": "narrow the request to one market or a specific symbol"})


# ---- update_view: validate the model's requested wave-viewer ViewSpec (Phase 2 actuation) ----
# Allowlist + range-check every field server-side before it can become a client action. The
# client re-validates too (defense in depth). Only these fields can ever drive the UI.
_VS_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")
_VS_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VS_MARKETS = {str(i) for i in range(17) if i not in (14, 15)}   # 14/15 (Korea) removed; never renumber
_VS_PE = {"consecutive": "cons", "cons": "cons", "pe0": "pe0", "pe1": "pe1", "pe2": "pe2", "pe3": "pe3"}
_VS_FIELDS = {"symbol", "market", "entry_date", "days_out", "years", "pe_cycle"}


def _confirmed_view_setup(current_view):
    """Return the complete setup identity for an actually confirmed browser view.

    A symbol plus ``view_ready`` is not enough evidence for a partial refresh:
    the browser must also identify the exact market, entry date, and duration
    whose two charts succeeded.
    """
    current = current_view or {}
    if not isinstance(current, dict) or current.get("view_ready") is not True:
        return None
    symbol = current.get("symbol")
    market = current.get("market")
    entry_date = current.get("entry_date") or current.get("start_date")
    days_out = current.get("days_out")
    if not (
        isinstance(symbol, str)
        and _VS_SYMBOL_RE.fullmatch(symbol)
        and market is not None
        and str(market) in _VS_MARKETS
        and isinstance(entry_date, str)
        and _VS_DATE_RE.fullmatch(entry_date)
        and not isinstance(days_out, bool)
    ):
        return None
    try:
        datetime.datetime.strptime(entry_date, "%Y-%m-%d")
        parsed_days = int(days_out)
    except (TypeError, ValueError):
        return None
    if not 1 <= parsed_days <= 366:
        return None
    return {
        "symbol": symbol.upper(),
        "market": str(market),
        "entry_date": entry_date,
        "days_out": parsed_days,
    }


def _validate_view_spec(spec, current_view=None):
    """Validate one ViewSpec atomically; return {} when any field is invalid.

    Silently applying only the valid subset can produce a different chart than
    the one Tara described (for example, a new symbol with the previous
    symbol's dates). A symbol change therefore also requires a resolved
    entry_date + days_out pair. Same-symbol requests may omit the pair to
    explicitly refresh the current setup.
    """
    if not isinstance(spec, dict) or not spec or set(spec) - _VS_FIELDS:
        return {}
    out = {}
    if "symbol" in spec:
        sym = spec.get("symbol")
        if not (isinstance(sym, str) and _VS_SYMBOL_RE.fullmatch(sym)):
            return {}
        out["symbol"] = sym.upper()
    if "market" in spec:
        mk = spec.get("market")
        if mk is None or str(mk) not in _VS_MARKETS:
            return {}
        out["market"] = str(mk)
    if "entry_date" in spec:
        ed = spec.get("entry_date")
        if not (isinstance(ed, str) and _VS_DATE_RE.fullmatch(ed)):
            return {}
        try:
            datetime.datetime.strptime(ed, "%Y-%m-%d")
            out["entry_date"] = ed
        except ValueError:
            return {}
    if "days_out" in spec:
        do = spec.get("days_out")
        if not (isinstance(do, int) and not isinstance(do, bool) and 1 <= do <= 366):
            return {}
        out["days_out"] = do
    if "years" in spec:
        yr = spec.get("years")
        if not (isinstance(yr, int) and not isinstance(yr, bool) and 1 <= yr <= 99):
            return {}
        out["years"] = yr
    if "pe_cycle" in spec:
        pe = spec.get("pe_cycle")
        if not (isinstance(pe, str) and pe.lower() in _VS_PE):
            return {}
        out["pe_cycle"] = _VS_PE[pe.lower()]

    has_entry = "entry_date" in out
    has_days = "days_out" in out
    if has_entry != has_days:
        return {}
    # A date/duration pair changes the actual setup. It must carry the symbol
    # and market that a read tool resolved; otherwise the browser would fill
    # in stale current-view fields and an invented setup could slip through.
    if has_entry and "symbol" not in out:
        return {}
    if out.get("symbol"):
        confirmed_setup = _confirmed_view_setup(current_view)
        setup_is_current = (
            not (has_entry and has_days)
            or (
                confirmed_setup is not None
                and out["entry_date"] == confirmed_setup["entry_date"]
                and out["days_out"] == confirmed_setup["days_out"]
            )
        )
        can_refresh_confirmed_setup = (
            confirmed_setup is not None
            and out["symbol"] == confirmed_setup["symbol"]
            and setup_is_current
            and (
                "market" not in out
                or out["market"] == confirmed_setup["market"]
            )
        )
        if not can_refresh_confirmed_setup:
            if not (has_entry and has_days and "market" in out):
                return {}
    return out


def _view_action(spec):
    """Build one client action with a correlation id.

    `validated` means only that the server accepted the ViewSpec. It does NOT
    mean the browser applied it or that chart data loaded; the client reports
    that outcome separately.
    """
    return {
        "action_id": uuid.uuid4().hex,
        "type": "set_view",
        "status": "validated",
        "spec": spec,
    }


def _queue_view_action(actions, spec):
    """Append a ViewSpec once and return the canonical queued action."""
    for action in actions:
        if action.get("type") == "set_view" and action.get("spec") == spec:
            return action
    action = _view_action(spec)
    actions.append(action)
    return action


def _view_actions_conflict(actions):
    """Return True when one turn requests two different values for one view field."""
    merged = {}
    for action in actions:
        if action.get("type") != "set_view" or not isinstance(action.get("spec"), dict):
            continue
        for key, value in action["spec"].items():
            if key in merged and merged[key] != value:
                return True
            merged[key] = value
    return False


def _card_market_id(card):
    if not isinstance(card, dict):
        return ""
    market = card.get("market")
    if isinstance(market, dict):
        market = market.get("id")
    if market not in (None, "") and str(market) in _VS_MARKETS:
        return str(market)
    wave_viewer = card.get("wave_viewer")
    pattern = wave_viewer.get("pattern") if isinstance(wave_viewer, dict) else None
    if isinstance(pattern, dict) and str(pattern.get("market_id")) in _VS_MARKETS:
        return str(pattern["market_id"])
    return ""


def _view_spec_is_grounded(spec, card_list, current_view=None):
    """Bind a symbol/setup action to confirmed context or a read result from this turn."""
    if not spec.get("symbol"):
        return set(spec).issubset({"market", "years", "pe_cycle"})
    confirmed_setup = _confirmed_view_setup(current_view)
    exact_confirmed = (
        confirmed_setup is not None
        and spec["symbol"] == confirmed_setup["symbol"]
        and (
            "market" not in spec
            or spec["market"] == confirmed_setup["market"]
        )
        and (
            "entry_date" not in spec
            or (
                spec.get("entry_date") == confirmed_setup["entry_date"]
                and spec.get("days_out") == confirmed_setup["days_out"]
            )
        )
    )
    if exact_confirmed:
        return True

    for card in card_list or []:
        setup = card.get("setup") if isinstance(card, dict) else None
        if not isinstance(setup, dict):
            setup = card if isinstance(card, dict) else {}
        try:
            setup_days = (
                setup.get("hold_days")
                if setup.get("hold_days") is not None
                else setup.get("days_out")
            )
            hold_days = int(setup_days)
        except (TypeError, ValueError):
            continue
        if (
            str(card.get("symbol") or "").upper() == spec.get("symbol")
            and setup.get("entry_date") == spec.get("entry_date")
            and hold_days == spec.get("days_out")
            and _card_market_id(card) == spec.get("market")
        ):
            return True
    return False


def _text_of(blocks):
    return "".join(
        b.get("text", "")
        for b in (blocks or [])
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    ).strip()


# A model occasionally prints another provider's XML-like function-call
# notation instead of returning Anthropic's native tool_use blocks. That text
# is never executable and must never reach the browser as if it were an answer.
_INTERNAL_TOOL_MARKUP_RE = re.compile(
    r"<\s*/?\s*(?:function_calls?|invoke|parameter)\b",
    re.IGNORECASE,
)
_VIEW_COMPLETION_RE = re.compile(
    r"(?:"
    r"\b(?:is|are|was|were|has\s+been)\s+(?:already\s+|now\s+)?loaded\b"
    r"|\b(?:i(?:'ve|\s+have)?|we(?:'ve|\s+have)?)\s+loaded\b"
    r"|\b(?-i:[A-Z][A-Z0-9.\-]{0,14})\s+(?:has\s+)?loaded\s+successfully\b"
    r"|\bloaded\s+(?:on|in|into)\s+(?:the|your)\s+(?:chart|viewer|screen)\b"
    r"|^\s*loaded[.!]?\s*$"
    r"|\breloaded\b"
    r"|\breload\s+(?:is\s+)?complete\b"
    r"|\b[A-Za-z0-9.\-]{1,15}\s+is\s+(?:now\s+)?on\s+(?:the|your)\s+(?:chart|viewer|screen)\b"
    r"|\b[A-Za-z0-9.\-]{1,15}\s+is\s+(?:now\s+)?(?:displayed|shown|showing)\s+"
    r"(?:on|in)\s+(?:the|your)\s+(?:chart|viewer|screen)\b"
    r"|\b(?:chart|viewer|screen)\s+(?:now\s+)?(?:shows|displays)\b"
    r"|\b(?:the\s+)?(?:chart|view|viewer|screen)\s+is\s+(?:now\s+)?showing\b"
    r"|\b(?:the\s+)?(?:chart|viewer|screen)\s+(?:now\s+)?contains\b"
    r"|\b(?:the\s+)?(?:chart|view|viewer|screen)\s+(?:has|have)\s+been\s+"
    r"(?:updated|changed|switched)\b"
    r"|\b(?:the\s+)?(?:chart|view|viewer|screen)\s+(?:has|have)\s+refreshed\b"
    r"|\b(?:i(?:'ve|\s+have)?|we(?:'ve|\s+have)?)\s+"
    r"(?:put|placed|opened|shown)\b.{0,50}\b(?:chart|viewer|screen)\b"
    r"|\b(?:i(?:'ve|\s+have)?|we(?:'ve|\s+have)?)\s+brought\s+up\s+"
    r"(?-i:[A-Z][A-Z0-9.\-]{0,14})\b"
    r"|\b(?:you(?:'re|\s+are)|we(?:'re|\s+are)|i(?:'m|\s+am))\s+"
    r"(?:now\s+)?viewing\b"
    r"|\b(?:chart|view|viewer|screen)\s+(?:is\s+)?(?:ready|updated|changed)\b"
    r"|\b(?:switched|updated|changed)\s+(?:the|your)\s+(?:chart|view|viewer)\b"
    r"|\b(?:i(?:'ve|\s+have)?|we(?:'ve|\s+have)?)\s+switched\s+to\s+"
    r"(?-i:[A-Z][A-Z0-9.\-]{0,14})\b"
    r"|^\s*done(?:\s*[-:–—].*)?[.!]?\s*$"
    r")",
    re.IGNORECASE,
)
_VIEW_PROMISE_RE = re.compile(
    r"\b(?:"
    r"(?:i|we)\s*(?:'ll|’ll|\s+will|\s+(?:am|are)\s+going\s+to)\s+"
    r"(?:try\s+to\s+)?(?:load|reload|open|display|show|pull\s+up|bring\s+up)"
    r"|let\s+me\s+(?:load|reload|open|display|show|pull\s+up|bring\s+up)"
    r"|(?:loading|reloading|opening|displaying|pulling\s+up|bringing\s+up)\s+"
    r"(?:(?-i:[A-Z][A-Z0-9.\-]{0,14})|it|this|that|(?:the|your)\s+"
    r"(?:chart|view|viewer|screen))\b.{0,20}\bnow\b"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_VIEW_COMPLETION_RE = re.compile(
    r"\b(?:"
    r"(?:i|we)\s+(?:haven't|have\s+not|didn't|did\s+not|won't|will\s+not)\s+"
    r"(?:load|loaded|reload|reloaded|change|changed|update|updated|switch|switched)"
    r"(?:\s+|.{0,25}\b)(?:the|your)?\s*(?:chart|view|viewer|screen)?"
    r"|(?:the\s+)?(?:chart|view|viewer|screen)\s+"
    r"(?:wasn't|was\s+not|isn't|is\s+not|hasn't\s+been|has\s+not\s+been)\s+"
    r"(?:loaded|reloaded|changed|updated|switched|refreshed|ready)"
    r")\b",
    re.IGNORECASE,
)
_ALREADY_LOADED_SYMBOL_RE = re.compile(
    r"\b([A-Za-z0-9.\-]{1,15})\s+is\s+already\s+loaded\b",
    re.IGNORECASE,
)
_VIEW_SYMBOL_TOKEN = (
    r"(?!(?:chart|graph|viewer|screen|trades?|picks?|ideas?|setups?|ones?)\b)"
    r"[A-Za-z][A-Za-z0-9.\-]{0,14}"
)
_DIRECT_VIEW_REQUEST_RE = re.compile(
    r"(?:"
    r"\b(?:load|reload|pull\s+up)\b"
    r"|\b(?:show|open)\s+(?:me\s+)?(?:the\s+)?(?:another|something\s+good|"
    r"this\s+(?:setup|pattern)|that\s+(?:setup|pattern)|"
    r"(?!(?:how|what|why|where|guide|help|price|trend|bar|graph|chart|viewer)\b)"
    r"[A-Za-z][A-Za-z0-9.\-]{0,14})\b"
    r"|\bput\b.{0,40}\b(?:on|in)\s+(?:the|your)\s+(?:chart|viewer)\b"
    r"|\b(?:can|could|may)\s+i\s+(?:see|view)\s+(?:the\s+)?"
    + _VIEW_SYMBOL_TOKEN +
    r"\b"
    r"|\bpull\s+(?:me\s+)?"
    + _VIEW_SYMBOL_TOKEN +
    r"\s+up\b"
    r"|\bdisplay\s+(?:me\s+)?(?:the\s+)?"
    + _VIEW_SYMBOL_TOKEN +
    r"\b"
    r"|\btake\s+me\s+to\s+(?:the\s+)?"
    + _VIEW_SYMBOL_TOKEN +
    r"\b"
    r")",
    re.IGNORECASE,
)
_VIEW_KNOB_REQUEST_RE = re.compile(
    r"\b(?:switch|change|set)\b.{0,50}\b(?:years?|lookback|pe(?:\s+cycle)?|"
    r"market|group|nasdaq|dow|s&p|etf|futures?|crypto|forex)\b",
    re.IGNORECASE,
)
_NEGATED_VIEW_REQUEST_RE = re.compile(
    r"\b(?:do\s+not|don't|dont|never|no\s+need\s+to|"
    r"not\s+want(?:\s+you)?\s+to|without|avoid|stop)\b.{0,45}?"
    r"\b(?:load(?:ed|ing)?|reload(?:ed|ing)?|display(?:ed|ing)?|"
    r"show(?:n|ed|ing)?|open(?:ed|ing)?|pull\s+up|switch(?:ed|ing)?|"
    r"change(?:d|ing)?|put)\b",
    re.IGNORECASE,
)
_DIAGNOSTIC_VIEW_REQUEST_RE = re.compile(
    r"\b(?:why|how)\b"
    r"(?=[^;.!?]{0,100}\b(?:did(?:n't|\s+not)|does(?:n't|\s+not)|failed|"
    r"fail(?:ed|ure)?|not\s+load|wasn't|was\s+not)\b)"
    r"[^;.!?]{0,140}",
    re.IGNORECASE,
)
_AUTO_VIEW_REQUEST_RE = re.compile(
    r"(?:"
    r"\bwhat\s+should\s+i\s+(?:trade|buy|sell)\b"
    r"|\btoday(?:'s|\s+is)?\s+(?:ai\s+)?pick\b"
    r"|\b(?:best|top)\s+(?:trade|pick|one)\b"
    r"|\bshould\s+i\s+(?:trade|buy|sell)\s+[A-Za-z][A-Za-z0-9.\-]{0,14}\b"
    r"|\bis\s+[A-Za-z][A-Za-z0-9.\-]{0,14}\s+(?:a\s+)?(?:good\s+)?trade\b"
    r"|\bwhat\s+about\s+(?-i:[A-Z][A-Z0-9.\-]{0,14})\b"
    r"|\banaly[sz]e\s+(?-i:[A-Z][A-Z0-9.\-]{0,14})\b"
    r"|\bdoes\s+(?-i:[A-Z][A-Z0-9.\-]{0,14})\s+(?:actually\s+)?make\s+money\b"
    r"|\b(?:give|recommend)\s+me\s+(?:a|one)\s+trade\b"
    r")",
    re.IGNORECASE,
)
_PLURAL_TRADE_LIST_REQUEST_RE = re.compile(
    r"(?:"
    r"\b(?:show|give|list|rank|find)\s+(?:me\s+)?(?:only\s+)?(?:the\s+)?"
    r"(?:top\s+\d+(?:\s+(?:seasonal\s+)?(?:trades|setups|ideas|picks|ones|"
    r"trade\s+(?:setups|ideas|picks)))?"
    r"|(?:top|best|strongest|high(?:est)?[-\s]+win[-\s]+rate)"
    r"\s+(?:seasonal\s+)?(?:trades|setups|ideas|picks|ones|"
    r"trade\s+(?:setups|ideas|picks)))\b"
    r"|\b(?:what|which)\s+are\b.{0,35}\b"
    r"(?:best|top|strongest|high(?:est)?[-\s]+win[-\s]+rate)\b.{0,20}\b"
    r"(?:trades|setups|ideas|picks|ones|trade\s+(?:setups|ideas|picks))\b"
    r"|\b(?:best|top(?:\s+\d+)?|strongest|high(?:est)?[-\s]+win[-\s]+rate)"
    r"\s+(?:seasonal\s+)?(?:trades|setups|ideas|picks|ones|"
    r"trade\s+(?:setups|ideas|picks))\b"
    r"|\bonly\s+the\s+best\s+ones\b"
    r")",
    re.IGNORECASE,
)
_LIVE_TIME_CRITERION_RE = re.compile(
    r"\b(?:today|today's|todays|current|currently|live|right\s+now)\b",
    re.IGNORECASE,
)
_LIVE_MARKET_CRITERION_RE = re.compile(
    r"\b(?:intraday\s+)?volume\b"
    r"|\b(?:broad\s+)?market(?:'s)?\s+(?:trend|direction|regime|momentum)\b"
    r"|\b(?:trend|direction|regime|momentum)\s+(?:and|of|for|in)\s+(?:the\s+)?market\b",
    re.IGNORECASE,
)
_LIVE_DECISION_RE = re.compile(
    r"\b(?:best|highest|which|what|tell\s+me|should\s+i|"
    r"long\s+or\s+short|buy|sell|trade|stock|pick)\b",
    re.IGNORECASE,
)
_NO_ACTION_EXPLANATION_RE = re.compile(
    r"\b(?:"
    r"can(?:not|'t|’t)|could(?:not|n't|n’t)|unable|won't|will\s+not|"
    r"not\s+found|isn't\s+available|is\s+not\s+available|unavailable|"
    r"out[-\s]+of[-\s]+scope|outside\s+(?:my|the|tradeWave's)\s+scope|"
    r"private(?:ly)?|not\s+publicly\s+traded|no\s+publicly\s+traded|"
    r"does(?:n't|\s+not)\s+have\b.{0,35}\b(?:ticker|symbol)|"
    r"(?:haven't|have\s+not|didn't|did\s+not)\s+(?:load|change)|"
    r"(?:chart|view|viewer)\s+(?:wasn't|was\s+not|hasn't\s+been|has\s+not\s+been)\s+"
    r"(?:loaded|changed|updated)"
    r")\b",
    re.IGNORECASE,
)
_NON_ACTIONABLE_RESULT_TEXT_RE = re.compile(
    r"\b(?:not[-_\s]+found|out[-_\s]+of[-_\s]+scope|non[-_\s]+actionable|"
    r"not[-_\s]+publicly[-_\s]+traded|private[-_\s]+company|"
    r"unsupported[-_\s]+symbol|no[-_\s]+such[-_\s]+symbol|"
    r"symbol\b.{0,40}\b(?:unavailable|unsupported))\b",
    re.IGNORECASE,
)

_UNSUPPORTED_LIVE_DATA_RESPONSE = (
    "I can't verify intraday volume or the broad market's live trend from TradeWave's "
    "seasonal data, so I won't rank or load a trade on that basis. A seasonal-pattern "
    "scan is the supported alternative."
)


def _contains_internal_tool_markup(text):
    return bool(_INTERNAL_TOOL_MARKUP_RE.search(text or ""))


def _contains_view_promise(text):
    plain = re.sub(r"<[^>]*>", " ", text or "")
    return bool(_VIEW_PROMISE_RE.search(plain))


def _view_completion_violation(text, actions, current_view=None):
    """Return True when prose claims a view action completed without proof.

    A queued action is deliberately *not* proof: only the browser can confirm
    that the requested state and its chart data loaded. The one no-action case
    we allow is a literal "SYMBOL is already loaded" statement that agrees
    with the viewer context supplied on this request.
    """
    plain = re.sub(r"<[^>]*>", " ", text or "")
    # A truthful failure such as "I haven't changed the chart" contains the
    # same status verbs as a completion claim. Remove only explicit negated
    # status clauses before evaluating positive completion language.
    plain = _NEGATED_VIEW_COMPLETION_RE.sub(" ", plain)
    if not _VIEW_COMPLETION_RE.search(plain):
        return False
    if actions:
        return True
    current_symbol = str((current_view or {}).get("symbol") or "").upper()
    current_ready = (current_view or {}).get("view_ready") is True
    matches = list(_ALREADY_LOADED_SYMBOL_RE.finditer(plain))
    if matches and current_symbol and current_ready:
        # Every completion claim must be the narrow, viewer-confirmed form.
        without_allowed = _ALREADY_LOADED_SYMBOL_RE.sub("", plain)
        return (
            any(m.group(1).upper() != current_symbol for m in matches)
            or bool(_VIEW_COMPLETION_RE.search(without_allowed))
        )
    return True


def response_violates_view_contract(text, actions=None, current_view=None):
    """Public guard for callers that run Tara without the native tool loop."""
    return (
        _contains_internal_tool_markup(text)
        or _contains_view_promise(text)
        or _view_completion_violation(text, actions or [], current_view)
    )


def _unsupported_live_data_request(text):
    """Return True for live criteria Tara's seasonal tools cannot verify.

    These asks are not ordinary "best seasonal setup" requests. Requiring an
    update_view action would encourage the model to substitute a Sharpe-ranked
    seasonal result for the requested intraday-volume or broad-market regime
    evidence.
    """
    return bool(
        isinstance(text, str)
        and _LIVE_TIME_CRITERION_RE.search(text)
        and _LIVE_MARKET_CRITERION_RE.search(text)
        and _LIVE_DECISION_RE.search(text)
    )


def _overlaps(match, spans):
    return any(match.start() < span.end() and span.start() < match.end() for span in spans)


def _latest_user_view_intent(messages):
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            if _unsupported_live_data_request(content):
                return "unsupported_live"

            negated = list(_NEGATED_VIEW_REQUEST_RE.finditer(content))
            diagnostic = list(_DIAGNOSTIC_VIEW_REQUEST_RE.finditer(content))
            lists = list(_PLURAL_TRADE_LIST_REQUEST_RE.finditer(content))
            negative_spans = negated + diagnostic
            events = [
                (match.start(), match.end(), "forbid")
                for match in negative_spans
            ]
            events.extend(
                (match.start(), match.end(), "list")
                for match in lists
            )

            # Positive directives inside "don't load ..." or inside a plural
            # list ask are lexical matches, not actuation requests. A later,
            # separate positive directive remains eligible, so "Don't load
            # TSLA; load AAPL instead" resolves to the latest directive.
            for matcher, intent in (
                (_DIRECT_VIEW_REQUEST_RE, "chart"),
                (_AUTO_VIEW_REQUEST_RE, "chart"),
                (_VIEW_KNOB_REQUEST_RE, "view"),
            ):
                for match in matcher.finditer(content):
                    if _overlaps(match, negative_spans) or _overlaps(match, lists):
                        continue
                    events.append((match.start(), match.end(), intent))

            if events:
                latest = max(events, key=lambda item: (item[0], item[1]))
                return None if latest[2] == "list" else latest[2]
        return None
    return None


def classify_view_intent(text):
    """Classify one user turn for callers that cannot run the tool gateway."""
    if not isinstance(text, str):
        return None
    return _latest_user_view_intent([{"role": "user", "content": text}])


def unsupported_live_data_response():
    """Return the deterministic capability boundary used with or without tools."""
    return _UNSUPPORTED_LIVE_DATA_RESPONSE


def _actions_satisfy_view_intent(actions, intent):
    view_specs = [
        action.get("spec", {})
        for action in actions or []
        if action.get("type") == "set_view" and isinstance(action.get("spec"), dict)
    ]
    if intent == "chart":
        return any(spec.get("symbol") for spec in view_specs)
    if intent == "view":
        return bool(view_specs)
    if intent == "forbid":
        return not view_specs
    if intent == "unsupported_live":
        return not view_specs
    return True


def _read_result_is_explicitly_non_actionable(out):
    """Accept only an explicit read failure/capability boundary, never an empty guess."""
    if not isinstance(out, dict):
        return False
    if out.get("error"):
        return True
    if out.get("non_actionable") is True or out.get("chartable") is False:
        return True
    if out.get("ok") is False:
        return True
    for key in ("code", "status", "message", "note", "reason", "out_of_scope"):
        value = out.get(key)
        if value is not None and _NON_ACTIONABLE_RESULT_TEXT_RE.search(str(value)):
            return True
    return False


def _user_mentions_symbol(text, symbol):
    symbol = str(symbol or "").strip()
    if not symbol or not isinstance(text, str):
        return False
    return bool(re.search(
        r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(symbol),
        text,
        re.IGNORECASE,
    ))


def _non_actionable_read_allows_no_view_action(
        candidate, view_intent, actions, latest_user_text, non_actionable_symbols):
    """Allow a truthful no-action answer only after a matching failed symbol read.

    This is deliberately narrower than "a tool errored": the failed read must be
    for a symbol named in this user turn, no view action may be queued, and the
    prose must explicitly explain inability/non-availability without promising a
    later load.
    """
    if view_intent != "chart" or actions or not isinstance(candidate, str):
        return False
    if _contains_internal_tool_markup(candidate) or _contains_view_promise(candidate):
        return False
    plain = re.sub(r"<[^>]*>", " ", candidate)
    if not _NO_ACTION_EXPLANATION_RE.search(plain):
        return False
    return any(
        _user_mentions_symbol(latest_user_text, symbol)
        for symbol in non_actionable_symbols
    )


def _protocol_correction(reason, action_queued=False):
    if action_queued:
        return (
            "A valid view action is already queued. Do NOT call any more view tools. Rewrite only "
            "the answer/evidence without tool markup and do not say loaded, reloaded, already "
            "loaded, done, switched, or updated. The browser owns completion status."
        )
    if reason == "printed_tool_markup":
        return (
            "Your previous response printed tool-call markup instead of using the native tools. "
            "Use the native tool now. Never print <function_calls>, <invoke>, or <parameter> tags."
        )
    if reason == "missing_view_action":
        return (
            "The user directly requested a chart/view change, but your response did not call "
            "update_view. For a symbol/setup, first use a read tool in this turn, then copy its "
            "exact symbol + market + entry_date + hold_days/days_out into update_view. Do not claim "
            "completion; the browser confirms it."
        )
    if reason == "unconfirmed_view_promise":
        return (
            "Do not promise a future chart/view change. Either use the native read tool plus "
            "update_view now, or, if the requested symbol read explicitly failed or was out of "
            "scope, explain truthfully why no chart action was sent."
        )
    if reason == "invalid_tool_envelope":
        return (
            "Your previous tool response was malformed. Send valid native tool_use blocks with "
            "unique non-empty ids, or answer without tool syntax. Never simulate a tool call in text."
        )
    return (
        "Your previous response claimed the chart was loaded before the browser confirmed it. "
        "Do not say loaded, reloaded, already loaded, or done. Use update_view when an action is "
        "needed, state only the evidence/result, and let the client add the completion status."
    )


def _index_cards(out, cards, card_list):
    """Stash every {symbol, headline, stats} card from a briefified read-tool result so the
    load-announcement guard can name the loaded pick deterministically (the model is unreliable).
    `cards` is symbol->latest card; `card_list` keeps EVERY card so the guard can match the loaded
    setup by entry_date (a same-symbol earlier card must not leak its win rate)."""
    if not isinstance(out, dict):
        return
    def stash(c):
        if isinstance(c, dict) and c.get("symbol"):
            cards[str(c["symbol"]).upper()] = c
            card_list.append(c)
    if out.get("symbol"):
        stash(out)
    if isinstance(out.get("card"), dict):
        stash(out["card"])
    for k in _LIST_KEYS:
        if isinstance(out.get(k), list):
            for it in out[k]:
                stash(it)


# The card HEADLINE ('AAPL long - ... Won 4/10 years, avg +2.0%, ...') is derived from the per-year
# rows and is the AUTHORITATIVE record - correct even when stats.historical_win_rate is the known-
# buggy value (it has come back as the LOSS fraction). Parse win count + avg from the headline.
_HL_WIN_RE   = re.compile(r'won\s*(\d+)\s*/\s*(\d+)', re.I)
_HL_AVG_RE   = re.compile(r'avg\s*([+-]?\d+(?:\.\d+)?)\s*%', re.I)
_HL_SHARPE_RE = re.compile(r'\b(?:sharpe(?:\s+ratio)?|sr)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)', re.I)
_RPL_WIN_RE  = re.compile(r'(\d+)\s*(?:of|/)\s*(?:the\s*last\s*)?(\d+)\s*year', re.I)  # context-anchored (a conflict)
_RPL_FRAC_RE = re.compile(r'(\d+)\s*(?:of(?:\s*the\s*last)?|/)\s*(\d+)', re.I)         # lenient (counts as present)
_RPL_PCT_RE  = re.compile(r'(\d{1,3})\s*%\s*win', re.I)
_RPL_AVG_RE = re.compile(
    r'\b(?:avg|average)(?:\s+(?:return|gain|profit))?\s*(?:of|:|is|=)?\s*'
    r'([+-]?\d+(?:\.\d+)?)\s*%',
    re.I,
)
_RPL_SHARPE_RE = re.compile(
    r'\b(?:sharpe(?:\s+ratio)?|sr)\s*(?:of|:|is|=)?\s*([+-]?\d+(?:\.\d+)?)',
    re.I,
)


def _card_headline_stats(card):
    """Authoritative (wins, years, avg_or_None) for a card. Prefers the HEADLINE win token
    ('Won 4/10 years') - exact and chart-consistent - and falls back to the stats fields
    (historical_win_rate x years) for a card whose headline carries no record (e.g. a weak
    'no high-conviction edge' card). Returns None only when neither is available."""
    if not isinstance(card, dict):
        return None
    h = card.get("headline")
    if isinstance(h, str):
        mw = _HL_WIN_RE.search(h)
        if mw:
            ma = _HL_AVG_RE.search(h)
            return int(mw.group(1)), int(mw.group(2)), (float(ma.group(1)) if ma else None)
    st = card.get("stats") if isinstance(card.get("stats"), dict) else card
    wr = st.get("historical_win_rate")
    yrs = st.get("years") or card.get("years")
    try:
        n = int(float(yrs))
    except (TypeError, ValueError):
        return None
    if n > 0 and isinstance(wr, (int, float)) and not isinstance(wr, bool):
        avg = st.get("avg_return_pct")
        return round(wr * n), n, (avg if isinstance(avg, (int, float)) and not isinstance(avg, bool) else None)
    return None


def _numeric_stat(value, percent=False):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if percent and text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _card_sharpe(card):
    if not isinstance(card, dict):
        return None
    headline = card.get("headline")
    if isinstance(headline, str):
        match = _HL_SHARPE_RE.search(headline)
        if match:
            return float(match.group(1))
    stats = card.get("stats") if isinstance(card.get("stats"), dict) else card
    for key in ("sharpe_ratio", "Sharpe Ratio", "sharpe", "sr"):
        value = _numeric_stat(stats.get(key))
        if value is not None:
            return value
    return None


def _card_entry_date(c):
    s = c.get("setup") if isinstance(c, dict) and isinstance(c.get("setup"), dict) else c
    return s.get("entry_date") if isinstance(s, dict) else None


def _card_days_out(c):
    s = c.get("setup") if isinstance(c, dict) and isinstance(c.get("setup"), dict) else c
    if not isinstance(s, dict):
        return None
    value = s.get("hold_days") if s.get("hold_days") is not None else s.get("days_out")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolved_action_setup(spec, current_view=None):
    """Resolve a symbol action to one complete setup identity.

    Full actions carry their own identity. Partial actions are valid only when
    every omitted identity field comes from the same confirmed browser view.
    """
    if not isinstance(spec, dict) or not spec.get("symbol"):
        return None
    identity_fields = ("symbol", "market", "entry_date", "days_out")
    if all(field in spec for field in identity_fields):
        candidate = {
            "symbol": str(spec.get("symbol") or "").upper(),
            "market": str(spec.get("market") or ""),
            "entry_date": spec.get("entry_date"),
            "days_out": spec.get("days_out"),
        }
        if (
            _VS_SYMBOL_RE.fullmatch(candidate["symbol"])
            and candidate["market"] in _VS_MARKETS
            and isinstance(candidate["entry_date"], str)
            and _VS_DATE_RE.fullmatch(candidate["entry_date"])
            and isinstance(candidate["days_out"], int)
            and not isinstance(candidate["days_out"], bool)
            and 1 <= candidate["days_out"] <= 366
        ):
            try:
                datetime.datetime.strptime(candidate["entry_date"], "%Y-%m-%d")
                return candidate
            except ValueError:
                return None
        return None

    confirmed = _confirmed_view_setup(current_view)
    if confirmed is None or str(spec.get("symbol") or "").upper() != confirmed["symbol"]:
        return None
    for field in ("market", "entry_date", "days_out"):
        if field in spec and spec.get(field) != confirmed[field]:
            return None
    return confirmed


def _current_view_evidence_card(current_view, expected_setup):
    """Build an exact evidence card from chart rows for a confirmed current view."""
    if _confirmed_view_setup(current_view) != expected_setup:
        return None
    supplied_stats = (
        current_view.get("stats")
        if isinstance((current_view or {}).get("stats"), dict)
        else {}
    )
    supplied_wins = _numeric_stat(supplied_stats.get("Num Winners"))
    supplied_losses = _numeric_stat(supplied_stats.get("Num Losers"))
    avg_return = _numeric_stat(
        supplied_stats.get("Avg Profit - All"),
        percent=True,
    )
    sharpe = _numeric_stat(supplied_stats.get("Sharpe Ratio"))
    wins = None
    years = None
    if (
        supplied_wins is not None
        and supplied_losses is not None
        and supplied_wins >= 0
        and supplied_losses >= 0
        and supplied_wins.is_integer()
        and supplied_losses.is_integer()
        and supplied_wins + supplied_losses > 0
    ):
        wins = int(supplied_wins)
        years = int(supplied_wins + supplied_losses)

    yearly = (current_view or {}).get("yearly_results")
    if wins is None:
        if not isinstance(yearly, list) or not yearly:
            return None
        returns = []
        for row in yearly:
            value = row.get("return_pct") if isinstance(row, dict) else None
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            returns.append(float(value))
        if not returns:
            return None
        if str((current_view or {}).get("direction") or "").lower() == "short":
            returns = [-value for value in returns]
        wins = sum(value >= 0 for value in returns)
        years = len(returns)
        avg_return = sum(returns) / len(returns)

    evidence_stats = {
        "historical_win_rate": wins / years,
        "years": years,
    }
    if avg_return is not None:
        evidence_stats["avg_return_pct"] = avg_return
    if sharpe is not None:
        evidence_stats["sharpe_ratio"] = sharpe
    return {
        "symbol": expected_setup["symbol"],
        "market": expected_setup["market"],
        "direction": str((current_view or {}).get("direction") or ""),
        "setup": {
            "entry_date": expected_setup["entry_date"],
            "hold_days": expected_setup["days_out"],
        },
        "stats": evidence_stats,
    }


def _announce_line(sym, card):
    """Compose a status-neutral line for a requested setup.

    The browser appends "Loaded on the chart" only after ChartData4 succeeds.
    This server-side line therefore contains evidence but no completion claim.
    """
    hs = _card_headline_stats(card)
    st = card.get("stats") if isinstance(card.get("stats"), dict) else card
    direction = (card.get("direction") or "").strip()
    parts = []
    n = None
    if hs:
        wins, n, avg = hs
        parts.append("won %d of the last %d years" % (wins, n))
        if avg is not None:
            parts.append("avg %+.1f%%" % avg)
    else:
        yrs = st.get("years") or card.get("years")
        try:
            n = int(float(yrs)) if yrs is not None else None
        except (TypeError, ValueError):
            n = None
        wr = st.get("historical_win_rate")
        avg = st.get("avg_return_pct")
        if isinstance(wr, (int, float)) and not isinstance(wr, bool):
            parts.append(("won %d of the last %d years" % (round(wr * n), n)) if n
                         else ("%d%% historical win rate" % round(wr * 100)))
        if isinstance(avg, (int, float)) and not isinstance(avg, bool):
            parts.append("avg %+.1f%%" % avg)
    sharpe = _card_sharpe(card)
    if sharpe is not None:
        parts.append("Sharpe %.2f" % sharpe)
    stat = ", ".join(parts) if parts else (card.get("headline") or "the pattern")
    based = (" based on the last %d years" % n) if n else ""
    dirtxt = (" " + direction) if direction else ""
    return "<b>%s</b>%s%s: %s." % (sym, dirtxt, based, stat)


def _numeric_claim_matches(raw_claim, expected):
    try:
        claim = float(raw_claim)
        decimals = len(str(raw_claim).split(".", 1)[1]) if "." in str(raw_claim) else 0
        return round(float(expected), decimals) == round(claim, decimals)
    except (TypeError, ValueError):
        return False


def _stat_conflicts(text, wins, yrs, avg=None, sharpe=None):
    """Detect any narrated setup statistic that conflicts with exact evidence.

    A correct win count must not mask a fabricated average or Sharpe ratio.
    Metrics the reply omits are fine; metrics it asserts must match the exact
    setup card at the precision the reply chose.
    """
    text = text or ""
    correct_win = any(
        (int(match.group(1)), int(match.group(2))) == (wins, yrs)
        for match in _RPL_FRAC_RE.finditer(text)
    ) or any(
        yrs and round(int(match.group(1)) / 100.0 * yrs) == wins
        for match in _RPL_PCT_RE.finditer(text)
    )
    win_conflict = False
    if not correct_win:
        win_conflict = any(
            (
                int(match.group(2)) == yrs
                and int(match.group(1)) != wins
            )
            or int(match.group(1)) == int(match.group(2))
            for match in _RPL_WIN_RE.finditer(text)
        ) or any(
            yrs and round(int(match.group(1)) / 100.0 * yrs) != wins
            for match in _RPL_PCT_RE.finditer(text)
        )

    avg_claims = [match.group(1) for match in _RPL_AVG_RE.finditer(text)]
    avg_conflict = bool(avg_claims) and (
        avg is None
        or not any(_numeric_claim_matches(claim, avg) for claim in avg_claims)
    )
    sharpe_claims = [match.group(1) for match in _RPL_SHARPE_RE.finditer(text)]
    sharpe_conflict = bool(sharpe_claims) and (
        sharpe is None
        or not any(_numeric_claim_matches(claim, sharpe) for claim in sharpe_claims)
    )
    return win_conflict or avg_conflict or sharpe_conflict


def _ensure_load_named(text, actions, cards, card_list, current_view=None):
    """Guarantee the loaded pick is announced with ITS OWN correct record. Fixes two failures:
    (1) a bare confirmation with no symbol; (2) the right symbol but a STALE/FABRICATED win rate
    carried from an earlier setup (loads the September window but says 'won 10 of 10' from the June
    setup). The card is matched to the complete loaded setup identity, and the HEADLINE is
    authoritative."""
    text = text or ""
    loaded = [a.get("spec", {}) for a in actions
              if a.get("type") == "set_view" and isinstance(a.get("spec"), dict) and a["spec"].get("symbol")]
    if not loaded:
        return text
    spec = loaded[-1]
    sym = str(spec.get("symbol")).upper()
    expected = _resolved_action_setup(spec, current_view)
    # Match evidence to the complete requested setup. Entry date alone is not
    # unique: the same symbol can have multiple durations or market mappings.
    # In particular, never use `cards[sym]`: it may be a different setup read
    # earlier in this turn.
    card = None
    if expected is not None:
        for c in card_list:
            if (
                str(c.get("symbol", "")).upper() == expected["symbol"]
                and _card_market_id(c) == expected["market"]
                and _card_entry_date(c) == expected["entry_date"]
                and _card_days_out(c) == expected["days_out"]
            ):
                card = c
                break
    if card is None and expected is not None:
        card = _current_view_evidence_card(current_view, expected)
    if not card:
        # The action may still be valid (for example a confirmed same-view
        # refresh), but without exact evidence its model-written statistics are
        # not safe to repeat.
        return "<b>%s</b> chart request." % sym
    hs = _card_headline_stats(card)
    if hs and _stat_conflicts(
        text,
        hs[0],
        hs[1],
        avg=hs[2],
        sharpe=_card_sharpe(card),
    ):
        # the reply states a win rate that is NOT this loaded setup's record -> replace with truth
        fixed = _announce_line(sym, card)
        dm = re.search(r'<i>.*?</i>', text, re.S)          # preserve a disclaimer if the model added one
        return fixed + ("<br><br>" + dm.group(0) if dm else "")
    if sym in text.upper():
        return text
    line = _announce_line(sym, card)
    if text.strip():
        return line + "<br><br>" + text
    return line


# --- screening interception: keep Tara's "which <group> stocks" answer == the on-screen table ---
# The wave-viewer opportunity table and the gateway /scan are DIFFERENT data paths (the table uses
# its own OppList4 lookback/expand params; /scan uses a fixed entry window + its own dedup), so a
# scan can name different tickers than the rows the user is actually looking at - and broadening the
# scan window does NOT fix it (verified: now/2w/month return the same rows). So when the model scans
# the SAME market the table is already on, we answer from the passed table rows instead (a guaranteed
# match); when it scans a DIFFERENT market, we auto-switch the table to that market so the screen
# follows the names Tara gives. This keys off the model's own find_best_opportunities call, so no
# fragile intent-detection is needed.
def _single_market_id(markets_param):
    """Resolve a find_best_opportunities `markets` arg to ONE market id ('0'..'16'), or None when it
    is empty / multi-market / not a bare id. Only a single, unambiguous market can be matched against
    the opp table or auto-switched (the prompt tells the model to pass the id for a group screen)."""
    if markets_param in (None, ""):
        return None
    parts = [p.strip() for p in str(markets_param).split(",") if p.strip()]
    if len(parts) != 1:
        return None
    return parts[0] if parts[0] in _VS_MARKETS else None


# Filters a find_best_opportunities call can carry that the opp-table rows CAN satisfy themselves
# (so we can still answer from the on-screen rows). Anything else - a win-rate / winning-years floor
# (the rows carry no win rate) or a years / pe_cycle change (a different lookback => different data) -
# means the rows can't answer it, so we fall back to the real gateway scan.
_TABLE_BLOCKING_FILTERS = {"min_win_rate", "min_winning_years", "years", "pe_cycle"}


def _filter_table_rows(rows, inp):
    """Apply the row-satisfiable filters of a find_best_opportunities call (direction / min_sharpe /
    min_avg_return / min_days / max_days, then limit) to the opp-table rows. Order is preserved (the
    table is already sorted best-first by Sharpe)."""
    direction = (inp.get("direction") or "").strip().lower()

    def keep(r):
        if not isinstance(r, dict):
            return False
        if direction in ("long", "short"):
            d = "short" if str(r.get("direction", "")).upper() in ("S", "SHORT") else "long"
            if d != direction:
                return False
        sr, av, dy = r.get("sharpe_ratio"), r.get("avg_profit"), r.get("days_out")
        if inp.get("min_sharpe") is not None and (sr is None or sr < inp["min_sharpe"]):
            return False
        if inp.get("min_avg_return") is not None and (av is None or av < inp["min_avg_return"]):
            return False
        if inp.get("min_days") is not None and (dy is None or dy < inp["min_days"]):
            return False
        if inp.get("max_days") is not None and (dy is None or dy > inp["max_days"]):
            return False
        return True

    out = [r for r in rows if keep(r)]
    lim = inp.get("limit")
    if isinstance(lim, int) and not isinstance(lim, bool) and lim > 0:
        out = out[:lim]
    return out


def _rows_to_scan_cards(rows, market_id):
    """Render the passed opportunity-table rows (date/symbol/days_out/direction/avg_profit/
    sharpe_ratio - see Chatbot.js buildOppTableContext) as a scan-style result so the model narrates
    the EXACT on-screen rows. Order is preserved (the table is already sorted best-first by Sharpe)."""
    cards = []
    for r in rows[:15]:
        if not isinstance(r, dict):
            continue
        d = str(r.get("direction", "")).upper()
        direction = "short" if d in ("S", "SHORT") else "long"
        stats = {}
        if r.get("avg_profit") is not None:
            stats["avg_return_pct"] = r["avg_profit"]
        if r.get("sharpe_ratio") is not None:
            stats["sharpe_ratio"] = r["sharpe_ratio"]
        setup = {}
        if r.get("date"):
            setup["entry_date"] = r["date"]
        if r.get("days_out") is not None:
            setup["hold_days"] = r["days_out"]
        cards.append({"symbol": r.get("symbol"), "market": {"id": str(market_id)},
                      "direction": direction,
                      "stats": stats, "setup": setup})
    return {"market": market_id, "source": "opportunity_table",
            "note": ("These ARE the rows currently shown in the user's opportunity table for this "
                     "group, sorted best-first by Sharpe. Name the top few from here; do NOT scan again."),
            "cards": cards}


# The gateway /scan and the wave-viewer opp table (OppList4) are DIFFERENT data paths that pick
# DIFFERENT setups per symbol (verified live: scan top = FAST/TXN/CDNS..., the real NASDAQ table top
# = AAPL/AMZN/CHTR... - AAPL is #1 in the table but absent from the scan at any years/window). Tara
# must SCREEN from OppList4, the same path the table uses, or her list won't match the screen. She
# calls it loopback as the logged-in user (their LTK carries the level + geo claims OppList4 needs).
def _opplist4_to_rows(ol):
    """Map raw OppList4 rows [date, symbol, days, dir, sharpe, avg, ...] to the dict shape
    _filter_table_rows / _rows_to_scan_cards use - mirroring Chatbot.js buildOppTableContext
    (days_out = raw + 1, avg rounded to 0.1)."""
    out = []
    for row in ol or []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            days = int(float(row[2])) + 1
        except (TypeError, ValueError):
            days = None
        try:
            sr = round(float(row[4]), 2)
        except (TypeError, ValueError):
            sr = None
        try:
            av = round(float(row[5]) * 10) / 10
        except (TypeError, ValueError):
            av = None
        out.append({"date": row[0], "symbol": row[1], "days_out": days,
                    "direction": row[3], "avg_profit": av, "sharpe_ratio": sr})
    return out


def _opplist4_rows(market_id, token, years):
    """Fetch a market's opportunity-TABLE rows (OppList4, the data path the wave-viewer table uses)
    as the logged-in user, for a cross-market 'which <group> stocks' screen. Returns the row dicts or
    None on any failure (caller falls back to the gateway scan). Uses the per-env appserver URL +
    the user's own token; never raises into the chat loop."""
    base = (config.appserver_url or "").rstrip("/")
    if not base or not token:
        return None
    try:
        y = int(years)
    except (TypeError, ValueError):
        y = 0
    if y <= 0:
        y = 12                                    # React opp-table default lookback
    today = datetime.datetime.now()
    url = "%s/OppList4/%s/%s/%s/%s/%s/-/0/0" % (base, market_id, today.strftime("%B"), today.day, y, y)
    try:
        r = requests.get(url, params={"token": token, "mode": "consecutive"}, timeout=(5, 20))
    except requests.RequestException as e:
        log.warning("tara OppList4 loopback market=%s failed: %s", market_id, e)
        return None
    if r.status_code != 200:
        log.warning("tara OppList4 loopback market=%s -> %s", market_id, r.status_code)
        return None
    try:
        ol = r.json().get("OppList")
    except ValueError:
        return None
    return _opplist4_to_rows(ol) if isinstance(ol, list) else None


def _symbol_max_available_years(market_id, symbol, token):
    """Return the symbol's consecutive data limit from the viewer's StockMetaData source.

    This mirrors ``SeasonalBarChart`` (end year minus start year) so a named-symbol change
    can inherit the current lookback without asking a younger ticker for unavailable years.
    It is a best-effort guard: failures leave the requested lookback unchanged and React's
    existing metadata clamp remains the final defense.
    """

    market = str(market_id or "").strip()
    ticker = str(symbol or "").strip().upper()
    base = (config.appserver_url or "").rstrip("/")
    if not base or not token or market not in _VS_MARKETS or not _VS_SYMBOL_RE.match(ticker):
        return None
    url = "%s/StockMetaData/%s/%s" % (base, quote(market), quote(ticker))
    try:
        response = requests.get(
            url,
            params={"token": token},
            timeout=(5, 15),
        )
    except requests.RequestException as exc:
        log.warning("tara StockMetaData %s/%s failed: %s", market, ticker, exc)
        return None
    if response.status_code != 200:
        log.warning(
            "tara StockMetaData %s/%s -> %s", market, ticker, response.status_code
        )
        return None
    try:
        metadata = response.json().get("StockMetaData")
    except (AttributeError, ValueError):
        return None
    if not isinstance(metadata, list) or len(metadata) < 2:
        return None
    try:
        first_year = int(str(metadata[0])[:4])
        last_year = int(str(metadata[1])[:4])
    except (TypeError, ValueError):
        return None
    available = last_year - first_year
    return min(available, 99) if available > 0 else None


def _append_market_switch(actions, target):
    """Queue a market-only set_view (switch the opp table to `target`) unless one is already queued."""
    if not any(a.get("type") == "set_view" and a.get("spec", {}).get("market") == target for a in actions):
        _queue_view_action(actions, {"market": target})


# Haiku often glues a closing call-to-action onto the last list item with just a space ("...29 days
# Want me to pull one up?") - and a bare space/newline does not render as a line break in the chat
# HTML. Guarantee the CTA lands on its own line: insert <br><br> before a recognized trailing CTA
# when it is not already break-separated. Anchored to end-of-string + a small phrase set => safe.
_TRAILING_CTA = re.compile(
    r'([^\s>])[ \t\n]+((?:Want me to|Want to|Want a|Should I|Say the word|Let me know)\b[^<>]*[.?!])\s*$',
    re.IGNORECASE,
)


def _break_before_cta(text):
    return _TRAILING_CTA.sub(r'\1<br><br>\2', text or '')


def _full_history_years(request_spec):
    if not isinstance(request_spec, dict):
        return None
    value = request_spec.get("years")
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 99):
        return None
    return value


def _apply_full_history_request(name, inp, request_spec):
    """Apply a deterministic max-history command to a provider's tool arguments.

    Models may treat 99 (the schema ceiling) as a magic "max" value or may reselect a
    symbol's best setup after the lookback changes.  The client supplied the exact real
    history limit and loaded window, so keep the provider's read on that same setup.
    """

    years = _full_history_years(request_spec)
    out = dict(inp) if isinstance(inp, dict) else {}
    if years is None:
        return out
    if name == "update_view":
        # This command changes one knob on the already-loaded setup. Do not let a
        # provider opportunistically switch the symbol/window in the same action.
        out = {"years": years}
    elif name == "analyze_symbol":
        out = {
            field: request_spec[field]
            for field in (
                "symbol", "market", "entry_date", "days_out", "direction", "pe_cycle", "years"
            )
            if field in request_spec
        }
    elif name == "get_symbol_patterns":
        # This is not the preferred tool for a loaded-window lookback change, but if a
        # provider chooses it, keep it on the verified loaded symbol and lookback.
        out = {
            field: request_spec[field]
            for field in ("symbol", "market", "pe_cycle", "years")
            if field in request_spec
        }
    return out


def _enforce_full_history_action(actions, request_spec):
    """Guarantee the viewer receives the same exact lookback used by the read tool."""

    years = _full_history_years(request_spec)
    if years is None:
        return
    found = False
    for action in actions:
        if not isinstance(action, dict) or action.get("type") != "set_view":
            continue
        spec = action.get("spec")
        if not isinstance(spec, dict):
            continue
        action["spec"] = {"years": years}
        found = True
    if not found:
        actions.append({"type": "set_view", "spec": {"years": years}})


def _viewer_year_entry_date(value, viewer_year):
    """Anchor a recurring setup's month/day to the viewer's current occurrence year."""

    if not isinstance(value, str) or not isinstance(viewer_year, int):
        return value
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%d").date()
        return parsed.replace(year=viewer_year).isoformat()
    except (TypeError, ValueError):
        return value


def _card_effective_years(card, preferred_years=None):
    """Resolve the target symbol's usable lookback from its verified card."""

    if not isinstance(card, dict):
        return preferred_years
    stats = card.get("stats") if isinstance(card.get("stats"), dict) else card
    requested = preferred_years if isinstance(preferred_years, int) else stats.get("years")
    try:
        requested = int(requested)
    except (TypeError, ValueError):
        requested = None
    headline_stats = _card_headline_stats(card)
    available = headline_stats[1] if headline_stats else None
    if requested is not None and available is not None:
        return min(requested, available)
    return requested if requested is not None else available


def _card_view_spec(card, symbol, viewer_year, preferred_years=None):
    """Build the smallest concrete viewer spec from a verified read-tool card."""

    if not isinstance(card, dict):
        return {}
    setup = card.get("setup") if isinstance(card.get("setup"), dict) else card
    candidate = {"symbol": symbol}
    if card.get("market") is not None:
        candidate["market"] = str(card["market"])
    entry_date = setup.get("entry_date") if isinstance(setup, dict) else None
    if entry_date:
        candidate["entry_date"] = _viewer_year_entry_date(entry_date, viewer_year)
    hold_days = setup.get("hold_days") if isinstance(setup, dict) else None
    if isinstance(hold_days, int) and not isinstance(hold_days, bool):
        candidate["days_out"] = hold_days
    years = _card_effective_years(card, preferred_years)
    if years is not None:
        candidate["years"] = years
    return _validate_view_spec(candidate)


def _enforce_named_symbol_action(
    actions, cards, symbol, viewer_year, preferred_years=None
):
    """Keep a named-symbol override on that symbol and the current recurrence year."""

    target = str(symbol or "").strip().upper()
    if not target or not _VS_SYMBOL_RE.match(target):
        return
    actions[:] = [
        action
        for action in actions
        if not (
            isinstance(action, dict)
            and action.get("type") == "set_view"
            and isinstance(action.get("spec"), dict)
            and action["spec"].get("symbol")
            and str(action["spec"]["symbol"]).strip().upper() != target
        )
    ]
    card = cards.get(target) if isinstance(cards, dict) else None
    effective_years = _card_effective_years(card, preferred_years)
    matching_action = None
    for action in actions:
        if not isinstance(action, dict) or action.get("type") != "set_view":
            continue
        spec = action.get("spec")
        if not isinstance(spec, dict):
            continue
        action_symbol = str(spec.get("symbol") or "").strip().upper()
        if action_symbol == target:
            matching_action = action
    if matching_action is not None:
        spec = matching_action["spec"]
        if spec.get("entry_date"):
            spec["entry_date"] = _viewer_year_entry_date(
                spec["entry_date"], viewer_year
            )
        if effective_years is not None:
            spec["years"] = effective_years
        matching_action["spec"] = _validate_view_spec(spec)
        return

    spec = _card_view_spec(card, target, viewer_year, preferred_years)
    if {"symbol", "entry_date", "days_out"}.issubset(spec):
        actions.append({"type": "set_view", "spec": spec})


def _execute_tara_tool(name, inp, user_id, actions, cards, card_list, *,
                       table_market=None, opp_table=None, user_token=None,
                       opp_table_years=None, full_history_request=None,
                       named_symbol_override=None, named_symbol_lookback=None):
    """Execute one provider-neutral Tara tool call through the established safety path."""

    inp = _apply_full_history_request(name, inp, full_history_request)
    target_symbol = str(named_symbol_override or "").strip().upper()
    effective_named_lookback = named_symbol_lookback
    action_symbol = str(inp.get("symbol") or "").strip().upper()
    if (
        target_symbol
        and action_symbol == target_symbol
        and isinstance(named_symbol_lookback, int)
        and name in {"analyze_symbol", "get_symbol_patterns", "update_view"}
    ):
        target_market = inp.get("market") or table_market
        available_years = _symbol_max_available_years(
            target_market, target_symbol, user_token
        )
        if available_years is not None:
            effective_named_lookback = min(named_symbol_lookback, available_years)
    if (
        target_symbol
        and isinstance(effective_named_lookback, int)
        and name in {"analyze_symbol", "get_symbol_patterns"}
        and action_symbol == target_symbol
    ):
        inp = dict(inp)
        inp["years"] = effective_named_lookback
    if name == "update_view":                       # client-side UI action, not a gateway call
        if (
            target_symbol
            and isinstance(effective_named_lookback, int)
            and action_symbol == target_symbol
        ):
            inp = dict(inp)
            inp["years"] = effective_named_lookback
        cleaned = _validate_view_spec(inp)
        if cleaned:
            actions.append({"type": "set_view", "spec": cleaned})
            return {"ok": True, "applied": cleaned}
        return {"ok": False, "error": "no valid view fields to apply"}

    if name == "find_best_opportunities":
        # Screen from OppList4 (the opp-table data path) so the answer == the on-screen table;
        # /scan is a different path that names different tickers (see _opplist4_rows note).
        target = _single_market_id(inp.get("markets"))
        blocking = bool(set(inp.keys()) & _TABLE_BLOCKING_FILTERS)
        screen_rows = None
        if target is not None and not blocking:
            if table_market == target and opp_table:
                screen_rows = _filter_table_rows(opp_table, inp)   # exact on-screen rows
            else:
                fetched = _opplist4_rows(target, user_token, opp_table_years)
                screen_rows = _filter_table_rows(fetched, inp) if fetched else None
                if table_market != target:        # switch the table so the screen follows the names
                    _append_market_switch(actions, target)
        if screen_rows:
            out = _rows_to_scan_cards(screen_rows, target)
        else:
            out = _briefify(run_tool(name, inp, user_id))  # multi-market / blocking / loopback-failed
            if target is not None and table_market != target:
                _append_market_switch(actions, target)
    else:
        out = _briefify(run_tool(name, inp, user_id))

    _index_cards(out, cards, card_list)
    return out


def run_chat_with_tools(messages, system, user_id, model, cache_ttl="5m",
                        opp_table=None, opp_table_market=None, user_token=None,
                        opp_table_years=None, current_view=None, turn_id=None,
                        protocol_trace=None):
    """Run the Tara chat with gateway tool-use. `messages` ends with the user turn. Returns
    (final_text, actions): the assistant TEXT plus any UI actions the model requested (Phase 2,
    e.g. [{'type':'set_view','spec':{...}}]). Read tools (scan/analyze/...) are executed as
    `user_id` against the gateway; update_view is validated server-side and queued as an action
    for the client to apply. For a 'which <group> stocks' screen, `opp_table` (the on-screen rows) +
    `opp_table_market` answer from the table when it is already on that group, else `user_token` +
    `opp_table_years` fetch that group's table (OppList4) loopback + auto-switch markets. Capped at
    _MAX_TOOL_ROUNDS."""
    convo = list(messages)
    actions = []
    cards = {}            # symbol -> latest briefified card, for the deterministic load-announcement guard
    card_list = []        # every card seen this turn, so the guard can match the loaded setup by entry_date
    table_market = str(opp_table_market) if opp_table_market not in (None, "") else None
    final_text = None
    protocol_failures = 0
    view_intent = _latest_user_view_intent(messages)
    latest_user_text = next(
        (
            message.get("content", "")
            for message in reversed(messages or [])
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ),
        "",
    )
    non_actionable_symbols = set()

    def trace(event, **fields):
        if isinstance(protocol_trace, list) and len(protocol_trace) < 24:
            protocol_trace.append({"event": event, **fields})

    if view_intent == "unsupported_live":
        trace("unsupported_live_data_intent")
        return _UNSUPPORTED_LIVE_DATA_RESPONSE, []

    for round_index in range(_MAX_TOOL_ROUNDS):
        resp = send_claude_messages(convo, model=model, system=system,
                                    cache_system=True, cache_ttl=cache_ttl,
                                    tools=TOOLS, return_raw=True)
        blocks = resp.get("content", []) or []
        blocks_are_valid = (
            isinstance(blocks, list)
            and all(isinstance(block, dict) for block in blocks)
        )
        if not isinstance(blocks, list):
            blocks = []
        native_tool_blocks = [
            block for block in blocks
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]
        if resp.get("stop_reason") != "tool_use":
            candidate = _text_of(blocks)
            reason = None
            if not blocks_are_valid or native_tool_blocks:
                reason = "invalid_tool_envelope"
            elif _contains_internal_tool_markup(candidate):
                reason = "printed_tool_markup"
            elif _contains_view_promise(candidate):
                reason = "unconfirmed_view_promise"
            elif _view_completion_violation(candidate, actions, current_view):
                reason = "unconfirmed_view_completion"
            elif (
                not _actions_satisfy_view_intent(actions, view_intent)
                and not _non_actionable_read_allows_no_view_action(
                    candidate,
                    view_intent,
                    actions,
                    latest_user_text,
                    non_actionable_symbols,
                )
            ):
                reason = "missing_view_action"
            if reason:
                protocol_failures += 1
                # Do not log the model text: it can contain the user's prompt,
                # raw tool arguments, or other customer data.
                log.warning(
                    "tara response protocol violation turn=%s round=%s reason=%s",
                    turn_id or "-",
                    round_index + 1,
                    reason,
                )
                trace(
                    "protocol_violation",
                    round=round_index + 1,
                    reason=reason,
                    stop_reason=str(resp.get("stop_reason") or ""),
                )
                convo.append({"role": "assistant", "content": blocks})
                convo.append({
                    "role": "user",
                    "content": _protocol_correction(
                        reason,
                        action_queued=bool(actions) and reason != "missing_view_action",
                    ),
                })
                continue
            final_text = candidate
            break
        tool_ids = [block.get("id") for block in native_tool_blocks]
        if (
            not blocks_are_valid
            or not native_tool_blocks
            or any(not isinstance(tool_id, str) or not tool_id for tool_id in tool_ids)
            or len(tool_ids) != len(set(tool_ids))
            or any(
                block.get("name") not in (set(_ALLOWED) | {"update_view"})
                or not isinstance(block.get("input"), dict)
                for block in native_tool_blocks
            )
        ):
            protocol_failures += 1
            log.warning(
                "tara response protocol violation turn=%s round=%s reason=invalid_tool_envelope",
                turn_id or "-",
                round_index + 1,
            )
            trace(
                "protocol_violation",
                round=round_index + 1,
                reason="invalid_tool_envelope",
                stop_reason=str(resp.get("stop_reason") or ""),
            )
            convo.append({"role": "assistant", "content": blocks})
            convo.append({
                "role": "user",
                "content": _protocol_correction(
                    "invalid_tool_envelope", action_queued=bool(actions)
                ),
            })
            continue
        # echo the assistant's tool_use turn back verbatim, then answer each tool call
        convo.append({"role": "assistant", "content": blocks})
        results = []
        for b in blocks:
            if b.get("type") != "tool_use":
                continue
            name, inp = b.get("name"), (b.get("input") or {})
            card_count_before = len(card_list)
            if name == "update_view":                       # client-side UI action, not a gateway call
                cleaned = _validate_view_spec(inp, current_view=current_view)
                if view_intent == "forbid":
                    out = {
                        "ok": False,
                        "error": (
                            "the user negated or is diagnosing a view action; do not change the view"
                        ),
                    }
                elif cleaned and _view_spec_is_grounded(
                    cleaned, card_list, current_view=current_view
                ):
                    _queue_view_action(actions, cleaned)
                    out = {
                        "ok": True,
                        "queued": cleaned,
                        "status": "pending_client_confirmation",
                        "instruction": (
                            "Do not say loaded, reloaded, already loaded, or done. "
                            "The browser will add completion text only after chart data loads."
                        ),
                    }
                else:
                    out = {
                        "ok": False,
                        "error": (
                            "invalid or ungrounded view setup; a new/different symbol setup must "
                            "exactly match symbol + market + entry_date + days_out from a successful "
                            "read tool result in this turn"
                        ),
                    }
            elif name == "find_best_opportunities":
                # Screen from OppList4 (the opp-table data path) so the answer == the on-screen table;
                # /scan is a different path that names different tickers (see _opplist4_rows note).
                target = _single_market_id(inp.get("markets"))
                blocking = bool(set(inp.keys()) & _TABLE_BLOCKING_FILTERS)
                screen_rows = None
                if target is not None and not blocking:
                    if table_market == target and opp_table:
                        screen_rows = _filter_table_rows(opp_table, inp)   # exact on-screen rows
                    else:
                        fetched = _opplist4_rows(target, user_token, opp_table_years)
                        screen_rows = _filter_table_rows(fetched, inp) if fetched else None
                        if table_market != target:        # switch the table so the screen follows the names
                            _append_market_switch(actions, target)
                if screen_rows:
                    out = _rows_to_scan_cards(screen_rows, target)
                else:
                    out = _briefify(run_tool(name, inp, user_id))      # multi-market / blocking-filter / loopback-failed
                    if target is not None and table_market != target:
                        _append_market_switch(actions, target)
                _index_cards(out, cards, card_list)
            else:
                out = _briefify(run_tool(name, inp, user_id))
                _index_cards(out, cards, card_list)
            if (
                name in {"analyze_symbol", "get_symbol_patterns"}
                and len(card_list) == card_count_before
                and _read_result_is_explicitly_non_actionable(out)
                and _user_mentions_symbol(latest_user_text, inp.get("symbol"))
            ):
                non_actionable_symbols.add(str(inp.get("symbol") or "").upper())
            trace(
                "tool_result",
                round=round_index + 1,
                tool=str(name or ""),
                ok=not (isinstance(out, dict) and bool(out.get("error"))),
                queued=bool(name == "update_view" and isinstance(out, dict) and out.get("ok")),
            )
            results.append({
                "type": "tool_result",
                "tool_use_id": b.get("id"),
                "content": _bounded_json(out),
            })
        convo.append({"role": "user", "content": results})
    if (
        not _actions_satisfy_view_intent(actions, view_intent)
        and not _non_actionable_read_allows_no_view_action(
            final_text,
            view_intent,
            actions,
            latest_user_text,
            non_actionable_symbols,
        )
    ):
        if actions:
            log.warning(
                "tara response protocol violation turn=%s reason=incomplete_view_action",
                turn_id or "-",
            )
        trace("protocol_violation", reason="incomplete_view_action")
        actions = []
        final_text = (
            "I couldn't send the complete chart action, so I haven't changed the chart. "
            "Please try that load again."
        )

    # If the model exhausted the loop after at least one valid action, preserve
    # the action but use deterministic, status-neutral prose. If there was no
    # valid action, fail closed rather than surfacing tool syntax or a false
    # success claim.
    if not final_text:
        if actions:
            loaded = [
                a.get("spec", {}) for a in actions
                if a.get("type") == "set_view" and isinstance(a.get("spec"), dict)
            ]
            latest = loaded[-1] if loaded else {}
            sym = str(latest.get("symbol") or "").upper()
            final_text = (
                "<b>%s</b> chart request." % sym
                if sym else "Requested view change."
            )
        elif protocol_failures:
            final_text = (
                "I couldn't send a valid chart action, so I haven't changed the chart. "
                "Please try that load again."
            )
        else:
            final_text = (
                "I couldn't complete that request safely, so I haven't changed the chart. "
                "Please try again."
            )
    if _view_actions_conflict(actions):
        log.warning(
            "tara response protocol violation turn=%s reason=conflicting_view_actions",
            turn_id or "-",
        )
        trace("protocol_violation", reason="conflicting_view_actions")
        actions = []
        final_text = (
            "I couldn't resolve that into one unambiguous chart setup, so I haven't changed "
            "the chart. Please try again."
        )
    # Deterministic guard: guarantee the loaded pick is NAMED (symbol + lookback + stat), since
    # Haiku-4.5 intermittently returns a bare 'Loaded on the chart' with no symbol.
    final_text = _ensure_load_named(
        final_text, actions, cards, card_list, current_view=current_view
    )
    final_text = _break_before_cta(final_text)   # closing CTA never runs onto the last list line
    if response_violates_view_contract(final_text, actions, current_view):
        log.warning(
            "tara response protocol violation turn=%s reason=unsafe_final_response",
            turn_id or "-",
        )
        trace("protocol_violation", reason="unsafe_final_response")
        if actions:
            final_text = _ensure_load_named(
                "", actions, cards, card_list, current_view=current_view
            )
            if not final_text:
                latest = actions[-1].get("spec", {})
                sym = str(latest.get("symbol") or "").upper()
                final_text = (
                    "<b>%s</b> chart request." % sym
                    if sym else "Requested view change."
                )
        else:
            final_text = (
                "I couldn't complete that chart request safely, so I haven't changed the chart. "
                "Please try again."
            )
    return final_text, actions


def run_chat_with_openai_tools(messages, system, user_id, model,
                               opp_table=None, opp_table_market=None,
                               user_token=None, opp_table_years=None,
                               full_history_request=None,
                               named_symbol_override=None,
                               named_symbol_lookback=None,
                               viewer_entry_year=None):
    """Run Tara's existing gateway tool loop through the OpenAI Responses API.

    Tool execution, result trimming, ViewSpec validation, table-screen interception, and
    deterministic narration guards are shared with the Anthropic path above.  Responses are
    stateless (``store:false`` in the adapter), so each round carries the prior output items and
    matching ``function_call_output`` items forward explicitly.
    """

    input_items = build_responses_input(messages, system=system)
    cache_key = prompt_cache_key(user_id)
    actions = []
    cards = {}
    card_list = []
    table_market = str(opp_table_market) if opp_table_market not in (None, "") else None
    final_text = None

    for _ in range(_MAX_TOOL_ROUNDS):
        response = send_openai_response(
            input_items,
            model=model,
            tools=TOOLS,
            cache_key=cache_key,
        )
        calls = function_calls(response)
        if not calls:
            final_text = response_text(response)
            break

        output_items = response.get("output", [])
        if not isinstance(output_items, list):
            raise OpenAIAPIError("OpenAI response output was not a list")
        input_items.extend(output_items)
        results = []
        for call in calls:
            call_id = call.get("call_id") or call.get("id")
            if not call_id:
                raise OpenAIAPIError("OpenAI function call omitted call_id")
            try:
                inp = decode_function_arguments(call)
                out = _execute_tara_tool(
                    call.get("name"),
                    inp,
                    user_id,
                    actions,
                    cards,
                    card_list,
                    table_market=table_market,
                    opp_table=opp_table,
                    user_token=user_token,
                    opp_table_years=opp_table_years,
                    full_history_request=full_history_request,
                    named_symbol_override=named_symbol_override,
                    named_symbol_lookback=named_symbol_lookback,
                )
            except OpenAIAPIError:
                # Feed a bounded, narration-safe error back to the model rather than executing
                # malformed arguments. Provider/API failures still propagate for Haiku fallback.
                out = {"ok": False, "error": "invalid tool arguments"}
            results.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _bounded_json(out),
                }
            )
        input_items.extend(results)

    if not final_text:
        response = send_openai_response(
            input_items,
            model=model,
            cache_key=cache_key,
        )
        final_text = response_text(response)
    if not final_text:
        raise OpenAIAPIError("OpenAI returned no assistant text")

    _enforce_full_history_action(actions, full_history_request)
    _enforce_named_symbol_action(
        actions,
        cards,
        named_symbol_override,
        viewer_entry_year,
        preferred_years=named_symbol_lookback,
    )
    final_text = _ensure_load_named(final_text, actions, cards, card_list)
    final_text = _break_before_cta(final_text)
    return final_text, actions
