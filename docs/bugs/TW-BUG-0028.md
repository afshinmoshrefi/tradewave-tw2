# TW-BUG-0028: Webinar signup drops the published Zoom link

- Status: complete unchanged candidate verified against Monday source; live activation blocked on dated release gates
- Confidence: reproduced by current read-only production loader/code inspection; no valid production registration submitted
- Priority: P2 - production webinar notification signup cannot complete
- First observed / last updated: 2026-10-08 13:47 UTC / 2026-10-09 13:45 UTC
- Executor/session: Codex / webinar-zoom-field-20261008, continuing the original 2026-10-08 13:55 UTC claim
- Evidence branch/worktree: `codex/webinar-monday-release-prep-20261009` / `/home/tradewave-worktrees/webinar-monday-release-prep-20261009`
- Authorization: targeted four-file signup repair and designated Codex operator retained under `Sentinel_de3245e3870481919c42ac162704ea57`; no campaign, Zoom/calendar, SMN or unrelated application changes

## Current User Impact and Source

At 2026-10-09 13:33:53 UTC production's published Google feed carries the meeting
URL in `zoom url`; its deployed `webinar_schedule.py` reads only legacy
`Webinar Link`. The parsed session loses `webinar_url`; actual registration code
therefore returns `invalid_session`, whose public message is “This webinar is
no longer available.” This mechanism is inferred from actual source, parsed
session and unchanged runtime. Only an empty validation request was submitted,
returning 400 / “Enter your first name.” No valid live signup/delivery is claimed.

The owner directly requested Monday rescheduling, event
`Sentinel_3a086cf76b808191948cbaee159554b5`. On October 9 the existing connected
Sheets writer succeeded without a new grant: only `webinar_schedule!B2:E2` was
changed and independently read back. Current values are October 12, 2026,
`1:00 PM ET`, “The 100-Year Pattern: October Outlook,” and the owner's corrected
description. Native date formatting and the exact F2 Zoom URL were preserved.
The earlier October 8 OAuth-scope failure is historical and no longer blocks
the source edit.

The existing production static generator ran successfully with `--force`.
Public HTML and JSON, and the actual browser card/registration dialog, agree on
Monday October 12 at 1 PM ET. Friday's card is removed. Public group is
`wb001_2026-10-12_0100PM`, start `2026-10-12T13:00:00-04:00`.
Zoom/calendar rescheduling and subscriber communication were owned by the parent;
this worker made no such writes.

## Fixed Candidate and Exact Artifact

The existing repair remains `0ed01f68201623f4f2e55bd32827fca10479bb1a`.
Only four runtime paths are replaced against production baseline
`c25ffd562dc3058ab41db5b07e9075dd841fb29b`:
`config.py`, `web/email_utils.py`, `web/webinar_registration.py`,
`webinar_schedule.py`. The repair accepts `zoom url`, preserves legacy
compatibility, excludes the private URL from public JSON, reloads server-controlled
session fields, and permits only the explicit production webinar scope while
global MailerLite writes remain off.

One complete immutable package is preserved on dev and staging web at
`/home/tradewave-webinar-artifacts/20261008-baseline-c25ffd-repair-0ed01f`.
Of 2,697 tracked entries, 2,693 baseline entries are unchanged.

- Complete archive SHA-256: `4e40858ac16075c68799a0086a853a890aaffb5c7ef254e95a7fe04164eb7e5f`.
- Inventory SHA-256: `4029a3514beeabf83ab736c755ae843a967aa59759671bcd7364547b763b4a29`.
- Current audited main: `f83a48484f916a89c4fbd9b26030ee7c946d58c5`.
- Pending review composite: `be8c0096b2ccfcef56151025aebe06e8fe0b1813deb080fa9aadcd3368dda6bf`.

The named exception `tw2-20261008-webinar-01` is integrated in
`docs/RELEASE_PROCESS.md`: it authorizes the pinned composite artifact and
isolated dev qualification, preserves actual baseline frontend provenance,
and designates Codex as this release's operator. The default release gates
are retained. Neither the four-file transport tar nor whole current main
is an alternative deployable artifact.

## Current Verification

