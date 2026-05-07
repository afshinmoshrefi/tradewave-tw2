import numpy as np
from scipy.stats import norm
import pandas as pd

#     r # interest_rate
#     S # underlying price
#     K # strike price
#     T # 250 days to expiration
#     sigma # volitility 
def blackScholes(r, S, K, T, sigma, option_type="C"):


    if T == 0: # this is days to expiration - this is at expiration when T == 0
        strike=K
        stock_price=S

        if option_type == 'C':
            if stock_price <= strike:
                return 0
            elif stock_price >= strike:
                return stock_price - strike

        elif option_type == 'P':
            if stock_price <= strike:
                return strike - stock_price
            elif stock_price > strike:
                return 0
        else:
            return 'Only P or C are valid'

    if S == 0:   # np.log(0) throws divide by 0 error
        return 0

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)


    if option_type == "C" :
        option_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

    elif option_type == "P":
        option_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    else:
        raise ValueError("Invalid option type. Use 'C' for call or 'P' for put.")

    return option_price
#------------------------------------------------------------------------------------------------------------------------------
def calculate_option_risk_profile(int_rate,S, strike_price, time_to_expire, sigma, option_type):

    pct_below = 1 # 0.5 means range should start from 50% below stock price to 50% above
    pct_above = 0.5

    # stock_price_range = np.linspace(0.5 * S, 1.5 * S, 100)
    stock_price_range = list(range(int(S*(1-pct_below)),int(S*(1+pct_above))))





    option_values_current = []
    option_values_exp     = []

    for stock_price in stock_price_range:
        option_price = blackScholes(int_rate, stock_price, strike_price, time_to_expire, sigma, option_type)
        option_values_current.append(float(option_price))
        # now calculate option value at expiration
        
        option_price = blackScholes(int_rate, stock_price, strike_price, 0             , sigma, option_type)
        option_values_exp.append(float(option_price))



    # stock_price_range = stock_price_range.tolist()

    return stock_price_range, option_values_current,option_values_exp

#------------------------------------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------------------------------------
# get option prices for a group of options
#------------------------------------------------------------------------------------------------------------------------------
def get_option_prices_for_group_options(dict):



    # sending at least 1 option is a requirement
    stock_price_range, option_values0_current,option_values0_exp = calculate_option_risk_profile(dict['int_rate'],dict['current_stock_price'], dict['strike_price0'], dict['time_to_expire0'], dict['sigma0'], dict['type0'])
    stock_price_range, option_values1_current,option_values1_exp = calculate_option_risk_profile(dict['int_rate'],dict['current_stock_price'], dict['strike_price1'], dict['time_to_expire1'], dict['sigma1'], dict['type1'])
    

    return stock_price_range , option_values0_current , option_values0_exp , option_values1_current , option_values1_exp

   
#------------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":

    int_rate = 0.05 # interest_rate
    S = 80 # underlying price 
    strike_price = 100 # strike price
    time_to_expire = 200/365 # 250 days to expiration
    sigma = 0.30 # volitility 

    stock_price_range = list(range(0,S*2+1))

    dict = {
        'current_stock_price' : S,
        'int_rate'            : int_rate,

        'strike_price0'       : strike_price,
        'time_to_expire0'     : time_to_expire,
        'sigma0'              : sigma,
        'type0'               : 'C',
        'long_or_short0'      : 'long', 

        'strike_price1'     : 105,
        'time_to_expire1'   : time_to_expire,
        'sigma1'            : sigma,
        'type1'             : 'P',
        'long_or_short1'    : 'short'
    }


    stock_price_range , option_values0_current , option_values0_exp , option_values1_current , option_values1_exp = get_option_prices_for_group_options(dict)

    print(option_values0_current )
    print('')
    print(option_values0_exp)
   