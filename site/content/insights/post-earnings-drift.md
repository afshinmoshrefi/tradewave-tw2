---
title: "Post-Earnings Announcement Drift: One of Finance's Most Stubborn Anomalies"
slug: post-earnings-drift
summary: "Stocks that beat earnings keep rising for weeks after the announcement; stocks that miss keep falling. The pattern was first documented in 1968. It has resisted being arbitraged away for over half a century. Here's why."
date: 2026-05-08
author: TradeWave Research
reading_minutes: 9
tags: ["anomaly", "earnings", "academic", "behavioral"]
featured: false
related: ["machine-learning-in-finance", "backtesting-pitfalls", "seasonality-momentum"]
---

In an efficient market, news hits prices instantly. A company reports earnings, the market digests the surprise, the stock jumps or drops, and trading moves on. That is the textbook story, and it is wrong.

The data says the adjustment leaks out for weeks. Stocks that beat expectations keep drifting higher for roughly sixty trading days after the announcement. Stocks that miss keep drifting lower over the same window. The drift is large enough to be economically meaningful, predictable enough to trade, and stubborn enough that it has survived more than fifty years of academic scrutiny without being arbitraged away. It is one of the most reliable repeating patterns in equities, and almost nobody who reads about it can capture it cleanly. This article explains both halves of that sentence.

Below: where the anomaly came from, why the efficient-market hypothesis says it should not exist, why it does anyway, and what actually stops you from trading it.

## Where the puzzle starts: Ball and Brown, 1968

The original observation is owed to Ray Ball and Philip Brown, in a paper titled "An Empirical Evaluation of Accounting Income Numbers" published in the Journal of Accounting Research in 1968. Their core finding was straightforward: when companies announce earnings that beat or miss expectations, the stock price moves on the announcement, but it does not move all the way. Some of the adjustment continues afterward, over periods of weeks.

This was a puzzle for the efficient-market view, but it took time to register. Foster, Olsen and Shevlin replicated the result in 1984 in The Accounting Review, using a larger sample and cleaner methodology. Their findings reinforced the original Ball-Brown observation and added precision: the drift was strongest for stocks at the extreme tails of the earnings-surprise distribution.

What both papers needed was a clean way to measure surprise. The convention that emerged was Standardized Unexpected Earnings, or SUE: actual earnings minus what analysts expected, divided by how noisy those forecasts had recently been. Dividing by the noise matters - a one-cent beat is trivial for a steady utility and enormous for a company whose estimates swing wildly. SUE turns a raw surprise into a score you can rank across thousands of stocks.

## The canonical study: Bernard and Thomas, 1989

The paper that established post-earnings announcement drift as a major anomaly was Victor Bernard and Jacob Thomas's 1989 piece in the Journal of Accounting and Economics, "Post-Earnings Announcement Drift: Delayed Price Response or Risk Premium?" It is still the most cited treatment of the topic.

Bernard and Thomas sorted stocks into ten deciles by SUE every quarter and tracked their cumulative abnormal returns over the following sixty trading days. The pattern they found is the one that has been replicated dozens of times since:

<figure><img src="/insights/charts/pead-drift.svg" alt="Post-earnings announcement drift"><figcaption>Stylized cumulative abnormal return after earnings surprise. Top decile (positive surprise) drifts higher for ~60 days; bottom decile drifts lower; control stays flat. After Bernard and Thomas (1989).</figcaption></figure>

The top decile of positive earnings surprises outperformed the bottom decile by approximately 6 to 8 percent over the sixty trading days following the announcement. This was after controlling for size, beta, and industry. The drift was largest in the first two weeks but continued through roughly day 60.

The Bernard-Thomas paper did one more thing that gave it lasting weight. It carefully ruled out risk-based explanations. The drift was not concentrated in high-beta stocks, was not explained by size or other known risk factors of the time, and produced consistently positive returns rather than the sporadic payoff pattern of a true risk premium. Bernard and Thomas concluded that the drift represented a delayed price response by investors, not compensation for bearing risk.

## Why this should not exist

Suppose you accept the Bernard-Thomas finding at face value. You now have a strategy that any first-year quant could implement in a weekend:

1. After every earnings announcement, compute the SUE for the reporting company.
2. Buy the top-decile names; short the bottom-decile names.
3. Hold for sixty trading days.
4. Rebalance as new earnings come out.

The data is not exotic. Earnings announcements are public. Analyst consensus estimates are sold by IBES, FactSet, and Bloomberg. The trade has a defined holding period. There is no obvious wrinkle that would prevent a smart investor from running it.

According to the efficient-market hypothesis in its semi-strong form, a strategy this transparent should be arbitraged away the moment it is published. Eugene Fama himself, in his 1998 review article "Market Efficiency, Long-Term Returns, and Behavioral Finance" in the Journal of Financial Economics, surveyed the anomaly literature with a critical eye and accepted PEAD as one of the few that withstood scrutiny. Fama's review is widely seen as the moment the academic community collectively shrugged and accepted the puzzle as real.

## Why it persists

The leading explanations break into three categories.

The first is investor under-reaction. Behavioral models, drawing on the work of Daniel Kahneman and Amos Tversky and on later refinements by Barberis, Shleifer and Vishny, suggest investors anchor on prior beliefs and update slowly when new information arrives. An earnings beat is interpreted as one piece of evidence; investors revise their views partially, and full price adjustment takes time. The slow drift is the market gradually working through the implications of the surprise.

