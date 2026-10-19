# TW-TASK-0026: October 19 TradeWave release

- Status: complete - production verified
- Confidence: exact source and artifact passed Dev, staging, and production gates
- Priority: P2
- Executor: Codex release manager, session 01a15227-2197-7d33-aa9d-e573769ad9c8
- Claim UTC: 2026-10-19T03:19:39.292131+00:00
- Authorization: Afshin explicitly authorized the Dev load-latency repair, staging deployment, and (after staging retest) autonomous production deployment with rollback on failure. The production verification and final receipts are recorded below.
- Release: tw2-20261019-01; source SHA 0c67bb840fa152c8de9e427d8a3e801239caf6f0
- Worktree: /home/tradewave-worktrees/load-latency-20261019

## Goal, Scope and Acceptance
Promote current Dev behavior as one immutable source/frontend artifact. Include exact ticker validation TW-BUG-0035 and Buy & Hold Across Time with zoom TW-TASK-0025. Preserve financial calculations and disclosed TW-BUG-0036 data limitation; no data repair, customer messaging, or separate SMN deployment.

## Executable plan and release claim
Keep main frozen after this claim until release disposition. Other task branches may proceed independently. Prior release tw2-20261015-01 is complete and manager released per current active.json.
1. Audit source/runtime parity and staging drift; preserve all unrelated changes.
2. Full safe Python/MCP/React regression, one source-stamped release build, mandatory authenticated API/MCP load gate.
3. Activate exact artifact on Dev with prior pointers retained; verify Explorer date contract, chart loading, ticker validation and Buy & Hold interactions.
4. Audit and capture staging rollback; deploy exact artifact with automatic rollback, verify runtime hashes, services, contracts and rendered behavior.
5. Finalize manifest and shared evidence; production deployment proceeds only against the exact approved source/artifact, after current snapshots and preflight, with automatic rollback on failure.

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
- At that point, the next action was to investigate TW-BUG-0024 and requalify a fresh candidate. That work and a separate staging release are recorded below; the failed candidate remains unpromoted.

## Resume authorization
User authorized fixing load latency and continuing staging, with production excluded. TW-BUG-0024 is claimed by the same session; staging remains unchanged while diagnosis runs.

## Replacement release
The failed release tw2-20261018-01 remains preserved with immutable evidence. Its failure was investigated under TW-BUG-0024 and resolved for the load-gate behavior in a separate release. Production remains excluded.

## Staging release completion - 2026-10-19 UTC

- Release tw2-20261019-01 promoted exact source/artifact SHA 0c67bb840fa152c8de9e427d8a3e801239caf6f0. The final manifest is complete, with staging verified and approved; production remains not started and untouched.
- Full regressions passed: Python 1751, MCP 61, React 482. The 41-test focused metadata half-open regression also passed.
- Dev load qualification passed after restart at p95 13.292s and warm at 8.081s, with 0% request errors. The existing 15-second p95 threshold and error limits were unchanged.
- Staging runtime and live API receipts passed with zero failures and warnings. CUA verified the real Explorer CAT chart and public Buy & Hold MSFT/AAPL comparisons, including 4- and 6-year selections and series, measure, range, and reset controls.
- During this release the scorer upstream remained unavailable on Dev. The app fails closed without fabricated scores; the metadata breaker prevents concurrent scan peers from creating a timeout storm. Production was not inspected or changed.
- Snapshot evidence: the August 18 stage-WEB snapshot was archived to Dev at /root/tradewave-snapshot-archive/stage-web/tw2-20260818-03 with checksum-verified rsync; current release snapshots are ready.
- Durable release evidence is under /var/lib/tradewave/release-state/tw2-20261019-01/evidence/: staging-deploy.log, staging-api.json, staging-runtime.json, staging-browser-gate.json, and browser screenshots. The prior failed October 18 release evidence remains under its separate release-state directory.

## Production handoff - 2026-10-19 UTC

- Afshin explicitly authorized autonomous production deployment after staging retest and confirmed provider snapshots for both production servers. Fresh on-box APP and WEB snapshots were also completed and verified before activation.
- Staging retest passed on the exact source/artifact. Public staging verification confirmed the CAT Explorer chart and Buy & Hold MSFT/AAPL comparisons, 4- and 6-year selections, measure, range, and reset. The earlier Explorer receipt was corrected because it showed a Dev-proxied view; evidence/staging-browser-evidence-correction.json documents the attribution and evidence/staging-retest-browser.json is the superseding receipt.
- Exact candidate 0c67bb840fa152c8de9e427d8a3e801239caf6f0 completed production deployment CLEAN with 0 failures and 0 warnings. Runtime heads and frontend hashes matched the release artifact on both production targets. The live API receipt passed Explorer rows, Buy & Hold MSFT/AAPL 4- and 6-year four-series comparisons, 403 for an invalid token, exact US ticker validation, and an LSE HSBA add/duplicate/cleanup flow. Scorer health returned HTTP 200 in 5 ms.
- CUA confirmed the rendered production CAT chart (one canvas, no placeholder) and Buy & Hold series, measure, range, and reset controls. Because fresh owner WorkOS sign-in presents a pre-existing human challenge, browser verification used transaction-only synthetic Explorer/Strategist shells bound to the exact bundle and proxied to the public production API; request logs are retained and no permanent users were created. This is a verification-method limitation, not a failed gate.
- The watchdog verified and disarmed; no rollback occurred and production remains live. The manifest is complete, production verified, and manager released.
- Receipts are under /var/lib/tradewave/release-state/tw2-20261019-01/evidence/: production-api.json, production-scorer-health.json, production-browser-gate.json, prod-fixture-requests.jsonl, production-snapshots.log, production-audit-targets.json, and production-readonly-preflight.log. The current-day snapshot summary is /root/tradewave-handoffs/tw2-20261019-01/prod/snapshots/summary.txt.
