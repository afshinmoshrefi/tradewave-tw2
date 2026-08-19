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
import html
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pooled_http import http as requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

from featured_patterns import (
    HUNDRED_YEAR_DISPLAY_DAYS,
    hundred_year_end_date,
    hundred_year_occurrence_start,
)

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
            "Screen the markets for seasonal RESEARCH CANDIDATES right now, ranked by "
            "Sharpe. Use this for 'anything good in <market>', 'best setups this month', "
            "and explicit stock/ETF opportunity screens. It returns historical evidence "
            "for comparison; it does not determine what a person should buy or trade."
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
            "Deep-dive ONE user-selected symbol into a PatternCard with its historical "
            "receipts plus other setups. Pin a specific setup with entry_date (+days_out) "
            "or a period preset; pe_cycle/years are the lookback knobs. Use for 'analyze GLD', "
            "'is AAPL seasonal now', 'explain this pattern over 20 years'. For recurring "
            "weakness, set direction=short and describe the result as a weak-period study, "
            "never as a sell or short recommendation."
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
            "says show me / load / pull up / open / change the years / switch to the PE cycle, "
            "asks to show/hide the MFE or MAE overlays, or asks to show the Trend Chart, "
            "Wave Stats, AI Scores, or Price Chart in the lower carousel. It can also show or hide the global "
            "guidance tooltips. "
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
                "days_out": {"type": "integer", "description": "1-367"},
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
                    "enum": ["trend_chart", "wave_stats", "ai_scores", "price_chart"],
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
    for k in ("rank", "symbol", "direction", "bias", "headline"):
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
    for k in ("entry_date", "hold_days"):
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
    # Keep a compact, direction-aware gain/loss record before dropping the
    # heavyweight receipts block. Discovery users need to see that a positive
    # average still contained losing years; hiding this would turn a research
    # screen into an overly promotional ranking.
    receipts = c.get("receipts") if isinstance(c.get("receipts"), dict) else {}
    history = {
        k: receipts[k]
        for k in ("years_tested", "wins", "losses", "best_year", "worst_year")
        if receipts.get(k) is not None
    }
    out = {k: v for k, v in c.items() if k not in _BRIEF_DROP}
    if history:
        out["history"] = history
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
_VS_BOTTOM_SLIDES = {"trend_chart", "wave_stats", "ai_scores", "price_chart"}
_VS_FIELDS = {
    "symbol", "market", "entry_date", "days_out", "years", "pe_cycle",
    "show_mfe", "show_mae", "show_tooltips", "bottom_slide",
}


def _confirmed_view_setup(current_view):
    """Return the exact setup whose primary and trend charts both succeeded."""
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
    if not 1 <= parsed_days <= 367:
        return None
    return {
        "symbol": symbol.upper(),
        "market": str(market),
        "entry_date": entry_date,
        "days_out": parsed_days,
    }


