# TW-TASK-0025: Buy & Hold Across Time

- Status: in-progress (historical view verified; approved zoom follow-up)
- Confidence: implemented and reproduced in live Dev browser and API
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

## Implementation milestone
Engine implementation and existing ChartData4 regression checks: 29 passed. Real stored
MSFT/AAPL/WMT x 4/6/10-year series calculated in 0.755s; all last exits <= October16,
2026, with independent holding-period cutoffs. UI implementation is on sibling task
branch, integration pending. Confirmed EODHD dividend adjustment convention, but stored
history consistency needs separate event audit (TW-BUG-0036); label this explicitly.

## Live candidate verification
Initial candidate eff2d97e: authenticated API nine real series passed in1.365s;
Explorer date-lock403 and invalid-token401 verified. Desktop and390px mobile charts,
three companies, dollar/percentage switch and per-series cutoffs rendered correctly.
Browser inspection found automatic linear ticks extending to2033 beyond last2020
purchase. Rolled back candidate pointers, released lock, and bounded presentation axis
to actual first/last plotted purchase dates; no engine/data change. Rebuild pending.

## Final Dev acceptance
Verified 2026-10-18T19:27:12.474766+00:00 source26ae2d68f7fef091f0fb131b4d26b9ade7ebf25a, bundle
main.817e110a.js.29 Python tests (including unchanged ChartData4 results),4 React tests,
optimized build, authenticated live nine-series response, Explorer403 and invalid-token401
passed. Desktop1440x1000 and mobile390x844 (viewport emulation) passed; original Buy & Hold
still selects Jan1 and366 days. No production/staging writes or data repairs.
Initial visual checks caused two focused presentation corrections (axis bounds and mobile
tooltip wrapping); prior Dev pointers were restored and lock released during rebuilding.
Every point remains engine-owned, no forecasts or incomplete holds.

Receipts: [API](evidence/TW-TASK-0025-live-api.json),
[verification](evidence/TW-TASK-0025-verification.json),
[desktop](evidence/TW-TASK-0025-desktop.jpg), [mobile](evidence/TW-TASK-0025-mobile.jpg).
Backend pointer is this task worktree. Frontend is
/home/flask/web-react/releases/build-26ae2d68f7fef091f0fb131b4d26b9ade7ebf25a.
Rollback script retains previous backend/frontend and restarts only appserver;
no web-runtime or schema changes. Final documentation commit is discoverable using
git log -1 -- docs/tasks/TW-TASK-0025.md; its application tree equals built source.
Next: Afshin can try Analysis > Buy & Hold Across Time on Dev. Separately investigate
TW-BUG-0036 before promising fully reconciled dividend-reinvestment total return.

## Approved zoom follow-up
Claim 2026-10-18T19:53:18.735685+00:00 by Codex chat01a15066-8f6d-7cd0-85bb-60db37f39af4.
Afshin approved overview range handles, dragging selected window to pan, mouse drag zoom
on the main chart, visible-data Y rescale and Reset view. Dev only. Companies, horizons,
engine numbers, date conventions and dividend disclosure must not change.
Branch codex/buy-hold-zoom-20261018; worktree /home/tradewave-worktrees/buy-hold-zoom-20261018.
Plan: add presentation-only range helpers and accessible pointer/touch overview; wire
main chart mouse selection and visible-data scaling; focused interaction/value-preservation
tests; one affected build; short locked frontend activation, desktop/mobile live verification,
main/app-tree parity and receipt. No backend/API/schema change. Rollback previous frontend
build26ae2d68f7fef091f0fb131b4d26b9ade7ebf25a; preserve active backend.
Acceptance: zoom1995-2008 approximately; resize both handles; pan width unchanged;
visible peaks re-fit vertically; reset full history; tooltip values remain raw engine values;
selected companies/hold periods retained; touch handles usable without scrolling page.
