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
- **Daily-pick X publishing** (`site/m_daily_ai_pick_social.py`) reads that same
  structured ledger record, never the standalone top-10 HTML page. It posts one
  factual, bounded message directly through X's user-context API. Dry-run is the
  default; writes require both `TW2_ENV=prod` and `TW2_X_POSTING_ENABLED=1`.
  A per-featured-date success lock is written only after X returns a post ID.
- **Public scorecard email signup** posts directly from the browser to the
  MailerLite form endpoint for `TradeWave Daily AI Pick - Scorecard` (form
  `193536028893512718`). The form is configured for double opt-in and the
  `DAILY_AI_PICK` group. The page reads MailerLite's JSON response and only shows
  success when `success` is true; it does not use the application lifecycle
  outbox described in section 2.6.
- So: the user's belief ("the daily AI pick is what gets stored in the scorecard")
  is **correct**. The "AI" = the ML scorer.
- TW2's standalone `site/generate_daily_ai_pick.py` -> `daily-ai-pick.html` is a
  separate top-10 artifact. It is not the canonical homepage pick and is not a
  source for scorecard social publishing.
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
  (`TW2_PUBLIC_HOST`, `TW2_ENV`, optional static-home gate
  `TW2_HOME_100_YEAR_PATTERN_ENABLED`), cross-tier
  (`TW2_APPSERVER_URL/IP`, `TW2_WEBSERVER_IP`),
  and external APIs (`EOD_TOKEN`, `ANTHROPIC_TOKEN`, `OPENAI_KEY`, `GROK_API_KEY`,
  `PERPLEXITY_API_KEY`, `REPLICATE_API_TOKEN`, `TAVILY_API_KEY`, `MAILERLITE_*`,
  `PUBLER_*`, `FACEBOOK_*`, direct X publishing (`X_API_KEY`, `X_API_KEY_SECRET`,
  `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`, `TW2_X_POSTING_ENABLED`),
  `INDEXNOW_KEY`, `TW2_GA_MEASUREMENT_ID`, `GA4_MP_API_SECRET`
  (server-side Measurement Protocol - see §9), `SENTRY_DSN`,
  contact form (`TURNSTILE_SITE_KEY/SECRET_KEY`, `RESEND_API_KEY`,
  `SUPPORT_EMAIL_TO/FROM`, `SUPPORT_IP_HASH_SALT` - see §5A),
  service URLs `TW2_ML_SCORER_URL/STOCKSCORE_URL/REALTIME_SERVICE_URL/EDGAR_SERVICE_URL/
  UPDATE_SERVER/KEYSTORE_URL/MASTER_APPSERVER/BLOG_QUEUE_SERVER/NEWS_WEBSITE_URL`).
  `TW2_ML_SCORER_MODE` selects `auto`, `v2`, or `v3`; `auto` detects the scorer
  contract from `/health` (`feature_count=59` for V2, `62` for V3).
- MailerLite application lifecycle configuration is explicit and fail-closed:
  `MAILERLITE_OUTBOUND_ENABLED`, `MAILERLITE_TRIAL_STARTED_GROUP_ID`,
  `MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID`, and
  `MAILERLITE_WINBACK_GROUP_ID`. `MAILERLITE_OUTBOUND_ENABLED` is effective only
  when it is truthy AND `TW2_ENV=prod`; lifecycle group IDs have no committed
  defaults. Dev and staging can therefore hold a shared account token without
  mutating production subscribers. Level-group IDs remain stable account-level
  identifiers in `config.MAILERLITE_LEVEL_GROUPS`.
- systemd loads it via `EnvironmentFile=`; a `<unit>.service.d/override.conf`
  `Environment=` wins for that service only. Cron does not inherit the override,
  so `TW2_ENV` must also be explicit in `/etc/tradewave/secrets.env`.
> **GOTCHA:** the `TW2_*_URL` service URLs must use the **VLAN `10.0.0.x`** addresses
> from inside the Kamatera network, not the public `104.238.214.253` (the central
> box allowlists by source IP -> public IP gets 403). `make_staging_secrets.sh`
> copies dev's public URLs, so these need hand-correction per env.
(Source: `config.py`, `make_staging_secrets.sh`, `web/app.py:157`.)

---

## 5. TW2 web tier (`web/app.py`, gunicorn `app:app` :5500)

Handles auth, the `/app/` shell, account/billing, admin. Marketing pages are NOT
Flask-rendered (static from `/var/www/tradewave/`).

- **100-Year Pattern public evidence page:**
  `site/generate_100_year_pattern.py` publishes the framework-free source at
  `site/100-year-pattern/100-year-pattern.html` to
  `/var/www/tradewave/100-year-pattern.html` and copies its CSV/book assets from
  `site/static/100-year-pattern/` to
  `/var/www/tradewave/_static/100-year-pattern/`. The physical `.html` filename
  is not the public address: nginx serves the canonical route
  `/100-year-pattern` and permanently redirects both `/100-year-pattern.html`
  and `/100-year-pattern/` to it. Homepage links, canonical/OG metadata, and
  generated calendar URLs all use the clean route. The homepage countdown is a
  separate, server-rendered block in `site/templates/index-dark-blue.html`,
  gated per environment by `TW2_HOME_100_YEAR_PATTERN_ENABLED`. The gate is off
  unless explicitly enabled, so stage and production do not inherit a dev test.
  The evidence-page countdown card also offers a no-signup calendar chooser.
  Google and Outlook open a prefilled event; Apple and other calendars receive
  an environment-aware `.ics` file rendered by the same generator. The public
  CTA retains the September 27 calendar anchor, while the 2026 event is dated
  Monday, September 28 because the published rule resolves a Sunday endpoint to
  the first trading day after it.

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
- **MailerLite lifecycle outbox:** signup and web-subscription Stripe paths write
  `mailerlite_lifecycle_events` in the SAME Postgres transaction as the user or
  billing mutation. `web/mailerlite_lifecycle.py` runs from the web-box flask
  crontab once per minute, derives the desired journey from the current User row,
  reconciles and verifies mutually exclusive `trial_started`,
  `trial_ended_explorer`, and `winback_explorer` trigger groups, and retries
  failures. No MailerLite HTTP call runs on the signup or Stripe request path.
  `reconcile` and `clear_paid` are permanent storage IDs. Paid checkout clears
  all lifecycle triggers; a local opt-out is removed from managed lifecycle
  groups and is never reactivated.
- **Admin:** Flask-Admin gated on `super_admin` role; `UserAdmin` validates
  `roles` against `models.ROLES`. **Roles single source of truth = `models.py:ROLES`**
  = `{super_admin, user, newsroom_author, service_account}`.
- **`report_renderer.py`:** renders a static date-range report (HTML + 3 PNGs) to
  `/var/www/tradewave/r/<slug>/`; invoked by the appserver via
  `/internal/render_report` (semaphore-limited to 4 concurrent).
(Source: `web/app.py`, `web/models.py`, `web/mailerlite_lifecycle.py`,
`web/email_utils.py`, `web/report_renderer.py`, `web/tier_compat.py`.)

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
2. **`POST /login/api`** (`login_api`) - the SERVICE login. Reads the key only
   from the `X-Service-Key` header and hashes it
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
- **Opportunity Table quote resilience (2026-08-21):** `OppList4` extracts only the
  symbols present in its regular and active rows, then calls the real-time service's
  bounded `/prices/bulk?symbols=...` route in chunks of 100. It must never call the
  multi-megabyte `/prices/all` route: that response can truncate while still starting
  with HTTP 200, which formerly left Redis empty and blanked the whole Price column.
  Validated quotes are cached per symbol in Redis for seven days, with a 55-minute
  fresh window. Refresh writes are per-symbol and occur only after validation, so a
  partial or failed refresh cannot erase last-known-good quotes. Matching refreshes
  use a short Redis lock to avoid request stampedes. `OppList4` returns older cached
  quotes with `source=realtime_stale` and their provider timestamp; the Price tooltip
  labels them as the last available real-time quote. Supported US/ETF rows retain the
  explicitly labeled completed-close fallback for small isolated quote gaps.
(Source: `appserver/appserver/appserver.py`, `web-react/src/components/TableBox.js`,
`web-react/src/components/realtimePrices.js`, `web/app.py:616`, `config.py`.)

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
- **AI-score eligibility is a TWO-part server contract (invariant, fixed 2026-08-16):**
  `OppList4` returns BOTH `ml_enabled` (market AND tier - may this user see AI scores
  here) and `ml_market_eligible` (market ONLY - `resourceID in
  config.ml_score_resource_ids`, i.e. US stocks + ETFs `'0','1','2','3','4','11'`).
  The viewer needs the market half on its own to tell "this market is not scored" apart
  from "your plan does not include AI scores"; it cannot derive it from the ANDed
  `ml_enabled`. REGRESSION 2026-08-06 (`37b53ab1`): the client began reading
  `opps['ml_market_eligible'] || false` while the appserver never emitted the key, so
  `mlMarketEligible` was permanently false - `selectOpportunityVisibleColumns` dropped
  all four AI columns on EVERY market and `AIScorePanel` rendered "AI Scores are not
  available for this market" for US stocks and ETFs. Reading a key the server never
  sends fails closed and SILENTLY; `tests/test_opplist_response_contract.py` now
  asserts every `opps['<key>']` read in `OppTable.js` exists in the `OppList4` payload.
