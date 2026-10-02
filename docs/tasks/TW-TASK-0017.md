# TW-TASK-0017: Direct WorkOS login for the SMN dashboard

- Status: verified on dev
- Executor/session: Codex smn-workos-login-20261002 / 01a0fd8d-64bf-7741-bc34-89f5d326c05d
- Authorization: Afshin approved giving SMN its own WorkOS login using existing accounts while preserving TradeWave admin authorization. Implementation and verification start on Dev. No production promotion is part of this development claim.
- Scope: SMN dashboard human login, callback, logout/session handling; a narrowly scoped TradeWave admin authorization contract if needed. Preserve service/API keys and existing dashboard functions. No paywall, account provisioning, publication, scheduler, model, or billing changes.
- Branch: codex/smn-workos-login-20261002 in both repositories.
- Worktrees: Windows orchestrator/smn-workos-login-20261002 (SMN); /home/tradewave-worktrees/smn-workos-login-20261002 on TradeWave Dev.
- Coordination: TW-TASK-0006 and TW-TASK-0008 reviewed. TW-TASK-0009 production recovery remains independently owned; its pending activation is not taken over. TW-TASK-0016 live manifest is complete with manager released. Current TradeWave main includes subsequent Scenario Studio styling.
- Acceptance: Start login on SMN, authenticate with existing WorkOS users, return directly to SMN; only current TradeWave super_admin users admitted. Reject invalid/expired/replayed callbacks, denied users and cross-environment identities; verify logout, session expiry and unchanged machine authentication. Prove a real Dev browser login before claiming completion.
- Next: user may exercise Dev dashboard; a separate qualified release is required for production.
- Evidence: Real browser login, logout and subsequent user sign-in passed on October 2; focused tests and activation details below. TradeWave database remains administrator authority.
- Deployment: Paired Dev candidates activated and browser-verified; production unchanged by this task. WorkOS Staging serves Dev and Staging.

Claim updated: 2026-10-02T20:45:07.754845+00:00

## Development checkpoint - October 2

SMN candidate d37860770639ae37e15a2e0fc99590737877ede4 is pushed on codex/smn-workos-login-20261002; not merged or activated. Changed dashboard_workos.py, dashboard_auth.py, pub_dashboard.py and focused tests. TradeWave paired change adds smn_workos_authorization.py and POST /smn-dashboard/authorize, with central database role check and environment/application-bound JWT validation. Architecture and private configuration requirements are in the ecosystem auth section. The feature defaults to the existing TradeWave bridge until explicitly configured.

Focused tests: 22 TradeWave tests passed on .176, including RSA-signed JWT rejection cases and original SSO regressions. 90 SMN unittest checks passed on .180 in isolated /opt/smn-worktrees/smn-workos-login-20261002 using its installed venv, including existing ticket/API/service authentication and direct login, PKCE/state, denial and logout behavior. The count includes inherited regression cases; it is not 90 unique new cases. No tests used customer accounts or sent emails. Provider calls are mocked; no live WorkOS login is claimed.

Pending: owner sign-in to WorkOS MANAGEMENT dashboard (separate from TradeWave website). Chrome tab was opened and retained for that setup. No provider application, credential or redirect configuration has been changed. Once signed in, inspect current environment/application capabilities, configure the dedicated SMN Dev application and securely provision credentials on the server. Confirm actual issuer/client_id claims, then finish tested commits, acquire Dev activation locks, record previous pointers/configuration, integrate and activate the paired changes, and verify actual browser admin login/logout plus denied/unauthenticated API behavior. No production deployment is authorized by this development checkpoint. Existing Dev and production runtimes unchanged by this task.

Paired TradeWave implementation is preserved in commit e98a022 (resolve full SHA from the task branch); live activation remains pending WorkOS configuration. Both candidate worktrees are clean after the checkpoint.

## WorkOS Staging application configured

Afshin signed into WorkOS management and clarified that its Staging environment serves both Dev and Staging. Verified the default client matches TradeWave Dev before changing settings. Created SMN Dashboard, client client_01M3Z7YJKDZ9DKVK9MNYEP6X85, in environment_01KQNXQ3K11VF2AQK8CAQCJAX7. Registered exact Dev callback /smn-dashboard/auth/callback and logout return /smn-dashboard/signed-out at smn-dev.trxstat.com. Maximum provider session eight hours; five-minute access tokens; no CORS origins, no new API key, no shared credential copied. WorkOS public authorization-code PKCE supports no client_secret; SMN uses that documented flow and hosted logout. This supersedes the initial API-key/revoke design above. SMN candidate5a7d02b passes91 Linux checks; paired TW22 tests remain passed. Next: guarded paired Dev activation, actual browser login/logout and final parity. WorkOS production unchanged.

## Dev live verification - October 2, 2026

Runtime candidates: TradeWave 8942cdef37cca5e2360af5811e1d99c899d9fc28 and SMN 5a7d02bc60d5fdb4832802020a94606e39e5236d. Both clean worktrees were activated under task-owned Dev locks with captured rollback pointers and configuration. TradeWave React build was preserved at build-c9a865640aeacf6e7fd10dc925ad065e80c0d8ac; no frontend rebuild.

Real Chrome proof: starting at SMN /login returned directly to the dashboard with Afshin's existing account and 705 articles. Audit recorded login via workos at 21:30:44Z, distinct from the older bridge login. Log out returned to /signed-out showing You are logged out. Clicking Sign in returned to the WorkOS hosted sign-in form. Afshin then signed in again and the dashboard displayed his account. Actual provider exchange, dedicated application binding, environment issuer, central admin authorization and callback all succeeded. No article mutation, publication or email was performed.

Anonymous SMN /api/articles and TradeWave POST /smn-dashboard/authorize each returned401. Automated rejection checks include missing/non-admin identity, invalid signature, foreign app/issuer, expiry, missing claims and invalid callback state; live non-admin login was not exercised. Final focused suites:22 TradeWave tests and91 SMN unittest checks passed (includes inherited regression cases). TradeWave authenticated /app/ rendered the Wave Viewer and accepted an opportunity-panel toggle after the backend restart.

Activation/rollback receipts and preserved prior configuration: /var/lib/tradewave/release-state/smn-workos-login-20261002/receipt.json on each Dev host. Root activation helper /var/tmp/smn-auth-dev-activation.py supports tw or smn rollback and restores captured pointer/configuration, restarts and verifies service. SMN previous source /opt/smn-daily/releases/d6e2b6fd59b15e2a601248df00073c078db24df4; TradeWave previous backend /home/tradewave-worktrees/tw2-20261002-01. Current pointers target each task worktree.

No WorkOS API key is required, created, or copied. No production environment settings or production runtimes changed. Production needs its own SMN WorkOS application/callback/issuer configuration and qualified staging-to-production release; this Dev result is not production readiness certification.
