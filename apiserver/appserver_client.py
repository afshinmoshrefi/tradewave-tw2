"""Bridge to the existing TradeWave appserver (the data engine).

Logs in once as a service account via POST /login/api with an X-Service-Key header,
caches the session token, then calls the data endpoints. Maps internal responses to the public v1 contract
and DROPS any raw price fields (seasonal-patterns-only / EOD posture).

The gateway agent extends the mapped accessors below. Internal endpoint paths/params and
exact response keys must be confirmed against appserver/appserver/appserver.py
(marked x-verify) - e.g. OppList4, ChartData4, MLScoreBatch, getResourcesObj.
"""
import concurrent.futures
import datetime
import json
import logging
import os
import re
import threading
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from . import settings
from .gateway_redis import create_client

log = logging.getLogger("apiserver.appserver_client")

# One bounded pool per gateway worker process. The Session carries no cookies or
# mutable auth state; every request supplies explicit headers/params.
_http = requests.Session()
_http.mount("http://", HTTPAdapter(pool_connections=32, pool_maxsize=64, pool_block=True))
_http.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=64, pool_block=True))

# Timeouts sit just under gunicorn's 120s worker timeout so a slow appserver surfaces as a
# clean RequestException (degraded card / structured 503) instead of a killed worker.
GET_TIMEOUT = 110
POST_TIMEOUT = 110

# 429 retry policy: the appserver rate limiter throttles the SHARED service identity, so a
# 429 is transient pressure on the shared bucket - retryable - and is NEVER a data gap.
_RETRY_ATTEMPTS = 3            # 1 try + up to 2 retries
_RETRY_BACKOFF = (1.0, 3.0)    # fallback sleeps when no usable Retry-After header
_RETRY_MAX_SLEEP = 10.0        # bound any Retry-After so a fan-out can't stall the worker
_STORM_SECONDS = 30.0
# Storm breaker: once a call exhausts its 429 retries, suppress retry sleeps for
# _STORM_SECONDS so a multi-row fan-out (scan receipts) fails fast + degrades honestly
# instead of stacking sleeps past the gunicorn timeout. Any healthy response resets it.
_rl_state = {"until": 0.0}


def storm_breaker_active():
    """Read-only health signal used by the load-test release gate."""
    return time.time() < _rl_state["until"]

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+\.?[A-Za-z0-9_=-]*")
_SECRET_QUERY_RE = re.compile(
    r"(?i)(?P<name>(?:access_|refresh_)?token|api_?key|key)=(?P<value>[^&\s'\"]+)"
)
_LEGACY_LOGIN_RE = re.compile(r"(?i)(/login/api/)[^/?#\s'\"]+")


def _scrub(text):
    """Strip credential material from any string headed for a log line or exception
    message: the service JWT travels as ?token=..., the service api key sits in the
    /login path, and requests embeds the full URL in its exception text. Prefixes only,
    never a full token."""
    s = str(text)
    s = _SECRET_QUERY_RE.sub(lambda m: "%s=***" % m.group("name"), s)
    s = _LEGACY_LOGIN_RE.sub(r"\1***", s)
    s = _JWT_RE.sub("eyJ***", s)
    key = settings.SERVICE_API_KEY
    if key:
        s = s.replace(str(key), "***")
    return s


def _retry_sleep_seconds(resp, attempt):
    """Honor a numeric Retry-After when present, else a small backoff - always bounded."""
    try:
        wait = float((resp.headers or {}).get("Retry-After"))
    except (TypeError, ValueError):
        wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
    return max(0.5, min(wait, _RETRY_MAX_SLEEP))


