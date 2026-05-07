
# the websocket payload is so different than the payload in http streaming - although it worked at first, it stopped working
# the requirement is to create a string representation of a json when using the websocket streaming API
# I based this example on the tech support email from tim.  the original is named tim.py

# this version 2 will get the list of symbols from redis db=1 key=live_symbols  - it also check live_symbols_timestamp 

import asyncio
import requests
import websockets
import sys
import config_tradier
import json
import redis
import asyncio

# Constants
REDIS_URL = 'redis://localhost:6379/1'

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

def create_streaming_market_session():
    url = MARKET_EVENTS_URL  # must be prod for streaming
    response = requests.post(url, headers=headers_prod)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid

#-------------------------------------------------------------------------------------------
def get_symbols_redis():
    symbols = ['BA'] # default

    live_symbols_redis = redis_client1.get('live_symbols')
    if live_symbols_redis is not None:
        symbols = json.loads(live_symbols_redis)

    print('get_symbols_redis',type(symbols),symbols)

    return symbols
#-------------------------------------------------------------------------------------------
async def ws_connect(SESSION_ID):

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
            print(payload)
            await websocket.send(payload)

            print(f">>> {payload}")

            async for message in websocket:
                print(f"<<< {message}")
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

#-------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    SYMBOLS = get_symbols_redis()
    last_timestamp = redis_client1.get('live_symbols_timestamp')

    status_code, url, sessionid = create_streaming_market_session()

    asyncio.run(ws_connect(sessionid))