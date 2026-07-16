#------------------------------------------------------------------------------------------------------------
# Part 1 these are api calls for appserver.py to call another appserver.py action over HTTP
#------------------------------------------------------------------------------------------------------------
# this program is are the remote api calling appserver apis from python.  these are the same apis used in the React app 5/8/2024
# there are 10 flask functions that either call to read opportunities or csvs in the data folder of the appserver
# these helpers call config.appserver_url. (The old "central data server" mode was a TW1
# experiment never implemented in TW2; it and its config vars were removed 2026-05-21.)
# the list of functions are:

# OppList4(resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0',symbol='')
# getChartData4(resourceID, date, symbol, daysOut, yrs,cut_off_year=0)
# getYearsMetaData2(resourceID, year, month, day)
# getHistory2(resourceID, symbol, d0, d1)
# getStockMetaData(resourceID, symbol)
# getListSymbols(resourceID)  
# getStockLastPrice(resourceID, symbol)
# getStockPriceByDate(resourceID, symbol,date)
# get_consolidated_seasonal_chart2(resourceID,symbol,sy,chart_start_date)
# get_security_price can call get_remote_StockPriceByDate



# import line:
# from appserver_apis import get_remote_OppList4, get_remote_chart_data4, get_remote_YearsMetaData2, get_remote_History2, get_remote_StockMetaData, get_remote_ListSymbols, get_remote_StockLastPrice, get_remote_StockPriceByDate, get_remote_consolidated_seasonal_chart2



#----------------------------------------------------------------------------------------------------------------------
# Part 2 this is a program when run nightly, it calls all the 10 year opplist4 for the last 10 days to future 10 days.
# this action loads all the opportunitiesw including active opportunities to redis and then first time access will be
# fast.  If this is not run then everything works fine except if the opplist including its action list is not in redis
# there will be a couple seconds delay the first time this opplist list is called.  the cache expiration is set in this
# file toward the bottom for how long it should keep the information in cache. 5/24/2024
#----------------------------------------------------------------------------------------------------------------------


#------------------------------------------------------------------------------------------------



import pandas as pd
from pooled_http import http as requests
import time
import jwt
import datetime
from datetime import timedelta
import calendar
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

secret_key = '65f3218cd73e46298be64cc6ee682aec'

#------------------------------------------------------------------------------------------------
# this uses a hack to get the token that changes. this hack is off on prod server. it only works on stage
#------------------------------------------------------------------------------------------------
def get_keyprovider_token():

    url = config.keystoreURL
    api_result = requests.get(url)
    result = api_result.json()
    token = result['key1']

    return token
#------------------------------------------------------------------------------------------------
# after logging in, the returned token is used to make other calls to the appserver
#------------------------------------------------------------------------------------------------
def login_appserver(keyprovider_token):

    url = config.appserver_url+'/login/28/3/4/5/'+keyprovider_token

    print('logging in to appserver at:',url)

    api_result = requests.get(url)
    result = api_result.json()

    if 'message' in result: # login failed due to timing - happens less than 0.1% of the time - try again
        time.sleep(10)
        api_result = requests.get(url) # try again
        result = api_result.json()
        if 'message' in result: # should not have happened - possibly due to appserver being down - lets log this message or print it
            print('message:',result['message'])
            return -1
        else:
            print('attempt 2 to login succeeded')
    else:
        print('attempt 1 to login succeeded')
    # write_to_log('login_appserver',url,result)
     
    data = jwt.decode(result['token'], secret_key)

    return result['token']
#------------------------------------------------------------------------------------------------


