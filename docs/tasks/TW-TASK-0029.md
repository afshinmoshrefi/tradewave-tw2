# TW-TASK-0029: Tara knowledge base cleanup (contradictions, stale UI facts, research-workflow tone)

- Status: fixed on branch, not activated
- Confidence: verified against source
- Priority: P2 - wrong or contradictory product facts in Tara answers
- First observed / last updated: 2026-11-17T11:46:52+00:00
- Executor/session/claim time: Claude (subagent of session_01Pi1koVo3NroLWvCft5ehNR), 2026-11-17T11:46:52+00:00
- Authorization: Afshin approved the "option A" fix list for `appserver/appserver/chatbot_knowledge.txt`. KB text only. No prices changed. No dev activation, no push to main; the orchestrator integrates and activates. Staging and production excluded.

## Goal, Scope and Acceptance

Remove contradictions and stale UI facts from the Tara knowledge base, make "Tara acts herself" versus "click path" consistent, correct dead account links, drop internal engineering detail, and review the "Research Requests" sections added by TW-TASK-0028 for wrong capability claims and refusal-first tone. Every changed UI fact must be verified in React or server source. Section headings used by `tara_prompt_context.py` routing must keep working.

## Evidence and Investigation

Baseline origin/main 589df95308eaef8d3e1da1982aa75bf11ed771c4. Facts verified in source:

- Settings gear, Watchlist icon, Tooltips switch and Securities Group dropdown all live in the header bar at the top of the left panel (`web-react/src/components/DesktopLayout.js:852-930`). Theme is Settings > General > Appearance (`DesktopLayout.js:993-1030`); the old header theme toggle handler is unused.
- Two separate Years controls: Opportunity Table (`OppTable.js:2193`, `App.js:1540-1576`) and bar chart toolbar (`SeasonalBarChart.js:3445`, `2062-2079`); a row click copies the table value to the viewer (`OppTable.js:747,1531`). Viewer range is 5 (3 in PE mode) up to available history (`SeasonalBarChart.js:663-687`); the product's own guide says 5 to 98 (`HelpPanelPopup.js`, `YearsRangePopup.js:124-134`). Plan caps 10/15 (`config.py:400-404`).
- Median is over all years (`TradeDetail.js:95` tooltip, `appserver.py:4313`).
- Exclude Current Range and Buy & Hold are Analysis-menu actions, not Date presets (`Common.js:523-561`).
- No weekend shift on a typed start date (`SeasonalBarChart.js:1602-1640`). Sat/Sun/Mon consolidation is in the opportunity list (`appserver.py:1213-1226`); Sat/Sun to Monday is calendar reminders only (`googleCalendarEvents.js:52-60`).
- Explorer has 0 watchlists (`config.py:376-392`, `TIER_FEATURES`).
- Filter grammar (`opportunityFilters.js:36-62`): avgp/sr/twa/twr/tl take `>`; price and ais/win/predr/pmfe take `>` or `<`; bare ticker text.
- `/account` and `/account/manage-subscription` (Stripe customer portal) in `web/app.py:2108,3571`, `web/templates/account.html`; sign-in is WorkOS AuthKit hosted (`web/app.py:633-655`).
- TWA/TWR columns need the `show_sr2` entitlement, granted to the two highest levels (`appserver.py:697,778-780`, `opportunityAIScores.js:139`). Win% column is `win_prob`, "AI chance of profit" (`DesktopLayout.js:1527-1541`).
- Help icon opens Help and Guides, not a video table (`HelpPanelPopup.js`). Remind me button (`SeasonalBarChart.js:3295-3330`).
- Markets: Russell 1000 exists, Korea removed (`config.py:504-522`, `tara_gateway.py:381`).
- Tara action set: `update_view` fields and read tools (`tara_gateway.py:64-180,376-387`); scan entry dates are current-year only (`apiserver/appserver_client.py:436-446`); read tools accept `pe` = current cycle only (`apiserver/routes.py`).

## Acceptance and Regression Checks

441 passed: `tests/test_tara_*.py` (includes research questions, prompt context, answer planner, action contract, short explanations). `git diff --check` clean. No test changes were needed. Not run: live model answers on dev (not activated by this task).

## Implementation and Handoff

Branch `claude/tara-kb-cleanup-20261117`, worktree `/home/tradewave-worktrees/tara-kb-cleanup-20261117`. One application file changed: `appserver/appserver/chatbot_knowledge.txt`. Backend-only, loaded at appserver start; no frontend build, dependencies or migrations. Rollback is reverting the commit.

Heading changes: "Interactive Info Popups (Sharpe Ratio and Trend Score)" was merged into the single "Interactive Info Popups"; its two non-popup paragraphs moved to a new "Seasonality Value and Strategy Questions"; "Help Icon (Video Tutorials)" became "Help Icon (Help and Guides)". None of these were named in `_TOPIC_ROUTES`, tests or fixtures. All other headings are unchanged.

## Open items for other owners

- Routing (not edited here, owned by the parallel routing task): "create a watch list" (two words) selects no section; "why did my chart change" and "how do I cancel my subscription" fall to weak lexical matches. The KB text is correct once the section is selected.
- `tara_prompt_context.research_capability_reply` and `tara_answer_planner` still hard-code "Portfolio Manager's notification icon" for calendar requests; the Remind me button is the shorter path and is now in the KB.
- `chatbot.py` system prompt still lists "slide/tab switch" as having no driving action, although `update_view.bottom_slide` exists.
- Could not verify from source whether the hosted sign-in page offers a password reset link, so the KB only says passwords are managed on the sign-in page and points to help@tradewave.ai.
- Production-log triage reported a user who could not add the TWR column. Source shows TWA/TWR require the top-plan entitlement, which the KB now states; whether that user was entitled was not investigated.

## Environment Verification

Dev: not activated. Staging and production: not changed or tested.

## History

- 2026-11-17T11:46:52+00:00: Claude claimed and completed the KB edit on the task branch; self-verified by source reading and focused tests, not independently reviewed.
