# this is a copy of updated_canceled_orders - only change is to remove filled orders 8/13/2024
# this thing removes filled orders - use with a lot of care - it could ruin things
# I use it when I want to remove a trade that I don't want in the portfolio anymore.  it changes the airplane color
# from orange to black - then it can be removed - its really just for development mainly

import redis
import json
import sys
import requests
import pprint

sys.path.insert(0, '/home/flask')
import config

import config_autotrade
from pprint import pprint

from tradier_api import get_quotes, get_creditspreads_for_opportunity,get_accounting_info,desired_selections_bullish_bearish,get_positions
from tradier_api import place_multileg_option_trade,get_orders,cancel_order,get_brokerage_clock,get_position_from_filled_order,get_one_order # 1/2/2024



redis_client  = redis.Redis(host='localhost', port=6379, db=0)  # used as a cache
redis_client2 = redis.Redis(host='localhost', port=6379, db=2)  # used as a db






# find index for dr_id = 16
# dr_id = '16' # the index being updated
# idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id)]
# idx = idx[0]

# print(redis_user_reports_list[idx])
# # orders = '9743731,9740790,9743789'
# orders = '735601'
# redis_user_reports_list[idx]['orders'] = orders

# redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis


#-----------------------------------------------------------------------------------------------------------------
def remove_canceled_orders(order_list):

    tmp_order_list = []
    # list of order ids in the system fetched orders
    # system_order_id_list = [o['id'] for o in system_orders]



    for order_id in order_list:
        
        # get the order_dictionary for this order
        order_dict=get_one_order(config_autotrade.account_id,order_id)

        print('\n\n',order_dict['order']['status'],'\n\n')

        if order_dict['order']['status'] == 'filled' :
            continue # dont want to keep this order number
        
        tmp_order_list.append(order_id)


    return tmp_order_list

#####################################################################################################################
#                                                    Main Program
#####################################################################################################################
if __name__ == '__main__':

    user_id = '16'

    redis_key_user_reports  = f'user_reports_{user_id}'
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    redis_user_reports_list = json.loads(redis_user_reports_list)

    # get all the orders
    # orders = get_orders(config_autotrade.account_id)

    # get all the positions
    positions = get_positions(config_autotrade.account_id)

    tmp_redis_user_reports_list = redis_user_reports_list.copy() 

    for opp in tmp_redis_user_reports_list:
        if 'orders' not in opp: continue    # there is no order field

        print(opp['symbol'])
        # if opp['symbol'] == 'MSFT': continue

        order_list = opp['orders'].split(',') # list of orders for this opp
        order_list = [int(order) for order in order_list]

        # if opp['symbol'] == 'MSFT':
        #     print('msft order_list =',order_list)
        #     new_order_list = []
        # else:


        new_order_list = remove_canceled_orders(order_list)


        print(new_order_list)
        print(opp)

        if len(new_order_list) == 0:
            del opp['orders']
        else:
            new_order_list_str = [str(order) for order in new_order_list]
            opp['orders']=','.join(new_order_list_str)

    redis_client2.set(redis_key_user_reports,json.dumps(tmp_redis_user_reports_list)) # set the list to the new list on redis


   
        

        
            






