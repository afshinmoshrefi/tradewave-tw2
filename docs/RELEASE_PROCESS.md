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
- Only the manager may advance release refs, activate dev, promote, or roll back.

### Owner

- Approves the reconstructed dev release tied to a full Git SHA and artifact hash.
- Approves staging before any production action.
- Confirms current-day production web and appserver snapshots before production promotion.

## Release state

Store each manifest on dev at:

```text
/home/tradewave-releases/<release-id>/release.json
```

Store the current ownership record at:

```text
/home/tradewave-releases/active.json
```

Validate release manifests with `ops/release_manifest.schema.json`. Do not store keys, tokens, secret values, customer content, or credentials.

The manifest records identity, ownership, included handoffs, source SHA, remote refs, artifact hashes, active runtime paths, tests, browser/contract evidence, approvals, snapshots, rollback, risks, and append-only events. Write manifest updates atomically.

## Authorization boundaries

- “Inspect,” “compare,” “diagnose,” and “is this ready?” are read-only.
- “Deploy to staging” authorizes release preparation and staging only.
- Staging success does not authorize production.
- Production requires explicit approval for the exact staging-approved release plus confirmation of current-day snapshots of both production servers.
- Approval never transfers to a different SHA, artifact, target, or later `main`.
- Follow `CLAUDE.md` for who runs live write commands. When agents are limited to authoring commands, the operator executes them.

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
2. Capture rollback state and verify the target preflight without mutation.
3. Advance `main` only to the tested release SHA when the runbook requires it.
4. Promote the exact source SHA and dev-built frontend artifact. Never rebuild or merge between dev approval and staging.
5. Confirm effective systemd base units and drop-ins resolve to the release. Confirm live process paths, not only files copied to `/home/flask`.
6. Confirm nginx/index references the expected bundle and its hash matches dev.
7. Run health/routes, release contracts, and real browser assertions under the relevant entitlement.
8. Roll back on any required failure and preserve evidence.
9. Record results and wait for explicit owner approval before production.

## Production gates

1. Require a staging-approved manifest for the same full SHA and artifact hashes.
2. Require explicit production approval in the current release conversation.
3. Require confirmation of current-day snapshots for production web and appserver.
4. Re-run non-mutating preflights and confirm rollback commands.
5. Promote without rebuilding or re-merging.
6. Repeat active-runtime, fingerprint, bundle, health, contract, and browser verification.
7. Roll back immediately when a required gate fails, then record the failure and active post-rollback state.

## Required Wave Viewer checks

Until automated gates with equivalent coverage are committed and proven, every affected release includes:

1. A real level-1/free-tier pattern request with non-empty `ChartData4` and an echoed `request.entry_date` equal to the requested US market date. Exercise the UTC/US-evening boundary when date logic is in scope.
2. A signed-in browser flow that clicks an opportunity row, finds a canvas inside `.seasonal-barchart-parent`, and confirms `.barchart-background` disappears after a successful load.

These checks catch failures that compilation, unit tests, HTTP status checks, and feature-marker searches cannot.

## Effective-runtime verification

A target is not verified merely because its checkout is clean or the desired files exist. Evidence must include:

- full intended release SHA and remote ref;
- `systemctl cat` plus effective fragment/drop-in paths for affected services;
- live process command line and working directory resolving to the intended release;
- active backend/source fingerprint;
- frontend build pointer, index-referenced bundle, and exact bundle hash;
- relevant nginx route/docroot;
- contract and browser results.

If `ops/deploy.sh`, `verify_deploy.sh`, or another tool reports success while this evidence disagrees, the release failed.

## Known unresolved blockers as of 2026-08-13

These were reported in the Wave Viewer staging investigation and require current read-only confirmation before the next promotion:

- `ops/deploy.sh` can update base unit paths or `/home/flask` while effective systemd drop-ins continue running `.tw2-app-current` from an older release.
- `verify_deploy.sh` can report `CLEAN` without validating effective runtime pointers or rendered product behavior.
- The scheduled `TW2_UPDATE_SERVER` may still use a public endpoint that returns 403 from Kamatera.
- Host-local `date.today()` may disagree with the US market date for date-locked/free-tier users after 00:00 UTC.

Do not treat this list as permission to alter servers or application code. Diagnose under the request's authorization and propose repairs separately when needed.

## Handoff

Before a manager stops:

- stop new mutations;
- atomically update the manifest with the last completed gate and current active pointers;
- name exact SHAs and hashes;
- record approvals still needed, pending steps, risks, snapshots, and rollback commands;
- commit and push repository work from a clean worktree;
- require the next manager to independently verify the manifest and live pointers.

The release is complete only when the requested target runs the exact recorded release, all mandatory gates pass, rollback is documented, and the manifest is final.
