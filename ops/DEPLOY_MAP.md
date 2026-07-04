# TradeWave deploy map (boxes, hosts, per-box config, flow)

The single reference for "what runs where" and "what must be true on each box" so a deploy
is one command and a verify is the gate. Pair with `ops/deploy.sh`, `ops/regen_site.sh`,
`ops/verify_deploy.sh`, and the `prod-deploy` skill.

## Topology - two boxes per environment

| Env     | WEB box (nginx + Flask + static site)        | APP box (data engine + API/MCP + portal)            |
|---------|-----------------------------------------------|-----------------------------------------------------|
| staging | `185.53.209.8`  host `tw2-stage.trxstat.com`  | `199.244.48.157` (api/mcp/developers-stage)         |
| prod    | `194.113.195.141` host `tradewave.ai`         | `138.128.240.115` (API/MCP **LIVE** since 2026-07 launch) |

SSH: `ssh -p 4369 root@<ip>`. Internal VLAN: appserver `10.0.0.92`, web `10.0.0.94`.
All public hosts are **Cloudflare tunnels** (cloudflared per box) - never convert to an A record.

### WEB box runs
- `nginx` (vhost `/etc/nginx/sites-enabled/tw2-<env>-web`) + `tradewave-web` (Flask/gunicorn, WorkOS/Stripe/Postgres).
- The static-site generators in `/home/flask/site/` -> output to `/var/www/tradewave/`.
- cloudflared tunnel `tw2-<env>-web` -> the public main host.
- **No SMN tree** on the staging web box (`/home/flask/smn` absent) - see "SMN pipeline" below.

### APP box runs
- `tradewave-appserver` (data engine), `tradewave-apiserver` (:8088 gateway), `tradewave-mcpserver` (:9090).
- `nginx` on **:8080** fronting the developer portal vhost (api/mcp/developers-*) -> docroot `/var/www/developers/`.
- cloudflared tunnel `tw2-<env>-app` -> api-/mcp-/developers-* hosts (ALL envs incl. prod since the 2026-07 API/MCP launch).

## Per-box config that is NOT in git (managed on the box)

`deploy.sh` never ships these. They are the usual source of "messy deploy"; keep them correct per box.

### 1. `/etc/tradewave/secrets.env` (host vars + secrets; root:flask 640, flask-readable)
Both boxes must have **`TW2_PUBLIC_HOST` = the customer host** (`deploy.sh` pre-flight enforces value==host on both):
- web + app: `TW2_PUBLIC_HOST=<host>` and `TW2_DOMAIN_ROOT=https://<host>` (staging `tw2-stage.trxstat.com`, prod `tradewave.ai`).
  - The app box was historically left at `stage2.trxstat.com` (NXDOMAIN) - this bakes dead portal back-links. Fixed 2026-06-19; keep it = the web host.
- app box portal hosts: `TW2_API_PUBLIC_HOST`, `TW2_MCP_PUBLIC_HOST`, `TW2_DEVELOPERS_PUBLIC_HOST` (= api-/mcp-/developers-<env>). The portal's OWN host comes from these, so they do NOT collide with `TW2_PUBLIC_HOST`.
- SMN host vars: `TW2_NEWS_WEBSITE_URL`, `TW2_SMN_FAVICON_URL`, `TW2_ARTICLE_FAVICON_URL` should point at the env's SMN host (e.g. `smn-stage` / the prod SMN host), NOT `smn-dev`. (Staging still carries some `smn-dev` values - cosmetic favicon on SMN/news pages; set correctly on prod.)
- `STRIPE_WEBHOOK_SECRET` = the real `whsec_...` on prod (staging carries a placeholder -> webhook fail-closes 503, expected).
- `TW2_API_CONSOLE_ENABLED=1` lights the `/account/api` console (web box; set on staging AND prod since the 2026-07 launch).

