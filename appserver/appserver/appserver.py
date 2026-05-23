
#     ip_address = flask.request.remote_addr
#     redis_client2 is being used as a no sql database
#     redis_client  is being used as a expirable cache

#     changing name of mailerlite groups to have tt_ in the beginning stands for top 10 - keep seperate than other groups
#     a user can have only 1 of 4 tt groups 

#     to use logging a variables do as follows: 
#      logging.debug("d0,d1= %s,%s", d0,d1)

#################################################################################################
# function create_title_slug must be copied from webserver file: /home/flask/blog/blog_tools.py
# last updated on 8/7/2023
#################################################################################################

# on 12/10/2023 - added SR2 to appserver chartData4 - SR2 is only available to me now - it has to be turned on in settings - shows SR2 in
#                 oppTable and on seasonalchartstat on the bottom of Trend chart sharpe-ratio section 


# on 12/10/2023 - added an optional parameter to chartData4 for cut_off_years - this is to remove the outlier of 1931 on PE3 - SPX
#                 currently its only available to myself to do the cut off - its done by going to settings on the top left gear icon in desktop wave viewer

# 12/13/2023 chartdata4 was using the entry date's high and low - its now fixed the high and low dates are checked 1 day after entry date line 1142

# 1/2/2024 adding trading / autotrading functions with tradier api to this appserver - could be moved to a new service later

# 1/19/2024  tradier has most of everything I needed for tracking orders and positions except that it loses the order connection to
#            positions.  
#            there are 2 API calls in tradier under Account for orders  
#            1) get_order : returns all orders for the current market session
#            2) get_an_order : gets detailed information for all previous orders
#            to find the correction position, I have to get the order_id stored in redis and look for a filled order
#            the filled order has to then be cross referenced with positions to find the current position that belongs to this opp
# 5/1/2024   adding active list for days and years that have active opportunities list

# 5/8/2024   modified flask limiter due to error and then warning - this maybe due to installing the latest flask-limiter here
#            the chatGPT reference is this: https://chat.openai.com/share/0e66126d-de77-4609-b306-fac4afa7a378
#            this was first created on keyprovider but it has to work on the other servers too before continuing
# 6/18/2024  3 functions are added for autotrading - also a standalone async service runs to service trade exits autotrade_async.py
#            add_new_trades_to_live_trade_list
#            publish_symbols
#            check_is_trade_duplicate - still not done yet

###############################################################
# RISK PROFILE HAS TO BE FIXED
###############################################################


from flask import Flask, jsonify, request, session, make_response,Blueprint
from flask_cors import CORS
from flask_limiter import Limiter, HEADERS
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import pandas as pd
import datetime
from datetime import timedelta
import base64
import hashlib
import hmac
from dateutil.relativedelta import relativedelta
import glob
import json
from functools import wraps
import jwt
import requests
import logging
import redis
import statistics
import calendar
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from slugify import slugify
import socket
import mailerlite as MailerLite
import re
from urllib.parse import quote as _urlquote
sys.path.insert(0, '/home/flask')
import config
import config_autotrade
from pprint import pprint
from tradier_api import get_quotes, get_creditspreads_for_opportunity,get_accounting_info,desired_selections_bullish_bearish,get_positions
from tradier_api import get_orders,cancel_order,get_brokerage_clock,get_position_from_filled_order,get_one_order # 1/2/2024
from tradier_api import place_multileg_option_trade,update_multileg_option_order

# TW2: optional Sentry init - no-op when SENTRY_DSN is empty/placeholder
try:
    import sentry_sdk
    if hasattr(config, 'SENTRY_DSN') and config.SENTRY_DSN and 'PLACEHOLDER' not in config.SENTRY_DSN:
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[FlaskIntegration()], traces_sample_rate=0.1)
except ImportError:
    pass

from chatbot import chatbot_bp  # Import the chatbot Blueprint


# from appserver_apis import get_remote_OppList4, get_remote_chart_data4, get_remote_YearsMetaData2, get_remote_History2, get_remote_StockMetaData, get_remote_ListSymbols, get_remote_StockLastPrice, get_remote_StockPriceByDate, get_remote_consolidated_seasonal_chart2, get_remote_security_price


from risk_profile import get_option_prices_for_group_options
from create_active_opps import create_active_list

from seasonal_chart_funcs import get_file_cache_path, load_from_file_cache, save_to_file_cache

from get_symbol_csv import get_symbol_csv, num_years_in_df,days_ago_was_last_row
from get_name_from_ticker import get_security_name_from_ticker  # use get_security_name_from_ticker(exchange,ticker)

# call a function in the blog folder
# sys.path.append('/home/flask/blog')
# from article_prompt import create_article_prompt
# from blog_tools import get_company_name

# import tradier_api

# from autotrade import new_route_bp  # Import the new_route Blueprint

# dataframes are stored in redis as dictionaries.  When a dataframe with length=0 is stored, the column names are
# lost.  when retrieving a 0 length dictionary, there are no column names.  following variable is used to
# hold opp3 column names for the 0 length opp stored in redis.
opp3columns = ['LorS', 'date', 'daysOut', 'sym', 'stddev', 'sharpe_ratio', '1%', '2%',
               '3%', '4%', '5%', '6%', '7%', '8%', '9%', '10%', '15%', '20%', '25%', '35%', '50%']

# used for trading - it's the custom keys for custom exits
custom_exit_fields =['exitStockGain','exitOptionGain', 'daysAfter' ,'daysAfterGain', 'daysBefore','waveEndAction','earlyExcerciseAction']

logging.basicConfig(filename='/var/log/tradewave/appserver.log',level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s',force=True)

# db0 is used for caching
redis_client   = redis.Redis(host='localhost', port=6379, db=0)
# db1 is used for autotrading
redis_client1  = redis.Redis(host='localhost', port=6379, db=1)
# db 2 is used for user_report information 
# this is seperated because db2 is used as a persistent database - while db0 is used as a cache db
redis_client2  = redis.Redis(host='localhost', port=6379, db=2)  
# db3 is used to access the news article db on the webserver
redis_client3  = redis.Redis(host=config.webserver_ip,port=6379,db=3)


ddir = config.ddir

# keystoreURL = 'http://localhost:7777'
keystoreURL = config.keystoreURL

# use of variable application is requirement of aws
application = app = Flask(__name__)

app.register_blueprint(chatbot_bp, url_prefix="/chatbot")

# app.debug = True

# places the client ip in the right place when using cloudflare
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)
CORS(app)  # added for cross scripting support


limiter = Limiter( 
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379/0",  # Use Redis as storage backend
    headers_enabled=True
    )
limiter.init_app(app)

# error handler for rate-limit : this handler adds the trigger header to show which rate-limit triggered the 429


@app.errorhandler(429)
def ratelimit_handler(e):
    response = e.get_response()
    c = str(response.data)
    # getting 429 trigger info like "1/minute" out of html response.data - couldn't figure out a better way
    x0 = c.find('<p>')
    x1 = c.find('</p>')
    trigger = c[x0+3:x1]
    response.headers["trigger"] = trigger
    # this line allows all custom headers to be exposed
    response.headers['Access-Control-Expose-Headers'] = '*'

    return response


# this switch is to allow for content for non logged-in users
noLoginContent = config.noLoginContent

#############################################################
# static secret key only used by flask session
app.config['SECRET_KEY'] = config.APPSERVER_JWT_SECRET  # TW2: shared with web tier for LTK signing
#############################################################
available_resources = config.available_resources
available_resources_path = config.available_resources_path

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------    
def check_for_token(func):  # check if there is a valid token
    @wraps(func)
    def wrapped(*args, **kwargs):
        token = request.args.get('token')
        # puts spaces between lines after each call in debug output of flask 5000
        # print('')
        if not token:
            return jsonify({'message': 'Missing token'}), 403
        try:
            # TW2: verify aud='tw2-appserver' + iss='tw2-web' from F2's web-tier mint.
            # Tokens minted before that change won't carry these claims; users must
            # hard-reload /app/ to mint a fresh LTK.
            data = jwt.decode(
                token, app.config['SECRET_KEY'],
                algorithms=['HS256'],
                audience='tw2-appserver',
                issuer='tw2-web',
            )
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'session expired'}), 401
        except jwt.InvalidAudienceError:
            logging.warning("check_for_token: invalid/missing audience ip=%s ua=%s",
                            get_remote_address(), request.headers.get('User-Agent', '-'))
            return jsonify({'message': 'invalid token'}), 401
        except jwt.InvalidIssuerError:
            logging.warning("check_for_token: invalid/missing issuer ip=%s ua=%s",
                            get_remote_address(), request.headers.get('User-Agent', '-'))
            return jsonify({'message': 'invalid token'}), 401
        except jwt.DecodeError:
            return jsonify({'message': 'invalid token'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'invalid token'}), 401
        return func(*args, **kwargs)
    return wrapped
# # --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# # ticker_symbol_alias changes the name of a ticker - initially built for changing GSPC to SPX 10/8/2022
# alias_symbols = {'GSPC':'SPX','SPX':'GSPC'}
# def ticker_symbol_alias(symbol):
#     if symbol in alias_symbols.keys():
#         return alias_symbols[symbol]
#     return symbol

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# get all levels is used when admin without level logs in or useUMP = False

def get_all_levels():
    all_level_list = []
    for k in config.level_access_hierarchy.keys():
        all_level_list.extend(config.level_access_hierarchy[k])
    all_level_list = list(set(all_level_list))


    return config.admin_levels,[],config.admin_levels  # all_levels_old,free_levels,premium_levels
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# userid is wp userid a number like 2 or 3 or 124  -
# - get tokens key1 = login token  key2 = UMP access token
# - query UMP for levels array for the user
# - set directory access based on user levels

def is_leap_in_date_range(d1,d2):
    dr=set(pd.date_range(d1,d2,freq='d'))
    dr=list(set([date_obj.strftime('%Y-%m-%d') for date_obj in dr]))
    y1 = d1[:4]
    y2 = d2[:4]
    if y1+'-02-29' in dr or y2+'-02-29' in dr:
        return True
    
    return False
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def get_user_levels(key2, wp_userid):
    # TW2: WordPress UMP is gone and login() now gates access from the signed LTK,
    # so this helper is no longer called. Kept as a safe no-op that returns all
    # levels; the WordPress-plugin code below is unreachable (left for git history).
    return get_all_levels(),[],get_all_levels()

    url = f'{config.wordpress_url}wp-content/plugins/indeed-membership-pro/apigate.php?ihch={key2}&action=get_user_levels&uid={wp_userid}'
    response = requests.get(url, timeout=10)
    # print('response=',response)
    r = response.json()
    # print('r=',r)



    #################################################################################
    #               this is a not logged in user
    #################################################################################
    if noLoginContent == True and wp_userid == '0':
        # none logged in have access to djia but userid=0 will limit it to today only
        return config.non_loggedin_levels,config.non_loggedin_levels,[]

    if len(r['response']) == 0:  # this is an admin : give them everything
        return get_all_levels()

    # otherwise, return all the levels this subscriber has
    level_list = list(r['response'].keys())




    # print('level_list=',level_list)
    # level_list.append(level_access_hierarchy[])
    
    all_level_list = []
    levels_free_list = [] # 4/12/2022
    levels_prem_list = [] # 4/12/2022
    
    for l in level_list:
        all_level_list.extend(config.level_access_hierarchy[l])

        levels_free_list.extend(config.level_access_hierarchy_free_registered[l]) # 4/12/2022
        levels_prem_list.extend(config.level_access_hierarchy_premium[l]) # 4/12/2022


    all_level_list   = list(set(all_level_list))
    levels_free_list = list(set(levels_free_list)) # 4/12/2022
    levels_prem_list = list(set(levels_prem_list)) # 4/12/2022


    return all_level_list,levels_free_list,levels_prem_list
# ------------------------------------------------------------------------------
# selected resource folder passed from react app on the token payload


def get_resource_folder_from_token(token, resourceID):

    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')

    resourceName = data['resource_disp'][int(resourceID)]

    # print('......resourceName=',resourceName,data)

    rf = ''
    for r in available_resources.keys():
        if resourceName == available_resources[r]:
            rf = available_resources_path[r].replace('_symbols.csv', '')
# why isn't there a break under rf = ?
    return rf+'/'
# -------------------------------------------------------------------------------
# log activity by sending a request to logcollector flask service
# -------------------------------------------------------------------------------


def get_geo_from_token(token):
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')

    # parameters for isoformat removes microseconds
    atime = datetime.datetime.now().isoformat(' ', 'seconds')
    wp_userid = data['user']
    ipv4 = data['ipv4']
    country_code = data['country_code']
    zip = data['zip']

    return atime, wp_userid, ipv4, country_code, zip

# -------------------------------------------------------------------------------
# log activity by sending a request to logcollector flask service
# -------------------------------------------------------------------------------
def update_activity_log(activityTime, resourceID, wp_userid, ipv4, country_code, zip, activity):

    # print('log collection',config.logcollector_url)

    if config.logcollector_url == '': # logcollector is turned off for this server
        return

    serverName = os.uname()[1]  # this is the local server's hostname,
    # TW2: percent-encode user-controlled segments to prevent path traversal /
    # SSRF via odd characters. activityTime, resourceID & serverName are server-side.
    safe_userid = _urlquote(str(wp_userid), safe='')
    safe_ipv4 = _urlquote(str(ipv4), safe='')
    safe_country = _urlquote(str(country_code), safe='')
    safe_zip = _urlquote(str(zip), safe='')
    safe_activity = _urlquote(str(activity), safe='')
    activity_request = f'{config.logcollector_url}activity/{serverName}/{activityTime}/{resourceID}/{safe_userid}/{safe_ipv4}/{safe_country}/{safe_zip}/{safe_activity}'
    try:
        x = requests.get(activity_request, timeout=5)
    except Exception:
        logging.exception("update_activity_log: logcollector unreachable")

    

#---------------------------------------
# get number of reports user has created
#---------------------------------------
def get_num_reports(wp_userid):
    
    redis_key_user_reports = f'user_reports_{wp_userid}' 
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    num_reports_created = 0
    if redis_user_reports_list is not None:
        redis_user_reports_list = json.loads(redis_user_reports_list)
        num_reports_created = len(redis_user_reports_list)

    # print(redis_user_reports_list)
    return num_reports_created
        

#--------------------------------------------------------------------------------------------------------------------------

@app.route('/login/<string:wp_userid>/<string:user_level>/<string:country_code>/<string:zip>/<string:skey>', methods=['GET'])
@limiter.limit(config.rate_limit_login[0])
@limiter.limit(config.rate_limit_login[1])
@limiter.limit(config.rate_limit_login[2])
@limiter.limit(config.rate_limit_login[3])
def login(wp_userid, user_level, country_code, zip, skey): # I had ip for no reason - changed it to user_level 3/7/2023
    # with open("log.txt", "a+") as f: f.write("text")
    # print('login started')
    
    # find the two highest levels in order to decide to turn on the TradeWave_Ratio
    # use level_access_hierarchy in config
    two_highest_levels = list(map(str, sorted(map(int, config.level_access_hierarchy.keys()), reverse=True)[:2]))

    its_afshin = False
    tw2_ltk_claims = None

    # TW2: the skey MUST be a valid LTK JWT issued by the web tier. ALL gating
    # (admin status, user_level, identity) is sourced from the signed LTK claims -
    # URL parameters are decorative and cannot grant access.
    if not skey:
        return jsonify({'message': 'authentication required'}), 401
    try:
        # verify aud + iss; the web tier mints the LTK with these claims.
        tw2_ltk_claims = jwt.decode(
            skey, app.config['SECRET_KEY'],
            algorithms=['HS256'],
            audience='tw2-appserver',
            issuer='tw2-web',
        )
    except jwt.ExpiredSignatureError:
        return jsonify({'message': 'session expired'}), 401
    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError) as e:
        logging.warning("login: LTK aud/iss check failed: %s ip=%s ua=%s",
                        e, get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'invalid token'}), 401
    except Exception as e:
        logging.warning("login: invalid LTK: %s ip=%s ua=%s",
                        e, get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'invalid token'}), 401

    # Cross-check URL wp_userid against LTK user_id - prevents identity spoofing
    if str(tw2_ltk_claims.get('user_id')) != str(wp_userid):
        logging.warning("login: identity mismatch URL=%s LTK=%s ip=%s ua=%s",
                        wp_userid, tw2_ltk_claims.get('user_id'),
                        get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'identity mismatch'}), 403

    # Source ALL gating from the LTK. URL user_level parameter is decorative.
    user_level = str(tw2_ltk_claims.get('legacy_level') or '1')
    its_afshin = bool(tw2_ltk_claims.get('is_admin', False))

    ipv4 = get_remote_address()  # gets the address from headers returned by cloudflare
    
    # logging.debug('inside login ipv4='+ipv4)

    # TW2: gate by tier from the signed LTK. super_admin / service_account /
    # Afshin email get all levels (admin path); everyone else gets the access list
    # defined in config.level_access_hierarchy for their numeric user_level.
    if its_afshin:
        user_access_list,_,_ = get_all_levels()
    else:
        user_access_list = config.level_access_hierarchy.get(user_level, ['0'])
    logging.debug(user_access_list)



    session.new = True # This regenerates the session ID to prevent session fixation 10/3/2024

    session['logged-in'] = True  # problem line

    # *************************************
    # get available resources for user ***
    # *************************************
    disp_list = []
    disp_list_path = []
    for k in available_resources.keys():
        if k in user_access_list:
            disp_list.append(available_resources[k])
            disp_list_path.append(available_resources_path[k])
   
    
    
    # print('user_level=',user_level,type(user_level))
    # print('disp_list=',disp_list)
    # print('disp_list_path=',disp_list_path)

    # print( type(config.num_opp_reports_allowed_by_level[user_level] ),type(get_num_reports(wp_userid)))

    user_level = user_level.replace(',','')

    # print('uuuuuuuuuuuuuuuuuuuu',user_level,type(user_level))
    
    show_sr2 = 0 # by default don't show sr2 or TWR or TradeWave_Ratio - its called all of those
    if user_level in two_highest_levels and wp_userid != '0': # two highest levels of membership get to see these proprietry values
        show_sr2 = 1


    if country_code == 'undefined':
        country_code = '!' 
    if zip == 'undefined':
        zip = '!'

    num_allowed_reports = config.num_opp_reports_allowed_by_level.get(user_level, 0)
    if its_afshin: num_allowed_reports = 2000


    # add session variables to the token
    # TW2: aud + iss claims so check_for_token can verify them on every request.
    token = jwt.encode({
        'user': wp_userid,
        'user_level':user_level,
        'lid': user_access_list,
        'ipv4': ipv4,
        'country_code': country_code,
        'zip': zip,
        # 'resources':disp_list_path,
        'resource_disp': disp_list,
        'num_portfolios_allowed':config.num_portfolios_allowed_by_level.get(user_level, 0),
        'num_watchlists_allowed':config.num_watchlists_allowed_by_level.get(user_level, 0),
        'num_watchlist_items_allowed':config.num_watchlist_items_allowed_by_level.get(user_level, 0),
        'num_reports_allowed'   :num_allowed_reports, # its set above so that afshin can get more
        'num_reports_created':get_num_reports(wp_userid),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=config.session_expiration_hours),
        'upgrade_message' : config.upgrade_message,
        'promotion_message' : config.promotion_message,
        'promotion_coupon_code' : config.promotion_coupon_code,
        'promotion_back_color' : config.promotion_back_color,
        'show_sr2': show_sr2,
        'is_admin': its_afshin,  # TW2: from LTK claim, not legacy admin_userids list
        'aud': 'tw2-appserver',
        'iss': 'tw2-web',
    },
        app.config['SECRET_KEY'])

    atime = datetime.datetime.now().isoformat()
    ipv4 = get_remote_address()
    update_activity_log(atime, disp_list, wp_userid, ipv4, country_code, zip, 'login')

    # print('login done returning token',token)

    response = make_response(jsonify({
        'token': token,
        'ip':ipv4
    }))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# TW2: API-key login for service accounts (scorecard, ticker pages, blog gen).
