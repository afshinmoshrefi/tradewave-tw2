# TW-TASK-0023: One-time securities menu customization tip

- Status: verified on dev
- Executor/session/claim: Codex, securities-menu-tip-20261010, 2026-10-10T13:36:56.488697+00:00
- Authorization: Owner accepted the proposed first-click popover, per-account acknowledgment, Customize Lists and Got It buttons, and settings help replay. Routine Dev activation included; staging/production excluded.

## Goal and Acceptance

First intentional mouse/touch/keyboard opening of the market dropdown shows a brief anchored tip explaining market hiding and published-list visibility. Both buttons persist acknowledgment per account; Customize Lists opens existing securities settings. Settings help can replay the explanation. Existing menu selection works normally after acknowledgment. No tip on page load; wait for account preferences to load; no acknowledgment on failed save. Test desktop and narrow mobile, persistence across fresh browser contexts, help replay, and list opt-out via actual desktop settings.

## Investigation and Plan

App owns account/catalog/preferences; shared SelectBox renders each securities dropdown. Add a focused tip component and activation callback through UserContext. Store acknowledgment separately from resettable list preferences using the existing authenticated appserver token flow. Connect Customize Lists to desktop inline settings and existing mobile securities settings. Desktop inline published controls still use legacy enabled_published; align them with TW-BUG-0032 hidden_published so customization actually works.

## Evidence, Handoff and Release

Repository afshinmoshrefi/tradewave-tw2. Branch codex/securities-menu-tip-20261010; source worktree /home/tradewave-worktrees/securities-menu-tip-20261010. Starting source 8097f90e; verified source/artifact 906bd7b6d578c63076d88b3fa9f5e62bac16185b pushed to task branch and main. Clean integration worktree /home/tradewave-worktrees/securities-menu-tip-dev-20261010 is active. No dependencies, configuration changes or migration.

Validation: 4 isolated backend route tests; 50 React tip/settings/Tara checks passed before the final touch correction, then all 9 affected tip/settings tests passed including the added touch regression (51 distinct React tests total). React production build passed with existing warnings. Live Chromium desktop 1440x1000, Android touch 390x844 and keyboard checks passed: no page-load tip, first opening, failed-save retry, Customize Lists destination, actual market/published-list opt-out persistence, fresh-browser acknowledgment persistence, and settings help replay. Desktop and mobile screenshots visually inspected. Harness uses existing Dev capture-bot ordinary user claims, actual signed live APIs and assets; does not exercise WorkOS sign-in, every subscription tier or native iPhone. Test-bot preferences were restored in finally; no customer data, roles or catalog changes.

Dev verified 2026-10-10T13:57:44.520326+00:00. All three affected/dependent services active; source main/backend/frontend matched before docs-only advance. Evidence at /var/lib/tradewave/release-state/securities-menu-tip-20261010/: dev-verification.json, browser.json, reproduce-browser.py, browser-desktop.png, browser-desktop-settings.png, browser-mobile.png, browser-mobile-settings.png and activation-before.json. Canonical ecosystem securities entry updated with the per-account acknowledgment dataflow and reset independence.

Rollback: atomically restore backend /home/tradewave-worktrees/published-lists-dev-20261010 and frontend /home/flask/web-react/releases/build-792d61c50a91b35d1d5e023f51b23355e6324ef6, restart tradewave-appserver and tradewave-web, verify dependent tradewave-apiserver active. Do not overwrite later releases or user preferences. Automatic rollback exercised during verification. No staging or production deployment by this task; next release qualification requires its own request.

## History

- 2026-10-10: Claimed after owner accepted first-use popover design.
- Live verification caught the legacy general-dialog destination and initial touch click dismissing the new overlay. Corrected to desktop panel visibility setter and outside pointer-down dismissal; added focused touch regression. Help replay preserves underlying settings.
- 2026-10-10T13:57:44Z: Full Dev browser verification passed; main pushed, receipt recorded and activation lock released.
