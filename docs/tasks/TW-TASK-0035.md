# TW-TASK-0035: Tara on Claude Haiku 5.5 - steps 1 to 6 of the Haiku-80 plan

- Status: phase A (918626f1) verified live on dev and on main, with the engine-reply lead OFF (`tara_gateway.DRAFT_REWRITE_ENABLED = False`). Phase B (this branch head) replaces the withdrawn rewrite with a lead-only design that stays OFF pending re-review; measured, it adds no helpfulness, so the recommendation is to leave it off. Sections below that describe a model rewrite of engine replies refer to commit 8ff5a607 and are superseded by the results file, section 8.
- Confidence: reproduced (measured with the TW-TASK-0032 harness, judge v3 and the TW-TASK-0036 bank, on a private instance)
- Priority: P1 - the owner chose Haiku 5.5 for cost; the target is at least 80% helpful, at most 3% unhelpful, no more false facts
- First observed / last updated: 2026-11-17T19:25:00+00:00 / 2026-11-17T21:30:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T19:25:00+00:00
- Authorization: implement steps 1 to 6 of the TW-TASK-0034 plan in the appserver Tara code, knowledge base, tests and docs on this branch; measure on private instances only (own port, `--no-control-socket`, own pid file). Excluded: dev activation, main, live services, `/home/flask/.gunicorn/gunicorn.ctl`, pointers, `dev-activation.lock`, the eval bank and judge (owned by TW-TASK-0036). API budget cap $50.

## Goal, Scope and Acceptance

Raise Haiku 5.5 helpfulness toward 80% without raising false facts or unhelpful answers, keeping: the engine as the only source of numbers, the plan gate on verified claims, AI entitlement, the Explorer date lock, the exact disclaimer floor, the view-claim guard, and a byte-stable cached prefix under 100K tokens.

1. Engine route replies become verified drafts the model rewrites inside the tool loop, with a number guard, a length rule and a fallback to the draft; compliance-only replies stay deterministic.
2. Route templates the rewrite cannot fix: win record with n, date and lookback fidelity, BTC/ETH ambiguity, Explorer sector screen.
3. Scan and comparison lists rendered in code.
4. Guard dead ends removed; `stop_reason: "refusal"` handled on every Anthropic path.
5. AI values (entitled users only), current-year bar state and the plan ladder in the live context.
6. No-retraction rule kept, market-only view switch dropped, injected lines in the user's language.
7. "All 15 markets": verified against config and stated in the knowledge base.
8. Coordinator addition (TW-TASK-0036 referee findings): five knowledge-base-versus-code mismatches, each checked against code first.

## Evidence and Investigation

Results, method and per-step measurements: [evidence/TW-TASK-0035-results-20261117.md](evidence/TW-TASK-0035-results-20261117.md).

What was verified before changing anything:

- Refusal handling (plan said the adapter did not check it): the tool loop already raised `ProviderNoAnswer` on `stop_reason: "refusal"` since TW-TASK-0033 S2. The gap was the text-only calls (`send_claude_messages` without `return_raw`: report explanation, no-tools path), where a refusal became an empty reply. Closed with `AnthropicRefusal`.
- Market count: `config.available_resources` has 15 groups (ids 0 to 13 and 16); the knowledge base listed all 15 but never said the number. Now stated in the KB and in the live `PLAN LADDER` block, both tied to config by a test.
- January 1: the engine itself moves a January 1 entry to January 2 (`appserver.py` ChartData4, "January 1st edge case"). The old template slid the whole window (Jan 2 to Apr 1) without saying so.
- Lookback: when this year's window has already finished the engine returns the lookback plus one completed year (20 asked, 21 returned).
- `Sharpe Ratio2` is the TradeWave Ratio (MFE based); the planner already treated it so. The planner's average was the mean of two-decimal rows (1.93) where the engine's own stat is 1.94.
- Referee KB items: scans do rank by AIS / AI Win% / PredR (`tara_gateway.TOOLS`, `rank_by`); Annualized Return is the compound per-occurrence return (`appserver.py`); the daily pick's `track_record` was dropped by `_briefify`; Scenario Studio (Import / Scenario / Reports buttons in the Portfolio Manager title bar, `ReportsDashboard.js`, `PortfolioScenarios.js`, `portfolio_scenarios.py`) was not in the KB; API limits are in `apiserver/tiers.py`.

