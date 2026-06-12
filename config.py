import os  # for env-loaded secrets — see /etc/tradewave/secrets.env

WORKOS_CLIENT_ID = os.environ.get('WORKOS_CLIENT_ID', '')  # set in /etc/tradewave/secrets.env (per-env: staging vs prod client)
WORKOS_API_KEY   = os.environ.get('WORKOS_API_KEY', '')  # set in /etc/tradewave/secrets.env
WORKOS_COOKIE_PASSWORD = os.environ.get('WORKOS_COOKIE_PASSWORD', '')  # set in /etc/tradewave/secrets.env
WORKOS_AUTHKIT_DOMAIN  = os.environ.get('WORKOS_AUTHKIT_DOMAIN', '')  # set in /etc/tradewave/secrets.env (per-env hosted UI domain)


STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')  # set in /etc/tradewave/secrets.env
STRIPE_SECRET_KEY      = os.environ.get('STRIPE_SECRET_KEY', '')  # set in /etc/tradewave/secrets.env
STRIPE_WEBHOOK_SECRET  = os.environ.get('STRIPE_WEBHOOK_SECRET', '')  # set in /etc/tradewave/secrets.env


# === DATABASE (TW2) ===
POSTGRES_DSN = os.environ.get('POSTGRES_DSN', '')  # set in /etc/tradewave/secrets.env

# === KEYPROVIDER (TW2) ===
SERVICE_API_KEY = os.environ.get('SERVICE_API_KEY', '')  # set in /etc/tradewave/secrets.env

# === APPSERVER (TW2) ===
APPSERVER_JWT_SECRET = os.environ.get('APPSERVER_JWT_SECRET', '')  # set in /etc/tradewave/secrets.env

# === TARA -> API GATEWAY (TW2) ===
# The in-product assistant (Tara) calls the v1 API gateway as a client (see
# docs/TARA_GATEWAY_INTEGRATION.md). PER-ENV base URL (dev :8088, staging/prod the gateway's
# own host) + the chatbot-tier service key (api_keys row, tier 'chatbot'). Both from secrets.env.
TARA_GATEWAY_URL = os.environ.get('TW2_GATEWAY_URL', '')  # e.g. http://127.0.0.1:8088/v1 (dev); set in /etc/tradewave/secrets.env
TARA_GATEWAY_KEY = os.environ.get('TARA_GATEWAY_KEY', '')  # chatbot service key; set in /etc/tradewave/secrets.env

# HMAC secret for users.api_key_hash lookup. The appserver and the
# db_admin backfill MUST agree, or every login_api will 403. If
# API_KEY_HMAC_SECRET is unset (transition default), fall back to
# APPSERVER_JWT_SECRET (same shared-secret model the JWT path uses).
API_KEY_HMAC_SECRET = os.environ.get('API_KEY_HMAC_SECRET', '') or APPSERVER_JWT_SECRET

# Gate for the in-web API/MCP customer console (/account/api). The API/MCP product
# ships "dark" on prod: the console only registers when TW2_API_CONSOLE_ENABLED is
# truthy (set on dev/staging). Unset (prod default) => /account/api is not exposed.
# The API gateway + MCP server are separate services, not provisioned on prod.
API_CONSOLE_ENABLED = os.environ.get('TW2_API_CONSOLE_ENABLED', '').strip().lower() in ('1', 'true', 'yes')

# === AFFILIATE PROGRAM (TW2) ===
# Form-prefill defaults for the Flask-Admin Affiliates tab (env-agnostic; NOT
# secrets). These mirror the public/advertised terms on the /affiliate page;
# each affiliate's actual discount/commission is still set per-row in admin.
AFFILIATE_DEFAULT_DISCOUNT_PCT = 20
AFFILIATE_DEFAULT_COMMISSION_PCT = 30

# === STRIPE (TW2) ===
# Get test keys from Stripe dashboard → Developers → API keys (toggle test mode)
# Get from Stripe dashboard → Webhooks → Add endpoint (won't work until cloudflared tunnel is set up)
# Create 4 Products in Stripe dashboard, copy each Price ID


