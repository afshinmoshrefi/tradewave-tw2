---
title: "Curve-Fitting vs Window Alignment: How to Adjust a Seasonal Window Without Fooling Yourself"
slug: "curve-fitting-vs-window-alignment"
summary: "Shifting a seasonal window a few days to line up with where the move really begins is legitimate. Searching the whole calendar for the best-looking dates is curve-fitting. Here is how to tell the difference and protect yourself from overfitting."
date: "2026-11-11"
author: "TradeWave Research"
category: "risk"
order: 2
tags: ['curve-fitting', 'overfitting', 'backtesting', 'window-alignment', 'data-mining']
related: ['how-many-years-of-data-seasonal-backtest', 'understanding-the-trend-chart', 'when-to-exit-a-seasonal-trade', 'sharpe-ratio-explained']
faq:
  - q: "What is curve-fitting in trading?"
    a: "Curve-fitting, or overfitting, is tuning a strategy so precisely to past data that it captures random noise instead of a real, repeatable effect. It produces backtests that look excellent and real-world results that disappoint."
  - q: "Is adjusting a seasonal window's dates curve-fitting?"
    a: "Not if the adjustment is small and grounded in what the chart shows, such as moving the start a few days to the point where the move typically begins. It becomes curve-fitting when you search every possible start and end date for the best statistics."
  - q: "How can I tell if a seasonal pattern is overfit?"
    a: "Warning signs include very short sample periods, oddly specific dates that collapse when shifted a few days, results that only work in one lookback, statistics that are far better than similar windows nearby, and no plausible real-world reason for the pattern."
---

## Key Takeaways

- **Alignment** is shifting a window's start or end by a small amount to match where behavior actually changes. It is legitimate.
- **Curve-fitting** is searching across the whole calendar for the dates with the best statistics. It manufactures patterns out of noise.
- A real pattern is **robust**: it stays good when you nudge the dates or the lookback.
- An overfit pattern is **fragile**: small changes make it collapse.
- The goal of a backtest is not to find what always works. It is to find what has worked **consistently enough** and **stably enough** to be useful.

## Why Overfitting Happens

Test enough combinations and something will always look brilliant. With thousands of securities, 365 start dates and dozens of holding periods, pure chance guarantees some windows with perfect-looking records. This is sometimes called *torturing the data until it confesses*.

The more combinations you try, the more skeptical you should be of the best one you find. Our Insights essay [Why Most Backtests Lie](/insights/backtesting-pitfalls.html) covers the statistics behind this.

## What Legitimate Alignment Looks Like

Seasonal behavior rarely flips on an exact date. The [Trend Chart](/learn/understanding-the-trend-chart.html) compresses many years into the typical path, and usually shows a **pivot zone** where the average bends and the real move begins, and a **peak zone** where it tends to stall.

Alignment means moving a window's edges a small distance to start at the pivot rather than a few days before it, or to end near the peak rather than well after it. In one documented example, moving a window's start by four days to its typical turning point lifted the Sharpe Ratio from 0.8 to 1.14. The pattern did not change. The measurement just started where the behavior actually starts.

### The Rules of Honest Alignment

1. **Start from a pattern that is already good.** Alignment refines a real edge. It should not create one.
2. **Move by small amounts:** days, not weeks.
3. **Have a visible reason** on the Trend Chart for every adjustment.
4. **Check the neighbors.** If shifting by a day or two in either direction destroys the result, the original was fragile.
5. **Recheck in other lookbacks.** An aligned window should still look good over 10, 15 and 20 years.

## What Curve-Fitting Looks Like

- Scanning every start and end date of the year for the highest Sharpe Ratio.
- Choosing whichever lookback makes the numbers best, then presenting it as the pattern.
- Adding conditions one at a time until the losing years disappear.
- Dates so specific that a two-day shift ruins the record.
- No plausible real-world reason for the window to exist.

## A Simple Robustness Checklist

Before you trust a window, ask:

- Does it hold up over at least two different lookbacks? See [How Many Years of Data Do You Need?](/learn/how-many-years-of-data-seasonal-backtest.html)
- Is the median close to the average, with no hero year? See [Median vs Average Return](/learn/median-vs-average-return.html)
- Do nearby windows (a few days earlier or later, a little shorter or longer) look similar?
- Is there a plausible driver: a sales season, fiscal calendar, harvest, tax date or policy cycle?
- Were the losing years small?

Patterns that pass all five deserve your attention. Patterns that fail several are probably noise, no matter how good the headline number looks.

## The Opposite Mistake: Overstaying

Alignment applies to exits too. Widening a window well past its typical peak usually destroys it. In one example, a 17-day window with a Sharpe Ratio of 2.18 and a perfect record fell to a Sharpe Ratio of about zero and a 60% win rate when stretched to 86 days. See [When to Exit a Seasonal Trade](/learn/when-to-exit-a-seasonal-trade.html).
