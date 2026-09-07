"""One completed, direction-aware cohort for gateway statistics and receipts.

ChartData4 rows contain underlying returns, even when its aggregate direction is
short. Completion is independent of profit: an unfinished gain is not a win and
a completed flat year is still an observation. This module never reads prices.
"""
import calendar
import datetime
import math
import statistics
from zoneinfo import ZoneInfo


def market_today():
    return datetime.datetime.now(ZoneInfo("America/New_York")).date()


def number(value):
    try:
        result = float(str(value).strip().rstrip("%").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def completed_entries(entries, *, entry_date=None, days_out=None, as_of=None, lookback=None):
    """Select completed observations, with a fallback for older engine responses.

Consecutive N means N prior entry years plus the current year if completed;
PE-N already selects N completed matching phases in the engine. Never impose an
exact-N cap on a consecutive cohort or count a current partial as completed.
"""
    cutoff = _date(as_of) or market_today()
    entry = _date(entry_date)
    days = number(days_out)
    rows = {}
    for row in entries if isinstance(entries, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            year = int(row.get("year"))
        except (TypeError, ValueError):
            continue
        if not 1 <= year <= 9999:
            continue
        parts = str(row.get("pct", "")).split(",")
        if number(parts[0]) is None:
            continue
        if row.get("completed") is False:
            continue
        if row.get("completed") is not True:
            if entry and days is not None:
                start = entry.replace(year=year, day=min(entry.day, calendar.monthrange(year, entry.month)[1]))
                end = start + datetime.timedelta(days=max(0, int(days) - 1))
                # Legacy ChartData4 keeps the same month/day across leap years.
                if calendar.isleap(end.year) and start <= datetime.date(end.year, 2, 29) <= end:
                    end += datetime.timedelta(days=1)
                if end > cutoff:
                    continue
            elif year >= cutoff.year or all(number(part) == 0 for part in parts):
                # Without a window, an unlabelled current year cannot establish completion.
                continue
        rows[year] = {**row, "completed": True}
    result = [rows[year] for year in sorted(rows)]
    if str(lookback or "").isdigit():
        result = result[-(int(lookback) + 1):]
    return result


def coherent_stats(stats, entries, direction, days_out=None):
    """Replace all receipt-derived aggregates using exactly the supplied cohort.

Sharpe uses the engine's configured risk-free rate when supplied. During a
rolling deployment, retain a legacy Sharpe only if the engine confirms the same
direction; an opposite-side ratio must never be relabelled.
"""
    raw = stats if isinstance(stats, dict) else {}
    result = dict(raw)
    same_direction = str(raw.get("Trade Dir", "")).lower() == direction
    for key in ("Sharpe Ratio", "Sharpe Ratio2"):
        result[key] = number(raw.get(key)) if same_direction else None
    result["Trade Dir"] = direction
    values = [number(str(row["pct"]).split(",")[0]) * (-1 if direction == "short" else 1)
              for row in entries]
    fields = ("Percent Profitable", "Avg Profit - All", "Avg Profit", "Avg Loss",
              "Median Profit", "Std Dev", "Annualized Return", "Cumulative Return")
    if not values:
        result.update({key: None for key in fields})
        result.update({"Num Winners": 0, "Num Losers": 0, "Sharpe Ratio": None, "Sharpe Ratio2": None})
        return result
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    avg = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0
    compounded = math.prod(1 + value / 100 for value in values)
    result.update({
        "Num Winners": len(wins), "Num Losers": len(losses),
        "Percent Profitable": 100 * len(wins) / len(values),
        "Avg Profit - All": round(avg, 2),
        "Avg Profit": round(statistics.mean(wins), 2) if wins else 0,
        "Avg Loss": round(statistics.mean(losses), 2) if losses else 0,
        "Median Profit": round(statistics.median(values), 2),
        "Std Dev": round(stdev, 2),
        "Cumulative Return": round((compounded - 1) * 100, 2),
        "Annualized Return": round((compounded ** (1 / len(values)) - 1) * 100, 2)
        if compounded >= 0 else None,
    })
    risk_free = number(raw.get("Risk Free Rate"))
    days = number(days_out)
    if risk_free is not None and days is not None:
        hurdle = risk_free * max(0, days - 1) / 365
        result["Sharpe Ratio"] = round((avg - hurdle) / stdev, 2) if stdev else 0
        favorable = []
        for row in entries:
            parts = str(row["pct"]).split(",")
            field = 2 if direction == "short" else 1
            value = number(parts[field]) if len(parts) > field else None
            if value is not None:
                favorable.append(-value if direction == "short" else value)
        if len(favorable) == len(values):
            sd = statistics.stdev(favorable) if len(favorable) > 1 else 0
            result["Sharpe Ratio2"] = round((statistics.mean(favorable) - hurdle) / sd, 2) if sd else 0
    return result
