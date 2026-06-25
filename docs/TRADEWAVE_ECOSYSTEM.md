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
TW1 **prod is 2-tier**: the web box (`10.0.0.40`) holds WordPress/MySQL (the user
list); a SEPARATE prod appserver holds the data engine + its Redis (the per-user
saved data). `.151` dev co-locates everything, so don't model prod off it. Note:
`.151`'s UMP level catalog + WP `siteurl` are STALE - trust `tier_compat.py` and
TW1 staging/prod for real levels, not dev.

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
- **Info / legal pages** (`site/generate_text_pages.py`, authored - run MANUALLY,
  no cron) -> `/var/www/tradewave/{terms,privacy,disclaimer,contact,learn,affiliate}.html`.
  Static, zero backend; nginx serves clean URLs via the catch-all `try_files $uri $uri/ $uri.html`
  (so `/affiliate` serves `affiliate.html`). `affiliate.html` = the invite-only
  affiliate-program explainer (recruiting copy + a mailto apply CTA; program terms
  - commission %, audience discount, payout cadence - are constants at the top of the
  generator). NOTE: `ops/deploy.sh` does NOT emit these pages; after a deploy you must
  run the generator on the box (`sudo -u flask /home/flask/venv/bin/python3
  /home/flask/site/generate_text_pages.py`) for changes to appear.
- **Affiliate program (manual, in-house - NO Rewardful/Tolt yet).** For the
  first ~10 hand-picked partners we run the program on Stripe's own primitives
  instead of paying for a SaaS. Backed by `web/affiliate_service.py` +
  `web/models.py` (`Affiliate`, `AffiliatePayout`) + migration `af1c0de2b3a4` +
  the Flask-Admin **Affiliates** category (`AffiliateAdmin`,
  `AffiliatePayoutAdmin`, `AffiliatePayoutComputeView` in `web/app.py`).
  Model = **1 Stripe coupon + 1 promotion code per affiliate (1:1:1)** so every
  discounted sale traces to exactly one partner by coupon id. Admin "Add
  affiliate" creates the Stripe coupon (`percent_off`, repeating 12mo = "X% off
  first year") + promo code automatically - no Stripe dashboard. Commission is
  computed **downstream** from Stripe (`compute_month`): per paid invoice in a
  month, basis = `amount_paid - tax`, commission = basis x `commission_pct`,
  honoring `commission_model` (recurring [default, lifetime] / first_payment /
  duration_12mo) and a self-referral guard. "Compute / What I owe" previews live
  and commits into the `affiliate_payouts` ledger, **idempotent** on
  `(affiliate_id, period_start, currency)`; operator marks rows paid + adds the
  PayPal/Wise txn id. Optional monthly cron: `web/affiliate_report.py`. This is
  a **pure downstream reader of Stripe** - it touches NO webhook/billing path,
  so it's safe to build/run during stabilization. Clean upgrade path: the codes
  + Stripe history map straight into Rewardful/Tolt later (coupon attribution).
  `code` + `discount_pct` are IMMUTABLE once the coupon exists (Stripe coupons
  can't be edited). On dev, `STRIPE_SECRET_KEY` is a TEST key, so provisioning
  creates disposable test coupons.
- **Standalone promo coupons (Coupons tab)** - plain marketing discount codes
  with NO affiliate / commission / payout. `web/promo_service.py` + `web/models.py`
  (`PromoCoupon`) + migration `b2c0fee1d3a5` + the top-level Flask-Admin **Coupons**
  view (`PromoCouponAdmin`). One Stripe coupon + one promotion code per row,
  created on save. Supports percent-off, fixed-amount-off (needs currency),
  free/100% (`percent_off=100`), and limits (`max_redemptions` + `expires_at` on
  the promotion code). code/discount/limits are IMMUTABLE once created; editing
  only touches name/notes/status, and archiving flips the Stripe promotion code's
  `active` flag. Distinct from affiliate coupons (which add commission tracking on
  top of the same primitives). Pure Stripe writes - no webhook/billing changes.
- **Affiliate referral link + cookie**: `/?code=ANNE` (or `?via=`) on the home page
  (`site/templates/index-dark-blue.html`) (1) stamps the code onto this page's
  checkout forms and (2) stores a first-party `tw_ref` cookie (60-day, first-touch,
  SameSite=Lax) so attribution survives navigation + the WorkOS signup round-trip.
  `web/app.py:stripe_create_checkout` resolves the code from the URL param, the form
  field, OR the `tw_ref` cookie (`_resolve_affiliate_promo`, active affiliates only)
  and PRE-APPLIES the affiliate's promotion code via `discounts=[...]` (falls back to
  manual entry if Stripe rejects it). The Stripe coupon stays the attribution source
  of truth. Disclosed in the Privacy Policy (`PRIVACY_COOKIE_NOTE` in
  `site/generate_text_pages.py`); first-party only, no third-party/ad trackers.
  Logged-out signup->subscribe: `/api/stripe/create-checkout` accepts **GET as well
  as POST** and the pricing CTAs submit as **GET**, so tier/period/code ride in the
  query string. A logged-out visitor who clicks Subscribe is bounced to WorkOS
  sign-up by `require_login` (which preserves `state=full_path`, incl. the query),
  and `auth_callback` replays that URL (GET) after sign-up -> they land on Stripe
  Checkout with the discount applied, instead of the old 405 (POST-only route + GET
  redirect after auth). Creating a Checkout Session is non-destructive, so GET is safe.

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

> **Build tooling (env-driven since 2026-05-22):** the `ops/staging/*.sh` build
> scripts read per-env coordinates from `target.env` (staging) / `prod_target.env`
> (prod) via `ops/staging/run.sh {staging|prod} <script>` - no hardcoded hosts/IPs.
> One quirk remains BY DESIGN: `bootstrap_stage_app_services.sh` writes the SMN
> daemons on the app box, but `migrate_smn_to_web.sh` then relocates them to web -
> so the rebuild ORDER matters (see ops/OPERATIONS.md). Live staging = `tw2-stage.trxstat.com`.