def _request(method, url, **kwargs):
    """One appserver HTTP call with bounded 429 retries and credential-scrubbed errors.

    A 429 is retried (Retry-After-aware, bounded) because it is shared-bucket rate-limit
    pressure, DISTINCT from a data gap; every other error stays fail-fast. When retries
    are exhausted the storm breaker makes subsequent calls single-attempt for a short
    window so bulk fan-outs degrade fast instead of sleeping past the worker timeout.
    Every raised RequestException has token/key material scrubbed from its message."""
    attempts = 1 if time.time() < _rl_state["until"] else _RETRY_ATTEMPTS
    try:
        for attempt in range(attempts):
            r = _http.request(method, url, **kwargs)
            if r.status_code == 429 and attempt < attempts - 1:
                wait = _retry_sleep_seconds(r, attempt)
                log.warning("appserver 429 (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1, attempts, wait, _scrub(url))
                time.sleep(wait)
                continue
            if r.status_code == 429:
                _rl_state["until"] = time.time() + _STORM_SECONDS
            else:
                _rl_state["until"] = 0.0
            r.raise_for_status()
            return r.json()
    except requests.RequestException as e:
        try:
            # Do not retain the original request/response objects: their prepared
            # URL can still hold the service JWT even when the displayed message is
            # clean, and error reporters may serialize exception attributes.
            scrubbed = type(e)(_scrub(e))
        except TypeError:
            # Exotic subclass init (e.g. JSONDecodeError): preserve the catchable
            # requests base type without retaining credential-bearing attributes.
            scrubbed = requests.RequestException(_scrub(e))
        raise scrubbed from None


def _seg(value):
    """URL-encode a single value so it can NEVER act as a path separator or traversal in an
    internal appserver path. A request param like '10/../../whoami' becomes one literal,
    percent-encoded segment (%2F...) instead of injecting extra path segments riding the
    service token. Apply to EVERY interpolated value in an internal path f-string."""
    return quote(str(value), safe="")
_token = {"value": None, "exp": 0.0}
_lock = threading.Lock()


def _get_token():
    with _lock:
        if _token["value"] and _token["exp"] > time.time() + 60:
            return _token["value"]
        url = f"{settings.APPSERVER_URL}/login/api"
        data = _request(
            "POST",
            url,
            headers={"X-Service-Key": settings.SERVICE_API_KEY or ""},
            timeout=10,
        )
        tok = data.get("token") or data.get("session_token")  # x-verify exact key
        if not tok:
            raise RuntimeError("appserver /login/api returned no token")
        _token.update(value=tok, exp=time.time() + 20 * 3600)
        return tok


def get(path, params=None):
    params = dict(params or {})
    params["token"] = _get_token()
    return _request("GET", f"{settings.APPSERVER_URL}{path}", params=params,
                    timeout=GET_TIMEOUT)


def post(path, json_body, params=None):
    params = dict(params or {})
    params["token"] = _get_token()
    return _request("POST", f"{settings.APPSERVER_URL}{path}", params=params,
                    json=json_body, timeout=POST_TIMEOUT)


# ---------------------------------------------------------------------------
# Shape helpers - map the appserver's internal shapes to the v1 contract and
# DROP every raw price field on the way out (seasonal-patterns-only / EOD posture).
# ---------------------------------------------------------------------------

# OppList4 / OppBySymbol return a list of lists in this fixed column order
# (see appserver.py: opp[['date','symbol','daysOut','lOrS','sharpe_ratio',
#  'avg_profit','median_profit','avg_profit2','sharpe_ratio2']]).
_OPP_COLS = ("date", "symbol", "daysOut", "lOrS", "sharpe_ratio",
             "avg_profit", "median_profit", "avg_profit2", "sharpe_ratio2")

# Publishable subset of the ChartData4 stats block: percentage / seasonal stats
# ONLY. Everything that reveals a price or volume LEVEL (52W High/Low, SMA 50/200,
# Avg Volume 20d) or is unrelated trade metadata (last_trade_date, earnings_*) is
# dropped. Keyed internal-stat-name -> public field name.
_PUBLIC_STAT_FIELDS = {
    "Trade Dir": "trade_direction",
    "Num Winners": "num_winners",
    "Num Losers": "num_losers",
    "Percent Profitable": "percent_profitable",
    "Avg Profit - All": "avg_profit_all",
    "Avg Profit": "avg_profit",
    "Avg Loss": "avg_loss",
    "Median Profit": "median_profit",
    "Annualized Return": "annualized_return",
    "Cumulative Return": "cumulative_return",
    "Std Dev": "std_dev",
    "Sharpe Ratio": "sharpe_ratio",
    "Sharpe Ratio2": "sharpe_ratio_mfe",
    "1M Return": "return_1m",
    "Trend Long": "trend_long",
    "Trend Short": "trend_short",
    "Trend Long1": "trend_long_prev",
    "Trend Short1": "trend_short_prev",
}


def _dir_to_public(lor_s):
    """Map the appserver direction labels to the contract enum (long|short).
    OppList4/OppBySymbol return 'Long'/'Short'; ChartData4 stats return 'long'/'short'.
    """
    s = str(lor_s).strip().lower()
    if s in ("l", "long"):
        return "long"
    if s in ("s", "short"):
        return "short"
    return s


def _dir_to_internal(direction):
    """Map the contract enum (long|short) to the appserver's raw l/s code."""
    d = str(direction).strip().lower()
    if d in ("long", "l"):
        return "l"
    if d in ("short", "s"):
        return "s"
    return d


def _num(v):
    """Coerce a numeric-ish value (str or number) to float, else None. years/labels
    are handled separately and stay strings - this is only for numeric columns."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _engine_days_to_display(value):
    """Convert the legacy engine offset to TradeWave's inclusive calendar-day label."""
    if value is None or str(value).strip() in ("", "None"):
        return None
    return int(value) + 1


def _display_days_to_engine(value):
    """Convert public inclusive calendar days to the engine's elapsed-day offset.

    TradeWave counts the entry date as calendar day 1.  ChartData4 and the original
    opportunity/ML datasets use ``daysOut = displayed_days - 1`` internally.
    """
    days = int(value)
    if days < 1:
        raise ValueError("days_out must be at least 1")
    return days - 1


def _pct_str_to_fraction(v):
    """Map a ChartData4 percentage-stat string ('60%') to a 0..1 fraction (0.6).

    The appserver stores 'Percent Profitable' as a rounded percent STRING with a
    trailing '%'. Plain numbers are accepted too. Returns None if not parseable."""
    if v is None or v == "":
        return None
    s = str(v).strip().rstrip("%").strip()
    f = _num(s)
    if f is None:
        return None
    return round(f / 100.0, 4)


def _win_rate_from_stats(stats):
    """The REAL historical win rate = ChartData4 'Percent Profitable' as a 0..1
    fraction: the share of years the seasonal window finished profitable (any
    positive year counts; NO profit threshold - this is exactly what the UI shows,
    and it is direction-aware in the appserver). This is NOT the ML win_prob."""
    if not isinstance(stats, dict):
        return None
    return _pct_str_to_fraction(stats.get("Percent Profitable"))


def _publishable_stats(stats):
    """Project the ChartData4 stats dict onto the publishable (percent-only) subset."""
    if not isinstance(stats, dict):
        return {}
    out = {}
    for internal_name, public_name in _PUBLIC_STAT_FIELDS.items():
        if internal_name in stats:
            out[public_name] = stats[internal_name]
    return out


def _opp_row_to_obj(row, market, years, win_rate=None):
    """Map one OppList4/OppBySymbol row (list) to a contract Opportunity dict.
    Drops nothing price-bearing (the row has no price columns).

    win_rate is the REAL historical win rate (ChartData4 'Percent Profitable', 0..1).
    The OppList4/OppBySymbol feed carries no per-row win rate, so the caller sources
    it per symbol via ChartData4 and passes it in; it is None when not enriched. It is
    distinct from ml.win_prob (the ML predicted probability)."""
    rec = dict(zip(_OPP_COLS, row))
    return {
        "symbol": rec.get("symbol"),
        "market": str(market),
        "direction": _dir_to_public(rec.get("lOrS")),
        "entry_date": rec.get("date"),
        "days_out": _engine_days_to_display(rec.get("daysOut")),
        "sharpe_ratio": _num(rec.get("sharpe_ratio")),
        "avg_profit_pct": _num(rec.get("avg_profit")),
        "median_profit_pct": _num(rec.get("median_profit")),
        "win_rate": win_rate,
        "years": str(years),  # lookback label stays a string (we control it as input)
        "ml": None,           # filled by the gateway when tier, quota, and market checks allow
    }


# --------------------------------- markets ---------------------------------

def list_markets():
    """Maps getResourcesObj -> [{id, name}]. id is the permanent resource key."""
    data = get("/getResourcesObj")
    resources = data.get("resources", {}) if isinstance(data, dict) else {}
    out = []
    for rid, name in resources.items():
        out.append({"id": str(rid), "name": name})
    return out


_resource_map = {"value": None, "exp": 0.0}
_resource_lock = threading.Lock()


def market_name_map():
    """Cached {id: name} for the markets (getResourcesObj). 6h TTL - the catalog is static.
    Used to stamp market.name on cards without re-fetching per row."""
    with _resource_lock:
        if _resource_map["value"] is not None and _resource_map["exp"] > time.time():
            return _resource_map["value"]
    m = {str(x["id"]): x["name"] for x in list_markets()}
    with _resource_lock:
        _resource_map.update(value=m, exp=time.time() + 6 * 3600)
    return m


def resolve_market_for_symbol(symbol, candidate_markets):
    """Find which of candidate_markets lists `symbol`. Returns the single market id if it
    appears in exactly one, a list of ids if several, or [] if none. Used by /v1/analyze to
    resolve an omitted market. Parallelized over the candidate markets."""
    sym = str(symbol).strip().upper()
    found = []

    def _has(m):
        try:
            syms = {str(s["symbol"]).upper() for s in list_symbols(m)}
            return m if sym in syms else None
        except Exception as e:  # noqa: BLE001
            log.warning("resolve_market_for_symbol: market %s lookup failed: %s", m, e)
            return None

    if not candidate_markets:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(candidate_markets))) as ex:
        for r in ex.map(_has, candidate_markets):
            if r is not None:
                found.append(r)
    return found


