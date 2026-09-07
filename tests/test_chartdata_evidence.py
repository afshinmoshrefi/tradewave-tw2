"""Execute the real ChartData4 calculation with synthetic EOD history.

Load only this function to avoid the monolithic server's process-wide service
startup. Authentication, CSV IO and Redis are fakes; the year loop and statistical
calculations under test are the production function, not a copied implementation.
"""
import ast
import calendar
import datetime
import json
import statistics
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask, jsonify, request

pytestmark = pytest.mark.unit


@pytest.fixture
def engine():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-only'
    dates = pd.bdate_range('2020-01-02', '2026-09-04')
    df = pd.DataFrame({'date': dates.strftime('%Y-%m-%d'), 'close': 100.0,
                       'high': 102.0, 'low': 98.0, 'volume': 1000, 'adj_factor': 1.0})
    def inc_day(value, n):
        return (datetime.date.fromisoformat(value) + datetime.timedelta(days=n)).isoformat()
    def inc_year(value, n):
        date = datetime.date.fromisoformat(value)
        year = date.year + n
        return date.replace(year=year, day=min(date.day, calendar.monthrange(year, date.month)[1])).isoformat()
    namespace = {
        'app': app, 'request': request, 'jsonify': jsonify, 'datetime': datetime,
        'calendar': calendar, 'statistics': statistics, 'json': json,
        'config': SimpleNamespace(exchange_mapping={'2':'test'}, csv_folder='/unused/',
                                  min_required_years=1, free_return=4, chart_data_expire_time=60),
        'jwt': SimpleNamespace(decode=lambda *a, **k: {'is_admin':True}),
        '_market_today': lambda: datetime.date(2026,9,7),
        'is_hundred_year_chart_request': lambda *a, **k: False,
        'get_geo_from_token': lambda *a: (None,)*5,
        'get_remote_address': lambda: '127.0.0.1',
        'update_activity_log': lambda *a: None,
        '_singleflight_cache_values': lambda keys: [None]*len(keys),
        'stockscore_with_availability': lambda *a: (0,0,0,0,False),
        'get_symbol_csv': lambda *a: df.copy(),
        'num_years_in_df': lambda data: data.date.str[:4].nunique(),
        'inc_date_day': inc_day, 'inc_date_year': inc_year,
        'custom_year_filter': lambda year, pe, *args: year % 4 == int(pe[-1]),
        'get_earnings_dates': lambda *a: None,
        'redis_client': SimpleNamespace(set=lambda *a: None, expire=lambda *a: None),
    }
    path = Path(__file__).parents[1] / 'appserver/appserver/appserver.py'
    tree = ast.parse(path.read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'getChartData4')
    fn.decorator_list = []
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
    def run(date='2026-09-01', days=30, years='10', direction='long'):
        with app.test_request_context('/?token=fake&exact_window=1&comparison_direction=' + direction):
            response = namespace['getChartData4']('2', date, 'TEST', str(days-1), years)
            return response.get_json()
    return df, run


@pytest.mark.parametrize('direction', ['long', 'short'])
def test_flat_completed_years_are_non_wins_and_partial_is_labelled(engine, direction):
    _, run = engine
    data = run(direction=direction)
    complete = [row for row in data['ChartData4'] if row['completed']]
    assert [row['year'] for row in complete] == list(range(2020,2026))
    assert data['ChartData4'][-1]['completed'] is False
    assert data['stats']['Num Winners'] == '0'
    assert data['stats']['Num Losers'] == str(len(complete))
    assert data['stats']['Avg Profit - All'] == '0.0%'


def test_lookback_beyond_listing_does_not_fabricate_prior_years(engine):
    _, run = engine
    data = run(years='99')
    assert data['ChartData4'][0]['year'] == 2020
    assert len(data['ChartData4']) == 7


def test_exact_january_window_is_not_silently_shifted(engine):
    _, run = engine
    data = run(date='2026-01-01', days=31)
    assert data['request']['entry_date'] == '2026-01-01'
    assert data['request']['days_out'] == 31


def test_single_interval_excursions_include_the_actual_move_and_entry_zero(engine):
    df, run = engine
    df.loc[df.date == '2025-09-02', ['close','high','low']] = [105,106,101]
    data = run(date='2026-09-01', days=2)
    row = next(row for row in data['ChartData4'] if row['year'] == 2025)
    assert row['pct'] == '5.0,6.0,0.0'


def test_average_and_cumulative_keep_fractional_percentage_points(engine):
    df, run = engine
    df.loc[df.date == '2025-09-30', ['close','high']] = [101.23,103]
    data = run()
    assert data['stats']['Avg Profit - All'] == '0.2%'
    assert data['stats']['Cumulative Return'] == '1.23%'
