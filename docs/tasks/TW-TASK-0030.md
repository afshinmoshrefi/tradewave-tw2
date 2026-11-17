# TW-TASK-0030: Five failed Tara research questions

- Status: fixed on branch, awaiting dev integration and activation
- Confidence: reproduced
- Priority: P1 - the owner asked five ordinary research questions on dev and every answer was wrong, thin or off-topic
- First observed / last updated: 2026-11-16T19:26:29+00:00 / 2026-11-17T12:40:00+00:00
- Executor/session/claim time: Claude Code session_01Pi1koVo3NroLWvCft5ehNR (subagent), 2026-11-17T11:30:00+00:00
- Authorization: Afshin asked for the failures to be fixed. Scope: code, tests and records on a task branch. Dev activation, pointer changes, service restarts and main are the orchestrator's; staging and production excluded.

## Goal, Scope and Acceptance

Owner turns on dev, 2026-11-16 19:26-19:36 UTC (`/var/log/tradewave/tara_questions.log.1`):

1. "find s&p500 stocks entering seasonaly bearish patterns htis week" (and retyped) - a "list" of one name, entry dated on a Sunday.
2. "which S&P500 stocks have the highest seasonal win rate over the next 10 days" - two names ranked by Sharpe and "The dataset did not return win-rate figures".
3. "analyze apple historic return from now to year end over the last 20 years" - one line, no dates; the queued chart was 11 PE+0 years while the text said 20 years.
4. "compare the seasonal performance of technology and utilities ETFs for the 4th quarter" (and with "XLK and XLF") - one symbol only, no comparison.
5. "what's the latest date that the 100 year pattern has bottomed" - reloaded the pattern and recited its summary.

Acceptance: each class (any index, direction, window, hold length, list size, 2 to 4 symbols, the 100-Year Pattern or the loaded pattern) is answered from engine values with a real ranked list, the win record with n, the dates, both sides of a comparison, and real low dates. No statistic is computed in the chatbot.

## Evidence and Investigation

Baseline origin/main 589df95308eaef8d3e1da1982aa75bf11ed771c4.

- Classes 1 and 2: `tara_gateway._investor_screen_result` and `_opplist4_rows` read ONE OppList4 table (today, the React default 12-of-12 band) and `_rows_to_scan_cards` carries no win record; the model tool path used gateway `/v1/scan`, whose window is applied after fetching OppList4 only at the window's first date (`apiserver/routes.py` `_resolve_window` / `opportunities_multi`). Live probe: the S&P 500 week of Nov 16 holds 91 short patterns at the 10-year band floor (8 winners), one at 12-of-12 for a single day.
- Classes 3 and 4: `tara_gateway._ensure_load_named` replaces any model reply whose win/average/Sharpe numbers differ from the ONE loaded setup's headline with `_announce_line`, so a multi-statistic study or a two-symbol comparison collapsed to "<b>XLK</b> long based on the last 20 years: ...". The gateway already had `/v1/compare`, but Tara had no route to it.
- Class 5: `build_hundred_year_pattern_command` answers every message that names the pattern; the engine computed each year's low (MAE) but did not return its date.

## Acceptance and Regression Checks

- New `tests/test_tara_research_engine_answers.py`: 69 tests replaying engine responses recorded on 2026-11-17 (`tests/fixtures/tara_research_engine_20261117.json`, no prices, no user data). Covers the five owner questions through `/chatbot/chat`, generalized variants (other indexes, directions, windows, hold lengths, filters, forex pairs, loaded-pattern comparisons, PE cycles), real phrasings from the production Tara log (question text only), plan boundaries, engine outage fall-through, and neighbor questions that must stay on their existing paths.
- Existing Tara suites unchanged and passing (see Final Verification).
- Engine: with `excursion_dates` absent, `ChartData4` responses from the worktree engine are byte-identical to the active dev engine for four studies; with it, `pct` rows and `stats` are identical and only the four date fields are added.

## Implementation and Handoff

Repository afshinmoshrefi/tradewave-tw2; branch `claude/tara-failed-questions-20261117`; worktree `/home/tradewave-worktrees/tara-failed-questions-20261117`. Source SHA: see the pushed branch head (recorded in the handoff message).

Changed files:
- `appserver/appserver/tara_research.py` (new): `build_research_command` and the five builders.
- `appserver/appserver/chatbot.py`: calls it after the loaded-pattern suitability boundary, before every other shortcut.
- `appserver/appserver/appserver.py`: `ChartData4` opt-in `excursion_dates=1` (adds `entry_trade_date`, `exit_trade_date`, `high_date`, `low_date` per year; own redis key suffix).
- `ops/activate_tara_release.sh`: adds the new module to the prior-source snapshot list.
- `docs/TRADEWAVE_ECOSYSTEM.md` section 7C, this record, the register row, tests, fixture, evidence.

No `chatbot_knowledge.txt` edit (TW-TASK-0029 owns that file). No migration, dependency, React build or apiserver/mcpserver change. Activation needs the normal backend pointer switch with an appserver restart (the engine route changed, so a prompt-only reload is not enough). Rollback: previous pointer.

Decisions: default lookback 10 years and list size 10; the detector is read at the market band floor; "next N days" means windows that START in the next N days and the reply says so; a weekend-dated pattern is shown on its first session with its calendar start; a comparison uses the lookback all symbols share; suitability intents keep their funnel.

Not changed, for a follow-up: gateway `/v1/scan` still screens only the first date of a window (affects MCP/API `find_best_opportunities` windows and Tara's remaining model-tool scans); `_ensure_load_named` still collapses multi-symbol model replies outside these classes; sector-within-index screens still need sector tags.

## Environment Verification

Dev: not activated. Verified locally on 2026-11-17 against real dev engine data by running the worktree appserver privately on 127.0.0.1:5077 with a synthetic Strategist-level identity: [answers](evidence/TW-TASK-0030-local-20261117.json). Staging and production: not changed or tested.

## History

- 2026-11-17T11:30:00+00:00: Claude claimed the task, reproduced from the audit log and traced root causes.
- 2026-11-17T12:40:00+00:00: Fix, tests and records pushed on the task branch for orchestrator integration. Self-verification, not independent review.
