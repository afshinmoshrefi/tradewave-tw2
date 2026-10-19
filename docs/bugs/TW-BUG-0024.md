# TW-BUG-0024: API scan load gate is not repeatable during release qualification

- Status: verified on staging
- Confidence: reproduced; exact release behavior verified on Dev and staging
- Priority: P2 - concurrent scorer metadata timeouts blocked repeatable release load qualification; ordinary low-volume requests remained healthy
- First observed / last updated: 2026-10-02 / 2026-10-19
- Executor/session: Codex release manager, session 01a15227-2197-7d33-aa9d-e573769ad9c8
- Authorization: Afshin authorized the latency repair and staging release; production excluded. No engine mathematics, entitlements, thresholds, or score fabrication.

## User Impact and Reproduction

On Dev run the existing ops/dev_mcp_release_auth.py run-gate from clean TradeWave1137664f6cee1647c5c28045bc8beb437c5045b0. Existing dedicated release credentials; normal50-concurrency200-request scan gate, p95 maximum15s and error ceiling1%. One warm-cache pass was followed by a failure after exact-source service restart. Staging and production were not changed.

## Evidence and Investigation

Durable receipts: /var/lib/tradewave/release-state/tw2-20261002-02/evidence on TradeWave Dev. mvp.log:15.334s p95,0%errors while frontend build overlapped. mvp-after-build.log:17.221s,22.5%errors; access-log classification counted45HTTP503. scan-diagnostic.json: five concurrent requests all200 in about5.8s with MISS/WAIT. Subsequent single request200/HIT. mvp-warm-cache.log:10.747s,0%errors, complete gatePASS. After exact-release restart, mvp-qualified.log:16.729s,23%errors, FAIL. No secret-bearing outputs retained. Cause is unconfirmed; scan cache contention, upstream latency and local resource load need differentiation. This cumulative source diff has no API scan or engine code changes.

## Acceptance and Regression Checks

Preserve existing authentication, rate limits, per-user entitlements and evidence completeness. Demonstrate normal mandated gate passes consistently after restart and with warmed cache; retain unsuccessful receipts. Do not relax timeout/error thresholds or cache incomplete results to qualify. Full candidate regression passed1550Python tests(5skipped),63MCP tests,457React tests. Real level1/date contract passed. Admin rendered chart and SMN directlogin passed. Required Explorer browser check remains unrun for this release.

## Implementation and Handoff

No repair. Candidate/artifact preserved in tw2-20261002-02/release.json; statusfailed, managerreleased. Dev source/frontend rollback verified in evidence/dev-activation.log; original directSMN login remains live. Prepared staging package and privateCUA fixture are under /root/tradewave-handoffs/tw2-20261002-02; do not execute until qualification is repaired and refreshed. Next: classify503response codes and upstream/cache timing without credential output, address actual cause within approved scope, then requalify exact source/artifacts and rendered Explorer check before staging.

## Environment Verification

Dev: exact release passed post-restart and warm load gates. Staging: exact release verified and approved. Production: not started and untouched.

## Authorized repair claim - 2026-10-19T03:43:30.457704+00:00
- Executor: Codex session 01a15227-2197-7d33-aa9d-e573769ad9c8; branch codex/load-latency-20261019; worktree /home/tradewave-worktrees/load-latency-20261019.
- User explicitly authorized investigation and repair of load-test latency, followed by staging deployment; production excluded. Related release task TW-TASK-0026.
- New reproduction: candidate 370a2ecc, p95 33.784s then 28.541s with zero errors; both automatic Dev rollbacks verified. Evidence in /var/lib/tradewave/release-state/tw2-20261018-01/evidence.
- Plan: separate client/network/auth/cache/upstream timing; reproduce bottleneck; minimal fix with focused regression preserving authentication, entitlements, rate limits and complete engine output. Then unchanged 200-request/concurrency50 gate after restart and warm, full exact-artifact staging qualification and guarded deploy. Preserve prior runtime rollback; no threshold relaxation or production writes.