---

## 4. config.py and secrets (the "where settings live" map)

`config.py` is **env-agnostic** - every per-env value comes from
`/etc/tradewave/secrets.env` via `os.environ.get()`. Never hardcode per-env values.

- `TW2_PUBLIC_HOST` -> `tw2_public_url` = `https://<host>/`; `domain_root` is an
  ALIAS of `tw2_public_url` (config.py:117-127). `TW2_DOMAIN_ROOT` is **retired**.
- `TW2_ENV` (explicit) or hostname inference -> `tw2_env` (`dev|staging|prod`),
  config.py:137-145. Drives `seo_enabled = (tw2_env=='prod')` (config.py:304).
- Key dicts: `available_resources`/`_path`/`exchange_mapping` (15 active markets,
  keys `'0'..'13','16'`); `level_access_hierarchy` (backend market filter -
  **level '1' free Explorer = DJ30 only since 2026-06-10; new signups get a
  7-day full-access REVERSE TRIAL first - see §11.1**); `num_*_allowed_by_level`
  ('1' watchlist entries = 0, aligned to TIER_FEATURES); `upgrade_message_by_level`
  (per-level nudge, '1' = post-trial upgrade message); `TIER_FEATURES`
  (explorer/analyst/strategist matrix + pricing);
  `ROLE_BYPASSES_TIER={super_admin,staff_admin,service_account}`.
- secrets.env vars (NAMES only): WorkOS (`WORKOS_CLIENT_ID/API_KEY/COOKIE_PASSWORD/AUTHKIT_DOMAIN`,
  `TW2_AUTH_CALLBACK_URL`), Stripe (`STRIPE_PUBLISHABLE_KEY/SECRET_KEY/WEBHOOK_SECRET`),
  `POSTGRES_DSN`, inter-service (`SERVICE_API_KEY`, `APPSERVER_JWT_SECRET`,
  `API_KEY_HMAC_SECRET` [defaults to APPSERVER_JWT_SECRET]), env identity
  (`TW2_PUBLIC_HOST`, `TW2_ENV`), cross-tier (`TW2_APPSERVER_URL/IP`, `TW2_WEBSERVER_IP`),
  and external APIs (`EOD_TOKEN`, `ANTHROPIC_TOKEN`, `OPENAI_KEY`, `GROK_API_KEY`,
  `PERPLEXITY_API_KEY`, `REPLICATE_API_TOKEN`, `TAVILY_API_KEY`, `MAILERLITE_*`,
  `PUBLER_*`, `FACEBOOK_*`, `INDEXNOW_KEY`, `TW2_GA_MEASUREMENT_ID`, `SENTRY_DSN`,
  contact form (`TURNSTILE_SITE_KEY/SECRET_KEY`, `RESEND_API_KEY`,
  `SUPPORT_EMAIL_TO/FROM`, `SUPPORT_IP_HASH_SALT` - see §5A),
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
  CSRF-exempt, same-origin redirect to `/`), `/api/me`, `/api/contact` (POST,
  CSRF-exempt, anonymous, Turnstile-gated - see §5A), `/app` + `/app/`
  (`app_index`), `/account`, `/pricing`, `/api/stripe/create-checkout`,
  `/stripe/success|cancel`, `/account/manage-subscription`, `/webhooks/stripe`,
  `/webhooks/workos`, `/internal/render_report` + `/internal/delete_report`
  (X-Service-Key), `/admin/*` (super_admin).
- **Auth = WorkOS AuthKit sealed session.** `/auth/callback` exchanges code ->
  seals session into the `tw2_session` cookie (httponly, secure, SameSite=Lax,
  7-day); `lazy_create_user()` upserts the Postgres `users` row (matches by
  `workos_user_id` then email; auto-grants `super_admin` to the owner email).
  `REDIRECT_URI` = `TW2_AUTH_CALLBACK_URL` (read ONCE at process start, app.py:157).
- **LTK** (`generate_ltk()`, web/app.py): HS256 JWT signed with
  `APPSERVER_JWT_SECRET`, `aud="tw2-appserver"`, `iss="tw2-web"`, 8h, carrying
  `user_id, tier, legacy_level, roles, is_admin`. Injected as `window.ltk`; the
  React app exchanges it at the appserver `/login`. The `tier`/`legacy_level`
  claims come from `effective_tier(user)`: an explorer inside their 7-day
  REVERSE TRIAL (`users.reverse_trial_ends_at` in the future) mints Strategist
  claims; `users.tier` itself is never mutated, so trial expiry is implicit at
  the next mint (no cron). Billing/admin paths keep reading `user.tier` raw.
- **`app_index()`** serves `web-react/build/index.html` with injected globals:
  `window.current_user_id`, `current_user_level` (legacy numeric via tier_compat,
  from the EFFECTIVE tier), `ltk`, `tw2_user_email/tier/is_admin/user_roles`
  (`tw2_user_tier` = effective tier), `tw2_env`, and `tw2_trial_ends_at` (ISO
  end of an ACTIVE reverse trial, '' otherwise). `/api/me` likewise returns
  `effective_tier` + `trial_ends_at` (additive) and derives
  `wp_user_levels`/`legacy_wp_level` from the effective tier.
- **Admin:** Flask-Admin gated on `super_admin` role; `UserAdmin` validates
  `roles` against `models.ROLES`. **Roles single source of truth = `models.py:ROLES`**
  = `{super_admin, user, newsroom_author, service_account}`.
- **`report_renderer.py`:** renders a static date-range report (HTML + 3 PNGs) to
  `/var/www/tradewave/r/<slug>/`; invoked by the appserver via
  `/internal/render_report` (semaphore-limited to 4 concurrent).
