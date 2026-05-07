#!/usr/bin/env python3
"""
TradeWave Programmatic SEO - Ticker Page Generator (Phase B)

For each Phase 1 ticker:
  1. Collect per-ticker data via ticker_data.collect_ticker_data().
  2. Render templates/ticker.html via Jinja2.
  3. Write {output_dir}/{SYMBOL}.html.

After all pages are rendered, write a sitemap.xml.

Usage:
    python generate_ticker_pages.py
    python generate_ticker_pages.py --tickers AAPL,JPM,SPY
    python generate_ticker_pages.py --tickers AAPL,JPM,SPY --out /tmp/ticker_test/

Paths, URLs, and config come from /home/flask/config.py. No env vars.
"""

import argparse
import datetime
import json
import os
import sys
import time

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Central config.
sys.path.insert(0, '/home/flask')
import config

# Phase A artifacts.
sys.path.insert(0, '/home/flask/site/ticker_pages')
from ticker_data import (
    login_appserver,
    fetch_realtime_prices,
    collect_ticker_data,
)
from generate_og_images import generate_all_og_images

# -------------------------------------------------------------------
# Paths and URLs (hardcoded per project conventions, no env vars).
# -------------------------------------------------------------------

TICKER_PAGES_DIR = '/home/flask/site/ticker_pages'
TEMPLATE_DIR = '/home/flask/site/ticker_pages/templates'
TEMPLATE_NAME = 'ticker.html'
HUB_TEMPLATE_NAME = 'patterns_index.html'

TICKER_LIST_JSON = '/home/flask/site/ticker_pages/data/ticker_list_phase1.json'
SECTOR_MAP_JSON = '/home/flask/site/ticker_pages/data/sector_map.json'

WEB_ROOT_DIR = config.web_root_dir  # TW2: /var/www/tradewave/
DEFAULT_OUTPUT_DIR = os.path.join(WEB_ROOT_DIR, 'patterns') + os.sep

# Production-facing URL base for the sitemap. Per PRD section 6.5 this is
# always the canonical tradewave.ai domain, regardless of where the files
# actually get written on this dev box.
PUBLIC_URL_BASE = 'https://tradewave.ai/patterns/'

# Signup / upgrade URLs, same pattern as /home/flask/blog/generate_home_page.py.
DOMAIN_ROOT = config.domain_root
SIGNUP_URL = '%sregister/?lid=1' % DOMAIN_ROOT
UPGRADE_URL = '%smy-account/?ihc_ap_menu=subscription' % DOMAIN_ROOT


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _safe_float(val, default=None):
    """Coerce a value to float, returning default if it can't be converted."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def load_ticker_list():
    with open(TICKER_LIST_JSON) as f:
        return json.load(f)


def load_sector_map():
    if not os.path.isfile(SECTOR_MAP_JSON):
        return {}
    with open(SECTOR_MAP_JSON) as f:
        return json.load(f)


def build_jinja_env():
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(['html', 'xml']),
    )
    return env


def year_breakdown_to_labeled(year_breakdown):
    """compute_election_cycle returns {1: v, 2: v, 3: v, 4: v}; the template
    expects election_cycle_breakdown keyed by 'Year 1'..'Year 4'."""
    if not year_breakdown:
        return None
    labeled = {}
    for i in (1, 2, 3, 4):
        v = year_breakdown.get(i)
        if v is None:
            # Some dicts may have string keys coming back from JSON round-trips.
            v = year_breakdown.get(str(i))
        labeled['Year %d' % i] = v
    return labeled


def enough_data_to_render(data):
    """Template requires at least monthly_returns with best_month + worst_month
    entries. If those aren't present we skip the ticker (would crash template)."""
    if not data:
        return False
    mr = data.get('monthly_returns') or {}
    best = data.get('best_month')
    worst = data.get('worst_month')
    if not best or not worst:
        return False
    if best not in mr or worst not in mr:
        return False
    if not isinstance(mr.get(best), dict) or 'avg_return' not in mr[best]:
        return False
    return True


