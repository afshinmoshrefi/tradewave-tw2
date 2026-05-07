# this flask app will fetch data from a mounted update_server URL 
# the client's IP should be enabled in nginx conf file like it was on keyprovider

# from flask import Flask, jsonify
import requests
import os
import time
import datetime
from datetime import timedelta
import pandas as pd
from os import listdir


data_dir = '/home/flask/data/'
csv_dir = data_dir+'csv/'
update_archive_dir = '/home/flask/data_updater/update_archive/'
eod_api_url = 'https://api.marketstack.com/v1/eod'
update_server_url = 'https://u.tararesearch.net/'

today_date = datetime.datetime.now().strftime("%Y-%m-%d")
yd = datetime.datetime.now() - timedelta(1)
yesterday_date = datetime.datetime.strftime(yd,"%Y-%m-%d")
date_time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
date_now = datetime.datetime.now().strftime("%Y-%m-%d")
update_filename_today = update_archive_dir+date_now+'.csv'
update_filename_yesterday = update_archive_dir+yesterday_date+'.csv'


# --------------------------------------------------------------------------------------------------------
def get_update_for_date(date):

    url = update_server_url+'updates/'+date
    api_result = requests.get(url)
    api_result_json = api_result.json()
    # print(api_result_json)
    # ll = api_result_json['update'] # this is a list of lists v
    return (api_result_json)
#-----------------------------------------------------------------------------
def update_csvs(df):
    csv_list = listdir(csv_dir)
    for f in csv_list:
        sym = f[:-4]
        # print('csv file:', csv_dir+f)
        dfcsv = pd.read_csv(csv_dir+f)
        dfcsv = dfcsv[['date', 'open', 'high', 'low', 'close', 'volume']]
        last_date = dfcsv['date'].iloc[dfcsv.shape[0]-1]
        # print('last_date in csv:', last_date)
        dfa = df[(df['symbol'] == sym.upper()) & (df['date'] > last_date)]
        if dfa.shape[0] > 0 :
            dfa = dfa[['date', 'open', 'high', 'low', 'close', 'volume']]
            dfcsv = dfcsv.append(dfa).sort_values('date').reset_index(drop=True)
            dfcsv.to_csv(csv_dir+f, index=False)
        else:
            print(sym+': no updates')
#-----------------------------------------------------------------------------
if __name__ == "__main__":
    print('update client version 1.0')


    f = open('/home/flask/data_updater/success_client.xxx', "w")
    f.close()


    u=get_update_for_date(today_date)
    # u=get_update_for_date(yesterday_date)
    result = u['update']
    # print('result=',result)
    if type(result)==str and result[:2]=='-1':
        print('no updates for this date')
    else:
        df=pd.DataFrame(result,columns=['date','symbol','open','high','low','close','volume'])
        update_csvs(df)
   


