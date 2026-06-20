---
title: "The Halloween Effect: What 200 Years of Data Says About 'Sell in May'"
slug: "halloween-effect"
summary: "Bouman and Jacobsen's 2002 study found Nov-Apr returns dramatically higher than May-Oct across 37 markets. Two decades of follow-up research has tested the claim against every reasonable counter-explanation. Here's what holds up - and what to actually do with it."
date: "2026-05-08"
author: "TradeWave Research"
reading_minutes: 9
tags: ["seasonality", "halloween-effect", "academic", "methodology"]
featured: true
related: ["january-effect", "reading-patterns-without-fooling-yourself", "presidential-cycle"]
---

"Sell in May and go away" sounds too neat to be true. London brokers have recited it for the better part of two centuries, and that alone should make you suspicious: folk wisdom in finance usually falls apart the moment someone tests it properly. The Halloween effect mostly hasn't. Twenty-plus years after Sven Bouman and Ben Jacobsen put real numbers behind the saying, the gap between winter-half and summer-half stock returns keeps turning up in fresh data, and researchers still cannot fully agree on why.

This article walks through what holds up: the 2002 finding, the sharpest critiques, the out-of-sample replications, and the competing explanations. Then it gets to the part most readers actually want, which is what to do with it.

The short version: the effect is real, small, and persistent, and the worst thing you can do with it is treat it as a binary rule that yanks you to cash every spring. Used well, it is a small tilt inside a strategy that already has reasons to exist.

## The original finding: 36 of 37 markets

Bouman and Jacobsen's paper, published in the *American Economic Review* in 2002, studied 37 country indices drawn from MSCI data, with sample windows reaching back to 1970 for most markets and 1973 for several. They asked a simple question: if you split each year into a November-through-April half and a May-through-October half, how do the average returns compare?

The answer was striking. In 36 of the 37 countries studied, average Nov-Apr returns were higher than average May-Oct returns. The gap was not subtle in most markets. A strategy of holding the equity index from November through April, then sitting in T-bills from May through October, beat buy-and-hold on a Sharpe-ratio basis in roughly two-thirds of the countries (Bouman and Jacobsen 2002).

To their credit, the authors did not just report the result and walk away. They worked through the obvious alternatives one by one. Sector composition? The effect held across sectors. The January effect in disguise? It survived removing January. Cross-correlation among markets that all happened to do well in winter? Partially, but too small to carry the result. Data mining? They argued no, since the saying predated the data they tested.

What they could not nail down was the mechanism. They suggested vacation patterns and seasonal risk aversion as the most plausible candidates, but they acknowledged the explanation was open.

## The first serious critique: outliers and fragility

The most cited rebuttal came quickly. Edwin Maberly and Raylene Pierce, writing in *Econ Journal Watch* (2004) and elsewhere, argued the U.S. result was fragile. Specifically, when you control for the October 1987 crash and the August 1998 LTCM-related collapse with dummy variables, the t-statistic on the Halloween effect for U.S. data falls below conventional significance thresholds. Their conclusion was blunt: the U.S. evidence is driven by a small number of extreme observations clustered in May-Oct windows. Without them, the effect more or less disappears.

This is the kind of critique that should make any honest researcher sweat. Two outliers driving a 30-year result is a real concern, and Maberly and Pierce were right to flag it.

But two things cut against its force. First, it applies only to the U.S. Bouman and Jacobsen's headline result was the international one - 36 of 37 markets. Even granting that the U.S. number is outlier-driven, that says nothing about why the pattern shows up almost everywhere else. Second, Russell Witte's 2010 follow-up in the *International Review of Financial Analysis* showed that other outliers cut the other way: adjust for the full set of large monthly moves and the strategy looks much like the unadjusted version. The outlier argument is not as one-sided as it first appeared.

<figure><img src="/insights/charts/halloween-effect-global.svg" alt="Mean returns Nov-Apr vs May-Oct by region"><figcaption>Mean annualized returns by half-year, illustrative composite of values reported in Bouman and Jacobsen (2002), Andrade et al. (2013), Zhang and Jacobsen (2021). Numbers are stylized for clarity; consult the underlying papers for exact figures.</figcaption></figure>

## The out-of-sample test that mattered

The cleanest test of any anomaly is fresh data the original authors could not have selected on. For the Halloween effect, that test arrived in 2013, when Sandro Andrade, Vidhi Chhaochharia, and Michael Fuerst published "Sell in May and Go Away Just Won't Go Away" in the *Financial Analysts Journal*. They took the same 37 countries Bouman and Jacobsen had studied and looked at out-of-sample data from 1998 through 2012 - a period that included the dot-com crash, the 2008 financial crisis, and the early eurozone troubles, none of which Bouman and Jacobsen could have known about when they wrote.

The pattern held. Average Nov-Apr returns exceeded May-Oct returns by approximately 10 percentage points (annualized) across the country sample in the out-of-sample window. For U.S. stocks specifically, the timing strategy generated about 6.9% annualized outperformance versus buy-and-hold over 1998-2012 (Andrade, Chhaochharia and Fuerst 2013). If anything, the effect appeared more pervasive in the post-publication data than in the original.

A separate update by Zhang and Jacobsen (2021) extended the analysis through 2017 and broadened to 65 countries, again finding the pattern intact in the large majority of them.

This is the evidence that convinced most academics the effect is a real statistical regularity, not a data-mining artifact. You can argue about the mechanism. You can argue about whether it survives costs. You cannot easily argue the pattern is not in the data.

## The mechanism debate: weather, vacations, or risk

If the effect is real, why is it there? The literature has roughly three candidate explanations, none of which has decisive evidence.