# this is for seasonal chart / trend chart file cache folder 12/17/2024
cache_folder='/home/flask/appserver/appserver/trend_chart_cache/'
##########################################################################################################################
# promotions shown on the wave viewer for users that are not logged-in
##########################################################################################################################
upgrade_message = 'Unlock the Full Power of TradeWave! Get complete access to all opportunities and premium features by upgrading now.'
upgrade_message = '''
📘 Get Early Access to My New Book
The 100-Year Prophecy explains the exact seasonal patterns powering TradeWave—
and you can read it before it’s released.
'''
upgrade_message = ''
# Per-LEVEL override of upgrade_message, keyed by the numeric legacy level the
# appserver login() gates on. Falls back to the global upgrade_message above
# for levels not listed, so paid levels stay clean. Level '1' = post-reverse-
# trial Explorer (DJ30 only since 2026-06-10); reverse-trial users mint
# level-'6' claims, so they never see this while the trial is active.
upgrade_message_by_level = {
    # State-agnostic on purpose: existing free accounts never had a reverse trial
# (reverse_trial_ends_at NULL), so 'your trial has ended' would be false for
# them. One truthful line covers both the post-trial and never-trialed cases.
    '1': 'You are on the free Explorer plan (DJ30). Upgrade to unlock all 15 markets.',
}
# promotion message is shown below the upgrade_message - it could be a coupon code or a discount message 0 - blank will remove it
promotion_message = '🎉 Get 60% OFF Tidal Subscription - first 100 subscribers' 
promotion_message = ''
promotion_coupon_code = 'SAVE60'
promotion_back_color  = 'orange'


TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY', '')  # set in /etc/tradewave/secrets.env
GROK_API_KEY = os.environ.get('GROK_API_KEY', '')  # set in /etc/tradewave/secrets.env
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN', '')  # set in /etc/tradewave/secrets.env
PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY', '')  # set in /etc/tradewave/secrets.env
OPENAI_KEY = os.environ.get('OPENAI_KEY', '')  # set in /etc/tradewave/secrets.env
EOD_token = os.environ.get('EOD_TOKEN', '')  # set in /etc/tradewave/secrets.env
anthropic_token = os.environ.get('ANTHROPIC_TOKEN', '')  # set in /etc/tradewave/secrets.env

# Publer settings for X posts
PUBLER_API_KEY = os.environ.get('PUBLER_API_KEY', '')  # set in /etc/tradewave/secrets.env
PUBLER_WORKSPACE_ID = os.environ.get('PUBLER_WORKSPACE_ID', '')  # set in /etc/tradewave/secrets.env (per-env workspace)
PUBLER_X_ACCOUNT_ID = os.environ.get('PUBLER_X_ACCOUNT_ID', '')  # set in /etc/tradewave/secrets.env (per-env X account)

#------------------------------------------
# facebook API variables
#------------------------------------------
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID', '')  # set in /etc/tradewave/secrets.env (per-env FB app)
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET', '')  # set in /etc/tradewave/secrets.env
# the long lived token expires on July 4, 2023
FACEBOOK_ACCESS_TOKEN  = os.environ.get('FACEBOOK_ACCESS_TOKEN', '')  # set in /etc/tradewave/secrets.env
# this is the main page of the TradeWave group
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID', '')  # set in /etc/tradewave/secrets.env (per-env FB page)
# Per-market FB page IDs. JSON-encoded in env (so prod can override per env).
# Format: {"0": 105060032587168, "1": 108908498866288, ...}
import json as _json_for_fbpages
_FACEBOOK_OPP_PAGES_JSON = os.environ.get('FACEBOOK_OPP_PAGES_JSON', '').strip()
if _FACEBOOK_OPP_PAGES_JSON:
    _decoded = _json_for_fbpages.loads(_FACEBOOK_OPP_PAGES_JSON)
    # JSON keys are strings — preserve TW1 contract that keys are ints.
    FACEBOOK_OPP_PAGES = {int(k): v for k, v in _decoded.items()}
else:
    FACEBOOK_OPP_PAGES = {}

# following needed to run blog_queue on dev
# staging blog username set as author
username = os.environ.get('TW2_WORDPRESS_USERNAME', '')  # set in /etc/tradewave/secrets.env (per-env WP author)
password = os.environ.get('WORDPRESS_APP_PASSWORD', '')  # set in /etc/tradewave/secrets.env
appserver_ip = os.environ.get('TW2_APPSERVER_IP', '')  # set in /etc/tradewave/secrets.env (redis host in appserver)
webserver_ip = os.environ.get('TW2_WEBSERVER_IP', '')  # set in /etc/tradewave/secrets.env (redis host in webserver)
articles_redis_db = 3
##########################################################################################################################
# NOTE (2026-05-21 cleanup): the useUMP flag (WordPress Ultimate Membership Pro login
# mode) was removed here as a never-used leftover, along with its dead consumers in
# the appserver - TW2 gates access via the signed LTK JWT in the appserver login(),
# so the UMP branches were dead code.

ml_scorer_url = os.environ.get('TW2_ML_SCORER_URL', '')  # set in /etc/tradewave/secrets.env (ML pattern scorer on keyprovider)
x_profile_url = os.environ.get('TW2_X_PROFILE_URL', '')  # set in /etc/tradewave/secrets.env (X/Twitter profile per env)

