"""
Monthly seasonality computation for TradeWave Programmatic SEO ticker pages.

Pure-Python, no API calls. Reads a ticker's CSV directly from
/home/flask/data/csv/US/{SYMBOL}.csv and computes:

  - Monthly seasonality: avg return, win rate, sample size, best/worst year
    per calendar month, based on first-trading-day close to last-trading-day
    close of each month across all available years.

  - Election-cycle overlay: same monthly-return aggregation filtered by the
    four-year presidential cycle phase.

Uses hardcoded path strings from /home/flask/config.py (csv_folder).
"""

import os
import sys
import datetime
import pandas as pd

# Central config. Explicit hardcoded path, not Path(__file__).parent.
sys.path.insert(0, '/home/flask')
import config

CSV_DIR_US = '/home/flask/data/csv/US'
CSV_DIR_ETF = '/home/flask/data/csv/ETF'

MONTH_ABBREVS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _csv_path(symbol):
    """Return the CSV path for a symbol. Check US equities first, then ETFs."""
    sym = symbol.upper()
    us_path = os.path.join(CSV_DIR_US, '%s.csv' % sym)
    if os.path.isfile(us_path):
        return us_path
    return os.path.join(CSV_DIR_ETF, '%s.csv' % sym)


def _load_price_frame(symbol):
    """Load OHLCV frame for a symbol. Returns DataFrame indexed by date or
    raises FileNotFoundError if no CSV exists."""
    path = _csv_path(symbol)
    if not os.path.isfile(path):
        raise FileNotFoundError('No CSV for symbol %s at %s' % (symbol, path))

    df = pd.read_csv(path)
    # CSV format: ,date,open,high,low,close,volume,adj_factor
    # First (unnamed) column is the index. Drop it if present.
    if df.columns[0] == '' or df.columns[0].startswith('Unnamed'):
        df = df.drop(columns=[df.columns[0]])

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    return df


def _month_end(year, month):
    """Last calendar day of the (year, month). Used to detect incomplete months."""
    if month == 12:
        nxt = datetime.date(year + 1, 1, 1)
    else:
        nxt = datetime.date(year, month + 1, 1)
    return nxt - datetime.timedelta(days=1)


def _monthly_returns_frame(df, today=None):
    """For every (year, month) present in the frame, compute:
       first-trading-day close to last-trading-day close percentage return.

    Drops any month that has not yet ended (e.g. current calendar month) so
    partial-month returns never pollute historical averages.

    Returns DataFrame with columns: year, month, ret_pct.
    """
    if today is None:
        today = datetime.date.today()

    grouped = df.groupby(['year', 'month'], sort=True)['close']
    firsts = grouped.first()
    lasts = grouped.last()

    out = pd.DataFrame({'first': firsts, 'last': lasts}).reset_index()
    out = out[(out['first'] > 0) & out['last'].notna()]
    out['ret_pct'] = (out['last'] - out['first']) / out['first'] * 100.0

    # Drop incomplete months: a (year, month) row is kept only if the month has
    # fully ended on or before today.
    out = out[out.apply(lambda r: _month_end(int(r['year']), int(r['month'])) <= today, axis=1)]
    return out[['year', 'month', 'ret_pct']]


def _completed_year_count(years, today=None):
    """How many fully completed calendar years span [first_year, last_complete_year]."""
    if today is None:
        today = datetime.date.today()
    if not years:
        return 0, None, None
    first_year = int(min(years))
    complete = [int(y) for y in years if today > datetime.date(int(y), 12, 31)]
    if not complete:
        return 0, first_year, None
    last_complete = max(complete)
    return last_complete - first_year + 1, first_year, last_complete


def _aggregate_month_stats(month_rets):
    """Aggregate a per-year return series for a single month into summary stats."""
    if len(month_rets) == 0:
        return {
            'avg_return': None,
            'win_rate': None,
            'sample_years': 0,
            'best_year_return': None,
            'worst_year_return': None,
        }
    return {
        'avg_return': round(float(month_rets.mean()), 2),
        'win_rate': round(float((month_rets > 0).mean() * 100.0), 1),
        'sample_years': int(len(month_rets)),
        'best_year_return': round(float(month_rets.max()), 2),
        'worst_year_return': round(float(month_rets.min()), 2),
    }


