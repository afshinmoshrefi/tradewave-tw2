# TradeWave Free vs Paid Strategy - Research & Recommendation

> Status: HISTORICAL RESEARCH, not the current product decision. The shipped ladder
> keeps Explorer AI off, uses Navigator at $19 with three markets and no permanent AI,
> keeps Analyst at $47, and keeps Strategist at $129. See `PRICING_STRATEGY.md` and
> `../PRICING_QUOTA_SPEC.md`. The proposals below remain experiment hypotheses only.

> Produced by a 24-agent adversarial workflow (5 models generated, each scored by 3
> independent lenses - conversion economist, give-away/cannibalization skeptic,
> growth+feasibility - then synthesized). Grounded in the verified code levers and
> the owner's decisive audience signal: **small, price-sensitive, retains hard once
> onboarded.** Goal: more signups AND more paid upgrades. Date: 2026-06-20.

## Recommendation in one line

**The Open Floor + Catch Rung** - keep the 7-day reverse trial, but land it on a
*generous, never-expiring* Explorer floor (ML score ON for DJ30, date-unlock on
DJ30, the public scorecard), sell **breadth + automation** up the ladder, reprice
Analyst $47 -> $39, and add ONE new **$19 "Seasonal" catch tier** below it as a
staged second wave. Annual-first display + a one-shot 72h post-trial coupon.

## Executive summary

The audience is the whole strategy: habit is already solved, so the wall is
willingness-to-pay. That single fact says **do not abandon the reverse trial** (it is
the one instrument that builds full-product habit before the ask) and **do not black
out the floor it lands on** (a blackout makes a churned free user never return,
leaking the small funnel at the bottom). The core bet: a price-sensitive,
habit-formed user will never climb a $0->$47 cliff, but will pay "less than a coffee
a week" to keep doing the exact thing they already do daily, on more than one market.

ML-on-free is the highest-leverage move and nearly free to ship - the appserver
already half-allows it (`ml_score_access_levels` includes `'1'`, resource scope clips
it to DJ30), so it is a one-line reconcile, not a rewrite, with zero leak. The new
$19 tier is the one genuinely expensive part (DB migration + billing whitelist +
React rebuild - NOT the "config-flip" three of the five models wrongly claimed), so
it is staged second behind the cheap, reversible floor/ML/reprice changes that ship
in week one.

---

# TradeWave Pricing & Trial Model: Final Recommendation

**Decision owner:** Head of Growth
**Audience (decisive constraint):** small, price-sensitive, retains hard once onboarded. Habit is solved; WTP is the wall.
**Goal:** more signups AND more paid upgrades.

---

## 1. Verdict table across all 5 models

| # | Model | Reverse trial | Free floor | New SKU below $47? | Avg score | Any kill? | My call |
|---|-------|--------------|-----------|--------------------|-----------|-----------|---------|
| 1 | **The Ledger** (free-forever + $19 catch) | DROP | Generous DJ30 (ML on, 10 patterns, 1 watchlist) | Yes ($19) | 4.0 | No | Strong, but drops the trial - throws away the one structural advantage |
| 2 | **The Open Ledger** (pick + scorecard center) | MODIFY (7d→3d, secondary) | DJ30 + daily pick + ML | Yes ($19) | 4.0 | No | Best acquisition framing; 3d trial is vestigial; leans on an already-public asset |
| 3 | **The Open Floor** (DJ30-forever, breadth paywall) | **KEEP**, fix the floor | DJ30 full depth + ML + **date-unlock on DJ30** | Yes ($19) | 3.67 | No | **Closest to right.** Keeps the trial, fixes the cliff into a narrowing |
| 4 | **The Window Close** (founding-rate, annual-first) | KEEP as urgency engine | Unchanged + ML-on-DJ30 | No (founding annual only) | 3.67 | No | Verified price-cache collision bug; annual-only forfeits the frugal majority |
| 5 | **The Closed Door** (hard 10d trial, no floor) | MODIFY (7d→10d), lock floor to ZERO | **None** (locked out) | No | 3.33 | No | Burns the long tail + word-of-mouth; no-card trial is trivially abusable |

