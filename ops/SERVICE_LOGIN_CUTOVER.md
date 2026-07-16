# One-time service-login header cutover

The release that removes `/login/api/<key>` needs a bounded coordinated restart.
Old WEB/API processes can otherwise keep the prior caller code in memory and send a
long-lived key in the path after the new appserver starts.

The normal deploy script detects the target stamp
`/var/lib/tradewave/release-gates/service-login-header-v1`. If it is absent, deploy
stops before changing either target unless the operator explicitly enables the
one-time mode:

Before that command, provision the environment-specific service identity on the
APP box. The schema seed deliberately does not copy this row between environments:

```bash
set -a
. /etc/tradewave/secrets.env
. /etc/tradewave/appserver.env
set +a
cd /home/flask/web
../venv/bin/python db_admin.py ensure-service-account
```

The deploy preflight independently derives the configured key hash in memory and
requires exactly one matching database row with the `service_account` role. It
prints only pass/fail information and runs before either worktree changes or any
caller is stopped.

```bash
TW2_DEPLOY_SHA=<reviewed-origin-main-sha> \
TW2_SERVICE_LOGIN_CUTOVER=1 \
bash ops/deploy.sh staging
```

The cutover syncs and verifies the same SHA on APP and WEB first. It then stops cron
and the old WEB/API/MCP callers, waits up to 60 seconds for any in-flight static
generator to exit, restarts the new appserver, and starts the new callers. The stamp
is written only after APP, API, and WEB are active. A pre-switch failure resumes the
recorded old callers. After the APP switch begins, recovery resumes them only if the
new appserver and authenticated header canary both pass; otherwise callers remain
stopped, fail-closed. No failure marks the migration complete. Correct the reported
cause and rerun the same command. Do not manually start a generator during this
window.

Run this on staging first. Complete the staging OAuth + BYOK acceptance gate and the
rest of the release checklist before repeating the command for production. Later
deploys see the stamp and use the ordinary restart path.
