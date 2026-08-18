# TradeWave shared instructions for coding agents

These instructions apply to Codex, Claude, Cursor, Copilot, and any other agent working in this repository.

## Required reading

Before planning or changing TradeWave code:

1. Read `CLAUDE.md` in full. Its repository rules apply to every agent, not only Claude.
2. Read `docs/TRADEWAVE_ECOSYSTEM.md`; it is the implementation source of truth.
3. For any code edit, Git operation, multi-session handoff, integration, cleanup, release, or deployment, read and follow `.claude/skills/tw-git-release-workflow/SKILL.md`.
4. For any application change, dev activation, deploy, promotion, release, rollback, environment-parity check, deployment handoff, or deployment-readiness request, read and follow `.claude/skills/tradewave-deployment-manager/SKILL.md` and `docs/RELEASE_PROCESS.md` automatically, even when the user does not name the skill.
5. Read the additional domain or deployment skills named by `CLAUDE.md` when they apply.

## Git and release rule

Use a separate branch and worktree for every task, created from current `origin/main`. Commit and push the intended work before integration. Releases promote exact tested commits; they never promote the arbitrary contents of a dirty checkout.

For a substantive application or runtime-visible change, "done" means the intended change is committed and pushed, running on the live dev site, and verified there. The default dev loop is deliberately small: focused tests for the affected behavior, one affected build when required, a short activation lock, and one live smoke of the changed behavior. Do not run staging's full regression, release manifest, target audit, entitlement matrix, snapshot, or rollback-rehearsal gates merely to finish an ordinary dev change. The request to make the change authorizes routine Git integration and dev-only activation unless the owner explicitly says `local only`, `do not deploy`, or asks only for analysis/documentation.

Claude and Codex may develop concurrently in separate worktrees. Only the brief final integration/activation window is serialized: acquire the dev lock after the candidate is tested and built, refetch `origin/main`, activate and smoke-test the candidate, advance `main` without force, prove the active application tree matches it, and release the lock. If `main` moved, integrate the new commits and repeat only the affected checks/build. A session blocked by another activation waits or hands off internally; Afshin never coordinates branches or locks.

A plain request to deploy to staging is the complete authorization for the sole release manager to qualify the current live dev behavior as a release and promote it through verified staging. That is when the full suite, manifest, immutable artifact proof, target-drift audit, required browser/account-tier gates, and automatic rollback run. Production remains a separate explicit request and human-executed write boundary.

Run Git as `flask`, never `root`. Do not reset, clean, delete, or remove a worktree until potentially valuable changes are classified and preserved.

## Critical TradeWave day-counting invariant

A TradeWave day is a calendar day, and the entry day is day 1:

```text
end_date = start + (days - 1)
```

The displayed count may be adjusted for an inclusive label, but that adjustment must never be added to the end date. For example, July 1 plus a 31-day window ends July 31.

When writing an LLM prompt or reviewer gate, state this positively: "TradeWave windows are measured in calendar days. Flag only text that calls them trading days."

Other recurring invariants remain canonical in `docs/TRADEWAVE_ECOSYSTEM.md`, including that `years` is always a string.