# Replaces the multi-step keyprovider handshake those scripts used in TW1 prod.
# Looks up the HMAC-SHA256 hash of the submitted api_key in TW2 Postgres
# `users.api_key_hash`; on match, mints a JWT scoped to that user's
# legacy_wp_level (typically '6' for service accounts = full access (Strategist)).
# The plaintext column is gone (alembic 5a3c1e2f4d6b); the hash is the only
# server-side secret material for service-account auth.
@app.route('/login/api/<string:api_key>', methods=['GET'])
@limiter.limit("10/minute")
@limiter.limit(config.rate_limit_login[2])
@limiter.limit(config.rate_limit_login[3])
def login_api(api_key):
    import psycopg2, psycopg2.extras

    # TW2: brute-force guard. Reject empty / too-short keys before any DB hit so a
    # WHERE api_key_hash = <hash of ''> query can never match a real row.
    if not api_key or len(api_key) < 16:
        logging.warning("login_api: short/empty api_key rejected ip=%s ua=%s",
                        get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'invalid api_key'}), 401

    # Hash the submitted plaintext with the shared HMAC secret. Fail loud if
    # the secret is unset: returning 503 here is better than silently 403'ing
    # every legitimate caller because we hashed with an empty key.
    hmac_secret = getattr(config, 'API_KEY_HMAC_SECRET', '') or ''
    if not hmac_secret:
        logging.error("login_api: API_KEY_HMAC_SECRET not configured; refusing")
        return jsonify({'message': 'service misconfigured'}), 503
    submitted_hash = hmac.new(
        hmac_secret.encode('utf-8'),
        api_key.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    try:
        conn = psycopg2.connect(config.POSTGRES_DSN)
    except Exception:
        logging.exception("login_api: db unreachable ip=%s ua=%s",
                          get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'service unavailable'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, email, roles, tier, legacy_wp_level FROM users WHERE api_key_hash = %s",
            (submitted_hash,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if row is None:
        logging.warning("login_api: api_key not found ip=%s ua=%s",
                        get_remote_address(), request.headers.get('User-Agent', '-'))
        return jsonify({'message': 'invalid api_key'}), 403

    wp_userid    = str(row['id'])
    user_level   = (row['legacy_wp_level'] or '6').replace(',', '')
    country_code = request.args.get('country', 'IN')
    zip_arg      = request.args.get('zip', 'svc')

    # Mirror the level-list + display-name building from the regular login() route
    user_access_list, _, _ = get_all_levels()
    disp_list = [available_resources[k] for k in available_resources if k in user_access_list]

    token = jwt.encode({
        'user': wp_userid,
        'user_level': user_level,
        'lid': user_access_list,
        'ipv4': request.remote_addr or '127.0.0.1',
        'country_code': country_code,
        'zip': zip_arg,
        'resource_disp': disp_list,
        'num_portfolios_allowed': config.num_portfolios_allowed_by_level.get(user_level, 100),
        'num_watchlists_allowed': config.num_watchlists_allowed_by_level.get(user_level, 100),
        'num_watchlist_items_allowed': config.num_watchlist_items_allowed_by_level.get(user_level, 500),
        'num_reports_allowed': config.num_opp_reports_allowed_by_level.get(user_level, 2000),
        'num_reports_created': 0,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7),
        'upgrade_message': '',
        'promotion_message': '',
        'promotion_coupon_code': '',
        'promotion_back_color': '',
        'show_sr2': 1,
        'is_admin': True,
        'is_service_account': True,
        'tw2_user_id': str(row['id']),
        'tw2_email': row['email'],
        'tw2_tier': row['tier'],
        'aud': 'tw2-appserver',
        'iss': 'tw2-web',
    }, app.config['SECRET_KEY'])
    return jsonify({
        'token': token,
        'ip': request.remote_addr,
        'user_id': str(row['id']),
        'tier': row['tier'],
    })


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# 4/12/2022  - return resource obj from config back to react app
@app.route('/getResourcesObj', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_login[0])
@limiter.limit(config.rate_limit_login[1])
@limiter.limit(config.rate_limit_login[2])
@limiter.limit(config.rate_limit_login[3])
def getResourcesObj():
    # print('getResourcesObj=',config.available_resources)

    return jsonify({
        'resources': config.available_resources,
        'free':config.level_access_hierarchy_free_registered,
        'nonloggedin-resources':config.non_loggedin_levels,
        'prem':config.level_access_hierarchy_premium
    })

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------

@app.route('/', methods=['GET'])
@app.route('/<string:token>', methods=['GET'])
def root(token=''):
    logged_in = False
    if 'logged-in' in session:
        logged_in = session['logged-in']

    # if token != '':
        # 	data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
        # 	try:
        # 		data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
        # 	except jwt.ExpiredSignatureError:
        # 		return jsonify({'message': 'expired token'})
        # 	except jwt.DecodeError:
        # 		return jsonify({'message': 'decode error'})
        # 	except jwt.InvalidIssuerError:
        # 		return jsonify({'message': 'Invalid Issuer Error'})
        # 	except jwt.InvalidTokenError:
        # 		return jsonify({'message': 'invalid token error'})

    # version 5 has login with jwt token
    return jsonify({
        'message': 'ver 5.0',
        'logged-in': logged_in,
        'token': token,
        'ip': get_remote_address()
    })




# --------start opplist4------------------------------------------------------------------------------------------------------------------------------------------------------------
# version 4 returns a list of lists instead of dictionary.  saves around 40% in size
# add active list to opplist4 based on module create_acitve_opps.py
# mode: selects opportunity dataset ('consecutive' default, 'pe' = presidential election cycle
@app.route('/OppList4/<string:resourceID>/<string:month>/<string:day>/<string:year1>/<string:year2>/<string:day_range>/<string:oppListExpanded>/<string:apply_filter>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_opp[0])
@limiter.limit(config.rate_limit_opp[1])
@limiter.limit(config.rate_limit_opp[2])
@limiter.limit(config.rate_limit_opp[3])
def OppList4(resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0',symbol=''):

    token = request.args.get("token")
    mode = request.args.get("mode", "consecutive")
    if mode != "pe":
        mode = "consecutive"

    # Defense-in-depth: reject obviously-invalid resourceIDs (e.g., '-1' from a
    # React first-load race before /getResourcesObj has populated). Return an
    # empty OppList with 400 so the front-end renders gracefully instead of 500.
    if resourceID == '-1' or resourceID not in available_resources:
        return jsonify({'OppList': [], 'error': 'invalid_resource_id'}), 400

    print('resourceID, month, day, year1, year2,day_range=',resourceID, month, day, year1, year2,day_range,mode)

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    current_year = int(today_date[:4])
    pe_phase = current_year % 4

    folder_suffix = f"_PE{pe_phase}" if mode == "pe" else ""
    redis_suffix  = f"_PE{pe_phase}" if mode == "pe" else "_CON"

    resourceFolder = get_resource_folder_from_token(token, resourceID)
     # get the userid from token
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    # print('data=',data)
    userid = data['user']            # userid 0 is not logged-in
    userlevel = data['user_level']   # userlevel = '1' is free Ripple


    day_range_n1=0 # used for filtering now 12/2/2023
    day_range_n2=0

    if day_range != '-': # days_range added as input to opplist4 to first use the day range to filter before selecting the highest sharpe_ratios
        # print('day_range=',day_range)
        s= day_range.split('-')
        day_range_n1=int(s[0])
        day_range_n2=int(s[1])  


    
    

    # print('opplist4 day_range=',day_range)


    month_num = datetime.datetime.strptime(month, '%B').month
    # create the exact selected opp date
    filter_date = f"{today_date[:4]}-{str(month_num).zfill(2)}-{day.zfill(2)}"
    next_trading_day = filter_date # used for weekends and holidays

    # should be updated based on user levels
    maxOppReturned = config.max_opportunities_returned

    # print('\n\n',oppListExpanded,'\n\n')

    

    # print('resourceFolder = ',resourceFolder)

   

    # print('userid=',userid)

    # fname = opportunities_dir+'Monthly_Opp_'+month+'_'+year1+'_'+year2+'.h5'
    # this is the oppPath for the month we want, however there is case if monday is 1st of the month,
    # we need the previous month days that are the weekend also, so we need oppPath_prev_month also 1/16/2023

    oppPath = resourceFolder+'opportunities/' +  'Monthly_Opp_'+month+'_'+year1+'_'+year2 + folder_suffix
    prev_month_num = month_num-1
    if prev_month_num == 0:prev_month_num = 12
    prev_month_name = calendar.month_name[prev_month_num]
    oppPath_prev = resourceFolder+'opportunities/' +  'Monthly_Opp_'+prev_month_name+'_'+year1+'_'+year2 + folder_suffix
    
    next_month_num = month_num+1
    if next_month_num == 13:next_month_num = 1
    next_month_name = calendar.month_name[next_month_num]
    oppPath_next = resourceFolder+'opportunities/' +  'Monthly_Opp_'+next_month_name+'_'+year1+'_'+year2 + folder_suffix


    # print('****************',oppPath_prev,oppPath_next)

    # only format = 4 is used now - 1,2,3 are deprecated
    format = 1 # format 1 is the old version all month in 1 h5 file
               # format 2 is the newer version every day of the month a different key in h5 file
               # format 3 is opp is a folder with each day of the month as a csv file
               # format 4 is opp is a folder with each day of th emonth as a compressed csv file
    fname=oppPath+'.h5'
    fname_folder=oppPath+'/'
    if os.path.isdir(fname_folder):
        format=3 # or 4
   
 
    elif os.path.isfile(fname) == True: format=2 # format is 1 or 2
    else: return jsonify({'OppList': '-1:'+fname}) # -1 is missing opp file
    ###############################################
    # redis interface
    ###############################################
    u = '0'
    if userid != '0':
        u = '1'

    # redis_key_opp = 'opp4_' + resourceID+'_'+month+'_'+day+'_'+year1+'_'+year2+'_' + oppListExpanded + '_' + u  # username 0 is non-loggedin 1 is loggedin - opportunities opp
    redis_key_opp  = 'opp4_'  + resourceID+'_'+month+'_'+day+'_'+year1+'_'+year2+'_' +day_range+'_'+oppListExpanded + '_' + u + redis_suffix # username 0 is non-loggedin 1 is loggedin - opportunities opp
    redis_key_oppa = 'oppa4_' + resourceID+'_'+month+'_'+day+'_'+year1+'_'+year2+'_' +day_range+'_'+oppListExpanded + '_' + u + redis_suffix # username 0 is non-loggedin 1 is loggedin - opportunities opp
    

    opp_redis  = redis_client.get(redis_key_opp)
    oppa_redis = redis_client.get(redis_key_oppa) # this is for active opportunites


    #######################
    # this is debug code
    #######################
    # if opp_redis is not None and oppa_redis is not None:
    #     opp_=json.loads(opp_redis)
    #     print('11111111111111111111','content from local redis cache: opp_redis=',type(opp_),opp_)






    #---------------------------------------------------------------------------------------------------
    # this section processing opp day consolidation for weekends and holidays
    #---------------------------------------------------------------------------------------------------
    # check if filter date is weekend, monday or a known holiday
    # weekends and mondays consolidate sat sun and mon
    # known holidays consolidate with the next weekday that is not a weekend
    # 0 is monday 5,6 are weekend days
    day_of_week = datetime.datetime.strptime(filter_date, '%Y-%m-%d').weekday()
    # days list is a list of positive and negative integers showing which days to add to today.  
    # by default [0] means just today [0,1,2] means add today tommorow and the next day
    # mondays should show [0,-1,-2] to add previous sun and sat
    daysList=[0]
    if   day_of_week == 5:
        daysList=[0,1,2]   # sat
        next_trading_day = inc_date_day(filter_date, 2)
    elif day_of_week == 6:
        daysList=[0,-1,1]  # sun
        next_trading_day = inc_date_day(filter_date, 1)
    elif day_of_week == 0:
        daysList=[0,-1,-2] # mon
        # next trading day is already monday - no need to set it

    # holdiays to support jan1, dec 25
    if daysList == [0] and (filter_date[5:] == '01-01' or filter_date[5:] == '12-25'):
        if day_of_week == 4: 
            daysList=[0,1,2,3] #friday
            next_trading_day = inc_date_day(filter_date, 3)
        else: 
            daysList=[0,1] # mon through thursday
            next_trading_day = inc_date_day(filter_date, 1)
    # now create a list of dates based on daysList
    # print('next trading day=',next_trading_day)
    datesListDates = [filter_date]
    if len(daysList)>1:
        for i in range(1,len(daysList)):
            datesListDates.append(inc_date_day(filter_date, daysList[i]))
        datesListDates.sort() 

        
    current_year = int(today_date[:4])
    for d in datesListDates:
        if int(d[:4])<current_year:
            datesListDates.remove(d)

   

    # print(datesListDates[-1][5:7])
    # print(datesListDates[1 ][5:7])
        
    #---------------------------------------------------------------------------------------------------

    # print('opp and oppa',opp_redis is None,oppa_redis is None)
# 
    if opp_redis is None or oppa_redis is None:

        if format == 3: # its always format 3 - format 1 and 2 are deprecated

            # print('datesListDates=',datesListDates)

            opp  = pd.DataFrame()
            oppa = pd.DataFrame() # holds the active wave list if exists in this folder 5/2/2024

            # check if there are active opp list for this date in this folder 2/5/2024
            active_file = f'{fname_folder}a{filter_date}.csv.gz'
            # print('active_file=',active_file)

            # if os.path.isfile(active_file) == True:
            #     oppa = pd.read_csv(active_file, compression='gzip')

            # sat sun mon have 3 possibilities of month change 4/27/2023
            # 1- sat sun mon are all the same month
            # 2- sat is last day of the month - sun is 1st - mon is 2nd
            # 3- sun is last day of the month - mon is 1st
            typ = 0 # this is when mid week and datesListDate length = 1 
            if len(datesListDates) == 3:
                m1=int(datesListDates[0][5:7])
                m2=int(datesListDates[1][5:7])
                m3=int(datesListDates[2][5:7])
                if   m1 == m2 and m2 == m3:typ = 1
                elif m2 != m1 and m2 == m3:typ = 2
                elif m1 == m2 and m2 != m3:typ = 3
                else                      :typ = -1

            # all the conditions are necessary to support change of month inside the weekend sat sun mon
            # type 2 example is sep30 oct1 oct2 in 2023
            # type 3 example is apr29 apr30 may1 in 2023
            for i in range(len(datesListDates)):
      
                d = datesListDates[i]
                if typ == 0 : p = fname_folder + d+'.csv.gz'
                if typ == 1 : p = fname_folder + d+'.csv.gz'
                if typ == 2 :
                    if i == 0:
                        if month_num == m1:
                            p = fname_folder + d+'.csv.gz'
                        else:
                            p = oppPath_prev+'/' + d +'.csv.gz' 
                    else:
                        if month_num == m1:
                            p = oppPath_next+'/' + d +'.csv.gz'
                        else:
                            p = fname_folder + d+'.csv.gz'
                if typ == 3 : 
                    if i == 0 or i == 1: 
                        if month_num == m1:
                            p = fname_folder + d+'.csv.gz'
                        else:
                            p = oppPath_prev +'/' + d+'.csv.gz'
                    else:
                        p = oppPath_next +'/' + d+'.csv.gz'

                
                if os.path.isfile(p) == False:
                    p = fname_folder + d+'.csv.gz'
                    if os.path.isfile(p) == False: 
                        return jsonify({'OppList': []}) # there is no data for this date - file is missing
                    else:      
                        if opp.shape == (0,0): 
                            opp = pd.read_csv(p)
                        else: opp = pd.concat([opp,pd.read_csv(p)])
                else:         
                    if opp.shape == (0,0): 
                        opp = pd.read_csv(p)
                    else:                  
                        opp = pd.concat([opp,pd.read_csv(p)])
                
                
                # print('ooooooooooooooooooooooooopp=',opp,'\n\n')


                # remove symbols listed in config - these are symbols that aren't being updated for some reason
                if resourceID in config.drop_symbols_by_market: 
                    # print('before',opp.shape[0],opp)
                    opp = opp[~opp['sym'].isin(config.drop_symbols_by_market[resourceID])]
                    # print('after',opp)

                # change all the dates on the opp list to next_trading_day to support weekend and holidays
                # opp['date']=next_trading_day # keep the dates as is 9/11/2022
            

        # this is dead code from when I had format =1 or format = 2

        # else:# format is 2 or 1
        #     with pd.HDFStore(fname) as hdf:
        #         keys = hdf.keys()  # added 1/7/2022
        #     if len(keys) == 0: # this is the folder format
        #         print('folder format')
        #     elif len(keys) > 1:  # this is the new format with each day in a different key
        #         opp = pd.read_hdf(fname, key='d'+filter_date.replace('-', ''))
        #     else:  # this is the old format with the entire month as 1 flat df
        #         opp = pd.read_hdf(fname)
        #         opp = opp[opp['date'] == filter_date]

        

        #----------------------------------------------------------------------------------------------------
        # filter by day range here 12/2/2023
        if day_range_n2 > 0: # second number gott to be bigger
            opp = opp[ (opp['daysOut'] >= day_range_n1) & (opp['daysOut'] <= day_range_n2)]
        #----------------------------------------------------------------------------------------------------

        ###################################################################################################
        # if oppListExpanded == 0 filter by daysOut - only show  max sharpe_ratio for each ticker symbol;
        
        if oppListExpanded == '0':

            opp['daysOut'] = opp['daysOut'].astype(int)
            opp['sharpe_ratio'] = opp['sharpe_ratio'].astype(float)

            # get the min daysOut and max sharpe_ratio entries for each symbol - do it by groupby

            idx = opp.groupby(['sym'])['daysOut'].transform(min) == opp['daysOut']
            opp_min = opp[idx]  # min daysout for each symbol
            # get max sharpe_ratio opportunities
            idx = opp.groupby(['sym'])['sharpe_ratio'].transform(max) == opp['sharpe_ratio']
            opp_max = opp[idx]  # max sharpe_ratio for each ticker symbol

            # if there is more than 1 highest sharpe_ratio, then select the one with shortest daysOut
            idx = opp_max.groupby(['sym'])['daysOut'].transform(min) == opp_max['daysOut']
            opp_max = opp_max[idx]  # max sharpe_ratio for each ticker symbol


            # opp = pd.concat([opp_min, opp_max], ignore_index=True).sort_values('sym').reset_index(drop=True)
            opp = pd.concat([opp_max], ignore_index=True).sort_values('sym').reset_index(drop=True) # 6/5/2022 - dropping opp_min

            opp = opp.drop_duplicates()

            opp['daysOut'] = opp['daysOut'].astype(str)
            opp['sharpe_ratio'] = opp['sharpe_ratio'].astype(str)
          

        # sort the opplist by ticker and daysOut
        opp['daysOuti'] = opp['daysOut'].apply(pd.to_numeric)  # dayouti is for sorting only
        opp = opp.sort_values(['sym', 'daysOuti'], ascending=[True, True])
        # just needed it for sorting - dropping after
        opp = opp.drop(labels='daysOuti', axis=1)

        ###### new sort - above sort can be removed ########
        opp['srn'] = opp['sharpe_ratio'].apply(pd.to_numeric)
        opp = opp.sort_values('srn', ascending=False)
        opp = opp.drop(labels='srn', axis=1)

        
        ###################################################################################################
        odic = opp.to_dict(orient='records')
        redis_client.set(redis_key_opp, json.dumps(odic))
        redis_client.expire(redis_key_opp, config.opp_expire_time)
        
        ######################################################################################################
        # get active opp list from create_active_opps.py - it generates it just in time and saves it in redis
        ######################################################################################################
        opp_mode = f"PE{pe_phase}" if mode == "pe" else "consecutive"
        oppa = create_active_list(
            resourceID,
            filter_date,
            int(year1),
            int(year2),
            config.active_days,
            opp_mode=opp_mode,
            resourceFolder=resourceFolder,   # NEW: see Step 5.2
        )
        
        # print(oppa)
        # save the active opplist to redis 5/2/2024
        oadic = oppa.to_dict(orient='records')
        redis_client.set(redis_key_oppa, json.dumps(oadic))
        redis_client.expire(redis_key_oppa, config.opp_expire_time)



    else:
        opp  = pd.DataFrame(json.loads(opp_redis))
        oppa = pd.DataFrame(json.loads(oppa_redis))

    # ------------------------------------------------------------------------
    # now we have opp llist - if symbol != '' then filter by symbol 12/4/2023
    # ------------------------------------------------------------------------
    # print(opp.columns)
    if symbol != '': # this is a symbol passed to the function
        opp = opp[opp['sym']==symbol]
    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4,country_code, zip, redis_key_opp)

    # ---------------------------------------------------------------------------------------
    # convert opp filter columns to numeric - problem occured after opportunities ver6 11/12/2021
    # get all filter columns
    filter_columns = [x for x in opp.columns if '%' in x]
    # convert filter columns to numeric - stopped working otherwise since ver 6
    opp[filter_columns] = opp[filter_columns].apply(pd.to_numeric)
    # ---------------------------------------------------------------------------------------

#########################################################################
# none logged-in users
#########################################################################
    if userid == '0':  # not logged-in
        # opp = opp[opp['date'] == today_date]
        maxOppReturned = config.max_opportunities_not_loggedin

#########################################################################
# logged-in users - free ripple
#########################################################################
    if userlevel == '1':  # free logged in : Ripple
        maxOppReturned = config.max_opportunities_loggedin_free

#########################################################################
# logged-in paid users on a market they only have FREE (date-locked) access to
# - same per-query cap as Ripple, regardless of tier (Strategist viewing
# futures/forex sees only the top 5 patterns, not 5000).
#########################################################################
    user_free_resources = config.level_access_hierarchy_free_registered.get(userlevel, [])
    if str(resourceID) in user_free_resources:
        maxOppReturned = config.max_opportunities_loggedin_free
#
#-------------------------------------------------------------------------
    if opp.shape[0] > maxOppReturned: # this is how I fixed the top 10 to match the blog reports 2/23/2023
        # print(opp)
        opp = opp[:maxOppReturned]

    filters = {'0%': opp.shape[0]}  # get all possible filters
    for c in opp.columns:
        if '%' in c:
            filters[c] = opp[c].sum()

    available_filters = []  # only filters that return less than maxOppReturned
    # save key and value of the largest filter that is > maxOppReturned 
    # and the next filter is smaller.  we want the smallest number that is > maxOppReturned
    sm_k='0%'
    sm_v=10000
    
    for k, v in filters.items():
        if v > 0 and v<sm_v and v >= maxOppReturned:
            sm_v=v # this is the smallest Key,value > maxOppReturned
            sm_k=k
    # add filters that are smaller or equal to sm_v
    for k, v in filters.items():
        if v>0 and v <= sm_v:
            available_filters.append(k)

    # if the opportunity number in config is too little, just don't put any filter
    if len(available_filters) == 0:
        available_filters.append('0%')



    if apply_filter+'%' in available_filters:
        applied_filter = apply_filter
    else:
        applied_filter = available_filters[0][:-1]

    

    # apply filter
    if applied_filter != '0':
        oppf = opp[opp[applied_filter+'%'] == 1]

        
        if oppf.shape[0] == 0:
            applied_filter = '0'
        else:
            opp = oppf
    
    # ------------------------------------------------------------------------------------------------
    if opp.shape[0] == 0:  # dictionary length 0 loses column names when converted to dataframe. redis storage
        for c in opp3columns:
            opp[c] = ''
    # ------------------------------------------------------------------------------------------------

    opp['LorS'] = opp['LorS'] .str.replace('l', 'Long').str.replace('s', 'Short')
    opp  = opp.rename(columns={'sym': 'symbol', 'LorS': 'lOrS'})
    opp  = opp[['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio','avg_profit','median_profit','avg_profit2','sharpe_ratio2']] # after adding sharpe_ratio2 12/1/2023
    if opp.shape[0] > maxOppReturned: # crop the list to be at most maxOppReturned
        opp = opp[:maxOppReturned]
    l  = opp.values.tolist()  # this is the  change to opplist4

    if oppa.empty: # when there are no active opportunities for this date oppa is empty
        la=[]
    else:          # this is for active opportunities 2/5/2024
        oppa['LorS'] = oppa['LorS'] .str.replace('l', 'Long').str.replace('s', 'Short')
        oppa  = oppa.rename(columns={'sym': 'symbol', 'LorS': 'lOrS'})
        oppa = oppa[['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio','avg_profit','median_profit','avg_profit2','sharpe_ratio2']] # after adding sharpe_ratio2 5/2/2024
        la = oppa.values.tolist() 

    # print('OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOppList Length=',len(l))
    # dfx = pd.DataFrame(l)
    # columns=['date','sym','days','dir','SR','AvgP','medianP','AvgP2','SR2']
    # dfx.to_csv('dfx.csv')
    # print(dfx)

    # Merge real-time prices for symbols in the opp lists
    # all_prices format: {symbol: [price, change_p]}
    all_prices = get_realtime_prices_cached()
    opp_prices = {}
    if all_prices:
        for row in l:
            if len(row) > 1 and row[1] in all_prices:
                p = all_prices[row[1]]
                opp_prices[row[1]] = {'price': p[0], 'change_p': p[1]}
        for row in la:
            if len(row) > 1 and row[1] not in opp_prices and row[1] in all_prices:
                p = all_prices[row[1]]
                opp_prices[row[1]] = {'price': p[0], 'change_p': p[1]}

    # Check if this user+market qualifies for ML score columns
    ml_enabled = False
    if resourceID in config.ml_score_resource_ids:
        if config.ml_score_access_mode == 'list' and str(userid) in config.ml_score_userids:
            ml_enabled = True
        elif config.ml_score_access_mode == 'level' and str(userlevel) in config.ml_score_access_levels:
            ml_enabled = True

    return jsonify({'OppList': l,'OppActiveList':la ,'AvailableFilters': available_filters, 'applied_filter': applied_filter, 'prices': opp_prices, 'ml_enabled': ml_enabled})
# --------end opplist4------------------------------------------------------------------------------------------------------------------------------------------------------------


# --------start OppBySymbol-------------------------------------------------------------------------------------------------------------------------------------------------------
# Returns best opportunities for a single symbol across the year from the opp_by_symbol folder structure.
# One entry per start date (highest sharpe_ratio; tie-break: shortest daysOut), sorted by sharpe_ratio desc.
# Folder: <resourceFolder>opp_by_symbol/<year1>_<year2>[_PE<phase>]/<symbol>.csv.gz
# Parameters mirror OppList4: year1/year2 are lookback/min-profitable-years, day_range filters by hold duration, mode=consecutive|pe
# top_pct (optional query param, default=10): return only the top N% by sharpe_ratio
@app.route('/OppBySymbol/<string:resourceID>/<string:symbol>/<string:year1>/<string:year2>/<string:day_range>/<int:top_pct>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_opp[0])
@limiter.limit(config.rate_limit_opp[1])
@limiter.limit(config.rate_limit_opp[2])
@limiter.limit(config.rate_limit_opp[3])
def OppBySymbol(resourceID, symbol, year1, year2, day_range, top_pct):

    token   = request.args.get("token")
    mode    = request.args.get("mode", "consecutive")
    if mode != "pe":
        mode = "consecutive"

    current_year = int(datetime.datetime.now().strftime("%Y"))
    pe_phase     = current_year % 4

    folder_suffix = f"_PE{pe_phase}" if mode == "pe" else ""
    redis_suffix  = f"_PE{pe_phase}" if mode == "pe" else "_CON"

    resourceFolder = get_resource_folder_from_token(token, resourceID)
    data      = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    wp_userid = data['user']

    day_range_n1 = 0
    day_range_n2 = 0
    if day_range != '-':
        s = day_range.split('-')
        day_range_n1 = int(s[0])
        day_range_n2 = int(s[1])

    # top_pct is not part of the cache key - the full deduped+sorted list is cached,
    # and the top_pct slice is applied at serve time
    redis_key = f'opp_by_sym_{resourceID}_{symbol}_{year1}_{year2}_{day_range}{redis_suffix}'
    opp_redis = redis_client.get(redis_key)

    if opp_redis is None:

        opp_by_symbol_dir = f'{resourceFolder}opp_by_symbol'
        opp_path = f'{opp_by_symbol_dir}/{symbol}/{year1}_{year2}{folder_suffix}.csv.gz'

        if not os.path.isdir(opp_by_symbol_dir) or not os.path.isfile(opp_path):
            return jsonify({'OppBySymbol': [], 'status': 'feature_not_available'})

        opp = pd.read_csv(opp_path, compression='gzip')

        # filter by hold duration (daysOut) when day_range is specified
        if day_range_n2 > 0:
            opp = opp[(opp['daysOut'] >= day_range_n1) & (opp['daysOut'] <= day_range_n2)]

        opp['sharpe_ratio'] = opp['sharpe_ratio'].astype(float)
        opp['daysOut']      = opp['daysOut'].astype(int)

        # one entry per start date: best sharpe_ratio; tie-break on shortest daysOut
        idx = opp.groupby('date')['sharpe_ratio'].transform(max) == opp['sharpe_ratio']
        opp = opp[idx]
        idx = opp.groupby('date')['daysOut'].transform(min) == opp['daysOut']
        opp = opp[idx]
        opp = opp.drop_duplicates(subset=['date'])

        # sort by sharpe_ratio descending - best opportunities on top
        opp = opp.sort_values('sharpe_ratio', ascending=False).reset_index(drop=True)

        odic = opp.to_dict(orient='records')
        redis_client.set(redis_key, json.dumps(odic))
        redis_client.expire(redis_key, config.opp_by_symbol_expire_time)

    else:
        opp = pd.DataFrame(json.loads(opp_redis))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key)

    if opp.empty:
        return jsonify({'OppBySymbol': [], 'status': 'ok'})

    # apply top_pct slice after cache read - keeps cache generic across different top_pct values
    import math
    top_n = max(1, math.ceil(len(opp) * top_pct / 100))
    opp = opp.head(top_n)

    opp['LorS'] = opp['LorS'].str.replace('l', 'Long').str.replace('s', 'Short')
    opp = opp.rename(columns={'sym': 'symbol', 'LorS': 'lOrS'})
    opp = opp[['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'avg_profit', 'median_profit', 'avg_profit2', 'sharpe_ratio2']]

    l = opp.values.tolist()

    return jsonify({'OppBySymbol': l, 'status': 'ok'})
# --------end OppBySymbol---------------------------------------------------------------------------------------------------------------------------------------------------------


def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------


def inc_date_year(d, i):
    return ((datetime.datetime.strptime(d, '%Y-%m-%d') + relativedelta(years=i)).strftime('%Y-%m-%d'))
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# 5/16/2022 - stock score is from 0 to 100 - lscore 100 would be bullish while sscore of 100 would be bearish
# stockscore is obtained from service running on keyprovider
# when currentFlag = 0 then use date for score,
# when currentFlag = 1 then use today for score 
def stockscore(resourceID, symbol,date):


    redis_key_stockscore = 'stockscore_'+resourceID+'_'+symbol

    stockscore_redis = redis_client.get(redis_key_stockscore)


    # stockscore_redis = None  # for testing remove


    if stockscore_redis is not None:
        stockscore = json.loads(stockscore_redis)
        # print('from redis:',stockscore,type(stockscore))
        lscore=stockscore['lscore']
        sscore=stockscore['sscore']
        lscore1=stockscore['lscore1']
        sscore1=stockscore['sscore1']
    else:

        lscore = 0
        sscore = 0
        lscore1 = 0
        sscore1 = 0

        if config.stockscore_url == '':  # no stock score for this server
            return lscore,sscore,lscore1,sscore1

        url = f'{config.stockscore_url}stockscore/{resourceID}/{symbol}'

        x = requests.get(url, timeout=10)

        
        if x.status_code == 200:
            j = x.json()


            lscore = j['lscore']
            sscore = j['sscore']
            lscore1 = j['lscore1']
            sscore1 = j['sscore1']
        
            redis_client.set(redis_key_stockscore, json.dumps(j))
            redis_client.expire(redis_key_stockscore, config.stockscore_expire_time)

    

    return lscore,sscore,lscore1,sscore1

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Batch stockscore endpoint - returns stockscores for multiple symbols in one call
# Uses daily Redis caching so first user of day pays cost, subsequent users get cache hits
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/StockScoreBatch/<string:resourceID>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_stockscore[0])
@limiter.limit(config.rate_limit_stockscore[1])
@limiter.limit(config.rate_limit_stockscore[2])
@limiter.limit(config.rate_limit_stockscore[3])
def StockScoreBatch(resourceID):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "bad_json"}), 400
    symbols = data.get('symbols', [])

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    results = {}
    uncached_symbols = []

    # First pass: check Redis cache for all symbols
    for symbol in symbols:
        redis_key = f'stockscore_daily_{resourceID}_{symbol}_{today_str}'
        cached = redis_client.get(redis_key)
        if cached is not None:
            results[symbol] = json.loads(cached)
        else:
            uncached_symbols.append(symbol)

    # Second pass: fetch uncached symbols in parallel
    def fetch_one(symbol):
        lscore, sscore, lscore1, sscore1 = stockscore(resourceID, symbol, today_str)
        scores = {
            'lscore': lscore,
            'sscore': sscore,
            'lscore1': lscore1,
            'sscore1': sscore1
        }
        redis_key = f'stockscore_daily_{resourceID}_{symbol}_{today_str}'
        redis_client.set(redis_key, json.dumps(scores))
        redis_client.expire(redis_key, config.stockscore_daily_expire_time)
        return symbol, scores

    if uncached_symbols:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(fetch_one, sym): sym for sym in uncached_symbols}
            for future in as_completed(futures):
                try:
                    symbol, scores = future.result()
                    results[symbol] = scores
                except Exception as e:
                    sym = futures[future]
                    results[sym] = {'lscore': 0, 'sscore': 0, 'lscore1': 0, 'sscore1': 0}

    return jsonify({'stockscores': results})

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# ML Score endpoints - async trickle-in scoring for opportunity table
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------

def _ml_ttl_seconds():
    """Seconds until midnight of the next trading day (Mon-Fri).
    Fri/Sat/Sun scores expire at midnight Monday."""
    now = datetime.datetime.now()
    dow = now.weekday()  # 0=Mon ... 6=Sun
    if dow == 4:      # Friday -> expire midnight Monday (3 days)
        days_ahead = 3
    elif dow == 5:    # Saturday -> expire midnight Monday (2 days)
        days_ahead = 2
    elif dow == 6:    # Sunday -> expire midnight Monday (1 day)
        days_ahead = 1
    else:             # Mon-Thu -> expire midnight tonight
        days_ahead = 1
    midnight = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((midnight - now).total_seconds()), 60)


def _ml_check_access(token):
    """Check if user has ML score access. Returns (userid, userlevel) or (None, None) if denied."""
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
        userid = str(data.get('user', '0'))
        userlevel = str(data.get('user_level', '1'))
    except Exception:
        return None, None

    if config.ml_score_access_mode == 'list':
        if userid not in config.ml_score_userids:
            return None, None
    elif config.ml_score_access_mode == 'level':
        if userlevel not in config.ml_score_access_levels:
            return None, None

    return userid, userlevel


def _ml_redis_key(sym, opp_date, days_out, direction):
    """Redis key for a cached ML score. Includes today's date so scores expire naturally."""
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    return f'ml4_{today}_{sym}_{opp_date}_{days_out}_{direction}'


def _ml_tier(days_out):
    """Return the ML scorer tier for a given daysOut, or None if out of range."""
    if days_out <= 30:
        return '10_30'
    elif days_out <= 60:
        return '31_60'
    elif days_out <= 90:
        return '61_90'
    return None


@app.route('/MLScoreBatch/<string:resourceID>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_mlscore[0])
@limiter.limit(config.rate_limit_mlscore[1])
@limiter.limit(config.rate_limit_mlscore[2])
@limiter.limit(config.rate_limit_mlscore[3])
def MLScoreBatch(resourceID):
    """Receive opportunity tuples, return cached scores + pending list.
    POST body: { "opportunities": [ {symbol, date, daysOut, direction}, ... ] }
    Response:  { "scores": { "AAPL|19|l": {...}, ... }, "pending": [ {symbol,date,daysOut,direction}, ... ] }
    """
    token = request.args.get('token')
    userid, userlevel = _ml_check_access(token)
    if userid is None:
        return jsonify({'scores': {}, 'pending': []})

    if resourceID not in config.ml_score_resource_ids:
        return jsonify({'scores': {}, 'pending': []})

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "bad_json"}), 400
    opps = data.get('opportunities', [])
    if not opps:
        return jsonify({'scores': {}, 'pending': []})

    scores = {}
    pending = []

    for opp in opps:
        sym = opp.get('symbol', '')
        opp_date = opp.get('date', '')
        days_out = int(opp.get('daysOut', 0))
        direction = opp.get('direction', '')
        if not all([sym, opp_date, days_out, direction]):
            continue
        if _ml_tier(days_out) is None:
            continue

        rkey = _ml_redis_key(sym, opp_date, days_out, direction)
        cached = redis_client.get(rkey)
        ui_key = f'{sym}|{days_out}|{direction}'

        if cached is not None:
            scores[ui_key] = json.loads(cached)
        else:
            pending.append({'symbol': sym, 'date': opp_date, 'daysOut': days_out, 'direction': direction})

    return jsonify({'scores': scores, 'pending': pending})