def list_symbols(market):
    """Maps GetListSymbols -> [{symbol, name}]. Internal returns
    {'AllowedSymbols': {symbol: name}}."""
    data = get(f"/GetListSymbols/{_seg(market)}")
    allowed = data.get("AllowedSymbols", {}) if isinstance(data, dict) else {}
    if not isinstance(allowed, dict):
        return []
    return [{"symbol": str(sym), "name": name} for sym, name in allowed.items()]


# ------------------------------ opportunities ------------------------------

# Per-row historical-win-rate enrichment hits ChartData4 once per opportunity, so it
# is bounded for the bulk list. ChartData4 is cached on the appserver, so re-runs are
# cheap, but a cold large list could fan out a lot of work; cap how many rows we enrich.
MAX_WIN_RATE_ENRICH = 50

# Gateway-side cache of the per-symbol historical win rate (ChartData4 'Percent
# Profitable'). A warm /opportunities request reads win_rate from here instead of
# re-fanning-out ChartData4 calls. The stat only moves on the daily data refresh, so a
# few-hour TTL is safe. Redis db4 (settings.REDIS_DB) - the gateway's own db, never the
# appserver's db0/2/3.
import redis as _redis_mod  # noqa: E402

_win_rate_cache = create_client()
_WIN_RATE_TTL = 6 * 3600
_WIN_RATE_NONE = "null"  # sentinel: computed, but no win rate available

