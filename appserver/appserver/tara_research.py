"""Deterministic, engine-grounded answers for Tara research requests (TW-TASK-0030).

Five request classes are answered here before any model routing, because each maps to
exact TradeWave engine output and a model narration kept collapsing them:

  1. index screens          "find S&P 500 stocks entering bearish patterns this week"
  2. ranked screens         "which S&P 500 stocks have the highest win rate, next 10 days"
  3. symbol window studies  "analyze Apple from now to year end over the last 20 years"
  4. symbol comparisons     "compare technology and utilities ETFs for the 4th quarter"
  5. excursion dates        "what's the latest date the 100-Year Pattern has bottomed"

Calculation authority: every statistic printed here is read from the appserver engine
(OppList4 detection rows and ChartData4 stats/rows) through the caller's own token, so
plan entitlements apply unchanged. This module only parses the request, selects and
orders engine values, and formats them. It never derives a return, win rate or Sharpe.
"""

from __future__ import annotations

import calendar
import datetime
import html
import json
import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import tara_gateway as tg
from featured_patterns import (
    HUNDRED_YEAR_DISPLAY_DAYS,
    hundred_year_view_spec,
    hundred_year_years_value,
)
from tw_dateformat import format_date_range

log = logging.getLogger("tara_research")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FANOUT_WORKERS = 3          # per process; four gunicorn processes share one 16-slot pool
_MAX_TIERS = 6               # win-rate bands read for one message, within the read budget
_MAX_ENGINE_CALLS = 40       # detector tables + verification studies for one message
_MAX_SCREEN_DAYS = 31
_DEFAULT_LOOKBACK = 10
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 15
_MAX_COMPARE = 6
_DEFAULT_COMPARE_DAYS = 30   # window used when a comparison names no dates

# Intents this module may answer. Suitability/guidance intents keep their own funnel.
_ALLOWED_INVESTOR_INTENTS = {
    None, "", "seasonal_stock", "seasonal_etf", "seasonal_current", "weak_stock",
    "weak_etf", "weak_symbol",
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NUM = r"(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")"

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)


def _int(value):
    text = str(value or "").strip().lower()
    if text in _NUMBER_WORDS:
        return _NUMBER_WORDS[text]
    try:
        return int(text)
    except ValueError:
        return None


def _esc(value):
    return html.escape(str(value if value is not None else ""))


def _day_label(day, weekday=False):
    label = "%s %d" % (day.strftime("%b"), day.day)
    return (day.strftime("%a") + " " + label) if weekday else label


def _long_date(day):
    return "%s %d, %d" % (day.strftime("%b"), day.day, day.year)


# ---------------------------------------------------------------------------
# Engine access (loopback as the signed-in user). Tests replace these two seams.
# ---------------------------------------------------------------------------

def _engine_opplist(market, day, year1, year2, day_range, token):
    """One OppList4 detection table. Returns (status, rows) with rows None on failure."""

    path = "/OppList4/%s/%s/%s/%s/%s/%s/0/0" % (
        quote(str(market)), day.strftime("%B"), day.day, int(year1), int(year2),
        quote(str(day_range), safe="-"),
    )
    status, payload = tg._loopback_json(
        path, token, params={"mode": "consecutive"}, timeout=(5, 30)
    )
    rows = payload.get("OppList") if isinstance(payload, dict) else None
    if isinstance(rows, str) and rows.startswith("-1:"):
        return status, []          # documented "no detector file for this band"
    return status, rows if isinstance(rows, list) else None


def _engine_chart(market, symbol, entry_date, days_out, years_value, token, **params):
    """One ChartData4 study. ``days_out`` is the inclusive display count."""

    path = "/ChartData4/%s/%s/%s/%s/%s" % (
        quote(str(market)), quote(str(entry_date)), quote(str(symbol).upper()),
        int(days_out) - 1, quote(str(years_value)),
    )
    return tg._loopback_json(path, token, params=params or None, timeout=(5, 30))


def _engine_symbol_names(market, token):
    status, payload = tg._loopback_json(
        "/GetListSymbols/%s" % quote(str(market)), token, timeout=(5, 15)
    )
    names = payload.get("AllowedSymbols") if status == 200 and payload else None
    return names if isinstance(names, dict) else None


_ENGINE_SLOTS = threading.BoundedSemaphore(_FANOUT_WORKERS)


def _parallel(function, items):
    """Run engine reads a few at a time. The semaphore is process-wide, so concurrent chat
    turns in one worker share the same small number of loopback slots."""

    items = list(items)
    if not items:
        return []

    def guarded(item):
        with _ENGINE_SLOTS:
            return function(item)

    with ThreadPoolExecutor(max_workers=min(_FANOUT_WORKERS, len(items))) as pool:
        return list(pool.map(guarded, items))


_BANDS_CACHE = None


def _band_floor(market, year1):
    """Minimum winning years the detector precomputes for this market and lookback."""

    global _BANDS_CACHE
    if _BANDS_CACHE is None:
        try:
            with open(_REPO_ROOT / "apiserver" / "market_bands.json") as handle:
                _BANDS_CACHE = json.load(handle).get("scan") or {}
        except (OSError, ValueError):
            log.warning("market_bands.json unavailable; using the 90%% default band")
            _BANDS_CACHE = {}
    floor = (_BANDS_CACHE.get(str(market)) or {}).get(str(int(year1)))
    if isinstance(floor, int) and 1 <= floor <= int(year1):
        return floor
    if _BANDS_CACHE.get(str(market)):
        return None                 # lookback not precomputed for this market
    return max(1, min(int(year1), round(0.9 * int(year1))))


def _band_lookbacks(market):
    return sorted(int(key) for key in (_BANDS_CACHE or {}).get(str(market), {}))


# ---------------------------------------------------------------------------
# Shared request parsing
# ---------------------------------------------------------------------------

_UNIVERSES = (
    (re.compile(r"\b(?:s\s*&\s*p|s\s+and\s+p|sp)\s*-?\s*500\b|\bs\s*&\s*p\b", re.I), "2", "S&P 500"),
    (re.compile(r"\bnasdaq(?:\s*-?\s*100)?\b|\bndx\s+stocks\b", re.I), "1", "NASDAQ 100"),
    (re.compile(r"\bdow(?:\s+jones)?(?:\s*-?\s*30)?\b|\bdjia\b|\bdj\s*30\b", re.I), "0", "Dow 30"),
    (re.compile(r"\brussell\s*-?\s*1000\b", re.I), "3", "Russell 1000"),
    (re.compile(r"\bwilshire(?:\s*-?\s*[56]000)?\b", re.I), "4", "Wilshire 5000"),
    (re.compile(r"\betfs?\b|\bexchange[-\s]traded\s+funds?\b", re.I), "11", "ETF"),
    (re.compile(r"\b(?:futures|commodit(?:y|ies))\b", re.I), "7", "Futures & Commodities"),
    (re.compile(r"\bcrypto(?:currenc(?:y|ies))?\b", re.I), "16", "Crypto"),
)

_SCREEN_SHAPE_RE = re.compile(
    r"\b(?:which|what|find|show|list|rank|screen|scan|give|top|best|strongest|highest|"
    r"any|are\s+there|look\s+(?:in|for))\b", re.I)
_SCREEN_NOUN_RE = re.compile(
    r"\b(?:stocks|names|tickers|symbols|securities|companies|patterns|setups|"
    r"opportunit(?:y|ies)|windows|trades|etfs|funds|shorts|longs|candidates|ideas)\b", re.I)
# "short"/"long" used about time or list length, not trade direction.
_DIRECTION_NOISE_RE = re.compile(
    r"\bshort[-\s]?list(?:s|ed)?\b|\b(?:short|long)(?:er|est)?[-\s]+"
    r"(?:term|dated|run|list|hold\w*|holding|window|duration|period|time|history|look[-\s]?back)\b|"
    r"\b(?:short|long)\s+(?:\w+\s+)?(?:hold\w*|holding\s+periods?)\b|\bas\s+long\s+as\b|\bhow\s+long\b",
    re.I)
_BEAR_EXPLICIT_RE = re.compile(r"\b(?:bearish|short(?:s|ing|[-\s]side|[-\s]direction)?)\b", re.I)
_BULL_EXPLICIT_RE = re.compile(r"\b(?:bullish|long(?:s|[-\s]side|[-\s]direction)?)\b", re.I)
_BEAR_SOFT_RE = re.compile(
    r"\b(?:weak(?:est|ness)?|declin\w+|sell[-\s]?offs?|downside|falls|fell|falling|drops|dropping|"
    r"go(?:es|ing)?\s+down|went\s+down|los(?:e|es|ing)\s+(?:value|ground|money)|"
    r"negative\s+(?:seasonal\s+|historical\s+|average\s+)*(?:returns?|performance|bias|seasonality)|"
    r"under[-\s]?perform\w*|sink(?:s|ing)?|sank|slid(?:e|es|ing)?|tank(?:s|ed|ing)?|slump\w*|"
    r"plung\w+|tumbl\w+|sell\s+candidates?|"
    r"(?:historically|tend(?:s)?\s+to|usually|typically|often|generally)\s+(?:fall|drop|decline))\b",
    re.I)
# Wording that may well mean "bearish" but is not specific enough to pick a side: the screen
# is left to the normal path unless the text also says bullish or bearish outright.
_VAGUE_BEAR_RE = re.compile(
    r"\b(?:worst|bad|poor(?:ly|est)?|lag(?:s|ging|gards?)?|down|lower|red|crash\w*|dip(?:s|ping)?|"
    r"struggl\w+|hurt|pain|danger\w*|risk(?:y|iest)|avoid\w*|stay\s+away|losers?|losing|loss(?:es)?|"
    r"sell|selling|pullbacks?|corrections?|drawdowns?|trouble|vulnerable)\b", re.I)
_BULL_SOFT_RE = re.compile(
    r"\b(?:rise|rises|rising|rose|rally|rallies|strong(?:est|er)?|upside|gains?|go(?:es)?\s+up)\b", re.I)
_BARE_FALL_RE = re.compile(r"\b(?:fall|drop|decline)\b", re.I)
_NEGATED_DIRECTION_RE = re.compile(
    r"(?:\b(?:not|no|non|never|none|nothing|neither|without|exclud\w+|except|rarely|seldom|least|"
    r"instead\s+of|rather\s+than|other\s+than)\b|n't\b)[-\s]+(?:\w+\s+){0,2}?"
    r"(?:bearish|bullish|shorts?|shorting|longs?|weak\w*|strong\w*|fall\w*|drop\w*|declin\w+|"
    r"ris(?:e|es|ing)|gains?)\b", re.I)
_INVERSE_RANK_RE = re.compile(
    r"\b(?:lowest|worst|least|fewest|smallest|weakest|poorest|bottom\s+%s)\b[^.;,]{0,30}"
    r"\b(?:win|sharpe|sr|returns?|profits?|gains?|rates?|avg|average|record|patterns?|setups?)\b"
    % _NUM, re.I)
_RANK_WIN_RE = re.compile(
    r"\b(?:win[-\s]*rates?|winning\s+(?:rate|percentage|years)|percent\s+profitable|"
    r"most\s+(?:consistent|reliable)|highest\s+probabilit\w+|most\s+often)\b", re.I)
_RANK_SHARPE_RE = re.compile(r"\b(?:sharpe|sr)\b", re.I)
_RANK_AVG_RE = re.compile(
    r"\b(?:avg\s*p?|average)\s*(?:return|profit|gain)s?\b|\bavgp\b|"
    r"\b(?:biggest|largest|highest)\s+(?:average\s+)?(?:gains?|returns?|profits?)\b", re.I)
_OFF_TOPIC_SCREEN_RE = re.compile(
    r"\b(?:earnings?|dividends?|volume|news|market\s+cap|valuation|p\s*/\s*e\b|revenue|"
    r"price\s+targets?|analysts?|upgrades?|downgrades?|52[-\s]week|rsi|macd|moving\s+averages?|"
    r"options?|iv\b|implied\s+volatility|watchlists?|ai\s+(?:score|win|probabilit)\w*|"
    r"ais|predr|pmfe)\b", re.I)
_SEASONAL_SCREEN_CUE_RE = re.compile(
    r"\b(?:seasonal\w*|patterns?|windows?|setups?|opportunit(?:y|ies)|win[-\s]*rates?|winrate|"
    r"sharpe|sr|bullish|bearish|shorts?|longs?|historical(?:ly)?|tend(?:s|ency)?|avg\s*p?|"
    r"average\s+(?:return|profit|gain)|hold(?:s|ing)?|rise|fall|won|winners?|"
    r"\d+\s+(?:out\s+)?of\s+\d+\s+years)\b", re.I)
_ADVICE_RE = re.compile(
    r"\b(?:should|shall|could|can|would|do|must)\s+(?:i|we)\s+(?:\w+\s+){0,2}?"
    r"(?:buy|sell|short|avoid|trade|invest|hold|own|pick|get\s+(?:in|out))\b|"
    r"\bwhat\s+(?:\w+\s+){0,2}?to\s+(?:buy|sell|short|avoid)\b|"
    r"\b(?:is\s+it|it\s+is|it's)\s+(?:better|best|smart|wise|safe|good)\s+to\s+(?:buy|sell|short|hold)\b|"
    r"\bworth\s+(?:buying|selling|shorting)\b|\bgood\s+(?:buy|investment)\b", re.I)
_ADVICE_BOUNDARY = (
    "TradeWave cannot tell you what to buy, sell, short or avoid. Here is the historical "
    "seasonal research instead.")
