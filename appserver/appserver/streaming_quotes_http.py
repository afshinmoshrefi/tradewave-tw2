import config_tradier
import requests
import datetime
from datetime import timedelta
import sys
sys.path.insert(0, '/home/flask')
import config_autotrade
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

#------------------------------------------------------------------------------------------------
def create_streaming_market_session():

    url = 'https://api.tradier.com/v1/markets/events/session'  # must be prod for streaming

    response = requests.post(url,headers=headers_prod)
    json_response = response.json()
    streaming_url = json_response['stream']['url']
    sessionid     = json_response['stream']['sessionid']

    return response.status_code,streaming_url,sessionid
#---------------------------------------------------------------------------------------------------
if __name__ == '__main__':


    
    symbol = 'AAPL'

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    status_code,url,sessionid = create_streaming_market_session()


    headers = {
        'Accept': 'application/json'
        }

    payload = { 
    'sessionid': sessionid,
    'symbols': 'AAPL,MSFT,NVDA',
    'linebreak': True
    }

    r = requests.get('https://stream.tradier.com/v1/markets/events', stream=True, params=payload, headers=headers)

    
    for line in r.iter_lines():
        if line:
            print(json.loads(line))



 

   
   