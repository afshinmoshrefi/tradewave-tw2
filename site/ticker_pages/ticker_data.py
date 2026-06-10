"""
Per-ticker data collection for TradeWave Programmatic SEO ticker pages.

One public entry point: collect_ticker_data(symbol, session, realtime_prices).
Gathers everything needed to render a single /patterns/{SYMBOL}.html page,
tolerating upstream failures. Fields that can't be filled come back as None
rather than raising.

Helpers for the caller:
    - login_appserver()           -> requests.Session with ?token= attached
    - fetch_realtime_prices()     -> {SYMBOL: [price, change_pct]}

All URLs, paths, and API keys come from /home/flask/config.py. No env vars.
No local config.py (would shadow the central config).
"""

import base64
import csv
import datetime
import json
import os
import sys

import pandas as pd
import requests

# Central config.
sys.path.insert(0, '/home/flask')
import config

from compute_monthly_seasonality import (
    compute_monthly_seasonality,
    compute_election_cycle,
    compute_monthly_by_cycle_phase,
    compute_forward_window,
)

APPSERVER_URL = config.appserver_url  # TW2: from secrets.env (TW2_APPSERVER_URL)
ML_SCORER_URL = config.ml_scorer_url
EDGAR_SERVICE_URL = config.edgar_service_url
REALTIME_URL = config.realtime_service_url
STOCKSCORE_URL = config.stockscore_url

# TW2 wave-viewer deep link: the React app lives at /app/ (relative so the
# link works on dev/staging/prod alike). The TW1 WordPress /wave-viewer page
# does not exist on TW2.
WAVE_VIEWER_BASE = '/app/?o='

# US equity resource IDs in descending specificity. When looking up a symbol
# for OppBySymbol/company name we try these in order and take the first hit.
US_RESOURCE_CSVS = [
    ('0', '/home/flask/data/dj30_symbols.csv'),
    ('1', '/home/flask/data/nasdaq100_symbols.csv'),
    ('2', '/home/flask/data/sp500_symbols.csv'),
    ('3', '/home/flask/data/rus1000_symbols.csv'),
    ('4', '/home/flask/data/wilshire5000_symbols.csv'),
    ('11', '/home/flask/data/ETF_symbols.csv'),
]

_symbol_index = None  # lazy: {SYMBOL: (resource_id, company_name)}


# ---------------------------------------------------------------------------
# Login + bulk realtime
# ---------------------------------------------------------------------------

def login_appserver():
    """Authenticate against the appserver and return a requests.Session with
    the token stashed on `session.token`.

    TW2: uses single-step service-account API key flow (config.SERVICE_API_KEY).
    Falls back to TW1 2-step keyprovider handshake if SERVICE_API_KEY not set.
    """
    s = requests.Session()

    # TW2 path
    if getattr(config, 'SERVICE_API_KEY', None):
        try:
            url = APPSERVER_URL + '/login/api/' + config.SERVICE_API_KEY
            resp = s.get(url, timeout=45).json()
            token = resp.get('token')
            if not token:
                print('login_appserver TW2 failed: %s' % resp.get('message', 'no token'))
            s.token = token
            return s
        except Exception as e:
            print('login_appserver TW2 exception: %s' % e)
            s.token = None
            return s

    # Legacy TW1 path
    try:
        url = APPSERVER_URL + '/login/2/3/4/5/6'
        kp_result = s.get(url, timeout=45).json()
        kp_token = kp_result['message'].split(' ')[4]
        url2 = APPSERVER_URL + '/login/28/3/4/5/' + kp_token
        result = s.get(url2, timeout=45).json()
        token = result.get('token')
        if not token:
            import time as _t
            _t.sleep(2)
            result = s.get(url2, timeout=15).json()
            token = result.get('token')
        s.token = token
        return s
    except Exception as e:
        print('login_appserver legacy failed: %s' % e)
        s.token = None
        return s


def fetch_realtime_prices():
    """Single bulk call to the realtime service. Returns {SYMBOL: [price, change_pct]}.
    Returns {} on failure."""
    try:
        url = REALTIME_URL.rstrip('/') + '/prices/all'
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        prices = data.get('prices', {}) if isinstance(data, dict) else {}
        trimmed = {}
        for sym, p in prices.items():
            if isinstance(p, dict):
                trimmed[sym] = [p.get('price'), p.get('change_p')]
        return trimmed
    except Exception as e:
        print('fetch_realtime_prices failed: %s' % e)
        return {}


# ---------------------------------------------------------------------------
# Symbol -> (resource_id, company_name) lookup
# ---------------------------------------------------------------------------

