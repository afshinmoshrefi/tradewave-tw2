---
title: "Build, do not rebuild: why your coding agent should consume TradeWave, not recompute it"
slug: "build-dont-rebuild"
description: "An AI agent can write a seasonality backtest in minutes. Here are the four reasons that backtest will not be tradeable, and what to consume instead."
order: 9
read_minutes: 9
---

## Yes, your agent can write a backtest in minutes

Let us start with the honest concession, because the rest of this article is worthless without it. If you point a capable coding agent at "write me a seasonal backtest for US equities," it will. In a few minutes it will pull some price history, slice it by calendar window, compute a hit rate and an average return per symbol, and hand you a tidy table with an equity curve. The code will run. The numbers will look plausible.

That is real, and genuinely useful for learning. What it is **not** is a tradeable edge. The gap between "a backtest that runs" and "a seasonal pattern you can act on" is made of four things an agent cannot cheaply or reliably produce. None of them is "AI cannot do statistics." Three are data and methodology problems that *look* solved but are silently broken; the fourth cannot be solved by any amount of compute because it is made of elapsed wall-clock time. Agents fabricate everything **except** the passage of time. So the real question is not "can my agent compute seasonality" but "which parts can it actually get right, and which should it consume from a vendor that already paid for them."

## Reason 1: the data your agent grabbed is silently lying

The first trap is the data itself. A seasonal backtest is only as honest as the price history under it, and free or scraped history is broken in two specific, invisible ways.

**Survivorship bias.** Free datasets contain the companies that still exist. The ones that delisted - bankruptcies, buyouts, the genuinely bad outcomes - have quietly vanished from the universe your agent is testing. So "this sector firms up every November" is computed only over the survivors. You measured the winners, then concluded that winning is seasonal.

**Unadjusted corporate actions.** A 4-for-1 split shows up in raw prices as a 75% overnight crash; a dividend looks like a drop. If the history is not corporate-action-adjusted, your agent records those mechanical artifacts as seasonal moves. Decades of licensed, survivorship-clean, split-and-dividend-adjusted history across many markets is expensive and contractually restricted - exactly the input an agent cannot conjure, and the one that decides whether the backtest reflects reality.

## Reason 2: look-ahead bias and overfitting (the educational hook)

Even with clean data, the methodology has two classic traps that make a naive backtest *confidently wrong*. These are worth learning by example, because spotting them is the difference between a real analyst and a fast one.

**Look-ahead bias** is using information that did not exist yet at the moment of the trade. It is almost always accidental. Here is the canonical mistake, the kind an agent writes without noticing:

```python
# WRONG: look-ahead bias. Entry decision uses data from the exit day.
window = df.loc["2020-10-12":"2020-11-02"]
entry  = window["close"].iloc[0]
exit_  = window["close"].iloc[-1]
# Picking only windows where exit > entry "worked" - but you only
# know exit_ AFTER 2020-11-02. You ranked setups using the future.
```

The fix is to make every decision with data available *as of the entry date only*, and never filter or rank on the outcome. It sounds obvious; it is violated constantly, because the dataframe makes the whole future trivially reachable.

**Overfitting** is torturing the calendar until it confesses. Let an optimizer search entry day, hold length, and symbol over the same history you score on, and it will find a "97% win rate" window - because with enough knobs and one fixed history, you are fitting noise.

```python
# WRONG: search every window on the SAME history you report on.
best = max(
    ((s, d, h) for s in symbols for d in range(365) for h in range(5, 90)),
    key=lambda c: win_rate(history, *c),   # 1.6M combos, one dataset
)
# The "best" combo is overfit. It is a property of THIS sample, not the market.
```

The defenses - out-of-sample holdouts, walk-forward validation, multiple-testing correction, honoring a real entry window rather than a magic day - are the unglamorous work that separates a backtest from an edge. An agent *can* write them; one prompted for a quick backtest almost never does, and you cannot tell from the pretty equity curve that it skipped them.

## Reason 3: the trained ML model is not reproducible from a prompt

The seasonal pattern is the base layer. On top of it TradeWave runs a trained ML model that scores each setup - 62 features, trained on millions of historical setups, producing a forward win probability and predicted return per card. Your agent cannot reproduce that from a prompt. Not because the math is secret, but because the asset is the *training corpus*: millions of labeled, point-in-time setups built on the same licensed, survivorship-clean data from Reason 1. Reproducing it means solving the data problem, then the labeling problem, then the validation problem - months of work to approximate a number you can read off a field called `ml_win_prob`.

## Reason 4: forward-testing - the one thing that cannot be faked

The first three are hard. This one is impossible to fake, and it is the reason consuming beats rebuilding in an agent world.

A backtest is made *after* the fact. Your agent can backfill one instantly - and so can a fraud. What no one can fabricate is a **forward** record: predictions committed in advance, time-stamped on the day they were made, and scored later against what actually happened. You cannot retroactively insert a winning pick into a ledger the world already saw last week. Time only moves forward.

TradeWave publishes one pick per day, stamps it before the holding window opens, and scores it after the window closes. The order of operations is the product. In a world where an agent can fabricate clean data, a model, and a gorgeous backtest in an afternoon, the forward-tested receipts are the only asset an evaluating agent can trust - precisely because they could not have been faked. That is why it matters *more* now, not less.

