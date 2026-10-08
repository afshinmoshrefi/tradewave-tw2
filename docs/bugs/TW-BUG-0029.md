# TW-BUG-0029: Wave Viewer direction indicator sits low under its heading

- Status: verified on live dev
- Priority: P3
- Executor/session: Codex `/root/toolbar_titles`, 2026-10-08 UTC
- Branch/worktree: `codex/direction-square-align-20261008` at `/home/tradewave-worktrees/direction-square-align-20261008`, based on `a466494c76b47bf5ca931cb02d95095314a70bc3`.
- Authorization: Afshin requested the bar-chart toolbar's colored direction rectangle and Help icon be raised to align with adjacent controls, and the rectangle's visible full/compact heading be `Bias`. Routine dev-only activation authorized; staging/production excluded.
- Acceptance: desktop title-on rectangle and Help icon align vertically with adjacent controls, title reads Bias at full/compact widths, title/tooltip routing and title-off/mobile behavior remain unchanged, and long/short color semantics remain engine-owned.
- Implementation: `SeasonalBarChart.js` renames only this indicator's full/compact heading and accessible name to `Bias`, and raises only its colored square and the Help SVG by 4px when desktop toolbar titles are visible. The title, tooltip trigger, long/short color, title-off and mobile layout are unchanged.
- Code/main SHA: `39a01a03d8bbb837cf36b36c55e8376db1620352`; clean task/integration worktrees. React release build passed with existing lint warnings and stamped the SHA. Live dev frontend `/home/flask/web-react/releases/build-39a01a03d8bbb837cf36b36c55e8376db1620352` serves `main.ff0730eb.js`; rollback pointer `build-cc20d0d3fabcee82ac93841f47223b03f33cc0cf` remains available.
- Live verification (2026-10-08): authenticated capture-bot Chromium through real nginx and API loaded an AAPL pattern. At 1920px (wide heading mode), Bias square/Help centers were 107/106.5px versus neighboring input center 105.85px. At 1280px (narrow mode), they were 102/101.5px versus input center 101.41px. Bias appeared at both widths and Help opened its panel. With titles off, neither offset applied; Pixel 5 remained title-free and unchanged. Final screenshot: `docs/bugs/evidence/TW-BUG-0029/live-narrow.png`. Staging and production not touched.
- Main/frontend parity: nonforced main push, served bundle stamp and exact React tree agree. Pre-existing unrelated backend source drift (active `e9499d99` versus main webinar/config changes) remains; this frontend-only fix did not restart backend services. Activation lock released. No staging qualification claim.

