---
title: "Combining Seasonality and Momentum: A Hybrid Edge with Academic Pedigree"
slug: seasonality-momentum
summary: "Heston and Sadka's 2008 paper found that stocks with high returns in a given calendar month tend to outperform again in the same month for years afterward. The combined seasonal-plus-momentum signal is stronger than either alone."
date: 2026-05-08
author: TradeWave Research
reading_minutes: 9
tags: ["seasonality", "momentum", "factor-models", "academic"]
featured: false
related: ["sector-seasonality", "machine-learning-in-finance", "post-earnings-drift"]
---

Two of the most thoroughly studied effects in equity markets are momentum (recent winners keep winning) and seasonality (calendar-tied return patterns). Each, on its own, is a significant body of literature with thousands of citations. Combined, they produce a signal that has survived 15-plus years of out-of-sample replication and global cross-checks. This article walks through the parent factors, the hybrid signal that emerges from combining them, and the implementation realities for anyone trying to deploy it.

## The two parent factors

The momentum literature begins with Jegadeesh and Titman (1993) "Returns to Buying Winners and Selling Losers" in the Journal of Finance. They show that buying U.S. stocks ranked in the top decile of 6-12 month past returns and shorting the bottom decile produced abnormal returns of about 1% per month over the next 3-12 months. The effect was large, robust to common risk adjustments, and could not be explained by lead-lag effects in stock prices. Two decades of follow-up research has confirmed the effect across markets (international momentum, Rouwenhorst 1998), asset classes (Asness, Moskowitz, and Pedersen 2013 "Value and Momentum Everywhere"), and time periods, while also documenting a notable crash risk: in 2009 the momentum factor lost roughly 80% of its peak value as the rebound rotation crushed long-winner positions.

The seasonality literature is older but historically focused on aggregate calendar anomalies (the January effect, the Halloween effect, day-of-week effects). What changed with Heston and Sadka (2008) "Seasonality in the Cross-Section of Stock Returns" in the Journal of Financial Economics was the application of seasonality to the individual-stock cross-section.

## What Heston and Sadka actually showed

The Heston and Sadka methodology is direct. For each stock and each calendar month, calculate the average return that stock has earned in that month over its history (excluding the most recent observation). Then, in any given calendar month, rank the universe by that historical same-month return. Buy the top decile, short the bottom decile.

The result, on U.S. data from 1965 through 2002: the top-decile portfolio outperformed the bottom-decile portfolio by approximately 0.93% per month in the same calendar month, and the effect persisted out 5, 10, and even 20 years. A stock that had historically performed well in March kept performing well in March, on average, for two decades.

Three things make this finding striking. First, the effect is in the cross-section. It is not "January is good for stocks"; it is "stocks that are historically good in January tend to be good this January." The general calendar-anomaly literature does not explain it because no single month drives the result. Second, the effect compounds across years: a stock that is a "March winner" in its history continues to be a March winner in subsequent Marches, and the pattern is replicated for every other month of the year. Third, the effect survives standard factor controls (size, value, momentum, industry).

## Why does this happen?

Three mechanism hypotheses dominate the literature.

The first is firm-specific seasonal cash flows. A retailer always has Q4 strength because its business is concentrated there. A mining company that operates in the southern hemisphere always discloses production around the same window. A REIT that owns ski resorts has a Q1 calendar. The market knows these patterns; equity prices internalise them; but the price reaction to known seasonal events is not always efficient, particularly for smaller and less-liquid names where attention is limited.

The second is liquidity and tax effects clustered in time. Tax-loss selling concentrates in November and December. Window dressing concentrates at quarter-ends. Mutual-fund tax distributions occur at predictable points in the calendar. Stocks that are historically affected by these flows continue to be affected, year after year, because the underlying institutional behaviour does not change.

The third is behavioural. Institutions rebalance on calendars: year-end window dressing, fiscal-year close, and pension reallocation cycles all create predictable demand and supply at predictable times. Stocks with characteristics that make them attractive or unattractive to those rebalancing flows experience repeated pressure in the same months.

Heston and Sadka are careful to note that the data alone cannot distinguish among these explanations, and the most likely answer is that all three contribute in different proportions across different stocks.

<figure><img src="/insights/charts/seasonality-momentum-combo.svg" alt="Seasonality + momentum combined returns"><figcaption>Cumulative excess return for seasonal-only, momentum-only, and combined signals (illustrative). Combination Sharpe in published studies tends to exceed either standalone Sharpe.</figcaption></figure>

## Replications and extensions

The Heston-Sadka result was striking enough that it triggered an immediate wave of replication and extension work.

Heston, Korajczyk, and Sadka (2010) "Intraday Patterns in the Cross-Section of Stock Returns" in the Journal of Finance applies the same logic at the intraday level: stocks that have historically done well in the first hour of trading continue to do well in that hour. The mechanism is presumably tied to recurring institutional execution patterns at predictable times of day.

Keloharju, Linnainmaa, and Nyberg (2016) "Return Seasonalities" in the Journal of Finance is the most thorough replication. They extend the test to international markets, multiple asset classes (U.S. stocks, international stocks, country indices, commodities, currencies), and longer horizons. The seasonal effect is global, robust to controls for size, value, momentum, and industry, and survives in every major asset class they examine. They explicitly conclude that "seasonalities" is an underappreciated source of cross-sectional return predictability.

