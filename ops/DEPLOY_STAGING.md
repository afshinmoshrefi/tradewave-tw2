I have everything. Now I'll compose the inventory.

---

# TW2 Pre-Deploy Inventory

**Source box:** `/home/flask` (dev, 192.168.1.176). Generated 2026-05-14. Inventory only — no recommendations.

## Current deployment addendum (2026-07-13): MailerLite lifecycle

This addendum supersedes the older MailerLite signup, migration-head, and
Stripe-deletion notes in the May 2026 inventory below.

The application now uses `mailerlite_lifecycle_events`, added by Alembic
revision `c7a9e2f4d6b8`, as a durable outbox. New signup and web-billing writes
atomically enqueue the permanent storage event types `reconcile` or
`clear_paid`. `web/mailerlite_lifecycle.py` later derives the desired state from
the current User row and reconciles one of three mutually exclusive MailerLite
automation trigger groups: `trial_started`, `trial_ended_explorer`, or
`winback_explorer`. The existing LEVEL groups remain access segmentation only.

Keep writes disabled throughout staging. Lifecycle IDs may remain blank there:

```
TW2_ENV=staging
MAILERLITE_OUTBOUND_ENABLED=0
```

Before the production deploy, configure the production web box with the real
credential and all three trigger-group IDs, but leave writes disabled:

```
TW2_ENV=prod
MAILERLITE_API_KEY=<connect API credential, or existing MAILERLITE_TOKEN fallback>
MAILERLITE_TRIAL_STARTED_GROUP_ID=<7-day new-signup trigger group>
MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID=<post-trial Explorer trigger group>
MAILERLITE_WINBACK_GROUP_ID=<former-paid Explorer trigger group>
MAILERLITE_OUTBOUND_ENABLED=0
```

`config.py` requires both a truthy `MAILERLITE_OUTBOUND_ENABLED` and
`TW2_ENV=prod`. Dev and staging are therefore no-write even if they share the
account token. Missing lifecycle group IDs also stop the production worker
without consuming the outbox.

Routine `ops/deploy.sh` runs `ops/migrate.sh`, installs the canonical cron with
`ops/install_mailerlite_lifecycle_cron.sh`, then restarts `tradewave-web`. The
same cron is installed by `ops/staging/make_bulletproof.sh`:

```cron
* * * * * { test -r /etc/tradewave/secrets.env && set -a && . /etc/tradewave/secrets.env && set +a && cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --limit 15; } >> /var/log/tradewave/mailerlite_lifecycle.log 2>&1
```

Before any lifecycle backfill, run the Stripe subscription-identity audit. It
is dry-run by default, retrieves current Stripe Product metadata, and pages all
Stripe subscriptions for each affected customer. Resolve all blocking rows
before applying in production while outbound remains disabled; `--apply`
requires explicit `TW2_ENV=prod`:

```
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py'
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/audit_stripe_subscription_identity.py --apply'
```

It preserves confirmed web/EOD and unlabelled legacy web subscriptions, and
never clears a paid web tier. A matching single EOD identity can be restored
atomically with the API move; incomplete, paginated, mismatched, shared, or
multiple-candidate evidence refuses the whole apply. Then, for users already inside an active
reverse trial when the migration lands, preview and schedule only their
trial-end reconcile:

```
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/backfill_active_reverse_trial_lifecycle.py'
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && /home/flask/venv/bin/python /home/flask/ops/backfill_active_reverse_trial_lifecycle.py --apply'
```

The script does not enroll these users midway through the day-0 automation and
does not touch expired Explorer accounts. Safe activation order is: deploy
staging with writes disabled, verify; deploy prod with writes disabled and all
three group IDs configured; audit and repair Stripe subscription identity; run
the backfill dry run and apply; finish, test,
and activate all three MailerLite automations; preview due outbox rows; only
then set `MAILERLITE_OUTBOUND_ENABLED=1` on prod and restart
`tradewave-web`. Enrolling people before an automation is active can lose its
group-join trigger. Emergency stop: set the flag to `0` and restart web; the
next cron is disabled and queued rows remain durable. One in-flight batch can
finish at most 15 rows, so remove the lifecycle cron and terminate only that
worker process if an immediate stop is required.

Stripe deletion is also fail-closed. `customer.subscription.deleted` can
downgrade a web user only when the event subscription matches
`users.stripe_subscription_id`, or when a recognizable web/EOD price has no
conflicting current subscription. An old conflicting deletion is ACKed 200 and
audited as `stale_subscription_deleted_ignored`. An unsafe unclassified
deletion is ACKed 200 and audited as
`unclassified_subscription_deleted_ignored`. Neither path mutates tier or
queues winback.

## 1. Code Routing — Per-Directory Tier Assignment

| Path | Contents | Tier |
|---|---|---|
| `/home/flask/appserver/appserver/` | `appserver.py` (gunicorn entrypoint, ~5000-line Flask, 297953 bytes — root-owned 600), `chatbot.py`, `tradier_api.py`, `risk_profile.py`, `create_active_opps.py`, `seasonal_chart_funcs.py`, `get_symbol_csv.py`, `get_name_from_ticker.py`, `autotrade_process_portfolios.py`, `appserver.wsgi`, `appserver_stage.sh`/`appserver_prod.sh`, blueprint `appserver.blueprint`, `trend_chart_cache/` (1540 JSON files, 19M), `earnings_calendar.csv`, `appserver.log*` | **APP** |
| `/home/flask/web/` | `app.py` (62765 bytes Flask web tier), `models.py` (SQLAlchemy), `tier_compat.py`, `email_utils.py`, `db_admin.py`, `report_renderer.py`, `alembic.ini`, `templates/` | **WEB** |
| `/home/flask/smn/` | Article pipeline: `article_processor.py` (systemd worker), `blog_queue.py` (port 7171 Flask), `daily_article_queue.py`, `select_news_articles.py`, `article_workflow.py`, `article_post_process.py` (58895 bytes), `publish_article.py` (67137 bytes), `rebuild_news_home.py` (203073 bytes), `AI_tools.py`, `thumbnails*.py`, `email_tools.py`, `seo_helpers.py`, `set_redirect.py`, `generate_top10_sr.py`, `generate_security_pages.py`, `get_top10_data.py`, `get_price_eod.py`, `blog_tools.py`, `article_*.py`, `ticker_motif_custom.json`, `volume_lists/`, `article_ideas/`, `logs/` | **APP** (article-processor + blog-queue services live here, both Redis-bound to localhost; cron entries also run from this dir) |
| `/home/flask/site/` | Static-site generators: `generate_home_page.py` (47835 bytes), `generate_scorecard.py`, `generate_security_pages.py`, `generate_insights.py`, `generate_insights_charts.py`, `generate_daily_ai_pick.py`, `generate_about_page.py`, `generate_research_page.py`, `generate_email_newsletter.py`, `generate_text_pages.py`, `inject_header.py`. `lib/blog_tools.py`, `lib/daily_pattern_picks.py`, `lib/get_price_eod.py`, `lib/svg_wave_chart.py`, `lib/text_utils.py`. `templates/`, `static/` (51MB + 54MB MP4s), `content/`, `data/`, `ticker_pages/` (separate compute/render subsystem). Output: `/var/www/tradewave/` (210M). | **WEB** (writes `/var/www/tradewave/` which nginx serves on the web box) — but calls config.appserver_url over HTTP |
| `/home/flask/data/` | 39GB market data. `csv/{US,LSE,KO,KQ,TO,INDX,COMM,ETF,FOREX,CC,GBOND}/` per-ticker CSVs. 17× `<market>_symbols.csv` (730–315k bytes each). Per-market dirs `dj30/`, `sp500/`, `nasdaq100/`, `rus1000/`, `wilshire5000/`, `Sectors_ETF/`, etc., containing `opportunities/` and/or `opp_by_symbol/` precomputed subfolders. | **APP** (read by appserver/smn/data_updater) |
| `/home/flask/edgar/` | **Does not exist** on dev box. `config.edgar_folder = '/home/flask/edgar/'` and `config.edgar_service_url` are set but unused locally; `TW2_EDGAR_SERVICE_URL=http://104.238.214.253:7670/` (remote keyprovider). | App reference only |
| `/home/flask/web-react/` | `package.json` (react 17.0.2, react-scripts 5.0.1, chartjs, swiper, @react-oauth/google), `build/` (1.8M precompiled), `node_modules/` (large, build-time only), `src/`, `public/`. `.env.production = GENERATE_SOURCEMAP=false`. PUBLIC_URL=/app/. | **WEB** (built once on dev; `build/` is what gets copied to staging-web — nginx aliases `/app/` → `/home/flask/web-react/build/`) |
| `/home/flask/tests/` | pytest suite, `conftest.py`, 5 `test_*.py` files. | **WEB** (DB-bound) |
| `/home/flask/ops/` | `uptime_check.sh`, `soak_monitor.sh`, `backup_db.sh` (mode 750), `restore_drill.sh` (mode 750), `nginx/` (reference copies of `/etc/nginx/` config) | **WEB** (DB ops + nginx) |
| `/home/flask/migrations/` | Alembic env + 5 versions. | **WEB** (Postgres-bound) |
| `/home/flask/data_updater/` | EOD downloader scripts: `EOD_downloader{,2,3,_bulk,_bulk_test}.py`, `update_client2.py`, `update_server.py`, `create_symbol_file*.py`. Stale `config.py` with hardcoded prod IPs (NOT loaded by tier code — only by `EOD_downloader_bulk.py`/`update_client2.py` which do `import config` from `/home/flask`). Sample CSV files (regeneratable, gitignored). | **APP** (writes `/home/flask/data/`) |
| `/home/flask/scripts/` | **Does not exist.** No such dir. | n/a |
| `/home/flask/config.py` | Shared 573-line config file. Imported on both tiers. | **SHARED** |
| `/home/flask/config_autotrade.py` | 4826-byte autotrade config. Imported only by appserver. | **APP** |

### Cross-tier imports

- `web/` → `appserver/`: **None.** No `from appserver` or `import appserver` anywhere in `/home/flask/web/`. Web reaches appserver only via HTTP.
- `appserver/` → `web/` / `smn/` / `site/`: **None.** appserver.py does not import from those packages (verified by grep).
- `web/` → `smn/`: **None** in web tier code. Note: `web/report_renderer.py` imports nothing from smn but writes into `/var/www/tradewave/r/` and reads `/home/flask/data/{market}_symbols.csv` at line 410.
- `site/` → `smn/`: `/home/flask/site/generate_security_pages.py:25` does `sys.path.insert(0, '/home/flask/smn')` and reads `/home/flask/smn/...` output. So `site/` co-located with `smn/` is a soft coupling.
- `site/lib/` is self-contained; `site/generate_*.py` calls `config.appserver_url` over HTTP.
- `data_updater/` → app: imports `/home/flask/config.py`.
- `tests/` → web: imports `models`, `tier_compat`, `email_utils`, `app` from `/home/flask/web/`.

### Direct cross-tier filesystem reads (load-bearing)