@app.route('/MLScorePending/<string:resourceID>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_mlscore[0])
@limiter.limit(config.rate_limit_mlscore[1])
@limiter.limit(config.rate_limit_mlscore[2])
@limiter.limit(config.rate_limit_mlscore[3])
def MLScorePending(resourceID):
    """Poll endpoint: check Redis for pending keys, score a chunk of misses via keyprovider.
    POST body: { "pending": [ {symbol, date, daysOut, direction}, ... ] }
    Response:  { "scores": { "AAPL|19|l": {...}, ... }, "still_pending": [ ... ] }
    """
    token = request.args.get('token')
    userid, userlevel = _ml_check_access(token)
    if userid is None:
        return jsonify({'scores': {}, 'still_pending': []})

    if resourceID not in config.ml_score_resource_ids:
        return jsonify({'scores': {}, 'still_pending': []})

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "bad_json"}), 400
    pending = data.get('pending', [])
    if not pending:
        return jsonify({'scores': {}, 'still_pending': []})

    CHUNK_SIZE = 5
    scores = {}
    still_pending = []
    to_score = []

    # First pass: check if any pending items are now cached (skip >90 days)
    for opp in pending:
        sym = opp.get('symbol', '')
        opp_date = opp.get('date', '')
        days_out = int(opp.get('daysOut', 0))
        direction = opp.get('direction', '')
        if _ml_tier(days_out) is None:
            continue
        rkey = _ml_redis_key(sym, opp_date, days_out, direction)
        cached = redis_client.get(rkey)
        ui_key = f'{sym}|{days_out}|{direction}'

        if cached is not None:
            scores[ui_key] = json.loads(cached)
        else:
            to_score.append(opp)

    # Score a chunk via keyprovider, grouped by tier
    chunk = to_score[:CHUNK_SIZE]
    remainder = to_score[CHUNK_SIZE:]

    if chunk:
        # Group chunk items by tier
        by_tier = {}
        for o in chunk:
            tier = _ml_tier(o['daysOut'])
            by_tier.setdefault(tier, []).append(o)

        ttl = _ml_ttl_seconds()
        for tier, tier_opps in by_tier.items():
            try:
                scorer_opps = [
                    {'symbol': o['symbol'], 'date': o['date'], 'daysOut': o['daysOut'], 'direction': o['direction']}
                    for o in tier_opps
                ]
                resp = requests.post(
                    f'{config.ml_scorer_url}/score',
                    json={'opportunities': scorer_opps, 'tier': tier},
                    timeout=30
                )
                if resp.status_code == 200:
                    results = resp.json().get('results', [])
                    for r in results:
                        if 'error' in r or 'vix_blocked' in r:
                            continue
                        sym = r.get('symbol', '')
                        days_out = int(r.get('daysOut', 0))
                        direction = r.get('direction', '')
                        opp_date = r.get('date', '')
                        ui_key = f'{sym}|{days_out}|{direction}'
                        score_data = {
                            'ml_score': r.get('ml_score'),
                            'win_prob': r.get('win_prob'),
                            'pred_return': r.get('pred_return'),
                            'pred_mfe': r.get('pred_mfe'),
                        }
                        scores[ui_key] = score_data
                        rkey = _ml_redis_key(sym, opp_date, days_out, direction)
                        redis_client.set(rkey, json.dumps(score_data), ex=ttl)
                else:
                    remainder = tier_opps + remainder
            except Exception as e:
                logging.error(f'MLScorePending scorer error (tier {tier}): {e}')
                remainder = tier_opps + remainder

    still_pending = remainder
    return jsonify({'scores': scores, 'still_pending': still_pending})


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# send a year to custom filter with sy code, : odd, even, pe0 ... 3 , bear, bull
# returns true or false 11/2/2022
def custom_year_filter ( yy, sv_code,chart_start_date,opp_start_date): # year is int sv_code is string

        # this is to fix the december start of one of the PEs - only applicable when opp start less than 2 weeks from 
        # the beginning of the year forcing trend chart start date to be in december of the previous year 3/11/2025
        if chart_start_date!='' and opp_start_date!='' and int(chart_start_date[:4]) < int (opp_start_date[:4]):
            yy+=1

        #-11/1/2022--------custom years------------------------------------------------------------------
        filter_year   = True
        if   sv_code == 'odd' and yy % 2 == 0: filter_year = False # when y is even skip it
        elif sv_code == 'even'and yy % 2 != 0: filter_year = False # when y is odd skip it
        elif sv_code == 'pe0' and yy % 4 != 0: filter_year = False # presidential election years is divisible by 4
        elif sv_code == 'pe1' and yy % 4 != 1: filter_year = False # presidential election years +1 remainder is 1
        elif sv_code == 'pe2' and yy % 4 != 2: filter_year = False # presidential election years +2 divisible by 2
        elif sv_code == 'pe3' and yy % 4 != 3: filter_year = False # presidential election years +3 remainder is 3
        elif sv_code == 'bear': pass
        elif sv_code == 'bull': pass
        #-11/1/2022--------------------------------------------------------------------------------------
        return filter_year # return True when yy is in sv_code filter - return True when yy = 1980 and sv_code='even' 
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def get_earnings_dates(symbol):
    """Fetch earnings data from EDGAR service (HTTP) with Redis caching.
    Returns dict with 'earnings_dates', 'next_earnings_est', 'days_to_earnings' or empty dict."""
    if not config.edgar_service_url:
        return {}

    # Check Redis cache first (cache for 24 hours)
    redis_key = f'earnings_{symbol}'
    cached = redis_client.get(redis_key)
    if cached is not None:
        return json.loads(cached)

    # Fetch from EDGAR service
    try:
        url = f'{config.edgar_service_url}earnings/{symbol}'
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return {}
        data = resp.json()
    except Exception as e:
        logging.warning(f'EDGAR service error for {symbol}: {e}')
        return {}

    filings = data.get('filings', [])
    projected = data.get('projected_next')

    # All filings (newest first) for historical price chart overlay
    # earnings_filings includes form type: 8-K/E (announcement), 10-Q (quarterly), 10-K (annual)
    earnings_filings = [{'date': f['date'], 'form': f['form']} for f in filings]

    result = {'earnings_filings': earnings_filings}

    if projected and projected.get('date'):
        result['next_earnings_est'] = projected['date']
        try:
            proj_date = datetime.datetime.strptime(projected['date'], '%Y-%m-%d').date()
            days_to = (proj_date - datetime.date.today()).days
            result['days_to_earnings'] = days_to
        except ValueError:
            pass

    # Cache in Redis for 24 hours
    redis_client.set(redis_key, json.dumps(result))
    redis_client.expire(redis_key, 86400)

    return result

def get_realtime_prices_cached():
    """Get all real-time prices from the realtime service, cached in Redis for 55 min.
    Returns dict of {symbol: [price, change_p]} - compact format to minimize Redis payload.
    Full /prices/all response is ~3MB; we trim to only price+change_p (~400KB)."""
    if not getattr(config, 'realtime_service_url', ''):
        return {}

    redis_key = 'realtime_prices'
    cached = redis_client.get(redis_key)
    if cached is not None:
        return json.loads(cached)

    try:
        url = f'{config.realtime_service_url}prices/all'
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        prices = data.get('prices', {})
        # Trim to [price, change_p] arrays - reduces ~3MB to ~400KB
        trimmed = {}
        for sym, p in prices.items():
            trimmed[sym] = [p.get('price'), p.get('change_p')]
        redis_client.set(redis_key, json.dumps(trimmed))
        redis_client.expire(redis_key, 3300)  # 55 min - slightly less than the 60 min refresh interval
        return trimmed
    except Exception as e:
        logging.warning(f'Realtime price service error: {e}')
        return {}

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------
# This API returns the securiy name based on the resourceID and symbol
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/NameFromTicker/<string:resourceID>/<string:symbol>', methods=['GET']) # 7/26/2025
@check_for_token
def NameFromTicker(resourceID, symbol):
    exchange = config.exchange_mapping[resourceID]
    redis_key_name = f'security_name_{exchange}_{symbol}'

    name_redis = redis_client.get(redis_key_name)
    if name_redis is not None:
        name = json.loads(name_redis)
        return jsonify({'name': name})

    # Lookup name
    name = get_security_name_from_ticker(exchange, symbol)

    # Only cache if name is valid (not None, not empty)
    if name:
        redis_client.set(redis_key_name, json.dumps(name))
        # redis_client.expire(redis_key_name, config.chart_data_expire_time)

    # If name is None, return empty string (or whatever default you want)
    return jsonify({'name': name if name else ''})

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
#  chartData4 selects the direction of the date range by counting the losing years vs winning years.  if losing years are greater than winning years, it selects short
#  for the direction of the date range otehrwise if its equal or greater winning years than losing years it assigns long to the date range in stats returned except:
#######################
#  special condition:
#######################
#  the only time the date range selects long no matter number of winning and losing years is when its calculating buy and hold stats for the security
#  buy and hold is determined when the days out is 367 days for leap years and 366 days for other years - buy and hold date range is typically
#  01/01 to 01/01 of the next year  
#  12/10/2023 - added cut_off_year to trim the oldest years when needed - this fixes the issue with PE3 on SPX where 1931 is a huge down and then there is no more
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/ChartData4/<string:resourceID>/<string:date>/<string:symbol>/<string:daysOut>/<string:yrs>',                    methods=['GET'])
@app.route('/ChartData4/<string:resourceID>/<string:date>/<string:symbol>/<string:daysOut>/<string:yrs>/<int:cut_off_year>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_chartData4[0])
@limiter.limit(config.rate_limit_chartData4[1])
@limiter.limit(config.rate_limit_chartData4[2])
@limiter.limit(config.rate_limit_chartData4[3])
def getChartData4(resourceID, date, symbol, daysOut, yrs, cut_off_year=0):

    print('symbol, yrs =', symbol, yrs)

    # Validate date format (must be YYYY-MM-DD)
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({'ChartData4': [], 'stats': {}, 'error': 'invalid date format'}), 400

    todayDate = datetime.datetime.today().strftime('%Y-%m-%d')
    today_year = int(todayDate[:4])
    start_date_year = int(date[:4])

    # Handle case where start date is dragged to future year
    if start_date_year > today_year:
        date = f'{today_year}-{date[5:]}'

    currentYear = datetime.datetime.strptime(date, '%Y-%m-%d').year

    # January 1st edge case - force to January 2nd
    if date.endswith('-01-01'):
        year = date[:4]
        date = f'{year}-01-02'

    # ----------------------------------------------
    # Redis cache key
    # ----------------------------------------------
    redis_key_chartdata = f'chartdata_{resourceID}_{symbol}_{date}_{daysOut}_{yrs}_{cut_off_year}'

    # Activity logging
    token = request.args.get("token")
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key_chartdata)

    # Check cache before stockscore to avoid unnecessary HTTP request on cache hits
    chartdata_redis = redis_client.get(redis_key_chartdata)
    if chartdata_redis is not None:
        chartData = json.loads(chartdata_redis)
        return jsonify(chartData)

    lscore, sscore, lscore1, sscore1 = stockscore(resourceID, symbol, date)

    # ----------------------------------------------
    # Load symbol data
    # ----------------------------------------------
    exchange = config.exchange_mapping[resourceID]
    fn_csv = config.csv_folder + exchange + '/' + symbol + '.csv'

    result = get_symbol_csv(symbol, exchange)

    if isinstance(result, str) and 'Not Traded' in result:
        return jsonify({'ChartData4': [], 'stats': {}})
    else:
        df = result

    num_years_in_data = num_years_in_df(df)
    if num_years_in_data < config.min_required_years:
        return jsonify({'ChartData4': 'Not Enough Data', 'stats': {}})

    # ----------------------------------------------
    # Parse yrs parameter
    # Format options:
    #   "22"      -> 22 consecutive years
    #   "pe2:10"  -> 10 most recent pe2 years
    #   "pe2"     -> all pe2 years (legacy support)
    # ----------------------------------------------
    pe_filter = None
    max_filtered_years = None
    custom_years = False

    if yrs.isdigit():
        # Simple consecutive years
        years = int(yrs)
    elif '-' in yrs:
        # New format: pe#:## (e.g., pe2:10)
        custom_years = True
        parts = yrs.split('-')
        pe_filter = parts[0]                  # "pe0", "pe1", "pe2", or "pe3"
        max_filtered_years = int(parts[1])    # number of pe years desired
        
        # Set years to span entire dataset so we can find enough pe matches
        y1 = int(df.iloc[0]['date'][:4])
        y2 = int(df.iloc[-1]['date'][:4])
        years = y2 - y1
    else:
        # Legacy format: just "pe2" with no limit
        custom_years = True
        pe_filter = yrs
        max_filtered_years = None  # No limit - return all matching years
        
        y1 = int(df.iloc[0]['date'][:4])
        y2 = int(df.iloc[-1]['date'][:4])
        years = y2 - y1

    # ----------------------------------------------
    # Determine trade status (active/past)
    # ----------------------------------------------
    daysout = int(daysOut)
    dates_list = list(df['date'])
    last_date_in_csv = df.iloc[-1]['date']

    trade_active = False
    trade_past = False
    active_trade_begin_last_year = False

    if date < df.iloc[-1]['date']:
        d_end = inc_date_day(date, daysout)
        if last_date_in_csv >= d_end:
            trade_past = True
        else:
            trade_active = True
    else:
        # Check if last year's trade began but didn't end yet
        last_year = int(date[:4]) - 1
        last_year_start_date = str(last_year) + date[4:]
        last_year_end_date = inc_date_day(last_year_start_date, daysout)
        if last_year_end_date > last_date_in_csv:
            trade_active = True
            active_trade_begin_last_year = True

    endNum = 0  # Don't add this year's data by default
    if trade_past or (trade_active and active_trade_begin_last_year == False):
        endNum = -1  # Include current year in the loop

    # ----------------------------------------------
    # Main loop - collect trade data for each year
    # Collect ALL matching years first, then trim to most recent N
    # ----------------------------------------------
    chartData = []
    pctArray = []
    pctArray_low = []
    pctArray_high = []

    for y in range(years, endNum, -1):
        d_start_0 = inc_date_year(date, -y)
        year_int = int(d_start_0[:4])

        # Apply cut_off_year filter
        if cut_off_year != 0 and year_int < cut_off_year:
            continue

        # Apply custom PE filter (but don't limit count yet - we'll trim after)
        if custom_years:
            if not custom_year_filter(year_int, pe_filter, '', ''):
                continue

        # Calculate last trading day of the year (handle weekends)
        last_trading_date = d_start_0[:4] + '-12-31'
        day_of_week = datetime.datetime.strptime(last_trading_date, '%Y-%m-%d').weekday()
        if day_of_week == 5:
            last_trading_date = inc_date_day(last_trading_date, -1)
        elif day_of_week == 6:
            last_trading_date = inc_date_day(last_trading_date, -2)

        # Find actual start date (d0) in the data
        d0 = d_start_0
        while d0 not in dates_list:
            d0 = inc_date_day(d0, 1)

        # Calculate end date
        d_start_1 = inc_date_day(d_start_0, daysout)

        # Handle leap year alignment
        ytest = int(d_start_1[:4])
        if calendar.isleap(ytest):
            ldate = d_start_1[:4] + '-02-29'
            if ldate >= d_start_0 and ldate <= d_start_1:
                d_start_1 = inc_date_day(d_start_1, 1)

        # Find actual end date (d1) in the data
        if (trade_active and y == 0) or (active_trade_begin_last_year and y == 1):
            d1 = df.iloc[-1]['date']
        else:
            if d_start_1[5:] == '12-31':
                d1 = last_trading_date
                while d1 not in dates_list:
                    d1 = inc_date_day(d1, -1)
            else:
                d1 = d_start_1
                while d1 not in dates_list:
                    d1 = inc_date_day(d1, 1)

        # Get price data
        df0 = df[df['date'] == d0]
        df1 = df[df['date'] == d1]

        c0 = df0['close'].iloc[0]
        c1 = df1['close'].iloc[0]

        i0 = df0.index.tolist()[0]
        i1 = df1.index.tolist()[0]

        # Calculate MFE/MAE (high/low during trade)
        if i1 - i0 < 2:
            high = c0
            low = c0
        else:
            trade_slice = df[i0 + 1:i1 + 1]
            high = trade_slice['high'].max()
            low = trade_slice['low'].min()

        # Calculate percentages
        ph = round(100 * (high - c0) / c0, 2)
        pl = round(100 * (low - c0) / c0, 2)
        p = round(100 * (c1 - c0) / c0, 2)
        p_low = round(100 * (low - c0) / c0, 2)
        p_high = round(100 * (high - c0) / c0, 2)

        pctArray.append(p)
        pctArray_low.append(p_low)
        pctArray_high.append(p_high)

        yearDict = {
            'year': currentYear - y,
            'pct': str(p) + ',' + str(ph) + ',' + str(pl),
            'price': str(c0) + ',' + str(c1)
        }
        chartData.append(yearDict)

    # ----------------------------------------------
    # IMPORTANT: Trim to most recent N years for custom PE filters
    # The loop processes oldest to newest, so chartData is in chronological order
    # We want the LAST (most recent) max_filtered_years entries
    # ----------------------------------------------
    if custom_years and max_filtered_years is not None and len(chartData) > max_filtered_years:
        # Keep only the most recent N entries (last N in the list)
        chartData = chartData[-max_filtered_years:]
        pctArray = pctArray[-max_filtered_years:]
        pctArray_low = pctArray_low[-max_filtered_years:]
        pctArray_high = pctArray_high[-max_filtered_years:]

    # ----------------------------------------------
    # Add current year placeholder if applicable
    # ----------------------------------------------
    current_year_filter_valid = True
    if custom_years:
        current_year_filter_valid = custom_year_filter(currentYear, pe_filter, '', '')

    if current_year_filter_valid and len(chartData) > 0 and currentYear > chartData[-1]['year']:
        yearDict = {'year': currentYear, 'pct': '0,0,0', 'price': '0,0'}
        chartData.append(yearDict)

    # ----------------------------------------------
    # Calculate statistics
    # ----------------------------------------------
    if len(pctArray) == 0:
        return jsonify({'ChartData4': chartData, 'stats': {}})

    pos = sum(x >= 0 for x in pctArray)
    neg = sum(x < 0 for x in pctArray)
    longOrShort = 'long' if pos >= neg else 'short'

    # Buy & hold is always long (start date == end date, one year apart)
    if len(d_start_0) > 5 and len(d_start_1) > 5:
        if d_start_0[5:] == d_start_1[5:]:
            longOrShort = 'long'

    if longOrShort == 'short':
        # Swap pos/neg counts
        pos, neg = neg, pos
        
        pctArray_winners = [-1 * x for x in pctArray if x <= 0]
        pctArray_losers = [x for x in pctArray if x > 0]
        pctArray = [-1 * x for x in pctArray]

        avgProfit = statistics.mean(pctArray)
        avgProfitW = 0 if len(pctArray_winners) == 0 else round(statistics.mean(pctArray_winners), 2)
        avgLossL = 0 if len(pctArray_losers) == 0 else -1 * round(statistics.mean(pctArray_losers), 2)

        pctArray_low = [-1 * x for x in pctArray_low]
        avgProfit2 = statistics.mean(pctArray_low)
        profit_stdev2 = statistics.stdev(pctArray_low) if len(pctArray_low) > 1 else 0
    else:
        pctArray_winners = [x for x in pctArray if x >= 0]
        pctArray_losers = [x for x in pctArray if x < 0]
        
        avgProfit = statistics.mean(pctArray)
        avgProfitW = 0 if len(pctArray_winners) == 0 else statistics.mean(pctArray_winners)
        avgLossL = 0 if len(pctArray_losers) == 0 else statistics.mean(pctArray_losers)

        avgProfit2 = statistics.mean(pctArray_high)
        profit_stdev2 = statistics.stdev(pctArray_high) if len(pctArray_high) > 1 else 0

    # Cumulative return
    tmp = 1
    for i in range(len(pctArray)):
        tmp *= (1 + pctArray[i] / 100)
    cumulativeReturn = (tmp - 1) * 100

    # Annualized return
    annualizedReturn = round(((tmp ** (1 / len(pctArray))) - 1) * 100, 2)

    # Median and standard deviation
    medianProfit = statistics.median(pctArray)
    profit_stdev = statistics.stdev(pctArray) if len(pctArray) > 1 else 0

    # Sharpe ratios
    if profit_stdev > 0:
        sharpe_ratio = (avgProfit - config.free_return * (daysout / 365)) / profit_stdev
    else:
        sharpe_ratio = 0

    if profit_stdev2 > 0:
        sharpe_ratio2 = (avgProfit2 - config.free_return * (daysout / 365)) / profit_stdev2
    else:
        sharpe_ratio2 = 0

    formatted_cumulative_return = "{:,}".format(int(cumulativeReturn)) + '%'

    # Additional market data
    high_52w = (df['high'] * df['adj_factor']).tail(252).max()
    low_52w = (df['low'] * df['adj_factor']).tail(252).min()
    avg_volume_20d = df['volume'].tail(20).mean()
    return_1m = (df['close'] * df['adj_factor']).iloc[-1] / (df['close'] * df['adj_factor']).iloc[-21] - 1
    sma_50 = (df['close'] * df['adj_factor']).tail(50).mean()
    sma_200 = (df['close'] * df['adj_factor']).tail(200).mean()

    detailDict = {
        'Trade Dir': longOrShort,
        'Num Winners': str(pos),
        'Num Losers': str(neg),
        'Percent Profitable': str(round(100 * pos / len(pctArray))) + '%',
        'Avg Profit - All': str(round(avgProfit)) + '%',
        'Avg Profit': str(round(avgProfitW, 2)) + '%',
        'Avg Loss': str(round(avgLossL, 2)) + '%',
        'Median Profit': str(round(medianProfit, 2)) + '%',
        'Annualized Return': str(annualizedReturn) + '%',
        'Cumulative Return': formatted_cumulative_return,
        'Std Dev': str(round(profit_stdev, 2)) + '%',
        'Sharpe Ratio': str(round(sharpe_ratio, 2)),
        'Sharpe Ratio2': str(round(sharpe_ratio2, 2)),
        'Trend Long': lscore,
        'Trend Short': sscore,
        'Trend Long1': lscore1,
        'Trend Short1': sscore1,
        'last_trade_date': df['date'].iloc[-1],
        '52W High': high_52w,
        '52W Low': low_52w,
        'Avg Volume 20d': avg_volume_20d,
        '1M Return': str(round(return_1m * 100, 2)) + '%',
        'SMA 50': sma_50,
        'SMA 200': sma_200,
    }

    # Add earnings data if available (from EDGAR per-ticker JSON files)
    earnings = get_earnings_dates(symbol)
    if earnings:
        detailDict.update(earnings)

    combineDict = {'ChartData4': chartData, 'stats': detailDict}

    redis_client.set(redis_key_chartdata, json.dumps(combineDict))
    redis_client.expire(redis_key_chartdata, config.chart_data_expire_time)

    return jsonify({'ChartData4': chartData, 'stats': detailDict})

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------


# @app.route('/YearsMetaData/<string:resourceID>/<string:month>', methods=['GET'])
# @check_for_token
# @limiter.limit(config.rate_limit_YearsMetaData[0])
# @limiter.limit(config.rate_limit_YearsMetaData[1])
# @limiter.limit(config.rate_limit_YearsMetaData[2])
# @limiter.limit(config.rate_limit_YearsMetaData[3])
# def getYearsMetaData(resourceID, month):


#     redis_key_yearsMetaData = 'years_meta_data_'+resourceID+'_'+resourceID+'_'+month
#     redis_ylst = redis_client.get(redis_key_yearsMetaData)



#     if redis_ylst is None:
#         token = request.args.get("token")
#         resourceFolder = get_resource_folder_from_token(token, resourceID)

#         lst_dict = []
#         p = resourceFolder+'opportunities/Monthly_Opp_'+month+'*.*'
#         lst = glob.glob(p)

#         # get years and partial years from
#         ylst = [[x[3], x[4][:-3]] for x in (l.split('_') for l in lst)]

#         redis_client.set(redis_key_yearsMetaData, json.dumps(ylst))
#         redis_client.expire(redis_key_yearsMetaData,config.years_metadata_expire_time)
#     else:
#         ylst = json.loads(redis_ylst)

#     # --------------------------------------------------------------------
#     # send info for activity logging
#     # --------------------------------------------------------------------
#     token = request.args.get("token")
#     atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
#     ipv4 = get_remote_address()
#     update_activity_log(atime, resourceID, wp_userid, ipv4,country_code, zip, redis_key_yearsMetaData)

#     # print("jsonify({'YearsMetaData': ylst})=",jsonify({'YearsMetaData': ylst}))

#     return jsonify({'YearsMetaData': ylst})
    
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# version 2 take a specific date instead of a specific month
# it will open opp_meta.csv which hold the years metadata for that day
@app.route('/YearsMetaData2/<string:resourceID>/<string:year>/<string:month>/<string:day>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_YearsMetaData[0])
@limiter.limit(config.rate_limit_YearsMetaData[1])
@limiter.limit(config.rate_limit_YearsMetaData[2])
@limiter.limit(config.rate_limit_YearsMetaData[3])
def getYearsMetaData2(resourceID, year, month, day):

    # The React app fires this with resourceID='-1' (the uninitialized
    # sentinel) before the real market settles after a switch. '-1' would
    # negative-index into the resource list (→ last market = CC) and read
    # the wrong market's opp_meta — on dev that silently returned garbage;
    # on a partial-data env it 500s. Reject the sentinel like OppList4 does.
    if resourceID == '-1' or resourceID == -1:
        return jsonify({'YearsMetaData': [], 'YearsMetaDataPE': [], 'error': 'invalid_resource_id'})

    date = year + '-' + month + '-' + day
    date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%d')

    redis_key_yearsMetaData   = 'years_meta_data_' + resourceID + '_' + date
    redis_key_yearsMetaDataPE = 'years_meta_data_PE_' + resourceID + '_' + date

    redis_ylst   = redis_client.get(redis_key_yearsMetaData)
    redis_ylstPE = redis_client.get(redis_key_yearsMetaDataPE)

    token = request.args.get("token")
    resourceFolder = get_resource_folder_from_token(token, resourceID)
    metaFile   = resourceFolder + 'opportunities/meta/opp_meta.csv'
    metaFilePE = resourceFolder + 'opportunities/meta/opp_meta_PE.csv'

    # -----------------------
    # Base metadata (required)
    # -----------------------
    if redis_ylst is None:
        # A missing per-market opp_meta.csv means this market's precomputed
        # opportunity data isn't provisioned in THIS environment (e.g. the
        # US-only staging subset has no CC/ETF/etc. opp data). That must not
        # 500 the whole wave-viewer — return empty metadata (the React side
        # already renders this as "no data for current selection"). Logged at
        # WARNING so a genuine prod data-pipeline failure still surfaces
        # loudly in logs/Sentry rather than being silently swallowed.
        if not os.path.exists(metaFile):
            logging.warning("YearsMetaData2: opp_meta missing, returning empty: %s (resourceID=%s date=%s)", metaFile, resourceID, date)
            sylst = []
        else:
            df = pd.read_csv(metaFile)
            df = df[df['date'] == date]
            if df.empty:
                logging.warning("YearsMetaData2: no opp_meta row for date, returning empty: %s date=%s", metaFile, date)
                sylst = []
            else:
                ylst = eval(df['meta_col'].iloc[0])
                sylst = []
                for b in ylst:
                    sylst.append([str(b[0]), str(b[1])])

        redis_client.set(redis_key_yearsMetaData, json.dumps(sylst))
        redis_client.expire(redis_key_yearsMetaData, config.years_metadata_expire_time)
    else:
        sylst = json.loads(redis_ylst)

    # -----------------------
    # PE metadata (optional)
    # -----------------------
    if redis_ylstPE is None:
        sylstPE = []  # default if file missing / row missing / parse issues

        if os.path.exists(metaFilePE):
            try:
                dfE = pd.read_csv(metaFilePE)
                dfE = dfE[dfE['date'] == date]
                if not dfE.empty:
                    ylstPE = eval(dfE['meta_col'].iloc[0])

                    sylstPE = []
                    for b in ylstPE:
                        sylstPE.append([str(b[0]), str(b[1])])
            except Exception:
                # Optional file should never break endpoint
                sylstPE = []

        redis_client.set(redis_key_yearsMetaDataPE, json.dumps(sylstPE))
        redis_client.expire(redis_key_yearsMetaDataPE, config.years_metadata_expire_time)
    else:
        sylstPE = json.loads(redis_ylstPE)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key_yearsMetaData)

    return jsonify({
        'YearsMetaData': sylst,
        'YearsMetaDataPE': sylstPE
    })
# def getYearsMetaData2(resourceID, year, month, day):

#     date = year+'-'+month+'-'+day
    
#     # print('date is =',date)

#     # adds extra digits when needed
#     date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%d')

#     redis_key_yearsMetaData = 'years_meta_data_'+resourceID+'_'+date
#     redis_ylst = redis_client.get(redis_key_yearsMetaData)

#     if redis_ylst is None:
#         token = request.args.get("token")
#         resourceFolder = get_resource_folder_from_token(token, resourceID)
#         metaFile   = resourceFolder+'opportunities/meta/opp_meta.csv'
#         metaFilePE = resourceFolder+'opportunities/meta/opp_meta_PE.csv'

#         df  = pd.read_csv(metaFile)
#         df = df[df['date'] == date]

#         # dfE = pd.read_csv(metaFilePE)
#         # dfE = dfE[dfE['date'] == date]

#         # print('df second',df)
#         ylst = eval(df['meta_col'].iloc[0])

#         # convert ylst to strings instead of integers.  react app was made with strings

#         sylst = []
#         for b in ylst:
#             sylst.append([str(b[0]), str(b[1])])

#         redis_client.set(redis_key_yearsMetaData, json.dumps(sylst))
#         redis_client.expire(redis_key_yearsMetaData,
#                             config.years_metadata_expire_time)

#     else:
#         sylst = json.loads(redis_ylst)

#     # --------------------------------------------------------------------
#     # send info for activity logging
#     # --------------------------------------------------------------------
#     token = request.args.get("token")
#     atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
#     ipv4 = get_remote_address()
#     update_activity_log(atime, resourceID, wp_userid, ipv4,country_code, zip, redis_key_yearsMetaData)

#     # print("jsonify({'YearsMetaData': sylst})=",jsonify({'YearsMetaData': sylst}))

#     return jsonify({'YearsMetaData': sylst})
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------

# @app.route('/ChartHistorical/<string:resourceID>/<string:symbol>/<string:d0>/<string:d1>', methods=['GET'])
# @check_for_token
# @limiter.limit(config.rate_limit_ChartHistorical[0])
# @limiter.limit(config.rate_limit_ChartHistorical[1])
# @limiter.limit(config.rate_limit_ChartHistorical[2])
# @limiter.limit(config.rate_limit_ChartHistorical[3])
# def getHistory(resourceID, symbol, d0, d1):

