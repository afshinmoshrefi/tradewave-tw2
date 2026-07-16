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
  Grok (`grok-3-mini`) for news extraction + research synthesis (Tavily search
  restricted to `WHITELISTED_SOURCE_DOMAINS`, `smn/article_prompt.py`), OpenAI
  `gpt-5.1` for article writing AND SEO titles (`smn/article_title.py` calls
  `send_openai_prompt` - the earlier "Claude for titles" note was stale, corrected
  2026-07-02), hero images via Replicate (SDXL standard / SD 3.5 Large premium
  router, `smn/article_hero_image.py`). Volume knob:
  `smn/daily_article_queue.py:ARTICLES_PER_DAY` (repo/dev = 2; per-box value may
  differ - read it off the box, don't recall). Publishes PUBLIC static HTML (NO
  gating anywhere, verified 2026-07-02) to `/var/www/smn/articles/` + `posts.json`
  index + sitemap.xml / sitemap-news.xml / rss.xml / `llms.txt` / IndexNow; every
  article embeds the MailerLite signup form (groups SMN-DAILY / SMN-WEEKLY) and the
  required `transition_to_tradewave` bridge paragraph (rule: no TradeWave mention in
  body before that bridge). Emails: `smn/send_smn_emails.py` - Mon-Fri 07:00 UTC
  daily blast + Sun 09:00 UTC weekly recap. SMN monetization strategy + external
  research (2026-07-02, owner decision pending): `docs/marketing/SMN_STRATEGY.md`.
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
  creates disposable test coupons. BUILT OUT SINCE (verified in code 2026-07-07):
  durable per-subscription attribution (`AffiliateReferral`, written from webhook
  metadata `tw2_affiliate_id`; compute attributes referral-first, coupon fallback);
  co-branded public `/join/<code>` landing (`page_display_name/logo/photo/note/
  signoff` on `Affiliate`); magic-link e-signature flow (`web/affiliate_agreement.py`,
  `/affiliate/sign/<token>`, immutable snapshot + audit fields, affiliates are
  created PAUSED and flip active only on signing); monthly/annual interval-split
  coupons; anonymized monthly statement emails (`web/affiliate_report.py`, cron 2nd
  03:30). Affiliates are NOT users yet (no `users` linkage; magic links only). The
  affiliate-facing login dashboard + optional SMN expert module:
  `docs/AFFILIATE_DASHBOARD_SPEC.md` - BUILT + tested on dev 2026-07-07 (32/32
  integration checks, `tests/test_affiliate_portal_dev.py`). Pieces: blueprint
  `web/affiliate_portal/` at `/account/affiliate` (auto-links by email on first
  visit -> `affiliates.user_id`, migration e7a1b2c9d4f5; access = linkage, NO new
  role); live current-month estimate via `affiliate_service.compute_for_affiliate`
  (cached ~1h, labeled estimate); self-serve join-page fields + headshot upload
  (PIL -> 512px webp into `/assets/affiliate-logos/`, operator notified);
  SMN expert module (operator invites via Flask-Admin "SMN Experts" ->
  `affiliate_smn_profiles` f8c2d3e0a5b6; affiliate click-accepts
  `docs/SMN_CONTRIBUTOR_TERMS.md` -> active; takes in `expert_takes`
  a9d3e4f1b6c7 via `web/expert_takes_service.py`, review queue "Expert Takes"
  admin, approve==publish); SMN box PULLS `/internal/expert_takes` +
  `/internal/expert_profiles` (X-Service-Key) via `smn/expert_sync.py`
  (injects/removes TW-EXPERT-DESK sections in article HTML, heals wiped
  sections after article regeneration, builds `/experts/<slug>.html` hubs;
  web-tier base from `TW2_WEB_INTERNAL_URL`, default loopback :5500).
  OPEN: expert_sync cron not yet in make_bulletproof.sh; staging/prod rollout
  via ops/deploy.sh + migration step; scorecard evaluation job (Phase C2) not built.
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
  **GOTCHA (hit 2026-07-09, W1.1 founding-offer campaign):** a standalone promo
  code (e.g. a marketing coupon like `FOUNDING20`) is NEVER surfaced via the
  `?code=`/`?via=` URL param or the `tw_ref` cookie - those two carriers are the
  AFFILIATE rail only (`_resolve_affiliate_promo`, resolves against the
  `Affiliate` table). Passing a non-affiliate code through `?code=` does not
  error; it just resolves to nothing and is silently ignored (checkout falls
  through to `allow_promotion_codes=True` regardless - see below). A standalone
  promo code is entered by the USER, by hand, into Stripe's own promotion-code
  field at Checkout - which only appears when `allow_promotion_codes=True` is
  set (i.e. whenever no affiliate discount pre-applied for that visitor). So any
  copy/email/link advertising a standalone promo code must send the visitor to
  a bare pricing/checkout URL (no `?code=` param) and instruct them to type the
  code in at checkout - never construct a link implying the code auto-applies.
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
  **Card-collection gotcha:** paid-tier Checkout Sessions set
  `subscription_data.trial_period_days=7` with Stripe's DEFAULT payment-method
  collection, so a CARD IS REQUIRED up front for the paid 7-day trial. This is a
  SECOND, distinct "7 days free" from the no-card reverse trial minted at signup
  (§11.1). Homepage/pricing copy saying "no card" is true ONLY of the signup path;
  do not describe the paid checkout trial as card-free.

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
  config.py:137-145. NOTE: `seo_enabled = (tw2_env=='prod')` (config.py:377) is a
  **DEAD flag** - read nowhere (verified 2026-07-04). The real per-env SEO gate is
  the `ENABLE_SEO = os.environ.get('TW2_ENV','').strip().lower()=='prod'` pattern,
  copied verbatim into every SEO-bearing generator: `site/generate_home_page.py:187`
  (home), `site/generate_scorecard.py`, `site/generate_about_page.py`,
  `site/generate_daily_ai_pick.py` (2026-07-04 fix - see §13.E, now DONE on dev).
  `robots.txt`/`sitemap.xml`/`llms.txt` are generated by `site/generate_seo_files.py`
  (last step in `ops/regen_site.sh`), not hand-maintained.
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
  `PUBLER_*`, `FACEBOOK_*`, `INDEXNOW_KEY`, `TW2_GA_MEASUREMENT_ID`, `GA4_MP_API_SECRET`
  (server-side Measurement Protocol - see §9), `SENTRY_DSN`,
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

- **Routes** (also: `/account/affiliate/*` partner dashboard blueprint +
  `/internal/expert_takes|expert_profiles` service-key pull feeds, 2026-07-07):
  `/healthz`, `/signup`, `/login`, `/auth/callback`, `/logout` (POST,
  CSRF-exempt, same-origin redirect to `/`), `/api/me`, `/api/contact` (POST,
  CSRF-exempt, anonymous, Turnstile-gated - see §5A), `/app` + `/app/`
  (`app_index`), `/account`, `/pricing`, `/api/stripe/create-checkout`,
  `/stripe/success|cancel`, `/account/manage-subscription`, `/webhooks/stripe`,
  `/webhooks/workos`, `/internal/render_report` + `/internal/delete_report`
  (X-Service-Key), `/admin/*` (super_admin).
- **There is NO logged-out / demo mode of the wave viewer:** `/app/` for an
  unauthenticated visitor redirects straight to WorkOS sign-up
  (`screen_hint="sign-up"`, return-to preserved incl. `?o=` pattern params).
  Marketing copy must not promise a no-login "live demo" at `/app/`.
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
- **Opp-table years/partial resolution chain (React `OppTable.js`, hardened 2026-07-03):**
  `YearsMetaData2` returns the valid `[years, partial]` dataset pairs (cons + PE); the opp
  table can only fetch `OppList4` for a pair that exists. The resolution chain: metadata
  effect fetches pairs -> main effect validates YEARS against the active metadata (dead
  years value = snap to nearest valid, tier-cap aware) -> resolves partial `-1`/invalid to
  the highest valid option -> fetch gate opens. INVARIANTS (each guards a real stuck-state
  bug): (a) NEVER call `YearsMetaData2` with the `-1` sentinel id - the server returns the
  empty-metadata sentinel and, raced against the real market's response with no ordering
  guard, it clobbered the metadata and spuriously auto-off'd PE mode (client now guards
  id=-1 + orders responses via `metaReqRef`); (b) the auto-step-down must step to the next
  LOWER VALID partial option, never a blind `-1` decrement (an invalid pair ping-pongs
  against the invalid-value reset while the OppList URL dedupe blocks refetching);
  (c) `initialMessage='Loading ...'` is set when an OppList4 fetch launches - it gates the
  step-down so a stale "no patterns" message can't trigger it mid-fetch. KNOWN mismatch
  (unfixed root, symptom neutralized by the years snap): the opp-years cookie slot is keyed
  on the WAVE-VIEWER's `PEselected`, not the opp table's own `showPEOpps` toggle, so a
  PE-slot years value can be restored into cons mode (`App.js getOppYearsForGroup` callers).