- `/home/flask/web/app.py:592` reads `Path("/home/flask/web-react/build/index.html")` — **web reads its own React build dir, fine on web box.**
- `/home/flask/web/app.py:593` reads `Path("/home/flask/site/templates/_tw_header.html")` — **web reads site/ template directly. Web box must have site/templates/**.
- `/home/flask/web/report_renderer.py:410` `pd.read_csv(symbols_csv)` where `symbols_csv` comes from `config.available_resources_path` = `/home/flask/data/{market}_symbols.csv`. **Web tier reads `/home/flask/data/*_symbols.csv` from the APP box paths.** This is a cross-tier file dependency (web box needs at minimum the 17 small _symbols.csv files, not the 39GB).
- `/home/flask/site/generate_security_pages.py:68` reads `Path(config.news_root_folder) / "markets"` = `/var/www/smn/markets/` — site reads SMN's output; SMN runs on app box → site reads from web's own filesystem; in current dev box this works because they're co-located. **On split topology, site/generate_security_pages.py needs `/var/www/smn/markets` content rsync'd or symlinked.**
- `/home/flask/site/lib/blog_tools.py:153` `pd.read_csv(symbols_csv)` — same as report_renderer pattern.

## 2. Hardcoded URLs / IPs / Ports / Paths

### Hardcoded service-port numbers (must be env-driven on staging)

| File:line | Issue |
|---|---|
| `/home/flask/web/app.py:1531` | `app.run(host="127.0.0.1", port=5500, debug=False)` — only used when running `python app.py` directly; gunicorn unit overrides. OK as fallback. |
| `/home/flask/site/generate_scorecard.py:31` | `APPSERVER_URL = 'http://127.0.0.1:5000'` — **hardcoded, NOT env-driven.** Bug on split topology: site runs on web box, must hit app box over VLAN. |
| `/home/flask/site/generate_home_page.py:231` | `APPSERVER_URL = 'https://app1pp.trxstat.com'` — **hardcoded prod URL, NOT env-driven.** |
| `/home/flask/site/generate_daily_ai_pick.py:46` | `APPSERVER_URL = 'https://app1pp.trxstat.com'` — same. |
| `/home/flask/web/app.py:531` | `redirect_after = "https://tw2.trxstat.com/"` — hardcoded post-logout destination. |
| `/home/flask/web/report_renderer.py:45` | `DOMAIN_ROOT = 'https://tw2.trxstat.com/'` — hardcoded; embedded in generated report HTML. |
| `/home/flask/smn/generate_tw_security_pages.py:64` | `DOMAIN_ROOT = "https://tw2.trxstat.com/"` — hardcoded. |
| `/home/flask/site/generate_security_pages.py:80` | `DOMAIN_ROOT = "https://tw2.trxstat.com/"` — hardcoded. |
| `/home/flask/site/generate_home_page.py:110` | `CANONICAL_ROOT = "https://tw2.trxstat.com/"` — hardcoded. |
| `/home/flask/site/generate_insights.py:135,137,140,184,186` | `https://tw2.trxstat.com` literals in OG tags / sitemap. |
| `/home/flask/site/generate_text_pages.py:274` | `https://tw2.trxstat.com/` canonical link literal. |
| `/home/flask/site/templates/insights_index.html`, `insights_article.html` | Multiple `tw2.trxstat.com` literals. |
| `/home/flask/site/templates/index-dark-blue.html:1802,1803` | `https://smn-dev.trxstat.com/` literals. |
| `/home/flask/site/templates/_tw_header.html:172` | `https://smn-dev.trxstat.com/` literal. |
| `/home/flask/site/generate_about_page.py:31,40,50,157,164,212` | `tradewave.ai` literals (canonical / mailto / JSON-LD). |
| `/home/flask/smn/article_post_process.py:454,541,1083` | `https://tradewave.ai` literals in article HTML/JSON-LD. |
| `/home/flask/smn/refresh_related_articles.py:45` | `https://tradewave.ai/news/...` literal. |
| `/home/flask/smn/publish_article.py:1843,1844` | `http://192.168.1.151/...` literal in comments (not active). |
| `/home/flask/smn/article_title.py:1156,1157` | `/var/www/html/wordpress/news/...` test fixture paths (in `if __name__`). |
| `/home/flask/data_updater/test.py:4` | `csv_folder = '/home/flask/data/dj30/csv/'` — broken path; test scaffold. |
| `/home/flask/data_updater/config.py:11` | `wordpress_url = 'http://192.168.68.105/'` — stale; this file is not used by tier services (it's an old prod artifact). |
| `/home/flask/data_updater/config.py:13` | `logcollector_url = 'http://104.238.214.253:7774/'` — stale, but the `data_updater/EOD_downloader_bulk.py` imports `from /home/flask/config` not the local one. |
| `/home/flask/data_updater/update_server.py:64` | `app.run(host='0.0.0.0', debug=True)` — only used if run manually; not a systemd service. |

### Hardcoded IPs in active code

- `/home/flask/web/app.py:152` `f"http://{os.environ.get('TW2_PUBLIC_HOST', '192.168.1.176')}/auth/callback"` — default falls back to dev IP if env not set.
- `/etc/systemd/system/tradewave-web.service` line `Environment=TW2_PUBLIC_HOST=192.168.1.176` — dev default; the **override.conf** rewrites it to `tw2.trxstat.com`.
- `/home/flask/site/generate_security_pages.py:231-232` and `/home/flask/smn/generate_tw_security_pages.py:375-376` — stale-URL **scrubbers** that strip `http://192.168.1.151:9000`, `http://192.168.1.151`, `http://192.168.1.176` from generated HTML (defense in depth).

### Hardcoded ports in active code

| File:line | Port |
|---|---|
| `/home/flask/smn/blog_queue.py:958` | `app.run(host='0.0.0.0',debug=False, port=7171)` — blog_queue listens on 7171 |
| `/home/flask/web/app.py:1531` | `127.0.0.1:5500` (fallback only) |
| `/home/flask/smn/article_processor.py:22` | `redis.Redis(host="localhost", port=6379, db=config.articles_redis_db)` — db=3 |
| `/home/flask/smn/blog_queue.py:35-36` | `localhost:6379 db=0` + `db=3` |
| `/home/flask/smn/email_tools.py:24-25` | localhost db=0; **db=2 via `host=config.appserver_ip`** (cross-tier Redis read) |
| `/home/flask/smn/generate_security_pages.py:241` | `redis.Redis(host=config.webserver_ip, port=6379, db=3)` — SMN running on app reads/writes web-box Redis db=3 over VLAN |
| `/home/flask/smn/rebuild_news_home.py:122` | same: web-box Redis db=3 |
| `/home/flask/smn/publish_article.py:242` | same: web-box Redis db=3 |
| `/home/flask/smn/select_news_articles.py:524`, `/home/flask/smn/daily_article_queue.py:275` | `localhost:6379 db=articles_redis_db (3)` — but `localhost` here means **app-box-local Redis db=3**, conflicting semantically with the web-box Redis db=3 used elsewhere |
| `/home/flask/tests/conftest.py:63` | `postgresql://tradewave@127.0.0.1:5432/tradewave_test` (test DSN) |
| `/home/flask/tests/test_security_audit_2026_05_08.py:240,253` | `HTTPConnection("127.0.0.1", 5000, timeout=2)` test (auto-skips when unreachable) |

### Absolute `/home/flask/` paths outside config.py

- `/home/flask/web/app.py:75-76,592,593`
- `/home/flask/web/models.py:15`
- `/home/flask/web/db_admin.py:55,56`
- `/home/flask/web/report_renderer.py:5,12,13` (comments)
- `/home/flask/site/generate_insights.py:40` `SITE_ROOT = Path('/home/flask/site')`
- `/home/flask/site/generate_text_pages.py:33` `SRC_DIR = Path("/home/flask/site/content")`
- `/home/flask/site/lib/svg_wave_chart.py:784` `/home/flask/blog/wave_chart_test.svg` (legacy test path)
- `/home/flask/data_updater/EOD_downloader3.py:539` writes `/home/flask/data_updater/EOD3_run.xxx`
- `/home/flask/data_updater/test.py:4`
- `/home/flask/migrations/env.py:43,44`
- `/home/flask/tests/conftest.py:78,79`
- Logging: `/home/flask/appserver/appserver/appserver.py:131` `logging.basicConfig(filename='/var/log/tradewave/appserver.log',...)` — app box log dir must exist.

## 3. State Plane

### Postgres tables (from `/home/flask/web/models.py`)

| Table | Columns | PK | FKs / Constraints |
|---|---|---|---|
| `users` | `id`(UUID,gen_random_uuid), `workos_user_id`(Text,unique), `email`(Text,unique,NOT NULL), `email_verified`(Bool), `first_name`, `last_name`, `legacy_phpass_hash`(Text), `roles`(JSONB,default=["user"]), `tier`(Text,default="explorer"), `legacy_wp_level`(Text), `stripe_customer_id`(Text,unique), `stripe_subscription_id`(Text), `stripe_subscription_status`(Text), `api_key_hash`(Text), `trial_ends_at`(TIMESTAMPTZ), `created_at`(TIMESTAMPTZ default now()), `updated_at`(TIMESTAMPTZ default now()), `last_login_at`(TIMESTAMPTZ) | id | CHECK `tier IN ('explorer','analyst','strategist','canceled')`; UNIQUE partial index on `stripe_subscription_id WHERE NOT NULL`; index on `api_key_hash`; trigger `users_legacy_wp_level_sync` (BEFORE INSERT/UPDATE of tier); trigger `users_updated_at` BEFORE UPDATE |
| `audit_log` | `id`(BIGINT), `actor_user_id`(UUID,FK users.id ON DELETE SET NULL), `actor_label`(Text), `action`(Text,NOT NULL), `target_user_id`(UUID,FK users.id ON DELETE SET NULL), `details`(JSONB), `created_at`(TIMESTAMPTZ default now()) | id (bigserial) | FKs users.id |
| `stripe_events` | `id`(BIGINT), `stripe_event_id`(Text,unique,NOT NULL), `event_type`(Text,NOT NULL), `user_id`(UUID,FK users.id), `payload`(JSONB), `received_at`(TIMESTAMPTZ default now()), `processed_at`(TIMESTAMPTZ), `processing_error`(Text) | id (bigserial) | FK users.id; unique stripe_event_id |
| `mailerlite_lifecycle_events` | `id`(BIGINT), `user_id`(UUID), `event_type`, `dedupe_key`, `status`, `attempts`, `available_at`, `claimed_at`, `processed_at`, `payload`(JSONB), `last_error`, `created_at`, `updated_at` | id (bigserial) | FK users.id ON DELETE CASCADE; unique dedupe_key; event type and status checks; due-work and user/status indexes |
| `coupons_used` | `id`(BIGINT), `user_id`(UUID,FK users.id ON DELETE CASCADE,NOT NULL), `stripe_coupon_id`(Text,NOT NULL), `redeemed_at`(TIMESTAMPTZ default now()), `metadata`(JSONB) | id (bigserial) | UNIQUE (user_id, stripe_coupon_id) |

Additional DB objects from `c0d92cd5de83_baseline_schema.py`: `schema_version` (legacy bookkeeping; superseded by alembic_version); `set_updated_at()` PL/pgSQL function used by `users_updated_at` trigger; `users_sync_legacy_wp_level()` from migration 1940d1f63473.

### Alembic migration chain (in order — bottom-up)

**Current deployment note:** revision `c7a9e2f4d6b8` adds the MailerLite
lifecycle outbox and `d8c4e6a2f9b1` adds separate API subscription identity.
The five-entry list below is the May 2026 inventory snapshot, not the current
head. Routine deploy runs `ops/migrate.sh` before web restart.

1. `c0d92cd5de83_baseline_schema.py` (down_revision = None) — **NO-OP**, stamp-only. Documents the hand-rolled baseline schema; downgrade() raises.
2. `18eb4ac1baa0_tier_compat_analyst_4_strategist_6_was_.py` (down_revision = c0d92cd5de83) — data-only UPDATEs to correct `users.legacy_wp_level` mapping. Idempotent. downgrade() is no-op.
3. `1940d1f63473_schema_hardening_tier_check_unique_sub_.py` (down_revision = 18eb4ac1baa0) — adds CHECK constraint, UNIQUE partial index on stripe_subscription_id, UNIQUE on coupons_used(user_id, stripe_coupon_id), trigger `users_legacy_wp_level_sync`.
4. `4c2f28489e2b_hash_users_api_key_defense_in_depth_for_.py` (down_revision = 1940d1f63473) — adds `users.api_key_hash` Text column + index `users_api_key_hash_idx`.
5. `5a3c1e2f4d6b_drop_users_api_key_plaintext.py` (down_revision = 4c2f28489e2b): **drops** the plaintext `users.api_key` column + drops index `idx_users_api_key`. This was the head at inventory time.

### Redis namespaces

**Redis db assignment (per `/home/flask/appserver/appserver/appserver.py:135-142`):**

| DB | Use | Host |
|---|---|---|
| 0 | App-side ephemeral cache (chart/opp/stockscore/seasonal_chart) + flask-limiter storage | `localhost` (app box) |
| 1 | Autotrading state | `localhost` (app box) |
| 2 | App-side persistent (user_reports, user_portfolios, user_watchlists, user_email_settings_*) | `localhost` (app box) |
| 3 | News article queue + published article payloads | **`config.webserver_ip`** (web box, when split) |

**Web-side Redis (per `/home/flask/web/app.py`):** No direct `redis.Redis(...)` in `/home/flask/web/app.py`. Web tier uses WorkOS sealed-cookie sessions, not Redis sessions. Flask `session` uses signed cookie. So **web-box Redis is used exclusively by SMN code that runs on the app box but reaches across the VLAN** (db=3, news article publish state).

**App-side Redis key patterns + TTLs** (file:line in appserver.py):

| Key pattern | TTL var | TTL (seconds) | Line |
|---|---|---|---|
| `opp4_{resID}_{month}_{day}_{year1}_{year2}_{dayRange}_{oppListExpanded}_{u}{suffix}` | opp_expire_time | 51 | 832, 1065 |
| `oppa4_...` (active) | opp_expire_time | 51 | 833, 1085 |
| `opp_by_sym_{resID}_{symbol}_{year1}_{year2}_{dayRange}{suffix}` | opp_by_symbol_expire_time | 3600 | 1275, 1307 |
| `stockscore_{resID}_{symbol}` | stockscore_expire_time | 51 | 1351, 1391 |
| `stockscore_daily_{resID}_{symbol}_{today_str}` | stockscore_daily_expire_time | 86400 | 1419, 1437 |
| `ml_score_*` (via `_ml_redis_key()` helper) | per-call ttl | varies | 1493, 1549, 1600, 1649, 1650 |
| `earnings_{symbol}` | hardcoded 86400 | 86400 | 1692, 1728 |
| `realtime_prices` | hardcoded 3300 | 3300 | 1739, 1756 |
| `security_name_{exchange}_{symbol}` | no expire | persist | 1769, 1781 |
| `chartdata_{resID}_{symbol}_{date}_{daysOut}_{yrs}_{cutOffYear}` | chart_data_expire_time | 51 | 1833, 2159 |
| `years_meta_data_{resID}_{date}` | years_metadata_expire_time | 51 | 2222, 2248 |
| `years_meta_data_PE_{resID}_{date}` | years_metadata_expire_time | 51 | 2223, 2273 |
| `history_v2_{resID}_{symbol}_{d0}_{d1}` | history_expire_time | 51 | 2393, 2433 |
| `stock_meta_data_{resID}_{symbol}` | stock_metadata_expire_time | 51 | 2443, 2475 |
| `list_symbols_{resID}` | stock_metadata_expire_time | 51 | 2486, 2535 |
| `stock_last_price_{resID}_{symbol}` | stocklastprice_expire_time | 51 | 2544, 2577 |
| `stock_price_by_date_{resID}_{symbol}_{date}` | stocklastprice_expire_time | 51 | 2587, 2619 |
| `spbd_{resID}_{symbol}_{date}` | spbd_static_expire_time | 993600 | 3657 |
| `seasonal_chart_{resID}_{symbol}_{sy}_{chart_start_date}` | seasonal_chart_expire_time | 51 (also file cache) | 2645, 2664, 2867 |

**App-side Redis db=2 persistent keys (no TTL):**
- `user_reports_{userid}` — lines 384, 3127, 3758, 3866, 3906, 3956, 4134
- `user_portfolios_{userid}` — lines 2961, 4006, 4028, 4067, 4106
- `num_today_{userid}` — line 3040 (ex=secs_to_midnight)
- `user_watchlists_{userid}` — line 4162
- `user_watchlist_items_{userid}_{name}` — line 4179
- `user_email_settings_*` — `/home/flask/smn/email_tools.py:69,78`

**Article-queue keys on db=3** (from `/home/flask/smn/blog_queue.py`, `article_processor.py`, `publish_article.py`):
- `news_article_queue` (FIFO list — `config.NEWS_QUEUE_NAME`)
- Holding key (per article_processor.py:90, 152, 156, 161, 165) — name not constant; scheduled-publish buffer
- Article payload keys: `redis_key_article` (line 3831 appserver, format `{rID}_{sym}_{sdate}_{days}_{years}_{tone}_{website_id}`), and `publish_article.py:475` writes payloads then deletes after consumption.

**Web-side Redis: NONE** — flask-session is signed-cookie only; the web tier does **not** open a Redis connection. The web box runs Redis only because SMN code (running on app box) reaches in over the VLAN at `config.webserver_ip:6379 db=3`.

### Filesystem state — cross-tier paths and sizes

| Path | Size | Owner tier | Used by |
|---|---|---|---|
| `/home/flask/data/` | 39G | APP | appserver, smn, data_updater |
| `/home/flask/data/csv/` | 5.8G | APP | per-exchange OHLCV: US 1.6G/3543 files, LSE 1.1G/7366, KQ 702M/2089, KO 648M/2642, TO 594M/3116, INDX 392M/1670, FOREX 314M/994, CC 311M/2351, ETF 88M/200, COMM 61M/380, GBOND 32M/148 |
| `/home/flask/data/<market>_symbols.csv` | 730–315861 bytes | APP — but **also read by `/home/flask/web/report_renderer.py:410`** | 17 files |
| `/home/flask/data/{dj30,sp500,nasdaq100,rus1000,wilshire5000,Sectors_ETF}/` | precomputed opportunities + opp_by_symbol parquet/csv | APP | appserver only |
| `/home/flask/edgar/` | **NOT PRESENT on dev**; config.edgar_folder='/home/flask/edgar/' is referenced but the EDGAR service is remote (TW2_EDGAR_SERVICE_URL=http://104.238.214.253:7670/) | n/a | n/a |
| `/home/flask/appserver/appserver/trend_chart_cache/` | 19M / 1540 JSON files | APP | seasonal_chart_funcs caches; auto-created on first miss |
| `/home/flask/appserver/appserver/earnings_calendar.csv` | bundled | APP | `config.earnings_calendar_file` |
| `/home/flask/web-react/build/` | 1.8M | WEB | served by nginx via alias |
| `/home/flask/site/static/` | 104MB (anne-marie_tradewave.mp4 51M, erin1.mp4 54M, favicons, product-demo.webp 128k) | WEB | copied/served as part of marketing site |
| `/home/flask/site/templates/` | site HTML templates including `_tw_header.html` (also read directly by web/app.py:593) | WEB | shared by site generators + web app |
| `/var/www/tradewave/` | 210M | WEB | nginx serves; written by site/* generators and web/report_renderer.py (`/var/www/tradewave/r/`) |
| `/var/www/tradewave/insights/`, `/markets/`, `/r/`, `/_static/`, `/patterns/` | subdirs | WEB | generated content |
| `/var/www/smn/` | 201M | APP-box (nginx?) | written by smn/publish_article.py + smn/generate_security_pages.py. **config.news_root_folder='/var/www/smn/'**. nginx config `/home/flask/ops/nginx/sites-available/smn-dev` serves this at smn-dev.trxstat.com (currently on dev box). |
| `/var/www/html/` | unknown | n/a | mentioned only in stale comments / legacy code |
| `/var/backups/tradewave/` | nightly db dumps (`db_YYYYMMDD_HHMM.sql.gz`) | WEB | written by `ops/backup_db.sh` |
| `/var/log/tradewave/` | per-service log files (see §14) | BOTH | systemd units + cron |

## 4. Env Vars & Secrets

### Every `os.environ.get(...)` call in `/home/flask/config.py`

| Var | Default | Comment | Tier |
|---|---|---|---|
| `WORKOS_CLIENT_ID` | `''` | per-env: staging vs prod client | WEB |
| `WORKOS_API_KEY` | `''` | | WEB |
| `WORKOS_COOKIE_PASSWORD` | `''` | | WEB |
| `WORKOS_AUTHKIT_DOMAIN` | `''` | per-env hosted UI domain | WEB |
| `STRIPE_PUBLISHABLE_KEY` | `''` | | WEB |
| `STRIPE_SECRET_KEY` | `''` | | WEB |
| `STRIPE_WEBHOOK_SECRET` | `''` | | WEB |
| `POSTGRES_DSN` | `''` | | WEB |
| `SERVICE_API_KEY` | `''` | | SHARED (referenced by appserver) |
| `APPSERVER_JWT_SECRET` | `''` | | SHARED (web signs, app verifies) |
| `API_KEY_HMAC_SECRET` | falls back to APPSERVER_JWT_SECRET | per `config.py:27` | SHARED |
| `TAVILY_API_KEY` | `''` | | APP (smn) |
| `GROK_API_KEY` | `''` | | APP (smn) |
| `REPLICATE_API_TOKEN` | `''` | | APP (smn) |
| `PERPLEXITY_API_KEY` | `''` | | APP (smn) |
| `OPENAI_KEY` | `''` | | APP (smn) |
| `EOD_TOKEN` | `''` | | APP (data_updater) |
| `ANTHROPIC_TOKEN` | `''` | | APP (smn) |
| `PUBLER_API_KEY` | `''` | | APP (smn) |
| `PUBLER_WORKSPACE_ID` | `''` | per-env workspace | APP |
| `PUBLER_X_ACCOUNT_ID` | `''` | per-env X account | APP |
| `FACEBOOK_APP_ID` | `''` | per-env FB app | APP |
| `FACEBOOK_APP_SECRET` | `''` | | APP |
| `FACEBOOK_ACCESS_TOKEN` | `''` | | APP |
| `FACEBOOK_PAGE_ID` | `''` | per-env FB page | APP |
| `FACEBOOK_OPP_PAGES_JSON` | `''` | JSON-encoded; per-env | APP |
| `TW2_WORDPRESS_USERNAME` | `''` | per-env WP author | APP (smn legacy) |
| `WORDPRESS_APP_PASSWORD` | `''` | | APP (smn legacy) |
| `TW2_APPSERVER_IP` | `''` | redis host in appserver | SHARED |
| `TW2_WEBSERVER_IP` | `''` | redis host in webserver | SHARED |
| `TW2_ML_SCORER_URL` | `''` | ML pattern scorer | APP |
| `TW2_X_PROFILE_URL` | `''` | X/Twitter profile per env | APP |
| `TW2_DOMAIN_ROOT` | `''` | per-env public root | SHARED |
| `TW2_EDGAR_SERVICE_URL` | `''` | EDGAR service URL | APP |
| `TW2_REALTIME_SERVICE_URL` | `''` | real-time price service | APP |
| `TW2_BLOG_QUEUE_SERVER` | `''` | per-env blog queue | APP |
| `MAILERLITE_TOKEN` | `''` | | APP |
| `TW2_APPSERVER_URL` | `''` | per-env appserver URL | SHARED (web→app, also site, smn) |
| `TW2_SMN_FAVICON_URL` | `''` | | SHARED |
| `TW2_ARTICLE_FAVICON_URL` | `''` | | APP |
| `INDEXNOW_KEY` | `''` | | APP (smn) |
| `TW2_NEWS_WEBSITE_URL` | `''` | per-env news site | SHARED |
| `TW2_MASTER_APPSERVER` | `''` | per-env master appserver | APP |
| `TW2_UPDATE_SERVER` | `''` | per-env update server | APP |
| `TW2_WORDPRESS_URL` | `''` | per-env WP URL | APP (smn) |
| `TW2_LOGCOLLECTOR_URL` | `''` | per-env log collector | APP |
| `TW2_STOCKSCORE_URL` | `''` | per-env stockscore service | APP |
| `TW2_KEYSTORE_URL` | `''` | per-env keystore URL | APP |
| `SENTRY_DSN` | `''` | | SHARED |
| `MAILERLITE_API_KEY` | `''` | | WEB (used by `/home/flask/web/email_utils.py`) |
| `MAILERLITE_GROUP_ID` | `''` | | WEB |
| `MAILERLITE_OUTBOUND_ENABLED` | `''` (false) | app-originated writes require truthy value plus `TW2_ENV=prod` | WEB |
| `MAILERLITE_TRIAL_STARTED_GROUP_ID` | `''` | lifecycle trigger ID, no committed default | WEB |
| `MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID` | `''` | lifecycle trigger ID, no committed default | WEB |
| `MAILERLITE_WINBACK_GROUP_ID` | `''` | lifecycle trigger ID, no committed default | WEB |

Outside config.py:
- `/home/flask/web/app.py:151-152` `TW2_AUTH_CALLBACK_URL` (default = `f"http://{TW2_PUBLIC_HOST}/auth/callback"`) — WEB
- `/home/flask/web/app.py:152,869,1125` `TW2_PUBLIC_HOST` (default 192.168.1.176 or tw2.trxstat.com) — WEB
- `/home/flask/web/db_admin.py:48,68` `API_KEY_HMAC_SECRET`
- `/home/flask/migrations/env.py` `TW2_ALEMBIC_DSN_OVERRIDE`, `POSTGRES_DSN` (parsed from secrets.env directly if not set)

### `/etc/tradewave/secrets.env` (READABLE — keys + per-env URL clues)

File header: `Loaded by systemd. NEVER commit to git. Owner: root:flask, mode 640. Modified 2026-05-07.`

Keys present (values redacted in this report — they were observed):

- WORKOS_CLIENT_ID, WORKOS_API_KEY, WORKOS_COOKIE_PASSWORD, WORKOS_AUTHKIT_DOMAIN
- STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
- POSTGRES_DSN
- SERVICE_API_KEY, APPSERVER_JWT_SECRET
- OPENAI_KEY, ANTHROPIC_TOKEN, TAVILY_API_KEY, GROK_API_KEY, PERPLEXITY_API_KEY, REPLICATE_API_TOKEN
- EOD_TOKEN
- PUBLER_API_KEY, PUBLER_WORKSPACE_ID, PUBLER_X_ACCOUNT_ID
- FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID, FACEBOOK_OPP_PAGES_JSON
- TW2_WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD
- MAILERLITE_TOKEN, MAILERLITE_API_KEY (empty), MAILERLITE_GROUP_ID (empty)
- Current lifecycle additions: MAILERLITE_OUTBOUND_ENABLED,
  MAILERLITE_TRIAL_STARTED_GROUP_ID,
  MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID, MAILERLITE_WINBACK_GROUP_ID
- SENTRY_DSN (empty)
- TW2_DOMAIN_ROOT, TW2_APPSERVER_IP, TW2_WEBSERVER_IP, TW2_APPSERVER_URL, TW2_ML_SCORER_URL, TW2_EDGAR_SERVICE_URL, TW2_REALTIME_SERVICE_URL, TW2_UPDATE_SERVER, TW2_LOGCOLLECTOR_URL, TW2_STOCKSCORE_URL, TW2_MASTER_APPSERVER, TW2_BLOG_QUEUE_SERVER, TW2_WORDPRESS_URL, TW2_NEWS_WEBSITE_URL, TW2_SMN_FAVICON_URL, TW2_ARTICLE_FAVICON_URL, TW2_X_PROFILE_URL, TW2_KEYSTORE_URL
- INDEXNOW_KEY

Current dev values include: `TW2_DOMAIN_ROOT=http://192.168.1.176/`, `TW2_APPSERVER_IP=192.168.68.151` (anomalous — this is a stale IP, not the staging VLAN), `TW2_WEBSERVER_IP=localhost`, `TW2_APPSERVER_URL=http://127.0.0.1:5000`, `TW2_BLOG_QUEUE_SERVER=http://localhost:7171/`, `TW2_WORDPRESS_URL=http://192.168.1.151/`, `TW2_NEWS_WEBSITE_URL=https://smn-dev.trxstat.com`, `TW2_KEYSTORE_URL=http://localhost:7777`. All Stripe + WorkOS keys are **test mode** (sk_test_, pk_test_, rapid-fish-71-**staging**.authkit.app, client_01KQNXQ43D9ASZC4E4JTB4Y2JV).

Per-env comments in config.py noting prod overrides: WORKOS_*, STRIPE_*, PUBLER_WORKSPACE_ID, PUBLER_X_ACCOUNT_ID, FACEBOOK_APP_ID, FACEBOOK_PAGE_ID, FACEBOOK_OPP_PAGES_JSON, TW2_WORDPRESS_USERNAME, all TW2_* URLs.

## 5. External Services

| Service | Caller tier | Caller file:line | Env var | Failure mode |
|---|---|---|---|---|
| **WorkOS AuthKit** | WEB | `web/app.py:98-100,140-147,168,204,458,533-561,1470` | WORKOS_API_KEY + WORKOS_CLIENT_ID + WORKOS_COOKIE_PASSWORD + WORKOS_AUTHKIT_DOMAIN | SDK 10s timeout (line 146); raises → caller catches in _read_sealed_session / auth_callback / logout. Hosted UI unreachable = users can't sign in/out. |
| **Stripe** | WEB | `web/app.py:103-115,712,805,877,910,953,1108,1126,1178,1281,1464` | STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET | RequestsClient timeout=10s + max_network_retries=2. SDK raises → caller logs + 500 to user. Webhook signature verification on `web/app.py:1178`. |
| **Mailerlite (web)** | WEB | `web/mailerlite_lifecycle.py` + `web/email_utils.py`, `https://connect.mailerlite.com/api` | MAILERLITE_API_KEY or MAILERLITE_TOKEN fallback, three lifecycle group IDs, MAILERLITE_OUTBOUND_ENABLED | Signup/Stripe writes durable outbox rows; minute worker retries, reconciles, and verifies managed groups. Writes require explicit prod-only enablement. |
| **Mailerlite (smn, legacy)** | APP | `smn/publish_article.py:80,5006-5125` (`MailerLite.Client`) + `smn/generate_tw_security_pages.py:140`, `smn/rebuild_news_home.py:109`, `smn/generate_security_pages.py:1548` (GET `https://connect.mailerlite.com/api/groups?limit=100`) | MAILERLITE_TOKEN | SDK exceptions propagate. |
| **WordPress (legacy)** | APP | `smn/blog_tools.py:123,214,236`, `smn/create_report.py:415,464,731`, `smn/generate_top10_sr.py:341,366,375`, `smn/publish_article.py:484`, `smn/set_redirect.py:31,38,64`, `site/lib/blog_tools.py:123,214,236` — all use `config.post_endpoint_url`, `config.tags_endpoint_url`, `config.redirect_endpoint_url` | TW2_WORDPRESS_URL + TW2_WORDPRESS_USERNAME + WORDPRESS_APP_PASSWORD | requests.* uncaught — caller can 500. **Note: `config.post_endpoint_url` is NOT defined in config.py — it is set elsewhere (or undefined; observed only in usage).** |
| **OpenAI** | APP | `smn/AI_tools.py:53,85,426,513-524` POST `api.openai.com/v1/chat/completions`, `/v1/images/generations` | OPENAI_KEY | requests timeouts 30-60s; retry_api_call wrapper. |
| **Anthropic** | APP | `smn/AI_tools.py:59,564,606` POST `api.anthropic.com/v1/messages` | ANTHROPIC_TOKEN | requests; uncaught → caller |
| **Grok (xAI)** | APP | `smn/AI_tools.py:43,145,155` POST `api.x.ai/v1/chat/completions` | GROK_API_KEY | timeouts; uncaught |
| **Perplexity** | APP | `smn/AI_tools.py:468,485,496` POST `api.perplexity.ai/chat/completions` | PERPLEXITY_API_KEY | timeouts; uncaught |
| **Tavily** | APP | `smn/AI_tools.py:40,226` POST `api.tavily.com/search` | TAVILY_API_KEY | 30s timeout |
| **EOD Historical Data** | APP | `data_updater/EOD_downloader*.py:60,82,122,142,29`, `smn/get_price_eod.py:31,118` (real-time `eodhd.com/api/real-time`), `site/lib/get_price_eod.py:31,118` | EOD_TOKEN | timeouts 5-10s; data_updater has retry+backoff |
| **Replicate** | APP | `smn/AI_tools.py` (imported; not grepped directly here but in installed packages) | REPLICATE_API_TOKEN | SDK |
| **Publer** | APP | `smn/publish_article.py` (references PUBLER_API_KEY via config; URL is `app.publer.io/api` per env) | PUBLER_API_KEY + PUBLER_WORKSPACE_ID + PUBLER_X_ACCOUNT_ID | n/a |
| **Facebook Graph** | APP | `smn/publish_article.py` (uses config.FACEBOOK_*) | FACEBOOK_APP_ID/SECRET/ACCESS_TOKEN/PAGE_ID, FACEBOOK_OPP_PAGES_JSON | n/a |
| **IndexNow** | APP | `smn/publish_article.py:1578,1600` POST `https://api.indexnow.org/indexnow` | INDEXNOW_KEY | requests; caller bears |
| **Sentry** | BOTH | `web/app.py:80-91`, `appserver/appserver.py:99-105` `sentry_sdk.init(dsn=...)` with FlaskIntegration | SENTRY_DSN | Optional; init skipped if empty or contains "PLACEHOLDER" |
| **Cloudflare** | — | Not directly called (Cloudflare tunnel mentioned in comments for Stripe webhook ingress). |
| **Google Analytics** | n/a | `config.ga_measurement_id=''` — not configured. |

Outbound TLS hosts (egress allowlist candidates): `api.workos.com`, `*.authkit.app`, `api.stripe.com`, `js.stripe.com`, `checkout.stripe.com`, `connect.mailerlite.com`, `api.openai.com`, `api.anthropic.com`, `api.x.ai`, `api.perplexity.ai`, `api.tavily.com`, `eodhistoricaldata.com`, `eodhd.com`, `api.replicate.com`, `api.indexnow.org`, `app.publer.io`, `graph.facebook.com`, `connect.facebook.net`.

## 6. System Dependencies

### Python

- Python **3.13.7** in `/home/flask/venv` (per `pyvenv.cfg`, system python3.13). System-site-packages disabled.
- `/home/flask/appserver/appserver/requirements.txt` (tiny, app-only): numpy, pandas, tables, Flask, Flask-Cors, pyjwt, redis, filelock, Flask-Limiter.
- **No top-level `/home/flask/requirements.txt` exists.** Actual installed packages in `/home/flask/venv/lib/python3.13/site-packages/`:

flask 3.1.3, flask_admin 2.1.0, flask_cors 6.0.2, flask_limiter 2.9.2, flask_session 0.8.0, flask_sqlalchemy 3.1.1, gunicorn 25.3.0, werkzeug 3.1.8, jinja2 3.1.6, markupsafe 3.0.3, itsdangerous 2.2.0, blinker 1.9.0, click 8.3.3, sqlalchemy 2.0.49, alembic 1.18.4, psycopg2_binary 2.9.12, mako 1.3.12, pyjwt 2.12.1, cryptography 46.0.7, cffi 2.0.0, pycparser 3.0, requests 2.33.1, urllib3 2.6.3, certifi 2026.4.22, idna 3.13, charset_normalizer 3.4.7, httpx 0.28.1, httpcore 1.0.9, h11 0.16.0, anyio 4.13.0, redis 7.4.0, filelock 3.29.0, limits 5.8.0, cachelib 0.13.0, deprecated 1.3.1, ordered_set 4.1.0, wrapt 2.1.2, pandas 3.0.2, numpy 2.4.4, scipy 1.17.1, tables 3.11.1, blosc2 4.1.2, numexpr 2.14.1, ndindex 1.10.1, msgspec 0.21.1, msgpack 1.1.2, matplotlib 3.10.9, pillow 12.2.0, contourpy 1.3.3, cycler 0.12.1, kiwisolver 1.5.0, fonttools 4.62.1, pyparsing 3.3.2, packaging 26.2, six 1.17.0, dateutil 2.9.0.post0, pytz 2026.2, pyyaml 6.0.3, py_cpuinfo 9.0.0, pydantic 2.13.4, pydantic_core 2.46.4, annotated_types 0.7.0, typing_extensions 4.15.0, typing_inspection 0.4.2, sentry_sdk 2.59.0, mailerlite 0.1.10, replicate 1.0.7, stripe 15.1.0, workos 6.2.0, slugify (python_slugify 8.0.4) + text_unidecode 1.3, bleach 6.3.0, webencodings 0.5.1, markdown 3.10.2, commonmark 0.9.1, rich 12.6.0, pygments 2.20.0, wtforms 3.2.1, iniconfig 2.3.0, pluggy 1.6.0, pytest 9.0.3, pytest_mock 3.15.1, greenlet 3.5.0.

Packages needing system libs: **psycopg2-binary** ships its own libpq (no libpq-dev needed); **pillow** (libjpeg/zlib generally satisfied by base Ubuntu); **lxml** is NOT installed; **tables** (HDF5) needs libhdf5 system package, satisfied here from wheels; **cryptography** uses wheels.

### Node / React build

- `/home/flask/web-react/package.json`: react 17.0.2, react-scripts 5.0.1, react-router-dom 6.11.1, chart.js 3.6.0, chartjs-plugin-{annotation,datalabels}, react-chartjs-2 3.3.0, swiper 6.7.0, html-to-image, html2canvas, jwt-decode 3.1.2, react-icons 4.11.0, @fortawesome/*, @react-oauth/google, gapi-script, socket.io-client 4.7.3, ws 8.16.0, uuid 9.0.1.
- No `engines` field. No `.nvmrc`.
- `build` script: `PUBLIC_URL=/app/ react-scripts build`.
- `.env.production = GENERATE_SOURCEMAP=false`.
- **Node/npm not needed at runtime** on either staging box. Only the `build/` output is needed on the web box.

### System packages

| Package | Web box | App box | Source |
|---|---|---|---|
| postgresql server + client (libpq) | ✓ (15+ for `gen_random_uuid()`) | ✗ | systemd `After=postgresql.service` (web only); secrets.env `POSTGRES_DSN=...@127.0.0.1:5432` |
| redis-server | ✓ (db=3 only) | ✓ (db=0,1,2,3) | systemd `After=redis-server.service` on web, app, blog-queue, article-processor |
| nginx | ✓ | ✗ (TBD — smn-dev.trxstat.com vhost referenced; could be on web box if SMN URL is reverse-proxied, or on app box if direct) | ops/nginx config exists |
| certbot | ✓ | ✓ | `/etc/crontab` `1 1 1 * * root certbot renew` per dev artifact (not on flask user crontab — may not be active) |
| python3.13 (or venv via system) | ✓ | ✓ | `/home/flask/venv/bin/python` |
| HDF5 runtime libs (for `tables`) | ✓ | ✓ | smn uses pytables; web does not but venv includes it |
| Standard build-essential | only if rebuilding wheels | only if rebuilding wheels | Not required if venv is rsync'd; required if `pip install` from source. |
| pgbouncer | not referenced | n/a | n/a |
| logrotate | ✓ | ✓ | `/etc/logrotate.d/tradewave` already present on dev |

## 7. Service Inventory

### systemd units (`/etc/systemd/system/tradewave-*.service`)

| Unit | Tier | User | WD | ExecStart | EnvironmentFile | After/Wants | Listen |
|---|---|---|---|---|---|---|---|
| `tradewave-appserver.service` | APP | flask:flask | `/home/flask/appserver/appserver` | gunicorn `--workers 9 --worker-class sync --timeout 120 --bind 0.0.0.0:5000` `appserver:app` | `/etc/tradewave/secrets.env` | After=network.target redis-server.service | 0.0.0.0:5000 |
| `tradewave-article-processor.service` | APP | flask:flask | `/home/flask/smn` | `/home/flask/venv/bin/python /home/flask/smn/article_processor.py` | secrets.env, PYTHONUNBUFFERED=1 | After=network.target redis-server.service; Wants=redis-server.service | (worker, no listener) |
| `tradewave-blog-queue.service` | APP | flask:flask | `/home/flask/smn` | `/home/flask/venv/bin/python /home/flask/smn/blog_queue.py` | secrets.env, PYTHONUNBUFFERED=1 | After=network.target redis-server.service; Wants=redis-server.service | 0.0.0.0:7171 |
| `tradewave-web.service` | WEB | flask:flask | `/home/flask/web` | gunicorn `--workers 4 --worker-class sync --timeout 60 --bind 127.0.0.1:5500` `app:app` | secrets.env, PYTHONPATH=/home/flask:/home/flask/web, **Environment=TW2_PUBLIC_HOST=192.168.1.176** (overridden by drop-in) | After=network.target postgresql.service redis-server.service | 127.0.0.1:5500 |
| `tradewave-web.service.d/override.conf` | drop-in | — | — | `Environment=TW2_PUBLIC_HOST=tw2.trxstat.com`, `Environment=TW2_AUTH_CALLBACK_URL=https://tw2.trxstat.com/auth/callback` | — | — | — |

appserver Type=**notify** (gunicorn integrates with systemd notification); others are Type=simple. Restart=on-failure (web/app), Restart=always (article-processor). RestartSec=3-5.

App tier services **always reach Redis on `localhost`** for db=0,1,2 (appserver) and for db=3 in smn/article_processor/select_news_articles/daily_article_queue. SMN code that lives on the app box also reaches **web-box** Redis db=3 via `config.webserver_ip` (`smn/publish_article.py:242`, `smn/rebuild_news_home.py:122`, `smn/generate_security_pages.py:241`, `smn/email_tools.py:25`). On split topology, **the article queue split is inconsistent**: `article_processor.py:22` uses localhost db=3 (app-box redis) while `publish_article.py:242` uses webserver_ip db=3 (web-box redis). Either both sides need to point at the same Redis, or this codebase has two parallel db=3 namespaces.

### Cron entries

System crontab `/etc/crontab`:
```
36 23 * * * root  set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/data_updater/update_client2.py >> /var/log/tradewave/update_client.log 2>&1
```
This is the **EOD data update**, currently configured to run on dev. Reads update_server from env, writes to `/home/flask/data/csv/`. App-box only.

flask user crontab (`crontab -u flask`):
| Schedule | Command | Log | Tier |
|---|---|---|---|
| `*/5 * * * *` | `/home/flask/ops/uptime_check.sh` | `/var/log/tradewave/uptime.log` | WEB |
| `30 3 * * *` | `/home/flask/ops/backup_db.sh` | `/var/log/tradewave/backup.log` | WEB (Postgres) |
| `*/30 * * * *` | `/home/flask/ops/soak_monitor.sh` | `/var/log/tradewave/soak.log` | WEB (checks all services + DB) |
| `*/10 * * * 1-5` | `set -a; . /etc/tradewave/secrets.env; set +a; venv/bin/python /home/flask/site/generate_scorecard.py` | `scorecard.log` | WEB (site/) — calls appserver_url over HTTP |
| `30 5 * * 1-5` | same for `site/generate_security_pages.py` | `security_pages.log` | WEB |
| `0 2 * * *` | `cd /home/flask/smn && venv/bin/python select_news_articles.py` | `select_news.log` | APP |
| `0 3 * * *` | `cd /home/flask/smn && venv/bin/python daily_article_queue.py` | `daily_queue.log` | APP |

root user crontab: empty (`no crontab for root`).
`/etc/cron.d/`: only `e2scrub_all`, `sysstat` (Ubuntu defaults). No tradewave entries.

There is NOT a `restore_drill.sh` cron entry; it is an on-demand operator tool.

### Ops scripts (`/home/flask/ops/`)

| Script | Purpose |
|---|---|
| `uptime_check.sh` | curl `https://tw2.trxstat.com/` (accept 200) and `/app/` (accept 200/302); log PASS/FAIL → uptime.log. (Will fail on staging until DNS + TLS exist.) |
| `soak_monitor.sh` | journalctl errors + `systemctl is-active` for tradewave-web/appserver/blog-queue/article-processor/nginx/postgresql/redis-server + `pg_stat_activity` count + `df -h /`. Pulls POSTGRES_DSN from secrets.env via grep. |
| `backup_db.sh` | mode 750 root:flask. Reads POSTGRES_DSN via `python -c "import config; print(config.POSTGRES_DSN)"`, `pg_dump --no-owner --no-privileges`, gzip → `/var/backups/tradewave/db_${TS}.sql.gz`, prune >14 days. Logs `/var/log/tradewave/backup.log`. **Requires `pg_dump` binary on web box.** |
| `restore_drill.sh` | mode 750 root:flask. Picks newest backup, creates `tradewave_restore_test` DB via `sudo -u postgres psql`, restores, asserts `users` count > 0, drops DB. **Requires sudoers entry letting flask run `sudo -u postgres psql`**. |
| `nginx/` | Reference copies of `/etc/nginx/sites-available/{tradewave,smn-dev}` + `/etc/nginx/snippets/{security_headers,tw2-proxy-headers,dotfile_deny}.conf`. README documents install steps. |

