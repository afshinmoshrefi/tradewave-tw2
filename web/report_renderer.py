"""
TW2 static report renderer - lifted from TW1 create_report.py + post_template.py.

Renders a TW1-style "date-range opportunity report" as a static HTML file plus
3 PNG charts to /var/www/tradewave/r/{slug}/. Called from appserver's
dr_report_publish endpoint after the redis portfolio-add succeeds.

No WordPress, no queue - direct call, file-on-disk output.

The chart functions (get_chart_data, create_barchart, create_cumulative_chart,
get_seasonal_chart_data, create_seasonals_chart) are lifted near-verbatim from
TW1's /home/flask/blog/create_report.py. The HTML strings (html_table,
chart_content_for_blog) are lifted from /home/flask/blog/post_template.py with
WP-specific shortcodes stripped and TW2's domain substituted.
"""

import math
import os
import sys
import base64
import datetime
import json
from datetime import timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta

import requests
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.patches import Rectangle

from PIL import Image, ImageDraw

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config
from tw_dateformat import format_date_range

# ──────────────────────────────────────────────────────────────────────────────
# Constants formerly in TW1 config - kept local to avoid polluting TW2 config.
# ──────────────────────────────────────────────────────────────────────────────
MAX_LABELS_TO_SHOW = 10
REPORT_OUTPUT_ROOT = '/var/www/tradewave/r'        # nginx serves this
REPORT_URL_BASE    = '/r'                          # public URL prefix
DOMAIN_ROOT        = (config.domain_root.rstrip('/') + '/') if config.domain_root else 'https://tw2.trxstat.com/'  # absolute base for links
WAVE_VIEWER_PATH   = 'app/'                        # TW2's React app (was TW1's wave-viewer/)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (lifted from create_report.py)
# ──────────────────────────────────────────────────────────────────────────────

def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')


def diff_between_dates(date2, date1):
    d1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(date2, "%Y-%m-%d")
    return (d2 - d1).days


def format_daterange_text(date1, date2):
    # Spaced en-dash range label (house convention) - see tw_dateformat.format_date_range.
    return format_date_range(date1, date2)


def format_date(date_string):
    date = datetime.datetime.strptime(date_string, '%Y-%m-%d')
    day = date.day
    if 11 <= day <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return date.strftime("%b %d{}".format(suffix)).replace(' 0', ' ')


def convert_param_base64(financial_group_id, symbol, date1, days_hold, history_years):
    pipe_str = f'{financial_group_id}|{symbol}|{date1}|{days_hold}|{history_years}'
    return base64.b64encode(pipe_str.encode()).decode()


# ──────────────────────────────────────────────────────────────────────────────
# Data fetchers - call appserver via local URL
# ──────────────────────────────────────────────────────────────────────────────

def get_chart_data(id, opp_date, symbol, days_out, years, zero_last_year, appserver_token):
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"{config.appserver_url}/ChartData4/{id}/{opp_date}/{symbol}/{days_out}/{years}?token={appserver_token}"
    result = requests.get(url, timeout=30).json()
    current_year = int(today_date[:4])
    if result['ChartData4'] and result['ChartData4'][-1]['year'] == current_year and zero_last_year:
        result['ChartData4'][-1]['price'] = '0,0'
        result['ChartData4'][-1]['pct'] = '0,0,0'
    return result


def get_seasonal_chart_data(id, symbol, years, opp_start_date, token, chart_start_date=None):
    """
    chart_start_date is where the trend chart begins (visual frame).
    opp_start_date is where the highlighted box on the chart starts (the pattern itself).
    For most reports they're the same; pass chart_start_date separately only if you
    want a wider visual frame than the pattern itself.
    """
    if chart_start_date is None:
        chart_start_date = opp_start_date
    url = f"{config.appserver_url}/consolidated_seasonal_chart2/{id}/{symbol}/{years}/{chart_start_date}/{opp_start_date}?token={token}"
    result = requests.get(url, timeout=30).json()
    labels = [x[0] for x in result['cons_seas_chart']]
    sea_vals = [x[1] for x in result['cons_seas_chart']]
    return labels, sea_vals


