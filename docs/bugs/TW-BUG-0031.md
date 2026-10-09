# TW-BUG-0031: Daily pick silently stalls on the V2 scorer

- Status: in-progress
- Confidence: reproduced
- Priority: P1. The morning job has published no pick since 2026-09-16, exits 0, and the homepage keeps presenting that older pick as current. That is a silent change of what the public ledger claims.
- First observed / last updated: 2026-10-09T19:48:34Z
- Executor/session/claim time: Cursor cloud agent `bc-917a67f2-114d-5687-9799-63084c10fb3b`, claimed 2026-10-09T19:48:34Z
- Authorization: implement the five CTO outcomes in the task request. Do not upgrade the scorer to V3. Do not backfill picks. Do not deploy to dev, staging, or production.

## User Impact and Reproduction

Preconditions: production ML scorer is V2. `GET /health` returns only `feature_count`, `status`, `tiers`, `uptime_seconds`, and `vix_cutoff`. Cron runs `site/generate_home_page.py` at 07:00 UTC (3:00 AM ET), which calls `site/lib/daily_pattern_picks.py`.

1. `current_pick_data_identity()` requires `metadata.data_as_of`, `context_data_complete is True`, and V3 provenance hashes.
2. The V2 payload has none of those fields, so every run since 2026-09-17 logs `Daily pick deferred: scorer data through None does not cover completed session YYYY-MM-DD`.
3. `generate_home_page.py` then logs `Reusing UHS from 2026-09-16 on homepage only. featured_history.json NOT updated` and the process exits 0.

Expected: a pick is published only when end-of-day data for the last completed US equity session is complete from a trustworthy source. If no pick is published, the job exits non-zero, alerts, and the homepage says no pick today. Dates 2026-09-17 through 2026-10-09 stay an empty scorer-outage gap, excluded from track-record stats, with no backdated rows in `featured_history.json`.

Actual: no ledger row after 2026-09-16, homepage reuse, exit 0. Dev (192.168.1.176) still selects picks (latest reported EME on 2026-10-06) because that scorer reports provenance. Dev does not reproduce this failure on its own.

## Evidence and Investigation

Confirmed in source, not by a production write:

- `site/lib/daily_pattern_picks.py` `current_pick_data_identity()` is the exact deferred message.
- Commit `ffb5137` added that gate. It assumes scorer `/health` carries V3 provenance.
- `appserver/appserver/ml_checkpoint_context.py` `_legacy_v2_metadata()` already recognizes V2 (`feature_count` 59) and builds a cache identity. That identity sets `context_data_complete` to false and `data_as_of` to the New York calendar date. Those placeholders are not proof that the last completed session is in the data.
- The trustworthy session proof already exists: `data_updater/eod_readiness.py` `validate_success_marker()`, fed by `/var/lib/tradewave/eod/update_status.json` or the appserver `GET /internal/eod-status`.
- `site/generate_home_page.py` reuses `history[-1]` when selection returns None, and `main()` does not `sys.exit` with that failure.
- Operator email already exists as `web/email_utils.resend_send_email` to `SUPPORT_EMAIL_TO`. It no-ops when Resend is unconfigured.

Hypothesis from the task, now matched to code: the prod V2 health payload cannot satisfy the V3 provenance gate. Not yet rechecked against the live prod process in this session.

## Acceptance and Regression Checks

- Exact V2 `/health` payload is accepted only when a validated EOD success marker covers `latest_completed_us_equity_session()`.
- Stale or incomplete EOD data is refused and `/select` is not called.
- V3 provenance behavior stays as it is.
- No published pick: non-zero exit, operator alert attempted, homepage renders "No pick today" and does not reuse the prior symbol as today's pick.
- 2026-09-17 through 2026-10-09 is a visible scorer-outage notice and is excluded from win rate and counts. No backdated pick is written.
- Tests not run yet: pending implementation.

## Implementation and Handoff

Repository: https://github.com/afshinmoshrefi/tradewave-tw2
Branch: `cursor/daily-pick-v2-freshness-fb3b`
Worktree: `/workspace` (cloud agent; not a `/home/tradewave-worktrees` checkout)
SHA: pending this claim commit
Next step: share `ml_checkpoint_context` V2 detection, bind publication to `validate_success_marker`, fail the homepage job loudly, record the outage gap, add tests. Do not deploy.

## Environment Verification

Dev: not deployed by this task (owner: do not deploy). Staging: not checked. Production: not checked.

## History

- 2026-10-09T19:48:34Z, Cursor cloud agent `bc-917a67f2-114d-5687-9799-63084c10fb3b`: claimed. Reproduction matches the logged string in `current_pick_data_identity()`. Implementation next. No deploy.
