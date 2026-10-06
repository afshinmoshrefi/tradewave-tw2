# October 6 newsletter delivered once

**MailerLite confirms 137 sent and 137 delivered** for campaign **200578330583369260**, `SMN-Daily-2026-10-06`. Provider dispatch began at **11:37:03 UTC** and finished at **11:37:49 UTC / 07:37:49 Eastern**. Delivery was independently read back before local completion was recorded at 11:38:58 UTC. Zero hard or soft bounces were reported in that observation. This is provider delivery evidence, not an inbox/open guarantee.

Afshin explicitly authorized through Dorothy: send the October 6 edition to the existing SMN Daily list once, containing the six already published articles. The supported MailerLite connector performed exactly one regular campaign creation and one instant-delivery request. The earlier audience/payload approval-review block was resolved by the quoted voice authorization; no new confirmation was requested by this worker.

## Audience and payload

- Existing **SMN-DAILY** group `179755084579604160`, 137 active recipients. No all-active filter, segment substitution or audience change.
- Exactly **CPRT, APH, XLK, IBM, MSFT, COST**, using their actual October 6 published titles, descriptions, hero URLs and article links.
- Existing installed email template, public favicon and sender retained: Seasonal Market News / `info@tradewave.ai`, reply-to `afshin@tradewave.ai`.
- Subject: **October 6 Seasonal Market News**. Introduction contains only verified date/ticker metadata: “October 6 edition: CPRT, APH, XLK, IBM, MSFT and COST.” No additional market claims or AI narrative were generated.
- Final HTML SHA256: `d54e9931319f4bc06a031ffdf1803cc08c40880d888ac730a972dcc2a866643d`.
- [Actual email preview](https://preview.mailerlite.io/preview/489451/emails/200578330604340786).

## Eligibility, duplication and preserved state

Fresh provider latest/ready/draft checks found no October 6 SMN daily campaign. The production journal and marker were absent for this date, and none of the six slugs was reserved. October 5's 138-recipient delivered campaign and the unrelated five-recipient DAILY_AI_PICK campaign were untouched.

The read-only eligibility check used the installed function with one explicit in-memory receipt-path substitution to the actual recovered receipt. All six date/selection, morning source, source-commit, catalog, URL and public origin body bindings passed. Receipt SHA256 remains `b3f921aa83b5b1421c26dfa3f6778480d2ca6ee55df3c43c2027a07ff4516e63`.

A narrow one-time operational helper acquired the existing newsletter/state exclusions, checked the journal hash and current receipt/source, and durably reserved the day marker before creation. It saved the returned campaign ID before the one send request. Creation/scheduling uncertainty had no automatic retry. The helper writes only operational journal, marker and recovery metadata; no installed source/configuration or service was changed. Journal file ownership and permissions were preserved on atomic updates.

After actual provider completion, the journal records `phase=sent`, the same campaign ID and 137 deliveries. All six slugs were added once to daily deduplication state (851 to 857); the normal day marker is completed. Recovery resolution and controller status now truthfully say `newsletter_released=true` and identify this campaign. The original failed reader tree and absent canonical publication receipt remain intact; no original publication receipt was fabricated.

Operational receipt root: `/var/lib/tradewave/smn-daily/subscription-primary/2026-10-06/newsletter-release-once-20261006/`. It contains the journal backup, approved payload and release-state receipt. Application source remains `2d1de1a9c9f200fa29a2db7f9660f3527727b660`; final hashes for the sender, subscription writer and profile loader match the preflight. No deployment, credentials change, paid narrative call, paid fallback, new article generation or extra newsletter occurred.

## Offline 6.1-Sol preparation

**Six focused offline tests passed**, preserving the real XLK article/source/review fixture. The package is `smn-sol61-offline-20261006/`; runner is `smn-sol61-offline-tests-20261006.py`. Tests cover current rejection versus isolated allowlist acceptance, actual review schema and malformed output rejection, changed-input refusal, exact model/medium/private CLI argument serialization with process interception, unavailable model/effort refusal before dispatch, and refusal to relabel the original Sol receipt as 6.1-Sol.

The candidate allowlist exists only in an isolated imported module. All provider process starts were mocked/intercepted; **zero real provider processes, model turns or benchmark calls** ran. No synthetic 6.1-Sol receipt was produced. The cached-receipt check is a proposed local trial boundary; it does not claim the installed adapter gained that guard.

Real CLI/account availability, supported 6.1-Sol effort and actual output quality remain unqualified. A later explicitly bounded one-review trial can reuse the dated XLK fixture; it would establish only that review case, not writer quality or approval to switch production profiles. Existing Sol reasoning checks were not repeated. Production models and normal 40-job allowance are unchanged; no peer consensus is claimed.

## Evidence and remaining work

- `smn-newsletter-delivery-confirmed-20261006.json`: real provider terminal status, timestamps, exact audience and delivery counts.
- `smn-newsletter-delivered-state-20261006.json` and `smn-newsletter-final-state-20261006.json`: journal/marker/recovery handoff, six-slug deduplication and unchanged source proof.
- `SMN-Daily-2026-10-06-approved-content.html` and `smn-approved-newsletter-payload-20261006.json`: exact payload.
- `smn-newsletter-send-preflight-20261006.json`: actual published article rows, real receipt and retained source/fixture evidence.
- `smn-sol61-offline-20261006/qualification.json`: six passing offline checks and explicit qualification limits.

October 6 publication and newsletter delivery are complete. Permanent quotation/budget recovery, pending continuity/watchdog release, normal mailer durable-state integration and the separate header defect remain owner work. No general daily send policy or deployment was changed by this once-only release. Follow the existing owners and draft PR #14 rather than starting a competing production change.
