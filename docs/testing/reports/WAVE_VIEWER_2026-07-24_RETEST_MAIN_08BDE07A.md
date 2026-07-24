TradeWave Wave Viewer — `main.08bde07a.js` Regression Retest

**Retest date:** 2026-07-24  
**Target:** `https://tw2-dev.trxstat.com/app/`  
**Authentication:** Confirmed; authenticated controls and Log Out were visible  
**Repairs made:** None

## Build and baseline

The app was hard-refreshed before testing. The loaded application bundle was:

`https://tw2-dev.trxstat.com/app/static/js/main.08bde07a.js`

The requested baseline was confirmed before testing:

- Universe: S&P 500 STOCKS
- Years: 10
- Recurrence: 8 of 10 years
- Filter: empty
- Results: 419 opportunities
- First/last opportunity: UNH / EQR

[Bundle and initial baseline](./00-bundle-and-baseline.png)

## Outcome

**6 PASS, 8 FAIL, 0 BLOCKED.**

| Case | Result | Evidence |
|---:|:---:|---|
| 5 | **PASS** | Deleting `avgp>10` character-by-character did not produce the former empty state. `10-90;avgp>` through `10-90;avg` retained one prior valid row; shorter tokens returned 286. [Screenshot](./case-05-incomplete.png) |
| 7 | **FAIL** | `10-90;foobar` retained one row but displayed no invalid/syntax indicator. Correcting it to `10-90` returned 286. [Invalid](./case-07-invalid.png) · [Corrected](./case-07-corrected.png) |
| 8 | **FAIL** | The rapid sequence ending `predr>3` displayed the preceding one-row result at the 250 ms sample, then corrected to 31 at 500 ms and remained stable through five seconds. The two sequences ending `10-90` stayed at 286. [Final state](./case-08-rapid-final.png) |
| 11 | **PASS** | Three 10→9→10 year cycles preserved 8-of-10 and the active `10-90` filter. Each return to 10 years restored 286 opportunities. [Screenshot](./case-11-years-return.png) |
| 13 | **FAIL** | The Filter input still has no placeholder, title, ARIA label, or description. The Learn index and relevant Wave Viewer/AvgP articles do not document `PredR`, `win>`, ranges, operators, or filter syntax. [Screenshot](./case-13-filter-help.png) |
| 15 | **PASS** | Three clean, settled `predr>3` runs each returned 31 opportunities. [Screenshot](./case-15-predr.png) |
| 17 | **FAIL** | `10-90;predr>3` and `predr>3;10-90` both returned 56 in three settled comparisons. Although order is consistent, 56 cannot be the intersection of the standalone 31-row `predr>3` result. [Screenshot](./case-17-order.png) |
| 20 | **FAIL** | `win>`/`win` and `predr>`/`predr`/`pred`/`pre` returned zero rows. The new build now displays “Finish the … filter” guidance, but the empty-result behavior remains. Full deletion restored 419. [Incomplete PredR](./case-20-incomplete-predr.png) |
| 22 | **FAIL** | Sorting Win% changed `win>70`/95 rows to `10-90`/112 rows. Sorting PredR changed `predr>3`/31 rows to `10-90`/286 rows. [Win sort](./case-22-win-sort.png) · [PredR sort](./case-22-predr-sort.png) |
| 26 | **PASS** | On UNH→PCAR selection, the 250 ms sample showed PCAR controls/header with detail masked by Loading. By 500 ms, symbol, company header, and Wave Detail all showed PCAR and remained consistent through three seconds. [Final state](./case-26-final.png) |
| 30 | **PASS** | Three PE+2 cycles were consistent: on = 59 opportunities/10-of-10; off = 419 opportunities/8-of-10. The empty filter and 10-year setting were restored on every off transition. [Screenshot](./case-30-pe2-cycles.png) |
| 35 | **PASS** | Two complete `PE Years→PE+1→PE+2→PE+3→consecutive` cycles returned to the initial PCAR state: 2026-07-24, 179 days, 10 viewer years, consecutive. [Screenshot](./case-35-pe-cycles.png) |
| NR-01 | **FAIL** | Setting the Viewer to six years left the Opportunity Table at 10 years/8-of-10/419 before reload. After reload, the table inherited six years/6-of-6 and returned 260. [Before reload](./NR-01-before-reload-viewer-6.png) · [After reload](./NR-01-after-reload.png) |
| NR-02 | **FAIL** | After an AI sort, clearing the filter and resetting recurrence was overridden within 500 ms. For 12 seconds the filter stayed `10-90`, the table had no rows, the footer retained 286, and visible Loading persisted. A reload was required to continue. [Screenshot](./NR-02-clear-after-ai-sort.png) |

## New regression assessment

Case 8 regressed from PASS in the prior retest to FAIL on this bundle: the old one-row result remained visible for 250 ms after the input already showed the final `predr>3` expression.

No additional regression identifier beyond the requested NR-01 and NR-02 cases was opened.

## DQ-01 — analytics follow-up

The BK Price `NaN` observation is excluded from Wave Viewer UI regression totals as instructed. It remains DQ-01 for symbol-status/pricing-coverage analytics follow-up.

## Console evidence

No Chrome console warnings or errors were captured.

## Final state

After testing, the controlled app was restored and reverified on `main.08bde07a.js`:

- Universe: S&P 500 STOCKS
- Years: 10
- Recurrence: 8 of 10 years
- Filter: empty
- Results: 419 opportunities
- Loading: false

[Restored final baseline](./final-restored-baseline-419.png)

No source code, deployment, configuration, API, database, analytics, or user-record repairs were performed.
