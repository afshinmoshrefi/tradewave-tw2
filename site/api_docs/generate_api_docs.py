#!/usr/bin/env python3
"""
TradeWave API developer-docs generator.

Reads  /home/flask/api/openapi.yaml   (the frozen REST contract)
Reads  /home/flask/api/MCP_TOOLS.md   (16 MCP tools - 5 flagship + 11 primitives)
Reads  /home/flask/apiserver/tiers.py (tier limits - imported directly)
Writes 7 static HTML files into the same directory as this script:

  quickstart.html    - get a key + first call in 5 minutes
  authentication.html - Bearer auth, key creation/rotation, BYOK for MCP
  api-reference.html  - all 11 endpoints, regenerated from openapi.yaml
  mcp-reference.html  - 16 tools (5 flagship + 11 primitives) + how to connect in Claude Desktop/ChatGPT/Cursor
  data-dictionary.html - every field + all 15 live markets defined in plain English
  rate-limits.html    - per-tier limits, headers, error shape, upgrade stub
  changelog.html      - v1 release notes

Re-run any time openapi.yaml changes to keep the API reference in sync.
No external build step needed - pure stdlib (+ PyYAML, which is in venv-api).

Usage:
    /home/flask/venv/bin/python generate_api_docs.py
    # or from the api_docs dir:
    python3 generate_api_docs.py
"""

from __future__ import annotations

import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Env-driven URL config (resolves per-env: dev/staging/prod)
# ---------------------------------------------------------------------------
sys.path.insert(0, "/home/flask/site/lib")
import portal_urls  # noqa: E402
import portal_seo  # noqa: E402

# Convenient aliases used throughout the generators
API_BASE    = portal_urls.API_BASE      # e.g. https://api-dev.trxstat.com/v1
MCP_URL     = portal_urls.MCP_URL      # e.g. https://mcp-dev.trxstat.com
CONSOLE_URL = portal_urls.CONSOLE_URL  # e.g. https://tw2-dev.trxstat.com/account/api
MAIN_URL    = portal_urls.MAIN_URL     # e.g. https://tw2-dev.trxstat.com

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent          # /home/flask
OPENAPI_YAML = REPO_ROOT / "api" / "openapi.yaml"
MCP_TOOLS_MD = REPO_ROOT / "api" / "MCP_TOOLS.md"
HEADER_PARTIAL = REPO_ROOT / "site" / "templates" / "_tw_header.html"
OUTPUT_DIR = HERE                       # write HTML next to this script

YEAR = datetime.now().year

# ---------------------------------------------------------------------------
# Load source data
# ---------------------------------------------------------------------------

def load_openapi() -> dict:
    with open(OPENAPI_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)

# Tier data is in tiers.py - import it directly so we stay in sync.
sys.path.insert(0, str(REPO_ROOT / "apiserver"))
from tiers import API_TIERS  # noqa: E402

# ---------------------------------------------------------------------------
# Shared layout helpers
# ---------------------------------------------------------------------------

def load_header() -> str:
    """The shared site header, slimmed to a DEVELOPER-PORTAL nav. The raw partial carries the full
    CONSUMER menu (Wave Viewer, Tickers, Scorecard, Insights, Research, News) with root-relative
    URLs that resolve to the WRONG host when served from the dev-portal domain - so for docs/learn/
    playground we both drop the consumer crowd and use ABSOLUTE dev-portal URLs (these pages live
    under /docs, /learn, /playground, so relative links would be wrong). The shared partial and the
    consumer site are untouched. Mirrors api_marketing.generate.page_shell."""
    header = HEADER_PARTIAL.read_text(encoding="utf-8")
    for old, new in (
        ('href="/"',        f'href="{portal_urls.MAIN_URL}"'),
        ('href="/login"',   f'href="{portal_urls.LOGIN_URL}"'),
    ):
        header = header.replace(old, new)
    dev_nav = (
        '<div class="tw-nav-links" id="tw-nav-links">\n'
        f'      <a href="{portal_urls.PORTAL_URL}/">API</a>\n'
        f'      <a href="{portal_urls.DOCS_URL}/quickstart.html">Docs</a>\n'
        f'      <a href="{portal_urls.PORTAL_URL}/pricing.html">Pricing</a>\n'
        f'      <a href="{portal_urls.PORTAL_URL}/mcp.html">MCP</a>\n'
        f'      <a href="{portal_urls.PORTAL_URL}/for-ai-agents.html">For AI agents</a>\n'
        f'      <a href="{portal_urls.LEARN_URL}/">Learn</a>\n'
        f'      <a href="{portal_urls.LOGIN_URL}" id="tw-auth-link">Log In</a>\n'
        f'      <a href="{portal_urls.nav("account/api/keys")}" id="tw-cta-link" class="tw-btn-primary">Get API Key</a>\n'
        '    </div>'
    )
    return re.sub(
        r'<div class="tw-nav-links" id="tw-nav-links">.*?</div>',
        lambda _m: dev_nav, header, count=1, flags=re.DOTALL,
    )


# CSS shared across all doc pages - brand-consistent with the site
PAGE_CSS = """
:root {
  --bg:          #0f0a15;
  --bg-alt:      #15101e;
  --bg-card:     #0c1225;
  --bg-code:     #111827;
  --text:        #e5e7eb;
  --text-dim:    #9ca3af;
  --text-muted:  #6b7280;
  --border:      #1f2937;
  --border-light:#374151;
  --accent:      #6366f1;
  --accent2:     #8b5cf6;
  --accent3:     #a855f7;
  --accent-green:#64dc8c;
  --link:        #a78bfa;
  --link-hover:  #c4b5fd;
  --success:     #10b981;
  --danger:      #ef4444;
  --warning:     #f59e0b;
  --grad:        linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
  --grad-text:   linear-gradient(135deg, #ffffff 0%, #c7d2fe 100%);
}
*{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.7;font-size:16px;
}
a{color:var(--link);text-decoration:none;}
a:hover{color:var(--link-hover);text-decoration:underline;}
code,kbd,samp{
  font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;
  font-size:0.88em;
}

/* ---- layout ---- */
.docs-wrap{display:flex;min-height:100vh;}

.docs-sidebar{
  width:240px;flex-shrink:0;
  background:var(--bg-alt);
  border-right:1px solid var(--border);
  padding:24px 0;
  position:sticky;top:0;height:100vh;overflow-y:auto;
}
.docs-sidebar h2{
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;
  color:var(--text-muted);padding:0 20px;margin:20px 0 8px;
}
.docs-sidebar h2:first-child{margin-top:0;}
.docs-sidebar a{
  display:block;padding:7px 20px;font-size:14px;font-weight:500;
  color:var(--text-dim);text-decoration:none;transition:all 0.15s;
}
.docs-sidebar a:hover,.docs-sidebar a.active{
  color:#fff;background:rgba(99,102,241,0.12);
}
.docs-sidebar .sidebar-divider{
  border:none;border-top:1px solid var(--border);margin:12px 0;
}

.docs-main{flex:1;min-width:0;padding:48px 56px 80px;max-width:900px;}
@media(max-width:960px){.docs-main{padding:32px 24px 60px;}}
@media(max-width:720px){
  .docs-sidebar{display:none;}
  .docs-main{padding:24px 16px 48px;}
}

/* ---- hero ---- */
.docs-hero{
  background:linear-gradient(135deg,rgba(99,102,241,0.15) 0%,rgba(168,85,247,0.10) 100%);
  border-bottom:1px solid var(--border);
  padding:64px 24px 48px;text-align:center;
}
.docs-hero h1{
  font-size:44px;font-weight:800;margin:0 0 14px;
  background:var(--grad);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text;
}
.docs-hero p{margin:0 auto;max-width:640px;color:var(--text-dim);font-size:18px;}
@media(max-width:640px){.docs-hero h1{font-size:30px;}.docs-hero p{font-size:16px;}}

/* ---- typography ---- */
h1{font-size:36px;font-weight:800;margin:0 0 20px;
   background:var(--grad-text);-webkit-background-clip:text;
   -webkit-text-fill-color:transparent;background-clip:text;}
h2{font-size:26px;font-weight:700;color:#fff;margin:48px 0 16px;padding-top:8px;}
h3{font-size:20px;font-weight:700;color:#f3f4f6;margin:32px 0 12px;}
h4{font-size:16px;font-weight:600;color:#e5e7eb;margin:24px 0 8px;}
p{color:var(--text);margin-bottom:16px;line-height:1.75;}
ul,ol{padding-left:22px;margin-bottom:16px;}
li{margin-bottom:8px;color:var(--text);}
strong{color:#fff;}
hr{border:none;border-top:1px solid var(--border);margin:40px 0;}

/* ---- callout boxes ---- */
.callout{
  border-radius:12px;padding:18px 22px;margin:24px 0;
  border-left:4px solid var(--accent);
  background:rgba(99,102,241,0.08);
}
.callout.green{border-color:var(--success);background:rgba(16,185,129,0.08);}
.callout.yellow{border-color:var(--warning);background:rgba(245,158,11,0.08);}
.callout p{margin:0;font-size:15px;}
.callout strong{color:inherit;}

/* ---- code ---- */
pre{
  background:var(--bg-code);border:1px solid var(--border);
  border-radius:10px;padding:20px;overflow-x:auto;margin:16px 0 24px;
  font-size:13.5px;line-height:1.65;
}
pre code{font-size:inherit;color:#e2e8f0;}
.inline-code{
  background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.2);
  border-radius:5px;padding:2px 7px;font-size:0.88em;color:#c7d2fe;
}

/* ---- code tabs ---- */
.code-tabs{margin:16px 0 24px;}
.code-tab-bar{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:0;}
.code-tab-btn{
  padding:8px 18px;font-size:13px;font-weight:600;
  color:var(--text-muted);background:none;border:none;
  border-bottom:2px solid transparent;cursor:pointer;
  font-family:inherit;transition:all 0.15s;
}
.code-tab-btn.active{color:var(--accent);border-bottom-color:var(--accent);}
.code-tab-btn:hover{color:var(--text-dim);}
.code-tab-pane{display:none;}
.code-tab-pane.active{display:block;}

/* ---- endpoint cards ---- */
.endpoint{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:14px;margin:28px 0;overflow:hidden;
}
.endpoint-header{
  display:flex;align-items:center;gap:14px;
  padding:16px 22px;background:rgba(15,10,21,0.6);
  border-bottom:1px solid var(--border);flex-wrap:wrap;
}
.method-badge{
  display:inline-block;padding:3px 10px;border-radius:6px;
  font-size:12px;font-weight:700;font-family:monospace;
  text-transform:uppercase;letter-spacing:0.5px;
}
.method-get{background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);}
.method-post{background:rgba(99,102,241,0.15);color:#818cf8;border:1px solid rgba(99,102,241,0.3);}
.endpoint-path{font-family:monospace;font-size:16px;font-weight:700;color:#e2e8f0;}
.endpoint-summary{font-size:14px;color:var(--text-dim);flex:1;}
.tier-badge{
  display:inline-block;padding:2px 10px;border-radius:100px;
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;
}
.tier-all{background:rgba(16,185,129,0.12);color:var(--success);}
.tier-pro{background:rgba(99,102,241,0.12);color:#818cf8;}
.endpoint-body{padding:22px;}
.endpoint-body p{font-size:15px;color:var(--text-dim);margin-bottom:14px;}
.endpoint-body h4{margin-top:20px;margin-bottom:10px;font-size:14px;
  text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);font-weight:600;}

/* ---- param / field tables ---- */
table{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0 20px;}
thead th{
  background:rgba(15,10,21,0.7);padding:10px 14px;text-align:left;
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;
  color:var(--text-muted);border-bottom:1px solid var(--border);
}
tbody td{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top;}
tbody tr:last-child td{border-bottom:none;}
.field-name{font-family:monospace;color:#c7d2fe;font-size:13.5px;}
.field-type{font-family:monospace;color:var(--text-muted);font-size:12px;}
.required-badge{
  display:inline-block;font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:0.5px;
  color:#ef4444;background:rgba(239,68,68,0.1);
  border:1px solid rgba(239,68,68,0.2);border-radius:4px;
  padding:1px 5px;margin-left:4px;
}

/* ---- response example ---- */
.response-ex{
  background:var(--bg-code);border:1px solid var(--border-light);
  border-radius:8px;padding:16px 20px;font-size:13px;
  line-height:1.6;overflow-x:auto;margin:12px 0 0;
}

/* ---- tool cards ---- */
.tool-card{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:14px;margin:20px 0;overflow:hidden;
}
.tool-card-header{
  display:flex;align-items:center;gap:14px;
  padding:14px 20px;background:rgba(15,10,21,0.5);
  border-bottom:1px solid var(--border);
}
.tool-name{font-family:monospace;font-size:15px;font-weight:700;color:#c7d2fe;}
.tool-card-body{padding:18px 20px;font-size:14px;color:var(--text-dim);}
.tool-card-body p{margin-bottom:10px;font-size:14px;}
.tool-card-body ul{margin-bottom:0;}

/* ---- tier table ---- */
.tier-table-wrap{overflow-x:auto;margin:16px 0 24px;}
.tier-table{width:100%;border-collapse:collapse;font-size:14px;}
.tier-table th{
  background:rgba(15,10,21,0.7);padding:12px 16px;text-align:left;
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;
  color:var(--text-muted);border-bottom:1px solid var(--border);
}
.tier-table td{padding:12px 16px;border-bottom:1px solid var(--border);}
.tier-table tbody tr:last-child td{border-bottom:none;}
.tier-name{font-weight:700;color:#fff;}
.price-col{color:var(--accent-green);font-weight:700;}
.check{color:var(--success);font-weight:700;}
.cross{color:var(--danger);}

/* ---- changelog ---- */
.changelog-entry{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:12px;padding:24px 28px;margin:20px 0;
}
.changelog-version{
  display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap;
}
.version-badge{
  background:var(--grad);color:#fff;padding:4px 14px;
  border-radius:100px;font-size:13px;font-weight:700;
}
.version-date{font-size:14px;color:var(--text-muted);}
.version-status{
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;
  padding:2px 10px;border-radius:100px;
  background:rgba(16,185,129,0.12);color:var(--success);
}

/* ---- footer ---- */
.docs-footer{
  border-top:1px solid var(--border);background:var(--bg-alt);
  padding:32px 24px;text-align:center;color:var(--text-muted);font-size:13px;
}
.docs-footer nav{margin-bottom:14px;}
.docs-footer nav a{color:var(--text-dim);margin:0 10px;font-size:14px;}
.docs-footer nav a:hover{color:#fff;}
.docs-footer .disclaimer{
  max-width:800px;margin:14px auto 0;font-size:11px;line-height:1.7;opacity:0.65;
}
"""

