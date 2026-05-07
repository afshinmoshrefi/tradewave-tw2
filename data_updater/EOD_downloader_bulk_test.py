# updated to new format of csv per exchange folder 6/5/2022

import requests
import glob
import os
import pandas as pd
import json
import sys
import time

sys.path.insert(0, '/home/flask')
import config

token = os.environ['EOD_TOKEN']
cut_days = 223

#--------------------------------------------------------------------------------------------


        
#--------------------------------------------------------------------------------------------
if __name__ == '__main__':

    # creating this file as a marker of when EOD_downloader runs last
    f = open("/home/flask/data_updater/EOD2_bulk_run.xxx", "w")
    f.close()



    groups = config.exchange_mapping
    exchange_list = list(set(groups.values())) # list of exchanges
    

    for exchange in exchange_list:

        if exchange != 'GBOND':continue

        print(exchange)

        df=pd.DataFrame(columns=['symbols','name'])
        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                df = pd.concat([df,pd.read_csv(config.available_resources_path[k])])
        slist = list(df['symbols'])
        csv_path = config.csv_folder+exchange+'/'
        print(exchange,df.shape[0],csv_path,slist,'\n\n')
        # update_resource_group(exchange,slist,csv_path)


        # # dfb = pd.read_csv('bulk.csv')
        apiURL = f'https://eodhistoricaldata.com/api/eod-bulk-last-day/US?api_token={token}&fmt=json'
        print(apiURL)
        api_result = requests.get(apiURL)
        api_response = api_result.json()
        dfb = pd.DataFrame(api_response)
        
        dfb.to_csv('bulk_test.csv')


        # dfb.to_csv('bulk.csv')  #tmp
        # dfb=dfb[['code', 'date', 'open', 'high','low', 'close', 'adjusted_close', 'volume']]
        # for s in slist:
        #         print(s)
        #         df = dfb[dfb['code']==s]
        #         if df.shape[0]==1:
        #             dfs =df[['date', 'open', 'high','low', 'close', 'adjusted_close', 'volume']]
        #             bulk_date = dfs['date'].iloc[0]
        #             # open the existing csv now
        #             dfe = pd.read_csv(csv_folder+exchange+'/'+s+'.csv')
        #             last_date = dfe['date'].iloc[-1]
        #             if bulk_date>last_date:
        #                 dff = pd.concat([dfe,dfs]).reset_index(drop=True)

        #                 dff.to_csv(csv_folder+exchange+'/'+s+'.csv')
        #         else:
        #             print('problem with exchange:',exchange,'symbol:',s,'returned',df.shape[0],'rows')

        