#     redis_key_history = 'history_'+resourceID+'_'+symbol+'_'+d0+'_'+d1

#     token = request.args.get("token")
#     resourceFolder = get_resource_folder_from_token(token, resourceID)

#     fn_csv = ddir+'csv/'+symbol+".csv"
#     df = pd.read_csv(fn_csv)[['date', 'close', 'volume']]
#     dates_list = list(df['date'])
#     while d0 not in dates_list:
#         d0 = inc_date_day(d0, 1)

#     if d1 < df['date'].iloc[-1]:
#         while d1 not in dates_list:
#             d1 = inc_date_day(d1, 1)
#     else:
#         d1 = df['date'].iloc[-1]

#     i0 = dates_list.index(d0)
#     i1 = dates_list.index(d1)+1
#     history_json = df[i0:i1].to_dict('records')

#     # --------------------------------------------------------------------
#     # send info for activity logging
#     # --------------------------------------------------------------------
#     token = request.args.get("token")
#     atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
#     ipv4 = get_remote_address()
#     update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key_history)

#     return jsonify({'ChartHistorical': history_json})

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------

@app.route('/ChartHistorical2/<string:resourceID>/<string:symbol>/<string:d0>/<string:d1>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_ChartHistorical[0])
@limiter.limit(config.rate_limit_ChartHistorical[1])
@limiter.limit(config.rate_limit_ChartHistorical[2])
@limiter.limit(config.rate_limit_ChartHistorical[3])
# return as a list of lists - much smaller in size
def getHistory2(resourceID, symbol, d0, d1):

    # print(resourceID, symbol, d0, d1)

    redis_key_history = 'history_v2_'+resourceID+'_'+symbol+'_'+d0+'_'+d1
    redis_history = redis_client.get(redis_key_history)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    token = request.args.get("token")
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4,country_code, zip, redis_key_history)

    if redis_history is not None:
        return jsonify({'ChartHistorical2': json.loads(redis_history)})

    token = request.args.get("token")
    resourceFolder = get_resource_folder_from_token(token, resourceID)

    # fn_csv = resourceFolder+'csv/'+symbol+".csv"
    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500
    fn_csv = config.csv_folder+exchange+'/'+symbol+'.csv'

   
    # df = pd.read_csv(fn_csv)[['date', 'close', 'volume']]
    result = get_symbol_csv(symbol,exchange)  # new way to getting the csv 7/21/2025
    if isinstance(result, str) and 'Not Traded' in result:
        return jsonify({'ChartHistorical2': []}) # error typically about the symbol is not traded
    else:
        df = result

    if df.empty:
        return jsonify({'ChartHistorical2': []})

    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]

    # print(type(df['date'].iloc[10]),type(d0))

    df2 = df[(df['date'] >= d0) & (df['date'] <= d1)]

    history_json = df2.values.tolist()
    redis_client.set(redis_key_history, json.dumps(history_json))
    redis_client.expire(redis_key_history, config.history_expire_time)

    return jsonify({'ChartHistorical2': history_json})
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------

# return years range from the stock csv for seasonal bar chart pull down
@app.route('/StockMetaData/<string:resourceID>/<string:symbol>', methods=['GET'])
@check_for_token
def getStockMetaData(resourceID, symbol):

    redis_key_stockMetaData = 'stock_meta_data_'+resourceID+'_'+symbol
    # redis_key_max_num_days  = 'maxdays_'+resourceID  # 11/29/2021 adding this one a bad way because don't want a new api

    redis_stock_datelist = redis_client.get(redis_key_stockMetaData)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    token = request.args.get("token")
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4,country_code, zip, redis_key_stockMetaData)

    if redis_stock_datelist is not None:
        return jsonify({'StockMetaData': json.loads(redis_stock_datelist)})

    token = request.args.get("token")
    resourceFolder = get_resource_folder_from_token(token, resourceID)

    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500
    result = get_symbol_csv(symbol,exchange)  # new way to getting the csv 7/21/2025
    
    if isinstance(result, str) and 'Not Traded' in result:
        return jsonify({'StockMetaData': result}) # error typically about the symbol is not traded
    elif 'Not Found' in result or (isinstance(result, pd.DataFrame) and result.empty):
        return jsonify({'StockMetaData': 'Not Found'})  # no data or insufficient data in the pd
    else:
        df = result

    df2 = df.iloc[[0, -1]]  # dataframe with 1st and last row of df

    redis_client.set(redis_key_stockMetaData, json.dumps(list(df2['date'])))
    redis_client.expire(redis_key_stockMetaData,   config.stock_metadata_expire_time)

    return jsonify({'StockMetaData': list(df2['date'])})

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
# returns a list of allowed symbols used for validating seasonal viewer symbol field - loads after login once
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/GetListSymbols/<string:resourceID>', methods=['GET'])
@check_for_token
def getListSymbols(resourceID):  # for now not using resourceID, maybe later

    redis_key_list_symbols = 'list_symbols_'+resourceID
    redis_symbols = redis_client.get(redis_key_list_symbols)

    # print('redis_symbols=',redis_symbols)

    if redis_symbols is not None:
        tmp = json.loads(redis_symbols) # tmp is type dict 
        return jsonify({'AllowedSymbols': tmp})

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    token = request.args.get("token")
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key_list_symbols)

    token = request.args.get("token")
    resourceFolder = get_resource_folder_from_token(token, resourceID)

    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500 6/4/2022

    # check if there is a special symbols file like /home/flask/data/csv/symbols/symbols_US.txt - where US is the exchange
    # if it exist, load that file instead of going through the following creation of the list - 7/21/2025
    all_symbols_file_path = '/home/flask/data/csv/symbols/symbols_' + exchange + '.csv'

    
    if os.path.exists(all_symbols_file_path):
        df = pd.read_csv(all_symbols_file_path, dtype=str)
    else:
        df = pd.DataFrame(columns=['symbols','name'])

        for k in config.exchange_mapping:
            if config.exchange_mapping[k] == exchange:
                df = pd.concat([df,pd.read_csv(available_resources_path[k],dtype=str)])
        
        df         = df.drop_duplicates('symbols')
        df         = df[['symbols','name']]
        df.columns = ['symbol','name'] # dropped (s) from symbols - just didn't make sense

    ########################################
    ####### zip doesn't work in flask ######
    ########################################
    symbol_to_name_dict = {}
    for i,r in df.iterrows():
        symbol_to_name_dict[r['symbol']]=r['name']

    symbol_to_name_dict = {str(k): v for k, v in symbol_to_name_dict.items()}
    redis_client.set(redis_key_list_symbols, json.dumps(symbol_to_name_dict))
    redis_client.expire(redis_key_list_symbols, config.stock_metadata_expire_time)
    return jsonify({'AllowedSymbols': symbol_to_name_dict})

#--------------------------------------------------------------------------------------------------------------------
# return last date and price for the symbol
@app.route('/StockLastPrice/<string:resourceID>/<string:symbol>', methods=['GET'])
@check_for_token
def getStockLastPrice(resourceID, symbol):

    redis_key_stockLastPrice = 'stock_last_price_'+resourceID+'_'+symbol
    redis_stock_last_price   = redis_client.get(redis_key_stockLastPrice)


    if redis_stock_last_price is not None:
        return jsonify({'StockLastPrice': json.loads(redis_stock_last_price)})


    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500

    fn_csv = config.csv_folder+exchange+'/'+symbol+'.csv'
    # df = pd.read_csv(fn_csv)[['date', 'close', 'volume']]
    result = get_symbol_csv(symbol,exchange)  # new way to getting the csv 7/21/2025





    if isinstance(result, str) and 'Not Traded' in result:
            return jsonify({'StockLastPrice': [0,0]}) # return [0,0] list if this symbol is not traded.  error is captured in stockmetadata
    elif isinstance(result, pd.DataFrame) and result.empty:
        return jsonify({'StockMetaData': 'Not Found'})  # no data or insufficient data in the pd
    else:
        df = result


    df = df[['date', 'close']]
    
    lastDate = df['date'].iloc[-1]
    lastPrice = str(df['close'].iloc[-1])


    redis_client.set(redis_key_stockLastPrice, json.dumps([lastDate,lastPrice]))
    redis_client.expire(redis_key_stockLastPrice, config.stocklastprice_expire_time) 


    return jsonify({'StockLastPrice': [lastDate,lastPrice]})
#--------------------------------------------------------------------------------------------------------------------
# return last date and price for the symbol
@app.route('/getStockPriceByDate/<string:resourceID>/<string:symbol>/<string:date>', methods=['GET'])
@check_for_token
def getStockPriceByDate(resourceID, symbol,date):

    redis_key_stockPriceByDate = 'stock_price_by_date_'+resourceID+'_'+symbol+'_'+date
    redis_result   = redis_client.get(redis_key_stockPriceByDate)
    if redis_result is not None:
        # print('redis')
        return jsonify(json.loads(redis_result))


    # print('csv')

    exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500

    fn_csv = config.csv_folder+exchange+'/'+symbol+'.csv'
    # df = pd.read_csv(fn_csv)[['date', 'close', 'volume']]
    df = get_symbol_csv(symbol,exchange)  # new way to getting the csv 7/21/2025



    dates_list = list(df['date'])
    last_date = df['date'].iloc[-1]
    
    price = 0  # initial state of price

    # check if date is larger than the last_date
    d0 = date
    if date <= last_date:
        while d0 not in dates_list:
            d0 = inc_date_day(d0,1)

        trow = df[df['date']==d0]
        price = trow['close'].iloc[0]

    redis_client.set(redis_key_stockPriceByDate, json.dumps({'date':d0,'price': price}))
    redis_client.expire(redis_key_stockPriceByDate, config.stocklastprice_expire_time) 
    return jsonify({'date':d0,'price': price})
#---------------------------------------------------------------------------------------------------------------------------------
# get the consolidated seasonal chart version 2 added chart start date - this is now called the trend_chart
# sy is seasonal years: need to support custom seasonal_years: odd, even, pe0, pe1, pe2, pe3, bull, bear
# Format options:
#   "22"      -> 22 consecutive years
#   "pe2:10"  -> 10 most recent pe2 years
#   "pe2"     -> all pe2 years (legacy support)
@app.route('/consolidated_seasonal_chart2/<string:resourceID>/<string:symbol>/<string:sy>/<string:chart_start_date>/<string:opp_start_date>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def get_consolidated_seasonal_chart2(resourceID, symbol, sy, chart_start_date, opp_start_date):

    print('trend resourceID, symbol, sy, chart_start_date, opp_start_date =', resourceID, symbol, sy, chart_start_date, opp_start_date)

    # Validate date formats (must be YYYY-MM-DD)
    try:
        datetime.datetime.strptime(chart_start_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({'cons_seas_chart': [], 'error': 'invalid chart_start_date'}), 400

    # Construct a unique cache key
    redis_key_seasonal_chart = f'seasonal_chart_{resourceID}_{symbol}_{sy}_{chart_start_date}'
    logging.debug(f"Generated cache key: {redis_key_seasonal_chart}")

    # Log activity
    token = request.args.get("token")
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, resourceID, wp_userid, ipv4, country_code, zip, redis_key_seasonal_chart)

    # Try Redis cache first
    sc_redis = redis_client.get(redis_key_seasonal_chart)
    if sc_redis is None:
        # Try file cache
        cons_seas_chart = load_from_file_cache(redis_key_seasonal_chart)

        if cons_seas_chart:
            logging.debug(f"Retrieved cons_seas_chart from file cache for key {redis_key_seasonal_chart}")
            try:
                redis_client.set(redis_key_seasonal_chart, json.dumps(cons_seas_chart))
                redis_client.expire(redis_key_seasonal_chart, config.seasonal_chart_expire_time)
                logging.debug(f"Cached cons_seas_chart to Redis for key {redis_key_seasonal_chart}")
            except Exception as e:
                logging.error(f"Redis set failed for key {redis_key_seasonal_chart}: {e}")
            return jsonify({'cons_seas_chart': cons_seas_chart})

        # If not found in any cache, process the seasonal chart
        exchange = config.exchange_mapping[resourceID]
        fn_csv = config.csv_folder + exchange + '/' + symbol + '.csv'
        result = get_symbol_csv(symbol, exchange)

        if isinstance(result, str) and 'Not Traded' in result:
            return jsonify({'cons_seas_chart': []})
        else:
            df = result

        num_years_in_data = num_years_in_df(df)
        if num_years_in_data < config.min_required_years:
            return jsonify({'cons_seas_chart': []})

        df = df[['date', 'close']]

        # ----------------------------------------------
        # Parse sy parameter
        # Format options:
        #   "22"      -> 22 consecutive years
        #   "pe2:10"  -> 10 most recent pe2 years
        #   "pe2"     -> all pe2 years (legacy support)
        # ----------------------------------------------
        pe_filter = None
        max_filtered_years = None
        custom_years = False

        if sy.isdigit():
            # Simple consecutive years
            seasonal_years = int(sy)
        elif '-' in sy:
            # New format: pe#:## (e.g., pe2:10)
            custom_years = True
            parts = sy.split('-')
            pe_filter = parts[0]                  # "pe0", "pe1", "pe2", or "pe3"
            max_filtered_years = int(parts[1])    # number of pe years desired
            
            # Set seasonal_years to span entire dataset so we can find enough pe matches
            first_year = int(df['date'].iloc[0][:4])
            last_year = int(df['date'].iloc[-1][:4])
            seasonal_years = last_year - first_year
        else:
            # Legacy format: just "pe2" with no limit
            custom_years = True
            pe_filter = sy
            max_filtered_years = None  # No limit - return all matching years
            
            first_year = int(df['date'].iloc[0][:4])
            last_year = int(df['date'].iloc[-1][:4])
            seasonal_years = last_year - first_year

        # ----------------------------------------------
        # Original data processing logic - fill missing dates
        # ----------------------------------------------
        d1 = set(pd.date_range(df['date'].iloc[0], df['date'].iloc[-1], freq='d'))
        s1 = set([date_obj.strftime('%Y-%m-%d') for date_obj in d1])
        all_dates = list(s1)
        all_dates.sort()
        s2 = set(df['date'])
        l = list(s1 - s2)
        l.sort()  # l is the missing days from df
        mdate = ''
        date_dict = {}

        for d in l:
            mdate = d
            for j in range(1, 1000):
                ndate = inc_date_day(mdate, j)
                if ndate not in l:
                    date_dict[mdate] = ndate
                    break

        sub_dates_list = list(set(date_dict.values()))
        dfx = df.loc[df['date'].isin(sub_dates_list)]
        dfx = dfx.sort_values('date')
        dfi = dfx.set_index('date')
        missing_dates = []
        missing_close = []

        for k in date_dict.keys():
            missing_dates.append(k)
            missing_close.append(dfi.loc[date_dict[k]]['close'])

        dfm = pd.DataFrame()
        dfm['date'] = missing_dates
        dfm['close'] = missing_close
        df2 = pd.concat([df, dfm]).sort_values('date').reset_index(drop=True)

        #################################################################
        # df2 has all the missing days including weekend, holidays or anything missing.
        #################################################################

        df2['year'] = df2['date'].str[0:4]
        years = list(set(df2['year']))
        years.sort()
        current_year = datetime.datetime.now().year

        # Adjust seasonal_years if it exceeds available data
        first_available_year = int(df['date'].iloc[0][:4])
        y1 = current_year - seasonal_years

        if y1 < first_available_year:
            y1 = first_available_year
            seasonal_years = current_year - y1

        y2 = y1 + seasonal_years - 1

        todayDate = datetime.datetime.today().strftime('%Y-%m-%d')
        curYear = todayDate[:4]

        d1 = chart_start_date
        d2 = inc_date_day(d1, 364)

        if is_leap_in_date_range(d1, d2):
            d2 = inc_date_day(d2, 1)

        #################################################################
        # Create list of date ranges for each year slice
        # Process from most recent to oldest so we can limit pe years correctly
        #################################################################
        year_date_slice = []
        filtered_year_count = 0

        for i in range(1, seasonal_years + 1):
            y1 = int(curYear) - i
            
            # Apply custom PE filter if enabled
            if custom_years:
                if not custom_year_filter(y1, pe_filter, chart_start_date, opp_start_date):
                    continue
                
                # Check if we've collected enough pe years
                if max_filtered_years is not None and filtered_year_count >= max_filtered_years:
                    break
                
                filtered_year_count += 1

            dd1 = str(y1) + d1[4:]
            dd2 = inc_date_day(dd1, 364)

            if is_leap_in_date_range(dd1, dd2):
                dd2 = inc_date_day(dd2, 1)

            year_date_slice.append([dd1, dd2])

        # ----------------------------------------------
        # Build allr dictionary with filtered year slices
        # ----------------------------------------------
        allr = {}
        df2['group'] = 0

        for dd in year_date_slice:
            k = dd[0] + ':' + dd[1]
            l = df2.index[(df2['date'] >= dd[0]) & (df2['date'] <= dd[1])].tolist()
            allr[k] = l

        # Assign group number to dates of each date range
        for k in allr.keys():
            maxi = max(allr[k])
            mini = min(allr[k])
            df2.loc[mini:maxi, 'group'] = int(k[:4])

        df2 = df2[df2['group'] != 0]

        # Group by the date slices
        list_df_by_year = list(df2.groupby('group'))

        # Create dfc as the current year list of dates for the group slice
        dr = set(pd.date_range(d1, d2, freq='d'))
        s1 = list(set([date_obj.strftime('%Y-%m-%d') for date_obj in dr]))

        # Remove Feb 29 for ANY year
        s1 = [d for d in s1 if d[5:] != '02-29']
        s1.sort()
        dfc = pd.DataFrame(s1, columns=['date'])

        for g in list_df_by_year:
            dfy = g[1].copy()

            # Remove Feb 29 for ANY year so dfy always aligns with dfc
            dfy = dfy[dfy['date'].str[5:] != '02-29']

            if dfy.shape[0] == 365:
                minC = dfy['close'].min()
                maxC = dfy['close'].max()
                dfc['p' + str(g[0])] = list(100 * (dfy['close'] - minC) / (maxC - minC))

        dfc['mean'] = dfc.mean(axis=1, numeric_only=True)
        dfc = dfc.round(2)

        dfc = dfc.sort_values('date')
        dfc = dfc.reset_index(drop=True)
        dfc = dfc[['date', 'mean']].sort_values('date')
        cons_seas_chart = dfc.values.tolist()

        # Store the result in Redis and file cache
        try:
            redis_client.set(redis_key_seasonal_chart, json.dumps(cons_seas_chart))
            redis_client.expire(redis_key_seasonal_chart, config.seasonal_chart_expire_time)
            logging.debug(f"Cached cons_seas_chart to Redis for key {redis_key_seasonal_chart}")
        except Exception as e:
            logging.error(f"Redis set failed for key {redis_key_seasonal_chart}: {e}")

        save_to_file_cache(redis_key_seasonal_chart, cons_seas_chart)
        logging.debug(f"Cached cons_seas_chart to file cache for key {redis_key_seasonal_chart}")

    else:
        cons_seas_chart = json.loads(sc_redis)
        logging.debug(f"Retrieved cons_seas_chart from Redis for key {redis_key_seasonal_chart}")

    return jsonify({'cons_seas_chart': cons_seas_chart})
#---------------------------------------------------------------------------------------------------
# this is a supporting function for dr_report_publish to check for duplicates - return boolean
#---------------------------------------------------------------------------------------------------
def check_for_duplicates(redis_user_reports_list,newdict):
    
    duplicate = False
    dr_id = -1
    for d in redis_user_reports_list:

        if d['portfolioID'] != newdict['portfolioID']: continue

        if d['symbol'] == newdict['symbol'] and d['date']==newdict['date'] and d['days_hold'] == newdict['days_hold'] and d['years'] == newdict['years'] and d['portfolioID'] == newdict['portfolioID'] :
            duplicate = True
            dr_id = d["dr_id"]
            break
    
    # print(duplicate)
    return duplicate,dr_id
#------------------------------------------------------------------------------------------------
# generate blog title and slug
# created this for the appserver to assign blog right away - this is not accessible by appserver otherwise
# this function is duplicated in create_report.py on the blog wordpress server 3/12/2023
#------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------------------------
# this post title is after rebranding
#------------------------------------------------------------------------------------------------
def create_title_slug(company, symbol, date1, date2, years, category):
    if category == config.category_report:
        post_title = f"{years}-Year TradeWave Report {company} {symbol} {date1} to {date2}"
        post_slug = slugify(post_title)
        return post_title, post_slug

    if category == config.category_date_range_report:
        if isinstance(years, str) and years.startswith("pe") and len(years) > 2:
            pe_part = years[2:]  # "2" or "2-11"

            if "-" in pe_part:
                pe_offset, num_years = pe_part.split("-", 1)  # "2", "11"
                post_title = f"Pres Election +{pe_offset} ({num_years}-Year) TradeWave Report {company} {symbol} {date1} to {date2}"
                slug_title = f"Pres Election {pe_offset}-{num_years} Years TradeWave Report {company} {symbol} {date1} to {date2}"
            else:
                post_title = f"Pres Election +{pe_part} TradeWave Report {company} {symbol} {date1} to {date2}"
                slug_title = f"Pres Election {pe_part} Years TradeWave Report {company} {symbol} {date1} to {date2}"

            post_slug = slugify(slug_title)
            return post_title, post_slug

        post_title = f"{years}-Year Custom TradeWave Report {company} {symbol} {date1} to {date2}"
        post_slug = slugify(post_title)
        return post_title, post_slug

    print("error with categories - check category assignment")
    exit()

#------------------------------------------------------------------------------------------------    
def generate_blog_title_slug(financial_group_id,symbol,date1,days_hold,years,category):

     # --------- get company name ---------------------------
    symbols_csv = config.available_resources_path[str(financial_group_id)]
    dfs = pd.read_csv(symbols_csv)[['symbols','name']]
    df=dfs[dfs['symbols'] == symbol]

    days_hold_corrected = str(int(days_hold)-1) # fixes the issue with days = today+hold_days

    company = ''
    if df.shape[0] == 1: company = df['name'].iloc[0]
    #------------------------------------------------------
    
    date2    = inc_date_day(date1,int(days_hold_corrected))

    post_title,post_slug =  create_title_slug(company, symbol, date1, date2, years,category)


    return post_title,post_slug
#---------------------------------------------------------------------------------------------------
# find the portfolio id number from portfolio name passed
#---------------------------------------------------------------------------------------------------
def get_id_from_portfolio_name(userid,portfolio_name):

    redis_key_user_portfolio_names = f'user_portfolios_{userid}' # this is a json version of a list of dictionaries
    redis_user_portfolio_names_list = redis_client2.get(redis_key_user_portfolio_names)

    if redis_user_portfolio_names_list is not None: 
        user_portfolios = json.loads(redis_user_portfolio_names_list)
    else: 
        return 0

    # print('\n\n user protfolieo=',user_portfolios,'\n')

    id=0
    lst = [d['id'] for d in user_portfolios if d['name'] == portfolio_name]
    if len(lst) > 0: 
        id=lst[0]
    

    return id

#---------------------------------------------------------------------------------------------------
# publishes a report for the current user
# this is really add an opportunity to the portoflio
# BUG FIX: when user manually types a ticker that doesn't belong to the selected US stock group,
# the saved resourceID was wrong. This helper resolves to the correct (most specific) US group.
_us_stock_groups = [
    ('0', '/home/flask/data/dj30_symbols.csv'),
    ('1', '/home/flask/data/nasdaq100_symbols.csv'),
    ('2', '/home/flask/data/sp500_symbols.csv'),
    ('3', '/home/flask/data/rus1000_symbols.csv'),
    ('4', '/home/flask/data/wilshire5000_symbols.csv'),
]
_us_stock_sets = {}  # lazy cache: resource_id -> set of symbols

def _load_us_stock_set(resource_id, csv_path):
    if resource_id not in _us_stock_sets:
        try:
            import csv as _csv
            with open(csv_path, newline='', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                _us_stock_sets[resource_id] = {row['symbols'].strip().upper() for row in reader}
        except Exception:
            _us_stock_sets[resource_id] = set()
    return _us_stock_sets[resource_id]

def resolve_resource_id(symbol, resource_id):
    """If resource_id is a US stock group and symbol doesn't belong, find the correct group."""
    us_ids = {rid for rid, _ in _us_stock_groups}
    if resource_id not in us_ids:
        return resource_id  # non-US group - don't touch it
    sym = symbol.strip().upper()
    for rid, path in _us_stock_groups:
        if sym in _load_us_stock_set(rid, path):
            return rid  # return most specific group that contains the ticker
    return resource_id  # not found in any group - keep original
#---------------------------------------------------------------------------------------------------
@app.route('/dr_report_publish/<string:resourceID>/<string:symbol>/<string:date>/<string:days_hold>/<string:years>/<string:dir>/<string:sharpe_ratio>/<string:selected_portfolio>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def dr_report_publish(resourceID,symbol,date,days_hold,years,dir,sharpe_ratio,selected_portfolio):

    ############## need slug ############


    token = request.args.get("token")
    zero_last_year  = False
    category        = config.category_date_range_report
    base_year       = date[0:4]
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    user_level      = data['user_level'].replace(',','') # apparently there are , somehow
    # num_allowed     = config.num_opp_reports_allowed_by_level[user_level]

    

    #--------------------------------------------------------------------------------------------------------
    # check for daily limits for the user_level - important for free users specially
    #--------------------------------------------------------------------------------------------------------
    redis_key_daily_reports_generated = f'num_today_{userid}'
    num = redis_client2.get(redis_key_daily_reports_generated)
    
    dt = datetime.datetime.now()
    secs_to_midnight = ((24 - dt.hour - 1) * 60 * 60) + ((60 - dt.minute - 1) * 60) + (60 - dt.second)


    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()


    if num is None:
        redis_client2.set(redis_key_daily_reports_generated,1,ex=secs_to_midnight)
    else: 
        num = int(num)

        if num >= config.num_daily_opp_reports_allowed_by_level.get(user_level, 0):
            update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'DR report publish fail num={num} ')
            return jsonify({'publish_dr_report':'daily_limit_reached','limit':config.num_daily_opp_reports_allowed_by_level.get(user_level, 0)})
        else:
            num = num + 1
            redis_client2.set(redis_key_daily_reports_generated,num,ex=secs_to_midnight)


    # generate title and slug for this post - 
    title,slug=generate_blog_title_slug(resourceID,symbol,date,days_hold,years,config.category_date_range_report)


    #--------------------------------------------------------------------------------------------------------
    # add to queue for blog creation to the webserver which is running a flask service called bloq_queue.py
    #--------------------------------------------------------------------------------------------------------

    hostname = socket.gethostname()

    # url = f'{config.blog_queue_server}report/{resourceID}/{symbol}/{date}/{days_hold}/{years}/{base_year}/{zero_last_year}/{category}/{userid}/{user_level}/{title}/{slug}'
    # 12/21/2023 - some forex pairs have / in the title.  custom reports failed with 404 - found out from top10 generation that I place - and - for title and slug - it fixed it
    url = f'{config.blog_queue_server}report/{resourceID}/{symbol}/{date}/{days_hold}/{years}/{base_year}/{zero_last_year}/{category}/{userid}/{user_level}/-/-'

    
    
    if hostname != 'afshin-VirtualBox': # can't send to queue when on dev server
        try:
            response = requests.get(url, timeout=5)
            with open('add_to_blog_queue.log', 'a') as f: f.write(f'{response.status_code}-{response.reason}-url={url}\n')
        except Exception as e:
            # TW2: blog_queue_server is a TW1 component (WordPress side); failures must
            # not block the portfolio-add path that runs after this block.
            with open('add_to_blog_queue.log', 'a') as f: f.write(f'EXC-{e}-url={url}\n')

    # logcollection
    activity_txt = f'rID={resourceID} symbol={symbol} date={date} days_hold={days_hold} years={years} base_year={base_year} title={title}'
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'DR report publish num={num}  {activity_txt}')
   
    # get portfolio id from the portfolio name
    pid = get_id_from_portfolio_name(userid,selected_portfolio)

    num_shares = config.initial_shares

    if selected_portfolio[0] == '&':  # if its an autotrading portfolio, initial number of shares should be 1
        num_shares = 1

    resourceID = resolve_resource_id(symbol, resourceID)  # fix wrong group when ticker was manually typed

    date_range_report_dict = {

        'publishDate' : datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'), # date published is only set when its first created
        'resourceID'  : resourceID,
        'portfolioID' : pid,
        'symbol'      : symbol,
        'date'        : date,
        'days_hold'   : days_hold,
        'years'       : years,
        'slug'        : slug,      # this same slug should be generated by the blog wordpress processor in create_report.py 3/12/2023
        'direction'   : dir,
        'sharpe_ratio': sharpe_ratio,
        'num_shares'  : num_shares,
        'note'        : '',
        'sm_post'     : 'np',         # valuses are 'np':not posted    'del': posted and deleted  'pos':posted
        'status'      : '0'  # using this to allow user to checkbox to mark a opportunity in a portfolio for attention or followup  - initially its 0 or 1 but later 2, 3, 4, ...
    }

    
    #------------------------------------------------------------------
    # storing reports published user
    redis_key_user_reports = f'user_reports_{userid}'
    user_dict = {}
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)
        is_this_a_duplicate,d_id = check_for_duplicates(redis_user_reports_list,date_range_report_dict) # checks if this is a duplicate
        if is_this_a_duplicate:
            return jsonify({'publish_dr_report':'duplicate','duplicate':d_id})
        if len(redis_user_reports_list)>0:
            max_item = max(redis_user_reports_list, key=lambda x: x['dr_id'])
            dr_id = max_item['dr_id']+1
        else:
            dr_id=1
    else:
        redis_user_reports_list=[]
        dr_id = 0                  # this is the initial id number - it will keep incrementing

    date_range_report_dict['dr_id']=dr_id # add the id key to the dictionary with the new dr_id 

    redis_user_reports_list.append(date_range_report_dict) # add the properties of the new report to the list

    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    # ── Render the static HTML report on the WEB tier ──
    # The output lives at /var/www/tradewave/r/{slug}/ on the web box; on a
    # split web/app deployment the appserver can't write there, so it POSTs
    # to the web tier's /internal/render_report and the web tier renders
    # locally. On dev (single box) webserver_ip=localhost so this is just a
    # loopback HTTP call. Background thread keeps the user response instant.
    import threading
    def _render_background(report_dict, tok, t, s):
        try:
            web_host = config.webserver_ip or 'localhost'
            url = f'http://{web_host}:5500/internal/render_report'
            resp = requests.post(
                url,
                headers={'X-Service-Key': config.SERVICE_API_KEY},
                json={'report_dict': report_dict, 'token': tok, 'title': t, 'slug': s},
                timeout=5,
            )
            if resp.status_code != 200:
                with open('add_to_blog_queue.log', 'a') as f:
                    f.write(f'RENDER-HTTP-{resp.status_code}-{resp.text[:200]}-slug={s}\n')
        except Exception as e:
            with open('add_to_blog_queue.log', 'a') as f:
                f.write(f'RENDER-EXC-{e}-slug={s}\n')
    threading.Thread(
        target=_render_background,
        args=(date_range_report_dict, token, title, slug),
        daemon=True,
    ).start()

    # Return the URL even though render hasn't completed - the file will exist
    # by the time the user navigates to it.
    report_url = f"https://tw2.trxstat.com/r/{slug}/"

    # print(redis_user_reports_list)
    return jsonify({'publish_dr_report':'success', 'report_url': report_url})
