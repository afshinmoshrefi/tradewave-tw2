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
_FANOUT_WORKERS = 5
_MAX_SCREEN_DAYS = 31
_DEFAULT_LOOKBACK = 10
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 15
_MAX_COMPARE = 4

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


def _parallel(function, items):
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(_FANOUT_WORKERS, len(items))) as pool:
        return list(pool.map(function, items))


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
_SHORT_RE = re.compile(
    r"\b(?:bearish|short(?:s|ing)?|weak(?:est|ness)?|declin\w*|fall(?:s|ing)?|drop(?:s|ping)?|"
    r"sell[-\s]?offs?|downside)\b", re.I)
_SHORT_TERM_RE = re.compile(r"\bshort[-\s]+(?:term|dated|hold)", re.I)
_LONG_RE = re.compile(r"\b(?:bullish|long|rise|rising|strong(?:est)?|upside|buy)\b", re.I)
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
    r"average\s+(?:return|profit|gain)|hold(?:s|ing)?|rise|fall)\b", re.I)
_TICKER_STOPWORDS = {
    "AI", "AIS", "AVG", "AVGP", "DJIA", "DOW", "ETF", "ETFS", "FOMC", "MAE", "MFE",
    "ML", "NASDAQ", "NDX", "PE", "Q1", "Q2", "Q3", "Q4", "SP", "SR", "TOP", "US",
    "USA", "YTD", "II", "OK", "TARA", "SPX", "AND", "OR", "VS", "U.S", "AVG", "MIN",
    "MAX", "EOY", "PE0", "PE1", "PE2", "PE3", "TWR", "TWA",
}


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


