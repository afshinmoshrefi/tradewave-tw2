# TW-BUG-0010: Browser Date and Market Date Can Leave the Date-Locked Chart Blank

- Status: open
- Confidence: reproduced on dev
- Priority: P1; valid Explorer row clicks can leave all charts blank in affected timezones
- First observed / last updated: 2026-09-16T01:46Z / 2026-09-16T02:12Z
- Executor/session: unassigned for implementation; recorded by Codex staging-release-20260915-auth
- Authorization: deployment investigation and documentation only; application repair not performed

## User Impact and Reproduction

On the September 15 US market evening (September 16 UTC), an Explorer browser in
UTC initialized its opportunity date as September 16. Clicking the first WMT row
left the Gain-Loss, Trend and Price loading covers present, with no canvases or
HTTP errors. The same candidate and flow in America/New_York loaded successfully.
Candidate: `05ae209ecaba231e5816f835dc133f7c0cdf00e8`, bundle `main.81dfb8cb.js`.

## Evidence and Investigation

[UTC browser receipt](evidence/staging-release-20260915/dev-browser-debug.log)
and [New York browser receipt](evidence/staging-release-20260915/dev-browser-ny.log).
Durable full evidence: `/var/lib/tradewave/release-state/tw2-20260915-01/evidence/`
on dev, including the initial automatic dev rollback log.

`Common.js:getTodayDate` uses browser-local Date fields. The date-locked backend
uses America/New_York; the strict response identity guard rejects unmatched dates.
The relevant local-date helper and non-exact-window guard behavior are unchanged
from previously deployed `c398d648`. This is not evidence of a new release regression.
The backend's explicit September 15 request/echo contract passed during the same
UTC/US date divergence. Do not fix this by changing server timezone or weakening
the response guard. New York emulation was used for the required owner-market
browser gate; the UTC failure is retained, not represented as a passing test.

## Acceptance and Regression Checks

Agree the canonical display-date behavior for date-locked tiers. Test Explorer
in UTC, America/New_York and a timezone ahead of UTC around US evening and date
boundaries. A real opportunity click must return verified engine data, remove all
loading covers and retain matching request/response identity. Preserve Strategist
historical dates and future-year normalization. No financial calculations here.

## Implementation and Handoff

No application changes. Record on `codex/staging-report-20260915`; release remains
pinned at `05ae209e`. Review this limitation before production promotion. Do not
claim it repaired by the staging release or by test timezone selection.

## Environment Verification

Dev: reproduced UTC; New York flow passed. Staging: same release and New York flow
passed; UTC reproduction not separately run. Production: not accessed or tested.

## History

- 2026-09-16: Captured during staging qualification; isolated browser-date difference;
  recorded as an unresolved existing-code risk. No repair owner assigned.
- 2026-09-16 production gate: Afshin was informed of the reproduced browser/market
  date mismatch and explicitly instructed "continue deployment" with the issue
  unchanged, planning to check it tonight. This is a release-risk deferral, not
  verification or repair authorization. Production reproduction remains untested.
