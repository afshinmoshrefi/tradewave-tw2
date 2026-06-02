"""v1 blueprint. /markets is implemented as the reference pattern (auth -> entitlement
-> appserver call -> contract-shaped JSON). The gateway agent implements the rest to
match api/openapi.yaml. Every data route uses @require_api_key; ML + market scope come
from g.customer['entitlements'] / tiers.py.

Safety posture (enforced here + in appserver_client): signals only - no raw OHLCV /
last price / price-by-date is ever returned; all returns are percentages. ML is offered on
EVERY tier but METERED PER DAY (ml_quota.py; free 5/day, unlimited on Pro) and only on
ML-eligible markets (ids 0-4, 11). Fail-fast: real errors surface as the contract Error
JSON via the app error handlers; only genuine data gaps fail soft.
"""
import datetime
import logging
import re

from flask import Blueprint, g, jsonify, request

from . import appserver_client, cards, ml_quota, tiers
from .auth import require_api_key

log = logging.getLogger("apiserver.routes")
v1 = Blueprint("v1", __name__)

_UPGRADE_URL = "https://tw2-dev.trxstat.com/account/api"

# how many ranked rows we enrich (win_rate + receipts + ml) AFTER ranking/slicing, so the
# scan never fans out ChartData4 50xN. Bounded by the appserver_client per-row cap.
_SCAN_ENRICH_CAP = appserver_client.MAX_WIN_RATE_ENRICH

# trading-day approximations for window resolution. "now" = entry within ~10 trading days.
_WINDOW_TRADING_DAYS = {"now": 10, "next_2_weeks": 14, "next_month": 31}


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _require_scope(market_id):
    """Return an (error_response, status) tuple if the market is out of the caller's
    tier scope, else None. The permanent resource keys '0'..'16' are the scope unit."""
    scope = set(g.customer["entitlements"]["markets"])
    if str(market_id) not in scope:
        return _err(
            "forbidden",
            "market '%s' is not in your plan's scope - upgrade for full market access"
            % market_id,
            403,
        )
    return None


def _today():
    return datetime.date.today().isoformat()


_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")


