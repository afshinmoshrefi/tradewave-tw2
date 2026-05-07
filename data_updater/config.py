
# when master_appserver is used, this appserver will fetch the data from the master_appserver
# if master_appserver is blank, this appserver fetches the data from local files
# initial attempt is for all functions that use historical data in the csv folder
# later update will add opportunity data also

master_appserver = 'https://app1kp.trxstat.com/' 
update_server    = 'http://104.238.214.253:7775/'

ddir = '/home/flask/data/'
wordpress_url = 'http://192.168.68.105/'
#logcollector_url = 'http://192.168.68.105:7676/' # when there is a value, every API activity will be logged in this server
logcollector_url = 'http://104.238.214.253:7774/' # this is prod log collector


# if set to False, all logged-in users see all content
useUMP = True

# allow for non logged-in users to see limited content:
noLoginContent = True

# keystore URL 
keystoreURL = 'http://localhost:7777' 

#############################################################################
# update available resources names and path when additional content is added
# update available_resources,available_resources_path,level_access_hierarchy
available_resources = {
    '1': 'Dow 30 Stocks',
    '2': 'S&P 500 Stocks',
    '3': 'Indicies USA',
    '4': 'Futures & Commodities',
    '5': 'FOREX All',
    '6': 'FOREX Liquid',
    '7': 'Government Bonds'
}

available_resources_path = {
    '1': '/home/flask/data/dj30_symbols.csv',
    '2': '/home/flask/data/sp500_symbols.csv',
    '3': '/home/flask/data/INDX_USA_symbols.csv',
    '4': '/home/flask/data/COMM_symbols.csv',
    '5': '/home/flask/data/FOREX_symbols.csv',
    '6': '/home/flask/data/FOREX_LQ_symbols.csv',
    '7': '/home/flask/data/GBOND_symbols.csv'
}

exchange_mapping={ # exchange mapping is used for EOD downloads - left is folder name, right is the exchange name for use with EOD download
    '1':'US',
    '2':'US',
    '3':'INDX',
    '4':'COMM',
    '5':'FOREX',
    '6':'FOREX',
    '7':'GBOND'
}

level_access_hierarchy = {
    '1': ['1'],
    '2': ['1'],
    '4': ['1'],
    '5': ['1','2','3','4','5','6','7'],
    '6': ['1','2','3','4','5','6','7']
}

#############################################################################
## rate-limit for each API 
rate_limit_login           = ['2/second','150/minute' ,'260/hour' ,'2000/day']
rate_limit_opp             = ['2/second','150/minute','1000/hour','2000/day']
rate_limit_chartData4      = ['2/second','150/minute','1000/hour','2000/day']
rate_limit_YearsMetaData   = ['2/second','150/minute','1000/hour','2000/day']
rate_limit_ChartHistorical = ['2/second','150/minute','1000/hour','2000/day']
#############################################################################
## redis expiration in seconds
opp_expire_time            = 1000000         # of seconds
chart_data_expire_time     = 1000000
years_metadata_expire_time = 1000000
history_expire_time        = 1000000
stock_metadata_expire_time = 1000000

max_opportunities_returned = 5000
max_opportunities_not_loggedin = 2000
