from tradier_api import get_quotes,get_one_order,get_orders,get_positions
import json
import datetime
import time

#-----------------------------------------------------------------------------------------------------
# runs when status of a trade changes - update values in redis db=1
# success return 1 while not finding the order returns 0
# symbol is for security only
#-----------------------------------------------------------------------------------------------------
def update_live_trade(redis_client1,account_id,data):

    print('##################### updating live_trades #####################')
    print('dddddddddddata=',data)
    order_id = data['id']
    parent_id = data.get('parent_id', 0) # parent_id is present when event is for an individual option in a spread
    
    print('parent_id parent_id parent_id parent_id parent_id =',parent_id)

    # parent_id = data['parent_id'] if data['parent_id'] else 0 # parent_id is present when event is for an individual option in a spread
    time.sleep(1.5) # important must wait because it takes time for appserver to write to redis live_trades file, without delay - it fails
    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 


    # print('----------------------------------------')
    # print('order_id=',type(order_id),order_id)
    # ttt = json.loads(redis_live_trades)
    # open_order_id  = ttt[0]['open_order_id']
    # close_order_id = ttt[0]['close_order_id']
    # print('open_order_id=',type('open_order_id'),open_order_id)
    # print('close_order_id=',type(close_order_id),close_order_id)


    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        for trade in live_trades:
            
            open_order_id   = int(trade['open_order_id']) if trade['open_order_id'] else 0
            close_order_id  = int(trade['close_order_id']) if trade['close_order_id'] else 0
            # print('open close and order_id',open_order_id,close_order_id,order_id)

            print('yyyy ',type(parent_id),type(open_order_id),type(close_order_id) )
            print('XXXXXXXXXXXXXXXXXXXX parent_id  open_order_id close_order_id = ',parent_id,open_order_id,close_order_id)

            # processes opening a trade
            if open_order_id == order_id:
                print('updating open trade in live_trades')
                trade['status'] = data['status']
          
                quote_dict = get_quotes(trade['symbol']) # security price at time option position was filled
                security_price = quote_dict['last']
                # trade['status'] = data['status']
                trade['price_open'] = data['price']
                trade['security_price_open'] = security_price
                trade['open_date'] = data['transaction_date'] 
                # print('\n\n\n final live_trades=',live_trades,'\n\n')
                redis_client1.set('live_trades', json.dumps(live_trades))
                # also update the live_symbols key in redis
                update_live_symbols(redis_client1,live_trades)
                return 1 # means success
                break
            # closing a trade
            elif close_order_id == order_id:

                print('ccccccccccccccccccccccccccccccc-updating close order in livetrade=',trade)
                quote_dict = get_quotes(trade['symbol']) # security price at time option position was filled
                security_price = quote_dict['last']
                print('security_price=',security_price)
                # trade['status'] = data['status']
                
                
                trade['price_close'] = data['avg_fill_price']
                trade['security_price_close'] = security_price
                trade['close_date'] = data['transaction_date'] 
                # print('\n\n\n final live_trades=',live_trades,'\n\n')
                redis_client1.set('live_trades', json.dumps(live_trades))
                # also update the live_symbols key in redis
                update_live_symbols(redis_client1,live_trades)
                return 1 # means success
                break

            elif parent_id == open_order_id: # individual option event 
                print('pppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppp')
                # get details of the child order which is one of the individual options 
                order = get_one_order(account_id,data['id'])
                option0_symbol = trade['option0_symbol']
                option1_symbol = trade['option1_symbol']
                executed_option_symbol  = order['order']['option_symbol']
                avg_fill_price = order['order']['avg_fill_price']
                exec_quantity = data['exec_quantity']
                # assign to the correct option

                if executed_option_symbol == option0_symbol:
                    trade['option0_open_quantity'] = exec_quantity
                    trade['option0_open_price']    = avg_fill_price
                elif executed_option_symbol == option1_symbol:
                    trade['option1_open_quantity'] = exec_quantity
                    trade['option1_open_price']    = avg_fill_price

                redis_client1.set('live_trades', json.dumps(live_trades))
                break
            elif parent_id == close_order_id:
                print('qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq')
                # get details of the child order which is one of the individual options 
                order                   = get_one_order(account_id,data['id'])
                option0_symbol          = trade['option0_symbol']
                option1_symbol          = trade['option1_symbol']
                executed_option_symbol  = order['order']['option_symbol']
                avg_fill_price          = order['order']['avg_fill_price']
                exec_quantity           = data['exec_quantity']

                print('option0_symbol,option1_symbol,executed_option_symbol,avg_fill_price, exec_quantity=',option0_symbol,option1_symbol,executed_option_symbol,avg_fill_price, exec_quantity)         

                # assign to the correct option
                if executed_option_symbol == option0_symbol:
                    trade['option0_close_quantity'] = exec_quantity
                    trade['option0_close_price']    = avg_fill_price
                elif executed_option_symbol == option1_symbol:
                    trade['option1_close_quantity'] = exec_quantity
                    trade['option1_close_price']    = avg_fill_price
        
                if executed_option_symbol == option0_symbol:
                    print('000000000000000000000000')
                    trade['option0_open_quantity'] = exec_quantity
                    trade['option0_open_price']    = avg_fill_price
                elif executed_option_symbol == option1_symbol:
                    print('111111111111111111111111')
                    trade['option1_open_quantity'] = exec_quantity
                    trade['option1_open_price']    = avg_fill_price
                redis_client1.set('live_trades', json.dumps(live_trades))
                return 1 # means success
                break