These replications matter because the multiple-testing critique (Harvey, Liu, and Zhu 2016 "and the Cross-Section of Expected Returns") raised legitimate concerns that many anomalies are statistical artefacts of search effort. The cross-sectional seasonality result has now survived two decades of out-of-sample replication, in foreign markets and other asset classes, with consistent magnitudes. That puts it in the small group of factor anomalies that most academic asset-pricing researchers consider real.

## Why combining seasonality with momentum helps

Both factors have weaknesses. Momentum has crash risk: when the market regime shifts, recent winners lose hard. Daniel and Moskowitz (2016) "Momentum Crashes" document that momentum drawdowns in 1932, 2001, and 2009 reached 60% to 80% peak-to-trough as the leadership rotated. Seasonality, on the other hand, has weak short-horizon predictive power on its own; the monthly signal-to-noise ratio is low, and standalone seasonal portfolios produce modest Sharpe ratios.

The combination addresses both weaknesses. Used together, the seasonal signal acts as a regime filter for momentum: rather than buying every momentum winner, buy only those that also have a positive same-month seasonal pattern. Conversely, the momentum overlay sharpens the seasonal signal: rather than buying every stock with a strong same-month history, buy only those that are currently in a positive momentum regime.

Several published studies have shown that the combination outperforms either standalone signal on Sharpe, including in the Keloharju et al. work and various practitioner replications. The intuition: the two signals capture distinct sources of predictability (current trend versus historical calendar pattern), so their combination has more information than either alone.

## A practical implementation outline

A retail-tractable version of the strategy looks like this.

First, define a universe. The published research uses NYSE and NASDAQ common equities; in practice you want enough liquidity to trade and enough names for cross-sectional ranking, so the S&P 1500 is a reasonable starting point.

Second, compute a 6-month or 12-month momentum rank for every name. The Jegadeesh-Titman convention is 12-2 (the past 12 months excluding the most recent month, to avoid short-term reversal contamination); 6-1 is also common.

Third, compute a same-month historical seasonal rank for every name. For the upcoming calendar month, calculate each stock's average return in that month over the prior 10-20 years (Keloharju et al. find the effect strengthens with longer windows up to 20 years, then plateaus).

Fourth, intersect. Take the top quintile or decile by momentum, then within that subset rank by same-month seasonal score. Hold the top X names for the calendar month, then rebalance.

Fifth, control transaction costs. Monthly rebalancing in a long-only structure is expensive at retail; layer in turnover thresholds (only trade names that move across rank tiers, not every name every month) and you cut costs significantly.

<div class="article-tw-callout"><strong>Doing the same-month rank.</strong> The Heston and Sadka methodology requires looking at how a stock has performed historically in a specific calendar month. Tools that show per-year bars for a given date range (TradeWave's Wave Viewer at /app/, or any seasonal-pattern viewer) make this measurement direct rather than spreadsheet-tedious.</div>

## The academic-versus-implementation gap

The gross Sharpe ratios reported in academic papers for the seasonality-momentum combination cluster around 1.0 to 1.5 annualised, depending on the universe, weighting scheme, and sample period. These are pre-cost numbers. After realistic transaction costs (modelled at the level of typical retail commission and bid-ask slippage), the realised Sharpe falls into the 0.5 to 0.8 range. That is still a defensible alpha source for a retail portfolio, but it is far below the headline numbers.

Three further implementation considerations matter.

Capacity is real. The Heston-Sadka effect is partially driven by smaller and less-liquid names; a strategy that scales to billions of dollars cannot trade those names without moving prices. The retail investor's advantage here is that capacity is not their problem. Picking 20 to 50 names within a $1 million account is well below any realistic capacity ceiling.

Regime breaks matter. 2020 was an unusually destructive year for many factor strategies, including momentum, because the market regime change happened too fast for trailing signals to adjust. Seasonality is a slower signal and may have suffered less, but the combination strategy still drew down materially in the COVID quarter. Any backtest that includes 2020 should be looked at with sensitivity analysis applied; any backtest that excludes 2020 is hiding a real risk.

Sample-period sensitivity matters. The Heston-Sadka original sample was 1965-2002. The 2008-2026 period has had two major regime shifts (the GFC, COVID) and the rise of passive flows, which may be changing the way institutional rebalancing affects individual stocks. Using a 20-year same-month window today means weighting the 2005-2025 era heavily, which may or may not be a good representation of the next decade.

## Practical takeaway

The cross-sectional seasonality effect documented by Heston and Sadka, and the combination of seasonality with momentum, sit in a small group of equity-market anomalies that have survived 15 years of out-of-sample replication, global cross-checks, and methodological scrutiny. The underlying evidence is strong enough that institutional managers do trade variants of these strategies.

For a retail investor, the realistic path is one of two:
- Accept the lower-Sharpe, lower-turnover version of the strategy (rank quarterly rather than monthly, hold longer, focus on a manageable number of names) and treat the result as one component of a diversified factor allocation.
- Or use the seasonality framework as a filter for an existing momentum or growth process, rather than as a standalone strategy.

What is not realistic is treating the published Sharpe ratios as achievable returns. Gross-of-cost research papers describe the effect; net-of-cost reality is roughly half the headline number after taxes and slippage. The signal is real; the implementation is the hard part.

Combined with the broader cross-sectional asset-pricing literature (the Fama-French 5-factor model, the Hou-Xue-Zhang q-factor model, the recent ML-augmented work in Gu, Kelly, and Xiu 2020 covered in our companion article), the seasonality-momentum combination sits in a coherent picture: equity returns have multiple, partly orthogonal sources of predictability, and a portfolio that combines them prudently can earn meaningful risk-adjusted excess return without making any single-factor bet.