_CYCLE_WORD_RE = re.compile(
    r"\b(?:mid[-\s]?terms?|(?:pre|post)[-\s]?election|election\s+(?:years?|cycle)|"
    r"presidential\s+(?:cycle|years?)|pe\s*\+?\s*[0-3])\b", re.I)
_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
_TICKER_STOPWORDS = {
    # analytics vocabulary and index names
    "AI", "AIS", "AVG", "AVGP", "DJIA", "DOW", "ETF", "ETFS", "FOMC", "MAE", "MFE", "ML",
    "NASDAQ", "NDX", "PE", "Q1", "Q2", "Q3", "Q4", "SP", "SR", "TOP", "US", "USA", "YTD",
    "II", "OK", "TARA", "SPX", "VS", "U.S", "MIN", "MAX", "EOY", "PE0", "PE1", "PE2", "PE3",
    "TWR", "TWA", "EOD", "ROI", "CEO", "IPO", "ATH", "EPS", "GDP", "CPI", "FED", "SEC", "API",
    "MCP", "FAQ", "PDF", "CSV", "UI", "TV", "UK", "EU", "AM", "PM", "ET", "EST", "PST", "UTC",
    "TW", "TW2", "NYSE", "OTC", "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    # ordinary English words that are also listed tickers
    "A", "AN", "ALL", "AND", "ANY", "ARE", "AS", "AT", "BE", "BEST", "BIG", "BUT", "BUY",
    "BY", "CAN", "CASH", "DAY", "DO", "EAT", "FAST", "FIND", "FOR", "FROM", "FUN", "GO",
    "GOOD", "HAS", "HE", "HELP", "HEY", "HI", "HIGH", "HOLD", "HOW", "I", "IF", "IN", "IS",
    "IT", "KEY", "LAST", "LIFE", "LIST", "LONG", "LOVE", "LOW", "ME", "MY", "NEW", "NEXT",
    "NO", "NOT", "NOW", "OF", "ON", "ONE", "OPEN", "OR", "OUT", "OVER", "PLAY", "PLEASE",
    "RANK", "RATE", "REAL", "RUN", "SEE", "SELL", "SHORT", "SHOW", "SO", "STOCK", "STOCKS",
    "THAT", "THE", "THIS", "TO", "TODAY", "TRUE", "TWO", "UP", "WAS", "WE", "WEEK", "WELL",
    "WHAT", "WHEN", "WHO", "WHY", "WIN", "WITH", "YEAR", "YEARS", "YES", "YOU", "MARKET",
    "INDEX", "MONTH",
}


def _mask(text, start, end):
    return text[:start] + " " * (end - start) + text[end:]


def _currency_pairs(text):
    """Currency pairs written EUR/USD, EUR-USD, eurusd. Returns (pairs, text with them masked)."""

    pairs, masked = [], text
    pattern = re.compile(r"(?<![A-Za-z])([A-Za-z]{3})\s?[/\-]?\s?([A-Za-z]{3})(?![A-Za-z])")
    position = 0
    while True:
        match = pattern.search(text, position)
        if not match:
            break
        base, quote_ccy = match.group(1).upper(), match.group(2).upper()
        if base in _CURRENCIES and quote_ccy in _CURRENCIES and base != quote_ccy:
            pairs.append((match.start(), base + quote_ccy))
            masked = _mask(masked, match.start(), match.end())
            position = match.end()
        else:
            position = match.start() + 1
    return pairs, masked


def _universe(text):
    hits = [(m.start(), market, label) for pattern, market, label in _UNIVERSES
            for m in [pattern.search(text)] if m]
    if not hits:
        if re.search(r"\b(?:all|every)\s+u\.?s\.?\s+(?:equit(?:y|ies)|stocks)\b", text, re.I):
            return "4", "Wilshire 5000"
        return None
    # A named index outranks the generic word "ETF"/"futures" in the same sentence.
    index_hits = [hit for hit in hits if hit[1] in {"0", "1", "2", "3", "4"}]
    chosen = min(index_hits or hits)
    return chosen[1], chosen[2]


