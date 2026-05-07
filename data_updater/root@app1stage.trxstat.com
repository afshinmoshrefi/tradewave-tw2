# this flask app will fetch data from a mounted update_server URL 
# the client's IP should be enabled in nginx conf file like it was on keyprovider

# from flask import Flask, jsonify
import requests
import os
import sys
import time
import datetime
from datetime import timedelta
import pandas as pd
from os import listdir
sys.path.insert(0, '/home/flask')
import config


data_dir = config.ddir
csv_dir = data_dir+'csv/'

csv_columns = ['date', 'open', 'high', 'low', 'close','volume', 'adj_factor']



#-----------------------------------------------------------------------------
if __name__ == "__main__":
    print('update client version 1.1')


    f = open('/home/flask/data_updater/success_client.xxx', "w")
    f.close()


    csv_list = listdir(csv_dir) # list of all file names in csv_dir
    sym_list = [x[:-4] for x in csv_list] # remove .csv

    count = 0
    for s in csv_list:
        
        print('starting with',s)

        df = pd.read_csv(csv_dir+s)
        df=df[csv_columns] # get rid of any unneeded columns

        symbol = s[:-4]
        last_date = df.iloc[-1]['date']
        url = config.update_server+'update/'+symbol+'/'+last_date
        

        result = requests.get(url)
        result = result.json()

        if result['update'] != '-1' :

            dfu = pd.DataFrame(result['update'] , columns = csv_columns)
            df = df.append(dfu).reset_index(drop=True)
            df.to_csv(csv_dir+s)
            print(count,'-',dfu.shape[0],'rows updated for',s)
        else:
            print(count,s[:-4],'not found')

        count+=1
        
        
       