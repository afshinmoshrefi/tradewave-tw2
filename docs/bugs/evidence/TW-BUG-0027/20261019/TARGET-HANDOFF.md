# SMN live cutover and image recovery

**Code deployed and verified October 19, 2026 at 16:34:35 UTC.** Actual SMN
`seasonalmarketnews / 209.182.216.112` now runs immutable revision
`55afe01a5683c6f2471e0d578867ad77390bb739`. Both pinned subscription/newsletter base
units have the correct effective ExecStart and WorkingDirectory. Existing
drop-ins remain unchanged and all five original timer states were restored.
[Live cutover proof](live-cutover-proof.json) records the actual observations.

The original six current-day articles and 123 edition files passed native
verification. New-code reader capture and reservation passed using a private
proof callback: no campaign intent, subscriber send, provider request, model job
or public content write occurred during code activation. Mail and publication
receipt hashes remained unchanged. The exact three managed files and pointer
were updated with qualified atomic/rollback primitives; the complete historical
October 9 apply operation was never invoked. Six wrapper-specific effective-unit
binding checks also pass. Operator SHA256:
`81f3c454678ef633b1b8464b6d9d8f39b5bfaf19a84fd97255d56f5ec9e5c24c`.

Afshin approved the bounded action at 16:17:01 UTC and confirmed the actual-SMN
current-day full-server backup at 16:24:02 UTC with “yes do it.” Unknown provider,
snapshot identifier and exact completion-clock fields remain null. The existing
targeted rollback preimages are separately restore-verified. Approval and backup
are satisfied for this exact cutover; do not ask for them again.

## Four images repaired and verified

Native publication/browser checks completed at **16:38:28 UTC**. Public article
and image HTTP/hash checks also pass from Windows. Restored public URLs:

- https://seasonalmarketnews.com/editions/2026-10-16/GS/article.html
- https://seasonalmarketnews.com/editions/2026-10-16/PGR/article.html
- https://seasonalmarketnews.com/editions/2026-10-16/XLK/article.html
- https://seasonalmarketnews.com/editions/2026-10-16/MRK/article.html

All four use previously published, visually inspected artwork with an explicit
archive caption. PGR's existing black upper band/stylized vehicle-damage warning
is retained. Original article JSON/HTML, hero-source receipt, factual reviews and
TradeWave values remain unchanged. C remains text-only and DPZ held. No new image,
paid provider or model job was used, and the mail journal did not change.

October 16 canonical receipt SHA256:
`86c901a7497d218ccfd569f7cc1d04b3dbad70d5dd04416196dc7ca31c75c3ab`.
The historical repair temporarily makes that date the homepage coverage date;
the operation therefore used a separate native publication-only transaction to
restore current October 19 coverage, retaining all six article bytes unchanged.
Current canonical receipt SHA256:
`f55168493347a1585632be39abfa4713153dcd71dbd3b3c43b94d1d743997034`.
Both transactions use the deployed exact source. The repair service exited
successfully and all five original timer states were restored. See
[repair receipt](hero-repair-live-proof.json) and
[independent public checks](public-recovery-verification.json).

## Remaining limits

No subscriber send or resend is authorized in this worker. Today's daily
newsletter remains terminal after pre-POST failures; code installation does not
reset it. Actual alert delivery is unverified and requires an existing approved
destination and functioning transport. C still lacks a qualified image.

The candidate already passed 151 actual-target mail/runtime tests, 90 native
publication/accounting tests, eight private activation/rollback cases (also as
root), native JavaScript and installed Chromium 153 checks. Those are completed
qualification, not evidence of successful future scheduled runs. Observe at
least three consecutive real weekdays and actual provider/alert delivery before
claiming stable unattended operation.

## Pending owner policy choices

The user requested explicit operating-rule choices. Three questions were raised:
editorial/style/image warnings versus essential article checks; partial-edition
newsletter policy; optional human review versus a one-hour review window. No
answer has been recorded yet and no new policy is enabled. Existing deployment
authorization and the 60-job allowance remain in force. The runbook contains
historical all-six/12-job text alongside later continuity/60-job overrides;
consolidation should preserve history while presenting one clear current policy.
Lock/retry defects remain engineering responsibilities, not owner-policy choices.

## Final independent verification

[Final live state](final-live-state.json) confirms source 55afe01a, native receipts for both dates, correct effective pinned units, all five enabled/active timers, released activation lock and unchanged mail journal after scheduled ticks resumed. The two native browser passes checked 10 historical and 12 current article layouts, with 199 and 215 public files respectively. [Eight actually viewed hero captures](hero-pixel-inspection.json) confirm desktop/mobile figures and archive captions. Existing tight mobile evidence-table wrapping is retained as an advisory observation, outside this image repair. No remaining code-deployment or four-image blocker exists.

## Citigroup read-only investigation

A suitable existing 4032 x 2268 photograph of 388 Greenwich Street was found, author/license verified, byte-checked and actually viewed. [Proposed source and exact constraints](C-READONLY-ASSET-PROPOSAL.md). C remains unchanged in production. No C image was uploaded to the server or shared repository, no generation was run and no receipt was fabricated. Separate C publication authorization and truthful licensed-source provenance integration remain.