## 8. Networking & Ports

| Service | Bind | Notes |
|---|---|---|
| appserver gunicorn | `0.0.0.0:5000` | bound to wildcard — both VLAN + public if exposed. On split topology this must be VLAN-only via firewall or `--bind 10.0.0.92:5000` |
| blog-queue (smn) | `0.0.0.0:7171` | bound to wildcard. App-internal. |
| web gunicorn | `127.0.0.1:5500` | loopback only; nginx fronts. |
| article-processor | none | redis consumer, no HTTP listener |
| Postgres | `127.0.0.1:5432` | per POSTGRES_DSN — web box only |
| Redis | port 6379 — both boxes | app box: db 0,1,2 cache + smn local. web box: db 3 for article publish state. |
| nginx | 80, 443 | web box (and possibly app box for smn-dev vhost) |

**Web → App VLAN connectivity needed:**
- `config.appserver_url` (port 5000) — used by `web/report_renderer.py:90,108`, `site/generate_*.py`, `smn/*.py`. So web box → app box on TCP/5000.
- `config.webserver_ip` (port 6379) — used by SMN code running on **app box** reaching back to **web box** Redis db=3 (`smn/publish_article.py:242`, etc.). So app box → web box on TCP/6379.
- `config.appserver_ip` (port 6379) — used by `smn/email_tools.py:25` (SMN on app, but the binding is awkward; in single-box dev `appserver_ip=192.168.68.151` is stale). On split, this reads from app-box Redis db=2.

