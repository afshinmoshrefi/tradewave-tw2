# Paste-ready prompt for the remote Wave Viewer task

Use **High** reasoning effort for this task, then paste everything below into
the Codex session on the testing computer.

---

Create a durable Codex goal with this objective:

> Make the TradeWave Wave Viewer on the development environment correct,
> stable, and fast. Continue the complete test -> repair -> verify -> deploy to
> dev -> retest loop until every correctness and performance terminal condition
> in `docs/testing/WAVE_VIEWER_LOOP.md` is achieved.

Keep that goal active until it is achieved. Do not mark it complete after one
repair, passing unit tests, a successful build, a successful deployment, one
clean retest, or a partial pass. If any case or performance budget fails,
immediately begin the next loop iteration. Ask me only when one of the explicit
stop conditions in the loop document is met.

This is full Wave Viewer regression testing and repair, not a
performance-only task. Test the complete original regression matrix, repair all
reproducible product regressions in scope, retest for newly introduced
regressions, and include P-01 loading speed as an additional required
acceptance area.

Start in this existing worktree and branch:

- worktree: `/home/tradewave-wave-loop-20260724`
- branch: `codex/wave-viewer-regression-loop-20260724`

Before changing anything, read these files completely:

1. `/home/tradewave-wave-loop-20260724/docs/TRADEWAVE_ECOSYSTEM.md`
2. `/home/tradewave-wave-loop-20260724/docs/testing/WAVE_VIEWER_LOOP.md`
3. `/home/tradewave-wave-loop-20260724/docs/testing/WAVE_VIEWER_CURRENT.md`
4. `/home/tradewave-wave-loop-20260724/docs/testing/WAVE_VIEWER_RUN_LOG.md`

The only deployment target authorized by this goal is the Wave Viewer
development host `192.168.1.176` (`TW2`) serving
`https://tw2-dev.trxstat.com/app/`. Never modify `192.168.1.180`, staging,
production, TW1, secrets, billing, authentication, customer data, or DQ-01.

The live dev bundle is currently `main.08bde07a.js`. It renders patterns after
rollback, but bar-chart loading is extraordinarily slow. The rejected bundle
`main.e3ef851f.js` became stranded on `Loading statistics for FAST...` and must
not be redeployed unchanged. The current branch accidentally contains
unverified frontend changes. Treat its source as quarantined: compare it with
the last-known-good source at `/home/flask/web-react/src/components`, remove
unintended changes, and reapply only verified repairs.

Run this loop autonomously until the goal is achieved:

1. **Test:** confirm the live bundle and baseline; reproduce the remaining
   cases; capture P-01 cold and warm latency measurements.
2. **Repair:** diagnose the actual frontend/backend timing and state causes;
   make the smallest coherent change and add focused tests or instrumentation.
3. **Verify:** run focused tests, all runnable React tests, and a production
   build. Before live deployment, prove through the dev-only capture/smoke
   harness that the primary chart-data request launches and a bar-chart canvas
   renders.
4. **Deploy to dev:** create an immutable release, record the rollback target,
   and atomically switch the `.176` dev symlink only.
5. **Retest:** hard-refresh, record the exact bundle hash, rerun repaired and
   adjacent cases, and repeat P-01 measurements on that same bundle. Once the
   focused set is green, run the complete original regression matrix.
6. **Record:** update `WAVE_VIEWER_CURRENT.md`, append
   `WAVE_VIEWER_RUN_LOG.md`, then commit and push the verified iteration.
7. **Continue:** if anything fails or misses budget, return to step 1 without
   waiting for me.

Correctness priority is cases 7, 8, 13, 17, 20, 22, NR-01, and NR-02. Rerun
adjacent passing cases 5, 11, 15, 26, 30, and 35 after each relevant repair.
DQ-01 (`BK` Price `NaN`) is an excluded analytics/reference-data follow-up.

P-01 performance is required, not optional. Measure:

- selection/page-ready to primary chart-data request start;
- chart-data request duration;
- response completion to first stable bar-chart canvas;
- total selection-to-usable-chart time.

Use one cold authenticated reload and five warm selections, including UNH,
PCAR, and FAST where available. The required budgets are:

- post-response frontend render median <= 500 ms, maximum <= 1 second;
- warm selection-to-usable-chart median <= 3 seconds, maximum <= 5 seconds;
- cold reload to first usable bar chart <= 10 seconds;
- primary chart request is not gated by optional downstream work;
- no stale, mixed-symbol, blank, or permanently Loading chart.

The goal is achieved only after all requested correctness cases and all P-01
budgets pass in **two consecutive clean runs on the same deployed bundle**, the
baseline is restored after both runs, and there are no new console, API,
data-mixing, Loading-state, or UI regressions. Continue looping until then.
