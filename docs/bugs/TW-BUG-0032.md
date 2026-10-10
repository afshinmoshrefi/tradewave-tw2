# TW-BUG-0032: Published admin lists hidden by default for regular users

- Status: verified on dev
- Confidence: reproduced and verified on Dev; production screenshot reported
- Priority: P2 - regular users cannot discover admin-published lists
- First observed / last updated: 2026-10-10T12:59:59.621910+00:00
- Executor/session/claim time: Codex, published-lists-20261010, 2026-10-10T12:59:59.621910+00:00
- Authorization: Owner requested investigation and fix. Routine Dev completion authorized; staging/production excluded.

## User Impact and Reproduction

Keith October 9 email screenshot ends the market dropdown at Crypto Currencies; owner screenshot shows four Published Lists. A signed-in user with no preferences receives enabled_published=[]; App.js hides every published list unless explicitly opted in. Expected: enabled admin-published lists appear for all eligible users by default.

## Evidence and Investigation

Starting main bd4b3df3. App.js securityTypeListCombined filters by enabled_published.includes(name). get_securities_prefs returns an empty opt-in list for new users. Related list creation/Tara work: TW-TASK-0019. Dev catalog contains all four enabled lists with all supported access levels.

## Acceptance and Regression Checks

New and existing default-preference users see enabled published lists. Explicit user hiding persists across reload; newly published lists remain visible. Disabled lists stay hidden; admin editing and access/market enforcement stay intact. Tara selection unhides its requested list. Passed: 3 isolated backend route tests and 45 React settings/Tara contract/guidance checks. React production build passed (existing warnings). Rendered Dev regular-user checks passed for default visibility of all four lists, selecting midcaps, hide/reload, and re-show/reload. Browser baseline reproduced zero dropdown lists despite a four-list authenticated catalog. The browser harness uses the existing Dev-only capture-bot shell, signed ordinary user claims and real live APIs/assets; it does not exercise WorkOS sign-in or every subscription tier. Explicit hiding is stored separately in hidden_published; existing opt-in data remains compatible.

## Implementation and Handoff

Branch codex/published-lists-20261010; worktree /home/tradewave-worktrees/published-lists-20261010. Source/integration SHA: 792d61c50a91b35d1d5e023f51b23355e6324ef6, pushed on the task branch and main; clean integration worktree /home/tradewave-worktrees/published-lists-dev-20261010 is active. Changed App.js dropdown and Tara unhide, SecuritiesGroupSettings.js visibility controls/reset, and appserver preference read/write; added focused route/component regressions. Canonical ecosystem entry updated. No dependencies, migrations or configuration changes. Next: qualify this change through staging when requested, then obtain explicit production release authorization. No production data or account edits. Rollback: restore backend /home/tradewave-worktrees/tara-followup-fix-20261004 and frontend /home/flask/web-react/releases/build-15464c2bb7d2064f32fa51b679e9a3f4bb0fd867 using the recorded atomic pointer mechanism, then restart tradewave-appserver and tradewave-web. This rollback was exercised during the browser-harness correction. Never overwrite subsequent releases or customer preferences. Test-bot preference state was restored after both checks; catalog/account roles were unchanged.

## Environment Verification

Dev verified 2026-10-10T13:09:08.125359+00:00 by Codex, source/artifact 792d61c50a91b35d1d5e023f51b23355e6324ef6. All three affected/dependent services active; main, backend and frontend source provenance matched after activation. Evidence: /var/lib/tradewave/release-state/published-lists-20261010/dev-verification.json, browser-before.json/png, browser-after.json/png, activation-before.json on Dev (SSH tradewave-vm). Recreate with an ordinary signed-in Strategist user whose legacy enabled_published=[]; no customer data needed. Browser check used Chromium desktop 1440x1000. Staging not deployed by task. Production not deployed by task.

## History

- 2026-10-10T12:59:59.621910+00:00: Codex claimed authorized fix; source opt-in visibility defect identified.

- 2026-10-10T13:09:08.125422+00:00: Codex verified Dev and released activation lock. Knowledge maintenance captured the visibility invariant in the existing ecosystem entry. Full staging regression and production verification intentionally pending their release requests.

- 2026-10-10T13:57:44Z: Follow-up TW-TASK-0023 corrected the separately rendered desktop inline settings controls to hidden_published opt-out behavior. Real desktop UI now verified hiding both a market and published list, plus persistence across a fresh browser context. Active Dev source 906bd7b6d578c63076d88b3fa9f5e62bac16185b includes that correction and one-time customization guidance; see task receipt for current pointers and rollback. Staging/production unchanged.
