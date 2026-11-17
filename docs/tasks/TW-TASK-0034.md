# TW-TASK-0034: Evidence-based plan to raise Tara on Claude Haiku 5.5 from 65% to at least 80% helpful

- Status: analysis delivered on branch (documentation only; nothing to activate)
- Confidence: reproduced (measured with the TW-TASK-0032 harness on private instances)
- Priority: P1 - the owner chose Haiku 5.5 for cost; it is helpful on 65% of the 731-question bank and the target is at least 80% helpful, at most 3% unhelpful
- First observed / last updated: 2026-11-17T16:40:00+00:00 / 2026-11-17T19:21:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T18:50:00+00:00
- Authorization: read-only analysis plus small measured experiments on private instances (own port, `--no-control-socket`, own pid file). No product code change, no dev activation, no live service, no `dev-activation.lock`. API budget cap $40.

## Goal, Scope and Acceptance

Produce a ranked, measured plan that takes the round-3 code (TW-TASK-0033) on Claude Haiku 5.5 from about 65% to at least 80% helpful, at most 3% unhelpful and fewer false-fact answers, at roughly Haiku cost.

1. Cluster Haiku's non-helpful answers on the 577 tuned questions by root cause and size each cluster against the 15-point gap.
2. Audit a sample of judge verdicts for judge and rubric error.
3. Measure the cheap levers on private instances (effort, prompt structure, worked examples, verify/repair, deterministic routes through the model).
4. Report cost per question and latency for each lever.

The 154 held-out questions were used only for the final checks, aggregates only.

## Evidence and Investigation

Plan and all figures: [evidence/TW-TASK-0034-haiku80-plan.md](evidence/TW-TASK-0034-haiku80-plan.md). Eval-only overlays used for the experiments: [evidence/TW-TASK-0034-overlays/](evidence/TW-TASK-0034-overlays/README.md).

Summary:

- Gap: 375 of 577 tuned questions helpful (65.0%); 80% needs 87 more. 202 non-helpful answers were hand-labelled. Largest causes: a correct model answer missing one required item (62, 10.7 points), deterministic route templates that omit or shift something (31, 5.4), not acting or acting unasked (20, 3.5), routes answering a neighbouring question (18, 3.1), tool output presented badly (16, 2.8), engine or data gaps (14, 2.4).
- Judge and rubric: sampled helpful verdicts all stand; no factual judge error found; 13% to 19% of non-helpful verdicts are rubric strictness or ambiguity (4.5 to 6.6 points of the 15).
- Measured and repeated on held-out: sending a deterministic route's reply through Haiku as a verified draft lifts those questions from 42.7% to 62.4% helpful (held-out 47.2% to 66.7%), +4.0 points on the bank, about $0.0012 and 2.5s per route question.
- Measured and flat: effort medium and high, question-type answer shapes, a relaxed length rule, a self-check repair call. Worked examples gained 5.8 points on tuned questions but did not repeat on held-out. The model path stays near 71%.
- Projection: 69% after the route step, 72% to 75% after the sized code fixes, 75.5% to 80.5% after rubric calibration, 77% to 83% with engine work. 80% is a stretch for Haiku, not a prompt-tuning outcome.

Analysis base: `origin/claude/tara-quality-round3-20261117` at `2e6a5a63`. origin/main moved to `e2294724` (TW-TASK-0033 review fixes, Haiku 5.5 primary) while this ran; the experiments were not repeated on it.

## Acceptance and Regression Checks

- Documentation only; no test suite applies. `git diff --check` clean.
- Every private instance was stopped and its private tree removed; no port in 5081 to 5086 is listening.
- Not done: product implementation of any step; a second run of each arm (budget).

## Implementation and Handoff

Branch `claude/tara-haiku80-plan-20261117`, worktree `/home/tradewave-worktrees/tara-haiku80-plan-20261117`, based on origin/main with `e2294724` merged in. Documentation only: this file, the register row, the plan and the overlay scripts under `docs/tasks/evidence/`. Raw runs (replies, verdicts, hand labels) stay on the dev box under `/root/tara-eval-runs/` (`h80-*`, `HAIKU80_PLAN.md`, mode 600/700).

Next action (orchestrator or owner): decide on plan step 1 (routes through the model with the tool loop and a number guard) and step 8 (rubric calibration and judge payload), which carry most of the supported lift.

Risks: single-run arms carry about 3.7 points of standard error on the 120-question sample; the sized steps are estimates until measured.

Spend: judge $34.91, Haiku 5.5 $3.12, total $38.03 of $40.

## Environment Verification

Dev: not applicable (no application change). Staging: not checked. Production: not checked.

## History

- 2026-11-17T18:50:00+00:00: Claude claimed the task on branch `claude/tara-haiku80-plan-20261117`.
- 2026-11-17T19:21:00+00:00: analysis, lever experiments and held-out checks complete; plan committed. Spend $38.03 of $40.
