# TW-BUG-0019: Mobile Wave Stats shows raw Sharpe Ratio2 row

- Status: open
- Confidence: reproduced in a real dev mobile browser
- Priority: P2 - a financial statistic appears with an internal label in the wrong table row
- First observed / last updated: 2026-09-27 17:31 UTC
- Executor/session/claim time: unassigned; documentation only
- Authorization: recording discovered bug only; no implementation or staging/production authorization

## User Impact and Reproduction

On TradeWave dev, open AAPL's 15-day Jan 15, 2026 study on a phone-sized Wave Stats view. The fourth **Wave Stats** row displays `Sharpe Ratio2 1.19` instead of the intended statistic/label for that slot. The same view's separate Wave Info now displays TWR 1.19 correctly, making the duplication visible. See the [320px dev screenshot](evidence/TW-BUG-0018/dev-mobile-320.png). The mobile Wave Stats component uses `filter={[4, 5, 9, 17]}` in `TradeDetailMobile.js`; its index appears to have drifted with the engine response order. The intended fourth metric needs confirmation against the prior UI and source before repair.

## Evidence and Investigation

The September 27 2026 screenshot used an authenticated dev capture-bot iPhone user agent at 320px, AAPL/S&P 500, Jan 15-29, 15 days, 10 consecutive years. This is separate from [TW-BUG-0018](TW-BUG-0018.md), which repaired the Wave Info table. No client-side calculation change is authorized or needed for a later presentation repair.

## Acceptance and Regression Checks

Confirm the intended mobile Wave Stats fourth row, select it by field name, and compare its displayed value to the same ChartData4 response. Check narrow phone widths and preserve Wave Info/entitlement behavior. Tests and live repair verification: not run because implementation is unclaimed.

## Implementation and Handoff

Repository `tradewave-tw2`, current main source `1a0d986047e715a0e475212780e989237804f99e`. No code branch, worktree, source commit, migration, build or activation for this bug. Next action: owner prioritizes/authorizes the independent mobile Wave Stats repair.

## Environment Verification

Dev: bug reproduced in screenshot above. Staging and production: not checked.

## History

- 2026-09-27: Codex recorded this independent visual defect while verifying TW-BUG-0018; no fix claimed.
