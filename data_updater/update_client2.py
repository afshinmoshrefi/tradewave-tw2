# update_client2.py
# This flask app will fetch data from a mounted update_server URL 
# The client's IP should be enabled in nginx conf file like it was on keyprovider
# Run this daily or weekdays with crontab on appservers
#
# Version 1.6 - Added fail-closed BRK-B-only EODHD recovery for a missing central file
# Version 1.5 - Added holiday-aware US/ETF population readiness proof
# Version 1.4 - Added post-market timestamp adjustment (file date set to next day if run 4:01 PM - 11:59 PM NY)
# Version 1.3 - Added retry logic, timeout, error handling, summary
# Version 1.2 - Uses the new format of data where csvs are stored per exchange

import requests
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import datetime
from datetime import timedelta
import pytz
import pandas as pd
from os import listdir
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import config
from data_updater.eod_readiness import (
    NY_TZ,
    build_status_marker,
    evaluate_eod_readiness,
    latest_completed_us_equity_session,
    target_table_date,
    terminal_row_fingerprint,
    validate_success_marker,
)


data_dir = config.ddir
csv_dir = config.csv_folder

csv_columns = ['date', 'open', 'high', 'low', 'close','volume', 'adj_factor']

# Retry settings
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff base
LEGACY_RESOURCE_SYMBOLS = {
    # Some mutable resource CSVs still use the old dotted spelling.  TradeWave
    # filenames and update-server routes use the canonical hyphenated symbol.
    'BRK.B': 'BRK-B',
}
# Recovery is deliberately narrower than manifest normalization.  Adding a
# future legacy spelling must not silently authorize a direct vendor fallback.
CANONICAL_MIGRATION_SYMBOLS = frozenset({'BRK-B'})
EODHD_RECOVERY_BOOTSTRAP_POLICY = {
    # The verified BRK-B corpus begins in 1997 and contains more than 7,000
    # daily rows.  These looser floors reject a partial response without tying
    # the bridge to an exact vendor row count.
    'BRK-B': {
        'minimum_rows': 5000,
        'latest_first_date': '2000-01-01',
    },
}
if not CANONICAL_MIGRATION_SYMBOLS.issubset(
    frozenset(LEGACY_RESOURCE_SYMBOLS.values())
) or set(EODHD_RECOVERY_BOOTSTRAP_POLICY) != set(CANONICAL_MIGRATION_SYMBOLS):
    raise RuntimeError('canonical recovery scope is not explicitly configured')
EODHD_RECOVERY_BASE_URL = 'https://eodhistoricaldata.com/api/eod'
EODHD_RECOVERY_TIMEOUT = (5, 30)
EODHD_RECOVERY_RETRIES = 3
_STRICT_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
STATUS_FILE = os.environ.get(
    'TW2_EOD_UPDATE_STATUS_FILE',
    '/var/lib/tradewave/eod/update_status.json',
)
def utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def market_date(now=None):
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = NY_TZ.localize(current)
    return current.astimezone(NY_TZ).date().isoformat()


def canonical_resource_symbol(value):
    """Return the canonical TradeWave symbol for one resource-manifest value."""

    symbol = str(value).strip().upper()
    return LEGACY_RESOURCE_SYMBOLS.get(symbol, symbol)


def symbol_csv_path(exchange_csv_folder, symbol):
    """Build a local CSV path without leaking a legacy manifest spelling."""

    canonical_symbol = canonical_resource_symbol(symbol)
    return os.path.join(exchange_csv_folder, f'{canonical_symbol}.csv')


def request_symbol_update(resource_id, symbol, last_date):
    """Request an update-server payload under the canonical TradeWave symbol."""

    canonical_symbol = canonical_resource_symbol(symbol)
    url = (
        f'{config.update_server}update/{resource_id}/'
        f'{canonical_symbol}/{last_date}'
    )
    return get_update_with_retry(url)


