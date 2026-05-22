# TradeWave Ecosystem - Single Source of Truth (TW1 + TW2)

> **READ THIS FIRST, before planning or doing ANY TradeWave task.** This is the
> canonical, code-verified map of the whole ecosystem. It exists so agents and
> sessions stop guessing, duplicating, and mis-modeling the system. If a memory
> file disagrees with this doc, this doc wins (it was built by reading the actual
> code + the live `.151`/`.176` boxes on 2026-05-22).
>
> **KEEP IT CURRENT (hard rule):** any change that alters architecture, a data
> flow, a deploy step, an invariant, or a path MUST update this doc in the SAME
> commit. Operational deploy detail lives in `ops/OPERATIONS.md`; cutover detail
> in `ops/PROD_CUTOVER.md`; this doc is the high-level map that points into them.
>
> Citations are `file:line` or box name. "OPEN" / "DRIFT" flags mark verified
> gaps and stale references found during the audit - see §13.

---

## 1. The mental model (internalize this)

- **The appserver is the data engine.** It is the ONLY component with the market
  data (CSV/parquet) and the seasonal-pattern computation. **Everything else -
  the React wave-viewer, the web tier, every content generator (home page,
  scorecard, tickers, daily pick), the SMN pipeline - is a CLIENT** that queries
  the appserver over HTTP and must authenticate first. "Why does X log into the
  appserver?" -> because X needs opportunity/chart data and the appserver gates it.
- **Content is generated, then served static.** Marketing/content pages (home,
  scorecard, `/patterns/` tickers, insights, SMN articles) are pre-generated to
  static HTML by Python generators and served by nginx off disk. The Flask web
  tier only handles auth, the `/app/` React shell, account/billing, admin.
- **TW1's WordPress is bypassed for content.** TW1 still has WordPress (for
  membership/UMP), but nginx serves the content URLs from a static `_static/`
  tree, overriding WP. There is no "WordPress page rendering" for that content.
- **TW2 = WordPress-removal rebuild of TW1.** Same appserver/data lineage and the
  same React app; the WP/UMP/PHP auth+membership producer is replaced by WorkOS +
  Stripe + Postgres + Flask, keeping the React consumer and the appserver
  `/login` handshake protocol unchanged.

---

## 2. TW1 (the system being replaced)

**Box:** TW1 dev = `192.168.1.151` (Ubuntu 20.04, Python 3.8). TW1 **prod** web =
`10.0.0.40` (Kamatera VLAN), owns `tradewave.ai` until cutover. `.151` is
read-only inspectable: `ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes root@192.168.1.151`.

### 2.1 Serving model (WordPress bypassed)
nginx port 80, root `/var/www/html/wordpress`, uses `try_files` to serve static
HTML from `_static/` BEFORE falling back to WordPress/PHP:

| URL | Served from |
|---|---|
| `/` | `_static/home.html` (regenerated frequently) -> WP fallback |
| `/scorecard` | `_static/scorecard.html` -> WP fallback |
| `/patterns/<TICKER>` | `_static/patterns/<TICKER>.html` (regex location) -> 404 |
| `/webinars` | `_static/webinars/index.html` -> WP fallback |
| everything else | WordPress (`index.php`) |

So content pages are TW1's own static HTML (no WP chrome). SMN articles likewise
publish as static HTML (`publish_to='html_folder'` -> `/var/www/html/smn/articles/`).
(Source: `.151` `nginx -T`; `reference_tw1_dev_vm_151.md`.)

### 2.2 Services & ports (.151)
gunicorn-on-unix-socket Flask services, all run as user `flask`:
`appserver.service` (data API), `keyprovider.service` (:7777, shared WP<->Flask
secret), `stockscore.service` (:7771), `data_updater.service` (:7778 updateserver),
`logcollector.service` (:7676). Plus mysql (WP), php7.4-fpm, redis, nginx.
`blog_queue` (:5001, SMN paywall API) is referenced but not always running.
Per-minute crons rotate the keyprovider key (`keystore/generate_key.py`) and
persist logs. (Source: `.151` `systemctl`, `ss -tlnp`, `/etc/crontab`.)

