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

import sys
import os
from pathlib import Path
from datetime import datetime

# Allow importing from the repo root and the site lib.
REPO = Path(__file__).resolve().parent.parent.parent  # /home/flask
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "site" / "lib"))

from apiserver.tiers import API_TIERS        # the one source of truth
from text_utils import no_em_dash            # hard brand rule
import portal_urls                           # env-resolved public URLs

OUT_DIR = Path(__file__).parent / "out"
HEADER_PARTIAL = REPO / "site" / "templates" / "_tw_header.html"
YEAR = datetime.now().year

LEGAL_DISCLAIMER = (
    "TradeWave is a research platform. It is not a brokerage and does not "
    "execute trades. All data is based on historical analysis and is provided "
    "for informational and educational purposes only. Past performance does "
    "not guarantee future results."
)

# Market names for the 15 active keys (14/15 removed = Korea).
MARKET_NAMES = {
    "0": "S&P 500",
    "1": "NASDAQ 100",
    "2": "Energy (Futures)",
    "3": "Metals (Futures)",
    "4": "Agriculture (Futures)",
    "5": "Forex",
    "6": "European Equities",
    "7": "Asia-Pacific Equities",
    "8": "Emerging Markets",
    "9": "US Small/Mid Cap",
    "10": "Fixed Income / Rates",
    "11": "US Sector ETFs",
    "12": "Canadian Equities",
    "13": "Australian Equities",
    "16": "Crypto",
}