def write_symbol_csv(frame, exchange_csv_folder, symbol):
    """Write one symbol frame to its canonical TradeWave filename."""

    csv_path = symbol_csv_path(exchange_csv_folder, symbol)
    temporary = f'{csv_path}.tmp.{os.getpid()}'
    try:
        frame.to_csv(temporary)
        os.replace(temporary, csv_path)
        set_file_date_tomorrow_if_post_market(csv_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return csv_path


class RecoveryValidationError(ValueError):
    """A secret-free validation failure for a bounded EODHD recovery."""


def _recovery_date(value, field_name):
    if not isinstance(value, str) or not _STRICT_ISO_DATE.fullmatch(value):
        raise RecoveryValidationError(f'{field_name} must be a strict ISO date')
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise RecoveryValidationError(
            f'{field_name} must be a valid ISO date'
        ) from exc
    if parsed.isoformat() != value:
        raise RecoveryValidationError(f'{field_name} must be a strict ISO date')
    return parsed


def _recovery_number(value, field_name, *, allow_zero=False):
    if isinstance(value, bool):
        raise RecoveryValidationError(f'{field_name} must be finite numeric data')
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RecoveryValidationError(
            f'{field_name} must be finite numeric data'
        ) from exc
    if not math.isfinite(number):
        raise RecoveryValidationError(f'{field_name} must be finite numeric data')
    if number < 0 or (number == 0 and not allow_zero):
        qualifier = 'nonnegative' if allow_zero else 'positive'
        raise RecoveryValidationError(f'{field_name} must be {qualifier}')
    return number


def validate_eodhd_recovery_rows(payload, last_date, completed_session):
    """Validate and adjust a bounded canonical-symbol EODHD response.

    The response is rejected as a whole.  It is never sorted, deduplicated, or
    clipped because doing so could hide a stale, malformed, or future row.
    """

    last_day = _recovery_date(str(last_date), 'local last_date')
    completed_day = (
        completed_session
        if isinstance(completed_session, datetime.date)
        else _recovery_date(str(completed_session), 'completed_session')
    )
    if not isinstance(payload, list) or not payload:
        raise RecoveryValidationError('response must contain at least one row')

    adjusted_rows = []
    previous_day = None
    for row in payload:
        if not isinstance(row, dict):
            raise RecoveryValidationError('each response row must be an object')
        day = _recovery_date(row.get('date'), 'row date')
        if day <= last_day:
            raise RecoveryValidationError('row date is not after local last_date')
        if day > completed_day:
            raise RecoveryValidationError('row date is after completed_session')
        if previous_day is not None and day <= previous_day:
            raise RecoveryValidationError(
                'row dates must be strictly ascending and unique'
            )

        raw_open = _recovery_number(row.get('open'), 'open')
        raw_high = _recovery_number(row.get('high'), 'high')
        raw_low = _recovery_number(row.get('low'), 'low')
        raw_close = _recovery_number(row.get('close'), 'close')
        adjusted_close = _recovery_number(
            row.get('adjusted_close'),
            'adjusted_close',
        )
        volume = _recovery_number(
            row.get('volume'),
            'volume',
            allow_zero=True,
        )
        if not volume.is_integer():
            raise RecoveryValidationError('volume must be an integer')
        if not (
            raw_low <= raw_open <= raw_high
            and raw_low <= raw_close <= raw_high
        ):
            raise RecoveryValidationError('OHLC values are not internally ordered')
        adjustment_factor = adjusted_close / raw_close
        adjusted_ohlc = [
            raw_open * adjustment_factor,
            raw_high * adjustment_factor,
            raw_low * adjustment_factor,
            adjusted_close,
        ]
        if (
            not math.isfinite(adjustment_factor)
            or adjustment_factor <= 0
            or any(not math.isfinite(value) or value <= 0 for value in adjusted_ohlc)
        ):
            raise RecoveryValidationError('adjusted OHLC data is invalid')

        adjusted_rows.append(
            [
                day.isoformat(),
                *adjusted_ohlc,
                int(volume),
                adjustment_factor,
            ]
        )
        previous_day = day

    if previous_day != completed_day:
        raise RecoveryValidationError(
            'terminal row date does not equal completed_session'
        )

    return adjusted_rows


def read_success_marker(
    path,
    expected_target_table_date,
    expected_completed_session,
):
    try:
        with open(path, encoding='utf-8') as handle:
            value = json.load(handle)
        if validate_success_marker(
            value,
            expected_target_table_date=expected_target_table_date,
            expected_completed_session=expected_completed_session,
        ):
            return value
    except (OSError, ValueError):
        pass
    return None


def terminal_observation(frame, state):
    """Return stable terminal-row evidence for one supported target file."""

    if frame is None or frame.empty:
        return {'state': state}
    row = frame[csv_columns].iloc[-1]
    return {
        'state': state,
        'terminal_date': str(row['date']),
        'terminal_row_fingerprint': terminal_row_fingerprint(
            [row[column] for column in csv_columns]
        ),
    }


def write_status_marker(path, payload):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = f'{path}.tmp.{os.getpid()}'
    try:
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_ml_score_prefetch(status_path):
    """Run the idempotent warmer without changing authoritative EOD success."""

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prefetch_ml_scores.py')
    if not os.path.isfile(script):
        print(f'ML prefetch skipped: {script} is missing')
        return False
    try:
        completed = subprocess.run(
            [sys.executable, script, '--status-file', status_path],
            check=False,
            timeout=45 * 60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'ML prefetch failed to run: {type(exc).__name__}')
        return False
    if completed.returncode != 0:
        print(
            'ML prefetch did not publish a complete generation; '
            'the next marker-gated hourly run will retry.'
        )
        return False
    return True

#-----------------------------------------------------------------------------
# POST-MARKET TIMESTAMP FUNCTIONS
#-----------------------------------------------------------------------------

def is_post_market_hours():
    """Check if current time is between 4:01 PM and 11:59 PM New York time."""
    ny_tz = pytz.timezone('America/New_York')
    ny_now = datetime.datetime.now(ny_tz)
    
    # 4:01 PM = 16:01, 11:59 PM = 23:59
    start_time = datetime.time(16, 1)
    end_time = datetime.time(23, 59)
    
    return start_time <= ny_now.time() <= end_time

def set_file_date_tomorrow_if_post_market(filepath):
    """If running in post-market hours, set file's modification date to tomorrow."""
    if is_post_market_hours():
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        # Set to midnight tomorrow
        tomorrow_timestamp = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        os.utime(filepath, (tomorrow_timestamp, tomorrow_timestamp))

#-----------------------------------------------------------------------------
def get_update_with_retry(url, retries=MAX_RETRIES):
    """
    Fetch update data with timeout and automatic retry on failure.
    
    Args:
        url: The update server URL to fetch
        retries: Number of retry attempts
    
    Returns:
        dict: The JSON response, or None if all retries failed
    """
    for attempt in range(retries):
        try:
            result = requests.get(url, timeout=REQUEST_TIMEOUT)
            result.raise_for_status()  # Raise exception for 4xx/5xx status codes
            return result.json()
        except requests.exceptions.Timeout:
            print(f'  Timeout on attempt {attempt + 1}/{retries}')
        except requests.exceptions.ConnectionError:
            print(f'  Connection error on attempt {attempt + 1}/{retries}')
        except requests.exceptions.RequestException as e:
            print(f'  Request error on attempt {attempt + 1}/{retries}: {e}')
        except ValueError as e:  # JSON decode error
            print(f'  Invalid JSON response on attempt {attempt + 1}/{retries}')
        
        # Wait before retry (exponential backoff: 2s, 4s, 8s)
        if attempt < retries - 1:
            wait_time = RETRY_BACKOFF ** (attempt + 1)
            time.sleep(wait_time)
    
    return None


def fetch_eodhd_recovery_rows(symbol, last_date, completed_session):
    """Fetch one explicitly canonical migration symbol from EODHD.

    The token is passed only as a request parameter and neither the request URL,
    parameters, response body, nor exception text is logged.
    """

    if symbol not in CANONICAL_MIGRATION_SYMBOLS:
        return None
    token = str(getattr(config, 'EOD_token', '') or '').strip()
    if not token:
        print(f'  EODHD recovery unavailable for {symbol}: credential not configured')
        return None

    try:
        last_day = _recovery_date(str(last_date), 'local last_date')
        completed_day = (
            completed_session
            if isinstance(completed_session, datetime.date)
            else _recovery_date(str(completed_session), 'completed_session')
        )
    except RecoveryValidationError as exc:
        print(f'  EODHD recovery rejected for {symbol}: {exc}')
        return None

    if last_day > completed_day:
        print(f'  EODHD recovery rejected for {symbol}: local date is in the future')
        return None
    if last_day == completed_day:
        return []

    url = f'{EODHD_RECOVERY_BASE_URL}/{symbol}.US'
    params = {
        'api_token': token,
        'period': 'd',
        'fmt': 'json',
        'order': 'a',
        'from': (last_day + datetime.timedelta(days=1)).isoformat(),
        'to': completed_day.isoformat(),
    }
    for attempt in range(EODHD_RECOVERY_RETRIES):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=EODHD_RECOVERY_TIMEOUT,
                allow_redirects=False,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            print(
                f'  EODHD recovery request failed for {symbol} '
                f'({type(exc).__name__}) attempt '
                f'{attempt + 1}/{EODHD_RECOVERY_RETRIES}'
            )
            if attempt < EODHD_RECOVERY_RETRIES - 1:
                time.sleep(RETRY_BACKOFF ** (attempt + 1))
            continue
        except requests.exceptions.RequestException as exc:
            print(
                f'  EODHD recovery request failed for {symbol} '
                f'({type(exc).__name__}); not retrying'
            )
            return None

        try:
            status_code = int(response.status_code)
        except (AttributeError, TypeError, ValueError):
            print(f'  EODHD recovery rejected for {symbol}: invalid HTTP status')
            return None
        if status_code == 429 or 500 <= status_code <= 599:
            print(
                f'  EODHD recovery request failed for {symbol} '
                f'(HTTP {status_code}) attempt '
                f'{attempt + 1}/{EODHD_RECOVERY_RETRIES}'
            )
            if attempt < EODHD_RECOVERY_RETRIES - 1:
                time.sleep(RETRY_BACKOFF ** (attempt + 1))
            continue
        if not 200 <= status_code <= 299:
            print(
                f'  EODHD recovery rejected for {symbol}: '
                f'HTTP {status_code}; not retrying'
            )
            return None
        try:
            payload = response.json()
        except ValueError:
            print(f'  EODHD recovery rejected for {symbol}: invalid JSON response')
            return None

        try:
            rows = validate_eodhd_recovery_rows(
                payload,
                last_day.isoformat(),
                completed_day,
            )
        except RecoveryValidationError as exc:
            print(f'  EODHD recovery rejected for {symbol}: {exc}')
            return None

        if last_day.isoformat() == '1800-01-01':
            policy = EODHD_RECOVERY_BOOTSTRAP_POLICY.get(symbol)
            first_day = datetime.date.fromisoformat(rows[0][0])
            if (
                policy is None
                or len(rows) < int(policy['minimum_rows'])
                or first_day
                > datetime.date.fromisoformat(policy['latest_first_date'])
            ):
                print(
                    f'  EODHD recovery rejected for {symbol}: '
                    'full-history bootstrap proof failed'
                )
                return None
        return rows

    return None


def recover_source_missing_update(
    update_server_result,
    *,
    symbol,
    exchange,
    last_date,
    completed_session,
):
    """Recover only an explicit canonical symbol after a source-missing reply.

    Returns ``(attempted, rows)``.  ``rows is None`` means an attempted
    recovery failed validation or transport and must fail the nightly run.
    """

    if not isinstance(update_server_result, dict):
        return False, None
    update_value = update_server_result.get('update')
    if not (
        isinstance(update_value, str)
        and update_value.lower().startswith('file missing:')
    ):
        return False, None
    if exchange != 'US' or symbol not in CANONICAL_MIGRATION_SYMBOLS:
        return False, None
    rows = fetch_eodhd_recovery_rows(symbol, last_date, completed_session)
    return True, rows

#-----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--force',
        action='store_true',
        help='run even if today already has a successful completion marker',
    )
    args = parser.parse_args()
    run_now = datetime.datetime.now(datetime.timezone.utc)
    current_market_date = market_date(run_now)
    current_target_table_date = target_table_date(run_now).isoformat()
    completed_session = latest_completed_us_equity_session(run_now)
    completed_session_iso = completed_session.isoformat()
    if not args.force:
        existing_marker = read_success_marker(
            STATUS_FILE,
            current_target_table_date,
            completed_session_iso,
        )
        if existing_marker:
            print(
                'EOD appserver sync already completed for '
                f'table date {current_target_table_date} '
                f'(session {completed_session_iso}) at '
                f'{existing_marker.get("completed_at")}'
            )
            # A prior EOD pull may have succeeded while its bounded warm failed.
            # Re-enter the idempotent warmer on each hourly marker no-op so it
            # retries without downloading the market data again.
            run_ml_score_prefetch(STATUS_FILE)
            raise SystemExit(0)

    started_at = run_now.isoformat()
    print('update client version 1.6')
    print(f'Started at {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Expected completed US session: {completed_session_iso}')
    print(f'Target opportunity-table date: {current_target_table_date}')
    print()

    # Counters for summary
    total_symbols = 0
    updated_count = 0
    recovered_count = 0
    skipped_count = 0
    failed_count = 0
    missing_count = 0  # symbol not on server
    observations = {}
    readiness_targets = {'US': set(), 'ETF': set()}
    ml_resource_ids = {str(value) for value in config.ml_score_resource_ids}

    exchange_resources = {}
    for resource_id, exchange in config.exchange_mapping.items():
        exchange_resources.setdefault(exchange, []).append(str(resource_id))

    for exchange in sorted(exchange_resources):
        exchange_csv_folder = config.csv_folder + exchange + '/'
        if not os.path.exists(exchange_csv_folder):
            os.makedirs(exchange_csv_folder)
        print(f'Processing exchange: {exchange}')

        symbols = []
        for resource_id in exchange_resources[exchange]:
            try:
                resource_frame = pd.read_csv(
                    config.available_resources_path[resource_id]
                )
                resource_symbols = [
                    canonical_resource_symbol(item)
                    for item in resource_frame['symbols'].tolist()
                    if str(item).strip()
                ]
                symbols.extend(resource_symbols)
                if resource_id in ml_resource_ids and exchange in readiness_targets:
                    readiness_targets[exchange].update(
                        symbol for symbol in resource_symbols if '.' not in symbol
                    )
            except Exception as e:
                print(f'  Error reading resource file for {resource_id}: {e}')
                failed_count += 1

        # Resource lists overlap heavily (for example AAPL is in several US
        # lists).  One target/file request is sufficient and gives the marker a
        # deterministic scope.
        slist = list(dict.fromkeys(symbols))
        readiness_target_set = readiness_targets.get(exchange, set())
        resource_id = exchange_resources[exchange][0]
        exchange_updated = 0
        exchange_failed = 0

        for c, s in enumerate(slist, 1):
            total_symbols += 1
            is_readiness_target = s in readiness_target_set
            observation_key = f'{exchange}:{s}'

            # Known supported share classes (currently BRK-B) are canonicalized
            # when the resource manifest is read.  Other dotted source symbols
            # remain outside this updater's supported target set.
            if '.' in s:
                skipped_count += 1
                continue

            csv_path = symbol_csv_path(exchange_csv_folder, s)
            exists = os.path.isfile(csv_path)
            last_date = '1800-01-01'  # get all data from 1800 if available
            df_existing = None

            if exists:
                try:
                    df_existing = pd.read_csv(csv_path)
                    df_existing = df_existing[csv_columns]
                    if df_existing.shape[0] == 0:
                        skipped_count += 1
                        if is_readiness_target:
                            observations[observation_key] = {
                                'state': 'empty_local_file'
                            }
                        continue
                    last_date = str(df_existing['date'].iloc[-1])
                except Exception as e:
                    print(f'  Error reading {csv_path}: {e}')
                    failed_count += 1
                    exchange_failed += 1
                    if is_readiness_target:
                        observations[observation_key] = {
                            'state': 'local_read_failed'
                        }
                    continue

            result = request_symbol_update(resource_id, s, last_date)

            if result is None:
                print(f'  FAILED: {s} - could not fetch from server')
                failed_count += 1
                exchange_failed += 1
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_existing,
                        'request_failed',
                    )
                continue

            if not isinstance(result, dict) or 'update' not in result:
                print(f'  FAILED: {s} - invalid update-server response')
                failed_count += 1
                exchange_failed += 1
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_existing,
                        'invalid_response',
                    )
                continue

            update_rows = result['update']
            recovered_update = False
            if isinstance(update_rows, str) and update_rows.lower().startswith(
                'file missing:'
            ):
                missing_count += 1
                recovery_attempted, recovery_rows = recover_source_missing_update(
                    result,
                    symbol=s,
                    exchange=exchange,
                    last_date=last_date,
                    completed_session=completed_session,
                )
                if recovery_attempted and recovery_rows is None:
                    print(f'  FAILED: {s} - canonical recovery was not verified')
                    failed_count += 1
                    exchange_failed += 1
                    if is_readiness_target:
                        observations[observation_key] = terminal_observation(
                            df_existing,
                            'recovery_failed',
                        )
                    continue
                if recovery_attempted:
                    update_rows = recovery_rows
                    recovered_update = bool(recovery_rows)
                else:
                    if is_readiness_target:
                        observations[observation_key] = terminal_observation(
                            df_existing,
                            'source_missing',
                        )
                    continue

            if not isinstance(update_rows, list):
                print(f'  FAILED: {s} - update rows are not a list')
                failed_count += 1
                exchange_failed += 1
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_existing,
                        'invalid_response',
                    )
                continue

            if len(update_rows) == 0:
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_existing,
                        'verified',
                    )
                continue

            try:
                dfu = pd.DataFrame(update_rows, columns=csv_columns)
                if exists and df_existing is not None:
                    df_final = pd.concat([df_existing, dfu]).reset_index(drop=True)
                else:
                    df_final = dfu
                write_symbol_csv(df_final, exchange_csv_folder, s)
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_final,
                        'verified',
                    )
                updated_count += 1
                if recovered_update:
                    recovered_count += 1
                exchange_updated += 1
                action = 'Recovered' if recovered_update else 'Updated'
                print(f'  {c}/{len(slist)} {action}: {s} (+{len(dfu)} rows)')
            except Exception as e:
                print(f'  Error saving {s}: {e}')
                failed_count += 1
                exchange_failed += 1
                if is_readiness_target:
                    observations[observation_key] = terminal_observation(
                        df_existing,
                        'local_write_failed',
                    )

        print(f'  {exchange}: {exchange_updated} updated, {exchange_failed} failed')
        print()

    readiness = evaluate_eod_readiness(
        targets_by_exchange={
            exchange: sorted(symbols)
            for exchange, symbols in readiness_targets.items()
        },
        observations=observations,
        completed_session=completed_session,
        resource_ids=sorted(ml_resource_ids, key=int),
    )
    valid_us_dates = []
    for key, observation in observations.items():
        if not key.startswith('US:'):
            continue
        try:
            valid_us_dates.append(
                datetime.date.fromisoformat(
                    str(observation.get('terminal_date'))
                ).isoformat()
            )
        except (TypeError, ValueError):
            continue
    latest_us_date = max(valid_us_dates) if valid_us_dates else None

    print('=' * 50)
    print('SUMMARY')
    print('=' * 50)
    print(f'Total unique symbols processed: {total_symbols}')
    print(f'Updated:  {updated_count}')
    print(f'Recovered: {recovered_count} (bounded canonical EODHD fallback)')
    print(f'Skipped:  {skipped_count}')
    print(f'Missing:  {missing_count} (not on server)')
    print(f'Failed:   {failed_count}')
    for exchange in ('US', 'ETF'):
        summary = readiness['coverage']['exchanges'][exchange]
        print(
            f'{exchange} readiness: {summary["complete_count"]}/'
            f'{summary["recent_count"]} recent targets on '
            f'{completed_session_iso}; population coverage '
            f'{summary["recent_coverage_ratio"]:.1%}; ready={summary["ready"]}'
        )
    print(f'Finished at {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    status = build_status_marker(
        base={
            'started_at': started_at,
            'completed_at': utc_now_iso(),
            'market_date': current_market_date,
            'target_table_date': current_target_table_date,
            'latest_us_date': latest_us_date,
            'total': total_symbols,
            'updated': updated_count,
            'skipped': skipped_count,
            'missing': missing_count,
            'failed': failed_count,
            'source': str(config.update_server),
        },
        readiness=readiness,
    )
    sync_ok = status['ok']
    write_status_marker(STATUS_FILE, status)
    print(
        f'Status marker: {STATUS_FILE} (ok={sync_ok}, '
        f'generation={status["generation_fingerprint"][:12]})'
    )
    if not sync_ok:
        raise SystemExit(1)
    run_ml_score_prefetch(STATUS_FILE)
