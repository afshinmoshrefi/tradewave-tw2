"""Authoritative historical price illustration, owned by the TradeWave engine.

Approved by Afshin on 2026-09-12. The normalized Trend Chart is NOT an input.
Clients consume the returned points; they must not reimplement this calculation.
"""
from bisect import bisect_left
import datetime as dt
import hashlib
import json
import math
from statistics import fmean
from pathlib import Path

from dateutil.relativedelta import relativedelta

METHOD = 'mean_historical_price_returns_v1'
OWNER = 'appserver/appserver/seasonal_projection.py::build_projection'


class ProjectionUnavailable(ValueError):
    """A valid request cannot be illustrated with this exact historical sample."""


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('Expected an ISO calendar date')
    result = dt.date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError('Expected an ISO calendar date')
    return result


def _number(value):
    if isinstance(value, bool):
        raise ProjectionUnavailable('Invalid price in source history')
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ProjectionUnavailable('Percentage price paths require finite positive closes')
    return result


def completed_years(receipt):
    """Consume the engine's cohort decision, not another year-selection formula."""
    rows = receipt.get('ChartData4')
    if not isinstance(rows, list) or not rows:
        raise ProjectionUnavailable('Completed seasonal observations unavailable')
    if any(type(row.get('completed')) is not bool for row in rows):
        raise ProjectionUnavailable('Engine completion identity missing')
    years = [row['year'] for row in rows if row['completed']]
    if (not years or any(type(year) is not int for year in years)
            or years != sorted(set(years))):
        raise ProjectionUnavailable('Invalid completed seasonal cohort')
    return years


def build_projection(history, *, study, years, price_date, period_days=60,
                     timeframe='daily', source=None):
    """Return dated prices and mean returns for an explicitly selected cohort.

    ``history`` contains the engine's adjusted close observations. ``years`` is
    the actual completed entry-year set from its ChartData4 receipt (or a retained
    original engine receipt in an explicit replay). The anchor is an observed
    close, never a caller-supplied price. Historical anniversaries use the next
    available observation, including weekends/holidays, never preceding prices.

    Horizons are inclusive CALENDAR days, including the anchor as day one. Daily
    points form a nominal calendar grid, not a claim of future exchange sessions.
    Weekly is only a server-selected display sampling of this same grid.
    """
    anchor = _date(price_date)
    start = _date(study['entry_date'])
    if type(period_days) is not int or not 2 <= period_days <= 366:
        raise ValueError('Projection horizon must be 2-366 inclusive calendar days')
    if timeframe not in ('daily', 'weekly'):
        raise ValueError('Invalid projection timeframe')
    if (not years or len(years) > 200 or any(type(y) is not int for y in years)
            or years != sorted(set(years)) or any(y > start.year for y in years)):
        raise ValueError('Invalid explicit historical years')
    if not isinstance(study.get('years'), str) or not study['years']:
        raise ValueError('Study lookback identity must remain a string')
    dates, closes = [], []
    for row in history:
        day = _date(row['date'])
        if dates and day <= dates[-1]:
            raise ProjectionUnavailable('Price history must have unique ascending dates')
        dates.append(day)
        closes.append(_number(row['close']))
    i = bisect_left(dates, anchor)
    if i == len(dates) or dates[i] != anchor:
        raise ProjectionUnavailable('Projection anchor is not an observed engine close')
    anchor_price = closes[i]
    end = anchor + dt.timedelta(days=period_days - 1)
    offsets = list(range(1, period_days)) if timeframe == 'daily' else list(range(7, period_days, 7))
    if period_days - 1 not in offsets:
        offsets.append(period_days - 1)
    future_dates = [anchor + dt.timedelta(days=offset) for offset in offsets]

    def close_on_or_after(nominal):
        index = bisect_left(dates, nominal)
        if nominal < dates[0] or index == len(dates) or dates[index] > anchor:
            raise ProjectionUnavailable('Exact cohort lacks a completed historical path')
        return dates[index], closes[index]

    observations = []
    for year in years:
        shift = year - start.year
        historical_anchor = anchor + relativedelta(years=shift)
        actual_anchor, base = close_on_or_after(historical_anchor)
        path = []
        effective_dates = []
        for day in future_dates:
            nominal = day + relativedelta(years=shift)
            actual, close = close_on_or_after(nominal)
            if actual < actual_anchor:
                raise ProjectionUnavailable('Historical path precedes its anchor')
            path.append(100.0 * (close / base - 1.0))
            effective_dates.append(actual.isoformat())
        observations.append({'year': year, 'anchor_nominal_date': historical_anchor.isoformat(),
                             'anchor_date': actual_anchor.isoformat(), 'anchor_price': base,
                             'effective_dates': effective_dates, 'return_pct': path})
    mean_returns = [fmean(row['return_pct'][i] for row in observations) for i in range(len(future_dates))]
    points = [[day.isoformat(), anchor_price * (1.0 + value / 100.0)]
              for day, value in zip(future_dates, mean_returns)]
    if any(not math.isfinite(value) or value <= 0 for _, value in points):
        raise ProjectionUnavailable('Projection produced an invalid price')
    history_bytes = json.dumps([[d.isoformat(), c] for d, c in zip(dates, closes)],
                              separators=(',', ':'), allow_nan=False).encode()
    return {
        'schema_version': 1, 'status': 'ok', 'owner_function': OWNER, 'method': METHOD,
        'units': {'points': 'price', 'mean_returns': 'percent_return',
                  'price_basis': 'engine_adjusted_close', 'side': 'underlying'},
        'study': dict(study), 'years': list(years), 'n': len(years),
        'anchor': {'date': anchor.isoformat(), 'price': anchor_price},
        'horizon': {'calendar_days': period_days, 'start_date': anchor.isoformat(),
                    'end_date': end.isoformat(), 'entry_day': 1,
                    'grid': 'nominal_calendar_dates', 'timeframe': timeframe},
        'historical_date_rule': 'next_available_engine_observation',
        'historical_year_alignment': 'calendar_anniversary_relativedelta',
        'points': points, 'mean_returns': [[day.isoformat(), value]
                                         for day, value in zip(future_dates, mean_returns)],
        'observations': observations,
        'source': {**(source or {}), 'engine_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'price_history_sha256': hashlib.sha256(history_bytes).hexdigest(),
                   'history_start': dates[0].isoformat(), 'history_end': dates[-1].isoformat()},
        'interpretation': 'Historical mean price illustration, not a forecast or full-window trade return.',
    }
