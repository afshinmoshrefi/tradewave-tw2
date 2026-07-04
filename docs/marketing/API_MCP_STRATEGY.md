All facts confirmed, with two important corrections to the plan's own claims:

1. **config.py:633 says TIER_FEATURES has "no runtime readers as of 2026-06-24"** — but app.py:786 docstring calls it "the source of truth" and :797 reads `resources_allowed` at runtime. The plan's correction (#1) is right: it IS exactly one runtime reader. The stale comment is at config.py:633-634.
2. The home pill text is at generate_home_page.py:1005 (plan said 1005 — confirmed), gated on MCP_LIVE (line 192, env `TW2_MCP_LIVE`).
3. SLA: the unqualified bullet is at generate.py:820 (`<li>SLA guarantee</li>` for business); :886 prose; :1376 already hedges "There is no self-serve SLA." Confirmed.
4. apiserver imports nothing from config/web/tier_compat — confirmed (zero hits).
5. Navigator config: `resources_allowed: [0,1,2]` — confirmed matches the plan.

Now I'll write the brief.

# TradeWave API + MCP - Pricing & Teaser Strategy

*Decision brief. Source of truth = `apiserver/tiers.py`. The developer portal is dark on prod (`TW2_MCP_LIVE` unset, `site/generate_home_page.py:192`), so there are zero subscribers to grandfather: changing the API/MCP model now is free. Web prices are live and out of scope here.*

---

## 0. IMPLEMENTATION STATUS (2026-06-29, dev, UNCOMMITTED - MCP_LIVE still OFF)

The MCP mirror + both teasers are **BUILT and verified on dev** (12-check end-to-end harness vs real Postgres PASSED; independent adversarial review verdict = **SHIP**; apiserver + web restarted healthy). Nothing reaches users until `TW2_MCP_LIVE` flips.

- **NEW `reverse_trial.py`** (top-level, dependency-free) - the SHARED reverse-trial cutoff math imported by BOTH the web venv and the gateway `venv-api` (both run `PYTHONPATH=/home/flask`). `effective_web_tier(tier, roles, rt_ends_at, bypass_roles)` is the single source of truth; **`web/app.py:effective_tier` was refactored to delegate to it** (passing `config.ROLE_BYPASSES_TIER` so config stays authoritative), behavior-identical, so web and chat can never drift.
- **`apiserver/tiers.py`** - `WEB_TIER_TO_MCP` (explorer DJ30 / navigator [0,1,2] / analyst [0,1,2,3,4,11] / strategist all-15), `mcp_tier_for()`, `merge_entitlements()` (field-wise MAX), + import-time rails (mirror parity, no delegation flag, scope only widens up-ladder). **Decided:** Analyst MCP scope = the *narrowed* `[0,1,2,3,4,11]` (matching the post-Fix-1 Dev set + `config` analyst), NOT the older 8-market set in §3.3. **Decided:** explorer/navigator steady-state `ml_daily_limit=0` (mirror Ladder A); the AI taste comes ONLY via the time-boxed teasers (loss-shaped), not a permanent 5/day trickle - the API-free(5/day)-vs-MCP(0/day) asymmetry of §3.5, intentional.
- **`apiserver/auth.py`** - branch (A) `workos_principal` now calls `_resolve_mcp(row)` = `effective_web_tier` -> `mcp_tier_for` -> `MAX(web-mirror, explicit api_tier)` (a paying dev is never downgraded in chat). Explorer trial teaser is automatic (effective_web_tier maps explorer+trial -> strategist).
- **Navigator teaser anchored in POSTGRES** (`users.navigator_mcp_first_connect_at`, added via `apiserver/schema.sql` ADD COLUMN IF NOT EXISTS, gateway-owned like `api_tier`) - NOT Redis. This closes the review's one LOW finding (a no-TTL Redis key could re-arm once under FLUSHDB/LRU eviction) AND makes the teaser cohort queryable for the A/B. Idempotent race-safe arming; fails CLOSED on DB error.
- **`apiserver/db.py`** - both user SELECTs return `reverse_trial_ends_at`; the WorkOS SELECT also returns `navigator_mcp_first_connect_at`; + `arm_navigator_teaser_if_null()`.

**Operator pre-launch (before `MCP_LIVE`):** run `psql "$POSTGRES_DSN" -f apiserver/schema.sql` on staging + prod (adds the one column, idempotent). Then commit + deploy. Remaining strategy items still open: Pro/Business standalone differentiation copy (§2.5), the Business SLA card-bullet fix (§2.6, `site/api_marketing/generate.py:820`), the in-band `teaser_state` tool-response field (§4.6) + `DaysRemainingPill`/account-page disclosure, and the `MCP_LIVE` flip itself.

---

## 1. Executive Summary - The Headline Calls

**The frame is two layers, two jobs.**

- **API = the DEVELOPER layer.** Programmatic, bring-your-own-key, the sellable revenue ladder Free / Dev / Pro / Business. Keep it. It is competitively priced and stays the product we charge for.
- **MCP = the USER layer.** Signed-in consumers using TradeWave *inside* ChatGPT / Claude (OAuth via WorkOS), entitlements following their **web** subscription. MCP is **not** a separate revenue SKU. It is a perception + conversion lever whose only job is to make the web tiers feel bigger and pull users up the web ladder.