# === CONTACT FORM / TIER-1 SUPPORT ===
# Cloudflare Turnstile (captcha) - per-env site/secret pair. On dev, use the
# Turnstile test keys (1x00000000000000000000AA + 1x0000000000000000000000000000000AA)
# which always pass; on staging/prod use real keys from the CF Turnstile dashboard.
TURNSTILE_SITE_KEY   = os.environ.get('TURNSTILE_SITE_KEY', '')    # public, embedded in /contact.html
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')  # server-side verify only

# Resend (transactional email). Single account; per-env API key so dev tickets
# don't blast out from the same key as prod. Empty/PLACEHOLDER => fail silently
# in email_utils (the ticket still lands in Postgres).
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')

# Where contact-form notifications land. SUPPORT_EMAIL_TO is the inbox we
# read; SUPPORT_EMAIL_FROM is the verified sender on the Resend side (DKIM/SPF
# configured on the FROM domain). tradewave.ai is now verified in Resend, so we
# send as help@tradewave.ai (the old notifications@trxstat.com default pointed at
# an UNVERIFIED domain -> Resend would reject it). Override per-env in secrets.env.
SUPPORT_EMAIL_TO   = os.environ.get('SUPPORT_EMAIL_TO',   'help@tradewave.ai')
SUPPORT_EMAIL_FROM = os.environ.get('SUPPORT_EMAIL_FROM', 'TradeWave <help@tradewave.ai>')

# Salt for ip_hash on support_tickets. NEVER reuse across envs - rotating it
# breaks lookup of historical ips, which is the whole point (no PII drift).
SUPPORT_IP_HASH_SALT = os.environ.get('SUPPORT_IP_HASH_SALT', '')

##########################################################################################################################

# === PUBLIC HOST (single source of truth) ===
# Exactly one public, browser-facing root per environment, and it is always a
# domain (never a LAN IP):
#     dev    -> tw2-dev.trxstat.com
#     stage  -> tw2-stage.trxstat.com
#     prod   -> tw2-prod.trxstat.com
# Set via TW2_PUBLIC_HOST in /etc/tradewave/secrets.env. This drives every
# user-facing absolute URL: the /app/ auth + logout return_to, the home-page
# canonical / OG / JSON-LD tags, email-newsletter links, and the article /
# wave-viewer links.
_tw2_public_host = os.environ.get('TW2_PUBLIC_HOST', '').strip().rstrip('/')
tw2_public_url = f'https://{_tw2_public_host}/' if _tw2_public_host else 'https://tw2-dev.trxstat.com/'

# domain_root is an ALIAS of tw2_public_url, retained for the ~30 existing call
# sites that still reference it. It used to be a separate TW2_DOMAIN_ROOT env var
# which on dev held a LAN IP (http://192.168.1.176/); that leaked the private host
# into canonical / OG / email URLs and forced strip-out hacks in the page
# generators. There is no LAN-IP requirement - every environment has a real domain
# - so the two names now resolve to a single value. TW2_DOMAIN_ROOT is retired and
# can be removed from secrets.env.
domain_root = tw2_public_url

# Coarse environment label, used to gate per-env behaviour at runtime (the same
# React build ships to every env, so this can't be a build-time switch). app.py
# injects it as window.tw2_env into the /app/ shell.
#
# Prefer an explicit TW2_ENV (set per box in secrets.env) so this survives a
# hostname change like the eventual tradewave.ai prod cutover. Fall back to
# inferring from the public host so an unset/typo'd box still degrades sensibly
# (and so dev/local works with no extra config).
_tw2_env_explicit = os.environ.get('TW2_ENV', '').strip().lower()
if _tw2_env_explicit in ('dev', 'staging', 'prod'):
    tw2_env = _tw2_env_explicit
elif 'tw2-prod' in _tw2_public_host:
    tw2_env = 'prod'
elif 'tw2-stage' in _tw2_public_host:
    tw2_env = 'staging'
else:
    tw2_env = 'dev'  # tw2-dev + local/ad-hoc default

active_days = 5 # number of look back days to find active opportunities for the active list

alias_symbols = {'GSPC':'SPX','SPX':'GSPC'} # this is the change GSPC to SPX 10/20/2022

trading_days_search_highest_sr = 14 # number of trading days before and after the current days to search for highest sr - used in autotrading

# autotrade strategies - minimum profit is based on risk capital

