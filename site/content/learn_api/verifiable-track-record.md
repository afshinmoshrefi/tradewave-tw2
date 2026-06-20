---
title: "The verifiable track record"
slug: "verifiable-track-record"
description: "Why a time-stamped, forward-tested daily-pick ledger is TradeWave's core trust asset, and how to read it with GET /daily-pick."
order: 6
read_minutes: 8
---

## Why a track record is the whole game

Anyone can backtest a strategy and show you a beautiful equity curve. Backtests are made *after* the fact - you already know what happened, so the temptation to tune the rules until the past looks perfect is overwhelming. That is why a backtest, however honest, is not evidence. It is a hypothesis.

A forward-tested track record is different. TradeWave publishes one seasonal opportunity per day as the daily pick. The pick is committed *before* the holding window opens, stamped with the date it was made, and then scored later against what actually happened. The order of operations is the point: the prediction exists first, the result exists second, and the gap between them is public.

That sequencing is something no data or execution vendor can fake. You cannot retroactively slip a winning pick into a ledger the world already saw yesterday. The receipts - the per-year history behind each card *and* the live forward results of the published picks - are the core trust asset of the platform. Everything else (the seasonal index, the edge score, the ML probability) is a claim. The track record is the proof, and this article is about reading it from the API.

Everything below is illustrative. Live responses carry a `disclaimer` and are educational, not personalized advice.

## Made in advance, scored later

Here is the lifecycle of a single daily pick:

1. **Commit.** Each day the engine selects one `PatternCard` and timestamps it (`receipts.as_of`). The setup is fixed: symbol, direction, entry window, hold days, exit date.
2. **Wait.** The seasonal hold plays out over the coming days or weeks. Nothing about the pick can change.
3. **Score.** When the window closes, the realized percentage return is recorded against that exact, previously published setup.
4. **Append.** The result joins the running forward-tested ledger. It is now permanent and visible to everyone.

Because step 1 always precedes step 3 in wall-clock time, the ledger is self-auditing. The realized win rate you read today is computed only from picks whose windows have already closed - never from open positions and never from hindsight.

## GET /daily-pick

The daily pick endpoint returns today's Pattern Card *and* the live track record of every pick that came before it, in one response. You can pull it right now with the public demo token `tw_demo_explore` - read-only, rate-limited, no signup - so you can inspect the real shape before you mint a key:

```bash
curl -s {{API_BASE}}/daily-pick \
  -H "Authorization: Bearer tw_demo_explore"
```

The pick itself is a normal `PatternCard` under the top-level `card` key - percentages and a normalized 0-100 seasonal index, never a price. The card's `receipts` block carries the per-year history behind the setup, and the top-level `track_record` block summarizes how the *published* picks have actually performed since they were committed.

```json
{
  "as_of": "2026-06-02",
  "featured_date": "2026-06-02",
  "card": {
    "rank": 1,
    "symbol": "EXMPL",
    "market": { "id": "0", "name": "DOW 30 STOCKS" },
    "direction": "long",
    "bias": "bullish",
    "setup": {
      "entry_date": "2026-06-03",
      "entry_window": "2026-06-03 to 2026-06-05",
      "hold_days": 18,
      "exit_date": "2026-06-21"
    },
    "edge_score": 71,
    "stats": {
      "historical_win_rate": 0.81,
      "sharpe_ratio": 1.6,
      "avg_return_pct": 3.4,
      "median_return_pct": 3.1,
      "years": "16"
    },
    "ml": { "ml_score": 68, "ml_win_prob": 0.66, "pred_return_pct": 2.9, "pred_mfe_pct": 4.7 },
    "receipts": { "...": "per-year history, best/worst year, curve summary" },
    "disclaimer": "Educational, not personalized advice.",
    "tier_notes": null
  },
  "track_record": {
    "count": 198,
    "win_count": 123,
    "win_rate": 0.62,
    "avg_return_pct": 1.9,
    "note": "Live forward-tested record of past daily picks (made in advance, scored later)."
  }
}
```

Two numbers carry different meanings, and they are deliberately *not* the same field:

- `card.stats.historical_win_rate` is the **share of profitable years** in the seasonal backtest for this symbol and window (here, `0.81` = profitable in 81% of the years tested).
- `track_record.win_rate` is the **forward-tested** win rate of the picks TradeWave actually published (here, `0.62`).