### 2. nginx vhost `/etc/nginx/sites-enabled/tw2-<env>-web` (symlink -> sites-available)
Route rules are per-box. Every customer route that is NOT a static file must `proxy_pass http://tw2_web`.
Required `location` blocks (mirror them across envs): `= /signup = /login = /logout = /account /account/ = /pricing = /healthz /auth/ /api/ /webhooks/ /admin /admin/ /stripe/ /affiliate/sign/ **/join/** /app...`; plus `/appserver/ -> tw2_appserver` (VLAN). Fallthrough `location / { try_files ... =404; }`.
- **`location /join/`** (affiliate co-branded landing) was MISSING on staging -> `/join/<code>` 404'd. Added 2026-06-19. Prod added it 2026-06-09. `verify_deploy.sh` checks `/join/TESTCODE != 404`.

### 3. cloudflared tunnel config (per box)
`tunnel route dns` mappings: web tunnel -> main host; app tunnel -> api-/mcp-/developers-<env>. Backed up to `config.yml.bak` when edited.

## Deploy flow - `bash ops/deploy.sh {staging|prod}` (run from the dev box)

1. **pre-flight**: `TW2_PUBLIC_HOST` value == the env host on BOTH boxes, else abort.
2. **app tier**: git pull (ff) + venv sync + restart `tradewave-appserver`; restart `apiserver`/`mcpserver` if provisioned (gateway `/healthz` gate).
3. **web tier**: git pull (ff) + venv sync + `migrate.sh` (alembic upgrade head + additive `apiserver/schema.sql`, fail-closed) + restart `tradewave-web` (+ SMN daemons if present).
4. **regen_site** (`ops/regen_site.sh`, as flask, secrets sourced): run EVERY main-site generator in **DATA-compute-then-RENDER** order with the correct host: `insights_charts` -> authored pages (text/about/research/insights/learn) -> `ticker` -> **`home_opportunities` (data: Top Patterns CSV)** -> **`home`** (sole writer of the new featured-pick row in `data/featured_history.json`) -> **`scorecard`** (reads that row + recomputes outcomes live; MUST follow `home`) -> `daily-pick` -> `markets` (SKIP if no SMN tree) -> **`refresh_market_quotes` (last: re-injects live prices + writes `assets/quotes.json`)**. Each step is fail-soft (logs + counts, never aborts). The home/scorecard/ticker/opportunities steps need the appserver (restarted in step 2); home also needs the ML scorer + live Stripe.
5. **React**: rsync to `releases/build-<hash>`, repoint `build` symlink (`build-previous` = instant rollback).
6. **nginx**: refresh the shared CSP snippet + reload (vhost itself is per-box, not shipped).
7. **portal**: assemble on the **APP box** (`/var/www/developers`) on EVERY env (prod dark-ship retired 2026-07-04; skips cleanly on an unprovisioned box).
8. **verify_deploy** (`ops/verify_deploy.sh <env>`): fail-loud smoke - services, routes (incl `/markets/`, `/join/`), baked-HTML host-leak grep, design/feature markers. Nonzero exit => live-but-not-clean.

### Pre-pull hygiene (both boxes, as the `flask` user)
`deploy.sh` uses `git pull --ff-only`; stray working-tree edits abort it. Clear them first:
`sudo -u flask git -C /home/flask status` then `sudo -u flask git -C /home/flask checkout -- <files>` (or stash). Never run box git as root (dubious-ownership).

## SMN pipeline (markets / news pages) - SEPARATE from deploy.sh

`generate_security_pages.py` imports `generate_tw_security_pages` from the SMN tree (`/home/flask/smn`); it CANNOT run on a bare web box. Market + news pages are produced where SMN lives and rsync'd into `/var/www/tradewave/markets` + `_static/markets`. `regen_site.sh` skips markets cleanly when SMN is absent. A clean `/markets/*` on an env requires running the SMN pipeline there - it is not a `deploy.sh` step.

## Rollback
- React: flip `build` symlink to `build-previous` (instant).
- Code/schema: restore from the date-named WEB + APP server snapshots (the prod snapshot gate).

## Prod-specific gates
- **Snapshot gate** (hard): never deploy prod unless Afshin confirms today's WEB + APP snapshots in the current conversation.
- API/MCP/portal are deployed + verified on prod like staging since 2026-07-04 (dark-ship retired; provision via ops/bootstrap_api_services.sh + PROD_CUTOVER.md 102-149 first).
- Live host is `tradewave.ai` behind Cloudflare (plain curl gets a 403 challenge) - verify through the box nginx with a `Host:` header (`verify_deploy.sh` does this).