So bidirectional: web→app 5000; app→web 6379. (Plus normal egress to the internet.)

Stripe inbound: `/webhooks/stripe` reaches the web tier via nginx → 5500. Requires public ingress on 443 with `tw2.trxstat.com` DNS.

WorkOS redirects: user-browser → WorkOS hosted UI → user-browser → `https://tw2.trxstat.com/auth/callback` → web. No server-to-server inbound from WorkOS unless webhooks are configured (`/webhooks/workos` exists as a **stub** at `web/app.py:1141-1144`).

## 9. Initial Data Required Before Services Start

**App box `tw2-stage-app`:**
- `/home/flask/data/` — 39G market data (5.8G csvs + 33G precomputed opportunities/opp_by_symbol). Can be regenerated from EODHD but slow.
- `/home/flask/data/*_symbols.csv` (17 files, 16K–315K each) — must be present before appserver loads opp data.
- `/home/flask/data/csv/<exchange>/<symbol>.csv` — file counts: US 3543, LSE 7366, KQ 2089, KO 2642, TO 3116, INDX 1670, FOREX 994, CC 2351, ETF 200, COMM 380, GBOND 148.
- `/home/flask/data/{dj30,sp500,nasdaq100,rus1000,wilshire5000,Sectors_ETF}/{opportunities,opp_by_symbol}/...` — required by appserver opportunity queries.
- `/home/flask/appserver/appserver/trend_chart_cache/` — 19M, 1540 JSON files. Auto-populates on cache miss; pre-warming optional.
- `/home/flask/appserver/appserver/earnings_calendar.csv` — bundled in repo per config.earnings_calendar_file.
- `/home/flask/edgar/` — **referenced in config but does not exist locally**; EDGAR data is fetched from remote `TW2_EDGAR_SERVICE_URL` on keyprovider. No on-box data needed.
- `/var/www/smn/` — 201M of SMN's generated articles + markets HTML. Required if app box also serves smn-dev vhost.

