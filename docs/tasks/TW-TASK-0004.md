# TW-TASK-0004: Michael editorial refinements and September 17 SMN Dev edition

- Status: verified
- Confidence: reproduced
- Priority: P2, reader clarity while preserving TradeWave studies
- First observed / claim: 2026-09-17T14:57:24.123579+00:00
- Last updated: 2026-09-17T15:31:45.224510+00:00
- Executor/session: Codex / smn-michael-editorial-20260917; implementation and runtime verification by this session, separate subscription-model editorial review jobs.
- Authorization: Michael's suggested edits and today's six production subjects recreated on Dev only. No production writes, schedulers, paid API fallback or mathematics changes.

## Goal, Scope and Outcome
Applied the tracked suggestions and opening note in [Recommended Edits](https://docs.google.com/document/d/1t5-yE-L3UApiC1urZF-TOM-tpLLvymG3tWh2P4QH7dE/edit). Document comments were empty. Natural openings and takeaways, plainer comparisons and risk/short-side explanations, completed sample dates, readable chart notes, and a specific TradeWave invitation are now generator/reviewer rules. Preserved SMN structure, production heroes, exact studies, native responsive charts and the owner-approved normalized trend overlay. Added no second calculation engine.

The [September 17 Dev edition](https://smn-dev.trxstat.com/editions/2026-09-17/) contains MO, COO, LEN, OMC, JNJ and DJI, each with a production comparison link. Original dates, duration, PE lookback, direction, observations and engine results match production. Consecutive-year comparisons are separately supplied TradeWave responses, never substituted for the article study. All 60-weekday projections come unchanged from TradeWave compute_projection.

## Source, Data and Implementation
SMN repo: https://github.com/afshinmoshrefi/SMN. Base main b2d82a979566c0e236503913c862ae54fa4ca1a6. Final main/live generator: `1d366e70a3e6e01b58212a5a841814e013a21ac2`. Task branch `codex/smn-michael-editorial-20260917`; clean integration branch `codex/smn-michael-integrated-20260917`. Both local worktrees are under `C:/Users/afshin/Documents/TradeWave Main Orchestrator`. All task source commits were pushed; final main advanced non-forced only after live verification.

Changed `blog/seasonal_edition.py` (writer/reviewer rules, useful CTA), `engine_seasonal.py` (plain captions and index label, no values changed), `engine_edition_workflow.py` (every source in a multi-source chart gets a word allowance), `chartkit.py` (mobile axis-label alignment/spacing), focused caption tests and `SUBSCRIPTION_DEV_PUBLICATION.md`. Mobile chart changes preserve engine-card and both CSV hashes for every subject.

Read-only capture retained today's production inputs and exact engine outputs. Fresh commissions use company releases/calendars and Fed statements; no old production copy supplied to writers. Official Codex CLI used saved ChatGPT authentication, Astra xhigh, no API fallback. Reused production illustrations. Six original writing jobs, six initial review jobs and three targeted copy-edit reviews retained as immutable receipts. MO opening/headline improved; LEN delivery guidance quantified; JNJ's initial review correctly held publication until explicit sales/EPS guidance benchmarks were added and a new review passed.

## Acceptance and Evidence
Portable [verification receipt](evidence/TW-TASK-0004-20260917.json) includes exact original study identities/cohorts, Dev/production links, source budgets, hashes, model receipts, engine provenance and rollback pointers.

- Focused pytest: **48 passed, 11 subtests passed**. Initial collection failed because the local test path was missing; corrected PYTHONPATH, then passed. No broad staging suite run.
- All six final mechanical/source-budget checks and seven-check editorial reviews pass, no major/blocker issues. Separate model review does not imply an independent human review.
- Chrome/Playwright: all 12 live desktop/mobile article layouts; correct study links, exact cohort rows, chart placement, loaded images, responsive assets, expandable data/comparisons, no horizontal overflow and Dev noindex. 121 public files match hashes; 16 committed source files match the active release.
- Direct pixel review of final article/chart captures for every subject and both live landing layouts. Prior September 8 edition remains available; previous September 10 release retained.
- Two minor DJI suggestions retained as nonblocking: smoother second opening sentence; unsigned positive rate-level labels. Captions explicitly identify target-rate upper bounds.

## Environment, Release and Recovery
**Dev verified** on the already active `.176` SMN recovery vhost; this task did not restore primary `.180`. Home points to the September 17 edition. Versioned source and web pointers match final SMN main. Dev lock released after checks and main parity. TradeWave app services/queues untouched.

Release record: `20260917-1d366e70a3` under `/var/lib/tradewave/release-state/`. Active web `/var/www/smn-dev-recovery/20260917-1d366e70a3`; active source `/var/lib/tradewave/smn-editorial/releases/1d366e70a3e6e01b58212a5a841814e013a21ac2`. Previous web `/var/www/smn-dev-recovery/20260910-b2d82a9795`; previous source `/var/lib/tradewave/smn-editorial/releases/b2d82a979566c0e236503913c862ae54fa4ca1a6`. Nginx before/after bytes and prior pointers are retained in the release record. Activation had automatic rollback on failed live checks or a failed non-forced main advance. For a later rollback, acquire a new Dev mutation claim/lock and restore both recorded previous pointers and nginx-before with nginx test/reload; do not call the completed release's locked rollback routine without a new controlled ownership window.

**Staging:** not deployed by this task; full qualification not run. **Production:** read-only inputs, not deployed or changed. No cron, daily subscription automation, email/distribution or paid API enabled.

## Durable Handoff and Next Action
Private portable audit on `tradewave-vm`: `/var/lib/tradewave/smn-editorial/audits/20260917/editorial-audit.tar.gz`, hash in linked evidence. SSH/sudo access required; outside public nginx root. Includes retained production datasets/payloads, source commissions, engine export, job prompts/schemas/outputs/receipts and final review/layout bindings. Excludes authentication material and usage-account snapshots. Publication/source archives and operations also retained at `/var/tmp/smn-michael-edition-1d366e70-20260917`; active release directories are durable runtime copies.

Local complete audit: `smn-review-20260917/engine-editorial`. Use committed `blog/engine_edition_workflow.py` and `SUBSCRIPTION_DEV_PUBLICATION.md` for the next edition. Preserve immutable job IDs and full engine study identity. Future editions require fresh production selection/data/source packets and new dated jobs; never silently reuse this edition's news or studies. No authorized implementation remains for this request. Next product action: Afshin compares the six Dev articles with production; any production promotion requires its own request and release process.

## History
- 2026-09-17T14:57:24.123579+00:00: Claim pushed before application edits, shared commit e2e99ef757a4d5baa7e4385841989e1645106d17.
- 2026-09-17T15:31:45.224510+00:00: All six recreated, reviewed and verified on Dev; final source main parity, lock released, portable handoff recorded.