- **Chart canvas resolution invariant (2026-08-04):** never force a fractional
  Chart.js `devicePixelRatio`. The seasonal bar chart and its canvas-rendered
  tooltip must use the browser's native device-pixel ratio. A forced `0.5`
  backing bitmap was stretched to twice its rendered size and became visibly
  blurry, especially with Windows or browser scaling above 100%.
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

**Phone-portrait opportunity columns live in ONE place (2026-08-16):**
`opportunityAIScores.js:MOBILE_OPPORTUNITY_COLUMNS` - `symbol, date, daysOut, lOrS,
avg_profit, sharpe_ratio, price` (Ticker / Date / Days / DIR / AvgP / SR / Price). It is
MEMBERSHIP only; render order still follows `columnOrder`, which keeps Price last. The
`37b53ab1` refactor moved column selection out of `TableBox.js` into
`opportunityAIScores.js` and retyped this set down to 3 columns (`symbol, daysOut,
sharpe_ratio`) while leaving the correct 7-item `MOBILE_COLS` behind as dead code in
`TableBox.js` - phones showed only Ticker/Days/SR from 2026-08-06 until 2026-08-16.
Per-column phone widths live beside it in `MOBILE_COLUMN_MIN_WIDTH`; the 7 core columns
total 336px and fit a ~390px viewport, and opting AI columns in via Settings
deliberately exceeds that so the table scrolls horizontally rather than dropping core
columns.

**Phone portrait ALWAYS uses short dates (MM-DD).** `resolveOpportunityShortDates()` ORs
the persisted `tw_short_dates` preference with phone-portrait; `OppTable` resolves it
once and passes the result to `TableBox`, so the date cells and the controls-row year
label (`OppTable.js`, shown once beside the month/day pickers) can never disagree. The
preference itself is never mutated. Rationale: the full `YYYY-MM-DD` does not fit beside
six other columns, and the "Short Dates" checkbox lives ONLY in `DesktopLayout`'s
settings panel - which never mounts on a phone (§7.2 routing), so a phone user cannot
reach the toggle at all. `isPhonePortrait(rdd, height, width)` in
`opportunityAIScores.js` is the single definition of phone-portrait for the table;
`TableBox` and `OppTable` both call it rather than re-deriving the orientation test,
which is exactly how the mobile column set and the column selector drifted apart in
`37b53ab1`.

Full mobile feature-parity audit (Opp/TableBox/chart/TradeDetail/InfoPopup/onboarding/
conversion/portfolio/trading-dialog components, 27 ranked defects incl. the AI-column gap
above): memory `project_mobile_parity_audit_2026_07`.

**Getting Started video onboarding is the active first-run experience (2026-08-25).**
The complete seven-day lesson implementation remains in the repository, but
`onboarding.js:LEGACY_SEVEN_DAY_LESSONS_ENABLED` keeps its auto-enrollment, LessonBox,
toolbar bulb, callouts, and Tara-tip suppression dormant. Every signed-in customer sees
the Getting Started video automatically once per browser and account under the versioned,
user-scoped localStorage key `tw_getting_started_video_seen_v2`. Version 2 reset the
first-run view for the corrected, redesigned onboarding panel on 2026-08-25. Closing by
any route records the view and unmounts the iframe, which also stops playback. A video-camera
icon in the desktop toolbar and a floating mobile video button always reopen it without
changing the saved state. `App.js` owns the modal state; subscription welcome hands off
through `tw-getting-started-video-open`. The player uses the privacy-enhanced
`youtube-nocookie.com` embed without autoplay, and nginx allows that origin only in
`frame-src`. The embed requests captions off, but the external player can still honor a
viewer's saved caption preference; only a TradeWave-hosted video can guarantee captions
stay off. Increment the key version only when every customer should automatically see a
replacement onboarding video.

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

The v2 public product (roadmap §9) sells the **derived** patterns (seasonal
opportunities, ML scores, the tracked daily pick) over a clean REST API + an MCP
server for AI agents - **never raw market data**. It launched on prod 2026-07-04;
paid standalone API price display remains separately gated as described below.

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
  over the gateway. Auth, two modes: ChatGPT, Claude.ai, and Claude Desktop can
  connect through OAuth - paste the URL and sign in with the TradeWave account
  (WorkOS AuthKit AS, RFC 9728 discovery; see `docs/MCP_OAUTH_INTEGRATION.md`). Cursor
  and other BYOK clients use per-connection `Authorization: Bearer <key>`; an optional
  local `mcp-remote` bridge can do the same. NO baked key for remote.
- **Console** `web/api_portal/` blueprint, mounted in `web/app.py` at `/account/api`
  (keys/usage/billing/MCP-connect). Reuses WorkOS session + Stripe + the `apiserver`
  package. Customer self-serve only.