## Acceptance and Regression Checks

- `pytest tests/ -m "not db"`: 2,569 passed, 5 skipped (2,526 at e2294724; 43 new tests in `tests/test_tara_engine_drafts.py`). db-marked suites not run (they need the `tradewave_test` database).
- `python3 tools/tara_eval/build_bank.py --check`: pass after the KB edits (in-line edits and two sections appended at the end, so no cited line moved).
- `git diff --check`: clean.
- Cached prefix: 70,185 tokens (system block plus tools, `messages.count_tokens`, claude-haiku-5-5); largest request in 1,690 measured calls 93,969 tokens (one outlier; all others under 85K). Byte-stability is asserted in `test_no_retraction_and_language_rules_are_in_the_cached_prefix`.
- Older route tests keep pinning the engine replies: `tests/conftest.py` turns the rewrite off for them (`tara_gateway.DRAFT_REWRITE_ENABLED`), because the engine reply is exactly what every guard failure falls back to. Tests that exercise the rewrite carry `@pytest.mark.tara_draft_rewrite`.
- Tests whose expectation changed on purpose: one closing request after the last round (`tool_choice` none), an answer in words accepted after one request for a chart action, no market-only switch unless asked, January 1 and lookback studies. `tests/fixtures/tara_research_engine_20261117.json` gained 12 engine responses recorded from the dev engine on the fixture's own date (read-only GETs) for the January 2 / 89-day requests.
- Not run: browser checks, db suites, Luna (OpenAI) as primary. The OpenAI loop received the same draft, list and fallback code and is covered only by the shared unit tests.

## Implementation and Handoff

Branch `claude/tara-haiku80-impl-20261117`, worktree `/home/tradewave-worktrees/tara-haiku80-impl-20261117`, based on origin/main `e2294724` with `origin/claude/tara-haiku80-plan-20261117` (TW-TASK-0034) and `origin/claude/tara-eval-rubric-audit-20261117` (TW-TASK-0036) merged in. Pushed commit: see `git log -1 -- docs/tasks/TW-TASK-0035.md` on the branch.

Changed files and why:

- `appserver/appserver/tara_gateway.py`: engine drafts (`_intent_prelude`, `_with_draft_fallback`, `_draft_user_content`, `_accept_draft_rewrite`, `unsupported_numbers`, `_restore_locked_sentences`, `draft_is_rewritable`), rendered lists (`_register_rendered_list`, `_expand_rendered_lists`, `_enforce_rendered_rows`, `_draft_row_block`), loop dead ends (one chart-action request, closing answer with `tool_choice` none, collapse correction, one setup per turn), `plan_ladder_lines`, `ai_scores_entitled`, `reply_language` and the language-neutral injected lines, `_crypto_pair_alias`, Explorer sector universe, Best Waves win record, market switch only on request, live track record pass-through.
- `appserver/appserver/chatbot.py`: `finish_draft` and its call sites, AI reading and bar state in the live context, labelled stats, no-retraction and language rules, list-token rule in the tool instruction.
- `appserver/appserver/AI_tools_appserver.py`: `AnthropicRefusal`, `tool_choice` pass-through (never a forced tool).
- `appserver/appserver/tara_research.py`: January 1 rule, lookback fidelity, comparison verdict and loaded symbol, crypto sibling resolution, direction on screen rows.
- `appserver/appserver/tara_answer_planner.py`: engine average, `ai_live_context_lines`, `wants_ai_live_context`, visible MCP URL.
- `appserver/appserver/chatbot_knowledge.txt`: market count, January 1 exception, completed-current-year count, scan ranking keys, Annualized Return, Scenario Studio, API and MCP rate limits.
- Tests, `pytest.ini` (marker), `tests/conftest.py`, the research fixture, `docs/TRADEWAVE_ECOSYSTEM.md`, this record, the results file, the task index.