auto_trade_strategies = {
    'Credit Spread':{
        'description':'Credit Spread',
        'option_strikes': 4,   # this means 4 options above and 4 options below the security price
        'early_exercise': 'close', # 3 possiblities 1)close : close the position, 2) replace :sell stock and replace the short put  3)covered_call : convert to covered call  
        'minimum_credit': 0.5,          # minimum credit to take - no less
        'minimum_profit': 0.25,         # minimum profit before closing - hopefully more
        'wave_end'      : 'break_even', # 'break_even or Close' after wave ends, set to break even + commision - 
        'close_days_before_expiration'    : 7       # if position has not been closed, close 7 days before expiration with a loss
    },
    # 'Covered Call':{
    #     'description':'Covered Call',
    #     'minimum_credit':0.5,
    #     'minimum_profit':0.5,
    # }
}

# permission for special users: - its hardcoded in Common.js in react app right now
userlist_amp = [ # permission to create folder names starting with & which is required for populate_portfolio and auto_trading
  '1',
  '22',
  '16'
]
userlist_auto = [ # must have this permission to be able to auto trade - icons for auto trading and portfolio trading reports only show for these users
  '1',
  '22',
  '16'
]

admin_userids = ['1', '16', '22']  # users who can create/manage published securities lists

# ML Score columns in the opportunity table (ml_score, win_prob, pred_return, pred_mfe).
# These columns appear only for US stocks and ETF markets (resource IDs 0-4, 11).
#
# ml_score_access_mode controls who sees ML columns:
#   'list'  - only the user IDs in ml_score_userids see them (start here for limited rollout)
#   'level' - any user whose level is in ml_score_access_levels sees them (for broader rollout)
#
# All logged-in tiers see ML columns: Explorer(1) + Analyst(4/5) + Strategist(6/7).
# (Was Strategist-only ['6','7']; opened to everyone 2026-06-10.)
ml_score_access_mode = 'level'
ml_score_userids = ['1', '16', '22']        # specific user IDs with ML score access (used only when mode='list')
ml_score_access_levels = ['1', '4', '5', '6', '7']   # Explorer + Analyst + Strategist (all logged-in tiers)
ml_score_resource_ids = ['0', '1', '2', '3', '4', '11']  # US stocks + ETFs only

home_stocks_json = "/home/flask/blog/home_stocks.json"  # this is for home page creation

earnings_calendar_file = '/home/flask/appserver/appserver/earnings_calendar.csv'

# EDGAR earnings date service — per-ticker JSON files with historical + projected earnings dates
edgar_folder = '/home/flask/edgar/'
edgar_earnings_folder = '/home/flask/edgar/earnings/'
edgar_service_url = os.environ.get('TW2_EDGAR_SERVICE_URL', '')  # set in /etc/tradewave/secrets.env (EDGAR service URL)

# Real-time price service — proactive bulk price fetch from EODHD, served via HTTP
realtime_service_url = os.environ.get('TW2_REALTIME_SERVICE_URL', '')  # set in /etc/tradewave/secrets.env (per-env real-time price service)

# number of hours a session is valid after logging in
session_expiration_hours = 24

# some symbols are no longer getting updated.  we'll drop them when loading opp_list 
drop_symbols_by_market = {

 '5':  ['CEX','MSCIWORLD'],  # indices common
 '6':  ['CEX','MSCIWORLD']  # indices all

}

# today_top10_data   = '/home/flask/blog/logs/today_top10_data.hdf'


initial_shares = 10 # 10 shares for each new opportunity

# blog generation section

category_report            = 29
category_top10             = 30
category_opp_top10         = 38
category_top10_archive     = 39
category_date_range_report = 40 # user generated date range report
ARTICLE_CATEGORY = 40

# blog_queue_server    = 'http://10.0.0.81:7171/' # this is the flask service on the same server as wordpress
blog_queue_server      = os.environ.get('TW2_BLOG_QUEUE_SERVER', '')  # set in /etc/tradewave/secrets.env (per-env blog queue)
# blog_queue_server      = 'localhost:5001/'
NEWS_QUEUE_NAME = "news_article_queue"

initial_reports_slug = 'report-processing'  # this is the initial slug for a page telling users the report is not done yet

mailerlite_token = os.environ.get('MAILERLITE_TOKEN', '')  # set in /etc/tradewave/secrets.env

num_opps_per_portfolio = 4 # this is the maximum opportunites that can be added to each portfolio

