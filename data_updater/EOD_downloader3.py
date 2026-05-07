# EOD_downloader3.py
# Improved version - same output format as EOD_downloader2.py
# Changes: Bulk API for small exchanges (<1000 symbols), sequential for large exchanges
#          Retry logic, connection pooling, automatic fallback if Bulk fails
#
# RELIABILITY FIRST:
# ==================
# This script prioritizes reliability over speed. Large exchanges (1000+ symbols)
# always use sequential downloads to prevent OOM errors. Bulk API is only used
# for smaller exchanges where memory usage is safe. If Bulk fails, we automatically
# fall back to sequential downloads.
#
# POST-MARKET TIMESTAMP ADJUSTMENT:
# =================================
# If this script runs between 4:01 PM and 11:59 PM New York time (post-market),
# the saved CSV files will have their modification date set to TOMORROW.
# This prevents is_file_modified_today() from triggering a re-download the next morning.
#
# LUMBER FUTURES SPLICING (LB -> LBR):
# =====================================
# In 2022-2023, CME transitioned from the old Random Length Lumber contract (LB/LBS)
# to the new Lumber contract (LBR). Key differences:
#   - Old LB: 110,000 board feet (railcar), delivered in Canada
#   - New LBR: 27,500 board feet (truckload), delivered in Chicago
#
# Both are quoted in $/1000 board feet, but prices differ due to:
#   - Different delivery locations (Canada vs Chicago)
#   - Different deliverable species (LBR allows more species)
#   - Different contract sizes affecting liquidity/pricing
#
# To create a continuous historical series for pattern analysis, we use the
# "backwards ratio adjustment" method:
#   1. Find the overlap period when both LB and LBR traded simultaneously
#   2. Calculate ratio = average(LBR_price / LB_price) during overlap
#   3. Multiply ALL historical LB prices by this ratio
#   4. Splice: adjusted LB history + LBR data = continuous series
#
# This preserves percentage returns (important for pattern analysis) while
# eliminating the price gap between contracts.
#
# The final output is saved as LBR.csv with the full adjusted history.

# one big update is that as of 2/7/2026 - if it runs after Newyork Close and before midnight, it will increment the date to the following day

import requests
import os
import pandas as pd
import sys
import time
import datetime
import gc

sys.path.insert(0, '/home/flask')
import config

EOD_token = config.EOD_token
cut_days = 223

# Lumber contract symbols for splicing
LUMBER_OLD = 'LB'      # Old Random Length Lumber (delisted)
LUMBER_NEW = 'LBR'     # New Lumber contract (current)
LUMBER_EXCHANGE = 'COMM'  # Commodities exchange

# Exchanges that support Bulk API
BULK_EXCHANGES = {'US', 'NYSE', 'NASDAQ', 'AMEX', 'LSE', 'TSX', 'ASX', 'NSE', 
                  'BSE', 'XETRA', 'PA', 'MI', 'MC', 'AS', 'SW', 'VI', 'BR',
                  'HK', 'SHE', 'SHG', 'KO', 'TW', 'JK', 'MX', 'SA', 'SN'}

# Only use Bulk API for exchanges smaller than this threshold
# Larger exchanges use sequential downloads to prevent OOM errors
BULK_MAX_SYMBOLS = 1000

#--------------------------------------------------------------------------------------------
# POST-MARKET TIMESTAMP FUNCTIONS
#--------------------------------------------------------------------------------------------

def is_post_market_hours():
    """
    Check if current time is between 4:01 PM and 11:59 PM New York time.
    
    Uses simple UTC offset: New York is UTC-5 (EST) or UTC-4 (EDT).
    This approximation assumes EST (UTC-5). Close enough for this purpose.
    """
    utc_now = datetime.datetime.utcnow()
    # New York is UTC-5 (EST) or UTC-4 (EDT). Using -5 as approximation.
    ny_hour = (utc_now.hour - 5) % 24
    
    # 4:01 PM = hour 16, 11:59 PM = hour 23
    return 16 <= ny_hour <= 23

def set_file_date_tomorrow_if_post_market(filepath):
    """If running in post-market hours, set file's modification date to tomorrow."""
    if is_post_market_hours():
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        # Set to midnight tomorrow
        tomorrow_timestamp = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        os.utime(filepath, (tomorrow_timestamp, tomorrow_timestamp))

