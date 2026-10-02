# TW-BUG-0023: Scenario Studio Used a Green Palette Instead of the TradeWave Color Scheme

- Status: verified on dev
- Confidence: reported by the owner and reproduced in live headless Chrome; the fix was verified by reading computed styles off the rendered dialog, not by grepping the bundle
- Priority: P2 - brand inconsistency on a user-facing feature; no functional impact
- First observed / last updated: 2026-10-02
- Executor/session/claim time: Claude Code (Opus 5), branch `claude/scenario-studio-brand-colors-20261002`, worktree `/home/tradewave-worktrees/scenario-brand-20261002`, claimed 2026-10-02
- Authorization: owner reported the green `TW / RESEARCH` heading and asked for the TradeWave color scheme. Owner chose a brand recolor that keeps the light report surface over a full theme-aware rewrite. Dev only. No staging or production authorization.

## User Impact and Reproduction

Open Portfolio Manager, then Scenario, Import or Reports. The Scenario Studio opens with its own green and gold palette: the `TW / RESEARCH` top bar was `#102d32`, the page heading and report hero bands were `#173d42`, the separator and every eyebrow, accent, active tab and marker were gold, and primary buttons were teal `#1a524f`. None of these are TradeWave colors, so the studio did not read as part of the product.

Root cause: `web-react/src/components/styles/PortfolioScenarios.css` holds about 90 hardcoded colors and does not read `themeColors(UITheme)` from `Common.js` the way the other dialogs do. The self-contained palette is deliberate, because it keeps the report surface light for print while the viewer around it may be dark, but nothing tied those literals to the brand.

## Acceptance and Regression Checks

Scope was color only. Layout, spacing, typography, the `@media print` rules and the semantic gain and loss colors are unchanged; the diff is 70 changed lines in one file with no markup change. Verified on dev at commit c9a8656 by driving the real authenticated app in headless Chrome, opening Portfolio Manager and then Scenario, and reading `getComputedStyle` off the mounted dialog:

- `.ps-topbar` background `rgb(20, 15, 33)` (`#140f21`), text `rgb(201, 198, 224)`
- `.ps-mark span`, the separator in `TW / RESEARCH`, `rgb(124, 92, 255)` (`#7C5CFF`, the exact brand purple)
- `.ps-heading` background `rgb(30, 24, 51)` (`#1e1833`), text `rgb(234, 240, 248)` (`#EAF0F8`)
- `.ps-heading .ps-kicker` `rgb(169, 139, 255)`, active tab and primary button `rgb(109, 77, 242)`

The served stylesheet carries no remaining `#102d32`, `#173d42`, `#cb9b55` or `#1a524f`. Full-dialog and header screenshots were captured and reviewed.

## Implementation and Handoff

Source commit c9a8656 (recolor) and 6be758a (ecosystem doc invariant), both pushed to `main`. React rebuilt once through `npm run build`; dev frontend pointer `/home/flask/web-react/build` moved to `releases/build-c9a865640aeacf6e7fd10dc925ad065e80c0d8ac` with `build-previous` kept as the rollback pointer. No backend, migration, dependency or configuration change. The brand values this file must keep are recorded in `docs/TRADEWAVE_ECOSYSTEM.md` section 7 beside the Scenario Studio description, so a later rule cannot silently reintroduce a per-component palette. Continues TW-TASK-0011 and TW-BUG-0020. Next action: owner visual review on dev. Staging and production still run the old green palette until a separate deploy request.

## Environment Verification

Dev only. `origin/main`, the live dev backend worktree `/home/tradewave-worktrees/tw2-20261002-01` and the live frontend build provenance all read c9a8656 at activation time. The dev activation lock was held only for the pointer swap and released. Staging and production unchanged.
