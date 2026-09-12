"""Exercise the owning engine with hand-checkable prices, not another calculator."""
import importlib.util
import ast
import datetime
import sys
from types import SimpleNamespace
from pathlib import Path
import pytest

path = Path(__file__).parents[1] / 'appserver/appserver/seasonal_projection.py'
spec = importlib.util.spec_from_file_location('seasonal_projection', path)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def project(history, **kwargs):
    return engine.build_projection(history, study={'entry_date': '2026-09-05', 'years': '2'},
        years=[2024, 2025], price_date='2026-09-04', period_days=4, **kwargs)


@pytest.fixture
def prices():
    return [{'date': d, 'close': c} for d, c in [
        ('2024-09-04', 100), ('2024-09-05', 110), ('2024-09-06', 120),
        ('2024-09-09', 130), ('2025-09-04', 200), ('2025-09-05', 180),
        ('2025-09-08', 180), ('2026-09-04', 50)]]


def test_price_returns_not_normalized_index_and_next_available_date(prices):
    result = project(prices)
    assert result['method'] == 'mean_historical_price_returns_v1'
    # +10% and -10% -> unchanged anchor. Final: +30% and -10% -> +10%.
    assert result['points'][0][0] == '2026-09-05'
    assert result['points'][0][1] == pytest.approx(50)
    assert result['points'][-1][1] == pytest.approx(55)
    assert result['points'][-1][0] == '2026-09-07'
    assert result['observations'][0]['effective_dates'][-1] == '2024-09-09'
    assert result['observations'][1]['effective_dates'][-1] == '2025-09-08'
    assert result['years'] == [2024, 2025]
    assert result['horizon']['calendar_days'] == 4


def test_weekly_is_engine_sample_of_same_calendar_path(prices):
    daily = project(prices)
    weekly = project(prices, timeframe='weekly')
    assert weekly['points'] == [daily['points'][-1]]


def test_missing_exact_cohort_or_anchor_holds(prices):
    with pytest.raises(engine.ProjectionUnavailable):
        project(prices[1:])
    with pytest.raises(engine.ProjectionUnavailable):
        project(prices[:-1])


def test_cohort_requires_engine_completion_flags():
    receipt = {'ChartData4': [{'year': 2022, 'completed': True}, {'year': 2026, 'completed': False}]}
    assert engine.completed_years(receipt) == [2022]
    with pytest.raises(engine.ProjectionUnavailable):
        engine.completed_years({'ChartData4': [{'year': 2022}]})


@pytest.mark.parametrize('bad', [0, -1, float('nan'), float('inf')])
def test_invalid_price_cannot_be_published(prices, bad):
    prices[0]['close'] = bad
    with pytest.raises(engine.ProjectionUnavailable):
        project(prices)


def test_calendar_anniversary_crosses_year_and_leap_day():
    history = [{'date': d, 'close': c} for d, c in [
        ('2022-12-30', 100), ('2023-01-03', 110), ('2026-12-30', 50)]]
    result = engine.build_projection(history, study={'entry_date': '2026-12-31', 'years': 'pe2-1'},
        years=[2022], price_date='2026-12-30', period_days=4)
    assert result['points'][-1][0] == '2027-01-02'
    assert result['points'][-1][1] == pytest.approx(55)
    assert result['observations'][0]['effective_dates'][-1] == '2023-01-03'
    leap = [{'date': d, 'close': c} for d, c in [
        ('2023-02-28', 100), ('2023-03-01', 120), ('2024-02-29', 50)]]
    result = engine.build_projection(leap, study={'entry_date': '2024-03-01', 'years': '1'},
        years=[2023], price_date='2024-02-29', period_days=2)
    assert result['observations'][0]['anchor_date'] == '2023-02-28'
    assert result['points'][0][1] == pytest.approx(60)


def test_route_uses_entitlement_receipt_and_preserves_cohort(monkeypatch, prices):
    from flask import Flask, jsonify, request
    import pandas as pd
    monkeypatch.setitem(sys.modules, 'seasonal_projection', engine)
    app = Flask(__name__)
    received = []
    denied = [False]
    receipt = {'request': {'market': '2', 'symbol': 'TEST', 'entry_date': '2026-09-05',
        'days_out': 30, 'years': 2, 'pe_cycle': 'cons'},
        'ChartData4': [{'year': 2024, 'completed': True}, {'year': 2025, 'completed': True}]}
    def primary(*args):
        received.append(args)
        if denied[0]:
            return jsonify({'error': 'market_not_in_plan'}), 403
        return jsonify(receipt)
    namespace = {'app': app, 'request': request, 'jsonify': jsonify, 'datetime': datetime,
        'getChartData4': primary, 'config': SimpleNamespace(exchange_mapping={'2': 'US'}),
        'get_symbol_csv': lambda *args: pd.DataFrame(prices)}
    source = path.with_name('appserver.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'getSeasonalProjection')
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    with app.test_request_context('/?price_date=2026-09-04&period_days=4'):
        # A tier-clamped study is echoed, never mislabeled as the requested 10.
        result = namespace['getSeasonalProjection']('2', '2026-09-05', 'TEST', '29', '10')
        assert result.get_json()['study']['years'] == '2'
        assert result.get_json()['years'] == [2024, 2025]
        assert 'observations' not in result.get_json()
        assert received[-1] == ('2', '2026-09-05', 'TEST', '29', '10')
        denied[0] = True
        result = app.make_response(namespace['getSeasonalProjection']('2', '2026-09-05', 'TEST', '29', '10'))
        assert result.status_code == 403
        count = len(received)
        invalid = app.make_response(namespace['getSeasonalProjection']('2', '2026-09-05', 'TEST', '9999', '10'))
        assert invalid.status_code == 400
        assert len(received) == count
