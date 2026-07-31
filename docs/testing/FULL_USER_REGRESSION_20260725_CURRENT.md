# Current TradeWave User-Facing Regression Status

Run: `TW-QA-20260725`

Status: completed on `.176`; repairs deployed and cleanup verified.

Authoritative surface: the signed-in visible Chrome session.

Current dev build: branch `codex/full-user-regression-20260725`, application code `929f8180`, browser asset `main.266c0d79.js`.

Verification: 14 focused contracts, 682 full Python tests, and 61 React tests passed. The normal production frontend build succeeded.

Corrected release verdict, 2026-07-28: **reasonable candidate for staging**. EODHD daily and realtime requests now return HTTP 200; the user verified real-phone behavior, CSV upload/download, and browser history. The earlier contrary observations were automation limitations. The strict `CI=true` build still promotes lint warnings to errors, but the normal production build passes; this matters only if strict CI is an actual release requirement.

Cleanup: complete. Only the pre-existing `main` and `Notifications` portfolios remain; all `TW-QA-20260725` records are absent and preferences are restored.

Full report: `FULL_USER_REGRESSION_20260725_REPORT.md`.
