import asyncio
import websockets
import json
import time

# Function to handle quote events
async def handle_quote_events(websocket):
    async for message in websocket:
        data = json.loads(message)
        print(f"Quote Event: {data}")

# Function to handle account events
async def handle_account_events(websocket):
    async for message in websocket:
        data = json.loads(message)
        print(f"Account Event: {data}")

# Function to print a message every minute
async def print_every_minute():
    while True:
        print("One minute has passed.")
        await asyncio.sleep(60)

async def main():
    # quote_uri = "wss://your_quote_websocket_url"  # Replace with your quote websocket URL
    # account_uri = "wss://your_account_websocket_url"  # Replace with your account websocket URL

    account_uri = "wss://sandbox-ws.tradier.com/v1/accounts/events"
    quote_uri = "wss://ws.tradier.com/v1/markets/events"

    async with websockets.connect(quote_uri) as quote_ws, websockets.connect(account_uri) as account_ws:
        quote_task = asyncio.create_task(handle_quote_events(quote_ws))
        account_task = asyncio.create_task(handle_account_events(account_ws))
        minute_task = asyncio.create_task(print_every_minute())

        await asyncio.gather(quote_task, account_task, minute_task)

if __name__ == "__main__":
    asyncio.run(main())
