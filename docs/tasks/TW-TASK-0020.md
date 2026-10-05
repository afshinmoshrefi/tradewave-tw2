# TW-TASK-0020: Restore mobile bar chart More controls

- Status: in-progress
- Executor/session/claim time: Codex /root/mobile_controls; 2026-10-05 10:51 UTC
- Authorization: fix this mobile toolbar regression; verify and activate on Dev only; staging/production excluded

## Goal, Scope and Acceptance

Restore usable mobile bar chart More controls after title removal. On Pixel 5 emulation at 390x844, the More caret opens a second row, Start Date and Days receive touch, and More closes the row. Mobile titles remain hidden and desktop titles remain available. Run one React build and focused live Dev touch smoke.

## Evidence and Investigation

Shared bug record: [TW-BUG-0026](../bugs/TW-BUG-0026.md). Origin/main at claim: `951821837d8807e96fe4243c4679c43767666617`. A desktop mouse click against smartphone emulation timed out at CDP and does not count as reproduction; genuine touch verification is pending.

## Implementation and Handoff

Branch `codex/toolbar-more-mobile-20261005`; local clean current-main carrier worktree `C:\Users\afshin\Documents\TradeWave Main Orchestrator\toolbar-more-mobile-20261005`; remote task worktree `/home/tradewave-worktrees/toolbar-more-mobile-20261005`, based on main `951821837d8807e96fe4243c4679c43767666617`. Code/integration commits, build provenance, Dev evidence, active pointer, rollback and final worktree state: pending. The only app edit is `z-index: 1` on `.second-layer-parent` in `SeasonalBarChart.css`. A production npm build completed with the exact CSS rule; it emitted only existing CRA lint and Browserslist warnings. Staging/production excluded. Preserve `/home/flask` unrelated changes.

## History

- 2026-10-05: Claimed authorized Dev-only repair, direct touch reproduction and implementation pending.
