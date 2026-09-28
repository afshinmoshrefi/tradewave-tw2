# TW-TASK-0014: Strategy Lab MCP capabilities (AI-run seasonal strategies anyone can copy)

- Status: in-progress
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

Pending. Tests not run yet.

## Implementation and Handoff

Pending. Next concrete action: create the dev worktree and trace where the ETF rejection is raised (gateway vs MCP layer), then implement item 1 with tests.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-28 20:30 UTC, Claude Code session `c7bd49c6`: plan agreed with Afshin over the conversation; task opened and Phase 1 claimed. Next: item 1.