# Gateway-side curve cache. The appserver already caches the computation, but without
# this layer every API response still spends an HTTP round trip and an appserver thread
# on each returned card. Values are price-safe [{date,index}] data only.
_curve_cache = create_client()
_CURVE_TTL = 6 * 3600


def _win_rate_for_opp(obj):
    """Source one opportunity's REAL historical win rate (0..1) from ChartData4's
    'Percent Profitable'. Returns None when the entry date / days_out is missing or
    the appserver has no stats for it. Relies on the appserver's ChartData4 cache.

    A per-row ChartData4 call can fail (a single symbol's data gap, or a transient
    appserver error under a cold-cache burst). Because this enriches a whole LIST, one
    such failure must not abort the list: we degrade that single row to win_rate=None
    (which min_win_rate then correctly excludes) and log it. This is a narrow,
    per-symbol soft-fail on the downstream fetch only - not a blanket swallow of gateway
    logic errors."""
    entry_date = obj.get("entry_date")
    days_out = obj.get("days_out")
    if not entry_date or days_out is None:
        return None
    cache_key = (f"gw:winrate:{obj.get('market')}:{obj.get('symbol')}:"
                 f"{entry_date}:{days_out}:{obj.get('years')}")
    try:
        cached = _win_rate_cache.get(cache_key)
    except _redis_mod.RedisError:
        cached = None  # redis down -> fall through to ChartData4 (pre-cache behavior)
    if cached is not None:
        val = cached.decode() if isinstance(cached, (bytes, bytearray)) else cached
        return None if val == _WIN_RATE_NONE else float(val)
    try:
        _chart, stats = _chart_data(obj["market"], obj["symbol"], entry_date, days_out, obj["years"])
    except requests.RequestException as e:
        log.warning("win_rate enrich skipped for %s/%s (days_out=%s): %s",
                    obj.get("market"), obj.get("symbol"), days_out, e)
        return None  # transient downstream failure - do not cache
    wr = _win_rate_from_stats(stats)
    try:
        _win_rate_cache.setex(cache_key, _WIN_RATE_TTL,
                              _WIN_RATE_NONE if wr is None else str(wr))
    except _redis_mod.RedisError:
        pass  # cache write best-effort; the computed result is already correct
    return wr


def opportunities(market, entry_date, year1="10", year2="9", day_range="-",
                  opp_list_expanded="0", direction=None, enrich_win_rate=0, mode="consecutive"):
    """Ranked seasonal opportunities for a market on an entry date, via OppList4.

    OppList4 is keyed to a single entry date (month name + day), not a from/to range,
    so the gateway passes `from` (or today) as the entry date. year1/year2 are the
    lookback / min-profitable-years window (year1 is echoed back as the Opportunity
    'years' string). The 'prices', 'ml_enabled', 'OppActiveList', 'AvailableFilters'
    keys from OppList4 are intentionally not surfaced.

    enrich_win_rate caps how many of the (post-direction-filter) rows get their REAL
    historical win_rate sourced per symbol from ChartData4 ('Percent Profitable'); 0
    means no enrichment. Rows past the cap keep win_rate=None. The OppList4 feed carries
    no win rate of its own, so this is the only honest source for min_win_rate filtering.
    """
    dt = datetime.datetime.strptime(entry_date, "%Y-%m-%d")
    month_name = dt.strftime("%B")
    day_num = str(dt.day)
    path = (f"/OppList4/{_seg(market)}/{_seg(month_name)}/{_seg(day_num)}/{_seg(year1)}"
            f"/{_seg(year2)}/{_seg(day_range)}/{_seg(opp_list_expanded)}/0")
    # mode='pe' loads the presidential-election-cycle dataset (the current cycle position);
    # 'consecutive' (default) is the standard consecutive-years dataset.
    params = {"mode": mode} if mode and mode != "consecutive" else None
    data = get(path, params=params)
    rows = data.get("OppList", []) if isinstance(data, dict) else []
    # appserver sentinel: OppList can be a string like '-1:<path>' when the opp file
    # is missing. Treat any non-list as "no opportunities" (fail-soft on data gaps,
    # not on errors).
    if not isinstance(rows, list):
        return []
    out = []
    want_dir = _dir_to_public(direction) if direction else None
    for row in rows:
        if not isinstance(row, list) or len(row) < len(_OPP_COLS):
            continue
        obj = _opp_row_to_obj(row, market, year1)
        if want_dir and obj["direction"] != want_dir:
            continue
        out.append(obj)
    enrich_n = min(int(enrich_win_rate), MAX_WIN_RATE_ENRICH)
    for obj in out[:enrich_n]:
        obj["win_rate"] = _win_rate_for_opp(obj)
    return out