#------------------------------------------------------------------------------------------------
# get opportunities list for the financial group
#------------------------------------------------------------------------------------------------
def get_remote_OppList4(keyprovider_token,resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0',symbol=''):
    
    
    appserver_url = config.appserver_url # this is the local appserver

    urlX = f'{appserver_url}/OppList4/{resourceID}/{month}/{day}/{year1}/{year2}/{day_range}/{oppListExpanded}/{apply_filter}?token={keyprovider_token}'
    # urlP is for debug printing
    urlP = f'{appserver_url}/OppList4/{resourceID}/{month}/{day}/{year1}/{year2}/{day_range}/{oppListExpanded}/{apply_filter}?token='
   
    print('opp_list4 url=',urlP)
   
    api_result = requests.get(urlX)
    result = api_result.json()
    return result
#---------------------------------------------------------------------------------------------------------------
def get_remote_chart_data4(appserver_token,resourceID,opp_date,symbol,daysOut,years,cut_off_year=0):
    
    appserver_url = config.appserver_url

    urlY = appserver_url+'/ChartData4/'+str(resourceID)+'/'+opp_date+'/'+symbol+'/'+daysOut+'/'+str(years)+'?token='+appserver_token
    result = requests.get(urlY)
    if result.status_code > 201 : print('get_chart_data returned',result.status_code,result.text,result.reason)
    api_result = result.json()
    return api_result
#---------------------------------------------------------------------------------------------------------------
def get_remote_YearsMetaData2(appserver_token, resourceID, year, month, day):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/YearsMetaData2/'+str(resourceID)+'/'+str(year)+'/'+str(month)+'/'+str(day)+'?token='+appserver_token
    result = requests.get(urlY)
    if result.status_code > 201 : print('YearsMetaData2 returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_History2(appserver_token,resourceID, symbol, d0, d1):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/ChartHistorical2/'+str(resourceID)+'/'+symbol+'/'+d0+'/'+d1+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getHistory2 returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_StockMetaData(appserver_token, resourceID, symbol):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/StockMetaData/'+str(resourceID)+'/'+symbol+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('StockMetaData returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_ListSymbols(appserver_token,resourceID):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/GetListSymbols/'+str(resourceID)+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('GetListSymbols returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_StockLastPrice(appserver_token, resourceID, symbol):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/StockLastPrice/'+str(resourceID)+'/'+symbol+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('GetListSymbols returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_StockPriceByDate(appserver_token, resourceID, symbol,date):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/getStockPriceByDate/'+str(resourceID)+'/'+symbol+'/'+date+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getStockPriceByDate returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_consolidated_seasonal_chart2(appserver_token,resourceID,symbol,seasonal_years,chart_start_date):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/consolidated_seasonal_chart2/'+str(resourceID)+'/'+symbol+'/'+str(seasonal_years)+'/'+chart_start_date+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getStockPriceByDate returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_security_price(resourceID,symbol,date):
    appserver_url = config.appserver_url

    urlY = appserver_url+'/consolidated_seasonal_chart2/'+str(resourceID)+'/'+symbol+'/'+str(seasonal_years)+'/'+chart_start_date+'?token='+appserver_token

    print('urlY = ',urlY)
#------------------------------------------------------------------------------------------------
def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
#------------------------------------------------------------------------------------------------
if __name__ == "__main__":

    print('running a test opplist api')

    keyprovider_token = get_keyprovider_token()
    appserver_token   = login_appserver(keyprovider_token)

    # Define variables
    resourceID = "1" 
    month     = 'May'  
    day       = '9'       
    year1     = '10'
    year2     = '10'  
    day_range = '10-40'  
    oppListExpanded = '0'  
    apply_filter = '0' 
    result = 'uncomment one of the functions for testing'
    # to test any of the 10 remote functions, uncomment one

    # result = get_remote_OppList4(appserver_token,resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0')
    # result = get_remote_chart_data(appserver_token, resourceID,'2021-05-09','AAPL', '10', '10')
    # result = get_remote_YearsMetaData2(appserver_token, resourceID, '2024', '3', '14')
    # result = get_remote_History2(appserver_token,resourceID, 'AAPL', '2021-04-09', '2021-05-10')
    # result = get_remote_StockMetaData(appserver_token, resourceID, 'AAPL')
    # result = get_remote_ListSymbols(appserver_token,resourceID)
    # result = get_remote_StockLastPrice(appserver_token, resourceID, 'AAPL')
    # result = get_remote_StockPriceByDate(appserver_token, resourceID, 'AAPL','2020-05-09')
    # result = get_remote_consolidated_seasonal_chart2(appserver_token,resourceID,'AAPL',10,'2024-01-02')


    # print(result)

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    days_before_and_after = 10 # this is number of days before today and after today to run opplist overnight to put the data in redis

    day1date = inc_date_day(today_date, -days_before_and_after)


    year1      = '10'
    # year2      = '10'
    year2_list = ['10','9'] 

    # call opplist4 in order to force the data into redis the night before -
    for year2 in year2_list:
        print('year2=',year2)
        for resource_id in config.available_resources:
            print('###########################################')
            print(f'#####################{resource_id}#####################')
            print('###########################################')
            # if resource_id !='4': continue # remove
            for i in range (0,days_before_and_after*2):
                d = inc_date_day(day1date, i)

                sp = d.split('-')
                month     = calendar.month_name[int(sp[1])]
                day       = sp[2]     
                day_range = '-'  
                oppListExpanded = '0'  
                apply_filter = '0' 

                print(resource_id, month, day, year1, year2,day_range,oppListExpanded)
                result=get_remote_OppList4(appserver_token,resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0')

                time.sleep(0.2)