#--------------------------------------------------------------------------------------------
def get_session():
    """Create session with connection pooling and auto-retry."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504]
        )
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

#--------------------------------------------------------------------------------------------
def get_sym_df(symbol, exchangeID, session):
    """Download full history for a single symbol."""
    eid = exchangeID
    if eid == 'ETF': eid = 'US'
    
    apiURL = f'https://eodhistoricaldata.com/api/eod/{symbol.strip()}.{eid}?api_token={EOD_token}&period=d&fmt=json'
    
    try:
        api_result = session.get(apiURL, timeout=30)
        
        if 'Not Found' in api_result.content.decode("utf-8"):
            print(symbol, 'not found')
            return pd.DataFrame()
        
        api_response = api_result.json()
        df = pd.DataFrame(api_response)
        return df
        
    except Exception as e:
        print(f'Error downloading {symbol}: {e}')
        return pd.DataFrame()

#--------------------------------------------------------------------------------------------
def get_bulk_data(exchange, session):
    """Download today's data for entire exchange in ONE call."""
    apiURL = f'https://eodhistoricaldata.com/api/eod-bulk-last-day/{exchange}?api_token={EOD_token}&fmt=json'
    
    try:
        response = session.get(apiURL, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        # Convert to dict: symbol -> single row DataFrame
        result = {}
        for item in data:
            symbol = item.get('code', '')
            if symbol:
                result[symbol] = pd.DataFrame([{
                    'date': item.get('date'),
                    'open': item.get('open'),
                    'high': item.get('high'),
                    'low': item.get('low'),
                    'close': item.get('close'),
                    'adjusted_close': item.get('adjusted_close'),
                    'volume': item.get('volume')
                }])
        
        print(f'Bulk API: got {len(result)} symbols for {exchange}')
        return result
        
    except Exception as e:
        print(f'Bulk API failed for {exchange}: {e}')
        return {}

#--------------------------------------------------------------------------------------------
def adjust(df):
    """Adjust OHLC using adjusted_close ratio. IDENTICAL OUTPUT FORMAT."""
    df['adj_factor'] = df['adjusted_close'] / df['close']
    df['open'] = df['open'] * df['adj_factor']
    df['high'] = df['high'] * df['adj_factor']
    df['low'] = df['low'] * df['adj_factor']
    df['close'] = df['close'] * df['adj_factor']
    df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'adj_factor']]
    return df

#--------------------------------------------------------------------------------------------
def trim_df(dfs):
    """Trim bad years with too many missing days. IDENTICAL OUTPUT FORMAT."""
    if dfs.empty:
        return dfs
        
    y0 = int(dfs['date'].iloc[0][:4])
    y1 = int(dfs['date'].iloc[dfs.shape[0]-1][:4])
    
    years_dict = {}
    for y in range(y0+1, y1):
        df2 = dfs[dfs['date'].str[:4] == str(y)]
        days = df2.shape[0]
        years_dict[y] = days
    
    years_list = list(years_dict.keys())[::-1]
    earliest_year_to_keep = 0
    
    for y in years_list:
        if years_dict[y] < cut_days:
            break
        else:
            earliest_year_to_keep = y
    
    first_date_in_csv = str(earliest_year_to_keep) + '-01-01'
    df = dfs[dfs['date'] > first_date_in_csv]
    return df

#--------------------------------------------------------------------------------------------
# LUMBER SPLICING FUNCTIONS
#--------------------------------------------------------------------------------------------