def _clean_chart_args(entry_date, days_out, years, symbol=None):
    """Validate the path/query values that feed internal appserver paths. Defense in depth
    on top of appserver_client._seg() encoding: reject obviously bad input with a clean 400
    instead of forwarding junk. Returns (entry_date, days_out, years) normalized, or raises
    ValueError with a user-facing message."""
    try:
        datetime.datetime.strptime(entry_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("entry_date must be YYYY-MM-DD")
    try:
        d = int(days_out)
    except (ValueError, TypeError):
        raise ValueError("days_out must be an integer")
    if not (1 <= d <= 366):
        raise ValueError("days_out must be between 1 and 366")
    if not str(years).isdigit() or not (1 <= int(years) <= 99):
        raise ValueError("years must be an integer between 1 and 99")
    if symbol is not None and not _SYMBOL_RE.match(symbol):
        raise ValueError("symbol contains invalid characters")
    return entry_date, str(d), str(years)


def _ml_eligible(market_id):
    return str(market_id) in tiers.ML_MARKETS


def _in_scope_markets():
    """The caller's in-scope market ids (intersection of tier scope and the real catalog)."""
    return list(g.customer["entitlements"]["markets"])


def _parse_markets_param(raw, name_map):
    """Resolve the `markets` csv (ids like '2,11' OR names like 'gold,energy') to a list of
    in-scope ids. Unknown/out-of-scope tokens are dropped. Default = ALL in-scope."""
    scope = set(_in_scope_markets())
    if not raw:
        return [m for m in _in_scope_markets()]
    name_to_id = {str(v).strip().lower(): str(k) for k, v in name_map.items()}
    out = []
    for tok in raw.split(","):
        t = tok.strip()
        if not t:
            continue
        if t in scope:
            out.append(t)
        elif t.lower() in name_to_id and name_to_id[t.lower()] in scope:
            out.append(name_to_id[t.lower()])
    # dedupe, preserve order
    seen = set()
    return [m for m in out if not (m in seen or seen.add(m))]


def _resolve_window(window):
    """Resolve the window param to (entry_lo_date, entry_hi_date, label).

    Supported: 'now' (~10 trading days), 'next_2_weeks', 'next_month', or 'YYYY-MM-DD..YYYY-MM-DD'.
    Returns dates as datetime.date. OppList4 is keyed to a SINGLE entry date, so the scan
    fetches at the window's start date and then keeps only setups whose entry_date falls in
    the window - giving a true window over a single-date primitive."""
    today = datetime.date.today()
    w = (window or "now").strip().lower()
    if ".." in w:
        lo_s, _, hi_s = w.partition("..")
        try:
            lo = datetime.datetime.strptime(lo_s.strip(), "%Y-%m-%d").date()
            hi = datetime.datetime.strptime(hi_s.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi, window
    days = _WINDOW_TRADING_DAYS.get(w)
    if days is None:
        return None
    # ~7 calendar days per 5 trading days
    cal = int(round(days * 7 / 5)) if w == "now" else days
    return today, today + datetime.timedelta(days=cal), w


@v1.get("/markets")
@require_api_key
def markets():
    scope = set(g.customer["entitlements"]["markets"])
    out = []
    for m in appserver_client.list_markets():
        out.append({
            "id": m["id"],
            "name": m["name"],
            "ml_eligible": m["id"] in tiers.ML_MARKETS,
            "in_scope": m["id"] in scope,
        })
    return jsonify({"markets": out})


@v1.get("/markets/<market_id>/symbols")
@require_api_key
def symbols(market_id):
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    return jsonify({"symbols": appserver_client.list_symbols(market_id)})


def _column_filters_from_args():
    """Parse the numeric COLUMN filters that the UI opportunity table also offers. They operate
    on RAW OppList4 columns (present on every row, no win-rate enrichment needed), so they can be
    applied early and cheaply: pattern length in calendar days (days_out), average and median
    seasonal profit (percent, matching avg_return_pct / median_return_pct), and the Sharpe ratio.
    Returns a predicate keep(opp) -> bool. Units: returns are PERCENT (e.g. min_avg_return=5 means
    >= 5%), matching the percent-valued fields; win-rate stays a 0..1 fraction (min_win_rate)."""
    min_days = request.args.get("min_days", type=int)
    max_days = request.args.get("max_days", type=int)
    min_avg = request.args.get("min_avg_return", type=float)
    min_med = request.args.get("min_median_return", type=float)
    min_sharpe = request.args.get("min_sharpe", type=float)

    def keep(o):
        d = o.get("days_out")
        if min_days is not None and (d is None or d < min_days):
            return False
        if max_days is not None and (d is None or d > max_days):
            return False
        if min_avg is not None and (o.get("avg_profit_pct") is None or o["avg_profit_pct"] < min_avg):
            return False
        if min_med is not None and (o.get("median_profit_pct") is None or o["median_profit_pct"] < min_med):
            return False
        if min_sharpe is not None and (o.get("sharpe_ratio") is None or o["sharpe_ratio"] < min_sharpe):
            return False
        return True

    return keep


# Presidential election cycle (pe_cycle). Two engine mechanisms:
#  - opportunity-list endpoints (scan / opportunities / opportunities-by-symbol) use the OppList4 /
#    OppBySymbol 'mode' param, which only has the CURRENT cycle position pre-computed: consecutive|pe.
#  - single-security chart/stats (seasonal-chart / patterns) use the ChartData4 'yrs' = 'pe{N}-{count}'
#    format, which can target ANY position: consecutive|pe|pe0|pe1|pe2|pe3.
_PE_CYCLES_LIST = {"consecutive", "pe"}
_PE_CYCLES_CHART = {"consecutive", "pe", "pe0", "pe1", "pe2", "pe3"}


def _resolve_pe_cycle(allow_positions):
    """Parse + validate the pe_cycle query param (default 'consecutive'). allow_positions=True
    permits pe0..pe3 (the single-security chart/stats endpoints); False restricts to
    consecutive|pe (the opportunity-list endpoints). Raises ValueError on a bad value."""
    raw = (request.args.get("pe_cycle") or "consecutive").strip().lower()
    allowed = _PE_CYCLES_CHART if allow_positions else _PE_CYCLES_LIST
    if raw not in allowed:
        if not allow_positions and raw in ("pe0", "pe1", "pe2", "pe3"):
            raise ValueError("pe0-pe3 target a specific cycle position and are only available on the "
                             "single-security endpoints (/v1/seasonal-chart, /v1/patterns); the "
                             "opportunity table supports pe_cycle=consecutive or pe (current cycle)")
        raise ValueError("pe_cycle must be one of %s" % sorted(allowed))
    return raw


def _opp_mode(pe_cycle):
    """OppList4/OppBySymbol mode for an opportunity-list pe_cycle (consecutive|pe -> mode)."""
    return "pe" if pe_cycle and pe_cycle != "consecutive" else "consecutive"


def _lookback_args():
    """The two pattern-DETECTION knobs the engine exposes (OppList4/OppBySymbol year1/year2):
      - years (year1): the LOOKBACK - how many years to scan for patterns (5-98, data-dependent).
        In PE mode this is the number of PE-position occurrences (e.g. the last 10 PE+2 years).
      - min_winning_years (year2): of those, the minimum number of WINNING years required for a
        pattern to be listed. e.g. years=10 & min_winning_years=9 is the classic '10-9' (>=90% of
        years won); '17-15' is years=17 & min_winning_years=15. Detection floors around 80%+.
    Defaults 10 / 9 (the prior hardcoded behavior, so existing callers are unchanged). Returns
    (year1_str, year2_str). Raises ValueError on a bad value. NOTE: the engine serves only the
    pre-computed (year1, year2) datasets; an unavailable combo returns no opportunities (fail-soft)."""
    years = request.args.get("years", default=10, type=int)
    mwy = request.args.get("min_winning_years", default=9, type=int)
    if years is None or not (1 <= years <= 99):
        raise ValueError("years (lookback) must be an integer between 1 and 99")
    if mwy is None or not (0 <= mwy <= years):
        raise ValueError("min_winning_years must be an integer between 0 and years")
    return str(years), str(mwy)


# Date-range PRESETS (the wave-viewer 'Months & Qtrs' dropdown) -> (entry_date, days_out) for a
# single security's seasonal window. MM-DD ranges; Winter/Buy&Hold wrap to the next year.
_PERIOD_RANGES = {
    "jan": ("01-01", "01-31"), "feb": ("02-01", "02-28"), "mar": ("03-01", "03-31"),
    "apr": ("04-01", "04-30"), "may": ("05-01", "05-31"), "jun": ("06-01", "06-30"),
    "jul": ("07-01", "07-31"), "aug": ("08-01", "08-31"), "sep": ("09-01", "09-30"),
    "oct": ("10-01", "10-31"), "nov": ("11-01", "11-30"), "dec": ("12-01", "12-31"),
    "q1": ("01-01", "03-31"), "q2": ("04-01", "06-30"), "q3": ("07-01", "09-30"), "q4": ("10-01", "12-31"),
    "spring": ("03-21", "06-20"), "summer": ("06-21", "09-21"),
    "fall": ("09-22", "12-21"), "winter": ("12-22", "03-20"),
}
_PERIOD_ALIASES = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun",
    "july": "jul", "august": "aug", "september": "sep", "october": "oct", "november": "nov",
    "december": "dec", "1st_qtr": "q1", "2nd_qtr": "q2", "3rd_qtr": "q3", "4th_qtr": "q4",
    "year_to_date": "ytd", "today_to_year_end": "year_end", "buy_and_hold": "buy_hold",
    "buy&hold": "buy_hold", "autumn": "fall",
}


def _resolve_period(period, reverse, base_entry, base_days):
    """Translate a date-range preset (month jan..dec / quarter q1..q4 / season spring..winter / ytd /
    year_end / buy_hold) and/or the 'reverse' complement into (entry_date, days_out) for the current
    year - the wave-viewer 'Months & Qtrs' dropdown, exposed in the API. reverse complements the base
    window (the period, else the caller's entry_date+days_out); a full-year (buy & hold) cannot be
    reversed. Raises ValueError on a bad preset / un-reversible range."""
    today = datetime.date.today()
    y = today.year
    p = (period or "").strip().lower().replace(" ", "_").replace("-", "_")
    p = _PERIOD_ALIASES.get(p, p)
    if not p:
        d0 = datetime.datetime.strptime(base_entry, "%Y-%m-%d").date()
        d1 = d0 + datetime.timedelta(days=max(1, int(base_days)) - 1)
    elif p == "ytd":
        d0, d1 = datetime.date(y, 1, 1), today
    elif p == "year_end":
        d0, d1 = today, datetime.date(y, 12, 31)
    elif p == "buy_hold":
        d0, d1 = datetime.date(y, 1, 1), datetime.date(y + 1, 1, 1)
    elif p in _PERIOD_RANGES:
        s, e = _PERIOD_RANGES[p]
        d0 = datetime.date(y, int(s[:2]), int(s[3:]))
        d1 = datetime.date(y, int(e[:2]), int(e[3:]))
        if d1 <= d0:                      # wrap (winter)
            d1 = datetime.date(y + 1, int(e[:2]), int(e[3:]))
    else:
        raise ValueError(
            "unknown period '%s' - use a month (jan..dec), quarter (q1..q4), season "
            "(spring/summer/fall/winter), ytd, year_end, or buy_hold" % period)
    if reverse:
        if (d1 - d0).days + 1 >= 365:
            raise ValueError("a full-year (buy_hold) range cannot be reversed")
        rd0 = d1 + datetime.timedelta(days=1)
        rd1 = d0 - datetime.timedelta(days=1)
        if rd1 < rd0:
            rd1 = rd1.replace(year=rd1.year + 1)
        d0, d1 = rd0, rd1
    days_out = (d1 - d0).days + 1
    if not (1 <= days_out <= 366):
        raise ValueError("the computed window is out of range")
    return d0.isoformat(), days_out


def _period_args():
    """Read period + reverse from the request. Returns (period, reverse_bool)."""
    period = request.args.get("period")
    reverse = (request.args.get("reverse") or "").strip().lower() in ("1", "true", "yes", "on")
    return period, reverse


def _chart_window_and_years(symbol, allow_positions=True):
    """Resolve (entry_date, days_out, yrs_string) for a per-security chart/stats request, honoring
    the date-range presets (period / reverse), the pe_cycle, and the years lookback. When a period
    or reverse is given it OVERRIDES entry_date/days_out; otherwise the explicit entry_date/days_out
    are validated. Raises ValueError on bad input."""
    pe_cycle = _resolve_pe_cycle(allow_positions=allow_positions)
    period, reverse = _period_args()
    if period or reverse:
        if not _SYMBOL_RE.match(symbol):
            raise ValueError("symbol contains invalid characters")
        years_n = request.args.get("years", default=10, type=int)
        if years_n is None or not (1 <= years_n <= 99):
            raise ValueError("years must be an integer between 1 and 99")
        entry_date, days_out = _resolve_period(
            period, reverse, request.args.get("entry_date") or _today(),
            request.args.get("days_out", default=30, type=int) or 30)
        days_out, years = str(days_out), str(years_n)
    else:
        entry_date, days_out, years = _clean_chart_args(
            request.args.get("entry_date") or _today(),
            request.args.get("days_out", default="30"),
            request.args.get("years", default="10"),
            symbol=symbol,
        )
    return entry_date, days_out, _chart_years(pe_cycle, years)


def _chart_years(pe_cycle, count):
    """Build the appserver ChartData4/seasonal-chart 'yrs' string: consecutive -> 'N';
    pe -> 'pe{current_phase}-N'; pe0..pe3 -> 'pe{N}-N'. count is the digit-validated lookback."""
    count = str(count)
    if pe_cycle == "consecutive":
        return count
    phase = datetime.date.today().year % 4 if pe_cycle == "pe" else int(pe_cycle[2:])
    return "pe%d-%s" % (phase, count)


@v1.get("/opportunities")
@require_api_key
def opportunities():
    market = request.args.get("market")
    if not market:
        return _err("invalid_request", "query param 'market' is required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    # OppList4 is keyed to a SINGLE entry date (month + day), so 'from' is the entry
    # date (default today). This endpoint is single-date by design; for a true date
    # WINDOW (now / next_2_weeks / next_month / from..to) use /v1/scan, which owns
    # windowed scanning. 'to' is accepted but NOT used to widen the query here; the
    # response sets window_supported=false so callers are never silently misled.
    entry_date = request.args.get("from") or _today()
    direction = request.args.get("direction")  # long|short, optional

    # min_win_rate filters on the REAL historical win rate (share of profitable years,
    # from ChartData4 'Percent Profitable') - NOT the ML win_prob. The OppList4 feed
    # has no per-row win rate, so we enrich each row's win_rate per symbol via
    # ChartData4. That is one (cached) ChartData4 call per row, so it is capped at
    # appserver_client.MAX_WIN_RATE_ENRICH rows; when min_win_rate is set we enrich up
    # to that cap and drop rows we could not enrich (an unknown rate must NOT pass a
    # minimum filter). Without min_win_rate we still enrich up to the cap so win_rate is
    # populated, but we never drop rows.
    min_win_rate = request.args.get("min_win_rate", type=float)
    enrich_n = appserver_client.MAX_WIN_RATE_ENRICH

    try:
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # consecutive | pe (current cycle)
        year1, year2 = _lookback_args()                      # lookback / min winning years
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    # Fetch RAW (no enrichment), apply the numeric column filters (pattern length, avg/median
    # profit %, Sharpe) on the raw rows FIRST, then enrich win_rate only on the survivors, so a
    # ChartData4 call is never spent on a row a column filter would have dropped.
    keep = _column_filters_from_args()
    opps = appserver_client.opportunities(
        market, entry_date, year1=year1, year2=year2, direction=direction,
        enrich_win_rate=0, mode=_opp_mode(pe_cycle))
    opps = [o for o in opps if keep(o)]

    # P0: surface how many rows were actually win-rate-evaluated and whether the
    # enrichment cap was hit, so a min_win_rate filter is never silently misleading
    # (rows past the cap have win_rate=None and are dropped by the filter).
    total_rows = len(opps)
    evaluated_count = min(total_rows, enrich_n)
    enrichment_capped = total_rows > enrich_n
    for o in opps[:enrich_n]:
        if o.get("win_rate") is None:
            o["win_rate"] = appserver_client._win_rate_for_opp(o)

    if min_win_rate is not None:
        opps = [o for o in opps if o.get("win_rate") is not None and o["win_rate"] >= min_win_rate]

    # limit: tier-capped to the plan's opp_limit (free 3, dev 100, pro 1000, business
    # 5000). A caller-supplied limit can only narrow, never exceed, the tier cap.
    tier_cap = g.customer["entitlements"]["opp_limit"]
    req_limit = request.args.get("limit", default=25, type=int)
    if req_limit < 0:
        req_limit = 0
    effective_limit = min(req_limit, tier_cap)
    opps = opps[:effective_limit]

    # Attach ML on ML-eligible markets, METERED by the daily allowance (free 5/day).
    if opps and _ml_eligible(market):
        granted = ml_quota.consume(g.customer, len(opps))
        score_rows = opps[:granted]
        if score_rows:
            items = [
                {"symbol": o["symbol"], "date": o["entry_date"],
                 "days_out": o["days_out"], "direction": o["direction"]}
                for o in score_rows
            ]
            ml = appserver_client.ml_scores(market, items)
            for o, score in zip(score_rows, ml):
                o["ml"] = score

    return jsonify({
        "opportunities": opps,
        "ml_remaining_today": ml_quota.remaining(g.customer),
        "entry_date": entry_date,
        "window_supported": False,  # single-date endpoint; use /v1/scan for windows
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
    })


def _symbol_patterns_response(symbol):
    """A security's TOP SEASONAL PATTERNS across the year, sorted by Sharpe (OppBySymbol - the
    data behind the wave-viewer pattern dropdown). Shared by /v1/opportunities/<symbol> and the
    clearer alias /v1/securities/<symbol>/patterns. Supports pe_cycle=consecutive|pe and the
    numeric column filters (min_days/max_days/min_avg_return/min_median_return/min_sharpe)."""
    market = request.args.get("market")
    if not market:
        return _err("invalid_request", "query param 'market' is required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err
    try:
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # OppBySymbol mode: consecutive | pe
        year1, year2 = _lookback_args()                      # lookback / min winning years
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    keep = _column_filters_from_args()
    opps = appserver_client.opportunities_by_symbol(
        market, symbol, year1=year1, year2=year2, mode=_opp_mode(pe_cycle))
    opps = [o for o in opps if keep(o)]

    # tier cap applies here too (one symbol can still yield many start-date setups).
    tier_cap = g.customer["entitlements"]["opp_limit"]
    opps = opps[:tier_cap]

    if opps and _ml_eligible(market):
        granted = ml_quota.consume(g.customer, len(opps))
        score_rows = opps[:granted]
        if score_rows:
            items = [
                {"symbol": o["symbol"], "date": o["entry_date"],
                 "days_out": o["days_out"], "direction": o["direction"]}
                for o in score_rows
            ]
            ml = appserver_client.ml_scores(market, items)
            for o, score in zip(score_rows, ml):
                o["ml"] = score

    return jsonify({"opportunities": opps, "ml_remaining_today": ml_quota.remaining(g.customer)})


@v1.get("/opportunities/<symbol>")
@require_api_key
def opportunities_by_symbol(symbol):
    return _symbol_patterns_response(symbol)


@v1.get("/securities/<symbol>/patterns")
@require_api_key
def symbol_patterns(symbol):
    """Clearly-named alias for the symbol's year-long ranked seasonal patterns (same data)."""
    return _symbol_patterns_response(symbol)


# --------------------------------------------------------------------------- #
# FLAGSHIP endpoints: build SignalCards via cards.py (one source of truth)     #
# --------------------------------------------------------------------------- #

def _enrich_and_card(opp, *, ml_available, seasonal_curve=None, as_of=None, rank=None,
                     ml_state="na", name_map=None):
    """Source receipts (ChartData4 stats + per-year entries) for ONE opp and build its
    card. A per-symbol data gap degrades that row to a card with whatever stats exist
    (logged inside appserver_client) - it never aborts the request."""
    stats, chart_entries = appserver_client.chart_stats_and_years(
        opp["market"], opp["symbol"], opp["entry_date"], opp.get("days_out"), opp.get("years"))
    # win_rate from the same stats (so historical_win_rate is consistent everywhere)
    if opp.get("win_rate") is None:
        opp["win_rate"] = appserver_client._win_rate_from_stats(stats)
    name_map = name_map or appserver_client.market_name_map()
    market_name = name_map.get(str(opp["market"]), str(opp["market"]))
    ml = opp.get("ml")
    return cards.build_signal_card(
        opp, stats, chart_entries, market_name=market_name, ml=ml,
        ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=as_of,
        rank=rank, ml_state=ml_state)


def _ml_state_for(opp, ml_available):
    """Map an opp's ML outcome to a card ml_state for tier_notes:
      'shown'       - the model scored it.
      'market'      - the market is not ML-eligible.
      'unavailable' - eligible AND we spent allowance trying, but the model returned no
                      score for this setup (e.g. a hold longer than the model covers).
                      A NEUTRAL note - never an upgrade nudge (the user already paid for it).
      'quota'       - eligible but we never tried because today's ML allowance was spent.
                      This is the ONLY state that nudges an upgrade.
    The route marks each eligible row it actually attempts with opp['_ml_attempted']; a
    missing flag is treated as 'unavailable' (safe default - never a false upsell)."""
    if ml_available and opp.get("ml"):
        return "shown"
    if not _ml_eligible(opp.get("market")):
        return "market"
    if opp.get("_ml_attempted"):
        return "unavailable"
    return "quota"


_RANK_KEYS = {
    "edge": lambda o: o.get("_edge_score") or 0,
    "win_rate": lambda o: o.get("win_rate") or 0,
    "sharpe": lambda o: o.get("sharpe_ratio") or 0,
    "ml": lambda o: ((o.get("ml") or {}).get("win_prob")) or 0,
    "avg_return": lambda o: o.get("avg_profit_pct") or 0,
}


@v1.get("/scan")
@require_api_key
def scan():
    """find_best_opportunities: cross-market ranked seasonal scan -> SignalCard[].

    Fans out OppList4 over the caller's in-scope markets IN PARALLEL, resolves the window
    to entry dates, ranks (default by edge_score), tier-caps, then enriches ONLY the
    surviving rows (win_rate + receipts + Pro ML) so we never fan out ChartData4 NxM."""
    name_map = appserver_client.market_name_map()
    markets_param = request.args.get("markets")
    market_ids = _parse_markets_param(markets_param, name_map)
    if not market_ids:
        return _err("invalid_request",
                    "no in-scope markets resolved from 'markets' - check ids/names and your plan scope",
                    400)

    win = _resolve_window(request.args.get("window"))
    if win is None:
        return _err("invalid_request",
                    "invalid 'window' - use now | next_2_weeks | next_month | YYYY-MM-DD..YYYY-MM-DD",
                    400)
    entry_lo, entry_hi, window_label = win

    direction = request.args.get("direction")
    min_win_rate = request.args.get("min_win_rate", type=float)
    min_years = request.args.get("min_years", type=int)
    # Default ranking = Sharpe descending, mirroring TradeWave's own daily-pick + SMN 'AI'
    # selectors (filter on win metrics, then sort by Sharpe). edge_score stays available
    # as a rank_by option and is shown on every card.
    rank_by = (request.args.get("rank_by") or "sharpe").strip().lower()
    if rank_by not in _RANK_KEYS:
        rank_by = "sharpe"
    try:
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # consecutive | pe (current cycle)
        year1, year2 = _lookback_args()                      # lookback / min winning years
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    tier_cap = g.customer["entitlements"]["opp_limit"]
    req_limit = request.args.get("limit", default=25, type=int)  # matches openapi.yaml /scan default
    if req_limit < 0:
        req_limit = 0
    effective_limit = min(req_limit, tier_cap)

    # 1) parallel fan-out at the window's start date (NO enrichment yet).
    raw = appserver_client.opportunities_multi(
        market_ids, entry_lo.isoformat(), year1=year1, year2=year2,
        direction=direction, mode=_opp_mode(pe_cycle))

    # 2) keep only setups whose entry_date falls inside the window (true window over the
    #    single-date OppList4 primitive).
    in_window = []
    for o in raw:
        ed = cards._parse_date(o.get("entry_date"))
        if ed is None:
            continue
        if entry_lo <= ed <= entry_hi:
            in_window.append(o)

    # 2b) numeric COLUMN filters the UI also offers (pattern length in days, avg/median profit %,
    #     Sharpe) - applied on raw rows before we pick the head to enrich. e.g. a 10-90 day range
    #     with avg profit >= 5% is min_days=10&max_days=90&min_avg_return=5.
    keep = _column_filters_from_args()
    in_window = [o for o in in_window if keep(o)]
    evaluated_count = len(in_window)

    # 3) order by Sharpe (present on every OppList4 row, no enrichment needed) to choose
    #    the head we enrich - this mirrors TradeWave's daily-pick / SMN 'AI' selection,
    #    which gate on win metrics then rank by Sharpe.
    in_window.sort(key=lambda o: o.get("sharpe_ratio") or 0, reverse=True)

    # 4) take a generous head for enrichment (cap), then enrich win_rate + ml on those.
    head = in_window[: max(effective_limit, min(_SCAN_ENRICH_CAP, len(in_window)))]
    head = head[:_SCAN_ENRICH_CAP]
    enrichment_capped = len(in_window) > len(head)

    # enrich win_rate (+ receipts happen at card build) on the head rows.
    for o in head:
        if o.get("win_rate") is None:
            o["win_rate"] = appserver_client._win_rate_for_opp(o)

    # 5) trust filters (after win_rate is real).
    filtered = head
    if min_win_rate is not None:
        filtered = [o for o in filtered if o.get("win_rate") is not None and o["win_rate"] >= min_win_rate]
    # min_years filter applied via receipts in the card build below (years_tested); we
    # approximate here with the lookback label, then re-check on the built card.

    # 6) attach ML inline, METERED by the daily allowance (free 5/day, unlimited Pro).
    #    filtered is in Sharpe order, so we spend the allowance on the strongest setups.
    #    We RESERVE allowance for the rows we will try, then REFUND any the model could not
    #    score (e.g. a hold longer than the model covers), so a metered customer is only
    #    ever charged for ML scores actually delivered. Rows past the allowance are left
    #    unattempted (a true 'quota' note); attempted-but-unscored rows get the neutral
    #    'unavailable' note - never a false "upgrade for unlimited" nudge.
    eligible = [o for o in filtered if _ml_eligible(o["market"])]
    granted = ml_quota.consume(g.customer, len(eligible)) if eligible else 0
    attempted = eligible[:granted]
    by_market = {}
    for o in attempted:
        o["_ml_attempted"] = True
        by_market.setdefault(o["market"], []).append(o)
    delivered = 0
    for mid, rows in by_market.items():
        items = [{"symbol": r["symbol"], "date": r["entry_date"],
                  "days_out": r["days_out"], "direction": r["direction"]} for r in rows]
        try:
            ml = appserver_client.ml_scores(mid, items)
        except Exception as e:  # noqa: BLE001 - ML is best-effort enrichment, never fatal
            log.warning("scan ML scoring failed for market %s: %s", mid, e)
            ml = []
        for r, score in zip(rows, ml):
            if score:
                r["ml"] = score
                delivered += 1
    ml_quota.refund(g.customer, granted - delivered)

    # 7) build cards, then re-rank by the requested key (default Sharpe).
    built = []
    for o in filtered:
        ml_available = bool(o.get("ml"))
        card = _enrich_and_card(
            o, ml_available=ml_available, as_of=_today(),
            ml_state=_ml_state_for(o, ml_available), name_map=name_map)
        if min_years is not None and card["receipts"]["years_tested"] < min_years:
            continue
        card["_sortkey"] = _scan_sortkey(card, rank_by)
        built.append(card)

    built.sort(key=lambda c: c["_sortkey"], reverse=True)
    built = built[:effective_limit]
    for i, c in enumerate(built, 1):
        c["rank"] = i
        c.pop("_sortkey", None)

    return jsonify({
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "window": window_label,
        "rank_by": rank_by,
        "count": len(built),
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
        "ml_remaining_today": ml_quota.remaining(g.customer),  # None = unlimited
        "opportunities": built,
    })


def _scan_sortkey(card, rank_by):
    if rank_by == "edge":
        return card.get("edge_score") or 0
    if rank_by == "win_rate":
        return card["stats"].get("historical_win_rate") or 0
    if rank_by == "sharpe":
        return card["stats"].get("sharpe_ratio") or 0
    if rank_by == "avg_return":
        return card["stats"].get("avg_return_pct") or 0
    if rank_by == "ml":
        ml = card.get("ml") or {}
        return ml.get("ml_win_prob") or 0
    return card.get("edge_score") or 0


@v1.get("/analyze/<symbol>")
@require_api_key
def analyze_symbol(symbol):
    """analyze_symbol: fuse OppBySymbol + ChartData4 + seasonal curve (+ Pro ML) into ONE
    rich SignalCard (the best setup) + compact other_setups[]."""
    name_map = appserver_client.market_name_map()
    market = request.args.get("market")

    if not market:
        # resolve the market if the symbol is unique across the caller's in-scope markets.
        candidates = appserver_client.resolve_market_for_symbol(symbol, _in_scope_markets())
        if not candidates:
            return _err("not_found",
                        "symbol '%s' not found in any of your in-scope markets - pass ?market=<id>"
                        % symbol, 404)
        if len(candidates) > 1:
            return _err("invalid_request",
                        "symbol '%s' exists in multiple markets %s - specify ?market=<id>"
                        % (symbol, ",".join(sorted(candidates))), 400)
        market = candidates[0]

    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    direction = request.args.get("direction")
    try:
        pe_cycle = _resolve_pe_cycle(allow_positions=False)        # consecutive | pe (wave-viewer knob)
        years_n = request.args.get("years", default=10, type=int)  # lookback knob
        if years_n is None or not (1 <= years_n <= 99):
            raise ValueError("years must be an integer between 1 and 99")
        # PIN a specific window: an explicit entry_date (+days_out), or a period/reverse preset. This is
        # the "click THIS exact opportunity / change the date range" flow - analyze loads THAT window
        # instead of auto-picking the best setup.
        period, reverse = _period_args()
        pin_entry = request.args.get("entry_date")
        pin_days = request.args.get("days_out", type=int)
        if pin_entry is not None:
            try:
                datetime.datetime.strptime(pin_entry, "%Y-%m-%d")
            except (ValueError, TypeError):
                raise ValueError("entry_date must be in YYYY-MM-DD format")
        if pin_days is not None and not (1 <= pin_days <= 366):
            raise ValueError("days_out must be an integer between 1 and 366")
        if period or reverse:
            pin_entry, pin_days = _resolve_period(period, reverse, pin_entry or _today(), pin_days or 30)
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    yrs = _chart_years(pe_cycle, years_n)   # 'N' | 'pe{phase}-N' - drives the receipts/curve lookback
    opps = appserver_client.opportunities_by_symbol(
        market, symbol, year1=str(years_n), mode=_opp_mode(pe_cycle))
    if direction:
        want = appserver_client._dir_to_public(direction)
        opps = [o for o in opps if o["direction"] == want]

    if pin_entry:
        # pin to the requested window: match a detected setup by entry_date (prefer the same
        # days_out); if none matches, analyze the exact window directly (stats come from ChartData4).
        best = next((o for o in opps if o.get("entry_date") == pin_entry
                     and (pin_days is None or o.get("days_out") == pin_days)), None)
        if best is None:
            best = next((o for o in opps if o.get("entry_date") == pin_entry), None)
        if best is None:
            best = {"symbol": symbol, "market": market, "entry_date": pin_entry,
                    "days_out": pin_days or 30,
                    "direction": (want if direction else "long"),
                    "win_rate": None, "sharpe_ratio": None,
                    "avg_profit_pct": None, "median_profit_pct": None}
            opps = [best] + opps
    else:
        if not opps:
            return _err("not_found",
                        "no seasonal setups for '%s' in market '%s'%s"
                        % (symbol, market, (" (%s)" % direction) if direction else ""), 404)
        # pick the best setup by preliminary edge_score (win_rate already enriched by
        # opportunities_by_symbol), build the rich card with receipts + seasonal curve.
        for o in opps:
            prelim, _ = cards.compute_edge_score(
                o.get("win_rate"), o.get("sharpe_ratio"),
                int(o.get("years")) if str(o.get("years") or "").isdigit() else 0)
            o["_edge"] = prelim
        opps.sort(key=lambda o: o["_edge"], reverse=True)
        best = opps[0]

    best["years"] = yrs   # receipts/curve use the requested lookback (and PE cycle)

    # ML metered by the daily allowance (free 5/day, unlimited Pro); spend 1 on the best.
    # Reserve, try, and REFUND if the model returns no score for this setup, so a metered
    # customer is only charged for ML actually delivered (and never sees a false upsell).
    granted = ml_quota.consume(g.customer, 1) if _ml_eligible(market) else 0
    if granted:
        best["_ml_attempted"] = True
        try:
            ml = appserver_client.ml_scores(market, [{
                "symbol": best["symbol"], "date": best["entry_date"],
                "days_out": best["days_out"], "direction": best["direction"]}])
            best["ml"] = ml[0] if ml else None
        except Exception as e:  # noqa: BLE001
            log.warning("analyze ML scoring failed for %s/%s: %s", market, best.get("symbol"), e)
            best["ml"] = None
        if not best.get("ml"):
            ml_quota.refund(g.customer, 1)
    ml_available = bool(best.get("ml"))

    seasonal_curve = None
    try:
        seasonal_curve = appserver_client._seasonal_curve(
            market, symbol, best["entry_date"], best.get("years") or "10")
    except Exception:  # noqa: BLE001 - curve_summary is optional, never fatal
        seasonal_curve = None

    card = _enrich_and_card(
        best, ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=_today(),
        rank=1, ml_state=_ml_state_for(best, ml_available), name_map=name_map)

    other = [cards.compact_setup(o) for o in opps[1:]]
    tier_cap = g.customer["entitlements"]["opp_limit"]
    other = other[: max(0, tier_cap - 1)]

    return jsonify({"card": card, "other_setups": other, "as_of": _today()})


@v1.get("/patterns/<market_id>/<symbol>")
@require_api_key
def pattern(market_id, symbol):
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    try:
        entry_date, days_out, yrs = _chart_window_and_years(symbol)
    except ValueError as e:
        return _err("invalid_request", str(e), 400)
    return jsonify(appserver_client.pattern_stats(market_id, symbol, entry_date, days_out, yrs))


@v1.get("/seasonal-chart")
@require_api_key
def seasonal_chart():
    market = request.args.get("market")
    symbol = request.args.get("symbol")
    if not market or not symbol:
        return _err("invalid_request", "query params 'market' and 'symbol' are required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err
    try:
        entry_date, days_out, yrs = _chart_window_and_years(symbol)
    except ValueError as e:
        return _err("invalid_request", str(e), 400)
    direction = request.args.get("direction")
    return jsonify(appserver_client.seasonal_chart(
        market, symbol, entry_date, days_out, yrs, direction=direction))


@v1.post("/score")
@require_api_key
def score():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _err("invalid_request", "JSON body with 'opportunities' is required", 400)
    items = body.get("opportunities")
    if not isinstance(items, list) or not items:
        return _err("invalid_request", "'opportunities' must be a non-empty array", 400)

    # ML-eligible markets only (0-4, 11). The score request items are not market-tagged
    # in the contract, so the market is taken from the 'market' query/body param and
    # must be ML-eligible. Default to S&P 500 ('2'), an ML-eligible market.
    market = request.args.get("market") or body.get("market") or "2"
    if not _ml_eligible(market):
        return _err("forbidden",
                    "market '%s' is not ML-eligible (ML markets: %s)"
                    % (market, ", ".join(sorted(tiers.ML_MARKETS))), 403)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    # Validate + normalize each requested opportunity to the contract's ScoreRequest.
    norm = []
    for it in items:
        if not isinstance(it, dict):
            return _err("invalid_request", "each opportunity must be an object", 400)
        missing = [k for k in ("symbol", "date", "days_out", "direction") if it.get(k) in (None, "")]
        if missing:
            return _err("invalid_request",
                        "opportunity missing required fields: %s" % ", ".join(missing), 400)
        try:
            days_out_i = int(it["days_out"])
        except (ValueError, TypeError):
            return _err("invalid_request", "days_out must be a number", 400)
        norm.append({
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": days_out_i,
            "direction": it["direction"],
        })

    # ML is offered on every tier but METERED PER DAY (free 5/day, unlimited Pro). Grant
    # up to the remaining allowance; score that many; the rest come back unscored with a
    # quota note. A zero grant returns a graceful upgrade nudge (HTTP 200, not an error).
    granted = ml_quota.consume(g.customer, len(norm))
    if granted == 0:
        lim = g.customer["entitlements"].get("ml_daily_limit")
        return jsonify({
            "requires": "upgrade", "reason": "ml_daily_limit",
            "message": "Daily ML limit reached (%s/day on your plan). Upgrade for unlimited ML scoring." % lim,
            "upgrade_url": _UPGRADE_URL, "ml_remaining_today": 0,
        }), 200

    ml = appserver_client.ml_scores(market, norm[:granted])
    scores = []
    for it, score in zip(norm[:granted], ml):
        row = {
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": it["days_out"],
            "direction": appserver_client._dir_to_public(it["direction"]),
        }
        if score:
            row.update(score)
        else:
            # appserver could not score it (e.g. days_out outside the 10-90 range)
            row.update({"ml_score": None, "win_prob": None,
                        "pred_return": None, "pred_mfe": None})
        scores.append(row)
    # requested beyond today's allowance: unscored, with a quota note (no error).
    for it in norm[granted:]:
        scores.append({
            "symbol": it["symbol"], "date": it["date"], "days_out": it["days_out"],
            "direction": appserver_client._dir_to_public(it["direction"]),
            "ml_score": None, "win_prob": None, "pred_return": None, "pred_mfe": None,
            "note": "daily ML limit reached - upgrade for unlimited",
        })
    return jsonify({
        "scores": scores,
        "granted": granted,
        "ml_remaining_today": ml_quota.remaining(g.customer),
    })


@v1.get("/daily-pick")
@require_api_key
def daily_pick():
    """The daily AI pick as a full SignalCard + the LIVE forward-tested track record
    (the strongest receipt: made in advance, scored later). The pick's own seasonal
    receipts come from ChartData4; the live record comes from featured_history."""
    raw = appserver_client.daily_pick_raw()
    if not raw:
        return jsonify({"card": None, "track_record": None, "as_of": _today()})

    opp = raw["opp"]
    market = opp.get("market")
    # The daily pick is the FREE teaser - a single published signal everyone sees - so its
    # ML score is shown WITHOUT consuming the daily ML allowance (the pick already carries
    # the ML the scorer selected it with). It is the hook, not a metered call.
    ml_available = bool(market and _ml_eligible(market) and opp.get("ml"))
    ml_state = ("shown" if ml_available
                else ("market" if not (market and _ml_eligible(market)) else "na"))

    seasonal_curve = None
    if market and opp.get("entry_date"):
        try:
            seasonal_curve = appserver_client._seasonal_curve(
                market, opp["symbol"], opp["entry_date"], opp.get("years") or "10")
        except Exception:  # noqa: BLE001
            seasonal_curve = None

    card = _enrich_and_card(
        opp, ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=_today(),
        rank=1, ml_state=ml_state)

    # fold the LIVE track record into the card receipts - the differentiating proof.
    tr = appserver_client.track_record()
    summary = tr.get("summary", {}) if isinstance(tr, dict) else {}
    live_record = {
        "count": summary.get("count"),
        "win_count": summary.get("win_count"),
        "win_rate": summary.get("win_rate"),
        "avg_return_pct": summary.get("avg_return_pct"),
        "note": "Live forward-tested record of past daily picks (made in advance, scored later).",
    }
    if isinstance(card, dict):
        card.setdefault("receipts", {})["live_track_record"] = live_record

    return jsonify({
        "card": card,
        "featured_date": raw.get("featured_date"),
        "track_record": live_record,
        "as_of": _today(),
    })


@v1.get("/daily-pick/track-record")
@require_api_key
def track_record():
    return jsonify(appserver_client.track_record())
