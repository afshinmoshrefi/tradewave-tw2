# TW-TASK-0032: Tara eval - question bank, LLM-judged harness, baseline and model comparison

- Status: in-progress
- Confidence: n/a (measurement task)
- Priority: P1 - the owner reports Tara stumbles on most real questions; there is no measuring stick
- First observed / last updated: 2026-11-17T13:00:00+00:00 / 2026-11-17T13:00:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T13:00:00+00:00
- Authorization: Afshin asked for the measurement system (bank, harness, baseline, model comparison). Scope: tools, fixtures, docs and records on a task branch. No Tara behavior change, no dev activation, no main push.

## Goal, Scope and Acceptance

Build the measuring stick that lets TradeWave make Tara helpfully answer nearly any beginner or professional trader/investor question: (A) a predicted question bank, (B) an automated eval harness with an LLM judge, (C) a baseline on live dev, (D) a model comparison, (E) whole-KB versus routed retrieval. This task does not fix Tara.

## History

- 2026-11-17T13:00:00+00:00: Claude claimed the task on branch `claude/tara-eval-20261117`.
