import config_tradier
from pooled_http import http as requests
import datetime
from datetime import timedelta
import sys
sys.path.insert(0, '/home/flask')
import config_autotrade
from pprint import pprint
from requests.exceptions import RequestException

headers = {
    'Authorization': f'Bearer {config_tradier.ACCESS_TOKEN}',
    'Accept': 'application/json'
}

#------------------------------------------------------------------------------------------------
def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
#------------------------------------------------------------------------------------------------
def diff_2_dates(date1,date0):
    d0 = datetime.datetime.strptime(date0, "%Y-%m-%d")
    d1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
    days_diff = (d1-d0).days

    return days_diff
#------------------------------------------------------------------------------------------------
# gets stock and option quote - comma delimited list of symbols, no spaces 
#------------------------------------------------------------------------------------------------
def get_quotes(symbols): # gets stock quote - 

    url = f'{config_tradier.API_BASE_URL}/v1/markets/quotes'
    response = requests.get(url,params={'symbols': symbols},headers=headers, timeout=15)
    
    # print(f'get_quote {symbols} returned response=',response.text)
    json_response = response.json()

    # print('from tradier_api.py get_quotes json_response= ',json_response)
    # print(json_response['quotes']['quote'])
    ret=  json_response['quotes']['quote']

    # price = dict['last']
    # if 1 symbol, ret is a dictionary
    # if more than 1 symbol its a list of dictionaries.

    return ret
#------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------
def get_option_strikes(symbol,expiration): # gets all the option strikes for the expiration date
    url = f'{config_tradier.API_BASE_URL}/v1/markets/options/strikes'
    response = requests.get(url, params={'symbol': symbol, 'expiration': expiration, 'greeks': 'false'}, headers=headers, timeout=15)

    json_response = response.json()

    return json_response,response.status_code
#--------------------------------------------------------------------------------------------------
# expiration_type is either weeklys or standard expiration
def get_option_expirations(symbol,expiration_type,wave_end_date):
    url = f'{config_tradier.API_BASE_URL}/v1/markets/options/expirations'
    response = requests.get(url, params={'symbol': symbol, 'includeAllRoots': 'true', 'strikes': 'true', 'contractSize': 'true', 'expirationType': 'true'}, headers=headers, timeout=15)

    json_response = response.json()

    ex_list = json_response['expirations']['expiration']


    filtered_expiration_list = []
    for g in ex_list:
        ex_date = g['date']

        
        diff = diff_2_dates(ex_date,wave_end_date)
        # print('ex_date=',ex_date,wave_end_date,diff)
        # print(ex_date,abs(diff),g['expiration_type'])
        # only return expirations that are 20 days or less from wave_end_date 
        if diff > -10  and g['expiration_type'] == expiration_type: # returned expiration has to started with at least 10 days before wave end
            g['diff'] = diff # add diff to the dictionary 
            filtered_expiration_list.append(g)

    return filtered_expiration_list
#------------------------------------------------------------------------------------------------
def get_options_chain(symbol,expiration_date):
    url = f'{config_tradier.API_BASE_URL}/v1/markets/options/chains'
    response = requests.get(url, params={'symbol': symbol, 'expiration': expiration_date, 'greeks':'true'}, headers=headers, timeout=15)

    json_response = response.json()
    options_list  = json_response['options']['option']


    return options_list
#------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------
def get_accounting_info(account_id): # returns available balance for trading and position size

    url = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/balances'
    response = requests.get(url, params={}, headers=headers, timeout=15)
    # if response.status_code == '401':
    #     print('401 - unauthorized')
    #     return 0
    balances_dict = response.json()
    balances_dict = balances_dict['balances']

    # keys in the dictionary are:
    # ['option_short_value', 'total_equity', 'account_number', 'account_type', 'close_pl', 'current_requirement', 'equity', 'long_market_value', 'market_value', 'open_pl', 'option_long_value', 'option_requirement', 'pending_orders_count', 'short_market_value', 'stock_long_value', 'total_cash', 'uncleared_funds', 'pending_cash', 'margin']
    
    # print('balances_dict=',balances_dict.keys())
    ##################################################################################
    # if per_trade_capital == 0 means trade the minimum - typically 1 option contract
    ##################################################################################
    return balances_dict['total_equity'],balances_dict
