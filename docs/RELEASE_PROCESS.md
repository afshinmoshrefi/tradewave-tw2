# TradeWave release process

This is the shared release policy for Codex, Claude, and human operators. `ops/OPERATIONS.md` contains commands and server details. This document defines ownership, evidence, gates, and approval boundaries.

## Core invariant

Every requested application change must become part of one reproducible dev release before it is called complete:

```text
requested application change
  -> isolated task commit
  -> clean integration on the newest origin/main
  -> one provenance-stamped frontend artifact
  -> exact activation and live verification on dev
  -> origin/main equals the active dev SHA
  -> staging promotion of the same commit and artifact
  -> production promotion of the same commit and artifact
```

The live dev site is the product-behavior source of truth. A dirty filesystem or a private task worktree is not dev and is not a release artifact. For a substantive application or runtime-visible change, the original change request implicitly authorizes routine Git integration, build, dev activation, and live verification. The session must not call the work fixed, complete, done, or live until the exact combined commit is running on dev, verified there, and equals `origin/main`. The exceptions are an explicit `local only` / `do not deploy` instruction and analysis- or documentation-only work.

This completion rule applies equally to Codex and Claude. They may develop concurrently in separate worktrees, but final integration and dev activation are serialized. The session finishing a change may become the recorded dev-completion manager; one manager means one exclusive mutation owner, not a separate conversation. If another manager owns the window, the finishing session preserves and hands off its exact commit and continues or waits for integration without making the owner coordinate branches.

The cross-agent bootstrap source is `ops/agent-bootstrap/TRADEWAVE_GLOBAL.md`. Install its content as Codex's global TradeWave skill and as Claude Code user memory (`~/.claude/CLAUDE.md`) so a stale worktree cannot hide the current repository controls. Repository policy remains authoritative after bootstrap.

A plain request to "deploy to staging" is intentionally sufficient. It approves the behavior running on dev at request time as the target and authorizes one release manager to automate the complete repository, dev, and staging workflow. The manager must not make the owner restate this document, choose routine commands, or execute staging commands. Production always requires a later explicit request.

The first release under this policy is a one-time `baseline-reconciliation` release. Its job is to inventory `/home/flask` and the active dev runtime, preserve every intended dev-only change on focused task branches, and establish an `origin/main` commit plus immutable artifact that reproduce the approved dev behavior. Atomically write completion to `/var/lib/tradewave/release-state/baseline.json` and record its path, exact release SHA, completion time, and evidence in the manifest's `baseline` object. Later standard and hotfix releases require that completed marker, start from that baseline, and may not reopen the historical dirty-dev inventory; they still perform the normal target out-of-band gate. An emergency rollback is never blocked merely because the baseline marker is pending, but it must still record exact current and restored pointers and evidence.

## Roles

### Development session

- Start from freshly fetched `origin/main` in one task branch and isolated worktree. Never continue application work in an old dirty worktree merely because it was already open.
- Commit and push only the task's intended changes and record the full SHA, tests, risks, configuration/migration requirements, and rollback notes.
- For an application/runtime change, continue through dev completion by becoming the recorded manager or handing the commit to the current manager internally. Do not stop at a local test or handoff and call the task complete.
- Do not touch staging or production without their separate explicit authorization.

### Deployment manager

- One manager owns one release ID at a time.
- A development session may assume this role for dev completion when no other manager owns the mutation window.
- The manager inventories handoffs and the actual dev runtime, integrates exact commits on the newest `origin/main`, builds the immutable release, and owns all activation and promotion evidence.
- The manager is replaceable only through a recorded handoff. Chat history is not release state.
- Only the manager may perform final integration, advance release refs, build artifacts, activate dev, or execute the authorized staging promotion and rollback.

### Owner

- By requesting a substantive application change, authorizes the agents to handle branches, commits, pushes, clean integration, and dev-only activation and verification required to leave the change live on dev and staging-ready. The owner does not manage these technical steps.
- By requesting staging deployment, approves the currently running dev behavior as the target. After exact automated parity is proven, the manager binds that request to the resulting full Git SHA and composite artifact hash without requesting redundant approval.
- Approves staging before any production action.
- Confirms current-day production web and appserver snapshots before production promotion.
- Executes or designates a human operator to execute production write commands. Staging is executed by the release manager under the staging-deploy authorization.

## Release state

Store each manifest on dev at:

```text
/var/lib/tradewave/release-state/<release-id>/release.json
```

Store the current ownership record at:

```text
/var/lib/tradewave/release-state/active.json
```

Initialize this dev-only state path once with:

```text
sudo bash /home/flask/ops/init_release_state.sh
```

The script establishes `/var/lib/tradewave/release-state` as `flask:flask` mode `0750` and refuses symlink or non-directory path collisions. It does not create a release or acquire the activation lock. This durable state directory must never share a parent with release checkouts, builds, worktrees, or cleanup targets. Validate release manifests with `ops/validate_release_manifest.py` before every promotion write and terminal status transition. Do not store keys, tokens, secret values, customer content, or credentials.