#-----------------------------------------------------------------------------------------------------
#-----------------------------------------------------------------------------------------------------
# remove entry from live trades list in redis db=1
#-----------------------------------------------------------------------------------------------------
def remove_order_from_live_trades_list(redis_client1,order_id):
    
    print('adding new trade to the live list\n')
    
    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

    rows_remove = 0

    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        print('live_trades=',type(live_trades),live_trades)

        if any(trade['open_order_id'] == order_id for trade in live_trades): # make sure this order exist before removing it
            before_num = len(live_trades)
            live_trades = [order for order in live_trades if order['open_order_id'] != order_id] # remove entry with 'order_id' == order_id
            after_num = len(live_trades)
            update_live_symbols(redis_client1,live_trades) # current symbols are published to be used by stream_quote in autotrade_async
            if before_num - after_num > 0:
                redis_client1.set('live_trades', json.dumps(live_trades))
            return before_num - after_num
        else: return -1 # shows why return was an error
    else: return -2

#------------------------------------------------------------------------------------------------------
# update current symbols from live_trades key in redis and publish for consumption by stream_quotes
#------------------------------------------------------------------------------------------------------
def update_live_symbols(redis_client1,redis_live_trades):

    symbols = []

    if redis_live_trades is not None:

        for t in redis_live_trades:
            if t['status'] == 'filled': # only filled status should be in live_symbols
                symbols.append(t['symbol'])
                symbols.append(t['option0_symbol'])
                symbols.append(t['option1_symbol'])

        symbols = list(set(symbols)) # get rid of duplicate symbols
        redis_client1.set('live_symbols',json.dumps(symbols))
        # also write the timestamp when the live_symbols changed - used to know when to update the symbols in autotrade_async
        redis_client1.set('live_symbols_timestamp',int(time.time()))

    return symbols
#---------------------------------------------------------------------------------------------------------
# checks to make sure all updates to live_trades have been made.  issues may occur if appserver_async.py  
# either wasn't running when event arrived from account_stream or just missed an event for any reason
# this function runs every 10 to 15 minutes and checks values that should be in live_trades for example
# if a trade was filled but it didn't register in live_trades - also if live_trades is deleted or a row is
# deleted for any reason, this routine recreates live_trades to continue autotrading operation seamlessly

