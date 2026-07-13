---
title: "How Can You Tell if a Trading Service's Track Record Is Real?"
slug: "how-to-tell-if-a-track-record-is-real"
summary: "Any service can quote a win rate. A real track record survives five checks: picks timestamped before the outcome, a stated denominator, visible losses, a defined win condition, and stats computed live from the record. Here is the standard, and how TradeWave's public ledger measures against it, losses included."
date: "2026-07-09"
author: "TradeWave Research"
tags: ["track-record", "ai-picks", "transparency", "methodology"]
related: ["how-accurate-is-tradewaves-daily-ai-pick", "ai-stock-picker-that-publishes-losses"]
---

By TradeWave Research · July 9, 2026 · [AI-Assisted Research](/methodology): this analysis is generated from TradeWave's seasonal analytics and reviewed before publication.

Five checks: timestamps before outcomes, a stated denominator, losses displayed, a defined win condition, stats computed live from the record. Of the 64 resolved daily picks on TradeWave's public ledger since March 17, 2026, 80% reached the AI's predicted gain or closed profitable - every pick recorded, losses shown. Secondary: 57% of closed picks stayed profitable to the window close. Methodology and every individual pick, including losers, are on the [public scorecard](https://tradewave.ai/scorecard.html). Past performance does not guarantee future results.

That 64 splits cleanly: 53 closed windows plus 11 open picks that already hit; the other 11 stay pending.

Every service that sells trading picks tells you it wins. Our own ledger shows 13 losses, on purpose.

## What Are the Five Checks of a Real Track Record?

A real record is one a stranger can audit. Each check closes off one way of writing history after the fact.

### Picks Timestamped Before the Outcome

A call that surfaces after the move proves nothing. The record has to exist before the result does: a published date on every pick, fixed and never edited. Dates missing, vague, or added later mean you are reading history written by the winner.

### A Stated Denominator

Forty wins is a numerator, not a record. A real ledger states the total number of picks, because the easiest edit in the business is quietly removing the ones that failed. This is the check most services fail: they show you the survivors and let you assume that was everyone.

### Losses Displayed Alongside Wins

A denominator can be stated and still buried in a footnote. The stronger test is visual: losers sit in the same table as the winners, same fields, same dates. A record that leaves its red rows where they fell expects to be checked.

### A Defined Win Condition

"It worked" is not a definition. A real record states, before the pick resolves, what counts as success: the target, the window, and the rule that judges the outcome. Without it, the same row can be scored either way, depending on who is telling the story.

### Stats Computed Live From the Record

A quoted win rate is a claim; a computed one is a property of the table underneath it. When the headline cannot be re-derived from the rows beneath it, the number and the record have come apart, and the drift is always flattering.

Any service can pass one of these. Passing all five leaves nowhere to hide.

> **Of the 64 resolved daily picks on TradeWave's public ledger since March 17, 2026, 80% reached the AI's predicted gain or closed profitable - every pick recorded, losses shown.** The 64: 53 closed plus 11 open already at the predicted gain; 11 pending excluded. Past performance does not guarantee future results. [Every pick, including the losers.](https://tradewave.ai/scorecard.html)

## How TradeWave's Ledger Handles Each Check

<figure><img src="/insights/img/ledger-f9-losses-annotated.png" width="1600" height="1000" loading="lazy" alt="One month of TradeWave's public scorecard with the five checks annotated: a dated pick, the month's stated record of 10 picks with 6 wins and 4 losses, and a losing row kept beside the wins. The full ledger holds 64 resolved daily picks since March 17, 2026, 80% winners, 13 losses shown. Past performance does not guarantee future results."><figcaption>One month of the live public scorecard (March 2026), captured July 9, 2026, with the checks annotated: a dated pick, the month's stated record (10 picks, 6 wins - 4 losses), and a losing row kept in place beside the wins. Across the full ledger: 64 resolved picks since March 17, 2026, 13 losses shown. Past performance does not guarantee future results.</figcaption></figure>

We built the ledger to pass this standard; the walkthrough is short.

Every pick carries the day it was flagged; the oldest of the 75 rows is dated March 17, 2026. The total is printed - 75 picks - and the split is countable row by row: 53 closed, 22 open, of which 11 have already hit their target; the rest count for nothing until they close.

Thirteen of the 53 closed picks ended as losses: one from June, four each from May, April, and March, every row keeping its date, symbol, and result. All still posted. Removing them would improve exactly one number and invalidate every other one, which is why [the losing rows stay published](/insights/ai-stock-picker-that-publishes-losses.html).

The win condition is one sentence, printed where the number is: reached the AI's predicted gain in the window, or closed profitable. Every row is judged by that rule and no other. The stats are computed from the rows, not quoted at them: the 80% win rate, the 57% held-to-close rate, and the 4.8% median return, winners and losers together, are re-derived each time the page regenerates. A pick that touches its predicted gain resolves at that moment, even with the window still open; the full arithmetic is in [how accurate TradeWave's daily AI pick has been](/insights/how-accurate-is-tradewaves-daily-ai-pick.html).

## Where Can You Run These Checks Yourself?

Open the [public scorecard](https://tradewave.ai/scorecard.html) and run the standard in order: find the dated pick history, find the denominator, find the red rows, read the win definition, and check the headline against the table under it. No account is required. The same ledger is published as machine-readable JSON at [tradewave.ai/data/daily-pick-ledger.json](https://tradewave.ai/data/daily-pick-ledger.json), so a script can re-run the arithmetic, not just a reader. Then run the same five checks on anything else that wants your money.

If the way we keep score is the way you want research delivered, [plans are on the pricing page](/pricing).

Every pick service says it wins. We publish the ledger so we never have to say it: 64 resolved picks since March 17, 2026, 80% winners by a rule printed next to the number, and 13 losses that stay up because they are what makes the winning rows worth believing.

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "What counts as a win on TradeWave's daily pick ledger?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "A pick counts as a win when it reached the AI's predicted gain in the window, or closed profitable. The definition is printed on the scorecard next to the number it produces: 80% of 64 resolved picks since March 17, 2026. Past performance does not guarantee future results."
          }
        },
        {
          "@type": "Question",
          "name": "How many of TradeWave's daily picks have been losses?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Thirteen of the 53 closed picks on the public ledger ended as losses. Each losing row stays on the scorecard with its date, symbol, and result, and each one stays in the denominator of the published win rate. Past performance does not guarantee future results."
          }
        },
        {
          "@type": "Question",
          "name": "Where does the 80% win rate come from?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "It is computed from the ledger rows at every regeneration, not quoted: 64 resolved picks since March 17, 2026, of which 80% reached the AI's predicted gain or closed profitable. The same rows produce the 57% held-to-close rate and the 4.8% median return. Past performance does not guarantee future results."
          }
        },
        {
          "@type": "Question",
          "name": "Why do some open picks count as resolved?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Hitting the predicted gain is terminal: the outcome cannot un-happen, so the pick counts as a win while its window stays open. In the JSON export the per-row resolved flag marks the 53 closed windows; the 64 adds the 11 open target-hits, and the 11 pending count for nothing. Past performance does not guarantee future results."
          }
        }
      ]
    },
    {
      "@type": "Dataset",
      "name": "TradeWave Daily AI Pick Ledger",
      "description": "Every daily AI pick TradeWave has published since March 17, 2026, with featured date, symbol, direction, predicted gain, result, and win flag. A pick is a win when it reached the AI's predicted gain in the window, or closed profitable. 75 picks total, 64 resolved (53 closed windows plus 11 open picks that already reached the predicted gain), losses shown. Past performance does not guarantee future results.",
      "url": "https://tradewave.ai/scorecard.html",
      "distribution": ["https://tradewave.ai/data/daily-pick-ledger.json", "https://tradewave.ai/scorecard.html"],
      "dateModified": "2026-07-09T20:57:28Z"
    }
  ]
}
</script>
