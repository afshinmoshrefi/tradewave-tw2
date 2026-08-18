---
name: tw-git-release-workflow
description: Enforce TradeWave Git isolation, automatic dev completion, handoffs, integration, cleanup, and deterministic promotion. Use before starting or continuing any TradeWave code change; when multiple Codex or Claude sessions are involved; when a checkout is stale or dirty; when completing a change on the live dev site; when creating a handoff; or when preparing, merging, cleaning, deploying, or promoting a release through dev, staging, or production.
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
11. For a substantive application or runtime-visible change, completion includes clean integration, activation, and live verification on dev unless the owner explicitly says `local only` or `do not deploy`. The active dev SHA and `origin/main` must match at completion.

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

## Complete an application change on dev

The coding session may become the recorded dev-completion manager. A separate conversation is not required. If another Claude or Codex manager owns the dev mutation window, preserve the commit and coordinate through release state/handoff; do not make the owner manage branches and do not call the task complete while it is waiting.

1. Acquire the dev coordination lock before final integration and keep it through live verification and the final `origin/main` identity check.
2. Refetch `origin/main` after acquiring the lock. Create a new clean integration worktree from it and integrate the exact task commit on top of every already completed change.
3. Resolve conflicts by preserving both intended behaviors where possible. Ask the owner only when the product intentions truly conflict, not for routine Git choices.
4. Run focused tests, the combined safe suite, and the release build from the clean candidate.
5. Activate the immutable candidate on dev and verify the changed behavior in the live product, including a rendered browser assertion when UI behavior changed.
6. Advance `origin/main` to the exact verified candidate without force-pushing. If the ref changed concurrently, roll dev back to its recorded previous release, integrate the new main, rebuild, and repeat.
7. Verify the freshly fetched `origin/main`, active backend source, and frontend provenance all identify the same full SHA. Only then report the change done and staging-ready.

## Integrate a release

1. Use a new clean integration worktree or clone based on current `origin/main`.
2. Fetch all task branches and verify every handoff SHA exists on the remote.
3. Review each task diff independently before merging it.
4. Merge or cherry-pick the exact handoff SHAs. Resolve conflicts against current behavior; do not choose an entire older side blindly.
5. Run focused tests after each risky merge, then the combined regression suite and release build.
6. Review `origin/main..HEAD`, confirm the worktree is clean, and push a release branch.
7. Record the tested full SHA. That exact SHA is the promotion candidate.

Do not add unrelated changes found in `/home/flask` to make the release "match dev." Preserve them separately and decide their fate as another task.

## Promote through environments

The designated release manager owns this section. A coding session may already be that manager after completing dev; otherwise the recorded handoff transfers exact state without owner coordination.

TradeWave promotion is:

```text
task commits -> tested combined commit -> live dev == origin/main -> staging -> verify -> production
```

Before staging:

1. Confirm the tested release is the commit that will advance `origin/main`.
2. Treat a plain staging-deploy request as approval to update `origin/main` to the exact verified candidate and deploy it to staging; do not request redundant intermediate approval.
3. Confirm `origin/main` points to the intended full SHA after the push.
4. Lock that exact SHA through staging approval and production promotion; do not advance `main` between environments.
5. The release manager runs the repository staging deployment from dev, including automatic rollback, and records its executing identity. Production remains a separate human-executed boundary.
6. Verify target out-of-band state, effective services and drop-ins, live process paths, health checks, migrations, static pages, React provenance, contracts, and rendered feature behavior.
7. Record the deployed SHA and verification result.

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
- for application/runtime work not explicitly kept local, the exact combined SHA is running and verified on dev, freshly fetched `origin/main` equals it, and the artifact is staging-ready.