FREE_MARKET_NAME = MARKET_NAMES.get("2", "Energy (Futures)")  # free tier = market 2 only


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
      <a href="use-cases.html">Use Cases</a>
      <a href="{portal_urls.nav('contact.html')}">Contact</a>
      <a href="{portal_urls.nav('privacy.html')}">Privacy</a>
      <a href="{portal_urls.nav('terms.html')}">Terms</a>
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
@media (max-width:1024px) { .pricing-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width:768px) {
  .page-hero h1 { font-size:32px; }
  .page-hero .sub { font-size:16px; }
  .section-head h2 { font-size:28px; }
  .grid-3, .grid-2 { grid-template-columns:1fr; }
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


def page_shell(title: str, description: str, body: str, active_nav: str = "") -> str:
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

    # Inject API-specific nav items by appending them into the header's nav-links.
    # We do a targeted string insert so we don't need to fork the header partial.
    api_nav_snippet = """
      <a href="index.html">API</a>
      <a href="pricing.html">API Pricing</a>
      <a href="mcp.html">MCP</a>"""
    # Insert after the rewritten Research link so ordering is logical.
    header = header.replace(
        f'<a href="{portal_urls.nav("research.html")}">Research</a>',
        f'<a href="{portal_urls.nav("research.html")}">Research</a>' + api_nav_snippet,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - TradeWave</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="noindex, nofollow">
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
    # Illustrative track-record rows (framed as such, not stated as fact).
    track_rows = [
        ("2020", "63%", "78%", "+15pp", "52"),
        ("2021", "67%", "82%", "+15pp", "61"),
        ("2022", "61%", "76%", "+15pp", "48"),
        ("2023", "65%", "80%", "+15pp", "57"),
        ("2024", "66%", "81%", "+15pp", "60"),
        ("2025 YTD", "68%", "83%", "+15pp", "31"),
    ]
    rows_html = "\n".join(
        f'<tr><td class="td-year">{r[0]}</td>'
        f'<td class="td-base">{r[1]}</td>'
        f'<td class="td-win">{r[2]}</td>'
        f'<td class="td-lift">{r[3]}</td>'
        f'<td class="td-n">{r[4]}</td></tr>'
        for r in track_rows
    )

    body = f"""
<section class="page-hero">
  <div class="container">
    <div class="tag tag-ml" style="margin-bottom:20px;">Now Available - API + MCP</div>
    <h1>
      <span class="gradient-text-w">TradeWave API &amp; MCP</span><br>
      <span style="font-size:.62em;color:var(--dim);font-weight:600;">Seasonal + ML trading signals for your apps and AI agents</span>
    </h1>
    <p class="sub">
      The same ML win-probability engine that powers the TradeWave scorecard is
      now accessible as a REST API and a native MCP server. Your code and your
      AI assistants can query ranked seasonal setups, score them with the ML model,
      and verify the pick track record - all without exposing raw price data.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="mcp.html" class="btn btn-secondary">Connect to Claude</a>
    </div>
    <p class="hero-note">Free tier available - no credit card required</p>
  </div>
</section>

<!-- Differentiation strip -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Not another data feed</h2>
      <p>TradeWave exposes derived signals only - no raw OHLCV, no last-price lookups.
         Every endpoint returns interpreted output: seasonal tendency, ML probability, or
         a verified track-record entry. That is the edge.</p>
    </div>
    <div class="grid-3">
      <div class="card diff-card">
        <div class="diff-icon">&#127917;</div>
        <h3>ML win-probability on seasonal patterns</h3>
        <p>A 62-feature model trained on millions of historical setups scores every
           seasonal opportunity with a win probability and predicted return before
           market open. Every tier includes ML signals (free starts at 5/day; Pro is unlimited).
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
        <p>The TradeWave MCP server connects in two lines of config to Claude, Cursor,
           or any MCP-compatible host. Ask your AI assistant to find the strongest
           seasonal longs in energy, rank by ML score, and compare to the live
           track record - no glue code required.</p>
      </div>
    </div>
  </div>
</section>

<!-- Track Record as credibility proof -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Daily-pick track record</h2>
      <p>The ML-selected daily pick has been publicly recorded every market day.
         These illustrative figures show the kind of lift the ML layer delivers
         over base seasonal win rates - verify the actual record live via the API.</p>
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
          {rows_html}
        </tbody>
      </table>
    </div>
    <p style="text-align:center;font-size:12px;color:var(--muted);margin-top:16px;">
      Illustrative figures. Actual realized results available via
      <code style="font-size:11px;">/v1/daily-pick/track-record</code>.
      Past performance does not guarantee future results.
    </p>
    <div style="text-align:center;margin-top:28px;">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">See the Live Record</a>
      <a href="{portal_urls.nav('scorecard.html')}" class="btn btn-ghost" style="margin-left:12px;">View Scorecard</a>
    </div>
  </div>
</section>

<!-- Competitor comparison -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">How TradeWave compares</h2>
      <p>Seasonax is the closest alternative - Bloomberg-gated at ~$480/mo with no ML layer and no API.
         TradeWave undercuts that price and is accessible to any developer or AI agent today.</p>
    </div>
    <div class="comp-table-wrap">
      <table class="comp-table">
        <thead>
          <tr>
            <th>Feature</th>
            <th>TradeWave API</th>
            <th>Seasonax</th>
            <th>Bloomberg Terminal</th>
          </tr>
        </thead>
        <tbody>
          <tr><td class="feat-col">ML win-probability scoring</td><td class="tw-col">All tiers (unlimited on Pro+)</td><td class="no-col">No</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">REST API access</td><td class="tw-col">Yes - all tiers</td><td class="no-col">No</td><td class="no-col">Terminal only</td></tr>
          <tr><td class="feat-col">MCP / AI agent integration</td><td class="tw-col">Yes - native</td><td class="no-col">No</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">Verified pick track record</td><td class="tw-col">Yes - forward-recorded</td><td class="no-col">Backtest only</td><td class="no-col">No</td></tr>
          <tr><td class="feat-col">Signals only (no raw prices)</td><td class="tw-col">Yes - by design</td><td class="no-col">Mixed</td><td class="no-col">Raw data</td></tr>
          <tr><td class="feat-col">Starting price</td><td class="tw-col">Free</td><td>~$480/mo</td><td>~$24,000/yr</td></tr>
          <tr><td class="feat-col">No Bloomberg required</td><td class="tw-col">Yes</td><td class="no-col">No (integration)</td><td>Bloomberg IS the product</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<!-- CTAs -->
<section class="section">
  <div class="container" style="text-align:center;">
    <h2 class="gradient-text-w" style="font-size:36px;font-weight:800;margin-bottom:16px;">Start building today</h2>
    <p style="color:var(--dim);font-size:17px;max-width:600px;margin:0 auto 32px;line-height:1.7;">
      A free key gives you the Energy market, the daily pick, and 5 ML signals/day.
      Upgrade to Dev for all 15 markets, or Pro for unlimited ML scoring.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="pricing.html" class="btn btn-secondary">See All Plans</a>
      <a href="mcp.html" class="btn btn-ghost">MCP Setup Guide</a>
    </div>
  </div>
</section>
"""
    return page_shell(
        "TradeWave API & MCP - Seasonal + ML Trading Signals",
        "REST API and MCP server for seasonal pattern analysis with ML win-probability scoring. "
        "Connect to Claude, Cursor, or any AI agent in minutes.",
        no_em_dash(body),
    )


# ===========================================================================
# PAGE 2 - Pricing
# ===========================================================================

def build_pricing() -> str:
    tiers = API_TIERS  # from the single source of truth

    # Annual = 20% off (2 months free).
    def annual_price(monthly: int) -> str:
        if monthly == 0:
            return "$0"
        return f"${int(monthly * 0.8)}"

    def annual_savings(monthly: int) -> str:
        if monthly == 0:
            return ""
        saved = monthly * 12 - int(monthly * 0.8) * 12
        return f"Save ${saved}/yr"

    def rate_label(r: dict) -> str:
        return f"{r['per_minute']}/min, {r['per_day']:,}/day"

    def market_scope(t: dict) -> str:
        if len(t["markets"]) == 1:
            return f"1 market ({FREE_MARKET_NAME})"
        return f"All {len(t['markets'])} markets"

    def card_html(key: str, t: dict, is_highlight: bool) -> str:
        hl = ' highlight' if is_highlight else ''
        price_display = f"${t['price_monthly']}" if t['price_monthly'] > 0 else "$0"
        ann = annual_price(t['price_monthly'])
        save = annual_savings(t['price_monthly'])
        save_span = f' <span class="save-badge">{save}</span>' if save else ''

        btn_class = "btn-primary" if is_highlight else "btn-secondary"
        btn_text = "Get Started" if key == "free" else f"Start {t['name']}"
        btn_href = portal_urls.CONSOLE_URL

        ml_limit = t.get("ml_daily_limit")
        if t["ml_access"] and ml_limit is None:
            ml_line = '<li class="ml-feat">Unlimited ML win-probability signals</li>'
        elif t["ml_access"]:
            ml_line = f'<li class="ml-feat">ML win-probability signals ({ml_limit}/day)</li>'
        else:
            ml_line = '<li class="no">ML win-probability scoring</li>'

        history_label = "Full history" if t["history"] == "full" else "Delayed data (30-day lag)"

        note_html = ""
        if key == "free":
            note_html = '<p class="p-note">No credit card required</p>'
        elif key == "business":
            note_html = f'<p class="p-note">Need more? <a href="{portal_urls.nav("contact.html")}" class="inline">Contact us</a> for Enterprise.</p>'

        taglines = {
            "free": "ML signals included (5/day) - no commitment.",
            "dev": "Build and prototype with full market access (100 ML signals/day).",
            "pro": "Unlimited ML win-probability scoring. The full edge.",
            "business": "High-volume production and team access. Unlimited ML.",
        }

        return f"""<div class="p-card{hl}">
  <p class="p-name">{t['name']}</p>
  <p class="p-tagline">{taglines.get(key, '')}</p>
  <div>
    <span class="p-price" data-monthly="{t['price_monthly']}" data-annual="{int(t['price_monthly']*0.8)}">{price_display}</span>
    <span class="p-price-unit">/mo</span>
  </div>
  <p class="p-annual-note" data-annual-note="{ann}/mo billed annually{save_span}">
    {ann}/mo billed annually{save_span}
  </p>
  <ul class="p-features">
    <li>{market_scope(t)}</li>
    {ml_line}
    <li>{history_label}</li>
    <li>Up to {t['opp_limit']:,} results per call</li>
    <li>{rate_label(t['rate'])}</li>
    <li>Up to {t['max_keys']} API key{'s' if t['max_keys'] > 1 else ''}</li>
    <li>Daily pick + track record</li>
    {'<li>Priority support</li>' if key in ('pro','business') else '<li class="no">Priority support</li>'}
    {'<li>SLA guarantee</li>' if key == 'business' else ''}
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

    body = f"""
<section class="page-hero" style="padding-bottom:40px;">
  <div class="container">
    <h1><span class="gradient-text-w">API &amp; MCP Pricing</span></h1>
    <p class="sub">Start free with ML signals included (5/day). All tiers include the daily pick
       and the verified track record. Pro unlocks unlimited ML win-probability scoring.</p>
  </div>
</section>

<section class="section" style="padding-top:20px;">
  <div class="container">
    <div class="billing-toggle">
      <button class="billing-btn active" id="btn-monthly" onclick="setBilling('monthly')">Monthly</button>
      <button class="billing-btn" id="btn-annual" onclick="setBilling('annual')">Annual <span class="save-badge">Save 20%</span></button>
    </div>

    <div class="pricing-grid">
      {cards_html}
    </div>

    <div class="enterprise-strip">
      <div>
        <h3>Enterprise</h3>
        <p>Custom rate limits, dedicated infrastructure, white-label options, SLAs,
           and team SSO. Used by quant funds and fintech platforms that need more
           than the Business tier provides.</p>
      </div>
      <a href="{portal_urls.nav('contact.html')}" class="btn btn-secondary" style="white-space:nowrap;">Contact Sales</a>
    </div>
  </div>
</section>

<!-- ML callout -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Unlimited ML win-probability scoring is the Pro upsell</h2>
      <p>Every plan includes ML signals - free starts at 5/day, Dev gets 100/day.
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
          Free gets a real taste of ML - 5 scored signals per day. Dev raises that to 100.
          Both tiers get the same signal quality; the limit is what scales with the plan.
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
          every market as often as you need. A 70% base seasonal win rate plus an 81%
          ML win_prob is a materially different bet - and Pro gives you unlimited of those.
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
          TradeWave covers 15 active markets: S&amp;P 500, NASDAQ 100, Energy futures,
          Metals, Agriculture, Forex, European and Asia-Pacific equities, Emerging Markets,
          US Small/Mid Cap, Fixed Income, US Sector ETFs, Canadian equities, Australian
          equities, and Crypto. The Free tier includes Energy (futures) only.
        </p>
      </details>
      <details style="border-bottom:1px solid var(--border);padding:0;">
        <summary style="padding:18px 0;font-size:15px;font-weight:600;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;color:var(--text);">
          Does the API ever return raw prices?
          <span style="font-size:20px;color:var(--muted);">+</span>
        </summary>
        <p style="padding:0 0 18px;font-size:14px;color:var(--dim);line-height:1.7;">
          No. By design the API exposes signals only - seasonal pattern statistics,
          win rates, percentage returns, and ML scores. No OHLCV data, no last-price
          endpoints. This keeps the output interpretable and keeps licensing clean.
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
        "TradeWave API plans from Free to Business. ML win-probability signals on every tier "
        "(free=5/day, dev=100/day, pro=unlimited). No Bloomberg required.",
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

    # Conversation 1: seasonal longs in energy, ML-ranked.
    conv1 = f"""<div class="chat-window">
  <div class="chat-bar">
    <span class="chat-dot red"></span>
    <span class="chat-dot ylw"></span>
    <span class="chat-dot grn"></span>
    <span class="chat-title">Claude - Pro plan (unlimited ML)</span>
  </div>
  <div class="chat-body">
    {user("Find the strongest seasonal longs in energy with greater than 70% win probability, ranked by ML score.")}
    {tool("tradewave.get_seasonal_opportunities(market='2', direction='long', min_win_rate=0.70)")}
    {tool("tradewave.score_opportunities([list of 14 setups])")}
    {agent("""I found <strong>14 seasonal long setups</strong> in the Energy market with base win rates above 70%.
After running them through the ML scorer here are the top 5, ranked by ML score:<br><br>
<table class="bubble-table">
  <thead><tr><th>Symbol</th><th>Entry</th><th>Hold</th><th>Base WR</th><th>ML Win Prob</th><th>ML Score</th><th>Pred Return</th></tr></thead>
  <tbody>
    <tr><td>CL1</td><td>Jun 12</td><td>18d</td><td>74%</td><td class="hi">84%</td><td class="acc">91</td><td class="hi">+5.1%</td></tr>
    <tr><td>HO1</td><td>Jun 14</td><td>22d</td><td>71%</td><td class="hi">81%</td><td class="acc">88</td><td class="hi">+4.3%</td></tr>
    <tr><td>NG1</td><td>Jun 18</td><td>15d</td><td>76%</td><td class="hi">79%</td><td class="acc">84</td><td class="hi">+3.8%</td></tr>
    <tr><td>RB1</td><td>Jun 10</td><td>20d</td><td>70%</td><td class="hi">77%</td><td class="acc">80</td><td class="hi">+3.2%</td></tr>
    <tr><td>BZ1</td><td>Jun 15</td><td>17d</td><td>73%</td><td class="hi">76%</td><td class="acc">77</td><td class="hi">+2.9%</td></tr>
  </tbody>
</table><br>
<strong>CL1 (WTI crude) entering Jun 12</strong> has the strongest ML conviction - an 84% win probability
vs. a 74% base seasonal rate, holding 18 days. The ML model is lifting all five setups
meaningfully above their seasonal base. Want the chart data for any of these?""")}
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
    <tr><td>May 23</td><td>SLB</td><td>Long</td><td>20d</td><td class="hi">Win</td><td class="hi">+2.8%</td></tr>
    <tr><td>May 22</td><td>HAL</td><td>Long</td><td>15d</td><td style="color:var(--danger)">Loss</td><td style="color:var(--danger)">-1.2%</td></tr>
    <tr><td>May 21</td><td>XOM</td><td>Long</td><td>21d</td><td class="hi">Win</td><td class="hi">+3.6%</td></tr>
    <tr><td>May 20</td><td>CL1</td><td>Long</td><td>18d</td><td class="hi">Win</td><td class="hi">+5.2%</td></tr>
    <tr><td>May 19</td><td>PSX</td><td>Long</td><td>22d</td><td class="hi">Win</td><td class="hi">+1.9%</td></tr>
    <tr><td>May 16</td><td>MPC</td><td>Long</td><td>17d</td><td style="color:var(--danger)">Loss</td><td style="color:var(--danger)">-0.8%</td></tr>
    <tr><td>May 15</td><td>VLO</td><td>Long</td><td>20d</td><td class="hi">Win</td><td class="hi">+2.5%</td></tr>
    <tr><td>May 14</td><td>HO1</td><td>Long</td><td>15d</td><td class="hi">Win</td><td class="hi">+3.3%</td></tr>
    <tr><td>May 13</td><td>RB1</td><td>Long</td><td>19d</td><td class="hi">Win</td><td class="hi">+4.7%</td></tr>
  </tbody>
</table><br>
<strong>8 of the last 10 resolved picks closed as wins (80%)</strong> - consistent with the historical
ML win rate. These outcomes were all locked in before market open, so there is no
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
at once. Want me to run the seasonal chart data for any of these to see the year-by-year path?""")}
  </div>
