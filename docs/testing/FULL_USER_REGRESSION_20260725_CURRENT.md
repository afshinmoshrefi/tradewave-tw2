# Current TradeWave User-Facing Regression Status

Run: `TW-QA-20260725`

Status: baseline inventory and traceability matrix in progress.

Authoritative surface: current signed-in visible Chrome.

Target boundary: `.176` only. `.180`, staging, production, admin screens, WorkOS changes, and real external side effects are excluded.

Current finding: the default opportunity table renders `NaN` for ticker `BK` price; diagnosis is in progress.

The run is not complete until the full matrix passes twice on the deployed immutable `.176` build, all disposable data is removed with absence verified, and the final release-readiness report is written.