### 2.3 Content generators + the DAILY-PICK / SCORECARD pipeline (DEFINITIVE)
Generators live in `/home/flask/blog/` on TW1 (TW2 moved them to `site/` + `smn/`):

- **Home page** (`blog/generate_home_page.py`) -> `_static/home.html`. Reads
  `home_opportunities.csv` + ML scorer + appserver (OppList4/ChartHistorical2) +
  stockscore. Calls `generate_scorecard()` at the end.
- **Scorecard** (`blog/generate_scorecard.py`, cron `*/10` weekdays) ->
  `_static/scorecard.html`. Reads `featured_history.json` + live prices.
- **Tickers** (`blog/generate_top10_AI.py` / `top10_jobs_today_to_queue_cron.py`)
  - "AI" here = Sharpe-ranked OppList4, NOT an LLM.
- **SMN articles** (cron: `select_news_articles.py` 02:00 -> `daily_article_queue.py`
  03:00 -> always-running `article_processor.py`). THIS pipeline DOES use LLMs:
  Grok (`grok-3-mini`/`grok-3`) for news extraction + research, OpenAI `gpt-5.1`
  for writing, Claude `claude-sonnet-4-6` for SEO titles, Stability SDXL for images.

**THE DAILY AI PICK = SCORECARD (settles prior confusion, verified on .151):**
- The "daily AI pick" shown on the home page and tracked in the scorecard is
  selected by the **ML scorer, NOT an LLM**.
- Pipeline: `daily_pattern_picks.get_daily_picks()` POSTs to the ML scorer
  (`ml_scorer/daily_opp_selection.py` `/select`), which filters S&P-500 candidates
  (sharpe>1, avg_profit>=5, win_prob>=0.75), scores them through an ML ensemble,
  and ranks by `win_prob`. `select_featured_from_ml_scorer()` then walks the ranked
  list top-down, **skips any symbol featured in the last 14 days**, and takes the
  **FIRST one OppList4 confirms** - no LLM consulted. The pick is appended to
  `featured_history.json`.
- **`featured_history.json` IS the daily-pick record AND the scorecard's data
  source.** Each entry = symbol + featured_date + pattern + ML metrics
  (sharpe, win_prob, ml_score, pred_return...) + price tracking (start/end/peak,
  win/loss). `generate_scorecard.py` reads it and renders the track record;
  `generate_home_page.py` appends to it; `send_daily_ai_pick.py` emails from it.
- So: the user's belief ("the daily AI pick is what gets stored in the scorecard")
  is **correct**. The "AI" = the ML scorer.
- **OPEN:** TW2 has a standalone `site/generate_daily_ai_pick.py` -> `daily-ai-pick.html`
  that may invoke an LLM for narrative. Confirm whether that page is the same pick
  as the scorecard featured pick or a separate artifact before relying on it.
(Source: `.151` `blog/*.py`, `ml_scorer/daily_opp_selection.py`, `featured_history.json`.)

### 2.4 TW1 auth (the "headcheese" pattern - the contract TW2 replaces)
1. WP `headcheese()` (Divi-child `functions.php`) runs on the React page load.
2. Fetches keyprovider (`:7777`) -> `{key1, key2}`. `key1` = LTK (login token);
   `key2` = UMP API gate key.
3. Injects `window.current_user_id`, `window.current_user_level` (UMP level IDs),
   `window.ltk` (=key1).
4. React calls appserver `/login/<wp_userid>/<user_level>/<country>/<zip>/<skey>`
   with `skey==key1`.
5. Appserver verifies skey == keyprovider's current key1 -> mints session token.

(Source: `reference_tw1_auth_flow.md`, verified against `.151`.)

---

## 3. TW2 topology (3 environments, all Cloudflare tunnels)

**Promotion flow: dev -> staging -> verify -> prod.** Staging is the prod GATE
(affirmed 2026-05-22); never deploy dev->prod direct, never skip/drop staging.

