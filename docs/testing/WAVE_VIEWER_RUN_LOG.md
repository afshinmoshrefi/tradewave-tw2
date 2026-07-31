# Wave Viewer regression run log

This file is append-only. Keep the compact current state in
`WAVE_VIEWER_CURRENT.md`.

## 2026-07-24 - Initial regression

- Target: authenticated `https://tw2-dev.trxstat.com/app/`
- Baseline: 419 opportunities at S&P 500, 10 years, 8 of 10.
- Main failures: filter edit races, invalid/incomplete filter ambiguity,
  AI-filter membership/order errors, sorting replacing filters, mixed viewer
  selection data, and recurrence/cycle state leakage.
- Source: `reports/WAVE_VIEWER_2026-07-24_INITIAL.md`.

## 2026-07-24 - Retest of `main.08bde07a.js`

- Result: 6 PASS, 8 FAIL, 0 BLOCKED.
- Pass: 5, 11, 15, 26, 30, 35.
- Fail: 7, 8, 13, 17, 20, 22, NR-01, NR-02.
- No browser-console warnings or errors.
- Baseline restored to 419 at the end.
- Source: `reports/WAVE_VIEWER_2026-07-24_RETEST_MAIN_08BDE07A.md`.

## 2026-07-24 - Source repair round after `main.08bde07a.js`

- Implemented repairs for the eight remaining cases.
- Focused verification: 19 tests passed.
- Broad React component verification: 78 tests passed across seven suites; the unrelated
  missing `src/App.js` legacy test entry still prevents a completely clean
  default run.
- Production build and browser acceptance remain to be completed on the Linux
  development host.

## 2026-07-24 - Development deployment of `main.e3ef851f.js`

- Source commit: `eca5ca958f825791ee9156cc42d97c77414e39be`.
- Isolated `.176` worktree:
  `/home/tradewave-wave-loop-20260724`.
- Server verification: seven component suites and 78 tests passed under Node.js
  22; the supported production build completed with existing ESLint warnings.
- Served build:
  `/home/flask/web-react/build -> releases/build-eca5ca958f82`.
- Rollback:
  `/home/flask/web-react/build-before-wave-loop-eca5ca9`, containing
  `main.08bde07a.js`.
- `main.e3ef851f.js` returned HTTP 200 locally and through Cloudflare. Nginx
  validated, all relevant services remained active, and the dev-only
  authenticated capture shell emitted the new bundle.
- The owner confirmed that patterns load in the authenticated browser after the
  deployment.
- Full authenticated browser regression retesting remains next.

## 2026-07-24 - `main.e3ef851f.js` rejected and rolled back

- The 419-row Opportunity Table loaded, but the Wave Viewer became stranded on
  `Loading statistics for FAST...` with zero chart canvases.
- No browser console error was recorded. Recent appserver logs contained no
  FAST chart-data request, proving the new frontend failed before launching the
  primary Wave Viewer request.
- The repair branch contained additional frontend changes that were absent from
  the source used for `main.08bde07a.js`; those changes had not been covered by
  the regression retest.
- `.176` was rolled back to
  `/home/flask/web-react/build-before-wave-loop-eca5ca9`, containing
  `main.08bde07a.js`. The rejected build remains at
  `/home/flask/web-react/releases/build-eca5ca958f82` for diagnosis.
- `tradewave-web`, `tradewave-appserver`, and nginx remained active. `.180` was
  not modified.

## 2026-07-24 - Rollback confirmed; P-01 performance regression opened

- The owner confirmed that patterns render again on `main.08bde07a.js` after
  rollback.
- Bar-chart and pattern loading is extraordinarily slow.
- P-01 is now required goal scope. Each loop must measure primary request
  launch delay, server response duration, post-response render duration, and
  total time.
- The loop cannot complete until every correctness case and the P-01 budgets
  pass in two consecutive clean runs on the same deployed bundle.

## 2026-07-24 - Correctness quarantine and focused repair

- Compared the rejected branch with the source that produced
  `main.08bde07a.js`.
- Restored the authoritative last-known-good component baseline and retained
  only the focused filter, AI-source, recurrence, latest-request, and viewer
  cycle repairs.
- Added a dev capture performance harness at
  `tools/ui_capture/wave_viewer_perf.js`.
- Meaningful unit verification passed: 6 suites and 51 tests. The unrelated
  CRA `src/App.test.js` entry still imports a missing `src/App.js`.
- The production build completed with the repository's existing warnings.
- The authenticated functional matrix was moved to the owner's visible Chrome
  session. Headless capture remained supplemental timing evidence only.

## 2026-07-24 - P-01 repair iterations

- `main.ef9205c7.js` restored correctness but its deployed P-01 medians were
  613 ms and 547 ms, above the 500 ms frontend budget.
- `main.2965c273.js` kept the canvas mounted, but its deployed median was
  589 ms.
- `main.e3bf2df4.js` deferred non-critical detail work; its first deployed run
  passed at 370 ms, but the second missed at 534 ms.
- `main.84c91001.js` reduced Chart.js backing-store work; its first deployed
  run passed at 338 ms, but the second missed at 512 ms.
- Timing splits showed that only fast cached responses missed. Optional
  comparison/buy-and-hold clearing was consuming the main thread after the
  immediate primary request started.
- Removed those unrelated clears from the primary-chart request lifecycle.
  Their own request paths continue to own their state.
- All rejected candidate builds remain immutable and recoverable. None was
  promoted outside `.176`.

## 2026-07-24 - Final deployment and two clean runs

- Final served bundle: `main.09d767ca.js`.
- Served build:
  `/home/flask/web-react/build -> build-wave-viewer-20260724-09d767ca`.
- Immediate rollback:
  `/home/flask/web-react/build-rollback-wave-viewer-20260724-84c91001
  -> build-wave-viewer-20260724-84c91001`.
- Visible authenticated Chrome run 1: complete correctness matrix PASS,
  console clean, no persistent Loading state, baseline restored.
- Visible authenticated Chrome run 2: complete correctness matrix PASS,
  console clean, no persistent Loading state, baseline restored.
- Both runs covered filter grammar and whitespace, invalid/incomplete recovery,
  rapid AI edits, range/AI intersections, sorting, universes, active-filter
  preservation, recurrence/lookbacks, PE+2, empty results, every table sort,
  large real wheel scrolling, beginning/middle/end/post-sort selections,
  rapid selections, long and short rows, viewer manual controls, viewer cycles,
  reverse date range, buy-and-hold, MFE/MAE, refresh clearing, and deep-link
  recurrence isolation.
- P-01 deployed run 1:
  `docs/testing/evidence/p01-postdeploy-final-run1-09d767ca.json`.
  Warm response-to-stable median 338 ms, max 472 ms; warm total median
  1,155 ms, max 1,202 ms; cold total 4,279 ms.
- P-01 deployed run 2:
  `docs/testing/evidence/p01-postdeploy-final-run2-09d767ca.json`.
  Warm response-to-stable median 478 ms, max 543 ms; warm total median
  833 ms, max 904 ms; cold total 4,062 ms.
- Both P-01 runs had zero console errors and zero missing targets.
- Final baseline for both runs: S&P 500 STOCKS, 10 years, 8 of 10, PE+2 off,
  empty filter, 419 opportunities, no viewer symbol, 2026-07-24, 30 days,
  10 viewer years, consecutive.
- WorkOS/auth configuration was not changed. `.180`, staging, production, TW1,
  secrets, customer data, billing, and DQ-01 were not touched.
