# TW-TASK-0014: Strategy Lab MCP capabilities (AI-run seasonal strategies anyone can copy)

- Status: in-progress (Phase 1 items 1-6 live on dev; item 5 widget display needs a real-host check; items 9, 11, 12 blocked on attorney sign-off)
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

Item 5 (one shared chart renderer), part 1:
- Afshin chose (2026-09-28) SMN's chart system as the one standard. New `twcharts/` package = SMN `blog/chartkit.py` (dev working copy sha256 a728bddc..., uncommitted Sep 23 edits on SMN 57055c2; differs from SMN prod b4e83def...) with Roboto fonts (Apache 2.0), buffer output, and `price_projection` removed. `mcpserver/chart_renderer.py` now draws the year-by-year bars (excursion needles) and the seasonal path through it, labeled with each chart's own claim; short cards use the chart system's price convention; PE slices are named, not called consecutive. `requirements-api.txt` adds matplotlib 3.10.9 (installed in dev `/home/flask/venv-api`; pip freeze before/after in the snapshot folder).
- Tests: `tests/test_twcharts.py` (4) and the updated `tests/test_mcp_chart_renderer.py`. Full suite 1509 passed; MCP 60 passed. Rendered SPY 2026-09-27/295d midterm charts inspected visually: they match the SMN article look.
- FINDING: over the real MCP transport neither `analyze_symbol` nor `whats_seasonal_now` returns image blocks, before or after this change. `analyze_symbol` (and scans) return an MCP Apps widget (`mcpserver/pattern_widget.html`) that draws its own SVG charts client-side from structuredContent; the PNG path (`_rich_lead`) is only used by `whats_seasonal_now`, whose decision-view cards carry no chart data. So part 1 has no visible effect yet. Part 2 (owner decision pending): send the shared-system PNGs with analyze/compare/basket results and/or make the widget show them.
- Activated under the lock; release gate PASS (p95 8.7 s).

