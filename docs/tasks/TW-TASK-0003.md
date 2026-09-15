# TW-TASK-0003: Reusable Dev MCP Release Authentication and Staging Promotion

- Status: in-progress
- Confidence: reproduced
- Priority: P1, release blocked by missing authenticated qualification
- First observed: 2026-09-14; claim updated: 2026-09-15T22:10:00Z
- Executor/session: Codex, staging-release-20260915-auth
- Authorization: owner explicitly approved setting up reusable dev MCP test authentication, then deploying all current dev fixes to staging. Production is excluded.

## Goal, Scope and Acceptance

Register a dev-only OAuth test client with renewable credentials held only on dev.
Qualify a clean candidate containing current main's completed bug fixes and the
separate OppList4 sparse-day/empty-response and OppTable guard repairs currently
in the active dev worktree. Preserve all unrelated work. Promote the identical
qualified source and frontend artifact to staging, with automatic rollback and
live backend, site, account-tier, MCP and rendered chart verification.

## Evidence and Investigation

Prior release evidence is on dev at `/var/lib/tradewave/release-state/tw2-20260914-01/`.
September 15 cleanup cleared both staging disk gates and preserved rollback artifacts.
At claim, main is `59314a72dd29878ac00af35105a1dde64d6b60a5`; backend pointer remains
`/home/tradewave-worktrees/restore-overlay-integrated-20260912`, HEAD `63a520ea`, with two uncommitted files.
The previous release artifact does not include the newest fixes and is not approved for promotion.

## Implementation and Handoff

Branch `codex/staging-release-20260915`; worktree `/home/tradewave-worktrees/tw2-20260915-01`.
Preserved and cleanly applied both active-dev repairs without changing their source
worktree. Six new sparse OppList4 regression tests cover missing middle/weekend
days, all-missing output shape and empty results. Main's latest completed chart
fixes TW-BUG-0001/0002/0008/0009 are included in this candidate. Open bugs
TW-BUG-0003 through TW-BUG-0007 remain outside this repair's scope.

Added dev-only root-protected WorkOS authorization-code/PKCE credential storage,
refresh and mandatory-gate wrapper, plus a dedicated API test identity using normal
Business limits (no customer subscription or production change). Public DCR does
not enable device-code grants; browser sign-in/consent is required once. Six
focused tests cover credential-file safety and token identity validation.

Qualification so far: 1,461 Python passed / 5 skipped; separate MCP suite 58
passed; React 46 suites / 447 tests passed; six additional auth security tests
passed. Durable logs and final runtime pointers are in
`/var/lib/tradewave/release-state/tw2-20260915-01/` on dev.

Pending: owner OAuth consent, exact-SHA build, dev live qualification, then guarded
staging promotion and live parity verification. No dev/staging runtime activation
by this task yet. Production remains untouched. Do not deploy the older September
14 artifact or describe this candidate as staging-approved before final gates pass.
