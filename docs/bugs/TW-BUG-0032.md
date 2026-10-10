# TW-BUG-0032: Published admin lists hidden by default for regular users

- Status: in-progress
- Confidence: reproduced in source; production screenshot reported
- Priority: P2 - regular users cannot discover admin-published lists
- First observed / last updated: 2026-10-10T12:59:59.621910+00:00
- Executor/session/claim time: Codex, published-lists-20261010, 2026-10-10T12:59:59.621910+00:00
- Authorization: Owner requested investigation and fix. Routine Dev completion authorized; staging/production excluded.

## User Impact and Reproduction

Keith October 9 email screenshot ends the market dropdown at Crypto Currencies; owner screenshot shows four Published Lists. A signed-in user with no preferences receives enabled_published=[]; App.js hides every published list unless explicitly opted in. Expected: enabled admin-published lists appear for all eligible users by default.

## Evidence and Investigation

Starting main bd4b3df3. App.js securityTypeListCombined filters by enabled_published.includes(name). get_securities_prefs returns an empty opt-in list for new users. Related list creation/Tara work: TW-TASK-0019. Dev catalog contains all four enabled lists with all supported access levels.

## Acceptance and Regression Checks

New and existing default-preference users see enabled published lists. Explicit user hiding persists across reload; newly published lists remain visible. Disabled lists stay hidden; admin editing and access/market enforcement stay intact. Tara selection unhides its requested list. Focused tests, production build and rendered Dev check pending.

## Implementation and Handoff

Branch codex/published-lists-20261010; worktree /home/tradewave-worktrees/published-lists-20261010. Next: implement default visibility with explicit per-user hiding, test/build, commit/push, activate and verify Dev. Source SHA pending. No production data or account edits. Rollback: record previous backend/frontend pointers before Dev activation.

## Environment Verification

Dev pending. Staging not deployed by task. Production not deployed by task.

## History

- 2026-10-10T12:59:59.621910+00:00: Codex claimed authorized fix; source opt-in visibility defect identified.