**Scoring read:** the three top models all share the same DNA - keep the reverse trial's habit-building, reconcile ML ON for the free DJ30 floor, and add a sub-$30 rung at the competitor price cluster. They diverge on whether to keep the trial (1 drops it, 3 keeps it) and on how much to lean on the scorecard. Every "give-away auditor" lens converged on the same two real risks: (a) the $19 tier cannibalizes the repriced Analyst, and (b) three of the five models hide a real code+schema+React cost under "config-flip."

---

## 2. Recommendation: **The Open Floor + Catch Rung** (a disciplined hybrid)

**Spine = Model 3 (The Open Floor).** Keep the 7-day reverse trial. Replace the post-trial *blackout* with a *narrowing*: the Explorer floor stays DJ30-only but becomes genuinely habit-sustaining - ML score ON for DJ30, start-date unlocked on DJ30 (hunt the Dow), the public daily pick + scorecard, limited Tara. The paywall sells **breadth** (the other 14 markets) and **automation** (watchlists/alerts, auto PE-cycle), not the core "aha."

**Graft from Model 1/2 (the $19 catch rung), staged second.** Insert one new "Seasonal" tier at $19/mo ($15/mo annual-equiv) - DJ30 + NASDAQ + S&P + Russell (resource IDs 0,1,2,3), ML on all four, date-unlocked on all four. This is the rung the trial steers to and the price-sensitive majority's painless yes.

**Graft from Model 4 (annual-first + a one-shot close), de-fanged.** Lead the pricing display with the annual monthly-equivalent. Fire ONE Stripe **coupon** (not a price edit) at trial expiry - a 72h "keep your access" first-period discount onto the $19/$39 rungs.

### Why this model, for THIS audience

1. **Keep the trial - it is the one structural advantage.** The owner's signal is decisive: habit is solved. The reverse trial is the only instrument that forms full-product habit (all 15 markets + ML) before the ask. Dropping it (Model 1) discards exactly the lever this audience hands us. The bug was never the trial; it was the cliff.

2. **Fix the cliff into a narrowing, not a blackout.** Today's floor (DJ30, NO ML, date-locked) yanks the very features that built the 7-day habit, then asks $47 to undo it - resentment, not payment, for a frugal user. Keeping ML + date-browse + the daily pick on DJ30 means a churned free user stays in orbit: re-marketable inventory, a standing word-of-mouth node, and a daily habit loop that keeps firing. For a brand with no ad budget, a retained free account is the cheapest growth asset there is.

3. **ML-on-free is the highest-leverage change and it is nearly free + leak-proof.** Code-verified: `ml_score_access_levels` already includes `'1'` (config.py:250), `ml_score_resource_ids` is US-stocks+ETFs (config.py:251), and Explorer's `resources_allowed=[0]` clips it to DJ30. The ONLY disagreement is `TIER_FEATURES['explorer'].ml_scoring=False` (config.py:613). Flipping it to `True` reconciles both systems, puts the differentiated "aha" in session 1, and is bounded to one market the user already cannot act on broadly (date-unlocked DJ30 is 30 mega-caps - the lowest-edge names). No leak, no infra cost.

4. **The $19 rung captures the bottom of a steep demand curve that is currently falling to $0.** The direct-analog price floor is $20-30 (Equity Clock $24.95, Barchart $29.95, Finviz $39.50, TradingView Essential $14.95). $47 is a gap with nothing below it; a comparison-shopping trader sees a $25 seasonality option before they reach us. $19 sits *below* every comparison-shop alternative, so the price-sensitive user has no cheaper exit. $19-realized beats $47-never.

