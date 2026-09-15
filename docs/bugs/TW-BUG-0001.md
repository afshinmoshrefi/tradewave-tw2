# TW-BUG-0001: Mobile Rotation Can Crash the Viewer

- Status: verified (dev, limited to the checks below)
- Confidence: reproduced and fixed
- Priority: P1 (viewer failure or silent change of user intent)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: Claude Code (claude-opus-5), session ac415bed-b1cf-4689-be18-536911d44893; claimed 2026-09-15T21:01Z; branch `claude/tw-bug-0001-mobile-rotation-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0001-mobile-rotation-20260915`; recorded by Codex, shared-bug-memory-20260915
- Authorization: Afshin authorized the fix on 2026-09-15 ("fix codex's recommended 2 bugs first"); fast dev completion only, no staging/production
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Fixed in: task `0bbf76b8f1ac23ada9c8267f473040fcd661d600` (`claude/tw-bug-0001-mobile-rotation-20260915`); on main via `99bce08d5c6cbbac88dd8832466e00a85cdca700`; verified on dev 2026-09-15 with bundle `main.35bdd7c9.js`
- Staging/production: not deployed by this task; not verified

## Reproduction, Impact and Evidence
**Priority: high.** Open the viewer in phone portrait, allow its charts to load, then rotate to landscape. The chart area can be replaced by **“MobileLayoutL encountered an error.”** Clicking **Retry panel** reproduced the failure.

This reproduced twice in Chromium iPhone emulation, including rotation without any preceding drag. The caught error is `Cannot read properties of undefined (reading 'speed')`. Its stack reaches `MobileLayoutL`'s reset effect and Swiper's `this.params.speed` read. A stale Swiper object during layout switching is the leading lifecycle explanation. See [MobileLayoutL.js:124](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/MobileLayoutL.js#L124).

[Screenshot](evidence/2026-09-15/mobile/03-landscape-rotation.png) · [Confirmed rotation and retry receipt](evidence/2026-09-15/mobile-confirm-rotate/audit.json)

## Investigation: Portrait/landscape lifecycle

Expected: a loaded viewer survives portrait to landscape and back; Retry panel restores a usable viewer after a recoverable error. The stack confirms slideTo reads missing params; the stale/destroyed instance lifecycle is the leading explanation, not an independently instrumented lifecycle proof.

## Acceptance and Regression Checks

Exercise repeated portrait/landscape cycles before and after a touch resize, plus retry and direct landscape load. No error boundary or speed exception; charts remain usable. Confirm physical Safari before claiming Safari coverage.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

Confirmed cause: App holds one Swiper instance in state for whichever layout is mounted. Rotation unmounts the portrait layout; swiper/react calls `destroy(true, false)`, which deletes the instance's params and sets `destroyed`. `MobileLayoutL` mounts, and its reset effect ran while `props.swiper` was still that destroyed object (the new Swiper's `setSwiper` had only been queued), so `slideTo` read `this.params.speed`. Retry panel remounted into the same stale-instance state. `swiperInstance.test.js` reproduces the exact exception on a real destroyed Swiper 6.7.0.

Change: new `web-react/src/components/swiperInstance.js` (`liveSwiper`) returns the instance only when it is not destroyed and still has params. `MobileLayoutL` uses it in `chartTo` and in a separate reset effect that also depends on `props.swiper`, so the reset applies once the landscape Swiper registers (table first, bar chart after a row was chosen). `MobileLayoutP.chartTo` uses the same guard. The cumulative-return effect keeps its original dependencies. `DesktopLayout` already slides through its own `swiperRef`, so tablets were not changed; unused `DesktopLayoutX` and Tara's desktop-only `showBottomSlide` were left unchanged.

Verification (Chromium iPhone emulation, 390x844 / 844x390, AAPL market 2, 2026-01-01, 366 days, 10 years):

| Case | Baseline `fce41885` | Live `99bce08d` |
|---|---|---|
| Three portrait -> landscape -> portrait cycles | Error panel on every landscape, speed exception | 9/9 pass: landscape layout, live Swiper, Trend Chart usable, 366 days kept |
| Touch press on right edge, then rotate | Error panel | Pass |
| Retry panel after the landscape boundary is forced into its error state | Error repeats | Pass: layout and bar chart render |
| Fresh landscape load | Speed error logged in the audit | Pass |

