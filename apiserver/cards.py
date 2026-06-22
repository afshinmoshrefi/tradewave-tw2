"""PatternCard builder - the ONE source of truth for the flagship card object.

Implements api/PATTERNCARD_SPEC.md sections 1-5. The gateway endpoints (/v1/scan,
/v1/analyze/<symbol>, /v1/daily-pick) all build their cards HERE so headline/verdict/
edge_score/receipts are composed identically and exactly once.

Hard invariants enforced here (mirrors the spec):
- DERIVED SEASONAL PATTERNS ONLY. No raw OHLCV / last price / price level / limit price is
  ever placed on a card. All movement is percentages; the seasonal curve is a 0-100 index.
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
    "Educational seasonal pattern + ML research, not personalized investment advice and not a "
    "recommendation to buy or sell. Past performance is not indicative of future results."
)

# neutral / low-conviction thresholds (spec section 4).
MIN_EDGE_SCORE = 40
MIN_WIN_RATE = 0.55
MIN_YEARS_TESTED = 5

# Stamped on a card whose receipts FAILED to load (429/timeout/upstream error - an outage,
# not a data gap). The card keeps the OppList-level stats and must never read as a
# confident "no edge" manufactured from missing data.
RECEIPTS_UNAVAILABLE_NOTE = (
    "Per-year receipts could not be loaded right now (upstream data temporarily "
    "unavailable - retry shortly). This is an outage, not a data gap: the setup stats "
    "from the opportunity scan are shown unverified."
)

# tier_notes for the ML state of a card (ML is metered per day across all tiers now).
_ML_NOTES = {
    "shown": "ML score shown.",
    "quota": "Daily ML limit reached on your plan - upgrade for unlimited ML scoring.",
    "market": "ML not available for this market (ML covers US stocks, indices and ETFs).",
    "unavailable": "ML score not available for this setup - the ML model covers shorter seasonal holds (up to about 90 days).",
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


def _excursions(pct_str):
    """ChartData4 per-year `pct` is 'net,mfe,mae' - three PERCENTAGES, never prices.
    Parse all three. By the appserver's (long-relative) convention: net is the trade's
    net % move, mfe (max favorable excursion) is the highest the move reached and is >= 0,
    mae (max adverse excursion) is the lowest it reached and is <= 0. Returns
    (net, mfe, mae) floats with None for any missing/blank field. No price is ever read."""
    if pct_str is None:
        return None, None, None
    parts = [p.strip() for p in str(pct_str).split(",")]
    net = _num(parts[0]) if len(parts) >= 1 else None
    mfe = _num(parts[1]) if len(parts) >= 2 else None
    mae = _num(parts[2]) if len(parts) >= 3 else None
    return net, mfe, mae


# --------------------------------------------------------------------------- #
# per-year receipts from ChartData4 entries                                   #
# --------------------------------------------------------------------------- #

def per_year_returns(chart_entries, lookback=None, direction="long"):
    """Build the per-year receipt rows from raw ChartData4 entries.

    Each entry is {'year': 2024, 'pct': 'net,mfe,mae', 'price': '...'}. We use ONLY the
    net pct; `price` is dropped (price-safety invariant). The appserver appends an entry
    for the in-progress current year; when that window has not run yet it is an all-zero
    stub (net,mfe,mae == 0,0,0) and is NOT a completed year - we exclude it (it would fake
    an extra 'loss' row). A current-year entry the appserver HAS scored (a real non-zero
    partial) is kept, so per_year stays consistent with the appserver's own Percent
    Profitable / Num Winners counts (which include it).

    win = the TRADE's net% > 0 (sign-flipped for shorts, since a short profits when the
    underlying falls); no threshold - matches the UI's direction-aware 'Percent Profitable'. The list is
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
        # The receipt is the TRADE's return: a short profits when the underlying
        # falls, so flip the sign for shorts before deciding win/loss. This keeps
        # per_year / wins / losses / best / worst consistent with the direction-aware
        # historical_win_rate + avg_profit the appserver reports.
        pnl = -net if direction == "short" else net
        rows.append({
            "year": str(e.get("year")),
            "return_pct": round(pnl, 2),
            "result": "win" if pnl > 0 else "loss",
        })
    # bound at lookback + 1 (history + the at-most-one current partial); drop the OLDEST
    # beyond that so the most recent years are kept. This only trims runaway lists; the
    # normal case (10 history + 1 partial) passes through untouched.
    if cap is not None and len(rows) > cap + 1:
        rows = rows[-(cap + 1):]
    wins = sum(1 for r in rows if r["result"] == "win")
    losses = sum(1 for r in rows if r["result"] == "loss")
    return rows, wins, losses