# ──────────────────────────────────────────────────────────────────────────────
# Chart generators - produce PNGs at given filename
# (signatures kept compatible with TW1 to ease future maintenance)
# ──────────────────────────────────────────────────────────────────────────────

def create_barchart(chart_data, years, filename, x1, y1, txt1, x2, y2, txt2, figsize, fontsize):
    bar_data, bar_label, bar_color = [], [], []
    green = (0/255, 153/255, 0/255, 1)
    red = (1, 0, 0, 1)

    for t in chart_data:
        bar_value = float(t['pct'].split(',')[0])
        bar_data.append(bar_value)
        bar_label.append(t['year'])
        bar_color.append(green if bar_value >= 0 else red)

    fig = plt.figure(figsize=figsize, facecolor=(1, 1, 1))
    ax = fig.add_subplot(1, 1, 1)
    ax.tick_params(axis='x', labelsize=20)
    ax.tick_params(axis='y', labelsize=20)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    bar_width = 0
    if years in ('odd', 'even'):
        bar_width = 1.5
    if years[:2] == 'pe':
        bar_width = 3

    plt.xticks(bar_label, color='dimgray')
    plt.yticks(color='dimgray')
    ax.axhline(y=0, color='k', linestyle='-', lw=0.5, zorder=0)
    ax.grid(color='darkgray', linewidth=0.5, axis='y')
    if bar_width > 0:
        ax.bar(bar_label, bar_data, color=bar_color, zorder=3, width=bar_width)
    else:
        ax.bar(bar_label, bar_data, color=bar_color, zorder=3)

    ax.text(x1, y1, txt1, transform=plt.gcf().transFigure, ha='left', fontsize=fontsize)
    ax.text(x2, y2, txt2, transform=plt.gcf().transFigure, ha='right', fontsize=fontsize)

    n = math.ceil(len(chart_data) / MAX_LABELS_TO_SHOW)
    [l.set_visible(False) for (i, l) in enumerate(ax.xaxis.get_ticklabels()) if i % n != 0]

    plt.savefig(filename)
    plt.close()
    return bar_data, bar_label


def create_cumulative_chart(bar_data, bar_label, opp_dir, filename, x1, y1, txt1, x2, y2, txt2, figsize, fontsize):
    cum_data = []
    cr = 1
    for p in bar_data:
        if opp_dir == 'short':
            cr *= (1 + (-p / 100))
        else:
            cr *= (1 + (p / 100))
        cum_data.append((cr * 100) - 100)

    fig = plt.figure(figsize=figsize, facecolor=(1, 1, 1))
    ax = fig.add_subplot(1, 1, 1)
    ax.tick_params(axis='x', labelsize=20)
    ax.tick_params(axis='y', labelsize=20)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.xticks(bar_label, color='dimgray')
    plt.yticks(color='dimgray')
    ax.plot(bar_label, cum_data)
    ax.grid(color='darkgray', linewidth=0.5)
    ax.text(x1, y1, txt1, transform=plt.gcf().transFigure, ha='left', fontsize=fontsize)
    ax.text(x2, y2, txt2, transform=plt.gcf().transFigure, ha='right', fontsize=fontsize)

    n = math.ceil(len(bar_data) / MAX_LABELS_TO_SHOW) if bar_data else 1
    [l.set_visible(False) for (i, l) in enumerate(ax.xaxis.get_ticklabels()) if i % n != 0]

    plt.savefig(filename)
    plt.close()