def _prepare_frame(df):
    """Normalize a price frame: ensure datetime, sort, add year/month cols.
    Used when the caller passes an already-loaded DataFrame (e.g. fetched
    from the appserver's ChartHistorical2 API)."""
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    return df


def compute_monthly_seasonality(symbol, df=None):
    """Compute monthly seasonality stats for a ticker. If `df` is provided
    (preloaded OHLCV DataFrame with a 'date' and 'close' column), use it
    directly; otherwise fall back to reading the local CSV.

    Returns a dict:
      {
        'Jan': {avg_return, win_rate, sample_years, best_year_return, worst_year_return},
        ...
        'Dec': {...},
        'best_month': 'Jan',
        'worst_month': 'Sep',
        'years_of_data': 44,
        'first_year': 1982,
      }
    """
    if df is None:
        df = _load_price_frame(symbol)
    else:
        df = _prepare_frame(df)
    mrets = _monthly_returns_frame(df)

    result = {}
    for m_idx, m_name in enumerate(MONTH_ABBREVS, start=1):
        subset = mrets.loc[mrets['month'] == m_idx, 'ret_pct']
        result[m_name] = _aggregate_month_stats(subset)

    # Find best / worst month by avg_return (skipping any None).
    ranked = [
        (m, result[m]['avg_return'])
        for m in MONTH_ABBREVS
        if result[m]['avg_return'] is not None
    ]
    if ranked:
        best_month = max(ranked, key=lambda x: x[1])[0]
        worst_month = min(ranked, key=lambda x: x[1])[0]
    else:
        best_month = None
        worst_month = None

    years = sorted(df['year'].unique().tolist())
    years_of_data, first_year, last_complete_year = _completed_year_count(years)

    result['best_month'] = best_month
    result['worst_month'] = worst_month
    result['years_of_data'] = years_of_data
    result['first_year'] = first_year
    result['last_complete_year'] = last_complete_year
    return result


def compute_election_cycle(symbol, current_year, df=None):
    """Compute election-cycle stats for a ticker.

    Year labels (mod 4):
      Year 1 = post-election (year % 4 == 1)
      Year 2 = midterm       (year % 4 == 2)
      Year 3 = pre-election  (year % 4 == 3)
      Year 4 = election      (year % 4 == 0)

    Returns:
      {
        'election_year_type': 'Midterm (Year 2)',
        'election_cycle_avg': <avg yearly total return in that phase>,
        'year_breakdown': {1: avg, 2: avg, 3: avg, 4: avg}
      }
    """
    if df is None:
        df = _load_price_frame(symbol)
    else:
        df = _prepare_frame(df)
    mrets = _monthly_returns_frame(df)
    if mrets.empty:
        return {
            'election_year_type': None,
            'election_cycle_avg': None,
            'year_breakdown': {1: None, 2: None, 3: None, 4: None},
        }

    # Aggregate to per-year total return: sum of monthly returns (approximate,
    # but consistent across cycle phases). Using sum keeps this transparent and
    # matches the PRD request for a single scalar per phase.
    yearly = mrets.groupby('year')['ret_pct'].sum().reset_index()
    yearly['phase'] = yearly['year'].apply(lambda y: 4 if (y % 4) == 0 else (y % 4))

    year_breakdown = {}
    for phase in [1, 2, 3, 4]:
        subset = yearly.loc[yearly['phase'] == phase, 'ret_pct']
        year_breakdown[phase] = (
            round(float(subset.mean()), 2) if len(subset) > 0 else None
        )

    # Phase label for current_year.
    current_phase = 4 if (current_year % 4) == 0 else (current_year % 4)
    phase_names = {
        1: 'Post-Election (Year 1)',
        2: 'Midterm (Year 2)',
        3: 'Pre-Election (Year 3)',
        4: 'Election (Year 4)',
    }

    return {
        'election_year_type': phase_names[current_phase],
        'election_cycle_avg': year_breakdown[current_phase],
        'year_breakdown': year_breakdown,
    }


