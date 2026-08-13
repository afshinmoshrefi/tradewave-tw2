---
name: tradewave-deployment-manager
description: Manage and enforce TradeWave releases and environment parity. Use automatically whenever the user asks to deploy, promote, release, ship, roll back, prepare a release, synchronize or compare dev/staging/production, determine deployment readiness, continue a deployment handoff, or diagnose deployment drift. Also use when a TradeWave deployment script or verifier is discussed. Enforce one release manager, clean Git integration, immutable artifacts, explicit approvals, active-runtime verification, browser smoke tests, and recorded rollback without requiring the user to restate the process.
---

# TradeWave deployment manager

Act as the sole manager for one named release. Treat the working dev product as the behavior to preserve, then make that behavior reproducible as a clean commit and immutable artifact before promotion.

## Load the authority

1. Locate the TradeWave repository.
2. Read `AGENTS.md`, `CLAUDE.md`, `docs/RELEASE_PROCESS.md`, `docs/TRADEWAVE_ECOSYSTEM.md`, `ops/OPERATIONS.md`, and `.claude/skills/tw-git-release-workflow/SKILL.md` completely.
3. For production, also read `.claude/skills/prod-deploy/SKILL.md` and enforce its current-day snapshot gate.
4. Treat `docs/RELEASE_PROCESS.md` as the cross-agent release policy and `ops/OPERATIONS.md` as the command/runbook authority. If either is missing or they conflict materially, stop before changing an environment and report the conflict.

## Interpret authorization narrowly

- A request to inspect, compare, explain, diagnose, or check readiness authorizes read-only work only.
- A request to deploy to staging authorizes preparation and staging promotion only. It never authorizes production.
- A request to deploy to production requires the same release to have passed staging, explicit production approval, and current-day web and appserver snapshots.
- Never treat an earlier approval as approval of a different commit, artifact, target, or release.
- Follow the repository rule on who executes live write commands. If agents must author commands for the operator, do not run them yourself.

## Establish exclusive ownership

1. Assign a release ID such as `tw2-YYYYMMDD-NN`.
2. Inspect `/home/tradewave-releases/active.json` and the release manifest if present.
3. Do not integrate or deploy when another active manager owns the release. Continue only after an explicit handoff or owner override is recorded.
4. Record manager identity, task/thread identity when available, requested target, and status. A manager may be replaced; the manifest, commit, artifacts, evidence, and approvals carry the authority, not chat memory.
5. Development agents may prepare committed task branches and handoffs. Only the release manager may integrate, advance the release branch or `main`, build the release artifact, activate dev, promote, or roll back.

Never print secrets in a manifest, log excerpt, or response.

## Reconcile dev before promotion

Do not assume Git, `/home/flask`, a bundle, and the running processes match.

1. Inspect the exact dev Git HEAD, branch, status, task worktrees, active backend process paths, effective systemd base units and drop-ins, frontend build pointer, referenced bundle, and bundle hash.
2. Inventory every difference needed to reproduce the behavior the user approves on dev. Do not guess which dirty files are junk and do not reset, stash, clean, delete, or overwrite unclassified work.
3. Preserve intended dev-only work on focused task branches. Integrate exact reviewed commits in a new clean release worktree based on current `origin/main`.
4. Resolve combined behavior in source. Do not copy an ad hoc dev bundle or selectively commit files merely because they look relevant.
5. Build once from the clean release commit with the repository build helper. Record the full source SHA, provenance marker, bundle names, and SHA-256 hashes.
6. Activate that exact candidate on dev using the documented runtime model. Prove effective systemd configuration, running process paths, nginx/frontend pointers, and reported fingerprints all resolve to the candidate.
7. Run focused tests, the combined safe suite, required contract checks, and real browser assertions. Exercise the changed behavior, not only feature strings or HTTP 200 responses.
8. Obtain or reconfirm the user's dev approval against the recorded commit and artifact. “Dev looked right before reconciliation” is not approval of a newly reconstructed release.