| Role | Public IP | VLAN | Tunnel hostname | SSH |
|---|---|---|---|---|
| dev (all tiers, one box) | 192.168.1.176 | - | `tw2-dev.trxstat.com`, `smn-dev` | local |
| stage-web | 185.53.209.8 | 10.0.0.94 | `tw2-stage.trxstat.com`, `smn-stage` | `root@185.53.209.8 -p 4369` |
| stage-app | 199.244.48.157 | 10.0.0.92 | `tw2-stage-app.trxstat.com` | `root@199.244.48.157 -p 4369` |
| prod-web | 194.113.195.141 | 10.0.0.98 | `tw2-prod.trxstat.com` (-> `tradewave.ai` at cutover) | `root@194.113.195.141 -p 4369` |
| prod-app | 138.128.240.115 | 10.0.0.96 | `tw2-prod-app.trxstat.com` | `root@138.128.240.115 -p 4369` |
| TW1 prod web | (ref) | 10.0.0.40 | owns `tradewave.ai` until cutover | - |

**All hosts are Cloudflare TUNNEL CNAMEs, never A records** (origin IPs never in
DNS). Do NOT convert prod to an A record. cloudflared on each box dials out;
public 80/443 is closed (cloudflared-only ingress). (Source: `OPERATIONS.md`,
`/etc/cloudflared/config.yml`, `bootstrap_stage_*_tunnel.sh`, `project_tw2_cloudflare_tunnels.md`.)

**Web box runs:** gunicorn `app:app` (:5500) behind nginx; `tradewave-web`,
`tradewave-blog-queue`, `tradewave-article-processor`; redis; cloudflared; all
content/email crons; serves `/var/www/tradewave/` + `/var/www/smn/`.
**App box runs:** gunicorn `appserver:app` (:80 on staging/prod via
CAP_NET_BIND_SERVICE; **:5000 on dev**); Postgres (web connects over VLAN);
redis; cloudflared; `/home/flask/data/` (US subset on staging, full on prod);
DB backups. (Source: installed `tradewave-*.service`, `migrate_app_port_to_80.sh`.)

> **DRIFT:** several bootstrap scripts + `make_staging_secrets.sh` still hardcode
> `stage2.trxstat.com` and `TW2_DOMAIN_ROOT`; `bootstrap_stage_app_services.sh`
> writes the SMN daemons on the app box though they actually run on web
> (`migrate_smn_to_web.sh` moved them). The live staging host is `tw2-stage.trxstat.com`.

---

## 4. config.py and secrets (the "where settings live" map)

`config.py` is **env-agnostic** - every per-env value comes from
`/etc/tradewave/secrets.env` via `os.environ.get()`. Never hardcode per-env values.

- `TW2_PUBLIC_HOST` -> `tw2_public_url` = `https://<host>/`; `domain_root` is an
  ALIAS of `tw2_public_url` (config.py:117-127). `TW2_DOMAIN_ROOT` is **retired**.
- `TW2_ENV` (explicit) or hostname inference -> `tw2_env` (`dev|staging|prod`),
  config.py:137-145. Drives `seo_enabled = (tw2_env=='prod')` (config.py:304).
- Key dicts: `available_resources`/`_path`/`exchange_mapping` (17 markets,
  keys `'0'..'13','16'`); `level_access_hierarchy` (backend market filter -
  **all levels currently get all 17 markets, open-paywall launch decision**);
  `num_*_allowed_by_level`; `TIER_FEATURES` (explorer/analyst/strategist matrix +
  pricing); `ROLE_BYPASSES_TIER={super_admin,staff_admin,service_account}`.
- secrets.env vars (NAMES only): WorkOS (`WORKOS_CLIENT_ID/API_KEY/COOKIE_PASSWORD/AUTHKIT_DOMAIN`,
  `TW2_AUTH_CALLBACK_URL`), Stripe (`STRIPE_PUBLISHABLE_KEY/SECRET_KEY/WEBHOOK_SECRET`),
  `POSTGRES_DSN`, inter-service (`SERVICE_API_KEY`, `APPSERVER_JWT_SECRET`,
  `API_KEY_HMAC_SECRET` [defaults to APPSERVER_JWT_SECRET]), env identity
  (`TW2_PUBLIC_HOST`, `TW2_ENV`), cross-tier (`TW2_APPSERVER_URL/IP`, `TW2_WEBSERVER_IP`),
  and external APIs (`EOD_TOKEN`, `ANTHROPIC_TOKEN`, `OPENAI_KEY`, `GROK_API_KEY`,
  `PERPLEXITY_API_KEY`, `REPLICATE_API_TOKEN`, `TAVILY_API_KEY`, `MAILERLITE_*`,
  `PUBLER_*`, `FACEBOOK_*`, `INDEXNOW_KEY`, `TW2_GA_MEASUREMENT_ID`, `SENTRY_DSN`,
  service URLs `TW2_ML_SCORER_URL/STOCKSCORE_URL/REALTIME_SERVICE_URL/EDGAR_SERVICE_URL/
  UPDATE_SERVER/KEYSTORE_URL/MASTER_APPSERVER/BLOG_QUEUE_SERVER/NEWS_WEBSITE_URL`).
