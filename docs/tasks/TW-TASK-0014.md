# TW-TASK-0014: Strategy Lab MCP capabilities (AI-run seasonal strategies anyone can copy)

- Status: in-progress (items 1-4 verified on dev; items 5-6 next; items 9, 11, 12 blocked on attorney sign-off)
- Confidence: reproduced (each gap below was observed through the live production MCP connector on 2026-09-28)
- Priority: P2 - blocks the public Strategy Lab video series and the "connect TradeWave to Claude or ChatGPT and run your own idea" user flow
- First observed / last updated: 2026-09-28 20:30 UTC
- Executor/session/claim time: Claude Code (Opus 5.5), session `c7bd49c6-d749-4f1e-8339-9085bf677acd`, claimed 2026-09-28 20:30 UTC. Work branch `claude/strategy-lab-p1-20260928`; dev worktree `/home/tradewave-worktrees/strategy-lab-p1-20260928` (to be created).
- Authorization: Afshin approved on 2026-09-28 the plan below and Phase 1 implementation with verified dev completion. Phases 2 and 3 are planned only. Staging and production need a separate request.

## Goal, Scope and Acceptance

Product goal: a public "Strategy Lab" of about 4 (maximum 6) AI-managed paper strategies built only from TradeWave research, plus a process viewers can repeat by connecting TradeWave MCP to Claude or ChatGPT. The AI does the work; the user makes two decisions: which risk (Compare) and whether the worst historical year is acceptable (Portfolio Scenarios). Rule kept: TradeWave generates the statistics; AI reads and explains them.

Starting lineup: (1) 100-Year Pattern - SPY, Sep 27 to Jul 18, fixed rule; (2) Steady Seasonal - long-history, lower-risk stocks; (3) Big Swing - short-history, high-return names; (4) Seasonal Swing Trader - 10 to 120 day trades. Later: Safety (gold/bonds) and a viewer "Your List" strategy.

User flow: Idea -> Find -> Compare (same window) -> Research (AI veto only) -> Scenario test vs SPY -> Report and track.