def build_meta_description(data, max_len=160):
    """Build a <=160 char meta description. When a forward_outlook is present,
    lead with the 30-day AI outlook. Otherwise fall back to monthly seasonality
    facts. Truncates progressively to stay under max_len."""
    sym = data['symbol']
    company = data.get('company_name') or sym
    years = data.get('years_of_data') or 0
    monthly = data.get('monthly_returns') or {}
    best = data.get('best_month')
    worst = data.get('worst_month')
    best_ret = monthly.get(best, {}).get('avg_return') if best else None
    worst_ret = monthly.get(worst, {}).get('avg_return') if worst else None
    fo = data.get('forward_outlook') or {}

    def fmt_pct(v):
        return ('%+.1f%%' % v) if v is not None else 'n/a'

    has_forward = bool(fo) and fo.get('ai_score') is not None

    if has_forward:
        candidates = [
            '%s (%s) 30-day AI outlook: %s bias, score %.1f (%d-yr avg %s). Best month: %s. Updated daily.' % (
                sym, company, fo['direction_label'], fo['ai_score'], len(fo.get('sample_years') or []),
                fmt_pct(fo.get('avg_return')), best or 'n/a'),
            '%s 30-day AI outlook: %s bias, score %.1f (%d-yr avg %s). Best month: %s. Updated daily.' % (
                sym, fo['direction_label'], fo['ai_score'], len(fo.get('sample_years') or []),
                fmt_pct(fo.get('avg_return')), best or 'n/a'),
            '%s 30-day AI outlook: %s bias, score %.1f. Best month: %s. Updated daily.' % (
                sym, fo['direction_label'], fo['ai_score'], best or 'n/a'),
            '%s 30-day AI outlook: %s bias, AI score %.1f. Updated daily.' % (
                sym, fo['direction_label'], fo['ai_score']),
        ]
        for c in candidates:
            if len(c) <= max_len:
                return c

    # Fallback: monthly seasonality description.
    for include_company in (True, False):
        prefix = '%s (%s) seasonal pattern analysis based on %d years of data.' % (sym, company, years) \
            if include_company else \
            '%s seasonal pattern analysis based on %d years of data.' % (sym, years)
        best_clause = ' Best month: %s (%s avg).' % (best or 'n/a', fmt_pct(best_ret))
        worst_clause = ' Worst month: %s (%s avg).' % (worst or 'n/a', fmt_pct(worst_ret))
        candidates = [
            prefix + best_clause + worst_clause + ' Updated daily.',
            prefix + best_clause + ' Updated daily.',
        ]
        for c in candidates:
            if len(c) <= max_len:
                return c

    fallback = '%s seasonal pattern analysis based on %d years of data. Updated daily.' % (sym, years)
    return fallback[:max_len]


def build_cycle_faq_schema_text(data):
    """Plain-text cycle-cycle FAQ answer used in JSON-LD schema markup."""
    sym = data['symbol']
    label = data.get('cycle_phase_label') or 'this cycle phase'
    sample = data.get('cycle_phase_sample_years') or []
    monthly = data.get('monthly_returns') or {}
    cyc = data.get('cycle_phase_monthly') or {}
    if not sample or not monthly or not cyc:
        avg = data.get('election_cycle_avg')
        if avg is None:
            return '%s cycle filtering is not yet available.' % sym
        return 'In %s years, %s has averaged %+.1f%% per year across its history.' % (label.lower(), sym, avg)
    deltas = []
    for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']:
        a = monthly.get(m, {}).get('avg_return')
        c = cyc.get(m, {}).get('avg_return') if cyc.get(m) else None
        if a is not None and c is not None:
            deltas.append((m, a, c, c - a))
    if not deltas:
        return 'In %s years, %s has limited cycle-phase monthly samples.' % (label.lower(), sym)
    deltas_sorted = sorted(deltas, key=lambda x: x[3])
    worst = deltas_sorted[0]
    best = deltas_sorted[-1]
    return ('Yes. In prior %s years (%d samples), %s\'s biggest cycle-phase divergence is %s '
            '(%+.1f%% in this phase versus %+.1f%% all-years). The strongest cycle-phase tailwind is %s '
            '(%+.1f%% in this phase versus %+.1f%% all-years).') % (
        label.lower(), len(sample), sym, worst[0], worst[2], worst[1], best[0], best[2], best[1])


