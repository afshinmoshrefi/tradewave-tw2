# TW-BUG-0015: Median labels overlap seasonal bars

- Status: in-progress
- Priority: P2
- Confidence: reproduced in owner screenshots (GC, QQQ, SPY)
- Executor/session: Codex smn-chart-labels-20260923
- Claimed: 2026-09-23T15:10:26.538058+00:00
- Authorization: owner requests unreadable chart labels fixed with professional appearance; Dev only.
- SMN branch/worktree: codex/smn-chart-labels-20260923; Windows orchestrator/smn-chart-labels-20260923, from7240b1a.

## Cause and acceptance
chartkit.record_bars right-aligns the median annotation near the final bar, causing its text to extend left into the bar. Fix presentation only: a tidy reserved right-hand gutter inside the frame, aligned with the median line, with rendered text extents proving no collision or clipping. Preserve every engine value, study, bar and financial calculation. Verify supplied GC/QQQ/SPY cases and mobile behavior; repair affected Dev assets with retained article prose/heroes/data. Production unchanged.

## Coordination
Claude lean daily candidate changes reviewer/effort/orchestration/layout checks but does not edit chartkit. Do not merge or override that experimental branch. This task does not remove daily visual checks or change model settings. User questions their value; broader workflow decision remains separate.

## Next
Focused renderer correction and examples, regression verification, exact-source Dev asset repair and shared completion evidence. Prior visual approval missed this defect; do not treat past approvals as proof of absence.
