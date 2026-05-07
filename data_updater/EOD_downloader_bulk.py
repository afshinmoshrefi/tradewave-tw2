# updated to new format of csv per exchange folder 6/5/2022

# bulk downloads one file containing the last day updates for each exchange and can quickly update all csv files -

# should run EOD_downloader2.py in the middle of night or weekends to get any issues corrected 

import requests
import glob
import os
import pandas as pd
import json
import sys
import time
from os.path import exists
import datetime

sys.path.insert(0, '/home/flask')
import config

token = os.environ['EOD_TOKEN']
cut_days = 223

#--------------------------------------------------------------------------------------------


        
#--------------------------------------------------------------------------------------------
if __name__ == '__main__':


    todayDate = datetime.datetime.today().strftime('%Y-%m-%d')

    # creating this file as a marker of when EOD_downloader runs last
    f = open("/home/flask/data_updater/EOD2_bulk_run.xxx", "w")
    f.close()

    t1=time.time()

    groups = config.exchange_mapping
    exchange_list = list(set(groups.values())) # list of exchanges
    

    for exchange in exchange_list:

        # if exchange != 'US':continue

        print(exchange)
        

        df=pd.DataFrame(columns=['symbols','name'])
        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                print(config.available_resources_path[k])
                df = pd.concat([df,pd.read_csv(config.available_resources_path[k])])
        slist = list(df['symbols'])
        csv_path = config.csv_folder+exchange+'/'
        # print(exchange,df.shape[0],csv_path,slist,'\n\n')
        # update_resource_group(exchange,slist,csv_path)

       
        # following commented out is for saving the bulk file for dev and experiments

        # bulk_filename = 'bulk_'+exchange+'.csv'

        # if exists(bulk_filename):
        #     dfb = pd.read_csv(bulk_filename)
        # else:
        #     print('api downloading ',exchange)
        #     eid = exchange
        #     if eid == 'ETF':eid='US'
        #     apiURL = f'https://eodhistoricaldata.com/api/eod-bulk-last-day/{eid}?api_token={token}&fmt=json'
        #     print(apiURL)
        #     api_result = requests.get(apiURL)
        #     api_response = api_result.json()
        #     dfb = pd.DataFrame(api_response)
        #     dfb.to_csv('bulk_'+exchange+'.csv')  
        

        print('api downloading bulk file for',exchange)
        eid = exchange
        if eid == 'ETF':eid='US'
        apiURL = f'https://eodhistoricaldata.com/api/eod-bulk-last-day/{eid}?api_token={token}&fmt=json'
        print(apiURL)
        api_result = requests.get(apiURL)
        api_response = api_result.json()
        dfb = pd.DataFrame(api_response)
        
        
        dfb=dfb[['code', 'date', 'open', 'high','low', 'close', 'adjusted_close', 'volume']]

        
        for s in slist:
            print(s)
            dfx = dfb[dfb['code']==s] # get the single line of daily result
            if dfx.shape[0]==1:
                dfs = dfx[['date', 'open', 'high','low', 'close','volume']]
                dfs['adj_factor'] = 1
                bulk_date = dfs['date'].iloc[0]
                # open the existing csv now
                csv_fn = config.csv_folder+exchange+'/'+s+'.csv'
                if exists(csv_fn):
                    dfe = pd.read_csv(csv_fn)
                    dfe = dfe[['date', 'open', 'high','low', 'close','volume','adj_factor']]
                    last_date = dfe['date'].iloc[-1]
                    if bulk_date>last_date:
                        dff = pd.concat([dfe,dfs]).reset_index(drop=True)
                        dff.to_csv(csv_fn)
                else: continue # file not found can't update single line in it
            else:
                if dfx.shape[0]==0:
                    print('Nothing returned: exchange:',exchange,'symbol:',s)
                else:
                    print('problem with exchange:',exchange,'symbol:',s,'returned',df.shape[0],'rows')

    t2=time.time()
    print(round(t2-t1,2),'seconds',round((t2-t1)/60,2),'minutes')   