def render_ticker_page(env, data, ticker_meta, sector_map, current_year, generated_at,
                       hub_entries_map=None):
    """Turn a page_data dict into rendered HTML. Fills in fields the template
    needs that collect_ticker_data doesn't produce (company_name fallback,
    related_tickers, signup/upgrade URLs, generated_at, labeled cycle breakdown).
    """
    symbol = data['symbol']

    # Company name fallback from the curated ticker list.
    if not data.get('company_name') and ticker_meta:
        data['company_name'] = ticker_meta.get('name')

    # Related tickers from sector_map.json.
    related = sector_map.get(symbol, []) or []
    # Defensive: template iterates, so ensure list of strings.
    related_tickers = [str(r) for r in related if r and r != symbol]

    # Build rich related ticker data for the cards (company name, AI score, best month).
    related_tickers_data = []
    if hub_entries_map:
        for rt_sym in related_tickers:
            entry = hub_entries_map.get(rt_sym)
            if entry:
                related_tickers_data.append(entry)

    # Template expects election_cycle_breakdown with 'Year 1'..'Year 4' keys.
    election_cycle_breakdown = year_breakdown_to_labeled(data.get('year_breakdown'))

    template = env.get_template(TEMPLATE_NAME)
    return template.render(
        # Core from collect_ticker_data.
        symbol=data['symbol'],
        company_name=data.get('company_name') or data['symbol'],
        current_price=_safe_float(data.get('current_price'), 0.0),
        price_change_pct=_safe_float(data.get('price_change_pct')),
        monthly_returns=data.get('monthly_returns') or {},
        best_month=data.get('best_month'),
        worst_month=data.get('worst_month'),
        active_patterns=data.get('active_patterns') or [],
        ai_score=data.get('ai_score'),
        win_prob=data.get('win_prob'),
        pred_return=data.get('pred_return'),
        pred_mfe=data.get('pred_mfe'),
        forward_outlook=data.get('forward_outlook'),
        is_etf=data.get('is_etf', False),
        election_year_type=data.get('election_year_type') or 'this cycle phase',
        election_cycle_avg=data.get('election_cycle_avg') if data.get('election_cycle_avg') is not None else 0.0,
        election_cycle_breakdown=election_cycle_breakdown,
        cycle_phase_monthly=data.get('cycle_phase_monthly') or {},
        cycle_phase_label=data.get('cycle_phase_label'),
        cycle_phase_sample_years=data.get('cycle_phase_sample_years') or [],
        cycle_faq_schema_text=build_cycle_faq_schema_text(data),
        next_earnings_est=data.get('next_earnings_est'),
        days_to_earnings=data.get('days_to_earnings'),
        years_of_data=data.get('years_of_data'),
        first_year=data.get('first_year'),

        # Added by the orchestrator.
        current_year=current_year,
        related_tickers=related_tickers,
        related_tickers_data=related_tickers_data,
        total_tickers=len(hub_entries_map) if hub_entries_map else len(related_tickers),
        signup_url=SIGNUP_URL,
        upgrade_url=UPGRADE_URL,
        generated_at=generated_at,
        meta_description=build_meta_description(data),
        favicon=config.tw_favicon,
    )


def render_hub_page(env, hub_entries, current_year, generated_at):
    """Render the /patterns/ index page listing all tickers with summary data."""
    # Sort: tickers with AI scores first (descending), then alphabetical.
    def sort_key(t):
        has_score = t.get('ai_score') is not None
        return (0 if has_score else 1, -(t.get('ai_score') or 0), t['symbol'])

    sorted_tickers = sorted(hub_entries, key=sort_key)

    # Unique sectors in display order.
    seen = set()
    sectors = []
    for t in sorted_tickers:
        s = t.get('sector') or 'Other'
        if s not in seen:
            seen.add(s)
            sectors.append(s)

    template = env.get_template(HUB_TEMPLATE_NAME)
    return template.render(
        tickers=sorted_tickers,
        sectors=sectors,
        current_year=current_year,
        generated_at=generated_at,
        signup_url=SIGNUP_URL,
        upgrade_url=UPGRADE_URL,
        favicon=config.tw_favicon,
    )