5. **The upgrade trigger is loss-shaped, not feature-shaped.** The free user runs the ML-calibrated hunt daily on DJ30. The moment they spot a scorecard win on a NASDAQ/S&P name and click to run the same hunt there, they hit the breadth wall - "unlock 14 more markets from $15/mo." They are not buying a feature they have never felt; they are buying *more of the thing they already do every day*. That is the strongest possible conversion logic for someone who resists price but not value.

6. **The scorecard is the risk-killer on the paywall.** Price sensitivity is really risk sensitivity ("will I get my money's worth?"). A public, growing, permalinked win/loss record answers that *before* the ask. Surface it on the pricing page and at the trial cliff.

### Why NOT the others

- **Window Close (4):** has a verified billing bug - the price cache keys strictly on `(md_tier, md_period)` (app.py:1232) and reads no `founding` key, so a founding annual price collides with the standard annual slot and resolves nondeterministically ("using last-seen", app.py:1236). Worse for the audience: founding is annual-only, which *excludes the most price-sensitive users entirely* (they cannot lay out $288+ upfront in week 2), and the single window means one missed at-bat = gone forever. It bets the whole conversion budget on one moment.
- **Closed Door (5):** zeroing the floor forfeits the long tail (this audience converts on month 3-6 of free habit, not in a 10-day window) and kills the only durable word-of-mouth surface (a locked-out user is a detractor: "it locks you out"). The no-card 10-day full-Strategist trial is also trivially abusable by serial re-signup - exactly what an all-the-time frugal user will do - with no card/device/email dedupe proposed.

---

## 3. Runner-up ideas worth grafting (each justified against the auditor verdicts)

| Graft | From | Why it survives the auditor lenses |
|-------|------|-----------------------------------|
| **$19 Seasonal catch rung** | Ledger / Open Ledger | The auditors flagged cannibalization of the repriced Analyst. I narrow the basket to **4 markets (0,1,2,3)** and **no SMN / no PE-cycle / 1 watchlist**, so Analyst keeps a real reason to exist (8 markets + ETFs + indices/futures, SMN, manual PE-cycle, 5 watchlists). The rung sells the *verb* (hunt across 4 markets), which resists free-substitution. |
| **ML-on-free, reconciled ON** | All three top models | Auditor-confirmed leak-proof: scoped to DJ30 via `resources_allowed=[0]`; the appserver already half-allows it. A coherent one-line reconcile, not a contradiction left latent. |
| **Annual-first display** | Window Close / all | Reframes us from "above Seasonax" to "near Finviz," collects cash for the 60-day push, removes 11 monthly churn decisions. Conversion economist endorsed it. **De-fang:** show $19/mo as the visible default for the catch rung with annual as the discount badge - the *headline number* matters most to the most price-sensitive signup (per the growth lens on Model 2). |
| **One-shot 72h post-trial close** | Open Floor / Window Close | A Stripe **coupon**, not a price edit - sidesteps the FREEZE rule entirely (verified). One-shot + one-way per account so it does not train users to wait for standing discounts. Targets the $19/$39 rungs, not a deep annual lock. |
| **Public scorecard on the paywall** | Open Ledger | Already built + public (`generate_scorecard.py`, `featured_history.json`). Zero new give-away. The risk-killer that converts "is it worth $19?" into "this has a proven record." |

**Deliberately NOT grafted** (flaws a judge flagged):
- The **3-day breadth trial** (Open Ledger) - vestigial; either keep the full 7-day or kill it, do not half-measure. I keep 7.
- The **founding-rate annual lock** (Window Close) - the collision bug + annual-only exclusion of the frugal target.
- **Zeroing the floor** (Closed Door) - long-tail + word-of-mouth destruction.
- **Lowering Strategist to $129** (Open Ledger/Closed Door) - the $149 anchor is not the problem and its all-15/auto-PE buyer is a different segment; cutting it just gives back ARPU. Keep $149.

---

## 4. Open risks (named, with the guard I am shipping)

