"""Publication consumes engine receipts and never relabels stale ML as current."""
import ast
import base64
import csv
import datetime as dt
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(monkeypatch, relative):
    monkeypatch.syspath_prepend(str(ROOT / 'site/lib'))
    monkeypatch.setitem(sys.modules, 'config', SimpleNamespace(
        appserver_url='http://engine', ml_scorer_url='http://scorer'))
    spec = importlib.util.spec_from_file_location('publication_test', ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_home_csv_preserves_engine_values_and_inclusive_identity(monkeypatch, tmp_path):
    module = load_module(monkeypatch, 'site/home_opportunities.py')
    monkeypatch.setattr(module, 'new_york_now', lambda: dt.datetime(2026, 9, 10))
    monkeypatch.setattr(module, 'appserver_login', lambda: 'test-token')
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    # Raw offset 29 is a 30-calendar-day window. TWA/TWR must be copied from
    # columns 7/8, not reconstructed from any other statistic.
    receipt = ['2026-09-10', 'AAA', 29, 'Long', 1.12, 4.34, 3.56, 8.78, 2.91]
    urls = []
    def get(url, **_):
        urls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {'OppList': [receipt]})
    monkeypatch.setattr(module.requests, 'get', get)
    monkeypatch.setattr(module, 'lookup_company_name', lambda symbol, _: symbol)
    path = tmp_path / 'home.csv'
    monkeypatch.setattr(sys, 'argv', ['home_opportunities.py', '--output', str(path)])
    assert module.main() == 0
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 1
    row = rows[0]
    assert row['TWA'] == '8.78' and row['TWR'] == '2.91'
    assert row['days'] == '30' and row['day_range'] == '7-30'
    assert base64.b64decode(row['pattern_param']).decode() == '2|AAA|2026-09-10|30|PE2-10'
    assert any('/6-29/' in url for url in urls)
    assert any('/30-59/' in url for url in urls)
    assert module.normalize_opp(receipt[:8]) is None
    assert module.normalize_opp(receipt[:7] + [float('nan'), 2.91]) is None


def test_closed_home_window_uses_inclusive_end():
    path = ROOT / 'site/generate_home_page.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('drop_closed_windows', 'group_by_day_range')]
    ns = dict(datetime=dt.datetime, date=dt.date, timedelta=dt.timedelta,
              sys=sys, OPPORTUNITIES_CSV='test.csv', OPPORTUNITIES_PER_TAB=10)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    row = dict(start_date='2026-07-01', days=31, day_range='31-60', symbol='AAA')
    assert ns['drop_closed_windows']([row], dt.date(2026, 7, 31)) == [row]
    assert ns['drop_closed_windows']([row], dt.date(2026, 8, 1)) == []
    ns['group_by_day_range']([row])
    assert row['end_date_formatted'] == 'Jul 31'


def health_metadata():
    return dict(model_release='v3', model_manifest_hash='model',
                feature_schema_hash='features', context_schema_version='1',
                data_generation_hash='generation', data_source_manifest_hash='sources',
                data_as_of='2026-09-09', context_data_complete=True)


@pytest.mark.parametrize('nested', [False, True])
def test_current_scorer_identity_accepts_both_health_envelopes(monkeypatch, nested):
    module = load_module(monkeypatch, 'site/lib/daily_pattern_picks.py')
    monkeypatch.setattr(module, 'latest_completed_us_equity_session', lambda: dt.date(2026, 9, 9))
    metadata = health_metadata()
    payload = {'metadata': metadata} if nested else metadata
    monkeypatch.setattr(module.requests, 'get', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload))
    identity = module.current_pick_data_identity()
    assert identity['data_as_of'] == '2026-09-09'
    assert identity['data_generation_hash'] == 'generation'


@pytest.mark.parametrize('changes', [
    {'data_as_of': '2026-08-28'}, {'context_data_complete': False},
    {'data_generation_hash': ''},
])
def test_stale_or_unverifiable_scorer_cannot_select_a_new_pick(monkeypatch, changes):
    module = load_module(monkeypatch, 'site/lib/daily_pattern_picks.py')
    monkeypatch.setattr(module, 'latest_completed_us_equity_session', lambda: dt.date(2026, 9, 9))
    metadata = health_metadata()
    metadata.update(changes)
    monkeypatch.setattr(module.requests, 'get', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: metadata))
    monkeypatch.setattr(module.requests, 'post', lambda *a, **k: pytest.fail('stale scorer was called'))
    with pytest.raises(RuntimeError, match='Daily pick deferred'):
        module.get_daily_picks('2026-09-10', ['2'], 1, 'l', 10, 30, 5, .8)


@pytest.mark.parametrize('changed', [False, True])
def test_pick_requires_stable_model_and_data_provenance(monkeypatch, changed):
    module = load_module(monkeypatch, 'site/lib/daily_pattern_picks.py')
    before = health_metadata()
    after = dict(before, data_generation_hash='replacement') if changed else before
    identities = iter([before, after])
    monkeypatch.setattr(module, 'current_pick_data_identity', lambda: next(identities))
    monkeypatch.setattr(module.requests, 'post', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {'picks': [{'symbol': 'AAA'}]}))
    if changed:
        with pytest.raises(RuntimeError, match='changed during selection'):
            module.get_daily_picks('2026-09-10', ['2'], 1, 'l', 10, 30, 5, .8)
    else:
        result = module.get_daily_picks('2026-09-10', ['2'], 1, 'l', 10, 30, 5, .8)
        assert result['metadata'] == before
        assert result['picks'] == [{'symbol': 'AAA'}]
