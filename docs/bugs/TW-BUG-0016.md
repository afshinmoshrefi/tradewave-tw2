# TW-BUG-0016: SMN plain bars chart omits a genuine flat year

- Status: in-progress (renderer candidate tested; safe Dev integration in progress)
- Confidence: reproduced in the September 25 AAPL capture; candidate verified in an isolated Dev-host render, not in the active service
- Priority: P2 - a published chart can silently misstate the historical sample and win count
- First observed: 2026-09-25; recorded: 2026-09-26 UTC
- Executor/session/claim time: Codex `/root/fix_flat_bar`, 2026-09-26 19:10 UTC; update: 2026-09-26 19:25 UTC
- Authorization: Afshin requested this SMN fix; implementation, focused tests and Dev verification authorized. Production writes remain unauthorized.

## User Impact and Reproduction

For the September 25 AAPL study, TradeWave returns ten completed observations (1986-2022). The 1986 entry and exit adjusted closes are both 0.1182, with a displayed 0.0% return and intraperiod range +1.85% / -6.89%. The production plain `bars` image omits 1986 and presents nine years (1990-2022), including a "9 of the past 9" claim. The range charts and engine statistics include all ten years. The retained TradeWave response reports `Num Winners=9`, `Num Losers=1`, `Percent Profitable=90.0%`; therefore an earlier claim in this record that 9 of 10 was the *correct winning count* is retracted. Afshin states that a tie should count as a win. The current engine result and implementation conflict with that intended convention, so SMN must not independently relabel the result as 10 wins. Any article with a genuine completed flat year may be affected. The September 25 Dev edition held AAPL at the existing `make_card` validation gate with reason `Engine full sample differs from the published chart`; five other articles passed and AAPL was not published.

## Evidence and Investigation

