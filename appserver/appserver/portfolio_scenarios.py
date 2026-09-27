"""Private, immutable portfolio scenario snapshots built from TradeWave chart rows."""

import datetime as dt
import inspect
import json
import logging
import math
import re
import statistics
import threading
import uuid
from urllib.parse import urlencode

import jwt
from flask import jsonify, request


USD_SHARE_RESOURCES = ('0', '1', '2', '3', '4', '11')
MAX_ROWS = 500
MAX_REPORTS = 200
MAX_ACTIVE = 2
MAX_JOB_SECONDS = 7200
_SYMBOL = re.compile(r'^[A-Z0-9.^_-]{1,32}$')
_UUID = re.compile(r'^[0-9a-f]{32}$')


class _Cancelled(Exception):
    pass


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 and number <= 1e12 else None


def _error(message, status=400):
    return jsonify({'error': message}), status


def _json():
    if request.content_length is not None and request.content_length > 200000:
        return None
    if not request.is_json:
        return None
    raw = request.stream.read(200001)
    if len(raw) > 200000:
        return None
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _years(value, cap):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[1-9][0-9]{0,2}|pe[0-3]-[1-9][0-9]{0,2})', value):
        return None
    count = int(value.split('-')[-1])
    if count > 100 or (cap is not None and count > cap):
        return None
    return count


def _summary(report):
    return {key: report.get(key) for key in ('id', 'parent_id', 'title', 'notes', 'created_at', 'status', 'settings', 'holdings_count')}


