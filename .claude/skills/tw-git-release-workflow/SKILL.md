---
name: tw-git-release-workflow
description: Enforce TradeWave Git isolation, handoffs, integration, cleanup, and deterministic promotion. Use before starting or continuing any TradeWave code change; when multiple Codex or Claude sessions are involved; when a checkout is dirty; when creating a handoff; or when preparing, merging, cleaning, deploying, or promoting a release through dev, staging, or production.
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
10. Follow the deployment and knowledge rules in `CLAUDE.md`, `docs/TRADEWAVE_ECOSYSTEM.md`, and the applicable deployment skill.

## Start a task

1. Read `CLAUDE.md` and `docs/TRADEWAVE_ECOSYSTEM.md` first.
2. Fetch `origin` as `flask`.
3. Create a task branch from the intended base, normally current `origin/main`.
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

## Finish and hand off a task

Before declaring the session done:

1. Inspect `git status` and the complete diff.
2. Remove or ignore generated artifacts; do not hide real source files with broad ignore rules.
3. Run tests appropriate to the change.
4. Update canonical documentation in the same commit when architecture, data flow, invariants, paths, or deployment behavior changed.
5. Commit only the task's intended changes and push the branch.
6. Write a handoff on the dev server under `/home/tradewave-handoffs/<release-or-date>/`.
7. Leave the task worktree clean. A WIP branch may be non-deployable, but it must still be preserved and identified.

The handoff must state:

- task and outcome;
- branch and full commit SHA;
- whether it is deployable or WIP;
- tests run and their results;
- migrations, dependencies, configuration, nginx, service, or build requirements;
- known risks, conflicts, and rollback notes;
- paths intentionally left untracked, if any, with a reason.

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

TradeWave promotion is:

```text
task commits -> tested release commit -> origin/main -> staging -> verify -> production
```

Before staging:

1. Confirm the tested release is the commit that will advance `origin/main`.
2. Obtain any required approval for updating `origin/main` and deploying.
3. Confirm `origin/main` points to the intended full SHA after the push.
4. Run the repository staging deployment procedure from dev.
5. Verify services, health checks, migrations, static pages, React provenance, and relevant feature behavior.
6. Record the deployed SHA and verification result.

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
