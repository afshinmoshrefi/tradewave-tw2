# TW-TASK-0032: Tara eval - question bank, LLM-judged harness, baseline and model comparison

- Status: delivered on branch (measurement only; nothing to activate)
- Confidence: n/a (measurement task)
- Priority: P1 - the owner reports Tara stumbles on most real questions; there is no measuring stick
- First observed / last updated: 2026-11-17T13:00:00+00:00 / 2026-11-17T14:30:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T13:00:00+00:00
- Authorization: Afshin asked for the measurement system (bank, harness, baseline, model comparison). Scope: tools, fixtures, docs and records on a task branch. No Tara behavior change, no dev activation, no main push.

## Goal, Scope and Acceptance

Build the measuring stick that lets TradeWave make Tara helpfully answer nearly any beginner or professional trader/investor question: (A) a predicted question bank, (B) an automated eval harness with an LLM judge, (C) a baseline on live dev, (D) a model comparison, (E) whole-KB versus routed retrieval. This task does not fix Tara.

## Evidence and Investigation

Results: [evidence/TW-TASK-0032-results-20261117.md](evidence/TW-TASK-0032-results-20261117.md).

- Baseline on live dev release `93849eaa` (TW-TASK-0031 active, Luna low, routed KB): helpful 34%, partial 43%, unhelpful 22% over 731 questions.
- Root causes of the 480 non-helpful answers: retrieval miss 46%, deterministic shortcut hijack 23%, model reasoning 22%, guard-replaced errors 3%, other 6%.
- 154-question comparison: whole KB in the cached prefix lifts Luna 36% -> 45%, Haiku 5.5 43% -> 56%, Sonnet 5.5 46% -> 64%; Luna medium effort 42%. Measured cost per model-bound question: Luna $0.0009, Haiku 5.5 $0.0010, Sonnet 5.5 $0.0141; whole KB adds about $0.001 (Luna/Haiku).
- TW-TASK-0031 before/after on 139 shared questions: 51 -> 53 helpful (inside noise).

## Acceptance and Regression Checks

- `tools/tara_eval/build_bank.py --check` passes (schema, fixtures, KB/code refs, duplicates, identifier scan).
- Runner, judge, report and private-instance launcher exercised end to end (9 runs). No unit tests were added; no existing tests were run because no product code changed.

## Implementation and Handoff

Branch `claude/tara-eval-20261117`, worktree `/home/tradewave-worktrees/tara-eval-20261117`, merged with origin/main `dca285fa`.

Added: `tools/tara_eval/` (README, `run_eval.py`, `judge.py`, `report.py`, `private_instance.py`, `build_bank.py`, `build_contexts.py`, `common.py`), `tests/fixtures/tara_eval_questions.json` (731), `tests/fixtures/tara_eval_contexts.json` (12 on-screen fixtures from the live engine, percent statistics only), `tests/fixtures/tara_eval_subset.txt` (154 ids), this record and the results summary. No product code, KB, config or service was changed. Private comparison instances and their worktrees were stopped and removed.

Raw run outputs: `/root/tara-eval-runs/` on the dev box (mode 700), including `baseline-post0031/report.md` and `compare.md`. The judge needs the `anthropic` SDK, installed in `/root/tara-eval-runs/venv` (not in `/home/flask/venv`).

Decisions: judge = claude-opus-5-5 at low effort with the full KB cached; the headline is the post-0031 run; the pre-0031 run is kept only for the before/after delta. Server-side refusal fallbacks were not enabled for the judge (a refused item is reported as a judge error and can be retried).

Next action (owner/orchestrator): pick from the ranked recommendations in the results file; re-run `run_eval.py` + `judge.py` after each change (full bank about $18 of judge spend, subset about $3).

## Environment Verification

Dev: measured only, no activation. Staging: not checked. Production: not checked.

## History

- 2026-11-17T13:00:00+00:00: Claude claimed the task on branch `claude/tara-eval-20261117`.
- 2026-11-17T13:35:06+00:00: orchestrator activated TW-TASK-0031 on dev mid-run; the first pass was frozen as the pre-0031 baseline and the full bank was re-run for the headline.
- 2026-11-17T14:30:00+00:00: bank, harness, baseline, model and whole-KB comparison delivered on the branch. Spend about $47.7 of the $60 cap.
