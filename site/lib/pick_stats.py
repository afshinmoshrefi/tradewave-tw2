#!/usr/bin/env python3
"""Shared win-counting for the daily-pick track record.

SINGLE SOURCE OF TRUTH for "did a featured pick win?" so the homepage strip
(generate_home_page.py) and the public scorecard (generate_scorecard.py) can
never report different win rates again.

Win definition (OWNER DEFINITION, set 2026-07-04 - reaffirms the scorecard's
original semantics; supersedes the 2026-06-16 held-to-close headline):
  * The AI publishes a predicted gain (pred_return) for a window. A pick that
    REACHES that gain (peak_return / MFE >= pred_return) is a WIN, permanently
    and immediately - open or closed, and it does not flip to a loss if price
    later fades into the close. "The entire point of the AI score is the
    highest probability of gain - if that gain is reached, it's a win."
  * A closed pick that never hit its target still wins if it closed
    profitable (actual_return > 0).
  * Open picks that have not hit yet are PENDING - excluded from the win-rate
    denominator entirely (never counted as losses-in-waiting).
  * Transparency stays: held-to-close rate (closed-profitable share) remains a
    separately labeled secondary stat, and every row shows the realized close
    return - a hit-then-faded pick displays as a WIN with its red close visible.

  * A scorer-outage gap is not a pick. Rows marked scorer_outage, and any row
    whose featured_date falls inside site/lib/scorer_outage_gaps.json, stay
    out of the win rate and the pick counts. The 2026-09-17 through 2026-10-09
    production stall is that kind of gap. Nothing in it is backfilled.
"""

import datetime as dt
import json
from pathlib import Path


_GAP_PATH = Path(__file__).resolve().parent / 'scorer_outage_gaps.json'


def load_outage_gaps():
    """Return the recorded publication gaps. Missing file means no gaps."""
    if not _GAP_PATH.is_file():
        return []
    with _GAP_PATH.open(encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError('scorer outage gap file must be a list')
    return [row for row in data if isinstance(row, dict)]


def outage_notices(gaps=None):
    """Visible sentences for gaps that have a notice. Not a pick count."""
    notices = []
    for gap in load_outage_gaps() if gaps is None else gaps:
        notice = str(gap.get('notice') or '').strip()
        if notice:
            notices.append(notice)
    return notices


def in_outage_gap(featured_date, gaps=None):
    """True when featured_date is inside an inclusive scorer-outage gap."""
    try:
        day = dt.date.fromisoformat(str(featured_date))
    except (TypeError, ValueError):
        return False
    for gap in load_outage_gaps() if gaps is None else gaps:
        try:
            start = dt.date.fromisoformat(str(gap.get('start')))
            end = dt.date.fromisoformat(str(gap.get('end')))
        except (TypeError, ValueError):
            continue
        if start <= day <= end:
            return True
    return False


def is_outage_record(entry):
    """True for an explicit gap marker. Those rows are not picks."""
    if not isinstance(entry, dict):
        return False
    kind = str(entry.get('record_type') or entry.get('kind') or '')
    return kind == 'scorer_outage'


def countable_picks(history, gaps=None):
    """Picks that enter win rate and counts.

    Drops scorer-outage markers and any row dated inside a recorded gap so a
    later backfill cannot move the public stats.
    """
    selected = load_outage_gaps() if gaps is None else gaps
    kept = []
    for entry in history or []:
        if not isinstance(entry, dict) or is_outage_record(entry):
            continue
        if in_outage_gap(entry.get('featured_date'), selected):
            continue
        kept.append(entry)
    return kept


def is_resolved(entry):
    """The pick has closed (its window ended and the close outcome is known)."""
    return (entry.get('status') == 'closed'
            and entry.get('actual_return') is not None)


def hit_target(entry):
    """The pick's best move in the window (peak_return / MFE) reached the AI's
    predicted gain - open or closed. Hitting is terminal for the prediction's
    claim: it never un-happens."""
    peak = entry.get('peak_return')
    pred = entry.get('pred_return') or 0
    return peak is not None and pred > 0 and peak >= pred


def is_judged(entry):
    """The pick can be scored: it either closed, or it already hit its target.
    Open picks that have not hit yet are pending and stay OUT of the win-rate
    denominator."""
    return is_resolved(entry) or hit_target(entry)


def is_win(entry):
    """True if the pick reached its predicted gain in the window, or closed
    profitable. False for pending (open, not-yet-hit) picks - callers should
    gate on is_judged() when they need to distinguish pending from lost."""
    if hit_target(entry):
        return True
    return is_resolved(entry) and entry['actual_return'] > 0


def compute_win_rate(history):
    """Return (win_rate_pct, wins, judged_count).

    Denominator = judged picks (closed, plus open picks that already hit -
    the prediction is proven, no reason to wait for the close). Rounded to a
    whole number. Scorer-outage gaps are not judged and are not pending."""
    history = countable_picks(history)
    judged = [e for e in history if is_judged(e)]
    wins = sum(1 for e in judged if is_win(e))
    win_rate = round((wins / len(judged)) * 100) if judged else 0
    return win_rate, wins, len(judged)


# --- secondary transparency stats ------------------------------------------

def reached_target(entry):
    """Row-level badge: the pick hit its predicted gain (alias of hit_target,
    kept for the per-row 'target reached' marker in the scorecard table)."""
    return hit_target(entry)


def compute_target_hit_rate(history):
    """Return (rate_pct, hits, judged_count): the share of judged picks that
    reached the predicted gain (excludes the closed-profitable-without-hit
    wins). Same denominator as compute_win_rate so the numbers compare."""
    history = countable_picks(history)
    judged = [e for e in history if is_judged(e)]
    hits = sum(1 for e in judged if hit_target(e))
    rate = round((hits / len(judged)) * 100) if judged else 0
    return rate, hits, len(judged)


def result_return(entry):
    """The pick's RESULT under the system's own exit rule: a pick that hit its
    predicted gain realizes exactly that gain (a standing limit order at the
    pre-published target fills on the touch - conservative: never the peak);
    a closed pick that never hit realizes its window-close return. Open
    not-yet-hit picks have no result (None). Keeps return stats consistent
    with the win definition - a target-hit winner must not drag a faded close
    into the medians (2026-07-05, WDC short: +6.8 target hit, -27.3 close)."""
    if hit_target(entry):
        return entry.get('pred_return')
    if is_resolved(entry):
        return entry.get('actual_return')
    return None


def compute_median_result_return(history):
    """Median result_return over judged picks (same population as the win
    rate), rounded to one decimal."""
    history = countable_picks(history)
    vals = sorted(v for v in (result_return(e) for e in history) if v is not None)
    return round(vals[len(vals) // 2], 1) if vals else 0


def compute_held_to_close_rate(history):
    """Return (rate_pct, wins, resolved_count) over CLOSED picks only: the
    share that finished profitable at the close. The secondary transparency
    stat beside the headline win rate (a hit pick can fade by the close;
    both facts stay visible)."""
    history = countable_picks(history)
    resolved = [e for e in history if is_resolved(e)]
    wins = sum(1 for e in resolved if e['actual_return'] > 0)
    rate = round((wins / len(resolved)) * 100) if resolved else 0
    return rate, wins, len(resolved)
