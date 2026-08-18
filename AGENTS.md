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

For a substantive application or runtime-visible change, "done" means the combined change is committed, running on the live dev site, verified there, and staging-ready. The request to make the change authorizes the routine Git integration and dev-only activation needed to reach that state unless the owner explicitly says `local only`, `do not deploy`, or asks only for analysis/documentation. The coding session may become the recorded dev-completion manager; one manager means exclusive ownership of the integration/activation window, not a separate conversation.

Claude and Codex may develop concurrently in separate worktrees. Their dev completions are serialized: the finishing manager locks before final integration, refetches the newest `origin/main`, combines the task with every completed change, tests and activates one immutable candidate, verifies the live dev behavior, and leaves `origin/main` equal to the exact active dev SHA. A session blocked by another active manager waits or hands off internally and must not claim completion while its change is only local.

A plain request to deploy to staging is the complete authorization for the sole release manager to promote the exact staging-ready dev SHA and artifact through verified staging, including automatic rollback, without asking the owner to restate the process or run commands. Production remains a separate explicit request and human-executed write boundary.

Run Git as `flask`, never `root`. Do not reset, clean, delete, or remove a worktree until potentially valuable changes are classified and preserved.

## Critical TradeWave day-counting invariant

A TradeWave day is a calendar day, and the entry day is day 1:

```text
end_date = start + (days - 1)
```

The displayed count may be adjusted for an inclusive label, but that adjustment must never be added to the end date. For example, July 1 plus a 31-day window ends July 31.

When writing an LLM prompt or reviewer gate, state this positively: "TradeWave windows are measured in calendar days. Flag only text that calls them trading days."

Other recurring invariants remain canonical in `docs/TRADEWAVE_ECOSYSTEM.md`, including that `years` is always a string.