def _explicit_tickers(text):
    """Upper-case ticker-like tokens the user typed (an all-caps message has none)."""

    letters = [ch for ch in text if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.7:
        return []
    found = []
    for match in re.finditer(r"(?<![A-Za-z0-9.&\-])([A-Z][A-Z0-9.\-]{1,9})(?![A-Za-z0-9&\-])", text):
        token = match.group(1).rstrip(".-")
        if len(token) > 1 and token not in _TICKER_STOPWORDS and token not in found:
            found.append(token)
    return found


def _direction(text):
    cleaned = _SHORT_TERM_RE.sub(" ", text)
    if _SHORT_RE.search(cleaned):
        return "short"
    return "long"


def _lookback_years(text):
    for pattern in (
        r"\b(?:last|past|previous|prior|over)\s+(?:the\s+)?(?:last\s+|past\s+)?(\d{1,2})\s*(?:-|\s)?(?:consecutive\s+)?years?\b",
        r"\b(\d{1,2})\s*(?:-|\s)?years?\s+(?:view|look[-\s]?back|history|window|seasonal|trend|record|of\s+history)\b",
        r"\b(\d{1,2})\s+of\s+(\d{1,2})\s+years\b",
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


# ---------------------------------------------------------------------------
# 1 + 2. Index screens
# ---------------------------------------------------------------------------

def _entry_window(text, today):
    """Resolve the ENTRY-date window of a screen: (first, last, label, note)."""

    lower = text.lower()
    week_start = today - datetime.timedelta(days=today.weekday())
    match = re.search(
        r"\b(?:next|coming|following|within|in\s+the\s+next|over\s+the\s+next)\s+(?:the\s+)?%s\s*"
        r"(?:calendar\s+|trading\s+)?(day|week|month)s?\b" % _NUM, lower)
    if match:
        count = _int(match.group(1)) or 1
        span = count * {"day": 1, "week": 7, "month": 30}[match.group(2)]
        note = ""
        if span > _MAX_SCREEN_DAYS:
            span = _MAX_SCREEN_DAYS
            note = "The entry window is capped at %d days per screen." % _MAX_SCREEN_DAYS
        last = today + datetime.timedelta(days=span - 1)
        return today, last, "in the next %d days" % span, note
    if re.search(r"\bnext\s+week\b", lower):
        first = week_start + datetime.timedelta(days=7)
        return first, first + datetime.timedelta(days=6), "next week", ""
    if re.search(r"\b(?:this|htis|tihs|ths|the\s+current|the\s+coming)\s+week\b", lower):
        return week_start, week_start + datetime.timedelta(days=6), "this week", ""
    if re.search(r"\bnext\s+month\b", lower):
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        first = datetime.date(year, month, 1)
        last = datetime.date(year, month, calendar.monthrange(year, month)[1])
        return first, last, "in " + first.strftime("%B"), ""
    if re.search(r"\b(?:this|the\s+current)\s+month\b", lower):
        last = datetime.date(today.year, today.month,
                             calendar.monthrange(today.year, today.month)[1])
        return today, last, "in the rest of %s" % today.strftime("%B"), ""
    if re.search(r"\btomorrow\b", lower):
        first = (today if re.search(r"\btoday\b|\b\w+\s+or\s+tomorrow\b", lower)
                 else today + datetime.timedelta(days=1))
        last = today + datetime.timedelta(days=2 if lower.count("tomorrow") > 1 else 1)
        return first, last, "in the next few days", ""
    return today, today, "today", ""


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
    if _explicit_tickers(text):
        return None
    if re.search(r"\b(?:compare|versus|vs\.?|against)\b", text, re.I):
        return None
    # The detector knows seasonal statistics only; other screening criteria are not its data.
    if _OFF_TOPIC_SCREEN_RE.search(text) or not _SEASONAL_SCREEN_CUE_RE.search(text):
        return None
    if re.search(r"\b(?:sector|industry|retail|technology|tech)\b", text, re.I) and universe[1] == "ETF":
        return None
    window_phrase = bool(re.search(
        r"\b(?:today|tomorrow|now|currently|(?:this|htis|tihs|ths)\s+(?:week|month)|next\s+(?:week|month)|"
        r"(?:next|coming|within)\s+(?:the\s+)?(?:\d+|\w+)\s+(?:calendar\s+|trading\s+)?(?:day|week|month)s?|"
        r"this\s+time\s+of\s+(?:the\s+)?year)\b", text, re.I))
    directional = bool(_SHORT_RE.search(_SHORT_TERM_RE.sub(" ", text)) or _LONG_RE.search(text))
    if not (window_phrase or explicit_filter or directional
            or _RANK_WIN_RE.search(text) or _RANK_SHARPE_RE.search(text) or _RANK_AVG_RE.search(text)):
        return None

    first, last, label, note = _entry_window(text, today)
    year_end = datetime.date(today.year, 12, 31)
    if first > year_end:
        return None
    last = min(last, year_end)

    limit = _DEFAULT_LIMIT
    match = (re.search(r"\b(?:top|best|strongest)\s*-?\s*%s\b" % _NUM, text, re.I)
             or re.search(r"\b%s\s+(?:best|top|strongest)\b" % _NUM, text, re.I))
    if match and _int(match.group(1)):
        limit = max(1, min(_MAX_LIMIT, _int(match.group(1))))

    year1 = _lookback_years(text) or _DEFAULT_LOOKBACK
    min_wins = None
    match = re.search(r"\b(\d{1,2})\s+(?:of|out\s+of|ou[ft]\s+of)\s+(\d{1,2})\s+years\b", text, re.I)
    if match and int(match.group(1)) <= int(match.group(2)):
        min_wins, year1 = int(match.group(1)), int(match.group(2))
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
        "market": universe[0], "universe": universe[1], "direction": _direction(text),
        "rank": rank, "first": first, "last": last, "window_label": label,
        "window_note": note, "hold": _hold_filter(text), "limit": limit, "year1": year1,
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
        day_range = "%d-%d" % (max(0, request["hold"][0] - 1), max(0, request["hold"][1] - 1))
    days = _request_days(request["first"], request["last"])
    single_day = request["first"] == request["last"]
    want = "short" if request["direction"] == "short" else "long"

    def fetch(day):
        return _engine_opplist(request["market"], day, request["year1"], year2, day_range, token)

    rows, statuses, failed = [], [], 0
    for status, payload in _parallel(fetch, days):
        statuses.append(status)
        if payload is None:
            failed += 1
            continue
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
    return rows, statuses, failed


def _verify_row(request, row, token):
    """Attach the engine's completed-year record for one detected pattern."""

    status, payload = _engine_chart(
        request["market"], row["symbol"], row["date"], row["days_out"], str(request["year1"]),
        token, comparison_direction=row["direction"])
    stats = payload.get("stats") if status == 200 and isinstance(payload, dict) else None
    if not isinstance(stats, dict) or not stats:
        return None
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
        avg = "avg move %s" % tg._fmt_pct(-row["avg"])
    else:
        record = "profitable in %d of %d years (%s)" % (row["wins"], row["n"], win_pct)
        avg = "avg return %s" % tg._fmt_pct(row["avg"])
    return "%d. <b>%s</b> - starts %s, %d-day window: %s, %s, Sharpe %.2f" % (
        index, _esc(row["symbol"]), entry, row["days_out"], record, avg, row["sharpe"])


def _market_label(request):
    return request["universe"] or tg.config.available_resources.get(
        request["market"], "market %s" % request["market"]).title()


def build_screen_command(message, user_token, *, today=None, table_market=None):
    text = str(message or "").strip()
    current = today or tg._market_today()
    request = _screen_request(text, current, table_market)
    if request is None or not user_token:
        return None
    label = _market_label(request)
    trace = {"event": "research_screen", "market": request["market"],
             "direction": request["direction"], "rank": request["rank"],
             "entry_first": request["first"].isoformat(),
             "entry_last": request["last"].isoformat(), "candidates": 0}

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
    pool_target = min(20, request["limit"] + 6)

    # Win-rate ranking walks the detector's bands from "won every year" downward, so the
    # strictest record is collected first; other rankings read the widest in-band table.
    tiers = (range(request["year1"], wanted - 1, -1)
             if request["rank"] == "win_rate" else [wanted])
    pool, screened, failed, statuses, reached = {}, 0, 0, [], wanted
    for tier in tiers:
        reached = tier
        rows, tier_statuses, tier_failed = _detected_rows(request, tier, user_token)
        statuses.extend(tier_statuses)
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
    verified = [row for row in _parallel(
        lambda row: _verify_row(request, row, user_token), ordered) if row]
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

    side = "bearish" if request["direction"] == "short" else "bullish"
    dates = (_day_label(request["first"]) if request["first"] == request["last"]
             else format_date_range(request["first"], request["last"]))
    rank_text = {"win_rate": "win rate, then Sharpe Ratio", "avg": "average return",
                 "sharpe": "Sharpe Ratio"}[request["rank"]]
    hold = request["hold"]
    hold_text = ""
    if hold:
        hold_text = (" Only %d-day windows." % hold[0] if hold[0] == hold[1]
                     else " Only windows of %d to %d days." % hold)
    if not shown:
        return {"reply": (
            "<b>No %s %s seasonal windows matched.</b> TradeWave's detector found no "
            "%s pattern that starts %s (%s) and won at least %d of the last %d years%s "
            "Widen the dates, lower the win-rate floor, or drop a filter and I will run it again."
            % (_esc(label), side, side, request["window_label"], dates, wanted,
               request["year1"], ("." + hold_text) if hold_text else ".")),
            "actions": [], "trace": trace}

    interpretation = ""
    if re.search(r"\bnext\s+%s\s+days?\b" % _NUM, text, re.I) and not hold:
        span = (request["last"] - request["first"]).days + 1
        interpretation = (
            " I read \"next %d days\" as windows that START in the next %d days, at any "
            "length; ask for \"%d-day holds\" to fix the holding period instead." % (span, span, span))
    lead = (
        "<div class=\"tara-analysis-section tara-analysis-lead\"><span class=\"tara-analysis-heading\">"
        "%s %s seasonal windows starting %s (%s)</span> Top %d by %s over a %d-year lookback.%s%s%s</div>"
        % (_esc(label), side, request["window_label"], dates, len(shown), rank_text,
           request["year1"], hold_text,
           (" A short-direction win means the stock fell during the window."
            if request["direction"] == "short" else ""), interpretation))
    lines = "<br>".join(
        _screen_line(index, row, request["direction"]) for index, row in enumerate(shown, 1))
    scope_bits = [
        "TradeWave's detector listed %d %s pattern%s for these dates that won at least %d of "
        "the last %d years; each record above is the engine's completed-year result."
        % (screened, side, "" if screened == 1 else "s", reached, request["year1"])]
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
_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
_NAME_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "plc", "sa",
    "nv", "ag", "holdings", "holding", "group", "the", "class", "a", "b", "c", "com",
    "trust", "lp",
}
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
    "with", "year", "years", "you", "your", "target", "best buy", "gap", "match", "block",
    "win", "early", "half", "side", "same", "key", "life", "general", "national",
} | set(_MONTHS)


