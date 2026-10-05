# Retained October 5 publication continuation

Production currently runs2cc3167. Recovery stopped at46/49 with five articles fully approved, no publication and no newsletter release. All original/prior evidence and four original approvals are unchanged. Silver's independent review passes all substantive checks and records only advisory style feedback. Its accurate phrase "seasonal trend scaled to the last recorded price for the next60 weekdays" triggered a regex intended to reject claims of actual future prices.

Exact candidate **2d1de1a9c9f200fa29a2db7f9660f3527727b660** adds only a narrow directly preceding "scaled to the last" price-anchor exception and regression tests to2cc3167. It still rejects independent future-actual-price claims, including a later claim in a paragraph that also has an anchor. Same behavior live on Dev40e5a20.49 focused Linux tests and actual saved-review replay passed on the exact production candidate: all five completed articles and SI existing review validate with unchanged content/receipts. No model jobs ran during qualification.

**Only new exact release/direct execution approval is needed.** The49 cumulative ceiling and October5 snapshots are already approved. No new allowance or snapshot confirmation is requested. Remaining model jobs are SIhero, SIpixels and homepage inspection:3, bringing46 to49. No new article editing, research, writing or editorial review. Full publication is still unverified and any genuine failure remains a hold.

## Operator execution after approval

Record new human approval in `approval.json` with exact `source_commit`, current UTC `date`, `approved_by`, `execute_production_repair:true`, existing confirmed `production_web_snapshot:true`, `production_app_snapshot:true`, and `max_cumulative_jobs:49`. Preserve prior approval references. Transfer this directory to `/var/tmp/smn-oct5-final` on209.182.216.112, SSH4369. Scripts and approval root-owned; bundle readable by flask. Check bundle hash in release.json.

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-final/upgrade-production.py activate /var/tmp/smn-oct5-final/approval.json /var/tmp/smn-oct5-final/candidate-2d1de1a.bundle
systemd-run --unit=smn-oct5-final-recovery --wait --pipe --collect --property=Type=exec --property=EnvironmentFile=/etc/tradewave/secrets.env --property=WorkingDirectory=/opt/smn-subscription/releases/2d1de1a9c9f200fa29a2db7f9660f3527727b660/blog --setenv=HOME=/root --setenv=TZ=UTC --setenv=PYTHONDONTWRITEBYTECODE=1 --setenv=PYTHONPATH=/home/flask --setenv=PATH=/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=SMN_CAPTURE_LOCAL=1 --setenv=SMN_CODEX=/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex --setenv=SMN_CLAUDE=/root/.local/bin/claude --setenv=SMN_PLAYWRIGHT=/opt/smn-playwright/node_modules/playwright --setenv=SMN_BROWSER_CHANNEL=bundled /home/flask/venv/bin/python /var/tmp/smn-oct5-final/recover-final-production.py /var/tmp/smn-oct5-final/approval.json /var/tmp/smn-oct5-final/release.json
```

The wrapper copies the retained46-job root into an isolated sibling, verifies all five approvals plus SI's saved review, and clears only SI's held state. It preserves every original/previous root and all job attempts. SI gets its normal remaining visual checks, followed by six-article validation and guarded production publication. Canonical newsletter eligibility is checked before exposing the ready receipt; normal duplicate protections remain. No private comparison or test email. Code install alone is not success. Verify all six public URLs, desktop/mobile homepage, canonical receipt, source hashes, controller status and actual jobs after completion.

Code rollback restores2cc3167 while preserving recovery/publication evidence:

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-final/upgrade-production.py rollback /var/lib/tradewave/release-state/smn-oct5-repair-2d1de1a9c9f2-YYYY-MM-DD unused
```

Existing publication rollback handles live-site activation failures. Operator scripts are syntax/helper/review checked; production execution of this package is pending. No separate SMN staging host or TradeWave release is involved. Automatic observer/alert installation remains outside this repair.
