# TW-TASK-0033: Tara quality round 3 - whole knowledge base, repairing guards, narrowed routes, one-line model policy

- Status: fixed on branch, awaiting dev integration and activation (not activated, main not pushed, by instruction)
- Confidence: reproduced (measured with the TW-TASK-0032 harness on private instances)
- Priority: P1 - Tara was helpful on 34% of the 731-question bank and unhelpful on 22%
- First observed / last updated: 2026-11-17T14:30:00+00:00 / 2026-11-17T16:40:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T14:45:00+00:00
- Authorization: Afshin asked for the model-agnostic fixes ranked 1, 2, 3, 5, 6 and 7 in the TW-TASK-0032 results, measured with that harness, with the primary model left unchanged but switchable in one line. Scope: code, knowledge base, tests, harness and records on a task branch; private measurement instances only. Dev activation, pointers, live services, `dev-activation.lock` and main excluded. API budget cap $80.

## Goal, Scope and Acceptance

Raise Tara's measured helpfulness without changing the primary model.

1. Whole knowledge base in the cached stable prefix; the 3-section regex routing is no longer the gate.
2. The view-contract guard and the load-announcement guard keep their safety purpose (never claim an action that did not happen; the loaded setup's own record) but keep the prose answer.
3. Deterministic routes answer only the question they were written for (investor funnel, planner blocks, direction flip, research routes, capability boundaries).
5. The loaded pattern's yearly rows and MAE, the user's verified plan and today's date are always in the prompt; rules: do the nearest useful thing, act rather than offer.
6. Tools honour the requested lookback and dates, prefer the US listing of a bare ticker, and return every compared symbol.
7. KB gaps: trial, refund, cancel and usage facts; price basis, survivorship and futures methodology; the calendar-reminder conflict. Only facts verified in code or published pages.
- Also: the duplicated plan-boundary sentence.

Non-negotiables kept: the engine is the only source of numbers (no model arithmetic on statistics; a prompt rule now says so, and extremes are selected by code from engine rows); the TW-TASK-0031 plan gates (`_plan_scope` on the verified `g.chatbot_jwt`) are untouched; the advice disclaimer floor (`ensure_required_disclaimer` in `_finalize_chat_response`) is untouched; every existing test stays green; nothing is special-cased to a bank question.

Acceptance: measured lift on the full bank with the current model, held-out subset reported separately from the tuned questions, and the same bank on Haiku 5.5 and Sonnet 5.5.

## Evidence and Investigation

Results: [evidence/TW-TASK-0033-results-20261117.md](evidence/TW-TASK-0033-results-20261117.md).

| model (whole KB, this branch) | n | helpful | partial | unhelpful | false-fact answers | held-out helpful | rest helpful | $ per model-bound question | latency p50 / p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline, live dev (Luna low, routed KB) | 731 | 34% | 43% | 22% | 22% | 36% | 34% | about $0.0009 | 2.3s / 7.4s |
| Luna low (current model) | 731 | 56% | 39% | 5% | 12% | 57% | 56% | $0.0019 | 2.3s / 8.0s |
| Haiku 5.5 low | 731 | 65% | 29% | 5% | 15% | 66% | 65% | $0.0019 | 3.6s / 8.8s |
| Sonnet 5.5 low | 330 | 73% | 22% | 4% | 18% | 73% | 74% | $0.0260 | 3.6s / 8.1s |

Facts verified for the knowledge base (fix 7), with their source:

- 7-day Strategist-level trial granted once at account creation, then Explorer: `web/app.py` (user create sets `reverse_trial_ends_at = now + 7 days`, CREATE path only), `effective_tier`, `config.level_access_hierarchy`.
- Refund wording: the published contact FAQ in `site/generate_text_pages.py` ("Subscription fees are generally non-refundable ... case-by-case"). Contact address `help@tradewave.ai` from the same file.
- Plan limits: `config.num_portfolios_allowed_by_level`, `num_watchlists_allowed_by_level`, `num_watchlist_items_allowed_by_level`, `num_opp_reports_allowed_by_level`, `num_years_allowed_by_level`.
- Price basis: `appserver/appserver/get_symbol_csv.py` `adjust()` scales open/high/low/close by `adjusted_close / close`; `buy_hold_across_time.py` states the provider adjusts for splits and dividends and that completeness is not audited.
- Survivorship: lists come from the provider's current `exchange-symbol-list` (`data_updater/create_symbols_file.py`); no point-in-time membership exists in the code.
- Futures: provider commodity series under the root symbol; the only TradeWave splice is lumber LB to LBR (`data_updater/EOD_downloader3.py`). The provider's roll rule is not in the repo, and the KB says so.
- Not settled by the code and therefore NOT written as fact: tracked-opportunity limits (KB 5/25/100 versus `config.num_opps_per_portfolio = 4`), access between cancelling and period end, any paid-plan trial.

## Acceptance and Regression Checks

- `pytest tests/ -m "not db"`: 2481 passed, 5 skipped (2385 before this task; 96 new in `tests/test_tara_quality_round3.py` and `tests/test_tara_research_engine_answers.py`). db-marked suites not run (they need the `tradewave_test` database).
- One existing test changed on purpose: `test_comparison_without_dates_asks_for_the_window` became `test_comparison_without_dates_uses_a_stated_default_window` (the owner asked for a default window instead of a question back).
- `tools/tara_eval/build_bank.py --check` passes (new KB sections are appended, so every cited KB line is unchanged).
- `git diff --check` clean.
- Not run: browser checks (no React change), staging gates.

## Implementation and Handoff

Branch `claude/tara-quality-round3-20261117`, worktree `/home/tradewave-worktrees/tara-quality-round3-20261117`, based on origin/main `dca285fa` with `origin/claude/tara-eval-20261117` (`1ca3f9b3`) merged in for the harness. Final SHA: see the branch head and the handoff file `/home/tradewave-handoffs/20261117-tara-quality-round3/HANDOFF.md`.

What changed (paths under `appserver/appserver/`):

- `chatbot.py`: `_KNOWLEDGE_BLOCK` and `_ANSWER_QUALITY_RULES` in the stable prefix; yearly rows and MAE always attached; `ENGINE-SELECTED EXTREMES`; `TODAY`; `USER PLAN`; `_FINAL_CHECKS`; pricing rule; provider dispatch (`run_model_turn`, report turn); ordinal references to Tara's previous list; sentence-level repair in the final checks.
- `tara_gateway.py`: `repair_view_contract`, `repair_investor_contract`, `_finish_tool_reply` (one tail for both provider loops), `_ensure_load_named` and `_announce_line`, `_describe_view_actions`, `plan_context_lines`, `_apply_user_stated_request`, `_clamp_read_years_to_plan`, `_prefer_us_listing` / `_us_listing_market`, `_scan_window_is_not_today`, `_PLAN_BOUNDARY_MARKER`, narrowed `classify_investor_intent` and `_CAPABILITY_GUIDE_RE`, Claude-loop corrections (`_protocol_correction`, `soft_view_check`).
- `tara_answer_planner.py`: `question_exceeds_canned_scope`, single-metric definitions, `previous_list_ordinal_target`.
- `tara_prompt_context.py`: `_DIR_NOT_FLIP_RE`; capability replies name the nearest working step. `select_topic_knowledge` is kept as a tested library but no longer called by the prompt builder.
- `tara_research.py`: lookback wordings, seasons, "next month", default comparison window, lower-case tickers and "X or Y" comparisons, up to 6 symbols, unresolved tickers reported, plan-limited empty screen names what the plan can do.
- `tara_runtime_policy.py`, `tara_model_router.py`, `AI_tools_appserver.py`, `openai_tools_appserver.py`, `portfolio_scenarios.py`: `ACTIVE_POLICY` switch and the Claude 5 request shape.
- `chatbot_knowledge.txt`: two appended sections and the earnings/calendar entries aligned with the deterministic replies.
- `tools/tara_eval/private_instance.py`: `--policy`, `--from-tree`; README.
- `docs/TRADEWAVE_ECOSYSTEM.md`: the prompt, guard and policy architecture.

To make a Claude model the primary: change `ACTIVE_POLICY = "luna"` to `"haiku55"` or `"sonnet55"` in `tara_runtime_policy.py` and update the pinned values in `tests/test_tara_runtime_policy.py` and `tests/test_tara_openai_canary.py` in the same commit. The other provider becomes the fallback automatically.

Activation requirements: backend only. Restart the appserver (gunicorn does not reload; the KB is read at start). No React build, migration, dependency, nginx or secret change. The release fingerprint's `prompt_hash` and `planner_hash` change. Expect about 42.6K cached input tokens per model call (measured $0.0019 per model-bound question on Luna, up from about $0.0009) and one cache write per OpenAI cache shard after a restart. Rollback: redeploy the previous release; nothing persistent changes.

Risks: (1) the model now answers questions the deterministic blocks used to take (compound, troubleshooting, count questions); advice-shaped turns and AI-value readings are excluded from that on purpose. (2) `_apply_user_stated_request` overrides a model-chosen window when the user wrote "next N days". (3) Claude primaries are longer-winded than the house style. (4) Held-out and tuned scores agree, but the bank is still one author's prediction of user questions.

Decisions: the calendar and earnings conflicts were resolved by making the KB describe what the deterministic replies do (existing tests pin those replies) and by adding the nearest working step to the replies. Sonnet was measured on 330 questions, not 731, for budget. Next action (orchestrator): review, integrate on current origin/main, activate on dev, smoke with a pricing question, a compare without dates and a "can you see my screen" question; owner picks the primary model from the table.

## Environment Verification

Dev: not activated by this task (private instances only). Staging: not checked. Production: not checked.

## History

- 2026-11-17T14:45:00+00:00: Claude claimed the task on branch `claude/tara-quality-round3-20261117`.
- 2026-11-17T15:33:00+00:00: mid-point on 176 tuned questions: helpful 31% to 49%, unhelpful 19% to 3%.
- 2026-11-17T16:40:00+00:00: final runs complete (Luna 56%, Haiku 5.5 65%, Sonnet 5.5 73% helpful); branch pushed. Spend $55.08 of $80.
