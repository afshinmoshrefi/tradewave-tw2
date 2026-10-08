# TW-BUG-0028: Webinar signup drops the published Zoom link

- Status: candidate verified with isolated staging tests; live activation blocked
- Confidence: read-only production loader inspection reproduced the missing link; owner reported "This webinar is no longer available"; no real test registration submitted
- Priority: P2 - notification signup for the October 9 webinar cannot complete
- First observed / last updated: 2026-10-08 13:47 UTC / 2026-10-08 15:27 UTC
- Executor/session/claim time: Codex / webinar-zoom-field-20261008 / 2026-10-08 13:55 UTC
- Authorization: targeted signup repair and qualification reported by parent; no subscriber campaign, unrelated entry, global lifecycle enablement or broader production deployment

## User Impact and Reproduction

Production's Google Apps Script feed provides the meeting URL as `zoom url`.
The deployed `webinar_schedule.py` reads only `Webinar Link`, leaving
`webinar_url` empty. Registration rejects that session as unavailable before
notification-group updates. The public card and modal correctly show October 9,
2026 at 1:00 PM ET. Existing hourly sync was manually run successfully at
2026-10-08 13:43:34 UTC. A live read at 14:23 UTC still shows that session;
Last-Modified 14:00:06 UTC indicates the subsequent scheduled refresh.

The existing production configuration also keeps `MAILERLITE_OUTBOUND_ENABLED`
off. The mapping fix alone would proceed to HTTP 503 / "Registration is
temporarily unavailable." Turning on that shared flag would allow unrelated
application and lifecycle writes, so it was not changed.

## Evidence and Investigation

- Task base: origin/main `3bfa6b07ac38c61947e87a6a5335f1945a9bf795`.
- Production baseline: `c25ffd562dc3058ab41db5b07e9075dd841fb29b`.
- Production loader SHA-256: `d4484546ec09a209265398281a46963848f9015d4ca770c03ac56e89bae5307c`.
- Read-only loader check: source Zoom key present; legacy key absent; loaded URL empty.
- Existing production API key and general webinar group are configured; no new credentials are requested.
- Source: TradeWave Webinars, `webinar_schedule` row 2. October 9, `1:00 PM EST` source label, America/New_York timezone and meeting URL preserved. Actual event offset is UTC-04:00.
- The source text remains "100-Year Pattern begins" / "Day 1 of the 100-Year pattern". Parent's authorized D2:E2 correction failed `ACCESS_TOKEN_SCOPE_INSUFFICIENT`; reconnection with editing access is pending. Child did not retry or bypass it.
- No subscriber, campaign, source spreadsheet, main, runtime, secrets, cron or security mutation occurred during repair preparation.

## Acceptance and Regression Checks

1. Accept `zoom url` while retaining legacy `Webinar Link` compatibility and precedence.
2. Keep the private meeting URL out of public JSON.
3. Use server-controlled date, time, URL and exact dated group; retain general plus dated notification groups.
4. Add production-only, default-off `MAILERLITE_WEBINAR_REGISTRATION_ENABLED`. Internal `webinar_registration` scope can permit this flow with the global switch off; existing application/lifecycle calls retain their default guard.
5. Missing links, inactive subscribers and local opt-outs keep their no-write behavior. Unknown permission scopes are denied.
6. Mock all MailerLite operations, including the actual Flask route; never create a test subscriber.

Focused command:

`/home/flask/venv/bin/python -m pytest tests/test_webinar_schedule.py tests/test_webinar_registration.py tests/test_webinar_deploy.py tests/test_mailerlite_http.py tests/test_mailerlite_lifecycle.py -q`

Result: **50 passed in 1.96 seconds**. `git diff --check` passes. The actual Flask
route under mocked HTTP returns 200 for the valid mapped session with webinar
permission, 503 when disabled and 400 when its URL is missing. Success tests
verify general plus dated membership and correct October 9 / 1 PM ET / server URL
fields while the global switch remains false. Environment matrix and direct
reconciliation tests prove lifecycle and generic signup make no HTTP calls.
No production signup or notification delivery is claimed.

## Implementation and Handoff

