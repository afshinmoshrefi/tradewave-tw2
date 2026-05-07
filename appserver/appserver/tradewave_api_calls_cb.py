# these api calls are for openai chatbot 
# changed the parameters of 
# run_opp_blog_generation(opp_date):
# added parameter html_table_only boolean
# this is used to only create an html table for each opportunities list

import requests
import pandas as pd
import os
import socket
import time
import datetime
from datetime import timedelta
import jwt
import calendar
import base64
import sys
sys.path.insert(0, '/home/flask')
import config

# this uses a hack to get the token that changes. this hack is off on prod server. it only works on stage
def get_keyprovider_token():
    url = config.appserver_url+'/login/2/3/4/5/6'
    api_result = requests.get(url)
    result = api_result.json()
    t = result['message'].split(' ')
    return t[4]
#---------------------------------------------------------------------------------------------------------------

# after logging in, the returned token is used to make other calls to the appserver
def login_appserver(keyprovider_token):
    url = config.appserver_url+'/login/28/3/4/5/'+keyprovider_token
    api_result = requests.get(url)
    result = api_result.json()
    return result['token']
#---------------------------------------------------------------------------------------------------------------
# used to create an encoded url to open the wave viewer to the exact opportunity
def convert_param_base64(financial_group_id,symbol,date1,days_hold,history_years):

    pipe_str = f'{financial_group_id}|{symbol}|{date1}|{days_hold}|{history_years}'
    encoded_string = base64.b64encode(pipe_str.encode()).decode()

    return encoded_string
#---------------------------------------------------------------------------------------------------------------
# this function is used to create a link in the chatbot for the returned opportunities to open the wave viewer
def create_opportunity_url(financial_group_id,symbol,date1,days_hold,history_years):
    encoded_string = convert_param_base64(financial_group_id,symbol,date1,days_hold,history_years)
    # url is different between dev and stage/prod - check it by hostname
    hostname = socket.gethostname()
    if hostname != 'afshin-VirtualBox':
        url = f'{config.wordpress_url}wave-viewer?o={encoded_string}'
    else:
        url = f'{config.wordpress_url}seasonals?o={encoded_string}'
    return url
#---------------------------------------------------------------------------------------------------------------

# this one decodes the token and return the list of financial groups from trade seasonals
def get_financial_groups():
    
    groups = config.available_resources
    return groups

#---------------------------------------------------------------------------------------------------------------

# get opportunities list for the financial group
# def get_opp_list(group_id, month,day,years,pyears,appserver_token):
    
#     urlX = config.appserver_url+'/OppList4/'+str(group_id)+'/'+month+'/'+day+'/'+str(years)+'/'+str(pyears)+'/-/0/0?token='+appserver_token
#     api_result = requests.get(urlX)
#     result = api_result.json()
#     return result
def get_opp_list(group_id, month, day, years, pyears,day_range,appserver_token):
    urlX = config.appserver_url+'/OppList4/'+str(group_id)+'/'+month+'/'+day+'/'+str(years)+'/'+str(pyears)+'/'+day_range+'/0/0?token='+appserver_token
    api_result = requests.get(urlX)

    # Debugging: Log the raw response
    # print("URL:", urlX)
    # print("Response Code:", api_result.status_code)
    # print("Response Text:", api_result.text)

    if api_result.status_code != 200:
        raise ValueError(f"API returned non-200 status: {api_result.status_code}")
    
    try:
        result = api_result.json()
        return result
    except ValueError:
        raise ValueError(f"Invalid JSON response: {api_result.text}")

#---------------------------------------------------------------------------------------------------------------


def get_chart_data(id,opp_date,symbol,daysOut,years,appserver_token):
    urlY = config.appserver_url+'/ChartData4/'+str(id)+'/'+opp_date+'/'+symbol+'/'+daysOut+'/'+str(years)+'?token='+appserver_token
    result = requests.get(urlY)
    if result.status_code > 201 : print('get_chart_data returned',result.status_code,result.text,result.reason)
    api_result = result.json()
    return api_result

#---------------------------------------------------------------------------------------------------------------

def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')  
#---------------------------------------------------------------------------------------------------------------


def diff_between_dates(date2,date1):

    d1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(date2, "%Y-%m-%d")

    difference = d2 - d1
    days = difference.days
    return int(days)

#---------------------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------
#  return years and pyears based on which resource group from 0 or 11 is selected
#------------------------------------------------------------------------------------------------
def get_years_pyears_from_resource_id(id):
    years    = 10  
    pyears   = 10
    if id == 0 or id == 5 or id == 11  or id==7 : 
        pyears = 9 # not enough results when returning 
    if id == 9: 
        pyears = 8 # forex liquid
    if id == 10  :  # this is bonds 
        years = 8
        pyears = 8
    return years,pyears




#####################################################################################################################
################################################   Main Program  ####################################################
#####################################################################################################################

if __name__ == '__main__':


    url=create_opportunity_url(0,'AAPL', '2024-12-21', 10, 10)
    print(url)
    exit()


    today_date = datetime.datetime.now().strftime("%Y-%m-%d")

    opp_date = today_date

    # num_opps  = config.num_opps_per_fi # this is the number of opportunities to return - 
    num_opps = 10
    month     = calendar.month_name[int(opp_date[5:7])]
    day       = str(int(opp_date[8:]))


    id       = 1
    years,pyears = get_years_pyears_from_resource_id(id)

    keyprovider_token=get_keyprovider_token()
    appserver_token=login_appserver(keyprovider_token)
    

    
    fgs=get_financial_groups()
    print(fgs)

    result = get_opp_list(id,month,day,years,pyears,appserver_token)
    print(result['OppList'])