---
title: "Build a cross-market seasonal screener with /scan"
slug: "cross-market-screener"
description: "Use the flagship GET /scan endpoint to rank seasonal opportunities across every market in your scope, with honest NO_SIGNAL filtering."
order: 3
read_minutes: 8
---

## Why /scan is the endpoint you actually want

Most TradeWave integrations start by reaching for `/opportunities`, the single-date primitive. That works, but it answers a narrow question: "what is seasonal for this one symbol on this one date?" When you are building a screener, you want the opposite - cast a wide net across many markets and a forward window, then let the engine rank what surfaces.

That is what `GET /scan` does. It is the HTTP face of `find_best_opportunities`, the same flagship tool exposed to AI agents over MCP. You hand it a set of markets and a time window; it evaluates the seasonal setups inside that window, scores each one, and returns a ranked list of `SignalCard` objects. Every card is a derived signal - percentages and a normalized seasonal index, never a raw price or an OHLCV bar.

Everything below is illustrative. Live responses carry a disclaimer and are educational, not personalized advice.

## The parameters

```
GET /scan?markets=&window=&direction=&min_win_rate=&min_years=&rank_by=&limit=
```

| Param | What it does |
|-------|--------------|
| `markets` | Comma-separated market ids to search. Omit to use your full scope. Get ids from `GET /markets`. |
| `window` | `now`, `next_2_weeks`, `next_month`, or a date range `YYYY-MM-DD..YYYY-MM-DD`. |
| `direction` | `long` or `short`. Omit to consider both. |
| `min_win_rate` | Floor on `historical_win_rate` (0..1) - the share of profitable years. |
| `min_years` | Minimum years of history a setup needs to qualify. |
| `rank_by` | `edge`, `win_rate`, `sharpe`, `ml`, or `avg_return`. Default `sharpe`. |
| `limit` | Max cards to return. |

A few things to internalize:

- `historical_win_rate` is the share of profitable years (0..1). It is NOT `ml_win_prob`, which is the ML model's predicted probability for a setup. Two distinct numbers, never interchanged.
- `window=now` finds setups whose entry window is open right now. The date-range form is for backtest-style "what is seasonal between these two dates" scans.
- `rank_by=sharpe` is the default because risk-adjusted return is usually what you want to sort a screener by. Switch to `edge` to rank by the blended `edge_score`, or `ml` to surface the model's top picks.

## A Python screener

This scans US equities and indices for the next month, keeps only setups with a strong historical win rate and enough history, and prints a ranked table of headlines.

```python
import os
import requests

BASE = "{{API_BASE}}"
HEADERS = {"Authorization": f"Bearer {os.environ['TW_API_KEY']}"}

def scan(markets, window="next_month", **params):
    resp = requests.get(
        f"{BASE}/scan",
        headers=HEADERS,
        params={"markets": ",".join(map(str, markets)), "window": window, **params},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

data = scan(
    markets=[0, 1, 2, 3, 4],   # US stocks, indices, ETFs in your scope
    window="next_month",
    direction="long",
    min_win_rate=0.65,         # >= 65% of years profitable
    min_years=10,              # >= 10 years of history
    rank_by="sharpe",
    limit=15,
)

cards = data["opportunities"]
print(f"evaluated {data['evaluated_count']} setups, returning {len(cards)}")
if data.get("enrichment_capped"):
    print("note: ML enrichment was capped for this scan")

print(f"\n{'#':<3}{'SYMBOL':<8}{'DIR':<6}{'WIN%':<7}{'YRS':<5}HEADLINE")
for c in cards:
    if c["signal"] == "NO_SIGNAL":
        continue
    s = c["stats"]
    print(
        f"{c['rank']:<3}{c['symbol']:<8}{c['direction']:<6}"
        f"{s['historical_win_rate']*100:>4.0f}%  {s['years']:<5}{c['headline']}"
    )
```

`min_win_rate` and `min_years` are enforced server-side, so the cards you get back already clear those floors. Re-checking them client-side (as the loop does by skipping `NO_SIGNAL`) is belt-and-suspenders, not duplication.

## Reading the envelope: evaluated_count and enrichment_capped

The top-level response carries two fields worth understanding:

- `evaluated_count` - how many candidate setups the engine actually examined before ranking. If you scanned five markets over a month and `evaluated_count` is in the hundreds, that is the breadth working for you. A small number relative to your scope usually means a tight `window` or strict `min_*` floors.
- `enrichment_capped` - ML scoring is metered per day (free keys get a small daily allowance; Pro and Business are unlimited). On a wide scan, the engine may rank by the requested key and only ML-enrich the top of the list. When it does, `enrichment_capped` is `true` and some cards come back with `ml: null`. That is graceful behavior, not an error - the HTTP status stays 200. Check `ml_remaining_today` on the response if you want to see your budget.

ML also only covers US stocks, indices, and ETFs (market ids 0, 1, 2, 3, 4, 11) and only shorter seasonal holds (up to about 90 days). Longer holds return `ml: null` with a `tier_notes` explaining the model covers shorter holds. So a `null` `ml` block can mean "out of budget," "not an ML-eligible market," or "hold too long" - all three are normal.

## Honest ranking: NO_SIGNAL is a feature

A screener that always hands you 15 trades is lying to you. `/scan` does not. When a candidate is the best available but still weak, the card comes back with `signal: "NO_SIGNAL"` and no `order_ticket`. Specifically, a setup is `NO_SIGNAL` when `edge_score < 40`, or `historical_win_rate < 0.55`, or `years_tested < 5`.

```json
{
  "rank": 1,
  "symbol": "EXMPL",
  "market": {"id": "0", "name": "DOW 30 STOCKS"},
  "direction": "long",
  "signal": "NO_SIGNAL",
  "edge_score": 33,
  "stats": {"historical_win_rate": 0.52, "sharpe_ratio": 0.4, "years": "6"},
  "ml": null,
  "headline": "No strong seasonal edge here right now.",
  "verdict": "Skip - the seasonal edge is too thin to act on.",
  "disclaimer": "Educational, not personalized advice."
}
```

If your whole scan comes back as `NO_SIGNAL` cards, that is the engine telling you nothing in that window clears the bar. Conflict-free honesty like this is the point of the product: we show the edge and the timing, you place the trade at any broker, and we never pretend an edge exists when it does not.

## The curl version

For a quick check from a shell or a cron job, the same scan in `curl`:

```bash
curl -s "{{API_BASE}}/scan?markets=0,1,2,3,4&window=next_month&direction=long&min_win_rate=0.65&min_years=10&rank_by=sharpe&limit=15" \
  -H "Authorization: Bearer $TW_API_KEY" \
  | jq '.opportunities[] | select(.signal != "NO_SIGNAL")
        | {rank, symbol, dir: .direction, win: .stats.historical_win_rate, headline}'
```

Get a key at [your account console]({{CONSOLE_URL}}). Tier scope (which markets are in_scope) and ML metering shape live on the [API pricing page]({{PRICING_URL}}) and your console - check there rather than hardcoding counts, since they can change.

## Where to go next

Once a `/scan` card looks interesting, drill in with `GET /analyze/{symbol}` for one rich `SignalCard` plus `other_setups`, or pull the forward-tested receipts behind `GET /daily-pick`. The screener finds candidates; the analyze and daily-pick endpoints give you the full per-year track record to decide. Building an agent instead? The same ranking is one MCP call to `find_best_opportunities` at [the MCP endpoint]({{MCP_URL}}).
