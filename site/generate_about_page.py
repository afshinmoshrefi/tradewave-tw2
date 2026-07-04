#!/usr/bin/env python3
"""
TradeWave About Page Generator (TW2)

Source notes
------------
The .151 source `/home/flask/blog/generate_about_page.py` was for
SeasonalMarketNews (uses config.news_root_folder, _inject_site_wrapper).
The raw WP content at /home/afshin/wp-pages/page_28.html is dated TradeSeasonals
(2022/2023 era, pre-rebrand) and full of Divi shortcodes.

Resolution: build a clean TW2-branded About page using the same founder-bio
structure that Afshin authored for SMN, with TradeWave wording, schema.org
Person LD, and the TW2 unified header partial.

Usage:
    python generate_about_page.py
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, '/home/flask')
import config

OUTPUT_DIR = config.web_root_dir
OUTPUT_FILENAME = 'about.html'
HEADER_PARTIAL = '/home/flask/site/templates/_tw_header.html'

CANONICAL = config.domain_root + 'about.html'

# Index only on prod; dev/staging stay noindex (same ENABLE_SEO pattern as
# generate_home_page.py - env-driven so the prod build flips it on automatically
# instead of relying on a manual edit before launch).
ENABLE_SEO = os.environ.get('TW2_ENV', '').strip().lower() == 'prod'
ROBOTS_CONTENT = 'index, follow' if ENABLE_SEO else 'noindex, nofollow'


def build_html():
    person_ld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Afshin Moshrefi",
        "jobTitle": "Founder and Quantitative Researcher",
        "email": "mailto:afshin@tradewave.ai",
        "url": "https://moshrefi.com/",
        "image": "https://moshrefi.com/assets/img/afshin-1024.webp",
        "worksFor": {
            "@type": "Organization",
            "name": "Tara Data Research LLC",
            "url": "https://taradataresearch.com/",
        },
        "sameAs": [
            "https://moshrefi.com/",
            config.domain_root,
            "https://seasonalmarketnews.com/",
            "https://100yearprophecy.com/",
        ],
        "knowsAbout": [
            "Quantitative finance",
            "Seasonal market analysis",
            "Machine learning",
            "Financial data systems",
            "Presidential election cycle patterns",
        ],
    }
    person_ld_str = json.dumps(person_ld, indent=2)
    year = datetime.now().year

    header_html = ''
    if os.path.isfile(HEADER_PARTIAL):
        with open(HEADER_PARTIAL) as f:
            header_html = f.read()

    head = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>About TradeWave - Afshin Moshrefi, Tara Data Research</title>
  <meta name="description" content="TradeWave is built by Afshin Moshrefi at Tara Data Research LLC. AI-scored seasonal market patterns across stocks, ETFs, indices, futures, forex, and bonds.">
  <link rel="canonical" href="{CANONICAL}">
  <meta name="robots" content="{ROBOTS_CONTENT}">
  <link rel="icon" type="image/png" href="{config.tw_favicon}">

  <meta property="og:locale" content="en_US">
  <meta property="og:type" content="profile">
  <meta property="og:title" content="About TradeWave - Afshin Moshrefi">
  <meta property="og:description" content="The founder, the research, and the methodology behind TradeWave.">
  <meta property="og:url" content="{CANONICAL}">
  <meta property="og:image" content="https://moshrefi.com/assets/img/afshin-1024.webp">
  <meta property="og:site_name" content="TradeWave">
  <meta name="twitter:card" content="summary_large_image">

  <script type="application/ld+json">
{person_ld_str}
  </script>

  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: rgb(15,10,21);
      --bg-secondary: rgb(25,22,35);
      --bg-card: #0c1225;
      --text-primary: #ffffff;
      --text-secondary: #9ca3af;
      --text-muted: #6b7280;
      --accent: #6366f1;
      --accent-hover: #818cf8;
      --border: #1f2937;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-primary); color: var(--text-primary); line-height: 1.65; }}
    .container {{ max-width: 800px; margin: 0 auto; padding: 0 24px; }}
    .about-hero {{ display: flex; align-items: flex-start; gap: 28px;
      padding: 56px 0 28px; }}
    .about-portrait {{ width: 160px; height: auto; border-radius: 12px; flex-shrink: 0;
      box-shadow: 0 12px 32px rgba(99,102,241,0.18); }}
    .about-hero h1 {{ font-size: 36px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 8px; }}
    .about-role {{ color: var(--text-secondary); font-size: 15px; margin-bottom: 6px; }}
    .about-contact a {{ color: var(--accent); text-decoration: none; }}
    .about-contact a:hover {{ color: var(--accent-hover); }}
    .about-body h2 {{ margin-top: 36px; margin-bottom: 12px; font-size: 22px;
      font-weight: 700; letter-spacing: -0.2px; }}
    .about-body p, .about-body li {{ color: var(--text-primary);
      font-size: 16px; margin-bottom: 14px; }}
    .about-body .direct-answer {{ color: var(--text-secondary); font-size: 16px; }}
    .about-body ul {{ padding-left: 24px; margin-bottom: 14px; }}
    .about-body li {{ margin-bottom: 8px; }}
    .about-body a {{ color: var(--accent); text-decoration: none; }}
    .about-body a:hover {{ color: var(--accent-hover); }}
    .methodology-note {{ margin-top: 36px; padding: 24px;
      background: var(--bg-secondary); border: 1px solid var(--border);
      border-radius: 12px; }}
    .methodology-note h2 {{ margin-top: 0; }}
    .about-foot {{ padding: 32px 0 64px; color: var(--text-muted);
      font-size: 12px; text-align: center; }}
    .about-foot a {{ color: var(--accent); text-decoration: none; }}
    @media (max-width: 540px) {{
      .about-hero {{ flex-direction: column; align-items: center; text-align: center; }}
    }}
  </style>
</head>
<body>
'''

    body = f'''
  <div class="container">

    <div class="about-hero">
      <img
        src="https://moshrefi.com/assets/img/afshin-640.webp"
        srcset="https://moshrefi.com/assets/img/afshin-640.webp 640w, https://moshrefi.com/assets/img/afshin-1024.webp 1024w"
        sizes="(max-width: 600px) 120px, 160px"
        width="160" height="215"
        alt="Afshin Moshrefi"
        class="about-portrait">
      <div>
        <h1>Afshin Moshrefi</h1>
        <p class="about-role">Founder, Tara Data Research LLC &middot; Quantitative Researcher</p>
        <p class="about-contact"><a href="mailto:afshin@tradewave.ai">afshin@tradewave.ai</a></p>
      </div>
    </div>

    <article class="about-body">
      <p>
        Afshin Moshrefi is the founder-engineer and quantitative researcher behind
        <a href="{config.domain_root}">TradeWave.ai</a> and
        <a href="https://seasonalmarketnews.com/">Seasonal Market News</a>, operated under
        <a href="https://taradataresearch.com/">Tara Data Research LLC</a>.
        TradeWave is a research platform that detects repeating seasonal patterns in the
        market - the way a stock or index has tended to move at the same time of year, or
        across the four-year election cycle. You choose how far back to look, from 1 to 99
        years - the major indices carry up to 98 years of actual price history - and judge
        the pattern for yourself. It covers US stocks, ETFs, indices,
        futures, forex, and government bonds, and adds an AI win-probability score from a
        62-feature model trained on 34.7 million data points. You can reach it on the web
        or ask for it inside ChatGPT and Claude.
      </p>

      <h2>What does TradeWave research?</h2>
      <p class="direct-answer">
        Repeating seasonal patterns, how those patterns behave in different market
        conditions, and where the four-year presidential election cycle fits in. Every
        pattern is defined, measured, and tested over the exact lookback window you pick.
        The point is evidence you can check, not narrative you have to take on faith.
      </p>

      <h2>Why is this different from traditional market analysis?</h2>
      <p class="direct-answer">
        It is built like an open ledger: every number traces back to the price history it
        came from, and you set the window and read the result yourself. We would rather be
        audited than believed, so vague forecasts you cannot test are left out by design.
        For an active trader, that means a seasonal pattern you can size with conviction
        because you checked it; for an institution, a research input that survives compliance
        and due diligence because every figure is reproducible.
      </p>

      <h2>Background</h2>
      <p>
        Moshrefi&rsquo;s career spans software engineering, invention, and applied
        machine learning across multiple industries:
      </p>
      <ul>
        <li>Built an early medical image management platform adopted across gastroenterology, dermatology, and dentistry.</li>
        <li>Created InstantWeb in the late 1990s, a website generator that allowed users to publish a web presence in minutes, years before mainstream blog-based builders became common.</li>
        <li>At Verizon, authored 16 invention disclosures, including work related to video communication over conventional telephony infrastructure.</li>
        <li>Began focused machine learning work in 2013 and completed formal training by 2017.</li>
        <li>Worked as an AI researcher in medical coding, developing production ML systems for real-world use.</li>
        <li>TradeWave began as a personal research project and became a platform once the patterns proved consistent and repeatable across time.</li>
      </ul>

      <h2>Published Work</h2>
      <p>
        Moshrefi is the author of
        <a href="https://www.amazon.com/dp/B0F1VG2NMK" target="_blank" rel="noopener"><em>The 100-Year Pattern</em></a>,
        a research-driven book documenting a long-horizon seasonal market pattern and the framework
        used to test it across regimes. The book is a public explanation of the thesis behind
        TradeWave&rsquo;s seasonality and election-cycle research.
      </p>

      <h2>Products</h2>
      <ul>
        <li><a href="{config.domain_root}">TradeWave.ai</a> - AI-scored seasonal pattern research for US stocks, ETFs, indices, futures, forex, and bonds, with a 1 to 99 year lookback you control and access inside ChatGPT and Claude.</li>
        <li><a href="https://seasonalmarketnews.com/">Seasonal Market News</a> - Institutional-style market news grounded in measurable seasonal history.</li>
        <li><a href="https://taradataresearch.com/">Tara Data Research LLC</a> - Parent company for all research and product work.</li>
      </ul>

      <section class="methodology-note">
        <h2>About the data behind TradeWave</h2>
        <p>
          Every seasonal pattern is computed in-house from end-of-day price history,
          with up to 98 years of data available for the major indices. The win-probability
          score comes from a 62-feature gradient-boosted model - many small decision trees
          stacked into one - tested on 8 years of data it never saw in training, so the
          results reflect performance on unseen years rather than a fit to the past. Nothing
          here is investment advice; it is research you are meant to verify. See the full
          <a href="/methodology">methodology</a> and the
          <a href="/research.html">research page</a> for the details.
        </p>
      </section>

    </article>

    <div class="about-foot">
      &copy; {year} Tara Data Research LLC &middot;
      <a href="/methodology">Methodology</a> &middot;
      <a href="/research.html">Research</a> &middot;
      <a href="/patterns/">Tickers</a> &middot;
      <a href="/app/">Wave Viewer</a>
      <p style="margin-top:14px;">
        TradeWave is a research platform. It is not a brokerage and does not execute trades.
        All data is historical and for informational and educational purposes only.
        Past performance does not guarantee future results.
      </p>
    </div>

  </div>
</body>
</html>
'''
    return head + header_html + body


def main():
    html = build_html()
    out = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Generated: {out}')
    print(f'Size: {len(html)} bytes')


if __name__ == '__main__':
    main()
