#!/usr/bin/env python3
"""
TradeWave Homepage Generator
Generates a homepage from CSV opportunities data + live stockscore data.

Usage:
    python generate_home_page.py
"""

import argparse
import csv
import json
import requests
import base64
import shutil
import time
import traceback
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from jinja2 import Environment, FileSystemLoader
import os
import sys
sys.path.insert(0, '/home/flask')
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent / 'lib'))
import config
import portal_urls  # per-env developer-portal URL for the footer link

from daily_pattern_picks import get_daily_picks
from blog_tools import get_company_name, convert_param_base64
from get_price_eod import get_quote_details
from ga_snippet import ga_head_snippet
from pick_stats import (
    compute_win_rate, compute_target_hit_rate, compute_held_to_close_rate, compute_median_result_return, is_resolved, is_win,
)  # shared win definition (homepage + scorecard must never diverge)

# Stripe price lookup (TW2: prices come live from Stripe via PRODUCT METADATA,
# exactly like web/app.py _refresh_price_cache: a price is used ONLY if its
# product carries product_line == "eod", tier in {analyst,strategist}, and
# period in {monthly,yearly}. Name-substring matching was REMOVED - the shared
# Stripe account holds legacy UMP / placeholder / RT prices that name-collide.
# Returns: {tier}_monthly, {tier}_yearly (per-month equiv), {tier}_yearly_daily, {tier}_yearly_savings
#
# A wrong price on the homepage is worse than a stale page, so if the Stripe
# fetch fails (or any of the 4 tier/period slots is missing) the generator
# refuses to publish fallback prices unless --allow-price-fallback was passed.
ALLOW_PRICE_FALLBACK = False  # set by main() from --allow-price-fallback

