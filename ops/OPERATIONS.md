# TW2 Operations — the one map

If you're lost, start here. Everything below is reproducible from committed scripts in `ops/staging/`.

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
# SMN pipeline daemons run on the WEB box (Type=simple, load smn/ at startup) — bounce them too when smn/ daemon code changed (the pull above already updated the code):
ssh root@<web> -p 4369 'sudo systemctl restart tradewave-blog-queue tradewave-article-processor && sudo systemctl is-active tradewave-blog-queue tradewave-article-processor'
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

Scripts in `ops/staging/`, all run from `.176`, all idempotent:

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
