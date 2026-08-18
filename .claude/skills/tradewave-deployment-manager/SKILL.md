---
name: tradewave-deployment-manager
description: Manage TradeWave application completion, dev activation, releases, and environment parity across Codex and Claude. Use automatically for any substantive TradeWave application or runtime-visible code change; whenever the user asks to fix, change, build, or update product behavior; when work must become live and verified on dev; when multiple agents are working concurrently; or when the user asks to deploy, promote, release, ship, roll back, prepare a release, compare environments, determine readiness, continue a handoff, or diagnose drift. A normal application-change request includes clean Git integration and verified dev activation unless the user says local-only or do-not-deploy. A plain staging-deploy request authorizes the complete gated staging workflow. Enforce one mutation owner, current-main worktrees, immutable artifacts, active-runtime verification, browser smoke tests, and recorded rollback.
---

# TradeWave deployment manager

Act as the sole mutation manager for one named release. A coding session may assume this role; a separate deployment conversation is not required. Treat the live dev product plus the requested change as behavior to preserve, then make the combined behavior reproducible as a clean commit and immutable artifact. "One manager" means exclusive ownership of final integration and activation, not one permanent agent.

## Load the authority

1. Locate the TradeWave repository.
2. Read `AGENTS.md`, `CLAUDE.md`, `docs/RELEASE_PROCESS.md`, `docs/TRADEWAVE_ECOSYSTEM.md`, `ops/OPERATIONS.md`, and `.claude/skills/tw-git-release-workflow/SKILL.md` completely.
3. For production, also read `.claude/skills/prod-deploy/SKILL.md` and enforce its current-day snapshot gate.
4. Treat `docs/RELEASE_PROCESS.md` as the cross-agent release policy and `ops/OPERATIONS.md` as the command/runbook authority. If a required file is missing from the current worktree, fetch and inspect it from current `origin/main` before concluding that the control is unavailable. Stop before changing an environment only if the authority is also missing from current `origin/main` or the authorities conflict materially.

## Interpret authorization narrowly

- A request to inspect, compare, explain, diagnose, or check readiness authorizes read-only work only.
- A request to fix, change, build, or update substantive TradeWave application behavior authorizes routine branch/worktree creation, commit and push, clean integration, build, dev-only activation, rollback-on-failure, and live verification needed to leave the change complete on dev and staging-ready. It does not authorize staging or production. An explicit `local only` or `do not deploy` instruction overrides this default.
- A request to deploy to staging is the complete authorization for the sole release manager to preserve work, integrate and push the clean release, advance `origin/main` after validation, build and activate dev, execute staging writes, verify staging, and automatically roll back staging on failure. It approves the behavior running on dev when the request is made as the release target. It never authorizes production.
- Do not ask the user to restate the workflow, select routine commands, run staging commands, or approve intermediate steps. Proceed autonomously while the captured dev behavior is reproduced exactly and every gate passes. Ask only when an unclassified change requires an owner decision, exact dev parity cannot be proven, required credentials/authority are unavailable, or rollback cannot be made safe.
- A request to deploy to production requires the same release to have passed staging, explicit production approval, and current-day web and appserver snapshots.
- Never treat an earlier approval as approval of a different commit, artifact, target, or release.
- The release manager executes approved repository, dev, and staging writes. Record `execution_mode=manager-live-write` and the executing agent identity for staging mutations. Production remains separate: agents inspect and author commands, and Afshin or his designated human operator executes production writes unless a later explicit policy change says otherwise.
- Every staging activation must include automatic rollback in the manager-started command. If automatic rollback fails, mark the release `rollback_required`, record the target as at risk, stop further writes, and report the exact state. For production, retain the operator/automatic-rollback rule in the production skill.

## Establish exclusive ownership

1. Assign a release ID such as `tw2-YYYYMMDD-NN`.
2. On the first use of this process, initialize the dev-owned state path with `sudo bash ops/init_release_state.sh`. Inspect `/var/lib/tradewave/release-state/active.json` and the release manifest if present. Keep durable state separate from disposable release checkouts.
3. Do not integrate or deploy when another active manager owns the release. Continue only after an explicit handoff or owner override is recorded.
4. Record manager identity, task/thread identity when available, requested target, and status. A manager may be replaced; the manifest, commit, artifacts, evidence, and approvals carry the authority, not chat memory.
5. Development agents work in isolated task branches. To finish application work, the coding session either becomes the recorded dev-completion manager or hands the exact pushed commit to the manager already holding the mutation window. Only the recorded manager may perform final integration, advance the release branch or `main`, build the release artifact, activate dev, execute the authorized staging promotion and rollback, or author production promotion and rollback commands.

Never print secrets in a manifest, log excerpt, or response.

## Complete application work on dev

