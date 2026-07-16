# Conversion Email Series - Handoff

Originally built 2026-06-29. Corrected 2026-07-14 after auditing the real
MailerLite triggers against the subscription state machine.

> **Superseding correction:** The original handoff applied the "tell people
> what they do not need" trust approach to every paid-plan nurture. That was a
> context error. Navigator, Analyst, and Strategist nurture recipients have
> already selected that paid plan. Their onboarding must build confidence and
> help them receive value, not prompt buyer's remorse.

## Release-blocking messaging policy

| Journey | Actual recipient context | Required message |
| --- | --- | --- |
| Navigator, Analyst, or Strategist nurture | The subscriber already selected that current paid plan. Entry can also follow a paid-to-paid plan change. | **Affirm, activate, and teach.** Confirm the plan is active, demonstrate its distinctive value, and build a repeatable product habit. Do not ask whether they need the plan, recommend Explorer or another tier, run a plan self-audit, or tell them to pay less. |
| First-time 7-day trial | A brand-new Explorer user has temporary full Strategist access and has not selected a paid plan. | Activate the trial and teach evidence-first product use. Plan comparisons must be neutral and limited to helping the user match needs at the decision point. Do not use explicit anti-resubscribe language. |
| First-time trial ended to Explorer | The same first-time user did not start a paid subscription and is now on Explorer. This is **not** a former paid subscriber. | Orient the user to Explorer and describe paid-tier differences neutrally when useful. Do not imply that they downgraded, churned, or previously paid. |
| Former-paid Winback Explorer | A web subscription ended or was downgraded to Explorer. | This is the **only** journey for explicit anti-resubscribe language: build trust, help Explorer remain useful, and say not to resubscribe until a specific paid capability is genuinely needed. |

This policy applies to the subject, preheader, recipient-visible HTML, plain
text, CTA, and internal email name. A paid email fails review if any of those
surfaces says or implies "do you need this plan," "choose the smaller plan,"
"stay free," "Analyst may fit better," or a similar downgrade prompt.

## Current MailerLite resources

The local source pairs live in
`docs/marketing/emails/{navigator,analyst,strategist}/email-{1..4}.{html,txt}`,
with subjects in each plan's `subjects.md`. Treat a source pair as one artifact:
HTML and TXT must be updated together and must express the same message.

The three paid onboarding automations are real and intentionally inactive:

| Paid journey | Trigger groups | Automation | Production cadence |
| --- | --- | --- | --- |
| Navigator | `navigator_monthly`, `navigator_yearly` | [TradeWave - Navigator Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588340700546941) | Day 0, 2, 4, 7 (delays 2/2/3 days) |
| Analyst | `analyst_monthly`, `analyst_yearly` | [TradeWave - Analyst Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588402343183617) | Day 0, 2, 4, 6 (delays 2/2/2 days) |
| Strategist | `strategist_monthly`, `strategist_yearly` | [TradeWave - Strategist Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588731493287625) | Day 0, 2, 4, 6 (delays 2/2/2 days) |

`TradeWave - Explorer Nurture (4 email)` (`191588255322343409`) is not a
fourth lifecycle journey. Its `explorer` trigger is a current-access
segmentation group shared by first-time, post-trial, and former-paid users. It
must remain inactive because it would overlap the dedicated Trial Started and
Winback journeys.

The three dedicated first-time and former-paid lifecycle automations are
documented in `docs/marketing/emails/MAILERLITE_LIFECYCLE_CUTOVER.md`.

## MailerLite MCP content capability

The old statement that MailerLite HTML could only be pasted manually in the
dashboard is obsolete. The current MailerLite MCP automation-email endpoint
can create or replace recipient-visible designed email content, including the
HTML body, while the automation remains inactive. The connected endpoint also
supports automation structure, subject/plain-text updates, delays, and direct
readback.

Use the MCP endpoint for the complete email, then read the automation back and
verify that the email is designed, complete, eligible for sending, has the
expected subject and body, and contains a resolved unsubscribe link. A helper's
plain-text length limit is not an HTML-authoring limitation and must not be used
as a reason to leave stale HTML in place.

The local HTML and TXT files remain the durable editorial source. Updating only
MailerLite or only one local format creates a regression path and is not a
complete change.

## Overlap and cutover rules

Access-level groups are mutually exclusive in application code, and all
replacement triggers use **Exit workflow when subscriber no longer matches**.
That does not prevent two automations with the same group trigger from starting
together.

- Enabled legacy `New Instituional Subscribers` (`163215402053141778`) shares
  both Strategist trigger groups with the replacement.
- Enabled legacy `New Pro Subscribers` (`164017395322586781`) shares
  `analyst_monthly` with the Analyst replacement.
- Dormant Explorer automations share the base `explorer` group and must remain
  inactive.
- Dormant `TW Trial (7-day)` shares `lifecycle_trial_started` and must remain
  inactive when the replacement is enabled.

At cutover, finish and test the inactive replacements first. In one controlled
maintenance window, disable the two overlapping paid legacy automations and
then enable the paid replacements. Do not enable both generations together.
Retain the disabled legacy workflows until controlled production enrollment is
verified; delete them only afterward.

## Navigator AI scoring decision

The runtime gate historically excluded Navigator from web-app AI scoring even
where older marketing copy suggested otherwise. Before approving Navigator
copy, verify the current runtime entitlement and pricing page. Until code and
pricing explicitly agree that Navigator includes AI scoring, the Navigator
nurture must describe its verified capabilities only: three date-unlocked
markets, 15 years of history, the election-cycle table filter, and its current
workspace limits.

## Release checklist

1. Rewrite all paid-plan HTML/TXT source pairs to follow the policy above.
   Paid nurture should confirm the selection and help the customer achieve a
   useful result; it must contain no downgrade or anti-buy section.
2. Write the complete designed emails through MailerLite MCP while each
   automation remains inactive. Keep the verified sender and monitored
   reply-to as TradeWave `<help@tradewave.ai>`.
3. Read back every automation. Traverse steps by `parent_id`, not raw array
   order, and verify the cadences in the table above.
4. Verify every email's recipient-visible HTML, plain text, subject, preheader,
   CTA, account link, unsubscribe link, sender, reply-to, and physical-address
   footer.
5. Send isolated one-recipient tests and inspect the received HTML in Gmail.
   Searching metadata alone is insufficient because HTML is what most
   recipients see.
6. Verify all feature, limit, price, support, and event claims against current
   product behavior and `https://tradewave.ai/#pricing`.
7. Perform the overlap-safe cutover above. Confirm one controlled subscriber
   enters only the intended journey before broader enrollment.

## Quality bar

Paid onboarding earns trust by accurately teaching the product the customer
chose and helping them reach value quickly. First-time trial and post-trial
Explorer messages may compare plans neutrally. Explicit "do not pay yet" or
"do not resubscribe yet" trust language is reserved for Former-paid Winback
Explorer.

Across every journey: keep historical evidence confident but never predictive,
show losing years and sample-size limits, avoid investment advice, use current
product claims only, and keep HTML, TXT, MailerLite readback, and received test
email content aligned.
