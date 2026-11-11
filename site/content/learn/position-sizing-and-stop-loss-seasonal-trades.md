---
title: "Position Sizing and Stop Losses for Seasonal Trades: The 1% Risk Method"
slug: "position-sizing-and-stop-loss-seasonal-trades"
summary: "How much should you buy, and where should the stop go? Learn the 1% risk method for position sizing, how to place a stop using a seasonal window's historical drawdowns, and how to plan the exit before you enter."
date: "2026-11-11"
author: "TradeWave Research"
category: "risk"
order: 1
featured: true
tags: ['position-sizing', 'stop-loss', 'risk-management', '1-percent-rule']
related: ['win-rate-vs-risk-reward-ratio', 'mfe-and-mae-explained', 'when-to-exit-a-seasonal-trade', 'trading-expectancy-explained']
faq:
  - q: "How do I calculate position size?"
    a: "Position size = amount you are willing to risk / distance to your stop. If you risk $1,000 and your stop is 5% below entry, the position is $1,000 / 0.05 = $20,000. If the stop is $4 below a $100 entry, you can buy $1,000 / $4 = 250 shares."
  - q: "What is the 1% rule in trading?"
    a: "The 1% rule means sizing each position so that hitting your stop loses no more than about 1% of your account. It keeps any single loss small and lets you survive a string of losers, which every strategy eventually has."
  - q: "Where should I put a stop loss on a seasonal trade?"
    a: "Somewhat beyond the drawdown that winning years typically endured inside the window, measured by Maximum Adverse Excursion. That gives the trade room to behave normally while cutting losers that move further against you than good years usually did."
---

## Key Takeaways

- Decide **how much you are willing to lose** before deciding how much to buy.
- **Position size = risk per trade / distance to the stop.**
- The **1% rule**: risk about 1% of the account per trade, so a string of losers stays survivable.
- Place the stop using the window's history: somewhat beyond the drawdown that **winning years** typically endured ([MAE](/learn/mfe-and-mae-explained.html)).
- Plan three numbers before entering: **target, stop and exit date**.

## Step 1: Decide Your Risk Per Trade

Pick a fixed percentage of the account you are willing to lose if a trade fails. Many traders use **0.5% to 2%**, with **1%** a common default.

Why so small? Because losing streaks happen. With 1% risk per trade, ten losers in a row cost about 10% of the account, which is painful but recoverable. With 10% risk per trade, the same streak can end the account.

| Risk per trade | Account left after 10 straight losses |
|---|---|
| 1% | about 90% |
| 2% | about 82% |
| 5% | about 60% |
| 10% | about 35% |

## Step 2: Choose the Stop From the Window's History

A stop is the price that says *this trade is wrong*. For a seasonal trade you have something most traders do not: years of evidence about how far good trades typically moved against you.

1. Open the window in the Wave Viewer and overlay MAE on the Profit Bar Chart.
2. Note the typical adverse move in the **winning** years. Say winners usually dipped 2% to 4% before working out.
3. Set the stop somewhat beyond that range, for example 5% below entry, so normal noise does not knock you out.
4. Check that losing years usually went **further** than that. If they did, the stop separates good years from bad ones.

If winners routinely dipped as deeply as losers did, no stop will distinguish them cleanly. Trade smaller or pass.

## Step 3: Calculate the Position Size

**Position size = (account x risk %) / stop distance**

Example: a $100,000 account, 1% risk, and a stop 5% below entry.

- Risk = $100,000 x 1% = **$1,000**
- Position = $1,000 / 5% = **$20,000**
- At a $50 share price, that is **400 shares**, with the stop at **$47.50**.

If the stop is hit, you lose about $1,000 (plus slippage), exactly the amount you planned.

Notice that a wider stop means a **smaller** position, and a tighter stop means a larger one. The risk stays constant; the size adjusts.

## Step 4: Set the Target and the Exit Date

- **Target:** informed by the typical favorable move, [MFE](/learn/mfe-and-mae-explained.html), but usually set below it, since no one sells every top. Using the median rather than the best years keeps it realistic.
- **Exit date:** the end of the window. Seasonal moves tend to peak and fade, and holding past the end often gives gains back. See [When to Exit a Seasonal Trade](/learn/when-to-exit-a-seasonal-trade.html).

Write all three numbers down before entering. Traders who plan exits execute them. Traders who do not, improvise, usually badly.

## How the Pieces Add Up

Hypothetical: ten trades sized as above, with a 40% win rate.

- 4 winners at +6% on $20,000 = +$1,200 each = **+$4,800**
- 6 losers averaging -2.5% on $20,000 = -$500 each = **-$3,000**
- Net: **+$1,800**

The trader lost more often than they won and still came out ahead, because losses were planned and small and winners had room to run. That is the arithmetic in [Win Rate vs Risk Reward Ratio](/learn/win-rate-vs-risk-reward-ratio.html), and [Trading Expectancy Explained](/learn/trading-expectancy-explained.html) shows how to estimate it before you trade.

## Adjusting Size to the Quality of the Pattern

Not every setup deserves full size. Consider trading smaller when:

- The [Sharpe Ratio](/learn/sharpe-ratio-explained.html) is low, meaning the yearly results are lumpy.
- The sample is thin, or the record depends on a [hero year](/learn/median-vs-average-return.html).
- Current price action strongly disagrees with the seasonal bias.
- You already hold several positions that tend to move together.

## Diversify Across Windows

One seasonal trade is a probability. A collection of independent ones, spread across different sectors, start dates and holding periods, is a strategy. A portfolio that only works when one sector leads is a bet, not a plan.
