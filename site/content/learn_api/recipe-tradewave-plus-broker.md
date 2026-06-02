---
title: "Recipe: TradeWave + your broker (works with any execution app)"
slug: "recipe-tradewave-plus-broker"
description: "A cookbook flow: ask TradeWave for the best seasonal setup, then place the broker-agnostic order ticket at any broker. We never take your trades."
order: 8
read_minutes: 8
---

## The recipe in one sentence

Ask TradeWave for the best seasonal setup and its ML win probability, then hand the broker-agnostic `order_ticket` to whatever execution app you already use. TradeWave finds the edge and the timing; you place the trade anywhere. We never take your trades, so there is no conflict of interest, and the ticket never carries a price level for us to game.

This works with any broker. Nothing in this flow is provider-specific - hand the ticket to any in-chat execution app, your broker's SDK, or a manual confirmation step. A `MARKET`/`DAY` ticket with a side, a symbol, and dates is universal.

Everything below is illustrative. Live responses carry a `disclaimer` and are educational, not personalized advice.

## The four steps

1. **Find** the best setup - `find_best_opportunities` over REST (`GET /scan`) or MCP.
2. **Read** the `SignalCard`: the edge, the receipts, and the optional ML block.
3. **Stage** the handoff - the `next_step.order_ticket` and `next_step.set_reminder`.
4. **Execute** at your broker. You place the trade; TradeWave is done at step 3.

## Step 1: Find the setup

Sweep your in-scope markets over a forward window and let the engine rank what surfaces. Filter on `historical_win_rate` (the share of profitable years) so weak setups never reach you.

```bash
curl -s "https://api.tradewave.ai/v1/scan?markets=0,1,2,3,4&window=next_2_weeks&direction=long&min_win_rate=0.65&min_years=10&rank_by=sharpe&limit=5" \
  -H "Authorization: Bearer $TW_API_KEY" \
  | jq '.results[0]'
```