def _price_fallback_or_die(reason, fallback):
    """LOUD stderr warning; exit nonzero unless --allow-price-fallback."""
    print("=" * 70, file=sys.stderr)
    print("   ERROR: Stripe price lookup unusable: %s" % reason, file=sys.stderr)
    if not ALLOW_PRICE_FALLBACK:
        print("   REFUSING to publish hardcoded fallback prices (a stale page "
              "beats a wrong-price page).", file=sys.stderr)
        print("   Re-run with --allow-price-fallback to override.", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)
    print("   --allow-price-fallback passed: publishing hardcoded fallback "
          "prices (verify they are still current!).", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    return fallback

def _stripe_prices():
    fallback = {
        'navigator_monthly':          '$19',
        'navigator_yearly':           '$14',
        'navigator_yearly_daily':     '$0.46/day',
        'navigator_yearly_savings':   'Save 26%',
        'analyst_monthly':            '$47',
        'analyst_yearly':             '$33.25',
        'analyst_yearly_daily':       '$1.09/day',
        'analyst_yearly_savings':     'Save 29%',
        'strategist_monthly':         '$129',
        'strategist_yearly':          '$99',
        'strategist_yearly_daily':    '$3.25/day',
        'strategist_yearly_savings':  'Save 23%',
        'max_yearly_savings':         'Save up to 30%',
    }
    if not config.STRIPE_SECRET_KEY or 'PLACEHOLDER' in config.STRIPE_SECRET_KEY:
        return _price_fallback_or_die('STRIPE_SECRET_KEY missing or placeholder', fallback)
    try:
        import stripe
        stripe.api_key = config.STRIPE_SECRET_KEY
        valid_tiers = ('navigator', 'analyst', 'strategist')
        valid_periods = ('monthly', 'yearly')
        cents_by_key = {}
        ids_by_key = {}
        for p in stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter():
            prod = p.product
            if not isinstance(prod, dict):
                prod = prod.to_dict() if hasattr(prod, "to_dict") else dict(prod)
            metadata = prod.get('metadata') or {}
            md_line = (metadata.get('product_line') or '').strip().lower()
            md_tier = (metadata.get('tier') or '').strip().lower()
            md_period = (metadata.get('period') or '').strip().lower()
            if md_line != 'eod' or md_tier not in valid_tiers or md_period not in valid_periods:
                continue  # legacy / RT / placeholder / unscoped price - ignore
            ids_by_key.setdefault((md_tier, md_period), []).append(p.id)
            cents_by_key[(md_tier, md_period)] = p.unit_amount or 0

        missing = [(t, per) for t in valid_tiers for per in valid_periods
                   if not cents_by_key.get((t, per))]
        if missing:
            return _price_fallback_or_die(
                'missing EOD price slots %s (need product metadata '
                'product_line=eod + tier + period on each)' % missing, fallback)

        # A slot with >1 active price is ambiguous: which one wins is
        # pagination-order luck, and the displayed price could diverge from
        # what checkout charges. Refuse to publish until the extras are
        # archived in Stripe.
        dupes = {k: v for k, v in ids_by_key.items() if len(v) > 1}
        if dupes:
            return _price_fallback_or_die(
                'AMBIGUOUS price slots %s - more than one ACTIVE Stripe price '
                'matches the same product metadata; archive the extras in '
                'Stripe so display cannot diverge from checkout' % dupes, fallback)

        out = dict(fallback)
        savings_pcts = []
        for tier in valid_tiers:
            mo = cents_by_key[(tier, 'monthly')]
            yr = cents_by_key[(tier, 'yearly')]
            raw_pct = (mo * 12 - yr) / (mo * 12) * 100
            if not (1000 <= mo <= 100000) or not (0 <= raw_pct <= 70):
                return _price_fallback_or_die(
                    '%s prices implausible (monthly $%.0f, yearly $%.0f = %.0f%% '
                    'savings); check the eod-tagged prices in Stripe' % (
                        tier, mo / 100, yr / 100, raw_pct), fallback)
            out[f'{tier}_monthly'] = f"${mo // 100}"
            # Exact per-month figure - rounding $33.25 to "$33" would imply a
            # $396/yr charge when Stripe bills $399 (trust-audit critical).
            out[f'{tier}_yearly']       = ('$%.2f' % (yr / 100 / 12)).rstrip('0').rstrip('.')
            out[f'{tier}_yearly_daily'] = f"${yr / 100 / 365:.2f}/day"
            pct = round((mo * 12 - yr) / (mo * 12) * 100)
            out[f'{tier}_yearly_savings'] = f"Save {pct}%"
            savings_pcts.append(pct)
        out['max_yearly_savings'] = f"Save up to {max(savings_pcts)}%"
        return out
    except SystemExit:
        raise
    except Exception as e:
        return _price_fallback_or_die('Stripe API call failed (%s)' % e, fallback)

# =============================================================================
# CONFIGURATION - Edit these settings
# =============================================================================

# Input: CSV file with opportunities
OPPORTUNITIES_CSV = "/home/flask/site/data/home_opportunities.csv"

# Output: Where to save the generated HTML
# OUTPUT_DIR = "/var/www/html/_static/"
# OUTPUT_DIR = "/var/www/html/wordpress/_static/"  # for dev
OUTPUT_DIR = config.web_root_dir

OUTPUT_FILENAME = "home.html"

# Stockscore API for live market data
# STOCKSCORE_URL = "http://10.0.0.30:7771/"
# STOCKSCORE_URL = 'http://104.238.214.253:7771/' # for dev
STOCKSCORE_URL = config.stockscore_url

STOCKSCORE_RESOURCE_ID = 2

# Canonical domain for absolute URLs (og:url, canonical, JSON-LD).
# Driven by config.domain_root (TW2_DOMAIN_ROOT env var): per-env public root.
# Falls back to https://tw2.trxstat.com/ if unset (e.g. ad-hoc dev runs).
CANONICAL_ROOT = (config.domain_root.rstrip('/') + '/') if config.domain_root else "https://tw2.trxstat.com/"

# Internal links: use relative paths ("/") so the page works on any host
# (LAN IP, cloudflared tunnel, or prod) without baking the dev hostname
# into hrefs. Existing format strings like "%s_static/markets/..." % DOMAIN_ROOT
# now produce a leading "/" instead of "http://192.168.1.176/".
DOMAIN_ROOT = "/"

# How many opportunities to show per tab
OPPORTUNITIES_PER_TAB = 10

# Show opportunities table on the page (set to False to hide)
SHOW_OPPORTUNITIES = True

# Enable SEO tags (robots, canonical, structured data) - PROD ONLY. Dev + staging stay noindex
# (staging is a gate; we never want it or dev indexed). Env-driven so the prod build flips it on
# automatically instead of relying on a manual edit before launch.
ENABLE_SEO = os.environ.get('TW2_ENV', '').strip().lower() == 'prod'

# Gate every "inside ChatGPT and Claude" / MCP claim on this flag. The redesign
# marks that section "Preview - gates on MCP_LIVE"; until the consumer MCP+OAuth
# front door is actually live we must NOT render the hero "New" pill, the
# connect/MCP section, or the "Inside ChatGPT and Claude" chip as live. Env-driven
# (TW2_MCP_LIVE=1) so it flips on without a code edit once MCP ships.
MCP_LIVE = os.environ.get('TW2_MCP_LIVE', '').strip().lower() in ('1', 'true', 'yes')

# =============================================================================
# SIGNUP & AUTH URLs
# =============================================================================

SIGNUP_URL = "/signup"
LOGIN_URL = "/login"
LOGOUT_URL = "/logout"
DASHBOARD_URL = "/account"
UPGRADE_URL = "/pricing"
# The public developer portal (API + MCP + docs), env-resolved (dev -> developers-dev,
# prod -> developers.tradewave.ai). Surfaced in the footer so users + search engines find it.
DEVELOPERS_URL = portal_urls.PORTAL_URL

# =============================================================================
# PRICING URLs - Set these to your actual signup pages for each plan
# =============================================================================

PRICING_EXPLORER_URL = "/signup"
PRICING_NAVIGATOR_MONTHLY_URL = "/api/stripe/create-checkout?tier=navigator&period=monthly"
PRICING_NAVIGATOR_YEARLY_URL = "/api/stripe/create-checkout?tier=navigator&period=yearly"
PRICING_ANALYST_MONTHLY_URL = "/api/stripe/create-checkout?tier=analyst&period=monthly"
PRICING_ANALYST_YEARLY_URL = "/api/stripe/create-checkout?tier=analyst&period=yearly"
PRICING_STRATEGIST_MONTHLY_URL = "/api/stripe/create-checkout?tier=strategist&period=monthly"
PRICING_STRATEGIST_YEARLY_URL = "/api/stripe/create-checkout?tier=strategist&period=yearly"

# =============================================================================
# ANNE-MARIE VIDEO (self-hosted MP4)
# =============================================================================

ANNEMARIE_VIDEO_URL = "/_static/anne-marie_tradewave.mp4"
ERIN_VIDEO_URL = "/_static/erin1.mp4"

# =============================================================================
# CONTACT
# =============================================================================

CONTACT_URL = "%scontact.html" % DOMAIN_ROOT

# =============================================================================
# MARKET BAR TICKERS
# =============================================================================

MARKET_BAR_TICKERS = [
    {"label": "S&P 500",  "symbol": "GSPC", "exchange": "INDX", "slug": "sp500"},
    {"label": "DOW",      "symbol": "DJI",  "exchange": "INDX", "slug": "dow"},
    {"label": "NASDAQ",   "symbol": "IXIC", "exchange": "INDX", "slug": "nasdaq"},
    {"label": "VIX",      "symbol": "VIX",  "exchange": "INDX", "slug": "vix"},
    {"label": "CRUDE",    "symbol": "CL",   "exchange": "COMM", "slug": "crude-oil"},
    {"label": "NAT GAS",  "symbol": "NG",   "exchange": "COMM", "slug": "natural-gas"},
    {"label": "GOLD",     "symbol": "GC",   "exchange": "COMM", "slug": "gold"},
]


def build_market_bar_data():
    """Fetch quotes and build market bar items for template."""
    items = []
    for t in MARKET_BAR_TICKERS:
        quote = get_quote_details(t["symbol"], t["exchange"])
        try:
            close_val = quote.get("close") if quote else None
            price = float(close_val) if close_val not in (None, "NA", "N/A", "") else None
        except (ValueError, TypeError):
            price = None

        if price is not None:
            try:
                change_p = float(quote.get("change_p") or 0)
            except (ValueError, TypeError):
                change_p = 0
            direction = "up" if change_p >= 0 else "down"
            sign = "+" if change_p >= 0 else ""
            price_fmt = "%s" % format(price, ",.2f")
            chg_fmt = "%s%.2f%%" % (sign, change_p)
        else:
            price_fmt = ""
            chg_fmt = ""
            direction = "flat"

        items.append({
            "label": t["label"],
            "slug": t["slug"],
            "price": price_fmt,
            "change": chg_fmt,
            "direction": direction,
            "url": "%smarkets/%s.html" % (DOMAIN_ROOT, t["slug"]),
        })
    return items


# =============================================================================
# FEATURED PATTERN HISTORY
# =============================================================================

FEATURED_HISTORY_FILE = "/home/flask/site/data/featured_history.json"
FEATURED_REPEAT_DAYS = 14  # don't repeat same symbol within this many days

# ML scorer params for featured pattern selection
FEATURED_RESOURCE_IDS = ['2']       # S&P 500
FEATURED_DIRECTION = 'both'
FEATURED_DAYS_OUT_MIN = 10
FEATURED_DAYS_OUT_MAX = 30
FEATURED_MIN_AVG_RETURN = 5.0
FEATURED_MIN_WIN_PROB = 0.75

# OppList4 lookup params
FEATURED_YEARS = 10
FEATURED_MIN_PYEARS = 8

# Appserver URL for OppList4 lookups
APPSERVER_URL = config.appserver_url.rstrip('/')
APPSERVER_USERID = 16


def load_featured_history():
    """Load featured history, return list of entries."""
    if not Path(FEATURED_HISTORY_FILE).exists():
        return []
    try:
        with open(FEATURED_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_featured_history(history):
    """Save featured history to JSON file."""
    with open(FEATURED_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_recent_symbols(history, days=FEATURED_REPEAT_DAYS):
    """Get symbols featured in the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return {
        entry['symbol']
        for entry in history
        if entry.get('featured_date', '') >= cutoff
    }


def appserver_login():
    """Login to appserver and return token. Retries on transient stalls."""
    def _get(url, attempts=3, timeout=30, sleep_s=5):
        last = None
        for i in range(attempts):
            try:
                return requests.get(url, timeout=timeout).json()
            except Exception as e:
                last = e
                print("   WARN appserver call failed (%s), attempt %d/%d" % (e, i + 1, attempts))
                time.sleep(sleep_s)
        raise last

    try:
        result = _get(APPSERVER_URL + '/login/api/' + config.SERVICE_API_KEY)
        return result.get('token')

        url = APPSERVER_URL + '/login/16/7/4/5/' + kp_token
        result = _get(url)
        if 'message' in result:
            time.sleep(10)
            result = _get(url)
            if 'message' in result:
                return None
        return result['token']
    except Exception as e:
        print("   ERROR appserver login failed after retries: %s" % e)
        return None


def fetch_close_price(resource_id, symbol, target_date, token):
    """Fetch the close price for a symbol on a specific date via ChartHistorical2.

    If the exact date isn't a trading day, returns the close from the nearest
    prior trading day.  Returns float or None on failure.
    """
    # Request a small window around the target date
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    d0 = (dt - timedelta(days=5)).strftime('%Y-%m-%d')
    d1 = (dt + timedelta(days=5)).strftime('%Y-%m-%d')
    url = '%s/ChartHistorical2/%s/%s/%s/%s?token=%s' % (
        APPSERVER_URL, resource_id, symbol, d0, d1, token
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get('ChartHistorical2', [])
        # rows: [date, open, high, low, close, volume]
        # Find exact date or nearest prior
        best = None
        for row in rows:
            if row[0] <= target_date:
                best = row
        if best:
            return float(best[4])  # close price
    except Exception as e:
        print("   WARNING: ChartHistorical2 failed for %s: %s" % (symbol, e))
    return None


def lookup_years_via_opplist4(symbol, target_date, days_out, direction, token):
    """Look up the years string for a pattern via OppList4.

    Tries consecutive mode first with years=10 (pyears 10,9,8), then PE mode.
    pyears/years must be > 0.8 to be valid.
    Returns (years_str, mode) or (None, None) if not found.
    """
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    month_name = dt.strftime('%B')
    day_num = str(dt.day)

    # Determine day_range bucket
    if days_out <= 30:
        day_range = '7-30'
    elif days_out <= 60:
        day_range = '31-60'
    else:
        day_range = '61-90'

    # Direction mapping: ML scorer uses 'l'/'s', OppList4 uses 'Long'/'Short'
    dir_match = 'Long' if direction == 'l' else 'Short'

    # Valid pyears for years=10: 10, 9, 8 (all where pyears/years > 0.8)
    valid_pyears = [p for p in range(FEATURED_YEARS, 0, -1)
                    if p / FEATURED_YEARS > 0.8]

    def search_opplist(mode, pyears):
        url = '%s/OppList4/%s/%s/%s/%s/%s/%s/0/0?token=%s&mode=%s' % (
            APPSERVER_URL, FEATURED_RESOURCE_IDS[0], month_name, day_num,
            FEATURED_YEARS, pyears, day_range, token, mode
        )
        try:
            result = requests.get(url, timeout=30).json()
            for opp in result.get('OppList', []):
                # opp: [date, symbol, daysOut, direction, SR, AvgP, median, ...]
                if (isinstance(opp, list) and len(opp) > 3 and
                        opp[1] == symbol and int(opp[2]) == days_out and
                        opp[3] == dir_match):
                    return True
        except Exception as e:
            print("      WARNING: OppList4 lookup failed (%s, pyears=%s): %s" % (mode, pyears, e))
        return False

    # Try consecutive first, walking pyears from highest to lowest valid
    for pyears in valid_pyears:
        if search_opplist('cons', pyears):
            return str(FEATURED_YEARS), 'cons'

    # Try PE mode with same pyears walk
    pe_cycle = dt.year % 4
    for pyears in valid_pyears:
        if search_opplist('pe', pyears):
            return 'pe%d-%s' % (pe_cycle, FEATURED_YEARS), 'pe'

    return None, None


def select_featured_from_ml_scorer():
    """Select featured pattern using ML scorer + history dedup + OppList4 confirmation.

    Walks ML picks top-down. Skips symbols featured in last 14 days and symbols
    that can't be confirmed in OppList4 (so the wave-viewer link is always valid).

    Returns a dict with all featured pattern data, or None.
    """
    history = load_featured_history()

    # If already picked today, reuse that entry
    today_str = date.today().isoformat()
    for entry in history:
        if entry.get('featured_date') == today_str:
            print("   Reusing today's pick: %s (already selected)" % entry['symbol'])
            return entry

    recent_symbols = get_recent_symbols(history)
    if recent_symbols:
        print("   Recent featured symbols (last %d days): %s" % (
            FEATURED_REPEAT_DAYS, ', '.join(sorted(recent_symbols))))

    # Find next weekday
    today = date.today()
    if today.weekday() >= 5:
        today = today + timedelta(days=(7 - today.weekday()))
    target = today.strftime('%Y-%m-%d')

    # Get ML-scored picks
    print("   Fetching ML scorer picks for %s..." % target)
    try:
        result = get_daily_picks(
            date=target,
            resource_ids=FEATURED_RESOURCE_IDS,
            num_picks=0,
            direction=FEATURED_DIRECTION,
            days_out_min=FEATURED_DAYS_OUT_MIN,
            days_out_max=FEATURED_DAYS_OUT_MAX,
            min_avg_return=FEATURED_MIN_AVG_RETURN,
            min_win_prob=FEATURED_MIN_WIN_PROB,
        )
    except Exception as e:
        print("   WARNING: ML scorer call failed: %s" % e)
        return None

    picks = result.get('picks', [])
    if not picks:
        print("   No qualifying picks from ML scorer.")
        return None

    print("   ML scorer returned %d qualifying picks." % len(picks))

    # Login to appserver once for OppList4 lookups
    token = appserver_login()
    if token is None:
        print("   WARNING: Appserver login failed, cannot confirm patterns.")
        return None

    # Walk picks: skip recently featured, skip if OppList4 can't confirm
    resource_id = FEATURED_RESOURCE_IDS[0]
    for p in picks:
        if p['symbol'] in recent_symbols:
            continue

        print("   Trying %s (wp=%.1f%%, ml=%.1f)..." % (
            p['symbol'], p['win_prob'] * 100, p['ml_score']))

        years_str, mode = lookup_years_via_opplist4(
            p['symbol'], target, p['daysOut'], p['direction'], token
        )
        if years_str is not None:
            print("   Confirmed in OppList4: mode=%s, years=%s" % (mode, years_str))
            pick = p
            break
        else:
            print("      Not found in OppList4, skipping.")
    else:
        print("   No picks confirmed by OppList4.")
        return None

    # Get company name
    company_name = get_company_name(int(resource_id), pick['symbol']) or pick['symbol']

    # Get start price (close on pattern start date)
    start_price = fetch_close_price(resource_id, pick['symbol'], target, token)
    if start_price:
        print("   Start price for %s on %s: $%.2f" % (pick['symbol'], target, start_price))
    else:
        print("   WARNING: Could not fetch start price for %s" % pick['symbol'])

    # Build pattern_param
    pattern_param = convert_param_base64(
        resource_id, pick['symbol'], target, str(pick['daysOut']), years_str
    )
    wave_viewer_url = "/app/?o=%s" % pattern_param

    # Build history entry
    history_entry = {
        'featured_date': date.today().isoformat(),
        'symbol': pick['symbol'],
        'company_name': company_name,
        'date': target,
        'daysOut': pick['daysOut'],
        'direction': pick['direction'],
        'resource_id': resource_id,
        'mode': mode,
        'years': years_str,
        'pattern_param': pattern_param,
        'wave_viewer_url': wave_viewer_url,
        'sharpe_ratio': pick['sharpe_ratio'],
        'sharpe_ratio2': pick.get('sharpe_ratio2', pick['sharpe_ratio']),
        'avg_profit': pick['avg_profit'],
        'avg_profit2': pick.get('avg_profit2', pick['avg_profit']),
        'median_profit': pick['median_profit'],
        'ml_score': pick['ml_score'],
        'win_prob': pick['win_prob'],
        'pred_return': pick['pred_return'],
        'pred_mfe': pick['pred_mfe'],
        'p_hit_return': pick.get('p_hit_return'),
        'p_hit_mfe': pick.get('p_hit_mfe'),
        'tier': pick.get('tier'),
        'start_price': start_price,
        'end_date': (datetime.strptime(target, '%Y-%m-%d') + timedelta(days=pick['daysOut'])).strftime('%Y-%m-%d'),
        'status': 'open',
    }

    # Save to history
    history.append(history_entry)
    save_featured_history(history)
    print("   Saved to featured history (%d total entries)." % len(history))

    return history_entry


def parse_pattern_param(pattern_param):
    """Decode base64 pattern_param -> resource_id, symbol, date, days, years."""
    try:
        decoded = base64.b64decode(pattern_param).decode('utf-8')
        parts = decoded.split('|')
        return {
            'resource_id': parts[0],
            'symbol': parts[1],
            'start_date': parts[2],
            'days': int(parts[3]),
            'years': parts[4].lower(),
        }
    except Exception:
        return None


# =============================================================================
# DISPLAY ALIASES
# =============================================================================

DISPLAY_ALIASES = {
    "pe":   "Election Year",
    "pe+1": "Post-Election",
    "pe+2": "Midterm",
    "pe+3": "Pre-Election",
    "cons": "All Years",
}

# =============================================================================
# PE CYCLE CALCULATION
# =============================================================================

def get_current_pe_cycle():
    """Calculate current Presidential Election cycle year."""
    year = datetime.now().year
    offset = year % 4
    if offset == 0:
        return "pe"
    return "pe+%d" % offset

CURRENT_PE_CYCLE = get_current_pe_cycle()

def get_alias(mode):
    """Get display alias for a pattern mode (pe or cons)."""
    if mode.lower() == "pe":
        return DISPLAY_ALIASES.get(CURRENT_PE_CYCLE, CURRENT_PE_CYCLE.upper())
    return DISPLAY_ALIASES.get(mode.lower(), mode.upper())

CURRENT_PE_DISPLAY = get_alias("pe")

# =============================================================================
# TEMPLATES & THEMES
# =============================================================================

TEMPLATES_DIR = Path(__file__).parent / "templates"

ACTIVE_THEME = "dark-blue"

THEMES = {
    "dark-blue": {
        "name": "Dark Blue",
        "template": "index-dark-blue.html",
        "description": "Dark theme with blue accents (fintech style)",
    },
}

# =============================================================================
# CSV LOADING
# =============================================================================

def load_opportunities_from_csv(csv_path):
    """Load opportunities from CSV file."""
    opportunities = []

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mode_raw = row["mode"]
                opp = {
                    "symbol": row["symbol"],
                    "company_name": row["company_name"],
                    "start_date": row["start_date"],
                    "days": int(row["days"]),
                    "direction": row["direction"],
                    "sharpe_ratio": float(row["SR"]),
                    "avg_return": float(row["AvgP"]),
                    "median_return": float(row["median"]),
                    "twa": float(row["TWA"]),
                    "twr": float(row["TWR"]),
                    "day_range": row["day_range"],
                    "mode": mode_raw,
                    "mode_display": get_alias(mode_raw),
                    "pattern_param": row["pattern_param"],
                    "wave_viewer_url": "/app/?o=%s" % row['pattern_param'],
                }
                opportunities.append(opp)
        print("   Loaded %d opportunities from CSV" % len(opportunities))
    except FileNotFoundError:
        print("   ERROR: CSV not found at %s" % csv_path)
        return []
    except Exception as e:
        print("   ERROR loading CSV: %s" % e)
        return []

    return opportunities


def drop_closed_windows(opportunities, today=None):
    """STALE GUARD: drop opportunities whose trade window has already closed
    (start_date + days before today). The CSV is refreshed manually, so without
    this the 'Top Patterns' section renders months-old windows under urgency copy."""
    today = today or date.today()
    current = []
    for opp in opportunities:
        try:
            start = datetime.strptime(opp["start_date"], "%Y-%m-%d").date()
        except ValueError:
            print("   WARN stale-table guard: dropping %s (bad start_date %r)"
                  % (opp.get("symbol"), opp.get("start_date")), file=sys.stderr)
            continue
        if start + timedelta(days=opp["days"]) >= today:
            current.append(opp)
    dropped = len(opportunities) - len(current)
    if dropped:
        print("   WARN stale-table guard: dropped %d row(s) whose trade window "
              "already closed (CSV: %s)." % (dropped, OPPORTUNITIES_CSV),
              file=sys.stderr)
    return current

# =============================================================================
# STOCKSCORE API
# =============================================================================

def fetch_stockscore_data(symbol):
    """Fetch live market data from stockscore API."""
    url = "%sstockta/%d/%s" % (STOCKSCORE_URL, STOCKSCORE_RESOURCE_ID, symbol)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        return {
            "price": data["price"]["current"],
            "price_change_1d": data["price_changes"].get("1d"),
            "week_52_position": data["week_52"]["range_position_pct"],
            "week_52_high": data["week_52"]["high"],
            "week_52_low": data["week_52"]["low"],
            "sma_50": data["moving_averages"].get("sma50"),
            "sma_200": data["moving_averages"].get("sma200"),
            "rsi": data["momentum"]["rsi_14"],
            "long_score": data["scores"]["long"],
            "short_score": data["scores"]["short"],
        }
    except requests.RequestException as e:
        print("      Warning: Stockscore API failed for %s: %s" % (symbol, e))
        return None
    except (KeyError, TypeError) as e:
        print("      Warning: Invalid stockscore response for %s: %s" % (symbol, e))
        return None

def enrich_with_stockscore(opportunities):
    """Add live market data to each opportunity."""
    print("   Fetching stockscore data for %d symbols..." % len(opportunities))

    for opp in opportunities:
        stockscore = fetch_stockscore_data(opp["symbol"])

        if stockscore:
            opp["price"] = stockscore["price"]
            opp["price_change_1d"] = stockscore["price_change_1d"]
            opp["week_52_position"] = stockscore["week_52_position"]
            opp["has_live_data"] = True

            sma_50 = stockscore.get("sma_50")
            if sma_50 and sma_50.get("value"):
                opp["above_sma_50"] = sma_50.get("above", False)
            else:
                opp["above_sma_50"] = None
        else:
            opp["price"] = 0.0
            opp["price_change_1d"] = None
            opp["week_52_position"] = 50.0
            opp["above_sma_50"] = None
            opp["has_live_data"] = False

    return opportunities

# =============================================================================
# GROUP BY DAY RANGE
# =============================================================================

def group_by_day_range(opportunities, limit_per_tab=10):
    """Group opportunities by day_range for tabs."""
    short_term = []
    medium_term = []

    for opp in opportunities:
        day_range = opp.get("day_range", "")

        try:
            start = datetime.strptime(opp["start_date"], "%Y-%m-%d")
            end = start + timedelta(days=opp["days"])
            opp["start_date_formatted"] = start.strftime("%b %d")
            opp["end_date_formatted"] = end.strftime("%b %d")
            opp["days_until_start"] = (start - datetime.now()).days
        except Exception:
            opp["start_date_formatted"] = opp["start_date"]
            opp["end_date_formatted"] = ""
            opp["days_until_start"] = 0

        if day_range == "7-30":
            short_term.append(opp)
        elif day_range == "31-60":
            medium_term.append(opp)

    short_term.sort(key=lambda x: x["start_date"])
    medium_term.sort(key=lambda x: x["start_date"])

    return {
        "short_term": {
            "label": "1-4 Weeks",
            "sublabel": "Quick Plays",
            "count": len(short_term),
            "opportunities": short_term[:limit_per_tab],
        },
        "medium_term": {
            "label": "1-2 Months",
            "sublabel": "Position Trades",
            "count": len(medium_term),
            "opportunities": medium_term[:limit_per_tab],
        },
    }

# =============================================================================
# HTML GENERATION
# =============================================================================

def compute_homepage_scorecard_stats():
    """Compute scorecard stats for the homepage ledger scoreboard.

    Mirrors generate_scorecard.compute_scorecard_stats() field-for-field so the
    homepage two-metric scoreboard ("We Publish the Ledger") and the public
    /scorecard can NEVER diverge. Two separate, labeled metrics over the SAME
    denominator (resolved picks), never blended into one number:
      win_rate           = reached the AI's predicted gain in-window, or closed
                           profitable (the OWNER definition, pick_stats 2026-07-04)
      held_to_close_rate = still in profit at the window close (strict, secondary)
    Win counting uses the shared definition in pick_stats so the homepage strip
    and the scorecard can never diverge.
    """
    history = load_featured_history()
    resolved = [e for e in history if is_resolved(e)]
    total_picks = len(history)
    still_open = total_picks - len(resolved)

    win_rate, wins_n, judged_n = compute_win_rate(history)
    target_hit_rate, hits_n, _ = compute_target_hit_rate(history)
    held_rate, held_n, _resolved_n = compute_held_to_close_rate(history)

    # Median RESULT return over judged picks: exit at target when hit, else the
    # window close - consistent with the win definition (shared pick_stats).
    avg_return = compute_median_result_return(history)

    # Current streak (consecutive resolved wins from most recent backwards),
    # rendered as a 'NW'/'NL' string for the ledger scoreboard.
    streak = 0
    streak_type = 'W'
    sorted_resolved = sorted(resolved, key=lambda x: x['featured_date'], reverse=True)
    if sorted_resolved:
        first_win = is_win(sorted_resolved[0])
        streak_type = 'W' if first_win else 'L'
        for e in sorted_resolved:
            if is_win(e) == first_win:
                streak += 1
            else:
                break

    return {
        'total_picks': total_picks,
        'win_rate': round(win_rate, 1),                 # hit predicted gain OR closed up
        'win_count': wins_n,
        'judged_count': judged_n,                       # closed + open-already-hit
        'target_hit_rate': round(target_hit_rate, 1),   # reached target in window
        'target_hit_count': hits_n,
        'held_to_close_rate': round(held_rate, 1),      # still up at the close (strict)
        'held_to_close_count': held_n,
        'avg_return': round(avg_return, 1),
        'current_streak': '%d%s' % (streak, streak_type) if streak else '--',
        'closed_count': len(resolved),
        'open_count': still_open,
    }


def build_ledger_rows(limit=5, min_resolved=3):
    """Build the forward-ledger preview rows for the 'We Publish the Ledger'
    section (newest first). Each row: {symbol, direction 'L'/'S',
    logged_date 'MM-DD', result 'win'/'loss'/'pending'}.

    Drives the redesign's scoretbl directly from featured_history.json using the
    shared is_resolved/is_win definitions, so the visible rows always agree with
    the headline win_rate. Replaces the hardcoded NOW/FTNT/NVDA/AMD/COP mock.

    Guarantees at least min_resolved settled rows (when the history has them):
    picks run 22-30 days, so the newest 5 entries are routinely ALL still open,
    and an all-pending strip reads as "no track record" in the one section whose
    job is proof. The oldest pending slots give way to the newest resolved picks;
    rows stay real entries, newest first.
    """
    history = load_featured_history()
    newest_first = list(reversed(history))

    picked = newest_first[:limit]
    have_resolved = sum(1 for e in picked if is_resolved(e))
    want_resolved = min(min_resolved, sum(1 for e in newest_first if is_resolved(e)))
    if have_resolved < want_resolved:
        backfill = [e for e in newest_first[limit:] if is_resolved(e)]
        for _ in range(want_resolved - have_resolved):
            # drop the OLDEST pending row still shown, pull in the next resolved
            oldest_pending = next((e for e in reversed(picked) if not is_resolved(e)), None)
            if oldest_pending is None or not backfill:
                break
            picked.remove(oldest_pending)
            picked.append(backfill.pop(0))
        picked.sort(key=lambda e: e.get('featured_date', ''), reverse=True)

    rows = []
    for entry in picked:
        if is_resolved(entry):
            result = 'win' if is_win(entry) else 'loss'
        else:
            result = 'pending'
        logged = entry.get('featured_date', '')
        rows.append({
            'symbol': entry.get('symbol', ''),
            'direction': 'L' if entry.get('direction') == 'l' else 'S',
            'logged_date': logged[5:] if len(logged) >= 10 else logged,  # MM-DD
            'result': result,
        })
    return rows


def _hero_headline(history):
    """Build dynamic hero headline from the most recent proven pick.

    Walks history newest-first, takes the first pick with peak_return >= 5%.
    Falls back to static headline if none qualifies.
    """
    for entry in reversed(history):
        peak = entry.get('peak_return', 0) or 0
        if peak >= 5.0:
            symbol = entry['symbol']
            days = entry['daysOut']
            if entry['direction'] == 's':
                return "$%s dropped %.1f%% in %d days." % (symbol, peak, days)
            return "$%s rose +%.1f%% in %d days." % (symbol, peak, days)
    return "One free seasonal stock pick, every morning before the open."


def generate_html(opportunities_by_tab, featured_data=None, market_bar_items=None,
                  show_opportunities=SHOW_OPPORTUNITIES):
    """Generate HTML from template and data."""

    jinja_env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )

    template = jinja_env.get_template(THEMES[ACTIVE_THEME]["template"])

    default_tab = "short_term"
    if not opportunities_by_tab.get("short_term", {}).get("opportunities"):
        default_tab = "medium_term"

    total_opps = sum(
        tab.get("count", 0)
        for tab in opportunities_by_tab.values()
    )

    # =========================================================================
    # CONTENT DICT
    # =========================================================================
    content = {
        "show_opportunities": show_opportunities,
        "enable_seo": ENABLE_SEO,
        # GA4 <head> snippet ('' when TW2_GA_MEASUREMENT_ID is unset, e.g. dev).
        "ga_head_snippet": ga_head_snippet(),
        # Absolute URL for canonical, og:url, and JSON-LD - independent of host.
        "canonical_url": CANONICAL_ROOT,

        # -- Meta --
        "meta": {
            # Kept in sync with hero.headline (the tab title / og:title must
            # never advertise a headline the page no longer says).
            "title": "TradeWave - Reveal Seasonal Tendencies With The Highest Probability of Repeating",
            "description": (
                "TradeWave detects recurring seasonal patterns from end-of-day "
                "data across 15 markets, over a lookback you choose: 1 to 99 "
                "years, calendar or election cycle. The engine is deterministic, "
                "same inputs and same numbers, and the model only ranks, it "
                "predicts nothing. Every daily pick is logged to a public ledger "
                "before the outcome, losses included. "
                + ("REST API and MCP included. " if MCP_LIVE else "REST API included. ")
                + "Research, not advice."
            ),
            "keywords": (
                "seasonal trading, stock market patterns, seasonal pattern research, "
                "quantitative trading, pattern scoring, machine learning stocks, "
                "wave viewer, election cycle trading, S&P 500 patterns, market history"
            ),
        },

        # -- Nav (template hardcodes the link row; only these URLs are bound) --
        "nav": {
            "signup_url": SIGNUP_URL,
            "login_url": LOGIN_URL,
            "logout_url": LOGOUT_URL,
            "dashboard_url": DASHBOARD_URL,
            "upgrade_url": UPGRADE_URL,
        },

        # -- Hero --
        # HERO TOURNAMENT WINNER (2026-07-01 conversion loop) - shipped verbatim.
        # The template binds h1 -> hero.headline and the single subhead ->
        # hero.subheadline (the old hardcoded-h1 template violation is fixed).
        # The dynamic _hero_headline() stays available as headline_dynamic for a
        # future variant; the template binds the static winner.
        #
        # Scored A/B runner-ups (composite /10) - swap-ready alternates:
        #   (7.34) H1:  "See the Evidence Before You Take the Trade"
        #          Sub: "Every AI-calibrated score opens to its per-year record
        #                across up to a century of market data - the exact dates,
        #                the size of each move, the years it failed. You decide
        #                what to do with it; TradeWave logs its daily pick in
        #                public before the outcome."
        #   (7.34) H1:  "Research You Can Audit Back to 1928"
        #          Sub: "Patterns ranked and scored by AI across 15 markets, with
        #                every figure opening to its per-year record. TradeWave's
        #                daily pick is posted before the outcome, and the losses
        #                stay up."
        #   (7.24) H1:  "History Finds the Pattern, the AI Grades It Down"
        #          Sub: "TradeWave finds moves that repeated across 15 markets and
        #                up to 98 years of data, then a machine-learning model
        #                calibrates each score down, never up. The daily pick goes
        #                on a public ledger before the outcome, losses included."
        "hero": {
            "eyebrow": "Seasonal Research That Shows Its Work",
            "headline": "Reveal Seasonal Tendencies With The Highest Probability of Repeating",
            "headline_dynamic": _hero_headline(load_featured_history()),
            "subheadline": (
                "AI-powered rankings and scores across 98 years of data, ready "
                "for you to leverage across thousands of stocks, ETFs, as well "
                "as your own portfolio."
            ),
            # The "New" MCP pill above the headline (links to #tara). Rendered
            # only when content.mcp_live is True (gated, see MCP_LIVE). No
            # "in plain English" phrasing (June-30 directive: many visitors
            # are not native English speakers) and no per-plan entitlement
            # claim here - the pill introduces Tara, nothing more.
            "pill_text": "Meet Tara, TradeWave's AI agent - now inside ChatGPT and Claude",
            "pill_url": "#tara",
            # Calendar-reminders pill: previewed 2026-07-04, owner REJECTED it for
            # the hero (feature announcements stay out of the hero region; the
            # calendar band + pricing bullets carry the feature). Text '' = hidden.
            # The template slot remains: it renders only while the Tara/MCP pill
            # is dark, should a future announcement ever need it.
            "pill_calendar_text": "",
            "pill_calendar_url": "#calendar-reminders",
            "cta_primary": "Start For Free - No Credit Card Required",
            "cta_primary_url": SIGNUP_URL,
            # FREE-path reassurance (June-30 directive). The free signup is
            # genuinely card-free; never reuse this line on a paid path.
            "cta_micro": "Full Access for 7 Days",
            # Lead-in to the hero's quiet free-report card (the card is styled
            # subordinate to the primary CTA; capture stays strong in 03/08).
            "report_lead": (
                "Prefer to start smaller? Get the free seasonal report on "
                "stocks you own - no account needed:"
            ),
            # The ONE compact hero disclaimer micro-line.
            "disclaimer": (
                "Historical research for educational purposes, not advice or "
                "a recommendation."
            ),
            # Above-the-fold trust strip labels. The counts come live from
            # content.scorecard_stats at render time - never hardcode a number
            # here; the template hides numeric segments until data exists.
            "trust_strip": {
                "logged_label": "picks on the public ledger",
                "held_label": "held a profit to the close",
                # De-duped 2026-07-02: the subheadline directly above already
                # says "logged before the outcome ... losses stay on the public
                # record" - never repeat it two lines later.
                "note": "The full record is public.",
                "link_text": "Inspect the ledger",
            },
            # Logged-in CTA variants
            "cta_analyst_url":     PRICING_ANALYST_MONTHLY_URL,
            "cta_strategist_url":  PRICING_STRATEGIST_MONTHLY_URL,
            "cta_wave_viewer_url": "/app/",
            "cta_webinars_url":    "%swebinars" % DOMAIN_ROOT,
        },

        # -- Tara (section 02 - the beginner hook, moved directly after the
        #    hero per the June-30 owner+Michael meeting). Frame: "You're in
        #    complete control" - answers AI distrust head-on (you ask, you set
        #    the parameters, Tara assists; she never replaces you and never
        #    tells you what to do). "Ask in plain English" phrasing dropped
        #    site-wide (many visitors are not native English speakers) -
        #    replaced by "in your own words".
        #    Headline decision (2026-07-01): "Let Tara Do the Rest" beat
        #    "Let AI Do the Rest" for a cold visitor - the generic "let AI do
        #    it" both triggers the AI-hype scam-prior and contradicts the
        #    control frame, while the named agent is introduced in the very
        #    next line, closing the "who is Tara?" gap immediately.
        "tara": {
            "eyebrow": "You're in Complete Control",
            "headline": "Tell TradeWave What You Want to See. Let Tara Do the Rest",
            # First mention on the page (the hero pill renders only when
            # MCP is live) - so this line must introduce her.
            "intro": (
                "TradeWave's AI agent Tara reads the data and produces the "
                "analysis for you."
            ),
            "ask_placeholder": "Which tech stocks tend to rise this time of year?",
            "ask_button": "See the Evidence",
            "control_points": [
                {"lead": "You ask.",
                 "text": "Any market, any question, in your own words."},
                {"lead": "You set the parameters.",
                 "text": ("Markets, date window, lookback, election cycle - "
                          "the analysis runs on your choices.")},
                {"lead": "Tara assists.",
                 "text": ("She runs the numbers, ranks the setups, and drives "
                          "the charts. She never replaces your judgment, and "
                          "she never tells you what to do.")},
            ],
            "micro": (
                "Tara reads the same deterministic statistics you see on the "
                "chart and explains the evidence - never personalized advice, "
                "never a prediction."
            ),
            # Truthful CTA - there is no public demo (/app/ is a signup wall
            # when logged out; 2026-07-01 audit item 3), so invite the real
            # action: the free signup, whose 7-day full access includes Tara.
            "micro_link_text": "Start free and ask her yourself",
        },

        # -- FAQ (section 08 - objection handling, 2026-07-01 audit item 5).
        #    The template renders BOTH the visible accordion and the FAQPage
        #    JSON-LD in <head> from this one list (content.faq.entries), so
        #    schema and page can never diverge. Claim rules: tier limits/entitlements are FROZEN (never
        #    restate them here); "no card" is asserted ONLY on the free path
        #    (locked decision 4); the model calibrates DOWN, never predicts.
        "faq": {
            "eyebrow": "FAQ",
            "headline": "Fair Questions, Straight Answers",
            # Key is "entries", NOT "items" - content.faq.items in Jinja
            # resolves to the dict method and breaks the loop.
            "entries": [
                {
                    "q": "Is this a signal service? Does it tell me what to buy?",
                    "a": ("No. TradeWave shows you the evidence - the exact "
                          "dates a move repeated, how often, how big it ran, "
                          "and the years it failed - and you decide what to do "
                          "with it. It never sends trade alerts and never gives "
                          "personalized advice. Even the one daily pick we "
                          "publish is research, logged to the public ledger "
                          "before the outcome is known."),
                },
                {
                    "q": "This sounds too good to be true. Where's the catch?",
                    "a": ("The catch is that seasonality is evidence, not "
                          "certainty - and we show you exactly that. Every "
                          "pattern opens to its full per-year record, failing "
                          "years included. The daily pick goes on a public "
                          "ledger before the outcome, and the losses stay up. "
                          "And the machine-learning model only calibrates a "
                          "pattern's probability down, never up - it ranks "
                          "what history supports; it never predicts. You do "
                          "not have to take our word for any of it."),
                    "link_text": "Inspect the ledger",
                    "link_url": "%sscorecard.html" % DOMAIN_ROOT,
                },
                {
                    "q": "What data is this built on?",
                    "a": ("End-of-day price history across 15 markets - US "
                          "stocks and ETFs, the major indices, futures, forex, "
                          "bonds, foreign indices, and crypto - reaching back "
                          "as far as a century. You choose the lookback, 1 to "
                          "99 years, calendar or election cycle, and the "
                          "engine is deterministic: the same inputs return the "
                          "same numbers, every time."),
                },
                {
                    "q": "Can I cancel? What happens after the trial?",
                    "a": ("Yes, in one click, anytime. Signing up starts 7 "
                          "days of the full platform; when that ends you keep "
                          "a free plan that never expires. Cancel a paid plan "
                          "and you simply drop back to the free plan - your "
                          "account stays."),
                },
                {
                    "q": "Is my card charged?",
                    "a": ("Starting free takes no card at all, so there is "
                          "nothing to charge. Paid-tier trials run 7 days free "
                          "and do take a card at checkout - cancel anytime "
                          "during the trial in one click and you pay nothing."),
                },
            ],
        },

        # -- Close (section 11) micro under the final CTA. The old "Launch the
        #    live demo" link promised a demo that does not exist - it points to
        #    the public scorecard instead (template binds content.scorecard_url).
        "close": {
            "micro": ("No credit card. Full platform for 7 days, then a free "
                      "plan that never expires."),
            "link_text": "Or inspect the public scorecard first",
        },

        # -- Lead modal (free seasonal report) post-success upsell line. Only
        #    the rewritten line is bound so far; the rest of the modal predates
        #    the content-dict convention.
        "lead_modal": {
            "upsell": ("Want these patterns live - change the window, stretch "
                       "the lookback, and ask Tara about them? Your account "
                       "starts with 7 days of the full platform, no card."),
        },

        # -- Proof (section 06 "What Traders Say") - the two cleared third-party
        #    endorsements (locked owner decision 2): video + quote for Anne-Marie
        #    Baiynd and Erin West, rendered between the ledger and pricing. Both
        #    are TradeWave affiliates, so the template renders the quiet
        #    material-connection disclosure right under the cards. The videos
        #    are 50MB+ self-hosted MP4s - click-to-play only, never autoplay.
        "proof": {
            "eyebrow": "What Traders Say",
            "headline": "From Traders Who Do This for a Living",
            "sub": (
                "Anne-Marie Baiynd and Erin West trade for a living and teach "
                "traders to do the same. Here is where TradeWave sits in their "
                "process - on camera, in their own words."
            ),
            "disclosure": (
                "Disclosure: Anne-Marie and Erin are TradeWave affiliates and "
                "may earn a commission when someone subscribes through them."
            ),
        },

        # -- Anne-Marie Video (rendered in the proof section) --
        "video": {
            "src": ANNEMARIE_VIDEO_URL,
            "quote": "I don't go into any trade without looking at it on TradeWave first",
            "author": "Anne-Marie Baiynd",
            "title": "CEO & Founder, TheTradingBook.com",
            "credential": "Bestselling Author & Market Strategist",
        },

        # -- Erin Video (rendered in the proof section) --
        "video2": {
            "src": ERIN_VIDEO_URL,
            "quote": "TradeWave has directed me to a few trades that were really lovely, five-figure trades",
            "author": "Erin West",
            "title": "Founder, Humans Who Trade",
            "credential": "Trading Coach & Educator for Women",
        },

        # -- Featured Pattern --
        "featured_pattern": featured_data,
        "scorecard_url": "%sscorecard.html" % DOMAIN_ROOT,
        "methodology_url": "%smethodology" % DOMAIN_ROOT,
        "developers_url": DEVELOPERS_URL,
        "scorecard_stats": compute_homepage_scorecard_stats(),
        # Forward-ledger preview rows (newest first) for the "We Publish the
        # Ledger" scoretbl - real picks, not the NOW/FTNT/NVDA mock.
        "ledger_rows": build_ledger_rows(limit=5),
        "recent_picks": [e['symbol'] for e in reversed(load_featured_history())][:3],
        "market_bar": market_bar_items or [],

        # Gate every MCP / "inside ChatGPT and Claude" claim (hero pill, connect
        # section, chips) until the consumer MCP+OAuth front door is live.
        "mcp_live": MCP_LIVE,

        # -- Pricing --
        # TW2: prices come from Stripe via lookup_keys, not hardcoded.
        # See _stripe_prices() above; falls back to defaults if Stripe unreachable.
        "pricing": (lambda _p=_stripe_prices(): {
            "headline": "Start With Full Access. Keep a Free Plan, or Upgrade When It Pays for Itself",
            # Rendered as the kicker under the pricing headline. Locked decision
            # 4 (2026-07-01): the "no card" promise is scoped to the FREE start
            # only - paid-tier trials collect a card at Stripe checkout, so this
            # line says so instead of implying "no card" everywhere.
            "subheadline": (
                "Signing up is free - 7 days of the full platform, no card "
                "required, then a free plan that never expires. Paid-tier "
                "trials also run 7 days free; those take a card at checkout "
                "and cancel in one click."
            ),
            "default_billing": "yearly",
            "max_yearly_savings": _p['max_yearly_savings'],
            "tiers": [
                {
                    "name": "Explorer",
                    "monthly_price": "Free",
                    "monthly_period": "",
                    "monthly_original": "",
                    "yearly_price": "Free",
                    "yearly_period": "",
                    "yearly_original": "",
                    "description": "Get a feel for the platform with no credit card required",
                    "trial_badge": "",
                    "features": [
                        "See today's top 5 seasonal patterns",
                        "10 years of seasonal history",
                        "Track up to 5 opportunities in 1 portfolio",
                        "One-click Google Calendar reminders",
                        "Real-time prices and Trend Score",
                        "Earnings date estimates (EDGAR)",
                        "Election-cycle overlay on loaded patterns",
                        "~upgrade:Upgrade to unlock AI scoring, all markets, and more",
                    ],
                    # Free start = the ONLY genuinely card-free path (locked
                    # decision 4); the micro-line may say "no card" here ONLY.
                    "cta": "Get the Free Plan",
                    "cta_micro": "No card required - free forever.",
                    "monthly_url": PRICING_EXPLORER_URL,
                    "yearly_url": PRICING_EXPLORER_URL,
                    "highlighted": False,
                    "after_launch_price": "",
                },
                {
                    "name": "Navigator",
                    "monthly_price": _p['navigator_monthly'],
                    "monthly_period": "/mo",
                    "monthly_original": "",
                    "yearly_price": _p['navigator_yearly'],
                    "yearly_period": "/mo, billed yearly",
                    "yearly_original": "",
                    "description": "Hunt seasonal patterns across the three big U.S. indices, with any start date",
                    "trial_badge": "",
                    "features": [
                        "Dow, NASDAQ 100, and S&P 500 - fully date-unlocked",
                        "Browse any start date, not just today",
                        "15 years of seasonal history",
                        "3 portfolios, track up to 25 opportunities",
                        "One-click Google Calendar reminders",
                        "1 watchlist, up to 25 symbols",
                        "Election-cycle filter on the opportunity table",
                        "~upgrade:Upgrade to Analyst for AI scoring and all U.S. stocks plus ETFs",
                    ],
                    # Paid trial: honest label (locked decision 4) - Stripe
                    # collects a card at checkout, so never say "no card" here.
                    "cta": "Try Free for 7 Days",
                    "cta_micro": "Card required at checkout. Cancel anytime in one click.",
                    "monthly_url": PRICING_NAVIGATOR_MONTHLY_URL,
                    "yearly_url": PRICING_NAVIGATOR_YEARLY_URL,
                    "checkout_tier": "navigator",
                    "highlighted": False,
                    "after_launch_price": "",
                    "yearly_daily": _p['navigator_yearly_daily'],
                    "yearly_savings": _p['navigator_yearly_savings'],
                },
                {
                    "name": "Analyst",
                    "monthly_price": _p['analyst_monthly'],
                    "monthly_period": "/mo",
                    "monthly_original": "",
                    "yearly_price": _p['analyst_yearly'],
                    "yearly_period": "/mo, billed yearly",
                    "yearly_original": "",
                    "description": "Deep seasonal insights across all U.S. stocks and ETFs with AI scoring",
                    "trial_badge": "",
                    "features": [
                        "AI Pattern Analyst with scoring",
                        "All U.S. stocks + ETFs, custom start dates",
                        # 63 = the data provider's deepest per-stock history (the
                        # oldest listed names, e.g. BA/IBM); most stocks are shorter,
                        # so this is a "where data is available" ceiling, never a
                        # per-stock promise. Re-check if the data provider changes.
                        "Full seasonal history - up to 63 years where data is available",
                        "25 portfolios, track up to 100 opportunities",
                        "One-click Google Calendar reminders",
                        "10 watchlists, up to 50 symbols each",
                        "Seasonal Market News articles",
                        "LIVE weekly Q&A webinar",
                        "Email Support",
                    ],
                    "cta": "Try Free for 7 Days",
                    "cta_micro": "Card required at checkout. Cancel anytime in one click.",
                    "monthly_url": PRICING_ANALYST_MONTHLY_URL,
                    "yearly_url": PRICING_ANALYST_YEARLY_URL,
                    "checkout_tier": "analyst",
                    "highlighted": False,
                    "after_launch_price": "",  # launch promo expired - Stripe drives current price
                    "yearly_daily": _p['analyst_yearly_daily'],
                    "yearly_savings": _p['analyst_yearly_savings'],
                },
                {
                    "name": "Strategist",
                    "monthly_price": _p['strategist_monthly'],
                    "monthly_period": "/mo",
                    "monthly_original": "",
                    "yearly_price": _p['strategist_yearly'],
                    "yearly_period": "/mo, billed yearly",
                    "yearly_original": "",
                    "description": "Everything in Analyst plus all 15 markets - futures, forex, bonds, foreign indices and crypto - and premium support",
                    "trial_badge": "7 days free, full access",
                    # ROI anchor - rendered in the Strategist card right under
                    # the features (Erin's full quote + video now live in the
                    # proof section, so the old card_testimonial was deleted).
                    "roi_anchor": "One winning trade on a $10k position pays for a year of Strategist.",
                    "features": [
                        "Everything in Analyst, plus:",
                        "Futures, forex, bonds, foreign indices, and crypto",
                        "All 15 markets with full access",
                        "100 portfolios; publish up to 500 date-range reports",
                        "50 watchlists, up to 100 symbols each",
                        "Weekly strategy Zoom call",
                        "Premium Support",
                    ],
                    "cta": "Try Free for 7 Days",
                    "cta_micro": "Card required at checkout. Cancel anytime in one click.",
                    "monthly_url": PRICING_STRATEGIST_MONTHLY_URL,
                    "yearly_url": PRICING_STRATEGIST_YEARLY_URL,
                    "checkout_tier": "strategist",
                    "highlighted": True,
                    "after_launch_price": "",  # launch promo expired - Stripe drives current price
                    "yearly_daily": _p['strategist_yearly_daily'],
                    "yearly_savings": _p['strategist_yearly_savings'],
                },
            ],
        })(),

        # -- Midterm Warning (removed from homepage, moved to blog) --
        "midterm_warning": None,

        # -- Founder --
        "founder": {
            "name": "Afshin Moshrefi",
            "title": "Founder, TradeWave.ai",
            "bio": (
                "Afshin Moshrefi has spent a lifetime building technology around "
                "one obsession: finding what is hidden in the data before the rest "
                "of the world catches on. TradeWave.ai grew out of that obsession, "
                "turning market seasonality into something traders can measure, "
                "verify, and actually use."
            ),
            "photo": "/_static/afshin-profile-pic.jpg",
            "linkedin": "https://www.linkedin.com/in/afshinmoshrefi/",
            "book_title": "The 100-Year Pattern",
            "book_url": "https://100yearpattern.com",
        },

        # -- Contact --
        "contact_url": CONTACT_URL,

        # -- Footer (minimal) --
        "footer": {
            # Rendered only when content.mcp_live is True (gated on MCP_LIVE).
            "mcp_note": (
                "TradeWave is available inside ChatGPT, Claude, and any "
                "MCP-capable assistant. Sign in with your account and ask "
                "your questions there - the same deterministic engine and "
                "the same public record, wherever you work."
            ),
            "legal": {
                "copyright": "%d Tara Data Research LLC. All rights reserved." % datetime.now().year,
                "disclaimer": (
                    "TradeWave is a research platform. It is not a brokerage and "
                    "does not execute trades. All data is based on historical analysis "
                    "and is provided for informational and educational purposes only. "
                    "Past performance does not guarantee future results. Trading and "
                    "investing involve substantial risk of loss. You should consult "
                    "with a qualified financial advisor before making any investment "
                    "decisions. Nothing on this website constitutes a recommendation "
                    "to buy or sell any security."
                ),
            },
        },

        "assets": {
            "favicon": config.tw_favicon,
            # Absolute URL to a REAL file - /static/images/* does not exist on
            # any box (og:image 404'd; trust-audit critical).
            "og_image": "%s_static/evidence_hero.webp" % CANONICAL_ROOT,
        },

        # =====================================================================
        # REDESIGN STATIC BRAND COPY ("The Ledger" direction). These are
        # marketing copy blocks, not live data - kept here (not hardcoded in the
        # template) so copy edits stay in one place and the template is pure
        # structure. Every approved headline/subhead lives verbatim below.
        # =====================================================================

        # -- Who It's For (section 09) - WIRED 2026-07-02: the template used to
        #    hardcode this section while a stale, different version sat dead
        #    here (zombie copy). This dict now IS the rendered copy; the
        #    template binds it. Questions render inside quote marks in the
        #    template - store them unquoted. Note de-duped: the sub already
        #    says "Same engine", so the note must not repeat it.
        "desks": {
            "eyebrow": "Who It's For",
            "headline": "Whoever's Asking, It Bends to You",
            "sub": ("Same engine for a fund running a thousand backtests and "
                    "a trader testing one window."),
            "note": ("Not different products - the same evidence, priced to "
                     "the job in front of you."),
            "cards": [
                {
                    "audience": "New and Independent Traders",
                    "question": "What's seasonal in tech right now?",
                    "blurb": ("Ask Tara, get a named ranked answer. Real "
                              "research in your first minute."),
                    "cta_text": "Start free",
                    "cta_url": "#pricing",
                },
                {
                    "audience": "Professionals, Quants and RIAs",
                    "question": ("Strongest 30 to 60 day windows across all "
                                 "markets, ranked by Sharpe"),
                    "blurb": ("The full per-year record, PE-cycle filtering, "
                              "and CSV - auditable down to the year."),
                    "cta_text": "See Analyst / Strategist",
                    "cta_url": "#pricing",
                },
                {
                    "audience": "Funds and Enterprise",
                    "question": ("Your agent can write a backtest; it cannot "
                                 "make it true"),
                    "blurb": ("License the pattern file, the model, and the "
                              "REST API - your stack, multi-seat, SSO, audit."),
                    "cta_text": "Talk to us",
                    "cta_url": "mailto:hello@tradewave.ai?subject=Funds%20%26%20Enterprise",
                },
            ],
        },

        # "Real Articles, Real Dates" feed. There is NO SMN/Insights feed wired
        # into the generator today, so this stays None and the section is hidden
        # rather than rendering fabricated dates. When a real feed loader is
        # added, populate [{date, title, url}] and the section appears.
        "recent_articles": None,
        "articles_library_url": "/insights/",
    }

    # Per-asset cache-buster (source-file mtime): nginx serves /_static/ with a
    # 1-day browser cache, so a swapped screenshot would not show for returning
    # visitors without a changed URL. Only changes when the asset actually does.
    _asset_dir = Path(__file__).resolve().parent / "static"
    content["asset_v"] = {
        a: int((_asset_dir / a).stat().st_mtime) if (_asset_dir / a).exists() else 0
        for a in ("evidence_hero.webp", "shows_work.webp", "ask.webp")
    }

    return template.render(content=content)

# =============================================================================
# MAIN
# =============================================================================

def main():
    global ALLOW_PRICE_FALLBACK
    parser = argparse.ArgumentParser(description="TradeWave homepage generator")
    parser.add_argument('--allow-price-fallback', action='store_true',
                        help="Publish the hardcoded fallback prices if the Stripe lookup "
                             "fails (default: refuse and exit nonzero - a stale page "
                             "beats a wrong-price page).")
    args = parser.parse_args()
    ALLOW_PRICE_FALLBACK = args.allow_price_fallback

    print("TradeWave Homepage Generator")
    print("   CSV: %s" % OPPORTUNITIES_CSV)
    print("   Output: %s/%s" % (OUTPUT_DIR, OUTPUT_FILENAME))
    print("   Theme: %s (%s)" % (ACTIVE_THEME, THEMES[ACTIVE_THEME]['name']))
    print("   PE Cycle: %s (%s)" % (CURRENT_PE_CYCLE, CURRENT_PE_DISPLAY))
    print()

    # 0. Fetch market bar quotes
    print("   Fetching market bar quotes...")
    market_bar_items = build_market_bar_data()
    print("   Market bar: %d tickers" % len(market_bar_items))

    # 1. Load opportunities from CSV
    opportunities = load_opportunities_from_csv(OPPORTUNITIES_CSV)
    if not opportunities:
        print("   No opportunities loaded. Exiting.")
        return

    # 1b. Stale-table guard: never render closed trade windows under urgency
    # copy. If fewer than 3 current rows remain, omit the whole section.
    opportunities = drop_closed_windows(opportunities)
    show_opportunities = SHOW_OPPORTUNITIES
    if len(opportunities) < 3:
        print("   WARN stale-table guard: only %d current opportunity row(s) "
              "remain (<3); omitting the Top Patterns section. Refresh %s "
              "(site/home_opportunities.py)." % (len(opportunities), OPPORTUNITIES_CSV),
              file=sys.stderr)
        show_opportunities = False

    # 2. Enrich with live stockscore data
    opportunities = enrich_with_stockscore(opportunities)

    # 3. Group by day range for tabs
    opportunities_by_tab = group_by_day_range(opportunities, OPPORTUNITIES_PER_TAB)

    # 4. Select featured pattern via ML scorer and generate SVG
    featured_data = None
    featured = select_featured_from_ml_scorer()
    if not featured:
        # Pipeline failed (login/ML/OppList4). Reuse the most recent pick from
        # history so the homepage still renders, but log LOUDLY and mark the
        # entry as stale. The scorecard reads featured_history.json directly,
        # so it will NOT update until select_featured_from_ml_scorer() succeeds.
        history = load_featured_history()
        if history:
            featured = dict(history[-1])
            featured['_stale_reuse'] = True
            print("=" * 70)
            print("   ERROR: No new AI pick produced today.")
            print("   Reusing %s from %s on homepage only." % (
                featured["symbol"], featured["featured_date"]))
            print("   featured_history.json NOT updated -> scorecard will NOT show a new pick.")
            print("=" * 70)
    if featured:
        print("   Featured pattern: %s (ML %.1f, WP %.1f%%)" % (
            featured["symbol"], featured["ml_score"], featured["win_prob"] * 100))
        try:
            from svg_wave_chart import generate_wave_chart_svg
            svg_path = "/home/flask/site/data/featured_chart.svg"
            generate_wave_chart_svg(
                resource_id=featured['resource_id'],
                symbol=featured['symbol'],
                start_date=featured['date'],
                days_out=featured['daysOut'],
                years=featured['years'],
                company_name=featured['company_name'],
                output_path=svg_path,
            )
            # Copy SVG into _static (it is referenced at /_static/featured_chart.svg).
            # Must be the _static SUBDIR, not the docroot root - else nginx serves a
            # stale _static/featured_chart.svg and the homepage's featured chart goes
            # weeks old while the fresh copy sits unused at the root.
            output_dir = Path(OUTPUT_DIR)
            static_out = output_dir / "_static"
            static_out.mkdir(parents=True, exist_ok=True)
            dest_svg = static_out / "featured_chart.svg"
            shutil.copy2(svg_path, str(dest_svg))
            print("   Featured SVG copied to %s" % dest_svg)

            # Extract years count and label for story
            years_str = featured['years']
            years_count = years_str.split('-')[-1] if '-' in years_str else years_str

            PE_YEAR_LABELS = {
                'pe0': 'election',
                'pe1': 'post-election',
                'pe2': 'midterm',
                'pe3': 'pre-election',
            }
            if featured['mode'] == 'pe' and '-' in years_str:
                pe_code = years_str.split('-')[0].lower()
                cycle_label = PE_YEAR_LABELS.get(pe_code, 'cycle')
                years_display = "%s %s" % (years_count, cycle_label)
            else:
                years_display = years_count

            # Compute end date for urgency display
            start_dt = datetime.strptime(featured["date"], "%Y-%m-%d")
            end_dt = start_dt + timedelta(days=featured["daysOut"])
            days_remaining = (end_dt - datetime.now()).days

            featured_data = {
                "show": True,
                "symbol": featured["symbol"],
                "company_name": featured["company_name"],
                "svg_url": "/_static/featured_chart.svg",
                "wave_viewer_url": featured["wave_viewer_url"],
                "story": (
                    "%s has averaged +%.1f%% in this %d-day window over the "
                    "past %s years (Sharpe %.2f). AI win probability: %.0f%%." % (
                        featured["symbol"],
                        featured["avg_profit"],
                        featured["daysOut"],
                        years_display,
                        featured["sharpe_ratio"],
                        featured["win_prob"] * 100,
                    )
                ),
                "sharpe_ratio": featured["sharpe_ratio"],
                "avg_return": featured["avg_profit"],
                "days": featured["daysOut"],
                "direction": "Long" if featured["direction"] == "l" else "Short",
                "win_prob": "%.1f" % (featured["win_prob"] * 100),
                "pred_return": "%.1f" % featured["pred_return"],
                "pred_mfe": "%.1f" % featured.get("pred_mfe", 0),
                "ml_score": "%.0f" % featured.get("ml_score", 0),
                "start_date_formatted": datetime.strptime(
                    featured["date"], "%Y-%m-%d").strftime("%b %d"),
                "end_date_formatted": end_dt.strftime("%b %d"),
                "days_remaining": max(days_remaining, 0),
                "published_time": "6:30 AM ET",
            }
        except Exception:
            # NEVER fail silently: the featured-pick card is the page's main
            # proof asset. Log the full traceback to stderr, then degrade to
            # bare stats (a missing card beats a missing homepage).
            print("   ERROR: featured-pick card failed to render; "
                  "homepage degrades to bare stats. Traceback:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            featured_data = None

    # 5. Generate HTML
    print("   Generating HTML...")
    html = generate_html(opportunities_by_tab, featured_data=featured_data,
                         market_bar_items=market_bar_items,
                         show_opportunities=show_opportunities)

    # 6. Save to output file
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    output_path.write_text(html)

    # Copy the home page's embedded image assets into _static so the /_static/*.webp
    # references resolve. The redesign embeds screenshots that have no other copy step
    # (deploy.sh and regen_site do not sync site/static), so they 404 without this.
    src_static = Path(__file__).resolve().parent / "static"
    static_out = output_dir / "_static"
    static_out.mkdir(parents=True, exist_ok=True)
    for asset in ("evidence_hero.webp", "shows_work.webp", "ask.webp"):
        src = src_static / asset
        if src.exists():
            shutil.copy2(str(src), str(static_out / asset))
            print("   Home asset copied to %s" % (static_out / asset))
        else:
            print("   WARN: home asset missing (page will 404 it): %s" % src)

    print("   Generated: %s" % output_path)
    print("   Size: %d bytes" % len(html))
    print("   Done!")

    # 7. Generate scorecard page
    print()
    pass  # TW2: scorecard generator not lifted yet

    # 8. Sync market bar quotes (handles futures mode)
    print()


if __name__ == "__main__":
    main()
