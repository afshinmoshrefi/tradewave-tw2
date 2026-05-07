#!/usr/bin/env python3
"""
TradeWave 2 — text-page generator (F4).

Lifts 3 legacy WP pages out of /home/afshin/wp-pages/ and emits TW2-branded
static HTML at /var/www/tradewave/{disclaimer.html, privacy.html, learn.html}.

- Strips Divi shortcodes ([et_pb_*] / [/et_pb_*]) and WP block comments.
- Wraps the resulting prose in a TW2 base layout (header partial + <main> +
  footer with Privacy/Disclaimer/Learn nav).
- learn.html is a placeholder; the actual Learn pages are authored elsewhere.

Idempotent: re-running overwrites the output files with fresh content.

Usage:
    python3 /home/flask/site/generate_text_pages.py
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SRC_DIR = Path("/home/flask/site/content")  # WP source HTML copied here
                                            # from /home/afshin/wp-pages/.
OUTPUT_DIR = Path("/var/www/tradewave")
TEMPLATES_DIR = Path(__file__).parent / "templates"
HEADER_PARTIAL = TEMPLATES_DIR / "_tw_header.html"

PAGES = [
    # (output filename, page title, source WP file id, hero subtitle)
    ("terms.html", "Terms & Conditions", "222576",
     "The terms governing your use of TradeWave."),
    ("privacy.html",    "Privacy Policy",     "222578",
     "How we collect, use, and protect your information."),
]

LEARN_FILENAME = "learn.html"
LEARN_TITLE = "Learn"
LEARN_SUBTITLE = "Guides, tutorials, and methodology — coming soon."

DISCLAIMER_FILENAME = "disclaimer.html"
DISCLAIMER_TITLE = "Financial Disclaimer"
DISCLAIMER_SUBTITLE = "What TradeWave is, what it isn't, and how to read what we publish."

# Year for the footer copyright + page-modified hint.
YEAR = datetime.now().year
TODAY_ISO = datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Strip helpers
# ---------------------------------------------------------------------------

# [et_pb_section ...attrs...] or [/et_pb_section]
DIVI_RE = re.compile(r"\[/?et_pb_[a-z_]+(?:\s+[^\]]*)?\]")
# <!-- wp:foo --> and <!-- /wp:foo -->
WP_COMMENT_RE = re.compile(r"<!--\s*/?wp:[^>]*-->")
# Stray legacy WP "page header" residue (we strip the whole hero section
# upfront so this is mostly redundant, but cheap insurance).
NBSP_RUN_RE = re.compile(r"(?:<p>\s*&nbsp;\s*</p>\s*){2,}")
# Legacy escape sequences from the WP DB dump (literal backslash-n, etc.).
LITERAL_NEWLINE_RE = re.compile(r"\\n")


def strip_wp_markup(raw: str) -> str:
    """Strip Divi shortcodes + WP block comments from a WP HTML blob."""
    s = DIVI_RE.sub("", raw)
    s = WP_COMMENT_RE.sub("", s)
    # The dumps contain literal "\n" rather than newlines — flatten.
    s = LITERAL_NEWLINE_RE.sub("\n", s)
    # Collapse stacked &nbsp; placeholders that the Divi hero left behind.
    s = NBSP_RUN_RE.sub("", s)
    # Rewrite legacy contact link to TW2's home so we don't ship dangling URLs.
    s = s.replace("https://tradeseasonals/contact", "/")
    s = s.replace("https://tradeseasonals.com", "/")
    return s.strip()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def load_header() -> str:
    return HEADER_PARTIAL.read_text(encoding="utf-8")


PAGE_CSS = """
:root {
  --bg: #0f0a15;
  --bg-alt: #15101e;
  --text: #e5e7eb;
  --text-dim: #9ca3af;
  --text-muted: #6b7280;
  --border: #1f2937;
  --link: #a78bfa;
  --link-hover: #c4b5fd;
}
html, body { background: var(--bg); color: var(--text); margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.7;
}
.tw-page-hero {
  background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(168,85,247,0.10) 100%);
  border-bottom: 1px solid var(--border);
  padding: 64px 24px 48px;
  text-align: center;
}
.tw-page-hero h1 {
  margin: 0 0 12px;
  font-size: 44px;
  font-weight: 800;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.tw-page-hero p { margin: 0 auto; max-width: 720px; color: var(--text-dim); font-size: 18px; }
main.tw-prose {
  max-width: 820px;
  margin: 0 auto;
  padding: 48px 24px 72px;
}
.tw-prose h2 {
  margin: 40px 0 16px;
  font-size: 26px;
  font-weight: 700;
  color: #ffffff;
}
.tw-prose h3 {
  margin: 28px 0 12px;
  font-size: 19px;
  font-weight: 600;
  color: #f3f4f6;
}
.tw-prose h4 { margin: 20px 0 8px; font-size: 16px; font-weight: 600; color: #f3f4f6; }
.tw-prose p, .tw-prose li { color: var(--text); }
.tw-prose a { color: var(--link); text-decoration: underline; }
.tw-prose a:hover { color: var(--link-hover); }
.tw-prose ul, .tw-prose ol { padding-left: 24px; }
.tw-prose li { margin-bottom: 8px; }
.tw-prose strong { color: #ffffff; }
.tw-prose hr { border: 0; border-top: 1px solid var(--border); margin: 32px 0; }
.tw-prose img { max-width: 100%; height: auto; border-radius: 8px; }
.tw-prose blockquote {
  border-left: 3px solid #8b5cf6;
  padding: 8px 16px;
  margin: 16px 0;
  color: var(--text-dim);
  background: rgba(139,92,246,0.05);
}
.tw-page-footer {
  border-top: 1px solid var(--border);
  background: var(--bg-alt);
  padding: 40px 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
.tw-page-footer nav { margin-bottom: 16px; }
.tw-page-footer nav a {
  color: var(--text-dim);
  text-decoration: none;
  margin: 0 12px;
  font-size: 14px;
}
.tw-page-footer nav a:hover { color: #ffffff; }
.tw-page-footer .tw-disclaimer {
  max-width: 800px;
  margin: 16px auto 0;
  font-size: 11px;
  line-height: 1.7;
  opacity: 0.7;
}
.tw-callout {
  background: rgba(139,92,246,0.08);
  border: 1px solid rgba(139,92,246,0.25);
  border-radius: 12px;
  padding: 20px 24px;
  margin: 32px 0;
}
.tw-callout p { margin: 0; }
@media (max-width: 640px) {
  .tw-page-hero h1 { font-size: 32px; }
  .tw-page-hero p { font-size: 16px; }
  main.tw-prose { padding: 32px 20px 48px; }
}
"""

LEGAL_DISCLAIMER = (
    "TradeWave is a research platform. It is not a brokerage and does not "
    "execute trades. All data is based on historical analysis and is provided "
    "for informational and educational purposes only. Past performance does "
    "not guarantee future results."
)


def render_page(title: str, subtitle: str, body_html: str, last_updated: str | None) -> str:
    """Wrap stripped prose in the TW2 layout."""
    header = load_header()
    last_updated_html = (
        f'<p class="tw-last-updated" style="color:#6b7280;font-size:13px;margin-top:0;">'
        f"Last updated: {last_updated}</p>"
        if last_updated else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — TradeWave</title>
  <meta name="description" content="{subtitle}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://tw2.trxstat.com/{title_to_filename(title)}">
  <style>{PAGE_CSS}</style>
</head>
<body>
{header}

<section class="tw-page-hero">
  <h1>{title}</h1>
  <p>{subtitle}</p>
</section>

<main class="tw-prose">
  {last_updated_html}
  {body_html}
</main>

<footer class="tw-page-footer">
  <nav aria-label="Footer">
    <a href="/">Home</a>
    <a href="/app/">Wave Viewer</a>
    <a href="/learn.html">Learn</a>
    <a href="/privacy.html">Privacy</a>
    <a href="/terms.html">Terms</a>
    <a href="/disclaimer.html">Disclaimer</a>
  </nav>
  <p>&copy; {YEAR} Tara Data Research LLC. All rights reserved.</p>
  <p class="tw-disclaimer">{LEGAL_DISCLAIMER}</p>
</footer>
</body>
</html>
"""


def title_to_filename(title: str) -> str:
    return {
        "Terms & Conditions": "terms.html",
        "Privacy Policy": "privacy.html",
        "Learn": "learn.html",
        "Financial Disclaimer": "disclaimer.html",
    }.get(title, title.lower().replace(" ", "-") + ".html")


# ---------------------------------------------------------------------------
# Per-page builders
# ---------------------------------------------------------------------------

LAST_UPDATED_RE = re.compile(r"<p>\s*Last updated:\s*([^<]+?)\s*</p>", re.I)


def build_legal_page(out_name: str, title: str, src_id: str, subtitle: str) -> tuple[str, dict]:
    src = SRC_DIR / f"page_{src_id}.html"
    raw = src.read_text(encoding="utf-8")
    stripped = strip_wp_markup(raw)
    # Pull "Last updated: ..." out of the body and surface it in the layout.
    last_updated = None
    m = LAST_UPDATED_RE.search(stripped)
    if m:
        last_updated = m.group(1).strip()
        stripped = LAST_UPDATED_RE.sub("", stripped, count=1)
    html = render_page(title, subtitle, stripped, last_updated)
    return html, {
        "src": str(src),
        "out": out_name,
        "raw_size": len(raw),
        "stripped_size": len(stripped),
        "wrapped_size": len(html),
        "last_updated": last_updated,
    }


def build_learn_placeholder() -> tuple[str, dict]:
    body = """
<div class="tw-callout">
  <p><strong>Learn pages are coming soon.</strong> We're putting the finishing touches on a series of guides covering seasonal patterns, AI scoring, the wave viewer, and how to read a TradeWave opportunity.</p>
</div>

<p>TradeWave is built around one idea: certain stocks repeat the same seasonal patterns year after year, and a 62-feature AI model can score how likely the next instance is to play out. The Learn section will walk you through the reasoning, the math, and the practical workflow — with worked examples on real tickers.</p>

<p>In the meantime, the fastest way to get a feel for the platform is to <a href="/app/">open the Wave Viewer</a>, pick any symbol from <a href="/patterns/">today's pattern list</a>, and read the chart. Every opportunity links to its historical proof.</p>

<p><a href="/">&larr; Back to home</a></p>
"""
    html = render_page(LEARN_TITLE, LEARN_SUBTITLE, body, None)
    return html, {
        "src": "(placeholder — WP source intentionally not used)",
        "out": LEARN_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": None,
    }


def build_disclaimer() -> tuple[str, dict]:
    body = """
<p>TradeWave is a research and analysis platform. We are not a registered investment adviser, broker-dealer, or financial planner. Read this page in full before acting on anything you find on the site.</p>

<h2>Not investment advice</h2>
<p>All content on TradeWave — including seasonal patterns, AI scores, scorecards, daily picks, opportunity lists, charts, and any commentary or articles — is provided for informational and educational purposes only. Nothing on TradeWave is a recommendation, solicitation, or offer to buy or sell any security, derivative, or other financial instrument.</p>

<h2>Past performance does not guarantee future results</h2>
<p>Historical seasonal patterns may not repeat. Markets evolve. Statistical edges that held for the last 10, 20, or 30 years can break in the next 10. The probability scores, win rates, and historical returns shown on TradeWave are computed from the data available at the time of analysis and are not guarantees of any future outcome.</p>

<h2>Investing involves risk</h2>
<p>The value of any investment can go up or down, and you may lose some or all of the money you invest. Before acting on any information from TradeWave, consider whether it is appropriate for your personal financial situation, risk tolerance, and investment objectives — and consult a licensed financial professional.</p>

<h2>No liability</h2>
<p>TradeWave, Tara Data Research LLC, and their operators, employees, and affiliates are not liable for any decisions you make based on the content of this site or for any losses, costs, or damages — direct or indirect — arising from your use of the platform. You are solely responsible for your own investment decisions.</p>

<h2>Data accuracy</h2>
<p>While we make best efforts to use accurate and up-to-date data from licensed providers, occasional errors, missing data points, corporate-action adjustments, and survivorship-bias gaps may occur. We do not warrant the completeness or accuracy of any specific data point, score, or backtest result.</p>

<h2>Forward-looking statements</h2>
<p>Articles and analysis published on TradeWave or its companion site Seasonal Market News may contain forward-looking statements about price movements, sectors, or economic conditions. These statements reflect the author's view at the time of writing and are not predictions. Conditions change. We may not update older content as new information becomes available.</p>

<h2>Third-party content</h2>
<p>TradeWave may link to or display content from third-party sources (news outlets, data providers, AI research tools). We do not endorse third-party content and are not responsible for its accuracy or for actions you take based on it.</p>

<p><a href="/">&larr; Back to home</a></p>
"""
    html = render_page(DISCLAIMER_TITLE, DISCLAIMER_SUBTITLE, body, TODAY_ISO)
    return html, {
        "src": "(authored in generator — single source of truth)",
        "out": DISCLAIMER_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": TODAY_ISO,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_output(out_name: str, html: str) -> None:
    """Write HTML to /var/www/tradewave/<out_name>, preserving flask:flask:644."""
    target = OUTPUT_DIR / out_name
    target.write_text(html, encoding="utf-8")  # we run AS flask via sudo wrapper


def main() -> int:
    if not SRC_DIR.is_dir():
        print(f"ERROR: source dir {SRC_DIR} not found", file=sys.stderr)
        return 2
    if not OUTPUT_DIR.is_dir():
        print(f"ERROR: output dir {OUTPUT_DIR} not found", file=sys.stderr)
        return 2

    print("TradeWave text-page generator (F4)")
    print(f"  src:    {SRC_DIR}")
    print(f"  out:    {OUTPUT_DIR}")
    print()

    summary = []
    for out_name, title, src_id, subtitle in PAGES:
        print(f"  building {out_name} from page_{src_id}.html ({title})...")
        html, info = build_legal_page(out_name, title, src_id, subtitle)
        write_output(out_name, html)
        summary.append(info)
        print(f"    raw {info['raw_size']:>7} -> stripped {info['stripped_size']:>7} -> wrapped {info['wrapped_size']:>7} bytes")

    print(f"  building {DISCLAIMER_FILENAME} (authored)...")
    html, info = build_disclaimer()
    write_output(DISCLAIMER_FILENAME, html)
    summary.append(info)
    print(f"    authored    -> wrapped {info['wrapped_size']:>7} bytes")

    print(f"  building {LEARN_FILENAME} (placeholder)...")
    html, info = build_learn_placeholder()
    write_output(LEARN_FILENAME, html)
    summary.append(info)
    print(f"    placeholder -> wrapped {info['wrapped_size']:>7} bytes")

    print()
    print("Done.")
    for s in summary:
        print(f"  {s['out']:>16} {s['wrapped_size']:>7} bytes  src={s['src']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
