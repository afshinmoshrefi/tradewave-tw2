#!/usr/bin/env python3
"""
generate_security_pages.py (TW2 marketing-site version)
========================================================
Lifted from .151:/home/flask/blog/generate_security_pages.py.

Generates dark-themed security detail pages for the TradeWave marketing
site at /var/www/tradewave/markets/{slug}.html.

Reads _page_data.json (saved by /home/flask/smn/generate_security_pages.py),
copies chart images, and outputs dark-themed HTML to TradeWave's marketing
markets/ directory (NOT _static/markets/, which is the old SMN-style path
that generate_tw_security_pages.py writes to).

Charts are written under markets/charts/ relative to the marketing root.

Cron: 30 5 * * 1-5 (after the SMN generator runs).
"""

import os, sys, json, shutil, re
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/smn')  # reuse SMN heavy lifting + dark theme bits
sys.path.insert(0, '/home/flask/site/lib')  # text_utils.no_em_dash
import config

import requests

from get_price_eod import get_quote_details
from text_utils import no_em_dash
from ga_snippet import ga_head_snippet

# Reuse the SMN generator (heavy lifting: build_security_page, _build_*_html,
# SECURITY_PAGES list, _fmt_price, _fmt_change, etc.)
import generate_security_pages as gsp

# Reuse the dark-theme overrides from the existing TW generator so we keep
# branding consistent without duplicating CSS / header / CTA / footer code.
import generate_tw_security_pages as tw


# =============================================================================
# CANONICAL TW2 HEADER PARTIAL
# =============================================================================
# Single source of truth for the TW2 site nav. Read at build time and spliced
# into every dark security page so the menu stays in lockstep with the home
# page and the React /app shell. See /home/flask/site/templates/_tw_header.html.
# (The marketing-site generator inherits this through tw._dark_header_html,
# which is monkey-patched onto gsp._build_header_html below; this constant is
# defined here too as a defensive backstop in case the partial is ever read
# outside of the tw module.)

_HEADER_PARTIAL_PATH = '/home/flask/site/templates/_tw_header.html'