For substantive application or runtime-visible work, do not stop after editing, local tests, a commit, or a handoff unless the owner explicitly requested local-only work. Branches, commits, worktrees, handoffs, locks, and routine conflict resolution are internal agent responsibilities.

1. Before editing, fetch current remote refs. If the current worktree is stale, dirty with unrelated work, or predates the policy files, preserve task-owned changes and move them to a fresh task worktree based on current `origin/main`. Check required policy files in `origin/main` before declaring them missing.
2. Commit and push only the task-owned change. Record its exact SHA and tests.
3. Inspect release state. If another Claude or Codex manager owns the dev mutation window, preserve the handoff and wait or coordinate with that manager; do not ask the owner to order branches and do not claim the change is done.
4. Acquire `/var/lib/tradewave/release-state/dev-activation.lock` before final integration. Refetch `origin/main` while holding the lock, create a clean integration worktree, and combine the task with every already completed change.
5. Run focused tests, the combined safe suite, and the release build. Activate that immutable candidate on dev and verify the actual changed behavior, including a rendered browser assertion for UI behavior.
6. After live verification, advance `origin/main` to the exact candidate with a non-forced, concurrency-safe update. If the remote ref changed unexpectedly, roll dev back to its recorded previous release, integrate the newer main, rebuild, and repeat. Never force-push or overwrite another completed change.
7. Re-fetch and prove `origin/main`, the live backend source, frontend provenance, and release manifest identify the same full SHA. Release the lock only after this proof.
8. Report the application change complete only with the live dev verification and exact SHA. State that it is staging-ready. Do not use "fixed," "done," "complete," or "live" for work that exists only in a private worktree.

## Reconcile dev before promotion

Do not assume Git, `/home/flask`, a bundle, and the running processes match.

1. Inspect the exact dev Git HEAD, branch, status, task worktrees, active backend process paths, effective systemd base units and drop-ins for every release-managed service, frontend build pointer, referenced bundle, and bundle hash.
2. Inventory every difference needed to reproduce the behavior the user approves on dev. Do not guess which dirty files are junk and do not reset, stash, clean, delete, or overwrite unclassified work.
3. Preserve intended dev-only work on focused task branches. Integrate exact reviewed commits in a new clean release worktree based on current `origin/main`.
4. Resolve combined behavior in source. Do not copy an ad hoc dev bundle or selectively commit files merely because they look relevant.
5. Build once from the clean release commit with the repository build helper. Record the full source SHA, provenance marker, bundle names, and SHA-256 hashes.
6. Before final integration, announce the expected interruption, then acquire `/var/lib/tradewave/release-state/dev-activation.lock` as an atomic directory lock with `mkdir` and write its owner metadata. Refuse an existing lock unless its owner explicitly hands it off or the owner records a stale-lock override. Refetch `origin/main`, integrate, and record the exact candidate SHA and evidence in `dev_coordination`. Activate that exact candidate on dev using the documented runtime model. Keep the lock through runtime/browser verification and the final `origin/main` identity check, then release only the lock owned by this release and record the release event.
7. Run focused tests, the combined safe suite, required contract checks, and real browser assertions. Exercise the changed behavior, not only feature strings or HTTP 200 responses.
8. When the clean candidate exactly reproduces the captured dev behavior and all required gates pass, bind the user's staging-deploy request as dev approval against the recorded commit and composite artifact hash. Do not request redundant approval. If parity is not proven, do not bind approval or promote.

If no clean commit and artifact reproduce approved dev behavior, the release is blocked. Do not promote.

For the first release under this policy, declare a one-time `baseline-reconciliation` release. Inventory and preserve all dev-only work, establish one clean `origin/main` commit and artifact that reproduce approved dev behavior, and atomically write `/var/lib/tradewave/release-state/baseline.json`. Record the marker path, exact release SHA, completion time, and evidence in the manifest's `baseline` object. Later standard releases require that completed marker and do not reopen the historical inventory.

## Maintain the release manifest

Store state on the dev server at `/var/lib/tradewave/release-state/<release-id>/release.json`, with `/var/lib/tradewave/release-state/active.json` identifying the active release. Never share this parent with release checkouts, builds, worktrees, or cleanup targets. Validate it with `ops/validate_release_manifest.py` before every promotion write and terminal status transition.

Record at minimum:

- release ID, manager, requested target, status, created/updated times;
- the baseline marker state and dev activation coordination/lock state;
- base and release branch, included handoff SHAs, full release SHA, remote ref state;
- frontend artifact paths and hashes, backend/source fingerprint, effective runtime paths;
- test, contract, browser, and environment-verification evidence;
- dev and staging approvals tied to the exact SHA and the composite `artifacts.manifest_sha256`; compute it from canonical JSON containing `git.release_sha`, `artifacts.backend_fingerprint`, and the path-sorted frontend artifact records, excluding the hash field itself; backend-only releases still bind the active frontend record;
- typed runtime, contract, and browser gates;
- out-of-band changes and their classification;
- snapshots, concrete backend and frontend rollback pointers and commands (record the unchanged pointer when a component is unaffected), deployment events, and known risks;
- who authored and who executed every state-changing event.

