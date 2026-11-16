# TW-TASK-0028: Michael's 20 Tara research questions

- Status: verified on dev
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

Dev: verified on source 61eb1b3db7a553132129216d9a3b8974c8e1d1ec. Staging and production: not changed or tested.

## History

- 2026-11-16T15:03:11.669251+00:00: Codex claimed scoped implementation; self-verification will be identified as such.

## Capability disposition

All 20 source prompts and filled-in cases are in tests/fixtures/tara_research_questions.json. Five KB workflow sections cover screening/ranking (1,2,3,4,9), dates/cycles (6,7,10,11,12,19), evidence (13,14,15,18), moving events (5,8), and actions (16,17,20). Current limits are taught explicitly, not implemented as new capabilities. Calendar writes, personal watchlist retrieval, earnings exclusion, true detrending and event-aligned historical calculations remain separate feature work. The unchanged gateway schema also limits phase reads and ranking completeness; answers must disclose this instead of substituting.

## Live-check correction

First candidate ec7f05e92488d7cd30abcaa441e5bf8f53b06b31 passed generic activation gates. Five authenticated live checks found correct FOMC and personal-watchlist boundaries, but investment guidance intercepted earnings/calendar requests and detrending became an ordinary SPX chart load. Candidate was rolled back to the prior dev pointer before correction. Added early deterministic capability answers for those three operations, before report/investor/view routing, with authenticated endpoint regressions asserting no actions or unrelated shortcut calls. No new market-data capability was added.

Corrected the gateway tool description that called market 1 tech: it is NASDAQ 100, not a verified technology-sector universe. Final focused suite: 370 passed. Second live checks pending.

## Final Verification and Handoff

- Source: 61eb1b3db7a553132129216d9a3b8974c8e1d1ec, pushed task branch codex/tara-michael-questions-20261116 and integration branch codex/tara-michael-integrated-20261116, then non-forced main promotion after live checks. Documentation-only closeout may advance main without another activation; application files remain identical.
- Tests: 371 passed across research questions, prompt context, answer planner, action contract, short explanations and OpenAI canary tests. All 20 original templates plus filled-in examples retrieve their intended workflows. Three authenticated endpoint tests prove earnings/calendar/detrending cannot reach unrelated scan/chart shortcuts. Calendar-day duration requests remain supported. git diff --check passed.
- Live: deterministic activation gate 6/6, model-bound OpenAI gate passed; five authenticated /chatbot/chat checks (FOMC, earnings, personal watchlist, detrended chart, calendar) returned accurate limitations and zero actions. Results: [live evidence](evidence/TW-TASK-0028-live-20261116.json). This is self-verification, not independent review. Full numeric end-to-end evaluation of all 20 questions was not run.
- Active backend: /home/flask/.tw2-releases/61eb1b3db7a553132129216d9a3b8974c8e1d1ec, via /home/flask/.tw2-app-current. Main/source parity verified; worktrees clean. Existing React pointer /home/flask/web-react/releases/build-0c67bb840fa152c8de9e427d8a3e801239caf6f0 unchanged. No UI/assets/build, dependency, migration, engine math, account or production changes.
- Previous backend: /home/tradewave-worktrees/affiliate-gaps-dev-20261116. Final activation's automatic rollback: /root/tradewave-snapshots/tara-parity-dev-20261116T151225Z/rollback.sh. Earlier verification candidates were restored before correction; a second smoke harness rejected the valid wording "ticker symbols" versus "tickers", which was corrected in the harness without changing that model answer.
- Next: owner can try the questions on dev. Separate feature work is needed for actual event-aligned calculations, personal-watchlist retrieval, earnings exclusions, calendar writes and detrended chart creation. The KB update does not claim these capabilities are implemented. Staging/production require separate authorization.

- 2026-11-16T15:13:23.280918+00:00: Codex completed dev activation, live verification, main parity and lock release; shared documentation/evidence closeout.
