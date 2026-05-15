# TW2 Operations — the one map

If you're lost, start here. Everything below is reproducible from committed scripts in `ops/staging/`.

## Boxes

| Role | Public | VLAN | SSH |
|---|---|---|---|
| dev (single box, all tiers) | 192.168.1.176 | — | local |
| stage-web | 185.53.209.8 | 10.0.0.94 | `ssh root@185.53.209.8 -p 4369` |
| stage-app | 199.244.48.157 | 10.0.0.92 | `ssh root@199.244.48.157 -p 4369` |

Prod = same shape, 2 CPU / 2 GB each, `tradewave.ai` web hostname. TW1 prod web is `10.0.0.40` (Kamatera VLAN).

## What runs where

**stage-app** = APIs + data. gunicorn `appserver:app` on **:80** (no nginx; CAP_NET_BIND_SERVICE). Postgres, Redis (user data). cloudflared → `tw2-stage-app.trxstat.com`. Has `/home/flask/data/` (US subset, 12 GB). DB backups live here.

**stage-web** = everything else. gunicorn `app:app` on :5500 behind nginx. cloudflared → `stage2.trxstat.com` + `smn-stage.trxstat.com`. Serves `/var/www/tradewave/` + `/var/www/smn/`. Runs SMN pipeline (blog-queue + article-processor systemd) + all content/email crons. Has `csv/US` for ticker/scorecard generators.

## Services (systemd, both boxes auto-restart on failure)

- stage-app: `tradewave-appserver`, postgresql, redis-server, cloudflared, chrony
- stage-web: `tradewave-web`, `tradewave-blog-queue`, `tradewave-article-processor`, nginx, redis-server, cloudflared, chrony

Health: `systemctl is-active <svc>`. Logs: `/var/log/tradewave/*.log` (rotated daily ×14).

## Deploy a code change

```
# on .176, after commit+push:
ssh root@185.53.209.8 -p 4369 'sudo -u flask git -C /home/flask pull --ff-only && systemctl restart tradewave-web'
ssh root@199.244.48.157 -p 4369 'sudo -u flask git -C /home/flask pull --ff-only && systemctl restart tradewave-appserver'
```

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
- **Uptime/soak**: `uptime_check.sh` (every 5 min) + `soak_monitor.sh` (every 30 min) log to `/var/log/tradewave/`. **Notification gap: these only log. Proper fix = external uptime monitor (Cloudflare Health Checks or an external pinger hitting `https://stage2.trxstat.com/healthz`) — not a homegrown emailer. Set this up in the Cloudflare dashboard.**

## Security posture

5 CRITICAL + ~10 HIGH from the 2026-05-15 audit closed (see `/home/afshin/SECURITY_AUDIT_2026-05-15_*.md` + memory). Public 80/443 closed (cloudflared-only ingress). CSRF on admin. Remaining HIGH (tracked, lower likelihood): JWT-in-URL on `/login/*`, SERVICE_API_KEY dual-use, CSP `unsafe-inline`. Re-audit cadence: before prod cutover + quarterly.

## When something breaks

1. `ssh <box> 'systemctl status tradewave-* --no-pager'`
2. `ssh <box> 'tail -50 /var/log/tradewave/{web,appserver}.error.log'`
3. `ssh <box> 'journalctl -u tradewave-<svc> --no-pager -n 50'`
4. `df -h /` — disk full is the usual culprit if logrotate ever lapses.
5. Roll back: `git -C /home/flask reset --hard <prev> && systemctl restart …` (last resort; prefer fixing forward).