# Per-level limits — mirror PRODUCTION TW1 config (dev was never accurate).
# Active levels: '1'=Ripple/Explorer, '4'/'5'=PRO/Analyst, '6'/'7'=Institutional/Strategist.
num_opp_reports_allowed_by_level = { # total date-range reports a user can ever publish
    '0': 0,
    '1': 5,
    '4': 100,
    '5': 100,
    '6': 500,
    '7': 500,
}
num_daily_opp_reports_allowed_by_level = { # per-day publish cap
    '0': 0,
    '1': 10,
    '4': 100,
    '5': 100,
    '6': 500,
    '7': 500,
}
num_portfolios_allowed_by_level = { # main default counts as 1; non-registered get 0
    '0': 0,
    '1': 1,
    '4': 25,
    '5': 25,
    '6': 100,
    '7': 100,
}
num_watchlists_allowed_by_level = {
    '0': 0,
    '1': 0,  # aligned to TIER_FEATURES['explorer'] watchlists_max (2026-06-10 reverse-trial close)
    '4': 10,
    '5': 10,
    '6': 50,
    '7': 50,
}
num_watchlist_items_allowed_by_level = {
    '0': 0,
    '1': 0,  # aligned to TIER_FEATURES['explorer'] watchlist_symbols_max (2026-06-10 reverse-trial close)
    '4': 50,
    '5': 50,
    '6': 100,
    '7': 100,
}

# appserver_url        = 'http://192.168.1.151:8001'
appserver_url        = os.environ.get('TW2_APPSERVER_URL', '')  # set in /etc/tradewave/secrets.env (per-env appserver URL)

tw_favicon     = '/favicon.png'  # served from /var/www/tradewave/favicon.png
smn_favicon    = os.environ.get('TW2_SMN_FAVICON_URL', '')  # set in /etc/tradewave/secrets.env (per-env favicon URL)
article_favicon = os.environ.get('TW2_ARTICLE_FAVICON_URL', '')  # set in /etc/tradewave/secrets.env (per-env article favicon URL)
smn_from_name  = 'Seasonal Market News'
smn_from_email = 'info@tradewave.ai'  # update to seasonalmarketnews.com address when available

# SEO configuration
# Production only: emits OG tags, JSON-LD, GA, sitemap, robots.txt AND pings
# IndexNow (submits URLs to Bing/Yandex). Derived from tw2_env so dev + staging
# are never indexable - the same code runs on every box, so this MUST key off the
# runtime env, not be hardcoded.
seo_enabled = (tw2_env == 'prod')

# Google Analytics GA4 measurement ID ('G-XXXXXXXXXX'). Env-driven so only prod
# (which sets TW2_GA_MEASUREMENT_ID in its secrets.env) tracks; empty default
# leaves dev + staging untracked.
ga_measurement_id = os.environ.get('TW2_GA_MEASUREMENT_ID', '')

# IndexNow API key — notifies Bing, Yandex, Naver on every article publish.
# This key must match the verification file at {news_root_folder}/{indexnow_key}.txt
# Per-env value (treated as a key/secret). Generate once with: uuid.uuid4().hex
indexnow_key = os.environ.get('INDEXNOW_KEY', '')  # set in /etc/tradewave/secrets.env

# OG image for homepage/site-wide social sharing (1200x630 recommended)
# Place the image at the news web root, e.g. /var/www/smn/smn-og-image.jpg
smn_og_image = '/assets/smn-og-image.jpg'


# folder locations
web_root_dir = '/var/www/tradewave/'  # TW2: marketing site root
news_root_folder = '/var/www/smn/'
articles_subfolder   = 'articles'
article_images_folder = news_root_folder
# new addition for news url to be different if needed
# so news could be on a subdirctory from the root like tradewave.ai/news - that the root
# or coudl be somewhere else like seasonalmarketnews.com - whcih could be a website on the same server
# in dev to simulte a second wesbite I use 192.168.1.151:9000
# in staging to simulate a second website I use smn.trxstat.com
# in production the second website is set to be SeasonalMarketNews.com
news_website_url = os.environ.get('TW2_NEWS_WEBSITE_URL', '')  # set in /etc/tradewave/secrets.env (per-env news site)





csv_folder = '/home/flask/data/csv/' # csvs have a subfolder for each exchange and are defined by exchange_mapping
daily_video_users = '' # this is a special users that looks like not logged-in but can change date - this is for daily video maker to change date
                       # and create top 10 video ahead of time 

# when master_appserver is used, this appserver will fetch the data from the master_appserver
# if master_appserver is blank, this appserver fetches the data from local files
# initial attempt is for all functions that use historical data in the csv folder
# later update will add opportunity data also

master_appserver   = os.environ.get('TW2_MASTER_APPSERVER', '')  # set in /etc/tradewave/secrets.env (per-env master appserver)
update_server      = os.environ.get('TW2_UPDATE_SERVER', '')  # set in /etc/tradewave/secrets.env (per-env update server)