</div>"""

    body = f"""
<section class="page-hero">
  <div class="container">
    <div class="tag tag-ml" style="margin-bottom:20px;">MCP Server</div>
    <h1><span class="gradient-text-w">TradeWave in your AI assistant</span></h1>
    <p class="sub">
      Connect the TradeWave MCP server to Claude, Cursor, or any MCP-compatible
      host. Your assistant gets access to 9 purpose-built trading tools and starts
      answering questions like these - no glue code, no API key juggling.
    </p>
    <div class="hero-ctas">
      <a href="{portal_urls.CONSOLE_URL}" class="btn btn-primary">Get a Free API Key</a>
      <a href="{portal_urls.DOCS_URL}" class="btn btn-secondary">MCP Setup Docs</a>
    </div>
  </div>
</section>

<!-- Setup strip -->
<section class="section alt">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">Two lines to connect</h2>
      <p>Add the TradeWave server to your MCP host config. Your API key gates the
         tier - ML signals work on every tier (free gets 5/day, Pro is unlimited).
         The server returns a clear quota message when the daily limit is reached, never a silent error.</p>
    </div>
    <div class="code-block" style="max-width:700px;margin:0 auto 32px;">
<span class="cm">// claude_desktop_config.json</span>
{{
  <span class="kw">"mcpServers"</span>: {{
    <span class="kw">"tradewave"</span>: {{
      <span class="kw">"command"</span>: <span class="st">"npx"</span>,
      <span class="kw">"args"</span>: [<span class="st">"@tradewave/mcp-server"</span>],
      <span class="kw">"env"</span>: {{ <span class="kw">"TRADEWAVE_API_KEY"</span>: <span class="st">"tw_your_key_here"</span> }}
    }}
  }}
}}</div>
    <p style="text-align:center;font-size:14px;color:var(--dim);">
      Also works with Cursor, Windsurf, and any host that supports the MCP protocol.
      <a href="{portal_urls.DOCS_URL}" class="inline">Full setup guide</a>.
    </p>
  </div>
