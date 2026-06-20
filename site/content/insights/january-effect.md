---
title: "The January Effect: Why Small Caps Outperformed in January, and Whether It Still Holds"
slug: "january-effect"
summary: "Rozeff and Kinney's 1976 finding that small-cap stocks earn outsized January returns triggered 50 years of work. The mechanism (tax-loss harvesting) is well understood. The interesting question now is whether the anomaly survived its own discovery."
date: "2026-05-08"
author: "TradeWave Research"
reading_minutes: 8
tags: ["seasonality", "january-effect", "small-cap", "academic"]
featured: false
related: ["halloween-effect", "post-earnings-drift", "reading-patterns-without-fooling-yourself"]
---

Most market anomalies are a mystery wrapped in an argument: people agree the pattern exists but fight for decades about why. The January effect is the rare exception. We know exactly why it happened, and we have known almost since the day it was documented. The driver is tax-loss harvesting: people dump their losers in December to book the tax write-off, beaten-up small stocks get pushed below fair value, and a rebound in early January cleans up the mess. The story is so clean that "obvious" is usually the right word.

So the interesting question was never whether the effect was real or why. It was something stranger: what happens to a pattern once everyone knows about it?

The classic argument from McLean and Pontiff (2016) is that academic publication should compress anomalies: once they are known, smart money trades them away. The January effect is the perfect test case. It was identified in 1976. It got fifty years of follow-up. So what happened to it?

The answer is partial decay, not full elimination. The effect has clearly weakened in U.S. large-caps. It persists in microcaps. And the reason it has not vanished entirely tells you something interesting about the limits of arbitrage when the underlying cause is a real economic constraint rather than a behavioral mistake.

## The original finding: 3.48% versus 0.42%

Michael Rozeff and William Kinney's 1976 paper in the *Journal of Financial Economics* was the cleanest possible test of the saying that "January is different." They took the equal-weighted NYSE index from 1904 through 1974 and just compared January monthly returns to the average of all other months. The numbers were stark. January's mean monthly return was 3.48%. The average across the other eleven months was 0.42% (Rozeff and Kinney 1976).

That is roughly an 8x ratio between January and the typical month. The pattern was statistically significant in every sub-period the authors tested, with the single exception of 1929-1940, when the entire decade was dominated by Depression-era volatility that overwhelmed any seasonal pattern.

A few things to note about the methodology. They used the equal-weighted index, which gives equal weight to small and large stocks alike. This matters because, as later work showed, the effect is concentrated in small caps. On a value-weighted index (where Apple counts more than a $300 million microcap), the January gap is real but much smaller. Rozeff and Kinney did not yet know they were measuring a small-cap phenomenon, but the equal-weighting choice meant they captured it cleanly.

## Keim's refinement: it's a small-cap effect, and it happens fast

Donald Keim's 1983 paper in the same journal sharpened the picture in two important ways. First, he showed that nearly half of the entire annual small-firm size premium - the well-documented tendency of small stocks to outperform large stocks over time - happened in January. Not 1/12 of it, which is what you would expect if size returns were spread evenly. Half of it, in one month (Keim 1983).

Second, he showed that more than half of the January excess return itself was concentrated in the first five trading days of the month. The first trading day of January was particularly extreme. Whatever was driving the effect, it was not gradual; it was a sharp price snap-back early in the month, with the rest of January looking more like a normal month.

This second finding matters a lot for the mechanism story. A pattern that concentrates in days 1-5 of the new tax year is suspiciously consistent with year-end tax selling depressing prices in late December, followed by an immediate rebound when the tax-driven selling pressure stops. It is harder to square with explanations like "investor mood improves in January" or "fund managers reposition for the year ahead," which would predict a more diffuse pattern.

<figure><img src="/insights/charts/january-effect-decay.svg" alt="January effect by decade"><figcaption>Small-cap January excess return (vs large cap) by decade. Composite of values from Rozeff and Kinney (1976), Keim (1983), Haug and Hirschey (2006), and post-2010 updates. The effect has clearly weakened post-2000 but not disappeared.</figcaption></figure>

## The mechanism: tax-loss harvesting (and a side dish of window-dressing)

The dominant explanation, supported by the timing pattern Keim documented and by direct studies of trading behavior, is tax-loss harvesting. The story works like this. Toward the end of December, investors holding stocks at unrealized losses have a tax incentive to sell, because realized capital losses can offset realized gains and (up to limits) ordinary income. Stocks that have done badly during the year therefore get extra selling pressure in late December. Their prices end the year depressed below where pure fundamental value would put them.

When the new tax year begins, the selling pressure stops. The stocks rebound to their pre-distortion prices, generating the early-January excess return. Because losers are concentrated in small caps (small caps are more volatile and more likely to have ended the year sharply down), the effect is concentrated there.

A secondary mechanism is institutional **window-dressing**. Mutual funds and other reporting institutions don't want to show beaten-up small-cap losers in their year-end portfolios. They sell those positions in December to clean up the holdings statement, then rebuild positions in January. This adds to the December selling pressure on small caps and reinforces the January rebound. The window-dressing channel is harder to pin down empirically because the trades are not driven by tax law in the same direct way, but multiple studies have found supporting evidence.

There are alternative explanations - liquidity rebalancing, year-end portfolio reconstitution by index funds, behavioral mood effects - but tax-loss harvesting is the dominant one in the literature, and it has the cleanest empirical fingerprint.

