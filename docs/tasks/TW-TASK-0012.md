# TW-TASK-0012: Chart Toolbar Control Titles

- Status: in-progress
- Confidence: reported
- Priority: P3 - improves control discoverability
- First observed / last updated: 2026-09-27 22:25 UTC
- Executor/session/claim time: Codex toolbar_titles / 2026-09-27 22:25 UTC
- Authorization: User requested implementation and routine dev activation; staging and production excluded.

## Goal, Scope and Acceptance

Add visible titles above every control in the bar-chart toolbar, from Add (+) through Help (?). Settings > General has a persisted Show toolbar titles switch, enabled by default. The date and duration controls read exactly "Start date" and "Days hold". Other titles accurately describe their controls. Enabled layout fits the title row; disabled layout is compact. Existing interactions and responsive use remain functional.

## Evidence and Investigation

Implementation inspection pending. Source baseline: origin/main `5aaff50f6caef3597c3f65cfb202831e0d8ed914`.

## Acceptance and Regression Checks

Focused tests, build, and rendered dev browser check pending.

## Implementation and Handoff

Repository: tradewave-tw2. Branch: `codex/toolbar-control-titles-20260927`. Worktree: `/home/tradewave-worktrees/toolbar-control-titles-20260927`. Code commit, dependencies, risks, and next action pending. No known migration or configuration change.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-27 22:25 UTC, Codex: Claimed authorized feature. Next: inspect toolbar and settings, implement and verify.
