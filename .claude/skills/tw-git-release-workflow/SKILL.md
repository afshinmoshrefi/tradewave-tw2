---
name: tw-git-release-workflow
description: Enforce TradeWave Git isolation, fast automatic dev completion, handoffs, integration, cleanup, and deterministic staging/production promotion. Use before starting or continuing any TradeWave code change; when multiple Codex or Claude sessions are involved; when a checkout is stale or dirty; when completing a change on the live dev site; when creating a handoff; or when preparing, merging, cleaning, deploying, or promoting through dev, staging, or production.
---

# TradeWave Git release workflow

Treat commits as release units. A server filesystem is an environment, not a release.

## Hard rules

1. Work in a dedicated branch and worktree for every task. Do not develop in the shared `/home/flask` checkout.
2. Run Git as `flask`, never `root`. Root-owned `.git` files break later fetches and pulls.
3. Keep one concern per branch. Do not mix unrelated changes from another session.
4. End every session with the intended work committed and pushed. If unfinished, use an explicitly labeled WIP commit on the task branch and mark it non-deployable.
5. Make the commit SHA the primary handoff. Notes supplement the commit; they never replace it.
6. Integrate exact pushed commits in a clean release worktree created from `origin/main`.
7. Deploy the reviewed release commit through `origin/main`; never copy an arbitrary dirty dev tree to staging.
8. Never use `git reset --hard`, `git clean -fdx`, broad deletion, or worktree removal until every potentially valuable change is classified and preserved.
9. Do not commit secrets, environment files, caches, temporary files, dependency trees, or ad hoc build backups.
10. Follow the deployment and knowledge rules in `CLAUDE.md`, `docs/TRADEWAVE_ECOSYSTEM.md`, and the applicable deployment skill. For every release, promotion, rollback, readiness, or parity request, use `.claude/skills/tradewave-deployment-manager/SKILL.md` and `docs/RELEASE_PROCESS.md`.
11. For a substantive application or runtime-visible change, completion includes clean integration, activation, and live verification on dev unless the owner explicitly says `local only` or `do not deploy`. Use the fast dev loop; staging's full release qualification begins only when staging is requested.

## Start a task

1. Fetch `origin` as `flask` before trusting the age or completeness of the current worktree. If local policy files are absent, read them from current `origin/main` before declaring them missing.
2. Read `AGENTS.md`, `CLAUDE.md`, `docs/RELEASE_PROCESS.md`, and `docs/TRADEWAVE_ECOSYSTEM.md` from the current policy source.
3. Create a task branch from current `origin/main`. Do not start new application work from a previously opened stale branch.
4. Create a dedicated worktree under `/home/tradewave-worktrees/` or another task-specific path.
5. Confirm the new worktree is clean before editing.

Example shape - adapt the task name and date:

```bash
sudo -u flask git -C /home/flask fetch origin
sudo -u flask git -C /home/flask worktree add \
  -b codex/<task>-YYYYMMDD \
  /home/tradewave-worktrees/<task>-YYYYMMDD \
  origin/main
```

Claude may use a `claude/` branch prefix. Preserve an existing branch name when continuing a task.

## Preserve the task commit

Before dev integration:

1. Inspect `git status` and the complete diff.
2. Remove or ignore generated artifacts; do not hide real source files with broad ignore rules.
3. Run tests appropriate to the change.
4. Update canonical documentation in the same commit when architecture, data flow, invariants, paths, or deployment behavior changed.
5. Commit only the task's intended changes and push the branch.
6. Write or update a handoff on the dev server under `/home/tradewave-handoffs/<release-or-date>/` when another manager must consume the commit.
7. Leave the task worktree clean. A WIP branch may be non-deployable, but it must still be preserved and identified.

The handoff must state:

- task and outcome;
- branch and full commit SHA;
- whether it is deployable or WIP;
- tests run and their results;
- migrations, dependencies, configuration, nginx, service, or build requirements;
- known risks, conflicts, and rollback notes;
- paths intentionally left untracked, if any, with a reason.

## Complete an application change on dev - fast loop

This is the default path for small, medium, and large application changes. A separate deployment conversation is not required. It deliberately does not create a release ID or manifest, run the full regression suite, inventory staging, take snapshots, or execute broad account-tier/browser matrices. Those are staging-qualification work.