- Branch: `codex/webinar-zoom-field-20261008`.
- Worktree: `/home/tradewave-worktrees/webinar-zoom-field-20261008` on dev.
- First mapping commit: `abd82eea19d4a1792153953073e4ddd166e1a2fd`. Tested runtime candidate: `0ed01f68201623f4f2e55bd32827fca10479bb1a`; later documentation-only commits preserve its runtime file hashes.
- Four runtime files: `webinar_schedule.py`, `config.py`, `web/email_utils.py`, `web/webinar_registration.py`. Against the recorded production baseline these contain only this concern: 23 insertions / 6 deletions.
- Required activation configuration: only `MAILERLITE_WEBINAR_REGISTRATION_ENABLED=1` in the qualified production web environment; preserve the existing false global switch and all unrelated flags.
- No React build, schema migration, replacement credentials, cron or firewall change required. Restart only affected web service once its qualified source/configuration is activated.
- Do not deploy whole main: it differs from production in 61 files. The complete immutable scoped artifact below is supporting candidate evidence, not an approved qualified release. The existing promotion process still requires canonical main/dev parity and explicit support for scoped artifact provenance.
- Preserve previous source/runtime/frontend pointers and hashes plus web configuration. Rollback must restore the qualified previous source/pointer and webinar setting, restart only affected web service, rerun only the webinar generator and verify health/content. No `git reset --hard` or unclassified overwrite.

## Environment Verification and Blockers

Dev: not activated; shared October 5 activation lock is preserved. The earlier
staging connectivity failure is resolved. At 14:41 UTC both staging servers
answer SSH and public `/healthz` returns HTTP 200 with DB/frontend healthy.
Both live checkouts are clean at `c25ffd562dc3058ab41db5b07e9075dd841fb29b`.
Web runs `/home/flask/web`; its unchanged frontend pointer is
`/home/flask/web-react/releases/build-c25ffd562dc3`, index SHA-256
`cd190cbaf8b4771778ea6fdff05c15ec3b8ab02b0e0cad6b0730560b4460187f`.

Exact candidate `0ed01f68201623f4f2e55bd32827fca10479bb1a` is preserved on
staging web in `/home/tradewave-webinar-qa/0ed01f68201623f4f2e55bd32827fca10479bb1a`.
There, all 48 unit tests pass (2.07 seconds); two database tests are deselected
because no dedicated local `tradewave_test` database exists on staging web or
app. The earlier unfiltered staging attempt reports 48 passed / 2 fixture
errors from connection refusal to local test Postgres, never the application DB.
Those two DB tests passed on dev in the 50-test focused result above.

At 14:50 UTC, an additional isolated actual-Flask-route check reads the real
published Google feed directly without touching its shared cache. It verifies
the October 9 13:00-04:00 session and exact source Zoom URL. With subscriber HTTP
fully mocked and only in-process configuration simulating the webinar production
opt-in, the route returns 200, confirms general plus dated membership and correct
date/time/URL fields, and proves lifecycle HTTP calls remain zero. Live staging
flags are unchanged; no real registration, subscriber or email operation occurs.

Four-file runtime archive:
`/home/tradewave-webinar-qa/webinar-signup-runtime-0ed01f682016.tar`, SHA-256
`aee361de6d6bccc657684c95f5f4e0c31baa67a30b9dfe7564e004674a9587f7`.
This is a tested scoped candidate, not a staging-approved immutable release.
No public staging service/pointer was activated. Full qualification/promotion
still requires canonical main/dev parity and the exact qualified manifest;
`ops/deploy.sh` enforces origin/main and updates both tiers, frontend, static
pages and other services. Using it would include unrelated current-main changes.
Do not bypass that gate or copy the four files into a live checkout. A reviewed
narrow promotion path must resolve that conflict before live activation.

Production: existing listing sync verified, signup candidate not deployed.
Read-only inspection finds local rollback snapshots dated October 2 on both
production boxes. Those archives do not verify today's provider snapshots.
No existing provider snapshot API is available. Current-day October 8 snapshot
confirmations remain needed for `tw2-prod-web / 194.113.195.141` and
`tw2-prod-app / 138.128.240.115`. `.claude/skills/prod-deploy/SKILL.md` explicitly
states: "If either confirmation is absent, stop before every production write".
`docs/RELEASE_PROCESS.md` additionally requires staging approval of the identical
SHA/artifact, a qualified manifest and human execution of production writes.

