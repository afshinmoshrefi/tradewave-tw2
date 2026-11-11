---
title: "MFE and MAE Explained: Maximum Favorable and Adverse Excursion for Targets and Stops"
slug: "mfe-and-mae-explained"
summary: "Maximum Favorable Excursion (MFE) is how far a trade moved in your favor at its best point. Maximum Adverse Excursion (MAE) is how far it moved against you at its worst. Together they show what happened inside a trade, and they are the most honest basis for profit targets and stop losses."
date: "2026-11-11"
author: "TradeWave Research"
category: "metrics"
order: 4
tags: ['mfe', 'mae', 'stop-loss', 'profit-target', 'metrics']
related: ['position-sizing-and-stop-loss-seasonal-trades', 'tradewave-ratio-twr-and-twa', 'sharpe-ratio-explained', 'when-to-exit-a-seasonal-trade']
faq:
  - q: "What is maximum adverse excursion (MAE)?"
    a: "MAE is the largest move against your position at any point while the trade was open, measured from the entry price. If you bought at 100 and the price fell to 92 before recovering, the MAE was 8%."
  - q: "What is maximum favorable excursion (MFE)?"
    a: "MFE is the largest move in your favor at any point while the trade was open. If you bought at 100, the price reached 115 and you exited at 106, the MFE was 15% even though you captured 6%."
  - q: "How do you use MAE to set a stop loss?"
    a: "Look at the MAE of the winning years. If winners rarely moved more than 6% against the entry before working out, a stop somewhat beyond that level gives the trade room to behave normally while still cutting losers that go further than winners usually do."
---

## Key Takeaways

- **MFE (Maximum Favorable Excursion):** the best point a trade reached in your favor. It answers **how good can it get?**
- **MAE (Maximum Adverse Excursion):** the worst point a trade reached against you. It answers **how bad can it get?**
- End-of-window returns hide the path. MFE and MAE reveal it.
- **MFE informs profit targets** and option strike choices. **MAE informs stops**, position size and the point where a trade is simply wrong.
- Seasonality is probability, not protection. Even strong windows can show large MAE in a bad year.

## Why the Path Matters

Most backtests report one number per year: where the window ended. But you do not live at the end of the window. You live through every day of it.

Two years can both finish +5%. In one, the price climbed steadily. In the other, it fell 18% first and recovered in the final week. On a spreadsheet they look identical. In a real account, the second one probably hit your stop, triggered a margin call on a leveraged position, or expired your option worthless before the recovery came.

MFE and MAE capture that difference.

## How They Are Measured

For each historical year in a seasonal window, measured from the entry price:

- **MFE** = the largest gain reached at any point before the window ended (for a long trade, the highest price reached).
- **MAE** = the largest loss reached at any point before the window ended (for a long trade, the lowest price reached).

For a short trade, the directions flip: MFE is the deepest fall and MAE is the highest rise.

### Example

You enter a long window at $100.

| Year | Lowest point | Highest point | Close at window end | MAE | MFE | Final |
|---|---|---|---|---|---|---|
| 1 | $97 | $112 | $108 | -3% | +12% | +8% |
| 2 | $90 | $109 | $104 | -10% | +9% | +4% |
| 3 | $99 | $115 | $106 | -1% | +15% | +6% |
| 4 | $88 | $101 | $93 | -12% | +1% | -7% |

From the final column alone, this window won 3 of 4 years. The excursions add the useful detail: winners usually saw small dips (1% to 10%), the loser went much deeper (12%), and the best moves ran well beyond where the window closed.

## Using MAE to Set Stops

A stop should sit beyond the normal noise of a working trade, but before the damage of a failing one.

1. Look at the **MAE of the winning years**. This is how much heat a good trade typically required.
2. Place the stop somewhat beyond the typical winning-year MAE.
3. Compare with the **MAE of the losing years**. If losers routinely went much deeper than winners, the stop separates them well.
4. Size the position so that hitting the stop costs a fixed, small slice of the account. See [Position Sizing and Stop Losses](/learn/position-sizing-and-stop-loss-seasonal-trades.html).

If winners and losers have similar MAE, a stop will not discriminate between them. Use smaller size, or treat the window as a bias rather than a trade.

## Using MFE to Set Targets

MFE shows how far a typical good year ran. A realistic target is often below the typical MFE, because you will not sell the exact top. If the window routinely reaches +12% and closes at +6%, the move tends to fade late, which is a reason to take profits early or tighten the stop near the end. See [When to Exit a Seasonal Trade](/learn/when-to-exit-a-seasonal-trade.html).

For options traders, MFE helps choose a strike the stock has historically reached, and MAE helps decide which structures can survive the typical drawdown.

## Probability Is Not Protection

A well-known example from TradeWave's research: a large-cap technology stock had a historically bullish January window with 18 winners and 2 losers over 20 years. In 2025 a news shock pushed the price **23.16%** against the position at its worst point, and the window finished **-5.22%**. The pattern's history did not prevent a deep MAE. Position size and a planned stop are what protect you.

## Seeing MFE and MAE in TradeWave

In the Wave Viewer you can overlay MFE and MAE on the Profit Bar Chart to see the excursions of every year alongside its final result. TradeWave also builds two proprietary metrics from MFE, the TradeWave Average and the TradeWave Ratio, which reward windows that move strongly in the right direction along the way. See [TradeWave Ratio and TradeWave Average](/learn/tradewave-ratio-twr-and-twa.html).