#---------------------------------------------------------------------------------------------------
# this is to place a multi leg options trade
# symbol:the stock symbol
# type  : market, debit, credit, even
# price : limit price for debit and credit orders
# option_symbol_0 : option symbol
# side_0 : buy_to_open, buy_to_close, sell_to_open, sell_to_close
# quantity_0 : num contracts
# option_symbol_1,side_1,quantity_1 : same as 0

    # data={
    #     'class': 'multileg', 
    #     'symbol': symbol, 
    #     'type': 'credit', 
    #     'duration': 'day', 
    #     'price': '1.0', 
    #     'option_symbol[0]': 'SPY190605C00282000', 
    #     'side[0]': 'buy_to_open', 
    #     'quantity[0]': '10', 
    #     'option_symbol[1]': 'SPY190605C00286000', 
    #     'side[1]': 'buy_to_close', 
    #     'quantity[1]': '10'
    # }

def place_multileg_option_trade(data,account_id):
    url  = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/orders'

    response = requests.post(url, data=data, headers=headers, timeout=30)
    if response.status_code != 200 :
        print(f'multileg_option_trade in tradier returned {response.status_code} - bad request')
        print('data for the post request =',data)
        json_response = {'error':'Bad Request'}
    else:
        json_response = response.json()
        # print(response.status_code)
        # print(json_response)

    return response.status_code,json_response
#------------------------------------------------------------------------------------------------
# only modifying price for testing - otherwise everything can be modified with tradier api
#------------------------------------------------------------------------------------------------
def update_multileg_option_order(order_id,account_id,price):

    url  = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/orders/{order_id}'

    data = {'updating existing order with new price':price}
    response = requests.put(url, data=data, headers=headers, timeout=30)
    print('update_multileg_option_order json response=',response.text)
    json_response = response.json()

    return json_response


#------------------------------------------------------------------------------------------------
def cancel_order(order_id,account_id):

    print('cancel_order order_id=',order_id)

    url  = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/orders/{order_id}'

    response = requests.delete(url, data={}, headers=headers, timeout=30)

    print('cancel_order response',response.text)
    
    json_response = response.json()

    print('cancel json_response ',json_response)

    return json_response


#------------------------------------------------------------------------------------------------
# get all the current positions in the tradier account
#------------------------------------------------------------------------------------------------
# def get_positions(account_id):
#     url = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/positions'

#     response = requests.get(url, params={}, headers=headers, timeout=15)
#     positions_dict = response.json()
#     if positions_dict['positions'] == 'null':
#         return []

#     return positions_dict['positions']

#------------------------------------------------------------------------------------------------
# rewritten by claude with error management
#------------------------------------------------------------------------------------------------
def get_positions(account_id):
    url = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/positions'

    # print('url in get_positions in tradier_api =', url)

    try:
        response = requests.get(url, params={}, headers=headers, timeout=10)
        response.raise_for_status()  # Raises an HTTPError for bad responses

        positions_dict = response.json()

        if not positions_dict or positions_dict.get('positions') == 'null':
            return []

        return positions_dict.get('positions', [])

    except requests.exceptions.JSONDecodeError:
        print("Error decoding JSON response")
        return []
    except RequestException as e:
        print(f"Error fetching positions: {e}")
        return []
    except KeyError:
        print("Unexpected response format")
        return []
#------------------------------------------------------------------------------------------------
# get all the open orders in the tradier account
#------------------------------------------------------------------------------------------------
def get_orders(account_id):

    page_num = 1

    url = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/orders'
    response = requests.get(url, params={'page': page_num, 'includeTags': 'true'}, headers=headers, timeout=15)


    # print('\n\n orders_dict in get_orders',response,'\n\n')

    ret = response.json()

    # print('orders_dict in get_orders',ret)


    if ret['orders'] == 'null':
            ret = []
    else:
        ret = ret['orders']['order']

    # print('type of ret from get_orders in tradier_api',type(ret))
    # print('ret from get_orders in tradier_api',type(ret),ret)
    
    

    return ret
