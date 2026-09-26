# TW-BUG-0017: TradeWave counts a flat long return as a loss

- Status: verified on dev (API); production not deployed
- Confidence: reproduced before repair and verified after repair through the live Dev HTTPS API; automated browser capture blocked by outdated panel selector
- Priority: P2 — winner/loser and win-rate statistics can contradict the intended tie convention
- First observed: 2026-09-25; recorded: 2026-09-26 19:42 UTC
- Executor/session/claim time: Codex `flat-return-engine-20260926`, 2026-09-26 UTC
- Authorization: Afshin explicitly requested fixing TW-BUG-0016 and TW-BUG-0017 on 2026-09-26 after confirming that zero is a long win and a short loss. Engine repair and dev completion authorized; staging/production excluded.

## User Impact and Reproduction

Affected target: TradeWave Dev at `https://tw2-dev.trxstat.com` (`192.168.1.176`). Afshin states that a **long** study's 0% tie counts as a win; a **short** study's 0% tie counts as a loss. This is the intended convention to preserve when the engine is repaired. Live API verification is recorded below; browser screenshot verification remains limited by the capture harness.

Retained request: `resource_id=2`, `symbol=AAPL`, `anchor_date=2026-10-11`, `days_out=21` (inclusive; URL path segment `20`), `years=pe2-10`, `Trade Dir=long`. The completed 1986 row is `pct=0.0,1.85,-6.89`, `price=0.1182,0.1182`. The ten completed rows contain nine positive displayed returns and this flat return. TradeWave reports `Num Winners=9`, `Num Losers=1`, `Percent Profitable=90.0%`. Under the stated long-tie convention, the flat row should be counted on the winning side. The recorded response is from the September 25 capture preserved on SMN Dev `.180`; its exact request and values establish the engine-output discrepancy without claiming a fresh `.176` website reproduction.

## Evidence and Investigation

- Retained response: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-claude/production-engine-export.json` on SMN Dev `.180`, `studies[AAPL]`, primary `pe2-10` response; `captured_at=2026-09-25T11:36:04.947292+00:00`. The related retained article payload is `/var/lib/tradewave/smn-daily/2026-09-25/production/AAPL/engine-payload.json`. These server-local files require `.180` access; they are not repository attachments.
- In TradeWave `appserver/appserver/appserver.py` at main `94f0a08ee2be49c01032f914e28fb0833f8c2102` (file last changed in `05ae209ecaba231e5816f835dc133f7c0cdf00e8`), `p` is rounded to two decimals before entering `pctArray` (around line 4175). Long direction selection treats `x >= 0` as positive (around line 4264), but the long statistics branch counts winners with `x > 0` and losers with `x <= 0` (around lines 4290–4291). The short branch already counts `x < 0` as winners and `x >= 0` as losers (around lines 4278–4279). This source path explains the retained AAPL result; the live `.176` runtime/source check is recorded below.
- Related but separate: [TW-BUG-0016](TW-BUG-0016.md) concerns SMN omitting the genuine flat bar. SMN must consume TradeWave's supplied numerical results, so this engine statistic cannot be silently corrected in the article/chart renderer.

## Acceptance and Regression Checks

For the exact AAPL study, verify the engine's completed 1986 row remains 0.0% and the long winner/loser and win-rate fields follow Afshin's tie-as-win convention. Exercise a completed short 0% row to ensure it remains on the losing side; also check positive, negative and unfinished placeholder rows. Compare the `.176` website/API display with the same engine response and study identity. Preserve TradeWave's sole calculation authority. Current regression and Dev evidence are recorded below.

## Implementation and Handoff

Engine commit `585b668ed701a10853542785d94a7f09d11413d1` is on main and active on Dev. The long partition now uses `>= 0` winners and `< 0` losers. Short behavior, existing rounding and row membership are unchanged. ChartData4 cache namespace advances from v2 to v3 so cached old classifications cannot survive activation. No migration or frontend build required.

Focused real-function tests: old code failed the three long-tie checks; corrected code passes all nine tests in `tests/test_chartdata_evidence.py`, covering flat/mixed long and short samples, unfinished/future placeholders and existing window/history evidence.

## Environment Verification

- Dev `.176`: active clean backend `/home/tradewave-worktrees/flat-return-release-585b668`, exact engine commit above. Previous pointer `/home/tradewave-worktrees/tw2-20260915-01` at `05ae209e` is retained for rollback. Only `tradewave-appserver.service` restarted; frontend artifact preserved. Existing frontend shell/manifest check passed. Activation lock released.
- Live HTTPS `/appserver/ChartData4/2/2026-10-11/AAPL/20/pe2-10?exact_window=1&comparison_direction=long` returned 9 winners/1 loser/90% before and 10/0/100% after. The response identifies 21 inclusive days, correcting the earlier record's 20-day label. All chart rows are byte-equivalent as parsed JSON. The 1986 row is still 0%, prices 0.1183/0.1183; current data differs slightly from retained production prices.
- Short version remains 0 winners/10 losers/0%, with every statistic and row unchanged. A separate 20-inclusive-day study (URL path `19`) remains 7/3 long and 3/7 short; all statistics and rows unchanged.
- Long winning-bucket average correctly changes 7.26% to 6.54% when the flat winner joins that bucket. Overall returns/excursions/sample membership are unchanged. Empty losing-bucket average formats as `0%` instead of `0.0%`.
- Evidence: [before](evidence/TW-BUG-0017/dev-before-long.json), [after](evidence/TW-BUG-0017/dev-after-long.json). Requests used the existing capture-bot login without storing credentials.
- Browser screenshot verification attempted with existing capture harness, but it stopped at `bottom panel dot "Wave Stats" not found`; no screenshot/UI verification claimed. Direct live API verification passed.
- Staging and production: no writes; repair not deployed there.

## History

- 2026-09-26: Codex `flat-return-engine-20260926` claims the TradeWave engine repair in branch `codex/flat-return-engine-20260926`, Windows worktree `TradeWave Main Orchestrator/flat-return-engine-20260926`, with remote test/activation worktree to match. Scope: ChartData4 long winner/loser partition, focused regressions and exact-study dev/API verification. Preserve row/sample membership, short tie-loss behavior and existing return precision. Related SMN renderer integration is coordinated separately under TW-BUG-0016; no model/generator-methodology change.

- 2026-09-26: Afshin clarified the intended long-tie win convention while reviewing [TW-BUG-0016](TW-BUG-0016.md) and requested a discoverable `.176` bug record. Codex recorded the separate engine issue with retained response and source evidence; repair remains unclaimed.
