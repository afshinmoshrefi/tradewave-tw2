# TW-TASK-0018: SMN Membership Preview and Daily Briefing Foundations

- Status: in-progress
- Confidence: reproduced (source/policy baseline); implementation pending
- Priority: P2 - authorized product foundations, no production incident
- First observed / last updated: 2026-10-03T03:07:21.1037656Z
- Executor/session/claim time: Codex coordinator 01a0ff6b-e439-79a3-9aa3-9d70763f9e85 / 2026-10-03T03:07:21.1037656Z
- Authorization: Afshin authorized development kickoff with appropriate agents on October 2. First milestone P0/P1/P10 and P11 readiness only; parent owns integration/review.

## Goal, Scope and Acceptance

Canonical [implementation plan](TW-TASK-0018/implementation-plan.md). Build runnable offline public-derivative preparation/validation using retained article evidence, and separate dated daily-news briefing preparation/validation plus ElevenLabs avatar readiness. No reader billing/paywall implementation or commercial activation.

Claims (Codex, Sol 6.1 medium coding; unique child sessions owned by the coordinator):
- preview_builder: branch codex/smn-membership-preview-20261002; worktree C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-membership-preview-20261002. Owns blog/public_derivative.py, optional blog/schemas/public_derivative.schema.json, blog/tests/test_public_derivative.py, docs/preview-development.md and blog/examples/public-derivative/ (small manifests only). Next: inspect retained approved source bundles and implement offline source-bound derivative validation/preparation.
- briefing_builder: branch codex/smn-daily-briefing-20261002; worktree C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-daily-briefing-20261002. Owns blog/daily_briefing.py, blog/elevenlabs_briefing.py, blog/schemas/daily_briefing.schema.json, blog/tests/test_daily_briefing.py, blog/tests/test_elevenlabs_briefing.py, docs/daily-briefing-development.md and blog/examples/daily-briefing/ (small fixtures/reviewable artifacts only). Next: implement dated grouped-headline/claim-map validation and provider readiness adapter without generation.
- coordinator owns shared documentation, integration and review. Child session identifiers will be checkpointed when supplied; no peer approval is asserted.

Exclusions: existing pipeline/controllers, publisher/catalog, dashboard/admin authentication, TradeWave engine, billing/reader identity, scheduler/email/alerts, provider/model settings, paid model calls, provider media generation, external posts and production writes. Preserve TW-TASK-0009 recovery and TW-TASK-0017 administrator login/release ownership. All TradeWave values remain unchanged source exports.

## Evidence and Investigation

Fetched SMN origin/main 1663cecd62e0accf9dc9ff52f7c4a2f16e7f2e4f; shared origin/main 8d64eb364da3590c147497d99e1f72cb352c3d54. Root agent policies, coordination, shared indexes, release/Git policies and relevant claims reviewed. Planning observations are dated source observations, not current production verification.

Read-only tradewave-vm release-state check at 2026-10-03T03:07:21.1037656Z: active tw2-20261002-02 status failed, manager.state released, main_locked_sha null; tw2-20261002-01 status complete, manager.state released, main_locked_sha null; dev-activation.lock absent. This resolves older TW-TASK-0016 freeze prose for this documentation claim only; recheck before later integration/activation.

## Acceptance and Regression Checks

Focused offline tests must prove evidence/hash binding, direction and material caveat preservation, invalid/missing source rejection, dated cutoff/deduplication and explicit provider readiness failures. Three retained derivative pilots and one actual dated news narrative remain review deliverables; synthetic tests alone do not certify editorial quality. P11 readiness must identify supported account/model/avatar/voice access and unresolved dependencies without claiming generated media or automation. No original article regeneration.

## Implementation and Handoff

Shared branch codex/smn-membership-kickoff-record-20261002; worktree C:/Users/afshin/Documents/smn-membership-kickoff-record-20261002. Source branches start clean at fetched SMN main. Pushed implementation SHAs/tests: pending. Documentation claim commit identified by git log -1 -- docs/tasks/TW-TASK-0018.md and completion receipt. No config/migrations/build/runtime changes in this claim. Next: accepted shared claim is pushed/refetched, then coordinator authorizes child implementation in the above scopes; checkpoint exact commits/evidence and remaining pilot limits.

Knowledge checkpoint: task state and decisions use this canonical record and plan. No new implemented architecture exists to assert in ecosystem documentation; no private memory updates authorized or performed.

## Environment Verification

Dev: not deployed by this task. Staging: not checked; no SMN staging environment. Production: read-only, not deployed by this task. Current source baseline does not certify live runtime.

## History

- 2026-10-03T03:07:21.1037656Z, Codex coordinator: published non-overlapping foundation claim and canonical authorized plan copy; release-state read-only check permits documentation integration. Implementation, editorial pilot review and provider readiness verification pending.
Retained fixture discovery: OMC and LEN September17 have passing receipts under smn-review-20260917/engine-editorial. A qualified bearish fixture is missing; the three-article pilot remains partial until one is found and reviewed.
