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

## October 4 implementation evidence

The four dev catalogs were seeded through the existing owner's normal generate_ltk -> /login/session -> /create_published_list flow. No account roles or entitlements were changed. All symbol arrays exactly match the production-created snapshots. Before-catalog backup and SHA-256 membership receipt: /var/lib/tradewave/release-state/tara-security-lists-20261004/. Static snapshots use Finviz October2 screening and IJH October1 equity constituent holdings; they do not add missing market-price data or auto-refresh.

Backend routing/catalog/signature tests: 145 passed. Frontend contract/guidance tests: 42 passed. The frontend test initially found a missing async response callback; corrected before activation. Final build/live verification pending. No staging or production code activation.

Rollback: preserve the previous backend and React symlink targets, atomically restore them and restart affected services. The published list data is additive and remains independently stored in Redis DB2. Prior catalog backup is retained; no rollback should overwrite unrelated subsequent admin changes.