</section>

<!-- Tool reference -->
<section class="section">
  <div class="container">
    <div class="section-head">
      <h2 class="gradient-text-w">9 trading tools, purpose-built for agents</h2>
      <p>Each tool is described so the model knows exactly when to call it. Agents do not
         need to know the API - they just get asked questions and the right tool fires.</p>
    </div>
    <div class="grid-3" style="gap:16px;">
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">list_markets</p>
        <p style="font-size:13px;color:var(--dim);">Returns the 15 active markets and which are in the caller's tier scope.</p>
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
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_opportunity_for_symbol</p>
        <p style="font-size:13px;color:var(--dim);">Deep dive into seasonal setups for one specific symbol across all available windows.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_seasonal_pattern</p>
        <p style="font-size:13px;color:var(--dim);">Aggregate seasonal pattern statistics for a symbol - win rates, average/median return, Sharpe across years.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_opportunity_chart</p>
        <p style="font-size:13px;color:var(--dim);">Per-year percentage paths plus average path for a setup. Data only - agents format the output, no image download required.</p>
      </div>
      <div class="card" style="padding:20px 24px;border-color:var(--accent);box-shadow:0 0 30px rgba(99,102,241,.12);">
        <p class="tag tag-ml" style="margin-bottom:10px;">All tiers (unlimited on Pro+)</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">score_opportunities</p>
        <p style="font-size:13px;color:var(--dim);">ML win_prob, pred_return, pred_mfe, and ml_score for a list of setups. Free=5/day, Dev=100/day, Pro+ = unlimited. Returns a quota message when the daily limit is hit.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_daily_pick</p>
        <p style="font-size:13px;color:var(--dim);">Today's ML-selected featured pick with full metadata. Available to all tiers as a credibility signal.</p>
      </div>
      <div class="card" style="padding:20px 24px;">
        <p class="tag tag-free" style="margin-bottom:10px;">All tiers</p>
        <p style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;">get_pick_track_record</p>
        <p style="font-size:13px;color:var(--dim);">Full forward-recorded win/loss history of past picks. The hook - not a backtest, a forward ledger you can audit.</p>
      </div>
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
      Example 1 - Scan energy for ML-ranked longs
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
      Get a free API key, add two lines to your MCP config, and ask your first
      question in under 5 minutes.
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
        "Connect the TradeWave MCP server to your AI assistant in two lines. "
        "9 purpose-built trading tools for seasonal analysis and ML-scored signals.",
        no_em_dash(body),
        active_nav="mcp",
    )


