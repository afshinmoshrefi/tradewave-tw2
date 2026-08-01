# TW2 Operations - the one map

If you're lost, start here. Everything below is reproducible from committed scripts in `ops/staging/`.

## The 3 operations (don't confuse them)

All run from dev (`.176`). An env = 2 boxes (web + app).

| Operation | Command | Touches | When |
|---|---|---|---|
| **Deploy code** | `bash ops/deploy.sh {staging\|prod}` | both web+app in one command: pull, restart, ship React, reload nginx | every code update - the normal flow |
| **Compile React** | `sudo -u flask bash -lc 'cd /home/flask/web-react && npm run build'` | nothing (builds the bundle on dev) | once before a deploy, ONLY if `web-react/src` changed |
| **Build a box** | `ops/staging/run.sh {staging\|prod} <script>` | one script -> one box (or runs on dev + reaches out); run the ordered sequence under "Rebuild a box from scratch" | rare - new box / full rebuild from bare metal |

To sync staging+prod with the latest code: (React build if `web-react/src` changed) -> `deploy.sh staging` -> verify -> `deploy.sh prod`. `run.sh` is NOT part of a routine deploy.

## Boxes

3 infrastructures (decision 2026-05-22: keep all three until ops are smooth, then maybe drop dev or staging). **Promotion flow: dev → staging → prod.** All hostnames are Cloudflare tunnels, not A records (do not convert to A — see memory `tw2-cloudflare-tunnels`).

| Role | Public IP | VLAN | Hostname | SSH |
|---|---|---|---|---|
| dev (single box, all tiers) | 192.168.1.176 | — | tw2-dev.trxstat.com | local |
| stage-web | 185.53.209.8 | 10.0.0.94 | tw2-stage.trxstat.com | `ssh root@185.53.209.8 -p 4369` |
| stage-app | 199.244.48.157 | 10.0.0.92 | tw2-stage-app.trxstat.com | `ssh root@199.244.48.157 -p 4369` |
| prod-web | 194.113.195.141 | 10.0.0.98 | tradewave.ai | `ssh root@194.113.195.141 -p 4369` |
| prod-app | 138.128.240.115 | 10.0.0.96 | tw2-prod-app.trxstat.com | `ssh root@138.128.240.115 -p 4369` |

2 CPU / 2 GB each. TW1 prod web is `10.0.0.40` (Kamatera VLAN). Prod SSH is `root@<ip> -p 4369`, same pattern as staging (confirmed 2026-05-22).

## What runs where

**stage-app** = APIs + data. gunicorn `appserver:app` on **:80** (no nginx; CAP_NET_BIND_SERVICE). Postgres, Redis (user data). cloudflared → `tw2-stage-app.trxstat.com`. Has `/home/flask/data/` (US subset, 12 GB). DB backups live here.

**stage-web** = everything else. gunicorn `app:app` on :5500 behind nginx. cloudflared → `tw2-stage.trxstat.com` + `smn-stage.trxstat.com`. Serves `/var/www/tradewave/` + `/var/www/smn/`. Runs SMN pipeline (blog-queue + article-processor systemd) + all content/email crons. Has `csv/US` for ticker/scorecard generators.

## Services (systemd, both boxes auto-restart on failure)

- stage-app: `tradewave-appserver`, postgresql, redis-server, cloudflared, chrony
- stage-web: `tradewave-web`, `tradewave-blog-queue`, `tradewave-article-processor`, nginx, redis-server, cloudflared, chrony

Health: `systemctl is-active <svc>`. Logs: `/var/log/tradewave/*.log` (rotated daily ×14).

## Deploy a code change

> **THIS SECTION IS THE SINGLE SOURCE OF TRUTH FOR DEPLOYMENT.** Any change that
> alters how a deploy works — a new systemd service, a new build artifact, a new
> env var that must be set on a box, a new cross-tier file, a new generator to
> re-run, a changed restart target — **MUST be reflected here in the same commit**.
> If you deploy something in a way that isn't written here, write it here. Do not
> let the real process drift out of this doc.

**Fast path (one command per env):** `bash ops/deploy.sh staging` → verify → `bash ops/deploy.sh prod`. The script runs everything below for one env (pre-flight, pull+restart web/app/SMN, React bundle, nginx) and aborts safely if `TW2_PUBLIC_HOST` is unset. Prereqs: commit+push, and `npm run build` if `web-react/` changed. The steps below are the reference the script implements (and for partial/manual deploys).

