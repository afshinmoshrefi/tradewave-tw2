# get_symbol_csv(symbol,exchange)  will return the df for the csv - if it doesn't exist or if its old, it downloads it first  
# otherwise, it opens and returns the df with df.get_csv()  7/20/2025

import requests
import logging
import os, os.path
import pandas as pd
import json
import pwd
import sys
from datetime import datetime,date
from filelock import FileLock, Timeout as LockTimeout  # Added for locking - so that .csv is downloaded once - otherwise it download 6 times

logger = logging.getLogger()  # Uses the root logger already set up in your script

sys.path.insert(0, '/home/flask')
import config

token = config.EOD_token
cut_days = 223

# -----------------------------------------------------
# download from EOD
def get_sym_df(symbol, exchangeID):

  

    print('\ndownloading', symbol, 'from eodhistoricaldata.com')
    eid = exchangeID
    if eid == 'ETF': eid = 'US'

    if symbol == 'SPX':
        apiURL = f'https://eodhd.com/api/eod/GSPC.{eid}?api_token={token}&period=d&fmt=json' # SPX is really GSPC in EOD but I use SPX
    else:
        apiURL = f'https://eodhd.com/api/eod/{symbol.strip()}.{eid}?api_token={token}&period=d&fmt=json'


    try:
        # timeout: a hung EODHD download used to hold the FileLock indefinitely and
        # stall every other worker wanting this ticker
        api_result = requests.get(apiURL, timeout=(10, 60))
    except requests.exceptions.RequestException as e:
        print('exeption on download:')
        print('url=', apiURL)
        print('exception:', e)  # e.response is None for timeouts/connection errors - never deref it
        return pd.DataFrame()

    if api_result.status_code != 200:
        logger.warning(f"EODHD returned HTTP {api_result.status_code} for {symbol}.{eid}")
        return pd.DataFrame()

    if 'Not Found' in api_result.content.decode("utf-8"):
        print(symbol, 'not found')
        return pd.DataFrame()

    api_response = api_result.json()
    df = pd.DataFrame(api_response)
    return df
# -----------------------------------------------------------------------------------------
# use the adjusted_close to calculate a ratio - use the ratio to adjust open high low and close
def adjust(df): 
    df['adj_factor'] = df['adjusted_close'] / df['close']
    df['open'] = df['open'] * df['adj_factor']
    df['high'] = df['high'] * df['adj_factor']
    df['low'] = df['low'] * df['adj_factor']
    df['close'] = df['close'] * df['adj_factor']
    df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'adj_factor']]
    return df
# -----------------------------------------------------------------------------------------
# trim bad years with too many missing days - hopefully its very old years trimmed
def trim_df(dfs):
    y0 = int(dfs['date'].iloc[0][:4])               # first year in the dataset
    y1 = int(dfs['date'].iloc[dfs.shape[0]-1][:4])  # last year in the dataset
    years_dict = {}
    
    for y in range(y0+1, y1):
        df2 = dfs[dfs['date'].str[:4] == str(y)]
        days = df2.shape[0]
        years_dict[y] = days
        
    earliest_year_to_keep = 0
    years_list = list(years_dict.keys())[::-1]

    for y in years_list:
        if years_dict[y] < cut_days: break
        else: earliest_year_to_keep = y

    # cut the dataframe with the earliest_year_to_keep and throw older data out
    first_date_in_csv = str(earliest_year_to_keep) + '-01-01'
    df = dfs[dfs['date'] > first_date_in_csv]
    return df
#-----------------------------------------------------------------------
# find out how many days ago was the last row in the downloaded file
def days_ago_was_last_row(df):
     
    last_date = df.iloc[-1]['date']
    days_ago =  (date.today() - pd.to_datetime(df.iloc[-1]['date']).date()).days 
    return days_ago
