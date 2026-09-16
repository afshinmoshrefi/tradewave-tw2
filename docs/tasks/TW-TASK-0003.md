# TW-TASK-0003: Reusable Dev MCP Release Authentication and Staging Promotion

- Status: verified on staging; production promotion in progress, awaiting operator execution (2026-09-16 UTC)
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

## Completed Release (2026-09-16 UTC)

Owner consent completed. Dev-only OAuth credentials are renewable and root-only;
later releases use the documented `run-gate` command without repeating setup unless
the grant expires or is revoked. No credentials are in Git or this record.

Dev and both staging Git trees are clean at
`05ae209ecaba231e5816f835dc133f7c0cdf00e8`; origin/main is pinned to that SHA.
Composite artifact: `f409df46defc42ab024ab9e1fade5c98aea2c16c1d61c28cd2a9efba3c77c37e`.
React: `main.81dfb8cb.js`, SHA256
`2c2011e5d57ab112cf72b022e6a94002aad3aa1952d9714557312d89e4d430f9`.
All 21 frontend files match; backend archive fingerprint matches on both tiers.
Effective processes use the qualified dev pointer and canonical staging paths;
no stale staging systemd drop-ins. Public React bytes match the qualified build.

Live qualification: authenticated API/MCP BYOK and real WorkOS OAuth passed;
200 requests at concurrency 50, final p95 12.470 seconds, zero errors, 16 healthy
gateway samples. Initial public load p95 was 29.635 seconds; identical subsequent
runs passed at 12.824 and 12.470 seconds. No thresholds were changed.

Dev and staging: Explorer/date-locked real chart contract passed with market date
2026-09-15 while UTC was September 16. New York browser row click, full-resolution
canvas, loading-cover removal, video modal and controls passed. Staging table
recurrence/filter/recovery passed. All 28 mobile rotation, landscape and right-edge
resize cases passed on both environments. Physical Safari was not tested.
All site generators completed; seven public-page routes returned valid HTML;
the deploy verifier reported zero failures and zero warnings.

One staging attempt rolled back successfully after the manager's SCP helper could
not overwrite a flask-owned disposable shell in sticky `/tmp`. The helper now
removes only its exact disposable file before copying. The successful retry used
the same source and build. Earlier dev attempts also restored their prior pointers
after a UTC-browser timeout and the same temporary-file protection issue.

Rollback snapshots on both staging servers:
`/root/tradewave-snapshots/tw2-20260915-01` (APP 32M, WEB 415M).
Staging rollback command, run on dev:
`bash /root/tradewave-handoffs/tw2-20260915-01/staging/rollback-staging.sh`.
The prior release is `c398d648463c10b31f088982f6cd67bfd8c30a72`.
Dev pointer rollback is recorded in the release state directory's `rollback-dev.sh`.

Known unresolved findings: TW-BUG-0003 through 0007, plus the browser-local/market
date mismatch in TW-BUG-0010 and Tara help routing in TW-BUG-0011. None are claimed
fixed. The latter two were discovered during qualification and are preserved as
explicit risks, including failed exploratory help expectations. Staging promotes
the actual qualified dev behavior; it is not a claim of globally bug-free behavior.

Authoritative final manifest on dev:
`/var/lib/tradewave/release-state/tw2-20260915-01/release.json` (valid, complete,
manager released). Evidence is in its `evidence/` directory. Production untouched.
Production requires a separate owner request and current-day snapshots of both
production servers; promote this exact artifact, never rebuild it.

This documentation-only completion is on `codex/staging-report-20260915`, based on
the release SHA, so main and the live release stay pinned during the production
approval gate. Do not mistake this report-only commit for another application build.

## Production Promotion Authorization and Prepared Command

2026-09-16: Afshin confirmed staging works, requested production promotion, confirmed
today's APP and WEB infrastructure snapshots, and explicitly said "continue
deployment" after discussion of TW-BUG-0010. The timezone issue remains unchanged;
Afshin plans an evening check. This authorizes promotion, not a timezone repair.

Resumed owner: Codex production-promotion-20260916. The same release manifest is
now `prod_preflight`, with approvals bound to SHA `05ae209e` and the unchanged
composite artifact. Main remains frozen. The report branch is still the shared
coordination branch; no documentation commit is substituted for the application.

Read-only checks verified production APP `138.128.240.115` and WEB
`194.113.195.141` clean at `c398d648463c10b31f088982f6cd67bfd8c30a72`, canonical
live process directories, no pointer drop-ins, the old frontend hash, nginx routes,
and 26 GB / 9.3 GB available respectively. Both staging tiers still match the
approved source, including all 21 frontend file hashes. The committed deployment
preflight passed host/environment, WorkOS issuer, both service identities,
systemd, Git and capacity gates. Evidence: release-state `evidence/prod-preflight*`.
No dependency requirement or schema/migration changes from production's prior
release were found. No production write has occurred during preparation.

Operator command on dev:
`bash /root/tradewave-handoffs/tw2-20260915-01/production/deploy-production.sh`

The command requires same-day snapshot approval, rechecks identity and targets,
captures checksum-verified local rollback snapshots on both production tiers,
then promotes the exact existing build. It includes automatic rollback through
all source/runtime/page/contract/rendered browser checks, including the 28 chart
rotation/resize cases already exercised on staging. It records completion only
after those gates pass. Expected production frontend: `main.81dfb8cb.js`.

Rollback (operator execution only):
`bash /root/tradewave-handoffs/tw2-20260915-01/production/rollback-production.sh`
This requires the command-created snapshots at
`/root/tradewave-snapshots/tw2-20260915-01-prod-release` on each tier.
The rollback restores the current `c398d648` source and `build-c398d648463c` frontend.
Next step: Afshin executes the guarded command; manager independently inspects
receipts/live state and updates this record with verified outcome. Production is
not yet deployed or verified by this task.
