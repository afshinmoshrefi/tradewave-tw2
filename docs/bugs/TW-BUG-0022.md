# TW-BUG-0022: Wave Viewer toolbar controls are too small

- Status: in-progress
- Confidence: reproduced in authenticated dev Chrome
- Priority: P2 - key pattern controls are hard to read and narrow controls can collapse
- First observed / last updated: 2026-09-27 22:47 UTC
- Executor/session/claim time: Codex `/root/wave_info_dev`, 2026-09-27 22:47 UTC
- Authorization: fix toolbar typography and responsive access on dev only. Preserve the separately owned TW-TASK-0012 toolbar-title feature, its default-on preference and existing control behavior. No staging or production.

## User Impact and Reproduction

In the desktop Wave Viewer, load a pattern and inspect the bar-chart toolbar. The date, Days, Years, cycle and Analysis controls are visually tiny; at narrower desktop widths Best Waves can collapse. Expected: readable control text and titles with controls accessible across desktop widths, without changing pattern data or calculations.

## Evidence and Investigation

Authenticated dev Chrome on active toolbar-title source `c2045a082ede9595fceb3783ccef53b228edaf6a` measured root/body font at 12px and key controls at 11.4px despite `0.95em` inline font declarations. The symbol input measured 9.1px at 1280px viewport. No ancestor transform or browser zoom caused the issue. At 1440px, Best Waves was 5.9px wide; at 1280px, 2px. `globalTextSize` is responsive application state, not a persisted user size setting. The title feature is recorded separately in TW-TASK-0012; do not duplicate or replace it.

## Acceptance and Regression Checks

Pending: scoped readable font floor and layout access in ON/OFF title states at desktop widths; visible selected option text; pointer/keyboard control access; mobile unaffected. Focused build and authenticated live dev browser proof pending.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/toolbar-font-dev-20260927`, clean worktree `/home/tradewave-worktrees/toolbar-font-20260927`, based on main `c2045a082ede9595fceb3783ccef53b228edaf6a`. Code/integration SHAs pending. No backend, math, config or migration change expected. Frontend build and pointer swap required; rollback to prior frontend pointer. Next: implement after scoped browser prototype, test and verify on dev.

## Environment Verification

Dev: baseline reproduced; fix pending. Staging: not checked. Production: not checked.

## History

- 2026-09-27 22:47 UTC, Codex `/root/wave_info_dev`: Claimed separate typography defect after peer title change landed on dev.