1. **Cannibalization: $19 Seasonal down-sells would-be $39 Analyst buyers.** Real and acknowledged by every auditor. Guard: narrow the Seasonal basket (4 markets, no SMN, no PE-cycle, 1 watchlist) so Analyst keeps felt value; **instrument the Seasonal→Analyst step-up rate** and the split of new-$19 vs. down-migrated-$47. If down-migration dominates net-new, widen the Analyst/Seasonal gap (drop Seasonal to 3 markets) rather than killing the rung.

2. **Blended-ARPU drag.** More conversions at $19 can lower revenue-per-paying-user even as count rises. Guard: this is the explicit metric in the experiment (track ARPU, not just conversion count) and the small-audience decision rule weights blended revenue, not raw conversion %.

3. **Free-rider ceiling: ML-on + date-unlocked DJ30 satisfies a Dow-only trader.** Guard: the start-date lock is removed *only on DJ30*; the other 14 markets stay date-locked-and-hidden via `level_access_hierarchy['1']=['0']`. The daily pick deliberately surfaces winners OFF DJ30 to manufacture the breadth itch (a content/selection discipline - flag to the ML-scorer owner; the config cannot guarantee it).

4. **The $19 tier is the ONE expensive change - do not ship it as a "config-flip."** Code-verified, a new `seasonal` tier requires: (a) widen `valid_tiers` at app.py:1219 AND the parallel set in generate_home_page.py:81; (b) a **DB migration** to widen `tier IN ('explorer','analyst','strategist','canceled')` at models.py:80 (else the subscription webhook 500s while Stripe charges - a silent revenue break); (c) **two** new legacy levels (monthly/yearly) across the 8 `num_*_by_level` + 3 `level_access_hierarchy*` dicts + `TIER_TO_LEGACY_LEVEL`/`LEGACY_LEVEL_TO_TIER` in tier_compat.py + ROLES; (d) the React wave-viewer gates on numeric `window.current_user_level → wpUserLevels`, so a new level is a **React rebuild + symlink-swap deploy**, not a config-only flip; (e) a price-cache slot collision is avoided because Seasonal uses its own `(tier='seasonal', period)` slots - fine once `valid_tiers` includes it. **This is why I stage the floor/ML/reprice changes (cheap, reversible) in week 1 and the new tier in week 2.**

5. **Tara leak vector.** "Limited Tara" must be hard-scoped to resource '0' + today, or a chatty user verbally extracts other-market/other-date signal and routes around the lock. Treat as a scoping requirement on the chatbot prompt, not an afterthought.

6. **Pricing display is hand-authored static HTML**, not driven by TIER_FEATURES. `generate_home_page.py` carries literal price fallbacks (lines 66-74) and a per-tier card block; adding a 4th column needs CSS + a regenerate + deploy across boxes (use the `tradewave-regen` skill).

---

## Config diffs to ship it

