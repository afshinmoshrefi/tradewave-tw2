# TW-BUG-0007: A Failed Trend Request Leaves an Empty Placeholder

- Status: open
- Confidence: reproduced
- Priority: P2 (user-visible boundary or recovery failure)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: unassigned; recorded by Codex, shared-bug-memory-20260915
- Authorization: document and track; implementation not yet assigned or authorized by this task
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
Changing years while the trend request receives HTTP 500 leaves an empty **Trend Chart** placeholder. The main bar chart can load successfully, so there is no other failure dialog. There is no trend-specific error message or retry control. A further years change recovers it.

This failure was **simulated in the audit browser only**; it was not an observed server outage. The existing [failure reporting](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalBarChart.js#L1285) does not render a chart error state.

[Screenshot](evidence/2026-09-15/desktop/17-failed-trend-load.png) · [Failure and recovery receipts, cases 17-19](evidence/2026-09-15/desktop/audit.json)

## Investigation: Actionable failed-load state

Inject HTTP 500 into only consolidated_seasonal_chart2 requests in a disposable browser, then change years while allowing real primary-chart calls. Expected: an explicit trend failure and a retry/recovery action. This is controlled fault injection, not proof of a historical server outage.

## Acceptance and Regression Checks

Check 500, transport failure and invalid/empty response according to their contracts; show a useful failure state and recover on retry. Late failed requests must not overwrite a newer successful study. Verify the primary chart remains usable.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0007.md` for the latest record commit.
