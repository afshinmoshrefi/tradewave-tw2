"""Exercise the real OppList4 file-loading block without live DB/cache calls."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

SOURCE = Path(__file__).parents[1] / 'appserver/appserver/appserver.py'

def loader(files):
    tree = ast.parse(SOURCE.read_text())
    opplist = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'OppList4')
    block = next(n for n in ast.walk(opplist) if isinstance(n, ast.If) and ast.unparse(n.test) == 'format == 3')
    wrapper = ast.parse('def load(datesListDates, fname_folder, oppPath_prev, oppPath_next, filter_date, month_num):\n    pass\n')
    wrapper.body[0].body = copy.deepcopy(block.body) + ast.parse('return opp, oppa').body
    ast.fix_missing_locations(wrapper)
    reads = []
    def read_csv(path):
        reads.append(path)
        return pd.DataFrame(files[path])
    env = {'pd': SimpleNamespace(DataFrame=pd.DataFrame, read_csv=read_csv, concat=pd.concat),
           'os': SimpleNamespace(path=SimpleNamespace(isfile=lambda path: path in files)),
           'jsonify': lambda value: value}
    exec(compile(wrapper, str(SOURCE), 'exec'), env)
    return env['load'], reads

@pytest.mark.parametrize('present_index', [0, 1, 2])
def test_sparse_weekend_preserves_each_available_day(present_index):
    dates = ['2026-09-12', '2026-09-13', '2026-09-14']
    path = '/current/' + dates[present_index] + '.csv.gz'
    expected = [{'symbol': 'TRV', 'date': dates[present_index]}]
    load, reads = loader({path: expected})
    opp, active = load(dates, '/current/', '/previous', '/next', '2026-09-14', 9)
    assert opp.to_dict('records') == expected
    assert active.empty
    assert reads == [path]

def test_all_missing_days_keep_empty_response_shape():
    load, reads = loader({})
    result = load(['2026-09-12', '2026-09-13', '2026-09-14'], '/current/', '/previous', '/next', '2026-09-14', 9)
    assert result == {'OppList': [], 'OppActiveList': []}
    assert reads == []

def test_sparse_month_boundary_retains_previous_month_row():
    expected = [{'symbol': 'TRV', 'date': '2026-01-31'}]
    load, reads = loader({'/previous/2026-01-31.csv.gz': expected})
    opp, active = load(['2026-01-31', '2026-02-01', '2026-02-02'], '/current/', '/previous', '/next', '2026-02-02', 2)
    assert opp.to_dict('records') == expected
    assert reads == ['/previous/2026-01-31.csv.gz']

def test_populated_days_are_combined_in_order_without_changes():
    dates = ['2026-09-12', '2026-09-13', '2026-09-14']
    expected = [{'symbol': 'TRV', 'date': date} for date in dates]
    files = {'/current/' + date + '.csv.gz': [row] for date, row in zip(dates, expected)}
    load, reads = loader(files)
    opp, active = load(dates, '/current/', '/previous', '/next', '2026-09-14', 9)
    assert opp.to_dict('records') == expected
    assert len(reads) == 3
