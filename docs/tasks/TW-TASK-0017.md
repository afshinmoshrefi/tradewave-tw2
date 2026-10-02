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

## Development checkpoint - October 2

SMN candidate d3786079 pending full SHA receipt (use remote branch) is pushed on codex/smn-workos-login-20261002; not merged or activated. Changed dashboard_workos.py, dashboard_auth.py, pub_dashboard.py and focused tests. TradeWave paired change adds smn_workos_authorization.py and POST /smn-dashboard/authorize, with central database role check and environment/application-bound JWT validation. Architecture and private configuration requirements are in the ecosystem auth section. The feature defaults to the existing TradeWave bridge until explicitly configured.

Focused tests: 22 TradeWave tests passed on .176, including RSA-signed JWT rejection cases and original SSO regressions. 90 SMN unittest checks passed on .180 in isolated /opt/smn-worktrees/smn-workos-login-20261002 using its installed venv, including existing ticket/API/service authentication and direct login, PKCE/state, denial and logout behavior. The count includes inherited regression cases; it is not 90 unique new cases. No tests used customer accounts or sent emails. Provider calls are mocked; no live WorkOS login is claimed.

Pending: owner sign-in to WorkOS MANAGEMENT dashboard (separate from TradeWave website). Chrome tab was opened and retained for that setup. No provider application, credential or redirect configuration has been changed. Once signed in, inspect current environment/application capabilities, configure the dedicated SMN Dev application and securely provision credentials on the server. Confirm actual issuer/client_id claims, then finish tested commits, acquire Dev activation locks, record previous pointers/configuration, integrate and activate the paired changes, and verify actual browser admin login/logout plus denied/unauthenticated API behavior. No production deployment is authorized by this development checkpoint. Existing Dev and production runtimes unchanged by this task.