Receipts: [baseline](evidence/claude-tw-bug-0001-0002-20260915/baseline/rotate-receipt.json) ([screenshot](evidence/claude-tw-bug-0001-0002-20260915/baseline/R01a-landscape-crash.png)), [live rotation](evidence/claude-tw-bug-0001-0002-20260915/live/rotate-receipt.json) ([screenshot](evidence/claude-tw-bug-0001-0002-20260915/live/R01a-landscape.png), [retry](evidence/claude-tw-bug-0001-0002-20260915/live/R06-retry-panel-recovers.png)), [live fresh landscape](evidence/claude-tw-bug-0001-0002-20260915/live/landscape-receipt.json).

- Focused Jest on the integrated candidate: 9 suites, 117 tests passed ([output](evidence/claude-tw-bug-0001-0002-20260915/focused-jest-output.txt)). Existing mounted regression `tools/ui_capture/check_trend_chart_labels.js` passed at desktop and both mobile orientations ([result](evidence/claude-tw-bug-0001-0002-20260915/label-regression.json)). Provenance build log: [build.log](evidence/claude-tw-bug-0001-0002-20260915/build.log).
- Browser harness: [verify-bugs.cjs](evidence/claude-tw-bug-0001-0002-20260915/verify-bugs.cjs) (derived from Codex's audit scripts; `--build` serves a candidate to a disposable browser only). Run as `flask` with the live dev capture shell: `node verify-bugs.cjs --mode rotate|landscape|resize --out DIR`. Baseline receipts on `fce41885` reproduced the failure; the same cases pass live on `99bce08d` ([live output](evidence/claude-tw-bug-0001-0002-20260915/live-output.txt)).
- Task commits pushed; integration branch `claude/tw-bug-0001-0002-dev-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0001-0002-dev-20260915`, merge candidate `99bce08d5c6cbbac88dd8832466e00a85cdca700`. All worktrees are clean and pushed.
- Dev activation 2026-09-15 (UTC, see [activation receipt](evidence/claude-tw-bug-0001-0002-20260915/activation.json)): artifact `/home/flask/web-react/releases/build-99bce08d5c6cbbac88dd8832466e00a85cdca700`, served bundle `main.35bdd7c9.js`, byte-identical to the build tested before activation except its provenance stamp. `build-previous` points to `build-fce41885ec8fbdc70fabc1fb56bde38c98339396` (rollback). The activation lock was taken with `mkdir`, main was refetched, live checks ran against the served bundle, then main advanced without force to `99bce08d` and the lock was released. Backend pointer and services were unchanged.
- Parity limit (unchanged, pre-existing): the active backend still carries the uncommitted OppList4 repair (23 lines in `appserver/appserver/appserver.py`), so full application parity is not claimed. Staging and production: not deployed by this task.

Not tested: physical iPhone Safari, Android, tablets, and a real (unforced) error in the Retry case; the Retry check forces the boundary's error state to recreate the destroyed-instance remount. Regression risk: the landscape reset now also runs when App's Swiper instance changes, which only happens when a layout's Swiper mounts.

Next: none required. If rotation fails again, reopen this ID with the failing revision; rerun `verify-bugs.cjs --mode rotate` and `--mode landscape`.

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
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0001.md` for the latest record commit.
- 2026-09-15T21:01Z: Claude Code claimed implementation (session ac415bed). Next: reproduce on dev `fce41885`, fix, focused tests, dev activation and live check.
- 2026-09-15: Claude Code (session ac415bed) reproduced on dev `fce41885`, fixed in `0bbf76b8`, integrated as `99bce08d`, activated and verified on dev (bundle `main.35bdd7c9.js`). Status verified on dev only.
- 2026-09-15: Codex independent live review passed; Afshin reported both fixes work. Missing build-log evidence restored. Review branch `codex/review-bug-fixes-20260915`; latest record commit via `git log -1 -- docs/bugs/TW-BUG-0001.md`.
