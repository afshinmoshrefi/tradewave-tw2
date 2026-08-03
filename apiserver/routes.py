"""v1 blueprint. /markets is implemented as the reference pattern (auth -> entitlement
-> appserver call -> contract-shaped JSON). The gateway agent implements the rest to
match api/openapi.yaml. Every data route uses @require_api_key; ML + market scope come
from g.customer['entitlements'] / tiers.py.

Safety posture (enforced here + in appserver_client): derived seasonal patterns only - no
raw OHLCV / last price / price-by-date is ever returned; all returns are percentages. ML is offered on
EVERY tier but METERED PER DAY (ml_quota.py; free 5/day, unlimited on Pro) and only on
ML-eligible markets (ids 0-4, 11). Fail-fast: real errors surface as the contract Error
JSON via the app error handlers; only genuine data gaps fail soft.
"""
import concurrent.futures
import datetime
import logging
import os
import re

import requests
from flask import Blueprint, g, jsonify, request

from . import appserver_client, cards, market_bands, ml_quota, scan_cache, tiers
from .auth import require_api_key

log = logging.getLogger("apiserver.routes")
v1 = Blueprint("v1", __name__)

# Per-env console URL (TW2_PUBLIC_HOST drives every public link); the dev host is
# only the unset-env fallback so customer-visible messages never leak it on prod.
_UPGRADE_URL = "https://%s/account/api" % os.environ.get("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")

# how many ranked rows we enrich (win_rate + receipts + ml) AFTER ranking/slicing, so the
# scan never fans out ChartData4 50xN. Bounded by the appserver_client per-row cap.
_SCAN_ENRICH_CAP = appserver_client.MAX_WIN_RATE_ENRICH

# Default scan scope when the caller passes no `markets`: the liquid equities core
# (DOW 30 / NASDAQ 100 / S&P 500 / ETFs). A no-markets scan over ALL ~15 markets is
# the timeout path; callers can still pass `markets=` to scan anything in their scope.
_DEFAULT_SCAN_MARKETS = ("0", "1", "2", "11")

# trading-day approximations for window resolution. "now" = entry within ~10 trading days.
_WINDOW_TRADING_DAYS = {"now": 10, "next_2_weeks": 14, "next_month": 31}

# POST /v1/score batch cap: each item is an appserver ML round-trip, and a few-hundred-item
# cold batch outlives the edge timeout - so over-cap requests get a clear 400 naming the cap.
_SCORE_BATCH_CAP = 100


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _require_scope(market_id):
    """Return an (error_response, status) tuple if the market is out of the caller's
    tier scope, else None. The permanent resource keys '0'..'16' are the scope unit.
    This 403 is the ONE legitimate upgrade nudge for markets - it fires only for a
    RESOLVED catalog market outside the plan (a typo/unknown market is a 400 upstream
    in _market_arg, never an upsell)."""
    scope = set(g.customer["entitlements"]["markets"])
    if str(market_id) not in scope:
        try:
            name = appserver_client.market_name_map().get(str(market_id))
        except Exception:  # noqa: BLE001 - the label is cosmetic; scope is still enforced
            name = None
        label = ("%s (%s)" % (name, market_id)) if name else "'%s'" % market_id
        return jsonify({"error": {
            "code": "forbidden",
            "message": "market %s is not in your plan's scope - upgrade for full market access" % label,
            "upgrade_url": _UPGRADE_URL,
        }}), 403
    return None


def _demo_guard_symbol(symbol):
    """If the caller is the PUBLIC demo token, restrict to the allowlisted symbols.
    Returns a 403 Flask response to ABORT, or None to proceed. A normal key has no
    'demo' entitlement, so this is a no-op for paying users."""
    ent = g.customer["entitlements"]
    if ent.get("demo"):
        allow = ent.get("demo_symbols", [])
        if str(symbol).upper() not in [s.upper() for s in allow]:
            return jsonify({"error": {"code": "demo_restricted",
                "message": "the public demo token works only for %s - create a free key at /account/api for any symbol" % ", ".join(allow)}}), 403
    return None


def _demo_block_enumeration():
    """Block symbol-enumeration / bulk endpoints for the demo token (anti-scraping)."""
    if g.customer["entitlements"].get("demo"):
        return jsonify({"error": {"code": "demo_restricted",
            "message": "symbol enumeration is not available on the demo token - create a free key at /account/api"}}), 403
    return None


def _demo_scope_rows(rows):
    """For the demo token, filter a list of opportunity rows down to the demo_symbols
    allowlist (tiers.INTERNAL_TIERS['demo']['demo_symbols']) BEFORE ranking/enrichment,
    so a market-wide scan/enumeration route evaluates and reports only the allowlisted
    universe instead of the full market (anti-scraping, and the demo stops burning
    full-market compute). No-op for a normal key (no 'demo' entitlement)."""
    ent = g.customer["entitlements"]
    if not ent.get("demo"):
        return rows
    allow = {s.upper() for s in ent.get("demo_symbols", [])}
    return [o for o in rows if str(o.get("symbol", "")).upper() in allow]


def _today():
    return datetime.date.today().isoformat()


_VALID_VIEWS = ("full", "evidence", "decision", "table")


def _view_arg(default="full"):
    """Progressive-disclosure verbosity: ?view=full|evidence|decision|table. 'full' is the API
    default (backward-compatible); the MCP layer asks for 'decision' so the assistant gets
    the lean read by default. ``evidence`` keeps the ranked winner full and trims runners.
    An unknown value falls back to the default (never an error)."""
    v = (request.args.get("view") or "").strip().lower()
    return v if v in _VALID_VIEWS else default


def _wants_chart():
    """?include=chart (comma-list tolerated) -> attach the Trend Chart curve + per-year bars
    inline on the card (one call instead of a second /seasonal-chart round-trip)."""
    raw = (request.args.get("include") or "").lower()
    return "chart" in [p.strip() for p in raw.split(",")]


_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")

# Contract enum (long|short) plus the appserver's raw l/s codes, case-insensitive.
_VALID_DIRECTIONS = {"long": "long", "l": "long", "short": "short", "s": "short"}


def _direction_arg(raw):
    """Validate + normalize a direction value to the contract enum (long|short).
    None/blank -> None (no filter). An unknown value (e.g. 'sideways') raises ValueError
    naming the valid values - a silent empty 200 would be a wrong-answer failure."""
    if raw is None or str(raw).strip() == "":
        return None
    d = str(raw).strip().lower()
    if d not in _VALID_DIRECTIONS:
        raise ValueError("invalid direction '%s' - valid values: long, short (or the "
                         "short forms l, s), case-insensitive" % raw)
    return _VALID_DIRECTIONS[d]


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


def _squash(s):
    """Lowercase + strip every non-alphanumeric, for forgiving name/alias matching
    ('S&P 500' / 'sp 500' / 'SP-500' all squash to 'sp500')."""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


