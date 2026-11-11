---
title: "Median vs Average Return: How to Spot a Hero Year in a Seasonal Backtest"
slug: "median-vs-average-return"
summary: "An average return can be carried by one spectacular year. The median shows the typical year. Learn why the gap between them matters, how to spot a hero year in a seasonal pattern, and what standard deviation adds."
date: "2026-11-11"
author: "TradeWave Research"
category: "metrics"
order: 6
tags: ['median-return', 'average-return', 'outliers', 'standard-deviation', 'metrics']
related: ['sharpe-ratio-explained', 'how-many-years-of-data-seasonal-backtest', 'understanding-the-stats-table', 'trading-expectancy-explained']
faq:
  - q: "What is the difference between median and average return?"
    a: "The average adds up every year's return and divides by the number of years, so one extreme year can pull it far up or down. The median is the middle result after sorting the years, so it reflects a typical year and ignores how extreme the outliers were."
  - q: "Which is better for evaluating a seasonal pattern, median or average?"
    a: "Use both. If the median is close to the average, the pattern earns its return consistently. If the median is far below the average, one or two big years are carrying the result and the pattern is less dependable than its average suggests."
---

## Key Takeaways

- The **average** (mean) return can be dominated by one or two extreme years.
- The **median** is the middle year after sorting. It shows what a **typical** year looked like.
- A large gap between average and median is the classic sign of a **hero year**.
- **Standard deviation** measures how spread out the yearly results are. High spread means a lumpy record.
- The Profit Bar Chart is the fastest way to see a hero year with your own eyes.

## A Ten-Year Example

Two windows, ten years each, both with an **average gain of +6%**.

| Year | Window A | Window B |
|---|---|---|
| 1 | +5% | +2% |
| 2 | +7% | -3% |
| 3 | +6% | +1% |
| 4 | +4% | +2% |
| 5 | +8% | -2% |
| 6 | +6% | +3% |
| 7 | +5% | +1% |
| 8 | +7% | -1% |
| 9 | +6% | +2% |
| 10 | +6% | +55% |
| **Average** | **+6.0%** | **+6.0%** |
| **Median** | **+6.0%** | **+1.5%** |
| **Wins** | **10 of 10** | **7 of 10** |

Window A earns about 6% almost every year. Window B earns about 1.5% in a typical year and owes its entire average to year 10. Strip out that one year and Window B's average drops to about 0.6%.

Both would show the same "Avg Gain" on a summary screen. Only one is a pattern you can plan around.

## How to Spot a Hero Year

1. **Compare median with average.** In the [Stats Table](/learn/understanding-the-stats-table.html), if the median gain is much lower than the average gain, an outlier is lifting the average.
2. **Look at the bars.** The Profit Bar Chart draws one bar per year. A hero year is impossible to miss: one bar towering over the rest.
3. **Check the spread.** A high standard deviation relative to the average means the results are scattered. The [Sharpe Ratio](/learn/sharpe-ratio-explained.html) will be lower too.
4. **Ask what happened that year.** A takeover bid, a once-in-a-generation crash recovery or a one-off news event will not repeat on schedule.

## Hero Losers Matter Too

Outliers can sit on the downside. A window can show a solid median but one catastrophic losing year that pulls the average down, or that would have wiped out several years of gains. Look at the size of the worst year, and at the [MAE](/learn/mfe-and-mae-explained.html) inside it, not just how many years lost.

## Standard Deviation in Plain English

Standard deviation measures how far the yearly results typically sit from their average. In the example, Window A's results cluster tightly (standard deviation about 1.2%), while Window B's are scattered (about 17%). A lower standard deviation means a steadier pattern. It is also the denominator of the Sharpe Ratio, which is why lumpy patterns score poorly on Sharpe.

## Using Median in Your Own Planning

When you estimate what a trade might earn, start from the median winning year, not the average. It produces more conservative targets and a more honest [expectancy](/learn/trading-expectancy-explained.html) estimate, and it protects you from building a plan around a year that may never repeat.