ddir               = '/home/flask/data/'
wordpress_url      = os.environ.get('TW2_WORDPRESS_URL', '')  # set in /etc/tradewave/secrets.env (per-env WP URL)

# WordPress REST endpoints — derived from wordpress_url. Used by smn/blog_tools.py,
# smn/create_report.py, smn/generate_top10_sr.py, smn/set_redirect.py,
# site/lib/blog_tools.py. If wordpress_url is empty (TW2 has no WordPress in that
# env), these become empty strings — callers that exercise these paths will fail
# with a clear connection error rather than AttributeError.
_wp_base             = wordpress_url.rstrip('/') + '/' if wordpress_url else ''
post_endpoint_url    = (_wp_base + 'wp-json/wp/v2/posts') if _wp_base else ''
tags_endpoint_url    = (_wp_base + 'wp-json/wp/v2/tags') if _wp_base else ''
redirect_endpoint_url = (_wp_base + 'wp-json/redirection/v1/') if _wp_base else ''

#logcollector_url  = 'http://192.168.1.151:7676/' # when there is a value, every API activity will be logged in this server
logcollector_url   = os.environ.get('TW2_LOGCOLLECTOR_URL', '')  # set in /etc/tradewave/secrets.env (per-env log collector)
# set TW2_LOGCOLLECTOR_URL='' to turn off log collector

stockscore_url = os.environ.get('TW2_STOCKSCORE_URL', '')  # set in /etc/tradewave/secrets.env (per-env stockscore service)


# allow for non logged-in users to see limited content:
noLoginContent = True

# keystore URL
keystoreURL = os.environ.get('TW2_KEYSTORE_URL', '')  # set in /etc/tradewave/secrets.env (per-env keystore URL)

#############################################################################
# update available resources names and path when additional content is added
# update available_resources,available_resources_path,level_access_hierarchy
available_resources = {
    '0': 'DOW 30 STOCKS',
    '1': 'NASDAQ 100 STOCKS',
    '2': 'S&P 500 STOCKS',
    '3': 'RUSSELL 1000 STOCKS',
    '4': 'WILSHIRE 5000',
    '5': 'INDICES COMMON',
    '6': 'INDICES ALL',
    '7': 'FUTURES & COMMODITIES',
    '8': 'FOREX ALL',
    '9': 'FOREX LIQUID',
    '10': 'GOVERNMENT BONDS',
    '11': 'ETFs',

    '12': 'LONDON EXCHANGE',
    '13': 'TORONTO STOCKS',

    '16': 'CRYPTO CURRENCIES'
    
}

available_resources_path = {
    '0': '/home/flask/data/dj30_symbols.csv',
    '1': '/home/flask/data/nasdaq100_symbols.csv',
    '2': '/home/flask/data/sp500_symbols.csv',
    '3': '/home/flask/data/rus1000_symbols.csv',
    '4': '/home/flask/data/wilshire5000_symbols.csv',
    '5': '/home/flask/data/INDX_COMMON_symbols.csv',
    '6': '/home/flask/data/INDX_USA_symbols.csv',
    '7': '/home/flask/data/COMM_symbols.csv',
    '8': '/home/flask/data/FOREX_symbols.csv',
    '9': '/home/flask/data/FOREX_LQ_symbols.csv',
    '10': '/home/flask/data/GBOND_symbols.csv',
    '11': '/home/flask/data/ETF_symbols.csv',

    '12': '/home/flask/data/LSE_symbols.csv',
    '13': '/home/flask/data/TO_symbols.csv',

    '16': '/home/flask/data/CC_symbols.csv'
}


exchange_mapping={ # exchange mapping is used for EOD downloads - left is folder name, right is the exchange name for use with EOD download
    '0':'US',
    '1':'US',
    '2':'US',
    '3':'US',
    '4':'US',
    '5':'INDX',
    '6':'INDX',
    '7':'COMM',
    '8':'FOREX',
    '9':'FOREX',
    '10':'GBOND',
    '11':'ETF',

    '12':'LSE',
    '13':'TO',

    '16':'CC'
}

# Membership-level → resource access. Mirrors PRODUCTION TW1 (dev was never accurate).
# Two-tier paid model: 4/5 = PRO (Analyst in TW2), 6/7 = Institutional (Strategist in TW2).
# tier_compat.py maps explorer→'1', analyst→'4', strategist→'6'.
#
# Three dicts work together:
#   _free_registered[lvl] = visible in dropdown but DATE LOCKED, can't type symbol
#   _premium[lvl]         = visible + full features (date unlocked, symbol typing)
#   level_access_hierarchy[lvl] = backend opp-list filter (which markets the
#                                  appserver will actually return data for)
# Frontend dropdown = (free ∪ premium); they are disjoint per level by design.

