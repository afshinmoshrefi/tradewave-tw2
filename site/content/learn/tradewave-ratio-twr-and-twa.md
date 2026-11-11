---
title: "TradeWave Ratio (TWR) and TradeWave Average (TWA): Measuring Pattern Quality Along the Path"
slug: "tradewave-ratio-twr-and-twa"
summary: "The TradeWave Ratio is TradeWave's signature pattern-quality score. Like the Sharpe Ratio it weighs return against variability, but it also uses Maximum Favorable Excursion, so it rewards windows that move strongly in the right direction even if they did not finish at the peak."
date: "2026-11-11"
author: "TradeWave Research"
category: "metrics"
order: 5
tags: ['twr', 'twa', 'tradewave-ratio', 'pattern-quality', 'metrics']
related: ['mfe-and-mae-explained', 'sharpe-ratio-explained', 'presidential-election-cycle-regimes', 'how-to-find-stocks-with-seasonal-patterns']
faq:
  - q: "What is the TradeWave Ratio (TWR)?"
    a: "TWR is TradeWave's pattern-quality score. It is Sharpe-like, comparing return with variability, but it incorporates Maximum Favorable Excursion so it credits windows that move strongly in the right direction during the trade, not only where they ended."
  - q: "What is a good TWR?"
    a: "A common screening threshold is TWR of at least 1.5 for studies using consecutive years and at least 1.0 for presidential-cycle studies, which have fewer data points. Higher is better."
  - q: "Does TWR replace the Sharpe Ratio?"
    a: "No. TWR complements the Sharpe Ratio. Sharpe judges the consistency of final results; TWR adds information about the favorable path inside the window. Patterns that score well on both are the strongest."
---

## Key Takeaways

- **TWA (TradeWave Average)** is an average outcome computed using Maximum Favorable Excursion, so it reflects the favorable movement that happened during the window, not just where it ended.
- **TWR (TradeWave Ratio)** is TradeWave's signature quality score: Sharpe-like, but incorporating MFE.
- TWR surfaces windows that **move strongly in the right direction along the way**, which the Sharpe Ratio can discard too early.
- Common screening thresholds: **TWR of at least 1.5** for consecutive-year studies, **at least 1.0** for election-cycle studies.
- TWR **complements** Sharpe. It does not replace it.

## The Problem TWR Solves

The [Sharpe Ratio](/learn/sharpe-ratio-explained.html) judges a window by its end-of-window results. That is useful, but it throws away the path.

Consider a window that, year after year, rallies hard in its first few weeks and then gives some of it back before the end date. Its final results look modest and somewhat inconsistent, so its Sharpe Ratio is middling. Yet for a trader with a sensible target, it was a reliable opportunity: it went the right way, strongly, almost every year.

The Sharpe Ratio cannot see that. A metric built on [Maximum Favorable Excursion](/learn/mfe-and-mae-explained.html) can.

## TradeWave Average (TWA)

TWA is TradeWave's average-outcome measure built from MFE. Where a plain average gain asks *where did the window usually end?*, TWA leans on *how far did the window usually run in your favor?* It is a better guide to what a disciplined exit could have captured, though no one sells every top, so treat it as an upper reference rather than a promise.

## TradeWave Ratio (TWR)

TWR takes the familiar Sharpe idea, return relative to variability, and uses each year's MFE in place of its final return. The result:

- Windows with **consistent, strong favorable movement** score well, even if their end-of-window results vary.
- Windows that **only occasionally** run in your favor, or whose favorable moves are erratic, score poorly.

Higher TWR means a more consistent, more efficient pattern.

## Thresholds

| Study type | Common TWR screen | Why |
|---|---|---|
| Consecutive years | 1.5 or higher | More data points, so a higher bar is achievable |
| Presidential-cycle phase (PE, PE+1, PE+2, PE+3) | 1.0 or higher | Each sample year is four calendar years apart, so samples are smaller and noisier |

These are screening thresholds, not guarantees. A pattern that clears them still needs to be [validated year by year](/learn/tradewave-workflow-scan-validate-organize-act.html).

## How to Use TWR and Sharpe Together

| TWR | Sharpe | What it usually means |
|---|---|---|
| High | High | Strong and steady. The best candidates. |
| High | Moderate | Strong favorable moves, inconsistent finishes. Plan targets and exits carefully; do not hold blindly to the end date. |
| Moderate | High | Steady but modest. Fine for conservative sizing. |
| Low | Low | Weak or noisy. Pass. |

## Using TWR in the Opportunities Table

TWR is available as a column and as a filter in the [Opportunities Table](/learn/finding-high-probability-trading-waves.html). A practical routine:

1. Set the lens and depth (see [How Many Years of Data Do You Need?](/learn/how-many-years-of-data-seasonal-backtest.html)).
2. Filter to consistent windows.
3. Apply a TWR screen appropriate to the lens: 1.5 for consecutive years, 1.0 for a cycle phase.
4. Sort the survivors by TWR or Sharpe and validate the top candidates in the Wave Viewer.

## A Caution

Like every metric, TWR summarizes history. It can be inflated by a small sample, and it says nothing about this year's news. Use it to rank and filter, then rely on your own stop, target and position size to manage the trade.