#------------------------------------------------------------------------------------------------
# get details of an order from tradier
# when getting all orders with get_orders(account_id) tradier only returns the current live orders
# however when getting details of 1 order with get_one_order, it will return details of the order
# even if the order is not live anymore - because of this details can be obtained by getting the
# orders list from reports_detail by dr_id then use get_one_order to get the detail of the order
# 
#------------------------------------------------------------------------------------------------
def get_one_order(account_id,order_id):

    url = f'{config_tradier.API_BASE_URL}/v1/accounts/{account_id}/orders/{order_id}'
    # print('url from get_one_order returned',url)

    response = requests.get(url, params={'includeTags': 'true'}, headers=headers, timeout=15)
    # print('response from get_one_order returned',response)
    ret = response.json()

    # print('\n\n order_id=',order_id)
    # print('ret from get_one_order returned',ret)

    return ret
#------------------------------------------------------------------------------------------------
def get_bullish_bearish_creditspreads(symbol,price,num_strikes,option_expiration_dict):

    ex_date         = option_expiration_dict['date']
    ex_strikes_list = option_expiration_dict['strikes']['strike']
    # diff            = option_expiration_dict['diff'] # difference of expiration and wave_end_date - negative means expiration is before wave_end_date 

    # find 3 strikes lower than the stock price and 3 strikes equal and higher than the stock price
    less_strikes = [s for s in ex_strikes_list if s < price ][::-1] # list reversed
    if len(less_strikes) > num_strikes: 
        less_strikes = less_strikes[:num_strikes]
    # find 3 strikes higher than the stock price number 3 was changed to variable num_strikes
    more_strikes = [s for s in ex_strikes_list if s >= price ]
    if len(more_strikes) > num_strikes: more_strikes = more_strikes[:num_strikes]

    # The spread catalogs below index up to [3] on both sides - a sparse chain
    # used to IndexError and 500 the route; raise a clean error instead so the
    # endpoint can return its graceful empty shape.
    if len(less_strikes) < 4 or len(more_strikes) < 4:
        raise ValueError(f'sparse option chain for {symbol} {ex_date}: '
                         f'{len(less_strikes)} lower / {len(more_strikes)} upper strikes (need 4 each)')

    # print('less_strikes=',less_strikes)
    # print('more_strikes=',more_strikes)

    # now I have 3 strikes above and 3 strikes below the current security price
    # find options for each of the strike prices - 
    # get both call and puts for bullish and bearish credit spread
    # get volume and open interest and greeks - need to plot risk profile

    options_list=get_options_chain(symbol,ex_date) # details of availabel options for the symbol for expiration date ex_date
    
    # create a filtered list that includes only strike prices in less_strikes and more_strikes - making the list smaller for ease of process
    options_list_f = [o for o in options_list if o['strike'] in less_strikes or o['strike'] in more_strikes]

    # now setup possible credit spreads both bullish and bearish
    # credit spreads to create:
    # bullish credit spreads buy put lower_price - sell put higher_price
    # bearish credit spreads buy call higher_price -sell call lower_price
    # 1) at the money bullish      : buy put  strike=less_strikes[0] | sell put  strike=more_strikes[0]
    # 2) at the money bullish wide : buy put  strike=less_strikes[0] | sell put  strike=more_strikes[1]
    
    # 3) at the money bearish      : buy call strike=more_strikes[0] ! sell call strike=less_strikes[0]
    # 4) at the money bearish wide : buy call strike=more_strikes[1] ! sell call strike=less_strikes[0]
    
    # * out of the money bullish is 1 strike out of the money while 2 is 2 strikes out of the money
    # 5) out of the money bullish  : buy put  strike=more_strikes[1] | sell put  strike=more_strikes[2]
    # 6) out of the money bullish2 : buy put  strike=more_strikes[2] | sell put  strike=more_strikes[3]

    # 7) out of the money bearish  : buy call strike=less_strikes[1] ! sell call strike=less_strikes[0]
    # 8) out of the money bearish2 : buy call strike=less_strikes[2] ! sell call strike=less_strikes[1]

    # 9) forgot about this one 1,1 - if first one is 0,0 then this is 1 strike above for buy and sell  
    # 10)  forgot about this one 1,1 - if first one is 0,0 then this is 1 strike above for buy and sell  

    # create 4 bullish credit spread strikes for buy options and sell option
    bullish_credit_spread_strikes = [
        {'sell':more_strikes[0],'buy':less_strikes[0]}, #1
        {'sell':more_strikes[1],'buy':less_strikes[0]}, #2
        {'sell':more_strikes[1],'buy':more_strikes[0]}, #9
        {'sell':more_strikes[2],'buy':more_strikes[1]}, #5
        {'sell':more_strikes[3],'buy':more_strikes[2]}  #6
    ]

    # create 4 bearsih creditspreads strikes for buy option and sell option
    bearish_credit_spread_strikes = [
        {'sell':less_strikes[0],'buy':more_strikes[0]}, #3
        {'sell':less_strikes[1],'buy':more_strikes[0]}, #4
        {'sell':less_strikes[1],'buy':less_strikes[0]}, #10
        {'sell':less_strikes[2],'buy':less_strikes[1]}, #7
        {'sell':less_strikes[3],'buy':less_strikes[2]}, #8
    ]
    # now we have the bull bear dicionaries that have a list of dictionaries that define strike prices for credit spreads
    # use the dictionary strike prices to create another dictionary that finds and stores the corresponding option dictionary
    # for each of the credit spreds from the options chain options_list_f

    bullish_creditspreads=[]
    for cs in bullish_credit_spread_strikes:
        buy_options  = [d for d in options_list_f if d['option_type'] == 'put' and d['strike'] == cs['buy']]
        sell_options = [d for d in options_list_f if d['option_type'] == 'put' and d['strike'] == cs['sell']]
        if not buy_options or not sell_options:
            continue  # sparse chain: this strike pair isn't listed - skip instead of IndexError
        bullish_creditspreads.append({'buy':buy_options[0],'sell':sell_options[0]})

    bearish_creditspreads=[]
    for cs in bearish_credit_spread_strikes:
        buy_options  = [d for d in options_list_f if d['option_type'] == 'call' and d['strike'] == cs['buy']]
        sell_options = [d for d in options_list_f if d['option_type'] == 'call' and d['strike'] == cs['sell']]
        if not buy_options or not sell_options:
            continue  # sparse chain: this strike pair isn't listed - skip instead of IndexError
        bearish_creditspreads.append({'buy':buy_options[0],'sell':sell_options[0]})

    return bullish_creditspreads, bearish_creditspreads , ex_date
