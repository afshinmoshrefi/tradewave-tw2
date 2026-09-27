# TW-BUG-0022: Wave Viewer toolbar controls are too small

- Status: deferred (user says 110% browser zoom makes the toolbar acceptable)
- Confidence: small computed text reproduced in authenticated dev Chrome; regression and remaining user impact unconfirmed
- Priority: P3 - reassess only if the user still finds controls difficult to read at their preferred zoom
- First observed / last updated: 2026-09-27 22:47 UTC
- Executor/session/claim time: Codex `/root/wave_info_dev`, 2026-09-27 22:47 UTC
- Authorization: initial dev typography investigation; user subsequently said 110% browser zoom makes the font look okay, though slightly small. No typography activation is authorized from this finding alone. Preserve the separately owned TW-TASK-0012 toolbar-title feature. No staging or production.

## User Impact and Reproduction

In the desktop Wave Viewer, load a pattern and inspect the bar-chart toolbar. The date, Days, Years, cycle and Analysis controls are visually tiny; at narrower desktop widths Best Waves can collapse. Expected: readable control text and titles with controls accessible across desktop widths, without changing pattern data or calculations.

## Evidence and Investigation

Authenticated dev Chrome on active toolbar-title source `c2045a082ede9595fceb3783ccef53b228edaf6a` measured root/body font at 12px and key controls at 11.4px despite `0.95em` inline font declarations. The symbol input measured 9.1px at 1280px viewport. No ancestor transform or browser zoom caused the issue. At 1440px, Best Waves was 5.9px wide; at 1280px, 2px. `globalTextSize` is responsive application state, not a persisted user size setting. The title feature is recorded separately in TW-TASK-0012; do not duplicate or replace it.

## Acceptance and Regression Checks

If reopened: compare at the user's preferred zoom in title ON/OFF states at desktop widths, check selected option text and pointer/keyboard access, and preserve mobile behavior. No fix was deployed.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/toolbar-font-dev-20260927`, worktree `/home/tradewave-worktrees/toolbar-font-20260927`. A speculative, unbuilt `SeasonalBarChart.js` wrap candidate remains uncommitted there for possible future review. It is not integrated or deployed. Reassess only on a new user report.

## Environment Verification

Dev: computed font measured; no font fix activated. User reports browser zoom 110% makes the font okay. Staging: not checked. Production: not checked.

## History

- 2026-09-27 22:47 UTC, Codex `/root/wave_info_dev`: Claimed separate typography defect after peer title change landed on dev.
- 2026-09-27 23:02 UTC, Codex `/root/wave_info_dev`: User clarified 110% zoom makes the font look okay; stopped speculative implementation and deferred this record. No app build or deployment.
