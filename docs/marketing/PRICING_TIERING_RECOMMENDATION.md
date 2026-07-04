Every reviewer claim is confirmed against live code. The pricing.html shows falsified $41/$58/$131/$199 prices, "Auto PE-cycle detection", "50×500 watchlists"; the home generator has the Navigator AI over-claim (1110, 1113), Strategist "election-cycle discovery" (1166), "4-year cycle" (1172), "track up to 500" (1174), "500 symbols" (1175), Analyst "5 watchlists" (1144); and app.py:1185 returns `open_app` for navigator despite the docstring at 1164 requiring score access. I have what I need to write the decisive report.

The latest reviews surface one genuinely new evidence point the prior plan got wrong: the research's actual #1 lever is **ML-on-free-DJ30** (a LADDER C), not ML-on-Navigator — and "LADDER B = Navigator AI" was mislabeled as research-coherent. I'll incorporate that as the third option and fix the other verified issues (the inert 400, the over-recommend-Analyst-for-Dow-only bug, the SSOT must read quota dicts not TIER_FEATURES, the $39 toss-up, the dormant $58/$199 already-live-on-pricing.html).

---

# TradeWave Tier Ladder & Pricing - Final Recommendation

*Prepared 2026-06-29. All gates verified against live `/home/flask/config.py`, `site/generate_home_page.py`, `web/templates/pricing.html`, and `web/app.py` on the dev box. Prices are the live Stripe-authoritative grounding values, not the stale figures in the research doc or in `TIER_FEATURES`.*

---

## 1. Executive Summary + Headline Recommendation

TradeWave's ladder is structurally sound and the price points are market-validated. The work is **not** a re-architecture - it is (a) one owner decision on where AI scoring starts, and (b) fixing a set of *verified* honesty/runtime bugs where the marketing currently promises things the runtime denies and the pricing page literally displays wrong prices.

**Stance: trust-first freemium.** Keep four backend tiers, present them as three visual decisions (Free / Analyst-default / Strategist-anchor) with Navigator as a de-emphasized-but-visible step-up. The free tier stays genuinely useful; the 7-day card-free reverse trial is the primary conversion engine; every upgrade wall maps to one nameable need.

**The headline recommendation (ship-now ladder):**

| Tier | Level | Monthly | Yearly (eff. /mo) | AI scoring | Markets (date-unlocked) | Role |
|---|---|---|---|---|---|---|
| **Explorer** (Free) | 1 | $0 | $0 | No | DJ30 only (`['0']`) | On-ramp + brand |
| **Navigator** | 2 | $19 | $14 ($168/yr, ~26%) | No *(owner fork below)* | Dow 30 + NASDAQ 100 + S&P 500 (`['0','1','2']`) | De-emphasized step-up |
| **Analyst** | 4 | **$47** *(candidate $39)* | $33 ($396/yr) | Yes | All US stocks + ETFs (`['0','1','2','3','4','11']`) | **Recommended / target** |
| **Strategist** | 6 | $129 | $99 ($1,188/yr, ~23%) | Yes (same US+ETF scope) | All 15 markets incl. futures/forex/bonds/crypto + aggregates 5,6 | Premium anchor |

**The one decision for the owner (Section 4):** where AI scoring starts. I recommend **shipping LADDER A now** (AI at Analyst - zero gate change, matches your own 2026-06-23 decision) and treating the two research-aligned alternatives as instrumented experiments, not preconditions.

**The honesty fixes ship regardless of that decision** and several are urgent because they are *live false claims today* (Section 8).

---

## 2. Per-Tier Feature Plan + Evidence Behind Each Fence

The two value metrics that scale cleanly with a trader's realized value are **market breadth** (resource keys 0-16, permanent IDs) and **the AI/ML calibration layer**; depth quotas (portfolios/tracked/watchlists) are the secondary up-ladder fence. This is the textbook value-metric choice for an analytics tool where value rises with sophistication, not raw consumption (Patrick Campbell / ProfitWell; Monetizely feature-gated framework).