def _normalize_company(name):
    words = re.sub(r"\(.*?\)", " ", str(name or "").lower())
    words = re.sub(r"\.com\b", " ", words)
    tokens = re.findall(r"[a-z0-9&']+", words.replace(".", " "))
    while tokens and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _company_symbol(phrase, token, cache):
    """Resolve a plain company name against the engine's US security list (exact name)."""

    if "names" not in cache:
        names = _engine_symbol_names("2", token) or _engine_symbol_names("0", token) or {}
        index = {}
        for symbol, name in names.items():
            index.setdefault(_normalize_company(name), []).append(str(symbol).upper())
        cache["names"] = index
    matches = cache["names"].get(phrase) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Share classes of one company (GOOGL/GOOG): take the primary first listing.
        return sorted(matches, key=lambda symbol: (len(symbol), symbol))[0] if len(
            {symbol[:3] for symbol in matches}) == 1 else None
    return None


def _find_securities(text, token, current_view=None, allow_names=True):
    """Ordered, de-duplicated securities named in the request: [{symbol, market, name}]."""

    found = []          # (position, symbol, market_hint, sector)

    def add(position, symbol, market=None, sector=None):
        if all(symbol != item[1] for item in found):
            found.append((position, symbol, market, sector))

    masked = text
    if _SECTOR_CONTEXT_RE.search(text):
        for match in _SECTOR_RE.finditer(text):
            for pattern, symbol, sector in _SECTOR_ETFS:
                if re.fullmatch(pattern, match.group(1), re.I):
                    add(match.start(), symbol, "11", sector)
                    break
        masked = _SECTOR_RE.sub(lambda m: " " * len(m.group(0)), masked)
    for ticker in _explicit_tickers(text):
        position = text.find(ticker)
        add(position, ticker)
        masked = masked.replace(ticker, " " * len(ticker))
    for pattern, symbol, market in _NAMED_SECURITIES:
        match = re.search(r"(?<![A-Za-z&])(?:%s)(?![A-Za-z&])" % pattern, masked, re.I)
        if match and not re.search(r"\b(?:stocks|companies|names)\b", masked[match.end():match.end() + 12], re.I):
            add(match.start(), symbol, market)
            masked = masked[:match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
    for match in re.finditer(r"(?<![A-Za-z])([A-Za-z]{3})/?([A-Za-z]{3})(?![A-Za-z])", masked):
        if match.group(1).upper() in _CURRENCIES and match.group(2).upper() in _CURRENCIES:
            add(match.start(), (match.group(1) + match.group(2)).upper(), "8")
            masked = masked[:match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
    if re.search(r"\b(?:current|loaded|this)\s+(?:loaded\s+)?(?:pattern|chart|symbol|stock|security|setup)\b", text, re.I):
        view = current_view if isinstance(current_view, dict) else {}
        symbol = str(view.get("symbol") or "").strip().upper()
        if tg._VS_SYMBOL_RE.fullmatch(symbol):
            add(len(text), symbol, str(view.get("market") or "") or None)
    if allow_names and token:
        cache = {}
        words = [(m.start(), m.group(0).lower()) for m in re.finditer(r"[A-Za-z][A-Za-z&']*", masked)]
        index = 0
        while index < len(words):
            matched = False
            for size in (3, 2, 1):
                chunk = words[index:index + size]
                if len(chunk) < size:
                    continue
                phrase = " ".join(word for _, word in chunk)
                phrase = re.sub(r"'s\b", "", phrase)
                if all(word in _NAME_STOPWORDS for word in phrase.split()) or (
                        phrase in _NAME_STOPWORDS) or len(phrase) < 3:
                    continue
                symbol = _company_symbol(phrase, token, cache)
                if symbol:
                    add(chunk[0][0], symbol, "2")
                    index += size
                    matched = True
                    break
            if not matched:
                index += 1

    resolved = []
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
                continue            # not a TradeWave security (or lookup down): not a slot
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


def _parse_period(text, today):
    """Resolve an explicit study window to (start, end, label), else None."""

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

    ahead = re.search(r"\b(?:over|in|for|during)?\s*the\s+next\s+%s\s+(day|week|month)s?\b" % _NUM, lower)
    if ahead and _int(ahead.group(1)):
        span_days = _int(ahead.group(1)) * {"day": 1, "week": 7, "month": 30}[ahead.group(2)]
        if 1 <= span_days <= 367:
            end = today + datetime.timedelta(days=span_days - 1)
            return today, end, "the next %d days" % span_days

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


def _study(security, start, days_out, pe_cycle, years, token, **params):
    """Fetch one engine study and return a normalized record or an error reply."""

    symbol, market = security["symbol"], security["market"]
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
    if status is None:
        return {"error": "unavailable", "unavailable": True}
    if status == 403:
        return {"error": "<b>%s is outside this account's available markets.</b> I cannot "
                         "load or summarize that chart without the required market access."
                         % _esc(symbol)}
    stats = payload.get("stats") if status == 200 and isinstance(payload, dict) else None
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
    spec = tg._validate_view_spec({
        "market": str(echo.get("market")), "symbol": str(echo.get("symbol") or "").upper(),
        "entry_date": entry.isoformat(), "days_out": days, "years": echo_years,
        "pe_cycle": str(echo.get("pe_cycle") or "cons"),
    })
    return {
        "symbol": symbol, "market": market, "name": security.get("name") or "",
        "entry": entry, "end": entry + datetime.timedelta(days=days - 1), "days": days,
        "years": echo_years, "requested_years": int(years), "available_years": available,
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


def _extremes_text(rows):
    if not rows:
        return ""
    best = max(rows, key=lambda row: row["ret"])
    worst = min(rows, key=lambda row: row["ret"])
    deepest = min(rows, key=lambda row: row["low"])
    highest = max(rows, key=lambda row: row["high"])
    return (
        "Best year: %d at %s. Worst year: %d at %s. Largest run-up inside the window "
        "(MFE): %s in %d. Deepest drop inside the window (MAE): %s in %d."
        % (best["year"], tg._fmt_pct(best["ret"]), worst["year"], tg._fmt_pct(worst["ret"]),
           tg._fmt_pct(highest["high"]), highest["year"], tg._fmt_pct(deepest["low"]),
           deepest["year"]))


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
    if isinstance(years_cap, int) and years_cap > 0:
        years = min(years, years_cap)
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
    if explicit and study["years"] < study["requested_years"] and study["pe_cycle"] == "cons":
        history_note = (" You asked for %d years; TradeWave has %d available for %s on this plan "
                        "and history." % (study["requested_years"], study["years"], symbol))
    elif study["pe_cycle"] == "cons" and study["n"] > study["years"]:
        history_note = (" This year's window has already finished, so TradeWave counts it with "
                        "the %d-year lookback." % study["years"])
    win_pct = "%.0f%%" % study["win_pct"] if study["win_pct"] is not None else "n/a"
    if study["direction"] == "short":
        record = (
            "TradeWave reads this window as a short-direction pattern: %s fell in %d of %d "
            "completed %s (%s). Short-side results: average %s (the underlying averaged %s), "
            "median %s, Sharpe Ratio %s."
            % (symbol, study["wins"], study["n"], cohort, win_pct, tg._fmt_pct(study["avg"]),
               tg._fmt_pct(-study["avg"]) if study["avg"] is not None else "unavailable",
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
        "Scope</span> I am loading this exact study in the Wave Viewer so every year is visible. "
        "Historical results are not a forecast.</div></div>"
        % (title, study["days"], _esc(label), study["n"], cohort, history_note, record,
           _extremes_text(study["rows"])))
    actions = [{"type": "set_view", "spec": study["spec"]}] if study["spec"] else []
    return {"reply": reply, "actions": actions, "trace": trace, "study": study}


# ---------------------------------------------------------------------------
# 4. Symbol comparison
# ---------------------------------------------------------------------------

_COMPARE_RE = re.compile(
    r"\b(?:compare|comparison|compared|versus|vs\.?|against|side[-\s]by[-\s]side|"
    r"better\s+than|outperform(?:s|ed)?|stack(?:s)?\s+up)\b", re.I)


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
                             years_cap=None, securities=None):
    text = str(message or "").strip()
    if not user_token:
        return None
    current = today or tg._market_today()
    securities = securities if securities is not None else _find_securities(
        text, user_token, current_view)
    if len(securities) < 2:
        return None
    if not _COMPARE_RE.search(text) and _parse_period(text, current) is None:
        return None
    trace = {"event": "research_comparison"}
    for item in securities:
        if item.get("error"):
            return {"reply": tg._resolution_boundary(item["error"]), "actions": [], "trace": trace}
    # Tickers the user typed define the comparison; a sector word beside them is context.
    named = _explicit_tickers(text)
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
    if period is None:
        return {"reply": (
            "<b>Which dates should I compare %s over?</b> Give me a window such as the 4th "
            "quarter, November through April, or now to year end, and I will run every symbol "
            "on the same dates and the same completed years."
            % _joined(securities)), "actions": [], "trace": trace}
    start, end, label = period
    days_out = (end - start).days + 1
    if not 1 <= days_out <= 367:
        return None
    pe_cycle = _pe_cycle(text)
    years, explicit = _requested_years(text, current_view)
    if pe_cycle != "cons" and not explicit:
        years = 99
    if isinstance(years_cap, int) and years_cap > 0:
        years = min(years, years_cap)

    histories = [
        tg._symbol_max_available_years(item["market"], item["symbol"], user_token, pe_cycle)
        for item in securities]
    known = [value for value in histories if isinstance(value, int)]
    common = min([years] + known)

    def fetch(count):
        return _parallel(
            lambda item: _study(item, start, days_out, pe_cycle, count, user_token,
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

_LOW_RE = re.compile(
    r"\b(?:bottom(?:ed|s|ing)?(?:\s+out)?|low(?:est)?(?:\s+point)?(?!\s+(?:win|sharpe|return|risk|average|avg|probab))|troughs?|"
    r"max(?:imum)?\s+(?:drawdown|adverse(?:\s+excursion)?)|deepest\s+(?:drop|drawdown)|mae)\b", re.I)
_HIGH_RE = re.compile(
    r"\b(?:peak(?:ed|s|ing)?|top(?:ped|s)?(?:\s+out)?(?!\s+(?:\d|ten|five|three))|"
    r"high(?:est)?(?:\s+point)?(?!\s+(?:win|sharpe|return|average|avg|probab))|"
    r"max(?:imum)?\s+favou?rable(?:\s+excursion)?|mfe)\b", re.I)
_WHEN_RE = re.compile(
    r"\b(?:when|what\s+(?:date|day|month|time)|which\s+(?:date|day|month)|latest|earliest|"
    r"how\s+(?:late|early|soon|long|far\s+in)|typical(?:ly)?|usual(?:ly)?|dates?)\b", re.I)
_LOADED_TARGET_RE = re.compile(
    r"\b(?:this|the\s+(?:current|loaded)|current|loaded|my)\s+(?:loaded\s+)?"
    r"(?:pattern|window|chart|setup|trade|study)\b", re.I)


def _offset_text(row, key, entry_date):
    """(date of the extreme, calendar day number) with the window's entry date as day 1."""

    try:
        point = datetime.date.fromisoformat(row[key])
        anchor = datetime.date.fromisoformat(entry_date)
        day = min(anchor.day, calendar.monthrange(row["year"], anchor.month)[1])
        start = datetime.date(row["year"], anchor.month, day)
    except (KeyError, TypeError, ValueError):
        return None
    offset = (point - start).days + 1
    return (point, max(1, offset)) if offset >= -7 else None


def build_excursion_date_command(message, current_view, user_token, *, today=None):
    text = str(message or "").strip()
    if not user_token or not _WHEN_RE.search(text):
        return None
    wants_low = bool(_LOW_RE.search(text))
    wants_high = bool(_HIGH_RE.search(text)) and not wants_low
    if not (wants_low or wants_high):
        return None
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
    if status is None:
        return None
    if status == 403:
        return {"reply": "<b>%s is outside this account's available markets.</b>" % _esc(spec["symbol"]),
                "actions": [], "trace": trace}
    rows = _completed_rows(payload) if status == 200 else []
    key = "low_date" if wants_low else "high_date"
    dated = []
    for row in rows:
        offset = _offset_text(row, key, spec["entry_date"])
        if offset:
            dated.append((row, offset[0], offset[1]))
    word = "low" if wants_low else "high"
    measure = "MAE" if wants_low else "MFE"
    if not dated:
        return {"reply": (
            "TradeWave's engine reports how deep each year's %s was (%s) for %s, but the date "
            "of that %s is not available in this response, so I won't guess one. Turn on the "
            "%s overlay in the Wave Viewer to see each year's extreme."
            % (word, measure, title, word, measure)), "actions": [], "trace": trace}

    total = len(dated)
    latest = max(dated, key=lambda item: (item[2], item[0]["year"]))
    earliest = min(dated, key=lambda item: (item[2], -item[0]["year"]))
    recent = max(dated, key=lambda item: item[0]["year"])
    ranked = sorted(dated, key=lambda item: item[2], reverse=True)
    value_key = "low" if wants_low else "high"
    verb = "bottomed" if wants_low else "peaked"
    window_days = spec["days_out"]

    def position(item):
        row, point, offset = item
        if row.get("entry_trade_date") == row.get(key):
            return "%s, the entry session (it never traded %s its entry close)" % (
                _long_date(point), "below" if wants_low else "above")
        if offset >= window_days:
            return "%s, the exit session (day %d of %d)" % (
                _long_date(point), window_days, window_days)
        return "%s, calendar day %d of %d (%s vs the entry close)" % (
            _long_date(point), offset, window_days, tg._fmt_pct(row[value_key]))

    def cycle(item):
        return "%d cycle: %s" % (item[0]["year"], position(item))

    at_entry = sum(1 for item in dated if item[0].get("entry_trade_date") == item[0].get(key))
    first_month = sum(1 for item in dated if item[2] <= 30)
    spread = (
        "In %d of %d completed cycles the %s came within the first 30 calendar days%s."
        % (first_month, total, word,
           (", and in %d the entry session itself was the %s" % (at_entry, word)) if at_entry else ""))
    latest_line = "The latest the pattern has %s: <b>%s</b>." % (verb, cycle(latest))
    earliest_line = "The earliest: %s." % cycle(earliest)
    if re.search(r"\bearliest\b|\bhow\s+(?:early|soon)\b", text, re.I):
        lead = "The earliest the pattern has %s: <b>%s</b>. %s" % (verb, cycle(earliest), spread)
        detail = [latest_line]
    elif re.search(r"\blatest\b|\bhow\s+late\b", text, re.I):
        lead = latest_line + " " + spread
        detail = [earliest_line]
    else:
        lead = spread + " " + latest_line
        detail = [earliest_line]
    detail.insert(0, "Latest three: " + "; ".join(cycle(item) for item in ranked[:3]) + ".")
    detail.append("Most recent completed cycle: " + position(recent) + ".")
    active = [row for row in ((payload.get("ChartData4") if isinstance(payload, dict) else None) or [])
              if isinstance(row, dict) and row.get("completed") is False and row.get(key)]
    if active:
        try:
            point = datetime.date.fromisoformat(str(active[-1][key]))
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
        "Scope</span> %s. The %s is each cycle's %s traded price after entry - the same point "
        "TradeWave's %s measures - with the entry date counted as day 1. History describes past "
        "cycles; it does not time the current one.</div></div>"
        % (title, word, lead, total, "<br>".join(detail), subject, word,
           "lowest" if wants_low else "highest", measure))
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
                text, user_token, today=today, table_market=table_market)
            if command is not None:
                return command
        if _names_several_cycles(text):
            return None
        compare = bool(_COMPARE_RE.search(text))
        study_shape = bool(_STUDY_VERB_RE.search(text)) and _parse_period(
            text, today or tg._market_today()) is not None
        if not (compare or study_shape):
            return None
        securities = _find_securities(text, user_token, current_view)
        if compare or (len(securities) >= 2 and study_shape):
            command = build_comparison_command(
                text, current_view, user_token, today=today, years_cap=years_cap,
                securities=securities)
            if command is not None:
                return command
        return build_window_study_command(
            text, current_view, user_token, today=today, years_cap=years_cap,
            securities=securities)
    except Exception:  # never let a research shortcut break the normal chat path
        log.exception("tara research command failed; falling back to the model path")
        return None
