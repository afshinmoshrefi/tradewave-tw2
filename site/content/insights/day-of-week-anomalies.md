---
title: "Day-of-Week Effects: From the Monday Anomaly of 1980 to Today's Flat Markets"
slug: "day-of-week-anomalies"
summary: "Ken French's 1980 paper showed Mondays returned negative on average while Fridays returned positive. The pattern was real, robust, and is now mostly gone. Here's the autopsy."
date: "2026-05-08"
author: "TradeWave Research"
reading_minutes: 7
tags: ["seasonality", "day-of-week", "academic", "methodology"]
featured: false
related: ["backtesting-pitfalls", "halloween-effect", "reading-patterns-without-fooling-yourself"]
---

For thirty years, Monday was the worst day to own U.S. stocks. The pattern was robust, replicated across independent studies, backed by plausible mechanisms and a serious academic literature. Then it vanished. Today the Monday effect is gone from the major U.S. indices, and its disappearance is the cleanest case study in markets of how an anomaly dies. It is worth understanding not for nostalgia but for a question you face with every pattern you trade: how confident should you be in an edge that other people can also see?

## What French actually found

The canonical reference is French (1980), Stock Returns and the Weekend Effect, in the Journal of Financial Economics. French studied close-to-close S&P 500 returns from 1953 to 1977 and reported a striking pattern: Monday returns averaged negative, around -0.17% per Monday, while every other day of the week showed modestly positive averages. Friday in particular tended to be the strongest day. The Monday effect was not a small bias on top of an otherwise random walk; it was a systematic, statistically significant feature of the data.

The original interpretation was framed in terms of two competing hypotheses. The "calendar-time" hypothesis predicts that Monday close-to-close returns should reflect three calendar days (Friday close to Monday close), so they should average roughly three times the typical daily return. They did not. The "trading-time" hypothesis predicts each trading day should look the same. Mondays did not look the same; they looked worse. The result was a puzzle that motivated a decade of follow-on work.

## The replications and refinements

The effect was robust enough to attract attention. Lakonishok and Smidt (1988), in Are Seasonal Anomalies Real? A Ninety-Year Perspective, used Dow Jones data going back to 1897 and confirmed a persistent Monday-negative pattern across multiple subperiods. Their broader contribution was to show that several calendar anomalies (turn-of-the-month, holiday effect, January effect, day-of-week) coexisted in the historical record, raising the question of whether they shared common drivers.

Connolly (1989), in An Examination of the Robustness of the Weekend Effect, was an early dissenting voice. He argued that the weekend effect was largely confined to specific subsamples, that standard-error corrections weakened the apparent significance, and that the pattern after the late 1970s was already noticeably weaker than in the French sample. With hindsight, Connolly's caution looks prescient.

A range of mechanism hypotheses appeared in the literature:

- **Bad-news Monday**: companies with negative news prefer to release it Friday after the close, when the market cannot react until Monday morning, depressing Monday opens and close-to-close returns.
- **Bid-ask bounce**: lower trading activity around the weekend interacted with quote conventions to bias measured Monday returns down.
- **Settlement timing**: pre-1990s settlement conventions in U.S. markets meant Friday-purchased stock did not require funding until the following week, creating a slight buying bias on Fridays and a corresponding pressure on Mondays.
- **Investor attention and behavioral cycles**: weekend mood effects, informed-trader return-to-desk patterns, and other behavioral stories.

None of these was decisively confirmed. Each could explain a fraction of the effect, and different studies favored different combinations.

<figure><img src="/insights/charts/dow-monday-effect-decay.svg" alt="Day-of-week effect by decade"><figcaption>S&P 500 mean daily return by day-of-week, four decades. The Monday effect is clearly negative pre-1990 and effectively gone after.</figcaption></figure>

## The decline

Sometime in the 1990s, the Monday effect started to fade. Mehdian and Perry (2001), in The Reversal of the Monday Effect: New Evidence from US Equity Markets, document that the effect had not just weakened but reversed in some specifications during the 1987-1998 subsample. That is exactly what one would expect if traders were aware of and trading against the historical pattern: as buyers stepped in to purchase on weak Monday opens, the bias smoothed out and eventually flipped sign in some windows.

Sullivan, Timmermann and White (2001), Dangers of Data Mining: The Case of Calendar Effects in Stock Returns, in the Journal of Finance, made a more aggressive statistical critique. They applied a bootstrap-corrected procedure that explicitly accounts for the fact that researchers had tested many calendar effects. After multiple-testing correction, much of the apparent significance of day-of-week, week-of-month, and similar anomalies in U.S. data weakened substantially. Sullivan, Timmermann and White did not claim the underlying patterns were never real. They argued that the published significance levels overstated how surprising the patterns should have been to a researcher who had explored a large universe of possible calendar regularities.

Olson, Mossman and Chou (2015), The Evolution of the Weekend Effect in US Markets, document the disappearance more formally. They show that across multiple specifications and subperiods, the post-1995 U.S. data does not support a statistically significant Monday effect at conventional thresholds. The pattern that French had documented for 1953-1977 had functionally vanished by the time anyone could put a name to its disappearance.

