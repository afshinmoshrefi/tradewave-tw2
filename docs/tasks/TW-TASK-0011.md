# TW-TASK-0011: Portfolio Holdings Import and Scenario Reports

- Status: in-progress
- Confidence: source reviewed; implementation pending
- Priority: P2 - owner-requested portfolio research feature
- First observed / last updated: 2026-09-27T19:54:26Z
- Executor/session/claim time: Codex, portfolio-scenarios-20260927, 2026-09-27T19:54:26Z
- Authorization: Afshin approved implementation in voice discussion with "Okay, let's get started." Includes routine dev completion; no staging or production deployment.

## Goal, Scope and Acceptance

Extend the existing Portfolio Manager, without a separate portfolio type:
1. Import CSV/pasted holdings with ticker and share quantity; resolve category per security, preview ambiguous/unmatched rows, preserve fractional quantities, enforce permissions and quotas.
2. Scenario setup selects all rows or one/more existing status colors; review exact holdings and quantities (including repeated tickers). Horizons: 30/60/90 calendar days, End of Year, and custom. Dates use TradeWave inclusive calendar convention.
3. Fixed-share valuation scenarios anchored to timestamped current prices. TradeWave supplies exact-window historical returns. Common completed historical years across holdings; disclose coverage and exclusions. No silent missing-as-zero or unsupported currency/instrument aggregation.
4. Portfolio historical replay, average scenario values/dollar and percentage changes, historical positive/flat/negative frequencies, annual outcomes, contributions and per-holding evidence. Verify existing engine capabilities before adding genuinely new engine-owned portfolio math. No averages of win probabilities or AI scores.
5. Polished private interactive report plus matching downloadable/printable PDF. Include AI commentary grounded in report facts; exact-window AI scores only when actually available. Never fabricate AI output or availability.
6. Multiple dated immutable snapshots per portfolio with history. Rename/notes may change; holdings/settings edits create revisions and refresh commentary. Old reports remain until explicitly deleted. Permanent deletion requires a Delete Forever acknowledgment and revokes hosted access; previously downloaded files cannot be revoked.
7. Save subset membership and quantities in the report, independent of later portfolio/color changes. Existing portfolio studies retain dates and behavior. Duplication explicitly excluded for now.

## Evidence and Investigation

Baseline GitHub main e42fb09a9ee09ff7b6deed50528a65e58017071f. Portfolio rows are per-user Redis report records with resourceID, symbol, date, days_hold, years, direction, num_shares and status. ReportsDashboard filters total valuations by status (0 means all). Watchlist CSV import currently selects a single best resource group and imports only symbols. Homepage seasonal_report.py already requests fixed horizons per ticker, but its downstream average/win computation must not be reused as engine authority.

## Acceptance and Regression Checks

Pending: engine contract, import parsing/validation, ownership/access isolation, immutable revisions, deletion, selection, missing/ambiguous/duplicate securities, long/short/fractional holdings, exact dates/common cohorts, AI failure handling, PDF parity, focused UI build and rendered dev smoke. No live verification yet.

## Implementation and Handoff

- Branch: codex/portfolio-scenarios-20260927
- Local managed worktree: C:/Users/afshin/.codex/worktrees/portfolio-scenarios/TradeWave Main Orchestrator
- Dev workspace: pending; preserve dirty /home/flask.
- Source/integration commits, dependencies and rollback: pending.
- Next action: engine audit and implement bounded authenticated report/import contracts, then UI/report presentation and focused tests.
- Dev GitHub SSH fetch currently fails authentication; local authenticated GitHub fetch works. Transfer exact commits via bundle if needed; all server Git operations run as flask.

## Environment Verification

Dev: not deployed by this task. Staging: not checked. Production: not checked.

## History

- 2026-09-27T19:54:26Z Codex: claimed owner-authorized implementation; source review complete and clean managed worktree created.
