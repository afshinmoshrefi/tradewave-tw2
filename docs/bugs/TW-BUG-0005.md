# TW-BUG-0005: February 29 Breaks the Date and Data Display

- Status: open
- Confidence: reproduced
- Priority: P2 (user-visible boundary or recovery failure)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: unassigned; recorded by Codex, shared-bug-memory-20260915
- Authorization: document and track; implementation not yet assigned or authorized by this task
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
With AAPL, consecutive years, and Jan-Dec off, enter **2028-02-29**. The tested 5-year, 39-day opportunity produced a **Data Temporarily Unavailable** dialog, an empty main bar chart, `undefined` Trend Chart statistics, and an incorrectly positioned highlight.

The accepted trend response contains 365 dates and omits February 29. The renderer silently uses index zero when it cannot find the entry date. The primary chart also failed to load for that entry. The repair must reconcile the engine date contract and display behavior; it must not invent a February 29 curve value in the client.

[Screenshot](evidence/2026-09-15/extra/10-leap-day.png) · [Receipt, case 10](evidence/2026-09-15/extra/audit.json)

## Investigation: Leap-day contract

The response covers 2028-02-15 through 2029-02-14 and lacks the entry date. Primary chart failure was observed, but its exact API cause was not separately traced. First investigate engine and input contracts. A product decision may be needed for an unsupported entry; no downstream invented Y value is acceptable.

## Acceptance and Regression Checks

Exercise valid February 29 and neighbors, leap/non-leap years, calendar modes and recovery. A valid date must yield supported coherent behavior or a clear explicit limitation; no undefined stats, silent index-zero highlight or generic unexplained failure. Agree on any engine-calculation change first.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0005.md` for the latest record commit.
