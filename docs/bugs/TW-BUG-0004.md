# TW-BUG-0004: Jan-Dec Highlights the Whole Year for Some PE Selections

- Status: open
- Confidence: reproduced
- Priority: P2 (user-visible boundary or recovery failure)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: unassigned; recorded by Codex, shared-bug-memory-20260915
- Authorization: document and track; implementation not yet assigned or authorized by this task
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
Use a late-year start such as **December 17**, select **PE Years** or **PE+1 Years**, and enable **Jan-Dec**. These selections move the opportunity into 2028 or 2029 while the Jan-Dec chart displays 2026.

The highlight covers the whole year instead of the selected portion. The renderer only shifts the opportunity year once, so it fails when the difference is two or three years. PE+3, one year ahead in the checked case, displayed correctly. The same [highlight-positioning code](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/SeasonalChart.js#L221) is involved.

[PE screenshot](evidence/2026-09-15/desktop/07-pe0-jan-dec.png) · [PE+1 screenshot](evidence/2026-09-15/desktop/08-pe1-jan-dec.png)

## Investigation: Multi-year PE normalization

Expected: December 17 maps to the corresponding late-year location (index 350 on the observed axis), rather than a full-year band. Do not assume a fixed duration across PE selections. PE+3 in 2027 passed the recorded single-year difference.

## Acceptance and Regression Checks

Check PE, PE+1, PE+2, PE+3 and consecutive modes with Jan-Dec on/off, late-year windows and year-crossing windows. Use the documented calendar/engine convention without changing the financial response.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0004.md` for the latest record commit.