Use atomic writes and keep append-only deployment events, starting with the release-ownership event. A required gate is not valid until it ran, passed, and contains evidence. An environment may be `verified` only when all four typed gates passed. A blocking out-of-band item forbids a deployed, approved-for-next-stage, or complete status. Handoffs update the manifest before the current manager stops.

## Promote the immutable release

For each environment, in order:

1. Verify preconditions before any write. Snapshot or capture rollback state as required. For staging, perform these actions autonomously under the staging-deploy authorization.
2. Reconcile target out-of-band state. Compare tracked files with their Git objects, effective systemd configuration and all release-managed process paths with the intended runtime model, and the active frontend hash with its provenance. Classify and preserve every difference. Any unclassified or blocking difference stops promotion; never overwrite it silently.
3. Require `origin/main` to equal the exact release SHA before staging. Lock that SHA in the manifest and require it to remain unchanged through staging approval and production promotion.
4. Promote the exact dev-approved source SHA and exact frontend artifact. Do not rebuild, re-merge, or substitute a later `main`.
5. Confirm target Git cleanliness and ownership without discarding target data.
6. Apply migrations/configuration only when listed in the manifest and approved by the runbook.
7. Activate the release through the actual runtime mechanism. Copying files to `/home/flask` is not activation when systemd uses a release pointer.
8. Inspect effective unit configuration, including drop-ins, and verify the running processes' working directories and command lines. Resolve conflicting base-unit and drop-in deployment models before promotion; detection alone is insufficient.
9. Verify nginx/index references the expected frontend bundle and hash. Confirm backend/source fingerprints.
10. Run service and route checks, the release-specific contract checks, and at least one real browser assertion for affected UI workflows.
11. On staging failure, automatically roll back inside the manager-started deployment command and verify the restored state. If rollback fails, mark `rollback_required`, stop, and report the exact live state. For production, follow the separate operator rule. Never report success because another verifier printed `CLEAN`.
12. Record results. Complete a requested staging release after verification without asking for another approval; any later production promotion remains a new explicit request.

Staging is mandatory before production. Production must use the same SHA and artifacts that passed staging.

## Required Wave Viewer regression gates

Until superseded by a tested repository gate, include both:

1. A level-1/free-tier contract check that loads a real US or INDX pattern, requires non-empty `ChartData4`, and proves the echoed `request.entry_date` matches the requested US market date. Include UTC/US-evening coverage when date behavior is relevant.
2. A browser check that signs in as a level-1/date-locked user, loads the app, clicks an opportunity row, verifies a canvas exists in `.seasonal-barchart-parent`, and verifies the `.barchart-background` loading/empty watermark is gone after success.

For any release touching current-date logic, require both ordinary-time and UTC/US-evening contract evidence. Do not pass until application code derives the US market date explicitly from `America/New_York`, independent of host timezone. Changing a box timezone or relaxing the frontend response guard is not an acceptable repair.

Staging intentionally contains only US and INDX market data. Missing ETF, COMM, FOREX, FOREX_LQ, CC, GBOND, LSE, and TO symbol lists and the updater's corresponding aggregate `ok:false` are expected. Do not add those datasets or storage, and do not choose them for staging contract tests.

Feature-marker greps, unit tests, build success, and HTTP 200 checks do not replace these gates.

## Release risk records

Read every unresolved dated record under `ops/release-risks/` and seed its still-current items into the manifest's `known_risks` and `out_of_band_changes`. Reverify rather than copying old status forward. Do not embed changing environment state in this skill.

Do not silently repair a risk while asked only to inspect or create policy. Record proposed code changes separately.

## Handoff and completion

Before handing to another Codex, Claude, or human manager:

1. Stop new mutations.
2. Update the manifest atomically with the last completed gate, exact active pointers, pending steps, approvals still required, risks, and rollback commands.
3. Commit and push any repository work from a clean worktree.
4. Name the full commit SHAs and artifact hashes. Do not rely on prose such as “latest dev.”
5. Require the next manager to independently re-read the manifest and verify live pointers before continuing.

Call application work complete only when dev runs the exact recorded release, freshly fetched `origin/main` equals that SHA, the changed behavior is live-verified, rollback is documented, and the artifact is staging-ready. Call a staging or production release complete only when the requested environment runs the exact recorded release, every required gate passes, rollback is documented, the manifest is final, and no further authorized work remains.