level_access_hierarchy_free_registered = {
    '1': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],   # Ripple sees all 15, all date-locked
    '4': ['5','6','7','8','9','10','12','13','16'],                            # PRO: indices/futures/forex/bonds/foreign/crypto are date-locked
    '5': ['5','6','7','8','9','10','12','13','16'],
    '6': [],                                                                              # Institutional: no free markets — all premium
    '7': [],
}
level_access_hierarchy_premium = {
    '1': [],                                                                              # Ripple: no premium
    '4': ['0','1','2','3','4','11'],                                                     # PRO: US stocks (DOW/NASDAQ/S&P/Russell/Wilshire) + ETFs
    '5': ['0','1','2','3','4','11'],
    '6': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],   # Institutional: everything
    '7': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],
}
# Backend opp-list filter (also drives /login resource_disp + token lid).
# REVERSE-TRIAL DECISION (Afshin, 2026-06-10, supersedes the 2026-05-18 launch
# open-paywall): level '1' (free Explorer) is DJ30 only ('0'). New signups get
# the full Strategist experience for 7 days via the reverse trial (web/app.py
# effective_tier mints level-'6' claims while users.reverse_trial_ends_at is in
# the future), then fall back here. Paired with the React default-security
# fallback fix (App.js falls back to the first accessible security when the
# hard-coded/cookied selection is not in resource_disp), so a DJ30-only list
# no longer blanks the opp table.
level_access_hierarchy = {
    '1': ['0'],
    '4': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],
    '5': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],
    '6': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],
    '7': ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16'],
}

admin_levels        = ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16']  # admins see everything
non_loggedin_levels = ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16']  # anonymous-visible resource list


#############################################################################
## rate-limit for each API - windows are [per-second, per-minute, per-hour, per-day]
## Since 2026-06 the appserver limiter keys data endpoints PER-USER (token user
## id; see appserver.py tw_rate_limit_key) - IP keying behind the Cloudflare
## tunnel + the web-box nginx proxy collapsed everyone onto 1-2 IPs (chronic
## prod 429s). Absolute counts MUST ascend second < minute < hour < day: the old
## 1500/minute > 1000/hour inversion made the tiny hour cap the real limit.
## Data-limit sizing: one React page load fires a parallel burst per endpoint
## family; a power user hard-refreshing 3-4 full loads/minute must never 429.
## rate_limit_login stays IP-keyed (anonymous path) and in prod that bucket is
## SHARED by all users - sized for the whole user base (see appserver.py note).
rate_limit_login           = ['50/second' ,'300/minute' ,'3000/hour','20000/day']
rate_limit_opp             = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_chartData4      = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_YearsMetaData   = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_ChartHistorical = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_stockscore      = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_general         = ['100/second','600/minute' ,'6000/hour','40000/day']
rate_limit_spbd            = ['100/second','2000/minute','5000/hour','50000/day']
rate_limit_mlscore         = ['100/second','600/minute' ,'6000/hour','40000/day']



#############################################################################
## redis expiration in seconds
opp_expire_time            = 51       # of seconds
chart_data_expire_time     = 51
years_metadata_expire_time = 51
history_expire_time        = 51
stock_metadata_expire_time = 51
stockscore_expire_time     = 51
stocklastprice_expire_time = 51
seasonal_chart_expire_time = 51
spbd_static_expire_time    = 993600  # 11.5 days - Security Price By Date (historical prices never change)
opp_by_symbol_expire_time  = 3600   # 1 hour - opp_by_symbol data changes only when analytics re-runs
spdd_active_expire_time    = 20160  # 5.6 hours - end date price for active trades (updates daily)
stockscore_daily_expire_time = 86400  # 24 hours - batch stockscore for opp table (daily granularity)




max_opportunities_returned     = 5000
max_opportunities_not_loggedin = 3   # mirrors prod
max_opportunities_loggedin_free = 5  # Explorer/Ripple per-query cap



free_return = 4.0  # use 3 month treasury bill yield in % - changed it to 4% from 1.5% starting jan 1, 2023
min_required_years = 5 # this is the minimum required years of data for a security to do seasonal analytics on tradewave
max_days_missing   = 14 # maximum number of days missing from data before its considered not traded

