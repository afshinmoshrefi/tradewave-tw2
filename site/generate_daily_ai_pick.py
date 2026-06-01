#!/usr/bin/env python3
"""
TradeWave Daily AI Pick Generator (TW2)

Lifted/adapted from /home/flask/blog/generate_top10_AI.py on .151. Original
script published a top-10 page to WordPress; this version produces a static
HTML page at /var/www/tradewave/daily-ai-pick.html.

Logic:
  1. Login to appserver, fetch OppList4 for each financial group.
  2. Concatenate, sort by Sharpe Ratio, drop duplicates, filter by avg profit.
  3. Take top 10. Render static HTML with TW2 branding (logo + nav).

Usage:
    python generate_daily_ai_pick.py
    python generate_daily_ai_pick.py --date 2026-05-07

Skipped financial groups:
  - Forex All (id 8) - same exclusion as original (config.restrict_gov_bonds_sr
    isn't applied here because we don't write a separate gov-bond ranking).
"""

import argparse
import calendar
import datetime
import os
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/site/lib')
import config
from blog_tools import assign_years_pyears

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OppList4 is served by the tier-local app server. Env-driven via
# config.appserver_url (TW2_APPSERVER_URL): dev=127.0.0.1:5000,
# staging=http://10.0.0.92:5000, prod=appserver-prod URL.
APPSERVER_URL = config.appserver_url.rstrip('/')

OUTPUT_DIR = config.web_root_dir
OUTPUT_FILENAME = 'daily-ai-pick.html'
HEADER_PARTIAL = '/home/flask/site/templates/_tw_header.html'