def calculate_lumber_ratio(lb_df, lbr_df):
    """
    Calculate the price ratio between LBR and LB during their overlap period.
    
    The overlap period is when both contracts traded simultaneously (roughly 2022-2023).
    We calculate: ratio = average(LBR_close / LB_close) for all overlapping dates.
    
    This ratio represents how much higher LBR prices are vs LB prices due to
    the different delivery locations and contract specifications.
    
    Returns:
        float: The average ratio, or None if no overlap found
    """
    if lb_df.empty or lbr_df.empty:
        return None
    
    # Find overlapping dates
    lb_dates = set(lb_df['date'].values)
    lbr_dates = set(lbr_df['date'].values)
    overlap_dates = lb_dates.intersection(lbr_dates)
    
    if len(overlap_dates) < 5:  # Need at least 5 days of overlap for reliable ratio
        print(f'WARNING: Only {len(overlap_dates)} overlapping days for LB/LBR ratio calculation')
        if len(overlap_dates) == 0:
            return None
    
    # Calculate ratio for each overlapping date
    ratios = []
    for date in overlap_dates:
        lb_price = lb_df[lb_df['date'] == date]['close'].values[0]
        lbr_price = lbr_df[lbr_df['date'] == date]['close'].values[0]
        
        if lb_price > 0:  # Avoid division by zero
            ratios.append(lbr_price / lb_price)
    
    if not ratios:
        return None
    
    avg_ratio = sum(ratios) / len(ratios)
    print(f'Lumber ratio calculated from {len(ratios)} overlapping days: {avg_ratio:.6f}')
    print(f'  Overlap period: {min(overlap_dates)} to {max(overlap_dates)}')
    
    return avg_ratio


def splice_lumber_contracts(lb_df, lbr_df, ratio):
    """
    Splice LB (old lumber) and LBR (new lumber) into a continuous series.
    
    Method: Backwards Ratio Adjustment
    - All historical LB prices are multiplied by the ratio
    - This makes LB prices comparable to LBR prices
    - The spliced series uses adjusted LB data for dates before LBR started,
      then switches to actual LBR data
    
    Args:
        lb_df: DataFrame with LB data (already adjusted via adjust() function)
        lbr_df: DataFrame with LBR data (already adjusted via adjust() function)
        ratio: The LBR/LB price ratio calculated from overlap period
    
    Returns:
        DataFrame: Continuous series with same columns as input
    """
    if lb_df.empty:
        return lbr_df
    if lbr_df.empty:
        return lb_df
    if ratio is None:
        print('WARNING: No ratio available, returning LBR only')
        return lbr_df
    
    # Find the first date in LBR - this is our splice point
    lbr_start_date = lbr_df['date'].min()
    print(f'Splicing lumber at {lbr_start_date} with ratio {ratio:.6f}')
    
    # Get LB data BEFORE LBR started (to avoid duplicates)
    lb_historical = lb_df[lb_df['date'] < lbr_start_date].copy()
    
    if lb_historical.empty:
        print('No LB history before LBR start date, returning LBR only')
        return lbr_df
    
    # Apply ratio adjustment to historical LB data
    # This adjusts: open, high, low, close (already adjusted for splits/dividends)
    # We multiply by ratio to make them comparable to LBR prices
    lb_historical['open'] = lb_historical['open'] * ratio
    lb_historical['high'] = lb_historical['high'] * ratio
    lb_historical['low'] = lb_historical['low'] * ratio
    lb_historical['close'] = lb_historical['close'] * ratio
    # Note: volume stays the same, adj_factor stays the same (it's from original adjust())
    
    # Combine: adjusted LB history + LBR data
    spliced = pd.concat([lb_historical, lbr_df], ignore_index=True)
    spliced = spliced.sort_values('date').reset_index(drop=True)
    
    print(f'Spliced lumber series: {len(lb_historical)} LB days + {len(lbr_df)} LBR days = {len(spliced)} total')
    
    return spliced


