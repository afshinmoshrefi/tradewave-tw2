# Wave Viewer loop - current state

**Updated:** 2026-07-24  
**Status:** `main.e3ef851f.js` failed Wave Viewer smoke testing and was rolled
back. Development is serving `main.08bde07a.js` again. The repair branch must be
corrected before another deployment.
**Handoff branch:** `codex/wave-viewer-regression-loop-20260724`

## Environment and deployment evidence

- Regression URL: `https://tw2-dev.trxstat.com/app/`
- Currently served bundle: `main.08bde07a.js`
- Rejected bundle: `main.e3ef851f.js`
- Rejected source commit:
  `eca5ca958f825791ee9156cc42d97c77414e39be`
- Isolated source worktree on `.176`:
  `/home/tradewave-wave-loop-20260724`
- Served build symlink after rollback:
  `/home/flask/web-react/build -> build-before-wave-loop-eca5ca9`
- Restored build directory:
  `/home/flask/web-react/build-before-wave-loop-eca5ca9`
  (contains `main.08bde07a.js`)
- Rejected build retained for diagnosis:
  `/home/flask/web-react/releases/build-eca5ca958f82`
- Baseline: S&P 500 STOCKS, 10 years, 8 of 10, empty filter, 419
  opportunities, UNH first and EQR last.
- Development host: `192.168.1.176`, hostname `TW2`.
- The remote task must still record the current Wave Viewer checkout, served
  build target, and rollback target before each deployment.

## Latest retest

The `main.08bde07a.js` retest produced 6 PASS, 8 FAIL, 0 BLOCKED.

| Case | State | Expected behavior |
|---|---|---|
| 5 | PASS | Incomplete AvgP deletion retains the last valid rows. |
| 7 | FAIL | `10-90;foobar` must visibly report invalid syntax. |
| 8 | FAIL | The final rapid edit must never show the preceding result, including at 250 ms. |
| 11 | PASS | 10 to 9 to 10 year cycles preserve 8 of 10 and the active range. |
| 13 | FAIL | The filter needs an accessible name and discoverable syntax help. |
| 15 | PASS | Stable `predr>3` runs return 31. |
| 17 | FAIL | Range plus PredR must be a true intersection and independent of token order. |
| 20 | FAIL | Incomplete Win/PredR tokens retain the last valid rows and show guidance. |
| 22 | FAIL | Sorting Win% or PredR must not replace the active filter. |
| 26 | PASS | A selected opportunity and the viewer settle on the same symbol without mixed data. |
| 30 | PASS | Opportunity-table PE+2 cycles restore 10 years, 8 of 10, and 419. |
| 35 | PASS | Viewer cycle changes return to the initial consecutive state. |
| NR-01 | FAIL | Viewer years must not become the Opportunity Table years after reload. |
| NR-02 | FAIL | A stale AI-sort response must not override a later clear or strand Loading. |

DQ-01, the BK Price `NaN` row, is excluded from this UI regression loop.

## Repairs now present on the handoff branch

- Bare unknown words such as `foobar` are invalid. Bare ticker searches remain
  supported only when ticker-shaped.
- Filter evaluation is synchronous with the current text, removing the former
  250 ms stale-result window.
- Incomplete and invalid edits display guidance while retaining the last valid
  result set.
- The filter input has a placeholder, title, ARIA label, and described syntax
  help.
- A server day-range result uses the stable baseline opportunity set as the ML
  score source. An AI predicate can remove range members but cannot add members
  from outside the active range, and token order cannot change membership.
- Incomplete or invalid filters cannot trigger recurrence auto-stepdown.
- Filter history closes as typing begins and cannot intercept Win% or PredR
  header clicks.
- Input clear, history selection, and day-range changes clear stale source state
  and expose an honest Loading state while a new source request is required.
- Deep-linked Wave Viewer years no longer overwrite the Opportunity Table's
  saved recurrence. A pure recurrence helper locks this ownership rule.
- Viewer cycle transitions use an explicit state helper so consecutive and PE
  cycles restore the correct values.

The first handoff commit accidentally captured additional unverified frontend
changes from the primary Windows workspace. Those changes were not all present
in the source that produced the last-known-good `main.08bde07a.js` bundle. Do
not redeploy the current branch unchanged. The exact last-known-good source
remains in `/home/flask/web-react/src/components` on `.176`; compare against it
and reapply only the intended regression repairs.

## Verification and failed-deployment evidence

- Focused helper suites: 4 suites, 19 tests passed.
- React component unit suites: 7 suites, 78 tests passed locally and again in
  the isolated `.176` worktree under Node.js 22.
- `src/App.test.js` remains a pre-existing unrelated test-runner failure because
  it imports missing `src/App.js`.
- Babel parsing succeeded for every changed component.
- The supported `bash ops/build_react_release.sh` command completed on `.176`.
  The build compiled with the project's existing ESLint warnings and produced
  `main.e3ef851f.js`.
- The asset returned HTTP 200 and initially displayed the 419-row Opportunity
  Table. Later smoke testing showed the Wave Viewer stuck on
  `Loading statistics for FAST...` with zero chart canvases.
- No browser console error appeared. The appserver received no FAST chart-data
  request, identifying this as a frontend lifecycle/request-launch failure
  rather than an appserver outage.
- The deployment was rolled back immediately. Nginx and all relevant services
  remained active, and the dev-only authenticated capture shell now emits
  `main.08bde07a.js`.

## Next action

1. Hard-refresh the authenticated browser and confirm the rollback restored
   Wave Viewer chart loading on `main.08bde07a.js`.
2. In `/home/tradewave-wave-loop-20260724`, compare the rejected branch source
   with `/home/flask/web-react/src/components`, the source corresponding to the
   last-known-good bundle.
3. Remove unintended source changes and reapply only the eight intended
   regression repairs with focused tests.
4. Build and smoke-test chart request launch through the dev-only capture
   harness before switching the served build.
5. Only after Wave Viewer charts load, run the eight failing cases and continue
   the loop according to `WAVE_VIEWER_LOOP.md`.

## Source reports

- `reports/WAVE_VIEWER_2026-07-24_INITIAL.md`
- `reports/WAVE_VIEWER_2026-07-24_RETEST_MAIN_08BDE07A.md`
