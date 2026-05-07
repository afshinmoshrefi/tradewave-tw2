
# this config file only has the settings for auto portfolio creation and auto trading 12/10/2023

#-------------------------------------------------
# description of the variables for scanning
#-------------------------------------------------
# 'min_sr': minimum sharpe ratio for the opportunity
# 'avg_ret':minimum avg return for the date range,
# 'min_mfe':minimum mfe in % but don't put % in - it is paireed with in_mfe_pct, 5 and 0.8 means to find opps that have reached 5% at least 80% of the years
# 'day_range':filter by days in the opportunity like 2-23 means only return opportunities that have # of days between 2 and 23
# 'min_mfe_pct': minimum percent that has reached min_mfe - 0.8 means 80% of the years have reached the % value in min_mfe so min_mfe=5 and min_mfe_pct=0.7 - 70% of years reached 5%
# 'initial_status': initial status flag - its the colored squed on the left of the opportuity in portfolio manager
# 'min_stock_price': minimum security price
# 'min_sr2'  : minimum value for sr2 - sr2 is calculated based on mfe so it is typically higher than sr but more relevant to credit spre3ad trades
# 'avg_ret2' : average returns based on mfe
# 'keep_highest_sr' : '0', when set to 1 it will remove the light blue opportunities that have better opportunity in future   
# 'days_look_forward_sr' : 20 this is to set how many days in the future to check for placing the blue square on the opportunity

# account_id             = '6YA44446' # actual account
account_id             = 'VA73842117'
portion_balance        = 0.5  # this is the portion of account dedicated to creditspread trading
# portion_risk_per_trade = 0.01 # 0.01 means 1% of the available_balance is dedicated to 1 trade  0 means - minimum # of options = 1 on every trade
portion_risk_per_trade = 0 # 0 means - minimum # of options = 1 on every trade
min_pct_credit         = 0.5  # 0.5 means at least 50% of the spread should be the price of the sold spread
max_pct_credit         = 0.8  # very high credit is suspicious, at least to me - set a maximum credit % limit
min_open_interest      = 10
min_days_to_expiration = 21   # that means options for creditspreads must have at least 20 days to expiration to be selected automatically.

# these settings are for scanning and creating a list of opportunities.  different settings will be used for each of the 12 markets.  
settings_us_stocks = { 'min_price':40,'min_sr':0, 'avg_ret':0, 'min_mfe':5, 'day_range':'2-51', 'min_mfe_pct':0.8, 'initial_status':'0', 'min_sr2'  : 1.5, 'avg_ret2' : 5,   'keep_highest_sr' : '0', 'days_look_forward_sr' : 5 }
settings_fc        = { 'min_price':0, 'min_sr':0, 'avg_ret':0, 'min_mfe':4, 'day_range':'2-51', 'min_mfe_pct':0.8, 'initial_status':'0', 'min_sr2'  : 1.5, 'avg_ret2' : 4,   'keep_highest_sr' : '0', 'days_look_forward_sr' : 5 }
settings_forex     = { 'min_price':0 ,'min_sr':0, 'avg_ret':0, 'min_mfe':0, 'day_range':'2-51', 'min_mfe_pct':0.8, 'initial_status':'0', 'min_sr2'  : 1.5, 'avg_ret2' : 0.5, 'keep_highest_sr' : '0', 'days_look_forward_sr' : 5 }

# list of the days to create portolios for
process_days = ['today','today+1','today+2','2023-12-20']

# markets can repeat with different parameters like 9/10 vs 10/10 years
# resourceID_list and years and pyears must have the same number of list entries - resourceID _list is looped to generate the portoflio
# the length of resourceID_list, years and pyears must be the same 
auto_portfolio_markets = {
    'date'           : 'today', # can also write a date in format of YYYY-MM-DD and can do "today"  or "today+2"  +2 will create 3 days of portfolios
    'resourceID_list': [9 ,9,3 ],  # 'resourceID_list': [0,1,2,3,4,7,9,11],
    'years'          : [10,10,10], # 'years'          : [10,10,10,10,10,10,10,10],
    'pyears'         : [8 ,9,9]    # 'pyears'         : [8,8,8,9,9,8,8,8]
}


# these are settings for which settings to use for each market
auto_portfolio_settings = {
    0:  settings_us_stocks,  # DOW 30 STOCKS,
    1:  settings_us_stocks,  # NASDAQ 100 STOCKS,
    2:  settings_us_stocks,  # S&P 500 STOCKS,
    3:  settings_us_stocks,  # RUSSELL 1000 STOCKS,
    4:  settings_us_stocks,  # WILSHIRE 5000,
    5:  settings_us_stocks,  # INDICES COMMON,
    6:  settings_us_stocks,  # INDICES ALL,
    7:  settings_fc       ,  # FUTURES & COMMODITIES,
    8:  settings_forex,      # FOREX ALL,
    9:  settings_forex,      # FOREX LIQUID,
    10: settings_fc,         # GOVERNMENT BONDS,
    11: settings_us_stocks,  # ETFs,
}



trade_tasks_list_name = 'trade_tasks_list' # this is in db=3

event_log_folder     = '/home/flask/appserver/appserver/logs/account-events/'
today_events_log_key = 'todays-events' # today events are saved in a dataframe in redis.  it is also periodically saved to disk

userid = ['16'] # used by async operations when userid is not known