## October 19 diagnosis
- At concurrency 50, local scan p95 25.430s (1 MISS,44 WAIT,5 HIT), public authenticated `/me` p95 0.612s, public scan p95 18.575s (50 HIT). Gateway scan work remains slow after the shared core cache; public TLS/auth is not the dominant delay.
- Isolated real-environment Flask profile: warm scan 3.607s, `ml_scores` 3.128s. Traced MLScoreBatch took 3.027s and returned no scores/two pending; MLScorePending took 0.079s, also no scores/two pending.
- Direct scorer metadata probe reproduced ConnectTimeout in 3.009s/3.013s and ConnectionError in 0.043s/0.077s. Current code caches valid metadata for 60s but neither coordinates misses nor backs off failures. Concurrent scans repeatedly occupy appserver threads attempting the unavailable scorer.
- Remediation in progress: shared metadata single-flight and bounded failure cooldown, retaining fail-closed unavailable results and successful identity TTL. Scorer connectivity itself is a separate unresolved dependency; this task must not fabricate ML scores or alter production to repair it.
- Sanitized diagnostics and repeatable scripts live in the prior release evidence directory: latency-diagnostic.jsonl, profile-scan.py, profile-metadata.py, metadata-outage.log.

## Implementation and focused checks
`ml_checkpoint_context.py` now coordinates health metadata lookups across workers with a URL/mode-scoped Redis token lock, a 3.5-second bounded waiter, and a separate five-second failure cooldown. Valid metadata still expires after 60 seconds; all validation and score identity rules remain. Redis failure fails closed; failed cooldown publication retains the expiring lock to prevent repeated probes. Sanitized owner-side warnings omit URL and exception text.
Focused regression: 40 tests passed in `tests/test_ml_checkpoint_context.py`, including concurrent success/failure, recovery, malformed/non-200 responses, identity isolation, stale-owner release, Redis failure, and positive-cache precedence. Full regression and exact live qualification pending; no fix verified yet.

## Initial fix live evidence and refinement
Candidate d648e280 passed full regression (1750 Python,61 MCP,482 React) and built. First post-restart gate passed p95 14.043s/errors0%; an immediate repeat hit existing minute quota (p95 9.465s,31.5%429). Gate scheduling now starts each 200-request run in a fresh existing minute window; no limits or thresholds changed. A later post-restart run still failed p95 23.183s/errors0%. Diagnostic runs then passed post-restart13.643s and warm8.187s/errors0%; per-response Server-Timing exposed queueing and recurrent approximately4s cache-hit processing during metadata probes.
Despite that passing pair, refinement is needed for repeatability: after cooldown expires, existing waiters block again during each unavailable scorer probe. Add a bounded recent-outage marker so one half-open probe retries while peers promptly retain unavailable state. Healthy initial lookups still share a bounded wait. Prior Dev was explicitly restored and four services verified before editing the inactive candidate; the passing pair and original manifest are preserved in `evidence/d648-qualified-pair-before-refinement/`. Staging untouched.

Half-open refinement focused checks: 41 passed. The concurrency regression holds the recovery probe behind an event and proves all 11 peers return unavailable before that probe is released; later valid recovery clears both breaker markers. Evidence: `metadata-half-open-focused-pytest.txt`. Full exact-source release qualification is pending.

## October 19 repair and staging verification

- Final source/artifact SHA 0c67bb840fa152c8de9e427d8a3e801239caf6f0, release tw2-20261019-01. The metadata breaker uses a 30-second recent-outage marker and a separate five-second retry cooldown. During a known outage, one bounded half-open probe may retry while concurrent scan peers return unavailable promptly. Healthy initial metadata lookups retain the bounded wait; valid recovery clears both outage markers. Results remain fail-closed and scoring/identity rules are unchanged.
- Focused regression: 41 passed, including a blocked recovery probe with 11 peers returning unavailable before probe release, followed by successful recovery. Full regressions: Python 1751, MCP 61, React 482.
- Dev load gate passed after restart at p95 13.292s and warm at 8.081s with 0% errors. Thresholds were not changed. Staging runtime and live API receipts passed. CUA verified Explorer CAT chart loading and public Buy & Hold MSFT/AAPL comparison controls (4- and 6-year selections, series, measure, range, reset).
- Scorer upstream remained unavailable on Dev during qualification. The system continues to return unavailable/fail closed without fabricated scores; upstream connectivity remains a separate dependency, not a failed staging gate.
- Staging evidence: /var/lib/tradewave/release-state/tw2-20261019-01/evidence/staging-deploy.log, staging-api.json, staging-runtime.json, staging-browser-gate.json, and screenshots. The October 18 failed candidate evidence remains preserved at /var/lib/tradewave/release-state/tw2-20261018-01/evidence/.
- Production was not inspected or changed.
