#!/usr/bin/env python3
"""Render the TradeWave API developer LEARNING track.

Reads the authored Markdown in site/content/learn_api/*.md (YAML frontmatter: title, slug,
description, order, read_minutes) and renders each to a branded HTML page that reuses the
developer-docs shell (same CSS, header, footer, code-tab styling) so the portal is cohesive.
Also builds a learning index (index.html) of article cards.

Output: site/api_learn/out/  (the deploy step publishes it at developers.tradewave.ai/learn/).
Run:  ./venv/bin/python site/api_learn/generate_learn_api.py
"""
import re
import sys
from pathlib import Path

import yaml
import markdown as md

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # /home/flask
CONTENT_DIR = REPO / "site" / "content" / "learn_api"
OUT_DIR = HERE / "out"

# Reuse the docs shell (CSS, header, footer, year) so /learn matches /docs exactly.
sys.path.insert(0, str(REPO / "site" / "lib"))
sys.path.insert(0, str(REPO / "site" / "api_docs"))
import portal_urls                              # noqa: E402
import portal_seo                               # noqa: E402
import generate_api_docs as gad                 # noqa: E402  (main() is __main__-guarded; safe to import)

DOCS_URL = portal_urls.DOCS_URL
LEARN_URL = portal_urls.LEARN_URL
API_BASE = portal_urls.API_BASE
MCP_SETUP_URL = portal_urls.MCP_SETUP_URL
# Signup-wrapped (spec API_CONSOLE_USER_FLOWS.md R1/R2): every "Get an API Key" CTA in the
# learning track is a free-key acquisition intent, so it routes through /signup carrying the
# real keys target, not straight to the login-gated console.
CONSOLE_URL = portal_urls.signup_url("/account/api/keys")

# ---------------------------------------------------------------------------
# URL templating: lessons are authored env-agnostic with {{TOKEN}} placeholders
# (a 2026-06-12 review found 8 of 9 lessons hardcoding api.tradewave.ai /
# mcp.tradewave.ai plus a dead tradewave.ai keys link, so the dev/staging output
# pointed every reader at prod). The generator substitutes them from portal_urls
# so each environment emits its own hosts, and FAILS the build (fail-fast) on a
# hardcoded tradewave.ai URL or an unknown/unsubstituted token.
# ---------------------------------------------------------------------------
URL_TOKENS = {
    "{{API_BASE}}": API_BASE,                       # https://<api-host>/v1
    "{{MCP_URL}}": portal_urls.MCP_URL,             # the MCP endpoint itself
    "{{MCP_SETUP_URL}}": MCP_SETUP_URL,             # the human MCP setup guide
    "{{CONSOLE_URL}}": CONSOLE_URL,                 # account console (API keys)
    "{{DOCS_URL}}": DOCS_URL,                       # developer docs root
    "{{LEARN_URL}}": LEARN_URL,                     # this learning track
    "{{PORTAL_URL}}": portal_urls.PORTAL_URL,       # developer portal root
    "{{PRICING_URL}}": portal_urls.dev("pricing.html"),  # API pricing page
}

_LEFTOVER_TOKEN = re.compile(r"\{\{[A-Z_]+\}\}")


def substitute_urls(text: str, source: str) -> str:
    if "tradewave.ai" in text:
        raise SystemExit(
            f"{source}: hardcoded tradewave.ai URL in lesson source - "
            "use the {{TOKEN}} placeholders (see URL_TOKENS) so every env "
            "emits its own hosts")
    for token, value in URL_TOKENS.items():
        text = text.replace(token, value)
    leftover = sorted(set(_LEFTOVER_TOKEN.findall(text)))
    if leftover:
        raise SystemExit(f"{source}: unknown URL token(s) {leftover} - add to URL_TOKENS or fix the typo")
    return text

# The small code-tab switcher script (identical behavior to the docs pages).
_TAB_SCRIPT = """
<script>
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.code-tabs').forEach(function(tabs) {
    var btns = tabs.querySelectorAll('.code-tab-btn');
    var panes = tabs.querySelectorAll('.code-tab-pane');
    btns.forEach(function(btn, i) {
      btn.addEventListener('click', function() {
        btns.forEach(function(b) { b.classList.remove('active'); });
        panes.forEach(function(p) { p.classList.remove('active'); });
        btn.classList.add('active');
        panes[i].classList.add('active');
      });
    });
  });
});
</script>"""

