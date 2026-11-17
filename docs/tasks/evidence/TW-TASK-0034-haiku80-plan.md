# TW-TASK-0034 - Plan to raise Tara on Claude Haiku 5.5 from 65% to at least 80% helpful (2026-11-17)

Read-only analysis plus small measured experiments on private instances. No product code was changed. Base code: `origin/claude/tara-quality-round3-20261117` at `2e6a5a63` (TW-TASK-0033). Bank, contexts, judge (claude-opus-5-5, low effort, judge prompt v2) and held-out list are the TW-TASK-0032 ones, unchanged.

## 1. Answer in one page

- Target: at least 80% helpful, at most 3% unhelpful, fewer false-fact answers, at about Haiku cost.
- Today (round-3 code, Haiku 5.5, effort low): 65.0% helpful, 29.8% partial, 5.2% unhelpful on the 577 tuned questions (375 helpful). 80% needs 462, so the gap is 87 questions (15.0 points).
- The gap is not one problem. Deterministic routes are 20% of the questions and 33% of the failures (43% helpful). The model path is 80% of the questions at 71% helpful, and most of its failures are a correct answer that leaves out one item the rubric requires.
- Measured levers (section 5):
  - Deterministic route output rewritten by Haiku: 42.7% to 62.4% helpful on the 117 deterministic questions (paired +29 / -6), which is +4.0 points on the bank. Held-out deterministic questions: 47.2% to 66.7% (paired +7 / -0).
  - Nothing moved the model path. Effort medium, effort high, question-type answer shapes, a relaxed length rule, a self-check repair call and worked examples (few-shot) all landed between 70.9% and 77.0% against a 71.2% control with a standard error near 3.7 points. The one arm that looked like a gain on tuned questions (worked examples, 77.0%) did not repeat on held-out questions (70.3% against 72.0% before). Haiku 5.5 on this prompt sits at about 71% on model-answered questions whatever cheap lever is pulled.
- Measurement: 13% to 19% of the non-helpful verdicts are rubric strictness or rubric ambiguity, not a user-visible defect (section 4). That is 4.5 to 6.6 points of the 15.
- Reaching 80% takes all four kinds of work: route output through the model (+4, measured and repeated on held-out), code fixes sized from the failure clusters (+3 to +6, not yet measured), rubric calibration (+3.5 to +5.5 after overlap), engine work (+1.5 to +2.5). Central estimate 78% to 79%, range 75% to 83%: 80% is at the edge of what the evidence supports for Haiku, and it is not reachable by prompt tuning or effort. The largest cluster (a correct answer missing one required item, 10.7 points) has no proven Haiku lever; Sonnet 5.5 is 12 points better on exactly those turns.

## 2. How this was measured

- Private instances only: `tools/tara_eval/private_instance.py --from-tree`, ports 5081 to 5086, `--no-control-socket`, own pid files, eval-only overlays applied to private copies. Live dev, its control socket, `dev-activation.lock` and every branch other than this one were untouched. All instances were stopped and removed.
- Failure analysis: every one of the 202 non-helpful Haiku verdicts on the 577 tuned questions was read (question, rubric, judge diagnosis) and hand-labelled with one root cause. The judge's own `failure_type` was not used for sizing because it is unreliable for this code (section 4.3).
- Lever experiments, model path: a fixed sample of 120 model-bound tuned questions, 72 drawn from the 135 that failed and 48 from the 325 that passed, re-weighted to the population (135 : 325). A control arm re-ran the unchanged code so that re-roll luck is not counted as lift.
- Lever experiment, deterministic routes: all 117 tuned questions that a deterministic route answers. Their baseline replies are deterministic, so before/after is a clean pair.
- Held-out questions (154) were run only at the end, once for the combined configuration and once for the few-shot configuration, and only aggregate verdicts were read.
- Noise: on the 120-question sample the standard error of the weighted helpful rate is about 3.7 points, so an arm needs roughly 7 points to stand on its own. The same code re-run moved 32% of previously failed answers to helpful and 12% of previously helpful answers to non-helpful.

