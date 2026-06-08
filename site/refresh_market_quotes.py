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
import json
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


# Fields published into /assets/quotes.json (the single source of truth the
# pages read client-side).
_QUOTE_FIELDS = ("close", "change", "change_p", "open", "high", "low",
                 "previousClose", "volume", "timestamp")

# Tag injected before </body> on every page so the bar + hero read quotes.json.
_SCRIPT_TAG = '<script src="/assets/market-quotes.js" defer></script>'

# Client updater: on load, fetch /assets/quotes.json and overwrite the market
# bar (every page) + the hero quote (on /markets/<slug>.html) with the SAME
# live values, so the home top bar and the securities pages can never disagree.
_MARKET_QUOTES_JS = r"""/* TradeWave live market quotes - written by site/refresh_market_quotes.py.
   One source of truth (/assets/quotes.json) so the home top bar matches every
   /markets quote page exactly, regardless of when each page's HTML was baked. */
(function () {
  var SLUG2SYM = {sp500:'GSPC', dow:'DJI', nasdaq:'IXIC', vix:'VIX',
                  'crude-oil':'CL', 'natural-gas':'NG', gold:'GC'};
  function fmtPrice(v) {
    v = parseFloat(v); if (isNaN(v)) return null;
    var a = Math.abs(v);
    if (a >= 1000) return v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (a >= 10) return v.toFixed(2);
    return v.toFixed(4);
  }
  function pct(cp) {
    cp = parseFloat(cp); if (isNaN(cp)) return null;
    var s = cp >= 0 ? '+' : '';
    return [s + cp.toFixed(2) + '%', cp >= 0 ? 'up' : 'down'];
  }
  function heroChg(c, cp) {
    c = parseFloat(c); cp = parseFloat(cp); if (isNaN(cp)) return null;
    var s = cp >= 0 ? '+' : '', d = cp >= 0 ? 'up' : 'down';
    if (!isNaN(c)) return [s + c.toFixed(2) + ' (' + s + cp.toFixed(2) + '%)', d];
    return [s + cp.toFixed(2) + '%', d];
  }
  function apply(q) {
    if (!q) return;
    var items = document.querySelectorAll('a.market-item');
    for (var i = 0; i < items.length; i++) {
      var a = items[i];
      var m = (a.getAttribute('href') || '').match(/\/markets\/([^.\/]+)\.html/);
      if (!m) continue;
      var d = q[SLUG2SYM[m[1]]]; if (!d || d.close == null) continue;
      var ps = a.querySelector('.market-price'); var p = fmtPrice(d.close);
      if (ps && p) ps.textContent = p;
      var pc = pct(d.change_p); var cs = a.querySelector('.market-change');
      if (cs && pc) { cs.textContent = pc[0]; cs.className = 'market-change ' + pc[1]; }
      if (pc) { var cur = /\bcurrent\b/.test(a.className) ? ' current' : ''; a.className = 'market-item ' + pc[1] + cur; }
    }
    var pm = document.querySelector('.price-main');
    var path = (location.pathname || '').match(/\/markets\/([^.\/]+)\.html/);
    if (pm && path) {
      var d = q[SLUG2SYM[path[1]]];
      if (d && d.close != null) {
        var p = fmtPrice(d.close); if (p) pm.textContent = p;
        var hc = heroChg(d.change, d.change_p); var ce = document.querySelector('.price-change');
        if (ce && hc) { ce.textContent = hc[0]; ce.className = 'price-change ' + hc[1]; }
        var map = {Open: 'open', High: 'high', Low: 'low', 'Prev Close': 'previousClose'};
        var labels = document.querySelectorAll('.quote-detail-label');
        for (var j = 0; j < labels.length; j++) {
          var lab = (labels[j].textContent || '').trim(); var val = labels[j].nextElementSibling;
          if (!val) continue;
          if (map[lab] != null) { var fv = fmtPrice(d[map[lab]]); if (fv) val.textContent = fv; }
          else if (lab === 'Volume' && d.volume != null) {
            var vv = parseFloat(d.volume);
            if (!isNaN(vv)) val.textContent = vv.toLocaleString('en-US', {maximumFractionDigits: 0});
          }
        }
      }
    }
  }
  function load() {
    try {
      fetch('/assets/quotes.json?_=' + Math.floor(Date.now() / 30000), {cache: 'no-store'})
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(apply).catch(function () {});
    } catch (e) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load);
  else load();
})();
"""


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


def _ensure_script_tag(html):
    """Inject the market-quotes.js tag before </body> if not already present."""
    if "market-quotes.js" in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", "    " + _SCRIPT_TAG + "\n</body>", 1)
    return html + "\n" + _SCRIPT_TAG + "\n"


def _write_atomic(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".rmq.")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o644)


def _write_assets(root, quotes):
    """Write /assets/quotes.json (source of truth) + /assets/market-quotes.js."""
    assets = os.path.join(root, "assets")
    os.makedirs(assets, exist_ok=True)
    payload = {}
    for inst in INSTRUMENTS:
        q = quotes.get(inst["symbol"])
        if not q:
            continue
        payload[inst["symbol"]] = {k: q.get(k) for k in _QUOTE_FIELDS}
    _write_atomic(os.path.join(assets, "quotes.json"),
                  json.dumps(payload, separators=(",", ":")))
    js_path = os.path.join(assets, "market-quotes.js")
    # Only rewrite the JS if it changed (it is effectively static).
    existing = None
    if os.path.exists(js_path):
        with open(js_path, encoding="utf-8") as f:
            existing = f.read()
    if existing != _MARKET_QUOTES_JS:
        _write_atomic(js_path, _MARKET_QUOTES_JS)


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

    if not args.dry_run:
        _write_assets(root, quotes)

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
        html = _ensure_script_tag(html)
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
