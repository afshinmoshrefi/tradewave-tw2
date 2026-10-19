# TW-TASK-0026: October 18 TradeWave staging release

- Status: in-progress
- Confidence: Dev behavior verified; new staging qualification pending
- Priority: P2
- Executor: Codex chat 01a15227-2197-7d33-aa9d-e573769ad9c8
- Claim UTC: 2026-10-19T03:19:39.292131+00:00
- Authorization: Afshin explicitly confirmed deployment of current Dev watchlist fix and Buy & Hold changes to staging. Production excluded.
- Release: tw2-20261018-01; branch codex/release-20261018
- Worktree: /home/tradewave-worktrees/tw2-20261018-01

## Goal, Scope and Acceptance
Promote current Dev behavior as one immutable source/frontend artifact. Include exact ticker validation TW-BUG-0035 and Buy & Hold Across Time with zoom TW-TASK-0025. Preserve financial calculations and disclosed TW-BUG-0036 data limitation; no data repair, customer messaging, or separate SMN deployment.

## Executable plan and release claim
Keep main frozen after this claim until release disposition. Other task branches may proceed independently. Prior release tw2-20261015-01 is complete and manager released per current active.json.
1. Audit source/runtime parity and staging drift; preserve all unrelated changes.
2. Full safe Python/MCP/React regression, one source-stamped release build, mandatory authenticated API/MCP load gate.
3. Activate exact artifact on Dev with prior pointers retained; verify Explorer date contract, chart loading, ticker validation and Buy & Hold interactions.
4. Audit and capture staging rollback; deploy exact artifact with automatic rollback, verify runtime hashes, services, contracts and rendered behavior.
5. Finalize manifest and shared evidence; production requires separate authorization.

## Evidence and handoff
Baseline main 4aa02c6b36efe0d6e3d766ed4a0136ba3b4def70 differs from live fa9ffc510929ac9b829479118a6836daef258e38 only in three bug documentation files. Dev backend /home/tradewave-worktrees/exact-ticker-integrated-20261018; frontend /home/flask/web-react/releases/build-fa9ffc510929ac9b829479118a6836daef258e38.
Manifest /var/lib/tradewave/release-state/tw2-20261018-01/release.json. Qualification, artifact hashes, target audit and executable rollback pending. No schema change expected; verify against previous release. Next action: run qualification at the claim commit, build once, then live Dev gates.

## Environment verification
Dev: prior behavior verified; exact release qualification pending. Staging: unchanged. Production: excluded and unchanged.
