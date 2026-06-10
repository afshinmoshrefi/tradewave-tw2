#!/usr/bin/env python3
"""TradeWave Insights blog generator.

Reads markdown articles from /home/flask/site/content/insights/<slug>.md,
renders them with the shared TW2 header into static HTML at
/var/www/tradewave/insights/.

Article frontmatter (YAML between --- fences):
    title:           Plain text. <80 chars ideal.
    slug:            URL-safe. Filename = slug.md, output = slug.html.
    summary:         2-3 sentence card description.
    date:            ISO YYYY-MM-DD.
    author:          Default "TradeWave Research".
    reading_minutes: Estimate.
    tags:            List of lowercase strings.
    featured:        Optional bool. True highlights on the index.
    related:         Optional list of other slugs to surface in Continue Reading.

Body: standard markdown plus inline HTML (figures, callouts, etc.).
The no_em_dash filter runs on the final HTML.
"""
from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, '/home/flask/site/lib')
from text_utils import no_em_dash  # noqa: E402
from ga_snippet import ga_head_snippet  # noqa: E402

# --------------------------------------------------------------------------- 
# Paths
# ---------------------------------------------------------------------------

SITE_ROOT     = Path('/home/flask/site')
CONTENT_DIR   = SITE_ROOT / 'content' / 'insights'
TEMPLATES_DIR = SITE_ROOT / 'templates'
HEADER_PATH   = TEMPLATES_DIR / '_tw_header.html'
OUTPUT_DIR    = Path('/var/www/tradewave/insights')
SITEMAP_PATH  = Path('/var/www/tradewave/sitemap.xml')

