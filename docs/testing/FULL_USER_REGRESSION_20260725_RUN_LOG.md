# TradeWave Full User-Facing Regression Run Log — 2026-07-25

## Environment

- Dev host: `192.168.1.176` (`TW2`) only.
- User surface: `https://tw2-dev.trxstat.com`.
- Authoritative browser: current signed-in visible desktop Chrome session.
- Initial deploy target: `/home/flask/web-react/build-wave-viewer-20260724-09d767ca`.
- Initial JS bundle: `main.09d767ca.js`.
- Isolated worktree: `/home/tradewave-full-regression-20260725`.
- Branch: `codex/full-user-regression-20260725`.
- Baseline commit: `fada980588e3fca9ce56159dff01257289702a23`.

## Boundaries

- Never access or change `.180`, staging, or production.
- Do not use admin screens.
- Do not submit broker orders, calendar events, email/SMS, payments, subscriptions, lead forms, social posts, or other external side effects.
- Preserve WorkOS/auth configuration and the signed-in session.
- All mutable QA records use prefix `TW-QA-20260725` and are tracked in the companion ledger.

## Baseline

- `nginx`, `tradewave-web`, `tradewave-appserver`, `tradewave-apiserver`, `cloudflared`, `redis-server`, and `postgresql`: active.
- Web `/healthz`: database and application healthy.
- Visible Chrome opened `/app/` as an authenticated user.
- Initial defect candidate: opportunity row for ticker `BK` displayed price `NaN`; diagnosis pending.

## Execution log

| Time (ET) | Test/change | Result | Evidence/notes |
|---|---|---|---|
| 2026-07-25 | Scope frozen | PASS | User-facing only; disposable cleanup authorized; external effects/admin excluded; `.176` only |
| 2026-07-25 | Isolated worktree created | PASS | Clean branch from prior verified Wave Viewer commit |
| 2026-07-25 | Baseline services and visible browser | PASS with defect candidate | Authenticated Wave Viewer loaded; `BK` showed `NaN` price |

## Defect ledger

| Defect | Severity | Status | Reproduction | Root cause | Fix | Verification |
|---|---|---|---|---|---|---|
| TBD-01: `BK` opportunity price renders `NaN` | TBD | Investigating | Default S&P 500 opportunities on 2026-07-25 | Pending | Pending | Pending |

## Deployments

| Build | Commit | Previous target | Health | Pass 1 | Pass 2 | Rollback |
|---|---|---|---|---|---|---|
| Pending | Pending | `build-wave-viewer-20260724-09d767ca` | Pending | Pending | Pending | Pending |

## Cleanup and boundary proof

Completed. Every application record in the disposable ledger is marked `deleted` and `absence_verified`. Final Portfolio Manager names are the pre-existing `main` and `Notifications`; favorites were restored to the original six symbols; tooltip and short-date preferences were restored.

## Completion appendix

| Test/change | Result | Evidence/notes |
|---|---|---|
| Visible Chrome Wave Viewer passes | PASS with release findings | Core viewer, charts, Portfolio Manager, watchlists, Tara, preferences, navigation, reload, multi-tab, empty/error recovery |
| Defect repairs | PASS | Commits `fc5492db` through `929f8180` |
| Non-empty portfolio deletion race | REPAIRED | Immediate select/delete now shows `Delete Forever / Cancel`; disposable row/portfolio then removed |
| Retired `CTRA` cache entry | REPAIRED | S&P default count 448 → 447; `CTRA` filter returns no rows |
| Focused contracts | PASS | 14 passed |
| Full Python suite | PASS | 682 passed, 3 environmental/generated-doc skips |
| React suite | PASS | 7 suites, 61 tests |
| Normal production build | PASS | `main.266c0d79.js` |
| CI-strict build | FAIL / release blocker | Existing lint warnings become errors under `CI=true` |
| Responsive qualification | FAIL / release blocker | Clipping/unusable layout at 1024×768, 768×1024, and 390×844 desktop-UA viewports |
| Market-data refresh | FAIL / release blocker | Configured EODHD credential returns HTTP 401 |
| Watchlist CSV upload | BLOCKED | Chrome extension file-URL permission disabled |
| Trade Detail CSV download | INCONCLUSIVE | Correct blob URL/filename; no download event/file in controlled Chrome |
| Browser back/forward | BLOCKED | Browser-control channel timed out twice |
| External/admin mutations | NOT RUN by design | Scope exclusion |
| `.180`, staging, production | UNTOUCHED | All host commands and deploy paths targeted `.176` only |

Final release verdict and remediation sequence are in `FULL_USER_REGRESSION_20260725_REPORT.md`.