- **Wave-viewer years selector overflow clamp (`SeasonalBarChart.js` ~283-297, fixed
  2026-07-09):** the years `<select>` is CONTROLLED; if `seasonalYears` exceeds every
  option (e.g. cons 95yr then switch regime to PE+2 whose list is 3..24), the browser
  silently displays the FIRST option ("3") while state stays "95" and the chart renders
  the appserver-clamped full set - selector and chart disagree. INVARIANT: on metadata
  resolve, snap the value DOWN to the max SELECTABLE (unlocked, tier-cap-aware) option on
  TRUE OVERFLOW ONLY - never touch an in-range value (the pre-2026 snap-to-max clobbered
  user selections on every symbol switch under PE; the comment block at the clamp explains
  both sides). Same step-down-clamp family as the OppTable dead-years snap above.
- **Gating / tier ENFORCEMENT (server-side; the appserver is THE boundary - React/
  dropdown gating is UX only and curl-bypassable). All clamps re-derive from config and
  bypass admin/service tokens. (Made real in the 2026-06-30 enforcement audit; before that
  most of this was defined-but-unenforced.):**
  - MARKETS - `level_access_hierarchy[level]`: Explorer '1'=`['0']` (DJ30); Navigator '2'=
    `['0','1','2']`; Analyst '4'/'5'=`['0','1','2','3','4','11']` (US stocks+ETFs); Strategist
    '6'/'7'=all 15; reverse-trial Explorers carry level-'6' claims. CLAMPED on OppList4,
    getChartData4, OppBySymbol, GetListSymbols + dr_report_publish -> out-of-scope market = 403.
  - AI/ML = LADDER A: `ml_score_access_levels=['4','5','6','7']` x `ml_score_resource_ids=
    ['0','1','2','3','4','11']` -> AI scoring STARTS at ANALYST. Explorer + Navigator get NO
    score (deterministic patterns only); reverse-trial (level 6) + Analyst+ get it. (Supersedes
    the old "ML columns open to all logged-in tiers" claim - NOT current.) The React opp table
    shows non-AI tiers one locked "AI Score" teaser column.
    **KNOWN GAP (2026-07-07 mobile-parity audit, unfixed):** on phone-portrait ONLY, this
    gate is bypassed by a DEVICE check, not entitlement - `OppTable.js`'s ML-score fetch
    effect OR's `isMobilePortrait` into its skip condition (`OppTable.js:717,729`) alongside
    the real `!mlEnabled` check, so the fetch never runs for ANY tier on that one layout.
    `TableBox.js`'s phone-portrait column allowlist (`MOBILE_COLS`, :93-97) independently
    excludes `ml_score` too, so even the locked teaser column above is ALSO absent there -
    silently, with no lock icon/hint. Rotating to landscape restores it (fresh mount, see
    §7.2). Full audit (27 findings): memory `project_mobile_parity_audit_2026_07`.
  - DATE-LOCK: a market in `level_access_hierarchy_free_registered[level]` is start-date-locked
    to today (getChartData4 forces date=today); `_premium[level]` markets are date-unlocked. After
    the market clamp the only date-locked combo is Explorer's DJ30 ("any start date" = the paid lever).
  - YEARS cap: `num_years_allowed_by_level` (Explorer 10 / Navigator 15; Analyst/Strategist
    uncapped) clamps the lookback - year1 (OppList4/OppBySymbol) + yrs (getChartData4) - so the
    opp table and the wave-viewer can never disagree. React grays over-cap years -> upgrade dialog.
  - QUOTAS (enforced): `num_portfolios_allowed_by_level` (add_user_portfolio_name);
    `num_opp_reports_allowed_by_level` lifetime + `num_daily_opp_reports_allowed_by_level`
    (dr_report_publish); `num_watchlists/_items_allowed_by_level`. `num_opps_per_portfolio` is
    intentionally NOT enforced (the lifetime tracked-opps cap governs).
  - RESULT caps: OppList4 returns anon 3 / free-or-date-locked 5 / premium up to 5000.
  - The CONSUMER MCP path MIRRORS the WEB sub (not the API ladder) - see §7A.
  - Post-trial upgrade nudge is per-level: `config.upgrade_message_by_level['1']` rides the
    `/login` JWT `upgrade_message` claim (other levels fall back to the global, currently '').
  (Full session detail + the probes that proved each clamp: memory `project_tier_enforcement_audit`.)
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

### 7.1 Price chart + seasonal projections (`StockLineChart` -> `LineChart`)
The price chart is a two-layer component: `StockLineChart.js` fetches
`/appserver/ChartHistorical2/<res>/<sym>/<d0>/<d1>` (adjusted OHLCV, ISO dates)
with SMA-seed padding, weekly aggregation, and localStorage-persisted user
price levels; `LineChart.js` renders via react-chartjs-2 with candlestick /
OHLC / line switch, MA + Bollinger overlays, earnings markers, trade box +
diagonal, and the seasonal-projection overlay.

**Seasonal projection lines (LineChart.js:516+).** Up to TWO dashed lines
forward-projected from the last close, using consolidated-seasonal cycles
already fetched for the same symbol:
- Primary (amber `#e8a838`, pill "Proj", tooltip "Toggle Seasonal Projection"):
  uses the user-selected `sy` cycle in `consolidatedSeasonalData`. Deliberately
  unadorned - the year window lives in the seasonal-years selector, not the
  toggle label.
- Secondary (indigo `#7c5cff`, pill "Proj {N}-Y"): uses a full-history cycle in
  `maxYearsConsolidatedSeasonalData`, where
  `N = min(StockMetaData y2 - y1, maxYearsCap() || Infinity)` - i.e. the
  ticker's raw history capped by the tier's years entitlement (Explorer 10 /
  Navigator 15 / Analyst+ uncapped, per `Common.js:maxYearsCap`).

**Both cycles come from `/consolidated_seasonal_chart2`** and are fetched
NOT in the chart itself but in `SeasonalBarChart.js` (:522 primary, :~580
secondary), which owns the trend-chart data pipeline and lifts both cycles +
`maxAvailableYears` to `App.js` state via setters. The chart is a pure consumer.
Cycle math: walks by index (not MM-DD) with cumulative `cycleDrift` carried
across each wrap, so trending stocks project continuously across the 365-day
boundary. Same period selector (14/30/60/90d) and daily/weekly timeframe drive
both lines.

**Toggles + hiding.**  `showProjection` and `showMaxProjection` persist via
`Common.js:lsGet/lsSet` (localStorage keys `showProjection` /
`showMaxProjection`); both default TRUE. The secondary pill and the secondary
line are HIDDEN when `parseInt(seasonalYears) === maxAvailableYears` (both
lines would be identical) or when the max-years cycle hasn't loaded. Chicken-
and-egg quirk: the secondary FETCH is skipped while `showMaxProjection` is
false (`SeasonalBarChart.js` max-fetch effect returns early), and the "Proj
N-Y" pill requires a non-empty `maxYearsConsolidatedSeasonalData` - so from a
cold start with the toggle saved OFF, the pill never renders and the ONLY
first-enable path is the DesktopLayout settings checkbox (once on, data loads
and the pill appears; toggling off does not clear the data, so the pill then
persists for the session). Pills are
desktop-only (`!rdd.isMobile`); the DesktopLayout settings panel exposes
matching checkboxes with the same "N-Y" suffix. Cookies were deliberately
rejected for these toggles - the codebase standardizes on `lsGet/lsSet` for
all chart-view preferences.

**PE cycle mode hides the projection BY DESIGN (data side-effect, not an explicit
gate).** Selecting a PE phase in the Mode selectbox other than the current year's
phase bumps `startDate` to the NEXT calendar year matching that phase - a future
year - via `bumpStartDateYearToPE` (`SeasonalBarChart.js:1029`, anchored to
`getTodayDate()`; e.g. PE+3 in 2026 -> 2027), clears `consolidatedSeasonalData`,
and refetches PE-filtered (`pe3-10` style years param). The returned slice no
longer overlaps today, so the `< 5`-points guard (`SeasonalBarChart.js:~599`)
keeps `consolidatedSeasonalData` empty -> the "Proj" pill is not rendered
(`StockLineChart.js:~847` requires a non-empty cycle) and the projection dataset
is not built (`LineChart.js:~682`, `projCount` stays 0). The current year's OWN
phase (PE+2 in 2026) does NOT bump the date, so the projection still draws there.
Rationale: a forward projection must anchor at the last close on the current
price chart; a future-year window has no current price to anchor to. Tara's KB +
prompt document this (see 7C).

