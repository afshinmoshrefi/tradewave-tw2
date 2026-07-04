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
"""


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
    whole number."""
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
    judged = [e for e in history if is_judged(e)]
    hits = sum(1 for e in judged if hit_target(e))
    rate = round((hits / len(judged)) * 100) if judged else 0
    return rate, hits, len(judged)


def compute_held_to_close_rate(history):
    """Return (rate_pct, wins, resolved_count) over CLOSED picks only: the
    share that finished profitable at the close. The secondary transparency
    stat beside the headline win rate (a hit pick can fade by the close;
    both facts stay visible)."""
    resolved = [e for e in history if is_resolved(e)]
    wins = sum(1 for e in resolved if e['actual_return'] > 0)
    rate = round((wins / len(resolved)) * 100) if resolved else 0
    return rate, wins, len(resolved)
