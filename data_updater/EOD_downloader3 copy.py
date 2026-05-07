import requests
import glob
import os
import pandas as pd
import json
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='eod_downloader3.log'
)

# API settings
token = os.environ['EOD_TOKEN']
cut_days = 223
MAX_RETRIES = 3
RETRY_BACKOFF = 2
PARALLEL_WORKERS = 10  # Adjust based on API rate limits and system capabilities
TIMEOUT = 30  # seconds

# Configure session with retries
session = requests.Session()
retries = Retry(total=MAX_RETRIES, backoff_factor=RETRY_BACKOFF, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

#--------------------------------------------------------------------------------------------
def get_sym_df(symbol, exchangeID):
    logger = logging.getLogger(__name__)
    logger.info(f'Downloading {symbol} from eodhistoricaldata.com')
    
    eid = exchangeID if exchangeID != 'ETF' else 'US'
    apiURL = f'https://eodhistoricaldata.com/api/eod/{symbol.strip()}.{eid}?api_token={token}&period=d&fmt=json'

    try:
        response = session.get(apiURL, timeout=TIMEOUT)
        response.raise_for_status()  # Raise exception for bad status codes
        
        if 'Not Found' in response.text:
            logger.warning(f'{symbol} not found')
            return pd.DataFrame()
        
        api_response = response.json()
        if not api_response:
            logger.warning(f'Empty response for {symbol}')
            return pd.DataFrame()
            
        df = pd.DataFrame(api_response)
        return df

    except requests.exceptions.RequestException as e:
        logger.error(f'Error downloading {symbol}: {str(e)}')
        return pd.DataFrame()
    except json.JSONDecodeError as e:
        logger.error(f'JSON decode error for {symbol}: {str(e)}')
        return pd.DataFrame()
    except Exception as e:
        logger.error(f'Unexpected error for {symbol}: {str(e)}')
        return pd.DataFrame()

#--------------------------------------------------------------------------------------------
def adjust(df):
    if df.empty:
        return df
        
    try:
        df['adj_factor'] = df['adjusted_close'] / df['close']
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] * df['adj_factor']
        return df[['date', 'open', 'high', 'low', 'close', 'volume', 'adj_factor']]
    except (KeyError, ZeroDivisionError) as e:
        logging.error(f'Error adjusting dataframe: {str(e)}')
        return df

#--------------------------------------------------------------------------------------------
def trim_df(dfs):
    if dfs.empty:
        return dfs
        
    try:
        y0 = int(dfs['date'].iloc[0][:4])
        y1 = int(dfs['date'].iloc[-1][:4])
        years_dict = {}
        
        for y in range(y0 + 1, y1):
            df2 = dfs[dfs['date'].str[:4] == str(y)]
            years_dict[y] = df2.shape[0]
        
        earliest_year_to_keep = 0
        for y in sorted(years_dict.keys(), reverse=True):
            if years_dict[y] < cut_days:
                break
            earliest_year_to_keep = y

        if earliest_year_to_keep:
            first_date_in_csv = f'{earliest_year_to_keep}-01-01'
            return dfs[dfs['date'] > first_date_in_csv]
        return dfs
        
    except Exception as e:
        logging.error(f'Error trimming dataframe: {str(e)}')
        return dfs

#--------------------------------------------------------------------------------------------
def process_symbol(symbol, exchange, csv_path):
    logger = logging.getLogger(__name__)
    
    if '.' in symbol:
        logger.info(f'Skipping symbol {symbol} due to invalid format')
        return
    
    try:
        s = config.alias_symbols.get(symbol, symbol)
        dfs = get_sym_df(s, exchange)
        
        if not dfs.empty:
            dfs = adjust(dfs)
            dfs = trim_df(dfs)
            
            if not dfs.empty:
                os.makedirs(csv_path, teacher_mode=0o755, exist_ok=True)
                dfs = dfs.reset_index(drop=True)
                dfs.to_csv(os.path.join(csv_path, f'{s}.csv'))
                logger.info(f'Successfully saved {s} to {csv_path}')
            else:
                logger.warning(f'No data after processing for {s}')
        else:
            logger.warning(f'No data retrieved for {s}')
            
    except Exception as e:
        logger.error(f'Error processing symbol {symbol}: {str(e)}')

#--------------------------------------------------------------------------------------------
def update_resource_group(exchange, slist, csv_path):
    logger = logging.getLogger(__name__)
    logger.info(f'Processing {len(slist)} symbols for exchange {exchange}')
    
    try:
        os.makedirs(csv_path, exist_ok=True)
        
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = [
                executor.submit(process_symbol, symbol, exchange, csv_path)
                for symbol in slist
                if '.' not in str(symbol)
            ]
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f'Error in future: {str(e)}')
                    
    except Exception as e:
        logger.error(f'Error processing exchange {exchange}: {str(e)}')

#--------------------------------------------------------------------------------------------
if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    
    try:
        # Create marker file
        with open("/home/flask/data_updater/EOD2_run.xxx", "w") as f:
            f.write(str(time.time()))
            
        t1 = time.time()
        groups = config.exchange_mapping
        exchange_list = sorted(set(groups.values()))
        
        for i, exchange in enumerate(exchange_list, 1):
            logger.info(f'Processing exchange {i}/{len(exchange_list)}: {exchange}')
            
            try:
                dtypes = {'symbols': 'str', 'name': 'str'}
                df = pd.DataFrame(columns=dtypes.keys()).astype(dtypes)
                
                for k in config.exchange_mapping:
                    if config.exchange_mapping[k] == exchange:
                        try:
                            dfm = pd.read_csv(config.available_resources_path[k], dtype=dtypes)
                            dfm = dfm[['symbols', 'name']]
                            df = pd.concat([df, dfm])
                        except Exception as e:
                            logger.error(f'Error reading resource {k}: {str(e)}')
                            continue
                
                if df.empty:
                    logger.warning(f'No symbols found for exchange {exchange}')
                    continue
                    
                slist = sorted(set(df['symbols'].astype(str)))
                csv_path = os.path.join(config.csv_folder, exchange, '')
                update_resource_group(exchange, slist, csv_path)
                
            except Exception as e:
                logger.error(f'Error processing exchange {exchange}: {str(e)}')
                continue
        
        t2 = time.time()
        logger.info(f'Completed in {round(t2-t1, 2)} seconds ({round((t2-t1)/60, 2)} minutes)')
        
    except Exception as e:
        logger.error(f'Fatal error in main: {str(e)}')
        sys.exit(1)
    finally:
        session.close()