If no clean commit and artifact reproduce approved dev behavior, the release is blocked. Do not promote.

## Maintain the release manifest

Store state on the dev server at `/home/tradewave-releases/<release-id>/release.json`, with `/home/tradewave-releases/active.json` identifying the active release. Validate it against `ops/release_manifest.schema.json` when that schema is present.

Record at minimum:

- release ID, manager, requested target, status, created/updated times;
- base and release branch, included handoff SHAs, full release SHA, remote ref state;
- frontend artifact paths and hashes, backend/source fingerprint, effective runtime paths;
- test, contract, browser, and environment-verification evidence;
- dev and staging approvals tied to the exact SHA and artifact hash;
- snapshots, rollback commands, previous pointers, deployment events, and known risks.

Use atomic writes and keep append-only deployment events. Handoffs update the manifest before the current manager stops.

## Promote the immutable release

For each environment, in order:

1. Verify preconditions before any write. Snapshot or capture rollback state as required.
2. Promote the exact dev-approved source SHA and exact frontend artifact. Do not rebuild, re-merge, or substitute a later `main`.
3. Confirm target Git cleanliness and ownership without discarding target data.
4. Apply migrations/configuration only when listed in the manifest and approved by the runbook.
5. Activate the release through the actual runtime mechanism. Copying files to `/home/flask` is not activation when systemd uses a release pointer.
6. Inspect effective unit configuration, including drop-ins, and verify the running processes' working directories and command lines. Confirm they resolve to the intended release.
7. Verify nginx/index references the expected frontend bundle and hash. Confirm backend/source fingerprints.
8. Run service and route checks, the release-specific contract checks, and at least one real browser assertion for affected UI workflows.
9. Roll back on a failed required gate. Mark the release failed and preserve evidence. Never report success because another verifier printed `CLEAN`.
10. Record results and wait for the next explicit approval boundary.

Staging is mandatory before production. Production must use the same SHA and artifacts that passed staging.

## Required Wave Viewer regression gates

Until superseded by a tested repository gate, include both:

1. A level-1/free-tier contract check that loads a real pattern, requires non-empty `ChartData4`, and proves the echoed `request.entry_date` matches the requested US market date. Include UTC/US-evening coverage when date behavior is relevant.
2. A browser check that signs in with the relevant entitlement, loads the app, clicks an opportunity row, verifies a canvas exists in `.seasonal-barchart-parent`, and verifies the `.barchart-background` loading/empty watermark is gone after success.

Feature-marker greps, unit tests, build success, and HTTP 200 checks do not replace these gates.

## Known fail-closed checks

Treat these as unresolved until current read-only evidence and reviewed code prove otherwise:

- `ops/deploy.sh` may update base units or `/home/flask` while systemd drop-ins keep services on an older `.tw2-app-current` release. Compare effective units and live process paths.
- `verify_deploy.sh` may report `CLEAN` without proving the running release or rendered product. Independently verify runtime and browser behavior.
- `TW2_UPDATE_SERVER` may point at a public updater that returns 403 from Kamatera. Classify values without printing secrets and verify the scheduled path before claiming operational readiness.
- Host-timezone `date.today()` behavior may diverge from the US market date for date-locked users. Keep the response guard strict and test the contract at the entitlement/time boundary.

Do not silently repair these while asked only to inspect or create policy. Record proposed code changes separately.

## Handoff and completion

Before handing to another Codex, Claude, or human manager:

1. Stop new mutations.
2. Update the manifest atomically with the last completed gate, exact active pointers, pending steps, approvals still required, risks, and rollback commands.
3. Commit and push any repository work from a clean worktree.
4. Name the full commit SHAs and artifact hashes. Do not rely on prose such as “latest dev.”
5. Require the next manager to independently re-read the manifest and verify live pointers before continuing.

Call a release complete only when the requested environment runs the exact recorded release, every required gate passes, rollback is documented, the manifest is final, and no further authorized work remains.