def opportunities_by_symbol(market, symbol, year1="10", year2="9", day_range="-",
                            top_pct=10, enrich_win_rate=True, mode="consecutive"):
    """Seasonal opportunities for one symbol, via OppBySymbol - the symbol's seasonal
    patterns across the year, sorted by Sharpe (the wave-viewer pattern dropdown data).
    Same row shape as OppList4. By default every row's REAL historical win_rate is sourced
    from ChartData4 ('Percent Profitable'). mode='pe' uses the presidential-cycle dataset."""
    path = (f"/OppBySymbol/{_seg(market)}/{_seg(symbol)}/{_seg(year1)}/{_seg(year2)}"
            f"/{_seg(day_range)}/{int(top_pct)}")
    params = {"mode": mode} if mode and mode != "consecutive" else None
    data = get(path, params=params)
    rows = data.get("OppBySymbol", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) < len(_OPP_COLS):
            continue
        out.append(_opp_row_to_obj(row, market, year1))
    if enrich_win_rate:
        for obj in out:
            obj["win_rate"] = _win_rate_for_opp(obj)
    return out


def opportunities_multi(markets, entry_date, year1="10", year2="9", direction=None,
                        max_workers=8, mode="consecutive", return_failures=False):
    """Fan out opportunities() over several markets IN PARALLEL (independent cached GETs)
    and return a flat list of Opportunity dicts (NO win_rate enrichment here - the caller
    enriches AFTER ranking/slicing so we never fan out 50xN ChartData4 calls).

    A single market's failure degrades to [] for that market (logged) - it must not abort
    the whole scan (fail-soft on a per-market data gap)."""
    results = []
    failures = []

    def _one(m):
        try:
            return appserver_opportunities_safe(m, entry_date, year1, year2, direction, mode), None
        except Exception as e:  # noqa: BLE001 - per-market isolation for the scan
            log.warning("scan: market %s failed, skipped: %s", m, e)
            return [], str(m)

    if not markets:
        return (results, failures) if return_failures else results
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(markets))) as ex:
        for rows, failed_market in ex.map(_one, markets):
            results.extend(rows)
            if failed_market is not None:
                failures.append(failed_market)
    return (results, failures) if return_failures else results


def appserver_opportunities_safe(market, entry_date, year1, year2, direction, mode="consecutive"):
    """opportunities() with no enrichment, isolated for the parallel scan."""
    return opportunities(market, entry_date, year1=year1, year2=year2,
                         direction=direction, enrich_win_rate=0, mode=mode)


# --------------------------- patterns / chart data -------------------------

def _chart_data(market, symbol, entry_date, days_out, years):
    """Raw ChartData4 fetch from a public/display window.

    ``days_out`` is the inclusive calendar-day count exposed by the gateway.  Convert it
    once at this boundary to ChartData4's legacy elapsed-day offset.  ``years`` stays a
    string because it may be a consecutive lookback or a PE-cycle slice.
    """
    engine_days_out = _display_days_to_engine(days_out)
    path = (f"/ChartData4/{_seg(market)}/{_seg(entry_date)}/{_seg(symbol)}"
            f"/{_seg(engine_days_out)}/{_seg(years)}")
    data = get(path)
    if not isinstance(data, dict):
        return [], {}
    chart = data.get("ChartData4", [])
    stats = data.get("stats", {})
    # ChartData4 can return a status string ('Not Enough Data') instead of a list.
    if not isinstance(chart, list):
        chart = []
    if not isinstance(stats, dict):
        stats = {}
    return chart, stats


def pattern_stats(market, symbol, entry_date, days_out="30", years="10"):
    """Maps ChartData4 -> the publishable aggregate-stats subset (no price series,
    no price/volume levels). Used by /patterns. win_rate is the REAL historical win
    rate (share of profitable years, 0..1) - the same 'Percent Profitable' the UI
    shows, also exposed inside stats as percent_profitable."""
    _chart, stats = _chart_data(market, symbol, entry_date, days_out, years)
    return {
        "symbol": str(symbol),
        "market": str(market),
        "win_rate": _win_rate_from_stats(stats),
        "stats": _publishable_stats(stats),
    }


