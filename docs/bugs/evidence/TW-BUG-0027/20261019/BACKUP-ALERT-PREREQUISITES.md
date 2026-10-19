Current update: exact bounded deployment/four-image approval has arrived.
Targeted rollback preimages are restore-verified; required full-server backup
completion is still unconfirmed. See [current backup proof](TARGETED-ROLLBACK-BACKUP.md).

# Minimal SMN backup and alert prerequisites

The bounded live cutover and four public hero repairs were explicitly approved
by Afshin at 16:17:01 UTC. Required full-server backup completion is still
unconfirmed, so deployment and public backfills remain held. Targeted rollback
preimages were captured and restore-verified at 16:19 UTC under that approval;
they do not replace the full-server prerequisite. No live activation, public
backfill, alert configuration or sending occurred. Candidate 55afe01a and its
passing qualification remain unchanged. No new standing permission or review-
policy change is requested.

## Backup: provider ID is not inherently mandatory

The retained October 9 operator's `snapshot_attestation` accepts
`human-confirmed-current-day` evidence for actual SMN. It requires Afshin's current
UTC-day confirmation of completion, exact target, genuine evidence/confirmation
reference and source/operator/baseline/artifact bindings. It explicitly leaves
unknown provider, snapshot-reference and exact completion-clock fields **null**.
An adequate current-day confirmation must not be held for an invented provider ID.
This corrects the earlier overly specific request for provider/clock details.

No current completed full-server backup was established by the permitted local
inspection; a provider-side backup may exist. Existing root access and installed
tar/rsync can create a checksum-verified rollback backup of this cutover's three
managed files, current pointer and prior unit/timer metadata once approved. The
old immutable 2b0075c release is retained. Native private atomic/restore cases have
passed as root. Verify new preimages by restoring copies in a private directory
and comparing bytes, modes and ownership before applying the cutover.

That targeted backup supports rollback of the bounded code change. It is not a
complete server/VM snapshot and does not cover disk loss or all mutable data. It
cannot silently replace the existing current-day server-backup gate. If that is
the intended alternative, Afshin must explicitly accept the narrower scope in
the pending bounded decision. Otherwise obtain current-day confirmation of the
actual existing SMN backup. No new provider account, purchase or credential is
needed merely to capture targeted rollback files.

Btrfs/LVM commands are installed, but actual volumes/filesystem/free extents were
not established. Tool presence alone does not prove guest snapshot capability.
No filesystem freeze, volume snapshot, database dump or provider call was made.

## Alerts: concrete missing inputs

The implemented operational observer uses **Resend HTTPS**. Its prior permitted
inventory found no observer units, disabled alerts, an empty recipient list and
no Resend key in the designated secrets file. The fresh capability-only check
found no sendmail, Postfix, Exim, msmtp, mail/mailx or ssmtp command. This does not
prove that no Python/API SMTP route could exist; such a route is unverified.

The existing MailerLite helper manages subscriber campaigns and groups. It is
not an operational-alert adapter and must not be repurposed to send subscriber
mail. Sender addresses are not verified alert recipients.

Minimum monitoring prerequisites are one named authorized operator recipient,
a usable existing Resend credential through the established secret store (or
specific approval for another transport/setup), and approved observer settings/
installation. Then perform one explicitly authorized operator-only delivery
exercise and retain matching delivered-provider evidence. No credential creation,
configuration change or test message occurred here. Actual alerts remain unproved.

Automatic approval review rejected the broader configuration/storage/recipient/
credential-metadata export. The safe command-availability check succeeded without
reading or exporting those fields. A detailed audit, if still needed, requires
explicit authorization for its exact metadata and local destination; it was not
retried by an indirect route.