# this function will run periodically in appserver_async
####################################################################
# userid saved in the data has to come from config_autotrade.userid
####################################################################
# userid when manual creditspread is placed in the UI comes from the UI
#---------------------------------------------------------------------------------------------------------
def reconcile_live_trades(redis_client1,redis_client2,account_id,userid):
    print('reconcile_live_trades')

    # get current live_trades data
    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

    # print(redis_live_trades)
    # orders = get_orders(account_id)

    # positions = get_positions(account_id)


    # for position in positions['position']:
    #     print(position)
    #     print('------')

    # for order in orders:
    #     if order['status'] == 'canceled' or order['status'] == 'expired': continue
    #     print(order)
    #     print('---')

    live_trades = [] # initializing live_trades
    updated_live_trades = []
    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        for trade in live_trades:
            print(trade)

            # check if live_trade entry is valid or need updates
            # 1- when order is first placed manually, the status in live_trades is a blank string.  check if order has been filled
            status = trade['status']
            # check if status is blank but order has been filled, then change status to 'filled'
            open_order_id  = trade['open_order_id']
            close_order_id = trade['close_order_id']
            dr_id          = trade['dr_id']
            open_order_status=get_order_status(account_id,userid,dr_id,open_order_id)


            # print('open_order_status=',open_order_status)


            # append to updated_live_trades and archive_live_trades based on the following conditions
            if open_order_status != '' and close_order_id == '': # this trade was filled but not closed - should be in live_trades

                # check if open_order_status is the same as the status in the live_trades - if it is, just leave it in live_trades as is
                # print('trade status =',trade['status'])

                if trade['status'] == open_order_status:
                    updated_live_trades.append(trade)
                else: # live_trade need to be updated
                    trade['status'] = open_order_status
                    trade['open_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
                    trade['security_price_open']
                    # trade['price_open'] # not sure what I was thinking 
 
                    updated_live_trades.append(trade)

            elif open_order_status == '' and close_order_id == '': # this trade order is placed but is not opened yet keep as is
                updated_live_trades.append(trade)
            elif open_order_id != '' and close_order_id != '': # this trade was filled and closed - archive and remove from live_trades
                # update fields for closing if not updated yet   

                # get current security price
                quote_dict = get_quotes(trade['symbol']) # security price at time option position was filled
                security_price = quote_dict['last'] 
                # assing fields that can be assinged before archiving the completed trade
                trade['close_order_id'] = close_order_id 
                trade['close_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
                trade['security_price_close'] = security_price
                # the following prices are not available unless they are captured on the with appserver_async in realtime so
                # these prices being captured is not guaranteed
                # trade['option0_close_price']
                # trade['option1_close_price']
                # trade['price_close']
                archive_trade(trade)

            print('------')
    # print(updated_live_trades)
#------------------------------------------------------------------------------------------------------
# check the status in the orders list
#------------------------------------------------------------------------------------------------------
def get_order_status(account_id,userid,dr_id,open_order_id):

    # get the list of reports from redis for this user first
    redis_key_user_reports  = f'user_reports_{userid}'
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    if redis_user_reports_list is not None:
        redis_user_reports_list = json.loads(redis_user_reports_list)
        # find index of dr_id
        idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id)]
        if len(idx) == 1:idx=idx[0]

        if 'orders' in redis_user_reports_list[idx]: 
            orders_str = redis_user_reports_list[idx]['orders']
            orders_lst = orders_str.split(',')
            for o in orders_lst:
                if int(o) == open_order_id:
                    # now get this order status from tradier get_one_order(account_id,order_id)
                    order_dict = get_one_order(account_id,o)
                    order_status = order_dict['status']
                    return order_status



    return 'not_found' # the open_order_id was not found in the list of current orders
#------------------------------------------------------------------------------------------------------
# check the status in the orders list
#------------------------------------------------------------------------------------------------------
def archive_trade(trade):
    print('archive trade')
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

    reconcile_live_trades(redis_client1,redis_client2,account_id,userid)