# Common shorthands for the catalog names (resolution is otherwise id / exact name /
# unambiguous fragment). Values are the PERMANENT resource keys '0'..'16'. Aliases exist
# mainly where a fragment would be ambiguous (forex/indices) or idiomatic (sp500, crypto).
_MARKET_ALIASES = {
    "sp500": "2", "spx": "2", "sandp500": "2", "sandp": "2",
    "dow": "0", "dow30": "0", "djia": "0", "dowjones": "0",
    "nasdaq": "1", "nasdaq100": "1", "ndx": "1",
    "russell": "3", "russell1000": "3",
    "wilshire": "4", "wilshire5000": "4",
    "etf": "11",
    "crypto": "16", "cryptos": "16", "cryptocurrency": "16", "cryptocurrencies": "16",
    "bonds": "10", "govbonds": "10", "governmentbonds": "10", "treasuries": "10",
    "europe": "12", "london": "12", "lse": "12", "uk": "12",
    "toronto": "13", "canada": "13", "tsx": "13",
    "futures": "7", "commodities": "7",
    "forex": "8", "fx": "8", "currencies": "8",
    "indices": "6", "indexes": "6",
}


def _resolve_market_token(tok, name_map):
    """One market token -> catalog id. Accepts the id itself, the exact name
    (case-insensitive), a known alias, or an unambiguous name fragment ('crypto').
    Returns the id string or None (unknown/ambiguous). Resolution NEVER consults the
    caller's scope - scope is checked separately (_require_scope) so an out-of-scope
    market reads as a true upgrade, never as a typo."""
    t = str(tok).strip()
    if not t:
        return None
    if t in name_map:                       # permanent resource key
        return t
    low = t.lower()
    for mid, name in name_map.items():
        if str(name).strip().lower() == low:
            return str(mid)
    sq = _squash(t)
    if not sq:
        return None
    if sq in _MARKET_ALIASES and _MARKET_ALIASES[sq] in name_map:
        return _MARKET_ALIASES[sq]
    sq_names = {str(mid): _squash(name) for mid, name in name_map.items()}
    exact = [mid for mid, sname in sq_names.items() if sname == sq]
    if len(exact) == 1:
        return exact[0]
    frags = [mid for mid, sname in sq_names.items() if sq in sname]
    if len(frags) == 1:
        return frags[0]
    return None


def _market_arg(raw):
    """Resolve a single market request value forgivingly (id / exact name / alias /
    unambiguous fragment, case-insensitive). Returns (market_id, None) on success or
    (None, error_response). Unknown -> a 400 with guidance, kept DISTINCT from the
    out-of-scope 403 (_require_scope, applied after) so a paying user passing a real
    catalog name never sees a false 'upgrade for market access'. If the catalog itself
    is unreachable, falls back to the raw value (pre-resolution behavior) rather than
    failing the request."""
    if raw is None or str(raw).strip() == "":
        return None, _err("invalid_request", "query param 'market' is required", 400)
    try:
        name_map = appserver_client.market_name_map()
    except requests.RequestException as e:
        log.warning("market catalog unavailable for resolution; using raw value: %s", e)
        return str(raw).strip(), None
    mid = _resolve_market_token(raw, name_map)
    if mid is None:
        return None, _err(
            "invalid_request",
            "unknown market '%s' - pass a market id or a name from /v1/markets "
            "(e.g. '2' or 'S&P 500 STOCKS')" % raw, 400)
    return mid, None


def _parse_markets_param(raw, name_map):
    """Resolve the `markets` csv to in-scope ids. Each token may be a market id ('2'),
    an exact catalog name (case-insensitive: 'S&P 500 STOCKS'), a common alias ('sp500',
    'crypto', 'europe'), or an unambiguous name fragment. Returns
    (ids, unknown_tokens, out_of_scope_labels) so the caller can distinguish a typo
    (-> 400) from a real market outside the plan (-> the honest upgrade 403) instead of
    silently dropping either. Default (raw empty) = the liquid core within scope."""
    scope = set(_in_scope_markets())
    if not raw:
        # Default to the liquid core (intersected with the caller's scope) to keep the
        # no-markets scan fast; fall back to full scope if none of the core is in scope.
        core = [m for m in _DEFAULT_SCAN_MARKETS if m in scope]
        return (core or [m for m in _in_scope_markets()]), [], []
    out, unknown, out_of_scope = [], [], []
    for tok in raw.split(","):
        t = tok.strip()
        if not t:
            continue
        mid = _resolve_market_token(t, name_map)
        if mid is None:
            unknown.append(t)
        elif mid not in scope:
            out_of_scope.append("%s (%s)" % (name_map.get(mid, mid), mid))
        else:
            out.append(mid)
    # dedupe, preserve order
    seen = set()
    return [m for m in out if not (m in seen or seen.add(m))], unknown, out_of_scope


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


def _min_win_rate_arg():
    """min_win_rate is a 0..1 FRACTION (share of profitable years). Humans habitually
    pass a percent (90); silently matching nothing would be a confident lie, so values
    in (1, 100] auto-normalize (90 -> 0.9) with an explanatory note, and anything > 100
    raises ValueError (-> 400). Returns (value_or_None, note_or_None)."""
    raw = request.args.get("min_win_rate", type=float)
    if raw is None:
        return None, None
    if raw > 100:
        raise ValueError("min_win_rate is a 0..1 fraction (90%% = 0.9); got %g" % raw)
    if raw > 1:
        return raw / 100.0, ("min_win_rate=%g was interpreted as a percent and "
                             "normalized to %g (the parameter is a 0..1 fraction)."
                             % (raw, raw / 100.0))
    return raw, None


# Primary-listing preference for scan dedupe ties (mirrors analyze's bare-ticker
# resolution order: S&P 500 -> DOW 30 -> NASDAQ 100).
_PRIMARY_MARKET_ORDER = {"2": 0, "0": 1, "1": 2}


# Markets whose SHARED TICKER means the SAME instrument (the US equity index
# memberships + the ETF list). Outside this group, equal tickers are frequently
# DIFFERENT instruments (CL = Colgate in S&P 500 but Crude Oil in futures), so
# the dedupe key keeps the market id and never merges them.
_SAME_INSTRUMENT_MARKETS = {"0", "1", "2", "3", "4", "11"}


def _dedupe_scan_rows(rows):
    """Collapse the SAME setup listed by several markets (e.g. MSFT in DOW 30 + NASDAQ
    100 + S&P 500) to ONE row, keyed (symbol, direction, entry_date, days_out) WITHIN
    the US-equity cross-listing group only - a live top-8 once carried MSFT x3.
    Preference: the ML-eligible market's row first (keeps ML enrichment possible),
    then the primary US listing order, then the higher Sharpe. First-appearance
    order is preserved (the scan re-sorts by Sharpe right after)."""
    def _pref(o):
        m = str(o.get("market"))
        return (0 if _ml_eligible(m) else 1,
                _PRIMARY_MARKET_ORDER.get(m, 9),
                -(o.get("sharpe_ratio") or 0))

    best, order = {}, []
    for o in rows:
        m = str(o.get("market"))
        group = "us-equity" if m in _SAME_INSTRUMENT_MARKETS else m
        k = (group, o.get("symbol"), o.get("direction"), o.get("entry_date"), o.get("days_out"))
        cur = best.get(k)
        if cur is None:
            best[k] = o
            order.append(k)
        elif _pref(o) < _pref(cur):
            best[k] = o
    return [best[k] for k in order]