YEAR = datetime.now().year

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Split a YAML frontmatter block from the markdown body.

    Returns (meta_dict, body_markdown).
    """
    if not text.startswith('---'):
        raise ValueError('article missing YAML frontmatter (must start with ---)')
    end = text.find('\n---', 3)
    if end == -1:
        raise ValueError('article frontmatter not closed (no second --- line)')
    fm = text[3:end].strip()
    body = text[end + 4:].lstrip('\n')
    meta = yaml.safe_load(fm) or {}
    return meta, body


def render_markdown(body: str) -> str:
    """Render markdown to HTML with extensions for tables, footnotes, fenced code."""
    return md.markdown(
        body,
        extensions=[
            'extra',        # includes tables, footnotes, fenced_code, etc.
            'sane_lists',
            'smarty',       # smart quotes; em dashes get filtered downstream anyway
            'toc',
            'attr_list',
        ],
        extension_configs={
            'toc': {'permalink': False},
        },
    )


def date_pretty(d: str | date) -> str:
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return d.strftime('%B %-d, %Y')


def date_iso(d: str | date) -> str:
    if isinstance(d, str):
        return d
    return d.isoformat()


def load_articles() -> List[Dict[str, Any]]:
    """Read every <slug>.md in CONTENT_DIR. Return a list of article dicts."""
    arts: List[Dict[str, Any]] = []
    for p in sorted(CONTENT_DIR.glob('*.md')):
        if p.name.startswith('_'):
            continue
        text = p.read_text(encoding='utf-8')
        try:
            meta, body = parse_frontmatter(text)
        except ValueError as e:
            print(f'  SKIP {p.name}: {e}', file=sys.stderr)
            continue
        slug = meta.get('slug') or p.stem
        meta['slug']            = slug
        meta['source_file']     = str(p)
        meta['body_md']         = body
        meta['body_html']       = render_markdown(body)
        meta.setdefault('author', 'TradeWave Research')
        meta['word_count']      = len(body.split())
        meta.setdefault('reading_minutes', max(1, meta['word_count'] // 220))
        meta.setdefault('tags', [])
        meta.setdefault('featured', False)
        meta.setdefault('related', [])
        if 'date' not in meta:
            meta['date'] = datetime.now().strftime('%Y-%m-%d')
        meta['date_pretty'] = date_pretty(meta['date'])
        meta['date_iso']    = date_iso(meta['date'])
        # og:image: first chart URL embedded in the body, else fallback to favicon.
        # Open Graph / Twitter Cards prefer raster (PNG), so swap the SVG
        # extension to PNG when the matching .png exists alongside.
        import re as _re
        m = _re.search(r'<img[^>]+src="(/insights/charts/[^"]+)"', meta['body_html'])
        if m:
            chart_path = m.group(1)
            png_candidate = _re.sub(r'\.svg$', '.png', chart_path)
            png_disk = Path('/var/www/tradewave') / png_candidate.lstrip('/')
            chosen = png_candidate if png_disk.exists() else chart_path
            meta['og_image_url'] = 'https://tw2.trxstat.com' + chosen
        elif meta.get('hero'):
            meta['og_image_url'] = ('https://tw2.trxstat.com' + meta['hero']
                                    if meta['hero'].startswith('/') else meta['hero'])
        else:
            meta['og_image_url'] = 'https://tw2.trxstat.com/favicon.png'
        arts.append(meta)
    arts.sort(key=lambda a: a['date_iso'], reverse=True)
    return arts


def pick_related(article: Dict[str, Any], all_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If the article specifies related slugs, use those. Otherwise pick up to
    4 articles that share a tag with this one (excluding self)."""
    out: List[Dict[str, Any]] = []
    if article.get('related'):
        for s in article['related']:
            for a in all_articles:
                if a['slug'] == s:
                    out.append(a)
                    break
    if out:
        return out[:4]
    my_tags = set(article.get('tags', []))
    others  = [a for a in all_articles if a['slug'] != article['slug']]
    scored  = sorted(
        others,
        key=lambda a: (-len(my_tags & set(a.get('tags', []))), a['date_iso']),
        reverse=False,
    )
    related = [a for a in scored if my_tags & set(a.get('tags', []))][:4]
    if not related:
        related = others[:4]
    return related


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def update_sitemap(articles: List[Dict[str, Any]]) -> None:
    """Make sure /insights/ + every article slug has a sitemap entry. Idempotent."""
    if not SITEMAP_PATH.exists():
        return
    existing = SITEMAP_PATH.read_text(encoding='utf-8')
    if '</urlset>' not in existing:
        return

    needed: List[str] = []
    needed.append('  <url>\n    <loc>https://tw2.trxstat.com/insights/</loc>\n    <lastmod>{}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>'.format(datetime.now().strftime('%Y-%m-%d')))
    for a in articles:
        needed.append('  <url>\n    <loc>https://tw2.trxstat.com/insights/{slug}.html</loc>\n    <lastmod>{date}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>'.format(slug=a['slug'], date=a['date_iso']))

    additions = ''
    for block in needed:
        url_loc = block.split('<loc>')[1].split('</loc>')[0]
        if url_loc not in existing:
            additions += '\n' + block

    if additions:
        new = existing.replace('</urlset>', additions + '\n</urlset>')
        SITEMAP_PATH.write_text(new, encoding='utf-8')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not CONTENT_DIR.is_dir():
        print(f'ERROR: {CONTENT_DIR} not found', file=sys.stderr)
        return 2
    if not OUTPUT_DIR.is_dir():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html']),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    article_tmpl = env.get_template('insights_article.html')
    index_tmpl   = env.get_template('insights_index.html')

    tw_header = HEADER_PATH.read_text(encoding='utf-8')

    articles = load_articles()
    if not articles:
        print('  no articles in', CONTENT_DIR)
        return 0

    print(f'TradeWave Insights generator')
    print(f'  content: {CONTENT_DIR}')
    print(f'  output:  {OUTPUT_DIR}')
    print()

    # Per-article pages
    for art in articles:
        related = pick_related(art, articles)
        html = article_tmpl.render(
            article=art,
            related=related,
            tw_header=tw_header,
            year=YEAR,
            ga_head_snippet=ga_head_snippet(),
        )
        html = no_em_dash(html)
        out = OUTPUT_DIR / f'{art["slug"]}.html'
        out.write_text(html, encoding='utf-8')
        print(f'  {art["slug"]:<32}  {len(html):>7} bytes  ({art["reading_minutes"]} min)')

    # Index
    html = index_tmpl.render(
        articles=articles,
        tw_header=tw_header,
        year=YEAR,
        ga_head_snippet=ga_head_snippet(),
    )
    html = no_em_dash(html)
    (OUTPUT_DIR / 'index.html').write_text(html, encoding='utf-8')
    print()
    print(f'  index.html               {len(html):>7} bytes  ({len(articles)} articles)')

    update_sitemap(articles)
    print()
    print('Done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