- systemd loads it via `EnvironmentFile=`; a `<unit>.service.d/override.conf`
  `Environment=` wins over secrets.env.
> **GOTCHA:** the `TW2_*_URL` service URLs must use the **VLAN `10.0.0.x`** addresses
> from inside the Kamatera network, not the public `104.238.214.253` (the central
> box allowlists by source IP -> public IP gets 403). `make_staging_secrets.sh`
> copies dev's public URLs, so these need hand-correction per env.
(Source: `config.py`, `make_staging_secrets.sh`, `web/app.py:157`.)

---

## 5. TW2 web tier (`web/app.py`, gunicorn `app:app` :5500)

Handles auth, the `/app/` shell, account/billing, admin. Marketing pages are NOT
Flask-rendered (static from `/var/www/tradewave/`).

- **Routes:** `/healthz`, `/signup`, `/login`, `/auth/callback`, `/logout` (POST,
  CSRF-exempt, same-origin redirect to `/`), `/api/me`, `/app` + `/app/`
  (`app_index`), `/account`, `/pricing`, `/api/stripe/create-checkout`,
  `/stripe/success|cancel`, `/account/manage-subscription`, `/webhooks/stripe`,
  `/webhooks/workos`, `/internal/render_report` + `/internal/delete_report`
  (X-Service-Key), `/admin/*` (super_admin).
- **Auth = WorkOS AuthKit sealed session.** `/auth/callback` exchanges code ->
  seals session into the `tw2_session` cookie (httponly, secure, SameSite=Lax,
  7-day); `lazy_create_user()` upserts the Postgres `users` row (matches by
  `workos_user_id` then email; auto-grants `super_admin` to the owner email).
  `REDIRECT_URI` = `TW2_AUTH_CALLBACK_URL` (read ONCE at process start, app.py:157).
- **LTK** (`generate_ltk()`, app.py:616): HS256 JWT signed with
  `APPSERVER_JWT_SECRET`, `aud="tw2-appserver"`, `iss="tw2-web"`, 8h, carrying
  `user_id, tier, legacy_level, roles, is_admin`. Injected as `window.ltk`; the
  React app exchanges it at the appserver `/login`.
- **`app_index()`** serves `web-react/build/index.html` with injected globals:
  `window.current_user_id`, `current_user_level` (legacy numeric via tier_compat),
  `ltk`, `tw2_user_email/tier/is_admin/user_roles`, `tw2_env`.
- **Admin:** Flask-Admin gated on `super_admin` role; `UserAdmin` validates
  `roles` against `models.ROLES`. **Roles single source of truth = `models.py:ROLES`**
  = `{super_admin, user, newsroom_author, service_account}`.
- **`report_renderer.py`:** renders a static date-range report (HTML + 3 PNGs) to
  `/var/www/tradewave/r/<slug>/`; invoked by the appserver via
  `/internal/render_report` (semaphore-limited to 4 concurrent).
(Source: `web/app.py`, `web/models.py`, `web/report_renderer.py`, `web/tier_compat.py`.)

---

## 6. TW2 appserver (`appserver/appserver/appserver.py`, gunicorn `appserver:app`)

The data engine. 73 routes; dev :5000 / staging+prod :80. Redis db0 cache, db2
persistent (reports/portfolios/watchlists), db3 news. Reads CSV under
`/home/flask/data/csv/`. Two auth paths:

