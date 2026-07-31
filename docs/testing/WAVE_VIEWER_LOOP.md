# Wave Viewer autonomous test and repair loop

## Purpose

This is the durable operating contract for a Codex task that owns the Wave
Viewer regression loop on the development environment. Read this file,
`WAVE_VIEWER_CURRENT.md`, and `docs/TRADEWAVE_ECOSYSTEM.md` before making
changes.

The task is authorized to inspect, edit, test, build, and deploy to the
development environment only. It is not authorized to modify staging,
production, TW1, customer data, billing, authentication, analytics records, or
the BK reference-data issue.

## Goal

Make the development Wave Viewer correct, stable, and fast. Keep this goal
active and continue the complete test -> repair -> verify -> deploy to dev ->
retest loop until every correctness and performance terminal condition in this
document is achieved.

This is a full application regression-and-repair goal, not a performance-only
exercise. The focused failing and adjacent cases establish repair order; once
they are green, run the complete original regression matrix and investigate any
newly observed regression. P-01 adds measurable speed acceptance to that full
test scope.

Do not mark the goal complete after a source repair, passing unit tests, a
successful build, or a successful deployment. Those are intermediate states.
Do not stop after one loop iteration. A regression or missed performance budget
starts another iteration on the same goal.

## Source and environment

- Handoff branch: `codex/wave-viewer-regression-loop-20260724`
- Application URL: `https://tw2-dev.trxstat.com/app/`
- Development host: `192.168.1.176`
- Repository path normally used on a TradeWave development host:
  `/home/flask`
- React source: `web-react/`
- React build command: `npm run build`

Before changing anything, confirm the hostname, repository path, nginx vhost,
current branch, worktree status, and the filesystem target serving
`tw2-dev.trxstat.com/app/`. Do not overwrite a dirty server checkout or switch
a symlink until its current target and rollback target have been recorded.

Never request or print a password or secret. Use credentials already available
to the remote task.

## Goal loop

Run these phases repeatedly without waiting for the owner between ordinary
development iterations:

1. **Test.** Read `WAVE_VIEWER_CURRENT.md`, inspect the served JavaScript
   bundle, restore the S&P 500 STOCKS / 10 years / 8 of 10 / empty-filter
   baseline, reproduce the remaining failures, and measure P-01 chart latency.
   Save concise evidence.
2. **Diagnose and repair.** Identify the state transition, request, rendering,
   or data-source cause. Add or update a focused automated test or timing
   instrumentation. Make the smallest coherent repair. Preserve Opportunity
   Table state independently from Wave Viewer cycle and years state.
3. **Verify before deployment.** Run focused tests, all runnable React unit
   tests, and a production React build. Use the dev-only capture/smoke harness
   to prove the primary chart-data request launches and the first bar-chart
   canvas renders before changing the live build symlink.
4. **Deploy to development only.** Use a new immutable release directory and
   an atomic symlink swap. Record and preserve the previous symlink as the
   rollback target. Never copy a partial build over a live directory.
5. **Retest the same bundle.** Hard-refresh the authenticated browser, record
   the bundle hash, verify the baseline, rerun repaired and adjacent cases, and
   repeat the P-01 timing sample. When the focused set is green, run the
   complete original regression matrix on that bundle.
6. **Record the iteration.** Update `WAVE_VIEWER_CURRENT.md`, append a dated
   entry to `WAVE_VIEWER_RUN_LOG.md`, and commit and push the verified round to
   the handoff branch.
7. **Evaluate the goal.** If any correctness case fails, any performance
   budget is missed, a Loading state becomes stranded, or a new regression
   appears, return to phase 1. Continue until the goal's terminal conditions
   have been achieved.

When one change affects filter membership, sorting, recurrence, loading state,
or viewer/table ownership, rerun every case in that interaction family rather
than only the originally failing case.

## Required regression order

Run the currently failing cases first:

1. Case 7 - invalid filter indicator.
2. Case 8 - rapid edit stale-result protection.
3. Case 13 - filter help and accessible naming.
4. Case 17 - day-range and PredR intersection.
5. Case 20 - incomplete AI-token editing.
6. Case 22 - sorting must not change the active filter.
7. NR-01 - viewer years must not propagate to the Opportunity Table after
   reload.
8. NR-02 - a stale AI-sort response must not override a later clear or leave
   Loading stranded.

Then rerun the already passing adjacent cases: 5, 11, 15, 26, 30, and 35.
Finally rerun the complete original matrix when the focused set is green.

The BK `NaN` row is DQ-01, an analytics/reference-data follow-up. It is not a
Wave Viewer UI regression and must not be counted in the pass/fail total.

## P-01 performance acceptance

The current known-good bundle renders patterns again after rollback, but the
bar chart is unacceptably slow. Treat chart and pattern loading speed as a
required product regression, not an optional optimization.

Instrument and report these timings separately:

1. user selection or page-ready to the primary chart-data request starting;
2. primary chart-data request duration;
3. chart-data response completion to the first stable bar-chart canvas;
4. total selection-to-usable-chart time.

Measure one cold authenticated reload and five warm opportunity selections.
Include UNH, PCAR, and FAST where the current baseline makes them available.
Record the browser, served bundle hash, opportunity, cache state, and each
timing rather than reporting only that loading "felt slow."

The acceptance budgets are:

- frontend overhead from chart-data response completion to a usable chart:
  median at or below 500 ms and no sample above 1 second;
- warm selection-to-usable-chart: median at or below 3 seconds and no sample
  above 5 seconds;
- cold authenticated reload to the first usable bar chart: at or below
  10 seconds;
- the primary chart-data request starts immediately and is not gated by
  optional downstream work;
- no stale, mixed-symbol, blank, or permanently Loading chart is accepted.

If the server response is the dominant cost, diagnose the endpoint, query,
payload, caching, and concurrency path instead of hiding the delay in the UI.
Keep the timings split so frontend and backend regressions are not confused.

## Acceptance and terminal conditions

The loop is complete only when all requested Wave Viewer cases pass in two
consecutive clean runs on the same deployed bundle, all P-01 performance
budgets pass in both runs, the baseline is restored at the end of both runs, no
persistent Loading state remains, and no new console, API, data-mixing, or UI
regression is introduced. Only then mark the goal achieved.

Stop and ask the owner only when:

- access to the development host or authenticated browser is unavailable;
- the observed host is not the intended Wave Viewer development environment;
- a repair requires staging, production, TW1, secrets, customer data, billing,
  or destructive work;
- the baseline data has changed and the expected counts can no longer be
  validated;
- the same external blocker remains after safe alternatives are exhausted.

Do not stop merely because one build or test fails. Diagnose, repair, and
continue the loop.

## Prompt for the remote Codex task

Use the complete paste-ready prompt in
`docs/testing/WAVE_VIEWER_REMOTE_GOAL_PROMPT.md`.