The forward number is almost always more sober than the backtest, and that gap is healthy - it is what an honest, unfaked ledger looks like. (The pick's `ml` block rides along for free on every tier and never draws down your daily ML allowance, since the pick already carries the score the engine selected it with.)

## GET /daily-pick/track-record

When you want the full ledger rather than today's card, call the dedicated endpoint. It returns a `summary` block plus `picks`, the complete list of published picks (closed ones carry `result` "win" or "loss"; picks still inside their hold window are "open"). The demo token works here too, so you can audit the live record before you sign up:

```bash
curl -s {{API_BASE}}/daily-pick/track-record \
  -H "Authorization: Bearer tw_demo_explore"
```

This is the endpoint to point a skeptic at. Pull it yourself, recompute the win rate from the raw results, and check it against the headline number. They will match, because the ledger is the source.

## Read it from Python

A short script fetches the ledger, prints the realized win rate, and lists the most recent closed picks. It runs as-is on the demo token, so you can verify the math before you ever create a key. Notice that every percentage is a derived return - there is not a single price in the response.

```python
import requests

BASE = "{{API_BASE}}"
HEADERS = {"Authorization": "Bearer tw_demo_explore"}  # or your own tw_live_xxx key

resp = requests.get(f"{BASE}/daily-pick/track-record", headers=HEADERS, timeout=30)
resp.raise_for_status()
tr = resp.json()

s = tr["summary"]
print(f"Live track record: {s['count']} picks published")
print(f"  headline win rate: {s['win_rate']:.0%}  ({s['win_count']} wins)")
print(f"  avg realized return: {s['avg_return_pct']:+.1f}%\n")

# Recompute the win rate from the raw ledger to verify the headline.
# Some picks are still inside their hold window (result "open") - the
# headline win rate is computed over CLOSED picks only, so do the same.
picks = tr["picks"]
closed = [p for p in picks if p["result"] in ("win", "loss")]
wins = sum(1 for p in closed if p["result"] == "win")
print(f"  recomputed win rate: {wins / len(closed):.0%}  ({wins}/{len(closed)})\n")

print("Most recent picks:")
for p in picks[:8]:
    flag = {"win": "WIN ", "loss": "loss"}.get(p["result"], "open")
    print(f"  {p['featured_date']}  {p['symbol']:<6} {flag} {p['return_pct']:+.1f}%")
```

Sample output:

```text
Live track record: 11 picks published
  headline win rate: 60%  (6 wins)
  avg realized return: +6.1%

  recomputed win rate: 60%  (6/10)

Most recent picks:
  2026-03-17  NEM    WIN  +8.3%
  2026-03-10  CVX    loss -1.1%
  2026-03-03  MSFT   WIN  +4.0%
```

The fact that the recomputed number matches the headline is the entire pitch. You did not have to trust the summary - you reproduced it.

## Provider-neutral, conflict-free

The ledger only means something because TradeWave has no stake in which way your trade goes:

- **We never take your trades.** The seasonal pattern carries a `next_step.order_ticket` with side, symbol, type, and dates - never a price or limit level. You place the trade at any broker you choose. We are not your counterparty and we do not see your fills.
- **We publish the misses.** Losses sit in the ledger next to the wins. A vendor optimizing for appearances would hide them; a forward-tested record cannot.
- **We return a `neutral` bias when the edge is thin.** When the best available setup is weak (`edge_score` below 40, `historical_win_rate` below 0.55, or fewer than 5 years tested), the card returns `bias: "neutral"` and no order ticket. Refusing to manufacture a trade is the same honesty that makes the track record believable.

Because we are paid for access to the seasonal pattern and never for your trading volume, the incentive is to be *right over time*, and the public ledger is how you hold us to it.

## Where to go next

- Read the daily pick end to end with [Your first TradeWave API call](/learn/first-api-call).
- Understand the two win-rate fields in [What is a seasonal edge](/learn/what-is-a-seasonal-edge).
- Get a key at [your account console]({{CONSOLE_URL}}) and compare tiers on the [API pricing page]({{PRICING_URL}}).

All outputs are educational and carry a `disclaimer`; they are not personalized investment advice.
