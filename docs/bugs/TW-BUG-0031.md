# TW-BUG-0031: Daily pick silently stalls on the V2 scorer

- Status: fixed
- Confidence: reproduced
- Priority: P1. The morning job published no pick after 2026-09-16, exited 0, and the homepage kept presenting that older pick as current.
- First observed / last updated: 2026-10-09T19:48:34Z / implementation update the same day
- Executor/session/claim time: Cursor cloud agent `bc-917a67f2-114d-5687-9799-63084c10fb3b`, claimed 2026-10-09T19:48:34Z
- Authorization: the five CTO outcomes in the task request. Do not upgrade the scorer to V3. Do not backfill picks. Do not deploy to dev, staging, or production.

## User Impact and Reproduction

Preconditions: production ML scorer is V2. `GET /health` returns only `feature_count`, `status`, `tiers`, `uptime_seconds`, and `vix_cutoff`. Cron runs `site/generate_home_page.py` at 07:00 UTC (3:00 AM America/New_York), which calls `site/lib/daily_pattern_picks.py`.

1. `current_pick_data_identity()` required `metadata.data_as_of`, `context_data_complete is True`, and V3 provenance hashes.
2. The V2 payload has none of those fields, so every run since 2026-09-17 logged `Daily pick deferred: scorer data through None does not cover completed session YYYY-MM-DD`.
3. `generate_home_page.py` then logged `Reusing UHS from 2026-09-16 on homepage only` and the process exited 0.

Expected: publish a pick only when end-of-day data for the last completed US equity session is complete from a trustworthy source. If no pick is published, exit non-zero, alert, and show "No pick today". Dates 2026-09-17 through 2026-10-09 stay an empty scorer-outage gap, excluded from track-record stats, with no backdated rows in `featured_history.json`.

Dev (192.168.1.176) still selects picks because that scorer reports provenance. Dev does not reproduce this failure unless `TW2_ML_SCORER_URL` points at a V2 health stub.

## Evidence and Investigation

Confirmed in source. Production was not written or re-probed by this session.

- The deferred sentence is `current_pick_data_identity()` in `site/lib/daily_pattern_picks.py` (added by `ffb5137`).
- `appserver/appserver/ml_checkpoint_context.py` `_legacy_v2_metadata()` already recognizes V2 (`feature_count` 59). Its `data_as_of` is the New York calendar date and `context_data_complete` is false. Those values are cache placeholders, not proof the last completed session is in the data.
- The trustworthy session proof is `data_updater/eod_readiness.py` `validate_success_marker()`, from `TW2_EOD_UPDATE_STATUS_FILE` or appserver `GET /internal/eod-status`.
- Operator email already exists: `web/email_utils.resend_send_email` to `SUPPORT_EMAIL_TO`. It no-ops when Resend is unconfigured. The job now prints that fact and still exits 1.

Decision: reuse `scorer_health_mode()` and `_legacy_v2_metadata()` for the V2 model contract, and bind `data_as_of` plus the data hashes to the validated EOD marker. Do not treat the V2 placeholders as publication proof. Do not upgrade the scorer.

## Acceptance and Regression Checks

Ran with `python3 -m pytest` on 2026-10-09:

- `tests/test_daily_pick_v2_freshness.py`
- `tests/test_home_publication_contract.py`
- `tests/test_ml_checkpoint_context.py`
- `tests/test_eod_readiness.py`
- `tests/test_appserver_client.py::test_track_record_obeys_published_target_exit_and_keeps_close_transparency`

Result: 54 passed, 0 failed, in one combined run after the gap file moved to `site/lib/`. The new file covers the exact V2 `/health` keys (`feature_count` 59, `status` ok, tiers `10_30` / `31_60` / `61_90`, `uptime_seconds` 86400, `vix_cutoff` 35, and no provenance fields), a complete EOD marker, a stale session, an incomplete marker, a missing marker, non-zero exit plus alert, the homepage "No pick today" state without reusing UHS, gap exclusion from `pick_stats` and `track_record()`, and refusal to call the scorer or write history on a gap date.

Not run: live dev or production cron, browser against 192.168.1.176, Resend delivery. Owner said not to deploy.

## Implementation and Handoff

Repository: https://github.com/afshinmoshrefi/tradewave-tw2
Branch: `cursor/daily-pick-v2-freshness-fb3b`
Worktree: `/workspace` (cloud agent; not a `/home/tradewave-worktrees` checkout)
Claim SHA: `d9a92842bcd425667826f23e286b3041bf355534`
Implementation SHA: this record's commit. Read it with `git log -1 -- docs/bugs/TW-BUG-0031.md`.

Changed:

- `appserver/appserver/ml_checkpoint_context.py`: shared `scorer_health_mode()` and `daily_pick_identity_from_health()`. V2 model fields come from `_legacy_v2_metadata()`. Publication data identity comes from a validated EOD marker.
- `site/lib/daily_pattern_picks.py`: the freshness gate calls that helper. V2 loads the EOD marker from the status file or `/internal/eod-status`.
- `site/generate_home_page.py`: no reuse of the previous pick. Missing publication alerts and `main()` returns 1. `sys.exit(main())` so cron sees it.
- `site/lib/operator_alert.py`: Resend email to `SUPPORT_EMAIL_TO`, plus a stderr ERROR when email is not sent.
- `site/lib/pick_stats.py`, scorecard, and `apiserver/appserver_client.py`: gap rows and gap dates stay out of win rate and counts.
- `site/lib/scorer_outage_gaps.json`: 2026-09-17 through 2026-10-09 inclusive. No rows added to `featured_history.json`. `site/data/` is gitignored, so the gap record lives next to `pick_stats.py`.
- Homepage and scorecard templates show the gap notice. The homepage shows "No pick today" when this morning did not publish.
- `tools/simulate_v2_daily_pick_scorer.py`: local V2 `/health` for a dev check. `/select` returns no picks.

Rollback: revert this branch. The gap file is data, not a migration. No schema change.

Next action: do not deploy from this session. On dev, simulate V2 as written in the pull request before any later activation. The first eligible publication date after the recorded gap is 2026-10-12 (Monday). The job does not backfill.

## Environment Verification

Dev: not deployed by this task. Staging: not checked. Production: not checked.

## History

- 2026-10-09T19:48:34Z, Cursor cloud agent `bc-917a67f2-114d-5687-9799-63084c10fb3b`: claimed. Reproduction matches the logged string in `current_pick_data_identity()`.
- 2026-10-09, same session: implemented the V2 gate, loud failure, no-pick homepage state, and outage gap. Focused tests passed. No deploy.