def _last_trading_day(today=None):
    """The most recent weekday (Mon-Fri). A naive approximation (market holidays are not
    modeled), used ONLY for the daily-pick staleness note - which is phrased as a soft
    'may not have been generated', never a hard claim."""
    d = today or datetime.date.today()
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


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
            # which seasonal pattern-detection paths exist for this market + an example win-rate
            # band, so an agent can answer coverage/band questions without a trial call.
            "pattern_detection": market_bands.market_summary(m["id"]),
        })
    return jsonify({"markets": out})


@v1.get("/me")
@require_api_key
def me():
    """Identity + capabilities for the caller's key: plan tier, ML allowance left
    today, and in-scope markets. Powers the MCP `whoami` tool. Reads only - does
    NOT consume ML allowance. Under MCP OAuth, g.customer is already the end
    user's tier, so this reflects them, not the MCP service principal."""
    ent = g.customer["entitlements"]
    scope = set(ent["markets"])
    in_scope = [{"id": m["id"], "name": m["name"], "ml_eligible": m["id"] in tiers.ML_MARKETS}
                for m in appserver_client.list_markets() if m["id"] in scope]
    return jsonify({
        "tier": g.customer["tier"],
        "tier_name": ent.get("name"),
        "ml_remaining_today": ml_quota.remaining(g.customer),  # None = unlimited
        "ml_daily_limit": ent.get("ml_daily_limit"),
        "opp_limit": ent.get("opp_limit"),
        "rate": ent.get("rate"),
        "markets_in_scope": in_scope,
        "upgrade_url": _UPGRADE_URL,
        # Structural in-chat teaser disclosure (MCP OAuth principals only; non-MCP callers
        # never carry teaser_state, so default to the inactive contract - never a KeyError).
        "teaser_state": g.customer.get("teaser_state") or {
            "active": False, "kind": None, "ends_at": None, "post_teaser_scope": None},
    })


@v1.get("/markets/<market_id>/symbols")
@require_api_key
def symbols(market_id):
    """Symbols for one market. A full market is large (S&P 500 alone is ~150KB), so the
    list pages: `prefix` filters by ticker prefix (case-insensitive) and `limit` caps the
    rows returned; `total`/`matched`/`count` make any truncation explicit, never silent."""
    r = _demo_block_enumeration()  # full symbol list = the scraping vector - block the demo token
    if r:
        return r
    market_id, m_err = _market_arg(market_id)
    if m_err:
        return m_err
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    syms = appserver_client.list_symbols(market_id)
    total = len(syms)
    prefix = (request.args.get("prefix") or "").strip().upper()
    if prefix:
        syms = [s for s in syms if str(s.get("symbol", "")).upper().startswith(prefix)]
    matched = len(syms)
    limit = request.args.get("limit", type=int)
    if limit is not None and limit >= 0:
        syms = syms[:limit]
    out = {"symbols": syms, "count": len(syms), "matched": matched, "total": total}
    if len(syms) < matched:
        out["note"] = ("showing %d of %d matching symbols - raise 'limit' or narrow "
                       "'prefix' for the rest" % (len(syms), matched))
    return jsonify(out)


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


def _lookback_args(market=None, path="scan", *, pe_mode=False, name_map=None):
    """The two pattern-DETECTION knobs the engine exposes (OppList4/OppBySymbol year1/year2):
      - years (year1): the LOOKBACK - how many years to scan for patterns (5-98, data-dependent).
        In PE mode this is the number of PE-position occurrences (e.g. the last 10 PE+2 years).
      - min_winning_years (year2): of those, the minimum number of WINNING years required for a
        pattern to be listed. e.g. years=10 & min_winning_years=9 is the classic '10-9' (>=90% of
        years won); '17-15' is years=17 & min_winning_years=15. Detection floors around 80%+.
    The engine serves only the per-market PRE-COMPUTED (year1, year2) datasets - it detects
    patterns inside a market-specific WIN-RATE BAND (year2/year1 floor; e.g. S&P 500 ~80-85%,
    Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback). So min_winning_years is NOT free:
    it must lie in [market_floor(year1), year1]. This function:
      - defaults min_winning_years to ~90% of years (clamped into the band) when omitted, so a
        bare years=20 yields a valid 20-18, NOT the old fixed 9 (which was out of band for any
        year1>~11 and silently returned nothing);
      - for a SINGLE market (market given), strictly validates the combo against that market's
        band and raises ValueError with the valid range if out of band (or if the symbol path is
        not available for that market);
      - for the multi-market scan (market=None) stays lenient (the band differs per market; the
        scan route annotates out-of-band markets instead);
      - skips the band check for PE mode (pe_mode=True), whose grid differs (year1 = #cycle
        occurrences); only the sanity bounds apply there.
    path is 'scan' (OppList4/Monthly_Opp grid, all markets) or 'symbol' (OppBySymbol grid, 5
    markets only). Returns (year1_str, year2_str). Raises ValueError on a bad/out-of-band value."""
    years = request.args.get("years", default=10, type=int)
    mwy_raw = request.args.get("min_winning_years", type=int)  # None when omitted
    if years is None or not (1 <= years <= 99):
        raise ValueError("years (lookback) must be an integer between 1 and 99")
    if mwy_raw is None:
        mwy = market_bands.default_year2(years, market_id=market, path=path)
    else:
        mwy = mwy_raw
        if not (0 <= mwy <= years):
            raise ValueError("min_winning_years must be an integer between 0 and years")
    if market is not None and not pe_mode:
        nm = name_map or appserver_client.market_name_map()
        err = market_bands.validate(market, years, mwy, path, display_name=nm.get(str(market)))
        if err:
            raise ValueError(err)
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
    market, m_err = _market_arg(request.args.get("market"))
    if m_err:
        return m_err
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    # OppList4 is keyed to a SINGLE entry date (month + day), so 'from' is the entry
    # date (default today). This endpoint is single-date by design; for a true date
    # WINDOW (now / next_2_weeks / next_month / from..to) use /v1/scan, which owns
    # windowed scanning. 'to' is accepted but NOT used to widen the query here; the
    # response sets window_supported=false so callers are never silently misled.
    entry_date = request.args.get("from") or _today()

    # min_win_rate filters on the REAL historical win rate (share of profitable years,
    # from ChartData4 'Percent Profitable') - NOT the ML win_prob. The OppList4 feed
    # has no per-row win rate, so we enrich each row's win_rate per symbol via
    # ChartData4. That is one (cached) ChartData4 call per row, so it is capped at
    # appserver_client.MAX_WIN_RATE_ENRICH rows; when min_win_rate is set we enrich up
    # to that cap and drop rows we could not enrich (an unknown rate must NOT pass a
    # minimum filter). Without min_win_rate we still enrich up to the cap so win_rate is
    # populated, but we never drop rows.
    enrich_n = appserver_client.MAX_WIN_RATE_ENRICH

    try:
        direction = _direction_arg(request.args.get("direction"))  # long|short, optional
        min_win_rate, mwr_note = _min_win_rate_arg()
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # consecutive | pe (current cycle)
        year1, year2 = _lookback_args(market=market, path="scan",
                                      pe_mode=_opp_mode(pe_cycle) != "consecutive")
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    # Fetch RAW (no enrichment), apply the numeric column filters (pattern length, avg/median
    # profit %, Sharpe) on the raw rows FIRST, then enrich win_rate only on the survivors, so a
    # ChartData4 call is never spent on a row a column filter would have dropped.
    keep = _column_filters_from_args()
    opps = appserver_client.opportunities(
        market, entry_date, year1=year1, year2=year2, direction=direction,
        enrich_win_rate=0, mode=_opp_mode(pe_cycle))
    # demo token: scope to the allowlist BEFORE column filters/enrichment - this is a
    # single-market enumeration route (same bulk-exposure shape as /v1/scan), previously
    # unguarded (subscriber-UX audit 2026-07-10 sweep finding). No-op for a normal key.
    opps = _demo_scope_rows(opps)
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

    # Attach ML on ML-eligible markets, METERED by the daily allowance (free 5/day). We
    # RESERVE allowance for the rows we try, then REFUND any the model could not score (or
    # an upstream ML blip) so a metered customer is only ever charged for scores delivered;
    # ML is best-effort enrichment here and never fails the request.
    if opps and _ml_eligible(market):
        granted = ml_quota.consume(g.customer, len(opps))
        score_rows = opps[:granted]
        if score_rows:
            items = [
                {"symbol": o["symbol"], "date": o["entry_date"],
                 "days_out": o["days_out"], "direction": o["direction"]}
                for o in score_rows
            ]
            try:
                ml = appserver_client.ml_scores(market, items)
            except Exception as e:  # noqa: BLE001 - ML is best-effort enrichment, never fatal
                log.warning("opportunities ML scoring failed for market %s: %s", market, e)
                ml = []
            delivered = 0
            for o, score in zip(score_rows, ml):
                if score:
                    o["ml"] = score
                    delivered += 1
            ml_quota.refund(g.customer, granted - delivered)

    payload = {
        "opportunities": opps,
        "ml_remaining_today": ml_quota.remaining(g.customer),
        "entry_date": entry_date,
        "window_supported": False,  # single-date endpoint; use /v1/scan for windows
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
        # educational-only: any pattern-bearing response (win rates / ML / returns) carries the
        # exact disclaimer, not just the composed PatternCard endpoints.
        "disclaimer": cards.DISCLAIMER,
    }
    if mwr_note:
        payload["min_win_rate_note"] = mwr_note
    return jsonify(payload)


