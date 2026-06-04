#!/usr/bin/env python3
"""
TradeWave 2 - text-page generator (F4).

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
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from text_utils import no_em_dash  # noqa: E402

sys.path.insert(0, "/home/flask")
import config  # noqa: E402  - per-env values (TURNSTILE_SITE_KEY) baked at gen time

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
LEARN_SUBTITLE = "Guides, tutorials, and methodology - coming soon."

DISCLAIMER_FILENAME = "disclaimer.html"
DISCLAIMER_TITLE = "Financial Disclaimer"
DISCLAIMER_SUBTITLE = "What TradeWave is, what it isn't, and how to read what we publish."

CONTACT_FILENAME = "contact.html"
CONTACT_TITLE = "Contact"
CONTACT_SUBTITLE = "Reach out - we read every email."
CONTACT_EMAIL = "help@tradewave.ai"

# --- Affiliate / partner program page (authored) ---------------------------
AFFILIATE_FILENAME = "affiliate.html"
AFFILIATE_TITLE = "Affiliate Program"
AFFILIATE_SUBTITLE = (
    "Earn recurring commission introducing your audience to seasonal-pattern "
    "trading - and give them a deal worth sharing."
)
# Public-facing program terms. Once this page is live these are a commitment;
# change them here (single source of truth) and re-run the generator.
AFF_COMMISSION = "30%"                       # recurring commission to the partner
AFF_COMMISSION_TERM = "for as long as your referral stays subscribed"
AFF_AUDIENCE_DISCOUNT = "20%"                # discount the partner's audience gets
AFF_AUDIENCE_DISCOUNT_TERM = "for their first year"
AFF_PAYOUT_CADENCE = "monthly"
PARTNER_EMAIL = "help@tradewave.ai"
PARTNER_SUBJECT = "Affiliate Partner Application"

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
    # The dumps contain literal "\n" rather than newlines - flatten.
    s = LITERAL_NEWLINE_RE.sub("\n", s)
    # Collapse stacked &nbsp; placeholders that the Divi hero left behind.
    s = NBSP_RUN_RE.sub("", s)
    # Rewrite legacy contact link to TW2's home so we don't ship dangling URLs.
    s = s.replace("https://tradeseasonals/contact", "/contact.html")
    s = s.replace("https://tradeseasonals.com", "https://tradewave.ai")
    return s.strip()


# Last-updated date the generator stamps on every legal page. Bump this
# whenever the content of Terms / Privacy / Disclaimer changes.
LEGAL_LAST_UPDATED = "January 15, 2026"

# Appended to the Privacy Policy only (see build_legal_page). Discloses the
# first-party referral cookie (tw_ref) the affiliate program sets. Factual +
# minimal: no third-party / advertising trackers, so no consent banner needed.
PRIVACY_COOKIE_NOTE = """
<h2>Cookies and referral tracking</h2>
<p>TradeWave uses a small number of first-party cookies that are essential to running
the service, such as keeping you signed in. If you arrive through a partner or affiliate
link, we also store a single first-party cookie named <code>tw_ref</code> that remembers
only that partner's referral code, so the partner who introduced you is credited if you
subscribe. It stores nothing but that code, expires after 60 days, and is never shared
with third parties. We do not use third-party advertising or cross-site tracking cookies.
You can clear these cookies at any time in your browser settings.</p>
"""


def tw_rebrand(s: str) -> str:
    """Rewrite TW1-era references (TradeSeasonals, old company name and
    address, third-party brand mentions) into TW2 equivalents. Runs after
    the WP markup strip so it operates on prose, not Divi attribute strings.
    """
    # Old company name + street address → current LLC + Boston address.
    # Update both segments together when the LLC moves.
    s = re.sub(
        r"Tara Research LLC,\s*25 Storey Ave Ste 8\s*-\s*PMB 111\s*"
        r"Newburyport,\s*MA\s*01950",
        "Tara Data Research LLC, Government Center, "
        "1 Washington Mall #1129, Boston, MA 02108",
        s,
    )
    # Catch any remaining bare references to the old LLC name.
    s = s.replace("Tara Research LLC", "Tara Data Research LLC")

    # Brand rename. Order matters: the longest variants first so a partial
    # match doesn't leave half a word behind.
    s = s.replace("TradeSeasonals.com", "TradeWave.ai")
    s = s.replace("tradeseasonals.com", "tradewave.ai")
    s = s.replace("TradeSeasonals", "TradeWave")
    s = s.replace("tradeseasonals", "tradewave")
    s = re.sub(r"\bTrade Seasonals\b", "TradeWave", s)
    s = re.sub(r"\btrade seasonals\b", "tradewave", s, flags=re.I)

    # Third-party brand contamination from the original WP source.
    # The "Barchart Content" clause was a copy-paste from a Barchart TOS
    # template - TradeWave doesn't redistribute Barchart data.
    s = s.replace("Barchart Content", "TradeWave Content")
    s = s.replace("Barchart", "TradeWave")

    # Typos in the original Financial Disclaimer prose.
    s = s.replace("investement adviser", "investment adviser")
    s = s.replace("unintended erros", "unintended errors")

    return s


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
  <title>{title} - TradeWave</title>
  <meta name="description" content="{subtitle}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://tradewave.ai/{title_to_filename(title)}">
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="shortcut icon" type="image/png" href="/favicon.png">
  <link rel="apple-touch-icon" href="/favicon.png">
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
    <a href="/contact.html">Contact</a>
    <a href="/affiliate">Affiliates</a>
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
        "Contact": "contact.html",
        "Affiliate Program": "affiliate.html",
    }.get(title, title.lower().replace(" ", "-") + ".html")


# ---------------------------------------------------------------------------
# Per-page builders
# ---------------------------------------------------------------------------

# Match a "<p>...Last Updated: <date>...</p>" block, tolerant of inline
# tags (<span>, <strong>, <b>, etc.) between the <p> and the text.
# Non-greedy + DOTALL keeps it from spanning across multiple paragraphs.
LAST_UPDATED_RE = re.compile(
    r"<p>.*?Last\s+[Uu]pdated:.*?</p>",
    re.I | re.DOTALL,
)


def build_legal_page(out_name: str, title: str, src_id: str, subtitle: str) -> tuple[str, dict]:
    src = SRC_DIR / f"page_{src_id}.html"
    raw = src.read_text(encoding="utf-8")
    stripped = strip_wp_markup(raw)
    # Apply TW2 rebrand (TradeSeasonals - > TradeWave, old address, etc.).
    stripped = tw_rebrand(stripped)
    # Hard rule: no em dashes in any TradeWave content.
    stripped = no_em_dash(stripped)
    # Drop any stale "Last updated:" line from the source body - we stamp
    # a single canonical date below so all three legal pages stay in sync.
    stripped = LAST_UPDATED_RE.sub("", stripped, count=1)
    last_updated = LEGAL_LAST_UPDATED
    # Disclose the first-party referral cookie on the privacy page only.
    if out_name == "privacy.html":
        stripped = stripped + PRIVACY_COOKIE_NOTE
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

<p>TradeWave is built around one idea: certain stocks repeat the same seasonal patterns year after year, and a 62-feature AI model can score how likely the next instance is to play out. The Learn section will walk you through the reasoning, the math, and the practical workflow - with worked examples on real tickers.</p>

<p>In the meantime, the fastest way to get a feel for the platform is to <a href="/app/">open the Wave Viewer</a>, pick any symbol from <a href="/patterns/">today's pattern list</a>, and read the chart. Every opportunity links to its historical proof.</p>

<p><a href="/">&larr; Back to home</a></p>
"""
    html = render_page(LEARN_TITLE, LEARN_SUBTITLE, body, None)
    return html, {
        "src": "(placeholder - WP source intentionally not used)",
        "out": LEARN_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": None,
    }


