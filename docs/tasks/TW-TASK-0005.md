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
