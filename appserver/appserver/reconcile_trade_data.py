# first task that should run periodically is to remove canceled and expired orders from user_reports_### key in redis db=2


import asyncio
import requests
import websockets
import sys
import config_tradier
import json
import redis
import asyncio
from  tradier_api import get_quotes , get_orders , get_positions
from  appserver_autotrade_funcs import update_live_trade,remove_order_from_live_trades_list
import config_autotrade
from collections import defaultdict


# Constants
# REDIS_URL = 'redis://localhost:6379/1'

MARKET_EVENTS_URL  = 'https://api.tradier.com/v1/markets/events/session'
ACCOUNT_EVENTS_URL = 'https://sandbox.tradier.com/v1/accounts/events/session'

WS_MARKET_URI  = 'wss://ws.tradier.com/v1/markets/events'
WS_ACCOUNT_URI = 'wss://sandbox-ws.tradier.com/v1/accounts/events'

redis_client1  = redis.Redis(host='localhost', port=6379, db=1)  # autotrade db
redis_client2  = redis.Redis(host='localhost', port=6379, db=2)  # tradwave reports db

#----------------------------------------------------------------------------------

headers = {
    'Authorization': f'Bearer {config_tradier.ACCESS_TOKEN}',
    'Accept': 'application/json'
}

headers_prod = {
    'Authorization': f'Bearer {config_tradier.ACCESS_TOKEN_PROD}',
    'Content-Length': '0',
    'Accept': 'application/json'
}

#---------------------------------------------------------------------------------------------------------
# checks to make sure all updates to live_trades have been made.  issues may occur if appserver_async.py  
# either wasn't running when event arrived from account_stream or just missed an event for any reason
# this function runs every 10 to 15 minutes and checks values that should be in live_trades for example
# if a trade was filled but it didn't register in live_trades - also if live_trades is deleted or a row is
# deleted for any reason, this routine recreates live_trades to continue autotrading operation seamlessly
#---------------------------------------------------------------------------------------------------------
def reconcile_live_trades(userid):
    
    live_trades = []
    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 
    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)
    
    # print(live_trades)

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)
    else:
        redis_user_reports_list=[]

    orders      = get_orders(config_autotrade.account_id)
    orders_list = [o['id'] for o in orders if 'id' in o]
    positions = get_positions(config_autotrade.account_id)
    sorted_positions = sorted(positions['position'], key=lambda x: x['date_acquired']) # sort by key in list of dictionaries
    # get quotes for all the positions in the account
    symbols = ','.join(position['symbol'] for position in positions['position'] if 'symbol' in position)
    quotes = get_quotes(symbols)
    # create a symbol_dict for easily finding underlying symbol for an option symbol
    sym_dict = {d['symbol']:d['underlying'] for d in quotes if 'underlying' in d}
    print(sym_dict)
    # exit()
  
    # remove orders that are no longer valid from redis reports record
    for r in redis_user_reports_list:
        print(r,'\n')
        if 'orders' in r:
            sp = r['orders'].split(',')
            updated_orders = '' 
            # remove all the orders that are no longer valid
            for o in sp:
                # print(r['dr_id'],o)
                if o in orders_list:
                    updated_orders += o+','
            if len(updated_orders)>0:updated_orders = updated_orders[:-1] # removing the extra comma
            r['orders'] = updated_orders
    

    # check if all the positions in redis_user_reports_list are accounted for - if there is are current positions that is missing from 
    # the redis_user_reports_list, then try to find and add it to the redis_user_reports_list 
    # for p in positions['position']:
    #     print(p)
    # print(positions['position'])

    # somehow this does the grouping, written by mistral
    # creates grouped options as long as they have the same date_acquired
    grouped_data = defaultdict(list)
    for item in positions['position']:
        grouped_data[item['date_acquired']].append(item)


    # for d in dict(grouped_data):
    #     print(grouped_data[d],'\n')

    for r in redis_user_reports_list:
        if 'orders' in r: # if there was an orders key, some trade was done for this

            num_positions = 0
            if 'positions' in r:
                existing_positions = r['positions']
                # print(existing_positions)
                sp = existing_positions.split(',')
                num_positions = len(sp)

            underlying_symbol = r['symbol']
            options_symbols = [key for key, value in sym_dict.items() if value == underlying_symbol]
            positions= ','.join(options_symbols)
            
            if num_positions < len(options_symbols): # something is missing or all is misisng
                r['positions'] = positions

                


    # write back the list of reports with updated orders and positions
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list))
#---------------------------------------------------------------------------------------------------
# checks all the orders for the user and remove expired and canceled orders from each dr_id
#---------------------------------------------------------------------------------------------------
def remove_unused_orders(userid):

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    if redis_user_reports_list is None:
        return

    redis_user_reports_list = json.loads(redis_user_reports_list)

    # print(redis_user_reports_list)

    for r in redis_user_reports_list:
        if 'orders' in r:
            orders_list = r['orders'].split(',')
            for o in orders_list:
                print(o)

#---------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    userid = config_autotrade.userid[0]
    remove_unused_orders(userid)

    # reconcile_live_trades(userid)