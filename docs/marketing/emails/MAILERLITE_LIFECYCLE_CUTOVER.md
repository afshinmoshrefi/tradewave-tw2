# MailerLite Lifecycle Cutover

Updated: 2026-07-14

The three lifecycle workflows and three paid onboarding workflows are real
MailerLite drafts. They are intentionally inactive until the application
outbox is deployed, recipient-visible email content is approved, and the
overlap-safe cutover below is complete.

## Live resources

| Journey | Trigger group | Automation | Timing |
| --- | --- | --- | --- |
| First signup trial | `lifecycle_trial_started` (`189853876367656773`) | [TW Lifecycle - Trial Started (7-day)](https://dashboard.mailerlite.com/automations/192896875220698599) | Day 0, 2, 4, 6 |
| Trial ended to Explorer | `lifecycle_trial_ended_explorer` (`192896580322330062`) | [TW Lifecycle - Trial Ended to Explorer](https://dashboard.mailerlite.com/automations/192896888595285340) | Day 7, 10, 14 |
| Former paid subscriber | `winback_explorer` (`192267699380815223`) | [TW Winback - Explorer (trust letter)](https://dashboard.mailerlite.com/automations/192267713628865734) | One day after paid access ends |

Related paid onboarding resources:

| Journey | Trigger groups | Automation | Timing |
| --- | --- | --- | --- |
| Navigator onboarding | `navigator_monthly`, `navigator_yearly` | [TradeWave - Navigator Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588340700546941) | Day 0, 2, 4, 7 |
| Analyst onboarding | `analyst_monthly`, `analyst_yearly` | [TradeWave - Analyst Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588402343183617) | Day 0, 2, 4, 6 |
| Strategist onboarding | `strategist_monthly`, `strategist_yearly` | [TradeWave - Strategist Nurture (4 email)](https://dashboard.mailerlite.com/automations/191588731493287625) | Day 0, 2, 4, 6 |

MailerLite MCP readback on 2026-07-14 found all six replacements inactive,
complete, unbroken, and configured to exit when a subscriber no longer matches
the trigger. Email content must still pass the lifecycle-policy review and
received-message test below before activation. A structurally complete
automation is not editorial approval.

The access group `explorer` (`97426012986410777`) is segmentation only. It
must not trigger a lifecycle automation. Do not backfill its existing members.

## Release-blocking messaging policy

The trigger determines the message. Do not reuse trust copy across contexts.

- **Paid Navigator, Analyst, and Strategist onboarding:** recipients have
  already selected the current paid plan. Affirm the decision, activate the
  distinguishing features, teach evidence-first use, and build a repeatable
  workflow. Never ask whether they need the plan, recommend another tier,
  promote Explorer, or include a plan self-audit.
- **First-time trial:** the user has not selected a paid plan. Activate the
  seven-day full-access experience. Plan matching may be neutral and confined
  to the decision point; do not use explicit anti-resubscribe language.
- **Trial ended to Explorer:** this is a first-time nonpayer, not a churned
  customer. Orient them to Explorer and describe tier differences neutrally.
  Do not say or imply that they downgraded or previously paid.
- **Former-paid Winback Explorer:** this is the only journey for explicit
  "do not resubscribe yet," "stay free until you need X," or equivalent
  anti-buy trust language.

Apply this rule to subjects, preheaders, internal names, HTML, plain text, and
CTAs. The HTML matters most in recipient review because that is what most email
clients display.

## MailerLite MCP and received-message checklist

1. Update the matching local `.html` and `.txt` source files together. Then use
   the current MailerLite MCP automation-email endpoint to create or replace
   the complete recipient-visible designed email while the automation remains
   inactive. The old dashboard-only/manual-paste limitation is obsolete.
2. Read every automation back. Verify designed/complete/eligible email state,
   expected subject and body, and **Exit workflow when subscriber no longer
   matches the trigger**. Traverse the sequence by `parent_id`; the raw step
   array is not chronological.
3. Send one test of every email and verify links, mobile layout, unsubscribe,
   sender, reply-to address, preheader, and the actual received HTML body. Keep
   MailerLite's automatic company footer enabled so the verified physical
   mailing address is included.
4. Verify `https://tradewave.ai/#pricing` shows Explorer, Navigator, Analyst,
   and Strategist with the same limits stated in the emails.
5. Keep all old Explorer and trial workflows inactive. Activate only these
   three, in this order: winback, trial-ended, trial-started.

The current MailerLite MCP integration can author recipient-visible automation
email content; it is no longer limited to shells, delays, and plain text. Always
verify by direct MailerLite readback and a received test. A helper's plain-text
length limit does not justify leaving old HTML or a generic fallback in place.

## Paid onboarding overlap-safe cutover

Two enabled legacy workflows share paid trigger groups with the replacements:

- `New Instituional Subscribers` (`163215402053141778`) shares both
  `strategist_monthly` and `strategist_yearly`.
- `New Pro Subscribers` (`164017395322586781`) shares `analyst_monthly`.

Do not activate the paid replacements while those overlapping legacy workflows
remain enabled. Finish and test all inactive replacements first. In one
controlled maintenance window, disable the two overlapping legacy workflows,
then enable Navigator, Analyst, and Strategist replacements. Keep the legacy
workflows disabled but undeleted until a controlled subscriber is confirmed in
exactly one intended journey.

Do not enable any automation on the base `explorer` access group. A new signup
belongs to `explorer` and `lifecycle_trial_started` simultaneously; a former
paid subscriber can rejoin `explorer` while joining `winback_explorer`.
Explorer-group automation would therefore duplicate both journeys.

## Application rollout

Set these production secrets with outbound writes still disabled:

```text
TW2_ENV=prod
MAILERLITE_OUTBOUND_ENABLED=0
MAILERLITE_TRIAL_STARTED_GROUP_ID=189853876367656773
MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID=192896580322330062
MAILERLITE_WINBACK_GROUP_ID=192267699380815223
```

Then:

1. On dev and staging, run tests, verify migration/enqueue behavior, and use
   the worker's `--dry-run`; external MailerLite writes are intentionally
   impossible there. An operator runs `bash ops/deploy.sh staging`, verifies
   staging, and finally runs `bash ops/deploy.sh prod`. The deploy includes
   lifecycle migration `c7a9e2f4d6b8`, API-subscription safety migration
   `d8c4e6a2f9b1`, and the once-per-minute worker.
2. On production, audit the stored Stripe subscription identities before any
   lifecycle backfill. This reads Stripe but writes nothing:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py'
   ```

3. Resolve every `blocking` row. The audit pages all Stripe subscriptions for
   each affected customer before an API ID can leave the web column. It never
   clears a paid web tier: exactly one live EOD subscription must match the
   database tier and is restored atomically, otherwise the row blocks for
   operator review. With outbound still disabled and explicit `TW2_ENV=prod`,
   apply the proven identity moves, then rerun the dry run:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py --apply'
   ```

   The audit never clears a confirmed web/EOD subscription, a paid web tier, or
   an unlabelled legacy web subscription. It refuses the whole apply on a
   Stripe lookup/pagination error, customer/tier/status mismatch, shared ID,
   incomplete or conflicting metadata, or multiple candidate subscriptions.
4. Preview the active-trial expiry backfill:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/ops/backfill_active_reverse_trial_lifecycle.py'
   ```

5. Review the count, then run the same command with `--apply` while outbound
   writes are still disabled.
6. Complete the MailerLite MCP and received-message checklist above.
7. Preview due outbox decisions without claiming rows or contacting
   MailerLite:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --dry-run --limit 15'
   ```

8. Set `MAILERLITE_OUTBOUND_ENABLED=1` in production and restart the web service.
9. Monitor
   `/var/log/tradewave/mailerlite_lifecycle.log` and the outbox status counts.

The backfill schedules only future trial-expiry transitions. It does not insert
existing Explorer subscribers into a nurture sequence and does not send old
signup emails to people already partway through a trial.
The worker also suppresses any queued Day-0 enrollment that is more than 24
hours old, while preserving its scheduled trial-end reconciliation.
