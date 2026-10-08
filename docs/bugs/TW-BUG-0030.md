# TW-BUG-0030: Desktop Reminder button sits low in titled toolbar

- Status: in progress on dev
- Priority: P3
- Executor/session: Codex `/root/toolbar_titles`, 2026-10-08 UTC
- Branch/worktree: `codex/reminder-button-align-20261008` at `/home/tradewave-worktrees/reminder-button-align-20261008`, based on `b2da55c5353405cf99d8b0effcc1e898b84c0613`.
- Authorization: Afshin requested aligning the desktop Reminder pill/bell with adjacent controls. Routine dev-only activation authorized; staging and production excluded.
- Acceptance: in desktop title mode, full and icon-only Reminder buttons are aligned without changing their internal bell/text spacing or pulse. Title-off and mobile layouts, interactions and tooltip routing remain unchanged.
- Next: apply the smallest scoped CSS adjustment, build, verify actual live geometry and interaction on dev.