**FIXED 2026-07-05: projections used to vanish once the loaded pattern's trade
BEGAN.** Diagnosis (browser-repro'd via `?o=` deep link): (1) `ChartData4`
(appserver.py:2097-2114, :2162) marks the trade active as soon as
`entry_date < last close in the CSV` and then computes a REAL in-progress pct for
the current-year bar (`d1 = last close`); the `'0,0,0'` placeholder row
(appserver.py:2231) exists ONLY while the trade hasn't started in data terms.
(2) `StockLineChart.js` sets `showCurrentLineChart=true` ONLY when the LAST bar
has `pct === '0,0,0'` and its year is the viewed year - otherwise the price chart
mounts the TRADE view (which for an active trade ends at the same last close, so
it LOOKED like the current chart minus the projections). (3) Every projection
element required `showCurrentLineChart`, and the "Current" button only resets
`lineChartYear`, so once one close landed after the entry date the projections
were unreachable for the pattern's whole life (weekends/holidays/EOD-lag made it
look like "works for a few days" after entry). THE FIX (option A):
`StockLineChart.js` computes `projectionCapable = showCurrentLineChart ||
(tradeActive && lastSeasonalBar.year === lineChartYear)`, gates both Proj pills
on it, and passes it to `LineChart`, whose `buildSeasonalProjection` entry gate
now keys on it (weekly point-spacing stays keyed on `showCurrentLineChart`
because weekly aggregation only applies to the current chart). Historical year
views and COMPLETED trades stay projection-free by design (their last point is
in the past - no anchor). D/W, E, and chart-range buttons remain
current-chart-only. Verified per-scenario in a real browser: fresh entry
unchanged, 20-days-in active trade now shows both pills + both dashed lines on
the trade view, completed trade shows none. Tara's KB WHY-paragraph +
`chatbot.py` missing-projection rule now cover the past-year-view and
completed-trade cases.

(Source: `web-react/src/components/{App.js, SeasonalBarChart.js, DesktopLayout.js,
StockLineChart.js, LineChart.js}`, `Common.js:maxYearsCap|lsGet|lsSet`,
appserver.py:2594 `getHistory2` / :2839 `consolidated_seasonal_chart2` / :2644
`StockMetaData`.)

### 7.2 Mobile layout routing (`MobileLayoutP`/`MobileLayoutL` vs `DesktopLayout`)
Device+orientation picks one of three layout components at `App.js:2907-2938` (`rdd` =
react-device-detect): `!rdd.isMobile` -> `DesktopLayout`; `rdd.isTablet && browserH<browserW`
(tablet-landscape) -> **also `DesktopLayout`** (the literal desktop tree - it branches on
device exactly once, `DesktopLayout.js:177`, a container-height swap only, nothing else -
so tablet-landscape collaterally hits every child component's own `!rdd.isMobile` gates
too, e.g. all of StockLineChart's chart-chrome gates below); `!rdd.isTablet &&
browserH<browserW` (phone-landscape) -> `MobileLayoutL`; `browserH>browserW` (phone-portrait
+ tablet-portrait) -> `MobileLayoutP`. Rotating the device unmounts/remounts a different
component at the same tree position (not a resize of one component), so device-scoped
`useEffect`s re-run fresh on rotation.

**Portrait vs landscape are NOT equivalent mobile experiences.** In `MobileLayoutP`,
`OppTable` is docked permanently below the chart swiper (:203-205, both always visible
together). In `MobileLayoutL`, `OppTable` is just slide 1 of a 6-slide swiper shared with
the charts (:191-193) - reaching the table means swiping away from whatever chart is
open. `InfoPopupHelpMobileP.js`/`InfoPopupHelpMobileL.js` (per-slide mobile coach-mark
overlays) are DEAD CODE in both layouts - imported once each but their only render site is
commented out (`MobileLayoutP.js:142`, `MobileLayoutL.js:163`), no other reference anywhere
in `src`. `<Chatbot/>` (Tara) mounts ONLY in `DesktopLayout.js:1452-1464` - never imported
into either mobile layout - so tablet-landscape gets Tara (routes to DesktopLayout) but
phones in either orientation do not (matches the deferred-by-decision Tara-mobile scope,
memory `enh_tara_mobile`).

Full mobile feature-parity audit (Opp/TableBox/chart/TradeDetail/InfoPopup/onboarding/
conversion/portfolio/trading-dialog components, 27 ranked defects incl. the AI-column gap
above): memory `project_mobile_parity_audit_2026_07`.

### 7.3 "Remind me" bell (one-click Google Calendar reminders; stateful pill)
Shipped 2026-07-04 as "Notify me" (auto-created a dedicated "Notifications" portfolio);
reworked + renamed 2026-07-08 (owner decisions: stateful BUTTON not a toggle switch -
an OFF would need Google-side deletion we can't do honestly; save to the CURRENT
portfolio like the Plus icon, dedicated portfolio dropped; pill must be TRUTHFUL -
"Reminder set" only when Google events were actually created, not merely saved).

- **UI**: `SeasonalBarChart.js` toolbar (state/handler ~1650-1870, render next to the
  Plus icon). Desktop pill (`.tw-notify-btn`, brand purple; `--set` = tinted-outline
  "✓ Reminder set" variant - white text on purple tint, green ✓; owner feedback
  2026-07-08: status must read at a glance, not whisper - `App.css`), icon-only
  under 1120px right-panel width; mobile = outline white bell (unset) vs filled
  GREEN bell (set). CSS classes and the
  `tw_notifybell_seen` localStorage pulse key keep the legacy `notify` prefix (stable
  IDs). Shared Google machinery (GIS loader, event-dict builder, insert, token flow):
  `googleCalendarEvents.js` - one OAuth client for all envs; also used by the AddGC
  dialog so content can't drift.
- **State**: appserver `GET /dr_report_exists/<symbol>/<date>/<days_hold>/<years>`
  (token-authed) - is this exact pattern saved in ANY portfolio (pattern-scoped ON
  PURPOSE; the publish dedup `check_for_duplicates` is portfolio-scoped, so a
  re-publish from another portfolio would duplicate the record AND burn lifetime
  quota) + `gc_events` (were Google events created) + found portfolio name + slug +
  publishDate (lets the client rebuild event dicts without re-publishing). React
  re-checks on pattern-identity change and on `numReportsCreated` (mutated by every
  save/delete path, so it doubles as the portfolio-changed signal) + `addGCVisible`.
- **gc_events stamp**: `POST /dr_report_mark_gc_events/<same identity>` sets
  `gc_events_created` (ISO UTC) on ALL identity-matching `user_reports_{userid}`
  records. Fired fire-and-forget after a successful insert by BOTH clients (bell +
  AddGC dialog). Absent key = never created (all pre-2026-07-08 records). Never
  cleared - Google-side deletions are invisible to us. This is the ONE schema
  addition to the user_reports record.
- **Click flow**: saved+gc_events -> "Reminder Set" details dialog (JSX card
  layout inside InfoPopup's info-box, which renders contentText bare so it takes
  elements; Re-create button + an "Edit reminder settings" LINK that opens the
  SAME AddGC dialog as the Portfolio Manager path, pre-filled, dims = manager's
  formula; a `forceGC` flag on googleCalendarDict makes all 3 layouts route to
  AddGC even when an '&' autotrade portfolio is the current selection);
  saved w/o gc_events (Plus-icon save or abandoned popup) -> straight to
  the Google token flow against the existing record, NO re-save; unsaved -> publish
  to `props.selectedPortfolio` (`'&'` autotrade portfolios and empty fall back to
  'main') then token flow. Popup-blocker: GIS preloaded on mount; at most one API
  call before `requestAccessToken` (fits the ~5s transient-activation window);
  dialog Retry/Re-create buttons are fresh gestures. Async guards: request-counter
  ref on the exists check; pattern-identity `key` guards the post-OAuth state flip
  (popups are slow, user may have switched patterns).
- Button copy referenced by name in `onboardingLessons.js` (Days 6-7) and
  `docs/ONBOARDING_LESSONS_LOCKED.md` - renamed to "Remind me" everywhere 2026-07-08.

### 7.4 UI Screenshot Capture Pipeline (dev-only; built + verified 2026-07-09)

Automated pixel-real screenshots of the wave-viewer (any theme/display/state, incl.
the opp table) with zero human interaction - built to unblock fully automated blog/
page publishing. **Full operating manual = `docs/UI_CAPTURE_PIPELINE.md` (read that,
not this, before touching it).** The pieces and where they live:

- **Auth**: `web/app.py` route `/internal/capture/app` renders the SAME
  `_render_app_shell(u)` as `/app/` (app_index was refactored into that shared
  helper) for the `capture-bot@tradewave.local` user (tier strategist, no real
  WorkOS identity, cannot log in normally). Double-gated: hard 404 unless
  `config.tw2_env == 'dev'`, plus gunicorn binds 127.0.0.1:5500 with no nginx
  location - unreachable off-box even on dev.
- **Readiness**: `web-react/src/components/captureReady.js` + 5 flags across 4
  components (OppTable `oppTable` / SeasonalBarChart `seasonal` + `trendChart` /
  StockLineChart `price` / TradeDetail `tradeDetail`) set `window.__twCapture.ready.*`
  only when non-empty data has rendered; cleared at fetch start. Pure
  instrumentation, ships harmlessly in the bundle. NOTE: `seasonal` and
  `trendChart` are BOTH in `SeasonalBarChart.js` but gate two DIFFERENT fetches -
  `seasonal` = the upper bar chart (`ChartData4`), `trendChart` = the lower
  trend-line chart (`consolidated_seasonal_chart2`, feeds `SeasonalChart.js`
  swiper slide 0). `seasonal` going true does NOT imply `trendChart` is ready;
  `trendChart` was added 2026-07-09 after a cold-load blank trend-chart pane
  passed every other gate (`capture.js` now waits on it too whenever
  `spec.display === "seasonal"`).
- **Harness**: `tools/ui_capture/` (capture.js + capture.sh + specs/). Declarative
  spec v1 (theme / display / market+symbol / pattern -> `?o=` / scale 2|4 /
  chart+table settings / crops) -> PNGs + meta.json provenance. Key mechanics:
  main-document interception (real `http://127.0.0.1/app/` origin, HTML fetched
  from the internal route), storage pre-seeding (localStorage keys are
  USER-SCOPED `<uuid>:<key>` except raw `UITheme`; overlay-suppression set incl.
  LessonBox + the two infinite CSS pulse keys), byte-stable frame gate for
  Chart.js animations, fail-fast sanity checks.
