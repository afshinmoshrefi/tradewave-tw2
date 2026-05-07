# 5/5/2024 - this program generates active opportunities list for today + days_before + days_after dates

import pandas as pd
import datetime
import calendar
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import os

import sys
sys.path.insert(0, '/home/flask')
import config


def normalize_opp_mode(opp_mode):
    """
    opp_mode:
      - None or "" => "consecutive"
      - "consecutive" => "consecutive"
      - "PE0"/"PE1"/"PE2"/"PE3" => same
      - "pe1" => "PE1"
    """
    if opp_mode is None:
        return "consecutive"
    s = str(opp_mode).strip()
    if s == "":
        return "consecutive"

    s_up = s.upper()
    if s_up == "CONSECUTIVE":
        return "consecutive"

    # Allow "PE1" or "pe1"
    if s_up in ("PE0", "PE1", "PE2", "PE3"):
        return s_up

    # Any unknown value, treat as consecutive (or raise if you prefer hard-fail)
    return "consecutive"
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def inc_date_year(d, i):
    return ((datetime.datetime.strptime(d, '%Y-%m-%d') + relativedelta(years=i)).strftime('%Y-%m-%d'))
#------------------------------------------------------------------------------------------------------
# generate a list of all the dates for the current year
# only need this function if generating active opportunities for every date in the current year
#------------------------------------------------------------------------------------------------------
# def generate_dates_list():

#     today_date   = datetime.datetime.now().strftime("%Y-%m-%d")
#     current_year = int(today_date[:4])
#     dates_list   = [f'{current_year}-01-01'] # start date

#     seasonal_years        = 10
#     seasonal_years_return = 10

#     # create a list of 365 dates for this year in format of YYYY-MM-DD | I don't want leap day in the list

#     for i in range(365):
#         # date = inc_date_day(start_date,i)
#         dates_list.append( inc_date_day(dates_list[i],1) )

#     return dates_list
#------------------------------------------------------------------------------------------------------
# generate a list of dates for today + days_before + days_after dates - these are the dates we'll process
# active opportunites for 
#------------------------------------------------------------------------------------------------------
def generate_dates_list(days_before,days_after):

    today_date   = datetime.datetime.now().strftime("%Y-%m-%d")
    dates_list   = [today_date] # start date


    # create a list of 365 dates for this year in format of YYYY-MM-DD | I don't want leap day in the list

    for i in range(0,days_before):
        # date = inc_date_day(start_date,i)
        print(i)
        dates_list.append(inc_date_day(today_date,-i-1) )
    for i in range(0,days_after):
        # date = inc_date_day(start_date,i)
        dates_list.append( inc_date_day(today_date,i+1) )

    dates_list.sort()

    return dates_list
#------------------------------------------------------------------------------------------------------
# get all the folders for seasonal_years and resourceID
#------------------------------------------------------------------------------------------------------
def get_folder_for_date_seasonal_years(resourceID, seasonal_years, seasonal_years_return, date, opp_mode=None, resourceFolder=None):

    opp_mode = normalize_opp_mode(opp_mode)

    # If OppList4 passes resourceFolder, use it. This is the correct base.
    if resourceFolder is not None and str(resourceFolder).strip() != "":
        available_resources_folder = resourceFolder.rstrip("/") + "/opportunities/"
    else:
        available_resources_folder = (
            config.available_resources_path[resourceID].replace('_symbols.csv','') + '/opportunities/'
        )

    opp_mode = normalize_opp_mode(opp_mode)

    available_resources_folder = (
        config.available_resources_path[resourceID]
        .replace('_symbols.csv','')
        + '/opportunities/'
    )

    m = int(date[5:7])
    month_name = calendar.month_name[m]

    suffix = ""
    if opp_mode != "consecutive":
        # opp_mode is "PE0".."PE3"
        suffix = f"_{opp_mode}"

    folder_path = f"{available_resources_folder}Monthly_Opp_{month_name}_{seasonal_years}_{seasonal_years_return}{suffix}/"
    file_path   = f"{folder_path}{date}.csv.gz"

    return folder_path, file_path
#------------------------------------------------------------------------------------------------------
# creates active list for resourceID,date,seasonal_years,seasonal_years_return,active_days
# active_days is the number of days we'll look back to find active opportunities
#------------------------------------------------------------------------------------------------------
def create_active_list(resourceID, date, seasonal_years, seasonal_years_return, active_days, opp_mode=None, resourceFolder=None):

    opp_mode = normalize_opp_mode(opp_mode)

    # OFF switch
    if int(active_days) <= 0:
        return pd.DataFrame()

    folder_path, file_path = get_folder_for_date_seasonal_years(
        resourceID, seasonal_years, seasonal_years_return, date, opp_mode=opp_mode, resourceFolder=resourceFolder
    )

    dfa = pd.DataFrame()

    for i in range(1, active_days):
        prev_date = inc_date_day(date, -i)
        if prev_date[5:] == '02-29':
            continue
        if prev_date[:5] != date[:5]:
            continue

        prev_folder_path, prev_file_path = get_folder_for_date_seasonal_years(
            resourceID, seasonal_years, seasonal_years_return, prev_date, opp_mode=opp_mode, resourceFolder=resourceFolder
        )

        if os.path.isfile(prev_file_path):
            df = pd.read_csv(prev_file_path, compression='gzip')
        else:
            continue

        dfa = pd.concat([dfa, df], ignore_index=True)

    # If nothing found, return empty instead of KeyError on 'date'
    if dfa.empty:
        return dfa

    # If something weird got concatenated without required columns, return empty (prevents KeyError)
    required_cols = {"date", "daysOut", "sym", "sharpe_ratio"}
    if not required_cols.issubset(set(dfa.columns)):
        return pd.DataFrame()

    # add date2 end date for window
    dfa['date_tmp'] = pd.to_datetime(dfa['date'])
    dfa['date2'] = (dfa['date_tmp'] + pd.to_timedelta(dfa['daysOut'], unit='D')).dt.strftime('%Y-%m-%d')
    del dfa['date_tmp']

    if ('Unnamed: 0' in dfa.columns):
        del dfa['Unnamed: 0']

    dfa = dfa[(dfa['date'] < date) & (dfa['date2'] > date)]

    idx = dfa.groupby('sym')['sharpe_ratio'].transform(max) == dfa['sharpe_ratio']
    dfa = dfa[idx].reset_index(drop=True)
    dfa = dfa.sort_values(by='sharpe_ratio', ascending=False).reset_index(drop=True)

    # Tag it so downstream/UI never has to guess
    dfa["opp_mode"] = opp_mode

    return dfa


#------------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    print('\n\n','ver 1.0 Create Active Opportunities for Today','\n')

    
    seasonal_years        = 10
    seasonal_years_return = 10
    days_before           = 0
    days_after            = 0
    active_days           = 30  # number of previous days to scan for active days
    resourceID            = '3'


    dates_list            = generate_dates_list(days_before,days_after)
    print(dates_list)
    # generate active list for resourceID, date, seasonal_years, seasonla_years_return and active_days lookback days
    # dfa = create_active_list(resourceID, dates_list[0], seasonal_years, seasonal_years_return, active_days, opp_mode="consecutive")
    dfa = create_active_list(resourceID, dates_list[0], seasonal_years, seasonal_years_return, active_days, opp_mode="PE1")


    print(dfa)