#!/usr/bin/env python3
"""
TradeWave site-level SEO/AEO files (TW2): robots.txt, sitemap.xml, llms.txt.

Writes into the web root (config.web_root_dir, /var/www/tradewave/ on the boxes):

  - robots.txt : Allow (prod) / Disallow (dev, staging) gated on ENABLE_SEO, same
    env pattern as generate_home_page.py. Lists all THREE sitemaps as absolute
    URLs in both cases (crawlers may still want to discover the sitemap even
    while disallowed, and it's useful for review tooling on dev/staging).
  - sitemap.xml: rebuilt FROM DISK every run - never a committed static artifact,
    because per-env content differs (e.g. the scorecard's featured picks). Style
    matches web/report_renderer.py:rebuild_report_sitemap and
    site/ticker_pages/generate_ticker_pages.py:write_sitemap. Owns the top-level
    marketing pages plus insights/, learn/, markets/. patterns/ and r/ have their
    own sitemaps (own writers - generate_ticker_pages.py, report_renderer.py) and
    are only LINKED from robots.txt here, never duplicated.
  - llms.txt  : a compact llmstxt.org-style map for LLM/agent readers.

Must run LAST in ops/regen_site.sh (after every other generator on this box) so
the sitemap reflects everything that generation pass just produced.

Usage (no arguments):
    /home/flask/venv/bin/python site/generate_seo_files.py
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/site/lib')
import config  # noqa: E402
from text_utils import no_em_dash  # noqa: E402

# Index only on prod; dev/staging stay noindex/disallowed (same ENABLE_SEO pattern
# as generate_home_page.py:187 - env-driven so the prod build flips it on
# automatically instead of relying on a manual edit before launch, which is what
# left tradewave.ai noindexed after cutover in the first place).
ENABLE_SEO = os.environ.get('TW2_ENV', '').strip().lower() == 'prod'

WEB_ROOT = Path(config.web_root_dir)
ROOT = config.domain_root  # trailing-slash absolute base, e.g. https://tw2-dev.trxstat.com/

# The three sitemaps that exist across the whole site. This one is written below;
# patterns/ and r/ are written by their own generators - listed here so robots.txt
# is the single discovery point for all of them.
SITEMAP_FILES = ['sitemap.xml', 'patterns/sitemap.xml', 'r/sitemap.xml']

# Top-level pages worth listing, only if present on disk. "home.html" is nginx's
# index for "/" (ops/nginx/sites-available/tradewave: `try_files /home.html =404;`
# at `location = /`), so it is emitted as the bare root URL, never "/home.html".
HOME_FILE = 'home.html'
TOP_LEVEL_PAGES = [
    'about.html', 'methodology.html', 'research.html', 'scorecard.html',
    'daily-ai-pick.html', 'affiliate.html', 'contact.html', 'privacy.html',
    'terms.html', 'disclaimer.html',
]

# Directories with their own article/page sets - every *.html one level deep (the
# chart/image subfolders don't match the glob). markets/ is the LIVE section dir
# (config.web_root_dir/markets, written by generate_security_pages.py); NOT
# _static/markets, the retired SMN-style path that dir-name still collides with.
# 404.html, home-ui-preview/, r/, and patterns/ are excluded by construction -
# nothing here ever scans those paths.
SECTION_DIRS = ['insights', 'learn', 'markets']


def _lastmod(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d')
    except OSError:
        return datetime.now().strftime('%Y-%m-%d')


def _page_title(path: Path) -> str:
    """First <title> in the file, minus any ' - TradeWave...' suffix; falls back
    to the filename stem."""
    try:
        import re
        head = path.read_text(encoding='utf-8', errors='ignore')[:2048]
        m = re.search(r'<title>(.*?)</title>', head, re.S)
        if m:
            return m.group(1).split(' - ')[0].split(' | ')[0].strip()
    except OSError:
        pass
    return path.stem.replace('-', ' ').title()


def build_markets_index() -> bool:
    """Write markets/index.html from the market pages on disk. The section never
    had an index (a bare /markets/ 403'd - verify_deploy flags it as a blocker),
    and the market pages themselves are SMN-coupled so this generator, which
    already scans the section for the sitemap, is the natural owner. From-disk
    like everything else here: pages that vanish drop off the index next run.
    Returns True if written (needed so the sitemap scan can include it)."""
    markets_dir = WEB_ROOT / 'markets'
    if not markets_dir.is_dir():
        return False
    pages = [p for p in sorted(markets_dir.glob('*.html')) if p.name != 'index.html']
    if not pages:
        return False
    items = '\n'.join(
        '      <li><a href="/markets/%s">%s</a></li>' % (p.name, _page_title(p))
        for p in pages)
    html = no_em_dash('''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Markets - TradeWave Seasonal Market Research</title>
  <meta name="description" content="Seasonal research hubs for the major markets TradeWave tracks - historical calendar-window behavior, shown year by year.">
  <link rel="canonical" href="%smarkets/">
  <style>
    body { margin:0; background:#0d1526; color:#e8edf6; font:16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    main { max-width:720px; margin:0 auto; padding:48px 24px; }
    h1 { font-size:32px; margin:0 0 8px; }
    p.sub { color:#9fb0c8; margin:0 0 32px; }
    ul { list-style:none; padding:0; }
    li { margin:0 0 12px; }
    a { color:#5eead4; text-decoration:none; font-size:18px; }
    a:hover { text-decoration:underline; }
    .home { display:inline-block; margin-top:32px; color:#9fb0c8; font-size:14px; }
  </style>
</head>
<body>
  <main>
    <h1>Markets</h1>
    <p class="sub">Seasonal research for the major markets TradeWave tracks - the historical record by calendar window, shown year by year.</p>
    <ul>
%s
    </ul>
    <a class="home" href="/">TradeWave home</a>
  </main>
</body>
</html>
''' % (ROOT, items))
    _write_atomic(markets_dir / 'index.html', html)
    print('markets/index.html   %d market pages listed' % len(pages))
    return True


def collect_urls():
    """Return [(loc, lastmod), ...] built from what's actually on this box's disk
    right now - the whole point being a stale/foreign-host entry can't survive a
    run, because nothing is carried over from a previous sitemap."""
    urls = []

    home = WEB_ROOT / HOME_FILE
    if home.is_file():
        urls.append((ROOT, _lastmod(home)))

    for name in TOP_LEVEL_PAGES:
        p = WEB_ROOT / name
        if p.is_file():
            urls.append((ROOT + name, _lastmod(p)))

    for sub in SECTION_DIRS:
        section_dir = WEB_ROOT / sub
        if not section_dir.is_dir():
            continue
        for html in sorted(section_dir.glob('*.html')):
            if html.name == 'index.html':
                loc = '%s%s/' % (ROOT, sub)  # canonical dir URL - no duplicate twin at /sub/index.html
            else:
                loc = '%s%s/%s' % (ROOT, sub, html.name)
            urls.append((loc, _lastmod(html)))

    return urls


def build_sitemap(urls) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in urls:
        lines.append('  <url>')
        lines.append('    <loc>%s</loc>' % loc)
        lines.append('    <lastmod>%s</lastmod>' % lastmod)
        lines.append('  </url>')
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


def build_robots() -> str:
    directive = 'Allow: /' if ENABLE_SEO else 'Disallow: /'
    lines = [
        '# TradeWave 2 - robots.txt',
        '# GENERATED by site/generate_seo_files.py on every regen (per-env) - hand',
        '# edits here will be OVERWRITTEN on the next run. Edit the generator instead.',
        '#',
        '# Dev/staging stay blocked (Disallow) until TW2_ENV=prod flips this to Allow;',
        '# the home page carries a matching noindex meta so the two never disagree.',
        '',
        'User-agent: *',
        directive,
        '',
    ]
    lines += ['Sitemap: %s%s' % (ROOT, f) for f in SITEMAP_FILES]
    return '\n'.join(lines) + '\n'


def _developers_line():
    """Best-effort: the developer-portal + MCP link. portal_urls raises on staging/
    prod if TW2_DEVELOPERS_PUBLIC_HOST/TW2_MCP_PUBLIC_HOST are unset (a real config
    error there - never leak a dev host into a published artifact). llms.txt is a
    nice-to-have, not the SEO-critical file, so we omit the line rather than
    hardcode a guess or fail the whole run over it. portal_urls raises AT IMPORT
    (module-level _host()), so the import must live inside this try - a
    top-of-file import would kill the whole generator on prod, where the portal
    hosts are legitimately unset (API/MCP ship dark there)."""
    try:
        import portal_urls  # noqa: E402
        return '- Developers - API and MCP for AI agents: %s (MCP endpoint: %s)' % (
            portal_urls.PORTAL_URL, portal_urls.MCP_URL)
    except Exception as e:
        print('  (skipping llms.txt Developers line: %s)' % e, file=sys.stderr)
        return None


def build_llms() -> str:
    intro = no_em_dash(
        "TradeWave is seasonal stock-market research. It counts how often a stock rose in a "
        "specific calendar window across decades of history and shows the full year-by-year "
        "record - the evidence, not a prediction. An ML model calibrates how strong each "
        "historical pattern is right now. A public forward scorecard logs every daily "
        "featured pick before the outcome is known and tracks it to completion, wins and "
        "losses alike."
    )
    lines = [
        '# TradeWave',
        '',
        intro,
        '',
        '## Sections',
        '- Methodology: %smethodology.html' % ROOT,
        '- Scorecard - the public forward track record: %sscorecard.html' % ROOT,
        '- Daily-Pick Ledger - the scorecard track record as machine-citable JSON: %sdata/daily-pick-ledger.json' % ROOT,
        '- Seasonal Patterns by Ticker: %spatterns/' % ROOT,
        '- Markets: %smarkets/' % ROOT,
        '- Insights: %sinsights/' % ROOT,
        '- Learn: %slearn/' % ROOT,
        '- Daily AI Pick: %sdaily-ai-pick.html' % ROOT,
    ]
    dev_line = _developers_line()
    if dev_line:
        lines.append(dev_line)
    return no_em_dash('\n'.join(lines)) + '\n'


def _write_atomic(path: Path, content: str):
    """tmp + os.replace, same hidden-dot-file pattern as
    web/report_renderer.py:rebuild_report_sitemap, so a concurrent request never
    sees a half-written file."""
    tmp = path.parent / ('.' + path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)


def _prune_legacy_static():
    """Remove the retired duplicate-content leftovers under _static/. The live
    market pages moved to /markets/ and research to /research.html long ago;
    the old copies kept serving stale hosts (35 host-leak FAILs on the 2026-07-04
    staging deploy) and shadowed the live pages in old sitemaps. Deleting here -
    the same generator that excludes them from the sitemap - makes every env
    self-heal on regen. Idempotent: silent no-op once gone."""
    import shutil
    legacy_dir = WEB_ROOT / '_static' / 'markets'
    if legacy_dir.is_dir():
        shutil.rmtree(legacy_dir, ignore_errors=True)
        print('pruned legacy %s' % legacy_dir)
    # learn.html: the pre-June placeholder, superseded by the /learn/ section
    # (generate_learn.py); its builder is uncalled and footers now link /learn/.
    for legacy_file in (WEB_ROOT / '_static' / 'research.html', WEB_ROOT / 'learn.html'):
        if legacy_file.is_file():
            try:
                legacy_file.unlink()
                print('pruned legacy %s' % legacy_file)
            except OSError as e:
                print('  prune failed for %s: %s' % (legacy_file, e), file=sys.stderr)


def main():
    if not WEB_ROOT.is_dir():
        print('FATAL: web root %s does not exist' % WEB_ROOT, file=sys.stderr)
        sys.exit(1)

    _prune_legacy_static()
    build_markets_index()

    urls = collect_urls()
    if not urls:
        print('FATAL: no pages found on disk under %s - refusing to write an empty '
              'sitemap' % WEB_ROOT, file=sys.stderr)
        sys.exit(1)

    _write_atomic(WEB_ROOT / 'sitemap.xml', build_sitemap(urls))
    print('sitemap.xml   %d urls -> %s' % (len(urls), WEB_ROOT / 'sitemap.xml'))

    _write_atomic(WEB_ROOT / 'robots.txt', build_robots())
    print('robots.txt    %s -> %s' % ('Allow (prod)' if ENABLE_SEO else 'Disallow (dev/staging)',
                                       WEB_ROOT / 'robots.txt'))

    _write_atomic(WEB_ROOT / 'llms.txt', build_llms())
    print('llms.txt      -> %s' % (WEB_ROOT / 'llms.txt'))

    if ENABLE_SEO:
        # Google Search Console site-verification file (FILE method). The token
        # is issued once for https://tradewave.ai/ (via the Site Verification
        # API, 2026-07-07, claude-ga4 service account = verified owner) and is
        # permanent - re-emitting it on every prod regen means no cleanup or
        # deploy step can ever silently un-verify the site. Prod-only: the
        # token names the tradewave.ai property, meaningless on dev/staging.
        gsc = 'google083fcaa7c3e113ea.html'
        _write_atomic(WEB_ROOT / gsc, 'google-site-verification: %s\n' % gsc)
        print('gsc-verify    -> %s' % (WEB_ROOT / gsc))


if __name__ == '__main__':
    main()
