# TW-TASK-0031: Tara failure classes from real production conversations

- Status: fixed on branch, awaiting dev integration and activation
- Confidence: reproduced
- Priority: P1 - eleven failure classes found in real customer conversations, including two broken suggested prompts
- First observed / last updated: 2026-11-17T11:00:00+00:00 / 2026-11-17T12:50:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T12:05:00+00:00
- Authorization: Afshin asked for every still-broken class in the production triage to be fixed. Scope: code, tests and records on a task branch. Dev activation, pointer changes, service restarts and main are the orchestrator's; staging and production excluded.

## Goal, Scope and Acceptance

A triage of 186 production Tara turns (2026-05-19 to 2026-11-14) left eleven classes still broken on dev. The triage file and the conversation log hold customer data and stay on the dev box; only question wording is used here.

1. "Show me ..." asks that are not chart commands ("Show me my usage so far and which plan actually fits", "show my Z probability for next 3 months") returned "I couldn't send the complete chart action".
2. AI-score ranking and filtering (AIS, AI Win%, PredR) was unavailable in Tara's scans, and a "predicted profit of minimum 5%" ask was answered with the historical average return.
3. Any message containing "should I" or "recent" was replaced by a ~250-word canned block starting "I can evaluate the evidence, but I can't decide whether you should take the trade."
4. "Which tech stocks tend to rise this time of year?" returned an S&P 500 list with the word "tech" ignored.
5. ROKU could not be analyzed; XAU and gold requests returned corn and NASDAQ futures.
6. "show me 100 year pattern" returned "I could not find ME".
7. UI how-to answers: "create a watch list" only opened the guide; chart-changed and cancel questions had no knowledge route. Added by the coordinator during the task: "what is median gain?" was defined as the middle of the gains only.
8. The deterministic stock screen carried a fixed ~70-word disclaimer and showed win counts only sometimes.
9. "min 5 of 7 years" screens returned nothing with the engine's "outside the detection range" wording.
10. Tara's own "next check" suggestions could not be run, and "TradeWave does not provide earnings-date data" contradicted her own analysis.
11. "When is SPX historically weak?" after the 100-Year Pattern dead-ended on "24 PE+2 samples".

Also: the calendar boundary named the Portfolio Manager notification icon instead of the Remind me button, and the prompt said there was no action for switching the lower viewer.

Acceptance: each class is fixed as a class (generalized variants, not the literal string), every number still comes from the TradeWave engine, plan limits are unchanged, boundaries are short and last, and the behaviours the triage marked "worth preserving" keep working.

## Evidence and Investigation

Base: `origin/claude/tara-integrated-20261117` (e11aecf2), which already holds TW-TASK-0029 and TW-TASK-0030.

1. `tara_gateway._DIRECT_VIEW_REQUEST_RE` accepted any word after show/open as a symbol ("my", "settings"), so the turn became a chart intent and the final guard discarded the model's answer.
2. `find_best_opportunities` had no ranking key or AI fields, `_BRIEF_DROP` removed each card's `ml` block, and `_mini` (the size-cap fallback) dropped everything else. The gateway `/v1/scan` already supports `rank_by=ml` and returns the engine's AI values.
3. `tara_answer_planner._ADVICE_PATTERNS` matched bare "should i", "would you" and "recommend"; `_RECENCY_PATTERNS` matched bare "recent" and "latest".
4. `classify_investor_intent` returns `seasonal_stock`; the research screen needs a named index, so the turn fell to the fixed market-2 screen.
5. ROKU: the engine detector lists no qualifying pattern at any lookback, `/v1/analyze` answers 404 with a useful message, and `_get` reduced it to "gateway 404". XAU: the bare code resolves to an index and a Toronto stock; spot gold is XAUUSD in Forex. `/v1/securities/<symbol>/patterns` covers five markets only and rejects ETFs and Forex All.
6. `_question_symbol`'s `show(?:\s+me)?\s+(token)` backtracks to capture "me".
7. `chatbot.py` told the model to open the watchlist guide and "never paste the full step list", and listed "slide/tab switch" as a gap although `bottom_slide` exists. The KB route was `\bwatchlist\b` (one word).
8. Fixed footer in `_investor_screen_response`; opportunity-table rows carry no win record.
9. Gateway `lookback_note` ("outside the detection band") reached the user; `apiserver/market_bands.json` holds each market's floor.
10. `_analysis_compact_next_check_line` and `_analysis_next_check_line` suggested studies no tool can run.
11. `build_best_waves_command` used the loaded view's lookback with no fallback. Live probe: SPX has no Short Best Wave at 24 PE+2, 10, 15 or 20 years; it has 15 at 5 years.

## Acceptance and Regression Checks

