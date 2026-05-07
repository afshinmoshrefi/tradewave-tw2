# these are shared functions across other python scripts for blog generation

import pandas as pd
import json
import os
import sys
import datetime
from datetime import timedelta
sys.path.insert(0, '/home/flask')
import config


#-------------------------------------------------------------------------------------------------
def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')  
#-------------------------------------------------------------------------------------------------
def diff_between_dates(date2,date1):

    d1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(date2, "%Y-%m-%d")

    difference = d2 - d1
    days = difference.days
    return int(days)
#------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------
# action 'add'  'get'
#------------------------------------------------------------------------------------------------
def json_log(log_filename, action, dict):
    file_exists = os.path.exists(log_filename)

    if action == 'add':
        with open(log_filename, 'a') as f:
            if file_exists:
                f.write(',\n')
            # dict_normalized = dict['event-detail']
            # dict_normalized['type'] = dict['type']
            # dict_normalized['local_datetime'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            json.dump(dict, f, indent=4)
            f.write('\n')

    if action == 'get':  # return the json as a list of dictionaries
        if file_exists:
            with open(log_filename, 'r') as f:
                dict_list = f.read()
                dict_list = '[\n' + dict_list + '\n]'
            return json.loads(dict_list)
#------------------------------------------------------------------------------------------------
def json_log_to_df(json_archive_filename):

    j=json_log(json_archive_filename,'get',{})
    df = pd.DataFrame(j)
    return df

#------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------
if __name__ == "__main__":

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    json_archive_filename = f'/home/flask/appserver/appserver/logs/trade-processor/trade_order_log_{today_date}.json'
    j=json_log(json_archive_filename,'get',{})

    # Convert the list of JSON objects to a pandas DataFrame
    df = pd.DataFrame(j)
    df.fillna(0, inplace=True)
    df['parent_id'] = df['parent_id'].astype(int)
    print(df)
    # Save the DataFrame as a CSV file
    # df.to_csv('output.csv', index=False)

    
    
