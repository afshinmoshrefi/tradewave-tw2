# updated to new format of csv per exchange folder 6/5/2022

import requests
import glob
import os,os.path
import pandas as pd
import json
import sys
import time

sys.path.insert(0, '/home/flask')
import config

token = os.environ['EOD_TOKEN']
cut_days = 223

#--------------------------------------------------------------------------------------------
# download from EOD
def get_sym_df(symbol,exchangeID):


    print('\n\ndownloading',symbol,'from eodhistoricaldata.com')
    eid = exchangeID
    if eid == 'ETF':eid='US'
    apiURL = f'https://eodhistoricaldata.com/api/eod/{symbol.strip()}.{eid}?api_token={token}&period=d&fmt=json'
    print('\n\napiURL=',apiURL,'\n\n')

    try:    
        api_result = requests.get(apiURL)
    except requests.exceptions.RequestException.HTTPError as e:  # This is the correct syntax
        print('exeption on download:')
        print('url=',apiURL)
        print('exception:',e.response.text)

    if 'Not Found' in api_result.content.decode("utf-8") :
        print(symbol,'not found')
        return pd.DataFrame()
    api_response = api_result.json()
    df = pd.DataFrame(api_response)

    return df
#--------------------------------------------------------------------------------------------
# use the adjusted_close to calculate a ratio - use the ratio to adjust open high low and close
def adjust(df): 
    
    df['adj_factor']=df['adjusted_close']/df['close']
    df['open']=df['open']*df['adj_factor']
    df['high']=df['high']*df['adj_factor']
    df['low']=df['low']*df['adj_factor']
    df['close']=df['close']*df['adj_factor']
    df = df[['date', 'open', 'high', 'low', 'close','volume','adj_factor']]
    return df
#--------------------------------------------------------------------------------------------
# trim bad years with too many missing days - hopefully its very old years trimmed
def trim_df(dfs):
    y0 = int(dfs['date'].iloc[0][:4])               # first year in the dataset
    y1 = int(dfs['date'].iloc[dfs.shape[0]-1][:4])  # last year in the dataset
    # print(y0,y1)
    years_dict={}
    
    for y in range(y0+1,y1):
        df2=dfs[dfs['date'].str[:4]==str(y)]
        days=df2.shape[0]
        years_dict[y]=days
        
    earliest_year_to_keep = {}
    years_list = list(years_dict.keys())[::-1]

    earliest_year_to_keep=0
    for y in years_list:
        if years_dict[y]<cut_days:break
        else : earliest_year_to_keep = y

    # cut the dataframe with the earliest_year_to_keep and throw older data out
    first_date_in_csv = str(earliest_year_to_keep)+'-01'+'-01'
    df=dfs[dfs['date']>first_date_in_csv]

    return df

#--------------------------------------------------------------------------------------------
# update all csvs for the resource group
def update_resource_group(exchange,slist,csv_path):



    if not os.path.exists(csv_path) : os.makedirs(csv_path)

    slist_str = [str(item) for item in slist]

    c  = 0
    for ss in slist_str:
        if '.' in ss: continue # avoiding stocks like bk.b

        c=c+1

        # if ss != 'SPX': continue # remove



        s = ss
        if ss in config.alias_symbols.keys(): # this is to change GSPC to SPX 10/20/2022
            s = config.alias_symbols[ss]


      

        dfs=get_sym_df(s,exchange)



        if dfs.shape[0]>0:
            dfs = adjust(dfs)
        


            dfs=trim_df(dfs)

            print(f'{c}/{len(slist_str)} -','saving ... ',ss,exchange,csv_path)

            

            dfs = dfs.reset_index(drop=True)
            dfs.to_csv(csv_path+ss+'.csv')        
#--------------------------------------------------------------------------------------------
if __name__ == '__main__':

    # creating this file as a marker of when EOD_downloader runs last
    f = open("/home/flask/data_updater/EOD2_run.xxx", "w")
    f.close()

    t1=time.time()

    groups = config.exchange_mapping
    exchange_list = list(set(groups.values())) # list of exchanges
    
    c = 0 

    for exchange in exchange_list:

        c = c+1

        # if exchange == 'US' or exchange == 'FOREX': continue # remove
        # if exchange != 'LSE':continue #################################remove

        print('processing exchange =',f'{c}/{len(exchange_list)} in',exchange)


        dtypes = {'symbols': 'str', 'name': 'str'}
        df = pd.DataFrame(columns=dtypes.keys()).astype(dtypes)

        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                dfm = pd.read_csv(config.available_resources_path[k],dtype=dtypes)
                dfm = dfm[['symbols','name']]
                df = pd.concat([df,dfm])

        df['symbols'] = df['symbols'].astype(str)

        slist = list(set(list(df['symbols'])))
        slist = [str(item) for item in slist]
        slist = sorted(slist)

    

        csv_path = config.csv_folder+exchange+'/'
        # print(exchange,df.shape[0],csv_path,slist,'')
        update_resource_group(exchange,slist,csv_path)


    t2=time.time()
    print(round(t2-t1,2),'seconds',round((t2-t1)/60,2),'minutes')   
