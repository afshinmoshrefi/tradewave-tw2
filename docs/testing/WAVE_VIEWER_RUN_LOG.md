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
