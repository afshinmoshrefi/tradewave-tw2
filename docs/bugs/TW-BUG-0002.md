# TW-BUG-0002: The Right Resize Edge Can Change the Duration Without a Drag

- Status: verified (dev, limited to the checks below)
- Confidence: reproduced and fixed
- Priority: P1 (viewer failure or silent change of user intent)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: Claude Code (claude-opus-5), session ac415bed-b1cf-4689-be18-536911d44893; claimed 2026-09-15T21:01Z; branch `claude/tw-bug-0002-right-resize-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0002-right-resize-20260915`; recorded by Codex, shared-bug-memory-20260915
- Authorization: Afshin authorized the fix on 2026-09-15 ("fix codex's recommended 2 bugs first"); fast dev completion only, no staging/production
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Fixed in: task `16feb436f7bfc5034882bb95c3c914b1f9357b6f`, `222bdb674b663bc911314c3b8cca99b840dd2aac` and harness mapping `ab824ccc8ed58e14bbd87cf3ffae71a7b4c2e789` (`claude/tw-bug-0002-right-resize-20260915`); on main via `99bce08d5c6cbbac88dd8832466e00a85cdca700`; verified on dev 2026-09-15 with bundle `main.35bdd7c9.js`
- Staging/production: not deployed by this task; not verified

## Reproduction, Impact and Evidence
**Priority: high.** Select AAPL, choose **Buy & Hold**, turn **Jan-Dec** off, then press and release the right resize handle without moving it. The tested duration changed from **366 to 351 days**. The opportunity end date and its statistics changed with it.

