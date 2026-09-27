# TW-TASK-0011: Portfolio Holdings Import and Scenario Reports

- Status: in-progress
- Confidence: implementation under review; focused backend and real-engine candidate smoke passed
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

Backend focused checks: five tests passed in the dev Python 3.13 environment, covering reviewed fractional import and validation, common cohort/long-short replay, frozen revisions, cross-user isolation, deletion during generation, mismatched quote dates and engine identity. Tests retain supplied engine return rows rather than duplicate their calculation.

Candidate loopback HTTP smoke (`tests/verify_portfolio_scenarios_dev.py`) passed with disposable service-owned AAPL 10.5 / MSFT 5 holdings: 30-day and End of Year each had 10 shared completed years; saved returns matched live ChartData4 exactly; AI commentary was ready. Title/notes updates preserved calculations, deletion required confirmation and returned 404 afterward. Disposable reports/holdings/portfolio were removed. Candidate service is separate from the active dev app. The final backend source also passed the same smoke after exact resource membership, cancellation and timeout checks were added. AI provider failure is covered by a focused test and preserves the factual report.

Pending: final parser/UI checks, provenance-stamped build, rendered browser smoke and print/PDF layout verification. No public dev activation yet.

## Implementation and Handoff

- Branch: codex/portfolio-scenarios-20260927
- Local managed worktree: C:/Users/afshin/.codex/worktrees/portfolio-scenarios/TradeWave Main Orchestrator
- Dev workspace: /home/tradewave-worktrees/portfolio-scenarios-20260927; dirty shared /home/flask preserved.
- Source/integration commits, dependencies and rollback: pending.
- Next action: finish UI review, test/build exact candidate, activate and verify on dev under the short activation lock.
- Dev GitHub SSH fetch currently fails authentication; local authenticated GitHub fetch works. Transfer exact commits via bundle if needed; all server Git operations run as flask.

## Environment Verification

Dev: not deployed by this task. Staging: not checked. Production: not checked.

## Implementation Decisions

- Existing ChartData4 owns per-security returns; its zero-based route duration is supplied as inclusive days minus one. Exact-window echo, historical count, PE cycle, symbol, resource and direction must match.
- Audit found no existing common-year fixed-share portfolio replay, so the new aggregation lives in the TradeWave appserver, not the browser. Short figures are modeled notionals, not brokerage equity.
- Scope initially accepts USD stock groups 0-4 and USD-listed ETFs (group 11 assumption). Other units/currencies explicitly fail. Latest closing quotes must share a date and be at most seven calendar days old; the report discloses any difference from the scenario's market-date start.
- Imported records are holdings without purchase cost basis or seasonal-study dates. Fractional share handling extends the manager; original studies retain their dates.
- Per-user Redis snapshots are private, indexed and bounded; no database migration or new dependency. One active report per user, two globally. Restarts can interrupt in-process jobs, which become failed after the bounded expiry and can be regenerated.
- AI text uses the existing Tara provider integration; exact-window AI scores remain explicitly unavailable. PDF delivery uses the browser's Print / Save as PDF with all selected horizons.
- Previous backend pointer: /home/tradewave-worktrees/flat-return-release-585b668. Previous frontend pointer: /home/flask/web-react/releases/build-c76bd9b8e036d6c2638c44871b1e64b1981392ae. Verify again at activation and retain for rollback.

## History

- 2026-09-27T19:54:26Z Codex: claimed owner-authorized implementation; source review complete and clean managed worktree created.
