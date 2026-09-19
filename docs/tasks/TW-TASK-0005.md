# TW-TASK-0005: Subscription daily SMN Dev workflow

- Status: in-progress
- Confidence: reproduced
- Executor: Codex smn-daily-worker-20260919
- Claim: 2026-09-19T13:38:22.346282+00:00
- Authorization: build and prove daily subscription workflow on Dev; production unchanged.

## Scope and Acceptance
Reuse Astra xhigh ChatGPT writer, preserve TradeWave mathematics, add durable edition state and duplicate prevention, explicit held recovery, source/editorial/visual gates, Dev-only publication. No API fallback. Existing Windows login is the initial worker. Daily schedule through Codex automation; no production schedulers changed. Check authentication without reading credentials. Prove repeat/resume/failure behavior with focused tests and live Dev status; avoid full article regeneration solely for tests.

## Work and Handoff
SMN base 1d366e70a3e6e01b58212a5a841814e013a21ac2; task branch codex/smn-daily-worker-20260919, local worktree smn-daily-worker-20260919. Shared records in this task worktree. Next: implement controller, verify, activate on Dev, document scheduler and rollback. No code edits yet. Previous Dev edition stays visible until a complete passing new package is available.

## Environment
Dev pending; staging/production not deployed by this task.

## Budget Checkpoint, September 19
Stopped at the usage boundary (weekly account readouts 0% initially, 3% at stop). No scheduler, runtime activation, production writes or article generation. ChatGPT login and Astra xhigh availability verified with zero model turns. SMN branch codex/smn-daily-worker-20260919 WIP 54dd53b99e31e4d8feaff160121edb3923ca0429 is NON-DEPLOYABLE. Controller repair and publisher repair were interrupted; controller file may be absent during rewrite. Source capture live attempt held on remote read failure; not diagnosed. Tests on earlier partial drafts are not acceptance proof. Existing September17 Dev source remains 1d366e70a3e6e01b58212a5a841814e013a21ac2.

Next: finish/review controller checkpoint and lock recovery, verify publisher generated wrapper syntax, lock-before-main-check handshake, interruption and mandatory live/source/hash checks; diagnose capture transport; realistic focused tests incl Linux installer; operational runbook; automation_update daily schedule only after verification; exact-source Dev activation with rollback and live smoke. Do not schedule WIP. Files and local worktree: smn-daily-worker-20260919 under TradeWave Main Orchestrator. Shared task remains in-progress at budget boundary, not complete.
