# TW-BUG-0018: Wave Info shows SMA 50 in place of Sharpe Ratio

- Status: in-progress
- Confidence: reproduced from owner screenshot and source mapping
- Priority: P2 - a financial metric is mislabeled in a visible statistics panel
- First observed / last updated: 2026-09-27 UTC
- Executor/session/claim time: Codex `wave-info-20260927`, 2026-09-27 UTC
- Authorization: Afshin requested the Wave Info repair and four-row layout on dev. No staging or production writes.

## User Impact and Reproduction

Open a seasonal study and its desktop statistics window. Wave Info shows `SMA 50` in the second row where Sharpe Ratio belongs. Trend Long occupies a second trend row and its label/info icon misalign. Owner's screenshot shows `Percent Profitable 100.0%`, `SMA 50 188.8884`, `Trend Alignment Against (37)`, and `Trend Long 37` with a left arrow. Exact study identity and active dev artifact in the screenshot are unknown.

Expected: Percent Profitable and engine Sharpe Ratio by name, a separately named engine TradeWave Ratio when the existing `showSR2` visibility gate permits it, and one Trend Alignment row with the direction-matched score and prior-reading arrow. Keep labels and info icon aligned.

## Evidence and Investigation

At main `3143e2a`, `web-react/src/components/TradeDetail.js` passes `filter={[12, 15, alignIdx, trendIdx]}` to Wave Info; position 15 resolves to SMA 50 after engine response field order changed. `VisualTable` places the info icon and arrow only on Trend Long/Short and stacks the label/icon vertically. TradeWave supplies Sharpe Ratio and `Sharpe Ratio2` (TradeWave Ratio); no client calculation is needed. The existing `showSR2` flag controls visibility of the latter and must be preserved. Owner screenshot attached in the conversation, September 27.

## Acceptance and Regression Checks

Inspect a real rendered dev study with eligible account: four rows in specified order, second row is engine Sharpe, third is engine TWR, combined alignment has direction-specific score/arrow and aligned info icon. For an ineligible account omit the TWR row. Verify unavailable trend score and short direction without stale/wrong arrows. Compare visible metric strings to one engine response.

## Implementation and Handoff

Branch `codex/wave-info-20260927`; local worktree `TradeWave Main Orchestrator/wave-info-20260927`; remote clean task worktree pending. Source commit, tests, artifact and dev activation pending. No intended engine, migration or configuration change. Previous dev pointers to be recorded before activation. Next action: implement named-row projection and validate browser behavior.

## Environment Verification

Dev: pending. Staging: not deployed by this task. Production: not deployed by this task.

## History

- 2026-09-27: Codex claims owner-authorized dev UI repair and separate TradeWave Ratio row; no calculation or entitlement change.
