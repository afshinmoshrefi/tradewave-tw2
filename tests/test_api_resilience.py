"""API recovery contracts. Faults affect only in-process fakes, never live services."""
import json
import time

import psycopg2
import pytest
import redis
import requests
from flask import g
from psycopg2.pool import PoolError

from apiserver import app as appmod, appserver_client as ac, auth, tiers

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    customer = {'user_id': 'resilience-test', 'email': 'qa@example.com', 'tier': 'dev',
                'entitlements': tiers.tier_for('dev')}
    monkeypatch.setattr(auth, 'resolve_customer', lambda key: dict(customer))
    monkeypatch.setattr(auth, 'check_rate_limit', lambda cust: (True, {'X-RateLimit-Remaining': '9'}))
    monkeypatch.setattr(auth, 'record_usage', lambda *a: None)
    return appmod.create_app().test_client()


@pytest.mark.parametrize('fault', [redis.ConnectionError, psycopg2.OperationalError,
                                  psycopg2.InterfaceError, PoolError])
def test_infrastructure_outage_returns_safe_retryable_503(client, monkeypatch, fault):
    def unavailable(*args):
        raise fault('private-host password=must-not-appear')
    monkeypatch.setattr(auth, 'check_rate_limit', unavailable)
    response = client.get('/v1/markets', headers={'Authorization': 'Bearer tw_live_test'})
    assert response.status_code == 503
    assert response.json['error']['code'] == 'service_unavailable'
    assert int(response.headers['Retry-After']) > 0
    assert 'must-not-appear' not in response.get_data(as_text=True)


def test_upstream_error_keeps_authenticated_rate_headers(client, monkeypatch):
    def unavailable():
        raise requests.ConnectionError('unavailable')
    monkeypatch.setattr(ac, 'list_markets', unavailable)
    response = client.get('/v1/markets', headers={'Authorization': 'Bearer tw_live_test'})
    assert response.status_code == 503
    assert response.headers.get('X-RateLimit-Remaining') == '9'


def _response(status, body):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.url = 'http://private/endpoint?token=private-test-token'
    return response


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_expired_service_token_refreshes_once_without_restarting_api(monkeypatch, method):
    monkeypatch.setattr(ac, '_token', {'value': 'expired', 'exp': time.time() + 72000})
    calls = []
    def transport(verb, url, **kwargs):
        calls.append((verb, url, kwargs))
        if url.endswith('/login/api'):
            return _response(200, {'token': 'fresh'})
        return _response(200, {'ok': True}) if kwargs['params']['token'] == 'fresh' else _response(401, {})
    monkeypatch.setattr(ac._http, 'request', transport)
    result = ac.get('/example') if method == 'GET' else ac.post('/example', {'items': [1]})
    assert result == {'ok': True}
    assert [verb for verb, _, _ in calls] == [method, 'POST', method]
    assert sum(url.endswith('/login/api') for _, url, _ in calls) == 1
    if method == 'POST':
        assert calls[0][2]['json'] == calls[2][2]['json'] == {'items': [1]}


def test_rejected_refresh_is_bounded_and_credential_safe(monkeypatch):
    monkeypatch.setattr(ac, '_token', {'value': 'expired', 'exp': time.time() + 72000})
    calls = []
    def transport(verb, url, **kwargs):
        calls.append(url)
        return _response(200, {'token': 'also-rejected'}) if url.endswith('/login/api') else _response(401, {})
    monkeypatch.setattr(ac._http, 'request', transport)
    with pytest.raises(requests.HTTPError) as failure:
        ac.get('/example')
    assert len(calls) == 3
    assert 'private-test-token' not in str(failure.value)
    assert failure.value.response is None and failure.value.request is None


def test_slow_retries_share_the_original_request_deadline(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(ac.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(ac.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    monkeypatch.setattr(ac, '_rl_state', {'until': 0.0})
    calls = []
    def slow_response(method, url, **kwargs):
        timeout = kwargs.get('timeout', 110)
        budget = getattr(timeout, 'total', timeout)
        calls.append(budget)
        clock[0] += min(float(budget), 25)
        return _response(429, {})
    monkeypatch.setattr(ac._http, 'request', slow_response)
    with appmod.create_app().test_request_context():
        g.upstream_deadline = 130.0
        with pytest.raises(requests.RequestException):
            ac._request('GET', 'http://private/example', timeout=110)
    assert clock[0] <= 130.1
    assert calls[0] <= 30


def test_expired_request_never_starts_more_upstream_work(monkeypatch):
    calls = []
    monkeypatch.setattr(ac._http, 'request', lambda *a, **k: calls.append(a) or _response(200, {}))
    with appmod.create_app().test_request_context():
        g.upstream_deadline = time.monotonic() - 1
        with pytest.raises(requests.Timeout):
            ac._request('GET', 'http://private/example', timeout=110)
    assert calls == []


def test_parallel_work_inherits_deadline_without_customer_context():
    from flask import has_request_context
    from apiserver.upstream_budget import current_deadline, parallel_map
    def child(_):
        return current_deadline(), has_request_context()
    with appmod.create_app().test_request_context():
        g.upstream_deadline = 12345.0
        g.customer = {'user_id': 'must-stay-in-request'}
        observed = parallel_map(child, range(6), max_workers=2)
    assert observed == [(12345.0, False)] * 6
    assert current_deadline() is None


def test_connection_pool_wait_obeys_request_deadline(monkeypatch):
    import threading
    monkeypatch.setattr(ac, '_http_slots', threading.Semaphore(0))
    calls = []
    monkeypatch.setattr(ac._http, 'request', lambda *a, **k: calls.append(a) or _response(200, {}))
    with appmod.create_app().test_request_context():
        g.upstream_deadline = time.monotonic() + .02
        with pytest.raises(requests.Timeout):
            ac._request('GET', 'http://private/example', timeout=110)
    assert calls == []