- **Gotchas promoted from the build** (details in the manual's failure table):
  any querystring except `?set=on` forces the lower display to slide 2 at boot;
  `?ask=` opens the Tara panel (never use in captures); `npm run build` can leave
  `build/` files unreadable by nginx (www-data) -> `/app/` asset 403s - fix perms
  755/644 after builds.
- **Honest-data rule**: dev captures are fine for opp-table/wave patterns (CSVs
  current) but NEVER source scorecard/ledger stats from dev (stale
  featured_history.json; prod is the claim source - GTM claim-rail rule).
- Acceptance gallery (visible proof): `http://tw2-dev.trxstat.com/capture-gallery/`
  (files in `/var/www/tradewave/capture-gallery/`). Planned skins, NOT built:
  HTTP wrapper, MCP `capture_tradewave_ui` tool.
- **Crop regions (added 2026-07-09)**: `waveViewer` (`.seasonal-barchart-parent`),
  `viewerPlusDisplay` (`#right-content`), `appNoBanner` (`#root`), plus `display`/
  `oppTable`/`full` (existing). `#main-header` is a SIBLING of `#root` in the raw
  HTML shell (`web-react/public/index.html`), not an ancestor - server-string-
  substituted by `web/app.py`, outside the React tree entirely - so "exclude the
  banner" is just `#root`'s own box, no offset math. `oppTable` crop is now sized
  to actual row `boundingClientRect`s (optional `oppTable.cropRows: N` spec field
  caps it) instead of the fixed-height `.opp_table_div` pane, fixing a real
  proportionality bug (1 row used to produce a 1954px-tall mostly-empty PNG).
- **KNOWN BUG (any future Puppeteer/screenshot work on this box must know this)**:
  `page.screenshot({clip})` is UNRELIABLE over a region containing a Chart.js
  `<canvas>` on this box - it can silently write a blank PNG even when
  `getImageData()` read directly against that same canvas, at the same instant,
  proves real painted pixels exist. Verified via controlled A/B, reproducible, not
  a timing issue (stability + a canvas-paint gate both already passed first). Root
  cause looks like a GPU-compositor-vs-canvas-backing-store desync in headless
  Chrome specific to the `clip` capture path at 2x/4x `deviceScaleFactor` - a
  plain unclipped `page.screenshot()` never exhibits it. Workaround (not a Chrome
  fix, a capture-strategy change): take one unclipped full-page screenshot, then
  crop it INSIDE the page via an offscreen `<canvas>` (`drawImage` + `toDataURL`)
  - `captureCroppedRegion()` in `capture.js`. Any other tool on this box doing
  clipped canvas screenshots (e.g. `/root/tw-uitools/shot.js`) should use the same
  software-crop workaround rather than trusting `page.screenshot({clip})` directly.

---

## 7A. TW2 v2 - Public API gateway + MCP (LIVE ON PROD since 2026-07-04)

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

**LAUNCHED ON PROD 2026-07-04** (dark-ship retired): prod-app runs venv-api +
`tradewave-apiserver` (:8088) + `tradewave-mcpserver` (:9090, streamable-http, OAuth
via prod AuthKit `https://committed-orbit-04.authkit.app` - the value MUST carry the
https:// scheme or the JWKS client crash-loops) behind nginx :8080 (per-env
`server_name` swap of ops/nginx/tradewave-developer-portal.conf; the REPO conf says
`listen 80` but installed copies use :8080 - the appserver owns :80 on app boxes) and
cloudflared ingress for api./mcp./developers.tradewave.ai. deploy.sh deploys+verifies
the full stack on every env (verify_deploy prod PORTAL=1). Paid API pricing display is
GATED OFF via `TW2_API_PRICING_LIVE` (unset = "Coming Soon"; owner sets prices later).
GOTCHA: `cloudflared tunnel route dns` on either prod box lands in the trxstat.com
zone (certs do not cover tradewave.ai) - the 3 public DNS records are dashboard-only.
The `users.api_tier` webhook write EXISTS and works (web/app.py ~:3125,
product_line=api routing; verified live 2026-07-10: Stripe TEST checkout flipped
api_tier in ~2s, cancel reverted to NULL in ~2s).

**Subscriber-UX audit 2026-07-10 (full journey tested end-to-end on dev + prod probe;
report + fix order in memory note project_api_subscriber_ux_audit_2026_07). OPEN GAPS:**
1. **FIXED (dev, 2026-07-10, uncommitted): demo-scan/enumeration giveaway.** The demo
   allowlist (`tiers.INTERNAL_TIERS['demo']['demo_symbols']` = AAPL/MSFT/NVDA/AMZN/TSLA)
   is now enforced at CANDIDATE-SELECTION time (before ranking/enrichment, so the demo
   also stops burning full-market compute) via a shared `_demo_scope_rows()` helper in
   `apiserver/routes.py`, applied to BOTH `/v1/scan` (was fully unguarded - the original
   finding) AND `/v1/opportunities` (a second unguarded single-market enumeration route
   found by the fix's own route-coverage sweep, same bulk-exposure shape as scan, fixed
   the same way). `evaluated_count`/`summary` now honestly describe the 5-symbol universe
   for the demo principal; non-demo callers are an exact no-op (gated on
   `entitlements['demo']`). Full route sweep (13 routes): symbol-scoped routes already had
   `_demo_guard_symbol` (analyze/patterns/seasonal-chart/opportunities-by-symbol/securities-
   patterns); `/markets/<id>/symbols` + `POST /score` already had `_demo_block_enumeration`;
   `/markets` + `/me` are metadata-only (no guard needed); `/daily-pick` +
   `/daily-pick/track-record` are a single published item, not caller-controlled
   enumeration (no guard needed). Verified live on DEV: demo `/v1/scan?market=2&limit=5` and
   `/v1/opportunities?market=2` both return ONLY allowlist symbols with truthful
   `evaluated_count`; a real key is unaffected (regression-tested + live-diffed). **PROD
   RECHECK 2026-07-12: this uncommitted fix is NOT deployed** - the public demo scan evaluated
   162 candidates and returned AVGO/CTAS/BX/PG/EXPD, and `/v1/opportunities` likewise returned
   non-allowlist symbols. Production still exposes the full ranked S&P candidate universe to
   the public token and burns the full-market compute path.
2. **FIXED (dev, 2026-07-10, uncommitted): `docs/API_CONSOLE_USER_FLOWS.md` §7.1
   entitlement rule implemented.** `apiserver/tiers.py` gained `API_TIER_RANK =
   {free:0, navigator:1, dev:2, pro:3, business:4}`; `api_tier_from_user()` now returns
   MAX(explicit, bundled) by rank instead of "explicit always wins" - a bundled-pro
   Strategist holding an explicit lower dev sub now correctly resolves `pro` (was
   demoted to `dev`). An explicit value unranked by `API_TIER_RANK` (a service/internal
   name like `mcp`/`chatbot` leaking in defensively) is treated as absent - logged,
   never grants, never crashes. 3 import-time rail asserts + 3 spot-asserts added,
   following the file's existing assert-at-import style. Only two real call sites in the
   repo, both safe by design for MAX: `apiserver/auth.py:67` (gateway auth) and
   `web/api_portal/blueprint.py:157` (console billing/UI - its docstring already
   described this exact contract pre-fix). MCP's `merge_entitlements`/`mcp_tier_for`
   were untouched (already MAXed via a separate path - see §7B MCP mirror block).
   Verified live end-to-end via a throwaway Postgres user+key (created, checked
   `GET /v1/me` resolved `pro`, deleted). The rest of spec §7 (billing card states,
   portal CTA routing, C1-C5 copy, /account hub link) landed the same day - see item 3.
3. **FIXED (dev, 2026-07-10, uncommitted): `docs/API_CONSOLE_USER_FLOWS.md` §7 items
   2-6 implemented** (portal CTA routing + billing card states + C1-C5 copy + account
   hub link). Portal CTAs (`site/api_marketing/generate.py`) now route paid cards to
   `signup?next=%2Faccount%2Fapi%2Fbilling%3Fsubscribe%3D<tier>` and the free card to
   `signup?next=%2Faccount%2Fapi%2Fkeys`; the Founder strip adds `%26promo%3DFOUNDER`.
   **The billing card-state defect (former item 4 below) is FIXED**: `routes_billing.py`
   no longer derives ANY card state from `has_customer = bool(stripe_customer_id)` (that
   flag now gates ONLY whether the "manage in portal" link renders, never purchase
   state) - a new `entitlement_context()` helper in `web/api_portal/blueprint.py`
   computes `explicit` (rankable `users.api_tier` or None - the webhook nulls it on
   cancel, so its presence/absence is the reliable "holds an active explicit API sub"
   signal), `bundled` (`WEB_TIER_TO_API[web tier]`), `effective` (calls
   `api_tiers.api_tier_from_user`, never reimplements the MAX), `effective_source`
   (which side won), and `redundant` (R7: explicit rank <= bundled rank). A pure
   `_card_state(card_rank, ctx)` in `routes_billing.py` implements R5's 6 states exactly
   (`current_explicit` / `current_bundled` / `included_below` / `downgrade` /
   `upgrade_explicit` / `subscribe`) - a churned subscriber (stale `stripe_customer_id`,
   NULL `api_tier`) now sees a real Subscribe button, and a bundled user never sees a
   purchasable-below card. Checkout is server-side re-guarded (4xx+flash, not 500, for
   `tier rank <= effective`) independent of what the UI rendered. `?subscribe=<tier>`
   highlights + scrolls to the target card (CSS `.plan-highlight`, respects
   `prefers-reduced-motion`) and degrades silently (no highlight, no error) for an
   unknown/already-covered tier or `API_PRICING_LIVE` off. `promo=FOUNDER` looks up the
   Stripe promotion-code id fresh per checkout (`stripe.PromotionCode.list(code=
   'FOUNDER', active=True)`, deliberately NOT cached - redemption count moves as seats
   fill) and passes `discounts=[{"promotion_code": id}]`; any Stripe rejection at
   session-create time falls back to `allow_promotion_codes=True` + a flash note, so
   the 101st founder-seat click never dead-ends. C1 (bundling banner) and C4 (active
   reverse-trial note, gated on `web_tier == 'explorer' AND reverse_trial.
   in_reverse_trial(...)` - never inferred from `effective != raw tier`, which breaks
   for a role-bypass admin) render on BOTH Keys and Billing from the same
   `entitlement_context()` dict so the two tabs can never disagree; C5 (redundant-sub
   advice) renders on Billing only. `/account` hub gained the "API & MCP" action (R8),
   gated on `config.API_CONSOLE_ENABLED` (new `account()` context var) so it does not
   404 while the console ships dark on prod. 20 new tests in `tests/test_api_portal.py`
   (persona x card-state matrix, banner copy, `?subscribe=` highlight/degrade, checkout
   guard, no-em-dash sweep) - 34/34 pass. Verified live via Flask test-client persona
   injection (`tools/api_console_audit/driver.py`'s pattern) against dev's real Stripe
   TEST mode (both the FOUNDER-promo and plain-checkout paths produced live Stripe
   Checkout sessions with the expected `discounts`/`allow_promotion_codes` shape).
   `tradewave-web` restarted, healthy.
4. **Cross-write to verify:** after an API-line subscribe, the API sub id appeared in
   the WEB `users.stripe_subscription_id` column (status NULL); `/stripe/success`
   writes sub_id UNCONDITIONALLY with no product_line guard (web/app.py:2612).
   Pin the writer with a real browser checkout before trusting the column.
5. **PROD proof-data topology failure (verified read-only 2026-07-12, unfixed):** the
   scorecard generator owns `/home/flask/site/data/featured_history.json` on the WEB box
   (76 rows), but `tradewave-apiserver` runs on the separate APP box and
   `apiserver/appserver_client.py` hardcodes that same local path. The file does not exist
   on PROD APP. `_load_featured_history()` treats absence as `[]`; `/v1/daily-pick` then
   returns HTTP 200 with `card:null`, while `/v1/daily-pick/track-record` returns HTTP 200
   with zero picks. There is no WEB-to-APP sync in `regen_site.sh` or `deploy.sh`, and WEB
   updates this file every scorecard cycle, so a deploy-time copy alone would become stale.
   Also, the API independently reimplements pick-result arithmetic instead of importing the
   WEB's shared `site/lib/pick_stats.py`, leaving a second drift path once transport is fixed.
   Required shape: one atomically published canonical proof artifact/data store accessible to
   both tiers; missing/stale proof data must fail readiness and return an explicit 503, not a
   successful empty payload. `verify_deploy.sh` must assert non-null/non-empty contracts.
   Separately, the machine ledger emitter exists only in dev's uncommitted
   `generate_scorecard.py`; PROD lacks the emitter and `/data/daily-pick-ledger.json` is 404.
6. **PUBLIC demo quotas are global, not per visitor (verified 2026-07-12):**
   `resolve_customer()` maps the published token to the constant `user_id='demo'`; rate-limit
   and ML-quota Redis keys use only `user_id`. All visitors therefore share 30 requests/min,
   1,000 requests/day, and just 25 ML scorings/day. With five cards per advertised demo scan,
   roughly five full scans can consume the entire global ML demo budget. The live response
   reached `ml_remaining_today:0` during verification. Serve a cached/precomputed demo or
   isolate abuse limits per visitor/IP; do not meter the public onboarding demo as one user.
Items 1-3 are FIXED on dev (uncommitted - owner commits) and were INDEPENDENTLY
RE-VERIFIED 2026-07-10 by a fresh-eyes agent run (own throwaway user, own Stripe TEST
objects, spec-verbatim string asserts): all 6 persona card-state rows match spec §3;
C4 renders ONLY during an active trial; the server-side checkout guard 400s an
already-covered tier with no Stripe session created; full lifecycle timed - subscribe
webhook write 2.04s, cancel 1.05s, and the CHURN-RECOVERY loop proven end-to-end
(post-cancel cards render actionable Subscribe again, and a churned user's
re-subscribe re-activated in 2.05s reusing the same Stripe customer); gateway MAX +
demo scoping confirmed with a no-leak check (a normal free key still gets the
full-market scan, evaluated_count 299). NOTE for spec readers: §3's table row
"Explorer: Free = current" is shorthand - per R5's authoritative prose a bundled
T==C card renders disabled "Included with your {WebTier} plan", which is what ships
(clarified in the spec table 2026-07-10).
REMAINING OPEN (2026-07-12 priority): deploy items 1-3, fix the production proof source
(item 5), and repair public-demo isolation/reliability (item 6) before calling the surface
production-clean. Verify the cross-write in item 4 before flipping
`TW2_API_PRICING_LIVE`; it can overwrite the WEB subscription id once standalone API
checkout is enabled. Lower-priority follow-ups: (a) the portal header auth-swap is DEAD
CODE on portal pages - the copied tw-auth-link script fetches `/api/me`
same-origin against the static portal nginx docroot (404s); a real fix needs CORS on
`/api/me` for the developers host PLUS widening the tw2_session cookie
domain/SameSite scope at 3 set_cookie sites (an auth-posture decision, deliberately
not bundled with the §7 work); (b) gateway 401 body is identical for invalid vs
missing key with no signup pointer; (c) cosmetics - console quickstart key overflows
its box, MCP/Usage tabs don't mention trial elevation, `api.tradewave.ai/` +
`/v1/health` 404. What already works well (keep): one-time key reveal + baked tabbed
quickstart, server-side key limits, ~2s webhook activation/cancel, checkout naming,
pricing copy exactly matches tiers.py.
(Source: `apiserver/`, `mcpserver/`, `web/api_portal/`, `site/lib/portal_urls.py`,
`api/openapi.yaml`; built + verified on dev .176, 2026-05-27; fixes 1-2 verified on dev
2026-07-10; item 3 (spec §7 remainder) implemented + verified on dev 2026-07-10.)

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
  (MONTHLY-only + Founder) under `product_line=api`; it SELF-HEALS an earlier annual
  seed by re-pointing each product's `default_price` to the monthly price FIRST (Stripe
  refuses to archive a default price) and then archiving every active annual price. It
  also self-verifies/heals the Founder coupon: retrieve with `expand=["applies_to"]`
  (current API versions OMIT `applies_to` from the default representation - without
  expand a restriction check silently reads "unrestricted"), drifted + 0 redemptions =
  delete + recreate, redeemed = loud warning + hands off; promo reuse requires ACTIVE +
  pointing at our coupon. Stripe SDK 15.x: `PromotionCode.create` nests the coupon under
  `promotion={"type":"coupon","coupon":id}` (top-level `coupon=` is gone).
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

**API billing + quota model (owner decisions 2026-07-05, pre-pricing-launch so no
grandfathering):**
- **MONTHLY ONLY.** There is no annual API price anywhere (`price_annual` removed from
  `tiers.py`; seeder/console/pricing page are all monthly-only; the console checkout
  400s an explicit annual ask with `monthly_only`). Why: developers won't prepay a year
  for an unproven API, annual lumps distort the MRR read, a large annual refund is a
  dispute magnet, and monthly keeps repricing agile while the ladder settles. Adding
  annual later is trivial (seeder is idempotent); walking it back would not be.
- **Per-day quotas are anchored to the data's cadence** - the dataset refreshes ONCE per
  trading day, so each cap = "a per-symbol card for everything in your scope, daily,
  plus headroom". Measured universe (dev appserver, 2026-07-05): US stocks + ETFs ~3.7k
  symbols; all markets ~18.7k unique (the per-market lists share one US name list, so
  markets 0-4 each report 3,465). Shipped: free 10/min+100/day, dev 60/min+1,000/day,
  pro 120/min+5,000/day (a full US+ETF sweep ~30min at burst), business
  300/min+20,000/day (a full all-markets nightly sweep ~1h). Above Business =
  Enterprise/custom. Never size per-day to data-feed scale: it reads as nonsense for
  EOD data and invites bulk export the EODHD derived-data posture avoids.
- **Quota is enforced PER CUSTOMER, not per key** (`auth.check_rate_limit` buckets on
  `user_id`), so `max_keys` never multiplies entitlement.
- The consumer-MCP mirrors were re-scaled to genuinely assistant-sized per-day caps at
  the same time (Analyst-in-chat 1,000/day, Strategist-in-chat 2,000/day - a heavy
  human chat day is a few hundred tool calls).

**Pricing-visibility gate (2026-07-04):** `apiserver/tiers.py:API_PRICING_LIVE` (env
`TW2_API_PRICING_LIVE`, truthy strings `1`/`true`/`yes`) is a DISPLAY-only flag, separate
from the tiers/quotas themselves (which are always live/enforced). While unset (owner has
not finalized paid-tier $), the marketing generator (`site/api_marketing/generate.py`),
the docs generator (`site/api_docs/generate_api_docs.py`), and the console billing page
(`web/api_portal/routes_billing.py` + `templates/api_billing.html`) all import it and
suppress paid-tier dollar amounts: marketing pricing cards show "Coming Soon" + a
talk-to-sales CTA (Free card + the Founder's-plan strip - which quotes a derived Pro
discount - are hidden with it; the old monthly/annual toggle was REMOVED outright
2026-07-05 with the monthly-only decision), docs show "See pricing page",
and the console billing page hides upgrade cards/checkout for tiers the user is NOT
already on (their own current plan - even if paid, e.g. a bundled Analyst->Dev - still
renders normally, since that is real state, not marketing). Checkout/Stripe code paths are
untouched. Regenerate after flipping: `ops/assemble_developer_portal.sh` (or the individual
generators). The flag resolution FALLS BACK to `/etc/tradewave/secrets.env` when the env var
is unset (`tiers._pricing_live_flag`, env wins; added 2026-07-05) - necessary because the
generators run from operator/deploy shells that do NOT load the box env (`deploy.sh` sshes
in as root), and before the fallback a post-flip deploy regen silently reverted the
published pages to "Coming Soon". Note `portal_urls`'s own secrets.env fallback does NOT
cover this: `generate.py` imports `apiserver.tiers` BEFORE `portal_urls`, so the flag was
evaluated before portal_urls seeded os.environ. Status: DEV flipped ON 2026-07-05 (sandbox
checkout testing); staging/prod remain OFF until the owner finalizes paid-tier $.

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

**Missing-projection why-question: a KB fact alone does NOT steer behavior (fix 2026-07-04).**
Tara answered "why is there no projection line" (asked with a PE+3 slice loaded) with the generic
enable-it-in-Settings steps - the real reason is the PE mode (see 7.1: a non-current PE phase moves
the view to a future year, so the projection is hidden by design). Fix in TWO layers, and the second
was required: (a) the FACT in `chatbot_knowledge.txt` ("Seasonal Projection" section WHY-paragraph +
PE Cycle key-concepts bullet); (b) a routing RULE in `chatbot.py build_system_prompt` (MISSING-
PROJECTION WHY-QUESTION: answer the reason, fire NO set_view, never change the user's PE mode
uninvited, offer the flip and act only on "yes"). LESSON (same class as the Phase-2 TOOL_INSTRUCTION
finding): with the KB fact alone, Tara still obeyed the earlier YOU-DRIVE prompt rules and silently
switched the user to consecutive mode without explaining - behavior routing MUST live in the
system-prompt rules; `chatbot_knowledge.txt` is for facts. Also added to the FORMAT rule: never emit
the em-dash character (house style). NOTE: `chatbot_knowledge.txt` is loaded once at appserver
startup (`_load_knowledge`) - restart `tradewave-appserver` after editing it. Verified live on dev
(PE+3 context chat + "yes" follow-up fires `set_view pe_cycle:cons`) and `tara_truth_eval.py` 8/8.

**Purple full-history projection line: chatbot coverage (2026-07-05).** `chatbot_knowledge.txt`
"Seasonal Projection" section now covers BOTH lines: a DEFINITION - PURPLE LINE routing paragraph
("what is the purple dashed line / Proj N-Y" -> full-history consecutive-years projection, compare
vs the golden line for slice-vs-long-run agreement), reworked how-it-works/enable-steps (enable-steps
lead with the Settings checkbox because of the 7.1 chicken-and-egg pill quirk), tier-cap note, and
both-lines-hidden-in-PE-future wording; the Settings-window list, PE key-concepts bullet, and guides
list were updated to match, and guide trigger #6 in `chatbot.py build_system_prompt` gained the
purple/Proj N-Y/full-history terms. Verified live on dev via `/chatbot/chat` probes (definition +
enable question; correct answers, projection guide auto-opened). GAP: the in-app `ProjectionPopup.js`
guide itself does NOT yet mention the purple line (stale guide; fixing it needs a React rebuild via
`npm run build`).

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
  breaks the next pull; `chown -R flask:flask /home/flask` to recover). Same failure
  family: root-owned working-tree files (seen 2026-07-02 on
  `site/templates/index-dark-blue.html`) make non-root editors fail EACCES on the
  temp-file rename - the same chown recovers, or edit as root preserving ownership.
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
- **GA4 server-side tracking (Measurement Protocol, built 2026-07-07, uncommitted
  on dev - NOT yet deployed):** `web/ga4_mp.py` fires `begin_checkout`/`purchase`/
  `sign_up` server-side so they don't depend on the browser tab staying open or
  gtag.js loading. `parse_ga_client_id(request)` reads the `_ga` cookie
  (`GA1.<ver>.<p1>.<p2>` -> client_id `"<p1>.<p2>"`, else `None`);
  `send_event(client_id, name, params, user_id)` POSTs to
  `google-analytics.com/mp/collect?measurement_id=<config.ga_measurement_id>&
  api_secret=<config.GA4_MP_API_SECRET>` - **fails open** (catches every
  exception, no retry, returns bool) and no-ops silently whenever measurement id /
  api secret / client_id is missing (the normal dev+staging state, since both are
  prod-only secrets.env values). Three fire points, each ALSO wrapped in its own
  local try/except beyond `send_event`'s internal fail-open, because each call
  site sits inside code whose own broad exception handler would otherwise
  misinterpret an analytics bug as a real failure:
    - `begin_checkout` - in `stripe_create_checkout()` (`/api/stripe/create-
      checkout`) right after `stripe.checkout.Session.create` succeeds. Also
      stamps `ga_client_id` + `tier` onto the Checkout **Session's own top-level
      `metadata`** (a separate object from `subscription_data.metadata`, which
      already carries `tw2_user_id`/`tw2_tier_target`/affiliate fields) so the
      webhook can read them back.
    - `purchase` - inside `/webhooks/stripe`'s `checkout.session.completed`
      branch (NOT `/stripe/success`). That branch already runs in this webhook
      but drives NO tier write (only `customer.subscription.*` events do), so
      this is purely additive; the handler's existing event_id dedup (before
      this code runs) makes it safe. `transaction_id` = the checkout session id
      (GA4's own purchase-dedup key); `value` = `amount_total/100.0` (this is
      legitimately `0.0` on the standard 7-day-trial checkout - nothing is
      charged yet at session-completion time, not a bug).
    - `sign_up` - in the WorkOS `auth_callback`, gated on a new transient
      (non-mapped, non-persisted) `User` attribute `_tw_new_signup` that
      `lazy_create_user()` sets to `True` ONLY on the brand-new-INSERT success
      path - deliberately NOT on the two-tab-signup IntegrityError re-query path
      (the sibling worker that won the race already got the flag), so a signup
      race can't double-fire `sign_up`. Plain Python attribute assignment
      survives `commit()`/`refresh()` since SQLAlchemy's expire-on-commit only
      expires mapped columns.
  Tests: `tests/test_ga4_mp.py` (cookie parsing + send_event, hermetic, no
  network) + 3 assertions added to `tests/test_lazy_create_user.py` for the
  `_tw_new_signup` marker. **Operator TODO before this does anything live:**
  set `GA4_MP_API_SECRET` in prod's `/etc/tradewave/secrets.env` (value lives at
  `/etc/tradewave/ga4-mp-secret` on the dev box already - do not read/copy it
  through chat) and deploy.