def _validate_view_spec(spec, current_view=None):
    """Validate one ViewSpec atomically; return {} when any field is invalid.

    Applying only a valid subset can produce a different chart than Tara
    described. A new setup therefore requires its full symbol, market, entry
    date, and duration. A partial symbol refresh is allowed only for an exact
    browser-confirmed view.
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
        if not (isinstance(do, int) and not isinstance(do, bool) and 1 <= do <= 367):
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
    for field in ("show_mfe", "show_mae", "show_tooltips"):
        if field in spec:
            value = spec.get(field)
            if not isinstance(value, bool):
                return {}
            out[field] = value
    if "bottom_slide" in spec:
        bottom_slide = spec.get("bottom_slide")
        if not (isinstance(bottom_slide, str) and bottom_slide in _VS_BOTTOM_SLIDES):
            return {}
        out["bottom_slide"] = bottom_slide

    has_entry = "entry_date" in out
    has_days = "days_out" in out
    if has_entry != has_days:
        # A duration-only command is an explicit viewer knob. A date without
        # duration, or a partial symbol setup, could silently combine with stale
        # browser state and is therefore rejected.
        if has_entry or "symbol" in out:
            return {}
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
    """Build a server-validated client action with a correlation id."""
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
    """Return True when one turn requests two values for the same view field."""
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
    """Bind a chart setup action to confirmed context or this turn's read result."""
    if not spec.get("symbol"):
        return set(spec).issubset({
            "market", "days_out", "years", "pe_cycle", "show_mfe", "show_mae",
            "show_tooltips", "bottom_slide",
        })
    confirmed_setup = _confirmed_view_setup(current_view)
    exact_confirmed = (
        confirmed_setup is not None
        and spec["symbol"] == confirmed_setup["symbol"]
        and ("market" not in spec or spec["market"] == confirmed_setup["market"])
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

# ---------------------------------------------------------------------------
# Investor discovery is deliberately separate from the legacy "single pick"
# path. An amount of money plus "what should I buy?" is a suitability question,
# not permission to turn the top Sharpe row into a personalized recommendation.
# The deterministic funnel is: horizon -> universe -> evidence shortlist -> the
# user's chosen symbol -> bullish/weak-period deep dive.
# ---------------------------------------------------------------------------
_BROAD_INVESTMENT_DISCOVERY_RE = re.compile(
    r"(?:"
    r"\bi\s+(?:have|got)\s+(?:about\s+)?\$?\s*[\d,.]+\b.{0,80}\b(?:invest|market|buy)\b"
    r"|\bi\s+(?:want|would\s+like|need)\s+to\s+(?:start\s+)?invest\b"
    r"|\b(?:how|where)\s+(?:do|can|should)\s+i\b.{0,70}\b"
    r"(?:invest|investment|stocks?|etfs?|securities|market)\b"
    r"|\bwhat\s+should\s+i\s+(?:buy|invest\s+in)\b"
    r"|\bwhere\s+should\s+i\s+(?:put|invest)\b.{0,40}\b(?:money|cash|savings)\b"
    r"|\bhelp\s+me\b.{0,35}\b(?:start\s+)?invest(?:ing|ment)?\b"
    r"|\bnew\s+to\s+investing\b"
    r")",
    re.IGNORECASE,
)
_GENERIC_TRADE_DISCOVERY_RE = re.compile(
    r"(?:\bwhat\s+should\s+i\s+trade\b"
    r"|\b(?:give|recommend|find)\s+me\s+(?:a|one)\s+trade\b"
    r"|\bwhat(?:'s|\s+is)\s+good\s+to\s+trade\b)",
    re.IGNORECASE,
)
_SEASONAL_DISCOVERY_RE = re.compile(
    r"\b(?:seasonal(?:ity)?\s+(?:patterns?|setups?|screens?|candidates?|opportunit(?:y|ies))|"
    r"(?:find|show|screen|rank)\b.{0,35}\bseasonal(?:ity)?|"
    r"this\s+time\s+of\s+(?:the\s+)?year|"
    r"bullish\b.{0,35}\b(?:windows?|patterns?|opportunit(?:y|ies))|"
    r"historical\s+(?:windows?|patterns?)|"
    r"days?\s*(?:/|or|and)\s*weeks?|short[-\s]+term\s+trad|"
    r"opportunit(?:y|ies)\s+(?:now|today|this\s+month))\b",
    re.IGNORECASE,
)
_LONG_TERM_HORIZON_RE = re.compile(
    r"\b(?:long[-\s]+term|retire(?:ment)?|buy\s+and\s+hold|"
    r"hold\s+for\s+years?|for\s+the\s+next\s+\d+\s+years?)\b",
    re.IGNORECASE,
)
_SEASONAL_HORIZON_REPLY_RE = re.compile(
    r"^\s*(?:seasonal|short[-\s]+term|days?|weeks?|days?\s*(?:/|or|and)\s*weeks?|"
    r"seasonal\s+(?:trade|opportunit(?:y|ies)))\s*[.!]?\s*$",
    re.IGNORECASE,
)
_LONG_TERM_HORIZON_REPLY_RE = re.compile(
    r"^\s*(?:long|long[-\s]+term|years?|retirement|buy\s+and\s+hold)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_ETF_UNIVERSE_RE = re.compile(r"\b(?:etfs?|exchange[-\s]+traded\s+funds?)\b", re.IGNORECASE)
_STOCK_UNIVERSE_RE = re.compile(
    r"\b(?:stocks?|equities|companies|s\s*&\s*p(?:\s+500)?|sp500)\b",
    re.IGNORECASE,
)
_WEAK_PERIOD_RE = re.compile(
    r"\b(?:weak(?:est|ness)?|bearish|downside\s+window|avoid\s+period|"
    r"bad\s+time|losing\s+period|exclude(?:d|\s+date)?\s+range)\b",
    re.IGNORECASE,
)
_EXCLUSION_STUDY_RE = re.compile(
    r"\b(?:exclude(?:d|\s+date)?\s+range|exclude\s+(?:this|the|current)\s+"
    r"(?:current\s+)?(?:date\s+)?range|date\s+range\s+exclusion)\b",
    re.IGNORECASE,
)
_BUY_HOLD_STUDY_RE = re.compile(
    r"(?:\b(?:how|what|show|explain|teach|walk)\b.{0,90}\b"
    r"buy\s*(?:&|and)\s*hold\b"
    r"|\bbuy\s*(?:&|and)\s*hold\b.{0,90}\b"
    r"(?:analysis|study|workflow|baseline|benchmark|compar|long[-\s]+term))",
    re.IGNORECASE,
)
_CAPABILITY_GUIDE_RE = re.compile(
    r"\b(?:what\s+(?:can|should)\s+i\s+(?:ask|research|do)|"
    r"what\s+can\s+(?:tara|you)\s+(?:do|help\s+with)|"
    r"how\s+can\s+(?:tara|you)\s+help|"
    r"show\s+me\s+what\s+i\s+can\s+ask)\b",
    re.IGNORECASE,
)
_PERSONAL_TRADE_DECISION_RE = re.compile(
    r"(?:"
    r"^\s*(?:so[,\s]+)?(?:do|should|could|would)\s+i\s+"
    r"(?:(?:go|stay)\s+)?(?:long|short|buy|sell|hold|trade|invest|"
    r"do\s+(?:a\s+)?(?:long|short))"
    r"(?:\s+(?:this|it|the\s+(?:stock|etf|fund|pattern|setup|trade)))?"
    r"(?:\s+or\s+(?:(?:go|stay)\s+)?(?:long|short|buy|sell|hold))?"
    r"\s*[?.!]*\s*$"
    r"|^\s*(?:would|should)\s+you\s+"
    r"(?:buy|sell|hold|go\s+long|go\s+short)"
    r"(?:\s+(?:this|it|the\s+(?:stock|etf|fund|pattern|setup|trade)))?"
    r"\s*[?.!]*\s*$"
    r")",
    re.IGNORECASE,
)

_ADVICE_SYMBOL_STOPWORDS = {
    "A", "AN", "ANYTHING", "ETF", "ETFS", "FUND", "FUNDS", "MARKET",
    "ONE", "SOMETHING", "STOCK", "STOCKS", "THE", "THIS", "TODAY",
}


def _named_investment_advice_symbol(text):
    """Return a user-named ticker-like token in a buy/sell/hold question.

    This is intentionally conservative: a generic "what should I buy?" must
    remain in the horizon-first discovery funnel, while "should I buy TSLA?"
    may load TSLA's evidence without answering the suitability question.
    """
    if not isinstance(text, str):
        return None
    patterns = (
        r"\bshould\s+i\s+(?:buy|sell|hold|invest\s+in)\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\b",
        r"\bis\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\s+(?:a\s+)?(?:good|safe|smart)\s+investment\b",
        r"\bis\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\s+(?:a\s+)?(?:good|safe|smart)\s+trade\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            token = match.group(1).upper()
            if token not in _ADVICE_SYMBOL_STOPWORDS:
                return token
    return None


def _explicit_ticker(text):
    """Extract an explicit all-caps ticker from a weak-period research ask."""
    if not isinstance(text, str):
        return None
    for token in re.findall(r"(?<![A-Za-z0-9.\-])([A-Z][A-Z0-9.\-]{0,9})(?![A-Za-z0-9.\-])", text):
        if token not in _ADVICE_SYMBOL_STOPWORDS and len(token) > 1:
            return token
    return None


def classify_investor_intent(messages_or_text):
    """Classify Tara's investor-education funnel using at most one prior user turn.

    Returned values are behavioral contracts, not marketing personas:
      start                - amount/general investing ask; ask horizon first
      long_term            - explain seasonality is only a timing overlay
      seasonal_etf/stock   - run a transparent bullish evidence screen
      seasonal_current     - seasonal/trade horizon known, universe still missing
      weak_etf/stock       - screen recurring underlying weakness as research
      weak_symbol          - deep-dive a user-named ticker's short-direction pattern
      exclusion_study      - discuss only a validated exclusion study/report
      buy_hold_study       - explain the long-term baseline/exclusion workflow
      capabilities         - explain Tara's outcome-oriented research paths
      named_security       - analyze a user-selected symbol without a buy/sell verdict
      trade_suitability     - explain a loaded pattern without a personal trade verdict
    """
    if isinstance(messages_or_text, str):
        user_turns = [messages_or_text]
    else:
        user_turns = [
            message.get("content", "")
            for message in (messages_or_text or [])
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ]
    if not user_turns:
        return None
    latest = user_turns[-1].strip()
    previous = user_turns[-2].strip() if len(user_turns) > 1 else ""

    if _CAPABILITY_GUIDE_RE.search(latest):
        return "capabilities"
    named_symbol = _named_investment_advice_symbol(latest)
    if named_symbol:
        return "named_security"
    if _PERSONAL_TRADE_DECISION_RE.search(latest):
        return "trade_suitability"
    if _explicit_ticker(latest) and _DIRECT_VIEW_REQUEST_RE.search(latest):
        # An explicit symbol plus a direct viewer verb is an actuation request,
        # even when the user also says "seasonal pattern". Let the chart-action
        # path read that symbol's evidence and queue a verified UI transaction;
        # the general investor funnel below is only for discovery questions.
        return None
    if _explicit_ticker(latest) and re.search(
        r"\b(?:analy[sz]e|evaluate|assess|review|explain|reliab(?:le|ility)|"
        r"how\s+(?:strong|good|consistent))\b",
        latest,
        re.IGNORECASE,
    ):
        # A named-security research question is not a broad market-discovery
        # request just because it also contains "current seasonal pattern".
        return None
    if _BUY_HOLD_STUDY_RE.search(latest):
        return "buy_hold_study"
    if _EXCLUSION_STUDY_RE.search(latest):
        return "exclusion_study"
    if _WEAK_PERIOD_RE.search(latest):
        if _ETF_UNIVERSE_RE.search(latest):
            return "weak_etf"
        if _STOCK_UNIVERSE_RE.search(latest):
            return "weak_stock"
        if _explicit_ticker(latest):
            return "weak_symbol"

    previous_is_investor_funnel = bool(
        _BROAD_INVESTMENT_DISCOVERY_RE.search(previous)
        or _GENERIC_TRADE_DISCOVERY_RE.search(previous)
        or _SEASONAL_DISCOVERY_RE.search(previous)
    )
    if previous_is_investor_funnel and _LONG_TERM_HORIZON_REPLY_RE.match(latest):
        return "long_term"
    if previous_is_investor_funnel and _SEASONAL_HORIZON_REPLY_RE.match(latest):
        return "seasonal_current"
    if previous_is_investor_funnel and _ETF_UNIVERSE_RE.fullmatch(latest.rstrip(".!? ")):
        return "seasonal_etf" if (
            _GENERIC_TRADE_DISCOVERY_RE.search(previous)
            or _SEASONAL_DISCOVERY_RE.search(previous)
        ) else "start"
    if previous_is_investor_funnel and _STOCK_UNIVERSE_RE.fullmatch(latest.rstrip(".!? ")):
        return "seasonal_stock" if (
            _GENERIC_TRADE_DISCOVERY_RE.search(previous)
            or _SEASONAL_DISCOVERY_RE.search(previous)
        ) else "start"

    broad = bool(_BROAD_INVESTMENT_DISCOVERY_RE.search(latest))
    generic_trade = bool(_GENERIC_TRADE_DISCOVERY_RE.search(latest))
    seasonal = bool(_SEASONAL_DISCOVERY_RE.search(latest))
    if not (broad or generic_trade or seasonal):
        return None
    if _LONG_TERM_HORIZON_RE.search(latest) and not seasonal:
        return "long_term"
    if seasonal or generic_trade:
        if _ETF_UNIVERSE_RE.search(latest):
            return "seasonal_etf"
        if _STOCK_UNIVERSE_RE.search(latest):
            return "seasonal_stock"
        return "seasonal_current"
    return "start"


def investor_guidance_response(intent):
    """Deterministic first-step education; no model and no market action."""
    if intent == "capabilities":
        return (
            "Tell me the outcome you want, and I will guide the research one step at a time. "
            "You can ask me to:<br>"
            "<b>Find opportunities</b> - screen bullish or historically weak ETF or S&amp;P 500 "
            "seasonal patterns for this time of year.<br>"
            "<b>Research a ticker</b> - load its exact seasonal pattern, explain wins, losses, "
            "worst years, Sharpe ratio, and reliability.<br>"
            "<b>Study downside</b> - find a ticker's recurring weak window without turning it "
            "into a sell or short recommendation.<br>"
            "<b>Research long-term investing</b> - open and read Buy &amp; Hold, compare symbols "
            "over the same history, then test a recurring weak date range.<br>"
            "<b>Learn TradeWave</b> - explain a chart, metric, setting, or research workflow. "
            "Choose one of the guided questions below, or describe what you want to accomplish."
        )
    if intent == "start":
        return (
            "TradeWave can help you research candidates, but it cannot decide what is suitable "
            "for your money or tell you what to buy. Is this for long-term investing over years, "
            "or a seasonal opportunity lasting days or weeks? For a seasonal search, I’ll screen "
            "historical patterns and show the losing evidence as well as the gains before you choose."
        )
    if intent == "long_term":
        return (
            "<b>1. Start with Buy &amp; Hold</b><br>"
            "In the Wave Viewer, enter a ticker such as MSFT. After its chart loads, open "
            "<b>Analysis &rarr; Buy &amp; Hold</b>. The green and red yearly bars show how the "
            "security performed in each completed year, the Trend Chart shows its typical path "
            "through the calendar, and Cumulative Return shows how repeated full-year holding "
            "compounded across the selected history.<br><br>"
            "<b>2. Compare investments</b><br>"
            "Keep MSFT's Buy &amp; Hold study loaded, open <b>Analysis &rarr; Compare "
            "Symbols&hellip;</b>, and enter WMT and AVGO. TradeWave compares the same full-year "
            "dates, direction, and common historical years so you can judge growth, consistency, "
            "and losses side by side.<br><br>"
            "<b>3. Advanced: test weak dates</b><br>"
            "If the yearly bars or Trend Chart reveal a recurring weak period, set that exact "
            "shorter date range and open <b>Analysis &rarr; Exclude Current Range</b>. After the "
            "outside dates load, select <b>View Exclusion Report</b> to compare the exclusion "
            "model with Buy &amp; Hold over the same completed years.<br><br>"
            "TradeWave provides historical evidence and timing context. It does not decide which "
            "investment fits your goals, risk, fees, taxes, or diversification needs."
        )
    if intent == "buy_hold_study":
        return (
            "<b>1. Open the Buy &amp; Hold study</b><br>"
            "In the Wave Viewer, enter the first ticker you want to study. After its chart loads, "
            "open <b>Analysis &rarr; Buy &amp; Hold</b>. This is TradeWave's Jan 1-to-Jan 1, "
            "always-invested baseline across completed years.<br><br>"
            "<b>2. Read historical growth</b><br>"
            "Use the green and red yearly bars to see each year's gain or loss, the Trend Chart "
            "to see the typical path through the calendar, and Cumulative Return to see the "
            "compounded result across the selected history.<br><br>"
            "<b>3. Compare securities</b><br>"
            "With that Buy &amp; Hold study still loaded, open <b>Analysis &rarr; Compare "
            "Symbols&hellip;</b>. For example, load MSFT first and enter WMT and AVGO. The report "
            "uses the same full-year dates, direction, and common historical years for a fair "
            "side-by-side comparison.<br><br>"
            "<b>4. Advanced: measure a weak period</b><br>"
            "Set the exact weak date range you found in the yearly evidence or Trend Chart, then "
            "open <b>Analysis &rarr; Exclude Current Range</b>. After it loads, select "
            "<b>View Exclusion Report</b> to see how excluding those dates changed cumulative "
            "return versus Buy &amp; Hold over the same completed years.<br><br>"
            "This is historical research, not a promise that timing will outperform or a decision "
            "about which investment is suitable for you."
        )
    if intent == "seasonal_current":
        return (
            "I can screen historical seasonal candidates without choosing one for you. Do you "
            "want a curated ETF screen or S&P 500 stock candidates? I’ll return a shortlist with "
            "the measured window and evidence, then you choose which one to inspect in depth."
        )
    return None


_GUIDANCE_SYMBOL_RE = re.compile(r"<b>\s*([A-Z][A-Z0-9.\-]{0,14})\s*</b>")


def _guided_question(label, prompt):
    """Return a small, display-safe guided-question item."""
    label = str(label or "").strip()[:60]
    prompt = str(prompt or "").strip()[:240]
    return {"label": label, "prompt": prompt} if label and prompt else None


def _guided_symbol(value):
    raw = str(value or "").strip().upper()
    symbol = raw if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", raw) else ""
    if not symbol or symbol in _ADVICE_SYMBOL_STOPWORDS:
        return ""
    return symbol


def guided_next_questions(messages_or_text=None, reply="", actions=None,
                          current_view=None, analysis_report=None):
    """Build at most three contextual questions Tara can actually handle.

    Labels describe the outcome; prompts are the exact utterances sent when a
    user clicks. The list is deterministic and only interpolates validated
    ticker tokens, so model prose cannot create arbitrary client controls.
    """
    report_type = (
        str((analysis_report or {}).get("report_type") or "")
        if isinstance(analysis_report, dict) else ""
    )
    if report_type == "range_comparison":
        return [
            _guided_question(
                "Judge the result",
                "Did excluding these dates improve the historical result versus Buy & Hold?",
            ),
            _guided_question(
                "Inspect the downside",
                "What was the worst completed year for each approach?",
            ),
            _guided_question(
                "Check limitations",
                "What are the limitations of this date-range exclusion study?",
            ),
        ]
    if report_type == "date_range_comparison":
        return [
            _guided_question(
                "Compare the ranges",
                "Which date range had the strongest historical evidence?",
            ),
            _guided_question(
                "Inspect the downside",
                "Which range had the worst losing year?",
            ),
            _guided_question(
                "Use the baseline",
                "How did each date range compare with Buy & Hold?",
            ),
        ]
    if report_type == "symbol_comparison":
        return [
            _guided_question(
                "Compare consistency",
                "Which symbol was profitable most often?",
            ),
            _guided_question(
                "Compare downside",
                "Which symbol had the smaller historical losses?",
            ),
            _guided_question(
                "Understand the tradeoff",
                "What tradeoff matters most in this comparison?",
            ),
        ]

    intent = classify_investor_intent(messages_or_text)
    symbols = []

    def add_symbol(value):
        symbol = _guided_symbol(value)
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    for action in actions or []:
        if not isinstance(action, dict):
            continue
        spec = action.get("spec")
        if isinstance(spec, dict):
            add_symbol(spec.get("symbol"))
    if isinstance(reply, str):
        for match in _GUIDANCE_SYMBOL_RE.findall(reply):
            add_symbol(match)
    if isinstance(current_view, dict) and current_view.get("view_ready") is True:
        add_symbol(current_view.get("symbol"))

    symbol = symbols[0] if symbols else ""
    if intent == "start":
        return [
            _guided_question("Plan for years", "long term"),
            _guided_question(
                "Find seasonal ETFs",
                "Show me bullish ETF patterns this time of year",
            ),
            _guided_question(
                "Find seasonal stocks",
                "Show me bullish S&P 500 stock patterns this time of year",
            ),
        ]
    if intent in {"long_term", "buy_hold_study"}:
        baseline_prompt = (
            "Show me the Buy & Hold workflow for %s" % symbol
            if symbol else "Show me the Buy & Hold workflow for long-term investors"
        )
        weak_prompt = (
            "When is %s historically weak?" % symbol
            if symbol else "How do I find a ticker's recurring weak dates?"
        )
        return [
            _guided_question("Establish a baseline", baseline_prompt),
            _guided_question("Find recurring weakness", weak_prompt),
            _guided_question(
                "Compare timing honestly",
                "How do I compare excluding a weak date range with Buy & Hold?",
            ),
        ]
    if intent == "seasonal_current":
        return [
            _guided_question(
                "Find ETF candidates",
                "Show me bullish ETF patterns this time of year",
            ),
            _guided_question(
                "Find stock candidates",
                "Show me bullish S&P 500 stock patterns this time of year",
            ),
            _guided_question(
                "Study weak periods",
                "Show me historically weak ETF periods this time of year",
            ),
        ]
    if intent in {"seasonal_etf", "seasonal_stock", "weak_etf", "weak_stock"} and symbols:
        questions = [
            _guided_question(
                "Inspect %s" % symbols[0],
                "Analyze %s's full seasonal evidence" % symbols[0],
            ),
        ]
        if len(symbols) > 1:
            questions.append(_guided_question(
                "Compare two candidates",
                "Compare %s and %s using their historical seasonal evidence"
                % (symbols[0], symbols[1]),
            ))
        questions.append(_guided_question(
            "Study the downside",
            "When is %s historically weak?" % symbols[0],
        ))
        return questions[:3]
    if intent == "weak_symbol" and symbol:
        return [
            _guided_question(
                "Judge recurrence",
                "How reliable is %s's weak-period pattern?" % symbol,
            ),
            _guided_question(
                "Compare with holding",
                "How do I compare this weak window with Buy & Hold?",
            ),
            _guided_question(
                "Build an exclusion study",
                "How do I create a Date Range Exclusion Report from this window?",
            ),
        ]
    if intent == "exclusion_study":
        return [
            _guided_question(
                "Create the valid report",
                "How do I create a Date Range Exclusion Report?",
            ),
            _guided_question(
                "Understand the baseline",
                "Show me the Buy & Hold workflow for long-term investors",
            ),
            _guided_question(
                "Avoid false comparisons",
                "Why must an exclusion study use the same completed years?",
            ),
        ]
    if symbol:
        return [
            _guided_question(
                "Judge reliability",
                "How reliable is %s's current seasonal pattern?" % symbol,
            ),
            _guided_question(
                "Find weak dates",
                "When is %s historically weak?" % symbol,
            ),
            _guided_question(
                "Study long-term holding",
                "Show me the Buy & Hold workflow for %s" % symbol,
            ),
        ]
    return [
        _guided_question(
            "Find opportunities",
            "Show me bullish S&P 500 stock patterns this time of year",
        ),
        _guided_question(
            "Learn the method",
            "How does TradeWave test a seasonal pattern?",
        ),
        _guided_question(
            "Invest for years",
            "Show me the Buy & Hold workflow for long-term investors",
        ),
    ]
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


_DIRECT_INVESTMENT_ADVICE_RE = re.compile(
    r"(?:"
    r"\byou\s+should\s+(?:buy|sell|hold|invest|allocate|put)\b"
    r"|\byou\s+should\s+(?:go\s+)?(?:long|short)\b"
    r"|\bi\s+(?:recommend|suggest)\s+(?:that\s+you\s+)?(?:buy|sell|hold|invest|allocate|put)\b"
    r"|\bi\s+(?:recommend|suggest)\s+(?:that\s+you\s+)?(?:go\s+)?(?:long|short)\b"
    r"|\b(?:buy|sell|hold)\s+(?-i:[A-Z][A-Z0-9.\-]{0,14})\b"
    r"|\b(?:put|invest|allocate)\s+(?:all\s+of\s+)?(?:your\s+)?\$?\s*[\d,.]+\b"
    r"|\ballocate\s+\d{1,3}\s*%\b"
    r"|\bconsider\s+(?:buying|selling|holding|investing|allocating)\b"
    r"|\b(?:a\s+)?(?:reasonable|appropriate|suitable)\s+allocation\s+(?:is|would\s+be)\b"
    r"|\b(?:the\s+)?(?:best|right|safe)\s+(?:investment|choice)\s+for\s+you\b"
    r")",
    re.IGNORECASE,
)
_INVESTMENT_FORECAST_RE = re.compile(
    r"\b(?:it|this|[A-Z][A-Z0-9.\-]{0,14})\s+(?:will|should|is\s+going\s+to)\s+"
    r"(?:rise|gain|return|make|earn|outperform|be\s+profitable)\b",
    re.IGNORECASE,
)
_INVESTMENT_BOUNDARY_RE = re.compile(
    r"\b(?:cannot|can't|can\s+not|does\s+not|doesn't|is\s+not|isn't)\b.{0,80}\b"
    r"(?:determine|decide|tell|recommend|personal|suitable|fits?|suitability)\b"
    r"|\bnot\s+(?:a\s+)?(?:personal\s+)?recommendation\b",
    re.IGNORECASE,
)
_NEGATED_DIRECT_ADVICE_RE = re.compile(
    r"\b(?:cannot|can't|can\s+not|do\s+not|don't|not)\b.{0,55}\b"
    r"(?:recommend(?:ation)?|tell|advise)\b.{0,35}\b(?:buy|sell|hold|invest|allocate)\b"
    r"(?:\s+(?-i:[A-Z][A-Z0-9.\-]{0,14})\b)?",
    re.IGNORECASE,
)


def response_violates_investor_contract(text, investor_intent):
    """Fail closed on personalized directives or forecasts in investor flows."""
    if investor_intent not in {
        "start", "long_term", "seasonal_etf", "seasonal_stock", "seasonal_current",
        "weak_etf", "weak_stock", "weak_symbol", "exclusion_study", "named_security",
        "trade_suitability",
    }:
        return False
    plain = re.sub(r"<[^>]*>", " ", text or "")
    advice_scan = _NEGATED_DIRECT_ADVICE_RE.sub(" ", plain)
    if _DIRECT_INVESTMENT_ADVICE_RE.search(advice_scan) or _INVESTMENT_FORECAST_RE.search(plain):
        return True
    if investor_intent == "named_security":
        return not (
            _INVESTMENT_BOUNDARY_RE.search(plain)
            and re.search(r"\bhistorical(?:ly)?\b", plain, re.IGNORECASE)
        )
    if investor_intent == "trade_suitability":
        bare_verdict = re.match(r"^\s*(?:go\s+)?(?:long|short)\b", plain, re.IGNORECASE)
        return bool(bare_verdict) or not _INVESTMENT_BOUNDARY_RE.search(plain)
    return False


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

            investor_intent = classify_investor_intent(messages)
            if investor_intent == "weak_symbol":
                return "chart"
            if investor_intent in {
                "start", "long_term", "seasonal_etf", "seasonal_stock",
                "seasonal_current", "weak_etf", "weak_stock", "exclusion_study",
            }:
                # Candidate discovery and investor education may switch the
                # opportunity-table market, but they never auto-select a winner
                # into the chart. The user chooses the deep dive.
                return None

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
    if reason == "personalized_investment_advice":
        queued = " A valid chart action is already queued; do not call more tools." if action_queued else ""
        return (
            "Rewrite as historical research, not a personalized recommendation." + queued + " Say "
            "TradeWave cannot determine whether the security is suitable for this user; include "
            "only the tool-grounded historical record and downside evidence. Do not say buy, sell, "
            "hold, allocate an amount, call anything safe, or predict what the security will do."
        )
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


def _display_stat(value, signed=False):
    """Format a validated numeric viewer stat without inventing precision."""
    if value is None:
        return None
    if value.is_integer():
        rendered = str(int(value))
    else:
        rendered = ("%.2f" % value).rstrip("0").rstrip(".")
    if signed and value > 0:
        rendered = "+" + rendered
    return rendered


def loaded_pattern_suitability_response(text, current_view=None):
    """Answer a personal trade-direction ask without giving a trade verdict.

    A confirmed viewer may contribute exact historical evidence, but its stored
    long/short setting is never converted into advice about what the user should
    do. This deterministic boundary also handles the request safely when no
    chart has been confirmed.
    """
    if not isinstance(text, str) or not _PERSONAL_TRADE_DECISION_RE.search(text):
        return None

    boundary = (
        "TradeWave cannot tell you whether to go long or short or whether a trade "
        "is suitable for you. "
    )
    disclaimer = (
        "<br><br><i>Past performance does not guarantee future results. "
        "Always manage your risk.</i>"
    )
    view = current_view if isinstance(current_view, dict) else {}
    symbol = str(view.get("symbol") or "").strip().upper()
    if view.get("view_ready") is not True or not _VS_SYMBOL_RE.fullmatch(symbol):
        return (
            boundary
            + "There is no confirmed loaded pattern to summarize. Load a historical setup, "
              "and I can explain its exact direction, win/loss record, average result, Sharpe "
              "ratio, and downside evidence without choosing the trade for you."
            + disclaimer
        )

    direction_value = str(view.get("direction") or "").strip().lower()
    if direction_value in {"l", "long", "bullish"}:
        direction = "Long"
    elif direction_value in {"s", "short", "bearish"}:
        direction = "Short"
    else:
        direction = "unspecified"

    stats = view.get("stats") if isinstance(view.get("stats"), dict) else {}
    wins = _numeric_stat(stats.get("Num Winners"))
    losses = _numeric_stat(stats.get("Num Losers"))
    percent_profitable = _numeric_stat(stats.get("Percent Profitable"), percent=True)
    avg_result = _numeric_stat(
        stats.get("Avg Profit - All")
        if stats.get("Avg Profit - All") is not None
        else stats.get("Avg Profit"),
        percent=True,
    )
    sharpe = _numeric_stat(stats.get("Sharpe Ratio"))

    evidence = []
    if (
        wins is not None and losses is not None
        and wins >= 0 and losses >= 0
        and wins.is_integer() and losses.is_integer()
        and wins + losses > 0
    ):
        evidence.append(
            "won %d of %d completed years shown"
            % (int(wins), int(wins + losses))
        )
    elif percent_profitable is not None and 0 <= percent_profitable <= 100:
        evidence.append(
            "was profitable in %s%% of the completed years shown"
            % _display_stat(percent_profitable)
        )
    if avg_result is not None:
        evidence.append("had an average pattern result of %s%%" % _display_stat(avg_result, signed=True))
    if sharpe is not None:
        evidence.append("had a Sharpe ratio of %s" % _display_stat(sharpe))

    entry_date = str(view.get("entry_date") or view.get("start_date") or "").strip()
    days_out = view.get("days_out")
    exact_window = ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry_date) and isinstance(days_out, int):
        exact_window = " for the %s, %d-day window" % (entry_date, days_out)

    evidence_text = ""
    if evidence:
        evidence_text = "; it " + ", ".join(evidence) + "."
    else:
        evidence_text = "."
    return (
        boundary
        + "The confirmed <b>%s</b> study is a historical <b>%s</b> pattern%s%s "
          "That is evidence for this exact historical setup, not today's market direction or a "
          "forecast. Review its losing years and MAE/drawdown before deciding."
        % (symbol, direction, exact_window, evidence_text)
        + disclaimer
    )


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
    """Resolve a symbol action to one complete, exact setup identity."""
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
            and 1 <= candidate["days_out"] <= 367
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
    """Build evidence only from chart rows belonging to the confirmed view."""
    if _confirmed_view_setup(current_view) != expected_setup:
        return None
    supplied_stats = (
        current_view.get("stats")
        if isinstance((current_view or {}).get("stats"), dict)
        else {}
    )
    supplied_wins = _numeric_stat(supplied_stats.get("Num Winners"))
    supplied_losses = _numeric_stat(supplied_stats.get("Num Losers"))
    avg_return = _numeric_stat(supplied_stats.get("Avg Profit - All"), percent=True)
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

    evidence_stats = {"historical_win_rate": wins / years, "years": years}
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
    """Compose a status-neutral evidence line for the requested setup."""
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
    """Detect a narrated setup statistic that conflicts with exact evidence."""
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
            (int(match.group(2)) == yrs and int(match.group(1)) != wins)
            or int(match.group(1)) == int(match.group(2))
            for match in _RPL_WIN_RE.finditer(text)
        ) or any(
            yrs and round(int(match.group(1)) / 100.0 * yrs) != wins
            for match in _RPL_PCT_RE.finditer(text)
        )
    avg_claims = [match.group(1) for match in _RPL_AVG_RE.finditer(text)]
    avg_conflict = bool(avg_claims) and (
        avg is None or not any(_numeric_claim_matches(claim, avg) for claim in avg_claims)
    )
    sharpe_claims = [match.group(1) for match in _RPL_SHARPE_RE.finditer(text)]
    sharpe_conflict = bool(sharpe_claims) and (
        sharpe is None or not any(_numeric_claim_matches(claim, sharpe) for claim in sharpe_claims)
    )
    return win_conflict or avg_conflict or sharpe_conflict


def _ensure_load_named(text, actions, cards, card_list, current_view=None):
    """Guarantee the loaded pick is announced with ITS OWN correct record. Fixes two failures:
    (1) a bare confirmation with no symbol; (2) the right symbol but a STALE/FABRICATED win rate
    carried from an earlier setup (loads the September window but says 'won 10 of 10' from the June
    setup). The card is matched to the loaded setup by entry_date, and the HEADLINE is authoritative."""
    text = text or ""
    loaded = [a.get("spec", {}) for a in actions
              if a.get("type") == "set_view" and isinstance(a.get("spec"), dict) and a["spec"].get("symbol")]
    if not loaded:
        return text
    spec = loaded[-1]
    sym = str(spec.get("symbol")).upper()
    expected = _resolved_action_setup(spec, current_view)
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
        cards.append({"symbol": r.get("symbol"), "direction": direction,
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


_HUNDRED_YEAR_SECURITY_RE = re.compile(
    r"\b(?:100|hundred)[- ]year(?:\s+seasonal)?\s+pattern\b", re.IGNORECASE
)
_BEST_TIME_BUY_RE = re.compile(
    r"\b(?:best|strongest|good)\s+(?:historical\s+)?(?:time|date|window|period)\s+"
    r"(?:to|for)\s+(?:buy(?:ing)?|enter(?:ing)?|invest(?:ing)?(?:\s+in)?)\b|"
    r"\bwhen\b.{0,45}\b(?:buy|enter|invest\s+in)\b",
    re.IGNORECASE,
)
_HISTORICAL_WEAK_SYMBOL_RE = re.compile(
    r"\bwhen\b.{0,45}\b(?:historically\s+)?weak\b|"
    r"\b(?:historically\s+weak|weakest|bearish)\b.{0,45}"
    r"\b(?:time|date|window|period|season)\b",
    re.IGNORECASE,
)
_QUESTION_SYMBOL_STOPWORDS = _ADVICE_SYMBOL_STOPWORDS | {
    "BEST", "BUY", "DID", "DO", "DOES", "DURING", "FOR", "HISTORICALLY",
    "HOW", "IN", "INDEX", "INVEST", "LONG", "OIL", "PATTERN", "SHORT",
    "TIME", "WHEN", "WEAK", "YEAR",
}


def _market_today():
    """Return the same US-market calendar date Tara uses for date-sensitive research."""

    return datetime.datetime.now(ZoneInfo("America/New_York")).date()


def _question_symbol(text, current_view=None):
    """Extract a ticker from a research question, with loaded-view pronoun support."""

    value = str(text or "")
    for token in re.findall(
        r"(?<![A-Za-z0-9.\-])([A-Z][A-Z0-9.\-]{0,14})(?![A-Za-z0-9.\-])",
        value,
    ):
        if token not in _QUESTION_SYMBOL_STOPWORDS and len(token) > 1:
            return token
    patterns = (
        r"\b(?:buy|enter|invest\s+in)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9.\-]{0,14})\b",
        r"\bwhen\s+is\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\b",
        r"\bhow\s+did\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\b",
        r"\bshow(?:\s+me)?\s+([A-Za-z][A-Za-z0-9.\-]{0,14})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if not match:
            continue
        token = match.group(1).upper()
        if token not in _QUESTION_SYMBOL_STOPWORDS and len(token) > 1:
            return token
    if re.search(r"\b(?:this|current|loaded)\s+(?:stock|security|ticker|symbol|chart)\b", value, re.I):
        view = current_view if isinstance(current_view, dict) else {}
        symbol = str(view.get("symbol") or "").strip().upper()
        if _VS_SYMBOL_RE.fullmatch(symbol):
            return symbol
    return None


def _loopback_json(path, token, *, params=None, timeout=(5, 20)):
    base = (config.appserver_url or "").rstrip("/")
    if not base or not token:
        return None, None
    query = dict(params or {})
    query["token"] = token
    try:
        response = requests.get(base + path, params=query, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("tara loopback %s failed: %s", path, exc)
        return None, None
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        payload = None
    return response.status_code, payload if isinstance(payload, dict) else None


def _symbol_resolution_score(question, match):
    haystack = " ".join(
        str(match.get(key) or "").lower() for key in ("label", "name")
    )
    query = str(question or "").lower()
    hints = (
        (("index", "indices"), ("index", "indices")),
        (("crude", "oil"), ("crude", "oil")),
        (("future", "futures"), ("future", "futures")),
        (("commodity", "commodities"), ("commodity", "commodities")),
        (("etf", "fund"), ("etf", "fund")),
        (("stock", "equity"), ("stock", "stocks", "equity", "equities")),
    )
    score = 0
    for question_terms, match_terms in hints:
        if any(term in query for term in question_terms) and any(
            term in haystack for term in match_terms
        ):
            score += 4
    for token in set(re.findall(r"[a-z]{3,}", query)):
        if token not in {"during", "hundred", "pattern", "year", "years", "historically"} and token in haystack:
            score += 1
    return score


_CANONICAL_INDEX_SYMBOLS = frozenset({
    "COMP", "DJI", "DJIA", "NDX", "NYA", "OEX", "RUT", "SPX", "VIX",
})


def _resolve_question_symbol(symbol, question, token, current_view=None):
    status, payload = _loopback_json(
        "/ResolveSymbol/%s" % quote(str(symbol).upper()), token, timeout=(5, 15)
    )
    if status != 200 or payload is None:
        return {"status": "unavailable", "symbol": str(symbol).upper()}
    matches = [item for item in payload.get("matches", []) if isinstance(item, dict)]
    if not matches:
        return {"status": "not_found", "symbol": str(symbol).upper()}

    scored = [(item, _symbol_resolution_score(question, item)) for item in matches]
    best_score = max(score for _, score in scored)
    best = [item for item, score in scored if score == best_score and score > 0]
    if len(best) == 1:
        selected = best[0]
    else:
        view = current_view if isinstance(current_view, dict) else {}
        current_market = str(view.get("market") or "")
        current_symbol = str(view.get("symbol") or "").upper()
        current_match = [
            item for item in matches
            if current_symbol == str(symbol).upper()
            and str(item.get("resourceID") or "") == current_market
        ]
        if len(current_match) == 1:
            selected = current_match[0]
        elif best_score == 0 and str(symbol).upper() in _CANONICAL_INDEX_SYMBOLS and len(
            index_matches := [
                item for item in matches
                if str(item.get("resourceID") or "") == "5"
            ]
        ) == 1:
            # TradeWave's canonical index symbols should not be displaced by
            # an unrelated foreign security that happens to reuse the ticker.
            selected = index_matches[0]
        elif best_score == 0 and len(
            us_matches := [
                item for item in matches
                if str(item.get("resourceID") or "") == "2"
            ]
        ) == 1:
            # For an unqualified ticker such as MSFT, prefer TradeWave's
            # representative US-stock market over a foreign receipt with the
            # same code. Explicit words such as CDR, index, ETF, or crude oil
            # score first and therefore remain authoritative.
            selected = us_matches[0]
        elif len(matches) == 1:
            selected = matches[0]
        else:
            return {
                "status": "ambiguous",
                "symbol": str(symbol).upper(),
                "matches": matches,
            }
    return {
        "status": "ok",
        "symbol": str(symbol).upper(),
        "market": str(selected.get("resourceID") or ""),
        "label": str(selected.get("label") or ""),
        "name": str(selected.get("name") or ""),
    }


def _resolution_boundary(resolution):
    symbol = html.escape(str(resolution.get("symbol") or "the symbol"))
    status = resolution.get("status")
    if status == "not_found":
        return "I could not find <b>%s</b> in TradeWave's supported security lists." % symbol
    if status == "ambiguous":
        options = []
        for item in resolution.get("matches", [])[:5]:
            label = html.escape(str(item.get("label") or item.get("resourceID") or "market"))
            name = html.escape(str(item.get("name") or symbol))
            options.append("%s (%s)" % (name, label))
        return (
            "<b>%s is ambiguous.</b> Please name the market or security, such as "
            "%s, so I do not load the wrong chart." % (symbol, "; ".join(options))
        )
    return (
        "I could not verify <b>%s</b> against TradeWave's security list right now, "
        "so I have not changed the chart." % symbol
    )


def _symbol_metadata_dates(market, symbol, token):
    status, payload = _loopback_json(
        "/StockMetaData/%s/%s" % (quote(str(market)), quote(str(symbol))),
        token,
        timeout=(5, 15),
    )
    metadata = payload.get("StockMetaData") if status == 200 and payload else None
    if not isinstance(metadata, list) or len(metadata) < 2:
        return None
    try:
        return (
            datetime.date.fromisoformat(str(metadata[0])[:10]),
            datetime.date.fromisoformat(str(metadata[-1])[:10]),
        )
    except (TypeError, ValueError):
        return None


def _completed_pe2_count(bounds, today):
    if not bounds:
        return None
    first_date, last_date = bounds
    available_through = min(last_date, today)
    count = 0
    for year in range(first_date.year, available_through.year + 1):
        if year % 4 != 2:
            continue
        start = datetime.date(year, 9, 27)
        if start >= first_date and hundred_year_end_date(start) <= available_through:
            count += 1
    return min(count, 99) if count > 0 else None


def _chart_data4(market, symbol, entry_date, days_out, years_value, token, *, direction="long"):
    try:
        engine_days = int(days_out) - 1
    except (TypeError, ValueError):
        return None, None
    return _loopback_json(
        "/ChartData4/%s/%s/%s/%s/%s" % (
            quote(str(market)),
            quote(str(entry_date)),
            quote(str(symbol).upper()),
            engine_days,
            quote(str(years_value)),
        ),
        token,
        params={"comparison_direction": direction},
        timeout=(5, 30),
    )


def _stat_number(stats, key):
    if not isinstance(stats, dict):
        return None
    raw = str(stats.get(key) or "").replace("%", "").replace(",", "").strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value, *, digits=1):
    if value is None:
        return "unavailable"
    rounded = round(float(value), digits)
    rendered = ("%.*f" % (digits, abs(rounded))).rstrip("0").rstrip(".")
    return ("+" if rounded >= 0 else "-") + rendered + "%"


def _verified_chart_spec(payload, expected):
    request_used = payload.get("request") if isinstance(payload, dict) else None
    if not isinstance(request_used, dict):
        return None
    try:
        spec = {
            "market": str(request_used.get("market")),
            "symbol": str(request_used.get("symbol") or "").upper(),
            "entry_date": str(request_used.get("entry_date") or ""),
            "days_out": int(request_used.get("days_out")),
            "years": int(request_used.get("years")),
            "pe_cycle": str(request_used.get("pe_cycle") or "cons"),
        }
    except (TypeError, ValueError):
        return None
    cleaned = _validate_view_spec(spec)
    for field in ("market", "symbol", "entry_date", "days_out", "pe_cycle"):
        if cleaned.get(field) != expected.get(field):
            return None
    return cleaned


def build_hundred_year_security_command(message, current_view, user_token, *, today=None):
    """Analyze any explicitly named security over the 100-Year Pattern dates and PE+2 cohort."""

    text = str(message or "").strip()
    if not text or not _HUNDRED_YEAR_SECURITY_RE.search(text):
        return None
    symbol = _question_symbol(text, current_view)
    if not symbol:
        return None
    resolution = _resolve_question_symbol(symbol, text, user_token, current_view)
    if resolution.get("status") != "ok":
        return {"reply": _resolution_boundary(resolution), "spec": None}

    current = today or _market_today()
    bounds = _symbol_metadata_dates(
        resolution["market"], resolution["symbol"], user_token
    )
    pe2_count = _completed_pe2_count(bounds, current)
    if not pe2_count:
        return {
            "reply": (
                "TradeWave does not have enough completed PE+2 history to evaluate "
                "<b>%s</b> over the 100-Year Pattern dates, so I have not changed the chart."
                % html.escape(resolution["symbol"])
            ),
            "spec": None,
        }

    entry_date = hundred_year_occurrence_start(current).isoformat()
    expected = {
        "market": resolution["market"],
        "symbol": resolution["symbol"],
        "entry_date": entry_date,
        "days_out": HUNDRED_YEAR_DISPLAY_DAYS,
        "pe_cycle": "pe2",
    }
    status, payload = _chart_data4(
        resolution["market"],
        resolution["symbol"],
        entry_date,
        HUNDRED_YEAR_DISPLAY_DAYS,
        "pe2-%s" % pe2_count,
        user_token,
        direction="long",
    )
    if status == 403:
        return {
            "reply": (
                "<b>%s is outside this account's available markets.</b> I cannot load or "
                "summarize that chart without the required market access."
                % html.escape(resolution["symbol"])
            ),
            "spec": None,
        }
    if status != 200 or not isinstance(payload, dict):
        return {
            "reply": "I could not retrieve the verified %s chart, so I have not changed the view."
            % html.escape(resolution["symbol"]),
            "spec": None,
        }
    spec = _verified_chart_spec(payload, expected)
    stats = payload.get("stats")
    rows = payload.get("ChartData4")
    if spec is None or not isinstance(stats, dict) or not isinstance(rows, list) or not stats:
        return {
            "reply": (
                "TradeWave could not produce the exact <b>%s</b> PE+2 chart for the "
                "100-Year Pattern dates. I have not claimed a result or changed the chart."
                % html.escape(resolution["symbol"])
            ),
            "spec": None,
        }

    winners = int(_stat_number(stats, "Num Winners") or 0)
    losers = int(_stat_number(stats, "Num Losers") or 0)
    completed = winners + losers
    worst = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            year = int(row.get("year"))
            value = float(str(row.get("pct") or "").split(",", 1)[0])
            row_end = hundred_year_end_date(datetime.date(year, 9, 27))
        except (TypeError, ValueError):
            continue
        if row_end <= current and (worst is None or value < worst[1]):
            worst = (year, value)

    symbol_html = html.escape(resolution["symbol"])
    name_html = html.escape(resolution.get("name") or resolution.get("label") or "")
    end = hundred_year_end_date(datetime.date.fromisoformat(entry_date))
    avg = _stat_number(stats, "Avg Profit - All")
    median = _stat_number(stats, "Median Profit")
    sharpe = _stat_number(stats, "Sharpe Ratio")
    worst_text = (
        " Worst completed observation: %s at %s." % (worst[0], _fmt_pct(worst[1]))
        if worst is not None else ""
    )
    reply = (
        "<b>%s during the 100-Year Pattern dates</b><br>"
        "%s%s was profitable in %s of %s completed PE+2 observations. Average return: "
        "%s; median: %s; Sharpe Ratio: %s.%s<br><br>"
        "I am loading %s from Sep 27, %s through Jul 18, %s on PE+2 using its "
        "actual available history. This applies the pattern's dates and presidential-cycle "
        "position to %s; the named 100-Year Pattern in the book is the SPX study. "
        "Historical results are not forecasts."
    ) % (
        symbol_html,
        (name_html + " (" if name_html else ""),
        (symbol_html + ")" if name_html else symbol_html),
        winners,
        completed,
        _fmt_pct(avg),
        _fmt_pct(median),
        ("%.2f" % sharpe if sharpe is not None else "unavailable"),
        worst_text,
        symbol_html,
        entry_date[:4],
        end.year,
        symbol_html,
    )
    return {"reply": reply, "spec": spec}


def _best_waves_rows(market, symbol, years, token):
    status, payload = _loopback_json(
        "/OppBySymbol/%s/%s/%s/%s/-/100" % (
            quote(str(market)), quote(str(symbol)), years, years
        ),
        token,
        params={"mode": "consecutive"},
        timeout=(5, 25),
    )
    if status != 200 or not isinstance(payload, dict):
        return status, None, None, None
    request_used = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    try:
        effective_years = int(request_used.get("years"))
    except (TypeError, ValueError):
        effective_years = None
    return status, payload.get("status"), payload.get("OppBySymbol"), effective_years


def build_best_waves_command(
    message,
    current_view,
    user_token,
    *,
    default_years=None,
    today=None,
):
    """Answer buy-timing and weak-window questions from the exact desktop Best Waves rows."""

    text = str(message or "").strip()
    is_buy = bool(_BEST_TIME_BUY_RE.search(text))
    is_weak = bool(_HISTORICAL_WEAK_SYMBOL_RE.search(text))
    if not (is_buy or is_weak):
        return None
    symbol = _question_symbol(text, current_view)
    if not symbol:
        return None
    resolution = _resolve_question_symbol(symbol, text, user_token, current_view)
    if resolution.get("status") != "ok":
        return {"reply": _resolution_boundary(resolution), "spec": None}

    view = current_view if isinstance(current_view, dict) else {}
    raw_years = view.get("years") if str(view.get("pe_cycle") or "cons").lower() in {"cons", "consecutive"} else None
    try:
        years = int(raw_years if raw_years is not None else default_years)
    except (TypeError, ValueError):
        years = 10
    years = min(max(years, 1), 99)
    status, feature_status, raw_rows, effective_years = _best_waves_rows(
        resolution["market"], resolution["symbol"], years, user_token
    )
    if effective_years is not None:
        years = effective_years
    if status == 403:
        return {
            "reply": "<b>%s is outside this account's available markets.</b> I cannot scan its Best Waves."
            % html.escape(resolution["symbol"]),
            "spec": None,
        }
    if status != 200 or raw_rows is None:
        return {
            "reply": "I could not retrieve %s's verified Best Waves, so I have not changed the chart."
            % html.escape(resolution["symbol"]),
            "spec": None,
        }
    direction = "Long" if is_buy else "Short"
    current = today or _market_today()
    candidates = []
    for row in raw_rows if isinstance(raw_rows, list) else []:
        if not isinstance(row, list) or len(row) < 7 or str(row[3]).lower() != direction.lower():
            continue
        try:
            entry = datetime.date.fromisoformat(str(row[0])[:10])
            display_days = int(row[2]) + 1
            end = entry + datetime.timedelta(days=display_days - 1)
            sharpe = float(row[4])
            avg = float(row[5])
            median = float(row[6])
        except (TypeError, ValueError):
            continue
        if is_buy:
            if not current - datetime.timedelta(days=7) <= entry <= datetime.date(current.year, 12, 31):
                continue
            if end < current:
                continue
        candidates.append({
            "entry": entry,
            "end": end,
            "days_out": display_days,
            "sharpe": sharpe,
            "avg": avg,
            "median": median,
        })
    if not candidates:
        purpose = "upcoming Long" if is_buy else "Short"
        feature_note = (
            "Best Waves data is not available for this symbol and setting."
            if feature_status == "feature_not_available"
            else "No pattern passed TradeWave's Best Waves threshold for this request."
        )
        return {
            "reply": (
                "<b>No qualifying %s Best Wave was found for %s at the %s-year setting.</b> "
                "%s On desktop paid plans, the Best Waves dropdown above the bar chart is "
                "hidden or empty when nothing qualifies."
                % (purpose, html.escape(resolution["symbol"]), years, feature_note)
            ),
            "spec": None,
        }
    if is_buy:
        recent = sorted(
            (item for item in candidates if item["entry"] <= current),
            key=lambda item: (item["entry"], item["sharpe"]),
            reverse=True,
        )
        upcoming = sorted(
            (item for item in candidates if item["entry"] > current),
            key=lambda item: (item["entry"], -item["sharpe"]),
        )
        selected = recent[0] if recent else upcoming[0]
    else:
        selected = max(candidates, key=lambda item: item["sharpe"])

    expected = {
        "market": resolution["market"],
        "symbol": resolution["symbol"],
        "entry_date": selected["entry"].isoformat(),
        "days_out": selected["days_out"],
        "pe_cycle": "cons",
    }
    chart_status, chart_payload = _chart_data4(
        resolution["market"], resolution["symbol"], selected["entry"].isoformat(),
        selected["days_out"], str(years), user_token,
        direction="long" if is_buy else "short",
    )
    spec = _verified_chart_spec(chart_payload or {}, expected) if chart_status == 200 else None
    if spec is not None:
        years = spec["years"]
    symbol_html = html.escape(resolution["symbol"])
    start_label = selected["entry"].strftime("%b %d, %Y").replace(" 0", " ")
    end_label = selected["end"].strftime("%b %d, %Y").replace(" 0", " ")
    if is_buy:
        timing = "already started" if selected["entry"] <= current else "is upcoming"
        heading = "Next qualifying Long Best Wave for %s" % symbol_html
        lead = "%s %s and runs %s through %s." % (symbol_html, timing, start_label, end_label)
    else:
        heading = "Strongest qualifying weak window for %s" % symbol_html
        lead = "%s's Short Best Wave runs %s through %s." % (symbol_html, start_label, end_label)
    action_text = (
        "I am loading that exact chart."
        if spec is not None else
        "This account did not return the exact requested chart, so I have not claimed that it loaded."
    )
    reply = (
        "<b>%s</b><br>%s Across the exact %s-year Best Waves setting, average "
        "direction-adjusted return was %s, median was %s, and Sharpe Ratio was %.2f.<br><br>"
        "%s On desktop paid plans, open the <b>Best Waves</b> dropdown above the bar chart "
        "to see every qualifying wave for %s. If no wave passes the minimum criteria, the list "
        "is empty or hidden. This is historical timing research, not a recommendation to buy or short."
    ) % (
        heading,
        lead,
        years,
        _fmt_pct(selected["avg"]),
        _fmt_pct(selected["median"]),
        selected["sharpe"],
        action_text,
        symbol_html,
    )
    return {"reply": reply, "spec": spec}


def _append_market_switch(actions, target):
    """Queue a market-only set_view (switch the opp table to `target`) unless one is already queued."""
    if not any(a.get("type") == "set_view" and a.get("spec", {}).get("market") == target for a in actions):
        actions.append({"type": "set_view", "spec": {"market": target}})


# A deliberately small beginner ETF research universe. The seasonal data does
# not carry current prospectus metadata, so Tara must not call the full ETF
# market "safe": it can contain leveraged, inverse, single-stock, commodity,
# and other specialized products. These are conventional, unleveraged,
# diversified stock/bond index tickers used only as a transparent STARTING
# UNIVERSE; selection still depends solely on the historical seasonal screen.
_BEGINNER_ETF_RESEARCH_UNIVERSE = {
    "AGG", "BND", "DIA", "EFA", "IEMG", "IJH", "IWM", "SPY", "TIP",
    "VTI", "VT", "VXUS",
}


def _cards_from_result(out):
    cards = []
    if not isinstance(out, dict):
        return cards
    if isinstance(out.get("card"), dict):
        cards.append(out["card"])
    if out.get("symbol"):
        cards.append(out)
    for key in _LIST_KEYS:
        if isinstance(out.get(key), list):
            cards.extend(item for item in out[key] if isinstance(item, dict))
    unique = []
    seen = set()
    for card in cards:
        symbol = str(card.get("symbol") or "").upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        unique.append(card)
    return unique


def _filter_result_symbols(out, allowed):
    if not isinstance(out, dict):
        return out
    if out.get("symbol") and str(out.get("symbol") or "").upper() not in allowed:
        return {
            "cards": [],
            "note": "no candidates from the curated ETF research universe",
        }
    filtered = dict(out)
    for key in _LIST_KEYS:
        if isinstance(filtered.get(key), list):
            filtered[key] = [
                item for item in filtered[key]
                if isinstance(item, dict)
                and str(item.get("symbol") or "").upper() in allowed
            ]
    if isinstance(filtered.get("card"), dict):
        if str(filtered["card"].get("symbol") or "").upper() not in allowed:
            filtered.pop("card", None)
    return filtered


def _investor_screen_result(intent, user_id, opp_table, table_market,
                            user_token, opp_table_years):
    """Run one deterministic candidate screen for the investor funnel.

    The result is sourced from the same OppList4 rows as the visible table when
    possible. ETF discovery is filtered before ranking/limiting to the curated
    starter universe; it never silently promotes an arbitrary leveraged or
    inverse fund merely because its Sharpe happens to rank first.
    """
    target = "11" if intent in {"seasonal_etf", "weak_etf"} else "2"
    direction = "short" if intent in {"weak_etf", "weak_stock"} else "long"
    inp = {
        "markets": target,
        "direction": direction,
        "min_avg_return": 0,
        "limit": 5,
    }

    source_rows = None
    if table_market == target and opp_table:
        source_rows = list(opp_table)
    else:
        source_rows = _opplist4_rows(target, user_token, opp_table_years)
    if source_rows is not None and target == "11":
        source_rows = [
            row for row in source_rows
            if str((row or {}).get("symbol") or "").upper()
            in _BEGINNER_ETF_RESEARCH_UNIVERSE
        ]
    screen_rows = _filter_table_rows(source_rows, inp) if source_rows else []
    if screen_rows:
        return _rows_to_scan_cards(screen_rows, target), target

    # Loopback can be unavailable (for example no browser token). The gateway
    # scan remains a valid fallback for stocks. For ETFs, request a wider set
    # and then fail closed if none belong to the curated universe.
    gateway_inp = dict(inp)
    if target == "11":
        gateway_inp["limit"] = 20
    out = _briefify(run_tool("find_best_opportunities", gateway_inp, user_id))
    if target == "11":
        out = _filter_result_symbols(out, _BEGINNER_ETF_RESEARCH_UNIVERSE)
    return out, target


def _display_month_day(value):
    if not isinstance(value, str):
        return ""
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%d")
        return parsed.strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return value[:24]


def _pct(value):
    number = _numeric_stat(value, percent=True)
    return ("%+.1f%%" % number) if number is not None else None


def _investor_candidate_line(card, weak=False):
    symbol = re.sub(r"[^A-Z0-9.\-]", "", str(card.get("symbol") or "").upper())[:15]
    if not symbol:
        return None
    setup = card.get("setup") if isinstance(card.get("setup"), dict) else card
    stats = card.get("stats") if isinstance(card.get("stats"), dict) else card
    history = card.get("history") if isinstance(card.get("history"), dict) else {}
    pieces = []
    entry = _display_month_day(setup.get("entry_date")) if isinstance(setup, dict) else ""
    days = _card_days_out(card)
    if entry:
        pieces.append(("weak window near " if weak else "window near ") + entry)
    if days:
        pieces.append("%d-day study" % days)

    hs = _card_headline_stats(card)
    if hs:
        wins, years, _ = hs
        pieces.append(("underlying fell in %d of %d years" if weak else "profitable in %d of %d years")
                      % (wins, years))
    elif history.get("wins") is not None and history.get("years_tested"):
        pieces.append(("underlying fell in %d of %d years" if weak else "profitable in %d of %d years")
                      % (history["wins"], history["years_tested"]))

    avg = _numeric_stat(stats.get("avg_return_pct"), percent=True) if isinstance(stats, dict) else None
    if avg is not None:
        pieces.append(
            "underlying avg move %+.1f%%" % (-avg)
            if weak else "avg historical return %+.1f%%" % avg
        )
    sharpe = _card_sharpe(card)
    if sharpe is not None:
        pieces.append("Sharpe %.2f" % sharpe)

    worst = history.get("worst_year") if isinstance(history.get("worst_year"), dict) else None
    if not weak and worst and _pct(worst.get("return_pct")):
        pieces.append("worst close %s (%s)" % (_pct(worst.get("return_pct")), worst.get("year")))
    return "<b>%s</b> — %s." % (symbol, "; ".join(pieces) if pieces else "historical candidate")


def _investor_screen_response(intent, out, user_text):
    weak = intent in {"weak_etf", "weak_stock"}
    etf = intent in {"seasonal_etf", "weak_etf"}
    candidates = _cards_from_result(out)[:5]
    if not candidates:
        if etf:
            return (
                "I couldn't produce a curated ETF seasonal screen from the available data, so I "
                "won't substitute a specialized or leveraged fund. No candidate was selected; "
                "please try the ETF screen again when the market data is available."
            )
        return (
            "I couldn't retrieve a complete historical seasonal screen, so I won't choose or "
            "invent a candidate. I haven't changed the chart; please try the screen again."
        )

    if weak:
        heading = (
            "These are historical weak-period research candidates, not sell or short "
            "recommendations. The list is ranked by the strength of the short-direction "
            "seasonal record:"
        )
    else:
        universe = "curated broad, unleveraged ETF" if etf else "S&P 500 stock"
        heading = (
            "TradeWave's %s screen found these bullish historical seasonal research "
            "candidates, not personal recommendations:" % universe
        )
    lines = [line for line in (
        _investor_candidate_line(card, weak=weak) for card in candidates
    ) if line]
    footer = []
    if re.search(r"(?:\$\s*[\d,.]+|\bi\s+(?:have|got)\s+[\d,.]+)", user_text or "", re.I):
        footer.append("Your dollar amount was not used to rank the patterns or assign a position size.")
    if etf:
        footer.append(
            "The starter universe is intended to exclude leveraged, inverse, and single-stock "
            "ETFs, but TradeWave does not verify current fees, holdings, liquidity, or fund documents."
        )
    else:
        footer.append(
            "TradeWave does not check company fundamentals, valuation, breaking news, or portfolio fit."
        )
    footer.append(
        "The research advantage is a repeatable calendar-window test across completed years, "
        "rather than a financial-news headline or a forecast."
    )
    if not any(isinstance(card.get("history"), dict) and card.get("history") for card in candidates):
        footer.append(
            "This screening feed has average return and Sharpe; a symbol deep dive adds its winning "
            "and losing years before any decision."
        )
    footer.append(
        "Past patterns may not repeat. Name a candidate to inspect its full evidence, or ask for "
        "that ticker's historically weak window."
    )
    return heading + "<br>" + "<br>".join(lines) + "<br><br>" + " ".join(footer)


def _weak_symbol_response(symbol, out, actions, current_view=None):
    candidates = _cards_from_result(out)
    if not candidates:
        return (
            "I couldn't retrieve a verified weak-period study for <b>%s</b>, so I haven't "
            "changed the chart or inferred a losing window." % symbol
        )
    card = candidates[0]
    card_list = [card]
    spec = {
        "symbol": str(card.get("symbol") or symbol).upper(),
        "market": _card_market_id(card),
        "entry_date": _card_entry_date(card),
        "days_out": _card_days_out(card),
    }
    cleaned = _validate_view_spec(spec, current_view=current_view)
    if cleaned and _view_spec_is_grounded(cleaned, card_list, current_view=current_view):
        _queue_view_action(actions, cleaned)
    line = _investor_candidate_line(card, weak=True)
    return (
        (line or "<b>%s</b> weak-period study." % symbol)
        + " This identifies recurring historical weakness in the underlying; it is not a sell "
          "or short recommendation, and the pattern may not repeat."
    )


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
                       named_symbol_override=None, named_symbol_lookback=None,
                       current_view=None, view_intent=None, latest_user_text="",
                       non_actionable_symbols=None):
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
    card_count_before = len(card_list)
    if name == "update_view":                       # client-side UI action, not a gateway call
        if (
            target_symbol
            and isinstance(effective_named_lookback, int)
            and action_symbol == target_symbol
        ):
            inp = dict(inp)
            inp["years"] = effective_named_lookback
        cleaned = _validate_view_spec(inp, current_view=current_view)
        if view_intent == "forbid":
            return {
                "ok": False,
                "error": "the user negated or is diagnosing a view action; do not change the view",
            }
        if cleaned and _view_spec_is_grounded(
            cleaned, card_list, current_view=current_view
        ):
            _queue_view_action(actions, cleaned)
            return {
                "ok": True,
                "queued": cleaned,
                "status": "pending_client_confirmation",
                "instruction": (
                    "Do not say loaded, reloaded, already loaded, or done. "
                    "The browser will add completion text only after chart data loads."
                ),
            }
        return {
            "ok": False,
            "error": (
                "invalid or ungrounded view setup; a new/different symbol setup must "
                "exactly match symbol + market + entry_date + days_out from a successful "
                "read tool result in this turn"
            ),
        }

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
    if (
        name in {"analyze_symbol", "get_symbol_patterns"}
        and len(card_list) == card_count_before
        and _read_result_is_explicitly_non_actionable(out)
        and _user_mentions_symbol(latest_user_text, inp.get("symbol"))
        and isinstance(non_actionable_symbols, set)
    ):
        non_actionable_symbols.add(str(inp.get("symbol") or "").upper())
    return out


def run_chat_with_tools(messages, system, user_id, model, cache_ttl="5m",
                        opp_table=None, opp_table_market=None, user_token=None,
                        opp_table_years=None, full_history_request=None,
                        named_symbol_override=None, named_symbol_lookback=None,
                        viewer_entry_year=None, current_view=None, turn_id=None,
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
    investor_intent = classify_investor_intent(messages)
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

    suitability = loaded_pattern_suitability_response(latest_user_text, current_view)
    if suitability:
        trace(
            "loaded_pattern_suitability_boundary",
            symbol=str((current_view or {}).get("symbol") or "").upper(),
        )
        return suitability, []

    guidance = investor_guidance_response(investor_intent)
    if guidance:
        trace("investor_guidance", intent=investor_intent)
        return guidance, []

    if investor_intent in {"seasonal_etf", "seasonal_stock", "weak_etf", "weak_stock"}:
        out, target = _investor_screen_result(
            investor_intent,
            user_id,
            opp_table,
            table_market,
            user_token,
            opp_table_years,
        )
        found = bool(_cards_from_result(out))
        if found and table_market != target:
            _append_market_switch(actions, target)
        trace(
            "investor_evidence_screen",
            intent=investor_intent,
            market=target,
            candidates=len(_cards_from_result(out)),
        )
        return _investor_screen_response(investor_intent, out, latest_user_text), actions

    if investor_intent == "weak_symbol":
        symbol = _explicit_ticker(latest_user_text)
        out = _briefify(run_tool(
            "analyze_symbol",
            {"symbol": symbol, "direction": "short"},
            user_id,
        ))
        trace(
            "weak_period_study",
            symbol=symbol or "",
            ok=bool(_cards_from_result(out)),
        )
        return _weak_symbol_response(symbol or "that symbol", out, actions, current_view), actions

    if investor_intent == "exclusion_study":
        trace("exclusion_study_requires_validated_report")
        return (
            "I can explain a validated Date Range Exclusion Report, but this chat turn does not "
            "contain one. I won't compare unmatched windows or invent an exclusion result; create "
            "the report from the loaded range, then its Explain with Tara action will give me the "
            "same completed years for the excluded dates, remaining dates, and Buy & Hold."
        ), []

    if investor_intent == "named_security":
        system = system + (
            "\n\nNAMED INVESTMENT QUESTION OVERRIDE: The user selected a security and asked whether "
            "to buy, sell, hold, or invest in it. Analyze and load the exact historical seasonal "
            "evidence, but do NOT answer the suitability question yes or no. Start by saying "
            "TradeWave cannot determine whether the security fits this user, then state the "
            "historical setup, losing-year risk, and capability limits. Never tell them to buy, "
            "sell, hold, allocate an amount, or expect a return."
        )

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
            elif response_violates_investor_contract(candidate, investor_intent):
                reason = "personalized_investment_advice"
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
            out = _execute_tara_tool(
                name,
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
                current_view=current_view,
                view_intent=view_intent,
                latest_user_text=latest_user_text,
                non_actionable_symbols=non_actionable_symbols,
            )
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
        trace("protocol_violation", reason="incomplete_view_action")
        actions = []
        final_text = (
            "I couldn't send the complete chart action, so I haven't changed the chart. "
            "Please try that load again."
        )

    # If the model exhausted the loop after a valid action, preserve the action
    # with status-neutral prose. Otherwise fail closed.
    if not final_text:
        if actions:
            loaded = [
                action.get("spec", {}) for action in actions
                if action.get("type") == "set_view" and isinstance(action.get("spec"), dict)
            ]
            latest = loaded[-1] if loaded else {}
            symbol = str(latest.get("symbol") or "").upper()
            final_text = "<b>%s</b> chart request." % symbol if symbol else "Requested view change."
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
        trace("protocol_violation", reason="conflicting_view_actions")
        actions = []
        final_text = (
            "I couldn't resolve that into one unambiguous chart setup, so I haven't changed "
            "the chart. Please try again."
        )
    # Deterministic guard: guarantee the loaded pick is NAMED (symbol + lookback + stat), since
    # Haiku-4.5 intermittently returns a bare 'Loaded on the chart' with no symbol.
    _enforce_full_history_action(actions, full_history_request)
    _enforce_named_symbol_action(
        actions,
        cards,
        named_symbol_override,
        viewer_entry_year,
        preferred_years=named_symbol_lookback,
    )
    final_text = _ensure_load_named(
        final_text, actions, cards, card_list, current_view=current_view
    )
    if response_violates_investor_contract(final_text, investor_intent):
        log.warning(
            "tara response protocol violation turn=%s reason=unsafe_investor_response",
            turn_id or "-",
        )
        trace("protocol_violation", reason="unsafe_investor_response")
        evidence = _ensure_load_named(
            "", actions, cards, card_list, current_view=current_view
        ) if actions else ""
        final_text = (
            "TradeWave cannot determine whether this security is suitable for you. "
            + (("Historical evidence: " + evidence + " ") if evidence else "")
            + "This is historical research, not a forecast or personal recommendation."
        )
    final_text = _break_before_cta(final_text)   # closing CTA never runs onto the last list line
    if response_violates_view_contract(final_text, actions, current_view):
        trace("protocol_violation", reason="unsafe_final_response")
        if actions:
            final_text = _ensure_load_named(
                "", actions, cards, card_list, current_view=current_view
            )
            if not final_text:
                latest = actions[-1].get("spec", {})
                symbol = str(latest.get("symbol") or "").upper()
                final_text = "<b>%s</b> chart request." % symbol if symbol else "Requested view change."
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
                               viewer_entry_year=None, current_view=None,
                               turn_id=None, protocol_trace=None):
    """Run Tara's existing gateway tool loop through the OpenAI Responses API.

    Tool execution, result trimming, ViewSpec validation, table-screen interception, and
    deterministic narration guards are shared with the Anthropic path above.  Responses are
    stateless (``store:false`` in the adapter), so each round carries the prior output items and
    matching ``function_call_output`` items forward explicitly.
    """

    actions = []
    cards = {}
    card_list = []
    table_market = str(opp_table_market) if opp_table_market not in (None, "") else None
    final_text = None
    investor_intent = classify_investor_intent(messages)
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

    suitability = loaded_pattern_suitability_response(latest_user_text, current_view)
    if suitability:
        trace(
            "loaded_pattern_suitability_boundary",
            symbol=str((current_view or {}).get("symbol") or "").upper(),
        )
        return suitability, []

    guidance = investor_guidance_response(investor_intent)
    if guidance:
        trace("investor_guidance", intent=investor_intent)
        return guidance, []

    if investor_intent in {"seasonal_etf", "seasonal_stock", "weak_etf", "weak_stock"}:
        out, target = _investor_screen_result(
            investor_intent,
            user_id,
            opp_table,
            table_market,
            user_token,
            opp_table_years,
        )
        if _cards_from_result(out) and table_market != target:
            _append_market_switch(actions, target)
        trace(
            "investor_evidence_screen",
            intent=investor_intent,
            market=target,
            candidates=len(_cards_from_result(out)),
        )
        return _investor_screen_response(investor_intent, out, latest_user_text), actions

    if investor_intent == "weak_symbol":
        symbol = _explicit_ticker(latest_user_text)
        out = _briefify(run_tool(
            "analyze_symbol", {"symbol": symbol, "direction": "short"}, user_id
        ))
        trace("weak_period_study", symbol=symbol or "", ok=bool(_cards_from_result(out)))
        return _weak_symbol_response(symbol or "that symbol", out, actions, current_view), actions

    if investor_intent == "exclusion_study":
        trace("exclusion_study_requires_validated_report")
        return (
            "I can explain a validated Date Range Exclusion Report, but this chat turn does not "
            "contain one. I won't compare unmatched windows or invent an exclusion result; create "
            "the report from the loaded range, then its Explain with Tara action will give me the "
            "same completed years for the excluded dates, remaining dates, and Buy & Hold."
        ), []

    if investor_intent == "named_security":
        system = system + (
            "\n\nNAMED INVESTMENT QUESTION OVERRIDE: The user selected a security and asked whether "
            "to buy, sell, hold, or invest in it. Analyze and load the exact historical seasonal "
            "evidence, but do NOT answer the suitability question yes or no. Start by saying "
            "TradeWave cannot determine whether the security fits this user, then state the "
            "historical setup, losing-year risk, and capability limits. Never tell them to buy, "
            "sell, hold, allocate an amount, or expect a return."
        )

    input_items = build_responses_input(messages, system=system)
    cache_key = prompt_cache_key(user_id)

    for round_index in range(_MAX_TOOL_ROUNDS):
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
                    current_view=current_view,
                    view_intent=view_intent,
                    latest_user_text=latest_user_text,
                    non_actionable_symbols=non_actionable_symbols,
                )
            except OpenAIAPIError:
                # Feed a bounded, narration-safe error back to the model rather than executing
                # malformed arguments. Provider/API failures still propagate for Haiku fallback.
                out = {"ok": False, "error": "invalid tool arguments"}
            trace(
                "tool_result",
                round=round_index + 1,
                tool=str(call.get("name") or ""),
                ok=not (isinstance(out, dict) and bool(out.get("error"))),
                queued=bool(
                    call.get("name") == "update_view"
                    and isinstance(out, dict)
                    and out.get("ok")
                ),
            )
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
        trace("protocol_violation", reason="incomplete_view_action")
        actions = []
        final_text = (
            "I couldn't send the complete chart action, so I haven't changed the chart. "
            "Please try that load again."
        )
    if _view_actions_conflict(actions):
        trace("protocol_violation", reason="conflicting_view_actions")
        actions = []
        final_text = (
            "I couldn't resolve that into one unambiguous chart setup, so I haven't changed "
            "the chart. Please try again."
        )

    _enforce_full_history_action(actions, full_history_request)
    _enforce_named_symbol_action(
        actions,
        cards,
        named_symbol_override,
        viewer_entry_year,
        preferred_years=named_symbol_lookback,
    )
    final_text = _ensure_load_named(
        final_text, actions, cards, card_list, current_view=current_view
    )
    if response_violates_investor_contract(final_text, investor_intent):
        trace("protocol_violation", reason="unsafe_investor_response")
        evidence = _ensure_load_named(
            "", actions, cards, card_list, current_view=current_view
        ) if actions else ""
        final_text = (
            "TradeWave cannot determine whether this security is suitable for you. "
            + (("Historical evidence: " + evidence + " ") if evidence else "")
            + "This is historical research, not a forecast or personal recommendation."
        )
    final_text = _break_before_cta(final_text)
    if response_violates_view_contract(final_text, actions, current_view):
        trace("protocol_violation", reason="unsafe_final_response")
        if actions:
            final_text = _ensure_load_named(
                "", actions, cards, card_list, current_view=current_view
            )
            if not final_text:
                latest = actions[-1].get("spec", {})
                symbol = str(latest.get("symbol") or "").upper()
                final_text = "<b>%s</b> chart request." % symbol if symbol else "Requested view change."
        else:
            final_text = (
                "I couldn't complete that chart request safely, so I haven't changed the chart. "
                "Please try again."
            )
    return final_text, actions
