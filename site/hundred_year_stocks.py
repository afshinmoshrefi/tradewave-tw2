#!/usr/bin/env python3
"""Daily S&P 500 stock list for the homepage 100-Year Pattern card.

Runs in the 07:00 weekday home refresh (ops/run_site_refresh.sh home) while the
100-Year Pattern occurrence is active, and writes a small JSON file that
site/generate_home_page.py renders inside the card.

Selection (owner-approved 2026-09-29, "option B"):
  1. OppList4 for S&P 500 (market 2), patterns starting today, long only, from
     the engine's precomputed 15-year table with at least 13 winning years
     (Monthly_Opp_*_15_13), in two lengths: 7-30 and 31-90 calendar days.
  2. Main record: ChartData4 for the same symbol/date/length over the last
     15 years (Num Winners / Num Losers / Avg Profit - All).
  3. Midterm record: ChartData4 for the same window over every midterm (PE+2)
     year the stock has. The engine limits the request to the years available;
     the count is Num Winners + Num Losers.
  4. Keep a stock only with at least 12 of 15 winning years, at least
     MIN_MIDTERM_YEARS midterm years, and more midterm wins than losses.
  5. Rank by the engine's ML score (MLScoreBatch / MLScorePending); keep the top
     PER_TAB for each length, one row per symbol per length.

Every number is passed through from the engine. Failures write nothing, and
the homepage falls back to its normal Top Patterns table.
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from log_safety import scrub_secret_text  # noqa: E402
from market_clock import new_york_now  # noqa: E402
import hundred_year_home  # noqa: E402

APPSERVER_URL = config.appserver_url.rstrip("/")
OUTPUT_JSON = "/home/flask/site/data/home_100yp_stocks.json"
RESOURCE_ID = "2"  # S&P 500
MAIN_YEARS = 15
MAIN_MIN_PROFITABLE = 13  # engine table 15_13
MAIN_MIN_WINNERS = 12  # 80% of 15
MIDTERM_REQUEST = "pe2-30"  # engine limits this to the stock's available years
MIN_MIDTERM_YEARS = 5
PER_TAB = 5
CANDIDATES_PER_TAB = 25
TABS = (
    # key, label, inclusive calendar-day range
    ("short", "Next 1–4 weeks", 7, 30),
    ("medium", "Next 1–3 months", 31, 90),
)
REQUEST_TIMEOUT = 60
ML_POLL_ROUNDS = 40
ML_POLL_SLEEP_S = 3


def _login() -> Optional[str]:
    try:
        resp = requests.post(
            APPSERVER_URL + "/login/api",
            headers={"X-Service-Key": config.SERVICE_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        return resp.json().get("token")
    except Exception as exc:
        print("   WARN appserver login failed: %s" % scrub_secret_text(exc, config.SERVICE_API_KEY))
        return None


def _get(path: str, token: str, params: Optional[dict] = None) -> Optional[dict]:
    query = {"token": token}
    query.update(params or {})
    try:
        resp = requests.get(APPSERVER_URL + path, params=query, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        # The prepared URL carries the session token; never log the exception.
        print("   WARN request failed: %s" % path.split("?")[0])
        return None
    if resp.status_code != 200:
        print("   WARN %s -> HTTP %s" % (path, resp.status_code))
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _post(path: str, token: str, body: dict) -> Optional[dict]:
    try:
        resp = requests.post(APPSERVER_URL + path, params={"token": token},
                             json=body, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        print("   WARN request failed: %s" % path)
        return None
    if resp.status_code != 200:
        print("   WARN %s -> HTTP %s" % (path, resp.status_code))
        return None
    try:
        return resp.json()
    except ValueError:
        return None


class Engine:
    """Thin wrapper over the appserver endpoints this module consumes."""

    def __init__(self, token: str):
        self.token = token

    def opp_list(self, today: _dt.date, low: int, high: int) -> list:
        # OppList4 filters raw day offsets; the tabs use inclusive calendar days.
        data = _get(
            "/OppList4/%s/%s/%d/%d/%d/%d-%d/0/0" % (
                RESOURCE_ID, today.strftime("%B"), today.day, MAIN_YEARS,
                MAIN_MIN_PROFITABLE, low - 1, high - 1),
            self.token,
            {"mode": "cons", "target_date": today.isoformat()},
        )
        rows = (data or {}).get("OppList")
        return rows if isinstance(rows, list) else []

    def chart(self, symbol: str, date: str, days_out: int, years: str) -> Optional[dict]:
        return _get(
            "/ChartData4/%s/%s/%s/%d/%s" % (RESOURCE_ID, date, symbol, days_out, years),
            self.token,
            {"comparison_direction": "long"},
        )

    def ml_scores(self, opps: list[dict]) -> dict:
        """Return {"SYM|date|daysOut|l": score_dict} from the engine's ML scorer."""
        scores: dict = {}
        first = _post("/MLScoreBatch/%s" % RESOURCE_ID, self.token, {"opportunities": opps})
        if not first:
            return scores
        scores.update(first.get("scores") or {})
        pending = first.get("pending") or []
        for _ in range(ML_POLL_ROUNDS):
            if not pending:
                break
            time.sleep(ML_POLL_SLEEP_S)
            polled = _post("/MLScorePending/%s" % RESOURCE_ID, self.token, {"pending": pending})
            if not polled:
                break
            scores.update(polled.get("scores") or {})
            pending = polled.get("still_pending") or []
        return scores