#------------------------------------------------------------------------------------------------
def get_creditspreads_for_opportunity(symbol_quote_dict,opp_date0,opp_days,num_strikes):
    # print(symbol_quote_dict)
    symbol    = symbol_quote_dict['symbol']
    price     = symbol_quote_dict['last']
    opp_date1 = inc_date_day(opp_date0,opp_days) # end date of the opportunity
    # print('wave end date = ',opp_date1)
    
    # we want to find the options expiration dates that are after opp_date1
    ex = get_option_expirations(symbol,'standard',opp_date1)
    if len(ex) < 2:  # thinly-listed underlying - was an IndexError/500 below
        raise ValueError(f'not enough option expirations for {symbol} after {opp_date1} (got {len(ex)})')

    # decide if to take the first expiration or second 0 or 1
    ex_date0 = ex[0]['date']
    diff0    = diff_2_dates(ex_date0,opp_date1)
    ex_date1 = ex[1]['date']
    diff1    = diff_2_dates(ex_date1,opp_date1)

    if diff0 > -3: 
        option_expiration_dict      = ex[0] # if expiration is less than 3 days before wave end use it - otherwise go to next expiration
        option_expiration_dict_next = ex[1] 
    else         :
        option_expiration_dict      = ex[1]
        option_expiration_dict_next = ex[2] if len(ex) > 2 else ex[1]

    bullish_creditspreads, bearish_creditspreads , ex_date = get_bullish_bearish_creditspreads(symbol,price,num_strikes,option_expiration_dict)
    bullish_creditspreads1, bearish_creditspreads1 , ex_date1 = get_bullish_bearish_creditspreads(symbol,price,num_strikes,option_expiration_dict_next)
    

    return {ex_date:{'bullish_creditspreads':bullish_creditspreads,'bearish_creditspreads': bearish_creditspreads },ex_date1:{'bullish_creditspreads':bullish_creditspreads1,'bearish_creditspreads':bearish_creditspreads1 }}