def build_contact() -> tuple[str, dict]:
    body = f"""
<style>
  .contact-intro {{ text-align:center; max-width:640px; margin:0 auto 40px; color:var(--text-dim); font-size:17px; }}
  .contact-grid {{ display:flex; justify-content:center; margin:0 0 48px; }}
  .contact-grid > .contact-card {{ width:100%; max-width:480px; }}
  .contact-card {{
    background: linear-gradient(180deg, rgba(139,92,246,0.06) 0%, rgba(99,102,241,0.03) 100%);
    border: 1px solid rgba(139,92,246,0.18);
    border-radius: 14px;
    padding: 28px 28px 24px;
    transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
  }}
  .contact-card:hover {{
    transform: translateY(-2px);
    border-color: rgba(139,92,246,0.36);
    box-shadow: 0 12px 32px rgba(139,92,246,0.12);
  }}
  .contact-card .icon {{
    width:42px; height:42px; border-radius:10px;
    display:flex; align-items:center; justify-content:center;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    color:#fff; font-size:20px; margin-bottom:14px;
  }}
  .contact-card h3 {{ margin:0 0 8px; font-size:18px; font-weight:700; color:#fff; }}
  .contact-card .lead {{ font-size:18px; margin:6px 0 4px; color:#fff; font-weight:600; }}
  .contact-card .meta {{ font-size:13px; color:var(--text-muted); margin:0 0 14px; line-height:1.6; }}
  .contact-card .cta {{
    display:inline-block; font-size:14px; font-weight:600;
    color:#a78bfa; text-decoration:none; margin-top:6px;
  }}
  .contact-card .cta:hover {{ color:#c4b5fd; }}
  .contact-card .addr {{ font-size:14px; color:var(--text); line-height:1.7; margin:0; }}

  .contact-pills {{ display:flex; flex-wrap:wrap; gap:10px; margin:0 0 48px; }}
  .contact-pills a {{
    display:inline-flex; align-items:center; padding:9px 16px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 999px;
    color: var(--text); text-decoration: none;
    font-size: 14px; font-weight: 500;
    transition: all 140ms ease;
  }}
  .contact-pills a:hover {{
    background: rgba(139,92,246,0.14);
    border-color: rgba(139,92,246,0.4);
    color: #fff;
    transform: translateY(-1px);
  }}

  .contact-form {{
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 32px;
    margin: 0 0 16px;
  }}
  .contact-form .row {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }}
  .contact-form label {{ display:block; font-size:13px; font-weight:600; color:var(--text-dim); margin-bottom:6px; letter-spacing:0.02em; text-transform:uppercase; }}
  .contact-form input,
  .contact-form select,
  .contact-form textarea {{
    width:100%; box-sizing:border-box;
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 11px 14px;
    color: var(--text);
    font-size: 15px;
    font-family: inherit;
    transition: border-color 140ms ease, background 140ms ease;
  }}
  .contact-form input:focus,
  .contact-form select:focus,
  .contact-form textarea:focus {{
    outline: none;
    border-color: rgba(139,92,246,0.55);
    background: rgba(0,0,0,0.42);
  }}
  .contact-form textarea {{ resize: vertical; min-height: 140px; }}
  .contact-form .field {{ margin-bottom: 16px; }}
  .contact-form .submit-row {{ display:flex; align-items:center; gap:18px; margin-top:8px; }}
  .contact-form button {{
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    color: #fff; border: 0; border-radius: 8px;
    padding: 12px 28px;
    font-size: 15px; font-weight: 600; cursor: pointer;
    transition: transform 140ms ease, box-shadow 140ms ease;
  }}
  .contact-form button:hover {{ transform: translateY(-1px); box-shadow: 0 8px 24px rgba(139,92,246,0.25); }}
  .contact-form .form-note {{ font-size: 13px; color: var(--text-muted); margin: 0; }}

  .contact-faq {{ margin: 56px 0 0; }}
  .contact-faq h2 {{ text-align:center; }}
  .contact-faq .q {{ background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 16px 20px; margin-bottom: 10px; }}
  .contact-faq .q strong {{ display:block; color:#fff; margin-bottom:4px; font-size:15px; }}
  .contact-faq .q p {{ margin:0; font-size:14px; color:var(--text-dim); line-height:1.7; }}

  @media (max-width: 720px) {{
    .contact-form .row {{ grid-template-columns: 1fr; }}
    .contact-form {{ padding: 24px 20px; }}
  }}
</style>

<p class="contact-intro">We're a small team that reads every message. Pick a topic below for a faster response, or use the form to send us a note.</p>

<div class="contact-grid">
  <div class="contact-card">
    <div class="icon">@</div>
    <h3>Email us</h3>
    <p class="lead">{CONTACT_EMAIL}</p>
    <p class="meta">Typical response time: <strong>1 business day</strong>. For account or billing issues, include your account email so we can find you faster.</p>
    <a class="cta" href="mailto:{CONTACT_EMAIL}">Open email →</a>
  </div>
</div>

<h2>Pick a topic</h2>
<div class="contact-pills">
  <a href="mailto:{CONTACT_EMAIL}?subject=Bug%20report">Bug report</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Feature%20request">Feature request</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Billing%20question">Billing</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Account%20access">Account access</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Data%20accuracy">Data accuracy</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Institutional%20%2F%20API">Institutional / API</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Press%20inquiry">Press</a>
  <a href="mailto:{CONTACT_EMAIL}?subject=Other">Other</a>
</div>

<h2>Or write to us directly</h2>
<form class="contact-form" id="tw-contact-form" novalidate>
  <div class="row">
    <div class="field">
      <label for="cf-name">Your name</label>
      <input id="cf-name" name="name" type="text" required autocomplete="name" maxlength="200">
    </div>
    <div class="field">
      <label for="cf-email">Your email</label>
      <input id="cf-email" name="email" type="email" required autocomplete="email" maxlength="320">
    </div>
  </div>
  <div class="field">
    <label for="cf-topic">Topic</label>
    <select id="cf-topic" name="topic">
      <option value="bug">Bug report</option>
      <option value="feature">Feature request</option>
      <option value="billing">Billing question</option>
      <option value="account">Account access</option>
      <option value="data">Data accuracy</option>
      <option value="institutional">Institutional / API</option>
      <option value="press">Press inquiry</option>
      <option value="other">Other</option>
    </select>
  </div>
  <div class="field">
    <label for="cf-message">Message</label>
    <textarea id="cf-message" name="message" rows="6" required maxlength="8000" placeholder="Tell us what's on your mind..."></textarea>
  </div>

  <!-- Honeypot: hidden, never filled by humans. Bots fill every input; if this
       has a value the server silently treats the submit as success and drops it. -->
  <div aria-hidden="true" style="position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden;">
    <label for="cf-company">Company (leave blank)</label>
    <input id="cf-company" name="company" type="text" tabindex="-1" autocomplete="off">
  </div>

  <div class="cf-turnstile" data-sitekey="{config.TURNSTILE_SITE_KEY}" data-callback="twTurnstileOk" data-error-callback="twTurnstileErr" style="margin: 8px 0 14px;"></div>

  <div class="submit-row">
    <button type="submit" id="cf-submit">Send message</button>
    <p class="form-note">Typical reply within one business day.</p>
  </div>
  <div id="cf-status" class="cf-status" role="status" aria-live="polite"></div>
</form>

<style>
  .cf-status {{ margin-top: 14px; font-size: 14px; min-height: 1.4em; }}
  .cf-status.is-ok {{
    color: #c4f0c8;
    background: rgba(74, 222, 128, 0.08);
    border: 1px solid rgba(74, 222, 128, 0.28);
    border-radius: 8px;
    padding: 12px 14px;
  }}
  .cf-status.is-err {{
    color: #fecaca;
    background: rgba(248, 113, 113, 0.08);
    border: 1px solid rgba(248, 113, 113, 0.28);
    border-radius: 8px;
    padding: 12px 14px;
  }}
  .cf-status .ref {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 700; }}
</style>

<div class="contact-faq">
  <h2>Frequently asked</h2>
  <div class="q">
    <strong>How fast do you respond?</strong>
    <p>We aim to reply within one business day. Billing and account-access issues get triaged first.</p>
  </div>
  <div class="q">
    <strong>I think a chart or score is wrong - what should I send?</strong>
    <p>The ticker, the date, and a screenshot of what looks off. We'll re-run the data pipeline and either fix the bug or explain what you're seeing.</p>
  </div>
  <div class="q">
    <strong>Do you offer institutional or API access?</strong>
    <p>Yes - pricing depends on your use case and volume. Email us with a sentence or two about what you'd build and we'll send a tailored quote.</p>
  </div>
  <div class="q">
    <strong>Can I get a refund?</strong>
    <p>Subscription fees are generally non-refundable, but write us if your situation is unusual - we review case-by-case.</p>
  </div>
</div>

<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<script>
(function() {{
  var form   = document.getElementById('tw-contact-form');
  var status = document.getElementById('cf-status');
  var submit = document.getElementById('cf-submit');
  var token  = null;

  // Turnstile callbacks - widget calls these once we have (or lose) a token.
  window.twTurnstileOk  = function(t) {{ token = t; }};
  window.twTurnstileErr = function() {{ token = null; }};

  function showOk(publicId) {{
    status.className = 'cf-status is-ok';
    if (publicId) {{
      status.innerHTML = 'Got it - your message landed. Reference: <span class="ref">' +
                         publicId + '</span>. We have also emailed you a confirmation.';
    }} else {{
      status.textContent = 'Thanks - your message has been received.';
    }}
    form.querySelectorAll('input, select, textarea, button').forEach(function(el) {{ el.disabled = true; }});
  }}

  function showErr(msg) {{
    status.className = 'cf-status is-err';
    status.textContent = msg;
    submit.disabled = false;
    submit.textContent = 'Send message';
  }}

  var ERR_MESSAGES = {{
    name_invalid:    'Please enter your name.',
    email_invalid:   'Please enter a valid email address.',
    topic_invalid:   'Please pick a topic.',
    message_invalid: 'Please add a message (or shorten it if it is very long).',
    captcha_failed:  'The verification check did not pass. Please reload the page and try again.',
    server_error:    'Something went wrong on our end. Please try again in a moment, or email help@tradewave.ai directly.',
  }};

  form.addEventListener('submit', function(e) {{
    e.preventDefault();
    status.className = 'cf-status';
    status.textContent = '';

    if (!token) {{
      showErr('One moment - waiting for the verification check to finish, then try again.');
      return;
    }}

    submit.disabled = true;
    submit.textContent = 'Sending...';

    var payload = {{
      name:    document.getElementById('cf-name').value.trim(),
      email:   document.getElementById('cf-email').value.trim(),
      topic:   document.getElementById('cf-topic').value,
      message: document.getElementById('cf-message').value.trim(),
      company: document.getElementById('cf-company').value,  // honeypot
      turnstile_token: token,
    }};

    fetch('/api/contact', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload),
    }}).then(function(r) {{
      return r.json().then(function(j) {{ return {{ status: r.status, body: j }}; }});
    }}).then(function(res) {{
      if (res.status >= 200 && res.status < 300 && res.body && res.body.ok) {{
        showOk(res.body.public_id);
      }} else {{
        var code = (res.body && res.body.error) || 'server_error';
        showErr(ERR_MESSAGES[code] || ERR_MESSAGES.server_error);
        if (window.turnstile) {{ try {{ window.turnstile.reset(); }} catch (e) {{}} }}
        token = null;
      }}
    }}).catch(function() {{
      showErr(ERR_MESSAGES.server_error);
      if (window.turnstile) {{ try {{ window.turnstile.reset(); }} catch (e) {{}} }}
      token = null;
    }});
  }});
}})();
</script>
"""
    html = render_page(CONTACT_TITLE, CONTACT_SUBTITLE, body, None)
    return html, {
        "src": "(authored in generator - single source of truth)",
        "out": CONTACT_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": None,
    }


