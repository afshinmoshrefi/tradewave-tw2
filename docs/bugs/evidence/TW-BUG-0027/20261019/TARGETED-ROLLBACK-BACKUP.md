# Targeted SMN rollback backup verified

Afshin explicitly approved the tested bounded SMN deployment and four prepared
image repairs at **2026-10-19 16:17:01 UTC**, reply "I approve", reference
`Sentinel_d4de0cc2fec0819183cb687d32d4a8c4`. The parent supplied that transcript and
expressly authorized this targeted backup preparation. The approval remains
conditional on the required full-server backup. Subscriber mail is excluded.

At **2026-10-19T16:19:45.155575+00:00**, an actual backup of **six existing files** was captured on
seasonalmarketnews / 209.182.216.112: the three managed change targets (activation
JSON and two pinned base units) plus their three existing drop-in files. Each
backed-up preimage was restored into a private rehearsal file using the retained
atomic primitive. **Bytes, mode, UID and GID all matched.** A private source-pointer
restore also resolved to the retained 2b0075c release. Six old runtime-module
hashes were checked against the frozen baseline.

On-server root: `/var/tmp/smn-targeted-rollback-backup-20261019-0g4qf6jf`.
Manifest: `backup-manifest.json`.
Manifest SHA256: `8a0e49122d96012893c102be980c179720f1f647dd9392c2c295bf93d0744932`.
Private preimage contents stayed on-server; only verification metadata returned.
See [backup proof](targeted-rollback-backup-proof.json) and
[approval evidence](conditional-live-approval.json).

**This is not a full-server backup and does not satisfy or replace that
prerequisite.** Full-server backup completion remains unconfirmed. Do not activate
the code or publicly backfill the four images until that condition is met. The
three managed files, current pointer, existing units/timers, publication receipt
and mail journal remain unchanged. No existing lock was acquired and no job was
interrupted. No provider/model/image call or subscriber send occurred.

Keep the backup and retained old release intact. Refresh all baseline hashes,
ownership, current pointer and service custody immediately before later use.
The mail journal was neither copied into this rollback backup nor restored;
never restore stale campaign state over newer provider activity.

Application remains the approved candidate 55afe01a. Four GS/PGR/XLK/MRK image
overrides are prepared and unpublished; C remains unresolved. New standing
permissions are unnecessary. The parent needs the remaining full-server backup
confirmation, not another approval for the same deployment/four repairs.