```
All changes are reversible. Stage in two waves: WAVE 1 = cheap config-flips + Stripe reprice (ship + A/B first); WAVE 2 = the new Seasonal tier (code + schema + React).

=================================================================
WAVE 1 - FLOOR + ML RECONCILE + REPRICE (config-flip + Stripe + restart)
=================================================================

--- /home/flask/config.py ---

[A] RECONCILE ML DRIFT in favor of ML-ON-FREE (the load-bearing one-line fix).
  ml_score_access_levels  : KEEP ['1','4','5','6','7']  (config.py:250 - already includes '1', leave it)
  ml_score_resource_ids   : KEEP ['0','1','2','3','4','11']  (config.py:251 - DJ30='0' covered; Explorer's resources_allowed=[0] clips ML to DJ30 only)
  TIER_FEATURES['explorer']['ml_scoring']:  False -> True   (config.py:613)
  # Net: both systems now agree Explorer sees ML, bounded to DJ30. ZERO leak (verified: resources_allowed=[0] is the clip).

[B] OPEN THE FLOOR - make Explorer habit-sustaining (a narrowing, not a blackout).
  TIER_FEATURES['explorer']:
    top_patterns_per_market:   5  -> 15      (config.py:608)
    change_start_date:         False -> True (config.py:609)   # date-unlock, but ONLY effective on DJ30 because resources_allowed=[0]
    portfolios_max:            1  -> 2       (config.py:614)
    tracked_opportunities_max: 5  -> 10      (config.py:615)
    # watchlists stay 0 (clean automation paywall); ml_scoring True from [A]
  max_opportunities_loggedin_free:  5 -> 15  (config.py:584)

  # START-DATE-ON-DJ30-FREE wiring: move '0' from the date-LOCKED list into the
  # date-UNLOCKED (premium) list for level '1', leaving the other 14 markets
  # locked-and-backend-hidden. level_access_hierarchy['1'] stays ['0'].
  level_access_hierarchy_free_registered['1']:
      ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','16']
   -> ['1','2','3','4','5','6','7','8','9','10','11','12','13','16']   # drop '0' (config.py:507)
  level_access_hierarchy_premium['1']:
      []  -> ['0']                                                    # add '0' = DJ30 date-unlocked (config.py:514)
  # level_access_hierarchy['1'] = ['0']  -> UNCHANGED (backend opp filter: DJ30 only, the 14-market withhold)

  num_portfolios_allowed_by_level['1']:  1 -> 2   (config.py:321)
  # num_watchlists_allowed_by_level['1'] stays 0 (config.py:329); num_opp_reports['1'] stays 5

--- /home/flask/site/generate_home_page.py ---  (display only - static, hand-authored)
  _stripe_prices() fallback dict (lines 66-74): update analyst_monthly '$47' -> '$39',
    analyst_yearly '$37' -> '$29', recompute the daily/savings strings.
    (Strategist UNCHANGED at $149/$99.)
  # The live values come from Stripe; this fallback must match so the page is correct if Stripe is unreachable.

--- STRIPE (stripe-edit + web restart to flush _price_cache; FREEZE rule: create NEW prices, never archive an active-sub price) ---
  Analyst: create new prices tier='analyst' period='monthly' $39, period='yearly' $348 ($29/mo-equiv),
           product_line='eod'.  (was $47/$37 - reprices the EXISTING tier, no schema/code change)
  Strategist: UNCHANGED ($149 / $99).
  After editing: systemctl restart the web unit (gunicorn does NOT auto-reload) to flush _price_cache={}.

--- POST-TRIAL CLOSE (Stripe COUPON, not a price - sidesteps FREEZE entirely) ---
  Create a one-shot coupon (e.g. 50% off first period) targeting the entry rungs; fire it by
  email/in-app at reverse_trial_ends_at + 0..72h. (web/promo_service.py + the affiliate/promo coupon plumbing already exists.)

--- DO NOT TOUCH in Wave 1 ---
  web/app.py:468 timedelta(days=7)  -> KEEP 7 (reverse trial length unchanged)
  effective_tier() elevation logic   -> UNCHANGED
  Strategist price/features           -> UNCHANGED ($149 anchor)

=================================================================
WAVE 2 - NEW $19 SEASONAL TIER (code + DB migration + React rebuild) - ship AFTER Wave 1 reads clean
=================================================================

[1] DB MIGRATION (required - else the subscription webhook 500s while Stripe charges):
    Alembic migration widening web/models.py:80 CheckConstraint:
      "tier IN ('explorer','analyst','strategist','canceled')"
   -> "tier IN ('explorer','seasonal','analyst','strategist','canceled')"

[2] BILLING WHITELIST (two places, both must change or the price is silently dropped):
    web/app.py:1219   valid_tiers = {"analyst","strategist"} -> add "seasonal"
    site/generate_home_page.py:81  valid_tiers = ('analyst','strategist') -> add 'seasonal'

[3] TIER_FEATURES['seasonal'] (config.py): resources_allowed=[0,1,2,3], top_patterns_per_market=50,
    change_start_date=True, ml_scoring=True, pe_cycle_filter_manual=False, pe_cycle_filter_auto=False,
    portfolios_max=5, tracked_opportunities_max=50, watchlists_max=1, watchlist_symbols_max=25,
    smn_articles=False, webinar_access=False, support_channel='community',
    monthly_price_launch=19, yearly_price_launch=15.

[4] NEW LEGACY LEVELS (two - monthly/yearly - to match the analyst 4/5, strategist 6/7 split):
    web/tier_compat.py: TIER_TO_LEGACY_LEVEL['seasonal']='2' (yearly default);
      LEGACY_LEVEL_TO_TIER: '2'->'seasonal', '3'->'seasonal'; add 'seasonal':0.5 rank between explorer(0) and analyst(1).
    config.py - add key '2' (and '3' mirror) to ALL of:
      level_access_hierarchy['2']=['0','1','2','3'];
      level_access_hierarchy_premium['2']=['0','1','2','3'] (date-unlocked);
      level_access_hierarchy_free_registered['2']=[];
      num_portfolios_allowed_by_level['2']=5; num_watchlists_allowed_by_level['2']=1;
      num_watchlist_items_allowed_by_level['2']=25; num_opp_reports_allowed_by_level['2']=25;
      num_daily_opp_reports_allowed_by_level['2']=25.
    web/models.py ROLES: add the seasonal tier where ROLES gates tier validation.

[5] REACT: window.current_user_level -> wpUserLevels must recognize level '2'/'3' or the wave-viewer
    mis-gates. This is a React-bundle change: npm run build (carries PUBLIC_URL=/app/) + symlink-swap deploy.

[6] STRIPE: new product, metadata product_line='eod', tier='seasonal', period monthly($19)/yearly($180 = $15/mo-equiv).
    Lands in its own (tier='seasonal', period) cache slots - no collision with analyst/strategist. Restart web.

[7] DISPLAY: add the Seasonal card to generate_home_page.py (4-up grid - needs CSS for the 4th column),
    lead annual monthly-equivalents, show $19/mo as the visible default for Seasonal with annual as a discount badge.
    Regenerate + deploy via the tradewave-regen skill across boxes.

ML RECONCILE FOR SEASONAL: 'seasonal' maps to legacy level '2'; add '2' to ml_score_access_levels so the
appserver grants ML on the seasonal markets. resources_allowed=[0,1,2,3] all sit inside ml_score_resource_ids
(['0','1','2','3','4','11']) so ML shows on all four Seasonal markets - consistent, no drift.
```

