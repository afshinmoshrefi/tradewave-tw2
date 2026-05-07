# appserver_async runs independent of the appserver and serves conditional operations that happen later.
# the main purpose is to manage exit orders for trades
# the main asynchronous services are:
# async websocket quote stream - the list of symbols to stream is dynamic and served from the redis db=1
# keys: ['live_trades','live_symbols','live_symbols_timestamp']
# the websocket loop checks if the value of live_symbols_timestamp has changed.  when changed, it reloads the SYMBOLS list


import asyncio
import requests
import websockets
import sys
import datetime
import config_tradier
import json
import redis
import asyncio
from  tradier_api import get_quotes 
from  appserver_autotrade_funcs import update_live_trade,remove_order_from_live_trades_list
import os
from trade_tools import json_log # from blog_processing in web server
sys.path.insert(0, '/home/flask')
import config
import config_autotrade

# Constants
# REDIS_URL = 'redis://localhost:6379/1'

MARKET_EVENTS_URL  = 'https://api.tradier.com/v1/markets/events/session'
ACCOUNT_EVENTS_URL = 'https://sandbox.tradier.com/v1/accounts/events/session'

WS_MARKET_URI  = 'wss://ws.tradier.com/v1/markets/events'
WS_ACCOUNT_URI = 'wss://sandbox-ws.tradier.com/v1/accounts/events'

redis_client1  = redis.Redis(host='localhost', port=6379, db=1)

last_timestamp = None
SYMBOLS = ['BA']
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
#----------------------------------------------------------------------------------
def create_streaming_market_session():
    url = MARKET_EVENTS_URL  # must be prod for streaming
    response = requests.post(url, headers=headers_prod)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid
#-------------------------------------------------------------------------------------------
# get all the stock symbols in the live_trades key
#-------------------------------------------------------------------------------------------
def get_symbols_redis():
    symbols = ['BA'] # default

    live_symbols_redis = redis_client1.get('live_symbols')
    if live_symbols_redis is not None:
        symbols = json.loads(live_symbols_redis)

    print('get_symbols_redis',type(symbols),symbols)

    return symbols
#-------------------------------------------------------------------------------------------
async def stream_quotes(SESSION_ID):

    global last_timestamp
    global SYMBOLS

    while True:
        symbols_str = json.dumps(SYMBOLS)
        PAYLOAD  = '{"symbols": '+symbols_str+', "filter": ["trade", "quote", "tradex"], "sessionid": "' + SESSION_ID + '", "linebreak": true, "validOnly": true}'

        uri = WS_MARKET_URI

        async with websockets.connect(uri, ssl=True, compression=None) as websocket:

            symbols_str = json.dumps(SYMBOLS)
            PAYLOAD  = '{"symbols": '+symbols_str+', "filter": ["trade", "quote", "tradex"], "sessionid": "' + SESSION_ID + '", "linebreak": true, "validOnly": true}'
            payload = PAYLOAD
            
            if len(SYMBOLS) > 0:
                print(payload)
                await websocket.send(payload)

            # print(symbols_str,type(symbols_str))
            print(f">>> {payload}")

            async for message in websocket:
                # print(f"<<< {message}")
                #########################################
                ##### implement quotes actions here #####
                #########################################


                # Check if 'live_symbols_timestamp' has changed
                current_timestamp = redis_client1.get('live_symbols_timestamp')
                if current_timestamp != last_timestamp:
                    # If it has changed, break the loop to restart the websocket connection
                    print("Timestamp has changed, restarting websocket connection...")
                    SYMBOLS = get_symbols_redis()
                    break

        # Set the last_timestamp to the current_timestamp after the loop
        last_timestamp = current_timestamp
        # Wait for a bit before restarting the connection to avoid rate limits
        await asyncio.sleep(1)
#------------------------------------------------------------------------------------------------
def create_streaming_account_session():
    url = ACCOUNT_EVENTS_URL   # must be prod for streaming
    response = requests.post(url, headers=headers)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid
#---------------------------------------------------------------------------------------------------
async def stream_account(sessionid):
    uri = WS_ACCOUNT_URI 
    async with websockets.connect(uri) as websocket:
        payload = {
            "events": ["order"],
            "sessionid": sessionid,
            "excludeAccounts": []
        }

        await websocket.send(json.dumps(payload))
        print(f"> {json.dumps(payload)}")

        while True:
            response = await websocket.recv()
            
            if 'heartbeat' not in response:
                print(type(response),f"< {response}")
            data = json.loads(response)
            archive_event(data)
            #########################################
            ##### implement account actions here ####
            #########################################
            if data['event'] == 'order': # and 'parent_id' not in data: # if parent_id is in data the event is for individual options
                if 'status' in data:
                    if data['status'] == 'canceled' or data['status'] == 'expired'  or data['status'] == 'rejected' :
                        order_id = data['id']
                        remove_order_from_live_trades_list(redis_client1,order_id) # this routine also remove symbol from live_symbols
                    elif data['status'] == 'filled' or data['status'] == 'partially_filled': 
                        # price = data['price']
                        # order_id = data['id']
                        # transaction_datetime = data['transaction_date']
                        update_live_trade(redis_client1,config_tradier.ACCOUNT_ID,data)
                        print('live trades updated')
#---------------------------------------------------------------------------------------------------
# adds to a log for all account data received via websocket
#---------------------------------------------------------------------------------------------------
def archive_event(data):

    if data['event'] == 'heartbeat': return 
    today_date = datetime.datetime.now().strftime("%Y-%m-%d") # this is the server's local timezone
    json_archive_filename = f'{config_autotrade.event_log_folder}account_events_{today_date}.json'
    os.makedirs(os.path.dirname(json_archive_filename), exist_ok=True)

    # print('data=',data)

    json_log(json_archive_filename,'add',data)                     
#---------------------------------------------------------------------------------------------------
async def periodic_task():
    while True:
        # Wait for 10 minutes
        await asyncio.sleep(600)
        # Tasks to perform every 10 minutes
        print("Executing periodic task...")
        #########################################
        ######## Add all the tasks here #########
        #########################################   

#---------------------------------------------------------------------------------------------------
async def main():

    SYMBOLS = get_symbols_redis() # get all the stock symbols in the live_trades key
    last_timestamp = redis_client1.get('live_symbols_timestamp')

    market_status, market_url, market_sessionid    = create_streaming_market_session()
    account_status, account_url, account_sessionid = create_streaming_account_session()

    await asyncio.gather(
        stream_quotes(market_sessionid),
        stream_account(account_sessionid),
        periodic_task()  # Include the periodic task function
    )

#---------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    asyncio.run(main())