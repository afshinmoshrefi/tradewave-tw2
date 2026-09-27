# TW-TASK-0012: Chart Toolbar Control Titles

- Status: in-progress
- Confidence: reproduced
- Priority: P3 - improves control discoverability
- First observed / last updated: 2026-09-27 22:35 UTC
- Executor/session/claim time: Codex toolbar_titles / 2026-09-27 22:25 UTC
- Authorization: User requested implementation and routine dev activation; staging and production excluded.

## Goal, Scope and Acceptance

Add visible titles above every control in the bar-chart toolbar, from Add (+) through Help (?). Settings > General has a persisted Show toolbar titles switch, enabled by default. The date and duration controls read exactly "Start date" and "Days hold". Other titles accurately describe their controls. Enabled layout fits the title row; disabled layout is compact. Existing interactions and responsive use remain functional.

## Evidence and Investigation

The toolbar renders in `SeasonalBarChart.js`; Settings > General is in `DesktopLayout.js`. The phone portrait toolbar exposes five additional controls in an expandable second row. `App.js` holds user-scoped local settings through `lsGet`/`lsSet`. Source baseline: origin/main `5aaff50f6caef3597c3f65cfb202831e0d8ed914`.

## Acceptance and Regression Checks

React production build passed on the task source September 27 (existing project lint warnings). Final candidate build and rendered dev browser check pending.

## Implementation and Handoff

Repository: tradewave-tw2. Branch: `codex/toolbar-control-titles-20260927`. Worktree: `/home/tradewave-worktrees/toolbar-control-titles-20260927`. Added a default-on user-scoped setting, titles on every visible toolbar control and mobile second-row control, and matching expanded/compact heights. Code commit and live evidence pending. No migration or configuration change. Rollback: restore previous frontend build pointer; backend unchanged. Next: integrate latest main, activate dev under lock, and verify rendered behavior.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-27 22:25 UTC, Codex: Claimed authorized feature. Next: inspect toolbar and settings, implement and verify.
- 2026-09-27 22:35 UTC, Codex: Implemented source and passed React build; another session currently owns the dev activation lock.
