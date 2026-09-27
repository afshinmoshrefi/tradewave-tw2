# TW-BUG-0020: Scenario Import Heading Overlap and Phone Layout

- Status: in-progress
- Confidence: owner-reported overlap; responsive verification pending
- Priority: P2 - impairs portfolio import readability and phone usability
- First observed / last updated: 2026-09-27
- Executor/session/claim time: Codex, portfolio-scenarios-20260927, 2026-09-27
- Authorization: owner requested no em dashes, import heading overlap fix, and smartphone verification.

## User Impact and Reproduction

On dev application revision 928fb73cb6bee129825e22e3d6d99c08ac448819, open Portfolio Manager, then Import. Introductory text overlaps Import holdings heading. Check import, setup, history, report and dialogs at desktop and 320-390px phone widths. Existing saved titles and AI text may contain em dashes.

## Acceptance and Regression Checks

Headings and descriptions do not overlap; phone actions remain reachable, tables scroll within their containers, and report totals remain unchanged. Render saved and new report copy without em dashes, including exports. Browser evidence and exact commit pending.

## Implementation and Handoff

Continues TW-TASK-0011 in its clean current-main local worktree and branch codex/portfolio-scenarios-20260927. Parent owns integration and dev activation; focused agent owns scenario CSS only. Financial calculations unchanged. No staging or production authorization. Next action: reproduce, fix and run responsive browser checks.

## Environment Verification

Dev: pending. Staging/production: not deployed by this task.
