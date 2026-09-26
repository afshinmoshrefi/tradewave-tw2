# TW-BUG-0016: SMN plain bars chart omits a genuine flat year

- Status: fixed (pushed task branch; live Dev integration pending)
- Confidence: reproduced in the September 25 AAPL capture; candidate verified in an isolated Dev-host render, not in the active service
- Priority: P2 - a published chart can silently misstate the historical sample and win count
- First observed: 2026-09-25; recorded: 2026-09-26 UTC
- Executor/session/claim time: Codex `/root/fix_flat_bar`, 2026-09-26 19:10 UTC; update: 2026-09-26 19:17 UTC
- Authorization: Afshin requested this SMN fix; implementation, focused tests and Dev verification authorized. Production writes remain unauthorized.

## User Impact and Reproduction

For the September 25 AAPL study, TradeWave returns ten completed observations (1986-2022). The 1986 entry and exit adjusted closes are both 0.1182, yielding a genuine 0.0% return, while its intraperiod range is +1.85% / -6.89%. The production plain `bars` image omits 1986 and presents nine years (1990-2022), including a "9 of the past 9" claim. The range charts and engine statistics include all ten years, so the correct cohort claim is 9 of 10. Any article with a genuine completed flat year may be affected. The September 25 Dev edition held AAPL at the existing `make_card` validation gate with reason `Engine full sample differs from the published chart`; five other articles passed and AAPL was not published.

## Evidence and Investigation

- Shared publication history and root-cause investigation: [TW-TASK-0005](../tasks/TW-TASK-0005.md), September 25 AAPL hold and root-cause sections.
- Preserved September 25 capture: `/var/lib/tradewave/smn-daily/2026-09-25` on the SMN server. September 26 private comparison: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-claude`. Inspect their state/receipts and source revisions before replay. These are server-local evidence paths, not repository attachments.
- In the affected SMN renderer, `blog/article_images.py` filters placeholder rows using MFE/MAE, then invokes `chartkit.record_bars` for plain bars without those values. `chartkit._drop_zeroed` treats the completed flat row as a placeholder and removes it. The TradeWave engine values are correct; this defect is in SMN chart rendering.
- A proposed, unmerged SMN fix is on `origin/claude/smn-flat-year-bars` at `0971c287546bf65a756f8d7545936c8b9c04ad3f`. It passes `verified_completed=True` for the plain chart and adds a focused test. Inspect and retest it against current SMN `main`; its existence does not establish Dev or production verification.

## Acceptance and Regression Checks

Render the captured AAPL study with the candidate fix. The plain bars chart must retain 1986 and show ten years, matching range charts, engine statistics and prose; the winning-year claim must be 9 of 10. Keep genuine completed flat years, while excluding unfinished/future zero placeholders. Verify an ordinary non-flat study and the other five September 25 articles are unaffected. Preserve TradeWave-supplied values exactly and keep the `make_card` mismatch hold active. After the renderer passes focused tests and Dev verification, regenerate the affected chart and take a fresh AAPL capture through the normal review gate. Tests and live checks for this bug have not been run by this documentation session.

## Implementation and Handoff

The repair is pushed to SMN branch `codex/smn-flat-year-bars-20260926`, commit `db29369e4efad1b6188b9e19b48af15318f19828` (a clean cherry-pick of Claude's `0971c28` onto SMN `40ef249`). Worktree: `C:\Users\afshin\Documents\TradeWave Main Orchestrator\smn-flat-year-bars-20260926`, clean. `blog/article_images.py` marks its already-filtered plain bar input as `verified_completed`; `blog/tests/test_chartkit.py` checks the completed flat-year count. TradeWave values and `engine_seasonal.make_card` were not changed. No config, migration or frontend build is needed.

Focused checks: `python -m unittest blog.tests.test_chartkit -v` (26 passed), `python -m unittest blog.tests.test_engine_seasonal -q` (10 passed), Python compile of the touched modules and `git diff --check` passed. An isolated run on SMN Dev `.180` used the pushed candidate files and each of the six retained September 25 `production/*/engine-payload.json` files. AAPL rendered all ten completed years, including 1986 at 0%, with `higher in 9 of 10 midterm election years`; a deliberately appended 2026 `0,0,0` placeholder was excluded. APH, CPRT, F, VIX and XLF retained their original completed-year counts. The image was visually inspected: 1986 is labeled at the baseline and the source says `n=10 completed years`. Evidence script and outputs: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-codex-flat-bar` on `.180`; rendered AAPL JPEG SHA-256 `4a361f0131a9b3a1c772d1f0b013bc970cab33bc2cd8d2a7a4c873fb4452c5da`.

The normal Dev activation remains pending. Active services execute `/home/flask/blog` from the old `deterministic-sources` checkout, which contains unrelated modified and untracked work and no isolated source pointer for this renderer. Its September 25 AAPL input still references the incorrect read-only production image, so `make_card` correctly holds publication. No active files, service pointers, article bytes or other September 25 evidence were changed. Next: preserve/classify that live checkout and integrate the exact pushed SMN commit through a safe Dev activation path; verify AAPL with a fresh source capture and the normal review gate after the separately authorized production renderer release. Do not bypass the gate or rerun writer jobs for this code fix.

## Environment Verification

- Dev: isolated candidate render verified on `.180` against all six retained payloads; active service not changed and AAPL remains held by the normal gate.
- Staging: no SMN staging environment established.
- Production: affected plain bars chart observed; fix not deployed or verified. Production remains read-only.

## History

- 2026-09-26: Codex `/root/fix_flat_bar` pushed SMN fix `db29369e4efad1b6188b9e19b48af15318f19828`, passed 36 focused tests and private Dev-host six-subject render, and visually verified the corrected AAPL chart. Active Dev integration remains pending due to unrelated checkout drift and the still-defective production capture.
- 2026-09-26: Codex `/root/fix_flat_bar` claimed the SMN renderer repair in `codex/smn-flat-year-bars-20260926`, worktree `C:\Users\afshin\Documents\TradeWave Main Orchestrator\smn-flat-year-bars-20260926`. Scope: `blog/article_images.py` and focused chart regression tests. Next: inspect/reuse candidate `0971c28`, test with retained AAPL evidence, activate and verify on Dev. No engine calculation or production change.
- 2026-09-26: Codex documentation session created this canonical bug record from the preserved September 25 investigation. Implementation remains unclaimed.
