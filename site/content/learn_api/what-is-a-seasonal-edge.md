---
title: "What is a seasonal edge, and how to read a TradeWave SignalCard"
slug: "what-is-a-seasonal-edge"
description: "Learn what a seasonal edge is and how to read every field of a TradeWave SignalCard, from edge_score to receipts and the broker-agnostic order ticket."
order: 1
read_minutes: 8
---

## What is a seasonal edge?

A **seasonal edge** is a recurring, calendar-driven tendency in a market: a stretch of the year where a symbol has, across many past years, moved in the same direction more often than not. Think "this index has historically firmed up in the back half of October" or "this stock tends to drift lower into mid-summer." These tendencies show up because real-world cycles repeat - earnings calendars, fiscal-year flows, tax dates, weather and demand cycles, index rebalances, and plain old investor habit.

A seasonal edge is **not** a prediction and **not** a price target. It is a statistical lean: a window with a favorable historical hit rate and a measurable average move. TradeWave surfaces those windows honestly, shows you the receipts, and lets you decide.

A few framing rules hold everywhere in the API:

- **Signals only.** TradeWave never returns raw prices, OHLCV bars, or dollar levels. Every move is a **percentage**, and the seasonal shape is a **normalized 0-100 index curve**, never a price path.
- **Educational, not advice.** Every response carries a `disclaimer`. Outputs are illustrative, not personalized.
- **Provider-neutral.** We show the edge and the timing; you place the trade at any broker. We never take your trades.

The unit of all of this is the **SignalCard** - the object returned by `/scan`, `/analyze`, and `/daily-pick`. Read one card well and you can read the whole API.

## An illustrative SignalCard

Here is a realistic (illustrative) card for a **long US equity** setup. Values are made up to teach the shape - do not trade off them.

```json
{
  "rank": 1,
  "symbol": "AAPL",
  "market": { "id": "0", "name": "DOW 30 STOCKS" },
  "direction": "long",
  "signal": "BUY",
  "setup": {
    "entry_date": "2026-10-12",
    "entry_window": "2026-10-12..2026-10-16",
    "hold_days": 21,
    "exit_date": "2026-11-02"
  },
  "edge_score": 78,
  "edge_basis": "0.40*win_rate + 0.30*sharpe + 0.20*ml + 0.10*sample",
  "stats": {
    "historical_win_rate": 0.80,
    "sharpe_ratio": 1.6,
    "avg_return_pct": 3.4,
    "median_return_pct": 3.1,
    "years": "15"
  },
  "ml": {
    "ml_score": 72,
    "ml_win_prob": 0.69,
    "pred_return_pct": 2.8,
    "pred_mfe_pct": 4.5
  },
  "receipts": {
    "years_tested": 15,
    "wins": 12,
    "losses": 3,
    "historical_win_rate": 0.80,
    "avg_return_pct": 3.4,
    "median_return_pct": 3.1,
    "best_year": { "year": 2019, "return_pct": 9.2 },
    "worst_year": { "year": 2018, "return_pct": -4.1 },
    "per_year": [
      { "year": 2024, "return_pct": 4.0, "result": "win" },
      { "year": 2023, "return_pct": 2.2, "result": "win" },
      { "year": 2022, "return_pct": -2.7, "result": "loss" }
    ],
    "curve_summary": "rises through late October, peaks early November",
    "source": "tradewave-seasonal-engine",
    "as_of": "2026-06-02"
  },
  "next_step": {
    "order_ticket": {
      "side": "buy",
      "symbol": "AAPL",
      "type": "MARKET",
      "time_in_force": "DAY",
      "suggested_entry_date": "2026-10-12",
      "suggested_exit_date": "2026-11-02",
      "note": "Seasonal long. Place at your broker; sizing is yours."
    },
    "copy_text": "Long AAPL, enter ~Oct 12, exit ~Nov 2 (21-day seasonal hold).",
    "set_reminder": {
      "type": "entry",
      "fire_on": "2026-10-12",
      "message": "AAPL seasonal long entry window opens"
    },
    "framing": "We show the edge and timing; you place the trade."
  },
  "headline": "AAPL has a strong late-October seasonal lean (long).",
  "verdict": "BUY",
  "disclaimer": "Educational, not personalized advice. Past seasonality does not guarantee future results.",
  "tier_notes": null
}
```

## Reading every field

### Identity and direction

- **`rank`** - position in a ranked result set (1 = best by your `rank_by` choice in `/scan`).
- **`symbol`** and **`market`** - what and where. `market.id` is the stable market identifier; `market.name` is the label.
- **`direction`** - `"long"` (you profit if it rises) or `"short"` (you profit if it falls).
- **`signal`** / **`verdict`** - `"BUY"`, `"SELL"`, or `"NO_SIGNAL"`. This is the actionable conclusion.

