---
name: tradewave-deployment-manager
description: Manage TradeWave fast dev completion and gated staging/production releases across Codex and Claude. Use automatically for any substantive application or runtime-visible change; whenever the user asks to fix, change, build, update, activate dev, deploy, promote, release, ship, roll back, compare environments, determine readiness, continue a handoff, or diagnose drift; and whenever multiple agents work concurrently. Ordinary changes use the focused fast dev loop unless the user says local-only or do-not-deploy. A plain staging-deploy request starts the full manifest, regression, immutable-artifact, target-audit, browser/contract, and automatic-rollback workflow.
---

# TradeWave deployment manager

Use one of two modes:

- **Fast dev completion** is the default for ordinary application changes. It makes the requested behavior live, verified, committed, pushed, and staging-ready without running staging's release machinery.
- **Qualified release** begins only when the user asks to deploy to staging or production. It creates the named release and full manifest, qualifies one immutable artifact, audits the target, promotes, verifies, and rolls back automatically when required.

One manager means exclusive ownership of an environment mutation window, not one permanent agent or a separate conversation.

## Load the authority

1. Locate the TradeWave repository and fetch current remote refs using the repository's required Git user.
2. Read AGENTS.md, CLAUDE.md, docs/RELEASE_PROCESS.md, docs/TRADEWAVE_ECOSYSTEM.md, ops/OPERATIONS.md, and .claude/skills/tw-git-release-workflow/SKILL.md completely.
3. For production, also read .claude/skills/prod-deploy/SKILL.md and enforce its current-day snapshot gate.
4. If a required file is missing from the current worktree, inspect it from current origin/main before declaring it unavailable. Stop before changing an environment only when current-main authority is also missing or materially conflicting.

## Interpret authorization

- Inspect, compare, explain, diagnose, and readiness questions are read-only.
- Fix, change, build, or update substantive application behavior authorizes routine branch/worktree creation, focused testing, commit/push, clean integration, required build, dev-only activation, rollback-on-failure, and live verification. It does not authorize staging or production. local only or do not deploy overrides the default.
- Deploy to staging is complete authorization to qualify the behavior running on dev at request time and execute every required repository, dev, and staging action through verified completion, including automatic staging rollback. Do not ask the user to restate the process, choose routine commands, or run staging commands.
- Production requires the same staging-approved release, a separate explicit production request, and current-day snapshots of both production servers. Agents inspect and author production commands; Afshin or his designated operator executes production writes unless policy explicitly changes.
- Never transfer approval to a different SHA, artifact, target, or later release.

## Coordinate concurrent work

- Claude and Codex may edit the same repository concurrently only in separate clean branches/worktrees based on current origin/main.
- Each task owns one concern and pushes its exact commit. Do not mix arbitrary files from another checkout.
- Serialize only the brief final dev activation and all staging/production mutations. Do not hold the dev lock while coding, running ordinary tests, or performing the first build.
- The lock is /var/lib/tradewave/release-state/dev-activation.lock, created atomically with mkdir and containing owner/task metadata. Refuse a live lock unless handed off or explicitly proven stale.
- If another session owns the activation window, preserve the exact pushed commit and wait or hand it off internally. Never ask Afshin to sequence branches or locks.
- Never print secrets in state, logs, or responses.

## Fast dev completion - default

Do this automatically for application/runtime work unless the owner requested local-only work:

1. Fetch origin/main. If the current worktree is stale, dirty with unrelated work, or lacks current controls, preserve task-owned changes and move them to a fresh task worktree from current main.
2. Review the complete task diff. Run focused tests for the changed behavior plus cheap, directly relevant compile/lint checks. Use proportional extra gates for migrations, auth, billing, security, destructive data paths, or deployment infrastructure.
3. Commit and push only the task-owned change.
4. Integrate the exact task commit in a clean worktree on current origin/main. Build only affected runtime artifacts:
   - React changes: run npm run build once through the documented build path and stamp provenance.
   - Backend-only changes: do not rebuild React.
   - Static-generator changes: run only the affected generator after activation.
   - Documentation/policy-only changes: do not rebuild or activate the application when its runtime tree is unchanged.
5. After the candidate is tested and built, acquire the dev activation lock and immediately refetch origin/main. If main moved, release the lock, integrate the new commits, rerun only checks/builds affected by that integration, and retry. Do not start the full suite merely because another task completed.
6. Record the current backend and frontend pointers, activate the candidate through the actual runtime mechanism, and restart only affected services. A copied file is not active when systemd or nginx follows a release pointer.
7. Run one live smoke that proves the changed behavior:
   - UI behavior: rendered browser assertion of the affected interaction.
   - Backend/API behavior: relevant live route or contract assertion.
   - Static page: public/origin content assertion for the changed page.
   Feature-marker greps, build success, and HTTP 200 alone are insufficient.
8. Advance origin/main to the verified candidate with a non-forced concurrency-safe push. If the push fails because main moved, roll dev back to the recorded pointers, release coordination, integrate the newer main, and retry.
9. Refetch and prove that current main's application tree, live backend source, and affected artifact provenance match. Release the lock promptly.
10. Report the exact SHA and live evidence. **Staging-ready** means clean, pushed, live on dev, and focused-tested. It does not mean the full staging qualification has run.

