# TW-TASK-0016: October 2 TradeWave Staging and Production Release

- Status: in-progress
- Confidence: reproduced
- Executor/session: Codex release-20261002
- Authorization: Afshin requested latest live Dev deployed to staging first if needed, then production; reinforced complete change coverage.
- Branch/worktree: codex/release-20261002, /home/tradewave-worktrees/tw2-20261002-01
- Manager state: /var/lib/tradewave/release-state/tw2-20261002-01/release.json on Dev.

## Release Coordination

Current staging and production run 05ae209ecaba231e5816f835dc133f7c0cdf00e8 (September 16). Dev's effective web, appserver, API/MCP and frontend source components match current main's application tree despite separate process directories. Preserve all existing worktrees and the dirty shared /home/flask checkout.

This record announces the qualified-release freeze. After this claim is integrated, keep main fixed through staging qualification and production disposition. Concurrent tasks may develop and push their own branches; defer default-branch integration until this manager releases the freeze. The exact locked SHA/artifact is authoritative only in the manifest after qualification. Never use the older candidate merely because it built successfully.

## Qualification and Scope

Complete application tree includes Portfolio holdings/scenarios, Wave Info and responsive toolbar changes, Tara knowledge, Strategy Lab API/MCP/renderer/tools, 100-Year Pattern homepage changes, static generators, requirements and scheduled jobs. No separate SMN repository/runtime promotion is authorized by this TradeWave release.

Python safe suite: 1534 passed / 5 skipped; MCP/renderer/transport: 64 passed; React: 48 suites / 457 tests. First cold API load had zero errors but p95 34.658s; permitted identical warm retry passed p95 12.054s with zero errors. No thresholds changed. Initial b33da4a build passed; pre-activation ref check caught a documentation-only main advance to 87882a1 before any runtime write. Rebuild at final claim SHA, reuse unchanged-source tests, and retain both initial gate logs.

Target audits: all four staging/production checkouts are clean at 05ae209; effective service/process paths are canonical /home/flask (the stage-app .tw2-app-current pointer is unused and must be preserved). All targets pass current disk headroom. Staging only supports US/INDX. Both WEB boxes already enable the homepage 100-Year Pattern; production/staging API pricing remains intentionally gated. SMN dashboard SSO is configured only on Dev.

## Remaining Gates and Handoff

1. Build/fingerprint final frozen SHA, reconcile Dev to it under the short activation lock, run live Explorer chart/date/browser and full API/MCP qualification.
2. Capture executable staging backend/frontend/static/unit/cron rollback, audit all target differences, run guarded deploy and mandatory live contracts/browser checks. Refresh today's 100-Year stock list as part of homepage publication; routine regen alone does not invoke its new generator.
3. Prepare production commands for exactly that staging-approved artifact. Afshin/operator executes production writes; require October 2 snapshots of both production servers confirmed in this release conversation. No production write has occurred.
4. Record environment outcomes, exact SHA/artifact and any pending verification before handoff; release freeze only after disposition is durable.

Previously unverified limits remain explicit: Portfolio native PDF pagination and MCP chart display inside signed-in ChatGPT/Claude hosts. No repair or successful verification is claimed for these by unit tests.