**Web box `tw2-stage-web`:**
- `/home/flask/web-react/build/` — 1.8M. nginx `/app/` alias.
- `/home/flask/site/templates/_tw_header.html` — read at runtime by `web/app.py:593`.
- `/home/flask/site/static/` — 104M including two MP4s (51M + 54M). Served as marketing assets.
- `/home/flask/data/*_symbols.csv` (17 small CSVs, ~1MB total) — read by `web/report_renderer.py:410` when generating reports. **Cross-tier file dependency.** Web box does NOT need the full 39G.
- `/var/www/tradewave/` — 210M static marketing site, generated by `/home/flask/site/generate_*.py`. nginx serves.
- Postgres `tradewave` database migrated through the current head, including `c7a9e2f4d6b8` (MailerLite outbox) and `d8c4e6a2f9b1` (separate API subscription identity).

## 10. Cross-tier Contracts

### JWT (web → app)

**Signing (web side)** — `/home/flask/web/app.py:597-635` `generate_ltk(user)`:
```
jwt.encode({
    "user_id":         str(user.id),
    "workos_user_id":  user.workos_user_id,
    "email":           user.email,
    "tier":            user.tier or "explorer",
    "legacy_level":    tier_to_legacy_level(user.tier or "explorer"),
    "roles":           user.roles or ["user"],
    "is_admin":        "super_admin" in (user.roles or []),
    "aud":             "tw2-appserver",
    "iss":             "tw2-web",
    "iat":             int(time.time()),
    # exp added elsewhere
}, config.APPSERVER_JWT_SECRET, algorithm=HS256)
```
plus a second JWT minted at `web/app.py:528` (login bootstrap form). Both use `config.APPSERVER_JWT_SECRET`.

**Verifying (app side)** — multiple sites in `/home/flask/appserver/appserver/appserver.py`:
```
jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'],
           audience='tw2-appserver', issuer='tw2-web')
```
Lines: 212, 324, 342, 421, 753, 1263, 1477, 3030, 3188, 3244, 3362, 3452, 3512, 3556, 3755, 3863. (`app.config['SECRET_KEY']` is set from `config.APPSERVER_JWT_SECRET` at appserver boot.)

**aud/iss are enforced.** The `TODO(F3)` at `/home/flask/web/app.py:605` reads "currently appserver does not pass these" but the codebase **does** now pass them — the TODO is stale and can be marked closed. Required claims: `aud=tw2-appserver`, `iss=tw2-web`. Algorithm: HS256. Secret env var: **APPSERVER_JWT_SECRET** (must match byte-exact on both boxes).

`SERVICE_API_KEY` (env: `SERVICE_API_KEY`, value `twsa_...`) is the long-lived service-account credential, separately hashed and stored in `users.api_key_hash` (HMAC-SHA256 with `API_KEY_HMAC_SECRET` which falls back to `APPSERVER_JWT_SECRET`). Back-office/internal callers send it in the `X-Service-Key` header to `POST /login/api`; it must never appear in a URL.

