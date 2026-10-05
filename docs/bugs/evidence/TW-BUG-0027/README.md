# October 5 SMN targeted recovery

Status: **prepared, not executed in production**. Dashboard deployment is already live; this is a separate article-generation repair. Candidate `08f871493a639a504b49794d78315d223b87a870` contains the fixes on installed `d6e2b6fd59b15e2a601248df00073c078db24df4`, excluding unrelated membership/media changes. Dev main is `6f8ab7b2dc8b7b48634d0f5b8bb5d558fcc7d1da`.

## Evidence and remaining decisions

- 99 focused Linux tests passed, native publisher imports passed from an unrelated working directory, and captured production evidence was replayed on Dev. All four approved articles remain unchanged. The six-article recovery/publication has NOT run.
- Silver: accept real zero-padded publication dates, retry temporary retrieval failures within a fixed limit, and preserve successful sources. Three valid primary pages now pass using saved discovery evidence.
- NVIDIA: preserve its already-present quarterly facts; a source-quotation mismatch can receive one fresh independent review within the job cap. Missing facts and invalid evidence still block publication.
- The publisher now rejects incomplete selected editions before preparing or activating them; runtime assets are resolved and checked before a publication transaction.
- Minimum recovery is nine new jobs: silver five, NVIDIA three, landing review one. **37 + 9 = 46 cumulative minimum**. Further genuine failures can still hold the run. The ordinary 40-job default stays unchanged.
- Exact cap source is installed `blog/smn_daily.py:68` (`max_jobs=40`), invoked without an override by installed `blog/smn_subscription_daily.py:159`. It is a runtime code default, not a separately saved dashboard allowance. CLI documents retries included at installed `smn_daily.py:564`. The retained ledger contains 36 job directories and one failed attempt.
- Obtain explicit approval for this exact new production repair, direct agent execution if desired, a one-time cumulative cap of at least 46, and today's production web/app snapshots. Do not reuse the October 2 release exception or snapshots. No new generation jobs or production writes were made during preparation.
- SMN has Dev and production only (`AGENTS.md`, Environments; `smn_subscription_daily.py` documents operator installation after Dev qualification). There is no separate SMN staging host to deploy. No TradeWave application release is part of this package. Actual recovery still must pass all six articles and normal desktop/mobile/live publication gates.

Authority: `C:/Users/afshin/.codex/skills/tradewave-deployment-manager/SKILL.md`, Interpret authorization: "Never transfer approval to a different SHA, artifact, target, or later release." Production execution is reserved to Afshin/operator unless explicitly changed. `C:/Users/afshin/Documents/TradeWave Main Orchestrator/.claude/skills/prod-deploy/SKILL.md`, snapshot gate: "Do not rely on a confirmation from a prior session/day." SMN `AGENTS.md` also states production is read-only under existing authorization.

## Operator procedure after approval

1. Record the actual approval in `approval.json` with `date` (current UTC date), exact `source_commit`, `approved_by`, booleans `production_web_snapshot`, `production_app_snapshot`, `execute_production_repair`, and integer `max_cumulative_jobs`. Do not populate these as granted before the human response. This package is specifically for edition 2026-10-05.
2. Transfer this directory to `/var/tmp/smn-oct5-operator` on `root@209.182.216.112`, SSH port 4369. Keep scripts/approval root-owned and bundle readable by flask. Use only `candidate-08f8714.bundle`; the older `candidate.bundle` is obsolete and must not be used. Check its SHA256 against `release.json`.
3. Run the guarded code upgrade:

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-operator/upgrade-production.py activate /var/tmp/smn-oct5-operator/approval.json /var/tmp/smn-oct5-operator/candidate-08f8714.bundle
```

The upgrade records unit/config/pointer rollback state, checks the exact baseline, pauses timers, locks the controller, preflights imports, updates only the publishing and newsletter code pointers, and verifies effective working directories. This does not upgrade the separately deployed dashboard or run generation. Failed post-write checks trigger guarded restoration; unresolved rollback failures must remain stopped for inspection.

4. Execute recovery with the existing production environment (never print secret values):

```sh
systemd-run --unit=smn-oct5-recovery --wait --pipe --collect --property=Type=exec --property=EnvironmentFile=/etc/tradewave/secrets.env --property=WorkingDirectory=/opt/smn-subscription/releases/08f871493a639a504b49794d78315d223b87a870/blog --setenv=HOME=/root --setenv=TZ=UTC --setenv=PYTHONDONTWRITEBYTECODE=1 --setenv=PYTHONPATH=/home/flask --setenv=PATH=/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=SMN_CAPTURE_LOCAL=1 --setenv=SMN_CODEX=/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex --setenv=SMN_CLAUDE=/root/.local/bin/claude --setenv=SMN_PLAYWRIGHT=/opt/smn-playwright/node_modules/playwright --setenv=SMN_BROWSER_CHANNEL=bundled /home/flask/venv/bin/python /var/tmp/smn-oct5-operator/recover-production.py /var/tmp/smn-oct5-operator/approval.json
```

The recovery retains the original failed edition, clones into `2026-10-05/chatgpt-recovery-08f8714`, reopens only SI and NVDA, and preserves original receipts and four approved article trees. Publication happens only after all six pass. A rerun resumes saved work; after verified publication it only completes reporting/receipt finalization. It creates no private comparison and sends no test email. Once the canonical verified receipt is visible, the already-approved newsletter timer can send the normal edition, subject to existing duplicate prevention.

5. Verify all six live URLs, homepage desktop/mobile, publication receipt, source hashes, canonical `verified_reader_urls`, cumulative jobs, and controller completion. Confirm original failed evidence remains present. A code install alone is not success. Preserve any new failure and report actual stage; never reset the ledger or increase the allowance silently.

## Rollback

Use the printed code-upgrade record directory:

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-operator/upgrade-production.py rollback /var/lib/tradewave/release-state/smn-oct5-repair-08f871493a63-YYYY-MM-DD unused
```

Code rollback preserves recovery work and publication records; it does not unpublish a successful edition. Publication has its own existing guarded activation/rollback. Do not overwrite peer changes or delete a live lock. After rollback check recorded hashes, release pointer, effective units and timer states. Operator wrappers are syntax/review checked; no production rollback rehearsal or production execution is claimed. Actual Dev activation rollback was verified.

## Separate prevention gap

Read-only production evidence at 12:35 UTC: operational observer service/timer are not installed; dashboard saved alert settings/status and observer state are absent, deployed defaults disable alerts and have no recipients; nonplaceholder Resend key is absent. Installing/configuring the observer, recipients, thresholds and credential is a separate remaining operational task. This package does not claim alerts or 99.9% reliability are established.
