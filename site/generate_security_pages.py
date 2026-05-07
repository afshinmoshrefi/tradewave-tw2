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
import config

import requests

from get_price_eod import get_quote_details

# Reuse the SMN generator (heavy lifting: build_security_page, _build_*_html,
# SECURITY_PAGES list, _fmt_price, _fmt_change, etc.)
import generate_security_pages as gsp

# Reuse the dark-theme overrides from the existing TW generator so we keep
# branding consistent without duplicating CSS / header / CTA / footer code.
import generate_tw_security_pages as tw

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

# Canonical TradeWave domain — pinned so generated metadata never leaks the
# LAN IP from config.domain_root into canonical/og:url/JSON-LD or hrefs.
# TODO(prod-cutover): swap to https://tradewave.ai/.
DOMAIN_ROOT = "https://tw2.trxstat.com/"


# =============================================================================
# DARK MARKET BAR — LINKS POINT TO /markets/ (NOT /_static/markets/)
# =============================================================================

def _dark_market_bar_html(current_slug=None, all_quotes=None):
    """Market bar with links pointing to TW marketing-site dark pages."""
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
            direction = "flat"

        short_labels = {"Dow Jones Industrial Average": "DOW", "NASDAQ Composite": "NASDAQ",
                        "CBOE Volatility Index": "VIX", "Crude Oil (WTI)": "CRUDE",
                        "Natural Gas": "NAT GAS"}
        short_label = short_labels.get(sec["label"], sec["label"])
        is_current = sec["slug"] == current_slug
        active_cls = " current" if is_current else ""

        # Marketing-site path: /markets/<slug>.html
        href = f'/markets/{sec["slug"]}.html'
        items_html += f'''
            <a href="{href}" class="market-item {direction}{active_cls}">
                <span class="market-symbol">{short_label}</span>
                {f'<span class="market-price">{price_fmt}</span>' if price_fmt else ''}
                {"<span class='market-change " + direction + "'>" + chg_fmt + "</span>" if chg_fmt else ""}
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

    gsp._build_base_css = tw._dark_base_css
    gsp._build_header_html = tw._dark_header_html
    gsp._build_cta_html = tw._dark_cta_html
    gsp._build_footer_html = tw._dark_footer_html
    gsp._build_market_bar_html = _dark_market_bar_html  # local: marketing-site links

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

        # Replace SMN favicon with TW favicon
        html = html.replace(config.smn_favicon, config.tw_favicon)

        # Replace SMN title branding
        html = html.replace("| Seasonal Market News", "| TradeWave")
        html = html.replace("Seasonal Market News", "TradeWave")

        # Strip any leftover SMN dev-host or LAN-IP references in the dark
        # TW marketing pages so nothing leaks private hostnames out to crawlers.
        # (Pages live at /markets/ — no /_static/ rewrite needed.)
        for stale in ('http://192.168.1.151:9000', 'http://192.168.1.151',
                      'http://192.168.1.176'):
            html = html.replace(f'{stale}/markets/',
                                f'{DOMAIN_ROOT.rstrip("/")}/markets/')
            html = html.replace(f'"{stale}/"',
                                f'"{DOMAIN_ROOT.rstrip("/")}/"')
            html = html.replace(f'"{stale}"',
                                f'"{DOMAIN_ROOT.rstrip("/")}"')

        out_path = TW_MARKETS_DIR / ("%s.html" % slug)
        out_path.write_text(html, "utf-8")
        print("  -> Wrote %s (%s bytes)" % (out_path, format(len(html), ',')))
        generated.append(slug)

    # Restore originals
    gsp._build_base_css = original_base_css
    gsp._build_header_html = original_header
    gsp._build_cta_html = original_cta
    gsp._build_footer_html = original_footer
    gsp._build_market_bar_html = original_market_bar
    gsp.SITE_URL = original_site_url

    print("\n[TW MARKETING SECURITY PAGES] Done. Generated %d pages: %s" % (
        len(generated), ", ".join(generated)))


if __name__ == "__main__":
    main()
