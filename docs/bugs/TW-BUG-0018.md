# TW-BUG-0018: Wave Info shows SMA 50 in place of Sharpe Ratio

- Status: verified on dev
- Confidence: owner screenshot/source reproduction; live dev browser verified after repair
- Priority: P2 - a financial metric is mislabeled in a visible statistics panel
- First observed / last updated: 2026-09-27 / 2026-09-27 17:31 UTC
- Executor/session/claim time: Codex `wave-info-20260927`, 2026-09-27 UTC
- Authorization: Afshin requested the Wave Info repair and four-row layout on dev. No staging or production writes.

## User Impact and Reproduction

Open a seasonal study and its desktop statistics window. Wave Info shows `SMA 50` in the second row where Sharpe Ratio belongs. Trend Long occupies a second trend row and its label/info icon misalign. Owner's screenshot shows `Percent Profitable 100.0%`, `SMA 50 188.8884`, `Trend Alignment Against (37)`, and `Trend Long 37` with a left arrow. Exact study identity and active dev artifact in the screenshot are unknown.

Expected: Percent Profitable and engine Sharpe Ratio by name, a separately named engine TradeWave Ratio when the existing `showSR2` visibility gate permits it, and one Trend Alignment row with the direction-matched score and prior-reading arrow. Keep labels and info icon aligned.

## Evidence and Investigation

At main `3143e2a`, `web-react/src/components/TradeDetail.js` passes `filter={[12, 15, alignIdx, trendIdx]}` to Wave Info; position 15 resolves to SMA 50 after engine response field order changed. `VisualTable` places the info icon and arrow only on Trend Long/Short and stacks the label/icon vertically. TradeWave supplies Sharpe Ratio and `Sharpe Ratio2` (TradeWave Ratio); no client calculation is needed. The existing `show_sr2` token claim and `showSR2` visibility flag must both permit TWR. Owner screenshot attached in the conversation, September 27.

## Acceptance and Regression Checks

Inspect a real rendered dev study with eligible account: four rows in specified order, second row is engine Sharpe, third is engine TWR, combined alignment has direction-specific score/arrow and aligned info icon. For an ineligible account omit the TWR row. Compare visible metric strings to the same engine response. Unit checks cover hidden TWR, unavailable/zero trend scores and short-direction arrows; no lower-tier browser session was available for live entitlement verification.

## Implementation and Handoff

Source commit `1a0d986047e715a0e475212780e989237804f99e` is on `origin/main` and active on dev. Branch `codex/wave-info-20260927`; local worktree `TradeWave Main Orchestrator/wave-info-20260927`; clean Linux build worktree `/home/tradewave-worktrees/wave-info-20260927`. `TradeDetail`, `TradeDetailMobile`, `VisualTable` and `waveInfoRows` now select named engine fields, show TWR only when the existing token claim and visibility flag allow it, and combine the direction-matched trend label, score and arrow. Narrow mobile uses `TWR` and `Alignment` labels and a compact score so all elements fit at 320px. No engine math, migration or configuration change. Four focused Jest tests passed; `ops/build_react_release.sh` passed with existing repository lint warnings. Previous frontend artifact is retained for rollback at `/home/flask/web-react/releases/build-4a0c34355f98bc44dc61b7cc12cfebba2e65848d`.

## Environment Verification

Dev: verified 2026-09-27 UTC. Active `/home/flask/web-react/build` points to immutable `build-1a0d986047e715a0e475212780e989237804f99e`, stamped with the same SHA; `main.ca5a5a9b.js` is served through nginx. Existing backend pointer `/home/tradewave-worktrees/flat-return-release-585b668` is unchanged, and its application tree matches current main. Final dev activation lock released. An authenticated capture-bot browser loaded AAPL, S&P 500, Jan 15-29 2026, 15 calendar days, 10 consecutive years. Desktop 1920x1080 and iPhone-UA widths 390/320 rendered four Wave Info rows. Displayed 90.91%, Sharpe 0.56 and TWR 1.19 match that exact ChartData4 response; alignment info icon and arrow are present, centered and inside cell bounds. Screenshots: [desktop](evidence/TW-BUG-0018/dev-desktop-wave-info.png), [390px](evidence/TW-BUG-0018/dev-mobile-390.png), [320px](evidence/TW-BUG-0018/dev-mobile-320.png). Mobile capture used current Swiper slide navigation because the older capture CLI's tab selector and `ready.tradeDetail` assumption do not match the mobile view; DOM/value/geometry assertions passed before the CLI's obsolete wait. Staging and production: not deployed by this task.

Separate finding: mobile Wave Stats still shows a raw `Sharpe Ratio2` fourth row due to its own positional filter; see [TW-BUG-0019](TW-BUG-0019.md). This repair was limited to Wave Info.

## History

- 2026-09-27: Codex claims owner-authorized dev UI repair and separate TradeWave Ratio row; no calculation or entitlement change.
- 2026-09-27: Codex verified the final build in the real dev desktop and mobile browsers, pushed source to main, and recorded screenshots. Next action: owner reviews on dev, then separately requests staging if desired.