#---------------------------------------------------------------------------------------------------   
# start writing an AI article for the newsroom by placing it on the writing queue
#---------------------------------------------------------------------------------------------------   
@app.route('/write_article_queue/<string:resourceID>/<string:symbol>/<string:date>/<string:days>/<string:years>/<string:direction>/<string:userid>/<string:publish_date>', methods=['POST'])
@check_for_token
def write_article_queue(resourceID, symbol, date, days, years, direction, userid, publish_date):

    token = request.args.get("token")
    data  = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid = data['user']



    url = f'{config.blog_queue_server}write_news_article/{resourceID}/{symbol}/{date}/{days}/{years}/{direction}/{userid}/{publish_date}'

    try:
        response = requests.get(url, timeout=10)

    except Exception:
        logging.exception("write_article_queue: blog_queue unreachable")
        return jsonify({
            "status": "failed",
            "reason": "blog_queue unreachable"
        }), 503

    # Must be valid JSON
    try:
        pdata = response.json()
    except Exception:
        return jsonify({
            "status": "failed",
            "reason": f"Invalid response from blog_queue: HTTP {response.status_code}"
        }), 502

    # Check message field
    if pdata.get("message") != "queued" and pdata.get("message") != "updated_existing":
        return jsonify({
            "status": "failed",
            "reason": pdata.get("reason", "blog_queue returned failure")
        }), 500

    # Success
    return jsonify({"status": "queued"})
#------------------------------------------------------------------------------------------------------------------   
# send all of opportunities in this folder without an article to the queue for AI article writing and publishing
#------------------------------------------------------------------------------------------------------------------   
#------------------------------------------------------------------------------------------------------------------   
# send all opportunities in this portfolio without an article AND not in the queue
# to the AI article queue for a given publish_date
#------------------------------------------------------------------------------------------------------------------   
@app.route('/article_folder_workflow/<int:portfolio_id>/<string:publish_date>', methods=['POST'])
@check_for_token
def article_folder_workflow(portfolio_id, publish_date):
    """
    Batch operation:
      For the given portfolio_id, look at all saved opportunities.
      For each one:
        - if it ALREADY has an article -> skip
        - if it is ALREADY queued       -> skip
        - else                          -> queue it for article generation on publish_date.
    """


    token = request.args.get("token")
    data   = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid = data['user']

    # ------------------------------------------------------------------
    # 1) Get the list of reports for this portfolio, with article flags
    #    IMPORTANT: call the *function* dr_report_list, not via HTTP.
    # ------------------------------------------------------------------
    # articleToggle = 1 => dr_report_list populates:
    #   o['article_exists'], o['article_queued'], o['article_publish_date'], etc.
    resp = dr_report_list(portfolio_id, articleToggle=1)


    # dr_report_list is a Flask view, so resp is a Response object.
    # If it isn't 200, blow up so we SEE it.
    if resp.status_code != 200:
        raise RuntimeError(f"dr_report_list failed: HTTP {resp.status_code}, body={resp.get_data(as_text=True)[:300]}")

    payload = resp.get_json()
    if payload is None:
        raise RuntimeError("dr_report_list returned no JSON")

    reports_list = payload.get("reports_list")
    if reports_list is None:
        raise RuntimeError("dr_report_list JSON missing 'reports_list'")

    # ------------------------------------------------------------------
    # 2) Walk the opportunities, queue the ones that are white
    # ------------------------------------------------------------------
    queued_count       = 0
    skipped_has_article = 0
    skipped_is_queued   = 0

    for o in reports_list:
        # defensive sanity checks – if these are missing, you WANT a crash
        rID   = o['resourceID']
        sym   = o['symbol']
        sdate = o['date']
        days  = o['days_hold']
        years = o['years']

        # If article already exists: skip (blue)
        if o.get('article_exists'):
            skipped_has_article += 1
            continue

        # If already queued: skip (orange)
        if o.get('article_queued'):
            skipped_is_queued += 1
            continue

        # White row: no article, not queued => queue it
        queue_url = (
            f"{config.blog_queue_server}"
            f"write_news_article/{rID}/{sym}/{sdate}/{days}/{years}/{userid}/{publish_date}"
        )

        print(f"[article_folder_workflow] QUEUE -> {queue_url}")

        # Let errors from requests bubble if things are really broken
        resp2 = requests.get(queue_url, timeout=10)

        # Log full response for debugging
        text_preview = resp2.text[:300]
        print(f"[article_folder_workflow] RESP {resp2.status_code}: {text_preview}")

        # Hard fail on non-200
        if resp2.status_code != 200:
            raise RuntimeError(
                f"blog_queue write_news_article failed "
                f"for {sym} {sdate} {days} {years}: HTTP {resp2.status_code} body={text_preview}"
            )

        pdata = resp2.json()
        # You said you were fine with always returning "queued" from blog_queue.
        # If you still have 'queued_new' or 'updated_existing', normalize them there.
        msg = pdata.get("message")
        if msg not in ("queued", "queued_new", "updated_existing"):
            raise RuntimeError(
                f"blog_queue returned unexpected message '{msg}' "
                f"for {sym} {sdate} {days} {years}: {pdata}"
            )

        queued_count += 1

    # ------------------------------------------------------------------
    # 3) Happy path – explicit counts so you can see in React / console
    # ------------------------------------------------------------------
    return jsonify({
        "status": "queued",
        "queued": queued_count,
        "skipped_existing": skipped_has_article,
        "skipped_queued": skipped_is_queued,
        "total": len(reports_list),
    })
#-----------------------------------------------------------------------------------------------------------
# create an Article prompt for the passed opportunity
# to create an article, it has to post an action to blog_queue.py service on web server 
# this is called from portfolio manager - icons to initiate publishing an article is only available to AM
#-----------------------------------------------------------------------------------------------------------
@app.route('/article_prompt/<string:resourceID>/<string:symbol>/<string:date>/<string:days_hold>/<string:years>/<string:userid>/<string:mode>/<string:note>', methods=['GET'])
@check_for_token
def article_prompt(resourceID, symbol, date, days_hold, years, userid, mode, note):
    """
    MODE SEMANTICS:
      - mode = "0": Synchronous article prompt generation (used by UI to preview prompt).
      - mode = "1": DEPRECATED.
                    Originally: Perplexity/Tavily research + prompt returned synchronously.
                    Now: still routed through blog_queue like mode 0, but should be phased out.
      - mode = "2": FULL ASYNC ARTICLE GENERATION.
                    Does NOT expect article_html back synchronously.
                    Instead, it delegates to start_article_workflow, which enqueues a
                    background job via blog_queue/article_processor.
    """

    # SEC-H3 - IDOR fix - derive userid from JWT, not URL. Mirrors the
    # article_publish/article_delete pattern. Admins may keep the URL value
    # so they can run prompt/load on another user's article-in-progress.
    token = request.args.get("token")
    data_jwt = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    jwt_userid = str(data_jwt['user'])
    if data_jwt.get('is_admin', False):
        userid = str(userid)
    else:
        if str(userid) != jwt_userid:
            logging.warning(
                "article_prompt: URL userid override user=%s url_userid=%s ip=%s ua=%s",
                jwt_userid, userid,
                request.headers.get("X-Forwarded-For", request.remote_addr),
                request.headers.get("User-Agent", "-"),
            )
        userid = jwt_userid

    # -------------------------
    # MODE 2 → async workflow
    # -------------------------
    if mode == "2":
        # Use the seasonal pattern start date as publish_date for now.
        # This calls the *internal* start_article_workflow function, which in turn
        # talks to blog_queue and pushes the job onto news_article_queue.
        return start_article_workflow(resourceID, symbol, date, days_hold, years, userid, date)

    # -------------------------
    # MODES 0, 1, and "hero" → existing synchronous blog_queue behavior
    # -------------------------
    # TW2: encode user-controlled `note` to prevent SSRF/path injection.
    safe_note = _urlquote(str(note), safe='')
    url = f'{config.blog_queue_server}article_prompt/{resourceID}/{symbol}/{date}/{days_hold}/{years}/{userid}/{mode}/{safe_note}'
    print('\n\n\n url=', url, '\n\n\n\n')

    try:
        response = requests.get(url, timeout=30)
    except Exception:
        logging.exception("article_prompt: blog_queue unreachable")
        return jsonify({"message": "failed", "reason": "upstream unreachable"}), 502
    try:
        pdata = response.json()
    except Exception:
        logging.exception("article_prompt: invalid JSON from blog_queue")
        return jsonify({"message": "failed", "reason": "upstream returned invalid response"}), 502

    # HERO MODE: just return status message
    if mode == "hero":
        return jsonify({
            "message": pdata.get("message", "failed"),
            "reason": pdata.get("reason", "")
        })

    # If blog_queue failed, bubble it up
    if pdata.get("message") == "failed":
        return jsonify({
            "message": "failed",
            "reason": pdata.get("reason", "article_prompt failed in blog_queue")
        }), 500

    # --------------- MODES 0 & 1: article_prompt ---------------
    # Mode 1 is deprecated but still allowed to behave like mode 0 here.
    prompt = pdata.get("prompt")
    if not prompt:
        return jsonify({
            "message": "failed",
            "reason": "Expected article_prompt from blog_queue but none returned"
        }), 500

    return jsonify({
        "message": "success",
        "article_prompt": prompt
    })
    



#-----------------------------------------------------------------------------------------------------------
# publishes an Article for the passed opportunity
# to create an article, it has to post an action to blog_queue.py service on web server 
# this is called from portfolio manager - icons to initiate publishing an article is only available to AM
# has to be posted because of size of the html article 
#-----------------------------------------------------------------------------------------------------------
@app.route('/article_publish/<string:resourceID>/<string:symbol>/<string:date>/<string:days_hold>/<string:years>/<string:direction>/<string:userid>', methods=['POST'])
@check_for_token
def article_publish(resourceID, symbol, date, days_hold, years, direction, userid):
    # TW2: IDOR fix - derive userid from JWT, not URL. Admins may publish for
    # another user; that path is gated on is_admin.
    token = request.args.get("token")
    data_jwt = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    jwt_userid = str(data_jwt['user'])
    if data_jwt.get('is_admin', False):
        # admins may publish for another user - keep the URL value as-is
        userid = str(userid)
    else:
        userid = jwt_userid

    article_html = request.get_data(as_text=True)

    # print('article_html=',article_html,'\n\n\n\n\n')

    url = f"{config.blog_queue_server}article_publish_bq"
    payload = {
        "resource_id": resourceID,
        "symbol": symbol,
        "date": date,
        "days": days_hold,
        "years": years,
        "direction":direction,
        "userid": userid,
        "article_html": article_html,
    }

    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except Exception:
        logging.exception("article_publish: blog_queue unreachable")
        return jsonify({"publish_article": "upstream unreachable"}), 502

    try:
        data = resp.json()
    except Exception:
        logging.exception("article_publish: blog_queue returned non-JSON")
        return jsonify({"publish_article": "invalid upstream response"}), 502

    return jsonify({
        "post_id":     data.get("post_id"),
        "status_code": data.get("status_code"),
        "slug":        data.get("slug"),
        "publish_article": data.get("reason"),
    })
#---------------------------------------------------------------------------------------------------
@app.route('/article_delete/<string:resourceID>/<string:symbol>/<string:date>/<string:days>/<string:years>/<string:userid>', methods=['POST'])
@check_for_token
def article_delete(resourceID, symbol, date, days, years, userid):
    """
    Proxy delete request to blog_queue.

    All real logic (queue removal + HTML article delete) is handled
    in blog_queue.delete_article_bq.
    """

    token = request.args.get("token")
    data  = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid = data['user']   # override any URL userid with JWT userid

    payload = {
        "resource_id": resourceID,
        "symbol": symbol,
        "date": date,
        "days": days,
        "years": years,
        "userid": userid,
    }

    url = f"{config.blog_queue_server}delete_article_bq"

    try:
        resp = requests.post(url, json=payload, timeout=20)
    except Exception:
        # blog_queue unreachable
        logging.exception("article_delete: blog_queue unreachable")
        return jsonify({
            "status": "failed",
            "reason": "blog_queue unreachable"
        }), 503

    # Pass through blog_queue's response as-is (but with a sane error if it's not JSON)
    try:
        pdata = resp.json()
    except Exception:
        return jsonify({
            "status": "failed",
            "reason": f"Invalid response from blog_queue: HTTP {resp.status_code}"
        }), 502

    # No extra smart logic here: blog_queue owns semantics ("deleted_from_queue", "deleted_article", etc.)
    return jsonify(pdata), resp.status_code
#---------------------------------------------------------------------------------------------------
@app.route('/article_load/<string:resourceID>/<string:symbol>/<string:date>/<string:days>/<string:years>/<string:userid>', methods=['GET'])
@check_for_token
def article_load(resourceID, symbol, date, days, years, userid):

    # SEC-H3 - IDOR fix - derive userid from JWT, not URL. Mirrors the
    # article_publish/article_delete pattern. Admins may keep the URL
    # value so they can load another user's article-in-progress.
    token = request.args.get("token")
    data_jwt = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    jwt_userid = str(data_jwt['user'])
    if data_jwt.get('is_admin', False):
        userid = str(userid)
    else:
        if str(userid) != jwt_userid:
            logging.warning(
                "article_load: URL userid override user=%s url_userid=%s ip=%s ua=%s",
                jwt_userid, userid,
                request.headers.get("X-Forwarded-For", request.remote_addr),
                request.headers.get("User-Agent", "-"),
            )
        userid = jwt_userid

    # Build correct URL to blog_queue (webserver)
    # NOTE: your route on webserver is /article_load_bq/<params...>
    url = (
        f"{config.blog_queue_server}"
        f"article_load_bq/{resourceID}/{symbol}/{date}/{days}/{years}/{userid}"
    )

    print(f"\n\n[APPSERVER] article_load -> calling: {url}\n")

    # Call webserver
    try:
        response = requests.get(url, timeout=30)
    except Exception:
        logging.exception("article_load: blog_queue unreachable")
        return jsonify({
            "found": False,
            "reason": "blog_queue unreachable",
        }), 502

    # Decode webserver response
    try:
        pdata = response.json()
    except Exception:
        logging.exception("article_load: invalid JSON from blog_queue")
        return jsonify({
            "found": False,
            "reason": "invalid JSON returned by blog_queue",
        }), 500

    # Forward status from webserver
    # If the content-service returned 404, propagate it
    status_code = response.status_code

    # Add trace to log
    # print(f"[APPSERVER] article_load result ({status_code}): {pdata}")

    # Return same structure to UI
    return jsonify(pdata), status_code
#---------------------------------------------------------------------------------------------------
@app.route('/get_news_home_url/', methods=['GET'])
@check_for_token
def get_news_home_url():
    """
    UI → appserver → blog_queue (webserver)
    Returns: { "news_home": "<full URL to the news home>" }
    """

    try:
        # Call blog queue
        url = f"{config.blog_queue_server}get_news_home_url/"
        resp = requests.get(url, timeout=10)

        if not resp.ok:
            return jsonify({
                "ok": False,
                "error": f"blog_queue returned {resp.status_code}"
            }), 500

        data = resp.json()

        print('data=',data)

        return jsonify({
            "ok": True,
            "news_home_url": data.get("news_home_url")
        })

    except Exception:
        logging.exception("get_news_home_url: failure")
        return jsonify({
            "ok": False,
            "error": "internal error"
        }), 500



#---------------------------------------------------------------------------------------------------
# get security price by day - save it in redis - used by dr_report_list
# seconds_expire is the number of seconds between now and 6:30PM tomorrow
#---------------------------------------------------------------------------------------------------
def get_security_price(resourceID,symbol,date): # need today_date to calculate expiration for tomorrow at 6PM

    redis_key_security_price_by_date = 'spbd_'+resourceID+'_'+symbol+'_'+date
    price = redis_client.get(redis_key_security_price_by_date)
    return_date = date # this is returned as the date of the price

    if price is None:
    
        token = request.args.get("token")
        resourceFolder = get_resource_folder_from_token(token, resourceID)

        exchange = config.exchange_mapping[resourceID] # should return US for nasdaq or sp500
        fn_csv = config.csv_folder+exchange+'/'+symbol+'.csv'

        # df = pd.read_csv(fn_csv) # load the csv data
        df = get_symbol_csv(symbol,exchange)  # new way to getting the csv 7/21/2025

        # handle case where get_symbol_csv returns a string error instead of DataFrame
        if not isinstance(df, pd.DataFrame) or df.shape[0] == 0:
            return 0, date

        d0 = date
        dates_list = list(df['date'])

        last_date_in_csv  = df['date' ].iloc[-1]
        last_price_in_csv = df['close'].iloc[-1]

        if date > last_date_in_csv:
            return_date = last_date_in_csv
            price       = last_price_in_csv
            seconds_expire = config.spdd_active_expire_time # this is expire seconds when the end date is active - 
        else:
            seconds_expire = config.spbd_static_expire_time # this is expire seconds when the row is found and has a price vs active 
            while d0 not in dates_list:
                d0 = inc_date_day(d0, 1)

            df = df[df['date']==d0]
            if df.shape[0] > 1: return 0,'multiple'  # returned mutliple rows - should not happen
            price = df['close'].iloc[0]

        redis_client.set(redis_key_security_price_by_date, json.dumps(price))
        redis_client.expire(redis_key_security_price_by_date, seconds_expire) 

    return float(price),return_date  # return date is the date that the price was pickedup at in the csv
#---------------------------------------------------------------------------------------------------
# Add this helper function at the top of your file or in a utilities module
# returns both queue status and publish date
def check_article_queue_publish_date(resource_id, symbol, date, days, years):
    """
    Check if an article matching the given parameters exists in the Redis queue.
    Returns True if found, False otherwise.
    """
    try:
        # Get all items from the queue (LRANGE 0 -1 gets all items)
        queue_items = redis_client3.lrange(config.NEWS_QUEUE_NAME, 0, -1)
        
        if not queue_items:
            return False, None
        
        # Search through queue items for a match
        for item in queue_items:
            try:
                entry = json.loads(item)

                # Match on key fields: resource_id, symbol, date, days, years
                if (entry.get('resource_id') == str(resource_id) and
                    entry.get('symbol', '').upper() == symbol.upper() and
                    entry.get('date') == date and
                    entry.get('days') == str(days) and
                    entry.get('years') == str(years)):
                    article_publish_date = entry.get('article_publish_date')

                    # print('ppppppppppppppppp',article_publish_date)
                    return True, article_publish_date
                    
            except json.JSONDecodeError:
                continue  # Skip malformed entries
                
        return False, None
        
    except Exception as e:
        print(f"Error checking article queue: {e}")
        return False, None
#---------------------------------------------------------------------------------------------------
# returns a list of reports this user has published
# using redis as a database - redis_client2
# its now portfolio enteries but old names are still in effect
# article toggle is for news articles and only toggled on by authorized people 
# when toggle is on, then this route will check if news articles exists for each saved pattern and return it
#---------------------------------------------------------------------------------------------------    
@app.route('/dr_report_list/<int:portfolio_id>/<int:articleToggle>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def dr_report_list(portfolio_id,articleToggle): # get the list of reports from redis and returns a list of dictionaries
    
    token           = request.args.get("token")
    today_date      = datetime.datetime.now().strftime("%Y-%m-%d")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)


    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'dr_report_list redis_key={redis_key_user_reports}')
    

    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)
        # print(redis_user_reports_list)
    else:
        redis_user_reports_list=[]

    # first filter the opp list by the portfolio id passed:
    reports_list_by_portfolio = [d for d in redis_user_reports_list if d.get("portfolioID") == portfolio_id]

    # print(reports_list_by_portfolio)
    
    # 

    for o in reports_list_by_portfolio:
        rID   = o['resourceID']
        sym   = o['symbol']
        sdate = o['date']
        days  = o['days_hold']
        # Check if Redis article exists
        if articleToggle == 1:
            tone = "neutral"
            website_id = 0
            years = o['years']
            redis_key = f"{rID}_{sym.upper()}_{sdate}_{days}_{years}_{tone}_{website_id}"
            exists = redis_client3.exists(redis_key)
            o['article_exists'] = True if exists == 1 else False
            # Check if article is queued for future publication
            o['article_queued'], o['article_publish_date'] = check_article_queue_publish_date(rID, sym, sdate, days, years)
        else:
            o['article_exists'] = False
            o['article_queued'] = False
            o['article_publish_date'] = None

        edate = inc_date_day(sdate, int(days))   

        # for some reason - have to check again after Jan 8 again 12/30/2024
        edate = inc_date_day(edate, -1)       

        # print('*************************************************',rID,sym,sdate,edate)

        price1,rdate1=get_security_price(rID,sym,sdate)
        price2,rdate2=get_security_price(rID,sym,edate)

        # if symbol is not traded, get_seucirty_price returns 0

        if price1 == 0 or price2 == 0:
            o['price1'] = 0
            o['gain_loss'] = 0
        else:
            gain_loss = 100 * (price2-price1)/price1
            o['price1'] = price1
            o['gain_loss'] = gain_loss

        # -----------------  ARTICLE LOOKUP ADDED CONDITIONALLY -----------------
        if articleToggle == 1:
            # be tolerant on how years is stored in the portfolio row
            years = o.get("lookback_years") or o.get("years") 
            # default: no article
            o["has_article"] = False

            if years:
                redis_key_article = f"{rID}_{sym.upper()}_{sdate}_{days}_{years}_neutral_0"
                try:
                    # print(redis_key_article)
                    raw = redis_client3.get(redis_key_article)
                except Exception as e:
                    # don't let Redis issues break this route
                    print("article redis error:", e)
                    raw = None

                if raw:
                    try:
                        article_payload = json.loads(raw)
                        entry = article_payload.get("entry", {})
                        o["has_article"]       = True
                        o["article_title"]     = entry.get("title")
                        o["article_url"]       = entry.get("url")
                        o["article_dek"]       = entry.get("dek")
                        o["article_published"] = entry.get("published_date")
                        o["article_tone"]      = article_payload.get("tone")
                        o["article_website_id"] = article_payload.get("website_id")
                    except Exception as e:
                        print("article json decode error:", e)


    return jsonify({'reports_list':reports_list_by_portfolio})
#---------------------------------------------------------------------------------------------------
# using dr_id as the primary key to update the num_shares of the opportunity in the list 
@app.route('/update_number_of_shares/<string:num_shares>/<int:portfolioID>/<string:dr_id>', methods=['POST'])
@check_for_token
def update_number_of_shares(num_shares,portfolioID,dr_id): # use slug as an identifier for which saved report to update

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'Update_num_shares portfolioID={portfolioID} dr_id={dr_id} num={num_shares}')
    

    if redis_user_reports_list is None:
        return jsonify({'update_number_of_shares':'none'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)
    # get the list index with the slug=slug
    # use the list index to update num_shares and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id) and redis_user_reports_list[i]["portfolioID"] == portfolioID]
    i=-1
    if len(idx)==1:i=idx[0]
    # now we have the index of the opportunity to update
    redis_user_reports_list[i]['num_shares']=num_shares
    # set the opp list to the new listed after updating the num_shares
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    return jsonify({'update_number_of_shares':'success'})
#---------------------------------------------------------------------------------------------------
# update status of the opportunity - default is 0 - no status - 1 would be stat1 - could also be other numbers
# this implements colored marking for user to mark an opportunity for reminder or any reason
# using dr_id as the primary key to update the status of the opportunity in the list 
#---------------------------------------------------------------------------------------------------
@app.route('/update_status/<string:status>/<int:portfolioID>/<string:dr_id>', methods=['POST'])
@check_for_token
def update_status(status,portfolioID,dr_id): # use slug as an identifier for which saved report to update
    
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'Update_status portfolioID={portfolioID} dr_id={dr_id} status={status}')


    if redis_user_reports_list is None:
        return jsonify({'update_status':'none'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)

    # for item in redis_user_reports_list:
    #     print(type(item['dr_id']) )


    # get the list index with the slug=slug
    # use the list index to update status and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id) and redis_user_reports_list[i]["portfolioID"] == portfolioID]

    i=-1
    if len(idx)==1:i=idx[0]

    # now we have the index of the opportunity to update
    redis_user_reports_list[i]['status']=status
    # set the opp list to the new listed after updating the num_shares
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    return jsonify({'update_status':'success'})

#---------------------------------------------------------------------------------------------------    
# removes a report from the user's list of reports in redisk
# when dr_id = -1 remove all
# need to also put a delete on the queue on the webserver to remove the report
#---------------------------------------------------------------------------------------------------
@app.route('/dr_report_remove/<string:dr_id>', methods=['POST'])
@check_for_token
def dr_report_remove(dr_id): # get the list of reports from redis and returns a list of dictionaries

    token = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    num_removed     = 0

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'dr_report_remove dr_id={dr_id}')
  

    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)
        if dr_id == '-1': # remove all
            num_removed = len(redis_user_reports_list)
            redis_user_reports_list=[]
        else:

            rec_to_del = [d for d in redis_user_reports_list if d['dr_id'] == int(dr_id)]
            # print('rec_to_del=',rec_to_del[0])
            slug = rec_to_del[0]["slug"]
            # if there is a social media post for this record delete it here
            if rec_to_del[0]["sm_post"] == "pos":
                try:
                    opp_del_social_media(slug)
                except Exception as e:
                    logging.exception("opp_del_social_media failed slug=%s", slug)
            # Vestigial TW1 blog_queue ping — must not block the user delete.
            hostname = socket.gethostname()
            if hostname != 'afshin-VirtualBox' and config.blog_queue_server:
                try:
                    requests.get(f'{config.blog_queue_server}delreport/{userid}/{slug}', timeout=5)
                except Exception as e:
                    with open('add_to_blog_queue.log', 'a') as f:
                        f.write(f'DELREPORT-QUEUE-EXC-{e}-slug={slug}\n')
            # Remove the static HTML on the web tier (where /var/www/tradewave/r/ lives).
            try:
                web_host = config.webserver_ip or 'localhost'
                requests.post(
                    f'http://{web_host}:5500/internal/delete_report',
                    headers={'X-Service-Key': config.SERVICE_API_KEY},
                    json={'slug': slug},
                    timeout=5,
                )
            except Exception as e:
                with open('add_to_blog_queue.log', 'a') as f:
                    f.write(f'DELREPORT-WEB-EXC-{e}-slug={slug}\n')
            # remove it from the user reports list
            redis_user_reports_list = [d for d in redis_user_reports_list if d['dr_id'] != int(dr_id)]
            num_removed = 1

    else:
        redis_user_reports_list=[]


    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis
    
    return jsonify({'num_removed':num_removed})
#---------------------------------------------------------------------------------------------------    
@app.route('/get_user_portfolio_names', methods=['GET'])
@check_for_token
def get_user_portfolio_names():

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    ipv4            = get_remote_address()

    redis_key_user_portfolio_names = f'user_portfolios_{userid}' # this is a json version of a list of dictionaries
    redis_user_portfolio_names_list = redis_client2.get(redis_key_user_portfolio_names)

    user_portfolios = [{'id':0, 'name':'main'}] # default portfolio

    if redis_user_portfolio_names_list is not None:
        user_portfolios = json.loads(redis_user_portfolio_names_list)
    else:
        redis_client2.set(redis_key_user_portfolio_names,json.dumps(user_portfolios)) # save the default 0:'main' portfolio name

    logging.warning("get_user_portfolio_names userid=%s ip=%s num_portfolios=%s", userid, ipv4, len(user_portfolios))

    return jsonify({'portfolio_names_list':user_portfolios})