The second is limits to arbitrage. To trade PEAD properly you have to short the bottom-decile names. Short-selling is constrained: borrow costs are high for some names, hard-to-borrow names cannot be shorted at all, and small-cap stocks where the effect is largest are precisely the ones with the worst short-availability. Investors who cannot short cannot fully arbitrage the negative side of the trade, leaving the asymmetric drift in place.

The third is liquidity risk. Ronnie Sadka's 2006 paper "Momentum and Post-Earnings-Announcement Drift Anomalies: The Role of Liquidity Risk" in the Journal of Financial Economics argues that PEAD is partially compensation for bearing liquidity risk. Stocks with high SUE tend to be smaller and less liquid; the spread you earn is in part the price of being willing to trade illiquid names when others will not. Garfinkel and Sokobin (2006) made a related volume-based argument: drift is concentrated in names where trading volume on the announcement was unusually high, suggesting heterogeneous beliefs and slow consensus formation.

These explanations are not mutually exclusive. The honest summary is that PEAD probably reflects a combination of slow human updating, frictions that prevent shorting in the negative tail, and a small genuine liquidity-risk premium. None of these go away because someone publishes a paper.

## Modern updates

The post-2000 literature has refined the picture without overturning it. Chordia, Goyal, Sadka and Shivakumar (2009), in "Liquidity and the Post-Earnings-Announcement Drift" in Financial Analysts Journal, examined whether the effect survives realistic transaction costs. Their finding: the drift is real and tradeable in liquid stocks, but the spread is smaller in mid- and small-caps where the underlying anomaly is strongest. Trading costs eat much of the apparent advantage in the names where the pattern is most powerful.

Hung, Li and Wang (2015) and other transaction-cost-aware studies confirm this. PEAD survives in net-of-cost form for institutional investors with good execution. For retail investors paying retail spreads, the picture is closer to "marginal."

The machine-learning literature has come at this from a different angle. Gu, Kelly and Xiu in their 2020 Review of Financial Studies paper "Empirical Asset Pricing via Machine Learning" trained neural networks on 94 firm characteristics including earnings-related variables. Among the dominant features that emerged were measures related to earnings surprise and post-announcement momentum. The ML models, with no theoretical priors, independently rediscovered PEAD. That is roughly the highest form of independent confirmation a quantitative finding can receive.

## What stops you from trading it

Anyone reading this and thinking they will go open a brokerage account and start ranking SUEs should consider what actually limits this strategy in practice.

The first issue is data. SUE requires consensus analyst estimates. These come from IBES, FactSet, or Refinitiv, and an institutional license costs from low five figures up to seven figures depending on how broadly you want it. Free alternatives like Yahoo Finance consensus estimates exist but are noisy, sometimes stale, and missing for the smaller names where the effect is largest.

The second issue is the holding period. Sixty trading days is roughly three calendar months. Over that span, the stock will see other news flow: macro shocks, sector rotations, idiosyncratic events. The PEAD pattern is a directional bias, not a guarantee. You will see plenty of trades where a positive-surprise stock ends the sixty days lower because the market sold off. Position sizing and risk management have to absorb that.

The third issue is the negative tail. Bottom-decile PEAD names are companies that just missed earnings. They are sometimes companies that just did very badly. Holding short positions in companies that are visibly deteriorating means you will eventually short something on its way to a binary event - a buyout that gaps the stock up, an activist letter, a guidance pre-announcement. The negative side of the trade has more tail risk than the long side, and that asymmetry has to be in the risk model.

The fourth issue is universe selection. The literature is very clear that PEAD is largest in mid-cap names that are followed but not over-followed. Mega-caps absorb earnings news efficiently because they have hundreds of analysts and millions of dollars of trading volume in the first hour. The names where PEAD is strongest are ones where bid-ask spreads, borrow costs, and capacity are all worse than the index.

## The honest takeaway

For most readers, PEAD is more interesting as a lens on market efficiency than as a strategy to deploy directly. It is one of the cleanest examples of a predictable pattern that the efficient-market hypothesis says should not exist, that practitioners have known about for decades, and that survives anyway. The reasons it survives - data costs, slow human updating, asymmetric short-sale constraints, real liquidity risk - are themselves a useful summary of why financial markets are efficient enough to be hard but not efficient enough to be uninteresting.

For long-only investors, the takeaway is small but real. If you are already deciding which stocks in a universe to overweight, recent earnings beats are a defensible tilt. The pattern is roughly orthogonal to value and weakly correlated with momentum, so it adds something. It is not a reason to build a PEAD-only fund.

PEAD is also a clean illustration of how we think about every pattern at TradeWave. A repeating tendency is only worth acting on once you have seen it hold across a long enough lookback, with the hit-rate and the misses visible rather than cherry-picked. That is exactly what the platform does for calendar and election-cycle seasonality: detect the pattern over a window you choose, anywhere from 1 to 99 years, attach an ML score, and keep the record auditable so you can judge the edge for yourself. The drift in this article is a different kind of pattern, but the discipline is the same one - measure the tendency honestly, then decide.

For anyone running quantitative strategies, PEAD is a good test case for the general principle that anomalies surviving fifty years of attention probably have structural reasons for surviving. The question to ask is not "why hasn't this been arbitraged?" but "what specifically prevents arbitrage in this case, and is that constraint binding for me?" The honest answer is usually that someone is bearing a real cost - data, illiquidity, short-borrow, tail risk - that the published return number ignores.

That is the texture of real anomalies. They look free in the paper. They are not free in the trade.
