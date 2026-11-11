---
title: "Trading Expectancy Explained: The Formula That Decides Whether a Strategy Makes Money"
slug: "trading-expectancy-explained"
summary: "Expectancy is the average amount you can expect to make or lose per trade. Learn the formula, how to calculate it in R-multiples, how it connects win rate and risk reward, and how to estimate it for a seasonal pattern."
date: "2026-11-11"
author: "TradeWave Research"
category: "metrics"
order: 2
tags: ['expectancy', 'win-rate', 'risk-reward', 'trading-math']
related: ['win-rate-vs-risk-reward-ratio', 'position-sizing-and-stop-loss-seasonal-trades', 'median-vs-average-return', 'how-many-years-of-data-seasonal-backtest']
faq:
  - q: "What is the trading expectancy formula?"
    a: "Expectancy = (win rate x average win) - (loss rate x average loss). For example, with a 60% win rate, an average win of $300 and an average loss of $200, expectancy is (0.6 x 300) - (0.4 x 200) = $100 per trade."
  - q: "What is a good expectancy in trading?"
    a: "Any reliably positive expectancy after costs is a working edge. Measured in R (the amount risked per trade), many traders consider +0.2R to +0.5R per trade solid. Very high expectancy from a small sample usually means the sample is too small to trust."
  - q: "What is an R-multiple?"
    a: "An R-multiple expresses a trade's result as a multiple of the amount you planned to risk. If you risked $500 and made $1,500, the trade was +3R. If you lost the full $500, it was -1R."
---

## Key Takeaways

- **Expectancy** is the average profit or loss per trade over many trades.
- Formula: **(win rate x average win) - (loss rate x average loss)**.
- Measuring results in **R-multiples** (multiples of the amount risked) makes expectancy comparable across strategies and account sizes.
- Positive expectancy is the requirement for a strategy to make money. A high win rate is not.
- Expectancy only becomes meaningful over **many** trades or years, so sample size matters.

## The Formula

**Expectancy = (W x AvgWin) - (L x AvgLoss)**

- **W** = win rate, as a decimal
- **L** = loss rate = 1 - W
- **AvgWin** = average size of a winning trade
- **AvgLoss** = average size of a losing trade, as a positive number

### Example in Dollars

You win 60% of trades. Winners average $300; losers average $200.

Expectancy = (0.60 x 300) - (0.40 x 200) = 180 - 80 = **$100 per trade**.

Over 100 similar trades, you would expect to come out about $10,000 ahead, before costs.

### Example in R-Multiples

R is the amount you planned to risk on a trade. If your stop would cost $500, then 1R = $500. Express every result as a multiple of R:

| Trade | Result | R-multiple |
|---|---|---|
| 1 | +$1,500 | +3.0R |
| 2 | -$500 | -1.0R |
| 3 | -$250 | -0.5R |
| 4 | +$750 | +1.5R |
| 5 | -$500 | -1.0R |

Sum = +2.0R over 5 trades, so expectancy = **+0.4R per trade**. With R in place, the same expectancy applies whether you trade a $10,000 or a $1,000,000 account, and you can compare strategies directly.

## Expectancy Connects Win Rate and Risk Reward

Win rate and reward-to-risk ratio are two halves of one number. You can have a low win rate and high expectancy, or a high win rate and negative expectancy. [Win Rate vs Risk Reward Ratio](/learn/win-rate-vs-risk-reward-ratio.html) works through an 80%-winner who loses money and a 35%-winner who makes money.

A useful rearrangement: if your average win is W times your average loss, you break even at a win rate of **1 / (1 + W)**. At 2 : 1 you need 33%; at 1 : 1 you need 50%; at 0.5 : 1 you need 67%.

## Estimating Expectancy for a Seasonal Pattern

A seasonal window gives you most of the inputs directly from history:

1. **Win rate:** the share of years the window finished in the right direction, such as 17 of 20 (85%).
2. **Average win:** the average gain in winning years. Check the [median](/learn/median-vs-average-return.html) too, so one huge year does not inflate it.
3. **Average loss:** the average loss in the losing years. The Profit Bar Chart shows every losing year individually.

Example: a window won in 17 of 20 years with a median winning gain of 6% and an average losing year of -4%.

Expectancy = (0.85 x 6%) - (0.15 x 4%) = 5.1% - 0.6% = **+4.5% per year** on the capital in the trade.

Two important adjustments:

- **Your stop changes the average loss.** If you exit at a planned stop, your losses are capped near the stop, not the full losing year. But a stop can also take you out of years that would have recovered. [MFE and MAE Explained](/learn/mfe-and-mae-explained.html) shows how to look at the path inside each year.
- **History is a base rate, not a promise.** Treat the result as a reasonable estimate, then shade it down for costs, slippage and the fact that the future will not exactly repeat the past.

## Why Sample Size Matters

Expectancy from five trades or five years is mostly noise. A single unusual year can swing it from strongly positive to negative. Prefer estimates built on many observations, and be skeptical of very high expectancy from small samples. See [How Many Years of Data Do You Need?](/learn/how-many-years-of-data-seasonal-backtest.html)

## Expectancy Is Per Trade; Growth Depends on Size

Positive expectancy tells you a strategy should make money over time. How fast it grows, and how large the drawdowns feel, depends on how much you risk per trade. That is the job of [position sizing](/learn/position-sizing-and-stop-loss-seasonal-trades.html).