def register_portfolio_scenarios(app, *, config, redis_db, check_for_token,
                                 symbols_for_market, chart_data, last_price, market_today,
                                 symbol_in_resource=None):
    """Register routes with explicit existing-engine dependencies for focused testing."""

    def claims():
        return jwt.decode(request.args.get('token'), app.config['SECRET_KEY'], algorithms=['HS256'],
                          audience='tw2-appserver', issuer='tw2-web')

    @app.after_request
    def scenario_cache_control(response):
        if request.path.startswith('/portfolio_scenarios/') or request.path.startswith('/portfolio_holdings/'):
            response.headers['Cache-Control'] = 'private, no-store'
        return response

    def allowed(data, rid):
        return rid in USD_SHARE_RESOURCES and (data.get('is_admin') or rid in config.level_access_hierarchy.get(str(data.get('user_level', '1')), ['0']))

    def exact_symbol(rid, symbol):
        if symbol_in_resource is not None:
            return bool(symbol_in_resource(rid, symbol))
        return symbol in {str(s).upper() for s in symbols_for_market(rid)}

    def portfolio_exists(user, portfolio_id):
        if portfolio_id == 0:
            return True
        raw = redis_db.get(f'user_portfolios_{user}')
        return any(int(p.get('id', -1)) == portfolio_id for p in json.loads(raw or b'[]'))

    def report_key(user, report_id):
        return f'portfolio_scenario_{user}_{report_id}'

    def ids_key(user):
        return f'portfolio_scenario_ids_{user}'

    def read_report(user, portfolio_id, report_id):
        if not _UUID.fullmatch(report_id):
            return None
        raw = redis_db.get(report_key(user, report_id))
        report = json.loads(raw) if raw else None
        return report if report and report.get('portfolio_id') == portfolio_id else None

    def save_report(user, report):
        redis_db.set(report_key(user, report['id']), json.dumps(report, allow_nan=False))

    def holdings_rows(user, portfolio_id):
        raw = redis_db.get(f'user_reports_{user}')
        return [row for row in json.loads(raw or b'[]') if row.get('portfolioID') == portfolio_id]

    def validate_rows(rows, data):
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            return None, 'rows_must_contain_1_to_500_items'
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                return None, 'invalid_row'
            symbol = str(row.get('symbol') or '').strip().upper()
            shares = _number(row.get('shares'))
            rid = str(row.get('resourceID', ''))
            if not _SYMBOL.fullmatch(symbol) or shares is None or not rid:
                return None, 'invalid_holding'
            if rid not in USD_SHARE_RESOURCES:
                return None, 'unsupported_resource_currency_or_unit'
            if not allowed(data, rid):
                return None, 'market_not_in_plan'
            if not exact_symbol(rid, symbol):
                return None, 'symbol_not_in_market'
            direction = str(row.get('direction') or 'long').lower()
            if direction not in ('long', 'short'):
                return None, 'invalid_direction'
            cleaned.append({'dr_id': row.get('dr_id'), 'resourceID': rid, 'symbol': symbol,
                            'shares': shares, 'direction': direction, 'status': str(row.get('status', '0'))[:16]})
        return cleaned, None

    def preview_row(row, index, data, market_symbols):
        if not isinstance(row, dict):
            return {'index': index, 'status': 'invalid', 'matches': []}
        symbol = str(row.get('symbol') or '').strip().upper()
        shares = _number(row.get('shares'))
        result = {'index': index, 'symbol': symbol, 'shares': shares, 'matches': []}
        if not _SYMBOL.fullmatch(symbol) or shares is None:
            result['status'] = 'invalid'
            return result
        selected = str(row.get('resourceID', ''))
        candidates = []
        for rid, names in market_symbols.items():
            if symbol in names and (rid not in USD_SHARE_RESOURCES or exact_symbol(rid, symbol)):
                candidates.append({'resourceID': rid, 'label': config.available_resources.get(rid, rid),
                                   'name': names[symbol], 'supported': rid in USD_SHARE_RESOURCES})
        result['matches'] = candidates
        eligible = [m for m in candidates if allowed(data, m['resourceID'])]
        if selected:
            result['status'] = ('ready' if any(m['resourceID'] == selected for m in eligible)
                                else 'unsupported' if selected not in USD_SHARE_RESOURCES and any(m['resourceID'] == selected for m in candidates)
                                else 'not_in_plan' if any(m['resourceID'] == selected for m in candidates)
                                else 'unmatched')
            if result['status'] == 'ready':
                result['resourceID'] = selected
        elif not candidates:
            result['status'] = 'unmatched'
        elif not eligible:
            result['status'] = 'unsupported' if all(m['resourceID'] not in USD_SHARE_RESOURCES for m in candidates) else 'not_in_plan'
        elif len(eligible) == 1:
            result['status'] = 'ready'
            result['resourceID'] = eligible[0]['resourceID']
        else:
            result['status'] = 'ambiguous'
        return result

    @app.route('/portfolio_holdings/preview', methods=['POST'])
    @check_for_token
    def portfolio_holdings_preview():
        body = _json()
        rows = body.get('rows') if body else None
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            return _error('rows_must_contain_1_to_500_items')
        data = claims()
        market_symbols = {}
        for rid in config.available_resources:
            names = symbols_for_market(rid)
            market_symbols[rid] = {str(symbol).upper(): name for symbol, name in names.items()}
        return jsonify({'rows': [preview_row(row, i, data, market_symbols) for i, row in enumerate(rows)]})

    @app.route('/portfolio_holdings/<int:portfolio_id>', methods=['POST'])
    @check_for_token
    def portfolio_holdings_import(portfolio_id):
        body = _json()
        if body is None:
            return _error('invalid_json')
        data = claims()
        user = data['user']
        if not portfolio_exists(user, portfolio_id):
            return _error('portfolio_not_found', 404)
        cleaned, error = validate_rows(body.get('rows'), data)
        if error:
            return _error(error, 403 if error == 'market_not_in_plan' else 400)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        today = market_today().isoformat()
        key = f'user_reports_{user}'
        for attempt in range(3):
            try:
                with redis_db.pipeline() as pipe:
                    pipe.watch(key)
                    existing = json.loads(pipe.get(key) or b'[]')
                    quota = config.num_opp_reports_allowed_by_level.get(str(data.get('user_level', '1')), 0)
                    if not data.get('is_admin') and len(existing) + len(cleaned) > quota:
                        return _error('report_quota_exceeded', 409)
                    next_id = max((int(r.get('dr_id', -1)) for r in existing), default=-1) + 1
                    imported = []
                    for row in cleaned:
                        record = {'dr_id': next_id, 'portfolioID': portfolio_id, 'resourceID': row['resourceID'],
                                  'symbol': row['symbol'], 'num_shares': str(row['shares']), 'direction': row['direction'],
                                  'status': '0', 'record_type': 'holding', 'import_kind': 'holdings',
                                  'imported_at': now, 'publishDate': now, 'date': today, 'days_hold': '1',
                                  'years': '20', 'slug': '', 'sharpe_ratio': '', 'note': '', 'sm_post': 'np'}
                        existing.append(record)
                        imported.append(record)
                        next_id += 1
                    pipe.multi()
                    pipe.set(key, json.dumps(existing))
                    pipe.execute()
                    break
            except Exception as exc:
                if type(exc).__name__ != 'WatchError':
                    raise
                if attempt == 2:
                    return _error('concurrent_portfolio_update', 409)
        return jsonify({'imported': len(imported), 'count': len(existing), 'rows': imported}), 201

    def parse_settings(body, data):
        settings = body if isinstance(body, dict) else {}
        years = settings.get('years', '20')
        count = _years(years, None if data.get('is_admin') else config.num_years_allowed_by_level.get(str(data.get('user_level', '1'))))
        if count is None:
            return None
        horizons = settings.get('horizons', ['30', '60', '90', 'eoy'])
        if not isinstance(horizons, list) or not 1 <= len(horizons) <= 5 or len(set(map(str, horizons))) != len(horizons):
            return None
        horizons = [str(h) for h in horizons]
        if any(h not in ('30', '60', '90', 'eoy', 'custom') for h in horizons):
            return None
        custom = settings.get('custom_days')
        if 'custom' in horizons and (isinstance(custom, bool) or not isinstance(custom, int) or not 1 <= custom <= 366):
            return None
        return {'years': years, 'horizons': horizons, 'custom_days': custom if 'custom' in horizons else None,
                'direction': 'saved', 'valuation_basis': 'USD share closing price',
                'history_basis': 'TradeWave completed exact-window returns'}

    def selected_holdings(body, user, portfolio_id, data):
        def checked(source):
            cleaned, error = validate_rows(source, data)
            if error:
                return cleaned, error
            ids = [row['dr_id'] for row in cleaned]
            if any(isinstance(i, bool) or not isinstance(i, int) for i in ids) or len(ids) != len(set(ids)):
                return None, 'invalid_or_duplicate_row_id'
            return cleaned, None

        parent_id = body.get('parent_id')
        if parent_id is not None:
            parent = read_report(user, portfolio_id, str(parent_id))
            if parent is None or parent.get('status') != 'ready':
                return None, 'parent_report_not_found'
        else:
            parent = None
        if 'holdings' in body:
            if parent is None:
                return None, 'explicit_holdings_require_parent'
            source = body['holdings']
            frozen = {(str(h.get('dr_id')), h.get('resourceID'), h.get('symbol')) for h in parent['holdings']}
            if not isinstance(source, list) or any((str(h.get('dr_id')), str(h.get('resourceID')), str(h.get('symbol'))) not in frozen for h in source if isinstance(h, dict)):
                return None, 'holdings_must_come_from_parent'
            if len({str(h.get('dr_id')) for h in source if isinstance(h, dict)}) != len(source):
                return None, 'duplicate_row_id'
            return checked(source)
        if parent is not None:
            source = parent['holdings']
        else:
            selection = body.get('selection') or {}
            if not isinstance(selection, dict):
                return None, 'invalid_selection'
            source = holdings_rows(user, portfolio_id)
            ids = selection.get('row_ids')
            statuses = selection.get('statuses')
            if ids is not None:
                if not isinstance(ids, list) or len(ids) > MAX_ROWS or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
                    return None, 'invalid_row_ids'
                source = [r for r in source if r.get('dr_id') in ids]
                if len(source) != len(set(ids)):
                    return None, 'row_not_found'
            if statuses is not None:
                if not isinstance(statuses, list) or not statuses or len(statuses) > 16:
                    return None, 'invalid_statuses'
                source = [r for r in source if str(r.get('status', '0')) in {str(s) for s in statuses}]
            overrides = body.get('shares') or {}
            directions = body.get('directions') or {}
            if not isinstance(overrides, dict) or not isinstance(directions, dict):
                return None, 'invalid_shares'
            source = [{'dr_id': r.get('dr_id'), 'resourceID': r.get('resourceID'), 'symbol': r.get('symbol'),
                       'shares': overrides.get(str(r.get('dr_id')), r.get('shares', r.get('num_shares'))),
                       'direction': directions.get(str(r.get('dr_id')), r.get('direction', 'long')),
                       'status': r.get('status', '0')} for r in source]
        return checked(source)

    def acquire_job(user, report_id):
        with redis_db.lock('portfolio_scenario_active_lock', timeout=10, blocking_timeout=5):
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            active = json.loads(redis_db.get('portfolio_scenario_active_jobs') or b'{}')
            active = {k: v for k, v in active.items() if now - float(v.get('started_at', 0)) < MAX_JOB_SECONDS}
            if len(active) >= MAX_ACTIVE or any(v.get('user') == str(user) for v in active.values()):
                return False
            active[report_id] = {'started_at': now, 'user': str(user)}
            redis_db.set('portfolio_scenario_active_jobs', json.dumps(active), ex=MAX_JOB_SECONDS)
            return True

    def release_job(report_id):
        with redis_db.lock('portfolio_scenario_active_lock', timeout=10, blocking_timeout=5):
            active = json.loads(redis_db.get('portfolio_scenario_active_jobs') or b'{}')
            active.pop(report_id, None)
            redis_db.set('portfolio_scenario_active_jobs', json.dumps(active), ex=MAX_JOB_SECONDS)

    def engine_call(view, *args, token, **query):
        path = '/?' + urlencode({'token': token, **query})
        with app.test_request_context(path):
            response = inspect.unwrap(view)(*args)
            if isinstance(response, tuple):
                response = response[0]
            return response.get_json()

    def build_horizon(report, key, token, user, check_active):
        start = dt.date.fromisoformat(report['as_of_date'])
        end = dt.date(start.year, 12, 31) if key == 'eoy' else start + dt.timedelta(days=(report['settings']['custom_days'] if key == 'custom' else int(key)) - 1)
        days = (end - start).days + 1
        by_holding = []
        sources = []
        common = None
        available = []
        for holding in report['holdings']:
            check_active()
            result = engine_call(chart_data, holding['resourceID'], start.isoformat(), holding['symbol'],
                                 str(days - 1), report['settings']['years'], token=token,
                                 exact_window='1', report_completed_years=report['requested_year_count'],
                                 comparison_direction=holding['direction'])
            if result.get('error'):
                raise ValueError('engine_result_unavailable')
            echo = result.get('request') or {}
            expected_pe = report['settings']['years'].split('-', 1)[0] if '-' in report['settings']['years'] else 'cons'
            if (echo.get('market') != holding['resourceID'] or echo.get('symbol') != holding['symbol'] or
                    echo.get('entry_date') != start.isoformat() or echo.get('days_out') != days or
                    echo.get('comparison_direction') != holding['direction'] or
                    echo.get('years') != report['requested_year_count'] or echo.get('pe_cycle') != expected_pe or
                    echo.get('report_completed_years') != report['requested_year_count']):
                raise ValueError('engine_study_mismatch')
            annual = {}
            raw_rows = []
            for item in result.get('ChartData4') or []:
                raw_rows.append({field: item.get(field) for field in ('year', 'pct', 'price', 'completed')})
                if item.get('completed') is not True:
                    continue
                try:
                    pct = float(str(item['pct']).split(',')[0])
                    year = int(item['year'])
                except (ValueError, TypeError, KeyError):
                    raise ValueError('invalid_engine_annual_row')
                if not math.isfinite(pct):
                    raise ValueError('invalid_engine_annual_row')
                annual[year] = pct if holding['direction'] == 'long' else -pct
            available.append({'dr_id': holding['dr_id'], 'symbol': holding['symbol'], 'years': len(annual)})
            by_holding.append((holding, annual))
            sources.append({'dr_id': holding['dr_id'], 'request': echo, 'annual_rows': raw_rows})
            common = set(annual) if common is None else common.intersection(annual)
        years = sorted(common or [])
        base = sum(h['base_value'] for h in report['holdings'])
        outcomes = []
        for year in years:
            contributions = [{'dr_id': h['dr_id'], 'symbol': h['symbol'], 'change': h['base_value'] * annual[year] / 100,
                              'return_pct': annual[year]} for h, annual in by_holding]
            change = sum(c['change'] for c in contributions)
            outcomes.append({'year': year, 'end_value': base + change, 'change': change,
                             'change_pct': change / base * 100, 'contributions': contributions})
        positive = sum(o['change'] > 0 for o in outcomes)
        flat = sum(o['change'] == 0 for o in outcomes)
        negative = sum(o['change'] < 0 for o in outcomes)
        mean_end = statistics.mean(o['end_value'] for o in outcomes) if outcomes else None
        median_end = statistics.median(o['end_value'] for o in outcomes) if outcomes else None
        detail = []
        for holding, annual in by_holding:
            values = [annual[y] for y in years]
            mean_pct = statistics.mean(values) if values else None
            detail.append({'dr_id': holding['dr_id'], 'symbol': holding['symbol'],
                           'direction': holding['direction'], 'base_value': holding['base_value'],
                           'weight_pct': holding['base_value'] / base * 100,
                           'mean_return_pct': mean_pct,
                           'mean_change': holding['base_value'] * mean_pct / 100 if values else None,
                           'mean_end_value': holding['base_value'] * (1 + mean_pct / 100) if values else None,
                           'positive': sum(v > 0 for v in values), 'flat': sum(v == 0 for v in values),
                           'negative': sum(v < 0 for v in values), 'count': len(values),
                           'annual_returns': [{'year': y, 'return_pct': annual[y]} for y in years]})
        return {'key': key, 'start_date': start.isoformat(), 'end_date': end.isoformat(), 'days': days,
                'valuation_label': report['valuation_label'],
                'base_value': base, 'mean_end_value': mean_end, 'median_end_value': median_end,
                'mean_change': mean_end - base if outcomes else None,
                'median_change': median_end - base if outcomes else None,
                'mean_change_pct': (mean_end / base - 1) * 100 if outcomes else None,
                'positive': positive, 'flat': flat, 'negative': negative,
                'coverage': {'common_years': years, 'count': len(years), 'available_by_holding': available,
                             'excluded_years': sorted(set().union(*(set(a) for _, a in by_holding)) - set(years))},
                'annual_outcomes': outcomes,
                'holdings': detail, 'engine_sources': sources}

    def commentary(report, user):
        facts = {'as_of_date': report['as_of_date'], 'base_price_as_of_date': report.get('base_price_as_of_date'),
                 'valuation_label': report['valuation_label'], 'holdings_count': len(report['holdings']),
                 'horizons': [{'key': h['key'], 'mean_change_pct': h['mean_change_pct'],
                               'mean_change': h['mean_change'], 'median_change': h['median_change'],
                               'positive': h['positive'], 'flat': h['flat'], 'negative': h['negative'],
                               'history_count': h['coverage']['count'],
                               'top_contributions': [{'symbol': row['symbol'], 'mean_change': row['mean_change'],
                                                      'weight_pct': row['weight_pct']}
                                                     for row in sorted(h['holdings'],
                                                                       key=lambda row: abs(row['mean_change'] or 0),
                                                                       reverse=True)[:5]]}
                              for h in report['horizons']]}
        prompt = ('Explain only the supplied historical scenario facts in under 120 words. '
                  'Do not calculate, invent statistics, predict outcomes, or give personalized investment advice. '
                  'State that historical scenarios are not forecasts. No tools.')
        messages = [{'role': 'user', 'content': json.dumps(facts)}]
        try:
            from openai_tools_appserver import send_openai_messages
            from tara_runtime_policy import PRIMARY_MODEL
            text = send_openai_messages(
                messages, system=prompt,
                user_id=user, model=PRIMARY_MODEL, max_output_tokens=256)
            if isinstance(text, str) and text.strip():
                return {'status': 'ready', 'text': text.strip(), 'model': PRIMARY_MODEL}
        except Exception:
            logging.warning('Portfolio scenario primary commentary unavailable')
        try:
            from AI_tools_appserver import send_claude_messages
            from tara_runtime_policy import FALLBACK_MODEL
            text = send_claude_messages(messages, model=FALLBACK_MODEL, system=prompt, max_tokens=256)
            if isinstance(text, str) and text.strip():
                return {'status': 'ready', 'text': text.strip(), 'model': FALLBACK_MODEL}
        except Exception:
            logging.warning('Portfolio scenario fallback commentary unavailable')
        return {'status': 'unavailable', 'text': None, 'model': None}

    def worker(user, report_id, token):
        report = None
        try:
            raw = redis_db.get(report_key(user, report_id))
            if raw is None:
                return
            report = json.loads(raw)
            def check_active():
                if (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(report['created_at'])).total_seconds() > MAX_JOB_SECONDS:
                    raise ValueError('worker_expired')
                if redis_db.get(report_key(user, report_id)) is None:
                    raise _Cancelled()
            for holding in report['holdings']:
                check_active()
                price_result = engine_call(last_price, holding['resourceID'], holding['symbol'], token=token)
                quote = price_result.get('StockLastPrice')
                if not isinstance(quote, list) or len(quote) != 2 or _number(quote[1]) is None:
                    raise ValueError('closing_price_unavailable')
                holding['price_date'] = str(quote[0])
                holding['price'] = float(quote[1])
                holding['base_value'] = holding['shares'] * holding['price']
            price_dates = {h['price_date'] for h in report['holdings']}
            if len(price_dates) != 1:
                raise ValueError('mixed_closing_price_dates')
            quote_day = dt.date.fromisoformat(next(iter(price_dates)))
            scenario_day = dt.date.fromisoformat(report['as_of_date'])
            age_days = (scenario_day - quote_day).days
            if age_days < 0 or age_days > 7:
                raise ValueError('closing_prices_stale')
            report['base_price_as_of_date'] = quote_day.isoformat()
            report['price_window_gap_days'] = age_days
            report['horizons'] = [build_horizon(report, key, token, user, check_active) for key in report['settings']['horizons']]
            check_active()
            report['ai_scores'] = {'status': 'unavailable', 'reason': 'Exact-window portfolio AI scores are not available.'}
            report['commentary'] = commentary(report, user)
            report['status'] = 'ready'
        except _Cancelled:
            pass
        except Exception as exc:
            logging.warning('Portfolio scenario failed category=%s', type(exc).__name__)
            if report is not None:
                report['status'] = 'failed'
                report['error'] = str(exc) if isinstance(exc, ValueError) else 'calculation_unavailable'
        finally:
            try:
                with redis_db.lock(f'portfolio_scenario_user_lock_{user}', timeout=10, blocking_timeout=5):
                    latest_raw = redis_db.get(report_key(user, report_id))
                    if latest_raw is not None and report is not None:  # Delete Forever may have run during calculation.
                        latest = json.loads(latest_raw)
                        if not (latest.get('status') == 'failed' and latest.get('error') == 'worker_expired'):
                            report['title'] = latest['title']
                            report['notes'] = latest['notes']
                            save_report(user, report)
            finally:
                release_job(report_id)

    @app.route('/portfolio_scenarios/<int:portfolio_id>', methods=['GET', 'POST'])
    @check_for_token
    def portfolio_scenarios(portfolio_id):
        data = claims()
        user = data['user']
        if not portfolio_exists(user, portfolio_id):
            return _error('portfolio_not_found', 404)
        if request.method == 'GET':
            ids = json.loads(redis_db.get(ids_key(user)) or b'[]')
            reports = [read_report(user, portfolio_id, rid) for rid in ids]
            return jsonify({'reports': [_summary(r) for r in reports if r]})
        body = _json()
        if body is None:
            return _error('invalid_json')
        settings = parse_settings(body.get('settings'), data)
        if settings is None:
            return _error('invalid_settings')
        holdings, error = selected_holdings(body, user, portfolio_id, data)
        if error:
            return _error(error, 403 if error == 'market_not_in_plan' else 400)
        title = body.get('title') or 'Portfolio scenario'
        notes = body.get('notes') or ''
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or not isinstance(notes, str) or len(notes) > 2000:
            return _error('invalid_title_or_notes')
        report_id = uuid.uuid4().hex
        if not acquire_job(user, report_id):
            return _error('scenario_capacity_busy', 429)
        try:
            with redis_db.lock(f'portfolio_scenario_user_lock_{user}', timeout=10, blocking_timeout=5):
                ids = json.loads(redis_db.get(ids_key(user)) or b'[]')
                user_quota = (MAX_REPORTS if data.get('is_admin') else
                              min(MAX_REPORTS, config.num_opp_reports_allowed_by_level.get(str(data.get('user_level', '1')), 0)))
                if len(ids) >= user_quota:
                    release_job(report_id)
                    return _error('scenario_quota_exceeded', 409)
                report = {'id': report_id, 'parent_id': body.get('parent_id'), 'portfolio_id': portfolio_id,
                          'title': title.strip(), 'notes': notes, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                          'status': 'running', 'settings': settings, 'requested_year_count': _years(settings['years'], None),
                          'calculation_version': 'portfolio_fixed_share_common_completed_v1',
                          'as_of_date': market_today().isoformat(), 'holdings_count': len(holdings),
                          'valuation_label': 'Modeled notional value' if any(h['direction'] == 'short' for h in holdings) else 'Holdings value',
                          'assumptions': ['Fixed share quantities', 'USD share closing prices',
                                          'No rebalancing, borrowing costs, collateral, or FX conversion',
                                          'Short exposure is modeled as notional value, not account equity'],
                          'holdings': holdings, 'horizons': [], 'commentary': {'status': 'pending', 'text': None}}
                ids.insert(0, report_id)
                with redis_db.pipeline() as pipe:
                    pipe.multi()
                    pipe.set(report_key(user, report_id), json.dumps(report, allow_nan=False))
                    pipe.set(ids_key(user), json.dumps(ids))
                    pipe.execute()
            threading.Thread(target=worker, args=(user, report_id, request.args['token']), daemon=True).start()
            return jsonify({'report': report}), 202
        except Exception:
            release_job(report_id)
            raise

    @app.route('/portfolio_scenarios/<int:portfolio_id>/<report_id>', methods=['GET', 'PATCH', 'DELETE'])
    @check_for_token
    def portfolio_scenario_detail(portfolio_id, report_id):
        user = claims()['user']
        report = read_report(user, portfolio_id, report_id)
        if report is None:
            return _error('report_not_found', 404)
        if request.method == 'GET':
            if report['status'] == 'running' and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(report['created_at'])).total_seconds() > MAX_JOB_SECONDS:
                with redis_db.lock(f'portfolio_scenario_user_lock_{user}', timeout=10, blocking_timeout=5):
                    report = read_report(user, portfolio_id, report_id)
                    if report is None:
                        return _error('report_not_found', 404)
                    if report['status'] == 'running':
                        report['status'] = 'failed'
                        report['error'] = 'worker_expired'
                        save_report(user, report)
            return jsonify({'report': report})
        body = _json()
        if body is None:
            return _error('invalid_json')
        if request.method == 'PATCH':
            if set(body) - {'title', 'notes'}:
                return _error('only_title_and_notes_are_editable')
            with redis_db.lock(f'portfolio_scenario_user_lock_{user}', timeout=10, blocking_timeout=5):
                report = read_report(user, portfolio_id, report_id)
                if report is None:
                    return _error('report_not_found', 404)
                title = body.get('title', report['title'])
                notes = body.get('notes', report['notes'])
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or not isinstance(notes, str) or len(notes) > 2000:
                    return _error('invalid_title_or_notes')
                report['title'] = title.strip()
                report['notes'] = notes
                save_report(user, report)
            return jsonify({'report': report})
        if body.get('confirm_forever') is not True:
            return _error('confirm_forever_required')
        with redis_db.lock(f'portfolio_scenario_user_lock_{user}', timeout=10, blocking_timeout=5):
            ids = json.loads(redis_db.get(ids_key(user)) or b'[]')
            with redis_db.pipeline() as pipe:
                pipe.multi()
                pipe.delete(report_key(user, report_id))
                pipe.set(ids_key(user), json.dumps([rid for rid in ids if rid != report_id]))
                pipe.execute()
        return jsonify({'deleted': True})