def create_seasonals_chart(bar_label, labels, sea_vals, date1, date2, opp_dir, filename, x1, y1, txt1, x2, y2, txt2, x3, y3, txt3, figsize, fontsize):
    opp_color = 'red' if opp_dir == 'Short' else 'green'

    fig = plt.figure(figsize=figsize, facecolor=(1, 1, 1))
    ax = fig.add_subplot(1, 1, 1)
    ax.tick_params(axis='y', labelsize=20)
    plt.subplots_adjust(bottom=0.2)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.xticks(bar_label, color='dimgray', rotation=90)
    plt.yticks(color='dimgray')
    ax.plot(labels, sea_vals)
    ax.grid(color='gray', linewidth=0.5, linestyle=':')
    ax.set_xticks(labels[::6])
    ax.set_xticklabels(labels[::6], fontsize=10)

    oppd1 = diff_between_dates(date1, labels[0])
    oppd2 = diff_between_dates(date2, date1)

    rect = Rectangle((oppd1, 0), oppd2, 100, alpha=0.1, fill=True, facecolor=opp_color, edgecolor='black', linewidth=2)
    ax.add_patch(rect)
    ax.text(x1, y1, txt1, transform=plt.gcf().transFigure, ha='left', fontsize=fontsize)
    ax.text(x2, y2, txt2, transform=plt.gcf().transFigure, ha='right', fontsize=fontsize)
    ax.text(x3, y3, txt3, transform=plt.gcf().transFigure, ha='right', fontsize=fontsize)

    plt.savefig(filename)
    plt.close()

    # Hide the year part of the date axis with a white rectangle (TW1 trick - adapting axis format
    # broke the chart layout, so this masks the year labels post-render).
    source_img = Image.open(filename).convert("RGBA")
    draw = ImageDraw.Draw(source_img)
    draw.rectangle(((210, 533), (1220, 570)), fill="white")
    source_img.save(filename)


# ──────────────────────────────────────────────────────────────────────────────
# HTML template strings - lifted from post_template.py, WP shortcodes stripped
# ──────────────────────────────────────────────────────────────────────────────

HTML_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{post_title}</title>
<meta name="description" content="{excerpt}">
<meta property="og:title" content="{post_title}">
<meta property="og:description" content="{excerpt}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical_url}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{canonical_url}">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="shortcut icon" href="/favicon.png">
<link rel="apple-touch-icon" href="/favicon.png">
<link rel="stylesheet" href="/_static/report.css?v={css_version}">
{json_ld}
</head>
<body>
{header_partial}
<section class="report-masthead">
  <div class="report-masthead-inner">
    <div class="report-eyebrow">{eyebrow}</div>
    <h1 class="report-headline">
      <span class="report-company">{company}</span>
      <span class="report-ticker">{symbol}</span>
      <span class="report-direction report-direction-{direction_class}">{direction_upper}</span>
    </h1>
    <div class="report-subtitle">{subtitle}</div>
  </div>
</section>
<main class="container-blog-content">
<div class="report-stats-strip">
  <div class="stat-card"><div class="stat-label">Sharpe</div><div class="stat-value">{sharpe_ratio}</div></div>
  <div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value">{percent_profitable}</div></div>
  <div class="stat-card"><div class="stat-label">Avg Gain</div><div class="stat-value">{avg_profit}</div></div>
  <div class="stat-card"><div class="stat-label">Days Held</div><div class="stat-value">{days_hold}</div></div>
</div>
{report_body}
</main>
{footer_partial}
</body>
</html>"""


HTML_TABLE_TEMPLATE = """
<p class="report-intro">
  Based on <span class="hl">{intro_years_phrase}</span>, TradeWave identified a recurring <span class="hl">{direction_word}</span> seasonal pattern in <span class="hl">{company} ({symbol})</span> between <span class="hl">{date_range_human}</span>. The charts and statistics below show the consistency, risk profile, and year-by-year performance of holding this trade across each historical cycle.
  <br><a class="cta" href="/{wave_viewer_path}?o={param}">Load on Wave Viewer</a>
</p>
<p class="report-meta">Generated {report_date}</p>

