# TW-BUG-0017: TradeWave counts a flat long return as a loss

- Status: open
- Confidence: reproduced in a retained same-study TradeWave response and traced to current engine code; the `.176` website has not been rechecked
- Priority: P2 — winner/loser and win-rate statistics can contradict the intended tie convention
- First observed: 2026-09-25; recorded: 2026-09-26 19:42 UTC
- Executor/session/claim time: unassigned for implementation; Codex `/root/fix_flat_bar` recorded the bug 2026-09-26 UTC
- Authorization: documentation only; no calculation change or deployment authorized

## User Impact and Reproduction

Affected target: TradeWave Dev at `https://tw2-dev.trxstat.com` (`192.168.1.176`). Afshin states that a **long** study's 0% tie counts as a win; a **short** study's 0% tie counts as a loss. This is the intended convention to preserve when the engine is repaired. The `.176` browser/API was not rerun for this record, so current website behavior there is pending direct verification.

Retained request: `resource_id=2`, `symbol=AAPL`, `anchor_date=2026-10-11`, `days_out=20`, `years=pe2-10`, `Trade Dir=long`. The completed 1986 row is `pct=0.0,1.85,-6.89`, `price=0.1182,0.1182`. The ten completed rows contain nine positive displayed returns and this flat return. TradeWave reports `Num Winners=9`, `Num Losers=1`, `Percent Profitable=90.0%`. Under the stated long-tie convention, the flat row should be counted on the winning side. The recorded response is from the September 25 capture preserved on SMN Dev `.180`; its exact request and values establish the engine-output discrepancy without claiming a fresh `.176` website reproduction.

## Evidence and Investigation

- Retained response: `/var/lib/tradewave/smn-daily/comparisons/2026-09-26-claude/production-engine-export.json` on SMN Dev `.180`, `studies[AAPL]`, primary `pe2-10` response; `captured_at=2026-09-25T11:36:04.947292+00:00`. The related retained article payload is `/var/lib/tradewave/smn-daily/2026-09-25/production/AAPL/engine-payload.json`. These server-local files require `.180` access; they are not repository attachments.
- In TradeWave `appserver/appserver/appserver.py` at main `94f0a08ee2be49c01032f914e28fb0833f8c2102` (file last changed in `05ae209ecaba231e5816f835dc133f7c0cdf00e8`), `p` is rounded to two decimals before entering `pctArray` (around line 4175). Long direction selection treats `x >= 0` as positive (around line 4264), but the long statistics branch counts winners with `x > 0` and losers with `x <= 0` (around lines 4290–4291). The short branch already counts `x < 0` as winners and `x >= 0` as losers (around lines 4278–4279). This source path explains the retained AAPL result; a live `.176` runtime/source parity check remains pending.
- Related but separate: [TW-BUG-0016](TW-BUG-0016.md) concerns SMN omitting the genuine flat bar. SMN must consume TradeWave's supplied numerical results, so this engine statistic cannot be silently corrected in the article/chart renderer.

## Acceptance and Regression Checks

For the exact AAPL study, verify the engine's completed 1986 row remains 0.0% and the long winner/loser and win-rate fields follow Afshin's tie-as-win convention. Exercise a completed short 0% row to ensure it remains on the losing side; also check positive, negative and unfinished placeholder rows. Compare the `.176` website/API display with the same engine response and study identity. Preserve TradeWave's sole calculation authority. No tests or `.176` browser checks were run for this documentation-only record.

## Implementation and Handoff

Canonical repository: `tradewave-tw2`, branch `codex/tw-bug-0017-tie-20260926`, worktree `C:\Users\afshin\Documents\tw-bug-0017-record-20260926`. This record and the index/cross-link are the only intended changes; no application files, configuration, migration, build or environment were changed. Implementation owner and commit: pending. Next action: claim the engine repair, confirm current `.176` runtime parity, then propose the calculation change to Afshin for agreement under TradeWave's calculation-authority rule before editing engine mathematics. Test and release under the normal TradeWave workflow.

## Environment Verification

- Dev `.176`: affected website named by Afshin; direct current browser/API reproduction and runtime SHA not checked in this documentation session.
- SMN Dev `.180`: retained TradeWave response reviewed; this is evidence storage, not an SMN calculation fix.
- Staging: not checked.
- Production: not checked; no writes authorized.

## History

- 2026-09-26: Afshin clarified the intended long-tie win convention while reviewing [TW-BUG-0016](TW-BUG-0016.md) and requested a discoverable `.176` bug record. Codex recorded the separate engine issue with retained response and source evidence; repair remains unclaimed.