def per_year_bars(chart_entries, direction="long"):
    """Per-year bars for the Trend Chart visualization: each completed year's TRADE return
    PLUS its favorable / adverse excursion band, all as PERCENTAGES (never prices). Built
    from the same ChartData4 entries as per_year_returns, with the unscored in-progress
    current year (all-zero stub) excluded identically so bars and receipts stay consistent.

    Direction-aware, mirroring per_year_returns: a SHORT profits when the underlying falls,
    so net is sign-flipped AND the excursions swap and flip (a short's favorable excursion is
    the long's adverse move, and vice versa): trade_mfe = -mae_long, trade_mae = -mfe_long.
    The result is always trade-relative: net_pct > 0 = a winning year, mfe_pct >= 0 (best the
    trade ran in its favor), mae_pct <= 0 (worst it ran against). Returns a chronological
    list of {year, net_pct, mfe_pct, mae_pct, result}."""
    bars = []
    if not isinstance(chart_entries, list):
        return bars
    for e in chart_entries:
        if not isinstance(e, dict):
            continue
        net, mfe, mae = _excursions(e.get("pct"))
        if net is None:
            continue
        parts = str(e.get("pct", "")).split(",")
        if parts and all(_num(x) == 0.0 for x in parts):
            continue  # unscored in-progress current year - not a completed bar
        if direction == "short":
            t_net = -net
            t_mfe = (-mae) if mae is not None else None
            t_mae = (-mfe) if mfe is not None else None
        else:
            t_net, t_mfe, t_mae = net, mfe, mae
        bars.append({
            "year": str(e.get("year")),
            "net_pct": round(t_net, 2),
            "mfe_pct": round(t_mfe, 2) if t_mfe is not None else None,
            "mae_pct": round(t_mae, 2) if t_mae is not None else None,
            "result": "win" if t_net > 0 else "loss",
        })
    return bars


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
    passes the already-sliced section (build_pattern_card slices the curve to hold_days,
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


def _timing(entry_d, exit_d, as_of_str):
    """Where the trade window sits relative to as_of (today by default) so the agent can
    judge urgency without doing date math. days_to_entry < 0 means the window already
    opened; status is a plain-language read. Calendar days, no price."""
    if not entry_d:
        return None
    today = _parse_date(as_of_str) or datetime.date.today()
    d2e = (entry_d - today).days
    if d2e > 1:
        status = "window opens in %d days" % d2e
    elif d2e == 1:
        status = "window opens tomorrow"
    elif d2e == 0:
        status = "window opens today"
    elif exit_d and today <= exit_d:
        status = "in the entry window now"
    else:
        status = "window has passed for this cycle"
    return {"days_to_entry": d2e, "status": status}


def _pattern_alignment(historical_win_rate, ml_win_prob, ml_available):
    """Does the per-instance ML view AGREE with the in-sample seasonal win rate? A quick
    'do both point the same way' read. Only a cross-check when an ML score is present
    (Pro / ML-eligible market); otherwise it is seasonal-only. NEVER conflates the two
    distinct win-rate fields - it compares them."""
    if not (ml_available and ml_win_prob is not None and historical_win_rate is not None):
        return {"verdict": "seasonal_only",
                "note": "Seasonal edge only - no ML score on this setup to cross-check."}
    hi, lo = 0.60, 0.50
    s_strong, m_strong = historical_win_rate >= hi, ml_win_prob >= hi
    if s_strong and m_strong:
        return {"verdict": "aligned",
                "note": "ML confirms the seasonal edge (both above 60%)."}
    if historical_win_rate < lo and ml_win_prob < lo:
        return {"verdict": "aligned_weak",
                "note": "ML and seasonal agree this looks weak (both below 50%)."}
    if s_strong and ml_win_prob < lo:
        return {"verdict": "divergent",
                "note": "Seasonal is strong but ML is cautious - treat as lower conviction."}
    if m_strong and historical_win_rate < lo:
        return {"verdict": "divergent",
                "note": "ML is constructive but the seasonal record is thin - lower conviction."}
    return {"verdict": "mixed", "note": "ML and seasonal are only partly aligned."}


def _extend_research(symbol, direction, entry_d, exit_d, hold_days):
    """The structured research hand-off carried on every card. TradeWave supplies a SEASONAL
    + ML statistical edge and the timing; the assistant is told, in machine-readable form, to
    extend it with its OWN news / fundamentals / macro tools and synthesize. The actionable
    twin of the MCP envelope hand-off, specialized to THIS setup. No price, no advice."""
    if entry_d and exit_d:
        win = "%s to %s" % (_fmt(entry_d), _fmt(exit_d))
    elif entry_d and isinstance(hold_days, int):
        win = "%s for ~%dd" % (_fmt(entry_d), hold_days)
    else:
        win = None
    earnings_check = ("Does an earnings report fall inside the %s window? TradeWave does not "
                      "track earnings - check your own calendar." % (win if win else "trade"))
    return {
        "tradewave_provides": ("A seasonal + 62-feature-ML statistical edge and the timing "
                               "for %s (%s)." % (symbol, direction)),
        "blind_to": ["fundamentals", "valuation", "news", "catalysts", "macro/rates",
                     "analyst views", "upcoming earnings", "live price"],
        "suggested_checks": [
            earnings_check,
            "Any scheduled catalyst (product, FDA, guidance, macro print) during the hold?",
            "Recent news or price action that would invalidate a %s bias on %s?" % (direction, symbol),
            "Is the sector / macro backdrop consistent with a %s here?" % direction,
            "What do current fundamentals or valuation say versus this purely seasonal read?",
        ],
        "loop_back": ("If your findings change the picture, call analyze_symbol again with a "
                      "tighter window, compare_opportunities to rank peers, or "
                      "get_pick_track_record for the live forward-tested record."),
        "synthesis_rule": ("Keep explicit which facts are TradeWave's (this card) versus your "
                           "own research. Do NOT invent a catalyst to justify the seasonal edge; "
                           "if there is none, the edge stands on the statistics alone."),
    }


# --------------------------------------------------------------------------- #
# the card builder                                                             #
# --------------------------------------------------------------------------- #

def build_pattern_card(opp, stats, chart_entries, *, market_name, ml=None,
                      ml_available=False, seasonal_curve=None, as_of=None, rank=None,
                      ml_state="na", include_chart=False, receipts_unavailable=False):
    """Build ONE PatternCard.

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
    receipts_unavailable: True when the ChartData4 receipts FETCH FAILED (429/timeout/
                    error - not a data gap). The card is stamped receipts_unavailable,
                    keeps the OppList-level stats and detected pattern, and its verdict degrades to
                    "data temporarily unavailable" - NEVER to a confident no-edge.
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

    # --- extended stats (un-stripped): dispersion + annualized/cumulative return + the
    # MFE-based Sharpe, all PERCENTAGES / ratios (pattern-safe; no price or level). IMPORTANT
    # direction note: unlike the per-year `pct` entries (which the appserver emits LONG-relative,
    # so per_year_returns / per_year_bars sign-flip them for shorts), these AGGREGATE stats are
    # computed by the appserver from a direction-adjusted array (it flips pctArray for shorts
    # BEFORE deriving Annualized/Cumulative Return and Sharpe Ratio2). They therefore arrive
    # ALREADY TRADE-RELATIVE (profit-signed) - re-flipping here would be a double-flip. std_dev is
    # a dispersion and is sign-invariant. So: take all four as-is. ---
    _stats = stats if isinstance(stats, dict) else {}
    std_dev = _num(_stats.get("Std Dev"))
    annualized = _num(_stats.get("Annualized Return"))
    cumulative = _num(_stats.get("Cumulative Return"))
    sharpe_mfe = _num(_stats.get("Sharpe Ratio2"))
    std_dev_pct = round(std_dev, 2) if std_dev is not None else None
    annualized_pct = round(annualized, 2) if annualized is not None else None
    cumulative_pct = round(cumulative, 2) if cumulative is not None else None
    sharpe_mfe = round(sharpe_mfe, 2) if sharpe_mfe is not None else None

    years_str = str(opp.get("years") or "10")

    # --- per-year receipts (from ChartData4 entries; net only, price dropped) ---
    # wins/losses/years_tested are derived from per_year so the receipts are internally
    # consistent (the headline 'won X/Y years' always matches the per_year rows), and
    # historical_win_rate is derived from those SAME counts below (chart-consistent), not the
    # appserver's aggregate Percent Profitable (which has disagreed with the year-by-year rows).
    if receipts_unavailable:
        per_year, wins, losses = [], 0, 0
        years_tested = None
        # ranking proxy: the requested lookback (detection already required most of those
        # years to win) - the receipts that would prove it just could not be fetched.
        years_for_edge = int(years_str) if years_str.isdigit() else 0
    else:
        per_year, wins, losses = per_year_returns(chart_entries, lookback=years_str,
                                                  direction=direction)
        years_tested = len(per_year)
        years_for_edge = years_tested
        # historical_win_rate MUST match the per-year rows - the SAME data the bar chart and the
        # headline 'Won X/Y years' (= wins/(wins+losses), line ~655) show. The appserver's aggregate
        # win_rate / Percent Profitable has come back DISAGREEING with the year-by-year rows (e.g.
        # 0.6 for a 4/10 setup), yielding a card whose win rate the chart contradicts. Derive it from
        # the counts here, the chart-consistent source. (The appserver value survives only as the
        # receipts_unavailable fallback above, when the per-year rows could not be fetched.)
        if (wins + losses) > 0:
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
        historical_win_rate, sharpe, years_for_edge,
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

    # --- neutral rule (spec section 4) ---
    if receipts_unavailable:
        # Receipts FAILED to load - an outage is never evidence of absence. Only a LOADED
        # weak win rate may down-rate the setup; an unknown one keeps the OppList-detected
        # pattern with an explicit unavailability note instead of a manufactured neutral.
        weak = historical_win_rate is not None and historical_win_rate < MIN_WIN_RATE
    else:
        weak = (edge_score < MIN_EDGE_SCORE
                or (historical_win_rate is None or historical_win_rate < MIN_WIN_RATE)
                or years_tested < MIN_YEARS_TESTED)
    bias = "neutral" if weak else ("bullish" if direction == "long" else "bearish")

    # --- receipts (always present; the trust layer) ---
    if receipts_unavailable:
        receipts = {
            "receipts_unavailable": True,
            "note": RECEIPTS_UNAVAILABLE_NOTE,
            "years_tested": None,
            "historical_win_rate": historical_win_rate,
            "avg_return_pct": _round(avg_return),
            "median_return_pct": _round(median_return),
            "per_year": [],
            "curve_summary": csum,
            "source": "TradeWave seasonal model, %sy lookback" % years_str,
            "as_of": as_of,
        }
    else:
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
        avg_return, sharpe, historical_win_rate, bias, receipts["curve_summary"],
        receipts_unavailable=receipts_unavailable)

    # --- next_step (omit order_ticket on neutral) ---
    next_step = _build_next_step(symbol, side, entry_d, exit_d, hold_days, bias)

    # --- tier_notes (ML is metered per day across all tiers; ml_state set by the route) ---
    tier_notes = _ML_NOTES.get(ml_state, _ML_NOTES["na"])

    card = {
        "rank": rank,
        "symbol": symbol,
        "market": {"id": str(opp.get("market")), "name": market_name},
        "direction": direction,
        "bias": bias,
        "setup": {
            "entry_date": _fmt(entry_d),
            "entry_window": _entry_window(entry_d),
            "hold_days": hold_days,
            "exit_date": _fmt(exit_d),
            "timing": _timing(entry_d, exit_d, as_of),
        },
        "edge_score": edge_score,
        "edge_basis": edge_basis,
        "stats": {
            "historical_win_rate": historical_win_rate,
            "sharpe_ratio": _round(sharpe, 2),
            "sharpe_ratio_mfe": sharpe_mfe,
            "avg_return_pct": _round(avg_return),
            "median_return_pct": _round(median_return),
            "std_dev_pct": std_dev_pct,
            "annualized_return_pct": annualized_pct,
            "cumulative_return_pct": cumulative_pct,
            "years": years_str,
        },
        "ml": ml_block,
        "alignment": _pattern_alignment(historical_win_rate, ml_win_prob, ml_available),
        "receipts": receipts,
        "extend_research": _extend_research(symbol, direction, entry_d, exit_d, hold_days),
        "next_step": next_step,
        "headline": headline,
        "verdict": verdict,
        "disclaimer": DISCLAIMER,
        "tier_notes": tier_notes,
    }
    # --- optional inline chart DATA (include=chart): the Trend Chart curve + per-year bars in
    # one payload so the client can draw without a second round-trip. All percentages / a 0-100
    # index - never a price. ---
    if include_chart:
        card["chart"] = {
            "trend_chart": [{"date": p.get("date"), "index": p.get("index")}
                            for p in (seasonal_curve or []) if isinstance(p, dict)],
            "per_year_bars": per_year_bars(chart_entries, direction),
            "note": ("trend_chart is the normalized 0-100 seasonal index (one point per day, "
                     "entry-anchored); per_year_bars are each year's trade return with its "
                     "favorable (mfe) / adverse (mae) excursion band. Percentages, never prices."),
        }
    return card


def _compose_text(symbol, direction, entry_d, hold_days, wins, losses, years_tested,
                  avg_return, sharpe, win_rate, bias, csum, receipts_unavailable=False):
    """Build headline + verdict. No em-dashes (use ' - ').

    receipts_unavailable: the per-year receipts FAILED to load (outage, not a data gap).
    neutral can then only mean a LOADED weak win rate, so the absence-derived reasons
    ('under 5 years of history') are never claimed, and a non-weak verdict degrades to
    'data temporarily unavailable' instead of asserting a verified record."""
    if bias == "neutral":
        headline = "%s %s - no high-conviction seasonal edge right now." % (symbol, direction)
        reasons = []
        if win_rate is not None and win_rate < MIN_WIN_RATE:
            reasons.append("win rate below 55%")
        elif win_rate is None and not receipts_unavailable:
            reasons.append("win rate below 55%")
        if not receipts_unavailable and (years_tested or 0) < MIN_YEARS_TESTED:
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
    if receipts_unavailable:
        verdict = ("Receipts temporarily unavailable - the per-year record could not be "
                   "loaded right now (upstream rate limit/outage), so this setup is "
                   "unverified. The scan-level stats stand; retry shortly for the full "
                   "receipts.")
        return headline.strip(), verdict
    # verdict: a one-line read.
    strength = "Strong" if (win_rate or 0) >= 0.75 else "Solid"
    shape_note = ""
    if csum and csum.get("shape"):
        shape_note = " Seasonal shape: %s." % csum["shape"]
    verdict = "%s, consistent seasonal %s.%s" % (strength, direction, shape_note)
    return headline.strip(), verdict.strip()


def _build_next_step(symbol, side, entry_d, exit_d, hold_days, bias):
    """The no-broker last mile. NO price level anywhere. Omits order_ticket on neutral."""
    framing = "TradeWave gives the edge and the timing; you place the trade at your own broker."
    if bias == "neutral":
        # Spec: OMIT order_ticket/copy_text/set_reminder on neutral (nothing to act on) -
        # the keys are absent, not present-but-null, so `'order_ticket' in next_step` is false.
        return {
            "headline": "Nothing to act on here right now.",
            "framing": framing,
        }
    hold_note = ("Seasonal hold ~%d calendar days. Size to your own risk." % hold_days
                 if isinstance(hold_days, int) else "Size to your own risk.")
    order_ticket = {
        "side": side,
        "symbol": symbol,
        "type": "MARKET",            # no limit / price level - seasonal-pattern-only invariant
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


# --------------------------------------------------------------------------- #
# progressive disclosure - view projection (the fix for "too much info")      #
# --------------------------------------------------------------------------- #

# The lean 'decision' view keeps the read + the next move and DROPS the heavy detail (the
# per_year[] array, the full chart, the extended stats). The agent re-requests view='full'
# when it actually needs the receipts.
_DECISION_RECEIPT_KEYS = ("receipts_unavailable", "note", "years_tested", "wins", "losses",
                          "historical_win_rate", "avg_return_pct", "best_year", "worst_year",
                          "curve_summary", "live_track_record", "source", "as_of")
_DECISION_STAT_KEYS = ("historical_win_rate", "sharpe_ratio", "avg_return_pct", "years")


def project_card(card, view="full"):
    """Shape a built card for the requested verbosity (progressive disclosure):
      'full'     - everything (the default for the raw API; backward-compatible).
      'decision' - the lean read: bias + verdict + setup/timing + edge + ml + alignment +
                   the research hand-off + next_step, with the heavy arrays (receipts.per_year,
                   chart, detail stats) trimmed. The agent re-requests 'full' for receipts.
      'table'    - a single flat row (for compact multi-card list rendering).
    Disclaimer handling: 'full' and 'decision' keep the exact per-card `disclaimer` (spec: every
    card carries it). 'table' omits it from the compact row for brevity - the endpoints add a
    response-level `disclaimer`, and the MCP envelope hoists exactly one, so it is never dropped
    from a response."""
    if not isinstance(card, dict):
        return card
    if view == "table":
        return _card_row(card)
    if view != "decision":
        return card  # 'full' (and any unknown value) -> untouched
    out = dict(card)
    # NB: a `chart` block is only ever present when the caller explicitly asked include=chart,
    # so it is preserved across views (they opted into that payload). edge_basis is detail.
    out.pop("edge_basis", None)
    # Token trim: the per-card extend_research block is the largest fixed-cost text on a
    # multi-card scan and is identical methodology per card; the MCP envelope hand-off
    # already carries it once per response. 'full' keeps it.
    out.pop("extend_research", None)
    stats = card.get("stats")
    if isinstance(stats, dict):
        out["stats"] = {k: stats[k] for k in _DECISION_STAT_KEYS if k in stats}
    rec = card.get("receipts")
    if isinstance(rec, dict):
        out["receipts"] = {k: rec[k] for k in _DECISION_RECEIPT_KEYS if k in rec}
    return out


def _card_row(card):
    """A compact one-line row for view='table' - the decision essentials only."""
    stats = card.get("stats") or {}
    ml = card.get("ml") or {}
    setup = card.get("setup") or {}
    market = card.get("market") or {}
    row = {
        "rank": card.get("rank"),
        "symbol": card.get("symbol"),
        "market": market.get("name") or market.get("id"),
        "direction": card.get("direction"),
        "bias": card.get("bias"),
        "entry_date": setup.get("entry_date"),
        "hold_days": setup.get("hold_days"),
        "edge_score": card.get("edge_score"),
        "historical_win_rate": stats.get("historical_win_rate"),
        "ml_win_prob": ml.get("ml_win_prob"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "headline": card.get("headline"),
    }
    # the honesty flag survives the compact projection - a row built on a failed receipts
    # fetch must never read as a verified one.
    if (card.get("receipts") or {}).get("receipts_unavailable"):
        row["receipts_unavailable"] = True
    return row