1. Fetch `origin/main`, integrate the exact task commit in a clean current-main worktree, and resolve routine conflicts without involving Afshin. Preserve every completed change.
2. Run focused tests for the affected behavior and cheap directly relevant compile/lint checks. Add proportional gates for migrations, auth, billing, security, destructive data paths, or deployment infrastructure; do not automatically substitute the entire staging checklist.
3. Build only the affected runtime artifact, once. For React changes, use `npm run build` and stamp provenance. Backend-only changes do not rebuild React. Documentation/policy-only changes do not activate dev when the application tree is unchanged.
4. Push the task/candidate branch, then acquire `/var/lib/tradewave/release-state/dev-activation.lock` only when the tested candidate is ready to activate. Refetch `origin/main` immediately. If it moved, release the lock, integrate the new commits, rerun only affected checks/builds, and retry.
5. Record the previous backend/frontend pointers, activate the candidate on dev through the real runtime mechanism, and run one live smoke that proves the changed behavior. A UI change requires a rendered browser check of that behavior; backend work requires the relevant live contract or route check. Do not replace the smoke with feature-string greps or HTTP 200 alone.
6. Advance `origin/main` to the verified candidate with a non-forced, concurrency-safe push. If it unexpectedly fails, roll dev back to the recorded pointers and retry from the newer main.
7. Refetch and prove that current main's application tree, the live backend source, and affected artifact provenance match. Release the lock promptly.
8. Report the change complete with its SHA and live evidence. "Staging-ready" means clean, pushed, live on dev, and focused-tested; full staging qualification has not yet run.

If another Claude or Codex session owns the short activation window, preserve the exact pushed commit and wait or hand it off internally. Never make Afshin order branches or locks.

## Qualify a staging release

1. Use a new clean integration worktree or clone based on current `origin/main`.
2. Fetch all task branches and verify every handoff SHA exists on the remote.
3. Review each task diff independently before merging it.
4. Merge or cherry-pick the exact handoff SHAs. Resolve conflicts against current behavior; do not choose an entire older side blindly.
5. Capture the current live-dev behavior as the approved target. Run focused tests after each risky merge, then the combined regression suite and release build.
6. Review `origin/main..HEAD`, confirm the worktree is clean, and push a release branch.
7. Record the tested full SHA. That exact SHA is the promotion candidate.

Do not add unrelated changes found in `/home/flask` to make the release "match dev." Preserve them separately and decide their fate as another task.

## Promote through environments

The designated release manager owns this section. A coding session may already be that manager after completing dev; otherwise the recorded handoff transfers exact state without owner coordination.

TradeWave flow is:

```text
task commits -> fast live dev completion -> full staging qualification -> staging -> verify -> production
```

Only after the user says `Deploy to staging`:

1. Assign the release ID and create the manifest; this is where full release ownership begins.
2. Confirm live dev and current `origin/main` have the same application tree. A docs-only main advance is allowed, but build the qualified artifact from the exact final main SHA.
3. Run the complete safe regression, required release-specific contracts, entitlement/browser gates, and provenance-stamped release build. Bind approval to the exact SHA and composite artifact hash.
4. Audit staging out-of-band state, effective services/drop-ins, live paths, data/migration/config requirements, and executable rollback. Lock the SHA through staging approval and production promotion.
5. The release manager deploys the exact qualified artifact to staging with automatic rollback, verifies it, and records the result. Production remains a separate human-executed boundary.

Production remains a separate promotion of the same verified commit and must satisfy the snapshot gate in the production deployment skill.

## Handle a dirty shared checkout

Do not guess which files are junk. Classify first:

- **Intended source work:** move or commit it to a named salvage/task branch and push it.
- **Generated or reproducible output:** verify its source and removal path, then remove it and add a narrow ignore rule if appropriate.
- **Unknown ownership or intent:** preserve it in a named salvage branch or patch and document it before cleanup.
- **Already integrated changes:** prove equivalence against the release SHA before discarding duplicates.
- **Secrets or machine-local configuration:** keep them out of Git and avoid printing their values.

After preservation, restore `/home/flask` to a clean operational checkout of the intended branch. Then inspect each registered worktree, remove only clean obsolete worktrees, run `git worktree prune`, repair ownership as `flask`, and validate with `git fsck` before optional garbage collection.

## Completion criteria

A development or release session is complete only when:

- intended changes are committed and pushed;
- the worktree is clean or explicitly documented as a preserved WIP;
- the handoff names the full SHA and test results;
- no unrelated files were swept into the commit;
- deployment, migration, configuration, and rollback requirements are recorded;
- canonical TradeWave knowledge has been updated when required.
- for application/runtime work not explicitly kept local, the current-main application tree is running and verified on dev, and the change is staging-ready under the lightweight definition above;
- for staging/production, the full release manifest and every required qualification gate are complete for the exact promoted SHA and artifact.
