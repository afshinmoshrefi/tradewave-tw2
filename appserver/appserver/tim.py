#!/usr/bin/env python3

import asyncio
import requests
import websockets
import sys
import config_tradier
import json


API_TOKEN = config_tradier.ACCESS_TOKEN_PROD

response = requests.post('https://api.tradier.com/v1/markets/events/session',
    data={},
    headers={'Authorization': 'Bearer ' + API_TOKEN, 'Accept': 'application/json'}
)

if response.status_code == 401:
    print("Token request respsponse: {}".format(response))
    sys.exit(1)
else:
    json_response = response.json()
    SESSION_ID = json_response['stream']['sessionid']

SYMBOLS = ["TSLA", "AAPL"]
symbols_str = json.dumps(SYMBOLS)
PAYLOAD  = '{"symbols": '+symbols_str+', "filter": ["trade", "quote", "tradex"], "sessionid": "' + SESSION_ID + '", "linebreak": true, "validOnly": true}'

async def ws_connect():
    uri = "wss://ws.tradier.com/v1/markets/events"
    async with websockets.connect(uri, ssl=True, compression=None) as websocket:
        payload = PAYLOAD
        print(payload)
        await websocket.send(payload)

        print(f">>> {payload}")

        async for message in websocket:
            print(f"<<< {message}")

asyncio.run(ws_connect())