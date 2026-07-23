#!/usr/bin/env python3
"""
TradeWave AI Scorecard Generator
Generates the /scorecard page from featured_history.json + live price data.

Usage:
    python generate_scorecard.py
"""

import json
import os
import requests
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import sys
sys.path.insert(0, '/home/flask')
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent / 'lib'))
import config
from blog_tools import convert_param_base64
from ga_snippet import ga_head_snippet
from log_safety import scrub_secret_text
from pick_stats import (  # shared win definition
    compute_win_rate, compute_target_hit_rate, compute_held_to_close_rate, compute_median_result_return, is_judged, is_resolved, is_win, reached_target, result_return,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

FEATURED_HISTORY_FILE = "/home/flask/site/data/featured_history.json"
OUTPUT_DIR = config.web_root_dir
OUTPUT_FILENAME = "scorecard.html"
# Machine-citable ledger export (TYPE H, docs/marketing/content-engine/
# CE_template_specs.md section 9) - served at /data/daily-pick-ledger.json.
LEDGER_JSON_RELPATH = "data/daily-pick-ledger.json"
TEMPLATES_DIR = "/home/flask/site/templates"
DOMAIN_ROOT = config.domain_root
APPSERVER_URL = config.appserver_url.rstrip('/')
REALTIME_SERVICE_URL = config.realtime_service_url
X_PROFILE_URL = config.x_profile_url

# Index only on prod; dev/staging stay noindex (same ENABLE_SEO pattern as
# generate_home_page.py - env-driven so the prod build flips it on automatically
# instead of relying on a manual edit before launch).
ENABLE_SEO = os.environ.get('TW2_ENV', '').strip().lower() == 'prod'
CANONICAL_URL = DOMAIN_ROOT + OUTPUT_FILENAME
META_DESCRIPTION = ("Every TradeWave daily pick, logged in public before the market opens: "
                     "the seasonal pattern, the win probability, the target - then the outcome, "
                     "wins and losses alike.")

# =============================================================================
# APPSERVER AUTH
# =============================================================================

def appserver_login():
    """Login to appserver and return token.
    TW2: uses single-step service-account API key flow.
    Falls back to legacy 2-step keyprovider flow if SERVICE_API_KEY isn't set.
    """
    if getattr(config, 'SERVICE_API_KEY', None):
        try:
            url = APPSERVER_URL + '/login/api'
            resp = requests.post(
                url,
                headers={'X-Service-Key': config.SERVICE_API_KEY},
                timeout=30,
            ).json()
            if 'token' in resp:
                return resp['token']
            print("   ERROR TW2 service-account login failed: %s" % resp.get('message', 'unknown'))
            return None
        except Exception as e:
            print("   ERROR TW2 service-account login exception: %s" % scrub_secret_text(e, config.SERVICE_API_KEY))
            return None

    # Legacy TW1 path - only runs if SERVICE_API_KEY isn't set
    def _get(url, attempts=3, timeout=30, sleep_s=5):
        last = None
        for i in range(attempts):
            try:
                return requests.get(url, timeout=timeout).json()
            except Exception as e:
                last = e
                print("   WARN appserver call failed (%s), attempt %d/%d" % (scrub_secret_text(e), i + 1, attempts))
                time.sleep(sleep_s)
        raise last

    try:
        result = _get(APPSERVER_URL + '/login/16/7/4/5/6')
        kp_token = result['message'].split(' ')[4]
        url = APPSERVER_URL + '/login/16/7/4/5/' + kp_token
        result = _get(url)
        if 'message' in result:
            time.sleep(10)
            result = _get(url)
            if 'message' in result:
                return None
        return result['token']
    except Exception as e:
        print("   ERROR legacy appserver login failed: %s" % scrub_secret_text(e))
        return None


# =============================================================================
# PRICE LOOKUPS
# =============================================================================

def fetch_close_price(resource_id, symbol, target_date, token):
    """Fetch the close price for a symbol on a specific date."""
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    d0 = (dt - timedelta(days=5)).strftime('%Y-%m-%d')
    d1 = (dt + timedelta(days=5)).strftime('%Y-%m-%d')
    url = '%s/ChartHistorical2/%s/%s/%s/%s?token=%s' % (
        APPSERVER_URL, resource_id, symbol, d0, d1, token
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get('ChartHistorical2', [])
        best = None
        for row in rows:
            if row[0] <= target_date:
                best = row
        if best:
            return float(best[4])
    except Exception as e:
        print("   WARNING: Price fetch failed for %s on %s: %s" % (symbol, target_date, scrub_secret_text(e)))
    return None


def fetch_realtime_prices_bulk(symbols):
    """Fetch real-time prices for multiple symbols from the realtime service.

    Returns dict: {symbol: {price, high}} for symbols found.
    Symbols not found (non-US stocks, indices, futures) are omitted.
    """
    if not symbols:
        return {}
    symbols_param = ','.join(s.upper() for s in symbols)
    url = REALTIME_SERVICE_URL.rstrip('/') + '/prices/bulk?symbols=' + symbols_param
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        for sym, pdata in data.get('prices', {}).items():
            p = pdata.get('price')
            if p is not None:
                entry = {'price': float(p)}
                h = pdata.get('high')
                if h is not None:
                    entry['high'] = float(h)
                result[sym.upper()] = entry
        return result
    except Exception as e:
        print("   WARNING: Realtime bulk fetch failed: %s" % scrub_secret_text(e))
        return {}


def fetch_current_price(resource_id, symbol, token):
    """Fetch the most recent close price for a symbol (fallback via ChartHistorical2)."""
    today = date.today()
    d1 = today.strftime('%Y-%m-%d')
    d0 = (today - timedelta(days=10)).strftime('%Y-%m-%d')
    url = '%s/ChartHistorical2/%s/%s/%s/%s?token=%s' % (
        APPSERVER_URL, resource_id, symbol, d0, d1, token
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get('ChartHistorical2', [])
        if rows:
            return float(rows[-1][4])
    except Exception as e:
        print("   WARNING: Current price fetch failed for %s: %s" % (symbol, scrub_secret_text(e)))
    return None


def fetch_end_price(resource_id, symbol, end_date, token):
    """Fetch the close price on or just after the pattern end date."""
    dt = datetime.strptime(end_date, '%Y-%m-%d')
    d0 = (dt - timedelta(days=2)).strftime('%Y-%m-%d')
    d1 = (dt + timedelta(days=5)).strftime('%Y-%m-%d')
    url = '%s/ChartHistorical2/%s/%s/%s/%s?token=%s' % (
        APPSERVER_URL, resource_id, symbol, d0, d1, token
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get('ChartHistorical2', [])
        # Find the first trading day on or after end_date
        for row in rows:
            if row[0] >= end_date:
                return float(row[4])
        # If none on/after, use the last available
        if rows:
            return float(rows[-1][4])
    except Exception as e:
        print("   WARNING: End price fetch failed for %s on %s: %s" % (symbol, end_date, scrub_secret_text(e)))
    return None


def fetch_peak_price(resource_id, symbol, start_date, end_date, direction, token):
    """Fetch the peak price during the trade window.

    For longs: highest high during the window.
    For shorts: lowest low during the window.
    Returns the peak price or None.

    ChartHistorical2 row format: [date, open, high, low, close, volume]
    """
    # Use the day after start (entry is at close of start_date) through end_date
    dt_start = datetime.strptime(start_date, '%Y-%m-%d')
    d0 = (dt_start + timedelta(days=1)).strftime('%Y-%m-%d')
    # For open positions, use today as the end
    today_str = date.today().strftime('%Y-%m-%d')
    d1 = min(end_date, today_str)
    # Add a few days buffer for weekends
    dt_end = datetime.strptime(d1, '%Y-%m-%d')
    d1_padded = (dt_end + timedelta(days=3)).strftime('%Y-%m-%d')

    url = '%s/ChartHistorical2/%s/%s/%s/%s?token=%s' % (
        APPSERVER_URL, resource_id, symbol, d0, d1_padded, token
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get('ChartHistorical2', [])
        # Filter to rows within the actual window
        window_rows = [r for r in rows if r[0] >= d0 and r[0] <= d1]
        if not window_rows:
            return None
        if direction == 'l':
            return max(float(r[2]) for r in window_rows)  # highest high
        else:
            return min(float(r[3]) for r in window_rows)  # lowest low
    except Exception as e:
        print("   WARNING: Peak price fetch failed for %s %s-%s: %s" % (symbol, start_date, end_date, scrub_secret_text(e)))
    return None


# =============================================================================
# DATA PROCESSING
# =============================================================================

def load_history():
    """Load featured history."""
    try:
        with open(FEATURED_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    """Save featured history (with enriched fields)."""
    with open(FEATURED_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def compute_end_date(start_date, days_out):
    """Compute the pattern end date."""
    dt = datetime.strptime(start_date, '%Y-%m-%d')
    end = dt + timedelta(days=days_out)
    return end.strftime('%Y-%m-%d')


def enrich_positions(history, token):
    """Enrich history entries with current/end prices and returns.

    Classifies each entry as 'open' or 'closed' and computes actual returns.
    Modifies entries in place and saves back to history file.
    """
    today_str = date.today().strftime('%Y-%m-%d')
    changed = False

    # Bulk-fetch real-time prices for all open positions in one call
    open_symbols = [
        e['symbol'] for e in history
        if today_str < compute_end_date(e['date'], e['daysOut'])
    ]
    realtime_prices = fetch_realtime_prices_bulk(open_symbols)
    if realtime_prices:
        print("   Realtime prices fetched for %d/%d open symbols" % (
            len(realtime_prices), len(open_symbols)))

    for entry in history:
        end_date = compute_end_date(entry['date'], entry['daysOut'])
        entry['end_date'] = end_date

        # Ensure start_price exists
        if not entry.get('start_price'):
            price = fetch_close_price(
                entry['resource_id'], entry['symbol'], entry['date'], token
            )
            if price:
                entry['start_price'] = price
                changed = True
            else:
                continue

        if today_str >= end_date:
            # Closed position
            entry['status'] = 'closed'
            if not entry.get('end_price'):
                end_price = fetch_end_price(
                    entry['resource_id'], entry['symbol'], end_date, token
                )
                if end_price:
                    entry['end_price'] = end_price
                    changed = True

            if entry.get('end_price') and entry.get('start_price'):
                if entry['direction'] == 'l':
                    entry['actual_return'] = round(
                        (entry['end_price'] - entry['start_price']) / entry['start_price'] * 100, 2
                    )
                else:
                    entry['actual_return'] = round(
                        (entry['start_price'] - entry['end_price']) / entry['start_price'] * 100, 2
                    )
                entry['win'] = entry['actual_return'] > 0

            # Peak return (MFE) for closed positions - fetch once and persist
            if not entry.get('peak_price') and entry.get('start_price'):
                peak = fetch_peak_price(
                    entry['resource_id'], entry['symbol'],
                    entry['date'], end_date, entry['direction'], token
                )
                if peak:
                    entry['peak_price'] = peak
                    if entry['direction'] == 'l':
                        entry['peak_return'] = round(
                            (peak - entry['start_price']) / entry['start_price'] * 100, 2
                        )
                    else:
                        entry['peak_return'] = round(
                            (entry['start_price'] - peak) / entry['start_price'] * 100, 2
                        )
                    changed = True
        else:
            # Open position
            entry['status'] = 'open'
            sym = entry['symbol'].upper()
            rt_data = realtime_prices.get(sym)
            current_price = None
            today_high = None
            if rt_data:
                current_price = rt_data['price']
                today_high = rt_data.get('high')
                entry['price_source'] = 'realtime'
            else:
                current_price = fetch_current_price(
                    entry['resource_id'], entry['symbol'], token
                )
                entry['price_source'] = 'close'
            if current_price and entry.get('start_price'):
                if entry['direction'] == 'l':
                    entry['current_return'] = round(
                        (current_price - entry['start_price']) / entry['start_price'] * 100, 2
                    )
                else:
                    entry['current_return'] = round(
                        (entry['start_price'] - current_price) / entry['start_price'] * 100, 2
                    )
                entry['current_price'] = current_price

            # Peak return (MFE) for open positions - recalculate each run
            if entry.get('start_price'):
                peak = fetch_peak_price(
                    entry['resource_id'], entry['symbol'],
                    entry['date'], end_date, entry['direction'], token
                )
                if peak:
                    # Historical OHLC may not include today, so incorporate
                    # today's intraday high/low from the realtime service
                    if today_high is not None:
                        if entry['direction'] == 'l':
                            peak = max(peak, today_high)
                        else:
                            peak = min(peak, today_high)
                    entry['peak_price'] = peak
                    if entry['direction'] == 'l':
                        entry['peak_return'] = round(
                            (peak - entry['start_price']) / entry['start_price'] * 100, 2
                        )
                    else:
                        entry['peak_return'] = round(
                            (entry['start_price'] - peak) / entry['start_price'] * 100, 2
                        )
                    changed = True

    if changed:
        save_history(history)

    return history


def compute_stats(history):
    """Compute aggregate stats for the stat boxes.

    Win counting uses the shared owner definition in pick_stats (2026-07-04)
    so the scorecard and the homepage strip can never diverge: a pick WINS
    when it reaches the AI's predicted gain inside the window (open or
    closed - hitting is terminal) or closes profitable; open picks that have
    not hit yet are pending. held_to_close is the stricter transparency stat
    shown beside it.
    """
    resolved = [e for e in history if is_resolved(e)]

    total_picks = len(history)
    still_open = total_picks - len(resolved)

    win_rate, wins_n, judged_n = compute_win_rate(history)
    target_hit_rate, hits_n, _ = compute_target_hit_rate(history)
    held_rate, held_n, _resolved_n = compute_held_to_close_rate(history)

    # Median RESULT return over judged picks: exit at target when hit, else the
    # window close - consistent with the win definition (a target-hit winner
    # must not drag its faded close into the median).
    avg_return = compute_median_result_return(history)

    # Current streak (consecutive resolved wins from most recent backwards).
    streak = 0
    streak_type = 'W'
    sorted_resolved = sorted(resolved, key=lambda x: x['featured_date'], reverse=True)
    if sorted_resolved:
        first_win = is_win(sorted_resolved[0])
        streak_type = 'W' if first_win else 'L'
        for e in sorted_resolved:
            if is_win(e) == first_win:
                streak += 1
            else:
                break

    return {
        'total_picks': total_picks,
        'win_rate': round(win_rate, 1),            # hit predicted gain OR closed up
        'win_count': wins_n,
        'judged_count': judged_n,                  # closed + open-already-hit
        'target_hit_rate': round(target_hit_rate, 1),  # reached target in window
        'target_hit_count': hits_n,
        'held_to_close_rate': round(held_rate, 1),  # still up at the close (strict)
        'held_to_close_count': held_n,
        'avg_return': round(avg_return, 1),
        'current_streak': '%d%s' % (streak, streak_type) if streak else '--',
        'closed_count': len(resolved),
        'open_count': still_open,
    }


def build_positions(history):
    """Build open and closed position lists for the template."""
    open_positions = []
    closed_positions = []

    for entry in history:
        row = {
            'featured_date': entry.get('featured_date', ''),
            'symbol': entry.get('symbol', ''),
            'company_name': entry.get('company_name', ''),
            'direction': 'Long' if entry.get('direction') == 'l' else 'Short',
            'days': entry.get('daysOut', 0),
            'win_prob': '%.1f' % (entry.get('win_prob', 0) * 100),
            'pred_return': '%.1f' % entry.get('pred_return', 0),
            'wave_viewer_url': entry.get('wave_viewer_url', ''),
        }

        # Success column: green check if peak >= predicted, red X only for closed failures
        peak_ret = entry.get('peak_return')
        pred_ret = entry.get('pred_return', 0)
        if peak_ret is not None and peak_ret >= pred_ret:
            row['success'] = 'yes'
        elif entry.get('status') == 'closed' and entry.get('actual_return') is not None and entry.get('actual_return') < 0:
            row['success'] = 'no'
        else:
            row['success'] = 'pending'

        # Table placement is by lifecycle: open picks stay in the open table
        # until their window CLOSES (their peak column shows a target hit
        # live). The headline win rate counts an open pick that already hit
        # its predicted gain as a win (owner definition, pick_stats
        # 2026-07-04) - placement here is about when the CLOSE outcome
        # exists, not whether the pick has won.
        if not is_resolved(entry):
            row['current_return'] = '%.1f' % entry.get('current_return', 0) if entry.get('current_return') is not None else '--'
            row['current_return_num'] = entry.get('current_return', 0)
            row['peak_return'] = '%.1f' % entry.get('peak_return', 0) if entry.get('peak_return') is not None else '--'
            row['peak_return_num'] = entry.get('peak_return', 0)
            row['price_source'] = entry.get('price_source', 'close')
            open_positions.append(row)
        else:
            # Closed: realize at the actual close return (no peak inflation).
            actual = entry.get('actual_return', 0)
            peak = entry.get('peak_return')
            row['actual_return'] = '%.1f' % actual if actual is not None else '--'
            row['actual_return_num'] = actual
            row['peak_return'] = '%.1f' % peak if peak is not None else '--'
            row['peak_return_num'] = peak or 0
            row['win'] = is_win(entry)
            row['wl'] = 'W' if is_win(entry) else 'L'
            # Result under the system exit rule (target when hit, else close) -
            # feeds the month-group medians so they match the headline metric.
            row['result_return_num'] = result_return(entry)
            # Second truth, shown separately: did the move reach target in the
            # window even if it faded by the close? (never overwrites actual_return)
            row['reached_target'] = reached_target(entry)
            closed_positions.append(row)

    # Sort: open by date ascending, closed by date descending (newest first)
    open_positions.sort(key=lambda x: x['featured_date'])
    closed_positions.sort(key=lambda x: x['featured_date'], reverse=True)

    return open_positions, closed_positions


def group_closed_by_month(closed_positions, expand_newest=2):
    """Group the (newest-first) closed rows into per-month sections for the
    collapsible ledger: the closed list grows forever, so each month renders
    as a <details> block whose summary line is that month's own results
    (picks, W-L, win rate, median close return). Newest expand_newest months
    ship open; ALL rows stay in the page (the ledger must remain auditable -
    grouping is presentation, never truncation)."""
    months = []
    by_key = {}
    for pos in closed_positions:  # already newest-first, so months come out newest-first
        key = pos['featured_date'][:7]
        if key not in by_key:
            label = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
            by_key[key] = {'key': key, 'label': label, 'positions': []}
            months.append(by_key[key])
        by_key[key]['positions'].append(pos)
    for i, m in enumerate(months):
        rows = m['positions']
        wins = sum(1 for r in rows if r['win'])
        # Median of RESULT returns (exit at target when hit, else the close) -
        # same semantics as the headline Median Return.
        returns = sorted(r['result_return_num'] for r in rows
                         if r.get('result_return_num') is not None)
        median = returns[len(returns) // 2] if returns else 0
        m['count'] = len(rows)
        m['wins'] = wins
        m['losses'] = len(rows) - wins
        m['win_rate'] = round(wins / len(rows) * 100) if rows else 0
        m['median_return'] = round(median, 1)
        m['open'] = i < expand_newest
    return months


# =============================================================================
# MACHINE-CITABLE LEDGER EXPORT (TYPE H)
# =============================================================================

# Pinned contract: docs/marketing/content-engine/CE_template_specs.md section 9,
# "Machine-citable export". This JSON is the artifact an AI assistant can verify
# the scorecard's claims against; the TYPE H Dataset schema points at it.
LEDGER_WIN_DEFINITION = (
    "A pick wins when it reaches the AI's predicted gain inside its window "
    "(hitting is terminal - it never un-happens, open or closed) or closes "
    "profitable at the window end. Open picks that have not hit yet are "
    "pending (win = null) and are excluded from the win_rate denominator, "
    "which is resolved picks plus open picks that already hit. result_return "
    "realizes the predicted gain when the target was hit, else the "
    "window-close return; null while pending."
)
PAST_PERFORMANCE_LINE = "Past performance does not guarantee future results."


def emit_ledger_json(history):
    """Write the full pick ledger as machine-readable JSON beside the scorecard.

    Same shared win definition as the page (pick_stats), same history, same
    run - the JSON and the HTML can never diverge. Every pick is included
    with a 'resolved' flag; 'win' is null for pending picks (open, target not
    yet hit) so a machine reader never mistakes pending for lost.
    """
    win_rate, _wins, _judged = compute_win_rate(history)

    picks = []
    for entry in sorted(history, key=lambda e: e['featured_date']):
        picks.append({
            'featured_date': entry['featured_date'],
            'symbol': entry.get('symbol', ''),
            'direction': 'long' if entry.get('direction') == 'l' else 'short',
            'predicted_gain': entry.get('pred_return'),
            'result_return': result_return(entry),
            'win': is_win(entry) if is_judged(entry) else None,
            'resolved': is_resolved(entry),
        })

    payload = {
        'win_rate': win_rate,
        'resolved_count': sum(1 for e in history if is_resolved(e)),
        'start_date': picks[0]['featured_date'] if picks else None,
        'computed_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'definition': LEDGER_WIN_DEFINITION,
        'past_performance': PAST_PERFORMANCE_LINE,
        'picks': picks,
    }

    out_path = Path(OUTPUT_DIR) / LEDGER_JSON_RELPATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(out_path.parent, 0o755)
    # tmp + os.replace so a machine reader never sees a half-written file
    # (same pattern as generate_seo_files.py:_write_atomic).
    tmp = out_path.parent / ('.' + out_path.name + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2) + '\n')
    os.replace(tmp, out_path)
    os.chmod(out_path, 0o644)
    return out_path


# =============================================================================
# HTML GENERATION
# =============================================================================

def generate_scorecard_html(stats, open_positions, closed_positions):
    """Generate the scorecard HTML page."""
    jinja_env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = jinja_env.get_template('scorecard.html')

    content = {
        'stats': stats,
        'open_positions': open_positions,
        'closed_positions': closed_positions,
        'closed_months': group_closed_by_month(closed_positions),
        'domain_root': DOMAIN_ROOT,
        'x_profile_url': X_PROFILE_URL,
        'favicon': config.tw_favicon,
        'robots_content': 'index, follow' if ENABLE_SEO else 'noindex, nofollow',
        'canonical_url': CANONICAL_URL,
        'meta_description': META_DESCRIPTION,
        # GA4 <head> snippet ('' when TW2_GA_MEASUREMENT_ID is unset, e.g. dev).
        'ga_head_snippet': ga_head_snippet(),
    }

    return template.render(content=content)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("TradeWave AI Scorecard Generator")
    print("   History: %s" % FEATURED_HISTORY_FILE)
    print("   Output: %s%s" % (OUTPUT_DIR, OUTPUT_FILENAME))
    print()

    # 1. Load history
    history = load_history()
    if not history:
        print("   No history entries found. Generating empty scorecard.")

    # 2. Login to appserver
    print("   Logging in to appserver...")
    token = appserver_login()
    if token is None:
        print("   WARNING: Appserver login failed. Generating with cached data only.")
    else:
        # 3. Enrich with prices
        print("   Enriching %d positions with price data..." % len(history))
        history = enrich_positions(history, token)

    # 4. Compute stats
    stats = compute_stats(history)
    print("   Stats: %d picks, %.1f%% win rate, %.1f%% avg return, streak: %s" % (
        stats['total_picks'], stats['win_rate'], stats['avg_return'], stats['current_streak']))

    # 5. Build position tables
    open_positions, closed_positions = build_positions(history)
    print("   Open: %d, Closed: %d" % (len(open_positions), len(closed_positions)))

    # 6. Generate HTML
    print("   Generating HTML...")
    html = generate_scorecard_html(stats, open_positions, closed_positions)

    # 7. Save
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    output_path.write_text(html)

    print("   Generated: %s" % output_path)
    print("   Size: %d bytes" % len(html))

    # 8. Machine-citable ledger export (CE_template_specs.md section 9)
    ledger_path = emit_ledger_json(history)
    print("   Ledger JSON: %s" % ledger_path)
    print("   Done!")


if __name__ == "__main__":
    main()
