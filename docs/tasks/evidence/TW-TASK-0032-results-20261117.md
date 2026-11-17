# TW-TASK-0032 results - Tara eval baseline and model comparison (2026-11-17)

Raw outputs (replies, verdicts, per-run reports) are on the dev box under `/root/tara-eval-runs/` (mode 700), not in the repo. No customer identifiers are stored anywhere; every request used a synthetic `tara-eval-<run>-<id>` identity.

## What was measured

- Bank: `tests/fixtures/tara_eval_questions.json`, 731 questions, 22 categories. Sources: 493 predicted, 126 production-log phrasings, 87 dev-log phrasings, 25 from Michael's research set. Personas: 272 beginner, 288 intermediate, 171 pro. Plans: 124 Explorer, 148 Navigator, 231 Analyst, 228 Strategist. Capability: 522 supported, 112 partial, 28 unsupported, 69 boundary.
- Target: live dev, release `93849eaa` (TW-TASK-0031 activated 13:35:06 UTC; identical Tara files to origin/main `dca285fa`). Model: gpt-5.6-luna, low effort, routed KB (max 3 sections).
- Judge: claude-opus-5-5, low effort, full KB as ground truth, structured verdict. Verdict `helpful` = a reasonable user would be satisfied: no false fact, question answered, must-items present, required UI action done.
- Noise: re-running the identical configuration on the 154-question subset flipped 9 verdicts up and 10 down (net -1), so differences under about 5 points on the subset are noise.

## Baseline (headline, post-0031, 731 questions)

**Helpful 34% (251) / partial 43% (316) / unhelpful 22% (164).** Latency p50 1.9s, p90 6.6s.

| dimension | pass | partial | fail |
|---|---:|---:|---:|
| correct (no false facts) | 66% | 19% | 15% |
| answered the question | 62% | 21% | 18% |
| helpful / actionable | 33% | 46% | 21% |
| right UI action | 90% | 3% | 7% |
| concise / tone | 71% | 26% | 3% |
| boundary handling (n=136) | 76% | 13% | 10% |

| category | n | helpful | partial | unhelpful |
|---|---:|---:|---:|---:|
| symbol_research | 29 | 14% | 52% | 34% |
| risk_boundary | 34 | 24% | 65% | 12% |
| comparisons | 25 | 24% | 20% | 56% |
| dates_cycles | 29 | 24% | 41% | 34% |
| getting_started | 30 | 27% | 43% | 30% |
| product | 25 | 28% | 60% | 12% |
| ai_scores | 38 | 29% | 53% | 18% |
| screening | 40 | 30% | 42% | 28% |
| pattern_analysis | 46 | 30% | 43% | 26% |
| troubleshooting | 35 | 31% | 40% | 29% |
| chart_reading | 37 | 32% | 49% | 19% |
| ui_howto | 60 | 33% | 38% | 28% |
| strategy | 30 | 33% | 50% | 17% |
| data_methodology | 30 | 33% | 50% | 17% |
| mcp_api | 25 | 36% | 40% | 24% |
| portfolio_tools | 34 | 38% | 38% | 24% |
| offtopic_markets | 26 | 38% | 46% | 15% |
| account_billing | 35 | 40% | 43% | 17% |
| non_english | 19 | 42% | 42% | 16% |
| multi_turn | 34 | 47% | 32% | 21% |
| messy_input | 26 | 58% | 35% | 8% |
| definitions | 44 | 59% | 34% | 7% |

By persona: beginner 36%, intermediate 34%, pro 32%. By plan: Explorer 44%, Navigator 36%, Strategist 33%, Analyst 29%. By source: dev log 40%, production log 35%, predicted 34%, Michael 24%. By capability: supported 39%, boundary 33%, unsupported 21%, partial 18%.

Pre/post TW-TASK-0031 on the 139 subset questions that ran before activation: 51 helpful / 27 unhelpful before, 53 / 26 after. No measurable change on this bank (inside noise).

## Root causes of the 480 non-helpful answers

| root cause | n | share |
|---|---:|---:|
| retrieval miss (KB has the answer; router attached none of the needed sections) | 221 | 46% |
| shortcut hijack (a deterministic route answered a different question or blocked a good answer) | 109 | 23% |
| model reasoning (facts were present; weak answer) | 106 | 22% |
| error or empty (guard replaced the reply with an error string) | 16 | 3% |
| missing tool or data | 12 | 2% |
| wrong fact with truth available | 9 | 2% |
| UI action error, tone, missing KB | 7 | 1% |

The retrieval bucket is mechanical (judge named the needed KB sections; none were in the routed set). The judge's own unprompted label was `retrieval_miss` for 126 of them. The whole-KB experiment below confirms the direction: it is the single largest lever.

## Top failure clusters (baseline, 731 questions)