#---------------------------------------------------------------------------------------------------
@app.route('/add_user_portfolio_name/<string:portfolio_name>', methods=['POST'])
@check_for_token
def add_user_portfolio_name(portfolio_name): # use slug as an identifier for which saved report to update

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_portfolio_names = f'user_portfolios_{userid}' # this is a json version of a list of dictionaries
    redis_user_portfolio_names_list = redis_client2.get(redis_key_user_portfolio_names)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'add_user_portfolio_name name={portfolio_name}')
  

    if redis_user_portfolio_names_list is not None: 
        user_portfolios = json.loads(redis_user_portfolio_names_list)
    else:
        user_portfolios = [{'id':0, 'name':'main'}] # this should not happend because this entry was added in get_protfolios ...

    if any(d["name"] == portfolio_name for d in user_portfolios): # its a duplicate
        return jsonify({'portfolio_names_list':'duplicate'})
    

    new_id = max(user_portfolios, key=lambda x: x["id"])["id"] + 1 # new id is 1 larger than the largest id
    port_dict = {'id':new_id,'name':portfolio_name}
    
    user_portfolios.append(port_dict)

    # print('..................user_portfolios=',user_portfolios)

    redis_client2.set(redis_key_user_portfolio_names,json.dumps(user_portfolios)) # save the default 0:'main' portfolio name

    return jsonify({'portfolio_names_list':user_portfolios,'new_portfolio':port_dict})
#---------------------------------------------------------------------------------------------------
@app.route('/edit_user_portfolio_name/<string:old_name>/<string:new_name>', methods=['POST'])
@check_for_token
def edit_user_portfolio_name(old_name,new_name): # use slug as an identifier for which saved report to update

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_portfolio_names = f'user_portfolios_{userid}' # this is a json version of a list of dictionaries
    redis_user_portfolio_names_list = redis_client2.get(redis_key_user_portfolio_names)

    # print(old_name,new_name)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'edit_user_portfolio_name old_name={old_name} new_name={new_name}')
  

    if redis_user_portfolio_names_list is not None: 
        user_portfolios = json.loads(redis_user_portfolio_names_list)
    else:
        user_portfolios = [{'id':0, 'name':'main'}] # this should not happend because this entry was added in get_protfolios ...


    for p in user_portfolios:
        if p['name'] != 'main' and p['name'] == old_name:
            p['name'] = new_name
            break

    redis_client2.set(redis_key_user_portfolio_names,json.dumps(user_portfolios)) # save the default 0:'main' portfolio name

    return jsonify({'portfolio_names_list':user_portfolios})
#---------------------------------------------------------------------------------------------------
@app.route('/del_user_portfolio_name/<string:portfolio_name>', methods=['POST'])
@check_for_token
def del_user_portfolio_name(portfolio_name): # use slug as an identifier for which saved report to update
    


    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    portfolio_id    = get_id_from_portfolio_name(userid,portfolio_name)

    redis_key_user_portfolio_names = f'user_portfolios_{userid}' # this is a json version of a list of dictionaries
    redis_user_portfolio_names_list = redis_client2.get(redis_key_user_portfolio_names)

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'del_user_portfolio_name name={portfolio_name}')


    if redis_user_portfolio_names_list is not None: 
        user_portfolios = json.loads(redis_user_portfolio_names_list)
    else:
        user_portfolios = [{'id':0, 'name':'main'}] # this should not happend because this entry was added in get_protfolios ...

    id = -1
    for p in user_portfolios:
        if p['name'] != 'main' and p['name'] == portfolio_name:
            
            user_portfolios.remove(p) # remove this user's portfolio id = p['id]
            # print('\n\n removing portfolio id=',id,'\n\n')
            break
  
    redis_client2.set(redis_key_user_portfolio_names,json.dumps(user_portfolios)) # save the default 0:'main' portfolio name
    #------------------------------------------------------------
    # also remove all reports with this portfolioid
    #------------------------------------------------------------
    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)

        redis_user_reports_list = [d for d in redis_user_reports_list if d['portfolioID'] != portfolio_id]

        redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list))
    
    return jsonify({'portfolio_names_list':user_portfolios})