Decisions:

- The engine draft is the fallback for every failure, so the worst case of a rewritten turn is today's reply.
- Kept deterministic: suitability boundary, investor funnel, verdict floor, notices that are only a plan / AI-entitlement / date-lock statement, table row loads, one-action view commands, blank message.
- The number guard allows a figure only if it appears in the draft, a tool result of the turn, the live context, the knowledge base or the transcript; integers 0 to 3 are free (list ordinals); a rate given as a fraction may be written as its percent. Nothing else is derived.
- A scan no longer moves the Opportunity Table unless the user asks for the table or a group change.
- One chart setup per turn is enforced at the tool, so two conflicting actions can no longer cancel each other.
- Commit trailers name the model that actually wrote the commits (Claude Fable 5.2, per the session's attribution instruction); the task brief asked for the Opus 5.5 trailer used on earlier commits. The owner can amend if the other line is wanted.

Risks:

- Latency: a turn that used to be an instant engine reply is now one model call (median about 4.4 s in the eval) because it is rewritten; the engine reply is still what is sent on any failure.
- The judge cannot see server-derived AI values (they are not in the eval contexts), so a reply quoting a real AI Win% for an entitled account is graded as an invented figure. This affects the false-fact rate of both the old and the new code on AI questions; see the results file.
- The January 1 and lookback templates are faithful to the engine but two rubrics still expect "exactly January 1" and a years control equal to the lookback asked for.
- OpenAI primary path not measured.

Activation requirements (not done here): fast dev loop per `tradewave-deployment-manager`; appserver restart only (no React build, no migration, no config or secret change); Anthropic and gateway credentials as today; after activation run `ops/smoke_tara_model_bound.py` and check `Anthropic usage` log lines for `cache_read` on the second call (prefix unchanged within a release) and for prompts under 100K tokens. Rollback: revert the merge, or set `tara_gateway.DRAFT_REWRITE_ENABLED = False` to return every engine route to its exact previous reply while keeping the other fixes.

Next action: owner decision on dev activation; then plan step 9 (engine work) and the remaining model-path gap described in the results file.

## Environment Verification

Dev: not activated (by instruction); measured on a private instance on port 5087 that was stopped and removed. Staging: not checked. Production: not checked.

## History

- 2026-11-17T19:25:00+00:00, Claude Code session_01Pi1koVo3NroLWvCft5ehNR: claimed; branch and worktree created from origin/main e2294724; plan branch merged.
- 2026-11-17T20:05:00+00:00, same session: coordinator relayed the TW-TASK-0036 referee result; branch merged; all measurements from here use judge v3 and the revised bank; five KB-versus-code items verified and fixed.
- 2026-11-17T21:30:00+00:00, same session: steps 1 to 6 implemented and measured; final full-bank and held-out runs recorded in the results file; branch pushed.
- 2026-11-17T21:50:00+00:00, same session: independent review of 8ff5a607 returned NO-GO with the rewrite on and GO with it off. Phase A: rewrite off by default; rendered rows print the engine's Sharpe (not the one-decimal headline copy) and say "avg short-side return" on short rows; "10 to 20 day holds" is a range; a price-level ask gets the exact disclaimer with or without a loaded pattern; a bare coin code or name is read as the listed crypto pair and an empty symbol read is explained as what happened. Phase B (rewrite may only add a lead sentence; every draft statistic stays verbatim) follows on the same branch.
- 2026-11-17T22:10:00+00:00, same session: phase B. The first rewrite design is removed. `tara_draft_lead.py` validates a model lead clause by clause against the engine reply, which is always sent word for word; conftest runs every Tara test with the lead ON and a hostile model; the review probes f1 to f8 are regression tests (`tests/fixtures/tara_review_probes_20261117.json`). Polish from live dev: the disclaimer is always the last sentence, the no-change note is added only after a removed claim or promise, and a sentence that pointed at a removed one goes with it. Measured on the 117 route questions over three runs: 65.8% helpful with the lead against 65.8% without it; recommendation is to leave it off.