File references are `appserver/appserver/` at `dca285fa`.

| # | cluster | n | helpful | type | example | where |
|---|---|---:|---:|---|---|---|
| 1 | Model turn with NO KB section attached (router matched nothing) | 103 | 26% | retrieval miss | "is there a video tutorial somewhere" -> "I can't verify a current tutorial link" (KB documents the Getting Started video) | `tara_prompt_context.py:49` (regex routes), `:296` (weak lexical fallback), `:319` |
| 2 | Model turn with sections attached but not the needed ones (3-section cap; plan/price, definitions, UI map, troubleshooting most often missing) | about 145 | - | retrieval miss | "how much is it" -> sends user to the pricing page, no prices (routed "How Can TradeWave Help Me Trade", needed "Subscription Tiers") | `tara_prompt_context.py:18` (`MAX_TOPIC_SECTIONS = 3`), `:324` |
| 3 | Tool turns that end as a one-line "X long based on the last N years: won ..." announce line, dropping the comparison, dates, extra symbols or the teaching the user asked for | 36 | 25% | shortcut hijack (post-processor) | "compare nvda amd avgo tsm and intc for q1" -> one NVDA line | `tara_gateway.py:2166` (`_announce_line`), `:2240` (`_ensure_load_named`) |
| 4 | View-contract guard replaces the answer with "I couldn't complete that chart request safely" / "Requested view change." | 27 | 0% | error (guard) | "can you actually see what's on my screen?", "exaplin me the chart analysis?", "where are the ai scores?" | `tara_gateway.py:5031-5042`, `:5275-5286`, `:1506`, `:1536` |
| 5 | `investor_guidance` canned reply fires on non-advice questions | 21 | 14% | shortcut hijack | "how do i make the table only show my watchlist stocks" -> suitability disclaimer; "Show me the 20-year seasonal trend for crude oil futures" -> ETF/S&P screen offer | `tara_gateway.py:1051` (`classify_investor_intent`), `:1154` |
| 6 | Deterministic planner answers (canned blocks: "Read:" evidence wall, AI-horizon block, green/red bars) that answer a neighboring question | 88 | 36% | shortcut hijack | "if my pattern is only 9 days is the AI win chance for the exact 9-day window?" -> 90-day-horizon block | `tara_answer_planner.py:5180` (`build_deterministic_reply`), `:4139`, `:4261` |
| 7 | Tool turns for named symbols / dates / screens: wrong window, wrong market resolution, lookback silently changed to 10, no load | 134 | 27% | model reasoning + tool gaps | "what does APPL usually do over the next 30 days" -> March window; "best setup for INFY" -> London listing, plan block; "btc vs eth" -> "cannot run per-symbol crypto" | `tara_gateway.py:65` (TOOLS), `:2449` (`_resolve_question_symbol`), tool loop `run_chat_with_openai_tools` |
| 8 | Loaded-pattern data withheld from the prompt, so Tara says it is "not available" (yearly rows, MAE) | 6+ | 17% | retrieval miss (context gating) | "which year was the worst" -> "individual yearly returns aren't available here" | `tara_prompt_context.py:422` (`needs_yearly_results`), `chatbot.py:1285`, `:1317` |
| 9 | Dead-end answers: correct "no" with no nearest alternative, or an offer instead of acting (largest source of `partial`) | about 89 partial | - | model reasoning (prompt) | "does tradewave work for intraday" -> correct no, nothing offered | stable prompt in `chatbot.py:1106` (`build_system_prompt`); low effort in `openai_tools_appserver.py` (`"effort": "low"`) |
| 10 | Deterministic research routes ignore part of the request | 40 | 48% | shortcut hijack | "compare AAPL and MSFT" -> asks which dates instead of defaulting; Wilshire scan with "15y, min 13 of 15" silently run as 10y, 9 of 10; earnings-filter ask stops at "can't" | `tara_research.py:1692`, `:48` (`_DEFAULT_LOOKBACK`), `tara_prompt_context.py:391` |

Also seen: 99 answers with at least one false fact (most often UI locations and plan facts that are in the KB but were not attached); 11 advice-shaped answers missing the required disclaimer; Explorer/Navigator answers that ignore the user's plan.

## Model and retrieval comparison (154-question stratified subset, private instances on `dca285fa`)

Only the model policy or the KB mode was changed in each private copy. 36 of the 154 are answered by deterministic routes in every variant, so the model can only move the other 118.

