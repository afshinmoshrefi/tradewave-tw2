# TradeWave — Per-Tier Quota Spec Across Surfaces (web / MCP / standalone API)

Status: PROPOSAL (2026-06-17). Confirmed decision behind it: **MCP is a feature of the
consumer tiers, including free — not sold separately; the developer API is the only
thing sold standalone.** ("Price the pattern, not the pipe.")

> **SUPERSEDED IN PART (2026-07-05, shipped in `apiserver/tiers.py` — that file is the
> SSOT, not the tables below):** (a) API billing is **MONTHLY ONLY** — the annual
> "2 months free" line below is dead; `price_annual` no longer exists and the seeder
> archives stale annual prices. (b) The rate row is obsolete: per-day quotas were
> re-anchored to "one per-symbol card for everything in your scope per trading day"
> (US+ETF ~3.7k symbols, all markets ~18.7k): free 10/100, dev 60/1,000, pro
> 120/5,000, business 300/20,000 (min/day). (c) Consumer-MCP mirrors re-scaled to
> assistant-sized caps (Analyst-in-chat 1,000/day, Strategist-in-chat 2,000/day).
> Rationale + the sweep math live in `docs/TRADEWAVE_ECOSYSTEM.md` (API billing +
> quota model). Fix A (Pro $199 vs Strategist $129 inversion) remains OPEN.

Sources of truth this reconciles:
- `config.py` `TIER_FEATURES` — web app entitlements (Explorer / Analyst / Strategist)
- `apiserver/tiers.py` `API_TIERS` + `WEB_TIER_TO_API` — programmatic (MCP + API) entitlements
- `apiserver/ml_quota.py` — per-day ML metering (Redis db4); `routes.py` graceful 200 nudge

---

## 1. Principles (the rules that make three surfaces coherent)

1. **Same tier = same pattern entitlement on every surface.** A surface (web table /
   chat / raw JSON) changes the *interaction mode*, not *what you're entitled to*. Market
   scope and ML eligibility must match across web, MCP, and API for the same tier.
2. **The ML/day meter governs the PROGRAMMATIC surfaces (MCP + standalone API), not the
   web UI.** A human clicking the wave-viewer is bounded by the screen and UI gating; a
   script/agent is metered per day. This is why web ML is "unlimited views" while MCP/API
   ML is capped per tier.
3. **Market breadth is the Strategist line on EVERY surface.** Futures, forex, bonds,
   international, and crypto patterns are Strategist/Pro-and-up — in the web app *and* over
   MCP/API. (Today the API leaks all 15 markets to Dev; see §5 Fix B.)
4. **The daily pick + its track record are always free/unmetered, everywhere.** It is the
   permanent teaser; even a free user at 0 ML remaining still gets it every day.
5. **A new user's 7-day reverse trial spans all surfaces.** Connecting via ChatGPT/Claude
   is itself the signup, and should grant the same 7-day full-Strategist experience in
   chat that it grants on the web. (Today it elevates web only; see §5 Fix D.)

---

## 2. Web app entitlements (from `config.py` TIER_FEATURES)

| Dimension | Explorer (free) | Analyst | Strategist |
|---|---|---|---|
| Price (mo / yr-eff.) — current live | $0 | $47 / $37 | $149 / $99 |
| Price (mo / yr) — **proposed** | $0 | **$39 / $25 ($299/yr)** | **$129 / $83 ($999/yr)** |
| Market scope | DJ30 only | US stocks+ETFs+US indices (ids 0,1,2,3,4,5,6,11) | **All 15** |
| Patterns / market | 5 | 100 | 500 |
| Change date range | no | yes | yes |
| PE-cycle | display only | manual filter | manual + auto |
| ML in opp table | DJ30 only | yes (UI-gated) | yes |
| Portfolios | 1 | 25 | 100 |
| Watchlists (items) | 0 | 5 (50) | 50 (500) |
| SMN articles | no | yes | yes |
| Support | community | email | premium |
| Reverse trial | 7-day full Strategist → Explorer | — | — |

Prices "proposed" are penetration-first recommendations and NOT locked.

---

## 3. Programmatic entitlements (MCP + standalone API — identical, by tier)

