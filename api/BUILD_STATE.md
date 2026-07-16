# TradeWave API + MCP - BUILD STATE (working control doc)

Live state of the "finish the API + MCP product" build. Update as phases complete.
Companion to: `api/STRATEGY_REVIEW_2026-05.md` (why), `api/PATTERNCARD_SPEC.md` (contract),
`api/openapi.yaml` + `api/MCP_TOOLS.md` (frozen surface). Started 2026-06-02 on dev .176,
branch `feature/api-mcp`.

## Locked decisions (from the operator, 2026-06-02)
1. **IA = dedicated public developer portal.**
   - `developers.tradewave.ai` (prod) / `developers-dev` / `developers-stage`.trxstat.com -
     PUBLIC, no-login: marketing landing + technical docs/reference + learning/tutorials + MCP setup + cookbook.
   - `api.tradewave.ai/v1` - the JSON API only. `mcp.tradewave.ai` - the MCP endpoint.
   - Console (keys/usage/billing) stays GATED at `tradewave.ai/account/api`.
2. **Mature DX = all four:** Python + TypeScript SDKs; interactive "Try it" playground;
   Postman collection + OpenAPI download + multi-language (curl/Python/JS) snippets; MCP agent
   cookbook (Claude/Cursor/ChatGPT + the TradeWave + Liquid recipe).
3. **ML model = metered freemium taste** (as already coded; NO change): Free 5/day, Dev 100/day,
   Pro/Business unlimited; daily-pick ML always free; graceful upgrade nudge when spent.
4. **Pricing:** Free $0 / Dev $39 / Pro $199 / Business $599 (base, locked) PLUS
   - annual ~17% off (Dev $390 / Pro $1,990 / Business $5,990),
   - Founder's deal: first 100, $99/mo Pro (50% off) 12mo, for logo + tracked-record testimonial,
   - free Dev-tier API key bundled into paid web subs (analyst/strategist -> api dev via inheritance).
   - Metered Business overage = DEFERRED (decide from real traffic). Stripe TEST mode on dev.
5. **Where:** all dev work on .176 `/home/flask`, branch `feature/api-mcp`. NOTHING touches
   staging/prod directly - author the operator's deploy steps (hard rule).

## Invariants (never violate - from PATTERNCARD_SPEC + CLAUDE.md)
- PATTERNS ONLY: no raw OHLCV / last price / price-by-date / price levels in any public response;
  all movement as percentages; seasonal curve is a 0-100 normalized index, never a price.
- `historical_win_rate` != `ml_win_prob` (distinct fields, never both "win rate").
- `years` + window labels stay STRINGS; market ids are permanent '0'..'16'.
- No em-dashes in user-facing copy (use ' - '); date RANGES use en-dash via tw_dateformat.
- Exact disclaimer on every PatternCard. Fail-fast on real errors; fail-soft only per-symbol gaps.

## Dev-box facts (verified 2026-06-02)
- secrets.env has POSTGRES_DSN, APPSERVER_JWT_SECRET (= HMAC fallback; no explicit
  API_KEY_HMAC_SECRET), SERVICE_API_KEY, TW2_APPSERVER_URL, STRIPE_* (test), WORKOS_*, TW2_ENV.
  MISSING (add later, dev defaults work): TW2_API_PUBLIC_HOST, TW2_MCP_PUBLIC_HOST,
  TW2_DEVELOPERS_PUBLIC_HOST.
- appserver live :5000, web tier :5500, nginx :80. Postgres up.
- venv-api built at /home/flask/venv-api (flask, gunicorn, psycopg2, redis, requests, httpx, mcp).
  requirements-api.txt added.
- schema.sql APPLIED to dev Postgres (api_keys, api_usage_daily, users.api_tier all present).

## Phase checklist
- [x] **0 Foundation:** branch reconciled; venv-api built; schema applied; gateway smoked
      end-to-end (markets/daily-pick/scan/analyze/score all 200, patterns-only verified, no
      price leak). Gateway runs: `nohup venv-api/bin/gunicorn -w 2 -b 127.0.0.1:8088 --pid
      /tmp/tw_api.pid apiserver.app:app`. Smoke key in /tmp/tw_smoke_key (pro tier).
      FIXED a flagship ML bug (see below). MCP smoke still TODO.
- [x] **1 Engine + web integration:** flagship ML mislabel FIXED + verified (flows through MCP);
      api_portal blueprint was already registered (+ set_user_loader); Stripe webhook now
      product_line-aware -> writes users.api_tier (model column added; never clobbers web tier
      / cross-downgrades); api_tier resolution validated e2e (NULL->pro/free->1mkt/dev->all);
      MCP server smoked (14 tools, BYOK env fallback, ValueError guard hardened).
      Minor follow-ups deferred to P2: _UPGRADE_URL hardcoded -> make env-driven; openapi.yaml
      /scan default limit (25) vs routes.py (10) mismatch.