def handle_lumber_splicing(csv_path, session):
    """

    LB stopped trading on dec 31, 2026 - LBR has replaced it but they do have some differences
    in order to preserve history, this function normalizes LB history to be in the same level 
    as LBR and stiches it to LBR as history

    Main function to handle lumber contract splicing for COMM exchange.
    
    This function:
    1. Downloads both LB (old) and LBR (new) lumber contracts
    2. Calculates the price ratio from their overlap period
    3. Creates a spliced continuous series
    4. Saves the result as LBR.csv
    
    The LB.csv file is also saved separately (unadjusted) for reference.
    
    Args:
        csv_path: Path to the COMM csv folder
        session: requests Session object
    
    Returns:
        bool: True if splicing was performed, False otherwise
    """
    print('\n' + '='*60)
    print('LUMBER CONTRACT SPLICING (LB -> LBR)')
    print('='*60)
    
    # Download LB (old contract)
    print(f'Downloading {LUMBER_OLD} (old lumber contract)...')
    lb_raw = get_sym_df(LUMBER_OLD, LUMBER_EXCHANGE, session)
    
    # Download LBR (new contract)
    print(f'Downloading {LUMBER_NEW} (new lumber contract)...')
    lbr_raw = get_sym_df(LUMBER_NEW, LUMBER_EXCHANGE, session)
    
    if lb_raw.empty and lbr_raw.empty:
        print('ERROR: Could not download either lumber contract')
        return False
    
    # Apply standard adjustments (same as all other symbols)
    lb_adj = pd.DataFrame()
    lbr_adj = pd.DataFrame()
    
    if not lb_raw.empty and lb_raw.shape[0] > 0:
        lb_adj = adjust(lb_raw)
        lb_adj = trim_df(lb_adj)
        # Save LB separately for reference
        lb_adj_save = lb_adj.reset_index(drop=True)
        lb_filename = csv_path + LUMBER_OLD + '.csv'
        lb_adj_save.to_csv(lb_filename)
        set_file_date_tomorrow_if_post_market(lb_filename)
        print(f'Saved {LUMBER_OLD}.csv ({len(lb_adj)} rows)')
    
    if not lbr_raw.empty and lbr_raw.shape[0] > 0:
        lbr_adj = adjust(lbr_raw)
        lbr_adj = trim_df(lbr_adj)
    
    # Calculate ratio from overlap period
    ratio = calculate_lumber_ratio(lb_adj, lbr_adj)
    
    # Splice the contracts
    spliced = splice_lumber_contracts(lb_adj, lbr_adj, ratio)
    
    # Save the spliced series as LBR.csv
    if not spliced.empty:
        spliced = spliced.reset_index(drop=True)
        lbr_filename = csv_path + LUMBER_NEW + '.csv'
        spliced.to_csv(lbr_filename)
        set_file_date_tomorrow_if_post_market(lbr_filename)
        print(f'Saved spliced {LUMBER_NEW}.csv ({len(spliced)} rows)')
        print('='*60 + '\n')
        return True
    
    print('='*60 + '\n')
    return False

#--------------------------------------------------------------------------------------------
def is_file_modified_today(file_path):
    """Check if file was modified today."""
    t = os.path.getmtime(file_path)
    file_date = datetime.datetime.fromtimestamp(t)
    today = datetime.datetime.today()
    return file_date.date() == today.date()