## 3. Where the 15 points are (577 tuned questions, 202 non-helpful)

| root cause (hand label) | path | n | points of the bank | share of the 15-point gap | unhelpful |
|---|---|---:|---:|---:|---:|
| Correct answer, one required item missing (a caveat, where it is on screen, the undo step, the manual route, the cheapest plan, the median, the disclaimer) | model | 62 | 10.7 | 72% | 0 |
| Route answered the right question but its template omits a required item or shifts the request (no win record with n, Jan 1 becomes Jan 2, 21 years for a 20-year ask, loads the weaker symbol, no disclaimer) | deterministic | 31 | 5.4 | 36% | 1 |
| Did not act, or acted when it should not have (offers instead of loading, no nearest alternative such as SPY for the S&P, unrequested market switch or load, claims an action that was not sent) | model | 20 | 3.5 | 23% | 1 |
| Route answered a neighbouring question or ignored the second intent | deterministic | 18 | 3.1 | 21% | 12 |
| Tool output presented badly (says 8 rows and lists 5, n of 10 then n of 11, rows without record or end date, internal scope text leaked) | model | 16 | 2.8 | 18% | 0 |
| Engine or data gap (no sector tags, TSM and INFY do not resolve, AI values not in the model's context, no pick track record, no current-year YTD, one row from the pattern list) | both | 14 | 2.4 | 16% | 4 |
| Guard or protocol dead end (generic error after repeated violations, reply collapsed to one line or to an upsell fragment) | model | 8 | 1.4 | 9% | 6 |
| Misread intent or ticker (Z as a metric, "in video", "next 3 months on this") | model | 7 | 1.2 | 8% | 4 |
| Canned brief is a wall of text | deterministic | 7 | 1.2 | 8% | 0 |
| Retracts its own earlier turn ("earlier figures were not from a tool run") | model | 6 | 1.0 | 7% | 0 |
| Capability boundary stops at an offer instead of doing the nearest thing | deterministic | 5 | 0.9 | 6% | 0 |
| Wrong language or English line injected into a non-English reply | model | 4 | 0.7 | 5% | 0 |
| Refuses or botches a simple derivation from on-screen rows (average without the best year, list of midterm years) | model | 4 | 0.7 | 5% | 2 |
| Total | | 202 | 35.0 | 233% | 30 |

The shares add to more than 100% because the non-helpful answers (35 points) are more than twice the gap (15 points): any 87 of the 202 close it.

By path: deterministic routes 117 questions, 50 helpful (43%), 67 non-helpful. Model path 460 questions, 325 helpful (71%), 135 non-helpful.

Three facts that shape the plan:

1. Model-path failures are mostly unstable, not systematic. Across seven re-runs of the 72 sampled failures, 25 (35%) never passed, 16 passed once or twice, and 31 passed three or more times. The 48 sampled passes held 88% of the time. So the model path is a spread of per-question pass probabilities around a stable 71% mean; raising it means raising completeness on every turn, not fixing a list of questions.
2. Sonnet's advantage is completeness. On the 141 model-bound tuned questions both models answered, Haiku is helpful on 70% and Sonnet 5.5 on 82%. Sonnet wins 27 and loses 11; 15 of its 27 wins are the "one required item missing" cluster. Sonnet writes longer answers (median 674 characters against 499).
3. The unhelpful 5.2% is concentrated: 12 of 30 are routes answering a neighbouring question, 6 are guard dead ends, 4 intent misreads, 4 engine gaps.

False facts (14.2% of answers flagged, 105 items): internal count or list contradictions 19, window dates and day counts 13, plan or price facts 11, the current-year bar called live on its entry day 5, AI values quoted without being in context 5, n against lookback 4, 1.93 against 1.94 from a route 4, Sharpe Ratio2 called TWR 3, retractions 3, claimed actions 3, other 35. Deterministic routes carry 22 of the 82 flagged answers.

## 4. Judge and rubric audit

### 4.1 Sample audit

26 non-helpful and 14 helpful verdicts were drawn at random and re-graded by hand against the question, rubric, reply and actions.

- Helpful verdicts: 14 of 14 stand. The judge is not lenient.
- Non-helpful verdicts: no factual judge error found. 3 of 26 are rubric problems outright and 4 are borderline:
  - pat-040 "does it usually give back gains": a complete year-by-year answer is marked partial for not adding "MFE and MAE are not targets or stops".
  - pat-016 "is this continuous front month, how do you handle the roll": accurate answer marked partial for not adding "end-of-day closes".
  - scan-024 "opportunities in the next week": the rubric demands the next calendar week (Nov 23 to 29); the reply used the next seven days, which is the ordinary reading.
  - Borderline: ai-031, fix-010, data-022 (a good answer missing one explanatory clause) and scan-015.
- Counting borderline as half: 5 of 26, 19% of non-helpful verdicts (wide interval at this sample size).

### 4.2 Structural estimate

27 of the 202 non-helpful verdicts (13%) pass every graded dimension, have no false fact, and miss exactly one must item. That is the population where rubric strictness alone decides the verdict.

### 4.3 What it means

- Measurement share of the gap: 13% to 19% of non-helpful, 26 to 38 questions, 4.5 to 6.6 points, 30% to 44% of the 15-point gap.
- "True" helpfulness of today's Haiku by a reasonable-user standard: about 70% to 72%, not 65%. The same correction lifts Luna and Sonnet too, so recalibration does not change the model ranking; it changes how far Haiku is from 80.
- The judge prompt makes any missing must item a partial. Many must lists mix what the user asked for with good-practice extras. Recalibration means moving extras from `must` to `ideal` by rule (a must item is something without which this user cannot act or would be misled), fixing ambiguous items (next week, GLD against GC for "gold"), and re-judging every model.
- `failure_type` is stale for round-3 code: the harness still passes the old regex router's `routed_kb` to the judge, so the judge blames "retrieval miss" (17 times) although the whole knowledge base is in the prompt. Drop `routed_kb` from the judge payload when the whole KB is attached.
- Single-run scores carry about 2 points of noise on the full bank and far more on subsets. Report the mean of two runs for model comparisons, or pair on deterministic questions.

## 5. Lever experiments

### 5.1 Model path (120-question sample, weighted to the 460 model-bound tuned questions)

Cost is measured token usage at list price ($0.10 input, $0.01 cache read, $0.50 output per 1M) with a warm cache. Latency is end-to-end per question.

| arm | helpful | unhelpful | false-fact answers | concise pass | failed stratum helpful (n=72) | passed stratum helpful (n=48) | $ per question | p50 / p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Control: round-3 code, effort low (re-run) | 71.2% | 5.1% | 11.4% | 68.6% | 32% | 88% | 0.00196 | 4.5s / 11.2s |
| Effort medium | 70.9% | 4.1% | 11.3% | 60.1% | 21% | 92% | 0.00217 | 5.2s / 13.3s |
| Answer shapes (question-type slots, no-retraction rule, language rule), low | 70.9% | 2.4% | 15.8% | 63.8% | 36% | 85% | 0.00205 | 4.2s / 11.6s |
| Answer shapes, medium | 72.4% | 4.1% | 9.3% | 60.3% | 36% | 88% | 0.00232 | 5.3s / 12.9s |
| Answer shapes, high | 73.9% | 1.6% | 11.3% | 66.8% | 36% | 90% | 0.00251 | 8.1s / 18.1s |
| Answer shapes + relaxed length rule ("2 to 5 short lines, completeness beats brevity"), low | 71.4% | 6.9% | 11.6% | 54.3% | 38% | 85% | 0.00210 | 4.5s / 12.1s |
| Answer shapes + self-check repair call, low | 74.3% | 2.4% | 12.8% | 61.2% | 38% | 90% | 0.00340 | 6.6s / 15.2s |
| Answer shapes + six worked examples (few-shot), low; not repeated on held-out, see 5.2 | 77.0% | 2.9% | 13.1% | 62.8% | 42% | 92% | 0.00212 | 4.4s / 10.9s |

Reading:

- Effort is not a lever here. Medium costs 11% more and 0.7s, high costs 28% more and 3.6s at the median, and neither moved helpfulness. On tool turns medium was worse on the failed stratum (5 of 36 against 10 of 36). Selective effort for analytical turns therefore has no support either. One API fact was confirmed on the way: the medium arm read the prompt cache the low arm had written (cache read 70,345, cache write 0), so on Haiku 5.5 a top-level effort change does not invalidate the cached system prefix.
- Rules alone do not change Haiku at low effort. With a new rule saying "when the term is one of a set, name the whole set", Haiku still answered "what is pe+2" without listing the cycle. The prompt is about 70K tokens with about 20K of accumulated rules; one more rule is not read as a priority.
- The repair call rewrote 110 of 120 answers instead of approving most of them, cost 73% more and 2 seconds, and gained 3 points inside the noise. Not worth it in this form.
- Worked examples looked like the one lever that moved (+5.8 points; the "one required item missing" cluster went from 12 of 38 to 20 of 38 helpful in the sample) but the held-out check in 5.2 did not repeat it, so it is recorded as not confirmed. What did repeat on held-out questions is a tidier answer: concise pass 65% to 75% and false-fact answers 16.9% to 13.6%. Cost +8% on the tuned sample, no latency change, prompt +1.2K tokens for the examples (+2.5K with the answer shapes; cached prefix 72.8K). The examples are invented questions (none is a bank question) answered from knowledge-base facts in the shape direct answer, each relevant fact on one short line, one next step.
- The no-retraction rule works as written: on the 39 multi-turn model questions, retraction phrases fell from 14 replies to 0, false-fact answers from 13 to 8 and concise pass rose from 13 to 19. Helpful stayed flat (18 to 19), so it is a correctness and tone fix, not a helpfulness lever.

### 5.2 Held-out checks (154 questions never used for tuning; aggregates only)

| configuration | n | helpful | partial | unhelpful | false-fact | paired up / down |
|---|---:|---:|---:|---:|---:|---|
| Round-3 Haiku (TW-TASK-0033 run), all held-out | 154 | 66.2% | 27.3% | 6.5% | 18.8% | |
| Answer shapes + route rewrite, all held-out | 154 | 68.8% | 22.1% | 9.1% | 16.2% | +15 / -11 |
| - deterministic-route questions, before | 36 | 47.2% | 38.9% | 13.9% | 25.0% | |
| - deterministic-route questions, after rewrite | 36 | 66.7% | 16.7% | 16.7% | 19.4% | +7 / -0 |
| - model-bound questions, before | 118 | 72.0% | 23.7% | 4.2% | 16.9% | |
| - model-bound questions, answer shapes only | 118 | 69.5% | 23.7% | 6.8% | 15.3% | +8 / -11 |
| - model-bound questions, answer shapes + worked examples | 118 | 70.3% | 22.9% | 6.8% | 13.6% | +12 / -14 |

The route rewrite holds on held-out questions (+19.5 points on deterministic questions, no paired loss). Neither answer shapes nor worked examples lift held-out model questions: 69.5% and 70.3% against 72.0% before, all inside the noise of a 118-question run. The model path is flat.

### 5.3 Deterministic routes through the model (117 tuned questions)

The overlay keeps every route exactly as it is, then hands its reply and queued actions to Haiku as a verified engine draft with the instruction to answer the question actually asked, reuse the draft's numbers and action statements unchanged, drop sections nobody asked for and add what is missing. The advice-disclaimer floor still runs afterwards and actions are untouched (117 of 117 identical).

| | helpful | partial | unhelpful | false-fact answers | concise pass | $ per question | p50 / p90 |
|---|---:|---:|---:|---:|---:|---:|---|
| Route reply as today | 42.7% | 44.4% | 12.8% | 18.8% | 48.7% | 0 | 0.03s / - |
| Route reply rewritten by Haiku | 62.4% | 29.9% | 7.7% | 25.6% | 20.5% | 0.00116 | 2.5s / 6.8s |

Paired +29 / -6. Gains by cause: template gaps 18 of 31 fixed, neighbouring-question routes 7 of 18, walls 4 of 7. Planner blocks moved from 25 to 39 of 55 helpful.

What the raw overlay got wrong, and what the real implementation must add:

- It has no tools, so it cannot scan or load. About 9 of the remaining 44 failures are "offered instead of doing" (capability boundaries, "pull up the first one", sector screens on the wrong plan). Run the draft through the normal tool loop instead of a tool-less call.
- It wrote longer replies (median 929 characters against 721) and concise pass fell to 20%. Give the rewrite a hard length rule per route.
- False-fact answers rose from 18.8% to 25.6% and six previously helpful answers regressed, three of them on a wrong label or figure. Add a number guard: every figure in the rewrite must appear in the draft or the live context, otherwise send the draft.
- It was called without the tool list and therefore wrote its own 68.7K-token cache entry. Pass the same tools so it shares the chat prefix cache.

## 6. Cost and latency

| configuration | $ per question, all questions, warm cache | p50 / p90 |
|---|---:|---|
| Round-3 Haiku today (held-out run) | 0.00144 | 2.9s / 9.7s |
| Answer shapes + route rewrite (held-out run) | 0.00172 | 3.2s / 9.7s |
| Route rewrite + worked examples, estimated from the arms | about 0.0018 | about 3.3s / 10s |

- Every lever recommended here stays within about 30% of today's Haiku cost. Sonnet 5.5 measured $0.026 per model-bound question in TW-TASK-0033, about 13 times more.
- The 100K-token price step matters more than any lever: Haiku 5.5 is $0.10 / $0.50 per 1M tokens up to a 100K-token prompt and $0.50 / $2.50 above it. The cached prefix is 70.3K tokens and the largest call seen was 78.5K. Knowledge-base growth has about 15K tokens of room; examples and answer cards must be paid for by trimming rules, not by adding on top.
- The eval figures assume a warm cache. A question that arrives after five idle minutes writes the 70K prefix again: about $0.0088 against $0.0007 for a read, so a cold question costs about five times the table figure. At real Tara traffic this will dominate the bill. Options, in order: a keep-alive pre-warm during active hours (a `max_tokens: 0` request with identical tools, system, thinking and effort; twelve reads an hour is under $0.01 an hour), or the one-hour TTL ($0.0141 per write) if gaps are usually between five minutes and an hour.
- Latency: the route rewrite turns an instant canned reply into a 2.5s model reply for 20% of questions. The worked examples add no latency. Effort high would nearly double median latency for no gain.

## 7. Ranked implementation plan

Lift is in points of the 577 tuned questions. "Measured" means judged in this task; "sized" means the cluster size times a recovery rate, discounted for the re-roll noise above.

| # | step | kind | expected lift | evidence | notes |
|---:|---|---|---:|---|---|
| 1 | Send every deterministic route's reply through Haiku as a verified engine draft, inside the normal tool loop, with a number guard and a per-route length rule | code + prompt | +4 (measured), +5 to +6 with tools and guard | 5.3, 5.2 | Largest single measured gain. Keeps the engine as the only source of numbers; plan gates, AI entitlement, the Explorer date lock and the disclaimer floor run exactly as today because the routes still run first and `_finalize_chat_response` is unchanged. Fall back to the draft on any guard failure. |
| 2 | Add six to ten worked examples to the cached prefix, and delete rules to pay for them | prompt | 0 on helpful (not confirmed); concise pass +10 points and false-fact -3 points on held-out | 5.1, 5.2 | Optional tidy-up, not a path to 80. Keep examples generic and off the bank. |
| 3 | Fix route templates the rewrite cannot fix: win record with n in best-waves and window-study replies, Jan 1 kept as Jan 1, n equal to the requested lookback, load the stronger of two compared symbols, crypto ticker ambiguity (BTC, ETH), Explorer sector screen on Dow 30, exclusion-report location question | code | +1.5 to +2.5 | section 3, list after 5.3 | 13 template and 11 neighbouring-question failures remain after the rewrite. |
| 4 | Guard and protocol dead ends: never return the generic "couldn't send the complete chart action" or a one-line remnant; when corrections are exhausted, answer in words and say nothing was changed; handle `stop_reason: "refusal"` by using the fallback provider | code | +0.7 to +1.0, unhelpful -1.0 | cluster of 8 (6 unhelpful) | The Anthropic adapter does not check for a refusal today; Haiku 5.5 has no server-side fallback, so an empty text would reach the guards. |
| 5 | Render scan and comparison lists in code from the tool rows (symbol, direction, entry, end date, W of N, average, the count actually shown) and let the model write only the lead and the read | code | +1.0 to +1.5, false-fact -3 | cluster of 16; 19 count contradictions | Removes "says 8, lists 5" and missing n or end dates at the source. |
| 6 | Put engine facts the model lacks into the live context: AI values for the loaded pattern when the user is entitled and they exist, the current-year row's state (upcoming, active day k of n, completed), Sharpe Ratio2 labelled, the plan ladder with the cheapest plan per market | code | +0.5 to +1.0, false-fact -2 | engine cluster, false-fact list | The deterministic AI route already fetches trusted AI values; the model path does not see them. Entitlement check unchanged. |
| 7 | Multi-turn: keep the no-retraction rule; stop emitting a market-only `set_view` for a scan the user did not ask to see in the table; keep the injected announce line in the user's language | prompt + code | +0.5 to +1.0, false-fact -1 | 5.1, 4 + 4 + 6 cases | Retractions 14 of 39 to 0 measured. |
| 8 | Recalibrate rubrics by rule and repair the judge payload, then re-baseline all three models; report two-run means | eval | +3.5 to +5.5 after overlap with step 1 | section 4 | Measurement, not product. Do it before deciding whether Haiku has reached 80. |
| 9 | Engine and product work: sector tags or a sector filter, US-listing resolution for ADRs (TSM, INFY), engine-computed average without the best or worst year and the list of cycle years, the pick's forward track record in `explain_pick`, current-year running return for YTD asks, month-only screens and sub-window search | engine | +1.5 to +2.5 | clusters of 14 and 4 | The no-arithmetic rule is correct; these are numbers the engine should hand over so the model does not have to refuse. |
| 10 | Knowledge-base answer cards: for the top question families (definitions, how-to, troubleshooting, plan questions, risk boundaries), a short "a complete answer covers" line beside the facts | KB | 0 to +2, unproven | 62-question cluster; every generic prompt version measured flat | Low prior after 5.1. Test on two categories with tuned and held-out questions before writing the rest. Must fit the 100K-token budget. |
| 11 | Only if the two-run score after steps 1 to 9 is short: send completeness-sensitive turns (definitions, strategy, risk boundaries, onboarding, about a third of model turns) to Sonnet 5.5 | model routing | +2 to +4 | Sonnet 82% against Haiku 70% on the same 141 model questions; it won 15 of the 22 "one item missing" failures compared | Owner decision (Sonnet was deferred). Blended cost near $0.009 per question, about five times Haiku. Sonnet alone does not reach 80 either: it was 73% on the bank in TW-TASK-0033 because routes and rubric strictness cap it too. |

Not recommended on this evidence: effort medium or high, per-turn effort, a second self-check call, more global rules, relaxing the length rule on its own, and any further prompt-only round aimed at the model path.

Projection (tuned questions): 65.0 today; 69 after step 1 (measured); 72 to 75 after steps 3 to 7 (sized, not measured); 75.5 to 80.5 after step 8; 77 to 83 after step 9. Central estimate 78% to 79%. Only step 1 is proven; steps 3 to 7 fix defects that were each read in the transcripts, but their lift is an estimate and each must be re-measured as it lands. Treat 80% as a stretch for Haiku that needs steps 1 to 9 to land near the top of their ranges, or step 11.

Unhelpful at most 3%: today 30 of 577 (5.2%). Step 1 removed 6 of the 15 unhelpful route answers on tuned questions and step 4 addresses 6 more, which gives about 3.1%; the two intent fixes in step 3 and step 9's ADR resolution take it under 3%. Note the held-out run did not show an unhelpful improvement (6.5% to 9.1%, 10 to 14 answers), so step 1 must ship with the tool loop and the guard before this claim is counted.

False facts: steps 5, 6 and 7 remove the three largest sources (list contradictions, live-bar and label errors, retractions). The raw rewrite increased false-fact answers on route questions; the number guard in step 1 is a release condition, not an optimisation.

## 8. What needs engine or product work, and what does not

- Prompt and knowledge base only: step 2, the rule half of step 7, step 10.
- Appserver code (Tara gateway, planner, prompt context): steps 1, 3, 4, 5, 6, the code half of step 7.
- Eval harness: step 8.
- Engine or product: step 9; in step 6 the AI values and current-year state come from data the engine already returns.

## 9. Claude API notes (Haiku 5.5)

- Request shape in round 3 is right: adaptive thinking, `output_config.effort`, no sampling parameters, no forced `tool_choice`, thinking blocks skipped when reading text.
- Effort default on Haiku 5.5 is medium; Tara pins low explicitly, which the data supports.
- A top-level effort change did not invalidate the cached prefix (measured). The beta per-message effort system message is not needed.
- Check `stop_reason` before reading content: a classifier refusal is HTTP 200 with no text, and Haiku 5.5 does not accept the `fallbacks` parameter. Route it to the existing fallback provider.
- Protocol corrections are sent as user turns after an assistant turn. A mid-conversation `role: "system"` message cannot follow an assistant turn, so the current placement is the available one; keep the "answer for the user only" suffix.
- Keep the tool list and system prefix byte-identical on every call that should share the cache (the rewrite call included), and keep the prompt under 100K tokens.

## 10. Reproduce

- Overlays: `/root/tara-eval-runs/h80/patch.py` (answer shapes, repair, route rewrite), `patch2.py` (length rule), `patch3.py` (worked examples); committed copies under `docs/tasks/evidence/TW-TASK-0034-overlays/`. They are eval-only and patch a private copy of the round-3 tree.
- Sample: `/root/tara-eval-runs/h80/sample.json` (72 failed + 48 passed model-bound ids, 117 deterministic ids).
- Runs under `/root/tara-eval-runs/`: `h80-a0` control, `h80-a1` medium, `h80-p1` shapes, `h80-p1m` shapes medium, `h80-p1h` shapes high, `h80-p2` shapes + length rule, `h80-p1r` shapes + repair, `h80-p3` shapes + examples, `h80-det` route rewrite, `h80-p2-multi` multi-turn, `h80-final-heldout` and `h80-p3-heldout` held-out checks.
- Hand labels for the 202 failures: kept with the raw runs on the dev box (`/root/tara-eval-runs/HAIKU80_PLAN.md`, appendix).

## 11. Spend

Judge $34.91 (1,365 calls), Haiku 5.5 $3.12, total $38.03 of the $40 cap. Experiments stopped there; every private instance is stopped and its private tree removed.