def write_sitemap(output_dir, rendered_symbols, today_iso):
    """Write sitemap.xml listing the hub page and every rendered ticker page."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    # Hub page first, higher priority.
    lines.append('  <url>')
    lines.append('    <loc>https://tradewave.ai/patterns/</loc>')
    lines.append('    <lastmod>%s</lastmod>' % today_iso)
    lines.append('  </url>')
    for sym in rendered_symbols:
        loc = '%s%s' % (PUBLIC_URL_BASE, sym)
        lines.append('  <url>')
        lines.append('    <loc>%s</loc>' % loc)
        lines.append('    <lastmod>%s</lastmod>' % today_iso)
        lines.append('  </url>')
    lines.append('</urlset>')
    sitemap_path = os.path.join(output_dir, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return sitemap_path


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate TradeWave ticker SEO pages.')
    parser.add_argument(
        '--tickers',
        default=None,
        help='Comma-separated list of tickers to render (e.g. AAPL,JPM,SPY). Defaults to all Phase 1 tickers.',
    )
    parser.add_argument(
        '--out',
        default=DEFAULT_OUTPUT_DIR,
        help='Output directory. Defaults to {web_root}/_static/patterns/.',
    )
    args = parser.parse_args()

    output_dir = args.out
    if not output_dir.endswith(os.sep):
        output_dir = output_dir + os.sep
    os.makedirs(output_dir, exist_ok=True)

    start = time.time()
    today = datetime.date.today()
    today_iso = today.strftime('%Y-%m-%d')
    current_year = today.year

    # Load ticker list and subset if --tickers given.
    full_list = load_ticker_list()
    if args.tickers:
        want = {t.strip().upper() for t in args.tickers.split(',') if t.strip()}
        tickers = [t for t in full_list if t['symbol'].upper() in want]
        found_syms = {t['symbol'].upper() for t in tickers}
        missing = want - found_syms
        if missing:
            # Allow tickers not in the Phase 1 list by synthesizing a meta row.
            for sym in missing:
                tickers.append({'symbol': sym, 'name': None, 'sector': None})
    else:
        tickers = full_list

    sector_map = load_sector_map()

    print('Logging into appserver...')
    session = login_appserver()
    if not getattr(session, 'token', None):
        print('WARNING: appserver login failed. Pattern + score sections will be empty.')

    print('Fetching realtime prices...')
    prices = fetch_realtime_prices()
    print('  got %d symbols' % len(prices))

    env = build_jinja_env()

    # --- Pass 1: Collect all ticker data ---
    all_data = {}  # symbol -> (data, meta)
    hub_entries = []
    skipped = []
    failed = []

    for meta in tickers:
        symbol = meta['symbol'].upper()
        t0 = time.time()
        try:
            data = collect_ticker_data(symbol, session, prices)
        except Exception as e:
            print('  [%s] collect_ticker_data raised: %s' % (symbol, e))
            failed.append(symbol)
            continue

        if not enough_data_to_render(data):
            print('  [%s] skipping: insufficient monthly seasonality data' % symbol)
            skipped.append(symbol)
            continue

        elapsed = time.time() - t0
        patterns = data.get('active_patterns') or []
        ai = data.get('ai_score')
        print('  [%s] %.2fs  patterns=%d  ai_score=%s  price=%s'
              % (symbol, elapsed, len(patterns), ai, data.get('current_price')))

        all_data[symbol] = (data, meta)

        # Collect summary for hub page, OG images, and related ticker cards.
        monthly = data.get('monthly_returns') or {}
        best = data.get('best_month')
        worst = data.get('worst_month')
        hub_entries.append({
            'symbol': symbol,
            'company_name': data.get('company_name') or meta.get('name') or symbol,
            'sector': meta.get('sector') or 'Other',
            'ai_score': data.get('ai_score'),
            'best_month': best,
            'best_month_return': monthly.get(best, {}).get('avg_return') if best else None,
            'worst_month': worst,
            'worst_month_return': monthly.get(worst, {}).get('avg_return') if worst else None,
            'active_patterns': len(patterns),
            'monthly_returns': monthly,
            'years_of_data': data.get('years_of_data') or 0,
        })

    # Build lookup map for related ticker cards.
    hub_entries_map = {e['symbol']: e for e in hub_entries}

    # --- Pass 2: Render all pages (now that related data is available) ---
    rendered = []
    for symbol, (data, meta) in all_data.items():
        try:
            html = render_ticker_page(
                env=env,
                data=data,
                ticker_meta=meta,
                sector_map=sector_map,
                current_year=current_year,
                generated_at=today_iso,
                hub_entries_map=hub_entries_map,
            )
        except Exception as e:
            print('  [%s] render failed: %s' % (symbol, e))
            failed.append(symbol)
            continue

        out_path = os.path.join(output_dir, '%s.html' % symbol)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html)
        except Exception as e:
            print('  [%s] write failed: %s' % (symbol, e))
            failed.append(symbol)
            continue

        rendered.append(symbol)

    # Sitemap over rendered pages only.
    sitemap_path = None
    if rendered:
        sitemap_path = write_sitemap(output_dir, rendered, today_iso)

    # OG images for social sharing.
    if hub_entries:
        og_count = generate_all_og_images(hub_entries, output_dir)
        print('  OG images: %d generated' % og_count)

    # Hub / index page.
    hub_path = None
    if hub_entries:
        try:
            hub_html = render_hub_page(env, hub_entries, current_year, today_iso)
            hub_path = os.path.join(output_dir, 'index.html')
            with open(hub_path, 'w', encoding='utf-8') as f:
                f.write(hub_html)
            print('  Hub page: %s (%d tickers)' % (hub_path, len(hub_entries)))
        except Exception as e:
            print('  Hub page render failed: %s' % e)

    total = time.time() - start
    print('')
    print('=' * 60)
    print('Ticker page generation summary')
    print('=' * 60)
    print('Output dir:     %s' % output_dir)
    print('Rendered:       %d' % len(rendered))
    print('Skipped:        %d  %s' % (len(skipped), skipped if skipped else ''))
    print('Failed:         %d  %s' % (len(failed), failed if failed else ''))
    if sitemap_path:
        print('Sitemap:        %s' % sitemap_path)
    if hub_path:
        print('Hub page:       %s' % hub_path)
    print('Elapsed:        %.1fs' % total)


if __name__ == '__main__':
    main()