### Phase 1 (authorized): launch
1. ETFs and indices (SPY, GLD, TLT, SPX) work in `analyze_symbol` and `compare_opportunities`.
2. Buy-and-hold benchmark in results (window cumulative vs the symbol's buy-and-hold).
3. Same-window compare: several symbols on one entry date, hold and year sample, with chart.
4. Basket scenarios as an MCP tool: the app's Portfolio Scenarios math for a HYPOTHETICAL basket of symbols with percentage weights (horizons 30/60/90/EOY/custom; samples 1-50 years or PE+N years). Reframed on 2026-09-28 by Afshin (option A) to stay inside the 2026-06-08 educational-only policy in `api/MCP_INTEGRATION_ROADMAP.md`: weights only, no holdings, share counts, dollars, cost basis or P&L; descriptive output only.
5. One shared chart renderer: MCP images come from the same renderer as the app and SMN (`site/lib/svg_wave_chart.py`), not the separate `mcpserver/chart_renderer.py`. MCP returns both the chart and the data.
6. "From today" mode: compare/analyze return the next valid window, not a window that already passed.

### Phase 2 (planned): dashboards
7. Create-report tool (server-built from TradeWave templates; link and PDF; AI writes only the explanation).
8. Save and track a strategy.
9. BLOCKED - attorney sign-off required (reads real holdings; 2026-06-08 policy). "Since I bought" scenario mode (per-holding purchase dates).
10. Day-by-day path per past year, to draw the historical band behind live value.
11. BLOCKED for personal holdings - attorney sign-off required. Personal strategy dashboards in the app. The public Strategy Lab dashboard (Afshin's own paper strategies, identical for every viewer) is not blocked.
12. BLOCKED - attorney sign-off required (holdings plus take-profit/stop directives). "Check my portfolio" MCP tool (live value vs 10y / 20y / last 5 midterm-year band, plain sentence, alerts above best / below worst year).

### Phase 3 (planned): extras
13. Exit-rule test (profit target and trailing stop, result per past year; needs when MFE/MAE happened).
14. Earnings dates in MCP results and an in-window earnings flag (data exists: `appserver.get_earnings_dates`).
15. Earnings-anchored pattern test (X days before/after earnings each year).
16. Ex-dividend dates (check current price provider first; no new vendor without measured need).
17. Year map for a user's list (strong and weak windows through the year).
18. Risk filter (maximum historical adverse excursion) and complete scan lists (today about 40-50 results).
19. Clear "not enough history" answer for new listings (example: SPCX, listed 2026-06-12).
20. ML scores return null on every call observed on 2026-09-28 - investigate.

Acceptance for Phase 1: each item reproduces its original failure below, then passes through the real MCP transport on dev in both a Claude-style and ChatGPT-style client path; existing tool behavior for stocks is unchanged.

## Evidence and Investigation

Observed 2026-09-28 through the production MCP connector:
- `analyze_symbol` GLD and TLT: "Per-symbol seasonal pattern detection is not available for ETFs." The low-level `get_opportunity_chart` works for SPY (market 11, `pe_cycle=pe2`, years 8): 8/8 midterm years since 1994, average +19.2%, worst in-window drawdown -19.1% (2018).
- `compare_opportunities` AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA: each card is that symbol's best window of the year; all 7 report "window has passed for this cycle" (May to July entries).
- `find_best_opportunities` shows at most about 40-50 results ("Only the top 50 candidates (by Sharpe) were fully evaluated").
- `analyze_symbol` full view (SPGI, 2026-09-28, 308 days, 20y) has cumulative return but no buy-and-hold comparison.
- `ml_win_prob` null on every card; SPGI card says "ML score is currently unavailable for this setup."
- Portfolio Scenarios exists only in the web app: `appserver/appserver/portfolio_scenarios.py`, `web-react/src/components/PortfolioScenarios.js`. Symbol comparison exists only in Wave Viewer (`SymbolComparisonDialog`, `web-react/src/components/SeasonalBarChart.js`).

## Acceptance and Regression Checks

Item 1 (ETF/index analysis):
- New tests in `tests/test_apiserver_endpoints.py`: ETF analysis uses the market scan (never the per-symbol grid); ETF with no setup today returns 404 that explains `entry_date`/`days_out`/`period`; stocks still use the per-symbol grid. Full suite on dev worktree: 1480 passed, 5 skipped (missing `mcp` module, ungenerated quickstart, deferred React branch), 0 failed.
- Live dev gateway (127.0.0.1:8088, stored dev release API key), before -> after activation:
  - `/v1/analyze/SPY?market=11`: 400 "Per-symbol ... not available for ETFs" -> 200 "SPY long - enter ~Sep 28, hold 320d. Won 9/10 years, avg +16.4%, Sharpe 1.2."
  - `/v1/analyze/GLD?market=11`: 400 -> 200 "GLD long - enter ~Sep 28, hold 248d. Won 9/10 years, avg +12.1%, Sharpe 0.9."
  - Pinned SPY 2026-09-28/294d/20y, AAPL and SPGI (market 2): identical output before and after.
- Release gate: first attempt failed before any request with `ImmatureSignatureError (iat)`: dev clock was 64.6 s behind (chrony "Not synchronised", conflicting sources). With owner approval, `chronyc makestep` at 20:48 UTC (state saved in `clock.before`); chrony then "Normal". Next gate run failed only the load p95 (42.1 s, 0% errors) right after the restart; the immediate re-run passed (p95 5.6 s): PASS API, daily-pick, MCP BYOK, OAuth, load, storm-breaker. The load gate calls `/v1/scan`, which this change does not touch; the cold-cache p95 after a restart is recorded as a separate observation.

Item 2 (buy-and-hold benchmark):
- `cards.buy_hold_window` (app canonical Jan 1 - Jan 1) and `cards.buy_hold_benchmark` (same completed years by label; Stats Table compounding); analyze adds `card.benchmark` and `beats_buy_hold` in table view; a failed Buy & Hold fetch leaves the card unchanged. New tests in `tests/test_cards.py` and `tests/test_apiserver_endpoints.py`. Full suite: 1485 passed, 5 skipped, 0 failed.
- Live dev: SPY 2026-09-27/295d, last 8 midterm years: window +222.18% vs buy-and-hold +16.91% cumulative over 7 shared years (avg 18.58% vs 3.73%; window better in 6 of 7). SPGI 2026-09-28/308d/20y: +2339.63% vs +1308.36% (window better in 10 of 20 years). Stock and ETF outputs from item 1 unchanged.
- Release gate after activation: PASS on first run (p95 12.4 s, 0% errors).
Item 3 (same-window compare):
- New `apiserver/compare.py` mirrors the app's Symbol Comparison (`web-react/src/components/analysisReportData.js`): direction-aware yearly results, restriction to the completed years all symbols share (latest N), the app's metrics (profitable = return >= 0; Sharpe with 4% risk-free scaled by days; compounded cumulative), minimum 5 shared years, same-years buy-and-hold per symbol, deterministic findings that name every tied leader and explain when a newer symbol shortens the shared history. New route `GET /v1/compare`; MCP `compare_opportunities` gains a same-window mode (entry_date/days_out or period, years, pe_cycle, direction) and is unchanged without it.
- Tests: `tests/test_compare.py` (6), 3 route tests, 1 MCP test. Full suite 1496 passed, 5 skipped; MCP suite (venv-api) 57 passed.
- Live dev: NVDA/WMT/PG, 2026-09-28/294d, midterm years: 6 shared years (NVDA has 6, WMT 13, PG 15); NVDA avg +76.61%, deepest drop -55.67%; PG avg +11.98%, worst year -0.43%; "NVDA and PG were profitable most often, in 5 of 6 years." Big 7, 20y: 13 shared years (META). SPY/GLD/TLT Q4, 15y: SPY +5.82% avg, 13 of 15 profitable. First live run exposed a tie named as a single leader; fixed in `dcda9a8`.
- Release gate after activation: PASS (p95 13.6 s, 0% errors).

Item 4 (basket scenarios):
- New `apiserver/scenarios.py` (the app's `build_horizon` math in percentages: same start date and horizon, completed years shared by all symbols, weighted yearly sum, best/worst year, up/flat/down counts, per-symbol contribution, optional same-years benchmark, deterministic summary). `POST /v1/basket-scenarios`; flagship MCP tool `basket_scenarios` (inventory now 18 = 7 flagship + 11 primitives; tests, checklist, API docs generators, `api/MCP_TOOLS.md`, `api/openapi.yaml`, ecosystem doc updated). Gateway `_chart_data` can request `report_completed_years` like the app's scenarios and verifies the echo.
- Policy guards: entries accept only symbol/weight_pct/market/direction (amount, shares, cost_basis -> 400); a test asserts no money or holding field appears in output.
- Tests: `tests/test_scenarios.py` (4), 5 route tests, 1 MCP test. Full suite 1505 passed, 5 skipped; MCP 58 + transport 2 passed (venv-api lacks `yaml`, so `test_consistency.py` runs in the main venv suite).
- Live dev: 40% PG / 30% WMT / 30% NVDA, 2026-09-28 to 2027-07-18, midterm years, benchmark SPY: 6 shared years (NVDA limits), average +30.5%, middle +14.7%, rose 6 of 6, worst 2014 +1.5%, best 2022 +93.3%; SPY +15.6% average, basket better in 3 of 6. 50% SPGI / 50% CSX, 20y, 30/60/90/eoy horizons all returned 20 shared years. `{"amount": 5000}` refused with 400. Items 1-3 smoke output unchanged. Not run: a side-by-side parity check against the app's Portfolio Scenarios UI (needs a signed-in app session).
- Activated under the dev activation lock; release gate PASS (p95 11.3 s, 0% errors).

Process note: items 1-3 were activated before this session loaded the repository's release rules; the dev activation lock was not taken for those activations and main was not advanced after each one. Corrected at 21:10 UTC: lock acquired, main fast-forwarded to the live candidate, parity proven, lock released.

- Finding for item 20: ML is only requested for 10-90 day windows within 5 days of entry (`_ml_unavailability_note`), so long holds never get ML - by design, not an outage. Still to check: why short windows also showed null.

## Implementation and Handoff

Branch `claude/strategy-lab-p1-20260928` pushed to GitHub; item 1 commit `bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (changes `apiserver/routes.py`, `tests/test_apiserver_endpoints.py`). Root cause: `analyze_symbol` validated every unpinned request against the per-symbol detection band, which hard-blocks markets without that grid, so its existing scan fallback was unreachable. `compare_opportunities` calls `/v1/analyze` per symbol and inherits the fix.

Dev activation: immutable release worktree `/home/flask/.tw2-releases/bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (only `apiserver/routes.py` differs from the prior release among apiserver/mcpserver/appserver Python files); `/home/flask/.tw2-app-current` repointed; apiserver and mcpserver restarted; appserver not restarted (backend code identical). Prior target `/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`.

Safety: owner VM snapshot taken before activation; snapshot folder `/root/tradewave-snapshots/strategy-lab-p1-dev-20260928T204338Z` on dev (prior target and SHA, unit files and drop-ins, service state, full prior backend code archive, runtime file hashes, before/after checks) with `rollback.sh` and `rollforward.sh`.

Item 2 commit `77978f2e1fff5475909b423cb814b492e7dc03fc`, release `/home/flask/.tw2-releases/77978f2e1fff5475909b423cb814b492e7dc03fc`; its snapshot folder `/root/tradewave-snapshots/strategy-lab-p1-dev-item2-20260928T205546Z` (rollback returns to the item 1 release `bb20f11c`; the first folder returns to the original `9b02f007`).

Item 3 commits `8cba9627eacdab6c1dd1f531f0d08e17b02c3111` and `dcda9a8d8763691d68bc9c44c6e01654768df989`; live release `/home/flask/.tw2-releases/dcda9a8d8763691d68bc9c44c6e01654768df989`; snapshot folders `strategy-lab-p1-dev-item3-20260928T210514Z` and `strategy-lab-p1-dev-item3b-20260928T210640Z`.

Item 4 commit `67d96a6a85d3ce76497eb4c42cdcad56b3a8d99d`, release `/home/flask/.tw2-releases/67d96a6a85d3ce76497eb4c42cdcad56b3a8d99d`, snapshot folder `strategy-lab-p1-dev-item4-20260928T221601Z` (rollback returns to `dcda9a8d`).

Next: item 5 (one shared chart renderer).

## Environment Verification

Dev: verified for items 1-4 - 2026-09-28 22:20 UTC, release `67d96a6a`, Claude session `c7bd49c6`, direct gateway before/after checks plus MCP release gate PASS. Staging: not checked. Production: not checked.

## History

- 2026-09-28 20:30 UTC, Claude Code session `c7bd49c6`: plan agreed with Afshin over the conversation; task opened and Phase 1 claimed. Next: item 1.
- 2026-09-28 20:47 UTC, Claude session `c7bd49c6`: item 1 implemented, tested, activated on dev with snapshot folder + owner VM snapshot; release gate blocked by dev clock skew. Next: owner decision on clock, then run gate.
- 2026-09-28 20:58 UTC, Claude session `c7bd49c6`: dev clock stepped (owner approved); item 1 gate PASS; item 2 implemented, activated with its own snapshot folder, gate PASS. Next: item 3.
- 2026-09-28 21:10 UTC, Claude session `c7bd49c6`: item 3 live and gated; lock taken, main advanced to the live candidate, lock released. Next: item 4.
- 2026-09-28 22:20 UTC, Claude session `c7bd49c6`: item 4 paused on the 2026-06-08 educational-only policy; Afshin chose the weights-only basket reframe (A); items 9/11/12 marked blocked on attorney sign-off; item 4 live under lock, gate PASS, main advanced. Next: item 5.
