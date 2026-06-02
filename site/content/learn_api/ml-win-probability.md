---
title: "Using the ML win-probability model"
slug: "ml-win-probability"
description: "Read the ml block on a TradeWave SignalCard, tell ml_win_prob apart from historical_win_rate, and handle metering and the 90-day horizon gracefully."
order: 4
read_minutes: 8
---

## What the ML model adds

Every TradeWave `SignalCard` starts with a **seasonal** read: across many past years, how often did this symbol move the right way in this window, and by how much? That is the `stats` and `receipts` part of the card, and it stands entirely on its own.

The machine-learning model is a **second opinion layered on top**. When it has something useful to say, the card carries an `ml` block. The model looks at the current setup and predicts how this particular instance is likely to play out, rather than just averaging the past. Think of seasonal as "what usually happens around now" and ML as "given the present conditions, here is my probability and magnitude estimate for this one."

The honest part: **ML is a complement, not a guarantee, and it is not on every setup.** Plenty of valid seasonal opportunities return `ml: null`. That is by design, and reading the `null` correctly is most of the work. Everything below is illustrative - live responses carry a `disclaimer` and are educational, not personalized advice.

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

1. **ML-eligible markets only.** The model currently covers **US stocks, indices, and ETFs** - market ids `0, 1, 2, 3, 4, 11`. You can also read this off `GET /markets`: each market carries an `ml_eligible` flag. Other markets (futures, FX, crypto, etc.) return seasonal signals normally but no `ml`.
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

Exact numbers live on the [pricing page](https://tradewave.ai/pricing) and in your [console](https://tradewave.ai/account/api/keys) - we do not hardcode them here because they can change.

When a free-tier caller runs out of allowance, the gateway does **not** error. It returns **HTTP 200** with the seasonal signal intact, `ml: null`, an `ml_remaining_today` counter, and a gentle upgrade nudge in `tier_notes`. Your code should treat "out of ML budget" exactly like "ML not eligible": fall back to the seasonal stats and move on.

## Scoring setups in bulk with POST /score

To attach ML scores to a batch of candidate setups, post them to `/score`:

```python
import requests

BASE = "https://api.tradewave.ai/v1"
HEADERS = {"Authorization": "Bearer tw_live_xxx"}

payload = {
    "opportunities": [
        {"symbol": "AAPL", "date": "2026-07-15", "days_out": 30,
         "direction": "long", "market": 1},
        {"symbol": "SPY",  "date": "2026-07-15", "days_out": 45,
         "direction": "long", "market": 3},
        # A longer hold - expect ml: null on this one.
        {"symbol": "XLE",  "date": "2026-07-15", "days_out": 120,
         "direction": "long", "market": 11},
    ]
}

resp = requests.post(f"{BASE}/score", headers=HEADERS, json=payload, timeout=30)
resp.raise_for_status()
data = resp.json()

for card in data["opportunities"]:
    sym = card["symbol"]
    hist = card["stats"]["historical_win_rate"]          # share of profitable years
    ml = card.get("ml")

    if ml is None:
        # Eligibility, horizon, or out-of-allowance - all land here. Not an error.
        note = card.get("tier_notes", "ML not available for this setup.")
        remaining = card.get("ml_remaining_today")
        suffix = f" (ml_remaining_today={remaining})" if remaining is not None else ""
        print(f"{sym}: seasonal hist_win_rate={hist:.0%}; ML n/a - {note}{suffix}")
    else:
        # ml_win_prob is the MODEL's predicted probability, distinct from hist.
        print(
            f"{sym}: hist_win_rate={hist:.0%}  "
            f"ml_win_prob={ml['ml_win_prob']:.0%}  "
            f"ml_score={ml['ml_score']}  "
            f"pred_return={ml['pred_return_pct']:+.1f}%  "
            f"pred_mfe={ml['pred_mfe_pct']:+.1f}%"
        )
```

The single `ml is None` branch covers all three "no ML" cases - ineligible market, hold longer than ~90 days, and exhausted daily allowance - because the gateway never raises for any of them. That is the whole point: a 200 with a neutral note keeps your screener running.

## A reusable rule for your UI

Boil the above down to one decision when you render a card:

- If `ml` is present, **show both** `historical_win_rate` and `ml_win_prob` with distinct labels, plus `pred_return_pct` and `pred_mfe_pct` as percentages.
- If `ml` is `null`, **show the seasonal stats alone** and surface `tier_notes` verbatim so the user knows why - eligibility, horizon, or budget.
- Never block a signal just because `ml` is missing. The seasonal edge, its `receipts`, and the broker-neutral `order_ticket` (side, symbol, dates - no price level) are the product. ML sharpens it when it can.

## Where to go next

- Read [What is a seasonal edge](/learn/what-is-a-seasonal-edge) for the full `SignalCard` anatomy, including `receipts` and the order ticket.
- Use [/scan](/learn/cross-market-screener) to surface candidates, then feed the winners to `/score` for ML.
- For a live `ml` block that costs nothing, call `GET /daily-pick` - its ML is always free and it ships with a public, time-stamped, forward-tested track record.
