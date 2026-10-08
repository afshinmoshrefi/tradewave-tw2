# TW-BUG-0028: Webinar signup drops the published Zoom link

- Status: candidate tested on isolated task branch; runtime activation blocked
- Confidence: read-only production loader inspection reproduced the missing link; owner reported "This webinar is no longer available"; no real test registration submitted
- Priority: P2 - notification signup for the October 9 webinar cannot complete
- First observed / last updated: 2026-10-08 13:47 UTC / 2026-10-08 14:23 UTC
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
- First mapping commit: `abd82eea19d4a1792153953073e4ddd166e1a2fd`; final candidate identity is `git log -1 --format=%H` on this branch.
- Four runtime files: `webinar_schedule.py`, `config.py`, `web/email_utils.py`, `web/webinar_registration.py`. Against the recorded production baseline these contain only this concern: 23 insertions / 6 deletions.
- Required activation configuration: only `MAILERLITE_WEBINAR_REGISTRATION_ENABLED=1` in the qualified production web environment; preserve the existing false global switch and all unrelated flags.
- No React build, schema migration, replacement credentials, cron or firewall change required. Restart only affected web service once its qualified source/configuration is activated.
- Do not deploy whole main: it differs from production in 61 files. This branch is supporting candidate evidence, not an approved immutable release artifact. The existing qualified promotion process still requires canonical main/dev parity and a frozen exact artifact.
- Preserve previous source/runtime/frontend pointers and hashes plus web configuration. Rollback must restore the qualified previous source/pointer and webinar setting, restart only affected web service, rerun only the webinar generator and verify health/content. No `git reset --hard` or unclassified overwrite.

## Environment Verification and Blockers

Dev: not activated; shared October 5 activation lock is preserved. Staging:
qualification blocked before writes. `185.53.209.8:4369` refuses SSH from
Windows and dev; existing prod jump to documented `10.0.0.94` returns "No route
to host". `https://tw2-stage.trxstat.com/healthz` returns HTTP 530 / Cloudflare
1033. No alternate target, tunnel/firewall change or credentials were invented.

Production: existing listing sync verified, signup candidate not deployed.
Read-only inspection finds local rollback snapshots dated October 2 on both
production boxes. Those archives do not verify today's provider snapshots.
No existing provider snapshot API is available. Current-day October 8 snapshot
confirmations remain needed for `tw2-prod-web / 194.113.195.141` and
`tw2-prod-app / 138.128.240.115`. `.claude/skills/prod-deploy/SKILL.md` explicitly
states: "If either confirmation is absent, stop before every production write".
`docs/RELEASE_PROCESS.md` additionally requires staging approval of the identical
SHA/artifact, a qualified manifest and human execution of production writes.

The source correction independently needs the parent Google Drive connection
to regain Sheets editing scopes. Its approval already exists in the parent;
no further child source attempt should be made.

## History

- 2026-10-08 13:55 UTC, Codex: isolated loader mapping fix; dirty shared checkout and dev lock preserved.
- 2026-10-08 14:23 UTC, Codex: separate webinar permission and mocked actual-route tests complete; 50 pass. Staging connectivity, current-day production snapshot and source OAuth scope blockers recorded; no runtime activation.
