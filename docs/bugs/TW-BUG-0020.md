# TW-BUG-0020: Scenario Import Heading Overlap and Phone Layout

- Status: verified on dev
- Confidence: overlap reproduced; fixed layout and copy self-verified in live Chrome at desktop and phone viewport sizes
- Priority: P2 - impairs portfolio import readability and phone usability
- First observed / last updated: 2026-09-27
- Executor/session/claim time: Codex, portfolio-scenarios-20260927, 2026-09-27
- Authorization: owner requested no em dashes, import heading overlap fix, and smartphone verification.

## User Impact and Reproduction

On dev application revision 928fb73cb6bee129825e22e3d6d99c08ac448819, open Portfolio Manager, then Import. Introductory text overlaps Import holdings heading. Check import, setup, history, report and dialogs at desktop and 320-390px phone widths. Existing saved titles and AI text may contain em dashes.

## Acceptance and Regression Checks

Headings and descriptions do not overlap; phone actions remain reachable, tables scroll within their containers, and report totals remain unchanged. Render saved and new report copy without em dashes, including exports. All checks passed on application commit 55bdbdc2fc61d020d0066382faf6f22a52d28129. [320px import](evidence/TW-BUG-0020/import-320.png) and [390px report](evidence/TW-BUG-0020/report-390.png) show live rendered results.

## Implementation and Handoff

Continues TW-TASK-0011 in its clean current-main local worktree and branch codex/portfolio-scenarios-20260927. Parent owns integration and dev activation; focused agent owns scenario CSS only. Financial calculations unchanged. No staging or production authorization. Source commits d1043d1 (punctuation and scoped layout), 82b3376 (retain original unrelated spacing), edab69c and 55bdbdc (touch-sized entry controls). All pushed to main. Remote runtime worktree `/home/tradewave-worktrees/scenario-polish-20260927` is clean. No dependencies or migrations. Next action: normal product review; the earlier native PDF pagination check in TW-TASK-0011 remains pending.

## Environment Verification

Dev: verified September 27, 2026, approximately 20:59 UTC by Codex. Backend and frontend provenance both 55bdbdc2fc61d020d0066382faf6f22a52d28129. Both services active and health OK. Main advanced non-forced after live smoke. Lock released; receipt `/var/lib/tradewave/release-state/scenario-polish-verified-55bdbdc` retains previous pointers. Rollback backend `/home/tradewave-worktrees/portfolio-scenarios-20260927`, frontend `/home/flask/web-react/releases/build-928fb73cb6bee129825e22e3d6d99c08ac448819`. Staging/production: not deployed by this task.

## Verification Evidence

- Confirmed inherited heading line-height was about 17px at a 38px desktop heading font. Scoped line-height now measures 42.56px; description begins below it.
- Six backend tests passed, including punctuation normalization that preserves numeric snapshot fields and does not mutate stored inputs.
- Four focused React suites passed, 48 tests: portfolioScenarioUtils, AIScorePanel, OpportunityAICell, analysisReportData. Local Jest path discovery was unavailable through the node_modules junction; actual suites ran on dev in the isolated worktree.
- Production build passed with existing warnings. An initial build preceded discovery of cramped phone launch controls; rebuilt once after that fix.
- Live engine smoke passed for two disposable holdings with 30-day and EOY horizons, ten common years, ready AI commentary, exact engine return fidelity and deletion/metadata checks.
- Chrome desktop 1536px and phone viewports with actual inner widths 320px and 390px: import heading, description and input do not overlap; content scrollWidth equals clientWidth. SPY 2.5 import preview resolved correctly without adding another holding. Black plus Red selects two positions; Custom accepts 120 days. History and original saved report open with ordinary hyphens, zero em dashes and unchanged baseline/30-day figures. EOY switching returns the existing $40,518.76 scenario value. Wide holdings table scrolls within its container. Report buttons are 44px high. Edit dialog fits fully at 320px and was canceled. Portfolio launch buttons are reachable and 44px high at phone width. Temporary viewport override reset after checks.
- Browser viewport testing, not physical iOS/Android device testing. Native print/PDF visual pagination remains outside available browser controls, as previously recorded. No calculation changes.

## History

- September 27, 2026: owner authorized presentation corrections. Implemented, committed, built, activated and live-verified on dev. Existing no-em-dash house style is now applied to scenario response text, including legacy saved reports, and static React interface copy.
