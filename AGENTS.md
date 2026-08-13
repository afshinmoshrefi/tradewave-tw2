# TradeWave shared instructions for coding agents

These instructions apply to Codex, Claude, Cursor, Copilot, and any other agent working in this repository.

## Required reading

Before planning or changing TradeWave code:

1. Read `CLAUDE.md` in full. Its repository rules apply to every agent, not only Claude.
2. Read `docs/TRADEWAVE_ECOSYSTEM.md`; it is the implementation source of truth.
3. For any code edit, Git operation, multi-session handoff, integration, cleanup, release, or deployment, read and follow `.claude/skills/tw-git-release-workflow/SKILL.md`.
4. For any deploy, promotion, release, rollback, environment-parity check, deployment handoff, or deployment-readiness request, read and follow `.claude/skills/tradewave-deployment-manager/SKILL.md` and `docs/RELEASE_PROCESS.md` automatically, even when the user does not name the skill.
5. Read the additional domain or deployment skills named by `CLAUDE.md` when they apply.

## Git and release rule

Use a separate branch and worktree for every task. Commit and push the intended work before handoff. Releases promote exact tested commits through `origin/main`; they never promote the arbitrary contents of a dirty dev checkout.

One designated deployment manager owns each release. Development sessions may hand off pushed task commits, but may not integrate, deploy, move release pointers, or advance `main`. Dev remains the behavior source of truth only after the exact approved behavior is reproduced by a clean commit and immutable artifact and reactivated on dev.

Run Git as `flask`, never `root`. Do not reset, clean, delete, or remove a worktree until potentially valuable changes are classified and preserved.

## Critical TradeWave day-counting invariant

A TradeWave day is a calendar day, and the entry day is day 1:

```text
end_date = start + (days - 1)
```

The displayed count may be adjusted for an inclusive label, but that adjustment must never be added to the end date. For example, July 1 plus a 31-day window ends July 31.

When writing an LLM prompt or reviewer gate, state this positively: "TradeWave windows are measured in calendar days. Flag only text that calls them trading days."

Other recurring invariants remain canonical in `docs/TRADEWAVE_ECOSYSTEM.md`, including that `years` is always a string.
