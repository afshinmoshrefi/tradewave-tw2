# TW-TASK-0019: Published US security lists and Tara selection

- Status: verified-dev
- Confidence: verified
- Priority: P2 - requested list discovery and viewer control
- First observed / last updated: 2026-10-04 UTC
- Executor/session/claim time: Codex, tara-published-security-lists-20261004, 2026-10-04 UTC
- Authorization: Copy four owner-requested published lists to dev; implement and verify Tara discovery, selection and manual instructions on dev.

## Goal, Scope and Acceptance

Dev has the same static snapshots as production: US Midcap Stocks ($2-10B), S&P MidCap 400, US Optionable Stocks & ADRs, US Optionable ETFs & Funds. Requests for midcaps or optionable stocks resolve the accessible published list, switch the securities dropdown and explain how to select it manually. Counts describe list members, not detected opportunities. Disabled or inaccessible lists cannot be selected.

## Evidence and Investigation

Published lists live in Redis DB2 tw_published_lists. App.js selects pl:name and filters parent market opportunities by its symbols. Tara's signed set_view contract currently has no list identity. Development worktree starts at origin/main 22a7ee06979600db7b4c9746d69af085259255e4.

## Acceptance and Regression Checks

Passed: 145 backend contract/catalog/entitlement tests, 42 frontend contract/guidance tests, 22 prompt context tests, React production build. Rendered Chrome checks selected every list with exact name and correct count. All 308 midcap, 202 S&P 400, 869 optionable stock and 330 ETF/fund opportunity rows belonged to their respective source lists. Asking how to select midcaps returned instructions and preserved the ETF/fund selection.

## Implementation and Handoff

Branch codex/tara-published-security-lists-20261004; worktree /home/tradewave-worktrees/tara-published-security-lists-20261004. Completed: catalog-backed deterministic list commands, signed view actions, exact observed list acknowledgements, preference enabling, manual instructions, focused tests, React build and live dev activation. Production Tara deployment is outside this request.

## Environment Verification

Dev: verified on source/artifact f935057beb4e433010bbe98f8675f5aa5feb226c; current main and active backend/build provenance match. Evidence is retained under /var/lib/tradewave/release-state/tara-security-lists-20261004/dev-verification.json and dev-ui-proof.json. Staging: not checked. Production: four admin-created lists verified in earlier owner session; Tara code unchanged.

## History

- 2026-10-04 UTC: Codex claimed task and inspected published-list storage and Tara contract.

## October 4 implementation evidence

The four dev catalogs were seeded through the existing owner's normal generate_ltk -> /login/session -> /create_published_list flow. No account roles or entitlements were changed. All symbol arrays exactly match the production-created snapshots. Before-catalog backup and SHA-256 membership receipt: /var/lib/tradewave/release-state/tara-security-lists-20261004/. Static snapshots use Finviz October2 screening and IJH October1 equity constituent holdings; they do not add missing market-price data or auto-refresh.

Backend routing/catalog/signature tests: 145 passed. Frontend contract/guidance tests: 42 passed. The frontend test initially found a missing async response callback; corrected before activation. React build and all four rendered list selections passed. The how-to request did not change selection. No staging or production code activation.

Rollback: preserve the previous backend and React symlink targets, atomically restore them and restart affected services. The published list data is additive and remains independently stored in Redis DB2. Prior catalog backup is retained; no rollback should overwrite unrelated subsequent admin changes.

- 2026-10-04 UTC: Committed and pushed f935057beb4e433010bbe98f8675f5aa5feb226c, activated and verified dev, advanced main non-forced, verified backend/frontend/main parity, released dev activation lock. Rollback pointers are in activation-before.json.

- Owner correction: "how about micaps" must select midcaps. Normal manual selection uses the top-left market dropdown with published lists at its bottom, not Settings. Backend follow-up parsing and guidance corrected; 176 backend/prompt regression checks passed. Live Chrome verified the exact typo follow-up, ordinary midcap follow-up, optionable follow-up and help-only behavior in the owner conversation. Active source e9499d99f33232ab0140b5c61ddae4ce943e1161; main matches; React artifact unchanged because this fix is backend-only. Evidence: followup-verification.json.
