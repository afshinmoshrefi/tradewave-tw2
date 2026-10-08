# TW-BUG-0028: Webinar signup drops the published Zoom link

- Status: fixed in isolated task branch; production deployment blocked
- Confidence: reproduced by read-only loader inspection; owner reported the exact public error "This webinar is no longer available"; no test registration was submitted
- Priority: P2 - the listed future webinar's notification signup cannot complete
- First observed / last updated: 2026-10-08 13:47 UTC / 2026-10-08 13:55 UTC
- Executor/session/claim time: Codex / webinar-zoom-field-20261008 / 2026-10-08 13:55 UTC
- Authorization: prepare and test the field-mapping fix; owner production approval reported at 2026-10-08 13:51:42 UTC. Required staging, snapshot and operator gates still apply. No unrelated application changes or subscriber campaign.

## User Impact and Reproduction

Production's Google Apps Script feed provides the meeting URL as `zoom url`.
`webinar_schedule.py:90` reads only `Webinar Link`, leaving `webinar_url` empty.
`web/webinar_registration.py:99-101` rejects that session before notification-group updates.
The public card and registration modal show October 9, 2026 at 1:00 PM ET.
The manual existing hourly sync succeeded at 2026-10-08 13:43:34 UTC.

## Evidence and Investigation

- Base: origin/main `3bfa6b07ac38c61947e87a6a5335f1945a9bf795`.
- Production loader SHA-256: `d4484546ec09a209265398281a46963848f9015d4ca770c03ac56e89bae5307c`.
- Read-only loader check: source Zoom key present; expected legacy key absent; loaded meeting URL empty.
- Browser card and modal verified; no production registration or subscriber write performed.
- Source: TradeWave Webinars, `webinar_schedule` row 2; date/time and meeting URL are preserved.
- Source-copy correction is separately blocked: automatic approval review rejected the delegated approval as insufficient direct source-edit authorization. The source text remains unchanged.

## Acceptance and Regression Checks

1. Accept the published `zoom url` field while retaining `Webinar Link` compatibility and precedence.
2. Keep meeting URLs out of browser-facing JSON.
3. Registration uses the verified server schedule and retains general plus dated notification groups.
4. Missing links, inactive subscribers and disabled environments retain their existing no-write behavior.
5. Unit tests mock all MailerLite operations; no test subscriber is created.

Focused tests: `python -m pytest tests/test_webinar_schedule.py tests/test_webinar_registration.py tests/test_webinar_deploy.py -q` - 17 passed in 0.34 seconds. `git diff --check` passes. These tests mock MailerLite calls and assert both general and dated notification-group membership plus the server-controlled meeting URL. No external subscriber writes occurred.

Production's existing secrets configuration reports `MAILERLITE_OUTBOUND_ENABLED` disabled, and the effective web unit has no assignment overriding this flag. Both registration and `_reconcile_managed_groups` enforce this shared guard. Fixing the URL alone therefore leaves the subsequent disabled-registration path, which maps to HTTP 503 / "Registration is temporarily unavailable." Enabling this global flag also enables other application/lifecycle writes; that broader activation is outside this concern and was not performed.

## Implementation and Handoff

- Branch: `codex/webinar-zoom-field-20261008`.
- Worktree: `/home/tradewave-worktrees/webinar-zoom-field-20261008` on TradeWave dev.
- Runtime change: `webinar_schedule.py`, one-line fallback for the published source header only; legacy `Webinar Link` retains precedence.
- Tests: `tests/test_webinar_schedule.py`, `tests/test_webinar_registration.py`.
- No React build, schema migration, new credentials, cron or security change required.
- Runtime activation must reload the existing web process that imported the loader.
- Rollback: preserve the prior loader/release artifact and web runtime pointer, restore the exact prior artifact/pointer, restart only the affected web service, then rerun the existing webinar generator and verify restored hashes/health.
- Pushed commit: identified by `git log -1 -- docs/bugs/TW-BUG-0028.md`; qualified release identity pending.
- Production baseline: `c25ffd562dc3058ab41db5b07e9075dd841fb29b`, web service working directory `/home/flask/web`. Current main differs in 61 files, so deploying all current main would violate this task's no-unrelated-changes scope.
- Production gates still missing: current-day confirmations for both server snapshots, same-artifact staging approval, qualified release manifest and designated human operator execution. The snapshot rule is `.claude/skills/prod-deploy/SKILL.md`; promotion/operator rules are `docs/RELEASE_PROCESS.md`.
- Shared default-branch claim was rejected by automatic approval review; preserve this reviewed concern on its task branch instead. No default-branch or runtime write was made.
- Next action: resolve the separate webinar-write enablement policy and source-edit authorization, then qualify the exact scoped artifact through current production gates; never enable the global lifecycle flag or deploy unrelated main changes merely to repair this form.

## Environment Verification

Dev: not activated. Staging: not checked. Production: listing sync verified; signup fix not deployed.

## History

- 2026-10-08 13:55 UTC, Codex: claimed scoped loader fix. Existing shared checkout and old dev activation lock are preserved; no runtime mutation.