#---------------------------------------------------------------------------------------------------
# WATCHLIST ROUTES
# Redis key: user_watchlists_{userid} -> JSON list of dicts: [{name, resourceId, resourceName, isDefault}, ...]
# Redis key: user_watchlist_items_{userid}_{name} -> JSON list of symbol strings: ["AAPL", "MSFT", ...]
#---------------------------------------------------------------------------------------------------
@app.route('/get_user_watchlist_names', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def get_user_watchlist_names():
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key = f'user_watchlists_{userid}'
    raw = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    return jsonify({'watchlist_names_list': watchlists})
#---------------------------------------------------------------------------------------------------
@app.route('/get_user_watchlist_items/<string:name>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def get_user_watchlist_items(name):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key = f'user_watchlist_items_{userid}_{name}'
    raw = redis_client2.get(redis_key)
    items = json.loads(raw) if raw else []

    return jsonify({'watchlist_items': items})
#---------------------------------------------------------------------------------------------------
@app.route('/add_user_watchlist_name/<string:name>/<string:resourceId>/<string:resourceName>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def add_user_watchlist_name(name, resourceId, resourceName):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    user_level      = str(data.get('user_level', '1'))

    max_allowed = config.num_watchlists_allowed_by_level.get(user_level, 0)

    redis_key = f'user_watchlists_{userid}'
    raw = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    if len(watchlists) >= max_allowed:
        return jsonify({'watchlist_names_list': 'limit_reached'})

    if any(w['name'] == name for w in watchlists):
        return jsonify({'watchlist_names_list': 'duplicate'})

    is_default = len(watchlists) == 0  # first watchlist becomes default
    new_wl = {'name': name, 'resourceId': resourceId, 'resourceName': resourceName, 'isDefault': is_default, 'addToSecurities': False}
    watchlists.append(new_wl)
    redis_client2.set(redis_key, json.dumps(watchlists))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'add_watchlist name={name}')

    return jsonify({'watchlist_names_list': watchlists, 'new_watchlist': new_wl})
#---------------------------------------------------------------------------------------------------
@app.route('/edit_user_watchlist_name/<string:old_name>/<string:new_name>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def edit_user_watchlist_name(old_name, new_name):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key = f'user_watchlists_{userid}'
    raw = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    for w in watchlists:
        if w['name'] == old_name:
            w['name'] = new_name
            break

    redis_client2.set(redis_key, json.dumps(watchlists))

    # rename the items key too
    old_items_key = f'user_watchlist_items_{userid}_{old_name}'
    new_items_key = f'user_watchlist_items_{userid}_{new_name}'
    raw_items = redis_client2.get(old_items_key)
    if raw_items:
        redis_client2.set(new_items_key, raw_items)
        redis_client2.delete(old_items_key)

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'edit_watchlist old={old_name} new={new_name}')

    return jsonify({'watchlist_names_list': watchlists})
#---------------------------------------------------------------------------------------------------
@app.route('/del_user_watchlist_name/<string:name>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def del_user_watchlist_name(name):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key = f'user_watchlists_{userid}'
    raw = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    watchlists = [w for w in watchlists if w['name'] != name]

    # delete items for that watchlist
    items_key = f'user_watchlist_items_{userid}_{name}'
    redis_client2.delete(items_key)

    redis_client2.set(redis_key, json.dumps(watchlists))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'del_watchlist name={name}')

    return jsonify({'watchlist_names_list': watchlists})
#---------------------------------------------------------------------------------------------------
@app.route('/set_default_watchlist/<string:name>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def set_default_watchlist(name):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key = f'user_watchlists_{userid}'
    raw = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    for w in watchlists:
        w['isDefault'] = (w['name'] == name)

    redis_client2.set(redis_key, json.dumps(watchlists))

    return jsonify({'watchlist_names_list': watchlists})
#---------------------------------------------------------------------------------------------------
@app.route('/set_watchlist_add_to_securities/<string:name>/<string:value>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def set_watchlist_add_to_securities(name, value):
    token      = request.args.get("token")
    data       = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid     = data['user']
    redis_key  = f'user_watchlists_{userid}'
    raw        = redis_client2.get(redis_key)
    watchlists = json.loads(raw) if raw else []

    for w in watchlists:
        if w['name'] == name:
            w['addToSecurities'] = (value == 'true')

    redis_client2.set(redis_key, json.dumps(watchlists))
    return jsonify({'watchlist_names_list': watchlists})
#---------------------------------------------------------------------------------------------------
@app.route('/add_user_watchlist_item/<string:watchlist_name>/<string:symbol>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def add_user_watchlist_item(watchlist_name, symbol):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    user_level      = str(data.get('user_level', '1'))

    max_items = config.num_watchlist_items_allowed_by_level.get(user_level, 0)

    items_key = f'user_watchlist_items_{userid}_{watchlist_name}'
    raw = redis_client2.get(items_key)
    items = json.loads(raw) if raw else []

    symbol = symbol.upper()

    if symbol in items:
        return jsonify({'watchlist_items': 'duplicate'})

    if len(items) >= max_items:
        return jsonify({'watchlist_items': 'limit_reached'})

    items.append(symbol)
    redis_client2.set(items_key, json.dumps(items))

    return jsonify({'watchlist_items': items})
#---------------------------------------------------------------------------------------------------
@app.route('/del_user_watchlist_item/<string:watchlist_name>/<string:symbol>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def del_user_watchlist_item(watchlist_name, symbol):
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    items_key = f'user_watchlist_items_{userid}_{watchlist_name}'
    raw = redis_client2.get(items_key)
    items = json.loads(raw) if raw else []

    symbol = symbol.upper()
    items = [s for s in items if s != symbol]
    redis_client2.set(items_key, json.dumps(items))

    return jsonify({'watchlist_items': items})
#---------------------------------------------------------------------------------------------------
@app.route('/detect_symbols_group/<string:encoded_symbols>', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def detect_symbols_group(encoded_symbols):
    import base64
    try:
        decoded = base64.b64decode(encoded_symbols).decode('utf-8')
        symbols = [s.strip().upper() for s in decoded.split(',') if s.strip()]
    except Exception:
        return jsonify({'error': 'invalid_encoding'})

    if len(symbols) == 0:
        return jsonify({'error': 'no_symbols'})

    # load symbol sets for each resource group
    group_matches = []
    for rid, csv_path in config.available_resources_path.items():
        try:
            df = pd.read_csv(csv_path)
            csv_symbols = set(df['symbols'].str.upper())
            matched = [s for s in symbols if s in csv_symbols]
            if len(matched) > 0:
                group_matches.append({
                    'resource_id': rid,
                    'resource_name': config.available_resources.get(rid, ''),
                    'match_count': len(matched),
                    'matched_symbols': matched
                })
        except Exception:
            continue

    if len(group_matches) == 0:
        return jsonify({'error': 'no_matches'})

    # sort by match count descending - best match first
    group_matches.sort(key=lambda g: g['match_count'], reverse=True)

    best = group_matches[0]
    valid_symbols = best['matched_symbols']
    invalid_symbols = [s for s in symbols if s not in valid_symbols]

    return jsonify({
        'detected_group': {'resource_id': best['resource_id'], 'resource_name': best['resource_name']},
        'valid_symbols': valid_symbols,
        'invalid_symbols': invalid_symbols,
        'all_groups': [{'resource_id': g['resource_id'], 'resource_name': g['resource_name'], 'match_count': g['match_count']} for g in group_matches]
    })
#---------------------------------------------------------------------------------------------------
@app.route('/bulk_add_watchlist_items/<string:watchlist_name>/<string:encoded_symbols>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def bulk_add_watchlist_items(watchlist_name, encoded_symbols):
    import base64
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    user_level      = str(data.get('user_level', '1'))

    max_items = config.num_watchlist_items_allowed_by_level.get(user_level, 0)

    try:
        decoded = base64.b64decode(encoded_symbols).decode('utf-8')
        symbols = [s.strip().upper() for s in decoded.split(',') if s.strip()]
    except Exception:
        return jsonify({'error': 'invalid_encoding'})

    items_key = f'user_watchlist_items_{userid}_{watchlist_name}'
    raw = redis_client2.get(items_key)
    items = json.loads(raw) if raw else []

    added = 0
    skipped_dup = 0
    skipped_limit = 0

    for sym in symbols:
        if sym in items:
            skipped_dup += 1
            continue
        if len(items) >= max_items:
            skipped_limit += len(symbols) - symbols.index(sym) - skipped_dup
            break
        items.append(sym)
        added += 1

    redis_client2.set(items_key, json.dumps(items))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'bulk_add_watchlist name={watchlist_name} added={added}')

    return jsonify({
        'watchlist_items': items,
        'watchlist_name': watchlist_name,
        'added_count': added,
        'skipped_duplicate': skipped_dup,
        'skipped_limit': skipped_limit
    })

#---------------------------------------------------------------------------------------------------
# PUBLISHED SECURITIES LISTS (admin-managed, available to users by level)
# Redis key: tw_published_lists -> JSON list of dicts
#---------------------------------------------------------------------------------------------------
@app.route('/get_published_lists', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def get_published_lists():
    token = request.args.get("token")
    data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    userid = data['user']
    user_level = str(data.get('user_level', '1'))

    raw = redis_client2.get('tw_published_lists')
    all_lists = json.loads(raw) if raw else []

    is_admin = bool(data.get('is_admin', False)) or userid in config.admin_userids

    # filter by access level - admins see all
    if is_admin:
        visible = all_lists
    else:
        visible = [pl for pl in all_lists if user_level in pl.get('access_levels', []) and pl.get('enabled', True)]

    return jsonify({'published_lists': visible, 'is_admin': is_admin})

#---------------------------------------------------------------------------------------------------
@app.route('/create_published_list', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def create_published_list():
    token = request.args.get("token")
    data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    userid = data['user']

    # TW2: data['user'] is a UUID; admin_userids is the legacy WP integer list.
    # Trust the LTK is_admin claim first; keep the legacy list as a fallback.
    if not (data.get('is_admin', False) or userid in config.admin_userids):
        return jsonify({'error': 'not_authorized'}), 403

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "bad_json"}), 400
    name = body.get('name', '').strip()
    resource_id = str(body.get('resource_id', ''))
    symbols = body.get('symbols', [])
    access_levels = body.get('access_levels', list(config.level_access_hierarchy.keys()))

    if not name or not resource_id:
        return jsonify({'error': 'missing_fields'})

    raw = redis_client2.get('tw_published_lists')
    all_lists = json.loads(raw) if raw else []

    if any(pl['name'] == name for pl in all_lists):
        return jsonify({'error': 'duplicate_name'})

    new_list = {
        'name': name,
        'resource_id': resource_id,
        'resource_name': config.available_resources.get(resource_id, ''),
        'symbols': [s.strip().upper() for s in symbols if s.strip()],
        'access_levels': access_levels,
        'enabled': True,
        'created_by': userid,
        'order': len(all_lists)
    }

    all_lists.append(new_list)
    redis_client2.set('tw_published_lists', json.dumps(all_lists))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'create_published_list name={name}')

    return jsonify({'published_lists': all_lists})

#---------------------------------------------------------------------------------------------------
@app.route('/update_published_list', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def update_published_list():
    token = request.args.get("token")
    data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    userid = data['user']

    if not (data.get('is_admin', False) or userid in config.admin_userids):
        return jsonify({'error': 'not_authorized'}), 403

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "bad_json"}), 400
    name = body.get('name', '')
    updates = body.get('updates', {})

    raw = redis_client2.get('tw_published_lists')
    all_lists = json.loads(raw) if raw else []

    found = False
    for pl in all_lists:
        if pl['name'] == name:
            if 'symbols' in updates:
                pl['symbols'] = [s.strip().upper() for s in updates['symbols'] if s.strip()]
            if 'access_levels' in updates:
                pl['access_levels'] = updates['access_levels']
            if 'enabled' in updates:
                pl['enabled'] = updates['enabled']
            if 'new_name' in updates:
                pl['name'] = updates['new_name'].strip()
            found = True
            break

    if not found:
        return jsonify({'error': 'not_found'})

    redis_client2.set('tw_published_lists', json.dumps(all_lists))
    return jsonify({'published_lists': all_lists})

#---------------------------------------------------------------------------------------------------
@app.route('/delete_published_list/<string:name>', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def delete_published_list(name):
    token = request.args.get("token")
    data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    userid = data['user']

    if not (data.get('is_admin', False) or userid in config.admin_userids):
        return jsonify({'error': 'not_authorized'}), 403

    raw = redis_client2.get('tw_published_lists')
    all_lists = json.loads(raw) if raw else []
    all_lists = [pl for pl in all_lists if pl['name'] != name]
    redis_client2.set('tw_published_lists', json.dumps(all_lists))

    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4, country_code, zip, f'delete_published_list name={name}')

    return jsonify({'published_lists': all_lists})

#---------------------------------------------------------------------------------------------------
# USER SECURITIES GROUP PREFERENCES
# Redis key: user_securities_prefs_{userid} -> JSON dict
#---------------------------------------------------------------------------------------------------
@app.route('/get_securities_prefs', methods=['GET'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def get_securities_prefs():
    token = request.args.get("token")
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid = data['user']

    redis_key = f'user_securities_prefs_{userid}'
    raw = redis_client2.get(redis_key)
    prefs = json.loads(raw) if raw else {'hidden_groups': [], 'enabled_published': []}

    return jsonify({'securities_prefs': prefs})

#---------------------------------------------------------------------------------------------------
@app.route('/set_securities_prefs', methods=['POST'])
@check_for_token
@limiter.limit(config.rate_limit_general[0])
@limiter.limit(config.rate_limit_general[1])
@limiter.limit(config.rate_limit_general[2])
@limiter.limit(config.rate_limit_general[3])
def set_securities_prefs():
    token = request.args.get("token")
    data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    userid = data['user']

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "bad_json"}), 400
    prefs = {
        'hidden_groups': body.get('hidden_groups', []),
        'enabled_published': body.get('enabled_published', [])
    }

    redis_key = f'user_securities_prefs_{userid}'
    redis_client2.set(redis_key, json.dumps(prefs))

    return jsonify({'securities_prefs': prefs})

#---------------------------------------------------------------------------------------------------
# using dr_id as the primary key for this user to update the num_shares of the opportunity in the list
@app.route('/get_note/<int:dr_id>', methods=['GET'])
@check_for_token
def get_note(dr_id): # use dr_id as an identifier for which saved report to update


    # print(dr_id)

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    # print(redis_user_reports_list)

    if redis_user_reports_list is None:
        return jsonify({'note':'missing opp'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)

    # get the list index with the slug=dr_id
    # use the list index to update num_shares and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == dr_id]
    i=-1
    if len(idx)==1:i=idx[0]
    # now we have the index of the opportunity 
    if 'note' in redis_user_reports_list[i]:
        note=redis_user_reports_list[i]['note']
    else:
        note = ''
    
    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'get_note dr_id={dr_id} note={note}')


    # redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    return jsonify({'note':note})
#---------------------------------------------------------------------------------------------------
# using slug as the primary key to update the num_shares of the opportunity in the list 
@app.route('/save_note/<string:note>/<int:dr_id>', methods=['POST'])
@check_for_token
def save_note(note,dr_id): # use dr_id as an identifier for which saved opp to update



    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)


    if redis_user_reports_list is None:
        return jsonify({'update_note':'missing opp'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)
    # get the list index with the dr_id=dr_id
    # use the list index to update num_shares and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == dr_id]
    i=-1
    if len(idx)==1:i=idx[0]
    # now we have the index of the opportunity to update
    if note == '-': note = '' # its passed with a - so rest api doesnt fail
    redis_user_reports_list[i]['note']=note
    # set the opp list to the new listed after updating the num_shares
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    ipv4 = get_remote_address()
    update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'save_note dr_id={dr_id} note={note}')


    return jsonify({'update_note':'saved'})
#---------------------------------------------------------------------------------------------------
# send this opp to social media
#---------------------------------------------------------------------------------------------------
@app.route('/opp_to_social_media/<string:note>/<string:slug>', methods=['POST'])
@check_for_token
def opp_to_social_media(note,slug): # use slug as an identifier for which saved opp to update

    # with open('/home/flask/appserver/appserver/test.txt', 'a') as file: file.write('b3' + '\n')

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    

    if redis_user_reports_list is None:
        return jsonify({'opp_to_social_media':'missing opp'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)



    # get the list index with the slug=slug
    # use the list index to update num_shares and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["slug"] == slug]
    i=-1
    if len(idx)==1:i=idx[0]
    # now we have the index of the opportunity to send to social media - its i

    

    resourceID   = redis_user_reports_list[i]['resourceID']
    symbol       = redis_user_reports_list[i]['symbol']
    date         = redis_user_reports_list[i]['date']
    days_hold    = redis_user_reports_list[i]['days_hold']
    years        = redis_user_reports_list[i]['years']
    slug         = redis_user_reports_list[i]['slug']
    dir          = redis_user_reports_list[i]['direction']
    sharpe_ratio = redis_user_reports_list[i]['sharpe_ratio']
    # note         = redis_user_reports_list[i]['note']
    # if note == '':note='-' # otherwise empty note makes the call fail
    #--------------------------------------------------------------------------------------------------------
    # set the field to 'pos'  means posted   
    #--------------------------------------------------------------------------------------------------------
    redis_user_reports_list[i]['sm_post']='pos'
    if note == '-': note = '' # its passed with a - so rest api doesnt fail
    redis_user_reports_list[i]['note']=note
    # set the opp list to the new listed after updating the sm_post field
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    #--------------------------------------------------------------------------------------------------------
    # add to queue for blog creation to the webserver which is running a flask service called bloq_queue.py
    #--------------------------------------------------------------------------------------------------------

    hostname = socket.gethostname()

    if hostname != 'afshin-VirtualBox': # can't send to queue when on dev server
        if note == '':note = '-'
        url = f'{config.blog_queue_server}am_dr_sm/{resourceID}/{symbol}/{date}/{days_hold}/{years}/{userid}/{slug}/{dir}/{sharpe_ratio}/{note}'
        response=requests.get(url, timeout=10)  # comment this out if its on the dev because it doesn't have access to config.blog_queue_server
        # print('response from posting afshin dr reporrt',response.status_code,response.reason)


    return jsonify({'opp_to_social_media':'success'})
#---------------------------------------------------------------------------------------------------
# del this opp to social media
#---------------------------------------------------------------------------------------------------
@app.route('/opp_del_social_media/<string:slug>', methods=['POST'])
@check_for_token
def opp_del_social_media(slug): # use slug as an identifier for which saved opp to update

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports = f'user_reports_{userid}' # this is a json version of a list of dictionaries
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)


    if redis_user_reports_list is None:
        return jsonify({'opp_del_social_media':'missing opp'})

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)
    # get the list index with the slug=slug
    # use the list index to update num_shares and then load it back to redis db=2
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["slug"] == slug]
    i=-1
    if len(idx)==1:i=idx[0]
    # now we have the index of the opportunity to send to social media - its i


    resourceID   = redis_user_reports_list[i]['resourceID']
    symbol       = redis_user_reports_list[i]['symbol']
    date         = redis_user_reports_list[i]['date']
    days_hold    = redis_user_reports_list[i]['days_hold']
    years        = redis_user_reports_list[i]['years']
    slug         = redis_user_reports_list[i]['slug']
    dir          = redis_user_reports_list[i]['direction']
    sharpe_ratio = redis_user_reports_list[i]['sharpe_ratio']
    # note         = redis_user_reports_list[i]['note'] # note is now passed by the rest api
    
    #--------------------------------------------------------------------------------------------------------
    # set the field to 'del'  means post is being deleted and marked as deleted   
    #--------------------------------------------------------------------------------------------------------
    redis_user_reports_list[i]['sm_post']='del'
    # set the opp list to the new listed after updating the sm_post field
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    #--------------------------------------------------------------------------------------------------------
    # add to queue for blog creation to the webserver which is running a flask service called bloq_queue.py
    #--------------------------------------------------------------------------------------------------------

    hostname = socket.gethostname()

    if hostname != 'afshin-VirtualBox': # can't send to queue when on dev server
        url = f'{config.blog_queue_server}am_dr_sm_del/{resourceID}/{symbol}/{date}/{days_hold}/{years}/{userid}/{slug}/{dir}/{sharpe_ratio}'
        response=requests.get(url, timeout=10)
        # print('response from deleting afshin dr report',response.status_code,response.reason)


    return jsonify({'opp_to_social_media':'success'})

#-------------------------------------------------------------------------------------------------
# get key1 and key2 from keyprovider
def get_keys(): # get key1 and key2 from keystore url
    response = requests.get(config.keystoreURL, timeout=10)
    json = response.json()
    key1 = json['key1']
    key2 = json['key2']

    return key1,key2
#---------------------------------------------------------------------------------------------------
# returns first_name,last_name,email by reading ump data
#-----------------------------------------------------------------------------------------------------
def get_user_name_and_email_ump(userid):
    _,key2 = get_keys()
    url = f'{config.wordpress_url}?ihc_action=api-gate&ihch={key2}&action=user_get_details&uid={userid}'
    response = requests.get(url, timeout=10)
    d = response.json()

    first_name = d['response']['first_name']
    last_name  = d['response']['last_name']
    email      = d['response']['user_email']
    
    return(first_name,last_name,email)

#-----------------------------------------------------------------------------------------------------
# return user_level and user_leve3l_name by reading ump data
# it only returns the largest membership (largest level number) if there are multiple
#-----------------------------------------------------------------------------------------------------
def get_user_memberships_ump(userid):
    _,key2 = get_keys()
    url = f'{config.wordpress_url}?ihc_action=api-gate&ihch={key2}&action=get_user_levels&uid={userid}'
    response = requests.get(url, timeout=10)
    d = response.json()
    membership_keys = d['response'].keys()

    largest_membership = '0'
    for m in membership_keys:
        if m > largest_membership:
            largest_membership = m

    # largest membership is the level we'll use for this user
    tmp=d['response'][largest_membership]  

    user_level = largest_membership
    user_level_name =  d['response'][largest_membership]['level_slug']    

    return(user_level,user_level_name)
    
#-----------------------------------------------------------------------------------------------------


#---------------------------------------------------------------------------------------------------
# purpose is to create an easy name -> group_id  dictionary for use in other functions
# creates 2 dictionaries 1) tt_ groups - a user can subscribe to only 1 of tt_ group - defines daily email format
#                           tt groups are 12 flags showing which of 12 markets to include in the email flag for all = 
#                           000000000000
#                        2) other users can have any number of them
#                            group_names:

#                                subscriber
#                                free
#                                basic_monthly
#                                basic_yearly
#                                premium_monthly
#                                premium_yearly
#                                elite_monthly
#                                elite_yearly
#                                corporate
#-----------------------------------------------------------------------------------------------------
# add group to a user by group_name
#-----------------------------------------------------------------------------------------------------
def add_group_to_user_by_group_name(group_name,subscriber_id):
    # get group_id from group_name
    _,dict_ot = get_email_groups()
    # check if group_name is a key in returned dict_ot
    if group_name in dict_ot:
        group_id = dict_ot[group_name]
        # add group membership for the user
        assign_subscriber_to_a_group(subscriber_id,group_id)
        return f'group_name {group_name} added for subscriber_id:{subscriber_id}'
    else:
        return f"group_name {group_name} doesn't exist in dict_ot"

#-----------------------------------------------------------------------------------------------------
# get all groups from mailerlite and put it in 1 dictionary 
#-----------------------------------------------------------------------------------------------------
def get_email_groups():
    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.groups.list(limit=100, page=1, sort='name')

    dict_groups = {} # all the other groups

    for g in response['data']:
       
            name = g['name'] # strip tt_ - the name has to be tt_ in mailerlite to seperate from other groups
            g_id = g['id']
            dict_groups[name]=g_id


    return dict_groups
#---------------------------------------------------------------------------------------------------
# add a new subscriber to mailerlite
#---------------------------------------------------------------------------------------------------
def add_to_mailerlite(first_name,last_name,email):

    # print('xxxxx',first_name,last_name,email,group_id_user_level,group_id_initial_opt_in)

    email_subscriber_id=0

    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.create(email, fields={'name': first_name, 'last_name': last_name}, ip_address='', optin_ip='')
    email_subscriber_id = response['data']['id']

    return email_subscriber_id
#---------------------------------------------------------------------------------------------------
# finds subscriber by email, and updates first and lastname
def update_subscriber(email,first_name,last_name):

    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.update(email, fields={'name': first_name, 'last_name': last_name}, ip_address='', optin_ip='')
    
    return response
#-----------------------------------------------------------------------------------------------------
def delete_subscriber(subscriber_id):
    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.delete(subscriber_id)
    # response = client.subscribers.forget(subscriber_id) # forget will remove all the old groups
    return response
#-----------------------------------------------------------------------------------------------------
# get the user's email groups from mailerlite
#-----------------------------------------------------------------------------------------------------
def get_subscriber(email):
    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.get(email)

    # print('\n\n\nresponse from get_subscriber=',response,'\n\n')

    first_name = response['data']['fields']['name'] 
    last_name = response['data']['fields']['last_name']
    groups_response = response['data']['groups']
    
    groups = []
    for g in groups_response:
        groups.append({'name':g['name'],'id':g['id']})

    return first_name,last_name,groups    

#---------------------------------------------------------------------------------------------------
def assign_subscriber_to_a_group(subscriber_id,group_id):

    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.assign_subscriber_to_group(int(subscriber_id), int(group_id))
    return response
    # print('assign to group response = ',response)
#---------------------------------------------------------------------------------------------------
def unassign_subscriber_from_a_group(subscriber_id,group_id):

    client = MailerLite.Client({'api_key': config.mailerlite_token })
    response = client.subscribers.unassign_subscriber_from_group(int(subscriber_id), int(group_id))
    return response
    # print('unassign from group response = ',response)
#---------------------------------------------------------------------------------------------------
# this is envoked everytime settings window is opened.  first_time it creates records in redis & mailerlite
# everytime it checks if ump data has changed compared to redis - if it has, data is updated in redis & mailerlite
#
# emails are changed to be opt-in or opt-out - when user is opt-in to email, they will receive daily an email
# with the top 10 opportuniteis based on sharpe-ratio - the variable is either 0 or 1 - 1 is opt-in
# opt-in group is called  (daily-email-opt-in)
# opt-out group is called (daily-email-opt-out)
# the reason we have a opt-out group is for correcting software issues.
# user must have one of the two, if they don't we reassign them to our default email group which is opt-in

# initial state email_state = 1 means it forces to remove group daily-top10-email-opt-out and assigns daily-top10-email-opt-in

@app.route('/settings_top10_email_get', methods=['GET'])
@check_for_token
def settings_top10_email_get(): 

    #------------------------------------------------------------------------------
    # this is initial email settings for users that don't have a redis record
    # checking for both incase there is a group assignment for this user already 
    opt_in_group_name = 'daily-top10-email-opt-in'
    opt_out_group_name= 'daily-top10-email-opt-out' 
    email_state_default = 1
    email_state = email_state_default # when 0 assigns opt_in group and unassigns opt out.  otherwise the other way
        
    #------------------------------------------------------------------------------
    
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_email_settings = f'user_email_settings_{userid}' # this is a json version of a list of dictionaries
    redis_user_email_settings = redis_client2.get(redis_key_email_settings)

    if redis_user_email_settings is None:
        # this user hasn't been added to redis and likely to mailerlite yet

        # 1) get the user's ump info & mailerlite group ids
        email_group_dict=get_email_groups()
        first_name,last_name,email = get_user_name_and_email_ump(userid)
        user_level_id_ump,user_level_name_ump = get_user_memberships_ump(userid)
        # 2) first add to mailerlite to get the mailerlite subscriberid
        email_subscriber_id=add_to_mailerlite(first_name,last_name,email)
        # 3) assign the email groups for the use
        group_id_user_level = email_group_dict[user_level_name_ump]
        assign_subscriber_to_a_group  (email_subscriber_id,group_id_user_level)
        # assign email opt-in or opt-out
        if email_state == 1:
            unassign_subscriber_from_a_group(email_subscriber_id, email_group_dict[opt_out_group_name])
            assign_subscriber_to_a_group  (email_subscriber_id  , email_group_dict[opt_in_group_name])
        else:
            unassign_subscriber_from_a_group(email_subscriber_id, email_group_dict[opt_in_group_name])
            assign_subscriber_to_a_group  (email_subscriber_id  , email_group_dict[opt_out_group_name])

        # 4) then  add to redis and include the mailerlite subscriberid
       
        info = {'first_name':first_name,'last_name':last_name,'email':email,'email_subscriber_id':email_subscriber_id,'wp_userid':userid,'wp_user_level_name':user_level_name_ump,'top10_email_state':email_state}
        redis_client2.set(redis_key_email_settings,json.dumps(info))
    else: 
        current_settings = json.loads(redis_user_email_settings)
        if 'top10_email_state' in current_settings:
            email_state = current_settings['top10_email_state']

            # print('email_state=',email_state,type(email_state))
        else: # this user doesn't have the top10_email_state key in the record.  either its old or an error stopped adding it - add it here
            email_subscriber_id = current_settings['email_subscriber_id']
            current_settings['top10_email_state'] = email_state_default
            redis_client2.set(redis_key_email_settings,json.dumps(current_settings))
            # also add /update the user group to mailerlite
            email_group_dict=get_email_groups()
            email_state = email_state_default
            if email_state == 1:
                unassign_subscriber_from_a_group(email_subscriber_id, email_group_dict['daily-top10-email-opt-out'])
                assign_subscriber_to_a_group    (email_subscriber_id , email_group_dict['daily-top10-email-opt-in'])
            else:
                unassign_subscriber_from_a_group(email_subscriber_id,  email_group_dict['daily-top10-email-opt-in'])
                assign_subscriber_to_a_group    (email_subscriber_id ,email_group_dict['daily-top10-email-opt-out'])


    

    return jsonify({'email_state':email_state})

#---------------------------------------------------------------------------------------------------
# this is for email selection by user 1 is opt-in and 0 is opt-out
@app.route('/settings_top10_email_set/<int:email_selection>', methods=['POST'])
@check_for_token
def settings_email_markets_set(email_selection): # email selection is either 0 or 1

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']


    redis_key_email_settings = f'user_email_settings_{userid}' # this is a json version of a list of dictionaries
    redis_user_email_settings = redis_client2.get(redis_key_email_settings)
   

    if redis_user_email_settings is not None:
        current_settings = json.loads(redis_user_email_settings)
        if 'top10_email_state' in current_settings:
            old_email_state = current_settings['top10_email_state']
            if email_selection != old_email_state: # need to change the selection
                email_subscriber_id = current_settings['email_subscriber_id']
                current_settings['top10_email_state'] = email_selection
                email_group_dict=get_email_groups()
                if email_selection == 1:
                    unassign_subscriber_from_a_group(email_subscriber_id, email_group_dict['daily-top10-email-opt-out'])
                    assign_subscriber_to_a_group    (email_subscriber_id , email_group_dict['daily-top10-email-opt-in'])
                else:
                    unassign_subscriber_from_a_group(email_subscriber_id,  email_group_dict['daily-top10-email-opt-in'])
                    assign_subscriber_to_a_group    (email_subscriber_id ,email_group_dict['daily-top10-email-opt-out'])

                redis_client2.set(redis_key_email_settings,json.dumps(current_settings))
   
   
    

    # --------------------------------------------------------------------
    # send info for activity logging
    # --------------------------------------------------------------------
    # atime, wp_userid, ipv4, country_code, zip = get_geo_from_token(token)
    # ipv4 = get_remote_address()
    # update_activity_log(atime, -1, wp_userid, ipv4,country_code, zip, f'settings_email_markets_set flags={flags}')
    

    return jsonify({'settings_email_top10_set':'success'})
#-----------------------------------------------------------------------------------------------------
# this is called from populate portfolio - does 2 things - gets the # or populates a portfolio
@app.route('/populate_portfolio/<string:qvars>/<string:portfolio_name>/<string:action>', methods=['POST'])
@check_for_token
def populate_portfolio(qvars,portfolio_name,action): 

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']
    pid             = get_id_from_portfolio_name(userid,portfolio_name) # portfolio_id

    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    base_year  = int(today_date[0:4]) 

    decoded_vars = base64.b64decode(qvars)
    decoded_str  = decoded_vars.decode('utf-8')
    sp=decoded_str.split('|')


    # there were 12 variables to pass so I encoded it to 1 base64 string - can alsways add more vars in the future
    #  let qvars = window.btoa(`${id}|${monthNum}|${day}|${years}|${pyears}|${min_sr}|${avg_ret}|${min_mfe}|${day_range}`);
    id=sp[0]
    month_name=calendar.month_name[int(sp[1])]
    day=sp[2]
    years=sp[3]
    pyears=sp[4]
    min_sr=sp[5]
    avg_ret=sp[6]
    min_mfe=sp[7]
    day_range=sp[8]
    min_mfe_pct=float(sp[9])
    initial_status=sp[10]
    min_stock_price=float(sp[11])
    min_sr2  = sp[12]
    avg_ret2 = sp[13]
    keep_highest_sr = sp[14] # this is '0' or '1'   
    days_look_forward_sr = int(sp[15])


    #---------------------------------
    # this if disables the % reach filter if the min_mfe_pct is set to less than 100% - 
    # It then filtered manually at the last step of filteration, year by year - very processor intensive
    if min_mfe_pct == 1:
        filter_value = min_mfe
    else:
        filter_value = '0'
    #---------------------------------

    if day_range.strip() == '': day_range = '1-1000'
    # 1-1000 day range basically means all opportunities based on day range 12/3/2023
    ret = OppList4(id, month_name, day, years, pyears, day_range,'0',filter_value)
    # def OppList4(resourceID, month, day, year1, year2,day_range,oppListExpanded, apply_filter='0'):
    s = ret.get_data(as_text=True)
    dict = json.loads(s) # load serialized json string in as dictionary

    # print('opplist returned=',dict['OppList'])
    
    opp_list = dict['OppList']

    # print('opp_list=',len(opp_list),opp_list)

    if len(opp_list) > 0:


        filters_list = dict['AvailableFilters']

        if min_mfe+'%' not in filters_list:
            opp_list = []  # filter was too large to return anything.  OppList4 doesn't handle this 

        # filter by day range
        dsp = day_range.split('-')
        d1 = int(dsp[0])-1
        d2 = int(dsp[1])-1

        # format of opp list is [date,symbol,days,long/short,SR,average_gain,median_profit,cumulative_return,std_dev]
        filtered_opplist1 = [entry for entry in opp_list if d1 <= float(entry[2]) <= d2] # filter by day range
        filtered_opplist2 = [entry for entry in filtered_opplist1 if float(entry[5]) >= float(avg_ret)] # filter by average return
        filtered_opplist3 = [entry for entry in filtered_opplist2 if float(entry[4]) >= float(min_sr)] # filter by sharpe ratio

        # now check the latest price for each security against min_stock_price to filter low priced stocks
        filtered_opplist4 = []
        for entry in filtered_opplist3:

            symbol = entry[1]
            p = getStockLastPrice(id, symbol)
            s = p.get_data(as_text=True)
            dict = json.loads(s) # load serialized json string in as dictionary
            last_price = dict['StockLastPrice'][1]
            last_date  = dict['StockLastPrice'][0]

            if float(last_price) >= min_stock_price:
                filtered_opplist4.append(entry)

        # aded Avg_return2 and SR2 for filtering    
        filtered_opplist5 = [entry for entry in filtered_opplist4 if float(entry[7]) >= float(avg_ret2)] # filter by average return 2
        filtered_opplist5 = [entry for entry in filtered_opplist5 if float(entry[8]) >= float(min_sr2)] # filter by sharpe ratio 2
            
        # now filter by  min_mfe_pct - this is what % of the annual mfe has reached the selected % - this value < 100% also disables the % filter when opplist4 is called  
        if min_mfe_pct < 1 and int(min_mfe)>0:
            filtered_opplist6 = []
            for entry in filtered_opplist5:
                cd=getChartData4(id, entry[0], entry[1], entry[2], years)
                chart_data = cd.get_data(as_text=True)
                dict = json.loads(chart_data)
                perf_data = dict['ChartData4'] # this is a list of dictionaries
                count_years_reached = 0
                for year_perf in perf_data:
                    if year_perf['year'] != base_year:
                        if entry[3] == 'Long':
                            reached=float(year_perf['pct'].split(',')[1]) # this is the long percentage reached for the trade by year year_perf['year']

                        elif entry[3] == 'Short':
                            reached=float(year_perf['pct'].split(',')[2]) # this is the short percentage reached for the trade by year year_perf['year']
                            # print('--',abs(reached),float(min_mfe))
                        
                        if abs(reached) >= float(min_mfe): count_years_reached += 1
                    

                # print('symbol:',entry[1],' reached=',count_years_reached,'total years:',len(perf_data)-1, float(min_mfe_pct))
                # print(count_years_reached/(len(perf_data)-1) ,float(min_mfe_pct))
                if count_years_reached/(len(perf_data)-1) >= float(min_mfe_pct): # checking the % years gain reached min_mfe - compared to what min % we wanted min_mfe_pct
                    filtered_opplist6.append(entry)

        else:
            filtered_opplist6 = filtered_opplist5    
    else:
        filtered_opplist6 = []

    # print(len(opp_list),len(filtered_opplist1),len(filtered_opplist2),len(filtered_opplist3),len(filtered_opplist4))

    if action == 'count':
        return jsonify({'populate_portfolio':'success','count':len(filtered_opplist6)})
    
    #-----------------------------------------------------------------------------------------------------------------------
    # load the user's portfolio entries
    #-----------------------------------------------------------------------------------------------------------------------
    redis_key_user_reports = f'user_reports_{userid}'
    # user_dict = {}
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    # print('redis_user_reports_list=',redis_user_reports_list)
    if redis_user_reports_list is not None: 
        redis_user_reports_list = json.loads(redis_user_reports_list)
        # is_this_a_duplicate,d_id = check_for_duplicates(redis_user_reports_list,date_range_report_dict) # checks if this is a duplicate
        if len(redis_user_reports_list)>0:
            max_item = max(redis_user_reports_list, key=lambda x: x['dr_id'])
            dr_id = max_item['dr_id']+1
        else:
            dr_id=0
    else:
        redis_user_reports_list=[]
        dr_id = 0    

    #-----------------------------------------------------------------------------------------------------------------------
    # add the filtered_opplist5 list to the user's portfolio
    #-----------------------------------------------------------------------------------------------------------------------        
    if action == 'add':

        # d_sr = config.trading_days_search_highest_sr # just set it to a shorter variable for 
        d_sr = days_look_forward_sr # this value is coming from the UI days selection - 

        for opp in filtered_opplist6:

            found_larger_sr  = False
            found_larger_sr2 = False

            # get portfolio id from the portfolio name
            pid = get_id_from_portfolio_name(userid,portfolio_name)

            
            # find the dates before and after the opp date to check for highest SR 12/4/2023
            dates_before_list,dates_after_list=find_weekdays_around_xdate(opp[0],d_sr)

            #-----------------------------------------------------------------------------------------------------------------------
            # Find the highest sharpe ratio for this opp for the next n days set in config.trading_days_search_highest_sr
            #-----------------------------------------------------------------------------------------------------------------------     

            largest_sr   = [opp[0],opp[4]]
            largest_sr2  = [opp[0],opp[8]]
            
            for d in dates_after_list:
                note_content = ''

                symbol = opp[1]
     
                month_name = calendar.month_name[int(d[5:7])]
                day_number = str(int(d[8:10]))

                ret = OppList4(id, month_name, day_number, years, pyears, day_range,'0',filter_value,symbol) 

                s = ret.get_data(as_text=True)
                dict = json.loads(s) # load serialized json string in as dictionary 

                # now find out if the future date has a sr and sr2 that's larger than today's
                if len(dict['OppList']) > 0:
                    date_sr = dict['OppList'][0][0] 
                    sr      = dict['OppList'][0][4] # this is the original sr, sr2 is 8
                    sr2     = dict['OppList'][0][8]  # this is  sr2 


                    if float(sr) > float(largest_sr[1]):
                        largest_sr=[date_sr,sr]
                        found_larger_sr  = True
        

                    if float(sr2) > float(largest_sr2[1]):
                        largest_sr2=[date_sr,sr2]    
                        found_larger_sr2 = True
            
            if found_larger_sr == False and found_larger_sr2 == False: 
                note_content = f'For the date: {opp[0]} \nsharpe ratio = {largest_sr[1]} \nsharpe ratio2 = {largest_sr2[1]}\n are the highest found based on the next {days_look_forward_sr} days.\n'
                initial_status = '0'
            else:    
                note_content = f'Higher SR  for this opportunity on {largest_sr[0]} SR={largest_sr[1]}.\n'
                note_content+= f'Higher SR2 for this opportunity on {largest_sr2[0]} SR2={largest_sr2[1]}. \n'
                initial_status = '5'

            #-----------------------------------------------------------------------------------
            # if keep_highest_sr is true or '1' don't add the items with better future SR
            #-----------------------------------------------------------------------------------
            # if (keep_highest_sr == '1' and initial_status != '5') or keep_highest_sr == '0':
                # filtered_opplist7.append(opp)

            date_range_report_dict = {

                'publishDate' : datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'), # date published is only set when its first created
                'resourceID'  : id,
                'portfolioID' : pid,
                'symbol'      : opp[1],
                'date'        : opp[0],
                'days_hold'   : str(int(opp[2])+1), # it was off by 1
                'years'       : years,
                'slug'        : '',      # no slug and no report generation for the auto populated opportunitesi generally used for auto trading
                'direction'   : opp[3].lower(),
                'sharpe_ratio': str(opp[4]),
                'num_shares'  : 1,
                'note'        : note_content,
                'sm_post'     : 'np',         # valuses are 'np':not posted    'del': posted and deleted  'pos':posted
                'status'      : initial_status
            }
            date_range_report_dict['dr_id']=dr_id

            is_this_a_duplicate,d_id = check_for_duplicates(redis_user_reports_list,date_range_report_dict) # checks if this is a duplicate
            if is_this_a_duplicate: # don't allow putting the same opportunity in the same portfolio 
                continue

            dr_id += 1 # increment dr_id for the next report

            if (keep_highest_sr == '1' and initial_status != '5') or keep_highest_sr == '0': 
                redis_user_reports_list.append(date_range_report_dict)

        redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

        return jsonify({'populate_portfolio':'success','count':len(redis_user_reports_list)})
    #-----------------------------------------------------------------------------------------------------------------------
    # remove the filtered_opplist5 list to the user's portfolio
    #-----------------------------------------------------------------------------------------------------------------------        
    if action == 'remove':
        # print('before length of redis_user_reports_list=',len(redis_user_reports_list))
        
        for opp in filtered_opplist6:

            # get portfolio id from the portfolio name
            
            date_range_report_dict = {

                'publishDate' : datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'), # date published is only set when its first created
                'resourceID'  : id,
                'portfolioID' : pid,
                'symbol'      : opp[1],
                'date'        : opp[0],
                'days_hold'   : str(int(opp[2])+1), # it was off by 1
                'years'       : years,
                'slug'        : '',      # no slug and no report generation for the auto populated opportunitesi generally used for auto trading
                'direction'   : opp[3].lower(),
                'sharpe_ratio': str(opp[4]),
                'num_shares'  : 1,
                'note'        : '',
                'sm_post'     : 'np',         # valuses are 'np':not posted    'del': posted and deleted  'pos':posted
                'status'      : initial_status
            }
            # date_range_report_dict['dr_id']=dr_id

            is_this_a_duplicate,d_id = check_for_duplicates(redis_user_reports_list,date_range_report_dict) # checks if this is a duplicate

            if is_this_a_duplicate: # remove the opportunity from the list
                date_range_report_dict['dr_id'] = d_id
                # tmp = [d for d in redis_user_reports_list if d['symbol'] == date_range_report_dict['symbol'] and d['date']==date_range_report_dict['date'] and d['days_hold'] == date_range_report_dict['days_hold'] and d['years'] == date_range_report_dict['years'] and d['portfolioID'] == date_range_report_dict['portfolioID']]
                tmp = []
                for d in redis_user_reports_list:
                    if d['symbol'] == date_range_report_dict['symbol'] and d['date']==date_range_report_dict['date'] and d['days_hold'] == date_range_report_dict['days_hold'] and d['years'] == date_range_report_dict['years'] and d['portfolioID'] == date_range_report_dict['portfolioID']:
                        continue
                    tmp.append(d)
                redis_user_reports_list = tmp

        redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis
        return jsonify({'populate_portfolio':'success','count':len(redis_user_reports_list)})
    #-----------------------------------------------------    
    if action == 'remove_blue': # remove opportunities with status set to lightblue which is 5.
        tmp = []
        for d in redis_user_reports_list:
            if d['portfolioID']==pid: 
                status = d['status']
                if status != '5': # these status levels are set in common in react - status 5 is the light blue status - erase the light blue opportunities
                    tmp.append(d)
            else:
                tmp.append(d)
        redis_user_reports_list = tmp

        redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    return jsonify({'populate_portfolio':'success','count':len(redis_user_reports_list)})
#-----------------------------------------------------------------------------------------------------
# find d0 and d1 of days before and after current date - it has to be in YYYY-MM-DD format and weekdays
def find_weekdays_around_xdate(d,num_days):

    if datetime.datetime.strptime(d, '%Y-%m-%d').weekday() == 5 : xdate = inc_date_day(d,2) # shift saturday to monday
    elif datetime.datetime.strptime(d, '%Y-%m-%d').weekday() == 6 : xdate = inc_date_day(d,1) # shift sunday to monday
    else : xdate = d

    # Find the last 10 weekdays before xdate
    last_10_weekdays_before = []
    current_date = inc_date_day(xdate,-1)
    while len(last_10_weekdays_before) < num_days:
        if datetime.datetime.strptime(current_date, '%Y-%m-%d').weekday() < 5:  # Monday to Friday are weekdays
            last_10_weekdays_before.append(current_date)
        current_date = inc_date_day(current_date,-1)

    # Find the next 10 days after xdate
    next_10_days_after = []
    current_date = inc_date_day(xdate,1)
    while len(next_10_days_after) < num_days:
        if datetime.datetime.strptime(current_date, '%Y-%m-%d').weekday() < 5:  # Monday to Friday are weekdays
            next_10_days_after.append(current_date)
        current_date = inc_date_day(current_date,1)

    return last_10_weekdays_before, next_10_days_after
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# process portfolio is a member of Trade Automation - it creates daily portfolios based on a scan, automated portfolios are named &YYYY-MM-DD
# It also creates monthly portfolios.  if a daily portfolio is more than 1 day old, the opportunities are copied to the Monthly portfolio - the old daily portoflio is deleted
# 12/10/2023  - process portfolio - does the following:
# 1) creates a & type portfolio with name of the current day - uses info from config on what parameters to use
# 2) creates a & type portfolio with the name of the current month, if it doesn't exist
# 3) moves daily type portfolios from previous days to the monthly portfolio - deletes the day portfolio - so there should be 1 day protfolio and 1 month portfolio for today
# option parameter is used to process either today or any date
@app.route('/process_auto_portfolio/<string:auto_portfolio_date>', methods=['POST'])
@app.route('/process_auto_portfolio', methods=['POST'])
@check_for_token
def process_auto_portfolio(auto_portfolio_date='today'):    



    today_date      = datetime.datetime.now().strftime("%Y-%m-%d")
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    # first process the daily portfolios that are more than 1 or 2 days old to move to the monthly portoflio - then the daily is deleted
    portfolios_ret  = get_user_portfolio_names()
    portfolios_data = portfolios_ret.get_data(as_text=True)
    portfolios_dict = json.loads(portfolios_data)

    process_old_daily_to_monthlys(portfolios_dict['portfolio_names_list'],userid) # this line moves the date named portfolios that are older than today to monthly portfolio

    #------------------------------------------------------------------------------------------------------------
    # start on populating the auto generated folder
    # get info about all the markets to use for portfolio generation - set in config_autotrade.py
    auto_portfolio_markets      = config_autotrade.auto_portfolio_markets
    auto_portfolio_settings     = config_autotrade.auto_portfolio_settings # settings for all markets 

    # now we'll create a daily automatic portfolio based on the date passed by  
    
    process_date = auto_portfolio_date # optional parameter passed to this API call 12/14/2023

    if process_date == 'today':
        process_date = today_date
    elif process_date == 'today+1':
        process_date = inc_date_day(today_date, 1)
        wd=datetime.datetime.strptime(process_date, '%Y-%m-%d').weekday()
        if wd == 5: process_date = inc_date_day(process_date,2)
        elif wd == 6: process_date = inc_date_day(process_date,1)
    elif process_date == 'today+2':
        process_date = inc_date_day(today_date, 2)
        wd=datetime.datetime.strptime(process_date, '%Y-%m-%d').weekday()
        if wd == 5: process_date = inc_date_day(process_date,2)
        elif wd == 6: process_date = inc_date_day(process_date,1)

    #--------------------------------------------------
    action_portfolio = '&'+process_date    
    #--------------------------------------------------
    #----------------------------------------------------------------------------------------------------------------------------------------------------
    # check if action_portfolio exists - if not create one and get the portoflioID - action portfolio is typically today's portfolio
    #----------------------------------------------------------------------------------------------------------------------------------------------------

    p_id=-1
    p_name=''
    # search to see if action portfolio exists if not create it
    found = False
    for p in portfolios_dict['portfolio_names_list']:
        p_id   = p['id']
        p_name = p['name']
        if p_name == action_portfolio:
            found = True
            break
    if not found: #need to create this portoflio
        ret  = add_user_portfolio_name(action_portfolio)
        tmp  = ret.get_data(as_text=True)
        dict = json.loads(tmp)
        
        p_id=dict['new_portfolio']['id']
        p_name=action_portfolio

    # now we have a portfolio named with &process_date
    # auto populate the portoflio
    resourceID_list = auto_portfolio_markets['resourceID_list']
    years_list      = auto_portfolio_markets['years']
    pyears_list     = auto_portfolio_markets['pyears']

    # loop through the list of markets and add them to the portfolio using populate_protfolio API call
    for i in range(len(resourceID_list)):
        
        resource_id = resourceID_list[i]
        bs  = config_autotrade.auto_portfolio_settings[resource_id]
        action_date = process_date
        month_num = int(action_date[5:7])
        day = int (action_date[8:10])
        years  =  years_list[i]
        pyears =  pyears_list[i]

        min_price = bs['min_price']

        #  let vars_combined = `${id}|${monthNum}|${day}|${years}|${pyears}|${min_sr}|${avg_ret}|${min_mfe}|${day_range}|${min_mfe_pct}|${initialStatus}|${minPrice}|${min_sr2}|${avg_ret2}|${fhs}|${selectedDays}`
        vars_combined = f"{resource_id}|{month_num}|{day}|{years}|{pyears}|{bs['min_sr']}|{bs['avg_ret']}|{bs['min_mfe']}|{bs['day_range']}|{bs['min_mfe_pct']}|{bs['initial_status']}|{min_price}|{bs['min_sr2']}|{bs['avg_ret2']}|{bs['keep_highest_sr']}|{bs['days_look_forward_sr']}"
        params = base64.b64encode(vars_combined.encode()).decode()

        populate_portfolio(params,p_name,'add')

    return jsonify({'populate_portfolio':'success'})
#-----------------------------------------------------------------------------------------------------
# this function moves the content of the 1st portfolio to 2nd portoflio and deletes first protfolio
#-----------------------------------------------------------------------------------------------------
# def move_portfolio_content(portfolio1_id,portfolio2_id):
#     # get content of the first portfolio
#     print(portfolio1_id,portfolio2_id)
#-----------------------------------------------------------------------------------------------------
# this function processes all the daily portoflios by moving them to monthly after 1 or more days
#-----------------------------------------------------------------------------------------------------
def process_old_daily_to_monthlys(portfolios,userid):

    
    today_date      = datetime.datetime.now().strftime("%Y-%m-%d")
    today_date_py   = datetime.datetime.strptime(today_date, "%Y-%m-%d")

    portfolio_names_list = [p['name'] for p in portfolios] # complete list of portfolio names for this user

    redis_key_user_reports = f'user_reports_{userid}'
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)
    if redis_user_reports_list is not None:
        redis_user_reports_list = json.loads(redis_user_reports_list)

    #----------------------------------------------------------------------------------------------------------------------------------------------------
    # check if any portfolios are more than a day old.  if they are move them to their corresponding monthly portfolio and delete the daily portfolio
    # if corresponding monthly portfolio doesn't exist, create it first
    #----------------------------------------------------------------------------------------------------------------------------------------------------

    # make a subset list of portfolio names that have the pattern of '&YYYY-MM-DD'
    date_pattern = re.compile(r'^&\d{4}-\d{2}-\d{2}$')
    only_date_portfolio_names = [p for p in portfolio_names_list if date_pattern.match(p)]

    # print('portfolio_names_list=',portfolio_names_list)

    # portfolio_ids_to_delete = [] # have save the portfolios for deleteion and delete at the end
    portfolio_names_to_delete = []
    for name in only_date_portfolio_names:

        monthly_id = -1 # portfolio id for the monthly portoflio
        daily_id = get_id_from_portfolio_name(userid,name) # get the portfolio id for the portfolio_name == name
        
        # check if the name is older than today - any portfolios older than today will be moved to a monthly portoflio
        date0 = datetime.datetime.strptime(today_date, "%Y-%m-%d")
        date1 = datetime.datetime.strptime(name[1:], "%Y-%m-%d")
        days_diff = (date1-date0).days

        if days_diff < 0:  # create monthly portfolio if needed.  move the opps to the monthly protoflio and delete the daily portoflios older than 1 day 
            # save the name of the daily portfolio for deletion
            # portfolio_ids_to_delete.append(daily_id)
            portfolio_names_to_delete.append(name)

            # get the opps from the portfolio name
            # for opp in redis_user_reports_list:
            for idx, opp in enumerate(redis_user_reports_list):
                
                if opp['portfolioID'] == daily_id:  # only checking opps from this portfolio
                    opp_date = opp['date']
                    date1 = datetime.datetime.strptime(opp_date, "%Y-%m-%d")
                    days_diff = (date1-today_date_py).days

                    if days_diff < 0: # this is moving to a monthly portfolio
                    # get the corresponding monthly portfolio name or create it if not exist
                        month_name = calendar.month_name[int(opp_date[5:7])]
                        monthly_portfolio_name = f'&{month_name[0:3]} Trades'
                        # print('monthly_portfolio_name=',monthly_portfolio_name)
                        if monthly_portfolio_name not in portfolio_names_list: # create the monthly portfolio
                            ret=add_user_portfolio_name(monthly_portfolio_name)
                            tmp  = ret.get_data(as_text=True)
                            dict = json.loads(tmp)
                            monthly_id = dict['new_portfolio']['id']
                            portfolio_names_list.append(monthly_portfolio_name) # have to add it otherwise, there are duplicate poretfolios trying to be created
                        else:
                            monthly_id = get_id_from_portfolio_name(userid,monthly_portfolio_name)
                        
                        # now move content of portfolio_id=daily_id to portoflio_id=monthly_id
                        # opp['PortfolioID'] = monthly_id
                        redis_user_reports_list[idx]['portfolioID'] = monthly_id
                        
    # update redis json for the list of opps
    x=redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list))

    # delete the portfolio where portfolio_id == daily_id
    portfolio_names_to_delete = list(set(portfolio_names_to_delete)) # get rid of duplicates
    for n in portfolio_names_to_delete:
        x=del_user_portfolio_name(n)
        x=x.get_data(as_text=True)
        x=json.loads(x)