### The setup window

`setup` is the *when*. `entry_date` is the central entry day; `entry_window` is the few-day band around it (seasonality is fuzzy, not a single magic date). `hold_days` is the holding period and `exit_date` is when the window historically closes.

### edge_score: the one-number summary

`edge_score` is a 0-100 blend of the four things that make a seasonal lean trustworthy: hit rate, risk-adjusted return, the ML read, and sample depth.

```python
edge_score = round(100 * clamp01(
    0.40 * win_rate +
    0.30 * min(sharpe / 3, 1) +
    0.20 * ml_or_winrate +
    0.10 * min(years / 15, 1)
))
```

`edge_basis` spells out which components actually drove the number for this card. Higher is stronger, but always read the receipts before you trust the score.

### stats: the historical track

`stats` summarizes the backtest of this exact window across `years` of history:

| Field | Meaning |
| --- | --- |
| `historical_win_rate` | Share of past years that were profitable (0..1). |
| `sharpe_ratio` | Average move per unit of variability. |
| `avg_return_pct` | Mean percent move over the hold. |
| `median_return_pct` | Middle percent move (robust to outliers). |
| `years` | How many years are in the sample. |

### ml: the model's read (and a key distinction)

`ml` is **either `null` or an object**. When present it adds the machine-learning view: `ml_score` (0-100 conviction), `ml_win_prob` (the model's **predicted probability** of a winning trade, 0..1), `pred_return_pct` (predicted percent return), and `pred_mfe_pct` (predicted maximum favorable excursion - best percent move reached during the hold).

> **Do not conflate two things called a "win rate."**
> `historical_win_rate` is a measured fact - the share of past years that were profitable.
> `ml_win_prob` is a forward prediction - the model's estimated probability for this trade.
> One looks backward and is countable; the other looks forward and is a model output.

ML is available on every tier but **metered per day** (the free tier gets a small daily ML allowance; Pro and Business are unlimited; the daily pick's ML is always free). It covers US stocks, indices, and ETFs, and only **shorter seasonal holds** (up to about 90 days). For longer holds, `ml` is `null` and `tier_notes` explains: *"ML score not available for this setup - the ML model covers shorter seasonal holds (up to about 90 days)."* If you run out of allowance, the response still returns HTTP 200 with a gentle upgrade nudge and an `ml_remaining_today` count - never an error. See the [API pricing page]({{PRICING_URL}}) and your console for current limits.

### receipts: the trust layer

`receipts` is what makes TradeWave different. It is the auditable proof behind the card: `years_tested`, `wins`, `losses`, the `best_year` and `worst_year`, and - most importantly - **`per_year`**, a year-by-year breakdown with each year's `return_pct` and a `result` of `"win"` or `"loss"`.

Scan `per_year` before you trust any score. Twelve wins in fifteen years with one ugly outlier tells a very different story than a knife-edge 8-of-15. `curve_summary` describes the seasonal shape in words, and `as_of` plus `source` time-stamp the evidence. For the daily pick specifically, this evidence is a public, forward-tested track record (see `/daily-pick/track-record`) - receipts you can check, not a marketing claim.

### NO_SIGNAL: honesty as a feature

When the best available setup is weak, TradeWave **refuses to manufacture a trade**. If `edge_score < 40`, or `historical_win_rate < 0.55`, or `years_tested < 5`, the card comes back with `signal: "NO_SIGNAL"` and **no `order_ticket`**. A no is a real answer. Surfacing it is a feature, not a gap.

### next_step: the broker-agnostic order ticket

`next_step` turns a signal into action without touching your money. The `order_ticket` is deliberately **price-free**:

- `side`, `symbol`, `type: "MARKET"`, `time_in_force: "DAY"`
- `suggested_entry_date`, `suggested_exit_date`, and a `note`

There is **no limit price or dollar level** - timing and direction only; sizing and execution are yours. `copy_text` is a ready-to-paste summary, `set_reminder` schedules an entry nudge, and `framing` restates the deal: we show the edge and timing, you place the trade at any broker.

## Putting it together

To read a SignalCard well:

1. Check `signal`. If it is `NO_SIGNAL`, stop - there is no edge worth trading.
2. Read `edge_score` for the headline, then `edge_basis` for what drove it.
3. **Open `receipts.per_year`** - this is the trust step.
4. Compare `historical_win_rate` (measured) against `ml_win_prob` (predicted); treat them as two different signals.
5. Use `setup` and `next_step.order_ticket` for timing, then size and place the trade yourself.

Everything here is illustrative and educational, not personalized advice. Grab a key at [your account console]({{CONSOLE_URL}}) and pull a live card from `GET /daily-pick` to see a real SignalCard, receipts and all.
