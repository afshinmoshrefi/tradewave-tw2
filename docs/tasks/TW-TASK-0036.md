# TW-TASK-0036: Independent audit of the Tara eval rubric and judge

- Status: delivered on branch (bank, judge and audit log pushed; not merged to main, by instruction)
- Confidence: reproduced (judge checked against 64 blind hand grades; four stored runs re-judged)
- Priority: P2 - the eval decides where Tara engineering effort goes; a wrong measuring stick misdirects it
- First observed / last updated: 2026-11-17T19:25:00+00:00 / 2026-11-17T19:54:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent, neutral referee), 2026-11-17T19:26:00+00:00
- Authorization: step 7 of the Haiku-80 plan (TW-TASK-0034). Scope: the question bank rubrics, the judge prompt and payload, the audit log and task records on this branch; re-judging stored replies (no new Tara model calls). Judge budget cap $40. Excluded: Tara's code, knowledge base, main, dev, live services.

## Goal, Scope and Acceptance

Make the eval fair and accurate, as a referee who does not own the score.

1. Written grading rules.
2. Every rubric checked against the rules and product truth (live dev code); wrong facts, over-strict, ambiguous and lenient items fixed; every change logged with before, after and reason. Decisions are made from the rule and product truth only, never from which model passes an item.
3. Judge payload fixed (stale regex-router output removed; same knowledge base as the model), judge prompt rechecked for length bias.
4. Judge validated against a blind hand-graded stratified sample of at least 60 answers; agreement reported before and after.
5. Stored replies re-judged for r3-final3-luna, r3-final3-haiku55, r3-final3-sonnet55 and r4-haiku55-heldout; old and new scores side by side, tuned and held-out separately.

## Evidence and Investigation

Full audit log, with every rubric change: [evidence/TW-TASK-0036-rubric-audit.md](evidence/TW-TASK-0036-rubric-audit.md).

- Rules: 15, in section 3 of the audit log.
- Rubric changes: 538 on 328 of 731 questions (loosened 252, tightened 106, fact fixed 109, clarified 71). 23 reviewer proposals were not applied.
- Judge v3: `routed_kb` and the vendor name removed from the payload, knowledge base loaded as Tara loads it, `must` graded item by item, `ideal` never required, explicit verdict test. No material length bias in v2; v3 is flat across reply length.
- Judge agreement with 64 blind hand grades: 67% before (kappa 0.44), 88% after (kappa 0.72); helpful versus not: 70% before, 91% after.

| run (stored answers) | set | n | old helpful | new helpful |
|---|---|---:|---:|---:|
| Haiku 5.5, r3-final3 | tuned | 577 | 65.0% | 75.9% |
| Haiku 5.5, r3-final3 | held-out | 154 | 66.2% | 72.7% |
| Haiku 5.5, r4 held-out rerun | held-out | 154 | 62.3% | 68.2% |
| Sonnet 5.5, r3-final3 | tuned | 176 | 73.9% | 81.8% |
| Sonnet 5.5, r3-final3 | held-out | 154 | 72.7% | 80.5% |
| Luna, r3-final3 | tuned (random 494 of 577) | 494 | 56.5% | 69.4% |
| Luna, r3-final3 | held-out | 154 | 57.1% | 68.2% |

Raw outputs (private, on the dev box, mode 700): old verdicts in `/root/tara-eval-runs/<run>/judged.jsonl` (untouched), new verdicts in `/root/tara-eval-runs/audit36-<run>/judged.jsonl`. No customer data and no user ids are in the repository.

## Acceptance and Regression Checks

- `python3 tools/tara_eval/build_bank.py --check`: pass (731 questions, every ref resolves).
- `git diff --check`: clean.
- `python3 -m py_compile tools/tara_eval/{judge,report,common}.py`: pass. `common.tara_kb_text()` verified equal to `chatbot._load_knowledge()` output.
- Not run: the appserver test suite (no product code changed); a fresh `run_eval.py` run (no new Tara calls were in scope).
- Not done: the last 83 Luna tuned answers (budget cap); Explorer and AI fixtures; re-pointing stale refs. See section 8 of the audit log.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`, branch `claude/tara-eval-rubric-audit-20261117`, worktree `/home/tradewave-worktrees/tara-eval-rubric-audit-20261117`, based on `origin/main` e2294724. Pushed commit: see `git log -1 -- docs/tasks/TW-TASK-0036.md` on the branch. Tree clean after the commit.

Changed files:

- `tests/fixtures/tara_eval_questions.json`: revised rubrics (questions, ids, contexts and the held-out list unchanged).
- `tools/tara_eval/judge.py`: judge v3 prompt, schema (`must_results`, `must_not_violated`, `rubric_flags`), payload and cache key.
- `tools/tara_eval/common.py`: `tara_kb_text()`.
- `tools/tara_eval/report.py`: no longer derives `retrieval_miss` from `routed_kb`.
- `tools/tara_eval/README.md`: judge and rubric rules.
- `docs/tasks/evidence/TW-TASK-0036-rubric-audit.md`, this record, the task index.

Decisions: recorded with reasons in the audit log (section 2, Appendix B). Risks: scores graded before this change (judge v2, old bank) are not comparable with scores after it; the judge cache key changed, so every run is graded afresh. Rollback: revert the commit; old verdicts and cache entries are still on disk. No configuration, migration or build step.

Next action: the owner reads section 8 of the audit log (ten decisions), then the Haiku-80 work re-judges its comparison runs with this bank and judge v3 (`judge.py --run <run> --budget N`, about $0.024 per answer) and re-bases the target.

## Environment Verification

Dev: not deployed by this task (eval tooling and records only). Staging: not checked. Production: not checked.

## History

- 2026-11-17T19:26:00+00:00, Claude Code session_01Pi1koVo3NroLWvCft5ehNR: claimed; branch created from origin/main e2294724 and pushed.
- 2026-11-17T19:54:00+00:00, same session: rules written, 731 rubrics reviewed by 13 result-blind reviewers and the referee, judge v3, 64 blind hand grades, four runs re-judged ($39.18 of the $40 cap), audit log written, branch pushed. Status delivered on branch.