(Source: `web/app.py`, `web/models.py`, `web/report_renderer.py`, `web/tier_compat.py`.)

---

## 5A. Tier-1 contact form (`/api/contact` + `support_tickets`)

Replaces the legacy mailto-only flow (`site/generate_text_pages.py:build_contact()`).
Static page at `/var/www/tradewave/contact.html` POSTs JSON to `/api/contact`
on the same origin (nginx already proxies `/api/` to the web tier).

- **Page:** `/contact.html` (static, generated by `site/generate_text_pages.py`).
  Renders the form + a Cloudflare Turnstile widget. **The Turnstile site key is
  baked into the HTML at gen time from `config.TURNSTILE_SITE_KEY`** - so the
  generator MUST be re-run on each box whenever `secrets.env` changes (the same
  rule that already applies to every other static-bake page).
- **Endpoint:** `POST /api/contact` (`web/app.py:api_contact`). Anonymous,
  `@csrf.exempt`. JSON body `{name, email, topic, message, company, turnstile_token}`.
  Abuse gates, in order: (1) honeypot field `company` - non-empty silently 200s;
  (2) server-side Turnstile verify against `TURNSTILE_SECRET_KEY`; (3) per-IP_hash
  soft rate limit (5/hr -> marks ticket `status=spam`, skips email).
- **Schema:** `support_tickets` (migration `7a5c3b9d12ef`).
  `id (uuid)`, `ticket_number (BigInt from `support_tickets_number_seq`)`,
  `public_id (text, STORED generated: 'TW-' || YYYY || '-' || lpad(num,5))`,
  `user_id (nullable fk users)`, `email`, `name`, `topic`, `body`,
  `status`, `enrichment (jsonb snapshot: tier/stripe/last_login)`,
  `user_agent`, `ip_hash (sha256(ip + SUPPORT_IP_HASH_SALT) - NEVER raw IP)`,
  `created_at`, `updated_at`, `resolved_at`.
  CHECK constraints mirror `web/models.py:SUPPORT_TICKET_TOPICS` and
  `SUPPORT_TICKET_STATUSES` - these values are **STORAGE IDs** (never rename).
- **Emails (best-effort, via Resend - `web/email_utils.py:resend_send_email`):**
  (a) notification to `SUPPORT_EMAIL_TO` with `Reply-To: <customer>` so hitting
  Reply in the operator's inbox goes straight to the customer. Subject prefix
  `[TW-YYYY-NNNNN]`. Includes the enrichment block.
  (b) confirmation to the visitor with their `public_id`. Kills the
  "did it send?" anxiety the legacy mailto couldn't solve.
  Resend failures log + return success to the visitor (DB row is canonical).
- **Per-env config (secrets.env):** `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`,
  `RESEND_API_KEY`, `SUPPORT_EMAIL_TO` (default `help@tradewave.ai`),
  `SUPPORT_EMAIL_FROM` (default `TradeWave Contact <notifications@trxstat.com>` -
  using trxstat.com for now; swap to tradewave.ai post-cutover with a DKIM
  record), `SUPPORT_IP_HASH_SALT` (per-env; rotating it loses rate-limit
  history by design - no PII drift).
- **Admin:** Flask-Admin "Support Tickets" view (`SupportTicketAdmin`,
  super_admin only). Tier-1 view is read-mostly: only `status` and `resolved_at`
  are editable. The email thread is the source of truth for replies; the DB is
  an audit log. **If/when we promote DB -> source of truth (Tier 2, AI triage),
  this view gains a reply form + Resend inbound webhook for threading.**

(Source: `web/app.py:api_contact`, `web/contact_form.py`, `web/email_utils.py:resend_send_email`,
`web/models.py:SupportTicket`, `migrations/versions/7a5c3b9d12ef_support_tickets_for_contact_form.py`,
`site/generate_text_pages.py:build_contact`.)

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
   via `SERVICE_API_KEY`). Hash secret is `API_KEY_HMAC_SECRET`, falling back to
   `APPSERVER_JWT_SECRET` when unset (web and app must agree on it). The row is
   created/refreshed by `web/db_admin.py ensure-service-account` (run per env on the
   app box; see §13.A); until then this 403s, which is why `home_opportunities` 403'd
   on staging.
- **Data endpoints** (all require `?token=`, `@check_for_token` enforces aud/iss):
  `OppList4`, `OppBySymbol`, `ChartData4`, `YearsMetaData2`, `ChartHistorical2`,
  `StockMetaData`, `getStockPriceByDate`, `consolidated_seasonal_chart2`,
  `StockScoreBatch`, `MLScoreBatch`/`MLScorePending`, etc. Short Redis TTLs (~51s);
  historical price-by-date cached 11.5 days.
- **Gating:** `level_access_hierarchy` by numeric level - level '1' (free
  Explorer) = DJ30 only (`['0']`) since 2026-06-10; reverse-trial users carry
  level-'6' LTK claims so they see everything until the trial lapses. OppList4
  caps results (anon 3, free '1' 5, paid premium up to 5000). ML opp-table
  columns open to all logged-in tiers (c3d66c3); Explorer simply sees them
  DJ30-scoped. The post-trial upgrade nudge is per-level:
  `config.upgrade_message_by_level['1']` rides the `/login` JWT's
  `upgrade_message` claim (other levels fall back to the global
  `upgrade_message`, currently '').