def chart_stats_and_years(market, symbol, entry_date, days_out, years):
    """Return (stats, chart_entries) for ONE setup: the ChartData4 stats dict PLUS the raw
    per-year entries [{year, pct, price}]. cards.py consumes the per-year entries (parsing
    the NET pct only and DROPPING price) to build the per_year receipts. This is the single
    accessor the flagship endpoints use to source receipts for a card.

    Two DISTINCT degraded outcomes (never conflated):
      - a genuine per-symbol DATA GAP ('Not Enough Data' etc.) comes back from the
        appserver as a 200 and maps to ({}, []) inside _chart_data - real absence;
      - a FAILED fetch (429 after retries / timeout / upstream error) returns (None, None)
        so the caller stamps the card receipts_unavailable instead of rendering a
        confident no-edge from missing data. Either way a multi-row scan never aborts."""
    try:
        chart, stats = _chart_data(market, symbol, entry_date, days_out, years)
    except requests.RequestException as e:
        log.warning("chart_stats_and_years FETCH FAILED for %s/%s (days_out=%s): %s",
                    market, symbol, days_out, e)
        return None, None
    return stats, chart


def _seasonal_curve(market, symbol, chart_start_date, years, opp_start_date=None):
    """Raw consolidated_seasonal_chart2 ('trendchart') fetch -> the normalized averaged
    seasonal curve. The appserver returns {'cons_seas_chart': [[date, mean], ...]} where
    `mean` is, per day-of-year, the mean across `years` of 100*(close-low)/(high-low)
    for that year - i.e. a 0-100 RELATIVE seasonal index (the smooth seasonal line),
    averaged across years. There is NO price/close in the payload, and prices cannot be
    reconstructed (the per-year high/low are not exposed and it is averaged), so it is
    price-safe. Returns a list of {date, index}. years/opp_start stay strings."""
    opp_start = opp_start_date or chart_start_date
    cache_key = (f"gw:curve:v1:{market}:{symbol}:{years}:"
                 f"{chart_start_date}:{opp_start}")
    try:
        cached = _curve_cache.get(cache_key)
    except _redis_mod.RedisError:
        cached = None
    if cached is not None:
        try:
            if isinstance(cached, (bytes, bytearray)):
                cached = cached.decode("utf-8")
            value = json.loads(cached)
            if isinstance(value, list):
                return value
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    path = (f"/consolidated_seasonal_chart2/{_seg(market)}/{_seg(symbol)}/{_seg(years)}"
            f"/{_seg(chart_start_date)}/{_seg(opp_start)}")
    data = get(path)
    rows = data.get("cons_seas_chart", []) if isinstance(data, dict) else []
    # appserver returns [] on a data gap (not enough years / symbol not traded).
    if not isinstance(rows, list):
        return []
    curve = []
    for row in rows:
        # each row is [date, normalized_mean]; ignore any malformed row.
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        idx = _num(row[1])
        if idx is None:
            continue
        curve.append({"date": str(row[0]), "index": idx})
    try:
        _curve_cache.setex(cache_key, _CURVE_TTL, json.dumps(curve, separators=(",", ":")))
    except _redis_mod.RedisError:
        pass
    return curve


def seasonal_chart(market, symbol, entry_date, days_out, years, direction=None):
    """The seasonal 'trendchart' as DATA: the normalized, year-averaged 0-100 seasonal
    curve from the appserver's consolidated_seasonal_chart2.

    Returns the smooth daily seasonal line (`seasonal_curve`: one {date, index} point
    per day across the ~365-day window starting at entry_date), plus the publishable
    percentage stats and the REAL historical win_rate from ChartData4. `index` is a
    0-100 RELATIVE seasonal index (high/low-normalized, averaged across years), never a
    price or a percent return. No raw price field is read or returned. years stays a
    string. days_out has no effect on the curve (the curve is a full annual cycle); it
    is accepted for parity with the other endpoints and echoed back.
    """
    try:
        days_out_i = int(days_out)
    except (TypeError, ValueError):
        days_out_i = None

    seasonal_curve = _seasonal_curve(market, symbol, entry_date, years)
    # ChartData4 gives the percentage stats + the historical win rate (Percent
    # Profitable). Both are cached on the appserver. Price/volume levels are dropped
    # by _publishable_stats; the price series is never requested.
    _chart, stats = _chart_data(market, symbol, entry_date, days_out, years)

    out = {
        "symbol": str(symbol),
        "market": str(market),
        "entry_date": entry_date,
        "days_out": days_out_i,
        "years": str(years),
        "win_rate": _win_rate_from_stats(stats),
        "seasonal_curve": seasonal_curve,
        "stats": _publishable_stats(stats),
    }
    if direction:
        out["direction"] = _dir_to_public(direction)
    elif isinstance(stats, dict) and stats.get("Trade Dir"):
        out["direction"] = _dir_to_public(stats.get("Trade Dir"))
    # one-call curve + bars: attach the per-year bars (each year's trade return with its
    # favorable/adverse excursion band, direction-aware) from the ChartData4 entries we
    # already fetched, so a chart can be drawn without a second round-trip. Percentages only.
    from . import cards as _cards  # local import: cards is dependency-free, no import cycle
    out["per_year_bars"] = _cards.per_year_bars(_chart, out.get("direction") or "long")
    return out


