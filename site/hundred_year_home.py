"""Homepage card data for the public 100-Year Pattern.

Every return and statistic shown on the card is passed through from the
TradeWave engine (ChartData4 for the canonical signature view defined in
appserver/appserver/featured_patterns.py). This module adds only display rules:

- which state the card is in (upcoming countdown / active / completed);
- the inclusive calendar day of the window ("Day 3 of 295");
- a trading-session count used to hold the live score until
  LIVE_SCORE_MIN_SESSIONS closes have printed after entry, so the homepage
  does not headline a one- or two-day move;
- how many completed winning cycles dipped below entry first (a count of the
  engine's own per-cycle return and MAE values, not a new return formula).

The session count is weekdays between the resolved entry and the engine's
last_trade_date. The window always opens in late September, when NYSE has no
holidays, so the count is exact for the only period where the gate matters.

Any failure (login, network, identity mismatch, stale data) degrades to the
card without numbers. It never falls back to a locally computed return.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
from pathlib import Path
from typing import Any, Callable, Optional

LIVE_SCORE_MIN_SESSIONS = 5
STALE_DATA_DAYS = 6

_FEATURED_PATTERNS_PATH = (
    Path(__file__).resolve().parents[1] / "appserver" / "appserver" / "featured_patterns.py"
)


def _featured_patterns():
    # Load by path: appserver/appserver is not a package and holds modules
    # whose names would shadow site modules if added to sys.path.
    spec = importlib.util.spec_from_file_location(
        "tw_featured_patterns", _FEATURED_PATTERNS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pct_fields(row: dict) -> Optional[tuple[float, float, float]]:
    try:
        ret, mfe, mae = (float(x) for x in str(row.get("pct", "")).split(","))
    except (TypeError, ValueError):
        return None
    return ret, mfe, mae


def _signed(value: float) -> str:
    return "%+.2f%%" % value


def _signed_stat(text: Any) -> Optional[str]:
    """Add the sign to an engine percent string such as "18.79%"."""
    try:
        return _signed(float(str(text).strip().rstrip("%")))
    except (TypeError, ValueError):
        return None


def _next_weekday(day: _dt.date) -> _dt.date:
    while day.weekday() >= 5:
        day += _dt.timedelta(days=1)
    return day


def _sessions_between(first: _dt.date, last: _dt.date) -> int:
    """Weekday sessions in (first, last]: closes printed after the entry close."""
    count = 0
    day = first + _dt.timedelta(days=1)
    while day <= last:
        if day.weekday() < 5:
            count += 1
        day += _dt.timedelta(days=1)
    return count


def _fmt_date(day: _dt.date) -> str:
    return "%s %d, %d" % (day.strftime("%b"), day.day, day.year)


def build_card(
    fetch_chart: Callable[[dict], Optional[dict]],
    today: Optional[_dt.date] = None,
) -> dict:
    """Return the template context for the homepage card.

    ``fetch_chart(spec)`` must return the ChartData4 JSON for the canonical
    view, or None on failure. ``spec`` carries the ChartData4 path fields.
    """

    fp = _featured_patterns()
    today = today or _dt.date.today()
    start = fp.hundred_year_occurrence_start(today)
    end = fp.hundred_year_end_date(start)
    status = fp.hundred_year_occurrence_status(today)
    entry_trading = _next_weekday(start)
    exit_trading = _next_weekday(end)

    card: dict[str, Any] = {
        "status": status,
        "cycle_label": "%d–%s" % (start.year, str(start.year + 1)[-2:]),
        "start_iso": start.isoformat(),
        "window_days": fp.HUNDRED_YEAR_DISPLAY_DAYS,
        "day_number": max(1, min((today - start).days + 1, fp.HUNDRED_YEAR_DISPLAY_DAYS)),
        "entry_label": _fmt_date(entry_trading),
        "exit_label": _fmt_date(exit_trading),
        "history": None,
        "live": None,
    }
    if status == "upcoming":
        return card

    spec = fp.hundred_year_view_spec(today)
    request = {
        "market": spec["market"],
        "entry_date": spec["entry_date"],
        "symbol": spec["symbol"],
        "engine_days": fp.HUNDRED_YEAR_ENGINE_DAYS,
        "years": fp.hundred_year_years_value(today),
    }
    try:
        data = fetch_chart(request)
    except Exception as exc:  # network or JSON error - fail soft
        print("   WARN 100-Year Pattern engine call failed: %s" % type(exc).__name__)
        data = None
    if not isinstance(data, dict):
        print("   WARN 100-Year Pattern: no engine response; card renders without numbers.")
        return card

    echo = data.get("request") or {}
    if not (
        str(echo.get("market")) == spec["market"]
        and str(echo.get("symbol", "")).upper() == spec["symbol"]
        and echo.get("entry_date") == spec["entry_date"]
        and int(echo.get("days_out") or 0) == fp.HUNDRED_YEAR_DISPLAY_DAYS
        and str(echo.get("pe_cycle")) == spec["pe_cycle"]
        and int(echo.get("years") or -1) == spec["years"]
    ):
        print("   WARN 100-Year Pattern: engine echoed a different study %r; numbers omitted." % echo)
        return card

    rows = data.get("ChartData4")
    stats = data.get("stats") or {}
    if not isinstance(rows, list):
        return card

    completed = [r for r in rows if r.get("completed") and _pct_fields(r)]
    current = next((r for r in rows if r.get("year") == start.year), None)

    try:
        winners = int(stats["Num Winners"])
        losers = int(stats["Num Losers"])
    except (KeyError, TypeError, ValueError):
        winners = losers = -1
    if winners >= 0 and winners + losers == len(completed) and completed:
        losses = [(r["year"], _pct_fields(r)[0]) for r in completed if _pct_fields(r)[0] < 0]
        dipped = sum(
            1 for r in completed
            if _pct_fields(r)[0] > 0 and _pct_fields(r)[2] < 0
        )
        card["history"] = {
            "cycles": len(completed),
            "first_year": completed[0]["year"],
            "last_year": completed[-1]["year"],
            "winners": winners,
            "percent_profitable": stats.get("Percent Profitable"),
            "mean": _signed_stat(stats.get("Avg Profit - All")),
            "median": _signed_stat(stats.get("Median Profit")),
            "only_loss": (
                {"year": losses[0][0], "value": _signed(losses[0][1])}
                if len(losses) == 1 else None
            ),
            "winners_that_dipped": dipped,
        }
    else:
        print("   WARN 100-Year Pattern: engine stats disagree with rows; history omitted.")

    if current is None:
        return card

    try:
        last_trade = _dt.date.fromisoformat(str(stats.get("last_trade_date")))
    except (TypeError, ValueError):
        last_trade = None
    sessions = _sessions_between(entry_trading, last_trade) if last_trade else 0
    fields = _pct_fields(current)
    stale = last_trade is None or (today - last_trade).days > STALE_DATA_DAYS

    live: dict[str, Any] = {
        "sessions": sessions,
        "min_sessions": LIVE_SCORE_MIN_SESSIONS,
        "show_score": False,
        "completed": bool(current.get("completed")),
    }
    if fields and not stale and last_trade and last_trade >= entry_trading:
        if sessions >= LIVE_SCORE_MIN_SESSIONS or current.get("completed"):
            live.update({
                "show_score": True,
                "return": _signed(fields[0]),
                "is_negative": fields[0] < 0,
                "as_of": _fmt_date(min(last_trade, exit_trading)),
            })
    elif stale and status == "active":
        print("   WARN 100-Year Pattern: engine data is stale (%s); live score hidden." % last_trade)
    card["live"] = live
    return card


_STOCK_FIELDS = ("symbol", "name", "window", "main", "midterm", "avg", "url")


def load_stock_list(path: str, today: _dt.date) -> Optional[dict]:
    """Today's stock list written by site/hundred_year_stocks.py, or None.

    A file from an earlier day is ignored so the card never shows windows that
    started in the past.
    """
    import json

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("as_of") != today.isoformat():
        return None
    tabs = []
    for tab in data.get("tabs") or []:
        rows = [
            {field: str(row.get(field) or "") for field in _STOCK_FIELDS}
            for row in (tab.get("rows") or [])
            if isinstance(row, dict) and str(row.get("url", "")).startswith("/app/?o=")
        ]
        if rows:
            tabs.append({"key": str(tab.get("key")), "label": str(tab.get("label")), "rows": rows})
    return {"tabs": tabs} if tabs else None
