"""SignalCard builder - the ONE source of truth for the flagship card object.

Implements api/SIGNALCARD_SPEC.md sections 1-5. The gateway endpoints (/v1/scan,
/v1/analyze/<symbol>, /v1/daily-pick) all build their cards HERE so headline/verdict/
edge_score/receipts are composed identically and exactly once.

Hard invariants enforced here (mirrors the spec):
- SIGNALS ONLY. No raw OHLCV / last price / price level / limit price is ever placed
  on a card. All movement is percentages; the seasonal curve is a 0-100 index.
- `historical_win_rate` (share of profitable years) and `ml_win_prob` (the ML model's
  predicted probability, Pro-only) are DISTINCT named fields - never both "win rate".
- `years` and window labels stay STRINGS. Market ids are the permanent keys '0'..'16'.
- Every card carries the exact `disclaimer` string.
- No em-dashes anywhere (use ' - ').

This module is pure composition: it takes already-fetched appserver data (an opportunity
dict, ChartData4 stats, the per-year ChartData4 returns, an optional seasonal curve, and
optional ml) and returns a card dict. It never calls the appserver itself (the endpoints /
appserver_client own fetching), so it stays cheap and testable.
"""
import datetime
import logging

log = logging.getLogger("apiserver.cards")

# The exact, regulator-facing disclaimer. Baked onto every card (spec section, DISCLAIMER).
DISCLAIMER = (
    "Educational seasonal + ML signal, not personalized investment advice and not a "
    "recommendation to buy or sell. Past performance is not indicative of future results."
)

# NO_SIGNAL / low-conviction thresholds (spec section 4).
MIN_EDGE_SCORE = 40
MIN_WIN_RATE = 0.55
MIN_YEARS_TESTED = 5

# tier_notes for the ML state of a card (ML is metered per day across all tiers now).
_ML_NOTES = {
    "shown": "ML score shown.",
    "quota": "Daily ML limit reached on your plan - upgrade for unlimited ML scoring.",
    "market": "ML not available for this market (ML covers US stocks, indices and ETFs).",
    "na": "ML not available.",
}

# edge_score blend weights (spec section 3). Tunable - this is the ONE place.
_W_WIN = 0.40
_W_SHARPE = 0.30
_W_ML = 0.20
_W_HISTORY = 0.10
_SHARPE_FULL = 3.0    # a 3.0 Sharpe earns full marks
_HISTORY_FULL = 15.0  # 15y of history earns full marks


# --------------------------------------------------------------------------- #
# small numeric helpers (cards.py owns its own parsing so it stays standalone) #
# --------------------------------------------------------------------------- #

def _clamp01(x):
    if x is None:
        return 0.0
    return max(0.0, min(1.0, x))


def _num(v):
    """Coerce a numeric-ish value (str '18%', '5.1', number) to float, else None."""
    if v is None or v == "":
        return None
    s = str(v).strip().rstrip("%").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _round(v, n=2):
    f = _num(v)
    return round(f, n) if f is not None else None


def _net_pct(pct_str):
    """ChartData4 per-year `pct` is 'net,mfe,mae' (or a bare number). Parse the NET (first
    field) only - mfe/mae are dropped. Returns float or None. No price is ever read."""
    if pct_str is None:
        return None
    s = str(pct_str).split(",")[0].strip()
    return _num(s)


# --------------------------------------------------------------------------- #
# per-year receipts from ChartData4 entries                                   #
# --------------------------------------------------------------------------- #

