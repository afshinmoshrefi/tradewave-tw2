"""Same-window symbol comparison (TW-TASK-0014 item 3).

Mirrors the app's Symbol Comparison report (web-react analysisReportData.js): every symbol is
measured on ONE shared setup and restricted to the completed years all symbols share, then the
report metrics are recomputed on those years. Pure functions - the route fetches the evidence.
"""

import statistics

from .cards import _excursions, buy_hold_benchmark
from .seasonal_evidence import completed_entries

MINIMUM_COMMON_YEARS = 5   # the app's rangeComparisonHistoryPlan minimum


def yearly_results(chart_entries, direction="long"):
    """Completed per-year trade results {year, return_pct, mfe_pct, mae_pct}, direction-aware
    exactly like the app's chartRowResult (a short swaps and flips the excursions)."""
    rows = []
    for entry in completed_entries(chart_entries or []):
        net, high, low = _excursions(entry.get("pct"))
        net, high, low = net or 0.0, high or 0.0, low or 0.0
        if direction == "short":
            net, high, low = -net, -low, -high
        rows.append({"year": int(entry.get("year")), "return_pct": round(net, 2),
                     "mfe_pct": round(high, 2), "mae_pct": round(low, 2)})
    return sorted(rows, key=lambda row: row["year"])


def _round(value):
    return None if value is None else round(value, 2)


def metrics(results, days_out, risk_free_pct=4.0):
    """The app's comparison metrics for one symbol over the given yearly results."""
    returns = [r["return_pct"] for r in results]
    if not returns:
        return {"sample_years": 0}
    average = statistics.mean(returns)
    stdev = statistics.stdev(returns) if len(returns) > 1 else 0
    winners = sum(1 for value in returns if value >= 0)
    growth = 1.0
    for value in returns:
        growth *= 1 + value / 100
    return {
        "sample_years": len(returns),
        "average_return_pct": _round(average),
        "median_return_pct": _round(statistics.median(returns)),
        "profitable_pct": _round(100 * winners / len(returns)),
        "winners": winners,
        "losers": len(returns) - winners,
        "best_return_pct": _round(max(returns)),
        "worst_return_pct": _round(min(returns)),
        "average_mfe_pct": _round(statistics.mean(r["mfe_pct"] for r in results)),
        "average_mae_pct": _round(statistics.mean(r["mae_pct"] for r in results)),
        "worst_mae_pct": _round(min(r["mae_pct"] for r in results)),
        "sharpe_ratio": _round((average - risk_free_pct * (days_out / 365)) / stdev) if stdev > 0 else 0,
        "cumulative_return_pct": _round((growth - 1) * 100),
    }


def compare(symbol_rows, days_out, max_years=None, buy_hold=None):
    """symbol_rows: {symbol: yearly_results}. Restricts every symbol to the completed years ALL
    symbols share (latest max_years of them), recomputes metrics, and explains the result.
    buy_hold: optional {symbol: buy-and-hold chart entries} for a same-years benchmark."""
    available = {sym: [r["year"] for r in rows] for sym, rows in symbol_rows.items()}
    common = sorted(set.intersection(*(set(years) for years in available.values()))) if available else []
    if max_years:
        common = common[-int(max_years):]
    common_set = set(common)
    rows = []
    for sym, results in symbol_rows.items():
        shared = [r for r in results if r["year"] in common_set]
        row = {"symbol": sym, "years_available": len(results),
               "metrics": metrics(shared, days_out), "yearly_results": shared}
        if buy_hold and buy_hold.get(sym):
            bench = buy_hold_benchmark(
                [{"year": str(r["year"]), "return_pct": r["return_pct"]} for r in shared],
                buy_hold[sym])
            if bench:
                row["benchmark"] = bench
                row["metrics"]["beats_buy_hold"] = bench["beats_buy_hold"]
        rows.append(row)
    return {
        "common_years": common,
        "years_used": len(common),
        "can_compare": len(common) >= MINIMUM_COMMON_YEARS,
        "minimum_years": MINIMUM_COMMON_YEARS,
        "rows": rows,
        "findings": findings(rows, common, max_years),
    }


def _leaders(rows, key, lowest=False):
    """Every symbol tied for the best value of key (ties are named, never hidden)."""
    usable = [r for r in rows if r["metrics"].get(key) is not None]
    if not usable:
        return []
    best = (min if lowest else max)(r["metrics"][key] for r in usable)
    return [r for r in usable if r["metrics"][key] == best]


def _names(rows):
    names = [r["symbol"] for r in rows]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def findings(rows, common, max_years=None):
    """Plain-English, deterministic findings - numbers only from the metrics above."""
    out = []
    if not common:
        return ["These symbols share no completed year for this setup, so they cannot be "
                "compared fairly."]
    n = len(common)
    avg = _leaders(rows, "average_return_pct")
    if avg:
        out.append("%s had the highest average return, %+.1f%% per year over the %d shared years."
                   % (_names(avg), avg[0]["metrics"]["average_return_pct"], n))
    cons = _leaders(rows, "profitable_pct")
    if cons:
        m = cons[0]["metrics"]
        out.append("%s %s profitable most often, in %d of %d years."
                   % (_names(cons), "was" if len(cons) == 1 else "were", m["winners"], m["sample_years"]))
    deep = _leaders(rows, "worst_mae_pct", lowest=True)
    if deep:
        out.append("%s had the deepest drop inside the window, %.1f%% at its worst point."
                   % (_names(deep), deep[0]["metrics"]["worst_mae_pct"]))
    short = [r for r in rows if r["years_available"] == min(x["years_available"] for x in rows)]
    longest = max(r["years_available"] for r in rows)
    wanted = int(max_years) if max_years else longest
    if short and short[0]["years_available"] < min(wanted, longest):
        out.append("%s has only %d years of history for this setup, so every symbol is compared "
                   "on the same %d shared years; %s alone has %d."
                   % (", ".join(r["symbol"] for r in short), short[0]["years_available"], n,
                      max(rows, key=lambda r: r["years_available"])["symbol"], longest))
    if n < MINIMUM_COMMON_YEARS:
        out.append("Only %d shared years - fewer than the %d needed for a fair comparison."
                   % (n, MINIMUM_COMMON_YEARS))
    return out
