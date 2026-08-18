# TradeWave release process

This is the shared policy for Codex, Claude, and human operators. ops/OPERATIONS.md contains commands and server details. This document defines ownership, evidence, gates, and approval boundaries.

## The operating model

TradeWave has two intentionally different workflows:

1. **Fast dev completion** happens for every substantive application change unless Afshin says local only or do not deploy. Its purpose is quick feedback and a trustworthy shared dev.
2. **Qualified release** begins only when Afshin says Deploy to staging. Its purpose is broad regression protection, deterministic promotion, and recoverable staging/production operations.

The flow is:

    task worktree -> focused tests -> affected build when required -> short dev activation
      -> changed behavior verified on dev -> commit/main parity -> staging-ready
      -> full staging qualification -> exact staging artifact -> production

Staging-ready is a lightweight state: the change is clean, committed, pushed, running on dev, and focused-tested. It does not mean the full regression, release manifest, staging inventory, account-tier matrix, snapshots, or rollback rehearsal have run.

The live dev site remains the product-behavior source of truth. A dirty filesystem or private worktree is not dev. Application work is not fixed, done, complete, or live until the requested behavior is verified on dev. Analysis and documentation-only work, and explicit local-only work, are exceptions.

Documentation/policy-only commits may advance origin/main without rebuilding dev when the application tree is unchanged. For application work, current main's application tree, active backend source, and affected artifact provenance must match at completion.

## Concurrent agents

Claude and Codex may develop concurrently in separate task branches and worktrees based on current origin/main. They never share a dirty checkout and never ask Afshin to coordinate branches.

Only environment mutation is serialized:

- The dev lock is held only for the short final ref check, activation, live smoke, main update, and parity proof.
- Coding, focused tests, and the first build happen before the lock.
- Staging and production have one qualified release manager at a time.
- If the dev lock is busy, a finishing session preserves its exact pushed commit and waits or hands it off internally.

## Roles

### Development session

- Fetch current origin/main and use one clean task worktree.
- Own one concern, review the complete diff, and commit/push only intended changes.
- Run focused affected-surface tests and proportional high-risk checks.
- Continue automatically through fast dev completion unless explicitly told not to deploy to dev.
- Do not touch staging or production without their separate authorization.

### Dev activation owner

- This is normally the development session itself, not a separate conversation.
- Owns only the brief dev activation window.
- Refetches main after locking, preserves completed work, activates through real runtime pointers, proves the changed behavior, advances main without force, proves parity, and releases the lock.

### Qualified release manager

- Begins when staging is requested.
- Assigns one release ID, creates and maintains the full manifest, runs complete qualification, locks the exact SHA/artifact, audits targets, promotes, verifies, and executes staging rollback.
- Is replaceable only through a recorded handoff. Chat history is not release state.

### Owner

- A substantive application-change request authorizes routine Git work and dev-only completion. Afshin does not manage branches, commits, worktrees, builds, handoffs, or locks.
- Deploy to staging approves the behavior running on dev at request time as the target and authorizes the complete automated repository/dev/staging workflow.
- Production requires a later explicit request plus current-day appserver and webserver snapshots.
- Production writes remain human-executed unless policy explicitly changes.

## Authorization boundaries

- Inspect, compare, diagnose, explain, and is-this-ready requests are read-only.
- Fix, change, build, and update application behavior authorize fast dev completion only.
- Deploy to staging authorizes full qualification and staging execution, including automatic rollback. Do not pause for routine Git, testing, build, activation, or staging commands.
- Staging approval never authorizes production.
- Approval is bound to the exact SHA, artifact hash, environment, and release.
- Pause only for a real product-intent conflict, unclassified valuable work that needs an owner decision, missing authority/credentials, inability to prove parity, or unsafe/failed rollback.

## Fast dev completion gates

Agents perform this sequence automatically:

1. Fetch origin/main. Move task-owned work out of stale or unrelated dirty checkouts into a clean current-main task worktree.
2. Review the full diff and run focused tests for the changed behavior. Add only relevant checks for migrations, auth, billing, security, destructive data paths, or deployment infrastructure.
3. Commit and push the task-owned change.
4. Integrate it in a clean worktree on the newest origin/main.
5. Build only what changed:
   - React source: one npm run build with provenance.
   - Backend only: no React rebuild.
   - Static generator/template: activate source, then run only the affected generator.
   - Documentation/policy only: no runtime activation.
6. After testing/building, atomically acquire /var/lib/tradewave/release-state/dev-activation.lock and write owner/task metadata. Refetch main immediately.
7. If main moved, release the lock, integrate it, and rerun only checks/builds affected by the new combination. Then retry.
8. Record previous affected pointers. Activate the candidate through the effective systemd/nginx/release-pointer model and restart only affected services.
9. Prove the changed behavior live. UI work requires a rendered interaction check; backend/API work requires the relevant live contract or route; static work requires a content assertion. Build success, string markers, and HTTP 200 alone are not behavior proof.
10. Advance origin/main with a non-forced concurrency-safe push. If it fails because main moved, roll dev back to recorded pointers and retry from newer main.
11. Refetch and prove current main's application tree, active backend source, and affected artifact provenance match. Release the lock promptly.

Routine dev completion does not assign a release ID, create a full manifest, run the full regression suite, audit staging, execute a broad entitlement/browser matrix, take snapshots, or rehearse complete staging rollback.

## Begin staging qualification

A plain Deploy to staging request is sufficient. The manager:

1. Captures the behavior currently running on dev as the approved target.
2. Assigns a release ID such as tw2-YYYYMMDD-NN and creates release state.
3. Inventories exact completed task SHAs and actual dev runtime pointers. It preserves all unclassified work and never resets, stashes, cleans, deletes, or overwrites it.
4. Confirms origin/main has the same application tree as live dev. A docs-only main advance is allowed.
5. Creates a clean release candidate at the exact final main SHA.
6. Runs focused integration checks, the complete safe regression suite, required release-specific contracts, and required Wave Viewer/account-tier/browser gates.
7. Builds one provenance-stamped immutable artifact from that exact SHA and records backend/source and frontend hashes.
8. Reconciles dev to the qualified artifact and reruns required dev runtime/contract/browser evidence.
9. Binds the owner's staging request to the full SHA and composite artifact hash.
10. Sets main_locked_sha. Main, source, and artifacts stay frozen through staging approval and production.

If clean source and artifact cannot reproduce the approved dev behavior, staging is blocked.

## Qualified release state

Store each qualified release manifest on dev at:

    /var/lib/tradewave/release-state/<release-id>/release.json

Store current qualified release ownership at:

    /var/lib/tradewave/release-state/active.json

Initialize the directory once with sudo bash ops/init_release_state.sh. It must be flask:flask mode 0750, refuse symlink/non-directory collisions, and remain separate from checkouts and builds. Validate manifests with ops/validate_release_manifest.py before promotion writes and terminal transitions. Never store secrets, credentials, customer content, keys, or tokens.

The manifest records identity/ownership, included task SHAs, exact release/main SHA, artifact hashes, active paths, tests, typed runtime/contract/browser evidence, approvals, target drift, snapshots, rollback, risks, and append-only events naming author and executor.

artifacts.manifest_sha256 is the composite release hash. Compute SHA-256 over UTF-8 canonical JSON with sorted keys and no insignificant whitespace containing git.release_sha, artifacts.backend_fingerprint, and frontend artifact records sorted by path, excluding manifest_sha256. Backend-only releases still record the unchanged active frontend artifact.

A required gate is valid only after it ran, passed, and contains evidence. An environment cannot be verified until every required typed gate passed. A blocking out-of-band item forbids deployed, approved-for-next-stage, or complete status.

## Staging gates

1. Confirm exclusive qualified-release ownership and a valid dev-approved manifest.
2. Before any write, audit tracked target files, effective systemd units and all drop-ins, every release-managed process path, nginx/docroots, and the active frontend hash/provenance. Classify and preserve every difference.
3. Capture executable rollback: previous backend pointer/SHA, previous frontend pointer/hashes, and exact commands. Record unchanged component pointers too.
4. Require origin/main to equal main_locked_sha.
5. Promote the exact qualified source and dev-built artifact. Do not rebuild, merge, or substitute.
6. Apply only recorded migrations/configuration.
7. Activate through the actual runtime mechanism and verify effective units/drop-ins and live process paths.
8. Verify backend fingerprints, frontend index/bundle/hash, nginx routes, services, health, release contracts, entitlements, and affected rendered behavior.
9. The manager-started staging command contains automatic rollback. A failed post-write gate triggers rollback and restoration verification. Failed rollback sets rollback_required and stops writes.
10. Record results and complete staging without another approval request.

verify_deploy.sh saying CLEAN is supporting evidence only and never overrides runtime or browser evidence.

## Production gates

1. Require the staging-approved manifest for the same SHA and artifact hashes.
2. Require explicit production approval for that release.
3. Require current-day snapshots of both production servers.
4. Rerun non-mutating preflights and confirm rollback.
5. Confirm origin/main still equals main_locked_sha.
6. Promote without rebuilding or re-merging and repeat runtime, fingerprint, bundle, health, contract, entitlement, and browser verification.
7. The human operator executes production writes. On failure, use the operator-started automatic rollback when available or immediately provide the exact recorded rollback.

## Required Wave Viewer release checks

Every affected staging or production release includes:

1. A real level-1/date-locked US or INDX pattern request with non-empty ChartData4 and echoed request.entry_date equal to the requested US market date. Cover ordinary and UTC/US-evening time when date logic is relevant.
2. A signed-in level-1 browser flow that clicks an opportunity row, finds a canvas in .seasonal-barchart-parent, and confirms .barchart-background disappears after success.

Current-date logic must derive US market date from America/New_York. Changing server timezone or weakening the response guard is not a repair. Staging intentionally has only US and INDX data; absent market updater failures are expected and those markets are not release-test inputs.

These broad checks run during staging qualification. The fast dev loop runs the smallest real browser/contract smoke that proves the behavior changed.

## Effective-runtime evidence

For a qualified target, evidence includes the intended release SHA/ref, effective unit fragments and drop-ins, live process command/working directory, backend fingerprint, frontend pointer/index/bundle/hash, nginx route/docroot, and required contract/browser results. Desired files existing in a checkout do not prove they are running.

## Risks and handoff

Read unresolved records under ops/release-risks/ during staging/production qualification, reverify them, and seed current items into the manifest. Do not burden unrelated routine dev changes with a full target-risk audit.

An unfinished dev handoff needs the exact pushed SHA, focused test results, risk/config/migration notes, and remaining work. It does not need a release manifest.

A qualified-release handoff atomically records exact pointers, SHAs/hashes, completed and pending gates, approvals, risks, snapshots, and rollback commands before the manager stops.

Application work is complete when it is committed, pushed, running on dev, and live-verified. A staging or production release is complete only when the requested target runs the exact qualified artifact, every mandatory gate passes, rollback is documented, and the manifest is final.