### HTTP endpoints called by web/site on appserver

| Caller file:line | URL pattern |
|---|---|
| `web/report_renderer.py:90` | `GET {appserver_url}/ChartData4/{id}/{opp_date}/{symbol}/{days_out}/{years}?token={ltk}` |
| `web/report_renderer.py:108` | `GET {appserver_url}/consolidated_seasonal_chart2/{id}/{symbol}/{years}/{chart_start_date}/{opp_start_date}?token={token}` |
| `site/lib/blog_tools.py:264,277` | `GET {appserver_url}/login/2/3/4/5/6` and `/login/28/3/4/5/{keyprovider_token}` |
| `site/lib/svg_wave_chart.py:79,85,106,115,124` | same /login plus `/ChartData4/...`, `/ChartHistorical2/...`, `/consolidated_seasonal_chart2/...` |
| `site/ticker_pages/ticker_data.py:38` | sets `APPSERVER_URL = config.appserver_url`, makes various calls |
| `smn/blog_tools.py:264-278`, `smn/create_report.py:84-287`, `smn/generate_top10_sr.py:31-73`, `smn/get_top10_data.py:31-75`, `smn/thumbnails.py:56`, `smn/thumbnail_tools.py:79` | legacy `/login/2/3/4/5/6` and `/login/28/3/4/5/{kp_token}` flows where still present; migrated callers use header-authenticated `POST /login/api`; data routes include `/OppList4/...`, `/ChartData4/...`, `/ChartHistorical2/...`, `/consolidated_seasonal_chart2/...` |
| `smn/select_news_articles.py:50` | sets `PROD_APPSERVER_URL = config.appserver_url.rstrip('/')` |

App-server routes invoked by these callers (subset, from appserver.py route grep): `/`, `/login/{userid}/{level}/{cc}/{zip}/{skey}`, `POST /login/api` (with `X-Service-Key`), `/OppList4/...`, `/OppBySymbol/...`, `/ChartData4/...`, `/ChartHistorical2/...`, `/StockMetaData/...`, `/GetListSymbols/...`, `/StockLastPrice/...`, `/getStockPriceByDate/...`, `/YearsMetaData2/...`, `/consolidated_seasonal_chart2/...`, `/NameFromTicker/...`, `/StockScoreBatch/...`, `/MLScoreBatch/...`, `/MLScorePending/...`, `/getResourcesObj`, `/dr_report_*`, `/article_*`, `/get_news_home_url/`, `/get_user_portfolio_names`, `/add_user_portfolio_name/...`, `/edit_user_portfolio_name/...`, `/del_user_portfolio_name/...`, `/get_user_watchlist_names`, `/get_user_watchlist_items/...`, `/update_status/...`, `/dr_report_list/...`, `/update_number_of_shares/...`, `/dr_report_remove/...`.

## 11. Migrations + Bootstrap-relevant Scripts

Alembic chain (see §3 for full detail): `c0d92cd5de83 → 18eb4ac1baa0 → 1940d1f63473 → 4c2f28489e2b → 5a3c1e2f4d6b`. Note the baseline migration is **stamp-only** — `alembic upgrade head` from an empty DB will NOT create the tables; the schema has to be created manually first (or copied from a dump), then `alembic stamp head` applied.

That short chain is the original inventory snapshot. Current lifecycle deploys
must reach at least `c7a9e2f4d6b8`, which creates
`mailerlite_lifecycle_events`; `ops/deploy.sh` reaches it through the normal
fail-closed `ops/migrate.sh` step before installing the minute cron and
restarting web.

The `tests/README.md` documents the schema-copy command:
```
sudo -u postgres psql -c "CREATE DATABASE tradewave OWNER tradewave;"
sudo PGPASSWORD=... pg_dump -h 127.0.0.1 -U tradewave -d <source> --schema-only --no-owner > schema.sql
sudo PGPASSWORD=... psql -h 127.0.0.1 -U tradewave -d tradewave -f schema.sql
```
For a brand-new staging-web Postgres, the baseline DDL must come from a dump of the dev DB (or be authored by hand). After that, `alembic stamp head` (or `alembic upgrade head` since migrations 18eb4ac1baa0 onwards are real DDL).

**One-time backfill scripts:**
- `/home/flask/ops/backfill_active_reverse_trial_lifecycle.py` schedules only
  the trial-end reconcile for Explorer users whose reverse trial is still
  active. It is dry-run by default; run `--apply` only after inspecting counts.
- `/home/flask/web/db_admin.py` — the `hash-api-keys` subcommand is **deprecated/refused** (plaintext column was dropped). No active operational subcommands.
- `/home/flask/smn/article_post_process.py:1436` `backfill_site_wrapper(force=False)` — re-wraps existing SMN articles in the latest site shell; `--force` flag.
- No `migrate_*` / `import_*` / `seed_*` files exist anywhere outside `/home/flask/migrations/`.

**WP → Postgres user migration:** the `users.legacy_phpass_hash` column exists in the schema (models.py:29) but **no importer code exists in the repo**. The column is sized to hold WP UMP phpass hashes; it appears to be intended for a future import that is not yet written. `users.legacy_wp_level` is sync'd by the DB trigger from `users.tier`, not from a WP import.

## 12. Known TODOs / Gaps

(grep `TODO|FIXME|XXX|HACK|F3` across Python; capped at 40)

| File:line | Comment |
|---|---|
| `/home/flask/web/app.py:605` | `TODO(F3): enforce aud="tw2-appserver" and iss="tw2-web" in appserver's decode (currently appserver does not pass these...)` — **stale: appserver DOES enforce both at 16 separate jwt.decode call sites.** Safe to close the TODO. |
| `/home/flask/smn/article_post_process.py:1242` | `# TODO: determine from data if needed` (market_family) |
| `/home/flask/site/generate_security_pages.py:79` | `# TODO(prod-cutover): swap to https://tradewave.ai/.` |
| `/home/flask/smn/generate_tw_security_pages.py:63` | `# TODO(prod-cutover): swap to https://tradewave.ai/.` |
| `/home/flask/site/generate_home_page.py:109` | `# TODO(prod-cutover): switch to https://tradewave.ai/ when we cut over.` |
| `/home/flask/site/generate_email_newsletter.py:14` | `# Render against live TW2 data layer (NOT yet implemented - TODO when ...)` |
| `/home/flask/site/generate_email_newsletter.py:32,524` | "Stubbed (TODO when TW2 data layer lands)" and "Stubs for TW1 data layer (TODO when TW2 grows equivalents)" |

No FIXME/XXX/HACK lines found in code (only in `.log` artifacts which are excluded).

## 13. Tests

`pytest.ini` markers: `db`, `unit`. testpaths=tests. pythonpath = `.`, `web`, `appserver/appserver` (so tests can `from models import ...` and `from app import ...`).

| File | Coverage | Marker | DB? |
|---|---|---|---|
| `tests/test_tier_compat.py` | `web/tier_compat.py` — anti-inversion assertions | `pytest.mark.unit` | No |
| `tests/test_sealed_session.py` | `web/app.py::_read_sealed_session` 5 branches | `pytest.mark.unit` | No |
| `tests/test_security_audit_2026_05_08.py` | Security audit; some tests probe `127.0.0.1:5000` and **auto-skip** if appserver not reachable | `pytest.mark.unit` | No (but reaches live appserver if up) |
| `tests/test_lazy_create_user.py` | `web/app.py::lazy_create_user` (happy + race + email-change + audit) | `pytest.mark.db` | **Yes** — needs `tradewave_test` |
| `tests/test_webhook_idempotency.py` | `web/app.py::webhook_stripe` primitives (StripeEvent dedup + `_json_safe`) | `pytest.mark.db` | **Yes** |

`tests/conftest.py` rewrites POSTGRES_DSN to point at `tradewave_test` and asserts; refuses to run against `tradewave`. Reads `/etc/tradewave/secrets.env` at import time (need flask user via `sudo -u flask`).

**Makefile targets** (`/home/flask/Makefile`): `test`, `test-unit`, `test-db`, `test-tier`, `test-webhook`, `test-session`, `test-user`. All use `sudo -u flask /home/flask/venv/bin/python -m pytest`.

DB-test prep (per `tests/README.md`):
```
sudo -u postgres psql -c "DROP DATABASE IF EXISTS tradewave_test;"
sudo -u postgres psql -c "CREATE DATABASE tradewave_test OWNER tradewave;"
pg_dump --schema-only --no-owner <prod_db> | psql tradewave_test
```

## 14. Logging

`/var/log/tradewave/` files (current dev box) and writer:

| File | Writer |
|---|---|
| `appserver.access.log` / `.error.log` | gunicorn (tradewave-appserver.service) |
| `appserver.log` | `logging.basicConfig(filename=...)` from appserver.py:131 |
| `article-processor.log` | tradewave-article-processor.service StandardOutput=append |
| `blog-queue.log` | tradewave-blog-queue.service StandardOutput=append |
| `web.access.log` / `.error.log` | gunicorn (tradewave-web.service) |
| `backup.log` | ops/backup_db.sh |
| `restore_drill.log` | ops/restore_drill.sh |
| `soak.log` | ops/soak_monitor.sh |
| `uptime.log` | ops/uptime_check.sh |
| `mailerlite_lifecycle.log` | once-per-minute durable lifecycle worker on the web box |
| `scorecard.log` | cron `site/generate_scorecard.py` (web-side cron) |
| `security_pages.log` | cron `site/generate_security_pages.py` (web-side cron) |
| `select_news.log` | cron `smn/select_news_articles.py` (app-side cron) |
| `daily_queue.log` | cron `smn/daily_article_queue.py` (app-side cron) |
| `update_client.log` | `/etc/crontab` `update_client2.py` (app-side cron) |

Logrotate `/etc/logrotate.d/tradewave`:
```
/var/log/tradewave/*.log { daily rotate 14 compress delaycompress missingok notifempty copytruncate create 0644 flask flask }
/home/flask/appserver/appserver/appserver.log { daily rotate 14 compress delaycompress missingok notifempty copytruncate create 0644 flask flask }
```
14-day retention; copytruncate (no SIGHUP needed).

Additional log files in tree:
- `/home/flask/appserver/appserver/add_to_blog_queue.log` (10K — written by appserver runtime)
- `/home/flask/appserver/appserver/chatbot_questions.log` (~700B)
- `/home/flask/smn/debug.log` (1.3MB, gitignored)
- `/home/flask/smn/logs/news_runs.jsonl` (article_processor JSONL — explicitly under `/home/flask/smn/logs/`)
- `/home/flask/data_updater/update_client2_output{1,2,3,4}.txt` (legacy outputs from `/etc/crontab` entries that mix `/etc/crontab` and the flask user crontab)

## 15. Other notable findings

- `/home/flask/.env` (mode 600 flask) exists but is unreadable by me; outside `.gitignore` (the file `.env` is gitignored, but the LIST item says ".env" is excluded). Probably holds a small subset of secrets for ad-hoc python runs.
- `/etc/crontab` contains a stale set of `flask` user entries pointing to `/home/flask/data_updater/update_client2.py` (4 runs/day) that PREDATE the formal `flask` user crontab. There's a one-line `36 23 * * * root` invocation that uses `set -a; . /etc/tradewave/secrets.env; set +a` correctly. The other four entries (`10 18`, `06 19`, `31 22`, `05 16`) lack `set -a; . secrets.env`, so they run without env vars. Plus `1 1 1 * * root certbot renew`.
- `/etc/systemd/system/tradewave-web.service` sets `Environment=TW2_PUBLIC_HOST=192.168.1.176` but the drop-in `override.conf` rewrites it to `tw2.trxstat.com` and adds `TW2_AUTH_CALLBACK_URL=https://tw2.trxstat.com/auth/callback`. The drop-in is currently the source of truth.
- `app.run(host='0.0.0.0',debug=False, port=7171)` at `smn/blog_queue.py:958` means blog-queue listens on all interfaces. On split topology, only smn (on app box) calls it via `config.TW2_BLOG_QUEUE_SERVER=http://localhost:7171/`, so binding to 0.0.0.0 should be fine but could be reduced to 127.0.0.1.
- `appserver.wsgi`, `appserver_prod.sh`, `appserver_stage.sh` exist but the actual entrypoint used by the systemd unit is `appserver:app` (gunicorn module:variable form). The shell scripts are dev-only artifacts.
- `data_updater/config.py` is a separate stale config file containing prod IPs. It is **shadowed by** the top-level `/home/flask/config.py` because `update_client2.py:20` does `sys.path.insert(0, '/home/flask'); import config` — so `data_updater/config.py` is never actually imported by tier-level code. Could be deleted, but safe to leave.
- `config.py` has shared values that are app-only (autotrade strategies lines 128-143, ml_score_*, available_resources etc.) and web-only (TIER_FEATURES, MAILERLITE_*, ROLE_BYPASSES_TIER) mixed in the same file. Both tiers import the full module. This is fine but means changes to app-only constants ship to web and vice versa.
- `config.useUMP = False` (config.py:105) — TW2 unauthenticated dev mode is the active path; appserver decode of `wp_userid`/`country_code`/`zip`/`skey` in the `/login/...` route is gated by `useUMP`.