# === TIER MATRIX (TW2) ===
# Source of truth for tier capabilities. Used by:
#  - Pricing page (/pricing) when rendered from this dict (future polish)
#  - Web tier when rendering the React app (decides what UI controls to show)
#  - Appserver (when refactored to read tier directly instead of legacy WP level)
# Existing TW1 num_*_by_level dicts above remain authoritative for the
# legacy code paths in appserver.py until that refactor is done. The
# tier_compat shim in /home/flask/web/tier_compat.py maps tier names to
# the WP numeric level IDs the legacy code expects.
TIER_FEATURES = {
    'explorer': {
        'name':                       'Explorer',
        'monthly_price_launch':       0,
        'yearly_price_launch':        0,
        'monthly_price_post':         0,
        'resources_allowed':          [0],   # DJ30 only
        'top_patterns_per_market':    5,
        'change_start_date':          False,
        'pe_cycle_overlay_only':      True,
        'pe_cycle_filter_manual':     False,
        'pe_cycle_filter_auto':       False,
        'ml_scoring':                 False,
        'portfolios_max':             1,
        'tracked_opportunities_max':  5,
        'watchlists_max':             0,
        'watchlist_symbols_max':      0,
        'smn_articles':               False,
        'webinar_access':             False,
        'support_channel':            'community',
    },
    'analyst': {
        'name':                       'Analyst',
        'monthly_price_launch':       47,
        'yearly_price_launch':        37,
        'monthly_price_post':         58,
        'resources_allowed':          [0,1,2,3,4,5,6,11],
        'top_patterns_per_market':    100,
        'change_start_date':          True,
        'pe_cycle_filter_manual':     True,
        'pe_cycle_filter_auto':       False,
        'ml_scoring':                 True,
        'portfolios_max':             25,
        'tracked_opportunities_max':  100,
        'watchlists_max':             5,
        'watchlist_symbols_max':      50,
        'smn_articles':               True,
        'webinar_access':             'qa_weekly',
        'support_channel':            'email',
        'trial_days':                 7,
    },
    'strategist': {
        'name':                       'Strategist',
        'monthly_price_launch':       149,
        'yearly_price_launch':        99,
        'monthly_price_post':         199,
        'resources_allowed':          'all',
        'top_patterns_per_market':    500,
        'change_start_date':          True,
        'pe_cycle_filter_manual':     True,
        'pe_cycle_filter_auto':       True,
        'ml_scoring':                 True,
        'portfolios_max':             100,
        'tracked_opportunities_max':  500,
        'watchlists_max':             50,
        'watchlist_symbols_max':      500,
        'smn_articles':               True,
        'webinar_access':             'zoom_weekly',
        'support_channel':            'premium',
        'trial_days':                 7,
    },
}

# Roles whose users bypass tier gating entirely (treated as having all access)
ROLE_BYPASSES_TIER = {'super_admin', 'staff_admin', 'service_account'}

# === MONITORING (added by Agent A) ===
# Sentry SDK is installed in the venv (sentry-sdk[flask]). Agents E (web) and F
# (appserver) are responsible for wiring sentry_sdk.init() into their app boot.
SENTRY_DSN = os.environ.get('SENTRY_DSN', '')  # set in /etc/tradewave/secrets.env

# === EMAIL / NEWSLETTER (added by Agent E) ===
# Mailerlite list-add hook fires on new user creation in /home/flask/web/app.py
# (lazy_create_user). Both keys must be set for the hook to fire; otherwise
# email_utils.mailerlite_subscribe() returns False fast.
# The connect-API credential. Historically only MAILERLITE_TOKEN was populated in
# secrets.env (a long API token that works as a Bearer token against connect.mailerlite.com);
# MAILERLITE_API_KEY was never set, so the signup list-add + level-group sync silently
# no-op'd. Fall back to MAILERLITE_TOKEN so the existing credential is actually used. (Set a
# dedicated MAILERLITE_API_KEY in secrets.env later if you want to rotate them independently.)
MAILERLITE_API_KEY  = os.environ.get('MAILERLITE_API_KEY', '') or os.environ.get('MAILERLITE_TOKEN', '')  # set in /etc/tradewave/secrets.env
MAILERLITE_GROUP_ID = os.environ.get('MAILERLITE_GROUP_ID', '')  # set in /etc/tradewave/secrets.env

# Mailerlite LEVEL groups (one MailerLite account across envs, so these IDs are
# stable identifiers, not per-env secrets - replicates TW1/UMP's "level -> group"
# auto-sync). Keyed by tier for free, "tier_period" for paid. email_utils.
# sync_mailerlite_level_group() keeps each subscriber in exactly their current
# level group. If a value is '' the sync skips that slot. (IDs confirmed live 2026-05-25.)
MAILERLITE_LEVEL_GROUPS = {
    'explorer':           '97426012986410777',
    'analyst_monthly':    '97426054440814482',
    'analyst_yearly':     '97426062589298035',
    'strategist_monthly': '97426069052720199',
    'strategist_yearly':  '97426077579740921',
}
