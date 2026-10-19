# Bounded SMN release handoff

Exact candidate: `55afe01a5683c6f2471e0d578867ad77390bb739`. Production baseline: `2b0075c85e45d8cd547c95b8868f8560532cf86b`.
Code and factual-review policy are unchanged since the 151-test proof; no factual
review bypass is proposed. Broad future-release permissions and a new review
window are not prerequisites. The parent owns any bounded release decision.

The [release plan](bounded-release-plan.json) gives exact old/new service commands,
proposed owned drop-ins, backup capture, activation and conditional rollback
steps. It is prepared, not executed. Source-code diff: 18 files total, four runtime
modules plus tests, exact captured HTML fixtures and the runbook. The fresh-hero
code remains identical to installed production.

151 Linux tests and native JavaScript checks pass. Six tests run real weekday,
partial-edition, Sunday, duplicate/restart, uncertain-provider and alert programs
with only external provider/model boundaries mocked. The full suite is on Dev
Python 3.13.7; actual SMN Python 3.12.3 checks compile and read-only replay, without
running the full private-filesystem scheduled suite there. Final systemd runtime,
native publication/browser/rollback rehearsal, current-day actual-SMN backup,
real provider/alert delivery and consecutive scheduled days remain unverified.

The [fresh 13:00 UTC inventory](alert-release-inventory.json) finds alerts disabled,
zero recipients, no alert service/timer, and no Resend key in their designated
secrets file. No destination was found in inspected configuration or cron MAILTO;
the newsletter sender is not automatically an alert recipient. Parent should
resolve this concrete monitoring gap without blocking code qualification on a
new general notification policy.

Today's six web articles are live. Newsletter attempts remain exhausted after
pre-POST lock failures; code activation does not reset them. No subscriber send
was performed. The October 18 recap's five missing pictures are an unfinished
October 16 media backfill: neutral placeholders had no public hero tags/URLs.
The other eleven images work. Backfill uses the existing fresh derivative
workflow and cannot add image tags to an already delivered recap.

The plan includes a precise one-time deployment wording only if the parent finds
an actual gap in existing approval. It must not be used to repeat the user's
blanket approval or require an all-future release authorization.

Additional checks, 13:05 UTC: **90/90 existing native publication/accounting
tests pass** on the same candidate. The original harness refusal of one exact
asset-preflight subprocess is retained in a separate failure proof and corrected
in the allowlist. No product code changed. **Actual local Chrome 155** also passes
four Python/JavaScript fixture contract comparisons, cash/futures and unavailable
quote transitions, old-receipt rejection, peer-edit rejection and malformed quote
rejection. This is an offline real-browser contract replay, not a target-system
publication/browser/rollback rehearsal. The standard Dev browser package path is
absent; no browser or dependency was installed there.
