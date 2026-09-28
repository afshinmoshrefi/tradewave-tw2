"""Basket scenarios for MCP/API callers (TW-TASK-0014 item 4).

Educational-only (owner policy 2026-06-08, api/MCP_INTEGRATION_ROADMAP.md): a basket is a
hypothetical list of symbols with percentage WEIGHTS - never a user's holdings, share counts,
cost basis, dollar amounts or P&L - and the output describes historical data only.

Mirrors the app's Portfolio Scenarios horizon math (appserver/appserver/portfolio_scenarios.py
build_horizon) in percentages: every symbol is measured over the same start date and horizon,
restricted to the completed years all symbols share, and each year's basket result is the sum
of each weight times that symbol's return that year. Pure functions - the route fetches evidence.
"""

import datetime
import statistics

from .cards import _net_pct
from .seasonal_evidence import completed_entries

HORIZON_KEYS = ("30", "60", "90", "eoy", "custom")


def horizon_window(start, key, custom_days=None):
    """(end_date, inclusive calendar days) for one horizon, exactly as the app computes it."""
    if key == "eoy":
        end = datetime.date(start.year, 12, 31)
    else:
        end = start + datetime.timedelta(days=(custom_days if key == "custom" else int(key)) - 1)
    return end, (end - start).days + 1


def annual_returns(chart_entries, direction="long"):
    """{year: trade return %} from completed engine rows; a short flips the sign (app rule)."""
    out = {}
    for entry in completed_entries(chart_entries or []):
        pct = _net_pct(entry.get("pct"))
        if pct is None:
            continue
        out[int(entry.get("year"))] = pct if direction == "long" else -pct
    return out


def horizon(basket, annual_by_symbol, start, end, days, key, benchmark=None):
    """basket: [{symbol, direction, weight_pct}] with weights summing to 100;
    annual_by_symbol: {symbol: {year: pct}}. benchmark: optional (symbol, {year: pct})
    measured on the basket's shared years. All results are percentages."""
    common = None
    for b in basket:
        years = set(annual_by_symbol[b["symbol"]])
        common = years if common is None else common & years
    years = sorted(common or [])
    outcomes = []
    for year in years:
        contributions = [{"symbol": b["symbol"],
                          "return_pct": round(annual_by_symbol[b["symbol"]][year], 2),
                          "contribution_pct": round(b["weight_pct"] * annual_by_symbol[b["symbol"]][year] / 100, 2)}
                         for b in basket]
        change = sum(b["weight_pct"] * annual_by_symbol[b["symbol"]][year] / 100 for b in basket)
        outcomes.append({"year": year, "change_pct": round(change, 2), "contributions": contributions})
    changes = [o["change_pct"] for o in outcomes]
    detail = []
    for b in basket:
        values = [annual_by_symbol[b["symbol"]][y] for y in years]
        mean_pct = statistics.mean(values) if values else None
        detail.append({
            "symbol": b["symbol"], "direction": b["direction"], "weight_pct": round(b["weight_pct"], 2),
            "mean_return_pct": None if mean_pct is None else round(mean_pct, 2),
            "mean_contribution_pct": None if mean_pct is None else round(b["weight_pct"] * mean_pct / 100, 2),
            "positive": sum(v > 0 for v in values), "flat": sum(v == 0 for v in values),
            "negative": sum(v < 0 for v in values), "count": len(values),
            "years_available": len(annual_by_symbol[b["symbol"]]),
        })
    best = max(outcomes, key=lambda o: o["change_pct"], default=None)
    worst = min(outcomes, key=lambda o: o["change_pct"], default=None)
    result = {
        "key": key, "start_date": start.isoformat(), "end_date": end.isoformat(), "days": days,
        "mean_change_pct": round(statistics.mean(changes), 2) if changes else None,
        "median_change_pct": round(statistics.median(changes), 2) if changes else None,
        "best_year": {"year": best["year"], "change_pct": best["change_pct"]} if best else None,
        "worst_year": {"year": worst["year"], "change_pct": worst["change_pct"]} if worst else None,
        "positive": sum(c > 0 for c in changes), "flat": sum(c == 0 for c in changes),
        "negative": sum(c < 0 for c in changes),
        "coverage": {
            "common_years": years, "count": len(years),
            "available_by_symbol": [{"symbol": b["symbol"], "years": len(annual_by_symbol[b["symbol"]])}
                                    for b in basket],
            "excluded_years": sorted(set().union(*(set(annual_by_symbol[b["symbol"]]) for b in basket))
                                     - set(years)),
        },
        "annual_outcomes": outcomes,
        "symbols": detail,
    }
    if benchmark:
        sym, annual = benchmark
        shared = [y for y in years if y in annual]
        if shared:
            values = [annual[y] for y in shared]
            result["benchmark"] = {
                "symbol": sym, "years_compared": len(shared),
                "mean_change_pct": round(statistics.mean(values), 2),
                "median_change_pct": round(statistics.median(values), 2),
                "worst_change_pct": round(min(values), 2), "best_change_pct": round(max(values), 2),
                "years_basket_beat_benchmark": sum(
                    1 for o in outcomes if o["year"] in annual and o["change_pct"] > annual[o["year"]]),
            }
    return result


def summary(h):
    """Deterministic plain-English lines for one horizon - numbers only from the result."""
    if not h["coverage"]["count"]:
        return ["These symbols share no completed year for this horizon, so no scenario can be built."]
    n = h["coverage"]["count"]
    lines = ["Over the last %d shared years, from %s to %s this basket changed %+.1f%% on average "
             "(middle year %+.1f%%); it rose in %d of %d years."
             % (n, h["start_date"], h["end_date"], h["mean_change_pct"], h["median_change_pct"],
                h["positive"], n)]
    lines.append("Worst year %s: %+.1f%%. Best year %s: %+.1f%%."
                 % (h["worst_year"]["year"], h["worst_year"]["change_pct"],
                    h["best_year"]["year"], h["best_year"]["change_pct"]))
    b = h.get("benchmark")
    if b:
        lines.append("%s over the same %d years: %+.1f%% on average, worst %+.1f%%; the basket did "
                     "better in %d of them." % (b["symbol"], b["years_compared"], b["mean_change_pct"],
                                                b["worst_change_pct"], b["years_basket_beat_benchmark"]))
    short = [a for a in h["coverage"]["available_by_symbol"] if a["years"] == n]
    longest = max(a["years"] for a in h["coverage"]["available_by_symbol"])
    if short and longest > n:
        lines.append("%s limits the shared history to %d years." % (", ".join(a["symbol"] for a in short), n))
    lines.append("Historical outcomes are research, not a forecast.")
    return lines