- New `tests/test_tara_prod_failures.py`: 170 tests, one section per class, with the production phrasings and generalized variants, the neighbours that must keep working (real tickers, explicit loads, real advice asks, record-recency questions, named indexes, pinned windows, in-band screens), and `/chatbot/chat` route tests for the deterministic classes.
- Updated assertions in `tests/test_tara_answer_planner.py` and `tests/test_tara_action_contract.py` for the intentionally changed wording (next checks, advice reply, screen footer, Best Waves empty result, calendar boundary).
- Results: see Final Verification in History.

## Implementation and Handoff

Repository afshinmoshrefi/tradewave-tw2; branch `claude/tara-prod-failures-20261117`; worktree `/home/tradewave-worktrees/tara-prod-failures-20261117`. Source SHA: the pushed branch head (recorded in the handoff message).

Changed files:
- `appserver/appserver/tara_gateway.py`: ticker plausibility and soft view-request acceptance (1, 6); AI scan fields and ranking, result notices that survive trimming (2); analyze recoveries, metal aliases, pattern-list fallback, gateway error detail (5); band-floor rerun (9); turn notes; `build_sector_screen_command` (4); win records and one-line footer (8); Best Waves fallback (11); evidence-first suitability boundary (3).
- `appserver/appserver/tara_answer_planner.py`: `_is_trade_advice_request`, short advice reply, exit-timing reply, recency narrowing (3); runnable next checks and the earnings-split reply (10); watchlist steps and Median Gain definition (7).
- `appserver/appserver/tara_prompt_context.py`: KB routes for watch list, chart-changed, billing/cancel, median (7); calendar boundary points to Remind me.
- `appserver/appserver/chatbot.py`: calls `build_sector_screen_command` after the Best Waves block (the `build_research_command` block is untouched); prompt no longer denies the lower-viewer action, gives watchlist steps, and labels sector proxies.
- `docs/TRADEWAVE_ECOSYSTEM.md` section 7C, this record, the register row, tests, evidence.

Not edited: `tara_research.py` (under review by its author; `build_screen_command` and `_band_floor` are called, not changed), `chatbot_knowledge.txt`, `apiserver`, `mcpserver`, React. No migration or dependency. Activation needs the normal backend pointer switch with an appserver restart; the sector screen and the band floor also need `tara_research.py` from TW-TASK-0030 in the same release. Rollback: previous pointer.

Decisions to confirm:
- A symbol with no detected pattern is answered with the plain 30-day window from today, labelled as not a detected pattern. 30 days is a presentation default, not a statistic.
- A bare XAU/XAG/XPT/XPD means the spot pair unless the named market lists the bare code (the XAU index in market 5).
- The Best Waves fallback ends at a 5-year list, labelled as a small sample.
- A turn note is English even when the reply is in another language; it appears only when the model left the substitution out.

Not fixed here:
- "show my usage": Tara still cannot see account usage. She now says so and gives the plan fit from the KB; real usage needs an account-data tool.
- A projection track record does not exist in TradeWave; Tara now says so instead of a canned block.
- Sector-within-index screens still need sector tags in the data.
- The research screen (TW-TASK-0030) reports a below-floor "N of 10" request at the detector's band without saying the request was below it; that file was out of scope.
- Possible product bug from the triage (clicking TWR in the column chooser does not add it) was not investigated.

## Environment Verification

Dev: not activated. Verified locally on 2026-11-17 against real dev engine data with a private appserver started from the worktree on 127.0.0.1:5078 (own port, no control socket, live service untouched) and a synthetic Strategist-level identity `claude-tara-task-0031-test-*`: [before and after answers](evidence/TW-TASK-0031-local-20261117.json). Staging and production: not changed or tested.

## History

- 2026-11-17T12:05:00+00:00: Claude claimed the task, replayed the 23 triage questions on the base branch and traced root causes.
- 2026-11-17T12:50:00+00:00: Fix, tests and records pushed on the task branch for orchestrator integration. Final Verification: `tests/test_tara_*.py` 681 passed; `pytest -m "not db"` 1943 passed, 5 skipped; `git diff --check` clean. Self-verification, not independent review.
- 2026-11-17T13:05:00+00:00: Merged origin/main 59615573 (TW-TASK-0030 final `tara_research.py`, live on dev). README conflict resolved keeping all rows. The sector screen now passes the plan's `years_cap` to `build_screen_command`. Added route tests proving the five TW-TASK-0030 owner questions still reach `build_research_command`; all five were also re-asked on the private instance and answered by the research route. `tests/test_tara_*.py` 844 passed; `pytest -m "not db"` rerun on the merged code (result in the handoff message); `git diff --check` clean.