## The decline: post-1980s, especially post-2000s

If the cause is tax-loss harvesting, the natural prediction is that the effect should weaken after the 1986 Tax Reform Act, which changed how losses could be used. The empirical record is more nuanced. Mark Haug and Mark Hirschey's 2006 paper in the *Financial Analysts Journal*, looking at value-weighted returns back to 1802 and equal-weighted returns from 1927, found that the small-cap January effect persisted across the entire two-century sample, including after 1986 (Haug and Hirschey 2006). They argued this was awkward for the pure tax-loss explanation, since the act was specifically designed to alter the tax treatment of losses.

But other studies pointed in the opposite direction. Saeyoung Easterday, Pradyot Sen, and Jens Stephan (2009) documented a meaningful decline in the small-firm January effect after 1990 and especially after 2000. Mehdian and Perry (2002) and Marquering, Nisser, and Valla (2006) reached similar conclusions on the U.S. and international evidence respectively. By the mid-2010s, the consensus had shifted: the January effect in U.S. large-caps was largely gone, and even in small-caps it was much smaller than the 3-5 percentage point gaps documented in the 1970s and 1980s.

Post-2000 large-cap January excess returns have typically run at less than 1 percentage point and frequently fail standard significance tests. The headline-grabbing version of the effect is no longer there.

## Why didn't it disappear entirely?

Here is the part that, in our view, has been underappreciated in the popular discussion. McLean and Pontiff (2016) showed that the average anomaly's risk-adjusted return falls by about 58% after publication. The January effect, looked at coldly, has decayed by roughly that much in U.S. large-caps. So far, so consistent with "publication kills anomalies."

But it has not disappeared. Why?

The answer is that tax-loss harvesting is a real economic constraint. It is not a behavioral mistake that an arbitrageur can simply trade against. The selling pressure in late December comes from people who have a genuine tax reason to sell - the tax savings are real, often larger than the small expected price impact, and timing the sales for late December is required by the calendar. You cannot arbitrage away a regulatory feature of the tax code by pointing out that it exists.

What arbitrageurs can do is provide liquidity into the December selling and capture some of the spread. They have done this, which is why the gap has narrowed. But they cannot eliminate the underlying flow, because the flow is structural. The tax loss harvester's behavior is utility-maximizing given the tax code, not irrational. Without a tax code change that removes the year-end deadline (which 1986 did not fully accomplish), there will always be some residual seasonal pattern.

This is a useful general lesson. Anomalies driven by **mistakes** tend to compress quickly after they are documented. Anomalies driven by **structural constraints** - tax rules, regulatory deadlines, mandate-driven flows, index reconstitution - compress more slowly and often have a floor.

## Is it tradable today?

Mostly no, for retail investors, and partially yes, for sophisticated ones with the right cost structure.

The reasons it is hard to trade today:

- **Bid-ask spreads on micro-caps**: most of the residual effect is in genuinely small stocks where spreads can be 1-3% round trip. That eats most of the expected edge.
- **Capacity**: even if you found a clean micro-cap January portfolio, you cannot deploy size into stocks with $50 million market caps without moving prices yourself.
- **Tax efficiency**: ironically, trading the January effect generates short-term capital gains, which are taxed at higher rates than long-term gains. The net-of-tax edge is even smaller than the gross-of-cost edge.
- **Concentration risk**: a portfolio of beaten-up small caps in late December is a portfolio of stocks selected for having done badly. They are doing badly for reasons. Some of those reasons persist into the next year.

The reasons it is still useful as an overlay:

- If you already hold small-cap exposure for other reasons, **rebalancing into the new year**, rather than mid-month, captures a small but real edge.
- If you run a small-cap-tilted portfolio, **harvesting your own losses in December** is tax-efficient and aligns with the structural flow rather than fighting it.
- Year-end **flow-driven volatility** in small caps is information for short-term traders who can read order book dynamics around December tax deadlines.

What you should not do is build a strategy whose entire thesis is "buy the small-cap losers in late December, sell after the first week of January." That trade has been picked over for fifty years. The residual edge is unlikely to survive your specific costs.

<div class="article-tw-callout"><strong>Test it yourself.</strong> The whole point of a structural anomaly is that you can check whether it still shows up in your own data. TradeWave's Wave Viewer (/app/) lets you run any symbol over a lookback you choose - anywhere from 1 to 99 years - and watch how a January tilt holds up decade by decade, with an ML score and an auditable record of every year that went into it. Other tools work too; the discipline is the same: verify before you commit capital.</div>

## Practical takeaway

The January effect is a real anomaly that has been understood for fifty years and partially arbitraged for forty. The remaining edge is small, concentrated in microcaps, and rarely worth pursuing as a standalone strategy. The useful applications are subtler: timing rebalances of existing small-cap allocations, tax-loss harvesting your own portfolio in December, and being aware that small-cap return dynamics in early January are systematically different from later in the year.

More broadly, the January effect is a case study in how anomalies decay. The portion of the effect that came from behavioral noise (mispricing without an underlying constraint) compressed fast once arbitrageurs woke up to it. The portion that came from structural tax-driven flows compressed slowly and persists at a reduced level. When you encounter a new "anomaly" in the literature, it is worth asking which of those two buckets it falls into. The first kind is gone within five to ten years of publication. The second kind has a floor, and the floor is set by whatever real-world constraint generates the flow in the first place.