---

## Experiment plan

```
CONTEXT: traffic is LOW. A 50/50 split on a small funnel will NOT reach classical significance in weeks. So the design is (a) ship the cheap, leak-proof, reversible changes to 100% first and read them as a pre/post time-series, and (b) reserve true A/B only for the one reversible, riskier lever (the $19 rung), read with sequential/Bayesian thresholds, not a fixed-n p-value.

-----------------------------------------------------------------
PHASE 0 (WEEK 1) - SHIP-TO-ALL, PRE/POST (no split): the floor + ML + reprice
-----------------------------------------------------------------
HYPOTHESIS: An ML-on, date-unlocked-DJ30, never-expiring floor + a $39 (from $47) Analyst lifts
  trial->paid and free->paid WITHOUT lowering blended ARPU - because nothing here is a new SKU,
  it is a strictly-better floor + a modest reprice of an existing tier.
WHY NOT A/B: these are leak-proof, unambiguously-better, fully-reversible config flips (verified).
  Splitting them wastes a small funnel and risks showing the worse arm to half your users for weeks.
READ AS: 4-week pre vs 4-week post on the same cohort definition. Annotate the deploy date.
DECISION RULE: keep unless post-period free->paid OR signup->trial-completion DROPS materially
  (>15% relative) - which would only happen if ML-on-DJ30 over-satisfies (free-rider ceiling).
  Reversible in one config flip if so.

-----------------------------------------------------------------
PHASE 1 (WEEKS 3-10) - THE ONE TRUE A/B: the $19 Seasonal rung
-----------------------------------------------------------------
This is the only lever with real downside (cannibalization + ARPU drag) and real ship-cost, so it
is the only thing worth a controlled split.
  CONTROL  (A): ladder = Free / $39 Analyst / $149 Strategist  (post-Phase-0)
  VARIANT  (B): ladder = Free / $19 Seasonal / $39 Analyst / $149 Strategist
ASSIGNMENT: deterministic hash of user_id -> A/B, sticky, assigned at signup. Show the assigned
  ladder on the pricing page + at the trial cliff. (Keep both Stripe price sets live; the freeze
  rule is fine - only adding prices.)

METRICS TO INSTRUMENT (the 5 the funnel turns on + 2 ARPU guards):
  1. signup rate           (visitor -> account)            [should be FLAT - ladder change is post-signup; a drop = a display/perf regression]
  2. trial->paid %         (reverse-trial -> any paid)      [PRIMARY - does a cheap rung convert the frugal trial user?]
  3. free->paid %          (post-trial Explorer -> any paid)[PRIMARY - does the catch rung rescue never-payers?]
  4. day-7 retention       (free + paid)                    [GUARD - floor must keep firing the habit loop]
  5. ARPU (blended, per paying user)                        [THE decisive guard - $19 must not drag blended revenue below control]
  PLUS: 6. tier-mix split (% landing on $19 vs $39 vs $149) and 7. Seasonal->Analyst step-up rate
        [diagnoses cannibalization vs net-new: if most $19 buyers came FROM would-be $39, that is down-migration]

DECISION RULE (revenue-weighted, NOT conversion-count):
  SHIP B if, over the test window, B's TOTAL paid revenue per 100 signups >= A's
    AND day-7 retention is not worse. (More $19 conversions are only good if they are net-new or
    if their volume outweighs the per-seat ARPU they pull down.)
  KILL B (revert to A - just stop showing the rung; the SKU can stay dormant) if B's revenue-per-100
    is clearly below A OR if metric 7 shows would-be-$39 buyers overwhelmingly routing to $19
    (down-migration, not bottom-of-curve capture).
  NARROW B (do not kill) if it is borderline: drop Seasonal to 3 markets (0,1,2) to widen the gap to Analyst,
    and re-read - cheaper than killing the tier you just built.

HOW TO READ IT WITH A SMALL AUDIENCE (low traffic):
  - Do NOT wait for a fixed-n 95% p-value; you will never hit it. Use a SEQUENTIAL / Bayesian read:
    compute P(B revenue-per-100 > A) and stop when it crosses ~0.9 (ship) or ~0.1 (kill), or at a hard
    8-week cap, whichever first.
  - Because n is tiny, ANCHOR on revenue-per-100-signups (a continuous $ metric) rather than a binary
    conversion-rate - dollars have more signal per user than a yes/no.
  - Use the founder's "high engagement once onboarded" signal as a prior: expect the rung to LIFT
    conversion count; the open question is ARPU, so weight metric 5 + the tier-mix split heaviest.
  - Triangulate quant-thin data with 5-10 qualitative exit/upgrade-intent prompts ("what would you pay
    to keep hunting other markets?") at the trial cliff - in a small community, 8 clear verbal signals
    beat a noisy 2% delta.
  - Cohort by signup-week, not calendar-week, so the trial lag (7 days) does not smear the read.

ROLLBACK: every lever is reversible. Phase 0 = config flip + restart. Phase 1 kill = stop rendering the
  $19 card (Stripe price stays dormant, no archive needed; freeze rule untouched). No destructive edits anywhere.
```
