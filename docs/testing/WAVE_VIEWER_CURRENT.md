# Wave Viewer loop - current state

**Updated:** 2026-07-24  
**Status:** COMPLETE. Development is serving `main.09d767ca.js`. The complete
Wave Viewer correctness matrix and P-01 budgets passed in two consecutive clean
runs on this deployed bundle. Both runs ended at the required baseline.
**Handoff branch:** `codex/wave-viewer-regression-loop-20260724`

## Environment and deployment evidence

- Regression URL: `https://tw2-dev.trxstat.com/app/`
- Development host: `192.168.1.176`, hostname `TW2`
- Served bundle: `main.09d767ca.js`
- Served build:
  `/home/flask/web-react/build -> build-wave-viewer-20260724-09d767ca`
- Immediate rollback:
  `/home/flask/web-react/build-rollback-wave-viewer-20260724-84c91001
  -> build-wave-viewer-20260724-84c91001`
- Isolated source worktree:
  `/home/tradewave-wave-loop-20260724`
- Baseline restored after each clean run: S&P 500 STOCKS, 10 years,
  8 of 10, PE+2 off, empty filter, 419 opportunities, no selected viewer
  symbol, 2026-07-24, 30 days, 10 viewer years, consecutive.
- The authoritative functional tests used the owner's visible, authenticated
  Chrome tab. The capture harness was used only for supplemental P-01 timing.
- `.180`, staging, production, TW1, WorkOS/auth configuration, secrets,
  customer data, billing, and DQ-01 were not touched.

## Final repairs

- Invalid, incomplete, ticker, range, AvgP, Win%, PredR, and combined filters
  now have deterministic syntax, guidance, retention, and intersection
  behavior.
- AI-filter requests use the current range source, ignore stale responses, and
  cannot override a later edit, clear, or sort.
- Filter help is discoverable and accessible.
- Opportunity-table recurrence remains independent from Wave Viewer deep-link
  and cycle state.
- Latest-row selection wins without mixed-symbol chart data.
- Bar-chart data is derived synchronously, Chart.js animation is disabled, and
  the chart component is memoized.
- A persistent bar-chart canvas stays mounted behind an opaque loading cover,
  avoiding a blank render followed by a second data render.
- Non-critical trade-detail state is deferred until after the primary chart
  paints. Optional comparison and buy-and-hold state are no longer cleared by
  the unrelated primary-chart request path.
- The responsive bar chart uses a 0.5 backing-store pixel ratio while
  preserving its CSS size, data, axes, colors, controls, and click behavior.
  The final chart was visually inspected in the visible Chrome session.

## Final verification

- Focused meaningful unit suites: 6 suites, 51 tests passed.
- `src/App.test.js` remains a pre-existing unrelated CRA boilerplate failure
  because it imports missing `src/App.js`.
- Production build completed with the repository's existing ESLint warnings.
- Visible Chrome pass 1: complete correctness matrix PASS; console clean;
  baseline restored.
- Visible Chrome pass 2: complete correctness matrix PASS; console clean;
  baseline restored.
- No persistent Loading state remained.
- Authentication remained active; WorkOS was not disabled or modified.

### P-01 deployed run 1

- Evidence:
  `docs/testing/evidence/p01-postdeploy-final-run1-09d767ca.json`
- Warm response-to-stable median: 338 ms
- Warm response-to-stable maximum: 472 ms
- Warm selection-to-usable median: 1,155 ms
- Warm selection-to-usable maximum: 1,202 ms
- Cold authenticated selection-to-usable: 4,279 ms
- Console errors: 0; missing targets: 0

### P-01 deployed run 2

- Evidence:
  `docs/testing/evidence/p01-postdeploy-final-run2-09d767ca.json`
- Warm response-to-stable median: 478 ms
- Warm response-to-stable maximum: 543 ms
- Warm selection-to-usable median: 833 ms
- Warm selection-to-usable maximum: 904 ms
- Cold authenticated selection-to-usable: 4,062 ms
- Console errors: 0; missing targets: 0

Both deployed runs meet the required median <= 500 ms, maximum <= 1 second,
warm median <= 3 seconds, warm maximum <= 5 seconds, and cold <= 10 seconds
budgets on the same `09d767ca` bundle.

## Source reports

- `reports/WAVE_VIEWER_2026-07-24_INITIAL.md`
- `reports/WAVE_VIEWER_2026-07-24_RETEST_MAIN_08BDE07A.md`
- `docs/testing/WAVE_VIEWER_RUN_LOG.md`
