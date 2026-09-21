# TW-BUG-0011: SMN review homepage hides retained prior articles

- Status: in-progress
- Confidence: reproduced
- Priority: P2 - readers cannot discover prior editions from the home page.
- First observed / last updated: 2026-09-21T14:26:36.979857+00:00
- Executor/session/claim time: Codex smn-home-archive-20260921 / 2026-09-21T14:26:36.979857+00:00
- Authorization: owner requests cumulative production-style homepage on existing Dev. Production read-only; preserve article bodies, charts, studies and existing URLs.

## User Impact and Reproduction
At SMN main/live 6557b93bf98dc4cf7c13e59e256a3b0897a80dec, open the Dev root after a daily edition is published. Nginx redirects to that date's six-card index. Earlier edition files remain but disappear from homepage discovery. Expected: production's news template with cumulative newest-first coverage and access to older articles, growing after each daily publication.

## Evidence and Investigation
Confirmed in blog/install_smn_recovery_edition.py::prepare: copytree preserves prior web files, but nginx home redirect is moved to the latest date. Only package article files are copied; no cumulative catalog is maintained. subscription_live.cjs expects this limited six-card landing, so it does not exercise cumulative browsing. Production uses the wire layout in blog/rebuild_news_home.py. Initial recovery intentionally lacked a full homepage; that constraint should not persist in the review workflow.

## Acceptance and Regression Checks
Retained Dev articles appear in a cumulative production-style homepage, newest first, with working older-article discovery. Subsequent publication merges catalog entries without duplicating or losing old editions. Dated edition/article URLs and existing article bytes remain intact. Browser checks cover desktop/mobile, older article navigation and accumulation; tests exercise sequential publication and repeat. No new model generation or TradeWave calculation is needed.

## Implementation and Handoff
SMN branch codex/smn-home-archive-20260921; local clean worktree smn-home-archive-20260921, base 6557b93bf98dc4cf7c13e59e256a3b0897a80dec. Implementation/tests/deployment pending. Related workflow TW-TASK-0005. Short Dev lock and pointer rollback, no production changes.

## Environment Verification
Dev: reproduced; repair pending. Staging: not checked. Production: read-only template reference, unchanged.

## History
- 2026-09-21T14:26:36.979857+00:00: Owner report reproduced and repair claimed. Next: reuse production template, recover retained catalog, implement cumulative install, test and activate Dev.
