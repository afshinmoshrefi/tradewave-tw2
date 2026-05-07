# update_client2.py
# This flask app will fetch data from a mounted update_server URL 
# The client's IP should be enabled in nginx conf file like it was on keyprovider
# Run this daily or weekdays with crontab on appservers
#
# Version 1.4 - Added post-market timestamp adjustment (file date set to next day if run 4:01 PM - 11:59 PM NY)
# Version 1.3 - Added retry logic, timeout, error handling, summary
# Version 1.2 - Uses the new format of data where csvs are stored per exchange

import requests
import os
import sys
import time
import datetime
from datetime import timedelta
import pytz
import pandas as pd
from os import listdir
sys.path.insert(0, '/home/flask')
import config


data_dir = config.ddir
csv_dir = config.csv_folder

csv_columns = ['date', 'open', 'high', 'low', 'close','volume', 'adj_factor']

# Retry settings
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff base

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

#-----------------------------------------------------------------------------
if __name__ == "__main__":
    print('update client version 1.4')  # 1.4 adds post-market timestamp adjustment
    print(f'Started at {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    # Counters for summary
    total_symbols = 0
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    missing_count = 0  # symbol not on server

    exchange_list = list(set(config.exchange_mapping.values()))

    for exchange in exchange_list:

        # if exchange != 'US':continue # remove
        
        exchange_csv_folder = config.csv_folder + exchange + '/'
        if not os.path.exists(exchange_csv_folder):
            os.makedirs(exchange_csv_folder)
        print(f'Processing exchange: {exchange}')

        df = pd.DataFrame(columns=['symbols', 'name'])
        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                try:
                    df = pd.concat([df, pd.read_csv(config.available_resources_path[k])])
                except Exception as e:
                    print(f'  Error reading resource file for {k}: {e}')
                    continue
                    
        slist = list(df['symbols'])
        slist = [str(item) for item in slist]

        exchange_updated = 0
        exchange_failed = 0

        for c, s in enumerate(slist, 1):
            total_symbols += 1

            if '.' in s:  # skipping symbols like BRK.B for now
                skipped_count += 1
                continue

            csv_path = exchange_csv_folder + s + '.csv'
            exists = os.path.isfile(csv_path)
            last_date = '1800-01-01'  # get all data from 1800 if available
            
            if exists:
                try:
                    df_existing = pd.read_csv(csv_path)
                    df_existing = df_existing[csv_columns]  # cut those extra index columns
                    if df_existing.shape[0] == 0:
                        skipped_count += 1
                        continue  # there are no rows - ignore and continue
                    last_date = df_existing['date'].iloc[df_existing.shape[0] - 1]  # last date in existing dataset
                except Exception as e:
                    print(f'  Error reading {csv_path}: {e}')
                    failed_count += 1
                    continue

            # Find index number for resourceID. For US stocks could be any US stock resourceID
            resourceID = 0
            for i in config.exchange_mapping:
                if config.exchange_mapping[i] == exchange:
                    resourceID = i
                    break

            # Get the data from update_server with retry logic
            url = f'{config.update_server}update/{resourceID}/{s}/{last_date}'
            result = get_update_with_retry(url)
            
            # Handle failed request (all retries exhausted)
            if result is None:
                print(f'  FAILED: {s} - could not fetch from server')
                failed_count += 1
                exchange_failed += 1
                continue
            
            # Handle missing file on server
            if 'missing' in str(result.get('update', '')):
                missing_count += 1
                continue
            
            # Handle empty update (already up to date)
            if len(result['update']) == 0:
                continue
            
            # Apply update
            try:
                dfu = pd.DataFrame(result['update'], columns=csv_columns)
                if exists:
                    df_final = pd.concat([df_existing, dfu]).reset_index(drop=True)
                else:
                    df_final = dfu
                df_final.to_csv(csv_path)
                set_file_date_tomorrow_if_post_market(csv_path)
                updated_count += 1
                exchange_updated += 1
                print(f'  {c}/{len(slist)} Updated: {s} (+{len(dfu)} rows)')
            except Exception as e:
                print(f'  Error saving {s}: {e}')
                failed_count += 1
                exchange_failed += 1

        print(f'  {exchange}: {exchange_updated} updated, {exchange_failed} failed')
        print()

    # Print summary
    print('=' * 50)
    print('SUMMARY')
    print('=' * 50)
    print(f'Total symbols processed: {total_symbols}')
    print(f'Updated:  {updated_count}')
    print(f'Skipped:  {skipped_count} (symbols with dots)')
    print(f'Missing:  {missing_count} (not on server)')
    print(f'Failed:   {failed_count}')
    print(f'Finished at {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)