## Why it disappeared

Three mechanism stories are usually offered for the decay, and they are not mutually exclusive.

**Algorithmic and institutional trading.** Through the 1990s and 2000s, electronic trading and algorithmic execution dramatically changed who was setting prices at the open and close. A pattern small enough to be missed by manual traders is well within the noticing-and-trading capacity of an algorithm scanning historical day-of-week regularities. Once a small edge can be systematically extracted at low cost, it does not survive long.

**Faster news cycles.** The bad-news Monday hypothesis depends on companies preferring to drop bad news after Friday close, where it sits unprocessed for two days. With 24-hour news cycles, after-hours trading, and pre-market futures markets that respond to weekend events, the sheltered window has narrowed. Bad news released Friday now starts trading in futures Sunday evening, blunting any Monday-specific repricing.

**Settlement and structural changes.** The shift from T+5 to T+3 to T+2 settlement and other structural reforms in U.S. markets weakened the Friday-buying mechanism that may have contributed to the original asymmetry.

It is also worth being honest about a fourth possibility, which Connolly raised at the time: maybe the original effect was less robust than the published t-statistics suggested, and what we have witnessed is partly genuine arbitrage and partly the regression of an overstated initial estimate.

## What modern data actually shows

For 2010 to the present, standard tests on S&P 500 daily returns produce non-significant day-of-week coefficients in most specifications. Mean Monday returns run slightly positive in some windows and slightly negative in others, but the spread across days of the week sits inside the noise band of daily volatility. The Monday-Friday gap that anchored French's 1980 paper is not in the modern data in any form you could trade.

This is not a U.S.-only story. Day-of-week effects have been documented and partially decayed in many other developed markets. Some emerging markets retain larger and more variable day-of-week patterns, consistent with the arbitrage hypothesis: where institutional capital is thinner and trading frictions are higher, anomalies can persist longer. As those markets mature, the patterns tend to weaken.

<div class="article-tw-callout"><strong>Test it before you trust it.</strong> This is exactly the check TradeWave is built for. Set the lookback to the recent decade instead of the full history, and the Monday pattern that anchored a famous paper simply does not show up at an actionable hit-rate. Run the same window on the pattern you actually care about. If an effect only survives when you include the 1980s, you have found a museum piece, not an edge - and the auditable record shows you why.</div>

## The lesson

Calendar anomalies are not eternal. The day-of-week story is the cleanest historical example of an anomaly that satisfied every reasonable test for being real (multiple independent samples, consistent direction, plausible mechanism, decades of supporting data) and then went away once enough capital paid attention to it. McLean and Pontiff (2016), in their well-known study Does Academic Research Destroy Stock Return Predictability?, show that this is not a one-off: predictive patterns systematically weaken after publication, by roughly a third on average and more in highly liquid markets.

This has two practical implications.

The first is methodological humility about any current anomaly. If you are looking at a pattern in 2026 data that holds back to 2010, you should ask whether it has the durability of a 30-year regularity or whether it is closer to a 16-year regularity that may be on the decay curve. The Monday effect was robust for thirty years before it disappeared in fifteen. Anything you find now should be treated with the assumption that, if it works, smart capital is already trading it.

The second is about how to read the literature. A paper from 1980 documenting a regularity in 1953-1977 data is not a recommendation for 2026 trading. It is a historical observation. The right way to read French (1980) is as a window into how a pattern can exist, why it might have existed, and what eventually happened to it. The same paper read as a trading setup would have lost you money for the past two decades.

## Practical takeaway

Do not trade calendar effects without testing whether they still work in the most recent data. Day-of-week is the textbook case of an anomaly that does not, but the broader principle generalizes. Use the recent decade as your validation set. If a pattern only shows up in pre-2000 data, it is a museum piece, not a strategy.

When you do find a current pattern that survives recent-data testing, build into your sizing the assumption that it is on a decay curve. Markets get smarter. The half-life of a published anomaly in liquid equity markets is shorter than most retail commentary admits. Treat any single calendar pattern as a small input among many, and design your portfolio to survive the day a regularity you depend on quietly stops working.

## References

- French, K. R. (1980). Stock Returns and the Weekend Effect. Journal of Financial Economics 8(1), 55-69.
- Lakonishok, J. and Smidt, S. (1988). Are Seasonal Anomalies Real? A Ninety-Year Perspective. Review of Financial Studies 1(4), 403-425.
- Connolly, R. A. (1989). An Examination of the Robustness of the Weekend Effect. Journal of Financial and Quantitative Analysis 24(2), 133-169.
- Mehdian, S. and Perry, M. J. (2001). The Reversal of the Monday Effect: New Evidence from US Equity Markets. Journal of Business Finance and Accounting 28(7-8).
- Sullivan, R., Timmermann, A. and White, H. (2001). Dangers of Data Mining: The Case of Calendar Effects in Stock Returns. Journal of Finance 56(5).
- Olson, D., Mossman, C. and Chou, N.-T. (2015). The Evolution of the Weekend Effect in US Markets. Quarterly Review of Economics and Finance 58.
- McLean, R. D. and Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? Journal of Finance 71(1), 5-32.