def _load_symbol_index():
    """Build {SYMBOL: (resource_id, company_name)} from the symbols CSVs.
    Most-specific group wins (DJ30 before SP500 before Russell, etc.)."""
    global _symbol_index
    if _symbol_index is not None:
        return _symbol_index

    idx = {}
    for rid, path in US_RESOURCE_CSVS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = (row.get('symbols') or '').strip().upper()
                    name = (row.get('name') or '').strip()
                    if not sym:
                        continue
                    # Keep the first (most specific) hit seen.
                    if sym not in idx:
                        idx[sym] = (rid, name)
        except Exception as e:
            print('symbol index load failed for %s: %s' % (path, e))
    _symbol_index = idx
    return _symbol_index


def _resolve_symbol(symbol):
    """Return (resource_id, company_name) for a symbol, or (None, None)."""
    idx = _load_symbol_index()
    return idx.get(symbol.upper(), (None, None))


def fetch_company_name(symbol):
    """Company name lookup. Reads from the symbols CSVs already on disk,
    which is the same source the appserver uses for its US-stock group
    resolution."""
    _, name = _resolve_symbol(symbol)
    return name or None


# ---------------------------------------------------------------------------
# OppBySymbol -> active patterns
# ---------------------------------------------------------------------------

def _convert_param_base64(resource_id, symbol, date1, days, years):
    """Local reimplementation of the wave-viewer param encoder:
       base64("resourceID|symbol|date|days|years"), '=' stripped."""
    raw = '%s|%s|%s|%s|%s' % (resource_id, symbol, date1, days, (years or '').upper())
    b = base64.b64encode(raw.encode('utf-8')).decode('ascii')
    return b.rstrip('=')


def _is_active(start_date_str, days_out, today):
    """A pattern is 'active' if today is between start and start+days_out."""
    try:
        start = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    except Exception:
        return False
    end = start + datetime.timedelta(days=int(days_out))
    return start <= today <= end


def fetch_opp_by_symbol(session, symbol, mode='cons'):
    """GET /OppBySymbol/{resource}/{symbol}/{year1}/{year2}/{day_range}/{top_pct}
    Returns a list of active pattern dicts (only patterns covering today).

    mode: 'cons' (consecutive) or 'pe' (election-cycle phase). Appserver
    expects ?mode=consecutive|pe.
    """
    if not getattr(session, 'token', None):
        return []
    resource_id, _ = _resolve_symbol(symbol)
    if resource_id is None:
        return []

    api_mode = 'pe' if mode == 'pe' else 'consecutive'
    # year1 = lookback window, year2 = min profitable years within that window.
    # Files on disk are named <year1>_<year2>[_PE<phase>].csv.gz and the
    # most-commonly-present combo is 10/10 (10-year lookback, 10 profitable).
    year1, year2 = '10', '10'
    day_range = '-'      # no filter; we want every hold-length
    top_pct = 100        # keep all rows; we filter to active ones ourselves

    url = '%s/OppBySymbol/%s/%s/%s/%s/%s/%d' % (
        APPSERVER_URL, resource_id, symbol.upper(), year1, year2, day_range, top_pct
    )
    params = {'token': session.token, 'mode': api_mode}

    try:
        resp = session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print('fetch_opp_by_symbol failed for %s: %s' % (symbol, e))
        return []

    rows = payload.get('OppBySymbol', []) if isinstance(payload, dict) else []
    today = datetime.date.today()
    active = []
    for row in rows:
        # Row shape: [date, symbol, daysOut, lOrS, sharpe_ratio, avg_profit,
        #             median_profit, avg_profit2, sharpe_ratio2]
        try:
            start_date = row[0]
            days = int(row[2])
            direction = row[3]
            sharpe = float(row[4]) if row[4] is not None else None
            avg_ret = float(row[5]) if row[5] is not None else None
        except Exception:
            continue

        if not _is_active(start_date, days, today):
            continue

        end_date = (
            datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
            + datetime.timedelta(days=days)
        ).strftime('%Y-%m-%d')

        # React ?o= contract (App.js): consecutive = the bare count ('10'), PE = 'pe2-10'.
        # '10-10' only renders via an appserver fallthrough - encode the bare count.
        years_str = str(year1) if api_mode == 'consecutive' else 'PE%d' % (datetime.date.today().year % 4)
        wv_param = _convert_param_base64(resource_id, symbol.upper(), start_date, str(days), years_str)

        active.append({
            'start_date': start_date,
            'end_date': end_date,
            'days': days,
            'direction': direction,
            'avg_return': round(avg_ret, 2) if avg_ret is not None else None,
            'sharpe': round(sharpe, 2) if sharpe is not None else None,
            'mode': 'cons' if api_mode == 'consecutive' else 'pe',
            'wave_viewer_url': '%s%s' % (WAVE_VIEWER_BASE, wv_param),
        })

    # Sort highest sharpe first so the "primary" active pattern is at [0].
    active.sort(key=lambda p: (p.get('sharpe') or -1e9), reverse=True)
    return active


