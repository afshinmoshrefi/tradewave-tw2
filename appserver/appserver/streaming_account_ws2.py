import config_tradier
import requests
import datetime
from datetime import timedelta
import sys
sys.path.insert(0, '/home/flask')
import config_autotrade
import json
import asyncio
import websockets

headers = {
    'Authorization': f'Bearer {config_tradier.ACCESS_TOKEN}',
    'Accept': 'application/json'
}

headers_prod = {
    'Authorization': f'Bearer {config_tradier.ACCESS_TOKEN_PROD}',
    'Content-Length': '0',
    'Accept': 'application/json'
}

#------------------------------------------------------------------------------------------------
def create_streaming_account_session():
    url = 'https://sandbox.tradier.com/v1/accounts/events/session'  # must be prod for streaming
    response = requests.post(url, headers=headers)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid
#---------------------------------------------------------------------------------------------------

async def stream_account(sessionid):
    uri = "wss://sandbox-ws.tradier.com/v1/accounts/events"
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
            print(f"< {response}")

#---------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    status_code, url, sessionid = create_streaming_account_session()
    asyncio.run(stream_account(sessionid))
