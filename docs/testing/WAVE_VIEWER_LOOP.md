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

## Source and environment

- Handoff branch: `codex/wave-viewer-regression-loop-20260724`
- Application URL: `https://tw2-dev.trxstat.com/app/`
- Owner-supplied development host: `192.168.1.180`
- Repository path normally used on a TradeWave development host:
  `/home/flask`
- React source: `web-react/`
- React build command: `npm run build`

Do not assume the host topology. On 2026-07-24, a direct HTTP request to
`192.168.1.180` returned the Seasonal Market News vhost, while ports 22 and 80
were open. Before changing anything, confirm the hostname, repository path,
nginx vhost, current branch, worktree status, and the filesystem target serving
`tw2-dev.trxstat.com/app/`. Do not overwrite a dirty server checkout or switch a
symlink until its current target and rollback target have been recorded.

Never request or print a password or secret. Use credentials already available
to the remote task.

## Loop

Run these steps repeatedly without waiting for the owner between ordinary
development iterations:

1. Read `WAVE_VIEWER_CURRENT.md` and inspect the currently served JavaScript
   bundle.
2. Restore and verify the baseline: S&P 500 STOCKS, 10 years, 8 of 10, empty
   filter, 419 opportunities, first UNH, last EQR.
3. Reproduce the remaining failures before editing. Save concise evidence.
4. Diagnose the state transition or data-source error. Add or update a focused
   automated test when the behavior can be isolated.
5. Make the smallest coherent repair. Preserve the Opportunity Table's state
   independently from the Wave Viewer's cycle and years state.
6. Run the focused tests, all React unit tests that can run, and a production
   React build.
7. Deploy the build to development only. Use a new immutable release directory
   and an atomic symlink swap when the host uses the release layout. Preserve
   the previous symlink for rollback. Never copy a partial build over a live
   directory.
8. Hard-refresh the authenticated browser, record the new bundle hash, verify
   the baseline, and retest the repaired cases plus adjacent cases.
9. Update `WAVE_VIEWER_CURRENT.md` and append a dated entry to
   `WAVE_VIEWER_RUN_LOG.md`.
10. Commit and push each verified round to the handoff branch.

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

## Acceptance and terminal conditions

The loop is complete only when all requested Wave Viewer cases pass in two
consecutive clean runs on the same deployed bundle, the baseline is restored at
the end of both runs, no persistent Loading state remains, and no new console
error or UI regression is introduced.

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

> Work autonomously through the TradeWave Wave Viewer development regression
> loop. First read `docs/TRADEWAVE_ECOSYSTEM.md`,
> `docs/testing/WAVE_VIEWER_LOOP.md`, and
> `docs/testing/WAVE_VIEWER_CURRENT.md`. Use branch
> `codex/wave-viewer-regression-loop-20260724`. You may inspect, edit, test,
> build, and deploy to the development environment only. Do not touch staging,
> production, TW1, secrets, billing, authentication, customer data, or DQ-01.
> Confirm that `192.168.1.180` is the correct Wave Viewer host and identify the
> served React build target before writing. Then loop through reproduce,
> diagnose, repair, automated verification, dev deployment, browser retest,
> documentation, commit, and push. Continue until every requested case passes
> twice consecutively on the same bundle or a listed stop condition is met.