def build_affiliate() -> tuple[str, dict]:
    # CSS kept as a plain (non-f) string so literal braces need no escaping.
    css = """
<style>
  .aff-lead { font-size:18px; color:var(--text-dim); max-width:760px; margin:0 0 8px; }
  .aff-cards, .aff-steps, .aff-terms { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin:24px 0; }
  .aff-card { background:linear-gradient(180deg, rgba(139,92,246,0.06), rgba(99,102,241,0.03)); border:1px solid rgba(139,92,246,0.18); border-radius:14px; padding:24px; }
  .aff-card h3, .aff-step h3 { margin:0 0 8px; font-size:17px; color:#fff; }
  .aff-card p, .aff-step p { margin:0; font-size:14px; color:var(--text-dim); line-height:1.65; }
  .aff-step { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:24px; }
  .aff-step .n { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border-radius:50%; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; font-weight:700; margin-bottom:12px; }
  .aff-terms .t { text-align:center; background:rgba(139,92,246,0.08); border:1px solid rgba(139,92,246,0.25); border-radius:14px; padding:28px 16px; }
  .aff-terms .big { display:block; font-size:30px; font-weight:800; background:linear-gradient(135deg,#6366f1,#a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-bottom:8px; }
  .aff-terms .lbl { font-size:13px; color:var(--text-dim); line-height:1.5; }
  .aff-faq .q { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:16px 20px; margin-bottom:10px; }
  .aff-faq .q strong { display:block; color:#fff; margin-bottom:4px; font-size:15px; }
  .aff-faq .q p { margin:0; font-size:14px; color:var(--text-dim); line-height:1.7; }
  .aff-cta-wrap { text-align:center; margin:48px 0 8px; padding:36px 24px; background:linear-gradient(135deg, rgba(99,102,241,0.12), rgba(168,85,247,0.10)); border:1px solid rgba(139,92,246,0.25); border-radius:16px; }
  .aff-cta-wrap h2 { margin:0 0 8px; }
  .aff-cta-wrap > p { color:var(--text-dim); margin:0 0 20px; }
  .aff-cta-wrap .aff-cta { display:inline-block; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; text-decoration:none; font-weight:700; font-size:16px; padding:14px 32px; border-radius:10px; transition:transform 140ms ease, box-shadow 140ms ease; }
  .aff-cta-wrap .aff-cta:hover { transform:translateY(-1px); box-shadow:0 10px 28px rgba(139,92,246,0.3); }
  .aff-cta-note { font-size:13px; color:var(--text-muted); margin:16px 0 0; }
  @media (max-width:720px) { .aff-cards, .aff-steps, .aff-terms { grid-template-columns:1fr; } }
</style>
"""
    mailto = f"mailto:{PARTNER_EMAIL}?subject={quote(PARTNER_SUBJECT)}"
    body = css + f"""
<p class="aff-lead">TradeWave helps traders find stocks that repeat the same seasonal patterns year after year, then scores each setup with a 62-feature AI model. If you teach, write about, or build a community around trading, our affiliate program lets you earn recurring income introducing your audience to a tool they will actually use - while handing them a real discount.</p>

<h2>Why partners promote TradeWave</h2>
<div class="aff-cards">
  <div class="aff-card">
    <h3>A product your audience keeps</h3>
    <p>Seasonal patterns, AI scoring, and a daily pick that earn a place in a trader's routine. Referrals stick around - and your recurring commission with them.</p>
  </div>
  <div class="aff-card">
    <h3>A real deal to offer</h3>
    <p>Your code gives your audience {AFF_AUDIENCE_DISCOUNT} off {AFF_AUDIENCE_DISCOUNT_TERM}. You are not just selling them something - you are saving them money.</p>
  </div>
  <div class="aff-card">
    <h3>Recurring, not one and done</h3>
    <p>Earn {AFF_COMMISSION} commission {AFF_COMMISSION_TERM}. Build a base of referrals and your {AFF_PAYOUT_CADENCE} payout compounds.</p>
  </div>
</div>

<h2>How it works</h2>
<div class="aff-steps">
  <div class="aff-step">
    <span class="n">1</span>
    <h3>Apply</h3>
    <p>Tell us about your audience. We partner with a small, hand-picked group, so every partner gets personal attention.</p>
  </div>
  <div class="aff-step">
    <span class="n">2</span>
    <h3>Share your code</h3>
    <p>You get a unique code. Drop it in a video, newsletter, course, or community - it works anywhere, even spoken aloud.</p>
  </div>
  <div class="aff-step">
    <span class="n">3</span>
    <h3>Earn {AFF_PAYOUT_CADENCE}</h3>
    <p>When someone subscribes with your code, they save and you earn. We pay out {AFF_PAYOUT_CADENCE}.</p>
  </div>
</div>

<h2>What you earn</h2>
<div class="aff-terms">
  <div class="t"><span class="big">{AFF_COMMISSION}</span><span class="lbl">recurring commission<br>{AFF_COMMISSION_TERM}</span></div>
  <div class="t"><span class="big">{AFF_AUDIENCE_DISCOUNT} off</span><span class="lbl">for your audience<br>{AFF_AUDIENCE_DISCOUNT_TERM}</span></div>
  <div class="t"><span class="big">{AFF_PAYOUT_CADENCE}</span><span class="lbl">payouts<br>by PayPal or Wise</span></div>
</div>

<h2>Who we partner with</h2>
<p>The program is invite and application based. It is a strong fit if you reach traders through:</p>
<ul>
  <li>Trading coaching, mentorship, or courses</li>
  <li>A YouTube channel, podcast, or newsletter about the markets</li>
  <li>A trading community, Discord, or signals group</li>
  <li>Educational content on seasonality, technical analysis, or stock research</li>
</ul>

<h2>Frequently asked</h2>
<div class="aff-faq">
  <div class="q">
    <strong>How and when do I get paid?</strong>
    <p>We total the revenue from your referrals each period and pay your {AFF_COMMISSION} commission {AFF_PAYOUT_CADENCE}, by PayPal or Wise.</p>
  </div>
  <div class="q">
    <strong>How is a referral tracked?</strong>
    <p>Your audience enters your code at checkout. The discount is their incentive to use it, and it ties the subscription to you.</p>
  </div>
  <div class="q">
    <strong>Is there any cost to join?</strong>
    <p>No. The program is free to join - you only ever earn.</p>
  </div>
  <div class="q">
    <strong>Do I need a huge audience?</strong>
    <p>No. We care more about how engaged and relevant your audience is than how big it is. Tell us about it when you apply.</p>
  </div>
</div>

<div class="aff-cta-wrap">
  <h2>Apply to partner with us</h2>
  <p>Send us a note about you and your audience. We review every application personally.</p>
  <a class="aff-cta" href="{mailto}">Apply now →</a>
  <p class="aff-cta-note">Or email <a href="{mailto}">{PARTNER_EMAIL}</a> with the subject "{PARTNER_SUBJECT}".</p>
</div>
"""
    html = render_page(AFFILIATE_TITLE, AFFILIATE_SUBTITLE, body, None)
    return html, {
        "src": "(authored in generator - single source of truth)",
        "out": AFFILIATE_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": None,
    }