### Explorer (Free) - the honest on-ramp
- **Features:** today's top-5 Dow 30 patterns with the full every-year green/red evidence table (losing years left in); Trend Score; real-time prices; EDGAR earnings dates; PE-cycle overlay on a loaded pattern; public scorecard; 1 portfolio / track 5.
- **Code-fact fences:** `level_access_hierarchy['1']=['0']` (DJ30 only); `max_opportunities_loggedin_free=5`; `change_start_date=False`; `num_portfolios['1']=1`, `num_watchlists['1']=0`, `num_watchlist_items['1']=0`; excluded from `ml_score_access_levels`.
- **Evidence:** a genuinely-useful free tier is acquisition infrastructure, not lost revenue - it lowers CAC ~30% and retains converts ~20% better (ProfitWell), and freemium that delivers a week-1 aha converts 3-4x (Amplitude/Mixpanel). The rule it must satisfy: *complete solution to a narrow problem* (DJ30, today) - never a complete broad one (Campbell). Explorer is correctly fenced.
- **Proposed sweetener (config-only, NOT the AI fence):** the day-7 cliff is steep. Lift `num_watchlists_allowed_by_level['1']` 0→1 **and** `num_watchlist_items` 0→5-10 so a Dow watcher can save the patterns they find. *(Reviewer catch: raising items while `watchlists_max` stays 0 is inert - there must be a list to put items in. Fix the list count first.)*

### Navigator ($19) - breadth + control
- **Features:** 3 markets date-unlocked (Dow/NASDAQ/S&P, keys 0,1,2); browse any start date; top 50 patterns/market; PE-cycle manual filter; 3 portfolios / track 25 / 1 watchlist (25 symbols).
- **Code-fact fences:** `level_access_hierarchy_premium['2']=['0','1','2']`; `change_start_date=True`; quotas `num_portfolios['2']=3`, `num_watchlists['2']=1`, `num_watchlist_items['2']=25`; **excluded from `ml_score_access_levels`** (so under LADDER A it has no AI).
- **Evidence:** Equity Clock (the direct seasonality comp) is $24.95/mo; Finviz Elite ~$39.99; TradingView Essential $14.95 - Navigator at $19 sits inside/below this entry band, the "painless yes." Its honest job is breadth and control (any date, 3 indices, 10x the patterns), which is a discrete "I want something new" feature-gate.
- **Ship-readiness:** Navigator is **already fully wired** - DB enum (migration `a1f4d2c9e7b3`, applied), `valid_tiers` (app.py:1814), checkout price map (app.py:1775-76), React level '2' gating, and the generated home page emits live Navigator checkout URLs. The research doc's "expensive new $19 tier (DB migration + React rebuild)" cost is *already paid*; it is not a net-new build.
- **Basket caveat (reviewer catch):** the research's loss-shaped $19 rung was a **4-market** basket (0,1,2,3 = +Russell) with ML on all four. Live Navigator is **3 markets, no Russell** (key 3 unlocks at Analyst). Do not claim Navigator *is* the research's rung; it is a near-but-not-exact realization.

### Analyst ($47, candidate $39) - the target / first full-universe AI tier
- **Features:** AI scoring (ml_score / win_prob / pred_return); all US stocks + ETFs date-unlocked; custom start dates; top 100 patterns/market; PE filter; 25 portfolios / track 100 / 10 watchlists (50 symbols); Seasonal Market News; weekly Q&A webinar; email support.
- **Code-fact fences:** `ml_score_access_levels` includes '4'; `level_access_hierarchy_premium['4']=['0','1','2','3','4','11']` (note: **does NOT** date-unlock aggregates 5,6 or the 9 non-US asset classes - those are Strategist-only); `num_portfolios['4']=25`, `num_watchlists['4']=10` *(the home page wrongly says 5)*, `num_watchlist_items['4']=50`.
- **Evidence:** AI scoring is TradeWave's headline differentiator; the feature-classification framework (CRV) says gate differentiator features at higher tiers and never bundle them into the base tier. Placing AI behind the compromise line makes Analyst the "best-reasons" middle choice (Simonson 1989; Ariely). Every AI-rating competitor paywalls its score as the premium payoff: Danelfin gates "all AI scores" to its $25 paid plan; Trade Ideas restricts Holly AI to Premium, not Standard.
- **AI scope is global US+ETF only:** `ml_score_resource_ids=['0','1','2','3','4','11']` is a single global list - **Analyst and Strategist have identical AI scope.** AI never scales by breadth up-ladder; it is never computed for futures/forex/bonds/crypto at any tier. Never imply Strategist gets "more AI."