NUM_PER_GROUP = getattr(config, 'num_opps_per_fi', 10)
TOP10_AVG_PROFIT_FILTER = getattr(config, 'top10_avg_profit_filter', 5)
RESTRICT_GOV_BONDS = getattr(config, 'restrict_gov_bonds_sr', -1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def appserver_login():
    """Login pattern from generate_home_page.py - keyprovider hack via APPSERVER_URL."""
    def _get(url, attempts=3, timeout=30, sleep_s=5):
        last = None
        for i in range(attempts):
            try:
                return requests.get(url, timeout=timeout).json()
            except Exception as e:
                last = e
                print('   WARN appserver call failed (%s), attempt %d/%d' % (e, i + 1, attempts))
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
        print('   ERROR appserver login failed: %s' % e)
        return None


def get_opp_list(group_id, month, day, years, pyears, token):
    """Fetch OppList4 for a single financial group."""
    url = '%s/OppList4/%s/%s/%s/%s/%s/-/0/0?token=%s' % (
        APPSERVER_URL, group_id, month, day, years, pyears, token,
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def opp_list_to_df(num, group_id, month, day, years, pyears, token):
    """Pull a group's opportunity list into a small DataFrame.

    OppList4 row layout (matches /home/flask/blog/generate_top10_AI.py):
      [date, symbol, daysOut, direction, sharpe, avg_profit, median, ...]
    """
    j = get_opp_list(group_id, month, day, years, pyears, token)
    rows = j.get('OppList', [])[:num] if isinstance(j, dict) else []
    out = []
    for opp in rows:
        if not isinstance(opp, list) or len(opp) < 6:
            continue
        try:
            sr = float(opp[4])
            ap = float(opp[5])
        except (TypeError, ValueError):
            continue
        try:
            d2 = (datetime.datetime.strptime(opp[0], '%Y-%m-%d')
                  + datetime.timedelta(days=int(opp[2]))).strftime('%Y-%m-%d')
        except Exception:
            d2 = ''
        out.append({
            'Date':         opp[0],
            'Symbol':       opp[1],
            'DaysOut':      opp[2],
            'Direction':    opp[3],
            'Sharpe Ratio': sr,
            'avg_profit':   ap,
            'Date2':        d2,
        })
    return pd.DataFrame(out)


def load_top10(opp_date, token):
    """Walk every financial group, return top-10 unique-symbol DataFrame."""
    month = calendar.month_name[int(opp_date[5:7])]
    day = str(int(opp_date[8:]))

    frames = []
    for key, name in config.available_resources.items():
        gid = int(key)
        if gid == 8:                          # FOREX ALL - same skip as original
            continue
        years, pyears = assign_years_pyears(gid)

        num = NUM_PER_GROUP
        if 'BONDS' in name and RESTRICT_GOV_BONDS > -1:
            num = RESTRICT_GOV_BONDS
        try:
            df_g = opp_list_to_df(num, gid, month, day, years, pyears, token)
        except Exception as e:
            print('   WARN OppList4 failed for group %s (%s): %s' % (gid, name, e))
            continue
        if df_g.empty:
            continue
        df_g['resource_id']  = gid
        df_g['market_name']  = name
        df_g['years']        = years

        # Annotate company name (best-effort).
        symbols_csv = config.available_resources_path.get(key)
        if symbols_csv and os.path.isfile(symbols_csv):
            try:
                dfs = pd.read_csv(symbols_csv)[['symbols', 'name']]
                df_g = df_g.merge(
                    dfs.rename(columns={'symbols': 'Symbol', 'name': 'company'}),
                    on='Symbol', how='left',
                )
            except Exception:
                df_g['company'] = ''
        else:
            df_g['company'] = ''
        df_g['company'] = df_g['company'].fillna('')

        frames.append(df_g)
        print('   %s: %d picks' % (name, len(df_g)))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(by='Sharpe Ratio', ascending=False)
    df = df.drop_duplicates(subset='Symbol').reset_index(drop=True)
    df = df[df['avg_profit'] > TOP10_AVG_PROFIT_FILTER]
    return df.head(10).reset_index(drop=True)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(df, opp_date):
    header_html = ''
    if os.path.isfile(HEADER_PARTIAL):
        with open(HEADER_PARTIAL) as f:
            header_html = f.read()

    domain_root = config.domain_root or '/'

    rows = []
    for i, r in df.iterrows():
        rank = i + 1
        sym  = r['Symbol']
        comp = r['company'] or ''
        market = r['market_name']
        date1 = r['Date']
        date2 = r['Date2']
        dir_  = r['Direction']
        days  = r['DaysOut']
        years = r['years']
        sr    = r['Sharpe Ratio']
        ap    = r['avg_profit']
        # Wave-viewer deeplink (same shape used elsewhere on TW2)
        wv_url = '%sapp/?symbol=%s&date=%s&days=%s&years=%s' % (
            domain_root, sym, date1, days, years,
        )
        rows.append(
            "<tr>"
            "<td class='r-num'>#{}</td>"
            "<td class='r-sym'><a href='{}'>{}</a></td>"
            "<td class='r-comp'>{}</td>"
            "<td class='r-mkt'>{}</td>"
            "<td class='r-dir {}'>{}</td>"
            "<td class='r-d1'>{}</td>"
            "<td class='r-d2'>{}</td>"
            "<td class='r-d'>{} d</td>"
            "<td class='r-y'>{} yr</td>"
            "<td class='r-sr'>{:.2f}</td>"
            "<td class='r-ap'>{:.1f}%</td>"
            "</tr>".format(
                rank, wv_url, sym, comp, market,
                dir_.lower(), dir_, date1, date2, days, years, sr, ap,
            )
        )
    rows_html = '\n'.join(rows) if rows else (
        "<tr><td colspan='11' style='text-align:center;padding:32px;color:#9ca3af'>"
        "No picks above filter for " + opp_date + ".</td></tr>"
    )

    nice_date = datetime.datetime.strptime(opp_date, '%Y-%m-%d').strftime('%B %-d, %Y')
    year = str(datetime.datetime.now().year)

    head = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily AI Pick - Top 10 Patterns for {NICE_DATE} | TradeWave</title>
  <meta name="description" content="TradeWave top 10 AI-scored seasonal patterns for {NICE_DATE}, ranked by Sharpe Ratio across 16 markets.">
  <meta name="robots" content="noindex, nofollow">
  <link rel="icon" type="image/png" href="{FAVICON}">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: rgb(15,10,21);
      --bg-secondary: rgb(25,22,35);
      --bg-card: #0c1225;
      --text-primary: #ffffff;
      --text-secondary: #9ca3af;
      --text-muted: #6b7280;
      --accent: #6366f1;
      --accent-hover: #818cf8;
      --success: #10b981;
      --danger: #ef4444;
      --border: #1f2937;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-primary); color: var(--text-primary); line-height: 1.5; }
    .container { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
    .pick-hero { text-align: center; padding: 56px 0 16px; }
    .pick-hero h1 { font-size: 36px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 8px; }
    .pick-hero p  { color: var(--text-secondary); font-size: 16px; }
    .pick-table { width: 100%; margin: 32px 0; border-collapse: collapse;
      background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px;
      overflow: hidden; font-size: 14px; }
    .pick-table th, .pick-table td { padding: 12px 14px; text-align: left;
      border-bottom: 1px solid var(--border); }
    .pick-table th { background: rgba(99,102,241,0.12); color: var(--text-primary);
      font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: 0.6px; }
    .pick-table tr:last-child td { border-bottom: none; }
    .pick-table tr:hover td { background: rgba(99,102,241,0.05); }
    .r-num { color: var(--text-muted); font-weight: 600; }
    .r-sym a { color: var(--accent); font-weight: 700; text-decoration: none; }
    .r-sym a:hover { color: var(--accent-hover); }
    .r-comp { color: var(--text-secondary); font-size: 13px; }
    .r-mkt  { color: var(--text-muted); font-size: 12px; }
    .r-dir.long  { color: var(--success); font-weight: 600; }
    .r-dir.short { color: var(--danger);  font-weight: 600; }
    .r-sr  { font-variant-numeric: tabular-nums; font-weight: 600; }
    .r-ap  { font-variant-numeric: tabular-nums; }
    .pick-foot { padding: 32px 0 64px; color: var(--text-muted);
      font-size: 12px; text-align: center; }
    .pick-foot a { color: var(--accent); text-decoration: none; }
    @media (max-width: 768px) {
      .pick-table { font-size: 12px; }
      .pick-table th, .pick-table td { padding: 8px 10px; }
      .r-comp { display: none; }
    }
  </style>
</head>
<body>
'''

    body = '''
  <div class="container">
    <div class="pick-hero">
      <h1>Daily AI Pick</h1>
      <p>Top 10 patterns for {NICE_DATE}, ranked by Sharpe Ratio across all markets.</p>
    </div>
    <table class="pick-table">
      <thead>
        <tr>
          <th>Rank</th><th>Symbol</th><th>Company</th><th>Market</th>
          <th>Dir</th><th>Entry</th><th>Exit</th><th>Hold</th>
          <th>Lookback</th><th>Sharpe</th><th>Avg Profit</th>
        </tr>
      </thead>
      <tbody>
{ROWS}
      </tbody>
    </table>
    <div class="pick-foot">
      &copy; {YEAR} Tara Data Research LLC &middot;
      <a href="/research.html">Research</a> &middot;
      <a href="/patterns/">Tickers</a> &middot;
      <a href="/app/">Wave Viewer</a>
      <p style="margin-top:14px;">TradeWave is a research platform. It is not a brokerage and does not execute trades.
      All data is historical and for informational and educational purposes only.</p>
    </div>
  </div>
</body>
</html>
'''

    out = head + header_html + body
    out = out.replace('{NICE_DATE}', nice_date) \
             .replace('{FAVICON}', config.tw_favicon) \
             .replace('{ROWS}', rows_html) \
             .replace('{YEAR}', year)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description='Generate daily AI pick page')
    p.add_argument('--date', help='YYYY-MM-DD opp_date (default: today)')
    args = p.parse_args()

    opp_date = args.date or datetime.datetime.now().strftime('%Y-%m-%d')
    print('Generating daily AI pick for %s' % opp_date)

    print('Logging into appserver: %s' % APPSERVER_URL)
    token = appserver_login()
    if not token:
        print('ERROR: appserver login failed')
        sys.exit(3)

    df = load_top10(opp_date, token)
    if df.empty:
        print('WARN: no picks returned (will still render empty page)')

    html = render_html(df, opp_date)

    out = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('Generated: %s' % out)
    print('Size: %d bytes' % len(html))


if __name__ == '__main__':
    main()