**The seven calls:**

1. **KEEP the API ladder shape and prices** - Free $0 / Dev $39 / Pro $199 / Business $599. Re-anchor the justification on the in-class comps only (Financhill $199/mo, Seasonax $49.95-$100/mo); drop the unverifiable raw-data citations.
2. **MCP consumer entitlements MIRROR the WEB sub, never the API ladder.** This reverses `PRICING_QUOTA_SPEC.md` §1/§3 (which today says MCP == API). Code confirms today's behavior follows the API ladder (`apiserver/auth.py:155` → `api_tier_from_user` → `tier_for`), so this is a genuine reversal.
3. **Fix the Navigator gap before anything ships.** A paying $19 Navigator silently falls through to **free** API/MCP entitlements (`apiserver/tiers.py:110` has no `navigator` key → `DEFAULT_TIER='free'`). This is a paid-customer bug.
4. **Narrow the Dev API tier** from all-15 markets to the Analyst data set - it currently hands away the breadth upsell.
5. **One honest, time-limited MCP teaser**, built end-to-end and instrumented, gated behind `TW2_MCP_LIVE`. Explorer reuses the existing 7-day reverse-trial clock; Navigator gets a separate, deliberately-scoped first-connect window.
6. **The wedge no comp has:** "your seasonal signals, AI-scored, inside ChatGPT and Claude." Seasonax and Financhill have no in-assistant surface. MCP is free, low-CAC distribution into a population pre-filtered to paying-AI users (~$20/mo WTP floor).
7. **The teaser is net-new apiserver code, not a reuse.** The gateway is reverse-trial-blind today (`apiserver/db.py:30,46` SELECTs omit `reverse_trial_ends_at`). If `MCP_LIVE` flips before the build ships, trial users get a **worse-than-web** chat experience = day-one bait-and-switch. The whole rollout is gated on the build below.

**Four corrections to the prior draft** (the credibility of a plan whose whole point is honesty depends on getting its own facts right):

- **(C1)** TIER_FEATURES is **not** "zero runtime readers." `web/app.py:797` reads `config.TIER_FEATURES[t]['resources_allowed']` at runtime and its docstring (`:786`) calls it "the source of truth." It is exactly **one** reader, and it is upgrade-*nudge* copy, not a gating path. The stale `config.py:633` comment ("no runtime readers as of 2026-06-24") gets fixed in the same change.
- **(C2)** The supersession target is real and precise: `PRICING_QUOTA_SPEC.md` §1 Principle 1 + §3 ("MCP and the standalone API consume the SAME API_TIERS entitlement") is an MCP==API rule; this plan reverses it to MCP==WEB.
- **(C3)** Cross-process feasibility is a hard gate, not an assumption: `apiserver/*.py` imports nothing from `config`/`web`/`tier_compat` (grep = zero hits); `tier_compat.py` lives in `web/`. "Derive via tier_compat" and "one shared helper" require a packaging decision, made explicit in §6.
- **(C4)** The Business SLA page is internally **hedged** (`site/api_marketing/generate.py:1376`: "There is no self-serve SLA"), not a naked over-claim. The only unqualified artifact is the `:820` card bullet. Scope the fix to that one line + the `:886` prose, not a sweep.

---

## 2. API DEVELOPER Layer - Free / Dev / Pro / Business

**Call: KEEP the 4-tier shape and the prices. Re-anchor the justification and close two leaks.**

### 2.1 The ladder is competitively positioned (hold prices)

| Tier | Price (mo / yr) | Markets | ML/day | Opps/call | Rate (min/day) | Keys |
|---|---|---|---|---|---|---|
| Free | $0 | S&P only `['2']` | 5 | 3 | 10 / 100 | 1 |
| Dev | $39 / $390 | **narrow to 8 (Fix 1)** | 100 | 100 | 60 / 5,000 | 3 |
| Pro | $199 / $1,990 | all 15 | unlimited | 1,000 | 300 / 50,000 | 10 |
| Business | $599 / $5,990 | all 15 | unlimited | 5,000 | 1,200 / 250,000 | 50 |

**Evidence the prices are right:** Dev $39 undercuts the entry rung of every in-class data API (Polygon/Massive Developer $79, Twelve Data Grow $79, Alpha Vantage $49.99). Pro $199 lands dead-center: identical to Polygon Advanced $199, brackets Twelve Data Pro $229 [massive.com/pricing; twelvedata.com/pricing; alphavantage.co/premium]. The closest *direct* comp by category - Financhill's seasonality standalone at $199/mo (page-verified, HIGH confidence) - anchors Pro precisely.

**Evidence fix - drop the unverifiable cites.** The prior draft's "Twelve Data Grow ~$29 / 17% annual" figures appear nowhere in the repo, and `docs/marketing/PRICING_COMP_REANCHOR.md` deliberately bans raw-data comps. Ground the two load-bearing claims on facts that *are* in the repo:
- **annual = 10× monthly** is verified directly in `tiers.py` (price_annual 390/1990/5990 = exactly 10× price_monthly 39/199/599) - no external citation needed.
- the **~17%-off annual band** is corroborated by Seasonax (~$41.66/mo on annual). Use raw-data ladders strictly as a *ceiling* sanity-band, never the anchor.