### Strategist ($129) - the premium anchor + multi-asset buyer
- **Features:** date-unlock + symbol-typing on all 15 markets incl. futures/forex/bonds/foreign indices/crypto **and** the broad-index aggregates 5,6; AI on US+ETF (same global scope as Analyst); 100 portfolios; 50 watchlists (100 symbols each, **not 500**); publish up to 500 date-range reports; weekly strategy Zoom; premium support.
- **Code-fact fences:** `level_access_hierarchy_premium['6']=` all 15 keys (the **only** tier date-unlocking the 9 non-US classes + 5,6); `num_portfolios['6']=100`, `num_watchlists['6']=50`, `num_watchlist_items['6']=100`, `num_opp_reports['6']=500`.
- **Evidence:** a high anchor lifts mid-tier selection ~28-40% (ConversionXL; Slack's $500 Enterprise lifted Professional 28%). Strategist's primary job is to make Analyst the obvious Goldilocks pick. At $129 it credibly undercuts MarketSurge ($149.95) as the all-markets pro tier.
- **Its real fence is breadth (the 9 non-US asset classes + aggregates 5,6), NOT the election cycle.** The PE flags (`pe_cycle_filter_auto/manual/overlay`) have **zero runtime readers** anywhere outside config.py (grep-verified across web/, appserver/, web-react/, site/), and PE *overlay reaches Explorer*. Any "election-cycle discovery" / "4-year cycle" exclusive claim is an unenforceable fence and must be scrubbed (Section 8).

---

## 3. Final Pricing + Anchoring/Annual Logic + Comps/WTP

**The price levels are validated; do not change Navigator $19 or Strategist $129.** The entire ladder lands inside externally observed WTP bands:

| TradeWave | Comp anchors (directional, see hygiene note) |
|---|---|
| Free Explorer | TradingView Basic free-forever = table stakes |
| Navigator $19 | Equity Clock $24.95 (direct seasonality comp); Finviz Elite ~$39.99; TradingView Essential $14.95 |
| Analyst $47 | Seasonax $49.95 (category-direct, **no AI**, 3-day trial); Danelfin Pro ~$49; TradingView Premium ~$49.95 |
| Strategist $129 | undercuts MarketSurge $149.95; well below Trade Ideas Premium $188-254 |

**FREEZE correction (this retracts a load-bearing error in the prior plan):** FREEZE does **not** forbid repricing forward. Per the `tradewave-pricing` skill (SKILL.md:12-13, 31-32) and the research doc, FREEZE forbids *editing/archiving an active-sub price*; it explicitly **sanctions creating a NEW price + grandfathering existing payers**. Repricing forward is the routine, allowed procedure - the single highest-leverage lever for a price-sensitive audience.

**Analyst $47 → $39: a genuine toss-up, owner's revenue-weighted call - NOT a lean-adopt.** Both sides have evidence:
- *For $39:* the research's entry comp cluster ($15-30) is where this audience comparison-shops; "$47 is a gap with nothing below it" (doc reason #4). FREEZE-safe via a new price.
- *For $47:* against the **only** category-direct comp (Seasonax $49.95, no AI), Analyst at $47 *with* AI scoring + a 7-day full trial already undercuts while offering more. And **Navigator $19 already occupies the entry band** the $39 reprice targets - so $19→$39 is only a $20 gap, compressing the ladder, and the research's own mitigation (narrow the cheap rung) is *not in place* for the live 3-market Navigator. The doc's $39 was designed inside a *different* ladder (with ML-on-free + a narrowed rung beneath it); lifting it out severs that logic.

**Recommendation: keep $47 for now; instrument first.** If you adopt $39, do it via a new Stripe price + grandfather, widen the Navigator/Analyst *feature* gap to defend it, and track blended ARPU + the $19→$39 step-up split + new-$39 vs down-migrated-$47 (the doc's own cannibalization guard).

**Costless levers (no price touch, highest ROI):**
1. **Default the billing toggle to ANNUAL**, framed in dollars saved. Annual cohorts retain ~2.5x monthly at month 12; this is the biggest LTV lever and free. Route the trial-expiry CTA to *annual Analyst*.
2. **Flip the highlight from Strategist to Analyst** with a neutral "Recommended" badge (back a "Most Popular" claim with a real number only once data exists). The page currently promotes the *wrong* card (Strategist `highlighted:True`), inverting the entire compromise logic.

**Dormant-hike guardrail (ADOPT):** `monthly_price_post` is `58` (analyst) and `199` (strategist) in `TIER_FEATURES` - grep-confirmed zero runtime readers, BUT **$58/$199 are already displayed live on pricing.html** as the "or $X/mo" figure (lines 123, 138). Set `monthly_price_post == monthly_price_launch` in C2 so an accidental operator price-sync cannot fire a band-breaking hike.

**Evidence hygiene:** the in-repo comp cluster is the project-vetted primary source but is ~9 days old. Any external competitor *dollar figure* used to back a price decision must carry a same-week dated stamp (`as of YYYY-MM-DD, <url>`) or be dropped to a directional band. Do **not** claim "every AI competitor paywalls at ~$49."

---

## 4. The AI-Scoring-Tier Decision (the one owner fork)

This is the single most load-bearing structural choice; it cascades into the copy edits, the email CTA, and the recommender. **There are three evidence-backed options, not two** - the prior plan mislabeled "AI at Navigator" as the research's recommendation, which it is not.

| Option | Change | Backing |
|---|---|---|
| **LADDER A** *(recommended ship-now)* | Leave `ml_score_access_levels=['4','5','6','7']` untouched. AI starts at Analyst. Navigator = breadth/control only. | Matches your live 2026-06-23 decision (config:248-249) making "see the AI score" the upgrade payoff. Zero gate change. AI is the cleanest single fence. The 7-day trial (level '6') already gives the AI taste honestly, and its loss is the hook. Every honesty fix becomes unconditional. |
| **LADDER B** | Add '2' to `ml_score_access_levels` → Navigator's indices 0,1,2 carry AI. | A minimal-cost proxy for the research's *intent*. **But:** it gives AI on 3 markets, not the doc's 4 (no Russell), and it puts AI on a $19 *paid* tier - which is **not** the doc's mechanism. Dilutes the fence; contradicts the 2026-06-23 call. |
| **LADDER C** *(the research's actual #1 lever)* | Flip `TIER_FEATURES['explorer'].ml_scoring`→True **and** add '1' to `ml_score_access_levels` → **ML on the free DJ30 floor.** | This is the doc's load-bearing recommendation (reason #3, "highest-leverage change, nearly free + leak-proof"). The loss-shaped trigger (reason #5) *requires* AI on the **free** tier: the free user runs the ML-calibrated hunt daily on DJ30, then hits the breadth wall and pays "for more of the thing they already do every day." **Leak-proof** because `resources_allowed=[0]` clips ML to ~30 DJ30 mega-caps. **Directly contradicts your 2026-06-23 removal of free AI** - that is the real fork the research poses. |

**My recommendation:** ship **LADDER A** now (it is the decided state and unblocks all the honesty fixes). Then put **LADDER C** in front of yourself as a deliberate re-decision: *your own research names the thing you removed on 2026-06-23 as the single highest-leverage lever.* That conflict deserves an explicit yes/no, framed as "confirm the removal stands," not buried. LADDER B is the weakest of the three - it neither matches your decision nor the research's mechanism; carry it only as a fallback experiment if you want a cheap AI rung without touching free.

Critically: **AI does not scale by breadth under any ladder** (`ml_score_resource_ids` is one global list). The ladders only move *where AI turns on*, never its scope.

---

## 5. Free-Tier + Trial Strategy

Three layered motions, each doing a different job (the evidence is unambiguous that they are not substitutes):
1. **Explorer freemium = always-on low-CAC volume + week-1 aha.** Keep it genuinely useful; do not cripple it to force upgrades. Sweeten the steady-state floor with the watchlist sweetener (1 list, 5-10 items - config only, not the AI fence).
2. **The 7-day card-free reverse trial = the PRIMARY conversion engine.** Code-fact: `effective_tier()` mints level '6' while `reverse_trial_ends_at` is future, and '6' is in `ml_score_access_levels`, so every new user tastes full AI + all 15 markets for 7 days. The day-7 drop to Explorer is the loss-aversion hook. Reverse trials convert materially above pure freemium (loss-aversion / endowment). Keep it card-free (protects signup volume, fits the trust brand) and keep the keep-what-you-save endowment promise.
3. **The paid ladder = the destination.**

**The day-7 cliff is the gating risk.** Cushions: the watchlist sweetener; an **activation flow** driving the user to their first AI-scored, every-year-laid-out pattern in session 1 (aha-in-24h converts 3-5x; no core action in 48h → 70-80% churn); contextual soft-gate prompts; and an end-of-trial loss summary ("you used X AI-scored patterns across Y markets you're about to lose").

**Activation is PARTIAL/net-new, not done** - state this plainly. The telemetry *exists* (`OnboardingEvent` + `/api/onboarding/event` + `symbol_scored` client-side + `market_opened`), but the session-1 checklist UI is the *uncommitted* `onboarding.js / OnboardingWelcome.js / TrialConversionCard.js / DaysRemainingPill.js` in the working tree. Shipping those into a session-1 flow that fires the first AI-scored pattern is the named gating dependency for front-end-marketing the trial against the steep cliff.

**Front-door honesty fix:** `generate_home_page.py:1059` says "Create a free account to see more patterns across all markets" - false for a steady-state Explorer (DJ30-only). Fix to trial-honest copy: "Create a free account - 7 days of full access, then keep the Dow 30 free forever."

Measure conversion **per activated user** (saw an AI-scored, every-year-laid-out pattern), not per raw signup - fintech free tiers over-fill with low-intent casuals (2-4%).

---

## 6. The Conversion Thesis (honesty as the strategy)

The owner's inverse-incentive philosophy is **empirically the higher-converting, higher-LTV, lower-refund design**, not a constraint to work around:
- **Transparency raises conversion:** ~4 in 10 startups improved conversion from clarity alone; NNG: +34% purchase likelihood with clear pricing.
- **The blemishing effect** (Ein-Gar, Shiv & Tormala, *JCR* 2012) - adding minor negatives after positives *raises* purchase intent - is exactly "we leave the losing years in," productized. Frame it prominently, positive stats first, red years second, never hedged (per the confident-evidence voice rule).
- **Perceived self-interest is a conversion tax:** conflicted financial advice makes advisees invest substantially less even when the advice is optimal. "Recommend the smallest plan that fits" removes that signal.
- **Negative disconfirmation (reality < promise) hurts ~2x** what positive surprise helps and drives first-cycle refunds - which is *precisely* the risk of the live Navigator "AI scoring" over-claim and the falsified pricing-page prices.

**The spine: one legible value gradient, each wall = one nameable need.**
LADDER A spine: Free (DJ30) → Navigator (BREADTH: 3 US indices + any date, no AI) → Analyst (INTELLIGENCE: AI + full US universe) → Strategist (FULL BREADTH: the 9 non-US classes + aggregates). *Explicit caveat:* under LADDER A the Navigator→Analyst wall couples two needs (AI + depth quotas 1→10 watchlists); accepted (AI is the headline) or softened by lifting `num_watchlists['2']`. LADDER C collapses this cleanest of all (free AI → breadth wall).

**The central conversion bug (verified, fix in C4):** the trial-expiry recommender (`_min_tier_for_markets`, app.py:783, called :894) populates `market_ids` **only** from `market_opened` events; `symbol_scored` (OnboardingWelcome.js:74) carries `{symbol, source, on_trial}` with **no market_id**. So the AI signal and the market signal are *decoupled*, and the markets-only recommender returns `navigator` or `None` for an AI-hooked user - stripping the AI feature the trial sold. **Fix:** set `ai_used`, then floor `rec` to `analyst` when `ai_used and rec in (None,'explorer','navigator')`.

**But guard against over-selling (reviewer catch, important - it inverts your philosophy):** under LADDER A, opening market 0 (DJ30) during the trial auto-shows the AI column, so a *pure Dow-only* user would trip `ai_used=True` and get wrongly floored to Analyst when their honest smallest-covering tier is **free Explorer**. **Fix the intersection to exclude retained-free markets:** floor to Analyst only when the user touched AI on a **non-DJ30** ml-eligible market (intersect used markets with `{1,2,3,4,11}`) OR `symbol_scored` fired on a non-Dow symbol. A Dow-only AI user must be recommended Explorer/Navigator, not Analyst.

**Navigator-recommendability gate:** do not let the recommender or any which-plan selector *return or name* `navigator` until pricing.html (C5) shows a Navigator card with a live CTA - recommending an unpurchasable tier is its own trust break.

**Rank-ordered highest-ROI builds, above any price change:** (1) activation speed; (2) contextual soft-gate prompts at the exact wall (~4.2% vs ~1.3% generic; soft beats hard 3-5x) - which *operationalizes* the inverse-incentive AND is the conversion lever simultaneously; (3) a "Which plan do you actually need?" selector that says "Explorer is plenty if you only trade the Dow 30"; (4) annual-default + AI-usage-routed expiry CTA.

---

## 7. Risks + What to A/B Test Next

**Risks:**
- **The AI-tier decision is a real fork, not settled.** LADDER A trades away the research's loss-shaped trigger for the price-sensitive majority; LADDER C restores it but reverses your 2026-06-23 call. Surface both; do not let the report pre-decide it.
- **The recommender can become an over-seller** (Dow-only → Analyst) if the AI floor isn't scoped to non-DJ30 markets. This directly contradicts the trust-first mandate.
- **`num_opps_per_portfolio=4` has zero runtime readers** - so neither "track up to 400" nor "track up to 500" is an *enforced* ceiling. Do not assert a tracked-opportunity count until enforcement is confirmed; cite only verified quotas.
- **Pricing-skill memory references $58/$199 as last-synced live prices.** Before authoring any reprice command, audit Stripe metadata (one active price per (tier, period) slot) to confirm what existing subs actually ride and avoid creating a third active analyst slot.
- **Day-7 cliff steepness** caps free→paid lift until activation ships.
- **De-emphasized Navigator** risks starving a competitively-priced tier - instrument its share of new paid subs with a pre-committed response (promote in the selector copy, never to a co-equal 4th card).

**A/B test queue (instrument, then decide):**
1. Analyst $47 vs $39 (new price + grandfather) - blended ARPU, $19→$39 step split, down-migration vs net-new.
2. LADDER A vs LADDER C (ML-on-free-DJ30) - free→paid per activated user, day-7 retention, Analyst cannibalization.
3. Highlight/badge on Analyst vs no badge - mid-tier selection share.
4. Annual-default toggle vs monthly-default - annual mix, month-12 retention.
5. Contextual soft-gate prompt vs generic upgrade nag at each wall.
6. Activation checklist on vs off - time-to-first-AI-pattern, trial→paid.

---

## 8. Implementation Deltas vs Current Tiers

Split so the **urgent live-false-claim fixes ship immediately with zero owner input**, and only the ladder-dependent edits wait on the AI decision.

### PHASE 0 - ladder-INDEPENDENT (true under every ladder; ship now)

**P0-a. `site/generate_home_page.py` (pure copy + highlight flip; regen + deploy):**
- L1144: "5 watchlists" → **"10 watchlists, up to 50 symbols each"** (`num_watchlists['4']=10`).
- L1166: Strategist description "election-cycle discovery, all 15 markets..." → **"Everything in Analyst plus all 15 markets - futures, forex, bonds, foreign indices and crypto - and premium support."** (PE is unenforceable; zero runtime readers; reaches Explorer.)
- L1172: "Spot 4-year cycle setups on any pattern" → **"Date-unlock all 15 markets - futures, forex, bonds, foreign indices and crypto."**
- L1174: "track up to 500 opportunities" → **"100 portfolios; publish up to 500 date-range reports."** (Do NOT assert "400" - `num_opps_per_portfolio` is unenforced.)
- L1175: "50 watchlists, up to 500 symbols each" → **"50 watchlists, up to 100 symbols each"** (`num_watchlist_items['6']=100`).
- L1059: signup_prompt "all markets" → trial-honest copy.
- L1183/1153: flip `highlighted` **Strategist True→False, Analyst False→True** + neutral "Recommended" badge.

**P0-b. `web/templates/pricing.html` (live falsified prices - same urgency as the home page):**
- L122-123: "$41 /mo billed yearly · or $58/mo" → live Stripe Analyst **$33 / $47**.
- L137-138: "$131 ... or $199/mo" → live Stripe Strategist **$99 / $129**.
- L142: remove "Auto PE-cycle detection in Opportunity Table" (unenforceable).
- L143: "100 portfolios / 500 opps / 50×500 watchlists" → **"100 portfolios; 50 watchlists, 100 symbols each; publish 500 reports."**
- L100: remove the Phase-5 banner; L114/132/147: lift **all** `cta disabled` (Analyst + Strategist are also dead today, not just Navigator); add the de-emphasized Navigator card; verify CTAs resolve to `/api/stripe/create-checkout?tier=...` (app.py:1814).

**P0-c. `config.py` runtime (restart appserver/web; changes `recommended_tier` output):**
- L660: `TIER_FEATURES['analyst']['resources_allowed']` `[0,1,2,3,4,5,6,11]` → **`[0,1,2,3,4,11]`**. This key **IS read at runtime** (app.py:797 `_min_tier_for_markets`). It wrongly includes 5,6, which `premium['4']` cannot date-unlock - over-stating Analyst sufficiency for a markets-5/6 user.
- Fix the false comment at the `TIER_FEATURES` header: "reference/documentation only (no runtime readers)" is **false** for `resources_allowed`. Rewrite to: "ONLY `resources_allowed` is read at runtime; every other key (ml_scoring, quotas, change_start_date, pe_cycle_*) has zero runtime readers - re-grep before assuming doc-only."
- Neutralize the dormant hikes: `monthly_price_post` analyst 58→47, strategist 199→129 (they are *already live on pricing.html*).

**P0-d. Single-source-of-truth refactor (do it, but decoupled - ship P0-a copy fixes first, don't block them):** derive the rendered home page **and** pricing.html numeric quotas **exclusively** from `num_*_allowed_by_level` (the live runtime gates), and AI-eligibility/markets from `ml_score_access_levels` + `level_access_hierarchy_premium`. **`TIER_FEATURES` must contribute ZERO numbers** - it contains stale values (analyst `watchlists_max=5`, navigator `ml_scoring=True`, resources_allowed[4] including 5,6) that the refactor would otherwise re-emit as new bugs.

### PHASE 1 - ladder-DEPENDENT (gate behind the owner's Section-4 decision)

| File | LADDER A | LADDER B | LADDER C |
|---|---|---|---|
| `generate_home_page.py:1110,1113` (Navigator AI copy) | **Edit** to breadth/control framing | Leave (becomes true) | Edit; add ML-on-free messaging on Explorer card |
| `config.py:253` ml gate | unchanged | add **'2'** | add **'1'** + flip `TIER_FEATURES['explorer'].ml_scoring`→True |
| `web/app.py:1185` `account_cta_mode` | change to `('analyst','strategist')` only + fix docstring (1164); re-grep `effective_tier` consumers | leave (correct) | change to `('analyst','strategist')`; Explorer free-AI doesn't change email-CTA logic |
| C4 recommender floor target | `analyst` (scoped to non-DJ30 markets) | `navigator` for pure-3-index AI users | `navigator`/`explorer` per smallest-cover |

**Hard sequencing:** P0 ships first and standalone. Within Phase 1, gate any commit that *names or returns* `navigator` (the C4 recommender, the which-plan selector) behind the pricing.html Navigator card. The `account_cta_mode` value and the Navigator home-page copy must be edited *together* so they cannot diverge (copy says no-AI while CTA says AI). Update `docs/TRADEWAVE_ECOSYSTEM.md` tier/ML notes in the same change per CLAUDE.md.

**The Navigator-AI gap, resolved:** today the home page sells Navigator AI scoring (`generate_home_page.py:1110,1113`), `TIER_FEATURES['navigator']['ml_scoring']=True`, but `ml_score_access_levels=['4','5','6','7']` denies it at runtime - a live false paid promise at the exact upgrade wall. Under LADDER A this is fixed by **correcting the marketing** (and setting `ml_scoring`→False / sourcing AI-eligibility from the gate, never from `TIER_FEATURES`). Under LADDER B the copy becomes true. Either way, the discrepancy is closed in the same commit as the ladder decision - it does not ship half-resolved.

---

**Bottom line:** Ship Phase 0 immediately - those are live falsehoods (wrong prices, denied AI promise, unenforceable PE claims) that the disconfirmation evidence says directly cause refunds and first-cycle churn. Make the one Section-4 decision (I recommend LADDER A now + an explicit yes/no on LADDER C, since it reverses your own 2026-06-23 call and your own research calls it the top lever). Keep the price *points* as-is; the highest-ROI work is activation + contextual honesty + annual-default, not re-pricing.