#!/usr/bin/env python3
"""
TradeWave API & MCP - marketing page generator.

Produces four static HTML pages into /home/flask/site/api_marketing/out/:
  index.html   - Landing / hero page
  pricing.html - 4-tier pricing (matches apiserver/tiers.py exactly)
  mcp.html     - MCP showcase (example agent conversations)
  use-cases.html - Use-case profiles

Run:
    python3 /home/flask/site/api_marketing/generate.py

Reads tiers directly from apiserver/tiers.py so prices can never drift.
No em-dashes anywhere (brand rule). No raw price data exposed (API contract).
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path
from datetime import datetime

# Allow importing from the repo root and the site lib.
REPO = Path(__file__).resolve().parent.parent.parent  # /home/flask
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "site" / "lib"))

from apiserver.tiers import API_TIERS, API_PRICING_LIVE  # the one source of truth
from text_utils import no_em_dash            # hard brand rule
import portal_urls                           # env-resolved public URLs
import portal_seo                            # SEO/social/llms helpers

OUT_DIR = Path(__file__).parent / "out"
HEADER_PARTIAL = REPO / "site" / "templates" / "_tw_header.html"
YEAR = datetime.now().year

LEGAL_DISCLAIMER = (
    "TradeWave is a research platform. It is not a brokerage and does not "
    "execute trades. All data is based on historical analysis and is provided "
    "for informational and educational purposes only. Past performance does "
    "not guarantee future results."
)

# Market names for the 15 active keys (ids 14/15 do not exist).
MARKET_NAMES = {
    "0": "DOW 30 STOCKS",
    "1": "NASDAQ 100 STOCKS",
    "2": "S&P 500 STOCKS",
    "3": "RUSSELL 1000 STOCKS",
    "4": "WILSHIRE 5000",
    "5": "INDICES COMMON",
    "6": "INDICES ALL",
    "7": "FUTURES & COMMODITIES",
    "8": "FOREX ALL",
    "9": "FOREX LIQUID",
    "10": "GOVERNMENT BONDS",
    "11": "ETFs",
    "12": "LONDON EXCHANGE",
    "13": "TORONTO STOCKS",
    "16": "CRYPTO CURRENCIES",
}

FREE_MARKET_NAME = MARKET_NAMES.get("2", "S&P 500 STOCKS")  # free tier = market 2 only (S&P 500 stocks)


# ---------------------------------------------------------------------------
# Shared shell: loads the header partial so nav/branding is identical to TW2.
# ---------------------------------------------------------------------------

def load_header() -> str:
    if HEADER_PARTIAL.is_file():
        return HEADER_PARTIAL.read_text(encoding="utf-8")
    # Fallback minimal header if partial missing.
    return f"""<nav style="background:#0f0a15;border-bottom:1px solid #1f2937;padding:16px 24px;display:flex;align-items:center;gap:32px;">
<a href="{portal_urls.MAIN_URL}" style="font-size:26px;font-weight:800;background:linear-gradient(135deg,#6366f1,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-decoration:none;">TradeWave</a>
<a href="index.html" style="color:#9ca3af;text-decoration:none;font-size:14px;">API Home</a>
<a href="pricing.html" style="color:#9ca3af;text-decoration:none;font-size:14px;">Pricing</a>
<a href="mcp.html" style="color:#9ca3af;text-decoration:none;font-size:14px;">MCP</a>
</nav>"""


def footer_html() -> str:
    return f"""<footer class="api-footer">
  <div class="container">
    <nav class="footer-nav" aria-label="Footer">
      <a href="{portal_urls.MAIN_URL}">TradeWave Home</a>
      <a href="index.html">API Home</a>
      <a href="pricing.html">API Pricing</a>
      <a href="mcp.html">MCP Showcase</a>
      <a href="for-ai-agents.html">For AI agents</a>
      <a href="use-cases.html">Use Cases</a>
      <a href="{portal_urls.nav('contact.html')}">Contact</a>
      <a href="{portal_urls.nav('privacy.html')}">Privacy</a>
      <a href="api-terms.html">API Terms</a>
      <a href="{portal_urls.nav('disclaimer.html')}">Disclaimer</a>
    </nav>
    <p class="footer-copy">&copy; {YEAR} Tara Data Research LLC. All rights reserved.</p>
    <p class="footer-legal">{LEGAL_DISCLAIMER}</p>
  </div>
</footer>"""


BASE_CSS = """
<style>
:root {
  --bg:       #0f0a15;
  --bg-alt:   #191622;
  --bg-card:  #0c1225;
  --text:     #ffffff;
  --dim:      #9ca3af;
  --muted:    #6b7280;
  --border:   #1f2937;
  --border-l: #374151;
  --accent:   #6366f1;
  --accent2:  #8b5cf6;
  --accent3:  #a855f7;
  --green:    #64dc8c;
  --success:  #10b981;
  --warn:     #f59e0b;
  --danger:   #ef4444;
  --grad:     linear-gradient(135deg,#6366f1 0%,#8b5cf6 50%,#a855f7 100%);
  --grad-txt: linear-gradient(135deg,#ffffff 0%,#c7d2fe 100%);
}
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}
.glow-bg {
  position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%,rgba(99,102,241,.15),transparent),
    radial-gradient(ellipse 60% 40% at 100% 0%,rgba(139,92,246,.10),transparent),
    radial-gradient(ellipse 60% 40% at 0% 100%,rgba(99,102,241,.08),transparent);
}
.container { max-width:1200px; margin:0 auto; padding:0 24px; position:relative; z-index:1; }

/* Typography */
.gradient-text {
  background: var(--grad);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}
.gradient-text-w {
  background: var(--grad-txt);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}

/* Buttons */
.btn {
  display:inline-flex; align-items:center; justify-content:center;
  padding:14px 28px; border-radius:12px; font-weight:600; font-size:15px;
  text-decoration:none; transition:all .3s; cursor:pointer; border:none;
  font-family:inherit;
}
.btn-primary {
  background: var(--grad); color:#fff;
  box-shadow:0 4px 20px rgba(99,102,241,.25),0 0 0 1px rgba(255,255,255,.1) inset;
}
.btn-primary:hover { transform:translateY(-2px); box-shadow:0 8px 30px rgba(99,102,241,.4),0 0 0 1px rgba(255,255,255,.15) inset; }
.btn-secondary {
  background:rgba(99,102,241,.1); color:var(--accent);
  border:1px solid rgba(99,102,241,.3);
}
.btn-secondary:hover { background:rgba(99,102,241,.2); border-color:var(--accent); }
.btn-ghost {
  background:transparent; color:var(--dim);
  border:1px solid var(--border);
}
.btn-ghost:hover { color:var(--text); border-color:var(--border-l); }

/* Section headings */
.section-head { text-align:center; margin-bottom:48px; }
.section-head h2 { font-size:38px; font-weight:800; margin-bottom:14px; }
.section-head p { font-size:17px; color:var(--dim); max-width:680px; margin:0 auto; }

/* Cards */
.card {
  background:var(--bg-card); border-radius:20px; padding:36px 28px;
  border:1px solid var(--border);
}

/* Tag pill */
.tag {
  display:inline-block; padding:5px 14px; border-radius:100px;
  font-size:12px; font-weight:700; letter-spacing:.4px; text-transform:uppercase;
}
.tag-ml { background:rgba(99,102,241,.15); color:var(--accent); border:1px solid rgba(99,102,241,.3); }
.tag-free { background:rgba(16,185,129,.12); color:var(--success); border:1px solid rgba(16,185,129,.25); }
.tag-pro { background:rgba(100,220,140,.12); color:var(--green); border:1px solid rgba(100,220,140,.25); }

/* Hero */
.page-hero { padding:80px 0 60px; text-align:center; position:relative; z-index:1; }
.page-hero h1 { font-size:52px; font-weight:800; line-height:1.25; margin-bottom:24px; }
.page-hero .sub { font-size:19px; color:var(--dim); max-width:740px; margin:0 auto 36px; line-height:1.7; }
.hero-ctas { display:flex; gap:16px; justify-content:center; flex-wrap:wrap; margin-bottom:12px; }
.hero-ctas .btn { padding:16px 36px; font-size:16px; }
.hero-note { font-size:13px; color:var(--muted); }

/* 3-col grid */
.grid-3 { display:grid; grid-template-columns:repeat(3,1fr); gap:28px; }
.grid-2 { display:grid; grid-template-columns:repeat(2,1fr); gap:28px; }
.grid-4 { display:grid; grid-template-columns:repeat(4,1fr); gap:24px; }

/* Checklist */
.check-list { list-style:none; }
.check-list li { display:flex; align-items:flex-start; gap:10px; color:var(--dim); font-size:14px; padding:6px 0; }
.check-list li::before { content:'\\2713'; color:var(--success); font-weight:700; flex-shrink:0; }
.check-list li.no::before { content:'\\2717'; color:var(--danger); }
.check-list li.ml::before { content:'\\2605'; color:var(--accent); }

