# Current TradeWave User-Facing Regression Status

Run: `TW-QA-20260725`

Status: completed on `.176`; repairs deployed and cleanup verified.

Authoritative surface: the signed-in visible Chrome session.

Current dev build: branch `codex/full-user-regression-20260725`, application code `929f8180`, browser asset `main.266c0d79.js`.

Verification: 14 focused contracts, 682 full Python tests, and 61 React tests passed. The normal production frontend build succeeded.

Release verdict: **not ready for staging or production**. Blocking items are the EODHD HTTP 401 refresh failure, responsive-layout failures at narrow/tablet/mobile widths, and the CI-strict frontend build failing on lint warnings. The CSV upload/download and browser-history evidence gaps must also be closed before production qualification.

Cleanup: complete. Only the pre-existing `main` and `Notifications` portfolios remain; all `TW-QA-20260725` records are absent and preferences are restored.

Full report: `FULL_USER_REGRESSION_20260725_REPORT.md`.