# --------------------------------- scoring ---------------------------------

def ml_scores(market, items):
    """Tier-metered ML scores via MLScoreBatch + MLScorePending. The gateway gates and
    meters access (Free 5/day, Dev 100/day, Pro/Business unlimited);
    the service account itself always has appserver ML access (level 6).

    MLScoreBatch returns cached scores + a pending list; MLScorePending scores the
    pending items via the keyprovider (chunked at 5). We poll MLScorePending until the
    pending list drains or we hit a bounded number of rounds.

    `items` is a list of {symbol, date, days_out, direction(long|short)}.
    Returns a list of contract MLScore dicts aligned 1:1 with `items` (None where the
    appserver could not score, e.g. days_out out of the 10-90 range).
    """
    # Build the appserver request body (internal uses elapsed daysOut + raw l/s direction).
    norm = []
    for it in items:
        norm.append({
            "symbol": it["symbol"],
            "date": it["date"],
            "daysOut": _display_days_to_engine(it["days_out"]),
            "direction": _dir_to_internal(it["direction"]),
        })

    scores = {}  # ui_key 'SYMBOL|daysOut|dir' -> {ml_score, win_prob, pred_return, pred_mfe}

    batch = post(f"/MLScoreBatch/{_seg(market)}", {"opportunities": norm})
    scores.update(batch.get("scores", {}) or {})
    pending = batch.get("pending", []) or []

    rounds = 0
    # Each round scores up to 5 pending items; bound rounds generously by the input
    # size so large batches still resolve but a stuck scorer can never loop forever.
    max_rounds = max(2, (len(norm) // 5) + 2)
    while pending and rounds < max_rounds:
        rounds += 1
        resp = post(f"/MLScorePending/{_seg(market)}", {"pending": pending})
        scores.update(resp.get("scores", {}) or {})
        new_pending = resp.get("still_pending", []) or []
        if len(new_pending) >= len(pending):
            # no forward progress (scorer error path re-queues) - stop, don't spin
            break
        pending = new_pending

    out = []
    for it in norm:
        ui_key = f"{it['symbol']}|{it['daysOut']}|{it['direction']}"
        s = scores.get(ui_key)
        if not s:
            out.append(None)
            continue
        out.append({
            "ml_score": s.get("ml_score"),
            "win_prob": s.get("win_prob"),
            "pred_return": s.get("pred_return"),
            "pred_mfe": s.get("pred_mfe"),
        })
    return out


# ------------------------------- daily pick --------------------------------
# The daily AI pick lives in featured_history.json (written by the site's
# generate_home_page / generate_scorecard pipeline on this same box). The
# appserver has no daily-pick HTTP route, so we read the record directly. Raw
# price fields (start_price/current_price/peak_price/end_price) are NEVER surfaced;
# returns are already stored as percentages (current_return/peak_return/actual_return).

FEATURED_HISTORY_FILE = settings.FEATURED_HISTORY_FILE


class FeaturedHistoryUnavailable(RuntimeError):
    """The canonical daily-pick feed is missing, malformed, or unreachable."""


def _load_featured_history():
    """Load the canonical chronological pick history.

    A configured remote URL is authoritative, including when a stale local file is
    present on a split app/web deployment.  A co-located dev install with no remote
    URL reads the file. A missing source is an honest 503, never a successful response
    containing ``card: null``.
    """
    if settings.FEATURED_HISTORY_URL:
        try:
            data = _request(
                "GET",
                settings.FEATURED_HISTORY_URL,
                headers={"X-Service-Key": settings.SERVICE_API_KEY or ""},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise FeaturedHistoryUnavailable("daily-pick feed unavailable") from exc
    elif FEATURED_HISTORY_FILE and os.path.exists(FEATURED_HISTORY_FILE):
        try:
            with open(FEATURED_HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise FeaturedHistoryUnavailable("daily-pick file unreadable") from exc
    else:
        raise FeaturedHistoryUnavailable("daily-pick source not configured")
    if not isinstance(data, list):
        raise FeaturedHistoryUnavailable("daily-pick feed has invalid shape")
    return data


def _realized_return_pct(entry):
    """Direction-aware realized/at-risk return % for a pick, mirroring the site's
    tracker: closed -> actual_return; open -> current_return. Already a percentage."""
    if entry.get("status") == "closed":
        if entry.get("actual_return") is not None:
            return entry["actual_return"]
        # fall back to current_return for closed picks the tracker hasn't finalized
        return entry.get("current_return")
    return entry.get("current_return")


def _pick_result(entry):
    """Map a pick to the contract result enum: win|loss|open.

    Mirrors generate_scorecard.compute_stats: an OPEN pick whose peak (MFE) already
    reached the predicted return counts as a win; otherwise open picks are 'open'.
    Closed picks use the tracker's 'win' boolean, else the sign of the realized return.
    """
    status = entry.get("status")
    if status == "closed":
        if entry.get("win") is not None:
            return "win" if entry["win"] else "loss"
        rr = _realized_return_pct(entry)
        if rr is None:
            return "open"
        return "win" if rr > 0 else "loss"
    # open
    peak = entry.get("peak_return")
    pred = entry.get("pred_return")
    if peak is not None and pred is not None and pred > 0 and peak >= pred:
        return "win"
    return "open"


def daily_pick():
    """The most recent featured pick -> contract DailyPick. Returns {} when there is
    no history. Raw prices are dropped; ML fields come straight from the stored record."""
    history = _load_featured_history()
    if not history:
        return {}
    e = history[-1]
    days = _engine_days_to_display(e.get("daysOut"))
    yrs = e.get("years")
    summary = (
        "%s %s seasonal setup over a %s-day hold, %s-year lookback."
        % (
            e.get("symbol", ""),
            _dir_to_public(e.get("direction", "")),
            days,
            yrs,
        )
    )
    return {
        "symbol": e.get("symbol"),
        "featured_date": e.get("featured_date"),
        "direction": _dir_to_public(e.get("direction", "")),
        "days_out": days,
        "pattern_summary": summary,
        "ml": {
            "ml_score": e.get("ml_score"),
            "win_prob": e.get("win_prob"),
            "pred_return": e.get("pred_return"),
            "pred_mfe": e.get("pred_mfe"),
        },
    }


def daily_pick_raw():
    """The most recent featured pick as a normalized Opportunity-shaped dict PLUS its stored
    ML, so the gateway can build a full PatternCard. Returns None when there is no history.
    Raw price fields (start_price/current_price/peak_price/end_price) are NEVER surfaced."""
    history = _load_featured_history()
    if not history:
        return None
    e = history[-1]
    days = _engine_days_to_display(e.get("daysOut"))
    market = str(e.get("resource_id")) if e.get("resource_id") is not None else None
    opp = {
        "symbol": e.get("symbol"),
        "market": market,
        "direction": _dir_to_public(e.get("direction", "")),
        "entry_date": e.get("date"),
        "days_out": days,
        "sharpe_ratio": _num(e.get("sharpe_ratio")),
        "avg_profit_pct": _num(e.get("avg_profit")),
        "median_profit_pct": _num(e.get("median_profit")),
        "win_rate": None,                 # sourced from ChartData4 at card build
        "years": str(e.get("years") or "10"),
        "ml": {
            "ml_score": e.get("ml_score"),
            "win_prob": e.get("win_prob"),
            "pred_return": e.get("pred_return"),
            "pred_mfe": e.get("pred_mfe"),
        },
    }
    return {"opp": opp, "featured_date": e.get("featured_date")}


def track_record():
    """Historical realized win/loss record of past daily picks -> contract TrackRecord.

    win_rate is wins / resolved (closed picks + open picks that already hit target),
    expressed 0..1 to match the contract (the site computes the same set as a 0..100
    %). avg_return_pct is the mean realized return over resolved picks. Raw prices are
    never surfaced; only the percentage returns are.
    """
    history = _load_featured_history()
    picks = []
    resolved_returns = []
    win_count = 0
    for e in history:
        result = _pick_result(e)
        rr = _realized_return_pct(e)
        picks.append({
            "symbol": e.get("symbol"),
            "featured_date": e.get("featured_date"),
            "return_pct": rr,
            "result": result,
        })
        if result in ("win", "loss"):
            win_count += 1 if result == "win" else 0
            if rr is not None:
                resolved_returns.append(rr)
    resolved_count = sum(1 for p in picks if p["result"] in ("win", "loss"))
    win_rate = round(win_count / resolved_count, 4) if resolved_count else 0.0
    avg_return = round(sum(resolved_returns) / len(resolved_returns), 2) if resolved_returns else 0.0
    return {
        "summary": {
            "count": len(picks),
            "win_count": win_count,
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
        },
        "picks": picks,
    }