- **Rate limiting is IDENTITY-KEYED (2026-06-12, "this world" redesign):**
  `tw_rate_limit_key()` keys data-endpoint limits on the `?token=` JWT's user id
  (`user:<id>`), EXEMPTS `is_service_account` tokens via a limiter request_filter
  (gateway + generators must never starve), and falls back to the PRE-ProxyFix
  socket peer for anonymous traffic (X-Forwarded-For is caller-controlled on the
  VLAN - never a limiter key). WHY: in TW2's topology every browser arrives via
  the tunnel/nginx proxy as 1-2 shared IPs - the old `get_remote_address` keying
  bucketed the whole userbase together (chronic prod 429s, the "intermittent
  no-data, refresh fixes it" bug; gateway scans rendered throttles as a FALSE
  neutral). Caps in `config.py` `rate_limit_*` (~538) were also un-inverted
  (hourly > per-minute now). 429s log key CLASS + endpoint. `/login` stays
  IP-keyed (anonymous path) and is sized for the whole base sharing one bucket.
  The React app pairs this with `web-react/src/components/twFetch.js` (retry +
  backoff + single-flight 401 re-login + visible retrying states).
(Source: `appserver/appserver/appserver.py`, `web/app.py:616`, `config.py`.)

---

## 7. TW2 React app (`web-react/`, served at `/app/`)

- CRA + react-scripts 5, React 17, `PUBLIC_URL=/app/`. **Build ONLY with
  `npm run build`** (the npm script supplies PUBLIC_URL=/app/; a raw
  `react-scripts build` used to emit root-relative /static/ asset paths and
  blank the app - .env.production now pins PUBLIC_URL as a backstop,
  2026-06-12). Built ONCE on dev, same
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

## 7A. TW2 v2 - Public API gateway + MCP (built on dev 2026-05-27, pre-launch)

The v2 public product (roadmap §9): sell the **derived** patterns (seasonal
opportunities, ML scores, the tracked daily pick) over a clean REST API + an MCP
server for AI agents - **never raw market data**. Built + verified end-to-end on dev
(.176); NOT on staging/prod yet (post-cutover, after the freeze).

**Components (all NEW + additive; the appserver code is UNCHANGED):**
- **Gateway** `apiserver/` (note: dir is `apiserver`, one letter off the `appserver`
  data engine). gunicorn `apiserver.app:app`, dev `127.0.0.1:8088`, systemd
  `tradewave-apiserver`, isolated venv `/home/flask/venv-api`. The public, paid front
  door: authenticates customer API keys, enforces tier/scope/rate-limit, **strips raw
  prices**, exposes ~12 curated `/v1` endpoints, and calls the existing appserver as a
  service account (`/login/api`).
- **MCP server** `mcpserver/` (named to not shadow the `mcp` SDK). FastMCP,
  streamable-http mounted at the ROOT (the BARE host is the canonical published
  connector URL; `/mcp` is kept as an alias), dev `127.0.0.1:9090`, systemd
  `tradewave-mcpserver`. 17 tools (6 flagship + 11 primitives), thin HTTP wrapper
  over the gateway. Auth, two modes: consumer apps (ChatGPT, Claude.ai) connect via
  OAuth - paste the URL, sign in with the TradeWave account (WorkOS AuthKit AS, RFC
  9728 discovery; see `docs/MCP_OAUTH_INTEGRATION.md`); dev tools are BYOK -
  per-connection `Authorization: Bearer <key>`, env `TRADEWAVE_API_KEY` fallback for
  stdio (Claude Desktop). NO baked key for remote.
- **Console** `web/api_portal/` blueprint, mounted in `web/app.py` at `/account/api`
  (keys/usage/billing/MCP-connect). Reuses WorkOS session + Stripe + the `apiserver`
  package. Customer self-serve only.
- **Portal + docs**: static, brand-matched, nginx-served. Sources `site/api_marketing/`
  + `site/api_docs/` (generators read `site/lib/portal_urls.py`).

**Contract:** `api/openapi.yaml` (12 endpoints) + `api/MCP_TOOLS.md` (17 tools - 6
flagship + 11 primitives).

**Data shapes (verified vs the appserver):** opportunities = OppList4/OppBySymbol;
`win_rate` = ChartData4 stat `Percent Profitable` (share of profitable years, no
threshold - matches the UI), enriched per-symbol (cap 50/list) + cached gateway-side
(redis db4, 6h TTL); `min_win_rate` filters on it (NOT `ml.win_prob`). ML = MLScoreBatch
+ MLScorePending (two-phase), Pro-only + markets 0-4,11. `/seasonal-chart` =
consolidated_seasonal_chart2 (365-day high/low-normalized, year-averaged 0-100 curve -
a price-SAFE shape, no price field). Daily pick/track-record = `site/data/featured_history.json`.

**Auth + data (app box):** customer keys in Postgres `api_keys` (HMAC-SHA256 via
`API_KEY_HMAC_SECRET`); usage in `api_usage_daily` + redis db4. Schema
`apiserver/schema.sql` (additive). Tiers/entitlements `apiserver/tiers.py`
(free/dev/pro/business; ML = the Pro line; unified accounts inherit the API tier from
the web tier via `WEB_TIER_TO_API`, optional `users.api_tier` for API-only subs). Stripe
products `product_line=api` (test on dev).

**URLs (env-driven):** `site/lib/portal_urls.py` reads `TW2_PUBLIC_HOST` /
`TW2_API_PUBLIC_HOST` / `TW2_MCP_PUBLIC_HOST` (dev: `api-dev`/`mcp-dev`.trxstat.com; prod
sets them to `api`/`mcp`.tradewave.ai). nginx vhost `sites-enabled/api-dev` (api-dev:
`/api/` portal, `/docs/`, `/v1/` -> gateway; mcp-dev -> :9090) + cloudflared ingress on
the `tw2` tunnel. GOTCHAS: tunnel->nginx is IPv6 so vhosts need `listen [::]:80`; CF
caches dev HTML so the dev portal vhost sets `Cache-Control no-store`.