## Complete Immutable Candidate and Release Review

`ops/webinar_artifact.py` implements candidate-only `build`, `verify`,
`materialize` and `plan`; no action activates a service. It reconstructs the
entire committed baseline plus exactly four pinned tested repair files, rejects
extra/tampered files and changed scope, refuses output overwrites and source
checkout writes, and preserves identical archive bytes during transport.
`ops/check_webinar_artifact.py` cold-imports the actual complete web runtime and
uses a private cache and fully forbidden/mocked subscriber HTTP for QA.
The preparation controls have 14 focused integrity/scope unit checks.
The final combined six-file focused suite passes **64 tests in 4.78 seconds** on
dev, including both dedicated-test-DB cases; `git diff --check` passes.

Complete package on dev and staging web:
`/home/tradewave-webinar-artifacts/20261008-baseline-c25ffd-repair-0ed01f`.
Its committed production baseline is `c25ffd562dc3058ab41db5b07e9075dd841fb29b`;
repair source is `0ed01f68201623f4f2e55bd32827fca10479bb1a`. Of 2,697 tracked
files, 2,693 are preserved exactly and only the four tested paths are replaced.

- Complete archive SHA-256: `4e40858ac16075c68799a0086a853a890aaffb5c7ef254e95a7fe04164eb7e5f`.
- Complete inventory SHA-256: `4029a3514beeabf83ab736c755ae843a967aa59759671bcd7364547b763b4a29`.
- Actual complete-payload staging tests: **48 passed, 2 deselected in 1.93 seconds**.
  The dedicated staging test DB is absent; the two DB cases passed on dev.
- Fresh cold-process probe at **15:27:01 UTC**: app and all repair modules load
  from that payload; actual source group/date/offset/Zoom URL match. The disabled
  valid registration reaches **503 with subscriber HTTP forbidden**, followed
  by **200 under fully mocked provider HTTP** with correct general/dated groups
  and fields. Global lifecycle permission stays off, lifecycle HTTP calls and
  real subscriber writes are zero, and no shared cache is touched.
- Frontend startup preflight: all 21 live frontend files copied privately with
  identical before/copy/after inventories. Payload checker passes with
  "React shell and manifest assets ready" against that private copy. Inventory
  SHA-256 `3ca22b93e72e16f7b3bca78f79904ed2b800b25b4ddce2751564867b0dcf9284`;
  staging receipt `/home/tradewave-webinar-artifacts/frontend-qa-receipt-20261008.json`.
  Live frontend pointer, web unit/process and clean baseline remain unchanged.

Independent review confirms the existing manifest semantic validator requires
promotion source to equal canonical locked main and every frontend `source_sha`
to equal that release SHA. There is no typed scoped baseline/overlay mode for
this complete candidate and preserved older frontend. Canonical source
integration and an explicit reviewed scoped provenance/process addition are
still required before any live activation. Do not relabel the older frontend's
source, loosen global gates, fabricate approval, or deploy unrelated main work.
Concrete `plan` output supplies the proposed web drop-in and rollback boundaries
but marks execution disallowed. Current-day snapshot confirmations and human
production execution remain required. See `docs/WEBINAR_SCOPED_CANDIDATE.md`.

The source correction independently needs the parent Google Drive connection
to regain Sheets editing scopes. Its approval already exists in the parent;
no further child source attempt should be made.

## History

- 2026-10-08 13:55 UTC, Codex: isolated loader mapping fix; dirty shared checkout and dev lock preserved.
- 2026-10-08 14:23 UTC, Codex: separate webinar permission and mocked actual-route tests complete; 50 pass. Staging connectivity, current-day production snapshot and source OAuth scope blockers recorded; no runtime activation.
- 2026-10-08 14:50 UTC, Codex: owner reports staging on; fresh SSH and public health confirm recovery. Exact candidate passes 48 staging unit tests and mocked actual-route check against the real source. Scoped archive hash recorded; live release path and production prerequisites remain blocked.
- 2026-10-08 15:27 UTC, Codex: complete baseline-plus-four-file immutable candidate transported and independently verified on staging; complete-payload unit/cold-import/no-sending and private frontend checks pass. Candidate preparation tools added without changing release policy, main, shared pointers or live runtime. Exact scoped provenance and snapshot/operator blockers retained.