### 2.2 Keep ML metered on every tier (the loss-shaped upsell)

ML scores are offered on every tier, metered per day (`tiers.py:8-12`): free 5 → dev 100 → pro/business unlimited. This is the right model and is externally validated - **Perplexity caps free at exactly 5 Pro searches/day, then "removes those limits" at $20/mo** [techjacksolutions.com; datastudios.org]. Patterns are never metered; only the ML *score* is withheld at the cap (a soft wall = a recurring paywall moment, the GPT-5 "feels like a wall, you can still continue" mechanic, ~6× the conversion of generic freemium: 12% vs 2% [dev.to/paywallpro]).

### 2.3 Fix 1 - narrow the Dev market scope (close the API-layer leak)

Dev = `ALL_MARKETS` today (`tiers.py:37`), so a $39 Dev buyer gets all 15 incl. futures/forex/crypto - the Strategist/$129 breadth upsell handed away on the API side. **Narrow Dev to the Analyst data set `['0','1','2','3','4','5','6','11']`** (8 ids, exactly `PRICING_QUOTA_SPEC` Fix B); reserve all-15 for Pro/Business. The market tiers strictly by data scope (Polygon, Twelve Data) - this is the dominant lever, and we're currently the only one not using it on Dev.

### 2.4 Fix 2 - defend the Dev→Pro gap ($39→$199, 5.1×), don't add a 5th tier

Four tiers is the proven shape (3-5 is the API-unicorn consensus [zuplo.com/learning-center]). Post-narrowing, the 5× buys a **capability step** (all-15 markets + unlimited ML + 10× rate/opps), not just a meter. **Founder** (Pro at $99/mo ×12, `api_tier` stays `'pro'` per `tiers.py:101`) fills the valley and anchors Pro. Instrument **Dev-at-cap → Pro** before launch. No reverse trials on the API layer - developers evaluate on docs + free-tier limits; add only a 75-80%-of-cap upgrade nudge in response headers/console (reuse `ml_quota.remaining()`, `apiserver/ml_quota.py:37`).

### 2.5 Fix 3 - the pricing inversion (real, code-verified)

`WEB_TIER_TO_API` maps `strategist → 'pro'` (`tiers.py:110`) and `auth.py` returns the **full** `tier_for('pro')` dict with **no separate bundled cap** - so a Strategist (~$99/mo annual-effective) bundles the $199 standalone Pro entitlement: the component costs 2× the bundle. **The "cap the bundled key" mechanism does not exist in code.**