Fresh October 9 cold imports of the complete artifact pass on dev and on the
actual staging host against Monday's published source. The URL matches the
source; disabled valid registration reaches 503 with subscriber HTTP forbidden.
The actual in-process Flask route under completely mocked provider HTTP returns
200 with correct general/dated groups and date/time/URL fields. Lifecycle HTTP
calls and actual subscriber writes are zero. Shared caches and live flags stay
unchanged. This is cold staging-environment qualification, not live staging
activation or a provider-delivery test.

The complete immutable artifact and all nine canonical runtime/control
fingerprints are independently checked. Prior unchanged-payload evidence remains
1,433 safe regression passes, 5 skips and 115 DB cases deselected, plus 27 focused
release invariant checks. The original focused repair had 50 passes including
the two dev test-DB cases; the staging test DB is absent.

All four targets are freshly audited clean at the pinned baseline. Both web
frontends match all 21 original hashes. Web health reports DB/frontend ready;
app services are running at their original CWDs. Nginx routes/docroots were
inventoried without edits. No task drop-in is active. Staging CWD, drop-ins and
frontend pointer/hash inventory still match its immutable rollback baseline.

Staging activation on October 8 was automatically rolled back at
16:59:30 UTC; today's staging is restored baseline. Production was not activated.
No current live-staging success or level-1 pass is claimed.

A review-only date patch changes only the controller's two quoted date literals
from October 8 to October 9. Nine mocked preflight checks prove today/both-target
acceptance and rejection of missing targets, stale dates, next-day execution
and pending staging/snapshot/production approvals, stopping before all actual
service operations. The original controller and authoritative manifest remain
unchanged. The date patch is not applied or executed.

## One Remaining Decision and Execution Boundary

The parent has requested current-day snapshots and the narrow level-1 exception.
Record a direct answer covering the October 9 continuation of this same named
release: both real production targets (web 194.113.195.141, app 138.128.240.115),
the release-only level-1/date-lock contract/browser substitution using fresh
existing signed-in level-6 checks, the reviewed date renewal, and necessary final
provenance/approval binding. Original scope/operator permission stays retained.

No current-day answer, exception or final binding is recorded in this evidence
branch. October 8 snapshot evidence is historical. Do not execute the expired
activator, mark level-1 checks passed, create accounts, change roles, or bypass
remaining gates. The unchanged runtime archive must remain fixed while the final
approved control commit receives its exact canonical SHA/composite binding.

After that decision, the manager completes actual staging activation under the
existing 20-minute rollback watchdog with flags 0/0, runtime/no-sending contracts
and authorized signed-in browser checks, then finalizes only after retained
gates pass. Production must use the identical artifact with global outbound 0
and webinar scope 1, fresh target audit and automatic rollback. No frontend
rebuild, appserver change, schema migration, replacement credentials, shared
secret, nginx, cron or security change is needed.

Rollback removes only the unchanged task-owned web drop-in, restores original
unit/CWD and exact frontend hashes, restarts the web service and verifies health.
A changed/foreign drop-in is rejected. Preserve original `before.json`; never
reset a checkout or weaken source/approval guards.

## Evidence and History

[October 9 final preparation](evidence/TW-BUG-0028/webinar-final-preparation-monday-20261009.json)
contains exact target audits, Monday staging cold contract, controller review
and one bundled decision. Shared full receipts and decision packet are under
`/home/tradewave-handoffs/2026-10-08/`. Authoritative release state remains
`/var/lib/tradewave/release-state/tw2-20261008-webinar-01/release.json`;
this documentation branch does not replace it or advance canonical main.

- October 8 13:55 UTC: original scoped loader repair, shared checkout/lock preserved.
- October 8 14:23 UTC: separate permission and mocked route tests, 50 passed.
- October 8 14:50 UTC: staging connectivity recovered; isolated candidate contracts passed.
- October 8 15:27 UTC: complete immutable artifact, inventory, cold imports and private frontend checks passed.
- October 8 16:08 UTC: owner approved named scoped mode and designated Codex operator.
- October 8 16:48 UTC: actual staging activation verified runtime/health/non-sending route; level-1 gate remained pending.
- October 8 16:59 UTC: watchdog restored staging, independently verified.
- October 9: Monday Sheet save/sync/public listing completed; source contract, complete provenance, four target audits and review-only date controls refreshed; live release remains gated.