**Architecture decisions:** the gateway is a SEPARATE process from the appserver
(blast-radius + security - the appserver stays internal/loopback; only the curated
gateway is public). ONE appserver serves both UI + API (Option A); the gateway's
rate-limits bound API load, so a 2nd appserver instance (Option B) is DEFERRED until
traffic competes (a no-code flip via `TW2_APPSERVER_URL`). On staging/prod, place the
gateway+MCP on the app box (gateway->appserver localhost); the public `api-`/`mcp-`
hostnames reach it via the web-box nginx over the VLAN or the app box's tunnel (finalize
at deploy). The gateway is **stateless** (state = Postgres + redis db4 + the appserver, all
over the network), so splitting it onto its OWN box later is a config flip, not a rewrite:
the unit files now read the bind/host from env (`TW2_APISERVER_BIND`, `TW2_MCP_HOST/PORT`;
defaults = loopback, so co-located behavior is unchanged), and everything else
(`TW2_APPSERVER_URL`, `REDIS_HOST`, Tara's `TW2_GATEWAY_URL`) was already per-env. Step-by-step:
`ops/SPLIT_GATEWAY_TO_OWN_BOX.md`.

**OPEN (pre-launch):** the systemd units / nginx vhost / cloudflared ingress are
box-config NOT yet in `ops/` deploy tooling; deploy to staging->prod is post-cutover via
ops/deploy.sh (add the new services to the restart matrix + a migration step + portal/docs
static-gen + the vhosts); `users.api_tier` + a webhook write for API-only subs deferred
(existing-tier users inherit fine); marketing copy is draft.
(Source: `apiserver/`, `mcpserver/`, `web/api_portal/`, `site/lib/portal_urls.py`,
`api/openapi.yaml`; built + verified on dev .176, 2026-05-27.)

---

## 7B. API + MCP services (the productized v2 surface, build-state map)

> §7A is the design/decision narrative; this section is the **operational shape**
> of the same product as built out on dev `.176` (branch `feature/api-mcp`). The
> live control doc is `api/BUILD_STATE.md` (what is done/open per phase); the frozen
> contract is `api/PATTERNCARD_SPEC.md` + `api/openapi.yaml` + `api/MCP_TOOLS.md`.
> **It is DERIVED-DATA-ONLY**: no raw OHLCV, last price, price-by-date, or price levels in
> any public response - all movement is percentages, the seasonal curve is a 0-100
> normalized index, never a price (the keystone invariant; see `api/PATTERNCARD_SPEC.md`).

The product is four NEW, additive pieces; the appserver data engine is UNCHANGED and
stays internal/loopback. All four bind loopback on every env - nginx + the `tw2`
cloudflared tunnel front them.

- **Gateway** - `apiserver/` (one letter off the `appserver` data engine, on purpose).
  gunicorn `apiserver.app:app` on `127.0.0.1:8088`, 4 gthread workers x 12 threads
  (the gateway is appserver-I/O-bound; sync workers capped it at 4 in-flight requests), systemd
  `tradewave-apiserver` (`Type=notify`), isolated venv `/home/flask/venv-api` (NOT
  the appserver `venv`; `requirements-api.txt`). The public paid front door: validates
  customer API keys, enforces tier/scope/rate-limit, **strips raw prices**, exposes the
  curated `/v1` derived-data endpoints (markets, daily-pick, scan, analyze, score, ...), and
  calls the appserver as a service account. Composes the `PatternCard` server-side
  (`apiserver/cards.py`) so weak agents render consistently.
- **MCP server** - `mcpserver/` (named to not shadow the `mcp` SDK). Run as
  `python -m mcpserver.server --transport streamable-http --host 127.0.0.1 --port 9090`
  (the unit reads `TW2_MCP_TRANSPORT`/`TW2_MCP_HOST`/`TW2_MCP_PORT`), systemd
  `tradewave-mcpserver` (`Type=simple`, NOT gunicorn). Mounted at the ROOT so the BARE
  public URL is the canonical connector address (`/mcp` aliased). Thin HTTP wrapper over
  the gateway: it reads `API_BASE_URL=http://127.0.0.1:8088/v1`, plus
  `TW2_MCP_PUBLIC_HOST` (the SDK's DNS-rebinding allowlist). Auth: **OAuth** for consumer
  apps (ChatGPT/Claude.ai sign in with the TradeWave account; WorkOS AuthKit, see
  `docs/MCP_OAUTH_INTEGRATION.md`) and **BYOK** for dev tools - each remote client sends
  its own `Authorization: Bearer <key>`; `TRADEWAVE_API_KEY` MUST be UNSET on the remote
  transport (a baked env key is the stdio/Claude-Desktop fallback only).
- **Customer console** - `web/api_portal/` blueprint mounted in `web/app.py` at
  `/account/api` (GATED behind the WorkOS session): create/revoke keys, see usage, manage
  the API subscription, and the MCP-connect helper. Reuses WorkOS + Stripe + the
  `apiserver` package. `web/api_portal/create_api_products.py` seeds the Stripe products
  (monthly + annual + Founder) under `product_line=api`.
- **Public developer portal** - `developers.*`, a no-login STATIC docroot at
  `/var/www/developers/` served by nginx (marketing landing + reference docs + learn +
  interactive playground + MCP cookbook). It is assembled from the repo by the generators
  (`site/api_marketing/`, `site/api_docs/`, `site/api_learn/`, `site/api_playground/`,
  all reading `site/lib/portal_urls.py`) - see `ops/assemble_developer_portal.sh`.

**Auth + data (app box):** customer keys in Postgres `api_keys` (HMAC-SHA256); daily usage
counters in `api_usage_daily` + redis **db4** (the gateway's own logical DB, distinct from
the appserver's user-data DBs); per-account API entitlement in `users.api_tier` (NULL =
inherit from the web tier via `WEB_TIER_TO_API`; set = an API-only sub). Schema is additive
(`apiserver/schema.sql` / the `api/` migration). Tiers/entitlements in `apiserver/tiers.py`
(free/dev/pro/business; ML fields are Pro-tier + ML-eligible markets only).

**URLs + edge (env-driven):** `site/lib/portal_urls.py` reads `TW2_PUBLIC_HOST`,
`TW2_API_PUBLIC_HOST`, `TW2_MCP_PUBLIC_HOST`, `TW2_DEVELOPERS_PUBLIC_HOST`. Per env the
public hostnames are: dev `api-dev` / `mcp-dev` / `developers-dev`.trxstat.com; staging
`*-stage.trxstat.com`; prod `api.tradewave.ai` / `mcp.tradewave.ai` /
`developers.tradewave.ai`. Each is a `tw2`-tunnel ingress entry (`-> http://localhost:80`)
plus an nginx server block: `api.*` proxies `/v1/` to the gateway `:8088`; `mcp.*` proxies
to the MCP server `:9090` (SSE-tuned: buffering off, long read timeout); `developers.*`
serves the static docroot. Deploy tooling: `ops/bootstrap_api_services.sh` (venv-api +
the two systemd units + nginx + cloudflared ingress) and `ops/assemble_developer_portal.sh`
(run the generators + rsync into `/var/www/developers/`). Operator deploy/restart steps:
`ops/OPERATIONS.md` "API/MCP deploy + restart"; go-live: `ops/PROD_CUTOVER.md` "API/MCP go-live".

(Source: `apiserver/`, `mcpserver/`, `web/api_portal/`, `site/`, `ops/bootstrap_api_services.sh`,
`ops/assemble_developer_portal.sh`, `api/BUILD_STATE.md`, `api/PATTERNCARD_SPEC.md`; dev .176.)

### 7C. Tara (in-product chatbot) -> gateway CLIENT (data flow; Phase 1 built 2026-06-02)

The wave-viewer assistant "Tara" (`appserver/appserver/chatbot.py`, Haiku 4.5) is now a
CLIENT of the v1 gateway: it calls the flagship tools (scan / analyze / symbol-patterns /
daily-pick) via Anthropic tool-use and narrates the gateway's own composed PatternCards, so
its numbers match the API/MCP/daily-pick (one source of truth, derived-data only, same disclaimer).
NOT a product merge - Tara stays the login-gated UI helper; the public API/MCP is unchanged.
Data flow: React `Chatbot.js` -> appserver `/chatbot/chat` (JWT-gated) -> `tara_gateway.py`
tool loop -> gateway `:8088/v1` (loopback) -> appserver engine. Auth/metering (option A):
Tara holds an internal **`chatbot` tier** key (`tiers.INTERNAL_TIERS`, `service:True`, kept OUT
of the sold `API_TIERS`) and passes the web user id as **`X-TW-On-Behalf-Of`**; the gateway
(`auth.py:_apply_on_behalf`) honors that header ONLY for `service:True` keys and swaps ONLY the
metering principal to **`cb:<user_id>`** (regex-validated), so ML/rate/usage meter per web user
on the chatbot's OWN quota, namespaced apart from that human's API ML bucket. Provisioned by
`apiserver/provision_chatbot_key.py` (secrets `TARA_GATEWAY_KEY` + `TW2_GATEWAY_URL`, per-env -
gateway is `:8088` dev, `:80` staging/prod). Falls back to the old no-tools chat when the
gateway is unconfigured. Full spec + the proposed Phase 2 (chat drives the wave-viewer setters):
`docs/TARA_GATEWAY_INTEGRATION.md`.

**Screening answers must match the on-screen opportunity table - Tara screens from OppList4, NOT
/scan (fix 2026-06-21).** The wave-viewer opp table (`OppList4`) and the gateway `/scan` are
DIFFERENT data paths that pick DIFFERENT setups per symbol (verified live: scan top = FAST/TXN/CDNS...;
the real NASDAQ table = AAPL/AMZN/CHTR... with AAPL #1 but ABSENT from /scan at any years/window -
/scan is structurally near-term-only). So a "which <group> stocks" answer built from /scan never
matches the table. Fix: `Chatbot.js` sends `opp_table_market` (+`_market_name`) and `opp_table_years`;
`tara_gateway.run_chat_with_tools` INTERCEPTS the model's `find_best_opportunities` call and answers
from OppList4 - if the table is already on the asked market, from the passed rows (`_rows_to_scan_cards`
+ `_filter_table_rows`); else it fetches that market's OppList4 LOOPBACK (`_opplist4_rows`, via
`config.appserver_url`, as the logged-in user - their LTK carries the level+geo claims OppList4 needs)
AND queues a `set_view {market}` so the table follows the names. Win-rate/winning-years/years/pe_cycle
filters (rows can't satisfy) or a loopback failure fall back to the gateway scan. NOTE: cross-market
loopback uses `opp_table_years` (default 12); a market whose valid lookback differs returns empty ->
/scan fallback.

**Stat-truth: a loaded setup's win rate must match its OWN per-year record (fix 2026-06-21).** Two
compounding bugs let Tara claim "won 10 of 10 years" for an AAPL September window that really lost 6
of 10: (a) the gateway card's `stats.historical_win_rate` was sourced from the appserver's aggregate
Percent Profitable, which DISAGREED with the per-year rows (returned 0.6 = the loss fraction for a
4/10 setup) - now derived from the per-year counts in `cards.py` (= wins/(wins+losses), the same
source as the headline 'Won X/Y' and the bar chart); (b) Tara's deterministic announce-guard
(`tara_gateway._ensure_load_named`) reused a STALE same-symbol card and read the buggy win_rate - now
it matches the card to the loaded setup by `entry_date`, takes the win count from the card HEADLINE
(authoritative), and REPLACES any reply whose win rate contradicts the loaded setup (a prompt rule -
"stats are per-setup, never carried over" - backs it up). GROUND-TRUTH EVAL: `appserver/appserver/
tara_truth_eval.py` runs Tara (single + multi-turn) and asserts every stated win-rate/avg/rank equals
the real per-year data (the gateway card / OppList4 table) - deterministic, with a self-test proving
it flags the original fabrication. This catches the class the old LLM-rubric, single-turn eval missed.

(Source: `appserver/appserver/{chatbot,tara_gateway,AI_tools_appserver}.py`, `web-react/src/components/Chatbot.js`,
`apiserver/{auth,tiers,provision_chatbot_key}.py`, `config.py`, `docs/TARA_GATEWAY_INTEGRATION.md`; dev .176.)

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
- **Legacy billing (handled by design, NOT a blocker):** TW1's UMP created one
  Stripe price per subscriber (~14+ no-metadata legacy prices, e.g. strategist
  $189/yr). TW2's active+metadata price cache can't map them - but it does not need
  to: the webhook PRESERVES tier on an unmappable price (`new_tier=None` -> tier
  unchanged, app.py:1409-1427), so founding members are never downgraded; they are
  seeded at cutover (PROD_CUTOVER pre-seed). **FREEZE: never archive a price with an
  active subscription.** An explicit `{legacy_price_id: tier}` map is optional
  belt-and-suspenders, not a blocker. (Keep a regression test so the preserve-on-
  unmappable behavior can't regress into a downgrade.) NOTE (2026-05-25): preserve is
  no longer SILENT - an unmappable price on a LIVE sub now logs `log.error` + an
  `unmappable_price` audit row (still ACKs 200), so a plan change between two legacy
  prices can't leave a stuck-high tier unnoticed. Caught by a 5-agent billing audit.
- **Tiers:** explorer/navigator/analyst/strategist (TIER_FEATURES). tier_compat:
  explorer->'1', navigator->'2', analyst->'4'/'5', strategist->'6'/'7'. Navigator
  ($19/mo, $168/yr; added 2026-06-25) = entry paid tier, Dow+NASDAQ+S&P (ids 0,1,2,
  date-unlocked; the rest date-locked teasers), legacy level '2'. users.tier CHECK +
  the legacy_wp_level sync trigger were widened for it in migration a1f4d2c9e7b3.
- **Mailerlite level-group sync (TW1/UMP parity, added 2026-05-25):** every account is
  kept in EXACTLY the Mailerlite group matching its (tier, billing-period):
  `explorer` / `analyst_monthly` / `analyst_yearly` / `strategist_monthly` / `strategist_yearly`
  (IDs in `config.MAILERLITE_LEVEL_GROUPS`). `email_utils.sync_mailerlite_level_group()`
  adds to the target group + removes from the other 4; it is wired into every tier-change
  point: signup (`lazy_create_user` -> explorer, new_user fast path), `/stripe/success`,
  the Stripe webhook (`subscription.created/updated` -> tier+period, fires on EVERY mappable
  event so a same-tier monthly<->yearly switch still moves groups; `deleted` -> explorer),
  `expire_trials.py` (-> explorer), and Flask-Admin `UserAdmin.after_model_change`. Best-effort
  (never blocks signup/billing). Period isn't stored in Postgres -> the webhook/success have it
  in scope; the reconcile derives it from the live Stripe price; a manual paid grant with no
  derivable period is SKIPPED + logged for manual placement. Rules: only the 5 LEVEL groups are
  ever touched (SMN/newsletter/webinar untouched); unsubscribed subscribers are never ADDED
  (only removed from wrong groups - can't reactivate). One-time/idempotent reconcile:
  `ops/migrate/reconcile_mailerlite.py` (dry-run default, `--apply`).
  IMPORTANT: every subscriber CREATE sends `status:"active"` so it's a direct/single-opt-in add
  (TW1 SaaS-signup parity) and does NOT fire MailerLite's double-opt-in "confirm your subscription"
  email. Omitting status lets the account default (double-opt-in is ON) email the user - which is
  reserved for the SMN newsletter FORM, not app/SaaS adds.
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
| Tiers | UMP levels 1/4-5/6-7 | explorer/navigator/analyst/strategist (tier_compat -> levels 1/2/4-5/6-7) |
| Data | `/home/flask/data/csv/` | `/home/flask/data/csv/` (same) |
| User identity (= redis key) | WP integer user id (`wp_users.ID`) | Postgres uuid (`users.id`) - CHANGES at migration; users + saved redis data (`user_portfolios_*` / `user_reports_*` / `user_watchlists_*`) moved by an email-joined key-remap. Tooling: `ops/migrate/` (export users via the UMP api-gate + db2; import to Postgres; remap+load redis). |

---

## 11. Invariants / landmines (do NOT break)

1. **Reverse-trial freemium gate (decided by owner 2026-06-10, supersedes the
   2026-05-18 open-paywall launch decision):** new free signups get the FULL
   Strategist experience for 7 days (`users.reverse_trial_ends_at`, set in
   `lazy_create_user`; existing explorers via `ops/grant_reverse_trial.py`),
   then fall back to a genuinely limited Explorer -
   `level_access_hierarchy['1']` = DJ30 only (`['0']`). NO tier mutation: the
   elevation happens at token-mint time (`web/app.py effective_tier`), so
   expiry is implicit and needs NO cron (`expire_trials.py` is the separate
   admin-granted-trial sweep and never touches reverse trials). The paired
   React default-security fallback (App.js falls back to the first accessible
   security) is what makes a DJ30-only list safe - do not remove it.
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
16. **Gateway `service:True` delegation is INTERNAL-only** - the `X-TW-On-Behalf-Of`
    metering-principal swap (`auth.py`) is honored ONLY for `service:True` tiers, which
    live ONLY in `tiers.INTERNAL_TIERS` (never `API_TIERS`; a module assert enforces it).
    A sold tier with `service:True` would let a paying key impersonate any user's metering.
    Delegation swaps the metering id ONLY (`cb:<uid>`), never entitlements (no scope escalation).

---

## 12. Where the deep detail lives

- `ops/OPERATIONS.md` - the operational runbook (deploy, restart matrix, box
  rebuild, gotchas, URL-rename procedure). Single source of truth for deploy.
- `ops/PROD_CUTOVER.md` - the cutover plan + `ops/cutover_repoint.sh`.
- `config.py` - all config + the data dicts.
- `api/SEASONAL_VARIABLES.md` - **canonical reference for the seasonal analysis knobs**: pattern
  DETECTION vs symbol ANALYSIS, the `years`/`min_winning_years` per-market WIN-RATE BAND (why
  "20-9" is impossible; floors are market-specific - S&P ~85%, Wilshire ~90%, FOREX ~70% at 20y),
  the two grids (scan = 15 markets, per-symbol = ids 0/1/2/7/9 only), min_days/max_days, pe_cycle,
  the three win rates, MFE/MAE, the Trend Chart. Enforced in `apiserver/market_bands.py` (manifest
  `apiserver/market_bands.json`, regenerated by `ops/generate_market_bands.py` on each data rebuild).
- `web/app.py` / `appserver/appserver/appserver.py` - the two Flask tiers.
- Memory store (`/root/.claude/projects/-home-flask/memory/`) - per-topic notes;
  this doc supersedes their collective content. See §13 for cleanup.

---

## 13. Gaps / open items (RE-VERIFIED against code 2026-05-22)

Several items first flagged here were inherited fears from older memories; a code
re-verification reclassified them. Only treat the REAL list as work.

**REAL (code/config-verified):**
- **A. Service-account api_key not backfilled** -> `site/home_opportunities.py`
  (uses `SERVICE_API_KEY` -> `/login/api`) gets `invalid api_key` (no
  `users.api_key_hash` row matches). RESOLVED 2026-05-22: added an idempotent
  `web/db_admin.py ensure-service-account` subcommand that upserts the
  `service-account-internal@tradewave.ai` user (roles `["service_account"]`, tier
  `strategist`, `legacy_wp_level=6`, `email_verified`, no `workos_user_id`) with
  `api_key_hash = HMAC-SHA256(SERVICE_API_KEY, API_KEY_HMAC_SECRET or APPSERVER_JWT_SECRET)`
  computed from the box's own secrets. Validated end-to-end on dev (login_api -> 200).
  RUN per env ON THE APP BOX (where the appserver + its Postgres live, so the secret
  matches): `sudo -u flask /home/flask/venv/bin/python /home/flask/web/db_admin.py
  ensure-service-account`. Pending: run on stage-app, then prod-app at build.
  NOTE: `site/generate_daily_ai_pick.py` is a SEPARATE issue - it uses the legacy
  keyprovider login (not `login_api`), and has NO LLM and does not touch
  `featured_history` (it's a standalone appserver-driven page, distinct from the
  ML-scorer scorecard featured pick).
- **B. Build-script hostname drift** - RESOLVED 2026-05-22. All 27 `ops/staging/*.sh`
  build scripts are env-driven: coordinates come from `target.env` (staging) /
  `prod_target.env` (prod) via the unified runner `ops/staging/run.sh {staging|prod}
  <script>` (payloads get the env file prepended; orchestrators source it; quoted
  config heredocs use a placeholder + sed). Verified: bash -n + shellcheck + a
  zero-bare-coordinate grep across all scripts, plus per-env value simulations. The
  old `run_prod.sh` sed-rewrite is gone (thin forwarder to `run.sh prod`).
- **C. `expire_trials` cron** - RESOLVED 2026-05-22. `make_bulletproof.sh` now
  installs the web-box daily cron (`15 4 * * *`, the schedule `web/expire_trials.py`
  documents) so admin-granted trials auto-revert to explorer. Apply to a live box by
  re-running `ops/staging/run.sh {staging|prod} make_bulletproof.sh` (idempotent).
- **D. Central-server leftover** - RESOLVED 2026-05-23. `TW2_CENTRAL_SERVER_URL` was a
  stray env var for the never-implemented "central data server" feature
  (`central_server_url`/`central_data_consumer`/`central_config_consumer`; consumers
  removed from config.py + appserver 2026-05-21). Removed from `make_staging_secrets.sh`
  + dev secrets + the deploy doc. **The other data-tier services are REAL and stay:**
  `ml_scorer` (FUNDAMENTAL - the daily-pick/scorecard engine; writes 4 opportunity-table
  columns ml_score/win_prob/pred_return/pred_mfe), `stockscore`, `edgar`, `realtime`,
  `update`, `logcollector`. They default to '' in config.py (= feature off, guarded) and
  are reached at their configured URLs. Do NOT confuse these with the removed feature.

**NON-ISSUES (re-verified - code already handles; were inherited fears):**
- **Legacy Stripe "PIN-map"** - NOT a blocker. The webhook PRESERVES tier on an
  unmappable (legacy, no-metadata) price (`new_tier=None` -> tier unchanged,
  app.py:1409-1427); it never downgrades founding members. They are seeded at
  cutover (PROD_CUTOVER pre-seed); FREEZE-price-cleanup still applies. Residual:
  keep a regression test so a future change can't turn this into a downgrade.
- **`generate_home_page.py` URLs** - NOT hardcoded: `CANONICAL_ROOT = config.domain_root`
  (env-driven; only a cosmetic `tw2.trxstat.com` fallback if TW2_PUBLIC_HOST is
  unset) and `APPSERVER_URL = config.appserver_url` (env-driven). The stale claim
  was from a 2026-05-14 inventory / TW1's copy.
- **Daily-AI-pick LLM** - resolved: no LLM anywhere in the pick (see A above).

**VERIFY / STATUS (not code bugs):**
- Stripe Checkout prices: confirm the 4 EOD prices carry correct launch pricing +
  `product_line=eod` metadata (live Stripe dashboard check).
- TW2 prod: already deployed + ~95% verified at the placeholder `tw2-prod.trxstat.com`
  (Afshin, 2026-05-22). Remaining ~5% overlaps gaps C/D + the prod-app service-account.
  The `tradewave.ai` flip is the separate cutover session.

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
