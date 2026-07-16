# Tiering/Pricing - Implementation status (2026-06-29)

> Status: HISTORICAL IMPLEMENTATION LOG. Ladder A shipped, but the proposed Analyst
> $39 reprice did not. The current ladder and exact annual charges are recorded in
> `PRICING_STRATEGY.md` and `../PRICING_QUOTA_SPEC.md`. Do not execute the old operator
> instructions below without a new owner decision.

Implements the ladder-independent Phase-0 fixes from `PRICING_TIERING_RECOMMENDATION.md` + adopts
**Ladder A** (AI scoring starts at Analyst; no config gate change). All edits are on the DEV box,
UNCOMMITTED; prod ships via `bash ops/deploy.sh staging|prod` (operator). Nothing on Stripe was touched.

## SHIPPED on dev (verified against live code before each edit)
**`site/generate_home_page.py`** (home page copy; applied via `ops/regen_site.sh`):
- Navigator: removed the false "AI scoring on Dow, NASDAQ, and S&P 500" claim and the "with AI scoring"
  description -> reframed to breadth/control ("Dow, NASDAQ 100, and S&P 500 - fully date-unlocked", "with
  any start date"); the Navigator->Analyst upgrade teaser now names AI ("Upgrade to Analyst for AI scoring
  and all U.S. stocks plus ETFs"). [Ladder A: AI is the Analyst unlock.]
- Analyst: "5 watchlists" -> "10 watchlists" (runtime `num_watchlists_allowed_by_level['4']=10`).
- Strategist: description "election-cycle discovery" removed (PE is ungated/unenforceable); "Spot 4-year
  cycle setups on any pattern" -> "Futures, forex, bonds, foreign indices, and crypto"; "track up to 500
  opportunities" -> "publish up to 500 date-range reports" (the real `num_opp_reports['6']=500`); "up to
  500 symbols each" -> "up to 100 symbols each" (`num_watchlist_items['6']=100`).
- Front-door signup prompt -> trial-honest ("7 days of full access, then keep the Dow 30 free forever").

**`config.py`** (runtime; applied via web restart):
- `TIER_FEATURES['analyst']['resources_allowed']` `[0,1,2,3,4,5,6,11]` -> `[0,1,2,3,4,11]`. THIS IS READ AT
  RUNTIME (`web/app.py` `_min_tier_for_markets`); it was over-granting Analyst markets 5,6 which
  `level_access_hierarchy_premium['4']` cannot date-unlock (over-stated Analyst sufficiency).
- Dormant price hikes neutralized: `monthly_price_post` analyst 58->47, strategist 199->129 (so an
  accidental price-sync cannot fire a band-breaking hike).
- `TIER_FEATURES['navigator']['ml_scoring']` True->False (dead doc field; aligns with the runtime gate
  that excludes Navigator, so the planned SSOT refactor cannot re-emit it as a new bug).

**`web/app.py`**:
- `account_cta_mode` no longer returns `open_app` for `navigator` (Navigator has no AI-score view under
  Ladder A); now `open_app` only for `('analyst','strategist')`, matching the docstring.

## Applied + verified on dev
- Web tier restarted -> the `config.py` + `app.py` runtime fixes are LIVE on dev.
- Static home page regenerated; VERIFIED `/var/www/tradewave/home.html` now shows "10 watchlists", the
  Strategist asset-class line, "fully date-unlocked", "free forever" - and NO "AI scoring on Dow", NO
  "election-cycle discovery", NO "500 symbols", NO "5 watchlists".
- DEPLOY-BLOCKER FIXED (dev): `ops/regen_site.sh` first aborted on a PermissionError copying `_static`
  image assets (evidence_hero.png/.webp, shows_work.png, ask.png were root-owned from a prior root-run
  regen; the dir is flask-owned). Re-chowned them to flask on dev so the flask-run regen succeeds (the
  home HTML had already been written before the copy step, so the copy fixes were live regardless).
  **OPERATOR: staging/prod almost certainly have the SAME root-owned `_static` assets. Run
  `find /var/www/tradewave/_static -user root -exec chown flask:flask {} +` on each box BEFORE
  `bash ops/deploy.sh`, or the regen step will abort the deploy.**

## CORRECTION to the research report (verified)
The report flagged `web/templates/pricing.html` as showing live falsified prices ($41/$58/$131/$199) -
URGENT. **That is a FALSE ALARM.** The `/pricing` route (`web/app.py:1766`) ALWAYS `redirect("/#pricing")`
to the home-page pricing section; nothing renders `pricing.html`. It is orphaned dead code (a candidate
for deletion, not a customer-facing bug). The real pricing surface = the home page, which pulls live
Stripe prices and is now corrected. Verifying the adversarial agents' claims against the routing caught this.

## DECISION ADOPTED: Ladder A
AI scoring starts at Analyst; `config.py:253 ml_score_access_levels=['4','5','6','7']` UNCHANGED. To switch
to Ladder B later (AI at Navigator): add `'2'` to that list, restart the web+appserver, and re-add the
Navigator AI copy. One-line gate change, fully reversible.

## AUTHORED - operator to run (NOT done: live Stripe, money, shared TW1 account)
**Analyst $47 -> $39 reprice (FREEZE-safe).** Use the `tradewave-pricing` skill:
1. In Stripe, CREATE a NEW recurring price on the existing Analyst product (product metadata
   `product_line=eod`): $39/mo monthly, and a new yearly (~$29/mo eff., your call) - do NOT edit/archive
   the existing $47/$33 price (active subs stay grandfathered on it).
2. Point the Analyst monthly (+ yearly) `lookup_keys` / `TIER_PRODUCT_NAMES` map at the new price.
3. The home page auto-reflects it (it reads live Stripe via `_stripe_prices()`); no copy edit needed.
4. Verify checkout resolves to the new price; confirm grandfathered payers unchanged.

## REMAINING (recommended next; not done this pass)
- **C4 trial-expiry recommender** (`web/app.py` `_min_tier_for_markets`, ~:783/:894): the AI signal is
  decoupled from the market signal (`symbol_scored` carries no market_id), so an AI-hooked trial user gets
  recommended Navigator/None - stripping the AI feature the trial sold. Fix: set `ai_used` and floor the
  rec to `analyst` when `ai_used and rec in (None,'explorer','navigator')`.
- **SSOT refactor**: derive the home page (and any pricing surface) numeric quotas + AI/market eligibility
  exclusively from the `num_*_allowed_by_level` dicts + `ml_score_access_levels` + `level_access_hierarchy_premium`;
  `TIER_FEATURES` should contribute ZERO numbers (it still holds stale values that a naive refactor would re-emit).
- **3-visual-tier presentation** (Free / Analyst "Recommended" / Strategist anchor; Navigator de-emphasized).
- **Explorer free sweetener** (config-only): `num_watchlists_allowed_by_level['1']` 0->1 AND
  `num_watchlist_items` 0->5-10 (raising items while list count is 0 is inert - fix the list first).
- **Update `docs/TRADEWAVE_ECOSYSTEM.md`** tier/ML notes (per CLAUDE.md) in the commit that lands these.
- Delete the orphaned `web/templates/pricing.html` (optional cleanup).
