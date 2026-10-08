#!/usr/bin/env python3
"""Cold-import an isolated complete candidate; never send subscriber requests."""
import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True, type=Path)
    args = parser.parse_args()
    root = args.artifact.resolve() / 'payload'
    sys.path[:0] = [str(root / 'web'), str(root)]
    settings = {
        'TW2_ENV': 'staging', 'MAILERLITE_OUTBOUND_ENABLED': '0',
        'MAILERLITE_WEBINAR_REGISTRATION_ENABLED': '0',
        'POSTGRES_DSN': 'postgresql://tradewave@127.0.0.1:5432/tradewave_test',
        'WORKOS_API_KEY': 'sk_test_candidate_only', 'WORKOS_CLIENT_ID': 'client_candidate_only',
        'WORKOS_COOKIE_PASSWORD': 'unit-only-cookie-password',
        'APPSERVER_JWT_SECRET': 'unit-only-jwt-secret-at-least-32-bytes',
        'SERVICE_API_KEY': 'unit-only-service-key', 'TW2_API_CONSOLE_ENABLED': '0',
        'TW2_REACT_BUILD_DIR': '/home/flask/web-react/build',
    }
    os.environ.update(settings)
    # Load app first, unlike tests that may warm-import the repair modules.
    app_module = importlib.import_module('app')
    import config
    import email_utils
    import webinar_registration as registration
    import webinar_schedule as schedule
    loaded = {}
    for module in (app_module, config, email_utils, registration, schedule):
        path = Path(module.__file__).resolve()
        assert root in path.parents, (module.__name__, str(path))
        loaded[module.__name__] = str(path.relative_to(root))
    assert config.tw2_env == 'staging'
    assert not config.MAILERLITE_OUTBOUND_ENABLED
    assert not config.MAILERLITE_WEBINAR_REGISTRATION_ENABLED
    group = 'wb001_2026-10-09_0100PM'
    body = {'first_name': 'Alex', 'email': 'person@example.com', 'group_name': group}

    class Response:
        def __init__(self, status, data=None):
            self.status_code, self._data = status, data or {}
            self.headers, self.text = {}, ''
        def json(self):
            return self._data

    with tempfile.TemporaryDirectory(prefix='webinar-candidate-qa-') as temporary:
        schedule.CACHE_FILE = Path(temporary) / 'schedule.json'
        forbidden = Mock(side_effect=AssertionError('subscriber HTTP is forbidden'))
        with patch.object(email_utils.requests, 'request', forbidden):
            disabled = app_module.app.test_client().post('/api/webinar/register', json=body)
        assert disabled.status_code == 503, disabled.json
        forbidden.assert_not_called()
        data = schedule.fetch_webinar_data()
        session = next(s for s in schedule.get_upcoming_webinars(data) if s['group_name'] == group)
        row = next(r for r in data if str(r.get('Webinar ID')).lower() == 'wb001'
                   and str(r.get('Date')).startswith('2026-10-09'))
        assert session['webinar_url'] == row['zoom url']
        assert session['start_iso'] == '2026-10-09T13:00:00-04:00'
        memberships, fields = set(), {}
        def mocked_http(method, url, **kwargs):
            if method == 'GET' and '/groups?' in url:
                return Response(200, {'data': [{'id': 'dated', 'name': group}]})
            if method == 'GET' and '/subscribers/' in url:
                return Response(200, {'data': {'id': 'mock-only', 'status': 'active',
                    'groups': [{'id': value} for value in memberships]}})
            if method == 'POST' and '/groups/' in url:
                memberships.add(url.rsplit('/', 1)[-1])
                return Response(204)
            if method == 'POST' and url == email_utils.MAILERLITE_API_URL:
                fields.update(kwargs['json']['fields'])
                return Response(200)
            raise AssertionError((method, url))
        http = Mock(side_effect=mocked_http)
        with patch.object(config, 'tw2_env', 'prod'), \
             patch.object(config, 'MAILERLITE_OUTBOUND_ENABLED', False), \
             patch.object(config, 'MAILERLITE_WEBINAR_REGISTRATION_ENABLED', True), \
             patch.object(config, 'MAILERLITE_API_KEY', 'mock-only-key'), \
             patch.object(config, 'MAILERLITE_WEBINAR_GROUP_ID', 'general'), \
             patch.object(config, 'MAILERLITE_LIFECYCLE_GROUPS', {'trial_started': 'g-trial'}), \
             patch.object(registration, '_locally_suppressed', lambda _email: False), \
             patch.object(email_utils, '_locally_suppressed', lambda _email: False), \
             patch.object(email_utils.requests, 'request', http):
            enabled = app_module.app.test_client().post('/api/webinar/register', json=body)
            assert enabled.status_code == 200 and enabled.json == {'status': 'success'}
            assert memberships == {'general', 'dated'}
            assert fields['webinar_date'] == 'October 9, 2026'
            assert fields['webinar_time'] == '1:00 PM ET'
            assert fields['webinar_url'] == row['zoom url']
            calls = http.call_count
            assert email_utils.sync_mailerlite_lifecycle_groups(
                body['email'], 'trial_started', create_if_missing=True,
            ) == 'skip:writes-disabled'
            assert http.call_count == calls
    print(json.dumps({
        'verified_utc': datetime.now(timezone.utc).isoformat(), 'cold_imports': loaded,
        'complete_artifact_used': True, 'actual_source_group': group,
        'date': session['formatted_date'], 'time': session['formatted_time'] + ' ET',
        'source_zoom_url_matches': True,
        'disabled_route_with_real_source_and_forbidden_subscriber_http': 503,
        'enabled_route_with_mocked_provider_http': 200,
        'general_and_dated_groups_and_fields_verified': True,
        'lifecycle_http_calls': 0, 'real_subscriber_writes': 0,
        'shared_source_cache_modified': False, 'public_service_activated': False,
    }, indent=2))


if __name__ == '__main__':
    main()
