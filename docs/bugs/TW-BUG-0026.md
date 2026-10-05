# TW-BUG-0026: Mobile bar chart More control does not open extra controls

- Status: in-progress
- Confidence: reported; live touch reproduction pending
- Priority: P2 - users cannot reach additional bar chart controls on mobile
- First observed / last updated: 2026-10-05 10:51 UTC
- Executor/session/claim time: Codex /root/mobile_controls; 2026-10-05 10:51 UTC
- Authorization: fix this mobile toolbar regression; verify and activate on Dev only; staging/production excluded

## User Impact and Reproduction

After mobile toolbar titles were removed, the bar chart up/down triangle (More) reportedly stopped opening extra controls. On mobile Dev, tap the More triangle. Expected: the expanded row of controls opens; actual: pending direct touch reproduction. Device/browser and current artifact: pending.

## Evidence and Investigation

Related change: [TW-TASK-0012](../tasks/TW-TASK-0012.md), which removed mobile toolbar titles while retaining desktop titles. A desktop mouse click against the supplied smartphone-emulated tab timed out in CDP and did not reproduce an app failure; direct touch verification is required. Candidate source is `web-react/src/components/SeasonalBarChart.js`.

## Acceptance and Regression Checks

Tap More using touch on a mobile viewport and verify the extra controls open, are usable, and close again. Confirm mobile control titles remain absent and desktop titles remain available. Run one React build and a focused live Dev touch smoke. Tests not run: pending.

## Implementation and Handoff

Repository `tradewave-tw2`; branch `codex/toolbar-more-mobile-20261005`; task worktree pending on `tradewave-vm` under `/home/tradewave-worktrees/`. Current origin/main at claim: `951821837d8807e96fe4243c4679c43767666617`. Source/integration SHAs, changed files, build, activation, evidence, rollback pointer and clean state: pending. Preserve unrelated dirty `/home/flask`. Next: reproduce with touch, identify the smallest correction, build, activate and verify Dev.

## Environment Verification

Dev: deployed/unverified; exact source/artifact pending. Staging: not checked. Production: not checked.

## History

- 2026-10-05: Claimed authorized mobile More-control regression; implementation and direct-touch reproduction pending.
