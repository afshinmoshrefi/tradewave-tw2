# TW-TASK-0035 results - Tara on Claude Haiku 5.5 after steps 1 to 6 (2026-11-17)

> **Read section 8 first.** Sections 1 to 7 were measured at commit 8ff5a607 with the first engine-draft rewrite ON. An independent review then showed that rewrite's number guard was too weak (NO-GO), so it was removed. What is live on dev is phase A (918626f1): the same code with the rewrite OFF. Section 8 has the phase A and phase B figures.

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

## 8. After the independent review: phase A (shipped) and phase B (lead only, off)

The review of 8ff5a607 found that the rewrite's guard only checked that each number existed somewhere: it accepted symbol swaps, sign flips, rose/fell swaps, changed n, date and best/worst swaps, dropped rows and plan notices, and figures taken from the user's own message; real Haiku dropped a row under a "Ranked by win rate" header, replaced an engine reply with its own scan and answered owner question 5 with Oct 13 2022 instead of Jun 2 1931 in 3 of 4 runs. The lift in section 3 for steps 1 to 3 (56.4% to 71.8% on the route questions) was therefore bought with answers that could be wrong, and it is withdrawn.

- **Phase A (918626f1, live on dev, main).** Rewrite off: every engine route sends its own reply. Template fixes, rendered lists on the model path, dead-end fixes, live context, knowledge-base facts and the review fixes (engine Sharpe in rendered rows, "avg short-side return", the hold range, crypto pair and empty-read note, price-level asks in the advice floor) are on.
- **Phase B (this commit, OFF by default).** The engine reply is sent word for word and the model may only add a short lead above it; `tara_draft_lead.validate_lead` checks the lead clause by clause against the engine reply (section "Engine replies with a validated model lead" in the ecosystem doc). All 22 hand-written probes from the review behave as required (2 faithful leads allowed, 20 refused), and with each of the 52 recorded real-model rewrites the engine reply reaches the user complete and unchanged.

Measured on the 117 tuned route questions, judge v3, one phase A run and three phase B runs (private instances on ports 5087 and 5088):

| arm | helpful | partial | unhelpful | false-fact | concise | $ per question | p50 / p90 |
|---|---:|---:|---:|---:|---:|---:|---|
| Round 3, same stick | 56.4% | 32.5% | 11.1% | 11.1% | 71.8% | 0 | 0.0s / 4.0s |
| First rewrite (8ff5a607, withdrawn) | 71.8% | 26.5% | 1.7% | 11.1% | 82.9% | 0.0015 | 4.4s / 8.9s |
| Phase A, rewrite off (`h80p-a1`) | 65.8% (77) | 23.9% | 10.3% | 7.7% | 69.2% | 0.00003 | 0.0s / 3.5s |
| Phase B, lead only, run 1 (`h80p-b1`) | 65.8% (77) | 24.8% | 9.4% | 7.7% | 66.7% | 0.0011 | 2.1s / 5.6s |
| Phase B, lead only, run 2 (`h80p-b2`) | 65.8% (77) | 23.9% | 10.3% | 7.7% | 61.5% | 0.0011 | 2.2s / 5.6s |
| Phase B, lead only, run 3 (`h80p-b3`) | 65.8% (77) | 24.8% | 9.4% | 6.8% | 62.4% | 0.0011 | 2.1s / 5.3s |

Phase B rows are paired to phase A: a question whose reply is byte-identical to phase A's keeps phase A's verdict (the judge graded identical replies differently 2 or 3 times per run, which is pure judge noise), and a lead that the final, slightly stricter rules would refuse is counted as the engine reply. Raw judge output for the three runs is 65.8%, 63.2% and 64.1%.

Reading:

- **The lead adds no measurable helpfulness.** 12 to 15 of 117 replies got a lead; paired against phase A the helpful count moved by +0 / -0, +0 / -0 and +1 / -1. Concise pass is 3 to 8 points lower because the reply is longer. It costs one model call ($0.0011) and about 2 seconds on every engine-route question.
- **Recommendation: leave `DRAFT_REWRITE_ENABLED` off.** The safe version of the idea does not pay for its latency. The route gain that is real and kept is the template work: 56.4% to 65.8% helpful on these questions with no model call.
- Owner's five research questions, three runs each with the lead on: the engine reply was present word for word in 15 of 15 replies with the same chart actions; a lead was added in 5 of 15 (questions 3 and 4) and every figure in it is the engine's; question 5 answers Jun 2, 1931 in every run.
- Where the withdrawn lift came from: the model restructuring and shortening the engine reply, answering a second intent and calling tools. Those are exactly the freedoms the review showed to be unsafe behind a number-existence guard. Getting that lift back safely means changing the engine templates themselves (shorter replies that lead with the answer, a second-intent handler), not a model pass over them.

Whole-bank estimate for what is live (phase A), not re-measured on the full bank: the route questions are 117 of 577 tuned, so 56.4% to 65.8% there is about +1.9 points on tuned, against +3.1 with the withdrawn rewrite; tuned helpfulness for phase A is therefore about 78 to 79% rather than the 79.9% in section 1. The model path (460 questions, 81.1%) is unchanged between the two.

Phase B spend: judge $7.60, Haiku 5.5 about $0.40, total about $8.00 of the additional $15. Overall task spend about $50.84 across the two budgets ($42.84 + $8.00).