<details>
  <summary><h2 class="report-h2-info">{company} TradeWave Opportunity Key Information<span class="info-circle"><i>i</i></span></h2></summary>
  <p class="info-block">
    The financial market is an ever-changing landscape, and investors need to stay on top of key indicators to make informed decisions. The key stats below provide a quick and comprehensive overview of the TradeWave opportunity and its quality.
  </p>
  <h3 class="report-h3">Symbol</h3><p class="info-block"><span class="hl">{symbol}</span> is the unique ticker symbol identifying the financial instrument analyzed in this report.</p>
  <h3 class="report-h3">Trade Direction</h3><p class="info-block">Indicates whether the historical pattern favored the long (buy) or short (sell) side, based on the instrument's performance over the date range.</p>
  <h3 class="report-h3">Date Range</h3><p class="info-block">Specifies the period over which the financial instrument is analyzed.</p>
  <h3 class="report-h3">Days Held</h3><p class="info-block">The holding period this analysis is based on, counted from the start date. The end date is derived from start-date and days-held.</p>
  <h3 class="report-h3">History Years</h3><p class="info-block">The number of years of historical data this report is based on. This report uses <span class="hl">{history_years}</span> years.</p>
  <h3 class="report-h3">Securities Group</h3><p class="info-block">Categorizes the financial instrument by sector, industry, asset class, or market segment.</p>
  <h3 class="report-h3">Number of Winners / Losers</h3><p class="info-block">Counts of trades that resulted in profits vs. losses during the analyzed period - direct measures of reliability and risk.</p>
  <h3 class="report-h3">Percent Profitable</h3><p class="info-block">Percentage of profitable trades out of the total executed.</p>
  <h3 class="report-h3">Average Gain / Average Loss</h3><p class="info-block">Mean gain per winning trade and mean loss per losing trade - drives expected value.</p>
  <h3 class="report-h3">Biggest Winner</h3><p class="info-block">The largest gain from a single trade in the analyzed period.</p>
  <h3 class="report-h3">Median Gain</h3><p class="info-block">The middle value of all gains - reduces the impact of outliers compared to the mean.</p>
  <h3 class="report-h3">Standard Deviation</h3><p class="info-block">Variability of profits and losses. Lower means more consistent; higher means more volatile.</p>
  <h3 class="report-h3">Cumulative Return</h3><p class="info-block">Total return on investment over the analyzed period.</p>
  <h3 class="report-h3">Sharpe Ratio</h3><p class="info-block">Risk-adjusted return. Higher = better return for the level of risk taken.</p>
  <h3 class="report-h3">Trend Long / Trend Short</h3><p class="info-block">Strength of the recent upward and downward trend in the instrument's price.</p>
</details>

<table class="stat-table">
  <tr><td class="stat-td-left">Symbol</td><td class="stat-td-right">{symbol}</td></tr>
  <tr><td class="stat-td-left">Trade Direction</td><td class="stat-td-right">{trade_direction}</td></tr>
  <tr><td class="stat-td-left">Date Range</td><td class="stat-td-right">{date_range_text}</td></tr>
  <tr><td class="stat-td-left">Days Held</td><td class="stat-td-right">{days_hold}</td></tr>
  <tr><td class="stat-td-left">History Years</td><td class="stat-td-right">{history_years}</td></tr>
  <tr><td class="stat-td-left">Securities Group</td><td class="stat-td-right">{securities_group}</td></tr>
  <tr><td class="stat-td-left">Num Winners</td><td class="stat-td-right">{num_winners}</td></tr>
  <tr><td class="stat-td-left">Num Losers</td><td class="stat-td-right">{num_losers}</td></tr>
  <tr><td class="stat-td-left">Percent Profitable</td><td class="stat-td-right">{percent_profitable}</td></tr>
  <tr><td class="stat-td-left">Biggest Winner</td><td class="stat-td-right">{biggest_winner}</td></tr>
  <tr><td class="stat-td-left">Avg Gain</td><td class="stat-td-right">{avg_profit}</td></tr>
  <tr><td class="stat-td-left">Avg Loss</td><td class="stat-td-right">{avg_loss}</td></tr>
  <tr><td class="stat-td-left">Median Gain</td><td class="stat-td-right">{median_profit}</td></tr>
  <tr><td class="stat-td-left">Standard Deviation</td><td class="stat-td-right">{std_dev}</td></tr>
  <tr><td class="stat-td-left">Cumulative Return</td><td class="stat-td-right">{cumulative_return}</td></tr>
  <tr><td class="stat-td-left">Sharpe Ratio</td><td class="stat-td-right">{sharpe_ratio}</td></tr>
  <tr><td class="stat-td-left">Trend Long</td><td class="stat-td-right">{trend_long}</td></tr>
  <tr><td class="stat-td-left">Trend Short</td><td class="stat-td-right">{trend_short}</td></tr>
