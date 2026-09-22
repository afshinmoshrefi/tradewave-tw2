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

Confirmed immediate cause: scorer rejects inconsistent prebuilt versus dynamically recalculated historical model inputs for the 60-day checkpoint. Both select best combo 9_7_PE2, but counts and two model fields differ. Follow-up localized the discrepancy to a break-even observation; the proposed strict-positive fix was retracted after owner clarification below. No evidence supports bypassing validation or substituting a score. The 30/60/70 windows are separately evaluated, so one can fail while its neighbors remain available. This predates and is independent of TW-BUG-0012's presentation change. Current UI generic temporary wording understates the structured non-retryable profile failure.

## Acceptance and Regression Checks

Further authorized repair must establish why the profile sets differ, preserve TradeWave/scorer calculation authority, and reconcile the authoritative inputs. Verify fresh 30/60/70-day receipts for this identical study, cache behavior, and neighboring durations. A refresh alone is not a repair: a fresh scorer request reproduces the failure. Never interpolate or disable the mismatch guard. Discuss any proposed engine mathematical change with the owner before implementation.

## Implementation and Handoff

Documentation only on codex/lrcx-60day-investigation-20260922, worktree /home/tradewave-worktrees/lrcx-60day-investigation-20260922. Record commit discoverable with git log -1 -- docs/bugs/TW-BUG-0013.md. Files: this record and index. No runtime, config, cache, dependency or model edits; no build/deployment required. Next action: when repair is authorized, investigate scorer prebuilt-profile construction against dynamic qualifying sets for LRCX September 22 / 60 days, using the recorded source/data identity. Scorer access uses the existing dev configuration; never print credentials.

## Environment Verification

Dev reproduced 2026-09-22T15:06:17.676397+00:00 via Chrome, Redis and direct scorer response. Staging and production not checked. No deployment by this task. No tests run because no code changed.

## History

- 2026-09-22T15:06:17.676397+00:00: Codex documented independent current-condition checkpoint failure and its exact provider reason.

## Localized Discrepancy - Earlier Interpretation Retracted

Owner requested tracing the actual bug rather than stopping at an input-mismatch description. Read-only inspection of standalone dev scorer 192.168.1.215 shows active release /home/flask/.ml-scorer-releases/4d6470dff5dde891154542f16b68d05d92414003.

`ml_scorer/feature_engine.py:_combo_row_from_observations` line 963 checks `np.sum(returns >= 0.0)`. This counts a flat return as a winning year. The exact extra qualifying key is `10_9_PE2`; there are no prebuilt-only keys. Its ten completed midterm-year observations, returned by the existing scorer engine, are:

1986: 0.00%; 1990: 28.12%; 1994: 6.76%; 1998: 73.22%; 2002: 55.23%; 2006: 36.85%; 2010: 19.78%; 2014: 4.92%; 2018: -7.30%; 2022: 16.37%.

1986 is an exact break-even in the scorer source CSV, not merely percentage display rounding: adjusted close 0.0943 on both September 22 and November 20. That yields eight positive years, one negative year, one zero year. Stored `10_8_PE2` exists; `10_9_PE2` does not.

Supporting generator-source inspection: local C:/seasonals/combine4 (3).ipynb, functions collection_matrix_by_year and create_long_short_seasonals, maps strictly positive raw price differences to +1, negative differences to -1, and leaves zero unchanged. It then sums positive indicators for long qualification. This local notebook is a historical source copy, not proof of current generator deployment; the actual stored qualifying rows independently support the strict-positive rule.

Diagnostic method: ran the existing FeatureEngine.compute_recalculated_pattern_profile in a separate Python process, using sys.settrace to inspect its locals at the existing mismatch exception. No live module, file, cache, service or model was changed. Captured dynamic-only key was `10_9_PE2`. Removing only that key from an in-memory diagnostic copy of dynamic_rows and invoking the existing engine _aggregate_pattern_profile/_profile_value_differences produced remaining_sets_identical=true and remaining_model_differences=[] under the existing validation tolerances. No substitute AI score was produced or served.

Proposed repair: align the scorer's win qualification with the authoritative generator (strictly favorable raw return, before presentation rounding); retain the profile-integrity guard. Audit the similar `>= 0.0` in compute_selected_recurrence_summary at line 905 and small-return rounding semantics. Do not silently broaden this into an engine methodology change. Owner agreement is required by calculation-authority policy before changing mathematical behavior. Current request was to identify the bug; no scoring code was changed. Regression should include this exact 1986 flat case, short-direction break-even, and small nonzero returns that round to zero. Verify all 30/60/70-day provider outputs after any approved repair.

- 2026-09-22T15:12:49.142386+00:00: Confirmed root cause and isolated counterfactual using existing scorer methods; no runtime writes. Next action is agreement on aligning scorer qualification, then a dedicated scorer worktree and focused repair/release workflow.

## Owner Correction - Break-Even Semantics

Afshin clarified that a break-even observation IS a long win and IS a short loss. This overrides the historical notebook inference. The earlier claim that long-side `>= 0` was incorrect and the proposed strict-positive long fix are RETRACTED. The diagnostic proved only that the extra `10_9_PE2` row causes the validation failure; it did not establish which source violated intended methodology.

Continue tracing the stored profile and original observation precision/data lineage. The scorer currently negates short returns then uses `>= 0` for both directions, which conflicts with the clarified short break-even rule and needs a separately scoped evaluation. No mathematical code was changed. Canonical win rule: original signed price return >= 0 is a long win, original signed price return < 0 is a short win; a displayed rounded zero does not establish an exact break-even.