Routine dev completion does **not** require a release ID, full release manifest, full regression suite, staging inventory, broad account-tier matrix, snapshots, or rollback rehearsal. A high-risk change adds relevant gates in step 2; it does not automatically inherit every staging gate.

## Begin a qualified staging release

Only after the user asks to deploy to staging:

1. Capture the behavior currently running on dev as the target. Assign a release ID such as tw2-YYYYMMDD-NN, claim manager ownership in release state, and create the manifest.
2. Confirm current origin/main has the same application tree as live dev. A docs-only main advance is allowed; the qualified artifact must still be built from the exact final main SHA.
3. Inventory all completed task SHAs and actual dev runtime pointers. Preserve unclassified dev work; never reset, stash, clean, delete, or overwrite it.
4. In a clean current-main release worktree, run focused integration checks, the complete safe regression suite, release-specific contracts, and the required release build. Build once and record source provenance, backend fingerprint, frontend paths/hashes, and the composite artifact hash.
5. Reconcile live dev with that exact qualified artifact. Run all required dev runtime, contract, entitlement, and browser gates. Bind the user's staging request to that exact SHA and composite artifact hash.
6. Lock main_locked_sha. Do not advance main, rebuild, re-merge, or substitute another artifact between staging qualification and production.

If dev behavior cannot be reproduced exactly from a clean commit and artifact, stop before staging.

## Maintain the release manifest

Store release manifests on dev at /var/lib/tradewave/release-state/<release-id>/release.json, with /var/lib/tradewave/release-state/active.json identifying the active qualified release. Initialize the state directory once with ops/init_release_state.sh. Keep it separate from disposable checkouts and validate manifests with ops/validate_release_manifest.py.

The full manifest starts at staging qualification, not during routine dev completion. It records:

- release/manager identity, target, status, timestamps, included task SHAs, exact release SHA, and locked main SHA;
- frontend paths/hashes, backend fingerprint, live process paths, and canonical composite artifact hash;
- test, runtime, contract, entitlement/browser, target-drift, and environment evidence;
- approvals bound to the exact SHA and artifact hash;
- out-of-band classifications, migrations/configuration, snapshots, risks, and concrete backend/frontend rollback pointers and commands;
- append-only events naming author and executor.

Write atomically. A required gate needs passed evidence. A blocking out-of-band item forbids deployment, approval, or completion.

## Promote the qualified artifact

For staging, then production:

1. Verify authorization and preconditions before any write. Capture executable rollback state.
2. Audit target tracked files, effective systemd base units/drop-ins, every release-managed process path, nginx/docroots, and active frontend hashes. Classify and preserve every difference; blocking or unknown drift stops promotion.
3. Require origin/main to equal main_locked_sha.
4. Promote the exact dev-qualified source SHA and artifact. Never rebuild or merge between environments.
5. Apply only recorded migrations/configuration and activate through the real runtime pointers.
6. Verify effective units/drop-ins, process working directories/commands, backend fingerprint, frontend index/bundle/hash, nginx route, health, contracts, and affected rendered behavior.
7. Staging commands must contain automatic rollback. On a failed post-write gate, roll back and verify restoration. If rollback fails, mark rollback_required, stop writes, and report the exact live state.
8. Record final evidence. Complete staging without another approval request. Production remains a later explicit request and human-executed write boundary.

Staging is mandatory before production. Production uses the same staging-approved SHA and artifacts and must pass the snapshot gate.

## Required Wave Viewer staging gates

Until replaced by a proven repository gate, every affected **staging or production release** includes:

1. A level-1/date-locked real US or INDX pattern with non-empty ChartData4 and echoed request.entry_date equal to the requested US market date. Include ordinary and UTC/US-evening coverage when date behavior is relevant.
2. A signed-in level-1 browser flow that clicks an opportunity row, finds a canvas in .seasonal-barchart-parent, and proves .barchart-background disappears after load.

For current-date changes, derive US market date from America/New_York; changing host timezone or weakening the response guard is not a repair. Staging intentionally has only US and INDX data. Do not add absent datasets or select absent markets for contracts.

These broad gates belong to staging qualification. During fast dev completion, exercise the changed behavior and only the entitlements/timing conditions directly affected by it.

## Risks, rollback, and handoff

- Read unresolved records under ops/release-risks/ when qualifying a staging/production release and reverify current status. Do not burden unrelated fast dev changes with a full target-risk audit.
- Before any activation, know the previous affected pointers. Routine dev may use the documented pointer rollback; staging/production records complete executable rollback in the manifest.
- Before handing a qualified release to another manager, atomically update the manifest with exact pointers, SHAs/hashes, completed/pending gates, approvals, risks, and rollback.
- Before handing unfinished dev work, push the exact task commit and state focused tests and remaining work; a full release manifest is unnecessary.

Call application work complete when it is committed, pushed, running on dev, and live-verified under the fast loop. Call a staging or production release complete only when the requested environment runs the exact qualified release, all mandatory gates pass, rollback is documented, and the manifest is final.
