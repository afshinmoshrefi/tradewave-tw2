"""Completed calendar-year holds on TradeWave's adjusted daily price series."""

from bisect import bisect_left
import calendar
import datetime as dt
import math
import re

import jwt
from flask import jsonify, request

from holding_returns import long_return_pct

HORIZONS = (1, 2, 4, 6, 10, 15, 20)
US_RESOURCES = ('0', '1', '2', '3', '4')
INITIAL_VALUE = 1000


def anniversary(date, years):
    year = date.year + years
    return date.replace(year=year, day=min(date.day, calendar.monthrange(year, date.month)[1]))


def completed_holds(frame, horizons, *, as_of, history_start=None):
    """Resolve dates once; never truncate an unobserved anniversary to last price."""
    if frame is None or not hasattr(frame, 'columns') or frame.empty:
        return None, {years: [] for years in horizons}
    if not {'date', 'close'}.issubset(frame.columns):
        raise ValueError('Price history is unavailable.')
    rows = []
    for raw_date, raw_close in frame[['date', 'close']].itertuples(index=False, name=None):
        date = dt.date.fromisoformat(str(raw_date))
        if date > as_of:
            continue
        price = float(raw_close)
        if not math.isfinite(price) or price <= 0:
            raise ValueError('Price history contains an invalid adjusted close.')
        rows.append((date, price))
    rows.sort()
    if not rows:
        return None, {years: [] for years in horizons}
    dates = [row[0] for row in rows]
    if len(set(dates)) != len(dates):
        raise ValueError('Price history contains duplicate dates.')
    series = {years: [] for years in horizons}
    for i, (purchase, entry_close) in enumerate(rows):
        if history_start and purchase < history_start:
            continue
        for years in horizons:
            target = anniversary(purchase, years)
            j = bisect_left(dates, target)
            if j >= len(rows):
                continue
            pct = long_return_pct(entry_close, rows[j][1])
            series[years].append({
                'purchase_date': purchase.isoformat(),
                'entry_date': purchase.isoformat(),
                'anniversary_date': target.isoformat(),
                'exit_date': dates[j].isoformat(),
                'return_pct': pct,
                'ending_value': round(INITIAL_VALUE * (1 + pct / 100), 2),
            })
    return dates[-1].isoformat(), series


def register_buy_hold_across_time(app, *, config, check_for_token, limiter,
                                 load_prices, symbol_in_resource, market_today,
                                 years_cap, is_date_locked):
    @app.route('/buy_hold_across_time', methods=['GET'])
    @check_for_token
    @limiter.limit('12/minute')
    def buy_hold_across_time():
        def error(message, status=400):
            return jsonify({'error': message}), status

        try:
            claims = jwt.decode(request.args.get('token'), app.config['SECRET_KEY'],
                                algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
        except jwt.InvalidTokenError:
            return error('Please sign in again.', 401)
        rid = request.args.get('resourceID', '')
        if rid not in US_RESOURCES:
            return error('Choose a US stocks group to explore Buy & Hold Across Time.')
        level = str(claims.get('user_level', '1'))
        admin = bool(claims.get('is_admin'))
        if not admin and rid not in config.level_access_hierarchy.get(level, []):
            return error('This securities group is not included in your plan.', 403)
        if is_date_locked(level, rid, admin):
            return error('Historical purchase-date analysis requires a plan with unlocked dates for this group.', 403)
        symbols = request.args.get('symbols', '').upper().split(',')
        raw_horizons = request.args.get('holding_years', '').split(',')
        if (not 1 <= len(symbols) <= 3 or len(set(symbols)) != len(symbols)
                or any(not re.fullmatch(r'[A-Z0-9.^_-]{1,32}', s) for s in symbols)):
            return error('Enter one to three distinct valid stock tickers.')
        if (not 1 <= len(raw_horizons) <= 3 or len(set(raw_horizons)) != len(raw_horizons)
                or any(h not in {str(y) for y in HORIZONS} for h in raw_horizons)):
            return error('Choose up to three holding periods: 1, 2, 4, 6, 10, 15 or 20 years.')
        horizons = [int(h) for h in raw_horizons]
        for symbol in symbols:
            if not symbol_in_resource(rid, symbol):
                return error(f'{symbol} is not in the selected securities group.')
        as_of = market_today()
        cap = years_cap(level, admin)
        history_start = anniversary(as_of, -cap) if cap else None
        series = []
        try:
            for symbol in symbols:
                data_through, results = completed_holds(
                    load_prices(symbol, config.exchange_mapping[rid]), horizons,
                    as_of=as_of, history_start=history_start)
                series.extend({'symbol': symbol, 'holding_years': years,
                               'data_through': data_through, 'points': results[years]}
                              for years in horizons)
        except (ValueError, TypeError, OverflowError):
            app.logger.warning('Buy & Hold Across Time rejected invalid price history')
            return error('Price history could not be used. Please try again later.', 503)
        response = jsonify({
            'initial_value': INITIAL_VALUE, 'as_of': as_of.isoformat(),
            'history_start': history_start.isoformat() if history_start else None,
            'series': series,
            'price_basis': 'TradeWave stored adjusted closes. The provider adjusts for splits and dividends; '
                           'historical adjustment completeness has not been audited. This is not a separately reconstructed dividend-reinvestment account. No additional dividends, fees or taxes are applied. Values use the engine return rounded to two decimals.',
            'date_convention': 'Each point starts on a trading day. Exit is the first available trading day on or after '
                               'the calendar-year anniversary. February 29 uses February 28 in non-leap years. '
                               'Only fully observed holds are included; these are historical outcomes, not forecasts.',
        })
        response.headers['Cache-Control'] = 'private, no-store'
        return response
