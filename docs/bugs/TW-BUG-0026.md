# TW-BUG-0026: Mobile bar chart More controls are covered by the canvas

- Status: in-progress
- Confidence: reproduced in the isolated Dev capture browser
- Priority: P2 - users cannot reach additional bar chart controls on mobile
- First observed / last updated: 2026-10-05 10:51 UTC
- Executor/session/claim time: Codex /root/mobile_controls; 2026-10-05 10:51 UTC
- Authorization: fix this mobile toolbar regression; verify and activate on Dev only; staging/production excluded

## User Impact and Reproduction

On Dev, load SPX for 2026-10-04 / 291 calendar days / PE+2 Years in Pixel 5 emulation at 390x844. Tap the More caret. The caret state changes and the panel DOM becomes flex, but the chart canvas paints above it and receives taps at the expanded controls. Expected: the second row is visible and usable. Actual: control hit tests resolve to CANVAS. A 3px touch move confirms the browser emits touch/click and toggles the panel; this is a stacking/visibility failure, not a missing state change.

## Evidence and Investigation

Related change: [TW-TASK-0012](../tasks/TW-TASK-0012.md), which removed mobile toolbar titles while retaining desktop titles. The internal capture shell ran with a synthetic authenticated test identity and modeled its already-accepted terms state only in the isolated browser cookie; no real account consent changed. A first-run Getting Started video overlay was closed using its UI. Before fix, the More target was the 20px SVG caret at x=223.98, y=42.19, 38.48px high; a 3px touch gesture opened the panel at y=80.67, but its first control hit stack was `CANVAS, DIV`. Confirmed cause: `.second-layer-parent` is absolutely positioned, has no stacking level, and precedes the later chart/canvas in the render tree. `web-react/src/components/SeasonalBarChart.js` toggles panel state correctly. Dev served `main.2177ddb6.js` before activation.

## Acceptance and Regression Checks

Tap More with a 3px mobile touch movement; verify the row is visible above the canvas, the Start Date and Days controls receive the touch hit, and a second More touch closes it. Confirm mobile titles remain absent. The pre-fix touch reproduced the canvas occlusion; isolated `npm run build` passed with existing lint/Browserslist warnings. Post-fix live verification pending. Desktop title behavior is preserved by the CSS-only scope.

## Implementation and Handoff

Repository `tradewave-tw2`; branch `codex/toolbar-more-mobile-20261005`; remote task worktree `/home/tradewave-worktrees/toolbar-more-mobile-20261005`, based on main `951821837d8807e96fe4243c4679c43767666617` and claim commit `a908aebc`. Code commit, integration SHA, activation pointer, rollback pointer and final evidence: pending. Changed file is `web-react/src/components/styles/SeasonalBarChart.css`; added only `z-index: 1` to `.second-layer-parent` so expanded controls paint above the chart. The isolated production build completed from this exact source tree before commit; task build artifacts stay outside the source commit. Preserve unrelated dirty `/home/flask`. Next: review/commit, integrate, activate the exact artifact, verify touch open/targets/close on Dev, then update status and receipts.

## Environment Verification

Dev: deployed/unverified; exact source/artifact pending. Staging: not checked. Production: not checked.

## History

- 2026-10-05: Claimed authorized Dev-only repair. Isolated touch reproduced controls hidden behind the canvas; the CSS stacking fix is implemented and built. Live Dev verification is pending.
