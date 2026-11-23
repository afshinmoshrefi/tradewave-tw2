# TW-TASK-0037 | Explain blank AI scores in the Opportunity Table

Verified on TradeWave dev at 2026-11-23T18:35:38.878565+00:00. Codex claimed this change at 2026-11-23 18:25 UTC on branch `codex/ai-score-table-reasons-20261123` in `/home/tradewave-worktrees/ai-score-table-reasons-20261123`. P2. Afshin authorized the dev table change.

## User-visible behavior

The table prints the reason from the score response for the displayed time window. Adjacent visible AI metric columns share one explanation. Individual columns show the same reason when the user enables a single AI metric. The score panel provides the longer explanation.

## Evidence

On November 23 the dev app resolved 100 sampled rows. Eighty-three had passed their entry date and 17 hit the volatility limit. The old frontend rendered a dash for MAR, UNH, GOOGL and T. After deployment, MAR and UNH displayed “Pattern already started.” GOOGL and T displayed “High volatility (VIX).”

The [rendered dev checks](evidence/TW-TASK-0037-dev-ui.json) used live S&P 500 data through the dev capture account. They covered dark desktop at 1440 px with four AI columns and light phone layout at 390 px with Win% enabled. In both layouts the reason fit its cell, columns aligned with their headings, and clicking GOOGL’s reason selected the row.

## Implementation and handoff

`OpportunityAICell`, `TableBox`, `opportunityAIScores` and `TableBox.css` own the cell, adjacent column groups, reason labels and wrapping. Five focused Jest suites passed all 100 tests, including zero scores, loading, older responses, service and history failures, column ordering, filters and sorting.

The React release script built commit `596be0fbfce138761890235b6290b66af4a43b1c`. Dev serves `main.9d6f94d2.js`. Dev used its existing appserver and scorer. The prior frontend release is `0c67bb840fa152c8de9e427d8a3e801239caf6f0` and can be selected through the standard dev frontend pointer for rollback. The first verification restored that release when the QA account's welcome video covered the table. Dismissing it through “Go to Wave Viewer” allowed the same candidate to pass the interaction on both layouts.

The task branch is `codex/ai-score-table-reasons-20261123`. The source commit reached main through the dev activation lock. This receipt is a documentation follow-up. No migration or service restart was needed. Staging and production are outside this dev delivery.

## Highlight high volatility

In progress, claimed by Codex on the same task branch at 2026-11-23 18:41 UTC. Afshin requested visual emphasis for the VIX message. Verify the visible warning, both themes and row selection on dev.

The affected component, normalizer and AI Scores panel passed 61 tests, including grouped warnings, older VIX responses and other unavailable reasons. The next check is the rendered table on dev.