1. **`/login/<wp_userid>/<level>/<country>/<zip>/<skey>`** - the LTK handshake.
   `skey` must be a valid LTK (HS256, `aud=tw2-appserver`, `iss=tw2-web`,
   `APPSERVER_JWT_SECRET`). Identity cross-checked (URL `wp_userid` vs LTK
   `user_id` -> 403 on mismatch). Gating sourced from LTK claims. Mints a 24h
   session token (`?token=`) for all data endpoints. (Old WP/UMP/keyprovider
   branch is dead code; `useUMP`/central-server removed 2026-05-21.)
2. **`/login/api/<api_key>`** (`login_api`) - the SERVICE login. Hashes the key
   with `API_KEY_HMAC_SECRET`, looks up `users.api_key_hash`; **no match -> 403
   "invalid api_key"**. Used by server-side scripts (e.g. `home_opportunities.py`
   via `SERVICE_API_KEY`). **Fails until a service-account row's `api_key_hash` is
   backfilled via `web/db_admin.py`** (the plaintext `api_key` column was dropped;
   only the hash is stored). This is why `home_opportunities`/`daily_ai_pick`
   currently 403 on staging.
- **Data endpoints** (all require `?token=`, `@check_for_token` enforces aud/iss):
  `OppList4`, `OppBySymbol`, `ChartData4`, `YearsMetaData2`, `ChartHistorical2`,
  `StockMetaData`, `getStockPriceByDate`, `consolidated_seasonal_chart2`,
  `StockScoreBatch`, `MLScoreBatch`/`MLScorePending`, etc. Short Redis TTLs (~51s);
  historical price-by-date cached 11.5 days.
- **Gating:** `level_access_hierarchy` by numeric level; OppList4 caps results
  (anon 3, free '1' 5, paid premium up to 5000). ML scoring restricted to levels
  6/7 and resource IDs 0-4,11.
(Source: `appserver/appserver/appserver.py`, `web/app.py:616`, `config.py`.)

---

## 7. TW2 React app (`web-react/`, served at `/app/`)

- CRA + react-scripts 5, React 17, `PUBLIC_URL=/app/`. Built ONCE on dev, same
  bundle to all envs (env-agnostic). `build/` is gitignored.
- Consumes injected `window.*` globals; `window.current_user_id`+`window.ltk` ->
  combined login token; calls the appserver via the same-origin `/appserver/`
  proxy (`appserverURL()` returns `/appserver`, never a hardcoded host).
- Login: `GET /appserver/login/<id>/<level>/<dev>/<os>/<token>` -> session JWT
  (stored in React state, sent as `?token=` on all data calls). JWT carries quotas,
  `roles`, `is_admin`, `resource_disp`, `upgrade_message`.
- **Runtime per-env gating:** `consoleGuard.js` (imported first) suppresses
  `console.log/debug/info` unless `window.tw2_env` is dev/staging (keeps the
  appserver JWT out of the prod console). Role-gating: article icons gated on
  `userRoles.includes('newsroom_author') || isAdmin` (ReportsDashboard.js).
- Features: PE-cycle overlays/filters (`mode=pe`), years selectors, securities
  groups + published lists + watchlists, the `?o=BASE64` shareable pattern param,
  the "Tara" chatbot, wave-viewer charts (bar/cumulative/price).
(Source: `web-react/src/*`, `web/app.py:679`, `project_tw2_react_build_env.md`.)

---

## 8. Deploy / ops / cron

**Routine deploy = `bash ops/deploy.sh {staging|prod}`** from dev. Per env:
pre-flight (`TW2_PUBLIC_HOST` set on both boxes, else abort) -> per tier
`git pull --ff-only` + `pip install -r requirements.txt` (mandatory - a missing
dep crash-loops workers into a 502) + restart (`tradewave-appserver` on app;
`tradewave-web` + `tradewave-blog-queue` + `tradewave-article-processor` on web)
+ `is-active` -> React symlink-swap -> nginx CSP reload. Full detail +
restart-matrix: `ops/OPERATIONS.md`.

**React deploy = SYMLINK SWAP** (NOT a dir copy, NOT git pull): `build` is a
symlink to `releases/build-<commit>`; deploy rsyncs to a new release dir then
`ln -sfn`; `build-previous` = instant rollback (`ln -sfn "$(readlink build-previous)" build`).
(`ops/deploy.sh`, `project_tw2_react_deploy.md`.)

