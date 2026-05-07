from tradier_api import get_quotes,get_one_order,get_orders,get_positions
import json
import datetime
import time



#------------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    # print('appserver functions for autotrading, used by appserver_async.py')

    import redis
    import sys
    import config_tradier
    import config_autotrade


    

    userid_list = config_autotrade.userid
    
    # right now we only use one userid in config_autotrade - it should be expanded to multiple when trading multiple accounts
    userid = userid_list[0]
    account_id = config_tradier.ACCOUNT_ID

    redis_client1  = redis.Redis(host='localhost', port=6379, db=1)
    redis_client2  = redis.Redis(host='localhost', port=6379, db=2)


    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 


    # remove AVGO from live_trades

    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)
        print(live_trades,'\n\n')

        updated_live_trades = []

        for trade in live_trades:
            if trade['symbol'] == 'AVGO':
                continue

            updated_live_trades.append(trade)

        # now rewrite live_trades to redis
        print('\n',updated_live_trades)
        redis_client1.set('live_trades', json.dumps(updated_live_trades))
            

            
   