def _explicit_tickers(text, allow_single=False):
    """Upper-case ticker tokens the user typed.

    One-letter tickers (F, T, V) are read only when ``allow_single`` is set, which the
    comparison path does because "compare F and GM" names two securities.

    An ordinary English word in capitals (IT, ALL, NOW) counts only when it is marked as a
    security: a leading ``$`` or a following "stock"/"shares"/"ticker". Currency pairs and
    index names are handled by their own parsers and never read as two tickers.
    """

    _pairs, masked = _currency_pairs(text)
    for pattern, _market, _label in _UNIVERSES:
        masked = pattern.sub(lambda m: " " * len(m.group(0)), masked)
    letters = [ch for ch in masked if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.7:
        return []
    found = []
    for match in re.finditer(
            r"(?<![A-Za-z0-9.&\-])(\$?)([A-Z][A-Z0-9.\-]{0,9})(?![A-Za-z0-9&\-])", masked):
        token = match.group(2).rstrip(".-")
        marked = bool(match.group(1)) or bool(re.match(
            r"\s+(?:stock|shares|ticker|symbol)\b", masked[match.end():], re.I))
        if len(token) < 2 and not marked and not (allow_single and token not in {"A", "I"}):
            continue
        if token in _TICKER_STOPWORDS and not marked:
            continue
        if token not in found:
            found.append(token)
    return found


def _direction(text):
    """'long', 'short', or None when the wording is negated or names both sides."""

    cleaned = _DIRECTION_NOISE_RE.sub(" ", text)
    if _NEGATED_DIRECTION_RE.search(cleaned):
        return None
    bear, bull = bool(_BEAR_EXPLICIT_RE.search(cleaned)), bool(_BULL_EXPLICIT_RE.search(cleaned))
    if bear and bull:
        return None
    if bull:
        return None if _BEAR_SOFT_RE.search(cleaned) else "long"
    if bear:
        return "short"
    soft_bear, soft_bull = bool(_BEAR_SOFT_RE.search(cleaned)), bool(_BULL_SOFT_RE.search(cleaned))
    if soft_bear and soft_bull:
        return None
    if soft_bear:
        return "short"
    if _BARE_FALL_RE.search(cleaned):
        return None                  # "this fall", "drop the least": not a direction request
    if _VAGUE_BEAR_RE.search(cleaned):
        return None                  # never default a possibly-bearish question to a bullish list
    return "long"


def _lookback_years(text):
    """The lookback the user asked for, in any of the ways people write it.

    "over the last 15 years", "15-year lookback", "13 of 15 years", "min 13 of 15",
    "15y" / "15 yrs", "use 20 years", "with a 20 year history".
    """
    for pattern in (
        r"\b(?:last|past|previous|prior|over)\s+(?:the\s+)?(?:last\s+|past\s+)?(\d{1,2})\s*(?:-|\s)?(?:consecutive\s+)?years?\b",
        r"\b(\d{1,2})\s*(?:-|\s)?years?\s+(?:view|look[-\s]?back|history|window|seasonal|trend|record|of\s+history)\b",
        r"\b(\d{1,2})\s+of\s+(\d{1,2})\s+years\b",
        r"\b(?:min(?:imum)?|at\s+least|won|winning|wins?|winners?)\b[^.;]{0,25}?"
        r"\b(\d{1,2})\s*(?:of|out\s+of|/)\s*(\d{1,2})\b",
        r"(?<![A-Za-z0-9.$])(\d{1,2})\s?(?:y|yr|yrs)\b(?!\s*old)",
        r"\b(?:use|using|with|on|at|across)\s+(?:a\s+|the\s+)?(\d{1,2})[-\s]?years?\b",
        r"\b(\d{1,2})[-\s]years?\s+(?:of\s+)?(?:data|sample|period|stats?|statistics|results?|average|avg)\b",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            value = int(match.group(match.lastindex))
            if 1 <= value <= 99:
                return value
    return None


def _names_several_cycles(text):
    """True when one request contrasts election-cycle cohorts (a different study shape)."""

    qualified = (r"\bmid[-\s]?terms?(?:\s+election)?(?:\s+years?)?", r"\bpre[-\s]?election(?:\s+years?)?",
                 r"\bpost[-\s]?election(?:\s+years?)?")
    hits = sum(bool(re.search(pattern, text, re.I)) for pattern in qualified)
    rest = text
    for pattern in qualified:
        rest = re.sub(pattern, " ", rest, flags=re.I)
    hits += bool(re.search(r"\b(?:presidential\s+)?election\s+years?\b", rest, re.I))
    return hits > 1


def _pe_cycle(text):
    if re.search(r"\bmid[-\s]?term", text, re.I) or re.search(r"\bpe\s*\+\s*2\b", text, re.I):
        return "pe2"
    if re.search(r"\bpre[-\s]?election", text, re.I) or re.search(r"\bpe\s*\+\s*3\b", text, re.I):
        return "pe3"
    if re.search(r"\bpost[-\s]?election", text, re.I) or re.search(r"\bpe\s*\+\s*1\b", text, re.I):
        return "pe1"
    if re.search(r"\b(?:presidential\s+)?election\s+years?\b", text, re.I):
        return "pe0"
    return "cons"


def _plan(token, market):
    """Plan limits the engine will apply to this caller on this market.

    Read from the token's own claims and config (the engine enforces them regardless); used
    only so a plan-limited result is described as plan-limited instead of as "none found".
    """

    try:
        import jwt
        claims = jwt.decode(str(token), options={"verify_signature": False})
    except Exception:
        return {"years_cap": None, "row_cap": None, "date_locked": False}
    if claims.get("is_admin") or claims.get("is_service_account"):
        return {"years_cap": None, "row_cap": None, "date_locked": False}
    level = str(claims.get("user_level", ""))
    config = tg.config
    free = str(market) in getattr(config, "level_access_hierarchy_free_registered", {}).get(level, [])
    row_cap = None
    if level == "1" or free:
        row_cap = getattr(config, "max_opportunities_loggedin_free", None)
    return {"years_cap": getattr(config, "num_years_allowed_by_level", {}).get(level),
            "row_cap": row_cap, "date_locked": free}


# ---------------------------------------------------------------------------
# 1 + 2. Index screens
# ---------------------------------------------------------------------------

_WINDOW_PATTERNS = (
    ("ahead", r"\b(?:(?:with)?in|over|during|for)?\s*(?:the\s+)?(?:next|coming|following)\s+%s\s*"
              r"(calendar\s+|trading\s+|business\s+)?(day|week|month)s?\b" % _NUM),
    ("next_week", r"\bnext\s+week\b"),
    ("this_week", r"\b(?:this|htis|tihs|ths|the\s+current|the\s+coming)\s+week\b"),
    ("next_month", r"\bnext\s+month\b"),
    ("this_month", r"\b(?:this|the\s+current)\s+month\b"),
    ("tomorrow", r"\b(?:(?:today|\w+)\s+or\s+)?tomorrow(?:\s+or\s+(?:the\s+)?day\s+\w+\s+tomorrow)?\b"),
    ("today", r"\b(?:today|right\s+now|now|currently|at\s+the\s+moment|"
              r"this\s+time\s+of\s+(?:the\s+)?year)\b"),
)
_UNPARSED_DATE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|"
    r"\b(?:in|during|for|by|until|till|through|starting|from|on|of)\s+may\b|\bmay\s+\d{1,2}\b|"
    r"\b(?:(?:first|1st|second|2nd|third|3rd|fourth|4th|this|next|last)\s+quarter|q[1-4])\b|"
    r"\b(?:19|20)\d{2}\b|\b(?:spring|summer|autumn|winter)\b|\b(?:this|the|next|last|in|for)\s+fall\b|"
    r"\byear[-\s]?end\b|\bend\s+of\s+(?:the\s+)?(?:year|month|week)\b|\b\d{1,2}/\d{1,2}\b|"
    r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b|\b(?:christmas|thanksgiving|holidays?|"
    r"black\s+friday|new\s+year'?s?|easter|halloween|santa)\b|\blast\s+(?:week|month)\b|\byesterday\b",
    re.I)


# Index names carry numbers that are not calendar years (Russell 2000).
_INDEX_NUMBER_RE = re.compile(
    r"\b(?:russell|wilshire|s\s*&\s*p|sp|nasdaq|dow(?:\s+jones)?|ftse|nikkei|stoxx|tsx)\s*-?\s*\d{2,4}\b",
    re.I)


def _add_weekdays(day, count):
    while count > 1:
        day += datetime.timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def _entry_window(text, today):
    """Resolve a screen's ENTRY-date window: (first, last, label, note), or None.

    None means the text names a date this parser did not consume, so the screen must not
    silently answer for today.
    """

    lower = text.lower()
    week_start = today - datetime.timedelta(days=today.weekday())
    kind = match = None
    for name, pattern in _WINDOW_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            kind = name
            break
    rest = _mask(lower, match.start(), match.end()) if match else lower
    note = ""
    window = None
    if kind == "ahead":
        count = _int(match.group(1)) or 1
        unit = match.group(3)
        trading = bool(match.group(2)) and match.group(2).strip() in {"trading", "business"}
        if trading and unit == "day":
            start = today if today.weekday() < 5 else _effective_entry(today)
            last = _add_weekdays(start, count)
            window = (today, last, "in the next %d trading days" % count)
        else:
            span = count * {"day": 1, "week": 7, "month": 30}[unit]
            window = (today, today + datetime.timedelta(days=span - 1), "in the next %d days" % span)
    elif kind == "next_week":
        first = week_start + datetime.timedelta(days=7)
        window = (first, first + datetime.timedelta(days=6), "next week")
    elif kind == "this_week":
        if today.weekday() >= 5:      # weekend: the week that is about to start
            first = _effective_entry(today)
            window = (first, first + datetime.timedelta(days=6), "this coming week")
        else:                         # the days still ahead, never sessions already gone
            window = (today, week_start + datetime.timedelta(days=6), "in the rest of this week")
    elif kind == "next_month":
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        first = datetime.date(year, month, 1)
        window = (first, datetime.date(year, month, calendar.monthrange(year, month)[1]),
                  "in " + first.strftime("%B"))
    elif kind == "this_month":
        last = datetime.date(today.year, today.month,
                             calendar.monthrange(today.year, today.month)[1])
        window = (today, last, "in the rest of %s" % today.strftime("%B"))
    elif kind == "tomorrow":
        phrase = match.group(0)
        first = today if " or tomorrow" in phrase else today + datetime.timedelta(days=1)
        last = today + datetime.timedelta(days=2 if phrase.count("tomorrow") > 1 else 1)
        window = (first, last, "in the next few days")
    elif kind == "today":
        window = (today, today, "today")

    if window is None:
        # An explicit month or month-day in the current year can be screened directly.
        dated = re.search(
            r"\b(?:start(?:ing|s)?|begin(?:ning|s)?|enter(?:ing|s)?|from|on|around)\s+(?:on\s+)?"
            + _MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", rest)
        monthly = re.search(r"\b(?:in|during|for|throughout)\s+" + _MONTH + r"\b", rest)
        if dated:
            try:
                first = datetime.date(today.year, _MONTHS[dated.group(1)], int(dated.group(2)))
            except ValueError:
                return None
            if first < today:
                return None
            window = (first, first, "on " + _day_label(first))
            rest = _mask(rest, dated.start(), dated.end())
        elif monthly:
            month = _MONTHS[monthly.group(1)]
            if month < today.month:
                return None           # the detector covers the current calendar year only
            first = max(today, datetime.date(today.year, month, 1))
            last = datetime.date(today.year, month, calendar.monthrange(today.year, month)[1])
            window = (first, last, "in " + first.strftime("%B"))
            rest = _mask(rest, monthly.start(), monthly.end())
    if _UNPARSED_DATE_RE.search(_INDEX_NUMBER_RE.sub(" ", rest)):
        return None
    if window is None:
        window = (today, today, "today")
    first, last, label = window
    if (last - first).days + 1 > _MAX_SCREEN_DAYS:
        last = first + datetime.timedelta(days=_MAX_SCREEN_DAYS - 1)
        note = "The entry window is capped at %d days per screen." % _MAX_SCREEN_DAYS
    return first, last, label, note


def _hold_filter(text):
    """Explicit hold-length constraint as display days (min, max) or None."""

    lower = text.lower()
    match = re.search(
        r"\b(?:hold(?:ing)?|held)\b[^.;]{0,24}?(\d{1,3})\s*(?:-|to|and)\s*(\d{1,3})\s*d(?:ays?)?\b", lower)
    if match:
        low, high = sorted((int(match.group(1)), int(match.group(2))))
        return low, high
    low = high = None
    match = re.search(
        r"\b(?:min(?:imum)?|at\s+least)\s+hold(?:ing)?(?:\s+(?:period|time|of))?\s+(\d{1,3})\s*d|"
        r"\bhold(?:ing)?\s+(?:for\s+)?(?:min(?:imum)?|at\s+least)\s+(\d{1,3})\s*d", lower)
    if match:
        low = int(match.group(1) or match.group(2))
    match = re.search(
        r"\b(?:max(?:imum)?|may|up\s+to|at\s+most)\s+hold(?:ing)?(?:\s+(?:period|time|of))?\s+(\d{1,3})\s*d|"
        r"\bhold(?:ing)?\s+(?:for\s+)?(?:a\s+)?(?:max(?:imum)?(?:\s+of)?|up\s+to|at\s+most|no\s+more\s+than)\s+(\d{1,3})\s*d", lower)
    if match:
        high = int(match.group(1) or match.group(2))
    if low or high:
        return low or 1, high or 367
    match = re.search(
        r"\b(\d{1,3})\s*-?\s*(?:calendar\s*-?\s*)?day\s+(?:holds?|holding|windows?|patterns?|trades?|setups?)\b|"
        r"\bhold(?:ing)?\s+(?:for\s+|of\s+)?(\d{1,3})\s+days?\b", lower)
    if match:
        exact = int(match.group(1) or match.group(2))
        return exact, exact
    return None


def _screen_request(text, today, table_market):
    universe = _universe(text)
    explicit_filter = bool(re.search(
        r"\b(?:win[-\s]*rate|sharpe|sr)\b[^.;]{0,20}\d|\bmin(?:imum)?\b[^.;]{0,25}\d|"
        r"\b\d{1,2}\s+of\s+\d{1,2}\s+years\b|\btop\s+\d|\bbest\s+\d|\b\d+\s+best\b", text, re.I))
    if universe is None:
        if not (explicit_filter and table_market):
            return None
        universe = (str(table_market), "")
    if not _SCREEN_SHAPE_RE.search(text) or not _SCREEN_NOUN_RE.search(text):
        return None
    pairs, _masked = _currency_pairs(text)
    if _explicit_tickers(text) or pairs:
        return None
    if re.search(r"\b(?:compare|versus|vs\.?|against)\b", text, re.I):
        return None
    # The detector knows seasonal statistics only; other screening criteria are not its data.
    if _OFF_TOPIC_SCREEN_RE.search(text) or not _SEASONAL_SCREEN_CUE_RE.search(text):
        return None
    if re.search(r"\b(?:sectors?|industr(?:y|ies)|retail|technology|tech)\b", text, re.I):
        return None                  # no sector tags inside an index or the ETF list
    # The detector's election-cycle tables cover only the current year's cycle position, and
    # an inverse ("lowest win rate") ranking is not what its bands hold: leave both alone.
    if _CYCLE_WORD_RE.search(text) or _INVERSE_RANK_RE.search(text):
        return None
    direction = _direction(text)
    if direction is None:
        return None
    hold = _hold_filter(text)
    if hold and hold[1] < 2:
        return None                  # the detector cannot isolate a 1-day window
    cleaned = _DIRECTION_NOISE_RE.sub(" ", text)
    window_phrase = any(re.search(pattern, text, re.I) for _name, pattern in _WINDOW_PATTERNS)
    directional = bool(_BEAR_EXPLICIT_RE.search(cleaned) or _BULL_EXPLICIT_RE.search(cleaned)
                       or _BEAR_SOFT_RE.search(cleaned) or _BULL_SOFT_RE.search(cleaned))
    if not (window_phrase or explicit_filter or directional
            or _RANK_WIN_RE.search(text) or _RANK_SHARPE_RE.search(text) or _RANK_AVG_RE.search(text)):
        return None

    # Lookback and threshold phrases contain numbers and "years"; read them before dates.
    year1 = _lookback_years(text) or _DEFAULT_LOOKBACK
    min_wins = None
    match = re.search(
        r"\b(\d{1,2})\s+(?:of|out\s+of|ou[ft]\s+of)\s+(\d{1,2})\s+years\b", text, re.I
    ) or re.search(
        r"\b(?:min(?:imum)?|at\s+least|won|winning|wins?|winners?)\b[^.;]{0,25}?"
        r"\b(\d{1,2})\s*(?:of|out\s+of|/)\s*(\d{1,2})\b", text, re.I)
    if match and int(match.group(1)) <= int(match.group(2)):
        min_wins, year1 = int(match.group(1)), int(match.group(2))

    window = _entry_window(text, today)
    if window is None:
        return None
    first, last, label, note = window
    year_end = datetime.date(today.year, 12, 31)
    if first > year_end:
        return None
    last = min(last, year_end)
    if not any((first + datetime.timedelta(days=offset)).weekday() < 5
               for offset in range((last - first).days + 1)):
        last = first                 # weekend-only window: that day's table carries Monday's entries

    limit = _DEFAULT_LIMIT
    match = (re.search(r"\b(?:top|best|strongest)\s*-?\s*%s\b" % _NUM, text, re.I)
             or re.search(r"\b%s\s+(?:best|top|strongest)\b" % _NUM, text, re.I))
    if match and _int(match.group(1)):
        limit = max(1, min(_MAX_LIMIT, _int(match.group(1))))

    # Thresholds are filters, not the ranking key: read them first, then rank on the rest.
    rest = text

    def threshold(pattern):
        nonlocal rest
        found = re.search(pattern, rest, re.I)
        if not found:
            return None
        rest = rest[:found.start()] + " " + rest[found.end():]
        return next(group for group in found.groups() if group is not None)

    comparator = r"(?:min(?:imum)?|of\s+at\s+least|at\s+least|above|over|more\s+than|greater\s+than|>=?)"
    min_win_rate = threshold(
        r"\bwin[-\s]*rate\s*(?:of\s+)?%s?\s*(\d{1,3})\s*%%|"
        r"\bmin(?:imum)?\s+win[-\s]*rate\s*(?:of\s+)?(\d{1,3})\s*%%" % comparator)
    min_win_rate = min(100, int(min_win_rate)) if min_win_rate else None
    min_sharpe = threshold(
        r"\b(?:sharpe(?:\s+ratio)?|sr)\s*(?:of\s+)?%s\s*(\d+(?:\.\d+)?)|"
        r"\bmin(?:imum)?\s+(?:sharpe(?:\s+ratio)?|sr)\s*(?:of\s+)?(\d+(?:\.\d+)?)" % comparator)
    min_sharpe = float(min_sharpe) if min_sharpe else None
    min_avg = threshold(
        r"\b(?:avg|average)\s*(?:profit|return|gain)?\s*(?:of\s+)?%s\s*(\d+(?:\.\d+)?)\s*%%|"
        r"\bmin(?:imum)?\s+(?:avg|average)?\s*(?:profit|return|gain)\s*(?:of\s+|more\s+than\s+)?"
        r"(\d+(?:\.\d+)?)\s*%%" % comparator)
    min_avg = float(min_avg) if min_avg else None
    rank = "sharpe"
    if _RANK_WIN_RE.search(rest):
        rank = "win_rate"
    elif _RANK_AVG_RE.search(rest):
        rank = "avg"
    return {
        "market": universe[0], "universe": universe[1], "direction": direction,
        "rank": rank, "first": first, "last": last, "window_label": label,
        "window_note": note, "hold": hold, "limit": limit, "year1": year1,
        "min_wins": min_wins, "min_win_rate": min_win_rate, "min_sharpe": min_sharpe,
        "min_avg": min_avg,
    }


def _request_days(first, last):
    """Detector tables to fetch. A Monday table already carries the weekend's patterns."""

    if first == last:
        return [first]
    days = [first + datetime.timedelta(days=offset) for offset in range((last - first).days + 1)]
    return [day for day in days if day.weekday() < 5]


def _effective_entry(day):
    """A weekend-dated pattern is entered on the next weekday (the Monday table lists it)."""

    if day.weekday() == 5:
        return day + datetime.timedelta(days=2)
    if day.weekday() == 6:
        return day + datetime.timedelta(days=1)
    return day


def _detected_rows(request, year2, token):
    """All detector rows for the request at one min-winning-years band."""

    day_range = "-"
    if request["hold"]:
        day_range = "%d-%d" % (max(0, request["hold"][0] - 1), max(1, request["hold"][1] - 1))
    days = _request_days(request["first"], request["last"])
    single_day = request["first"] == request["last"]
    want = "short" if request["direction"] == "short" else "long"

    def fetch(day):
        return _engine_opplist(request["market"], day, request["year1"], year2, day_range, token)

    rows, statuses, failed, raw_counts = [], [], 0, []
    for status, payload in _parallel(fetch, days):
        statuses.append(status)
        if payload is None:
            failed += 1
            continue
        raw_counts.append(len(payload))
        for raw in payload:
            if not isinstance(raw, list) or len(raw) < 6:
                continue
            try:
                calendar_day = datetime.date.fromisoformat(str(raw[0]))
                row = {
                    "date": str(raw[0]), "symbol": str(raw[1]).upper(),
                    "days_out": int(float(raw[2])) + 1,
                    "direction": "short" if str(raw[3]).strip().lower() in {"s", "short"} else "long",
                    "sharpe": float(raw[4]), "avg": float(raw[5]), "tier": year2,
                }
            except (TypeError, ValueError):
                continue
            row["entry"] = _effective_entry(calendar_day)
            if row["direction"] != want or not tg._VS_SYMBOL_RE.fullmatch(row["symbol"]):
                continue
            if not single_day and not request["first"] <= row["entry"] <= request["last"]:
                continue
            rows.append(row)
    return rows, statuses, failed, raw_counts


_MISMATCH = "mismatch"


def _echo_matches(payload, market_symbol, entry_date, days_out, years=None, pe_cycle=None):
    """True only when the engine computed the study that was asked for.

    The engine silently rewrites a request it will not serve as asked (a date-locked plan
    gets today's window, a capped plan gets fewer years). Its echoed ``request`` is the
    only proof of what the numbers describe.
    """

    echo = payload.get("request") if isinstance(payload, dict) else None
    if not isinstance(echo, dict):
        return False
    try:
        echoed_entry = str(echo.get("entry_date"))
        if str(entry_date).endswith("-01-01") and echoed_entry == str(entry_date)[:4] + "-01-02":
            echoed_entry = str(entry_date)      # the engine's own January 1 -> January 2 rule
        same = (str(echo.get("symbol") or "").upper() == str(market_symbol).upper()
                and echoed_entry == str(entry_date)
                and int(echo.get("days_out")) == int(days_out))
        if years is not None:
            same = same and int(echo.get("years")) == int(years)
        if pe_cycle is not None:
            same = same and str(echo.get("pe_cycle") or "cons") == pe_cycle
    except (TypeError, ValueError):
        return False
    return same


def _verify_row(request, row, token):
    """Attach the engine's completed-year record for one detected pattern."""

    status, payload = _engine_chart(
        request["market"], row["symbol"], row["date"], row["days_out"], str(request["year1"]),
        token, comparison_direction=row["direction"])
    stats = payload.get("stats") if status == 200 and isinstance(payload, dict) else None
    if not isinstance(stats, dict) or not stats:
        return None
    if not _echo_matches(payload, row["symbol"], row["date"], row["days_out"],
                         request["year1"], "cons"):
        return _MISMATCH
    wins = tg._stat_number(stats, "Num Winners")
    losses = tg._stat_number(stats, "Num Losers")
    if wins is None or losses is None or wins + losses <= 0:
        return None
    verified = dict(row)
    verified.update({
        "wins": int(wins), "n": int(wins + losses),
        "win_pct": tg._stat_number(stats, "Percent Profitable"),
        "avg": tg._stat_number(stats, "Avg Profit - All"),
        "median": tg._stat_number(stats, "Median Profit"),
        "sharpe": tg._stat_number(stats, "Sharpe Ratio"),
    })
    if verified["win_pct"] is None or verified["sharpe"] is None or verified["avg"] is None:
        return None
    return verified


def _rank_key(rank):
    if rank == "win_rate":
        return lambda row: (row.get("win_pct", row["tier"]), row["sharpe"], row["avg"])
    if rank == "avg":
        return lambda row: (row["avg"], row["sharpe"])
    return lambda row: (row["sharpe"], row["avg"])


def _best_per_symbol(rows, rank):
    key = _rank_key(rank)
    best = {}
    for row in rows:
        current = best.get(row["symbol"])
        if current is None or key(row) > key(current):
            best[row["symbol"]] = row
    return sorted(best.values(), key=key, reverse=True)


def _screen_line(index, row, direction):
    entry = _day_label(row["entry"], weekday=True)
    if row["entry"].isoformat() != row["date"]:
        # The engine dates this pattern on a weekend; it is entered on the next session.
        entry += " (calendar start %s)" % _day_label(
            datetime.date.fromisoformat(row["date"]), weekday=True)
    win_pct = ("%.0f%%" % row["win_pct"])
    if direction == "short":
        record = "fell in %d of %d years (%s)" % (row["wins"], row["n"], win_pct)
        avg = "avg short-side return %s" % tg._fmt_pct(row["avg"])
    else:
        record = "profitable in %d of %d years (%s)" % (row["wins"], row["n"], win_pct)
        avg = "avg return %s" % tg._fmt_pct(row["avg"])
    return "%d. <b>%s</b> - starts %s, %d-day window: %s, %s, Sharpe %.2f" % (
        index, _esc(row["symbol"]), entry, row["days_out"], record, avg, row["sharpe"])


def _market_label(request):
    return request["universe"] or tg.config.available_resources.get(
        request["market"], "market %s" % request["market"]).title()


def build_screen_command(message, user_token, *, today=None, table_market=None, years_cap=None):
    text = str(message or "").strip()
    current = today or tg._market_today()
    request = _screen_request(text, current, table_market)
    if request is None or not user_token:
        return None
    label = _market_label(request)
    plan = _plan(user_token, request["market"])
    limits = []                     # plan limits that shaped this answer, stated to the user
    cap = years_cap if isinstance(years_cap, int) and years_cap > 0 else plan["years_cap"]
    if isinstance(cap, int) and request["year1"] > cap:
        limits.append("Your plan's lookback is capped at %d years, so this screen uses %d, not %d."
                      % (cap, cap, request["year1"]))
        request["year1"] = cap
        if request["min_wins"]:
            request["min_wins"] = min(request["min_wins"], cap)
    if plan["date_locked"] and not (request["first"] == request["last"] == current):
        limits.append("On your plan this market can be screened for today's entries only, so "
                      "this list covers today instead of %s." % request["window_label"])
        request.update(first=current, last=current, window_label="today", window_note="")
    if plan["row_cap"]:
        limits.append("Your plan shows only the top %d patterns per day on this market, so this "
                      "is a plan-limited sample, not the full screen." % plan["row_cap"])
    trace = {"event": "research_screen", "market": request["market"],
             "direction": request["direction"], "rank": request["rank"],
             "entry_first": request["first"].isoformat(),
             "entry_last": request["last"].isoformat(), "candidates": 0,
             "plan_limited": bool(limits)}

    floor = _band_floor(request["market"], request["year1"])
    if floor is None:
        choices = _band_lookbacks(request["market"])
        return {"reply": (
            "TradeWave does not precompute a %d-year screen for %s. Available lookbacks run "
            "from %d to %d years; ask again with one of those."
            % (request["year1"], _esc(label), choices[0], choices[-1])), "actions": [], "trace": trace}
    wanted = floor
    if request["min_wins"]:
        wanted = max(wanted, request["min_wins"])
    if request["min_win_rate"]:
        wanted = max(wanted, math.ceil(request["min_win_rate"] / 100.0 * request["year1"]))
    wanted = min(wanted, request["year1"])
    pool_target = min(16, request["limit"] + 6)

    # Win-rate ranking walks the detector's bands from "won every year" downward, so the
    # strictest record is collected first; other rankings read the widest in-band table.
    # Both are bounded: at most _MAX_TIERS bands and _MAX_ENGINE_CALLS engine reads a turn.
    table_count = max(1, len(_request_days(request["first"], request["last"])))
    tier_budget = max(1, min(_MAX_TIERS, (_MAX_ENGINE_CALLS - pool_target) // table_count))
    tiers = [wanted]
    if request["rank"] == "win_rate":
        # CONSECUTIVE bands from the strictest down, so no win-rate level is ever skipped:
        # every name that won at least `reached` years is in the pool. When the read budget
        # ends before the pool fills, the reply says how far down the ranking reaches.
        tiers = list(range(request["year1"], wanted - 1, -1))[:tier_budget]
    pool, screened, failed, statuses, reached, raw_counts = {}, 0, 0, [], wanted, []
    for tier in tiers:
        reached = tier
        rows, tier_statuses, tier_failed, tier_counts = _detected_rows(request, tier, user_token)
        statuses.extend(tier_statuses)
        raw_counts.extend(tier_counts)
        failed += tier_failed
        screened = max(screened, len({(row["symbol"], row["date"], row["days_out"]) for row in rows}))
        for row in _best_per_symbol(rows, "sharpe" if request["rank"] == "win_rate" else request["rank"]):
            if request["min_sharpe"] is not None and row["sharpe"] < request["min_sharpe"]:
                continue
            if request["min_avg"] is not None and abs(row["avg"]) < request["min_avg"]:
                continue
            pool.setdefault(row["symbol"], row)
        if len(pool) >= pool_target:
            break
    if statuses and all(status == 403 for status in statuses):
        return {"reply": (
            "<b>%s is outside this account's available markets.</b> I cannot screen it "
            "without the required market access." % _esc(label)), "actions": [], "trace": trace}
    if not pool and failed and failed == len(statuses):
        return None                 # engine unreachable: leave the turn to the normal path

    ordered = sorted(pool.values(), key=_rank_key(request["rank"]), reverse=True)[:pool_target]
    checked = _parallel(lambda row: _verify_row(request, row, user_token), ordered)
    mismatched = sum(1 for row in checked if row == _MISMATCH)
    verified = [row for row in checked if isinstance(row, dict)]
    if request["min_win_rate"] is not None:
        verified = [row for row in verified if row["win_pct"] >= request["min_win_rate"]]
    if request["min_wins"] is not None:
        verified = [row for row in verified if row["wins"] >= request["min_wins"]]
    if request["min_sharpe"] is not None:
        verified = [row for row in verified if row["sharpe"] >= request["min_sharpe"]]
    if request["min_avg"] is not None:
        verified = [row for row in verified if row["avg"] >= request["min_avg"]]
    verified.sort(key=_rank_key(request["rank"]), reverse=True)
    shown = verified[:request["limit"]]
    trace["candidates"] = len(shown)
    if mismatched:
        limits.append("%d detected pattern%s could not be verified on the dates listed because "
                      "the engine returned a different window for this plan; %s left out."
                      % (mismatched, "" if mismatched == 1 else "s",
                         "it was" if mismatched == 1 else "they were"))

    side = "bearish" if request["direction"] == "short" else "bullish"
    dates = (_day_label(request["first"]) if request["first"] == request["last"]
             else format_date_range(request["first"], request["last"]))
    if request["window_label"].startswith("on "):
        request["window_label"] = "that day"
    rank_text = {
        "win_rate": "win rate, then Sharpe Ratio",
        "avg": "average return (comparing each stock's highest-Sharpe window)",
        "sharpe": "Sharpe Ratio"}[request["rank"]]
    hold = request["hold"]
    hold_text = ""
    if hold:
        hold_text = (" Only %d-day windows." % hold[0] if hold[0] == hold[1]
                     else " Only windows of %d to %d days." % hold)
    advice = _ADVICE_BOUNDARY + " " if _ADVICE_RE.search(text) else ""
    if not shown:
        if limits:
            return {"reply": (
                "<b>I can't give a full %s %s screen on this plan.</b> %s Nothing %s in that "
                "limited view matched, which says nothing about the full market. What your plan "
                "does show: ask for \"today's top %s setups\" for the patterns entering now, or "
                "name a %s stock and I will analyze its current window. Full screens are part of "
                "the paid plans: tradewave.ai/pricing."
                % (_esc(label), side, " ".join(limits), side, _esc(label), _esc(label))),
                "actions": [], "trace": trace}
        deeper = ""
        if request["rank"] == "win_rate" and reached > wanted:
            deeper = (" A win-rate screen reads the detector's %d strictest band%s; ask for the "
                      "best by Sharpe Ratio to include records down to %d of %d."
                      % (len(tiers), "" if len(tiers) == 1 else "s", wanted, request["year1"]))
        return {"reply": (
            "<b>No %s %s seasonal windows matched.</b> TradeWave's detector found no "
            "%s pattern that starts %s (%s) and won at least %d of the last %d years%s%s "
            "Widen the dates, lower the win-rate floor, or drop a filter and I will run it again."
            % (_esc(label), side, side, request["window_label"], dates, reached,
               request["year1"], ("." + hold_text) if hold_text else ".", deeper)),
            "actions": [], "trace": trace}

    interpretation = ""
    if re.search(r"\bnext\s+%s\s+days?\b" % _NUM, text, re.I) and not hold and not plan["date_locked"]:
        span = (request["last"] - request["first"]).days + 1
        interpretation = (
            " I read \"next %d days\" as windows that START in the next %d days, at any "
            "length; ask for \"%d-day holds\" to fix the holding period instead." % (span, span, span))
    lead = (
        "<div class=\"tara-analysis-section tara-analysis-lead\"><span class=\"tara-analysis-heading\">"
        "%s %s seasonal windows starting %s (%s)</span> %sTop %d by %s over a %d-year lookback.%s%s%s</div>"
        % (_esc(label), side, request["window_label"], dates, advice, len(shown), rank_text,
           request["year1"], hold_text,
           (" A short-direction win means the security fell during the window; "
            "returns are short-side, so positive means it fell."
            if request["direction"] == "short" else ""), interpretation))
    lines = "<br>".join(
        _screen_line(index, row, request["direction"]) for index, row in enumerate(shown, 1))
    scope_bits = list(limits)
    if request["rank"] == "win_rate" and reached > wanted:
        scope_bits.append(
            "This win-rate ranking covers every pattern that won at least %d of the last %d "
            "years%s; names with a lower record are not ranked here." % (
                reached, request["year1"],
                "" if len(shown) >= request["limit"] else
                " - the %d found in the detector's %d strictest band%s, which is as far as one "
                "screen reads" % (len(shown), len(tiers), "" if len(tiers) == 1 else "s")))
    scope_bits.append(
        "TradeWave's detector listed %d %s pattern%s for these dates that won at least %d of "
        "the last %d years; each record above is the engine's completed-year result."
        % (screened, side, "" if screened == 1 else "s", reached, request["year1"]))
    if request["window_note"]:
        scope_bits.append(request["window_note"])
    if failed:
        scope_bits.append("%d daily table%s could not be read, so the list may be incomplete."
                          % (failed, "" if failed == 1 else "s"))
    scope_bits.append(
        "Historical research candidates, not %s recommendations; past patterns may not repeat. "
        "Name a ticker to load its chart." % ("sell or short" if request["direction"] == "short" else "buy"))
    reply = (
        "<div class=\"tara-analysis\">" + lead
        + "<div class=\"tara-analysis-section\">" + lines + "</div>"
        + "<div class=\"tara-analysis-section tara-analysis-scope\"><span class=\"tara-analysis-heading\">"
        "Scope</span> " + " ".join(scope_bits) + "</div></div>")
    actions = []
    if table_market is not None and str(table_market) != request["market"]:
        actions.append({"type": "set_view", "spec": {"market": request["market"]}})
    return {"reply": reply, "actions": actions, "trace": trace, "rows": shown}


# ---------------------------------------------------------------------------
# Security and period parsing for studies and comparisons
# ---------------------------------------------------------------------------

_SECTOR_ETFS = (
    (r"tech(?:nology)?", "XLK", "Technology"),
    (r"utilit(?:y|ies)", "XLU", "Utilities"),
    (r"financials?|banks?|banking", "XLF", "Financials"),
    (r"energy", "XLE", "Energy"),
    (r"health\s*care|healthcare", "XLV", "Health Care"),
    (r"industrials?", "XLI", "Industrials"),
    (r"materials", "XLB", "Materials"),
    (r"consumer\s+staples|staples", "XLP", "Consumer Staples"),
    (r"consumer\s+discretionary|discretionary", "XLY", "Consumer Discretionary"),
    (r"real\s+estate", "XLRE", "Real Estate"),
    (r"communications?(?:\s+services)?", "XLC", "Communication Services"),
)
_SECTOR_BY_SYMBOL = {symbol: name for _, symbol, name in _SECTOR_ETFS}
_SECTOR_RE = re.compile(
    r"\b(" + "|".join(pattern for pattern, _, _ in _SECTOR_ETFS) + r")\b", re.I)
_SECTOR_CONTEXT_RE = re.compile(r"\b(?:etfs?|sector\s+(?:fund|spdr)s?|sector\s+etfs?|spdrs?)\b", re.I)

# Plain-language names for instruments that are not companies. Company names are
# resolved against the engine's own security list instead (see _company_symbol).
_NAMED_SECURITIES = (
    (r"(?:the\s+)?(?:s\s*&\s*p|s\s+and\s+p|sp)\s*-?\s*500(?:\s+index)?|(?:the\s+)?s\s*&\s*p", "SPX", "5"),
    (r"(?:the\s+)?nasdaq(?:\s*-?\s*100)?(?:\s+index)?", "NDX", "5"),
    (r"(?:the\s+)?dow(?:\s+jones)?(?:\s+industrial(?:s|\s+average)?)?", "DJI", "5"),
    (r"(?:the\s+)?russell\s*2000", "RUT", "5"),
    (r"gold(?:\s+futures)?", "GC", "7"),
    (r"(?:crude\s+)?oil(?:\s+futures)?|crude(?:\s+futures)?", "CL", "7"),
    (r"silver(?:\s+futures)?", "SI", "7"),
    (r"natural\s+gas(?:\s+futures)?", "NG", "7"),
)
_NAME_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "plc", "sa",
    "nv", "ag", "holdings", "holding", "group", "the", "class", "a", "b", "c", "com",
    "trust", "lp",
}
# One-word company names are matched ONLY from this curated list. The engine's security
# list holds about 1,100 one-word names that are ordinary English ("happen", "people",
# "post", "capital", "news"), so free-text single words are never looked up there.
_KNOWN_COMPANIES = {
    "apple": "AAPL", "microsoft": "MSFT", "amazon": "AMZN", "nvidia": "NVDA", "tesla": "TSLA",
    "google": "GOOGL", "alphabet": "GOOGL", "facebook": "META", "netflix": "NFLX",
    "walmart": "WMT", "disney": "DIS", "boeing": "BA", "intel": "INTC", "oracle": "ORCL",
    "cisco": "CSCO", "pfizer": "PFE", "nike": "NKE", "starbucks": "SBUX", "costco": "COST",
    "mastercard": "MA", "adobe": "ADBE", "salesforce": "CRM", "broadcom": "AVGO",
    "paypal": "PYPL", "exxon": "XOM", "chevron": "CVX", "jpmorgan": "JPM", "pepsi": "PEP",
    "pepsico": "PEP", "mcdonalds": "MCD", "mcdonald's": "MCD", "qualcomm": "QCOM",
    "palantir": "PLTR", "ibm": "IBM", "amd": "AMD", "caterpillar": "CAT", "verizon": "VZ",
    "merck": "MRK", "abbvie": "ABBV", "citigroup": "C", "visa": "V",
}
# Words that never start or end a multi-word company-name lookup.
_NAME_STOPWORDS = {
    "a", "about", "after", "against", "all", "an", "analysis", "analyze", "analyse", "and",
    "any", "are", "as", "at", "average", "be", "bearish", "been", "before", "best",
    "between", "bullish", "by", "can", "chart", "compare", "comparison", "consecutive",
    "current", "cycle", "data", "date", "dates", "day", "days", "did", "do", "does",
    "during", "each", "election", "end", "ending", "etf", "etfs", "first", "for",
    "fourth", "from", "fund", "funds", "gain", "has", "have", "historic", "historical",
    "historically", "history", "hold", "how", "i", "in", "is", "it", "its", "last",
    "late", "like", "loaded", "long", "look", "loss", "me", "mid", "midterm", "month",
    "months", "my", "next", "now", "of", "on", "one", "or", "over", "past", "pattern",
    "patterns", "performance", "performed", "period", "please", "quarter", "range",
    "rate", "recurring", "return", "returns", "seasonal", "seasonality", "second",
    "sector", "short", "show", "since", "start", "starting", "stock", "stocks", "tell",
    "tend", "tendency", "than", "that", "the", "their", "them", "these", "third", "this",
    "through", "till", "time", "to", "today", "trend", "two", "until", "up", "versus",
    "view", "vs", "was", "week", "weeks", "were", "what", "when", "which", "window",
    "with", "year", "years", "you", "your", "win", "early", "half", "side", "same",
    "happen", "happens", "people", "post", "pre", "news", "market", "markets", "good",
    "better", "buy", "sell", "price", "prices", "top", "new", "old", "high", "low", "goods",
    "capital", "information", "technology", "healthcare", "energy", "financial", "general",
    "national", "american", "international", "global", "united", "southern", "northern",
    "eastern", "western", "summer", "winter", "spring", "fall", "returns", "question",
} | set(_MONTHS)
_NAMES_TTL_SECONDS = 3600
_NAMES_CACHE = {"at": 0.0, "index": None}


def _normalize_company(name):
    words = re.sub(r"\(.*?\)", " ", str(name or "").lower())
    words = re.sub(r"\.com\b", " ", words)
    tokens = re.findall(r"[a-z0-9&']+", words.replace(".", " "))
    while tokens and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _company_index(token):
    """Normalized multi-word company names -> symbols, from the engine's US security list.

    Security names are not plan-gated content, so one process-wide copy is kept for an hour.
    """

    now = time.time()
    if _NAMES_CACHE["index"] is not None and now - _NAMES_CACHE["at"] < _NAMES_TTL_SECONDS:
        return _NAMES_CACHE["index"]
    names = _engine_symbol_names("2", token) or _engine_symbol_names("0", token)
    if not names:
        return {}
    index = {}
    for symbol, name in names.items():
        normalized = _normalize_company(name)
        if " " in normalized:
            index.setdefault(normalized, []).append(str(symbol).upper())
    _NAMES_CACHE.update(at=now, index=index)
    return index


def _company_symbol(phrase, token):
    """Resolve a multi-word company name on an EXACT match with the engine's own name."""

    matches = _company_index(token).get(phrase) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and len({symbol[:3] for symbol in matches}) == 1:
        # Share classes of one company: take the primary first listing.
        return sorted(matches, key=lambda symbol: (len(symbol), symbol))[0]
    return None


def _find_securities(text, token, current_view=None, allow_names=True, unresolved=None):
    """Ordered, de-duplicated securities named in the request: [{symbol, market, name}]."""

    found = []          # (position, symbol, market_hint, sector)

    def add(position, symbol, market=None, sector=None):
        if all(symbol != item[1] for item in found):
            found.append((position, symbol, market, sector))

    # Currency pairs first, so EUR/USD is one instrument and never two "tickers".
    pairs, masked = _currency_pairs(text)
    for position, pair in pairs:
        add(position, pair, "8")
    # Election-cycle and period words are study settings, never security names.
    masked = _CYCLE_WORD_RE.sub(lambda m: " " * len(m.group(0)), masked)
    if _SECTOR_CONTEXT_RE.search(text):
        for match in _SECTOR_RE.finditer(masked):
            for pattern, symbol, sector in _SECTOR_ETFS:
                if re.fullmatch(pattern, match.group(1), re.I):
                    add(match.start(), symbol, "11", sector)
                    break
        masked = _SECTOR_RE.sub(lambda m: " " * len(m.group(0)), masked)
    for ticker in _explicit_tickers(text, allow_single=bool(_COMPARE_RE.search(text))):
        position = re.search(r"(?<![A-Za-z0-9])\$?%s(?![A-Za-z0-9])" % re.escape(ticker), text).start()
        add(position, ticker)
        masked = re.sub(r"(?<![A-Za-z0-9])\$?%s(?![A-Za-z0-9])" % re.escape(ticker),
                        lambda m: " " * len(m.group(0)), masked)
    for pattern, symbol, market in _NAMED_SECURITIES:
        match = re.search(r"(?<![A-Za-z&])(?:%s)(?![A-Za-z&])" % pattern, masked, re.I)
        if match and not re.search(r"\b(?:stocks|companies|names)\b", masked[match.end():match.end() + 12], re.I):
            add(match.start(), symbol, market)
            masked = _mask(masked, match.start(), match.end())
    if re.search(r"\b(?:current|loaded|this)\s+(?:loaded\s+)?(?:pattern|chart|symbol|stock|security|setup)\b", text, re.I):
        view = current_view if isinstance(current_view, dict) else {}
        symbol = str(view.get("symbol") or "").strip().upper()
        if tg._VS_SYMBOL_RE.fullmatch(symbol):
            add(len(text), symbol, str(view.get("market") or "") or None)
    if allow_names and token:
        words = [(m.start(), re.sub(r"'s$", "", m.group(0).lower()))
                 for m in re.finditer(r"[A-Za-z][A-Za-z&']*", masked)]
        index = 0
        while index < len(words):
            matched = False
            for size in (3, 2):
                chunk = [word for _, word in words[index:index + size]]
                if len(chunk) < size or chunk[0] in _NAME_STOPWORDS or chunk[-1] in _NAME_STOPWORDS:
                    continue
                symbol = _company_symbol(" ".join(chunk), token)
                if symbol:
                    add(words[index][0], symbol, "2")
                    index += size
                    matched = True
                    break
            if not matched:
                known = _KNOWN_COMPANIES.get(words[index][1])
                if known:
                    add(words[index][0], known, "2")
                index += 1

    # Lower-case tickers are read last, and only in a comparison: named instruments
    # ("gold" is GC, not the ticker GOLD) and company names have already been masked.
    guessed = set()
    if _is_comparison(text):
        for position, ticker in _lowercase_compare_tickers(masked, {item[1] for item in found}):
            add(position, ticker)
            guessed.add(ticker)

    resolved = []
    typed = set(_explicit_tickers(text, allow_single=True))
    for _, symbol, market, sector in sorted(found):
        resolution = tg._resolve_question_symbol(symbol, text, token, current_view)
        if resolution.get("status") != "ok":
            if market and resolution.get("status") == "ambiguous":
                picked = [item for item in resolution.get("matches", [])
                          if str(item.get("resourceID")) == str(market)]
                if len(picked) == 1:
                    resolution = {"status": "ok", "symbol": symbol, "market": str(market),
                                  "name": str(picked[0].get("name") or "")}
            if resolution.get("status") == "ambiguous":
                resolved.append({"symbol": symbol, "error": resolution})
                continue
            if resolution.get("status") != "ok":
                # Not a TradeWave security (or lookup down): not a slot. A ticker the
                # user typed is reported so a comparison never drops it silently.
                if (isinstance(unresolved, list) and resolution.get("status") == "not_found"
                        and symbol in typed | guessed):
                    unresolved.append((symbol, symbol in typed))
                continue
        entry = {"symbol": resolution["symbol"], "market": resolution["market"],
                 "name": resolution.get("name") or ""}
        resolved.append(entry)
    return resolved


def _month_day(month_text, day_text, year, *, end=False, mid=False):
    month = _MONTHS[month_text.lower().rstrip(".")]
    if day_text:
        day = int(day_text)
    elif mid:
        day = 15
    elif end:
        day = calendar.monthrange(year, month)[1]
    else:
        day = 1
    day = min(day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


# Same season boundaries as the gateway's period presets (apiserver/routes.py).
_SEASONS = {"spring": ((3, 21), (6, 20)), "summer": ((6, 21), (9, 21)),
            "fall": ((9, 22), (12, 21)), "winter": ((12, 22), (3, 20))}


def _parse_period(text, today):
    """Resolve an explicit study window to (start, end, label), else None.

    None also covers wording this parser must not approximate: a named calendar year
    ("December 2022" is one year, not a seasonal study) and trading-day counts.
    """

    if re.search(r"\b(?:19|20)\d{2}\b", _INDEX_NUMBER_RE.sub(" ", text)) or re.search(
            r"\b(?:trading|business)\s+days?\b", text, re.I):
        return None
    try:
        period = _parse_period_text(text, today)
    except ValueError:              # an impossible calendar date such as Feb 30
        return None
    if period is None or period[1] <= period[0]:
        return None                 # a zero-length window is not a study
    return period


def _parse_period_text(text, today):
    lower = text.lower()
    year = today.year
    year_end = r"(?:year[-\s]?end|(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?year|eoy|new\s+year'?s?\s+eve)"

    quarter = re.search(r"\b(?:(first|1st|second|2nd|third|3rd|fourth|4th)\s+quarter|q([1-4]))\b", lower)
    if quarter:
        number = int(quarter.group(2)) if quarter.group(2) else {
            "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4}[quarter.group(1)]
        start = datetime.date(year, 3 * number - 2, 1)
        end = datetime.date(year, 3 * number, calendar.monthrange(year, 3 * number)[1])
        return start, end, "Q%d" % number

    if re.search(r"\b(?:from\s+)?(?:now|today|here)\b.{0,25}\b%s" % year_end, lower) or re.search(
            r"\b(?:rest|remainder)\s+of\s+(?:the\s+|this\s+)?year\b", lower):
        return today, datetime.date(year, 12, 31), "now to year end"

    edge = r"(?:(early|mid|late|the\s+end\s+of|end\s+of|the\s+start\s+of|start\s+of)[-\s]+)?"
    day = r"(?:\s+(\d{1,2})(?:st|nd|rd|th)?)?"
    joiner = r"\s*(?:to|through|thru|until|till|til|and|-|–)\s*(?:the\s+)?"
    span = re.search(
        r"\b" + edge + _MONTH + r"\.?" + day + joiner
        + r"(?:" + edge + _MONTH + r"\.?" + day + r"|(" + year_end + r"))", lower)
    if span:
        start_edge, start_month, start_day = span.group(1), span.group(2), span.group(3)
        start = _month_day(start_month, start_day, year,
                           mid=bool(start_edge and "mid" in start_edge),
                           end=bool(start_edge and ("late" in start_edge or "end" in start_edge)))
        if start_edge and "late" in start_edge and not start_day:
            start = start.replace(day=21)
        if span.group(7):
            end = datetime.date(year, 12, 31)
        else:
            end_edge, end_month, end_day = span.group(4), span.group(5), span.group(6)
            end_year = year
            if _MONTHS[end_month.rstrip(".")] < start.month or (
                    _MONTHS[end_month.rstrip(".")] == start.month and end_day
                    and int(end_day) < start.day):
                end_year += 1
            end = _month_day(end_month, end_day, end_year, end=not end_day,
                             mid=bool(end_edge and "mid" in end_edge))
            if end_edge and "early" in end_edge and not end_day:
                end = end.replace(day=10)
        return start, end, format_date_range(start, end)

    part = re.search(
        r"\b(first|last)\s+(?:(%s)\s+weeks?|(half))\s+of\s+%s\b" % ("|".join(_NUMBER_WORDS) + r"|\d", _MONTH),
        lower)
    if part:
        month = _MONTHS[part.group(4)]
        last_day = calendar.monthrange(year, month)[1]
        length = 15 if part.group(3) else 7 * (_int(part.group(2)) or 1)
        if part.group(1) == "first":
            start = datetime.date(year, month, 1)
            end = datetime.date(year, month, min(length, last_day))
        else:
            end = datetime.date(year, month, last_day)
            start = end - datetime.timedelta(days=length - 1)
        return start, end, format_date_range(start, end)

    ahead = re.search(
        r"\b(?:over|in|for|during)?\s*(?:the\s+)?(?:next|coming)\s+%s\s+(day|week|month)s?\b" % _NUM, lower)
    if ahead and _int(ahead.group(1)):
        span_days = _int(ahead.group(1)) * {"day": 1, "week": 7, "month": 30}[ahead.group(2)]
        if 1 <= span_days <= 367:
            end = today + datetime.timedelta(days=span_days - 1)
            return today, end, "the next %d days" % span_days

    season = re.search(
        r"\b(?:in|during|for|over|through|this|next|the|every|each)\s+(?:the\s+)?"
        r"(spring|summer|fall|autumn|winter)\b|\b(spring|summer|autumn|winter)\b", lower)
    if season:
        name = season.group(1) or season.group(2)
        (m1, d1), (m2, d2) = _SEASONS["fall" if name == "autumn" else name]
        start = datetime.date(year, m1, d1)
        end = datetime.date(year + (1 if (m2, d2) < (m1, d1) else 0), m2, d2)
        return start, end, name

    if re.search(r"\bnext\s+month\b", lower):
        first = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        return first, last, first.strftime("%B")

    month = re.search(
        r"\b(?:in|during|for|throughout|every|each)\s+(?:the\s+month\s+of\s+)?%s\b|\b%s(?:'s)?\s+"
        r"(?:seasonal\s+|bullish\s+|bearish\s+)*(?:pattern|window|performance|seasonality|tendency|returns?)\b"
        % (_MONTH, _MONTH), lower)
    if month:
        name = month.group(1) or month.group(2)
        if name == "may" and not re.search(r"\b(?:in|during|for)\s+may\b", lower):
            return None
        number = _MONTHS[name]
        start = datetime.date(year, number, 1)
        end = datetime.date(year, number, calendar.monthrange(year, number)[1])
        return start, end, start.strftime("%B")
    return None


def _view_period(current_view):
    view = current_view if isinstance(current_view, dict) else {}
    try:
        start = datetime.date.fromisoformat(str(view.get("start_date") or view.get("entry_date"))[:10])
        days = int(str(view.get("days_out")))
    except (TypeError, ValueError):
        return None
    if not 1 <= days <= 367:
        return None
    end = start + datetime.timedelta(days=days - 1)
    return start, end, "the loaded window"


def _requested_years(text, current_view, default=_DEFAULT_LOOKBACK):
    explicit = _lookback_years(text)
    if explicit:
        return explicit, True
    view = current_view if isinstance(current_view, dict) else {}
    cycle = str(view.get("pe_cycle") or "cons").lower()
    raw = str(view.get("years") or "")
    if cycle in {"cons", "consecutive"} and raw.isdigit() and 1 <= int(raw) <= 99:
        return int(raw), False
    return default, False


def _years_value(pe_cycle, years):
    return str(int(years)) if pe_cycle == "cons" else "%s-%d" % (pe_cycle, int(years))


_PE_LABELS = {
    "cons": "consecutive years", "pe0": "election years (PE+0)",
    "pe1": "post-election years (PE+1)", "pe2": "midterm years (PE+2)",
    "pe3": "pre-election years (PE+3)",
}


def _completed_rows(payload):
    rows = []
    for row in (payload.get("ChartData4") if isinstance(payload, dict) else None) or []:
        if not isinstance(row, dict) or row.get("completed") is False:
            continue
        parts = str(row.get("pct") or "").split(",")
        try:
            item = {"year": int(row.get("year")), "ret": float(parts[0]),
                    "high": float(parts[1]), "low": float(parts[2])}
        except (TypeError, ValueError, IndexError):
            continue
        for key in ("low_date", "high_date", "entry_trade_date", "exit_trade_date"):
            if row.get(key):
                item[key] = str(row[key])
        rows.append(item)
    return rows


_UNSET = object()


def _study(security, start, days_out, pe_cycle, years, token, available=_UNSET, **params):
    """Fetch one engine study and return a normalized record or an error reply."""

    symbol, market = security["symbol"], security["market"]
    if available is _UNSET:
        available = tg._symbol_max_available_years(market, symbol, token, pe_cycle)
    used = min(int(years), available) if isinstance(available, int) else int(years)
    status, payload = _engine_chart(
        market, symbol, start.isoformat(), days_out, _years_value(pe_cycle, used), token, **params)
    if status == 403 and market == "2":
        # A US stock resolves to the S&P 500 group; a plan limited to the Dow 30 or
        # NASDAQ 100 group may still hold the same security there.
        for alternate in ("0", "1"):
            status, payload = _engine_chart(
                alternate, symbol, start.isoformat(), days_out, _years_value(pe_cycle, used),
                token, **params)
            if status != 403:
                market = alternate
                break
    if status == 403:
        return {"error": "<b>%s is outside this account's available markets.</b> I cannot "
                         "load or summarize that chart without the required market access."
                         % _esc(symbol)}
    if status != 200 or not isinstance(payload, dict):
        # Engine unreachable or failing: let the normal chat path take the turn.
        return {"error": "unavailable", "unavailable": True}
    stats = payload.get("stats")
    echo = payload.get("request") if isinstance(payload, dict) else None
    if not isinstance(stats, dict) or not stats or not isinstance(echo, dict):
        return {"error": "TradeWave could not produce a verified <b>%s</b> study for those "
                         "dates, so I have not stated a result or changed the chart."
                         % _esc(symbol)}
    wins = tg._stat_number(stats, "Num Winners")
    losses = tg._stat_number(stats, "Num Losers")
    if wins is None or losses is None or wins + losses <= 0:
        return {"error": "TradeWave has no completed years for <b>%s</b> on those dates."
                         % _esc(symbol)}
    try:
        entry = datetime.date.fromisoformat(str(echo.get("entry_date")))
        days = int(echo.get("days_out"))
        echo_years = int(echo.get("years"))
    except (TypeError, ValueError):
        return {"error": "TradeWave returned an unverifiable <b>%s</b> study, so I have not "
                         "stated a result." % _esc(symbol)}
    # The engine silently rewrites a request it will not serve as asked (a date-locked plan
    # is given today's window). Only its own January 1 -> January 2 entry rule is accepted.
    asked_entry = start
    if start.month == 1 and start.day == 1 and entry == start + datetime.timedelta(days=1):
        asked_entry = entry
    if entry != asked_entry or days != int(days_out) or str(
            echo.get("pe_cycle") or "cons") != pe_cycle:
        return {"plan_limited": True, "error": (
            "<b>I can't run that %s study on this plan.</b> TradeWave returned a window "
            "starting %s (%d days) instead of %s (%d days), which is what happens on a market "
            "your plan can study from today's date only. I have not stated a result or "
            "changed the chart." % (_esc(symbol), _long_date(entry), days,
                                    format_date_range(start, start + datetime.timedelta(
                                        days=int(days_out) - 1)), int(days_out)))}
    spec = tg._validate_view_spec({
        "market": str(echo.get("market")), "symbol": str(echo.get("symbol") or "").upper(),
        "entry_date": entry.isoformat(), "days_out": days, "years": echo_years,
        "pe_cycle": str(echo.get("pe_cycle") or "cons"),
    })
    return {
        "symbol": symbol, "market": market, "name": security.get("name") or "",
        "entry": entry, "end": entry + datetime.timedelta(days=days - 1), "days": days,
        "years": echo_years, "requested_years": int(years), "available_years": available,
        "engine_capped": echo_years < used,
        "pe_cycle": str(echo.get("pe_cycle") or "cons"),
        "direction": str(stats.get("Trade Dir") or "long").lower(),
        "wins": int(wins), "n": int(wins + losses),
        "win_pct": tg._stat_number(stats, "Percent Profitable"),
        "avg": tg._stat_number(stats, "Avg Profit - All"),
        "median": tg._stat_number(stats, "Median Profit"),
        "avg_win": tg._stat_number(stats, "Avg Profit"),
        "avg_loss": tg._stat_number(stats, "Avg Loss"),
        "sharpe": tg._stat_number(stats, "Sharpe Ratio"),
        "rows": _completed_rows(payload), "spec": spec or None, "payload": payload,
    }


def _extremes_text(rows, direction="long"):
    """Best/worst year and the largest moves inside the window, labelled for the engine's
    trade direction: a rise is the favorable move (MFE) of a long pattern and the adverse
    move (MAE) of a short one."""

    if not rows:
        return ""
    best = max(rows, key=lambda row: row["ret"])
    worst = min(rows, key=lambda row: row["ret"])
    deepest = min(rows, key=lambda row: row["low"])
    highest = max(rows, key=lambda row: row["high"])
    rise_label, drop_label = ("MAE", "MFE") if direction == "short" else ("MFE", "MAE")
    return (
        "Underlying's best year: %d at %s. Worst year: %d at %s. Largest rise inside the "
        "window (%s): %s in %d. Deepest drop inside the window (%s): %s in %d."
        % (best["year"], tg._fmt_pct(best["ret"]), worst["year"], tg._fmt_pct(worst["ret"]),
           rise_label, tg._fmt_pct(highest["high"]), highest["year"],
           drop_label, tg._fmt_pct(deepest["low"]), deepest["year"]))


# ---------------------------------------------------------------------------
# 3. Symbol window study
# ---------------------------------------------------------------------------

_STUDY_VERB_RE = re.compile(
    r"\b(?:analy[sz]e|analysis|historic(?:al(?:ly)?)?|perform(?:ed|ance|s)?|tendenc(?:y|ies)|"
    r"returns?|track\s+record|how\s+(?:has|have|did|does|do)|tend(?:s)?\s+to|"
    r"(?:recurring|bearish|bullish)\s+(?:seasonal\s+)?(?:pattern|window|tendency)|seasonal\s+trend)\b",
    re.I)


def build_window_study_command(message, current_view, user_token, *, today=None,
                               years_cap=None, securities=None):
    text = str(message or "").strip()
    if not user_token or not _STUDY_VERB_RE.search(text):
        return None
    current = today or tg._market_today()
    period = _parse_period(text, current)
    if period is None:
        return None
    securities = securities if securities is not None else _find_securities(
        text, user_token, current_view)
    if len(securities) != 1:
        return None
    security = securities[0]
    trace = {"event": "research_window_study", "symbol": security.get("symbol", "")}
    if security.get("error"):
        return {"reply": tg._resolution_boundary(security["error"]), "actions": [], "trace": trace}
    start, end, label = period
    days_out = (end - start).days + 1
    if not 1 <= days_out <= 367:
        return None
    pe_cycle = _pe_cycle(text)
    years, explicit = _requested_years(text, current_view)
    if pe_cycle != "cons" and not explicit:
        years = 99
    asked_years = years
    cap = years_cap if isinstance(years_cap, int) and years_cap > 0 else _plan(
        user_token, security["market"])["years_cap"]
    if isinstance(cap, int) and cap > 0:
        years = min(years, cap)
    study = _study(security, start, days_out, pe_cycle, years, user_token)
    if study.get("unavailable"):
        return None
    if study.get("error"):
        return {"reply": study["error"], "actions": [], "trace": trace}

    symbol = _esc(study["symbol"])
    name = _esc(study["name"])
    title = "%s%s, %s" % (symbol, (" (%s)" % name) if name else "",
                          format_date_range(study["entry"], study["end"], with_year=True))
    cohort = _PE_LABELS.get(study["pe_cycle"], "years")
    history_note = ""
    if explicit and study["pe_cycle"] == "cons" and (
            asked_years > years or study["engine_capped"]):
        history_note = (" You asked for %d years; your plan's lookback is capped at %d, so this "
                        "is the %d-year study." % (asked_years, study["years"], study["years"]))
    elif explicit and study["years"] < study["requested_years"] and study["pe_cycle"] == "cons":
        history_note = (" You asked for %d years; TradeWave has %d years of history for %s."
                        % (study["requested_years"], study["years"], symbol))
    elif study["pe_cycle"] == "cons" and study["n"] > study["years"]:
        history_note = (" This year's window has already finished, so TradeWave counts it with "
                        "the %d-year lookback." % study["years"])
    win_pct = "%.0f%%" % study["win_pct"] if study["win_pct"] is not None else "n/a"
    if study["direction"] == "short":
        record = (
            "TradeWave reads this window as a short-direction pattern: %s fell in %d of %d "
            "completed %s (%s). Short-side results (a positive figure means the underlying "
            "fell): average %s, median %s, Sharpe Ratio %s."
            % (symbol, study["wins"], study["n"], cohort, win_pct, tg._fmt_pct(study["avg"]),
               tg._fmt_pct(study["median"]),
               "%.2f" % study["sharpe"] if study["sharpe"] is not None else "unavailable"))
    else:
        record = (
            "%s was profitable in %d of %d completed %s (%s). Average return %s, median %s, "
            "Sharpe Ratio %s. Average gain in up years %s; average loss in down years %s."
            % (symbol, study["wins"], study["n"], cohort, win_pct, tg._fmt_pct(study["avg"]),
               tg._fmt_pct(study["median"]),
               "%.2f" % study["sharpe"] if study["sharpe"] is not None else "unavailable",
               tg._fmt_pct(study["avg_win"]), tg._fmt_pct(study["avg_loss"])))
    reply = (
        "<div class=\"tara-analysis\">"
        "<div class=\"tara-analysis-section tara-analysis-lead\"><span class=\"tara-analysis-heading\">"
        "%s</span> %d calendar days (%s), %d completed %s.%s</div>"
        "<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">Record</span> %s</div>"
        "<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">Range of outcomes</span> "
        "%s Yearly figures are the underlying's own move.</div>"
        "<div class=\"tara-analysis-section tara-analysis-scope\"><span class=\"tara-analysis-heading\">"
        "Scope</span> %sI am loading this exact study in the Wave Viewer so every year is visible. "
        "Historical results are not a forecast.</div></div>"
        % (title, study["days"], _esc(label), study["n"], cohort, history_note, record,
           _extremes_text(study["rows"], study["direction"]),
           (_ADVICE_BOUNDARY + " ") if _ADVICE_RE.search(text) else ""))
    actions = [{"type": "set_view", "spec": study["spec"]}] if study["spec"] else []
    return {"reply": reply, "actions": actions, "trace": trace, "study": study}


# ---------------------------------------------------------------------------
# 4. Symbol comparison
# ---------------------------------------------------------------------------

_COMPARE_RE = re.compile(
    r"\b(?:compare|comparison|compared|versus|vs\.?|against|side[-\s]by[-\s]side|"
    r"better\s+than|outperform(?:s|ed)?|stack(?:s)?\s+up)\b", re.I)


# "spy or qqq for next month", "which is better, AAPL or MSFT" are comparisons too.
_CHOICE_RE = re.compile(
    r"\bwhich\s+(?:one\s+)?(?:is|was|looks|does)\s+(?:better|stronger|best|strongest)\b"
    r"|\b(?:better|stronger)\b[^.?!]{0,30}\bor\b"
    r"|(?<![A-Za-z])[A-Za-z]{1,5}\s+or\s+[A-Za-z]{1,5}\s+(?:for|in|over|during|this|next|right\s+now)\b",
    re.I)


def _is_comparison(text):
    return bool(_COMPARE_RE.search(text) or _CHOICE_RE.search(text))


_LOWERCASE_NOT_TICKERS = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "vs", "q1", "q2", "q3", "q4", "ytd", "eoy", "etf", "etfs", "month", "months", "fall",
    "per", "plus", "mid", "late", "early", "term", "both", "each", "also", "does", "tell",
    "show", "give", "look", "looks", "been", "were", "will", "into", "onto", "about",
    "gold", "oil", "gas", "corn", "wheat", "bond", "bonds", "cash", "coin", "fx", "tech",
    "bank", "banks", "chip", "chips", "rate", "rates", "yen", "euro", "peso", "real",
    "small", "large", "cap", "caps", "value", "growth", "bull", "bear", "call", "put",
    "puts", "calls", "usa", "china", "japan", "india", "uk", "eu", "summer", "fall",
}


def _lowercase_compare_tickers(text, already):
    """Lower-case tickers in a comparison ("compare nvda amd avgo", "xom vs cvx").

    Only read in a comparison, only for short words that are not ordinary English, and
    every candidate still has to resolve to a TradeWave security before it counts.
    """
    out = []
    for match in re.finditer(r"(?<![A-Za-z0-9.&$\-])([a-z]{2,5})(?![A-Za-z0-9&\-])", text):
        word = match.group(1)
        upper = word.upper()
        if (word in tg._COMMON_ENGLISH_WORDS or word in _LOWERCASE_NOT_TICKERS
                or word in _NAME_STOPWORDS or word in _NUMBER_WORDS
                or upper in _TICKER_STOPWORDS or upper in already
                or word in _KNOWN_COMPANIES):
            continue
        out.append((match.start(), upper))
        if len(out) >= 8:
            break
    return out


def _leaders(studies, key, lowest=False):
    usable = [study for study in studies if study.get(key) is not None]
    if not usable:
        return []
    best = (min if lowest else max)(study[key] for study in usable)
    return [study for study in usable if study[key] == best]


def _joined(studies):
    names = [_esc(study["symbol"]) for study in studies]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def build_comparison_command(message, current_view, user_token, *, today=None,
                             years_cap=None, securities=None, missing=None):
    text = str(message or "").strip()
    if not user_token:
        return None
    current = today or tg._market_today()
    securities = securities if securities is not None else _find_securities(
        text, user_token, current_view)
    if len(securities) < 2:
        return None
    if not _is_comparison(text) and _parse_period(text, current) is None:
        return None
    trace = {"event": "research_comparison"}
    for item in securities:
        if item.get("error"):
            return {"reply": tg._resolution_boundary(item["error"]), "actions": [], "trace": trace}
    # Tickers the user typed define the comparison; a sector word beside them is context.
    named = _explicit_tickers(text, allow_single=True)
    sector_notes = []
    if len([item for item in securities if item["symbol"] in named]) >= 2:
        implied = [item for item in securities if item["symbol"] not in named]
        securities = [item for item in securities if item["symbol"] in named]
        for item in implied:
            wanted = _SECTOR_BY_SYMBOL.get(item["symbol"])
            others = [
                "%s is the %s sector ETF" % (_esc(other["symbol"]), _SECTOR_BY_SYMBOL[other["symbol"]])
                for other in securities
                if other["symbol"] in _SECTOR_BY_SYMBOL
                and not re.search(r"\b(?:%s)\b" % next(
                    pattern for pattern, symbol, _ in _SECTOR_ETFS if symbol == other["symbol"]),
                    text, re.I)]
            if wanted:
                sector_notes.append(
                    "You mentioned %s, but %s; the %s sector ETF is %s. I compared the tickers "
                    "you named - say \"add %s\" to include it."
                    % (wanted, " and ".join(others) if others else "did not name its ticker",
                       wanted, _esc(item["symbol"]), _esc(item["symbol"])))
    extra = securities[_MAX_COMPARE:]
    securities = securities[:_MAX_COMPARE]
    trace["symbols"] = [item["symbol"] for item in securities]
    period = _parse_period(text, current) or (
        _view_period(current_view)
        if re.search(r"\b(?:current|loaded|this)\b", text, re.I) else None)
    default_note = ""
    if period is None:
        # No dates named: compare on a stated default instead of asking. The loaded
        # window is the user's current context; otherwise the next 30 calendar days.
        period = _view_period(current_view)
        if period is not None:
            default_note = ("You did not name dates, so this uses the window loaded in the "
                            "Wave Viewer. Name any window (a month, a quarter, now to year "
                            "end) to rerun it.")
        else:
            period = (current, current + datetime.timedelta(days=_DEFAULT_COMPARE_DAYS - 1),
                      "the next %d days" % _DEFAULT_COMPARE_DAYS)
            default_note = ("You did not name dates, so this uses the next %d calendar days "
                            "from today. Name any window (a month, a quarter, now to year "
                            "end) to rerun it." % _DEFAULT_COMPARE_DAYS)
        trace["default_window"] = True
    start, end, label = period
    days_out = (end - start).days + 1
    if not 1 <= days_out <= 367:
        return None
    pe_cycle = _pe_cycle(text)
    years, explicit = _requested_years(text, current_view)
    if pe_cycle != "cons" and not explicit:
        years = 99
    asked_years = years
    caps = [years_cap] if isinstance(years_cap, int) and years_cap > 0 else [
        _plan(user_token, item["market"])["years_cap"] for item in securities]
    caps = [value for value in caps if isinstance(value, int) and value > 0]
    if caps:
        years = min([years] + caps)

    histories = {
        item["symbol"]: tg._symbol_max_available_years(
            item["market"], item["symbol"], user_token, pe_cycle)
        for item in securities}
    known = [value for value in histories.values() if isinstance(value, int)]
    common = min([years] + known)

    def fetch(count):
        return _parallel(
            lambda item: _study(item, start, days_out, pe_cycle, count, user_token,
                                available=histories[item["symbol"]],
                                comparison_direction="long", report_completed_years=str(count)),
            securities)

    studies = fetch(common)
    for study in studies:
        if study.get("unavailable"):
            return None
        if study.get("error"):
            return {"reply": study["error"], "actions": [], "trace": trace}
    shortest = min(study["n"] for study in studies)
    if any(study["n"] != shortest for study in studies) and shortest >= 1:
        # One symbol has fewer completed years than its listing span implied: rerun every
        # symbol on that common count so the engine computes each record on the same cohort.
        common = shortest
        studies = fetch(common)
        for study in studies:
            if study.get("unavailable"):
                return None
            if study.get("error"):
                return {"reply": study["error"], "actions": [], "trace": trace}
    cohorts = {tuple(row["year"] for row in study["rows"]) for study in studies}
    if len(cohorts) != 1 or not studies[0]["rows"]:
        return {"reply": (
            "TradeWave's completed years for %s do not line up on these dates, so a "
            "side-by-side comparison would not be fair. I have not stated a result."
            % _joined(studies)), "actions": [], "trace": trace}
    year_list = [row["year"] for row in studies[0]["rows"]]
    n = len(year_list)
    cohort = _PE_LABELS.get(studies[0]["pe_cycle"], "years")

    lines = []
    for study in studies:
        sector = _SECTOR_BY_SYMBOL.get(study["symbol"])
        tag = study["name"] or (sector + " sector ETF" if sector else "")
        lines.append(
            "<b>%s</b>%s: up in %d of %d years (%.0f%%), avg %s, median %s, Sharpe %s, "
            "best %s, worst %s, deepest drop inside the window %s"
            % (_esc(study["symbol"]), (" (%s)" % _esc(tag)) if tag else "", study["wins"],
               study["n"], study["win_pct"] or 0.0, tg._fmt_pct(study["avg"]),
               tg._fmt_pct(study["median"]),
               "%.2f" % study["sharpe"] if study["sharpe"] is not None else "n/a",
               tg._fmt_pct(max(row["ret"] for row in study["rows"])),
               tg._fmt_pct(min(row["ret"] for row in study["rows"])),
               tg._fmt_pct(min(row["low"] for row in study["rows"]))))
    reads = []
    top = _leaders(studies, "avg")
    if top:
        reads.append("Higher average return: %s at %s." % (_joined(top), tg._fmt_pct(top[0]["avg"])))
    top = _leaders(studies, "win_pct")
    if top:
        reads.append("Most consistent: %s, up in %d of %d years." % (_joined(top), top[0]["wins"], n))
    top = _leaders(studies, "sharpe")
    if top and top[0]["sharpe"] is not None:
        reads.append("Best Sharpe Ratio: %s at %.2f." % (_joined(top), top[0]["sharpe"]))

    notes = list(sector_notes)
    if missing:
        notes.insert(0, "I could not find %s as a TradeWave symbol, so %s not in this comparison."
                     % (", ".join(_esc(symbol) for symbol in missing[:4]),
                        "it is" if len(missing) == 1 else "they are"))
    if default_note:
        notes.insert(0, default_note)
    if _ADVICE_RE.search(text):
        notes.insert(0, _ADVICE_BOUNDARY)
    if explicit and asked_years > years:
        notes.append("You asked for %d years; your plan's lookback is capped at %d."
                     % (asked_years, years))
    if common < years and explicit:
        short = min(studies, key=lambda study: study.get("available_years") or 999)
        notes.append(
            "You asked for %d years; %s limits the shared history, so every symbol uses the "
            "same %d completed years." % (years, _esc(short["symbol"]), n))
    if extra:
        notes.append("I compared the first %d symbols; a comparison holds up to %d."
                     % (_MAX_COMPARE, _MAX_COMPARE))
    heading = "%s, %s" % (" vs ".join(_esc(study["symbol"]) for study in studies),
                          format_date_range(studies[0]["entry"], studies[0]["end"]))
    reply = (
        "<div class=\"tara-analysis\">"
        "<div class=\"tara-analysis-section tara-analysis-lead\"><span class=\"tara-analysis-heading\">"
        "%s</span> %s%d calendar days. Same dates and the same %d completed %s (%d-%d) for "
        "every symbol, long direction.</div>"
        "<div class=\"tara-analysis-section\">%s</div>"
        "<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">Read</span> %s</div>"
        "<div class=\"tara-analysis-section tara-analysis-scope\"><span class=\"tara-analysis-heading\">"
        "Scope</span> %sI am loading %s in the Wave Viewer; open Analysis, then Compare Symbols, "
        "for the full report. Historical results are not a forecast.</div></div>"
        % (heading, "" if "\u2013" in label else _esc(label[:1].upper() + label[1:]) + ", ",
           studies[0]["days"], n, cohort, year_list[0], year_list[-1],
           "<br>".join(lines), " ".join(reads),
           (" ".join(notes) + " ") if notes else "", _esc(studies[0]["symbol"])))
    actions = [{"type": "set_view", "spec": studies[0]["spec"]}] if studies[0]["spec"] else []
    return {"reply": reply, "actions": actions, "trace": trace, "studies": studies}


# ---------------------------------------------------------------------------
# 5. Date of the low / high inside a pattern
# ---------------------------------------------------------------------------

# The question must ask WHEN an extreme happened: a when-word and an extreme NOUN in the same
# clause. "How high does it go", "is it near its high", "how high is its win rate" and "why
# is 1930 so low" are different questions and are left to their own paths.
_EXTREME_LOW = (r"(?:bottom(?:ed|s|ing)?(?:\s+out)?|trough(?:s|ed)?|"
                r"(?:its|the|a|their|that|each|every)\s+(?:\w+\s+)?low(?:s|est\s+point)?(?:\s+point)?|"
                r"hit(?:s|ting)?\s+(?:its\s+|the\s+|a\s+)?low|lows?\s+(?:date|point|day)|"
                r"mae(?:\s+(?:date|point|day))?|maximum\s+adverse\s+excursion|"
                r"deepest\s+(?:drop|drawdown|point))")
_EXTREME_HIGH = (r"(?:peak(?:ed|s|ing)?|top(?:ped|s)?\s+out|topped|"
                 r"(?:its|the|a|their|that|each|every)\s+(?:\w+\s+)?high(?:s|est\s+point)?(?:\s+point)?|"
                 r"hit(?:s|ting)?\s+(?:its\s+|the\s+|a\s+)?high|highs?\s+(?:date|point|day)|"
                 r"mfe(?:\s+(?:date|point|day))?|maximum\s+favou?rable\s+excursion)")
_EXTREME_TAIL_GUARD = (r"(?!\s+(?:win|sharpe|returns?|rate|risk|average|avg|probab\w*|price|"
                       r"season\w*|time|period|months?|quarter|conviction|confidence|quality|"
                       r"volume|year|years|score|percent\w*))")
_WHEN_WORDS = (r"(?:when|what\s+(?:date|day|month|time(?:\s+of\s+year)?)|which\s+(?:date|day|month)|"
               r"latest|earliest|how\s+(?:late|early|soon)|on\s+what\s+(?:date|day)|"
               r"(?:typical(?:ly)?|usual(?:ly)?)\s+(?:date|day|time|bottom|peak|low|high))")
_LOW_RE = re.compile(r"\b" + _EXTREME_LOW + r"\b" + _EXTREME_TAIL_GUARD, re.I)
_HIGH_RE = re.compile(r"\b" + _EXTREME_HIGH + r"\b" + _EXTREME_TAIL_GUARD, re.I)
_WHEN_RE = re.compile(r"\b" + _WHEN_WORDS + r"\b", re.I)
_NOT_A_DATE_QUESTION_RE = re.compile(
    r"^\s*why\b|\bhow\s+(?:high|low|deep|far|much|big|bad)\b|\bnear\s+(?:its|the)\s+(?:high|low)\b|"
    r"\b(?:latest|current|today'?s?)\s+price\b", re.I)
_LOADED_TARGET_RE = re.compile(
    r"\b(?:this|the\s+(?:current|loaded)|current|loaded|my)\s+(?:loaded\s+)?"
    r"(?:pattern|window|chart|setup|trade|study)\b", re.I)


def _extreme_request(text):
    """'low' / 'high' when a single clause asks WHEN that extreme occurred, else None."""

    for clause in re.split(r"[,.;?!]|\s+-\s+|\s+(?:and|but)\s+(?=(?:why|how|what|is|are|does|do)\b)", text):
        if not clause.strip() or _NOT_A_DATE_QUESTION_RE.search(clause):
            continue
        if not _WHEN_RE.search(clause):
            continue
        low, high = bool(_LOW_RE.search(clause)), bool(_HIGH_RE.search(clause))
        if low != high:
            return "low" if low else "high"
    return None


def build_excursion_date_command(message, current_view, user_token, *, today=None):
    text = str(message or "").strip()
    wanted = _extreme_request(text) if user_token else None
    if wanted is None:
        return None
    wants_low = wanted == "low"
    current = today or tg._market_today()
    trace = {"event": "research_excursion_dates"}
    if tg._HUNDRED_YEAR_SECURITY_RE.search(text):
        spec = hundred_year_view_spec(current)
        years_value = hundred_year_years_value(current)
        title = "The 100-Year Pattern"
        subject = "SPX, PE+2 (midterm years), Sep 27 through Jul 18, %d calendar days" % (
            HUNDRED_YEAR_DISPLAY_DAYS)
    elif _LOADED_TARGET_RE.search(text) and isinstance(current_view, dict) and current_view.get("symbol"):
        period = _view_period(current_view)
        cycle = tg._VS_PE.get(str(current_view.get("pe_cycle") or "cons").lower())
        raw_years = str(current_view.get("years") or "")
        market = str(current_view.get("market") or "")
        if period is None or cycle is None or not raw_years.isdigit() or market not in tg._VS_MARKETS:
            return None
        spec = {"market": market, "symbol": str(current_view["symbol"]).upper(),
                "entry_date": period[0].isoformat(), "days_out": (period[1] - period[0]).days + 1,
                "years": int(raw_years), "pe_cycle": cycle}
        years_value = _years_value(cycle, int(raw_years))
        title = "%s loaded pattern" % _esc(spec["symbol"])
        subject = "%s, %d calendar days, %s" % (
            format_date_range(period[0], period[1]), spec["days_out"], _PE_LABELS.get(cycle, ""))
    else:
        return None
    trace["symbol"] = spec["symbol"]

    status, payload = _engine_chart(
        spec["market"], spec["symbol"], spec["entry_date"], spec["days_out"], years_value,
        user_token, excursion_dates="1")
    if status == 403:
        return {"reply": "<b>%s is outside this account's available markets.</b>" % _esc(spec["symbol"]),
                "actions": [], "trace": trace}
    if status != 200 or not isinstance(payload, dict):
        return None
    if not _echo_matches(payload, spec["symbol"], spec["entry_date"], spec["days_out"],
                         spec["years"], spec["pe_cycle"]):
        return {"reply": (
            "TradeWave returned a different window than %s for this plan, so I won't attach "
            "dates to it. On a date-locked market only today's start date can be studied."
            % title), "actions": [], "trace": trace}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    short = str(stats.get("Trade Dir") or "long").lower() == "short"
    date_key, day_key = ("low_date", "low_day") if wants_low else ("high_date", "high_day")
    value_key = "low" if wants_low else "high"
    word = "low" if wants_low else "high"
    # The low is the adverse point of a long pattern and the favorable point of a short one.
    measure = "MFE" if (wants_low == short) else "MAE"
    verb = "bottomed" if wants_low else "peaked"
    window_days = spec["days_out"]
    dated = []
    for raw in payload.get("ChartData4") or []:
        if not isinstance(raw, dict) or raw.get("completed") is False:
            continue
        try:
            point = datetime.date.fromisoformat(str(raw[date_key]))
            day_number = int(raw[day_key])
            parts = str(raw.get("pct") or "").split(",")
            value = float(parts[2 if wants_low else 1])
            year = int(raw["year"])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        dated.append({"year": year, "point": point, "day": day_number, value_key: value,
                      "at_entry": raw.get("entry_trade_date") == raw.get(date_key),
                      "at_exit": raw.get("exit_trade_date") == raw.get(date_key)})
    if not dated:
        return {"reply": (
            "TradeWave's engine reports how far each year's %s was from entry (%s) for %s, but "
            "the date of that %s is not available in this response, so I won't guess one. Turn "
            "on the %s overlay in the Wave Viewer to see each year's extreme."
            % (word, measure, title, word, measure)), "actions": [], "trace": trace}

    total = len(dated)
    ranked = sorted(dated, key=lambda item: (item["day"], item["year"]), reverse=True)
    latest, earliest = ranked[0], ranked[-1]
    recent = max(dated, key=lambda item: item["year"])

    def position(item):
        if item["at_entry"]:
            return "%s, the entry session (it never traded %s its entry close)" % (
                _long_date(item["point"]), "below" if wants_low else "above")
        if item["at_exit"]:
            return "%s, the exit session" % _long_date(item["point"])
        return "%s, calendar day %d of %d (%s vs the entry close)" % (
            _long_date(item["point"]), item["day"], window_days, tg._fmt_pct(item[value_key]))

    def cycle(item):
        return "%d cycle: %s" % (item["year"], position(item))

    latest_line = "The latest the pattern has %s: <b>%s</b>." % (verb, cycle(latest))
    earliest_line = "The earliest: %s." % cycle(earliest)
    if re.search(r"\bearliest\b|\bhow\s+(?:early|soon)\b", text, re.I):
        lead = "The earliest the pattern has %s: <b>%s</b>." % (verb, cycle(earliest))
        detail = [latest_line]
    else:
        lead = latest_line
        detail = [earliest_line]
    detail.insert(0, "Latest three: " + "; ".join(cycle(item) for item in ranked[:3]) + ".")
    detail.append("Most recent completed cycle: " + position(recent) + ".")
    active = [row for row in payload.get("ChartData4") or []
              if isinstance(row, dict) and row.get("completed") is False and row.get(date_key)]
    if active:
        try:
            point = datetime.date.fromisoformat(str(active[-1][date_key]))
            detail.append(
                "The %s cycle is still running: its %s so far was %s, and it is excluded from "
                "the completed record." % (active[-1].get("year"), word, _long_date(point)))
        except ValueError:
            pass
    reply = (
        "<div class=\"tara-analysis\">"
        "<div class=\"tara-analysis-section tara-analysis-lead\"><span class=\"tara-analysis-heading\">"
        "%s: date of the %s</span> %s</div>"
        "<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">Across %d completed "
        "cycles</span> %s</div>"
        "<div class=\"tara-analysis-section tara-analysis-scope\"><span class=\"tara-analysis-heading\">"
        "Scope</span> %s. The %s is each cycle's %s traded price after entry - the point "
        "TradeWave's %s is measured from for this %s pattern. Dates and day numbers are the "
        "engine's, with the window's start date as day 1. History describes past cycles; it does "
        "not time the current one.</div></div>"
        % (title, word, lead, total, "<br>".join(detail), subject, word,
           "lowest" if wants_low else "highest", measure, "short" if short else "long"))
    cleaned = tg._validate_view_spec(spec)
    actions = [{"type": "set_view", "spec": cleaned}] if cleaned else []
    return {"reply": reply, "actions": actions, "trace": trace, "dated": dated}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_research_command(message, current_view, user_token, *, investor_intent=None,
                           table_market=None, years_cap=None, today=None):
    """Return {'reply', 'actions', 'trace'} for a supported research request, else None."""

    text = str(message or "").strip()
    if not text or not user_token or investor_intent not in _ALLOWED_INVESTOR_INTENTS:
        return None
    try:
        command = build_excursion_date_command(text, current_view, user_token, today=today)
        if command is not None:
            return command
        if not (investor_intent in {"seasonal_etf", "weak_etf"}
                and not re.search(r"\b(?:win[-\s]*rate|sharpe|top\s+\d|rank)\b", text, re.I)):
            command = build_screen_command(
                text, user_token, today=today, table_market=table_market, years_cap=years_cap)
            if command is not None:
                return command
        if _names_several_cycles(text):
            return None
        compare = _is_comparison(text)
        study_shape = bool(_STUDY_VERB_RE.search(text)) and _parse_period(
            text, today or tg._market_today()) is not None
        if not (compare or study_shape):
            return None
        unresolved = []
        securities = _find_securities(text, user_token, current_view, unresolved=unresolved)
        if compare and len(securities) < 2:
            return None              # one side did not resolve: never answer for the other alone
        if compare or (len(securities) >= 2 and study_shape):
            # A lower-case word that did not resolve is only reported as a missing ticker
            # when the message is plainly a ticker list (two or more others resolved).
            missing = [symbol for symbol, was_typed in unresolved
                       if was_typed or len(securities) >= 2]
            command = build_comparison_command(
                text, current_view, user_token, today=today, years_cap=years_cap,
                securities=securities, missing=missing)
            if command is not None:
                return command
            if len(securities) >= 2:
                return None          # two instruments were named: never answer for just one
        return build_window_study_command(
            text, current_view, user_token, today=today, years_cap=years_cap,
            securities=securities)
    except Exception:  # never let a research shortcut break the normal chat path
        log.exception("tara research command failed; falling back to the model path")
        return None