# A little extra CSS for the learning index cards (scoped; appended to the shared PAGE_CSS).
_LEARN_CSS = """
.learn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;margin:28px 0;}
.learn-card{display:block;border:1px solid var(--border);border-radius:12px;padding:20px 22px;
  background:var(--bg-alt);text-decoration:none;transition:border-color .15s,transform .15s;}
.learn-card:hover{border-color:var(--accent);transform:translateY(-2px);}
.learn-card .num{font-size:12px;font-weight:700;color:var(--accent);letter-spacing:.05em;}
.learn-card h3{margin:8px 0 6px;color:#fff;font-size:17px;}
.learn-card p{margin:0;color:var(--text-dim);font-size:14px;line-height:1.55;}
.learn-card .meta{margin-top:12px;font-size:12px;color:var(--text-muted);}
.article-meta{color:var(--text-muted);font-size:13px;margin:-6px 0 22px;}
.article-nav{display:flex;justify-content:space-between;gap:14px;margin-top:40px;
  border-top:1px solid var(--border);padding-top:22px;}
.article-nav a{font-size:14px;color:var(--text-dim);text-decoration:none;max-width:48%;}
.article-nav a:hover{color:#fff;}
.article-nav .next{text-align:right;margin-left:auto;}
.docs-main h2{margin-top:34px;}
.docs-main pre{overflow:auto;}
"""


def render_markdown(body: str) -> str:
    return md.markdown(
        body,
        extensions=["fenced_code", "tables", "toc", "sane_lists", "attr_list", "footnotes"],
        output_format="html5",
    )