LEGAL_DISCLAIMER = (
    "TradeWave is a research platform. It is not a brokerage and does not "
    "execute trades. All data is based on historical analysis and is provided "
    "for informational and educational purposes only. Past performance does "
    "not guarantee future results."
)

NAV_LINKS = [
    ("Quickstart",       "quickstart.html"),
    ("Authentication",   "authentication.html"),
    ("API Reference",    "api-reference.html"),
    ("MCP Reference",    "mcp-reference.html"),
    ("Data Dictionary",  "data-dictionary.html"),
    ("Rate Limits",      "rate-limits.html"),
    ("Changelog",        "changelog.html"),
]


def sidebar_html(active: str) -> str:
    links = "\n".join(
        f'<a href="{href}" {"class=\"active\"" if href == active else ""}>{label}</a>'
        for label, href in NAV_LINKS
    )
    api_host_label = API_BASE.replace("https://", "").replace("http://", "")
    return f"""
<nav class="docs-sidebar" aria-label="Docs navigation">
  <h2>Developer Docs</h2>
  {links}
  <hr class="sidebar-divider">
  <h2>Try &amp; build</h2>
  <a href="{portal_urls.PLAYGROUND_URL}">API Playground</a>
  <a href="{portal_urls.LEARN_URL}">Learning track</a>
  <a href="{portal_urls.MCP_SETUP_URL}">MCP setup</a>
  <hr class="sidebar-divider">
  <h2>API</h2>
  <a href="{API_BASE}">{api_host_label}</a>
  <a href="openapi.yaml">OpenAPI spec (YAML)</a>
  <a href="tradewave.postman_collection.json">Postman collection</a>
</nav>"""


def footer_html() -> str:
    return f"""
<footer class="docs-footer">
  <nav>
    <a href="{portal_urls.nav('/')}">Home</a>
    <a href="{portal_urls.nav('/pricing')}">Pricing</a>
    <a href="{portal_urls.nav('/app/')}">Wave Viewer</a>
    <a href="{portal_urls.nav('/contact.html')}">Contact</a>
    <a href="{portal_urls.nav('/privacy.html')}">Privacy</a>
    <a href="{portal_urls.nav('/terms.html')}">Terms</a>
    <a href="{portal_urls.nav('/disclaimer.html')}">Disclaimer</a>
  </nav>
  <p>&copy; {YEAR} Tara Data Research LLC. All rights reserved.</p>
  <p class="disclaimer">{LEGAL_DISCLAIMER}</p>
</footer>"""


def page(title: str, description: str, active_href: str, hero_title: str,
         hero_sub: str, body: str, extra_head: str = "") -> str:
    header = load_header()
    sb = sidebar_html(active_href)
    ft = footer_html()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - TradeWave Developer Docs</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index, follow">
  {portal_seo.head_tags(portal_urls.DOCS_URL + '/' + (active_href if active_href.endswith('.html') else 'quickstart.html'), title, description)}
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
  <style>{PAGE_CSS}</style>
  {extra_head}
</head>
<body>
{header}
<div class="docs-hero">
  <h1>{hero_title}</h1>
  <p>{hero_sub}</p>
</div>
<div class="docs-wrap">
  {sb}
  <main class="docs-main" id="main-content">
{body}
  </main>