**TW1->TW2 sync = temp-key pattern:** dev pushes its TW1-authorized key to the
target web box, the target rsyncs FROM TW1 prod (`10.0.0.40`) over the VLAN, key
is shredded on exit. Used by `migrate_smn_content_from_tw1.sh` (`/var/www/smn/`),
`migrate_scorecard_from_tw1.sh` (`featured_history.json`), `ops/sync_content_from_tw1.sh`.
**The only genuine file-sync from TW1 is `featured_history.json`** (TW1
`/home/flask/blog/` -> TW2 `/home/flask/site/data/`); the home/scorecard/ticker/
daily-pick content is GENERATED by TW2 (needs the appserver, hence the api_key
prereq). See `project_tw2_content_sync.md`.

**Crons** (web box flask crontab): SMN pipeline (select 02:00 / queue 03:00 /
always-on processor), security pages, `home_opportunities.py` (00:04),
`generate_home_page.py` (07:00), `generate_scorecard.py` (every 10m, 09-16),
`update_news_quotes.py` (every min), SMN emails, daily-AI-pick email + social,
EOD `update_client2.py` (23:36), ticker regen (02:00 + hourly 09-16). App box:
DB backup 03:30 + weekly restore drill. (`make_bulletproof.sh`, `OPERATIONS.md §16`.)
> **GAPS:** `expire_trials.py` (15 04) is NOT installed by `make_bulletproof.sh`;
> `generate_home_page.py` still hardcodes `CANONICAL_ROOT=tw2.trxstat.com` /
> `APPSERVER_URL=app1pp` (fix before a prod home regen).

**Box rebuild from scratch:** 17 ordered idempotent steps in `ops/staging/`
(bootstrap OS -> code+venv -> secrets -> schema -> data lift -> services ->
:80 -> tunnel -> cross-tier render -> SMN -> scorecard -> hardening -> lockdown ->
bulletproof). See `OPERATIONS.md`.

**Deploy gotchas** (see `OPERATIONS.md` "Deploy gotchas"):
- `/app/` 502 but service "active" = gunicorn workers crash-looping on a missing
  venv dep; check `/var/log/tradewave/web.error.log`; `pip install`. (Static home
  still serves -> "home OK, app 502" = dead workers.) This was the `flask_wtf`
  cause of "staging broken."
- `git pull` aborts on `config.py` = box drift (a prior surgical
  `git checkout origin/main -- config.py`); `git checkout HEAD -- config.py && git pull`
  after reading the diff. (Clean-but-old tree is NOT drift.)
- Run all box git/build/file ops as `sudo -u flask` (root-owned `.git/index`
  breaks the next pull; `chown -R flask:flask /home/flask` to recover).
- Renaming an env URL touches 6 places: Cloudflare DNS, cloudflared ingress
  (RESTART cloudflared), nginx `server_name` (reload), secrets `TW2_PUBLIC_HOST`
  + `TW2_AUTH_CALLBACK_URL` (restart web), WorkOS redirect URI, and the browser
  cache (test incognito). Verify with `curl -sS -i https://<host>/login | grep -i location`.

---

## 9. Auth, billing, cutover

- **WorkOS:** dev + staging share a "Staging" env (test keys; AuthKit domain
  `rapid-fish-71-staging.authkit.app`, client `client_01KQNXQ43D9ASZC4E4JTB4Y2JV`);
  prod has its own "Production" env. Sealed-session cookie; redirect URIs
  registered per WorkOS env + driven by `TW2_AUTH_CALLBACK_URL`.
- **Stripe:** TW2 SHARES TW1's LIVE Stripe account. The `/webhooks/stripe` handler
  MUST return **200** for foreign/unmatched-customer events (records a
  `processing_error` row, replayable in `/admin`); a 5xx causes Stripe retry-storm
  + auto-disable. Prices are pulled live from active Stripe prices filtered by
  product metadata (`product_line=eod`, `tier`, `period`) - NOT hardcoded;
  in-process cache, restart `tradewave-web` after a price change. 7-day trial in
  checkout; Stripe Billing Portal for cancel/manage.