# ---------------------------------------------------------------------------
# ML scorer
# ---------------------------------------------------------------------------

def _tier_for_days(days):
    if days <= 30:
        return '10_30'
    if days <= 60:
        return '31_60'
    return '61_90'


def fetch_ml_score(pattern):
    """Score a single active pattern via the ML scorer service.

    Input: pattern dict as returned by fetch_opp_by_symbol (must include
    start_date, days, direction, and enough context to recover the symbol).

    Returns dict with {score, win_prob, pred_return, pred_mfe} (None on failure).
    """
    empty = {'score': None, 'win_prob': None, 'pred_return': None, 'pred_mfe': None}
    try:
        symbol = pattern.get('symbol') or pattern.get('_symbol')
        start = pattern['start_date']
        days = int(pattern['days'])
        direction_raw = (pattern.get('direction') or '').lower()
        # Scorer expects single-letter direction: 'l' or 's'.
        direction = 'l' if direction_raw.startswith('l') else 's'

        body = {
            'opportunities': [{
                'symbol': symbol,
                'date': start,
                'daysOut': days,
                'direction': direction,
            }],
            'tier': _tier_for_days(days),
        }
        url = ML_SCORER_URL.rstrip('/') + '/score'
        resp = requests.post(url, json=body, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])
        if not results:
            return empty
        r = results[0]
        if r.get('error') or r.get('vix_blocked'):
            return empty
        wp = r.get('win_prob')
        return {
            'score': r.get('ml_score'),
            'win_prob': (wp * 100.0) if isinstance(wp, (int, float)) else wp,
            'pred_return': r.get('pred_return'),
            'pred_mfe': r.get('pred_mfe'),
        }
    except Exception as e:
        print('fetch_ml_score failed: %s' % e)
        return empty


# ---------------------------------------------------------------------------
# Historical OHLCV via appserver ChartHistorical2 (for seasonality compute)
# ---------------------------------------------------------------------------

