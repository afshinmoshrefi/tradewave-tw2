# this flask app will serve daily update files in update_archive to remote systems
# the remote server's IP should be enabled in nginx conf file like it was on keyprovider
# version 1.2 uses the new format of csvs in exchange folder 

from flask import Flask, jsonify
import os
import time
import datetime
import pandas as pd
import sys

sys.path.insert(0, '/home/flask')
import config

data_dir = config.ddir
csv_dir = config.csv_folder

today_date = datetime.datetime.now().strftime("%Y-%m-%d")

date_time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
date_now = datetime.datetime.now().strftime("%Y-%m-%d")


app = Flask(__name__)


@app.route('/', methods=['GET'])
def root():
    logged_in = False

    return jsonify({'update_server': 'ver 1.2'})
# -------------------------------------------------------------------------------------------------------
# returns data for number of days


@app.route('/update/<string:resourceID>/<string:symbol>/<string:last_date>', methods=['GET'])
def update(resourceID,symbol,last_date):

    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500 6/4/2022
    print(exchange,resourceID)
    fn_csv = config.csv_folder+exchange+'/'+symbol+'.csv'
    

    exist = os.path.isfile(fn_csv)

    if not exist:
        # return jsonify({'update': '-1'})
        return jsonify({'update': 'file missing:'+fn_csv})


    df = pd.read_csv(fn_csv)
    df = df[['date', 'open', 'high', 'low', 'close', 'volume','adj_factor']]

    df=df[df['date']>last_date]

    update_json = df.values.tolist()

    return jsonify({'update': update_json})

# --------------------------------------------------------------------------------------------------------


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
