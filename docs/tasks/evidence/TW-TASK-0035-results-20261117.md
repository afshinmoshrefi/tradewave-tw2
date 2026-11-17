# TW-TASK-0035 results - Tara on Claude Haiku 5.5 after steps 1 to 6 (2026-11-17)

All figures below use judge v3 and the revised bank from TW-TASK-0036, except where "old stick" is written. Private instance only (port 5087, `--no-control-socket`, own pid file, copy of this worktree, stopped and removed). Model: `claude-haiku-5-5`, effort low, adaptive thinking, 1-hour cache TTL. Held-out replies were not read; only aggregate verdicts were used.

## 1. Final table

Baseline is the round-3 code (TW-TASK-0033) re-judged by the referee with the same stick (`audit36-*` runs).

| set | run | n | helpful | partial | unhelpful | false-fact answers | concise pass | $ per question, warm | p50 / p90 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| tuned | round 3 (`audit36-r3-final3-haiku55`) | 577 | 75.9% | 19.6% | 4.5% | 9.4% | 82.8% | 0.00149 | 2.9s / 9.1s |
| tuned | this branch, run 1 (`h80i-full1`) | 577 | 79.9% (461) | 18.0% | 2.1% (12) | 6.8% | 90.5% | 0.00180 | 3.6s / 9.2s |
| tuned, every second question | round 3 | 289 | 76.5% | 20.8% | 2.8% | 8.0% | 83.0% | | |
| tuned, every second question | this branch, run 1 | 289 | 79.6% | 18.3% | 2.1% | 7.3% | 89.3% | | |
| tuned, every second question | this branch, run 2 (`h80i-tunedhalf2`) | 289 | 78.9% | 19.0% | 2.1% | 5.5% | 86.5% | 0.00199 | 3.5s / 9.9s |
| held-out | round 3 (`audit36-r3-final3-haiku55`) | 154 | 72.7% | 21.4% | 5.8% | 13.0% | 85.1% | 0.00144 | 2.9s / 9.7s |
| held-out | round 3 rerun (`audit36-r4-haiku55-heldout`) | 154 | 68.2% | 26.6% | 5.2% | 11.0% | 86.4% | | 2.5s / 9.2s |
| held-out | this branch, run 1 (`h80i-full1`) | 154 | 76.0% (117) | 20.8% | 3.2% (5) | 7.1% | 90.3% | 0.00187 | 3.8s / 9.5s |
| held-out | this branch, run 2 (`h80i-held2`) | 154 | 74.0% (114) | 24.0% | 1.9% (3) | 9.1% | 89.0% | 0.00190 | 3.8s / 9.8s |

Reading:

- Tuned: 75.9% to 79.9% helpful on one full run (paired +61 / -38); the second run on half of the questions gives 78.9% where the first gave 79.6% and round 3 gave 76.5%. Call it 79% to 80%, about +3 to +4 points.
- Held-out: 75.0% as the mean of two runs against 70.5% as the mean of the two round-3 runs (72.7% and 68.2%): about +4.5 points. Paired against `r3-final3`: +18 / -13 and +19 / -17.
- Unhelpful: 4.5% to 2.1% tuned, 5.5% to 2.6% held-out (two-run means). The 3% ceiling is met on both sets.
- False-fact answers fell on both sets (tuned 9.4% to 6.8%; held-out 12.0% to 8.1%, two-run means). Concise pass rose 4 to 8 points.
- 80% helpful is reached on the tuned questions within run-to-run noise and is NOT reached on held-out (75%).
- Run-to-run noise: the same code on the same 289 tuned questions flipped 19 answers up and 21 down between two runs.

## 2. Cost and latency

List price for Haiku 5.5 prompts up to 100K tokens: $0.10 input, $0.01 cache read, $0.20 one-hour cache write, $0.50 output per 1M tokens.

- Warm: $0.00181 per question over the whole bank ($0.00148 before, +22%). The increase is the engine-route questions, which used to cost nothing and now cost one model call.
- Cold: the cached prefix is 72.6K tokens (tools plus the stable system block; `count_tokens` gives 70.2K for the system block and tools alone). A question that finds the cache empty pays one prefix write, about $0.0145, instead of a $0.0007 read, so a cold question costs about $0.016. No cold write occurred inside the measured runs (the cache was already warm).
- Calls per question 1.40. Latency p50 3.6s (2.9s before), p90 9.2s (9.1s). Engine-route questions specifically: median 0.0s before, 4.4s now.
- Largest prompt seen in 1,690 measured calls: 93,969 tokens (one outlier, a correction round after a very long first answer); the next largest is 84,769 and everything else is under 82.1K. All under the 100K price step. Headroom is about 27K tokens above the prefix; the knowledge base should not grow further without trimming rules.

## 3. Per step

Steps 1 to 3 change what the engine routes send; steps 4 to 6 change the model path. They were measured as those two groups on the TW-TASK-0034 samples (tuned questions only), not as six separate arms.

