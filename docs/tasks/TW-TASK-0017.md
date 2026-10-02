# TW-TASK-0017: Direct WorkOS login for the SMN dashboard

- Status: in-progress
- Executor/session: Codex smn-workos-login-20261002 / 01a0fd8d-64bf-7741-bc34-89f5d326c05d
- Authorization: Afshin approved giving SMN its own WorkOS login using existing accounts while preserving TradeWave admin authorization. Implementation and verification start on Dev. No production promotion is part of this development claim.
- Scope: SMN dashboard human login, callback, logout/session handling; a narrowly scoped TradeWave admin authorization contract if needed. Preserve service/API keys and existing dashboard functions. No paywall, account provisioning, publication, scheduler, model, or billing changes.
- Branch: codex/smn-workos-login-20261002 in both repositories.
- Worktrees: Windows orchestrator/smn-workos-login-20261002 (SMN); /home/tradewave-worktrees/smn-workos-login-20261002 on TradeWave Dev.
- Coordination: TW-TASK-0006 and TW-TASK-0008 reviewed. TW-TASK-0009 production recovery remains independently owned; its pending activation is not taken over. TW-TASK-0016 live manifest is complete with manager released. Current TradeWave main includes subsequent Scenario Studio styling.
- Acceptance: Start login on SMN, authenticate with existing WorkOS users, return directly to SMN; only current TradeWave super_admin users admitted. Reject invalid/expired/replayed callbacks, denied users and cross-environment identities; verify logout, session expiry and unchanged machine authentication. Prove a real Dev browser login before claiming completion.
- Next: implement minimal direct AuthKit integration and central admin authorization; provision a separate SMN application with registered Dev callback if authorized dashboard access is available. Keep secrets out of source and evidence.
- Evidence: Source inspection confirms TradeWave roles live in its database; WorkOS login alone does not grant dashboard access. Dev and production have separate existing ticket keys. No application code changed yet.
- Deployment: Dev not deployed by this task; production not deployed by this task.

Claim updated: 2026-10-02T20:45:07.754845+00:00