- Shared publication history and root-cause investigation: [TW-TASK-0005](../tasks/TW-TASK-0005.md), September 25 AAPL hold and root-cause sections.
- Preserved September 25 capture: `/var/lib/tradewave/smn-daily/2026-09-25` on the SMN server. September 26 private comparison: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-claude`. Inspect their state/receipts and source revisions before replay. These are server-local evidence paths, not repository attachments.
- In the affected SMN renderer, `blog/article_images.py` filters placeholder rows using MFE/MAE, then invokes `chartkit.record_bars` for plain bars without those values. `chartkit._drop_zeroed` treats the completed flat row as a placeholder and removes it. The TradeWave engine values are correct; this defect is in SMN chart rendering.
- A proposed, unmerged SMN fix is on `origin/claude/smn-flat-year-bars` at `0971c287546bf65a756f8d7545936c8b9c04ad3f`. It passes `verified_completed=True` for the plain chart and adds a focused test. Inspect and retest it against current SMN `main`; its existence does not establish Dev or production verification.
- The separately retained 2026-09-26 TradeWave response for request `resource_id=2`, `symbol=AAPL`, `anchor_date=2026-10-11`, `days_out=20`, `years=pe2-10` has a completed 1986 row (`pct=0.0,1.85,-6.89`, `price=0.1182,0.1182`) and reports 9 winners/1 loser/90.0%. Current TradeWave `appserver/appserver/appserver.py` classifies long-window values with `x > 0` as winners and `x <= 0` as losers. This confirms a conflict with Afshin's stated tie-as-win convention. The renderer must consume the supplied engine count; an engine correction requires its own agreement and verification.
- The distinct TradeWave engine statistic defect is tracked as [TW-BUG-0017](TW-BUG-0017.md). This SMN record owns the missing bar and renderer fidelity only.

## Acceptance and Regression Checks

Render the captured AAPL study with the candidate fix. The plain bars chart must retain 1986 and show ten years, matching the range charts and engine sample. Its count must come from the same-study TradeWave response; with a flat row, the title must not call that row "higher." Resolve the tie-as-win convention in TradeWave before claiming that a 9/10 or 10/10 winning count is correct. Keep genuine completed flat years, while excluding unfinished/future zero placeholders. Verify an ordinary non-flat study and the other five September 25 articles are unaffected. Preserve TradeWave-supplied values exactly and keep the `make_card` mismatch hold active. After a safe renderer activation and separately authorized production correction, regenerate the affected chart and take a fresh AAPL capture through the normal review gate.

## Implementation and Handoff

The revised renderer candidate is pushed to SMN branch `codex/smn-flat-year-bars-20260926`, commit `5a500cb5927599fb7d4d36b2d0fef074b51c5b46` (based on Claude's `0971c28` via `db29369`). Worktree: `C:\Users\afshin\Documents\TradeWave Main Orchestrator\smn-flat-year-bars-20260926`, clean. `blog/article_images.py` marks its already-filtered plain bar input as `verified_completed` and passes TradeWave's `Num Winners`/`Num Losers`; `blog/chartkit.py` uses that count for article charts, checks its total against completed rows, and uses neutral wording when a flat row exists. `blog/tests/test_chartkit.py` checks both retained flat years and consumption of a supplied count. TradeWave values, engine logic and `engine_seasonal.make_card` were not changed. No config, migration or frontend build is needed.

Focused checks: `python -m unittest blog.tests.test_chartkit blog.tests.test_engine_seasonal -q` (36 passed), Python compile of touched modules and `git diff --check` passed. An isolated run on SMN Dev `.180` used the revised candidate files and all six retained September 25 `production/*/engine-payload.json` files, including each subject's supplied TradeWave counts. AAPL rendered all ten completed years, including 1986 at 0%, with neutral title `TradeWave reports 9 winning years among 10 completed years`; a deliberately appended 2026 `0,0,0` placeholder was excluded. APH, CPRT, F, VIX and XLF retained their original completed-year counts. The revised image was visually inspected: 1986 is labeled at the baseline and the source says `n=10 completed years`. Evidence script and outputs: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-codex-flat-bar` on `.180`; revised AAPL JPEG SHA-256 `55b31a51b13f0f3574fc8e0a61119f04138199374a804468a32a6c7cba356951`. The earlier image hash and directional 9/10 wording are superseded.

The normal Dev activation remains pending. Active services execute `/home/flask/blog` from the old `deterministic-sources` checkout, which contains unrelated modified and untracked work and no isolated source pointer for this renderer. Its September 25 AAPL input still references the incorrect read-only production image, so `make_card` correctly holds publication. No active files, service pointers, article bytes or other September 25 evidence were changed. Next: preserve/classify that live checkout and integrate the exact pushed SMN commit through a safe Dev activation path; verify AAPL with a fresh source capture and the normal review gate after the separately authorized production renderer release. Do not bypass the gate or rerun writer jobs for this code fix.

## Environment Verification

- Dev: revised isolated candidate render verified on `.180` against all six retained payloads; active service not changed and AAPL remains held by the normal gate. TradeWave's tie classification is unresolved against the stated convention.
- Staging: no SMN staging environment established.
- Production: affected plain bars chart observed; fix not deployed or verified. Production remains read-only.

## History

- 2026-09-26: Owner explicitly requested fixing both 0016 and 0017. Codex `flat-return-engine-20260926` coordinates shared records; delegated `/root/smn_flat_bar` claims SMN candidate integration and safe Dev renderer verification. Preserve all dirty `/home/flask` peer changes, existing publication gates and production. Long zero is an engine win; short zero is an engine loss. Exact live source path must be proven before declaring Dev activation.

- 2026-09-26: Afshin clarified that ties should count as wins. Codex found the same-study TradeWave response reports 9 winners/1 loser and current engine code classifies a zero long return as non-winning. Retracted the prior "correct 9 of 10" assertion. Pushed revised SMN renderer `5a500cb5927599fb7d4d36b2d0fef074b51c5b46`, verified engine-count pass-through and neutral flat-row title in isolated Dev, without changing engine math or active services. The intended engine tie convention still needs resolution.
- 2026-09-26: Codex `/root/fix_flat_bar` pushed SMN fix `db29369e4efad1b6188b9e19b48af15318f19828`, passed 36 focused tests and private Dev-host six-subject render, and visually verified the corrected AAPL chart. Active Dev integration remains pending due to unrelated checkout drift and the still-defective production capture.
- 2026-09-26: Codex `/root/fix_flat_bar` claimed the SMN renderer repair in `codex/smn-flat-year-bars-20260926`, worktree `C:\Users\afshin\Documents\TradeWave Main Orchestrator\smn-flat-year-bars-20260926`. Scope: `blog/article_images.py` and focused chart regression tests. Next: inspect/reuse candidate `0971c28`, test with retained AAPL evidence, activate and verify on Dev. No engine calculation or production change.
- 2026-09-26: Codex documentation session created this canonical bug record from the preserved September 25 investigation. Implementation remains unclaimed.
