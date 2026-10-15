# TW-TASK-0024: October 15 full TradeWave staging release

- Status: in-progress
- Owner: Codex chat 01a13f7d-e3a3-7460-aa4e-4a9dae97833f, 2026-10-15
- Authorization: deploy all completed TradeWave Dev changes to staging. Production
  snapshots reported taken; production deployment is not requested by this turn.
- Release: tw2-20261015-01
- Branch/worktree: codex/release-20261015, /home/tradewave-worktrees/tw2-20261015-01
- Baseline Dev source: 3fc3cdb08ca70587433916898f348148356b597b
- Manifest: /var/lib/tradewave/release-state/tw2-20261015-01/release.json

## Release claim and executable plan
Keep main frozen after this claim through qualification and staging disposition.
Other tasks may push isolated branches; do not integrate into main during this release.
Capture all completed current Dev behavior; separately classify target drift and
uncommitted work without sweeping it into a release. Separate SMN runtime is excluded.

1. Inventory Dev source/process/frontend and staging revisions, configuration, services,
   static artifacts, migration state and recoverable differences.
2. Full safe Python, MCP and React regression plus required authenticated API/MCP load
   qualification. Preserve prior TW-BUG-0024 failure criteria, not old pass receipts.
3. Build one source-stamped React artifact at the final frozen SHA; activate exact source
   and artifact on Dev under the short lock. Verify Explorer date/data and rendered chart.
4. Bind manifest to source/composite artifact; prepare executable automatic rollback;
   promote the same qualified artifact to staging without rebuilding.
5. Verify actual runtime identities, service routes, migrations, regenerated static pages,
   CSV fix, level-1 date contract, rendered chart and API/MCP gates.
6. Record results, rollback paths and production-ready handoff. Production writes excluded.

## Acceptance / pending
All checks above must pass. Unit/build/HTTP-200 alone are not acceptance.
No customer emails, campaigns, payments, or separate SMN deployment.
Current target audit, test counts, final source SHA, artifacts, browser evidence and
rollback state: pending. Do not call this release deployable until manifest gates pass.
