#!/usr/bin/env python3
"""Shared win-counting for the daily-pick track record.

SINGLE SOURCE OF TRUTH for "did a featured pick win?" so the homepage strip
(generate_home_page.py) and the public scorecard (generate_scorecard.py) can
never report different win rates again.

Win definition (the defensible one):
  * A pick is RESOLVED only once it has CLOSED (status == 'closed' with an
    actual_return). Open positions are still in-flight and are NOT counted as
    wins or losses, no matter how far the peak ran intraday.
  * A closed pick is a WIN when its realized close-to-close return
    (actual_return) is positive - i.e. the move actually went the predicted
    direction by the close. We do NOT count peak_return (the best intraday
    excursion), because peaks are not realizable returns and inflate the rate.

This yields the conservative, defensible number (~60%) rather than the
peak-based figure (~80%).
"""


def is_resolved(entry):
    """A pick counts toward the win rate only once it has closed."""
    return (entry.get('status') == 'closed'
            and entry.get('actual_return') is not None)


def is_win(entry):
    """True if a resolved (closed) pick finished in the predicted direction.

    Returns False for unresolved/open picks - callers should gate on
    is_resolved() first when they need to distinguish open from lost.
    """
    if not is_resolved(entry):
        return False
    return entry['actual_return'] > 0


def compute_win_rate(history):
    """Return (win_rate_pct, wins, resolved_count) over closed picks.

    win_rate_pct is rounded to a whole number. resolved_count excludes any
    still-open positions.
    """
    resolved = [e for e in history if is_resolved(e)]
    wins = sum(1 for e in resolved if is_win(e))
    win_rate = round((wins / len(resolved)) * 100) if resolved else 0
    return win_rate, wins, len(resolved)


def reached_target(entry):
    """True if a resolved pick's best intraperiod move (peak_return / MFE)
    reached or exceeded its predicted return at some point in the window.

    This is the SECOND, separately-labeled metric: it answers "did the
    predicted seasonal move materialize during the window" (an opportunity to
    exit at target), which is a DIFFERENT question from is_win() ("did it hold
    a profit all the way to the close"). The two are shown side by side and
    never blended - a pick can reach target then fade to a close loss (COP,
    NVDA in the live record), and both facts are reported honestly.
    """
    if not is_resolved(entry):
        return False
    peak = entry.get('peak_return')
    pred = entry.get('pred_return') or 0
    return peak is not None and pred > 0 and peak >= pred


def compute_target_hit_rate(history):
    """Return (target_hit_rate_pct, hits, resolved_count) over closed picks -
    the share whose intraperiod peak reached the predicted target. Same
    denominator as compute_win_rate so the two headline numbers compare
    directly."""
    resolved = [e for e in history if is_resolved(e)]
    hits = sum(1 for e in resolved if reached_target(e))
    rate = round((hits / len(resolved)) * 100) if resolved else 0
    return rate, hits, len(resolved)
