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
Next: establish WorkOS device authorization and protected refresh-token storage, integrate preserved fixes, qualify and deploy. All new test results and runtime verification pending. Dev/staging not deployed by this task; production untouched.