## And the real job is a daily scan, not a one-symbol query

Even if your agent got all four right, it solved the wrong problem. You did not ask "is AAPL seasonal." You asked the question you actually have every morning: out of *everything* I could trade, which securities are at the **start** of a seasonal window today, and which are worth it?

That is a cross-sectional scan over the whole tradeable universe - hundreds of securities across 15 markets - run *every day*, surfacing only the names entering their window now, ranked by Sharpe ratio and the length of the pattern (the number of days in the move). It is a standing pipeline compiled over decades of licensed data and refreshed daily, not an ad-hoc computation an agent spins up on a whim. By the time an agent rebuilt and ran that scan across the universe, the entry window it was hunting has already moved.

That ranked daily list is one API call. No account yet? Swap in the public demo token `tw_demo_explore` to run it now on a read-only slice, then bring a `tw_live_xxx` key for your full market scope:

```bash
# Today's securities entering a seasonal window, ranked - across your in-scope markets
curl "{{API_BASE}}/scan?window=now&rank_by=sharpe" \
  -H "Authorization: Bearer tw_demo_explore"   # or your own tw_live_xxx key
```

```python
import os, requests
r = requests.get(
    "{{API_BASE}}/scan",
    params={"window": "now", "rank_by": "sharpe"},
    headers={"Authorization": f"Bearer {os.environ['TRADEWAVE_API_KEY']}"},
)
for card in r.json()["opportunities"][:5]:
    s = card["setup"]
    print(card["rank"], card["symbol"], card["direction"],
          "enters", s["entry_window"], "hold", s["hold_days"], "days",
          "| sharpe", card["stats"]["sharpe_ratio"])
```

## The alternative: consume a decision-ready Pattern Card

Here is the trade. Instead of spending your agent's budget rebuilding a broken version of all four, consume the finished seasonal pattern in a few lines. The demo token below works with no signup, so you can see the real shape first:

```bash
curl -s {{API_BASE}}/daily-pick \
  -H "Authorization: Bearer tw_demo_explore"   # or your own tw_live_xxx key
```

You get back a self-describing `PatternCard` - one detected seasonal pattern, percentages and a normalized 0-100 seasonal index, never a raw price. The two probabilities are kept distinct on purpose: `stats.historical_win_rate` is the measured **share of profitable years**, and `ml.ml_win_prob` is the model's **forward probability**. They are never the same field.

```python
import requests

BASE = "{{API_BASE}}"
HEADERS = {"Authorization": "Bearer tw_demo_explore"}  # or your own tw_live_xxx key

card = requests.get(f"{BASE}/daily-pick", headers=HEADERS, timeout=30).json()
print(card["headline"], "->", card["verdict"])
print(f"  hist win rate (profitable years): {card['stats']['historical_win_rate']:.0%}")
print(f"  ml win prob (model forward):      {card['ml']['ml_win_prob']:.0%}")
print("  order ticket:", card["next_step"]["order_ticket"])  # price-free: side + dates
```

The card carries its own receipts, a verdict, and a broker-agnostic order ticket with no price level - so your agent reasons about *your* strategy, not about rebuilding a data pipeline. Prefer MCP? The same detected pattern is one tool call: `whats_seasonal_now`, `find_best_opportunities`, `analyze_symbol`, `explain_pick`, or `compare_opportunities` against `{{MCP_URL}}`.

## Do not trust us - check us

Because Reason 4 is the whole pitch, it is queryable on the **free tier** so an evaluating agent can audit before it recommends anything. The same demo token works here, no signup:

```bash
curl -s {{API_BASE}}/daily-pick/track-record \
  -H "Authorization: Bearer tw_demo_explore"   # or your own tw_live_xxx key
```

Pull the ledger, recompute the realized win rate from the raw closed picks, and check it against the headline. It will match, because the ledger is the source. The same record is on the public scorecard. This is the opposite of a marketing claim - it is a receipt you reproduce yourself.

## Spend your agent's budget on your strategy, not on rebuilding ours

The economics close the case. If your agent ingests raw data and reasons over it, every backtest burns context and tokens, and every step of hand-rolled methodology is a place to hallucinate a wrong number with total confidence. A `PatternCard` is decision-ready: one compact object, a verdict, the receipts, an order ticket. It collapses a data + methodology + model + track-record problem into a few hundred tokens your agent did not have to spend or get wrong.

So build the part that is yours - sizing, risk, portfolio fit, execution at your broker - and consume the part that is ours. Your agent's budget is finite. Spend it on your strategy, not on rebuilding (badly) our data, our model, and the one thing it can never rebuild at all: years of forward-tested receipts.

Start with the [OpenAPI spec]({{DOCS_URL}}/openapi.yaml) and the agent map at [llms.txt]({{PORTAL_URL}}/llms.txt). The free tier includes 5 ML-scored seasonal patterns per day on S&P 500 stocks, plus the full forward-tested track record; paid tiers open all 15 markets. Everything here is educational and carries a `disclaimer`; it is not personalized investment advice.