</div>
{ft}
<script>
// Simple code-tab switcher
document.addEventListener('DOMContentLoaded', function() {{
  document.querySelectorAll('.code-tabs').forEach(function(tabs) {{
    var btns = tabs.querySelectorAll('.code-tab-btn');
    var panes = tabs.querySelectorAll('.code-tab-pane');
    btns.forEach(function(btn, i) {{
      btn.addEventListener('click', function() {{
        btns.forEach(function(b) {{ b.classList.remove('active'); }});
        panes.forEach(function(p) {{ p.classList.remove('active'); }});
        btn.classList.add('active');
        panes[i].classList.add('active');
      }});
    }});
  }});
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 1. Quickstart
# ---------------------------------------------------------------------------

def build_quickstart() -> str:
    body = f"""
<h1>Quickstart</h1>
<p>Get your API key and make your first call in under 5 minutes.</p>

<div class="callout green">
  <p><strong>Free tier included.</strong> Create an account and get a free API key instantly - no credit card required. The free tier gives you S&amp;P 500 stocks with a limit of 3 results per call.</p>
</div>

<h2>Step 1 - Create an account and get a key</h2>
<ol>
  <li>Sign up or log in at <a href="{CONSOLE_URL}">Account &rarr; API Keys</a>.</li>
  <li>Navigate to <strong>Account &rarr; API Keys</strong> in the dashboard.</li>
  <li>Click <strong>Create Key</strong>. Copy the key immediately - it is shown only once.</li>
</ol>

<p>Keys look like <code class="inline-code">tw_live_abc123...</code>. Keep them secret - treat them like passwords.</p>

<h2>Step 2 - Make your first call</h2>

<p>The base URL for all API calls is:</p>
<pre><code>{API_BASE}</code></pre>

<p>Every request needs the key in the <code class="inline-code">Authorization</code> header:</p>
<pre><code>Authorization: Bearer &lt;your-api-key&gt;</code></pre>

<h3>Get today's daily AI pick</h3>
<div class="code-tabs">
  <div class="code-tab-bar">
    <button class="code-tab-btn active">curl</button>
    <button class="code-tab-btn">Python</button>
    <button class="code-tab-btn">JavaScript</button>
  </div>
  <div class="code-tab-pane active">
<pre><code>curl {API_BASE}/daily-pick \\
  -H "Authorization: Bearer &lt;your-api-key&gt;"</code></pre>
  </div>
  <div class="code-tab-pane">
<pre><code>import urllib.request, json

KEY = "&lt;your-api-key&gt;"
req = urllib.request.Request(
    "{API_BASE}/daily-pick",
    headers={{"Authorization": f"Bearer {{KEY}}"}},
)
with urllib.request.urlopen(req) as r:
    pick = json.loads(r.read())

print(pick["symbol"], pick["direction"], pick["days_out"], "days")</code></pre>
  </div>
  <div class="code-tab-pane">
<pre><code>const KEY = "&lt;your-api-key&gt;";

const res = await fetch("{API_BASE}/daily-pick", {{
  headers: {{ Authorization: `Bearer ${{KEY}}` }},
}});
const pick = await res.json();
console.log(pick.symbol, pick.direction, pick.days_out + " days");</code></pre>
  </div>
</div>

<h3>List top seasonal opportunities (S&amp;P 500, market id "2")</h3>
<div class="code-tabs">
  <div class="code-tab-bar">
    <button class="code-tab-btn active">curl</button>
    <button class="code-tab-btn">Python</button>
    <button class="code-tab-btn">JavaScript</button>
  </div>
  <div class="code-tab-pane active">
<pre><code>curl "{API_BASE}/opportunities?market=2&amp;limit=5" \\
  -H "Authorization: Bearer &lt;your-api-key&gt;"</code></pre>
  </div>
  <div class="code-tab-pane">
<pre><code>import urllib.request, json, urllib.parse

KEY = "&lt;your-api-key&gt;"
params = urllib.parse.urlencode({{"market": "2", "limit": 5}})
req = urllib.request.Request(
    f"{API_BASE}/opportunities?{{params}}",
    headers={{"Authorization": f"Bearer {{KEY}}"}},
)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read())

for opp in data["opportunities"]:
    print(opp["symbol"], opp["direction"], f"{{opp['avg_profit_pct']:.1f}}%")</code></pre>
  </div>
  <div class="code-tab-pane">
<pre><code>const KEY = "&lt;your-api-key&gt;";

const res = await fetch(
  "{API_BASE}/opportunities?market=2&limit=5",
  {{ headers: {{ Authorization: `Bearer ${{KEY}}` }} }}
);
const {{ opportunities }} = await res.json();
opportunities.forEach(o =>
  console.log(o.symbol, o.direction, o.avg_profit_pct.toFixed(1) + "%")
);</code></pre>
  </div>
</div>

<h3>Example response</h3>
<pre class="response-ex"><code>{{
  "opportunities": [
    {{
      "symbol":           "AAPL",
      "market":           "2",
      "direction":        "long",
      "entry_date":       "2026-06-01",
      "days_out":         22,
      "sharpe_ratio":     1.84,
      "avg_profit_pct":   3.12,
      "median_profit_pct":2.88,
      "win_rate":         0.78,
      "years":            "10",
      "ml":               null
    }}
  ]
}}</code></pre>

<h2>Next steps</h2>
<ul>
  <li><a href="authentication.html">Authentication</a> - key creation, rotation, BYOK for MCP.</li>
  <li><a href="api-reference.html">API Reference</a> - all 11 endpoints with full parameter and schema details.</li>
  <li><a href="mcp-reference.html">MCP Reference</a> - connect TradeWave directly to Claude, ChatGPT, or Cursor.</li>
  <li><a href="data-dictionary.html">Data Dictionary</a> - plain-English definitions of every field.</li>
</ul>
"""
    return page(
        title="Quickstart",
        description="Get a TradeWave API key and make your first call in 5 minutes.",
        active_href="quickstart.html",
        hero_title="Quickstart",
        hero_sub="Get a key and make your first call in under 5 minutes.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 2. Authentication
# ---------------------------------------------------------------------------

def build_authentication() -> str:
    body = f"""
<h1>Authentication</h1>
<p>All requests to the TradeWave API must be authenticated with an API key.</p>

<h2>Bearer token scheme</h2>
<p>Pass your key in the <code class="inline-code">Authorization</code> header on every request:</p>
<pre><code>Authorization: Bearer &lt;your-api-key&gt;</code></pre>

<p>There is no session, no cookie, and no OAuth flow for the REST API. Every request is independently authenticated against the key's HMAC hash stored in the database. The key itself is never stored in plaintext.</p>

<div class="callout yellow">
  <p><strong>Keep keys secret.</strong> Do not embed them in client-side JavaScript, commit them to source control, or pass them in URL query parameters. Use environment variables or a secrets manager.</p>
</div>

<h2>Key management in the console</h2>
<ol>
  <li>Go to <a href="{CONSOLE_URL}">Account &rarr; API Keys</a> in the dashboard.</li>
  <li>Go to <strong>Account &rarr; API Keys</strong>.</li>
  <li><strong>Create</strong> - generates a new key. Copy it immediately; it is displayed only at creation time.</li>
  <li><strong>Rotate</strong> - generates a new secret for the same key slot and invalidates the old one. Useful when you suspect a key has been exposed.</li>
  <li><strong>Revoke</strong> - permanently deletes a key. Requests using it will get <code class="inline-code">401</code>.</li>
</ol>

<h3>Key limits by tier</h3>
<div class="tier-table-wrap">
<table class="tier-table">
  <thead>
    <tr>
      <th>Tier</th>
      <th>Max keys</th>
    </tr>
  </thead>
  <tbody>
    <tr><td class="tier-name">Free</td><td>1</td></tr>
    <tr><td class="tier-name">Dev</td><td>3</td></tr>
    <tr><td class="tier-name">Pro</td><td>10</td></tr>
    <tr><td class="tier-name">Business</td><td>50</td></tr>
  </tbody>
</table>
</div>

<h2>BYOK for MCP (Bring Your Own Key)</h2>
<p>The TradeWave MCP server uses the same API keys. There is no separate credential system. TradeWave's MCP is a hosted HTTP server at <code class="inline-code">https://mcp.tradewave.ai/mcp</code>. HTTP-native clients (ChatGPT and others) point straight at that URL and send your TradeWave API key as a Bearer token. Stdio-only clients (Claude Desktop, Cursor) bridge to it with the <code class="inline-code">mcp-remote</code> npx shim, passing the key in the <code class="inline-code">Authorization</code> header.</p>

<pre><code># HTTP-native client: send the key as a Bearer token
Authorization: Bearer tw_live_abc123...

# Stdio client (Claude Desktop / Cursor): bridge with the mcp-remote shim
npx -y mcp-remote https://mcp.tradewave.ai/mcp \\
  --header "Authorization: Bearer tw_live_abc123..."</code></pre>

<p>Tier and entitlements (market scope, ML access, rate limits) are read directly from the key - no additional configuration is needed. See <a href="mcp-reference.html">MCP Reference</a> for full connection instructions.</p>

<h2>Error responses</h2>
<p>Authentication errors return standard HTTP status codes:</p>

<div class="tier-table-wrap">
<table class="tier-table">
  <thead>
    <tr><th>Status</th><th>Code</th><th>Meaning</th></tr>
  </thead>
  <tbody>
    <tr><td>401</td><td><code class="inline-code">unauthorized</code></td><td>Missing or invalid key</td></tr>
    <tr><td>403</td><td><code class="inline-code">forbidden</code></td><td>Key is valid but the resource requires a higher tier</td></tr>
  </tbody>
</table>
</div>

<p>Error body shape:</p>
<pre><code>{{
  "error": {{
    "code":    "unauthorized",
    "message": "API key missing or invalid."
  }}
}}</code></pre>
"""
    return page(
        title="Authentication",
        description="How TradeWave API key authentication works - Bearer tokens, key rotation, and BYOK for MCP.",
        active_href="authentication.html",
        hero_title="Authentication",
        hero_sub="Bearer tokens, key management, and BYOK for MCP.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 3. API Reference (generated from openapi.yaml)
# ---------------------------------------------------------------------------

def _param_rows(params: list, spec: dict) -> str:
    """Render a parameter list as table rows, resolving $ref if needed."""
    rows = []
    for p in params:
        if "$ref" in p:
            # $ref like "#/components/parameters/MarketId" - walk from spec root
            ref_path = p["$ref"].lstrip("#/").split("/")
            obj = spec
            for seg in ref_path:
                obj = obj[seg]
            p = obj
        name = p.get("name", "")
        location = p.get("in", "")
        required = p.get("required", False)
        schema = p.get("schema", {})
        ptype = schema.get("type", "string")
        if "enum" in schema:
            ptype += " (" + " | ".join(f'"{v}"' for v in schema["enum"]) + ")"
        if "default" in schema:
            ptype += f", default {schema['default']}"
        description = p.get("description", "")
        req_badge = '<span class="required-badge">required</span>' if required else ""
        rows.append(
            f"<tr>"
            f"<td><span class='field-name'>{name}</span>{req_badge}</td>"
            f"<td><span class='field-type'>{location}</span></td>"
            f"<td><span class='field-type'>{ptype}</span></td>"
            f"<td>{description}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _schema_rows(schema_ref: str, spec: dict, depth: int = 0) -> str:
    """Render schema properties as table rows (1 level deep)."""
    if not schema_ref:
        return ""
    components = spec.get("components", {}).get("schemas", {})
    # Resolve $ref
    if isinstance(schema_ref, str) and schema_ref.startswith("#/components/schemas/"):
        name = schema_ref.split("/")[-1]
        schema = components.get(name, {})
    elif isinstance(schema_ref, dict):
        schema = schema_ref
    else:
        return ""

    props = schema.get("properties", {})
    if not props:
        return ""

    rows = []
    for field, fdef in props.items():
        ftype = fdef.get("type", "")
        if "$ref" in fdef:
            ref_name = fdef["$ref"].split("/")[-1]
            ftype = f"object ({ref_name})"
        if "enum" in fdef:
            ftype += " (" + " | ".join(f'"{v}"' for v in fdef["enum"]) + ")"
        desc = fdef.get("description", "")
        rows.append(
            f"<tr>"
            f"<td><span class='field-name'>{field}</span></td>"
            f"<td><span class='field-type'>{ftype}</span></td>"
            f"<td>{desc}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


METHOD_COLORS = {"get": "method-get", "post": "method-post"}


EXAMPLE_RESPONSES: dict[str, str] = {
    "GET /markets": """{
  "markets": [
    {"id": "0",  "name": "DOW 30 STOCKS",      "ml_eligible": true,  "in_scope": true},
    {"id": "2",  "name": "S&P 500 STOCKS",     "ml_eligible": true,  "in_scope": true},
    {"id": "16", "name": "CRYPTO CURRENCIES",   "ml_eligible": false, "in_scope": true}
  ]
}""",
    "GET /markets/{market_id}/symbols": """{
  "symbols": [
    {"symbol": "AAPL", "name": "Apple Inc"},
    {"symbol": "MSFT", "name": "Microsoft Corp"}
  ]
}""",
    "GET /opportunities": """{
  "entry_date": "2026-05-31",
  "window_supported": false,
  "evaluated_count": 50,
  "enrichment_capped": true,
  "opportunities": [
    {
      "symbol": "DOV",    "market": "2",
      "direction": "long","entry_date": "2026-06-01",
      "days_out": 246,    "sharpe_ratio": 3.31,
      "avg_profit_pct": 18.49, "median_profit_pct": 18.4,
      "win_rate": 1.0,    "years": "10",
      "ml": null
    },
    {
      "symbol": "NDSN",   "market": "2",
      "direction": "long","entry_date": "2026-05-31",
      "days_out": 82,     "sharpe_ratio": 2.66,
      "avg_profit_pct": 5.68, "median_profit_pct": 6.04,
      "win_rate": 1.0,    "years": "10",
      "ml": {"ml_score": 29.0, "win_prob": 0.6665,
             "pred_return": 2.2999, "pred_mfe": 8.5967}
    }
  ]
}""",
    "GET /opportunities/{symbol}": """{
  "opportunities": [
    {
      "symbol": "AAPL",  "market": "2",
      "direction": "long","entry_date": "2026-06-01",
      "days_out": 22,     "sharpe_ratio": 1.84,
      "avg_profit_pct":  3.12, "median_profit_pct": 2.88,
      "win_rate": 0.78,  "years": "10",
      "ml": null
    }
  ]
}""",
    "GET /patterns/{market_id}/{symbol}": """{
  "symbol": "AAPL", "market": "2",
  "stats": {
    "avg_profit_pct": 3.12, "median_profit_pct": 2.88,
    "win_rate": 0.78,       "sharpe_ratio": 1.84,
    "sample_size": 18
  }
}""",
    "GET /seasonal-chart": """{
  "symbol": "AAPL",  "market": "2",
  "direction": "long","entry_date": "2026-06-01",
  "days_out": 22,    "years": "10",
  "seasonal_curve": [
    {"date": "2026-06-01", "index": 41.2},
    {"date": "2026-06-02", "index": 42.8},
    {"date": "2026-06-23", "index": 58.6}
  ],
  "stats": {"avg_profit_pct": 3.12, "win_rate": 0.78},
  "win_rate": 0.78, "years": "10"
}""",
    "POST /score": """{
  "granted": 1,
  "ml_remaining_today": null,
  "scores": [
    {
      "symbol": "AAPL",
      "date": "2026-06-01",
      "direction": "long",
      "days_out": 20,
      "ml_score": 95.1,
      "win_prob": 0.8452,
      "pred_return": 4.0913,
      "pred_mfe": 7.4427
    }
  ]
}""",
    "GET /scan": """{
  "generated_at": "2026-05-31T18:30:13",
  "window": "now",
  "rank_by": "sharpe",
  "count": 3,
  "evaluated_count": 334,
  "enrichment_capped": true,
  "ml_remaining_today": null,
  "opportunities": [
    {
      "rank": 1,
      "symbol": "DOV",
      "market": {"id": "2", "name": "S&P 500 STOCKS"},
      "direction": "long",
      "signal": "BUY",
      "setup": {"entry_date": "2026-06-01",
                "entry_window": "2026-05-29 to 2026-06-04",
                "hold_days": 246, "exit_date": "2027-02-02"},
      "edge_score": 97,
      "edge_basis": "win_rate 1.00 x sharpe 3.3 x 10y history",
      "stats": {"historical_win_rate": 1.0, "sharpe_ratio": 3.31,
                "avg_return_pct": 18.49, "median_return_pct": 18.4, "years": "10"},
      "ml": null,
      "receipts": {
        "years_tested": 10, "wins": 10, "losses": 0,
        "historical_win_rate": 1.0, "avg_return_pct": 18.49, "median_return_pct": 18.4,
        "best_year": {"year": "2019", "return_pct": 25.8},
        "worst_year": {"year": "2024", "return_pct": 12.17},
        "per_year": [{"year": "2025", "return_pct": 18.41, "result": "win"}],
        "curve_summary": {"shape": "strengthens through the hold; seasonal index rising",
                          "trend": "rising", "change_pts": 8.4,
                          "peak_day": 240, "trough_day": 0},
        "source": "TradeWave seasonal model, 10y lookback", "as_of": "2026-05-31"
      },
      "next_step": {
        "headline": "To act on this, here is a ready-to-place ticket:",
        "order_ticket": {"side": "BUY", "symbol": "DOV", "type": "MARKET",
                         "time_in_force": "DAY", "suggested_entry_date": "2026-06-01",
                         "suggested_exit_date": "2027-02-02",
                         "note": "Seasonal hold ~246 calendar days. Size to your own risk."},
        "copy_text": "BUY DOV market, day order; plan exit ~2027-02-02 (246d seasonal hold).",
        "set_reminder": {"type": "seasonal_entry", "fire_on": "2026-05-31",
                         "message": "DOV seasonal window opens tomorrow."},
        "framing": "TradeWave gives the edge and the timing; you place the trade at your own broker."
      },
      "headline": "DOV long - enter ~Jun 1, hold 246d. Won 10/10 years, avg +18.5%, Sharpe 3.3.",
      "verdict": "Strong, consistent seasonal long.",
      "disclaimer": "Educational seasonal + ML signal, not personalized investment advice and not a recommendation to buy or sell. Past performance is not indicative of future results.",
      "tier_notes": "ML score shown (Pro)."
    }
  ]
}""",
    "GET /analyze/{symbol}": """{
  "card": {
    "rank": 1,
    "symbol": "AAPL",
    "market": {"id": "2", "name": "S&P 500 STOCKS"},
    "direction": "long",
    "signal": "BUY",
    "setup": {"entry_date": "2026-06-25", "entry_window": "2026-06-22 to 2026-06-28",
              "hold_days": 24, "exit_date": "2026-07-19"},
    "edge_score": 91,
    "edge_basis": "win_rate 1.00 x sharpe 3.4 x ml_win_prob 0.71 x 10y history",
    "stats": {"historical_win_rate": 1.0, "sharpe_ratio": 3.42,
              "avg_return_pct": 6.05, "median_return_pct": 6.01, "years": "10"},
    "ml": {"ml_score": 59.5, "ml_win_prob": 0.7087,
           "pred_return_pct": 1.3736, "pred_mfe_pct": 5.8771},
    "receipts": {
      "years_tested": 10, "wins": 10, "losses": 0,
      "historical_win_rate": 1.0, "avg_return_pct": 6.05, "median_return_pct": 6.01,
      "best_year": {"year": "2016", "return_pct": 8.51},
      "worst_year": {"year": "2017", "return_pct": 3.57},
      "per_year": [{"year": "2025", "return_pct": 5.42, "result": "win"}],
      "curve_summary": {"shape": "strengthens into the exit; seasonal index rising +13 pts over the hold",
                        "trend": "rising", "change_pts": 13.1,
                        "peak_day": 20, "trough_day": 0},
      "source": "TradeWave seasonal model, 10y lookback", "as_of": "2026-05-31"
    },
    "next_step": {
      "headline": "To act on this, here is a ready-to-place ticket:",
      "order_ticket": {"side": "BUY", "symbol": "AAPL", "type": "MARKET",
                       "time_in_force": "DAY", "suggested_entry_date": "2026-06-25",
                       "suggested_exit_date": "2026-07-19",
                       "note": "Seasonal hold ~24 calendar days. Size to your own risk."},
      "copy_text": "BUY AAPL market, day order; plan exit ~2026-07-19 (24d seasonal hold).",
      "set_reminder": {"type": "seasonal_entry", "fire_on": "2026-06-24",
                       "message": "AAPL seasonal window opens tomorrow."},
      "framing": "TradeWave gives the edge and the timing; you place the trade at your own broker."
    },
    "headline": "AAPL long - enter ~Jun 25, hold 24d. Won 10/10 years, avg +6.0%, Sharpe 3.4.",
    "verdict": "Strong, consistent seasonal long. Seasonal shape: builds through the window (peak ~day 363), rises overall.",
    "disclaimer": "Educational seasonal + ML signal, not personalized investment advice and not a recommendation to buy or sell. Past performance is not indicative of future results.",
    "tier_notes": "ML score shown (Pro)."
  },
  "other_setups": [
    {"symbol": "AAPL", "direction": "long", "entry_date": "2026-06-24",
     "hold_days": 28, "historical_win_rate": 1.0, "sharpe_ratio": 2.95,
     "avg_return_pct": 6.5, "median_return_pct": 6.34, "years": "10"}
  ],
  "as_of": "2026-05-31"
}""",
    "GET /daily-pick": """{
  "card": {
    "rank": 1,
    "symbol": "NVDA",
    "market": {"id": "2", "name": "S&P 500 STOCKS"},
    "direction": "long",
    "signal": "BUY",
    "setup": {"entry_date": "2026-05-08", "entry_window": "2026-05-05 to 2026-05-11",
              "hold_days": 30, "exit_date": "2026-06-07"},
    "edge_score": 85,
    "edge_basis": "win_rate 0.82 x sharpe 2.8 x ml_win_prob 0.85 x 11y history",
    "stats": {"historical_win_rate": 0.82, "sharpe_ratio": 2.84,
              "avg_return_pct": 23.79, "median_return_pct": 23.51, "years": "10"},
    "ml": {"ml_score": 95.6, "ml_win_prob": 0.8452,
           "pred_return_pct": 6.8239, "pred_mfe_pct": 14.4871},
    "receipts": {
      "years_tested": 11, "wins": 9, "losses": 2,
      "historical_win_rate": 0.82, "avg_return_pct": 23.79, "median_return_pct": 23.51,
      "best_year": {"year": "2017", "return_pct": 45.25},
      "worst_year": {"year": "2019", "return_pct": -16.24},
      "per_year": [{"year": "2019", "return_pct": -16.24, "result": "loss"}],
      "curve_summary": {"shape": "builds through the window (peak ~day 364), rises overall",
                        "peak_day": 364, "trough_day": 0},
      "source": "TradeWave seasonal model, 10y lookback", "as_of": "2026-05-31",
      "live_track_record": {"count": 10, "win_count": 7, "win_rate": 0.7,
                            "avg_return_pct": 6.69,
                            "note": "Live forward-tested record of past daily picks (made in advance, scored later)."}
    },
    "next_step": {
      "headline": "To act on this, here is a ready-to-place ticket:",
      "order_ticket": {"side": "BUY", "symbol": "NVDA", "type": "MARKET",
                       "time_in_force": "DAY", "suggested_entry_date": "2026-05-08",
                       "suggested_exit_date": "2026-06-07",
                       "note": "Seasonal hold ~30 calendar days. Size to your own risk."},
      "copy_text": "BUY NVDA market, day order; plan exit ~2026-06-07 (30d seasonal hold).",
      "set_reminder": {"type": "seasonal_entry", "fire_on": "2026-05-07",
                       "message": "NVDA seasonal window opens tomorrow."},
      "framing": "TradeWave gives the edge and the timing; you place the trade at your own broker."
    },
    "headline": "NVDA long - enter ~May 8, hold 30d. Won 9/11 years, avg +23.8%, Sharpe 2.8.",
    "verdict": "Strong, consistent seasonal long. Seasonal shape: builds through the window (peak ~day 364), rises overall.",
    "disclaimer": "Educational seasonal + ML signal, not personalized investment advice and not a recommendation to buy or sell. Past performance is not indicative of future results.",
    "tier_notes": "ML score shown (Pro)."
  },
  "featured_date": "2026-05-08",
  "track_record": {"count": 10, "win_count": 7, "win_rate": 0.7,
                   "avg_return_pct": 6.69,
                   "note": "Live forward-tested record of past daily picks (made in advance, scored later)."},
  "as_of": "2026-05-31"
}""",
    "GET /daily-pick/track-record": """{
  "summary": {
    "count": 312, "win_count": 249,
    "win_rate": 0.798, "avg_return_pct": 3.1
  },
  "picks": [
    {"symbol": "NVDA", "featured_date": "2026-05-27",
     "return_pct": null, "result": "open"},
    {"symbol": "AAPL", "featured_date": "2026-05-06",
     "return_pct": 4.5,  "result": "win"}
  ]
}""",
}


def build_api_reference() -> str:
    spec = load_openapi()
    paths = spec.get("paths", {})
    components = spec.get("components", {})

    endpoint_html = []

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue

            summary = operation.get("summary", "")
            description = operation.get("description", "")
            params = operation.get("parameters", [])
            tags = operation.get("tags", [])
            key = f"{method.upper()} {path}"
            example = EXAMPLE_RESPONSES.get(key, "")
            is_pro = "scoring" in tags

            # Determine request body schema ref
            req_body = operation.get("requestBody", {})
            req_schema_ref = ""
            if req_body:
                content = req_body.get("content", {})
                for ct, ct_val in content.items():
                    s = ct_val.get("schema", {})
                    if "$ref" in s:
                        req_schema_ref = s["$ref"].split("/")[-1]
                    break

            # Determine response schema ref
            resp_schema_ref = ""
            responses = operation.get("responses", {})
            ok = responses.get("200", {})
            ok_content = ok.get("content", {})
            for ct, ct_val in ok_content.items():
                s = ct_val.get("schema", {})
                if "$ref" in s:
                    resp_schema_ref = s["$ref"].split("/")[-1]
                elif "properties" in s:
                    for prop, pdef in s.get("properties", {}).items():
                        if "items" in pdef and "$ref" in pdef["items"]:
                            resp_schema_ref = pdef["items"]["$ref"].split("/")[-1]
                            break
                break

            tier_badge = (
                '<span class="tier-badge tier-pro">Pro</span>'
                if is_pro else
                '<span class="tier-badge tier-all">All tiers</span>'
            )

            params_section = ""
            if params:
                param_rows = _param_rows(params, spec)
                params_section = f"""
<h4>Parameters</h4>
<table>
  <thead><tr><th>Name</th><th>In</th><th>Type</th><th>Description</th></tr></thead>
  <tbody>
    {param_rows}
  </tbody>
</table>"""

            req_body_section = ""
            if req_schema_ref:
                schema_obj = components.get("schemas", {}).get(req_schema_ref, {})
                props = schema_obj.get("properties", {})
                items_schema = None
                if "opportunities" in props:
                    arr_items = props["opportunities"].get("items", {})
                    items_schema = arr_items
                if items_schema:
                    item_props = items_schema.get("properties", {})
                    item_required = items_schema.get("required", [])
                    rows = []
                    for fn, fd in item_props.items():
                        ftype = fd.get("type", "")
                        if "enum" in fd:
                            ftype += " (" + " | ".join(f'"{v}"' for v in fd["enum"]) + ")"
                        req = '<span class="required-badge">required</span>' if fn in item_required else ""
                        rows.append(
                            f"<tr><td><span class='field-name'>{fn}</span>{req}</td>"
                            f"<td><span class='field-type'>{ftype}</span></td>"
                            f"<td></td></tr>"
                        )
                    req_body_section = f"""
<h4>Request body - array of opportunity identifiers</h4>
<table>
  <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>"""

            resp_section = ""
            if resp_schema_ref:
                schema_rows = _schema_rows(f"#/components/schemas/{resp_schema_ref}", spec)
                if schema_rows:
                    resp_section = f"""
<h4>Response fields ({resp_schema_ref})</h4>
<table>
  <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
  <tbody>
    {schema_rows}
  </tbody>
</table>"""

            example_section = ""
            if example:
                example_section = f"""
<h4>Example response</h4>
<pre class="response-ex"><code>{example}</code></pre>"""

            desc_p = f"<p>{description.strip()}</p>" if description.strip() else ""

            endpoint_html.append(f"""
<div class="endpoint" id="{method}-{path.strip('/').replace('/', '-').replace('{', '').replace('}', '')}">
  <div class="endpoint-header">
    <span class="method-badge {METHOD_COLORS.get(method, '')}">{method.upper()}</span>
    <span class="endpoint-path">/v1{path}</span>
    <span class="endpoint-summary">{summary}</span>
    {tier_badge}
  </div>
  <div class="endpoint-body">
    {desc_p}
    {params_section}
    {req_body_section}
    {resp_section}
    {example_section}
  </div>
</div>""")

    endpoints_block = "\n".join(endpoint_html)

    body = f"""
<h1>API Reference</h1>
<p>All endpoints are under <code class="inline-code">{API_BASE}</code>. Every request requires <code class="inline-code">Authorization: Bearer &lt;key&gt;</code>.</p>

<div class="callout">
  <p><strong>Signals only.</strong> All returns are expressed as percentages. Raw OHLCV data and price levels are never returned. ML is available on every tier, metered per day (free 5/day, unlimited on Pro/Business).</p>
</div>

<div class="callout green">
  <p><strong>This page is generated from <code>/api/openapi.yaml</code>.</strong> Re-run <code>generate_api_docs.py</code> after any contract change to keep it in sync.</p>
</div>

<h2>Base URL</h2>
<pre><code>{API_BASE}</code></pre>

<h2>Authentication</h2>
<pre><code>Authorization: Bearer &lt;your-api-key&gt;</code></pre>

<h2>Endpoints</h2>
{endpoints_block}

<hr>

<h2 id="openapi">OpenAPI spec</h2>
<p>The machine-readable contract lives at <code class="inline-code">/api/openapi.yaml</code> in the repository. You can point any OpenAPI-compatible tool (Redoc, Swagger UI, Insomnia, Postman) at it.</p>

<h2>Error shape</h2>
<p>All errors follow the same envelope:</p>
<pre><code>{{
  "error": {{
    "code":    "rate_limited",
    "message": "You have exceeded 10 requests per minute."
  }}
}}</code></pre>

<p>See <a href="rate-limits.html">Rate Limits &amp; Errors</a> for the full list of codes.</p>
"""
    return page(
        title="API Reference",
        description="Complete reference for all 11 TradeWave API v1 endpoints - parameters, schemas, and example responses.",
        active_href="api-reference.html",
        hero_title="API Reference",
        hero_sub="All 11 endpoints, generated from the OpenAPI contract.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 4. MCP Reference
# ---------------------------------------------------------------------------

def build_mcp_reference() -> str:
    body = f"""
<h1>MCP Reference</h1>
<p>The TradeWave MCP server exposes 16 tools (5 flagship + 11 primitives) that let AI assistants (Claude, ChatGPT, Cursor) reason over seasonal trading signals directly. Auth is BYOK - your TradeWave API key gates the server; tier and entitlements flow from the key.</p>

<div class="callout">
  <p><strong>A research partner, not a black box.</strong> TradeWave supplies a seasonal + 62-feature-ML statistical edge and the timing only. It is blind to fundamentals, valuation, news, catalysts, macro/rates, analyst views, earnings dates, and the live price. It is designed to pair with the assistant's own web, news, and reasoning tools: TradeWave gives the seasonal/ML edge, the assistant extends it with fundamentals/news/macro, and the two synthesize one view. Every card carries a research hand-off, and the <code class="inline-code">describe_tradewave</code> tool self-documents the method. Tools use progressive disclosure - a one-line decision by default, full receipts / the Trend Chart data on request.</p>
</div>

<div class="callout">
  <p><strong>Signals only.</strong> The same contract as the REST API applies. No raw prices or OHLCV data is ever returned. ML tools are available on every tier, metered per day (free 5/day, unlimited on Pro/Business). When the daily limit is reached the tool returns a graceful stub instead of an error.</p>
</div>

<h2>Flagship tools</h2>
<p>Start here. These five do the synthesis for you - rank, explain, and compare seasonal setups in one call.</p>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">find_best_opportunities</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>The workhorse. Scans a market (or the user's watchlist) and returns the strongest seasonal setups right now as ranked decision cards - headline, signal, edge score, entry window, and a research hand-off. Use when the user asks what to trade or when to enter.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">market</code>, <code class="inline-code">window</code> (e.g. "now"), <code class="inline-code">direction</code> (long | short), <code class="inline-code">rank_by</code>, <code class="inline-code">limit</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/scan</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">analyze_symbol</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Deep-dives one named ticker - the best current seasonal setup plus alternative setups, full receipts, and a ready-to-place ticket. Use when the user asks about a specific symbol.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">symbol</code> (required), <code class="inline-code">market</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/analyze/{{symbol}}</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">explain_pick</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns the full receipts behind a setup - years tested, per-year win/loss history, best/worst year, the Trend Chart summary, and the seasonal + ML basis. Use when the user asks "why?" or wants to see the evidence behind a card.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">symbol</code> (required), <code class="inline-code">market</code>, <code class="inline-code">entry_date</code>, <code class="inline-code">days_out</code>, <code class="inline-code">direction</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/analyze/{{symbol}}</code> (receipts)</p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">whats_seasonal_now</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>The zero-input starting point. Returns what is seasonally in play right now across the caller's in-scope markets - a fast "what should I be looking at today" overview.</p>
    <p><strong>Inputs:</strong> none (optional <code class="inline-code">market</code>, <code class="inline-code">limit</code>)</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/scan</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">compare_opportunities</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Puts two or more setups side by side on the same yardstick - edge score, win rate, Sharpe, avg/median return, ML basis - so the assistant can reason about which is stronger. Use when the user is choosing between candidates.</p>
    <p><strong>Inputs:</strong> list of <code class="inline-code">{{symbol, market, entry_date, days_out, direction}}</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/analyze/{{symbol}}</code> (per item)</p>
  </div>
</div>

<h2>Primitive tools</h2>
<p>Lower-level building blocks for clients that want to compose their own flow.</p>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">list_markets</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns the 15 active TradeWave markets and which are within the caller's tier scope. Use this to discover what markets are available before fetching opportunities.</p>
    <p><strong>Inputs:</strong> none</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/markets</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">whoami</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Reports the caller's identity and entitlements as resolved from the API key - tier, in-scope markets, ML allowance, and remaining quota. Use to check what the current key can do before making scoped calls.</p>
    <p><strong>Inputs:</strong> none</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/markets</code> (entitlements)</p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">describe_tradewave</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Self-documents the method: what TradeWave measures (seasonal + 62-feature ML), what it is blind to (fundamentals, news, macro, live price), and how the assistant should pair it with its own research tools. Call this once so the model frames TradeWave correctly as a research partner.</p>
    <p><strong>Inputs:</strong> none</p>
    <p><strong>Maps to:</strong> static method description</p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">list_symbols</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Lists the tradeable symbols in a market.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">market</code> (market id, e.g. "2")</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/markets/{{market_id}}/symbols</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_seasonal_opportunities</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Find the best seasonal trade setups for a market and date window, ranked by historical edge. Use when the user asks what to trade, when to enter, or which symbols have a strong seasonal tendency.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">market</code> (required), <code class="inline-code">from</code>, <code class="inline-code">to</code>, <code class="inline-code">direction</code> (long | short), <code class="inline-code">min_win_rate</code> (0-1), <code class="inline-code">limit</code></p>
    <p><strong>Returns:</strong> ranked list - symbol, direction, entry date, holding period, Sharpe ratio, avg/median return %, win rate. ML fields are available on every tier (metered per day) and are null only when your daily ML allowance is spent or the market is not ML-eligible (ids 0-4, 11).</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/opportunities</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_symbol_patterns</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Fetches the seasonal setups for a specific symbol. Use when you want the raw per-symbol opportunity rows rather than a synthesized card.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">symbol</code> (required), <code class="inline-code">market</code> (required)</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/opportunities/{{symbol}}</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_seasonal_pattern</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns aggregate seasonal pattern statistics for a symbol - win rate, average return, Sharpe, sample size. No price series is returned.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">market</code> (required), <code class="inline-code">symbol</code> (required)</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/patterns/{{market_id}}/{{symbol}}</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_opportunity_chart</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns The Trend Chart DATA (not an image) for a seasonal setup - a single year-averaged, normalized 0-100 seasonal index curve (<code class="inline-code">seasonal_curve</code>, one <code class="inline-code">{{date, index}}</code> point per day). It is the typical within-year shape (where it rises, peaks, fades), NOT per-year cumulative price paths, and the index is never a price. Agents can reason over the shape. Raw prices are intentionally not exposed.</p>
    <p><strong>Inputs:</strong> <code class="inline-code">market</code> (required), <code class="inline-code">symbol</code> (required), <code class="inline-code">entry_date</code>, <code class="inline-code">days_out</code>, <code class="inline-code">direction</code>, <code class="inline-code">years</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/seasonal-chart</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">score_opportunities</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Runs the ML model on a list of opportunities and returns <code class="inline-code">ml_score</code>, <code class="inline-code">win_prob</code>, <code class="inline-code">pred_return</code>, and <code class="inline-code">pred_mfe</code> for each. Available on every tier, metered per day (free 5/day, Dev 100/day, Pro/Business unlimited). When the daily limit is reached the response includes a graceful stub instead of scoring - never an error.</p>
    <p><strong>Inputs:</strong> list of <code class="inline-code">{{symbol, date, days_out, direction}}</code></p>
    <p><strong>Maps to:</strong> <code class="inline-code">POST /v1/score</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_daily_pick</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns today's ML-selected featured opportunity. The daily pick is the top ML-scored setup published each morning before market open.</p>
    <p><strong>Inputs:</strong> none</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/daily-pick</code></p>
  </div>
</div>

<div class="tool-card">
  <div class="tool-card-header">
    <span class="tool-name">get_pick_track_record</span>
    <span class="tier-badge tier-all">All tiers</span>
  </div>
  <div class="tool-card-body">
    <p>Returns the verifiable, time-stamped win/loss record of all past daily picks - this is the live, forward-tested <code class="inline-code">track_record.win_rate</code>, distinct from the seasonal <code class="inline-code">historical_win_rate</code> and the per-instance <code class="inline-code">ml_win_prob</code>. Use this to show the AI's historical performance to the user.</p>
    <p><strong>Inputs:</strong> none</p>
    <p><strong>Maps to:</strong> <code class="inline-code">GET /v1/daily-pick/track-record</code></p>
  </div>
</div>

<h2>Connecting to MCP clients</h2>

<p>TradeWave's MCP is a hosted HTTP server at <code class="inline-code">https://mcp.tradewave.ai/mcp</code>. HTTP-native clients (ChatGPT and others) point straight at that URL with a Bearer API key. Stdio-only clients (Claude Desktop, Cursor) bridge to it with the <code class="inline-code">mcp-remote</code> npx shim. There is no npm package to install.</p>

<h3>Claude Desktop</h3>
<p>Claude Desktop is a stdio-only client, so it bridges to the hosted server with the <code class="inline-code">mcp-remote</code> shim. Add the following block to your <code class="inline-code">claude_desktop_config.json</code> (usually at <code class="inline-code">~/Library/Application Support/Claude/claude_desktop_config.json</code> on macOS):</p>
<pre><code>{{
  "mcpServers": {{
    "tradewave": {{
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://mcp.tradewave.ai/mcp",
        "--header", "Authorization: Bearer ${{TRADEWAVE_API_KEY}}"
      ],
      "env": {{
        "TRADEWAVE_API_KEY": "tw_live_&lt;your-key&gt;"
      }}
    }}
  }}
}}</code></pre>
<p>Restart Claude Desktop. The TradeWave tools appear in the tools panel automatically.</p>

<h3>ChatGPT (HTTP-native MCP)</h3>
<p>ChatGPT speaks MCP over HTTP, so point it straight at the hosted endpoint with a Bearer API key - no shim needed:</p>
<pre><code>Server URL: https://mcp.tradewave.ai/mcp
Auth type:  API Key (Bearer)
Header:     Authorization: Bearer &lt;your-api-key&gt;</code></pre>
<p>In the connector / GPT builder, paste the server URL and select <strong>API Key</strong> as the auth method, supplying your TradeWave key as the Bearer token.</p>

<h3>Cursor</h3>
<p>Cursor is also a stdio client, so it uses the same <code class="inline-code">mcp-remote</code> shim. In <strong>Cursor Settings &rarr; Features &rarr; MCP Servers</strong>, add:</p>
<pre><code>{{
  "tradewave": {{
    "command": "npx",
    "args": [
      "-y", "mcp-remote",
      "https://mcp.tradewave.ai/mcp",
      "--header", "Authorization: Bearer ${{TRADEWAVE_API_KEY}}"
    ],
    "env": {{
      "TRADEWAVE_API_KEY": "tw_live_&lt;your-key&gt;"
    }}
  }}
}}</code></pre>

<h2>Tier behavior in MCP</h2>
<p>The same tier rules from the REST API apply:</p>
<ul>
  <li>Free: S&amp;P 500 stocks only, 3 results per call, 5 ML calls/day.</li>
  <li>Dev: all 15 markets, 100 ML calls/day.</li>
  <li>Pro/Business: all 15 markets, unlimited ML calls.</li>
  <li><code class="inline-code">score_opportunities</code> scores up to the daily allowance and returns <code class="inline-code">ml_remaining_today</code>. When the daily limit is already spent it returns a graceful <code class="inline-code">{{"requires":"upgrade","reason":"ml_daily_limit"}}</code> stub - the agent can surface this to the user without crashing.</li>
</ul>
"""
    return page(
        title="MCP Reference",
        description="TradeWave MCP server - 16 tools (5 flagship + 11 primitives) for AI assistants, plus connection instructions for Claude Desktop, ChatGPT, and Cursor.",
        active_href="mcp-reference.html",
        hero_title="MCP Reference",
        hero_sub="16 tools for AI assistants (5 flagship + 11 primitives) - connect in Claude Desktop, ChatGPT, or Cursor.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 5. Data Dictionary
# ---------------------------------------------------------------------------

def build_data_dictionary() -> str:
    body = """
<h1>Data Dictionary</h1>
<p>Plain-English definitions of every field returned by the TradeWave API. All monetary returns are expressed as <strong>percentages</strong>. Raw prices and OHLCV data are never returned.</p>

<h2>Core opportunity fields</h2>
<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Definition</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="field-name">symbol</td>
      <td class="field-type">string</td>
      <td>Ticker symbol (e.g. "AAPL"). Exactly as used by the market data provider.</td>
    </tr>
    <tr>
      <td class="field-name">market</td>
      <td class="field-type">string</td>
      <td>Permanent market id ("0".."16"). See the Markets table below. Never renumbered.</td>
    </tr>
    <tr>
      <td class="field-name">direction</td>
      <td class="field-type">string</td>
      <td><strong>long</strong> - the seasonal pattern historically rises over the holding period. <strong>short</strong> - it historically falls. This is a historically derived signal, not a recommendation.</td>
    </tr>
    <tr>
      <td class="field-name">entry_date</td>
      <td class="field-type">date</td>
      <td>The calendar date the seasonal pattern entry window begins (ISO 8601, e.g. "2026-06-01").</td>
    </tr>
    <tr>
      <td class="field-name">days_out</td>
      <td class="field-type">integer</td>
      <td>The holding period in calendar days. The pattern's historical win/loss statistics are measured at this exit point. Example: 22 means the exit is 22 calendar days after entry.</td>
    </tr>
    <tr>
      <td class="field-name">years</td>
      <td class="field-type">string</td>
      <td>The lookback window label - always a string (e.g. "10", "5"). Represents how many years of historical instances are included in the statistical summary. Kept as a string to preserve the exact label used in the platform.</td>
    </tr>
    <tr>
      <td class="field-name">sharpe_ratio</td>
      <td class="field-type">number</td>
      <td>The Sharpe ratio of the seasonal pattern over the lookback window. Higher is better. Measures return per unit of volatility across the historical instances. Not annualized - it is specific to the holding period defined by <strong>days_out</strong>.</td>
    </tr>
    <tr>
      <td class="field-name">avg_profit_pct</td>
      <td class="field-type">number</td>
      <td>Mean return (in percent) across all historical instances of this pattern. Positive = historically profitable on average. Example: 3.12 means the average instance returned +3.12%.</td>
    </tr>
    <tr>
      <td class="field-name">median_profit_pct</td>
      <td class="field-type">number</td>
      <td>Median return (in percent) across historical instances. Less sensitive to outlier years than the mean. Useful when a single large year skews <strong>avg_profit_pct</strong>.</td>
    </tr>
    <tr>
      <td class="field-name">win_rate</td>
      <td class="field-type">number (0..1)</td>
      <td>Fraction of historical instances that closed in the profitable direction at <strong>days_out</strong>. Example: 0.78 means 78% of past instances were winners. Does not account for position sizing or slippage.</td>
    </tr>
  </tbody>
</table>

<h2>ML fields (all tiers, metered per day)</h2>
<p>ML fields are available on every tier, metered per day: free 5/day, Dev 100/day, Pro/Business unlimited. ML fields are <code class="inline-code">null</code> when the daily limit is exhausted or the market is not ML-eligible (ids 5-13, 16). ML-eligible markets are ids 0, 1, 2, 3, 4, and 11.</p>
<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Definition</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="field-name">ml_score</td>
      <td class="field-type">number</td>
      <td>Composite ML score from the 62-feature model (higher = stronger predicted edge). Not directly interpretable as a probability - use <strong>win_prob</strong> for that.</td>
    </tr>
    <tr>
      <td class="field-name">win_prob</td>
      <td class="field-type">number (0..1)</td>
      <td>ML-estimated probability that this opportunity will be a winner at the exit date. Calibrated to historical out-of-sample results. Example: 0.81 = 81% predicted win probability.</td>
    </tr>
    <tr>
      <td class="field-name">pred_return</td>
      <td class="field-type">number</td>
      <td>ML-predicted return in percent at the exit date. This is the model's point estimate of the expected percentage gain (long) or drop (short).</td>
    </tr>
    <tr>
      <td class="field-name">pred_mfe</td>
      <td class="field-type">number</td>
      <td>Predicted Maximum Favorable Excursion in percent - the ML model's estimate of the best-case intra-period move in the favorable direction. Useful for sizing and stop placement, not a guarantee.</td>
    </tr>
  </tbody>
</table>

<h2>Daily pick fields</h2>
<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Definition</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="field-name">featured_date</td>
      <td class="field-type">date</td>
      <td>The date this pick was published (ISO 8601). One pick is published each trading morning.</td>
    </tr>
    <tr>
      <td class="field-name">pattern_summary</td>
      <td class="field-type">string</td>
      <td>A plain-English description of why this symbol was selected - the key stats and seasonal context.</td>
    </tr>
    <tr>
      <td class="field-name">return_pct</td>
      <td class="field-type">number | null</td>
      <td>Realized return in percent at the exit date. Null while the trade is still open (result = "open").</td>
    </tr>
    <tr>
      <td class="field-name">result</td>
      <td class="field-type">string</td>
      <td>"win", "loss", or "open". "open" means the holding period has not yet elapsed.</td>
    </tr>
  </tbody>
</table>

<h2>Seasonal chart fields</h2>
<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Definition</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="field-name">seasonal_curve</td>
      <td class="field-type">array</td>
      <td>The single year-averaged, normalized 0-100 seasonal index curve - one <code class="inline-code">{date, index}</code> point per calendar day. <code class="inline-code">index</code> is a relative shape (0-100), NEVER a price, and the series cannot be used to reconstruct prices. This is the typical within-year shape, not per-year paths.</td>
    </tr>
    <tr>
      <td class="field-name">per_year</td>
      <td class="field-type">array</td>
      <td>On a SignalCard's <code class="inline-code">receipts</code>: one row per lookback year as <code class="inline-code">{year, return_pct, result}</code> - the % return that year and whether it was a win or loss. No price series.</td>
    </tr>
  </tbody>
</table>

<h2>Markets (ids 0 - 16)</h2>
<p>Market ids are permanent resource keys. They are never renumbered. Ids 14 and 15 (Korea) were removed; the gap is intentional.</p>
<div class="tier-table-wrap">
<table class="tier-table">
  <thead>
    <tr><th>ID</th><th>Market</th><th>ML eligible</th><th>Notes</th></tr>
  </thead>
  <tbody>
    <tr><td>0</td><td>DOW 30 STOCKS</td><td class="check">Yes</td><td></td></tr>
    <tr><td>1</td><td>NASDAQ 100 STOCKS</td><td class="check">Yes</td><td></td></tr>
    <tr><td>2</td><td>S&amp;P 500 STOCKS</td><td class="check">Yes</td><td>Free tier access</td></tr>
    <tr><td>3</td><td>RUSSELL 1000 STOCKS</td><td class="check">Yes</td><td></td></tr>
    <tr><td>4</td><td>WILSHIRE 5000</td><td class="check">Yes</td><td></td></tr>
    <tr><td>5</td><td>INDICES COMMON</td><td class="cross">No</td><td></td></tr>
    <tr><td>6</td><td>INDICES ALL</td><td class="cross">No</td><td></td></tr>
    <tr><td>7</td><td>FUTURES &amp; COMMODITIES</td><td class="cross">No</td><td></td></tr>
    <tr><td>8</td><td>FOREX ALL</td><td class="cross">No</td><td></td></tr>
    <tr><td>9</td><td>FOREX LIQUID</td><td class="cross">No</td><td></td></tr>
    <tr><td>10</td><td>GOVERNMENT BONDS</td><td class="cross">No</td><td></td></tr>
    <tr><td>11</td><td>ETFs</td><td class="check">Yes</td><td></td></tr>
    <tr><td>12</td><td>LONDON EXCHANGE</td><td class="cross">No</td><td></td></tr>
    <tr><td>13</td><td>TORONTO STOCKS</td><td class="cross">No</td><td></td></tr>
    <tr><td>14</td><td colspan="3"><em>Removed (Korea) - id reserved, never reused</em></td></tr>
    <tr><td>15</td><td colspan="3"><em>Removed (Korea) - id reserved, never reused</em></td></tr>
    <tr><td>16</td><td>CRYPTO CURRENCIES</td><td class="cross">No</td><td></td></tr>
  </tbody>
</table>
</div>

<div class="callout">
  <p><strong>No raw prices ever.</strong> The API never returns OHLCV data, last price, or price-by-date. All numeric return fields are percentages, measured from entry to exit over the holding window. This is by design and is an invariant of the API contract.</p>
</div>
"""
    return page(
        title="Data Dictionary",
        description="Plain-English definitions of every TradeWave API field - direction, days_out, Sharpe ratio, win rate, ML scores, markets, and more.",
        active_href="data-dictionary.html",
        hero_title="Data Dictionary",
        hero_sub="Plain-English definitions of every field and all 15 active markets.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 6. Rate Limits & Errors
# ---------------------------------------------------------------------------

def build_rate_limits() -> str:
    tiers = API_TIERS

    # Build tier table rows from live tiers.py
    tier_rows = []
    for tier_key, t in tiers.items():
        pm = t["rate"]["per_minute"]
        pd = t["rate"]["per_day"]
        opp = t["opp_limit"]
        price = f"${t['price_monthly']}/mo" if t["price_monthly"] else "Free"
        ml = '<span class="check">Yes</span>' if t["ml_access"] else '<span class="cross">No</span>'
        tier_rows.append(
            f"<tr><td class='tier-name'>{t['name']}</td>"
            f"<td class='price-col'>{price}</td>"
            f"<td>{pm:,}/min</td><td>{pd:,}/day</td>"
            f"<td>{opp:,}</td><td>{ml}</td></tr>"
        )
    tier_rows_html = "\n".join(tier_rows)

    body = f"""
<h1>Rate Limits &amp; Errors</h1>
<p>Limits are enforced per API key. Exceeding them returns a <code class="inline-code">429 Too Many Requests</code> response with retry headers.</p>

<h2>Per-tier limits</h2>
<div class="tier-table-wrap">
<table class="tier-table">
  <thead>
    <tr>
      <th>Tier</th>
      <th>Price</th>
      <th>Rate (per min)</th>
      <th>Rate (per day)</th>
      <th>Max results (/opportunities)</th>
      <th>ML access</th>
    </tr>
  </thead>
  <tbody>
    {tier_rows_html}
  </tbody>
</table>
</div>
<p>The <strong>max results</strong> column is the tier cap for the <code class="inline-code">limit</code> parameter on <code class="inline-code">GET /v1/opportunities</code>. Requesting more than the cap returns up to the cap without error.</p>

<h2>Rate limit headers</h2>
<p>Every response includes these headers:</p>
<table>
  <thead>
    <tr><th>Header</th><th>Value</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="field-name">X-RateLimit-Limit</td>
      <td>Your tier's per-minute request limit</td>
    </tr>
    <tr>
      <td class="field-name">X-RateLimit-Remaining</td>
      <td>Requests remaining in the current minute window</td>
    </tr>
    <tr>
      <td class="field-name">X-RateLimit-Reset</td>
      <td>Unix timestamp (UTC) when the current window resets</td>
    </tr>
  </tbody>
</table>

<p>Example headers on a 429 response:</p>
<pre><code>HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit:     10
X-RateLimit-Remaining: 0
X-RateLimit-Reset:     1748384460
Content-Type:          application/json

{{
  "error": {{
    "code":    "rate_limited",
    "message": "You have exceeded 10 requests per minute. Retry after 2026-05-27T14:01:00Z."
  }}
}}</code></pre>

<h2>Error codes</h2>
<table>
  <thead>
    <tr><th>HTTP status</th><th>code</th><th>Meaning</th></tr>
  </thead>
  <tbody>
    <tr><td>400</td><td><code class="inline-code">bad_request</code></td><td>Missing or invalid parameter (see message for details)</td></tr>
    <tr><td>401</td><td><code class="inline-code">unauthorized</code></td><td>Missing or invalid API key</td></tr>
    <tr><td>403</td><td><code class="inline-code">forbidden</code></td><td>Valid key but the resource requires a higher tier</td></tr>
    <tr><td>404</td><td><code class="inline-code">not_found</code></td><td>Unknown market id or symbol</td></tr>
    <tr><td>429</td><td><code class="inline-code">rate_limited</code></td><td>Too many requests - check X-RateLimit-Reset</td></tr>
    <tr><td>500</td><td><code class="inline-code">internal_error</code></td><td>Unexpected server error - try again; report if persistent</td></tr>
  </tbody>
</table>

<h2>ML daily limit stub</h2>
<p>When the daily ML allowance is already fully spent, <code class="inline-code">POST /v1/score</code> returns <strong>HTTP 200</strong> with a limit stub rather than an error. This lets MCP agents degrade gracefully. The stub includes <code class="inline-code">ml_remaining_today: 0</code> so callers can check it without parsing the message.</p>
<pre><code>{{
  "requires":          "upgrade",
  "reason":            "ml_daily_limit",
  "message":           "Daily ML limit reached. Upgrade for unlimited ML calls.",
  "upgrade_url":       "{portal_urls.nav('/pricing')}",
  "ml_remaining_today": 0
}}</code></pre>
<p>For MCP/agents, check for <code class="inline-code">"reason": "ml_daily_limit"</code> to distinguish a spent daily allowance from other upgrade prompts.</p>

<h2>Error envelope</h2>
<p>All error responses (4xx, 5xx) follow this shape:</p>
<pre><code>{{
  "error": {{
    "code":    "string",
    "message": "string"
  }}
}}</code></pre>

<h2>Best practices</h2>
<ul>
  <li>Check <code class="inline-code">X-RateLimit-Remaining</code> proactively and back off before hitting zero.</li>
  <li>On 429, wait until <code class="inline-code">X-RateLimit-Reset</code> before retrying.</li>
  <li>For MCP/agents, check for <code class="inline-code">"reason": "ml_daily_limit"</code> in the response to handle a spent daily ML allowance gracefully.</li>
  <li>On 500, retry with exponential backoff. If the error persists, contact <a href="{portal_urls.nav('/contact.html')}">support</a>.</li>
</ul>
"""
    return page(
        title="Rate Limits & Errors",
        description="TradeWave API rate limits by tier, X-RateLimit headers, error codes, and the Pro upgrade stub.",
        active_href="rate-limits.html",
        hero_title="Rate Limits &amp; Errors",
        hero_sub="Per-tier limits, retry headers, error codes, and the upgrade stub.",
        body=body,
    )


# ---------------------------------------------------------------------------
# 7. Changelog
# ---------------------------------------------------------------------------

def build_changelog() -> str:
    body = """
<h1>Changelog</h1>
<p>Version history for the TradeWave Data API and MCP server. Breaking changes are always version-bumped.</p>

<div class="changelog-entry">
  <div class="changelog-version">
    <span class="version-badge">v1.0.0</span>
    <span class="version-date">2026-05-27</span>
    <span class="version-status">Current</span>
  </div>
  <p><strong>Initial public release.</strong></p>
  <ul>
    <li>9 REST endpoints: markets, symbols, opportunities (list + by-symbol), patterns, seasonal-chart, score (Pro), daily-pick, track-record.</li>
    <li>16 MCP tools (5 flagship + 11 primitives) wrapping the REST API - connect via Claude Desktop, ChatGPT, or Cursor.</li>
    <li>4 API tiers: Free, Dev ($39/mo), Pro ($199/mo), Business ($599/mo).</li>
    <li>Bearer token auth via <code class="inline-code">Authorization: Bearer &lt;key&gt;</code>. Keys issued in the dashboard.</li>
    <li>ML fields (<code class="inline-code">ml_score</code>, <code class="inline-code">win_prob</code>, <code class="inline-code">pred_return</code>, <code class="inline-code">pred_mfe</code>) available on every tier, metered per day (free 5/day, Dev 100/day, Pro/Business unlimited), on ML-eligible markets (ids 0-4, 11).</li>
    <li>Graceful upgrade stubs for non-Pro ML calls - HTTP 200 with <code class="inline-code">{"requires":"pro"}</code>.</li>
    <li>15 active markets (ids 0-13, 16). Ids 14/15 reserved (Korea, removed).</li>
    <li>All returns are percentages. No raw OHLCV or price-level data is ever returned.</li>
    <li><code class="inline-code">years</code> field remains a string throughout the API (stable label, not an integer).</li>
    <li>Rate limits: Free 10/min 100/day, Dev 60/min 5k/day, Pro 300/min 50k/day, Business 1.2k/min 250k/day.</li>
    <li>Standard <code class="inline-code">X-RateLimit-Limit</code> / <code class="inline-code">X-RateLimit-Remaining</code> / <code class="inline-code">X-RateLimit-Reset</code> headers on all responses.</li>
  </ul>
</div>

<div class="callout">
  <p><strong>API stability contract.</strong> v1 endpoints, field names, and the market id mapping are stable. Breaking changes (renamed or removed fields, behavior changes) will be released as v2 with a deprecation notice. Additive changes (new fields, new endpoints) may be made to v1 without notice.</p>
</div>
"""
    return page(
        title="Changelog",
        description="TradeWave API v1 release history and stability contract.",
        active_href="changelog.html",
        hero_title="Changelog",
        hero_sub="Version history and API stability contract.",
        body=body,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PAGES = [
    ("quickstart.html",       build_quickstart),
    ("authentication.html",   build_authentication),
    ("api-reference.html",    build_api_reference),
    ("mcp-reference.html",    build_mcp_reference),
    ("data-dictionary.html",  build_data_dictionary),
    ("rate-limits.html",      build_rate_limits),
    ("changelog.html",        build_changelog),
]


def main() -> int:
    print("TradeWave API docs generator")
    print(f"  openapi.yaml: {OPENAPI_YAML}")
    print(f"  output:       {OUTPUT_DIR}")
    print()

    if not OPENAPI_YAML.exists():
        print(f"ERROR: {OPENAPI_YAML} not found", file=sys.stderr)
        return 2
    if not HEADER_PARTIAL.exists():
        print(f"ERROR: {HEADER_PARTIAL} not found", file=sys.stderr)
        return 2

    for fname, builder in PAGES:
        print(f"  building {fname} ...", end=" ", flush=True)
        html = builder()
        out = OUTPUT_DIR / fname
        out.write_text(html, encoding="utf-8")
        print(f"{len(html):,} bytes -> {out}")

    print()
    print("Done. Regenerate any time with:")
    print("  /home/flask/venv/bin/python /home/flask/site/api_docs/generate_api_docs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
