# TW-TASK-0019: Published US security lists and Tara selection

- Status: in-progress
- Confidence: reproduced
- Priority: P2 - requested list discovery and viewer control
- First observed / last updated: 2026-10-04 UTC
- Executor/session/claim time: Codex, tara-published-security-lists-20261004, 2026-10-04 UTC
- Authorization: Copy four owner-requested published lists to dev; implement and verify Tara discovery, selection and manual instructions on dev.

## Goal, Scope and Acceptance

Dev has the same static snapshots as production: US Midcap Stocks ($2-10B), S&P MidCap 400, US Optionable Stocks & ADRs, US Optionable ETFs & Funds. Requests for midcaps or optionable stocks resolve the accessible published list, switch the securities dropdown and explain how to select it manually. Counts describe list members, not detected opportunities. Disabled or inaccessible lists cannot be selected.

## Evidence and Investigation

Published lists live in Redis DB2 tw_published_lists. App.js selects pl:name and filters parent market opportunities by its symbols. Tara's signed set_view contract currently has no list identity. Development worktree starts at origin/main 22a7ee06979600db7b4c9746d69af085259255e4.

## Acceptance and Regression Checks

Pending: deterministic alias routing, entitlement/catalog failures, signed list identity validation and acknowledgement, rendered dropdown/filter transitions for all four lists.

## Implementation and Handoff

Branch codex/tara-published-security-lists-20261004; worktree /home/tradewave-worktrees/tara-published-security-lists-20261004. Next: implement catalog-backed deterministic list commands using signed view actions; focused tests, React build and fast dev activation. Production Tara deployment is outside this request.

## Environment Verification

Dev: pending. Staging: not checked. Production: four admin-created lists verified in earlier owner session; Tara code unchanged.

## History

- 2026-10-04 UTC: Codex claimed task and inspected published-list storage and Tara contract.
