# Complete webinar candidate preparation

`ops/webinar_artifact.py` prepares and verifies a complete immutable candidate.
It has no live activation action. It does not change `ops/deploy.sh`, the release
manifest validator, canonical main/dev parity, snapshot requirements or the human
production-operator boundary.

The payload contains every tracked file from production baseline
`c25ffd562dc3058ab41db5b07e9075dd841fb29b`, replacing only `config.py`,
`web/email_utils.py`, `web/webinar_registration.py` and `webinar_schedule.py`
with their exact tested bytes from `0ed01f68201623f4f2e55bd32827fca10479bb1a`.
The tool pins all four repair hashes. Changes elsewhere in the overlay source
are excluded; different bytes inside an allowed path are also rejected.

Run as `flask`, outside operational/source checkouts:

```bash
python ops/webinar_artifact.py build --repo . \
  --baseline c25ffd562dc3058ab41db5b07e9075dd841fb29b \
  --overlay 0ed01f68201623f4f2e55bd32827fca10479bb1a \
  --output /home/tradewave-webinar-artifacts/20261008-baseline-c25ffd-repair-0ed01f
```

The sidecar manifest records both commits, all file hashes/modes, the inventory
fingerprint and deterministic archive hash. `verify` reconstructs the entire
recipe independently from Git and checks payload plus archive. `materialize`
accepts the original manifest/archive transport, validates against Git before
writing anything, and preserves the identical archive bytes. Existing outputs
are never overwritten. Payload files/directories and archive are read-only.

Use `check_webinar_artifact.py --artifact <package>` in a fresh staging process.
It cold-imports the real Flask app from that payload, verifies all repaired
module paths, checks the real source's valid session reaches HTTP 503 while
provider calls are forbidden, then verifies HTTP 200 using fully mocked provider
operations. It uses a private temporary source cache and test-only configuration;
it submits no real registration and sends no email. Keep the live frontend
pointer unchanged. For private preflight, copy its resolved artifact into a
separate QA directory, compare every file hash before and after copying, and run
the payload's `python -m web.react_build` with `TW2_REACT_BUILD_DIR` set to that
verified private copy. Record the original pointer and unchanged fingerprints.

`plan` emits concrete web-only systemd drop-in and rollback review material,
explicitly marked `execution_allowed=false`. It preserves the appserver, React,
nginx, database and SMN jobs and keeps the global MailerLite flag off. It is not
an executable deployment command or a qualified release approval.

Before live activation, integrate the source into canonical main and establish
explicit reviewed release-policy support for the scoped baseline-plus-overlay
artifact. The current complete-tree/main parity rule cannot silently be bypassed.
Retain existing targeted repair approval for identical bytes, all qualification
and rollback gates, current-day production web/app snapshots and human execution.
Record final source, artifact and configuration provenance in the qualified
manifest. TW-BUG-0028 owns current test evidence and blockers.

## Verified complete candidate

The package at the path above contains 2,697 tracked baseline files. Exactly
2,693 remain byte-for-byte and mode-for-mode identical to production; the four
hash-pinned repair files are the only replacements. Dev and staging retain the
same original archive bytes:

- Payload archive SHA-256: `4e40858ac16075c68799a0086a853a890aaffb5c7ef254e95a7fe04164eb7e5f`.
- Inventory SHA-256: `4029a3514beeabf83ab736c755ae843a967aa59759671bcd7364547b763b4a29`.
- Final dev suite: 64 passed in 4.78 seconds, including 14 candidate-integrity
  checks and both dedicated-test-DB cases; `git diff --check` passes.
- Staging tests against that complete payload: 48 passed, 2 DB tests deselected
  (dedicated local test DB absent); these DB tests passed on dev.
- Fresh cold-process check at 2026-10-08 15:27:01 UTC: all app/repair imports
  resolve inside the payload; the actual source session reaches HTTP 503 with
  subscriber HTTP forbidden, and HTTP 200 with fully mocked provider operations.
  Source URL, general/dated groups and server date/time fields match; lifecycle
  HTTP calls and real subscriber writes remain zero.
- The payload's startup frontend checker passes against a private, verified
  copy of all 21 existing frontend files. Its inventory SHA-256 is
  `3ca22b93e72e16f7b3bca78f79904ed2b800b25b4ddce2751564867b0dcf9284`.
  The live frontend and service state are unchanged.

## Independent release review

Current `ops/validate_release_manifest.py` requires
`main_locked_sha == release_sha == remote_main_sha` for promotion and requires
every `artifacts.frontend[*].source_sha == release_sha`, including preserved
frontend artifacts. The existing typed manifest has no scoped baseline/overlay
artifact mode. A canonical merge alone does not resolve those requirements.

An explicit reviewed process addition must record the actual production
baseline, canonical repair source, complete payload inventory/archive identity,
and unchanged frontend's actual source/hash, while retaining qualification,
approval binding, snapshot, rollback and operator checks. Do not relabel the old
frontend as built from a new release SHA, fabricate approval fields, relax the
global validator, or treat this candidate sidecar as a qualified release
manifest. No live activation is supported by these preparation tools.
