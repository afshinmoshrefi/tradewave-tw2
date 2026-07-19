---
title: "Your first TradeWave API call in 5 minutes"
slug: "first-api-call"
description: "Make your first TradeWave call with the public demo token, then swap in your own key and read GET /daily-pick."
order: 2
read_minutes: 6
---

## What you will build

In the next five minutes you go from a blank terminal to a real TradeWave seasonal pattern printed in front of you - no signup required for the first call. The friendliest endpoint is the daily pick: one detected seasonal pattern, scored and dated, returned as a fully formed `PatternCard` with its live forward-tested track record. No parameters, no setup, just one GET request.

Everything the API returns is a **detected seasonal pattern**: win rates over many years, a normalized seasonal index, an ML score, and a 0-100 edge score. You never get raw prices or OHLCV bars. You place the trade at whatever broker you use; the API gives you the edge and the timing and never touches your orders.

## Step 1 - Make the call with the demo token

You can make your first call right now with the public demo token `tw_demo_explore`. It is read-only, rate-limited, and returns the live daily pick, so you can see the shape of a real response before you sign up for anything.

Here is the same request in three flavors. Pick yours and run it.

```bash
curl {{API_BASE}}/daily-pick \
  -H "Authorization: Bearer tw_demo_explore"
```

```python
import requests

resp = requests.get(
    "{{API_BASE}}/daily-pick",
    headers={"Authorization": "Bearer tw_demo_explore"},
    timeout=15,
)
resp.raise_for_status()
card = resp.json()["card"]   # the PatternCard lives under "card"
print(card["headline"])
print(card["verdict"])
```

```javascript
const resp = await fetch("{{API_BASE}}/daily-pick", {
  headers: { Authorization: "Bearer tw_demo_explore" },
});
const { card } = await resp.json();  // the PatternCard lives under "card"
console.log(card.headline);
console.log(card.verdict);
```

You should see a one-line headline and a verdict for today's pattern. That is your first call done.

## Step 2 - Swap in your own API key

The demo token is shared and capped. For real use, mint your own key:

- Visit {{CONSOLE_URL}}
- Generate a key. It looks like `tw_live_xxx`.
- Treat it like a password. Keep it server-side and out of source control.

Every request authenticates with a bearer token over the base URL `{{API_BASE}}`:

```
Authorization: Bearer tw_live_xxx
```

Re-run any of the snippets above with your `tw_live_xxx` key in place of `tw_demo_explore`. The daily pick takes no arguments, and its ML score is always free, so it never draws down your daily ML allowance.

## Step 3 - Read the response

The endpoint returns a small envelope: today's `PatternCard` under the top-level `card` key, next to a `track_record` summary of how previously published picks actually did. A trimmed response looks like this (illustrative - your live values will differ):

```json
{
  "as_of": "2026-06-02",
  "featured_date": "2026-06-02",
  "card": {
    "rank": 1,
    "symbol": "XLE",
    "market": { "id": "11", "name": "ETFs" },
    "direction": "long",
    "bias": "bullish",
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
      "curve_summary": {
        "shape": "strengthens into the exit; seasonal index rising +5 pts over the hold",
        "trend": "rising",
        "change_pts": 5.1,
        "peak_day": 18,
        "trough_day": 0
      },
      "source": "forward-tested daily pick",
      "as_of": "2026-06-02"
    },
    "headline": "Energy ETF has risen in 13 of the last 16 Junes",
    "verdict": "Strong seasonal long with confirming ML.",
    "disclaimer": "Educational seasonal pattern + ML research, not personalized investment advice and not a recommendation to buy or sell. Past performance is not indicative of future results.",
    "tier_notes": "ML score shown."
  },
  "track_record": { "count": 11, "win_count": 6, "win_rate": 0.6, "avg_return_pct": 6.1 }
}
```

### The four fields to read first

- **`headline`** - a one-line, plain-English summary of the setup. Great for notifications.
- **`verdict`** - the call in a sentence: how strong, and why.
- **`bias`** - `bullish`, `bearish`, or `neutral`. When the strongest available seasonal pattern is still weak, the API returns `neutral` and no order ticket. Handle that case in your code: a quiet day is a valid answer, not an error.
- **`edge_score`** - a 0-100 blend of win rate, risk-adjusted return, the ML score, and sample depth. Higher is stronger.

### Two probabilities that are NOT the same thing

This trips up everyone once, so learn it now:

| Field | Meaning | Range |
| --- | --- | --- |
| `historical_win_rate` | Share of past years that were profitable | 0..1 |
| `ml_win_prob` | The ML model's predicted probability for this setup | 0..1 |

In the example above, the pattern won in 13 of 16 years (`historical_win_rate` = 0.81), while the model's forward-looking estimate (`ml_win_prob`) is 0.69. They answer different questions - one is the historical record, the other is a prediction.

### Receipts: the audit trail

The `receipts` block is the audit trail behind the pattern: a time-stamped, forward-tested record of how many years were tested, the win and loss counts, the best and worst years, and a per-year breakdown. Because the daily pick is published and then tracked forward over time, you can verify the edge in your own code instead of trusting a single summary number. Pull the full history any time:

```bash
curl {{API_BASE}}/daily-pick/track-record \
  -H "Authorization: Bearer tw_live_xxx"
```

### About `ml` and `null`

The `ml` object can be `null`, so guard for it. The ML model covers US stocks, indices, and ETFs on shorter seasonal holds (up to about 90 days). For longer holds you will see `ml: null` plus a `tier_notes` explaining why. The daily pick's ML score is always free, but elsewhere ML is metered per day - free accounts get a small daily allowance, while Pro and Business are unlimited. See {{PRICING_URL}} for current tiers.

### Place the trade yourself

Inside `next_step` you get an `order_ticket` carrying `side`, `symbol`, `type` ("MARKET"), `time_in_force` ("DAY"), and suggested entry and exit dates. Notice what is **not** there: no price or limit level. The API gives you the edge and the timing, and you place the order at your own broker.

## Where to go next

The daily pick is one detected seasonal pattern. The real power shows up when you go looking for your own:

- **`GET /scan`** - the discovery call. Sweep one or more markets over a time window, filter by direction, win rate, and sample depth, and rank by `sharpe`, `edge`, `win_rate`, `ml`, or `avg_return`. This is `find_best_opportunities`.
- **`GET /analyze/{symbol}`** - one rich `PatternCard` for a symbol you already have in mind, plus `other_setups` you may have missed.

```bash
curl "{{API_BASE}}/scan?markets=0,3&window=next_month&rank_by=sharpe&limit=5" \
  -H "Authorization: Bearer tw_live_xxx"
```

Building an AI agent instead? The same seasonal patterns are available over MCP at {{MCP_URL}} (sign in with your TradeWave account from ChatGPT or Claude.ai, or bring your own key in the `Authorization` header from dev tools), with tools like `find_best_opportunities`, `analyze_symbol`, and `explain_pick`.

Every response is educational and carries a disclaimer; it is not personalized advice. Now go build on your first card.
