
import requests
import glob
import os
import pandas as pd
import json
sys.path.insert(0, '/home/flask')
import config


data_dir = '/home/flask/data/'
csv_dir  = data_dir+'csv/'
if not os.path.exists(csv_dir): os.makedirs(csv_dir)
token = os.environ['EOD_TOKEN']
cut_days = 223



###############################################################################
groupID=1 # 0 is dj30 1 is sp500 - this is the list to use for downloading
###############################################################################



bundle_symbol_files = glob.glob(data_dir+'*.csv')
bundle_symbol_files = [x.replace('\\','/') for x in bundle_symbol_files]
bundle_folder = [os.path.basename(x)[:-12] for x in bundle_symbol_files]
bundle_folder,bundle_symbol_files



# create folders for the bundles if they don't exist
for f in bundle_folder:
    p = data_dir+f
    if not os.path.exists(p): os.makedirs(p)



# mapping for symbol bundles and exchanges
# add mapping here for new bundles
# exchange_mapping=[
#   {'COMM':'COMM'},
#   {'sp500':'US'},
#   {'INDX_USA':'INDX'},
#   {'dj30':'US'},
#   {'FOREX':'FOREX'},
#   {'FOREX_LQ':'FOREX'},
#   {'GBOND':'GBOND'}
# ]






def get_sym_df(symbol,exchangeID):
    print('downloading',symbol,'from eodhistoricaldata.com')
    apiURL = f'https://eodhistoricaldata.com/api/eod/{symbol}.{exchangeID}?api_token={token}&period=d&fmt=json'
#     print(apiURL)
    api_result = requests.get(apiURL)
    if 'Not Found' in api_result.content.decode("utf-8") :
        print(symbol,'not found')
        return pd.DataFrame()
    
    api_response = api_result.json()
    df = pd.DataFrame(api_response)

    return df




# use the adjusted_close to calculate a ratio - use the ratio to adjust open high low and close
def adjust(df): 
    
    df['adj_factor']=df['adjusted_close']/df['close']
    df['open']=df['open']*df['adj_factor']
    df['high']=df['high']*df['adj_factor']
    df['low']=df['low']*df['adj_factor']
    df['close']=df['close']*df['adj_factor']
    df = df[['date', 'open', 'high', 'low', 'close','volume','adj_factor']]
    return df


# adjust all the csvs using adjusted_close ratio
dfs = pd.read_csv(bundle_symbol_files[groupID])
dfs['symbols']=dfs['symbols'].str.upper()

for s in list(dfs['symbols']):
    csv_exists =  os.path.isfile(csv_dir+s)  
    if csv_exists: continue  # skip loading if already downloaded
    df=get_sym_df(s,'US')
    if df.shape[0]>0:
        df=adjust(df)
        df.to_csv(csv_dir+s+'.csv')
        print('done with:',s)
    else:
        print('skipping:',s)
print('start trimming....')
###################################################
#################### trim  ########################
###################################################

sym_info={} # holds info about number of days for each year of each ticker symbol data

for s in list(dfs['symbols']):
    f=csv_dir+s+'.csv'

    csv_exists =  os.path.isfile(f)  
    if csv_exists == False: continue  # skip loading if not downloaded

    df = pd.read_csv(f)
    y0 = int(df['date'].iloc[0][:4])
    y1 = int(df['date'].iloc[df.shape[0]-1][:4])
    
    years_dict={}
    
    for y in range(y0+1,y1):
        df2=df[df['date'].str[:4]==str(y)]
        days=df2.shape[0]
        
        years_dict[y]=days
        
        if days < 240:
            print(s,y,days)
    
    sym_info[s]=years_dict

# cut to the nearest year that has less data in days than 

earliest_year_to_keep = {}

for s in sym_info.keys():
    years_list = list(sym_info[s].keys())[::-1]
    for i in years_list:
        if sym_info[s][i] < cut_days:
            earliest_year_to_keep[s]=i+1
            break



earliest_year_to_keep



# cut the bad years data out now - this is because number of days was less than cut_days = 223
for s in earliest_year_to_keep.keys():
    f=csv_dir+s+'.csv'
    df = pd.read_csv(f)
    size1 = df.shape[0]
    first_date_in_csv = str(earliest_year_to_keep[s])+'01'+'01'
    df=df[df['date']>first_date_in_csv]
    size2 = df.shape[0]
    print(s,earliest_year_to_keep[s],size1,size2)
    df.to_csv(f)