- [x] **2 Developer surface:** COMPLETE. Full cohesive developer portal, all cross-linked,
      0 em-dashes across the whole portal, no price leaks. Pieces:
        - marketing (site/api_marketing/out/, 4 pages), docs (site/api_docs/, 7 pages + downloads).
        - LEARNING track: 8 authored+self-reviewed md articles -> site/api_learn/out/ (index +
          8 lessons) via site/api_learn/generate_learn_api.py (reuses docs shell; markdown lib).
          The Liquid/broker cookbook recipe is lesson 8 (recipe-tradewave-plus-broker).
        - EXTRAS: site/api_docs/generate_api_extras.py -> openapi.yaml + openapi.json +
          tradewave.postman_collection.json + .well-known/mcp.json. Linked from docs + playground.
        - PLAYGROUND: site/api_playground/generate_playground.py -> out/index.html. Live "Try it"
          console (BYOK localStorage, endpoint registry, PatternCard renderer, per-request
          curl/Python/JS). Calls API_BASE; needs the api-* tunnel live (P5) for real sends.
        - GATEWAY CORS added (apiserver/settings.py CORS_ORIGINS + app.py after_request):
          env-driven allowlist (developers/main hosts per env; API_CORS_ORIGINS or "*"); preflight
          via Flask automatic-OPTIONS; verified (allowed echoes ACAO, disallowed gets none).
        - portal_urls: added PLAYGROUND_URL; docs sidebar cross-links learn/playground/mcp + downloads.
      Per-endpoint multi-lang snippets: covered by the playground (3-language per-request) +
      quickstart; api-reference keeps curl. Docroot consolidation -> P5 deploy assembles
      /var/www/developers/ (root=marketing, /docs, /learn, /playground, /.well-known/mcp.json).
      DECISION (docroot): generators write to site/ staging dirs; P5 deploy assembles
      /var/www/developers/. Generators (re-run any time): site/api_marketing/generate.py,
      site/api_docs/generate_api_docs.py, site/api_docs/generate_api_extras.py,
      site/api_learn/generate_learn_api.py, site/api_playground/generate_playground.py.
      Live gateway: nohup venv-api gunicorn on :8088 (pidfile /tmp/tw_api.pid).
- [x] **3 SDKs:** COMPLETE + verified. Python `tradewave` (api/sdks/python; pip-installable, typed
      dataclasses, retries, errors; smoke-tested live against the gateway - daily_pick/scan/analyze
      green) + TS `@tradewave/sdk` (api/sdks/typescript; ESM, strict, zero-dep fetch; tsc --noEmit clean,
      builds dist/). Both v0.1.0, README + examples. Publish to PyPI/npm = operator GTM step.
- [x] **4 Pricing:** COMPLETE. Source of truth = apiserver/tiers.py: added price_annual
      (dev 390/pro 1990/business 5990 = 10x monthly = 2 months free, ~17% off) + FOUNDER dict
      (Pro 50% off 12mo, max 100, code FOUNDER) + bundle note on WEB_TIER_TO_API.
      - create_api_products.py: now creates monthly + annual prices per tier AND the Founder
        coupon (founder_pro_50_12mo, applies_to Pro) + promo code FOUNDER (idempotent, TEST-only).
        OPERATOR runs it once at integration: STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python
        web/api_portal/create_api_products.py  (NOT run during build).
      - routes_billing.py: price cache keyed by (tier, interval); checkout reads interval=month|year
        (+ subscription metadata interval); falls back to monthly if no annual price.
      - Public pricing page (site/api_marketing): correct annual math, "2 months free", Founder
        strip, "already subscribe? Analyst=Dev / Strategist=Pro" bundle note. Regenerated.
      - Console api_billing.html: monthly/annual toggle (updates price + hidden interval), annual
        note, Founder callout. Jinja2 parses; 0 em-dashes.
      Consumer-sub dev-key bundle = the existing api_tier inheritance (web analyst->api dev,
      strategist->pro); no separate charge. Webhook already product_line=api aware (P1).
