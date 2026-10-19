# TW-BUG-0024: API scan load gate is not repeatable during release qualification

- Status: in-progress
- Confidence: reproduced
- Priority: P2 - blocks SMN dashboard/auth release promotion; ordinary low-volume requests remain healthy
- First observed / last updated: 2026-10-02
- Executor/session: Codex smn-auth-release-20261002; diagnosis recorded, no API repair claimed
- Authorization: release qualification and documentation; no engine mathematics or entitlement changes

## User Impact and Reproduction

On Dev run the existing ops/dev_mcp_release_auth.py run-gate from clean TradeWave1137664f6cee1647c5c28045bc8beb437c5045b0. Existing dedicated release credentials; normal50-concurrency200-request scan gate, p95 maximum15s and error ceiling1%. One warm-cache pass was followed by a failure after exact-source service restart. Staging and production were not changed.

## Evidence and Investigation

Durable receipts: /var/lib/tradewave/release-state/tw2-20261002-02/evidence on TradeWave Dev. mvp.log:15.334s p95,0%errors while frontend build overlapped. mvp-after-build.log:17.221s,22.5%errors; access-log classification counted45HTTP503. scan-diagnostic.json: five concurrent requests all200 in about5.8s with MISS/WAIT. Subsequent single request200/HIT. mvp-warm-cache.log:10.747s,0%errors, complete gatePASS. After exact-release restart, mvp-qualified.log:16.729s,23%errors, FAIL. No secret-bearing outputs retained. Cause is unconfirmed; scan cache contention, upstream latency and local resource load need differentiation. This cumulative source diff has no API scan or engine code changes.

## Acceptance and Regression Checks

Preserve existing authentication, rate limits, per-user entitlements and evidence completeness. Demonstrate normal mandated gate passes consistently after restart and with warmed cache; retain unsuccessful receipts. Do not relax timeout/error thresholds or cache incomplete results to qualify. Full candidate regression passed1550Python tests(5skipped),63MCP tests,457React tests. Real level1/date contract passed. Admin rendered chart and SMN directlogin passed. Required Explorer browser check remains unrun for this release.

## Implementation and Handoff

No repair. Candidate/artifact preserved in tw2-20261002-02/release.json; statusfailed, managerreleased. Dev source/frontend rollback verified in evidence/dev-activation.log; original directSMN login remains live. Prepared staging package and privateCUA fixture are under /root/tradewave-handoffs/tw2-20261002-02; do not execute until qualification is repaired and refreshed. Next: classify503response codes and upstream/cache timing without credential output, address actual cause within approved scope, then requalify exact source/artifacts and rendered Explorer check before staging.

## Environment Verification

Dev: failure reproduced and rollback verified October2. Staging/prod: read-only source/runtime audits pass at priorc25ffd5; no deployment.

## Authorized repair claim - 2026-10-19T03:43:30.457704+00:00
- Executor: Codex session 01a15227-2197-7d33-aa9d-e573769ad9c8; branch codex/load-latency-20261019; worktree /home/tradewave-worktrees/load-latency-20261019.
- User explicitly authorized investigation and repair of load-test latency, followed by staging deployment; production excluded. Related release task TW-TASK-0026.
- New reproduction: candidate 370a2ecc, p95 33.784s then 28.541s with zero errors; both automatic Dev rollbacks verified. Evidence in /var/lib/tradewave/release-state/tw2-20261018-01/evidence.
- Plan: separate client/network/auth/cache/upstream timing; reproduce bottleneck; minimal fix with focused regression preserving authentication, entitlements, rate limits and complete engine output. Then unchanged 200-request/concurrency50 gate after restart and warm, full exact-artifact staging qualification and guarded deploy. Preserve prior runtime rollback; no threshold relaxation or production writes.