---

## Unresolvable from dev box

The following cannot be determined from the dev codebase + dev config and must be answered by the user or discovered on the staging hosts themselves:

1. **Are systemd units already installed on the staging boxes?** The dev box has `/etc/systemd/system/tradewave-{appserver,article-processor,blog-queue,web}.service` plus a `tradewave-web.service.d/override.conf`. We don't know if these have been pushed to either staging box yet.
2. **Does each staging box have `/etc/tradewave/secrets.env`?** And if so, with what per-env overrides (which Stripe + WorkOS clients, which DSN, which IPs/URLs)? Specifically:
   - Is the staging WorkOS app `rapid-fish-71-staging.authkit.app` or a different staging tenant?
   - Is staging Stripe still test mode (`pk_test_…`) on staging, or is staging-prod using a separate live key? (Currently all keys in secrets.env are `*_test_*`.)
   - What is the staging Postgres password / does the user `tradewave` exist with that password on staging-web?
   - What value should `TW2_APPSERVER_IP` take on each box (presumably `10.0.0.92` on web for reaching Redis on app, and `10.0.0.92` on app for itself)?
   - What value should `TW2_WEBSERVER_IP` take (presumably `10.0.0.94` on app for reaching Redis on web, and `10.0.0.94` on web for itself)?
   - `TW2_APPSERVER_URL`: is it `http://10.0.0.92:5000` for web→app over VLAN?
3. **Has the staging Postgres been provisioned?** With `gen_random_uuid()` available (pgcrypto extension), with the `tradewave` user + `tradewave` database, and the schema either created by hand or pulled from a dump? Has `alembic upgrade head` been run, and where is alembic_version stamped?
4. **Has the staging WorkOS app been created?** Including the AuthKit redirect URI `https://tw2.trxstat.com/auth/callback` (or whatever the staging public host is) and the AuthKit hosted-UI domain.
5. **Has the staging Stripe webhook endpoint been registered** to point at `https://<staging-web>/webhooks/stripe`?
6. **What DNS exists for the staging boxes?** Specifically: is `tw2.trxstat.com` pointed at 185.53.209.8 (web)? Is `smn-dev.trxstat.com` pointed at the app box (185.53.209.8 or somewhere else)? What about a separate `app1stage.trxstat.com` or similar for the app box?
7. **TLS:** Do staging certs exist for `tw2.trxstat.com` and `smn-dev.trxstat.com`? Is certbot already configured? The dev-box `/etc/crontab` has `1 1 1 * * root certbot renew` but the staging boxes may or may not.
8. **Are the 17 `*_symbols.csv` files going to be rsync'd to the web box** (for `web/report_renderer.py:410`), or will the code be changed to fetch them from the app box over HTTP? Currently the path is hardcoded to `/home/flask/data/`.
9. **Are `/home/flask/web-react/build/`, `/home/flask/site/templates/`, `/home/flask/site/static/`, and `/var/www/tradewave/` going to be present on the web box** at deploy time? They come from running the React build + the `site/generate_*` scripts; the bootstrap will need to either run those scripts post-install or rsync the artifacts.
10. **Is `/var/www/smn/` (the 201M of generated SMN articles) going to live on the app box** (since smn/publish_article.py writes there from the app tier) **or on the web box** (since nginx serves it under `smn-dev.trxstat.com`)? If on app, the smn-dev vhost must run on app or the app box must export the dir to the web box.
11. **The article-queue Redis split is ambiguous:** `smn/article_processor.py:22` and `smn/select_news_articles.py:524` and `smn/daily_article_queue.py:275` use `localhost:6379 db=3` (so app-box-local), but `smn/publish_article.py:242` and `smn/rebuild_news_home.py:122` and `smn/generate_security_pages.py:241` use `config.webserver_ip:6379 db=3` (so web-box). Is the intended pipeline that articles are *queued* on app-local Redis and *published* via web-box Redis db=3 (two different streams), or is one of these wrong? The bootstrap scripts need to be told which redis instance holds `news_article_queue`.
12. **Is `pg_dump`/`psql` installed on the web box?** `ops/backup_db.sh` and `ops/restore_drill.sh` both require them. `restore_drill.sh` also requires a sudoers entry letting flask invoke `sudo -u postgres psql` without a password.
13. **What user runs the cron entries on each box?** Currently all flask-user cron is split: WEB cron entries (uptime, backup_db, soak_monitor, site/generate_scorecard, site/generate_security_pages) belong on the web box; APP cron entries (smn/select_news_articles, smn/daily_article_queue) belong on the app box; and the `/etc/crontab` `update_client2.py` belongs on the app box. We don't know if these crontabs have been installed on the right boxes yet.
14. **Source of `config.post_endpoint_url` / `config.tags_endpoint_url` / `config.redirect_endpoint_url`** — these are referenced by `smn/blog_tools.py`, `smn/create_report.py`, `smn/generate_top10_sr.py`, `smn/set_redirect.py`, `site/lib/blog_tools.py` but **NOT defined in `/home/flask/config.py`**. They appear to be expected to be derived from `config.wordpress_url` at runtime via WordPress paths, but no derivation code exists. If any of these code paths execute on staging, they will fail with AttributeError. Need user confirmation whether those WP-publish paths are still active in TW2.
15. **Is the legacy `data_updater/config.py` ever loaded** at runtime in some path I missed, or can it be ignored? The grep shows only `update_client2.py` and EOD_downloader_bulk* do `sys.path.insert(0, '/home/flask'); import config`, so they pick up the top-level one, not the local data_updater/config.py. But if any other script in data_updater/ runs from data_updater/ working dir without that sys.path insert, it could shadow.
16. **The `legacy_phpass_hash` column** has no importer code. Was a WP→Postgres migration ever performed on staging, or is staging starting empty with `users` rows created lazily via `/auth/callback` from WorkOS? If the former, where is the import script? The README/migrations don't reference one.
17. **Sentry DSN** is empty in secrets.env. Is Sentry expected to be enabled on staging, and what's the DSN?
18. **MailerLite application writes are intentionally disabled on staging.**
    Keep `MAILERLITE_OUTBOUND_ENABLED=0`; `config.py` also requires
    `TW2_ENV=prod`. Validate outbox state with the worker's `--dry-run` mode and
    do not point staging at production lifecycle trigger groups.
19. **`TW2_APPSERVER_IP=192.168.68.151`** in dev secrets.env is anomalous (the dev box is 192.168.1.176). Is this a stale value that needs replacement, or is there a third remote service at that address? It is read by `smn/email_tools.py:25` (`redis.Redis(host=config.appserver_ip, port=6379, db=2)`); on dev this would fail to connect unless 192.168.68.151 actually responds.
20. **Does the staging-app box need a `data_updater/symbols_US.txt`** (or other downloadable seeds)? Currently `data_updater/EOD_downloader_bulk.py` and `create_symbol_file2.py` re-fetch from EODHD on demand.
21. **Stripe Price IDs / Product IDs** — config.py:32 says "Create 4 Products in Stripe dashboard, copy each Price ID" but no Price IDs are stored in config.py. They must be discovered dynamically via `stripe.Price.list(...)` (see `web/app.py:805`). Confirm staging Stripe has the 4 products + prices created.
22. **The `TW2_PUBLIC_HOST` override** in `tradewave-web.service.d/override.conf` is currently `tw2.trxstat.com`. Will the same hostname route to both dev (192.168.1.176) and staging-web (185.53.209.8), or does staging need a different hostname (e.g., `tw2-stage.trxstat.com`)? The hardcoded literals in `site/templates/*`, `site/generate_insights.py`, `web/report_renderer.py:45`, `site/generate_home_page.py:110`, etc. all bake `tw2.trxstat.com` into generated HTML — these will need re-generation per env.

---

# 16. TW1-prod Cron Coverage → TW2 Web Gap

Source: TW1 production `/etc/crontab` provided by user 2026-05-14. Goal: TW2 web tier must have AT LEAST the dynamic-content functionality TW1 prod provides.

## 16.1 Full coverage matrix

| TW1 cron command | TW1 schedule | TW2 code present? | TW2 cron present (dev)? | Gap class |
|---|---|---|---|---|
| `select_news_articles.py` | `0 2 * * 1-5` | `smn/` ✓ | yes — but `0 2 * * *` (7d not 5d) | **schedule mismatch** |
| `daily_article_queue.py` | `0 3 * * 1-5` | `smn/` ✓ | yes — but `0 3 * * *` (7d not 5d) | **schedule mismatch** |
| `delete_old_blogs.py` | `35 3 * * *` | ✗ | ✗ | **dropped in TW2** (no WordPress to clean) |
| `generate_security_pages.py` | `30 5 * * 1-5` | `site/` ✓ | yes ✓ | **ok** |
| `generate_tw_security_pages.py` | `40 5 * * 1-5` | `smn/` ✓ | **no** | **cron-only gap** |
| `m_daily_ai_pick_social.py` | `10 6 * * 0-5` | ✗ | ✗ | **code+cron gap — need TW1 source** |
| `home_opportunities.py` | `4 0 * * *` | ✗ | ✗ | **code+cron gap — need TW1 source** |
| `generate_home_page.py` | `0 7 * * 1-5` | `site/` ✓ | **no** | **cron-only gap** |
| `send_daily_ai_pick.py` | `30 7 * * 1-5` AND `41 7 * * 1-5` | ✗ | ✗ | **code+cron gap — need TW1 source** (TW1 had 2 entries — bug or intentional double-send) |
| `send_smn_emails.py` | `0 7 * * 1-5` + `0 9 * * 0` | ✗ | ✗ | **code+cron gap — need TW1 source** |
| `update_news_quotes.py` | `* * * * 0-5` (every min, 6 days) | ✗ | ✗ | **code+cron gap — need TW1 source** |
| `generate_scorecard.py` | `*/10 9-16 * * 1-5` | `site/` ✓ | yes — but `*/10 * * * 1-5` (24h not market hrs) | **schedule mismatch** |
| `generate_ticker_pages.py` | `0 2,9-16 * * *` | `site/ticker_pages/` ✓ | **no** | **cron-only gap** |
| `webinar_page_generator.py` | `0 10-17 * * *` | ✗ | ✗ | **code+cron gap — need TW1 source** |
| `rebuild_news_home.py` | (commented in TW1) | `smn/` ✓ | n/a | **leave disabled** — TW1 disabled it |

## 16.2 What plumbing TW2 already has

For the 5 "code+cron gap" scripts, here's what TW2 already provides as building blocks:

| TW1 script | What TW2 plumbing exists | What's missing |
|---|---|---|
| `home_opportunities.py` | `site/generate_home_page.py` knows the CSV schema; `smn/get_top10_data.py` has `get_opp_list()` + login helpers; the schema is fixed at `start_date,symbol,company_name,days,direction,SR,AvgP,median,TWA,TWR,day_range,mode,pattern_param` | **The high-level filter logic**: which resource IDs, what SR cutoff, what max age, dedup strategy. Inferable but risky to guess. |
| `send_smn_emails.py` | `smn/email_tools.py` has full Mailerlite primitives: `create_campaign`, `schedule_campaign`, `get_email_groups`, `assign_subscriber_to_a_group` | **The high-level logic**: which articles to feature today, subject line, template HTML, schedule time, weekly recap vs daily content. |
| `send_daily_ai_pick.py` | Mailerlite primitives in email_tools.py; daily AI pick data structure unknown | **The compose+send logic** + (TW1 had it scheduled twice — clarify whether `30 7` and `41 7` are intentional or a bug). |
| `m_daily_ai_pick_social.py` | Config has `PUBLER_*` and `FACEBOOK_*` credentials but **no TW2 Python code uses them** | **All of it** — Publer API client, FB Graph posting, X via Publer, content composition. |
| `update_news_quotes.py` | `smn/get_price_eod.py` has `get_current_price()`, `get_quote_details()`, `_try_realtime_service()`; `smn/publish_article.py` knows how to write quote HTML | **The "find-and-replace prices in existing rendered pages" loop logic.** Pages to scan, CSS selectors / regex to find prices, throttling. |
| `webinar_page_generator.py` | Nothing — TW1 had it at `/home/flask/webinar/` (separate dir) | **All of it**. May be deprecated in TW2 — confirm whether the webinar feature is shipping or being dropped. |