def compute_monthly_by_cycle_phase(symbol, current_year, df=None):
    """For each calendar month, compute avg return / win rate / sample size
    using ONLY years that match the same election-cycle phase as current_year.

    The current_year itself is excluded (in-progress, mostly partial months).

    Returns:
      {
        'phase': 2,
        'phase_label': 'Midterm (Year 2)',
        'monthly': {'Jan': {avg_return, win_rate, sample_years}, ..., 'Dec': {...}},
        'sample_years_list': [1998, 2002, ..., 2022],   # phase years used
      }
    """
    if df is None:
        df = _load_price_frame(symbol)
    else:
        df = _prepare_frame(df)
    mrets = _monthly_returns_frame(df)

    current_phase = 4 if (current_year % 4) == 0 else (current_year % 4)
    phase_names = {
        1: 'Post-Election (Year 1)',
        2: 'Midterm (Year 2)',
        3: 'Pre-Election (Year 3)',
        4: 'Election (Year 4)',
    }

    if mrets.empty:
        return {
            'phase': current_phase,
            'phase_label': phase_names[current_phase],
            'monthly': {m: _aggregate_month_stats(pd.Series(dtype=float)) for m in MONTH_ABBREVS},
            'sample_years_list': [],
        }

    # Phase match: year % 4 maps to phase (mod 4 == 0 -> phase 4).
    def _phase(y):
        return 4 if (y % 4) == 0 else (y % 4)

    phase_rows = mrets[(mrets['year'].apply(_phase) == current_phase) & (mrets['year'] != current_year)]
    sample_years_list = sorted(phase_rows['year'].unique().tolist())

    monthly = {}
    for m_idx, m_name in enumerate(MONTH_ABBREVS, start=1):
        subset = phase_rows.loc[phase_rows['month'] == m_idx, 'ret_pct']
        monthly[m_name] = _aggregate_month_stats(subset)

    return {
        'phase': current_phase,
        'phase_label': phase_names[current_phase],
        'monthly': monthly,
        'sample_years_list': [int(y) for y in sample_years_list],
    }


