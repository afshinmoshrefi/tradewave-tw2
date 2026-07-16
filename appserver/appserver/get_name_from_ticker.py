# this script get the company or security name from a ticker symbol by queriying EODhd  7/20/2025

from pooled_http import http as requests
import os, os.path
import pandas as pd
import json
import pwd
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

token = config.EOD_token

#----------------------------------------------------------------------------------------------------------------
# this function only gets back stock company names from US, LSE, TA, TO, MX, MC, VN, MX
#----------------------------------------------------------------------------------------------------------------
def get_security_name_from_ticker(exchange: str, ticker: str) -> str:
    valid_exchanges = ['US', 'LSE', 'TA', 'TO', 'MX', 'MC', 'VN']
    exchange = exchange.upper()
    if exchange not in valid_exchanges:
        return get_security_name_from_csv(exchange, ticker)

    url_search = f"https://eodhd.com/api/search/{ticker}"
    params = {'api_token': token, 'fmt': 'json'}
    try:
        resp = requests.get(url_search, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json() or []
        for item in results:
            if item.get('Exchange', '').upper() == exchange:
                return item.get('Name')
    except Exception as e:
        print(f"EODHD lookup error: {e}")
    return None
#----------------------------------------------------------------------------------------------------------------
def get_security_name_from_csv(exchange: str, ticker: str) -> str:

    if exchange == 'INDX' and ticker == 'SPX':
        return 'S&P 500 Index'

    if exchange == 'INDX':
        csv_symbols_file = os.path.join(config.ddir, 'INDX_USA_symbols.csv')
    else:
        csv_symbols_file = os.path.join(config.ddir, f'{exchange}_symbols.csv')
    

    try:
        df = pd.read_csv(csv_symbols_file)
        # Find row(s) where 'symbols' column matches the ticker (case-insensitive)
        match = df[df['symbols'].str.upper() == ticker.upper()]
        if not match.empty:
            return match.iloc[0]['name']
    except Exception as e:
        print(f"CSV lookup error: {e}")
    return None
#----------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    
    exchange = 'US'
    ticker = 'HPQ'
    company = get_security_name_from_ticker(exchange, ticker)

    print(company)
