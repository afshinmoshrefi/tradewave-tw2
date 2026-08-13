---
name: prod-deploy
description: Enforce the TradeWave production snapshot approval gate. Use together with the TradeWave deployment-manager skill whenever deploying, promoting, releasing, rolling back, or preparing changes for production.
---

# TradeWave production gate

First follow `.claude/skills/tradewave-deployment-manager/SKILL.md`,
`docs/RELEASE_PROCESS.md`, and the current `ops/OPERATIONS.md`. This skill adds one gate; it
does not replace release ownership, immutable artifact, staging approval, active-runtime,
contract, browser, or rollback requirements.

## Require current-day snapshots

Before any production-affecting deployment of new code, require Afshin to confirm in the
current release conversation that both of these snapshots were taken on the current date:

- production web server;
- production appserver.

If either confirmation is absent, stop before every production write and ask whether today's
web and appserver snapshots are complete. Do not infer confirmation from an earlier day,
session, release, or general statement that backups exist.

Tie the confirmation to the exact release SHA and artifact hashes in the release manifest.
Record the snapshot references and approval time without recording secrets.

## Continue only through the shared process

After the snapshot gate passes:

1. Confirm the identical SHA and artifacts passed staging and have explicit staging approval.
2. Require explicit production approval for that exact release.
3. Re-run non-mutating production preflights and verify rollback commands.
4. Follow the current command path in `ops/OPERATIONS.md`.
5. Independently verify effective systemd units and drop-ins, live process paths, backend
   fingerprints, frontend pointers and hashes, contracts, and rendered browser behavior.
6. Roll back on any mandatory-gate failure and record the resulting live state.

Never use stale server details embedded in a skill as operational authority. Read the current
runbook and manifest for every production release.
