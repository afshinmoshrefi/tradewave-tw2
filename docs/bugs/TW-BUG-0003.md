# TW-BUG-0003: Starting on the Chart's Last Date Puts the Highlight on the Left

- Status: open
- Confidence: reproduced
- Priority: P2 (user-visible boundary or recovery failure)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: unassigned; recorded by Codex, shared-bug-memory-20260915
- Authorization: document and track; implementation not yet assigned or authorized by this task
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
Select **Buy & Hold**, turn **Jan-Dec** off, and drag the start from January 1 to November 19, 2026. Use the start-date right arrow 28 times to reach **December 17**, the chart's final displayed date.

The start and duration correctly become December 17 and 16 days, but the highlight moves to the far left. It paints indices 0-14 instead of the right edge. The retained-window rule accepts the last date; the renderer treats equality with that date as a year wrap. See [SeasonalChart.js:227](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalChart.js#L227).

[Screenshot](evidence/2026-09-15/desktop/02b-last-date-boundary.png)

## Investigation: Inclusive final-date boundary

Expected: December 17 entry maps to the actual last category (index 364), with any portion beyond the chart handled by the existing display convention. It must not wrap to index zero. A direct +350-day drag was not the confirmed reproduction because clipping/minimum width constrained that gesture.

## Acceptance and Regression Checks

Exercise first date, penultimate date, exact final date, and one day beyond it, through date arrows and typed dates. Preserve the stable in-range window and fresh out-of-range behavior; no silently defaulted index zero.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0003.md` for the latest record commit.
