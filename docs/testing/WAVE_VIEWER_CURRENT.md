# Wave Viewer loop - current state

**Updated:** 2026-07-24  
**Status:** Latest repairs are source-complete and locally verified, but are not
yet built or deployed on the development host.  
**Handoff branch:** `codex/wave-viewer-regression-loop-20260724`

## Environment and deployment evidence

- Regression URL: `https://tw2-dev.trxstat.com/app/`
- Last browser-verified bundle: `main.08bde07a.js`
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

The branch also captures the complete previously uncommitted React state used
by the regression work, including the responsiveness and Tara action-contract
changes on which the tested frontend source depends. This avoids rebuilding
from an older partial source snapshot.

## Verification already completed before handoff

- Focused helper suites: 4 suites, 19 tests passed.
- React component unit suites: 7 suites, 78 tests passed.
- `src/App.test.js` remains a pre-existing unrelated test-runner failure because
  it imports missing `src/App.js`.
- Babel parsing succeeded for every changed component.
- A production build could not run on the primary Windows workspace because its
  Node.js 14 runtime cannot load the current ESLint dependencies. Build on the
  Linux development host with its supported Node runtime.

## Next action

1. Fetch and check out the handoff branch in a clean worktree on the remote
   machine or development host.
2. Confirm `.176` is the Wave Viewer host and record the currently served build
   and rollback target.
3. Run focused tests and the production build.
4. Deploy to development only and confirm the bundle hash is no longer
   `main.08bde07a.js`.
5. Verify the 419-row baseline.
6. Run the eight failing cases, then the six adjacent passing cases.
7. Continue the loop according to `WAVE_VIEWER_LOOP.md`.

## Source reports

- `reports/WAVE_VIEWER_2026-07-24_INITIAL.md`
- `reports/WAVE_VIEWER_2026-07-24_RETEST_MAIN_08BDE07A.md`
