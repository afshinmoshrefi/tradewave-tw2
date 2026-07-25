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

Pending. Completion requires every ledger item to be marked `deleted` and `absence_verified`, plus a final host/deployment audit proving only `.176` was touched.