def _symbol_patterns_response(symbol):
    """A security's TOP SEASONAL PATTERNS across the year, sorted by Sharpe (OppBySymbol - the
    data behind the wave-viewer pattern dropdown). Shared by /v1/opportunities/<symbol> and the
    clearer alias /v1/securities/<symbol>/patterns. Supports pe_cycle=consecutive|pe and the
    numeric column filters (min_days/max_days/min_avg_return/min_median_return/min_sharpe)."""
    raw_market = request.args.get("market")
    if not raw_market:
        # Single-market shortcut: a caller with exactly one in-scope market (demo + free
        # tiers) needs no ?market, so /securities/AAPL/patterns works bare. Multi-market
        # callers still get the explicit 'market is required' 400 (the symbol is ambiguous).
        scoped = _in_scope_markets()
        if len(scoped) == 1:
            raw_market = scoped[0]
    market, m_err = _market_arg(raw_market)
    if m_err:
        return m_err
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err
    try:
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # OppBySymbol mode: consecutive | pe
        year1, year2 = _lookback_args(market=market, path="symbol",
                                      pe_mode=_opp_mode(pe_cycle) != "consecutive")
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
            # ML is best-effort: refund any reserved allowance the model did not deliver
            # (unscored row or an upstream blip) so a metered caller is only charged for
            # scores actually returned; never fail the request on an ML outage.
            try:
                ml = appserver_client.ml_scores(market, items)
            except Exception as e:  # noqa: BLE001 - ML is best-effort enrichment, never fatal
                log.warning("symbol-patterns ML scoring failed for market %s: %s", market, e)
                ml = []
            delivered = 0
            for o, score in zip(score_rows, ml):
                if score:
                    o["ml"] = score
                    delivered += 1
            ml_quota.refund(g.customer, granted - delivered)

    return jsonify({"opportunities": opps, "ml_remaining_today": ml_quota.remaining(g.customer),
                    "disclaimer": cards.DISCLAIMER})


@v1.get("/opportunities/<symbol>")
@require_api_key
def opportunities_by_symbol(symbol):
    r = _demo_guard_symbol(symbol)
    if r:
        return r
    return _symbol_patterns_response(symbol)


@v1.get("/securities/<symbol>/patterns")
@require_api_key
def symbol_patterns(symbol):
    """Clearly-named alias for the symbol's year-long ranked seasonal patterns (same data)."""
    r = _demo_guard_symbol(symbol)
    if r:
        return r
    return _symbol_patterns_response(symbol)


# --------------------------------------------------------------------------- #
# FLAGSHIP endpoints: build PatternCards via cards.py (one source of truth)     #
# --------------------------------------------------------------------------- #

_PREFETCH_NOT_PROVIDED = object()

# Only these percentage/ratio fields are needed to build a PatternCard. The scan
# core drops every other ChartData4 field before publishing to gateway Redis.
# Per-year entries retain only year + pct; any raw price is removed.
_SCAN_SAFE_STATS = {
    "Percent Profitable", "Sharpe Ratio", "Avg Profit - All", "Median Profit",
    "Std Dev", "Annualized Return", "Cumulative Return", "Sharpe Ratio2",
}
_SCAN_SAFE_OPP_FIELDS = {
    "symbol", "market", "direction", "entry_date", "days_out", "sharpe_ratio",
    "avg_profit_pct", "median_profit_pct", "win_rate", "years",
}
_SCAN_COLUMN_FILTER_PARAMS = (
    "min_days", "max_days", "min_avg_return", "min_median_return", "min_sharpe",
)


def _price_safe_scan_receipts(stats, chart_entries):
    safe_stats = {}
    if isinstance(stats, dict):
        safe_stats = {key: stats[key] for key in _SCAN_SAFE_STATS if key in stats}
    safe_entries = []
    if isinstance(chart_entries, list):
        for entry in chart_entries:
            if not isinstance(entry, dict):
                continue
            safe_entries.append({
                key: entry.get(key) for key in ("year", "pct") if key in entry
            })
    return safe_stats, safe_entries


def _price_safe_scan_opp(opp):
    """Project an internal opportunity onto the reusable, non-metered scan fields."""
    if not isinstance(opp, dict):
        return {}
    safe = {key: opp.get(key) for key in _SCAN_SAFE_OPP_FIELDS if key in opp}
    # ML is always recomputed after authentication and quota consumption. Keeping an
    # explicit empty slot preserves the Opportunity shape without sharing a score.
    safe["ml"] = None
    return safe