#---------------------------------------------------------------------------------------------------
# checks if credit spread passes the filtering tests - returns False if fails
#---------------------------------------------------------------------------------------------------
def select_creditspread_based_on_filters(cs,per_trade_capital): 

    # pprint(cs)

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    expiration     = cs['buy']['expiration_date']

    buy_strike     = cs['buy']['strike']
    buy_OI         = cs['buy']['open_interest']
    buy_bid        = cs['buy']['bid']
    buy_ask        = cs['buy']['ask']
    if buy_bid == None or buy_ask == None: # if there is no bid or ask its set to None
        buy_bid = 0
        buy_ask = 0

    sell_strike    = cs['sell']['strike']
    sell_OI        = cs['sell']['open_interest']
    sell_bid       = cs['sell']['bid']
    sell_ask       = cs['sell']['ask']
    if sell_bid == None or sell_ask == None: # if there is no bid or ask its set to None
        sell_bid = 0
        sell_ask = 0

    spread         = abs(sell_strike - buy_strike) # abs is used to take care of bullish and bearish
    buy_mark       = (buy_bid + buy_ask) / 2
    sell_mark      = (sell_bid + sell_ask) / 2
    credit         = round(abs(sell_mark - buy_mark),2) # abs is used to take care of bullish and bearish
    pct_credit     = credit / spread
    days_to_expire = diff_2_dates(expiration,today_date)

    if cs['sell']['greeks'] != None and cs['buy']['greeks'] != None:
        spread_delta   = round(cs['sell']['greeks']['delta'] - cs['buy']['greeks']['delta'],4)
    else:
        spread_delta = 0

    risk_per_cont  = (spread - credit) * 100; # 100 shares per contract
    if risk_per_cont > 0:
        numContracts = int(per_trade_capital / risk_per_cont)
    else:
        numContracts = 0 # technically risk_per_cont should never be 0 so if it is, set contract to 0 also

    # print(bb,s,numContracts)
    #-----------------------------------------------------------------------------------------
    # test if this selection can be used otherwise continue to the next cs for examination
    #-----------------------------------------------------------------------------------------

    # check if credit is higher than the spread.  these are bad quotes and need to be disqualified, until another quote is fetched
    if credit > spread: 
        return False # this cannot happend - bad quote

    # check open_interest buy_OI and sell_OI has to be larger than config_autotrade.min_open_interest + it has to be more than # contracts
    if buy_OI < numContracts or buy_OI < config_autotrade.min_open_interest or sell_OI < config_autotrade.min_open_interest or sell_OI < numContracts: 
        return False

    # pct_credit has to be larger than config_autotrade.min_pct_credit
    if credit / spread < config_autotrade.min_pct_credit:
        return False

    # pct_credit has to be smaller than config_autotrade.max_pct_credit - trying to filter out too high of credit because ...
    if credit / spread > config_autotrade.max_pct_credit:
        return False

    # days to expiration has to be larger than config_autotrade.min_days_to_expiration     
    if days_to_expire < config_autotrade.min_days_to_expiration:
        return False

    return True

