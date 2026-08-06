"""Canonical symbol contracts for the appserver EOD update client."""

import copy
from pathlib import Path

import pandas as pd
import pytest
import requests

from data_updater import update_client2 as updater


pytestmark = pytest.mark.unit


VALID_EODHD_ROWS = [
    {
        'date': '2026-08-04',
        'open': 198,
        'high': 202,
        'low': 196,
        'close': 200,
        'adjusted_close': 100,
        'volume': 0,
    },
    {
        'date': '2026-08-05',
        'open': 101,
        'high': 104,
        'low': 99,
        'close': 102,
        'adjusted_close': 102,
        'volume': 1000,
    },
]


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_brk_b_legacy_manifest_symbol_requests_and_writes_canonical_name(
    tmp_path,
    monkeypatch,
):
    requested_urls = []
    response = {'update': []}

    monkeypatch.setattr(updater.config, 'update_server', 'http://updates.test/')
    monkeypatch.setattr(
        updater,
        'get_update_with_retry',
        lambda url: requested_urls.append(url) or response,
    )
    monkeypatch.setattr(
        updater,
        'set_file_date_tomorrow_if_post_market',
        lambda path: None,
    )

    assert updater.canonical_resource_symbol('brk.b') == 'BRK-B'
    assert updater.canonical_resource_symbol('BRK-B') == 'BRK-B'
    assert updater.canonical_resource_symbol('BF.B') == 'BF.B'
    assert updater.request_symbol_update('2', 'BRK.B', '2026-08-05') == response

    frame = pd.DataFrame(
        [['2026-08-06', 1, 2, 0.5, 1.5, 100, 1]],
        columns=updater.csv_columns,
    )
    written_path = updater.write_symbol_csv(frame, str(tmp_path), 'BRK.B')

    assert requested_urls == [
        'http://updates.test/update/2/BRK-B/2026-08-05'
    ]
    assert Path(written_path) == tmp_path / 'BRK-B.csv'
    assert (tmp_path / 'BRK-B.csv').is_file()
    assert not (tmp_path / 'BRK.B.csv').exists()
    assert list(tmp_path.glob('*.tmp.*')) == []


def test_canonical_brk_b_recovery_requests_bounded_eodhd_range_and_adjusts_ohlc(
    monkeypatch,
    capsys,
):
    calls = []
    secret = 'do-not-log-this-eod-token'
    monkeypatch.setattr(updater.config, 'EOD_token', secret)

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(copy.deepcopy(VALID_EODHD_ROWS))

    monkeypatch.setattr(updater.requests, 'get', fake_get)

    rows = updater.fetch_eodhd_recovery_rows(
        'BRK-B',
        '2026-08-03',
        '2026-08-05',
    )

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == 'https://eodhistoricaldata.com/api/eod/BRK-B.US'
    assert secret not in url
    assert kwargs['timeout'] == (5, 30)
    assert kwargs['allow_redirects'] is False
    assert kwargs['params'] == {
        'api_token': secret,
        'period': 'd',
        'fmt': 'json',
        'order': 'a',
        'from': '2026-08-04',
        'to': '2026-08-05',
    }
    assert rows == [
        ['2026-08-04', 99.0, 101.0, 98.0, 100.0, 0, 0.5],
        ['2026-08-05', 101.0, 104.0, 99.0, 102.0, 1000, 1.0],
    ]
    assert secret not in capsys.readouterr().out


def test_recovery_scope_is_exactly_canonical_migration_symbol_on_us(monkeypatch):
    assert updater.CANONICAL_MIGRATION_SYMBOLS == {'BRK-B'}
    calls = []
    monkeypatch.setattr(
        updater,
        'fetch_eodhd_recovery_rows',
        lambda *args: calls.append(args) or [['recovered']],
    )
    missing = {'update': 'file missing:/data/csv/US/BRK-B.csv'}

    assert updater.recover_source_missing_update(
        {'update': []},
        symbol='BRK-B',
        exchange='US',
        last_date='2026-08-04',
        completed_session='2026-08-05',
    ) == (False, None)
    assert updater.recover_source_missing_update(
        missing,
        symbol='BRK.B',
        exchange='US',
        last_date='2026-08-04',
        completed_session='2026-08-05',
    ) == (False, None)
    assert updater.recover_source_missing_update(
        missing,
        symbol='AAPL',
        exchange='US',
        last_date='2026-08-04',
        completed_session='2026-08-05',
    ) == (False, None)
    assert updater.recover_source_missing_update(
        missing,
        symbol='BRK-B',
        exchange='ETF',
        last_date='2026-08-04',
        completed_session='2026-08-05',
    ) == (False, None)
    assert calls == []


