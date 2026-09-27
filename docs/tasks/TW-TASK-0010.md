# TW-TASK-0010: Avg Gain value tooltips

- Status: verified on dev
- Confidence: reproduced and live-verified
- Priority: P3 - clarify two existing values
- First observed / last updated: 2026-09-27 UTC
- Executor/session/claim time: Codex `/root/wave_info_dev`, 2026-09-27 UTC
- Authorization: Afshin requested short tooltips on each Avg Gain value on dev; preserve engine values, layout and existing detailed tooltip when global tips are on. No staging or production.

## Goal, Scope and Acceptance

In Wave Stats, with global tooltips off, hovering the first Avg Gain value shows `Average of winning years`; hovering the second shows `Average of all years`. With global tooltips on, retain the existing detailed row tooltip and avoid competing short tips. Preserve the existing comma-separated numbers and responsive layout.

## Evidence and Investigation

At baseline `b0957627610f5a8de08ad11f4147b63c44689774`, `TradeDetail.js` combines two separate appserver fields (`Avg Profit` and `Avg Profit - All`); `VisualTable.js` disables the row-level Tippy when global tooltips are off. A mixed AAPL study displayed `2.38%, 1.74%`; an all-winning KMB study displayed `4.55%, 4.55%`, each matching the engine.

## Acceptance and Regression Checks

- 2026-09-27, authenticated dev Chrome at 1920 x 1080, AAPL long, January 15-29, 2026, 10 years: loaded candidate `main.af8f6b5f.js`. With global tooltips OFF, hovering each number separately displayed exactly the requested short tooltip. The row remained `2.38%, 1.74%`.
- Clicked the actual global tooltip toggle ON. The short-tip spans disappeared, the original detailed row tooltip appeared, and the row still read `2.38%, 1.74%`, matching the two TradeWave engine fields. Existing capture chart-ready, painted-canvas, visual-stability and sanity checks passed.
- `npm run build` passed with pre-existing project lint warnings. No dedicated component test existed. Mobile hover was not run; markup and text are shared, and no style dimensions changed.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/avg-gain-tooltips-20260927`, pushed source commit `7653f1129e55363ee458b0667476ec6360de0a68`; worktree `/home/tradewave-worktrees/avg-gain-tooltips-20260927`. Clean integration commit and active dev source: `c76bd9b8e036d6c2638c44871b1e64b1981392ae`; frontend artifact `/home/flask/web-react/releases/build-c76bd9b8e036d6c2638c44871b1e64b1981392ae`. `TradeDetail.js` retains the two named engine values; `VisualTable.js` adds scoped per-number tips. No math, backend, configuration or migrations. Previous dev frontend pointer for rollback: `/home/flask/web-react/releases/build-1a0d986047e715a0e475212780e989237804f99e`. Next: owner review on dev; staging requires a separate request.

## Environment Verification

Dev: verified on 2026-09-27 at `c76bd9b8e036d6c2638c44871b1e64b1981392ae` by authenticated browser interaction and engine-value comparison. Staging: not checked. Production: not checked.

## History

- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Claimed authorized UI enhancement at `d97e91ea3c541e57af5f355b1d06d7013d4b088e`.
- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Implemented, built and verified on live dev at `c76bd9b8e036d6c2638c44871b1e64b1981392ae`.