#---------------------------------------------------------------------------------------------------
# this routine input is a dict which is output of get_creditspreads_for_opportunity
# it then uses a list of desired creditspreads in order [[0,3],[0,2],[0,0],[0,1],[1,3],[1,2],[1,0],[1,1]]
# it tests the first if it fails in tests the second until it finds one selection to return as 
# automated selected creditspread - this creditspread can be changed with UI or automated selection below
#---------------------------------------------------------------------------------------------------
def desired_selections_bullish_bearish(dict):

    #  return {ex_date:{'bullish_creditspreads':bullish_creditspreads,'bearish_creditspreads': bearish_creditspreads },ex_date1:{'bullish_creditspreads':bullish_creditspreads1,'bearish_creditspreads':bearish_creditspreads1 }}
    ex_dates=list(dict.keys())

    # also get account info for per trade risk capital for credit spreads
    total_equity,balances_dict = get_accounting_info(config_autotrade.account_id) 
    capital_available = total_equity * config_autotrade.portion_balance # this is a fraction like 0.5 means only trade half of the account
    per_trade_capital = capital_available * config_autotrade.portion_risk_per_trade

    # desired selection in the following order [expiration_date_index,creditspread_list_index]
    selection_order = [[0,3],[0,2],[0,0],[0,1],[1,3],[1,2],[1,0],[1,1]]
    selected_bullish = [-1,-1] # hold selected cs to be sent to UI
    selected_bearish = [-1,-1] # hold selected cs to be sent to UI

    # select which  bullish credit spread is set for auto selection one for each expiration date
    for s in selection_order:
        expiration_index   = s[0]
        creditspread_index = s[1]
        # for bullish credit spreads
        cs = dict[ex_dates[expiration_index]]['bullish_creditspreads'][creditspread_index]
        passed = select_creditspread_based_on_filters(cs,per_trade_capital)
        
        # print('ppppppppppppppppassed=',passed)


        if passed == True:
            selected_bullish = s
            break

    # select which bearish credit spread
    for s in selection_order:
        expiration_index   = s[0]
        creditspread_index = s[1]
        # for bearish credit spreads
        cs = dict[ex_dates[expiration_index]]['bearish_creditspreads'][creditspread_index]
        passed = select_creditspread_based_on_filters(cs,per_trade_capital)
        if passed == True:
            selected_bearish = s
            break


            
    # print ('bullish=',selected_bullish)
    # print ('bearish=',selected_bearish)    
        
    return selected_bullish,selected_bearish

#---------------------------------------------------------------------------------------------------
# get trading calendar days and times from brokerage
#---------------------------------------------------------------------------------------------------
def get_brokerage_calendar():

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    month = today_date[5:7]
    year  = today_date[:4]
    day   = today_date[8:]

    url  = f'{config_tradier.API_BASE_URL}/v1/markets/calendar'

    response = requests.get(url,params={'month': month, 'year': year},headers=headers, timeout=15)
    json_response = response.json()

    # print(json_response['calendar']['days']['day'])

    current_day = [d for d in json_response['calendar']['days']['day'] if d['date']==today_date]

    return current_day[0]
#---------------------------------------------------------------------------------------------------
# get trading calendar days and times from brokerage
#---------------------------------------------------------------------------------------------------
def get_brokerage_clock():

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    url  = f'{config_tradier.API_BASE_URL}/v1/markets/clock'

    response = requests.get(url,params={'delayed':'true'},headers=headers, timeout=15)
    json_response = response.json()

    return json_response['clock']
#---------------------------------------------------------------------------------------------------
# this function takes the filled orders and their quantity from order dictionary and
# cross references with positions list of dictionaries - if it finds the position that
# matches the order including quantity then it returns the position
# input is the order dictionary and positions dictionary 
#---------------------------------------------------------------------------------------------------
def get_position_from_filled_order(order,positions):

    # print('\n\norder=',order)

    if len(positions) == 0:
        return {}
    
    # check if order was filled 
    status = order['order']['status']
    if status != 'filled':
        return {}


    # get option symbols and quantity
    symbol0    = order['order']['leg'][0]['option_symbol']
    order_qty0 = order['order']['leg'][0]['quantity']
    side0      = order['order']['leg'][0]['side']
    ls0        = 'long' if  'buy' in side0 else 'short'

    symbol1    = order['order']['leg'][1]['option_symbol']
    order_qty1 = order['order']['leg'][1]['quantity']
    side1      = order['order']['leg'][1]['side']
    ls1        = 'long' if  'buy' in side1 else 'short'

    leg0={}
    leg1={}

    for p in positions['position']:

        if p['symbol'] == symbol0:
            leg0 = p
        elif p['symbol'] == symbol1:
            leg1 = p


    postion_dict = {}
    if leg0 and leg1:
        position_dict = {'order_id':order['order']['id'],'leg0':leg0,'leg1':leg1}
    else: # if one of the legs is not found then return empty dictionary 2/27/2024
        position_dict = {}

    return position_dict

