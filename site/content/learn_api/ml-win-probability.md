---
title: "Using the ML win-probability model"
slug: "ml-win-probability"
description: "Read the ml block on a TradeWave Pattern Card, tell ml_win_prob apart from historical_win_rate, and handle metering and the 90-day horizon gracefully."
order: 4
read_minutes: 8
---

## What the ML model adds

Every TradeWave Pattern Card opens with a **seasonal** read: across many past years, how often did this symbol move the right way in this window, and by how much? That is the `stats` and `receipts` part of the card, and it stands entirely on its own.

The machine-learning model is a **second opinion layered on top**. When it has something useful to say, the card carries an `ml` block. Instead of averaging the past, the model looks at the current setup and predicts how this particular instance is likely to play out. Seasonal answers "what usually happens around now"; ML answers "given today's conditions, here is my probability and magnitude estimate for this one." Building a screener? You can rank candidates by the seasonal read alone, then let ML break ties on the setups it covers.

One honest caveat up front: **ML is a complement, not a guarantee, and it is not on every setup.** Plenty of valid seasonal patterns come back with `ml: null`, by design - and reading that `null` correctly is most of the integration work. Want to see a real `ml` block in two seconds before you write any code? The public demo token works against the daily pick, whose ML is always free:

```bash
curl "{{API_BASE}}/daily-pick" \
  -H "Authorization: Bearer tw_demo_explore"
```

Everything below is illustrative - live responses carry a `disclaimer` and are educational, not personalized advice.

## The ml block, field by field

When present, `ml` is a small object:

```json
"ml": {
  "ml_score": 78,
  "ml_win_prob": 0.71,
  "pred_return_pct": 3.4,
  "pred_mfe_pct": 5.1
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ml_score` | 0-100 | The model's overall conviction in this setup, on the same 0-100 scale as `edge_score`. |
| `ml_win_prob` | 0..1 | The model's **predicted probability** that this instance closes profitable. |
| `pred_return_pct` | percentage | The model's expected return over the hold, as a percent move (never a price or level). |
| `pred_mfe_pct` | percentage | Predicted **maximum favorable excursion** - the best unrealized move the model expects along the way, as a percent. |

Note what is *not* here: no entry price, no limit, no dollar target. ML predictions are percentages, consistent with the rest of the API.

## ml_win_prob is NOT historical_win_rate

This is the one distinction worth tattooing on your integration. The two numbers look similar and live close together, but they answer different questions.

- **`historical_win_rate`** (in `stats` and `receipts`) is backward-looking and model-free: the **share of past years that were profitable**. If a setup has 18 years of history and 13 of them made money, `historical_win_rate` is `13 / 18 = 0.72`. It is a count of receipts.
- **`ml_win_prob`** (in `ml`) is the **ML model's forward-looking predicted probability** for *this* instance. It is not a fraction of past years; it is the model's calibrated guess for the trade in front of you.

They will often disagree, and that is informative. A setup can have a strong `historical_win_rate` of 0.72 but a softer `ml_win_prob` of 0.58 because current conditions look unusual to the model - or the reverse. Never average them, never relabel one as the other, and never call either of them simply "win rate" in your UI. Show both, labeled distinctly.

## Which setups get an ML score

ML is offered on **every tier**, but it is not offered on every setup. Two coverage rules decide whether you see an `ml` block or `ml: null`:

1. **ML-eligible markets only.** The model currently covers **US stocks, indices, and ETFs** - market ids `0, 1, 2, 3, 4, 11`. You can also read this off `GET /markets`: each market carries an `ml_eligible` flag. Other markets (futures, FX, crypto, etc.) return detected seasonal patterns normally but no `ml`.
2. **Shorter seasonal holds only - up to about 90 days.** The model is trained for shorter horizons. Setups with longer holds return `ml: null` with a neutral note.

When a longer hold trips the horizon limit, the card stays fully valid - you just get `ml: null` plus a `tier_notes` string:

```json
"ml": null,
"tier_notes": "ML score not available for this setup - the ML model covers shorter seasonal holds (up to about 90 days)."
```

Handle this as a normal, expected branch, not an error. The seasonal edge is still the product; ML is the optional garnish.

## Metering: a daily allowance, and the daily pick is free

ML scoring is **metered per day**:

- **Free** tier gets a small daily ML allowance.
- **Pro / Business** get unlimited ML scoring.
- The **daily pick's** ML is **always free** and never counts against your allowance, so `GET /daily-pick` is a great way to see a live `ml` block without spending budget.

Exact numbers live on the [API pricing page]({{PRICING_URL}}) and in your [console]({{CONSOLE_URL}}) - we do not hardcode them here because they can change.

When a free-tier caller runs out of allowance, the gateway does **not** error. It returns **HTTP 200** with the detected seasonal pattern intact, `ml: null`, an `ml_remaining_today` counter, and an upgrade nudge in `tier_notes`. Treat "out of ML budget" exactly like "ML not eligible": fall back to the seasonal stats and move on.

## Scoring setups in bulk with POST /score

To attach ML scores to a batch of candidate setups, post them to `/score`. Two contract details to get right:

- One **market per call**: pass it as a top-level `market` (body or query parameter, default `"2"`, S&P 500 stocks). It must be one of the ML-eligible markets. Each opportunity needs only `symbol`, `date`, `days_out`, and `direction`.
- The response is a flat `scores` array, **not** Pattern Cards: each row echoes your setup and adds `ml_score`, `win_prob`, `pred_return`, and `pred_mfe` (the bare-score spellings, unlike the `ml` block on a card). Rows the model cannot score - or that land beyond your daily allowance - come back with those fields `null` plus a `note`.

```python
import requests

BASE = "{{API_BASE}}"
HEADERS = {"Authorization": "Bearer tw_live_xxx"}

payload = {
    "market": "2",   # one ML-eligible market per call (resource ids are strings)
    "opportunities": [
        {"symbol": "AAPL", "date": "2026-07-15", "days_out": 30, "direction": "long"},
        {"symbol": "MSFT", "date": "2026-07-15", "days_out": 45, "direction": "long"},
        # A longer hold - expect null ML fields on this one (the model covers ~10-90 days).
        {"symbol": "XOM",  "date": "2026-07-15", "days_out": 120, "direction": "long"},
    ],
}

resp = requests.post(f"{BASE}/score", headers=HEADERS, json=payload, timeout=30)
resp.raise_for_status()
data = resp.json()

print(f"granted: {data['granted']}  ml_remaining_today: {data['ml_remaining_today']}")
for row in data["scores"]:
    sym = row["symbol"]
    if row["win_prob"] is None:
        # Horizon, coverage, or out-of-allowance - all land here. Not an error.
        note = row.get("note", "ML not available for this setup.")
        print(f"{sym}: ML n/a - {note}")
    else:
        # win_prob is the MODEL's predicted probability - distinct from the
        # historical_win_rate you read off a Pattern Card.
        print(
            f"{sym}: win_prob={row['win_prob']:.0%}  "
            f"ml_score={row['ml_score']}  "
            f"pred_return={row['pred_return']:+.1f}%  "
            f"pred_mfe={row['pred_mfe']:+.1f}%"
        )
```

That single `win_prob is None` branch covers every "no ML" case - a hold outside the model's ~10-90 day horizon, a market the model does not cover, and an exhausted daily allowance - because the gateway never raises for any of them. A 200 with a neutral `note` keeps your screener running no matter which one you hit. (No live key yet? Inspect a real `ml` block first via `GET /daily-pick` with `tw_demo_explore`, then bring a `tw_live_xxx` key here to score in bulk.)

## A reusable rule for your UI

Boil the above down to one decision when you render a card:

- If `ml` is present, **show both** `historical_win_rate` and `ml_win_prob` with distinct labels, plus `pred_return_pct` and `pred_mfe_pct` as percentages.
- If `ml` is `null`, **show the seasonal stats alone** and surface `tier_notes` verbatim so the user knows why - eligibility, horizon, or budget.
- Never block a seasonal pattern just because `ml` is missing. The seasonal edge, its `receipts`, and the broker-neutral `order_ticket` (side, symbol, dates - no price level) are the product. ML sharpens it when it can.

## Where to go next

- Read [What is a seasonal edge](/learn/what-is-a-seasonal-edge) for the full Pattern Card anatomy, including `receipts` and the order ticket.
- Use [/scan](/learn/cross-market-screener) to surface candidates, then feed the winners to `/score` for ML.
- For a live `ml` block that costs nothing, call `GET /daily-pick` - its ML is always free and it ships with a public, time-stamped, forward-tested track record.
