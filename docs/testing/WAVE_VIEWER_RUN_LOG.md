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
