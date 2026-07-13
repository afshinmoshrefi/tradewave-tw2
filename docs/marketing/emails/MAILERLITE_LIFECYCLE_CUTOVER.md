# MailerLite Lifecycle Cutover

Updated: 2026-07-13

All three workflows are real MailerLite drafts. They are intentionally inactive
until the application outbox is deployed and the email designs are reviewed.

## Live resources

| Journey | Trigger group | Automation | Timing |
| --- | --- | --- | --- |
| First signup trial | `lifecycle_trial_started` (`189853876367656773`) | [TW Lifecycle - Trial Started (7-day)](https://dashboard.mailerlite.com/automations/192896875220698599) | Day 0, 2, 4, 6 |
| Trial ended to Explorer | `lifecycle_trial_ended_explorer` (`192896580322330062`) | [TW Lifecycle - Trial Ended to Explorer](https://dashboard.mailerlite.com/automations/192896888595285340) | Day 7, 10, 14 |
| Former paid subscriber | `winback_explorer` (`192267699380815223`) | [TW Winback - Explorer (trust letter)](https://dashboard.mailerlite.com/automations/192267713628865734) | One day after paid access ends |

MailerLite MCP verification on 2026-07-13 found all three trigger groups empty,
all eight subjects populated, the expected 4/3/1 email steps, and no domain-auth
warning. Direct readback still showed MailerLite's generic plain-text fallback,
no visual design, and no preheader on all eight emails. The workflows remain
inactive and require the dashboard checklist below before activation.

The access group `explorer` (`97426012986410777`) is segmentation only. It
must not trigger a lifecycle automation. Do not backfill its existing members.

## MailerLite dashboard checklist

1. For every email, paste the matching `.html` file into the visual email. In
   the matching `.txt` file, skip the opening `Subject`, `Preview`, and `Send`
   metadata block and paste only the message body into MailerLite's plain-text
   version. Copy the preheader from the adjacent `subjects.md`. Keep the
   already-populated subject and the sender as TradeWave
   `<help@tradewave.ai>`.
2. On both new automation triggers, enable **Exit workflow when subscriber no
   longer matches the trigger**. The existing winback trigger already has this
   enabled.
3. Send one test of every email and verify links, mobile layout, unsubscribe,
   sender, reply-to address, and preheader. Keep MailerLite's automatic company
   footer enabled so the verified physical mailing address is included.
4. Verify `https://tradewave.ai/#pricing` shows Explorer, Navigator, Analyst,
   and Strategist with the same limits stated in the emails.
5. Keep all old Explorer and trial workflows inactive. Activate only these
   three, in this order: winback, trial-ended, trial-started.

MailerLite's automation API created the shells, triggers, delays, and subjects.
In this account, body and preheader updates did not persist through the API, so
the HTML, plain text, and preheaders must be completed and verified in the
dashboard. The two new exit toggles also remain a dashboard step.

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
6. Complete the MailerLite dashboard checklist above.
7. Preview due outbox decisions without claiming rows or contacting
   MailerLite:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --dry-run --limit 15'
   ```

8. Set `MAILERLITE_OUTBOUND_ENABLED=1` in production and restart the web service.
9. Monitor
   `/var/log/tradewave/mailerlite_lifecycle.log` and the outbox status counts.

The backfill schedules only future trial-expiry transitions. It does not insert
the 168 existing Explorer subscribers into a nurture sequence and does not send
old signup emails to people already partway through a trial.
The worker also suppresses any queued Day-0 enrollment that is more than 24
hours old, while preserving its scheduled trial-end reconciliation.
