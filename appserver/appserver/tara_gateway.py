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
            "says show me / load / pull up / open / change the years / switch to the PE cycle, "
            "asks to show/hide the MFE or MAE overlays, or asks to show the Trend Chart, "
            "Wave Stats, or Price Chart in the lower carousel. It can also show or hide the global "
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
_VS_MARKETS = {str(i) for i in range(17) if i not in (14, 15)}   # 14/15 (Korea) removed; never renumber
_VS_PE = {"consecutive": "cons", "cons": "cons", "pe0": "pe0", "pe1": "pe1", "pe2": "pe2", "pe3": "pe3"}
_VS_BOTTOM_SLIDES = {"trend_chart", "wave_stats", "price_chart"}


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
    for field in ("show_mfe", "show_mae", "show_tooltips"):
        value = spec.get(field)
        if isinstance(value, bool):
            out[field] = value
    bottom_slide = spec.get("bottom_slide")
    if isinstance(bottom_slide, str) and bottom_slide in _VS_BOTTOM_SLIDES:
        out["bottom_slide"] = bottom_slide
    return out


def _text_of(blocks):
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


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
_RPL_WIN_RE  = re.compile(r'(\d+)\s*(?:of|/)\s*(?:the\s*last\s*)?(\d+)\s*year', re.I)  # context-anchored (a conflict)
_RPL_FRAC_RE = re.compile(r'(\d+)\s*(?:of(?:\s*the\s*last)?|/)\s*(\d+)', re.I)         # lenient (counts as present)
_RPL_PCT_RE  = re.compile(r'(\d{1,3})\s*%\s*win', re.I)


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


def _card_entry_date(c):
    s = c.get("setup") if isinstance(c, dict) and isinstance(c.get("setup"), dict) else c
    return s.get("entry_date") if isinstance(s, dict) else None


def _announce_line(sym, card):
    """Compose a compliant one-line load announcement for the LOADED setup: symbol + lookback + the
    key historical stat, from the card HEADLINE (authoritative), falling back to the stats fields.
    Past-record framing only ('won X of the last N years') - never a forward claim."""
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
    stat = ", ".join(parts) if parts else (card.get("headline") or "the pattern")
    based = (" based on the last %d years" % n) if n else ""
    dirtxt = (" " + direction) if direction else ""
    return "<b>%s</b>%s%s: %s. Loaded on the chart." % (sym, dirtxt, based, stat)


def _stat_conflicts(text, wins, yrs):
    """True when the reply asserts a win rate that CONTRADICTS the loaded setup's real record and
    never states the correct one (a stale/fabricated stat, e.g. 'won 10 of 10' for a 4/10 setup).
    The correct record in ANY form (lenient) suppresses the flag, so a comparison that also cites
    other symbols' rates is left alone; only context-anchored ('... years' / '...% win') wrong claims
    count as conflicts, so dates/ratios don't false-trigger."""
    text = text or ""
    # PRESENT (lenient): the correct record stated anywhere -> trust the reply, never clobber.
    for m in _RPL_FRAC_RE.finditer(text):
        if (int(m.group(1)), int(m.group(2))) == (wins, yrs):
            return False
    for m in _RPL_PCT_RE.finditer(text):
        if yrs and round(int(m.group(1)) / 100.0 * yrs) == wins:
            return False
    # CONFLICT (context-anchored): a win-rate claim that is NOT the correct record.
    for m in _RPL_WIN_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if (b == yrs and a != wins) or a == b:   # same lookback / different count, or a perfect 'N of N' claim
            return True
    for m in _RPL_PCT_RE.finditer(text):
        if yrs and round(int(m.group(1)) / 100.0 * yrs) != wins:
            return True
    return False


def _ensure_load_named(text, actions, cards, card_list):
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
    entry = spec.get("entry_date")
    # Match the card to the LOADED setup (by entry_date) so an earlier same-symbol card can't leak
    # its stats; fall back to the latest card seen for the symbol.
    card = None
    if entry:
        for c in card_list:
            if str(c.get("symbol", "")).upper() == sym and _card_entry_date(c) == entry:
                card = c
    if card is None:
        card = cards.get(sym)
    if not card:
        return text
    hs = _card_headline_stats(card)
    if hs and _stat_conflicts(text, hs[0], hs[1]):
        # the reply states a win rate that is NOT this loaded setup's record -> replace with truth
        fixed = _announce_line(sym, card)
        dm = re.search(r'<i>.*?</i>', text, re.S)          # preserve a disclaimer if the model added one
        return fixed + ("<br><br>" + dm.group(0) if dm else "")
    if sym in text.upper():
        return text
    line = _announce_line(sym, card)
    if text.strip():
        # the model wrote its own confirmation; drop our trailing "Loaded on the chart." to avoid a double
        return line.replace(" Loaded on the chart.", "") + "<br><br>" + text
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


def _append_market_switch(actions, target):
    """Queue a market-only set_view (switch the opp table to `target`) unless one is already queued."""
    if not any(a.get("type") == "set_view" and a.get("spec", {}).get("market") == target for a in actions):
        actions.append({"type": "set_view", "spec": {"market": target}})


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
                        opp_table_years=None, full_history_request=None,
                        named_symbol_override=None, named_symbol_lookback=None,
                        viewer_entry_year=None):
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
    for _ in range(_MAX_TOOL_ROUNDS):
        resp = send_claude_messages(convo, model=model, system=system,
                                    cache_system=True, cache_ttl=cache_ttl,
                                    tools=TOOLS, return_raw=True)
        blocks = resp.get("content", []) or []
        if resp.get("stop_reason") != "tool_use":
            final_text = _text_of(blocks)
            break
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
            )
            results.append({
                "type": "tool_result",
                "tool_use_id": b.get("id"),
                "content": _bounded_json(out),
            })
        convo.append({"role": "user", "content": results})
    # If we broke out with the model's final text, use it; else force a final no-tool answer.
    # (empty string counts as missing - a content-filtered/truncated response otherwise
    # flows through as a blank chat bubble)
    if not final_text:
        final_text = send_claude_messages(convo, model=model, system=system,
                                          cache_system=True, cache_ttl=cache_ttl)
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
    final_text = _ensure_load_named(final_text, actions, cards, card_list)
    final_text = _break_before_cta(final_text)   # closing CTA never runs onto the last list line
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
