# TW-TASK-0025: Buy & Hold Across Time

- Status: in-progress
- Confidence: current selection verified in Dev browser; implementation pending
- Priority: P2, authorized investor historical comparison view
- Executor: Codex chat 01a15066-8f6d-7cd0-85bb-60db37f39af4
- Claim/update UTC: 2026-10-18T19:07:58.402739+00:00
- Authorization: Afshin approved phase-one Dev implementation, testing and activation. No production or staging change; no forecasts/ML/incomplete-window estimates.

## Goal, Scope and Acceptance
Add Analysis > Buy & Hold Across Time immediately after Buy & Hold. Dedicated responsive view compares companies and fixed calendar-year holding periods, plotting completed actual outcomes at daily historical purchase dates. Engine supplies total percentage gain and ending value of hypothetical $1,000. Explicit anniversary/session and price-adjustment conventions; stop each series at last fully observed exit. Preserve existing Buy & Hold and Years meaning.

## Executable Plan
1. Trace engine-owned returns, price adjustment and date resolution; reuse existing calculation and authorization helpers. Add bounded engine history endpoint only where needed.
2. Add dedicated React dialog/chart and distinct Holding period controls; pass engine values through unchanged, present loading/empty/error states and complete-period cutoff.
3. Test calculation/date boundaries, auth/validation and existing Buy & Hold behavior; build once with provenance. Verify actual Dev response and desktop/mobile rendering.
4. Under short Dev activation lock, refetch main, activate tested source/artifact with previous pointers retained, smoke test and push main without force; prove source/artifact parity.

## Evidence and Investigation
Current main at start d6a4fccdd7abca8071d2b45dacd54cd334d52924. Live Dev Analysis contains Compare Symbols, Compare Date Ranges, Buy & Hold, Exclude Current Range. Existing shortcut changes Jan-1 full-year seasonal baseline. Source Common.js:554 and SeasonalBarChart.js:2177.
TW-TASK-0024 index is stale: release manifest tw2-20261015-01/release.json status complete, manager released, updated 2026-10-16T03:05:08Z. No active release freeze remains.

## Acceptance and Regression Checks
Pending: engine ownership trace; leap day/non-session anniversary/completion cutoff; invalid symbols/horizons and access; multiple series and empty/error display; desktop and mobile; original shortcut unchanged.

## Implementation and Handoff
Branch codex/buy-hold-across-time-20261018; worktree /home/tradewave-worktrees/buy-hold-across-time-20261018. No code changes yet. No schema migration planned. Build and engine tests required. Prior Dev backend /home/tradewave-worktrees/tw2-20261015-01 and frontend /home/flask/web-react/releases/build-c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce (recheck at activation); rollback restores affected pointers and restarts affected service. Next: implement engine-backed contract and view.

## Environment Verification
Dev pending. Staging and production not deployed by this task.
