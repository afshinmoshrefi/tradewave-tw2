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
- Agents may make approved repository changes in isolated worktrees and may activate an approved candidate on dev. For staging and production, agents perform read-only inspection and author exact commands; Afshin or his designated human operator executes every live write.
- If a required rollback cannot run automatically inside an operator-started command, author the exact rollback immediately, mark the release `rollback_required`, record that the target remains at risk, and stop. Do not claim rollback until the operator confirms execution and the manager verifies the resulting state.

## Establish exclusive ownership

1. Assign a release ID such as `tw2-YYYYMMDD-NN`.
2. Inspect `/var/lib/tradewave/release-state/active.json` and the release manifest if present. Keep durable state separate from disposable release checkouts.
3. Do not integrate or deploy when another active manager owns the release. Continue only after an explicit handoff or owner override is recorded.
4. Record manager identity, task/thread identity when available, requested target, and status. A manager may be replaced; the manifest, commit, artifacts, evidence, and approvals carry the authority, not chat memory.
5. Development agents may prepare committed task branches and handoffs. Only the release manager may integrate, advance the release branch or `main`, build the release artifact, activate dev, or author staging/production promotion and rollback commands.

Never print secrets in a manifest, log excerpt, or response.

## Reconcile dev before promotion

Do not assume Git, `/home/flask`, a bundle, and the running processes match.

1. Inspect the exact dev Git HEAD, branch, status, task worktrees, active backend process paths, effective systemd base units and drop-ins for every release-managed service, frontend build pointer, referenced bundle, and bundle hash.
2. Inventory every difference needed to reproduce the behavior the user approves on dev. Do not guess which dirty files are junk and do not reset, stash, clean, delete, or overwrite unclassified work.
3. Preserve intended dev-only work on focused task branches. Integrate exact reviewed commits in a new clean release worktree based on current `origin/main`.
4. Resolve combined behavior in source. Do not copy an ad hoc dev bundle or selectively commit files merely because they look relevant.
5. Build once from the clean release commit with the repository build helper. Record the full source SHA, provenance marker, bundle names, and SHA-256 hashes.
6. Activate that exact candidate on dev using the documented runtime model. Prove effective systemd configuration, running process paths, nginx/frontend pointers, and reported fingerprints all resolve to the candidate.
7. Run focused tests, the combined safe suite, required contract checks, and real browser assertions. Exercise the changed behavior, not only feature strings or HTTP 200 responses.
8. Obtain or reconfirm the user's dev approval against the recorded commit and artifact. “Dev looked right before reconciliation” is not approval of a newly reconstructed release.

If no clean commit and artifact reproduce approved dev behavior, the release is blocked. Do not promote.

For the first release under this policy, declare a one-time `baseline-reconciliation` release. Inventory and preserve all dev-only work, establish one clean `origin/main` commit and artifact that reproduce approved dev behavior, and record the baseline marker. Later standard releases start from that baseline and do not reopen the historical inventory.

## Maintain the release manifest

Store state on the dev server at `/var/lib/tradewave/release-state/<release-id>/release.json`, with `/var/lib/tradewave/release-state/active.json` identifying the active release. Never share this parent with release checkouts, builds, worktrees, or cleanup targets. Validate it against `ops/release_manifest.schema.json` when that schema is present.

Record at minimum:

- release ID, manager, requested target, status, created/updated times;
- base and release branch, included handoff SHAs, full release SHA, remote ref state;
- frontend artifact paths and hashes, backend/source fingerprint, effective runtime paths;
- test, contract, browser, and environment-verification evidence;
- dev and staging approvals tied to the exact SHA and artifact hash;
- typed runtime, contract, and browser gates;
- out-of-band changes and their classification;
- snapshots, concrete backend/frontend rollback pointers and commands, deployment events, and known risks;
- who authored and who executed every state-changing event.

Use atomic writes and keep append-only deployment events. Handoffs update the manifest before the current manager stops.

## Promote the immutable release

For each environment, in order:

1. Verify preconditions before any write. Snapshot or capture rollback state as required.
2. Reconcile target out-of-band state. Compare tracked files with their Git objects, effective systemd configuration and all release-managed process paths with the intended runtime model, and the active frontend hash with its provenance. Classify and preserve every difference. Any unclassified or blocking difference stops promotion; never overwrite it silently.
3. Require `origin/main` to equal the exact release SHA before staging. Lock that SHA in the manifest and require it to remain unchanged through staging approval and production promotion.
4. Promote the exact dev-approved source SHA and exact frontend artifact. Do not rebuild, re-merge, or substitute a later `main`.
5. Confirm target Git cleanliness and ownership without discarding target data.
6. Apply migrations/configuration only when listed in the manifest and approved by the runbook.
7. Activate the release through the actual runtime mechanism. Copying files to `/home/flask` is not activation when systemd uses a release pointer.
8. Inspect effective unit configuration, including drop-ins, and verify the running processes' working directories and command lines. Resolve conflicting base-unit and drop-in deployment models before promotion; detection alone is insufficient.
9. Verify nginx/index references the expected frontend bundle and hash. Confirm backend/source fingerprints.
10. Run service and route checks, the release-specific contract checks, and at least one real browser assertion for affected UI workflows.
11. On failure, use automatic rollback only when it is already part of the operator-started deployment command. Otherwise author the rollback immediately, mark `rollback_required`, and wait for operator execution. Never report success because another verifier printed `CLEAN`.
12. Record results and wait for the next explicit approval boundary.

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

Call a release complete only when the requested environment runs the exact recorded release, every required gate passes, rollback is documented, the manifest is final, and no further authorized work remains.
