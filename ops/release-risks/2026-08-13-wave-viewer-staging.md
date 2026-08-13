# Wave Viewer staging out-of-band state - 2026-08-13

This is a dated evidence record, not permanent environment truth and not authorization to change a server. Reverify every item read-only before the next release and copy still-current blockers into that release manifest.

## Observed state

Read-only inspection on 2026-08-13 found staging intentionally differs from `origin/main` at `82c1dd5e1ea0fdea9af107cef8eab435c82827e1`:

- Dev worktree `/home/flask/.tw2-release-waveviewer-staging-20260812` is on local-only branch `fix/viewer-primary-chart-loading-20260812`. It was clean but not pushed.
- Commit `a041a72fc7f3679f8ee30707cd53a00dd73168c1` clears `primaryChartLoading` on every load outcome.
- Commit `119f66cbb5d7e3af2388ae03e2642b1f23cfe888` restores the Gain-Loss Bar Chart render lost during integration.
- Commit `ebf74522ebfd100fa26ec26853c0610df3475763` derives date-lock "today" from the US market timezone rather than the host timezone.
- Stage-app checkout remains at `82c1dd5e1ea0fdea9af107cef8eab435c82827e1` with a tracked modification to `appserver/appserver/appserver.py`. The `_market_today()` change was applied directly on that server.
- `tradewave-appserver` had no active drop-ins at inspection time and ran with working directory `/home/flask/appserver/appserver`. Earlier release-pointer drop-ins had been disabled out of band.
- Stage-web checkout remains at `82c1dd5e1ea0fdea9af107cef8eab435c82827e1`, while its active frontend points to `/home/flask/web-react/releases/build-119f66cbb5d7` and serves `main.1746cfc2.js`.
- Active staging bundle SHA-256 was `8834177aad7bb7256b32822c4562459af59a6b6d94fb2fc9d249301f86217747`.
- The prior frontend pointer was `/home/flask/web-react/releases/build-a041a72fc7f3`.

Promoting current `origin/main` to staging without reconciliation would overwrite or bypass these fixes and can restore blank-chart behavior.

## Other reported risks to reverify

- `ops/deploy.sh` and the release-pointer activation model conflict. A deploy can update `/home/flask` while an effective systemd drop-in continues running an older `.tw2-app-current` release.
- `verify_deploy.sh` can report `CLEAN` without proving the live backend path or rendered chart behavior.
- Staging's scheduled `TW2_UPDATE_SERVER` was reported to use a public updater that returned HTTP 403 from Kamatera. Classify the configured endpoint without printing it and verify reachability before relying on the next schedule.
- Staging intentionally carries only US and INDX data. Eight other market symbol lists are absent by design and can make the updater's aggregate status `ok:false` even when US and INDX succeed.

## Required disposition before promotion

1. Preserve and push the three exact commits on a reviewed task branch.
2. Integrate them into the clean baseline-reconciliation candidate and make `origin/main` equal that candidate before staging promotion.
3. Replace the hand-applied stage-app modification with the exact committed source through the chosen single runtime model.
4. Resolve the base-unit versus release-pointer deployment model in reviewed code and verify every release-managed unit and live process path.
5. Record a concrete staging backend rollback SHA or pointer and command, not only the frontend `build-previous` pointer.
6. Run the level-1 US/INDX date contract and rendered browser chart assertions after activation.
7. Keep this record unresolved until the release manifest contains evidence for each disposition.