/* Code block */
.code-block {
  background:#060b18; border:1px solid var(--border); border-radius:12px;
  padding:20px 24px; font-family:'Fira Code','Cascadia Code',Consolas,monospace;
  font-size:13px; color:#c7d2fe; overflow-x:auto; line-height:1.6;
}
.code-block .cm { color:#4b5563; }
.code-block .kw { color:#a78bfa; }
.code-block .st { color:#6ee7b7; }
.code-block .nu { color:#fcd34d; }
.code-block .fn { color:#93c5fd; }

/* Track record table */
.track-table-wrap {
  border-radius:14px; overflow:hidden; border:1px solid var(--border);
  max-width:800px; margin:0 auto;
}
.track-table { width:100%; border-collapse:collapse; font-size:14px; }
.track-table th {
  background:var(--bg); padding:13px 16px; text-align:center;
  font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px;
  color:var(--muted); border-bottom:1px solid var(--border);
}
.track-table td {
  padding:11px 16px; text-align:center;
  background:var(--bg-card); border-bottom:1px solid var(--border);
}
.track-table tr:last-child td { border-bottom:none; }
.td-year { font-weight:700; color:var(--text); }
.td-win  { color:var(--green); font-weight:700; }
.td-base { color:var(--dim); }
.td-lift { color:var(--accent); font-weight:600; }
.td-n    { color:var(--muted); }
.td-note { font-size:11px; color:var(--muted); font-style:italic; }

/* Chat bubbles (MCP showcase) */
.chat-window {
  background:#060b18; border:1px solid rgba(99,102,241,.3);
  border-radius:16px; overflow:hidden;
  box-shadow:0 0 60px rgba(99,102,241,.12), 0 24px 80px rgba(0,0,0,.5);
  max-width:820px; margin:0 auto 40px;
}
.chat-bar {
  background:rgba(15,10,21,.9); border-bottom:1px solid var(--border);
  padding:12px 20px; display:flex; align-items:center; gap:10px;
}
.chat-dot { width:10px; height:10px; border-radius:50%; }
.chat-dot.red { background:#ef4444; }
.chat-dot.ylw { background:#f59e0b; }
.chat-dot.grn { background:#10b981; }
.chat-title { font-size:13px; font-weight:600; color:var(--dim); margin-left:8px; }
.chat-body { padding:24px 24px; display:flex; flex-direction:column; gap:16px; }
.bubble {
  max-width:82%; border-radius:14px; padding:12px 16px;
  font-size:14px; line-height:1.6;
}
.bubble.user {
  align-self:flex-end;
  background:rgba(99,102,241,.2); border:1px solid rgba(99,102,241,.3);
  color:var(--text); border-radius:14px 14px 2px 14px;
}
.bubble.agent {
  align-self:flex-start;
  background:rgba(12,18,37,.9); border:1px solid var(--border);
  color:var(--dim); border-radius:2px 14px 14px 14px;
}
.bubble.agent strong, .bubble.agent b { color:var(--text); }
.bubble.tool-call {
  align-self:flex-start;
  background:rgba(99,102,241,.06); border:1px dashed rgba(99,102,241,.25);
  color:var(--accent); font-family:monospace; font-size:12px;
  border-radius:8px; padding:8px 14px;
}
.bubble-table {
  width:100%; border-collapse:collapse; margin-top:10px; font-size:13px;
}
.bubble-table th { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.3px; padding:4px 8px; border-bottom:1px solid var(--border); text-align:left; }
.bubble-table td { padding:6px 8px; border-bottom:1px solid rgba(31,41,55,.5); color:var(--dim); }
.bubble-table td.hi { color:var(--green); font-weight:700; }
.bubble-table td.acc { color:var(--accent); font-weight:600; }

/* Chat label */
.chat-label {
  font-size:11px; color:var(--muted); font-weight:700; text-transform:uppercase;
  letter-spacing:.5px; margin-bottom:4px;
}

/* Pricing */
.pricing-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:20px; max-width:1140px; margin:0 auto; }
.p-card {
  background:var(--bg-card); border:1px solid var(--border); border-radius:20px;
  padding:32px 24px; display:flex; flex-direction:column; position:relative;
}
.p-card.highlight { border-color:var(--accent); box-shadow:0 0 50px rgba(99,102,241,.2); }
.p-card.highlight::before {
  content:'Most Popular';
  position:absolute; top:-14px; left:50%; transform:translateX(-50%);
  background:var(--grad); color:#fff; padding:5px 18px; border-radius:100px;
  font-size:11px; font-weight:700; letter-spacing:.3px; white-space:nowrap;
}
.p-name { font-size:20px; font-weight:700; margin-bottom:4px; }
.p-tagline { font-size:13px; color:var(--dim); margin-bottom:20px; min-height:36px; }
.p-price { font-size:44px; font-weight:800; color:var(--green); line-height:1; }
.p-price-unit { font-size:16px; color:var(--muted); font-weight:400; }
.p-annual-note { font-size:12px; color:var(--muted); margin-top:6px; margin-bottom:20px; }
.p-features { list-style:none; flex:1; margin:16px 0 24px; }
.p-features li { display:flex; align-items:flex-start; gap:10px; font-size:13px; color:var(--dim); padding:6px 0; border-bottom:1px solid rgba(31,41,55,.5); }
.p-features li:last-child { border-bottom:none; }
.p-features li::before { content:'\\2713'; color:var(--success); font-weight:700; flex-shrink:0; margin-top:1px; }
.p-features li.no { opacity:.5; }
.p-features li.no::before { content:'\\2717'; color:var(--danger); }
.p-features li.ml-feat { font-weight:600; color:var(--text); }
.p-features li.ml-feat::before { content:'\\2605'; color:var(--accent); }
.p-card .btn { width:100%; padding:12px 20px; font-size:14px; }
.p-note { font-size:11px; color:var(--muted); text-align:center; margin-top:10px; line-height:1.5; }

/* Toggle */
.billing-toggle { display:flex; justify-content:center; gap:0; margin-bottom:40px; }
.billing-btn {
  padding:10px 28px; font-size:14px; font-weight:600; cursor:pointer;
  border:1px solid var(--border); color:var(--dim); background:var(--bg-card);
  font-family:inherit; transition:all .2s;
}
.billing-btn:first-child { border-radius:8px 0 0 8px; }
.billing-btn:last-child  { border-radius:0 8px 8px 0; border-left:none; }
.billing-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
.save-badge { font-size:11px; font-weight:700; color:var(--green); margin-left:6px; }

/* Enterprise strip */
.enterprise-strip {
  max-width:900px; margin:40px auto 0; padding:32px 40px;
  background:rgba(99,102,241,.05); border:1px solid rgba(99,102,241,.2);
  border-radius:16px; display:flex; align-items:center; justify-content:space-between; gap:28px;
  flex-wrap:wrap;
}
.enterprise-strip h3 { font-size:20px; font-weight:700; margin-bottom:8px; }
.enterprise-strip p { font-size:14px; color:var(--dim); max-width:500px; }
.founder-strip {
  max-width:900px; margin:32px auto 0; padding:28px 36px;
  background:linear-gradient(90deg, rgba(245,158,11,.10), rgba(99,102,241,.06));
  border:1px solid rgba(245,158,11,.35);
  border-radius:16px; display:flex; align-items:center; justify-content:space-between; gap:28px;
  flex-wrap:wrap;
}
.founder-strip h3 { font-size:19px; font-weight:700; margin-bottom:8px; color:#fbbf24; }
.founder-strip p { font-size:14px; color:var(--dim); max-width:560px; }
.founder-strip code { background:rgba(0,0,0,.35); padding:1px 7px; border-radius:5px; color:#fff; font-weight:700; }
.bundle-note { max-width:900px; margin:18px auto 0; text-align:center; font-size:13px; color:var(--muted); }
.bundle-note a { color:var(--accent); }

/* Use-case cards */
.uc-card { padding:36px 32px; }
.uc-icon { font-size:36px; margin-bottom:16px; }
.uc-card h3 { font-size:19px; font-weight:700; margin-bottom:10px; }
.uc-card p { font-size:14px; color:var(--dim); line-height:1.7; margin-bottom:14px; }
.uc-card .who { font-size:12px; color:var(--accent); font-weight:700; text-transform:uppercase; letter-spacing:.5px; margin-bottom:16px; display:block; }

/* Diff cards */
.diff-card { padding:32px; text-align:left; }
.diff-card .diff-icon { font-size:28px; margin-bottom:14px; }
.diff-card h3 { font-size:18px; font-weight:700; margin-bottom:10px; }
.diff-card p { font-size:14px; color:var(--dim); line-height:1.7; }

/* Competitor comparison */
.comp-table-wrap { max-width:860px; margin:0 auto; border-radius:14px; overflow:hidden; border:1px solid var(--border); }
.comp-table { width:100%; border-collapse:collapse; font-size:14px; }
.comp-table th { background:var(--bg); padding:13px 20px; text-align:left; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); border-bottom:1px solid var(--border); }
.comp-table th:not(:first-child) { text-align:center; }
.comp-table td { padding:13px 20px; background:var(--bg-card); border-bottom:1px solid var(--border); color:var(--dim); }
.comp-table td:not(:first-child) { text-align:center; }
.comp-table tr:last-child td { border-bottom:none; }
.comp-table .tw-col { color:var(--green); font-weight:700; }
.comp-table .no-col { color:var(--danger); }
.comp-table .feat-col { color:var(--text); font-weight:600; }

/* Sections */
.section { padding:88px 0; position:relative; z-index:1; }
.section.alt { background:rgba(25,22,35,.5); }

/* Footer */
.api-footer {
  background:var(--bg-alt); border-top:1px solid var(--border);
  padding:48px 0 28px; position:relative; z-index:1;
}
.footer-nav { display:flex; flex-wrap:wrap; gap:8px 24px; justify-content:center; margin-bottom:20px; }
.footer-nav a { color:var(--muted); text-decoration:none; font-size:14px; transition:color .2s; }
.footer-nav a:hover { color:var(--text); }
.footer-copy { text-align:center; font-size:13px; color:var(--muted); margin-bottom:12px; }
.footer-legal { text-align:center; font-size:11px; color:var(--muted); max-width:800px; margin:0 auto; line-height:1.8; opacity:.6; }

/* Responsive */
@media (max-width:1024px) { .pricing-grid { grid-template-columns:repeat(2,1fr); } .grid-4 { grid-template-columns:repeat(2,1fr); } }
@media (max-width:768px) {
  .page-hero h1 { font-size:32px; }
  .page-hero .sub { font-size:16px; }
  .section-head h2 { font-size:28px; }
  .grid-3, .grid-2, .grid-4 { grid-template-columns:1fr; }
  .pricing-grid { grid-template-columns:1fr; max-width:420px; margin:0 auto; }
  .enterprise-strip { flex-direction:column; text-align:center; padding:24px; }
  .hero-ctas { flex-direction:column; align-items:center; }
  .hero-ctas .btn { width:100%; max-width:340px; }
  .chat-window { border-radius:12px; }
  .bubble { max-width:95%; }
  .container { padding:0 16px; }
  .section { padding:60px 0; }
  .comp-table th:nth-child(3), .comp-table td:nth-child(3) { display:none; }
}
html { scroll-behavior:smooth; }

/* Link override for inside-content links */
a.inline { color:var(--accent); text-decoration:none; font-weight:600; }
a.inline:hover { text-decoration:underline; }
</style>
"""


def page_shell(title: str, description: str, body: str, active_nav: str = "",
               robots: str = "index, follow") -> str:
    """Wrap body in the full TW2-branded page shell."""
    header = load_header()
    foot = footer_html()

    # Rewrite all main-site root-relative paths in the header partial so they
    # resolve correctly when served from the api host (not the main host).
    _main_nav_rewrites = [
        ('href="/"',                  f'href="{portal_urls.MAIN_URL}"'),
        ('href="/app/"',              f'href="{portal_urls.nav("app/")}"'),
        ('href="/patterns/"',         f'href="{portal_urls.nav("patterns/")}"'),
        ('href="/scorecard.html"',    f'href="{portal_urls.nav("scorecard.html")}"'),
        ('href="/insights/"',         f'href="{portal_urls.nav("insights/")}"'),
        ('href="/research.html"',     f'href="{portal_urls.nav("research.html")}"'),
        ('href="/learn.html"',        f'href="{portal_urls.nav("learn.html")}"'),
        ('href="/login"',             f'href="{portal_urls.LOGIN_URL}"'),
        ('href="/pricing"',           f'href="{portal_urls.nav("pricing")}"'),
    ]
    for old, new in _main_nav_rewrites:
        header = header.replace(old, new)

    # DEVELOPER PORTAL nav: the shared site header carries the full CONSUMER menu (Wave Viewer,
    # Tickers, Scorecard, Insights, Research, News) which crowds the API/MCP pages and does not
    # serve a developer audience. Replace the whole nav-link list with a focused developer nav -
    # the shared partial (and the consumer site) are untouched; the logo still links back to the
    # main site, and the auth/CTA ids (tw-auth-link/tw-cta-link) are preserved for the JS hooks.
    _dev_nav = (
        '<div class="tw-nav-links" id="tw-nav-links">\n'
        '      <a href="index.html">API</a>\n'
        f'      <a href="{portal_urls.DOCS_URL}/quickstart.html">Docs</a>\n'
        '      <a href="pricing.html">Pricing</a>\n'
        '      <a href="mcp.html">MCP</a>\n'
        '      <a href="for-ai-agents.html">For AI agents</a>\n'
        f'      <a href="{portal_urls.LEARN_URL}/">Learn</a>\n'
        f'      <a href="{portal_urls.LOGIN_URL}" id="tw-auth-link">Log In</a>\n'
        f'      <a href="{portal_urls.nav("account/api/keys")}" id="tw-cta-link" class="tw-btn-primary">Get API Key</a>\n'
        '    </div>'
    )
    header = re.sub(
        r'<div class="tw-nav-links" id="tw-nav-links">.*?</div>',
        lambda _m: _dev_nav, header, count=1, flags=re.DOTALL,
    )

    # active_nav is "", "pricing", "mcp", "use-cases" -> map to the output filename.
    _page = (active_nav + ".html") if (active_nav and active_nav != "index") else "index.html"
    _canonical = portal_urls.PORTAL_URL + ("/" if _page == "index.html" else "/" + _page)
    _seo = portal_seo.head_tags(
        _canonical, title, description,
        jsonld=portal_seo.api_jsonld() if _page == "index.html" else None,
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - TradeWave</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="{robots}">
  {_seo}
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="shortcut icon" type="image/png" href="/favicon.png">
  <link rel="apple-touch-icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" media="print" onload="this.media='all'">
  <noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"></noscript>
{BASE_CSS}
</head>
<body>
<div class="glow-bg"></div>
{header}
{body}
{foot}
</body>
</html>"""


# ===========================================================================
# PAGE 1 - Landing / Hero
# ===========================================================================

def build_index() -> str:
    if API_PRICING_LIVE:
        pricing_hero_note = (
            f'No credit card. Free, then Dev $39, Pro $199, Business $599 (redistribution to your users '
            f'under license), and Enterprise with volume licensing, an SLA, and a signed agreement - '
            f'<a href="{portal_urls.nav("contact.html")}" style="color:var(--accent);">talk to sales</a>.'
        )
    else:
        pricing_hero_note = (
            f'No credit card. The Free tier is open now - paid plans (Dev, Pro, Business, and Enterprise '
            f'with volume licensing, an SLA, and a signed agreement) launch soon - '
            f'<a href="{portal_urls.nav("contact.html")}" style="color:var(--accent);">talk to sales</a>.'
        )
    body = f"""
<section class="page-hero">
  <div class="container">
    <div class="tag tag-ml" style="margin-bottom:20px;">REST + MCP - Now Available</div>
    <h1>
      <span class="gradient-text-w">Seasonal patterns and ML scores for US markets, in one API call</span>
    </h1>
    <p class="sub">
      Query 1-99 years of seasonal history - by calendar or election cycle - with an ML win-probability
      on every setup, over REST or straight from ChatGPT and Claude via MCP. Try it in ~30 seconds below
      with a live demo call, then build, embed, or ship on it.
    </p>

    <div class="code-block" style="max-width:680px;margin:0 auto 28px;text-align:left;">
<span class="cm"># Real authenticated call - no signup, no key, paste and run</span>
<span class="kw">curl</span> {portal_urls.API_BASE}/scan?market=2&amp;limit=5 \\
  -H <span class="st">"Authorization: Bearer tw_demo_explore"</span>
    </div>
    <p class="hero-note" style="margin-bottom:24px;">
      <code style="color:var(--accent);">tw_demo_explore</code> is a public demo token - it is a constant,
      not a secret, so paste it as-is. Returns today's ranked seasonal patterns for AAPL, MSFT, NVDA, AMZN
      and TSLA. A free key unlocks every symbol.
    </p>

    <div class="hero-ctas">
      <a href="{portal_urls.DOCS_URL}/quickstart.html" class="btn btn-primary">Run it in 30 seconds</a>
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-secondary">Get a free key</a>
      <a href="mcp.html" class="btn btn-ghost">Connect it to Claude</a>
    </div>
    <p class="hero-note">{pricing_hero_note}</p>
  </div>
</section>

<!-- Differentiation strip -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Derived research, not a data firehose</h2>
      <p>Raw market data is a commodity; execution needs capital and a license. The scarce, defensible
         layer is the one in between - the quantified reason a setup is worth a look. Each detected seasonal
         pattern ships as percentages, a 0-100 seasonal index and an ML win-probability, with the dates
         that bound the window - never raw OHLCV. Because we return derived values, not exchange-licensed
         quotes, there are no exchange agreements, per-terminal fees, or market-data audits on your side.</p>
    </div>
    <div class="grid-3">
      <div class="card diff-card">
        <div class="diff-icon">&#127917;</div>
        <h3>ML win-probability on seasonal patterns</h3>
        <p>A 62-feature model trained on millions of historical setups scores every
           seasonal opportunity with a win probability and predicted return before
           market open. Every tier includes ML scores (free starts at 5/day; Pro is unlimited).
           No other seasonality API offers it.</p>
      </div>
      <div class="card diff-card">
        <div class="diff-icon">&#128200;</div>
        <h3>Verifiable, time-stamped track record</h3>
        <p>Every daily pick is recorded before it opens. The
           <code style="font-size:12px;color:var(--accent);">get_pick_track_record</code>
           endpoint returns the realized win/loss history - not a backtested curve,
           a forward-looking ledger you can audit call by call.</p>
      </div>
      <div class="card diff-card">
        <div class="diff-icon">&#129302;</div>
        <h3>Agent-native via MCP</h3>
        <p>The TradeWave MCP server is a hosted HTTP endpoint: sign in from ChatGPT or Claude.ai with your
           TradeWave account, or connect Claude Desktop, Cursor, or any MCP-compatible host with an
           API key. Ask your AI assistant to find the strongest
           seasonal longs in S&P 500 stocks, rank by ML score, and compare to the live
           track record - no glue code required. TradeWave supplies the seasonal and ML edge
           plus the timing; your assistant pairs it with its own fundamentals, news, and macro tools.</p>
      </div>
    </div>
  </div>
</section>

<!-- Where TradeWave sits (edge-layer positioning) -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Where TradeWave sits</h2>
      <p>We are the layer above the trade, not another place to make it. Use TradeWave for the reason
         and the timing, then render it in your own app, route it to your agent, or hand the ticket to
         whatever you already execute with - any in-chat execution app or broker.</p>
    </div>
    <div class="grid-3">
      <div class="card diff-card">
        <h3>Raw data feeds</h3>
        <p>Prices, quotes, and history sold by the call. A commodity in a race to zero - they hand you
           numbers but no edge and no timing, so the decision is still entirely on you.</p>
      </div>
      <div class="card diff-card">
        <h3>Execution apps and brokers</h3>
        <p>The last mile that places the order and clears the trade. Most never publish a forward-tested
           track record, and a venue that earns per trade is structurally conflicted, so "sit this one
           out" is not something they are built to tell you.</p>
      </div>
      <div class="card diff-card" style="border-color:var(--accent);">
        <h3>TradeWave - the research layer</h3>
        <p>The quantified reason and the timing, as a Pattern Card with verifiable, time-stamped,
           forward-tested receipts - and an honest empty result when nothing scores. We sit between the
           other two: derived values out (percentages and a 0-100 seasonal index), no raw prices in your
           response.</p>
      </div>
    </div>
  </div>
</section>

<!-- Agent-era thesis teaser: consume, do not compute -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Your agent can write a backtest. It cannot make it true.</h2>
      <p>A capable agent can scaffold a seasonality backtest in minutes. What it cannot conjure is the
         licensed data, the trained model, and the forward-tested receipts that decide whether the backtest
         is true or just confidently wrong. Consume that edge in one call instead of rebuilding it badly.</p>
    </div>
    <div style="text-align:center;margin-top:28px;">
      <a href="for-ai-agents.html" class="btn btn-primary">For AI agents - why consume, not compute</a>
    </div>
  </div>
</section>

<!-- Track Record as credibility proof -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Audited, not believed</h2>
      <p>We do not show you a curve to admire. Every daily pick is logged before the outcome,
         then scored against what actually happened - a forward record you can audit call by call,
         not a backtest fit after the fact. Read the live record instead of taking our word for it.</p>
    </div>

    <div class="track-table-wrap">
      <table class="track-table">
        <thead>
          <tr>
            <th>Year</th>
            <th>Base seasonal win rate</th>
            <th>ML-selected picks win rate</th>
            <th>ML lift</th>
            <th>Picks</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="td-year">Example</td>
            <td class="td-base">64%</td>
            <td class="td-win">79%</td>
            <td class="td-lift">+15pp</td>
            <td class="td-n">57</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p style="text-align:center;font-size:12px;color:var(--muted);margin-top:16px;">
      One example row, shown only to explain how the ML layer is meant to lift the base seasonal
      win rate - it is a concept, not a result. The real numbers are public and call-by-call: pull
      the realized record from <code style="font-size:11px;">/v1/daily-pick/track-record</code> on
      the free tier, or read the same record on the public scorecard. Past performance does not
      guarantee future results.
    </p>
    <div style="text-align:center;margin-top:28px;">
      <a href="{portal_urls.nav('scorecard.html')}" class="btn btn-primary">See the Public Record</a>
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-ghost" style="margin-left:12px;">Pull It via the API</a>
    </div>
  </div>
</section>

<!-- What makes TradeWave different (provider-neutral category columns; no competitor names per house rule) -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">What Makes TradeWave Different</h2>
      <p>TradeWave is the only seasonality engine that both shows its work and scores the odds: an
         AI-calibrated win-probability on every pattern, a forward-recorded track record, and native
         REST and MCP access - at a fraction of the cost of a data terminal, open to any developer or
         AI agent today.</p>
    </div>
    <div class="comp-table-wrap">
      <table class="comp-table">
        <thead>
          <tr>
            <th>Feature</th>
            <th>TradeWave API</th>
            <th>Typical seasonality tools</th>
            <th>Data terminals</th>
          </tr>
        </thead>
        <tbody>
          <tr><td class="feat-col">ML win-probability scoring</td><td class="tw-col">All tiers (unlimited on Pro+)</td><td class="no-col">No</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">REST API access</td><td class="tw-col">Yes - all tiers</td><td class="no-col">Rare</td><td class="no-col">Terminal only</td></tr>
          <tr><td class="feat-col">MCP / AI agent integration</td><td class="tw-col">Yes - native</td><td class="no-col">No</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">Verified pick track record</td><td class="tw-col">Yes - forward-recorded</td><td class="no-col">Backtest only</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">Redistributable to your own users</td><td class="tw-col">Yes - by design</td><td class="no-col">Mixed</td><td class="no-col">Raw data only</td></tr>
          <tr><td class="feat-col">No data terminal or seat required</td><td class="tw-col">Yes</td><td class="no-col">Varies</td><td class="no-col">Required</td></tr>
          <tr><td class="feat-col">Starting price</td><td class="tw-col">Free</td><td>Hundreds per month</td><td>Tens of thousands per year</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<!-- CTAs -->
<section class="section">
  <div class="container" style="text-align:center;">
    <h2 class="gradient-text-w" style="font-size:36px;font-weight:800;margin-bottom:16px;">Try, build, ship</h2>
    <p style="color:var(--dim);font-size:17px;max-width:640px;margin:0 auto 32px;line-height:1.7;">
      Start free, scale when it earns its place. The full ladder is on the pricing page.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="pricing.html" class="btn btn-secondary">See All Plans</a>
      <a href="{portal_urls.nav('contact.html')}" class="btn btn-ghost">Contact Sales</a>
    </div>
  </div>
</section>
"""
    return page_shell(
        "TradeWave API & MCP - Seasonal Patterns + ML Research",
        "REST API and MCP server for seasonal pattern analysis with ML win-probability scoring. "
        "Connect to Claude, Cursor, or any AI agent in minutes.",
        no_em_dash(body),
    )


# ===========================================================================
# PAGE 2 - Pricing
# ===========================================================================

def build_pricing() -> str:
    tiers = API_TIERS  # from the single source of truth

    # Annual = price_annual (10x monthly = pay for 10 months, get 12 = 2 months free, ~17% off).
    def annual_permo(t: dict) -> int:
        return 0 if t["price_monthly"] == 0 else round(t["price_annual"] / 12)

    def annual_savings(t: dict) -> str:
        if t["price_monthly"] == 0:
            return ""
        saved = t["price_monthly"] * 12 - t["price_annual"]
        return f"Save ${saved}/yr"

    def rate_label(r: dict) -> str:
        return f"{r['per_minute']}/min, {r['per_day']:,}/day"

    def market_scope(t: dict) -> str:
        if len(t["markets"]) == 1:
            return f"1 market ({FREE_MARKET_NAME})"
        return f"All {len(t['markets'])} markets"

    def card_html(key: str, t: dict, is_highlight: bool) -> str:
        hl = ' highlight' if is_highlight else ''
        # Pricing-visibility gate (apiserver.tiers.API_PRICING_LIVE): the owner has not
        # finalized paid-tier pricing yet, so paid cards show "Coming Soon" with no dollar
        # figure and route their CTA to sales instead of signup, until the flag flips.
        price_hidden = key != "free" and not API_PRICING_LIVE
        ann_permo = annual_permo(t)
        ann = f"${ann_permo}"
        save = annual_savings(t)
        save_span = f' <span class="save-badge">{save}</span>' if save else ''
        annual_total = t.get('price_annual', 0)

        if price_hidden:
            price_html = '<span class="p-price">Coming Soon</span>'
            annual_note_html = ""
        else:
            price_display = f"${t['price_monthly']}" if t['price_monthly'] > 0 else "$0"
            price_html = (f'<span class="p-price" data-monthly="{t["price_monthly"]}" '
                          f'data-annual="{ann_permo}">{price_display}</span>\n'
                          f'    <span class="p-price-unit">/mo</span>')
            annual_note_html = (f'<p class="p-annual-note" data-annual-note="{ann}/mo billed annually '
                                f'(${annual_total}/yr){save_span}">\n'
                                f'    {ann}/mo billed annually (${annual_total}/yr){save_span}\n  </p>')

        btn_class = "btn-primary" if is_highlight else "btn-secondary"
        if price_hidden:
            btn_text = "Talk to Sales"
            btn_href = portal_urls.nav("contact.html")
        else:
            btn_text = "Get Started" if key == "free" else f"Start {t['name']}"
            btn_href = portal_urls.CONSOLE_URL

        ml_limit = t.get("ml_daily_limit")
        if t["ml_access"] and ml_limit is None:
            ml_line = '<li class="ml-feat">Unlimited ML win-probability scores</li>'
        elif t["ml_access"]:
            ml_line = f'<li class="ml-feat">ML win-probability scores ({ml_limit}/day)</li>'
        else:
            ml_line = '<li class="no">ML win-probability scoring</li>'

        # NOTE: deliberately NO data-freshness/"history" bullet. tiers.py carries a
        # `history` field ("delayed"/"full") but NO code path consumes it - free keys
        # receive the same live seasonal patterns as paid (verified 2026-06-12), so selling
        # "Delayed data (30-day lag)" was a false claim. The Free card is anchored on
        # the caps that ARE enforced: 1 market, 3 results/call, 5 ML scores/day.

        note_html = ""
        if key == "free":
            note_html = '<p class="p-note">No credit card required</p>'
        elif key == "business":
            note_html = f'<p class="p-note">Need more? <a href="{portal_urls.nav("contact.html")}" class="inline">Contact us</a> for Enterprise.</p>'

        taglines = {
            "free": "ML scores included (5/day) - no commitment.",
            "dev": "Build and prototype with full market access (100 ML scores/day).",
            "pro": "Unlimited ML across every market at 120 req/min - no web seat required.",
            "business": "High-volume production, team access, and redistribution rights - no web seat required.",
        }

        return f"""<div class="p-card{hl}">
  <p class="p-name">{t['name']}</p>
  <p class="p-tagline">{taglines.get(key, '')}</p>
  <div>
    {price_html}
  </div>
  {annual_note_html}
  <ul class="p-features">
    <li>{market_scope(t)}</li>
    {ml_line}
    <li>Up to {t['opp_limit']:,} results per call</li>
    <li>{rate_label(t['rate'])}</li>
    <li>Up to {t['max_keys']} API key{'s' if t['max_keys'] > 1 else ''}</li>
    <li>Daily pick + track record</li>
    {'<li>Priority support</li>' if key in ('pro','business') else '<li class="no">Priority support</li>'}
  </ul>
  <a href="{btn_href}" class="btn {btn_class}">{btn_text}</a>
  {note_html}
</div>"""

    cards_html = "\n".join([
        card_html("free", tiers["free"], False),
        card_html("dev",  tiers["dev"],  False),
        card_html("pro",  tiers["pro"],  True),
        card_html("business", tiers["business"], False),
    ])

    # The Founder's plan is a 50%-off discount on Pro's list price - with Pro not yet
    # priced there is nothing to discount, so hold the strip until pricing goes live.
    founder_strip_html = ""
    if API_PRICING_LIVE:
        founder_strip_html = f"""<div class="founder-strip">
      <div>
        <h3>Founder's plan - first 100 only</h3>
        <p>Get <strong>Pro at $99/mo</strong> (50% off) for your first 12 months, in exchange for
           your logo and a short tracked-record testimonial. Use code <code>FOUNDER</code> at
           checkout. When the first 100 seats are gone, this is gone.</p>
      </div>
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary" style="white-space:nowrap;">Claim a founder seat</a>
    </div>"""

    # The monthly/annual toggle only ever switches a price display - with paid pricing not
    # yet live there is nothing for it to switch (paid cards show "Coming Soon"; Free is
    # $0 either way), so swap it for a single muted note instead of an inert control.
    if API_PRICING_LIVE:
        billing_toggle_html = """<div class="billing-toggle">
      <button class="billing-btn active" id="btn-monthly" onclick="setBilling('monthly')">Monthly</button>
      <button class="billing-btn" id="btn-annual" onclick="setBilling('annual')">Annual <span class="save-badge">2 months free</span></button>
    </div>"""
    else:
        billing_toggle_html = ('<p class="p-note" style="text-align:center;margin-bottom:24px;">'
                                'Paid plans launch soon. The Free tier and bring-your-own-key access '
                                'are open now.</p>')

    body = f"""
<section class="page-hero" style="padding-bottom:40px;">
  <div class="container">
    <h1><span class="gradient-text-w">API &amp; MCP Pricing</span></h1>
    <p class="sub">A seasonal-pattern research API over REST and MCP. Free tier includes ML scores (5/day),
       the daily pick, and the verified track record. Dev opens 6 markets (US stocks + ETFs); Pro opens
       all 15 and removes the ML cap; Business adds redistribution rights and team controls.</p>
    <p class="hero-note" style="margin-top:14px;">No signup to try it: <code style="color:var(--accent);">tw_demo_explore</code> is a public demo token - a real authenticated call in about 30 seconds, no key, no card.</p>
  </div>
</section>

<section class="section" style="padding-top:20px;">
  <div class="container">
    {billing_toggle_html}

    <div class="pricing-grid">
      {cards_html}
    </div>

    {founder_strip_html}

    <p class="bundle-note">Already subscribe to TradeWave? Your plan already includes API access -
       <strong>Analyst includes the Dev tier</strong> and <strong>Strategist includes Pro</strong>,
       at no extra cost. Just <a href="{portal_urls.CONSOLE_URL}">create a key</a>.
       Standalone Pro and Business are for builders without a web seat who need the published API caps
       (Pro 120 req/min, Business 300 req/min) and, on Business, redistribution rights - the bundled
       Strategist Pro key carries the identical 120 req/min cap.</p>

    <div class="section-head" style="margin-top:64px;">
      <h2 class="gradient-text-w">Built for teams and enterprises</h2>
      <p>Bring the edge layer into your org with the controls a security and procurement team expects -
         centralized multi-seat key management, audit logs, commercial seasonal-pattern redistribution
         rights, and enterprise single sign-on on Business and Enterprise plans, with a contractual SLA
         on Enterprise.</p>
    </div>
    <div class="card" style="max-width:880px;margin:0 auto;">
      <p style="color:var(--dim);line-height:1.7;">When you put a verifiable, conflict-free seasonal-pattern feed
        in front of a whole desk, the questions stop being about alpha and start being about governance.
        TradeWave runs on identity powered by WorkOS, gives admins centralized control of seats, keys, and
        billing, and writes an audit trail of who pulled which seasonal pattern and when. To be clear about scope:
        single sign-on and directory sync govern who can reach the human console - your API calls stay
        key-based on every plan, so a developer or service authenticates with a scoped API key, not your IdP.</p>
      <ul style="color:var(--dim);line-height:1.8;margin:14px 0 0;padding-left:20px;">
        <li><strong>Single sign-on and directory sync</strong> - SAML or OIDC plus SCIM provisioning through your identity provider (Okta, Azure AD, Google Workspace) to govern console access. Available on Business and Enterprise; talk to us to enable.</li>
        <li><strong>Multi-seat key management and centralized billing</strong> - issue, rotate, scope, and revoke API keys per developer or service from one admin view, on one invoice.</li>
        <li><strong>Audit logs</strong> - a time-stamped record of key usage and seasonal-pattern access, exportable for your own compliance and review.</li>
        <li><strong>A service-level agreement</strong> - uptime and support commitments so the seasonal-pattern feed can sit in a production trading workflow. Contractual SLA on Enterprise; Business includes priority support.</li>
        <li><strong>Commercial seasonal-pattern redistribution rights</strong> - license TradeWave seasonal patterns into your own product or feed, as percentage movement and the 0-100 seasonal index only, never raw prices. Granted by written agreement on Business and Enterprise - the boundaries live in the <a href="api-terms.html" class="inline">API Terms</a>.</li>
      </ul>
      <div style="text-align:center;margin-top:22px;">
        <a href="{portal_urls.nav('contact.html')}" class="btn btn-primary">Contact sales</a>
      </div>
    </div>
  </div>
</section>

<!-- ML callout -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Unlimited ML win-probability scoring is the Pro upsell</h2>
      <p>Every plan includes ML scores - free starts at 5/day, Dev gets 100/day.
         Pro and Business unlock unlimited ML calls via the score_opportunities endpoint,
         the 62-feature model that assigns win probability and predicted return to each setup.</p>
    </div>
    <div class="grid-2" style="max-width:860px;margin:0 auto;">
      <div class="card">
        <p style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:12px;">Free / Dev - ML included (metered)</p>
        <div class="code-block"><span class="cm"># Ranked seasonal setups + ML on every tier</span>
GET /v1/opportunities?market=0&amp;min_win_rate=0.60
<span class="cm"># Returns: symbol, entry, hold, sharpe, win_rate, avg_return</span>
POST /v1/score  <span class="cm"># free=5/day, dev=100/day</span>
<span class="cm"># Returns: ml_score, win_prob, pred_return, pred_mfe</span></div>
        <p style="font-size:13px;color:var(--dim);margin-top:14px;line-height:1.6;">
          Free gets a real taste of ML - 5 scored seasonal patterns per day. Dev raises that to 100.
          Both tiers get the same pattern quality; the limit is what scales with the plan.
        </p>
      </div>
      <div class="card" style="border-color:var(--accent);box-shadow:0 0 40px rgba(99,102,241,.15);">
        <p style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--accent);margin-bottom:12px;">Pro+ - Unlimited ML scoring</p>
        <div class="code-block"><span class="cm"># No daily cap on ML calls</span>
POST /v1/score  <span class="cm"># unlimited</span>
<span class="kw">win_prob</span>: <span class="nu">0.81</span>
<span class="kw">pred_return</span>: <span class="nu">+4.2%</span>
<span class="kw">ml_score</span>: <span class="nu">87</span></div>
        <p style="font-size:13px;color:var(--dim);margin-top:14px;line-height:1.6;">
          Pro removes the daily ML cap entirely. Run the scorer across every setup in
          every market as often as you need - score a whole universe, not a sample. These are
          historical, forward-tested probabilities, not predictions; Pro just lets you compute
          them without limit.
        </p>
      </div>
    </div>
  </div>
</section>

<!-- FAQ -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Pricing FAQ</h2>
    </div>
    <div style="max-width:720px;margin:0 auto;">
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          Can I use my TradeWave web subscription to get API access?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          Yes. Analyst subscribers automatically receive Dev-tier API access;
          Strategist subscribers receive Pro-tier access. A standalone API
          subscription is also available if you want API-only access at any tier.
        </p>
      </details>
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          What counts as a market?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          TradeWave covers 15 active markets: Dow 30, NASDAQ 100, S&amp;P 500, and Russell 1000
          stocks, the Wilshire 5000, indices, futures and commodities, Forex (all and liquid),
          government bonds, ETFs, the London exchange, Toronto stocks, and crypto currencies.
          The Free tier includes S&amp;P 500 stocks only.
        </p>
      </details>
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          Does the API ever return raw prices?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          No. By design the API exposes seasonal patterns only - seasonal pattern statistics,
          win rates, percentage returns, and ML scores. No OHLCV data, no last-price
          endpoints. This keeps the output interpretable and keeps licensing clean.
        </p>
      </details>
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          What am I allowed to do with the seasonal patterns?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          Free, Dev, and Pro are internal-use plans: use seasonal patterns in, and display them within, your own
          application, research, and team, with attribution to TradeWave. Redistribution and resale to anyone
          outside your org are reserved for Business and Enterprise, where you can license the derived values
          (percentage movement and the 0-100 seasonal index, never raw prices) into your own product or feed
          by written agreement. Full boundaries are in the <a href="api-terms.html" class="inline">API Terms</a>.
        </p>
      </details>
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          What happens if I exceed a rate limit?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          The API returns HTTP 429 with a Retry-After header. It does not drop
          the connection or charge overages. The per-minute bucket resets every 60 seconds;
          the daily bucket resets at midnight UTC.
        </p>
      </details>
      <details style="padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          Can I cancel or change tiers at any time?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          Yes. Upgrades take effect immediately; downgrades take effect at the next
          billing cycle. No lock-in periods. Annual subscriptions are non-refundable
          after the first 14 days.
        </p>
      </details>
    </div>
  </div>
</section>

<script>
function setBilling(mode) {{
  document.getElementById('btn-monthly').classList.toggle('active', mode === 'monthly');
  document.getElementById('btn-annual').classList.toggle('active', mode === 'annual');
  document.querySelectorAll('.p-price').forEach(function(el) {{
    var m = parseInt(el.dataset.monthly, 10);
    var a = parseInt(el.dataset.annual, 10);
    if (m === 0) {{ el.textContent = '$0'; return; }}
    el.textContent = mode === 'monthly' ? '$' + m : '$' + a;
  }});
  document.querySelectorAll('[data-annual-note]').forEach(function(el) {{
    if (mode === 'annual') {{
      el.style.display = 'block';
    }} else {{
      el.style.display = 'none';
    }}
  }});
}}
// Hide annual notes on load (monthly is default).
document.querySelectorAll('[data-annual-note]').forEach(function(el) {{ el.style.display = 'none'; }});
</script>
"""
    return page_shell(
        "API & MCP Pricing",
        "TradeWave API plans from Free to Business. ML win-probability scores on every tier "
        "(free=5/day, dev=100/day, pro=unlimited). Derived seasonal patterns only - cleanly "
        "licensable, no raw OHLCV.",
        no_em_dash(body),
        active_nav="pricing",
    )


# ===========================================================================
# PAGE 3 - MCP Showcase
# ===========================================================================

def build_mcp() -> str:
    # Chat bubble helpers.
    def user(text: str) -> str:
        return f'<div class="chat-label">You</div><div class="bubble user">{text}</div>'

    def tool(text: str) -> str:
        return f'<div class="bubble tool-call">{text}</div>'

    def agent(text: str) -> str:
        return f'<div class="chat-label">Claude (via TradeWave MCP)</div><div class="bubble agent">{text}</div>'

    # Conversation 1: seasonal longs in S&P 500 stocks, ML-ranked.
    conv1 = f"""<div class="chat-window">
  <div class="chat-bar">
    <span class="chat-dot red"></span>
    <span class="chat-dot ylw"></span>
    <span class="chat-dot grn"></span>
    <span class="chat-title">Claude - Pro plan (unlimited ML)</span>
  </div>
  <div class="chat-body">
    {user("Find the strongest seasonal longs in S&P 500 stocks with greater than 70% win probability, ranked by ML score.")}
    {tool("tradewave.get_seasonal_opportunities(market='2', direction='long', min_win_rate=0.70)")}
    {tool("tradewave.score_opportunities([list of 14 setups])")}
    {agent("""I found <strong>14 seasonal long setups</strong> in the S&P 500 stocks market with historical win rates above 70%.
After running them through the ML scorer here are the top 5, ranked by ML score:<br><br>
<table class="bubble-table">
  <thead><tr><th>Symbol</th><th>Entry</th><th>Hold</th><th>Hist WR</th><th>ML Win Prob</th><th>ML Score</th><th>Pred Return</th></tr></thead>
  <tbody>
    <tr><td>AAPL</td><td>Jun 12</td><td>18d</td><td>74%</td><td class="hi">84%</td><td class="acc">91</td><td class="hi">+5.1%</td></tr>
    <tr><td>MSFT</td><td>Jun 14</td><td>22d</td><td>71%</td><td class="hi">81%</td><td class="acc">88</td><td class="hi">+4.3%</td></tr>
    <tr><td>NVDA</td><td>Jun 18</td><td>15d</td><td>76%</td><td class="hi">79%</td><td class="acc">84</td><td class="hi">+3.8%</td></tr>
    <tr><td>JPM</td><td>Jun 10</td><td>20d</td><td>70%</td><td class="hi">77%</td><td class="acc">80</td><td class="hi">+3.2%</td></tr>
    <tr><td>HD</td><td>Jun 15</td><td>17d</td><td>73%</td><td class="hi">76%</td><td class="acc">77</td><td class="hi">+2.9%</td></tr>
  </tbody>
</table><br>
<strong>AAPL entering Jun 12</strong> has the strongest ML conviction - an 84% ML win probability
vs. a 74% historical seasonal win rate, holding 18 days. The ML model is lifting all five setups
meaningfully above their seasonal base. This is a seasonal and ML read only - pair it with your own
check on fundamentals, earnings dates, and news before you act. Want the Trend Chart data for any of these?""")}
  </div>
</div>"""

    # Conversation 2: today's pick + track record.
    conv2 = f"""<div class="chat-window">
  <div class="chat-bar">
    <span class="chat-dot red"></span>
    <span class="chat-dot ylw"></span>
    <span class="chat-dot grn"></span>
    <span class="chat-title">Claude - Free plan (track record always available)</span>
  </div>
  <div class="chat-body">
    {user("What's today's pick and does it actually work? Show me the evidence.")}
    {tool("tradewave.get_daily_pick()")}
    {tool("tradewave.get_pick_track_record()")}
    {agent("""<strong>Today's pick: XOM (Exxon Mobil) - Long, entering today, 21-day hold.</strong><br><br>
ML win probability: <strong class="hi" style="color:var(--green)">81%</strong> &nbsp; |&nbsp;
Predicted return: <strong class="hi" style="color:var(--green)">+3.9%</strong> &nbsp; |&nbsp;
ML Score: <strong class="acc" style="color:var(--accent)">88</strong><br><br>
Now, the track record. Here are the last 10 resolved picks (all recorded before market open,
outcome measured at end of hold period):<br><br>
<table class="bubble-table">
  <thead><tr><th>Date</th><th>Symbol</th><th>Direction</th><th>Hold</th><th>Result</th><th>Return</th></tr></thead>
  <tbody>
    <tr><td>May 26</td><td>CVX</td><td>Long</td><td>18d</td><td class="hi">Win</td><td class="hi">+4.1%</td></tr>
    <tr><td>May 23</td><td>UNH</td><td>Long</td><td>20d</td><td class="hi">Win</td><td class="hi">+2.8%</td></tr>
    <tr><td>May 22</td><td>CAT</td><td>Long</td><td>15d</td><td style="color:var(--danger)">Loss</td><td style="color:var(--danger)">-1.2%</td></tr>
    <tr><td>May 21</td><td>XOM</td><td>Long</td><td>21d</td><td class="hi">Win</td><td class="hi">+3.6%</td></tr>
    <tr><td>May 20</td><td>AAPL</td><td>Long</td><td>18d</td><td class="hi">Win</td><td class="hi">+5.2%</td></tr>
    <tr><td>May 19</td><td>PG</td><td>Long</td><td>22d</td><td class="hi">Win</td><td class="hi">+1.9%</td></tr>
    <tr><td>May 16</td><td>HD</td><td>Long</td><td>17d</td><td style="color:var(--danger)">Loss</td><td style="color:var(--danger)">-0.8%</td></tr>
    <tr><td>May 15</td><td>JPM</td><td>Long</td><td>20d</td><td class="hi">Win</td><td class="hi">+2.5%</td></tr>
    <tr><td>May 14</td><td>MSFT</td><td>Long</td><td>15d</td><td class="hi">Win</td><td class="hi">+3.3%</td></tr>
    <tr><td>May 13</td><td>KO</td><td>Long</td><td>19d</td><td class="hi">Win</td><td class="hi">+4.7%</td></tr>
  </tbody>
</table><br>
<strong>8 of the last 10 resolved picks closed as wins (80%)</strong> - in line with the model's
predicted win probability. These outcomes were all locked in before market open, so there is no
look-ahead bias. The full record is available at <code>/v1/daily-pick/track-record</code>.""")}
  </div>
</div>"""

    # Conversation 3: Q3 seasonal portfolio across sectors.
    conv3 = f"""<div class="chat-window">
  <div class="chat-bar">
    <span class="chat-dot red"></span>
    <span class="chat-dot ylw"></span>
    <span class="chat-dot grn"></span>
    <span class="chat-title">Claude - Pro plan (ML enabled)</span>
  </div>
  <div class="chat-body">
    {user("Build me a Q3 seasonal portfolio across US sectors. I want diversified exposure, minimum 70% ML win probability, nothing overlapping by more than 5 days.")}
    {tool("tradewave.list_markets()")}
    {tool("tradewave.get_seasonal_opportunities(market='11', from='2026-07-01', to='2026-09-30', direction='long', min_win_rate=0.65, limit=50)")}
    {tool("tradewave.score_opportunities([all 50 sector ETF setups])")}
    {agent("""I've screened 50 Q3 sector ETF setups and filtered to those with ML win probability above 70%,
then selected one per sector sub-group to avoid overlap. Here is a 6-position portfolio:<br><br>
<table class="bubble-table">
  <thead><tr><th>Symbol</th><th>Sector</th><th>Entry</th><th>Exit</th><th>ML Win Prob</th><th>Pred Return</th><th>Sharpe</th></tr></thead>
  <tbody>
    <tr><td>XLE</td><td>Energy</td><td>Jul 3</td><td>Jul 24</td><td class="hi">82%</td><td class="hi">+4.8%</td><td>1.42</td></tr>
    <tr><td>XLK</td><td>Technology</td><td>Jul 8</td><td>Jul 30</td><td class="hi">78%</td><td class="hi">+3.9%</td><td>1.31</td></tr>
    <tr><td>XLV</td><td>Healthcare</td><td>Jul 15</td><td>Aug 5</td><td class="hi">75%</td><td class="hi">+2.6%</td><td>1.18</td></tr>
    <tr><td>XLI</td><td>Industrials</td><td>Aug 4</td><td>Aug 25</td><td class="hi">73%</td><td class="hi">+3.1%</td><td>1.24</td></tr>
    <tr><td>XLF</td><td>Financials</td><td>Aug 18</td><td>Sep 8</td><td class="hi">71%</td><td class="hi">+2.3%</td><td>1.09</td></tr>
    <tr><td>XLU</td><td>Utilities</td><td>Sep 2</td><td>Sep 23</td><td class="hi">70%</td><td class="hi">+2.0%</td><td>1.05</td></tr>
  </tbody>
</table><br>
<strong>No two positions overlap by more than 2 days.</strong> All six have ML win probabilities above your 70% threshold.
The positions are staggered across July, August, and September, so you are never holding more than two
at once. This is a seasonal and ML read only - I would pair each with a fundamentals and macro check before sizing.
Want me to pull the Trend Chart (the year-averaged 0-100 seasonal index) for any of these?""")}
  </div>
</div>"""

    body = f"""
<section class="page-hero">
  <div class="container">
    <div class="tag tag-ml" style="margin-bottom:20px;">MCP Server</div>
    <h1><span class="gradient-text-w">Ask ChatGPT and Claude for ranked seasonal patterns</span></h1>
    <p class="sub">
      Connect the TradeWave MCP server and your AI assistant answers in plain language:
      "the strongest seasonal longs in US stocks right now, ML-ranked" comes back as a table
      of real setups with win rates, ML probabilities, and a forward track record you can audit.
      Paste one URL, sign in with your TradeWave account, ask. No glue code, no API key juggling.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="{portal_urls.DOCS_URL}" class="btn btn-secondary">MCP Setup Docs</a>
    </div>
    <p style="font-size:13px;color:var(--dim);margin-top:16px;">17 purpose-built tools, 6 flagship plus 11 primitives. Try it with the public demo token <code style="font-size:12px;color:var(--accent);">tw_demo_explore</code> - a real call in about 30 seconds, no signup.</p>
  </div>
</section>

<!-- Setup strip -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Paste the URL, sign in, ask</h2>
      <p>TradeWave's MCP is a hosted HTTP server at <code style="font-size:13px;color:var(--accent);">{portal_urls.MCP_URL}</code>.
         In ChatGPT or Claude.ai, paste that URL into Settings - Connectors, click Connect, and
         sign in with your TradeWave account - no API key needed. Bring-your-own-login means metering
         follows the account you sign in with, not a shared key. In chat, AI scoring follows your
         TradeWave plan: it begins at Analyst (Explorer and Navigator see the deterministic seasonal
         patterns), and Strategist is unlimited. When a daily limit is reached the server returns a
         clear quota message, never a silent error.</p>
    </div>
    <div class="code-block" style="max-width:700px;margin:0 auto 16px;">
<span class="cm">// claude_desktop_config.json - Claude Desktop / Cursor (dev tools: bring your own API key)</span>
{{
  <span class="kw">"mcpServers"</span>: {{
    <span class="kw">"tradewave"</span>: {{
      <span class="kw">"command"</span>: <span class="st">"npx"</span>,
      <span class="kw">"args"</span>: [<span class="st">"-y"</span>, <span class="st">"mcp-remote"</span>, <span class="st">"{portal_urls.MCP_URL}"</span>, <span class="st">"--header"</span>, <span class="st">"Authorization: Bearer ${{TRADEWAVE_API_KEY}}"</span>]
    }}
  }}
}}</div>
    <p style="text-align:center;font-size:14px;color:var(--dim);">
      Dev tools keep bring-your-own-key auth: Claude Desktop and Cursor are stdio-only, so they
      bridge to the hosted server with the
      <code style="font-size:12px;color:var(--accent);">mcp-remote</code> npx shim shown above,
      passing a Bearer API key. There is no npm package to install.
      <a href="{portal_urls.DOCS_URL}" class="inline">Full setup guide</a>.
    </p>
  </div>
</section>

<!-- TradeWave + your broker recipe (GTM hero feature) -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Recipe: from chat question to placeable order ticket</h2>
      <p>Ask for the edge, get a broker-agnostic ticket, place it anywhere. We do not take your
         trades - we show you our receipts.</p>
    </div>
    <div class="card" style="max-width:840px;margin:0 auto;">
      <p style="color:var(--dim);line-height:1.7;margin-bottom:4px;">Ask TradeWave through MCP for the
        best seasonal setup and its ML win probability. You get back a Pattern Card with the receipts and
        a broker-agnostic order ticket: a side, a symbol, and the dates, with no price level for us to
        game. Hand it to whatever you already trade with. We find the edge and the timing; you place
        the trade. Because we never earn per trade, a no-pattern day is as honest as a buy.</p>
      <div style="margin:18px 0;padding:14px 18px;border-left:3px solid var(--accent);background:rgba(99,102,241,.07);border-radius:8px;color:var(--dim);font-style:italic;">"Using TradeWave, find the best seasonal long entering its window in the next two weeks across my markets, show me the win rate and ML probability, and give me the order ticket."</div>
      <ol style="color:var(--dim);line-height:1.85;padding-left:20px;margin:0;">
        <li><strong>Find</strong> - call find_best_opportunities to scan your in-scope markets and rank the strongest setups.</li>
        <li><strong>Read</strong> - off the top Pattern Card, take the edge, the year-by-year receipts, and the optional ML win-probability block (distinct from the historical win rate), plus the order ticket in next_step.</li>
        <li><strong>Place it anywhere</strong> - the MARKET/DAY ticket carries no price level, so it maps cleanly onto any in-chat execution app, broker SDK, or a manual confirmation.</li>
      </ol>
      <div style="text-align:center;margin-top:22px;">
        <a href="{portal_urls.LEARN_URL}/recipe-tradewave-plus-broker.html" class="btn btn-primary">See the full recipe</a>
      </div>
    </div>
  </div>
</section>

<!-- Tool reference -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">17 trading tools, purpose-built for agents</h2>
      <p>Six flagship tools cover the decisions; eleven primitives give an agent full control.
         Each is described so the model knows exactly when to call it - agents do not
         need to know the API, they just get asked questions and the right tool fires. Tools use
         progressive disclosure: a one-line decision by default, the full receipts and Trend Chart data on request.</p>
    </div>
    <h3 style="font-size:15px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px;">6 flagship tools</h3>
    <div class="grid-3" style="gap:16px;margin-bottom:32px;">
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">find_best_opportunities</p>
        <p style="font-size:13px;color:var(--dim);">Scan the caller's in-scope markets and return the strongest ranked seasonal setups as decision-ready Pattern Cards, each with a research hand-off.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">analyze_symbol</p>
        <p style="font-size:13px;color:var(--dim);">Deep dive on one symbol: its seasonal windows, the historical win rate, and the ML read, with the Trend Chart available on request.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">explain_pick</p>
        <p style="font-size:13px;color:var(--dim);">Unpack why a setup or the daily pick scores the way it does - the seasonal edge, the ML factors, and the receipts behind it.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">morning_briefing</p>
        <p style="font-size:13px;color:var(--dim);">The one-call start of the day: today's pick, the live track record with the last five outcomes, and the top setups entering their window now - say "good morning" and it fires.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">whats_seasonal_now</p>
        <p style="font-size:13px;color:var(--dim);">What is entering its seasonal window today across the caller's markets - the daily, universe-wide scan in one call.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">Flagship</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">compare_opportunities</p>
        <p style="font-size:13px;color:var(--dim);">Put two or more setups side by side on historical win rate, ML win probability, predicted return, and Sharpe to pick the better bet.</p>
      </div>
    </div>
    <h3 style="font-size:15px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px;">11 primitives</h3>
    <div class="grid-3" style="gap:16px;">
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">list_markets</p>
        <p style="font-size:13px;color:var(--dim);">Returns the 15 active markets and which are in the caller's tier scope.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">whoami</p>
        <p style="font-size:13px;color:var(--dim);">Reports the caller's tier, market scope, and remaining daily ML quota so an agent can plan its calls.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">describe_tradewave</p>
        <p style="font-size:13px;color:var(--dim);">Self-documents the method: a seasonal plus 62-feature ML edge only, blind to fundamentals, news, and live price - built to pair with the agent's own tools.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">list_symbols</p>
        <p style="font-size:13px;color:var(--dim);">All tradeable symbols in a market. Use to populate screener inputs.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_seasonal_opportunities</p>
        <p style="font-size:13px;color:var(--dim);">Find the best seasonal setups for a market and date window, ranked by edge. Symbol, direction, entry, hold, Sharpe, win rate, average return.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_symbol_patterns</p>
        <p style="font-size:13px;color:var(--dim);">All seasonal patterns for one specific symbol across its available windows - direction, entry, hold, win rate, Sharpe.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_seasonal_pattern</p>
        <p style="font-size:13px;color:var(--dim);">Aggregate seasonal pattern statistics for a symbol - win rates, average/median return, Sharpe across years.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_opportunity_chart</p>
        <p style="font-size:13px;color:var(--dim);">The Trend Chart data for a setup: a single year-averaged, normalized 0-100 seasonal index curve (the typical within-year shape), not prices. Data only - agents format the output.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">All tiers (unlimited on Pro+)</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">score_opportunities</p>
        <p style="font-size:13px;color:var(--dim);">ML win_prob, pred_return, pred_mfe, and ml_score for a list of setups. Free=5/day, Dev=100/day, Pro+ = unlimited. Returns a quota message when the daily limit is hit.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_daily_pick</p>
        <p style="font-size:13px;color:var(--dim);">Today's ML-selected featured pick with full metadata. Available to all tiers as a credibility proof point.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_pick_track_record</p>
        <p style="font-size:13px;color:var(--dim);">Full forward-recorded win/loss history of past picks. The hook - not a backtest, a forward ledger you can audit.</p>
      </div>
    </div>
  </div>
</section>

<!-- For data buyers and institutions -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">For data buyers and institutions</h2>
      <p>The same server, read through a licensing lens. The API returns derived values only:
         percentages, a 0-100 seasonal index, and ML probabilities, never raw OHLCV. That keeps it
         outside the exchange real-time market-data redistribution regime, so it is cleanly licensable
         with no exchange agreements, no per-terminal fees, and no market-data audits on your side.</p>
    </div>
    <div class="grid-3" style="gap:16px;margin-bottom:24px;">
      <div class="card" style="padding:22px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.10);">
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:8px;">Licensing superpower</p>
        <p style="font-size:13px;color:var(--dim);line-height:1.7;">Because derived values, not exchange-licensed prices, cross the wire, the feed is cleanly licensable. The boundaries live in the <a href="api-terms.html" class="inline">API Terms</a>.</p>
      </div>
      <div class="card" style="padding:22px 24px;">
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:8px;">Redistribution under license</p>
        <p style="font-size:13px;color:var(--dim);line-height:1.7;">Internal and personal use on Free, Dev, and Pro. Redistribute the derived values to your own end users under a written license at <strong>Business</strong>. Custom white-label, multi-tenant, and downstream-feed scope at <strong>Enterprise</strong>.</p>
      </div>
      <div class="card" style="padding:22px 24px;">
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:8px;">Data integrity</p>
        <p style="font-size:13px;color:var(--dim);line-height:1.7;">Deterministic, the same inputs return the same numbers. An auditable public record, every pick logged before the outcome. End-of-day data across the US-market universe.</p>
      </div>
    </div>
    <div class="card" style="max-width:920px;margin:0 auto;padding:20px 26px;border-left:3px solid var(--accent);background:rgba(99,102,241,.06);">
      <p style="font-size:14px;color:var(--dim);line-height:1.75;margin:0;">
        <strong style="color:var(--text);">Enterprise, by contact sales.</strong> Custom volume, a contractual SLA with uptime and
        service credits, SSO and SCIM with audit logs, an MSA and DPA with security review, invoicing with PO and net-30,
        and dedicated support. SSO and SCIM are available on Business and Enterprise; a contractual SLA is Enterprise-only (Business includes priority support). There is no self-serve SLA;
        <a href="{portal_urls.nav('contact.html')}" class="inline">talk to sales</a> to scope the agreement.
      </p>
    </div>
  </div>
</section>

<!-- Example conversations -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">What it looks like in practice</h2>
      <p>These are realistic example conversations. Numbers are illustrative.
         The MCP server is calling live API endpoints behind each tool call.</p>
    </div>

    <h3 style="font-size:18px;font-weight:700;color:var(--dim);margin-bottom:16px;text-align:center;">
      Example 1 - Scan S&P 500 stocks for ML-ranked longs
    </h3>
    {conv1}

    <h3 style="font-size:18px;font-weight:700;color:var(--dim);margin-bottom:16px;text-align:center;margin-top:32px;">
      Example 2 - Today's pick and its track record
    </h3>
    {conv2}

    <h3 style="font-size:18px;font-weight:700;color:var(--dim);margin-bottom:16px;text-align:center;margin-top:32px;">
      Example 3 - Build a diversified Q3 seasonal portfolio
    </h3>
    {conv3}
  </div>
</section>

<section class="section">
  <div class="container" style="text-align:center;">
    <h2 class="gradient-text-w" style="font-size:36px;font-weight:800;margin-bottom:16px;">Ready to connect?</h2>
    <p style="color:var(--dim);font-size:17px;max-width:600px;margin:0 auto 32px;line-height:1.7;">
      Paste the server URL into ChatGPT or Claude.ai and sign in with your TradeWave
      account, or drop a free API key into Claude Desktop or Cursor, and ask your
      first question in under 5 minutes. <a href="pricing.html" class="inline">See pricing</a>.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="{portal_urls.DOCS_URL}" class="btn btn-secondary">Full MCP Docs</a>
      <a href="pricing.html" class="btn btn-ghost">See Pricing</a>
    </div>
  </div>
</section>
"""
    return page_shell(
        "TradeWave MCP - Use TradeWave in Claude, Cursor, and ChatGPT",
        "Add TradeWave to ChatGPT or Claude and sign in with your TradeWave account, or drop an API key into Claude Desktop or Cursor. "
        "17 purpose-built trading tools (6 flagship plus 11 primitives) for seasonal analysis and ML-scored seasonal patterns.",
        no_em_dash(body),
        active_nav="mcp",
    )


# ===========================================================================
# PAGE 4 - Use Cases
# ===========================================================================

def build_use_cases() -> str:
    dev_opens_note = "Dev ($39/mo) opens" if API_PRICING_LIVE else "Dev opens"
    dev_prototyping_note = ("Dev tier at $39/mo for prototyping; no commitment to full plan"
                             if API_PRICING_LIVE else
                             "Dev tier for prototyping; no commitment to full plan")
    body = f"""
<section class="page-hero">
  <div class="container">
    <h1><span class="gradient-text-w">Who uses the TradeWave API</span></h1>
    <p class="sub">
      Concrete things people build on the API and MCP server - a personal scanner, an ML score
      layer in a backtest, a seasonal tab in a fintech product. Three audiences, mapped to the tier
      that unlocks each one.
    </p>
  </div>
</section>

<!-- Use case 1 -->
<section class="section">
  <div class="container">
    <div class="grid-2" style="gap:40px;align-items:center;max-width:1000px;margin:0 auto;">
      <div>
        <span class="who">Indie devs and prosumer quants</span>
        <h2 style="font-size:30px;font-weight:800;margin-bottom:16px;" class="gradient-text-w">
          Build a seasonal scanner without building the data stack
        </h2>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:20px;">
          Wire the MCP server into Claude or ChatGPT and you have a working scanner in one afternoon:
          ask "rank the strongest seasonal longs in S&P 500 stocks this week by ML win probability"
          and get a ranked table back, no terminal, no separate data seat. Or skip the chat and hit
          <code style="font-size:13px;color:var(--accent);">/opportunities</code> from a cron job to
          email yourself the same list every morning. TradeWave supplies the seasonal and ML edge;
          you - or the assistant - pair it with news and fundamentals.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          Free covers the build: S&P 500 stocks, the daily pick, 5 ML win-probability scores/day,
          and the full track record - enough to ship a personal tool end to end. {dev_opens_note}
          all 15 markets and 100 ML scores/day; Pro lifts the ML cap entirely.
        </p>
        <ul class="check-list">
          <li>Two surfaces, one account: REST for code, MCP for the chat window</li>
          <li>Daily pick before the open with an ML win-probability score</li>
          <li>Forward-recorded track record you can pull and audit yourself</li>
          <li>Connect ChatGPT or Claude in under 5 minutes - sign in, no API key to manage</li>
        </ul>
      </div>
      <div class="card" style="padding:32px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:16px;">Typical workflow</p>
        <div style="display:flex;flex-direction:column;gap:12px;">
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">1</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Create a free TradeWave account (no credit card).</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">2</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Paste the MCP server URL into ChatGPT or Claude.ai and sign in (dev tools like Claude Desktop and Cursor use an API key instead).</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">3</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Ask Claude for seasonal setups in any market - get a ranked table in seconds.</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">4</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Free includes 5 ML scores/day. Upgrade to Pro for unlimited ML scoring when you need it.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- Use case 2 -->
<section class="section alt">
  <div class="container">
    <div class="grid-2" style="gap:40px;align-items:center;max-width:1000px;margin:0 auto;">
      <div class="card" style="padding:32px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:16px;">Example API call (Python)</p>
        <div class="code-block">
<span class="kw">import</span> requests

<span class="cm"># Get ML-scored S&P 500 stock setups entering this week</span>
resp = requests.<span class="fn">get</span>(
    <span class="st">"{portal_urls.API_BASE}/opportunities"</span>,
    params={{
        <span class="st">"market"</span>: <span class="st">"2"</span>,        <span class="cm"># S&P 500 stocks (free tier)</span>
        <span class="st">"direction"</span>: <span class="st">"long"</span>,
        <span class="st">"min_win_rate"</span>: <span class="nu">0.65</span>,
        <span class="st">"limit"</span>: <span class="nu">20</span>
    }},
    headers={{<span class="st">"X-API-Key"</span>: api_key}}
)

<span class="cm"># Score them with ML (metered on Free/Dev, unlimited on Pro+)</span>
setups = [{{<span class="st">"symbol"</span>: o[<span class="st">"symbol"</span>], <span class="st">"date"</span>: o[<span class="st">"entry_date"</span>],
           <span class="st">"days_out"</span>: o[<span class="st">"days_out"</span>], <span class="st">"direction"</span>: o[<span class="st">"direction"</span>]}}
          <span class="kw">for</span> o <span class="kw">in</span> resp.json()[<span class="st">"opportunities"</span>]]
score_resp = requests.<span class="fn">post</span>(
    <span class="st">"{portal_urls.API_BASE}/score"</span>,
    json={{<span class="st">"market"</span>: <span class="st">"2"</span>, <span class="st">"opportunities"</span>: setups}},
    headers={{<span class="st">"X-API-Key"</span>: api_key}}
)
<span class="cm"># Returns: ml_score, win_prob, pred_return, pred_mfe per setup</span></div>
      </div>
      <div>
        <span class="who">Quants, RIAs, and small funds</span>
        <h2 style="font-size:30px;font-weight:800;margin-bottom:16px;" class="gradient-text-w">
          A programmatic ML score layer, not another data subscription
        </h2>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:20px;">
          The API delivers ranked seasonal setups and ML scores in JSON. Pipe them into
          your existing backtest framework, portfolio optimizer, or risk model. No
          database to maintain, no ETL, no price-data licensing headache.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          TradeWave covers 15 markets: Dow 30, NASDAQ 100, S&P 500, and Russell 1000 stocks,
          the Wilshire 5000, indices, futures and commodities, Forex, government bonds, ETFs,
          the London exchange, Toronto stocks, and crypto. The ML model currently scores six of
          those markets at the symbol level (the four US stock universes, the Wilshire 5000, and ETFs).
          The seasonal and ML read is a statistical edge only - pair it with your own fundamentals,
          news, and macro analysis.
        </p>
        <ul class="check-list">
          <li>Drop ranked setups straight into a backtest input or a weekly research-note generator</li>
          <li>REST API with JSON responses - no proprietary SDK required</li>
          <li>Seasonal patterns only - no raw price licensing, no OHLCV compliance burden</li>
          <li class="ml">ML win_prob and pred_return on every tier - free=5/day, dev=100/day, pro=unlimited (6 ML-eligible markets)</li>
          <li>Up to 1,000 results per call on Pro, 5,000 on Business</li>
          <li>120 req/min on Pro - compatible with intraday sweep workflows</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<!-- Use case 3 -->
<section class="section">
  <div class="container">
    <div class="grid-2" style="gap:40px;align-items:center;max-width:1000px;margin:0 auto;">
      <div>
        <span class="who">Fintech builders and platform developers</span>
        <h2 style="font-size:30px;font-weight:800;margin-bottom:16px;" class="gradient-text-w">
          Ship a seasonal-analysis feature in a day, not a quarter
        </h2>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:20px;">
          Embedding seasonal patterns in your app used to mean building a data pipeline,
          licensing historical prices, training your own model, and maintaining all of it.
          With the TradeWave API you call one endpoint and get a ranked, scored, and
          explained output your users can act on.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          The Business tier (300 req/min, 250,000 req/day, 50 API keys) is sized for
          multi-tenant products - no web seat required - and adds redistribution rights so
          you can serve the derived values to your own end users under license. Enterprise is
          available for custom rate limits, SLAs, and white-label use.
        </p>
        <ul class="check-list">
          <li>No raw price data means no exchange license to negotiate</li>
          <li>MCP-ready: surface TradeWave seasonal patterns inside any AI-native product</li>
          <li>Multiple API keys per account - one per tenant or environment</li>
          <li>Outputs are percentage returns - safe to display without price context</li>
          <li>{dev_prototyping_note}</li>
        </ul>
      </div>
      <div class="card" style="padding:32px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:16px;">What you ship to users</p>
        <div style="display:flex;flex-direction:column;gap:16px;">
          <div style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);border-radius:12px;padding:16px 20px;">
            <p style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px;">Seasonal opportunity screener</p>
            <p style="font-size:13px;color:var(--dim);line-height:1.6;">Filter by market, date window, direction, win rate - return ranked table. One API call.</p>
          </div>
          <div style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);border-radius:12px;padding:16px 20px;">
            <p style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px;">ML-scored watchlist</p>
            <p style="font-size:13px;color:var(--dim);line-height:1.6;">User adds tickers to a watchlist, your app scores them nightly against upcoming seasonal windows. Available on every tier (quota scales with plan; unlimited on Pro+).</p>
          </div>
          <div style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);border-radius:12px;padding:16px 20px;">
            <p style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px;">In-app seasonal tab + agent tool</p>
            <p style="font-size:13px;color:var(--dim);line-height:1.6;">Render a "Seasonal outlook" tab on any symbol page from one call, or expose TradeWave as a tool to your product's AI assistant so users can ask for it in chat. Same data, two surfaces.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- Institution / data-buyer band -->
<section class="section alt">
  <div class="container" style="max-width:1000px;">
    <div class="section-head">
      <span class="who">Institutions and data buyers</span>
      <h2 class="gradient-text-w">A seasonal-pattern feed you can actually license</h2>
      <p>The thing a data desk checks first: can we use this without dragging an exchange agreement
         behind it. The API returns derived values only - percentage returns, a 0-100 seasonal index,
         and ML win probabilities, never raw OHLCV - so it sits outside the real-time market-data
         redistribution regime. That means no exchange agreements, no per-terminal fees, and no
         market-data audits on your side to license it.</p>
    </div>
    <div class="grid-2" style="gap:24px;align-items:start;margin-bottom:28px;">
      <div class="card" style="padding:28px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:14px;">Redistribution scales with the tier</p>
        <ul class="check-list" style="margin:0;">
          <li>Free, Dev, and Pro: internal and personal use - your team, your code, your research</li>
          <li>Business: redistribute the derived seasonal values to your own end users under a written license</li>
          <li>Enterprise: custom white-label, multi-tenant, or a downstream feed, by agreement</li>
        </ul>
        <p style="font-size:13px;color:var(--muted);line-height:1.7;margin-top:14px;">
          The exact boundaries live in the <a href="api-terms.html" class="inline">API Terms</a>.
        </p>
      </div>
      <div class="card" style="padding:28px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:14px;">A number you can stand behind</p>
        <ul class="check-list" style="margin:0;">
          <li>Deterministic: the same inputs return the same numbers, every call</li>
          <li>An auditable public record - every pick is logged before the outcome is known</li>
          <li>End-of-day data across the US-market universe, no intraday guesswork</li>
        </ul>
        <p style="font-size:13px;color:var(--muted);line-height:1.7;margin-top:14px;">
          SSO/SCIM and audit logs are available on Business and Enterprise; a contractual SLA is
          Enterprise-only (Business includes priority support) - talk to sales to scope them.
        </p>
      </div>
    </div>
  </div>
</section>

<!-- Teams and enterprises band -->
<section class="section">
  <div class="container" style="max-width:900px;">
    <div class="section-head">
      <h2 class="gradient-text-w">And one for whole desks: teams and enterprises</h2>
      <p>Quant funds and fintech platforms put the edge layer in front of a team: enterprise single
         sign-on (SAML or OIDC) and SCIM directory sync through your identity provider for the console,
         and multi-seat key management on one invoice. Single sign-on governs the console login; your
         API calls stay key-based on every plan. Powered by WorkOS, available on Business and Enterprise.</p>
    </div>
    <div style="text-align:center;">
      <a href="{portal_urls.nav('contact.html')}" class="btn btn-primary">Contact sales</a>
      <a href="pricing.html" class="btn btn-ghost" style="margin-left:12px;">See Business plan</a>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="section alt">
  <div class="container" style="text-align:center;">
    <h2 class="gradient-text-w" style="font-size:34px;font-weight:800;margin-bottom:16px;">
      Which use case fits you?
    </h2>
    <p style="color:var(--dim);font-size:17px;max-width:600px;margin:0 auto 32px;line-height:1.7;">
      All three start with the same free API key. No credit card, no commitment.
      The plan you need becomes obvious once you have the data in front of you.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="pricing.html" class="btn btn-secondary">Compare Plans</a>
      <a href="mcp.html" class="btn btn-ghost">MCP Showcase</a>
    </div>
  </div>
</section>
"""
    return page_shell(
        "TradeWave API Use Cases - Devs, Quants, Fintech Builders",
        "What people build on the TradeWave API and MCP server: indie devs shipping a seasonal "
        "scanner, quants adding an ML score layer to a backtest, and fintech builders embedding a "
        "seasonal tab. Each mapped to the tier that unlocks it.",
        no_em_dash(body),
        active_nav="use-cases",
    )


def build_agents() -> str:
    """The 'For AI agents' page (agent-era positioning). Copy authored + honesty-critiqued,
    stored in for_agents_copy.json so the long agent-facing copy stays out of the code."""
    import json as _json
    from pathlib import Path as _Path
    raw = (_Path(__file__).parent / "for_agents_copy.json").read_text(encoding="utf-8")
    # The authored copy carries the prod URLs; rewrite to the env-driven hosts
    # (same idiom as portal_seo.build_llms) so dev/staging/prod each emit their own.
    raw = (raw
           .replace("https://api.tradewave.ai/v1", portal_urls.API_BASE)
           .replace("https://mcp.tradewave.ai", portal_urls.MCP_URL)
           .replace("https://developers.tradewave.ai", portal_urls.PORTAL_URL)
           .replace("https://tradewave.ai/account/api/keys", portal_urls.CONSOLE_URL))
    copy = _json.loads(raw)

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    secs = []
    for i, s in enumerate(copy.get("sections", [])):
        alt = " alt" if i % 2 == 0 else ""
        paras = "\n".join(
            f'      <p style="color:var(--dim);line-height:1.7;max-width:840px;margin:0 auto 14px;">{esc(p)}</p>'
            for p in s.get("body", []))
        bullets = ""
        if s.get("bullets"):
            items = "\n".join(f"        <li>{esc(b)}</li>" for b in s["bullets"])
            bullets = (f'      <ul style="color:var(--dim);line-height:1.8;max-width:840px;'
                       f'margin:8px auto 0;padding-left:20px;">\n{items}\n      </ul>')
        prompt_block = ""
        if "integrate" in s["heading"].lower():
            prompt_block = (
                '      <div style="max-width:840px;margin:18px auto 0;">'
                '<div style="font-size:12px;font-weight:700;color:var(--muted);margin-bottom:6px;letter-spacing:.04em;">'
                'PASTE INTO CLAUDE CODE OR CURSOR</div>'
                '<pre style="background:#0d0a14;border:1px solid rgba(255,255,255,.12);border-radius:10px;'
                'padding:16px 18px;overflow:auto;font-size:12.5px;line-height:1.55;color:#d1d5db;white-space:pre-wrap;">'
                f'<code>{esc(copy.get("paste_prompt", ""))}</code></pre></div>')
        cta_block = ""
        if "institution" in s["heading"].lower():
            cta_block = (
                '      <div style="max-width:840px;margin:18px auto 0;">'
                '<a href="mailto:hello@tradewave.ai" class="btn btn-secondary">Talk to sales</a></div>')
        secs.append(f"""
<section class="section{alt}">
  <div class="container">
    <div class="section-head"><h2 class="gradient-text-w">{esc(s['heading'])}</h2></div>
{paras}
{bullets}
{prompt_block}
{cta_block}
  </div>
</section>""")

    body = f"""
<section class="page-hero">
  <div class="container">
    <div class="tag tag-ml" style="margin-bottom:20px;">For AI agents</div>
    <h1><span class="gradient-text-w">{esc(copy.get('hero_headline', 'Built to be consumed by agents'))}</span></h1>
    <p class="sub">{esc(copy.get('hero_sub', ''))}</p>
    <div class="hero-ctas">
      <a href="{portal_urls.DOCS_URL}/quickstart.html" class="btn btn-primary">Read the quickstart</a>
      <a href="{portal_urls.MCP_SETUP_URL}" class="btn btn-secondary">Connect via MCP</a>
    </div>
    <p class="hero-note">No signup to try it: <code style="color:var(--accent);">tw_demo_explore</code> is a public demo token - a real call in about 30 seconds. The forward-tested track record is open to audit on the free tier.</p>
  </div>
</section>
{''.join(secs)}
<section class="section">
  <div class="container" style="text-align:center;">
    <h2 class="gradient-text-w" style="font-size:34px;font-weight:800;margin-bottom:16px;">Consume the edge, do not recompute it</h2>
    <div class="hero-ctas">
      <a href="{portal_urls.DOCS_URL}/quickstart.html" class="btn btn-primary">Read the quickstart</a>
      <a href="{portal_urls.LEARN_URL}/build-dont-rebuild.html" class="btn btn-secondary">Why not just compute it</a>
    </div>
  </div>
</section>
"""
    return page_shell(
        "For AI Agents - the edge your agent cannot compute but can consume",
        "TradeWave is built to be consumed by AI agents: decision-ready seasonal patterns scored by ML over "
        "REST and MCP, seasonal patterns only, with a forward-tested track record your agent can audit.",
        no_em_dash(body),
        active_nav="for-ai-agents",
    )


# ===========================================================================
# PAGE 6 - API Terms of Service (DRAFT - pending counsel review)
# ===========================================================================

def build_api_terms() -> str:
    """The API/MCP product terms. The consumer-site terms (terms.html) ban data mining
    and commercial use, which would prohibit the API product itself - so API contexts
    link HERE instead. DRAFT until counsel signs off; the banner says so explicitly.

    The per-tier boundary this page draws (the launch-blocker fix):
      Free / Dev / Pro  = DISPLAY of seasonal patterns inside your own application or team,
                          with attribution; no bulk redistribution, no resale of
                          raw API responses.
      Business          = redistribution only by separate written agreement
                          (percentages and the 0-100 seasonal index only).
    """
    effective = datetime.now().strftime("%B %d, %Y")
    body = f"""
<section class="page-hero" style="padding-bottom:24px;">
  <div class="container">
    <h1><span class="gradient-text-w">TradeWave API Terms of Service</span></h1>
    <p class="sub">The terms that govern the TradeWave Data API and the TradeWave MCP server.
       They apply to API keys, MCP connections, and everything returned by the
       <code style="font-size:14px;color:var(--accent);">/v1</code> endpoints.</p>
  </div>
</section>

<section class="section" style="padding-top:12px;">
  <div class="container" style="max-width:860px;">

    <div style="background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.45);border-radius:12px;
                padding:18px 24px;margin-bottom:36px;">
      <p style="font-size:14px;color:#fbbf24;font-weight:700;letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px;">
        Draft - pending counsel review</p>
      <p style="font-size:14px;color:var(--dim);line-height:1.7;">
        This page is a working draft published for transparency while the TradeWave API is in its
        launch window. It states the intended terms and has not yet been reviewed by counsel.
        Until a reviewed version replaces it, treat it as the operative statement of what each
        plan permits. Questions: <a href="{portal_urls.nav('contact.html')}" class="inline">contact us</a>.
        Draft last updated {effective}.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">1. What these terms cover</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        These API Terms govern your use of the TradeWave Data API, the TradeWave MCP server, API keys,
        and the data they return (together, the "API"). They are separate from the
        <a href="{portal_urls.nav('terms.html')}" class="inline">consumer website terms</a>, which govern
        the TradeWave web application for human visitors. Where the consumer terms restrict automated
        access, data mining, or commercial use of the website, those restrictions do not apply to use of
        the API under a valid API plan - programmatic access is exactly what the API is sold for, within
        the boundaries below. By creating an API key or connecting over MCP you accept these terms.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">2. What each plan permits: display vs. redistribution</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;margin-bottom:14px;">
        Every plan licenses you to <strong>use and display</strong> TradeWave seasonal patterns. What scales with
        the plan is the audience and the right to pass seasonal patterns onward:</p>
      <ul style="color:var(--dim);line-height:1.85;padding-left:20px;font-size:14px;">
        <li style="margin-bottom:10px;"><strong>Free, Dev, and Pro</strong> - you may use seasonal patterns in, and
          display them within, your own application, research, and team, including showing derived values
          (headlines, win rates, percentage returns, edge scores, ML probabilities) to the users of an app
          you operate, with attribution to TradeWave (a "Powered by TradeWave" notice or a link to
          tradewave-provided pages near the displayed seasonal patterns). You may NOT bulk-redistribute seasonal patterns,
          resell or relicense raw API responses, expose the API itself (or a thin proxy of it) as your own
          data product, or use the API to build or train a competing seasonal-pattern dataset or feed.</li>
        <li style="margin-bottom:10px;"><strong>Business</strong> - everything above, plus commercial
          seasonal-pattern redistribution rights <strong>by separate written agreement only</strong>. Redistribution
          covers licensing TradeWave seasonal patterns into your own product or downstream feed, and is limited to
          derived values: percentage movement and the 0-100 seasonal index. Raw API responses and the
          underlying historical series are never redistributable. Contact sales to put the written
          agreement in place; the plan alone does not grant redistribution.</li>
        <li><strong>Enterprise</strong> - custom scope by written agreement.</li>
      </ul>
      <p style="font-size:13px;color:var(--muted);line-height:1.7;margin-top:12px;">
        Plan caps (markets, results per call, ML scores per day, rate limits, key counts) are listed on
        the <a href="pricing.html" class="inline">pricing page</a> and enforced by the gateway.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">3. Seasonal patterns only - no raw market data</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        By design the API returns derived seasonal patterns: seasonal statistics, win rates, percentage returns,
        Sharpe ratios, the normalized 0-100 seasonal index, and ML scores. It never returns raw prices,
        quotes, or OHLCV bars. You agree not to attempt to reconstruct raw price series from API outputs,
        and not to present API outputs as a market-data feed. This is what keeps the product cleanly
        licensable for you as well as for us.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">4. Educational seasonal patterns, not investment advice</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        TradeWave is a research platform, not a brokerage and not an investment adviser. Every seasonal pattern is
        statistical, historical, and educational; none of it is personalized investment advice or a
        recommendation to buy or sell. Responses carry a <code style="font-size:12px;">disclaimer</code>
        field - if you display seasonal patterns to your users you must preserve that educational framing and must
        not present TradeWave outputs as personalized advice, your own advice, or a guarantee of results.
        Past performance does not guarantee future results. You are responsible for your own compliance
        obligations (and your users') in the jurisdictions where you operate.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">5. Keys and credentials</h3>
      <ul style="color:var(--dim);line-height:1.85;padding-left:20px;font-size:14px;">
        <li>API keys are issued per account and are confidential. Do not publish, share, sell, or embed
            them in client-side code.</li>
        <li>You are responsible for all usage under your keys. Rotate a key immediately if you suspect
            exposure (the console has one-click rotation).</li>
        <li>One account per customer; do not create accounts or keys to evade tier caps or metering.</li>
      </ul>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">6. Rate limits, metering, and abuse</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        Plans carry per-minute and per-day rate limits and a per-day ML metering allowance; the API
        answers over-limit requests with HTTP 429 and a Retry-After header, and exhausted ML quota with a
        clear in-band message. You agree to respect these limit responses and not to circumvent limits by
        rotating keys, accounts, or IP addresses. Automated access at or under your plan's limits is
        normal and expected - that is the product. Access patterns intended to scrape the catalog beyond
        plan scope, degrade the service, or probe its security are prohibited.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">7. Suspension and termination</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        We may suspend or revoke keys that violate these terms, with notice where practical. You can stop
        using the API and cancel the subscription at any time; upgrades take effect immediately and
        downgrades at the next billing cycle. Sections 2 (redistribution boundaries), 3 (seasonal patterns only),
        and 4 (no advice) survive termination with respect to data you obtained while subscribed.</p>
    </div>

    <div class="card" style="margin-bottom:28px;">
      <h3 style="margin-bottom:10px;">8. Service, changes, and contact</h3>
      <p style="font-size:14px;color:var(--dim);line-height:1.8;">
        The API is provided as-is; uptime and support commitments (SLA) exist only on plans that include
        them in writing. We version the API and announce breaking changes in the
        <a href="{portal_urls.DOCS_URL}/changelog.html" class="inline">changelog</a>. We may update these
        terms; material changes will be announced on this page and, for paid plans, by email. Questions
        about what your plan permits: <a href="{portal_urls.nav('contact.html')}" class="inline">contact us</a>.</p>
    </div>

    <p style="font-size:12px;color:var(--muted);line-height:1.7;">
      Related: <a href="{portal_urls.nav('privacy.html')}" class="inline">Privacy</a> -
      <a href="{portal_urls.nav('disclaimer.html')}" class="inline">Disclaimer</a> -
      <a href="{portal_urls.nav('terms.html')}" class="inline">Consumer website terms</a> (govern the web
      app, not the API) - <a href="pricing.html" class="inline">API pricing</a>.</p>
  </div>
</section>
"""
    return page_shell(
        "API Terms of Service (Draft)",
        "The terms that govern the TradeWave Data API and MCP server: per-tier display and "
        "redistribution boundaries, the seasonal-patterns-only principle, and the educational no-advice posture.",
        no_em_dash(body),
        active_nav="api-terms",
        robots="noindex, follow",  # draft pending counsel review - do not index until final
    )


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pages = [
        ("index.html",        build_index,     "Landing / hero"),
        ("pricing.html",      build_pricing,   "Pricing"),
        ("mcp.html",          build_mcp,       "MCP showcase"),
        ("for-ai-agents.html", build_agents,   "For AI agents"),
        ("use-cases.html",    build_use_cases, "Use cases"),
        ("api-terms.html",    build_api_terms, "API terms (draft)"),
    ]

    for filename, builder, label in pages:
        html = builder()
        # Final em-dash safety sweep on the whole document.
        html = no_em_dash(html)
        out = OUT_DIR / filename
        out.write_text(html, encoding="utf-8")
        print(f"  {label:18s}  ->  {out}  ({len(html):,} bytes)")

    print(f"\nAll pages written to {OUT_DIR}/")
    print("Validate: open any file in a browser or run:\n"
          "  python3 -m http.server --directory "
          f"{OUT_DIR} 8080")


if __name__ == "__main__":
    main()
