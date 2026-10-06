"""Read-only current-day SMN static-edition verification; never repairs or sends.

Run on the production host with Python 3.9+. The default date is today's
America/New_York date. --date YYYY-MM-DD permits an explicit historical audit.
Exit 0 means the complete static edition passed every listed check; exit 2 means
attention is required. This does not establish newsletter delivery or alert health.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path('/var/lib/tradewave/smn-daily/subscription-primary')
WEB = Path('/var/www/smn')
ORIGIN = 'https://seasonalmarketnews.com'
MAX_BYTES = 2 * 1024 * 1024
# This exact observed public edge addition is the only allowed HTML normalization.
CF_BEACON = b'''<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/v31edd6df95cf4e85bb4c19e7a9bdbcba1788362987495" integrity="sha512-iIg7k2xntmwu6/uSb5tpc/hySgZc4eoL31yB29W6tJFo2akwjPWcEqnCEdJvGexCL0KEQwVYv5BlowfhVz26hg==" data-cf-beacon='{"version":"2024.11.0","token":"6c5153e7bcd94cb993504acb03b8923e","r":1,"spa":2}' crossorigin="anonymous"></script>'''

def sha(value): return hashlib.sha256(value).hexdigest()
def read(path): return json.loads(path.read_text())

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.urls = set()
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href: self.urls.add(urljoin(ORIGIN, href))

def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'SMNReadOnlyVerification/1.1',
                                      'Cache-Control': 'no-cache'}), timeout=15) as response:
        body = response.read(MAX_BYTES + 1)
        if response.status != 200 or response.url != url or len(body) > MAX_BYTES:
            raise ValueError('Public response status, location or size differs')
        return body

def match(body, expected):
    if sha(body) == expected: return 'exact'
    if body.count(CF_BEACON) == 1:
        for addition in (CF_BEACON, CF_BEACON + b'\n'):
            if addition in body and sha(body.replace(addition, b'', 1)) == expected:
                return 'exact_known_cloudflare_beacon'
    return None

def inspect(day):
    base = ROOT / day
    reader = base / 'chatgpt'
    receipt_path = reader / 'production-publication-receipt.json'
    if not receipt_path.is_file():
        resolution = read(base / 'recovery-resolution.json')
        reader = Path(resolution['recovery_root']).resolve()
        if (reader.parent != base.resolve() or resolution.get('edition_date') != day or
                resolution.get('status') != 'live_verified' or not resolution.get('original_failed_edition_unchanged')):
            raise ValueError('Recovery resolution is outside the verified dated scope')
        receipt_path = reader / 'production-publication-receipt.json'
        if sha(receipt_path.read_bytes()) != resolution.get('publication_receipt_sha256'):
            raise ValueError('Recovery receipt differs from resolved publication')
    selection = read(base / 'inputs/input-selection.json')
    receipt = read(receipt_path)
    expected = selection.get('symbols') or []
    if not (selection.get('date') == day and 1 <= len(expected) <= 6 and
            len(set(expected)) == len(expected) and
            all(isinstance(symbol, str) and re.fullmatch(r'[A-Z0-9._-]+', symbol) for symbol in expected)):
        raise ValueError('Invalid current-date frozen selection')
    selected_posts = base / 'inputs/production/posts.json'
    selection_hash = (selection.get('files') or {}).get('production/posts.json')
    selection_valid = (sha(selected_posts.read_bytes()) == selection_hash and
                       {row.get('symbol') for row in read(selected_posts)} == set(expected))
    continuity = receipt.get('publication_policy') == 'continuity-v1'
    published = receipt.get('published_symbols', expected)
    declared_complete = (receipt.get('complete') is True and
                         receipt.get('expected_symbols') == expected and
                         set(published) == set(expected) and not receipt.get('pending_symbols')) if continuity else True
    receipt_valid = (receipt.get('status') == 'live_verified' and receipt.get('production_written') is True
                     and receipt.get('edition_date') == day and declared_complete)
    if receipt.get('membership_publication'):
        raise ValueError('Membership edition requires bound preview/member verification; static checker cannot certify it')
    with ThreadPoolExecutor(max_workers=2) as pool:
        catalog_future = pool.submit(fetch, ORIGIN + '/posts.json')
        home_future = pool.submit(fetch, ORIGIN + '/')
        catalog = json.loads(catalog_future.result())
        parser = Links(); parser.feed(home_future.result().decode('utf-8'))
    if not isinstance(catalog, list): raise ValueError('Public catalog is not a list')
    files = receipt.get('files') or {}
    relevant = {relative: digest for relative, digest in files.items()
                if relative.startswith('editions/' + day + '/')}
    origin_mismatches = []
    for relative, digest in relevant.items():
        path = (WEB / relative).resolve()
        if WEB.resolve() not in path.parents or not path.is_file() or sha(path.read_bytes()) != digest:
            origin_mismatches.append(relative)
    def article(symbol):
        relative = f'editions/{day}/{symbol}/article.html'
        url = ORIGIN + '/' + relative
        entries = [row for row in catalog if isinstance(row, dict) and urljoin(ORIGIN, row.get('url', '')) == url]
        catalog_ok = (len(entries) == 1 and entries[0].get('symbol') == symbol and
                      str(entries[0].get('published_date', ''))[:10] == day and
                      entries[0].get('edition_id') == 'subscription-' + day)
        row = {'symbol': symbol, 'url': url, 'catalog_current_unique': catalog_ok,
               'homepage_link_present': url in parser.urls, 'receipt_sha256': files.get(relative)}
        try:
            body = fetch(url)
            row.update(public_sha256=sha(body), content_match=match(body, files.get(relative)))
        except Exception as exc:
            row.update(content_match=None, error_type=type(exc).__name__)
        row['passed'] = bool(row['catalog_current_unique'] and row['homepage_link_present'] and row['content_match'])
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:
        articles = list(pool.map(article, expected))
    recovery = receipt.get('recovery_root')
    recovery_path_valid = (not recovery or base.resolve() in Path(recovery).resolve().parents)
    return {'checked_utc': datetime.now(timezone.utc).isoformat(), 'edition_date': day,
            'active_release': str(Path('/opt/smn-subscription/current').resolve()),
            'source_commit': receipt.get('source_commit'), 'receipt_sha256': sha(receipt_path.read_bytes()), 'verified_reader_root': str(reader),
            'frozen_selection_valid': selection_valid, 'receipt_complete_verified': receipt_valid,
            'coverage_status': receipt.get('coverage_status', 'complete' if receipt_valid else 'unverified'),
            'recovery_root': recovery, 'recovery_root_within_day': recovery_path_valid,
            'origin_edition_files_checked': len(relevant), 'origin_mismatches': origin_mismatches,
            'articles': articles, 'newsletter_delivery': 'not_assessed', 'alert_delivery': 'not_assessed',
            'complete_edition_verified': bool(selection_valid and receipt_valid and recovery_path_valid
                and relevant and not origin_mismatches and all(row['passed'] for row in articles))}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat())
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    try:
        result = inspect(args.date)
    except Exception as exc:
        result = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'edition_date': args.date,
                  'complete_edition_verified': False, 'error_type': type(exc).__name__,
                  'error': str(exc)[:240], 'scope': 'read-only; no repair, credentials or provider actions'}
    print(json.dumps(result, indent=2))
    return 0 if result.get('complete_edition_verified') else 2

if __name__ == '__main__': raise SystemExit(main())