A second check started with a fully visible 30-day opportunity. Moving the right handle ten date positions produced **39 days**, although the intended result was 40. The handler derives the entire duration from the overlay width, which loses clipped days and the inclusive entry day. See [SeasonalChart.js:606](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalChart.js#L606).

[Screenshot after the stationary click](evidence/2026-09-15/extra/02-right-click-without-drag.png) · [Resize receipts, cases 01-05](evidence/2026-09-15/extra/audit.json)

## Investigation: Duration and inclusive calendar boundaries

Expected: a stationary press/release preserves all 366 days and end date. A fully visible 30-day May 1 window expanded by ten category-day positions becomes 40. Investigate movement deltas, clipped overlays and mouse/touch handlers without deriving financial results.

## Acceptance and Regression Checks

Test no movement, positive/negative movement, clipped/unclipped right edge, minimum duration, and touch. Assert start/end/duration as well as visible geometry and exact engine values. Preserve end = start + (days - 1).

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

Confirmed cause: on release the handler set `days = round(overlayWidth / pixelsPerDay)`. An unclipped highlight spans `days - 1` category positions, and a highlight whose end runs past the chart is drawn only to the chart boundary, so the width lost the inclusive day and the clipped days. A `|days - daysOut| <= 1` tolerance hid the off-by-one for stationary clicks on unclipped windows only.

Additional failure found during verification (same handles, fixed in `222bdb67`): a drag that started on a resize edge also started a text selection. The next drag then became a native drag-and-drop of that selection (`dragstart`, `pointercancel`), no mouseup arrived, and the resize never completed. Consecutive drags on one mounted chart therefore failed silently. Also, a move past the width bound was ignored rather than clamped, so a fast drag stopped short of the 2-day minimum.

Change:
- New `web-react/src/components/trendRightResize.js` (`rightResizeDays`): duration = current duration + whole day positions moved; no movement or sub-day jitter keeps the duration. When the end runs past the chart, a leftward drag measures from the visible boundary; a rightward drag never shortens. Clamped to `minDaysOut`/`maxDaysOut`. `end = start + (days - 1)` is preserved. No engine values are calculated.
- `SeasonalChart.js`: the highlight effect records whether the end runs past the chart and how many days the drawn edge represents; the right-edge handler records the start width on press and calls `rightResizeDays`; unchanged results snap the overlay back; the right-edge width bound is one position (2 days) and clamps. The resize overlay uses the existing `noselect` class. The pixels-per-day learning call keeps its previous width-derived input. The left-edge handler is unchanged.
- `tools/ui_capture/check_trend_chart_labels.js` loads the new real module.

Verification (desktop 1600x1000 mouse, AAPL market 2, Buy & Hold, Jan-Dec off, 10 years):

| Case | Baseline `fce41885` | Live `99bce08d` |
|---|---|---|
| Press/release right edge, no movement, 366 days (end past chart) | 351 days | 366, highlight unchanged |
| Clipped edge +5 | 355 | 366 (not shortened) |
| Clipped edge -10 | wrong/cascaded | 342 days, end 2026-12-08, highlight end where released |
| 2026-05-01, 30 days, +10 | 39 | 40, end 2026-06-09 |
| Then -10, +1, no movement (consecutive drags) | lost or wrong | 30, 31, 31 |
| Drag far left | 5 | 2 (minimum) |
| Neighbour: 60 days, left edge +20, then right +5 | not run | start 2026-05-21 with end kept; window first/last kept (TW-BUG-0009); 45 days |
| Mobile portrait touch press, no movement | not isolated | 366 kept |

Receipts: [baseline](evidence/claude-tw-bug-0001-0002-20260915/baseline/resize-receipt.json) ([351 days](evidence/claude-tw-bug-0001-0002-20260915/baseline/D02-right-press-release-351-days.png), [39 days](evidence/claude-tw-bug-0001-0002-20260915/baseline/D06-right-plus-10-gives-39.png)), [live](evidence/claude-tw-bug-0001-0002-20260915/live/resize-receipt.json) ([no movement](evidence/claude-tw-bug-0001-0002-20260915/live/D02-right-press-release-no-move.png), [clipped -10](evidence/claude-tw-bug-0001-0002-20260915/live/D04-clipped-edge-left-10.png), [+10](evidence/claude-tw-bug-0001-0002-20260915/live/D06-right-plus-10.png), [-10](evidence/claude-tw-bug-0001-0002-20260915/live/D07-right-minus-10.png)). Unit contract: `trendRightResize.test.js`.

- Focused Jest on the integrated candidate: 9 suites, 117 tests passed ([output](evidence/claude-tw-bug-0001-0002-20260915/focused-jest-output.txt)). Existing mounted regression `tools/ui_capture/check_trend_chart_labels.js` passed at desktop and both mobile orientations ([result](evidence/claude-tw-bug-0001-0002-20260915/label-regression.json)). Provenance build log: [build.log](evidence/claude-tw-bug-0001-0002-20260915/build.log).
- Browser harness: [verify-bugs.cjs](evidence/claude-tw-bug-0001-0002-20260915/verify-bugs.cjs) (derived from Codex's audit scripts; `--build` serves a candidate to a disposable browser only). Run as `flask` with the live dev capture shell: `node verify-bugs.cjs --mode rotate|landscape|resize --out DIR`. Baseline receipts on `fce41885` reproduced the failure; the same cases pass live on `99bce08d` ([live output](evidence/claude-tw-bug-0001-0002-20260915/live-output.txt)).
- Task commits pushed; integration branch `claude/tw-bug-0001-0002-dev-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0001-0002-dev-20260915`, merge candidate `99bce08d5c6cbbac88dd8832466e00a85cdca700`. All worktrees are clean and pushed.
- Dev activation 2026-09-15 (UTC, see [activation receipt](evidence/claude-tw-bug-0001-0002-20260915/activation.json)): artifact `/home/flask/web-react/releases/build-99bce08d5c6cbbac88dd8832466e00a85cdca700`, served bundle `main.35bdd7c9.js`, byte-identical to the build tested before activation except its provenance stamp. `build-previous` points to `build-fce41885ec8fbdc70fabc1fb56bde38c98339396` (rollback). The activation lock was taken with `mkdir`, main was refetched, live checks ran against the served bundle, then main advanced without force to `99bce08d` and the lock was released. Backend pointer and services were unchanged.
- Parity limit (unchanged, pre-existing): the active backend still carries the uncommitted OppList4 repair (23 lines in `appserver/appserver/appserver.py`), so full application parity is not claimed. Staging and production: not deployed by this task.

Original implementer did not test touch drag with movement; see the independent review below for subsequent limited coverage. Still not tested: physical Safari, leap-day windows (TW-BUG-0005 owns the leap-day contract; index arithmetic across a missing February 29 remains that record's scope), PE year-shifted highlights (TW-BUG-0004), and the final-date wrap (TW-BUG-0003). The left edge still derives its minimum width from `minDaysOut` positions and still has no selection protection other than the shared overlay class.

Next: none required. If the right edge regresses, reopen this ID and rerun `verify-bugs.cjs --mode resize`.

## Independent Review and Owner Confirmation (2026-09-15)

Codex independently reviewed the implementation and reran all 28 original live cases
on dev bundle `main.35bdd7c9.js`; all passed with no browser/console errors. Four
additional touch/rotation cases passed with the handle explicitly revealed before
each gesture. See [review, runnable commands and limitations](evidence/codex-review-0001-0002-20260915/README.md)
and [summary](evidence/codex-review-0001-0002-20260915/summary.json).
Afshin also confirmed both fixes worked in his testing; device and exact environment
were not specified. The linked build log was missing from Git and is now restored.
Status remains verified on dev; this review changed no application code.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0002.md` for the latest record commit.
- 2026-09-15T21:01Z: Claude Code claimed implementation (session ac415bed). Next: reproduce on dev `fce41885`, fix, focused tests, dev activation and live check.
- 2026-09-15: Claude Code (session ac415bed) reproduced on dev `fce41885`, fixed in `16feb436` and `222bdb67` (also consecutive-drag selection failure), integrated as `99bce08d`, activated and verified on dev (bundle `main.35bdd7c9.js`). Status verified on dev only.
- 2026-09-15: Codex independent live review passed; Afshin reported both fixes work. Missing build-log evidence restored. Review branch `codex/review-bug-fixes-20260915`; latest record commit via `git log -1 -- docs/bugs/TW-BUG-0002.md`.
