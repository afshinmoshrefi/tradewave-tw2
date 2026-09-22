# TW-BUG-0012: AI Future-Entry Message Incorrectly Blames Time Length

- Status: in-progress
- Confidence: reproduced
- Priority: P3, misleading explanation; expected score timing gate is working
- First observed / last updated: 2026-09-22T14:48:05.102725+00:00
- Executor/session: Codex, klac-ai-score-investigation-20260922
- Authorization: investigate missing score and record findings only; no application repair or deployment

## User Impact and Reproduction

On dev in the user's existing Chrome tab, open https://tw2-dev.trxstat.com/app/?o=MXxLTEFDfDIwMjYtMTAtMDF8MTk3fHBlMi02 . The viewer is KLAC, NASDAQ 100 resource 1, October 1, 2026 through April 15, 2027, 197 inclusive calendar days, six PE+2 years, long. On September 22 the AI panel says "No AI reading is available for this time length" and "This score will appear closer to the pattern start date." All 30/60/90-day checkpoints say "Not available yet."

Expected: explain the future-entry timing restriction directly. Actual: headline implies an unsupported duration while the detail correctly identifies timing. Missing scores themselves are expected on this date, not evidence of a scorer outage.

## Evidence and Investigation

Active backend source: 05ae209ecaba231e5816f835dc133f7c0cdf00e8, /home/flask/.tw2-app-current resolves to /home/tradewave-worktrees/tw2-20260915-01. tradewave-appserver is active and its WorkingDirectory follows that pointer. Browser was inspected without changing selection or reloading.

- appserver/appserver/appserver.py:1867-1868 sets five days and America/New_York timezone.
- _ml_entry_date_state at line 1930 returns too_far_ahead when entry is more than five calendar days away. MLScoreBatch at line 2657 and MLScorePending at line 2854 enforce it before scoring.
- web-react/src/components/opportunityAIScores.js maps too_far_ahead to the observed detail text.
- web-react/src/components/AIScorePanel.js falls through to the generic time-length headline for this reason.
- 197 days is supported with bounded 30/60/90-day AI checkpoints, not a complete 197-day model forecast. The timing gate applies regardless of this duration or the selected PE cohort.

September 26, New York date, is the first eligible date for an October 1 entry. Eligibility does not guarantee provider/data availability. No live API payload was captured and scorer health was not tested; neither is needed to explain the observed reason text.

## Acceptance and Regression Checks

Executed the exact active-source _ml_entry_date_state function extracted through Python AST, with its declared constant and timezone, without importing or modifying the live Flask application. For October 1 entry: September 22 and 25 returned too_far_ahead; September 26 and October 1 returned None (eligible); October 2 returned after_entry. Browser observation confirms the matching future-entry copy.

Future repair should give too_early/too_far_ahead a timing-specific headline, preferably with the first eligible date. Preserve the five-day rule and long-wave checkpoint semantics. Verify separate duration, recurrence, provider-failure and after-entry messages remain accurate. No application tests/build/deploy run because no application change was authorized or made.

## Implementation and Handoff

Repository: afshinmoshrefi/tradewave-tw2. Branch: codex/klac-ai-score-investigation-20260922. Worktree: /home/tradewave-worktrees/klac-ai-score-investigation-20260922, based on 428be7bb (current main at start). Documentation-only record and bug-index update. Exact record commit: git log -1 -- docs/bugs/TW-BUG-0012.md. No runtime/configuration/dependency changes, rollback or activation required. Next action: if wording repair is authorized, claim this record and implement the focused AI panel message correction. Do not change the scoring window to address this report.

## Environment Verification

Dev: observed UI and checked active-source gate on 2026-09-22T14:48:05.102725+00:00; no deployment by this task. Staging and production: not checked.

## History

- 2026-09-22T14:48:05.102725+00:00: Codex confirmed expected future-entry suppression and recorded separate misleading headline defect. Application remains unchanged.

- 2026-09-22T14:49:52.000231+00:00: Owner authorized clear user-facing explanations of historical/current inputs and future/past score availability. Codex claims implementation on codex/klac-ai-score-investigation-20260922 in the same clean worktree; scope is UI wording, focused checks and dev activation. Scoring rules stay unchanged.