def _enrich_and_card(opp, *, ml_available, seasonal_curve=None, as_of=None, rank=None,
                     ml_state="na", name_map=None, include_chart=False,
                     prefetched_stats=_PREFETCH_NOT_PROVIDED,
                     prefetched_chart_entries=_PREFETCH_NOT_PROVIDED,
                     prefetched_receipts_unavailable=False):
    """Source receipts (ChartData4 stats + per-year entries) for ONE opp and build its
    card. Two distinct degraded paths, never conflated: a genuine per-symbol DATA GAP
    yields empty stats/entries and the card reflects the thin record; a FAILED fetch
    (429 after retries / timeout / upstream error, surfaced as (None, None)) stamps the
    card receipts_unavailable so it degrades to 'data temporarily unavailable' instead
    of a confident no-edge. Neither aborts the request."""
    if (prefetched_stats is _PREFETCH_NOT_PROVIDED
            or prefetched_chart_entries is _PREFETCH_NOT_PROVIDED):
        stats, chart_entries = appserver_client.chart_stats_and_years(
            opp["market"], opp["symbol"], opp["entry_date"],
            opp.get("days_out"), opp.get("years"))
        receipts_unavailable = stats is None and chart_entries is None
    else:
        stats = prefetched_stats
        chart_entries = prefetched_chart_entries
        receipts_unavailable = bool(prefetched_receipts_unavailable)
    if receipts_unavailable:
        stats, chart_entries = {}, []
    elif opp.get("win_rate") is None:
        # win_rate from the same stats (so historical_win_rate is consistent everywhere)
        opp["win_rate"] = appserver_client._win_rate_from_stats(stats)
    name_map = name_map or appserver_client.market_name_map()
    market_name = name_map.get(str(opp["market"]), str(opp["market"]))
    ml = opp.get("ml")
    return cards.build_pattern_card(
        opp, stats, chart_entries, market_name=market_name, ml=ml,
        ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=as_of,
        rank=rank, ml_state=ml_state, include_chart=include_chart,
        receipts_unavailable=receipts_unavailable)


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
    """find_best_opportunities: cross-market ranked seasonal scan -> PatternCard[].

    Fans out OppList4 over the caller's in-scope markets IN PARALLEL, resolves the window
    to entry dates, ranks (default by Sharpe), tier-caps, then enriches ONLY the
    surviving rows (win_rate + receipts + Pro ML) so we never fan out ChartData4 NxM."""
    name_map = appserver_client.market_name_map()
    markets_param = request.args.get("markets")
    market_ids, unknown_toks, out_of_scope = _parse_markets_param(markets_param, name_map)
    if not market_ids:
        # Distinct failures: a real catalog market outside the plan is the honest upgrade
        # 403; a typo/unknown token is a 400 with guidance - NEVER an upsell.
        if out_of_scope:
            return jsonify({"error": {
                "code": "forbidden",
                "message": "market(s) %s are not in your plan's scope - upgrade for full "
                           "market access" % ", ".join(out_of_scope),
                "upgrade_url": _UPGRADE_URL,
            }}), 403
        if unknown_toks:
            return _err("invalid_request",
                        "unknown market(s): %s - pass ids or names from /v1/markets "
                        "(e.g. '2' or 'S&P 500 STOCKS')" % ", ".join(unknown_toks), 400)
        return _err("invalid_request",
                    "no in-scope markets resolved from 'markets' - check ids/names and your plan scope",
                    400)
    notes = []
    if out_of_scope:
        notes.append("out-of-scope market(s) skipped: %s - upgrade for access: %s"
                     % (", ".join(out_of_scope), _UPGRADE_URL))
    if unknown_toks:
        notes.append("unknown market token(s) ignored: %s" % ", ".join(unknown_toks))
    markets_note = "; ".join(notes) or None

    win = _resolve_window(request.args.get("window"))
    if win is None:
        return _err("invalid_request",
                    "invalid 'window' - use now | next_2_weeks | next_month | YYYY-MM-DD..YYYY-MM-DD",
                    400)
    entry_lo, entry_hi, window_label = win

    min_years = request.args.get("min_years", type=int)
    # Default ranking = Sharpe descending, mirroring TradeWave's own daily-pick + SMN 'AI'
    # selectors (filter on win metrics, then sort by Sharpe). edge_score stays available
    # as a rank_by option and is shown on every card.
    rank_by = (request.args.get("rank_by") or "sharpe").strip().lower()
    if rank_by not in _RANK_KEYS:
        rank_by = "sharpe"
    try:
        direction = _direction_arg(request.args.get("direction"))
        min_win_rate, mwr_note = _min_win_rate_arg()
        pe_cycle = _resolve_pe_cycle(allow_positions=False)  # consecutive | pe (current cycle)
        # multi-market scan: lenient (market=None) - the band differs per market, so we default
        # min_winning_years to ~90% and annotate any out-of-band markets below rather than error.
        year1, year2 = _lookback_args(market=None, path="scan",
                                      pe_mode=_opp_mode(pe_cycle) != "consecutive")
    except ValueError as e:
        return _err("invalid_request", str(e), 400)

    tier_cap = g.customer["entitlements"]["opp_limit"]
    req_limit = request.args.get("limit", default=25, type=int)  # matches openapi.yaml /scan default
    if req_limit < 0:
        req_limit = 0
    effective_limit = min(req_limit, tier_cap)

    # Default Sharpe scans with no post-receipt filters need only the requested rows.
    # Other rankings / trust filters may reorder or reject rows, so retain the bounded
    # 50-row head for correctness. The depth is part of the shared cache key.
    needs_full_head = bool(
        min_win_rate is not None or min_years is not None or rank_by != "sharpe"
    )
    core_depth = _SCAN_ENRICH_CAP if needs_full_head else min(
        effective_limit, _SCAN_ENRICH_CAP
    )
    column_filter_key = {
        key: request.args.get(key) for key in _SCAN_COLUMN_FILTER_PARAMS
        if request.args.get(key) is not None
    }
    demo_enabled = bool(g.customer["entitlements"].get("demo"))
    cache_key = scan_cache.make_key({
        "markets": sorted(str(mid) for mid in market_ids),
        "entry_lo": entry_lo.isoformat(),
        "entry_hi": entry_hi.isoformat(),
        "years": str(year1),
        "min_winning_years": str(year2),
        "direction": direction,
        "pe_mode": _opp_mode(pe_cycle),
        "column_filters": column_filter_key,
        "depth": core_depth,
        "demo": demo_enabled,
        "demo_symbols": sorted(g.customer["entitlements"].get("demo_symbols", []))
        if demo_enabled else [],
    })

    def _build_scan_core():
        multi = appserver_client.opportunities_multi(
            market_ids, entry_lo.isoformat(), year1=year1, year2=year2,
            direction=direction, mode=_opp_mode(pe_cycle), return_failures=True)
        if (isinstance(multi, tuple) and len(multi) == 2
                and isinstance(multi[1], list)):
            raw, failed_markets = multi
        else:
            # Unit-test fakes and older compatible clients return the historical list.
            raw, failed_markets = multi, []

        # Demo remains scoped before enrichment. Its cache key is separate from normal
        # customers, so a public token can never read a full-universe core.
        raw = _demo_scope_rows(raw)
        in_window = []
        for opp in raw:
            entry_date = cards._parse_date(opp.get("entry_date"))
            if entry_date is not None and entry_lo <= entry_date <= entry_hi:
                in_window.append(_price_safe_scan_opp(opp))

        keep = _column_filters_from_args()
        in_window = [opp for opp in in_window if keep(opp)]
        in_window = _dedupe_scan_rows(in_window)
        evaluated = len(in_window)
        in_window.sort(key=lambda opp: opp.get("sharpe_ratio") or 0, reverse=True)
        selected = in_window[:core_depth]

        def _fetch_receipts(opp):
            stats, entries = appserver_client.chart_stats_and_years(
                opp["market"], opp["symbol"], opp["entry_date"],
                opp.get("days_out"), opp.get("years"))
            unavailable = stats is None and entries is None
            if unavailable:
                stats, entries = {}, []
            safe_stats, safe_entries = _price_safe_scan_receipts(stats, entries)
            if not unavailable and opp.get("win_rate") is None:
                opp["win_rate"] = appserver_client._win_rate_from_stats(safe_stats)
            return {
                "opp": opp,
                "stats": safe_stats,
                "chart_entries": safe_entries,
                "receipts_unavailable": unavailable,
            }

        records = []
        if selected:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                records = list(executor.map(_fetch_receipts, selected))
        degraded = any(record["receipts_unavailable"] for record in records)
        value = {
            "evaluated_count": evaluated,
            "enrichment_capped": evaluated > len(records),
            "failed_markets": failed_markets,
            "candidates": records,
        }
        # Empty is cacheable when every requested market responded successfully. A
        # partial market failure or transient receipt failure is never published.
        return scan_cache.BuildResult(
            value=value,
            cacheable=not failed_markets and not degraded,
        )

    try:
        cache_result = scan_cache.get_or_build(cache_key, _build_scan_core)
    except scan_cache.ScanBuildBusy:
        response = jsonify({"error": {
            "code": "scan_busy",
            "message": "scan capacity is busy building fresh data - retry shortly",
        }})
        response.status_code = 503
        response.headers["Retry-After"] = "1"
        response.headers["X-TW-Scan-Cache"] = "BUSY"
        return response

    core = cache_result.value
    evaluated_count = int(core.get("evaluated_count") or 0)
    enrichment_capped = bool(core.get("enrichment_capped"))
    failed_markets = [str(market) for market in (core.get("failed_markets") or [])]
    records = list(core.get("candidates") or [])
    head = [record.get("opp") or {} for record in records]

    # Trust filters are customer/query overlays and are never cached into shared data.
    filtered_records = records
    if min_win_rate is not None:
        filtered_records = [
            record for record in filtered_records
            if (record.get("opp") or {}).get("win_rate") is not None
            and (record.get("opp") or {})["win_rate"] >= min_win_rate
        ]

    # 6) attach ML inline, METERED by the daily allowance (free 5/day, unlimited Pro).
    #    filtered is in Sharpe order, so we spend the allowance on the strongest setups.
    #    We RESERVE allowance for the rows we will try, then REFUND any the model could not
    #    score (e.g. a hold longer than the model covers), so a metered customer is only
    #    ever charged for ML scores actually delivered. Rows past the allowance are left
    #    unattempted (a true 'quota' note); attempted-but-unscored rows get the neutral
    #    'unavailable' note - never a false "upgrade for unlimited" nudge.
    eligible = [record["opp"] for record in filtered_records
                if _ml_eligible(record["opp"]["market"])]
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

    # 7) build cards WITHOUT the seasonal curve first (parallel) - curve_summary is only
    #    needed on the cards we actually RETURN, so we fetch it for the ranked top-N below
    #    (avoids a curve round-trip for every candidate that gets ranked out). max_workers=4
    #    bounds the shared appserver bucket; the card-build helpers are g-free.
    _as_of = _today()
    def _build_card(record):
        o = record["opp"]
        ml_available = bool(o.get("ml"))
        card = _enrich_and_card(
            o, ml_available=ml_available, as_of=_as_of,
            ml_state=_ml_state_for(o, ml_available), name_map=name_map,
            prefetched_stats=record.get("stats") or {},
            prefetched_chart_entries=record.get("chart_entries") or [],
            prefetched_receipts_unavailable=record.get("receipts_unavailable", False))
        card["_opp"] = o
        card["_chart_entries"] = record.get("chart_entries") or []
        return card

    built = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _ex:
        for card in _ex.map(_build_card, filtered_records):
            # years_tested is None on a receipts_unavailable card: an unverifiable record
            # is kept (with its explicit flag), never silently dropped by a trust filter.
            yt = card["receipts"].get("years_tested")
            if min_years is not None and yt is not None and yt < min_years:
                continue
            card["_sortkey"] = _scan_sortkey(card, rank_by)
            built.append(card)

    built.sort(key=lambda c: c["_sortkey"], reverse=True)
    pre_cap_count = len(built)
    built = built[:effective_limit]
    # the FREE-TIER WALL, made visible: true only when the PLAN cap (not the caller's own
    # limit) was the binding constraint on how many ranked cards came back.
    if not needs_full_head:
        candidate_count_after_filters = evaluated_count
    else:
        candidate_count_after_filters = pre_cap_count
    capped_by_plan = (
        candidate_count_after_filters > effective_limit and tier_cap < req_limit
    )

    # curve_summary for the RETURNED cards only (parallel): the richest narratable line,
    # without paying a curve fetch for cards that ranked out. Mirrors build_pattern_card's
    # hold-window slice (the curve starts at entry; the first days_out points are the section).
    include_chart = _wants_chart()
    primary = built[0] if built else None

    def _add_curve(card):
        o = card["_opp"]
        try:
            curve = appserver_client._seasonal_curve(
                o["market"], o["symbol"], o["entry_date"], o.get("years") or "10")
        except Exception:  # noqa: BLE001 - curve_summary is optional, never fatal
            return
        if not curve:
            return
        hold = o.get("days_out")
        section = curve[:hold] if isinstance(hold, int) and hold > 1 else curve
        card["receipts"]["curve_summary"] = cards.curve_summary(section)
        if include_chart and card is primary:
            cards.attach_chart_evidence(
                card, curve, card.get("_chart_entries") or [], o.get("direction"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _ex:
        list(_ex.map(_add_curve, built))

    # Even when the optional seasonal curve fetch fails, keep the winner's per-year
    # evidence chart. A partial evidence pack is more useful than silently dropping both.
    if include_chart and primary is not None and "chart" not in primary:
        cards.attach_chart_evidence(
            primary, [], primary.get("_chart_entries") or [],
            (primary.get("_opp") or {}).get("direction"))

    for i, c in enumerate(built, 1):
        c["rank"] = i
        c.pop("_sortkey", None)
        c.pop("_opp", None)
        c.pop("_chart_entries", None)

    # --- the honest one-line lead (computed on the FULL cards, before projection) ---
    # Scan honesty: an all-neutral page must never read as "Found N setups"; a degraded
    # enrichment (rate-limited win-rate/receipts fetches) must say so; a plan-capped list
    # must show the wall (mirroring the ML-nudge pattern) instead of a quietly short list.
    shown = len(built)
    high_conviction = sum(1 for c in built if c.get("bias") != "neutral")
    degraded_rows = sum(
        1 for c in built
        if (c.get("receipts") or {}).get("receipts_unavailable")
        or (c.get("stats") or {}).get("historical_win_rate") is None)
    cand = "candidate" if evaluated_count == 1 else "candidates"
    if shown == 0:
        summary = ("Evaluated %d %s - none matched the filters. Try widening the "
                   "window or markets, or relaxing the filters." % (evaluated_count, cand))
    elif high_conviction == 0:
        summary = ("Evaluated %d %s - 0 have a high-conviction edge right now; the "
                   "%d shown are neutral (listed for transparency, nothing to act on)."
                   % (evaluated_count, cand, shown))
    else:
        summary = ("Evaluated %d %s - showing %d ranked seasonal setups, %d with a "
                   "high-conviction seasonal pattern." % (evaluated_count, cand, shown, high_conviction))
    if degraded_rows:
        summary += (" Win-rate data unavailable for %d row(s) (upstream rate limit/outage) - "
                    "those rows are shown unverified; retry shortly." % degraded_rows)
    if failed_markets:
        summary += (
            " Data was unavailable for market(s) %s; their results are omitted, so retry "
            "before treating this scan as complete."
            % ", ".join(name_map.get(market, market) for market in failed_markets)
        )
    if enrichment_capped:
        summary += (" Only the top %d candidates (by Sharpe) were fully evaluated "
                    "(enrichment cap)." % len(head))
    if mwr_note:
        summary += " " + mwr_note
    if capped_by_plan:
        # last, so the bare URL cleanly terminates the summary string.
        summary += (" Results are capped by your plan: showing %d of %d evaluated - "
                    "upgrade for the full ranked list: %s" % (shown, evaluated_count, _UPGRADE_URL))

    # progressive disclosure: shape each card to the requested verbosity (default lean view
    # comes from the MCP layer; the raw API defaults to 'full' / backward-compatible).
    view = _view_arg()
    opportunities = [cards.project_card(c, view) for c in built]

    # never silent: if the (year1, year2) combo is out of band for some scanned markets, those
    # markets contributed nothing - tell the caller rather than returning a quietly short list.
    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "window": window_label,
        "markets_scanned": market_ids,
        "market_failures": failed_markets,
        "rank_by": rank_by,
        "view": view,
        "lookback": {"years": int(year1), "min_winning_years": int(year2)},
        "count": len(built),
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
        "capped_by_plan": capped_by_plan,
        "shown_of_evaluated": "%d of %d" % (shown, evaluated_count),
        "ml_remaining_today": ml_quota.remaining(g.customer),  # None = unlimited
        "opportunities": opportunities,
        # envelope-level disclaimer: guarantees it survives a 'table' projection (rows are
        # compact and carry no per-card disclaimer) for both API and MCP consumers.
        "disclaimer": cards.DISCLAIMER,
    }
    if capped_by_plan:
        payload["upgrade_url"] = _UPGRADE_URL
    if mwr_note:
        payload["min_win_rate_note"] = mwr_note
    if markets_note:
        payload["markets_note"] = markets_note
    oob = market_bands.out_of_band_markets(market_ids, year1, year2, "scan")
    if oob:
        names = appserver_client.market_name_map()
        payload["lookback_note"] = (
            "min_winning_years=%s is outside the detection band for %s at a %s-year lookback, "
            "so those markets returned nothing. Raise min_winning_years (toward %s) to include them."
            % (year2, ", ".join(names.get(m, m) for m in oob), year1, year1))
    response = jsonify(payload)
    response.headers["X-TW-Scan-Cache"] = cache_result.status
    response.headers["Server-Timing"] = f'scan-cache;desc="{cache_result.status}"'
    return response


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
    rich PatternCard (the best setup) + compact other_setups[]."""
    r = _demo_guard_symbol(symbol)
    if r:
        return r
    name_map = appserver_client.market_name_map()
    market = request.args.get("market")
    resolution_note = None

    if market:
        # forgiving resolution (id / exact name / alias / fragment, case-insensitive):
        # 'S&P 500 STOCKS' or 'sp500' must work, and an unknown value is a 400 - a paying
        # user must never see a false 'upgrade for market access' for a name/typo.
        market, m_err = _market_arg(market)
        if m_err:
            return m_err
    else:
        # Single-market shortcut: if the caller has exactly one in-scope market (demo + free
        # tiers), use it directly and skip resolve_market_for_symbol (that helper calls
        # GetListSymbols, which currently 500s) - so /analyze/AAPL works with no ?market.
        scoped = _in_scope_markets()
        if len(scoped) == 1:
            market = scoped[0]
            candidates = scoped
        else:
            candidates = appserver_client.resolve_market_for_symbol(symbol, scoped)
        if not candidates:
            return _err("not_found",
                        "symbol '%s' not found in any of your in-scope markets - pass ?market=<id>"
                        % symbol, 404)
        if len(candidates) > 1:
            # A bare ticker is the most common entry path - resolve to the primary US listing
            # (S&P 500 -> DOW 30 -> NASDAQ 100) and note the alternatives, rather than hard-erroring.
            # Strict disambiguation is opt-in via ?strict=1.
            if request.args.get("strict", "").strip().lower() in ("1", "true", "yes"):
                return _err("invalid_request",
                            "symbol '%s' exists in multiple markets %s - specify ?market=<id>"
                            % (symbol, ",".join(sorted(candidates))), 400)
            market = next((m for m in ("2", "0", "1") if m in candidates), sorted(candidates)[0])
            others = ", ".join("%s (%s)" % (name_map.get(c, c), c)
                               for c in sorted(candidates) if c != market)
            resolution_note = ("Using %s on %s. It also trades in: %s - pass ?market=<id> to pick another."
                               % (symbol.upper(), name_map.get(market, market), others))
        else:
            market = candidates[0]

    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    try:
        direction = _direction_arg(request.args.get("direction"))
        pe_cycle = _resolve_pe_cycle(allow_positions=False)        # consecutive | pe (wave-viewer knob)
        # OppBySymbol is a precomputed detection grid keyed by BOTH lookback and its
        # market-specific winning-years floor. Never pair a custom lookback with the
        # client's legacy default year2=9 (for example, 16/9 returns no ITW patterns).
        year1, year2 = _lookback_args(
            market=market,
            path="symbol",
            pe_mode=_opp_mode(pe_cycle) != "consecutive",
            name_map=name_map,
        )
        years_n = int(year1)
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
        market, symbol, year1=year1, year2=year2, mode=_opp_mode(pe_cycle))
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
            # OppBySymbol has no per-symbol file for some markets (e.g. ETFs/crypto) even when
            # the cross-market scanner (OppList4) ranks the symbol. Fall back to today's market
            # scan kept to this symbol, so 'find a trade -> tell me more about #1' stays coherent.
            scan_rows = appserver_client.opportunities(
                market, _today(), year1=year1, year2=year2, direction=direction or None,
                enrich_win_rate=5, mode=_opp_mode(pe_cycle))
            opps = [o for o in scan_rows if o.get("symbol") == symbol]
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

    include_chart = _wants_chart()
    card = _enrich_and_card(
        best, ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=_today(),
        rank=1, ml_state=_ml_state_for(best, ml_available), name_map=name_map,
        include_chart=include_chart)
    if resolution_note:
        card["note"] = resolution_note
    view = _view_arg()
    card = cards.project_card(card, view)

    other = [cards.compact_setup(o) for o in opps[1:]]
    tier_cap = g.customer["entitlements"]["opp_limit"]
    other = other[: max(0, tier_cap - 1)]

    return jsonify({"card": card, "other_setups": other, "view": view,
                    "disclaimer": cards.DISCLAIMER, "as_of": _today()})


@v1.get("/patterns/<market_id>/<symbol>")
@require_api_key
def pattern(market_id, symbol):
    r = _demo_guard_symbol(symbol)
    if r:
        return r
    market_id, m_err = _market_arg(market_id)
    if m_err:
        return m_err
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    try:
        entry_date, days_out, yrs = _chart_window_and_years(symbol)
    except ValueError as e:
        return _err("invalid_request", str(e), 400)
    try:
        data = appserver_client.pattern_stats(market_id, symbol, entry_date, days_out, yrs)
    except requests.RequestException as e:
        # upstream 429 (after the client's bounded retries) / timeout / error: a structured,
        # retryable 503 - never an opaque 500 (and never presented as a data gap).
        log.warning("patterns upstream unavailable for %s/%s: %s", market_id, symbol, e)
        return _err("upstream_unavailable",
                    "chart data temporarily unavailable - retry shortly", 503)
    if isinstance(data, dict):
        data["disclaimer"] = cards.DISCLAIMER  # educational-only: win-rate/stats payload
    return jsonify(data)


@v1.get("/seasonal-chart")
@require_api_key
def seasonal_chart():
    market = request.args.get("market")
    symbol = request.args.get("symbol")
    if not market or not symbol:
        return _err("invalid_request", "query params 'market' and 'symbol' are required", 400)
    r = _demo_guard_symbol(symbol)
    if r:
        return r
    market, m_err = _market_arg(market)
    if m_err:
        return m_err
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err
    try:
        direction = _direction_arg(request.args.get("direction"))
        entry_date, days_out, yrs = _chart_window_and_years(symbol)
    except ValueError as e:
        return _err("invalid_request", str(e), 400)
    try:
        data = appserver_client.seasonal_chart(
            market, symbol, entry_date, days_out, yrs, direction=direction)
    except requests.RequestException as e:
        # upstream 429 (after the client's bounded retries) / timeout / error: a structured,
        # retryable 503 - never an opaque 500 (and never presented as a data gap).
        log.warning("seasonal-chart upstream unavailable for %s/%s: %s", market, symbol, e)
        return _err("upstream_unavailable",
                    "chart data temporarily unavailable - retry shortly", 503)
    if isinstance(data, dict):
        data["disclaimer"] = cards.DISCLAIMER  # educational-only: Trend Chart + win-rate payload
    return jsonify(data)


@v1.post("/score")
@require_api_key
def score():
    # Preserve the dev branch's explicit demo response copy while keeping the same
    # anti-enumeration behavior as _demo_block_enumeration().
    if g.customer["entitlements"].get("demo"):
        return jsonify({"error": {"code": "demo_restricted",
            "message": "batch scoring is not available on the demo token - use GET /v1/analyze/{symbol} on the demo tickers, or create a free API key for full access"}}), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _err("invalid_request", "JSON body with 'opportunities' is required", 400)
    items = body.get("opportunities")
    if not isinstance(items, list) or not items:
        return _err("invalid_request", "'opportunities' must be a non-empty array", 400)
    if len(items) > _SCORE_BATCH_CAP:
        # A few-hundred-item cold batch outlives the edge timeout; cap it with a clear
        # 400 that NAMES the cap instead of letting the request die mid-flight.
        return _err("invalid_request",
                    "'opportunities' is capped at %d items per request (got %d) - split "
                    "the batch into chunks of at most %d"
                    % (_SCORE_BATCH_CAP, len(items), _SCORE_BATCH_CAP), 400)

    # ML-eligible markets only (0-4, 11). The score request items are not market-tagged
    # in the contract, so the market is taken from the 'market' query/body param and
    # must be ML-eligible. Default to S&P 500 ('2'), an ML-eligible market.
    market, m_err = _market_arg(request.args.get("market") or body.get("market") or "2")
    if m_err:
        return m_err
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
        try:
            direction = _direction_arg(it["direction"])
        except ValueError as e:
            return _err("invalid_request", str(e), 400)
        norm.append({
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": days_out_i,
            "direction": direction,
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

    # ML is best-effort: an upstream blip must REFUND the reserved allowance and degrade
    # soft (rows come back unscored), never 500 and never silently drop reserved rows.
    try:
        ml = appserver_client.ml_scores(market, norm[:granted])
    except Exception as e:  # noqa: BLE001 - ML enrichment, never fatal
        log.warning("score ML scoring failed for market %s: %s", market, e)
        ml = []
    scores = []
    delivered = 0
    attempted = norm[:granted]
    for i, it in enumerate(attempted):
        score = ml[i] if i < len(ml) else None
        row = {
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": it["days_out"],
            "direction": appserver_client._dir_to_public(it["direction"]),
        }
        if score:
            row.update(score)
            delivered += 1
        else:
            # appserver could not score it (e.g. days_out outside the 10-90 range) or an
            # upstream ML blip - the reserved allowance for this row is refunded below.
            row.update({"ml_score": None, "win_prob": None,
                        "pred_return": None, "pred_mfe": None})
        scores.append(row)
    # only ever charge for ML scores actually delivered.
    ml_quota.refund(g.customer, granted - delivered)
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
        "granted": delivered,
        "ml_remaining_today": ml_quota.remaining(g.customer),
        # educational-only: ML scores (win_prob / pred_return) are pattern-bearing.
        "disclaimer": cards.DISCLAIMER,
    })


@v1.get("/daily-pick")
@require_api_key
def daily_pick():
    """The daily AI pick as a full PatternCard + the LIVE forward-tested track record
    (the strongest receipt: made in advance, scored later). The pick's own seasonal
    receipts come from ChartData4; the live record comes from featured_history."""
    raw = appserver_client.daily_pick_raw()
    if not raw:
        return jsonify({"card": None, "track_record": None, "as_of": _today()})

    opp = raw["opp"]
    market = opp.get("market")
    # The daily pick is the FREE teaser - a single published seasonal pattern everyone sees - so its
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
        rank=1, ml_state=ml_state, include_chart=_wants_chart())

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

    # project AFTER folding the live record (the decision view keeps live_track_record).
    view = _view_arg()
    card = cards.project_card(card, view)

    # STALENESS GUARD: featured_history is written by the daily generator; if it has not
    # run for the most recent trading day, say so explicitly instead of presenting an old
    # pick silently as today's. Naive weekday check - holidays read as a soft 'may'.
    featured = raw.get("featured_date")
    featured_d = cards._parse_date(featured)
    expected = _last_trading_day()
    stale_note = None
    if featured_d is None or featured_d < expected:
        stale_note = ("This pick was featured on %s, NOT today (%s): no newer pick has "
                      "been generated for the most recent trading day (%s). Present it as "
                      "the %s pick - the latest available - not as today's."
                      % (featured, _today(), expected.isoformat(), featured))

    payload = {
        "card": card,
        "featured_date": featured,
        "track_record": live_record,
        "view": view,
        "disclaimer": cards.DISCLAIMER,
        "as_of": _today(),
    }
    if stale_note:
        payload["stale_note"] = stale_note
    return jsonify(payload)


@v1.get("/daily-pick/track-record")
@require_api_key
def track_record():
    data = appserver_client.track_record()
    if isinstance(data, dict):
        # educational-only: performance claims must carry the disclaimer ("past performance...").
        data["disclaimer"] = cards.DISCLAIMER
    return jsonify(data)
