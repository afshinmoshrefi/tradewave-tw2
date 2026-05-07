
# the websocket payload is so different than the payload in http streaming - although it worked at first, it stopped working
# the requirement is to create a string representation of a json when using the websocket streaming API
# I based this example on the tech support email from tim.  the original is named tim.py

import asyncio
import requests
import websockets
import sys
import config_tradier
import json




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
    url = 'https://api.tradier.com/v1/markets/events/session'  # must be prod for streaming
    response = requests.post(url, headers=headers_prod)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid

#-------------------------------------------------------------------------------------------

async def ws_connect(SYMBOLS,SESSION_ID):


    symbols_str = json.dumps(SYMBOLS)
    PAYLOAD  = '{"symbols": '+symbols_str+', "filter": ["trade", "quote", "tradex"], "sessionid": "' + SESSION_ID + '", "linebreak": true, "validOnly": true}'


    uri = "wss://ws.tradier.com/v1/markets/events"
    async with websockets.connect(uri, ssl=True, compression=None) as websocket:
        payload = PAYLOAD
        print(payload)
        await websocket.send(payload)

        print(f">>> {payload}")

        async for message in websocket:
            print(f"<<< {message}")

#-------------------------------------------------------------------------------------------

if __name__ == '__main__':

    SYMBOLS = ["NVDA", "AAPL","MSFT"]


    status_code, url, sessionid = create_streaming_market_session()

    asyncio.run(ws_connect(SYMBOLS,sessionid))