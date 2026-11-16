# TW-TASK-0028: Michael's 20 Tara research questions

- Status: in-progress
- Confidence: reproduced
- Priority: P2 - missing and incorrect knowledge retrieval
- First observed / last updated: 2026-11-16T15:03:11.669251+00:00
- Executor/session/claim time: Codex 01a1e032-bf72-7df1-878c-2da3cc7d7d6b, 2026-11-16T15:03:11.669251+00:00
- Authorization: Afshin approved implementing the knowledge/routing update and verifying it on TW2 dev. Missing capabilities must be stated accurately; no new calendar, event-data, personal-watchlist or earnings integrations. Staging and production excluded.

## Goal, Scope and Acceptance

Include all 20 prompts from Michael's November 10, 2026 Tara questions email as grounded research workflows. Route literal templates and realistic filled-in questions to the relevant small KB sections. Preserve ordinary definitions and named-pattern routing. Do not invent financial results, change requested universes/rankings/cycles, or claim unsupported UI actions. Verify focused routing regressions and representative live model answers on dev.

## Evidence and Investigation

Baseline origin/main 2958c0e065a8e30afae4be453c7866f034768107. Dev hostname tw2-dev.trxstat.com maps to 192.168.1.176. Runtime follows /home/flask/.tw2-app-current, not the shared source checkout. Active selector returns no section for retail Black Friday, earnings exclusion and calendar prompts, and the unrelated 100-Year Pattern for gold/FOMC. Source KB is loaded at process startup. Existing TW-TASK-0013 covers UI knowledge; TW-TASK-0019 covers published lists, not personal watchlist retrieval.

## Acceptance and Regression Checks

Passed: 73 research-question/prompt-context tests (all 20 templates and 20 concrete examples, neighboring definitions, context caps, failed-year evidence) and 289 existing planner/action-contract/short-answer/OpenAI routing tests. git diff --check passed. Authenticated live checks pending. No engine math changes.

## Implementation and Handoff

Repository afshinmoshrefi/tradewave-tw2; branch codex/tara-michael-questions-20261116; worktree /home/tradewave-worktrees/tara-michael-questions-20261116. Source SHA pending. Backend-only, no frontend build/dependencies/migrations. Preserve existing active source and frontend pointers; use documented Tara activation with rollback. Next: add workflows/routing/tests, push candidate, live-verify under dev lock and advance main non-forced.

## Environment Verification

Dev: not deployed by this task yet. Staging and production: not changed or tested.

## History

- 2026-11-16T15:03:11.669251+00:00: Codex claimed scoped implementation; self-verification will be identified as such.

## Capability disposition

All 20 source prompts and filled-in cases are in tests/fixtures/tara_research_questions.json. Five KB workflow sections cover screening/ranking (1,2,3,4,9), dates/cycles (6,7,10,11,12,19), evidence (13,14,15,18), moving events (5,8), and actions (16,17,20). Current limits are taught explicitly, not implemented as new capabilities. Calendar writes, personal watchlist retrieval, earnings exclusion, true detrending and event-aligned historical calculations remain separate feature work. The unchanged gateway schema also limits phase reads and ranking completeness; answers must disclose this instead of substituting.

## Live-check correction

First candidate ec7f05e92488d7cd30abcaa441e5bf8f53b06b31 passed generic activation gates. Five authenticated live checks found correct FOMC and personal-watchlist boundaries, but investment guidance intercepted earnings/calendar requests and detrending became an ordinary SPX chart load. Candidate was rolled back to the prior dev pointer before correction. Added early deterministic capability answers for those three operations, before report/investor/view routing, with authenticated endpoint regressions asserting no actions or unrelated shortcut calls. No new market-data capability was added.

Corrected the gateway tool description that called market 1 tech: it is NASDAQ 100, not a verified technology-sector universe. Final focused suite: 370 passed. Second live checks pending.