#--------------------------------------------------------------------------------------------
def update_resource_group(exchange, slist, csv_path):
    """Update all CSVs for an exchange."""
    
    if not os.path.exists(csv_path):
        os.makedirs(csv_path)
    
    slist_str = [str(item) for item in slist]
    session = get_session()
    
    # =========================================================================
    # SPECIAL HANDLING: Lumber contract splicing for COMM exchange
    # =========================================================================
    # For commodities (COMM), we handle LB and LBR specially because:
    # - LB (old contract) was delisted in favor of LBR (new contract)
    # - They have different specifications but track the same commodity
    # - We splice them together for continuous historical analysis
    # - See comments at top of file for full explanation
    # =========================================================================
    lumber_symbols = {LUMBER_OLD, LUMBER_NEW}  # {'LB', 'LBR'}
    
    if exchange == LUMBER_EXCHANGE:  # COMM
        # Handle lumber splicing separately
        handle_lumber_splicing(csv_path, session)
        # Remove lumber symbols from regular processing (we already handled them)
        slist_str = [s for s in slist_str if s not in lumber_symbols]
    
    # Separate: need full download vs just need today's update vs already current
    need_full_download = []
    need_update = []
    
    for ss in slist_str:
        if '.' in ss: continue
        
        csv_filename = csv_path + ss + '.csv'
        
        if os.path.exists(csv_filename):
            if not is_file_modified_today(csv_filename):
                need_update.append(ss)
        else:
            need_full_download.append(ss)
    
    print(f'{exchange}: {len(need_update)} need update, {len(need_full_download)} need full download')
    
    # =========================================================================
    # BULK API FOR SMALL EXCHANGES ONLY
    # =========================================================================
    # Only use Bulk API if:
    #   1. Exchange supports it
    #   2. Total symbols < BULK_MAX_SYMBOLS (prevents OOM on large exchanges)
    #   3. There are symbols that need updating
    # If Bulk fails for any reason, we fall back to sequential (bulletproof)
    # =========================================================================
    use_bulk = (exchange in BULK_EXCHANGES and 
                len(slist_str) < BULK_MAX_SYMBOLS and 
                len(need_update) > 0)
    
    if use_bulk:
        try:
            bulk_data = get_bulk_data(exchange, session)
            
            updated = 0
            for ss in need_update[:]:  # iterate copy so we can modify
                s = config.alias_symbols.get(ss, ss)
                csv_filename = csv_path + ss + '.csv'
                
                if s in bulk_data and not bulk_data[s].empty:
                    try:
                        existing_df = pd.read_csv(csv_filename, index_col=0)
                        new_data = bulk_data[s]
                        
                        if 'adjusted_close' in new_data.columns:
                            new_data = adjust(new_data)
                            new_date = new_data['date'].iloc[0]
                            
                            if new_date not in existing_df['date'].values:
                                merged = pd.concat([existing_df, new_data], ignore_index=True)
                                merged = merged.reset_index(drop=True)
                                merged.to_csv(csv_filename)
                                set_file_date_tomorrow_if_post_market(csv_filename)
                                updated += 1
                                need_update.remove(ss)
                        
                        del existing_df, new_data  # Free memory immediately
                    except Exception as e:
                        print(f'Error updating {ss}: {e}')
                
                # Delete this symbol's bulk data immediately after processing
                if s in bulk_data:
                    del bulk_data[s]
            
            # Clear any remaining bulk data and force garbage collection
            bulk_data.clear()
            del bulk_data
            gc.collect()
            
            print(f'Bulk updated {updated} symbols')
            
        except Exception as e:
            # Bulk API failed entirely - fall back to sequential
            print(f'Bulk API failed for {exchange}, using sequential: {e}')
    
    elif len(slist_str) >= BULK_MAX_SYMBOLS:
        print(f'{exchange} has {len(slist_str)} symbols - using sequential downloads (safer)')
    
    # Full downloads for new symbols + any that failed bulk update
    all_downloads = need_full_download + need_update
    
    c = 0
    failed = 0
    for ss in all_downloads:
        if '.' in ss: continue
        c += 1
        
        s = config.alias_symbols.get(ss, ss)
        csv_filename = csv_path + ss + '.csv'
        
        print(f'{c}/{len(all_downloads)} - downloading {ss}')
        
        try:
            dfs = get_sym_df(s, exchange, session)
            if dfs.shape[0] > 0:
                dfs = adjust(dfs)
                dfs = trim_df(dfs)
                dfs = dfs.reset_index(drop=True)
                dfs.to_csv(csv_filename)
                set_file_date_tomorrow_if_post_market(csv_filename)
        except Exception as e:
            print(f'FAILED {ss}: {e}')
            failed += 1
    
    if failed > 0:
        print(f'WARNING: {failed} symbols failed to download')
    
    session.close()

#--------------------------------------------------------------------------------------------
if __name__ == '__main__':
    
    # Marker file
    f = open("/home/flask/data_updater/EOD3_run.xxx", "w")
    f.close()
    
    t1 = time.time()
    
    groups = config.exchange_mapping
    exchange_list = sorted(list(set(groups.values())))
    
    c = 0
    for exchange in exchange_list:
        c += 1
        print(f'Processing exchange {c}/{len(exchange_list)}: {exchange}')
        
        dtypes = {'symbols': 'str', 'name': 'str'}
        df = pd.DataFrame(columns=dtypes.keys()).astype(dtypes)
        
        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                dfm = pd.read_csv(config.available_resources_path[k], dtype=dtypes)
                dfm = dfm[['symbols', 'name']]
                df = pd.concat([df, dfm])
        
        df['symbols'] = df['symbols'].astype(str)
        slist = sorted(list(set(list(df['symbols']))))
        
        csv_path = config.csv_folder + exchange + '/'
        update_resource_group(exchange, slist, csv_path)
    
    t2 = time.time()
    print(round(t2-t1, 2), 'seconds', round((t2-t1)/60, 2), 'minutes')