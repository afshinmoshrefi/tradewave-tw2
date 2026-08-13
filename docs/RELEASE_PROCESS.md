# TradeWave release process

This is the shared release policy for Codex, Claude, and human operators. `ops/OPERATIONS.md` contains commands and server details. This document defines ownership, evidence, gates, and approval boundaries.

## Core invariant

The version approved on dev must become one reproducible release:

```text
approved dev behavior
  -> clean Git commit
  -> one provenance-stamped frontend artifact
  -> exact activation on dev
  -> staging promotion of the same commit and artifact
  -> production promotion of the same commit and artifact
```

Dev is the product-behavior source of truth. A dirty dev filesystem is not a release artifact. Before promotion, the release manager must preserve the desired dev changes in Git, rebuild from a clean commit, activate that candidate on dev, and reconfirm the behavior.

The first release under this policy is a one-time `baseline-reconciliation` release. Its job is to inventory `/home/flask` and the active dev runtime, preserve every intended dev-only change on focused task branches, and establish an `origin/main` commit plus immutable artifact that reproduce the approved dev behavior. Record completion in `/var/lib/tradewave/release-state/baseline.json`. Later standard releases start from that baseline and may not reopen the historical dirty-dev inventory; they still perform the normal target out-of-band gate.

## Roles

### Development session

- Use one task branch and isolated worktree.
- Commit and push only the task's intended changes.
- Provide the full SHA, tests, risks, configuration/migration requirements, and rollback notes in a handoff.
- Do not integrate, update `main`, build the release artifact, deploy, or move environment pointers.

### Deployment manager

- One manager owns one release ID at a time.
- The manager inventories handoffs and the actual dev runtime, integrates exact commits, builds the immutable release, and owns all promotion evidence.
- The manager is replaceable only through a recorded handoff. Chat history is not release state.
- Only the manager may integrate, advance release refs, build artifacts, activate dev, author promotion commands, or author rollback commands.

### Owner

- Approves the reconstructed dev release tied to a full Git SHA and artifact hash.
- Approves staging before any production action.
- Confirms current-day production web and appserver snapshots before production promotion.
- Executes or designates a human operator to execute staging and production write commands authored by the manager.

## Release state

Store each manifest on dev at:

```text
/var/lib/tradewave/release-state/<release-id>/release.json
```

Store the current ownership record at:

```text
/var/lib/tradewave/release-state/active.json
```

This durable state directory must never share a parent with release checkouts, builds, worktrees, or cleanup targets. Validate release manifests with `ops/release_manifest.schema.json`. Do not store keys, tokens, secret values, customer content, or credentials.

The manifest records identity, ownership, included handoffs, source SHA, the locked `main` SHA, artifact hashes, active runtime paths, typed browser/contract/runtime evidence, approvals, out-of-band changes, snapshots, concrete rollback, risks, and append-only events. Every event records who authored it and who executed it. Write manifest updates atomically.

## Authorization boundaries

- “Inspect,” “compare,” “diagnose,” and “is this ready?” are read-only.
- “Deploy to staging” authorizes release preparation and staging only.
- Staging success does not authorize production.
- Production requires explicit approval for the exact staging-approved release plus confirmation of current-day snapshots of both production servers.
- Approval never transfers to a different SHA, artifact, target, or later `main`.
- Agents may write in approved isolated repository worktrees and may activate an approved candidate on dev. They never execute staging or production write commands. The deployment manager performs read-only remote inspection, authors exact commands, and records them; Afshin or his designated human operator executes them.
- An operator-started deployment command may contain automatic rollback. Otherwise, when a post-write gate fails, the manager immediately authors the exact rollback, marks the release `rollback_required`, records the still-active risk, and stops. The rollback is not complete until the operator confirms execution and the manager verifies the resulting state.

## Git and integration gates

1. Never develop in the shared active `/home/flask` checkout.
2. Run server Git operations as `flask`, not `root`.
3. Never reset, stash, clean, delete, or overwrite unclassified dirty dev work.
4. Fetch current remote refs and create a clean integration worktree from `origin/main`.
5. Verify every handoff SHA exists remotely and review each task diff independently.
6. Reconcile the combined source against the behavior the owner approves on dev. Preserve missing dev changes as explicit task commits; do not sweep unrelated files into the release.
7. Run focused tests after risky merges and the combined safe suite before building.
8. Commit and push the clean release candidate. Record its full SHA.

If the approved dev behavior cannot be reproduced from the clean release candidate, stop. Do not promote the dirty checkout or its ad hoc bundle.

## Build and dev-approval gates

1. Build React once from the exact clean candidate with `ops/build_react_release.sh`.
2. Require `.tradewave-source-sha` to equal the release SHA.
3. Record all active frontend bundle names and SHA-256 hashes.
4. Activate the candidate on dev through the same documented runtime model used by the service configuration.
5. Verify effective systemd units and drop-ins, process working directories/command lines, backend fingerprints, frontend symlinks/index, bundle hashes, and nginx routing.
6. Run release-specific contract checks and rendered browser tests. Tests and bundle-string greps are supporting evidence, not product verification.
7. Record owner approval against the full SHA and artifact hash.

## Staging gates

1. Confirm exclusive manager ownership and a complete dev-approved manifest.
2. Inspect and reconcile target out-of-band state before any write. Compare every tracked target file with its Git object, inspect effective unit fragments and drop-ins for every release-managed service, verify live process paths, and hash the active frontend. Classify and preserve every difference in `out_of_band_changes`. Any unclassified or blocking item stops promotion.
3. Capture concrete rollback state: previous backend SHA or release pointer, previous frontend pointer and hashes, and exact operator commands. If backend rollback is not safe and executable, stop.
4. Because `ops/deploy.sh` deploys `origin/main`, require `origin/main` to equal the exact tested release SHA before promotion. Record that SHA as `main_locked_sha`. It must not advance between staging deployment, staging approval, and production promotion.
5. Promote the exact source SHA and dev-built frontend artifact. Never rebuild or merge between dev approval and staging.
6. Confirm effective systemd base units and drop-ins resolve to one release model and the intended release. Confirm all release-managed live process paths, not only files copied to `/home/flask`. A conflicting base-unit/release-pointer model must be resolved, not merely observed.
7. Confirm nginx/index references the expected bundle and its hash matches dev.
8. Run health/routes, release contracts, and real browser assertions under the required entitlement.
9. Use automatic rollback only when it is built into the operator-started command. Otherwise author the exact rollback, mark `rollback_required`, and wait for operator execution before verifying the result.
10. Record results and wait for explicit owner approval before production.

## Production gates

1. Require a staging-approved manifest for the same full SHA and artifact hashes.
2. Require explicit production approval in the current release conversation.
3. Require confirmation of current-day snapshots for production web and appserver.
4. Re-run non-mutating preflights and confirm rollback commands.
5. Confirm `origin/main` still equals `main_locked_sha`, then promote without rebuilding or re-merging.
6. Repeat active-runtime, fingerprint, bundle, health, contract, and browser verification.
7. On failure, follow the same operator/automatic rollback rule as staging and record the actual post-rollback state.

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
