# TW-TASK-0024: October 15 full TradeWave staging release

- Status: complete
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

## Acceptance and disposition
The exact c8ea5b0 release and its source-stamped frontend passed full staging
qualification. The release manifest is complete and valid, all four staging gates
passed, automatic rollback is ready, and the exact-artifact browser gate passed.
Production deployment was not requested and production remains unchanged. No customer
emails, campaigns, payments, or separate SMN deployment occurred.

The original latency failure remains recorded below; the subsequent post-restart and
repeat gates met the unchanged threshold. The stale October 9 market-data freshness
finding remains an unresolved pre-existing risk and was not refreshed or represented
as fixed. See the sanitized evidence receipt at
[evidence/TW-TASK-0024-staging-20261015.json](evidence/TW-TASK-0024-staging-20261015.json).

## Qualification findings
The initial Python run had 62 failures: the guarded local tradewave_test database
was behind current schema, and Tara tests invoked the undecorated handler without
the decoded claims now supplied by the production auth decorator. Correct test
schema/fixtures rather than weaken application auth. Original logs are preserved.
React passed 50 suites / 473 tests; separate MCP suite passed 61 tests.

Initial live Dev API/MCP qualification passed authentication and returned zero load
errors, but failed latency: p95 26.411s versus 15s, 200 requests at concurrency 50.
This is not a pass and no staging write is permitted on this evidence. Preserve
the existing threshold and require fresh exact-artifact post-restart qualification.
Receipt: release-state/tw2-20261015-01/evidence/mvp-initial.log.

## Final staging qualification (2026-10-15)
- Release: tw2-20261015-01, source c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce,
  composite artifact 6b6415e649eccdff16453acd7aeddfea07c3b18e4ff33646c29ee50e7d4910a8.
- Regression: Python 1695 passed / 5 skipped; MCP 61 passed; React 473 passed.
- Load: initial p95 26.411s / 0% errors failed the 15s threshold and remains preserved.
  Exact-artifact post-restart p95 was 10.504s / 0% errors; repeat p95 was 6.369s /
  0% errors. The threshold was not relaxed.
- Staging deploy verification reported 0 failures and 0 warnings. Runtime receipt proved
  the exact SHA and clean source on both hosts, all four service processes and working
  directories, backend fingerprint, and all 21 frontend artifact hashes.
- Authenticated Explorer contract passed: current New York date 2026-10-15, OppList4
  returned 5 patterns / 38 active / 27 priced symbols, ChartData4 returned 11 AXP rows
  with the date lock, and repeated empty responses were byte-identical.
- Browser gate passed on the exact artifact: real pattern response and rendered
  opportunity chart; canvas=1, placeholder=0.
- TW-BUG-0033 staging live check passed for BP in the US WILSHIRE import, rejected a
  bogus ticker, preserved BP-only London selection and AAPL/MSFT behavior. It used an
  ephemeral synthetic strategist login and called no watchlist mutation endpoint.
- Staging rollback and snapshots are ready. Production remains unchanged and unapproved.
- Known risk: updater last reported session Oct 8 / latest US date Oct 9, ok=false,
  updated=0, failed=19003, with ETF/US coverage not ready. Logs were empty, cause
  is unknown, and no refresh was triggered. A root HEAD 403 does not establish a GET
  failure; this risk is not fixed by this release.

Sanitized evidence is in the receipt above and on the release host at
/var/lib/tradewave/release-state/tw2-20261015-01/evidence/.