The manifest records identity, ownership, the baseline marker, dev activation coordination, included handoffs, source SHA, the locked `main` SHA, artifact hashes, active runtime paths, typed browser/contract/runtime evidence, approvals, out-of-band changes, snapshots, concrete rollback, risks, and append-only events. Every event records who authored it and who executed it. The first event records release ownership. Write manifest updates atomically.

`artifacts.manifest_sha256` is the composite release hash used at every approval boundary; it is not a self-hash of `release.json`. Compute SHA-256 over UTF-8 canonical JSON with sorted keys and no insignificant whitespace containing `git.release_sha`, `artifacts.backend_fingerprint`, and the frontend artifact records sorted by path, excluding `manifest_sha256` itself. It exists for backend-only releases too; record the unchanged active frontend artifact so the full running product remains bound. Every approved `artifact_sha256` must equal it. A required gate is valid only after it ran, passed, and contains evidence; an environment cannot be `verified` unless all four typed gates passed. Any `blocking:true` out-of-band record prevents a deployed, approved-for-next-stage, or complete release status.

## Authorization boundaries

- A request to fix, change, build, or update TradeWave application behavior authorizes the routine repository writes and dev-only activation necessary to finish that change on the live dev site. It does not authorize staging or production. An explicit `local only` or `do not deploy` instruction overrides this default.

- “Inspect,” “compare,” “diagnose,” and “is this ready?” are read-only.
- “Deploy to staging” authorizes the sole manager to perform every required repository, dev, and staging action through verified completion, including preserving and pushing intended work, advancing `origin/main` after validation, and executing automatic staging rollback. It is also approval of the behavior running on dev when requested, conditional on exact automated reconstruction.
- Do not pause for routine Git, build, test, dev activation, staging execution, or rollback choices. Pause only for an unclassified change requiring an owner decision, inability to prove dev parity, unavailable required authority/credentials, or unsafe/failed rollback.
- Staging success does not authorize production.
- Production requires explicit approval for the exact staging-approved release plus confirmation of current-day snapshots of both production servers.
- Approval never transfers to a different SHA, artifact, target, or later `main`.
- The release manager may execute repository, dev, and staging write commands authorized by a staging-deploy request and records itself as executor. Production remains read-only for agents; Afshin or his designated human operator executes production writes.
- A manager-started staging deployment must contain automatic rollback. If a post-write gate fails, run rollback automatically and verify the restored state. If rollback fails, mark `rollback_required`, record the still-active risk, stop further writes, and report the exact live state. Production retains the operator/automatic-rollback rule.

## Git and integration gates

1. Never develop in the shared active `/home/flask` checkout.
2. Run server Git operations as `flask`, not `root`.
3. Never reset, stash, clean, delete, or overwrite unclassified dirty dev work.
4. Before planning or editing, fetch current remote refs. If required policy files are absent locally, inspect them from current `origin/main` (for example with `git show`) before declaring them missing; then create a fresh task worktree from that ref.
5. Verify every handoff SHA exists remotely and review each task diff independently.
6. Acquire the dev coordination lock before final integration, refetch `origin/main`, and integrate the task on top of every already completed change. Never overwrite a newer dev completion with an older branch.
7. Reconcile the combined source against the requested behavior. Preserve missing dev changes as explicit task commits; do not sweep unrelated files into the release.
8. Run focused tests after risky merges and the combined safe suite before building. Record the full candidate SHA.

If the approved dev behavior cannot be reproduced from the clean release candidate, stop. Do not promote the dirty checkout or its ad hoc bundle.

## Build and dev-approval gates

1. Atomically create `/var/lib/tradewave/release-state/dev-activation.lock` with `mkdir` before final integration and write owner/release metadata inside it. Refuse a live lock unless its owner explicitly hands it off, or record evidence and owner approval for a stale-lock override. Hold the lock through activation, verification, and the final remote-ref check. A competing Claude or Codex completion waits; it does not ask the owner to order branches.
2. Build React once from the exact clean candidate with `ops/build_react_release.sh`.
3. Require `.tradewave-source-sha` to equal the release SHA and record all active frontend bundle names and SHA-256 hashes.
4. Announce the exact SHA and expected interruption to active dev sessions. Record the lock owner, SHA, and evidence in `dev_coordination`.
5. Activate the candidate on dev through the documented runtime model and verify effective units/drop-ins, process working directories/command lines, backend fingerprints, frontend symlinks/index, bundle hashes, nginx routing, release contracts, and rendered browser behavior.
6. After live verification, advance `origin/main` to the exact candidate using a non-forced, concurrency-safe update. If the remote ref changed unexpectedly, roll dev back to its recorded previous release, integrate the newly completed work, rebuild, and retry while retaining coordination. Never force-push or leave a completed dev state that differs from `origin/main`.
7. Verify the active dev source SHA, artifact provenance, and freshly fetched `origin/main` are identical. Only then release the lock and call the application change complete and staging-ready.
8. If a staging deployment was requested, bind that request as owner approval against the same full SHA and composite `artifacts.manifest_sha256`; do not ask again. Otherwise stop after reporting the verified dev SHA and staging readiness.

