# TW-TASK-0014: Strategy Lab MCP capabilities (AI-run seasonal strategies anyone can copy)

- Status: in-progress (item 1 deployed on dev; release gate blocked by dev clock)
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
4. Portfolio Scenarios as an MCP tool (horizons 30/60/90/EOY/custom; samples 10-50 years or last 10 PE+N years).
5. One shared chart renderer: MCP images come from the same renderer as the app and SMN (`site/lib/svg_wave_chart.py`), not the separate `mcpserver/chart_renderer.py`. MCP returns both the chart and the data.
6. "From today" mode: compare/analyze return the next valid window, not a window that already passed.

### Phase 2 (planned): dashboards
7. Create-report tool (server-built from TradeWave templates; link and PDF; AI writes only the explanation).
8. Save and track a strategy.
9. "Since I bought" scenario mode (per-holding purchase dates).
10. Day-by-day path per past year, to draw the historical band behind live value.
11. Personal strategy dashboards in the app (same component powers the public challenge dashboard).
12. "Check my portfolio" MCP tool (live value vs 10y / 20y / last 5 midterm-year band, plain sentence, alerts above best / below worst year).

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
- Not yet run: `ops/dev_mcp_release_auth.py run-gate` (MCP transport + load). It failed before any request with `ImmatureSignatureError (iat)`: the dev host clock is about 64.6 s behind; chrony reports "Leap status: Not synchronised" with conflicting sources. Not caused by this change.

## Implementation and Handoff

Branch `claude/strategy-lab-p1-20260928` pushed to GitHub; item 1 commit `bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (changes `apiserver/routes.py`, `tests/test_apiserver_endpoints.py`). Root cause: `analyze_symbol` validated every unpinned request against the per-symbol detection band, which hard-blocks markets without that grid, so its existing scan fallback was unreachable. `compare_opportunities` calls `/v1/analyze` per symbol and inherits the fix.

Dev activation: immutable release worktree `/home/flask/.tw2-releases/bb20f11c5422417c1623893028ea2e1fd8a7ee5b` (only `apiserver/routes.py` differs from the prior release among apiserver/mcpserver/appserver Python files); `/home/flask/.tw2-app-current` repointed; apiserver and mcpserver restarted; appserver not restarted (backend code identical). Prior target `/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`.

Safety: owner VM snapshot taken before activation; snapshot folder `/root/tradewave-snapshots/strategy-lab-p1-dev-20260928T204338Z` on dev (prior target and SHA, unit files and drop-ins, service state, full prior backend code archive, runtime file hashes, before/after checks) with `rollback.sh` and `rollforward.sh`.

Next: owner decision on the dev clock so the MCP release gate can run; then items 2-6.

## Environment Verification

Dev: deployed/unverified for item 1 - 2026-09-28 20:45 UTC, `bb20f11c`, Claude session `c7bd49c6`, direct gateway checks passed; MCP release gate pending (dev clock). Staging: not checked. Production: not checked.

## History

- 2026-09-28 20:30 UTC, Claude Code session `c7bd49c6`: plan agreed with Afshin over the conversation; task opened and Phase 1 claimed. Next: item 1.
- 2026-09-28 20:47 UTC, Claude session `c7bd49c6`: item 1 implemented, tested, activated on dev with snapshot folder + owner VM snapshot; release gate blocked by dev clock skew. Next: owner decision on clock, then run gate.
