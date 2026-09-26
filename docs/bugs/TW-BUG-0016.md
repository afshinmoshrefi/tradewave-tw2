# TW-BUG-0016: SMN plain bars chart omits a genuine flat year

- Status: open
- Confidence: reproduced in the September 25 AAPL capture and traced to the SMN chart path; candidate fix not verified live
- Priority: P2 - a published chart can silently misstate the historical sample and win count
- First observed: 2026-09-25; recorded: 2026-09-26 UTC
- Executor/session/claim time: unassigned for implementation
- Authorization: record and hand off the bug only; no repair, Dev activation or production deployment authorized by this record

## User Impact and Reproduction

For the September 25 AAPL study, TradeWave returns ten completed observations (1986-2022). The 1986 entry and exit adjusted closes are both 0.1182, yielding a genuine 0.0% return, while its intraperiod range is +1.85% / -6.89%. The production plain `bars` image omits 1986 and presents nine years (1990-2022), including a "9 of the past 9" claim. The range charts and engine statistics include all ten years, so the correct cohort claim is 9 of 10. Any article with a genuine completed flat year may be affected. The September 25 Dev edition held AAPL at the existing `make_card` validation gate with reason `Engine full sample differs from the published chart`; five other articles passed and AAPL was not published.

## Evidence and Investigation

- Shared publication history and root-cause investigation: [TW-TASK-0005](../tasks/TW-TASK-0005.md), September 25 AAPL hold and root-cause sections.
- Preserved September 25 capture: `/var/lib/tradewave/smn-daily/2026-09-25` on the SMN server. September 26 private comparison: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-claude`. Inspect their state/receipts and source revisions before replay. These are server-local evidence paths, not repository attachments.
- In the affected SMN renderer, `blog/article_images.py` filters placeholder rows using MFE/MAE, then invokes `chartkit.record_bars` for plain bars without those values. `chartkit._drop_zeroed` treats the completed flat row as a placeholder and removes it. The TradeWave engine values are correct; this defect is in SMN chart rendering.
- A proposed, unmerged SMN fix is on `origin/claude/smn-flat-year-bars` at `0971c287546bf65a756f8d7545936c8b9c04ad3f`. It passes `verified_completed=True` for the plain chart and adds a focused test. Inspect and retest it against current SMN `main`; its existence does not establish Dev or production verification.

## Acceptance and Regression Checks

Render the captured AAPL study with the candidate fix. The plain bars chart must retain 1986 and show ten years, matching range charts, engine statistics and prose; the winning-year claim must be 9 of 10. Keep genuine completed flat years, while excluding unfinished/future zero placeholders. Verify an ordinary non-flat study and the other five September 25 articles are unaffected. Preserve TradeWave-supplied values exactly and keep the `make_card` mismatch hold active. After the renderer passes focused tests and Dev verification, regenerate the affected chart and take a fresh AAPL capture through the normal review gate. Tests and live checks for this bug have not been run by this documentation session.

## Implementation and Handoff

Implement in SMN, not the TradeWave engine. Start by comparing the candidate commit above with current SMN main and checking its test evidence. Claim the repair in this record before code edits, with executor/session, UTC time, branch/worktree and next action. Follow normal SMN Dev integration and verification. Production requires separate authorization and the production deployment procedure; do not treat the candidate branch as deployed. No config, migration or build requirement has been established here.

## Environment Verification

- Dev: AAPL was held by the September 25 review gate; repaired behavior not verified.
- Staging: no SMN staging environment established.
- Production: affected plain bars chart observed; fix not deployed or verified.

## History

- 2026-09-26: Codex documentation session created this canonical bug record from the preserved September 25 investigation. Implementation remains unclaimed.
