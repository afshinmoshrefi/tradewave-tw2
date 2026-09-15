# TW-BUG-0002: The Right Resize Edge Can Change the Duration Without a Drag

- Status: in-progress
- Confidence: reproduced
- Priority: P1 (viewer failure or silent change of user intent)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: Claude Code (claude-opus-5), session ac415bed-b1cf-4689-be18-536911d44893; claimed 2026-09-15T21:01Z; branch `claude/tw-bug-0002-right-resize-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0002-right-resize-20260915`; recorded by Codex, shared-bug-memory-20260915
- Authorization: Afshin authorized the fix on 2026-09-15 ("fix codex's recommended 2 bugs first"); fast dev completion only, no staging/production
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
**Priority: high.** Select AAPL, choose **Buy & Hold**, turn **Jan-Dec** off, then press and release the right resize handle without moving it. The tested duration changed from **366 to 351 days**. The opportunity end date and its statistics changed with it.

A second check started with a fully visible 30-day opportunity. Moving the right handle ten date positions produced **39 days**, although the intended result was 40. The handler derives the entire duration from the overlay width, which loses clipped days and the inclusive entry day. See [SeasonalChart.js:606](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalChart.js#L606).

[Screenshot after the stationary click](evidence/2026-09-15/extra/02-right-click-without-drag.png) · [Resize receipts, cases 01-05](evidence/2026-09-15/extra/audit.json)

## Investigation: Duration and inclusive calendar boundaries

Expected: a stationary press/release preserves all 366 days and end date. A fully visible 30-day May 1 window expanded by ten category-day positions becomes 40. Investigate movement deltas, clipped overlays and mouse/touch handlers without deriving financial results.

## Acceptance and Regression Checks

Test no movement, positive/negative movement, clipped/unclipped right edge, minimum duration, and touch. Assert start/end/duration as well as visible geometry and exact engine values. Preserve end = start + (days - 1).

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0002.md` for the latest record commit.
- 2026-09-15T21:01Z: Claude Code claimed implementation (session ac415bed). Next: reproduce on dev `fce41885`, fix, focused tests, dev activation and live check.
