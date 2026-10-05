# October 5 citation repair continuation

**Prepared, not authorized or deployed.** Production currently runs08f8714; its recovery stopped at43 cumulative jobs with SI/NVDA held and no publication. Original evidence and all four approved articles are hash-verified unchanged. No October5 newsletter started. The code deployment itself succeeded.

Next exact production candidate: `2cc3167a435065843bb2b8834a750e7213fb75ec`, only the citation matcher and its regression tests added to08f8714. The same change is live on Dev at `afd6f2e650d2155366e6a05508ee1fe7111a60ed`.49 focused Linux tests and actual captured-review replay passed, without generation jobs. See `dev-contract-proof.json` and `dev-activation-proof.json`.

## What this fixes

The reviewer copied rendered source references such as `[1]`, while the gate compared against article text without those references. It now recognizes only reference numbers belonging to the actual source-bound units; substantive text, source IDs, factual checks and quote reading order remain strict. An otherwise passing review with reversed exact spans gets one new review, not an automatic rewrite.

NVIDIA's saved fresh review now passes all eight required source-bound quotations and can be reused. Silver's first review reversed two quotation spans, and both its original and revised draft contain the unsupported phrase "a normalized average seasonal path" (revised wording varies). The originally proposed unconditional restoration of the first draft is superseded: restore its shorter original text, then use the existing receipt-bound `Edition.copyedit` operation to replace exactly that phrase with "a section of TradeWave’s seasonal trend scaled to the last recorded price". This matches the immutable chart caption. Preserve writer receipts, save the copyedit receipt, and require a fresh independent review. No invented model receipt or manually passed approval.

Minimum remaining jobs: one fresh SI review, two hero inspections, two article pixel inspections and one homepage inspection =6. **43 + 6 =49 cumulative minimum**, three above the current46 allowance. Normal daily40 cap remains unchanged. Further genuine failures can still hold the edition; no guaranteed success claim.

## Required decision

Approve candidate2cc3167 for direct production execution and a one-time49 cumulative cap. Today's web/app snapshots were already explicitly confirmed in coordinating chat turn01a10c26-cd6f-7a62-a18f-4f24c568b241; do not ask for that confirmation again on the same day. The new SHA and higher cap are not covered by approval of08f8714/46. Deployment skill: "Never transfer approval to a different SHA, artifact, target, or later release."

## Execute only after approval

Record approval in `approval.json`: exact `source_commit`, current UTC `date`, `approved_by`, `execute_production_repair:true`, existing confirmed `production_web_snapshot:true` and `production_app_snapshot:true`, and `max_cumulative_jobs:49`. Include the new human approval evidence. Copy this directory to `/var/tmp/smn-oct5-citations` on209.182.216.112, SSH4369; root owns scripts/approval and flask can read the bundle.

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-citations/upgrade-production.py activate /var/tmp/smn-oct5-citations/approval.json /var/tmp/smn-oct5-citations/candidate-2cc3167.bundle
```

The reviewed upgrade is the same guarded mechanism used successfully for08f8714, pinned to its current baseline and the new exact candidate/bundle. It snapshots units/config/pointer, locks, preflights, activates, checks effective units and restores on failed post-write checks. Recovery wrapper:

```sh
systemd-run --unit=smn-oct5-citation-recovery --wait --pipe --collect --property=Type=exec --property=EnvironmentFile=/etc/tradewave/secrets.env --property=WorkingDirectory=/opt/smn-subscription/releases/2cc3167a435065843bb2b8834a750e7213fb75ec/blog --setenv=HOME=/root --setenv=TZ=UTC --setenv=PYTHONDONTWRITEBYTECODE=1 --setenv=PYTHONPATH=/home/flask --setenv=PATH=/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin --setenv=SMN_CAPTURE_LOCAL=1 --setenv=SMN_CODEX=/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex --setenv=SMN_CLAUDE=/root/.local/bin/claude --setenv=SMN_PLAYWRIGHT=/opt/smn-playwright/node_modules/playwright --setenv=SMN_BROWSER_CHANNEL=bundled /home/flask/venv/bin/python /var/tmp/smn-oct5-citations/recover-citations-production.py /var/tmp/smn-oct5-citations/approval.json /var/tmp/smn-oct5-citations/release.json
```

It clones the retained43-job recovery into a separate sibling, keeps both older failed roots and all receipts, applies the explicit one-phrase copyedit, and runs only remaining work. Publication requires all six articles and existing desktop/mobile/live checks. It verifies newsletter eligibility before exposing the canonical receipt and preserves duplicate-send protections. No private comparison or test email; the existing ordinary newsletter may send after verified publication.

Code rollback, using the printed record:

```sh
/home/flask/venv/bin/python /var/tmp/smn-oct5-citations/upgrade-production.py rollback /var/lib/tradewave/release-state/smn-oct5-repair-2cc3167a4350-YYYY-MM-DD unused
```

This restores08f8714 without erasing retained recovery work or unpublishing an already verified edition. Normal publication has its own guarded rollback. The new wrapper is reviewed/syntax checked; production execution has not happened. SMN has Dev/production, no separate staging host or TradeWave application promotion in this package. Observer installation/settings/Resend remain separate follow-up work.
