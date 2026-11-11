---
title: "Win Rate vs Risk Reward Ratio: Why 80% Winners Can Still Lose Money"
slug: "win-rate-vs-risk-reward-ratio"
summary: "Your win rate does not decide whether you make money. Your risk reward ratio and your expectancy do. A trader who is right 35% of the time can beat one who is right 80% of the time. Here is the math, and how seasonality fits in."
date: "2026-11-11"
author: "TradeWave Research"
category: "metrics"
order: 1
featured: true
tags: ['win-rate', 'risk-reward', 'expectancy', 'risk-management', 'video']
related: ['trading-expectancy-explained', 'position-sizing-and-stop-loss-seasonal-trades', 'mfe-and-mae-explained', 'sharpe-ratio-explained']
video:
  id: "3STPilmV3aU"
  title: "Risk Reward Ratio vs Win Rate: Which Matters More?"
  description: "Your trading win rate doesn't decide whether you make money. Your risk reward ratio does. A trader who's right 35% of the time can beat one who's right 80%, and here's the math."
  duration: "PT6M"
  upload_date: "2026-10-20"
faq:
  - q: "Which matters more, win rate or risk reward ratio?"
    a: "Neither alone. What decides profitability is expectancy: win rate times average win, minus loss rate times average loss. A high win rate with small wins and large losses can lose money, and a low win rate with large wins and small losses can make money."
  - q: "Can you lose money with an 80% win rate?"
    a: "Yes. If you win 1 unit 80% of the time and lose 5 units 20% of the time, you make 0.8 and lose 1.0 per trade on average, a net loss of 0.2 units per trade."
  - q: "What is a good risk reward ratio?"
    a: "There is no single correct number. A lower win rate needs a higher reward-to-risk ratio to break even. At a 40% win rate you need average wins at least 1.5 times your average loss just to break even, before costs."
  - q: "How does seasonality help with win rate and risk reward?"
    a: "Seasonal analysis shows how often a calendar window worked, how far it typically ran in your favor (MFE) and how far it went against you (MAE). Those measured values give you a realistic target, a stop and a probability instead of guesses."
---

## Key Takeaways

- Win rate measures how often you are right. It says nothing about how much you make when right or lose when wrong.
- **Expectancy** combines both: (win rate x average win) - (loss rate x average loss). Positive expectancy is the goal, not a high win rate.
- A trader right 80% of the time can lose money if the losses are large. A trader right 35% of the time can make money if the winners are much bigger than the losers.
- The practical rule is old and simple: cut losers short and let winners run.
- Seasonality is a first layer of evidence. It tells you how often a window worked and how big the typical move and drawdown were, which feeds directly into targets, stops and position size.

## Why Traders Chase a High Win Rate

Being right feels good and being wrong hurts, so most traders gravitate toward systems that win often. The trap is that the easiest way to raise a win rate is to take profits quickly and give losing trades more room. That habit quietly shrinks the average win and inflates the average loss, and the account can bleed even while the scoreboard says you are winning most of the time.

## Trader A vs Trader B: The Expectancy Math

Measure every trade in **R**, the amount you planned to risk. A trade that loses its full planned risk is -1R. A trade that makes three times the planned risk is +3R.

| | Trader A | Trader B |
|---|---|---|
| Win rate | 35% | 80% |
| Average win | +3R | +1R |
| Average loss | -1R | -5R |
| Expectancy per trade | (0.35 x 3) - (0.65 x 1) = **+0.40R** | (0.80 x 1) - (0.20 x 5) = **-0.20R** |
| Result after 100 trades | **+40R** | **-20R** |

Trader B is right more than twice as often and still ends up 60R behind. The difference is entirely in the size of the wins and losses. For a deeper walkthrough of the formula, see [Trading Expectancy Explained](/learn/trading-expectancy-explained.html).

### The Break-Even Win Rate for Any Risk Reward Ratio

If your average win is W times your average loss, you break even at a win rate of 1 / (1 + W), before commissions and slippage.

| Reward-to-risk (W) | Break-even win rate |
|---|---|
| 0.5 : 1 | 67% |
| 1 : 1 | 50% |
| 1.5 : 1 | 40% |
| 2 : 1 | 33% |
| 3 : 1 | 25% |

Read it both ways. A system that wins 60% of the time with half-size wins (0.5 : 1) is below break-even. A system that wins only 35% of the time with 3 : 1 winners is comfortably profitable.

## Cut Losers Short, Let Winners Run

Some of the best-known traders in history have been right only a little more than half the time. Their edge came from losing small and winning big. In practice that means three things:

1. **Decide the stop before you enter.** A stop is the price that says the idea is wrong.
2. **Size the position so the stop costs a fixed, small slice of the account**, often around 1%.
3. **Give the winner room to reach a realistic target** instead of grabbing the first profit.

Each of these needs a number, and that is where historical evidence helps.

## Where Seasonal Trading Fits

Seasonal trading looks at how a stock, ETF or index has behaved over the same calendar window across many years. It does not predict the future. It gives you a measured base rate.

The idea has a long pedigree. The best-known version is the Best Six Months framing popularized by the Stock Trader's Almanac, which observed that the market historically did most of its work between late fall and spring. TradeWave applies the same logic to any symbol and any window, and measures the result precisely.

Think of seasonality as **layer one**: it tells you when the odds have historically leaned your way. Your entry trigger, stop and size still come from your own rules. [Seasonal vs Technical vs Fundamental Analysis](/learn/seasonal-vs-technical-vs-fundamental-analysis.html) covers how the three lenses work together.

## How TradeWave Shows the Numbers You Need

The Opportunities Table and the Stats Table give you the inputs for expectancy without guesswork:

- **Win count:** how many years the window finished in the right direction, such as 9 of 10.
- **Average and median gain:** the typical size of a winning year.
- **Average loss and the losing years themselves:** how much it cost when it failed. The Profit Bar Chart shows every failed year individually.
- **MAE (maximum adverse excursion):** the worst drawdown inside the window each year, which is the honest basis for a stop. See [MFE and MAE Explained](/learn/mfe-and-mae-explained.html).

## Worked Example: Position Size and Stop Loss

This example is hypothetical and illustrative only.

- Account: $100,000. Risk per trade: 1%, so **$1,000**.
- The window's historical drawdowns suggest a stop **5%** below entry.
- Position size = $1,000 / 5% = **$20,000**.

Now suppose you take ten trades like this with a 40% win rate. Four winners at +$1,200 each (a 6% gain on $20,000) make $4,800. Six losers at -$500 each (the average loss came in smaller than the full stop) cost $3,000. Net: **+$1,800**, even though you lost more often than you won.

The full method, including how to choose the stop from a window's history, is in [Position Sizing and Stop Losses for Seasonal Trades](/learn/position-sizing-and-stop-loss-seasonal-trades.html).

## Losing Is Part of the Job

Every strategy has losing trades, and seasonal patterns are no exception. A window that worked in 9 of 10 years still failed once. The goal is not to avoid losses. It is to keep them small and planned, so the winners pay for them with room to spare. A controlled loss is an acceptable outcome. A big loss is the only one that is not.
