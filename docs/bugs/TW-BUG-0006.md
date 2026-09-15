# TW-BUG-0006: Invalid Typed Dates Can Blank the Chart

- Status: open
- Confidence: reproduced
- Priority: P2 (user-visible boundary or recovery failure)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: unassigned; recorded by Codex, shared-bug-memory-20260915
- Authorization: document and track; implementation not yet assigned or authorized by this task
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
Enter **2026-02-31** in the start-date field. The client accepts it, then the trend endpoint returns HTTP 400 with `invalid chart date`. Both chart areas become empty and the user receives a generic temporary-data error instead of a useful invalid-date message. Closing the dialog and entering a valid date recovered the chart.

There is also a timing case: enter an invalid-format value while a years change has cleared the trend data. The date handler accesses `[0][0]` on the empty array and throws. The audit reproduced this with a delayed browser request. See [calendar validation](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalBarChart.js#L1617) and [empty-array access](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalBarChart.js#L1728).

[Screenshot](evidence/2026-09-15/input/02-invalid-calendar-date.png) · [Input and recovery receipts](evidence/2026-09-15/input/audit.json)

## Investigation: Calendar validation and loading race

Reproduction B: delay the trend response by 2.5 seconds in the browser while changing years; with the trend array empty enter oops. Both Enter and blur paths need investigation. Calendar checks currently accept any day 1..31 independent of month. A later successful response recovered the timed case; permanent crash was not established.

## Acceptance and Regression Checks

Reject February 31 and non-leap February 29 before submitting a study; test valid leap day under its actual contract. During pending/empty data, invalid input via Enter and blur must not throw. Preserve valid study state or show actionable validation, and verify correction/recovery.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0006.md` for the latest record commit.
