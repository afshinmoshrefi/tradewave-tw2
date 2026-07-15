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
| prod-web | 194.113.195.141 | 10.0.0.98 | tw2-prod.trxstat.com (→ tradewave.ai at cutover) | `ssh root@194.113.195.141 -p 4369` |
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
Expect: staging → `tw2-stage.trxstat.com` (+ `TW2_ENV=staging`); prod → `TW2_PUBLIC_HOST=tw2-prod.trxstat.com` + `TW2_ENV=prod`. A systemd `override.conf` wins over `secrets.env`.

### 2. Server code — pull on BOTH boxes, restart by what changed

Each pull is followed by `pip install -r requirements.txt` (a dependency that's in requirements.txt but not installed crash-loops the gunicorn workers into a 502 - this is what had staging broken).
```
# WEB box   (stage 185.53.209.8 / prod 194.113.195.141):
ssh root@<web> -p 4369 'sudo -u flask git -C /home/flask pull --ff-only && sudo -u flask /home/flask/venv/bin/pip install -q -r /home/flask/requirements.txt && sudo systemctl restart tradewave-web && sudo systemctl is-active tradewave-web'
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
| `appserver/` | `tradewave-appserver` (app box) |
| `web/report_renderer.py` | `tradewave-web` **and** `tradewave-appserver` (appserver invokes it via `dr_report_publish`) |
| `smn/` used by the pipeline services | `tradewave-blog-queue` + `tradewave-article-processor` (web box) |
| `smn/` cron-only scripts (generate_security_pages, rebuild_news_home, daily_article_queue, update_news_quotes …) | none — next cron run uses new code |
| `config.py`, `tw_dateformat.py` (shared by all) | ALL: `tradewave-web`, `tradewave-appserver`, `tradewave-blog-queue`, `tradewave-article-processor` |
| `site/generate_*`, `site/templates/` | none — re-run the generator (step 3) or wait for cron |
| `web-react/` | none — rsync the bundle (step 2b) |
| `ops/nginx/` | reload nginx (step 3) |
| `secrets.env` / systemd units (NOT in git) | edit box-side, then `systemctl daemon-reload` + restart affected svc |

### 2b. React bundle (build/ is gitignored - rsync to a release dir + symlink swap, NOT pull)
`/home/flask/web-react/build` is a **symlink** to `releases/build-<commit>`; nginx serves `/app/` through it. Deploy = ship a new release dir named by the source commit hash, then repoint the symlink (keeps `build-previous` for instant rollback). Build once on dev, ship the same bundle to stage-web then prod-web:
```
# on dev:
REL=$(git -C /home/flask rev-parse --short HEAD)
rsync -az -e 'ssh -p 4369' /home/flask/web-react/build/ root@<web>:/home/flask/web-react/releases/build-$REL/
# on <web>:
cd /home/flask/web-react && chown -R flask:flask releases/build-$REL && ln -sfn "$(readlink build)" build-previous && ln -sfn releases/build-$REL build && chown -h flask:flask build build-previous
```
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

### 4. Verify on the env's own hostname
`tw2-stage.trxstat.com` / `tw2-prod.trxstat.com`: login + logout (same-origin, works on first click), a report page renders, `/app/` loads with the console quiet (consoleGuard), `/api/me` returns the right tier. **Only then promote to the next env.**

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
| `tradewave-mcpserver` | lifetime-shared activation fence -> absolute release Python -> Streamable HTTP server | `127.0.0.1:9090` | `/home/tradewave-mcp/current/venv` | exec |

PID 1 reads only `/etc/tradewave/mcpserver.env` (root:root 0600), generated transactionally by
the immutable deploy from a strict allowlist, before dropping to the dedicated `tradewave-mcp`
identity. The process cannot browse `/etc/tradewave` or `/home/flask`. The file contains the local
bind/API base, WorkOS issuer, canonical MCP URL/host, and dedicated MCP delegation key. A newly
provisioned key must exist only in this MCP-specific file; the transactional first migration removes
every legacy `MCP_GATEWAY_KEY` assignment from the broad platform file before activation. The unit
must never load the broad platform `secrets.env`; `TRADEWAVE_API_KEY` is **UNSET** on the remote transport (BYOK - clients send their own
`Authorization: Bearer`). The unit defaults `TW2_MCP_TRANSPORT=streamable-http`; the server
serves the MCP endpoint at the ROOT path `/` with `/mcp` as a permanent alias (NOT SSE at
`/sse`). Logs go only to journald (`journalctl -u tradewave-mcpserver`).

MCP releases are immutable and separate from the potentially dirty gateway checkout. Deploy only
an exact reviewed lowercase 40-character SHA through the installed launcher:
```
sudo /usr/local/sbin/tradewave-mcp-release <exact-lowercase-40-character-sha>
```
Each root-owned, non-writable `/home/tradewave-mcp/releases/mcp-<sha>/` bundle contains source,
a minimal CPython 3.13 runtime populated offline and binary-wheel-only with `--require-hashes` from the
MCP 1.28.1 lock. Systemd, nginx, provisioning, and verifier assets come only from the separately installed
fixed controller. The seal binds source, wheels, and installed bytes; the host interpreter, standard
library, CA store, and OS remain external trust boundaries. `current` selects
code + runtime atomically; `previous` is the rollback target. Any failed
dependency audit/unit/nginx/process/service-key/public-contract/20-session check restores all prior
pointers, the dedicated environment, and config. The
gateway remains in `/home/flask` and is neither reset nor repointed. Roll back with
`sudo /usr/local/sbin/tradewave-mcp-release --rollback`.

Isolation prevents the MCP worker from reading or modifying the gateway checkout and its broad
secrets; it does not make the loopback gateway untrusted. The gateway remains an explicit trusted
application dependency: it authenticates the dedicated MCP service key, resolves delegated WorkOS
subjects, applies tiers, meters calls, and returns tool data. A compromised gateway (or its current
database role) could forge those decisions or responses. Removing that trust requires a separately
isolated gateway and narrower database roles, which is a platform re-architecture outside this MCP RC.

**1. Build the loopback services (once per box / new box); then wire the edge manually:**
```
sudo bash /home/flask/ops/bootstrap_api_services.sh
```
Idempotent + echoes each step. It does ONLY the loopback layer: builds `/home/flask/venv-api`
from `requirements-api.txt`, applies the additive `apiserver/schema.sql`, and installs +
`enable --now`s the two systemd units (gateway :8088, mcp :9090). It does NOT wire the edge -
it only echoes a reminder that nginx + cloudflared are separate. The edge is two manual steps
done per box (cross-ref PROD_CUTOVER "API/MCP go-live" Step 4):
- **nginx vhost** - install `ops/nginx/tradewave-developer-portal.conf` (the `api.`/`mcp.`/
  `developers.` server blocks) into `sites-available`, symlink into `sites-enabled`, then
  `nginx -t && systemctl reload nginx`.
- **cloudflared ingress** - add the `api-`/`mcp-`/`developers-` (prod: bare `api.`/`mcp.`/
  `developers.tradewave.ai`) ingress entries to `/etc/cloudflared/config.yml` BEFORE the
  `- service: http_status:404` catch-all, then `systemctl restart cloudflared` (the cloudflared
  edit alone does nothing - that is the 404).

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
| `mcpserver/`, MCP lock, unit, or MCP nginx edge | immutable deploy command above (tests + atomic restart + rollback gate) |
| `web/api_portal/` (console) | `systemctl restart tradewave-web` (it is a `web/app.py` blueprint) |
| `site/api_*` generators/copy | re-run script 2 (no restart) |
| MCP source metadata or service-key rotation | run the immutable MCP release controller; it owns transactional key provisioning, environment regeneration, activation proof, and rollback |

gunicorn does NOT auto-reload - always restart after a Python edit.

**4. Health checks (on the app box):**
```
systemctl is-active tradewave-apiserver tradewave-mcpserver
curl -sS http://127.0.0.1:8088/v1/markets -H "Authorization: Bearer $KEY" | head    # gateway, signals-only
# Run the authenticated contract/load gates through the immutable deploy or ops/verify_deploy.sh.
# Both use the permanent root-only /etc/tradewave/mcp-verifier.env via
# mcp-service-env.py exec-with-verifier; never export or copy its raw token.
curl -sS -i https://<api-host>/v1/markets | head                                    # edge -> gateway via tunnel+nginx
curl -sS    https://<developers-host>/.well-known/mcp.json | head                   # portal docroot served
```
For target-side diagnosis, first run the active bundle's sealed
`artifacts/provision-mcp-key.py --check-verifier`, then execute its sealed
`verify_mcp_contract.py` and `verify_mcp_load.py` artifacts through
`artifacts/mcp-service-env.py exec-with-verifier --source
/etc/tradewave/mcp-verifier.env -- <absolute-python> <absolute-verifier-script> ...`.
The helper passes a minimal child environment and never prints the credential.
The 20-session gate is not count-only: every synchronized phase must finish within 5s, `whoami`
p95/max within 2s/3s, and full-session p95/max within 12s/15s; any breach rolls back the release.
The deploy also authenticates `MCP_GATEWAY_KEY` locally: no principal must return `401 missing
principal`, a random valid-shaped principal must return `401 unknown user`, and the configured safe
`TW_MCP_SMOKE_WORKOS_SUB` must return 200 at `TW_MCP_SMOKE_EXPECT_TIER`. After deployment, create a
fresh ChatGPT connector, complete WorkOS authorization, prove a tier-correct call, then prove refresh
token rotation by calling again after access-token expiry. Metadata/DCR is automated; user-consent and
refresh issuance remain an interactive release check.

If a manual `urllib` metadata fetch gets Cloudflare 403 while the release probe succeeds, do not
misdiagnose WorkOS Connect as disabled: the AuthKit edge is User-Agent-sensitive. Re-run with the
named `TradeWave-MCP-Release-Gate/1.0` identity (the automated verifier does this) and require the
same metadata fields; never weaken the metadata contract or the edge allowlist to accommodate an
anonymous default Python User-Agent.

Spot-check the gateway JSON for **no raw price fields** (the signals-only invariant). 502-but-active
= a worker crash on a missing `venv-api` dep (same failure mode as the web tier; `pip install -r
requirements-api.txt`).

## Reliability

- **DB backups**: `ops/backup_db.sh` nightly 03:30 on stage-app → `/var/backups/tradewave/db_*.sql.gz`, 14-day prune. Restore verified weekly by `ops/restore_drill.sh`. **Restore test: `sudo -u flask /home/flask/ops/restore_drill.sh` on stage-app — must say PASS.**
- **Logs**: logrotate daily ×14 + journald capped 500 M. Disk-fill (the #1 "breaks every few days") is contained.
- **Crons**: full set on stage-web flask crontab (SMN pipeline, security pages, homepage, scorecard, quotes, daily AI pick, SMN emails daily+weekly, social). `expire_trials` 04:15. EOD refresh 23:36. Ticker regen 02:00 + hourly 09-16.
- **Uptime/soak**: `uptime_check.sh` (every 5 min) + `soak_monitor.sh` (every 30 min) log to `/var/log/tradewave/`. **Notification gap: these only log. Proper fix = external uptime monitor (Cloudflare Health Checks or an external pinger hitting `https://tw2-stage.trxstat.com/healthz`) — not a homegrown emailer. Set this up in the Cloudflare dashboard.**

## Security posture

5 CRITICAL + ~10 HIGH from the 2026-05-15 audit closed (see `/home/afshin/SECURITY_AUDIT_2026-05-15_*.md` + memory). Public 80/443 closed (cloudflared-only ingress). CSRF on admin. Remaining HIGH (tracked, lower likelihood): JWT-in-URL on `/login/*`, SERVICE_API_KEY dual-use, CSP `unsafe-inline`. Re-audit cadence: before prod cutover + quarterly.

## When something breaks

1. `ssh <box> 'systemctl status tradewave-* --no-pager'`
2. `ssh <box> 'tail -50 /var/log/tradewave/{web,appserver}.error.log'`
3. `ssh <box> 'journalctl -u tradewave-<svc> --no-pager -n 50'`
4. `df -h /` — disk full is the usual culprit if logrotate ever lapses.
5. Roll back: `git -C /home/flask reset --hard <prev> && systemctl restart …` (last resort; prefer fixing forward).