MCP and the standalone API consume the **same** `API_TIERS` entitlement. The only
difference is *auth/billing source*:
- **Consumer MCP** (ChatGPT/Claude): WorkOS OAuth → resolves the user's web tier →
  `WEB_TIER_TO_API` maps it (no extra charge — it's their consumer sub).
- **Standalone API** (developers): an explicit `users.api_tier` set by an API Stripe sub.

| Entitlement | free | dev | pro | business |
|---|---|---|---|---|
| Maps from web tier | Explorer | Analyst | Strategist | (none) |
| Standalone price (mo) — current | $0 | $39 | **$199** ⚠ | $599 |
| Standalone price (mo) — **proposed** | $0 | $39 | **$99** | **$499** |
| Standalone price (yr) | $0 | $390 | 10× mo | 10× mo |
| Market scope — current | S&P 500 only (`["2"]`) | **ALL 15** ⚠ | all 15 | all 15 |
| Market scope — **proposed** | S&P 500 only | **Analyst set (0,1,2,3,4,5,6,11)** | all 15 | all 15 |
| ML-eligible markets in scope | 2 | 0,1,2,3,4,11 | 0,1,2,3,4,11 | 0,1,2,3,4,11 |
| **ML scores / day** — current | 5 | 100 | unlimited | unlimited |
| **ML scores / day** — **proposed** | **10** | 100 | unlimited | unlimited |
| Daily-pick ML | free/unmetered | free | free | free |
| Results per scan (`opp_limit`) | 3 | 100 | 1000 | 5000 |
| Rate (per min / per day) | 10 / 100 | 60 / 5000 | 300 / 50000 | 1200 / 250000 |
| API keys (`max_keys`) | 1 | 3 | 10 | 50 |
| Graceful ML-limit behaviour | HTTP 200 `requires:upgrade` + `upgrade_url` + `ml_remaining_today` (never an error) | same | n/a | n/a |
| All 17 MCP tools available | yes (capped) | yes | yes | yes |

⚠ = current value that creates an inconsistency — see §5.

Annual on the API stays "2 months free" (10× monthly, ~17% off) — API buyers are less
price-sensitive than consumers, so a shallower annual discount than the consumer ~35% is
fine, and it's moot for bundled users (a Strategist-annual buyer already has Pro-API).

---

## 4. Free-MCP spec (the ChatGPT/Claude acquisition funnel)

This is the most important surface for penetration — it's free distribution in the
ChatGPT and Claude connector directories where no competitor exists.

**Connect flow (zero anonymous access — identity is required to meter, and the connect IS
the signup):**
1. User adds the TradeWave connector in ChatGPT/Claude → "Sign in with TradeWave" (WorkOS
   OAuth). One click = a new Explorer account.
2. **First 7 days:** reverse trial → full **Strategist/Pro** MCP power in chat (all 15
   markets, unlimited ML). *(Requires §5 Fix D.)*
3. **After day 7:** drops to the free-MCP limits below.

**Permanent free-MCP limits (the `free` API tier):**
| Limit | Value |
|---|---|
| Markets | S&P 500 only (market `2`) |
| ML scores/day | **10** (proposed; 5 today) — *plus* the daily pick's ML, always free |
| Results per scan | 3 |
| Rate | 10/min, 100/day |
| Tools | all 17 (flagship + primitives), capped as above |
| Always-on hooks | daily pick + live track record, every day, unmetered |
| At the ML cap | graceful 200 nudge in-chat ("daily ML limit reached — upgrade for unlimited") with an upgrade link → converts inside ChatGPT/Claude |

The conversion mechanic: a free user asks "find me seasonal setups in [non-S&P market]"
or burns their 10 ML → the tool returns the upgrade nudge *inside the chat client* →
they subscribe to Analyst/Strategist → same login now works at the higher tier across
chat AND web.

---

## 5. Inconsistencies in the current code to fix (found while reading `tiers.py`)

**Fix A — Pricing inversion: Pro API ($199) > web Strategist ($149/$99).**
Strategist *includes* Pro API (`WEB_TIER_TO_API`), so a buyer gets Pro-API for $99/mo
(annual) inside Strategist while standalone Pro API costs $166–199/mo. The component
costs more than the bundle — irrational on a pricing page.
→ Set standalone **Pro ≤ Strategist**. Recommended: Pro $99/mo. Framing this unlocks:
"Strategist = Pro API **plus** the entire web platform for just +$30/mo." Same logic:
Dev $39 ≤ Analyst $39 (Analyst = Dev API + app).

**Fix B — Dev API grants ALL 15 markets; web Analyst grants 8.**
`API_TIERS["dev"]["markets"] = ALL_MARKETS` lets an Analyst-level user pull
futures/forex/bonds/intl/crypto patterns over MCP/API — the exact breadth that is the web
Strategist upsell. It leaks the upsell and breaks Principle 3.
→ Set `dev` market scope to the Analyst set `["0","1","2","3","4","5","6","11"]`. Keep
pro/business at all 15.

**Fix C — Free market mismatch: web Explorer = DJ30; API free = S&P 500.**
→ Pick one for a consistent "free = the S&P 500" story. Recommend **S&P 500 (market 2)**
on both (most recognizable to the ChatGPT audience; already the API default). Aligning
web Explorer DJ30→S&P 500 is a small product call (touches homepage/reverse-trial copy).

**Fix D — Reverse trial elevates web but (likely) not MCP/API.**
The api gateway reads raw `users.tier` (`db.py`), while the 7-day Strategist elevation
lives in `web/app.py` `effective_tier()`. So a new user connecting via ChatGPT/Claude
gets *free* limits instead of the trial's full power — the single biggest miss in the MCP
funnel.
→ Have the gateway / WorkOS-principal resolution compute `effective_tier`
(check `reverse_trial_ends_at`) before `WEB_TIER_TO_API`, so the trial spans all surfaces.

**Minor — internal principals.** The `mcp` fallback tier (`INTERNAL_TIERS`) has its own
ml_daily_limit=5; if §4 bumps free to 10, mirror it (it's a fallback that shouldn't fire
in normal OAuth use). Tara's `chatbot` principal (30 ML/day per web user) is a separate
in-app bucket and out of scope for the sellable spec — but consider scaling Tara's daily
budget by tier later (flat 30 today for everyone).

---

## 6. Proposed `apiserver/tiers.py` edits (for review — not yet applied)

```python
# Fix C: free market already "2" (S&P 500) — keep; align web Explorer separately.
# Fix A: lower Pro (and Business) so the bundle is never cheaper than the component.
"pro":      { ... "price_monthly": 99,  "price_annual": 990,  ... }
"business": { ... "price_monthly": 499, "price_annual": 4990, ... }
# Fix B: Dev market scope = Analyst set, not ALL_MARKETS.
"dev":      { ... "markets": ["0","1","2","3","4","5","6","11"], ... }
# §4: free ML taste 5 -> 10.
"free":     { ... "ml_daily_limit": 10, ... }
# Minor: mirror the mcp fallback.
INTERNAL_TIERS["mcp"]["ml_daily_limit"] = 10
```
Plus Fix D in the gateway auth/principal path (compute effective_tier) and the
`create_api_products.py` / pricing-page reads that follow `price_*`.
```
