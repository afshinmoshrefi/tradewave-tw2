# TW-TASK-0036: Independent audit of the Tara eval rubric and judge

- Status: in-progress
- Confidence: reported (TW-TASK-0034 plan estimates that 13% to 19% of non-helpful verdicts are rubric strictness or ambiguity, and that the judge's `failure_type` is stale)
- Priority: P2 - the eval decides where Tara engineering effort goes; a wrong measuring stick misdirects it
- First observed / last updated: 2026-11-17T19:30:00+00:00 / 2026-11-17T20:10:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent, neutral referee), 2026-11-17T20:10:00+00:00
- Authorization: step 7 of the Haiku-80 plan. Scope: the question bank rubrics, the judge prompt and payload, the audit log and task records on this branch; re-judging stored replies (no new Tara model calls). Judge budget cap $40. Excluded: Tara's code, knowledge base, main, dev, live services.

## Goal, Scope and Acceptance

Make the eval fair and accurate, as a referee who does not own the score.

1. Written grading rules.
2. Every rubric checked against the rules and product truth (live dev code); wrong facts, over-strict, ambiguous and lenient items fixed; every change logged with before, after and reason. Decisions are made from the rule and product truth only, never from which model passes an item.
3. Judge payload fixed (stale regex-router output removed; same knowledge base as the model), judge prompt rechecked for length bias.
4. Judge validated against a blind hand-graded stratified sample of at least 60 answers; agreement reported before and after.
5. Stored replies re-judged for r3-final3-luna, r3-final3-haiku55, r3-final3-sonnet55 and r4-haiku55-heldout; old and new scores side by side, tuned and held-out separately.

## Evidence and Investigation

Audit log: `docs/tasks/evidence/TW-TASK-0036-rubric-audit.md` (pending).

## Acceptance and Regression Checks

`tools/tara_eval/build_bank.py --check` and `git diff --check`: pending.

## Implementation and Handoff

Branch `claude/tara-eval-rubric-audit-20261117`, worktree `/home/tradewave-worktrees/tara-eval-rubric-audit-20261117`, based on `origin/main` e2294724. Work in progress.

## Environment Verification

Dev: not deployed by this task (eval tooling and records only). Staging: not checked. Production: not checked.

## History

- 2026-11-17T20:10:00+00:00, Claude Code session_01Pi1koVo3NroLWvCft5ehNR: claimed; branch created from origin/main e2294724.