**Promotion flow: dev → staging → prod**, one env at a time. Code is edited and
tested on dev (`.176`), then promoted. The **React bundle is built ONCE on dev**
(env-agnostic, runtime-gated by `window.tw2_env`) and the *same* bundle is copied
to stage-web then prod-web — never rebuilt per env.

Each box holds the full repo at `/home/flask`, so the rule is simple:
**`git pull` on every box of the target env, then restart only the service(s)
whose code changed** (gunicorn does NOT auto-reload). Pulling everywhere is
idempotent and avoids cross-tier "which box needs this file" puzzles.

### 0. On dev (edit → test → commit → push)
```
sudo -u flask git -C /home/flask add <files>
sudo -u flask git -C /home/flask commit -m "…"
sudo -u flask git -C /home/flask push
# if web-react/ changed, build the bundle (plain build — NOT CI=true, which fails on pre-existing lint warnings):
sudo -u flask bash -lc 'cd /home/flask/web-react && npm run build'
# restart the relevant dev service(s) to test locally before promoting
```
All git/build/file ops on every box run as **`sudo -u flask`** (root ownership in `/home/flask` breaks `git pull` and the build — keep it flask:flask).

### 1. Pre-flight on the target env (before restarting)
The app derives `domain_root`/`tw2_public_url` from **`TW2_PUBLIC_HOST`**; if unset/wrong, all URLs fall back to `tw2-dev`. Check BOTH boxes of the target:
```
ssh root@<box> -p 4369 "grep -E 'TW2_PUBLIC_HOST|TW2_ENV' /etc/tradewave/secrets.env; systemctl cat tradewave-web 2>/dev/null | grep TW2_PUBLIC_HOST"
```
Expect: staging → `tw2-stage.trxstat.com` (+ `TW2_ENV=staging`); prod →
`TW2_PUBLIC_HOST=tradewave.ai` + `TW2_ENV=prod`. The deploy preflight requires
`TW2_ENV` in `secrets.env` on both boxes because cron does not inherit a systemd
override. A systemd override may still replace `TW2_PUBLIC_HOST` for a service,
so keep it consistent with `secrets.env`.

MailerLite application lifecycle writes are separately fail-closed. On staging,
keep `MAILERLITE_OUTBOUND_ENABLED=0`; `config.py` also requires `TW2_ENV=prod`, so
a staging token cannot mutate the shared MailerLite account. Before production
activation, the prod web box needs these values in `/etc/tradewave/secrets.env`:

```
TW2_ENV=prod
MAILERLITE_API_KEY=<connect API credential, or use the existing MAILERLITE_TOKEN fallback>
MAILERLITE_TRIAL_STARTED_GROUP_ID=<new-signup 7-day journey trigger group>
MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID=<post-trial Explorer journey trigger group>
MAILERLITE_WINBACK_GROUP_ID=<former-paid Explorer trust-letter trigger group>
MAILERLITE_OUTBOUND_ENABLED=0
```

Leave the final flag at `0` until every automation is fully designed, tested,
and active. Group IDs are environment configuration and must not be hardcoded
in `config.py`.

### 2. Server code — pull on BOTH boxes, restart by what changed