| variant | helpful | unhelpful | false-fact answers | model-bound helpful (n=118) | latency p50 / p90 (model turns) | $ per model-bound question | paired vs baseline |
|---|---:|---:|---:|---:|---|---:|---|
| Luna low, routed KB (live baseline) | 36% | 23% | 17% | 36% | 2.3s / 8.0s | - | - |
| Luna low, routed KB (private re-run) | 36% | 24% | 13% | 35% | 2.3s / 7.8s | $0.0009 | +9 / -10 |
| Luna medium, routed KB | 42% | 21% | 12% | 42% | 2.7s / 9.4s | $0.0011 | +18 / -10 |
| Haiku 5.5 low, routed KB | 43% | 22% | 12% | 44% | 3.1s / 9.0s | $0.0010 | +19 / -9 |
| Sonnet 5.5 low, routed KB | 46% | 17% | 12% | 48% | 3.2s / 9.2s | $0.0141 | +20 / -5 |
| Luna low, WHOLE KB cached | 45% | 14% | 6% | 47% | 2.5s / 10.2s | $0.0020 | +22 / -9 |
| Haiku 5.5 low, WHOLE KB cached | 56% | 17% | 8% | 61% | 3.5s / 9.1s | $0.0019 | +37 / -7 |
| Sonnet 5.5 low, WHOLE KB cached | 64% | 14% | 6% | 71% | 3.3s / 8.6s | $0.0218 | +45 / -3 |

Costs are measured token usage priced at list rates (Luna $0.20 / $0.02 cached / $1.20 per 1M, from public listings and not invoice-verified; Haiku 5.5 $0.10 / $0.50; Sonnet 5.5 $2 / $10). The whole KB is about 42K Luna tokens per call, read from cache after the first call.

Readings:
- Whole KB versus routed, same model: Luna +9 points and false-fact answers cut from 13% to 6%; Haiku 5.5 +13 points; Sonnet 5.5 +18 points. Retrieval is confirmed as the largest single lever, and it costs about $0.001 more per question on Luna or Haiku.
- Model at fixed retrieval: Haiku 5.5 is about 7 points above Luna low at the same price; Sonnet 5.5 is a further 3 to 8 points at about 12x the price.
- Luna medium effort: +6 points for +25% cost and +0.4s median latency.
- No variant fixes the deterministic routes and guards: the 36 deterministic questions and the guard-replaced replies score the same in every column.

## Ranked recommendations (estimated lift on the full bank; estimates, to be re-measured with this harness)

1. Send the whole KB in the cached prefix (drop the 3-section regex routing). Measured +9 to +18 points on the subset depending on model, halves false facts. Also removes the routing regex maintenance. Risk: about 42K cached tokens per call; measured cost +$0.001 per question.
2. Fix the view-contract guard and the announce-line post-processor (clusters 3 and 4): 63 questions at 14% helpful. Let a non-chart question through with no action instead of erroring; keep the model's full text when it covers several symbols or a non-load request. Estimated +5 to +7 points.
3. Narrow the deterministic hijacks (clusters 5, 6, 10): `investor_guidance` only for real advice asks, planner blocks only when the question matches the block, research comparison defaults to the upcoming window instead of asking. About 150 questions at about 35% helpful. Estimated +5 to +8 points.
4. Switch the model to Haiku 5.5 (same price as Luna, +7 to +14 points here) or Sonnet 5.5 if about $0.02 per question is acceptable (+19 to +28 with the whole KB). Decide after 1 to 3, re-running the comparison.
5. Always attach the loaded pattern's yearly rows and excursions (cluster 8) and tell the model the user's plan; add a prompt rule "after a 'no', offer the nearest supported thing; act instead of offering" (cluster 9). Estimated +3 to +5 points, mostly partial -> helpful.
6. Tool fixes (cluster 7): honor requested lookback and dates, resolve US listings first, return all compared symbols. Estimated +3 to +4 points, concentrated in symbol_research, comparisons and dates_cycles (the three worst categories).
7. KB gaps found while writing the bank (small volume, high embarrassment): no trial/refund/usage facts, methodology (dividends, survivorship, futures roll), projection track record, calendar-reminder path conflict (KB L1439 versus `tara_prompt_context.py:391` reply), TS column, tracked-opportunity limits versus `config.py:345`.

## Spend

Judge (Opus 5.5): $41.61 over about 1,790 calls. Private model runs: $5.11. Live-dev Luna turns (two full baseline passes): about $1.0 estimated. Total about $47.7 of the $60 cap.

## Caveats

- Prices and plan facts are graded against the KB (Navigator $19, Analyst $47, Strategist $129). If Stripe differs, those rubric items are wrong.
- The judge cannot verify numbers from Tara's research tools for other symbols; it only flags contradictions.
- The subset has 7 questions per category, so per-category differences between variants are not significant; use the totals and paired counts.
- Multi-turn questions replay earlier turns for real but keep the on-screen context static.
- Code refs in the bank were resolved before the TW-TASK-0031 merge; `tara_gateway.py` line numbers in bank refs may be off by the lines 0031 added. KB refs are unaffected (0031 did not change the KB).
