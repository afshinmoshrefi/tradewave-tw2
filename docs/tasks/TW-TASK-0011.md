# TW-TASK-0011: Portfolio Holdings Import and Scenario Reports

- Status: fixed (live on dev; native PDF layout verification pending)
- Confidence: core flows reproduced and self-verified on dev; PDF layout remains unverified
- Priority: P2 - owner-requested portfolio research feature
- First observed / last updated: 2026-09-27T19:54:26Z / 2026-09-27T20:35:00Z
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

Final checks: 5 backend tests and 3 parser/selection tests passed. Production React build succeeded with existing lint warnings. The final active backend passed the real-engine HTTP smoke. Browser checks on Chrome/dev verified ambiguous category resolution, fractional imports, empty-portfolio immediate refresh, multi-color subset selection, all five horizons, saved history after reload, share-count revisions preserving the original, and permanent-delete checkbox gating (browser deletion canceled). API smoke verified actual deletion using disposable fixtures. Downloaded CSV was inspected and includes frozen shares, baseline values and horizon evidence.

[Rendered scenario report evidence](evidence/TW-TASK-0011/scenario-report.png). Browser sample portfolio `Scenario Preview` contains illustrative NVDA 100, MSFT 20, AAPL 10.5 holdings and two saved reports (original and AAPL 12.5 revision). `Scenario Import Check` contains the disposable SPY 2.5 regression fixture, retained for repeat checks. These are demonstration holdings, not brokerage records.

Pending: native print/PDF visual layout verification. Print action invoked the browser print flow, but the available browser automation cannot inspect the native dialog; no saved PDF was visually verified. Large-portfolio load and mobile layout were not exercised. Exact-window AI scores are explicitly unavailable; commentary was generated successfully. Initial valuation supports USD stock groups 0-4 and USD-listed ETF group 11 only.

## Implementation and Handoff

- Branch: codex/portfolio-scenarios-20260927
- Local managed worktree: C:/Users/afshin/.codex/worktrees/portfolio-scenarios/TradeWave Main Orchestrator
- Dev workspace: /home/tradewave-worktrees/portfolio-scenarios-20260927; dirty shared /home/flask preserved.
- Source commits: c9df19350a6e9dc57c04269d794617aeb4fd797d (implementation), 928fb73cb6bee129825e22e3d6d99c08ac448819 (empty-import refresh regression); both pushed to main. No new dependencies or migration. Rollback pointers below.
- Next action: visually inspect Print / Save as PDF for the five-horizon saved sample, confirm pagination and matching values, then mark full acceptance verified. Use a browser with native print access. No staging/production action authorized.
- Dev GitHub SSH fetch currently fails authentication; local authenticated GitHub fetch works. Transfer exact commits via bundle if needed; all server Git operations run as flask.

## Environment Verification

Dev: core flows verified at 2026-09-27T20:34Z. Active backend and frontend provenance both 928fb73cb6bee129825e22e3d6d99c08ac448819; backend worktree clean, appserver/apiserver active, health database/frontend/overall OK. Frontend artifact `/home/flask/web-react/releases/build-928fb73cb6bee129825e22e3d6d99c08ac448819`, browser bundle `main.827e060a.js`. Application commit advanced to main after smoke. Follow-up documentation does not change runtime sources. Activation lock released; receipt preserved at `/var/lib/tradewave/release-state/portfolio-scenarios-verified-928fb73`. Staging: not deployed by this task. Production: not deployed by this task.

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

- 2026-09-27T20:35:00Z Codex: implemented, tested and activated on dev. First activation exposed empty-portfolio import refresh; restored prior pointers, fixed the effect dependency, rebuilt and repeated activation/smoke successfully. Main advanced non-forced to the verified application commit. Core browser checks and CSV passed; native PDF inspection remains pending. Shared dirty checkout preserved. Candidate service stopped.

- September 27, 2026 follow-up: [TW-BUG-0020](../bugs/TW-BUG-0020.md) fixes import heading overlap, removes em dashes from scenario copy and static React interface text, and verifies 320px/390px layouts. Current dev source/artifact 55bdbdc2fc61d020d0066382faf6f22a52d28129; 48 React tests and 6 backend tests pass. Native PDF pagination remains pending.
