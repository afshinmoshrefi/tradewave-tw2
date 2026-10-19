# TW-TASK-0026: October 18 TradeWave staging release

- Status: in-progress
- Confidence: regression passed; live Dev qualification failed; staging not attempted
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


## Regression qualification (2026-10-19 UTC)
- Exact starting candidate: `1ac16255fb39a5f4954a95fa9d360535ac00d518`; frozen `origin/main` matched before qualification.
- Safe Python regression: `/home/flask/venv/bin/python -m pytest -ra --tb=short` from the candidate worktree - **1740 passed, 5 skipped, 10 warnings**. The skips are missing optional MCP imports in this venv, two ungenerated quickstart snippets, and the documented deferred AI-branch React contract.
- Separate MCP regression: `/home/flask/venv-api/bin/python -m pytest tests/test_mcpserver.py -ra --tb=short` - **61 passed**.
- Initial React regression found one stale expected menu list: `Common.js` already includes `Buy & Hold Across Time` between `Buy & Hold` and `Reverse Date Range`. Updated only the test expectation to include the exact existing value and label. Focused test: **3 passed**. Full React regression: `npm test -- --watchAll=false --runInBand` - **52 suites, 482 tests passed**.
- The first React build completed for the starting SHA `1ac16255fb39a5f4954a95fa9d360535ac00d518`, but is superseded by the test/documentation commit. No activation was performed. A provenance-stamped build of the final commit is required before continuing qualification.
- Logs: `/var/lib/tradewave/release-state/tw2-20261018-01/evidence/pytest-full.log`, `pytest-mcpserver.log`, `react-npm-test.log` (initial failure), `react-date-range-targeted.log`, `react-npm-test-after-fix.log`, and `react-build.log` (superseded build).

## Release disposition (2026-10-19 UTC)
- Exact candidate `370a2ecc148adbf64a57116c8489113466317c00` built successfully; artifact fingerprint `936245966280fc8bae8f8605b3b7cb34f26272702ee32add2661fc099e979cd9`. Python 1740 passed/5 skipped, MCP 61 passed, React 52 suites/482 tests passed. No runtime application changes during this release.
- Mandatory authenticated API/MCP post-restart load gate failed on two bounded attempts: p95 **33.784s** then **28.541s**, above **15s**, with 200 requests at concurrency 50 and 0% request errors. OAuth signature/issuer/audience validation succeeded. The repeat/warm gate and browser qualification were not reached. This resembles open TW-BUG-0024; root cause is not established. No thresholds were weakened.
- Each failed attempt automatically restored prior Dev backend `/home/tradewave-worktrees/exact-ticker-integrated-20261018` and frontend `/home/flask/web-react/releases/build-fa9ffc510929ac9b829479118a6836daef258e38`. Both pointers, health checks and all four active services were verified after final rollback. Dev activation lock released.
- Staging remains unchanged at `c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce`; no staging snapshots or deployment executed. Production excluded and untouched. Prepared staging scripts were not executed.
- Release manifest is schema-valid `failed`; Dev `rolled_back`, rollback `verified`, staging `not_started`. Manager ownership and main freeze released. Candidate artifact and evidence retained. Temporary Explorer fixture service/tunnel stopped and credential-bearing fixture shells removed.
- Evidence root `/var/lib/tradewave/release-state/tw2-20261018-01/`: `evidence/attempt-1/mvp-post-restart.log`, `evidence/mvp-post-restart.log`, `evidence/dev-activation.log`, `dev-rollback-verified.json`, `evidence/react-build-final.log`, `release.json`.
- Next action: investigate the live load-gate latency under TW-BUG-0024 before a fresh qualification attempt. Deployment acceptance remains incomplete; do not promote this failed candidate or infer staging approval.

## Resume authorization
User authorized fixing load latency and continuing staging, with production excluded. TW-BUG-0024 is claimed by the same session; staging remains unchanged while diagnosis runs.