def test_source_missing_integration_attempts_only_canonical_recovery(monkeypatch):
    recovered = [['2026-08-05', 1, 2, 0.5, 1.5, 100, 1]]
    calls = []
    monkeypatch.setattr(
        updater,
        'fetch_eodhd_recovery_rows',
        lambda *args: calls.append(args) or recovered,
    )

    attempted, rows = updater.recover_source_missing_update(
        {'update': 'file missing:/data/csv/US/BRK-B.csv'},
        symbol='BRK-B',
        exchange='US',
        last_date='2026-08-04',
        completed_session='2026-08-05',
    )

    assert attempted is True
    assert rows == recovered
    assert calls == [('BRK-B', '2026-08-04', '2026-08-05')]


@pytest.mark.parametrize(
    ('mutate', 'last_date', 'completed_session', 'message'),
    [
        (
            lambda rows: rows[0].update(date='2026-08-03'),
            '2026-08-03',
            '2026-08-05',
            'not after local last_date',
        ),
        (
            lambda rows: rows[1].update(date='2026-08-04'),
            '2026-08-03',
            '2026-08-05',
            'strictly ascending and unique',
        ),
        (
            lambda rows: rows[0].update(open=float('nan')),
            '2026-08-03',
            '2026-08-05',
            'finite numeric data',
        ),
        (
            lambda rows: rows[0].update(volume=-1),
            '2026-08-03',
            '2026-08-05',
            'nonnegative',
        ),
        (
            lambda rows: rows[0].update(volume=1.5),
            '2026-08-03',
            '2026-08-05',
            'volume must be an integer',
        ),
        (
            lambda rows: rows[0].update(low=203),
            '2026-08-03',
            '2026-08-05',
            'not internally ordered',
        ),
        (
            lambda rows: rows[1].update(date='2026-08-06'),
            '2026-08-03',
            '2026-08-05',
            'after completed_session',
        ),
        (
            lambda rows: rows.pop(),
            '2026-08-03',
            '2026-08-05',
            'does not equal completed_session',
        ),
    ],
)
def test_recovery_rejects_stale_duplicate_invalid_and_future_rows(
    mutate,
    last_date,
    completed_session,
    message,
):
    payload = copy.deepcopy(VALID_EODHD_ROWS)
    mutate(payload)

    with pytest.raises(updater.RecoveryValidationError, match=message):
        updater.validate_eodhd_recovery_rows(
            payload,
            last_date,
            completed_session,
        )


def test_recovery_transport_retries_are_bounded_and_secret_safe(
    monkeypatch,
    capsys,
):
    secret = 'never-print-this-token'
    calls = []
    sleeps = []
    monkeypatch.setattr(updater.config, 'EOD_token', secret)

    def timeout(url, **kwargs):
        calls.append((url, kwargs))
        raise requests.Timeout(f'failed URL containing {secret}')

    monkeypatch.setattr(updater.requests, 'get', timeout)
    monkeypatch.setattr(updater.time, 'sleep', sleeps.append)

    assert updater.fetch_eodhd_recovery_rows(
        'BRK-B',
        '2026-08-04',
        '2026-08-05',
    ) is None
    assert len(calls) == updater.EODHD_RECOVERY_RETRIES
    assert sleeps == [2, 4]
    assert all(call[1]['timeout'] == (5, 30) for call in calls)
    assert all(call[1]['allow_redirects'] is False for call in calls)
    assert secret not in capsys.readouterr().out


def test_recovery_does_not_retry_permanent_http_error(monkeypatch):
    calls = []
    sleeps = []
    monkeypatch.setattr(updater.config, 'EOD_token', 'secret')
    monkeypatch.setattr(
        updater.requests,
        'get',
        lambda *args, **kwargs: calls.append((args, kwargs))
        or _Response({'error': 'unauthorized'}, status_code=401),
    )
    monkeypatch.setattr(updater.time, 'sleep', sleeps.append)

    assert updater.fetch_eodhd_recovery_rows(
        'BRK-B',
        '2026-08-04',
        '2026-08-05',
    ) is None
    assert len(calls) == 1
    assert sleeps == []


def test_recovery_rejects_partial_bootstrap(monkeypatch):
    monkeypatch.setattr(updater.config, 'EOD_token', 'secret')
    monkeypatch.setattr(
        updater.requests,
        'get',
        lambda *args, **kwargs: _Response(
            [copy.deepcopy(VALID_EODHD_ROWS[-1])]
        ),
    )

    assert updater.fetch_eodhd_recovery_rows(
        'BRK-B',
        '1800-01-01',
        '2026-08-05',
    ) is None


def test_recovery_adjustment_matches_real_brk_b_pre_split_shape():
    rows = updater.validate_eodhd_recovery_rows(
        [
            {
                'date': '1997-01-02',
                'open': 1110,
                'high': 1110,
                'low': 1095,
                'close': 1097,
                'adjusted_close': 21.94,
                'volume': 385000,
            }
        ],
        '1997-01-01',
        '1997-01-02',
    )

    assert rows[0][0] == '1997-01-02'
    assert rows[0][1:5] == pytest.approx([22.2, 22.2, 21.9, 21.94])
    assert rows[0][5] == 385000
    assert rows[0][6] == pytest.approx(0.02)