## Staging gates

1. Confirm exclusive manager ownership and a complete dev-approved manifest.
2. Inspect and reconcile target out-of-band state before any write. Compare every tracked target file with its Git object, inspect effective unit fragments and drop-ins for every release-managed service, verify live process paths, and hash the active frontend. Classify and preserve every difference in `out_of_band_changes`. Any unclassified or blocking item stops promotion.
3. Capture concrete rollback state: previous backend SHA or release pointer, previous frontend pointer and hashes, and exact commands. Both references are required even when one component is unchanged. If either affected component lacks a safe executable automatic rollback, stop.
4. Because `ops/deploy.sh` deploys `origin/main`, require `origin/main` to equal the exact tested release SHA before promotion. Record that SHA as `main_locked_sha`. It must not advance between staging deployment, staging approval, and production promotion.
5. Promote the exact source SHA and dev-built frontend artifact. Never rebuild or merge between dev approval and staging.
6. Confirm effective systemd base units and drop-ins resolve to one release model and the intended release. Confirm all release-managed live process paths, not only files copied to `/home/flask`. A conflicting base-unit/release-pointer model must be resolved, not merely observed.
7. Confirm nginx/index references the expected bundle and its hash matches dev.
8. Run health/routes, release contracts, and real browser assertions under the required entitlement.
9. Execute staging autonomously with automatic rollback built into the manager-started command. On failure, verify rollback; if rollback fails, mark `rollback_required` and stop.
10. Record results and complete the staging request. Explicit owner approval is still required before any later production request.

## Production gates

1. Require a staging-approved manifest for the same full SHA and artifact hashes.
2. Require explicit production approval in the current release conversation.
3. Require confirmation of current-day snapshots for production web and appserver.
4. Re-run non-mutating preflights and confirm rollback commands.
5. Confirm `origin/main` still equals `main_locked_sha`, then promote without rebuilding or re-merging.
6. Repeat active-runtime, fingerprint, bundle, health, contract, and browser verification.
7. On failure, the operator-started production command performs automatic rollback when available; otherwise the manager immediately authors the exact rollback for operator execution. Record and verify the actual post-rollback state.

## Required Wave Viewer checks

Until automated gates with equivalent coverage are committed and proven, every affected release includes:

1. A real level-1/free-tier US or INDX pattern request with non-empty `ChartData4` and an echoed `request.entry_date` equal to the requested US market date. Exercise both ordinary time and the UTC/US-evening boundary when date logic is in scope.
2. A browser flow signed in as a level-1/date-locked user that clicks an opportunity row, finds a canvas inside `.seasonal-barchart-parent`, and confirms `.barchart-background` disappears after a successful load.

These checks catch failures that compilation, unit tests, HTTP status checks, and feature-marker searches cannot.

For any release touching current-date behavior, do not pass until the application derives US market date explicitly from `America/New_York`, independent of host timezone. Changing server timezone or weakening the frontend response guard is not an acceptable repair.

Staging intentionally contains only US and INDX market data to control SSD cost. ETF, COMM, FOREX, FOREX_LQ, CC, GBOND, LSE, and TO symbol lists are intentionally absent. The updater can therefore report aggregate `ok:false` for those eight expected absences even when US and INDX completed successfully. Do not add the absent datasets or storage, rerun a successful catch-up, or use absent markets for staging contracts.

## Effective-runtime verification

A target is not verified merely because its checkout is clean or the desired files exist. Evidence must include:

- full intended release SHA and remote ref;
- `systemctl cat` plus effective fragment/drop-in paths for every release-managed service, including services not expected to change;
- live process command line and working directory resolving to the intended release;
- active backend/source fingerprint;
- frontend build pointer, index-referenced bundle, and exact bundle hash;
- relevant nginx route/docroot;
- contract and browser results.

If `ops/deploy.sh`, `verify_deploy.sh`, or another tool reports success while this evidence disagrees, the release failed.

## Dated release risks

Changing environment status does not belong in permanent policy. Read every unresolved record under `ops/release-risks/`, reverify it read-only, and seed still-current items into the new manifest's `known_risks` and `out_of_band_changes`. Do not treat a risk record as permission to alter a server or application code.

## Handoff

Before a manager stops:

- stop new mutations;
- atomically update the manifest with the last completed gate and current active pointers;
- name exact SHAs and hashes;
- record approvals still needed, pending steps, risks, snapshots, and rollback commands;
- commit and push repository work from a clean worktree;
- require the next manager to independently verify the manifest and live pointers.

The release is complete only when the requested target runs the exact recorded release, all mandatory gates pass, rollback is documented, and the manifest is final.
