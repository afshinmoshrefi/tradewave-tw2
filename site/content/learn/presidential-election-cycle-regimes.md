---
title: "The Presidential Election Cycle Lens: How PE, PE+1, PE+2 and PE+3 Change Seasonal Patterns"
slug: "presidential-election-cycle-regimes"
summary: "The four-year U.S. presidential cycle changes how markets behave through the calendar. Learn what PE, PE+1, PE+2 (midterm) and PE+3 mean, why blending all years can hide a real pattern, and how to use the cycle lens in TradeWave."
date: "2026-11-11"
author: "TradeWave Research"
category: "seasonal-trading"
order: 4
tags: ['presidential-cycle', 'election-cycle', 'midterm-year', 'pe-plus-2', 'regimes']
related: ['how-many-years-of-data-seasonal-backtest', 'what-is-a-seasonal-pattern', 'seasonal-investing-for-long-term-investors', 'how-to-find-stocks-with-seasonal-patterns']
faq:
  - q: "What does PE+2 mean in TradeWave?"
    a: "PE+2 is the midterm-election year, the second year after a presidential election. PE is the election year, PE+1 the year after, and PE+3 the pre-election year. Selecting PE+2 measures a pattern using only past midterm years."
  - q: "How does a midterm election year affect the stock market?"
    a: "In TradeWave's research on the S&P 500 since 1930, midterm years have been the most volatile and correction-prone phase of the cycle, with weakness concentrated from May through October, followed by historically strong performance from late September into the following summer."
  - q: "Why does '10 years' mean something different in cycle mode?"
    a: "Ten consecutive years covers a decade. Ten midterm years covers roughly forty years, because a midterm comes once every four years. They are different datasets, so a pattern can look strong in one and weak in the other."
---

## Key Takeaways

- The U.S. presidential cycle has four phases: **PE** (election year), **PE+1** (post-election), **PE+2** (midterm) and **PE+3** (pre-election).
- Many seasonal patterns behave very differently depending on the phase. Averaging all years together can **hide a real edge or manufacture a fake one**.
- A cycle setting is a **lens**, not a fact about the market. Changing it changes which years you measure.
- "10 years" in consecutive mode and "10 PE+2 years" are **different datasets**.
- When the consecutive lens and the cycle lens **disagree**, that disagreement is itself useful information.

## The Four Phases

| Phase | Name | Example years |
|---|---|---|
| PE | Presidential election year | 2016, 2020, 2024 |
| PE+1 | Post-election year | 2017, 2021, 2025 |
| PE+2 | Midterm-election year | 2018, 2022, 2026 |
| PE+3 | Pre-election year | 2019, 2023, 2027 |

The label is relative to the calendar, so it moves forward each year. 2026 is a PE+2 year; 2027 will be PE+3.

The cycle matters for markets not because of politics in the abstract, but because policy timing, fiscal decisions and investor expectations tend to follow the electoral calendar. Our Insights essay on [the presidential cycle](/insights/presidential-cycle.html) reviews the academic evidence and its limits.

## Why Blending Years Can Mislead

Imagine a stock that rises strongly in a certain window in three phases of the cycle and falls in the fourth. Averaged over all years, the window looks mediocre. Measured by phase, it is strong three years out of four and a clear short in the fourth. The blended number told you less than either version.

TradeWave's research on "Sell in May" shows this effect at index scale. Across 24 cycles from 1930 to 2022, S&P 500 weakness from May to October concentrated almost entirely in **midterm years**. In the other three phases, May through October was positive. The slogan is half-right: it describes a real effect, but in the wrong years.

## The Midterm Year Is Special

PE+2 has historically been the messiest year of the cycle: the most volatile and the most prone to corrections. That is exactly why isolating it is revealing. After the midterm turbulence, TradeWave's research finds one of the most persistent windows in market history: from about **September 27** of a midterm year to about **July 18** of the next year, the S&P 500 rose in **23 of 24 cycles** since 1930, failing only in 1930 itself. That window is known as [the 100-Year Pattern](/100-year-pattern).

A pattern that strong is not a promise, and TradeWave treats it as context. But it shows why the lens matters: it only becomes visible once midterm years are separated from the rest.

## How to Use the Lens in TradeWave

The cycle lens is available in both the Opportunities Table and the Wave Viewer.

1. **Set the lens before you read anything.** Choose consecutive years or a specific phase. This changes the dataset, not just the chart.
2. **Set the depth deliberately.** In consecutive mode you can go back many decades. In cycle mode each sample year is four calendar years apart, so the available count is much smaller. See [How Many Years of Data Do You Need?](/learn/how-many-years-of-data-seasonal-backtest.html)
3. **Read "10 of 10" correctly.** In cycle mode it means 10 qualifying phase years, not 10 years in a row.
4. **Compare lenses.** Hold the date, depth and holding period constant and toggle only the lens. If a scan that is mostly bullish in consecutive years becomes mostly bearish in the current phase, the current phase deserves your attention.
5. **Use lower quality thresholds in cycle mode.** Fewer data points means noisier statistics. A common screen is a TradeWave Ratio of at least 1.5 in consecutive mode and at least 1.0 in cycle mode. See [TradeWave Ratio and TradeWave Average](/learn/tradewave-ratio-twr-and-twa.html).

## A Worked Example of a Regime Flip

In one TradeWave study, scanning S&P 500 stocks for windows starting January 5, 2026 with 5 to 60 day holds:

- **Consecutive 10-year lens:** 85 opportunities, about 93% of them bullish.
- **PE+2 10-year lens:** 30 opportunities, about 83% of them bearish.

Same date, same holding periods, opposite tone. The scan did not change the market; it changed which years were in the sample. When lenses disagree this sharply, the clearer and more internally consistent lens is usually the better guide for that year, and it is a strong reason to be cautious with blended-year signals.

## Common Mistakes

- **Mixing lenses without noticing.** Always check which lens and depth produced a number before comparing it with another.
- **Over-trusting small cycle samples.** Six midterm years is a thin record. Look for large margins, small losing years and a plausible cause.
- **Treating the cycle as destiny.** It is a lens for measuring probability, not a calendar of guaranteed outcomes.