#---------------------------------------------------------------------------------------------------
###########################################################################################################
if __name__ == '__main__':


    # orders = get_orders(config_autotrade.account_id)
    # print(orders)

    # exit()

    # 13903626,13903663
    order_id = 13903663 

    order     = get_one_order(config_autotrade.account_id,order_id)

    print(order)
    exit()

    # positions = get_positions(config_autotrade.account_id)
    # print(positions)
    # exit()

    
    # position_dict=get_position_from_filled_order(order,positions)
    # print(position_dict)
    # exit()
    

    # json_response = get_trading_clock()
    # print(json_response)
    # exit()

    # json_response = get_trading_calendar()
    # exit()

    # json_response=cancel_order('9740775',config_autotrade.account_id)
    # print(json_response)
    # exit()


    # positions_dict=get_positions(config_autotrade.account_id)

    # for p in positions_dict['position']:
    #     print(p)
    #     print('')

    # exit()

    # for p in positions_dict['position']:
    #     # print(p)
    #     print('')


    # exit()
    # order_id = 9782866 # apple order
    # price = '3.50'
    # json_response = update_multileg_option_order(order_id,config_autotrade.account_id,price)

    # print(json_response)

    # exit()


    # order_id=9743731 
    # order_id=9740790 
    # order_id=9743789 
    # order_id=9743971 
    # order_id=9754585
    # order_id=735601
    # order_id=9754581
    # order_id=9769338
    # order_id = 9782866 # apple order

    order_id = 13045873
    order_id = 12929573



    one_order = get_one_order(config_autotrade.account_id,order_id)
    pprint(one_order['order'])
    exit()


    # symbols= 'NVDA240216P00555000,NVDA240216P00560000'
    # symbols= 'NVDA240216P00555000'
    # symbols= 'AMZN'
    # ret  = get_quotes(symbols)

    # print('')
    # pprint(ret)
    # exit()

    orders_list = get_orders(config_autotrade.account_id)
    # pprint(orders_list)


    for o in orders_list:
        print(o)
        # print(o['symbol'],'=',o['id'],'status=',o['status'])
        print('')

    # exit()

   

    total_equity,balances_dict=get_accounting_info(config_autotrade.account_id) 
    pprint('balances_dict=',balances_dict)
    # exit()

    data={
        'class': 'multileg', 
        'symbol': 'MSFT', 
        'type': 'credit', 
        'duration': 'day', 
        'price': '2.6', 
        'option_symbol[0]': 'MSFT240216P00395000', 
        'side[0]': 'buy_to_open', 
        'quantity[0]': '10', 
        'option_symbol[1]': 'MSFT240216P00400000', 
        'side[1]': 'sell_to_open', 
        'quantity[1]': '10'
    }

    place_multileg_option_trade(data,'VA73842117')


    # exit()
    
    # account = config_autotrade.account_id
    # total_equity,balances_dict = get_accounting_info ('VA73842117')
    # print('total_equity=',total_equity)
    # exit()

    num_strikes = 5
    symbol      = 'GS'
    opp_date0   = '2024-01-03' 
    opp_days    = 8

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    dict  = get_quotes(symbol) # get the stock price for AAPL for right now

    # print(f'{symbol} price is:{dict["last"]}')



    dict = get_creditspreads_for_opportunity(dict,opp_date0,opp_days,num_strikes)



    # auto select which credit spread for bullish and which for bearish
    selected_bullish,selected_bearish = desired_selections_bullish_bearish (dict)

    print(selected_bullish)
    print(selected_bearish)