def per_year_returns(chart_entries, lookback=None):
    """Build the per-year receipt rows from raw ChartData4 entries.

    Each entry is {'year': 2024, 'pct': 'net,mfe,mae', 'price': '...'}. We use ONLY the
    net pct; `price` is dropped (price-safety invariant). The appserver appends an entry
    for the in-progress current year; when that window has not run yet it is an all-zero
    stub (net,mfe,mae == 0,0,0) and is NOT a completed year - we exclude it (it would fake
    an extra 'loss' row). A current-year entry the appserver HAS scored (a real non-zero
    partial) is kept, so per_year stays consistent with the appserver's own Percent
    Profitable / Num Winners counts (which include it).

    win = net% > 0 (no threshold - matches the UI's 'Percent Profitable'). The list is
    bounded at lookback + 1 (the historical years plus the at-most-one current partial) so
    it never runs away but never silently drops a real scored year. wins/losses/years_tested
    are derived from THESE rows so the card is internally consistent.
    Returns (rows, wins, losses); rows is chronological list of {year(str), return_pct, result}.
    """
    rows = []
    if not isinstance(chart_entries, list):
        chart_entries = []
    try:
        cap = int(lookback) if lookback not in (None, "") else None
    except (TypeError, ValueError):
        cap = None
    for e in chart_entries:
        if not isinstance(e, dict):
            continue
        net = _net_pct(e.get("pct"))
        if net is None:
            continue
        # skip the in-progress current year when the appserver hasn't scored it yet (all
        # three of net,mfe,mae are 0). A real scored partial year is kept.
        parts = str(e.get("pct", "")).split(",")
        is_zero_stub = all(_num(x) == 0.0 for x in parts) if parts else False
        if is_zero_stub:
            continue
        rows.append({
            "year": str(e.get("year")),
            "return_pct": round(net, 2),
            "result": "win" if net > 0 else "loss",
        })
    # bound at lookback + 1 (history + the at-most-one current partial); drop the OLDEST
    # beyond that so the most recent years are kept. This only trims runaway lists; the
    # normal case (10 history + 1 partial) passes through untouched.
    if cap is not None and len(rows) > cap + 1:
        rows = rows[-(cap + 1):]
    wins = sum(1 for r in rows if r["result"] == "win")
    losses = sum(1 for r in rows if r["result"] == "loss")
    return rows, wins, losses


def _best_worst(per_year):
    if not per_year:
        return None, None
    best = max(per_year, key=lambda r: r["return_pct"])
    worst = min(per_year, key=lambda r: r["return_pct"])
    return ({"year": best["year"], "return_pct": best["return_pct"]},
            {"year": worst["year"], "return_pct": worst["return_pct"]})


def curve_summary(section_curve):
    """Describe the TREND OF THE SECTION - the slice of the normalized trend chart that
    spans the trade's hold window (entry -> exit), NOT the whole annual cycle. The caller
    passes the already-sliced section (build_signal_card slices the curve to hold_days,
    because the appserver returns the curve starting at the entry date, so the first
    hold_days points ARE the hold window). `index` is a relative 0-100 seasonal index,
    never a price. Returns {shape, trend, change_pts, peak_day, trough_day} or None.

    'change_pts' = index at exit minus index at entry (how much the seasonal index moves
    across the hold). 'trend' rising / falling / flat. peak_day / trough_day are days
    INTO THE HOLD (0 = entry), so 'peak ~day 14' means day 14 of the hold, not the year.
    NEVER ships the full curve inline (that stays at the /v1/seasonal-chart primitive)."""
    if not section_curve:
        return None
    idxs = [c.get("index") for c in section_curve if isinstance(c, dict) and c.get("index") is not None]
    if len(idxs) < 2:
        return None
    n = len(idxs)
    peak_day = max(range(n), key=lambda i: idxs[i])
    trough_day = min(range(n), key=lambda i: idxs[i])
    change_pts = round(idxs[-1] - idxs[0], 1)
    trend = "rising" if change_pts > 2 else ("falling" if change_pts < -2 else "flat")
    # where the index peaks WITHIN the hold (day 0 = entry).
    if peak_day <= n * 0.34:
        when = "peaks early in the hold"
    elif peak_day >= n * 0.67:
        when = "strengthens into the exit"
    else:
        when = "peaks mid-hold"
    shape = "%s; seasonal index %s %+0.0f pts over the hold" % (when, trend, change_pts)
    return {"shape": shape, "trend": trend, "change_pts": change_pts,
            "peak_day": peak_day, "trough_day": trough_day}


# --------------------------------------------------------------------------- #
# edge_score - the documented, explainable blend (spec section 3)             #
# --------------------------------------------------------------------------- #

