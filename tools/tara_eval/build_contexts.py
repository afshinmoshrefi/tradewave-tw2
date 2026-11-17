#!/usr/bin/env python3
"""Build realistic Tara request contexts (wave_viewer / screen_context / opportunities).

The shapes mirror web-react/src/components/Chatbot.js buildWaveViewerContext(),
chatbotScreenContext.js buildChatbotScreenContext() and buildOpportunityTableContext().
Numbers come from the live engine (OppList4 / ChartData4) of the target appserver, so
"analyze this"-type questions are graded against real statistics, not invented ones.

Re-run this whenever the snapshot goes stale (scanner fixtures are dated near "today"):
    python tools/tara_eval/build_contexts.py --target http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys

import requests

from common import CONTEXTS_PATH, load_env_files, mint_token

STAT_KEYS = (
    "Trade Dir", "Num Winners", "Num Losers", "Percent Profitable",
    "Avg Profit - All", "Avg Profit", "Avg Loss", "Median Profit",
    "Annualized Return", "Cumulative Return", "Std Dev", "Sharpe Ratio",
    "Sharpe Ratio2", "Trend Long", "Trend Short", "Trend Long1", "Trend Short1",
    "Trend Score Available", "next_earnings_est", "days_to_earnings",
)
MARKET_NAMES = {
    "0": "DOW 30 STOCKS", "1": "NASDAQ 100 STOCKS", "2": "S&P 500 STOCKS",
    "7": "FUTURES & COMMODITIES", "11": "ETFs", "16": "CRYPTO CURRENCIES",
}


class Engine:
    def __init__(self, target):
        self.base = target.rstrip("/")
        self.token = mint_token("tara-eval-contexts", 6, minutes=20)

    def get(self, path, **params):
        params["token"] = self.token
        response = requests.get(self.base + path, params=params, timeout=(5, 40))
        response.raise_for_status()
        return response.json()

    def opp_rows(self, market, day, years=12):
        data = self.get(
            "/OppList4/%s/%s/%s/%s/%s/-/0/0" % (market, day.strftime("%B"), day.day, years, years),
            mode="consecutive",
        )
        rows = []
        for row in data.get("OppList") or []:
            try:
                rows.append({
                    "date": row[0], "symbol": row[1], "days_out": int(float(row[2])) + 1,
                    "direction": row[3], "avg_profit": round(float(row[5]) * 10) / 10,
                    "sharpe_ratio": round(float(row[4]), 2),
                })
            except (TypeError, ValueError, IndexError):
                continue
        return rows

    def chart(self, market, symbol, entry_date, days_out, years, pe_cycle="cons", direction="long"):
        years_value = str(years) if pe_cycle == "cons" else "%s-%s" % (pe_cycle, years)
        return self.get(
            "/ChartData4/%s/%s/%s/%s/%s" % (market, entry_date, symbol, int(days_out) - 1, years_value),
            comparison_direction=direction,
        )


def _num(text):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def wave_viewer(engine, market, symbol, entry_date, days_out, years=12, pe_cycle="cons",
                origin="scanner", direction=None):
    payload = engine.chart(market, symbol, entry_date, days_out, years, pe_cycle, direction or "long")
    bars = payload.get("ChartData4") or []
    if direction is None:
        # Arbitrary windows have no scanner direction: derive it from the completed bars
        # exactly like deriveDirectionFromBars() and re-ask the engine for that side's stats.
        returns = [_num(str(row.get("pct") or "").split(",")[0]) for row in bars]
        ups = sum(1 for value in returns if value is not None and value > 0)
        downs = sum(1 for value in returns if value is not None and value < 0)
        direction = "short" if downs > ups else "long"
        if direction == "short":
            payload = engine.chart(market, symbol, entry_date, days_out, years, pe_cycle, "short")
            bars = payload.get("ChartData4") or []
    stats = payload.get("stats") or {}
    yearly = []
    for row in bars:
        parts = str(row.get("pct") or "").split(",")
        ret = _num(parts[0]) if parts else None
        if ret is None:
            continue
        yearly.append({
            "year": row.get("year"),
            "underlying_return_pct": ret,
            "upside_excursion_pct": _num(parts[1]) if len(parts) > 1 else None,
            "downside_excursion_pct": _num(parts[2]) if len(parts) > 2 else None,
        })
    view = {
        "market": str(market), "symbol": symbol, "entry_date": entry_date, "days_out": int(days_out),
        "years": int(years), "pe_cycle": pe_cycle, "cut_off_year": 0,
    }
    key = "|".join(str(view[k]) for k in ("market", "symbol", "entry_date", "days_out", "years", "pe_cycle", "cut_off_year"))
    ctx = {
        "market": str(market), "symbol": symbol, "start_date": entry_date, "entry_date": entry_date,
        "days_out": int(days_out), "years": int(years), "pe_cycle": pe_cycle,
        "direction": direction, "selection_origin": origin,
        "mfe_enabled": False, "mae_enabled": False,
        "view_ready": True, "view_request_key": key,
        "stats": {k: stats[k] for k in STAT_KEYS if stats.get(k) not in (None, "")},
        "yearly_results": yearly,
    }
    return ctx


def screen(slide="trend_chart", rows=25, lookback="12", ai=False, projection=False):
    ctx = {
        "active_bottom_slide": slide,
        "ai_scores_available": bool(ai),
        "price_chart_mode": "current" if slide == "price_chart" else "unknown",
        "selected_projection_visible": bool(projection),
        "full_history_projection_visible": bool(projection),
        "opportunity_table_visible": True,
        "selected_lookback": str(lookback),
        "projection_period": "90",
        "opportunity_rows": rows,
        "selected_window_path": "unknown",
        "full_history_window_path": "unknown",
    }
    return ctx


def win_rate(view):
    return _num(str(view["stats"].get("Percent Profitable", "")).rstrip("%")) or 0.0


def pick(engine, market, rows, predicate, score, limit=8):
    best, best_score = None, None
    for row in [r for r in rows if predicate(r)][:limit]:
        try:
            view = wave_viewer(engine, market, row["symbol"], row["date"], row["days_out"],
                               direction=str(row.get("direction") or "long").lower())
        except Exception:
            continue
        value = score(view)
        if best is None or value > best_score:
            best, best_score = view, value
    return best


def best_window(engine, market, symbol, entry_date, candidates=(21, 30, 45, 60, 90), **kw):
    views = []
    for days in candidates:
        try:
            views.append(wave_viewer(engine, market, symbol, entry_date, days, **kw))
        except Exception:
            continue
    if not views:
        raise SystemExit("engine returned no data for %s in market %s" % (symbol, market))
    return max(views, key=lambda v: abs(win_rate(v) - 50))


def build(target):
    engine = Engine(target)
    today = datetime.date.today()
    iso = today.isoformat()
    sp_rows = engine.opp_rows("2", today)
    if not sp_rows:
        raise SystemExit("S&P 500 opportunity table is empty; cannot build contexts")
    table = {
        "opportunities": sp_rows[:25], "opp_table_length": len(sp_rows), "opp_table_market": "2",
        "opp_table_market_name": MARKET_NAMES["2"], "opp_table_years": 12, "opp_table_pe_cycle": "cons",
    }

    def with_table(view, scr, **override):
        ctx = dict(table)
        ctx.update({"wave_viewer": view, "screen_context": scr})
        ctx.update(override)
        return ctx

    def market_table(market, years=12):
        rows = engine.opp_rows(market, today, years)
        return {
            "opportunities": rows[:25], "opp_table_length": len(rows), "opp_table_market": str(market),
            "opp_table_market_name": MARKET_NAMES.get(str(market), ""), "opp_table_years": years,
            "opp_table_pe_cycle": "cons",
        }

    contexts = {
        "empty": {"wave_viewer": {}, "screen_context": {}, "opportunities": []},
    }
    top = sp_rows[0]
    contexts["default_table"] = with_table(
        wave_viewer(engine, "2", top["symbol"], top["date"], top["days_out"],
                    direction=str(top["direction"]).lower()), screen("trend_chart"))

    longs = [r for r in sp_rows if str(r["direction"]).lower() == "long"]
    strong = pick(engine, "2", longs, lambda r: 15 <= r["days_out"] <= 90, win_rate) or contexts["default_table"]["wave_viewer"]
    contexts["stock_long_strong"] = with_table(strong, screen("wave_stats"))

    # Bearish scanner rows are rare; walk the S&P 500 table forward until one appears.
    short_view = None
    for offset in range(0, 45, 3):
        rows = engine.opp_rows("2", today + datetime.timedelta(days=offset))
        shorts = [r for r in rows if str(r["direction"]).lower() == "short"]
        if shorts:
            short_view = pick(engine, "2", shorts, lambda r: True, win_rate, limit=4)
            if short_view:
                break
    if short_view is None:
        raise SystemExit("no bearish S&P 500 scanner pattern found in the next 45 days")
    contexts["stock_short"] = with_table(short_view, screen("trend_chart"))

    contexts["stock_mixed_custom"] = with_table(
        wave_viewer(engine, "2", "AAPL", iso, 45, origin="user_defined"), screen("trend_chart"))

    ai_view = pick(engine, "2", longs, lambda r: 20 <= r["days_out"] <= 60 and r["symbol"] != strong["symbol"], win_rate, limit=5) or strong
    contexts["stock_long_ai"] = with_table(ai_view, screen("ai_scores", ai=True))

    # Crypto history is short: the engine only has data for lookbacks up to ~8 years.
    for name, market, symbol, years in (
        ("etf_long", "11", "XLK", 12), ("futures_gold", "7", "GC", 12), ("crypto_btc", "16", "BTC-USD", 8),
    ):
        view = best_window(engine, market, symbol, iso, years=years, origin="user_defined")
        ctx = market_table(market, years)
        ctx.update({"wave_viewer": view, "screen_context": screen(
            "trend_chart", rows=len(ctx["opportunities"]), lookback=str(years))})
        contexts[name] = ctx

    pe_view = best_window(engine, "2", "MSFT", iso, years=10, pe_cycle="pe2", origin="user_defined")
    contexts["stock_pe2"] = with_table(pe_view, screen("trend_chart", lookback="pe2-10"), opp_table_pe_cycle="cons")

    long_window = pick(engine, "2", longs, lambda r: 150 <= r["days_out"] <= 300, win_rate, limit=4)
    if long_window is None:
        long_window = wave_viewer(engine, "2", "MSFT", iso, 200, origin="user_defined")
    contexts["stock_long_window"] = with_table(long_window, screen("wave_stats"))

    started = today - datetime.timedelta(days=10)
    old_rows = [r for r in engine.opp_rows("2", started) if str(r["direction"]).lower() == "long"]
    active = pick(engine, "2", old_rows, lambda r: 30 <= r["days_out"] <= 120, win_rate, limit=5)
    if active is None:
        active = wave_viewer(engine, "2", "MSFT", started.isoformat(), 45, origin="user_defined")
    contexts["stock_active"] = with_table(active, screen("price_chart", projection=True))

    return {
        "schema_version": 1,
        "built_on": iso,
        "built_from": "live engine OppList4/ChartData4 (percent statistics only; no customer data)",
        "contexts": contexts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="http://127.0.0.1:5000")
    parser.add_argument("--out", default=str(CONTEXTS_PATH))
    args = parser.parse_args()
    load_env_files()
    data = build(args.target)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    for name, ctx in data["contexts"].items():
        view = ctx.get("wave_viewer") or {}
        stats = view.get("stats") or {}
        print("%-20s %-8s %-10s %4s d  %-5s win=%s n=%s" % (
            name, view.get("symbol", "-"), view.get("entry_date", "-"), view.get("days_out", "-"),
            view.get("direction", "-"), stats.get("Percent Profitable", "-"), len(view.get("yearly_results") or [])),
            file=sys.stderr)


if __name__ == "__main__":
    main()