def fetch_price_frame(symbol, session, d0='1980-01-01', d1=None):
    """Fetch OHLCV price history for a symbol via the appserver's
    /ChartHistorical2 API. Returns a pandas DataFrame with columns
    ['date', 'open', 'high', 'low', 'close', 'volume'], or None on failure.

    This is used instead of reading /home/flask/data/csv/ directly, so the
    ticker-page generator can run on a webserver that doesn't have the CSV
    archive locally.
    """
    if not getattr(session, 'token', None):
        return None
    resource_id, _ = _resolve_symbol(symbol)
    if resource_id is None:
        return None
    if d1 is None:
        d1 = datetime.date.today().strftime('%Y-%m-%d')
    url = '%s/ChartHistorical2/%s/%s/%s/%s' % (
        APPSERVER_URL, resource_id, symbol.upper(), d0, d1
    )
    try:
        resp = session.get(url, params={'token': session.token}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print('fetch_price_frame failed for %s: %s' % (symbol, e))
        return None
    rows = payload.get('ChartHistorical2', []) if isinstance(payload, dict) else []
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    return df


# ---------------------------------------------------------------------------
# Forward 30-day outlook (synthetic pattern scored against today)
# ---------------------------------------------------------------------------

def collect_forward_outlook(symbol, hold_days=30, lookback_years=None, df=None):
    """Build a 'what does this stock historically do over the next N days?'
    snapshot and score it through the ML scorer.

    Direction is auto-derived from the historical pos/neg split (TradeWave's
    convention: more losing years than winning years -> Short).

    Returns:
      {
        'anchor_date':      'YYYY-MM-DD',
        'end_date_est':     'YYYY-MM-DD',
        'hold_days':        30,
        'lookback_years':   20,
        'sample_years':     [...],
        'yearly_returns':   [{'year', 'ret_pct', 'start', 'end'}, ...],
        'avg_return':       float,
        'pos_count':        int,
        'neg_count':        int,
        'win_rate_long':    float,
        'win_rate_short':   float,
        'direction':        'l' or 's',
        'direction_label':  'LONG' or 'SHORT',
        'best_year':        {...},
        'worst_year':       {...},
        # scorer fields (may be None on failure):
        'ai_score':         float,
        'win_prob':         float,    # scorer's own model prob, 0-100
        'pred_return':      float,
        'pred_mfe':         float,
      }
    Or None if insufficient historical data.
    """
    today = datetime.date.today()
    try:
        stats = compute_forward_window(
            symbol,
            anchor_date=today,
            hold_days=hold_days,
            lookback_years=lookback_years,
            df=df,
        )
    except Exception as e:
        print('compute_forward_window failed for %s: %s' % (symbol, e))
        return None
    if not stats:
        return None

    direction = stats['direction']
    stats['direction_label'] = 'LONG' if direction == 'l' else 'SHORT'

    # Phase-filtered slice: same window, but restricted to years matching the
    # current election-cycle phase. Useful context next to the all-years number.
    cur_year = today.year
    cur_phase = 4 if (cur_year % 4) == 0 else (cur_year % 4)
    phase_names = {
        1: 'Post-Election (Year 1)',
        2: 'Midterm (Year 2)',
        3: 'Pre-Election (Year 3)',
        4: 'Election (Year 4)',
    }
    phase_short = {1: 'post-election', 2: 'midterm', 3: 'pre-election', 4: 'election'}
    try:
        phase_stats = compute_forward_window(
            symbol,
            anchor_date=today,
            hold_days=hold_days,
            lookback_years=lookback_years,
            cycle_phase=cur_phase,
            df=df,
        )
    except Exception as e:
        print('compute_forward_window (phase) failed for %s: %s' % (symbol, e))
        phase_stats = None
    stats['phase'] = cur_phase
    stats['phase_label'] = phase_names[cur_phase]
    stats['phase_label_short'] = phase_short[cur_phase]
    stats['phase_stats'] = phase_stats  # may be None or have very few samples

    # Score the synthetic pattern: start=today, days=hold_days, direction=derived.
    scorer_input = {
        'symbol': symbol.upper(),
        'start_date': stats['anchor_date'],
        'days': hold_days,
        'direction': direction,
    }
    scores = fetch_ml_score(scorer_input)
    stats['ai_score'] = scores.get('score')
    stats['win_prob'] = scores.get('win_prob')
    stats['pred_return'] = scores.get('pred_return')
    stats['pred_mfe'] = scores.get('pred_mfe')
    return stats


# ---------------------------------------------------------------------------
# EDGAR earnings
# ---------------------------------------------------------------------------

def fetch_earnings(symbol):
    """Fetch earnings data from the EDGAR HTTP service on keyprovider.
    Same pattern as appserver.get_earnings_dates(). Works on any host since
    it doesn't depend on a local /home/flask/edgar/earnings/ directory.
    Returns {next_earnings_est, days_to_earnings} (either may be None)."""
    out = {'next_earnings_est': None, 'days_to_earnings': None}
    if not EDGAR_SERVICE_URL:
        return out
    try:
        url = EDGAR_SERVICE_URL.rstrip('/') + '/earnings/' + symbol.upper()
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return out
        data = resp.json()
    except Exception as e:
        print('fetch_earnings (HTTP) failed for %s: %s' % (symbol, e))
        return out

    projected = data.get('projected_next') or {}
    date_str = projected.get('date')
    if date_str:
        out['next_earnings_est'] = date_str
        try:
            proj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            out['days_to_earnings'] = (proj - datetime.date.today()).days
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# StockScore -> trend_score
# ---------------------------------------------------------------------------

def fetch_trend_score(symbol):
    """Fetch long/short trend scores from the StockScore service.
    Returns {long, short} (either may be None) or None on failure."""
    resource_id, _ = _resolve_symbol(symbol)
    if resource_id is None:
        resource_id = '0'  # StockScore doesn't really care for scoring, US group is fine
    url = '%sstockta/%s/%s' % (STOCKSCORE_URL, resource_id, symbol.upper())
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        scores = data.get('scores') or {}
        return {
            'long': scores.get('long'),
            'short': scores.get('short'),
        }
    except Exception as e:
        print('fetch_trend_score failed for %s: %s' % (symbol, e))
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def collect_ticker_data(symbol, session, realtime_prices):
    """Build the page_data dict for one ticker. Tolerates all upstream
    failures; returns whatever it could gather.

    Arguments:
      symbol          -- ticker (case-insensitive)
      session         -- requests.Session from login_appserver()
      realtime_prices -- dict from fetch_realtime_prices()
    """
    symbol = symbol.upper()
    current_year = datetime.date.today().year

    # --- Historical OHLCV frame (fetched once via appserver HTTP API) ---
    price_df = fetch_price_frame(symbol, session)

    # --- Monthly seasonality ---
    monthly = {}
    best_month = worst_month = None
    years_of_data = None
    first_year = None
    try:
        seas = compute_monthly_seasonality(symbol, df=price_df)
        for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']:
            monthly[m] = seas.get(m)
        best_month = seas.get('best_month')
        worst_month = seas.get('worst_month')
        years_of_data = seas.get('years_of_data')
        first_year = seas.get('first_year')
    except Exception as e:
        print('compute_monthly_seasonality failed for %s: %s' % (symbol, e))

    # --- Election cycle ---
    election = {
        'election_year_type': None,
        'election_cycle_avg': None,
        'year_breakdown': {1: None, 2: None, 3: None, 4: None},
    }
    try:
        election = compute_election_cycle(symbol, current_year, df=price_df)
    except Exception as e:
        print('compute_election_cycle failed for %s: %s' % (symbol, e))

    # --- Monthly stats filtered to current cycle phase ---
    cycle_monthly = {
        'phase': None, 'phase_label': None,
        'monthly': {}, 'sample_years_list': [],
    }
    try:
        cycle_monthly = compute_monthly_by_cycle_phase(symbol, current_year, df=price_df)
    except Exception as e:
        print('compute_monthly_by_cycle_phase failed for %s: %s' % (symbol, e))

    # --- Realtime price ---
    price = change_pct = None
    pr = realtime_prices.get(symbol) if realtime_prices else None
    if isinstance(pr, (list, tuple)) and len(pr) >= 2:
        price, change_pct = pr[0], pr[1]

    # --- Active patterns ---
    active_patterns = fetch_opp_by_symbol(session, symbol, mode='cons')

    # --- AI score for top active pattern (if any) ---
    ai_score = win_prob = pred_return = pred_mfe = None
    if active_patterns:
        primary = dict(active_patterns[0])
        primary['symbol'] = symbol  # scorer needs it
        scores = fetch_ml_score(primary)
        ai_score = scores['score']
        win_prob = scores['win_prob']
        pred_return = scores['pred_return']
        pred_mfe = scores['pred_mfe']

    # --- Forward 30-day outlook (synthetic, always computed) ---
    forward_outlook = None
    try:
        forward_outlook = collect_forward_outlook(symbol, hold_days=30, lookback_years=None, df=price_df)
    except Exception as e:
        print('collect_forward_outlook failed for %s: %s' % (symbol, e))

    # --- Earnings ---
    # ETFs (resource '11') don't have earnings at all, so flag them for the
    # template to render 'N/A (ETF)' instead of 'Not scheduled'.
    resource_id, _ = _resolve_symbol(symbol)
    is_etf = (resource_id == '11')
    earnings = fetch_earnings(symbol) if not is_etf else {'next_earnings_est': None, 'days_to_earnings': None}

    # --- Trend score ---
    trend = fetch_trend_score(symbol)

    return {
        'symbol': symbol,
        'company_name': fetch_company_name(symbol),
        'current_price': price,
        'price_change_pct': change_pct,

        'monthly_returns': monthly,
        'best_month': best_month,
        'worst_month': worst_month,

        'active_patterns': active_patterns,

        'ai_score': ai_score,
        'win_prob': win_prob,
        'pred_return': pred_return,
        'pred_mfe': pred_mfe,

        'election_year_type': election.get('election_year_type'),
        'election_cycle_avg': election.get('election_cycle_avg'),
        'year_breakdown': election.get('year_breakdown'),

        'cycle_phase_monthly': cycle_monthly.get('monthly') or {},
        'cycle_phase_label': cycle_monthly.get('phase_label'),
        'cycle_phase_sample_years': cycle_monthly.get('sample_years_list') or [],

        'forward_outlook': forward_outlook,

        'is_etf': is_etf,
        'next_earnings_est': earnings.get('next_earnings_est'),
        'days_to_earnings': earnings.get('days_to_earnings'),

        'trend_score': trend,

        'years_of_data': years_of_data,
        'first_year': first_year,
    }


if __name__ == '__main__':
    sym = sys.argv[1] if len(sys.argv) > 1 else 'AAPL'
    sess = login_appserver()
    prices = fetch_realtime_prices()
    from pprint import pprint
    pprint(collect_ticker_data(sym, sess, prices))