def compute_edge_score(historical_win_rate, sharpe_ratio, years_tested,
                       ml_win_prob=None, ml_available=False):
    """The ONE edge_score implementation (spec section 3). Returns (score_int, basis_str).

    edge_score = round(100 * clamp01(0.40*win_rate_n + 0.30*sharpe_n + 0.20*ml_n + 0.10*history_n))
      win_rate_n  = historical_win_rate (0..1)
      sharpe_n    = clamp(sharpe / 3.0, 0, 1)
      ml_n        = ml_win_prob if (ml_available and present) else win_rate_n  (so non-Pro still ranks)
      history_n   = clamp(years_tested / 15.0, 0, 1)
    """
    wr = _clamp01(historical_win_rate if historical_win_rate is not None else 0.0)
    sh = _num(sharpe_ratio) or 0.0
    sharpe_n = _clamp01(sh / _SHARPE_FULL)
    yt = years_tested or 0
    history_n = _clamp01(yt / _HISTORY_FULL)
    if ml_available and ml_win_prob is not None:
        ml_n = _clamp01(ml_win_prob)
        ml_src = "ml_win_prob %.2f" % ml_win_prob
    else:
        ml_n = wr  # fall back so ranking still works for non-Pro / no-ML rows
        ml_src = None
    blended = (_W_WIN * wr + _W_SHARPE * sharpe_n + _W_ML * ml_n + _W_HISTORY * history_n)
    score = round(100 * _clamp01(blended))
    # edge_basis = the dominant factors in words.
    parts = ["win_rate %.2f" % wr]
    if sh:
        parts.append("sharpe %.1f" % sh)
    if ml_src:
        parts.append(ml_src)
    parts.append("%dy history" % yt)
    basis = " x ".join(parts)
    return score, basis


# --------------------------------------------------------------------------- #
# date / framing helpers                                                       #
# --------------------------------------------------------------------------- #

def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _fmt(d):
    return d.isoformat() if d else None


def _short(d):
    """'Jul 12' style for headlines (no em-dash)."""
    return d.strftime("%b %d").replace(" 0", " ") if d else None


def _entry_window(entry_d, tol_days=3):
    if not entry_d:
        return None
    lo = entry_d - datetime.timedelta(days=tol_days)
    hi = entry_d + datetime.timedelta(days=tol_days)
    return "%s to %s" % (_fmt(lo), _fmt(hi))


# --------------------------------------------------------------------------- #
# the card builder                                                             #
# --------------------------------------------------------------------------- #

