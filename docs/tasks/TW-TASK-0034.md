# TW-TASK-0034: Evidence-based plan to raise Tara on Claude Haiku 5.5 from 65% to at least 80% helpful

- Status: in-progress (analysis only)
- Confidence: reproduced (measured with the TW-TASK-0032 harness on private instances)
- Priority: P1 - the owner chose Haiku 5.5 for cost; it is helpful on 65% of the 731-question bank and the target is at least 80% helpful, at most 3% unhelpful
- First observed / last updated: 2026-11-17T16:40:00+00:00 / 2026-11-17T18:50:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T18:50:00+00:00
- Authorization: read-only analysis plus small measured experiments on private instances (own port, `--no-control-socket`, own pid file). No product code change, no dev activation, no live service, no `dev-activation.lock`. API budget cap $40.

## Goal, Scope and Acceptance

Produce a ranked, measured plan that takes the round-3 code (TW-TASK-0033, `origin/claude/tara-quality-round3-20261117`) on Claude Haiku 5.5 from about 65% to at least 80% helpful, at most 3% unhelpful and fewer false-fact answers, at roughly Haiku cost.

1. Cluster Haiku's non-helpful answers on the 577 tuned questions by root cause and size each cluster against the 15-point gap.
2. Audit a sample of judge verdicts for judge and rubric error.
3. Measure the cheap levers on private instances (effort, prompt structure, verify/repair, deterministic routes through the model).
4. Report cost per question and latency for each lever.

The 154 held-out questions are used only for the final check.

## Evidence and Investigation

Pending: [evidence/TW-TASK-0034-haiku80-plan.md](evidence/TW-TASK-0034-haiku80-plan.md).

## Acceptance and Regression Checks

Pending.

## Implementation and Handoff

Branch `claude/tara-haiku80-plan-20261117`, worktree `/home/tradewave-worktrees/tara-haiku80-plan-20261117`, based on origin/main `dca285fa`. Documentation only.

## Environment Verification

Dev: not applicable (no application change). Staging: not checked. Production: not checked.

## History

- 2026-11-17T18:50:00+00:00: Claude claimed the task on branch `claude/tara-haiku80-plan-20261117`.
