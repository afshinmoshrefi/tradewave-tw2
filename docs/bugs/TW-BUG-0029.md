# TW-BUG-0029: Wave Viewer direction indicator sits low under its heading

- Status: in progress on dev
- Priority: P3
- Executor/session: Codex `/root/toolbar_titles`, 2026-10-08 UTC
- Branch/worktree: `codex/direction-square-align-20261008` at `/home/tradewave-worktrees/direction-square-align-20261008`, based on `a466494c76b47bf5ca931cb02d95095314a70bc3`.
- Authorization: Afshin requested the bar-chart toolbar's colored direction rectangle be raised to align with adjacent controls, and its visible full/compact heading be `Bias`. Routine dev-only activation authorized; staging/production excluded.
- Acceptance: desktop title-on rectangle aligns vertically with adjacent controls, title reads Bias at full/compact widths, title/tooltip routing and title-off/mobile behavior remain unchanged, and long/short color semantics remain engine-owned.
- Next: measure live geometry, implement minimal offset/title change, focused build and live dev smoke.

