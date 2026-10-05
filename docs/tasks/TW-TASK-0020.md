# TW-TASK-0020: Restore mobile bar chart More controls

- Status: in-progress
- Executor/session/claim time: Codex /root/mobile_controls; 2026-10-05 10:51 UTC
- Authorization: fix this mobile toolbar regression; verify and activate on Dev only; staging/production excluded

## Goal, Scope and Acceptance

Restore the mobile bar chart More triangle interaction after mobile toolbar title removal. Tap opens the extra control row; its controls remain usable; tap closes it. Mobile titles remain hidden and desktop titles remain available. Run one React build and focused live Dev touch smoke.

## Evidence and Investigation

Shared bug record: [TW-BUG-0026](../bugs/TW-BUG-0026.md). Origin/main at claim: `951821837d8807e96fe4243c4679c43767666617`. A desktop mouse click against smartphone emulation timed out at CDP and does not count as reproduction; genuine touch verification is pending.

## Implementation and Handoff

Branch `codex/toolbar-more-mobile-20261005`; local clean current-main carrier worktree `C:\Users\afshin\Documents\TradeWave Main Orchestrator\toolbar-more-mobile-20261005`; remote task worktree pending at `/home/tradewave-worktrees/toolbar-more-mobile-20261005`. Code commit, integration commit, build provenance, Dev evidence, active pointer, rollback and final worktree state: pending. Staging/production excluded. Preserve `/home/flask` unrelated changes.

## History

- 2026-10-05: Claimed authorized Dev-only repair, direct touch reproduction and implementation pending.
