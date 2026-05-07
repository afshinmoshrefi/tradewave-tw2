# this program is for testing calling appserver apis from python.  these are the same apis used in the React app 5/8/2024

import pandas as pd
import requests
import sys
import jwt

sys.path.insert(0, '/home/flask')
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

    if config.central_data_consumer:
        url = config.central_server_url+'/login/28/3/4/5/'+keyprovider_token
    else:
        url = config.appserver_url+'/login/28/3/4/5/'+keyprovider_token
    
    print(url)

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
    print('dddddddddddata = ',data)



    return result['token']
#------------------------------------------------------------------------------------------------


#------------------------------------------------------------------------------------------------
# get opportunities list for the financial group
#------------------------------------------------------------------------------------------------
def get_remote_OppList4(keyprovider_token,resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0',symbol=''):
    
    
    appserver_url = config.central_server_url # only used when central_data_consumer is True


    urlX = f'{appserver_url}/OppList4/{resourceID}/{month}/{day}/{year1}/{year2}/{day_range}/{oppListExpanded}/{apply_filter}?token={keyprovider_token}'
    api_result = requests.get(urlX)
    result = api_result.json()
    return result
#---------------------------------------------------------------------------------------------------------------
def get_remote_chart_data(appserver_token,resourceID,opp_date,symbol,daysOut,years,cut_off_year=0):
    
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/ChartData4/'+str(resourceID)+'/'+opp_date+'/'+symbol+'/'+daysOut+'/'+str(years)+'?token='+appserver_token
    result = requests.get(urlY)
    if result.status_code > 201 : print('get_chart_data returned',result.status_code,result.text,result.reason)
    api_result = result.json()
    return api_result
#---------------------------------------------------------------------------------------------------------------
def get_remote_YearsMetaData2(appserver_token, resourceID, year, month, day):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/YearsMetaData2/'+str(resourceID)+'/'+str(year)+'/'+str(month)+'/'+str(day)+'?token='+appserver_token
    result = requests.get(urlY)
    if result.status_code > 201 : print('YearsMetaData2 returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_History2(appserver_token,resourceID, symbol, d0, d1):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/ChartHistorical2/'+str(resourceID)+'/'+symbol+'/'+d0+'/'+d1+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getHistory2 returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_StockMetaData(appserver_token, resourceID, symbol):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/StockMetaData/'+str(resourceID)+'/'+symbol+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('StockMetaData returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_ListSymbols(appserver_token,resourceID):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/GetListSymbols/'+str(resourceID)+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('GetListSymbols returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_StockLastPrice(appserver_token, resourceID, symbol):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/StockLastPrice/'+str(resourceID)+'/'+symbol+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('GetListSymbols returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result

#------------------------------------------------------------------------------------------------
def get_remote_StockPriceByDate(appserver_token, resourceID, symbol,date):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/getStockPriceByDate/'+str(resourceID)+'/'+symbol+'/'+date+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getStockPriceByDate returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------
def get_remote_consolidated_seasonal_chart2(appserver_token,resourceID,symbol,seasonal_years,chart_start_date):
    appserver_url = config.central_server_url # only used when central_data_consumer is True

    urlY = appserver_url+'/consolidated_seasonal_chart2/'+str(resourceID)+'/'+symbol+'/'+str(seasonal_years)+'/'+chart_start_date+'?token='+appserver_token

    print('urlY = ',urlY)

    result = requests.get(urlY)
    if result.status_code > 201 : print('getStockPriceByDate returned',result.status_code,result.text,result.reason)

    api_result = result.json()
    return api_result
#------------------------------------------------------------------------------------------------


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


    # result = get_remote_OppList4(appserver_token,resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0')
    # result = get_remote_chart_data(appserver_token, resourceID,'2021-05-09','AAPL', '10', '10')
    # result = get_remote_YearsMetaData2(appserver_token, resourceID, '2024', '3', '14')
    # result = get_remote_History2(appserver_token,resourceID, 'AAPL', '2021-04-09', '2021-05-10')
    # result = get_remote_StockMetaData(appserver_token, resourceID, 'AAPL')
    # result = get_remote_ListSymbols(appserver_token,resourceID)
    # result = get_remote_StockLastPrice(appserver_token, resourceID, 'AAPL')
    # result = get_remote_StockPriceByDate(appserver_token, resourceID, 'AAPL','2020-05-09')
    # result = get_remote_consolidated_seasonal_chart2(appserver_token,resourceID,'AAPL',10,'2024-01-02')


    print(result)