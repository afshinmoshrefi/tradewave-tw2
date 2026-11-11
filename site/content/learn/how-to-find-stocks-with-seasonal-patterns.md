---
title: "How to Find Stocks With Seasonal Patterns: A Step-by-Step Guide"
slug: "how-to-find-stocks-with-seasonal-patterns"
summary: "A practical, step-by-step method for finding stocks, ETFs and indexes with reliable seasonal patterns: choose a universe and start date, set the year lens and depth, filter for consistency, then validate each candidate before you trade it."
date: "2026-11-11"
author: "TradeWave Research"
category: "seasonal-trading"
order: 3
tags: ['seasonal-stocks', 'stock-screener', 'opportunities-table', 'how-to']
related: ['finding-high-probability-trading-waves', 'tradewave-workflow-scan-validate-organize-act', 'how-many-years-of-data-seasonal-backtest', 'curve-fitting-vs-window-alignment']
faq:
  - q: "How do I find stocks with seasonal patterns?"
    a: "Pick a start date and a universe of securities, measure how each one performed over every holding period from that date across many years, keep the windows that worked in a large share of years with a strong risk-adjusted return, then inspect each survivor year by year before trading it. TradeWave's Opportunities Table automates the scan."
  - q: "What win rate should a seasonal pattern have?"
    a: "Many traders start with patterns that worked in at least 80% of sampled years, such as 9 of 10 or 16 of 20. Win rate alone is not enough; also check the median gain, the size of losing years and the Sharpe Ratio."
  - q: "Can I find seasonal patterns in ETFs and commodities too?"
    a: "Yes. Seasonality often shows up clearly in sector ETFs, indexes and commodity futures because their drivers, such as energy demand or harvest timing, are tied to the calendar."
---

## Key Takeaways

- Finding seasonal stocks is a **search across three dimensions**: securities, start dates and holding periods.
- Set the **year lens** and **sample depth** before reading any results, because they define the data.
- Filter for **consistency first** (such as 9 of 10 years), then rank by **risk-adjusted quality** (Sharpe Ratio, TradeWave Ratio).
- Every candidate must be **validated year by year** before it becomes a trade.
- Avoid the biggest trap: searching every possible date range until something looks perfect.

## Why Searching by Hand Is So Hard

To find a seasonal pattern you need to answer: for this security, starting on this date, holding for this many days, what happened in each of the last N years? Now repeat that for every holding period from a few days to several months, for every start date of the year, for thousands of securities. That is millions of windows and billions of price comparisons, and it is why seasonality is underused. TradeWave runs that search for you, on the order of a trillion data points.

## Step 1: Choose the Universe

Decide where to look. Common choices are the S&P 500, the Nasdaq 100, the Dow 30, sector groups, ETFs, futures and currencies. Start with a universe you understand. Available universes depend on your plan.

## Step 2: Choose the Start Date

Most traders scan for windows that **open soon**, such as today or a few days ahead, so there is time to plan the entry. You can also look ahead weeks or months to build a calendar of upcoming setups.

## Step 3: Set the Lens and the Depth

These two controls change the underlying data, not just the display:

- **Lens:** consecutive calendar years, or one phase of the presidential cycle such as midterm years only. See [The Presidential Election Cycle Lens](/learn/presidential-election-cycle-regimes.html).
- **Depth:** how many years in the sample. Ten consecutive years is a common default; 15 or 20 gives a sturdier record. See [How Many Years of Data Do You Need?](/learn/how-many-years-of-data-seasonal-backtest.html)

A useful trick: run the same scan twice, once in consecutive years and once in the current cycle phase. If the results flip from mostly bullish to mostly bearish, the cycle phase is telling you something important about this year.

## Step 4: Filter for Consistency

Keep only windows that finished in the right direction in a large share of years. A 9-of-10 filter is a good starting point and is TradeWave's default view. This removes most coincidences before you look at anything else.

## Step 5: Rank by Quality, Not Just Return

Among consistent windows, prefer those with a higher [Sharpe Ratio](/learn/sharpe-ratio-explained.html) and [TradeWave Ratio](/learn/tradewave-ratio-twr-and-twa.html). These reward steady, repeatable moves over erratic ones. A big average gain with a low Sharpe Ratio usually means a bumpy ride or a hero year.

You can also narrow by holding period. Short windows of a few weeks suit active traders. Windows of several months suit swing traders and investors.

## Step 6: Validate Each Candidate

Open each shortlisted window in the [Wave Viewer](/learn/using-the-wave-viewer.html) and read the evidence in order:

1. **Profit Bar Chart:** is the record broad-based, with small losing years?
2. **Trend Chart:** is the typical path clean, and where does the move usually start and peak?
3. **Stats Table:** do the numbers confirm it, including [median vs average](/learn/median-vs-average-return.html) and cumulative return against buy and hold?

Drop anything where the three views disagree. The full loop is in [Scan, Validate, Organize, Act](/learn/tradewave-workflow-scan-validate-organize-act.html).

## Step 7: Plan and Save

For each keeper, write down the target, stop and exit date, size the position, and save the pattern to the [Portfolio Manager](/learn/using-the-portfolio-manager.html) with a calendar reminder.

## What to Avoid

- **Endless date shopping.** If you test every possible start and end date, some window will look extraordinary by chance alone. Small, honest adjustments are fine; hunting the whole calendar is not. See [Curve-Fitting vs Window Alignment](/learn/curve-fitting-vs-window-alignment.html).
- **Thin samples.** Treat anything built on a handful of years as a hypothesis, not evidence.
- **Ignoring the losing years.** Always look at how bad the failures were, not just how often they happened.

Ready to try it? The [four-minute tour](/learn/learn-tradewave-in-4-minutes.html) walks through the same steps on screen.
