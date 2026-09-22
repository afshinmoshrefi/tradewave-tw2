# TW-BUG-0013: LRCX 60-Day AI Checkpoint Fails Profile Validation

- Status: open
- Confidence: reproduced
- Priority: P2, missing current eligible AI checkpoint
- First observed / last updated: 2026-09-22T15:06:17.676397+00:00
- Executor/session: Codex lrcx-60day-investigation-20260922; implementation unclaimed
- Authorization: investigate and document; no engine changes or deployment

## User Impact and Reproduction

Dev URL: https://tw2-dev.trxstat.com/app/?o=MXxMUkNYfDIwMjYtMDktMjJ8NzB8MTA%3D
LRCX, NASDAQ 100 resource 1, September 22, 2026 entry, 70 inclusive calendar days, long, 10 consecutive years. The AI panel shows 30 and 70 days with scores but the 60-day card says Temporarily unavailable and contains dashes. Entry is today, so the five-day date gate is not the cause. Browser observed data through September 21, 2026.

## Evidence and Investigation

Active backend: 05ae209ecaba231e5816f835dc133f7c0cdf00e8. Frontend artifact: 4a0c34355f98bc44dc61b7cc12cfebba2e65848d. Shared main at investigation start: 9139a6c7. A new Chrome tab reproduced the user's report.

Read-only Redis lookup through the engine's build_checkpoint_plan/read_cached_checkpoint confirmed 30 days available and 60 days unavailable with prebuilt_profile_mismatch, retryable=false. A fresh direct POST to the configured scorer /score/context reproduced the same error independently of the app cache (HTTP 200 with per-item failure). Request used resource_id=1, symbol=LRCX, date=2026-09-22, calendar_days=30/60, direction=l, years='10', partial={selection:null,mode:consecutive,requested_years:'10'}.

Retained exact diagnostic fields from the 60-day scorer response:

```json
{"status":"unavailable","tier":"31_60","error":{"code":"prebuilt_profile_mismatch","retryable":false,"details":{"dynamic_best_combo":"9_7_PE2","dynamic_combo_count":28,"mismatched_model_fields":["pat_num_combos_qualifying","pat_best_winrate"],"model_values_match":false,"prebuilt_best_combo":"9_7_PE2","prebuilt_combo_count":27,"qualifying_sets_match":false}}}
```

Scorer identity: model_release=v3-22sage-20260802-03, feature_schema_version=v3-62, context_schema_version=duration-comparison-context-v5, pattern_profile_schema_version=all-qualifying-combos-v2, data_as_of=2026-09-21, context_data_complete=true, missing_context_data_sources=[]. Data generation hash: 823566e1891059af980791f71ff6e760d864b50d369060341f606acfd1bff6ee. Fresh 30-day win_prob=0.7968, ml_score=87.5. The browser displays 30-day AI Win Chance 80% and 70-day 72%; the 70-day raw response was not captured.

Confirmed immediate cause: scorer rejects inconsistent prebuilt versus dynamically recalculated historical model inputs for the 60-day checkpoint. Both select best combo 9_7_PE2, but counts and two model fields differ. Underlying origin (data generation, profile construction, date conventions or another defect) is not yet established. No evidence supports bypassing validation or substituting a score. The 30/60/70 windows are separately evaluated, so one can fail while its neighbors remain available. This predates and is independent of TW-BUG-0012's presentation change. Current UI generic temporary wording understates the structured non-retryable profile failure.

## Acceptance and Regression Checks

Further authorized repair must establish why the profile sets differ, preserve TradeWave/scorer calculation authority, and reconcile the authoritative inputs. Verify fresh 30/60/70-day receipts for this identical study, cache behavior, and neighboring durations. A refresh alone is not a repair: a fresh scorer request reproduces the failure. Never interpolate or disable the mismatch guard. Discuss any proposed engine mathematical change with the owner before implementation.

## Implementation and Handoff

Documentation only on codex/lrcx-60day-investigation-20260922, worktree /home/tradewave-worktrees/lrcx-60day-investigation-20260922. Record commit discoverable with git log -1 -- docs/bugs/TW-BUG-0013.md. Files: this record and index. No runtime, config, cache, dependency or model edits; no build/deployment required. Next action: when repair is authorized, investigate scorer prebuilt-profile construction against dynamic qualifying sets for LRCX September 22 / 60 days, using the recorded source/data identity. Scorer access uses the existing dev configuration; never print credentials.

## Environment Verification

Dev reproduced 2026-09-22T15:06:17.676397+00:00 via Chrome, Redis and direct scorer response. Staging and production not checked. No deployment by this task. No tests run because no code changed.

## History

- 2026-09-22T15:06:17.676397+00:00: Codex documented independent current-condition checkpoint failure and its exact provider reason.
