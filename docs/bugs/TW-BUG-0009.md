# TW-BUG-0009: In-range start changes recenter the rolling chart

- Status: verified (dev, limited to the checks below)
- Confidence: reproduced and fixed
- Priority: P2
- Last verified: 2026-09-15; no new runtime check during registration
- Executor: Codex, original task trend-chart-stable-window-20260915; owner feedback confirmed the combined behavior works
- Current implementation owner: none; retained as resolved history
- Staging/production: not deployed by these tasks; not verified

## Original Failure and Expected Behavior

Reproduce on 0ee9172f: AAPL, Buy & Hold, Jan-Dec off, move the left edge far forward while staying within the visible range. The new curve starts 14 days before the new entry. Expected: keep the loaded window for in-range changes of the same study while still requesting updated opportunity data. This followed the label fix and is tracked separately because rendering correctness and viewport behavior are distinct.

## Preserved Implementation and Verification Report

The report below is historical evidence from the original task. Its active pointers and version statements describe that task's verification, not an automatically refreshed environment inventory. TW-BUG-0001 through TW-BUG-0007 remain open despite these focused fixes. Frontend success does not establish full backend parity.

# Trend Chart: keep the displayed range during start-date drags

## Outcome

The follow-up is committed, on main, and live on dev at [fce41885](https://github.com/afshinmoshrefi/tradewave-tw2/commit/fce41885ec8fbdc70fabc1fb56bde38c98339396), serving `main.0ee1de72.js`. Large forward and backward drags inside the loaded date range now keep the chart boundaries fixed.

The original label correction exposed existing request behavior: every start-date adjustment requested a curve beginning 14 days before the new start. Retained axis labels had partly hidden that movement. This follow-up retains the accepted rolling window while its data, market, symbol, years and PE selection remain current. The engine still receives the new opportunity start. Date-pair and stale-response guards remain active; all plotted dates and values come from the engine.

Moving outside the loaded range, changing the study, clearing/replacing the chart data, or switching Jan-Dec starts a fresh window under the existing mode rules. The maximum-history projection request uses the same window policy.

## Repeat the live test

1. Refresh dev, select AAPL, and choose **Buy & Hold**.
2. Open the Trend Chart and uncheck **Jan-Dec**.
3. Note the chart's first and last dates. Drag the left edge far to the right while staying inside those dates, then release.
4. Drag the left edge backward a little, then farther backward while remaining inside the chart.

Expected: the opportunity start and highlight move, and opportunity data updates. The chart's first and last dates remain the same. The curve remains fully plotted and aligned.

## Verified results

| Live state | Opportunity start | Chart first date | Chart last date | Chart instance |
|---|---|---|---|---|
| Buy & Hold, Jan-Dec on | 2026-01-01 | 2026-01-01 | 2026-12-31 | 6 |
| Jan-Dec off | 2026-01-01 | 2025-12-18 | 2026-12-17 | 7 |
| Forward 322 days | 2026-11-19 | 2025-12-18 | 2026-12-17 | 7 |
| Backward 7 days | 2026-11-12 | 2025-12-18 | 2026-12-17 | 7 |
| Backward 100 days | 2026-08-04 | 2025-12-18 | 2026-12-17 | 7 |
| Jan-Dec on | 2026-08-04 | 2026-01-01 | 2026-12-31 | 14 |
| Jan-Dec off again | 2026-08-04 | 2026-07-21 | 2027-07-20 | 15 |

All seven live states had 365 aligned labels/points, exact matching engine values, correct highlight indices, and no browser errors. Screenshots were visually checked for the initial rolling window and the large forward drag.

- 74 focused Jest tests passed across four suites.
- Nine controlled effect/request checks passed, including late HTTP and JSON, aborted transport, invalid responses, retained-window requests and reset conditions.
- The existing real mounted-component regression passed at desktop, mobile portrait and mobile landscape sizes.
- The documented release build passed with lint warnings. Full mobile application interactions and production were not exercised.

Evidence: [live receipts](evidence/trend-chart-stable-window-20260915/live-verification.json), [forward-drag screenshot](evidence/trend-chart-stable-window-20260915/live-03-large-forward.png), [activation/provenance receipt](evidence/trend-chart-stable-window-20260915/activation.json), [test output](evidence/trend-chart-stable-window-20260915/focused-jest-output.txt), [build log](evidence/trend-chart-stable-window-20260915/build.log).

## Release state

Task source is `2a5313de4f510eaf9360dbd7bc5393e901c2ea33` on `codex/trend-chart-stable-window-20260915`. Clean integration from fresh main produced `fce41885ec8fbdc70fabc1fb56bde38c98339396` on `codex/trend-chart-stable-window-dev-20260915`. Both worktrees are clean and pushed. The canonical ecosystem entry and existing trend-start pairing memory were updated.

The release artifact's hashes match the clean build, and its served main bundle was verified through nginx. The short activation lock covered the final main refetch, frontend swap, live checks and non-forced main push. The lock is released. Web and appserver remain active with their original PIDs, 1589 and 1586. The previous frontend release, `0ee9172f`, remains available through `build-previous`.

Full application parity still has the previously reported dependency: the unchanged active backend retains the separate uncommitted OppList4 sparse-data repair, 23 changed lines in `appserver/appserver/appserver.py`. Its file hash remained unchanged. The separate OppTable guard also remains in its original worktree. The [release policy](../RELEASE_PROCESS.md) requires: “Refetch and prove that current main's application tree, live backend source, and affected artifact provenance match.” Frontend provenance passes; the preserved backend difference prevents a full environment parity claim and needs separate clean integration. No staging or production activation occurred.


## Continuation

No additional fix is assigned for this resolved record. If the same failure returns, reopen this ID with a new failing revision and evidence. Repeat the original mounted regression and live interactions; do not remove the explicit label replacement or stable-window protections to resolve a neighboring bug.