</table>
"""


def _intro_years_phrase(years):
    """Reader-friendly phrase describing the data filter used in the report.

    Used in the report's intro paragraph so a reader immediately understands
    what historical sample the pattern is based on (e.g. "the last 10 midterm
    election years" instead of opaque tokens like "pe2-10").

    PE-cycle naming follows U.S. politics convention:
      PE / PE0 = presidential election year     (e.g. 2024, 2020)
      PE1      = post-election year             (e.g. 2025, 2021)
      PE2      = midterm election year          (e.g. 2026, 2022)
      PE3      = pre-election year              (e.g. 2027, 2023)
    """
    if years == 'odd':
        return "the last odd-numbered years"
    if years == 'even':
        return "the last even-numbered years"
    if years[:2] == 'pe':
        # "pe2-10" -> cycle "2", count "10" ;  "pe" alone -> cycle "" count "10"
        cycle = years[2:3] if len(years) > 2 and years[2:3].isdigit() else ''
        count = years.split('-')[1] if '-' in years else '10'
        if cycle == '1':
            return f"the last {count} post-election years (the year following each U.S. presidential election)"
        if cycle == '2':
            return f"the last {count} midterm election years"
        if cycle == '3':
            return f"the last {count} pre-election years (the year before each U.S. presidential election)"
        return f"the last {count} U.S. presidential election years"
    return f"the last {years} consecutive years"


def _years_caveat(years):
    if years == 'odd':
        return "filtered to <span class='hl'>Odd</span> years (no US elections)"
    if years == 'even':
        return "filtered to <span class='hl'>Even</span> years (US election years)"
    if years[:2] == 'pe':
        return f"filtered to <span class='hl'>Presidential Election + {years[2:3]}</span> years" if len(years) > 2 else "filtered to <span class='hl'>Presidential Election</span> years"
    return f"covering <span class='hl'>{years}</span> years of history"


def _chart_sections(symbol, date1, date2, years, bar_img, cum_img, sea_img, bar_alt, cum_alt, sea_alt):
    yc = _years_caveat(years)
    return f"""
<details open>
  <summary><h2 class="report-h2-info">{symbol} Gain Loss BarChart<span class="info-circle"><i>i</i></span></h2></summary>
  <p class="info-block">This chart shows the percentage gain or loss of buying <span class="hl">{symbol}</span> on <span class="hl">{date1}</span> and selling on <span class="hl">{date2}</span>. Green = profitable year, red = losing year. Mostly green bars indicate a strong bullish TradeWave pattern; consistent bar sizes indicate low Standard Deviation.</p>
  <p class="info-block">Sharpe Ratio is a critical consistency indicator. ≥ 1.0 typically reflects consistent year-to-year positive outcomes. Note that the historical sample size influences the Sharpe Ratio's interpretation.</p>
  <p class="info-block">Data is {yc}. When assessing the Sharpe Ratio, account for the number of historical years.</p>
</details>
<img class="report-chart" src="{bar_img}" alt="{bar_alt}">

<details open>
  <summary><h2 class="report-h2-info">{symbol} Cumulative Return Chart<span class="info-circle"><i>i</i></span></h2></summary>
  <p class="info-block">Shows the total compounded growth from holding the {symbol} pattern from {date1} to {date2} year-over-year. Useful for understanding long-term trend strength versus single-year volatility.</p>
  <p class="info-block">Compare the slope across years: a steady upward slope suggests a robust pattern; flat or oscillating segments indicate years where the pattern weakened.</p>
</details>
<img class="report-chart" src="{cum_img}" alt="{cum_alt}">

<details open>
  <summary><h2 class="report-h2-info">{symbol} {years} Year TradeWave Trend Chart<span class="info-circle"><i>i</i></span></h2></summary>
  <p class="info-block">The detrended average price movement throughout the year for <span class="hl">{symbol}</span>, {yc}. The shaded box marks the date range opportunity ({date1} to {date2}); its color (green/red) reflects the direction the historical pattern favored.</p>
  <p class="info-block">Use this chart to evaluate how well the date range aligns with historical seasonal trends. Adjusting the window in the Wave Viewer can reveal nearby improvements in profitability or risk.</p>
</details>
<img class="report-chart" src="{sea_img}" alt="{sea_alt}">

<p class="closing">
  TradeWave analysis examines historical patterns in an asset's price movements during specific times of the year. By integrating these insights into trading strategies, investors can anticipate market movements influenced by seasonal trends, economic cycles, and recurring events.
</p>
<p class="closing">
  This report provides a thorough analysis of {symbol}'s historical price movements within the specified date range. Past performance does not guarantee future results - but recurring seasonal patterns offer a data-driven edge for risk management and timing decisions.
</p>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Main render entry point
# ──────────────────────────────────────────────────────────────────────────────

def render(report_dict, appserver_token, post_title, post_slug):
    """
    Render a static HTML report + 3 PNG charts for a saved pattern.

    Args:
      report_dict: the date_range_report_dict assembled in dr_report_publish
      appserver_token: a valid JWT (used to fetch chart data from appserver)
      post_title: human-readable title
      post_slug: URL slug (also used as image filename suffix)

    Returns:
      str: public URL of the rendered report (e.g. "https://tw2.trxstat.com/r/{slug}/")
    """
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    fontsize = 14

    resource_id = report_dict['resourceID']
    symbol      = report_dict['symbol']
    date1       = report_dict['date']
    days_hold   = str(report_dict['days_hold'])
    years       = report_dict['years']
    opp_dir     = report_dict['direction']

    days_hold_corrected = str(int(days_hold) - 1)
    date2 = inc_date_day(date1, int(days_hold_corrected))

    # Output paths
    out_dir = os.path.join(REPORT_OUTPUT_ROOT, post_slug)
    os.makedirs(out_dir, exist_ok=True)
    f_barchart = os.path.join(out_dir, f'gain-loss-barchart-{post_slug}.png')
    f_cumchart = os.path.join(out_dir, f'cumulative-return-{post_slug}.png')
    f_seachart = os.path.join(out_dir, f'trend-chart-{post_slug}.png')

    # Public URLs (relative - nginx serves /r/{slug}/...)
    bar_img = f"{REPORT_URL_BASE}/{post_slug}/gain-loss-barchart-{post_slug}.png"
    cum_img = f"{REPORT_URL_BASE}/{post_slug}/cumulative-return-{post_slug}.png"
    sea_img = f"{REPORT_URL_BASE}/{post_slug}/trend-chart-{post_slug}.png"

    # ── Fetch chart data from appserver ──
    cdata = get_chart_data(resource_id, date1, symbol, days_hold_corrected, years, False, appserver_token)

    # ── Company name lookup ──
    company = symbol
    try:
        symbols_csv = config.available_resources_path[str(resource_id)]
        df = pd.read_csv(symbols_csv)[['symbols', 'name']]
        match = df[df['symbols'] == symbol]
        if not match.empty:
            company = match['name'].iloc[0]
    except Exception:
        pass

    # ── Generate barchart + cumulative ──
    txt1 = 'TradeWave.AI'
    txt2 = f'{symbol} TradeWave Gain Loss Barchart - {date1} to {date2}'
    bar_data, bar_label = create_barchart(cdata['ChartData4'], years, f_barchart,
                                          0.005, 0.01, txt1, 0.99, 0.01, txt2, (14, 6), fontsize)

    # If date1 is today, drop incomplete current year from cumulative calc
    if date1 == today_date:
        bar_data = bar_data[:-1]
        bar_label = bar_label[:-1]

    txt2_cum = f'{symbol} TradeWave Cumulative Return Chart - {date1} to {date2}'
    create_cumulative_chart(bar_data, bar_label, opp_dir, f_cumchart,
                            0.005, 0.01, txt1, 0.99, 0.01, txt2_cum, (14, 6), fontsize)

    # ── Generate seasonals/trend chart ──
    labels, sea_vals = get_seasonal_chart_data(resource_id, symbol, years, date1, appserver_token)
    txt2_sea = f'{symbol} {years} Year TradeWave Trend Chart'
    txt3_sea = f'{date1} to {date2}'
    create_seasonals_chart(bar_label, labels, sea_vals, date1, date2, opp_dir, f_seachart,
                           0.005, 0.01, txt1, 1, 0.01, txt2_sea, 0.99, 0.97, txt3_sea, (14, 6), fontsize)

    # ── Compute biggest winner ──
    if opp_dir == 'long':
        bw = max([float(x['pct'].split(',')[0]) for x in cdata['ChartData4']])
    else:
        bw = -min([float(x['pct'].split(',')[0]) for x in cdata['ChartData4']])

    years_updated = years.upper() if years[:2] == 'pe' else years

    # ── Resource group name ──
    sec_group = config.available_resources.get(str(resource_id), 'Unknown')

    # ── Build the stats-table HTML ──
    # report_date is the human-visible "Generated ..." line; JSON-LD datePublished
    # keeps the ISO today_date (schema.org requires ISO 8601).
    _td = datetime.datetime.strptime(today_date, '%Y-%m-%d')
    table_vars = {
        'report_date'       : f"{_td.strftime('%b')} {_td.day}, {_td.year}",
        'symbol'            : symbol,
        'company'           : company,
        'trade_direction'   : opp_dir.capitalize(),
        'date1'             : date1,
        'date2'             : date2,
        'date_range_text'   : format_daterange_text(date1, date2),
        'days_hold'         : days_hold,
        'history_years'     : years_updated,
        'securities_group'  : sec_group,
        'num_losers'        : cdata['stats'].get('Num Losers', '-'),
        'num_winners'       : cdata['stats'].get('Num Winners', '-'),
        'percent_profitable': cdata['stats'].get('Percent Profitable', '-'),
        'biggest_winner'    : f'{bw:.2f}%',
        'avg_loss'          : cdata['stats'].get('Avg Loss', '-'),
        'avg_profit'        : cdata['stats'].get('Avg Profit', '-'),
        'median_profit'     : cdata['stats'].get('Median Profit', '-'),
        'std_dev'           : cdata['stats'].get('Std Dev', '-'),
        'cumulative_return' : cdata['stats'].get('Cumulative Return', '-'),
        'sharpe_ratio'      : cdata['stats'].get('Sharpe Ratio', '-'),
        'trend_long'        : cdata['stats'].get('Trend Long', '-'),
        'trend_short'       : cdata['stats'].get('Trend Short', '-'),
        'param'             : convert_param_base64(resource_id, symbol, date1, days_hold, years_updated),
        'domain_root'       : DOMAIN_ROOT,
        'wave_viewer_path'  : WAVE_VIEWER_PATH,
        'intro_years_phrase': _intro_years_phrase(years),
        'direction_word'    : opp_dir,  # 'long' or 'short' - reads naturally inline
        'date_range_human'  : f"{datetime.datetime.strptime(date1, '%Y-%m-%d').strftime('%b')} {int(datetime.datetime.strptime(date1, '%Y-%m-%d').strftime('%d'))} and {datetime.datetime.strptime(date2, '%Y-%m-%d').strftime('%b')} {int(datetime.datetime.strptime(date2, '%Y-%m-%d').strftime('%d'))}",
    }
    html_table = HTML_TABLE_TEMPLATE.format(**table_vars)

    # ── Build the chart sections HTML ──
    bar_alt = f'Gain/Loss barchart {symbol} for date range {date1} to {date2}'
    cum_alt = f'Cumulative return chart {symbol} for date range {date1} to {date2}'
    sea_alt = f'TradeWave Trend Chart {symbol} over {years_updated} years'
    chart_sections = _chart_sections(symbol, format_date(date1), format_date(date2), years,
                                     bar_img, cum_img, sea_img, bar_alt, cum_alt, sea_alt)

    # ── Assemble full page ──
    canonical_url = f"{DOMAIN_ROOT}{REPORT_URL_BASE.lstrip('/')}/{post_slug}/"
    excerpt = f"{years_updated}-Year Date Range Report for {company} ({symbol}) - {format_date(date1)} to {format_date(date2)}. Detailed charts and statistics."

    # ── Structured title block (research-note style: eyebrow / headline / subtitle) ──
    # eyebrow: report type label, uppercase. Distinguishes cons (10-YEAR) from
    # PE-cycle (PE2 · 10-YEAR) and odd/even-year filtered patterns.
    if years[:2] == 'pe':
        pe_label = years.upper().split('-')[0]  # "PE2" from "pe2-10"
        pe_years = years.split('-')[1] if '-' in years else '10'
        eyebrow = f"{pe_label} · {pe_years}-YEAR TRADEWAVE PATTERN"
    elif years in ('odd', 'even'):
        eyebrow = f"{years.upper()}-YEAR TRADEWAVE PATTERN"
    else:
        eyebrow = f"{years}-YEAR TRADEWAVE PATTERN"
    headline = f"{company} ({symbol})"
    # Subtitle: human-readable date-range label, e.g. "May 20 - Jun 8, 2026" (en-dash via helper)
    subtitle = format_date_range(date1, date2, with_year=True)

    # Optional: header/footer partials
    header_partial = _read_partial(str(_REPO_ROOT / 'site' / 'templates' / '_tw_header.html'))
    footer_partial = _read_partial('/var/www/tradewave/_partials/tw_app_footer.html')

    # Cache-buster from report.css mtime so a CSS edit invalidates browser
    # cache immediately (nginx serves /_static/ with expires 1d).
    try:
        css_version = int(os.path.getmtime('/var/www/tradewave/_static/report.css'))
    except OSError:
        css_version = 0

    og_image_url = f"{DOMAIN_ROOT}{bar_img.lstrip('/')}"

    # ── JSON-LD (schema.org Article) - LLM/SEO metadata only, no visible content change ──
    json_ld_dict = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post_title,
        "datePublished": today_date,
        "image": og_image_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "publisher": {"@type": "Organization", "name": "TradeWave", "url": "https://tradewave.ai"},
    }
    # Escape "</" so a value can never prematurely close the <script> tag (\/  is a valid
    # JSON escape for '/', so this doesn't change what the JSON decodes to).
    json_ld = '<script type="application/ld+json">' + json.dumps(json_ld_dict).replace('</', '<\\/') + '</script>'

    page_html = HTML_PAGE_TEMPLATE.format(
        post_title=post_title,
        excerpt=excerpt,
        canonical_url=canonical_url,
        og_image=og_image_url,
        json_ld=json_ld,
        header_partial=header_partial,
        report_body=html_table + chart_sections,
        footer_partial=footer_partial,
        css_version=css_version,
        eyebrow=eyebrow,
        headline=headline,
        subtitle=subtitle,
        company=company,
        symbol=symbol,
        direction_class=opp_dir.lower(),
        direction_upper=opp_dir.upper(),
        sharpe_ratio=table_vars['sharpe_ratio'],
        percent_profitable=table_vars['percent_profitable'],
        avg_profit=table_vars['avg_profit'],
        days_hold=days_hold,
    )

    # Write
    out_html = os.path.join(out_dir, 'index.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(page_html)

    # Keep /r/sitemap.xml in sync with what's actually on disk (best-effort - must
    # never fail the render itself).
    try:
        rebuild_report_sitemap()
    except Exception:
        pass

    return canonical_url


def _read_partial(path):
    """Return contents of an HTML partial, or empty string if missing."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ''


# ──────────────────────────────────────────────────────────────────────────────
# Sitemap for /r/ (SEO groundwork) - lists every rendered report so crawlers can
# discover them without following internal links.
# ──────────────────────────────────────────────────────────────────────────────

def rebuild_report_sitemap():
    """Rebuild /var/www/tradewave/r/sitemap.xml from every report currently on disk.

    Lists every {slug}/index.html under REPORT_OUTPUT_ROOT and emits one <url> entry
    per report (lastmod = the index.html's mtime). Written atomically (tmp file +
    os.replace) so a concurrent request never sees a half-written file.

    Called from three places:
      1. render() - after writing a new/refreshed report's index.html.
      2. web/app.py internal_delete_report() - after an rmtree removes a report dir.
      3. report_expiry.py - after its daily expiry sweep deletes anything.
    """
    root = Path(REPORT_OUTPUT_ROOT)
    if not root.is_dir():
        return None

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for index_html in sorted(root.glob('*/index.html')):
        slug = index_html.parent.name
        loc = f"{DOMAIN_ROOT}{REPORT_URL_BASE.lstrip('/')}/{slug}/"
        try:
            lastmod = datetime.datetime.fromtimestamp(index_html.stat().st_mtime).strftime('%Y-%m-%d')
        except OSError:
            continue
        lines.append('  <url>')
        lines.append(f'    <loc>{loc}</loc>')
        lines.append(f'    <lastmod>{lastmod}</lastmod>')
        lines.append('  </url>')
    lines.append('</urlset>')

    sitemap_path = root / 'sitemap.xml'
    tmp_path = root / '.sitemap.xml.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp_path, sitemap_path)
    return str(sitemap_path)