def _record(chart: Optional[dict]) -> Optional[dict]:
    """Winners / total / average from an engine ChartData4 response."""
    if not isinstance(chart, dict):
        return None
    stats = chart.get("stats") or {}
    try:
        winners = int(stats["Num Winners"])
        losers = int(stats["Num Losers"])
    except (KeyError, TypeError, ValueError):
        return None
    rows = chart.get("ChartData4")
    completed = [r for r in rows if isinstance(r, dict) and r.get("completed")] if isinstance(rows, list) else []
    if winners + losers <= 0 or winners + losers != len(completed):
        return None
    return {
        "winners": winners,
        "total": winners + losers,
        "avg": hundred_year_home._signed_stat(stats.get("Avg Profit - All")),
    }


def _pattern_param(symbol: str, date: str, days: int) -> str:
    raw = "%s|%s|%s|%d|%d" % (RESOURCE_ID, symbol, date, days, MAIN_YEARS)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _fmt(day: _dt.date) -> str:
    return "%s %d" % (day.strftime("%b"), day.day)


def build(engine: Any, today: _dt.date, names: Callable[[str], str]) -> dict:
    tabs = []
    for key, label, low, high in TABS:
        seen: set[str] = set()
        candidates = []
        for raw in engine.opp_list(today, low, high):
            try:
                date, symbol, days_out, direction = str(raw[0]), str(raw[1]), int(raw[2]), str(raw[3])
            except (IndexError, TypeError, ValueError):
                continue
            days = days_out + 1
            if direction != "Long" or date != today.isoformat() or not low <= days <= high:
                continue
            if symbol in seen:
                continue
            seen.add(symbol)
            candidates.append({"symbol": symbol, "date": date, "daysOut": days_out, "days": days})
            if len(candidates) >= CANDIDATES_PER_TAB:
                break

        kept = []
        for cand in candidates:
            main = _record(engine.chart(cand["symbol"], cand["date"], cand["daysOut"], str(MAIN_YEARS)))
            if not main or main["total"] != MAIN_YEARS or main["winners"] < MAIN_MIN_WINNERS:
                continue
            mid = _record(engine.chart(cand["symbol"], cand["date"], cand["daysOut"], MIDTERM_REQUEST))
            if not mid or mid["total"] < MIN_MIDTERM_YEARS or mid["winners"] * 2 <= mid["total"]:
                continue
            cand.update(main=main, midterm=mid)
            kept.append(cand)

        # years/mode/partial identify the 15_13 study; patterns over 30 days need
        # them for the engine's duration-checkpoint scoring.
        scores = engine.ml_scores([
            {"symbol": c["symbol"], "date": c["date"], "daysOut": str(c["daysOut"]),
             "direction": "l", "years": str(MAIN_YEARS), "mode": "consecutive",
             "partial": str(MAIN_MIN_PROFITABLE)}
            for c in kept
        ]) if kept else {}
        for cand in kept:
            score = scores.get("%s|%s|%d|l" % (cand["symbol"], cand["date"], cand["daysOut"])) or {}
            cand["ml_score"] = score.get("ml_score") if score.get("status") == "available" else None
        # Engine ML score first; candidates without one keep the engine's table order.
        ranked = sorted(
            enumerate(kept),
            key=lambda item: (item[1]["ml_score"] is None, -(item[1]["ml_score"] or 0), item[0]),
        )
        rows = []
        for _, cand in ranked[:PER_TAB]:
            start = _dt.date.fromisoformat(cand["date"])
            end = start + _dt.timedelta(days=cand["days"] - 1)
            rows.append({
                "symbol": cand["symbol"],
                "name": names(cand["symbol"]),
                "window": "%s → %s" % (_fmt(start), _fmt(end)),
                "days": cand["days"],
                "main": "%d of %d yrs" % (cand["main"]["winners"], cand["main"]["total"]),
                "midterm": "%d of %d midterm yrs" % (cand["midterm"]["winners"], cand["midterm"]["total"]),
                "avg": cand["main"]["avg"],
                "ml_score": cand["ml_score"],
                "url": "/app/?o=%s" % _pattern_param(cand["symbol"], cand["date"], cand["days"]),
            })
        print("   %s: %d candidates -> %d kept -> %d shown" % (key, len(candidates), len(kept), len(rows)))
        tabs.append({"key": key, "label": label, "rows": rows})
    return {"as_of": today.isoformat(), "tabs": tabs}


def _name_lookup(token: str) -> Callable[[str], str]:
    cache: dict[str, str] = {}

    def lookup(symbol: str) -> str:
        if symbol not in cache:
            data = _get("/NameFromTicker/%s/%s" % (RESOURCE_ID, symbol), token) or {}
            name = data.get("NameFromTicker") or data.get("name") or symbol
            cache[symbol] = str(name).strip() or symbol
        return cache[symbol]

    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=OUTPUT_JSON)
    parser.add_argument("--date", help="Scan date YYYY-MM-DD (default: New York today)")
    args = parser.parse_args()

    today = _dt.date.fromisoformat(args.date) if args.date else new_york_now().date()
    fp = hundred_year_home._featured_patterns()
    if fp.hundred_year_occurrence_status(today) != "active":
        print("100-Year Pattern not active on %s; stock list skipped." % today)
        return 0
    if today.weekday() >= 5:
        print("Weekend; stock list skipped.")
        return 0

    token = _login()
    if not token:
        return 0
    result = build(Engine(token), today, _name_lookup(token))
    if not any(tab["rows"] for tab in result["tabs"]):
        print("   WARN no qualifying stocks; previous file left unchanged.")
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(".%s.tmp" % out.name)
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, out)
    print("Wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
