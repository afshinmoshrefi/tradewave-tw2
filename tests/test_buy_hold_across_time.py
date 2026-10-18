import datetime as dt
from pathlib import Path
import sys
from types import SimpleNamespace

import jwt
import pandas as pd
import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parents[1] / 'appserver/appserver'))
from buy_hold_across_time import completed_holds, register_buy_hold_across_time
from holding_returns import long_return_pct

pytestmark = pytest.mark.unit


def frame(dates, prices):
    return pd.DataFrame({'date': dates, 'close': prices})


def test_leap_anniversary_next_session_and_no_partial_hold():
    data = frame(['2020-02-28', '2020-02-29', '2021-02-26', '2021-03-01', '2022-02-28'],
                 [100, 200, 120, 150, 180])
    through, result = completed_holds(data, [1, 2], as_of=dt.date(2022, 2, 28))
    leap = next(p for p in result[1] if p['purchase_date'] == '2020-02-29')
    assert leap['anniversary_date'] == '2021-02-28'
    assert leap['exit_date'] == '2021-03-01'
    assert leap['return_pct'] == -25
    assert leap['ending_value'] == 750
    assert through == '2022-02-28'
    assert result[1][-1]['purchase_date'] == '2021-02-26'
    assert result[2][-1]['purchase_date'] == '2020-02-29'


def test_unobserved_weekend_anniversary_is_not_shortened():
    data = frame(['2020-03-01', '2021-02-26'], [100, 200])
    assert completed_holds(data, [1], as_of=dt.date(2021, 3, 1))[1][1] == []


def test_december_anniversary_is_full_calendar_hold_and_future_prices_excluded():
    data = frame(['2021-12-31', '2022-12-30', '2023-01-03'], [100, 125, 150])
    assert completed_holds(data, [1], as_of=dt.date(2023, 1, 2))[1][1] == []
    point = completed_holds(data, [1], as_of=dt.date(2023, 1, 3))[1][1][0]
    assert point['exit_date'] == '2023-01-03'
    assert point['return_pct'] == long_return_pct(100, 150)


@pytest.mark.parametrize('price', [0, -1, float('nan'), float('inf')])
def test_invalid_prices_fail_closed(price):
    with pytest.raises(ValueError):
        completed_holds(frame(['2020-01-02'], [price]), [1], as_of=dt.date(2026, 1, 1))


def test_empty_history_and_duplicate_dates():
    assert completed_holds(pd.DataFrame(), [4], as_of=dt.date.today()) == (None, {4: []})
    with pytest.raises(ValueError):
        completed_holds(frame(['2020-01-02'] * 2, [100, 200]), [1], as_of=dt.date.today())


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-only-secret-not-a-real-credential'
    reads = []
    def load(symbol, exchange):
        reads.append(symbol)
        return frame(['2000-01-03', '2020-01-03', '2021-01-04', '2026-01-05'], [1, 100, 120, 150])
    register_buy_hold_across_time(
        app, config=SimpleNamespace(level_access_hierarchy={'2': ['0'], '1': ['0']}, exchange_mapping={'0': 'US'}),
        check_for_token=lambda fn: fn, limiter=SimpleNamespace(limit=lambda _: lambda fn: fn),
        load_prices=load, symbol_in_resource=lambda rid, symbol: symbol in ['MSFT', 'AAPL'],
        market_today=lambda: dt.date(2026, 1, 5), years_cap=lambda level, admin: None if admin else 10,
        is_date_locked=lambda level, rid, admin: level == '1' and not admin)
    def get(query=None, level='2', admin=False, token=True):
        claims = {'aud': 'tw2-appserver', 'iss': 'tw2-web', 'user_level': level, 'is_admin': admin}
        encoded = jwt.encode(claims, app.config['SECRET_KEY'], algorithm='HS256') if token else 'invalid'
        params = {'resourceID': '0', 'symbols': 'MSFT', 'holding_years': '1', 'token': encoded}
        params.update(query or {})
        return app.test_client().get('/buy_hold_across_time', query_string=params)
    return get, reads


def test_route_caps_history_returns_native_values(client):
    get, reads = client
    response = get()
    assert response.status_code == 200
    body = response.get_json()
    assert body['history_start'] == '2016-01-05'
    assert body['series'][0]['points'][0]['purchase_date'] == '2020-01-03'
    assert body['series'][0]['points'][0]['return_pct'] == 20
    assert body['series'][0]['points'][0]['ending_value'] == 1200
    assert response.headers['Cache-Control'] == 'private, no-store'


def test_bad_auth_and_market_deny_before_price_read(client):
    get, reads = client
    assert get(token=False).status_code == 401
    assert get(level='7').status_code == 403
    assert get(level='1').status_code == 403
    assert reads == []


@pytest.mark.parametrize('query', [
    {'symbols': '../secrets'}, {'symbols': 'MSFT,MSFT'}, {'symbols': 'UNKNOWN'},
    {'symbols': 'MSFT,AAPL,WMT,IBM'}, {'holding_years': '0'},
    {'holding_years': '4,4'}, {'holding_years': '1,2,4,6'},
    {'holding_years': '1.0'}, {'resourceID': '16'},
])
def test_invalid_inputs_do_not_read_prices(client, query):
    get, reads = client
    assert get(query).status_code == 400
    assert not reads


def test_multiple_symbols_horizons_and_empty_series(client):
    get, reads = client
    body = get({'symbols': 'MSFT,AAPL', 'holding_years': '1,20'}).get_json()
    assert len(body['series']) == 4
    assert reads == ['MSFT', 'AAPL']
    assert [s['points'] for s in body['series'] if s['holding_years'] == 20] == [[], []]
