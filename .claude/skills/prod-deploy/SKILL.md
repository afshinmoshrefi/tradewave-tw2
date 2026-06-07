---
name: prod-deploy
description: TradeWave production deployment process. Use whenever deploying new code to production — "deploy to prod", "run deploy.sh prod", "ship to production", "production deploy/release". ENFORCES the mandatory pre-deploy server-snapshot gate before any prod-affecting action.
---

# Production deployment (TradeWave)

## ⛔ HARD GATE — server snapshots first (NEVER skip)

Before **any major deployment of new code to production**, the operator (Afshin) takes:
- an **up-to-date snapshot of the WEB server**, named with the **current date**, AND
- a snapshot of the **APPSERVER**.

These snapshots are the **rollback path**. Therefore:

> **NEVER run a production deploy (`bash ops/deploy.sh prod`, or any prod-affecting step) unless Afshin has EXPLICITLY told you, in the current conversation, that the snapshots are taken.**

If he has not said so, **STOP and ask**: "Have you taken today's web + appserver snapshots?" Then wait for confirmation. Do **not** assume, and do **not** rely on a confirmation from a prior session/day. This is non-negotiable.

## Process (only after the gate is cleared)

1. **Confirm snapshots** — the gate above.
2. **Code is on `main` + pushed** — `deploy.sh` deploys `origin/main`. Ensure the release is merged to main, reconciled with any prod hotfixes, and the working tree is clean. (Validate on **staging first** — `bash ops/deploy.sh staging` — to catch deploy bugs.)
3. **Pre-flight the prod boxes** (`ssh -p 4369`; web `194.113.195.141`, app `138.128.240.115`):
   - reachable; `TW2_PUBLIC_HOST` set; `RESEND_API_KEY` set if affiliate/transactional emails are needed (best-effort otherwise).
   - `git` clean **as the `flask` user** (`sudo -u flask git -C /home/flask status`); `git stash` or resolve any stray local edits so `git pull --ff-only` succeeds (run git as `flask`, not root — root hits "dubious ownership").
   - `alembic current` is at a clean head so `migrate.sh` applies cleanly (it's fail-closed — a bad/mismatched alembic state aborts the deploy).
   - per-box nginx rules present, e.g. `location /affiliate/sign/` in `/etc/nginx/sites-enabled/tw2-prod-web` (a symlink to `sites-available/tw2-prod-web`). `deploy.sh` does **NOT** ship the site config — per-box nginx is managed on the box. Add the rule after `location /stripe/`, then `nginx -t && systemctl reload nginx`.
4. **Deploy** — from the dev box: `bash ops/deploy.sh prod`. It runs `migrate.sh` (alembic upgrade head + the additive `apiserver/schema.sql` for `users.api_tier`) **before** the web restart, ships static pages + the React bundle, reloads nginx (CSP snippet only), and **skips the developer portal on prod** (API/MCP dark).
5. **Verify** — the live customer host is **`tradewave.ai`** (behind Cloudflare; plain `curl` gets a 403 bot-challenge). Verify through the prod box's nginx with a Host header:
   ```
   ssh -p 4369 root@194.113.195.141 'for p in /healthz /affiliate /affiliate/sign/x /account/api; do printf "  %s -> %s\n" "$p" "$(curl -s -o /dev/null -w "%{http_code}" -H "Host: tradewave.ai" http://127.0.0.1$p)"; done'
   ```
   Expect: `/healthz` 200, `/affiliate` 200, `/affiliate/sign/x` 410, `/account/api` 404 (API console dark). Confirm `systemctl is-active tradewave-web` = active.
6. **Rollback** if needed — React: flip the `build` symlink to `build-previous` (instant). Schema/code: restore from the date-named server snapshots from step 1.

## Notes
- `tw2-prod.trxstat.com` is the deploy/placeholder name and is **not** externally routed; the live host is `tradewave.ai`.
- API/MCP ships "dark" on prod: the `/account/api` console is gated by `TW2_API_CONSOLE_ENABLED` (unset on prod), and the gateway/MCP services + `developers.` portal are not provisioned.
- Secrets (`/etc/tradewave/secrets.env`) are **per-box and NOT in git** — `deploy.sh` never touches them. Set new ones (e.g. `RESEND_API_KEY`) on the box by hand.
