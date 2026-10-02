# TW-TASK-0016: October 2 TradeWave Staging and Production Release

- Status: in-progress
- Confidence: reproduced
- Executor/session: Codex release-20261002
- Authorization: Afshin requested latest live Dev deployed to staging first if needed, then production; reinforced complete change coverage.
- Branch/worktree: codex/release-20261002, /home/tradewave-worktrees/tw2-20261002-01
- Manager state: /var/lib/tradewave/release-state/tw2-20261002-01/release.json on Dev.

## Release Coordination

Initial staging and production ran 05ae209ecaba231e5816f835dc133f7c0cdf00e8 (September 16). Staging now runs the qualified release below; production remains on that initial SHA. Dev's effective web, appserver, API/MCP and frontend source components match current main's application tree despite separate process directories. Preserve all existing worktrees and the dirty shared /home/flask checkout.

This record announces the qualified-release freeze. After this claim is integrated, keep main fixed through staging qualification and production disposition. Concurrent tasks may develop and push their own branches; defer default-branch integration until this manager releases the freeze. The exact locked SHA/artifact is authoritative only in the manifest after qualification. Never use the older candidate merely because it built successfully.

## Qualification and Scope

Complete application tree includes Portfolio holdings/scenarios, Wave Info and responsive toolbar changes, Tara knowledge, Strategy Lab API/MCP/renderer/tools, 100-Year Pattern homepage changes, static generators, requirements and scheduled jobs. No separate SMN repository/runtime promotion is authorized by this TradeWave release.

Python safe suite: 1534 passed / 5 skipped; MCP/renderer/transport: 64 passed; React: 48 suites / 457 tests. First cold API load had zero errors but p95 34.658s; permitted identical warm retry passed p95 12.054s with zero errors. No thresholds changed. Initial b33da4a build passed; pre-activation ref check caught a documentation-only main advance to 87882a1 before any runtime write. Rebuild at final claim SHA, reuse unchanged-source tests, and retain both initial gate logs.

Target audits: all four staging/production checkouts are clean at 05ae209; effective service/process paths are canonical /home/flask (the stage-app .tw2-app-current pointer is unused and must be preserved). All targets pass current disk headroom. Staging only supports US/INDX. Both WEB boxes already enable the homepage 100-Year Pattern; production/staging API pricing remains intentionally gated. SMN dashboard SSO is configured only on Dev.

## Verified Staging and Production Handoff

- Locked source/main: c25ffd562dc3058ab41db5b07e9075dd841fb29b.
- Composite artifact: bb0b788da42bd01328a1e6160fbae3555386f4b55524ed3b9439c277fc647ff9. Backend fingerprint cd13ea9178fa134dba6cd5257e7b43cdf1105050baf6a124a46de338c0f1b845; 21 immutable frontend files; main JS 4d98bd7582979c4a81dd3290b590ea69eb8c82834640fb257dc6f1819ce472c9.
- Complete scope since September16: 181 changed files, every intervening commit inventoried in evidence/full-release-commits.txt. Docs-only main advances caught before activation, and once after live Dev checks; that activation automatically restored prior Dev pointers and verified health. Final c25 Dev activation qualified successfully. Final authenticated API/MCP/load gate p95 11.676s, zero errors.
- Staging promoted exact source/build without rebuilding. Backend and all21frontend hashes verified, all four real process working directories canonical, zero target drift, public route/static generator gate clean with zero failures/warnings. Explorer date-locked MSFT chart echoed October2 and returned nonempty11rows; rendered canvas/background, recurrence reset/refetch, desktop/mobile/rotation/resize and privacy-enhanced video gates passed. Tara unsupported-action contracts passed.
- Comparison AAPL/MSFT and a50/50hypothetical basket with MSFT benchmark returned ten shared completed years2016-2025. Gate consumes engine/application output without recomputing financial results. Native PDF pagination and MCP chart display inside signed-in ChatGPT/Claude hosts remain previously unverified.
- Explicit new stock generator and final homepage render completed. home_100yp_stocks.json as_of October2 has nonempty tabs. Checksummed rollback captures generated site/data in addition to source, units, nginx, crons, frontend pointers and static docroot.
- Staging rollback: bash /root/tradewave-handoffs/tw2-20261002-01/staging/rollback-staging.sh. Dev rollback: bash /var/lib/tradewave/release-state/tw2-20261002-01/rollback-dev.sh. Prior target SHA05ae and priorDev backend5ea/frontendf4 retained.
- Production read-only canonical preflight passed; source/runtime still05ae. Production writes have not occurred. Status awaiting_prod_approval. Require Afshin's current-conversation October2 snapshots of both production hosts, exact-release approval and operator execution under current policy. Operator package lives /root/tradewave-handoffs/tw2-20261002-01/production onDev and binds this same SHA/artifact.
- Freeze remains active through production disposition. This outcome is pushed on codex/release-20261002-report to preserve locked main/artifact; integrate the documentation after disposition. Concurrent work can continue on separate branches.

Evidence and durable state are in /var/lib/tradewave/release-state/tw2-20261002-01 onDev; release.json validates and active.json points to the exact SHA. Record production execution, actual snapshots, outcome and freeze release here when completed.
