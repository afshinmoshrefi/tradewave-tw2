"""Dev-only HTTP smoke with real engine data and disposable service-owned records.

Run with the normal dev environment loaded. Never prints tokens or provider keys.
"""
import datetime
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config


def main():
    if os.environ.get('TW2_ENV') != 'dev':
        raise SystemExit('This smoke is permitted only on dev.')
    base = os.environ.get('SCENARIO_SMOKE_URL', 'http://127.0.0.1:5000').rstrip('/')
    if base not in ('http://127.0.0.1:5000', 'http://127.0.0.1:5002'):
        raise SystemExit('Use a loopback dev appserver.')
    login = requests.post(base + '/login/api', headers={'X-Service-Key': config.SERVICE_API_KEY}, timeout=30)
    assert login.status_code == 200, 'service login failed'
    token = login.json()['token']

    def call(method, path, body=None, expected=200, query=None):
        try:
            response = requests.request(method, base + path, params={'token': token, **(query or {})}, json=body, timeout=90)
        except requests.RequestException:
            raise RuntimeError('Dev scenario request failed; credentials omitted.') from None
        assert response.status_code == expected, '%s %s returned %s' % (method, path, response.status_code)
        return response.json()

    name = 'Scenario QA ' + uuid.uuid4().hex[:10]
    report_ids, row_ids = [], []
    portfolio_id = None
    try:
        created = call('POST', '/add_user_portfolio_name/' + name, {})
        portfolio_id = next(p['id'] for p in created['portfolio_names_list'] if p['name'] == name)
        rows = [{'symbol': 'AAPL', 'shares': 10.5, 'resourceID': '2'},
                {'symbol': 'MSFT', 'shares': 5, 'resourceID': '1'}]
        preview = call('POST', '/portfolio_holdings/preview', {'rows': rows})
        assert all(r['status'] == 'ready' for r in preview['rows']), 'preview failed'
        imported = call('POST', '/portfolio_holdings/%s' % portfolio_id, {'rows': rows}, 201)
        row_ids = [r['dr_id'] for r in imported['rows']]
        assert float(imported['rows'][0]['num_shares']) == 10.5, 'fractional shares lost'
        root = '/portfolio_scenarios/%s' % portfolio_id
        created = call('POST', root, {'title': 'Scenario QA snapshot', 'selection': {'row_ids': row_ids},
                       'settings': {'years': '10', 'horizons': ['30', 'eoy']}}, 202)['report']
        report_ids.append(created['id'])
        path = root + '/' + created['id']
        deadline = time.monotonic() + 420
        report = created
        while report['status'] == 'running' and time.monotonic() < deadline:
            time.sleep(2)
            report = call('GET', path)['report']
        assert report['status'] == 'ready', 'scenario did not finish: ' + str(report.get('error', report['status']))
        assert len(report['horizons']) == 2
        for horizon in report['horizons']:
            assert horizon['coverage']['count'] > 0, 'no common history'
            for holding in report['holdings']:
                source = call('GET', '/ChartData4/%s/%s/%s/%s/%s' % (
                    holding['resourceID'], report['as_of_date'], holding['symbol'], horizon['days'] - 1,
                    report['settings']['years']), query={'exact_window': '1', 'report_completed_years': 10,
                                                         'comparison_direction': holding['direction']})
                expected = {int(r['year']): float(str(r['pct']).split(',')[0])
                            for r in source['ChartData4'] if r.get('completed') is True}
                saved = next(h for h in horizon['holdings'] if h['dr_id'] == holding['dr_id'])
                assert all(r['return_pct'] == expected[r['year']] for r in saved['annual_returns']), 'engine fidelity mismatch'
        frozen = json.dumps(report['horizons'], sort_keys=True)
        edited = call('PATCH', path, {'title': 'Scenario QA renamed', 'notes': 'Disposable dev smoke'})['report']
        assert json.dumps(edited['horizons'], sort_keys=True) == frozen, 'metadata edit changed results'
        call('DELETE', path, {'confirm_forever': False}, 400)
        assert call('GET', path)['report']['id'] == report['id']
        print(json.dumps({'status': 'passed', 'holdings': len(report['holdings']),
                          'horizons': [{'key': h['key'], 'common_years': h['coverage']['count']} for h in report['horizons']],
                          'commentary': report['commentary']['status'], 'as_of': report['as_of_date']}))
    finally:
        if portfolio_id is not None:
            for report_id in report_ids:
                call('DELETE', '/portfolio_scenarios/%s/%s' % (portfolio_id, report_id), {'confirm_forever': True})
                call('GET', '/portfolio_scenarios/%s/%s' % (portfolio_id, report_id), expected=404)
            for row_id in row_ids:
                call('POST', '/dr_report_remove/%s' % row_id, {})
            call('POST', '/del_user_portfolio_name/' + name, {})


if __name__ == '__main__':
    main()
