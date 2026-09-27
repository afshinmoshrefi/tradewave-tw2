"""Focused contract checks using retained engine rows as the return authority."""

import contextlib
import datetime as dt
import json
import pathlib
import sys
import types
import unittest

import jwt
from flask import Flask, jsonify, request


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'appserver' / 'appserver'))
import portfolio_scenarios as scenarios


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key):
        self.values.pop(key, None)

    def lock(self, *args, **kwargs):
        return contextlib.nullcontext()

    def pipeline(self):
        database = self
        class Pipeline:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def watch(self, key):
                pass
            def get(self, key):
                return database.get(key)
            def multi(self):
                self.pending = []
            def set(self, key, value):
                self.pending.append(('set', key, value))
            def delete(self, key):
                self.pending.append(('delete', key))
            def execute(self):
                for operation in self.pending:
                    if operation[0] == 'set':
                        database.set(operation[1], operation[2])
                    else:
                        database.delete(operation[1])
        return Pipeline()


class ImmediateThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class DeferredThread(ImmediateThread):
    pending = []

    def start(self):
        self.pending.append(self)


class PortfolioScenarioTest(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.price_dates = {'AAA': '2026-09-25', 'BBB': '2026-09-25'}
        self.echo_market_override = None
        self.exact_symbols = {'0': {'AAA', 'BBB'}, '11': set()}
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'test-key'
        config = types.SimpleNamespace(
            level_access_hierarchy={'6': ['0', '11']},
            num_opp_reports_allowed_by_level={'6': 500},
            num_years_allowed_by_level={'6': 50},
            available_resources={'0': 'US STOCKS', '11': 'ETFs'},
        )
        def token_guard(func):
            def wrapped(*args, **kwargs):
                if not request.args.get('token'):
                    return jsonify({'error': 'missing_token'}), 403
                return func(*args, **kwargs)
            wrapped.__name__ = func.__name__
            return wrapped

        def chart(rid, date, symbol, days, years):
            pe = years.split('-', 1)[0] if '-' in years else 'cons'
            count = int(years.split('-')[-1])
            rows = [{'year': 2023, 'pct': '10,12,-5' if symbol == 'AAA' else '-10,2,-15',
                     'price': '10,11', 'completed': True}]
            if symbol == 'AAA':
                rows.append({'year': 2024, 'pct': '20,22,-1', 'price': '10,12', 'completed': True})
            return jsonify({'ChartData4': rows, 'request': {
                'market': self.echo_market_override or rid, 'symbol': symbol, 'entry_date': date, 'days_out': int(days) + 1,
                'years': count, 'pe_cycle': pe, 'comparison_direction': request.args['comparison_direction'],
                'report_completed_years': count}})

        def price(rid, symbol):
            return jsonify({'StockLastPrice': [self.price_dates[symbol], '10' if symbol == 'AAA' else '20']})

        self.original_thread = scenarios.threading.Thread
        scenarios.threading.Thread = ImmediateThread
        self.original_decode = getattr(scenarios.jwt, 'decode', None)
        if not hasattr(jwt, 'encode'):
            scenarios.jwt.decode = lambda token, *args, **kwargs: {'user': int(token), 'user_level': '6'}
        self.original_openai = sys.modules.get('openai_tools_appserver')
        self.original_policy = sys.modules.get('tara_runtime_policy')
        self.original_anthropic = sys.modules.get('AI_tools_appserver')
        sys.modules['openai_tools_appserver'] = types.SimpleNamespace(
            send_openai_messages=lambda *args, **kwargs: 'Historical scenarios are not forecasts.')
        sys.modules['tara_runtime_policy'] = types.SimpleNamespace(PRIMARY_MODEL='test-model')
        scenarios.register_portfolio_scenarios(
            self.app, config=config, redis_db=self.redis, check_for_token=token_guard,
            symbols_for_market=lambda rid: {'AAA': 'AAA Inc', 'BBB': 'BBB Inc'} if rid == '0' else {},
            chart_data=chart, last_price=price, market_today=lambda: dt.date(2026, 9, 27),
            symbol_in_resource=lambda rid, symbol: symbol in self.exact_symbols.get(rid, set()))
        self.client = self.app.test_client()
        self.token = self.make_token(1)

    def tearDown(self):
        scenarios.threading.Thread = self.original_thread
        if self.original_decode is None:
            del scenarios.jwt.decode
        else:
            scenarios.jwt.decode = self.original_decode
        for name, old in [('openai_tools_appserver', self.original_openai),
                          ('tara_runtime_policy', self.original_policy),
                          ('AI_tools_appserver', self.original_anthropic)]:
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def make_token(self, user):
        if not hasattr(jwt, 'encode'):
            return str(user)
        return jwt.encode({'user': user, 'user_level': '6', 'aud': 'tw2-appserver', 'iss': 'tw2-web'},
                          self.app.config['SECRET_KEY'], algorithm='HS256')

    def path(self, suffix, token=None):
        return suffix + '?token=' + (token or self.token)

    def test_import_preview_and_quota_input_validation(self):
        url = self.path('/portfolio_holdings/preview')
        result = self.client.post(url, json={'rows': [{'symbol': 'AAA', 'shares': 0.5},
                                                       {'symbol': 'ZZZ', 'shares': 1}]}).get_json()['rows']
        self.assertEqual([r['status'] for r in result], ['ready', 'unmatched'])
        bad = self.client.post(self.path('/portfolio_holdings/0'),
                               json={'rows': [{'symbol': 'AAA', 'shares': -1, 'resourceID': '0'}]})
        self.assertEqual(bad.status_code, 400)
        good = self.client.post(self.path('/portfolio_holdings/0'),
                                json={'rows': [{'symbol': 'AAA', 'shares': 0.5, 'resourceID': '0'}]})
        self.assertEqual(good.status_code, 201)
        self.assertEqual(good.get_json()['rows'][0]['num_shares'], '0.5')
        self.assertEqual(good.get_json()['rows'][0]['record_type'], 'holding')
        self.assertEqual(good.headers['Cache-Control'], 'private, no-store')
        unsupported = self.client.post(self.path('/portfolio_holdings/0'),
                                       json={'rows': [{'symbol': 'AAA', 'shares': 1, 'resourceID': '7'}]})
        self.assertEqual(unsupported.get_json()['error'], 'unsupported_resource_currency_or_unit')
        self.exact_symbols['0'].remove('BBB')
        wrong_group = self.client.post(self.path('/portfolio_holdings/0'),
                                       json={'rows': [{'symbol': 'BBB', 'shares': 1, 'resourceID': '0'}]})
        self.assertEqual(wrong_group.get_json()['error'], 'symbol_not_in_market')

    def test_common_cohort_snapshot_revision_and_deletion(self):
        source = [{'dr_id': 1, 'portfolioID': 0, 'resourceID': '0', 'symbol': 'AAA',
                   'num_shares': '2', 'direction': 'long', 'status': '1'},
                  {'dr_id': 2, 'portfolioID': 0, 'resourceID': '0', 'symbol': 'BBB',
                   'num_shares': '1', 'direction': 'short', 'status': '2'}]
        self.redis.set('user_reports_1', json.dumps(source))
        created = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'title': 'Two holdings', 'selection': {'row_ids': [1, 2]},
            'settings': {'horizons': ['30'], 'years': '20'}})
        self.assertEqual(created.status_code, 202)
        report_id = created.get_json()['report']['id']
        report = self.client.get(self.path('/portfolio_scenarios/0/' + report_id)).get_json()['report']
        self.assertEqual(report['status'], 'ready')
        horizon = report['horizons'][0]
        self.assertEqual(horizon['end_date'], '2026-10-26')
        self.assertEqual(horizon['coverage']['common_years'], [2023])
        self.assertEqual(horizon['coverage']['excluded_years'], [2024])
        self.assertAlmostEqual(horizon['mean_change_pct'], 10)
        self.assertEqual((horizon['positive'], horizon['flat'], horizon['negative']), (1, 0, 0))
        self.assertEqual(horizon['engine_sources'][1]['annual_rows'][0]['pct'], '-10,2,-15')

        self.redis.set('user_reports_1', '[]')
        frozen = [dict(row) for row in report['holdings']]
        frozen[0]['shares'] = 3
        revised = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'parent_id': report['id'], 'holdings': frozen,
            'settings': {'horizons': ['30'], 'years': '20'}})
        self.assertEqual(revised.status_code, 202)
        self.assertNotEqual(revised.get_json()['report']['id'], report['id'])
        self.assertEqual(self.client.get(self.path('/portfolio_scenarios/0/' + report['id'])).get_json()['report']['holdings'][0]['shares'], 2)
        other = self.client.get(self.path('/portfolio_scenarios/0/' + report['id'], self.make_token(2)))
        self.assertEqual(other.status_code, 404)
        self.assertEqual(self.client.delete(self.path('/portfolio_scenarios/0/' + report['id']),
                                            json={}).status_code, 400)
        self.assertEqual(self.client.delete(self.path('/portfolio_scenarios/0/' + report['id']),
                                            json={'confirm_forever': True}).status_code, 200)
        self.assertEqual(self.client.get(self.path('/portfolio_scenarios/0/' + report['id'])).status_code, 404)

    def test_deleted_running_report_cannot_be_resurrected(self):
        self.redis.set('user_reports_1', json.dumps([{'dr_id': 1, 'portfolioID': 0, 'resourceID': '0',
                                                      'symbol': 'AAA', 'num_shares': '2', 'direction': 'long'}]))
        DeferredThread.pending = []
        scenarios.threading.Thread = DeferredThread
        created = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'settings': {'horizons': ['30'], 'years': '20'}})
        self.assertEqual(created.status_code, 202)
        report_id = created.get_json()['report']['id']
        deleted = self.client.delete(self.path('/portfolio_scenarios/0/' + report_id),
                                     json={'confirm_forever': True})
        self.assertEqual(deleted.status_code, 200)
        DeferredThread.pending.pop().target(1, report_id, self.token)
        self.assertEqual(self.client.get(self.path('/portfolio_scenarios/0/' + report_id)).status_code, 404)

    def test_mixed_quotes_and_engine_identity_fail_closed(self):
        self.redis.set('user_reports_1', json.dumps([{'dr_id': 1, 'portfolioID': 0, 'resourceID': '0',
                                                      'symbol': 'AAA', 'num_shares': '2', 'direction': 'long'},
                                                     {'dr_id': 2, 'portfolioID': 0, 'resourceID': '0',
                                                      'symbol': 'BBB', 'num_shares': '1', 'direction': 'long'}]))
        self.price_dates['BBB'] = '2026-09-24'
        created = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'settings': {'horizons': ['30'], 'years': '20'}})
        report_id = created.get_json()['report']['id']
        failed = self.client.get(self.path('/portfolio_scenarios/0/' + report_id)).get_json()['report']
        self.assertEqual(failed['error'], 'mixed_closing_price_dates')
        self.price_dates['BBB'] = '2026-09-25'
        self.echo_market_override = '11'
        created = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'settings': {'horizons': ['30'], 'years': '20'}})
        report_id = created.get_json()['report']['id']
        failed = self.client.get(self.path('/portfolio_scenarios/0/' + report_id)).get_json()['report']
        self.assertEqual(failed['error'], 'engine_study_mismatch')

    def test_commentary_provider_failure_keeps_factual_report(self):
        def unavailable(*args, **kwargs):
            raise RuntimeError('provider_unavailable')
        sys.modules['openai_tools_appserver'].send_openai_messages = unavailable
        sys.modules['AI_tools_appserver'] = types.SimpleNamespace(send_claude_messages=unavailable)
        sys.modules['tara_runtime_policy'].FALLBACK_MODEL = 'fallback-test'
        self.redis.set('user_reports_1', json.dumps([{'dr_id': 1, 'portfolioID': 0, 'resourceID': '0',
                                                      'symbol': 'AAA', 'num_shares': '2', 'direction': 'long'}]))
        created = self.client.post(self.path('/portfolio_scenarios/0'), json={
            'settings': {'horizons': ['30'], 'years': '20'}})
        report_id = created.get_json()['report']['id']
        report = self.client.get(self.path('/portfolio_scenarios/0/' + report_id)).get_json()['report']
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['commentary'], {'status': 'unavailable', 'text': None, 'model': None})
        self.assertEqual(report['horizons'][0]['coverage']['count'], 2)


if __name__ == '__main__':
    unittest.main()
