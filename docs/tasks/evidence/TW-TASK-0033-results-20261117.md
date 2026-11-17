# TW-TASK-0033 results - Tara quality round 3 (2026-11-17)

Raw outputs (replies, verdicts) are on the dev box under `/root/tara-eval-runs/` (mode 700), not in the repo: `r3-final3-luna`, `r3-final3-haiku55`, `r3-final3-sonnet55` (final figures), `r3-final-*` (single full passes), `r3-fix*-*` (targeted re-measures), `r3d-tune` (mid-point). Every request used a synthetic `tara-eval-<run>-<id>` identity. Same bank, contexts, judge (claude-opus-5-5, low effort) and judge prompt as TW-TASK-0032.

## How it was measured

- Private instances only (`tools/tara_eval/private_instance.py --from-tree`, ports 5091-5093, `--no-control-socket`, own pid files). Live dev, its control socket, pointers and the activation lock were not touched.
- Tuning used only the 577 questions outside `tests/fixtures/tara_eval_subset.txt`. The 154 held-out questions were run and judged at the end and their replies were not read while changing Tara. Held-out and rest agree within 2 points for every model, so the lift is not fitted to the tuned questions.
- Model switch for the Claude runs: the one `ACTIVE_POLICY` line of `tara_runtime_policy.py` in the private copy, exactly as a release would do it.
- Luna and Haiku 5.5: full bank (731). Sonnet 5.5: 330 questions (the 154 held-out plus a 176-question stratified sample of the rest, 8 per category) to stay inside the budget.
- Three small guard fixes were made after the full passes (a "now active" false positive, the Claude loop's correction rounds, the neutral description of a queued view change). Every question whose trace or reply showed the changed code path was re-run on the final code and re-judged (Luna 47, Haiku 61, Sonnet 28), and merged. That re-measure selects weak answers, so part of its gain is re-roll luck: the single-pass figures are given beside the final ones and differ by at most 2 points.

## Final scores

| model (whole KB, round-3 code) | n | helpful | partial | unhelpful | false-fact answers | held-out helpful / unhelpful (n=154) | rest helpful / unhelpful | $ per model-bound question | latency p50 / p90 (model turns) |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| Baseline: live dev, Luna low, routed KB (TW-TASK-0032) | 731 | 34% | 43% | 22% | 22% | 36% / 23% | 34% / 22% | about $0.0009 | 2.3s / 7.4s |
| **Luna low (current model)** | 731 | **56%** | 39% | 5% | 12% | 57% / 8% | 56% / 5% | $0.0019 | 2.3s / 8.0s |
| **Haiku 5.5 low** | 731 | **65%** | 29% | 5% | 15% | 66% / 6% | 65% / 5% | $0.0019 | 3.6s / 8.8s |
| **Sonnet 5.5 low** | 330 | **73%** | 22% | 4% | 18% | 73% / 6% | 74% / 2% (n=176) | $0.0260 | 3.6s / 8.1s |

Single full pass before the targeted re-measure: Luna 55% / 39% / 6%, Haiku 64% / 29% / 7%, Sonnet 73% / 22% / 5%.

- Costs are measured token usage priced at the TW-TASK-0032 list rates (Luna $0.20 / $0.02 cached / $1.20 per 1M; Haiku 5.5 $0.10 / $0.01 / $0.50; Sonnet 5.5 $2 / $0.10 / $10), not invoice-verified. 148 of 731 questions are answered by deterministic routes at no model cost in every column.
- Prompt caching is confirmed in usage on both providers: the stable prefix is 42,643 Luna tokens and 70,345 Claude tokens, written once per cache shard and read on every later call (cached share of input 95% to 97%).
- "False-fact answers" counts answers with at least one statement the judge flagged. Luna nearly halves it (22% to 12%). The Claude models write longer answers and are flagged more often (15% and 18%) while being judged helpful more often; the judge's concise/tone pass rate is Luna 78%, Haiku 65%, Sonnet 40%.
- Judge noise on an identical configuration is about 5 points either way on 154 questions (TW-TASK-0032) and about 2 on the full bank.

## Lift by fix (Luna low, 731 questions, paired with the baseline)

These are before/after figures for the baseline questions each fix targets, not isolated ablations: all fixes are in the final code together, and the clusters overlap. Clusters defined by a baseline failure (1b, 2a) start at 0% by construction.

| fix / cluster (defined on the BASELINE reply) | n | helpful before | helpful after | unhelpful before | unhelpful after | paired up / down |
|---|---:|---:|---:|---:|---:|---|
| 1 whole KB: baseline model turns with no tool call | 403 | 39% | 64% | 17% | 3% | +140 / -24 |
| 1b baseline judged retrieval_miss | 126 | 0% | 57% | 41% | 1% | +93 / -1 |
| 2a view-contract guard replaced the reply | 28 | 0% | 71% | 86% | 0% | +28 / -0 |
| 2b announce-line collapse | 28 | 11% | 54% | 61% | 7% | +23 / -0 |
| 3a investor_guidance canned reply | 21 | 14% | 43% | 57% | 10% | +12 / -0 |
| 3b planner / other deterministic blocks | 88 | 36% | 45% | 19% | 11% | +11 / -1 |
| 3c research routes + capability boundary | 46 | 43% | 50% | 17% | 7% | +5 / -0 |
| 5 loaded-pattern questions (a pattern on screen, model turn) | 186 | 38% | 60% | 18% | 2% | +68 / -15 |
| 6 baseline tool turns (symbols, dates, screens) | 151 | 24% | 45% | 31% | 7% | +67 / -10 |
| 7 account_billing + data_methodology categories | 65 | 37% | 78% | 17% | 2% | +32 / -2 |
| ALL paired | 731 | 35% | 56% | 22% | 5% | +245 / -35 |
| held-out subset | 154 | 36% | 57% | 23% | 8% | +48 / -10 |
| rest | 577 | 34% | 56% | 22% | 5% | +197 / -25 |

Mid-point (176 tuned questions, whole KB plus the guard, hijack and tool fixes, before the final-check block, the engine-selected extremes, the pricing rule and the ordinal fix): helpful 31% to 49%, unhelpful 19% to 3%.

## By category (Luna low)

| category | n | helpful before | helpful after | unhelpful before | unhelpful after | paired up / down |
|---|---:|---:|---:|---:|---:|---|
| strategy | 30 | 33% | 37% | 17% | 7% | +5 / -2 |
| dates_cycles | 29 | 24% | 38% | 34% | 10% | +9 / -0 |
| screening | 40 | 30% | 40% | 28% | 12% | +9 / -0 |
| offtopic_markets | 26 | 38% | 42% | 15% | 4% | +3 / -1 |
| getting_started | 30 | 27% | 47% | 30% | 3% | +10 / -0 |
| risk_boundary | 34 | 24% | 47% | 12% | 3% | +9 / -0 |
| symbol_research | 29 | 14% | 48% | 34% | 14% | +15 / -1 |
| pattern_analysis | 46 | 30% | 50% | 26% | 2% | +14 / -1 |
| ai_scores | 38 | 32% | 50% | 16% | 16% | +9 / -2 |
| comparisons | 25 | 24% | 52% | 56% | 16% | +12 / -0 |
| multi_turn | 34 | 47% | 53% | 21% | 12% | +8 / -4 |
| messy_input | 26 | 58% | 54% | 8% | 4% | +6 / -6 |
| ui_howto | 60 | 33% | 57% | 28% | 0% | +26 / -2 |
| portfolio_tools | 34 | 38% | 59% | 24% | 9% | +11 / -4 |
| troubleshooting | 35 | 37% | 60% | 29% | 3% | +16 / -3 |
| non_english | 19 | 42% | 63% | 16% | 0% | +8 / -2 |
| product | 25 | 32% | 64% | 12% | 0% | +10 / -1 |
| chart_reading | 37 | 32% | 68% | 19% | 3% | +14 / -2 |
| data_methodology | 30 | 33% | 70% | 17% | 3% | +14 / -1 |
| mcp_api | 25 | 36% | 72% | 24% | 0% | +10 / -0 |
| definitions | 44 | 59% | 73% | 7% | 2% | +9 / -2 |
| account_billing | 35 | 40% | 86% | 17% | 0% | +18 / -1 |

## What is left (Luna low, 322 non-helpful of 731)

| root cause (judge label) | n |
|---|---:|
| model reasoning (facts present, answer incomplete: missing the nearest alternative, the loaded value, n, the worst year) | 181 |
| deterministic route answered a neighbouring question | 66 |
| retrieval miss (fact in the KB, not used) | 39 |
| UI action error | 11 |
| missing tool or data | 10 |
| tone, wrong fact, missing KB | 15 |

1. Deterministic routes are now the weakest path: 148 questions at 45% helpful in every model column (planner blocks 44%, window study 33%, capability boundaries 0 of 5, sector screen 0 of 3, suitability boundary 1 of 4). Existing tests pin them (advice floor, trusted AI values, capability boundaries), so narrowing them further is a product decision, not a bug fix.
2. Partial answers on the model path (37% of Luna's model turns): correct but incomplete. Haiku 5.5 leaves 26% partial and Sonnet 5.5 16%; Luna at medium effort was +6 points in TW-TASK-0032 and was not re-measured here.
3. Lowest categories on Luna: strategy 37%, dates_cycles 38%, screening 40%, offtopic 42%. Dates and screens need engine work rather than wording: a month-only screen ("which stocks rise in January"), sub-window search, entry dates past the current market year, event-relative windows (FOMC, Black Friday), and a sector filter.
4. Symbol resolution: `/ResolveSymbol` returns nothing for some US ADRs (TSM, INFY), so a comparison reports them as not found and a bare read relies on the plan retry.
5. A load whose reply quoted a different lookback than the viewer shows becomes "Requested chart setup: ..." plus the remaining prose; correct, but terse.
6. KB items left open because the code does not settle them: tracked-opportunity limits (KB 5/25/100 versus `config.num_opps_per_portfolio = 4`), projection track record, access between cancelling and the end of the paid period.
7. Claude primaries only: answers are longer than the house style (concise/tone pass 65% Haiku, 40% Sonnet). A length rule tuned for Claude was not attempted because the model is the owner's pending decision.

## Spend

Judge $43.43 (1,732 calls). Models $11.66: Sonnet 5.5 $8.11, Luna $2.28, Haiku 5.5 $1.27. Total $55.08 of the $80 cap.