- **Dunning (Stripe Smart Retries final-notice email, built 2026-07-09, GTM
  playbook CARD W1.3, uncommitted on dev):** Stripe Dashboard-side Smart Retries
  (FOUNDER-toggled, account-level - no API/CLI surface exists for it) owns every
  mid-sequence "your payment failed" email; the app owns exactly ONE, a final
  pre-cancel "your access pauses" nudge. `_fire_dunning_final_notice()` in
  `web/app.py` (near `_existing_eod_subscription`) is called from the
  `invoice.payment_failed` branch of `webhook_stripe()`, gated on
  `collection_method == "charge_automatically"` AND a real `subscription` present
  AND `next_payment_attempt is None` (see §11 invariant 19 for why the bare-null
  check alone is wrong). Best-effort/post-commit, same fail-open pattern as GA4
  above (own try/except at the call site; the helper itself never raises past
  that). Sends via `email_utils.resend_send_email`; the CTA link is a live Stripe
  billing-portal session, degrading to a plain `/account` link if that call
  fails. Tier/access is intentionally UNCHANGED by dunning - `invoice.payment_failed`
  never touches `new_tier` in the webhook's tier-mapping block, so access stays
  live through Stripe's whole retry sequence; only the copy warns it is ending.
  Tests: `tests/test_dunning.py` (8 tests, full webhook-request-path coverage via
  the existing `mock_stripe` fixture - no live Stripe test-clock needed).
  **Operator TODO before this recovers anything:** enable Smart Retries in the
  Stripe Dashboard (Billing -> Revenue recovery / Retries) + the cancel-after-
  N-failures final action - the app code is inert without it (a `past_due` sub
  would otherwise hang forever with no configured end state).