Item 5 part 2 (owner chose option A, 2026-09-28):
- `analyze_symbol` renders the twcharts images off the event loop (`asyncio.to_thread`) and sends them as base64 PNGs in the result `_meta["tradewave/charts"]` (kinds `year_bars`, `seasonal_path`, with each chart's alt text), which hosts pass to the embedded app, not the model; content stays text-only. The widget (`pattern_widget.html`) shows those images and falls back to its built-in SVG charts when absent or when an image fails to load. Template URI moved to `pattern-evidence-v4`; v3 and v2 stay served for cached connectors.
- Tests: 2 new MCP tests (images only in `_meta`, never in content or structuredContent; widget reads `_meta`/`toolResponseMetadata` with an error fallback); widget-template tests updated to v4/v3/v2. MCP 62 passed; full suite 1509 passed; widget script `node --check` OK.
- Live dev over the real MCP transport: `analyze_symbol` SPY 2026-09-27/295d midterm returns text-only content plus `_meta` charts (year_bars 68,071 bytes, seasonal_path 89,815 bytes) and advertises `ui://tradewave/pattern-evidence-v4.html`. Compare and basket smokes unchanged.
- NOT verified: the widget actually displaying the images inside ChatGPT and Claude (needs a signed-in host session with the dev connector). The fallback keeps the old charts if a host blocks data: images.
- Release gate: first run failed load (44.5% errors, all `/v1/scan` 503 with the 101-byte `scan_busy` body between 00:06:23 and 00:06:48 UTC); immediate re-run PASS (p95 6.6 s, 0% errors). Cause: the scan cache TTL is 120 s and waiters give up after 12 s, so a gate run that finds a cold cache while the appserver is busy (here, right after this item's compare/basket smokes) returns the designed retryable 503. `/v1/scan` is unchanged by this task. Recorded as a separate observation: the load gate is sensitive to a cold scan cache.

Item 6 (from-today mode):
- `analyze` gains `timing=next|best` (default next): the best setup whose entry is today or later, or within the card's 3-day entry window; when the top-Sharpe slice has none, the FULL detected per-symbol list (same detection band) is fetched without enrichment and only its top 5 upcoming setups are refreshed from completed evidence and ranked by edge; if nothing lies ahead, the year's best is kept with `next_occurrence` (same month-day next year). `timing=best` keeps the old behavior. Table view adds `next_entry_date`. MCP `analyze_symbol` exposes `timing`; compare without a window inherits the default. `api/MCP_TOOLS.md` updated.
- Tests: 6 route/helper tests, 1 MCP test. Full suite 1523 passed; MCP 63 passed.
- Live dev, Big 7 unpinned (before -> after): every symbol moved from a passed May-July window to one ahead: AAPL Nov 9 (358d, 9/9, avg +30.7%), MSFT Oct 10 (308d, 9/10, +28.3%), GOOGL Dec 6, AMZN Dec 19, NVDA Dec 17, META Nov 17, TSLA Oct 21 (83d, 9/10, +31.6%). `timing=best` still returns the old windows. Compare, basket and MCP chart smokes unchanged. 14 cold analyze calls took 16.6 s.
- Activated under the dev lock (two releases in one lock window, each with its own snapshot folder); release gate PASS (p95 11.8 s).

Process note: items 1-3 were activated before this session loaded the repository's release rules; the dev activation lock was not taken for those activations and main was not advanced after each one. Corrected at 21:10 UTC: lock acquired, main fast-forwarded to the live candidate, parity proven, lock released.

- Finding for item 20: ML is only requested for 10-90 day windows within 5 days of entry (`_ml_unavailability_note`), so long holds never get ML - by design, not an outage. Still to check: why short windows also showed null.

## Implementation and Handoff

Branch `claude/strategy-lab-p1-20260928` pushed to GitHub; item 1 commit `bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (changes `apiserver/routes.py`, `tests/test_apiserver_endpoints.py`). Root cause: `analyze_symbol` validated every unpinned request against the per-symbol detection band, which hard-blocks markets without that grid, so its existing scan fallback was unreachable. `compare_opportunities` calls `/v1/analyze` per symbol and inherits the fix.

Dev activation: immutable release worktree `/home/flask/.tw2-releases/bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (only `apiserver/routes.py` differs from the prior release among apiserver/mcpserver/appserver Python files); `/home/flask/.tw2-app-current` repointed; apiserver and mcpserver restarted; appserver not restarted (backend code identical). Prior target `/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`.

Safety: owner VM snapshot taken before activation; snapshot folder `/root/tradewave-snapshots/strategy-lab-p1-dev-20260928T204338Z` on dev (prior target and SHA, unit files and drop-ins, service state, full prior backend code archive, runtime file hashes, before/after checks) with `rollback.sh` and `rollforward.sh`.

Item 2 commit `77978f2e1fff5475909b423cb814b492e7dc03fc`, release `/home/flask/.tw2-releases/77978f2e1fff5475909b423cb814b492e7dc03fc`; its snapshot folder `/root/tradewave-snapshots/strategy-lab-p1-dev-item2-20260928T205546Z` (rollback returns to the item 1 release `bb20f11c`; the first folder returns to the original `9b02f007`).

Item 3 commits `8cba9627eacdab6c1dd1f531f0d08e17b02c3111` and `dcda9a8d8763691d68bc9c44c6e01654768df989`; live release `/home/flask/.tw2-releases/dcda9a8d8763691d68bc9c44c6e01654768df989`; snapshot folders `strategy-lab-p1-dev-item3-20260928T210514Z` and `strategy-lab-p1-dev-item3b-20260928T210640Z`.

Item 4 commit `67d96a6a85d3ce76497eb4c42cdcad56b3a8d99d`, release `/home/flask/.tw2-releases/67d96a6a85d3ce76497eb4c42cdcad56b3a8d99d`, snapshot folder `strategy-lab-p1-dev-item4-20260928T221601Z` (rollback returns to `dcda9a8d`).

Item 5 part 1 commit `b376e47824fd665c50e88f3e160e6f2b97a692a9`, release `/home/flask/.tw2-releases/b376e47824fd665c50e88f3e160e6f2b97a692a9`, snapshot folder `strategy-lab-p1-dev-item5-20260928T222743Z` (rollback returns to `67d96a6a`; matplotlib stays installed, unused by the prior release).

Item 5 part 2 commit `1f21742d005c6f40e628a040e6ae006ff19f46ce`, release `/home/flask/.tw2-releases/1f21742d005c6f40e628a040e6ae006ff19f46ce`, snapshot folder `strategy-lab-p1-dev-item5b-20260929T000533Z`.

Item 6 commits `9d804d5ece5a631c68aa4fade9933459072b1e60` and `a8e6239ce15dee49cd450b2be4c8ac83d4f1391f` (branch `claude/mcp-from-today-20260929`, based on main `469d600`), live release `/home/flask/.tw2-releases/a8e6239ce15dee49cd450b2be4c8ac83d4f1391f`, snapshot folders `strategy-lab-p1-dev-item6-20260929T004906Z` (rollback to `469d600c`) and `strategy-lab-p1-dev-item6b-20260929T005130Z` (rollback to `9d804d5e`).

Phase 1 complete on dev. Next: owner check of the widget images in ChatGPT/Claude with the dev connector; knowledge-base update; staging only on request; Phase 2 items 7, 8, 10 (not blocked) and Phase 3 when authorized.

## Environment Verification

Dev: verified for Phase 1 items 1-6 (widget display in real hosts pending) - 2026-09-29 00:55 UTC, release `a8e6239c`, Claude session `c7bd49c6`, direct gateway before/after checks plus MCP release gate PASS. Staging: not checked. Production: not checked.

## History

- 2026-09-28 20:30 UTC, Claude Code session `c7bd49c6`: plan agreed with Afshin over the conversation; task opened and Phase 1 claimed. Next: item 1.
- 2026-09-28 20:47 UTC, Claude session `c7bd49c6`: item 1 implemented, tested, activated on dev with snapshot folder + owner VM snapshot; release gate blocked by dev clock skew. Next: owner decision on clock, then run gate.
- 2026-09-28 20:58 UTC, Claude session `c7bd49c6`: dev clock stepped (owner approved); item 1 gate PASS; item 2 implemented, activated with its own snapshot folder, gate PASS. Next: item 3.
- 2026-09-28 21:10 UTC, Claude session `c7bd49c6`: item 3 live and gated; lock taken, main advanced to the live candidate, lock released. Next: item 4.
- 2026-09-28 22:20 UTC, Claude session `c7bd49c6`: item 4 paused on the 2026-06-08 educational-only policy; Afshin chose the weights-only basket reframe (A); items 9/11/12 marked blocked on attorney sign-off; item 4 live under lock, gate PASS, main advanced. Next: item 5.
- 2026-09-28 22:35 UTC, Claude session `c7bd49c6`: item 5 part 1 live under lock, gate PASS; found MCP charts are drawn by the Apps widget, not PNG images. Awaiting owner decision on part 2.
- 2026-09-29 00:10 UTC, Claude session `c7bd49c6`: item 5 part 2 live under lock; gate PASS on re-run after a cold-cache scan_busy burst. Next: owner host check, item 6.
- 2026-09-29 00:55 UTC, Claude session `c7bd49c6`: item 6 live under lock, gate PASS, main advanced. Phase 1 complete on dev. (A homepage overlap with session "100 year pattern home page update" at 00:34 was resolved in its favor; TW-BUG-0023 is a duplicate on its own branch.)