def load_articles() -> list:
    arts = []
    for p in sorted(CONTENT_DIR.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
        body = substitute_urls(body, p.name)
        meta["body_html"] = render_markdown(body.strip())
        meta.setdefault("slug", p.stem)
        meta.setdefault("title", p.stem)
        meta.setdefault("order", 999)
        meta.setdefault("read_minutes", 5)
        arts.append(meta)
    arts.sort(key=lambda a: a.get("order", 999))
    return arts


def sidebar(active_slug: str, articles: list) -> str:
    if active_slug == "connect-an-ai-agent-mcp":
        return f"""
<nav class="docs-sidebar" aria-label="MCP setup navigation">
  <h2>Setup</h2>
  <a href="#connect-tradewave" class="active">Connect TradeWave</a>
  <a href="#chatgpt">ChatGPT</a>
  <a href="#claudeai-and-claude-desktop">Claude</a>
  <a href="#confirm-the-connection">Confirm connection</a>
  <a href="#troubleshooting">Troubleshooting</a>
  <a href="#other-clients">Other clients</a>
  <hr class="sidebar-divider">
  <h2>More</h2>
  <a href="{MCP_SETUP_URL}">MCP Overview</a>
  <a href="{portal_urls.MCP_REFERENCE_URL}">MCP Tool Reference</a>
  <a href="{DOCS_URL}/quickstart.html">Developer Docs</a>
</nav>"""
    links = "\n".join(
        f'<a href="{a["slug"]}.html" {"class=\"active\"" if a["slug"] == active_slug else ""}>{a["title"]}</a>'
        for a in articles
    )
    more_links = f"""
  <a href="{DOCS_URL}/quickstart.html">Developer Docs</a>
  <a href="{DOCS_URL}/api-reference.html">API Reference</a>
  <a href="{portal_urls.PLAYGROUND_URL}">API Playground</a>
  <a href="{MCP_SETUP_URL}">MCP Overview</a>
  <a href="{CONSOLE_URL}">Get an API Key</a>"""
    return f"""
<nav class="docs-sidebar" aria-label="Learning navigation">
  <h2>Learn</h2>
  <a href="index.html" {'class="active"' if active_slug == "" else ""}>Overview</a>
  {links}
  <hr class="sidebar-divider">
  <h2>More</h2>
  {more_links}
</nav>"""


def shell(title: str, description: str, hero_title: str, hero_sub: str,
          sidebar_html: str, body: str, canonical_url: str = None,
          mcp_lesson: bool = False) -> str:
    header = gad.load_header()
    if mcp_lesson:
        # This lesson's primary path is hosted OAuth. Keep the global developer header from
        # telling ChatGPT/Claude users to get an API key or replacing the MCP setup link after
        # the shared authenticated-user script runs.
        header = header.replace(
            f'<a href="{CONSOLE_URL}" id="tw-cta-link" class="tw-btn-primary">Get API Key</a>',
            '<a href="#connect-tradewave" id="tw-cta-link" class="tw-btn-primary" '
            'data-preserve-cta="true">Connect TradeWave</a>',
        )
        header = header.replace(
            "if (cta) {",
            "if (cta && cta.dataset.preserveCta !== 'true') {",
        )
        header = header.replace(
            f'<a href="{portal_urls.API_PRICING_URL}">Pricing</a>',
            f'<a href="{portal_urls.API_PRICING_URL}">API Pricing</a>',
        )
    footer = gad.footer_html()
    canonical_url = canonical_url or LEARN_URL + "/"
    seo = portal_seo.head_tags(canonical_url, title, description, og_type="article")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - TradeWave Developer Learning</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index, follow">
  {seo}
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
  <style>{gad.PAGE_CSS}{_LEARN_CSS}</style>
</head>
<body>
{header}
<div class="docs-hero">
  <h1>{hero_title}</h1>
  <p>{hero_sub}</p>
</div>
<div class="docs-wrap">
  {sidebar_html}
  <main class="docs-main" id="main-content">
{body}
  </main>
</div>
{footer}
{_TAB_SCRIPT}
</body>
</html>"""


def build_index(articles: list) -> str:
    cards = []
    for a in articles:
        cards.append(f"""
  <a class="learn-card" href="{a['slug']}.html">
    <div class="num">LESSON {a['order']:02d}</div>
    <h3>{a['title']}</h3>
    <p>{a.get('description','')}</p>
    <div class="meta">{a.get('read_minutes',5)} min read</div>
  </a>""")
    body = f"""
<p>A hands-on track for building with the TradeWave Data API and MCP server. Every lesson uses
runnable code and the live <a href="{DOCS_URL}/api-reference.html">v1 endpoints</a>. New here?
Start with lesson 1, or jump straight to <a href="first-api-call.html">your first API call</a>.</p>

<div class="callout green">
  <p><strong>Following the REST API lessons?</strong> Create a developer key in the
  <a href="{CONSOLE_URL}">dashboard</a> and send it as
  <code class="inline-code">Authorization: Bearer tw_live_...</code>. The MCP setup lesson uses the
  TradeWave account authorization shown in that guide.</p>
</div>

<div class="learn-grid">{''.join(cards)}</div>

<h2>What you will be able to do</h2>
<ul>
  <li>Read a <strong>Pattern Card</strong> and trust it (receipts, per-year results, <code class="inline-code">neutral</code> honesty).</li>
  <li>Scan every market you can trade and rank the best seasonal setups with one call.</li>
  <li>Use the <strong>ML win-probability</strong> model, and handle its coverage gracefully.</li>
  <li>Connect Claude, Cursor, or ChatGPT to TradeWave over MCP.</li>
  <li>Build robust clients (rate limits, quotas, retries) and place trades at any broker.</li>
</ul>
"""
    return shell(
        title="Learn the TradeWave API",
        description="A hands-on developer track for the TradeWave seasonal-edge + ML-scored seasonal pattern API and MCP server.",
        hero_title="Learn the TradeWave API",
        hero_sub="Concepts and how-to guides, with runnable code, for the seasonal-edge + ML-scored seasonal pattern platform.",
        sidebar_html=sidebar("", articles),
        body=body,
    )


def build_article(a: dict, prev_a, next_a, articles: list) -> str:
    nav_bits = []
    if prev_a:
        nav_bits.append(f'<a class="prev" href="{prev_a["slug"]}.html">&larr; {prev_a["title"]}</a>')
    else:
        nav_bits.append('<span></span>')
    if next_a:
        nav_bits.append(f'<a class="next" href="{next_a["slug"]}.html">{next_a["title"]} &rarr;</a>')
    article_nav = f'<div class="article-nav">{"".join(nav_bits)}</div>'
    meta = ('<div class="article-meta">Setup guide</div>'
            if a["slug"] == "connect-an-ai-agent-mcp"
            else f'<div class="article-meta">Lesson {a["order"]:02d} &middot; {a.get("read_minutes",5)} min read</div>')
    body = meta + a["body_html"] + article_nav
    return shell(
        title=a["title"],
        description=a.get("description", ""),
        hero_title=a["title"],
        hero_sub=a.get("description", ""),
        sidebar_html=sidebar(a["slug"], articles),
        body=body,
        canonical_url=LEARN_URL + "/" + a["slug"] + ".html",
        mcp_lesson=a["slug"] == "connect-an-ai-agent-mcp",
    )


def main() -> int:
    articles = load_articles()
    if not articles:
        print(f"No articles found in {CONTENT_DIR}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"TradeWave learning generator\n  content: {CONTENT_DIR}\n  output:  {OUT_DIR}\n")
    (OUT_DIR / "index.html").write_text(build_index(articles), encoding="utf-8")
    print(f"  index.html ({len(articles)} lessons)")
    for i, a in enumerate(articles):
        prev_a = articles[i - 1] if i > 0 else None
        next_a = articles[i + 1] if i < len(articles) - 1 else None
        html = build_article(a, prev_a, next_a, articles)
        (OUT_DIR / f"{a['slug']}.html").write_text(html, encoding="utf-8")
        print(f"  {a['slug']}.html  ({a.get('read_minutes',5)}m)")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