- **Trial-activation Postgres signal (`ai_score_viewed`, built 2026-07-09, GTM
  playbook CARD W1.4, uncommitted on dev):** `users.first_ai_score_viewed_at`
  (migration `b3f6a8c1d9e2`, nullable TIMESTAMPTZ) is the persistence anchor for
  the day-2/day-7 trial-activation emails (Week-2 cards) - **they read this
  column, never GA4**, per strategy §2's binding persistence rule. Written by
  `POST /api/activation/ai-score-viewed` (`web/app.py`, right after
  `onboarding_usage_summary`), called once per browser session by
  `web-react/src/components/TableBox.js` (a `useEffect` gated on
  `hasAI && hasMLData` - i.e. an Analyst+ user has REAL ml_score data on screen,
  not just the locked teaser column) via a module-level fired-flag (courtesy
  dedupe only; the server's own idempotent `IS NULL` guard + `with_for_update()`
  is the actual source of truth for first-touch). One handler does, in order:
  (1) append an `onboarding_events` row (`event_type='ai_score_viewed'` - reuses
  the existing table, no new one), (2) idempotent first-touch UPDATE of the new
  column, (3) fire the GA4 `ai_score_viewed` event (fail-open, same pattern as
  above, fired AFTER the Postgres commit). Tests: `tests/test_activation_signal.py`
  (6 tests).
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

