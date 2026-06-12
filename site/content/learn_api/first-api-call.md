---
title: "Your first TradeWave API call in 5 minutes"
slug: "first-api-call"
description: "Get an API key, set the Authorization header, and call GET /daily-pick to read your first TradeWave SignalCard."
order: 2
read_minutes: 6
---

## What you will build

In the next five minutes you will go from nothing to a real TradeWave signal printed in your terminal. The fastest way to see what the API returns is the daily pick: one curated seasonal opportunity, delivered as a fully formed `SignalCard`, complete with its live forward-tested track record. No parameters, no setup - just a key and one GET request.

Everything TradeWave returns is a **derived signal**. You get percentages, a normalized seasonal index, and an honest edge score. You never get raw prices or OHLCV bars. You place the trade at any broker you like; we show the edge and the timing, and we never touch your orders.

## Step 1 - Get an API key

Create a key from your account console:

- Visit {{CONSOLE_URL}}
- Generate a key. It looks like `tw_live_xxx`.
- Treat it like a password. Keep it server-side and out of source control.

Every request to the API authenticates with a bearer token:

```
Authorization: Bearer tw_live_xxx
```

The base URL for all v1 endpoints is `{{API_BASE}}`.

## Step 2 - Call GET /daily-pick

The daily pick is the friendliest first call because it takes no arguments and its ML score is always free, so it never touches your daily ML allowance.

Here is the same request in three flavors. Pick yours.

```bash
curl {{API_BASE}}/daily-pick \
  -H "Authorization: Bearer tw_live_xxx"
```

```python
import requests

resp = requests.get(
    "{{API_BASE}}/daily-pick",
    headers={"Authorization": "Bearer tw_live_xxx"},
    timeout=15,
)
resp.raise_for_status()
card = resp.json()["card"]   # the SignalCard lives under "card"
print(card["headline"])
print(card["verdict"])
```

```javascript
const resp = await fetch("{{API_BASE}}/daily-pick", {
  headers: { Authorization: "Bearer tw_live_xxx" },
});
const { card } = await resp.json();  // the SignalCard lives under "card"
console.log(card.headline);
console.log(card.verdict);
```

## Step 3 - Read the response

The endpoint returns a small envelope: today's `SignalCard` under the top-level `card` key, next to a `track_record` summary of how the previously published picks actually did. A trimmed response looks like this (illustrative - your live values will differ):

```json
{
  "as_of": "2026-06-02",
  "featured_date": "2026-06-02",
  "card": {
    "rank": 1,
    "symbol": "XLE",
    "market": { "id": "11", "name": "ETFs" },
    "direction": "long",
    "signal": "BUY",
    "setup": {
      "entry_date": "2026-06-05",
      "entry_window": "2026-06-03 to 2026-06-08",
      "hold_days": 21,
      "exit_date": "2026-06-26"
    },
    "edge_score": 78,
    "edge_basis": "win_rate + sharpe + ml + sample depth",
    "stats": {
      "historical_win_rate": 0.81,
      "sharpe_ratio": 1.9,
      "avg_return_pct": 3.4,
      "median_return_pct": 3.1,
      "years": "16"
    },
    "ml": {
      "ml_score": 72,
      "ml_win_prob": 0.69,
      "pred_return_pct": 2.8,
      "pred_mfe_pct": 4.5
    },
    "receipts": {
      "years_tested": 16,
      "wins": 13,
      "losses": 3,
      "historical_win_rate": 0.81,
      "avg_return_pct": 3.4,
      "median_return_pct": 3.1,
      "best_year": { "year": "2016", "return_pct": 9.2 },
      "worst_year": { "year": "2020", "return_pct": -4.1 },
      "per_year": [
        { "year": "2024", "return_pct": 4.0, "result": "win" },
        { "year": "2023", "return_pct": -1.2, "result": "loss" }
      ],
      "curve_summary": "rising into late June",
      "source": "forward-tested daily pick",
      "as_of": "2026-06-02"
    },
    "headline": "Energy ETF has risen in 13 of the last 16 Junes",
    "verdict": "Strong seasonal long with confirming ML.",
    "disclaimer": "Educational, not personalized advice.",
    "tier_notes": ""
  },
  "track_record": { "count": 11, "win_count": 6, "win_rate": 0.6, "avg_return_pct": 6.1 }
}
```

### The four fields to read first

- **`headline`** - a one-line, plain-English summary of the setup. Great for notifications.
- **`verdict`** - the call in a sentence: how strong, and why.
- **`signal`** - `BUY`, `SELL`, or `NO_SIGNAL`. When the best available setup is weak, TradeWave returns `NO_SIGNAL` and no order ticket on purpose. That conflict-free honesty is the point: we would rather show you nothing than sell you a bad trade.
- **`edge_score`** - a 0-100 blend of win rate, risk-adjusted return, the ML view, and sample depth. Higher is stronger.

### Two probabilities that are NOT the same thing

This trips up everyone once, so learn it now:

| Field | Meaning | Range |
| --- | --- | --- |
| `historical_win_rate` | Share of past years that were profitable | 0..1 |
| `ml_win_prob` | The ML model's predicted probability for this setup | 0..1 |

In the example above, the pattern won in 13 of 16 years (`historical_win_rate` = 0.81), while the model's forward-looking estimate (`ml_win_prob`) is 0.69. They answer different questions - one is the historical record, the other is a prediction.

### Receipts are the moat

The `receipts` block is your audit trail. It is a public, time-stamped, forward-tested record: how many years were tested, the win and loss counts, best and worst years, and a per-year breakdown. Because the daily pick is tracked forward in public over time, you can verify the edge instead of taking it on faith. Pull the full history any time:

```bash
curl {{API_BASE}}/daily-pick/track-record \
  -H "Authorization: Bearer tw_live_xxx"
```

### About `ml` and `null`

The `ml` object can be `null`. The ML model covers US stocks, indices, and ETFs, and only shorter seasonal holds (up to about 90 days). For longer holds you will see `ml: null` and a `tier_notes` explaining why. The daily pick's ML is always provided free, but elsewhere ML is metered per day - free accounts get a small daily allowance, while Pro and Business are unlimited. See {{PRICING_URL}} for current tiers.

### Place the trade yourself

Inside `next_step` you get an `order_ticket` carrying `side`, `symbol`, `type` ("MARKET"), `time_in_force` ("DAY"), and suggested entry and exit dates. Notice what is **not** there: no price or limit level. TradeWave gives you the edge and the timing - you place the order at your own broker.

## Where to go next

The daily pick is one signal. The real power shows up when you go looking:

- **`GET /scan`** - the flagship discovery call. Sweep one or more markets over a time window, filter by direction, win rate, and sample depth, and rank by `sharpe`, `edge`, `win_rate`, `ml`, or `avg_return`. This is `find_best_opportunities`.
- **`GET /analyze/{symbol}`** - one rich `SignalCard` for a symbol you already have in mind, plus `other_setups` you may have missed.

```bash
curl "{{API_BASE}}/scan?markets=0,3&window=next_month&rank_by=sharpe&limit=5" \
  -H "Authorization: Bearer tw_live_xxx"
```

Building an AI agent instead? The same signals are available over MCP at {{MCP_URL}} (sign in with your TradeWave account from ChatGPT or Claude.ai, or bring your own key in the `Authorization` header from dev tools), with tools like `find_best_opportunities`, `analyze_symbol`, and `explain_pick`.

Every response is educational and carries a disclaimer; it is not personalized advice. Now go read your first card.