## 16.3 Proposed staging-web crontab

Once we get TW1 source and port the 5 missing scripts, this is what should land on `tw2-stage-web`'s flask user crontab (mirrors TW1 prod schedules). TW2 paths and `/var/log/tradewave/` log destinations:

```cron
# === System health (TW2-original, not from TW1) ===
*/5 * * * * /home/flask/ops/uptime_check.sh >/dev/null 2>&1
30 3 * * * /home/flask/ops/backup_db.sh >/dev/null 2>&1
*/30 * * * * /home/flask/ops/soak_monitor.sh >/dev/null 2>&1

# === SMN Article Pipeline (cross-tier: select+queue cron on WEB? or on APP?
#     TW1 ran from /home/flask/blog/ on web box. TW2 puts smn/ on app box. ⚠
#     If kept on web here, requires smn/ rsync'd to web. If moved to app,
#     these two lines belong in the staging-app crontab instead.) ===
0 2 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python select_news_articles.py >> /var/log/tradewave/select_news.log 2>&1
0 3 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python daily_article_queue.py >> /var/log/tradewave/daily_queue.log 2>&1

# === Security Pages (SMN light + TW dark) ===
30 5 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_security_pages.py >> /var/log/tradewave/security_pages.log 2>&1
40 5 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python generate_tw_security_pages.py >> /var/log/tradewave/security_pages.log 2>&1

# === Social Media (BLOCKED — needs TW1 source) ===
# 10 6 * * 0-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py >> /var/log/tradewave/m_daily_ai_pick_social.log 2>&1

# === TradeWave Homepage + Daily AI Pick ===
# 4 0 * * * — home_opportunities.py — BLOCKED, needs TW1 source
# 0 7 * * 1-5 — generate_home_page.py — code exists, cron entry:
0 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_home_page.py >> /var/log/tradewave/home_page.log 2>&1
# 30 7 * * 1-5 — send_daily_ai_pick.py — BLOCKED, needs TW1 source

# === SMN Emails (BLOCKED — needs TW1 source) ===
# 0 7 * * 1-5 — send_smn_emails.py daily
# 0 9 * * 0   — send_smn_emails.py weekly recap

# === Live Quote Updates ===
# * * * * 0-5 — update_news_quotes.py — BLOCKED, needs TW1 source
*/10 9-16 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_scorecard.py >> /var/log/tradewave/scorecard.log 2>&1

# === Ticker pages ===
0 2,9-16 * * * set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/site/ticker_pages && /home/flask/venv/bin/python generate_ticker_pages.py >> /var/log/tradewave/ticker_pages.log 2>&1

# === Webinar Page (BLOCKED — needs TW1 source, or confirm dropped) ===
# 0 10-17 * * * — webinar_page_generator.py
```

Differences from TW2 dev crontab:
- **fix**: `select_news_articles` / `daily_article_queue` constrained to `1-5` (was `* *`)
- **fix**: `generate_scorecard.py` constrained to `9-16` market hours (was all day)
- **add**: `generate_tw_security_pages.py` at `40 5 * * 1-5`
- **add**: `generate_home_page.py` at `0 7 * * 1-5`
- **add**: `generate_ticker_pages.py` at `0 2,9-16 * * *`
- **add**: 5 placeholders for scripts still to be ported

## 16.4 What's needed to close the goal

To reach functional parity with TW1 web, the following TW1 prod files must be ported to TW2:

```
/home/flask/blog/home_opportunities.py
/home/flask/blog/send_smn_emails.py
/home/flask/blog/send_daily_ai_pick.py
/home/flask/blog/m_daily_ai_pick_social.py
/home/flask/blog/update_news_quotes.py
/home/flask/webinar/webinar_page_generator.py   # may be deprecated
```

Cheapest way to share them with the porting agent:

```bash
# From any host with SSH access to TW1 prod:
mkdir -p /tmp/tw1_blog
scp root@<TW1-prod-host>:/home/flask/blog/{home_opportunities,send_smn_emails,send_daily_ai_pick,m_daily_ai_pick_social,update_news_quotes}.py /tmp/tw1_blog/
scp root@<TW1-prod-host>:/home/flask/webinar/webinar_page_generator.py /tmp/tw1_blog/ 2>/dev/null
chmod -R o+r /tmp/tw1_blog
```

Or paste each script's contents in the porting conversation. Either path unblocks the goal.

---

# 17. TW1 → TW2 Scripts: Ported (2026-05-14)

The 5 previously-blocked code+cron-gap scripts have been ported from inference using existing TW2 plumbing. Each is marked with `TW1_SPEC:` comments inline where I made an assumption about TW1 behavior that the user should validate.

| TW1 script | TW2 location | Approach |
|---|---|---|
| `home_opportunities.py` | `/home/flask/site/home_opportunities.py` | Login via `SERVICE_API_KEY`, query `/OppList4/` for resource_id=2 (S&P 500) in both `pe` and `cons` modes for both day_range buckets, filter direction=Long & SR≥0.5 & within 90-day forward window, dedupe by (symbol,date) keeping highest SR, look up names via `/NameFromTicker/`, write CSV. **TWA/TWR formulas are best-effort approximations** (placeholder pending TW1 reference). |
| `send_smn_emails.py` | `/home/flask/smn/send_smn_emails.py` | Auto-detects daily vs weekly mode from day-of-week. Reads `/var/www/smn/posts.json`, filters by published_date within window (28h daily / 7d weekly), composes inline-styled HTML, uses `email_tools.create_campaign` + `schedule_campaign`. Requires `SMN_EMAIL_GROUP_ID` env var. Daily lock file in `/var/log/tradewave/`. |
| `send_daily_ai_pick.py` | `/home/flask/site/send_daily_ai_pick.py` | Parses `/var/www/tradewave/daily-ai-pick.html` (title + table), wraps in clean email template with inline styles, rewrites relative URLs to absolute via `config.domain_root`, schedules Mailerlite campaign. Refuses to send if HTML > 24h old. Lock prevents TW1's duplicate 30 7 + 41 7 cron firing. |
| `m_daily_ai_pick_social.py` | `/home/flask/site/m_daily_ai_pick_social.py` | Parses top pick from daily-ai-pick.html, posts to FB Page via Graph API v18.0 and to X via Publer v1 `/posts/schedule`. **Defaults to dry-run** — requires `--send` to actually publish. Skip flags `--skip-fb` and `--skip-x` for partial-network operation. Lock only if at least one network succeeded. |
| `update_news_quotes.py` | `/home/flask/smn/update_news_quotes.py` | Refreshes `/var/www/smn/assets/quotes.json` + `/var/www/tradewave/assets/quotes.json`. Fetches 7 market-bar symbols (GSPC, DJI, IXIC, VIX, CL, NG, GC) via `get_quote_details()` (which uses the local realtime service first, falls back to EODHD). Each run ~3-5s. Atomic write. Fail-soft if all lookups fail — keeps existing JSON. |
| `generate_webinar_page.py` | **PORTED** | Reads the published TradeWave Webinars Sheet, renders only future `wb001` sessions at `/webinars/`, keeps `/webinar` as a compatibility alias, and writes the public schedule used by the conditional home-footer link. |

## 17.1 Validated on dev

- All 5 files `py_compile` clean
- All 73 existing tests still green (`make test`)
- `update_news_quotes.py --dry-run` end-to-end run: 7/7 quotes fetched in 3.7s, JSON payload valid (verified manually against EODHD)

## 17.2 Updated staging-web crontab

This replaces §16.3 — all 14 active entries plus `update_client2.py` (which goes in `/etc/crontab` not the flask user crontab).

```cron
# === System health ===
*/5 * * * * /home/flask/ops/uptime_check.sh >/dev/null 2>&1
30 3 * * * /home/flask/ops/backup_db.sh >/dev/null 2>&1
*/30 * * * * /home/flask/ops/soak_monitor.sh >/dev/null 2>&1

# === Durable MailerLite application lifecycle (no writes on staging) ===
* * * * * { test -r /etc/tradewave/secrets.env && set -a && . /etc/tradewave/secrets.env && set +a && cd /home/flask && /home/flask/venv/bin/python /home/flask/web/mailerlite_lifecycle.py --limit 15; } >> /var/log/tradewave/mailerlite_lifecycle.log 2>&1

# === SMN Article Pipeline ===
# These reference smn/ which lives on the APP box. If smn/ is rsync'd to
# the web box too (per the "ship everything to both boxes" plan), keep
# them here. Otherwise move to /home/flask/ops/crontab.app.
0 2 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python select_news_articles.py >> /var/log/tradewave/select_news.log 2>&1
0 3 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python daily_article_queue.py >> /var/log/tradewave/daily_queue.log 2>&1

# === Security Pages ===
30 5 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_security_pages.py >> /var/log/tradewave/security_pages.log 2>&1
40 5 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/smn && /home/flask/venv/bin/python generate_tw_security_pages.py >> /var/log/tradewave/security_pages.log 2>&1

# === Social Media ===
10 6 * * 0-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py --send >> /var/log/tradewave/m_daily_ai_pick_social.log 2>&1

# === TradeWave Homepage + Daily AI Pick ===
4 0 * * * set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/home_opportunities.py >> /var/log/tradewave/home_opportunities.log 2>&1
0 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_home_page.py >> /var/log/tradewave/home_page.log 2>&1
30 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/send_daily_ai_pick.py >> /var/log/tradewave/daily_ai_pick.log 2>&1

# === SMN Emails ===
0 7 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/smn/send_smn_emails.py >> /var/log/tradewave/smn_email_cron.log 2>&1
0 9 * * 0 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/smn/send_smn_emails.py >> /var/log/tradewave/smn_email_cron.log 2>&1

# === Live Quote Updates ===
* * * * 0-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/smn/update_news_quotes.py >> /var/log/tradewave/smn_quote_injection.log 2>&1
*/10 9-16 * * 1-5 set -a; . /etc/tradewave/secrets.env; set +a; /home/flask/venv/bin/python /home/flask/site/generate_scorecard.py >> /var/log/tradewave/scorecard.log 2>&1

# === Ticker pages ===
0 2,9-16 * * * set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask/site/ticker_pages && /home/flask/venv/bin/python generate_ticker_pages.py >> /var/log/tradewave/ticker_pages.log 2>&1

# === Webinar Page — DROPPED in TW2 (no source, no code; confirm intentional) ===
```

Note: I dropped TW1's redundant `41 7` send_daily_ai_pick.py entry. The lock file in `send_daily_ai_pick.py` makes a second daily call a no-op anyway — but keeping the schedule clean is preferable.

## 17.3 Required secrets.env additions for staging

In addition to the existing TW2 keys, the new scripts need:

```
SMN_EMAIL_GROUP_ID=<mailerlite group id for SMN subscribers>
DAILY_AI_PICK_GROUP_ID=<mailerlite group id for daily AI pick subscribers>   # optional; falls back to SMN
MAILERLITE_OUTBOUND_ENABLED=0
MAILERLITE_TRIAL_STARTED_GROUP_ID=
MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID=
MAILERLITE_WINBACK_GROUP_ID=
TW2_API_BILLING_PORTAL_CONFIGURATION_ID=PLACEHOLDER_RUN_API_STRIPE_SEED_AND_PERSIST_BPC_ID
```

PUBLER_*, FACEBOOK_*, MAILERLITE_TOKEN, EOD_TOKEN are already in secrets.env (we just verified all are populated on dev).

Before enabling or deploying the staging API console, run the API catalog
seeder with the environment's Stripe TEST key. It validates the complete TEST
catalog, creates or updates one dedicated non-default API Billing Portal
configuration, and prints the exact value to persist:

```
sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask && ./venv/bin/python web/api_portal/create_api_products.py'
```

Replace the generated placeholder with the printed
`TW2_API_BILLING_PORTAL_CONFIGURATION_ID=bpc_...` line in the WEB box's
`/etc/tradewave/secrets.env`. Re-running is the validation step and is
idempotent; it refuses duplicate active products/prices and refuses Stripe's
shared default portal. Use the same TEST-only procedure for dev and persist the
printed value in dev's WEB secrets. `ops/deploy.sh staging` fails before service
restart while the value is absent or still a placeholder.

The blank lifecycle IDs and disabled flag are deliberate on staging. Production
gets the three reviewed trigger IDs but stays disabled until every automation
is active and the outbox/backfill previews have been checked. See the current
deployment addendum at the top of this file and `ops/OPERATIONS.md` §3a.