- **Portal + docs**: static, brand-matched, nginx-served. Sources `site/api_marketing/`
  + `site/api_docs/` (generators read `site/lib/portal_urls.py`).
  LAUNCH GATE (2026-07-17): `portal_urls.MCP_LIVE` (env `TW2_MCP_LIVE`, secrets.env
  fallback - same flag + truthy parse as the home page and account card, so every
  surface flips together per env). While OFF, `site/api_docs/generate_api_docs.py`
  (mcp-reference) and `site/api_learn/generate_learn_api.py` (the connect-an-AI-agent
  article) render a "Preview" callout instead of promising a live consumer connect;
  content/URLs otherwise unchanged. Flipping the env flag + regenerating needs no code
  edit. Docs-accuracy invariant: examples in the docs are captured from live gateway
  responses, never hand-invented (the 2026-07-16 audit found invented examples were the
  #1 drift class); `api/MCP_TOOLS.md` is the MCP tool SSOT - sync `build_mcp_reference()`
  to it + `mcpserver/server.py` whenever tools change.

**Contract:** `api/openapi.yaml` (12 endpoints) + `api/MCP_TOOLS.md` (17 tools - 6
flagship + 11 primitives).

**Data shapes (verified vs the appserver):** opportunities = OppList4/OppBySymbol;
`win_rate` = ChartData4 stat `Percent Profitable` (share of profitable years, no
threshold - matches the UI), enriched per-symbol + cached gateway-side
(redis db4, 6h TTL); `min_win_rate` filters on it (NOT `ml.win_prob`). `/scan` enriches
only the requested Sharpe-ranked depth unless a receipt-dependent filter or alternate
ranking requires the bounded 50-row head. Its price-safe scan core is shared for 120 seconds
with a Redis distributed single-flight lock. Auth, tier projection, rate limiting, ML quota,
and ML scoring still run on every request. ML = MLScoreBatch
+ MLScorePending (two-phase), metered by API tier and limited to markets 0-4,11.
`/seasonal-chart` =
consolidated_seasonal_chart2 (365-day high/low-normalized, year-averaged 0-100 curve -
a price-SAFE shape, no price field). Daily pick/track-record = `site/data/featured_history.json`.

**Auth + data (app box):** customer keys in Postgres `api_keys` (HMAC-SHA256 via
`API_KEY_HMAC_SECRET`); usage in `api_usage_daily` + redis db4. Schema
`apiserver/schema.sql` (additive). Tiers/entitlements `apiserver/tiers.py`
(free/dev/pro/business; ML is 5/day, 100/day, unlimited, unlimited respectively;
unified accounts inherit the API tier from the web tier via `WEB_TIER_TO_API`; the
active `users.api_tier` column holds a separate API-only subscription). Stripe
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
at deploy). The gateway holds no authoritative local state (state = Postgres + gateway
redis db4 + the appserver, all over the network), so splitting it onto its OWN box later is
a config flip, not a rewrite:
the unit files now read the bind/host from env (`TW2_APISERVER_BIND`, `TW2_MCP_HOST/PORT`;
defaults = loopback, so co-located behavior is unchanged), and everything else
(`TW2_APPSERVER_URL`, `TW2_GATEWAY_REDIS_URL`, Tara's `TW2_GATEWAY_URL`) is per-env. Step-by-step:
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
API-only subscription webhooks write `users.api_tier` and the separate
`api_stripe_subscription_id` / `api_stripe_subscription_status` identity fields.
Web and API checkout metadata carry `product_line`, and terminal webhook events prefer
the matching stored identity before price-based classification. The remaining
commercial gate is the owner-controlled public price visibility flip.

**API subscriber journey, integrated and regression-tested in the current branch:**

1. The public demo allowlist from
   `tiers.INTERNAL_TIERS['demo']['demo_symbols']` is enforced before ranking and
   enrichment in both `/v1/scan` and `/v1/opportunities`. This prevents both
   full-universe disclosure and full-market compute for the demo principal.
2. `api_tier_from_user()` resolves the highest ranked explicit or web-bundled API
   entitlement. An explicit lower tier cannot demote a stronger bundled entitlement,
   and unranked internal names never grant access.
3. The API portal uses one shared entitlement context for Keys and Billing. It
   distinguishes explicit, bundled, included-below, downgrade, upgrade, and subscribe
   states; rechecks upgrade eligibility server-side; supports a guarded Founder promo;
   and links the console from `/account` only while the feature is enabled.
4. API checkout and lifecycle events preserve the web subscription identity. API
   subscription creation, replacement, cancellation, and stale deletion operate on
   the API-specific fields and cannot silently overwrite or downgrade the web plan.
5. Daily-pick proof data has one canonical owner on the web tier. Co-located
   environments may read the file directly; split environments use the private,
   service-key-authenticated `/internal/featured-history` feed. Missing, malformed,
   or unreachable proof data returns an explicit 503 instead of a successful
   `card:null` response.

**Remaining API onboarding risk:** all public demo callers currently resolve to the
same `user_id='demo'`, so they share the same minute, day, and ML quotas. This is not
an authorization escape, but it can make the public demo unreliable under concurrent
use. Before the public pricing flip, either serve a cached/precomputed demo or isolate
abuse limits per visitor/IP and add an integration test for concurrent demo use.

These changes are code-complete in this integration branch and are not yet deployed
to staging or production.
(Source: `apiserver/`, `mcpserver/`, `web/api_portal/`, `site/lib/portal_urls.py`,
`api/openapi.yaml`; implementation is integrated in the release branch and pending
the complete dev integrity gate.)

---

## 7B. API + MCP services (the productized v2 surface, build-state map)

> §7A is the design/decision narrative; this section is the **operational shape**
> of the same product as built out on dev `.176` (branch `feature/api-mcp`). The
> historical build record is `api/BUILD_STATE.md`; the frozen
> contract is `api/PATTERNCARD_SPEC.md` + `api/openapi.yaml` + `api/MCP_TOOLS.md`.
> **It is DERIVED-DATA-ONLY**: no raw OHLCV, last price, price-by-date, or price levels in
> any public response - all movement is percentages, the seasonal curve is a 0-100
> normalized index, never a price (the keystone invariant; see `api/PATTERNCARD_SPEC.md`).

The product is four NEW, additive pieces; the appserver data engine stays the canonical
internal data service. Its public contract is unchanged, but its runtime now has bounded
concurrency and cache/file safety for the API/MCP workload. All four bind loopback on every env - nginx + the `tw2`
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
  `TW2_MCP_PUBLIC_HOST` (the SDK's DNS-rebinding allowlist). Auth: **OAuth** for ChatGPT,
  Claude.ai, and Claude Desktop (sign in with the TradeWave account; WorkOS AuthKit, see
  `docs/MCP_OAUTH_INTEGRATION.md`) and **BYOK** for Cursor and other key-based clients.
  Each BYOK connection sends its own `Authorization: Bearer <key>`;
  `TRADEWAVE_API_KEY` MUST be UNSET on the remote transport.
- **Customer console** - `web/api_portal/` blueprint mounted in `web/app.py` at
  `/account/api` (GATED behind the WorkOS session): create/revoke keys, see usage, manage
  the API subscription, and the MCP-connect helper. Reuses WorkOS + Stripe + the
  `apiserver` package. `web/api_portal/create_api_products.py` seeds separate monthly
  and annual Stripe prices plus the Founder promotion under `product_line=api`. It also
  self-verifies/heals the Founder coupon: retrieve with `expand=["applies_to"]`
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
  (free/dev/pro/business; ML is tier-metered and only markets 0-4,11 are ML-eligible).

**API billing + quota model (current contract, code-verified 2026-07-17):**
- QUOTA DOCTRINE (owner, 2026-07-05, restored 2026-07-17): TradeWave sells detected
  seasonal patterns, not price data; the dataset refreshes once per trading day, so the
  per-day cap = "one per-symbol card for everything in your scope, daily, plus headroom"
  (US+ETF ~3.7k symbols; all markets ~18.7k). Data-feed-scale quotas are WRONG for this
  product and were explicitly rejected. HISTORY: the 2026-07-16 "Integrate verified API
  console" commit (93f0a16d) silently reverted the quotas to feed scale
  (5k/50k/250k) and re-added annual billing; quotas re-restored 2026-07-17. When
  "integrating" snapshots, diff `tiers.py` quota/billing lines against this block first.
- The enforced request caps are Free 10/min and 100/day, Dev 60/min and 1,000/day,
  Pro 120/min and 5,000/day, and Business 300/min and 20,000/day (Dev = a few-hundred-
  symbol working set daily; Pro = a full US+ETF sweep with headroom; Business = a full
  all-markets sweep with headroom; above that is Enterprise/custom).
- **Quota is enforced PER CUSTOMER, not per key** (`auth.check_rate_limit` buckets on
  `user_id`), so `max_keys` never multiplies entitlement.
- Consumer MCP mirrors the web product, ASSISTANT-scaled (a human chatting, never a
  feed): 400/day Explorer, 1,000/day Navigator, 1,000/day Analyst, 2,000/day Strategist.
- Billing is MONTHLY ONLY (owner decision 2026-07-05, REAFFIRMED 2026-07-17 after the
  93f0a16d revert briefly re-added annual). No `price_annual` anywhere; the seeder
  creates monthly prices only and SELF-HEALS a stale annual seed (re-points
  default_price to monthly first, then archives annual prices - verified live on dev
  Stripe TEST 2026-07-17, where it archived 3 stale annual prices the revert had
  created); checkout 400s any non-monthly interval; the price cache skips non-monthly
  prices so a stale one can never resolve. Live prod Stripe was never touched and
  remains monthly-only.
- The quota contract is pinned by `tests/test_consistency.py::
  test_api_price_and_quota_contract_matches_current_spec` + `docs/PRICING_QUOTA_SPEC.md`
  - change all three together.

**Pricing/acquisition gate (2026-07-04):** `apiserver/tiers.py:API_PRICING_LIVE` (env
`TW2_API_PRICING_LIVE`, truthy strings `1`/`true`/`yes`) controls paid-offer display and
server-side creation of new API subscriptions. It remains separate from tiers/quotas
(which are always live/enforced) and does not block existing subscribers from managing or
cancelling through the Billing Portal. While unset (owner has
not finalized paid-tier $), the marketing generator (`site/api_marketing/generate.py`),
the docs generator (`site/api_docs/generate_api_docs.py`), and the console billing page
(`web/api_portal/routes_billing.py` + `templates/api_billing.html`) all import it and
suppress paid-tier dollar amounts: marketing pricing cards show "Coming Soon" + a
talk-to-sales CTA (Free card + the Founder's-plan strip - which quotes a derived Pro
discount - are hidden with it; the monthly/annual toggle appears only after the flag
is enabled), docs show "See pricing page",
and the console billing page hides upgrade cards/checkout for tiers the user is NOT
already on (their own current plan - even if paid, e.g. a bundled Analyst->Dev - still
renders normally, since that is real state, not marketing). The checkout POST independently
returns 403 while the gate is off, including for handcrafted requests. Regenerate after
flipping: `ops/assemble_developer_portal.sh` (or the individual
generators). The flag resolution FALLS BACK to `/etc/tradewave/secrets.env` when the env var
is unset (`tiers._pricing_live_flag`, env wins; added 2026-07-05) - necessary because the
generators run from operator/deploy shells that do NOT load the box env (`deploy.sh` sshes
in as root), and before the fallback a post-flip deploy regen silently reverted the
published pages to "Coming Soon". Note `portal_urls`'s own secrets.env fallback does NOT
cover this: `generate.py` imports `apiserver.tiers` BEFORE `portal_urls`, so the flag was
evaluated before portal_urls seeded os.environ. Status: DEV flipped ON 2026-07-05 (sandbox
checkout testing); staging/prod remain OFF until the owner finalizes paid-tier $.

**MVP scalability baseline (2026-07-15, code complete, not deployed):** the appserver's
tracked unit defaults to 4 gthread workers x 4 threads for the 4 CPU / 16 GB dev box and
the owner-approved low-traffic 2 CPU / 4 GB production box. Production keeps four worker
processes for isolation and bounded concurrency, with modest CPU oversubscription while
traffic is low. Threads absorb bounded external-HTTP waits. Capacity scales when observed
load reaches the documented operational triggers. Appserver outbound HTTP uses reusable
bounded pools; expensive cache misses use Redis single-flight locks; CSV and JSON publishers use atomic
rename so readers never observe partial files. The API gateway uses a 12-connection
Postgres pool per worker, a 30-second positive-only bounded API-key cache (revocation may
take at most that TTL), atomic Redis ML-quota consumption, and exposes the appserver 429
storm-breaker state on `/healthz`. The scan path shares a price-safe 120-second core in
gateway Redis with a distributed single-flight lock. Default Sharpe scans enrich only the
requested result depth, so `limit=5` makes five ChartData calls instead of enriching the
old 50-row head. Seasonal curves are also cached in gateway Redis for six hours. Cache keys
contain normalized scan inputs only; authentication, entitlements, rate limiting, ML quota,
and ML scoring remain per request. Degraded receipt or market results are not stored in the
normal cache, and partial market failures are explicit in `market_failures`. Set
`TW2_GATEWAY_REDIS_URL` when API/MCP move off the appserver box so every API node shares the
same cache and coordination locks. MCP tool functions are async at the gateway I/O boundary,
share one bounded 32-connection `httpx` pool, and preserve the existing WorkOS OAuth and
BYOK validation paths. There is no appserver or API framework rewrite.

The split-topology daily-pick source is explicit: the web tier owns
`site/data/featured_history.json` and serves it only through the service-key-protected
`/internal/featured-history` route; the gateway reads its local configured file first and
falls back to `TW2_FEATURED_HISTORY_URL`. Missing or malformed data is a structured 503,
never a successful `card:null`. Gunicorn and nginx access formats log paths without query
strings so legacy `?token=` credentials are not retained in access logs. The read-only
release gate is `ops/verify_mvp_release.py`; it requires API BYOK and WorkOS OAuth MCP
handshakes, a non-null daily pick, bounded concurrent API load, and verifies the gateway
storm breaker never fires.

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

The wave-viewer assistant "Tara" (`appserver/appserver/chatbot.py`) is a CLIENT of the v1
gateway: it calls the flagship tools (scan / analyze / symbol-patterns / daily-pick) through
provider function tools and narrates the gateway's own composed PatternCards, so its numbers
match the API/MCP/daily-pick (one source of truth, derived-data only, same disclaimer).
NOT a product merge - Tara stays the login-gated UI helper; the public API/MCP is unchanged.
Data flow: React `Chatbot.js` -> appserver `/chatbot/chat` (JWT-gated) -> `tara_gateway.py`
provider-specific tool loop -> gateway `:8088/v1` (loopback) -> appserver engine. Auth/metering
(option A):

**Consumer-MCP product explanations (2026-08-04):** Tara answers common questions about
connecting TradeWave to ChatGPT or Claude through a deterministic product-knowledge route before
the model call. She distinguishes an unconnected general AI, screen-aware Tara inside Wave Viewer,
and an outside assistant using TradeWave MCP. The outside assistant can call the derived research
tools and return exact Wave Viewer links but cannot control the already-open viewer. Same-input
derived numbers come from the same gateway; account OAuth follows the consumer web plan and needs
no user-created API key; raw prices and holdings remain out of scope. Broader wording selects only
the dedicated MCP section from `chatbot_knowledge.txt`, so unrelated turns do not pay its token cost.

Tara holds an internal **`chatbot` tier** key (`tiers.INTERNAL_TIERS`, `service:True`, kept OUT
of the sold `API_TIERS`) and passes the web user id as **`X-TW-On-Behalf-Of`**; the gateway
(`auth.py:_apply_on_behalf`) honors that header ONLY for `service:True` keys and swaps ONLY the
metering principal to **`cb:<user_id>`** (regex-validated), so ML/rate/usage meter per web user
on the chatbot's OWN quota, namespaced apart from that human's API ML bucket. Provisioned by
`apiserver/provision_chatbot_key.py` (secrets `TARA_GATEWAY_KEY` + `TW2_GATEWAY_URL`, per-env -
gateway is `:8088` dev, `:80` staging/prod). Falls back to the old no-tools chat when the
gateway is unconfigured. Full spec + the proposed Phase 2 (chat drives the wave-viewer setters):
`docs/TARA_GATEWAY_INTEGRATION.md`.

**Investor discovery, proactive guidance, and chart-completion truth (2026-08-18).** Tara now
turns broad questions such as “I have $2,000—what should I buy?” and “How do I figure out what to
invest in?” into an educational research funnel: clarify horizon and investable universe, screen
mathematical seasonal candidates, compare recurrence/sample size/upside/downside and path risk,
then deep-dive a user-chosen setup. She teaches Buy & Hold as the long-horizon baseline with short
numbered guidance: enter a ticker in the Wave Viewer, use **Analysis -> Buy & Hold** to read yearly
gains/losses, the typical calendar path, and compounded growth, then keep that full-year study loaded
and use **Analysis -> Compare Symbols...** for a common-history comparison. Only after those main
steps does she teach **Analysis -> Exclude Current Range** and **View Exclusion Report** as an
advanced weak-period study. She avoids personalized buy or allocation recommendations. Proactive
starter and follow-up questions show users what Tara can do.
The suggested-question cards sit in a compact tray below the conversation. Its header chevron
slides only those cards closed or open, never the conversation or message input, and the choice is
stored with the existing user-scoped localStorage helpers so each user keeps their own preference.
Every viewer change is a signed, allowlisted action; success requires matching observed UI state and
non-empty primary and trend chart sources. Question events and browser action receipts share
`turn_id`/`action_id` values so failures and displayed responses are auditable. The full behavioral,
safety, action, audit, and evaluation contract is in `docs/TARA_INVESTOR_DISCOVERY_DESIGN.md`.

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

**Verified screen-aware answers and short-bar truth (2026-07-31).** A broad question such as
"what am I looking at?" can no longer be answered reliably from generic layout prose: Tara must
know which lower slide is active and which projection lines are actually rendered. `Chatbot.js`
now sends an allowlisted `screen_context`, built by `chatbotScreenContext.js`, containing only UI
metadata (active lower slide, current/active/historical price-chart mode, visible gold/purple
projection flags, their lookbacks, opportunity-row count, and closed-vocabulary direction summaries
for the selected/full-history normalized curves across the loaded window). It never sends the curves
or raw price series. `StockLineChart` keys its rendered-state report to symbol, inclusive window,
lookback and PE cycle; `chatbotScreenContext.js` ignores a stale report after any of those change and
uses its derived first-render fallback until the matching chart reports back.
`tara_answer_planner.py` sanitizes that snapshot and creates a verified fact ledger from the loaded
pattern. High-confidence screen-overview and bar-color questions bypass the LLM entirely: the reply
always covers the top Gain-Loss chart, the active lower slide (including visible projections on the
Price Chart), and the left table when visible. Explicit analysis of the already-loaded pattern is
also deterministic as of 2026-07-31 (details below); other open-ended questions use the selected
model provider with compact verified facts appended last to its system prompt. The release-owned
policy is identical in every environment: OpenAI `gpt-5.6-luna` is primary and Haiku 4.5 is a
classified runtime fallback only.

The direction contract is essential: `ChartData4[].pct[0]` and the bars are the UNDERLYING price
move, not direction-adjusted trade P&L. Green/up means the security rose; red/down means it fell.
For a long setup, positive/green years are profitable. For a short setup, negative/red years are
profitable and the short return is the inverse of the underlying move; positive/green years are
losing short trades. Tara's client payload therefore names these fields
`underlying_return_pct`/`upside_excursion_pct`/`downside_excursion_pct`, and both the prompt builder
and deterministic planner convert them by direction before labeling PROFIT/LOSS, MFE, MAE, win
rate, or averages. Records exclude the current-year placeholder and always state `n`. The planner
also excludes a non-zero active partial observation until its inclusive window has finished; while
that row is present it omits engine Sharpe/TWR and derives cumulative return from completed rows so
aggregates cannot silently mix cohorts. A genuinely completed current-year observation is included.
The planner also owns the inclusive display date (`start + (days - 1)`, invariant 0A), so a 6-day Jul 31 window
ends Aug 5. For an arbitrary window (`rowIndexClicked === -1`), the client derives direction from
the non-zero per-year underlying returns instead of trusting `ChartData4`'s unreliable arbitrary-
window direction field. Regression coverage: `tests/test_tara_answer_planner.py` and
`web-react/src/components/chatbotScreenContext.test.js`. The verified context now states both
the selected-history and full-history lookback labels explicitly whenever the Price Chart is
active, so a model cannot describe two visible projections without naming which sample feeds each.

As of 2026-08-01, a loaded-chart request such as "max and min for each year," "highs and lows
year by year," or "best and worst move each year" is a deterministic per-year excursion request.
Tara clarifies the plain-language terms as best move (MFE) and worst move (MAE), then reports the
direction-adjusted intrawindow values and final return for every completed observation, newest
first, with the sample size and median path values. The alias requires explicit per-year scope so
unrelated maximum/minimum questions do not get misrouted. It never substitutes the highest and
lowest end-of-window returns across the sample for MFE/MAE.

The shorter visual commands "show me max and min" and "show me MFE and MAE" mean something
different: they deterministically emit a validated `set_view` action with `show_mfe:true` and
`show_mae:true`, and React turns on those overlays for the already-loaded chart. Singular show/hide
commands can control either overlay independently. The frontend suppresses its concept-guide
auto-open fallback when one of these actions is present, so the guide cannot cover the chart the
user just asked to change. Definitions still open the guide; explicit requests to list per-year
values still use the deterministic value response above.

**Loaded full-history command and chart alignment (2026-08-01).** "Load max years," "use all
available years," and "show the full history" are resolved from the loaded symbol's verified
`full_history_years` screen value (for example, ROST = 40), never from `99`. The latter is only the
tool/API validation ceiling, not a full-history sentinel; using it generated decades of zero rows
before a younger symbol's listing, diluted aggregate statistics, left React state at a value absent
from the selector, and made the browser display the first option (5) while Tara claimed 40. Both
provider loops now override the read to the same loaded symbol/date/duration/direction at the exact
real lookback and enforce the matching `set_view` action. React independently clamps consecutive-
history actions to the symbol's known maximum as defense in depth.

A Tara `set_view` action that loads another symbol in the currently selected market preserves the
opportunity rows. `OppTable` deduplicates identical query URLs, so clearing a same-market list cannot
cause a replacement fetch and previously stranded the table at `Loading ...`. Only an actual market
change clears the rows; that change produces a distinct `OppList4` URL and a real refetch.

Direct lower-panel navigation is also provider-independent as of 2026-08-02. Requests such as
"show me the Trend Chart," "show me the stats," and "open the Price Chart" deterministically emit
an allowlisted `bottom_slide` ViewSpec and React moves the desktop lower Swiper to index 0, 1, or 2.
Explanatory questions still use Tara's concept/guide path. This replaces the former prompt-only
"swipe to slide N" limitation, which could acknowledge a request without changing the screen.

**Guidance-tooltip control (2026-08-04):** Tara deterministically maps dislike/removal wording to
`show_tooltips:false` and confusion about controls/buttons/icons to `show_tooltips:true`. The field
is boolean-validated in the same ViewSpec on the backend and frontend, then applied through
`SetTooltipSW`, the state used by the visible Tooltips switch in the upper-left toolbar beside the
settings gear. Tara names that location after changing the setting. Asking only what or where the
switch is produces an explanation without changing the preference.

When a user names a different ticker without naming another lookback (for example, ADI is loaded at
16 years and the user asks "how does ITW do?"), the target read and load inherit the current
consecutive 16-year setting instead of the tools' 10-year default. The backend enforces this for both
providers and caps the final action to the target card's available completed record when it is
smaller. An explicit N-year or max-history request still overrides inheritance. The canonical
`/v1/analyze/<symbol>` route also resolves the matching market-specific detection pair for custom
lookbacks (`16/14` for the S&P symbol grid), rather than combining `years=16` with the legacy
10-year default floor of `9`, which returned an empty setup list despite valid 16-year patterns.

Ordinal opportunity commands are provider-independent as of 2026-08-01. `TableBox` publishes the
exact rows visible after active-list selection, text filtering, and user sorting back to `App`, and
`Chatbot.js` sends that ordered snapshot (not merely the raw OppList4 order). The appserver parses
direct commands such as "load the top one," "open row 2," and "load the 3rd one on the list" before
either model runs, selects the 1-based row deterministically, validates its ViewSpec, and returns a
`load_opportunity` action. React applies that setup as the equivalent of a row click, retains the
opportunity table's string lookback and PE phase, and highlights the requested visible row. This
prevents prompt segmentation, conversation resets, model counting, or provider choice from making
Tara ask which market when the table already supplies the answer.

TradeWave gateway/viewer windows are inclusive CALENDAR days and count the entry date as day 1. At
the one appserver boundary, the gateway converts public `days_out` to the legacy analytics offset
`daysOut = days_out - 1`; opportunity and stored-pick offsets are converted back to inclusive labels.
The shared API scan-core cache uses its `v2` namespace for this normalized contract, preventing a
warm pre-normalization entry from briefly resurfacing the old offset after deployment.
Thus a displayed Aug 3-Aug 19 pattern is 17 days but every `ChartData4` and ML calculation receives
16, exactly like the React viewer. Finally, `BarChart` now emits one MFE and one MAE array slot for
every year label. An all-zero placeholder uses `null` overlays instead of omitting its entries, so a
pre-history/current-year row can no longer shift real excursion bars onto decades-old labels.

The public 100-Year Pattern is one exact exhibit, not a general indices-market entitlement.
`appserver/appserver/featured_patterns.py` owns its canonical identity: market `5`, SPX, the
latest/current PE+2 September 27 occurrence, 295 inclusive display days (`daysOut=294`), the
completed cohort encoded as the string `pe2-N`, and no cutoff year. `getChartData4` bypasses only
the normal market, date-lock, and years-cap checks when every field matches; every near miss follows
the caller's normal subscription rules. An active partial occurrence remains visible but is excluded
from completed aggregates until its inclusive window ends. Tara resolves book/signature-pattern
requests deterministically before either model provider, loads that same canonical ViewSpec, and
states the completed `n`, entry-year range, historical record, and current-row status.

Tara can also compare any explicitly named security with the 100-Year Pattern's dates and PE+2
position. This does not widen the public SPX entitlement. Tara resolves the ticker through the local
`ResolveSymbol` contract, uses descriptive words such as `index` or `crude oil` to disambiguate
cross-market duplicates, and defaults an otherwise unqualified duplicate ticker to the representative
US-stock market when exactly one such match exists. It derives the security's completed PE+2 count
from `StockMetaData` and calls
`ChartData4` with September 27 through July 18 and `comparison_direction=long`. The reply and signed
view action are built only from the effective request and statistics echoed by that response.

Best-time-to-buy and named-symbol historical-weakness questions use the exact `OppBySymbol` data
behind the desktop Best Waves selector. `OppBySymbol` now echoes the effective market, symbol,
lookback, minimum profitable years, and mode after entitlement clamping. Tara uses the exact Wave
Viewer lookback and cycle mode when querying those rows. She searches Long rows from one week ago
through year-end and selects the highest-Sharpe qualifying row for buy-timing research, and uses the strongest Short row for a
weak-period question, then preflights the selected row with `ChartData4`. A mismatched effective
request produces no action or success claim, and an empty selector is reported as no qualifying
Best Wave at that setting.

**Segmented prompt loading + verified loaded-pattern analysis (2026-07-31).** The previous prompt
path appended the entire roughly 89,000-character `chatbot_knowledge.txt` plus up to 30 opportunity rows,
every yearly row, and every `ChartData4.stats` field to every model call. Worse, Anthropic caching
wrapped that whole changing string in one cache block, so changing the loaded symbol or active screen
invalidated the huge prefix. The replacement has three ordered layers:

1. `chatbot.py`'s stable behavior/tool contract is the first system block, with the cache breakpoint
   at its end. `AI_tools_appserver.send_claude_messages` now accepts ordered system blocks and applies
   `cache_ttl` to that explicit breakpoint (`5m` default; `1h` supported). Topic and live-context
   changes therefore preserve the stable-prefix cache, including across tool-loop rounds. Provider
   responses log only the input/cache-create/cache-read/output token counts for operational QA.
2. `tara_prompt_context.py` parses the KB once by `##` heading and selects at most three complete,
   relevant sections (16,000-character ceiling) for the current question. It includes yearly rows
   only for specific-year/bar/outlier/MFE/MAE questions and opportunity rows only for table/list/rank/
   screen questions (maximum 12). The React payload sends a derived-stat allowlist only, and the
   server repeats that allowlist at the trust boundary; raw price levels, moving averages, volume,
   and nested filing history do not enter Tara context. The old `last_price`/`last_price_date` fields
   were removed as well.
3. Live loaded-pattern identity, selected derived stats, exact rank when available, allowlisted screen
   state, and the positively stated calendar-day/short-return fact ledger remain the final dynamic
   block, where they have maximum recency.

Measured with the real tool-enabled prompt and representative loaded/screen questions, model-bound
system content fell from roughly 117K-121K characters to 31K-34K characters (about 72%-74% smaller;
character count, not a token estimate). Live dev provider usage then confirmed the cache boundary:
the first identical knowledge request created 8,854 stable-prefix cache tokens; the next read all
8,854 with zero cache creation. A later KB-suffix edit still reused those same 8,854 cached tokens.
An explicit request such as "analyze this pattern," "how strong is this," "what stands out?," or
"what do you think of this opportunity?" does not call the model when the referenced pattern is
already loaded. `tara_answer_planner.py` now uses an intent-focused evidence read rather than one
generic metric dump. As of 2026-08-01, broad analysis is a compact decision brief: exact inclusive
calendar window; cohort type, year span and `n`; direction-adjusted hit rate, gross mean and median;
Sharpe explicitly labeled as cross-year ending-return consistency; average winner/loss payoff;
median MFE, median MAE, worst MAE and worst ending result; one material current/robustness issue;
one targeted next check; and a gross-cost/non-forecast scope line. MAE is described as the adverse
move from entry, not peak-to-trough maximum drawdown, and Tara never converts MFE/MAE into a target
or stop. Missing excursion fields stay missing rather than becoming a false `0%` path claim.

For an eligible US-stock/ETF user, that deterministic brief now adds a server-derived,
current-condition ML section. The browser cannot supply or override this evidence: `chatbot.py`
removes any incoming `wave_viewer.ai_analysis`, then calls the scorer callback registered in
`current_app.extensions['tara_ai_analysis_context']`. The callback reuses the web product's
`_ml_check_access`, `ml_score_resource_ids`, daily Redis keys, and ML scorer. A 10-90-calendar-day
pattern receives a like-for-like AI Win Probability, PredR, and PMFE in Tara's prose; the composite
AIS number is intentionally omitted there because it has no direct standalone interpretation. AIS
remains available in the opportunity table and its dedicated explainer. Tara compares AI Win
Probability with the historical win rate only because both describe the exact same window. These
names remain distinct: the former is a current-condition model estimate and the latter is the
observed share of profitable completed years.

TradeWave supports both scorer contracts. V2 provides exact-window scores through 90 calendar
days using its 59-feature models and metadata-free `/score` response. V3 provides the 62-feature
contract, complete scorer provenance, and recalculated duration comparisons. Feature construction
remains entirely inside the scorer. In `auto` mode TradeWave detects the contract from `/health`;
operators can pin either version with `TW2_ML_SCORER_MODE=v2|v3`.

For a window longer than 90 calendar days, Tara requests bounded 30-, 60-, and 90-calendar-day
readings from the same entry date and direction and presents them as an `AI-calibrated outlook`.
The copy leads with the available probabilities and predicted returns, identifies which horizon has
the highest probability and predicted return, and pairs them with the complete-window historical
analysis without negative limitation-led language. The legacy scorer still accepts the
analytics-engine offset, so `tara_ai_analysis.py` converts those
inclusive calendar labels to `daysOut=29/59/89`; it never adds a day to an end date. Independent
tiers are requested in parallel and cached under the same daily keys as the opportunity table.
Current-condition scores are suppressed more than five calendar days before entry so inputs are
not presented stale, and a new entry-time score is not calculated after entry because post-entry
data would contaminate the pre-entry comparison. Missing/provider-failed results remain unavailable,
never numeric zero. The historical brief remains available if enrichment fails.

AI-horizon why-questions are also deterministic. `tara_answer_planner.py` recognizes variants such
as "why does AI only do the first 90 days?" and explains that the models are trained and calibrated
for 10-90-calendar-day seasonal horizons, then shows how the 30/60/90 current-condition outlook and
the complete-window historical record fit together. This route runs before provider selection and
does not wait for a scorer call.

When a chart pattern is loaded, terse commands such as `analyze`, `analyze this`, and `analyze it`
are deterministic analysis intents. They must take the same enriched brief path as `analyze this
pattern`; they do not fall through to an LLM provider or return its older generic summary.

Tara also owns two deterministic product-education intents. Seasonality-value prompts (`convince me
I should use seasonality`, `why should I use seasonality`, comparisons with normal indicators) use
the loaded pattern as a concrete demonstration: exact inclusive calendar window, observed record
with `n`, flexible 10/12/15/20/25/maximum-history testing, historical base rate versus the separate
AI Win Probability concept, and visible guide links. Strategy-building prompts (`help me come up
with a winning strategy`, `turn this into a testable strategy`) produce a positive research process:
fixed rules, robustness across history/date/hold/PE cohorts, payoff and MFE/MAE failure evidence,
current-condition context, and unchanged forward tracking. Both routes bypass the model and live ML
scorer so the answer is immediate, stable, HTML-card formatted, and cannot regress into a defensive
essay. They do not claim Sharpe demonstrates statistical significance or above-chance results.

Recent comparisons use the latest five completed observations versus the earlier non-overlapping
sample, and are phrased descriptively ("weaker in this sample"), never as proof of regime decay.
The React context also labels a loaded window `scanner` versus `user_defined`; scanner-selected
analysis discloses that its in-sample statistics are selection-sensitive because the opportunity
engine searched many candidates. Gross results disclose unmodeled execution costs/taxes and, for
shorts, borrow costs/dividends owed. Focused follow-ups such as "has it weakened recently?," "what's
the catch?," "is one year carrying it?," "why is it short?," a specific historical year, and "why
does it rank here?" return only the requested evidence slice. Break-even rate, cumulative compounding,
dispersion and streak detail are no longer forced into every broad answer.

The same planner labels PE-cycle samples as cycle observations rather than consecutive years, uses
the direction-specific live Trend score, and translates Trend Alignment into the concrete comparison:
roughly the last one to two weeks of price movement versus the loaded seasonal direction (upward for
a long, downward for a short). `Aligned` means recent movement confirms that direction; `Against`
means it has not been moving strongly in that direction; `Neutral` means no clear confirmation.
This is current-momentum context, not a historical pattern score or forecast. `ChartData4` and
`StockScoreBatch` carry an explicit score-availability bit; a provider/configuration failure is
rendered as unavailable rather than the legacy numeric `0` fallback. During rolling deploys, a
legacy all-zero current/prior score set without the bit is also treated as unavailable. The planner
also explains when TWR materially exceeds Sharpe. TWR applies the Sharpe-style
return-to-dispersion calculation to each completed observation's direction-adjusted MFE rather than
its ending return; it does not use final close-to-close gains/losses. When a losing finish first had
meaningful favorable MFE, Tara surfaces the year, MFE, final result, and giveback so an endpoint-only
record cannot hide exit sensitivity. It also flags an
estimated earnings date inside the current occurrence, and states whether the selected-history and
full-history normalized seasonal curves support or oppose the loaded direction. React derives only
those closed-vocabulary curve-direction labels (`supports` / `against` / `flat` / `unknown`); the
0-100 curves and raw prices never enter Tara's payload. A loaded "should I trade it?" request is also
handled deterministically: Tara says she can evaluate but not decide the trade, gives the strongest
historical support and counter-signal, and includes the disclaimer. All analysis is explicitly
historical, makes no forward claim, and is not a trade recommendation. Questions about a different
symbol stay on the policy/tool path, but an explicitly named ticker is authoritative over the loaded
chart and pronouns. A bare cross-symbol request inherits the current consecutive lookback; the tool
layer caps it to the target symbol's `StockMetaData` history, forces the read and view action to the
same effective lookback, and anchors the recurring setup to the current occurrence year.
`/v1/analyze/<symbol>` passes the matching market-specific `year1` and `year2` detection grid pair,
so a non-default lookback cannot silently resolve through the legacy 10-year band. Investor-grade
outperformance remains a declared gap:
Tara must not claim that a long window beats buy-and-hold until the same-security and market
benchmarks are passed with verified matching cohort, exposure and return semantics.

Trend score level and Trend-arrow movement are separate facts. For a Long pattern, alignment uses
the current Trend Long score; for a Short pattern, it uses the current Trend Short score. The arrow
compares that score with its previous available reading: green up means higher, red down means
lower, and white/gray horizontal means unchanged. Therefore an Aligned score such as Trend Long 69
can correctly have a red down arrow. Tara handles arrow questions deterministically and must never
translate a red arrow into `Against` or bearish meaning when the current score remains Aligned.

As of 2026-08-01, broad loaded-pattern analysis also separates three contexts that must never be
blended: the aggregate cohort, an individually selected historical Price Chart year, and the dated
current/next occurrence. Tara labels a historical chart year as one path, names that year's PE
phase, and states that the aggregate statistics are not statistics for that one year. Occurrence
timing is derived from the literal inclusive CALENDAR window: upcoming replies give the exact start,
days until start, and inclusive end; active replies give the calendar day within the window, end,
and days to end while excluding the partial live row; completed replies state whether the finalized
entry-year row is present in the completed `n`. Occurrence status never shifts a weekend entry to
Monday. Reminder delivery may move separately, but the analytical window does not.

Direct lower-carousel commands are deterministic UI actions: Trend Chart, Wave Stats (including
“show me the stats”), AI Scores, and Price Chart map to the semantic
`bottom_slide=trend_chart|wave_stats|ai_scores|price_chart` contract. `DesktopLayout` owns the
physical Swiper indices and acknowledges the exact semantic slide before the signed action can
complete. These commands do not reload the symbol or clear the opportunity table. Concept questions
such as “what does the Trend Chart show?” remain explanations and do not move the viewer.

PE context is anchored to the occurrence's ENTRY year, including a cross-year window that remains
active in January. With consecutive years loaded, Tara identifies that occurrence phase and suggests
the exact same symbol/direction/date/duration in the matching PE cohort. With a PE cohort already
loaded, she suggests the exact same window in consecutive years for broader context. A non-current
phase explicitly names both the occurrence phase and the current year's phase; a loaded-cohort versus
occurrence-phase mismatch is flagged rather than rationalized. Every compact PE label includes its
plain-English phase (for example, `PE+2 (midterm)`), and a loaded PE sample converts observations to
its calendar footprint: 10 contiguous PE+2 observations represent a 40-calendar-year cycle lookback,
not 10 consecutive years. The suggested comparison is an explicit user-invoked link. React dispatches
that link through the same cycle transition used by the Wave Viewer selector, so switching to the
matching PE phase or back to consecutive years preserves each view's saved date and lookback. Tara
never says the alternate cohort is stronger or weaker until it has been loaded. Any comparison must
preserve the exact inclusive window and state `n` for both cohorts. Regression coverage includes
current matching PE, non-current PE, mismatched PE, upcoming, active, completed, cross-year active,
historical-price-chart, PE-span, and cycle-action cases in `tests/test_tara_answer_planner.py` and
`web-react/src/components/viewerCycleState.test.js`.

The same evidence brief is rendered as semantic HTML rather than one `<br>`-joined paragraph.
`tara_answer_planner.py` wraps each labeled line in a `tara-analysis-section`; `Chatbot.css` gives
those sections spacing, a subtle theme-aware surface and border, a separate accent-colored heading,
tabular numerals, and a quieter scope/disclosure treatment. This keeps the detailed analysis
scannable inside the narrow desktop chat column without removing the evidence the user requested.
Other short Tara answers retain their compact normal message rendering.

**GPT-5.6 Luna release policy (2026-08-04).** Deterministic planner answers still run first and never
enter a provider route. Every remaining model-bound turn starts on the tracked primary provider and
model: OpenAI `gpt-5.6-luna`. `tara_model_router.py` contains no authenticated-user bucket,
percentage canary, or environment default. `TARA_OPENAI_CANARY_PERCENT` is retired and absent during
normal operation. Missing `OPENAI_KEY` or an invalid tracked primary policy fails deployment
preflight and does not silently select another model. `openai_tools_appserver.py` uses the stateless
Responses API (`store:false`) with `gpt-5.6-luna`, low reasoning effort, low text verbosity, a bounded
2,048-token output ceiling, and an explicit cache breakpoint at the end of the same stable prompt
prefix used by Anthropic. Four stable cache-key shards share that prefix without concentrating all
requests on one routing key.

`tara_gateway.run_chat_with_openai_tools` carries Responses function calls and outputs forward
explicitly but executes them through the same `_execute_tara_tool` path as Haiku. Thus gateway reads,
OppList4/table interception, result trimming, ViewSpec validation, UI actions, and the final truth
guards do not vary by model. A classified OpenAI request, API, connection, or adapter failure discards
unreturned local UI actions and retries the full turn on Haiku; configuration failures do not fall
back. Tara exposes only the usual generic error if both runtime providers fail.
Question-log rows record `deterministic`, `openai`, `anthropic`, or `anthropic_fallback`, while provider
usage and turn-completion logs contain the actual provider, exact model, token/cache counts, and safe
failure category but no prompt text or provider response body. `/chatbot/runtime-fingerprint` and
`ops/verify_tara_release.py` expose only the release SHA, tracked model policy, prompt and planner
hashes, frontend bundle hash when supplied, and non-secret configuration hash.

**Gateway restart/service-login invariant (2026-08-01).** The gateway keeps both
`SERVICE_API_KEY` and its downstream appserver JWT in process memory. A manual appserver-only restart
once loaded the current secrets file on the appserver while the long-running gateway retained an
older key; `/healthz` remained 200, but every Tara read failed at `/login/api` and the model replied
"temporarily busy." The tracked `tradewave-apiserver.service` now has
`PartOf=tradewave-appserver.service` plus ordering after it, so an explicit appserver restart also
restarts the gateway. Its `ExecStartPost` runs a fresh, credential-safe `_get_token()` canary; a key,
HMAC, database-row, or endpoint mismatch now fails service activation instead of presenting a false
healthy state. The existing deployment path already restarts APP then API/MCP; this closes the manual
restart gap.

Regression coverage: `tests/test_tara_prompt_context.py`, `tests/test_ai_tools_prompt_cache.py`, and
`tests/test_tara_answer_planner.py`, plus `tests/test_tara_openai_canary.py` for routing, request,
cache-breakpoint, and shared-tool-loop behavior.

(Source: `appserver/appserver/{chatbot,tara_prompt_context,tara_answer_planner,tara_gateway,AI_tools_appserver,openai_tools_appserver,tara_model_router}.py`,
`web-react/src/components/{Chatbot,chatbotScreenContext,BarChartPopup,GettingStartedPopup}.js`,
`apiserver/{auth,tiers,provision_chatbot_key}.py`, `config.py`, `docs/TARA_GATEWAY_INTEGRATION.md`; dev .176.)

---

## 8. Deploy / ops / cron

**Staging/production deploy = `bash ops/deploy.sh {staging|prod}`** from dev after
full release qualification. Per env: pre-flight (`TW2_PUBLIC_HOST` set on both
boxes, else abort) -> per tier `git pull --ff-only` + `pip install -r
requirements.txt` (mandatory - a missing dep crash-loops workers into a 502) +
web-box `ops/migrate.sh` + idempotent lifecycle cron install + affected service
restarts + `is-active` -> exact React symlink-swap -> nginx reload. Full detail
+ restart-matrix: `ops/OPERATIONS.md`.

**Git/dev invariant:** agents promote commits, never arbitrary dirty files. Every Codex
or Claude task uses a dedicated current-main branch/worktree and pushes its intended
commit. Ordinary completion uses the fast dev loop: focused affected-surface tests, one
required build, a short final activation lock, a live smoke of the changed behavior, and
a non-forced main update. Full regression, release manifest, staging inventory, broad
account-tier gates, snapshots, and rollback rehearsal begin only when staging is requested.
Claude and Codex may develop concurrently; only the brief dev activation and environment
promotions are serialized. `/home/flask` is operational, not a scratchpad. Canonical
procedure: `.claude/skills/tw-git-release-workflow/SKILL.md`.

**Dev React activation invariant:** the Flask app resolves its React index from the
repository root selected by `/home/flask/.tw2-app-current`. A fast-dev activation must
therefore point `.tw2-app-current` at the complete candidate root and restart
`tradewave-web`; changing only `/home/flask/web-react/build` can leave the running app
serving an index that references missing or stale bundles. Keep the convenience build
symlink aligned with the candidate, but never treat it as the runtime switch by itself.

**Coordination/release-state invariant:** `/var/lib/tradewave/release-state/` is
initialized by `ops/init_release_state.sh` as `flask:flask` mode `0750`.
Routine dev uses only the atomic `dev-activation.lock`, acquired after testing/building
and held through the brief ref check, activation, changed-behavior smoke, main update, and
parity proof. A full named manifest is created only for staging/production qualification
and then records ownership, immutable artifacts, broad gates, target drift, approvals,
snapshots, and rollback.

**Tara immutable app release invariant (2026-08-04):** a scoped Tara-only backend promotion uses
a clean detached worktree under `/home/flask/.tw2-releases/<sha>` and atomically points
`/home/flask/.tw2-app-current` at it. Systemd drop-ins make both `tradewave-appserver` and its coupled
`tradewave-apiserver` load that exact source tree. `ops/activate_tara_release.sh` snapshots the prior
source/config/unit state, runs fail-closed credential and fingerprint checks, performs deterministic
and model-bound live gates, and writes tested rollback and roll-forward scripts. The dirty developer
checkout is never reset, stashed, switched, or used as the artifact. For a backend-only Tara diff,
the active React artifact, homepage, 100-Year Pattern page, and nginx configuration remain untouched.

The APP deploy pre-flight enforces the supported low-traffic environment baseline
of 2 CPUs / 4 GB for both staging and production. Production approval for that
baseline was recorded by the owner on 2026-08-03. Capacity scales above the
baseline in response to observed traffic. Host, identity, clean-tree, disk,
service, route, and post-deploy health gates remain enforced in every environment.

**React deploy = SYMLINK SWAP** (NOT a dir copy, NOT git pull): `build` is a
symlink to `releases/build-<commit>`; deploy rsyncs to a new release dir then
`ln -sfn`; `build-previous` = instant rollback (`ln -sfn "$(readlink build-previous)" build`).
(`ops/deploy.sh`, `project_tw2_react_deploy.md`.)

**Environment favicon = a root static artifact, not an environment-specific React
bundle.** `ops/regen_site.sh` publishes `/var/www/tradewave/favicon.png` from the
explicit `TW2_ENV` mapping (dev white, staging black, production brand colour), and
`ops/assemble_developer_portal.sh` applies the same mapping to the developer portal.
Every surface already links the root-relative `/favicon.png`.

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
`m_daily_ai_pick_social.py --send` (07:10 weekdays, after the homepage writer),
`m_daily_pick_close_social.py --send` (03:00-06:59 UTC Tue-Sat, only after
the appserver EOD completion marker, no post when nothing closes),
`update_news_quotes.py` (every min), SMN emails, daily-AI-pick email,
`web/mailerlite_lifecycle.py --limit 15` (every minute), `expire_trials.py`
(04:15), appserver EOD `update_client2.py` (03:05-05:05 UTC Tue-Sat after the
keyprovider's 20:03 ET EODHD load), ticker regen (02:00 + hourly 09-16).
The MailerLite worker takes a Postgres advisory lock, reclaims ten-minute stale
claims, and is a no-write operation unless production explicitly enables it.
The X worker is also inert outside production and until its independent outbound
flag is enabled. Routine deploy installs both workers' canonical cron entries.
App box:
DB backup 03:30 + weekly restore drill. (`make_bulletproof.sh`, `OPERATIONS.md §16`.)

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
  checkout; Stripe Billing Portal for cancel/manage. A
  `customer.subscription.deleted` event is allowed to downgrade the web tier
  only when its subscription ID matches `users.stripe_subscription_id`, or when
  the event has a recognizable web/EOD price and no conflicting current
  subscription. A delayed delete for an older subscription is ACKed 200 without
  mutation and audited as `stale_subscription_deleted_ignored`; an event that
  cannot safely be classified is audited as
  `unclassified_subscription_deleted_ignored`. This prevents an out-of-order
  delete from downgrading a current payer or enrolling that payer in winback.
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
- **Tiers:** explorer/navigator/analyst/strategist. `tier_compat` maps explorer->'1',
  navigator->'2', analyst->'4'/'5', strategist->'6'/'7'. Current consumer prices are
  Explorer $0; Navigator $19/mo or $168/yr; Analyst $47/mo or $399/yr; Strategist
  $129/mo or $1,188/yr. Stripe metadata is price-authoritative. Ladder A is the
  decided entitlement: AI starts at Analyst; Explorer and Navigator have no permanent
  AI scoring. Navigator (added 2026-06-25) unlocks Dow+NASDAQ+S&P (ids 0,1,2) and
  custom start dates at legacy level '2'. `users.tier` CHECK + the legacy_wp_level sync
  trigger were widened for it in migration a1f4d2c9e7b3. The reconciled cross-surface
  matrix is `docs/PRICING_QUOTA_SPEC.md`; business decisions are in
  `docs/marketing/PRICING_STRATEGY.md`.
- **MailerLite level segmentation + durable lifecycle automation (rebuilt
  2026-07-13):** LEVEL groups describe current access only and remain exactly
  one of `explorer`, `navigator_monthly/yearly`, `analyst_monthly/yearly`, or
  `strategist_monthly/yearly` (`config.MAILERLITE_LEVEL_GROUPS`). LIFECYCLE
  groups are separate, mutually exclusive automation triggers:
  `trial_started`, `trial_ended_explorer`, and `winback_explorer`
  (`config.MAILERLITE_LIFECYCLE_GROUPS`). The shared Explorer LEVEL group must
  never trigger a lifecycle automation because it contains first-time free
  users, post-trial users, and former payers.

  Critical signup and web-billing paths use the durable
  `mailerlite_lifecycle_events` outbox (migration `c7a9e2f4d6b8`). A new signup
  atomically queues an immediate reconcile plus a reconcile scheduled for
  `reverse_trial_ends_at`. Paid checkout/subscription events atomically queue a
  clear or reconcile so a purchase removes trial/winback triggers. A valid
  current-subscription deletion changes the user to Explorer and queues the
  winback reconcile. Dedupe keys make callback refreshes and Stripe retries
  harmless. MailerLite HTTP is outside the request transaction.

  The once-per-minute `web/mailerlite_lifecycle.py` worker derives the desired
  state from the CURRENT User row, not the historical event payload; this makes
  delayed events converge safely. It removes old lifecycle groups before adding
  the one desired group, verifies final membership, never reactivates an
  inactive/unsubscribed subscriber, retries failures with bounded backoff, and
  recovers stale claims. Access-level reconciliation follows the lifecycle
  transition. `reconcile` and `clear_paid` are permanent storage IDs.

  Production writes require both `TW2_ENV=prod` and
  `MAILERLITE_OUTBOUND_ENABLED=1`, plus all three lifecycle group IDs. Until
  then the outbox remains durable but the worker consumes nothing. Safe launch
  order is deploy with writes disabled, run
  `ops/audit_stripe_subscription_identity.py` dry-run then `--apply`, run
  `ops/backfill_active_reverse_trial_lifecycle.py` dry-run then `--apply`,
  finish/test/activate all three MailerLite automations, preview the outbox, and
  only then enable writes. The backfill schedules only the post-trial reconcile
  for trials already active at deployment; it never drops an existing user into
  the middle of the day-0 sequence and never touches expired Explorers. Full
  commands and emergency stop: `ops/OPERATIONS.md` §3a.

  Only managed LEVEL and LIFECYCLE groups are touched; SMN/newsletter/webinar
  groups are outside this reconciler. A direct SaaS-created subscriber carries
  `status:"active"` to avoid MailerLite double opt-in; the public SMN form keeps
  its own confirmation behavior. The older one-time level audit remains
  `ops/migrate/reconcile_mailerlite.py` (dry-run default, `--apply`).
- **GA4 server-side tracking (Measurement Protocol, built and verified in the integration branch; not yet deployed):** `web/ga4_mp.py` fires `begin_checkout`/`purchase`/
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
- **Dunning (Stripe Smart Retries final-notice email, built for GTM playbook CARD W1.3 and verified in the integration branch; not yet deployed):** Stripe Dashboard-side Smart Retries
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
- **Trial-activation Postgres signal (`ai_score_viewed`, built for GTM playbook CARD W1.4 and verified in the integration branch; not yet deployed):** `users.first_ai_score_viewed_at`
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
   admin-granted-trial sweep and never touches reverse trials). A MailerLite
   outbox row may be scheduled for the same cutoff, but it changes email-group
   membership only and never grants, expires, or mutates product access. The paired
   React default-security fallback (App.js falls back to the first accessible
   security) is what makes a DJ30-only list safe - do not remove it.
2. **Resource keys are permanent:** keys `'0'..'16'` are stable IDs (Korea 14/15
   removed leaving a hole; crypto stays 16). Never renumber - persisted data keys off them.
3. **Stripe webhook ACK 200** for foreign/unmatched customers (shared account).
   Never revert to 5xx.
4. **FREEZE legacy Stripe price cleanup** - never archive a price with an active sub.
5. **No em-dashes** in TradeWave/SMN content (use ` - `). Date-range LABELS use
   en-dash via `tw_dateformat.py`; prose uses words; slugs stay ASCII.
6. **A substantive application-change request includes fast clean integration and verified
   dev activation unless the owner explicitly says local-only or do-not-deploy.** Focused
   tests, the affected build, a short lock, and a changed-behavior smoke finish dev.
   Full regression and release-manifest gates start only on a plain staging-deploy request,
   which authorizes the sole manager to execute the complete gated staging workflow.
   Never touch production or TW1 directly - author
   production commands and the operator runs them. Read-only inspection of `.151` is allowed.
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
17. **Stripe deletion must match current web state:** never downgrade a user from
    `customer.subscription.deleted` when the deleted subscription ID conflicts
    with `users.stripe_subscription_id`. Missing/unrecognized price plus no
    matching current subscription is unclassified and must also be ignored.
    Both cases ACK 200 and write their dedicated audit action.
    Terminal deletes resolve a matching stored web/API subscription identity
    before consulting Stripe pricing, then accept an explicit `product_line`
    from the event. If a different current identity is stored and an ambiguous
    delete cannot be classified because Stripe pricing is unavailable, preserve
    access and ACK 200 through the unclassified-delete audit path. A stale or
    archived price must never turn a safely ignorable delete into a retry storm.
18. **MailerLite lifecycle triggers are not access groups:** the shared Explorer
    LEVEL group must never trigger onboarding or winback. Only the three
    environment-configured LIFECYCLE groups may trigger those automations.
    Every app-originated MailerLite mutation requires the explicit prod-only
    outbound gate; `reconcile` and `clear_paid` are permanent outbox storage IDs.
19. **GA4 server-side tracking (`web/ga4_mp.py`) must never affect checkout/webhook/
    signup, even if GA is fully down** - `send_event()` fails open internally, but every
    call site is ALSO locally wrapped in its own try/except (see §9), because each site
    sits inside a route/handler whose own broad exception handler would otherwise turn
    an analytics bug into a false checkout failure (`stripe_create_checkout`) or a
    wasted Stripe-retry that the webhook's event_id dedup would then silently swallow
    (`/webhooks/stripe`). Never remove either layer of wrapping when touching this code.
20. **`@require_login` (`web/app.py`) always REDIRECTS (302 to WorkOS hosted signup) an
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
21. **Stripe `invoice.payment_failed`'s `next_payment_attempt` field being `null` does
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

- `docs/RELEASE_PROCESS.md` - mandatory cross-agent fast-dev and qualified-release
  policy: focused dev completion by default, then full artifact, approval, runtime,
  browser/contract, handoff, and rollback gates when staging/production is requested.
- `ops/release-risks/` - dated, reverified release hazards and out-of-band environment
  evidence. These records seed a release manifest but never replace current read-only checks.
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
- TW2 prod: the May 2026 `tw2-prod.trxstat.com` placeholder status is historical.
  The current production hostname and deployment target is `tradewave.ai`; do
  not use the placeholder for launch verification. Remaining verification
  overlaps gaps C/D + the prod-app service-account.

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
  non-atomic pairs remain in ~20 cache writes (orphan-key risk only). Dead-file inventory:
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

**G. 2026-07-24 Wave Viewer regression handoff - SOURCE COMPLETE; DEV
BUILD/RETEST REQUIRED.** The source state used by the Windows regression work is
captured on branch `codex/wave-viewer-regression-loop-20260724` with its durable
workflow in `docs/testing/WAVE_VIEWER_LOOP.md`.

- The opportunity filter is a two-source state machine: its one valid day-range
  segment selects a server-side OppList4 membership set, while other predicates
  filter in the browser. AI predicates use scores anchored to the baseline
  opportunity set. They may remove rows from the active server range but must
  never add rows outside it, and token order must not change membership.
- Incomplete or invalid tokens retain the last valid rows with explicit
  guidance. Unknown bare words are invalid while ticker-shaped bare searches
  remain supported. Filtering is derived synchronously from the current input,
  so a previous result cannot remain visible during a delayed effect window.
- Sorting is presentation-only. A Win% or PredR header click must never rewrite
  the filter, server range, recurrence, or source membership. Stale async
  responses cannot override a later filter clear or recurrence reset, and a
  source-changing transition must show matching rows or an honest bounded
  Loading state.
- The Wave Viewer and Opportunity Table own independent recurrence state. Viewer
  cycle or viewer-years changes, including deep links and reloads, must never
  overwrite the table's saved years/partial pair.

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