- [x] **5 Ops:** COMPLETE + VALIDATED LIVE ON DEV. Authored: ops/systemd/{tradewave-apiserver,
      tradewave-mcpserver}.service (systemd-analyze verify clean), ops/nginx/tradewave-developer-portal.conf
      (api/mcp/developers blocks, SSE-tuned), ops/bootstrap_api_services.sh, ops/assemble_developer_portal.sh,
      deploy.sh edits, and ECOSYSTEM §7B + OPERATIONS + PROD_CUTOVER sections.
      VALIDATED ON DEV (full stack through nginx): bootstrap_api_services.sh ran clean -> both services
      now systemd-managed (tradewave-apiserver :8088 Type=notify healthz OK; tradewave-mcpserver :9090
      SSE listening). assemble_developer_portal.sh built /var/www/developers (26 files, no .py leak).
      nginx vhost installed on dev: developers-dev/ (200 html), /.well-known/mcp.json (200 json),
      /docs,/learn,/playground (200), postman (200); api-dev/healthz + /v1/markets (200, 15 mkts) via
      proxy; mcp-dev/sse real MCP handshake (event: endpoint / session_id). The nohup gateway is
      RETIRED - services are now proper systemd units on dev.
      OPERATOR-ONLY remaining (external, documented): cloudflared ingress + DNS for api./mcp./developers.
      per env (can't test without DNS); install nginx vhost + bootstrap on staging/prod; create_api_products.py.
      (old in-progress notes:) Facts: gateway = venv-api gunicorn 127.0.0.1:8088 apiserver.app:app
      (loopback ALL envs; nginx fronts); MCP = venv-api python -m mcpserver.server --transport sse
      --host 127.0.0.1 --port 9090 (env API_BASE_URL + TW2_MCP_PUBLIC_HOST; TRADEWAVE_API_KEY UNSET).
      cloudflared: single 'tw2' tunnel, all hosts -> localhost:80, nginx routes by server_name.
      Services co-located on the APP box; portal docroot + console on the WEB box.
      DONE: ops/deploy.sh edited (guarded app-tier api/mcp restart + venv-api sync + /healthz gate;
        web-tier portal assembly; both skip if unprovisioned, like the SMN-daemon guard). bash -n OK.
      AUTHORING via background workflow (api-mcp-ops): ops/systemd/tradewave-apiserver.service +
        tradewave-mcpserver.service; ops/nginx/tradewave-developer-portal.conf (api/mcp/developers
        server blocks, SSE-tuned mcp); ops/bootstrap_api_services.sh; ops/assemble_developer_portal.sh
        (generators + rsync -> /var/www/developers/{,docs,learn,playground,.well-known}); cloudflared
        ingress additions; ECOSYSTEM/OPERATIONS/PROD_CUTOVER sections.
      TODO after workflow: review artifacts; validate (nginx -t, systemd-analyze verify) on dev;
        optionally install+start the units on dev to replace the nohup gateway; confirm assemble script.
- [x] **6 Validate + adversarial review:** COMPLETE. 5-dimension adversarial workflow (patterns-only,
      security, contract, brand, regression) with LIVE gateway probing.
      HEADLINE: patterns-only PASSED with decisive proof (gateway strips every raw price the upstream
      ChartData4 carries - per_year price, 52W H/L, SMA, volume all dropped; curve is 0-100 index).
      FIXED + RE-VERIFIED LIVE:
        - HIGH path-injection on the appserver bridge: appserver_client._seg() URL-encodes every
          internal path segment + routes._clean_chart_args validates days_out/years/entry_date/symbol.
          Live: days_out=30/aaa -> 400, years=10/../x -> 400 (were 200).
        - MED query-string key leak: auth._extract_key drops ?api_key= (header-only). ?api_key -> 401.
        - MED playground XSS-by-construction: esc() escapes every response-derived field in renderCard.
        - MED /scan limit drift: routes default 10 -> 25 (matches openapi). Live default count 25.
        - MED ML-access doc contradiction: fixed openapi.yaml ml desc + api-reference + changelog +
          data-dictionary to the metered-every-tier model (were "gated to Pro").
        - MED "historical ML win rate" wording in marketing mcp -> "model's predicted win probability".
        - MED portal generator venv footer venv-api -> venv (the one with markdown/yaml/jinja).
        - LOW data-dictionary phantom yearly_paths/exit_pct -> real seasonal_curve {date,index} + per_year.
        - LOW neutral-bias next_step now OMITS order_ticket/copy_text/set_reminder (was null). Verified live.
        - polish: openapi version 1.0.0-draft -> 1.0.0.
      ACCEPTED/NOTED (not blocking): curve_summary is null on /scan cards (cost trade-off; populated on
        /analyze + /daily-pick); pre-existing em-dashes in OLD ops/*.sh comments (NEW surface = 0);
        TS examples/ excluded from tsc; stats.years(label) vs receipts.years_tested(+partial) off-by-one
        is documented expected behavior. NEW api surface: 0 em-dashes, 0 price leaks, disclaimer on every card.

## Notes / gotchas found
- The untracked working-tree copy on daily-pick-fixes was a PARTIAL snapshot restore (missing
  portal_urls.py); `feature/api-mcp` is the complete committed source. Reconciled onto it.
- portal_urls.py currently encodes the OLD IA (api-host/api + /docs). Must rework for developers. host.
- README claim "api_tier ALTER commented out" is STALE - schema.sql line 31 has it active.
- gunicorn entrypoint: see apiserver/app.py (module-level `app`).
- FIXED (Phase 1, committed to working tree, not yet git-committed): flagship ML mislabel.
  `/v1/scan` + `/v1/analyze` ranked long-hold setups (Sharpe-sorted); the ML model only covers
  holds up to ~90 days, so it returns None for them; the card wrongly said "Daily ML limit
  reached - upgrade for unlimited" even to unlimited Pro users. Fix: new `unavailable` ml_state
  + `_ml_attempted` flag (routes.py `_ml_state_for`, scan/analyze blocks), new `_ML_NOTES`
  entry (cards.py), and `ml_quota.refund()` so metered users are only charged for ML actually
  delivered. Also replaced silent `except Exception: pass` with logging.
- ML model horizon: scores holds up to ~90 days; None for >=120 (verified). Document this on
  the docs site + SDKs (set expectations: ML = shorter-horizon complement to seasonal).
- `_UPGRADE_URL` is hardcoded to tw2-dev.trxstat.com in routes.py - make env-driven (portal_urls
  / TW2_PUBLIC_HOST) before prod. (Phase 1/2 follow-up.)
- gunicorn HUP does NOT reload app code here - use a full restart (pidfile /tmp/tw_api.pid).
- DANGER: never `pkill -f` a pattern that also matches the running shell command (self-kill).
  Target gunicorn by `pgrep -x gunicorn` + /proc cmdline port filter, or use the pidfile.

## Phase 7 - Discoverability + SEO + dev exposure (2026-06-02, post-review)
- DEV NOW BROWSABLE: added cloudflared ingress for developers-dev / api-dev / mcp-dev (-> localhost:80,
  nginx host-routed) + created the developers-dev CNAME (`cloudflared tunnel route dns tw2 ...`).
  Live + verified public via the Cloudflare edge: https://developers-dev.trxstat.com (portal, all pages
  200), https://api-dev.trxstat.com/v1 (key-gated), https://mcp-dev.trxstat.com/sse. (api-dev/mcp-dev DNS
  pre-existed.) NOTE: the dev box's LOCAL resolver negative-caches; use external resolver to test from the box.
- HOME-PAGE DISCOVERABILITY (operator chose: footer): site/generate_home_page.py now imports portal_urls,
  exposes content.developers_url (= portal_urls.PORTAL_URL, per-env), and site/templates/index-dark-blue.html
  Resources footer column has a "Developers (API & MCP)" link. Regenerated home -> link live.
- SEO (site/lib/portal_seo.py NEW + wired into all 4 page generators):
  - per-page canonical + Open Graph + Twitter Card + JSON-LD (Organization + WebSite sitewide; WebAPI on
    the landing). FIXED: marketing pages were noindex,nofollow -> now index,follow (they are the primary
    SEO surface). Per-page canonicals correct.
  - site/api_docs/generate_seo_files.py NEW -> sitemap.xml (21 urls) + robots.txt (Sitemap pointer) +
    llms.txt (llmstxt.org map for AI agents - apt for MCP) + og-developers.png (1200x630 PIL card).
    Wired into ops/assemble_developer_portal.sh (runs last). All served 200 with correct content-types.
- OPERATOR GTM follow-ups (not code): submit sitemap to Google Search Console; list the MCP server in the
  MCP Registry / mcp.so / Glama / Smithery / PulseMCP + the ChatGPT app directory; set the per-env
  TW2_DEVELOPERS_PUBLIC_HOST so prod emits developers.tradewave.ai canonicals; consider a main-site NAV
  link (currently footer-only) if more prominence is wanted.

## Phase 8 - Marketing repositioning (Liquid edge-layer thesis + WorkOS enterprise) 2026-06-02
- Reworked site/api_marketing/generate.py copy (drafted + adversarially critiqued, all clean):
  - LANDING hero -> "The edge layer for AI traders" + "we do not take your trades, we show you our
    receipts" + provider-neutral subhead; CTAs now Read the docs / Try it live; hero note "Works with
    Liquid (Co-Invest) and any broker".
  - Differentiation section-head -> the provider-neutral thesis (broker-agnostic ticket, conflict-free,
    neutral-bias honesty). NEW "Where TradeWave sits" 3-category section (data feeds / execution apps /
    edge layer) - complementary-not-competing, Liquid named positively.
  - MCP page: NEW GTM hero "Recipe: TradeWave + your broker (works with Liquid and any app)" card with
    the 3-step flow + example agent prompt, links to /learn/recipe-tradewave-plus-broker.html.
  - Pricing: Enterprise strip -> full "Built for teams and enterprises" block: WorkOS SSO (SAML/OIDC) +
    SCIM, multi-seat keys, audit, SLA, commercial pattern-redistribution rights, Contact sales.
  - Use-cases: teams/enterprise band before the final CTA.
- WorkOS/SSO HONESTLY SCOPED (per operator decision): SSO/SCIM governs the CONSOLE login only; API
  calls stay key-based on every plan; it is a Business/Enterprise "contact sales" capability (powered
  by WorkOS), NOT a shipped self-serve feature. Liquid framed only as a partner/channel, never a target.
- Verified: positioning present on all pages, 0 em-dashes, no Liquid disparagement, no SSO over-claim,
  developers-dev portal live 200. NOTE: enterprise SSO/SCIM is marketed as available; actually
  delivering it for a signed customer is a separate small build (org/team model + WorkOS SSO connection
  + SCIM endpoint) - scope when a deal needs it.

## Phase 9 - Agent-era positioning (June 2026: the reader is often the agent) 2026-06-02
Premise (operator-aligned): coding agents build the integration + trading agents consume signals;
TradeWave is the edge an agent CANNOT cheaply compute but CAN consume. Authored + adversarially
honesty-critiqued (the critic's job: keep every claim surgical - concede an agent CAN backtest, claim
only the four precise things; never a blanket "AI cant"). All verified clean.
- NEW landing section (site/api_marketing build_index): "Your agent can write a backtest. It cannot
  make it true." + 4 cards (licensed clean data / look-ahead+overfit traps / the trained 62-feature
  model / forward-tested receipts) + token-economics + verify-the-receipts points.
- NEW page: site/api_marketing build_agents() -> for-ai-agents.html (copy in
  site/api_marketing/for_agents_copy.json). Hero "Built to be consumed by agents", 5 sections incl. a
  ready PASTE PROMPT for Claude Code/Cursor. Wired into nav (header+footer) + main() PAGES + sitemap.
- NEW learn lesson 9: site/content/learn_api/build-dont-rebuild.md ("Build, do not rebuild") - the
  four reasons + methodology-traps educational hook + how to consume + verify. Renders via learn gen.
- llms.txt ENHANCED: site/lib/llms_agent_append.md appended by portal_seo.build_llms() with env-driven
  URL substitution (dev/staging/prod each emit their own hosts) - "why consume not compute" + "if you
  are an agent integrating/evaluating" + a one-paragraph integration prompt. So an evaluating agent
  reading the site gets the full argument + entry points.
- The core moat reframed for the agent economy: forward-tested receipts are the one un-fakeable asset
  (time only moves forward), and they are VERIFIABLE (free-tier /v1/daily-pick/track-record + public
  scorecard) so an evaluating agent can audit before recommending. "Do not trust us - check us."
- Verified live: for-ai-agents.html + build-dont-rebuild.html + llms.txt all 200; 0 em-dashes whole
  portal; no blanket "AI cant"; 4 files concede agents CAN backtest; patterns-only held; sitemap 23 urls.

## Phase 9b - "The daily scan is a pipeline, not a prompt" differentiator (operator insight)
Added a DISTINCT class of moat (operation/scale, not just data quality): TradeWave runs a daily,
cross-sectional scan over the whole tradeable universe (hundreds of securities x 15 markets), surfaces
the ones at the START of a seasonal window today, ranked by Sharpe ratio + pattern length (days in the
move) = the /v1/scan opportunity table. An agent can analyze a symbol you name; it cannot stand up a
daily universe-wide seasonal-entry scanner over a compiled multi-decade licensed dataset on a whim
(standing pipeline refreshed daily; by the time it rebuilt it, the window moved). Woven into 4 surfaces
honestly (each CONCEDES one-symbol analysis is easy): for-ai-agents.html (new section), landing callout,
learn lesson 9 (new "## And the real job is a daily scan" section + runnable /v1/scan code), and
llms.txt (point 5). Verified: 0 em-dashes, no "agent cant scan" overclaim, patterns-only, live 200.

## Phase 10 - Column filters on opportunities/scan (operator request, the UI filter parity) 2026-06-02
Added the numeric column filters the UI opportunity table offers, to BOTH /v1/scan (find_best_opportunities)
and /v1/opportunities (get_seasonal_opportunities) + their MCP tools:
- min_days / max_days  -> pattern length (holding period) in calendar days, e.g. a 10-90 day range
- min_avg_return       -> avg seasonal profit, PERCENT (5 = 5%; matches avg_return_pct)
- min_median_return    -> median seasonal profit, PERCENT
- min_sharpe           -> Sharpe ratio floor
Existing min_win_rate (0..1 fraction) + min_years + direction unchanged.
DESIGN: filters operate on RAW OppList4 columns (days_out/avg_profit_pct/median_profit_pct/sharpe_ratio),
applied BEFORE win-rate enrichment (apiserver/routes.py:_column_filters_from_args) so a ChartData4 call is
never spent on a row a filter would drop; /opportunities refactored to raw-fetch -> column-filter -> enrich
survivors. Units note: returns are PERCENT (match the percent fields); win_rate stays a 0..1 fraction.
WIRED: routes.py (both endpoints), openapi.yaml (both), mcpserver/server.py (both tools), MCP_TOOLS.md.
VERIFIED LIVE: "top 10 between 10-90 days, avg profit >= 5%" -> GET /v1/scan?window=now&min_days=10&max_days=90&
min_avg_return=5&limit=10 returns 10 cards, 0 filter violations across 50 rows; /opportunities same; MCP tool
introspection shows all params; docs/openapi.json/postman regenerated; 0 em-dashes; backwards compatible.
NOTED (pre-existing, NOT from this change): /v1/scan can return duplicate rows (same symbol/hold/stats twice)
when window=now surfaces a symbol at two nearby entry dates - worth a dedup pass on scan; separate item.

## Phase 11 - Presidential election cycle + symbol-patterns list (operator request) 2026-06-02
Decisions: param name = pe_cycle; Feature 2 = Both (enhance + clearly-named alias). Engine verified on
dev (OppList4 mode=pe -> 134 rows; ChartData4 yrs=pe2-10 -> 1986/1990/.../2022/2026; OppBySymbol mode=pe).
FEATURE 1 - PE cycle (two engine mechanisms, exactly as the operator described):
  - Opportunity table (scan / opportunities / opportunities-by-symbol / patterns list): pe_cycle=consecutive|pe
    via the OppList4/OppBySymbol `mode` query param (pe = the CURRENT cycle position; pre-computed dataset).
    Threaded mode through appserver_client.opportunities/opportunities_by_symbol/opportunities_multi/safe.
  - Per-security chart/stats (seasonal-chart / patterns-stats): pe_cycle=consecutive|pe|pe0|pe1|pe2|pe3 via
    the ChartData4/seasonal-chart `yrs`/`sy` = 'pe{N}-{count}' format (count = the `years` param). routes
    _resolve_pe_cycle(allow_positions) + _opp_mode + _chart_years. pe0-3 REJECTED (400) on the table
    endpoints (engine only has the current phase there); allowed on per-security. Backwards compatible.
FEATURE 2 - symbol patterns list (the wave-viewer pattern dropdown = OppBySymbol, Sharpe-ranked): already
  served by GET /v1/opportunities/{symbol}; refactored to _symbol_patterns_response() shared by it AND the
  NEW clearly-named GET /v1/securities/{symbol}/patterns; both take pe_cycle + the column filters.
WIRED + VERIFIED LIVE: gateway (routes.py + appserver_client.py), MCP (server.py: pe_cycle on
find_best_opportunities/get_seasonal_opportunities/get_opportunity_for_symbol/get_seasonal_pattern/
get_opportunity_chart + NEW get_symbol_patterns tool = 15 tools), openapi.yaml (pe_cycle on 5 endpoints +
the new /securities/{symbol}/patterns path), MCP_TOOLS.md, docs/openapi.json/postman regenerated, portal
re-assembled, 0 em-dashes, both services active.
NOTE: the patterns list returns the appserver top_pct=10 slice by default (~top 10% of a symbol's patterns,
Sharpe-ranked); could expose top_pct as a param if the operator wants more/fewer. Separate small item.

## Phase 12 - Expose year1/year2 (pattern lookback + min winning years) 2026-06-02
GAP fixed (operator caught it): the gateway hardcoded year1=10/year2=9 and never exposed them.
The two pattern-DETECTION knobs (engine OppList4/OppBySymbol year1/year2):
  - years (year1): the LOOKBACK - how many years to scan for patterns (5-98, data-dependent; the
    number of PE-position occurrences in pe mode). Default 10.
  - min_winning_years (year2 / pyears): of those years, the minimum number of WINNING years required
    for a pattern to be listed. '10-9' = years=10 & min_winning_years=9 (>=90% won); '17-15' = 17/15.
    Detection floors ~80%+. Default 9. Composes with pe_cycle (e.g. 10-9 + pe = last 10 PE-position
    years with >=9 winners).
appserver_client ALREADY accepted year1/year2; only the routes needed to pass them. Added
routes._lookback_args() (validates years 1-99, min_winning_years 0..years) wired into /v1/scan,
/v1/opportunities, and _symbol_patterns_response (/opportunities/{symbol} + /securities/{symbol}/patterns).
Widened _clean_chart_args years range 50->99 for the per-security chart lookback.
VERIFIED LIVE (S&P): 10-9->306, 10-10(stricter)->101, 17-15->206, 5-5->295 (sets differ correctly);
/scan 10-9 pe -> 5; validation: min_winning_years>years->400, years=200->400, defaults->200,
per-security years=40->200. Wired MCP (years+min_winning_years on find_best_opportunities/
get_seasonal_opportunities/get_symbol_patterns/get_opportunity_for_symbol), openapi (4 endpoints),
MCP_TOOLS.md, docs/openapi.json/postman regenerated, 0 em-dashes, both services active. Backwards compatible.
OPERATOR SAID "there is also more to add to api and mcp" - awaiting the next items.

## Phase 13 - Date-range presets (wave-viewer "Months & Qtrs" dropdown) 2026-06-02
Exposed the per-security date-range presets (Common.js monthsAndQtrs / SeasonalBarChart handler) on the
API + MCP, on the window-based per-security endpoints (/v1/seasonal-chart + /v1/patterns/{market}/{symbol})
and their MCP tools (get_opportunity_chart, get_seasonal_pattern):
  - period: months jan..dec | quarters q1..q4 | seasons spring/summer/fall/winter | ytd (year to date)
    | year_end (today to year end) | buy_hold (Jan 1 -> Jan 1, full year). OVERRIDES entry_date/days_out;
    gateway computes (entry_date, days_out) for the current year (Winter/Buy&Hold wrap to next year).
  - reverse=true: the COMPLEMENT of the window (period=mar&reverse=true = all year except March, entry
    Apr 1 / 334 days - matches the operator's example). A full-year (buy_hold) range cannot be reversed -> 400.
routes._resolve_period() mirrors the React math exactly; _chart_window_and_years() shared by both routes
(period overrides _clean_chart_args; pe_cycle + years still honored). Widened days_out cap 365->366 (buy_hold).
VERIFIED LIVE: jan->2026-01-01/31d, q1->Jan1/90d, q3->Jul1/92d, winter->Dec22/89d(wrap), spring->Mar21/92d,
ytd->Jan1/153d, year_end->today/213d, buy_hold->Jan1/366d; mar+reverse->Apr1/334d, q1+reverse->Apr1/275d;
buy_hold+reverse->400, unknown period->400, patterns period=q2->win_rate 0.73, no-period->200 (backwards compat).
Wired MCP (period+reverse on get_opportunity_chart + get_seasonal_pattern), openapi (2 endpoints, enum of all
presets), MCP_TOOLS.md, docs/openapi.json/postman regenerated, 0 em-dashes, both services active.
("seasonals" in the operator's list = the 4 seasons spring/summer/fall/winter, included.)

## Phase 14 - Pin /v1/analyze to a SPECIFIC clicked opportunity 2026-06-02
Closed the table->wave-viewer drill: /v1/analyze (+ MCP analyze_symbol) auto-picked the best setup with no
way to load THE setup the user clicked on the opportunity table. Now analyze accepts the wave-viewer knobs:
  - entry_date (YYYY-MM-DD) [+ days_out]: PIN to that exact opportunity. Matches a detected setup by
    entry_date (prefers same days_out); if none matches, analyzes the exact window directly (stats sourced
    from ChartData4 via build_pattern_card's opp->stats fallback, so an arbitrary window still renders a full card).
  - pe_cycle (consecutive|pe) + years (1-99): the lookback/cycle knobs (same as /seasonal-chart). Drives
    OppBySymbol mode + the receipts/curve lookback (best['years']=_chart_years).
  - period + reverse: the Phase-13 date-range presets, here too (override entry_date/days_out).
No pin = unchanged best-by-edge_score behavior (backwards compatible). other_setups now computed as
"every opp except the chosen one" (was opps[1:], wrong once best != index 0). Added entry_date strptime +
days_out 1-366 validation (was a 200-on-garbage gap).
VERIFIED LIVE (WMT/market 0): no-pin->sharpe 3.35/avg 6.2 (edge-best); pin 2026-05-23/82->3.17/6.38;
pin 2026-05-19/82->3.18/5.81 (each loads its EXACT clicked setup, not the best); arbitrary 2026-06-02/71->
win 1.0/2.48 (ChartData4-sourced); pe+years=20->0.32/4.0/0.64; period=q3->0.86/8.0/0.8. Validation:
bad entry_date->400, days_out=999->400, pe_cycle=pe2(positions rejected on analyze)->400. MCP forwarding
verified end-to-end (same numbers via analyze_symbol.fn). openapi (/analyze/{symbol} +6 params), MCP_TOOLS.md,
mcp.json description, docs/openapi.json/postman regenerated, 0 em-dashes, both services active.

## Phase 15 - Tara (in-product chatbot) becomes a CLIENT of the gateway, read-client 2026-06-02
The shipped wave-viewer assistant "Tara" (appserver/appserver/chatbot.py, Haiku 4.5) could only reason over
the on-screen context; it never called the v1 gateway. Phase 1 of docs/TARA_GATEWAY_INTEGRATION.md gives Tara
tool-use so it FETCHES + narrates the gateway's own composed PatternCards - one source of truth, patterns-only,
same disclaimer as the API/MCP/daily-pick. NOT a product merge (the public API/MCP is unchanged; Tara stays the
login-gated UI helper). Metering = option A: an internal 'chatbot' tier (tiers.INTERNAL_TIERS, service:True, kept
OUT of the sold API_TIERS) + an X-TW-On-Behalf-Of delegation in the gateway (auth.py, honored ONLY for service:True
keys, principal regex-validated + 'cb:'-namespaced) so ML/rate/usage meter PER WEB USER on the chatbot's own quota,
separate from that human's API ML bucket. Built: tiers.py (chatbot tier + assert no sold tier is service:True),
auth.py (_apply_on_behalf), AI_tools_appserver.py (tools= + return_raw on send_claude_messages), NEW
appserver/appserver/tara_gateway.py (gateway client _get + 4 flagship tool schemas + allowlisted dispatch +
bounded tool loop), chatbot.py (chat() runs the tool loop when TARA_TOOLS_ENABLED, else unchanged fallback), config.py
(TARA_GATEWAY_URL/KEY env-agnostic), apiserver/provision_chatbot_key.py (mints the chatbot service key; never prints raw).
VERIFIED LIVE (dev): explain_pick->real NVDA card (91% 10/11y, +23.8%, SR 2.8) + disclaimer; find_best_opportunities
->real UNH/WMT/AXP + all-markets scan->BPS-PA/DOV/RBC...; ML metered mlq:cb:<user>=10; a NORMAL customer key +
on-behalf header did NOT delegate (no cb: key). ADVERSARIAL REVIEW (13 agents, 4 lenses): security core CLEAN
(no escalation, no spoof, key never leaks, patterns-only intact, loop terminates); fixed 1 real HIGH (tool-result
JSON was raw-sliced -> malformed on big payloads; now _bounded_json caps lists/heavy fields to valid JSON, tested
80k->1.4k valid), 1 MEDIUM (gateway read timeout 60->20s, fail-fast), 1 hardening (sold-tier service:True assert).
0 em-dashes. (Phase 2 below.)

## Phase 16 - Tara UI-actuation: chat DRIVES the wave-viewer (Tara Phase 2) 2026-06-02
Tara can now operate the wave-viewer, not just narrate it - the fix for the "too many controls for a
newcomer" problem (ask in plain English; Tara drives the knobs). New `update_view` tool in tara_gateway.py:
the model passes a concrete ViewSpec (symbol/market/entry_date/days_out/years/pe_cycle); run_chat_with_tools
now returns (text, actions); an update_view call is validated server-side by `_validate_view_spec` (allowlist +
range-check, invalid fields dropped) and queued as `{type:'set_view', spec}` - it NEVER hits the gateway
(no quota). chat() returns `{reply, actions}` (additive; old bundles ignore it via Array.isArray guard).
Frontend: `Chatbot.js applyViewSpec` re-validates each field (defense in depth) then calls the React setters,
mirroring loadOppWV; a fresh load (clear opportunities/consolidated/reportsDash + SetSymbol) only on a symbol
CHANGE, else knobs apply in place. `SetPEselected` added to `App.js chartSetProps` (wave-viewer PE selector).
TOOL_INSTRUCTION APPENDED (recency) + forceful: "you MUST call update_view ... do NOT tell them to click" -
the first attempt failed because the base 'guide-the-user-to-click' persona won; appending fixed it. For a
date-range preset the model resolves it via analyze_symbol(period=) -> concrete entry_date+days_out, so the
frontend needs no period math. React bundle rebuilt (nginx serves /app/ from web-react/build on dev).
VERIFIED LIVE: "load NVDA 20y"->action {market:'1',symbol:'NVDA',years:20}; "lookback 15"->{years:15};
"PE+2"->{pe_cycle:'pe2'}. ADVERSARIAL REVIEW (3 lenses): validation correct BOTH ends, strict set_view-only
allowlist, no eval, bool-as-int hardened, loop capped, no quota burn, backward-compat - all confirmed; fixed
1 MEDIUM (exception path now also returns actions:[] for envelope consistency). 0 em-dashes introduced.
Blast radius of actuation = which chart/knobs the user sees (no code exec, no data beyond patterns-only, no auth/billing).

## Phase 17 - Quota re-anchor + MONTHLY-ONLY billing (owner decisions) 2026-07-05
The sold ladder's per-day quotas were data-feed-scale nonsense for a dataset that refreshes once
per trading day (owner: "50,000 per day!! this is not price data download"). Re-anchored every
per-day cap to sweep math = "a per-symbol card for everything in your scope, daily, plus headroom"
(measured on the dev appserver: US stocks+ETFs ~3.7k symbols, all markets ~18.7k unique):
free 10/min+100/day (unchanged), dev 60/min+1,000/day (was 5,000), pro 120/min+5,000/day (was
50,000; full US+ETF sweep ~30min at burst), business 300/min+20,000/day (was 250,000; full
all-markets nightly sweep ~1h; above = Enterprise). Consumer-MCP mirrors made genuinely
assistant-scaled: Analyst-in-chat 1,000/day (was 5,000), Strategist-in-chat 2,000/day (was
20,000). Quota is per CUSTOMER not per key (auth.check_rate_limit buckets on user_id).
SAME RELEASE: API billing went MONTHLY ONLY - price_annual deleted from tiers.py (all dicts);
create_api_products.py seeds monthly only + SELF-HEALS an earlier annual seed (re-points
default_price to monthly FIRST - Stripe refuses to archive a default price - then archives
active annual prices); console checkout 400s {error: monthly_only} on an explicit annual ask;
api_billing.html billing-cycle toggle + annual notes + cycle JS removed; marketing pricing page
annual math/toggle/setBilling removed, FAQ updated, use-cases Business blurb now interpolates
API_TIERS (was hardcoded 250,000). Verified: tiers import rails pass, template parses, both
services restarted healthy, portal re-assembled with zero stale numbers/annual strings in
/var/www/developers. Rationale + doctrine in TRADEWAVE_ECOSYSTEM.md "API billing + quota model".

### Phase 17 addendum - TEST-Stripe seed executed + two Stripe gotchas (2026-07-05, later same day)
Dev sandbox is now fully wired (opus agent run + independently re-verified): TEST catalog = the 3
monthly products (default_price = the monthly price), Founder coupon founder_pro_50_12mo restricted
to Pro + active FOUNDER promo, NEW TEST webhook endpoint we_1TpsgIIs3CeQWow8zSw8B6aB ->
https://tw2-dev.trxstat.com/webhooks/stripe (the 6 events web/app.py consumes), signing secret
rotated into dev secrets.env box-to-box (root:flask 640 preserved), web restarted, unsigned POST
/webhooks/stripe -> 400 (route + secret gate proven). Stale DISABLED endpoint we_1TT43EIs3CeQWow8
7HvrFIw5 (tw2.trxstat.com) left for the owner to delete. GOTCHAS (cost real debugging): (1) stripe
SDK 15.x / current API: PromotionCode.create takes promotion={"type":"coupon","coupon":id} - the
top-level coupon= param is GONE (affiliate_service/promo_service were already migrated; the seeder
was not). (2) API version 2026-04-22.dahlia OMITS coupon.applies_to from the default representation
- retrieve with expand=["applies_to"] or a restriction check silently sees "unrestricted".
_ensure_founder now self-heals: expand-retrieve -> spec-match (incl. Pro restriction) -> drifted+
0-redemptions = delete+recreate, redeemed = loud warning + hands off; name (the one mutable field)
kept canonical; promo reuse requires ACTIVE + pointing at OUR coupon (a deleted coupon deactivates
its promos), strays get deactivated.

### Phase 17 addendum 2 - dev pricing flipped LIVE + the regen-revert trap fixed (2026-07-05)
TW2_API_PRICING_LIVE=1 added to dev secrets.env; web+apiserver restarted; portal re-assembled;
verified: 0 "Coming Soon", cards $0/$39/$199/$599 + "All plans billed monthly. No lock-in - cancel
anytime.", Founder strip ($99/mo), docs rate-limits show $ - dev checkout is now fully testable.
TRAP FOUND + FIXED: the flag was env-only, but the portal generators run from shells that never
load the box env (deploy.sh sshes in as root; assemble_developer_portal.sh inherits the caller's
env) - and portal_urls' secrets.env fallback did NOT save it because generate.py imports
apiserver.tiers BEFORE portal_urls seeds os.environ. So after a prod flip, EVERY deploy regen
would have silently reverted the published pages to "Coming Soon". Fix: tiers._pricing_live_flag()
falls back to /etc/tradewave/secrets.env when the env var is unset (env wins). Staging/prod flags
remain OFF until the owner finalizes $.

### Phase 17 addendum 3 - LIVE Stripe seed executed (owner-requested, 2026-07-05)
LIVE api-line catalog created from DEV using the updated monthly-only seeder with prod-web's live
key fetched box-to-box over ssh (prod's checked-out create_api_products.py was still the stale
annual+old-SDK version - do NOT run the seeder ON prod until the release deploys). Created fresh
(nothing pre-existed): Dev prod_UpYsmRY0DrjDFT ($39/mo price_1TptkkIs3CeQWow8IP567Bte), Pro
prod_UpYsTxNHHdGMBf ($199/mo price_1TptklIs3CeQWow8aZxM4pRw), Business prod_UpYs9aBTeIAPDh
($599/mo price_1TptkmIs3CeQWow890IPIUXL) - each default_price=monthly, metadata product_line=api+
tier; coupon founder_pro_50_12mo (50% repeating 12mo, max 100, applies_to LIVE Pro) + active promo
FOUNDER (max 100). Independently re-verified read-only incl. expand=["applies_to"]. Prod stays
customer-invisible (TW2_API_PRICING_LIVE off on prod; console shows no upgrade cards) but prod's
DEPLOYED old code resolves these correctly if checkout is invoked (old annual fallback lands on
monthly since no annual price exists; webhook product_line=api mapping is live since the July 4
release).

### Phase 17 addendum 4 - console quickstart hardened + cross-platform (2026-07-05/06)
web/api_portal/routes_keys.py + templates/api_keys.html "Get started" card, three fixes:
(1) HOST WAS HARDCODED to api.tradewave.ai / developers.tradewave.ai in the template - the dev/
staging consoles showed PROD urls. Now env-driven: routes_keys._public_host(env_var, by_env) =
explicit TW2_API_PUBLIC_HOST / TW2_DEVELOPERS_PUBLIC_HOST wins, else derive from config.tw2_env
(same pattern as routes_mcp._mcp_host); passed as api_host/developers_host. (2) The curl used a
backslash line-continuation that broke on paste; now ONE line, and the freshly-created key is baked
into the example on the one-time reveal view (new_raw_key or 'YOUR_API_KEY'). (3) TABBED cURL /
PowerShell / Python (owner-requested) so it is copy-paste-correct on any OS - the PowerShell tab
uses Invoke-RestMethod with a -Headers hashtable because in Windows PowerShell 5.1 `curl` is an
alias for Invoke-WebRequest and rejects `-H` (this bit the owner live: "Cannot convert ... to
IDictionary"). Copy button lives in the tab bar and copies the ACTIVE tab; tab choice persists in
localStorage so it survives the create-key page reload. Verified headless (Playwright): tab
switch/isolation/persistence + active-tab copy payloads for all three, dev host + key baked in, no
prod-host leak, Python indentation preserved. NOTE: the public developer-portal docs
(site/api_docs, site/api_learn) still show curl-only snippets - a candidate for the same tabbed
treatment if we want portal parity (NOT done).
