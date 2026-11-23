# TW-TASK-0037 | Explain blank AI scores in the Opportunity Table

In progress on TradeWave dev. Codex claimed this change at 2026-11-23 18:25 UTC on branch `codex/ai-score-table-reasons-20261123` in `/home/tradewave-worktrees/ai-score-table-reasons-20261123`. P2. Reproduced on the November 23 dev table.

## Goal and evidence

Afshin requested a visible reason wherever an AI score is unavailable in the dev Opportunity Table. The current cell renders a dash even when the appserver supplies a reason. On November 23 the dev scoring routes resolved 100 stored table rows. MAR and UNH were among the 83 past their entry date. Each of the other 17 returned `vix_blocked`.

## Acceptance and handoff

An eligible viewer can read the reason directly in the table. Verify past-entry and volatility results on live dev, and exercise ordinary scores, zero, loading and optional AI columns. Use the existing scored response and the React release build. The next step is implementing and testing the table presentation. Dev activation and browser verification are pending.
