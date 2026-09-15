# TW-BUG-0008: Retained category labels garble a replaced trend curve

- Status: verified (dev, limited to the checks below)
- Confidence: reproduced and fixed
- Priority: P1
- Last verified: 2026-09-15; no new runtime check during registration
- Executor: Codex, original task trend-chart-implementation-20260915; owner feedback confirmed the combined behavior works
- Current implementation owner: none; retained as resolved history
- Staging/production: not deployed by these tasks; not verified

## Original Failure and Expected Behavior

Reproduce on pre-label-fix source: AAPL, Buy & Hold, Jan-Dec off, move the left edge far forward and then slightly backward on the mounted chart. Old Chart.js categories can retain 687 dates against 365 current data points, yielding a blank/garbled curve. Expected: dates, parsed X positions and exact Y values match each accepted engine response. The mounted regression fails old code and passes the fix.

## Preserved Implementation and Verification Report

The report below is historical evidence from the original task. Its active pointers and version statements describe that task's verification, not an automatically refreshed environment inventory. TW-BUG-0001 through TW-BUG-0007 remain open despite these focused fixes. Frontend success does not establish full backend parity.

# Trend Chart correction - dev verification

## Outcome

The Trend Chart correction is **committed, pushed to main, running on dev, and verified with real browser drags**.