def build_disclaimer() -> tuple[str, dict]:
    body = """
<p>TradeWave is a research and analysis platform. We are not a registered investment adviser, broker-dealer, or financial planner. Read this page in full before acting on anything you find on the site.</p>

<h2>Not investment advice</h2>
<p>All content on TradeWave - including seasonal patterns, AI scores, scorecards, daily picks, opportunity lists, charts, and any commentary or articles - is provided for informational and educational purposes only. Nothing on TradeWave is a recommendation, solicitation, or offer to buy or sell any security, derivative, or other financial instrument.</p>

<h2>Past performance does not guarantee future results</h2>
<p>Historical seasonal patterns may not repeat. Markets evolve. Statistical edges that held for the last 10, 20, or 30 years can break in the next 10. The probability scores, win rates, and historical returns shown on TradeWave are computed from the data available at the time of analysis and are not guarantees of any future outcome.</p>

<h2>Investing involves risk</h2>
<p>The value of any investment can go up or down, and you may lose some or all of the money you invest. Before acting on any information from TradeWave, consider whether it is appropriate for your personal financial situation, risk tolerance, and investment objectives - and consult a licensed financial professional.</p>

<h2>No liability</h2>
<p>TradeWave, Tara Data Research LLC, and their operators, employees, and affiliates are not liable for any decisions you make based on the content of this site or for any losses, costs, or damages - direct or indirect - arising from your use of the platform. You are solely responsible for your own investment decisions.</p>

<h2>Data accuracy</h2>
<p>While we make best efforts to use accurate and up-to-date data from licensed providers, occasional errors, missing data points, corporate-action adjustments, and survivorship-bias gaps may occur. We do not warrant the completeness or accuracy of any specific data point, score, or backtest result.</p>

<h2>Forward-looking statements</h2>
<p>Articles and analysis published on TradeWave or its companion site Seasonal Market News may contain forward-looking statements about price movements, sectors, or economic conditions. These statements reflect the author's view at the time of writing and are not predictions. Conditions change. We may not update older content as new information becomes available.</p>

<h2>Third-party content</h2>
<p>TradeWave may link to or display content from third-party sources (news outlets, data providers, AI research tools). We do not endorse third-party content and are not responsible for its accuracy or for actions you take based on it.</p>

<p><a href="/">&larr; Back to home</a></p>
"""
    html = render_page(DISCLAIMER_TITLE, DISCLAIMER_SUBTITLE, body, LEGAL_LAST_UPDATED)
    return html, {
        "src": "(authored in generator - single source of truth)",
        "out": DISCLAIMER_FILENAME,
        "raw_size": 0,
        "stripped_size": len(body),
        "wrapped_size": len(html),
        "last_updated": LEGAL_LAST_UPDATED,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_output(out_name: str, html: str) -> None:
    """Write HTML to /var/www/tradewave/<out_name>, preserving flask:flask:644."""
    target = OUTPUT_DIR / out_name
    # Final defense against em dashes (forbidden in TradeWave content).
    html = no_em_dash(html)
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

    print(f"  building {CONTACT_FILENAME} (authored)...")
    html, info = build_contact()
    write_output(CONTACT_FILENAME, html)
    summary.append(info)
    print(f"    authored    -> wrapped {info['wrapped_size']:>7} bytes")

    print(f"  building {AFFILIATE_FILENAME} (authored)...")
    html, info = build_affiliate()
    write_output(AFFILIATE_FILENAME, html)
    summary.append(info)
    print(f"    authored    -> wrapped {info['wrapped_size']:>7} bytes")

    # Learn placeholder removed 2026-05-31 - real content now generated by
    # /home/flask/site/generate_learn.py (mirrors generate_insights.py).
    # See /home/flask/site/content/learn/*.md for source.

    print()
    print("Done.")
    for s in summary:
        print(f"  {s['out']:>16} {s['wrapped_size']:>7} bytes  src={s['src']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