0. **Scorecard WIN DEFINITION (owner, 2026-07-04 - explicit, supersedes the
   2026-06-16 held-to-close headline):** a daily pick WINS when it reaches the
   AI's predicted gain (`peak_return >= pred_return`) inside its window - open
   or closed, permanently (no flip-back on a faded close) - or when it closes
   profitable. Open picks that have not hit are PENDING (excluded from the
   denominator). "The entire point of the AI score is the highest probability
   of gain - if that gain is reached, it's a win." Single source =
   `site/lib/pick_stats.py` (is_win/is_judged/hit_target; scorecard + homepage
   both consume it). Held-to-close stays as the LABELED SECONDARY stat and
   every row keeps its realized close return visible - do NOT remove that
   transparency, and do NOT make held-to-close the headline again.
   RETURN STATS follow the same exit rule (owner, 2026-07-05): a target-hit
   pick REALIZES exactly its pre-published predicted gain (limit order fills
   on the touch - never the peak); a miss realizes the window close; open
   not-yet-hit picks have no result (`pick_stats.result_return`). Medians
   (headline + month groups + homepage) must never mix a hit winner's faded
   close into the return stats (the June-2026 WDC short: +6.8 target hit,
   -27.3 close - the bug that prompted this rule).

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
17. **GA4 server-side tracking (`web/ga4_mp.py`) must never affect checkout/webhook/
    signup, even if GA is fully down** - `send_event()` fails open internally, but every
    call site is ALSO locally wrapped in its own try/except (see §9), because each site
    sits inside a route/handler whose own broad exception handler would otherwise turn
    an analytics bug into a false checkout failure (`stripe_create_checkout`) or a
    wasted Stripe-retry that the webhook's event_id dedup would then silently swallow
    (`/webhooks/stripe`). Never remove either layer of wrapping when touching this code.
18. **`@require_login` (`web/app.py`) always REDIRECTS (302 to WorkOS hosted signup) an
    unauthenticated caller - it never itself returns 401.** It was written for page
    routes. Every existing JSON API route that uses it (`onboarding_event`,
    `api_activation_ai_score_viewed`) ALSO does a manual `if get_current_user() is None:
    return 401` inside the view body as a defensive habit, but that check is dead code -
    the decorator already redirected before the view ever runs. Don't rely on 401 from
    a `@require_login` JSON route in a test or a client; assert the redirect instead
    (`test_activation_signal.py::test_anonymous_is_redirected_not_written` is the
    reference case). A same-origin JSON fetch from React handles the redirect body
    harmlessly (the client only cares about `ok`), so this has never been worth fixing,
    but it recurs every time a new `@require_login` JSON endpoint is added - stop
    re-deriving it.
