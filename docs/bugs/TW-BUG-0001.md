# TW-BUG-0001: Mobile Rotation Can Crash the Viewer

- Status: in-progress
- Confidence: reproduced
- Priority: P1 (viewer failure or silent change of user intent)
- First observed / last updated: 2026-09-15 (audit date; exact per-case wall times not retained)
- Executor/session: Claude Code (claude-opus-5), session ac415bed-b1cf-4689-be18-536911d44893; claimed 2026-09-15T21:01Z; branch `claude/tw-bug-0001-mobile-rotation-20260915`, worktree `/home/tradewave-worktrees/claude-tw-bug-0001-mobile-rotation-20260915`; recorded by Codex, shared-bug-memory-20260915
- Authorization: Afshin authorized the fix on 2026-09-15 ("fix codex's recommended 2 bugs first"); fast dev completion only, no staging/production
- Affected baseline: dev frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, `main.0ee1de72.js`
- Staging/production: not tested; affected versions there are unknown

## Reproduction, Impact and Evidence
**Priority: high.** Open the viewer in phone portrait, allow its charts to load, then rotate to landscape. The chart area can be replaced by **“MobileLayoutL encountered an error.”** Clicking **Retry panel** reproduced the failure.

This reproduced twice in Chromium iPhone emulation, including rotation without any preceding drag. The caught error is `Cannot read properties of undefined (reading 'speed')`. Its stack reaches `MobileLayoutL`'s reset effect and Swiper's `this.params.speed` read. A stale Swiper object during layout switching is the leading lifecycle explanation. See [MobileLayoutL.js:124](https://github.com/afshinmoshrefi/tradewave-tw2/blob/fce41885ec8fbdc70fabc1fb56bde38c98339396/web-react/src/components/MobileLayoutL.js#L124).

[Screenshot](evidence/2026-09-15/mobile/03-landscape-rotation.png) · [Confirmed rotation and retry receipt](evidence/2026-09-15/mobile-confirm-rotate/audit.json)

## Investigation: Portrait/landscape lifecycle

Expected: a loaded viewer survives portrait to landscape and back; Retry panel restores a usable viewer after a recoverable error. The stack confirms slideTo reads missing params; the stale/destroyed instance lifecycle is the leading explanation, not an independently instrumented lifecycle proof.

## Acceptance and Regression Checks

Exercise repeated portrait/landscape cycles before and after a touch resize, plus retry and direct landscape load. No error boundary or speed exception; charts remain usable. Confirm physical Safari before claiming Safari coverage.

Read [audit setup and limits](evidence/2026-09-15/README.md). Retain the protections in [TW-BUG-0008](TW-BUG-0008.md) and [TW-BUG-0009](TW-BUG-0009.md). Related highlight/input contracts: TW-BUG-0003 through TW-BUG-0006.

## Implementation and Handoff

No fix commit, implementation branch, migration, build or deployment exists for this record. No new regression tests were run during registration. Next: claim this bug after implementation is authorized, reproduce against the then-current runtime and trace the identified code at the current source revision. Add the smallest relevant regression check and implement under [shared management](../WORK_MANAGEMENT.md) and existing release rules. Rollback planning belongs to that fix; no runtime rollback is needed for this documentation.

## History

- 2026-09-15: Codex reproduced during read-only audit of fce41885; application unchanged. Findings recorded in `80fb093e08af4b9de8247c91853cc42f767961bb`.
- 2026-09-15: Codex registered the finding with portable evidence and explicit acceptance criteria. Status remains open, owner unassigned. Use `git log -1 -- docs/bugs/TW-BUG-0001.md` for the latest record commit.
- 2026-09-15T21:01Z: Claude Code claimed implementation (session ac415bed). Next: reproduce on dev `fce41885`, fix, focused tests, dev activation and live check.