def build_signal_card(opp, stats, chart_entries, *, market_name, ml=None,
                      ml_available=False, seasonal_curve=None, as_of=None, rank=None,
                      ml_state="na"):
    """Build ONE SignalCard.

    opp:            an Opportunity dict from appserver_client (_opp_row_to_obj shape):
                    symbol, market, direction, entry_date, days_out, sharpe_ratio,
                    avg_profit_pct, median_profit_pct, win_rate, years.
    stats:          the ChartData4 publishable/raw stats dict (for win_rate, counts, sharpe).
    chart_entries:  raw ChartData4 per-year entries (for per_year receipts; price dropped).
    market_name:    resolved market name string.
    ml:             optional ML dict {ml_score, win_prob, pred_return, pred_mfe} (None if N/A).
    ml_available:   True only when caller is Pro AND market is ML-eligible.
    seasonal_curve: optional [{date, index}] for curve_summary (NOT shipped inline).
    as_of:          ISO date string the data is stamped as-of (defaults to today).
    rank:           pre-sorted rank int (the endpoint sets it; the agent never sorts).
    """
    as_of = as_of or datetime.date.today().isoformat()
    symbol = opp.get("symbol")
    direction = opp.get("direction") or "long"
    side = "BUY" if direction == "long" else "SELL"

    # --- stats (distinct historical_win_rate vs ml_win_prob) ---
    historical_win_rate = opp.get("win_rate")
    if historical_win_rate is None and isinstance(stats, dict):
        pp = stats.get("Percent Profitable")
        f = _num(pp)
        historical_win_rate = round(f / 100.0, 4) if f is not None else None

    sharpe = opp.get("sharpe_ratio")
    if sharpe is None and isinstance(stats, dict):
        sharpe = _num(stats.get("Sharpe Ratio"))
    avg_return = opp.get("avg_profit_pct")
    if avg_return is None and isinstance(stats, dict):
        avg_return = _num(stats.get("Avg Profit - All"))
    median_return = opp.get("median_profit_pct")
    if median_return is None and isinstance(stats, dict):
        median_return = _num(stats.get("Median Profit"))

    years_str = str(opp.get("years") or "10")

    # --- per-year receipts (from ChartData4 entries; net only, price dropped) ---
    # wins/losses/years_tested are derived from per_year so the receipts are internally
    # consistent (the headline 'won X/Y years' always matches the per_year rows). The
    # authoritative historical_win_rate stays the appserver's Percent Profitable above.
    per_year, wins, losses = per_year_returns(chart_entries, lookback=years_str)
    years_tested = len(per_year)

    # win rate fallback from counts only if Percent Profitable was missing entirely.
    if historical_win_rate is None and (wins + losses) > 0:
        historical_win_rate = round(wins / (wins + losses), 4)

    best, worst = _best_worst(per_year)

    # --- ml (distinct names; null for free / non-eligible) ---
    ml_block = None
    ml_win_prob = None
    if ml_available and ml:
        ml_win_prob = ml.get("win_prob")
        ml_block = {
            "ml_score": ml.get("ml_score"),
            "ml_win_prob": ml_win_prob,           # DISTINCT name from historical_win_rate
            "pred_return_pct": ml.get("pred_return"),
            "pred_mfe_pct": ml.get("pred_mfe"),
        }

    # --- edge score (the one blend) ---
    edge_score, edge_basis = compute_edge_score(
        historical_win_rate, sharpe, years_tested,
        ml_win_prob=ml_win_prob, ml_available=ml_available)

    # --- setup dates ---
    entry_d = _parse_date(opp.get("entry_date"))
    hold_days = opp.get("days_out")
    exit_d = None
    if entry_d and isinstance(hold_days, int):
        exit_d = entry_d + datetime.timedelta(days=hold_days)

    # --- trend chart SECTION: the slice of the curve over the hold window. The appserver
    # returns the curve starting at the entry date, so the first hold_days points are the
    # entry -> exit section. curve_summary describes the TREND of that section, not the year.
    section_curve = seasonal_curve
    if seasonal_curve and isinstance(hold_days, int) and hold_days > 1:
        section_curve = seasonal_curve[: hold_days + 1]
    csum = curve_summary(section_curve)

    # --- NO_SIGNAL rule (spec section 4) ---
    weak = (edge_score < MIN_EDGE_SCORE
            or (historical_win_rate is None or historical_win_rate < MIN_WIN_RATE)
            or years_tested < MIN_YEARS_TESTED)
    signal = "NO_SIGNAL" if weak else side

    # --- receipts (always present; the trust layer) ---
    receipts = {
        "years_tested": years_tested,
        "wins": wins,
        "losses": losses,
        "historical_win_rate": historical_win_rate,
        "avg_return_pct": _round(avg_return),
        "median_return_pct": _round(median_return),
        "best_year": best,
        "worst_year": worst,
        "per_year": per_year,
        "curve_summary": csum,
        "source": "TradeWave seasonal model, %sy lookback" % years_str,
        "as_of": as_of,
    }

    # --- headline + verdict (gateway-composed, mandatory) ---
    headline, verdict = _compose_text(
        symbol, direction, entry_d, hold_days, wins, losses, years_tested,
        avg_return, sharpe, historical_win_rate, signal, receipts["curve_summary"])

    # --- next_step (omit order_ticket on NO_SIGNAL) ---
    next_step = _build_next_step(symbol, side, entry_d, exit_d, hold_days, signal)

    # --- tier_notes (ML is metered per day across all tiers; ml_state set by the route) ---
    tier_notes = _ML_NOTES.get(ml_state, _ML_NOTES["na"])

    card = {
        "rank": rank,
        "symbol": symbol,
        "market": {"id": str(opp.get("market")), "name": market_name},
        "direction": direction,
        "signal": signal,
        "setup": {
            "entry_date": _fmt(entry_d),
            "entry_window": _entry_window(entry_d),
            "hold_days": hold_days,
            "exit_date": _fmt(exit_d),
        },
        "edge_score": edge_score,
        "edge_basis": edge_basis,
        "stats": {
            "historical_win_rate": historical_win_rate,
            "sharpe_ratio": _round(sharpe, 2),
            "avg_return_pct": _round(avg_return),
            "median_return_pct": _round(median_return),
            "years": years_str,
        },
        "ml": ml_block,
        "receipts": receipts,
        "next_step": next_step,
        "headline": headline,
        "verdict": verdict,
        "disclaimer": DISCLAIMER,
        "tier_notes": tier_notes,
    }
    return card


