#!/usr/bin/env python3
"""
daily_pattern_picks.py
======================
Selects top ML-scored seasonal pattern picks by calling the ML scorer's
/select endpoint on keyprovider.

Usage as module:
    from daily_pattern_picks import get_daily_picks
    picks = get_daily_picks(
        date='2026-03-17',
        resource_ids=['2', '11'],
        num_picks=1,
        direction='l',
        days_out_min=10,
        days_out_max=30,
        min_avg_return=5.0,
        min_win_prob=0.80,
        exclude_symbols=['AAPL'],
    )

Smoke test (just run it):
    python daily_pattern_picks.py
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
_APPSERVER_DIR = _REPO_ROOT / 'appserver' / 'appserver'
if str(_APPSERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_APPSERVER_DIR))
import config
from data_updater.eod_readiness import latest_completed_us_equity_session
from ml_checkpoint_context import (
    daily_pick_identity_from_health,
    scorer_health_mode,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)


def load_authoritative_eod_marker():
    """Load the EOD success marker the daily pick may trust.

    A local ``TW2_EOD_UPDATE_STATUS_FILE`` (default
    ``/var/lib/tradewave/eod/update_status.json``) wins when it exists, which
    is the single-box dev layout. Split web/app production has no local copy,
    so the appserver ``/internal/eod-status`` route is the same marker.
    """
    path = os.environ.get(
        'TW2_EOD_UPDATE_STATUS_FILE',
        '/var/lib/tradewave/eod/update_status.json',
    )
    if path and os.path.isfile(path):
        with open(path, encoding='utf-8') as handle:
            marker = json.load(handle)
        if not isinstance(marker, dict):
            raise RuntimeError('Daily pick deferred: EOD status is invalid')
        return marker
    return _fetch_appserver_eod_marker()


def _fetch_appserver_eod_marker():
    base_url = str(getattr(config, 'appserver_url', '') or '').rstrip('/')
    key = getattr(config, 'SERVICE_API_KEY', '') or ''
    if not base_url or not key:
        raise RuntimeError(
            'Daily pick deferred: scorer data through None does not cover '
            'completed session (EOD status is unavailable)')
    try:
        login = requests.post(
            base_url + '/login/api',
            headers={'X-Service-Key': key},
            timeout=10,
        )
        login.raise_for_status()
        token = (login.json() or {}).get('token')
        if not token:
            raise RuntimeError('appserver service login failed')
        response = requests.get(
            base_url + '/internal/eod-status',
            params={'token': token},
            timeout=10,
        )
        response.raise_for_status()
        marker = response.json()
    except Exception:
        # Do not chain the requests error: its URL can carry the service token.
        raise RuntimeError(
            'Daily pick deferred: scorer data through None does not cover '
            'completed session (EOD status is unavailable)') from None
    if not isinstance(marker, dict):
        raise RuntimeError('Daily pick deferred: EOD status is invalid')
    return marker


def current_pick_data_identity():
    """Require the same completed session as the existing EOD publication gate.

    Check both sides of selection: a refresh or model restart during a request
    must not produce a new public pick with mixed provenance.

    V3 scorer health carries that proof itself. V2 health does not, so the
    model contract is the shared ``_legacy_v2_metadata`` identity and the
    session proof is the validated EOD success marker. A pick is never
    published from the V2 cache placeholders alone.
    """
    expected = latest_completed_us_equity_session().isoformat()
    response = requests.get(f'{config.ml_scorer_url.rstrip("/")}/health', timeout=10)
    response.raise_for_status()
    payload = response.json()
    marker = None
    if scorer_health_mode(payload) == 'v2':
        marker = load_authoritative_eod_marker()
    return daily_pick_identity_from_health(
        payload,
        scorer_url=config.ml_scorer_url,
        completed_session=expected,
        eod_marker=marker,
    )


def get_daily_picks(date, resource_ids, num_picks, direction, days_out_min,
                    days_out_max, min_avg_return, min_win_prob,
                    exclude_symbols=None):
    """
    Get top ML-scored pattern picks for a given date.

    Args:
        date: str 'YYYY-MM-DD'
        resource_ids: list of market IDs to search (e.g. ['2', '11'])
        num_picks: int, number of picks to return (0 = all qualifying)
        direction: 'l' for long, 's' for short, 'both'
        days_out_min: minimum holding period in days
        days_out_max: maximum holding period in days
        min_avg_return: minimum historical avg_profit percentage
        min_win_prob: minimum ML win probability (e.g. 0.80)
        exclude_symbols: list of symbols to skip (optional)

    Returns:
        dict with 'picks' list and metadata from ML scorer
    """
    identity = current_pick_data_identity()
    payload = {
        'date': date,
        'resource_ids': [str(r) for r in resource_ids],
        'num_picks': num_picks,
        'direction': direction,
        'days_out_min': days_out_min,
        'days_out_max': days_out_max,
        'min_avg_return': min_avg_return,
        'min_win_prob': min_win_prob,
        'exclude_symbols': exclude_symbols or [],
    }

    url = f'{config.ml_scorer_url}/select'
    log.info(f'Calling {url} for {date}, {len(resource_ids)} markets, '
             f'{direction} {days_out_min}-{days_out_max}d, min_ret={min_avg_return}%, '
             f'min_wp={min_win_prob:.0%}, num_picks={num_picks}')

    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    if current_pick_data_identity() != identity:
        raise RuntimeError('Daily pick deferred: model or data changed during selection')
    result['metadata'] = identity

    log.info(f'Pre-filter: {result.get("candidates_after_prefilter", 0)}, '
             f'scored: {result.get("candidates_scored", 0)}, '
             f'qualifying: {result.get("candidates_passing_win_prob", 0)}, '
             f'picks: {len(result.get("picks", []))}, '
             f'elapsed: {result.get("elapsed_ms", 0):.0f}ms')

    return result


def _print_table(result):
    """Print picks as a formatted table."""
    picks = result.get('picks', [])
    if not picks:
        print('No qualifying picks found.')
        return

    print(f'\n{"#":<4} {"Dir":<4} {"Symbol":<8} {"Days":<5} {"WinPr":<7} '
          f'{"PrRet":<7} {"PrMFE":<7} {"AvgPr":<7} {"AvgPr2":<7} '
          f'{"SR":<6} {"SR2":<6} {"ML":<5}')
    print('-' * 78)
    for i, p in enumerate(picks, 1):
        d = 'L' if p['direction'] == 'l' else 'S'
        print(f'{i:<4} {d:<4} {p["symbol"]:<8} {p["daysOut"]:<5} '
              f'{p["win_prob"]:<7.1%} {p["pred_return"]:<7.1f} '
              f'{p["pred_mfe"]:<7.1f} {p["avg_profit"]:<7.1f} '
              f'{p["avg_profit2"]:<7.1f} {p["sharpe_ratio"]:<6.2f} '
              f'{p["sharpe_ratio2"]:<6.2f} {p["ml_score"]:<5.1f}')

    print(f'\nCandidates: {result.get("candidates_after_prefilter", 0)} pre-filter, '
          f'{result.get("candidates_scored", 0)} scored, '
          f'{result.get("candidates_passing_win_prob", 0)} qualifying')
    print(f'Elapsed: {result.get("elapsed_ms", 0):.0f}ms')


# =============================================================================
# Smoke test: just run the script to see all qualifying picks for today
# =============================================================================

if __name__ == '__main__':
    # Find next weekday (today if weekday, else next Monday)
    today = date.today()
    if today.weekday() >= 5:  # Saturday or Sunday
        today = today + timedelta(days=(7 - today.weekday()))
    target = today.strftime('%Y-%m-%d')

    print(f'Daily Pattern Picks - {target}')
    print(f'ML Scorer: {config.ml_scorer_url}')
    print('=' * 78)

    result = get_daily_picks(
        date=target,
        resource_ids=['2'],         # S&P 500
        num_picks=0,                # all qualifying
        direction='both',           # long and short
        days_out_min=10,
        days_out_max=30,
        min_avg_return=5.0,
        min_win_prob=0.75,
    )

    _print_table(result)