# -----------------------------------------------------------------------------------------
# Modified 7/20/2025 to match CSV format of comprehensive downloader: adjust prices using adjusted_close, trim years with fewer than 223 trading days, include columns date, open, high, low, close, volume, adj_factor, and include index number column
# added filelock so that download happens once instead of 6 times
def get_symbol_csv(ticker, exchange):
    csv_folder = config.csv_folder + exchange + '/'
    if not os.path.exists(csv_folder):
        try:
            os.makedirs(csv_folder)
            logger.info(f"Created directory: {csv_folder}")
        except Exception as e:
            logger.error(f"Failed to create directory {csv_folder}: {e}", exc_info=True)
            return pd.DataFrame()

    output_file = os.path.join(csv_folder, f"{ticker}.csv")
    lock_file = output_file + ".lock"

    try:
        logger.info(f"Acquiring lock for {output_file}")
        with FileLock(lock_file, timeout=30):
            logger.info(f"Lock acquired for {output_file}")

            # 1) If today's CSV exists, read & return it
            # if os.path.exists(output_file):
            #     mtime = datetime.fromtimestamp(os.path.getmtime(output_file)).date()
            #     logger.info(f"{output_file} exists. Last modified: {mtime}")
            #     if mtime == datetime.now().date():
            #         try:
            #             df = pd.read_csv(output_file, index_col=0)
            #             logger.info(f"Loaded existing CSV for {ticker} ({exchange}), shape={df.shape}")
            #             return df
            #         except Exception as e:
            #             logger.error(f"Error reading CSV {output_file}: {e}", exc_info=True)
            #             # Fall through to download

            # 1) If CSV exists, check data freshness (skip download for custom symbols)
            if os.path.exists(output_file):
                # Never download custom spliced symbols - they're maintained by separate logic
                custom_symbols = ['LBR']  # Add other custom symbols here
                
                if ticker in custom_symbols:
                    logger.info(f"{ticker} is a custom symbol, loading without freshness check")
                    try:
                        df = pd.read_csv(output_file, index_col=0)
                        logger.info(f"Loaded existing CSV for {ticker} ({exchange}), shape={df.shape}")
                        return df
                    except Exception as e:
                        logger.error(f"Error reading CSV {output_file}: {e}", exc_info=True)
                        return pd.DataFrame()  # Don't download custom symbols
                
                # For regular symbols, check if data is fresh
                try:
                    df = pd.read_csv(output_file, index_col=0)
                    days_ago = days_ago_was_last_row(df)
                    logger.info(f"{ticker} data is {days_ago} days old")

                    # Market-day-aware freshness: Friday's data is still fresh on Sat/Sun/Mon
                    # weekday(): 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri 5=Sat 6=Sun
                    weekday = date.today().weekday()
                    if weekday == 5:   max_stale = 2  # Saturday - Friday data is 1 day old
                    elif weekday == 6: max_stale = 3  # Sunday - Friday data is 2 days old
                    elif weekday == 0: max_stale = 4  # Monday - Friday data is 3 days old
                    else:              max_stale = 2  # Tue–Fri - yesterday is acceptable

                    if days_ago <= max_stale:
                        logger.info(f"Data is fresh for {ticker} ({exchange}), shape={df.shape}")
                        return df
                    else:
                        logger.info(f"Data is {days_ago} days old for {ticker}, will download fresh data")
                        # Fall through to download
                except Exception as e:
                    logger.error(f"Error reading CSV {output_file}: {e}", exc_info=True)
                    # Fall through to download

    #-----------------------------------------------------------------------------------------------

            # 2) Download fresh data
            logger.info(f"Downloading fresh data for {ticker} ({exchange})")
            df = get_sym_df(ticker, exchange)


            if df.empty or df.shape[0] < 2 :
                logger.warning(f"No or insufficient data for {ticker} ({exchange}). DataFrame shape: {df.shape}")
                # If download failed but we have existing CSV data, return it (stale is better than nothing)
                if os.path.exists(output_file):
                    try:
                        stale_df = pd.read_csv(output_file, index_col=0)
                        if not stale_df.empty:
                            logger.info(f"Download failed, returning stale CSV for {ticker} ({exchange}), shape={stale_df.shape}")
                            return stale_df
                    except Exception:
                        pass
                return pd.DataFrame()

            # find out how many days ago was the last row in the downloaded file

            days_ago =  days_ago_was_last_row(df)
            if days_ago > config.max_days_missing : # typically set to 14 days - this stock would be not traded
                logger.warning(f"Last trading day for {ticker} ({exchange}) was {days_ago} days ago. DataFrame shape: {df.shape}")
                return f"Not Traded: Last trading day for {ticker} was {days_ago} days ago"

            # 3) Process data
            try:
                df = adjust(df)
                logger.info(f"Adjusted data for {ticker} ({exchange})")
            except Exception as e:
                logger.error(f"Error adjusting data for {ticker} ({exchange}): {e}", exc_info=True)
                return pd.DataFrame()
            try:
                df = trim_df(df)
                logger.info(f"Trimmed data for {ticker} ({exchange})")
            except Exception as e:
                logger.error(f"Error trimming data for {ticker} ({exchange}): {e}", exc_info=True)
                return pd.DataFrame()
            df = df.reset_index(drop=True)

            # 4) Save to CSV and set ownership
            try:
                df.to_csv(output_file)
                logger.info(f"Saved CSV to {output_file}")
            except Exception as e:
                logger.error(f"Error saving CSV {output_file}: {e}", exc_info=True)
                return pd.DataFrame()

            try:
                flask_uid = pwd.getpwnam('flask').pw_uid
                flask_gid = pwd.getpwnam('flask').pw_gid
                os.chown(output_file, flask_uid, flask_gid)
                logger.info(f"Changed ownership of {output_file} to flask")
            except Exception as e:
                logger.warning(f"Could not chown {output_file}: {e}", exc_info=True)

            return df
    except LockTimeout:
        # Another worker held the lock past 30s (typically a slow EODHD download).
        # This used to propagate and 500 every concurrent request for the ticker;
        # serve the existing on-disk CSV read-only instead (reading needs no lock).
        logger.warning(f"Lock timeout for {output_file}; serving existing CSV without refresh")
        if os.path.exists(output_file):
            try:
                return pd.read_csv(output_file, index_col=0)
            except Exception:
                logger.exception(f"Could not read {output_file} after lock timeout")
        return pd.DataFrame()
    finally: # purpose of finally is to cleanup the lock files - before lock files stayed around
            # Minimal addition: remove the lock file if it exists (cleanup)
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    logger.info(f"Removed lock file {lock_file}")
                except Exception as e:
                    logger.warning(f"Could not remove lock file {lock_file}: {e}")

# -----------------------------------------------------------------------------------------
# returns how many full years of data exist in this dataframe
def num_years_in_df(df):
    if df.empty or 'date' not in df.columns:
        return 0

    start_date = df['date'].iloc[0]
    end_date = df['date'].iloc[-1]

    start_year = int(start_date[:4])
    end_year = int(end_date[:4])

    if not (start_date[5:7] == '01' and start_date[8:10] in {'02', '03', '04'}):
        start_year += 1

    if not (end_date[5:7] == '12' and end_date[8:10] in {'29', '30', '31'}):
        end_year -= 1

    return max(0, end_year - start_year + 1)

# -----------------------------------------------------------------------------------------

if __name__ == '__main__':
    ticker = 'ADRXX'   # NS, ADR
    exchange = 'US'
    print(f"Attempting to download data for {ticker} ({exchange})")
    result = get_symbol_csv(ticker, exchange)
    print('result=',result)