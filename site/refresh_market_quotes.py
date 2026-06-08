#!/usr/bin/env python3
"""
refresh_market_quotes.py
========================
Lightweight live-price re-injector for the TradeWave marketing site.

Rewrites only the *prices* in the already-built static HTML:
  - the market bar (7 items) on every page that carries one, and
  - the hero quote (price / change / open-high-low-prevclose / volume /
    "as of" timestamp) on each /markets/<slug>.html page.

It does NOT regenerate charts, seasonal projections, or the AI featured
pick, so it is cheap and side-effect-free and can run on a short cron to
keep prices current between the heavy daily bakes.

Why this exists
---------------
The home page is baked once a weekday at 07:00 (generate_home_page.py) and
the markets pages are baked by generate_security_pages.py. Between bakes
their prices go stale -- and on tw2-prod the markets baker has been crashing
since mid-May (missing smn deps), so its pages froze. SMN keeps its prices
fresh by calling smn/generate_security_pages.inject_security_prices() from
rebuild_news_home; this is the dependency-free TradeWave equivalent (it only
needs site/lib/get_price_eod, so it deploys and runs on any box).

Quotes come from get_quote_details (local realtime price service first, then
EODHD fallback) -- the same source the bakers use.

Usage:
    python refresh_market_quotes.py [--root /var/www/tradewave] [--dry-run]
"""

import argparse
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/site/lib')
import config
from get_price_eod import get_quote_details

# The 7 market-bar instruments. `slug` is the stable key used in the
# /markets/<slug>.html links, so we key the bar rewrite on it (labels differ
# between the short bar form "S&P 500"/"DOW" and the long page titles).
INSTRUMENTS = [
    {"symbol": "GSPC", "exchange": "INDX", "slug": "sp500",       "appserver_symbol": "SPX"},
    {"symbol": "DJI",  "exchange": "INDX", "slug": "dow",         "appserver_symbol": "DJI"},
    {"symbol": "IXIC", "exchange": "INDX", "slug": "nasdaq",      "appserver_symbol": "IXIC"},
    {"symbol": "VIX",  "exchange": "INDX", "slug": "vix",         "appserver_symbol": "VIX"},
    {"symbol": "CL",   "exchange": "COMM", "slug": "crude-oil",   "appserver_symbol": "CL"},
    {"symbol": "NG",   "exchange": "COMM", "slug": "natural-gas", "appserver_symbol": "NG"},
    {"symbol": "GC",   "exchange": "COMM", "slug": "gold",        "appserver_symbol": "GC"},
]


def _fmt_price(val):
    """Match smn/generate_security_pages._fmt_price exactly."""
    if val is None:
        return " - "
    if abs(val) >= 1000:
        return f"{val:,.2f}"
    if abs(val) >= 10:
        return f"{val:.2f}"
    return f"{val:.4f}"


def _bar_change(change_p):
    """Market-bar change text: percent only (e.g. '+1.01%')."""
    if change_p is None:
        return "", "flat"
    direction = "up" if change_p >= 0 else "down"
    sign = "+" if change_p >= 0 else ""
    return f"{sign}{change_p:.2f}%", direction


def _hero_change(change, change_p):
    """Hero change text: absolute + percent (e.g. '+67.06 (+0.91%)')."""
    if change_p is None:
        return "", "flat"
    direction = "up" if change_p >= 0 else "down"
    sign = "+" if change_p >= 0 else ""
    if change is not None:
        return f"{sign}{change:.2f} ({sign}{change_p:.2f}%)", direction
    return f"{sign}{change_p:.2f}%", direction