The **weather/SAD hypothesis**, formalized by Mark Kamstra, Lisa Kramer, and Maurice Levi (2003) in the *American Economic Review*, links seasonal affective disorder to risk aversion. The argument: shorter daylight hours in fall and winter make investors more risk-averse, depressing prices in autumn; risk aversion eases as days lengthen, and prices recover into spring. The hypothesis has the virtue of being measurable - you can test it against latitude, and the original paper found a latitude effect roughly consistent with it. It has the drawback that the data is noisy and the cross-sectional patterns are not as clean as the headline result suggests.

The **vacation hypothesis** comes from Harrison Hong and Jialin Yu's 2009 paper "Gone Fishin'" in the *Journal of Financial Markets*. They documented that trading turnover is significantly lower in summer in most markets, and that mean returns are also lower in summer in countries where the turnover decline is sharpest. The mechanism is roughly: when sophisticated traders are at the beach, market depth is thinner, risk premia rise, and returns get pushed forward into the autumn restart. This is correlation rather than causation, and the magnitude is not large enough to fully account for the Bouman-Jacobsen gap, but it is the most behaviorally clean of the three candidates.

The **risk premium** explanation, advanced by Ben Jacobsen and Nuttawat Visaltanachoti (2009) and others, says simply that risk is genuinely higher in winter (whether through cash-flow seasonality, agricultural cycles, or insurance flows) and that the Nov-Apr return is just compensation for that risk. The problem is that volatility is typically higher in fall, not winter, which cuts against the cleanest version of this story.

None of the three is definitive, and they are not mutually exclusive. The honest summary: a 5 to 10 percentage point annual gap is too large for any single mechanism the literature has offered, and the question stays open.

## What about the U.S. specifically

For U.S. readers wondering about the actual numbers: studies looking at the S&P 500 from roughly 1970 through the late 2010s consistently show mean Nov-Apr returns in the neighborhood of 7% (annualized for the half-year) versus 1-2% for May-Oct. The exact numbers depend on the sample window, the index used, and whether dividends are reinvested, which is why these are typically reported as ranges rather than precise point estimates. The point is that the gap is large in headline terms, but the standard deviation around either half-year mean is also large, which is why year-by-year tests rarely produce statistically significant results even when the long-run averages diverge sharply.

This is the crucial caveat. The Halloween effect is a statement about averages over decades, not about any single year. In any given year, May-Oct may well outperform Nov-Apr. In the 1970-2017 window, roughly 35 to 40% of individual years showed May-Oct beating Nov-Apr in U.S. data. A strategy built on the assumption that the next single year will follow the average is a strategy with a meaningful chance of looking foolish twelve months later.

## What to do with this

Here is the part where most popular write-ups of the Halloween effect go wrong. They take a real but small statistical regularity and turn it into "go to cash on May 1, buy back on November 1." That advice ignores three things that any honest reading of the literature has to grapple with.

First, transaction costs and taxes. Andrade and his coauthors flagged this themselves. Even at modern retail spreads, two annual round trips on a meaningful portfolio chip away at the spread between half-years, and in a taxable account you are converting long-term capital gains potential into short-term losses on a regular schedule. The 6.9% annualized "outperformance" the literature cites is a gross figure.

Second, opportunity cost. Sitting in T-bills for half the year means missing whatever the equity premium produces in May-Oct on average. That premium is positive even in the "weak" half. The Halloween strategy outperforms because the winter half is much stronger, not because the summer half is bad. Treating summer as "bad" misreads the result.

Third, the multiple-testing problem. The Halloween effect is one of dozens of calendar anomalies in the literature, and at least some of those would show up by chance even if no real seasonality existed. The Halloween effect happens to survive the more rigorous corrections, but its effect size after those corrections is smaller than the headline numbers suggest.

The reasonable use of the Halloween effect, in our view, is as a small tilt rather than a binary rule. If your strategy already has a mechanical reason to rebalance, lean modestly toward higher equity weight in the Nov-Apr window. If you run a tactical overlay on a buy-and-hold core, a modest seasonal tilt is one of several indicators you might combine with valuation, momentum, and macro factors. What you should not do is convert a 5 percentage point statistical regularity into a 100% on/off allocation.

The other thing worth doing is testing it on your own universe. The aggregate result holds across countries and decades. That tells you nothing about whether it holds for the tickers you actually trade, on your timeframe, after your costs. Anomalies that look beautiful in aggregate often look much messier on a single symbol, and the only way to know is to run the data yourself.

<div class="article-tw-callout"><strong>Test it yourself.</strong> TradeWave detects repeating seasonal patterns on any symbol with at least 5 years of history, over a lookback you set anywhere from 1 to 99 years, on a plain calendar or an election-cycle basis - so you can see whether the Nov-Apr tilt actually shows up for your tickers, with a hit-rate and an auditable record rather than a headline average. Other tools work too; the point is to validate on your own universe before you commit capital.</div>

## What to remember

The Halloween effect is not folk wisdom dressed up as a paper. It is a statistical regularity that has survived a serious critique (Maberly and Pierce 2003), an out-of-sample replication on data the original authors had no access to (Andrade, Chhaochharia and Fuerst 2013), and an even longer follow-up that broadened the country set (Zhang and Jacobsen 2021). The mechanism is unsettled. The size is small but real. The right way to use it is as a small input to a larger process, not as a market-timing trigger.

The most useful frame is this: the Halloween effect is one of the cleanest examples in the seasonality literature of an anomaly that should have been arbitraged away and largely has not been. That tells you something about the limits of arbitrage in retail markets, and it tells you that "everyone knows about this" is not the same as "everyone trades on this." Most people who know about the effect are not positioned to act on it consistently after costs. The gap has narrowed over the decades, but it is still there, and there is no clean reason to expect it to vanish in the next ten years.