- Main / frontend source: [`0ee9172f9a4a835d9883c7531108f38606df0e3c`](https://github.com/afshinmoshrefi/tradewave-tw2/commit/0ee9172f9a4a835d9883c7531108f38606df0e3c).
- Task branch: `codex/trend-chart-current-labels-20260915`, tip `e8d9b5ac45b3e0e9c7e987ad993c2b40579acbea`.
- Integration branch: `codex/trend-chart-dev-20260915`.
- Active frontend: `/home/flask/web-react/releases/build-0ee9172f9a4a835d9883c7531108f38606df0e3c`, serving `main.21523192.js`.
- No staging or production activation occurred.

**Full application parity remains unresolved because of a separate, pre-existing uncommitted backend repair.** The frontend meets its focused testing and live verification criteria. The environment is not being declared fully staging-ready.

## Change

[SeasonalChart.js](https://github.com/afshinmoshrefi/tradewave-tw2/blob/0ee9172f9a4a835d9883c7531108f38606df0e3c/web-react/src/components/SeasonalChart.js#L333) now supplies date labels from the current `chartData` tuples:

```javascript
labels: props.chartData.map(([date]) => date),
```

This replaces the retained category dates whenever a new rolling curve arrives. The curve, axis, and opportunity highlight now refer to the same current dates. Engine values, dates, leap-day convention, the 14-day lead-in, and inclusive opportunity duration remain unchanged.

The complete task diff is one runtime expression and its comment, a browser regression harness, retained engine fixtures, and a canonical knowledge entry. No drag-listener or request-handling rewrite was introduced.

## Validation

The new [mounted-chart regression](https://github.com/afshinmoshrefi/tradewave-tw2/blob/0ee9172f9a4a835d9883c7531108f38606df0e3c/tools/ui_capture/check_trend_chart_labels.js) failed on the original source at the retained label array. It passed on the corrected source and integrated candidate at desktop, mobile portrait, and mobile landscape sizes. Each layout exercises six successive response replacements on one chart, then an empty-data reload. Assertions cover exact date order/count, parsed X positions, opportunity alignment, visible dimensions, and exact engine Y values. Adjacent UI is stubbed; the component, date helpers, React wrapper, Chart.js parser/scales, and annotation plugin are real.

The four existing focused Jest suites passed **57 tests**. The source diff and script syntax checks passed. The provenance-stamped `npm run build` succeeded through `ops/build_react_release.sh`; the existing repository lint warnings remain. Dependencies were reused without changes.

### Live browser checks

The active dev artifact was exercised through local nginx using the documented capture-bot authenticated shell, with real AAPL engine responses and pointer drags at 1600 × 1000.

| State | Start | Duration | Chart instance | Points / labels | Highlight indices |
|---|---|---:|---:|---|---|
| Buy & Hold, Jan-Dec on | 2026-01-01 | 366 | 6 | 365 / 365 | 0-365 |
| Jan-Dec off | 2026-01-01 | 366 | 7 | 365 / 365 | 14-365 |
| Left edge forward 322 days | 2026-11-19 | 44 | 7 | 365 / 365 | 14-57 |
| Left edge backward 7 days | 2026-11-12 | 51 | 7 | 365 / 365 | 14-64 |
| Left edge backward 100 days | 2026-08-04 | 151 | 14 | 365 / 365 | 14-164 |
| Jan-Dec on | 2026-08-04 | 151 | 15 | 365 / 365 | 215-365 |
| Jan-Dec off again | 2026-08-04 | 151 | 16 | 365 / 365 | 14-164 |

Every state had axis indices 0-364, exact correspondence between plotted values and the matching engine response, and the expected opportunity bounds. The large forward and small backward drags reused chart instance 7, directly exercising the original failure mechanism. No browser errors occurred. The endpoint index 365 is the existing out-of-range end convention for an opportunity that includes next January 1.

- [Large forward drag screenshot](evidence/trend-chart-implementation-20260915/live-03-large-forward.png)
- [Small backward drag screenshot](evidence/trend-chart-implementation-20260915/live-04-small-backward.png)
- [Live response and chart-state receipts](evidence/trend-chart-implementation-20260915/live-verification.json)
- [Activation, provenance, rollback pointers, and parity receipt](evidence/trend-chart-implementation-20260915/activation.json)
- [Focused test output](evidence/trend-chart-implementation-20260915/focused-jest-output.txt) and [build log](evidence/trend-chart-implementation-20260915/build.log)

Integrated mobile application interactions, leap-boundary drags, and production were not exercised. Mobile coverage here is the real shared component at both mobile orientations; the unchanged mobile callers use that component.

## Integration and activation

The task started from current main `fe0c271b`. Integration preserved the seven already-pushed fixes through `63a520ea`, which were already running on dev, then merged only the chart task commits. Relative to the previously served frontend source `660ae608`, the resulting React source diff contains only the label correction and its comment.

The artifact was copied to its SHA-named release directory and all file hashes were compared with the clean build. The candidate shell/manifest preflight passed. The short dev activation lock was acquired only after testing/building, and main was refetched before the swap. The live main bundle bytes matched the artifact through nginx, web frontend health was `ok`, and all seven rendered checks passed before the non-forced main push. Main was refetched and confirmed at the candidate SHA. The lock was released.

Only the frontend pointer changed. `tradewave-web` and `tradewave-appserver` remained active with their original PIDs, 1589 and 1586. The root-owned frontend releases parent directory required a nonrecursive ownership correction to `flask:flask` so the documented build/file workflow could proceed as `flask`.

The previous frontend remains intact at `/home/flask/web-react/releases/build-660ae608dabab53e3cdf52e0db70fa82c41f0336`, and `build-previous` points to it. The activation runner contains automatic rollback for a failed live check or rejected main push. Rollback was not needed during this activation.

## Precise remaining dependency

The active backend pointer remains `/home/tradewave-worktrees/restore-overlay-integrated-20260912`, HEAD `63a520ea`. Its `appserver/appserver/appserver.py` has **23 changed lines, 19 insertions and 4 deletions**, relative to the integrated candidate. These are the pre-existing OppList4 sparse-day / empty-response changes, not chart calculations. Their file hash was checked before and after activation and stayed identical. The separate uncommitted `OppTable.js` guard was also preserved in its original worktree and was not swept into this task.

The [TradeWave deployment-manager skill](../RELEASE_PROCESS.md) requires: “Refetch and prove that current main's application tree, live backend source, and affected artifact provenance match.” The frontend portion passes; the preserved uncommitted backend changes prevent that complete claim. Resolving it requires separately preserving, reviewing/testing, committing and integrating the OppList4 work into clean source. Replacing the backend with older clean code would discard an existing live repair, so that was not done.

This is a main/dev parity dependency, not an imported staging qualification gate. Staging disk space and MCP test credentials did not gate this frontend activation. The chart correction is live; full environment staging readiness remains unclaimed.

The canonical ecosystem document and the existing `project_trend_start_date_pairing.md` memory entry were updated. Both task and integration worktrees are clean and pushed.

## Handoff delivery

The final report was sent to originating task `01a0a5f9-df26-7a71-a2bf-b17ff8ca3848`, but the tool rejected delivery because that task had been archived. It was not unarchived. This report is the retained handoff; the verified dev artifact and released lock are unaffected.


## Continuation

No additional fix is assigned for this resolved record. If the same failure returns, reopen this ID with a new failing revision and evidence. Repeat the original mounted regression and live interactions; do not remove the explicit label replacement or stable-window protections to resolve a neighboring bug.