Get a key at [tradewave.ai/account/api/keys](https://tradewave.ai/account/api/keys). Which markets are `in_scope` and your ML allowance live on the [pricing page](https://tradewave.ai/pricing) and in your console - read them there rather than hardcoding, since they can change.

## Step 2: Read the SignalCard

The top result is a `SignalCard`. Here is a trimmed, illustrative one - your live values will differ:

```json
{
  "rank": 1,
  "symbol": "XLE",
  "market": { "id": 3, "name": "ETFs" },
  "direction": "long",
  "signal": "BUY",
  "setup": {
    "entry_date": "2026-06-05",
    "entry_window": "2026-06-03..2026-06-08",
    "hold_days": 21,
    "exit_date": "2026-06-26"
  },
  "edge_score": 78,
  "stats": {
    "historical_win_rate": 0.81,
    "sharpe_ratio": 1.9,
    "avg_return_pct": 3.4,
    "median_return_pct": 3.1,
    "years": 16
  },
  "ml": { "ml_score": 72, "ml_win_prob": 0.69, "pred_return_pct": 2.8, "pred_mfe_pct": 4.5 },
  "next_step": {
    "order_ticket": {
      "side": "buy",
      "symbol": "XLE",
      "type": "MARKET",
      "time_in_force": "DAY",
      "suggested_entry_date": "2026-06-05",
      "suggested_exit_date": "2026-06-26",
      "note": "Seasonal entry window opens 2026-06-03."
    },
    "set_reminder": {
      "type": "calendar",
      "fire_on": "2026-06-05",
      "message": "TradeWave: seasonal entry window for XLE is open."
    },
    "copy_text": "Buy XLE, hold ~21 days, target exit 2026-06-26.",
    "framing": "Seasonal long. You place the trade at any broker."
  },
  "headline": "Energy ETF has risen in 13 of the last 16 Junes",
  "disclaimer": "Educational, not personalized advice."
}
```

Two distinct numbers do the persuading, and you should never collapse them into one "win rate":

| Field | Meaning | Range |
| --- | --- | --- |
| `historical_win_rate` | Share of past years that were profitable | 0..1 |
| `ml_win_prob` | The ML model's predicted probability for this setup | 0..1 |

One is the historical record; the other is a forward-looking prediction. All movement is in percentages (`avg_return_pct`, `pred_return_pct`); there is never a price or an OHLCV bar in the card. If you want the year-by-year proof, read the `receipts` block, or pull the forward-tested record behind `GET /daily-pick/track-record`.

If the best available setup is weak, the card comes back with `signal: "NO_SIGNAL"` and no `order_ticket` - by design, when `edge_score < 40`, `historical_win_rate < 0.55`, or `years_tested < 5`. A recipe that always produces a trade would be lying to you. This one stops cooking when there is nothing worth eating.

## Step 3: Stage the handoff

The whole point of `next_step` is that it is ready to execute somewhere else. The `order_ticket` is deliberately minimal and provider-neutral:

- `side` - `buy` or `sell`
- `symbol` - the ticker
- `type` - always `MARKET`
- `time_in_force` - always `DAY`
- `suggested_entry_date` / `suggested_exit_date` - the seasonal window
- `note` - a one-line human reason

Notice what is **not** there: no price, no limit level, no stop. TradeWave shows the edge and the timing; the price you get is between you and your broker. Because we never see or set a level, there is nothing for us to mark up, and nothing tying our incentives to your fill.

Use `set_reminder` to fire a calendar or push reminder on the entry date, and `copy_text` as a one-line summary you can drop into any chat or order pad.

## Step 4: Execute at your broker

Now hand the ticket to your execution app. Below, a small Python helper pulls the top setup and turns the ticket into a generic order payload. Swap `place_order` for your broker's SDK, any in-chat execution app, or a manual confirmation step - the input is identical.

```python
import os, requests

BASE = "https://api.tradewave.ai/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['TW_API_KEY']}"}

def best_setup(markets, window="next_2_weeks"):
    r = requests.get(f"{BASE}/scan", headers=HEADERS, timeout=30, params={
        "markets": ",".join(map(str, markets)),
        "window": window, "direction": "long",
        "min_win_rate": 0.65, "min_years": 10,
        "rank_by": "sharpe", "limit": 5,
    })
    r.raise_for_status()
    for card in r.json()["results"]:
        if card["signal"] != "NO_SIGNAL":
            return card
    return None

def to_order(ticket):
    # Broker-agnostic. Map these fields onto any execution API.
    return {
        "side": ticket["side"],
        "symbol": ticket["symbol"],
        "order_type": ticket["type"],         # MARKET
        "time_in_force": ticket["time_in_force"],  # DAY
        # No price/limit/stop - your broker decides the fill.
    }

card = best_setup([0, 1, 2, 3, 4])
if card:
    ticket = card["next_step"]["order_ticket"]
    print("Headline:", card["headline"])
    print("Win rate:", card["stats"]["historical_win_rate"],
          "| ML win prob:", (card["ml"] or {}).get("ml_win_prob"))
    order = to_order(ticket)
    # place_order(order)   # <- your broker / execution app here
    print("Ready to send:", order)
else:
    print("No setup cleared the bar - nothing to trade today.")
```

If you are driving an AI agent instead of writing code, the same flow is one MCP call. Ask `find_best_opportunities` (or `whats_seasonal_now`) at [mcp.tradewave.ai](https://mcp.tradewave.ai), read the `order_ticket` off the returned card, and let the agent hand it to whatever execution tool it is also connected to. The agent never needs a price level because the ticket does not carry one.

## A note on ML and metering

The `ml` block is offered on every tier but metered per day - free keys get a small daily allowance; Pro and Business are unlimited. The model covers US stocks, indices, and ETFs and only shorter seasonal holds (up to about 90 days); longer holds and other markets return `ml: null` with a `tier_notes` explaining why. When you run out of allowance, the call still returns a normal `200` with an upgrade nudge and `ml_remaining_today` - never an error. The daily pick's ML is always free, so `GET /daily-pick` is a clean way to see a fully enriched card every day.

## Why this split matters

The reason the recipe has exactly one handoff and no order routing is the moat: a public, time-stamped, forward-tested daily-pick track record you can audit (`GET /daily-pick/track-record`), and a provider-neutral ticket that lets you trade the edge at any broker. We show the edge and the timing; you place the trade. That separation is what makes the receipts trustworthy - we have no position in your fill.

## Where to go next

- Drill into a single name with `GET /analyze/{symbol}` for one rich `SignalCard` plus `other_setups`.
- Audit the live record with `GET /daily-pick` and `GET /daily-pick/track-record`.
- Wire an agent end to end with the [MCP guide](https://mcp.tradewave.ai).

Every response is educational and carries a `disclaimer`; it is not personalized advice.