- **Legacy billing (pre-cutover blocker):** TW1's UMP created one Stripe price per
  subscriber (~14+ no-metadata legacy prices, e.g. strategist-yearly $189). TW2's
  active+metadata cache can't map them. **FREEZE: do not archive any price with an
  active subscription.** A `{legacy_price_id: tier}` PIN MAP + a
  "never downgrade on unrecognized price" guard are REQUIRED for cutover and
  **do not yet exist in code** (OPEN).
- **Tiers:** explorer/analyst/strategist (TIER_FEATURES). tier_compat:
  explorer->'1', analyst->'4'/'5', strategist->'6'/'7'.
- **Cutover (TW1 -> tradewave.ai), per `ops/PROD_CUTOVER.md`:** Phase 1 (days
  ahead): lower TTL to 60s, add `tradewave.ai` to prod tunnel ingress, WorkOS prod
  redirect URI, Stripe prod webhook, pre-seed `users` from a TW1 DB dump. Phase 2
  (minutes): final user delta sync, flip the `tradewave.ai` DNS to the prod tunnel,
  purge CF cache, re-point `TW2_PUBLIC_HOST`/`TW2_AUTH_CALLBACK_URL` + nginx
  server_name + restart web, regenerate static/SMN content (`ops/cutover_repoint.sh`
  does the box-side). App box + React bundle: no change. Rollback = restore the DNS
  record (TW1 kept running as the rollback target for a soak period).
- **Post-cutover roadmap:** cutover -> 2-4wk stabilization (HARD RULE: no prod
  deploys touching billing/auth/data paths) -> TW1 decommission -> v2 (affiliate,
  then API, then MCP [thin wrapper over the API], then paid-SMN).
(Source: `web/app.py`, `config.py`, `ops/PROD_CUTOVER.md`, and the stripe/billing/
roadmap memories.)

---

## 10. TW1 <-> TW2 mapping

| Concept | TW1 (`.151`/`10.0.0.40`) | TW2 |
|---|---|---|
| Generators | `/home/flask/blog/` | `/home/flask/site/` + `/home/flask/smn/` |
| Daily-pick/scorecard data | `blog/featured_history.json` | `site/data/featured_history.json` |
| Home opp data | `blog/home_opportunities.csv` | `site/data/home_opportunities.csv` |
| Static web root | `/var/www/html/wordpress/_static/` (WP bypassed) | `/var/www/tradewave/` |
| SMN root | `/var/www/html/smn/` | `/var/www/smn/` |
| React source / build | `wp-content/.../seasonals/{src,build}`, `PUBLIC_URL=/wp-content/...` | `/home/flask/web-react/{src,build}`, `PUBLIC_URL=/app/` |
| Auth producer | WP + UMP + keyprovider (headcheese) | WorkOS + Stripe + Postgres + `web/app.py` (mints LTK) |
| Auth consumer + handshake | React + appserver `/login` | SAME React + SAME appserver `/login` |
| Tiers | UMP levels 1/4-5/6-7 | explorer/analyst/strategist (tier_compat -> same levels) |
| Data | `/home/flask/data/csv/` | `/home/flask/data/csv/` (same) |

---

## 11. Invariants / landmines (do NOT break)

1. **Open paywall:** `level_access_hierarchy['1']` = all 17 markets (launch
   decision). Do NOT revert without Afshin + fixing the React default-security
   fallback first.
2. **Resource keys are permanent:** keys `'0'..'16'` are stable IDs (Korea 14/15
   removed leaving a hole; crypto stays 16). Never renumber - persisted data keys off them.
3. **Stripe webhook ACK 200** for foreign/unmatched customers (shared account).
   Never revert to 5xx.
4. **FREEZE legacy Stripe price cleanup** - never archive a price with an active sub.
5. **No em-dashes** in TradeWave/SMN content (use ` - `). Date-range LABELS use
   en-dash via `tw_dateformat.py`; prose uses words; slugs stay ASCII.
6. **Never touch live/staging/prod (or TW1) directly** - author commands, the
   operator runs them. Read-only inspection of `.151` is allowed.
7. **All TW2 hosts are Cloudflare tunnels** - never convert prod to an A record.
8. **config.py is env-agnostic** - per-env values only via secrets.env. Never use
   `git checkout origin/main -- file` as a deploy mechanism (causes box drift).
   `TW2_DOMAIN_ROOT` is retired.
