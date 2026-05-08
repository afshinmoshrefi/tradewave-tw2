# this script calls one API call in tradewave appserver api route is: process_auto_portfolio
# This is used in crontab at 4AM to have the auto trading portfolios ready for the day

# the userid has to have access to autotrading and scanning

import json
import requests
import pandas as pd
import sys

sys.path.insert(0, '/home/flask')
import config
import config_autotrade

userid = 16 # afshin userid on dev is used to create auto portfolio


#------------------------------------------------------------------------------------------------------------------------------------------------
def login_appserver(keyprovider_token):

    url = f'{config.appserver_url}/login/{userid}/1/1/0/{keyprovider_token}'
    # url = config.appserver_url+'/login/29/3/4/5/6'+keyprovider_token
    api_result = requests.get(url)
    result = api_result.json()
    print(result)
    return result['token']

#------------------------------------------------------------------------------------------------------------------------------------------------  
# because this is run in a server it has access to get keyprovider's token directly via intranet
def get_keyprovider_token():
    response = requests.get(config.keystoreURL)
    json = response.json()
    key1 = json['key1']
    key2 = json['key2']

    return key1 
#------------------------------------------------------------------------------------------------------------------------------------------------
def process_auto_portfolios(appserver_token): # create auto portfolio for today only

    url = f'{config.appserver_url}/process_auto_portfolio?token={appserver_token}'



    # TW2 A2-M2: route is now POST-only.
    result = requests.post(url, json={})
    if result.status_code > 201 : print('process_auto_portfolio ',result.status_code,result.text,result.reason)
    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------------------------------------------------------
def process_auto_portfolios_by_date(appserver_token,portfolio_date): # this is used to create multiple days in the future instead of just today like process_auto_porfolios

    url = f'{config.appserver_url}/process_auto_portfolio/{portfolio_date}?token={appserver_token}'
    # TW2 A2-M2: route is now POST-only.
    result = requests.post(url, json={})
    if result.status_code > 201 : print('get_chart_data returned',result.status_code,result.text,result.reason)
    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    keyprovider_token=get_keyprovider_token()
    appserver_token=login_appserver(keyprovider_token)

    # check if multiple days are being created - setting is in config_autotrade
    # process_days = ['today','today+1','today+2','2023-12-20']
    for d in config_autotrade.process_days:
        print('processing auto portfolio for this date: ',d)
        process_auto_portfolios_by_date(appserver_token,d)

    


    # response=process_auto_portfolios(appserver_token)
    # print(response)

