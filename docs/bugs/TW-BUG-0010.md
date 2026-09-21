# TW-BUG-0010: SMN counts an unfinished TradeWave row as historical evidence

- Status: in-progress
- Confidence: reproduced
- Priority: P2 - first fresh scheduled Dev edition is held; no affected new content published
- First observed / last updated: 2026-09-21T11:06:11.427963+00:00
- Executor/session: Codex SMN daily heartbeat 2026-09-21; implementation claimed by Codex smn-completed-observations-20260921
- Authorization: scheduled Dev workflow, read-only diagnosis and documentation. Held edition is not automatically retried. No engine-calculation change authorized.

## User Impact and Reproduction
At SMN source `ee9e7f4af913519c8649d4e68608fa7cf9bd91da`, capture September21 production picks LEN, VIX, CPRT, XLF, APH and GIS and read-only engine exports through the existing transport. Invoke `engine_seasonal.make_card` for the exact original studies with retained prompt and published dataset. Five pass. APH uses resource2, pe2-8, long, start2026-09-18, duration202. Its published chart and retained packet contain eight completed midterm observations 1994 through2022. The live response includes those observations plus a 2026 row explicitly marked `completed: false`, price `77.55,77.55`, pct `0.0,0.0,0.0`.

Expected: the client respects the engine's completed-observation contract while preserving the original cohort and values. Actual: `decode_rows` excludes only current/future rows with price exactly `0,0`. It ignores the authoritative completed flag, counts this nonzero-price unfinished row, and the later full-sample guard raises `Engine full sample differs from the published chart` (9 versus8). This identifies a client interpretation gap, not a demonstrated TradeWave calculation defect. No return was recalculated to diagnose it.

## Evidence and Investigation
[Captured request, response and six-study preflight](evidence/TW-BUG-0010-20260921.json). Full private immutable local source capture: `smn-review-20260919/daily-worker/2026-09-21`, including production archive/hashes, dataset, prompt and engine export. Official engine owner/hash retained in evidence. Confirmed code at SMN `blog/engine_seasonal.py`, `decode_rows` and `make_card`, revision above. Original eight APH row values pass the comparison before the sample-size guard; this does not claim all possible engine metrics are validated. Root cause shown directly by the returned flag and current branch condition.

## Acceptance and Regression Checks
Pending repair review: consume `completed:false` consistently without removing legitimate completed flat years or altering engine values. Validate this exact APH cohort and ordinary future zero-price placeholders, PE/consecutive comparisons and the five passing subjects. Test missing completion metadata against the documented engine contract rather than guessing. Preserve all pre-repair captures. Resume only through explicit recovery with newly bound evidence/jobs as appropriate. No new test, writer or reviewer model calls were run after the gate held; no article layout/publication checks were reached.

## Implementation and Handoff
SMN clean main/worktree `smn-daily-integrated-20260919` at `ee9e7f4af913519c8649d4e68608fa7cf9bd91da`. No application edits or deployment performed. Run is held in `preflight-hold.json`; no fresh articles generated. Research agents were stopped; any partial research is not an approved commission. Next: scope and implement the client completion-flag correction through the normal Dev process, then explicitly recover the date; do not change the engine or silently slice/reaggregate results. Source fixes and fresh editorial jobs remain pending. No configuration/migration/rollback needed for this documentation-only observation.

## Environment Verification
Local worker: reproduced using captured production input and production engine output at timestamp above. Dev new edition: not deployed; approved September17 content remains. Production: read-only capture only, unchanged. Staging: not checked. This report does not assert production SMN is wrong.

## History
- 2026-09-21T11:06:11.427963+00:00: First scheduled complete batch held by source-fidelity gate before writer/reviewer calls. Recorded under TW-TASK-0005. No automatic retry or correction.

## Authorized repair claim
2026-09-21T11:16:12.588858+00:00: Afshin explicitly requested fix it. Correct SMN completion-flag consumption only, preserve engine results, run captured APH/six-study regression, activate and verify Dev. SMN branch codex/smn-completed-observations-20260921, fresh worktree of that name. No production or engine changes.