| group | sample | before (round 3, same stick) | after | paired |
|---|---|---|---|---|
| Steps 1 to 3, first cut, old stick (`h80i-det1`) | 117 engine-route questions | 42.7% helpful, 12.8% unhelpful, 18.8% false-fact, 48.7% concise | 65.0%, 0.9%, 14.5%, 58.1% | +31 / -5 |
| Steps 1 to 3 (`h80i-t2`) | same 117 | 56.4% helpful, 11.1% unhelpful, 11.1% false-fact, 71.8% concise | 71.8%, 1.7%, 11.1%, 82.9% | +27 / -9 |
| Steps 4 to 6 (`h80i-t2`) | 120 model-path questions (72 earlier failures, 48 earlier passes) | 69.2% helpful, 5.0% unhelpful, 12.5% false-fact | 69.2%, 4.2%, 7.5% | +12 / -12 |

- Step 1 (draft in the tool loop, number guard, fallback): the TW-TASK-0034 overlay without tools or guard measured 42.7% to 62.4% helpful with false-fact answers up from 18.8% to 25.6% and concise pass down to 20.5% (old stick). The product version reaches 65.0% on the same stick with false-fact answers down and concise pass up. In the full run 124 engine drafts were rewritten and 7 were rejected by a guard and sent as the engine wrote them (5 number guard, 1 retyped list, 1 length).
- Step 2 (templates): the comparison, window-study, Best Waves, crypto and Explorer sector fixes are inside the row above; `cmp-002`, `cmp-008`, `cmp-024`, `date-012`, `sym-019`, `sym-020`, `multi-021` moved to helpful.
- Step 3 (lists in code): no reply in the full run leaked a list token, and scan rows now carry dates, record and average.
- Step 4 (dead ends): fail-closed replies ("I couldn't send / complete / resolve ...") in the 731-question run: 4 before, 0 now. Closing answers in words: 3; a words answer accepted after one chart-action request: 2.
- Steps 5 and 6: helpful is flat on the model path, as TW-TASK-0034 predicted; false-fact answers on the sample fell from 12.5% to 7.5%.

By path in the final tuned run: model 460 questions 81.1% helpful; engine draft rewritten 94 questions 76.6%; engine reply sent unchanged (compliance or UI command) 18 questions 77.8%; rewrite rejected and draft sent 5 questions 40%.

## 4. Remaining gap

- Held-out is at 75%, five points short. The model path is where the questions are (80% of the bank) and no step here lifts it; the judge labels 84 of the 116 tuned non-helpful answers "model reasoning" (a correct answer missing one required item). Lowest tuned categories: getting started 57%, AI scores 58%, strategy 61%, dates and cycles 64%, screening 64%.
- Measurement limit on AI questions: the eval contexts carry no AI values, so the judge marks a real server reading ("AI Win% 84%") as an invented figure. 10 tuned answers in the final run carry that flag and all 10 are graded non-helpful (3 in the round-3 run). With AI values in the fixtures (listed as not done in TW-TASK-0036) up to 1.7 points of tuned helpfulness would be re-graded; this is an upper bound, not a claim.
- Two rubrics still expect "exactly January 1" and a years control equal to the lookback asked for; the engine does neither (section "verified" in the task record).
- Not attempted here: plan step 9 (sector tags, ADR resolution for TSM and INFY, engine-computed subset averages, current-year running return), step 10 (answer cards), step 11 (Sonnet for completeness-sensitive turns).

## 5. Safety checks that were measured, not assumed

- Engine actions: in the 117-question engine-route sample every accepted rewrite kept the engine's queued action unchanged (a changed or dropped action rejects the rewrite; unit-tested).
- Number guard: unit-tested for changed figures, arithmetic, fraction-to-percent spelling and list ordinals; 5 live rejections in the full run fell back to the engine reply.
- Disclaimer and plan sentences: restored word for word when the rewrite omits them (unit-tested); the disclaimer floor in `_finalize_chat_response` is unchanged and still runs last.
- Compliance-only replies are not sent to the model at all (suitability boundary, investor funnel, notices): 28 of 731 replies in the full run were sent exactly as the engine wrote them.
- Prefix: byte-identical across requests (unit-tested); every measured call read the cache (`cache_write` 0 across the full run).

## 6. Spend

Judge $39.56 (h80i-det1 2.49, h80i-model1 3.37, h80i-t2 5.87, h80i-full1 17.42, h80i-held2 3.54, h80i-tunedhalf2 6.87), Haiku 5.5 $3.28, total $42.84 of the $50 cap. The first run (h80i-det1, $2.49) was graded with the old stick before the referee's change arrived.

## 7. Reproduce

```bash
PY=/root/tara-eval-runs/venv/bin/python; cd tools/tara_eval
sudo python3 private_instance.py start --name h80i --port 5087 --from-tree <this worktree> --policy haiku55
$PY run_eval.py --run <name> --target http://127.0.0.1:5087 \
    --question-log /home/tradewave-worktrees/tara-eval-private-h80i/.eval/tara_questions.log --concurrency 3
$PY judge.py --run <name> --budget <usd>
sudo python3 private_instance.py stop --name h80i --remove
```

Raw runs (private, on the dev box): `/root/tara-eval-runs/h80i-*`; helper scripts `/root/tara-eval-runs/h80i/{stats,final,show}.py`; sample id lists `/root/tara-eval-runs/h80/ids_det.txt`, `ids_model.txt`, `/root/tara-eval-runs/h80i/ids_tuned_half.txt`.