**Resolve via the lower-build honest path:** do *not* claim a phantom cap. Make standalone Pro/Business carry the legitimate, quantified differentiator they already have headroom for - **higher published rate caps** (Pro 300/min 50k/day; Business 1200/min 250k/day, both far above any bundled-web key's needs) + **no web seat** - and **state it on the page:** "A bundled web key inherits your tier's programmatic limits; standalone Pro/Business exist for higher dedicated rate/throughput and commercial terms." If a real bundled-cap is ever wanted, it becomes a named build item (a distinct entitlement dict with explicitly lower `per_minute`/`per_day`/`opp_limit`), gated alongside `MCP_LIVE` - **never shipped as copy-only**, because that recreates the asserted-but-unbuilt trust risk this plan flags for the SLA.

### 2.6 Fix 4 - the Business SLA (corrected scope: one line, not a sweep)

The page is internally hedged: `site/api_marketing/generate.py:1376` already states "There is no self-serve SLA" and reserves a contractual SLA for Enterprise/contact-sales (`:543`, `:1374`, `:1925`). The **only** unqualified self-serve promise is the Business comparison-card bullet `<li>SLA guarantee</li>` (`:820`), which contradicts `:1376`, plus the `:886` prose ("A service-level agreement - uptime and support commitments"). **Action = one-line copy fix:** delete/qualify `:820` and scrub `:886` to "Enterprise, by written agreement," matching the page's own framing. Sell Business on the legally-true differentiators (50 seats + named support + commercial/redistribution license, `:872`/`:887`). No build.

### 2.7 Cross-surface note (state on the portal)

A developer who is also an Analyst gets 8 markets on the BYO-key Dev API (post-Fix-1) but the **web mirror** over consumer-MCP. These differ **on purpose** - the two surfaces follow different sources (API ladder vs web sub). Document it so a dual-holder isn't surprised.

---

## 3. MCP USER Layer - Mirror, Packaging, AI Gating

**Call: consumer-OAuth MCP entitlements MIRROR THE WEB SUB. BYO-key dev-tool MCP keeps the API ladder.**

### 3.1 The scope decision (decisive)

Today `auth.py:147-159` routes the `workos_principal` through `api_tier_from_user` → `tier_for` - i.e. **MCP == API ladder** (so an Analyst would resolve to `'dev'` = all-15, pre-Fix-1). **Replace that branch:** build a new `WEB_TIER_TO_MCP` dict in `tiers.py` (full per-tier entitlement: markets + rate + opp_limit + ml_daily_limit), and in the (A) `workos_principal` branch resolve scope from it keyed on `row['tier']`, **not** `api_tier_from_user()`. The BYO-key dev-tool MCP path (Cursor/Claude Desktop) keeps resolving against `API_TIERS` - those developers bought the API explicitly.

**Why mirror, not ladder:** MCP is a conversion lever for the web tiers; a user inside ChatGPT must see exactly what their web plan shows. Mirroring the API ladder is precisely what causes the leak (Analyst web = 6 US markets but Dev API = all 15 → MCP would surface futures/forex/crypto the web app hides). Over-generous in-chat scope hands away the upsell and anchors $0 [softwarepricing.com; productled.com on ConvertKit]. The bundled-entitlement pattern is the mature one: Zuplo ("same API, same auth, different entitlements based on plan"), HubSpot's ChatGPT connector (free across all its tiers, paywall on the assistant side) [zuplo.com/blog/monetize-an-mcp-server; hubspot.com/ai-tools/openai-connector].

### 3.2 The explicit-api_tier precedence trap

`api_tier_from_user` returns the **explicit `users.api_tier` column FIRST** (`tiers.py:131-134`). A user holding *both* a web sub and a purchased api_tier (an Analyst who also bought standalone Pro, or any Founder whose `api_tier='pro'`) must not get **less** in chat than they paid for. **Rule: consumer-MCP scope = MAX(web-sub mirror, explicit-api_tier scope).** Add `(has-api_tier × has-web-sub)` to the test matrix; name the Founder (`api_tier='pro'`) case concretely.

### 3.3 The mirror definition - reconcile three disagreeing Analyst scopes BEFORE coding

This is the real decision. Three sources disagree on what "Analyst" means:
- **(i)** `config.level_access_hierarchy['4']` = all 15 (the opp-list gating filter the web app actually runs);
- **(ii)** `config.TIER_FEATURES['analyst'].resources_allowed` = `[0,1,2,3,4,11]` (6 ids - the upgrade-*nudge* engine at `app.py:797`, **the one runtime reader**, per C1);
- **(iii)** `PRICING_QUOTA_SPEC` `_min_tier` = `[0,1,2,3,4,5,6,11]`.

Picking 15 for MCP while the web nudge treats Analyst as 6 markets produces **contradictory upsell copy across surfaces**. **Decide: clamp Analyst MCP scope to the genuinely-unlocked set `['0','1','2','3','4','5','6','11']`** (the Dev set, matching the premium hierarchy + Fix B), and surface other markets as **text-only** upgrade hints (no data). This avoids a large net-new build: the gateway has **no date-lock concept at all** (grep `date_lock`/`datelock` in apiserver = nothing), so "Analyst = all 15 with 9 date-locked teasers" would require a net-new per-market redaction mode *and* would over-deliver Strategist data to a $47 tier. Clamping is honest and ships now. (The all-15-with-teasers experience, if later wanted, is its own blocking build item with a redaction test.)

### 3.4 The mirror scopes (final)

| Web tier | MCP markets | Steady-state ML/day |
|---|---|---|
| explorer | `['0']` (DJ30, level '1') | 0 |
| navigator | `['0','1','2']` (level '2') | 0 |
| analyst | `['0','1','2','3','4','5','6','11']` (unlocked US set) | metered (AI on) |
| strategist | all 15 (level '6') | metered (AI on) |

Derive from the runtime **gating** source (`level_access_hierarchy` via a shared module - see §6 feasibility gate) and add an **import-time assert**: every web tier has a `WEB_TIER_TO_MCP` entry AND its scope is a subset of its level's backend filter (mirror the existing service-flag assert at `tiers.py:117`), so a future web-tier edit can't silently re-open a leak.

### 3.5 AI gating (resolve gap #3 deliberately - it IS net-new, not mirroring)

`WEB_TIER_TO_MCP` carries its **own** `ml_daily_limit`, distinct from `API_TIERS`. Steady state: explorer/navigator = 0 (web AI starts at Analyst - Ladder A), analyst/strategist get AI. **Verified feasible:** `ml_quota._limit` reads `cust['entitlements']['ml_daily_limit']` (`ml_quota.py:34`), so a distinct MCP entitlements dict with `ml_daily_limit=0` suffices.

This deliberately makes the **same free identity** behave 5/day on BYO-key API but 0/day on consumer-MCP. **Document the asymmetry as intentional** in `WEB_TIER_TO_MCP` comments + MCP docs: "API free = developer evaluation taste 5/day; MCP mirrors your WEB plan, where AI starts at Analyst." That makes it a design fact, not a support surprise.

**ML-bucket isolation:** reuse the proven `cb:`-namespacing precedent (`auth.py:164` rewrites `cust['user_id']` to `'cb:'+id` so the chatbot bucket never collides) - give the consumer-MCP principal an **`mcp:`-prefixed** metering user_id so one human's MCP and API ML buckets (`mlq:<id>:<date>`, `ml_quota.py:29`) never collide.

### 3.6 Packaging

Market MCP as a per-tier perk with entitlements mirrored exactly. The audience is pre-filtered to ~$20/mo AI subscribers (ChatGPT Plus/Pro/Business, Claude paid, Perplexity Pro/Max all gate connectors behind paid tiers [truthifi.com; perplexity.ai/changelog]) - a high-WTP showroom. **Supersede `PRICING_QUOTA_SPEC.md` §1 Principle 1 + §3** (MCP==API) → MCP mirrors WEB; keep the spec's still-correct parts (Fix A/B/D) and update in place. Note the real remaining divergence: the spec proposes **web** price changes (Strategist $129→$83, Analyst $39→$25) which this plan refuses to touch.

---

## 4. THE TEASER STRATEGY

**Call: ONE teaser, shipped end-to-end and instrumented before any second mechanism.** More teaser surfaces = more disclosure copy that can drift into a dark pattern. Simplicity is a trust discipline here.

### 4.1 The mechanism (net-new - the gateway is reverse-trial-blind today)

1. **Add `reverse_trial_ends_at` to BOTH `apiserver/db.py` SELECTs** (`get_user_by_workos_id` ~line 30 and `get_user_by_key_hash` ~line 46 - both currently omit it, verified).
2. **Feasibility gate (C3, made explicit):** the apiserver imports nothing from `config`/`web`/`tier_compat` (grep = zero hits); `effective_tier` lives in `web/app.py:1530`. Pick ONE before `MCP_LIVE`:
   - **(a) [recommended]** extract the reverse-trial cutoff math + `level_access_hierarchy` + `ROLE_BYPASSES_TIER` into a small **shared module** both processes import (and verify the apiserver deploy ships it) - a single in-process call; OR
   - **(b)** have the gateway resolve effective web tier + scope via an authenticated webserver endpoint (web = source of truth).
   
   Either way, the cutoff math is **imported, never duplicated**, so web and chat can't diverge.

With that wired, an Explorer in their existing 7-day signup trial resolves to **Strategist scope on the MCP path too**.

### 4.2 The Explorer teaser (reuses the existing clock)

- **What they taste:** full Strategist scope - all 15 markets + AI-calibrated probability scoring - inside ChatGPT/Claude.
- **For whom:** Explorer (the one tier the existing reverse-trial clock serves).
- **How long / how many:** the **remaining days of the running 7-day signup trial** - **not** a fresh 7 days armed at MCP connect (re-arming `reverse_trial_ends_at` would re-elevate the *web* tier too via `effective_tier` = a real leak). 7-day is evidence-optimal: a 337,724-user RCT found 7-day beat 30-day (15.44% vs 14.63%); Grammarly runs exactly 7-day-then-auto-downgrade [userpilot.com/blog/saas-reverse-trial]. AI is full during the window; **cap teaser ML at a generous-but-bounded number (e.g. 50/day)** so one user can't run unbounded inference COGS. **One window per WorkOS identity** (not per subscription) to block churn-and-resignup farming.
- **This is the only honest reading of "one coherent window":** the web trial's remaining days mirrored into chat.

### 4.3 The connect-is-signup edge (verify, don't assume)

`PRICING_QUOTA_SPEC` §4 says connecting in ChatGPT can *be* the signup. `web/app.py:468` sets `reverse_trial_ends_at = now+7d` at the web signup path; **confirm the OAuth-first/connector signup path hits the same code**, else a connector signup could start with no trial = a worse bait-and-switch than the one we're fixing. Connect-flow copy must disambiguate the shared clock: *"Your 7-day full-Strategist trial is ONE clock shared by web and chat - connecting in ChatGPT shows whatever days remain."*

### 4.4 Late-connect (decided): remaining-days-only

A user who connects after the web trial lapsed gets **no fresh taste** - mirrored steady-state scope + upgrade nudge immediately. So the marketing promise must be *"during your 7-day trial, the same Strategist access on web and in ChatGPT,"* **not** "free AI inside ChatGPT on every plan." Add a last-day pre-expiry heads-up so the snap-back (which lands on both surfaces the same day) is anticipated.

### 4.5 The loss-shaped conversion mechanic

At expiry the MCP tool result returns a **value-quantified, single-rung** nudge (usage-ROI framing converts ~40% better than feature lists [gtmstrategist.com]):

> "This week in your assistant you pulled AI-calibrated signals on 23 setups across 15 markets. Your plan keeps DJ30 - upgrade to Analyst ($47/mo, or $33/mo billed yearly) to keep AI scoring."

Framed as **discovery** ("you discovered a Premium feature," the Spotify pattern [appcues.com]), not punishment. After expiry, fire only **when the cap bites, at most once per session with cooldown** - no standing daily banner. Loss-shaped/timed tastes out-convert permanent freemium by ~4-6× (reverse trials 7-21% vs freemium 3-15% [userpilot; chartmogul.com]).

### 4.6 Why it is honest

**No card captured** - entitlements follow the existing web sub via OAuth, so no auto-charge, no negative-option / FTC-Section-5 exposure [ftc.gov dark-patterns enforcement]. **Enforce disclosure structurally** (the load-bearing channel must survive host-LLM paraphrasing + refactors): make **`teaser_state {active|expired, ends_at, post_teaser_scope}` a REQUIRED machine-readable field on every teaser tool response**, plus the always-reachable TradeWave-controlled surfaces `DaysRemainingPill.js` + the account page. **Demote the confirmation email to best-effort reinforcement only** (deliverability isn't guaranteed - it can't be the guarantee). The build-gating test asserts the **in-band `teaser_state` field** (non-empty `ends_at` + `post_teaser_scope`), **never** the email. The free floor stays genuinely useful (deterministic patterns are never metered).

### 4.7 The Navigator play (separate, net-new infra - acknowledged honestly)

**Fix the gap first (hard requirement, code-verified).** `tiers.py:110` `WEB_TIER_TO_API` has no `navigator` key, so a paying $19 Navigator falls to `DEFAULT_TIER='free'` (S&P-only `['2']`, 5 ML/day) - **identical to a $0 Explorer on both API and MCP today.** This is a paid-customer bug; it ships **before** MCP goes live.

- **Add a dedicated `navigator` API entry:** markets `['0','1','2']` (mirroring `config.level_access_hierarchy['2']` and `config.py:635` `resources_allowed: [0,1,2]`), `ml_daily_limit=5`, opp_limit/rate between free and dev. Map `navigator → this entry` in `WEB_TIER_TO_API`.
- **Do NOT map `navigator → 'dev'`** (that re-leaks all-15 + 100 ML/day into a $19 plan and undercuts the Analyst→Dev bundle).
- **Guard the sellable-catalog iterators** (pricing page / Stripe sync) so the navigator entry never appears as a standalone API product - reuse the `INTERNAL_TIERS` exclusion pattern (`tiers.py:65`).
- On MCP, navigator resolves through `WEB_TIER_TO_MCP` to `['0','1','2']`, `ml_daily_limit=0` steady state.

**The Navigator-specific teaser.** Navigator is paid and **never** receives the explorer reverse trial (`effective_tier` at `app.py:1531` elevates only `tier=='explorer'`), so there is **no existing clock to reuse**. This is a second, deliberately-scoped, one-time window keyed on **first-MCP-connect** (a `navigator_mcp_teaser_ends_at` column / Redis key), once per WorkOS identity, **never** a re-arm of `reverse_trial_ends_at` (which would leak web elevation via `effective_tier`).

- **Scope matched to the target: grant ANALYST scope, NOT Strategist.** Navigator's web pain is "no AI" (`config.py` `ml_scoring=False`), and the targeted upsell is the single rung to Analyst ($47, the first AI web tier). The taste = Navigator's 3 markets + AI scoring - the exact thing denied on web. The loss at expiry is precisely "AI on your US stocks/ETFs" = the Analyst value prop, making the one-rung ask honest and frictionless (vs tasting all-15 and being steered to the wrong tier).
- **Expiry copy:** "Your 7-day AI trial ended. Navigator keeps Dow, NASDAQ and S&P; upgrade to Analyst ($47/mo, or $33/mo yearly) for AI scoring across all US stocks and ETFs."

**Sequencing honesty.** Ship Explorer first because it **reuses the existing clock** (lower build cost), **not** because it's highest-yield - by this plan's own logic a $0 Explorer paying no AI vendor can't even connect a connector, so the reachable Explorer slice is thin. **Instrument connect-rate-by-tier from day one** and let it decide whether to promote the Navigator teaser ahead of schedule (Navigator users are paid and likelier to also hold a paid AI assistant).

---

## 5. How This Lifts Perceived Value + Web Subscriptions

MCP raises perceived tier value and drives web subscriptions through three evidence-backed mechanisms - with the honesty caveats promoted *into* the thesis.

1. **Unique wedge.** Seasonax ($49.95-$100/mo, no AI) and Financhill ($199/mo) have **no in-assistant surface**, so "your seasonal signals, AI-scored, inside your AI assistant" is a category only TradeWave occupies. This is a differentiation claim for the web pricing page + upgrade copy - **not** a web price change.
2. **Pre-filtered high-WTP, low-CAC distribution.** MCP connectors are gated behind the assistant vendors' own paid tiers, so every reachable user already pays ~$20/mo for AI - a qualified showroom. Self-serve CAC (~$702) is ~16× cheaper than sales-led (~$11,400) [singlegrain.com], and there is **no native in-assistant billing** (OpenAI Apps SDK recommends external checkout [developers.openai.com/apps-sdk/build/monetization]), so 100% of conversion returns to TradeWave's Stripe for the **web** sub. MCP can only be a lever, never a SKU.
3. **Mirror makes the ladder legible in-chat.** Every session the user sees "you have N markets here; Strategist has 15" - a soft, honest paywall impression at the highest-intent moment, with the floor staying useful **and** consistent with the web nudge engine (which is exactly why Analyst MCP scope is clamped to the same unlocked set the web nudge uses, not all-15 - contradictory cross-surface upsell copy is avoided by construction).

**Honesty caveat (decision-bearing, in the thesis).** There is **no public quantified case study** tying MCP-availability to a measured conversion/WTP lift (web search returned none). The cited reverse-trial benchmarks (14-25%) come from **card-on-file** trials where conversion = the auto-charge; this is a **no-card, must-actively-go-to-Stripe** taste, so realistic conversion sits at loss-framed **feature-discovery** rates (low single digits), not auto-charge rates. And the reachable population is structurally capped (a $0 Explorer who pays no AI vendor literally cannot connect). **So MCP is a tier-up accelerant on an already-engaged high-WTP slice, not the primary free→paid volume funnel** - the web reverse trial + in-app paywalls remain the volume lever.

**Action (numeric, decision-bearing):**
- Do **not** bake MCP lift into revenue forecasts. Set an explicit conservative working assumption (MCP-teaser → Stripe behaves like loss-framed in-app feature discovery, low single digits).
- Set a numeric **kill/keep gate:** instrument first-MCP-connect → teaser-expiry → web-Stripe-checkout as a funnel with connect-rate-by-tier; if web-checkout rate among teaser-expired users **< 2% after 200 connects**, MCP stays a perception lever only and we do not invest in further teaser surfaces.
- **Soften the live pill** in the same change that flips `MCP_LIVE`: `generate_home_page.py:1005` currently reads *"Now inside ChatGPT and Claude, free on every plan"* → change to *"Now inside ChatGPT and Claude - what you see in chat mirrors your plan, with a time-limited full taste during your trial"* so the honest framing and the feature land together.

---

## 6. Implementation Deltas (code-cited)

All changes land in `apiserver/` (the gateway) except the copy fixes. **All gated behind `TW2_MCP_LIVE`** (`generate_home_page.py:192`).

| # | Delta | File:line | Type |
|---|---|---|---|
| 1 | Add `navigator` API entry (markets `['0','1','2']`, ml 5/day) + map in `WEB_TIER_TO_API` | `apiserver/tiers.py:31-55`, `:110` | net-new |
| 2 | Guard sellable-catalog iterators against the navigator entry (reuse `INTERNAL_TIERS` exclusion) | `apiserver/tiers.py:65` pattern | net-new |
| 3 | Narrow Dev markets `ALL_MARKETS` → `['0','1','2','3','4','5','6','11']` | `apiserver/tiers.py:37` | edit |
| 4 | New `WEB_TIER_TO_MCP` dict (markets + rate + opp + own `ml_daily_limit`) + import-time subset assert (mirror `tiers.py:117`) | `apiserver/tiers.py` | net-new |
| 5 | Replace the `workos_principal` branch to resolve from `WEB_TIER_TO_MCP` keyed on `row['tier']`, with **MAX(web-mirror, explicit-api_tier)** precedence | `apiserver/auth.py:147-159` | edit |
| 6 | `mcp:`-prefixed metering user_id (mirror the `cb:` precedent) | `apiserver/auth.py:164` pattern | net-new |
| 7 | Add `reverse_trial_ends_at` to both SELECTs | `apiserver/db.py:30`, `:46` | edit |
| 8 | **Cross-process feasibility (C3):** shared module for cutoff math + `level_access_hierarchy` + `ROLE_BYPASSES_TIER`, imported by both processes (option a); verify the apiserver deploy ships it | new shared module; `web/app.py:1530` is the current home | **blocking gate** |
| 9 | Teaser resolution: Explorer = remaining web-trial days mirrored to Strategist scope, capped ML 50/day, one window per WorkOS id | `apiserver/auth.py` + teaser module | net-new |
| 10 | Navigator teaser: separate `navigator_mcp_teaser_ends_at`, first-connect, Analyst scope, once per identity, never touch `reverse_trial_ends_at` | new column/key | net-new |
| 11 | Required `teaser_state {active|expired, ends_at, post_teaser_scope}` on every teaser tool response | MCP tool layer | net-new |
| 12 | Fix stale comment "no runtime readers as of 2026-06-24" (C1: `app.py:797` IS one reader) | `config.py:633-634` | copy |
| 13 | SLA: delete/qualify `<li>SLA guarantee</li>`; scrub `:886` prose to Enterprise-by-agreement | `site/api_marketing/generate.py:820`, `:886` | copy |
| 14 | Soften MCP home pill in the same change as `MCP_LIVE` flip | `site/generate_home_page.py:1005` | copy |
| 15 | Supersede `PRICING_QUOTA_SPEC.md` §1/§3 (MCP==WEB), keep Fix A/B/D; **also** update `docs/TRADEWAVE_ECOSYSTEM.md` (auth/billing + TW1↔TW2 entitlement mapping) per CLAUDE.md same-commit rule | docs | **blocking gate** |

**`MCP_LIVE` flip is gated on:** #4, #5, #7, #8, #9, #11, #14 landing **together** with passing tests. Absent the teaser build, flipping `MCP_LIVE` gives a trial Explorer S&P-only/5-ML in chat = **worse than web** = day-one bait-and-switch.

**Verified-feasible primitives:** `ml_quota._limit` reads `cust['entitlements']['ml_daily_limit']` (`ml_quota.py:34`), so a distinct MCP entitlements dict works without touching the quota engine. The `cb:` namespacing precedent (`auth.py:164`) proves per-principal bucket isolation works.

---

## 7. Risks + What to A/B Test

**Risks (each with code-verified mitigation):**

1. **False-reuse build risk (load-bearing).** The teaser is net-new, not a reuse of the reverse-trial clock (gateway is trial-blind: `db.py` SELECTs omit the column; `auth.py:155` resolves via `api_tier_from_user`; `effective_tier` is web-only + explorer-only). *Mitigation:* gate `MCP_LIVE` on deltas #7/#8/#9/#11/#14 landing together.
2. **Cross-process import feasibility (C3).** apiserver imports nothing from config/web/tier_compat. *Mitigation:* pick option (a) shared module or (b) authenticated endpoint **before** `MCP_LIVE`; don't leave it assumed.
3. **Explicit api_tier precedence trap.** `api_tier_from_user` returns the explicit column first (`tiers.py:131-134`). *Mitigation:* MCP scope = MAX(web-mirror, explicit-api_tier); test `(has-api_tier × has-web-sub)`; name the Founder case.
4. **Three Analyst scope maps disagree** (15 / 6 / 8). *Mitigation:* clamp Analyst MCP to `['0','1','2','3','4','5','6','11']`; fix the stale `config.py:633` comment same change.
5. **Date-lock-in-MCP is net-new, not a parenthetical** (grep = nothing). *Mitigation:* take the clamp path (no redaction build); the all-15-with-teasers UX is a separate blocking item with a redaction test if ever pursued.
6. **Per-surface AI gating is net-new, not mirroring** (5/day API vs 0/day MCP for the same identity). *Mitigation:* distinct MCP entitlements dict (`ml_quota.py:34` reads it); `mcp:` metering principal so buckets never collide; test tier × in/out-of-window × API-key/OAuth.
7. **Navigator teaser is a second trial** (Navigator never gets the explorer reverse trial). *Mitigation:* separate column/key, never touch `reverse_trial_ends_at`; ship Explorer first, Navigator after the rail proves out (or sooner if data favors).
8. **Disclosure drop = dark pattern** (must survive host-LLM paraphrasing). *Mitigation:* required machine-readable `teaser_state` field + DaysRemainingPill + account page as load-bearing channels; email is best-effort only; build-gating test asserts the in-band field, never the email.
9. **Business SLA - scoped to one line (C4).** *Mitigation:* one-line fix at `:820`/`:886`; sell Business on 50 seats + named support + commercial license.
10. **Pricing inversion (real).** Strategist bundles the $199 Pro entitlement with no cap in code. *Mitigation:* don't claim a phantom cap; resolve via higher published rate caps + no web seat, stated on the page.
11. **Conversion magnitude unproven + audience capped.** No MCP-lift case study; cited benchmarks are card-on-file; reachable population gated behind paid AI vendors. *Mitigation:* treat MCP as accelerant not volume funnel; the §5 kill/keep gate (<2% checkout after 200 connects → perception-lever-only).
12. **Doc supersession (precise).** Reverse `PRICING_QUOTA_SPEC.md` §1/§3 to MCP==WEB; keep Fix A/B/D; **also** update `docs/TRADEWAVE_ECOSYSTEM.md` per the CLAUDE.md same-commit rule (blocking, not a footnote).

**What to A/B test (instrument from day one):**

- **Teaser duration:** remaining-days mirror vs a capped fresh window (within the honesty rail) - watch connect→checkout, not just connect.
- **Loss-framed copy:** value-quantified usage recap ("23 setups across 15 markets") vs feature-list nudge (hypothesis: ~40% lift for ROI framing [gtmstrategist.com]).
- **Navigator teaser scope:** Analyst-scope taste (recommended) vs Strategist-scope taste - measure which converts to *which* tier and at what one-rung-vs-leap rate.
- **Sequencing:** Explorer-first vs Navigator-first, driven by **connect-rate-by-tier** (the data that decides whether the thin Explorer slice or the paid Navigator slice is the real funnel).
- **Nudge cadence post-expiry:** at-cap-only-with-cooldown vs once-per-session vs standing banner (watch churn/annoyance signals, not just clicks).
- **The kill/keep gate itself:** web-checkout rate among teaser-expired users; pre-set 2% / 200-connect threshold to decide perception-lever-only vs invest-in-more-surfaces.

*Sources: `apiserver/tiers.py`, `apiserver/auth.py`, `apiserver/db.py`, `apiserver/ml_quota.py`, `web/app.py`, `config.py`, `site/api_marketing/generate.py`, `site/generate_home_page.py` (all read/verified on dev `/home/flask`, 2026-06-29); `docs/PRICING_QUOTA_SPEC.md`; `docs/marketing/PRICING_COMP_REANCHOR.md`; comps massive.com, twelvedata.com, alphavantage.co, seasonax.com, financhill.com; mechanics chartmogul.com, userpilot.com, zuplo.com, hubspot.com, revenuecat.com, ftc.gov, perplexity.ai, developers.openai.com.*