# TW-TASK-0020: Restore mobile bar chart More controls

- Status: complete
- Executor/session/claim time: Codex /root/mobile_controls; 2026-10-05 10:51 UTC
- Authorization: fix this mobile toolbar regression; verify and activate on Dev only; staging/production excluded

## Goal, Scope and Acceptance

Restore usable mobile bar chart More controls after title removal. On Pixel 5 emulation at 390x844, the More caret opens a second row, Start Date and Days receive touch, and More closes the row. Mobile titles remain hidden and desktop titles remain available. One React build and focused live Dev touch smoke passed.

## Evidence and Investigation

Shared bug record: [TW-BUG-0026](../bugs/TW-BUG-0026.md). Origin/main at claim: `a908aebca998fd9c1654f74d02fb0825afec5066`. A desktop mouse click against smartphone emulation timed out at CDP and does not count as reproduction; genuine touch reproduced the panel state change but showed the canvas intercepting row controls. Fix: scoped z-index: 1.

## Implementation and Handoff

Branch `codex/toolbar-more-mobile-20261005`; local clean current-main carrier worktree `C:\Users\afshin\Documents\TradeWave Main Orchestrator\toolbar-more-mobile-20261005`; remote task worktree `/home/tradewave-worktrees/toolbar-more-mobile-20261005`, based on main `a908aebca998fd9c1654f74d02fb0825afec5066`. Code commit ae0aa6fe695fa241d98ddb6c19dfb0713fb3b627; React build stamp matches it. Live Dev used main.961a8aa0.js / main.682a7363.css, active pointer /home/flask/web-react/build -> releases/build-ae0aa6fe695fa241d98ddb6c19dfb0713fb3b627, previous pointer build-f935057beb4e433010bbe98f8675f5aa5feb226c. Touch opened the second row, the date input received the hit, and More closed it. Screenshot: [dev-mobile-more-open.png](../bugs/evidence/TW-BUG-0026/dev-mobile-more-open.png). The only app edit is `z-index: 1` on `.second-layer-parent` in `SeasonalBarChart.css`. A production npm build completed with the exact CSS rule; it emitted only existing CRA lint and Browserslist warnings. Staging/production excluded. Preserve `/home/flask` unrelated changes.

## History

- 2026-10-05: Authorized Dev-only repair complete: one CSS stacking rule, one successful React build, live mobile touch open/input/close verification. Staging/production excluded.