#-----------------------------------------------------------------------------------------------------
# this will use tradier api to return a list of potential credit spreads for trading
#-----------------------------------------------------------------------------------------------------
@app.route('/get_creditspreads_data/<string:opp_symbol>/<string:opp_start_date>/<int:opp_days>/<int:num_strikes>', methods=['GET'])
@check_for_token
def get_creditspreads_data(opp_symbol,opp_start_date,opp_days,num_strikes):    

    today_date      = datetime.datetime.now().strftime("%Y-%m-%d")
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    # print('opp_symbol=',opp_symbol)

    dict  = get_quotes(opp_symbol) 
    
    # print('dict in get_quotes in appserver returned ',opp_symbol,dict)
    
    # print(f"get_quotes called for {opp_symbol} price is:{dict['last']}")

    creditspreads_dict = get_creditspreads_for_opportunity(dict,opp_start_date,opp_days,num_strikes)

    selected_bullish,selected_bearish = desired_selections_bullish_bearish (creditspreads_dict)
    cs_selections = {'bullish':selected_bullish,'bearish':selected_bearish}

    # also get account info for per trade risk capital for credit spreads
    total_equity,balances_dict = get_accounting_info(config_autotrade.account_id) 
    capital_available = total_equity * config_autotrade.portion_balance # this is a fraction like 0.5 means only trade half of the account
    per_trade_capital = capital_available * config_autotrade.portion_risk_per_trade # if per_trade_capital==0 means trade minimum like 1 option contract per trade
    positions_dict    = get_positions(config_autotrade.account_id)

    return jsonify({'creditspreads_dict':creditspreads_dict,'stock_quote':dict,'capital_available':capital_available,'per_trade_capital':per_trade_capital,'auto_selection':cs_selections,'positions_dict':positions_dict})
#-----------------------------------------------------------------------------------------------------
# place new credit spread order - basically sell a bullish or bearish at the money credit spread
# when a new creditspread is sold, a new row is added to live_trades table in redis db=1
# also used to exit a position including market and conditional exits from the dialog box confirmation 
# the UI
# userid used in the saved data is passed from the UI during manual placing of a creditspread

# possible 4 types of order can be placed
# 1) new creditspread open trade: this order will place a new credit spread trade
# 2) new creditspread close trade: this order places a new close trade
# 3) update creditspread close trade: 
#    a) changes parameters of custom exit 
#    b) updates standing trade exit for the position with tradier
# 4) market exit order: could be manual or machine triggered.  
#    a) updates exit_trigger to manual_market or 
#    b) updates exit_tigger to any of the other custom exit types that triggered the exit



#-----------------------------------------------------------------------------------------------------
@app.route('/place_creditspread_order', methods=['POST'])
@check_for_token
def place_creditspread_order():   

    incoming_data = request.json 
    data = incoming_data.copy() # data is mostly formed properly for sending for order placment


    # do this later 6/17/2024 - routing works but need to add an override so that accidental duplications don't place
    # multiple of the same exact orders
    # check if the incoming_data is a duplicate - 
    # is_duplicate=check_is_trade_duplicate(data)

    

    # if is_duplicate:
    #     return jsonify({'return_status':status_code,'order_status':order_status,'order_id':order_id,'message':message})

    

    # check if order_type is:

    # 1) new_creditspread_open
    # 2) new_creditspread_close
    # 3) update_creditspread_close
    # 4) creditspread_close_market





    new_order = True
    live_trade_dict = get_live_order(data['dr_id']) # this function will retrieve an order from live_trades with this dr_id
                                                    # if it didn't exist, an empty dictionary is returned

    # SEC-H2 - if the dr_id maps to an existing live_trade row, verify that
    # row is owned by the authenticated user before allowing a re-price /
    # modification. Without this filter any authenticated user could pass
    # another user's dr_id in the JSON body and modify the co-tenant's
    # pending Tradier order in the shared autotrade account. New-order
    # path (live_trade_dict == {}) is unaffected since no other user's
    # state is referenced.
    if live_trade_dict != {}:
        token_h2 = request.args.get("token")
        jwt_data_h2 = jwt.decode(
            token_h2, app.config['SECRET_KEY'],
            algorithms=['HS256'],
            audience='tw2-appserver',
            issuer='tw2-web',
        )
        jwt_userid_h2 = str(jwt_data_h2['user'])
        owner_userid = str(live_trade_dict.get('userid'))
        if owner_userid != jwt_userid_h2:
            logging.warning(
                "place_creditspread_order: ownership check failed user=%s "
                "dr_id=%s owner=%s ip=%s ua=%s",
                jwt_userid_h2, data.get('dr_id'), owner_userid,
                request.headers.get("X-Forwarded-For", request.remote_addr),
                request.headers.get("User-Agent", "-"),
            )
            return jsonify({
                'return_status': 403,
                'order_status': 'forbidden',
                'order_id': -1,
                'message': 'order not owned by user',
            }), 403

    if live_trade_dict != {}:
        order_id  = live_trade_dict['open_order_id'] # made a change from close_order_id to open_order_id 8/30/2024
        price     = data['price']
        new_order = False


    print('live_trade_dict=',live_trade_dict)

    print('\ndata coming to place_creditspread_order =',data)
    # update_live_trades_list(incoming_data)
    # return ({})

    dr_id  = data['dr_id'] 
    del data['dr_id']      # remove to make sure data has only the needed keys for order placement
    for k in custom_exit_fields: # remove all the custom fields to place an order with tradier
        data.pop(k,None)

    # print('after place_creditspread_order:data input =',data)

    if new_order == True:
        status_code,json_response = place_multileg_option_trade(data,config_autotrade.account_id)
    else: # this is a modification of an existing order
        status_code,json_response = update_multileg_option_order(order_id,config_autotrade.account_id,price)

    print('place_creditspread_order json_response output =',json_response,status_code)

    if 'errors' in json_response:
        # print(json_response,status_code)
        order_status = 'error'
        message = json_response['errors']['error'][0]
        order_id = -1
    else:

        order_status = json_response['order']['status']
        order_id = json_response['order']['id']
        message = 'No Errors from brokerage'
        print('order_status=',order_status)

        # save the order_id in the report json for the opp
        if new_order == True:
            save_order_id(order_id,dr_id)

        # check if this is a new open position trade.  if new position, add a row to the table live_trades in redis db=1
        if '_to_open' in data['side[0]'] and order_status == 'ok' and order_id != -1: # its a new trade being opened 
            # print('checking ',data['side[0]'])
            incoming_data['order_id']   = order_id # adding the new order_id to the dictionary before saving it in live_trades
            incoming_data['account_id'] = config_autotrade.account_id
            add_new_trade_to_live_trades_list(incoming_data)

        elif '_to_close' in data['side[0]']: # main information that needs to be added is order_id_close
            incoming_data['order_id'] = order_id
            incoming_data['trigger_close']= 'manual'
            update_live_trades_list(incoming_data)

    # pprint(json_response)

    return jsonify({'return_status':status_code,'order_status':order_status,'order_id':order_id,'message':message})
#-----------------------------------------------------------------------------------------------------
# checks if the trade data is the same as an existing live trade - if identical return True
#-----------------------------------------------------------------------------------------------------
def check_is_trade_duplicate(data):
    
    # only compare the following keys and disregard the rest of the keys
    keys_to_compare = ['class','symbol','type','price','option_symbol[0]','side[0]','quantity[0]','option_symbol[1]','side[1]','quantity[1]','dr_id']

    json = redis_client1.get('live_trades') #db=1 is for autotrading 

    if json is None:
        return False
    
    # create a dataframe from live_trades key in redis db=1
    df = pd.read_json(json)
    # create a subset dictionary from incoming data
    data_c = {key: data.get(key) for key in keys_to_compare}

    for i,r in df.iterrows():
        data_r = {key: r.to_dict().get(key) for key in keys_to_compare} # same keys for comparison to see if the row is in live_trades already
        
        # print('\n data_r=',data_r,'\n data_c=',data_c)
        
        if data_r == data_c: # this is a duplicate
            return True

    return False # didn't find a duplicate in live_trades
# #-----------------------------------------------------------------------------------------------------
# # create new entry in live trade list in redis db=1
# # happens when a order is first placed 
# #-----------------------------------------------------------------------------------------------------
def add_new_trade_to_live_trades_list(tdata):
    
    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    print('adding new trade to the live list\n')
    # print('data=',data)

    q0 = int(tdata['quantity[0]'])  # make the quantity negative if its a sell_to_open
    if tdata['side[0]'] == 'sell_to_open':q0=-q0
    q1 = int(tdata['quantity[1]'])
    if tdata['side[1]'] == 'sell_to_open':q1=-q1

    if '_to_open' in tdata['side[0]'] : # selling a new creditspread
        print('tdata=',tdata)
        #----------------------------------------------------------------------------------------
        # create the dictionary of data for a new creditspread trade
        # this data is added and updated in live_trades.  
        # when trade is completed and position fully exited, it is added to trades_archive 
        #----------------------------------------------------------------------------------------
        cs_trade_data = {
            'userid': userid, # userid for all the synchronous open operations - async needs userid in config_autotrade
            'account_id': tdata['account_id'],
            'dr_id': tdata['dr_id'],
            'trade_id': '', # assigned when archived
            'trade_type': 'creditspread',
            'trigger_open': 'manual', # when this is automated, set it to auto
            'open_date': '', # assigned when open order is filled
            'trigger_close': '', # manual_market, stock_profit, option_profit, option_gain_after_days, days_before_expiration, wave_end, excercised 
            'close_date': '',
            'symbol': tdata['symbol'], #security symbol
            'security_price_open':'', # assigned on 
            'security_price_close':'',
            'option0_symbol': tdata['option_symbol[0]'],
            'option1_symbol': tdata['option_symbol[1]'],
            'option0_open_quantity': q0, # options that are sold are designated as negative quantity
            'option1_open_quantity': q1, 
            'option0_close_quantity': 0, # quantity of closed options.  trade is complete when open and close quantities match
            'option1_close_quantity': 0,
            'option0_open_price': '',
            'option1_open_price': '',
            'option0_close_price': '',
            'option1_close_price': '',
            'price_open': '',
            'price_close': '',
            'status': '', # this is status of the order.  open, filled, expired, canceled - cancel and expired deletes from live_trades
            #-- exit_ are parameters for the exit dialog on tradewave
            'exitStockGain': '',
            'exitOptionGain': '',
            'daysAfter': '',
            'daysAfterGain': '',
            'daysBefore': 0,
            'waveEndAction': '',
            'earlyExcerciseAction': '',
            #--------------------------------------------------------
            'open_order_id': tdata['order_id'],
            'close_order_id': '', # assigned as soon as there is an exit order
            # 'position_id': '', # I don't think I need it
            'close_order_type':'',  # this is for exit - values : market, limit, stop, stop_limit, trailing_stop
            'extra_info': ''
        }

        redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

        if redis_live_trades is not None:
            live_trades = json.loads(redis_live_trades)
            live_trades.append(cs_trade_data)
        else:
            live_trades = [cs_trade_data] # make it a list of dictionaries

        # update_live_symbols(live_trades) # current symbols are published to be used by stream_quote in autotrade_async
        
        redis_client1.set('live_trades', json.dumps(live_trades))
#-----------------------------------------------------------------------------------------------------
# get the conditional order from live_trades by dr_id
#-----------------------------------------------------------------------------------------------------
def get_live_order(dr_id):


    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 
    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)
        for r in live_trades:
            if r['dr_id'] == dr_id: # found it
                return r
    return {}

#-----------------------------------------------------------------------------------------------------
# this routine is called when a conditional exit order is set or updated
# adds close_order_id to the live_trades db=1
#-----------------------------------------------------------------------------------------------------
def update_live_trades_list(tdata):

    print('\n tdata from update_live_trades_list=',tdata)

    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        dr_id = tdata['dr_id']
        for r in live_trades:
            if r['dr_id'] == dr_id: # found it


                # del r['exit_stock_profit']
                # del r['exit_option_profit']
                # del r['exit_after_days']
                # del r['exit_after_days_option_gain']
                # del r['exit_before_expiration_days']
                # del r['exit_wave_end']
                # del r['exit_early_excercise']

                r['close_order_id']       = tdata['order_id']
                r['trigger_close']        = tdata['trigger_close']

                r['exitStockGain']        = tdata['exitStockGain']
                r['exitOptionGain']       = tdata['exitOptionGain']
                r['daysAfter']            = tdata['daysAfter']
                r['daysAfterGain']        = tdata['daysAfterGain']
                r['daysBefore']           = tdata['daysBefore']
                r['waveEndAction']        = tdata['waveEndAction']
                r['earlyExcerciseAction'] = tdata['earlyExcerciseAction']
                break
        redis_client1.set('live_trades', json.dumps(live_trades))
#-----------------------------------------------------------------------------------------------------
# remove entry from live trades list in redis db=1
# this should only run for:
# 1) opening order for a trade is canceled before it is filled
# 2) closing order for a trade is successful. trade should be archived and removed from 
#    live_trades list.
#-----------------------------------------------------------------------------------------------------
def remove_order_from_live_trades_list(order_id):
    
    print('removing trade from the live list\n')

    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

    rows_remove = 0

    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)
        if any(trade['open_order_id'] == order_id for trade in live_trades):  # make sure this order exist before removing it
            before_num = len(live_trades)
            live_trades = [order for order in live_trades if order['open_order_id'] != order_id] # remove entry with 'order_id' == order_id
            after_num = len(live_trades)
            # update_live_symbols(live_trades) # current symbols are published to be used by stream_quote in autotrade_async
            if before_num - after_num > 0:
                redis_client1.set('live_trades', json.dumps(live_trades))
                return before_num - after_num # should return 1 when working correctly
            else:
                return 0
        else: 
            return -1 # order_id wasn't found in live_trades
    else:
        return -2 # shows why return was an error - there wasn't a redis_live_trades in db=1

# #------------------------------------------------------------------------------------------------------
# # update current symbols from live_trades key in redis and publish for consumption by stream_quotes
# #------------------------------------------------------------------------------------------------------
# def update_live_symbols(redis_live_trades):

#     symbols = []

#     if redis_live_trades is not None:
#         # live_trades = json.loads(redis_live_trades)

#         for t in redis_live_trades:
#             symbols.append(t['symbol'])
#             symbols.append(t['option_symbol[0]'])
#             symbols.append(t['option_symbol[1]'])

#         symbols = list(set(symbols)) # get rid of duplicate symbols
#         redis_client1.set('live_symbols',json.dumps(symbols))
#         # also write the timestamp when the live_symbols changed - used to know when to update the symbols in autotrade_async
#         redis_client1.set('live_symbols_timestamp',int(time.time()))

#     return symbols
#-----------------------------------------------------------------------------------------------------
# cancel a credit spread or other types of trade orders
#-----------------------------------------------------------------------------------------------------
@app.route('/cancel_placed_order', methods=['POST'])
@check_for_token
def cancel_placed_order():

    data = request.json  # this is for POST
    order_id = data['order_id']

    # SEC-H1 - verify the order belongs to the authenticated user before
    # cancelling. The autotrade brokerage account is shared across all
    # users, so without this check any authenticated user could pass an
    # arbitrary order_id and cancel another user's pending Tradier order.
    token = request.args.get("token")
    jwt_data = jwt.decode(
        token, app.config['SECRET_KEY'],
        algorithms=['HS256'],
        audience='tw2-appserver',
        issuer='tw2-web',
    )
    jwt_userid = str(jwt_data['user'])

    redis_live_trades = redis_client1.get('live_trades')  # db=1 is for autotrading
    matching_trade = None
    if redis_live_trades is not None:
        live_trades_check = json.loads(redis_live_trades)
        for t in live_trades_check:
            if t.get('open_order_id') == order_id and str(t.get('userid')) == jwt_userid:
                matching_trade = t
                break

    if matching_trade is None:
        logging.warning(
            "cancel_placed_order: ownership check failed user=%s order_id=%s ip=%s ua=%s",
            jwt_userid, order_id,
            request.headers.get("X-Forwarded-For", request.remote_addr),
            request.headers.get("User-Agent", "-"),
        )
        return jsonify({'response': {'error': 'forbidden'}, 'message': 'order not owned by user'}), 403

    json_response = cancel_order(order_id,config_autotrade.account_id)

    # print('jjjjjjjjjjjjjjjjjj',type(json_response),json_response)

    # also remove the trade and symbol from live_trades and live_symbols keys in dp=1
    remove_order_from_live_trades_list(order_id)

    return jsonify({'response':json_response})
#-----------------------------------------------------------------------------------------------------
# this function saves the order_id in the user_reports_##### key 
#-----------------------------------------------------------------------------------------------------
def save_order_id(order_id,dr_id):

    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    # print('save_order_id  order_id, dr_id=',order_id,dr_id)

    redis_key_user_reports  = f'user_reports_{userid}'
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    if redis_user_reports_list is None:
        return 'error opportunity list for this user is empty!'

    # load the list
    redis_user_reports_list = json.loads(redis_user_reports_list)
    # find index of dr_id
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id)]




    i=-1
    if len(idx)==1:idx=idx[0] # there should not be more than 1 result for the idx search
    # now we have the index of the opportunity to update
    # check if there is a key named orders first - if not create it
    # print('idx=',idx)
    # print('redis_user_reports_list')
    # pprint(redis_user_reports_list)

    if 'orders' in redis_user_reports_list[idx]:
        orders = redis_user_reports_list[idx]['orders']
        orders = orders + ',' + str(order_id)
    else:
        orders = str(order_id) # order_id is the order coming from brokerage after order placement
    # update or create the key 'orders'  - this is saving all orders for this opportunity placed with brokerage
    # print('idx=',idx)
    # print(redis_user_reports_list)
    # print('orders=',orders,type(orders))
    # print('order_id=',order_id,type(order_id))
    # print('redis_user_reports_list[idx]=',redis_user_reports_list)
    redis_user_reports_list[idx]['orders']=orders
    # set the opp list to the new listed after updating the num_shares
    redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

    # for o in redis_user_reports_list:
    #     print(o)
    #     print('')

    return 'ok'
#-----------------------------------------------------------------------------------------------------
# get all the orders from the brokerage
#-----------------------------------------------------------------------------------------------------
@app.route('/get_trade_orders', methods=['GET'])
@check_for_token
def get_trade_orders():   

    json_response=get_orders(config_autotrade.account_id)
    # print(type(json_response))


    if type(json_response) == dict: # when orders are only 1 - the dictionary is returned, otherwise a list of dict - fixing it here
        json_response = [json_response] 

    # positions_dict    = get_positions(config_autotrade.account_id)

    return jsonify({'orders':json_response})

#-----------------------------------------------------------------------------------------------------
# get all the orders from the brokerage
#-----------------------------------------------------------------------------------------------------
@app.route('/get_positions_for_dr_id/<int:dr_id>', methods=['GET'])
@check_for_token
def get_positions_for_dr_id(dr_id):   


    token           = request.args.get("token")
    data            = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'], audience='tw2-appserver', issuer='tw2-web')
    userid          = data['user']

    redis_key_user_reports  = f'user_reports_{userid}'
    redis_user_reports_list = redis_client2.get(redis_key_user_reports)

    if redis_user_reports_list is None:
        return jsonify({'error':'redis_user_reports_list has not been created yet'})

    redis_user_reports_list = json.loads(redis_user_reports_list)
    # find index of dr_id
    idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id)]
    if len(idx) == 1:idx=idx[0]
 
    positions_lst = []
    if 'orders' in redis_user_reports_list[idx]: 

        orders_str = redis_user_reports_list[idx]['orders']
        orders_lst = orders_str.split(',')
        orders_lst.reverse()  # now last order is on top at index 0


        positions = get_positions(config_autotrade.account_id) # positions from brokerage

        # print('ppppppppppppppppppppostions=',positions)c

        for o in orders_lst: # checking each order_number if its filled check for positions
            if o == '':continue
            order_dict    = get_one_order(config_autotrade.account_id,o)
            # print('\n\n order_dict=',order_dict)
            position_dict = get_position_from_filled_order(order_dict,positions)
            if position_dict:
                # get custom_exit_fields from live_trades
                custom_exit_dict = get_custom_exit_fields(position_dict['order_id'])
                position_dict['custom_exit_fields'] = custom_exit_dict 
                positions_lst.append(position_dict)

    # print('positions_lst=',positions_lst)
        
    return jsonify({'positions':positions_lst})
#-----------------------------------------------------------------------------------------------------
# return the custom exit fields from live_trades
# custom exit fields are mixed with the data used to send order to tradier.  tradier doesn't seem
# to have an issue when extra fields are send 
#-----------------------------------------------------------------------------------------------------
def get_custom_exit_fields(order_id):

    redis_live_trades = redis_client1.get('live_trades') #db=1 is for autotrading 

    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        # custom_exit_fields = ['exit_stock_profit','exit_option_profit','exit_after_days','exit_after_days_option_gain','exit_before_expiration_days','exit_wave_end','exit_early_excercise']
        # changed custom fields names to names used in react app
        # custom_exit_fields =['exitStockGain','exitOptionGain', 'daysAfter' ,'daysAfterGain', 'daysBefore','waveEndAction','earlyExcerciseAction']


        for trade in live_trades:
            if trade['open_order_id'] == order_id:
                custom_exit_dict = {key: trade[key] for key in custom_exit_fields}
                return custom_exit_dict
        
    return {}  # didn't find the order_id    

#-----------------------------------------------------------------------------------------------------
# get quote(s) from the brokerage - 1 symbol returns dict - >1 symbols return list of dicts
#-----------------------------------------------------------------------------------------------------
@app.route('/get_quotes_brokerage/<string:symbols>', methods=['GET'])
@check_for_token
def get_quotes_brokerage(symbols):   

    json_response=get_quotes(symbols)

    # pprint(json_response[2])

    return jsonify({'quotes':json_response})
#-----------------------------------------------------------------------------------------------------
# get quote(s) from the brokerage - 1 symbol returns dict - >1 symbols return list of dicts
#-----------------------------------------------------------------------------------------------------
@app.route('/get_trading_clock', methods=['GET'])
@check_for_token
def get_trading_clock():   

    json_response=get_brokerage_clock()

    market_open_state = 'false'

    if json_response['state'] == 'open':
        market_open_state = 'true'

    return jsonify({'market_open_state':market_open_state})
#-----------------------------------------------------------------------------------------------------
# place exit order for creditspread
#-----------------------------------------------------------------------------------------------------
@app.route('/exit_creditspread_order', methods=['POST'])
@check_for_token
def exit_creditspread_order():   

    data = request.json # data is already formed properly for sending for order placment

    num_contracts    = data['num_contracts'   ] 
    stock_profit     = data['stock_profit'    ]  
    stock_loss       = data['stock_loss'      ] 
    options_profit   = data['options_profit'  ] 
    options_loss     = data['options_loss'    ] 
    after_days       = data['after_days'      ] 
    after_gain       = data['after_gain'      ] 
    expire_exit_days = data['expire_exit_days'] 
    order_type       = data['order_type'      ] 
    dr_id            = data['dr_id'           ]            

    # print('stock_loss=',stock_loss)

    #--------------------------------------------
    # if order type is market, place market order
    #--------------------------------------------


    #--------------------------------------------
    # place OCO exit as follows:
    #--------------------------------------------
    # place profit exit order with gain of options_profit
    
    # place stop-loss order with loss of options_loss

    #--------------------------------------------
    # place async exits based on other criteria
    #--------------------------------------------
    # place stock profit exit order with stock gain of stock_profit
    # when criteria is true, modify option exit to market


    # place stock loss exit order with stock loss of stock_loss
    # when criteria is true, modify option exit to market


    # place option exit order expire_exit_days before expiration
    # when true, modify option exit to market

    # if after_days is today, replace/modify option_profit profit order to a gain of after_gain



    return jsonify({'status':'ok'})
#-----------------------------------------------------------------------------------------------------
# place conditional exit order for creditspread
#-----------------------------------------------------------------------------------------------------
@app.route('/exit_creditspread_conditional', methods=['POST'])
@check_for_token
def exit_creditspread_conditional():   

    data = request.json # data is already formed properly for sending for order placment

    print('exit_creditspread_conditional = ', data)
#-----------------------------------------------------------------------------------------------------
# get conditional exit order parameters from live_trades
#-----------------------------------------------------------------------------------------------------
@app.route('/get_conditional_exit_parameters', methods=['GET'])
@check_for_token
def get_conditional_exit_parameters(order_id):   


    custom_exit_fields = get_custom_exit_fields(order_id)

    # redis_key_live_trades = 'live_trades' # user saved opportunities database - 
    # live_trades_redis = redis_client1.get(redis_key_live_trades)
    # live_trades = []
    # if redis_user_reports_list is not None:
    #     live_trades = json.loads(redis_key_live_trades)

    #     print('live_trades=',live_trades)

    #     custom_parameters = {}

    return jsonify({'status':'ok','custom_exit_fields':custom_exit_fields})

#-----------------------------------------------------------------------------------------------------
# set conditional exit order parameters in live_trades
#-----------------------------------------------------------------------------------------------------
# @app.route('/set_conditional_exit_parameters', methods=['POST'])
# @check_for_token
def set_conditional_exit_parameters(data):   

    # data = request.json # data is already formed properly for sending for order placment
    order_id = data['order_id']

    # print('set_conditional_exit_parameters = ', data)

    new_custom_exit_fields = data['custom_exit_fields']
    redis_key_live_trades = 'live_trades' # user saved opportunities database - 
    redis_live_trades = redis_client1.get(redis_key_live_trades) #db=1 is for autotrading 
    
    if redis_live_trades is not None:
        live_trades = json.loads(redis_live_trades)

        for trade in live_trades:
            if trade['open_order_id'] == order_id:
                trade.update(new_custom_exit_fields)
                return jsonify({'status':'ok','trade':trade} ) 
                break


    return jsonify({'status':'not found'} ) 

#-----------------------------------------------------------------------------------------------------
# Risk Profile calculation
#-----------------------------------------------------------------------------------------------------
@app.route('/risk_profile', methods=['POST'])
@check_for_token
def risk_profile():   

    data = request.json # data is already formed properly for sending for order placment

    int_rate = config.free_return / 100 # interest_rate
    S = 90 # underlying price
    strike_price = 100 # strike price
    time_to_expire = 22/365 # 250 days to expiration
    sigma = 0.30 # volitility 

    data['int_rate'] = int_rate

    # print('data=',data)

    data1 = {
        'current_stock_price' : S,
        'int_rate'            : int_rate,
        'strike_price0'       : strike_price,
        'time_to_expire0'     : time_to_expire,
        'sigma0'              : sigma,
        'type0'               : 'P',
        'long_or_short0'      : 'long',
        'strike_price1'       : 105,
        'time_to_expire1'     : time_to_expire,
        'sigma1'              : sigma,
        'type1'               : 'P',
        'long_or_short1'      : 'short',
        'debit_or_credit'     : 2.67         
    }
 
    num_contracts = data['num_contracts']
    del data['num_contracts']

    spread = abs(data['strike_price0']-data['strike_price1'])    
    
    stock_price_range , option_values0_current , option_values0_exp , option_values1_current , option_values1_exp = get_option_prices_for_group_options(data)

    credit = data['debit_or_credit']
    
    option_values_current = [(a - b  + credit) * 100 * num_contracts for a, b in zip(option_values0_current, option_values1_current)]
    option_values_exp     = [(a - b  + credit) * 100 * num_contracts for a, b in zip(option_values0_exp, option_values1_exp)]


    # print('riskprofile ',{'status':'ok','cs_exp':option_values_exp,'cs_current':option_values_current,'cs_labels':stock_price_range})
    # print('\n\n\n\n')

    return jsonify({'status':'ok','cs_exp':option_values_exp,'cs_current':option_values_current,'cs_labels':stock_price_range})
    # return jsonify({'status':'ok','cs_exp':option_values0_exp,'cs_current':option_values0_current,'cs_labels':stock_price_range})

#-----------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    # get available resources by loading all the symbol csv files in the root of data
    app.run(host='0.0.0.0', debug=True)