Each pull is followed by `pip install -r requirements.txt` (a dependency that's in requirements.txt but not installed crash-loops the gunicorn workers into a 502 - this is what had staging broken).
```
# WEB box   (stage 185.53.209.8 / prod 194.113.195.141):
ssh root@<web> -p 4369 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo -u flask bash /home/flask/ops/migrate.sh && sudo bash /home/flask/ops/install_mailerlite_lifecycle_cron.sh && sudo bash /home/flask/ops/install_daily_ai_pick_social_cron.sh && sudo systemctl restart tradewave-web && sudo systemctl is-active tradewave-web'
# APP box   (stage 199.244.48.157 / prod 138.128.240.115):
ssh root@<app> -p 4369 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo systemctl restart tradewave-appserver && sudo systemctl is-active tradewave-appserver'
# SMN pipeline daemons run on the WEB box (Type=simple, load smn/ at startup) — bounce them too when smn/ daemon code changed (the pull above already updated the code).
# NOTE: these two units exist only on boxes provisioned for content generation (stage-web). Prod web is NOT provisioned with them pre-cutover, so deploy.sh restarts them only if `systemctl cat` finds them — a missing optional unit must not abort the deploy before the React/nginx steps.
ssh root@<web> -p 4369 'for u in tradewave-blog-queue tradewave-article-processor; do systemctl cat "$u" >/dev/null 2>&1 && sudo systemctl restart "$u" && sudo systemctl is-active "$u" || echo "skip $u (not installed)"; done'
```
Restart matrix (which service to bounce after the pull):

| Changed | Restart |
|---|---|
| `web/` (app.py, models.py) | `tradewave-web` (web box) |
| `migrations/` | run `ops/migrate.sh` before restarting `tradewave-web` (routine `deploy.sh` does this) |
| `web/mailerlite_lifecycle.py` or its cron | run `ops/install_mailerlite_lifecycle_cron.sh`; the next minute uses the new worker |
| `appserver/` | `tradewave-appserver` (app box) |
| Tara gateway credentials or `tradewave-appserver` restart | `tradewave-apiserver` follows automatically via `PartOf`; its startup login canary must pass |
| `web/report_renderer.py` | `tradewave-web` **and** `tradewave-appserver` (appserver invokes it via `dr_report_publish`) |
| `smn/` used by the pipeline services | `tradewave-blog-queue` + `tradewave-article-processor` (web box) |
| `smn/` cron-only scripts (generate_security_pages, rebuild_news_home, daily_article_queue, update_news_quotes …) | none — next cron run uses new code |
| `config.py`, `tw_dateformat.py` (shared by all) | ALL: `tradewave-web`, `tradewave-appserver`, `tradewave-blog-queue`, `tradewave-article-processor` |
| `site/generate_*`, `site/templates/` | none — re-run the generator (step 3) or wait for cron |
| `web-react/` | none — rsync the bundle (step 2b) |
| `ops/nginx/` | reload nginx (step 3) |
| `secrets.env` / systemd units (NOT in git) | edit box-side, then `systemctl daemon-reload` + restart affected svc |
| MailerLite lifecycle values in `secrets.env` | restart `tradewave-web`; each cron invocation also sources the new values |

### 2b. React bundle (build/ is gitignored - rsync to a release dir + symlink swap, NOT pull)
`/home/flask/web-react/build` is a **symlink** to `releases/build-<commit>`; nginx serves `/app/` through it. Deploy = ship a new release dir named by the source commit hash, then repoint the symlink (keeps `build-previous` for instant rollback). Build once on dev, ship the same bundle to stage-web then prod-web:
```
# on dev:
REL=$(git -C /home/flask rev-parse --short HEAD)
rsync -az -e 'ssh -p 4369' /home/flask/web-react/build/ root@<web>:/home/flask/web-react/releases/build-$REL/
# on <web>:
cd /home/flask/web-react && chown -R flask:flask releases/build-$REL && chmod -R a+rX releases/build-$REL && ln -sfn "$(readlink build)" build-previous && ln -sfn releases/build-$REL build && chown -h flask:flask build build-previous
```
The build helper and deploy both normalize public bundle read/traverse permissions;
`rsync -a` otherwise preserves a restrictive operator umask and nginx returns 403
for the JS/CSS while the authenticated `/app/` shell remains stuck on "Loading".
`verify_deploy.sh` requests the active hashed main bundle and manifest through nginx
and blocks the release unless both return 200.
Rollback (instant, no hash): `cd /home/flask/web-react && ln -sfn "$(readlink build-previous)" build`
(One-time per box, already done on stage+prod: `mkdir -p releases && mv build releases/build-prev && ln -s releases/build-prev build`. `deploy.sh` runs ship+flip automatically. Full detail: memory `tw2-react-deploy-method`.)

### 3. Post-deploy (only if relevant)
- **nginx** (CSP/headers in `ops/nginx/` changed): re-apply via `ops/staging/apply_audit_hardening.sh` (or copy the snippet into the site config), then `ssh root@<web> -p 4369 'nginx -t && systemctl reload nginx'` (a gunicorn restart does NOT pick up nginx config).
- **Home page / static site** (`site/templates/` or `site/generate_*` changed): re-run on the web box —
  ```
  ssh root@<web> -p 4369
  sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_home_page.py'
  ```
  ⚠ `generate_home_page.py` still has hardcoded `CANONICAL_ROOT=tw2.trxstat.com` / `APPSERVER_URL=app1pp…` — make those env-driven before relying on a prod regen. (Otherwise it bakes the wrong host into the home page.)

### 3a. Daily AI pick X publishing

`site/m_daily_ai_pick_social.py` publishes the exact homepage/scorecard pick from
`/home/flask/site/data/featured_history.json`. It does not read
`daily-ai-pick.html`, use Publer, or use Hermes. The canonical cron runs at 07:10
Monday through Friday, ten minutes after `generate_home_page.py` writes the pick.
Routine deploy installs the cron idempotently.

Keep these values absent or disabled on dev and staging. On the production web
box, create an X app with write permission and user-context access tokens, then
set the following in `/etc/tradewave/secrets.env`:

```
X_API_KEY=<consumer key>
X_API_KEY_SECRET=<consumer secret>
X_ACCESS_TOKEN=<user access token>
X_ACCESS_TOKEN_SECRET=<user access token secret>
TW2_X_POSTING_ENABLED=0
```

Verify the exact pending copy without a network write:

```
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py'
```

After review, set `TW2_X_POSTING_ENABLED=1`. No service restart is needed because
each cron process reloads `secrets.env`. To make the first production post under
operator observation, run the same command with `--send`, then verify:

```
tail -50 /var/log/tradewave/m_daily_ai_pick_social.log
ls -l /var/log/tradewave/m_daily_ai_pick_social.x.*.json
sudo -u flask crontab -l | grep m_daily_ai_pick_social.py
```

Emergency stop: set `TW2_X_POSTING_ENABLED=0`. Existing successful dates remain
locked and failed API requests remain retryable because they do not create a lock.

### 3b. MailerLite lifecycle outbox and activation

`mailerlite_lifecycle_events` is the durable application-email outbox. Signup
and Stripe paths insert a deduplicated `reconcile` or `clear_paid` event in the
same Postgres transaction as the user or billing change. They do not call
MailerLite on the request path. The web-box cron runs once per minute, claims at
most 15 due rows, derives the desired state from the current `users` row, and
reconciles exactly one of these mutually exclusive trigger groups:

- `trial_started`: a first-time Explorer whose reverse trial is still active.
- `trial_ended_explorer`: that same first-time user's trial has ended without a paid subscription.
- `winback_explorer`: a former paid subscriber whose current web subscription ended.
- no lifecycle group: any current payer, local opt-out, or explicit `clear_paid` event.

The worker verifies MailerLite membership after each mutation. Network errors,
429s, and server errors remain retryable; a ten-minute stale claim is recovered.
A Postgres advisory lock prevents overlapping cron invocations. The canonical
entry is installed idempotently by `ops/install_mailerlite_lifecycle_cron.sh`
and by both routine deploy and `make_bulletproof.sh`:

```cron
* * * * * { test -r /etc/tradewave/secrets.env && set -a && . /etc/tradewave/secrets.env && set +a && cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --limit 15; } >> /var/log/tradewave/mailerlite_lifecycle.log 2>&1
```

Safe production rollout, in order:

1. Keep `MAILERLITE_OUTBOUND_ENABLED=0`. Deploy to staging with `TW2_ENV=staging` and verify. The Alembic outbox migration and cron installation run before the web restart.
2. Before deploying prod, set `TW2_ENV=prod`, populate the MailerLite credential and all three lifecycle group IDs, and keep the outbound flag at `0`. Then deploy prod.
3. Audit stored Stripe subscription identities before lifecycle backfill. The
   first command is Stripe-backed but read-only. It pages every subscription
   for each affected Stripe customer. Resolve every `blocking` row; with
   explicit `TW2_ENV=prod` and outbound still disabled, apply the proven API
   identity moves and rerun the dry run:
   ```
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py'
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py --apply'
   ```
   The audit preserves confirmed web/EOD and unlabelled legacy web identities,
   and never clears a paid web tier. One matching EOD identity can be restored
   atomically; incomplete pagination, customer/tier/status mismatch, shared
   IDs, or multiple candidate subscriptions refuse the whole apply.
4. Schedule only the post-trial transition for users whose reverse trial was already active when this code deployed. The first command is a dry run; inspect its counts before applying:
   ```
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/backfill_active_reverse_trial_lifecycle.py'
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/backfill_active_reverse_trial_lifecycle.py --apply'
   ```
   This deliberately does not put an existing user midway into the day-0 trial journey and does not touch expired Explorer accounts.
5. In MailerLite, finish the designs and links, send tests, and activate all three automations. Do not enroll subscribers while an automation is inactive because a group-join trigger may not replay later.
6. Preview due work without claiming rows or contacting MailerLite:
   ```
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --dry-run --limit 15'
   ```
7. Set `MAILERLITE_OUTBOUND_ENABLED=1` on the prod web box and restart `tradewave-web`. The next cron tick drains due rows using current user state.
8. Confirm the cron and watch the first batches:
   ```
   sudo -u flask crontab -l | grep mailerlite_lifecycle.py
   tail -f /var/log/tradewave/mailerlite_lifecycle.log
   ```

Emergency stop: set `MAILERLITE_OUTBOUND_ENABLED=0` and restart
`tradewave-web`. The next cron invocation is disabled and pending rows remain
durable. One already-running batch can finish at most 15 rows; for an immediate
stop, remove the lifecycle cron line and terminate only the exact
`/home/flask/web/mailerlite_lifecycle.py` process, then confirm the log is quiet.

Stripe deletion safety is part of the same flow. A
`customer.subscription.deleted` event can downgrade the web tier only when its
subscription ID matches `users.stripe_subscription_id`, or when its price is
recognizably a web/EOD price and there is no conflicting current subscription.
A delayed deletion for an older subscription is acknowledged with HTTP 200,
does not mutate the user, and records `stale_subscription_deleted_ignored`.
An unclassified deletion is likewise ignored and records
`unclassified_subscription_deleted_ignored`. This prevents a current payer
from being downgraded or enrolled in winback by an out-of-order Stripe event.

### 4. Verify on the env's own hostname
`tw2-stage.trxstat.com` / `tradewave.ai`: login + logout (same-origin, works on first click), a report page renders, `/app/` loads with the console quiet (consoleGuard), `/api/me` returns the right tier. **Only then promote to the next env.**

### Rollback
`ssh root@<box> -p 4369 'sudo -u flask git -C /home/flask reset --hard <prev-sha> && systemctl restart <svc>'` (last resort; prefer fixing forward). React: `cd /home/flask/web-react && ln -sfn "$(readlink build-previous)" build` (instant, above).

## Deploy gotchas (learned 2026-05-22 - read before debugging a deploy)

- **`/app/` returns 502 but `systemctl is-active tradewave-web` says `active`.** The gunicorn *master* holds port 5500 (so it looks "up"), but every *worker* is crash-looping on an import. Check `tail -30 /var/log/tradewave/web.error.log` for the traceback. **#1 cause: a dependency listed in requirements.txt but not installed in that box's venv** (this is the `flask_wtf` incident that kept staging "broken" for weeks). Fix: `sudo -u flask /home/flask/venv/bin/pip install -r /home/flask/requirements.txt && sudo systemctl restart tradewave-web`. The deploy now pip-installs every run so it can't recur. Tell-tale: the static marketing home still serves (nginx reads it off disk, no gunicorn), so **"home works but `/app/` 502s" points straight at the web workers.**

- **`git pull` aborts: "Your local changes to the following files would be overwritten by merge: config.py".** The box's `config.py` drifted - almost always a prior *surgical* `git checkout origin/main -- config.py` left it modified vs the box's HEAD. Diagnose: `sudo -u flask git -C /home/flask status --short` (`M config.py` = real drift; `??` lines are just untracked files, harmless) and `git diff config.py`. `config.py` is **env-agnostic** - every per-env value comes from `secrets.env` - so a local edit is almost always stale and already superseded by the committed version. After confirming the diff is only that superseded change: `sudo -u flask git -C /home/flask checkout HEAD -- config.py && sudo -u flask git -C /home/flask pull --ff-only`. **Never blind-discard without reading the diff** (a hand-set value not in `secrets.env` would be lost). NOTE: "behind/old code" with a CLEAN tree is NOT drift - a plain `git pull` updates it.

- **Run all git/build/file ops on a box as `sudo -u flask`.** Root-owned files in `/home/flask` (especially `.git/index`, `.git/refs`) break the next `sudo -u flask git pull`. If it happens: `chown -R flask:flask /home/flask`.

## Renaming an environment's URL (e.g. stage2 -> tw2-stage)

The hostname lives in SIX places; changing one is not enough, and most need a reload/restart. Skip any and you get a 404, a 502, or a WorkOS `redirect-uri-invalid`:

1. **Cloudflare DNS** - rename the tunnel record (same tunnel target).
2. **cloudflared ingress** (`/etc/cloudflared/config.yml`) - add the new hostname, then **`systemctl restart cloudflared`**. Editing the file alone does nothing - that is the 404 ("page not found").
3. **nginx `server_name`** - then **`nginx -t && systemctl reload nginx`**.
4. **`secrets.env`** - update BOTH `TW2_PUBLIC_HOST` and `TW2_AUTH_CALLBACK_URL`, then **`systemctl restart tradewave-web`**. The WorkOS redirect is read from `TW2_AUTH_CALLBACK_URL` ONCE at process start (`web/app.py` `REDIRECT_URI`), and it is a SEPARATE var from `TW2_PUBLIC_HOST` - updating only the public host leaves auth sending the old callback.
5. **WorkOS** - add `https://<new-host>/auth/callback` to that env's redirect URIs.
6. **Test in a fresh/incognito browser.** The browser caches the old auth redirect, so a stale tab keeps sending the old callback even after everything above is correct (this ate ~30 min on staging). Source of truth for what the app actually emits: `curl -sS -i https://<host>/login | grep -i location` - read the `redirect_uri=` in the 302.

## Rebuild a box from scratch (ordered)

Scripts in `ops/staging/`, all run from `.176`, all idempotent, all **env-driven**.
Run each via the unified runner, which supplies per-env coordinates from `target.env`
(staging) or `prod_target.env` (prod) — no hardcoded hosts/IPs:

```
ops/staging/run.sh staging <script.sh>          # build/rebuild staging
ops/staging/run.sh prod    <script.sh>          # build/rebuild prod (placeholder tw2-prod.trxstat.com)
ops/staging/run.sh prod    inventory.sh app     # tier-neutral payloads take a 3rd arg: app|web
```
(`run_prod.sh <script>` still works — it now just forwards to `run.sh prod`.) Order:

1. `inventory.sh` — see what the bare VM has
2. `bootstrap_stage_{app,web}.sh` — OS layer (packages, flask uid 1001, ufw, deploy key)
3. add deploy pubkey to GitHub (per box)
4. `bootstrap_stage_app_code.sh` — git clone + venv + pip
5. `make_staging_secrets.sh` → scp secrets.env (per-env, Fernet cookie key)
6. `seed_stage_schema.sh` — pg_dump schema (alembic baseline is stamp-only)
7. `lift_data_us_only.sh` (app) / `lift_content_stage_web.sh` + `lift_csv_us_to_web.sh` (web)
8. `bootstrap_stage_{app,web}_services.sh` — systemd + nginx
9. `migrate_app_port_to_80.sh` — gunicorn → :80 (TW1 convention)
10. `bootstrap_stage_{app,web}_tunnel.sh` — cloudflared (delete A record first)
11. `wire_cross_tier_render.sh` — web:5500 reachable from app
12. `migrate_smn_to_web.sh` + `migrate_smn_content_from_tw1.sh` + `fix_smn_urls_on_stage_web.sh`
13. `migrate_scorecard_from_tw1.sh`
14. `apply_audit_hardening.sh` — CSP + systemd hardening (ProtectSystem=**full**, never strict)
15. `wipe_cf_cert_post_tunnel.sh` — remove account-wide CF cert
16. `lockdown_public_ports.sh` — close public 80/443 (cloudflared only)
17. `make_bulletproof.sh` — backups + logrotate + journald cap + full cron set

Full annotated playbook + every gotcha: memory `project_tw2_staging_deployment.md`.

## API/MCP deploy + restart

The v2 public product (gateway + MCP + developer portal). Map: `docs/TRADEWAVE_ECOSYSTEM.md`
§7A/§7B; contract: `api/PATTERNCARD_SPEC.md` + `api/openapi.yaml`; build-state: `api/BUILD_STATE.md`.
**SIGNALS-ONLY** (no raw prices). These are NEW services additive to the appserver; they live on
the **app box** (gateway -> appserver over localhost), public via `api-`/`mcp-`/`developers-`
hostnames. All scripts are run BY the operator on the target box (never auto-run against
staging/prod). Author them on dev; operator runs them.

**Hosts per env** (drive `portal_urls.py` via `secrets.env`):

| Env | API | MCP | Developer portal |
|---|---|---|---|
| dev | api-dev.trxstat.com | mcp-dev.trxstat.com | developers-dev.trxstat.com |
| staging | api-stage.trxstat.com | mcp-stage.trxstat.com | developers-stage.trxstat.com |
| prod | api.tradewave.ai | mcp.tradewave.ai | developers.tradewave.ai |

Set `TW2_API_PUBLIC_HOST`, `TW2_MCP_PUBLIC_HOST`, `TW2_DEVELOPERS_PUBLIC_HOST` (and the existing
`TW2_PUBLIC_HOST`) in `/etc/tradewave/secrets.env` BEFORE running the scripts/generators.

**Services (systemd, app box, auto-restart on failure):**

| Unit | Command | Bind | Venv | Type |
|---|---|---|---|---|
| `tradewave-apiserver` | `gunicorn apiserver.app:app` (4 gthread workers x 12 threads) | `127.0.0.1:8088` | `/home/flask/venv-api` | notify |
| `tradewave-mcpserver` | `python -m mcpserver.server --transport streamable-http --port 9090` | `127.0.0.1:9090` | `/home/flask/venv-api` | simple |

MCP env: `API_BASE_URL=http://127.0.0.1:8088/v1`, `TW2_MCP_PUBLIC_HOST=<host>`, and
`TRADEWAVE_API_KEY` **UNSET** on the remote transport (BYOK - clients send their own
`Authorization: Bearer`). The unit defaults `TW2_MCP_TRANSPORT=streamable-http`; the server
uses one bounded async gateway pool (`TW2_MCP_GATEWAY_MAX_INFLIGHT`, default 32) and
serves the MCP endpoint at the ROOT path `/` with `/mcp` as a permanent alias (NOT SSE at
`/sse`). Logs: `/var/log/tradewave/`.

**1. Build the loopback services and nginx surface (once per box / new box):**
```
sudo bash /home/flask/ops/bootstrap_api_services.sh
```
Idempotent + echoes each step. It builds `/home/flask/venv-api`
from `requirements-api.txt`, applies the additive `apiserver/schema.sql`, and installs +
`enable --now`s the two systemd units (gateway :8088, mcp :9090). It also renders and installs
the API/MCP/developer nginx vhosts from `secrets.env` through
`ops/install_developer_portal_nginx.sh` (dev :80, staging/prod :8080). Cloudflared remains a
separate edge step. The staging/prod app-tunnel bootstrap routes the three public hosts to
`http://localhost:8080` before its final 404 catch-all; appserver stays on APP :80.

**2. Assemble the developer portal docroot:**
```
sudo bash /home/flask/ops/assemble_developer_portal.sh
```
Runs the generators (`site/api_marketing/generate.py`, `site/api_docs/generate_api_docs.py` +
`generate_api_extras.py`, `site/api_learn/generate_learn_api.py`,
`site/api_playground/generate_playground.py`) with `/home/flask/venv/bin/python`, then rsyncs into
`/var/www/developers/` (`/`, `/docs`, `/learn`, `/playground`, `/.well-known/mcp.json`). Re-run any
time copy/contract changes; re-run after an env-host change (the pages bake the hostnames). No
service restart needed (nginx serves it off disk).

**3. Restart matrix (after a code change):**

| Changed | Restart |
|---|---|
| `apiserver/` (gateway) | `systemctl restart tradewave-apiserver` |
| `mcpserver/` | `systemctl restart tradewave-mcpserver` |
| `web/api_portal/` (console) | `systemctl restart tradewave-web` (it is a `web/app.py` blueprint) |
| `site/api_*` generators/copy | re-run script 2 (no restart) |
| `secrets.env` host/key change | restart the affected unit(s) above, then re-run script 2 |

gunicorn does NOT auto-reload - always restart after a Python edit.

The tracked `tradewave-apiserver` unit is ordered after and `PartOf=tradewave-appserver`.
An appserver restart therefore refreshes the gateway's cached service JWT as one lifecycle,
and the gateway's `ExecStartPost` performs a real service login. A mismatched service key,
JWT secret, database role, or appserver endpoint fails activation instead of leaving Tara on
a superficially healthy gateway that returns internal errors.

**4. Health checks (on the app box):**
```
systemctl is-active tradewave-apiserver tradewave-mcpserver
curl -sS http://127.0.0.1:8088/v1/markets -H "Authorization: Bearer $KEY" | head    # gateway, signals-only
# MCP: streamable-http at the ROOT (alias /mcp), NOT SSE at /sse. Answer an initialize handshake:
curl -sS http://127.0.0.1:9090/ -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' | head
curl -sS -i https://<api-host>/v1/markets | head                                    # edge -> gateway via tunnel+nginx
curl -sS    https://<developers-host>/.well-known/mcp.json | head                   # portal docroot served
```
Spot-check the gateway JSON for **no raw price fields** (the signals-only invariant). 502-but-active
= a worker crash on a missing `venv-api` dep (same failure mode as the web tier; `pip install -r
requirements-api.txt`).

**5. Mandatory pre-deployment gate:** use existing test credentials only. The script is
read-only and does not create users, keys, products, or subscriptions.
```
export TW2_TEST_API_KEY='tw_...'
export TW2_TEST_OAUTH_TOKEN='...'
python /home/flask/ops/verify_mvp_release.py \
  --api-base https://api-dev.trxstat.com/v1 \
  --mcp-url https://mcp-dev.trxstat.com/mcp \
  --concurrency 50 --requests 200
```
PASS requires API-key auth, a non-null daily pick, MCP BYOK, MCP WorkOS OAuth, at most 1%
request errors, p95 at or below 15 seconds for the scan workload, and no gateway
storm-breaker activation. Run away from the 02:00 UTC cron burst. Do not use
`--skip-oauth` for a release decision.

## Reliability

- **DB backups**: `ops/backup_db.sh` nightly 03:30 on stage-app → `/var/backups/tradewave/db_*.sql.gz`, 14-day prune. Restore verified weekly by `ops/restore_drill.sh`. **Restore test: `sudo -u flask /home/flask/ops/restore_drill.sh` on stage-app — must say PASS.**
- **Logs**: logrotate daily ×14 + journald capped 500 M. Disk-fill (the #1 "breaks every few days") is contained.
- **Crons**: full set on stage-web flask crontab (SMN pipeline, security pages, homepage, scorecard, quotes, daily AI pick, SMN emails daily+weekly, social). Direct X morning social runs at 07:10 weekdays after the 07:00 homepage pick writer. The close-ledger publisher polls 03:00-06:59 UTC Tue-Sat and can run only after the appserver publishes a successful EOD completion marker; zero-close market dates are locked without posting. Both X jobs are inert outside production. The durable MailerLite lifecycle worker runs every minute and is a no-write operation unless production explicitly enables it. `expire_trials` runs at 04:15. The keyprovider starts EODHD at 20:03 ET; appservers pull from keyprovider at 03:05-05:05 UTC Tue-Sat until successful. Ticker regeneration runs at 02:00 + hourly 09-16.
- **Uptime/soak**: `uptime_check.sh` (every 5 min) + `soak_monitor.sh` (every 30 min) log to `/var/log/tradewave/`. **Notification gap: these only log. Proper fix = external uptime monitor (Cloudflare Health Checks or an external pinger hitting `https://tw2-stage.trxstat.com/healthz`) — not a homegrown emailer. Set this up in the Cloudflare dashboard.**

## Security posture

5 CRITICAL + ~10 HIGH from the 2026-05-15 audit closed (see `/home/afshin/SECURITY_AUDIT_2026-05-15_*.md` + memory). Public 80/443 closed (cloudflared-only ingress). CSRF on admin. Remaining HIGH (tracked, lower likelihood): JWT-in-URL on `/login/*`, SERVICE_API_KEY dual-use, CSP `unsafe-inline`. Re-audit cadence: before prod cutover + quarterly.

## When something breaks

1. `ssh <box> 'systemctl status tradewave-* --no-pager'`
2. `ssh <box> 'tail -50 /var/log/tradewave/{web,appserver}.error.log'`
3. `ssh <box> 'journalctl -u tradewave-<svc> --no-pager -n 50'`
4. `df -h /` — disk full is the usual culprit if logrotate ever lapses.
5. Roll back: `git -C /home/flask reset --hard <prev> && systemctl restart …` (last resort; prefer fixing forward).