def _read_header_partial():
    try:
        with open(_HEADER_PARTIAL_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ''

# =============================================================================
# CONFIGURATION
# =============================================================================

# Input: data exported by /home/flask/smn/generate_security_pages.py
SMN_MARKETS_DIR = Path(config.news_root_folder) / "markets"
SMN_CHARTS_DIR = SMN_MARKETS_DIR / "charts"
PAGE_DATA_FILE = SMN_MARKETS_DIR / "_page_data.json"

# Output: TradeWave marketing-site markets directory
# (distinct from /_static/markets/ used by generate_tw_security_pages.py)
TW_MARKETS_DIR = Path(config.web_root_dir) / "markets"
TW_CHARTS_DIR = TW_MARKETS_DIR / "charts"

# Canonical TradeWave domain - driven by config.domain_root (TW2_DOMAIN_ROOT).
# Falls back to https://tw2.trxstat.com/ if unset (ad-hoc dev runs).
DOMAIN_ROOT = (config.domain_root.rstrip('/') + '/') if config.domain_root else "https://tw2.trxstat.com/"


# =============================================================================
# NAVY MARKET BAR - PIXEL-IDENTICAL TO THE HOME PAGE
# =============================================================================
# The home page market bar (/var/www/tradewave/home.html) is the approved
# design. Index pages MUST match it in structure AND look. The home bar uses
# navy palette tokens; the index-page theme has no such tokens, so the CSS
# below is SELF-CONTAINED with LITERAL colors equal to the resolved home
# tokens:
#   --bg #0B1220  --panel #0F1A2E  --line rgba(255,255,255,.09)
#   --ink #EAF0F8 (symbol)  --muted #9FB0C8 (item/price)
#   --win #3FB68B (up)  --loss #E5687F (down)
# It is appended as the LAST rules in the page <style> so it overrides the
# old blue var-based .market-bar rules (and their mobile media query) by
# source order, theme-independent. The home bar also uses 'JetBrains Mono';
# we add that font link so the bar is pixel-identical (see main()).

# Short labels exactly as the home bar renders them.
_MARKET_BAR_SHORT_LABELS = {
    "S&P 500": "S&P 500",
    "Dow Jones Industrial Average": "DOW",
    "NASDAQ Composite": "NASDAQ",
    "CBOE Volatility Index": "VIX",
    "Crude Oil (WTI)": "CRUDE",
    "Natural Gas": "NAT GAS",
    "Gold": "GOLD",
}


def _navy_market_bar_css():
    """Self-contained navy .market-bar CSS, literal colors = resolved home
    tokens, identical paddings/fonts/gap/scroll behavior to the home bar.
    Emitted last in the <style> so it wins over the old blue rules."""
    return """
        /* Unified market bar - pixel-identical to the home page (literal navy
           colors; self-contained so it is independent of the page theme). */
        .market-bar{background:#0F1A2E;border-top:none;border-bottom:1px solid rgba(255,255,255,.09);padding:8px 0;overflow-x:auto;scrollbar-width:none}
        .market-bar::-webkit-scrollbar{display:none}
        .market-bar-content{display:flex;gap:22px;align-items:center;padding:0 24px;width:max-content;min-width:100%;max-width:none;margin:0 auto;justify-content:center}
        .market-item{display:flex;align-items:center;gap:7px;font-family:'JetBrains Mono',monospace;font-size:.78rem;white-space:nowrap;color:#9FB0C8;text-decoration:none;padding:0;border-top:none;border-bottom:none;border-image:none}
        .market-item.up,.market-item.down{border-image:none}
        .market-item .market-symbol{color:#EAF0F8;font-weight:700}
        .market-item .market-price{color:#9FB0C8;font-weight:700}
        .market-item .market-change{font-weight:700}
        .market-item .market-change.up{color:#3FB68B}
        .market-item .market-change.down{color:#E5687F}
"""


def _dark_market_bar_html(current_slug=None, all_quotes=None):
    """Market bar matching the home page EXACTLY: same classes, same per-ticker
    <a href="/markets/<slug>.html"> with market-symbol / market-price /
    market-change up|down, same ticker set + order (the SECURITY_PAGES order:
    S&P 500 / DOW / NASDAQ / VIX / CRUDE / NAT GAS / GOLD). The /markets/<slug>
    href is what the live refresher (refresh_market_quotes.py) keys on, so each
    item live-syncs to the same /assets/quotes.json values as the home bar."""
    items_html = ""
    for sec in gsp.SECURITY_PAGES:
        quote = (all_quotes or {}).get(sec["symbol"]) or get_quote_details(sec["symbol"], sec["exchange"])
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
            price_fmt = f"{price:,.2f}"
            chg_fmt = f"{sign}{change_p:.2f}%"
        else:
            price_fmt = ""
            chg_fmt = ""
            direction = "down"

        short_label = _MARKET_BAR_SHORT_LABELS.get(sec["label"], sec["label"])

        # Marketing-site path: /markets/<slug>.html - the refresher keys on this.
        href = f'/markets/{sec["slug"]}.html'
        price_span = f'<span class="market-price">{price_fmt}</span>' if price_fmt else ''
        chg_span = (f'<span class="market-change {direction}">{chg_fmt}</span>'
                    if chg_fmt else '')
        items_html += f'''
            <a href="{href}" class="market-item">
                <span class="market-symbol">{short_label}</span>
                {price_span}
                {chg_span}
            </a>'''

    return f'''
    <div class="market-bar">
        <div class="market-bar-content">
            {items_html}
        </div>
    </div>'''


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("[TW MARKETING SECURITY PAGES] Starting (output: %s)" % TW_MARKETS_DIR)

    # Check for SMN-generated page data
    if not PAGE_DATA_FILE.exists():
        print("  ERROR: %s not found. Run /home/flask/smn/generate_security_pages.py first." % PAGE_DATA_FILE)
        return

    # Load exported data
    with open(str(PAGE_DATA_FILE), 'r') as f:
        page_data = json.load(f)
    print("  Loaded page data for %d securities" % len(page_data))

    # Create output dirs
    TW_MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    TW_CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy chart images from SMN to TW marketing markets/charts/
    if SMN_CHARTS_DIR.exists():
        chart_count = 0
        for chart_file in SMN_CHARTS_DIR.glob("*.jpg"):
            dest = TW_CHARTS_DIR / chart_file.name
            shutil.copy2(str(chart_file), str(dest))
            chart_count += 1
        print("  Copied %d chart images" % chart_count)

    # Fetch quotes for market bar
    print("  Fetching quotes for market bar...")
    all_quotes = {}
    for sec in gsp.SECURITY_PAGES:
        q = get_quote_details(sec["symbol"], sec["exchange"])
        if q:
            all_quotes[sec["symbol"]] = q

    # Monkey-patch the display functions to use dark theme + marketing-site links
    original_base_css = gsp._build_base_css
    original_header = gsp._build_header_html
    original_cta = gsp._build_cta_html
    original_footer = gsp._build_footer_html
    original_market_bar = gsp._build_market_bar_html

    # The page <style> is `_build_base_css() + _build_page_css()`. Append the
    # self-contained navy market-bar CSS to the END of _build_page_css() so it
    # is the LAST market-bar CSS in the document - this overrides BOTH the old
    # blue var-based rules in base CSS AND the mobile @media .market-bar-content
    # override at the tail of page CSS (the home bar has no mobile override, so
    # ours must win at every width). Result: pixel-identical, theme-independent.
    original_page_css = gsp._build_page_css

    def _page_css_navy():
        return original_page_css() + "\n" + _navy_market_bar_css()

    gsp._build_base_css = tw._dark_base_css
    gsp._build_page_css = _page_css_navy
    gsp._build_header_html = tw._dark_header_html
    gsp._build_cta_html = tw._dark_cta_html
    gsp._build_footer_html = tw._dark_footer_html
    gsp._build_market_bar_html = _dark_market_bar_html  # local: navy bar, marketing-site links

    # Patch site URL references
    original_site_url = gsp.SITE_URL
    gsp.SITE_URL = DOMAIN_ROOT.rstrip('/')

    # Generate dark pages
    generated = []
    for sec in gsp.SECURITY_PAGES:
        slug = sec["slug"]
        pd = page_data.get(slug)
        if not pd:
            print("  WARNING: No data for %s, skipping" % slug)
            continue

        # Use dark chart URLs, falling back to light if missing
        dark_urls = pd.get("dark_chart_urls", {})
        source_urls = dark_urls if dark_urls else pd.get("chart_urls", {})
        tw_chart_urls = {}
        for key, url in source_urls.items():
            # Marketing-site charts live at /markets/charts/...
            filename = url.split("/")[-1]
            tw_chart_urls[key] = "/markets/charts/%s" % filename

        html = gsp.build_security_page(
            pd["sec"], pd.get("quote", {}), [], [],  # no news, no related for TW
            tw_chart_urls, pd.get("max_pe", 0),
            projection_targets=pd.get("projection_targets", {}),
            projection_stats=pd.get("projection_stats", {}),
            ai_analysis=pd.get("ai_analysis"),
            usage_guide=pd.get("usage_guide"),
            all_quotes=all_quotes,
            all_ai_snippets={},
            price_history={},
        )

        # Load 'JetBrains Mono' so the unified navy market bar uses the SAME
        # font as the home page bar (pixel-identical). The base head only
        # requests Inter + IBM Plex Mono; add JetBrains Mono once, before the
        # existing Google Fonts stylesheet link.
        if 'JetBrains+Mono' not in html and 'fonts.googleapis.com/css2' in html:
            html = html.replace(
                '<link href="https://fonts.googleapis.com/css2',
                '<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">\n    <link href="https://fonts.googleapis.com/css2',
                1)

        # Replace SMN favicon with TW favicon
        html = html.replace(config.smn_favicon, config.tw_favicon)

        # Replace SMN title branding
        html = html.replace("| Seasonal Market News", "| TradeWave")
        html = html.replace("Seasonal Market News", "TradeWave")

        # Strip any leftover SMN dev-host or LAN-IP references in the dark
        # TW marketing pages so nothing leaks private hostnames out to crawlers.
        # (Pages live at /markets/ - no /_static/ rewrite needed.)
        for stale in ('http://192.168.1.151:9000', 'http://192.168.1.151',
                      'http://192.168.1.176'):
            html = html.replace(f'{stale}/markets/',
                                f'{DOMAIN_ROOT.rstrip("/")}/markets/')
            html = html.replace(f'"{stale}/"',
                                f'"{DOMAIN_ROOT.rstrip("/")}/"')
            html = html.replace(f'"{stale}"',
                                f'"{DOMAIN_ROOT.rstrip("/")}"')

        # GA4 snippet (the SMN-built head has none; '' when the id is unset).
        ga = ga_head_snippet()
        if ga and '</head>' in html:
            html = html.replace('</head>', ga + '\n</head>', 1)

        # Defensive em-dash sweep before write (project rule: no U+2014).
        html = no_em_dash(html)

        out_path = TW_MARKETS_DIR / ("%s.html" % slug)
        out_path.write_text(html, "utf-8")
        print("  -> Wrote %s (%s bytes)" % (out_path, format(len(html), ',')))
        generated.append(slug)

    # Restore originals
    gsp._build_base_css = original_base_css
    gsp._build_page_css = original_page_css
    gsp._build_header_html = original_header
    gsp._build_cta_html = original_cta
    gsp._build_footer_html = original_footer
    gsp._build_market_bar_html = original_market_bar
    gsp.SITE_URL = original_site_url

    print("\n[TW MARKETING SECURITY PAGES] Done. Generated %d pages: %s" % (
        len(generated), ", ".join(generated)))


if __name__ == "__main__":
    main()