# ===========================================================================
# PAGE 4 - Use Cases
# ===========================================================================

def build_use_cases() -> str:
    body = f"""
<section class="page-hero">
  <div class="container">
    <h1><span class="gradient-text-w">Who uses the TradeWave API</span></h1>
    <p class="sub">
      Seasonal ML signals inside your code, your models, or your AI assistant.
      Three audiences, three different ways they extract the edge.
    </p>
  </div>
</section>

<!-- Use case 1 -->
<section class="section">
  <div class="container">
    <div class="grid-2" style="gap:40px;align-items:center;max-width:1000px;margin:0 auto;">
      <div>
        <span class="who">Retail and prosumer traders</span>
        <h2 style="font-size:30px;font-weight:800;margin-bottom:16px;" class="gradient-text-w">
          The AI assistant that knows when to trade
        </h2>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:20px;">
          Ask Claude or any MCP-compatible assistant "what should I look at in energy this week"
          and get a ranked list of seasonal longs with ML win probabilities - without opening
          a terminal, running a screener, or paying $480/mo to Seasonax.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          The free tier gives you the Energy futures market, the daily pick, 5 ML win-probability
          signals/day, and the full track record. The Dev tier adds all 15 markets and 100 ML signals/day
          for $39/mo. Pro unlocks unlimited ML scoring.
        </p>
        <ul class="check-list">
          <li>No Bloomberg required - works from any browser or AI chat window</li>
          <li>Daily pick delivered before market open with ML confidence score</li>
          <li>Forward-recorded track record you can audit yourself</li>
          <li>Connect to Claude in under 5 minutes via the MCP server</li>
        </ul>
      </div>
      <div class="card" style="padding:32px;">
        <p style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:16px;">Typical workflow</p>
        <div style="display:flex;flex-direction:column;gap:12px;">
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">1</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Get a free API key from the console (no credit card).</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">2</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Add the TradeWave MCP server to Claude Desktop in two lines.</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">3</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Ask Claude for seasonal setups in any market - get a ranked table in seconds.</p>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <div style="width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0;">4</div>
            <p style="font-size:14px;color:var(--dim);line-height:1.6;">Free includes 5 ML signals/day. Upgrade to Pro for unlimited ML scoring when you need it.</p>
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

<span class="cm"># Get ML-scored energy setups entering this week</span>
resp = requests.<span class="fn">get</span>(
    <span class="st">"{portal_urls.API_BASE}/opportunities"</span>,
    params={{
        <span class="st">"market"</span>: <span class="st">"2"</span>,        <span class="cm"># energy</span>
        <span class="st">"direction"</span>: <span class="st">"long"</span>,
        <span class="st">"min_win_rate"</span>: <span class="nu">0.65</span>,
        <span class="st">"limit"</span>: <span class="nu">20</span>
    }},
    headers={{<span class="st">"X-API-Key"</span>: api_key}}
)

<span class="cm"># Score them with ML (Pro tier)</span>
score_resp = requests.<span class="fn">post</span>(
    <span class="st">"{portal_urls.API_BASE}/score"</span>,
    json={{<span class="st">"setups"</span>: resp.json()[<span class="st">"results"</span>]}},
    headers={{<span class="st">"X-API-Key"</span>: api_key}}
)
<span class="cm"># Returns: ml_score, win_prob, pred_return, pred_mfe</span></div>
      </div>
      <div>
        <span class="who">Quants, RIAs, and small funds</span>
        <h2 style="font-size:30px;font-weight:800;margin-bottom:16px;" class="gradient-text-w">
          A programmatic ML signal layer, not another data subscription
        </h2>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:20px;">
          The API delivers ranked seasonal setups and ML scores in JSON. Pipe them into
          your existing backtest framework, portfolio optimizer, or risk model. No
          database to maintain, no ETL, no price-data licensing headache.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          TradeWave covers 15 markets: US large cap, small/mid cap, sector ETFs,
          energy and commodity futures, Forex, international equities, fixed income,
          and crypto. The ML model currently scores six of those markets at the
          symbol level.
        </p>
        <ul class="check-list">
          <li>REST API with JSON responses - no proprietary SDK required</li>
          <li>Signals only - no raw price licensing, no OHLCV compliance burden</li>
          <li class="ml">ML win_prob and pred_return on every tier - free=5/day, dev=100/day, pro=unlimited (6 ML-eligible markets)</li>
          <li>Up to 1,000 results per call on Pro, 5,000 on Business</li>
          <li>300 req/min on Pro - compatible with intraday sweep workflows</li>
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
          Embedding seasonal signals in your app used to mean building a data pipeline,
          licensing historical prices, training your own model, and maintaining all of it.
          With the TradeWave API you call one endpoint and get a ranked, scored, and
          explained output your users can act on.
        </p>
        <p style="font-size:16px;color:var(--dim);line-height:1.8;margin-bottom:24px;">
          The Business tier (1,200 req/min, 250,000 req/day, 50 API keys) is sized for
          multi-tenant products. Enterprise is available for custom rate limits, SLAs,
          and white-label use.
        </p>
        <ul class="check-list">
          <li>No raw price data means no exchange license to negotiate</li>
          <li>MCP-ready: surface TradeWave signals inside any AI-native product</li>
          <li>Multiple API keys per account - one per tenant or environment</li>
          <li>Outputs are percentage returns - safe to display without price context</li>
          <li>Dev tier at $39/mo for prototyping; no commitment to full plan</li>
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
            <p style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px;">AI analyst backed by TradeWave</p>
            <p style="font-size:13px;color:var(--dim);line-height:1.6;">Connect the MCP server to your product's AI layer. Users ask questions, TradeWave tools answer them transparently.</p>
          </div>
        </div>
      </div>
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
        "TradeWave API Use Cases - Traders, Quants, Fintech Builders",
        "Who uses the TradeWave API and MCP server: retail traders using AI assistants, "
        "quants adding ML signals to their models, and fintech builders shipping seasonal-analysis features.",
        no_em_dash(body),
        active_nav="use-cases",
    )


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pages = [
        ("index.html",     build_index,     "Landing / hero"),
        ("pricing.html",   build_pricing,   "Pricing"),
        ("mcp.html",       build_mcp,       "MCP showcase"),
        ("use-cases.html", build_use_cases, "Use cases"),
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