def _compose_text(symbol, direction, entry_d, hold_days, wins, losses, years_tested,
                  avg_return, sharpe, win_rate, signal, csum):
    """Build headline + verdict. No em-dashes (use ' - ')."""
    if signal == "NO_SIGNAL":
        headline = "%s %s - no high-conviction seasonal edge right now." % (symbol, direction)
        reasons = []
        if win_rate is None or win_rate < MIN_WIN_RATE:
            reasons.append("win rate below 55%")
        if years_tested < MIN_YEARS_TESTED:
            reasons.append("under 5 years of history")
        why = "; ".join(reasons) if reasons else "the blended edge is too low to act on"
        verdict = "Low conviction - %s. No setup worth placing here." % why
        return headline, verdict

    when = _short(entry_d) or "the seasonal window"
    avg_txt = ("avg %+.1f%%" % avg_return) if avg_return is not None else ""
    sharpe_txt = ("Sharpe %.1f" % sharpe) if sharpe else ""
    record = "Won %d/%d years" % (wins, wins + losses) if (wins + losses) else ""
    bits = [b for b in (record, avg_txt, sharpe_txt) if b]
    tail = (", ".join(bits) + ".") if bits else ""
    hold_txt = ("hold %dd" % hold_days) if isinstance(hold_days, int) else ""
    headline = "%s %s - enter ~%s%s. %s" % (
        symbol, direction, when, (", " + hold_txt) if hold_txt else "", tail)
    # verdict: a one-line read.
    strength = "Strong" if (win_rate or 0) >= 0.75 else "Solid"
    shape_note = ""
    if csum and csum.get("shape"):
        shape_note = " Seasonal shape: %s." % csum["shape"]
    verdict = "%s, consistent seasonal %s.%s" % (strength, direction, shape_note)
    return headline.strip(), verdict.strip()


def _build_next_step(symbol, side, entry_d, exit_d, hold_days, signal):
    """The no-broker last mile. NO price level anywhere. Omits order_ticket on NO_SIGNAL."""
    framing = "TradeWave gives the edge and the timing; you place the trade at your own broker."
    if signal == "NO_SIGNAL":
        return {
            "headline": "Nothing to act on here right now.",
            "order_ticket": None,
            "copy_text": None,
            "set_reminder": None,
            "framing": framing,
        }
    hold_note = ("Seasonal hold ~%d calendar days. Size to your own risk." % hold_days
                 if isinstance(hold_days, int) else "Size to your own risk.")
    order_ticket = {
        "side": side,
        "symbol": symbol,
        "type": "MARKET",            # no limit / price level - signals-only invariant
        "time_in_force": "DAY",
        "suggested_entry_date": _fmt(entry_d),
        "suggested_exit_date": _fmt(exit_d),
        "note": hold_note,
    }
    exit_txt = (" plan exit ~%s" % _fmt(exit_d)) if exit_d else ""
    hold_paren = (" (%dd seasonal hold)" % hold_days) if isinstance(hold_days, int) else ""
    copy_text = "%s %s market, day order;%s%s." % (side, symbol, exit_txt, hold_paren)
    reminder = None
    if entry_d:
        fire = entry_d - datetime.timedelta(days=1)
        reminder = {
            "type": "seasonal_entry",
            "fire_on": _fmt(fire),
            "message": "%s seasonal window opens tomorrow." % symbol,
        }
    return {
        "headline": "To act on this, here is a ready-to-place ticket:",
        "order_ticket": order_ticket,
        "copy_text": copy_text,
        "set_reminder": reminder,
        "framing": framing,
    }


def compact_setup(opp):
    """A compact setup+stats row for other_setups[] (no full receipts/next_step)."""
    return {
        "symbol": opp.get("symbol"),
        "direction": opp.get("direction"),
        "entry_date": opp.get("entry_date"),
        "hold_days": opp.get("days_out"),
        "historical_win_rate": opp.get("win_rate"),
        "sharpe_ratio": _round(opp.get("sharpe_ratio"), 2),
        "avg_return_pct": _round(opp.get("avg_profit_pct")),
        "median_return_pct": _round(opp.get("median_profit_pct")),
        "years": str(opp.get("years") or "10"),
    }