def compute_forward_window(symbol, anchor_date=None, hold_days=30, lookback_years=None, cycle_phase=None, df=None):
    """For a given anchor date (defaults to today), compute the historical
    distribution of returns from buying on that calendar date and holding for
    `hold_days` calendar days. If `lookback_years` is None (default), uses every
    prior year present in the ticker's CSV; otherwise uses the last N years.
    The current year is always excluded (it would be incomplete).

    If `cycle_phase` is set (1..4), only years matching that election-cycle phase
    are kept, where phase = 4 if year%4==0 else year%4.

    For each prior year Y:
      - find the first trading close on or after (Y, anchor.month, anchor.day)
      - find the last  trading close on or before (Y, anchor.month, anchor.day) + hold_days
      - compute % change

    Direction is auto-derived per TradeWave's convention: if negative years
    outnumber positive years, the setup is Short ('s'), otherwise Long ('l').
    (A tie breaks Long.)

    Returns:
      {
        'anchor_date':     '2026-04-13',
        'end_date_est':    '2026-05-13',
        'hold_days':       30,
        'lookback_years':  20,
        'sample_years':    [2006, 2007, ..., 2025],
        'yearly_returns':  [{'year': Y, 'ret_pct': r, 'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}, ...],
        'avg_return':      float,
        'median_return':   float,
        'pos_count':       int,
        'neg_count':       int,
        'win_rate_long':   float,   # pos / (pos+neg) * 100
        'win_rate_short':  float,   # neg / (pos+neg) * 100
        'direction':       'l' or 's',
        'best_year':       {'year': Y, 'ret_pct': r},
        'worst_year':      {'year': Y, 'ret_pct': r},
      }
    """
    if anchor_date is None:
        anchor_date = datetime.date.today()

    if df is None:
        df = _load_price_frame(symbol)
    else:
        df = _prepare_frame(df)
    if df.empty:
        return None

    # Build a sorted list of (date, close) pairs once.
    df_sorted = df.sort_values('date').reset_index(drop=True)
    dates = df_sorted['date'].dt.date.tolist()
    closes = df_sorted['close'].tolist()

    import bisect

    def _first_close_on_or_after(target):
        i = bisect.bisect_left(dates, target)
        if i >= len(dates):
            return None, None
        return dates[i], closes[i]

    def _last_close_on_or_before(target):
        i = bisect.bisect_right(dates, target) - 1
        if i < 0:
            return None, None
        return dates[i], closes[i]

    current_year = anchor_date.year
    available_years = sorted({int(y) for y in df_sorted['date'].dt.year.unique().tolist() if int(y) < current_year})
    if lookback_years is None:
        years_to_check = available_years
    else:
        years_to_check = [y for y in available_years if y >= current_year - lookback_years]
    if cycle_phase is not None:
        def _phase(y):
            return 4 if (y % 4) == 0 else (y % 4)
        years_to_check = [y for y in years_to_check if _phase(y) == cycle_phase]

    yearly = []
    for y in years_to_check:
        try:
            anchor_y = datetime.date(y, anchor_date.month, anchor_date.day)
        except ValueError:
            # Feb 29 on a non-leap year etc; skip.
            continue
        end_y = anchor_y + datetime.timedelta(days=hold_days)

        s_date, s_close = _first_close_on_or_after(anchor_y)
        e_date, e_close = _last_close_on_or_before(end_y)
        if s_date is None or e_date is None:
            continue
        if s_date > end_y or e_date < anchor_y:
            continue
        if s_close is None or e_close is None or s_close <= 0:
            continue
        ret = (e_close - s_close) / s_close * 100.0
        yearly.append({
            'year': y,
            'ret_pct': round(float(ret), 2),
            'start': s_date.strftime('%Y-%m-%d'),
            'end': e_date.strftime('%Y-%m-%d'),
        })

    if not yearly:
        return None

    rets = [r['ret_pct'] for r in yearly]
    pos = sum(1 for r in rets if r > 0)
    neg = sum(1 for r in rets if r < 0)
    avg = sum(rets) / len(rets)
    srt = sorted(rets)
    mid = len(srt) // 2
    median = srt[mid] if len(srt) % 2 == 1 else (srt[mid - 1] + srt[mid]) / 2.0

    direction = 's' if neg > pos else 'l'
    total_non_zero = pos + neg if (pos + neg) > 0 else 1
    win_long = pos / total_non_zero * 100.0
    win_short = neg / total_non_zero * 100.0

    best = max(yearly, key=lambda r: r['ret_pct'])
    worst = min(yearly, key=lambda r: r['ret_pct'])

    return {
        'anchor_date': anchor_date.strftime('%Y-%m-%d'),
        'end_date_est': (anchor_date + datetime.timedelta(days=hold_days)).strftime('%Y-%m-%d'),
        'hold_days': hold_days,
        'lookback_years': lookback_years,
        'sample_years': [r['year'] for r in yearly],
        'yearly_returns': yearly,
        'avg_return': round(float(avg), 2),
        'median_return': round(float(median), 2),
        'pos_count': pos,
        'neg_count': neg,
        'win_rate_long': round(win_long, 1),
        'win_rate_short': round(win_short, 1),
        'direction': direction,
        'best_year': {'year': best['year'], 'ret_pct': best['ret_pct']},
        'worst_year': {'year': worst['year'], 'ret_pct': worst['ret_pct']},
    }


if __name__ == '__main__':
    sym = sys.argv[1] if len(sys.argv) > 1 else 'AAPL'
    from pprint import pprint
    pprint(compute_monthly_seasonality(sym))
    print()
    pprint(compute_election_cycle(sym, 2026))
    print()
    pprint(compute_monthly_by_cycle_phase(sym, 2026))
    print()
    pprint(compute_forward_window(sym))
