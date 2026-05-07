# trade queue is a service like blog_queue - it reads the messages that was put on the queue by stream-account and other producers
# the first job of trade_queue is the take the events (messages) from the queue and store it as a row to a csv log of all order events

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
import os
import time
import threading

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
    url = 'https://api.tradier.com/v1/markets/events/session'
    response = requests.post(url, headers=headers_prod)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid = json_response['stream']['sessionid']
    return response.status_code, streaming_url, sessionid

def read_symbols_from_file(file_path='symbols.txt'):
    with open(file_path, 'r') as file:
        symbols_list = [line.strip().split(',') for line in file]
    symbols = [symbol for symbols_per_line in symbols_list for symbol in symbols_per_line]
    return symbols

def file_modified_time(file_path):
    return os.path.getmtime(file_path)

async def ws_connect(sessionid, symbols):
    uri = "wss://ws.tradier.com/v1/markets/events"
    async with websockets.connect(uri, ssl=True, compression=None) as websocket:
        payload = {
            "symbols": symbols,
            "sessionid": sessionid,
            "linebreak": True
        }
        await websocket.send(json.dumps(payload))
        print(f">>> {json.dumps(payload)}")

        async for message in websocket:
            print(f"<<< {message}")

def watch_symbols_file(file_path, callback):
    last_modified_time = file_modified_time(file_path)

    while True:
        time.sleep(1)
        current_modified_time = file_modified_time(file_path)

        if current_modified_time > last_modified_time:
            last_modified_time = current_modified_time
            callback()

if __name__ == '__main__':
    symbols_file = 'symbols.txt'

    status_code, url, sessionid = create_streaming_market_session()
    symbols = read_symbols_from_file(symbols_file)

    # Start a separate thread to watch for changes in the symbols file
    def thread_target():
        asyncio.run(ws_connect(sessionid, symbols))

    threading.Thread(target=thread_target, daemon=True).start()

    # Watch for changes in the symbols file
    try:
        asyncio.run(watch_symbols_file(symbols_file, lambda: asyncio.run(ws_connect(sessionid, read_symbols_from_file(symbols_file)))))
    except asyncio.CancelledError:
        pass
