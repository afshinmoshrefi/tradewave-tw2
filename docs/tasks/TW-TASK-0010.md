# TW-TASK-0010: Avg Gain value tooltips

- Status: in-progress
- Confidence: reproduced presentation behavior
- Priority: P3 - clarify two existing values
- First observed / last updated: 2026-09-27 UTC
- Executor/session/claim time: Codex `/root/wave_info_dev`, 2026-09-27 UTC
- Authorization: Afshin requested short tooltips on each Avg Gain value on dev; preserve engine values, layout and existing detailed tooltip when global tips are on. No staging or production.

## Goal, Scope and Acceptance

In Wave Stats, with global tooltips off, hovering the first Avg Gain value shows `Average of winning years`; hovering the second shows `Average of all years`. With global tooltips on, retain the existing detailed row tooltip and avoid competing short tips. Preserve the existing comma-separated numbers and responsive layout.

## Evidence and Investigation

At baseline `b0957627610f5a8de08ad11f4147b63c44689774`, `TradeDetail.js` combines two separate appserver fields (`Avg Profit` and `Avg Profit - All`); `VisualTable.js` disables the row-level Tippy when global tooltips are off. A mixed AAPL study displayed `2.38%, 1.74%`; an all-winning KMB study displayed `4.55%, 4.55%`, each matching the engine.

## Acceptance and Regression Checks

Pending: focused component check and authenticated dev browser hover checks for both tooltip states; verify values stay engine-identical and desktop/mobile layout remains stable. Staging/production not checked.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/avg-gain-tooltips-20260927`; worktree `/home/tradewave-worktrees/avg-gain-tooltips-20260927`. Source and integration SHAs pending. No math, backend, configuration or migrations. Rollback: prior dev frontend pointer. Next: implement the two presentation hints, test, activate and verify on dev.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Claimed authorized UI enhancement from current main; implementation pending.