def _to_float(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _update_bar_item(html, slug, price_str, chg_str, direction):
    """Update one market-bar <a> item (price + change text + up/down classes), keyed by slug."""
    anchor = re.compile(
        r'(<a\b[^>]*href=["\']/markets/' + re.escape(slug) + r'\.html["\'][^>]*>)(.*?)(</a>)',
        re.DOTALL)

    def repl(m):
        open_tag, inner, close = m.group(1), m.group(2), m.group(3)
        # Direction class on the anchor (preserve a trailing " current" marker).
        open_tag = re.sub(r'(class=["\']market-item )(up|down|flat)\b',
                          lambda mm: mm.group(1) + direction, open_tag)
        # Price span.
        inner = re.sub(r'(<span class=["\']market-price["\']>)[^<]*(</span>)',
                       lambda mm: mm.group(1) + price_str + mm.group(2), inner)
        # Change span (normalize to double quotes; harmless if it already used them).
        inner = re.sub(r'<span class=["\']market-change [^"\']*["\']>[^<]*</span>',
                       '<span class="market-change %s">%s</span>' % (direction, chg_str),
                       inner)
        return open_tag + inner + close

    return anchor.sub(repl, html, count=1)


def _refresh_bar(html, quotes):
    for inst in INSTRUMENTS:
        q = quotes.get(inst["symbol"])
        if not q:
            continue
        close = _to_float(q.get("close"))
        if close is None:
            continue
        chg_str, direction = _bar_change(_to_float(q.get("change_p")))
        html = _update_bar_item(html, inst["slug"], _fmt_price(close), chg_str, direction)
    return html


def _refresh_hero(html, inst, q):
    """Update the hero quote block on a /markets/<slug>.html page.

    Regexes mirror smn/generate_security_pages.inject_security_prices().
    """
    close = _to_float(q.get("close"))
    if close is None:
        return html
    chg_str, direction = _hero_change(_to_float(q.get("change")), _to_float(q.get("change_p")))

    html = re.sub(r'(<span class="price-main">)[^<]*(</span>)',
                  lambda m: m.group(1) + _fmt_price(close) + m.group(2), html)
    html = re.sub(r"<span class=['\"]price-change [^'\"]*['\"]>[^<]*</span>",
                  "<span class='price-change %s'>%s</span>" % (direction, chg_str), html)

    detail_map = {"Open": "open", "High": "high", "Low": "low", "Prev Close": "previousClose"}
    for label, key in detail_map.items():
        val = _to_float(q.get(key))
        html = re.sub(
            r'(<span class="quote-detail-label">' + re.escape(label) +
            r'</span><span class="quote-detail-value">)[^<]*(</span>)',
            lambda m: m.group(1) + _fmt_price(val) + m.group(2), html)

    vol = _to_float(q.get("volume"))
    if vol:
        html = re.sub(
            r'(<span class="quote-detail-label">Volume</span>'
            r'<span class="quote-detail-value">)[^<]*(</span>)',
            lambda m: m.group(1) + ("%s" % format(vol, ",.0f")) + m.group(2), html)

    ts = q.get("timestamp")
    if ts:
        try:
            ts_str = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
                "%b %d, %Y %I:%M %p UTC")
            html = re.sub(
                r'(<div class="security-meta">)[^<]*(</div>)',
                lambda m: m.group(1) + ("%s &middot; %s" % (inst["appserver_symbol"], ts_str)) + m.group(2),
                html)
        except (ValueError, OSError):
            pass
    return html


def _write_atomic(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".rmq.")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o644)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=config.web_root_dir,
                    help="web root holding home.html + markets/ (default: config.web_root_dir)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = args.root.rstrip("/")

    quotes = {}
    for inst in INSTRUMENTS:
        q = get_quote_details(inst["symbol"], inst["exchange"])
        if q and _to_float(q.get("close")) is not None:
            quotes[inst["symbol"]] = q
    if not quotes:
        print("refresh_market_quotes: no quotes fetched; leaving files unchanged.")
        return 1

    targets = [(os.path.join(root, "home.html"), None)]
    for inst in INSTRUMENTS:
        targets.append((os.path.join(root, "markets", "%s.html" % inst["slug"]), inst))

    changed = 0
    for path, inst in targets:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            orig = f.read()
        html = _refresh_bar(orig, quotes)
        if inst is not None and inst["symbol"] in quotes:
            html = _refresh_hero(html, inst, quotes[inst["symbol"]])
        if html != orig:
            changed += 1
            if args.dry_run:
                print("would update %s" % path)
            else:
                _write_atomic(path, html)

    summary = ", ".join(
        "%s=%s" % (i["symbol"], _fmt_price(_to_float(quotes[i["symbol"]]["close"])))
        for i in INSTRUMENTS if i["symbol"] in quotes)
    print("refresh_market_quotes: %s%d file(s) updated under %s | %s" % (
        "(dry-run) " if args.dry_run else "", changed, root, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