19. **Stripe `invoice.payment_failed`'s `next_payment_attempt` field being `null` does
    NOT by itself mean "Smart Retries are exhausted."** It is ALSO always `null` on
    `collection_method=send_invoice` invoices (no retry schedule ever exists there) and
    on the very first failure of a subscription whose retries are disabled account-wide.
    Any "final failure" / "retries exhausted" gate keyed off this field MUST additionally
    require `collection_method == "charge_automatically"` AND a real `subscription` on
    the invoice (see `web/app.py::webhook_stripe`'s dunning gate, `_fire_dunning_final_notice`
    call site, for the reference implementation) - caught in reasoner-review 2026-07-09,
    do not re-introduce the bare-null check.

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
- `docs/UI_CAPTURE_PIPELINE.md` - **canonical manual for the automated UI screenshot
  pipeline** (dev-only): spec schema, the full state-seeding map (scoped-key gotcha),
  overlay suppression, failure modes, runbook. Summary in §7.4.
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

- **E. PROD IS NOINDEXED - the cutover SEO flip never happened.** Found by the
  2026-07-04 AEO/LLM-visibility audit (live-prod-verified). **CODE FIX BUILT ON
  DEV 2026-07-04 (branch `feat/free-seasonal-report-funnel`, uncommitted at time
  of writing) - prod itself is NOT yet redeployed/regenerated, so prod is STILL
  noindexed until the next `TW2_ENV=prod` deploy + regen runs.** What changed:
  (1) NEW `site/generate_seo_files.py` writes `robots.txt` (`Allow: /` on prod /
  `Disallow: /` elsewhere, same `ENABLE_SEO` env test as `generate_home_page.py:187`,
  lists all 3 sitemaps), `sitemap.xml` (**rebuilt FROM DISK every run** - scans
  the web root's top-level pages + `insights/*.html` + `learn/*.html` +
  `markets/*.html` fresh each time, so a stale host or a deleted page can never
  survive a run; explicitly excludes `_static/markets` (retired SMN-era path),
  `404.html`, `home-ui-preview/`, `r/`, `patterns/`), and `llms.txt` (compact
  agent-facing map; Developers-portal line is best-effort via `portal_urls`,
  omitted rather than hardcoded if that host isn't configured). It is now the
  ONLY writer of `sitemap.xml` - `generate_insights.py:update_sitemap()` and
  `generate_learn.py:update_sitemap()` (the old append-only functions that grew
  stale-host/duplicate entries every run) are now no-ops, kept only so their call
  sites didn't need touching. Wired as the LAST step in `ops/regen_site.sh` (must
  run after every other generator so the sitemap reflects that run's output).
  (2) `scorecard.html` (`site/templates/scorecard.html` + `site/generate_scorecard.py`),
  `site/generate_about_page.py`, `site/generate_daily_ai_pick.py` now gate
  `noindex, nofollow` vs `index, follow` on the same per-generator `ENABLE_SEO`
  flag instead of hardcoding `noindex` forever; scorecard also gained a meta
  description (it had none), canonical link, and minimal OG tags (title/description/
  type/url) - previously it had ZERO metadata despite being the single most
  citable asset (the public forward track record). Verified on dev both ways
  (`TW2_ENV=dev` -> noindex/Disallow, `TW2_ENV=prod` -> index,follow/Allow, then
  reverted dev to its correct noindex state). REMAINING (not done here): (a) an
  actual prod deploy + `ops/regen_site.sh` run with `TW2_ENV=prod` (author the
  command, operator runs it - never touch prod directly); (b) Cloudflare AI Crawl
  Control / Bot Fight Mode bot-UA policy (verify before the 2026-09-15 Cloudflare
  default-category change); (c) GSC + Bing Webmaster Tools verify/submit
  (`INDEXNOW_KEY` already in secrets.env); (d) the content-restructure items
  (Q&A headings, TWA definition missing from static HTML, markets stats-as-divs).
  Full fix plan + owner priorities + LLM-citation research: memory
  `project_aeo_llm_visibility.md`.

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

**F. 2026-07-07 stability audit (appserver + React) - FIXED on dev (uncommitted) + the REMAINING backlog.**
A 4-agent review of the appserver (+ support modules) and the React wave-viewer; ~35
verified defects fixed on dev, pytest baseline unchanged (313 pass / same 4 pre-existing
fails), `npm run build` clean. What was hardened (details in git diff of that day):
- appserver.py: the `i=-1` not-found fallback (6 endpoints silently wrote to `list[-1]` -
  wrong-record corruption incl. wrong social-media posts) now returns not_found;
  `dr_report_remove` unknown-id/legacy-record 500; `getStockPriceByDate` missing the
  Not-Traded string guard (the ONE `get_symbol_csv` caller without it); daily-report
  quota counter now atomic INCR (double-click TOCTOU let users past the cap); the
  flask-limiter now has `swallow_errors=True` + `in_memory_fallback_enabled=True`
  (a redis db0 blip used to 500 EVERY rate-limited route at the limiter stage);
  `getChartData4` date-snap loops bounded + set-membership (unbounded `while d not in
  list` could spin a worker forever); `eval` -> `ast.literal_eval` on opp_meta;
  `detect_symbols_group` redis-cached (used to re-read every market CSV per call).
- Support modules: tradier_api.py `let1`/`leg1` NameError typo on order-position matching;
  timeouts on ALL Tradier calls (none had any - a Tradier hang froze gunicorn workers);
  sparse-option-chain guards + `get_creditspreads_data` graceful-degrade (returns the
  `[-1,-1]` sentinel shape the client handles); get_symbol_csv.py EODHD timeout +
  `e.response.text` crash-in-except fix + FileLock-timeout fallback to the stale CSV;
  Tara LLM read timeout 300s -> 100s (gunicorn kills workers at 120s - the 300s timeout
  made the apology fallback unreachable); tara_gateway empty-final-text guard.
- React: StockLineChart price-level persist-before-load effect (P0: switching symbols
  corrupted/erased saved price lines in localStorage); generation-counter ordering guards
  on OppList4 / ChartHistorical2 / NameFromTicker / manual-ticker-resolve / watchlist-items
  (slow older responses clobbered newer state); `loggedinUser === 0` vs `'0'` dead anon
  branches (App.js x2, InfoPopup x2); TradeInstrument order-path fixes (Place-Order crash
  on empty creditSpreadList, res.ok checks + visible error dialogs on order/cancel failure,
  socket null-guard, tracked refresh timers); day_range blur-handler crash (3 files);
  TableBox `table_data` dep + shallow clone; resize-handler batching; assorted timer cleanups.
- KNOWN REMAINING (deliberately deferred, in priority order): (1) db2 persistent JSON
  lists (reports/portfolios/watchlists) are non-atomic read-modify-write with NO per-user
  lock - two tabs can lose updates (the quota counter was the sharpest case and is fixed;
  the general fix = short per-user redis lock); (2) perf backlog: LineChart.js rebuilds all
  Chart.js datasets/plugins every render + unthrottled price-level drag, App.js ~150-key
  chartProps bag defeats child memoization, TradeInstrument `process_streaming_line`
  closes over stale state (deps gap); (3) NaN can leak into ChartData4/consolidated stats
  JSON on short/flat histories (strict JSON.parse rejects it); (4) `set()`+`expire()`
  non-atomic pairs remain in ~20 cache writes (orphan-key risk only); (5) OppList4
  realtime-prices cache has a small stampede window on expiry. Dead-file inventory:
  `appserver_apis.py` fully dead; `highest_volume_stocks.py` + `appserver_async.py` +
  `appserver_autotrade_funcs.py` + `reconcile_trade_data.py` have NO systemd/cron entry
  point (autotrade reconciliation is manual-only today); `tara_truth_eval.py` = manual CLI.
  SAME-DAY FIX (web tier, found live): `reverse_trial_ends_at_iso()` used
  `effective_tier != raw tier` as its "trial active" test - but the ROLE BYPASS
  (super_admin etc.) also elevates the effective tier, so a bypass-role explorer row with
  `reverse_trial_ends_at=NULL` 500'd `/app/` + `/api/me` (None.isoformat) once the web
  tier restarted with the bypass logic loaded. Now keys on
  `reverse_trial.in_reverse_trial()` + explorer tier. RULE: any "is the trial active"
  check must use the shared predicate, never tier-elevation inference.
  GOTCHA for editors: `tradier_api.py` is CRLF - scripted whole-file writes must preserve
  `\r\n` or the diff explodes. GOTCHA (bit us same day): a useEffect deps array that
  references a const/useState declared LATER in the component is a temporal-dead-zone
  ReferenceError at render - the build compiles fine, the app blanks at runtime (the
  DesktopLayout error boundary catches it panel-wide). When adding a dep, verify the
  declaration sits above the effect, then headless-verify the viewer (playwright +
  box-minted LTK + route-fulfilled /app/ index).

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