9. **gunicorn does not auto-reload** - restart after Python edits; deploy must
   `pip install -r requirements.txt`.
10. **Roles single source of truth = `models.py:ROLES`.**
11. **React = one bundle, symlink-swap deploy** - never rebuild per env, never
    dir-swap (breaks `build-previous` rollback), own `flask:flask`.
12. **Deploy dev -> staging -> prod** (staging is the gate). Never dev->prod direct.
13. **`years` stays a string; no casual field renames (`resourceID`/`daysOut`);
    fail-fast (no broad `except`/silent fallback).**
14. **No secrets in chat** - box-to-box only; classification-only diagnostics.
15. **Central-service `TW2_*_URL` must use VLAN `10.0.0.x`** from inside Kamatera
    (public IP gets 403'd by source-IP allowlist).

---

## 12. Where the deep detail lives

- `ops/OPERATIONS.md` - the operational runbook (deploy, restart matrix, box
  rebuild, gotchas, URL-rename procedure). Single source of truth for deploy.
- `ops/PROD_CUTOVER.md` - the cutover plan + `ops/cutover_repoint.sh`.
- `config.py` - all config + the data dicts.
- `web/app.py` / `appserver/appserver/appserver.py` - the two Flask tiers.
- Memory store (`/root/.claude/projects/-home-flask/memory/`) - per-topic notes;
  this doc supersedes their collective content. See §13 for cleanup.

---

## 13. Known gaps / open items (verified 2026-05-22)

1. **Legacy Stripe price PIN MAP not in code** - hard pre-cutover blocker for
   founding-member billing continuity. Need `{legacy_price_id: tier}` + a
   "don't downgrade on unrecognized price" webhook guard.
2. **Service-account `api_key_hash` not backfilled** on the appserver DB -> 
   `home_opportunities`/`daily_ai_pick` get "invalid api_key". Fix via `web/db_admin.py`.
3. **Stripe Checkout prices** - confirm the 4 EOD prices carry correct launch
   pricing + `product_line=eod` metadata (a $2 placeholder was once found). Needs a
   live Stripe dashboard check.
4. **Script drift to `stage2.trxstat.com`** in `make_staging_secrets.sh`,
   `bootstrap_stage_web_services.sh`, `migrate_scorecard_from_tw1.sh` echo - update
   to `tw2-stage.trxstat.com` before reuse.
5. **`generate_home_page.py` hardcoded URLs** (`CANONICAL_ROOT=tw2.trxstat.com`,
   `APPSERVER_URL=app1pp`) - make env-driven before a prod home regen.
6. **`expire_trials` cron** not installed by `make_bulletproof.sh`.
7. **Central-service URLs** may 403 from staging/prod if set to the public IP
   (use VLAN IPs).
8. **OPEN question:** is TW2's `site/generate_daily_ai_pick.py` (-> `daily-ai-pick.html`)
   an LLM-narrated page, and is it the same pick as the ML-scorer scorecard
   featured pick, or a separate artifact?
9. **TW2 prod boxes** not fully built/verified as of 2026-05-21 (task in progress).

---

## 14. Memory cleanup (from the audit)

The old store `/home/afshin/.claude/projects/-home-afshin/memory/` is a near-duplicate
of the active `/root/.claude/projects/-home-flask/memory/` plus some unique
historical files. This doc supersedes the collective memory content.
- **Superseded (safe to archive):** both `MEMORY.md` bullet indexes (replaced by
  this doc as the canonical map), `project_tw2_two_envs_decision.md` (reversed by
  staging-kept), `project_tw2_environments.md` (outdated topology),
  `project_tw2_milestone1_state.md` + `project_tw2_dev_vm_176.md` (stale snapshots),
  the `*_2026_05_06` build/hardening logs (historical), and the old store's verbatim duplicates.
- **Keep (active rules/context):** the `feedback_*` files, the invariant memories
  (open-paywall, resource-keys, stripe-shared, legacy-billing, cloudflare-tunnels,
  deploy-gotchas, react-deploy, staging-kept, content-sync, domain-split, roles,
  gunicorn-reload), `reference_tw_level_gating`, `reference_tw1_*`, `user_profile`.
- **Going forward:** memories should be short pointers/deltas; this doc carries the
  full picture.
